"""`promote`: where an owner's approval becomes an immutable revision (design §6, §7, §17, §19).

Everything else in this package reads a revision. This is the one thing that makes one, so its
failure modes are the ones the whole bundle inherits.

## The nine steps are the contract, not an outline

§6 numbers them and this module runs them in that order:
1. Take the exclusive bundle lock, **non-blocking**. Contention is `bundle_lock_held`, exit 3, and
   no write. "No wait" is literal on POSIX; on Windows the acquire pays a bounded reclaim window
   first, which is D-224's recorded departure, described in `locking.py` rather than restated here.
2. Re-check that the draft's parent is still `CURRENT`. A mismatch is `stale_draft_parent` with the
   draft left exactly as it was, because `rebase-draft` is the drain for it.
3. Derive the next revision as `CURRENT.revision + 1` — contiguous along the selected chain, and
   never a directory name.
4. Validate the direct parent, compare the ledgers as exact prefixes, and bind the draft to its
   owner-approval stamp through the candidate digest.
5. Write the next revision into a same-filesystem temporary directory.
6. **Re-read the whole temporary tree from disk** and validate it, then write `COMPLETE` last.
7. Rename the complete directory to `revisions/sha256-<digest>`, reusing an exact existing target
   and refusing any other.
8. Write a temporary `CURRENT`, flush and close it, and `os.replace` it into place.
9. Release the lock.

The commit point is the single `os.replace` in step 8. Everything before it is invisible to a
reader: `read_current_once` reads the pointer once, resolves the digest-named directory it names,
and requires that directory's `COMPLETE`. So a promotion killed at any earlier boundary leaves
readers on the complete old selection, and one killed after it leaves them on the complete new one.
There is no third state, and that is the whole point of writing `COMPLETE` before the rename and the
pointer after it.

**This is a process-crash guarantee and nothing more.** Nothing here fsyncs a directory or claims
that a power cut cannot lose a rename the kernel acknowledged. Each file is written, flushed and
closed before the tree is re-read, which is what makes the bytes visible to any other process — not
what makes them survive the machine losing power.

## Why the temporary tree is nested under a digest-named directory

Step 6 says validate *before* `COMPLETE` exists, and §20.6 makes the directory name part of a
revision's identity. So the staged tree is built at
`revisions/.tmp-promotion-<random>/sha256-<digest>/`: the inner directory already carries its final
name, so the from-disk validation is the same validation a reader will run later rather than a
weakened one, and step 7 is a plain rename of the inner directory. The two clauses that cannot pass
yet are named in `_DEFERRED_TO_A_LATER_STEP`, and each is re-asserted where it lands — `COMPLETE` is
read back after it is written, and the pointer is resolved through `read_current_once` after it is
replaced. Nothing is dropped; two things are deferred and then checked.

## What is deleted, and what is never deleted

§21 forbids deleting revisions, drafts, blobs and unselected digest directories, and this command
does not. A successful promotion leaves the draft where it was — the owner may still want it, and
removing it is not promotion's decision to make.

The one thing removed is this command's own staging directory, created under
`PROMOTION_TEMP_PREFIX` in this operation, and only in two cases: a refusal that never renamed it
anywhere, and step 7 finding a byte-identical target already in place, where `identical_trees` has
proved the same bytes are retained. A target that *differs* is the opposite case — both directories
are retained, `CURRENT` is untouched, and `inventory` reports the leftover.

## The parent is passed, never rediscovered

Promotion is the one caller that already holds the parent, so it hands it over as a
`ParentSnapshot` instead of letting the validation layer resolve it from disk. Two parent-shaped
parameters exist and they are not interchangeable: `candidate_content_digest` takes the parent's
**manifest envelope**, and `required_approval_decisions` (reached through `validate_history`) takes
the parent's **documents**. Swapping them type-checks under neither and fails deep inside
`build_index`.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Final

from boardwatch.profile_bundle.blobs import quarantined_blobs
from boardwatch.profile_bundle.canonical import (
    APPROVAL_LEDGER_PATH,
    CHANGE_LEDGER_PATH,
    EVIDENCE_PATH,
    MANIFEST_PATH,
    CanonicalizationError,
    FilesystemBlobReader,
    MissingBlobError,
    bundle_digest,
    candidate_content_digest,
    evidence_set_digest,
    record_digest,
    referenced_blob_digests,
)
from boardwatch.profile_bundle.diff import RecordIdCollision, diff_records, record_contents
from boardwatch.profile_bundle.errors import (
    BundleIoError,
    Diagnostic,
    IssueCode,
    OperationOutcome,
    ProfileBundleError,
    RestrictedYamlError,
    diagnostic,
    io_reason,
    outcome_with,
)
from boardwatch.profile_bundle.index import build_index
from boardwatch.profile_bundle.layout import (
    ENTITY_DOCUMENT_DIRECTORIES,
    DocumentKind,
    discover_source_files,
)
from boardwatch.profile_bundle.locking import BundleLockHeldError, bundle_lock
from boardwatch.profile_bundle.models.documents import BundleDocuments, DocumentModel
from boardwatch.profile_bundle.models.history import (
    Actor,
    ApprovalLedger,
    ApprovalStamp,
    ChangeLedger,
    ChangeRecord,
)
from boardwatch.profile_bundle.models.manifests import DraftManifest, RevisionManifest
from boardwatch.profile_bundle.paths import (
    approval_path,
    blobs_dir,
    complete_marker_path,
    current_path,
    digest_token,
    draft_root,
    require_draft_segment,
    revision_root,
    revisions_dir,
)
from boardwatch.profile_bundle.storage import (
    SelectedRevision,
    SelectionError,
    identical_trees,
    read_current_once,
    selected_documents,
)
from boardwatch.profile_bundle.validation.context import (
    ParentSnapshot,
    load_documents,
    parse_error_diagnostics,
)
from boardwatch.profile_bundle.validation.digest import (
    CurrentPointer,
    PointerError,
    current_pointer_bytes,
    read_complete,
)
from boardwatch.profile_bundle.validation.run import validate_bundle
from boardwatch.profile_bundle.yaml_loader import load_yaml_bytes
from boardwatch.profile_bundle.yaml_writer import document_bytes

#: The prefix every staged promotion uses, directly under `revisions/`. Same filesystem as the
#: target, which is what makes step 7 a rename rather than a copy. A leftover is reported by
#: `inventory` under its existing "this directory holds only digest-named revisions" finding, so no
#: second rule about what belongs there is needed here.
PROMOTION_TEMP_PREFIX: Final = ".tmp-promotion-"

#: The prefix the staged `CURRENT` uses. It sits at the bundle root because that is where its
#: destination is and `os.replace` needs both on one filesystem; a leftover is genuinely outside the
#: closed root grammar and `inventory` reports it as an undeclared entry.
CURRENT_TEMP_PREFIX: Final = ".tmp-current-"

#: The placeholder `bundle_digest` the manifest carries while its own digest is being computed.
#: `canonical._manifest_with` blanks this field before hashing the manifest leaf, so its value
#: cannot influence the digest it is about to become; it exists only because the field is a
#: `Sha256Digest` and the model refuses anything else.
_PENDING_DIGEST: Final = "sha256:" + "0" * 64

#: The three documents promotion derives. Everything else is copied from the draft byte for byte,
#: for the reason `checkout` copies: re-emitting rewrites bytes the owner never touched and makes
#: the first diff against the new revision unreadable.
_DERIVED_DOCUMENTS: Final[frozenset[PurePosixPath]] = frozenset(
    {MANIFEST_PATH, CHANGE_LEDGER_PATH, APPROVAL_LEDGER_PATH}
)

#: The two §20.6 clauses the step-6 validation cannot satisfy, because they are about artefacts
#: steps 6 and 8 have deliberately not written yet. Neither is dropped: `COMPLETE` is read back
#: through `read_complete` once written, and the pointer is resolved through `read_current_once`
#: once replaced. `current_pointer_mismatch` additionally cannot report anything new here — for a
#: first promotion there is no `CURRENT` at all, and for every later one step 2 has already resolved
#: it and refused if it could not.
_DEFERRED_TO_A_LATER_STEP: Final[frozenset[str]] = frozenset(
    {str(IssueCode.COMPLETE_MARKER_MISSING), str(IssueCode.CURRENT_POINTER_MISMATCH)}
)


class TargetConflictReason(StrEnum):
    """Why an existing digest target could not be reused. Typed at the raise site (§6 step 7)."""

    MARKER_MISSING = "marker_missing"
    CONTENT_DIFFERS = "content_differs"


@dataclass(frozen=True)
class PromotionRequest:
    """What the operator supplies; everything else about the revision is derived.

    `actor` is `models.history.Actor` rather than a second spelling of the same closed set: §17
    already fixes it to `owner`, `agent` or `importer`, and `created_by` in the manifest and `actor`
    in the change record are both that enum. `authorized_by` is deliberately absent — §17 derives it
    from the approval stamp, so it is not the caller's to state.

    `created_at` is passed in because nothing under `profile_bundle/` reads a clock: a revision's
    timestamp is part of its identity, and a package that invented one would make the same bytes
    hash differently depending on when they were promoted.
    """

    draft_name: str
    summary: str
    actor: Actor
    created_at: datetime


def promote(
    bundle_root: Path, request: PromotionRequest
) -> OperationOutcome[SelectedRevision]:
    """Promote `drafts/<name>` into the next immutable revision and select it (§6, §19)."""
    # Confinement first and outside the lock, exactly as `rebase-draft` does it: a name that could
    # escape `drafts/` would decide where the staging tree and the pointer go, and that must not be
    # settled while holding a lock another writer is waiting on. The segment grammar, because this
    # addresses a draft that already exists: every name `inventory` lists under `drafts/` must be
    # one this command will take, and the shorter operator-facing cap refuses the rebase backup of
    # a long draft name — the one directory that is the only copy of a pre-rebase draft.
    draft_name = require_draft_segment(request.draft_name)
    # Before the lock, because `filelock` creates the lockfile's directory: a mistyped `--bundle`
    # would otherwise leave a new empty directory behind as the only trace of a failed command.
    if not bundle_root.is_dir():
        return _refusal(
            IssueCode.BUNDLE_NOT_FOUND,
            "there is no bundle at the requested path, so there is no draft to promote",
        )
    try:
        with bundle_lock(bundle_root):
            return _promote_locked(bundle_root, draft_name, request)
    except BundleLockHeldError as exc:
        return _refusal(IssueCode.BUNDLE_LOCK_HELD, str(exc))
    except MissingBlobError as exc:
        # The backstop for a blob that disappears mid-promotion. `_derive` catches the ordinary
        # case, where the blob was already gone when the draft's identity was computed; this covers
        # every later computation, and it exists because the store is shared and takes no lock —
        # `add-evidence` and a hand-edit both reach it while this command is running. Without it a
        # `MissingBlobError` escapes `promote` as an exception, which is the shape §21 has no exit
        # code for.
        return _refusal(
            IssueCode.MISSING_BLOB,
            f"blob sha256:{exc.bare_digest} left this bundle while the promotion was running, so "
            "the revision's identity could not be computed and nothing was promoted",
            path=EVIDENCE_PATH.as_posix(),
        )
    except BundleIoError as exc:
        return _refusal(IssueCode.IO_ERROR, str(exc))
    except OSError as exc:
        return _refusal(
            IssueCode.IO_ERROR, f"the promotion could not complete: {io_reason(exc)}"
        )


def _promote_locked(
    bundle_root: Path, name: str, request: PromotionRequest
) -> OperationOutcome[SelectedRevision]:
    """Steps 2-8, under the lock."""
    prepared = _prepare(bundle_root, name, request)
    if isinstance(prepared, OperationOutcome):
        return prepared
    return _commit(bundle_root, prepared)


# --------------------------------------------------------------------------------------
# Steps 2-4: what is promoted, and whether it may be
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Prepared:
    """Everything steps 5-8 need, with every refusal already made."""

    bundle_root: Path
    draft_dir: Path
    manifest: RevisionManifest
    documents: BundleDocuments
    parent: ParentSnapshot | None
    blobs: FilesystemBlobReader
    revision: int
    bundle_digest: str
    findings: tuple[Diagnostic, ...]


def _prepare(
    bundle_root: Path, name: str, request: PromotionRequest
) -> _Prepared | OperationOutcome[SelectedRevision]:
    try:
        selection = _selected_or_none(bundle_root)
    except SelectionError as exc:
        return _refusal(exc.code, str(exc))

    draft_dir = draft_root(bundle_root, name)
    if draft_dir.is_symlink():
        # Before `is_dir()`, which follows the link and answers for its target. Nothing else covers
        # this one path: `require_confined_root` checks the root's own members, so it reaches
        # `drafts` and not `drafts/<name>`, and `discover_source_files` refuses links it walks
        # *past* rather than the tree's own root. That leaves the directory whose bytes become an
        # immutable revision as the one path with no rule, while `inventory` already classifies a
        # symlinked draft as a stray artefact and leaves it out of the drafts it reports — so
        # promoting one installs a revision from a directory no other command calls a draft.
        return _refusal(
            IssueCode.SYMLINK_REFUSED,
            f"drafts/{name} is a symlink; a bundle is self-contained under one root, so the "
            "content a revision is computed from must be inside it",
            path=f"drafts/{name}",
        )
    if not draft_dir.is_dir():
        return _refusal(
            IssueCode.DRAFT_NOT_FOUND, f"drafts/{name} does not exist; there is nothing to promote"
        )
    try:
        draft = load_documents(draft_dir, mode="draft")
    except ProfileBundleError as exc:
        return outcome_with(None, parse_error_diagnostics(exc))
    draft_manifest = draft.manifest
    if not isinstance(draft_manifest, DraftManifest):
        return _refusal(
            IssueCode.DRAFT_MANIFEST_INVALID,
            f"drafts/{name} holds a revision manifest; only a draft can be promoted",
        )

    # Step 2. One comparison covers all four ways a parent can be wrong — moved, gone, appeared
    # under a parentless draft, or never this bundle's at all — because "which revision is this a
    # draft of" has exactly one right answer and `CURRENT` is it.
    selected_digest = None if selection is None else selection.bundle_digest
    if draft_manifest.parent_bundle_digest != selected_digest:
        return _refusal(
            IssueCode.STALE_DRAFT_PARENT,
            f"drafts/{name} was checked out of "
            f"{draft_manifest.parent_bundle_digest or 'no revision'} but this bundle now selects "
            f"{selected_digest or 'no revision'}; rebase-draft moves it onto the current one and "
            "nothing about the draft was changed",
        )

    blobs = FilesystemBlobReader(blobs_dir(bundle_root))
    parent: ParentSnapshot | None = None
    parent_findings: tuple[Diagnostic, ...] = ()
    if selection is not None:
        resolved = _parent(selection)
        if isinstance(resolved, OperationOutcome):
            return resolved
        parent, parent_findings = resolved

    ledger_findings = _ledgers_extend_the_parent(
        draft, None if parent is None else parent.documents
    )
    if ledger_findings:
        return outcome_with(None, ledger_findings)

    derived = _derive(bundle_root, request, draft, parent, blobs)
    if isinstance(derived, OperationOutcome):
        return derived
    manifest, documents = derived
    return _Prepared(
        bundle_root=bundle_root,
        draft_dir=draft_dir,
        manifest=manifest,
        documents=documents,
        parent=parent,
        blobs=blobs,
        revision=manifest.revision,
        bundle_digest=manifest.bundle_digest,
        findings=parent_findings,
    )


def _selected_or_none(bundle_root: Path) -> SelectedRevision | None:
    """The selected revision, or `None` for a bundle that has never been promoted.

    `read_current_once` is the one pointer read (and the one confinement check), so promotion enters
    through it like every other command. Only "there is no `CURRENT`" becomes `None`: every other
    selection failure is a bundle whose selected revision cannot be resolved, and promoting a second
    revision 1 over it would replace history rather than extend it.
    """
    try:
        return read_current_once(bundle_root)
    except SelectionError as exc:
        if exc.code is IssueCode.NO_CURRENT_REVISION:
            # Confinement is not rechecked here: `read_current_once` runs it before it looks for
            # the pointer at all, so reaching this arm already means the root is confined.
            return None
        raise


def _parent(
    selection: SelectedRevision,
) -> tuple[ParentSnapshot, tuple[Diagnostic, ...]] | OperationOutcome[SelectedRevision]:
    """Step 4's parent half: the snapshot, plus whatever the parent's own state costs.

    §6 admits exactly one exception to validating the parent, and this is where it is taken. A
    parent whose documents parse but whose referenced blob is missing or fails its digest keeps its
    quarantine reported and skips only the recomputation that needs those bytes — which is the whole
    point of the recovery path, since the owner's next act is to recapture the evidence into a new
    blob and promote the replacement. Everything else about the parent still blocks: documents that
    will not parse, a schema this build does not support, a manifest that disagrees with the
    directory naming it, and a mutated document that no longer produces the parent's own digest.

    "Skips only the recomputation that needs those bytes" is literal: the digest is recomputed with
    the quarantined blobs' declared digests standing in for their leaves, which is exactly the value
    an intact blob would have contributed and nothing more. Skipping the whole comparison instead
    would leave every parent document a ledger prefix does not cover — the manifest, the policy
    catalogs, every entity file — free to be edited under cover of one broken blob, and the child
    would then cement a `parent_bundle_digest` naming a directory that no longer produces it.

    The quarantine is reported as a warning rather than under its declared blocker tier. The tier is
    a statement about *this* operation: a blocker would refuse the promotion, and refusing it would
    leave an owner with a bundle no supported command can repair. `checkout` reports the identical
    condition as a blocker because there the result is the unusable thing.
    """
    try:
        documents = selected_documents(selection)
    except SelectionError as exc:
        return _refusal(exc.code, str(exc))
    except ProfileBundleError as exc:
        return outcome_with(None, parse_error_diagnostics(exc))
    manifest = documents.manifest
    # `selected_documents` refuses a draft manifest in a selected revision, so this narrowing is a
    # type assertion rather than a check with an outcome of its own.
    assert isinstance(manifest, RevisionManifest)

    try:
        referenced = referenced_blob_digests(documents)
    except CanonicalizationError as exc:
        return _refusal(
            IssueCode.MISSING_REQUIRED_FILE,
            f"the parent revision's evidence set could not be read: {exc}",
        )
    try:
        quarantined = quarantined_blobs(selection.bundle_root, referenced)
    except BundleIoError:
        # Caught here rather than at `promote`'s outer arm, and deliberately not interpolated, for
        # `validation/completeness.py`'s reason: `BundleIoError` is built from `str(OSError)`, which
        # appends the absolute path it failed on, and every rendering emits `message` verbatim — so
        # stringifying it would put a `$HOME` path in a report an operator pastes elsewhere.
        # Recovering the logical file from that message would mean parsing it, which this package
        # refuses to do anywhere; the fault is named by its logical path instead.
        return _refusal(
            IssueCode.IO_ERROR,
            "the parent revision's blob store could not be read, so nothing about its evidence "
            "could be established and nothing was promoted",
            path=EVIDENCE_PATH.as_posix(),
        )
    findings = tuple(
        diagnostic(
            IssueCode.CORRUPT_BLOB_QUARANTINE,
            f"the parent revision's blob sha256:{declared} is quarantined ({reason.value}); its "
            "blob integrity was not rechecked and nothing was moved or deleted, so a replacement "
            "revision that recaptures the evidence can still be promoted",
            path=EVIDENCE_PATH.as_posix(),
            tier="warning",
            reason=reason.value,
            blob=declared,
        )
        for declared, reason in quarantined
    )
    computed = bundle_digest(
        documents,
        FilesystemBlobReader(blobs_dir(selection.bundle_root)),
        quarantined=frozenset(declared for declared, _ in quarantined),
    )
    if computed != manifest.bundle_digest:
        return _refusal(
            IssueCode.BUNDLE_DIGEST_MISMATCH,
            "the selected revision's documents no longer produce the digest its manifest "
            "carries, so it cannot be the parent of a new revision",
        )
    return (
        ParentSnapshot(
            root=selection.root,
            documents=documents,
            envelope=manifest.envelope,
            index=build_index(documents),
        ),
        findings,
    )



def _ledgers_extend_the_parent(
    draft: BundleDocuments, parent: BundleDocuments | None
) -> tuple[Diagnostic, ...]:
    """§6 step 4 and §17: the parent's ledgers must survive into the draft untouched.

    The three are not checked alike, because promotion does not treat them alike. `history/` is
    derived: promotion itself appends the one change record and the one approval stamp, so a draft
    that already carries an extra entry is authoring history rather than proposing content, and the
    two ledgers must be *exactly* the parent's. `conflicts/rulings.yaml` is ordinary owner content
    that a draft may legitimately add to, so only the prefix is required.

    A first promotion has no parent, and the same comparison against no entries is the rule there
    rather than an absence of one: revision 1 inherits nothing, so its draft must carry nothing in
    `history/` for promotion to append the first change record and the first stamp to. Running this
    only for a parented draft left the models' own validators as the first thing to see a
    pre-authored entry, and they raise where §21 has no exit code for an exception.

    Comparison is by `record_digest`, the same canonical form every other prefix check in the
    package uses, so "unchanged" means the same thing here as it does in `validate_history`.
    """
    findings: list[Diagnostic] = []
    for path, appendable in (
        (CHANGE_LEDGER_PATH, False),
        (APPROVAL_LEDGER_PATH, False),
        (PurePosixPath("conflicts/rulings.yaml"), True),
    ):
        ours = _ledger_entries(draft, path)
        theirs: tuple[str, ...] | None = () if parent is None else _ledger_entries(parent, path)
        if ours is None or theirs is None:
            # A missing declared file is `validate_structural`'s finding, reported against the
            # staged tree with every other structural fault rather than as a prefix failure here.
            continue
        if ours[: len(theirs)] != theirs or (not appendable and len(ours) != len(theirs)):
            inherited = "empty" if parent is None else "the parent revision's entries"
            findings.append(
                diagnostic(
                    IssueCode.LEDGER_PREFIX_CHANGED,
                    f"the draft's {path} must be {inherited}"
                    f"{' followed by its own additions' if appendable else ''}; these ledgers are "
                    "append-only and promotion is what appends to them",
                    path=path.as_posix(),
                )
            )
    return tuple(findings)


def _ledger_entries(
    documents: BundleDocuments, path: PurePosixPath
) -> tuple[str, ...] | None:
    document = documents.by_path.get(path)
    if isinstance(document, ChangeLedger):
        return tuple(record_digest(entry) for entry in document.changes)
    if isinstance(document, ApprovalLedger):
        return tuple(record_digest(entry) for entry in document.approvals)
    if document is None:
        return None
    rulings = getattr(document, "rulings", None)
    if rulings is None:  # pragma: no cover - the path decides the model, and it is a ruling ledger
        return None
    return tuple(record_digest(entry) for entry in rulings)


# --------------------------------------------------------------------------------------
# Step 4's derivation, in the order the digests depend on each other
# --------------------------------------------------------------------------------------


def _derive(
    bundle_root: Path,
    request: PromotionRequest,
    draft: BundleDocuments,
    parent: ParentSnapshot | None,
    blobs: FilesystemBlobReader,
) -> tuple[RevisionManifest, BundleDocuments] | OperationOutcome[SelectedRevision]:
    """The promoted tree, in the one order its digests admit.

    The order is forced and it is the same order `tests/profile_bundle/conftest.py` reproduces:

    1. The **candidate digest** comes from the draft as the owner approved it — before any promotion
       document exists, because §7's candidate view omits `history/approvals.yaml` entirely and
       keeps `history/changes.yaml` only through the parent's prefix.
    2. The **approval stamp** is found by that digest, so a stamp can only be for content that was
       actually approved.
    3. The **change record** is appended, deriving `authorized_by` from the stamp rather than
       trusting the request.
    4. The **bundle digest** is computed last, over the tree that now includes both.

    Running these in any other order produces a revision whose approval binds bytes the owner never
    saw, which is precisely what `_the_candidate_view_recomputes_its_approved_digest` exists to
    catch afterwards.
    """
    envelope = None if parent is None else parent.envelope
    try:
        candidate = candidate_content_digest(draft, blobs, envelope)
        evidence_digest = evidence_set_digest(draft, blobs)
    except MissingBlobError as exc:
        return outcome_with(
            None,
            (
                diagnostic(
                    IssueCode.MISSING_BLOB,
                    f"blob sha256:{exc.bare_digest} is not in this bundle, so the draft's identity "
                    "cannot be computed; restore or recapture it before promoting",
                    path=EVIDENCE_PATH.as_posix(),
                    blob=exc.bare_digest,
                ),
            ),
        )
    except CanonicalizationError as exc:
        return _refusal(
            IssueCode.MISSING_REQUIRED_FILE,
            f"{exc}; the draft's identity was not computed, so nothing was promoted",
            path=EVIDENCE_PATH.as_posix(),
        )

    stamp = _approval_stamp(bundle_root, candidate)
    if isinstance(stamp, Diagnostic):
        return outcome_with(None, (stamp,))

    revision = 1 if parent is None else parent.envelope.revision + 1
    parent_digest = None if parent is None else parent.envelope.bundle_digest
    try:
        changed = (
            tuple(sorted(record_contents(draft)))
            if parent is None
            else tuple(sorted(diff_records(parent.documents, draft).touched))
        )
    except RecordIdCollision as exc:
        # `diff_records` raises rather than reports, so this cannot be left to the staged tree's
        # `validate_referential`, which would never run. Same condition, same code, reported here
        # only because the derivation cannot proceed past it.
        return outcome_with(
            None,
            tuple(
                diagnostic(
                    IssueCode.DUPLICATE_RECORD_ID,
                    f"{collision.record_id} is defined in both {collision.first_path} and "
                    f"{collision.second_path}; the promotion's changed-record list cannot name "
                    "which of two records with one ID changed",
                    path=collision.second_path.as_posix(),
                    record_id=collision.record_id,
                    first_path=collision.first_path.as_posix(),
                )
                for collision in exc.collisions
            ),
        )

    change = _change_record(request, revision, parent_digest, changed)
    if isinstance(change, Diagnostic):
        return outcome_with(None, (change,))

    ledgers = _appended_ledgers(draft, change, stamp)
    if isinstance(ledgers, Diagnostic):
        return outcome_with(None, (ledgers,))

    values: dict[str, object] = draft.manifest.model_dump(mode="json")
    values.pop("draft_of_revision", None)
    values.update(
        {
            "state": "revision",
            "revision": revision,
            "parent_bundle_digest": parent_digest,
            "created_at": request.created_at,
            "created_by": request.actor,
            "change_id": change.change_id,
            "approved_candidate_digest": candidate,
            "approval_stamp_id": stamp.approval_stamp_id,
            # Recomputed rather than carried across: §7 step 3 makes this the one manifest field
            # that is a statement about the documents beside it, and the candidate view the owner
            # approved overwrites the declared value with exactly this one. Promoting the draft's
            # declared copy would promote a field the owner's approval did not cover.
            "evidence_set_digest": evidence_digest,
            "bundle_digest": _PENDING_DIGEST,
        }
    )

    by_path = {**draft.by_path, **ledgers}
    provisional = RevisionManifest.model_validate(values)
    digest = bundle_digest(BundleDocuments(manifest=provisional, by_path=by_path), blobs)
    values["bundle_digest"] = digest
    manifest = RevisionManifest.model_validate(values)
    return manifest, BundleDocuments(manifest=manifest, by_path=by_path)


def _change_record(
    request: PromotionRequest,
    revision: int,
    parent_digest: str | None,
    changed: tuple[str, ...],
) -> ChangeRecord | Diagnostic:
    """The one change record this promotion appends, or why the request cannot produce one.

    `PromotionRequest` is a plain dataclass, so this is the first thing that sees what the operator
    typed: a blank or whitespace-only summary and a `created_at` with no UTC offset are both refused
    here, by `ChangeRecord`'s own field types rather than by a second copy of their rules. Left
    uncaught they leave a function typed `-> OperationOutcome[...]` as a `ValidationError`, and §21
    has no exit code for that.
    """
    try:
        return ChangeRecord.model_validate(
            {
                "change_id": f"change.{revision:06d}",
                "revision": revision,
                "parent_bundle_digest": parent_digest,
                "actor": request.actor,
                # §17: derived from the matching approval stamp, never trusted from the request.
                # The stamp was found under the candidate digest and its `approved_via` is a
                # controlling terminal, so the authority behind this revision is the owner's
                # whoever ran the command.
                "authorized_by": Actor.OWNER,
                "summary": request.summary,
                "changed_record_ids": changed,
                "created_at": request.created_at,
            }
        )
    except ValueError as exc:
        return diagnostic(
            IssueCode.MODEL_VALIDATION_ERROR,
            f"this promotion's change record is not a valid one: {exc}",
            path=CHANGE_LEDGER_PATH.as_posix(),
        )


def _approval_stamp(bundle_root: Path, candidate: str) -> ApprovalStamp | Diagnostic:
    """The owner's stamp for exactly this candidate digest (§13, §19, §21).

    Keyed by the digest rather than by the draft's name, so the lookup itself is the binding: a
    draft edited after approval has a different candidate digest and simply has no stamp, which is
    `missing_approval_stamp` and the owner's cue to approve the content they now have.

    The file holds exactly what `approvals.approval_stamp_bytes` emits, which is where that form is
    defined; nothing about it is restated here. A stamp whose recorded digest disagrees with
    the name it is filed under is `stale_approval_stamp`: the check can only fire for a file that
    was copied or hand-edited, and that is exactly the case where trusting the filename would let
    one approval authorise different content.
    """
    path = approval_path(bundle_root, candidate)
    logical = PurePosixPath(f"approvals/{path.name}")
    if not path.is_file():
        return diagnostic(
            IssueCode.MISSING_APPROVAL_STAMP,
            f"no owner approval is recorded for candidate digest {candidate}; run "
            "profile-bundle approve for this exact digest before promoting",
            path=logical.as_posix(),
            candidate_content_digest=candidate,
        )
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return diagnostic(
            IssueCode.IO_ERROR,
            f"{logical} could not be read: {io_reason(exc)}",
            path=logical.as_posix(),
        )
    try:
        stamp = ApprovalStamp.model_validate(load_yaml_bytes(raw, logical_path=logical))
    except RestrictedYamlError as exc:
        return diagnostic(exc.code, str(exc), path=logical.as_posix())
    except ValueError as exc:
        return diagnostic(
            IssueCode.MODEL_VALIDATION_ERROR,
            f"{logical} is not a readable approval stamp: {exc}",
            path=logical.as_posix(),
        )
    if stamp.candidate_content_digest != candidate:
        return diagnostic(
            IssueCode.STALE_APPROVAL_STAMP,
            f"{logical} approves {stamp.candidate_content_digest}, not the {candidate} its name "
            "claims; an approval binds content, so the two cannot differ",
            path=logical.as_posix(),
            record_id=stamp.approval_stamp_id,
            candidate_content_digest=candidate,
        )
    return stamp


def _appended_ledgers(
    draft: BundleDocuments, change: ChangeRecord, stamp: ApprovalStamp
) -> dict[PurePosixPath, DocumentModel] | Diagnostic:
    """The two history documents with exactly one entry appended to each (§17).

    The append is where the two ledgers' own rules are enforced — contiguous revisions, one stamp
    ID used once — and they are enforced by constructing the models rather than by restating them
    here, so a rule added to either ledger is inherited instead of drifting. What this owes is the
    translation: `ApprovalLedger` refuses a stamp ID the parent's ledger already holds, and that is
    an ordinary thing for the tool that filed the stamp to have chosen, not an internal error.
    """
    changes = draft.by_path.get(CHANGE_LEDGER_PATH)
    approvals = draft.by_path.get(APPROVAL_LEDGER_PATH)
    if not isinstance(changes, ChangeLedger) or not isinstance(approvals, ApprovalLedger):
        return diagnostic(
            IssueCode.MISSING_REQUIRED_FILE,
            "the draft has no change or approval ledger to append this promotion to; restore the "
            "documents under history/ before promoting",
            path="history",
        )
    try:
        return {
            CHANGE_LEDGER_PATH: ChangeLedger(changes=(*changes.changes, change)),
            APPROVAL_LEDGER_PATH: ApprovalLedger(approvals=(*approvals.approvals, stamp)),
        }
    except ValueError as exc:
        return diagnostic(
            IssueCode.MODEL_VALIDATION_ERROR,
            f"this promotion's change record and approval stamp do not extend the draft's history/ "
            f"ledgers: {exc}",
            path="history",
        )


# --------------------------------------------------------------------------------------
# Steps 5-8: the writes, in the one order a crash is survivable in
# --------------------------------------------------------------------------------------


def _commit(
    bundle_root: Path, prepared: _Prepared
) -> OperationOutcome[SelectedRevision]:
    staging = Path(
        tempfile.mkdtemp(dir=_revisions(bundle_root), prefix=PROMOTION_TEMP_PREFIX)
    )
    staged = staging / digest_token(prepared.bundle_digest)
    keep_staging = False
    try:
        _write_revision(staged, prepared)  # step 5

        reread = _reread(staged, prepared)  # step 6
        if isinstance(reread, OperationOutcome):
            return reread

        # Step 6's last act. `COMPLETE` is what a reader requires before trusting the tree, so it is
        # written only once every document beside it has been written, closed and read back.
        _write_file(complete_marker_path(staged), f"{prepared.bundle_digest}\n".encode())
        marker = _marker_agrees(staged, prepared.bundle_digest)
        if marker is not None:
            return outcome_with(None, (marker,))

        target = revision_root(bundle_root, prepared.bundle_digest)
        conflict = _install(staged, target)  # step 7
        if conflict is not None:
            keep_staging = True  # both directories are retained; `CURRENT` is untouched
            return outcome_with(None, (conflict,))

        _replace_pointer(bundle_root, prepared)  # step 8
    finally:
        if not keep_staging:
            # This command's own staging directory, created under `PROMOTION_TEMP_PREFIX` in this
            # operation and never renamed anywhere else. On the success path it is an empty
            # directory whose one child has been renamed out of it; on a refusal it holds only
            # bytes this command wrote and nothing else refers to.
            shutil.rmtree(staging, ignore_errors=True)

    return _select(bundle_root, prepared)


def _write_revision(staged: Path, prepared: _Prepared) -> None:
    """Step 5: the whole revision, into a directory beside its destination.

    Every document the draft already holds is copied byte for byte; the three promotion derives are
    emitted through `document_bytes`, the one writer whose output this bundle's loader is known to
    read back unchanged.
    """
    staged.mkdir(parents=True)
    for logical in ENTITY_DOCUMENT_DIRECTORIES:
        (staged / logical).mkdir(parents=True, exist_ok=True)
    for source in discover_source_files(prepared.draft_dir, final_revision=False):
        if source.kind is DocumentKind.MANIFEST or source.logical_path in _DERIVED_DOCUMENTS:
            continue
        _write_file(staged / source.logical_path, source.abspath.read_bytes())
    _emit(staged, MANIFEST_PATH, prepared.manifest)
    for logical in sorted(_DERIVED_DOCUMENTS - {MANIFEST_PATH}, key=str):
        _emit(staged, logical, prepared.documents.by_path[logical])


def _reread(
    staged: Path, prepared: _Prepared
) -> None | OperationOutcome[SelectedRevision]:
    """Step 6: read the whole staged tree back from disk and validate what is actually there.

    Two claims, and the writer's own report is evidence for neither.

    The tree must **produce the digest that is about to name it**, recomputed from the bytes that
    landed — which also covers the blob bytes, since a blob leaf is part of that digest and the
    store takes no lock.

    The tree must **validate**, through the same `validate_bundle` a reader runs, with the parent
    handed over rather than rediscovered. Only `_DEFERRED_TO_A_LATER_STEP` is tolerated, and both of
    its members are re-asserted after the artefact they are about exists.

    The tier filter passes over `information` as well, which is three codes and not a third silent
    deferral. `completeness_counts` and `orphaned_artefact` are reports about a bundle rather than
    faults in this tree. The third, `candidate_digest_unverified`, is §20.6's "I made no claim", and
    it cannot arise here: it is emitted when the candidate view could not be recomputed, whose three
    causes are a missing blob — which the digest recomputation above raises on before validation
    runs — a final `change_id` that does not match the manifest, which this promotion derived
    together, and an ancestor that could not be read, which is why the parent is handed over.
    Listing it in `_DEFERRED_TO_A_LATER_STEP` would be a tolerance for something that cannot happen.

    There is deliberately no third check comparing the re-read models with the ones the derivation
    produced (D-115). The digest is computed *from* those models, so any difference between them
    changes it — except in the two manifest fields the leaf excludes, `bundle_digest` (blanked) and
    `evidence_set_digest` (overwritten), and those are exactly what `validate_digest`'s own two
    comparisons exist for. A model-by-model comparison could therefore never be the check that
    refused anything, and shipping it would read as coverage;
    `test_profile_bundle_promotion.py` names where each half actually lands.
    """
    try:
        documents = load_documents(staged, mode="revision")
    except ProfileBundleError as exc:
        return outcome_with(None, parse_error_diagnostics(exc))
    computed = bundle_digest(documents, prepared.blobs)
    if computed != prepared.bundle_digest:
        return _refusal(
            IssueCode.INTERNAL_ERROR,
            "the staged revision's bytes on disk produce a different digest than the one the "
            "promotion computed, so it was discarded rather than installed",
        )
    checked = validate_bundle(
        staged,
        bundle_root=prepared.bundle_root,
        mode="revision",
        parent=prepared.parent,
    )
    blocking = tuple(
        finding
        for finding in checked.diagnostics
        if finding.tier in ("error", "blocker") and finding.code not in _DEFERRED_TO_A_LATER_STEP
    )
    if blocking:
        return outcome_with(None, blocking)
    return None


def _marker_agrees(staged: Path, digest: str) -> Diagnostic | None:
    """The deferred half of §20.6's marker clause, asserted where the marker now exists."""
    try:
        marker = read_complete(staged)
    except PointerError as exc:
        return diagnostic(IssueCode.COMPLETE_MARKER_MISSING, str(exc), path="COMPLETE")
    if marker != digest:
        return diagnostic(
            IssueCode.INTERNAL_ERROR,
            f"the staged revision's COMPLETE names {marker}, not the {digest} it was written for",
            path="COMPLETE",
        )
    return None


