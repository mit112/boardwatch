"""The per-run funnel artifact (P0 item 1) — the pure half.

Gate P0 asks that *which source produced each lead and why every non-lead was dropped* be
answerable **from the artifact alone, without reading code**. Most of these tests are
therefore assertions about what the rendered artifact SAYS, not about internal state: a
funnel whose numbers are right but whose Markdown omits a drop reason fails the gate just as
surely as a funnel that does not add up.

The rest guard the three collapses that would each destroy a signal this program exists to
preserve — not-instrumented folded into 0, `cache_hit_unattributed` folded into
`cache_hit_prior_run`, and `uncertain` folded into `ineligible`.
"""

from __future__ import annotations

import json
from pathlib import Path

from boardwatch.eligibility.catalog import RulesCatalog, load_rules
from boardwatch.reports.abstain import AbstainReport, build_abstain_report
from boardwatch.reports.run_funnel import (
    Lead,
    RunFunnel,
    ScanContext,
    build_run_funnel,
    funnel_to_dict,
    funnel_to_markdown,
    write_run_funnel,
)
from boardwatch.store.run_funnel_queries import CorpusCounts, TailoredArtifactCounts

BUNDLED = Path("does-not-exist")  # no override dir: load_rules falls back to the bundled catalog


def catalog() -> RulesCatalog:
    return load_rules(BUNDLED)


def corpus(
    *,
    open_postings: int = 100,
    evaluated: int = 90,
    no_current_evaluation: int = 10,
    eligible: int = 40,
    ineligible: int = 20,
    uncertain: int = 30,
    extra_verdicts: dict[str, int] | None = None,
    judged_this_run: int = 50,
    cache_hit_prior_run: int = 30,
    cache_hit_unattributed: int = 10,
) -> CorpusCounts:
    verdicts = {"eligible": eligible, "ineligible": ineligible, "uncertain": uncertain}
    verdicts.update(extra_verdicts or {})
    return CorpusCounts(
        open_postings=open_postings,
        evaluated=evaluated,
        no_current_evaluation=no_current_evaluation,
        by_verdict=verdicts,
        judged_this_run=judged_this_run,
        cache_hit_prior_run=cache_hit_prior_run,
        cache_hit_unattributed=cache_hit_unattributed,
    )


def lead(posting_id: int = 7, *, pdf_built: bool = True, slug: str = "stripe") -> Lead:
    return Lead(
        posting_id=posting_id,
        title="Backend Engineer",
        company="Stripe",
        provider="greenhouse",
        board_slug=slug,
        company_source="registry",
        out_dir=f"/tmp/apps/2026-08-06/stripe-{posting_id}",
        pdf_built=pdf_built,
    )


def funnel(
    *,
    counts: CorpusCounts | None = None,
    leads: list[Lead] | None = None,
    shortlisted: int | None = None,
    hidden_ineligible: int = 5,
    hidden_non_swe: int = 8,
    tailor_failed: int = 0,
    artifacts: TailoredArtifactCounts | None = None,
    marked_applied: int = 0,
    abstain: AbstainReport | None = None,
    unattributed_evaluations: int = 20_637,
) -> RunFunnel:
    leads = [lead()] if leads is None else leads
    # Default to a CONSISTENT tailor stage. Every shortlisted posting either produced a lead
    # or failed, so a caller that is not testing the tailor stage gets a funnel whose only
    # imbalance is the one that test introduced deliberately.
    if shortlisted is None:
        shortlisted = len(leads) + tailor_failed
    return build_run_funnel(
        run_id=42,
        started_at=None,
        finished_at=None,
        scan=ScanContext(ran=True, boards_attempted=85, boards_complete=80, boards_failed=5,
                         postings_seen=13_590),
        corpus=counts or corpus(),
        shortlisted=shortlisted,
        hidden_ineligible=hidden_ineligible,
        hidden_non_swe=hidden_non_swe,
        leads=leads,
        tailor_failed=tailor_failed,
        tailored_artifacts=artifacts
        or TailoredArtifactCounts(
            rows=len(leads), with_pdf=sum(1 for item in leads if item.pdf_built)
        ),
        marked_applied=marked_applied,
        unattributed_evaluations=unattributed_evaluations,
        abstain=abstain or build_abstain_report(catalog(), {}),
    )


def rule_id_prefix(line: str, ids: list[str]) -> bool:
    """True when this Markdown table row is one of the catalog's rule rows."""
    return line.split("|")[1].strip() in ids


def stage(report: RunFunnel, name: str):
    return next(item for item in report.stages if item.name == name)


def drops(report: RunFunnel, name: str) -> dict[str, int]:
    return {drop.reason: drop.count for drop in stage(report, name).drops}


# --------------------------------------------------------------------------------------
# The three collapses
# --------------------------------------------------------------------------------------


