"""`boardwatch profile-bundle`: the twelve commands design §7 and §19 name.

This module is a **translation**, and deliberately nothing else. Every decision about the bundle is
made under `boardwatch.profile_bundle`; what lives here is argument parsing, the two renderings,
and the exit code. The one exception is the approval prompt, which is an operator interaction and
therefore has nowhere else to live — and even that calls the pure `build_approval_stamp` for the
document it files.

## Three rules this file is answerable for

- **No database.** The bundle is filesystem-only, so these commands call `load_settings` for
  `config_dir` and never `build_context`, which would create and migrate `boardwatch.db` in a data
  directory the operator never asked to initialise.
- **No absolute path in a diagnostic.** Everything printed about a failure is a *logical* path
  inside the bundle or the name of the option that carried the input. An operator pastes JSON into
  a bug report; their home directory is not ours to publish.
- **The exit tiers are read, never restated.** `OperationOutcome.exit_code` and
  `errors.exit_code_for_category` own the 0/1/2/3 mapping. Exit 2 is the only one this layer
  produces, and only through Typer's own parameter handling — which is what §21 means by "produced
  before command execution".

## Why every command has `--json`

Design §19 shows the flag on the four read-only commands, because those are the ones an agent reads
back. But §21's exit contract covers the whole family, and its exit-1 and exit-3 rows —
`stale_draft_parent`, `bundle_lock_held`, `promotion_target_conflict` — only ever arise in
`promote`, `rebase-draft` and `approve`. A machine surface on four commands would leave the exit
contract's most consequential rows with no machine rendering at all.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Final, NoReturn, Protocol, TypeVar

import typer

from boardwatch.core.settings import load_settings
from boardwatch.profile_bundle import authoring, drafts, inspection, migrations, promotion, rebase
from boardwatch.profile_bundle.approvals import (
    ApprovalDecision,
    approval_stamp_bytes,
    build_approval_stamp,
    required_approval_decisions,
)
from boardwatch.profile_bundle.blobs import quarantined_blobs
from boardwatch.profile_bundle.canonical import (
    FilesystemBlobReader,
    candidate_content_digest,
    referenced_blob_digests,
)
from boardwatch.profile_bundle.errors import (
    BundlePathError,
    Diagnostic,
    IssueCode,
    JsonValue,
    OperationOutcome,
    ProfileBundleError,
    diagnostic,
    io_reason,
    outcome_with,
)
from boardwatch.profile_bundle.index import build_index
from boardwatch.profile_bundle.layout import FIXED_DOCUMENTS, DocumentKind
from boardwatch.profile_bundle.models.documents import BundleDocuments
from boardwatch.profile_bundle.models.history import Actor
from boardwatch.profile_bundle.models.manifests import DraftManifest, RevisionManifest
from boardwatch.profile_bundle.paths import (
    approval_path,
    approvals_dir,
    blobs_dir,
    draft_root,
    require_draft_name,
    require_draft_segment,
    resolve_bundle_root,
    revision_root,
)
from boardwatch.profile_bundle.reports import (
    REPORT_SCHEMA,
    ValidationReport,
    diagnostic_json,
    diagnostic_line,
)
from boardwatch.profile_bundle.storage import (
    SelectedRevision,
    SelectionError,
    read_current_once,
    selected_documents,
)
from boardwatch.profile_bundle.validation import (
    ParentSnapshot,
    load_documents,
    parse_error_diagnostics,
    validate_bundle,
)

#: The draft `init` and `checkout` create when the operator names none. The option is optional in
#: §19's surface, so a default has to live somewhere, and the command layer is where a default that
#: is purely a convenience belongs.
DEFAULT_DRAFT_NAME: Final = "baseline"

#: What the owner types to approve. An exact word rather than a y/n, so a stray keypress cannot
#: file an approval — and not the digest itself, which is 64 characters an owner would paste rather
#: than read.
CONFIRMATION_WORD: Final = "approve"

#: The one document `init` deliberately leaves for the owner to author. Read out of the grammar
#: rather than spelled again, so a change to the layout moves the signpost with it.
IDENTITY_DOCUMENT: Final = next(
    path for path, kind in FIXED_DOCUMENTS.items() if kind is DocumentKind.IDENTITY
)

#: The human translation of that absence. The machine message stays exactly what the structural
#: layer emits — a script matching on it must not break — and this is added underneath, in the one
#: rendering a person reads.
IDENTITY_SIGNPOST: Final = (
    f"    -> {IDENTITY_DOCUMENT} is yours to author. A new bundle is created without it on "
    "purpose: a person needs a display name and review dates that only you have, and a "
    "placeholder that survived to promotion would be a fact nobody wrote. Add the file to the "
    "draft and validate again."
)

_T = TypeVar("_T")

profile_bundle_app = typer.Typer(
    no_args_is_help=True,
    help="Author, validate and promote the canonical career-profile bundle.",
)


# --------------------------------------------------------------------------------------
# Options
# --------------------------------------------------------------------------------------


def _new_draft(value: str) -> str:
    """A draft name the operator is asking to create: the shorter, operator-facing cap."""
    try:
        return require_draft_name(value)
    except BundlePathError as exc:
        raise typer.BadParameter(str(exc), param_hint="--draft") from exc


def _existing_draft(value: str) -> str:
    """A draft name that already exists: the segment grammar `inventory` reports names under.

    Deliberately the wider of the two. A rebase backup is a draft directory with a derived suffix,
    it is the only copy of a draft whose rebase went wrong, and refusing to address it here would
    make `inventory` list a draft no command would take.
    """
    try:
        return require_draft_segment(value)
    except BundlePathError as exc:
        raise typer.BadParameter(str(exc), param_hint="--draft") from exc


def _optional_existing_draft(value: str | None) -> str | None:
    """`--draft` where omitting it means "the selected revision", not "a draft called None"."""
    return None if value is None else _existing_draft(value)


def _iso_date(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter(
            f"{value!r} is not an ISO date (YYYY-MM-DD)", param_hint="--as-of"
        ) from exc


BUNDLE_OPTION = typer.Option(  # noqa: B008
    None, "--bundle", help="Bundle root (default: <config dir>/career-profile)."
)
NEW_DRAFT_OPTION = typer.Option(  # noqa: B008
    DEFAULT_DRAFT_NAME, "--draft", callback=_new_draft, help="Name for the draft to create."
)
DRAFT_OPTION = typer.Option(  # noqa: B008
    ..., "--draft", callback=_existing_draft, help="Draft to operate on."
)
OPTIONAL_DRAFT_OPTION = typer.Option(  # noqa: B008
    None,
    "--draft",
    callback=_optional_existing_draft,
    help="Validate this draft instead of the selected revision.",
)
JSON_OPTION = typer.Option(False, "--json", help="Emit the deterministic machine report.")  # noqa: B008


# --------------------------------------------------------------------------------------
# The two renderings
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Rendered:
    """One command's answer in both shapes, before the envelope is put around it."""

    result: Mapping[str, JsonValue]
    lines: Sequence[str]


