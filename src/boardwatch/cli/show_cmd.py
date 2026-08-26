"""boardwatch show <id> (§2.3; closed-posting behavior per round-2 finding 5).

Closed postings render a CLOSED banner + closed_at with body/link/comp intact
and 'closed — not ranked' in place of the score section; no preflight and no
on-demand extraction runs for them ('displayed, never ranked', §3.6).
"""

from __future__ import annotations

from typing import cast

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import select

from boardwatch.cli._hints import print_next_step
from boardwatch.cli.context import build_context
from boardwatch.core.clock import utcnow
from boardwatch.eligibility.audit import AuditView, VerdictPresentation, load_audit, load_llm_audit
from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.preflight import current_identity
from boardwatch.extract.preflight import run_preflight
from boardwatch.extract.taxonomy import load_taxonomy
from boardwatch.rank.explain import explain
from boardwatch.rank.heuristic import (
    hard_filter_verdict,
    profile_view_from_row,
    score_posting,
)
from boardwatch.rank.leveling import load_leveling, resolve_schemes
from boardwatch.rank.role_gate import role_verdict, zero_signal_verdict
from boardwatch.rank.seniority_gate import TargetBand, seniority_verdict
from boardwatch.store.queries import get_profile
from boardwatch.store.tables import companies, extractions, postings

console = Console()


def _render_audit(audit: AuditView) -> None:
    """The persisted eligibility audit, evidence linked. Plain lines, no Rich markup, so a
    disposition or a sliced quote can never be read as a style tag.

    "No flags" != cleared (CLAUDE.md, P2 item 6): an `eligible` that fired zero requirement
    rows is worded distinctly from one that fired and cleared some, via the typed
    `VerdictPresentation` derived from the stored verdict and requirement count — the stored
    verdict itself is never touched. The header never says "cleared" for a row that isn't:
    a `preference`-family row can be `unmet`/`unknown` without blocking the verdict (D-035), so
    a mixed outcome gets neutral wording instead of an aggregate "N cleared" overclaim; the
    per-requirement lines below always show each row's true disposition either way."""
    n = len(audit.requirements)
    if audit.presentation is VerdictPresentation.ELIGIBLE_NO_RULES_APPLIED:
        header = "Eligibility: eligible — no eligibility rule applied (not screened)"
    elif audit.presentation is VerdictPresentation.ELIGIBLE_CLEARED:
        header = f"Eligibility: eligible — {n} requirement{'s' if n != 1 else ''} cleared"
    elif audit.presentation is VerdictPresentation.ELIGIBLE_MIXED:
        header = (
            f"Eligibility: eligible — {n} requirement{'s' if n != 1 else ''} evaluated "
            f"({audit.met_count} cleared; see details)"
        )
    else:
        header = f"Eligibility: {audit.verdict}"
    if audit.is_historical:
        header += f" (historical, captured {audit.captured_at})"
    console.print(header, markup=False)
    if not audit.catalog_version_matches:
        console.print("catalog version no longer present — showing raw rule ids", markup=False)
    for req in audit.requirements:
        console.print(f"  {req.disposition} · {req.requiredness}: {req.label}", markup=False)
        if req.quote:
            console.print(f"      quote: {req.quote}", markup=False)
        for sup in req.support:
            console.print(f"      support: {sup.evidence_quote}", markup=False)


def _render_llm_audit(audit: AuditView) -> None:
    """The opt-in LLM lane's read, dimmed and labeled advisory so it never reads as the
    authoritative verdict above it (D-P3-13). Plain lines with markup off, same as
    _render_audit, since the quote is arbitrary JD text that could contain '['."""
    console.print(f"advisory (LLM): {audit.verdict}", style="dim", markup=False)
    for req in audit.requirements:
        console.print(
            f"  {req.disposition} · {req.requiredness}: {req.label}",
            style="dim",
            markup=False,
        )
        if req.quote:
            console.print(f"      quote: {req.quote}", style="dim", markup=False)


