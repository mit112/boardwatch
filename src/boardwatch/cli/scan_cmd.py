"""boardwatch scan (§2.3). P0 reports board/posting counts; the filter-match
count is added by Task 14, which owns the filter code."""

from __future__ import annotations

import typer
from rich.console import Console

from boardwatch.cli._hints import print_next_step
from boardwatch.cli.context import build_context
from boardwatch.scan.coordinator import ScanLockHeldError, run_scan

console = Console()


def scan(
    ctx: typer.Context,
    company: str | None = typer.Option(None, "--company", help="Scan only this company slug."),
    provider: str | None = typer.Option(None, "--provider", help="Scan only this provider."),
) -> None:
    """Fetch watched boards (workers) and apply per board in one transaction (coordinator)."""
    app_ctx = build_context(ctx.obj, ensure=False)  # run_scan migrates inside the lock
    try:
        summary = run_scan(app_ctx.engine, app_ctx.settings, company=company, provider=provider)
    except ScanLockHeldError as exc:
        console.print(str(exc))  # names the blocking pid when the sidecar has one (D-043)
        raise typer.Exit(code=2) from None
    from boardwatch.cli.top_cmd import count_filter_matches

    line = (
        f"Scanned {summary.companies} companies · {summary.providers} provider(s) · "
        f"complete {summary.complete} · partial {summary.partial} · failed {summary.failed} · "
        f"unchanged {summary.unchanged} · {summary.open_postings} open postings"
    )
    matches = count_filter_matches(app_ctx.engine, app_ctx.settings)
    if matches is not None:
        # "ranking filters", not "your filters": this count comes from the ranker and would
        # contradict `top` once `top` hides postings persisted as ineligible.
        line += f" · {matches} match ranking filters"
    console.print(line)
    print_next_step(console, "run `boardwatch top` to see your ranked shortlist")
