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

from pathlib import Path

from sqlalchemy import Engine, select

from boardwatch.core.settings import Settings
from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.engine import ENGINE_KIND, current_evaluations, engine_version
from boardwatch.eligibility.preflight import current_identity
from boardwatch.reports.abstain import AbstainReport, build_abstain_report
from boardwatch.reports.run_funnel import (
    Lead,
    RunFunnel,
    ScanContext,
    ShortlistCounts,
    build_run_funnel,
)
from boardwatch.store.abstain_queries import count_requirement_dispositions
from boardwatch.store.queries import current_posting_versions
from boardwatch.store.run_funnel_queries import (
    CorpusCounts,
    SourceOutcome,
    TailoredArtifactCounts,
    count_applied_for_postings,
    count_by_source,
    count_corpus,
    count_open_postings,
    count_tailored_artifacts,
    count_unattributed_evaluations,
    lead_provenance,
)
from boardwatch.store.tables import runs

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


def collect_run_funnel(
    engine: Engine,
    settings: Settings,
    *,
    run_id: int,
    scan: ScanContext,
    shortlist: ShortlistCounts,
    tailored: list[tuple[int, str, str, Path, bool]],
    tailor_failed: int,
    errors: list[str],
    fatal: str | None,
) -> RunFunnel:
    """Read every count this run's funnel needs, then hand them to the pure builder.

    `tailored` is (posting_id, company, title, out_dir, pdf_built) per lead — plain tuples so
    this module does not import `PipelineSummary` and make pipeline -> reports -> pipeline a
    cycle.
    """
    catalog = load_rules(settings.config_dir)
    posting_ids = [posting_id for posting_id, _, _, _, _ in tailored]

    with engine.connect() as conn:
        identity = current_identity(conn, settings)
        if identity is None:
            corpus = _corpus_without_profile(count_open_postings(conn))
            abstain: AbstainReport = build_abstain_report(catalog, {})
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
            evals = current_evaluations(
                conn, [cv.posting_version_id for cv in versions.values()], *identity
            )
            counts = count_requirement_dispositions(conn, [eid for eid, _ in evals.values()])
            abstain = build_abstain_report(catalog, counts)

        # Per board (P0 item 3). Passed the identity rather than the two hashes so a run with
        # no profile reports every board's `eligible` as 0 without a second code path.
        sources: tuple[SourceOutcome, ...] = count_by_source(
            conn,
            identity=identity,
            engine_kind=ENGINE_KIND,
            engine_version=engine_version(),
            run_id=run_id,
            posting_ids=posting_ids,
        )
        tailored_artifacts: TailoredArtifactCounts = count_tailored_artifacts(conn, run_id)
        marked_applied = count_applied_for_postings(conn, posting_ids)
        unattributed = count_unattributed_evaluations(conn)
        provenance = lead_provenance(conn, posting_ids)
        row = conn.execute(
            select(runs.c.started_at, runs.c.finished_at).where(runs.c.id == run_id)
        ).one_or_none()

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
        )
        for posting_id, company, title, out_dir, pdf_built in tailored
    ]

    return build_run_funnel(
        run_id=run_id,
        started_at=row.started_at if row is not None else None,
        finished_at=row.finished_at if row is not None else None,
        scan=scan,
        corpus=corpus,
        shortlist=shortlist,
        sources=sources,
        leads=leads,
        tailor_failed=tailor_failed,
        tailored_artifacts=tailored_artifacts,
        marked_applied=marked_applied,
        unattributed_evaluations=unattributed,
        abstain=abstain,
        errors=errors,
        fatal=fatal,
    )
