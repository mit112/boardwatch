"""boardwatch show <id> (§2.3; closed-posting behavior per round-2 finding 5).

Closed postings render a CLOSED banner + closed_at with body/link/comp intact
and 'closed — not ranked' in place of the score section; no preflight and no
on-demand extraction runs for them ('displayed, never ranked', §3.6).
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import select

from boardwatch.cli.context import build_context
from boardwatch.cli.top_cmd import profile_view_from_row
from boardwatch.core.clock import utcnow
from boardwatch.extract.preflight import run_preflight
from boardwatch.extract.taxonomy import load_taxonomy
from boardwatch.rank.explain import explain
from boardwatch.rank.heuristic import score_posting
from boardwatch.store.queries import get_profile
from boardwatch.store.tables import companies, extractions, postings

console = Console()


def show(
    ctx: typer.Context,
    posting_id: int = typer.Argument(..., help="Posting id (the # column of top)."),
) -> None:
    """Full posting with a live score-component breakdown."""
    app_ctx = build_context(ctx.obj)
    engine, settings = app_ctx.engine, app_ctx.settings
    with engine.connect() as conn:
        row = conn.execute(
            select(postings, companies.c.name.label("company_name"))
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
            profile_view_from_row(profile_row), skills, row.title, row.posted_at,
            list(row.locations_json or []), row.remote_policy,
            settings.weights, utcnow(), settings.recency_half_life_days,
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

    console.print(row.body_text)
