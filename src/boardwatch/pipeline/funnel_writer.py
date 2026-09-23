"""Assemble the per-run funnel artifact from the store and write it (P0 item 1).

The split is deliberate. `reports/run_funnel.py` is pure — counts in, artifact out, no
engine and no clock — and `store/run_funnel_queries.py` holds the reads. This module is the
only place that knows both, so the pure half stays testable without a database and the
queries stay testable without a pipeline.

It reads the run back out of the store rather than trusting the summary it is handed:
`CLAUDE.md` requires the deliverable be counted through a different path than the one that
produced it, and the two recounts are recorded as cross-checks so a disagreement is visible
in the artifact instead of being resolved silently in favour of whichever ran last.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, Engine, Row, select

from boardwatch.core.settings import Settings
from boardwatch.delivery.form_questions import FormQuestionSweep
from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.engine import (
    ENGINE_KIND,
    engine_version,
    not_applicable_field_families,
)
from boardwatch.eligibility.facts import parse_facts
from boardwatch.eligibility.final_gate import gate_engine_version
from boardwatch.eligibility.preflight import current_identity
from boardwatch.eligibility.read import current_evaluations_chunked
from boardwatch.extract.taxonomy import load_taxonomy
from boardwatch.projection.run import ProjectionLeadOutcome
from boardwatch.rank.leveling import load_leveling
from boardwatch.reports.abstain import AbstainReport, build_abstain_report
from boardwatch.reports.manifest import config_hash, profile_row_hash, routing_hash
from boardwatch.reports.run_funnel import (
    ApplyLaneCohort,
    BoardCoverageReport,
    CodeProvenance,
    DeathProbeReport,
    ExecutionProvenance,
    GateCounters,
    LaneReport,
    Lead,
    LivenessCheck,
    RunFunnel,
    RunIdentity,
    RunManifest,
    ScanContext,
    ShortlistCounts,
    StageDuration,
    build_projection_counters,
    build_run_funnel,
    identity_drift,
)
from boardwatch.store.abstain_queries import count_requirement_dispositions
from boardwatch.store.delivery_queries import apply_lane_cohort
from boardwatch.store.queries import (
    current_posting_versions,
    get_profile,
    get_watched_companies,
    record_corpus_counts,
)
from boardwatch.store.run_funnel_queries import (
    CorpusCounts,
    DedupSweep,
    SourceOutcome,
    TailoredArtifactCounts,
    count_applied_for_postings,
    count_by_source,
    count_corpus,
    count_open_postings,
    count_projected_tailored_artifacts,
    count_stub_postings,
    count_tailored_artifacts,
    count_unattributed_evaluations,
    lead_provenance,
    sweep_duplicates,
)
from boardwatch.store.tables import runs
from boardwatch.tailor.coverage import CoverageReport

# What a corpus looks like when there is no profile: the head is still countable, but nothing
# downstream of it has been judged, so every split is unknown rather than zero.
_EMPTY_VERDICTS: dict[str, int] = {}


def _corpus_without_profile(open_postings: int) -> CorpusCounts:
    """No profile means no identity to scope evaluations by, so nothing was judged.

    `no_current_evaluation` is the whole corpus — which is the truth, not a degradation: a
    run with no profile judged nothing, and the funnel should say so and still reconcile.
    """
    return CorpusCounts(
        open_postings=open_postings,
        evaluated=0,
        no_current_evaluation=open_postings,
        by_verdict=_EMPTY_VERDICTS,
        judged_this_run=0,
        cache_hit_prior_run=0,
        cache_hit_unattributed=0,
    )


def manifest_identity(
    settings: Settings,
    *,
    identity: tuple[str, str] | None,
    profile_row: Row[Any] | None,
) -> RunIdentity:
    """The manifest's six values, from `current_identity` and the profile row (T137).

    The ONE computation of them. `collect_run_funnel` builds the manifest from it and
    `run_pipeline` reads the run's start identity through it (`read_run_identity`), so a
    difference between the two readings is an input that moved. A second copy of this would be a
    second opinion able to drift from the first — the defect class T137 exists to report.
    """
    return RunIdentity(
        code_fingerprint=engine_version(),
        config_hash=config_hash(settings),
        profile_facts_hash=identity[0] if identity is not None else None,
        rules_hash=identity[1] if identity is not None else None,
        profile_row_hash=(
            profile_row_hash(
                skills=profile_row.skills_json,
                target_titles=profile_row.target_titles_json,
                exclude_titles=profile_row.exclude_titles_json,
                locations=profile_row.locations_json,
                remote_only=profile_row.remote_only,
                target_seniority_band=profile_row.target_seniority_band,
                leveling_digest=load_leveling(settings.config_dir).digest,
                taxonomy_version=load_taxonomy(settings.config_dir).version,
            )
            if profile_row is not None
            else None
        ),
        # T111. The SIXTH value. It reads the same `settings` object and adds nothing to any hash
        # above it — a run that flips a routing knob moves this and only this.
        routing_hash=routing_hash(settings),
    )


def read_run_identity(conn: Connection, settings: Settings) -> RunIdentity:
    """`manifest_identity` over the same two reads `collect_run_funnel` makes."""
    return manifest_identity(
        settings, identity=current_identity(conn, settings), profile_row=get_profile(conn)
    )


#: The `boardwatch` package directory — where the running code was imported from, which on the
#: daily driver is an EDITABLE checkout parked on whatever branch that tree is on.
_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
#: Per git call. Provenance is reporting, and a hung git must cost the field, never the run.
_GIT_TIMEOUT_SECONDS = 5.0


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        errors="replace",
        check=True,
        timeout=_GIT_TIMEOUT_SECONDS,
    ).stdout


def code_provenance(root: Path) -> CodeProvenance | None:
    """The commit `root` is checked out at and whether its tree is dirty, or `None`.

    `None` — never a guess — when `root` is not a git checkout (a wheel install), when git is
    missing, fails or times out. FAIL-OPEN: nothing here may fail a run.

    `ls-files --error-unmatch` first, because a wheel installed into a virtualenv INSIDE a
    checkout sits in a git work tree without being part of it: `rev-parse HEAD` would answer
    with the enclosing checkout's commit, which names code that did not run. The package's own
    `__init__.py` being TRACKED is what makes `root` the source the process imported.

    `--no-optional-locks` on the status call: a plain `git status` refreshes and rewrites the
    index under `index.lock`, and this runs unattended against the owner's own checkout — a
    concurrent commit there must not meet a lock this took, and a run killed mid-call must not
    leave one behind.
    """
    try:
        _git(root, "ls-files", "--error-unmatch", "--", "__init__.py")
        commit = _git(root, "rev-parse", "HEAD").strip()
        dirty = bool(_git(root, "--no-optional-locks", "status", "--porcelain").strip())
    except (OSError, subprocess.SubprocessError):
        return None
    return CodeProvenance(commit=commit, dirty=dirty)


def read_execution_provenance(
    conn: Connection,
    settings: Settings,
    *,
    boards_attempted: int,
    skip_scan: bool,
    project: bool,
    liveness_prober: bool,
    top_n: int,
) -> ExecutionProvenance:
    """T137's execution provenance, from `settings`, the store and the command's own flags."""
    return ExecutionProvenance(
        code=code_provenance(_PACKAGE_ROOT),
        gate_engine_version=gate_engine_version(),
        gate_model=settings.gate.model,
        gate_effort=settings.gate.effort,
        lanes=settings.lanes_enabled,
        watched_companies=len(get_watched_companies(conn)),
        boards_attempted=boards_attempted,
        skip_scan=skip_scan,
        project=project,
        liveness_prober=liveness_prober,
        top_n=top_n,
    )


def collect_run_funnel(
    engine: Engine,
    settings: Settings,
    *,
    run_id: int,
    scan: ScanContext,
    shortlist: ShortlistCounts | None,
    liveness: LivenessCheck | None = None,
    # D-325. `None` means the measured-death sweep did NOT run, never that it found nothing.
    death_probe: DeathProbeReport | None = None,
    # T96. `None` means the Greenhouse application-form sweep did NOT run — no fetcher, a budget
    # of 0, or it raised — never that it found no candidates.
    form_questions: FormQuestionSweep | None = None,
    # T42. `None` means the gate was NOT armed this run (`settings.gate.enabled` False),
    # never that it judged nothing.
    gate: GateCounters | None = None,
    # T43 appended `pending_tailor`: a review-lane lead delivered with no PDF.
    tailored: list[tuple[int, str, str, Path, bool, bool]],
    tailor_failed: int,
    # P5a. `projection_ran` is the ONLY thing that decides whether the artifact carries a
    # `projection` stage — never whether `projection_outcomes` is non-empty. A projected run can
    # legitimately count nothing (the preflight refused before the loop, or every shortlisted lead
    # was withheld as gone), and the converse hazard is real too: `_retract_projected` would leave
    # `PROJECTED: -1` on a counter it was called against with no `PROJECTED` key, which is
    # unreachable today only because `ResumeLineageMismatch` has one raise site gated on a lineage
    # being present. Reading the run's own verdict instead means neither accident can move the
    # stage in or out of the artifact.
    #
    # REQUIRED, with no default. A default of `False` fails in the omission direction: a caller
    # that forgot the argument would silently claim projection never ran and drop the whole stage
    # from the artifact, which reads as a legitimate authored run rather than as a mistake. There
    # is no safe default in the other direction either — `True` would fabricate an empty stage on
    # every authored run — so the honest answer is that the caller must state it and the type
    # checker enforces that it did.
    projection_ran: bool,
    projection_outcomes: Mapping[ProjectionLeadOutcome, int] | None = None,
    rewrite_rows: list[dict[str, object]],
    coverages: Sequence[CoverageReport | None] = (),
    # D-274. Loaded by the CALLER (`runner._load_board_coverage`) and passed in, because the
    # morning artifact must render the identical object: `held` has no run dimension, so two
    # loads can disagree. Building it here would reintroduce exactly that drift.
    board_coverage: BoardCoverageReport | None = None,
    # D7. Built by the pipeline's lane stage and passed straight through — there is nothing to
    # read back out of the store for it: a lane's outcome counters are in-memory tallies of
    # requests it made, and the postings it DID land are already counted by the per-source table
    # (a lane company carries `company_source='lane'`, so the attribution comes free). Required
    # rather than defaulted here, unlike in the pure builder: this module has exactly one caller
    # and a forgotten argument should be a type error rather than a silently lane-less artifact.
    lanes: Sequence[LaneReport],
    # Timed by the CALLER (`runner._StageClock`) and passed straight through: stage wall clock
    # is in-memory measurement of work the pipeline did, with nothing to read back out of the
    # store. `None` means the run was not timed at all — the honest reading for a stored
    # artifact written before this shipped — which is not the same as an empty sequence.
    stage_durations: Sequence[StageDuration] | None,
    # T137. The identity `run_pipeline` read before ranking, through `read_run_identity`. `None`
    # means NOT MEASURED — every caller outside `run_pipeline`, and a start reading that failed —
    # and the artifact says so rather than reporting a stable run.
    start_identity: RunIdentity | None = None,
    # T137. `None` means not recorded, and the section says so.
    execution_provenance: ExecutionProvenance | None = None,
    errors: list[str],
    fatal: str | None,
) -> RunFunnel:
    """Read every count this run's funnel needs, then hand them to the pure builder.

    `tailored` is (posting_id, company, title, out_dir, pdf_built, pending_tailor) per lead —
    plain tuples so this module does not import `PipelineSummary` and make pipeline -> reports
    -> pipeline a cycle. `coverages` is one per-lead coverage report in the SAME order (P4 item
    6), passed separately from the tuple exactly as `rewrite_rows` is.
    """
    catalog = load_rules(settings.config_dir)
    posting_ids = [posting_id for posting_id, _, _, _, _, _ in tailored]

    with engine.connect() as conn:
        identity = current_identity(conn, settings)
        profile_row = get_profile(conn)
        if identity is None:
            corpus = _corpus_without_profile(count_open_postings(conn))
            abstain: AbstainReport = build_abstain_report(
                catalog, {}, not_applicable_families=frozenset()
            )
        else:
            profile_hash, rules_hash = identity
            corpus = count_corpus(
                conn,
                profile_hash=profile_hash,
                rules_hash=rules_hash,
                engine_kind=ENGINE_KIND,
                engine_version=engine_version(),
                run_id=run_id,
            )
            # Same scope as `eligibility abstain`: the CURRENT evaluation of every OPEN
            # posting. Keeping the scopes identical is what lets the two be compared at all.
            versions = current_posting_versions(conn, None)
            evals = current_evaluations_chunked(
                conn, [cv.posting_version_id for cv in versions.values()], *identity
            )
            counts = count_requirement_dispositions(conn, [eid for eid, _ in evals.values()])
            # `identity` came from `current_identity`, which only returns non-None when a
            # profile row exists — so the profile is guaranteed here.
            assert profile_row is not None
            na = not_applicable_field_families(
                parse_facts(profile_row.eligibility_facts_json), catalog
            )
            abstain = build_abstain_report(catalog, counts, not_applicable_families=na)

        # ONE corpus-wide duplicate sweep, read by two consumers: the per-source `unique`
        # column and the funnel's `dedup` stage. Run here rather than inside `count_by_source`
        # so the stage and the column cannot disagree about a corpus that moved between them.
        dedup: DedupSweep = sweep_duplicates(conn)
        # Per board (P0 item 3). Passed the identity rather than the two hashes so a run with
        # no profile reports every board's `eligible` as 0 without a second code path.
        sources: tuple[SourceOutcome, ...] = count_by_source(
            conn,
            identity=identity,
            engine_kind=ENGINE_KIND,
            engine_version=engine_version(),
            run_id=run_id,
            posting_ids=posting_ids,
            dedup=dedup,
        )
        tailored_artifacts: TailoredArtifactCounts = count_tailored_artifacts(conn, run_id)
        # An INDEPENDENT recount of the projected leads: artifact rows whose meta carries the
        # projection lineage, read here rather than derived from the counter the loop incremented.
        # Read only on a projected run — on an authored one the answer is 0 by construction and
        # there is nothing to compare it with.
        projected_lineage_rows = (
            count_projected_tailored_artifacts(conn, run_id) if projection_ran else 0
        )
        # T110. B8's volume cohort, read HERE and not from the leads this function was handed.
        # The two answer different questions and the ordering is what separates them: a lead's
        # `pending_tailor` flag — which the `pdf` stage enters at — was stamped before the tailor
        # loop, while `runner`'s application-form sweep runs after the render and before this
        # artifact is written. So a rendered apply-lane lead that the sweep hard-stopped in the
        # same run is inside `pdf.entered` and is NOT in this cohort, which is the whole point.
        #
        # Read through `apply_lane_cohort` rather than recomputed from `tailored` for the reason
        # every other count in this block is read back out of the store: the funnel must count
        # the deliverable through a different path than the one that produced it, and this one
        # re-runs the real `review_gate.lane` over the state the run actually left behind.
        apply_lane = ApplyLaneCohort(
            placements=apply_lane_cohort(conn, run_ids={run_id}).get(run_id, ())
        )
        marked_applied = count_applied_for_postings(conn, posting_ids)
        unattributed = count_unattributed_evaluations(conn)
        provenance = lead_provenance(conn, posting_ids)
        stub_postings = count_stub_postings(conn)
        row = conn.execute(
            select(runs.c.started_at, runs.c.finished_at, runs.c.status).where(
                runs.c.id == run_id
            )
        ).one_or_none()

    # The corpus counts, onto the run row (D-371). Written from the `corpus` object the block
    # above already produced rather than re-counted: `count_corpus` is five sweeps over the
    # whole open corpus, and a second independent sweep here would not only pay that cost
    # twice, it could DISAGREE with the artifact — two numbers for one run's corpus, with
    # nothing to say which is authoritative.
    #
    # Before the manifest and the artifact write, so the counts survive a later reporting
    # failure. Everything from `RunManifest(` down can raise (the caller catches it, records
    # the failure and stays fail-open, D-287); a corpus collapse is exactly the kind of
    # upstream change that could also break artifact rendering, and the run whose numbers the
    # detector most needs must not be the one run that recorded none.
    #
    # `candidates` folds the two DELIVERABLE verdicts. `ineligible` cannot become a lead, so
    # it is not a candidate; the fold is a monitoring numerator, and the funnel's own verdict
    # stage keeps the split unfolded for every reader.
    record_corpus_counts(
        engine,
        run_id,
        open_postings=corpus.open_postings,
        evaluated=corpus.evaluated,
        candidates=corpus.by_verdict.get("eligible", 0) + corpus.by_verdict.get("uncertain", 0),
    )

    # T137. The END reading, through the function the start reading used — see
    # `manifest_identity`.
    end_identity = manifest_identity(settings, identity=identity, profile_row=profile_row)
    manifest = RunManifest(
        code_fingerprint=end_identity.code_fingerprint,
        config_hash=end_identity.config_hash,
        profile_facts_hash=end_identity.profile_facts_hash,
        rules_hash=end_identity.rules_hash,
        profile_row_hash=end_identity.profile_row_hash,
        # `runs.status` is `running` until finish_run stamps it; a funnel written from the
        # pipeline's finally block reads the terminal value finish_run just wrote (D-029).
        status=row.status if row is not None else "running",
        # D-323. In plain text beside `config_hash`, which already covers it: a hash cannot
        # tell a reader whether the hard US gate was armed, and without that each lead's
        # `location_class` is a verdict with no claim attached to it.
        location_filter_mode=settings.location_filter_mode,
        routing_hash=end_identity.routing_hash,
    )

    leads = [
        Lead(
            posting_id=posting_id,
            title=title,
            company=company,
            # A lead whose company row vanished is a real anomaly, so it is labelled as
            # unknown rather than dropped from the table — a missing lead reads as a smaller
            # funnel, which is the one thing this artifact must never do.
            provider=provenance[posting_id].provider if posting_id in provenance else "unknown",
            board_slug=(
                provenance[posting_id].board_slug if posting_id in provenance else "unknown"
            ),
            company_source=(
                provenance[posting_id].company_source if posting_id in provenance else "unknown"
            ),
            out_dir=str(out_dir),
            pdf_built=pdf_built,
            # D-323. `None` on a lead whose posting row did not resolve, the same anomaly the
            # three fields above label `"unknown"` — which is what distinguishes it from a
            # posting that resolved and named no place.
            locations=provenance[posting_id].locations if posting_id in provenance else None,
            pending_tailor=pending_tailor,
        )
        for posting_id, company, title, out_dir, pdf_built, pending_tailor in tailored
    ]

    return build_run_funnel(
        run_id=run_id,
        started_at=row.started_at if row is not None else None,
        finished_at=row.finished_at if row is not None else None,
        manifest=manifest,
        scan=scan,
        corpus=corpus,
        shortlist=shortlist,
        liveness=liveness,
        death_probe=death_probe,
        form_questions=form_questions,
        gate=gate,
        apply_lane=apply_lane,
        dedup=dedup,
        sources=sources,
        leads=leads,
        tailor_failed=tailor_failed,
        projection=(
            build_projection_counters(projection_outcomes or {}) if projection_ran else None
        ),
        projected_lineage_rows=projected_lineage_rows,
        tailored_artifacts=tailored_artifacts,
        marked_applied=marked_applied,
        stub_postings=stub_postings,
        rewrite_rows=rewrite_rows,
        unattributed_evaluations=unattributed,
        abstain=abstain,
        coverages=coverages,
        board_coverage=board_coverage,
        lanes=lanes,
        stage_durations=stage_durations,
        identity_drift=(
            None if start_identity is None else identity_drift(start_identity, end_identity)
        ),
        provenance=execution_provenance,
        errors=errors,
        fatal=fatal,
    )
