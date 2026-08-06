"""The pipeline run — scan, then eligibility, then tailor, all under one `runs` row (D-016).

Before this, no code path had a `run_id` in scope where an evaluation or an artifact was
written: `insert_run` lived inside the scan's file lock, eligibility ran later as a `top`
preflight side-effect, and tailoring ran later still, one posting at a time. The only thing
stitching the three together was `.agent/bin/bw-daily`, gitignored shell that is not part of
the product. This module is what that becomes.

**The scan stage creates the row, and the pipeline finishes it.** That split matters and is
not the rejected "run_id = the scan run" option from D-016: what the id *denotes* is the
pipeline, but the INSERT has to happen where the scan's file lock already protects it.
Minting before the lock would migrate the schema and write a row outside the lock — exactly
what `coordinator.py`'s deferred `ensure_schema` exists to prevent — and would strand a row
whenever another scan holds the lock. With `--no-scan` there is no lock to sit inside, so the
pipeline mints its own.

`finished_at` is stamped once, at the end, by whoever owns the run. Each stage receives the
id rather than minting its own; run standalone, each still mints one, which is what keeps
`run_id IS NULL` meaning solely "predates run attribution" (D-019).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console
from sqlalchemy import Engine

from boardwatch.core.clock import utcnow
from boardwatch.core.settings import Settings
from boardwatch.pipeline.funnel_writer import collect_run_funnel
from boardwatch.reports.run_funnel import (
    ScanContext,
    ShortlistCounts,
    WrittenArtifact,
    write_run_funnel,
)
from boardwatch.reports.tailor import run_tailor
from boardwatch.scan.coordinator import ScanSummary, run_scan
from boardwatch.store.db import ensure_schema
from boardwatch.store.queries import ensure_run, finish_run

DEFAULT_TOP_N = 8


@dataclass
class TailoredLead:
    posting_id: int
    company: str
    title: str
    out_dir: Path
    pdf_built: bool


@dataclass
class PipelineSummary:
    """What one pipeline run did, per stage.

    Counts are what the funnel artifact (P0 item 1) reads; it is deliberately a plain
    dataclass so that writer needs no new query.

    `errors` is every non-fatal problem, for the ledger and the operator. `fatal` is the one
    thing that makes the RUN a failure. They are separate on purpose: with 85 watched boards a
    few dead ones are the documented norm, and `boardwatch scan` already treats them as
    success. If a single unreachable board made the daily driver exit non-zero, the exit
    status would be 1 every day and would stop carrying any information — which is precisely
    the signal destruction the run ledger exists to prevent.
    """

    run_id: int
    scan_postings_seen: int = 0
    scan_open_postings: int = 0
    scan_boards_failed: int = 0
    scan_boards_complete: int = 0
    evaluated: int = 0
    # The ranker's whole population accounting, not just what it showed. `shortlisted` alone
    # is capped at --top and so measures the flag rather than the funnel; the considered count
    # and the four hidden buckets are what let the funnel's shortlist stage reconcile.
    shortlist: ShortlistCounts = field(
        default_factory=lambda: ShortlistCounts(considered=0, shortlisted=0)
    )
    tailored: list[TailoredLead] = field(default_factory=list)
    tailor_failed: int = 0
    errors: list[str] = field(default_factory=list)
    fatal: str | None = None
    # Where the per-run funnel artifact landed (P0 item 1). None only when writing it failed,
    # which is reported to the console and never allowed to fail the run.
    funnel: WrittenArtifact | None = None

    @property
    def leads_with_pdf(self) -> int:
        return sum(1 for lead in self.tailored if lead.pdf_built)


def _slug(company: str, posting_id: int) -> str:
    """A filesystem-safe folder name that stays unique when two roles share a company."""
    keep = [c.lower() if c.isalnum() else "-" for c in company]
    base = "".join(keep).strip("-") or "company"
    while "--" in base:
        base = base.replace("--", "-")
    return f"{base}-{posting_id}"


def run_pipeline(
    engine: Engine,
    settings: Settings,
    *,
    console: Console | None = None,
    top_n: int = DEFAULT_TOP_N,
    out_root: Path,
    resume_path: Path,
    skip_scan: bool = False,
) -> PipelineSummary:
    """Run scan → eligibility → tailor under one run row and return what each stage did.

    Raises ScanLockHeldError if another scan holds the lock. Nothing is written in that case,
    because the row is created by the scan stage inside the lock it failed to acquire.
    """
    console = console or Console()
    # Deferred: top_cmd imports from the CLI layer, and importing it at module scope makes
    # pipeline -> cli -> pipeline a cycle the moment run_cmd imports this.
    from boardwatch.cli.top_cmd import NoProfileError, rank_open_postings

    scan_summary = None
    if not skip_scan:
        console.print("[bold]scan[/bold]")
        # Not wrapped: a contended scan must leave the DB untouched, and it does — the run
        # insert and ensure_schema both live inside the lock it never acquired.
        scan_summary = run_scan(engine, settings, finish=False)
        run_id = scan_summary.run_id
    else:
        ensure_schema(engine)
        run_id = ensure_run(engine, None)

    summary = PipelineSummary(run_id=run_id)
    # Computed before the try so the finally can write the funnel artifact into it even when
    # the run aborts partway — a crashed run is exactly when its funnel is worth having.
    day_dir = out_root / utcnow().date().isoformat()
    # Everything from here to finish_run is guarded: a run row whose finished_at stays NULL is
    # reported by `doctor` as still in progress forever, and accretes one more row per retry.
    # Ctrl-C during the multi-minute tailor loop is the likeliest way to hit this.
    stage_errors: list[str] = []
    try:
        if scan_summary is not None:
            summary.scan_postings_seen = scan_summary.postings_seen
            summary.scan_open_postings = scan_summary.open_postings
            summary.scan_boards_failed = scan_summary.failed
            summary.scan_boards_complete = scan_summary.complete
            # CLAUDE.md's fail-safe table: "systemic outage => fatal (prevents the silent
            # empty day)". Boards were attempted and NOT ONE completed is a DNS/network
            # failure, not a few dead slugs. Reporting success for it is exactly bar metric
            # B5's failure. Note this reads the outcome, not a status field.
            attempted = scan_summary.companies
            if attempted > 0 and scan_summary.complete == 0 and scan_summary.unchanged == 0:
                summary.fatal = (
                    f"systemic scan outage: {attempted} boards attempted, none completed"
                )
            # NOT added to stage_errors: the scan stage already persisted these into
            # errors_json itself, and finish_run appends. Passing them again would record
            # every scan error twice and make any per-run error count uninterpretable.
            summary.errors.extend(scan_summary.errors)

        if summary.fatal is not None:
            stage_errors.append(f"scan: {summary.fatal}")
            summary.errors.append(f"scan: {summary.fatal}")
            return summary

        console.print("[bold]eligibility[/bold]")
        try:
            ranked = rank_open_postings(
                engine, settings, limit=top_n, output_console=console, run_id=run_id
            )
        except NoProfileError:
            # Not a crash: a fresh install has no profile yet. The run is real and produced
            # nothing, which is exactly what the funnel should record — but it IS fatal,
            # because nothing downstream can run.
            summary.fatal = "no profile configured; nothing ranked or tailored"
            stage_errors.append(f"eligibility: {summary.fatal}")
            summary.errors.append(f"eligibility: {summary.fatal}")
            return summary
        summary.shortlist = ShortlistCounts(
            considered=ranked.considered,
            shortlisted=len(ranked.visible),
            hidden_hard_filter=ranked.hidden_hard_filter,
            hidden_non_swe=ranked.hidden_non_swe,
            hidden_ineligible=ranked.hidden_ineligible,
            hidden_below_cutoff=ranked.hidden_below_cutoff,
            skipped_not_new=ranked.skipped_not_new,
        )

        console.print("[bold]tailor[/bold]")
        for posting in ranked.visible:
            dest = day_dir / _slug(posting.company, posting.posting_id)
            try:
                result = run_tailor(
                    engine,
                    settings,
                    posting.posting_id,
                    resume_path=resume_path,
                    out_dir=_ensure_dir(dest),
                    run_id=run_id,
                )
            except Exception as exc:  # one lead failing is not the run failing (P1 item 5)
                # Leave no empty folder behind: counting the deliverable by listing the dated
                # directory is the obvious independent check, and a husk would inflate it.
                _remove_if_empty(dest)
                summary.tailor_failed += 1
                message = f"tailor: posting {posting.posting_id}: {exc}"
                stage_errors.append(message)
                summary.errors.append(message)
                continue
            summary.tailored.append(
                TailoredLead(
                    posting_id=posting.posting_id,
                    company=posting.company,
                    title=posting.title,
                    out_dir=dest,
                    pdf_built=result.pdf_path is not None,
                )
            )

        # Every lead the ranker produced failed to render. Not "zero was provably right" —
        # zero was produced from a non-empty shortlist, which is a broken résumé path
        # (missing resume.yaml, typst gone), not an honest empty day.
        shortlisted = summary.shortlist.shortlisted
        if summary.fatal is None and shortlisted > 0 and not summary.tailored:
            summary.fatal = (
                f"every lead failed to tailor ({summary.tailor_failed}/{shortlisted})"
            )

        summary.evaluated = _count_evaluations(engine, run_id)
        return summary
    except BaseException as exc:
        # #4: the finally below closes the row either way. Without recording the exception,
        # a crashed run and a clean empty run are indistinguishable in the ledger — the row
        # reads as finished with no errors. The message is in scope here; do not drop it.
        stage_errors.append(f"pipeline: aborted: {exc!r}")
        raise
    finally:
        finish_run(engine, run_id, errors=stage_errors)
        # After finish_run, so the artifact records a finished_at rather than reporting every
        # run as still in progress. Failure to write is reported and swallowed on purpose:
        # this block runs while an exception may be propagating, and raising here would
        # replace the real cause of the failure with a reporting error.
        try:
            summary.funnel = _emit_funnel(engine, settings, summary, scan_summary, day_dir)
        except Exception as exc:  # noqa: BLE001 - never mask the run's own outcome
            console.print(f"  ! funnel artifact not written: {exc}", markup=False)


def _emit_funnel(
    engine: Engine,
    settings: Settings,
    summary: PipelineSummary,
    scan_summary: ScanSummary | None,
    day_dir: Path,
) -> WrittenArtifact:
    """Collect the funnel from the store and write both halves beside the day's leads."""
    funnel = collect_run_funnel(
        engine,
        settings,
        run_id=summary.run_id,
        scan=ScanContext(
            ran=scan_summary is not None,
            boards_attempted=scan_summary.companies if scan_summary else 0,
            boards_complete=summary.scan_boards_complete,
            boards_failed=summary.scan_boards_failed,
            postings_seen=summary.scan_postings_seen,
        ),
        shortlist=summary.shortlist,
        tailored=[
            (lead.posting_id, lead.company, lead.title, lead.out_dir, lead.pdf_built)
            for lead in summary.tailored
        ],
        tailor_failed=summary.tailor_failed,
        errors=summary.errors,
        fatal=summary.fatal,
    )
    return write_run_funnel(funnel, day_dir)


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _remove_if_empty(path: Path) -> None:
    try:
        path.rmdir()
    except OSError:
        pass  # non-empty (partial output worth keeping) or already gone


def _count_evaluations(engine: Engine, run_id: int) -> int:
    from sqlalchemy import func, select

    from boardwatch.store.tables import eligibility_evaluations

    with engine.connect() as conn:
        return int(
            conn.execute(
                select(func.count())
                .select_from(eligibility_evaluations)
                .where(eligibility_evaluations.c.run_id == run_id)
            ).scalar_one()
        )