def _human_diagnostic(finding: Diagnostic) -> str:
    line = diagnostic_line(finding)
    if (
        finding.code == str(IssueCode.MISSING_REQUIRED_FILE)
        and finding.path == IDENTITY_DOCUMENT.as_posix()
    ):
        return f"{line}\n{IDENTITY_SIGNPOST}"
    return line


def _emit(
    command: str,
    outcome: OperationOutcome[Any],
    rendered: _Rendered,
    *,
    as_json: bool,
    as_of: date | None = None,
) -> NoReturn:
    """Print one command's answer and exit with the code the library computed.

    Never returns: every command ends here, so the exit code and the output are emitted in one
    place and a command cannot print an answer and then fall through to a different one.
    """
    if as_json:
        payload: dict[str, JsonValue] = {
            "report_schema": REPORT_SCHEMA,
            "command": command,
            "outcome": outcome.category,
            "exit_code": outcome.exit_code,
            "as_of": as_of.isoformat() if as_of is not None else None,
            "result": dict(rendered.result),
            "diagnostics": [diagnostic_json(finding) for finding in outcome.diagnostics],
        }
        typer.echo(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        )
    else:
        lines = [f"profile-bundle {command}: {outcome.category}"]
        if as_of is not None:
            lines.append(f"as-of: {as_of.isoformat()}")
        lines.extend(rendered.lines)
        lines.extend(_human_diagnostic(finding) for finding in outcome.diagnostics)
        typer.echo("\n".join(lines))
    raise typer.Exit(code=outcome.exit_code)


def _nothing() -> _Rendered:
    return _Rendered(result={}, lines=())


def _guarded(call: Callable[[], OperationOutcome[_T]]) -> OperationOutcome[_T]:
    """Run one library call, turning a typed escape into §21's could-not-complete.

    `ProfileBundleError` is the package's own base class, so this catches exactly the failures it
    declares and nothing else — a bare `except Exception` here would swallow a genuine defect in
    this file and report it as an unreadable bundle. The exception's message is deliberately not
    printed: some of them are built from a stringified `OSError`, which carries an absolute path.
    """
    try:
        return call()
    except ProfileBundleError as exc:
        return outcome_with(
            None,
            (
                diagnostic(
                    IssueCode.INTERNAL_ERROR,
                    "the command could not complete; nothing was written. This is a defect — "
                    "please report the error type below with what you ran",
                    error_type=type(exc).__name__,
                ),
            ),
        )
    except OSError as exc:
        return outcome_with(
            None,
            (
                diagnostic(
                    IssueCode.IO_ERROR, f"the command could not complete: {io_reason(exc)}"
                ),
            ),
        )


