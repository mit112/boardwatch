"""The funnel's `projection` stage (P5a task 9) — its own balanced stage, never counters bolted
onto `tailor`.

Why a stage. The funnel is a closed, balanced stage model: `tailor` already balances
`shortlisted = tailored + tailor_failed + withheld_not_live`. A lead lost to projection is in none
of those three buckets, so before this change a `--project` run with one per-lead drop reported
`reconciles: no` — Gate P0's headline claim — and the only alternative on offer was folding the
drop into `tailor_failed`, which names the wrong stage and destroys the new catalog's meaning.

Three properties here are load-bearing, and each is a distinction that would disappear silently if
the implementation drifted:

  * **An outcome no lead reached is ABSENT, not a drop of 0.** `projection_outcomes` is a
    `Counter`, so indexing it yields 0 for a member nothing reached; a stage built by walking
    `ProjectionLeadOutcome` and indexing would emit a row of zeros and no arithmetic would notice.
    Same rule as D-023's `not instrumented` versus 0.
  * **No stage at all when `--project` was not passed.** A `projection` stage reading 0 in / 0 out
    claims projection ran and dropped nothing. The decision is made from the run's own verdict
    (`projection_availability is None`), never from the counter being empty — a projected run
    legitimately counts nothing, and a stray counter entry must not be able to conjure the stage.
  * **Every shortlisted lead is counted in exactly one stage.** The runner partitions the cohort
    into four terminal states (lead, tailor failure, withheld as gone, projection failure), and the
    two stages' balances have to be those same four terms — which is why the `withheld_not_live`
    bucket MOVES to the projection stage rather than being left where it would be subtracted twice.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert

from boardwatch.eligibility.catalog import RulesCatalog, load_rules
from boardwatch.projection.run import ProjectionLeadOutcome
from boardwatch.reports.abstain import build_abstain_report
from boardwatch.reports.run_funnel import (
    ARTIFACT_VERSION,
    CrossCheck,
    Lead,
    LivenessCheck,
    RunFunnel,
    RunManifest,
    ScanContext,
    ShortlistCounts,
    Stage,
    build_projection_counters,
    build_run_funnel,
    funnel_to_dict,
    funnel_to_markdown,
)
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import insert_run
from boardwatch.store.run_funnel_queries import (
    CorpusCounts,
    SourceOutcome,
    TailoredArtifactCounts,
    count_projected_tailored_artifacts,
)
from boardwatch.store.tables import artifacts

BUNDLED = Path("does-not-exist")  # no override dir: load_rules falls back to the bundled catalog

# Naive UTC, matching boardwatch.core.clock.utcnow() (A2).
NOW = datetime(2026, 8, 17, 9, 0, 0)


def catalog() -> RulesCatalog:
    return load_rules(BUNDLED)


def lead(posting_id: int) -> Lead:
    return Lead(
        posting_id=posting_id,
        title="Backend Engineer",
        company="Stripe",
        provider="greenhouse",
        board_slug="stripe",
        company_source="registry",
        out_dir=f"/tmp/apps/2026-08-17/stripe-{posting_id}",
        pdf_built=True,
    )


def funnel(
    *,
    # None derives the one value that makes every stage BALANCE, so a test not aimed at a balance
    # cannot trip one by arithmetic it did not intend. Pass it to break a balance deliberately.
    shortlisted: int | None = None,
    leads: int = 2,
    tailor_failed: int = 0,
    dead: int | None = None,
    outcomes: Mapping[ProjectionLeadOutcome, int] | None = None,
    # False models a run where `--project` was never passed: there is no verdict to report.
    projection_ran: bool = True,
    # False models a run where the ranker never executed — which is every preflight refusal, since
    # the projection preflight returns before `rank_open_postings`.
    ranker_ran: bool = True,
    # None means "the store agrees with the pipeline", the healthy case; an int forces a
    # disagreement so the cross-check can be shown to be able to fail.
    lineage_rows: int | None = None,
) -> RunFunnel:
    """A funnel whose every OTHER stage and check balances, so the only thing a test can trip is
    the one it is about. The derived `shortlisted` is the runner's own partition — a lead, a tailor
    failure, a lead withheld as gone, or a projection failure — which makes it larger than `leads`
    whenever a test asks for a drop, so a tailor stage still entering at `shortlisted` is visible.
    """
    lead_objects = [lead(700 + i) for i in range(leads)]
    if shortlisted is None:
        shortlisted = (
            leads
            + tailor_failed
            + (dead or 0)
            + sum(
                count
                for outcome, count in (outcomes or {}).items()
                if outcome is not ProjectionLeadOutcome.PROJECTED
            )
        )
    counts = CorpusCounts(
        open_postings=100,
        evaluated=100,
        no_current_evaluation=0,
        by_verdict={"eligible": 100},
        judged_this_run=100,
        cache_hit_prior_run=0,
        cache_hit_unattributed=0,
    )
    tailored_artifacts = TailoredArtifactCounts(rows=len(lead_objects), with_pdf=len(lead_objects))
    return build_run_funnel(
        run_id=42,
        started_at=None,
        finished_at=None,
        manifest=RunManifest(
            code_fingerprint="engine-1+abc123def456",
            config_hash="c0ffee",
            profile_facts_hash="pf00",
            profile_row_hash="pr00",
            rules_hash="ru1e5",
            status="ok",
        ),
        scan=ScanContext(ran=True),
        corpus=counts,
        shortlist=(
            ShortlistCounts(considered=shortlisted, shortlisted=shortlisted)
            if ranker_ran
            else None
        ),
        liveness=(
            None if dead is None else LivenessCheck(checked=shortlisted, dead=dead, unknown=0)
        ),
        leads=lead_objects,
        tailor_failed=tailor_failed,
        projection=(
            build_projection_counters(outcomes or Counter()) if projection_ran else None
        ),
        projected_lineage_rows=len(lead_objects) if lineage_rows is None else lineage_rows,
        tailored_artifacts=tailored_artifacts,
        sources=[
            SourceOutcome(
                provider="greenhouse",
                board_slug="stripe",
                company_source="registry",
                open_postings=counts.open_postings,
                eligible=100,
                leads=tailored_artifacts.rows,
                applied=0,
            )
        ],
        marked_applied=0,
        stub_postings=0,
        rewrite_rows=[],
        unattributed_evaluations=0,
        abstain=build_abstain_report(catalog(), {}),
    )


def stage_named(report: RunFunnel, name: str) -> Stage | None:
    """None when the stage is ABSENT — which is a different report from a stage of zeros."""
    return next((item for item in report.stages if item.name == name), None)


def named(report: RunFunnel, name: str) -> Stage:
    found = stage_named(report, name)
    assert found is not None, f"no stage named {name!r}"
    return found


def check_named(report: RunFunnel, name: str) -> CrossCheck | None:
    return next((item for item in report.cross_checks if item.name == name), None)


def drops(stage: Stage) -> dict[str, int]:
    return {drop.reason: drop.count for drop in stage.drops}


# The four leads of the default funnel: 2 tailored, 1 withheld as gone, 1 projection failure.
FOUR_TERMINAL_STATES: Counter[ProjectionLeadOutcome] = Counter(
    {ProjectionLeadOutcome.PROJECTED: 2, ProjectionLeadOutcome.CANDIDATE_UNRENDERABLE: 1}
)


# --------------------------------------------------------------------------------------
# The balance
# --------------------------------------------------------------------------------------


def test_the_projection_stage_balances() -> None:
    """`entered = advanced + every drop`, with the drops counted per lead rather than left as a
    remainder. Without its own stage a projection drop either breaks the tailor stage's identity
    (`shortlisted = tailored + tailor_failed + withheld_not_live`) or hides inside `tailor_failed`.
    """
    report = funnel(dead=1, outcomes=FOUR_TERMINAL_STATES)
    stage = named(report, "projection")

    assert stage.entered == 4
    assert stage.advanced == 2
    assert drops(stage) == {"withheld_not_live": 1, "candidate_unrenderable": 1}
    assert stage.entered == stage.advanced + sum(drop.count for drop in stage.drops)
    assert stage.reconciled is True


def test_the_projection_stage_is_not_derived() -> None:
    """No bucket here is the remainder of the others — each is incremented where the lead actually
    leaves — so the balance is evidence and the artifact must not label it bookkeeping."""
    stage = named(funnel(dead=1, outcomes=FOUR_TERMINAL_STATES), "projection")
    assert stage.derived is False
    assert "projection" in [s.name for s in funnel(outcomes=FOUR_TERMINAL_STATES).stages]


def test_the_projection_stage_can_actually_fail_its_balance() -> None:
    """Non-vacuity for the test above: a drop the pipeline did not count leaves the stage
    unreconciled rather than being absorbed. This is the failure a `derived` stage cannot have."""
    report = funnel(shortlisted=4, dead=0, outcomes=Counter({ProjectionLeadOutcome.PROJECTED: 2}))
    stage = named(report, "projection")

    assert stage.entered == 4
    assert stage.reconciled is False
    assert stage in report.unreconciled
    assert report.reconciles is False


def test_the_tailor_stage_now_enters_at_projected() -> None:
    report = funnel(dead=1, outcomes=FOUR_TERMINAL_STATES)

    assert named(report, "tailor").entered == named(report, "projection").advanced
    # The part that could regress: it is no longer the ranker's shortlist.
    assert named(report, "tailor").entered == 2
    assert named(report, "shortlist").advanced == 4


def test_the_tailor_stage_no_longer_carries_the_withheld_bucket() -> None:
    """It moves to the projection stage rather than being counted in both: subtracting the withheld
    leads twice would report a healthy run as unbalanced."""
    report = funnel(dead=1, outcomes=FOUR_TERMINAL_STATES)

    assert drops(named(report, "tailor")) == {"tailor_failed": 0}
    assert "withheld_not_live" in drops(named(report, "projection"))
    assert named(report, "tailor").reconciled is True


def test_every_shortlisted_lead_is_counted_in_exactly_one_stage() -> None:
    """The runner's four terminal states — lead, tailor failure, withheld as gone, projection
    failure — and nothing counted twice or in none. `_cohort_guard` reconciles the same partition
    by ID set, so a lead the funnel loses is a lead that guard would have called unaccounted.
    """
    report = funnel(
        shortlisted=5,
        leads=2,
        tailor_failed=1,
        dead=1,
        outcomes=Counter(
            {
                ProjectionLeadOutcome.PROJECTED: 3,
                ProjectionLeadOutcome.LINEAGE_MISMATCH: 1,
            }
        ),
    )
    projection = named(report, "projection")
    tailor = named(report, "tailor")

    # projection: 5 = 3 + (1 withheld + 1 lineage_mismatch) · tailor: 3 = 2 + 1
    assert projection.reconciled is True
    assert tailor.reconciled is True
    counted = len(report.leads) + sum(
        drop.count for stage in (projection, tailor) for drop in stage.drops
    )
    assert counted == named(report, "shortlist").advanced == 5
    reasons = [drop.reason for stage in (projection, tailor) for drop in stage.drops]
    assert len(reasons) == len(set(reasons)), reasons


def test_a_projected_run_that_lost_a_lead_still_reconciles() -> None:
    """The regression this task exists to fix: before the stage existed, a `--project` run with one
    per-lead drop reported `reconciles: no`, because the lost lead was in neither of the tailor
    stage's two buckets. Gate P0's headline claim, not cosmetics."""
    report = funnel(dead=0, outcomes=FOUR_TERMINAL_STATES)

    assert report.unreconciled == ()
    assert report.disagreements == ()
    assert report.reconciles is True
    assert funnel_to_dict(report)["reconciles"] is True
    assert "DOES NOT RECONCILE" not in funnel_to_markdown(report)


# --------------------------------------------------------------------------------------
# Absent, not zero
# --------------------------------------------------------------------------------------


def test_an_outcome_no_lead_reached_is_absent_not_a_drop_of_zero() -> None:
    """`projection_outcomes` is a `Counter`: `outcomes[SOME_OUTCOME]` is 0 for a member nothing
    reached. An implementation that walked `ProjectionLeadOutcome` and indexed it would emit five
    drops here — four of them zeros claiming a bucket was checked and found empty — and every
    balance would still hold."""
    stage = named(funnel(dead=1, outcomes=FOUR_TERMINAL_STATES), "projection")

    catalog_reasons = {outcome.value for outcome in ProjectionLeadOutcome}
    named_here = {drop.reason for drop in stage.drops} & catalog_reasons
    assert named_here == {ProjectionLeadOutcome.CANDIDATE_UNRENDERABLE.value}
    assert all(
        drop.count > 0 for drop in stage.drops if drop.reason in catalog_reasons
    ), drops(stage)


def test_a_clean_projected_run_names_no_outcome_at_all() -> None:
    """Every lead projected: the stage carries the withheld bucket and NOTHING else, rather than
    five zero rows for the five ways a lead can fail to be projected."""
    stage = named(funnel(dead=0, leads=4, outcomes=Counter({
        ProjectionLeadOutcome.PROJECTED: 4
    })), "projection")

    assert drops(stage) == {"withheld_not_live": 0}
    assert stage.advanced == 4


def test_build_projection_counters_iterates_rather_than_indexing() -> None:
    """The fold is handed a plain `Mapping`, not a `Counter`, on purpose: an implementation that
    indexed a member it had not been given would raise `KeyError` here instead of silently
    reading 0. `PROJECTED` absent means 0 advanced, which is a different claim from a bucket
    of zeros for outcomes nobody reached."""
    counters = build_projection_counters({ProjectionLeadOutcome.OUTPUT_IO_FAILURE: 2})

    assert counters.projected == 0
    assert [drop.reason for drop in counters.drops] == ["output_io_failure"]


def test_the_drops_are_ordered_so_two_runs_render_the_same_artifact() -> None:
    """A `Counter` iterates in first-increment order — whichever lead failed first. Two runs with
    the same outcomes must not produce artifacts that diff."""
    first = build_projection_counters(
        Counter(
            {
                ProjectionLeadOutcome.OUTPUT_IO_FAILURE: 1,
                ProjectionLeadOutcome.EXTRACTION_UNAVAILABLE: 1,
            }
        )
    )
    second = build_projection_counters(
        Counter(
            {
                ProjectionLeadOutcome.EXTRACTION_UNAVAILABLE: 1,
                ProjectionLeadOutcome.OUTPUT_IO_FAILURE: 1,
            }
        )
    )
    assert first.drops == second.drops


# --------------------------------------------------------------------------------------
# Absent stage, not a stage of zeros
# --------------------------------------------------------------------------------------


def test_the_stage_is_absent_without_the_flag() -> None:
    """Absent, not zeroed. A stage reporting 0 in / 0 out claims projection ran and dropped
    nothing; D-023 set this precedent with `not instrumented` versus 0."""
    report = funnel(dead=1, projection_ran=False)

    assert stage_named(report, "projection") is None
    assert "projection" not in [item.name for item in report.stages]
    assert not any(
        stage["name"] == "projection" for stage in funnel_to_dict(report)["stages"]  # type: ignore[union-attr]
    )


def test_the_authored_run_is_untouched() -> None:
    """No `--project`, so the tailor stage still enters at the shortlist and still carries the
    withheld bucket, and there is no lineage cross-check to disagree."""
    report = funnel(dead=1, projection_ran=False)

    assert named(report, "tailor").entered == named(report, "shortlist").advanced == 3
    assert drops(named(report, "tailor")) == {"tailor_failed": 0, "withheld_not_live": 1}
    assert named(report, "tailor").reconciled is True
    assert check_named(report, "projected_leads") is None


def test_a_stray_counter_entry_cannot_conjure_the_stage() -> None:
    """A stray counter entry does not reach the BUILDER's omit decision, which is `projection is
    None` and nothing else. `_retract_projected` called against a counter with no `PROJECTED` key
    would leave `PROJECTED: -1` — unreachable today only because `ResumeLineageMismatch` has one
    raise site gated on a lineage being present, which is a behavioural accident rather than a
    structural guarantee.

    Scope note, because this helper folds the counter itself: the run-level decision — verdict, not
    counter emptiness — is made one layer up in `funnel_writer.collect_run_funnel`, so this test
    cannot see a drift there. `tests/pipeline/test_run_funnel_projection_stage.py::
    test_a_refused_projected_run_still_carries_an_UNMEASURED_stage` is the one that can, and it
    goes red if that condition ever starts consulting the counter.
    """
    report = funnel(
        projection_ran=False, outcomes=Counter({ProjectionLeadOutcome.PROJECTED: -1})
    )

    assert stage_named(report, "projection") is None


def test_an_empty_counter_on_a_projected_run_still_gets_its_stage() -> None:
    """The converse, and the reason the decision cannot be the counter: a projected run that
    withheld every shortlisted lead as gone counted no outcome at all, and still has a verdict to
    report."""
    report = funnel(shortlisted=2, leads=0, dead=2, outcomes=Counter())
    stage = named(report, "projection")

    assert stage.entered == 2
    assert stage.advanced == 0
    assert drops(stage) == {"withheld_not_live": 2}
    assert stage.reconciled is True


def test_the_stage_is_not_instrumented_when_the_ranker_never_ran() -> None:
    """Every preflight refusal is this run: `--project` was passed, the preflight refused, and the
    pipeline returned BEFORE `rank_open_postings`. How many leads projection would have attempted
    is unknown, so it is reported as unmeasured — not as zero, and not as a broken balance."""
    report = funnel(ranker_ran=False, leads=0, outcomes=Counter())
    stage = named(report, "projection")

    assert stage.entered is None
    assert stage.advanced is None
    assert stage.instrumented is False
    assert stage.reconciled is None
    assert stage not in report.unreconciled
    assert named(report, "tailor").entered is None
    assert "NOT INSTRUMENTED" in stage.note


# --------------------------------------------------------------------------------------
# The independent recount
# --------------------------------------------------------------------------------------


def test_the_projected_leads_are_recounted_from_the_store() -> None:
    """A component's self-report is not verification. The pipeline's lead objects are compared
    against `resume_tailored` rows carrying projection lineage — a different path from the counter
    the loop incremented, and one the plain `tailored` row count cannot substitute for."""
    report = funnel(dead=1, outcomes=FOUR_TERMINAL_STATES)
    check = check_named(report, "projected_leads")

    assert check is not None
    assert check.in_memory == len(report.leads) == 2
    assert check.from_store == 2
    assert check.agrees


def test_a_lead_rendered_without_lineage_is_a_failure() -> None:
    """The failure mode the existing `tailored` cross-check is blind to: the row is there, so the
    row count still agrees, but it carries no projection lineage."""
    report = funnel(dead=1, outcomes=FOUR_TERMINAL_STATES, lineage_rows=1)
    check = check_named(report, "projected_leads")

    assert check is not None and not check.agrees
    assert check in report.disagreements
    assert report.reconciles is False
    # The other recount, over the same rows, still agrees — which is why this one had to exist.
    assert check_named(report, "tailored") is not None
    assert check_named(report, "tailored").agrees  # type: ignore[union-attr]


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path)
    ensure_schema(eng)
    return eng


def test_the_store_recount_counts_only_lineage_bearing_rows(engine: Engine) -> None:
    """The query behind that cross-check, against a real store: this run's tailored rows whose meta
    carries the projection lineage, and nothing else. An authored lead and another run's projected
    lead are both excluded."""
    run_id = insert_run(engine)
    other_run = insert_run(engine)
    rows = [
        ("resume_tailored", run_id, {"projection_kind": "projection", "degraded": False}),
        ("resume_tailored", run_id, {"projection_kind": "projection"}),
        ("resume_tailored", run_id, {"degraded": False}),  # authored: no lineage
        ("resume_tailored", other_run, {"projection_kind": "projection"}),
        ("resume_tailored_llm", run_id, {"projection_kind": "projection"}),  # Tier B, not a lead
    ]
    with engine.begin() as conn:
        for index, (kind, owner, meta) in enumerate(rows):
            conn.execute(
                insert(artifacts).values(
                    kind=kind,
                    uri=f"/tmp/apps/tailored-{index}.tex",
                    meta_json=meta,
                    created_at=NOW,
                    run_id=owner,
                )
            )

    with engine.connect() as conn:
        assert count_projected_tailored_artifacts(conn, run_id) == 2
        assert count_projected_tailored_artifacts(conn, other_run) == 1


# --------------------------------------------------------------------------------------
# The artifact
# --------------------------------------------------------------------------------------


def test_the_artifact_version_is_bumped() -> None:
    """A new stage is a new section, and more than that: on a projected run `tailor.entered` stops
    meaning `shortlisted`. Every bump so far signalled a new top-level section, and D-113 is the
    precedent for DECLINING one on a merely additive key — this is not one."""
    assert ARTIFACT_VERSION == 5
    assert funnel_to_dict(funnel(outcomes=FOUR_TERMINAL_STATES))["artifact_version"] == 5


def test_the_stage_sits_between_shortlist_and_tailor() -> None:
    names = [stage["name"] for stage in funnel_to_dict(  # type: ignore[index]
        funnel(outcomes=FOUR_TERMINAL_STATES)
    )["stages"]]  # type: ignore[union-attr]
    assert names.index("shortlist") + 1 == names.index("projection")
    assert names.index("projection") + 1 == names.index("tailor")


def test_the_markdown_names_every_projection_drop() -> None:
    """Gate P0: why every non-lead was dropped, answerable from the artifact alone. A stage whose
    numbers are right but whose Markdown omits a drop fails the gate just the same."""
    text = funnel_to_markdown(funnel(dead=1, outcomes=FOUR_TERMINAL_STATES))

    assert "### projection — 4 in, 2 out" in text
    assert "**candidate_unrenderable**: 1" in text
    assert "**withheld_not_live**: 1" in text
    # Named among the stages whose balance could actually have failed, not as bookkeeping.
    assert "shortlist, projection, tailor" in text
    assert "| projection | 4 | 2 | 2 | **yes** |" in text
    # An outcome nothing reached appears nowhere, in either half of the artifact.
    assert ProjectionLeadOutcome.OUTPUT_IO_FAILURE.value not in text
