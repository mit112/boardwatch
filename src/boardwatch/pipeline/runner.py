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

from collections import Counter
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, replace
from datetime import timedelta
from itertools import zip_longest
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING

import httpx
from rich.console import Console
from sqlalchemy import Engine, select

from boardwatch.core.clock import utcnow
from boardwatch.core.dedup import Suppression
from boardwatch.core.lineage import ResumeSourceLineage
from boardwatch.core.politeness import Fetcher
from boardwatch.core.regroup import plan_regrouping
from boardwatch.core.settings import Settings
from boardwatch.delivery.api import resolve_owner_name
from boardwatch.delivery.queue import DEFAULT_QUEUE_ROOT, reconcile_queue, sync_queue
from boardwatch.eligibility.audit import AuditView, load_audit
from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.preflight import current_identity
from boardwatch.lanes.admission import CompanyBudget
from boardwatch.lanes.base import Lane, LaneResult
from boardwatch.lanes.facets import (
    MINED_FACET_WINDOW_DAYS,
    LaneFacets,
    mined_facet_candidates,
    role_facets,
    surviving_mined_facets,
)
from boardwatch.lanes.hiringcafe import HiringCafeLane
from boardwatch.lanes.jobapps import JobAppsLane
from boardwatch.lanes.linkedin import LinkedInLane, search_urls
from boardwatch.notify.alert_escalation import escalate_alerts
from boardwatch.notify.apply_lane_drought import check_apply_lane_drought
from boardwatch.notify.corpus_regression import check_corpus_regression
from boardwatch.notify.delivery_drought import check_delivery_drought
from boardwatch.notify.heartbeat import send_heartbeat
from boardwatch.notify.intake_death import check_intake_death
from boardwatch.notify.liveness_blind import check_liveness_blind
from boardwatch.notify.scan_health import scan_outage_alert
from boardwatch.pipeline.death_probe import sweep_unwatched_deaths
from boardwatch.pipeline.freshness import folders_reconcile
from boardwatch.pipeline.funnel_writer import collect_run_funnel
from boardwatch.pipeline.liveness import LivenessProber, check_leads
from boardwatch.pipeline.policy import run_policy_version
from boardwatch.profile_bundle.paths import resolve_bundle_root
from boardwatch.projection.errors import ProjectionError
from boardwatch.projection.run import (
    ISSUE_SCOPE,
    ProjectionAvailability,
    ProjectionLeadOutcome,
    ProjectionRunContext,
    classify_availability,
    classify_lead_outcome,
    project_for_posting,
    resolve_projection_run,
)
from boardwatch.projection.scoring import DEFAULT_SCORER_ID
from boardwatch.reports.board_coverage import CoverageReport as BoardCoverageReport
from boardwatch.reports.board_coverage import build_report as build_board_coverage_report
from boardwatch.reports.morning import MorningLead, build_morning, write_morning
from boardwatch.reports.resume_gate import LeadArtifactError, RenderToolMissingError
from boardwatch.reports.run_funnel import (
    DeathProbeReport,
    LaneReport,
    LivenessCheck,
    ProviderFetchCost,
    ScanContext,
    ShortlistCounts,
    StageDuration,
    WrittenArtifact,
    write_run_funnel,
)
from boardwatch.reports.tailor import ResumeLineageMismatch, default_compile_runner, run_tailor
from boardwatch.scan.apply import apply_board
from boardwatch.scan.coordinator import (
    ScanSummary,
    is_systemic_scan_outage,
    run_scan,
    systemic_scan_outage_reason,
)
from boardwatch.store.coverage_queries import load_board_coverage
from boardwatch.store.db import ensure_schema
from boardwatch.store.facet_queries import delivered_postings, facet_trials
from boardwatch.store.ledger_queries import record_disposition
from boardwatch.store.queries import (
    RUN_FAILED,
    RUN_OK,
    append_run_error,
    company_exists,
    ensure_run,
    finish_run,
    get_profile,
    reap_stale_runs,
    upsert_lane_company,
)
from boardwatch.store.regroup import apply_merges, job_anchors, protected_job_ids
from boardwatch.store.run_funnel_queries import lead_provenance
from boardwatch.store.tables import postings
from boardwatch.tailor.coverage import CoverageReport
from boardwatch.tailor.load import ResumeLoadError
from boardwatch.tailor.persona import PersonaError
from boardwatch.tailor.render.latex import TemplateArtifactError

if TYPE_CHECKING:
    # Type-only. `top_cmd` imports from the CLI layer, and importing it at runtime module scope
    # makes pipeline -> cli -> pipeline a cycle the moment `run_cmd` imports this — which is why
    # `run_pipeline` imports it inside the function body. `from __future__ import annotations`
    # keeps the annotation below a string, so nothing is evaluated at import time.
    from boardwatch.cli.top_cmd import RankedPosting

# A display limit, never a filter: everything beyond it is counted into `capped_by_top_n` and
# stays status='open'.
#
# D-272 raised this 8 -> 40 because 8 discarded 3,502 postings per run that had cleared every
# gate, and because **40 matched job-apps' measured median of 42 A DAY**. That justification was
# per-DAY and it did not survive D-288: the launchd job now fires 8 times a day, so 40 per RUN is
# 320 a day — 7.6x the median it was chosen to match. The two decisions were taken separately and
# neither noticed the other.
#
# Lowered to 10 (D-293, Mit's ruling) as a HOLDING value, not a new equilibrium. The cost of this
# cap is the render — every lead is a tailored résumé and a PDF — and D-292 measured that ~51% of
# what currently reaches the shortlist is not a software role at all. Producing 320 résumés a day
# against a half-junk pile is the waste this avoids; 10 x 8 runs = 80/day, which still clears
# B1's >= 10 net-new leads/day comfortably.
#
# **Do not raise this until the D-293 precision work has landed.** 0 was considered and REFUSED:
# it produces no leads at all, so it fails B1 outright and would stall the provisional pass while
# Gate P3's clean-tick counter kept running.
DEFAULT_TOP_N = 10

# A lane is constructed from `Settings` rather than from nothing, so the one knob it owns —
# `lane_posting_budget`, the ceiling on JD-body GETs it may make in a run — reaches it without
# the lane importing config itself. `LaneResult` is the only thing it hands back.
#
# The second argument is the run's facets, and it is passed in for a reason a default could
# not serve: they are derived from the user's PROFILE row and her own delivered leads, both of
# which live in the store, and a lane that reached into the store to find its own search terms
# would be both untestable and the one place a hardcoded role query could hide. Explicit at every
# registration site, so a new lane cannot quietly forget to be multi-tenant.
#
# The two halves arrive APART. Every faceted lane gets `profile` — those are the titles the user
# asked for. `mined` is this repo's inference from her delivered leads, and it goes only to the
# lane whose own conversion record is the evidence for it, so mining cannot quietly spend another
# lane's request budget.
LaneFactory = Callable[[Settings, LaneFacets], Lane]

# The lane registry: the name a user writes in `settings.lanes_enabled` -> a factory for it. A
# MAPPING and not a branch inside `_run_lanes`, so a second lane is one row here and no change
# to the stage that drives it.
#
# A name in `lanes_enabled` with no row here is reported into `summary.errors` and skipped —
# never silently ignored, because a typo in config would then be indistinguishable from a lane
# that ran and found nothing, which is the exact absent-versus-zero confusion the acquisition
# tally exists to prevent.
#
# Registered is NOT enabled: `settings.lanes_enabled` is empty by default, so nothing in this
# map runs until an operator names it. Registration only makes a lane reachable.
LANE_FACTORIES: dict[str, LaneFactory] = {
    # `lane_search_pages` reaches hiring.cafe as of the SSR re-point (D-393): `&page=N` was
    # measured on 2026-08-31 to return a disjoint hit set, so the setting now buys real depth
    # here rather than promising depth the lane cannot deliver.
    HiringCafeLane.name: lambda settings, facets: HiringCafeLane(
        posting_budget=settings.lane_posting_budget,
        search_facets=facets.profile,
        search_pages=settings.lane_search_pages,
    ),
    # BOTH lanes now read `lane_search_pages`, through different URL builders: LinkedIn's
    # `start=` is a probed, working ITEM offset, while hiring.cafe's `&page=` is a page number
    # on the SSR surface D-393 approved. The older note here said hiring.cafe had no working
    # paging parameter; that was true of the retired `/jobs/*` form only.
    #
    # LinkedIn is still the only lane handed the MINED facets, and that reason is unchanged: the
    # trial record that prunes a barren mined term is this lane's own `keywords=` provenance
    # (`store.facet_queries`). Handing them to a lane whose acquisitions leave no such record
    # would buy searches nothing could ever measure or retire.
    LinkedInLane.name: lambda settings, facets: LinkedInLane(
        posting_budget=settings.lane_posting_budget,
        search_facets=facets.profile + facets.mined,
        search_pages=settings.lane_search_pages,
    ),
    # Reads job-apps' discovery tree off the local disk (D-385). It takes neither the posting
    # budget nor the facets: there are no requests to bound, and the source is already a
    # filtered set rather than a search this lane composes. `facets` is still accepted by the
    # factory signature, which is what keeps every registration site uniform.
    JobAppsLane.name: lambda settings, facets: JobAppsLane(
        source_dir=settings.jobapps_discovery_dir,
        queue_dir=settings.jobapps_queue_dir,
    ),
}

