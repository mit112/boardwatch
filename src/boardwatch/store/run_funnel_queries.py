"""Store-side counts for the per-run funnel artifact (PROGRAM.md §3.P0.1).

Every number here is read back out of the STORE, independently of the in-memory
`PipelineSummary` the pipeline hands back. That separation is the whole point:
`CLAUDE.md` — *"A component's self-report is not verification. Count the deliverable
through a different path than the one that produced it."* The funnel writer compares the
two and records any disagreement rather than picking a winner.

**The counts are deliberately NOT derived from one another.** `no_current_evaluation` is
its own `NOT EXISTS` sweep rather than `open_postings - evaluated`, and the attribution
buckets are their own `GROUP BY` rather than a remainder. A reconciliation between numbers
where one was computed by subtracting the others cannot ever fail, and an assertion that
cannot fail is the defect this repo has now been burned by four times.

No import from `boardwatch.eligibility` — the engine kind and version are parameters. The
eligibility layer reads and writes the store; the reverse dependency would invert the
layering (see `queries.save_eligibility`, which states the same rule).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy import Connection, Select, case, func, literal, select, tuple_

from boardwatch.store.tables import (
    applications,
    artifacts,
    companies,
    eligibility_evaluations,
    eligibility_inputs,
    posting_versions,
    postings,
)

# The Tier A résumé artifact the pipeline's tailor stage writes, one per lead.
TAILORED_KIND = "resume_tailored"

# Attribution buckets. `unattributed` is kept apart from `prior_run` because a NULL run_id
# means exactly one thing (D-019) — the row predates run attribution — and folding it into
# either neighbour would destroy the only evidence that the population is not growing.
THIS_RUN = "judged_this_run"
PRIOR_RUN = "cache_hit_prior_run"
UNATTRIBUTED = "cache_hit_unattributed"


@dataclass(frozen=True)
class CorpusCounts:
    """The open-posting corpus, split by what the store says happened to each posting.

    `open_postings` is the funnel's head. Note it is NOT `ScanSummary.postings_seen`:
    `postings_seen` counts postings a board LISTED this run (an unchanged board returns 304
    and lists none), while this counts every open posting in the store. They are different
    populations, so chaining one into the other would be arithmetic that is wrong on every
    run with an unchanged board or a `--no-scan`.
    """

    open_postings: int
    evaluated: int
    no_current_evaluation: int
    by_verdict: Mapping[str, int]
    judged_this_run: int
    cache_hit_prior_run: int
    cache_hit_unattributed: int

    @property
    def corpus_reconciles(self) -> bool:
        """Every open posting either has a current-identity evaluation or does not."""
        return self.open_postings == self.evaluated + self.no_current_evaluation

    @property
    def attribution_reconciles(self) -> bool:
        """Every evaluated posting was judged this run or was already on file."""
        return self.evaluated == (
            self.judged_this_run + self.cache_hit_prior_run + self.cache_hit_unattributed
        )

    @property
    def verdict_reconciles(self) -> bool:
        return self.evaluated == sum(self.by_verdict.values())


def _current_identity_evaluations(
    *, profile_hash: str, rules_hash: str, engine_kind: str, engine_version: str
) -> Select[tuple[int, str, int | None]]:
    """(posting_id, verdict, run_id) for each OPEN posting's CURRENT version's evaluation.

    At most one row per open posting: `input_fingerprint` is unique per (posting version,
    profile, rules) and `uq_eligibility_deterministic` is unique per (input, engine_version)
    — but only `WHERE engine_kind = 'deterministic'`, it is a PARTIAL index. The engine_kind
    filter is therefore load-bearing, not decorative: without it the un-deduped LLM lane
    would contribute extra rows and inflate every count in this module.
    """
    newest = posting_versions.alias("pv_newer")
    newer = (
        select(newest.c.id)
        .where(
            newest.c.posting_id == posting_versions.c.posting_id,
            tuple_(newest.c.captured_at, newest.c.id)
            > tuple_(posting_versions.c.captured_at, posting_versions.c.id),
        )
        .exists()
    )
    return (
        select(
            postings.c.id.label("posting_id"),
            eligibility_evaluations.c.verdict,
            eligibility_evaluations.c.run_id,
        )
        .select_from(postings)
        .join(posting_versions, posting_versions.c.posting_id == postings.c.id)
        .join(eligibility_inputs, eligibility_inputs.c.posting_version_id == posting_versions.c.id)
        .join(
            eligibility_evaluations,
            eligibility_evaluations.c.input_id == eligibility_inputs.c.id,
        )
        .where(
            postings.c.status == "open",
            ~newer,
            eligibility_inputs.c.profile_hash == profile_hash,
            eligibility_inputs.c.rules_hash == rules_hash,
            eligibility_evaluations.c.engine_kind == engine_kind,
            eligibility_evaluations.c.engine_version == engine_version,
        )
    )


def count_open_postings(conn: Connection) -> int:
    return int(
        conn.execute(
            select(func.count()).select_from(postings).where(postings.c.status == "open")
        ).scalar_one()
    )


def count_corpus(
    conn: Connection,
    *,
    profile_hash: str,
    rules_hash: str,
    engine_kind: str,
    engine_version: str,
    run_id: int,
) -> CorpusCounts:
    """Five independent sweeps of the corpus, so the three reconciliations can genuinely fail."""
    base = _current_identity_evaluations(
        profile_hash=profile_hash,
        rules_hash=rules_hash,
        engine_kind=engine_kind,
        engine_version=engine_version,
    )
    evaluated_sub = base.subquery()

    open_postings = count_open_postings(conn)

    evaluated = int(
        conn.execute(select(func.count()).select_from(evaluated_sub)).scalar_one()
    )

    # Its own NOT EXISTS sweep, not open_postings - evaluated. A posting lands here when it
    # has no version row at all, or its current version has never been judged under this
    # profile+rules identity — a corrected fact makes the whole corpus land here again.
    judged_ids = select(evaluated_sub.c.posting_id)
    no_current_evaluation = int(
        conn.execute(
            select(func.count())
            .select_from(postings)
            .where(postings.c.status == "open", postings.c.id.not_in(judged_ids))
        ).scalar_one()
    )

    by_verdict = {
        str(row[0]): int(row[1])
        for row in conn.execute(
            select(evaluated_sub.c.verdict, func.count()).group_by(evaluated_sub.c.verdict)
        ).all()
    }

    # The stage D-016 exists for. Without run_id, "judged during this run" and "already on
    # file" are the same number, which is precisely the indistinguishability the column was
    # added to prevent. NULL is its own bucket and is never folded into either neighbour.
    bucket = case(
        (evaluated_sub.c.run_id == run_id, literal(THIS_RUN)),
        (evaluated_sub.c.run_id.is_(None), literal(UNATTRIBUTED)),
        else_=literal(PRIOR_RUN),
    )
    attribution = {
        str(row[0]): int(row[1])
        for row in conn.execute(
            select(bucket.label("bucket"), func.count()).group_by(bucket)
        ).all()
    }

    return CorpusCounts(
        open_postings=open_postings,
        evaluated=evaluated,
        no_current_evaluation=no_current_evaluation,
        by_verdict=by_verdict,
        judged_this_run=attribution.get(THIS_RUN, 0),
        cache_hit_prior_run=attribution.get(PRIOR_RUN, 0),
        cache_hit_unattributed=attribution.get(UNATTRIBUTED, 0),
    )


def count_unattributed_evaluations(conn: Connection) -> int:
    """Evaluations carrying no run at all, across the WHOLE store.

    Reported as its own top-level number and never folded into a run's counts. Per D-019 it
    can only shrink: every write path in `src/` now mints a run rather than writing NULL, so
    a growth in this number between two runs means a NULL leaked back in.
    """
    return int(
        conn.execute(
            select(func.count())
            .select_from(eligibility_evaluations)
            .where(eligibility_evaluations.c.run_id.is_(None))
        ).scalar_one()
    )


@dataclass(frozen=True)
class TailoredArtifactCounts:
    """What the artifacts table says this run produced, read back independently.

    `with_pdf` is NOT a row count. `artifacts.uri` stores the `.typ` path whether or not a
    PDF was ever compiled, so a `resume_tailored` row can exist with no PDF — that is D-006's
    silent degrade, and reading `COUNT(*)` here would report it as a delivered lead. Whether
    the PDF compiled lives only in `meta_json.typst_pdf_built`.
    """

    rows: int
    with_pdf: int


def count_tailored_artifacts(conn: Connection, run_id: int) -> TailoredArtifactCounts:
    pdf_built = func.json_extract(artifacts.c.meta_json, "$.typst_pdf_built")
    row = conn.execute(
        select(
            func.count(),
            # SQLite's json1 yields integer 1/0 for a JSON boolean; count the truthy ones.
            func.coalesce(func.sum(case((pdf_built == 1, 1), else_=0)), 0),
        ).where(artifacts.c.run_id == run_id, artifacts.c.kind == TAILORED_KIND)
    ).one()
    return TailoredArtifactCounts(rows=int(row[0]), with_pdf=int(row[1]))


@dataclass(frozen=True)
class Provenance:
    """The board a posting came from. Gate P0 requires this per lead, from the artifact alone."""

    provider: str
    board_slug: str
    company_source: str


def lead_provenance(conn: Connection, posting_ids: list[int]) -> dict[int, Provenance]:
    """posting_id -> the watched board that produced it, in ONE query."""
    if not posting_ids:
        return {}
    rows = conn.execute(
        select(
            postings.c.id,
            companies.c.provider,
            companies.c.slug,
            companies.c.source,
        )
        .join(companies, postings.c.company_id == companies.c.id)
        .where(postings.c.id.in_(posting_ids))
    ).all()
    return {
        int(row[0]): Provenance(
            provider=str(row[1]), board_slug=str(row[2]), company_source=str(row[3])
        )
        for row in rows
    }


def count_applied_for_postings(conn: Connection, posting_ids: list[int]) -> int:
    """How many of these postings' jobs already carry an application row.

    A snapshot at artifact-write time, not a property of the run: `applications` has no
    run_id and marking applied is a later, manual act. Scoped through `jobs` because an
    application hangs off the canonical job anchor, not off a posting.
    """
    if not posting_ids:
        return 0
    job_ids = select(postings.c.job_id).where(postings.c.id.in_(posting_ids))
    return int(
        conn.execute(
            select(func.count(func.distinct(applications.c.job_id))).where(
                applications.c.job_id.in_(job_ids)
            )
        ).scalar_one()
    )
