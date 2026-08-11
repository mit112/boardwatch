"""`inventory`, `inspect`, and `conflicts`: the three read-only reports (design §6, §19, §21).

## Reports, not repairs

§21 is categorical: these commands perform no writes, and no Gate A command deletes a revision, a
blob, a draft, or an unselected digest directory. So everything unusual this module finds becomes a
*field* or a *diagnostic* and nothing becomes an action. `inventory` in particular never adopts a
complete-but-unselected directory: a digest name reserves no revision number, so promotion is free
to reuse or ignore one, and an inventory that "helpfully" selected it would rewrite history from a
read-only command.

## Where the line between a field and a diagnostic falls

A **diagnostic** means *this file is outside the grammar*: an entry under the bundle root that is
not one of the seven declared members, an entry under `revisions/` that is not digest-named, a
digest-named directory whose `COMPLETE` is missing or disagrees, a file under `blobs/sha256/` whose
name is not a digest. Those are all `orphaned_artefact` at the `information` tier, so they never
change an exit code — the operator is being told, not stopped.

A **field** means *this is normal and you should know*: unreferenced blobs (an older revision may
still cite them), complete-but-unselected revisions, the draft list.

Two things are genuine errors and do change the exit code: a selected revision that cannot be
resolved or read, and a private `local-sources.yaml` that will not parse or that maps a source ID
the selected revision does not declare. The second is dead configuration — the owner cannot reopen
an original through it and nothing else will ever mention it.

**A bundle that has never promoted is not a finding.** It is the state `init` deliberately leaves
behind, so `inventory` reports `selected: None` and exits 0. Any other choice would make a fresh
bundle exit 1 and teach an operator to ignore this command's exit code.

## One pointer read

All three commands enter through `storage.read_current_once`, so an operation reports one coherent
immutable revision even if a promotion lands while it is running.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ValidationError

from boardwatch.profile_bundle.blobs import BLOB_TEMP_PREFIX, stored_digests
from boardwatch.profile_bundle.canonical import referenced_blob_digests
from boardwatch.profile_bundle.errors import (
    BundlePathError,
    Diagnostic,
    IssueCode,
    OperationOutcome,
    ProfileBundleError,
    RestrictedYamlError,
    diagnostic,
    outcome_with,
)
from boardwatch.profile_bundle.index import build_index
from boardwatch.profile_bundle.models.documents import BundleDocuments
from boardwatch.profile_bundle.models.history import ConflictRecord
from boardwatch.profile_bundle.models.sidecars import LocalSourcesSidecar
from boardwatch.profile_bundle.paths import (
    APPROVALS_DIR,
    BLOB_ALGORITHM_DIR,
    BLOBS_DIR,
    DRAFTS_DIR,
    LOCAL_SOURCES_FILE,
    REVISIONS_DIR,
    ROOT_MEMBERS,
    approvals_dir,
    blobs_dir,
    digest_token,
    drafts_dir,
    local_sources_path,
    require_bare_digest,
    require_draft_name,
    revisions_dir,
)
from boardwatch.profile_bundle.storage import (
    SelectedRevision,
    SelectionError,
    read_current_once,
    selected_documents,
)
from boardwatch.profile_bundle.validation.digest import PointerError, read_complete
from boardwatch.profile_bundle.yaml_loader import load_yaml_bytes

#: A selection failure that is a normal state rather than something to act on: `init` leaves exactly
#: this behind, and every bundle is in it until its first promotion.
_NOT_A_FINDING = IssueCode.NO_CURRENT_REVISION

_SIDECAR_PATH = PurePosixPath(LOCAL_SOURCES_FILE)


@dataclass(frozen=True)
class InventoryReport:
    """Everything present under one bundle root, and nothing changed by looking."""

    bundle_root: Path
    selected: SelectedRevision | None
    drafts: tuple[str, ...]
    approval_stamps: tuple[str, ...]
    complete_revisions: tuple[str, ...]
    incomplete_revisions: tuple[str, ...]
    temporary_entries: tuple[str, ...]
    referenced_blobs: tuple[str, ...]
    unreferenced_blobs: tuple[str, ...]
    undeclared_root_entries: tuple[str, ...]
    local_sources: LocalSourcesSidecar | None

    @property
    def unselected_revisions(self) -> tuple[str, ...]:
        """Complete revision directories that `CURRENT` does not name.

        Retained forever by §21 and reported so an operator can see them; nothing here or in
        `promote` treats their existence as a reason to do anything.
        """
        if self.selected is None:
            return self.complete_revisions
        selected = self.selected.root.name
        return tuple(name for name in self.complete_revisions if name != selected)


@dataclass(frozen=True)
class InspectReport:
    """One record, read from the one revision that was selected when the command started."""

    revision: int
    bundle_digest: str
    record_id: str
    kind: str
    path: str
    record: BaseModel
    evidence_ids: tuple[str, ...]
    conflict_ids: tuple[str, ...]


@dataclass(frozen=True)
class ConflictsReport:
    """Every conflict group in the selected revision, and which of them are still open."""

    revision: int
    bundle_digest: str
    conflicts: tuple[ConflictRecord, ...]
    unresolved_ids: frozenset[str]


# --------------------------------------------------------------------------------------
# inventory
# --------------------------------------------------------------------------------------


def inventory(bundle_root: Path) -> OperationOutcome[InventoryReport]:
    """Report what is under `bundle_root`. Adopts nothing, deletes nothing, writes nothing."""
    findings: list[Diagnostic] = []
    selection: SelectedRevision | None = None
    try:
        selection = read_current_once(bundle_root)
    except SelectionError as exc:
        if exc.code is not _NOT_A_FINDING:
            findings.append(diagnostic(exc.code, str(exc)))

    documents: BundleDocuments | None = None
    if selection is not None:
        try:
            documents = selected_documents(selection)
        except SelectionError as exc:
            findings.append(diagnostic(exc.code, str(exc)))
        except ProfileBundleError as exc:
            findings.append(
                diagnostic(IssueCode.IO_ERROR, f"the selected revision could not be read: {exc}")
            )

    undeclared = _undeclared_root_entries(bundle_root)
    findings.extend(_orphans("", undeclared, "the bundle root's member list is closed"))

    complete, incomplete, temporary = _revision_directories(bundle_root)
    findings.extend(
        _orphans(
            f"{REVISIONS_DIR}/",
            incomplete,
            "a digest-named revision without a usable COMPLETE marker is a torn promotion; it is "
            "retained and blocks nothing",
        )
    )
    findings.extend(
        _orphans(f"{REVISIONS_DIR}/", temporary, "this directory holds only digest-named revisions")
    )

    drafts, stray_drafts = _draft_names(bundle_root)
    findings.extend(
        _orphans(f"{DRAFTS_DIR}/", stray_drafts, "an interrupted draft installation, left in place")
    )

    stamps, stray_stamps = _approval_stamps(bundle_root)
    findings.extend(
        _orphans(f"{APPROVALS_DIR}/", stray_stamps, "this directory is keyed by candidate digest")
    )

    stored, stray_blobs = _blob_entries(bundle_root)
    findings.extend(
        _orphans(
            f"{BLOBS_DIR}/{BLOB_ALGORITHM_DIR}/",
            stray_blobs,
            "the blob store holds one file per digest, named by it",
        )
    )
    referenced = _referenced(documents)

    sidecar, sidecar_findings = _local_sources(bundle_root, documents)
    findings.extend(sidecar_findings)

    report = InventoryReport(
        bundle_root=bundle_root,
        selected=selection,
        drafts=drafts,
        approval_stamps=stamps,
        complete_revisions=complete,
        incomplete_revisions=incomplete,
        temporary_entries=temporary,
        referenced_blobs=() if referenced is None else referenced,
        unreferenced_blobs=(
            ()
            if referenced is None
            else tuple(digest for digest in stored if digest not in frozenset(referenced))
        ),
        undeclared_root_entries=undeclared,
        local_sources=sidecar,
    )
    return outcome_with(report, findings)


def _undeclared_root_entries(bundle_root: Path) -> tuple[str, ...]:
    """Names directly under the root that the closed §6 grammar does not admit.

    A symlinked member counts as undeclared even when its name is right: `CURRENT` and the revision
    directories are refused as symlinks at the point of use, and a symlinked `blobs/` or `drafts/`
    would put bundle content outside the one root the bundle claims to be self-contained under.
    """
    if not bundle_root.is_dir():
        return ()
    return tuple(
        sorted(
            entry.name
            for entry in bundle_root.iterdir()
            if entry.name not in ROOT_MEMBERS or entry.is_symlink()
        )
    )


def _revision_directories(bundle_root: Path) -> tuple[tuple[str, ...], tuple[str, ...],
                                                      tuple[str, ...]]:
    """Split `revisions/` into complete, incomplete, and not-a-revision-at-all.

    Completeness is `COMPLETE` naming this directory's own digest — the §6 step 7 comparison. A
    marker that names something else makes the directory untrustworthy rather than merely
    unfinished, and both land in the same bucket because both call for the same non-action.
    """
    directory = revisions_dir(bundle_root)
    if not directory.is_dir():
        return ((), (), ())
    complete: list[str] = []
    incomplete: list[str] = []
    temporary: list[str] = []
    for entry in sorted(directory.iterdir()):
        digest = _digest_of_token(entry.name)
        if digest is None or not entry.is_dir() or entry.is_symlink():
            temporary.append(entry.name)
            continue
        try:
            marker = read_complete(entry)
        except PointerError:
            incomplete.append(entry.name)
            continue
        (complete if marker == digest else incomplete).append(entry.name)
    return tuple(complete), tuple(incomplete), tuple(temporary)


def _digest_of_token(name: str) -> str | None:
    """`sha256-<64-hex>` back to `sha256:<64-hex>`, or `None` when the name is not one.

    Round-tripped through `digest_token` rather than matched against a second copy of its pattern,
    so a change to the filesystem spelling of a digest cannot leave this reader behind.
    """
    prefix, separator, hexadecimal = name.partition("-")
    if prefix != "sha256" or not separator:
        return None
    try:
        digest = "sha256:" + require_bare_digest(hexadecimal)
    except BundlePathError:
        return None
    return digest if digest_token(digest) == name else None


def _approval_stamps(bundle_root: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The candidate digests `approvals/` holds a stamp for, and anything else living there."""
    directory = approvals_dir(bundle_root)
    if not directory.is_dir():
        return ((), ())
    stamps: list[str] = []
    stray: list[str] = []
    for entry in sorted(directory.iterdir()):
        digest = _digest_of_token(entry.stem) if entry.suffix == ".yaml" else None
        if digest is None or not entry.is_file() or entry.is_symlink():
            stray.append(entry.name)
            continue
        stamps.append(digest)
    return tuple(stamps), tuple(stray)