# The UA the lane fetcher sends. Not boardwatch's identifying UA, and NOT app impersonation:
# no lifted API key, no vendor app headers, no `verify=False`. That pattern is why the Indeed
# lane is parked, and reusing it here would park this one too. What this is instead is an
# ordinary browser UA against an ordinary public web page, which is the same request a person
# opening that page makes.
_LANE_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


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
    # P4 item 6: this lead's keyword-coverage report, carried for the morning artifact and the
    # funnel's coverage summary. None when the measurement was unavailable — never a veto.
    coverage: CoverageReport | None = None
    # True when the JD-tailored PDF failed its compile/layout gate and this lead shipped the
    # untailored master résumé instead — `run_tailor`'s fail-safe fallback. Threaded from
    # `TailorResult.degraded` so a SYSTEMATIC degrade (every lead shipping generic while the run
    # still prints green) surfaces as a count on the run line, not only in the artifact meta.
    degraded: bool = False


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
    # Net intake this run. Surfaced on the CLI summary line because "0 new across the whole
    # corpus" is the likeliest failure of a system left unattended for weeks: a provider that
    # returns an empty-but-`complete` listing is NOT a scan outage (is_systemic_scan_outage
    # stays False on unchanged/complete > 0) and yields zero leads with no fatal, so the number
    # has to be visible rather than buried in `evaluated: 0`.
    scan_new: int = 0
    scan_closed: int = 0
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
    # The subset of `tailor_failed_ids` the résumé gate refused DETERMINISTICALLY
    # (`LeadArtifactError`), which is what earns a permanent `skipped` disposition. An
    # unclassified failure is excluded on purpose: it may be transient, and a permanent
    # disposition on a transient fault silently deletes a real lead (P6 slice 2).
    unshippable_ids: list[int] = field(default_factory=list)
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
    # `None` here withholds the heartbeat, exactly as a `None` funnel does — the digest is where
    # this run's alerts are delivered, so a run that could not write one warned nobody.
    morning: WrittenArtifact | None = None
    # D-274. This run's board-coverage report, loaded ONCE in the finally block and shared by
    # both artifacts. `None` means the load failed (reported to the console), never that
    # coverage is zero.
    board_coverage: BoardCoverageReport | None = None
    # P6 slice 2: postings moved onto a canonical job this run, and the groups left ungrouped.
    # Refusals are carried rather than dropped — a refusal that is invisible is a leak in the
    # same way an unlistable suppression is.
    regrouped: int = 0
    # P6 item 6. `None` means the shortlist was NOT probed, which is not the same as "probed and
    # none were dead" — the D-022/D-023 rule. A run with no prober reports the check as
    # unmeasured rather than claiming a clean liveness result it never took.
    liveness_checked: int | None = None
    liveness_dead: int | None = None
    liveness_unknown: int | None = None
    # A SUBSET of `liveness_unknown`, not a fourth partition member: these were gone-statuses
    # forgiven for arriving through a redirect. Counted separately because a rise here with
    # `liveness_dead` at 0 is the signature of the detector being disarmed rather than of a
    # healthy corpus.
    liveness_gone_after_redirect: int | None = None
    # The postings withheld as gone, kept by ID rather than by count so the cohort guard can
    # reconcile SETS. They are not tailor failures and not leads; they never entered the loop.
    dead_lead_ids: list[int] = field(default_factory=list)
    # P5a — the run-scoped projection verdict. Decided by the `--project` preflight, and re-decided
    # only if a RUN-SCOPED cause surfaces later inside the per-lead loop: `select()` raises
    # `PINNED_SET_COMPILE_FAILED`, `PINNED_SET_EXCEEDS_BUDGET` and `COMPILE_INFRASTRUCTURE_FAILURE`
    # while building one lead, and all three are run-invariant, so the run's verdict is what they
    # change — never one lead's outcome.
    #
    # `None` means the flag was NOT passed, which is not the same as `AVAILABLE`: a run that never
    # asked has no verdict to report, and defaulting to `AVAILABLE` would claim a resolve that
    # never happened. Anything other than `AVAILABLE` is accompanied by `fatal`, so the two can
    # never disagree about whether the run delivered.
    #
    # This enum member — never the `fatal` STRING — is the typed cause. Nothing classifies a
    # projection failure by matching that message.
    projection_availability: ProjectionAvailability | None = None
    # Per-lead projection outcomes, one increment per attempted lead. A `Counter`, deliberately
    # left EMPTY rather than pre-seeded with a zero per member: an outcome that never occurred is
    # ABSENT, not zero, so a reader can omit a funnel stage entirely instead of printing a row of
    # zeros for a bucket nothing reached.
    projection_outcomes: Counter[ProjectionLeadOutcome] = field(default_factory=Counter)
    # The postings whose PROJECTION failed, kept by ID beside the counter above for the same reason
    # `dead_lead_ids` is: the cohort guard reconciles SETS. A THIRD terminal state, exactly like a
    # withheld-as-gone lead — not a lead, and deliberately not a `tailor_failed`: the tailor stage
    # never ran for these, so folding them into that count would make it a lie and would hide the
    # projection drops inside a bucket whose reason names the wrong stage.
    #
    # They earn no `skipped` disposition either. Only a refusal the RÉSUMÉ earned is permanent
    # (`LeadArtifactError.is_deterministic`); a projection that could not be built is the owner's
    # bundle or the machine, and burying the lead for it would delete an opportunity that
    # tomorrow's run would have built.
    projection_failed_ids: list[int] = field(default_factory=list)
    # One entry per enabled lane that RETURNED a result (JD-acquisition spec §4). Empty is the
    # default and means no lane ran — `settings.lanes_enabled` ships `()`. A lane that RAISED is
    # absent here and named in `errors` instead, which is the honest pair: it produced no counts,
    # and an entry of zeros would claim it attempted work and recovered nothing.
    lanes: list[LaneReport] = field(default_factory=list)
    # D-325. What the measured-death sweep did to the postings no board scan enumerates.
    # `None` means the sweep did NOT run — no prober, or it raised — which is not the same as a
    # sweep that closed nothing. `closed = 0` is in fact the EXPECTED reading: sensitivity is
    # 6.7% against a control of proven-closed postings, so a zero here is weak evidence about
    # the class and must not be read as one.
    death_probe: DeathProbeReport | None = None
    # Wall clock per stage, in the order the stages ran, filled in by `_StageClock` below.
    # Empty means the run never reached its first mark; the funnel reports that as timed-with-
    # no-boundary rather than as untimed, which is `None` and is what a pre-D-343 artifact has.
    stage_durations: list[StageDuration] = field(default_factory=list)

    @property
    def leads_with_pdf(self) -> int:
        return sum(1 for lead in self.tailored if lead.pdf_built)


class _StageClock:
    """Wall clock between pipeline stage boundaries.

    Boundaries, not wrappers. Wrapping each stage in a context manager would mean reindenting
    the whole pipeline body and would still lose the cost of a stage that `return`s early;
    marking after each stage costs one line per stage and charges any unmarked work to the
    next mark, so consecutive durations sum to the run and an unaccounted block is a visible
    row rather than a missing total.

    `perf_counter`, not `utcnow`, for the same reason `scan/workers.py` uses it: these are
    durations, and a wall-clock subtraction is wrong across an NTP step.
    """

    def __init__(self) -> None:
        self._last = perf_counter()
        self.durations: list[StageDuration] = []

    def mark(self, name: str) -> None:
        """Close the stage that just ended. `name` names the work BEHIND this boundary."""
        now = perf_counter()
        self.durations.append(StageDuration(name=name, seconds=now - self._last))
        self._last = now


def _lane_fetcher(settings: Settings) -> Fetcher:
    """The lane's own `Fetcher`, carrying a browser UA, kept SEPARATE from the scan's.

    Two instances rather than one client with a swapped header, because the six ATS providers
    keep the honest identifying UA: that is the D22 politeness contract, and an aggregator's
    edge behaviour is no reason to stop identifying ourselves to boards that answer us honestly.

    The cost is real and is why the separation is stated rather than assumed: per-host pacing
    state lives per `Fetcher` instance, so these two do not share a delay.

    **THE HIRING.CAFE LANE NOW DOES TARGET A PROVIDER HOST**, and the two halves of what that
    used to rule out are answered separately rather than together.

    * IDENTITY is preserved outright. That lane restores `politeness.identifying_user_agent()`
      per request for a provider board (`Fetcher.get(headers=...)`), so a board that answers us
      honestly still gets the honest UA. D22 is unweakened; only the aggregator sees the
      browser UA, which is what D-369 bought it.
    * PACING is weakened in one narrow way, and it is bounded rather than argued away: the two
      instances keep separate per-host state, so the lane's first request to a provider host is
      not spaced against the scan's last one. Nothing CONCURRENT results — `run()` runs the
      scan stage, then the projection preflight, then this stage, strictly in that order, so
      the two never have a request in flight at the same time. What remains is that one
      boundary request can fall inside the >=1.0s window. Within the lane stage the contract
      holds unchanged, because one `Fetcher` serves every lane and its per-host lock is held
      for each request's full duration.
    """
    return Fetcher(
        settings,
        httpx.Client(
            headers={"User-Agent": _LANE_USER_AGENT}, timeout=30.0, follow_redirects=True
        ),
    )


def _run_lanes(
    engine: Engine, settings: Settings, run_id: int
) -> tuple[list[LaneReport], list[str]]:
    """Run every enabled lane; return what each did and every non-fatal problem.

    **A lane may never fail the run.** A lane is additive breadth: the corpus without it is
    exactly the corpus this pipeline has always ranked, so the fail-safe direction is open — the
    same direction an unreachable board already gets, and for the same reason. An aggregator
    that is down, has moved its markup, or has started refusing us must cost the run its extra
    reach and nothing else. The catch is therefore broad and per LANE, so one lane's failure
    does not take a second lane's results with it.

    The failure is still LOUD: it lands in `summary.errors`, which the run row persists and the
    CLI prints, and the lane is absent from the reported list rather than present with zeros.
    """
    reports: list[LaneReport] = []
    errors: list[str] = []
    if not settings.lanes_enabled:
        # No client is constructed at all on the default path, so a run with lanes off opens no
        # extra connection pool and sends nothing anywhere.
        return reports, errors
    # Read ONCE for the stage, not once per lane: it is the same profile for every lane, and a
    # second read could only differ by racing a `profile set` mid-run.
    facets = _lane_facets(engine)
    # ONE fetcher for the whole stage. Pacing is per-host inside it, so lanes on different hosts
    # do not block each other, and two lanes that ever shared a host would correctly serialize.
    fetcher = _lane_fetcher(settings)

    # Lanes are RESOLVED before anything is submitted, so an unregistered name is reported
    # without a worker ever being started for it, and the resolved order is the one
    # `lanes_enabled` declares.
    resolved: list[tuple[str, Lane]] = []
    for name in settings.lanes_enabled:
        factory = LANE_FACTORIES.get(name)
        if factory is None:
            registered = ", ".join(sorted(LANE_FACTORIES)) or "none"
            errors.append(f"lane {name}: not a registered lane (registered: {registered})")
            continue
        try:
            resolved.append((name, factory(settings, facets)))
        except Exception as exc:  # noqa: BLE001 - additive breadth never fails the run
            errors.append(f"lane {name}: collection failed: {exc!r}")
    if not resolved:
        return reports, errors

    # PARALLEL fetch, SERIAL apply — the same shape `scan/coordinator.py` uses, and for the same
    # reason: `apply_board` is the pipeline's single writer, so it runs in the CONSUMING loop
    # below and never in a worker. Two lanes applying at once would be two writers on one
    # SQLite store.
    #
    # `max_workers` is the lane count and is deliberately NOT a setting. It is bounded by
    # `LANE_FACTORIES` (two today), the per-host pace — not the worker count — is what limits
    # request rate, and a knob here would imply a tuning decision that does not exist.
    #
    # What this buys is bounded by the SLOWEST lane, not divided by the lane count: run 129's
    # lanes issued ~85 requests to hiringcafe and ~166 to linkedin, so the pacing floor moves
    # from their sum to their max and a third lane would be nearly free behind linkedin. The
    # apply half does not move at all. Do not expect a speedup proportional to lanes.
    by_name: dict[str, LaneReport] = {}
    with ThreadPoolExecutor(max_workers=len(resolved)) as pool:
        future_map = {
            pool.submit(_fetch_lane, engine, settings, lane, fetcher): (name, lane)
            for name, lane in resolved
        }
        # `as_completed`, so the first lane to finish fetching starts applying while the others
        # are still on the network. Order is restored below.
        for future in as_completed(future_map):
            name, lane = future_map[future]
            try:
                fetched = future.result()
            except Exception as exc:  # noqa: BLE001 - additive breadth never fails the run
                # Same message as before the split: a lane whose FETCH raised is reported and
                # absent from `reports`, never present with zeros.
                errors.append(f"lane {name}: collection failed: {exc!r}")
                continue
            try:
                by_name[name] = _apply_lane(engine, lane, fetched, run_id)
            except Exception as exc:  # noqa: BLE001 - one lane's apply must not take another's
                errors.append(f"lane {name}: collection failed: {exc!r}")

    # Back into `lanes_enabled` order. `as_completed` yields by completion, which would make the
    # funnel's lane list order depend on which aggregator answered first — a diff in every
    # artifact for no reason, and a fixture that passes or fails by race.
    reports.extend(by_name[name] for name, _ in resolved if name in by_name)
    return reports, errors


def _lane_facets(engine: Engine) -> LaneFacets:
    """The run's two facet sources: the user's stated targets, and the ones her outcomes support.

    An absent profile is every store before onboarding runs, and an absent one yields NO facets
    rather than an error: a lane is additive breadth, so it must still run unfaceted, exactly as
    it did before the facet existed. `getattr` matches `rank.heuristic`'s read of the same
    column, which is nullable.

    Mining runs on the SAME connection and is evidence-gated end to end, so a store with no
    delivered leads yields no mined facets and the lanes ask exactly what they asked before.
    Three reads, in the order the two rules need them: what the profile asks for, what the
    delivered leads support, and — for those candidates only — what each has already bought.
    """
    cutoff = utcnow() - timedelta(days=MINED_FACET_WINDOW_DAYS)
    with engine.connect() as conn:
        row = get_profile(conn)
        profile = role_facets(getattr(row, "target_titles_json", None)) if row is not None else ()
        candidates = mined_facet_candidates(delivered_postings(conn, since=cutoff), profile)
        if not candidates:
            return LaneFacets(profile=profile)
        # Built by the lane's own request builder rather than reassembled here, so the string a
        # trial is looked up under is byte-identical to the one the lane would request. A second
        # statement of that URL shape here could drift from the first without failing anything.
        urls = dict(zip(candidates, search_urls(candidates), strict=True))
        by_url = facet_trials(conn, tuple(urls.values()), since=cutoff)
        trials = {term: by_url[url] for term, url in urls.items() if url in by_url}
    return LaneFacets(profile=profile, mined=surviving_mined_facets(candidates, trials))


def _collect_lane(
    engine: Engine, settings: Settings, lane: Lane, fetcher: Fetcher, run_id: int
) -> LaneReport:
    """Drive ONE lane end to end: fetch it, then land what it collected.

    Both halves in one call, on the calling thread. `_run_lanes` does NOT use this — it needs the
    halves apart, so it can overlap the fetches and keep the applies serial. This stays because a
    single lane driven start to finish is still the honest unit for a caller with one lane, and
    because it is the seam the lane-stage tests exercise directly.

    The substance lives in the two halves: `_fetch_lane` owns the admission closure and the
    concurrency argument, `_apply_lane` owns the single-writer rule.
    """
    fetched = _fetch_lane(engine, settings, lane, fetcher)
    return _apply_lane(engine, lane, fetched, run_id)


