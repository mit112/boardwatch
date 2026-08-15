"""`boardwatch profile-bundle`: the commands design §7 and §19 name, plus `approve-projection`
(Task 10) and `project` (Task 18) — both defined in `cli/projection_cmd.py` and registered here by
function reference — and `import`, which gives Gate A's enumerators the entry point §16 left them
without. Deliberately not counted here: a number in a docstring goes stale the next time the group
grows, and no test can pin it.

This module is a **translation**, and deliberately nothing else. Every decision about the bundle is
made under `boardwatch.profile_bundle`; what lives here is argument parsing, the two renderings,
and the exit code. The one exception is the approval *question*, which is an operator interaction
and has nowhere else to live — everything else about an approval, including the candidate digest
and the stamp, is `authoring`'s, because the digest is computed with the bundle's private
serializer and `test_profile_bundle_hash_isolation` keeps that one-directional.

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

Design §19 shows the flag on three commands — `validate`, `inventory`, `conflicts`; `inspect` is
listed with no flag at all — because those are the ones an agent reads back. But §21's exit
contract covers the whole family, and its exit-1 and exit-3 rows — `stale_draft_parent`,
`bundle_lock_held`, `promotion_target_conflict` — only ever arise in `promote`, `rebase-draft` and
`approve`. A machine surface on three commands would leave the exit contract's most consequential
rows with no machine rendering at all.

Both T18 review lenses ruled the uniform envelope right and §19's list under-specified: §19 opens
"The **proposed** command surface is", while §21 is normative and explicitly family-wide. T19 owns
amending §19 to show `[--json]` family-wide, along with `--deep-history`, which §7 names and §19
gives no surface.

**One documented exception.** `approve-projection` ships without `--json` — a deliberate choice,
not an oversight: it is a live terminal question-and-answer (the owner types the confirmation word
back), and no JSON schema for that exchange was ever specified, so adding one would have been
unrequested configurability rather than filling a gap. `project`, this family's other new command,
is a reporting command like `inspect`/`inventory` and carries the full envelope.
"""

from __future__ import annotations

import json

# `sys` is not read anywhere below: `_StandardTerminal.is_controlling` now lives in
# `cli/_approval.py`. The import stays so `monkeypatch.setattr(profile_bundle_cmd.sys, "stdin", …)`
# (`tests/profile_bundle/test_profile_bundle_cli_approval.py`) still finds a `sys` attribute here —
# it patches the one shared `sys` module, which `_approval.py`'s `sys.stdin`/`sys.stdout` reads too.
import sys  # noqa: F401
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Final, NoReturn, TypeVar

import typer