# --------------------------------------------------------------------------------------
# Shared resolution
# --------------------------------------------------------------------------------------


def _bundle_root(ctx: typer.Context, override: Path | None) -> Path:
    """`--bundle`, else `config_dir / "career-profile"`.

    `load_settings` reads `config.toml` and creates nothing; `build_context` would create the data
    directory and the database, which no bundle command needs.
    """
    return resolve_bundle_root(load_settings(data_dir=ctx.obj).config_dir, override)


def _selected(bundle_root: Path) -> SelectedRevision | None:
    """The selected revision, or `None` when this bundle has never been promoted."""
    try:
        return read_current_once(bundle_root)
    except SelectionError as exc:
        if exc.code is IssueCode.NO_CURRENT_REVISION:
            return None
        raise


def _parent_snapshot(bundle_root: Path, tree: Path, mode: str) -> ParentSnapshot | None:
    """The direct parent of the tree being validated, when it is on disk and readable.

    Supplied explicitly rather than left to the validation layer's own disk resolution, because the
    caller already knows which revision the tree descends from and §20.6's candidate recomputation
    needs that exact one. `None` when there is no parent or it cannot be read — which validation
    reports as `unverifiable_ancestor` rather than treating as a clean comparison.
    """
    try:
        documents = load_documents(tree, mode="draft" if mode == "draft" else "revision")
        digest = documents.manifest.parent_bundle_digest
        if digest is None:
            return None
        parent_dir = revision_root(bundle_root, digest)
        parent_documents = load_documents(parent_dir, mode="revision")
    except ProfileBundleError:
        return None
    manifest = parent_documents.manifest
    if not isinstance(manifest, RevisionManifest):
        return None
    return ParentSnapshot(
        root=parent_dir,
        documents=parent_documents,
        envelope=manifest.envelope,
        index=build_index(parent_documents),
    )


def _refusal(code: IssueCode, message: str) -> OperationOutcome[Any]:
    return outcome_with(None, (diagnostic(code, message),))


# --------------------------------------------------------------------------------------
# Draft lifecycle
# --------------------------------------------------------------------------------------


def _draft_rendered(handle: drafts.DraftHandle | None) -> _Rendered:
    if handle is None:
        return _nothing()
    return _Rendered(
        result={
            "draft": handle.name,
            "draft_of_revision": handle.draft_of_revision,
            "parent_bundle_digest": handle.parent_bundle_digest,
        },
        lines=(
            f"draft: {handle.name}",
            f"parent: {handle.parent_bundle_digest or 'none (this bundle has no revision yet)'}",
        ),
    )


