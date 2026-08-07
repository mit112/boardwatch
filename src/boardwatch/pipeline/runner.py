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
from datetime import timedelta
from pathlib import Path

from rich.console import Console
from sqlalchemy import Engine, select

from boardwatch.core.clock import utcnow
from boardwatch.core.settings import Settings
from boardwatch.eligibility.audit import AuditView, load_audit
from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.engine import ENGINE_KIND, engine_version
from boardwatch.eligibility.preflight import current_identity
from boardwatch.pipeline.freshness import folders_reconcile
from boardwatch.pipeline.funnel_writer import collect_run_funnel
from boardwatch.reports.morning import MorningLead, build_morning, write_morning
from boardwatch.reports.resume_gate import LeadArtifactError, TypstUnavailableError
from boardwatch.reports.run_funnel import (
    ScanContext,
    ShortlistCounts,
    WrittenArtifact,
    write_run_funnel,
)
from boardwatch.reports.tailor import run_tailor
from boardwatch.scan.coordinator import ScanSummary, is_systemic_scan_outage, run_scan
from boardwatch.store.db import ensure_schema
from boardwatch.store.queries import RUN_FAILED, RUN_OK, ensure_run, finish_run, reap_stale_runs
from boardwatch.store.run_funnel_queries import count_eligible_judged_this_run, lead_provenance
from boardwatch.store.tables import postings

DEFAULT_TOP_N = 8


