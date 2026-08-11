"""Move a draft onto the selected revision, or refuse having written nothing (design §6, §21).

A draft is checked out of one revision and edited while the world moves on. `rebase-draft` is how it
catches up, and the whole value of the command is in what it does when it *cannot*.

## The order of operations is the contract

1. Take the bundle's exclusive writer lock, **non-blocking**, before anything else — including
   before rereading `CURRENT`. Reading the pointer first would mean deciding what to rebase onto
   using a value a promotion could replace while this command was still deciding.
2. Refuse, without writing, on: an occupied backup path that does not hold this exact draft, a
   record both sides touched, an unreadable old parent, or an evidence blob whose bytes are gone.
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
    FilesystemBlobReader,
    MissingBlobError,
    evidence_set_digest,
)
from boardwatch.profile_bundle.diff import (
    NO_BASE,
    DocumentMergeConflict,
    diff_records,
    merge_document,
    merge_values,
    record_contents,
)
from boardwatch.profile_bundle.drafts import DRAFT_TEMP_PREFIX, DraftHandle
from boardwatch.profile_bundle.errors import (
    BundleIoError,
    Diagnostic,
    IssueCode,
    OperationOutcome,
    ProfileBundleError,
    diagnostic,
    outcome_with,
)
from boardwatch.profile_bundle.layout import ENTITY_DOCUMENT_DIRECTORIES
from boardwatch.profile_bundle.locking import BundleLockHeldError, bundle_lock
from boardwatch.profile_bundle.models.documents import BundleDocuments, DocumentModel
from boardwatch.profile_bundle.models.manifests import DraftManifest, RevisionManifest
from boardwatch.profile_bundle.paths import (
    blobs_dir,
    draft_root,
    drafts_dir,
    rebase_backup_root,
    require_draft_name,
    revision_root,
)
from boardwatch.profile_bundle.storage import (
    SelectedRevision,
    SelectionError,
    read_current_once,
    selected_documents,
)
from boardwatch.profile_bundle.validation.context import load_documents, parse_error_diagnostics
from boardwatch.profile_bundle.yaml_writer import document_bytes

MANIFEST_PATH = PurePosixPath("manifest.yaml")
EVIDENCE_PATH = PurePosixPath("evidence/records.yaml")

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
    # holding a lock that makes another writer wait.
    draft_name = require_draft_name(name)
    # Before the lock, because `filelock` creates the lockfile's directory: a mistyped `--bundle`
    # would otherwise leave a new empty directory behind as the only trace of a failed command.
    if not bundle_root.is_dir():
        return _refusal(
            IssueCode.NO_CURRENT_REVISION,
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

    backup = rebase_backup_root(bundle_root, name, draft_manifest.parent_bundle_digest)
    reuse = backup.exists()
    if reuse and not _identical_trees(draft_dir, backup):
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
    """
    merged: dict[PurePosixPath, DocumentModel] = {}
    sources: dict[PurePosixPath, _Source] = {}
    for logical in sorted(set(ours.by_path) | set(theirs.by_path), key=str):
        inherited = None if base is None else base.by_path.get(logical)
        our_document = ours.by_path.get(logical)
        their_document = theirs.by_path.get(logical)
        if our_document is None:
            # Absent from the draft: dropped by the owner if the base had it, otherwise a file only
            # the new revision has. The owner-dropped case cannot also have been edited by the new
            # revision — that would be an overlap, already refused above.
            if inherited is None and their_document is not None:
                merged[logical] = their_document
                sources[logical] = revision_dir / logical
            continue
        if their_document is None:
            if inherited is None:
                merged[logical] = our_document
                sources[logical] = draft_dir / logical
            continue
        if our_document == their_document or (
            inherited is not None and their_document == inherited
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
        # An exact backup already holds these bytes, so the draft is moved to a temporary name and
        # removed after the install. Nothing is lost: the retained backup is byte-identical, which
        # is the condition that got us here.
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


def _identical_trees(left: Path, right: Path) -> bool:
    """Whether two real directories hold exactly the same relative paths and bytes.

    A symlink on either side makes the answer `False` rather than "follow it and compare": a
    symlinked backup is not this draft's bytes, it is a pointer at somebody else's. That includes
    the *root* — a backup path symlinked at the draft would otherwise compare equal to it by
    construction, and the caller would then delete the only copy of the pre-rebase draft.
    """
    left_contents = _tree_contents(left)
    return left_contents is not None and left_contents == _tree_contents(right)


def _tree_contents(root: Path) -> dict[str, bytes] | None:
    """Every relative path under `root` and its bytes, or `None` if `root` is not a real directory.

    `rglob` follows a symlinked root silently, so the root is checked before it is walked.
    """
    if root.is_symlink() or not root.is_dir():
        return None
    contents: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            return None
        contents[relative + "/" if path.is_dir() else relative] = (
            b"" if path.is_dir() else path.read_bytes()
        )
    return contents


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


def _merge_conflict(logical: PurePosixPath, exc: DocumentMergeConflict) -> Diagnostic:
    """A per-document merge refusal, reported with the same code as a record overlap.

    `draft_rebase_conflict` covers it because the operator's situation is identical — two edits, one
    place, nobody but them can choose — and inventing a second code for the field-level case would
    widen a closed catalog to describe a distinction they cannot act on differently.
    """
    return diagnostic(
        IssueCode.DRAFT_REBASE_CONFLICT,
        f"{logical}: {exc}",
        path=logical.as_posix(),
        record_id=exc.record_id,
        record_ids=[exc.record_id] if exc.record_id is not None else [],
        field=exc.field,
    )


__all__ = ["rebase_draft"]
