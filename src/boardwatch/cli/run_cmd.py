"""boardwatch run — the pipeline run: scan → eligibility → tailor under one `runs` row.

Thin by convention: everything multi-step lives in boardwatch/pipeline/runner.py and comes
back as a summary dataclass. Replaces the core of the gitignored `bw-daily` shell driver.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from boardwatch.cli.context import build_context
from boardwatch.pipeline.liveness import build_prober
from boardwatch.pipeline.runner import DEFAULT_TOP_N, PipelineSummary, run_pipeline
from boardwatch.scan.coordinator import ScanLockHeldError

console = Console()

DEFAULT_OUT_ROOT = Path.home() / "boardwatch-applications"


def _shortlist_line(summary: PipelineSummary) -> str:
    """Says the ranker did not run, rather than printing zeros as if it had."""
    if summary.shortlist is None:
        return "ranker did not run"
    counts = summary.shortlist
    # `hidden_handled` is named here and not only in the funnel artifact: it is the bucket that
    # explains a legitimately empty day, and `_zero_output_guard` was widened to stop fataling on
    # it. A widened guard whose bucket is absent from the operator's one-line summary prints
    # "0 shortlisted of 400 considered (0, 0, 0, 0)" and exits 0 — counts that visibly fail to
    # reconcile, which is the silent empty day in a new costume. `dead_lead_ids` is here for
    # exactly the same reason: it is the other clause that widened that guard.
    dead = (
        f", {len(summary.dead_lead_ids)} withheld as gone" if summary.dead_lead_ids else ""
    )
    return (
        f"{counts.shortlisted} shortlisted of {counts.considered} considered "
        f"({counts.hidden_ineligible} ineligible, {counts.hidden_non_swe} non-SWE, "
        f"{counts.hidden_duplicate} duplicate, {counts.hidden_applied} already applied, "
        f"{counts.hidden_handled} already handled, "
        f"{counts.hidden_below_cutoff} below cutoff{dead})"
    )


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
    check_liveness: bool = typer.Option(
        True,
        "--check-liveness/--no-check-liveness",
        help="Re-fetch each shortlisted posting and withhold any that answers 404/410. "
        "Turning it off reports liveness as unmeasured, not as zero dead.",
    ),
) -> None:
    """Run the whole pipeline once, attributing every row it writes to one run."""
    # ensure=False mirrors scan_cmd: run_scan migrates INSIDE the scan lock, so a contended
    # run must not have migrated the live DB on its way to being rejected.
    app_ctx = build_context(ctx.obj, ensure=False)
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
            # Built here rather than inside the pipeline so the decision to talk to the network
            # is the CLI's, and so `run_pipeline` stays callable with no outbound I/O at all.
            liveness_prober=build_prober(settings) if check_liveness else None,
        )
    except ScanLockHeldError as exc:
        console.print(str(exc))  # names the blocking pid when the sidecar has one (D-043)
        raise typer.Exit(code=2) from None

    console.print(
        f"run {summary.run_id} · {summary.scan_postings_seen} postings seen · "
        f"{summary.scan_open_postings} open · {summary.evaluated} evaluated · "
        f"{_shortlist_line(summary)} · "
        f"{len(summary.tailored)} tailored · {summary.leads_with_pdf} with PDF"
    )
    for lead in summary.tailored:
        mark = "✓" if lead.pdf_built else "·"
        console.print(f"  {mark} {lead.company} — {lead.title} → {lead.out_dir}", markup=False)
    if summary.funnel is not None:
        console.print(f"  funnel → {summary.funnel.markdown_path}", markup=False)
    if summary.morning is not None:
        console.print(f"  morning → {summary.morning.markdown_path}", markup=False)
    for err in summary.errors:
        console.print(f"  ! {err}", markup=False)

    # Only a FATAL condition fails the run. A few unreachable boards and a few leads that
    # would not tailor are the documented norm across 85 watched boards, and `boardwatch scan`
    # already exits 0 for them; making the daily driver exit 1 every day would destroy the
    # exit status as a signal. Both are still counted, printed and persisted above.
    if summary.fatal is not None:
        console.print(f"run {summary.run_id} FAILED: {summary.fatal}", markup=False)
        raise typer.Exit(code=1)