@dataclass
class TailoredLead:
    posting_id: int
    company: str
    title: str
    out_dir: Path
    pdf_built: bool
    # Threaded from the ranker's `RankedPosting` / `run_tailor`'s result rather than
    # re-derived later — they are already computed once here and the morning artifact
    # (P3 item 7) is the only other reader. `pdf_path` is the real compiled path, distinct
    # from `pdf_built`: the latter is a bool the funnel already carries, this is where it is.
    why: str = ""
    score: float = 0.0
    pdf_path: Path | None = None


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
    #
    # None until the ranker actually runs, and NOT a zeroed instance: a fatal scan outage and a
    # missing profile both return before it. A default of considered=0 made the artifact report
    # 0 in / 0 out on those runs and, because the stage is no longer `derived`, list it among
    # the stages whose balance could have failed — asserting the ranker ran and accounted for
    # everything when it never executed.
    shortlist: ShortlistCounts | None = None
    tailored: list[TailoredLead] = field(default_factory=list)
    tailor_failed: int = 0
    # The posting_id of every candidate that failed to tailor, alongside the count above.
    # Threaded through so the cohort-completeness guard (P3 item 9) can reconcile by ID SET
    # against `ranked.visible`, rather than by count — a count identity balances even when one
    # candidate vanished and another was double-counted; an ID-set difference cannot.
    tailor_failed_ids: list[int] = field(default_factory=list)
    # Every Tier-B rewrite row across all leads this run — the fabrication counters (P0 item 8)
    # are folded from these. Empty when LLM tailoring is off, which is an honest zero.
    rewrite_rows: list[dict[str, object]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    fatal: str | None = None
    # Where the per-run funnel artifact landed (P0 item 1). None only when writing it failed,
    # which is reported to the console and never allowed to fail the run.
    funnel: WrittenArtifact | None = None
    # Where the per-run morning artifact landed (P3 item 7). Same fail-safe as `funnel`: a
    # reporting failure is swallowed and reported to the console, never allowed to fail the run.
    morning: WrittenArtifact | None = None

    @property
    def leads_with_pdf(self) -> int:
        return sum(1 for lead in self.tailored if lead.pdf_built)


def _cohort_guard(
    visible_ids: frozenset[int], lead_ids: frozenset[int], failed_ids: frozenset[int]
) -> str | None:
    """P3 item 9 — every SHORTLISTED candidate must reach a terminal state: a lead or a tailor
    failure. `visible_ids - (lead_ids | failed_ids)` is the unaccounted set; comparing SETS
    rather than `len(visible) == len(lead) + len(failed)` is deliberate — a compensating bug
    (one candidate lost, a different one double-counted as a lead) balances the count identity
    but cannot hide inside a set difference.
    """
    unaccounted = visible_ids - (lead_ids | failed_ids)
    if unaccounted:
        ids = ", ".join(str(posting_id) for posting_id in sorted(unaccounted))
        return f"cohort incomplete: {len(unaccounted)} shortlisted candidates unaccounted: {ids}"
    return None


def _zero_output_guard(eligible_judged_this_run: int) -> str | None:
    """P3 item 5 (B5) — 0 leads is provably right IFF this run did no NEW eligible work.

    `eligible_judged_this_run` is run_id-attributed (not a cross-run handled ledger): a
    steady-state day where every eligible posting is a cache hit from a PRIOR run has this at
    0 and is honest. > 0 with 0 leads means new eligible work existed this run and nothing came
    of it — the silent-empty-day this guard exists to catch.
    """
    if eligible_judged_this_run > 0:
        return (
            f"empty day not provably right: {eligible_judged_this_run} eligible postings "
            "judged this run but 0 leads"
        )
    return None


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

    # P3 slice 2 (D-046): drain any crashed/killed prior run before minting this one's row.
    # Never touches the row this run is about to create (it doesn't exist yet). Swallowed and
    # logged, mirroring `_emit_funnel` below: a drain failure must never block a new run.
    try:
        reap_stale_runs(engine, older_than=timedelta(hours=settings.reap_stale_after_hours))
    except Exception as exc:  # noqa: BLE001 - never mask the run's own outcome
        console.print(f"  ! stale-run reap failed: {exc}", markup=False)

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
            # empty day)". `is_systemic_scan_outage` (D-037) is the same predicate
            # `coordinator.py`'s standalone scan uses, so the two can never disagree on the
            # same event. Note this reads the outcome, not a status field.
            attempted = scan_summary.companies
            if is_systemic_scan_outage(
                attempted=attempted,
                complete=scan_summary.complete,
                unchanged=scan_summary.unchanged,
            ):
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
            except TypstUnavailableError as exc:
                # An environment fault, not a per-lead failure (P1a): the binary is either on
                # PATH or it isn't, so every remaining lead would fail identically — abort the
                # stage rather than burn through the whole shortlist re-discovering that.
                summary.fatal = f"typst binary unavailable: {exc}"
                message = f"tailor: {summary.fatal}"
                stage_errors.append(message)
                summary.errors.append(message)
                break
            except LeadArtifactError as exc:
                # Leave no empty folder behind: counting the deliverable by listing the dated
                # directory is the obvious independent check, and a husk would inflate it.
                _remove_if_empty(dest)
                summary.tailor_failed += 1
                summary.tailor_failed_ids.append(posting.posting_id)
                message = f"tailor: posting {posting.posting_id}: {exc}"
                stage_errors.append(message)
                summary.errors.append(message)
                continue
            except Exception as exc:  # one lead failing is not the run failing (P1 item 5)
                # Leave no empty folder behind: counting the deliverable by listing the dated
                # directory is the obvious independent check, and a husk would inflate it.
                _remove_if_empty(dest)
                summary.tailor_failed += 1
                summary.tailor_failed_ids.append(posting.posting_id)
                message = f"tailor: posting {posting.posting_id}: {exc}"
                stage_errors.append(message)
                summary.errors.append(message)
                continue
            if result.rewrites is not None:
                summary.rewrite_rows.extend(result.rewrites)
            summary.tailored.append(
                TailoredLead(
                    posting_id=posting.posting_id,
                    company=posting.company,
                    title=posting.title,
                    out_dir=dest,
                    pdf_built=result.pdf_path is not None,
                    why=posting.why,
                    score=posting.score.total,
                    pdf_path=result.pdf_path,
                )
            )

        # Every lead the ranker produced failed to render. Not "zero was provably right" —
        # zero was produced from a non-empty shortlist, which is a broken résumé path
        # (missing resume.yaml, typst gone), not an honest empty day.
        shortlisted = summary.shortlist.shortlisted if summary.shortlist else 0
        if summary.fatal is None and shortlisted > 0 and not summary.tailored:
            summary.fatal = (
                f"every lead failed to tailor ({summary.tailor_failed}/{shortlisted})"
            )

        # P3 item 5 (B5) — zero-output guard. Only reachable here when `shortlisted == 0` (the
        # `shortlisted > 0` empty case is already fatal above), i.e. a candidate-less day.
        # Checked BEFORE cohort completeness (design's stated order) so the more specific
        # empty-day message wins when both would otherwise fire on the same run.
        if summary.fatal is None and not summary.tailored:
            with engine.connect() as conn:
                identity = current_identity(conn, settings)
                # None only when the profile vanished mid-run after `rank_open_postings`
                # already required one to exist — unreachable in practice. Treated as "no
                # NEW eligible work is knowable", not as suspicious, per the fail-safe stance:
                # ambiguity here must not manufacture a false alarm.
                eligible_judged_this_run = (
                    count_eligible_judged_this_run(
                        conn,
                        profile_hash=identity[0],
                        rules_hash=identity[1],
                        engine_kind=ENGINE_KIND,
                        engine_version=engine_version(),
                        run_id=run_id,
                    )
                    if identity is not None
                    else 0
                )
            summary.fatal = _zero_output_guard(eligible_judged_this_run)

        # P3 item 9 — cohort completeness. Every SHORTLISTED candidate (`ranked.visible`, which
        # EXCLUDES `skipped_not_new` — top_cmd.py:63) must have reached a terminal state: a lead
        # (`summary.tailored`) or a tailor failure (`summary.tailor_failed_ids`). Reconciled by
        # posting_id SET, not by count, so a compensating bug cannot balance.
        if summary.fatal is None:
            visible_ids = frozenset(posting.posting_id for posting in ranked.visible)
            lead_ids = frozenset(lead.posting_id for lead in summary.tailored)
            failed_ids = frozenset(summary.tailor_failed_ids)
            summary.fatal = _cohort_guard(visible_ids, lead_ids, failed_ids)

        # P3 item 6 — filesystem-truth. The leads the DB says this run produced must have a
        # folder on disk. Reuses slice 4's `pipeline/freshness.py` reconciliation rather than a
        # second implementation; only the folder/artifact-row clause, not `funnel_present` or
        # `status`, since neither has been written yet at this point in the run.
        if summary.fatal is None:
            with engine.connect() as conn:
                folder_count, artifact_rows = folders_reconcile(conn, run_id)
            if folder_count != artifact_rows:
                summary.fatal = (
                    f"filesystem-truth: {folder_count} lead folder(s) on disk vs "
                    f"{artifact_rows} tailored artifact row(s) in the store for run {run_id}"
                )

        summary.evaluated = _count_evaluations(engine, run_id)
        return summary
    except BaseException as exc:
        # #4: the finally below closes the row either way. Without recording the exception,
        # a crashed run and a clean empty run are indistinguishable in the ledger — the row
        # reads as finished with no errors. The message is in scope here; do not drop it.
        message = f"pipeline: aborted: {exc!r}"
        stage_errors.append(message)
        # ALSO onto the summary, which is what the funnel artifact reads. Recording it only in
        # stage_errors put it in the `runs` row but left the artifact reporting a crashed run as
        # RECONCILES with no FATAL line and an empty Errors section — and Gate P0 asks the
        # artifact to be answerable on its own.
        summary.errors.append(message)
        if summary.fatal is None:
            summary.fatal = message
        raise
    finally:
        # Tied to `fatal`, not to `stage_errors`: a run that lost one lead to a tailor failure
        # is a successful run with an error, and the artifact's FATAL line is the thing a
        # reader already treats as "this run did not deliver". Keeping the two in step means
        # `status == failed` and a FATAL line in the artifact can never disagree. The crash
        # path sets `summary.fatal` before re-raising, so an abort reaches here as `failed`.
        finish_run(
            engine,
            run_id,
            errors=stage_errors,
            status=RUN_FAILED if summary.fatal is not None else RUN_OK,
        )
        # After finish_run, so the artifact records a finished_at rather than reporting every
        # run as still in progress. Failure to write is reported and swallowed on purpose:
        # this block runs while an exception may be propagating, and raising here would
        # replace the real cause of the failure with a reporting error.
        try:
            summary.funnel = _emit_funnel(engine, settings, summary, scan_summary, day_dir)
        except Exception as exc:  # noqa: BLE001 - never mask the run's own outcome
            console.print(f"  ! funnel artifact not written: {exc}", markup=False)
        # AFTER the funnel: the morning artifact links to `funnel-<run_id>.md` by name rather
        # than by the WrittenArtifact above, so it renders that link even when the funnel
        # itself failed to write (the name is deterministic from run_id either way).
        try:
            summary.morning = _emit_morning(engine, settings, summary, day_dir)
        except Exception as exc:  # noqa: BLE001 - never mask the run's own outcome
            console.print(f"  ! morning artifact not written: {exc}", markup=False)


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
        rewrite_rows=summary.rewrite_rows,
        errors=summary.errors,
        fatal=summary.fatal,
    )
    return write_run_funnel(funnel, day_dir)


