"""boardwatch run — the pipeline run: scan → eligibility → tailor under one `runs` row.

Thin by convention: everything multi-step lives in boardwatch/pipeline/runner.py and comes
back as a summary dataclass. Replaces the core of the gitignored `bw-daily` shell driver.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from boardwatch.cli.context import build_context
from boardwatch.pipeline.runner import DEFAULT_TOP_N, run_pipeline
from boardwatch.scan.coordinator import SCAN_LOCK_MESSAGE, ScanLockHeldError

console = Console()

DEFAULT_OUT_ROOT = Path.home() / "boardwatch-applications"


def run(
    ctx: typer.Context,
    top_n: int = typer.Option(
        DEFAULT_TOP_N, "--top", help="How many ranked postings to tailor a résumé for."
    ),
    out_root: Path = typer.Option(  # noqa: B008
        DEFAULT_OUT_ROOT, "--out", help="Root for dated output folders (<out>/<YYYY-MM-DD>/)."
    ),
    resume_path: Path | None = typer.Option(  # noqa: B008
        None, "--resume", help="Authored résumé YAML (default: {config_dir}/resume.yaml)."
    ),
    skip_scan: bool = typer.Option(
        False, "--no-scan", help="Reuse already-fetched postings instead of refetching boards."
    ),
) -> None:
    """Run the whole pipeline once, attributing every row it writes to one run."""
    app_ctx = build_context(ctx.obj)
    settings = app_ctx.settings
    try:
        summary = run_pipeline(
            app_ctx.engine,
            settings,
            console=console,
            top_n=top_n,
            out_root=out_root,
            resume_path=resume_path or settings.config_dir / "resume.yaml",
            skip_scan=skip_scan,
        )
    except ScanLockHeldError:
        console.print(SCAN_LOCK_MESSAGE)
        raise typer.Exit(code=2) from None

    console.print(
        f"run {summary.run_id} · {summary.scan_postings_seen} postings seen · "
        f"{summary.scan_open_postings} open · {summary.evaluated} evaluated · "
        f"{summary.shortlisted} shortlisted · {len(summary.tailored)} tailored · "
        f"{summary.leads_with_pdf} with PDF"
    )
    for lead in summary.tailored:
        mark = "✓" if lead.pdf_built else "·"
        console.print(f"  {mark} {lead.company} — {lead.title} → {lead.out_dir}", markup=False)
    for err in summary.errors:
        console.print(f"  ! {err}", markup=False)
    if summary.errors:
        raise typer.Exit(code=1)
