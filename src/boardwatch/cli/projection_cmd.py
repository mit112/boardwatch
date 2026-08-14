"""`approve-projection`: a controlling terminal, or nothing is approved.

Registered onto `profile_bundle_app` by `cli/profile_bundle_cmd.py`, never the other way — that
module imports this one to register the command, so this module must not import anything back from
it. `CONFIRMATION_WORD` and `approval_terminal` come from `cli/_approval.py`, the shared leaf
module both command modules import; a leaf import satisfies the one-way registration direction
without duplicating the seam.

**No `--yes`, no environment variable and no piped answer.** The refusal is structural: there is
no code path in this module that reads an environment variable to decide whether to prompt, and
`approval_terminal()`'s `is_controlling()` is what a detached or redirected process actually
reaches.

The command shows the owner every declared entry's templated fields already resolved against the
bundle's CURRENT revision — `projection.pool.projection_candidate` — never the template source, so
approving means having seen the literal words a résumé would carry. That resolution needs no
existing approval: `projection_candidate` performs no owner-gate check, because it computes the
very thing the gate is checked against (see its own docstring in `projection/pool.py`).

**`projection.pool` is imported inside the command, not at module level, and this is load-bearing,
not style.** `profile_bundle_cmd.py`'s own docstring states "No database" as one of the three
rules it is answerable for, and `tests/profile_bundle/test_profile_bundle_cli.py`'s
`test_the_command_module_imports_no_store_module` enforces it structurally: importing
`profile_bundle_cmd` must not pull `boardwatch.store` into `sys.modules` at all, regardless of
whether anything is ever queried. `projection.pool` transitively reaches
`projection.shell` → `tailor.load` → `reports.resume_gate` → `tailor.plan` →
`extract.taxonomy` → `boardwatch.store.tables` — a pre-existing chain in already-shipped code
(Tasks 7 and 12), not something this task adds. Importing `projection_cmd` eagerly from
`profile_bundle_cmd.py` would drag that whole chain in at CLI-module-import time and break the
guard. `cli/app.py`'s `version()` command defers `from boardwatch.store.db import
schema_revision` the same way, for the identical reason — this is that codebase's own idiom for
it, not a new one.
"""

from __future__ import annotations

import json

# `sys` is not read anywhere below: `_StandardTerminal.is_controlling` lives in `cli/_approval.py`.
# The import stays so `monkeypatch.setattr(projection_cmd.sys, "stdin", …)`
# (`tests/projection/test_projection_cli_approval.py`) still finds a `sys` attribute here — it
# patches the one shared `sys` module, which `_approval.py`'s `sys.stdin`/`sys.stdout` reads too.
import sys  # noqa: F401
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn

import typer

from boardwatch.cli._approval import CONFIRMATION_WORD, approval_terminal
from boardwatch.core.settings import load_settings
from boardwatch.profile_bundle.errors import (
    Diagnostic,
    IssueCode,
    JsonValue,
    OperationOutcome,
    ProfileBundleError,
    diagnostic,
    outcome_with,
)
from boardwatch.profile_bundle.paths import resolve_bundle_root
from boardwatch.profile_bundle.reports import REPORT_SCHEMA, diagnostic_json, diagnostic_line
from boardwatch.projection.errors import ProjectionError, ProjectionIssue, raise_violation
from boardwatch.projection.stamp import read_stamp, write_stamp

if TYPE_CHECKING:
    # Type-only: `boardwatch.projection.pool` is imported for real inside `approve_projection`
    # and `project` themselves, never at module level. See the module docstring.
    from boardwatch.projection.errors import ProjectionViolation
    from boardwatch.projection.pool import ProjectionCandidate

