"""Digest validation: the layer that makes every other layer's guarantee durable (design §20.6).

A revision that once validated cleanly and whose bytes have since changed is unusable, and nothing
in the other layers can tell. They read the documents; this one asks whether the documents are still
the ones that were promoted and approved.

## Four artifacts, four ways to disagree

A promoted revision states its identity in four places: the directory name, the `COMPLETE` marker,
`manifest.bundle_digest`, and `CURRENT`. Each disagreement is reported under its own code rather
than folded into one, because "the directory was renamed", "the marker is missing" and "the
manifest was edited" call for different actions, and an operator who cannot tell them apart guesses.

## Two comparisons that look redundant and are not

`canonical._manifest_with` **overwrites** the manifest's declared `evidence_set_digest` with the
recomputed value before hashing the manifest leaf. A forged declared value therefore does not move
`bundle_digest` at all, so it needs its own comparison or it can never be detected. The same shape
applies to the candidate digest: it is checked against the manifest *and* the approval stamp,
because editing both together is a forgery that either comparison alone accepts.

## What this layer deliberately does not do

- **It does not deep-parse ancestors.** §20.6 says validation of an already-selected revision does
  not repeat promotion's parent checks. That is implemented by omission.
- **It does not report a missing blob.** `validation/evidence.py` already does, under a code that
  names the file. Two codes for one missing blob is noise.
- **It does not restate `validate_history`'s findings.** The final change entry's revision and
  `change_id` are already compared there; only its parent digest is left, and it is checked here
  because it is a digest.
- **It computes nothing without a blob reader.** Every digest needs the blob bytes, and reporting a
  mismatch that was never computed would be a measurement nobody took. That silence is safe only
  because `validation/run.py` always supplies a reader, and a test asserts it there.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path

from pydantic import PositiveInt, ValidationError

from boardwatch.profile_bundle.canonical import (
    CanonicalizationError,
    MissingBlobError,
    bundle_digest,
    candidate_digest_from_revision,
    evidence_set_digest,
)
from boardwatch.profile_bundle.errors import (
    BundlePathError,
    Diagnostic,
    IssueCode,
    ProfileBundleError,
    diagnostic,
)
from boardwatch.profile_bundle.models.base import Sha256Digest, StrictModel
from boardwatch.profile_bundle.models.manifests import DraftManifest
from boardwatch.profile_bundle.paths import (
    complete_marker_path,
    current_path,
    digest_token,
    require_digest,
)
from boardwatch.profile_bundle.validation.context import ValidationContext

MANIFEST_PATH = "manifest.yaml"
CHANGES_PATH = "history/changes.yaml"
CURRENT_PATH = "CURRENT"
COMPLETE_PATH = "COMPLETE"


class PointerError(ProfileBundleError):
    """A `CURRENT` or `COMPLETE` file that is absent, unreadable, or outside its exact contract."""


class CurrentPointer(StrictModel):
    """The whole content of `CURRENT`: which revision is selected, and its digest.

    A `StrictModel` rather than a hand-parsed dict so an unexpected key is refused instead of
    ignored. `CURRENT` is the file promotion replaces atomically as its commit point, and a reader
    that tolerates a superset is how a half-written pointer from a future format gets accepted as a
    valid one.

    Defined here rather than in storage because this is the layer that first needs to read it;
    T14's `read_current_once` wraps this model instead of parsing the file a second way. Two readers
    for one 45-byte file is two chances to disagree about what it says.
    """

    bundle_digest: Sha256Digest
    revision: PositiveInt


def read_current(bundle_root: Path) -> CurrentPointer:
    """Parse `CURRENT`, refusing anything outside its exact contract.

    The contract is canonical JSON with exactly these two keys and one trailing newline. Trailing
    content is refused rather than stripped: a pointer with extra bytes after the object is a torn
    write, and treating it as valid is how an interrupted promotion becomes the selected revision.
    """
    path = current_path(bundle_root)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PointerError(f"{CURRENT_PATH} is unreadable: {exc}") from exc
    if not raw.endswith("\n") or raw.rstrip("\n") != raw[:-1]:
        raise PointerError(f"{CURRENT_PATH} must end with exactly one newline")
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise PointerError(f"{CURRENT_PATH} is not valid JSON: {exc}") from exc
    try:
        return CurrentPointer.model_validate(payload)
    except ValidationError as exc:
        raise PointerError(f"{CURRENT_PATH} is not a valid pointer: {exc}") from exc


def read_complete(revision_dir: Path) -> str:
    """Parse a `COMPLETE` marker, whose entire content is `sha256:<64hex>` and one newline."""
    path = complete_marker_path(revision_dir)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PointerError(f"{COMPLETE_PATH} is unreadable: {exc}") from exc
    if not raw.endswith("\n") or raw.rstrip("\n") != raw[:-1]:
        raise PointerError(f"{COMPLETE_PATH} must end with exactly one newline")
    try:
        return require_digest(raw[:-1])
    except BundlePathError as exc:
        raise PointerError(f"{COMPLETE_PATH} does not carry a digest: {exc}") from exc


def validate_digest(ctx: ValidationContext) -> tuple[Diagnostic, ...]:
    """Every digest finding that makes the revision invalid (§20.6)."""
    if ctx.blobs is None:
        return ()
    return tuple(
        finding
        for check in (
            _the_manifest_state_matches_the_tree,
            _the_evidence_set_digest_is_recomputed,
            _the_bundle_digest_is_the_one_on_disk,
            _the_directory_and_marker_name_this_manifest,
            _the_current_pointer_agrees_when_it_names_this_revision,
            _the_candidate_view_recomputes_its_approved_digest,
            _the_final_change_names_the_same_parent,
        )
        for finding in check(ctx)
    )


def _the_manifest_state_matches_the_tree(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """A draft manifest in a revision tree, or the reverse.

    `load_documents`'s `mode` decides only whether a `COMPLETE` marker is admissible beside the
    documents; it never compares `manifest.state` to the mode it was handed. So a promoted tree
    carrying draft sentinels, or a draft carrying a real `bundle_digest`, parses without complaint.
    """
    expected = "revision" if ctx.mode == "revision" else "draft"
    if ctx.manifest.state != expected:
        yield diagnostic(
            IssueCode.DRAFT_MANIFEST_INVALID,
            f"the tree was read as a {expected} but its manifest declares "
            f"state {ctx.manifest.state!r}",
            path=MANIFEST_PATH,
        )


def _the_evidence_set_digest_is_recomputed(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """The declared evidence-set digest, which the bundle digest provably cannot police."""
    blobs = ctx.blobs
    assert blobs is not None  # `validate_digest` returns early without a reader
    computed = _computed(lambda: evidence_set_digest(ctx.documents, blobs))
    if computed is None or computed == ctx.manifest.evidence_set_digest:
        return
    yield diagnostic(
        IssueCode.EVIDENCE_SET_DIGEST_MISMATCH,
        "the manifest's evidence_set_digest is not the one its evidence records and blobs produce",
        path=MANIFEST_PATH,
        declared=ctx.manifest.evidence_set_digest,
        computed=computed,
    )


def _the_bundle_digest_is_the_one_on_disk(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """§21: evidence or a revision mutated after promotion is a digest failure.

    A draft is exempt: its `bundle_digest` is `Literal[""]` by contract, so there is no claim to
    check. Promotion is where the claim is made.
    """
    manifest = ctx.manifest
    if isinstance(manifest, DraftManifest):
        return
    computed = _bundle_digest_of(ctx)
    if computed is None or computed == manifest.bundle_digest:
        return
    yield diagnostic(
        IssueCode.BUNDLE_DIGEST_MISMATCH,
        "the revision's documents and blobs do not produce the digest its manifest carries",
        path=MANIFEST_PATH,
        declared=manifest.bundle_digest,
        computed=computed,
    )


def _the_directory_and_marker_name_this_manifest(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """The directory name and `COMPLETE` must both name the manifest's digest.

    Both are compared against the manifest rather than against the recomputed digest, so that a
    mutated document reports one mismatch (the bundle digest) instead of three.
    """
    manifest = ctx.manifest
    if isinstance(manifest, DraftManifest):
        return
    expected = digest_token(manifest.bundle_digest)
    if ctx.root.name != expected:
        yield diagnostic(
            IssueCode.MANIFEST_DIRECTORY_MISMATCH,
            f"the revision directory is named {ctx.root.name!r} but its manifest declares "
            f"{manifest.bundle_digest}",
            path=MANIFEST_PATH,
            directory=ctx.root.name,
        )
    try:
        marker = read_complete(ctx.root)
    except PointerError as exc:
        yield diagnostic(
            IssueCode.COMPLETE_MARKER_MISSING,
            f"the revision has no usable COMPLETE marker: {exc}",
            path=COMPLETE_PATH,
        )
        return
    if marker != manifest.bundle_digest:
        yield diagnostic(
            IssueCode.MANIFEST_DIRECTORY_MISMATCH,
            f"COMPLETE names {marker} but the manifest declares {manifest.bundle_digest}",
            path=COMPLETE_PATH,
            marker=marker,
        )


def _the_current_pointer_agrees_when_it_names_this_revision(
    ctx: ValidationContext,
) -> Iterator[Diagnostic]:
    """`CURRENT` must agree with the manifest of the revision it selects — and only that one.

    An unselected revision is retained, not wrong: §21 forbids deleting unselected digest
    directories, so reporting "this is not current" would make inspecting an older revision
    permanently red. The pointer is therefore only compared when it names this tree, or when this
    tree claims the revision number the pointer selects.
    """
    manifest = ctx.manifest
    if isinstance(manifest, DraftManifest) or ctx.bundle_root is None:
        return
    try:
        pointer = read_current(ctx.bundle_root)
    except PointerError as exc:
        yield diagnostic(
            IssueCode.CURRENT_POINTER_MISMATCH,
            f"CURRENT could not be read, so the selected revision is unknown: {exc}",
            path=CURRENT_PATH,
        )
        return
    names_this_tree = pointer.bundle_digest == manifest.bundle_digest
    claims_this_number = pointer.revision == manifest.revision
    if names_this_tree == claims_this_number:
        return
    yield diagnostic(
        IssueCode.CURRENT_POINTER_MISMATCH,
        f"CURRENT selects revision {pointer.revision} at {pointer.bundle_digest}, which matches "
        f"revision {manifest.revision} at {manifest.bundle_digest} in only one of the two",
        path=CURRENT_PATH,
        pointer_digest=pointer.bundle_digest,
        pointer_revision=pointer.revision,
    )


def _the_candidate_view_recomputes_its_approved_digest(
    ctx: ValidationContext,
) -> Iterator[Diagnostic]:
    """The promoted revision must reduce back to the candidate digest the owner approved.

    This is what binds an approval to content rather than to a name. It is compared against the
    manifest *and* the final approval stamp: editing both together is a forgery that either
    comparison alone accepts.
    """
    manifest = ctx.manifest
    if isinstance(manifest, DraftManifest):
        return
    if manifest.parent_bundle_digest is not None and ctx.parent is None:
        # The candidate view of a child revision folds in its parent's revision number and digest,
        # so without the parent snapshot the recomputation is not merely approximate — it is a
        # different digest, and comparing it would report EVERY revision after the first as a
        # mismatch. §20.6 says validating an already-selected revision does not deep-parse
        # ancestors, so the honest behaviour when the ancestor was not supplied is to make no claim.
        # Promotion (which always holds the parent) is where this becomes mandatory.
        return
    blobs = ctx.blobs
    assert blobs is not None  # `validate_digest` returns early without a reader
    parent = ctx.parent.envelope if ctx.parent is not None else None
    computed = _computed(lambda: candidate_digest_from_revision(ctx.documents, blobs, parent))
    if computed is None:
        # `candidate_digest_from_revision` raises on the same final-`change_id` mismatch
        # `validate_history` already reports. Silence here leaves the operator one finding.
        return
    if computed != manifest.approved_candidate_digest:
        yield diagnostic(
            IssueCode.CANDIDATE_DIGEST_MISMATCH,
            "the revision's inverse candidate view does not recompute the candidate digest its "
            "manifest says was approved",
            path=MANIFEST_PATH,
            declared=manifest.approved_candidate_digest,
            computed=computed,
        )
    stamps = ctx.index.stamps
    if stamps and stamps[-1].candidate_content_digest != computed:
        yield diagnostic(
            IssueCode.CANDIDATE_DIGEST_MISMATCH,
            "the final approval stamp approved a candidate digest the revision does not recompute",
            path="history/approvals.yaml",
            record_id=stamps[-1].approval_stamp_id,
            declared=stamps[-1].candidate_content_digest,
            computed=computed,
        )


def _the_final_change_names_the_same_parent(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """§20.6 clause 3, minus the two halves `validate_history` already owns."""
    manifest = ctx.manifest
    if isinstance(manifest, DraftManifest):
        return
    changes = ctx.index.changes
    if not changes:
        return
    if changes[-1].parent_bundle_digest != manifest.parent_bundle_digest:
        yield diagnostic(
            IssueCode.CHANGE_ENTRY_MISMATCH,
            "the final change entry names a different parent digest than the manifest",
            path=CHANGES_PATH,
            record_id=changes[-1].change_id,
        )


def _bundle_digest_of(ctx: ValidationContext) -> str | None:
    blobs = ctx.blobs
    assert blobs is not None  # `validate_digest` returns early without a reader
    return _computed(lambda: bundle_digest(ctx.documents, blobs))


def _computed(compute: Callable[[], str]) -> str | None:
    """Run a digest computation, returning `None` when another layer owns the failure.

    A missing blob is `validation/evidence.py`'s finding and a recoverable-candidate failure is
    `validate_history`'s; both would otherwise surface here a second time under a digest code, and
    an operator seeing two codes for one cause fixes one and hunts for a second problem.
    """
    try:
        return compute()
    except (MissingBlobError, CanonicalizationError):
        return None


__all__ = [
    "CurrentPointer",
    "PointerError",
    "read_complete",
    "read_current",
    "validate_digest",
]