def test_an_uninstrumented_stage_reports_none_and_does_not_claim_to_reconcile() -> None:
    """Dedup has never run, so its stage reports None — and crucially `reconciled` is None
    too, NOT True.

    Both halves matter and they fail differently. Reporting 0 would claim boardwatch
    measured dedup and found no duplicates, which is the opposite of the truth. Reporting
    `reconciled is True` would let an unmeasured stage count towards Gate P0's "reconciles
    to 100%", so the gate could be passed by stages that were never instrumented at all.
    """
    dedup = stage(funnel(), "dedup")

    assert dedup.entered is None
    assert dedup.advanced is None
    assert dedup.instrumented is False
    assert dedup.reconciled is None, "an unmeasured stage must not report as reconciled"

    # And it is excluded from the gate's population rather than silently passing it.
    assert dedup not in funnel().instrumented_stages


def test_unattributed_cache_hits_are_never_folded_into_the_prior_run_bucket() -> None:
    """D-019: a NULL run_id means exactly one thing — the row predates attribution.

    The attribution stage must carry `cache_hit_prior_run` and `cache_hit_unattributed` as
    two separate drops with their own counts. Summing them into one "cache hit" bucket would
    erase the only evidence that the unattributable population is not growing.
    """
    report = funnel(counts=corpus(cache_hit_prior_run=30, cache_hit_unattributed=10))
    attribution = drops(report, "attribution")

    assert attribution["cache_hit_prior_run"] == 30
    assert attribution["cache_hit_unattributed"] == 10
    # Named separately in the rendered artifact too, or the gate's "without reading code"
    # clause is not met for the one bucket D-019 is about.
    body = funnel_to_markdown(report)
    assert "cache_hit_prior_run" in body
    assert "cache_hit_unattributed" in body


def test_abstained_is_reported_apart_from_ineligible() -> None:
    """`ABSTAIN` is never folded into either neighbour, in any report, ever (CLAUDE.md).

    The store has no `abstain` verdict — the keystone invariant's ABSTAIN persists as
    `uncertain` — so the artifact renames it and must not let it land in `ineligible`.
    """
    report = funnel(counts=corpus(eligible=40, ineligible=20, uncertain=30))
    verdict = drops(report, "verdict")

    assert verdict["abstained"] == 30
    assert verdict["ineligible"] == 20
    assert stage(report, "verdict").advanced == 40


# --------------------------------------------------------------------------------------
# Reconciliation must be capable of failing
# --------------------------------------------------------------------------------------


def test_a_stage_whose_counts_do_not_add_up_fails_reconciliation() -> None:
    """The reconciliation is a real assertion, not a formatting exercise.

    A funnel whose corpus does not partition — 100 open postings, 90 evaluated, 5 with no
    evaluation — must report `reconciles is False` and name `corpus` as the offender. If this
    test can never fail, nothing in Gate P0's "reconciles to 100%" has any teeth.
    """
    report = funnel(counts=corpus(open_postings=100, evaluated=90, no_current_evaluation=5))

    assert stage(report, "corpus").reconciled is False
    assert [item.name for item in report.unreconciled] == ["corpus"]
    assert report.reconciles is False
    assert "DOES NOT RECONCILE" in funnel_to_markdown(report)


def test_a_balanced_funnel_reconciles() -> None:
    """The companion to the test above: the same shape, made consistent, must pass.

    Without this, the failing test would be satisfied by a `reconciles` that is always False.
    """
    report = funnel(
        counts=corpus(
            open_postings=100, evaluated=90, no_current_evaluation=10,
            eligible=40, ineligible=20, uncertain=30,
            judged_this_run=50, cache_hit_prior_run=30, cache_hit_unattributed=10,
        )
    )

    assert report.unreconciled == ()
    assert report.reconciles is True
    assert "RECONCILES" in funnel_to_markdown(report)


def test_the_store_disagreeing_with_the_pipeline_fails_reconciliation() -> None:
    """A component's self-report is not verification (CLAUDE.md).

    Every stage here balances; only the independent recount disagrees — the pipeline believes
    it tailored one lead, the artifacts table has two rows for the run. `reconciles` must be
    False on that alone, or the cross-check is decoration and the artifact is a self-report
    wearing a tick.
    """
    report = funnel(
        leads=[lead(7)],
        artifacts=TailoredArtifactCounts(rows=2, with_pdf=1),
    )

    assert report.unreconciled == (), "the stages balance; only the recount disagrees"
    assert [check.name for check in report.disagreements] == ["tailored"]
    assert report.reconciles is False