@dataclass(frozen=True)
class _FetchedLane:
    """One lane's network half, carried from the fetch phase to the serial apply phase.

    A frozen carrier rather than a tuple because `_run_lanes` holds one per lane across a thread
    boundary and the apply half reads all three fields; a positional tuple there is the shape
    that silently transposes `budget` and `result` on the next edit.
    """

    result: LaneResult
    budget: CompanyBudget
    fetch_seconds: float


def _lane_company_cap(settings: Settings, lane_name: str) -> int | None:
    """This lane's cap on new companies: its override if one is named, else the shared default.

    `"unlimited"` becomes `None`, which is `CompanyBudget`'s own uncapped sentinel — translated
    here rather than in `Settings` so `CompanyBudget` stays the one place that decides what
    "no cap" means.
    """
    override = settings.lane_new_companies_per_run_overrides.get(lane_name)
    if override is None:
        return settings.lane_new_companies_per_run
    return None if override == "unlimited" else override


def _fetch_lane(
    engine: Engine, settings: Settings, lane: Lane, fetcher: Fetcher
) -> _FetchedLane:
    """A lane's PACED NETWORK half — everything before the first write. Runs off the main thread.

    Split from the apply half so `_run_lanes` can overlap lanes on DIFFERENT hosts while
    `apply_board`, the pipeline's single writer, stays serial. Safe to run concurrently for two
    reasons that are properties of code this function does not own, so both are stated here:

    * `Fetcher` is thread-safe BY DESIGN and already used this way by the scan. It keeps a
      `threading.Lock` per host, held for a request's FULL duration, and paces INSIDE that lock.
      So two lanes on one host serialize and the 1 req/s contract holds unchanged — running
      lanes concurrently is NOT a load increase on any third party, which is what keeps this out
      of the owner-gated pacing question.
    * `budget` is per LANE, constructed here, so no two threads share one. The cap was always
      per lane; this changes nothing about it.

    The admission closure is the substantive half of the cap and it lives HERE, with the runner,
    because it needs the store. `CompanyBudget.admit()` has no notion of *new* and deliberately
    does not build one (`lanes/admission.py` says so in its own docstring): without the
    is-it-known check every one of the ten slots goes to a company already stored, reach never
    widens, and the refusal list looks exactly like a normal capped run — a control failure that
    nothing reports. An already-known company is therefore admitted FREE and is not charged.

    Each `admits` call opens and closes its OWN short connection. Holding one open across
    `collect()` would pin a SQLite reader — and its read snapshot — for the whole of the lane's
    paced network work, blocking WAL checkpointing and standing in the path of a migration for
    minutes. The protocol calls `admits` once per distinct `(provider, slug)`, so this is a few
    dozen calls a run, which is nothing beside a one-second-per-host fetch pace. Under
    concurrency those are SQLite READERS, which WAL permits alongside each other and alongside
    the single writer.
    """
    budget = CompanyBudget(_lane_company_cap(settings, lane.name))

    def admits(provider: str, slug: str) -> bool:
        with engine.connect() as conn:
            if company_exists(conn, provider=provider, slug=slug):
                return True
        return budget.admit(provider, slug)

    # `perf_counter` for the same reason `_StageClock` uses it: these are durations, and a
    # wall-clock subtraction is wrong across an NTP step.
    started = perf_counter()
    result = lane.collect(fetcher, admits)
    return _FetchedLane(result=result, budget=budget, fetch_seconds=perf_counter() - started)


def _apply_lane(
    engine: Engine, lane: Lane, fetched: _FetchedLane, run_id: int
) -> LaneReport:
    """Land one lane's collected companies. **Runs on the main thread, always.**

    `apply_board` is the pipeline's single writer and this function is where it is called, so
    keeping this out of the worker pool is the whole reason the fetch/apply split exists. Two
    lanes applying concurrently would put two writers on one SQLite store.
    """
    result = fetched.result
    budget = fetched.budget
    apply_started = perf_counter()
    for company in result.snapshots:
        # `upsert_lane_company` is called for EVERY snapshot, including a company the store
        # already holds — the convergence case a lane exists to produce. It is conflict-safe by
        # design and leaves an existing row's `source` and `watched` alone, so this can never
        # relabel a registry company or unwatch a board the user watches; running it
        # unconditionally is what guarantees a `company_id` to apply against without a branch.
        #
        # `watched=False` is what the upsert writes for a NEW row, and it is load-bearing:
        # `scan/coordinator` looks a watched company's provider up in the six-provider map and
        # appends `unknown provider` to `summary.errors` on a miss. A watched company keyed to a
        # lane's own provider name would add that line to every run forever, and ten new
        # companies a run makes the run error count meaningless inside a week.
        #
        # One short transaction per company, not one around the loop: `apply_board` opens and
        # commits its own per-board transaction, which is the per-board atomicity guarantee an
        # outer transaction would silently take away.
        with engine.begin() as conn:
            # The id comes back from the upsert rather than from a second select on
            # `(provider, slug)`: the row the upsert resolved to may be stored under a
            # different SLUG CASE than the lane offered, and re-selecting by the lane's
            # spelling would then find nothing (`queries.stored_slug`).
            company_id = upsert_lane_company(
                conn,
                provider=company.provider,
                slug=company.slug,
                # The employer's display name, which the funnel's leads table and the morning
                # artifact render. It only reaches `companies.name` on INSERT: the upsert leaves
                # an existing row's name alone, so a lane can never overwrite a curated registry
                # name — which matters because `scan/apply.py` feeds `companies.name` into the
                # `cross_host` posting identity, so rewriting it would silently re-key that
                # company's identities.
                name=company.name,
            )
        # `scan_kind="lane"`, and the default is not good enough here: `apply_board` writes a
        # `board_scans` row every time, and board coverage outer-joins that table on
        # `(company_id, run_id)`. A lane touching an already-watched company would otherwise
        # emit a SECOND row for that pair, so the company appears twice — once measured, once
        # enumerated-only — inflating `corpus_boards` and every bucket count.
        apply_board(engine, company.snapshot, company_id, run_id, scan_kind="lane")

    tally = result.tally
    return LaneReport(
        name=lane.name,
        counts=tally.counts,
        attempted=tally.attempted,
        resolved=tally.resolved,
        is_silent_outage=tally.is_silent_outage,
        # Only companies the store did NOT already hold reach the budget, so `admitted` is the
        # reach this run ADDED rather than the companies the lane touched.
        admitted=budget.admitted,
        refused=budget.refused,
        # How deep each search actually read. Carried from the lane rather than recomputed from
        # `lane_search_pages`, which is the CEILING and not what was fetched — a facet that ran
        # out of results after two pages is exactly the case the setting cannot report.
        search_pages=result.search_pages,
        # Paced network work, and the half upstream throttling shows up in. Carried from the
        # fetch phase, which may have run on another thread.
        fetch_seconds=fetched.fetch_seconds,
        # The `apply_board` loop — the single writer, and the half no amount of lane
        # parallelism can shorten.
        apply_seconds=perf_counter() - apply_started,
    )


def _retract_projected(outcomes: Counter[ProjectionLeadOutcome]) -> None:
    """Un-count one `PROJECTED` lead, for a lead whose projection is repudiated after the fact.

    One caller: the `ResumeLineageMismatch` arm. The sidecars landed, so the lead was counted, and
    then `run_tailor` proved the document it was handed is not the one that lineage describes —
    before parsing or rendering anything. So the lead never advanced out of projection, and the
    count has to say so: a reader's only balance is `served == projected + drops`, and a lead
    counted in both terms makes that arithmetic unclosable.

    Deletes the key at zero rather than leaving `PROJECTED: 0` behind. `projection_outcomes` is
    empty by default precisely so an outcome that never occurred is ABSENT rather than zero — a
    residual zero would claim projection ran and advanced nothing, which is a different report.
    """
    outcomes[ProjectionLeadOutcome.PROJECTED] -= 1
    if outcomes[ProjectionLeadOutcome.PROJECTED] == 0:
        del outcomes[ProjectionLeadOutcome.PROJECTED]


def _abandon_unattempted(summary: PipelineSummary, remaining: Sequence[RankedPosting]) -> None:
    """Give every lead the aborted projection stage never reached a terminal accounting.

    `remaining` is the lead the run-scoped cause surfaced on, plus every lead behind it — none of
    them was projected, and before this they were counted nowhere. The funnel's projection stage
    still declares it entered at the ranker's shortlist, so `entered == advanced + drops` failed on
    exactly this path: a fourth case outside the three the design promises are exhaustive (flag
    absent, preflight refused, balanced run).

    `NOT_ATTEMPTED` is not a diagnosis. The typed cause is `summary.projection_availability` and
    `fatal` states it once for the whole run; this only says these leads never got a turn. The ids
    go onto `projection_failed_ids` for the same reason every other non-`PROJECTED` outcome's do —
    the counter and the id list are read as one set, and a reader comparing their sizes must not
    find them disagreeing. Nothing downstream is changed by that on this path: `_cohort_guard`, the
    all-failed fatal and `folders_reconcile` all run only while `summary.fatal is None`.
    """
    for posting in remaining:
        summary.projection_outcomes[ProjectionLeadOutcome.NOT_ATTEMPTED] += 1
        summary.projection_failed_ids.append(posting.posting_id)


def _abandon_unattempted_if_projected(
    summary: PipelineSummary,
    projection_ctx: ProjectionRunContext | None,
    remaining: Sequence[RankedPosting],
) -> None:
    """`_abandon_unattempted`, but only when there is a projection stage whose balance to close.

    The tailor loop's three run-scoped `break`s predate `--project` and fire on an authored run
    too, where `projection_outcomes` must stay EMPTY — a `not_attempted` count there would
    materialise a stage that never ran. `projection_ctx` is the same object the loop reads to decide
    whether to project at all, so the guard cannot drift from the condition it guards.
    """
    if projection_ctx is None:
        return
    _abandon_unattempted(summary, remaining)


def _projection_scope(exc: Exception) -> ProjectionAvailability | ProjectionLeadOutcome:
    """Route one projection failure raised INSIDE the per-lead loop by scope, then classify it.

    Scope first, deliberately. Both classifiers refuse the other's scope by raising
    (`projection/run.py`), which is what makes a routing mistake loud — so a loop that called
    `classify_lead_outcome` on everything would abort the run with the classifier's own
    `AssertionError` instead of recording a typed fatal. Three run-scoped causes really do surface
    here rather than at the preflight, because `select()` raises them while building ONE lead:
    `PINNED_SET_COMPILE_FAILED`, `PINNED_SET_EXCEEDS_BUDGET` and `COMPILE_INFRASTRUCTURE_FAILURE`.

    A member is read out of `ISSUE_SCOPE` only to decide WHICH classifier to ask; the answer always
    comes from the classifier, so the guard that fails on a row whose value type and classifier
    disagree still runs. Anything that is not a `ProjectionError` is run-scoped or unclassified by
    construction (`classify_lead_outcome` takes only this package's own refusals), so it goes to
    `classify_availability` — which raises rather than inventing a bucket for an unmapped type, and
    that raise is correct: it reaches the crash handler, which records `fatal` and re-raises.
    """
    if isinstance(exc, ProjectionError) and isinstance(
        ISSUE_SCOPE.get(exc.violation.issue), ProjectionLeadOutcome
    ):
        return classify_lead_outcome(exc)
    return classify_availability(exc)


def _projection_unavailable(availability: ProjectionAvailability, detail: str) -> str:
    """The one operator sentence for a run-scoped projection refusal.

    Both sites that can raise one — the preflight, and the run-scoped arm of the per-lead loop —
    resolve through the same closed catalog, so they owe the operator the same remedy. They wrote
    it separately before, and only the preflight's copy carried the remedy: a `bundle_unreadable`
    that surfaced from the loop instead told the operator what had happened and nothing about how
    to get out of it, for a cause identical to one the preflight explains. Which site a run-scoped
    member happens to surface from is an accident of timing, so it may not decide how much the
    operator is told.

    The member is the typed outcome and nothing classifies behaviour by reading this string;
    `detail` is the free-text context the site has and the other does not.
    """
    return (
        f"projection unavailable: {availability.value} ({detail}); "
        "run `boardwatch profile-bundle approve-projection` after fixing what that names, "
        "or drop --project to run from the authored résumé"
    )


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


class ZeroOutputReconciliationError(RuntimeError):
    """A run-scoped suppression twin exceeded the this-run candidate count — a counting bug in
    the ranker/liveness attribution, surfaced loudly rather than clamped (P3 item 5 / B5)."""


