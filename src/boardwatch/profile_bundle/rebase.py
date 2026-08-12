"""Move a draft onto the selected revision, or refuse having written nothing (design §6, §21).

A draft is checked out of one revision and edited while the world moves on. `rebase-draft` is how it
catches up, and the whole value of the command is in what it does when it *cannot*.

## The order of operations is the contract

1. Take the bundle's exclusive writer lock, **non-blocking**, before anything else — including
   before rereading `CURRENT`. Reading the pointer first would mean deciding what to rebase onto
   using a value a promotion could replace while this command was still deciding.
2. Refuse, without writing, on: an occupied backup path that does not hold this exact draft, a
   record both sides touched, a document one side deleted and the other changed, one ID claimed by
   two records, an unreadable old parent, or an evidence blob whose bytes are gone.
3. Build the rebased tree in a same-filesystem temporary directory and **reread it from disk**.
4. Rename the old draft to its deterministic backup, then rename the rebased tree into place.

Steps 1-3 write only inside a temporary directory that is removed on every failure path, which is
what makes "no writes" literal rather than approximate.

## Why the backup is checked before the merge is attempted

Both refusals are exit 1 and both write nothing, so the order is a judgement call, and this one is
made in the operator's favour: an occupied backup path blocks the rebase no matter how the merge
would have gone, and it is the one thing they must physically move. Reporting a record conflict
first would hand them a merge to resolve and then refuse again for a reason they could have fixed
in the same breath.

## Crash consistency, and the deliberate absence of a rollback

Between the two renames in step 4 the draft name is momentarily absent and the backup holds the
original. That window is the design's: §21 promises the original *or* the exact backup survives,
not that the draft name is never empty. There is deliberately no compensating rename on failure —
a process that is killed cannot run compensation, so a rollback would give an exception and a
`SIGKILL` two different recovery shapes, and the operator would have to know which one happened.
One shape: look in `drafts/<name>.pre-rebase-<parent>/`.

## What "validate before installing" means here

The rebased tree is read back through the production loader and compared, document by document, to
the models the merge produced. That is a second path to the same answer: the writer's own claim to
have written the right bytes is not evidence. It deliberately stops there and does not gate on
structural validation — a draft is a work in progress and may legitimately be incomplete (an `init`
draft has no `facts/identity.yaml` at all), so refusing to rebase it would strand the owner on a
parent that keeps moving.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath

from boardwatch.profile_bundle.canonical import (
    EVIDENCE_PATH,
    MANIFEST_PATH,
    FilesystemBlobReader,
    MissingBlobError,
    evidence_set_digest,
)
from boardwatch.profile_bundle.diff import (
    NO_BASE,
    DocumentMergeConflict,
    RecordIdCollision,
    diff_records,
    is_append_only,
    merge_document,
    merge_values,
    record_contents,
)
from boardwatch.profile_bundle.drafts import DRAFT_TEMP_PREFIX, DraftHandle
from boardwatch.profile_bundle.errors import (
    BundleIoError,
    BundlePathError,
    Diagnostic,
    IssueCode,
    OperationOutcome,
    ProfileBundleError,
    diagnostic,
    outcome_with,
)
from boardwatch.profile_bundle.index import record_ids_in_document
from boardwatch.profile_bundle.layout import ENTITY_DOCUMENT_DIRECTORIES
from boardwatch.profile_bundle.locking import BundleLockHeldError, bundle_lock
from boardwatch.profile_bundle.models.documents import BundleDocuments, DocumentModel
from boardwatch.profile_bundle.models.manifests import DraftManifest, RevisionManifest
from boardwatch.profile_bundle.paths import (
    blobs_dir,
    draft_root,
    drafts_dir,
    rebase_backup_root,
    require_draft_segment,
    revision_root,
)
from boardwatch.profile_bundle.storage import (
    SelectedRevision,
    SelectionError,
    identical_trees,
    read_current_once,
    selected_documents,
)
from boardwatch.profile_bundle.validation.context import load_documents, parse_error_diagnostics
from boardwatch.profile_bundle.yaml_writer import document_bytes

#: Manifest fields the rebase carries across by three-way merge. Derived from the two models rather
#: than listed, so a field added to the shared envelope is merged instead of silently dropped: it is
#: everything a draft and a revision both declare, minus everything this module assigns itself.
_DERIVED_MANIFEST_FIELDS: frozenset[str] = frozenset(
    {
        "state",
        "draft_of_revision",
        "parent_bundle_digest",
        "bundle_digest",
        "approved_candidate_digest",
        "approval_stamp_id",
        "change_id",
        "evidence_set_digest",
    }
)
_INHERITED_MANIFEST_FIELDS: frozenset[str] = (
    frozenset(DraftManifest.model_fields) & frozenset(RevisionManifest.model_fields)
) - _DERIVED_MANIFEST_FIELDS

#: One logical document's bytes for the staged tree: a file to copy verbatim, or a merged model to
#: emit. Copying is preferred wherever one side's document survives unchanged, for the same reason
#: `checkout` copies — re-emitting rewrites bytes the owner never touched and makes the next diff
#: unreadable.
_Source = Path | DocumentModel


def rebase_draft(bundle_root: Path, *, name: str) -> OperationOutcome[DraftHandle]:
    """Rebase `drafts/<name>` onto the selected revision (§6, §21).

    Returns `clean` when the draft already descends from the selected revision — a rebase with
    nothing to do writes nothing and creates no backup, so running it twice is safe.
    """
    # Confinement first, and outside the lock: a name that could escape `drafts/` would place the
    # backup and the staging tree wherever it liked, and that decision must not be made while
    # holding a lock that makes another writer wait. The segment grammar, because every name
    # `inventory` lists under `drafts/` must be one this command will take — including the backup of
    # a maximum-length draft, which is the only copy of that draft and the one thing an operator
    # would be rebasing after a rebase went wrong.
    draft_name = require_draft_segment(name)
    # Before the lock, because `filelock` creates the lockfile's directory: a mistyped `--bundle`
    # would otherwise leave a new empty directory behind as the only trace of a failed command.
    if not bundle_root.is_dir():
        return _refusal(
            IssueCode.BUNDLE_NOT_FOUND,
            "there is no bundle at the requested path, so there is no revision to rebase onto",
        )
    try:
        with bundle_lock(bundle_root):
            return _rebase_locked(bundle_root, draft_name)
    except BundleLockHeldError as exc:
        return _refusal(IssueCode.BUNDLE_LOCK_HELD, str(exc))
    except BundleIoError as exc:
        return _refusal(IssueCode.IO_ERROR, str(exc))
    except OSError as exc:
        return _refusal(
            IssueCode.IO_ERROR, f"the rebase could not complete: {exc.strerror or exc.__class__}"
        )


def _rebase_locked(bundle_root: Path, name: str) -> OperationOutcome[DraftHandle]:
    try:
        selection = read_current_once(bundle_root)
    except SelectionError as exc:
        return _refusal(exc.code, str(exc))

    draft_dir = draft_root(bundle_root, name)
    if not draft_dir.is_dir():
        return _refusal(
            IssueCode.DRAFT_NOT_FOUND, f"drafts/{name} does not exist; there is nothing to rebase"
        )
    try:
        ours = load_documents(draft_dir, mode="draft")
    except ProfileBundleError as exc:
        return outcome_with(None, parse_error_diagnostics(exc))
    draft_manifest = ours.manifest
    if not isinstance(draft_manifest, DraftManifest):
        return _refusal(
            IssueCode.DRAFT_MANIFEST_INVALID,
            f"drafts/{name} holds a revision manifest; only a draft can be rebased",
        )

    if draft_manifest.parent_bundle_digest == selection.bundle_digest:
        return OperationOutcome.clean(_handle(name, draft_dir, draft_manifest))

    try:
        backup = rebase_backup_root(bundle_root, name, draft_manifest.parent_bundle_digest)
    except BundlePathError:
        # A name that is itself derived — a backup of a backup — has no room left for another
        # suffix inside the per-component limit. Reported rather than raised, because this arrives
        # from `inventory`'s own list and a crash out of a function typed to return an outcome is
        # the shape this project treats as a defect. Copying it to a shorter name is the way out.
        return _refusal(
            IssueCode.DRAFT_BACKUP_CONFLICT,
            f"drafts/{name} is already a derived name, so no backup name can be derived from it "
            "without exceeding the length a single path component may have; copy it to a shorter "
            "name and rebase that",
            path=f"drafts/{name}",
        )
    reuse = backup.exists()
    if reuse and not identical_trees(draft_dir, backup):
        return _refusal(
            IssueCode.DRAFT_BACKUP_CONFLICT,
            f"drafts/{backup.name} already exists and does not hold this draft byte for byte; "
            "move it aside before rebasing, because the backup path is derived and cannot be "
            "renumbered",
            path=f"drafts/{backup.name}",
        )

    base = _base_documents(bundle_root, draft_manifest.parent_bundle_digest)
    if isinstance(base, Diagnostic):
        return outcome_with(None, (base,))
    try:
        theirs = selected_documents(selection)
    except SelectionError as exc:
        return _refusal(exc.code, str(exc))
    except ProfileBundleError as exc:
        return outcome_with(None, parse_error_diagnostics(exc))

    collisions = _collision_diagnostics(base, ours, theirs, name, selection.revision)
    if collisions:
        return outcome_with(None, collisions)

    overlap = _overlapping_records(base, ours, theirs)
    if overlap:
        return _conflict(
            overlap,
            f"{len(overlap)} record(s) were changed both in drafts/{name} and in revision "
            f"{selection.revision}; a rebase never resolves a record conflict for the owner",
        )

    plan = _merge_plan(base, ours, theirs, draft_dir, selection.root)
    if isinstance(plan, Diagnostic):
        return outcome_with(None, (plan,))
    merged, sources = plan

    manifest = _rebased_manifest(base, ours, theirs, selection, merged, bundle_root)
    if isinstance(manifest, Diagnostic):
        return outcome_with(None, (manifest,))

    return _install(bundle_root, draft_dir, backup, reuse, name, manifest, merged, sources)


# --------------------------------------------------------------------------------------
# Reading the three trees
# --------------------------------------------------------------------------------------


def _base_documents(
    bundle_root: Path, parent_digest: str | None
) -> BundleDocuments | None | Diagnostic:
    """The revision the draft was checked out of, or `None` for a parentless draft.

    A parent that is no longer readable is reported as `unverifiable_ancestor` — §21's own name for
    a missing or unreadable ancestor — rather than as a parse failure, because the tree that failed
    to read is not the one the operator asked about.
    """
    if parent_digest is None:
        return None
    root = revision_root(bundle_root, parent_digest)
    if not root.is_dir():
        return diagnostic(
            IssueCode.UNVERIFIABLE_ANCESTOR,
            f"the draft's parent revision {parent_digest} is not in this bundle, so there is no "
            "base to compare the draft against",
        )
    try:
        return load_documents(root, mode="revision")
    except ProfileBundleError as exc:
        return diagnostic(
            IssueCode.UNVERIFIABLE_ANCESTOR,
            f"the draft's parent revision {parent_digest} could not be read: {exc}",
        )


def _collision_diagnostics(
    base: BundleDocuments | None,
    ours: BundleDocuments,
    theirs: BundleDocuments,
    name: str,
    revision: int,
) -> tuple[Diagnostic, ...]:
    """Duplicate record IDs in any of the three trees, attributed to the tree that holds them.

    A rebase deliberately does not validate the draft first (see the module docstring), so a draft
    with two records claiming one ID reaches the merge. Neither the record diff nor the install-time
    reread can catch it: the index answers for the shadowed ID with the *other* record, and the
    reread compares the installed tree against the merge's own output. So it is checked here, by
    tree, before any merge decision is taken.
    """
    findings: list[Diagnostic] = []
    for subject, documents in (
        (f"drafts/{name}", ours),
        (f"revision {revision}", theirs),
        ("the draft's old parent revision", base),
    ):
        if documents is None:
            continue
        try:
            record_contents(documents)
        except RecordIdCollision as exc:
            findings.extend(
                diagnostic(
                    IssueCode.DUPLICATE_RECORD_ID,
                    f"{collision.record_id} is defined in both {collision.first_path} and "
                    f"{collision.second_path} in {subject}; a rebase cannot tell which of two "
                    "records with one ID a change refers to",
                    path=collision.second_path.as_posix(),
                    record_id=collision.record_id,
                    first_path=collision.first_path.as_posix(),
                )
                for collision in exc.collisions
            )
    return tuple(findings)


def _overlapping_records(
    base: BundleDocuments | None, ours: BundleDocuments, theirs: BundleDocuments
) -> tuple[str, ...]:
    """Record IDs both sides touched. Empty means the two edits are independent.

    A parentless draft has no base, so *every* record on each side is an addition and the overlap
    is simply the IDs they share — which is the honest answer: two trees that both introduce
    `skill.x` from nowhere have collided.
    """
    if base is None:
        ours_touched = frozenset(record_contents(ours))
        theirs_touched = frozenset(record_contents(theirs))
    else:
        ours_touched = diff_records(base, ours).touched
        theirs_touched = diff_records(base, theirs).touched
    return tuple(sorted(ours_touched & theirs_touched))


# --------------------------------------------------------------------------------------
# The merge
# --------------------------------------------------------------------------------------


def _merge_plan(
    base: BundleDocuments | None,
    ours: BundleDocuments,
    theirs: BundleDocuments,
    draft_dir: Path,
    revision_dir: Path,
) -> tuple[dict[PurePosixPath, DocumentModel], dict[PurePosixPath, _Source]] | Diagnostic:
    """The merged documents, and where each one's bytes come from.

    `BundleDocuments.by_path` holds every declared file *except* the manifest, which is why nothing
    here filters it out: the manifest is derived rather than merged and reaches the staged tree
    through `_rebased_manifest`.

    A document only one side still has is dropped only when the *other* side left it exactly as the
    base had it. Anything else is a one-sided deletion facing an edit, and it is refused rather than
    resolved by absence — see `_deletion_conflict` for why the record-ID overlap gate cannot see it.

    Taking one side's document whole, rather than merging, is an optimisation for the case where a
    merge could only reproduce it — and it must not fire for an append-only ledger the selected
    revision happens not to have touched. That is the *ordinary* case for `conflicts/rulings.yaml`,
    because a promotion appends a change record and an approval stamp but almost never a ruling; a
    draft that dropped an inherited entry would then install with nothing said, and §17's guarantee
    that the selected revision's entries are the result's prefix would hold only where some
    unrelated edit happened to route the document through `merge_document`. The other short-cut —
    the draft left the document as the base had it, so the revision's copy wins — is safe for the
    same ledgers: the draft appended nothing, so the revision's sequence *is* the result.
    """
    merged: dict[PurePosixPath, DocumentModel] = {}
    sources: dict[PurePosixPath, _Source] = {}
    for logical in sorted(set(ours.by_path) | set(theirs.by_path), key=str):
        inherited = None if base is None else base.by_path.get(logical)
        our_document = ours.by_path.get(logical)
        their_document = theirs.by_path.get(logical)
        if our_document is None:
            # Absent from the draft: a file only the new revision has, or one the owner dropped.
            if inherited is None:
                if their_document is not None:
                    merged[logical] = their_document
                    sources[logical] = revision_dir / logical
                continue
            if their_document is not None and their_document != inherited:
                return _deletion_conflict(
                    logical, their_document, deleted_by="the draft", changed_by="that revision"
                )
            continue
        if their_document is None:
            if inherited is None:
                merged[logical] = our_document
                sources[logical] = draft_dir / logical
                continue
            if our_document != inherited:
                return _deletion_conflict(
                    logical,
                    our_document,
                    deleted_by="the selected revision",
                    changed_by="the draft",
                )
            continue
        if our_document == their_document or (
            inherited is not None
            and their_document == inherited
            and not is_append_only(our_document)
        ):
            merged[logical] = our_document
            sources[logical] = draft_dir / logical
        elif inherited is not None and our_document == inherited:
            merged[logical] = their_document
            sources[logical] = revision_dir / logical
        else:
            try:
                value = merge_document(inherited, our_document, their_document)
            except DocumentMergeConflict as exc:
                return _merge_conflict(logical, exc)
            merged[logical] = value
            sources[logical] = value
    return merged, sources


def _rebased_manifest(
    base: BundleDocuments | None,
    ours: BundleDocuments,
    theirs: BundleDocuments,
    selection: SelectedRevision,
    merged: Mapping[PurePosixPath, DocumentModel],
    bundle_root: Path,
) -> DraftManifest | Diagnostic:
    """The draft manifest, re-parented and with its content-derived fields recomputed.

    `evidence_set_digest` is recomputed rather than merged: it is the one manifest field that is a
    statement about the documents beside it, and carrying either side's copy across a merge of the
    evidence document would make the rebased draft assert an evidence set nobody has.
    """
    inherited = None if base is None else base.manifest
    try:
        fields = {
            name: merge_values(
                name,
                NO_BASE if inherited is None else getattr(inherited, name),
                getattr(ours.manifest, name),
                getattr(theirs.manifest, name),
            )
            for name in sorted(_INHERITED_MANIFEST_FIELDS)
        }
    except DocumentMergeConflict as exc:
        return _merge_conflict(MANIFEST_PATH, exc)

    if EVIDENCE_PATH not in merged:
        # Reachable by a draft the owner deleted the file from: `load_documents` treats a missing
        # declared file as a structural finding rather than a parse failure, so it gets this far.
        return diagnostic(
            IssueCode.MISSING_REQUIRED_FILE,
            f"the rebased draft would have no {EVIDENCE_PATH}, so it cannot state an evidence-set "
            "digest; restore the document in the draft before rebasing",
            path=EVIDENCE_PATH.as_posix(),
        )
    try:
        # The manifest is excluded from the evidence-set digest by §7 step 3 (that is what keeps the
        # digest acyclic), so the one passed here is a placeholder that cannot influence the result.
        digest = evidence_set_digest(
            BundleDocuments(manifest=theirs.manifest, by_path=dict(merged)),
            FilesystemBlobReader(blobs_dir(bundle_root)),
        )
    except MissingBlobError as exc:
        return diagnostic(
            IssueCode.MISSING_BLOB,
            f"blob sha256:{exc.bare_digest} is not in this bundle, so the rebased draft cannot "
            "state an evidence-set digest; restore or recapture it before rebasing",
            blob=exc.bare_digest,
        )

    return DraftManifest.model_validate(
        {
            **fields,
            "state": "draft",
            "draft_of_revision": selection.revision,
            "parent_bundle_digest": selection.bundle_digest,
            "bundle_digest": "",
            "approved_candidate_digest": "",
            "approval_stamp_id": "",
            "change_id": "",
            "evidence_set_digest": digest,
        }
    )


# --------------------------------------------------------------------------------------
# Installation
# --------------------------------------------------------------------------------------


def _install(
    bundle_root: Path,
    draft_dir: Path,
    backup: Path,
    reuse: bool,
    name: str,
    manifest: DraftManifest,
    merged: Mapping[PurePosixPath, DocumentModel],
    sources: Mapping[PurePosixPath, _Source],
) -> OperationOutcome[DraftHandle]:
    staging = Path(tempfile.mkdtemp(dir=drafts_dir(bundle_root), prefix=DRAFT_TEMP_PREFIX))
    installed = False
    try:
        try:
            _write_tree(staging, manifest, sources)
        except ProfileBundleError as exc:
            return _refusal(
                IssueCode.INTERNAL_ERROR, f"the rebased draft could not be written: {exc}"
            )
        try:
            reread = load_documents(staging, mode="draft")
        except ProfileBundleError as exc:
            return outcome_with(None, parse_error_diagnostics(exc))
        # `BundleDocuments` keeps the manifest out of `by_path`, so both halves are compared.
        if reread.manifest != manifest or dict(reread.by_path) != dict(merged):
            return _refusal(
                IssueCode.INTERNAL_ERROR,
                "the rebased draft did not read back as the tree the merge produced, so it was "
                "discarded rather than installed",
            )
        # An exact backup already holds these bytes, so the draft is moved aside and removed after
        # the install. What is renamed and deleted here is the operator's OWN pre-rebase draft: the
        # temporary prefix is applied by this path moments before deleting, and marks nothing about
        # where the directory came from. A deliberate departure from §21's "no command deletes
        # drafts", licensed by one fact only — `identical_trees` proved at `reuse` that these exact
        # bytes are retained at the backup path. Provenance is not the licence; the proof is. The
        # alternative — leaving it — adds a full-size `.tmp-draft-` tree that no command drains and
        # that `inventory` reports forever as an interrupted installation that never happened.
        # `ignore_errors` because the install has already succeeded: a failure here leaves residue
        # that `inventory` reports, and failing the operation would be the worse answer.
        vacated = (
            drafts_dir(bundle_root) / f"{DRAFT_TEMP_PREFIX}{uuid.uuid4().hex}" if reuse else backup
        )
        os.rename(draft_dir, vacated)  # boundary: the backup rename
        os.rename(staging, draft_dir)  # boundary: the rebased install
        installed = True
        if reuse:
            shutil.rmtree(vacated, ignore_errors=True)
    finally:
        if not installed:
            shutil.rmtree(staging, ignore_errors=True)
    return OperationOutcome.clean(_handle(name, draft_dir, manifest))


def _write_tree(
    staging: Path, manifest: DraftManifest, sources: Mapping[PurePosixPath, _Source]
) -> None:
    for logical in ENTITY_DOCUMENT_DIRECTORIES:
        (staging / logical).mkdir(parents=True, exist_ok=True)
    _emit(staging, MANIFEST_PATH, manifest)
    for logical, source in sorted(sources.items(), key=lambda item: str(item[0])):
        target = staging / logical
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(source, Path):
            shutil.copyfile(source, target)
        else:
            _emit(staging, logical, source)


def _emit(staging: Path, logical: PurePosixPath, document: DocumentModel) -> None:
    (staging / logical).write_bytes(
        document_bytes(document.model_dump(mode="json"), logical_path=logical)
    )


# --------------------------------------------------------------------------------------
# Outcomes
# --------------------------------------------------------------------------------------


def _handle(name: str, root: Path, manifest: DraftManifest) -> DraftHandle:
    return DraftHandle(
        name=name,
        root=root,
        draft_of_revision=manifest.draft_of_revision,
        parent_bundle_digest=manifest.parent_bundle_digest,
    )


def _refusal(
    code: IssueCode, message: str, *, path: str | None = None
) -> OperationOutcome[DraftHandle]:
    return outcome_with(None, (diagnostic(code, message, path=path),))


def _conflict(record_ids: Sequence[str], message: str) -> OperationOutcome[DraftHandle]:
    """One diagnostic naming every colliding record, not one diagnostic per record.

    The operator's next action is the same for all of them — open the draft and decide — and a
    hundred findings for one rebase would bury the first.
    """
    ordered = sorted(record_ids)
    return outcome_with(
        None,
        (
            diagnostic(
                IssueCode.DRAFT_REBASE_CONFLICT,
                message,
                record_id=ordered[0],
                record_ids=list(ordered),
            ),
        ),
    )


def _deletion_conflict(
    logical: PurePosixPath, kept: DocumentModel, *, deleted_by: str, changed_by: str
) -> Diagnostic:
    """One side deleted a document the other side changed. Refused, never resolved by dropping it.

    The record-ID overlap gate cannot see this shape. It intersects record IDs, and a document one
    side no longer has contributes none — so a deletion facing an addition passes it in both
    directions, and for the six `policy/*.yaml` catalogs (which hold no addressable records at all)
    it passes for *every* edit they can carry. Treating the absence as the answer would discard the
    other side's work with no finding; when `changed_by` is the selected revision it would revert an
    already-promoted record, which the change ledger would not record either.

    `record_ids` names the records the surviving document holds — the work that would be lost — and
    is legitimately empty for a document without addressable records, where `path` is the locator.
    """
    record_ids = sorted(record_ids_in_document(kept))
    return diagnostic(
        IssueCode.DRAFT_REBASE_CONFLICT,
        f"{logical} was deleted by {deleted_by} and changed by {changed_by}; a rebase never "
        "chooses between a deletion and an edit, so resolve it in the draft",
        path=logical.as_posix(),
        record_id=record_ids[0] if record_ids else None,
        record_ids=record_ids,
    )


def _merge_conflict(logical: PurePosixPath, exc: DocumentMergeConflict) -> Diagnostic:
    """A per-document merge refusal, reported with the same code as a record overlap.

    `draft_rebase_conflict` covers it because the operator's situation is identical — two edits, one
    place, nobody but them can choose — and inventing a second code for the field-level case would
    widen a closed catalog to describe a distinction they cannot act on differently.

    `record_ids` is empty exactly when the conflicting unit has no addressable records — a catalog
    version or a tuple of catalog rows — and then `path` plus `details.field` is the whole locator
    (D-129). A document-level invariant is *not* one of those cases: its unit is the document, so a
    refusal on a ledger holding twelve records names all twelve. Reading an empty list as "no
    records were affected" is the reading the ruling forbids, and a whole-document conflict is
    precisely where that reading would be reassuring and wrong.
    """
    return diagnostic(
        IssueCode.DRAFT_REBASE_CONFLICT,
        f"{logical}: {exc}",
        path=logical.as_posix(),
        record_id=exc.record_id,
        record_ids=list(exc.record_ids),
        field=exc.field,
    )


__all__ = ["rebase_draft"]