def test_a_pdf_that_never_compiled_is_caught_by_the_recount() -> None:
    """D-006's silent degrade, as a cross-check.

    `artifacts.uri` holds the `.typ` path whether or not a PDF was ever produced, so a row
    count cannot tell a delivered lead from a degraded one. When the pipeline claims a PDF
    and `meta_json.typst_pdf_built` does not agree, the artifact must say so.
    """
    report = funnel(
        leads=[lead(7, pdf_built=True)],
        artifacts=TailoredArtifactCounts(rows=1, with_pdf=0),
    )

    assert [check.name for check in report.disagreements] == ["leads_with_pdf"]
    assert report.reconciles is False


def test_a_derived_stage_is_labelled_so_its_balance_is_not_read_as_evidence() -> None:
    """`shortlist` balances by construction, because `capped_by_top_n` is the remainder.

    That is bookkeeping, not verification, and the artifact must distinguish it from the
    stages that can actually fail. Otherwise a reader counting green ticks would credit the
    funnel with more evidence than it has.
    """
    report = funnel()

    assert stage(report, "shortlist").derived is True
    assert stage(report, "corpus").derived is False, "the one genuinely falsifiable stage"
    # Partitions of the very set `entered` counts, so their balance holds for every possible
    # input. Labelling them non-derived would present two unfailable ticks as evidence.
    assert stage(report, "attribution").derived is True
    assert stage(report, "verdict").derived is True

    # Scoped to the shortlist TABLE ROW. `"yes (derived)" in body` passes even when every row
    # renders "**yes**", because the legend paragraph below the table contains the phrase.
    body = funnel_to_markdown(report)
    row = next(line for line in body.splitlines() if line.startswith("| shortlist |"))
    assert row.rstrip().endswith("yes (derived) |"), row
    corpus_row = next(line for line in body.splitlines() if line.startswith("| corpus |"))
    assert corpus_row.rstrip().endswith("**yes** |"), corpus_row


def test_a_verdict_outside_the_vocabulary_is_carried_not_discarded() -> None:
    """Widening the verdict CHECK must not silently shrink the verdict stage.

    An unknown verdict lands in `verdict_out_of_vocabulary` and keeps the stage balanced. If
    it were dropped on the floor, the stage would stop reconciling for a reason no drop
    explains — or worse, the denominator would quietly shrink.
    """
    report = funnel(
        counts=corpus(
            evaluated=95, eligible=40, ineligible=20, uncertain=30,
            extra_verdicts={"needs_review": 5},
            judged_this_run=55, cache_hit_prior_run=30, cache_hit_unattributed=10,
        )
    )

    assert drops(report, "verdict")["verdict_out_of_vocabulary"] == 5
    assert stage(report, "verdict").reconciled is True


# --------------------------------------------------------------------------------------
# "From the artifact alone, without reading code"
# --------------------------------------------------------------------------------------


def test_the_markdown_names_the_board_that_produced_each_lead() -> None:
    """Gate P0: *which source produced each lead* — answerable from the artifact alone."""
    body = funnel_to_markdown(funnel(leads=[lead(7, slug="stripe"), lead(9, slug="ramp")]))

    # Scoped to the lead ROWS. A bare `"registry" in body` passes even when the column is
    # replaced by a placeholder, because the table HEADER reads `| registry/user |`.
    rows = [line for line in body.splitlines() if line.startswith("| 7 |") or
            line.startswith("| 9 |")]
    assert len(rows) == 2, body
    assert "greenhouse:stripe" in rows[0]
    assert "greenhouse:ramp" in rows[1]
    assert all("| registry |" in row for row in rows), rows


def test_the_markdown_names_every_drop_reason_with_its_count() -> None:
    """Gate P0: *why every non-lead was dropped* — every bucket named and counted in prose.

    A reader must never have to subtract two numbers to discover why postings left the
    funnel, so each reason appears with its own figure.
    """
    report = funnel(
        counts=corpus(no_current_evaluation=10, ineligible=20, uncertain=30),
        hidden_ineligible=5,
        hidden_non_swe=8,
        tailor_failed=3,
    )
    body = funnel_to_markdown(report)

    # Every reason asserted in its RENDERED form, `- **reason**: N`, never as a bare
    # substring. Three of these are substrings of something else on the page and passed even
    # when their Drop was deleted outright: "ineligible" occurs inside "hidden_ineligible",
    # "abstained" is a column header in the per-rule table, and "capped_by_top_n" appeared in
    # a stage note. A bare `in body` check cannot tell prose from data.
    expected = {
        "no_current_evaluation": 10, "cache_hit_prior_run": 30, "cache_hit_unattributed": 10,
        "ineligible": 20, "abstained": 30, "hidden_ineligible": 5, "hidden_non_swe": 8,
        "tailor_failed": 3, "no_pdf": 0, "not_marked_applied": 1,
    }
    for reason, count in expected.items():
        assert f"- **{reason}**: {count}" in body, (
            f"{reason} is not stated with its count; the reader would have to subtract"
        )


