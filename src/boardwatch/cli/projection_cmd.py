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

# Every `as_of` below is read from the SAME clock the pipeline reads (`utcnow().date()`), never
# `date.today()`. `as_of` feeds effective-fact resolution, so it decides WHICH facts render: for an
# owner at UTC-4/5 the local and UTC dates differ for several hours every evening, and a preview
# built from the local date would show a résumé assembled from different effective facts than
# `run --project` produces. The `runs` row and the lineage record are both UTC, and a preview that
# disagrees with the run it is previewing is worse than either convention alone.
from boardwatch.core.clock import utcnow
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
from boardwatch.projection.errors import ProjectionError, ProjectionIssue
from boardwatch.projection.stamp import write_stamp

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
        candidate = projection_candidate(bundle_root, declaration_path, as_of=utcnow().date())
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
    """Fold one `ProjectionViolation` into the bundle family's `Diagnostic` shape (R27).

    `ProjectionIssue` stays the authoritative catalog for projection's own business outcomes and
    is never taught into `profile_bundle.errors` member by member. `STALE_PROJECTION_APPROVAL`
    reuses the bundle's own `STALE_APPROVAL_STAMP`: the identical shape of failure — an approval's
    bound content diverged from what is current — just for projection's own stamp rather than
    the bundle's own `ApprovalStamp`. `project_pool` raises it unconditionally now (D-167), on
    every path that reaches it, not behind a flag. Every other member funnels into the one new
    `PROJECTION_REFUSED` code; `details.projection_issue` carries the specific member so nothing
    is lost at the fold.

    Two reachable members leak an absolute filesystem path in their OWN message or `where`, and
    are sanitized here rather than at their raise site (this family's second rule forbids that in
    any diagnostic): `BUNDLE_UNREADABLE` (`pool.py`'s `f"the bundle at {bundle_root} could not be
    read..."`, `where=str(bundle_root)` — both replaced) and `SHELL_SOURCE_UNREADABLE`
    (`shell.py`'s message interpolates a caught `OSError`, whose `str()` embeds the shell file's
    absolute path on a missing or unreadable file — message replaced; `where` is kept as-is, since
    it is already `path.name`, a bare filename, not the leak).

    Re-derived for this fix, not restated from the prior pass: `project_pool` (the only path
    `project` calls) reaches exactly five modules that call `raise_violation` — `pool.py` itself,
    `declaration.py`, `contract.py`, `grammar.py`, and `shell.py`. (`persona_preflight.py`,
    `posting.py`, and `select.py` also call `raise_violation`, but are Stage 2 only, reached by
    `resume_project`, never by this command.) Reading every call site in those five, the two
    members above are the only ones whose message or `where` can carry an absolute path; every
    other reachable call builds its message and `where` only from ids, predicate names, digests,
    and bare filenames (`path.name`, never a full path).
    """
    code = (
        IssueCode.STALE_APPROVAL_STAMP
        if violation.issue is ProjectionIssue.STALE_PROJECTION_APPROVAL
        else IssueCode.PROJECTION_REFUSED
    )
    if violation.issue is ProjectionIssue.BUNDLE_UNREADABLE:
        message = "the bundle could not be read to produce a projection pool"
        where: str | None = None
    elif violation.issue is ProjectionIssue.SHELL_SOURCE_UNREADABLE:
        message = "shell_source is not a valid header/education shell"
        where = violation.where
    else:
        message = violation.message
        where = violation.where
    if where is not None:
        return diagnostic(code, message, projection_issue=str(violation.issue), where=where)
    return diagnostic(code, message, projection_issue=str(violation.issue))