@profile_bundle_app.command("init")
def init(
    ctx: typer.Context,
    bundle: Path | None = BUNDLE_OPTION,
    draft: str = NEW_DRAFT_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Create the bundle skeleton and one empty, parentless revision-1 draft."""
    root = _bundle_root(ctx, bundle)
    outcome = _guarded(lambda: drafts.init_draft(root, name=draft))
    _emit("init", outcome, _draft_rendered(outcome.value), as_json=json_output)


@profile_bundle_app.command("checkout")
def checkout(
    ctx: typer.Context,
    bundle: Path | None = BUNDLE_OPTION,
    draft: str = NEW_DRAFT_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Copy the selected revision into a writable draft."""
    root = _bundle_root(ctx, bundle)
    outcome = _guarded(lambda: drafts.checkout_current(root, name=draft))
    _emit("checkout", outcome, _draft_rendered(outcome.value), as_json=json_output)


@profile_bundle_app.command("rebase-draft")
def rebase_draft(
    ctx: typer.Context,
    draft: str = DRAFT_OPTION,
    bundle: Path | None = BUNDLE_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Move a draft onto the selected revision, keeping a deterministic backup of the old one."""
    root = _bundle_root(ctx, bundle)
    outcome = _guarded(lambda: rebase.rebase_draft(root, name=draft))
    _emit("rebase-draft", outcome, _draft_rendered(outcome.value), as_json=json_output)


# --------------------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------------------


def _validation_rendered(report: ValidationReport | None) -> _Rendered:
    if report is None:
        return _nothing()
    return _Rendered(
        result={
            "schema_version": report.schema_version,
            "bundle_digest": report.bundle_digest,
            "candidate_digest": report.candidate_digest,
            "counts": report.counts.as_json(),
        },
        lines=(
            ", ".join(
                (
                    f"{report.counts.error} error",
                    f"{report.counts.blocker} blocker",
                    f"{report.counts.warning} warning",
                    f"{report.counts.information} information",
                )
            ),
            f"candidate digest: {report.candidate_digest or 'not computed by this run'}",
        ),
    )


@profile_bundle_app.command("validate")
def validate(
    ctx: typer.Context,
    bundle: Path | None = BUNDLE_OPTION,
    draft: str | None = OPTIONAL_DRAFT_OPTION,
    completeness: bool = typer.Option(  # noqa: B008
        False, "--completeness", help="Also run the dated completeness checks."
    ),
    as_of: str | None = typer.Option(  # noqa: B008
        None, "--as-of", help="Date the completeness checks run at (default: today)."
    ),
    deep_history: bool = typer.Option(  # noqa: B008
        False, "--deep-history", help="Recompute every intact ancestor, not just the envelope."
    ),
    json_output: bool = JSON_OPTION,
) -> None:
    """Validate the selected revision, or a draft, and report everything every layer found."""
    requested = _iso_date(as_of)
    if requested is not None and not completeness:
        # The same reasoning that keeps `--draft` off `migrate`: an argument that cannot affect the
        # outcome would be accepted and silently ignored, which discards what the operator asked
        # for. Only completeness is dated (§20).
        raise typer.BadParameter(
            "--as-of dates the completeness checks, so it needs --completeness",
            param_hint="--as-of",
        )
    if deep_history and not completeness:
        raise typer.BadParameter(
            "--deep-history is the ancestor audit inside completeness, so it needs --completeness",
            param_hint="--deep-history",
        )
    # The **local** date (§20): "today" for an operator is the day they are having, and a UTC
    # default would report a different one for anybody west of Greenwich after their afternoon.
    effective = (requested or datetime.now().astimezone().date()) if completeness else None

    root = _bundle_root(ctx, bundle)
    if draft is not None:
        tree = draft_root(root, draft)
        mode = "draft"
        if not tree.is_dir():
            outcome = _refusal(
                IssueCode.DRAFT_NOT_FOUND, f"drafts/{draft} does not exist; nothing to validate"
            )
            _emit("validate", outcome, _nothing(), as_json=json_output)
    else:
        selection = _guarded(lambda: _selected_outcome(root))
        if selection.value is None:
            _emit("validate", selection, _nothing(), as_json=json_output)
        tree = selection.value.root
        mode = "revision"

    outcome = _guarded(
        lambda: validate_bundle(
            tree,
            bundle_root=root,
            mode="draft" if mode == "draft" else "revision",
            completeness=completeness,
            as_of=effective,
            parent=_parent_snapshot(root, tree, mode),
            deep_history=deep_history,
        )
    )
    report = outcome.value
    _emit(
        "validate",
        outcome,
        _validation_rendered(report),
        as_json=json_output,
        as_of=report.as_of if report is not None else None,
    )


def _selected_outcome(bundle_root: Path) -> OperationOutcome[SelectedRevision]:
    try:
        return OperationOutcome.clean(read_current_once(bundle_root))
    except SelectionError as exc:
        return outcome_with(None, (diagnostic(exc.code, str(exc)),))


@profile_bundle_app.command("inspect")
def inspect(
    ctx: typer.Context,
    record_id: str = typer.Argument(..., help="The record to inspect."),  # noqa: B008
    bundle: Path | None = BUNDLE_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Show one record from the selected revision, with what cites it."""
    root = _bundle_root(ctx, bundle)
    outcome = _guarded(lambda: inspection.inspect_record(root, record_id))
    _emit("inspect", outcome, _inspect_rendered(outcome.value), as_json=json_output)


def _inspect_rendered(report: inspection.InspectReport | None) -> _Rendered:
    if report is None:
        return _nothing()
    return _Rendered(
        result={
            "revision": report.revision,
            "bundle_digest": report.bundle_digest,
            "record_id": report.record_id,
            "kind": report.kind,
            "path": report.path,
            "record": report.record.model_dump(mode="json"),
            "evidence_ids": list(report.evidence_ids),
            "conflict_ids": list(report.conflict_ids),
        },
        lines=(
            f"{report.record_id} ({report.kind}) in {report.path}, revision {report.revision}",
            f"evidence: {', '.join(report.evidence_ids) or 'none'}",
            f"conflicts: {', '.join(report.conflict_ids) or 'none'}",
            json.dumps(report.record.model_dump(mode="json"), indent=2, sort_keys=True),
        ),
    )


@profile_bundle_app.command("inventory")
def inventory(
    ctx: typer.Context,
    bundle: Path | None = BUNDLE_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """List every draft, revision, approval stamp and blob this bundle holds."""
    root = _bundle_root(ctx, bundle)
    outcome = _guarded(lambda: inspection.inventory(root))
    _emit("inventory", outcome, _inventory_rendered(outcome.value), as_json=json_output)


def _inventory_rendered(report: inspection.InventoryReport | None) -> _Rendered:
    """Everything `inventory` measured — and `null` where it measured nothing.

    Two things are deliberately absent. `bundle_root` is an absolute path on this machine, and the
    operator supplied it. `local_sources`' values are the absolute roots of the private sidecar,
    which is exactly the material §5 keeps out of every revision, digest and export; the source IDs
    it resolves are reported instead, because *which* sources are locally available is the fact a
    reader needs.
    """
    if report is None:
        return _nothing()
    selected = report.selected
    # `None` is not zero: a run that could not read the evidence set measured nothing, and printing
    # "0 referenced" would be a number nobody took (D-012).
    if report.referenced_blobs is None or report.unreferenced_blobs is None:
        blobs_line = "blobs: not measured (the evidence set could not be read)"
    else:
        blobs_line = (
            f"blobs: {len(report.referenced_blobs)} referenced, "
            f"{len(report.unreferenced_blobs)} unreferenced"
        )
    return _Rendered(
        result={
            "selected_revision": None if selected is None else selected.revision,
            "selected_bundle_digest": None if selected is None else selected.bundle_digest,
            "drafts": list(report.drafts),
            "approval_stamps": list(report.approval_stamps),
            "complete_revisions": list(report.complete_revisions),
            "incomplete_revisions": list(report.incomplete_revisions),
            "unselected_revisions": list(report.unselected_revisions),
            "temporary_entries": list(report.temporary_entries),
            "referenced_blobs": (
                None if report.referenced_blobs is None else list(report.referenced_blobs)
            ),
            "unreferenced_blobs": (
                None if report.unreferenced_blobs is None else list(report.unreferenced_blobs)
            ),
            "undeclared_root_entries": list(report.undeclared_root_entries),
            "local_source_ids": (
                []
                if report.local_sources is None
                else sorted(report.local_sources.resolved_source_ids())
            ),
        },
        lines=(
            f"selected revision: "
            f"{'none' if selected is None else f'{selected.revision} {selected.bundle_digest}'}",
            f"drafts: {', '.join(report.drafts) or 'none'}",
            f"revisions: {len(report.complete_revisions)} complete, "
            f"{len(report.incomplete_revisions)} incomplete",
            f"approval stamps: {len(report.approval_stamps)}",
            blobs_line,
        ),
    )


@profile_bundle_app.command("conflicts")
def conflicts(
    ctx: typer.Context,
    bundle: Path | None = BUNDLE_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """List the selected revision's conflict groups and which are still open."""
    root = _bundle_root(ctx, bundle)
    outcome = _guarded(lambda: inspection.conflicts_report(root))
    _emit("conflicts", outcome, _conflicts_rendered(outcome.value), as_json=json_output)


def _conflicts_rendered(report: inspection.ConflictsReport | None) -> _Rendered:
    if report is None:
        return _nothing()
    return _Rendered(
        result={
            "revision": report.revision,
            "bundle_digest": report.bundle_digest,
            "conflicts": [record.model_dump(mode="json") for record in report.conflicts],
            "unresolved_ids": sorted(report.unresolved_ids),
        },
        lines=tuple(
            f"{record.conflict_id}: {record.state} "
            f"({len(record.candidate_fact_ids)} candidates, "
            f"active ruling {record.active_ruling_id or 'none'})"
            for record in report.conflicts
        )
        or ("no conflict groups",),
    )


@profile_bundle_app.command("migrate")
def migrate(
    ctx: typer.Context,
    bundle: Path | None = BUNDLE_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Report the selected revision's schema state. At schema v1 this writes nothing."""
    root = _bundle_root(ctx, bundle)
    outcome = _guarded(lambda: migrations.migrate_bundle(root))
    result = outcome.value
    rendered = (
        _nothing()
        if result is None
        else _Rendered(
            result={"status": result.status, "schema_version": result.schema_version},
            lines=(f"{result.status} at schema version {result.schema_version}",),
        )
    )
    _emit("migrate", outcome, rendered, as_json=json_output)


# --------------------------------------------------------------------------------------
# Authoring
# --------------------------------------------------------------------------------------


def _gate_lines(gates: Sequence[ApprovalDecision]) -> tuple[str, ...]:
    if not gates:
        return ("owner approval required: none",)
    return (
        "owner approval required:",
        *(
            f"  {decision.action.value} {decision.target_record_id} -> "
            f"{decision.resulting_state}"
            for decision in gates
        ),
    )


def _gate_json(gates: Sequence[ApprovalDecision]) -> list[JsonValue]:
    return [
        {
            "action": decision.action.value,
            "target_record_id": decision.target_record_id,
            "target_content_digest": decision.target_content_digest,
            "resulting_state": decision.resulting_state,
        }
        for decision in gates
    ]


@profile_bundle_app.command("add-evidence")
def add_evidence(
    ctx: typer.Context,
    draft: str = DRAFT_OPTION,
    evidence_file: Path = typer.Option(  # noqa: B008
        ...,
        "--evidence-file",
        exists=True,
        dir_okay=False,
        readable=True,
        help="A strict evidence record, as YAML.",
    ),
    capture: Path = typer.Option(  # noqa: B008
        ...,
        "--capture",
        exists=True,
        dir_okay=False,
        readable=True,
        help="The capture bytes the record describes.",
    ),
    bundle: Path | None = BUNDLE_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Capture one evidence record into a draft, then revalidate it."""
    root = _bundle_root(ctx, bundle)
    # Read inside the guard: Click has already refused a path that is absent, a directory, or
    # unreadable — before execution, which is what §21's exit 2 is for — so what is left here is
    # the file changing under us, and that is an I/O failure the shared arm reports without the
    # absolute path a stringified `OSError` carries.
    outcome = _guarded(
        lambda: authoring.add_evidence(
            root,
            draft_name=draft,
            evidence_document=evidence_file.read_bytes(),
            capture=capture.read_bytes(),
        )
    )
    added = outcome.value
    if added is None:
        _emit("add-evidence", outcome, _nothing(), as_json=json_output)
    rendered = _Rendered(
        result={
            "draft": added.draft_name,
            "evidence_id": added.evidence_id,
            "capture_kind": added.capture_kind,
            "blob_digest": added.blob_digest,
            "blob_outcome": added.blob_outcome,
            "owner_gates": _gate_json(added.owner_gates),
        },
        lines=(
            f"added {added.evidence_id} to drafts/{added.draft_name} "
            f"({added.capture_kind} capture"
            f"{'' if added.blob_digest is None else f', blob {added.blob_outcome}'})",
            *_gate_lines(added.owner_gates),
        ),
    )
    _emit(
        "add-evidence",
        _with_revalidation(root, draft, outcome),
        rendered,
        as_json=json_output,
    )


@profile_bundle_app.command("resolve-conflict")
def resolve_conflict(
    ctx: typer.Context,
    draft: str = DRAFT_OPTION,
    ruling_file: Path = typer.Option(  # noqa: B008
        ...,
        "--ruling-file",
        exists=True,
        dir_okay=False,
        readable=True,
        help="A strict owner ruling record, as YAML.",
    ),
    bundle: Path | None = BUNDLE_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Append one owner ruling to a draft and update only the group it rules on."""
    root = _bundle_root(ctx, bundle)
    outcome = _guarded(
        lambda: authoring.resolve_conflict(
            root, draft_name=draft, ruling_document=ruling_file.read_bytes()
        )
    )
    ruled = outcome.value
    if ruled is None:
        _emit("resolve-conflict", outcome, _nothing(), as_json=json_output)
    rendered = _Rendered(
        result={
            "draft": ruled.draft_name,
            "ruling_id": ruled.ruling_id,
            "conflict_id": ruled.conflict_id,
            "conflict_state": ruled.conflict_state.value,
            "owner_gates": _gate_json(ruled.owner_gates),
        },
        lines=(
            f"appended {ruled.ruling_id}; {ruled.conflict_id} is now "
            f"{ruled.conflict_state.value}",
            *_gate_lines(ruled.owner_gates),
        ),
    )
    _emit(
        "resolve-conflict",
        _with_revalidation(root, draft, outcome),
        rendered,
        as_json=json_output,
    )


def _with_revalidation(
    bundle_root: Path, draft: str, outcome: OperationOutcome[_T]
) -> OperationOutcome[_T]:
    """§19 step 6: an authoring command ends by revalidating the draft it changed.

    The validation's findings join the command's own, so one exit code answers "did the change land
    and is the draft still promotable". Run here rather than inside `authoring` so there is one
    definition of how a draft's parent is resolved, and it is the one `validate` uses.
    """
    tree = draft_root(bundle_root, draft)
    revalidated = _guarded(
        lambda: validate_bundle(
            tree,
            bundle_root=bundle_root,
            mode="draft",
            parent=_parent_snapshot(bundle_root, tree, "draft"),
        )
    )
    return outcome_with(outcome.value, (*outcome.diagnostics, *revalidated.diagnostics))


# --------------------------------------------------------------------------------------
# Approval: the one operator interaction in the family
# --------------------------------------------------------------------------------------


class ApprovalTerminal(Protocol):
    """The seam between the approval decision and the person making it.

    Exactly one implementation exists in production, and this protocol is the only thing a test
    replaces. Everything else on the approval path — the candidate digest, the derived decisions,
    the stamp, the bytes and where they land — is the production code, so a test cannot approve
    anything by a route a script could not also take.
    """

    def is_controlling(self) -> bool: ...

    def show(self, text: str) -> None: ...

    def ask(self, prompt: str) -> str: ...


@dataclass(frozen=True)
class _StandardTerminal:
    def is_controlling(self) -> bool:
        return sys.stdin.isatty() and sys.stdout.isatty()

    def show(self, text: str) -> None:
        typer.echo(text)

    def ask(self, prompt: str) -> str:
        return str(typer.prompt(prompt, default="", show_default=False))


def approval_terminal() -> ApprovalTerminal:
    """The production terminal. There is no second way to reach the stamp writer."""
    return _StandardTerminal()


@dataclass(frozen=True)
class _Approval:
    candidate_digest: str
    stamp_id: str
    decisions: tuple[ApprovalDecision, ...]


@profile_bundle_app.command("approve")
def approve(
    ctx: typer.Context,
    draft: str = DRAFT_OPTION,
    bundle: Path | None = BUNDLE_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Record the owner's approval of a draft's exact content, on a controlling terminal.

    There is no `--yes`, no environment variable and no piped answer. §13 is explicit that this is
    an operator-interaction seam rather than access control: any process with write permission can
    construct a stamp file. What makes the approval mean something is that it is bound to one
    candidate digest and is reviewable, not that Boardwatch can tell a person from a script.
    """
    root = _bundle_root(ctx, bundle)
    outcome = _guarded(lambda: _approve(root, draft, terminal=approval_terminal()))
    approval = outcome.value
    rendered = (
        _nothing()
        if approval is None
        else _Rendered(
            result={
                "candidate_digest": approval.candidate_digest,
                "approval_stamp_id": approval.stamp_id,
                "owner_gates": _gate_json(approval.decisions),
            },
            lines=(
                f"approved candidate {approval.candidate_digest}",
                f"stamp: {approval.stamp_id}",
                *_gate_lines(approval.decisions),
            ),
        )
    )
    _emit("approve", outcome, rendered, as_json=json_output)


def _approve(bundle_root: Path, draft: str, *, terminal: ApprovalTerminal) -> (
    OperationOutcome[_Approval]
):
    # Before anything is read: the refusal is about how this process was started, not about the
    # bundle, and a piped caller must get the same answer whatever state the bundle is in.
    if not terminal.is_controlling():
        return outcome_with(
            None,
            (
                diagnostic(
                    IssueCode.APPROVAL_REQUIRES_CONTROLLING_TTY,
                    "approve needs a controlling terminal on both stdin and stdout. There is no "
                    "--yes and no environment override: the owner is asked, or nothing is "
                    "approved. Run it yourself in a terminal",
                ),
            ),
        )

    tree = draft_root(bundle_root, draft)
    if not tree.is_dir():
        return _refusal(
            IssueCode.DRAFT_NOT_FOUND, f"drafts/{draft} does not exist; there is nothing to approve"
        )
    try:
        documents = load_documents(tree, mode="draft")
    except ProfileBundleError as exc:
        # The draft's own parse failures, reported as themselves. Letting them reach `_guarded`
        # would turn "this document will not parse" into "please file a bug".
        return outcome_with(None, parse_error_diagnostics(exc))
    manifest = documents.manifest
    if not isinstance(manifest, DraftManifest):
        return _refusal(
            IssueCode.DRAFT_MANIFEST_INVALID,
            f"drafts/{draft} holds a revision manifest; only a draft can be approved",
        )

    try:
        selection = _selected(bundle_root)
    except SelectionError as exc:
        # Every selection failure except "no revision yet" is a bundle whose selected revision
        # cannot be resolved, and it carries its own typed code. `_selected` folds only that one
        # case into `None`.
        return outcome_with(None, (diagnostic(exc.code, str(exc)),))
    selected_digest = None if selection is None else selection.bundle_digest
    if manifest.parent_bundle_digest != selected_digest:
        # Refused rather than stamped: the candidate digest a stale draft produces is one no
        # promotion will ever look for, so the stamp would be a file with no drain. `rebase-draft`
        # is the way forward, and it changes the digest — which is what makes the old stamp stale.
        return _refusal(
            IssueCode.STALE_DRAFT_PARENT,
            f"drafts/{draft} was checked out of "
            f"{manifest.parent_bundle_digest or 'no revision'} but this bundle now selects "
            f"{selected_digest or 'no revision'}; rebase-draft moves it onto the current one",
        )

    try:
        parent_documents = None if selection is None else selected_documents(selection)
    except SelectionError as exc:
        return outcome_with(None, (diagnostic(exc.code, str(exc)),))
    except ProfileBundleError as exc:
        return outcome_with(None, parse_error_diagnostics(exc))
    envelope = None
    if parent_documents is not None:
        parent_manifest = parent_documents.manifest
        if not isinstance(parent_manifest, RevisionManifest):  # pragma: no cover - refused above
            return _refusal(
                IssueCode.DRAFT_MANIFEST_INVALID,
                "the selected revision does not carry a revision manifest",
            )
        envelope = parent_manifest.envelope

    quarantine = _quarantine(bundle_root, documents)
    if quarantine:
        return outcome_with(None, quarantine)

    candidate = candidate_content_digest(
        documents, FilesystemBlobReader(blobs_dir(bundle_root)), envelope
    )
    decisions = required_approval_decisions(documents, parent_documents)
    revision = 1 if selection is None else selection.revision + 1

    terminal.show(_prompt_text(draft, candidate, decisions))
    if terminal.ask(f"Type {CONFIRMATION_WORD!r} to approve") != CONFIRMATION_WORD:
        return _refusal(
            IssueCode.APPROVAL_DECLINED,
            "the confirmation did not match, so nothing was approved and nothing was written",
        )

    stamp = build_approval_stamp(
        stamp_id=f"approval-stamp.{revision:06d}",
        candidate_digest=candidate,
        approved_at=datetime.now(UTC),
        decisions=decisions,
    )
    path = approval_path(bundle_root, candidate)
    written = _write_stamp(
        bundle_root,
        path,
        approval_stamp_bytes(stamp, logical_path=PurePosixPath(f"approvals/{path.name}")),
    )
    if written is not None:
        return outcome_with(None, (written,))
    return OperationOutcome.clean(
        _Approval(
            candidate_digest=candidate,
            stamp_id=stamp.approval_stamp_id,
            decisions=decisions,
        )
    )


def _quarantine(bundle_root: Path, documents: BundleDocuments) -> tuple[Diagnostic, ...]:
    """A capture the draft names that the store cannot produce intact.

    Approving one would bind the owner's decision to bytes nobody can read back, and the candidate
    digest could not be computed from them anyway. Reported here rather than left to the digest
    computation because `MissingBlobError` escaping as an exception is the shape §21 has no exit
    code for.
    """
    try:
        referenced = referenced_blob_digests(documents)
    except ProfileBundleError as exc:
        return parse_error_diagnostics(exc)
    return tuple(
        diagnostic(
            IssueCode.CORRUPT_BLOB_QUARANTINE,
            f"the draft cites blob sha256:{declared}, which this bundle cannot produce intact "
            f"({reason.value}); recapture the evidence before approving",
            path="evidence/records.yaml",
            tier="error",
            blob=declared,
            reason=reason.value,
        )
        for declared, reason in quarantined_blobs(bundle_root, referenced)
    )


def _prompt_text(
    draft: str, candidate: str, decisions: Sequence[ApprovalDecision]
) -> str:
    """What the owner reads before answering.

    The decisions arrive already ordered by `required_approval_decisions` — by action then target —
    and are printed in that order rather than re-sorted here, so the list the owner approves is the
    list the stamp records.
    """
    lines = [
        f"Approving drafts/{draft}.",
        f"Candidate content digest: {candidate}",
        "",
    ]
    if decisions:
        lines.append(f"{len(decisions)} owner-gated transition(s) in this candidate:")
        lines.extend(
            f"  {decision.action.value} {decision.target_record_id} -> {decision.resulting_state}"
            for decision in decisions
        )
    else:
        lines.append(
            "No additional owner-gated transitions; the stamp authorises the candidate itself."
        )
    lines.append("")
    return "\n".join(lines)


def _write_stamp(bundle_root: Path, path: Path, raw: bytes) -> Diagnostic | None:
    """File the stamp atomically. `None` means it landed."""
    logical = f"approvals/{path.name}"
    try:
        approvals_dir(bundle_root).mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".tmp-approval-")
        staged = Path(temporary)
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(staged, path)
        except BaseException:
            staged.unlink(missing_ok=True)
            raise
    except OSError as exc:
        return diagnostic(
            IssueCode.IO_ERROR,
            f"{logical} could not be written: {io_reason(exc)}",
            path=logical,
        )
    return None


# --------------------------------------------------------------------------------------
# Promotion
# --------------------------------------------------------------------------------------


@profile_bundle_app.command("promote")
def promote(
    ctx: typer.Context,
    draft: str = DRAFT_OPTION,
    summary: str = typer.Option(  # noqa: B008
        ..., "--summary", help="What this revision changes, for the change ledger."
    ),
    actor: Actor = typer.Option(  # noqa: B008
        Actor.OWNER, "--actor", help="Who is proposing the change."
    ),
    bundle: Path | None = BUNDLE_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Promote an approved draft into the next immutable revision and select it."""
    root = _bundle_root(ctx, bundle)
    request = promotion.PromotionRequest(
        draft_name=draft,
        summary=summary,
        actor=actor,
        # The package reads no clock on purpose: a revision's timestamp is part of its identity.
        created_at=datetime.now(UTC),
    )
    outcome = _guarded(lambda: promotion.promote(root, request))
    selected = outcome.value
    rendered = (
        _nothing()
        if selected is None
        else _Rendered(
            result={
                "revision": selected.revision,
                "bundle_digest": selected.bundle_digest,
            },
            lines=(
                f"promoted revision {selected.revision}",
                f"bundle digest: {selected.bundle_digest}",
            ),
        )
    )
    _emit("promote", outcome, rendered, as_json=json_output)


__all__ = ["ApprovalTerminal", "approval_terminal", "profile_bundle_app"]
