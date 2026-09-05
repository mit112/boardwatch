"""boardwatch run — the pipeline run: scan → eligibility → tailor under one `runs` row.

Thin by convention: everything multi-step lives in boardwatch/pipeline/runner.py and comes
back as a summary dataclass. Replaces the core of the gitignored `bw-daily` shell driver.
"""

from __future__ import annotations

import os
from pathlib import Path

import typer
from rich.console import Console

from boardwatch.cli._hints import print_next_step
from boardwatch.cli.context import build_context
from boardwatch.delivery.queue import DEFAULT_QUEUE_ROOT
from boardwatch.pipeline.liveness import build_prober
from boardwatch.pipeline.runner import DEFAULT_TOP_N, PipelineSummary, run_pipeline
from boardwatch.scan.coordinator import ScanLockHeldError

console = Console()

DEFAULT_OUT_ROOT = Path.home() / "boardwatch-applications"


def _coverage_line(summary: PipelineSummary) -> str:
    """One line of board-discovery reach for the run log (D-274).

    "not measured" and "not measurable" are different facts and are worded differently: the
    first is our failure to read the columns, the second is a real report in which no board
    stated a total we can trust. Neither is ever printed as 0%.
    """
    report = summary.board_coverage
    if report is None:
        return "not measured (load failed; see the ! line above)"
    ratio = (
        "not measurable"
        if report.global_ratio is None
        else f"{100 * report.global_ratio:.1f}%"
    )
    counts = report.bucket_counts
    return (
        f"{ratio} ({report.measured_held:,} held of {report.measured_total:,} stated) · "
        f"{counts['measured']} measured · {counts['enumerated_only']} no total · "
        f"{counts['censored']} censored · {counts['dark']} dark · {counts['stale']} stale · "
        f"{counts['unscanned']} unscanned · {counts['unreadable']} unreadable "
        f"of {report.corpus_boards} watched"
    )