def test_the_markdown_reports_every_catalog_rule_including_those_that_never_fired() -> None:
    """Gate P0 requires per-rule abstain for EVERY rule in the catalog.

    The rules worth knowing about are the ones with no rows at all, and a report built by
    grouping the data cannot show them. Each of the 44 must be named, and a never-fired rule
    must read as `never fired` rather than as 0%.
    """
    cat = catalog()
    body = funnel_to_markdown(funnel(abstain=build_abstain_report(cat, {})))

    ids = [pattern.rule_id for family in cat.families for pattern in family.patterns]
    assert len(ids) == 44
    for rule_id in ids:
        assert rule_id in body, f"{rule_id} absent from the artifact"
    assert "never fired" in body
    # Scoped to the TABLE rows: the surrounding prose explains why 0% is wrong and would
    # otherwise satisfy a naive substring check for the very string it warns against.
    rates = [line.rsplit("|", 2)[-2].strip() for line in body.splitlines()
             if line.startswith("| ") and rule_id_prefix(line, ids)]
    assert rates, "no rule rows were rendered"
    assert set(rates) == {"never fired"}, f"a never-fired rule rendered as a rate: {set(rates)}"


def test_a_rule_that_never_fired_serialises_as_null_rather_than_zero() -> None:
    """The JSON half must preserve the same distinction the Markdown does.

    `null` and `0.0` mean opposite things — 'cannot be measured' versus 'never abstains' —
    and a consumer reading the JSON would rank a dead rule as the healthiest in the catalog.
    """
    cat = catalog()
    fired = next(p.rule_id for f in cat.families for p in f.patterns)
    report = funnel(abstain=build_abstain_report(cat, {(fired, "met"): 3}))

    rules = {r["rule_id"]: r for r in funnel_to_dict(report)["abstain"]["rules"]}  # type: ignore[index]
    assert rules[fired]["abstain_rate"] == 0.0
    others = [r for rid, r in rules.items() if rid != fired]
    assert all(r["abstain_rate"] is None for r in others)
    assert all(r["never_fired"] is True for r in others)


def test_the_unattributable_population_is_reported_as_its_own_number() -> None:
    """D-019's invariant is only checkable if the artifact states the number every run.

    It is never folded into the run's counts and never reported as 0 — a reader compares it
    across runs to confirm no NULL leaked back in.
    """
    report = funnel(unattributed_evaluations=20_637)

    assert funnel_to_dict(report)["unattributed_evaluations"] == 20_637
    assert "20637" in funnel_to_markdown(report)


def test_scan_throughput_is_not_presented_as_a_funnel_edge() -> None:
    """`postings_seen` and the corpus are different populations.

    An unchanged board returns 304 and lists nothing, so postings_seen is routinely far below
    the open corpus. Chaining them would be arithmetic that is wrong on most real runs, so
    scan is reported as context and the funnel's head is the corpus.
    """
    report = funnel(counts=corpus(open_postings=100))

    assert stage(report, "corpus").entered == 100
    assert 13_590 not in [item.entered for item in report.stages]
    assert funnel_to_dict(report)["scan"]["postings_seen"] == 13_590  # type: ignore[index]


# --------------------------------------------------------------------------------------
# Emission
# --------------------------------------------------------------------------------------


def test_both_halves_are_written_and_named_by_run(tmp_path: Path) -> None:
    """Two runs on one day must not overwrite each other's artifact, so the run id is in the
    filename rather than only the date."""
    written = write_run_funnel(funnel(), tmp_path)

    assert written.json_path == tmp_path / "funnel-42.json"
    assert written.markdown_path == tmp_path / "funnel-42.md"
    payload = json.loads(written.json_path.read_text())
    assert payload["run_id"] == 42
    assert payload["artifact_version"] == 1
    assert written.markdown_path.read_text().startswith("# boardwatch run 42")


def test_the_json_keeps_every_drop_rather_than_pre_summing_them(tmp_path: Path) -> None:
    """A machine consumer must be able to reach the same conclusions the prose does.

    If the JSON carried only totals, the per-reason breakdown would exist in the Markdown
    alone and any downstream check of Gate P0 would have to parse prose.
    """
    written = write_run_funnel(funnel(tailor_failed=3), tmp_path)
    payload = json.loads(written.json_path.read_text())

    stages = {item["name"]: item for item in payload["stages"]}
    assert {d["reason"] for d in stages["attribution"]["drops"]} == {
        "cache_hit_prior_run", "cache_hit_unattributed",
    }
    assert stages["dedup"]["entered"] is None
    assert stages["dedup"]["reconciled"] is None
    assert stages["tailor"]["drops"][0] == {
        "reason": "tailor_failed", "count": 3, "note": "",
    }
