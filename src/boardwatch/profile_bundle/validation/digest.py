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
  not repeat promotion's parent checks, and that "ancestor links are traversed through stored
  manifest digests without deep revalidation". Reading a parent's *stable manifest envelope* is
  exactly that permitted traversal, and `read_ancestor_manifest` is the one reader that does it;
  loading an ancestor's documents is the deep parse, and only `deep=True` completeness does that.
- **It does not report a missing blob.** `validation/evidence.py` already does, under a code that
  names the file. Two codes for one missing blob is noise.
- **It does not restate `validate_history`'s findings.** The final change entry's revision and
  `change_id` are already compared there; only its parent digest is left, and it is checked here
  because it is a digest.
- **It computes nothing without a blob reader.** Every digest needs the blob bytes, and reporting a
  mismatch that was never computed would be a measurement nobody took. That silence is safe only
  because `validation/run.py` always supplies a reader, and a test asserts it there.

## A silence that is stated rather than assumed

Where this layer declines to compare, it says so. `candidate_digest_unverified` is an information
row carrying the typed reason no candidate digest was recomputed, because the deferral that
justifies the silence — `ancestry_completeness`'s `unverifiable_ancestor` blocker — runs only when
completeness is requested. On the default path a re-sealed revision whose parent directory was
deleted otherwise reported nothing at all, which is the same output as a revision whose approval was
verified. The tier is `information` so §21's "the selected revision remains structurally valid"
still holds exactly: the exit code does not move, only the ambiguity goes away.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final, Literal

from pydantic import PositiveInt, TypeAdapter, ValidationError

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
    RestrictedYamlError,
    UnsupportedSchemaVersionError,
    diagnostic,
    io_reason,
)
from boardwatch.profile_bundle.models.base import Sha256Digest, StrictModel
from boardwatch.profile_bundle.models.manifests import (
    BundleManifest,
    DraftManifest,
    RevisionManifest,
    StableManifestEnvelope,
)
from boardwatch.profile_bundle.paths import (
    complete_marker_path,
    current_path,
    digest_token,
    require_digest,
    revision_root,
)
from boardwatch.profile_bundle.schema import require_supported_schema
from boardwatch.profile_bundle.validation.context import ValidationContext
from boardwatch.profile_bundle.yaml_loader import load_yaml_bytes

MANIFEST_PATH = "manifest.yaml"
CHANGES_PATH = "history/changes.yaml"
CURRENT_PATH = "CURRENT"
COMPLETE_PATH = "COMPLETE"

_MANIFEST_ADAPTER: Final[TypeAdapter[BundleManifest]] = TypeAdapter(BundleManifest)

#: Why one ancestor could not be verified. Typed at the raise site so a consumer classifies on
#: `details["reason"]` rather than on the message text.
AncestorFault = Literal[
    "absent",
    "unreadable",
    "malformed",
    "unsupported_schema",
    "not_a_revision",
    "declared_digest_mismatch",
    "content_digest_mismatch",
    "cycle",
]

#: Why a run made no candidate-digest claim. A parent that could not be resolved keeps its own
#: `AncestorFault` rather than being flattened into one bucket, so `unverifiable_ancestor` and this
#: row describe the same absence in the same words; `not_recomputable` is everything else, which is
#: always another layer's finding (a missing blob, or a candidate view that cannot be inverted).
CandidateDigestGap = AncestorFault | Literal["not_recomputable"]


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


