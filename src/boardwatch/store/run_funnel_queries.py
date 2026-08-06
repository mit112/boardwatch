"""Store-side counts for the per-run funnel artifact (PROGRAM.md §3.P0.1).

Every number here is read back out of the STORE, independently of the in-memory
`PipelineSummary` the pipeline hands back. That separation is the whole point:
`CLAUDE.md` — *"A component's self-report is not verification. Count the deliverable
through a different path than the one that produced it."* The funnel writer compares the
two and records any disagreement rather than picking a winner.

**`no_current_evaluation` is its own sweep — a `NOT IN` subquery — never
`open_postings - evaluated`.**
A reconciliation between numbers where one was computed by subtracting the others cannot ever
fail, and an assertion that cannot fail is the defect this repo has now been burned by four
times. That makes `corpus_reconciles` the one identity here that a database state can break.

The attribution buckets and the verdict split are a different matter and are NOT presented as
evidence: both are SQL partitions of the very subquery `evaluated` counts, so their sums equal
it by construction. Their VALUES carry the signal; the funnel marks those two stages `derived`
so no reader mistakes their balance for verification.

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

# Application statuses that imply a submission actually happened. `interested` is excluded
# because it is `create_application`'s default and means only that a lead was tracked;
# `withdrawn` because it cannot distinguish withdrawing an application from withdrawing
# interest before applying.
APPLIED_STATUSES = ("applied", "interviewing", "offer", "rejected")

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
        """Every open posting either has a current-identity evaluation or does not.

        The ONLY genuinely falsifiable identity in this dataclass, because
        `no_current_evaluation` is its own NOT EXISTS sweep over a different table
        expression (a NOT IN subquery). `judged_this_run + cache_hit_* == evaluated` and
        `sum(by_verdict) == evaluated` are deliberately NOT offered as properties: both are
        partitions of the very subquery `evaluated` counts, so they hold for every possible
        database state. Shipping them as `*_reconciles` would be shipping two assertions that
        cannot fail, which is the defect this repo keeps rediscovering. The funnel labels
        those two stages `derived` instead.
        """
        return self.open_postings == self.evaluated + self.no_current_evaluation


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

    # Its own sweep (a NOT IN subquery), not open_postings - evaluated. A posting lands here when it
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


@dataclass(frozen=True)
class SourceOutcome:
    """One watched board's outcomes this run — PROGRAM.md §3.P0 item 3.

    `open_postings` is the denominator, and it is deliberately NOT `postings_seen` per board.
    D-022: a board that answered 304 listed nothing this run and would show a denominator of
    zero while still owning hundreds of open postings the funnel judged.

    **`unique` and `assisted` are `None`, never 0.** Both are dedup-attribution quantities —
    `assisted` credits a source that arrived second for a posting another source won. Postings
    are 1:1 with jobs here and each belongs to exactly one company, so there is no second source
    to credit and neither is measurable until P6 lands dedup. Reporting 0 would assert "no
    source ever arrived second", which is the naive attribution job-apps records as having
    nearly cost it a working adapter.
    """

    provider: str
    board_slug: str
    company_source: str
    open_postings: int
    eligible: int
    leads: int
    applied: int
    unique: int | None = None
    assisted: int | None = None

    @property
    def board(self) -> str:
        return f"{self.provider}:{self.board_slug}"


def count_by_source(
    conn: Connection,
    *,
    identity: tuple[str, str] | None,
    engine_kind: str,
    engine_version: str,
    run_id: int,
    posting_ids: list[int],
) -> tuple[SourceOutcome, ...]:
    """Per-board outcomes, as four independent sweeps merged on company id.

    Four sweeps rather than one joined query because `artifacts` and `applications` are both
    many-per-posting in principle: folding them into a single GROUP BY would fan out and
    multiply the open-posting denominator by rows that have nothing to do with it.

    Every count here travels through the `companies` join that the funnel's own stages never
    touch, so `sum(per_source) == funnel total` is a genuinely falsifiable check rather than a
    partition of itself: an open posting whose company row vanished, or an artifact with no
    posting_version, shows up as a disagreement instead of silently shrinking the table.
    """
    open_by_company = dict(
        conn.execute(
            select(postings.c.company_id, func.count())
            .where(postings.c.status == "open")
            .group_by(postings.c.company_id)
        ).all()
    )

    eligible_by_company: dict[int, int] = {}
    if identity is not None:
        profile_hash, rules_hash = identity
        judged = _current_identity_evaluations(
            profile_hash=profile_hash,
            rules_hash=rules_hash,
            engine_kind=engine_kind,
            engine_version=engine_version,
        ).subquery()
        eligible_by_company = dict(
            conn.execute(
                select(postings.c.company_id, func.count())
                .select_from(judged)
                .join(postings, postings.c.id == judged.c.posting_id)
                .where(judged.c.verdict == "eligible")
                .group_by(postings.c.company_id)
            ).all()
        )

    # artifacts carries no posting_id — only posting_version_id — so the board a lead came
    # from is reachable only through its version. An artifact whose posting_version_id is NULL
    # is attributable to no board and is what the leads reconciliation exists to surface.
    leads_by_company = dict(
        conn.execute(
            select(postings.c.company_id, func.count(func.distinct(postings.c.id)))
            .select_from(artifacts)
            .join(posting_versions, posting_versions.c.id == artifacts.c.posting_version_id)
            .join(postings, postings.c.id == posting_versions.c.posting_id)
            .where(artifacts.c.run_id == run_id, artifacts.c.kind == TAILORED_KIND)
            .group_by(postings.c.company_id)
        ).all()
    )

    applied_by_company: dict[int, int] = {}
    if posting_ids:
        # Same scoping and status filter as count_applied_for_postings, so the two agree by
        # construction on which rows count as a submission.
        applied_by_company = dict(
            conn.execute(
                select(postings.c.company_id, func.count(func.distinct(applications.c.job_id)))
                .select_from(postings)
                .join(applications, applications.c.job_id == postings.c.job_id)
                .where(
                    postings.c.id.in_(posting_ids),
                    applications.c.status.in_(APPLIED_STATUSES),
                )
                .group_by(postings.c.company_id)
            ).all()
        )

    # A board with no open postings can still own a lead, if its posting closed mid-run. Keyed
    # off the union rather than off open_postings alone so a lead can never vanish from the
    # table — a missing lead reads as a smaller funnel, the one thing this artifact must not do.
    company_ids = (
        set(open_by_company)
        | set(eligible_by_company)
        | set(leads_by_company)
        | set(applied_by_company)
    )
    if not company_ids:
        return ()
    meta = {
        int(row[0]): (str(row[1]), str(row[2]), str(row[3]))
        for row in conn.execute(
            select(companies.c.id, companies.c.provider, companies.c.slug, companies.c.source)
            .where(companies.c.id.in_(company_ids))
        ).all()
    }
    outcomes = [
        SourceOutcome(
            # A company row that vanished is a real anomaly: labelled unknown and kept, never
            # dropped, so the reconciliation against the funnel's totals still catches it.
            provider=meta.get(company_id, ("unknown", "unknown", "unknown"))[0],
            board_slug=meta.get(company_id, ("unknown", "unknown", "unknown"))[1],
            company_source=meta.get(company_id, ("unknown", "unknown", "unknown"))[2],
            open_postings=int(open_by_company.get(company_id, 0)),
            eligible=int(eligible_by_company.get(company_id, 0)),
            leads=int(leads_by_company.get(company_id, 0)),
            applied=int(applied_by_company.get(company_id, 0)),
        )
        for company_id in company_ids
    ]
    # Leads first: the artifact's job is to answer which source produced each lead, so the
    # boards that produced one belong at the top rather than buried among 118 rows.
    return tuple(
        sorted(
            outcomes,
            key=lambda item: (-item.leads, -item.eligible, -item.open_postings, item.board),
        )
    )


def count_applied_for_postings(conn: Connection, posting_ids: list[int]) -> int:
    """How many of these postings' jobs carry an application that was actually SUBMITTED.

    A snapshot at artifact-write time, not a property of the run: `applications` has no
    run_id and marking applied is a later, manual act. Scoped through `jobs` because an
    application hangs off the canonical job anchor, not off a posting, so it survives its
    posting being revised or closed.

    Status is filtered, not ignored. `create_application` defaults to `interested`, which
    means a lead was merely tracked — counting it would report a posting nobody applied to as
    a conversion, in the one stage that claims to measure conversion. `withdrawn` is excluded
    for the opposite reason: it is ambiguous, since interest can be withdrawn before applying.
    A closed catalog, so a new status is a visible decision rather than a silent bucket.
    """
    if not posting_ids:
        return 0
    job_ids = select(postings.c.job_id).where(postings.c.id.in_(posting_ids))
    return int(
        conn.execute(
            select(func.count(func.distinct(applications.c.job_id))).where(
                applications.c.job_id.in_(job_ids),
                applications.c.status.in_(APPLIED_STATUSES),
            )
        ).scalar_one()
    )