from boardwatch.cli import projection_cmd
from boardwatch.cli._approval import (
    CONFIRMATION_WORD,
    ApprovalTerminal,
    _StandardTerminal,  # noqa: F401 -- see `import sys` above: same test-attribute seam
    approval_terminal,
)
from boardwatch.core.settings import load_settings
from boardwatch.profile_bundle import authoring, drafts, inspection, migrations, promotion, rebase
from boardwatch.profile_bundle.approvals import ApprovalDecision
from boardwatch.profile_bundle.errors import (
    BundleIoError,
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
from boardwatch.profile_bundle.models.base import (
    Surface,
    UsageContext,
    VerificationBasis,
    VerificationState,
)
from boardwatch.profile_bundle.models.history import Actor
from boardwatch.profile_bundle.models.manifests import RevisionManifest
from boardwatch.profile_bundle.paths import (
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
)
from boardwatch.profile_bundle.validation import (
    ParentSnapshot,
    load_documents,
    validate_bundle,
)

#: The draft `init` and `checkout` create when the operator names none. The option is optional in
#: §19's surface, so a default has to live somewhere, and the command layer is where a default that
#: is purely a convenience belongs.
DEFAULT_DRAFT_NAME: Final = "baseline"

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
        typer.echo(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
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


#: What `_guarded` says happened when the call it wrapped could not complete. Every library entry
#: point checks before it writes and stages what it does write, so the default is true of a
#: command's own work. It is NOT true of the two calls that run *after* one has committed — §19
#: step 6's revalidation and `promote`'s read-back — and an unconditional "nothing was written"
#: above a populated result is the command contradicting itself.
_NOTHING_WRITTEN: Final = "the command could not complete; nothing was written"
_AFTER_THE_WRITE: Final = "the change was written, but the draft could not be re-checked"
_AFTER_PROMOTION: Final = (
    "the revision was promoted and selected, but its manifest could not be read back"
)


def _guarded(
    call: Callable[[], OperationOutcome[_T]],
    *,
    unable: str = _NOTHING_WRITTEN,
    after_write: bool = False,
) -> OperationOutcome[_T]:
    """Run one library call, turning a typed escape into §21's could-not-complete.

    `ProfileBundleError` is the package's own base class, so this catches exactly the failures it
    declares and nothing else — a bare `except Exception` here would swallow a genuine defect in
    this file and report it as an unreadable bundle. The exception's message is deliberately not
    printed: some of them are built from a stringified `OSError`, which carries an absolute path.

    `after_write=True` is for the guards that run once a change is already durable, where
    `IO_ERROR`/`INTERNAL_ERROR` would be the wrong *type* and not merely the wrong wording: both are
    members of `COULD_NOT_COMPLETE_CODES`, so an automated caller reads exit 3, concludes nothing
    happened, and retries into `duplicate_record_id`. Putting that distinction only in `unable`'s
    prose left the one thing a consumer can branch on still saying the opposite, which is the
    string-matching this package refuses to do anywhere else. `details.cause` keeps the kind the
    original code would have carried.
    """
    try:
        return call()
    except BundleIoError as exc:
        # A `ProfileBundleError` whose cause is I/O, so it must not be reported as a defect and its
        # `cause` must not say `internal`. Caught ahead of the base class because `except` order is
        # the only thing that separates them, and the two arms disagree about what the operator
        # should do: one is theirs to fix, the other is ours.
        #
        # Its own message is deliberately NOT interpolated — it is built from `str(OSError)`, which
        # appends the absolute path it hit. The reason is recovered from the chained exception
        # instead, where `io_reason` renders the strerror alone: "Permission denied" tells an
        # operator this is theirs to fix, and dropping it left the file case saying strictly less
        # than the directory case for the same underlying errno.
        reason = io_reason(exc.__cause__) if isinstance(exc.__cause__, OSError) else None
        io_message = f"{unable}: the bundle could not be read or written"
        if reason is not None:
            io_message = f"{io_message} ({reason})"
        if after_write:
            return outcome_with(
                None, (diagnostic(IssueCode.RECHECK_UNAVAILABLE, io_message, cause="io"),)
            )
        return outcome_with(None, (diagnostic(IssueCode.IO_ERROR, io_message),))
    except ProfileBundleError as exc:
        message = (
            f"{unable}. This is a defect — please report the error type below with what you ran"
        )
        if after_write:
            return outcome_with(
                None,
                (
                    diagnostic(
                        IssueCode.RECHECK_UNAVAILABLE,
                        message,
                        error_type=type(exc).__name__,
                        cause="internal",
                    ),
                ),
            )
        return outcome_with(
            None,
            (diagnostic(IssueCode.INTERNAL_ERROR, message, error_type=type(exc).__name__),),
        )
    except OSError as exc:
        reason = f"{unable}: {io_reason(exc)}"
        if after_write:
            return outcome_with(
                None, (diagnostic(IssueCode.RECHECK_UNAVAILABLE, reason, cause="io"),)
            )
        return outcome_with(None, (diagnostic(IssueCode.IO_ERROR, reason),))


# --------------------------------------------------------------------------------------
# Shared resolution
# --------------------------------------------------------------------------------------


def _bundle_root(ctx: typer.Context, override: Path | None) -> Path:
    """`--bundle`, else `config_dir / "career-profile"`.

    `load_settings` reads `config.toml` and creates nothing; `build_context` would create the data
    directory and the database, which no bundle command needs.
    """
    return resolve_bundle_root(load_settings(data_dir=ctx.obj).config_dir, override)


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
        located = _guarded(lambda: _draft_tree(root, draft))
        if located.value is None:
            _emit("validate", located, _nothing(), as_json=json_output)
        tree = located.value
        mode = "draft"
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


def _draft_tree(bundle_root: Path, draft: str) -> OperationOutcome[Path]:
    """The named draft's directory, or the typed refusal that says there is none.

    Called through `_guarded` rather than inline, because `Path.is_dir()` re-raises every `OSError`
    that is not "it does not exist": an unreadable `drafts/` arrives here as a `PermissionError`,
    and one escaping this layer would be a raw traceback carrying the operator's absolute path, at
    exit 1 where §21 requires 3, and with no JSON at all under `--json`. `draft_root` cannot raise
    here — `_existing_draft` already applied the segment grammar it checks — so the `OSError` arm is
    the whole reason this is a function.
    """
    # `validate --draft` is a reading surface that reaches no function confining the root, so it
    # needs the root's own answer before the draft's (D-138).
    if not bundle_root.is_dir():
        return _refusal(
            IssueCode.BUNDLE_NOT_FOUND,
            "there is no bundle at this path, so there is no draft to validate; `init` creates "
            "one, and --bundle names an existing one somewhere else",
        )
    tree = draft_root(bundle_root, draft)
    if not tree.is_dir():
        return _refusal(
            IssueCode.DRAFT_NOT_FOUND, f"drafts/{draft} does not exist; nothing to validate"
        )
    return OperationOutcome.clean(tree)


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
            f"  {decision.action.value} {decision.target_record_id} -> {decision.resulting_state}"
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
            "cited_back": list(added.cited_back),
        },
        lines=(
            f"added {added.evidence_id} to drafts/{added.draft_name} "
            f"({added.capture_kind} capture"
            f"{'' if added.blob_digest is None else f', blob {added.blob_outcome}'})",
            *((f"cited back from: {', '.join(added.cited_back)}",) if added.cited_back else ()),
            *_gate_lines(added.owner_gates),
        ),
    )
    _emit(
        "add-evidence",
        _with_revalidation(root, draft, outcome),
        rendered,
        as_json=json_output,
    )


