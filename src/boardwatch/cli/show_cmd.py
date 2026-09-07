"""boardwatch show <id> (§2.3; closed-posting behavior per round-2 finding 5).

Closed postings render a CLOSED banner + closed_at with body/link/comp intact
and 'closed — not ranked' in place of the score section; no preflight and no
on-demand extraction runs for them ('displayed, never ranked', §3.6).
"""

from __future__ import annotations

from dataclasses import asdict
from typing import cast

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import select

from boardwatch.cli._hints import print_next_step
from boardwatch.cli._json_out import emit_json, narrative
from boardwatch.cli._profile_row import refuse_unusable_profile_row
from boardwatch.cli.context import build_context
from boardwatch.core.clock import utcnow
from boardwatch.eligibility.audit import AuditView, VerdictPresentation, load_audit, load_llm_audit
from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.facts import ProfileRowInvalid
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


def _render_audit(audit: AuditView, out: Console) -> None:
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
    out.print(header, markup=False)
    if not audit.catalog_version_matches:
        out.print("catalog version no longer present — showing raw rule ids", markup=False)
    for req in audit.requirements:
        out.print(f"  {req.disposition} · {req.requiredness}: {req.label}", markup=False)
        if req.quote:
            out.print(f"      quote: {req.quote}", markup=False)
        for sup in req.support:
            out.print(f"      support: {sup.evidence_quote}", markup=False)


def _render_llm_audit(audit: AuditView, out: Console) -> None:
    """The opt-in LLM lane's read, dimmed and labeled advisory so it never reads as the
    authoritative verdict above it (D-P3-13). Plain lines with markup off, same as
    _render_audit, since the quote is arbitrary JD text that could contain '['."""
    out.print(f"advisory (LLM): {audit.verdict}", style="dim", markup=False)
    for req in audit.requirements:
        out.print(
            f"  {req.disposition} · {req.requiredness}: {req.label}",
            style="dim",
            markup=False,
        )
        if req.quote:
            out.print(f"      quote: {req.quote}", style="dim", markup=False)


def show(
    ctx: typer.Context,
    posting_id: int = typer.Argument(..., help="Posting id (the # column of top)."),
    as_json: bool = typer.Option(
        False, "--json", help="Emit one JSON object instead of the readout."
    ),
) -> None:
    """Full posting with a live score-component breakdown."""
    out = narrative(as_json, console)
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
        out.print(f"no posting with id {posting_id}")
        raise typer.Exit(code=1)

    payload: dict[str, object] = {
        "posting": {
            "id": row.id,
            "title": row.title,
            "company": row.company_name,
            "provider": row.provider,
            "slug": row.slug,
            "url": row.url,
            "locations": list(row.locations_json or []),
            "remote_policy": row.remote_policy,
            "department": row.department,
            "posted_at": row.posted_at,
            "status": row.status,
            "closed_at": row.closed_at,
            "salary_min": row.salary_min,
            "salary_max": row.salary_max,
            "salary_currency": row.salary_currency,
            "salary_period": row.salary_period,
            "job_id": row.job_id,
        }
    }
    out.print(f"[bold]{row.title}[/bold] — {row.company_name}")
    if row.url:
        out.print(f"Link: {row.url}")
    if row.locations_json:
        out.print(f"Locations: {', '.join(row.locations_json)} · {row.remote_policy}")
    if row.salary_min is not None or row.salary_max is not None:  # structured comp iff present
        comp = f"Compensation: {row.salary_min}–{row.salary_max}"
        extras = " ".join(str(part) for part in (row.salary_currency, row.salary_period) if part)
        out.print(f"{comp} {extras}".rstrip())

    if row.status == "closed":
        out.print(f"[red]CLOSED[/red] — closed at {row.closed_at}")
        out.print("closed — not ranked")
    else:
        run_preflight(engine, settings, out)
        with engine.connect() as conn:
            profile_row = get_profile(conn)
            if profile_row is None:
                out.print("no profile yet — run `boardwatch init` first")
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
        components = list(explain(score))
        for entry in components:
            table.add_row(
                entry.component,
                "—" if entry.raw is None else f"{entry.raw:.2f}",
                f"{entry.weight:.2f}",
                "—" if entry.weighted is None else f"{entry.weighted:.3f}",
                entry.detail,
            )
        out.print(table)
        payload["score"] = {
            "total": score.total,
            "components": [asdict(entry) for entry in components],
        }
        # `show <id>` is the audit surface for the role gate: every posting says what the
        # gate made of its title, so a hidden row can always be looked up and checked.
        # Plain line, markup off — the matched text is arbitrary title text.
        role, role_reason = role_verdict(row.title)
        hidden_note = " — hidden from top unless --include-non-swe" if role == "not_swe" else ""
        out.print(f"Role: {role_reason}{hidden_note}", markup=False)
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
            out.print(f"Signal: {zero_signal_reason}{signal_note}", markup=False)
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
        out.print(f"Band: {band_reason}{band_note}", markup=False)
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
        out.print(f"Hard filter: {hard_line}", markup=False)
        payload["gates"] = {
            "role": {"verdict": role, "reason": role_reason},
            "signal": {"verdict": zero_signal, "reason": zero_signal_reason},
            "band": {"verdict": band, "reason": band_reason},
            "hard_filter": None if hard_veto is None else asdict(hard_veto),
        }

    catalog = load_rules(settings.config_dir)
    with engine.connect() as conn:
        try:
            identity = current_identity(conn, settings)
        except ProfileRowInvalid as exc:
            refuse_unusable_profile_row(exc, out)
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
        _render_audit(audit, out)
    if llm_audit is not None:
        _render_llm_audit(llm_audit, out)
    payload["eligibility"] = None if audit is None else asdict(audit)
    payload["llm_eligibility"] = None if llm_audit is None else asdict(llm_audit)
    payload["body_text"] = row.body_text
    if as_json:
        emit_json(payload)
        return

    console.print(row.body_text)
    print_next_step(console, "`boardwatch track add <#>` to record an application")