def _boundary_outcome(exc: ProjectionError | ProfileBundleError) -> OperationOutcome[Any]:
    """The §21 outcome one refusal implies, at this command's boundary.

    `project_pool` now calls `read_stamp` (`projection/stamp.py`) itself, unconditionally
    (D-167), to compare the stamp's `bundle_digest` against the bundle actually being read — so
    the plain `ProfileBundleError` arm is for that call failing inside `project_pool`, not merely
    surviving past it. A stamp written by an older schema revision (missing a field a newer
    `ProjectionStamp` now requires — this is not a theoretical race, it is what anyone who ran
    `approve-projection` before `bundle_digest` became required has sitting on disk), one whose
    bytes fail to parse, or one removed in the gap between the two calls all become
    `ProfileBundleError` there rather than escaping uncaught. This arm reports that as
    `INTERNAL_ERROR` rather than folding it into `PROJECTION_REFUSED`, since none of those is a
    projection business outcome.
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
) -> None:
    """Serialize the JD-blind Stage 1 pool for the owner's review, JD-blind and no database.

    `projection.pool.project_pool` runs the owner gate unconditionally now (D-167): `stamp_exists`
    proves `projection.yaml`'s own digest was approved, and `read_stamp` then compares the stamp's
    `bundle_digest` against the bundle actually being read, refusing (`STALE_PROJECTION_APPROVAL`,
    folded to the bundle's own `STALE_APPROVAL_STAMP`) when the bundle has moved since approval —
    the one case an unedited, still-approved declaration would otherwise hide entirely. There used
    to be a `--check` flag gating that second half; it was deleted (D-167) once the comparison
    became unconditional, because an opt-in flag on a consent control is the wrong shape and a
    check that cannot fire differently from plain `project` is a check that is deleted, not kept.
    """
    config_dir = load_settings(data_dir=ctx.obj).config_dir
    declaration_path = declaration if declaration is not None else config_dir / "projection.yaml"
    bundle_root = resolve_bundle_root(config_dir, bundle)
    as_of = utcnow().date()

    # Deferred: see the module docstring on why `projection.pool` is never imported at module
    # level here; the same reasoning covers `projection.serialize`, reached only through this one
    # command.
    from boardwatch.projection.pool import project_pool
    from boardwatch.projection.serialize import resume_document_bytes

    try:
        pool = project_pool(bundle_root, declaration_path, config_dir=config_dir, as_of=as_of)
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


# --------------------------------------------------------------------------------------
# `resume project` — Stages 1 and 2 together, posting-aware
# --------------------------------------------------------------------------------------

#: A NEW top-level group (`resume` names nothing today), deliberately outside
#: `profile_bundle_app`: JD skills and the page budget are database-owned, so this command uses
#: `build_context`, unlike every command in the bundle family. Registered in `cli/app.py` with
#: one import plus `app.add_typer(resume_app, name="resume")` — `cli/app.py` is not part of the
#: tailor closure `tests/profile_bundle/test_profile_bundle_tailor_isolation.py` walks, so this
#: is safe; that suite is re-run, not assumed, to prove it.
resume_app = typer.Typer(
    no_args_is_help=True,
    help="Project a career-profile bundle into a posting-aware résumé (Stage 1 + Stage 2).",
)

POSTING_OPTION = typer.Option(..., "--posting", help="Posting id (the # column of top).")  # noqa: B008
SCORER_OPTION = typer.Option(  # noqa: B008
    "mean_per_bullet",
    "--scorer",
    help=(
        "Entry scorer ranking candidates against the JD's skills. Defaults to mean_per_bullet, "
        "adopted by the owner-labeled selection matrix (D-198): it had the highest mean rank "
        "agreement with the matrix's ten postings and, being normalized per bullet, resists the "
        "bullet-count inflation that fools total_distinct. Agreement is weak in absolute terms "
        "(mean Kendall tau-b <= 0.16), so the pick stays overridable rather than silent. Choices: "
        "coverage_then_density, mean_per_bullet, mean_top_k, total_distinct. An unknown name is "
        "refused with the live list of registered choices."
    ),
)
RESUME_OUT_OPTION = typer.Option(  # noqa: B008
    None, "--out", help="Output directory (default {data_dir}/projected/<posting id>)."
)


@resume_app.command("project")
def resume_project(
    ctx: typer.Context,
    posting_id: int = POSTING_OPTION,
    scorer_name: str = SCORER_OPTION,
    declaration: Path | None = DECLARATION_OPTION,
    bundle: Path | None = BUNDLE_OPTION,
    out: Path | None = RESUME_OUT_OPTION,
) -> None:
    """Project the bundle (Stage 1) then select which entries reach the résumé against
    `posting_id`'s JD skills and page budget (Stage 2). Writes `resume.projected.yaml` and
    `projection-manifest.json` beside each other under `--out`.

    The flow is two commands, deliberately: this one, then `tailor run <id> --resume <path>`.
    Folding projection into `tailor run` would require `tailor` to know about the bundle — the
    exact wall this design keeps up. Two costs are accepted rather than optimised away: the JD is
    read twice, and the résumé compiles twice (a scratch compile here, just to fit the page
    budget; the real artifact in `tailor run`).
    """
    # Deferred for the same reason `project`'s own imports are (see the module docstring):
    # `projection.scoring` reaches `boardwatch.store` too, via `extract.taxonomy`, so it is
    # never imported at this module's top level either.
    from boardwatch.projection.scoring import SCORERS

    config_dir = load_settings(data_dir=ctx.obj).config_dir

    # The cheapest possible refusal point: neither the bundle nor the database is needed to
    # tell whether a persona declares `entries` (Task 15's own collision), so this runs before
    # `project_pool` reads anything and before `--scorer` is even validated.
    from boardwatch.projection.persona_preflight import reject_entry_declaring_personas
    from boardwatch.tailor.persona import PersonaError

    try:
        reject_entry_declaring_personas(config_dir)
    except (ProjectionError, PersonaError) as exc:
        # `reject_entry_declaring_personas` calls `load_personas`, which raises `PersonaError` —
        # not `ProjectionError` — for a registry that is malformed rather than merely
        # entry-declaring: invalid YAML, no default persona, a duplicate id, a role_family outside
        # the closed set. This is the FIRST thing in the command that reads `personas.yaml`, so it
        # is where that refusal has to be reported; uncaught, it was a traceback.
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    if scorer_name not in SCORERS:
        typer.echo(
            f"unknown scorer {scorer_name!r}; choices: {', '.join(sorted(SCORERS))}",
            err=True,
        )
        raise typer.Exit(code=1)

    # Unlike `project`, this command legitimately needs a database (JD skills and the page
    # budget are posting-context facts) — `build_context` is deferred here purely to keep this
    # module's own store-import guard intact for the OTHER commands it hosts, not because a
    # database is somehow forbidden for this one. `projection.run` is deferred for that same
    # reason: it reaches `boardwatch.store` through `projection.posting`.
    from boardwatch.cli.context import build_context
    from boardwatch.extract.taxonomy import TaxonomyError
    from boardwatch.projection.run import project_for_posting, resolve_projection_run
    from boardwatch.reports.tailor import default_compile_runner
    from boardwatch.tailor.equivalences import EquivalenceError
    from boardwatch.tailor.render.latex import TemplateArtifactError

    app_ctx = build_context(ctx.obj)
    settings = app_ctx.settings
    config_dir = settings.config_dir
    declaration_path = declaration if declaration is not None else config_dir / "projection.yaml"
    bundle_root = resolve_bundle_root(config_dir, bundle)
    as_of = utcnow().date()
    out_dir = out if out is not None else settings.data_dir / "projected" / str(posting_id)

    try:
        # `resolve_projection_run` resolves the taxonomy ONCE, above the `posting_context` call
        # `project_for_posting` makes, so this command cannot extract a posting's skills under one
        # taxonomy and score them under another. It also owns the pool, the equivalence table and
        # the persona registry version, so nothing here re-reads any of them.
        run_ctx = resolve_projection_run(
            app_ctx.engine,
            settings,
            bundle_root=bundle_root,
            declaration_path=declaration_path,
            scorer_id=scorer_name,
            as_of=as_of,
        )
        result = project_for_posting(
            run_ctx,
            app_ctx.engine,
            settings,
            posting_id,
            out_dir=out_dir,
            compile_runner=default_compile_runner(),
        )
    except (
        ProjectionError,
        ProfileBundleError,
        TemplateArtifactError,
        PersonaError,
        TaxonomyError,
        EquivalenceError,
    ) as exc:
        # Exactly `resolve_projection_run`'s documented raise set, plus what `select` adds. Every
        # one is an operator-actionable configuration fault, so every one is a message and an exit
        # code rather than a traceback:
        #
        # * `ProjectionError` — every member of the closed catalog.
        # * `ProfileBundleError` — `project_pool` calls `read_stamp` unconditionally (D-167), which
        #   raises this for a stamp that fails to parse or validate against the current schema.
        #   The same widening `project`'s own boundary already has.
        # * `TemplateArtifactError` — `select`'s `compile_prefix` calls `renderer.emit`, which
        #   resolves and validates a user-supplied `{config_dir}/resume_template.tex` and refuses a
        #   leftover `%%..%%`/TODO/placeholder marker with a bare `RuntimeError` subclass.
        # * `TaxonomyError` — a malformed `{config_dir}/taxonomy.yaml` override.
        # * `EquivalenceError` — the packaged `tailor/equivalences.yaml` is unreadable or malformed.
        #   No user override exists for it, so this arm means a corrupt installation.
        # * `PersonaError` — `resolve_projection_run` reads the registry too. The preflight above
        #   reads the same file first and so refuses a malformed one there in practice; this arm
        #   covers the file changing between the two reads, and keeps the two boundaries from
        #   disagreeing about which families are typed refusals.
        #
        # `RenderToolMissingError`/`LeadArtifactError` are still not listed: both are raised by
        # `run_tailor` after inspecting a `GateResult`, never by `evaluate_compile`, `to_pdf`, or
        # the default runner, which only ever return one.
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    # `project_for_posting` raises on every refusal, so a returned result always carries both —
    # which is now in `ProjectionResult`'s own types rather than re-asserted here.
    selection = result.selection
    typer.echo(f"wrote {result.resume_path}")
    typer.echo(f"wrote {result.manifest_path}")
    selected_count = len(selection.selected_candidate_ids)
    typer.echo(
        f"posting {posting_id} scorer {scorer_name} "
        f"pinned {len(selection.pinned_entry_ids)} selected {selected_count} "
        f"fallback {selection.used_fallback} pages {selection.page_count}"
    )