def _strongest_evidence(audit: AuditView | None) -> tuple[str | None, str | None]:
    """The strongest cleared requirement's quote, or the eligibility rationale.

    "Strongest" is the longest non-empty quote among `met` requirements — the most specific
    evidenced span available. Falls back to the first requirement carrying a rationale (any
    disposition) when no `met` requirement has a usable quote — e.g. an INELIGIBLE verdict, or
    a met requirement whose stored span failed to resolve. Returns `(None, None)`, never a
    fabricated string, when the audit itself is absent or carries nothing usable.
    """
    if audit is None:
        return None, None
    met_quotes = [req.quote for req in audit.requirements if req.disposition == "met" and req.quote]
    if met_quotes:
        return "quote", max(met_quotes, key=len)
    for req in audit.requirements:
        if req.rationale:
            return "rationale", req.rationale
    return None, None


def _emit_morning(
    engine: Engine,
    settings: Settings,
    summary: PipelineSummary,
    day_dir: Path,
) -> WrittenArtifact:
    """Build the morning artifact (P3 item 7) from this run's already-tailored leads and write
    it beside the funnel.

    Sourced from `summary.tailored` — the SAME population the funnel's Leads table carries —
    never from `digest`/`notify`, which are cursor-scoped to "new since last look" and would
    silently drop a re-tailored lead whose posting was not `new` this run. `why`/`score` were
    already computed once by the ranker and threaded onto `TailoredLead`; `apply_url` is a
    fresh `postings.url` join (one query for every posting_id, mirroring `reports/notify.py`);
    the verdict label and evidence span come from a per-lead `load_audit` call reusing this
    run's own (profile_hash, rules_hash) identity, so the label agrees with what `top`/`show`
    would render for the same posting right now.
    """
    posting_ids = [lead.posting_id for lead in summary.tailored]
    catalog = load_rules(settings.config_dir)

    with engine.connect() as conn:
        identity = current_identity(conn, settings)
        profile_hash, rules_hash = identity if identity is not None else (None, None)
        urls: dict[int, str | None] = {}
        if posting_ids:
            urls = {
                int(row.id): row.url
                for row in conn.execute(
                    select(postings.c.id, postings.c.url).where(postings.c.id.in_(posting_ids))
                ).all()
            }
        provenance = lead_provenance(conn, posting_ids)
        rows: list[MorningLead] = []
        for lead in summary.tailored:
            audit = load_audit(
                conn, lead.posting_id, catalog, profile_hash=profile_hash, rules_hash=rules_hash
            )
            evidence_kind, evidence_text = _strongest_evidence(audit)
            prov = provenance.get(lead.posting_id)
            board = f"{prov.provider}:{prov.board_slug}" if prov is not None else "unknown"
            rows.append(
                MorningLead(
                    posting_id=lead.posting_id,
                    title=lead.title,
                    company=lead.company,
                    board=board,
                    score=lead.score,
                    why=lead.why,
                    verdict_label=(
                        audit.presentation.value if audit is not None else "no_audit_on_record"
                    ),
                    apply_url=urls.get(lead.posting_id),
                    pdf_path=str(lead.pdf_path) if lead.pdf_path is not None else None,
                    evidence_kind=evidence_kind,
                    evidence_text=evidence_text,
                )
            )

    artifact = build_morning(
        run_id=summary.run_id, funnel_name=f"funnel-{summary.run_id}.md", leads=rows
    )
    return write_morning(artifact, day_dir)


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