def _draft_names(bundle_root: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Draft directory names, and anything under `drafts/` that is not one.

    Deliberately not parsed: a draft is the one place in the bundle that may hold anything at all,
    and an inventory that read every draft's manifest would fail on somebody's work in progress.
    An entry left by an interrupted install is reported, never adopted and never removed.
    """
    directory = drafts_dir(bundle_root)
    if not directory.is_dir():
        return ((), ())
    found: list[str] = []
    stray: list[str] = []
    for entry in sorted(directory.iterdir()):
        try:
            name = require_draft_name(entry.name)
        except BundlePathError:
            stray.append(entry.name)
            continue
        if entry.is_dir() and not entry.is_symlink():
            found.append(name)
        else:
            stray.append(entry.name)
    return tuple(found), tuple(stray)


def _blob_entries(bundle_root: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    directory = blobs_dir(bundle_root)
    stored = stored_digests(bundle_root)
    if not directory.is_dir():
        return ((), ())
    known = frozenset(stored)
    # A `.tmp-` name is an in-flight or abandoned capture the store already knows to skip, not an
    # artefact that does not belong here; the prefix is read from the store rather than restated.
    stray = tuple(
        sorted(
            entry.name
            for entry in directory.iterdir()
            if entry.name not in known and not entry.name.startswith(BLOB_TEMP_PREFIX)
        )
    )
    return stored, stray


def _referenced(documents: BundleDocuments | None) -> tuple[str, ...] | None:
    """The blob digests the SELECTED revision cites, or `None` when they could not be read.

    A blob outside this set is not garbage — §6 shares the store across revisions, and an older
    revision may be the only thing citing it. That is exactly why the report names it and no command
    removes it. `None` is distinct from empty on purpose: a revision whose evidence document is
    missing has no measured reference set, and calling every stored blob unreferenced would be a
    measurement nobody took.
    """
    if documents is None:
        return None
    try:
        return referenced_blob_digests(documents)
    except ProfileBundleError:
        return None


def _local_sources(
    bundle_root: Path, documents: BundleDocuments | None
) -> tuple[LocalSourcesSidecar | None, tuple[Diagnostic, ...]]:
    """Parse the private sidecar and check its keys against the selected source catalog."""
    path = local_sources_path(bundle_root)
    if not path.exists():
        return None, ()
    try:
        raw = load_yaml_bytes(path.read_bytes(), logical_path=_SIDECAR_PATH)
    except RestrictedYamlError as exc:
        return None, (diagnostic(exc.code, str(exc), path=LOCAL_SOURCES_FILE),)
    except OSError as exc:
        return None, (
            diagnostic(IssueCode.IO_ERROR, f"{LOCAL_SOURCES_FILE}: {exc}", path=LOCAL_SOURCES_FILE),
        )
    try:
        sidecar = LocalSourcesSidecar.model_validate(raw)
    except ValidationError as exc:
        return None, (
            diagnostic(
                IssueCode.MODEL_VALIDATION_ERROR,
                f"{LOCAL_SOURCES_FILE} is not a source-ID to absolute-root mapping: "
                f"{exc.error_count()} field error(s)",
                path=LOCAL_SOURCES_FILE,
            ),
        )
    if documents is None:
        # Nothing to compare against; reporting every mapping as broken would be a measurement
        # taken against a catalog that was never read.
        return sidecar, ()
    catalog = build_index(documents).sources
    declared = frozenset(catalog.by_id) if catalog is not None else frozenset()
    return sidecar, tuple(
        diagnostic(
            IssueCode.BROKEN_REFERENCE,
            f"{LOCAL_SOURCES_FILE} maps {source_id}, which the selected revision's source catalog "
            "does not declare; the mapping cannot reopen anything",
            path=LOCAL_SOURCES_FILE,
            record_id=source_id,
        )
        for source_id in sorted(sidecar.resolved_source_ids() - declared)
    )


def _orphans(prefix: str, names: Iterable[str], why: str) -> tuple[Diagnostic, ...]:
    """One `information` finding per artefact outside the grammar. Never changes an exit code.

    `prefix` qualifies the reported path with the directory the entry was found in, so a stray
    `notes.txt` at the root and one under `revisions/` are two distinguishable findings.
    """
    return tuple(
        diagnostic(IssueCode.ORPHANED_ARTEFACT, f"{prefix}{name}: {why}", path=f"{prefix}{name}")
        for name in names
    )


# --------------------------------------------------------------------------------------
# inspect and conflicts
# --------------------------------------------------------------------------------------


def inspect_record(bundle_root: Path, record_id: str) -> OperationOutcome[InspectReport]:
    """Report one record from the selected revision, with what cites it and what contests it."""
    resolved = _selected(bundle_root)
    if isinstance(resolved, Diagnostic):
        return outcome_with(None, (resolved,))
    selection, documents = resolved

    index = build_index(documents)
    record = index.get(record_id)
    path = index.path_of(record_id)
    kind = index.kinds.get(record_id)
    if record is None or path is None or kind is None:
        return outcome_with(
            None,
            (
                diagnostic(
                    IssueCode.RECORD_NOT_FOUND,
                    f"{record_id} is not a record in revision {selection.revision}",
                    record_id=record_id,
                ),
            ),
        )
    return OperationOutcome.clean(
        InspectReport(
            revision=selection.revision,
            bundle_digest=selection.bundle_digest,
            record_id=record_id,
            kind=kind,
            path=path,
            record=record,
            evidence_ids=index.evidence_links.get(record_id, ()),
            conflict_ids=tuple(
                conflict.conflict_id
                for conflict in index.conflicts
                if record_id in conflict.candidate_fact_ids or conflict.subject_id == record_id
            ),
        )
    )


def conflicts_report(bundle_root: Path) -> OperationOutcome[ConflictsReport]:
    """List every conflict group in the selected revision.

    An unresolved group is data, not a finding: §20.5 says a bundle may validly preserve
    uncertainty, and `validate --completeness` is where an open group becomes a blocker.
    """
    resolved = _selected(bundle_root)
    if isinstance(resolved, Diagnostic):
        return outcome_with(None, (resolved,))
    selection, documents = resolved
    index = build_index(documents)
    return OperationOutcome.clean(
        ConflictsReport(
            revision=selection.revision,
            bundle_digest=selection.bundle_digest,
            conflicts=index.conflicts,
            unresolved_ids=index.unresolved_conflict_ids,
        )
    )


def _selected(bundle_root: Path) -> tuple[SelectedRevision, BundleDocuments] | Diagnostic:
    """The selected revision and its documents, or the one diagnostic explaining why not.

    Unlike `inventory`, these two commands have nothing to say about a bundle whose selection cannot
    be resolved, so "no revision has been promoted yet" is a refusal here rather than a field.
    """
    try:
        selection = read_current_once(bundle_root)
        return selection, selected_documents(selection)
    except SelectionError as exc:
        return diagnostic(exc.code, str(exc))
    except ProfileBundleError as exc:
        return diagnostic(IssueCode.IO_ERROR, f"the selected revision could not be read: {exc}")


__all__ = [
    "ConflictsReport",
    "InspectReport",
    "InventoryReport",
    "conflicts_report",
    "inspect_record",
    "inventory",
]