DECLARATION_OPTION = typer.Option(  # noqa: B008
    None,
    "--declaration",
    help="Projection declaration path (default: <config dir>/projection.yaml).",
)
BUNDLE_OPTION = typer.Option(  # noqa: B008
    None, "--bundle", help="Bundle root (default: <config dir>/career-profile)."
)
JSON_OPTION = typer.Option(False, "--json", help="Emit the deterministic machine report.")  # noqa: B008
CHECK_OPTION = typer.Option(  # noqa: B008
    False,
    "--check",
    help=(
        "Also verify the owner's approval still covers the CURRENT bundle revision, not just "
        "the declaration; exits non-zero on drift."
    ),
)


def _prompt_text(candidate: ProjectionCandidate) -> str:
    """What the owner reads before answering: every declared entry's resolved template fields.

    Prints the resolved value from `candidate.entries` — never the raw template string from
    `projection.yaml` — so the owner approves the literal text a résumé would carry.
    """
    lines = [
        "Approving projection.yaml.",
        f"Projection digest: {candidate.projection_digest}",
        f"Bundle digest: {candidate.bundle_digest}",
        "",
    ]
    if candidate.entries:
        noun = "entry" if len(candidate.entries) == 1 else "entries"
        lines.append(f"{len(candidate.entries)} declared {noun} with resolved template values:")
        for entry in candidate.entries:
            lines.append(f"  {entry.entry_id}:")
            lines.append(f"    heading: {entry.heading}")
            if entry.title is not None:
                lines.append(f"    title: {entry.title}")
            if entry.subtitle is not None:
                lines.append(f"    subtitle: {entry.subtitle}")
            if entry.dates is not None:
                lines.append(f"    dates: {entry.dates}")
            if entry.location is not None:
                lines.append(f"    location: {entry.location}")
    else:
        lines.append("No entries declared; the stamp authorises the declaration itself.")
    lines.append("")
    return "\n".join(lines)


