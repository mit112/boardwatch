"""export: take your data with you.

Writes every open or tracked posting with its eligibility verdict and your funnel state
as a flat snapshot (A6). Runs the eligibility preflight first so an export reflects the
current profile rather than a stale verdict, matching what `top` shows. Preflight
progress and the confirmation go to stderr; stdout carries ONLY data rows, so
`boardwatch export --format jsonl | jq` stays clean (A3).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from boardwatch.cli.context import build_context
from boardwatch.eligibility.preflight import run_eligibility
from boardwatch.eligibility.read import current_verdicts
from boardwatch.reports.export import export_rows, write_csv, write_jsonl
from boardwatch.store.funnel_queries import list_funnel
from boardwatch.store.queries import current_posting_versions

# A3: chatter goes to stderr, data rows to stdout.
console = Console(stderr=True)

_WRITERS = {"jsonl": write_jsonl, "csv": write_csv}


def export(
    ctx: typer.Context,
    format_: str = typer.Option("jsonl", "--format", help="jsonl or csv."),
    out: Annotated[
        Path | None, typer.Option("--out", help="Write to this file instead of stdout.")
    ] = None,
) -> None:
    """Export every open or tracked posting with its verdict and your funnel state."""
    writer = _WRITERS.get(format_)
    if writer is None:
        raise typer.BadParameter(
            f"{format_!r} is not a format. Choose jsonl or csv.", param_hint="--format"
        )
    app_ctx = build_context(ctx.obj)
    stats = run_eligibility(app_ctx.engine, app_ctx.settings, console)
    with app_ctx.engine.connect() as conn:
        # Verdict scope: every open posting plus every tracked posting, closed or not, so a
        # closed tracked row carries the identity it was computed under (A6).
        open_versions = current_posting_versions(conn, None)
        tracked_ids = {
            row.posting_id for row in list_funnel(conn) if row.posting_id is not None
        }
        versions = current_posting_versions(conn, sorted(set(open_versions) | tracked_ids))
        verdicts = current_verdicts(
            conn,
            [cv.posting_version_id for cv in versions.values()],
            stats.profile_hash,
            stats.rules_hash,
        )
        # A10: stream the iterator straight to the writer while the connection is open;
        # the writer's return value is the count, so nothing is materialized.
        rows = export_rows(
            conn,
            verdicts=verdicts,
            profile_hash=stats.profile_hash,
            rules_hash=stats.rules_hash,
        )
        if out is None:
            writer(rows, sys.stdout)
            return
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8", newline="") as stream:
            count = writer(rows, stream)
    console.print(f"wrote {count} rows to {out}")
