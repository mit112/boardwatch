"""boardwatch scan (§2.3). P0 reports board/posting counts; the filter-match
count is added by Task 14, which owns the filter code."""

from __future__ import annotations

import typer
from rich.console import Console

from boardwatch.cli.context import build_context
from boardwatch.scan.coordinator import run_scan

console = Console()


def scan(
    ctx: typer.Context,
    company: str | None = typer.Option(None, "--company", help="Scan only this company slug."),
    provider: str | None = typer.Option(None, "--provider", help="Scan only this provider."),
) -> None:
    """Fetch watched boards (workers) and apply per board in one transaction (coordinator)."""
    app_ctx = build_context(ctx.obj)
    summary = run_scan(app_ctx.engine, app_ctx.settings, company=company, provider=provider)
    console.print(
        f"Scanned {summary.companies} companies · {summary.providers} provider(s) · "
        f"complete {summary.complete} · partial {summary.partial} · failed {summary.failed} · "
        f"unchanged {summary.unchanged} · {summary.open_postings} open postings"
    )