def approve_projection(
    ctx: typer.Context,
    declaration: Path | None = DECLARATION_OPTION,
    bundle: Path | None = BUNDLE_OPTION,
) -> None:
    """Record the owner's approval of `projection.yaml`'s exact resolved content, on a
    controlling terminal.

    Mirrors `profile-bundle approve` (`cli/profile_bundle_cmd.py:979-1051`): there is no `--yes`,
    no environment variable and no piped answer. §13's fail-safe direction applies identically —
    a run that cannot establish it has the owner's attention has not got it, so it refuses rather
    than assuming consent.
    """
    config_dir = load_settings(data_dir=ctx.obj).config_dir
    declaration_path = declaration if declaration is not None else config_dir / "projection.yaml"
    bundle_root = resolve_bundle_root(config_dir, bundle)
    terminal = approval_terminal()

    if not terminal.is_controlling():
        typer.echo(
            "approve-projection needs a controlling terminal on both stdin and stdout. There is "
            "no --yes and no environment override: the owner is asked, or nothing is approved. "
            "Run it yourself in a terminal",
            err=True,
        )
        raise typer.Exit(code=1)

    # Deferred: see the module docstring on why `projection.pool` is never imported at module
    # level here.
    from boardwatch.projection.pool import projection_candidate

    try:
        candidate = projection_candidate(bundle_root, declaration_path, as_of=date.today())
    except (ProjectionError, ProfileBundleError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    terminal.show(_prompt_text(candidate))
    if terminal.ask(f"Type {CONFIRMATION_WORD!r} to approve") != CONFIRMATION_WORD:
        typer.echo(
            "the confirmation did not match, so nothing was approved and nothing was written",
            err=True,
        )
        raise typer.Exit(code=1)

    path = write_stamp(
        config_dir,
        digest=candidate.projection_digest,
        bundle_digest=candidate.bundle_digest,
        approved_at=datetime.now(UTC),
    )
    typer.echo(f"approved projection {candidate.projection_digest}")
    typer.echo(f"stamp: {path}")


# --------------------------------------------------------------------------------------
# `project` — Stage 1 serialization for review
# --------------------------------------------------------------------------------------


def _projection_diagnostic(violation: ProjectionViolation) -> Diagnostic:
    """Fold one `ProjectionViolation` into the bundle family's `Diagnostic` shape (R27/R30).

    `ProjectionIssue` stays the authoritative catalog for projection's own business outcomes and
    is never taught into `profile_bundle.errors` member by member. `STALE_PROJECTION_APPROVAL`
    reuses the bundle's own `STALE_APPROVAL_STAMP`: the identical shape of failure — an approval's
    bound content diverged from what is current — just for `project --check`'s stamp rather than
    the bundle's own `ApprovalStamp`. Every other member funnels into the one new
    `PROJECTION_REFUSED` code; `details.projection_issue` carries the specific member so nothing
    is lost at the fold.

    `BUNDLE_UNREADABLE` is the one reachable member whose own message and `where`
    (`pool.py`'s `str(bundle_root)`) can carry an absolute filesystem path — this family's second
    rule forbids that in any diagnostic, so it gets a fixed, path-free message and no `where`
    instead. Every other reachable member's message and `where` are built only from ids, predicate
    names, digests, and bare filenames (`path.name`, never a full path) — confirmed by reading
    every `raise_violation` call in `declaration.py`, `contract.py`, and `grammar.py` that
    `project_pool` can reach.
    """
    code = (
        IssueCode.STALE_APPROVAL_STAMP
        if violation.issue is ProjectionIssue.STALE_PROJECTION_APPROVAL
        else IssueCode.PROJECTION_REFUSED
    )
    if violation.issue is ProjectionIssue.BUNDLE_UNREADABLE:
        message = "the bundle could not be read to produce a projection pool"
        where: str | None = None
    else:
        message = violation.message
        where = violation.where
    if where is not None:
        return diagnostic(code, message, projection_issue=str(violation.issue), where=where)
    return diagnostic(code, message, projection_issue=str(violation.issue))


def _boundary_outcome(exc: ProjectionError | ProfileBundleError) -> OperationOutcome[Any]:
    """The §21 outcome one refusal implies, at this command's boundary.

    `project_pool` never raises anything but `ProjectionError` (unlike `projection_candidate`,
    which this command does not call — see its own docstring on why), so the plain
    `ProfileBundleError` arm exists only for a `read_stamp` failure surviving past
    `project_pool`'s own `stamp_exists` gate — reported as an internal error rather than folded
    into `PROJECTION_REFUSED`, since it is not a projection business outcome at all.
    """
    if isinstance(exc, ProjectionError):
        finding = _projection_diagnostic(exc.violation)
    else:
        finding = diagnostic(IssueCode.INTERNAL_ERROR, str(exc), error_type=type(exc).__name__)
    return outcome_with(None, (finding,))


def _emit_project(
    outcome: OperationOutcome[Any],
    result: dict[str, JsonValue],
    lines: tuple[str, ...],
    *,
    as_json: bool,
    as_of: date,
) -> NoReturn:
    """Print `project`'s answer and exit with the code the library computed.

    Mirrors `profile_bundle_cmd._emit`'s envelope shape exactly (all seven keys), but is not that
    function: `projection_cmd.py` must not import back from `profile_bundle_cmd.py` (this module's
    own docstring), so the shared shape is repeated here rather than imported.
    """
    if as_json:
        payload: dict[str, JsonValue] = {
            "report_schema": REPORT_SCHEMA,
            "command": "project",
            "outcome": outcome.category,
            "exit_code": outcome.exit_code,
            "as_of": as_of.isoformat(),
            "result": result,
            "diagnostics": [diagnostic_json(finding) for finding in outcome.diagnostics],
        }
        typer.echo(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    else:
        out_lines = [
            f"profile-bundle project: {outcome.category}",
            f"as-of: {as_of.isoformat()}",
            *lines,
        ]
        out_lines.extend(diagnostic_line(finding) for finding in outcome.diagnostics)
        typer.echo("\n".join(out_lines))
    raise typer.Exit(code=outcome.exit_code)


def project(
    ctx: typer.Context,
    declaration: Path | None = DECLARATION_OPTION,
    bundle: Path | None = BUNDLE_OPTION,
    json_output: bool = JSON_OPTION,
    check: bool = CHECK_OPTION,
) -> None:
    """Serialize the JD-blind Stage 1 pool for the owner's review, JD-blind and no database.

    Always calls `projection.pool.project_pool`, checked or not: its owner-gate check
    (`stamp_exists`) runs on every invocation, so an edited-but-unapproved `projection.yaml`
    already exits non-zero without `--check` (`MISSING_PROJECTION_APPROVAL`, folded to
    `PROJECTION_REFUSED` below) — a `--check` that only repeated that gate would never fire
    differently from plain `project` and so would be a check that could never change an outcome.

    `--check`'s own, otherwise-unreachable job is the other half of drift `project_pool` cannot
    see: the approval stamp binds `projection_digest` (the declaration's own digest) but, until
    now, nothing bound the bundle revision the owner actually reviewed against. `--check` compares
    the freshly-computed `pool.bundle_digest` against the `bundle_digest`
    `approve_projection` recorded in the stamp, and refuses (`STALE_PROJECTION_APPROVAL`, folded
    to the bundle's own `STALE_APPROVAL_STAMP`) when the bundle has moved since — the one case an
    unedited, still-approved declaration would otherwise hide entirely.
    """
    config_dir = load_settings(data_dir=ctx.obj).config_dir
    declaration_path = declaration if declaration is not None else config_dir / "projection.yaml"
    bundle_root = resolve_bundle_root(config_dir, bundle)
    as_of = date.today()

    # Deferred: see the module docstring on why `projection.pool` is never imported at module
    # level here; the same reasoning covers `projection.serialize`, reached only through this one
    # command. `projection.stamp` (`read_stamp`/`write_stamp`) is already a module-level import
    # above: it is also `approve_projection`'s, and it does not transitively reach
    # `boardwatch.store` (unlike `projection.pool`).
    from boardwatch.projection.pool import project_pool
    from boardwatch.projection.serialize import resume_document_bytes

    try:
        pool = project_pool(bundle_root, declaration_path, config_dir=config_dir, as_of=as_of)
        if check:
            stamp = read_stamp(config_dir, pool.projection_digest)
            if stamp.bundle_digest != pool.bundle_digest:
                raise_violation(
                    ProjectionIssue.STALE_PROJECTION_APPROVAL,
                    "the owner's approval was reviewed against a different bundle revision; the "
                    "resolved template values may no longer match the bundle's current facts. "
                    "Run approve-projection again after reviewing the current text",
                    where=pool.projection_digest,
                )
    except (ProjectionError, ProfileBundleError) as exc:
        _emit_project(_boundary_outcome(exc), {}, (), as_json=json_output, as_of=as_of)

    document = resume_document_bytes(pool.resume).decode("utf-8")
    result: dict[str, JsonValue] = {
        "bundle_revision": pool.bundle_revision,
        "bundle_digest": pool.bundle_digest,
        "projection_digest": pool.projection_digest,
        "pinned_entry_ids": list(pool.pinned_entry_ids),
        "candidate_entry_ids": list(pool.candidate_entry_ids),
        "no_match_fallback_ids": list(pool.no_match_fallback_ids),
        "resume": document,
    }
    lines = (
        f"bundle revision {pool.bundle_revision} ({pool.bundle_digest})",
        f"projection digest {pool.projection_digest}",
        f"pinned: {', '.join(pool.pinned_entry_ids) or 'none'}",
        f"candidates: {', '.join(pool.candidate_entry_ids) or 'none'}",
        "",
        document,
    )
    _emit_project(OperationOutcome.clean(pool), result, lines, as_json=json_output, as_of=as_of)
