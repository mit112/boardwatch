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
    ShortlistCounts,
    build_run_funnel,
    funnel_to_dict,
    funnel_to_markdown,
    write_run_funnel,
)
from boardwatch.store.run_funnel_queries import (
    CorpusCounts,
    SourceOutcome,
    TailoredArtifactCounts,
)

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
    hidden_hard_filter: int = 0,
    hidden_below_cutoff: int = 0,
    skipped_not_new: int = 0,
    considered: int | None = None,
    tailor_failed: int = 0,
    artifacts: TailoredArtifactCounts | None = None,
    marked_applied: int = 0,
    abstain: AbstainReport | None = None,
    unattributed_evaluations: int = 20_637,
    sources: list[SourceOutcome] | None = None,
    # False models a run where the ranker never executed (no profile / fatal scan outage).
    ranker_ran: bool = True,
) -> RunFunnel:
    leads = [lead()] if leads is None else leads
    # Default to a CONSISTENT tailor stage. Every shortlisted posting either produced a lead
    # or failed, so a caller that is not testing the tailor stage gets a funnel whose only
    # imbalance is the one that test introduced deliberately.
    if shortlisted is None:
        shortlisted = len(leads) + tailor_failed
    # Default to a BALANCED shortlist stage for the same reason as the tailor stage above: a
    # caller not testing this stage should not have to know the identity to avoid tripping it.
    if considered is None:
        considered = (
            shortlisted + hidden_ineligible + hidden_non_swe
            + hidden_hard_filter + hidden_below_cutoff + skipped_not_new
        )
    counts = counts or corpus()
    tailored_artifacts = artifacts or TailoredArtifactCounts(
        rows=len(leads), with_pdf=sum(1 for item in leads if item.pdf_built)
    )
    # Default to a per-source table that ACCOUNTS for the whole funnel, for the same reason the
    # tailor and shortlist stages default to balanced: a test not aimed at attribution should
    # not have to restate the totals to avoid tripping it.
    if sources is None:
        sources = [SourceOutcome(
            provider="greenhouse", board_slug="stripe", company_source="registry",
            open_postings=counts.open_postings,
            eligible=counts.by_verdict.get("eligible", 0),
            leads=tailored_artifacts.rows,
            applied=marked_applied,
        )]
    return build_run_funnel(
        run_id=42,
        started_at=None,
        finished_at=None,
        scan=ScanContext(ran=True, boards_attempted=85, boards_complete=80, boards_failed=5,
                         postings_seen=13_590),
        corpus=counts,
        shortlist=ShortlistCounts(
            considered=considered,
            shortlisted=shortlisted,
            hidden_hard_filter=hidden_hard_filter,
            hidden_non_swe=hidden_non_swe,
            hidden_ineligible=hidden_ineligible,
            hidden_below_cutoff=hidden_below_cutoff,
            skipped_not_new=skipped_not_new,
        ) if ranker_ran else None,
        leads=leads,
        tailor_failed=tailor_failed,
        tailored_artifacts=tailored_artifacts,
        sources=sources,
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


def test_a_tracked_lead_that_lost_its_pdf_does_not_break_the_applied_stage() -> None:
    """The applied stage is rooted at `tailored`, not at `leads_with_pdf`.

    `marked_applied` is counted over every tailored posting, so against `with_pdf` it can
    legitimately exceed what entered: a lead whose PDF failed to compile (D-006's silent
    degrade) whose job was already tracked from an earlier day. The clamped remainder would
    then report the stage as broken and drag Gate P0's headline metric down with it.

    Two leads, one with no PDF, both already applied to: rooted at `with_pdf` this is
    `entered=1, advanced=2` and cannot balance; rooted at `tailored` it is bounded, because
    the count is DISTINCT job ids drawn from exactly these postings.
    """
    report = funnel(
        leads=[lead(7, pdf_built=True), lead(9, pdf_built=False)],
        artifacts=TailoredArtifactCounts(rows=2, with_pdf=1),
        marked_applied=2,
    )
    applied = stage(report, "applied")

    assert applied.entered == 2, "the applied stage is rooted at the PDF count again"
    assert applied.advanced == 2
    assert applied.reconciled is True
    assert report.reconciles is True


def test_a_derived_stage_is_labelled_so_its_balance_is_not_read_as_evidence() -> None:
    """`attribution` and `verdict` balance by construction — they are SQL partitions of the
    very set `entered` counts, so their sums equal it for every possible database state.

    That is bookkeeping, not verification, and the artifact must distinguish it from the
    stages that can actually fail. Otherwise a reader counting green ticks would credit the
    funnel with more evidence than it has.
    """
    report = funnel()

    assert stage(report, "corpus").derived is False, "an independent NOT IN sweep"
    # Partitions of the very set `entered` counts, so their balance holds for every possible
    # input. Labelling them non-derived would present two unfailable ticks as evidence.
    assert stage(report, "attribution").derived is True
    assert stage(report, "verdict").derived is True
    # Remainder buckets: one drop is computed from the others.
    assert stage(report, "pdf").derived is True
    assert stage(report, "applied").derived is True

    # Scoped to the verdict TABLE ROW. `"yes (derived)" in body` passes even when every row
    # renders "**yes**", because the legend paragraph below the table contains the phrase.
    body = funnel_to_markdown(report)
    row = next(line for line in body.splitlines() if line.startswith("| verdict |"))
    assert row.rstrip().endswith("yes (derived) |"), row
    corpus_row = next(line for line in body.splitlines() if line.startswith("| corpus |"))
    assert corpus_row.rstrip().endswith("**yes** |"), corpus_row


def test_the_shortlist_stage_is_evidence_because_the_ranker_reports_what_it_considered() -> None:
    """P0 item 3's structural change: `shortlist` stopped being bookkeeping.

    `entered` is the ranker's own considered count, measured independently of the five drop
    counters, so this identity can genuinely fail. While `capped_by_top_n` was a remainder it
    could not, and the artifact correctly refused to present it as evidence.
    """
    report = funnel(considered=20, shortlisted=1, hidden_ineligible=5, hidden_non_swe=8,
                    hidden_hard_filter=4, hidden_below_cutoff=2, leads=[lead()])

    shortlist = stage(report, "shortlist")
    assert shortlist.derived is False
    assert shortlist.entered == 20, "the ranker's considered population, not a sum of drops"
    assert shortlist.reconciled is True
    body = funnel_to_markdown(report)
    row = next(line for line in body.splitlines() if line.startswith("| shortlist |"))
    assert row.rstrip().endswith("**yes** |"), row
    # Named in the artifact's own list of what could have failed, which is what the gate reads.
    assert "shortlist" in next(
        line for line in body.splitlines() if "could actually have failed" in line
    )


def test_a_posting_the_ranker_loses_breaks_the_shortlist_stage_instead_of_hiding() -> None:
    """The failure this stage now exists to catch: a `continue` with no counter.

    One posting considered but landing in no bucket must read as DOES NOT RECONCILE. Under the
    old remainder-based `entered` this input was arithmetically impossible to express, which is
    precisely why 14,873 postings could go missing without the artifact noticing.
    """
    report = funnel(considered=21, shortlisted=1, hidden_ineligible=5, hidden_non_swe=8,
                    hidden_hard_filter=4, hidden_below_cutoff=2, leads=[lead()])

    shortlist = stage(report, "shortlist")
    assert shortlist.reconciled is False
    assert report.reconciles is False
    assert "shortlist" in [item.name for item in report.unreconciled]


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
    # Bumped to 2 by P0 item 3, which added the sources and source_totals sections.
    assert payload["artifact_version"] == 2
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


# --------------------------------------------------------------------------------------
# Per-source outcomes (P0 item 3)
# --------------------------------------------------------------------------------------


def source(
    slug: str = "stripe", *, provider: str = "greenhouse", company_source: str = "registry",
    open_postings: int = 100, eligible: int = 40, leads: int = 1, applied: int = 0,
) -> SourceOutcome:
    return SourceOutcome(
        provider=provider, board_slug=slug, company_source=company_source,
        open_postings=open_postings, eligible=eligible, leads=leads, applied=applied,
    )


def source_row(body: str, board: str) -> str:
    """The rendered per-source table row for one board, not merely a line mentioning it."""
    return next(line for line in body.splitlines() if line.startswith(f"| {board} |"))


def test_the_per_source_table_names_each_board_and_its_outcomes() -> None:
    """Gate P0: which source produced each lead, from the artifact alone.

    Asserted on the RENDERED ROW rather than with `in body`: the section's own prose names
    every board, every column and every quantity it explains, so a substring assertion over
    the whole document would pass against an empty table.
    """
    report = funnel(sources=[source("stripe", leads=1, eligible=40),
                             source("quiet", leads=0, eligible=0, open_postings=7)])
    body = funnel_to_markdown(report)

    assert source_row(body, "greenhouse:stripe").split("|")[3].strip() == "100"
    assert source_row(body, "greenhouse:stripe").split("|")[7].strip() == "1"
    quiet = source_row(body, "greenhouse:quiet")
    assert quiet.split("|")[3].strip() == "7"
    assert quiet.split("|")[7].strip() == "0", "a board that produced nothing still gets a row"


def test_unique_and_assisted_render_as_uninstrumented_in_the_row_itself() -> None:
    """Not 0, and pinned inside the ROW. The paragraph above the table also says
    "not instrumented", so `in body` would pass with the cells rendering 0."""
    body = funnel_to_markdown(funnel(sources=[source("stripe")]))
    cells = [cell.strip() for cell in source_row(body, "greenhouse:stripe").split("|")]

    assert cells[4] == "not instrumented", "unique"
    assert cells[5] == "not instrumented", "assisted"


def test_unique_and_assisted_serialise_as_null_rather_than_zero(tmp_path: Path) -> None:
    """A machine consumer must be able to tell "no duplicates" from "never measured"."""
    written = write_run_funnel(funnel(sources=[source("stripe")]), tmp_path)
    row = json.loads(written.json_path.read_text())["sources"][0]

    assert row["unique"] is None
    assert row["assisted"] is None
    assert row["leads"] == 1


def test_a_lead_attributable_to_no_board_fails_reconciliation() -> None:
    """The check the companies join exists for.

    The funnel counted a `resume_tailored` row for this run that the per-board sweep could not
    resolve to any board — an artifact with no posting_version, or a vanished company row.
    Gate P0 asks which source produced each lead, so this cannot be allowed to read as green.
    """
    report = funnel(
        leads=[lead(7), lead(8)],
        artifacts=TailoredArtifactCounts(rows=2, with_pdf=2),
        sources=[source("stripe", leads=1)],
    )

    assert report.reconciles is False
    assert [total.name for total in report.unattributable] == ["leads"]
    body = funnel_to_markdown(report)
    assert next(line for line in body.splitlines() if line.startswith("| leads |")).endswith(
        "**NO** |"
    )


def test_the_per_source_eligible_total_is_not_offered_as_a_reconciliation() -> None:
    """It was, and a review showed it could not fail — so it was deleted, not kept as decoration.

    `eligible_by_company` groups the very same current-identity subquery the verdict stage
    counts, by a NOT NULL foreign key, joined on a primary key. Its sum equals the verdict
    stage's `eligible` for every possible database state. Shipping that as evidence is the
    defect D-023 exists to forbid, so the only remaining total is `leads`, whose two sides have
    genuinely different shapes.
    """
    report = funnel(counts=corpus(eligible=40), sources=[source("stripe", eligible=39)])

    assert [total.name for total in report.source_totals] == ["leads"]
    # A per-board eligible count that disagrees with the verdict stage does NOT fail the run,
    # because no honest implementation can produce that state.
    assert report.reconciles is True


def test_a_fully_attributed_run_reconciles() -> None:
    """The happy path must still be reachable, or the check above proves nothing."""
    report = funnel(
        leads=[lead(7)],
        counts=corpus(eligible=40),
        sources=[source("stripe", eligible=25, leads=1), source("brex", eligible=15, leads=0)],
    )

    assert report.unattributable == ()
    assert report.reconciles is True


def test_the_provider_rollup_aggregates_boards() -> None:
    """PROGRAM.md's breadth question is about PROVIDERS; 118 board rows do not answer it."""
    report = funnel(
        counts=corpus(eligible=60),
        artifacts=TailoredArtifactCounts(rows=1, with_pdf=1),
        leads=[lead(7)],
        sources=[
            source("stripe", provider="greenhouse", eligible=25, leads=1),
            source("brex", provider="greenhouse", eligible=25, leads=0),
            source("openai", provider="ashby", eligible=10, leads=0),
        ],
    )
    body = funnel_to_markdown(report)

    greenhouse = next(line for line in body.splitlines() if line.startswith("| greenhouse |"))
    assert greenhouse.split("|")[2].strip() == "2", "two boards rolled up"
    assert greenhouse.split("|")[4].strip() == "50"
    ashby = next(line for line in body.splitlines() if line.startswith("| ashby |"))
    assert ashby.split("|")[2].strip() == "1"
    # Leads first: the provider that produced one must outrank the one that did not.
    assert body.index("| greenhouse |") < body.index("| ashby |")


def test_a_run_where_the_ranker_never_ran_reports_the_stage_as_unmeasured() -> None:
    """A fatal scan outage and a missing profile both return before the ranker.

    Reporting 0 in / 0 out would assert that it ran, considered nothing, and accounted for
    everything — and since the stage is no longer `derived`, it would appear in the artifact's
    list of stages whose balance could actually have failed. That is a fabricated green tick on
    a stage that never executed.
    """
    report = funnel(ranker_ran=False, leads=[])

    shortlist = stage(report, "shortlist")
    assert shortlist.entered is None
    assert shortlist.advanced is None
    assert shortlist.reconciled is None, "an unmeasured stage must not report as reconciled"
    assert shortlist not in report.instrumented_stages
    # The tailor stage's `entered` is the shortlist count, so it is equally unknown.
    assert stage(report, "tailor").entered is None

    body = funnel_to_markdown(report)
    failed_line = next(line for line in body.splitlines() if "could actually have failed" in line)
    assert "shortlist" not in failed_line
    assert "tailor" not in failed_line
    row = next(line for line in body.splitlines() if line.startswith("| shortlist |"))
    assert "not instrumented" in row, row
