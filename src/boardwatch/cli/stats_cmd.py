"""boardwatch stats: a one-screen read-only readout over the local DB.

Supersedes the scattered ad-hoc counts (`scan`'s "N match ranking filters",
`eligibility summary`'s evaluated/verdict counts, `top`'s "N hidden as ineligible") as the
single aggregation surface. Read-only; keyless; no network.
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from boardwatch.cli.context import build_context
from boardwatch.reports.stats import compute_stats

console = Console()


def stats(
    ctx: typer.Context,
    days: int = typer.Option(7, "--days", help="Trailing window for qualified/week."),
) -> None:
    """Qualified-opportunities/week and the discovery pipeline, from your local DB."""
    app_ctx = build_context(ctx.obj)
    report = compute_stats(
        app_ctx.engine, app_ctx.settings, window_days=days, output_console=console
    )
    if report is None:
        console.print("no profile yet — run `boardwatch init` first")
        raise typer.Exit(code=1)
    qual = Table(title=f"Qualified opportunities (last {report.window_days}d)",
                 show_header=True, header_style="bold", title_justify="left")
    qual.add_column("Bucket")
    qual.add_column("Count", justify="right")
    qual.add_row("qualified", str(report.qualified))
    qual.add_row("uncertain", str(report.uncertain))
    qual.add_row("ineligible", str(report.ineligible))
    qual.add_row("unevaluated", str(report.unevaluated))
    console.print(qual)
    pipe = Table(title="Pipeline", show_header=True, header_style="bold", title_justify="left")
    pipe.add_column("Stage")
    pipe.add_column("Count", justify="right")
    pipe.add_row("seen (open)", str(report.seen))
    pipe.add_row("passes filters", str(report.passes_filters))
    pipe.add_row("not ineligible", str(report.not_ineligible))
    pipe.add_row("tracked (submitted)", str(report.tracked))
    console.print(pipe)
