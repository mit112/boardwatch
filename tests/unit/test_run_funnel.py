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

import ast
import json
from pathlib import Path

from boardwatch.eligibility.catalog import RulesCatalog, load_rules
from boardwatch.rank.location_gate import classify_location
from boardwatch.reports.abstain import AbstainReport, build_abstain_report
from boardwatch.reports.board_coverage import BoardCoverage
from boardwatch.reports.board_coverage import CoverageReport as BoardCoverageReport
from boardwatch.reports.board_coverage import build_report as build_board_report
from boardwatch.reports.run_funnel import (
    Lead,
    LivenessCheck,
    RunFunnel,
    RunManifest,
    ScanContext,
    ShortlistCounts,
    build_coverage_summary,
    build_run_funnel,
    funnel_to_dict,
    funnel_to_markdown,
    write_run_funnel,
)
from boardwatch.store.run_funnel_queries import (
    CorpusCounts,
    DedupSweep,
    SourceOutcome,
    TailoredArtifactCounts,
)
from boardwatch.tailor.coverage import CoverageReport
from boardwatch.tailor.rewrite import filter as rewrite_filter
from boardwatch.tailor.rewrite import lane, verb_diversity

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


def lead(
    posting_id: int = 7,
    *,
    pdf_built: bool = True,
    slug: str = "stripe",
    locations: tuple[str, ...] | None = ("New York, NY",),
) -> Lead:
    return Lead(
        posting_id=posting_id,
        title="Backend Engineer",
        company="Stripe",
        provider="greenhouse",
        board_slug=slug,
        company_source="registry",
        out_dir=f"/tmp/apps/2026-08-06/stripe-{posting_id}",
        pdf_built=pdf_built,
        locations=locations,
    )