def current_pointer_bytes(pointer: CurrentPointer) -> bytes:
    """The one byte form of `CURRENT`: canonical JSON and exactly one trailing newline.

    Promotion writes these bytes and `read_current` requires them, so the contract has one owner.
    The alternative — a writer that emits a form and a reader that describes the same form in its
    own words — is how "canonical" becomes a word in a design document rather than a property of a
    file, which is exactly the state this replaces.

    Deliberately NOT `canonical.canonical_json_bytes`: that serializer is the bundle's *identity*
    algorithm, and `CURRENT` is excluded from every digest. Routing a pointer through it would
    couple the pointer's spelling to a hash contract it takes no part in, so that widening one would
    silently move the other.
    """
    return (
        json.dumps(
            pointer.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        + b"\n"
    )


def read_current(bundle_root: Path) -> CurrentPointer:
    """Parse `CURRENT`, refusing anything outside its exact contract.

    The contract is canonical JSON with exactly these two keys and one trailing newline, and it is
    enforced by re-emitting the parsed pointer through `current_pointer_bytes` and requiring the
    file to be those bytes. Stated that way rather than as a second description of the form, so the
    reader cannot drift from the writer: an added key, a reordering, or `json.dumps(indent=4)` all
    fail one comparison instead of three separate rules that each have to be remembered.

    Trailing content is refused rather than stripped for the same reason it always was: a pointer
    with extra bytes after the object is a torn write, and treating it as valid is how an
    interrupted promotion becomes the selected revision.
    """
    path = current_path(bundle_root)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise PointerError(f"{CURRENT_PATH} is unreadable: {io_reason(exc)}") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise PointerError(f"{CURRENT_PATH} is not valid JSON: {exc}") from exc
    try:
        pointer = CurrentPointer.model_validate(payload)
    except ValidationError as exc:
        raise PointerError(f"{CURRENT_PATH} is not a valid pointer: {exc}") from exc
    if raw != current_pointer_bytes(pointer):
        raise PointerError(
            f"{CURRENT_PATH} is not in the canonical pointer form: it must be exactly the compact "
            "key-sorted JSON object this bundle writes, followed by one newline"
        )
    return pointer


def read_complete(revision_dir: Path) -> str:
    """Parse a `COMPLETE` marker, whose entire content is `sha256:<64hex>` and one newline."""
    path = complete_marker_path(revision_dir)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PointerError(f"{COMPLETE_PATH} is unreadable: {io_reason(exc)}") from exc
    if not raw.endswith("\n") or raw.rstrip("\n") != raw[:-1]:
        raise PointerError(f"{COMPLETE_PATH} must end with exactly one newline")
    try:
        return require_digest(raw[:-1])
    except BundlePathError as exc:
        raise PointerError(f"{COMPLETE_PATH} does not carry a digest: {exc}") from exc


class AncestorUnverifiable(ProfileBundleError):
    """One ancestor could not be read, with the reason typed rather than described."""

    def __init__(self, reason: AncestorFault, message: str) -> None:
        super().__init__(message)
        self.reason: AncestorFault = reason


@dataclass(frozen=True)
class AncestorRevision:
    """One ancestor's directory and its parsed manifest, as read through its stable envelope."""

    root: Path
    manifest: RevisionManifest


def read_ancestor_manifest(bundle_root: Path, digest: str) -> AncestorRevision:
    """Read one ancestor's manifest from disk, refusing anything that is not a promoted revision.

    The one reader for §20.6's permitted ancestor traversal. Two callers need it and they need it
    to agree: `completeness.ancestry_completeness` walks the chain and reports each failure as an
    `unverifiable_ancestor` blocker, and `_the_candidate_view_recomputes_its_approved_digest` needs
    the direct parent's `revision` and `bundle_digest` — the `StableManifestEnvelope` fields, and
    nothing else — to recompute the candidate view of a child revision. A second reader would be a
    second set of rules about what counts as a readable ancestor.

    Nothing here loads the ancestor's other documents. That is the deep parse §20.6 says validating
    an already-selected revision does not do; `completeness._audit_ancestor_bytes` is the opt-in
    that does, and it layers on top of this.
    """
    try:
        root = revision_root(bundle_root, digest)
    except BundlePathError as exc:
        raise AncestorUnverifiable("malformed", str(exc)) from exc
    path = root / MANIFEST_PATH
    logical = PurePosixPath(root.name) / MANIFEST_PATH
    if not root.is_dir() or not path.is_file():
        raise AncestorUnverifiable("absent", f"{root.name} is not on disk")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise AncestorUnverifiable(
            "unreadable", f"{logical} is unreadable: {io_reason(exc)}"
        ) from exc
    try:
        parsed = load_yaml_bytes(raw, logical_path=PurePosixPath(MANIFEST_PATH))
        manifest = _MANIFEST_ADAPTER.validate_python(parsed)
    except (RestrictedYamlError, ValidationError) as exc:
        raise AncestorUnverifiable("malformed", f"its manifest does not parse: {exc}") from exc
    try:
        require_supported_schema(manifest.schema_version)
    except UnsupportedSchemaVersionError as exc:
        raise AncestorUnverifiable("unsupported_schema", str(exc)) from exc
    if not isinstance(manifest, RevisionManifest):
        raise AncestorUnverifiable(
            "not_a_revision", "its manifest declares state 'draft'; an ancestor is always promoted"
        )
    if manifest.bundle_digest != digest:
        raise AncestorUnverifiable(
            "declared_digest_mismatch",
            f"the directory names {digest} but its manifest declares {manifest.bundle_digest}",
        )
    return AncestorRevision(root=root, manifest=manifest)


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

    It must fire at every revision, not only the first. A child's candidate view folds in its
    parent's revision number and digest, and an earlier form of this check declined the comparison
    whenever no `ParentSnapshot` had been handed in — which `validate_bundle` never does, so the
    clause was skipped for every revision from 2 onward. Re-sealing such a tree around content no
    owner approved passed every other digest check, because every other digest is recomputed from
    the new bytes. `recomputed_candidate_digest` closes it by reading the parent's stable envelope
    from disk, the traversal §20.6 explicitly permits.
    """
    manifest = ctx.manifest
    if isinstance(manifest, DraftManifest):
        return
    computed, gap = _candidate_digest_claim(ctx)
    if computed is None:
        # The comparison did not happen, and saying so is not the same as reporting the cause.
        #
        # The cause always belongs to another layer: a missing blob is `validation/evidence.py`'s
        # finding, a final-`change_id` mismatch that makes the candidate view unrecoverable is
        # `validate_history`'s, and an unreadable ancestor is `ancestry_completeness`'s
        # `unverifiable_ancestor`. Restating any of them here under a digest code sends an operator
        # hunting for a second problem, so this row names the gap and types the reason instead.
        #
        # It is emitted rather than skipped because only ONE of those three deferrals runs on this
        # path. `ancestry_completeness` runs only under `completeness=True`, so a re-sealed revision
        # whose parent directory had been deleted reported no diagnostics and exited 0 — the same
        # shape as a revision whose approval was verified. §21 keeps such a revision structurally
        # valid, so the tier here is `information`, which never moves an exit code.
        yield diagnostic(
            IssueCode.CANDIDATE_DIGEST_UNVERIFIED,
            "no candidate digest could be recomputed for this revision, so its approved candidate "
            "digest was not compared against its content; this run makes no claim about it",
            path=MANIFEST_PATH,
            reason=gap,
        )
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


def recomputed_candidate_digest(ctx: ValidationContext) -> str | None:
    """The candidate digest a promoted revision reduces back to, or `None` when none can be claimed.

    Public because the report needs the same value the check compares: printing the manifest's
    declared `approved_candidate_digest` would make a never-verified number indistinguishable from a
    verified one in machine output, and `None` here is precisely "this run made no claim".

    The parent is resolved in one of two ways and never guessed at. A caller that already holds the
    parent — promotion does — supplies a `ParentSnapshot`; anyone else gets it read from disk, since
    §20.6 permits traversing ancestor links through their stored manifest digests. Only the stable
    envelope's `revision` and `bundle_digest` are read — exactly what
    `canonical._candidate_manifest` consumes.
    """
    return _candidate_digest_claim(ctx)[0]


def _candidate_digest_claim(
    ctx: ValidationContext,
) -> tuple[str | None, CandidateDigestGap | None]:
    """The recomputed candidate digest, or `None` and the typed reason there is none.

    Both halves come from one call because the check that compares the digest and the row that
    reports its absence need the same answer, and asking twice could give two.

    A parent that could not be resolved keeps `AncestorUnverifiable`'s own `reason`, so "the
    directory is gone" and "the manifest does not parse" stay distinguishable in `details` — the
    same fault vocabulary `ancestry_completeness` reports under, rather than a second one.
    """
    manifest = ctx.manifest
    blobs = ctx.blobs
    if isinstance(manifest, DraftManifest) or blobs is None:
        return None, "not_recomputable"
    try:
        parent = _parent_envelope(ctx, manifest)
    except AncestorUnverifiable as exc:
        return None, exc.reason
    computed = _computed(lambda: candidate_digest_from_revision(ctx.documents, blobs, parent))
    return (computed, None) if computed is not None else (None, "not_recomputable")


def _parent_envelope(
    ctx: ValidationContext, manifest: RevisionManifest
) -> StableManifestEnvelope | None:
    """The direct parent's stable envelope, `None` for revision 1, or a typed refusal.

    `None` is a real answer — revision 1 has no parent and its candidate view says so — which is why
    an unreadable parent raises rather than returning `None`: folding "there is no parent" into
    "the parent could not be read" would compare a child revision against a parentless candidate
    view and report every such revision as a forgery.
    """
    declared = manifest.parent_bundle_digest
    if declared is None:
        return None
    if ctx.parent is not None:
        return ctx.parent.envelope
    if ctx.bundle_root is None:
        raise AncestorUnverifiable("absent", "no bundle root was supplied to resolve the parent in")
    return read_ancestor_manifest(ctx.bundle_root, declared).manifest.envelope


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
    "AncestorFault",
    "AncestorRevision",
    "AncestorUnverifiable",
    "CandidateDigestGap",
    "CurrentPointer",
    "PointerError",
    "current_pointer_bytes",
    "read_ancestor_manifest",
    "read_complete",
    "read_current",
    "recomputed_candidate_digest",
    "validate_digest",
]