def _install(staged: Path, target: Path) -> Diagnostic | None:
    """Step 7: rename the complete tree to its digest name, or reuse an exact existing one.

    A target already in place is a torn earlier attempt at the same content — digest names are
    content, so nothing else can be there. It is reused only when it holds exactly these bytes,
    marker included, and any difference retains both directories and leaves `CURRENT` alone. §21
    forbids deleting either one, and there is nothing to choose between them anyway: this attempt
    cannot say which of two disagreeing trees the owner meant.

    "Already in place" is `exists() or is_symlink()`, because `exists()` follows a link and answers
    `False` for a dangling one. Renaming onto that path fails inside the `os.rename`, which unwinds
    through `_commit`'s `finally` and removes the staged tree — the one refusal that discarded it,
    reported as an I/O failure rather than as the conflict it is.
    """
    if not (target.exists() or target.is_symlink()):
        os.rename(staged, target)
        return None
    try:
        read_complete(target)
    except PointerError as exc:
        return _target_conflict(target, TargetConflictReason.MARKER_MISSING, str(exc))
    if not identical_trees(staged, target):
        return _target_conflict(
            target,
            TargetConflictReason.CONTENT_DIFFERS,
            "it does not hold this revision byte for byte",
        )
    return None


def _target_conflict(target: Path, reason: TargetConflictReason, why: str) -> Diagnostic:
    return diagnostic(
        IssueCode.PROMOTION_TARGET_CONFLICT,
        f"revisions/{target.name} already exists and {why}; both directories were retained and "
        "CURRENT was not changed",
        path=f"revisions/{target.name}",
        reason=reason.value,
    )


