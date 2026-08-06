"""The pipeline run — scan, then eligibility, then tailor, all under one `runs` row (D-016).

Before this, no code path had a `run_id` in scope where an evaluation or an artifact was
written: `insert_run` lived inside the scan's file lock, eligibility ran later as a `top`
preflight side-effect, and tailoring ran later still, one posting at a time. The only thing
stitching the three together was `.agent/bin/bw-daily`, gitignored shell that is not part of
the product. This module is what that becomes.

The row is minted here, before the first stage, and finished here, after the last — so
`finished_at` means "the pipeline is done", not "scan is done". Each stage receives the id
rather than minting its own; run standalone, each still mints one, which is what keeps
`run_id IS NULL` meaning solely "predates run attribution".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from rich.console import Console
from sqlalchemy import Engine

from boardwatch.core.settings import Settings
from boardwatch.reports.tailor import run_tailor
from boardwatch.scan.coordinator import ScanLockHeldError, run_scan
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

    Counts are what the funnel artifact (P0 item 3) will read; it is deliberately a plain
    dataclass so that writer needs no new query.
    """

    run_id: int
    scan_postings_seen: int = 0
    scan_open_postings: int = 0
    evaluated: int = 0
    shortlisted: int = 0
    tailored: list[TailoredLead] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

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
    today: date | None = None,
    skip_scan: bool = False,
) -> PipelineSummary:
    """Run scan → eligibility → tailor under one run row and return what each stage did.

    Raises ScanLockHeldError if another scan holds the lock. The run row is finished before
    the exception escapes, so a contended run is recorded as a real run that aborted rather
    than left dangling for `doctor` to report as still running.
    """
    console = console or Console()
    # Deferred: top_cmd imports from the CLI layer, and importing it at module scope makes
    # pipeline -> cli -> pipeline a cycle the moment run_cmd imports this.
    from boardwatch.cli.top_cmd import NoProfileError, rank_open_postings

    run_id = ensure_run(engine, None)
    summary = PipelineSummary(run_id=run_id)

    if not skip_scan:
        console.print("[bold]scan[/bold]")
        try:
            scan_summary = run_scan(engine, settings, run_id=run_id)
        except ScanLockHeldError:
            finish_run(engine, run_id, errors=["scan: lock held by another process"])
            raise
        summary.scan_postings_seen = scan_summary.postings_seen
        summary.scan_open_postings = scan_summary.open_postings
        summary.errors.extend(scan_summary.errors)

    console.print("[bold]eligibility[/bold]")
    try:
        ranked = rank_open_postings(
            engine, settings, limit=top_n, output_console=console, run_id=run_id
        )
    except NoProfileError:
        # Not a crash: a fresh install has no profile yet. The run is real and it produced
        # nothing, which is exactly what the funnel should record.
        summary.errors.append("eligibility: no profile configured; nothing ranked or tailored")
        finish_run(engine, run_id, errors=summary.errors)
        return summary
    summary.shortlisted = len(ranked.visible)

    console.print("[bold]tailor[/bold]")
    day_dir = out_root / (today or date.today()).isoformat()
    for posting in ranked.visible:
        dest = day_dir / _slug(posting.company, posting.posting_id)
        dest.mkdir(parents=True, exist_ok=True)
        try:
            result = run_tailor(
                engine,
                settings,
                posting.posting_id,
                resume_path=resume_path,
                out_dir=dest,
                run_id=run_id,
            )
        except Exception as exc:  # one lead failing is not the run failing (P1 item 5)
            summary.errors.append(f"tailor: posting {posting.posting_id}: {exc}")
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

    # `evaluated` is read off the run's own evaluation rows rather than off the stats object
    # rank_open_postings discards, so the count comes through a different path than the one
    # that produced it (CLAUDE.md: a component's self-report is not verification).
    summary.evaluated = _count_evaluations(engine, run_id)
    finish_run(engine, run_id, errors=summary.errors)
    return summary


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