def show(
    ctx: typer.Context,
    posting_id: int = typer.Argument(..., help="Posting id (the # column of top)."),
) -> None:
    """Full posting with a live score-component breakdown."""
    app_ctx = build_context(ctx.obj)
    engine, settings = app_ctx.engine, app_ctx.settings
    with engine.connect() as conn:
        row = conn.execute(
            select(
                postings,
                companies.c.name.label("company_name"),
                companies.c.provider,
                companies.c.slug,
            )
            .join(companies, postings.c.company_id == companies.c.id)
            .where(postings.c.id == posting_id)
        ).one_or_none()
    if row is None:
        console.print(f"no posting with id {posting_id}")
        raise typer.Exit(code=1)

    console.print(f"[bold]{row.title}[/bold] — {row.company_name}")
    if row.url:
        console.print(f"Link: {row.url}")
    if row.locations_json:
        console.print(f"Locations: {', '.join(row.locations_json)} · {row.remote_policy}")
    if row.salary_min is not None or row.salary_max is not None:  # structured comp iff present
        comp = f"Compensation: {row.salary_min}–{row.salary_max}"
        extras = " ".join(str(part) for part in (row.salary_currency, row.salary_period) if part)
        console.print(f"{comp} {extras}".rstrip())

    if row.status == "closed":
        console.print(f"[red]CLOSED[/red] — closed at {row.closed_at}")
        console.print("closed — not ranked")
    else:
        run_preflight(engine, settings, console)
        with engine.connect() as conn:
            profile_row = get_profile(conn)
            if profile_row is None:
                console.print("no profile yet — run `boardwatch init` first")
                raise typer.Exit(code=1)
            profile = profile_view_from_row(profile_row)
            version = load_taxonomy(settings.config_dir).version
            extraction = conn.execute(
                select(extractions.c.json).where(
                    extractions.c.posting_id == row.id,
                    extractions.c.content_hash == row.content_hash,
                    extractions.c.kind == "taxonomy",
                    extractions.c.engine_version == version,
                )
            ).scalar_one_or_none()
        skills = set((extraction or {}).get("skills", []))
        score = score_posting(
            profile, skills, row.title, row.posted_at,
            list(row.locations_json or []), row.remote_policy,
            settings.weights, utcnow(), settings.recency_half_life_days,
            settings.zero_skill_coverage_prior,
        )
        table = Table(title=f"Score {score.total:.2f}")
        table.add_column("Component")
        table.add_column("Raw")
        table.add_column("Weight")
        table.add_column("Weighted")
        table.add_column("Detail")
        for entry in explain(score):
            table.add_row(
                entry.component,
                "—" if entry.raw is None else f"{entry.raw:.2f}",
                f"{entry.weight:.2f}",
                "—" if entry.weighted is None else f"{entry.weighted:.3f}",
                entry.detail,
            )
        console.print(table)
        # `show <id>` is the audit surface for the role gate: every posting says what the
        # gate made of its title, so a hidden row can always be looked up and checked.
        # Plain line, markup off — the matched text is arbitrary title text.
        role, role_reason = role_verdict(row.title)
        hidden_note = " — hidden from top unless --include-non-swe" if role == "not_swe" else ""
        console.print(f"Role: {role_reason}{hidden_note}", markup=False)
        # Same contract for the zero-signal rule, and it needs no extra query: `extraction` was
        # already read above for the score, and it is the ROW (None when absent), not a
        # collapsed `or {}`, so this surface can tell "found nothing" from "never looked".
        # `body_empty` is computed in Python here, not in SQL as the ranking surfaces do it:
        # this query is a single posting and already selects `postings` whole, so `body_text`
        # is in hand and a second predicate would be a second read of the same fact. The strip
        # set is spelled out rather than left to a bare `.strip()`, which also strips Unicode
        # whitespace SQLite's `trim` does not — this surface has to agree with `top` about
        # which body is empty, or `show` would explain a row `top` did not hide.
        zero_signal, zero_signal_reason = zero_signal_verdict(
            role, extraction, body_empty=not (row.body_text or "").strip(" \t\n\r\f\v")
        )
        if zero_signal != "pass":
            signal_note = (
                " — hidden from top unless --include-zero-signal"
                if zero_signal == "veto"
                else " — the rule could not fire, so this row is NOT filtered"
            )
            console.print(f"Signal: {zero_signal_reason}{signal_note}", markup=False)
        # Same contract for the seniority gate: a row `top` hides as above_band must be
        # explainable by looking it up, or the quarantine is unauditable.
        leveling = load_leveling(settings.config_dir)
        schemes, _binding_warning = resolve_schemes(leveling, settings.config_dir)
        band, band_reason = seniority_verdict(
            row.title, schemes.get((row.provider, row.slug)),
            cast(TargetBand, profile.target_seniority_band),
            leveling.fields["software"], leveling,
        )
        band_note = (
            " — hidden from top unless --include-over-seniority" if band == "above_band" else ""
        )
        console.print(f"Band: {band_reason}{band_note}", markup=False)
        # And the same contract for the hard filters -- the LARGEST cut in the pipeline, and the
        # one this surface said nothing about. A row `top` drops for an excluded title or a
        # non-US location has to be explainable by looking it up, or the bucket is unauditable.
        hard_veto = hard_filter_verdict(
            row.title, list(row.locations_json or []), row.remote_policy,
            profile_view_from_row(profile), settings.location_filter_mode,
        )
        hard_line = (
            f"{hard_veto.clause} ({hard_veto.detail}) "
            "— hidden from top unless --include-hard-filter"
            if hard_veto is not None
            else "cleared every hard filter"
        )
        console.print(f"Hard filter: {hard_line}", markup=False)

    catalog = load_rules(settings.config_dir)
    with engine.connect() as conn:
        identity = current_identity(conn, settings)
        profile_hash, rules_hash = identity if identity is not None else (None, None)
        audit = load_audit(
            conn,
            posting_id,
            catalog,
            profile_hash=profile_hash,
            rules_hash=rules_hash,
        )
        llm_audit = load_llm_audit(conn, posting_id, catalog)
    if audit is not None:
        _render_audit(audit)
    if llm_audit is not None:
        _render_llm_audit(llm_audit)

    console.print(row.body_text)
    print_next_step(console, "`boardwatch track add <#>` to record an application")