def _zero_output_guard(
    candidate_judged_this_run: int,
    handled_this_run: int = 0,
    applied_this_run: int = 0,
    duplicate_this_run: int = 0,
    dead_this_run: int = 0,
) -> str | None:
    """P3 item 5 (B5) — 0 leads is provably right IFF every candidate THIS run judged
    (`eligible`/`uncertain`) was either delivered or honestly SUPPRESSED (already built/skipped/
    seen, already applied, a provable duplicate, or gone). All four explainers are RUN-scoped
    (D-282): the corpus-scoped `hidden_*` buckets are an exhaustive partition and can explain any
    empty day, so a clause built from them can never fire. A rejection (hard-filter, non-SWE,
    over-seniority, below-cutoff) is NOT an explainer — a filter or cap that ate the whole
    shortlist is exactly the silent empty day this guard exists to catch (D-246).

    `candidate_judged_this_run` counts `eligible` AND `uncertain` (both CAN become leads;
    `ineligible` cannot), run_id-attributed (not a cross-run handled ledger): a steady-state day
    where every candidate posting is a cache hit from a PRIOR run has this at 0 and is honest.

    Each of the four twins is a run-scoped SUBSET of the candidates judged this run, and the
    four subsets are disjoint — a posting leaves the ranker at exactly one `continue`, and
    `dead` is a post-rank fate of a posting that was surfaced, disjoint from the three
    suppressions that `continue` before surfacing. `unexplained` is what is left after
    subtracting all four; a negative value is a counting bug and raises
    `ZeroOutputReconciliationError` rather than being silently clamped to 0.
    """
    unexplained = (
        candidate_judged_this_run
        - handled_this_run
        - applied_this_run
        - duplicate_this_run
        - dead_this_run
    )
    if unexplained < 0:
        raise ZeroOutputReconciliationError(
            f"run-scoped suppression twins ({handled_this_run}+{applied_this_run}+"
            f"{duplicate_this_run}+{dead_this_run}) exceed candidates judged this run "
            f"({candidate_judged_this_run})"
        )
    if unexplained > 0:
        return (
            f"empty day not provably right: {unexplained} of {candidate_judged_this_run} "
            "candidate postings judged this run were neither delivered nor honestly suppressed"
        )
    return None


def _record_shortlist_dispositions(
    engine: Engine,
    settings: Settings,
    summary: PipelineSummary,
    run_id: int,
    *,
    surfaced_job_ids: Sequence[int],
    stage_completed: bool,
) -> None:
    """Record every disposition this run earned, AFTER the tailor loop has run.

    Three tiers, all keyed on the posting's CANONICAL job — which `_regroup` has already settled
    this run, so a disposition covers the whole duplicate group rather than one member of it:

    - `built` for every tailored lead;
    - `skipped` for a refusal that is genuinely deterministic (see
      `LeadArtifactError.is_deterministic`);
    - `seen` for the rest of the shortlist, so tomorrow's run advances past what this one worked
      through.

    `stage_completed` gates the `seen` tier only. A stage that ended in a fatal never presented
    these jobs as anything, so suppressing them would hide leads on the strength of a crash; the
    permanent tiers stand either way, because each names work that actually happened.

    Monotonic throughout: `seen` cannot lower a job already `built`, and `record_disposition`
    writes nothing rather than downgrading.
    """
    posting_ids = [lead.posting_id for lead in summary.tailored] + summary.unshippable_ids
    if not posting_ids and not (stage_completed and surfaced_job_ids):
        return
    built_ids = {lead.posting_id for lead in summary.tailored}
    now = utcnow()
    with engine.begin() as conn:
        stamp = run_policy_version(conn, settings)
        anchors = job_anchors(conn, posting_ids)
        decided_jobs: set[int] = set()
        for posting_id in posting_ids:
            job_id = anchors.get(posting_id)
            if job_id is None:
                continue  # no anchor to key on; `postings.job_id` is NOT NULL by trigger
            is_built = posting_id in built_ids
            decided_jobs.add(job_id)
            record_disposition(
                conn,
                job_id,
                disposition="built" if is_built else "skipped",
                reason="lead_built" if is_built else "unshippable_artifact",
                policy_version=stamp,
                now=now,
                run_id=run_id,
            )
        if not stage_completed:
            return
        expires_at = now + timedelta(days=settings.seen_ttl_days)
        for job_id in surfaced_job_ids:
            if job_id in decided_jobs:
                continue  # already carries this run's permanent decision
            record_disposition(
                conn,
                job_id,
                disposition="seen",
                reason="surfaced",
                expires_at=expires_at,
                now=now,
                run_id=run_id,
            )