def _replace_pointer(bundle_root: Path, prepared: _Prepared) -> None:
    """Step 8: the commit point.

    The staged pointer is written, flushed and closed before `os.replace` runs, so a reader either
    sees the previous pointer or this one — never a half-written file. `os.replace` is used rather
    than `os.rename` because the destination normally exists, and rather than unlink-then-write
    because a `CURRENT` that is briefly absent is a bundle that briefly has no selected revision.
    """
    pointer = CurrentPointer(bundle_digest=prepared.bundle_digest, revision=prepared.revision)
    handle, temporary = tempfile.mkstemp(dir=bundle_root, prefix=CURRENT_TEMP_PREFIX)
    os.close(handle)
    staged = Path(temporary)
    try:
        _write_file(staged, current_pointer_bytes(pointer))
        os.replace(staged, current_path(bundle_root))
    except BaseException:
        staged.unlink(missing_ok=True)
        raise


def _select(
    bundle_root: Path, prepared: _Prepared
) -> OperationOutcome[SelectedRevision]:
    """Resolve the new selection the way a reader will, after the pointer has been replaced.

    This is the deferred pointer clause, asserted where it lands, and it is deliberately a full
    `read_current_once` rather than a comparison against what was just written: it re-reads the
    file, re-derives the directory from it and requires that directory's `COMPLETE` to agree, which
    is exactly the sequence every later command performs.
    """
    try:
        selection = read_current_once(bundle_root)
    except SelectionError as exc:
        return _refusal(exc.code, str(exc))
    if selection.bundle_digest != prepared.bundle_digest or selection.revision != prepared.revision:
        return _refusal(
            IssueCode.CURRENT_POINTER_MISMATCH,
            "CURRENT does not select the revision this promotion wrote",
        )
    return outcome_with(selection, prepared.findings)


# --------------------------------------------------------------------------------------
# Filesystem
# --------------------------------------------------------------------------------------


def _write_file(path: Path, data: bytes) -> None:
    """The one write in this module: create, write, flush, close.

    Every file promotion produces goes through here so that "each file is flushed and closed before
    the tree is re-read" is a property of one function rather than of every call site. The flush is
    explicit although closing the handle implies it — the sequence §6 states is the sequence that is
    written, and neither one is a durability claim: they make the bytes visible to other processes,
    which is all a process-crash contract needs.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        stream.write(data)
        stream.flush()


def _emit(staged: Path, logical: PurePosixPath, document: DocumentModel) -> None:
    _write_file(staged / logical, document_bytes(document.model_dump(mode="json"),
                                                 logical_path=logical))


def _revisions(bundle_root: Path) -> Path:
    directory = revisions_dir(bundle_root)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _refusal(
    code: IssueCode, message: str, *, path: str | None = None
) -> OperationOutcome[SelectedRevision]:
    return outcome_with(None, (diagnostic(code, message, path=path),))


__all__ = [
    "CURRENT_TEMP_PREFIX",
    "PROMOTION_TEMP_PREFIX",
    "PromotionRequest",
    "TargetConflictReason",
    "promote",
]
