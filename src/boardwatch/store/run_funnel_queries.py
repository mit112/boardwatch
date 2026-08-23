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

from boardwatch.core.dedup import resolve_duplicates
from boardwatch.core.lineage import meta_probe_key
from boardwatch.store.applications import APPLIED_STATUSES
from boardwatch.store.identity_queries import (
    identities_complete,
    load_identities,
    load_identity_inputs,
)
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


def count_stub_postings(conn: Connection) -> int:
    """Open postings whose JD body is empty after trimming — the stub-rate numerator (P0 item 6).

    Denominated over `count_open_postings`, so the two share the corpus head. `body_text` is
    NOT NULL, so a stub is a whitespace-only body, not a missing row. The two-arg `trim` names
    the strip set explicitly — SQLite's one-arg `trim` removes spaces ONLY, so a body of tabs
    or newlines would otherwise slip through as non-empty."""
    return int(
        conn.execute(
            select(func.count())
            .select_from(postings)
            .where(postings.c.status == "open")
            .where(func.trim(postings.c.body_text, " \t\n\r\f\v") == "")
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


def count_candidate_judged_this_run(
    conn: Connection,
    *,
    profile_hash: str,
    rules_hash: str,
    engine_kind: str,
    engine_version: str,
    run_id: int,
) -> int:
    """Open postings whose CURRENT-identity evaluation is a CANDIDATE verdict (`eligible` OR
    `uncertain`) AND was itself judged by THIS run (`run_id` attribution) — the P3 item 5 (B5)
    zero-output guard's predicate.

    `uncertain` counts, not only `eligible`: an `uncertain` posting can become a lead exactly like
    an `eligible` one, where an `ineligible` one cannot, and
    a run that judged new candidate work yet produced 0 leads is the silent empty day this
    guard exists to catch regardless of which of the two verdicts the candidate carries. This
    also keeps the guard's coverage intact now that a body firing no family abstains to
    `uncertain` rather than clearing to `eligible` by silence (D-250): the same normal posting
    that used to count as `eligible` still counts, under its corrected verdict.

    NOT "the ranker hides only `ineligible`" — that was this docstring's earlier claim and it is
    false (D-282). `cli/top_cmd.py` also hides `hidden_hard_filter`, `hidden_non_swe`,
    `hidden_over_seniority` and `hidden_duplicate`, so a posting counted here can still be
    withheld. This count is RUN-scoped and those buckets are CORPUS-scoped; see
    `pipeline/runner.py::_zero_output_guard` for why that mismatch leaves B5 without an
    instrument.

    Deliberately run_id-attributed rather than a cross-run "handled ledger": a steady-state day
    where every candidate posting is a cache hit from a PRIOR run has this count at 0 and is
    honest (nothing NEW happened this run), which is exactly what dissolves the reviewer's
    false-alarm concern without inventing a second identity path. Reuses
    `_current_identity_evaluations` — the same subquery `count_corpus` partitions — rather than
    a new one, per CLAUDE.md's closed-catalog default.
    """
    sub = _current_identity_evaluations(
        profile_hash=profile_hash,
        rules_hash=rules_hash,
        engine_kind=engine_kind,
        engine_version=engine_version,
    ).subquery()
    return int(
        conn.execute(
            select(func.count())
            .select_from(sub)
            .where(sub.c.verdict.in_(("eligible", "uncertain")), sub.c.run_id == run_id)
        ).scalar_one()
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

    `with_pdf` is NOT a row count. `artifacts.uri` stores the `.tex` path whether or not a
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


def count_projected_tailored_artifacts(conn: Connection, run_id: int) -> int:
    """This run's `resume_tailored` rows whose master was PROJECTED, not authored (P5a).

    The predicate is the PRESENCE of the lineage, not its value: `ResumeSourceLineage.as_meta()`
    writes every field under a `projection_` prefix, so the probed key exists on exactly the rows
    `run_tailor` was handed a lineage for. Testing presence rather than restating the literal
    `"projection"` here keeps this check from carrying its own copy of the emitter's constant —
    and the KEY is derived from the emitter too (`meta_probe_key`), not spelled out, so renaming
    the field it names moves this probe with it instead of silently matching nothing.

    Counted apart from `count_tailored_artifacts` above rather than by widening it: the funnel
    compares this against the leads the pipeline believed it projected, and a run where the
    lineage silently stopped being written would leave the row count identical while this one
    drops — the failure a plain row count cannot see.
    """
    lineage = func.json_extract(artifacts.c.meta_json, f"$.{meta_probe_key()}")
    return int(
        conn.execute(
            select(func.count()).where(
                artifacts.c.run_id == run_id,
                artifacts.c.kind == TAILORED_KIND,
                lineage.is_not(None),
            )
        ).scalar_one()
    )


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

    Both are dedup-attribution quantities. `unique` counts this source's surviving open
    postings; `assisted` counts its suppressed postings whose survivor belongs to a
    *different* company_id — it credits a source that arrived second for a posting another
    source won. They are deliberately NOT a partition: a posting suppressed in favour of a
    survivor from the same source is counted in neither, and `unique + assisted ==
    open_postings` is not an invariant — do not "fix" it into one.

    **`unique` is measured only when identities are COMPLETE.** Every open posting must
    carry a row at the current IDENTITY_ALGORITHM_VERSION. A number computed over a partial
    backfill is not a measurement, and an existence check (`if identities:`) cannot tell the
    two apart. A version bump therefore degrades `unique` to None until a re-backfill, which
    is the honest report.

    **`assisted` is not instrumented at all, and reports None — never 0.** The only kind
    permitted to suppress is `exact_quad`, which is keyed on company_id; sources ARE
    company_id, so no suppression this build can produce crosses a source boundary. There is
    no mechanism that could count one. Reporting 0 would assert "we looked and no source
    arrived second" — the naive attribution D-022/D-023 record as having nearly cost
    job-apps a working adapter. It becomes measurable when an aggregator posting can be
    dereferenced to exact requisition evidence.
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
    """Per-board outcomes, as five independent sweeps merged on company id.

    Separate sweeps rather than one joined query because `artifacts` and `applications` are both
    many-per-posting in principle: folding them into a single GROUP BY would fan out and
    multiply the open-posting denominator by rows that have nothing to do with it.

    **`sum(per_source) == funnel total` is NOT generally a falsifiable check, and this docstring
    used to claim it was.** Every sweep here groups by `postings.company_id` — a NOT NULL column
    behind an enforced foreign key. `companies` is joined nowhere in the counting; it is read
    once, at the end, for display labels. So grouping by board cannot lose or duplicate a
    posting, and a per-board total compared against the same set the funnel already counted
    agrees for every possible database state. A per-board `eligible` total was shipped on that
    reasoning and deleted for it (D-028); do not reinstate it, or an `open_postings` equivalent,
    on the belief that the board grouping makes it independent.

    Only `leads` is worth comparing, and only because its two sides are shaped differently: a
    row count of artifacts against a distinct-posting count resolved through `posting_versions`.
    """
    open_by_company: dict[int, int] = {
        int(row[0]): int(row[1])
        for row in conn.execute(
            select(postings.c.company_id, func.count())
            .where(postings.c.status == "open")
            .group_by(postings.c.company_id)
        ).all()
    }

    eligible_by_company: dict[int, int] = {}
    if identity is not None:
        profile_hash, rules_hash = identity
        judged = _current_identity_evaluations(
            profile_hash=profile_hash,
            rules_hash=rules_hash,
            engine_kind=engine_kind,
            engine_version=engine_version,
        ).subquery()
        eligible_by_company = {
            int(row[0]): int(row[1])
            for row in conn.execute(
                select(postings.c.company_id, func.count())
                .select_from(judged)
                .join(postings, postings.c.id == judged.c.posting_id)
                .where(judged.c.verdict == "eligible")
                .group_by(postings.c.company_id)
            ).all()
        }

    # artifacts carries no posting_id — only posting_version_id — so the board a lead came
    # from is reachable only through its version. An artifact whose posting_version_id is NULL
    # is attributable to no board and is what the leads reconciliation exists to surface.
    leads_by_company: dict[int, int] = {
        int(row[0]): int(row[1])
        for row in conn.execute(
            select(postings.c.company_id, func.count(func.distinct(postings.c.id)))
            .select_from(artifacts)
            .join(posting_versions, posting_versions.c.id == artifacts.c.posting_version_id)
            .join(postings, postings.c.id == posting_versions.c.posting_id)
            .where(artifacts.c.run_id == run_id, artifacts.c.kind == TAILORED_KIND)
            .group_by(postings.c.company_id)
        ).all()
    }

    applied_by_company: dict[int, int] = {}
    if posting_ids:
        # Same scoping and status filter as count_applied_for_postings, so the two agree by
        # construction on which rows count as a submission.
        applied_by_company = {
            int(row[0]): int(row[1])
            for row in conn.execute(
                select(postings.c.company_id, func.count(func.distinct(applications.c.job_id)))
                .select_from(postings)
                .join(applications, applications.c.job_id == postings.c.job_id)
                .where(
                    postings.c.id.in_(posting_ids),
                    applications.c.status.in_(APPLIED_STATUSES),
                )
                .group_by(postings.c.company_id)
            ).all()
        }

    # Fifth sweep: survivor attribution (design §6.1). Gated on completeness, not on
    # existence: a number computed over a partial backfill is not a measurement, and
    # `if identities:` cannot tell the two apart. A version bump empties the current-version
    # rows, closes this gate, and degrades `unique` to None — which is the honest report.
    unique_by_company: dict[int, int] = {}
    complete = identities_complete(conn)
    if complete:
        identity_rows = load_identity_inputs(conn)
        # No id list: at corpus scale it would exceed SQLite's bound-parameter cap and take
        # the funnel artifact down with it. See load_identities.
        identities = load_identities(conn)
        suppressed = {s.posting_id for s in resolve_duplicates(identity_rows, identities)}
        for row in identity_rows:
            if row.posting_id not in suppressed:
                unique_by_company[row.company_id] = unique_by_company.get(row.company_id, 0) + 1

    # A board with no open postings can still own a lead, if its posting closed mid-run. Keyed
    # off the union rather than off open_postings alone so a lead can never vanish from the
    # table — a missing lead reads as a smaller funnel, the one thing this artifact must not do.
    company_ids = (
        set(open_by_company)
        | set(eligible_by_company)
        | set(leads_by_company)
        | set(applied_by_company)
    )
    # A board whose every posting was suppressed still appears, with unique=0.
    company_ids |= set(unique_by_company)
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
            # Defensive only. `postings.company_id` is NOT NULL behind an enforced foreign
            # key, so a missing company row is unreachable — this is not a check, and an
            # earlier comment here wrongly claimed the kept-and-labelled row is what makes a
            # reconciliation catch it. Keeping it would in fact hide it, since its count is
            # still summed (D-028).
            provider=meta.get(company_id, ("unknown", "unknown", "unknown"))[0],
            board_slug=meta.get(company_id, ("unknown", "unknown", "unknown"))[1],
            company_source=meta.get(company_id, ("unknown", "unknown", "unknown"))[2],
            open_postings=int(open_by_company.get(company_id, 0)),
            eligible=int(eligible_by_company.get(company_id, 0)),
            leads=int(leads_by_company.get(company_id, 0)),
            applied=int(applied_by_company.get(company_id, 0)),
            unique=unique_by_company.get(company_id, 0) if complete else None,
            # `assisted` stays not-instrumented: no suppressing kind in this slice can cross
            # a source boundary, so 0 would be a structural zero dressed as a measurement.
            # See the SourceOutcome docstring and design §6.2 before changing this.
            assisted=None,
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