def _regroup(engine: Engine, suppressions: Sequence[Suppression]) -> tuple[int, list[str]]:
    """Move each suppressed posting onto its survivor's job. Returns (moved, messages).

    Refusals are returned as non-fatal messages, not swallowed: a group left ungrouped because a
    member's job carries an application is a correct outcome, but an invisible one is a leak.
    """
    if not suppressions:
        return 0, []
    member_ids = sorted(
        {s.posting_id for s in suppressions} | {s.survivor_posting_id for s in suppressions}
    )
    messages: list[str] = []
    with engine.begin() as conn:
        plan = plan_regrouping(
            suppressions,
            job_anchors(conn, member_ids),
            protected_job_ids=protected_job_ids(conn),
        )
        moved = apply_merges(conn, plan.merges, identity_kind="exact_quad", now=utcnow())
    for refusal in plan.refusals:
        messages.append(
            f"regroup: group of posting {refusal.survivor_posting_id} left ungrouped "
            f"({refusal.reason}): {', '.join(str(p) for p in refusal.member_posting_ids)}"
        )
    return moved, messages


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
    project: bool = False,
    liveness_prober: LivenessProber | None = None,
) -> PipelineSummary:
    """Run scan → eligibility → tailor under one run row and return what each stage did.

    Raises ScanLockHeldError if another scan holds the lock. Nothing is written in that case,
    because the row is created by the scan stage inside the lock it failed to acquire.

    `liveness_prober=None` skips the liveness check (P6 item 6) and reports it as UNMEASURED,
    not as zero dead. Passed in rather than built here so that *which URLs get probed* is the
    caller's decision — `run_cmd` always supplies one. This does **not** make the pipeline
    offline: the scan stage fetches every configured board and is by far its largest network
    consumer, so `liveness_prober=None` is not an offline mode. `skip_scan=True` plus no prober
    is.

    `project=True` renders each lead from the career-profile bundle's projection instead of the
    authored résumé, and REFUSES the whole run — before any lead earns a ledger disposition — when
    the projection cannot be resolved. Never a fallback to the authored résumé: a fallback
    *succeeds*, so every lead would enter `summary.tailored`, every one of those would earn a
    permanent `built` disposition, and re-approving projection could never recover them.

    A projection that fails for ONE lead counts its outcome in `summary.projection_outcomes`,
    records a non-fatal error and skips that lead: the run continues and the lead stays reachable
    tomorrow. A RUN-scoped cause that surfaces inside the loop — `select()` raises three of them
    while building a single lead — stops the stage with `fatal` instead, because every remaining
    lead would fail on it identically.
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

    # Started BEFORE the scan, so the scan is the first mark rather than untimed work the
    # run's own artifact cannot see.
    clock = _StageClock()
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
    clock.mark("scan")

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
            summary.scan_new = scan_summary.new
            summary.scan_closed = scan_summary.closed
            # CLAUDE.md's fail-safe table: "systemic outage => fatal (prevents the silent
            # empty day)". `is_systemic_scan_outage` (D-037) is the same predicate
            # `coordinator.py`'s standalone scan uses, so the two can never disagree on the
            # same event. Note this reads the outcome, not a status field. The SENTENCE is
            # shared for the same reason the predicate is: both callers persist it, and the
            # row a reader reaches for should not depend on which command wrote it.
            attempted = scan_summary.companies
            if is_systemic_scan_outage(
                attempted=attempted,
                complete=scan_summary.complete,
                unchanged=scan_summary.unchanged,
            ):
                summary.fatal = systemic_scan_outage_reason(attempted)
            # NOT added to stage_errors: the scan stage already persisted these into
            # errors_json itself, and finish_run appends. Passing them again would record
            # every scan error twice and make any per-run error count uninterpretable.
            summary.errors.extend(scan_summary.errors)

        if summary.fatal is not None:
            stage_errors.append(f"scan: {summary.fatal}")
            summary.errors.append(f"scan: {summary.fatal}")
            return summary

        # P5a — the `--project` preflight. HERE, after the scan outcome and BEFORE the ranker call
        # below, and the position is the guarantee rather than a preference: the ranker is invoked
        # with `record_surfaced=False` and every shortlist disposition is deferred to
        # `_record_shortlist_dispositions` after the tailor loop, so nothing between this point and
        # that call has written one. `_zero_output_guard` and `_cohort_guard` cannot stand in for
        # this — both run AFTER that write, and both need a ranked cohort this run will not have.
        #
        # Fail-closed, never a fallback to the authored résumé. A fallback *succeeds*, so every
        # lead enters `summary.tailored`, `built_ids` is derived from exactly that set, and each
        # lead earns a PERMANENT `built` the ledger suppresses on every later run — re-approving
        # projection could not recover them. Refusing first is what makes re-approval a real drain.
        #
        # The honest limit: *no LEAD DISPOSITION* is achievable; *nothing recorded at all* is not.
        # The `runs` row already exists (`scan/coordinator.py` creates it inside the scan lock) and
        # a scan that ran has already written posting versions and events. The claim is scoped to
        # lead dispositions, which is exactly what the drain needs.
        #
        # `return`, never a bare one: only `fatal` decides the persisted status
        # (`finish_run(..., status=RUN_FAILED if summary.fatal is not None ...)` below) and only
        # `fatal` makes `run_cmd.py` exit 1. A return that left it None would write `status=ok` and
        # exit 0 having produced nothing — the run reporting success while producing nothing that
        # P3's gate forbids.
        projection_ctx: ProjectionRunContext | None = None
        if project:
            # One clock reading for the whole run, from the same clock the `runs` row uses. Not
            # cosmetic: `as_of` feeds effective-fact resolution, so it decides WHICH facts render.
            # Re-read per lead, a run crossing midnight UTC would render two leads from two
            # different fact sets and no digest over either résumé could detect it.
            as_of = utcnow().date()
            try:
                projection_ctx = resolve_projection_run(
                    engine,
                    settings,
                    bundle_root=resolve_bundle_root(settings.config_dir, None),
                    declaration_path=settings.config_dir / "projection.yaml",
                    scorer_id=DEFAULT_SCORER_ID,
                    as_of=as_of,
                )
                summary.projection_availability = ProjectionAvailability.AVAILABLE
            except Exception as exc:
                # Classified, never swallowed. A bare `except Exception` is safe ONLY because
                # `classify_availability` raises on an unmapped type: an unrecognised failure
                # surfaces loudly instead of becoming a silent wrong bucket. Letting that raise
                # propagate is correct — the crash handler below sets `summary.fatal` before
                # re-raising, so the run still records `failed`.
                #
                # The member is the typed outcome; the string below is the operator's sentence
                # about it and nothing classifies behaviour by reading it.
                availability = classify_availability(exc)
                summary.projection_availability = availability
                summary.fatal = _projection_unavailable(availability, str(exc))
                message = f"projection: {summary.fatal}"
                stage_errors.append(message)
                summary.errors.append(message)
                return summary
        clock.mark("projection")

        # The lane stage (JD-acquisition spec §4) — additive breadth, run before the ranker so
        # that a posting a lane discovers is judged by THIS run rather than by tomorrow's. It
        # reaches employers no ATS provider can and lands their postings through the SAME
        # `apply_board` every provider uses, so every persistence invariant is inherited rather
        # than restated.
        #
        # Placed after the `--project` preflight rather than immediately after the scan, and
        # deliberately: a refused projection returns before the ranker, while a lane's cost is
        # minutes of politeness-paced network, so paying it on a run that is about to refuse
        # buys nothing. The preflight's own guarantee is untouched — it is that no LEAD
        # DISPOSITION is written before it, and this stage writes companies and postings, the
        # two tables the scan stage already wrote before the preflight ran.
        #
        # No `fatal` arm. `_run_lanes` catches per lane and returns what went wrong, because a
        # lane is additive: the corpus without it is exactly the corpus this pipeline has always
        # ranked, so a dead aggregator costs the run its extra reach and nothing else.
        if settings.lanes_enabled:
            console.print("[bold]lanes[/bold]")
        lane_reports, lane_errors = _run_lanes(engine, settings, run_id)
        summary.lanes.extend(lane_reports)
        stage_errors.extend(lane_errors)
        summary.errors.extend(lane_errors)
        clock.mark("lanes")

        # D-325 — the measured-death sweep, HERE: after the lanes have re-sighted whatever they
        # could find (a positive sighting clears a strike in `_apply_listed`) and before the
        # ranker, so a posting proved dead this run leaves the pool this run rather than next.
        #
        # The population is `companies.watched = 0` — the rows for which no board scan can ever
        # produce an absence signal (D-314) — and the only evidence that closes one is the stored
        # URL itself answering a non-redirect 404/410, twice, in different runs.
        #
        # Reuses the SHORTLIST prober: `liveness_prober is None` means the operator asked for no
        # network liveness at all, and sweeping anyway would ignore that. It also means a run
        # that skips the check reports the sweep as UNMEASURED rather than as zero closed.
        #
        # No `fatal` arm, and caught rather than propagated: this is additive in the same sense a
        # lane is. The corpus without it is exactly the corpus this pipeline has always ranked,
        # so a sweep that dies costs the run its extra reach and nothing else. The report stays
        # `None` on failure — honest as "unmeasured", and deliberately understating any probes
        # that did land before the fault, because each posting commits in its own transaction.
        if liveness_prober is not None and settings.death_probe_budget > 0:
            try:
                summary.death_probe = sweep_unwatched_deaths(
                    engine,
                    prober=liveness_prober,
                    run_id=run_id,
                    budget=settings.death_probe_budget,
                    ttl_hours=settings.death_probe_ttl_hours,
                )
            except Exception as exc:  # noqa: BLE001 - never mask the run's own outcome
                message = f"death probe: sweep failed ({type(exc).__name__}: {exc})"
                stage_errors.append(message)
                summary.errors.append(message)
            else:
                probe = summary.death_probe
                console.print(
                    f"death probe: {probe.attempted} of {probe.due} due probed, "
                    f"{probe.gone} gone, {probe.unknown} unknown, {probe.closed} closed "
                    f"({probe.budget_refused} refused by budget)"
                )
        clock.mark("death_probe")

        console.print("[bold]eligibility[/bold]")
        try:
            ranked = rank_open_postings(
                engine,
                settings,
                limit=top_n,
                output_console=console,
                run_id=run_id,
                # The pipeline records its own dispositions AFTER the tailor loop
                # (`_record_shortlist_dispositions`). Letting the ranker write `seen` here put the
                # suppression on the wrong side of the render: a missing `tectonic`, an invalid
                # persona or a Ctrl-C between ranking and tailoring left the whole shortlist
                # suppressed for the TTL with nothing built, and the retry re-ranked into an empty
                # shortlist. Deciding after the loop is what makes the comment below true.
                record_surfaced=False,
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
            hidden_zero_signal=ranked.hidden_zero_signal,
            signal_unmeasured=ranked.signal_unmeasured,
            hidden_ineligible=ranked.hidden_ineligible,
            hidden_below_cutoff=ranked.hidden_below_cutoff,
            skipped_not_new=ranked.skipped_not_new,
            hidden_duplicate=ranked.hidden_duplicate,
            hidden_slate_cap=ranked.hidden_slate_cap,
            hidden_handled=ranked.hidden_handled,
            hidden_applied=ranked.hidden_applied,
            hidden_over_seniority=ranked.hidden_over_seniority,
            uncertain_band=ranked.uncertain_band,
            band_tokens_seen_while_inert=ranked.band_tokens_seen_while_inert,
            judged_this_run=len(ranked.judged_this_run_ids),
            handled_this_run=ranked.hidden_handled_this_run,
            applied_this_run=ranked.hidden_applied_this_run,
            duplicate_this_run=ranked.hidden_duplicate_this_run,
            # `dead_this_run` is not knowable yet — liveness runs after this point — and is
            # filled in below once it is, via `dataclasses.replace` (ShortlistCounts is frozen).
        )

        # P6 slice 2 §3.4: project this run's duplicate groups onto canonical jobs, so a lead
        # built below lands on the job that covers its duplicates from the next run onward.
        # Reuses the suppressions the ranker already resolved rather than re-deduplicating the
        # corpus — the coverage that costs is two duplicates that are BOTH ineligible, which are
        # never surfaced, so grouping them changes nothing.
        summary.regrouped, regroup_errors = _regroup(engine, ranked.suppressions)
        stage_errors.extend(regroup_errors)
        summary.errors.extend(regroup_errors)
        clock.mark("eligibility")

        # P6 item 6 — liveness, immediately before the render and after everything that decides
        # WHICH postings are leads. Here because the gate clause is "0 dead postings reaching the
        # lead list", and this is the last point at which a posting is still only a candidate.
        #
        # Nothing is written. A `dead` result withholds the lead from THIS run and from the
        # ledger write below; it does not close the posting, because `postings.status` belongs to
        # the scanner's board-absence rule and one 404 must not be able to retire a live
        # requisition permanently. Tomorrow's run asks again.
        leads = list(ranked.visible)
        dead_job_ids: set[int] = set()
        if liveness_prober is not None:
            results = check_leads(
                engine, [p.posting_id for p in leads], prober=liveness_prober
            )
            summary.liveness_checked = len(results)
            summary.liveness_dead = sum(1 for r in results.values() if r.withholds)
            summary.liveness_unknown = sum(
                1 for r in results.values() if r.verdict == "unknown"
            )
            summary.liveness_gone_after_redirect = sum(
                1 for r in results.values() if r.gone_but_redirected
            )
            dead_ids = {pid for pid, r in results.items() if r.withholds}
            if dead_ids:
                summary.dead_lead_ids.extend(sorted(dead_ids))
                for posting_id in sorted(dead_ids):
                    detail = results[posting_id].detail
                    summary.errors.append(
                        f"liveness: posting {posting_id} withheld as gone ({detail})"
                    )
                leads = [p for p in leads if p.posting_id not in dead_ids]
                # The `seen` write below must not name a job whose lead was withheld: nothing was
                # presented to anybody, so suppressing it for the TTL would hide a posting that
                # may simply have been behind a broken CDN. Same reasoning as the stage gate.
                with engine.connect() as anchor_conn:
                    dead_job_ids = set(job_anchors(anchor_conn, sorted(dead_ids)).values())
            redirected_note = (
                f", {summary.liveness_gone_after_redirect} of them gone-after-redirect"
                if summary.liveness_gone_after_redirect
                else ""
            )
            console.print(
                f"liveness: {summary.liveness_checked} checked, {summary.liveness_dead} gone, "
                f"{summary.liveness_unknown} unknown (unknown is served){redirected_note}"
            )

        clock.mark("liveness")

        # Names the résumé source in the log, so a projected run is distinguishable from an
        # authored one after the fact. Byte-identical to the plain header when `--project` was not
        # passed; `projection_ctx` itself stays in scope for the loop below.
        console.print(f"[bold]tailor[/bold]{' (projected)' if projection_ctx is not None else ''}")
        # Enumerated so a run-scoped projection failure can name the leads it aborted on — this one
        # and every one behind it — rather than leaving them counted nowhere while the funnel stage
        # still claims it entered at the full shortlist. See `_abandon_unattempted`.
        for lead_index, posting in enumerate(leads):
            dest = day_dir / _slug(posting.company, posting.posting_id)
            # The authored résumé and no lineage, unless this lead is projected below. Never a
            # FALLBACK: a projection that fails does not reach `run_tailor` at all (it `continue`s),
            # because a fallback SUCCEEDS and every lead it produced would earn a permanent `built`
            # for an artifact nobody asked for — the defect the whole design exists to avoid.
            lead_resume_path = resume_path
            lead_lineage: ResumeSourceLineage | None = None
            if projection_ctx is not None:
                try:
                    # `dest` is NOT pre-created. `_publish` stages both sidecars in a sibling
                    # directory and renames them in only once every byte exists, so a lead that
                    # refuses leaves no directory at all — which `_remove_if_empty` (an `rmdir`)
                    # could not undo once one sidecar was inside it.
                    projected = project_for_posting(
                        projection_ctx,
                        engine,
                        settings,
                        posting.posting_id,
                        out_dir=dest,
                        compile_runner=default_compile_runner(),
                    )
                except Exception as exc:
                    # Broad, then routed by SCOPE — see `_projection_scope`, which raises rather
                    # than bucketing anything the two closed catalogs do not name.
                    scope = _projection_scope(exc)
                    if isinstance(scope, ProjectionAvailability):
                        # Run-invariant: every remaining lead would fail identically, so the stage
                        # stops here exactly as it does for a missing render tool. Recorded as the
                        # RUN's verdict and as `fatal`, never as a lead outcome — counting it
                        # per-lead would grant the leads after it a disposition under a run-wide
                        # fault, which is the one mistake a total table cannot prevent by itself.
                        summary.projection_availability = scope
                        summary.fatal = _projection_unavailable(
                            scope, f"posting {posting.posting_id}: {exc}"
                        )
                        message = f"projection: {summary.fatal}"
                        stage_errors.append(message)
                        summary.errors.append(message)
                        # This lead and every one behind it get a terminal accounting before the
                        # break. Without it the stage stops with the funnel still declaring it
                        # entered at the ranker's shortlist while `advanced` and the drops hold
                        # only the work that finished first — a stage that DOES NOT RECONCILE, and
                        # a fourth case outside the three §4.5 promises are exhaustive.
                        _abandon_unattempted(summary, leads[lead_index:])
                        break
                    # Per-lead: counted, reported as a NON-fatal error, and the run continues.
                    summary.projection_outcomes[scope] += 1
                    summary.projection_failed_ids.append(posting.posting_id)
                    # A lead outcome is only ever returned by `classify_lead_outcome`, which
                    # `_projection_scope` calls behind its own `isinstance` check — so `exc` here is
                    # always a `ProjectionError` and its violation can be read as data.
                    assert isinstance(exc, ProjectionError)
                    # The violation's own fields, not `str(exc)`: that already LEADS with the issue
                    # value, so prefixing it with the outcome printed
                    # `output_io_failure: output_io_failure: …` for every member whose outcome and
                    # issue happen to share a name. The outcome is the bucket this run counted, and
                    # the violation's message names the issue in prose, so nothing is lost.
                    message = (
                        f"projection: posting {posting.posting_id}: {scope.value}: "
                        f"{exc.violation.message} ({exc.violation.where})"
                    )
                    stage_errors.append(message)
                    summary.errors.append(message)
                    continue
                summary.projection_outcomes[ProjectionLeadOutcome.PROJECTED] += 1
                lead_resume_path = projected.resume_path
                lead_lineage = projected.lineage
            try:
                result = run_tailor(
                    engine,
                    settings,
                    posting.posting_id,
                    resume_path=lead_resume_path,
                    out_dir=_ensure_dir(dest),
                    run_id=run_id,
                    # None on the authored path, so that path is byte-identical to before. On the
                    # projected one this is what arms `_master_from_lineage`: without it the
                    # hash/version validation and the artifact's `projection_*` provenance are
                    # unreachable code.
                    source_lineage=lead_lineage,
                )
            except (RenderToolMissingError, TemplateArtifactError) as exc:
                # An environment/authoring fault, not a per-lead failure (P1a): either the
                # compiler binary is missing from PATH or the template itself is broken, so
                # every remaining lead would fail identically — abort the stage rather than
                # burn through the whole shortlist re-discovering that.
                summary.fatal = f"render tool unavailable: {exc}"
                message = f"tailor: {summary.fatal}"
                stage_errors.append(message)
                summary.errors.append(message)
                # THIS lead is not in the remainder: on a projected run it was already counted
                # `PROJECTED` — projection finished for it and the TAILOR stage is where it drops.
                # The leads behind it never reached projection at all. Same reasoning at the two
                # `break`s below; the tailor stage's own behaviour on a fatal abort is unchanged
                # from the authored path and is not this stage's balance to close.
                _abandon_unattempted_if_projected(summary, projection_ctx, leads[lead_index + 1:])
                break
            except ResumeLoadError as exc:
                # A malformed or genuinely-broken master résumé (P4 item 5b: a bad contact
                # block, a leftover template artifact) is an authoring fault, not a per-lead
                # one — `load_resume()` re-validates it on every call, so every remaining lead
                # would fail identically. Abort the stage rather than rediscovering that lead
                # by lead, exactly like `RenderToolMissingError` above.
                summary.fatal = f"master résumé invalid: {exc}"
                message = f"tailor: {summary.fatal}"
                stage_errors.append(message)
                summary.errors.append(message)
                _abandon_unattempted_if_projected(summary, projection_ctx, leads[lead_index + 1:])
                break
            except PersonaError as exc:
                # A malformed persona registry (bundled or {config_dir} override) is a
                # configuration fault, not a per-lead one — `load_personas()` re-validates it on
                # every call, so every remaining lead would fail identically. Fail the run
                # loudly rather than silently degrading each lead, exactly like the two above.
                summary.fatal = f"persona registry invalid: {exc}"
                message = f"tailor: {summary.fatal}"
                stage_errors.append(message)
                summary.errors.append(message)
                _abandon_unattempted_if_projected(summary, projection_ctx, leads[lead_index + 1:])
                break
            except LeadArtifactError as exc:
                # Leave no empty folder behind: counting the deliverable by listing the dated
                # directory is the obvious independent check, and a husk would inflate it.
                _remove_if_empty(dest)
                summary.tailor_failed += 1
                summary.tailor_failed_ids.append(posting.posting_id)
                # A permanent `skipped` only for a refusal the RÉSUMÉ earned. `is_deterministic`
                # asks the exception, which carries both gate reasons as data (CLAUDE.md forbids
                # recovering that by string-matching the message): too many pages repeats
                # identically and is worth not re-rendering, whereas a non-zero `tectonic` exit is
                # environmental and burying the lead for it would delete a real opportunity that
                # tomorrow's run would have built. The generic `except` below records nothing for
                # the same reason.
                if exc.is_deterministic:
                    summary.unshippable_ids.append(posting.posting_id)
                message = f"tailor: posting {posting.posting_id}: {exc}"
                stage_errors.append(message)
                summary.errors.append(message)
                continue
            except ResumeLineageMismatch as exc:
                # An EXPLICIT arm, above the broad one, and it has to be: `run_tailor` raises this
                # when the file it was handed is not the document its lineage describes (swapped
                # bytes, a re-parsed model, or a posting version that moved between projection and
                # tailoring). Caught by the `except Exception` below it would be filed as an
                # ordinary `tailor_failed` and `ProjectionLeadOutcome.LINEAGE_MISMATCH` could never
                # be produced — a typed refusal silently degraded into a generic bucket, which
                # ships looking green.
                #
                # Not a fatal: the mismatch is about ONE posting's projected document, and the next
                # lead's own projection and validation are independent of it.
                _retract_projected(summary.projection_outcomes)
                summary.projection_outcomes[ProjectionLeadOutcome.LINEAGE_MISMATCH] += 1
                summary.projection_failed_ids.append(posting.posting_id)
                message = (
                    f"projection: posting {posting.posting_id}: "
                    f"{ProjectionLeadOutcome.LINEAGE_MISMATCH.value}: {exc}"
                )
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
                    coverage=result.coverage,
                    degraded=result.degraded,
                )
            )
            if result.degraded:
                # A shippable-but-UNTAILORED PDF is not a failed lead (pdf_built stays True), so
                # nothing above records it. Left unsurfaced, a systematic cause — every tailored
                # output running one page over the limit, a template regression — ships generic
                # résumés on every lead while the run stays green. Recorded like a tailor
                # failure: onto the `runs` row via stage_errors, onto the funnel and CLI via
                # summary.errors. Not fatal — the untailored master is a real, correct résumé.
                message = (
                    f"tailor: posting {posting.posting_id}: shipped untailored master "
                    f"(tailored gate: {result.degrade_reason})"
                )
                stage_errors.append(message)
                summary.errors.append(message)

        # P6 slice 2 §5.3 — the whole ledger write, AFTER the loop, so every disposition names
        # work that actually happened: `built` only for a lead whose artifact already exists, and
        # `seen` only when the stage got far enough to have presented the shortlist at all. A
        # crash between ranking and here leaves the job undisposed, which over-shows it next run.
        # That is the safe direction; the opposite would suppress a job with no deliverable.
        _record_shortlist_dispositions(
            engine,
            settings,
            summary,
            run_id,
            # A job whose posting was withheld as gone is dropped from the `seen` tier for the
            # same reason a fatal drops the whole tier: it was never presented to anybody.
            surfaced_job_ids=tuple(
                job_id for job_id in ranked.surfaced_job_ids if job_id not in dead_job_ids
            ),
            stage_completed=summary.fatal is None,
        )

        # Every lead the ranker produced failed to render. Not "zero was provably right" —
        # zero was produced from a non-empty shortlist, which is a broken résumé path
        # (missing resume.yaml, tectonic gone), not an honest empty day. Postings withheld as
        # gone are subtracted first: they never entered the tailor loop, so counting them as
        # render failures would report a dead board as a broken résumé path.
        shortlisted = summary.shortlist.shortlisted if summary.shortlist else 0
        renderable = shortlisted - len(summary.dead_lead_ids)
        # A projected lead that never reached `run_tailor` is counted here and NOT subtracted from
        # `renderable`, deliberately: it was renderable, and a run that produced nothing from a
        # non-empty shortlist must stay fatal. Subtracting them would leave the zero-output guard
        # below as the only backstop, and that guard is widened by `hidden_handled`/`hidden_applied`
        # — so on any steady-state day a projection that failed on every lead would have written
        # `status=ok` with nothing delivered.
        unrendered = summary.tailor_failed + len(summary.projection_failed_ids)
        if summary.fatal is None and renderable > 0 and not summary.tailored:
            # "project or tailor", because `unrendered` sums BOTH: a projected lead that never
            # reached `run_tailor` is in the numerator, so naming only tailoring would point an
            # operator at the résumé path for a failure that happened before it.
            summary.fatal = f"every lead failed to project or tailor ({unrendered}/{renderable})"

        # P3 item 5 (B5) — zero-output guard. Reachable when `renderable == 0`, which is either a
        # candidate-less day (`shortlisted == 0`) or — since P6 item 6 — a day where a non-empty
        # shortlist was entirely WITHHELD as dead. The second is why the fatal above subtracts
        # `dead_lead_ids` and why this guard takes them: `shortlisted > 0` no longer implies the
        # fatal already fired. Checked BEFORE cohort completeness (design's stated order) so the
        # more specific empty-day message wins when both would otherwise fire on the same run.
        judged = ranked.judged_this_run_ids
        dead_this_run = len(set(summary.dead_lead_ids) & judged)
        if summary.shortlist is not None:
            # Filled in here, not at the initial population above: liveness (which produces
            # `dead_lead_ids`) runs after that point. `ShortlistCounts` is frozen.
            summary.shortlist = replace(summary.shortlist, dead_this_run=dead_this_run)
        if summary.fatal is None and not summary.tailored:
            summary.fatal = _zero_output_guard(
                len(judged),
                handled_this_run=ranked.hidden_handled_this_run,
                applied_this_run=ranked.hidden_applied_this_run,
                duplicate_this_run=ranked.hidden_duplicate_this_run,
                dead_this_run=dead_this_run,
            )

        # P3 item 9 — cohort completeness. Every SHORTLISTED candidate (`ranked.visible`, which
        # EXCLUDES `skipped_not_new` — top_cmd.py:63) must have reached a terminal state: a lead
        # (`summary.tailored`) or a tailor failure (`summary.tailor_failed_ids`). Reconciled by
        # posting_id SET, not by count, so a compensating bug cannot balance.
        if summary.fatal is None:
            # Postings withheld as gone are removed from the cohort rather than added to the
            # accounted set: they are a THIRD terminal state, not a lead and not a render
            # failure, and folding them into either would make one of those counts a lie. A lead
            # whose PROJECTION refused is removed for exactly that reason — a fourth terminal
            # state, and the tailor stage never ran for it.
            visible_ids = (
                frozenset(posting.posting_id for posting in ranked.visible)
                - frozenset(summary.dead_lead_ids)
                - frozenset(summary.projection_failed_ids)
            )
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
        clock.mark("tailor")
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
        # `status=failed` with `errors_json=[]` is a run that cannot say why it failed, and it
        # is the shape an unattended failure actually took: the reason lived only in the
        # console log. Four fatal paths reach here without ever touching `stage_errors` — the
        # all-leads-unrendered fatal, `_zero_output_guard`, `_cohort_guard` and the
        # filesystem-truth guard all set `summary.fatal` and fall through — so this is the
        # choke point that guarantees the reason is persisted.
        #
        # HERE rather than at each of those four sites, and that is the whole point: the
        # failure mode is not those four, it is the FIFTH fatal path somebody adds later and
        # forgets to record. A guarantee that lives in one place a fatal cannot bypass is
        # retroactively correct for a path that has not been written yet; four more `append`
        # calls would only be correct for the four that exist today.
        #
        # The sites that DO record prefix the reason with their stage (`scan: `, `projection: `,
        # `tailor: `) and the crash handler records it verbatim, so on every current path the
        # reason is a SUFFIX of what was already appended. `endswith` is the dedup test rather
        # than substring containment: it is exact for all of them, and where a future site
        # wraps the reason differently it errs toward recording it TWICE rather than not at
        # all — the safe direction for a guard whose only job is that the reason is never
        # missing. `summary.errors` is left alone: the funnel already renders `summary.fatal`
        # as its own FATAL line, so the artifact could always answer this and only the row
        # could not.
        if summary.fatal is not None and not any(
            recorded.endswith(summary.fatal) for recorded in stage_errors
        ):
            stage_errors.append(f"fatal: {summary.fatal}")
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
        # Loaded ONCE, before either artifact, and handed to both (D-274). `held` is a live
        # count of open postings with no run dimension, so loading it per artifact would let
        # the funnel and the morning file disagree about one run's coverage whenever a
        # posting closed in between. Its own failure costs the SECTION, not the artifact:
        # this returns None and the renderers say so, where an escaping exception would take
        # the whole funnel down with it through the except below.
        summary.board_coverage = _load_board_coverage(engine, run_id, console)
        # LAST mark, and inside the `finally` so it fires on the crash and early-return paths
        # too — those are exactly the runs whose cost breakdown is worth having. On a clean run
        # it covers `finish_run` and the coverage load above and nothing else: the late guards
        # sit BEFORE `clock.mark("tailor")` and are charged there. On an aborting run it also
        # absorbs everything since the last mark that completed, which is the point of marking
        # boundaries rather than wrapping stages.
        #
        # `finalize`, not `reports`: the three artifact writes below run AFTER this mark, and
        # they must — the funnel is one of them and cannot contain its own duration. The
        # markdown states that exclusion rather than letting the shares imply otherwise.
        clock.mark("finalize")
        summary.stage_durations = list(clock.durations)
        # Where the ESCALATABLE alerts begin, and why a mark is needed at all: `summary.errors`
        # is not "the run's alerts". It accumulates every stage error the pipeline produced — a
        # single 404 on one board slug, a lane that could not collect, a per-lead projection or
        # tailor degradation — and those are routine on a 379-board fleet. Measured over the last
        # 25 runs, NINE carried a non-empty `summary.errors` and not one of the nine was a
        # finalize-block alert: runs 124-128 each carried `plaid: HTTP 404` for one dead slug.
        # Escalating that list would drive an external monitor DOWN on five consecutive ordinary
        # `status=ok` runs, and an owner who learns a DOWN check means nothing has lost the only
        # property this channel has. Everything appended from here on is a deliberate ALERT: the
        # artifact-write failures, the six soft detectors, and the heartbeat's own result.
        escalatable_from = len(summary.errors)
        try:
            summary.funnel = _emit_funnel(engine, settings, summary, scan_summary, day_dir)
        except Exception as exc:  # noqa: BLE001 - never mask the run's own outcome
            # Recorded, not just printed (D-287, open question 1). Still fail-open — a
            # reporting failure must never discard a run that produced real leads — but
            # `finish_run` has already committed above, so until this write a funnel-less run
            # was byte-identical to a clean one in the store. That is the wrong thing to be
            # invisible: Gate P3 counts clean unattended runs while B1 and B5 are read out of
            # the funnel. `append_run_error` only appends; it cannot touch status or
            # finished_at, because a reporting failure is not a run outcome.
            note = f"funnel artifact not written: {exc}"
            console.print(f"  ! {note}", markup=False)
            summary.errors.append(note)
            append_run_error(engine, run_id, note)
        # The delivery queue (design §4.3), guarded exactly as the two artifact writes are. It
        # sits BETWEEN them so a failure here reaches the morning digest below, which is the
        # file the owner actually reads. The queue holds COPIES of what the run already
        # delivered — the résumé and the funnel above are the run's real output — so a queue
        # failure must cost the queue and nothing else, and it must not sit upstream of an
        # artifact a gate reads. Recorded on `summary.errors` as well as printed, because
        # `run_cmd` prints that list after the call returns and a silently unwritten queue is a
        # queue the owner will trust anyway.
        try:
            lead_failures, folder_failures = _sync_queue(engine, settings, console)
            queue_failures = _interleave(lead_failures, folder_failures)
            # Per-lead failures used to stop at the log line above, which is defensible while
            # somebody is watching the run and is not defensible unattended: `run_cmd` prints that
            # line into a file nobody opens, so a queue that had quietly stopped copying leads was
            # byte-identical in the store to one that copied every one of them — and the owner
            # would go on trusting a queue that had gone empty. Escalated to the same two places
            # every other reporting failure in this block reaches, and durable through
            # `append_run_error` because `finish_run` has already committed. Still NOT fatal, for
            # the reason the block comment above gives: the queue holds COPIES, and the dated tree
            # and the funnel are the run's real output.
            if queue_failures:
                # Capped rather than joined whole: a systemic queue fault fails every lead, and a
                # note carrying hundreds of details would be stored in `runs.errors_json` and
                # reprinted into the morning digest. Three name the shape; the count stays exact.
                # `_interleave` is what stops three lead failures hiding every folder failure —
                # the cap would otherwise fall entirely inside whichever kind came first.
                shown = "; ".join(queue_failures[:3])
                if len(queue_failures) > 3:
                    shown += f"; +{len(queue_failures) - 3} more"
                note = (
                    f"delivery queue: {len(queue_failures)} lead folder(s) failed to copy or "
                    f"drain — {shown}"
                )
                console.print(f"  ! {note}", markup=False)
                summary.errors.append(note)
                append_run_error(engine, run_id, note)
        except Exception as exc:  # noqa: BLE001 - never mask the run's own outcome
            note = f"delivery queue not synced: {exc}"
            console.print(f"  ! {note}", markup=False)
            summary.errors.append(note)
            # Durable, like the funnel and morning handlers: this runs after `finish_run`,
            # so `summary.errors` alone never reaches `runs.errors_json` (D-287).
            append_run_error(engine, run_id, note)
        # F4 intake-death detector. The heartbeat below fires on any clean outcome, so a
        # run that scans fine but finds NOTHING new — a dead fleet, a silent fetch
        # regression — pages nobody. This reads the per-run net-new count the scan already
        # persisted (`runs.new_count`) and raises a SOFT alert when a window of scanning
        # runs all read zero. It never sets `fatal`: the run succeeded, so the heartbeat
        # must still fire — a stalled intake tickets, it does not trip the dead-man's
        # switch. Recorded on `summary.errors` (reprinted by `run_cmd`) and, because
        # `finish_run` has already committed, made durable through `append_run_error`.
        try:
            intake_alert = check_intake_death(engine)
            if intake_alert is not None:
                console.print(f"  ! {intake_alert}", markup=False)
                summary.errors.append(intake_alert)
                append_run_error(engine, run_id, intake_alert)
        except Exception as exc:  # noqa: BLE001 - never mask the run's own outcome
            note = f"intake-death check not run: {exc}"
            console.print(f"  ! {note}", markup=False)
            summary.errors.append(note)
            append_run_error(engine, run_id, note)
        # Partial scan-outage soft alert. `is_systemic_scan_outage` only fatals when EVERY
        # board fails; a provider or IP block can dark most of the fleet while a few boards
        # complete, which is not systemic — the heartbeat stays green and F4 cannot see it
        # because the survivors still emit net-new. Soft and non-fatal, recorded in the run.
        # `scan_summary` is None on a lane-only or `--no-scan` run.
        if scan_summary is not None:
            outage = scan_outage_alert(scan_summary.companies, summary.scan_boards_failed)
            if outage is not None:
                console.print(f"  ! {outage}", markup=False)
                summary.errors.append(outage)
                append_run_error(engine, run_id, outage)
        # Delivery-drought soft alert. Intake can be healthy while the tailor, rank, or delivery
        # path silently ships nothing; the heartbeat stays green and intake-death cannot see it
        # (net-new > 0). Fires only when the last clean runs each judged a candidate yet
        # delivered zero — a quiet day and an eligibility collapse both abstain. Non-fatal.
        try:
            drought = check_delivery_drought(engine)
            if drought is not None:
                console.print(f"  ! {drought}", markup=False)
                summary.errors.append(drought)
                append_run_error(engine, run_id, drought)
        except Exception as exc:  # noqa: BLE001 - never mask the run's own outcome
            note = f"delivery-drought check not run: {exc}"
            console.print(f"  ! {note}", markup=False)
            summary.errors.append(note)
            append_run_error(engine, run_id, note)
        # Apply-lane drought soft alert, and it sits HERE, immediately below its sibling, because
        # the sibling is blind to exactly one fault: `check_delivery_drought` counts
        # `resume_tailored` artifacts, which are written whichever lane the lead routes to. So a
        # global break in location classification, the role gate or a requirement flag would send
        # every lead to `_review`, keep artifacts flowing at the normal rate, leave the drought
        # check abstaining and the heartbeat green — and ship zero apply-ready leads for a
        # fortnight. Fires only when the last clean runs each delivered PLACEABLE leads and none
        # reached the apply lane; a run that delivered nothing abstains and is the sibling's story.
        # Non-fatal: those leads are in `_review`, reviewable and not lost.
        #
        # Above `_emit_morning` like every soft alert here — below it the alert still fires, is
        # still recorded, and is invisible in the one artifact an unattended owner reads.
        try:
            lane_alert = check_apply_lane_drought(engine)
            if lane_alert is not None:
                console.print(f"  ! {lane_alert}", markup=False)
                summary.errors.append(lane_alert)
                append_run_error(engine, run_id, lane_alert)
        except Exception as exc:  # noqa: BLE001 - never mask the run's own outcome
            note = f"apply-lane-drought check not run: {exc}"
            console.print(f"  ! {note}", markup=False)
            summary.errors.append(note)
            append_run_error(engine, run_id, note)
        # Liveness-blindness soft alert. The liveness stage is fail-open by design — any
        # transport fault is `unknown`, and `unknown` is served — so a prober whose egress has
        # broken (DNS, a proxy, a blocked IP) returns `unknown` for the whole shortlist, drops
        # `dead` to zero, and ships every lead unverified while the run line still reads
        # normally. The conjunction is the signal: a high unknown share AND no gone-status at
        # all is a property of the prober, not of the postings. Non-fatal and deliberately not
        # gated on the heartbeat below — the leads this run produced are real and the run
        # succeeded, so a blind prober tickets rather than tripping the dead-man's switch.
        # Recorded on `summary.errors` (reprinted by `run_cmd`) and, because `finish_run` has
        # already committed above, made durable through `append_run_error`.
        try:
            blind_alert = check_liveness_blind(
                summary.liveness_checked, summary.liveness_unknown, summary.liveness_dead
            )
            if blind_alert is not None:
                console.print(f"  ! {blind_alert}", markup=False)
                summary.errors.append(blind_alert)
                append_run_error(engine, run_id, blind_alert)
        except Exception as exc:  # noqa: BLE001 - never mask the run's own outcome
            note = f"liveness-blindness check not run: {exc}"
            console.print(f"  ! {note}", markup=False)
            summary.errors.append(note)
            append_run_error(engine, run_id, note)
        # Corpus-regression detector (D-371) — the one collapse the checks above cannot
        # see. Intake death stays quiet because postings keep arriving; a delivery drought
        # abstains BY CONSTRUCTION, because its honest guard is "did this run judge a
        # candidate?" and a corpus that has gone entirely ineligible judged none. So a rules
        # edit or a profile fact that stops resolving leaves every existing signal green while
        # an unattended machine ships nothing for a fortnight. This compares the run's
        # candidate RATE — never a count, which an identity re-key legitimately drops by 96%
        # on a perfectly clean run — against the median of the last five comparable runs.
        # Same contract as the check above: soft, never `fatal`, appended to `summary.errors`
        # for `run_cmd` to reprint, and made durable through `append_run_error` — safe because
        # `finish_run` has already committed, and `append_run_error` cannot touch status or
        # finished_at.
        try:
            corpus_alert = check_corpus_regression(engine)
            if corpus_alert is not None:
                console.print(f"  ! {corpus_alert}", markup=False)
                summary.errors.append(corpus_alert)
                append_run_error(engine, run_id, corpus_alert)
        except Exception as exc:  # noqa: BLE001 - never mask the run's own outcome
            note = f"corpus-regression check not run: {exc}"
            console.print(f"  ! {note}", markup=False)
            summary.errors.append(note)
            append_run_error(engine, run_id, note)
        # LAST thing the finalize block writes, and deliberately so: the morning digest now
        # renders `summary.errors` (P3 item 7) and is the only artifact here the owner reads
        # unattended. Every handler above appends its note to that list BEFORE this runs, so a
        # funnel-write failure, a queue-sync failure and the intake-death alert all reach the
        # digest. Emitting it earlier renders the digest and THEN appends alerts nobody sees
        # until the next run — which is where the queue sync used to leave its note. Any future
        # soft alert belongs above this call for the same reason. It still comes after the
        # funnel for the original reason too: it links to `funnel-<run_id>.md` by NAME rather
        # than by the WrittenArtifact above, so it renders that link even when the funnel itself
        # failed to write (the name is deterministic from run_id either way).
        try:
            summary.morning = _emit_morning(engine, settings, summary, day_dir)
        except Exception as exc:  # noqa: BLE001 - never mask the run's own outcome
            # Recorded, not just printed — the same asymmetry the funnel handler above closes
            # (D-287). The morning artifact is the owner's daily digest (P3 item 7); a swallowed
            # write left only a console line that no unattended run is read from, so the note now
            # also reaches `summary.errors` (which `run_cmd` reprints) and the `runs` row via
            # `append_run_error`. Still fail-open: a digest write is not the run's outcome — and
            # the heartbeat gate below, not this handler, is what makes the failure carry.
            note = f"morning artifact not written: {exc}"
            console.print(f"  ! {note}", markup=False)
            summary.errors.append(note)
            append_run_error(engine, run_id, note)
        # Dead-man's-switch: ping the monitor ONLY on a clean outcome, so a failed or
        # crashed run (fatal set above, or set-before-raise on the crash path) stays silent
        # and the external monitor still alerts. Gated on `fatal`, not on reaching a return —
        # the late guards fall through here with `fatal` set. Swallowed like the emits above:
        # telemetry must never be the thing that fails the run (D-076). No-op unless the
        # operator set BOARDWATCH_HEARTBEAT_URL, so it is off by default for every other user.
        #
        # Also gated on the funnel having been written. A run whose funnel write failed stays
        # non-fatal (fail-open, D-287), but its authoritative record is missing — B1, B5 and the
        # Gate P3 clean-run count are all read out of that artifact — so a green ping would
        # assert a trustworthy run that never fully recorded itself. Withholding the ping makes
        # the monitor alert on that state instead. `summary.funnel` is None exactly when
        # `_emit_funnel` raised above.
        #
        # And gated on the morning digest, for a reason that did NOT hold before the digest
        # began rendering `summary.errors`. Until then it was a convenience view of facts the
        # funnel already held, and gating on it would have paged daily over a reporting bug. It
        # is now the only channel by which a soft alert reaches an absent owner: the console
        # goes to a log file nobody opens, `runs.errors_json` is queried by nothing, and the
        # funnel buries an alert a thousand lines deep in a file that is searched rather than
        # read. A run whose digest did not write therefore delivered its leads and delivered
        # none of its warnings, and looked identical to a run that had nothing to warn about —
        # which is the exact silent-degradation class the heartbeat gate exists to break.
        #
        # A persistent digest bug will now page every day, and that is the intended cost: over a
        # fortnight of unattended running it means a fortnight of blind operation, and one alert
        # a day is proportional to that. The switch is not being overloaded with a new claim,
        # either — the funnel clause above already moved its meaning from "a run happened" to
        # "a run happened and recorded itself", and this extends the same predicate to the one
        # record that is actually delivered. Withholding a ping never fails the run, never
        # changes `runs.status` and never discards a lead; the leads still ship.
        #
        # The ping's own outcome is recorded, not discarded. A ping the monitor REFUSES — a
        # rotated token, a deleted check, an endpoint answering 500 — is indistinguishable from
        # a healthy run to everything downstream: the monitor sees no ping and cannot tell a
        # refused one from a machine that never woke up, and boardwatch's silence reads as
        # health. `send_heartbeat` returns `None` for both quiet outcomes (acknowledged, or no
        # URL configured — an unset URL must never raise an alert, it is the default), so a
        # string here means a ping was attempted and did not land. Handled like every soft alert
        # above: printed, onto `summary.errors` for `run_cmd` to reprint, and made durable
        # through `append_run_error` because `finish_run` has long since committed.
        #
        # This is the ONE alert that cannot reach the digest, and that is structural rather than
        # an oversight to tidy up later. The rule the digest imposes — a soft alert belongs
        # ABOVE `_emit_morning` — cannot hold for an alert raised by the gate whose job is to
        # observe whether `_emit_morning` succeeded; pinging earlier to buy the digest would
        # break the two clauses in this very condition. So this note reaches the console (the
        # launchd log on an unattended run) and `runs.errors_json`, and no artifact — nothing
        # reads a prior run's error list, so it will not surface in tomorrow's digest either.
        # That is a real loss and it is stated rather than papered over; it is also strictly
        # smaller than what it replaces, which was no trace of any kind.
        #
        # Still strictly fail-open (D-076): no `fatal`, no raise, no retry, no second ping. The
        # broad `except` also covers `append_run_error`, so a store that refuses the write costs
        # a console line and never the run.
        if summary.fatal is None and summary.funnel is not None and summary.morning is not None:
            try:
                heartbeat_alert = send_heartbeat()
                if heartbeat_alert is not None:
                    console.print(f"  ! {heartbeat_alert}", markup=False)
                    summary.errors.append(heartbeat_alert)
                    append_run_error(engine, run_id, heartbeat_alert)
            except Exception as exc:  # noqa: BLE001 - never mask the run's own outcome
                console.print(f"  ! heartbeat not sent: {exc}", markup=False)
        # Escalation, and it belongs HERE — below `_emit_morning` and below the heartbeat gate —
        # which is the one place in this block that is NOT a mistake. The rule the digest imposes
        # ("a soft alert belongs ABOVE `_emit_morning`") is about where an alert is RAISED. This
        # raises nothing: it REPORTS the alerts every handler above already raised, so it has to
        # run after the last of them or it would send a payload missing exactly the alerts that
        # arrived latest. **A mechanical rebase that "fixes" this upward into the alert block
        # silently truncates the report** — the same class of accident the ordering invariant
        # exists to catch, running the other way.
        #
        # Below the heartbeat specifically, so `summary.errors` already carries a REFUSED PING by
        # the time it is read. That is the single alert most worth escalating: it means the
        # dead-man's switch itself is not reporting, so the monitor's silence can no longer be
        # trusted to mean health. The cost of this order is that a failure of the escalation POST
        # cannot itself be escalated — it is recorded like every other soft alert and no further.
        # Something has to be last; this is the cheapest thing to lose.
        #
        # Why it exists at all: the heartbeat gate above is satisfied by a run that is merely
        # non-fatal, so a run that raised every alert in this block still pings GREEN. While the
        # owner is at the machine that is fine — the digest carries the alerts. Unattended it is
        # not: the digest is a local file in no synced folder, so a fortnight of degraded runs
        # reads as a fortnight of healthy ones. Presence-gated and unset by default (D-076
        # fail-open), so this is a no-op for anyone who has not configured an endpoint.
        try:
            # The SLICE, never the whole list — see `escalatable_from` above. A stage error is
            # not an alert, and escalating one is how this channel would train its reader to
            # ignore it.
            escalation_alert = escalate_alerts(run_id, tuple(summary.errors[escalatable_from:]))
            if escalation_alert is not None:
                console.print(f"  ! {escalation_alert}", markup=False)
                summary.errors.append(escalation_alert)
                append_run_error(engine, run_id, escalation_alert)
        except Exception as exc:  # noqa: BLE001 - never mask the run's own outcome
            # Durable, not print-only like the heartbeat's fallback next door. A permanently
            # misconfigured URL — a typo'd port raises `httpx.InvalidURL`, which is NOT an
            # `HTTPError` — would otherwise cost one console line per run into a launchd log
            # nobody opens, with no record anywhere: the exact silent degradation this feature
            # exists to end. `append_run_error` is safe here because `finish_run` committed long
            # ago and it can touch neither status nor finished_at.
            note = f"alert escalation not sent: {exc}"
            console.print(f"  ! {note}", markup=False)
            summary.errors.append(note)
            append_run_error(engine, run_id, note)


def _load_board_coverage(
    engine: Engine, run_id: int, console: Console
) -> BoardCoverageReport | None:
    """This run's board-coverage report, or `None` if it could not be read (D-274).

    Scoped to THIS run's `board_scans` rows, not the latest scanned run: the artifact is
    stamped with a run number and must describe that run's boards. Every run before the
    coverage columns existed therefore reports honestly rather than borrowing a later run's
    numbers.

    Catches broadly and on purpose. `load_board_coverage` already degrades a single bad ROW
    to `unreadable`, but a store whose schema predates the four columns raises
    `OperationalError` for the whole SELECT, and this is called from a `finally` that may
    already be unwinding an exception. A reporting failure must cost this section only --
    letting it escape would lose the entire funnel, which is the artifact that explains the
    run.
    """
    try:
        with engine.connect() as conn:
            return build_board_coverage_report(load_board_coverage(conn, run_id=run_id))
    except Exception as exc:  # noqa: BLE001 - a mute section beats a missing artifact
        console.print(f"  ! board coverage not measured: {exc}", markup=False)
        return None


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
            # Read off `scan_summary` for the same reason `boards_attempted` and `fetch_cost`
            # above are: these two complete the partition of `boards_attempted` and nothing
            # else in the pipeline consumes them, so carrying them through `PipelineSummary`
            # would add two fields with one reader apiece.
            boards_partial=scan_summary.partial if scan_summary else 0,
            boards_unchanged=scan_summary.unchanged if scan_summary else 0,
            boards_failed=summary.scan_boards_failed,
            postings_seen=summary.scan_postings_seen,
            # `None` when no scan ran, so the artifact distinguishes "not measured" from
            # "measured and empty" (D-330). A lane never reaches the timing seam and is
            # deliberately absent rather than present at zero.
            fetch_cost=None if scan_summary is None else tuple(
                ProviderFetchCost(
                    provider=provider, boards=cost.boards,
                    seconds=cost.seconds, untimed=cost.untimed,
                )
                for provider, cost in scan_summary.fetch_cost.items()
            ),
        ),
        shortlist=summary.shortlist,
        liveness=LivenessCheck(
            checked=summary.liveness_checked,
            dead=summary.liveness_dead,
            unknown=summary.liveness_unknown,
            gone_after_redirect=summary.liveness_gone_after_redirect,
        ),
        # D-325. `None` when the sweep did not run — never a block of zeros.
        death_probe=summary.death_probe,
        stage_durations=summary.stage_durations,
        tailored=[
            (lead.posting_id, lead.company, lead.title, lead.out_dir, lead.pdf_built)
            for lead in summary.tailored
        ],
        tailor_failed=summary.tailor_failed,
        # P5a — the run's own verdict decides whether the artifact carries a `projection` stage.
        # `None` means `--project` was never passed and there is nothing to report; it is
        # deliberately distinct from `AVAILABLE` (see `PipelineSummary.projection_availability`),
        # and it is read here rather than testing the counter for emptiness, which is a different
        # question with two legitimate answers.
        projection_ran=summary.projection_availability is not None,
        projection_outcomes=summary.projection_outcomes,
        rewrite_rows=summary.rewrite_rows,
        # Already loaded once above; the morning artifact receives this identical object.
        board_coverage=summary.board_coverage,
        # D7. Passed straight through — a lane's counters are in-memory tallies of requests it
        # made, so there is nothing to read back out of the store for them. What the lane
        # PERSISTED is recounted independently anyway: its postings arrive in the per-source
        # table under `company_source='lane'`, through a query that never saw this list.
        lanes=summary.lanes,
        # P4 item 6: one coverage report per lead, same order as `tailored`, for the funnel's
        # coverage summary. Mirrors how `rewrite_rows` is passed separately, not via the Lead.
        coverages=[lead.coverage for lead in summary.tailored],
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
                    coverage=lead.coverage,
                )
            )

    artifact = build_morning(
        run_id=summary.run_id,
        funnel_name=f"funnel-{summary.run_id}.md",
        leads=rows,
        # The SAME object the funnel got, not a second load — see the call site.
        board_coverage=summary.board_coverage,
        # The same two the funnel receives, from the same lists, and passed the same way. The
        # digest is the artifact the owner actually opens, so an alert that only reached the
        # funnel reached nobody during an unattended fortnight. Passed rather than re-derived:
        # one writer, one list, so the two artifacts cannot drift about what this run raised.
        errors=summary.errors,
        fatal=summary.fatal,
    )
    return write_morning(artifact, day_dir)


def _interleave(first: list[str], second: list[str]) -> list[str]:
    """Both lists represented from the front, so a capped view cannot fall inside just one.

    Taken one from each in turn rather than concatenated: the caller shows the first three, and a
    concatenation ordered lead-then-folder would let three lead failures suppress every folder
    cause. Order within each kind is preserved.
    """
    merged: list[str] = []
    for pair in zip_longest(first, second):
        merged.extend(item for item in pair if item is not None)
    return merged


def _sync_queue(
    engine: Engine, settings: Settings, console: Console
) -> tuple[list[str], list[str]]:
    """Drain, then rebuild, the delivery queue on disk from what the store says (design §4.3).

    **Reconcile first**, the same order and for the same reason as `delivery/server.py`'s
    `prime_queue`: a lead the owner applied to through the review page is no longer in
    `delivered_unapplied`, so only `reconcile_queue` can move its folder into `_applied/`.
    Draining is also why this is not gated on `summary.tailored` and why the call site sits in
    the run's `finally` — a day that arrived with nothing still has to retire what the owner
    acted on since yesterday, and a run that aborted early is not a reason to leave an applied
    lead sitting in the queue.

    Neither entry point raises on contention: both report `contended=True`, so a scheduled run
    colliding with a serving web app is a normal outcome that changed nothing, not an error. Both
    also report per-lead failures inside their report rather than raising; those failures are
    returned so the caller can record them durably, and they are still never re-raised here.

    **ONE STRING PER FAILURE, NOT A COUNT.** `LeadFailure` and `FolderFailure` each already carry
    a `detail`, and this function used to discard both and return `len()`. So the run line and
    `runs.errors_json` said `4 lead folder(s) failed` with the cause recorded nowhere — which is
    the same invisibility the block comment at the call site escalated this to fix, just one step
    further along: a number with no reason is not something an unattended owner can act on. Run
    139 is the measured case, and diagnosing its four took a store-versus-disk reconstruction that
    the detail strings would have answered outright.

    **THE TWO KINDS ARE RETURNED SEPARATELY, not concatenated.** The caller shows only the first
    few, so a flat list ordered sync-then-drain would let three lead failures hide every folder
    failure behind them. Keeping them apart lets the caller sample from both, and it does so
    without classifying anything by string-matching a message.

    Control characters are stripped from each detail: a queue folder may have been RENAMED by the
    owner (`_index` supports exactly that), so its name is untrusted text that reaches a one-line
    console print and a Markdown bullet in the morning digest.

    `DEFAULT_QUEUE_ROOT` is read from this module's namespace at call time rather than captured in
    a default argument, so a test can redirect the root by name; a `Settings` field would add four
    separately gated registration sites for a path no config file needs to carry.
    """
    root = DEFAULT_QUEUE_ROOT
    with engine.connect() as conn:
        # The owner's name for the résumé filename, resolved by the one function that already
        # owns that question (`answers.yaml` first, the authored résumé's header second), on the
        # connection already open here rather than by reading the résumé a second time.
        owner_name = resolve_owner_name(conn, settings.config_dir)
        drained = reconcile_queue(conn, root=root)
        synced = sync_queue(conn, root=root, owner_name=owner_name)
    contended = " (contended, nothing changed)" if synced.contended or drained.contended else ""
    console.print(
        f"  queue → {root}: {synced.created} new, {synced.updated} updated, "
        f"{synced.unchanged} unchanged, {synced.moved + drained.moved} moved, "
        f"{synced.failed + drained.failed} failed{contended}",
        markup=False,
    )
    # Both halves of the partition: a lead `sync_queue` could not write, and a folder
    # `reconcile_queue` could not move. They are one list to the caller because the answer to
    # either is the same — the queue on disk no longer matches what the store says was delivered.
    # Named by what each report identifies its failures BY, which differs for a reason:
    # `sync_queue` works from the database and knows the posting, `reconcile_queue` works from
    # disk and knows only the folder.
    return (
        [f"posting {item.posting_id}: {_oneline(item.detail)}" for item in synced.failures],
        [f"folder {_oneline(item.folder)}: {_oneline(item.detail)}" for item in drained.failures],
    )


def _oneline(text: str) -> str:
    """Untrusted text flattened to one line for a console print and a Markdown bullet.

    Queue folder names are owner-renameable, so a newline or a control character in one would
    break the single-line alert the digest promises. Replaced rather than dropped so the length
    still reflects what was there.
    """
    return "".join(
        " " if character < " " or character == "\x7f" else character for character in text
    )


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