def _lane_lines(summary: PipelineSummary) -> list[str]:
    """One line of lane reach per lane that ran, for the run log (D7).

    Nothing is printed when no lane ran, which is every run until `lanes_enabled` names one:
    a daily "lanes → none" would be noise, and a lane that IS enabled but produced no report
    already prints its reason through the `!` error lines below.

    `SILENT OUTAGE` is spelled out rather than left for the reader to infer from `0 resolved`.
    A lane with nothing to attempt also resolves 0 and is fine; a lane that attempted work and
    recovered no body is the condition this whole tally exists to make visible, and the prior
    art's browser tier ran 11 scheduled runs in exactly that state with nothing saying so.

    `admitted` counts only companies the store did not already hold, so it reads as reach ADDED.
    A run whose admitted count is 0 while `refused` is non-zero is a lane at its cap; one where
    both are 0 is a lane that found only companies already known.
    """
    lines: list[str] = []
    for lane in summary.lanes:
        outage = " · SILENT OUTAGE (attempted, recovered nothing)" if lane.is_silent_outage else ""
        lines.append(
            f"  lane {lane.name} → {lane.attempted} attempted · {lane.resolved} resolved · "
            f"{len(lane.admitted)} new companies · {len(lane.refused)} refused by the cap{outage}"
        )
    return lines


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
    # D-246. `over seniority` is a drop and belongs in the parenthesised accounting; `uncertain
    # band` is NOT — it counts postings inside `shortlisted` — so it is appended after the
    # accounting rather than inside it, where summing the buckets would over-count. It is named
    # at all because nothing else puts the gate's abstain rate in front of the operator daily,
    # and a gate that cannot fire has to be visible as a number.
    # `hidden_hard_filter` is named here as of the drain landing. It was deliberately exempt
    # while it was un-inspectable -- naming a number the operator could not act on is noise --
    # but it is the LARGEST cut in the pipeline (17,891 on run 67, 59% of the corpus), so once
    # `top --include-hard-filter` exists the daily line has to say it is there.
    uncertain = f" · {counts.uncertain_band} uncertain band" if counts.uncertain_band else ""
    # Same treatment as `uncertain_band` and for the same reason: `signal_unmeasured` counts
    # postings inside `shortlisted`, so it is appended after the parenthesised accounting rather
    # than inside it. Named at all because a non-zero value means the zero-signal rule was
    # partly inert on this run, which no other line puts in front of the operator.
    unmeasured = (
        f" · {counts.signal_unmeasured} body signal unmeasured" if counts.signal_unmeasured else ""
    )
    # Named separately because the two halves end on different events (D-439): one on the next
    # run, one only when the owner actions the lead they already hold. Suppressed at 0 so the
    # line does not grow for the case where the distinction does not arise.
    slate_standing = (
        f" ({counts.slate_cap_standing} on your queue)" if counts.slate_cap_standing else ""
    )
    return (
        f"{counts.shortlisted} shortlisted of {counts.considered} considered "
        f"({counts.hidden_hard_filter} hard-filtered, "
        f"{counts.hidden_ineligible} ineligible, {counts.hidden_non_swe} non-SWE, "
        f"{counts.hidden_zero_signal} zero signal, "
        f"{counts.hidden_over_seniority} over seniority, "
        f"{counts.hidden_duplicate} duplicate, "
        f"{counts.hidden_slate_cap} slate-capped{slate_standing}, "
        f"{counts.hidden_applied} already applied, "
        f"{counts.hidden_handled} already handled, "
        f"{counts.hidden_below_cutoff} below cutoff{dead}){uncertain}{unmeasured}"
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
        None,
        "--resume",
        help="Authored résumé YAML (default: {config_dir}/resume.yaml). Cannot be combined with "
        "--project, which supplies each lead's document from the bundle instead.",
    ),
    skip_scan: bool = typer.Option(
        False, "--no-scan", help="Reuse already-fetched postings instead of refetching boards."
    ),
    project: bool = typer.Option(
        False,
        "--project",
        help="Render each lead from the career-profile bundle's projection instead of the "
        "authored résumé. Requires a current projection approval: without one the run refuses "
        "before any lead is consumed, rather than falling back to the authored résumé.",
    ),
    check_liveness: bool = typer.Option(
        True,
        "--check-liveness/--no-check-liveness",
        help="Re-fetch each shortlisted posting and withhold any that answers 404/410. "
        "Turning it off reports liveness as unmeasured, not as zero dead.",
    ),
    queue_root: Path | None = typer.Option(  # noqa: B008
        None,
        "--queue-root",
        help="The delivery queue's own root (default: the delivery queue's own default root, "
        f"{DEFAULT_QUEUE_ROOT}). Left as `None` rather than defaulting to that path here: "
        "`_sync_queue` still resolves the default from `pipeline.runner`'s own module namespace "
        "at call time when this is absent, which is the seam a test redirects by name (T5).",
    ),
) -> None:
    """Run the whole pipeline once, attributing every row it writes to one run."""
    # BEFORE `build_context`, and before anything that could mint a `runs` row: both options
    # describe an active choice of document source, and with both passed every projected lead
    # overwrites the résumé path — so the explicit `--resume` would silently have no effect. What
    # the combination MEANS is P5b's question (the design's §8 lists it among the contracts P5a
    # deliberately leaves open), and until the owner rules it the only honest answer is to refuse.
    # A usage error, not a fatal run: nothing about the store or the bundle is wrong, and a refusal
    # that first created a run row would burn a row per typo.
    if project and resume_path is not None:
        raise typer.BadParameter(
            "--resume names an authored résumé and --project renders each lead from the "
            "career-profile bundle's projection instead; pass one or the other. What the two "
            "together should mean is not decided yet, so this refuses rather than silently "
            "ignoring --resume.",
            param_hint="--resume",
        )
    # ALSO before `build_context`, and before any queue I/O: `BOARDWATCH_DATA_DIR` is how a
    # scratch store gets pointed at (`--data-dir` outranks it — core/settings.py's documented
    # precedence — which is exactly why this checks `ctx.obj is None` rather than the env var
    # alone; a caller that named `--data-dir` on the command line made a visible, deliberate
    # choice, not one an invisible shell variable made for them). Without this, a run against a
    # scratch store still defaults `_sync_queue` to the OWNER'S REAL `~/boardwatch-queue`, which
    # a scratch store then treats as authoritative: consolidation rmtree, drains, and leads
    # pulled back out of `_applied` (T5). Checked here, not inside `_sync_queue`, so the refusal
    # fires before the scan, eligibility and tailor stages do any work at all — not after they
    # have already spent the run's time and then discarded it.
    if queue_root is None and ctx.obj is None and os.environ.get("BOARDWATCH_DATA_DIR"):
        raise typer.BadParameter(
            f"BOARDWATCH_DATA_DIR={os.environ['BOARDWATCH_DATA_DIR']} is set and no --queue-root "
            f"was given; refusing rather than reconciling the real queue at {DEFAULT_QUEUE_ROOT} "
            "against a store BOARDWATCH_DATA_DIR points elsewhere. Pass --queue-root to point the "
            "queue at the same scratch location, or unset BOARDWATCH_DATA_DIR to use the real "
            "store and its real queue together.",
            param_hint="--queue-root",
        )
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
            project=project,
            # Built here rather than inside the pipeline so that which URLs get probed is the
            # CLI's decision. Not an offline switch — the scan stage fetches every configured
            # board, and `--no-scan` is what makes a run offline.
            liveness_prober=build_prober(settings) if check_liveness else None,
            # `None` unless given, same reasoning as `web_cmd`'s `--queue-root` resolution: a
            # relative root would price a shorter destination than the one actually written.
            queue_root=queue_root.expanduser().resolve() if queue_root is not None else None,
        )
    except ScanLockHeldError as exc:
        console.print(str(exc))  # names the blocking pid when the sidecar has one (D-043)
        raise typer.Exit(code=2) from None

    # Net intake and the untailored count are both silent-failure signals: "0 new" is intake
    # death (a provider quietly returns an empty listing), and any untailored count means a lead
    # shipped the generic master. Both leave `fatal` unset, so the log line is where they show.
    degraded_count = sum(1 for lead in summary.tailored if lead.degraded)
    degraded_note = f" ({degraded_count} untailored)" if degraded_count else ""
    console.print(
        f"run {summary.run_id} · {summary.scan_postings_seen} postings seen · "
        f"{summary.scan_new} new · {summary.scan_closed} closed · "
        f"{summary.scan_open_postings} open · {summary.evaluated} evaluated · "
        f"{_shortlist_line(summary)} · "
        f"{len(summary.tailored)} tailored{degraded_note} · {summary.leads_with_pdf} with PDF"
    )
    if summary.scan_empty_complete_guarded:
        # Named, not counted, mirroring `scan_cmd`'s own line (T15): an operator needs to know
        # WHICH board answered empty to tell a degraded provider from a renamed slug apart.
        # Printed only when the guard fired at all — the healthy-run case is an empty list, and
        # a line that prints every day trains the reader to stop looking at it.
        console.print(
            f"  ! {len(summary.scan_empty_complete_guarded)} empty-complete guarded "
            f"({', '.join(sorted(summary.scan_empty_complete_guarded))})",
            markup=False,
        )
    for lead in summary.tailored:
        mark = "✓" if lead.pdf_built else "·"
        console.print(f"  {mark} {lead.company} — {lead.title} → {lead.out_dir}", markup=False)
    # D-274: printed for every run, including one whose coverage could not be read — the
    # launchd job redirects stdout to ~/Library/Logs/boardwatch-run.log, so this is the only
    # place an unattended run's reach is visible without opening a file.
    console.print(f"  board coverage → {_coverage_line(summary)}", markup=False)
    # Beside board coverage, and for the same reason it is printed at all: the launchd job
    # redirects stdout to a log file, and this is the only place an unattended run's lane reach
    # is visible without opening the funnel artifact.
    for line in _lane_lines(summary):
        console.print(line, markup=False)
    if summary.funnel is not None:
        console.print(f"  funnel → {summary.funnel.markdown_path}", markup=False)
    if summary.morning is not None:
        console.print(f"  morning → {summary.morning.markdown_path}", markup=False)
    for err in summary.errors:
        console.print(f"  ! {err}", markup=False)

    if summary.fatal is None and summary.tailored:
        print_next_step(
            console,
            "review the leads above, then `boardwatch track add <#>` after you apply",
        )

    # Only a FATAL condition fails the run. A few unreachable boards and a few leads that
    # would not tailor are the documented norm across 85 watched boards, and `boardwatch scan`
    # already exits 0 for them; making the daily driver exit 1 every day would destroy the
    # exit status as a signal. Both are still counted, printed and persisted above.
    if summary.fatal is not None:
        console.print(f"run {summary.run_id} FAILED: {summary.fatal}", markup=False)
        raise typer.Exit(code=1)