def run_manifest(
    *,
    code_fingerprint: str = "engine-1+abc123def456",
    config_hash: str = "c0ffee",
    profile_facts_hash: str | None = "pf00",
    profile_row_hash: str | None = "pr00",
    rules_hash: str | None = "ru1e5",
    status: str = "ok",
    location_filter_mode: str = "soft",
) -> RunManifest:
    return RunManifest(
        code_fingerprint=code_fingerprint,
        config_hash=config_hash,
        profile_facts_hash=profile_facts_hash,
        profile_row_hash=profile_row_hash,
        rules_hash=rules_hash,
        status=status,
        location_filter_mode=location_filter_mode,
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
    hidden_duplicate: int = 0,
    hidden_applied: int = 0,
    hidden_handled: int = 0,
    hidden_over_seniority: int = 0,
    hidden_zero_signal: int = 0,
    signal_unmeasured: int = 0,
    uncertain_band: int = 0,
    band_tokens_seen_while_inert: int = 0,
    judged_this_run: int = 0,
    handled_this_run: int = 0,
    applied_this_run: int = 0,
    duplicate_this_run: int = 0,
    dead_this_run: int = 0,
    liveness: LivenessCheck | None = None,
    scan: ScanContext | None = None,
    considered: int | None = None,
    tailor_failed: int = 0,
    artifacts: TailoredArtifactCounts | None = None,
    marked_applied: int = 0,
    abstain: AbstainReport | None = None,
    unattributed_evaluations: int = 20_637,
    sources: list[SourceOutcome] | None = None,
    # False models a run where the ranker never executed (no profile / fatal scan outage).
    ranker_ran: bool = True,
    manifest: RunManifest | None = None,
    stub_postings: int = 0,
    rewrite_rows: list[dict[str, object]] | None = None,
    coverages: list[CoverageReport | None] | None = None,
    board_coverage: BoardCoverageReport | None = None,
    # P6. `None` means the duplicate sweep did not run, which is what every test that is not
    # about dedup wants: the stage then reports itself unmeasured, as it always did.
    dedup: DedupSweep | None = None,
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
            + hidden_duplicate + hidden_applied + hidden_over_seniority + hidden_handled
            + hidden_zero_signal
        )
    # `uncertain_band`, `band_tokens_seen_while_inert` and `signal_unmeasured` are
    # deliberately ABSENT from that sum: they count postings that PASSED and are already
    # inside `shortlisted`. Adding them here would be the same double-count that adding
    # them to `drops` would be. `hidden_zero_signal` IS in the sum -- it is a real drop.
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
            stubs=stub_postings,
        )]
    return build_run_funnel(
        board_coverage=board_coverage,
        run_id=42,
        started_at=None,
        finished_at=None,
        manifest=manifest or run_manifest(),
        scan=scan or ScanContext(ran=True, boards_attempted=85, boards_complete=80,
                                 boards_failed=5, postings_seen=13_590),
        corpus=counts,
        shortlist=ShortlistCounts(
            considered=considered,
            shortlisted=shortlisted,
            hidden_hard_filter=hidden_hard_filter,
            hidden_non_swe=hidden_non_swe,
            hidden_ineligible=hidden_ineligible,
            hidden_below_cutoff=hidden_below_cutoff,
            skipped_not_new=skipped_not_new,
            hidden_duplicate=hidden_duplicate,
            hidden_applied=hidden_applied,
            hidden_handled=hidden_handled,
            hidden_over_seniority=hidden_over_seniority,
            hidden_zero_signal=hidden_zero_signal,
            signal_unmeasured=signal_unmeasured,
            uncertain_band=uncertain_band,
            band_tokens_seen_while_inert=band_tokens_seen_while_inert,
            judged_this_run=judged_this_run,
            handled_this_run=handled_this_run,
            applied_this_run=applied_this_run,
            duplicate_this_run=duplicate_this_run,
            dead_this_run=dead_this_run,
        ) if ranker_ran else None,
        liveness=liveness,
        leads=leads,
        tailor_failed=tailor_failed,
        tailored_artifacts=tailored_artifacts,
        sources=sources,
        marked_applied=marked_applied,
        stub_postings=stub_postings,
        rewrite_rows=rewrite_rows or [],
        coverages=coverages or [],
        unattributed_evaluations=unattributed_evaluations,
        abstain=abstain or build_abstain_report(catalog(), {}),
        dedup=dedup,
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


def test_the_dedup_bound_renders_beside_the_drop_and_not_as_one() -> None:
    """Gate P0 is answerable from the ARTIFACT, so the Markdown has to keep the two apart.

    `company_title_location` redundancy is an upper bound over genuinely different jobs
    (D-327). Rendered in the same bullet list as `suppressed_duplicate` a reader would sum
    them and quote a suppression that never happened, so it renders under its own heading
    that says what it is not.
    """
    sweep = DedupSweep(
        complete=True,
        entered=84_821,
        suppressed=2_064,
        suppressing_groups=1_472,
        suppressing_redundant=2_064,
        candidate_redundant={"company_title_location": 5_268, "content_hash_only": 12_571},
        suppressed_by_company={},
    )
    rendered = funnel_to_markdown(funnel(dedup=sweep))

    assert "### dedup — 84821 in, 82757 out" in rendered
    assert "- **suppressed_duplicate**: 2064" in rendered
    assert "Beside the drop — **not** dropped, and never summed into it:" in rendered
    assert "- `candidate_redundant_company_title_location`: 5268" in rendered
    # The bound is not in the stage's arithmetic: dropped is the suppression alone.
    assert stage(funnel(dedup=sweep), "dedup").dropped == 2_064


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
    # ...and the JSON half, which this test stopped one line short of. `funnel_to_dict`'s
    # `"reconciles"` key can be hardcoded True with the whole suite green: every one of the
    # eight assertions on it repo-wide checks `is True`, so the False path was never pinned.
    # That key is the machine-readable accounting record and what the web viewer's run-list
    # badge reads, so hardcoding it shows a run GREEN in the UI while the markdown beside it
    # says DOES NOT RECONCILE — the artifact contradicting itself is precisely what Gate P0's
    # "reconciles to 100%" cannot afford.
    assert funnel_to_dict(report)["reconciles"] is False


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

    `artifacts.uri` holds the `.tex` path whether or not a PDF was ever produced, so a row
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
    # NOT proof that `entered` is independent of the drops — this fixture is balanced, so a
    # remainder-based implementation gives 20 too. The sibling test below, with an UNBALANCED
    # input, is what can actually fail. See the module docstring on what is and is not pinned.
    assert shortlist.entered == 20
    assert shortlist.reconciled is True
    body = funnel_to_markdown(report)
    row = next(line for line in body.splitlines() if line.startswith("| shortlist |"))
    assert row.rstrip().endswith("**yes** |"), row
    # Named in the artifact's own list of what could have failed, which is what the gate reads.
    assert "shortlist" in next(
        line for line in body.splitlines() if "could actually have failed" in line
    )


def test_an_applied_suppression_is_named_in_the_artifact_and_still_reconciles() -> None:
    """P6 item 5. The ranker's `hidden_applied` bucket has to be mirrored here or the identity
    above goes False — which is the only thing standing between "a new bucket" and "postings
    quietly missing from the funnel again", since the three bucket lists are hand-maintained.
    """
    report = funnel(considered=17, shortlisted=1, hidden_ineligible=5, hidden_non_swe=8,
                    hidden_applied=3, leads=[lead()])

    shortlist = stage(report, "shortlist")
    # Asserted FIRST, because this is the claim: drop the mirroring and the identity goes False
    # on its own, without needing a test that knows the bucket's name.
    assert shortlist.entered == 17
    assert shortlist.reconciled is True
    applied = next(drop for drop in shortlist.drops if drop.reason == "hidden_applied")
    assert applied.count == 3
    assert "track status" in applied.note  # the drain is named where the count is


def test_the_shortlist_stage_reconciles_with_the_new_bucket() -> None:
    """D-246. `hidden_over_seniority` is a DROP, so it must be mirrored here or the identity
    goes False — the same hand-maintained mirror that `hidden_applied` above guards."""
    report = funnel(considered=10, shortlisted=6, hidden_ineligible=0, hidden_non_swe=0,
                    hidden_over_seniority=4, leads=[lead()], tailor_failed=5)

    shortlist = stage(report, "shortlist")
    assert shortlist.entered == 10
    assert shortlist.reconciled is True


def test_the_shortlist_stage_reconciles_with_the_zero_signal_bucket() -> None:
    """`hidden_zero_signal` is a genuine DROP, in the same shape as `hidden_over_seniority`.

    Non-zero on purpose: a `Drop` that is merely PRESENT is proved by nothing, because a
    zero-count drop leaves the identity balanced whether it is mirrored or not. With four
    postings in the bucket, deleting the `Drop` from the shortlist stage takes `entered` to
    10 against a drop sum of 6 and this test fails.
    """
    report = funnel(considered=10, shortlisted=6, hidden_ineligible=0, hidden_non_swe=0,
                    hidden_zero_signal=4, leads=[lead()], tailor_failed=5)

    shortlist = stage(report, "shortlist")
    assert shortlist.entered == 10
    assert shortlist.reconciled is True
    drop = next(item for item in shortlist.drops if item.reason == "zero_signal_uncertain")
    assert drop.count == 4
    # The note has to say what the bucket MEANS, not just name it: this is the only place an
    # operator reading the artifact learns why the postings went.
    assert "no recognised requirement terms" in drop.note
    assert "--include-zero-signal" in drop.note  # the drain is named where the count is


def test_the_unmeasured_signal_abstain_is_reported_and_never_subtracted(tmp_path: Path) -> None:
    """`signal_unmeasured` counts postings that PASSED, so it must not be a `Drop` — AND it has
    to reach the durable artifact anyway.

    Both halves, because pinning only the negative is what let the counter go nowhere at all.
    `zero_signal_uncertain: 0` is ambiguous between "no such posting" and "the rule never got
    the input it reads", and resolving that ambiguity is the ONLY reason this counter exists —
    so a value that lives in memory and reaches no `Drop`, no note and no JSON key defeats it
    entirely. Asserted in BOTH rendered halves: absence from the drops is not evidence of
    presence anywhere else, and a machine consumer reads the JSON, not the prose.

    Set NON-ZERO against a `considered` that excludes it. If it were ever mirrored as a drop
    the stage would subtract it twice and `reconciled` would go False here.
    """
    report = funnel(considered=10, shortlisted=6, hidden_ineligible=0, hidden_non_swe=0,
                    hidden_zero_signal=4, signal_unmeasured=3, leads=[lead()], tailor_failed=5)

    shortlist = stage(report, "shortlist")
    assert shortlist.entered == 10
    assert shortlist.reconciled is True
    assert not [item for item in shortlist.drops if item.reason == "signal_unmeasured"]

    # The COUNT, not just the name: a renderer that names the bucket and drops the figure
    # answers nothing from the artifact alone.
    body = funnel_to_markdown(report)
    assert "`signal_unmeasured`: 3" in body

    written = write_run_funnel(report, tmp_path)
    payload = json.loads(written.json_path.read_text())
    shortlist_json = next(item for item in payload["stages"] if item["name"] == "shortlist")
    assert "`signal_unmeasured`: 3" in shortlist_json["note"]
    # And it is still not a drop on the machine-readable side either.
    assert "signal_unmeasured" not in {drop["reason"] for drop in shortlist_json["drops"]}


def test_funnel_carries_run_scoped_attribution() -> None:
    """B5: the run-scoped attribution surfaces as an ADDITIVE shortlist field. A run that judged
    3 candidates this run, handled 1 of them this run, and produced 0 leads leaves 2
    unexplained. The corpus reconciliation identity (`reconciled`) is untouched by this field."""
    report = funnel(
        considered=10, shortlisted=0, hidden_ineligible=0, hidden_non_swe=0,
        hidden_below_cutoff=10, leads=[], tailor_failed=0,
        judged_this_run=3, handled_this_run=1,
    )

    shortlist = stage(report, "shortlist")
    assert shortlist.reconciled is True
    assert shortlist.run_scoped_attribution == {
        "judged": 3, "handled": 1, "applied": 0, "duplicate": 0, "dead": 0, "unexplained": 2,
    }


def test_the_markdown_names_the_over_seniority_drop_with_its_count() -> None:
    """Gate P0's *why every non-lead was dropped*, and the drain named where the count is."""
    report = funnel(considered=10, shortlisted=6, hidden_ineligible=0, hidden_non_swe=0,
                    hidden_over_seniority=4, leads=[lead()], tailor_failed=5)

    assert "- **hidden_over_seniority**: 4" in funnel_to_markdown(report)
    drop = next(d for d in stage(report, "shortlist").drops
                if d.reason == "hidden_over_seniority")
    assert "top --include-over-seniority" in drop.note


def test_uncertain_band_is_reported_but_is_not_a_drop() -> None:
    """Folding an abstain into a drop would break the identity AND hide the abstain.

    `uncertain_band` counts postings that PASSED — they are already inside `advanced`. A
    `Drop` for them would subtract them a second time and the stage would stop reconciling,
    so the number is carried in the stage's report prose instead.
    """
    report = funnel(considered=10, shortlisted=6, hidden_ineligible=0, hidden_non_swe=0,
                    uncertain_band=3, band_tokens_seen_while_inert=2,
                    hidden_over_seniority=4, leads=[lead()], tailor_failed=5)

    shortlist = stage(report, "shortlist")
    assert shortlist.reconciled is True
    assert all(drop.reason != "uncertain_band" for drop in shortlist.drops)
    assert all(drop.reason != "band_tokens_seen_while_inert" for drop in shortlist.drops)
    body = funnel_to_markdown(report)
    assert "uncertain_band" in body
    assert "band_tokens_seen_while_inert" in body
    # The counts themselves, not just the names — a renderer that names the bucket and drops
    # the figure answers nothing "from the artifact alone".
    assert "`uncertain_band`: 3" in body
    assert "`band_tokens_seen_while_inert`: 2" in body


# ------------------------------- the scan block's four-way board split (never three-way)


def test_the_markdown_names_the_partial_and_unchanged_boards_it_used_to_swallow() -> None:
    """Run 126's real split. The three-way line said "346 attempted · 166 complete · 1 failed",
    leaving 179 boards a reader could only read as having silently done nothing."""
    report = funnel(scan=ScanContext(
        ran=True, boards_attempted=346, boards_complete=166, boards_partial=39,
        boards_unchanged=140, boards_failed=1, postings_seen=18_553,
    ))

    body = funnel_to_markdown(report)
    assert (
        "346 boards attempted · 166 complete · 39 partial · 140 unchanged · 1 failed"
    ) in body
    assert "partition the boards attempted" in body


def test_a_board_outcome_that_is_empty_reports_zero_rather_than_dropping_its_key() -> None:
    """A measured zero and an absent bucket are different claims — this fix exists because
    the artifact could not tell them apart."""
    payload = funnel_to_dict(funnel(scan=ScanContext(
        ran=True, boards_attempted=2, boards_complete=2, postings_seen=7,
    )))["scan"]

    assert payload["boards_partial"] == 0
    assert payload["boards_unchanged"] == 0
    assert payload["boards_failed"] == 0
    assert payload["boards_reconciled"] is True


def test_a_scan_whose_outcomes_do_not_sum_to_the_boards_attempted_says_so() -> None:
    """The reconciliation is published, not implied: a gap is named where it is read."""
    report = funnel(scan=ScanContext(
        ran=True, boards_attempted=346, boards_complete=166, boards_failed=1,
        postings_seen=18_553,
    ))

    assert funnel_to_dict(report)["scan"]["boards_reconciled"] is False
    assert "do not sum to the boards attempted" in funnel_to_markdown(report)


def test_a_run_that_did_not_scan_reports_no_reconciliation_rather_than_a_pass() -> None:
    """`0 == 0` is not evidence. Same rule as `Stage.reconciled`: an uncomputable identity
    is `None`, never a tick."""
    payload = funnel_to_dict(funnel(scan=ScanContext(ran=False)))["scan"]

    assert payload["boards_reconciled"] is None


def test_the_artifact_version_does_not_move_for_the_board_split() -> None:
    """ADDITIVE keys in a block that has existed since v1, on the `scan.fetch_cost` precedent.

    Nothing already in the artifact changes meaning: `boards_attempted`, `boards_complete`,
    `boards_failed` and `postings_seen` count exactly what they counted before, and a consumer
    that ignores `boards_partial`/`boards_unchanged`/`boards_reconciled` reads every old key
    correctly. Pinned as a literal because that is what a consumer sees.
    """
    from boardwatch.reports.run_funnel import ARTIFACT_VERSION

    assert ARTIFACT_VERSION == 7
    assert funnel_to_dict(funnel())["artifact_version"] == 7


def test_an_unprobed_liveness_check_reports_unmeasured_rather_than_zero_dead() -> None:
    """P6 item 6, and the D-022/D-023 rule it obeys: nulls, not zeros, and `instrumented` is
    emitted so a reader never has to infer "unmeasured" from a null."""
    report = funnel()
    payload = funnel_to_dict(report)

    assert payload["liveness"] == {
        "instrumented": False, "checked": None, "dead": None, "unknown": None, "alive": None,
        "gone_after_redirect": None,
    }
    section = funnel_to_markdown(report).split("## Liveness")[1].split("##")[0]
    assert "not instrumented" in section
    assert "NOT the same as no dead postings" in section


def test_a_probed_liveness_check_reports_dead_and_unknown_separately() -> None:
    """`unknown` is next to `dead` and not folded into `alive`: a run where the probe learned
    nothing looks identical to a healthy one if you read only `dead`."""
    report = funnel(liveness=LivenessCheck(checked=10, dead=2, unknown=3, gone_after_redirect=1))
    payload = funnel_to_dict(report)

    # `gone_after_redirect` is a SUBSET of `unknown` — `alive` still subtracts only dead+unknown,
    # so 10-2-3 is 5 and not 4. Adding it to the partition is the tempting mistake here.
    assert payload["liveness"] == {
        "instrumented": True, "checked": 10, "dead": 2, "unknown": 3, "alive": 5,
        "gone_after_redirect": 1,
    }
    section = funnel_to_markdown(report).split("## Liveness")[1].split("##")[0]
    assert "2 withheld as gone" in section
    assert "3 unknown (served)" in section
    assert "1 were gone-after-redirect" in section
    assert "disarmed" in section


def test_a_posting_the_ranker_loses_breaks_the_shortlist_stage_instead_of_hiding() -> None:
    """The failure this stage now exists to catch: a `continue` with no counter.

    One posting considered but landing in no bucket must read as DOES NOT RECONCILE. Under the
    old remainder-based `entered` this input was arithmetically impossible to express, which is
    precisely why 15,959 postings could go missing without the artifact noticing.
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


# --------------------------------------------------------------------------------------
# Artifact v7 — a lead's location, and the hard US gate's verdict on it (D-267)
# --------------------------------------------------------------------------------------


def test_a_lead_carries_the_locations_its_posting_named() -> None:
    """D-267: the hard US gate is the one gate whose failure is a lead the user cannot take,
    and until v7 a `Lead` row carried no location at all — so the gate left no trace in the
    artifact it produces and no "all leads US-located" claim was reproducible afterwards."""
    (row,) = funnel_to_dict(funnel(leads=[lead(locations=("Austin, TX", "Remote"))]))["leads"]

    assert row["locations"] == ["Austin, TX", "Remote"]


def test_a_lead_that_names_no_place_reports_null_rather_than_an_empty_list() -> None:
    """`None` and `[]` are different claims about the same posting, exactly as
    `delivery_queries._posted_days` returns None rather than 0: a posting that names no place
    has not named an empty place, and a reader must be able to tell "the board published no
    location" from "the board published a location this build read as nothing"."""
    (row,) = funnel_to_dict(funnel(leads=[lead(locations=None)]))["leads"]

    assert row["locations"] is None
    # And the gate still records a verdict on it — an unresolvable location is `unknown`,
    # which is what the gate FAIL-OPENS on. Absent would read as "the gate never ran".
    assert row["location_class"] == "unknown"


def test_the_verdict_beside_a_lead_is_the_production_classifier_s_own() -> None:
    """Not a second implementation living in the report layer. The artifact's claim is only
    worth reading if it is the same function the ranker vetoed with — `classify_location` —
    so it is asserted against that function rather than against transcribed answers."""
    cases: tuple[tuple[str, ...], ...] = (
        ("Austin, TX",),
        ("Berlin, Germany",),
        ("Remote",),
        ("Bengaluru, India", "New York, NY"),
    )
    for locations in cases:
        (row,) = funnel_to_dict(funnel(leads=[lead(locations=locations)]))["leads"]
        assert row["location_class"] == classify_location(locations), locations


def test_the_verdict_field_can_carry_the_value_the_gate_is_supposed_to_drop() -> None:
    """Without this the audit is vacuous. A field that can only ever say `us`/`unknown` makes
    "no lead classifies non_us" true by construction, which is the D-267/D-268 failure mode:
    a metric that reads healthy whether or not the thing it measures is present."""
    (row,) = funnel_to_dict(funnel(leads=[lead(locations=("Buc, France",))]))["leads"]

    assert row["location_class"] == "non_us"


def test_the_markdown_leads_table_names_each_lead_s_location_and_verdict() -> None:
    """Gate P0's "from the artifact alone, without reading code" applies to the human half
    too: the Markdown is what an operator reads when a visa-ineligible lead is suspected."""
    body = funnel_to_markdown(
        funnel(leads=[lead(7, locations=("Austin, TX",)), lead(9, locations=None)])
    )

    rows = [line for line in body.splitlines() if line.startswith(("| 7 |", "| 9 |"))]
    assert len(rows) == 2, body
    assert "Austin, TX" in rows[0] and "| us |" in rows[0]
    # The absent case renders as an em dash and `unknown`, never as an empty cell that reads
    # like a rendering bug.
    assert "| — |" in rows[1] and "| unknown |" in rows[1]


def test_the_leads_section_records_its_match_rule_and_its_corpus_size() -> None:
    """D-268's rule, applied where the claim is made: a ratio records its match rule AND its
    corpus size beside it, or only the numerator is quotable later. "0 leads classify
    non_us" is worthless without "over these 2 leads, by classify_location"."""
    body = funnel_to_markdown(funnel(leads=[lead(7), lead(9)]))

    (rule_line,) = [line for line in body.splitlines() if "classify_location" in line]
    assert "location_gate" in rule_line, rule_line
    assert "2 lead" in rule_line, rule_line


def test_the_manifest_says_whether_the_location_gate_was_armed_at_all() -> None:
    """The verdicts are unreadable without it. `location_filter_mode` is `soft` by default, and
    in `soft` mode a `non_us` lead is not a leak — it is the documented behaviour. A reader who
    cannot see the mode cannot tell a passing gate from a disarmed one."""
    payload = funnel_to_dict(funnel(manifest=run_manifest(location_filter_mode="hard")))["manifest"]

    assert payload["location_filter_mode"] == "hard"
    body = funnel_to_markdown(funnel(manifest=run_manifest(location_filter_mode="hard")))
    row = next(line for line in body.splitlines() if line.startswith("| location filter mode |"))
    assert "hard" in row


def test_the_hard_gate_s_claim_is_checkable_from_the_artifact_alone() -> None:
    """The whole point of v7. Nothing here reads the store, the settings or the ranker — it is
    the check an operator can run over a `funnel-N.json` months later, and it must be able to
    FAIL, which the `non_us` lead below is there to prove."""
    payload = funnel_to_dict(
        funnel(
            manifest=run_manifest(location_filter_mode="hard"),
            leads=[lead(7, locations=("Austin, TX",)), lead(9, locations=("Buc, France",))],
        )
    )

    armed = payload["manifest"]["location_filter_mode"] == "hard"
    leaked = [row["posting_id"] for row in payload["leads"] if row["location_class"] == "non_us"]
    assert armed and leaked == [9], payload["leads"]


def test_the_markdown_names_every_drop_reason_with_its_count() -> None:
    """Gate P0: *why every non-lead was dropped* — every bucket named and counted in prose.

    A reader must never have to subtract two numbers to discover why postings left the
    funnel, so each reason appears with its own figure.
    """
    # Every shortlist bucket gets a DISTINCT non-zero count. With two of them left at 0, the
    # renderer could swap `hidden_hard_filter` and `capped_by_top_n` and the suite stayed green
    # — the artifact would misstate WHY postings were dropped and still reconcile.
    report = funnel(
        counts=corpus(no_current_evaluation=10, ineligible=20, uncertain=30),
        hidden_ineligible=5,
        hidden_non_swe=8,
        hidden_hard_filter=4,
        hidden_below_cutoff=2,
        skipped_not_new=7,
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
        "hidden_hard_filter": 4, "capped_by_top_n": 2, "skipped_not_new": 7,
        "tailor_failed": 3, "no_pdf": 0, "not_marked_applied": 1,
    }
    for reason, count in expected.items():
        assert f"- **{reason}**: {count}" in body, (
            f"{reason} is not stated with its count; the reader would have to subtract"
        )


def test_the_markdown_reports_every_catalog_rule_including_those_that_never_fired() -> None:
    """Gate P0 requires per-rule abstain for EVERY rule in the catalog.

    The rules worth knowing about are the ones with no rows at all, and a report built by
    grouping the data cannot show them. each of the 45 must be named, and a never-fired rule
    must read as `never fired` rather than as 0%.
    """
    cat = catalog()
    body = funnel_to_markdown(funnel(abstain=build_abstain_report(cat, {})))

    ids = [pattern.rule_id for family in cat.families for pattern in family.patterns]
    assert len(ids) == 45
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


def test_a_field_tier_rule_that_does_not_apply_renders_as_not_applicable() -> None:
    """A field-tier family skipped for THIS profile's career_field is correctly scoped out —
    not dead — and the artifact has to say which of the two it is.

    Both halves regressed before this test existed. The Markdown reached the rate branch and
    formatted a `None` rate, and because `write_run_funnel` writes the JSON first the failure
    surfaced as a half-written artifact pair rather than a crash. The JSON carried no flag at
    all, so the rule read as `never_fired: false, abstain_rate: null` — folded into the noise
    the keystone invariant forbids folding an abstain into.
    """
    cat = catalog()
    skipped = "clearance"
    report = funnel(
        abstain=build_abstain_report(cat, {}, not_applicable_families=frozenset({skipped}))
    )
    skipped_ids = [p.rule_id for f in cat.families if f.id == skipped for p in f.patterns]
    assert skipped_ids, "the fixture family declares no rules to scope out"

    body = funnel_to_markdown(report)
    # Scoped to the skipped family's OWN table rows. The section explains itself in English
    # and the phrase recurs in its census line and prose, so a bare substring check would
    # pass on the commentary alone.
    rows = {
        line.split("|")[1].strip(): line.rsplit("|", 2)[-2].strip()
        for line in body.splitlines()
        if line.startswith("| ") and rule_id_prefix(line, skipped_ids)
    }
    assert set(rows) == set(skipped_ids), f"a scoped-out rule went unrendered: {set(rows)}"
    assert set(rows.values()) == {"not applicable"}, rows
    # The census must still partition the catalog: not-applicable is in neither of the other
    # two buckets, so omitting it makes the three numbers stop adding up.
    census = next(line for line in body.splitlines() if "rules in the catalog" in line)
    assert f"{len(skipped_ids)} not applicable to this field" in census

    abstain = funnel_to_dict(report)["abstain"]
    rules = {r["rule_id"]: r for r in abstain["rules"]}  # type: ignore[index]
    assert all(rules[rule_id]["not_applicable"] is True for rule_id in skipped_ids)
    assert all(rules[rule_id]["never_fired"] is False for rule_id in skipped_ids)
    assert abstain["not_applicable"] == len(skipped_ids)  # type: ignore[index]
    assert abstain["never_fired"] == abstain["rule_count"] - len(skipped_ids)  # type: ignore[index]


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
    # Bumped to 3 by P0 item 4/6/8, which added the manifest, stub_rate and fabrication
    # sections; to 4 by P6 item 6, which added the top-level `liveness` block; to 5 by P5a,
    # which added the `projection` stage and changed what `tailor.entered` means on a
    # projected run; to 6 by D-274, which added the `board_coverage` section so a scheduled
    # run reports the discovery coverage it was already persisting; to 7 by D-267, which put
    # each lead's `locations` and the hard US gate's verdict on them into the record the gate
    # itself produces.
    assert payload["artifact_version"] == 7
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
    stubs: int = 0,
) -> SourceOutcome:
    return SourceOutcome(
        provider=provider, board_slug=slug, company_source=company_source,
        open_postings=open_postings, eligible=eligible, leads=leads, applied=applied,
        stubs=stubs,
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
    # Distinct values in every column, so no assertion is satisfied by a neighbouring cell and
    # a swapped pair is caught. `eligible` matters most: its reconciliation was deleted for
    # being unfailable, so this row is now the ONLY guard on the rendered per-board figure.
    report = funnel(
        counts=corpus(eligible=43),
        artifacts=TailoredArtifactCounts(rows=1, with_pdf=1),
        leads=[lead(7)],
        sources=[source("stripe", leads=1, eligible=40, open_postings=100, applied=3),
                 source("quiet", leads=0, eligible=2, open_postings=7, company_source="user")],
    )
    body = funnel_to_markdown(report)

    stripe = [cell.strip() for cell in source_row(body, "greenhouse:stripe").split("|")]
    assert stripe[2] == "registry", "registry/user column"
    assert stripe[3] == "100", "open"
    assert stripe[6] == "40", "eligible"
    assert stripe[7] == "1", "leads"
    assert stripe[8] == "3", "applied"
    quiet = [cell.strip() for cell in source_row(body, "greenhouse:quiet").split("|")]
    assert quiet[2] == "user"
    assert quiet[3] == "7"
    assert quiet[6] == "2"
    assert quiet[7] == "0", "a board that produced nothing still gets a row"


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
    """The one comparison whose two sides are shaped differently, so it can disagree.

    The funnel counted `resume_tailored` ROWS for this run; the per-board sweep counted DISTINCT
    postings resolved through `posting_versions`. An artifact whose posting_version_id is NULL
    resolves to no board, and two artifacts for one posting collapse to one distinct posting.
    Gate P0 asks which source produced each lead, so neither may read as green. NOT a test of a
    vanished company row: `postings.company_id` is NOT NULL behind an enforced foreign key, so
    that state is unreachable (D-028).
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
        # ashby FIRST, so the ordering assertion below tests the sort key rather than the
        # order these were written in: `totals` is a dict built in source order.
        sources=[
            source("openai", provider="ashby", eligible=10, leads=0, open_postings=60),
            source("stripe", provider="greenhouse", eligible=25, leads=1, open_postings=30),
            source("brex", provider="greenhouse", eligible=25, leads=0, open_postings=20),
        ],
    )
    body = funnel_to_markdown(report)

    def rollup_row(provider: str) -> list[str]:
        prefix = f"| {provider} |"
        row = next(line for line in body.splitlines() if line.startswith(prefix))
        return [cell.strip() for cell in row.split("|")]

    greenhouse = rollup_row("greenhouse")
    assert greenhouse[2] == "2", "two boards rolled up"
    assert greenhouse[3] == "50", "open summed, not the board count"
    assert greenhouse[4] == "50", "eligible summed"
    assert greenhouse[5] == "1", "leads summed"
    ashby = rollup_row("ashby")
    assert ashby[2] == "1"
    assert ashby[3] == "60"
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


def test_an_uninstrumented_stage_with_no_note_still_renders_a_readable_line() -> None:
    """`tailor` carries no note, so an unmeasured run rendered a bare `**` under the drops.

    Small, but this is the section Gate P0 requires to be readable without consulting code, and
    a stray `**` in it is the artifact failing to explain a stage it chose not to measure.
    """
    body = funnel_to_markdown(funnel(ranker_ran=False, leads=[]))
    tailor_index = body.splitlines().index("### tailor")
    following = body.splitlines()[tailor_index + 1 : tailor_index + 3]

    assert "**" not in following, following
    assert any(line.strip() for line in following), "the stage explained nothing at all"


# --------------------------------------------------------------------------------------
# Artifact v3 — manifest (item 4), stub rate (item 6), fabrication counters (item 8)
# --------------------------------------------------------------------------------------


def test_manifest_renders_in_both_halves() -> None:
    """The manifest is what makes two runs comparable for reproducibility; it must survive to
    the JSON a check reads and the Markdown a human reads."""
    report = funnel(
        manifest=run_manifest(
            code_fingerprint="engine-2+deadbeef1234",
            config_hash="CONFIGHASH",
            profile_facts_hash="PFHASH",
            profile_row_hash="PRHASH",
            rules_hash="RULESHASH",
            status="ok",
            location_filter_mode="hard",
        )
    )
    payload = funnel_to_dict(report)["manifest"]
    assert payload == {
        "code_fingerprint": "engine-2+deadbeef1234",
        "config_hash": "CONFIGHASH",
        "profile_facts_hash": "PFHASH",
        "profile_row_hash": "PRHASH",
        "rules_hash": "RULESHASH",
        "status": "ok",
        "location_filter_mode": "hard",
    }
    body = funnel_to_markdown(report)
    config_row = next(line for line in body.splitlines() if line.startswith("| config hash |"))
    assert "CONFIGHASH" in config_row
    prow = next(line for line in body.splitlines() if line.startswith("| profile row hash |"))
    assert "PRHASH" in prow


def test_manifest_shows_dash_for_absent_profile_hashes() -> None:
    """A run with no profile has no profile-dependent hash; the artifact must say so as `—`,
    not render a Python `None` a reader would misread."""
    report = funnel(
        manifest=run_manifest(
            code_fingerprint="engine-2+abc",
            config_hash="C",
            profile_facts_hash=None,
            profile_row_hash=None,
            rules_hash=None,
            status="ok",
        )
    )
    body = funnel_to_markdown(report)
    prow = next(line for line in body.splitlines() if line.startswith("| profile row hash |"))
    assert "None" not in prow
    assert prow.strip().endswith("| — |")


def test_stub_rate_reports_a_fraction_scoped_to_its_row() -> None:
    report = funnel(counts=corpus(open_postings=200), stub_postings=4)
    assert report.stub_rate.rate == 0.02
    payload = funnel_to_dict(report)["stub_rate"]
    assert payload == {"open_postings": 200, "stubs": 4, "rate": 0.02}
    body = funnel_to_markdown(report)
    line = next(line for line in body.splitlines() if "empty JD body" in line)
    assert "4 of 200" in line and "2.00%" in line


def test_stub_rate_over_an_empty_corpus_is_none_never_zero() -> None:
    """A rate over zero rows is undefined; 0% would read as a healthy corpus of stubs."""
    report = funnel(counts=corpus(open_postings=0), stub_postings=0)
    assert report.stub_rate.rate is None
    assert funnel_to_dict(report)["stub_rate"]["rate"] is None
    body = funnel_to_markdown(report)
    assert any("not instrumented" in line for line in body.splitlines() if "rate" in line)


def _filter_reject_reasons() -> set[str]:
    """Every reason `passes_overmatch_filter` can put in a `FilterResult`, read from its
    source. `lane.py` interpolates these behind the `filter:` prefix, so the funnel's
    prefix branch is only proven total if the set comes from the filter itself."""
    tree = ast.parse(Path(rewrite_filter.__file__).read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "FilterResult"
        ):
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    out.add(arg.value)
    return out


def _emitted_drop_reasons() -> set[str]:
    """Derive the `drop_reason` values the Tier-B emitters can actually produce.

    Read from the emitters' own source at call time, never restated here: a hard-coded list
    agrees with itself, so adding a fourteenth literal to `lane.py` would leave a test named
    "every drop reason" green while covering thirteen. Both emitter modules are located
    through their imported module objects, so a move or a rename fails loudly rather than
    silently matching nothing.

    Two shapes appear at the `drop_reason=` keyword: a plain string constant, and one
    f-string (`f"filter:{fr.reason}"`). The f-string is expanded by taking its literal
    prefix and crossing it with the filter's own reason catalog; `None` (a kept row) is not
    a drop reason and is skipped.
    """
    reasons: set[str] = set()
    saw_interpolated = False
    for module in (lane, verb_diversity):
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.keyword) or node.arg != "drop_reason":
                continue
            value = node.value
            if isinstance(value, ast.Constant):
                if isinstance(value.value, str):
                    reasons.add(value.value)
                continue
            assert isinstance(value, ast.JoinedStr), ast.dump(value)
            prefix = "".join(
                part.value
                for part in value.values
                if isinstance(part, ast.Constant) and isinstance(part.value, str)
            )
            assert prefix, "an interpolated drop_reason with no literal prefix is unmappable"
            saw_interpolated = True
            reasons |= {f"{prefix}{r}" for r in _filter_reject_reasons()}
    # The derivation is only a check if it actually found things; an empty or truncated walk
    # would otherwise pass this test by classifying nothing.
    assert saw_interpolated, "the filter: f-string arm was not reached — did lane.py change?"
    assert len(reasons) >= 15, sorted(reasons)
    return reasons


def test_fabrication_counters_classify_every_drop_reason() -> None:
    """Every `drop_reason` the Tier-B emitters can produce lands in a named bucket.

    `other` is the closed catalog's tripwire — a non-zero value renders a literal FAILURE
    line in the artifact — so this asserts `other == 0` over the DERIVED set of emitted
    reasons rather than over a list retyped here. Adding a new `drop_reason=` literal to
    `lane.py` or `verb_diversity.py` without a funnel branch fails this test.
    """
    emitted = _emitted_drop_reasons()
    rows: list[dict[str, object]] = [
        {"kept": False, "drop_reason": reason} for reason in sorted(emitted)
    ]
    report = funnel(rewrite_rows=rows)
    fab = report.fabrication
    assert fab.bullets_seen == len(emitted)
    assert fab.other == 0, sorted(emitted)
    # The two reasons this slice's own work turns on, named explicitly so a derivation that
    # silently stopped finding them cannot pass the count assertion above by luck.
    assert "lane_dead" in emitted and fab.lane_dead == 1
    assert "verb_repeat" in emitted and fab.verb_diversity_rejected == 1


def test_fabrication_counters_separate_the_truth_gates_from_the_fallbacks() -> None:
    """The two truth gates (judge, overmatch filter) are the fabrication signal B4 measures;
    they must be counted apart from the non-fabrication fallbacks."""
    rows: list[dict[str, object]] = [
        {"kept": True, "drop_reason": None},
        {"kept": False, "drop_reason": "unchanged"},
        {"kept": False, "drop_reason": "judge"},
        {"kept": False, "drop_reason": "filter:overmatch_tech"},
        {"kept": False, "drop_reason": "budget"},
        {"kept": False, "drop_reason": "error"},
        {"kept": False, "drop_reason": "no_candidate"},
        {"kept": False, "drop_reason": "lane_dead"},
    ]
    report = funnel(rewrite_rows=rows)
    fab = report.fabrication
    assert (fab.bullets_seen, fab.kept, fab.unchanged) == (8, 1, 1)
    assert (fab.judge_rejected, fab.overmatch_filtered, fab.rejected) == (1, 1, 2)
    assert (fab.budget, fab.error, fab.no_candidate, fab.other) == (1, 1, 1, 0)
    # `lane_dead` is NOT `error`: the provider was never called for these bullets.
    assert fab.lane_dead == 1
    assert funnel_to_dict(report)["fabrication"]["lane_dead"] == 1
    body = funnel_to_markdown(report)
    line = next(line for line in body.splitlines() if "rejected by a truth gate" in line)
    assert "2 rejected" in line and "1 judge" in line and "1 overmatch" in line
    fallbacks = next(line for line in body.splitlines() if line.startswith("fallbacks:"))
    assert "1 lane_dead" in fallbacks


def test_structural_filter_rejects_are_excluded_from_the_b4_numerator() -> None:
    """`passes_overmatch_filter` (tailor/rewrite/filter.py) emits structural rejects (empty,
    not_single_line, too_long) alongside its fabrication catches (invented_entity,
    invented_skill). A structural malformation is not a fabrication and must not inflate B4's
    `rejected` numerator — it lands in its own `filter_structural_rejected` bucket instead."""
    rows: list[dict[str, object]] = [
        {"kept": False, "drop_reason": "filter:too_long"},
        {"kept": False, "drop_reason": "filter:empty"},
        {"kept": False, "drop_reason": "filter:not_single_line"},
        {"kept": False, "drop_reason": "filter:invented_entity"},
        {"kept": False, "drop_reason": "judge"},
    ]
    report = funnel(rewrite_rows=rows)
    fab = report.fabrication
    assert fab.filter_structural_rejected == 3
    # Mutation check: only the fabrication catch (invented_entity) counts toward
    # `overmatch_filtered`/`rejected` — the three structural rejects must not.
    assert (fab.judge_rejected, fab.overmatch_filtered, fab.rejected) == (1, 1, 2)
    assert fab.other == 0
    payload = funnel_to_dict(report)["fabrication"]
    assert payload["filter_structural_rejected"] == 3
    assert payload["rejected"] == 2
    body = funnel_to_markdown(report)
    assert any(
        "3" in line and "structural malformation" in line for line in body.splitlines()
    )


def test_an_unknown_drop_reason_is_a_failure_bucket_not_a_silent_drop() -> None:
    """CLAUDE.md: out-of-catalog is a failure, never a new bucket. An unrecognised Tier-B
    outcome must surface as `other` and print a FAILURE line, not vanish."""
    report = funnel(rewrite_rows=[{"kept": False, "drop_reason": "teleported"}])
    assert report.fabrication.other == 1
    body = funnel_to_markdown(report)
    assert any("FAILURE" in line and "closed catalog does not name" in line
               for line in body.splitlines())


def test_provenance_vetoes_are_counted_separately_from_the_b4_numerator() -> None:
    """A provenance veto is a conservative, deliberately over-broad guard, not a caught
    fabrication (P1b). It must land in its own named bucket — not `other` (out-of-catalog)
    and not `rejected` (the B4 numerator, judge + overmatch only)."""
    rows: list[dict[str, object]] = [
        {"kept": False, "drop_reason": "provenance"},
        {"kept": False, "drop_reason": "provenance"},
        {"kept": False, "drop_reason": "judge"},
        {"kept": False, "drop_reason": "filter:overmatch_tech"},
    ]
    report = funnel(rewrite_rows=rows)
    fab = report.fabrication
    assert fab.provenance_rejected == 2
    assert fab.other == 0
    # Mutation check: `rejected` must stay judge + overmatch only, unmoved by provenance rows.
    assert (fab.judge_rejected, fab.overmatch_filtered, fab.rejected) == (1, 1, 2)
    payload = funnel_to_dict(report)["fabrication"]
    assert payload["provenance_rejected"] == 2
    assert payload["rejected"] == 2
    body = funnel_to_markdown(report)
    assert any(
        "2" in line and "reverted to Tier-A for lack of provenance" in line
        for line in body.splitlines()
    )


def test_overmatch_vetoes_are_counted_separately_from_the_b4_numerator() -> None:
    """P4 item 1 (D-048): the deterministic overmatch (verbatim-lift / unusual-caps) veto is
    a conservative, deliberately over-broad guard, not a caught fabrication -- same
    treatment as provenance. It must land in its own named bucket (`lift_rejected`), not
    `other` (out-of-catalog) and not `rejected` (the B4 numerator, judge + the OLDER
    pre-judge overmatch filter only). Distinguished from `filter:overmatch_tech`, which is a
    different, older mechanism that happens to share the "overmatch" name."""
    rows: list[dict[str, object]] = [
        {"kept": False, "drop_reason": "overmatch"},
        {"kept": False, "drop_reason": "overmatch"},
        {"kept": False, "drop_reason": "provenance"},
        {"kept": False, "drop_reason": "judge"},
        {"kept": False, "drop_reason": "filter:overmatch_tech"},
    ]
    report = funnel(rewrite_rows=rows)
    fab = report.fabrication
    assert fab.lift_rejected == 2
    assert fab.provenance_rejected == 1
    assert fab.other == 0
    # Mutation check: `rejected` must stay judge + the older overmatch filter only, unmoved
    # by the new overmatch (lift) rows.
    assert (fab.judge_rejected, fab.overmatch_filtered, fab.rejected) == (1, 1, 2)
    payload = funnel_to_dict(report)["fabrication"]
    assert payload["lift_rejected"] == 2
    assert payload["rejected"] == 2
    body = funnel_to_markdown(report)
    assert any(
        "2" in line and "verbatim JD-span lift or unusual capitalization" in line
        for line in body.splitlines()
    )


def test_an_unclassified_overmatch_variant_would_still_land_in_other() -> None:
    """CLAUDE.md: out-of-catalog is a failure, never a new bucket. A near-miss string that
    is NOT exactly "overmatch" (e.g. a typo or a future sub-reason) must surface as `other`,
    not silently get folded into `lift_rejected`."""
    report = funnel(rewrite_rows=[{"kept": False, "drop_reason": "overmatched"}])
    assert report.fabrication.lift_rejected == 0
    assert report.fabrication.other == 1


def test_register_vetoes_are_counted_separately_from_the_b4_numerator() -> None:
    """P4 item 3a: the three craft-register guards (banned-register, buzzword-density,
    verb-diversity) are conservative style/register vetoes, not caught fabrications -- same
    treatment as provenance_rejected/lift_rejected. Each lands in its own named bucket, not
    `other` (out-of-catalog) and not `rejected` (the B4 numerator, judge + the older
    pre-judge overmatch filter only)."""
    rows: list[dict[str, object]] = [
        {"kept": False, "drop_reason": "banned_register"},
        {"kept": False, "drop_reason": "banned_register"},
        {"kept": False, "drop_reason": "buzzword_density"},
        {"kept": False, "drop_reason": "verb_repeat"},
        {"kept": False, "drop_reason": "judge"},
        {"kept": False, "drop_reason": "filter:overmatch_tech"},
    ]
    report = funnel(rewrite_rows=rows)
    fab = report.fabrication
    assert fab.banned_register_rejected == 2
    assert fab.buzzword_rejected == 1
    assert fab.verb_diversity_rejected == 1
    assert fab.other == 0
    # Mutation check: `rejected` must stay judge + overmatch only, unmoved by the three new
    # register buckets.
    assert (fab.judge_rejected, fab.overmatch_filtered, fab.rejected) == (1, 1, 2)
    payload = funnel_to_dict(report)["fabrication"]
    assert payload["banned_register_rejected"] == 2
    assert payload["buzzword_rejected"] == 1
    assert payload["verb_diversity_rejected"] == 1
    assert payload["rejected"] == 2
    body = funnel_to_markdown(report)
    assert any(
        "2" in line and "banned-register cliché" in line for line in body.splitlines()
    )


def test_an_unclassified_register_variant_would_still_land_in_other() -> None:
    """CLAUDE.md: out-of-catalog is a failure, never a new bucket. Near-miss strings that
    are NOT exactly the three closed-catalog reasons must surface as `other`."""
    report = funnel(
        rewrite_rows=[
            {"kept": False, "drop_reason": "banned_registers"},
            {"kept": False, "drop_reason": "buzzword_densities"},
            {"kept": False, "drop_reason": "verb_repeats"},
        ]
    )
    fab = report.fabrication
    assert (fab.banned_register_rejected, fab.buzzword_rejected, fab.verb_diversity_rejected) == (
        0,
        0,
        0,
    )
    assert fab.other == 3


def test_requirement_echo_vetoes_are_counted_separately_from_the_b4_numerator() -> None:
    """P4 item 3b: a requirement-echo veto is a conservative style/register veto, not a
    caught fabrication -- same treatment as the three P4 item 3a register buckets. Lands
    in its own named bucket, not `other` (out-of-catalog) and not `rejected` (the B4
    numerator, judge + the older pre-judge overmatch filter only)."""
    rows: list[dict[str, object]] = [
        {"kept": False, "drop_reason": "requirement_echo"},
        {"kept": False, "drop_reason": "requirement_echo"},
        {"kept": False, "drop_reason": "judge"},
        {"kept": False, "drop_reason": "filter:overmatch_tech"},
    ]
    report = funnel(rewrite_rows=rows)
    fab = report.fabrication
    assert fab.requirement_echo_rejected == 2
    assert fab.other == 0
    # Mutation check: `rejected` must stay judge + overmatch only, unmoved by the new
    # requirement-echo bucket.
    assert (fab.judge_rejected, fab.overmatch_filtered, fab.rejected) == (1, 1, 2)
    payload = funnel_to_dict(report)["fabrication"]
    assert payload["requirement_echo_rejected"] == 2
    assert payload["rejected"] == 2
    body = funnel_to_markdown(report)
    assert any(
        "2" in line and "restating a JD qualification" in line for line in body.splitlines()
    )


def test_an_unclassified_requirement_echo_variant_would_still_land_in_other() -> None:
    """CLAUDE.md: out-of-catalog is a failure, never a new bucket."""
    report = funnel(rewrite_rows=[{"kept": False, "drop_reason": "requirement_echoes"}])
    assert report.fabrication.requirement_echo_rejected == 0
    assert report.fabrication.other == 1


# -- P4 item 6: keyword-coverage summary section -----------------------------------


def _cov(fraction: float | None, missing: tuple[str, ...] = ()) -> CoverageReport:
    total = 0 if fraction is None else 4
    covered = 0 if fraction is None else round(fraction * total)
    return CoverageReport(
        covered=tuple(f"c{i}" for i in range(covered)),
        missing=missing,
        denominator_source="qualifications",
        covered_count=covered,
        total_count=total,
        fraction=fraction,
    )


def test_build_coverage_summary_averages_only_leads_with_a_fraction() -> None:
    summary = build_coverage_summary(
        [
            _cov(0.5, missing=("Kubernetes", "Go")),
            _cov(1.0, missing=()),
            _cov(None),  # JD named no recognized requirements: excluded from the average
            None,  # measurement unavailable: not counted as measured at all
        ]
    )
    assert summary.leads_measured == 3
    assert summary.leads_with_fraction == 2
    assert summary.mean_fraction == 0.75
    assert summary.median_fraction == 0.75
    assert ("Kubernetes", 1) in summary.top_missing


def test_zero_lead_run_fabricates_no_coverage() -> None:
    summary = build_coverage_summary([])
    assert summary.leads_measured == 0
    assert summary.leads_with_fraction == 0
    # None, never 0.0 — a mean over zero leads is undefined, not "covers nothing".
    assert summary.mean_fraction is None
    assert summary.median_fraction is None
    assert summary.top_missing == ()


def test_coverage_section_renders_in_the_markdown_artifact() -> None:
    leads_cov = [_cov(0.5, missing=("Kubernetes",))]
    body = funnel_to_markdown(funnel(leads=[lead()], coverages=leads_cov))
    assert "## Keyword coverage" in body
    assert "Kubernetes" in body
    assert "REPORT, never a veto" in body


def test_coverage_section_says_measured_zero_when_no_coverage() -> None:
    body = funnel_to_markdown(funnel(leads=[lead()]))
    assert "0 lead(s) measured" in body


# --------------------------------------------------------------------------------------
# The board_coverage section (D-274)
# --------------------------------------------------------------------------------------


def _one_measured_board() -> BoardCoverageReport:
    return build_board_report(
        [
            BoardCoverage(
                company_id=1,
                name="Acme",
                provider="greenhouse",
                bucket="measured",
                held=500,
                board_reported_total=1000,
                board_enumerated=1000,
                detail_deferred=0,
                shortfall=500,
                ratio=0.5,
            )
        ]
    )


def test_board_coverage_is_null_when_it_could_not_be_measured() -> None:
    """`null`, never a zeroed block: a run whose coverage load FAILED must not be
    indistinguishable from a run that measured every board at nothing."""
    payload = funnel_to_dict(funnel(board_coverage=None))

    assert payload["board_coverage"] is None


def test_board_coverage_is_a_separate_key_from_resume_keyword_coverage() -> None:
    """`coverage` in this artifact has meant resume KEYWORD coverage since P4 item 6. Two
    different measurements one word apart would mislead every future reader, so the board
    instrument gets its own key and the old one keeps its meaning."""
    payload = funnel_to_dict(funnel(board_coverage=_one_measured_board()))

    assert set(payload["coverage"]) == {  # type: ignore[arg-type]
        "leads_measured",
        "leads_with_fraction",
        "mean_fraction",
        "median_fraction",
        "top_missing",
    }
    assert payload["board_coverage"] is not None
    assert "bucket_counts" in payload["board_coverage"]  # type: ignore[operator]


def test_board_coverage_reaches_both_halves_of_the_artifact() -> None:
    """A JSON-only section would leave the operator's own reading surface mute, which is the
    defect this change exists to fix."""
    built = funnel(board_coverage=_one_measured_board())

    payload = funnel_to_dict(built)
    rendered = funnel_to_markdown(built)

    assert payload["board_coverage"]["global_ratio"] == 0.5  # type: ignore[index]
    assert "## Board coverage" in rendered
    assert "50.0%" in rendered
    assert "greenhouse:Acme" in rendered


def test_the_markdown_still_renders_a_board_coverage_section_when_it_is_absent() -> None:
    """The heading is unconditional. A missing section reads as "this artifact predates the
    instrument"; a present section saying "not measured" reads as what actually happened."""
    rendered = funnel_to_markdown(funnel(board_coverage=None))

    assert "## Board coverage" in rendered
    assert "not measured this run" in rendered