@profile_bundle_app.command("import")
def import_source(
    ctx: typer.Context,
    draft: str = DRAFT_OPTION,
    source: str = typer.Option(  # noqa: B008
        ..., "--source", help="The source ID, as declared in policy/sources.yaml."
    ),
    from_path: Path | None = typer.Option(  # noqa: B008
        None,
        "--from",
        exists=True,
        dir_okay=False,
        readable=True,
        help="The source document (default: resolved through local-sources.yaml).",
    ),
    bundle: Path | None = BUNDLE_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Enumerate one approved source into a draft's import ledger, then revalidate it."""
    root = _bundle_root(ctx, bundle)
    outcome = _guarded(
        lambda: authoring.import_source(
            root,
            draft_name=draft,
            source_id=source,
            source_bytes=None if from_path is None else from_path.read_bytes(),
        )
    )
    imported = outcome.value
    if imported is None:
        _emit("import", outcome, _nothing(), as_json=json_output)
    counts = imported.counts
    rendered = _Rendered(
        result={
            "draft": imported.draft_name,
            "source_id": imported.source_id,
            "enumerator_id": imported.enumerator_id,
            "source_content_digest": imported.source_content_digest,
            "record_count": imported.record_count,
            "counts_by_disposition": dict(counts),
            "denominator": imported.denominator,
            "changed": imported.changed,
        },
        lines=(
            f"{'enumerated' if imported.changed else 'unchanged'}: {imported.source_id} "
            f"contributes {imported.record_count} record(s) to drafts/{imported.draft_name} "
            f"({imported.denominator} in the ledger)",
            "  " + ", ".join(f"{name}: {count}" for name, count in sorted(counts.items())),
        ),
    )
    _emit("import", _with_revalidation(root, draft, outcome), rendered, as_json=json_output)


@profile_bundle_app.command("extract")
def extract(
    ctx: typer.Context,
    draft: str = DRAFT_OPTION,
    source: str = typer.Option(  # noqa: B008
        ..., "--source", help="The source ID to extract, as declared in policy/sources.yaml."
    ),
    from_path: Path | None = typer.Option(  # noqa: B008
        None,
        "--from",
        exists=True,
        dir_okay=False,
        readable=True,
        help="The source document (default: resolved through local-sources.yaml).",
    ),
    bundle: Path | None = BUNDLE_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Deterministically extract one source's candidates, re-deriving its ledger and report."""
    root = _bundle_root(ctx, bundle)
    outcome = _guarded(
        lambda: authoring.extract_source(
            root,
            draft_name=draft,
            source_id=source,
            source_bytes=None if from_path is None else from_path.read_bytes(),
        )
    )
    extracted = outcome.value
    if extracted is None:
        _emit("extract", outcome, _nothing(), as_json=json_output)
    counts = extracted.counts
    reasons = extracted.report_reasons
    rendered = _Rendered(
        result={
            "draft": extracted.draft_name,
            "source_id": extracted.source_id,
            "enumerator_id": extracted.enumerator_id,
            "source_content_digest": extracted.source_content_digest,
            "record_count": extracted.record_count,
            "counts_by_disposition": dict(counts),
            "report_reasons": dict(reasons),
            "denominator": extracted.denominator,
            "changed": extracted.changed,
        },
        lines=(
            f"{'extracted' if extracted.changed else 'unchanged'}: {extracted.source_id} "
            f"contributes {extracted.record_count} record(s) to drafts/{extracted.draft_name} "
            f"({extracted.denominator} in the ledger)",
            "  " + ", ".join(f"{name}: {count}" for name, count in sorted(counts.items())),
            "  review reasons: "
            + (
                ", ".join(f"{name}: {count}" for name, count in sorted(reasons.items()) if count)
                or "none"
            ),
        ),
    )
    _emit("extract", _with_revalidation(root, draft, outcome), rendered, as_json=json_output)


@profile_bundle_app.command("promote-candidates")
def promote_candidates(
    ctx: typer.Context,
    draft: str = DRAFT_OPTION,
    source: str = typer.Option(  # noqa: B008
        ..., "--source", help="The source ID whose imported candidates to promote."
    ),
    from_path: Path | None = typer.Option(  # noqa: B008
        None,
        "--from",
        exists=True,
        dir_okay=False,
        readable=True,
        help="The source document (default: resolved through local-sources.yaml).",
    ),
    bundle: Path | None = BUNDLE_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Promote one source's imported candidates into entities, facts, and grounded skills (§6.8).

    Deterministic and owner-mediated: facts are born `unresolved` with no fabricated evidence, and a
    skill is created only where a bullet's `tech_tags` grounds it to an entity. One-shot: it refuses
    if the draft already holds promoted entities or skills.
    """
    root = _bundle_root(ctx, bundle)
    outcome = _guarded(
        lambda: authoring.promote_candidates(
            root,
            draft_name=draft,
            source_id=source,
            source_bytes=None if from_path is None else from_path.read_bytes(),
            as_of=date.today(),
        )
    )
    promoted = outcome.value
    if promoted is None:
        _emit("promote-candidates", outcome, _nothing(), as_json=json_output)
    rendered = _Rendered(
        result={
            "draft": promoted.draft_name,
            "source_id": promoted.source_id,
            "entity_count": promoted.entity_count,
            "fact_count": promoted.fact_count,
            "skill_count": promoted.skill_count,
            "category_count": promoted.category_count,
            "changed": promoted.changed,
        },
        lines=(
            f"{'promoted' if promoted.changed else 'unchanged'}: {promoted.source_id} -> "
            f"{promoted.entity_count} entit(y/ies), {promoted.fact_count} fact(s), "
            f"{promoted.skill_count} skill(s) in drafts/{promoted.draft_name}",
            "  facts are born unresolved; confirm, attest, and approve them to promote and render",
        ),
    )
    _emit(
        "promote-candidates",
        _with_revalidation(root, draft, outcome),
        rendered,
        as_json=json_output,
    )


@profile_bundle_app.command("edit-fact")
def edit_fact(
    ctx: typer.Context,
    draft: str = DRAFT_OPTION,
    fact_id: str = typer.Option(  # noqa: B008
        ..., "--fact-id", help="The fact to correct. `inspect` shows one and what cites it."
    ),
    value: str = typer.Option(  # noqa: B008
        ..., "--value", help="The corrected wording."
    ),
    bundle: Path | None = BUNDLE_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Correct one fact by filing a successor that supersedes it, then revalidate the draft."""
    root = _bundle_root(ctx, bundle)
    outcome = _guarded(
        lambda: authoring.edit_fact(
            root,
            draft_name=draft,
            fact_id=fact_id,
            value=value,
            as_of=date.today(),
        )
    )
    edited = outcome.value
    if edited is None:
        _emit("edit-fact", outcome, _nothing(), as_json=json_output)
    rendered = _Rendered(
        result={
            "draft": edited.draft_name,
            "fact_id": edited.fact_id,
            "successor_fact_id": edited.successor_fact_id,
            "document": edited.document,
            "owner_gates": _gate_json(edited.owner_gates),
        },
        lines=(
            f"{edited.successor_fact_id} supersedes {edited.fact_id} in {edited.document}",
            *_gate_lines(edited.owner_gates),
        ),
    )
    _emit("edit-fact", _with_revalidation(root, draft, outcome), rendered, as_json=json_output)


@profile_bundle_app.command("add-fact")
def add_fact(
    ctx: typer.Context,
    draft: str = DRAFT_OPTION,
    fact_id: str = typer.Option(..., "--fact-id", help="The new fact's identifier."),  # noqa: B008
    subject_id: str = typer.Option(  # noqa: B008
        ..., "--subject-id", help="The entity the fact is about."
    ),
    predicate: str = typer.Option(  # noqa: B008
        ..., "--predicate", help="The predicate, as declared in policy/predicates.yaml."
    ),
    value: str = typer.Option(..., "--value", help="The fact's wording."),  # noqa: B008
    evidence_id: str = typer.Option(  # noqa: B008
        ..., "--evidence-id", help="The evidence record supporting it, already in the draft."
    ),
    # No defaults, deliberately: these two say how strongly the bundle believes the fact, and a
    # default would assert it on the owner's behalf every time a caller left them out.
    verification_state: VerificationState = typer.Option(  # noqa: B008
        ..., "--verification-state", help="How settled the fact is."
    ),
    verification_basis: VerificationBasis = typer.Option(  # noqa: B008
        ..., "--verification-basis", help="How it was established."
    ),
    usage_context: UsageContext = typer.Option(  # noqa: B008
        ..., "--usage-context", help="How the subject encountered the material."
    ),
    surface: list[Surface] = typer.Option(  # noqa: B008
        ..., "--surface", help="A surface the fact may reach. Repeat for more than one."
    ),
    bundle: Path | None = BUNDLE_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Write one new fact into the document owning its subject, then revalidate the draft."""
    root = _bundle_root(ctx, bundle)
    outcome = _guarded(
        lambda: authoring.add_fact(
            root,
            draft_name=draft,
            fact_id=fact_id,
            subject_id=subject_id,
            predicate=predicate,
            value=value,
            evidence_id=evidence_id,
            verification_state=verification_state.value,
            verification_basis=verification_basis.value,
            usage_context=usage_context.value,
            surfaces=[item.value for item in surface],
            as_of=date.today(),
        )
    )
    added = outcome.value
    if added is None:
        _emit("add-fact", outcome, _nothing(), as_json=json_output)
    rendered = _Rendered(
        result={
            "draft": added.draft_name,
            "fact_id": added.fact_id,
            "document": added.document,
            "owner_gates": _gate_json(added.owner_gates),
        },
        lines=(
            f"added {added.fact_id} to {added.document}",
            *_gate_lines(added.owner_gates),
        ),
    )
    _emit("add-fact", _with_revalidation(root, draft, outcome), rendered, as_json=json_output)


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
            f"appended {ruled.ruling_id}; {ruled.conflict_id} is now {ruled.conflict_state.value}",
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

    Only reached once the write has landed — both callers emit the refusal themselves when the
    authoring step produced no value — which is why the composition is
    `OperationOutcome.from_diagnostics` and not `errors.outcome_with`. `outcome_with`'s
    could-not-complete precedence is right for a command's own work: a run that could not read the
    bundle has not found one error, it has found nothing at all. It is wrong here. Exit 3 tells an
    automated caller that nothing happened and it may retry, and the retry lands on
    `duplicate_record_id` against the record this command already committed. The diagnostic still
    names the I/O failure; the envelope's `outcome` says what happened to the draft, which is what
    §21 means by carrying the category explicitly.

    **Which could-not-complete code the override actually serves, since guessing it wrong is easy.**
    The guard's own failures are typed `RECHECK_UNAVAILABLE`, so they no longer rely on this at all.
    What is left is a code `validate_bundle` itself emits that happens to be a member of
    `COULD_NOT_COMPLETE_CODES`: `unsupported_secret_scan_ruleset_version`, from
    `validation/evidence.py`, which a draft revalidation does reach. Exit 1 is right for it — the
    recheck *ran* and reported a real finding about a draft that really changed, which is not
    "nothing happened". It is **not** `unsupported_schema_version`: `authoring._load` refuses an
    unsupported schema before either write, so that code cannot arrive here, and an earlier version
    of this reasoning naming it was wrong.
    """
    tree = draft_root(bundle_root, draft)
    revalidated = _guarded(
        lambda: validate_bundle(
            tree,
            bundle_root=bundle_root,
            mode="draft",
            parent=_parent_snapshot(bundle_root, tree, "draft"),
        ),
        unable=_AFTER_THE_WRITE,
        after_write=True,
    )
    return OperationOutcome.from_diagnostics(
        outcome.value, (*outcome.diagnostics, *revalidated.diagnostics)
    )


# --------------------------------------------------------------------------------------
# Approval: the one operator interaction in the family
# --------------------------------------------------------------------------------------


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
    filed = outcome.value
    rendered = (
        _nothing()
        if filed is None
        else _Rendered(
            result={
                "candidate_digest": filed.candidate_digest,
                "approval_stamp_id": filed.stamp_id,
                "owner_gates": _gate_json(filed.decisions),
            },
            lines=(
                f"approved candidate {filed.candidate_digest}",
                f"stamp: {filed.stamp_id}",
                *_gate_lines(filed.decisions),
            ),
        )
    )
    _emit("approve", outcome, rendered, as_json=json_output)


def _approve(
    bundle_root: Path, draft: str, *, terminal: ApprovalTerminal
) -> OperationOutcome[authoring.FiledApproval]:
    """Ask, then file. Everything about the bundle is `authoring`'s; the question is this layer's.

    The terminal is consulted first, before anything is read: the refusal is about how this process
    was started rather than about the bundle, so a piped caller gets the same answer whatever state
    the bundle is in.
    """
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

    proposed = authoring.approval_candidate(bundle_root, draft_name=draft)
    candidate = proposed.value
    if candidate is None:
        return outcome_with(None, proposed.diagnostics)

    terminal.show(_prompt_text(candidate))
    if terminal.ask(f"Type {CONFIRMATION_WORD!r} to approve") != CONFIRMATION_WORD:
        return _refusal(
            IssueCode.APPROVAL_DECLINED,
            "the confirmation did not match, so nothing was approved and nothing was written",
        )
    # The package reads no clock, so the moment the owner answered is this layer's to supply.
    return authoring.file_approval_stamp(
        bundle_root, candidate=candidate, approved_at=datetime.now(UTC)
    )


def _prompt_text(candidate: authoring.ApprovalCandidate) -> str:
    """What the owner reads before answering.

    The decisions arrive already ordered by `required_approval_decisions` — by action then target —
    and are printed in that order rather than re-sorted here, so the list the owner approves is the
    list the stamp records.
    """
    lines = [
        f"Approving drafts/{candidate.draft_name}.",
        f"Candidate content digest: {candidate.candidate_digest}",
        "",
    ]
    if candidate.decisions:
        lines.append(f"{len(candidate.decisions)} owner-gated transition(s) in this candidate:")
        lines.extend(
            f"  {decision.action.value} {decision.target_record_id} -> {decision.resulting_state}"
            for decision in candidate.decisions
        )
    else:
        lines.append(
            "No additional owner-gated transitions; the stamp authorises the candidate itself."
        )
    lines.append("")
    return "\n".join(lines)


# `approve-projection` is defined in `cli/projection_cmd.py`, not here, and registered by
# function reference rather than its own `@profile_bundle_app.command(...)` decorator — the same
# pattern `cli/app.py` uses for every command whose module it does not own (`app.command("scan")
# (_scan)`, etc.). It lives in its own module because it approves `{config_dir}/projection.yaml`,
# not the bundle, and `projection_cmd.py` must not import anything from this module (see that
# module's own docstring for why); this file may freely import it, since the dependency runs only
# one way.
profile_bundle_app.command("approve-projection")(projection_cmd.approve_projection)

# `project` is defined in `cli/projection_cmd.py` for the identical reason and registered the
# identical way: it serializes `{config_dir}/projection.yaml`'s Stage 1 pool, not the bundle
# itself, and the one-way import direction (this file imports `projection_cmd`, never the
# reverse) is what `projection_cmd.py`'s own module docstring holds itself to.
profile_bundle_app.command("project")(projection_cmd.project)


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
    if selected is None:
        _emit("promote", outcome, _nothing(), as_json=json_output)
    # Read back rather than reported from the value promotion returned: `SelectedRevision` carries
    # where the revision is and what it hashes to, by design, and counting the deliverable through
    # a different path than the one that produced it is the rule this project keeps paying for.
    read_back = _guarded(
        lambda: _promoted_manifest(selected), unable=_AFTER_PROMOTION, after_write=True
    )
    _emit(
        "promote",
        OperationOutcome.from_diagnostics(selected, (*outcome.diagnostics, *read_back.diagnostics)),
        _promotion_rendered(selected, read_back.value),
        as_json=json_output,
    )


def _promoted_manifest(selected: SelectedRevision) -> OperationOutcome[RevisionManifest]:
    """The manifest of the revision just written, read from the tree rather than from memory."""
    manifest = load_documents(selected.root, mode="revision").manifest
    if not isinstance(manifest, RevisionManifest):  # pragma: no cover
        # `promotion` builds a `RevisionManifest`, writes it, and re-verifies the tree's digest
        # from disk before `CURRENT` names it, so this narrowing is the type system's rather than a
        # second check on promotion's work.
        return _refusal(
            IssueCode.DRAFT_MANIFEST_INVALID,
            "the promoted revision does not carry a revision manifest",
        )
    return OperationOutcome.clean(manifest)


def _promotion_rendered(selected: SelectedRevision, manifest: RevisionManifest | None) -> _Rendered:
    """A promotion's answer, with the approval that authorised it.

    `promote` is the one irreversible success in the family, and CLAUDE.md's rule for a cleared
    result is that it carries its own evidence chain — here, which stamp, binding which candidate
    digest. §7 has promotion write both into the manifest and §13 makes that pair the authority for
    the revision, so reporting only the revision number left an operator to open `manifest.yaml`
    themselves to find out what cleared it.

    `None` when the manifest could not be read back, never `""`: the sentinels a *draft* uses for
    these two fields are empty strings, and reporting one here would say the revision was promoted
    without an approval rather than that this run could not read which.
    """
    stamp = None if manifest is None else manifest.approval_stamp_id
    candidate = None if manifest is None else manifest.approved_candidate_digest
    return _Rendered(
        result={
            "revision": selected.revision,
            "bundle_digest": selected.bundle_digest,
            "approval_stamp_id": stamp,
            "approved_candidate_digest": candidate,
        },
        lines=(
            f"promoted revision {selected.revision}",
            f"bundle digest: {selected.bundle_digest}",
            f"authorised by: {stamp or 'unread'} binding candidate {candidate or 'unread'}",
        ),
    )


__all__ = ["ApprovalTerminal", "approval_terminal", "profile_bundle_app"]
