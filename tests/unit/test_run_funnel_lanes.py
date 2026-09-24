"""The funnel's `lanes` section (JD-acquisition spec §4.4, plan D7) — the pure half.

Two things are under test and neither is arithmetic. The first is that all ten acquisition
outcomes survive into the artifact even at zero: `AcquisitionTally` instruments all ten, so a 0
is a MEASURED zero, and an emitter that dropped the empty keys would turn it back into an
absence — the confusion that let the prior art's browser tier recover nothing for 11 runs with
nothing failing. The second is that `is_silent_outage` reaches the reader as its own field,
because `resolved == 0` is also true of a lane that had nothing to do.

`artifact_version` does not move for the lane section. It is asserted here as well as at the
three sites that already pin it, so the additive-key ruling is visible from the change that
relies on it. (The number itself is 7 since D-267 put each lead's location into the artifact —
that bump was NOT for `lanes`, and this test says so by pinning the constant, not a literal.)
"""

from __future__ import annotations

from pathlib import Path

from boardwatch.eligibility.catalog import load_rules
from boardwatch.lanes.base import SearchOutcome
from boardwatch.lanes.outcomes import ACQUISITION_OUTCOMES, AcquisitionTally
from boardwatch.reports.abstain import build_abstain_report
from boardwatch.reports.run_funnel import (
    ARTIFACT_VERSION,
    LaneReport,
    RunFunnel,
    RunManifest,
    ScanContext,
    build_run_funnel,
    funnel_to_dict,
    funnel_to_markdown,
)
from boardwatch.store.run_funnel_queries import (
    CorpusCounts,
    LaneCaptureCounts,
    TailoredArtifactCounts,
)


def _tally(*outcomes: str) -> AcquisitionTally:
    tally = AcquisitionTally()
    for outcome in outcomes:
        tally.record(outcome)
    return tally


def _report(
    name: str = "stub",
    *outcomes: str,
    admitted: tuple[tuple[str, str], ...] = (),
    refused: tuple[tuple[str, str], ...] = (),
    persisted_new: tuple[tuple[str, str], ...] = (),
    fetch_seconds: float | None = None,
    apply_seconds: float | None = None,
    search_pages: tuple[tuple[str, int], ...] = (),
    search_outcomes: tuple[SearchOutcome, ...] = (),
    snapshots: int | None = None,
) -> LaneReport:
    tally = _tally(*outcomes)
    return LaneReport(
        name=name,
        counts=tally.counts,
        attempted=tally.attempted,
        resolved=tally.resolved,
        is_silent_outage=tally.is_silent_outage,
        admitted=admitted,
        refused=refused,
        persisted_new=persisted_new,
        # Default None on purpose: every test above this line predates the cost split and must
        # keep exercising the NOT MEASURED path rather than being silently backfilled with 0.0.
        fetch_seconds=fetch_seconds,
        apply_seconds=apply_seconds,
        search_pages=search_pages,
        search_outcomes=search_outcomes,
        snapshots=snapshots,
    )


def _funnel(
    lanes: tuple[LaneReport, ...] = (), lane_captures: LaneCaptureCounts | None = None
) -> RunFunnel:
    """The smallest funnel that renders, with only the lane section varying."""
    return build_run_funnel(
        run_id=1,
        started_at=None,
        finished_at=None,
        manifest=RunManifest(
            code_fingerprint="f",
            config_hash="c",
            profile_facts_hash=None,
            profile_row_hash=None,
            rules_hash=None,
            status="ok",
            location_filter_mode="soft",
        ),
        scan=ScanContext(ran=False),
        corpus=CorpusCounts(
            open_postings=0,
            evaluated=0,
            no_current_evaluation=0,
            by_verdict={},
            judged_this_run=0,
            cache_hit_prior_run=0,
            cache_hit_unattributed=0,
        ),
        shortlist=None,
        sources=(),
        leads=(),
        tailor_failed=0,
        tailored_artifacts=TailoredArtifactCounts(rows=0, with_pdf=0),
        marked_applied=0,
        stub_postings=0,
        rewrite_rows=(),
        unattributed_evaluations=0,
        abstain=build_abstain_report(
            # No override dir: `load_rules` falls back to the bundled catalog.
            load_rules(Path("does-not-exist")), {}, not_applicable_families=frozenset()
        ),
        lanes=lanes,
        lane_captures=lane_captures,
    )


def test_the_artifact_version_does_not_move_for_the_lane_section() -> None:
    """Plan D7: `lanes` is an ADDITIVE key on the D-113 precedent, not a bump of its own.

    Asserted from both directions — the constant and the emitted payload — because a bump made
    in the constant alone would still change every artifact a consumer reads. Pinned AGAINST
    the constant rather than against a literal, so a later bump made for some other section
    cannot be read as evidence that `lanes` earned one.
    """
    assert funnel_to_dict(_funnel())["artifact_version"] == ARTIFACT_VERSION
    assert (
        funnel_to_dict(_funnel((_report("stub", "body_inline"),)))["artifact_version"]
        == ARTIFACT_VERSION
    )


def test_a_run_with_no_lane_still_emits_the_key_as_an_empty_list() -> None:
    """`[]`, not a missing key: absent would read as an OLDER artifact rather than as a run
    with every lane off, and those are different facts about the same JSON."""
    payload = funnel_to_dict(_funnel())
    assert "lanes" in payload
    assert payload["lanes"] == []


def test_every_one_of_the_ten_outcomes_reaches_the_artifact_including_the_zeros() -> None:
    """A dropped zero is an absence, and an absence reads as "not measured"."""
    payload = funnel_to_dict(_funnel((_report("stub", "body_inline", "fetch_gone"),)))

    counts = payload["lanes"][0]["counts"]  # type: ignore[index]
    assert set(counts) == set(ACQUISITION_OUTCOMES)
    assert counts["body_inline"] == 1
    assert counts["fetch_gone"] == 1
    # The measured zeros are present rather than pruned.
    assert counts["dependency_missing"] == 0
    assert counts["rejected_login_wall"] == 0


def test_a_lane_that_attempted_work_and_recovered_nothing_reports_a_silent_outage() -> None:
    """The condition the whole tally exists to make visible."""
    payload = funnel_to_dict(_funnel((_report("stub", "fetch_refused", "extracted_empty"),)))

    lane = payload["lanes"][0]  # type: ignore[index]
    assert lane["attempted"] == 2
    assert lane["resolved"] == 0
    assert lane["is_silent_outage"] is True
    assert "SILENT OUTAGE" in funnel_to_markdown(_funnel((
        _report("stub", "fetch_refused", "extracted_empty"),
    )))


def test_a_lane_with_nothing_to_attempt_is_not_reported_as_an_outage() -> None:
    """`is_silent_outage` is not `resolved == 0`. A lane with no work is a benign zero, and
    crying outage over it would train the reader to ignore the line that matters."""
    payload = funnel_to_dict(_funnel((_report("quiet"),)))

    lane = payload["lanes"][0]  # type: ignore[index]
    assert lane["attempted"] == 0
    assert lane["resolved"] == 0
    assert lane["is_silent_outage"] is False
    assert "SILENT OUTAGE" not in funnel_to_markdown(_funnel((_report("quiet"),)))


def test_both_sides_of_the_company_cap_are_named_not_merely_counted() -> None:
    """A company dropped silently is indistinguishable from one the lane never saw."""
    report = _report(
        "stub",
        "body_inline",
        admitted=(("hiringcafe", "src:tok"),),
        refused=(("greenhouse", "acme"), ("lever", "beta")),
    )
    payload = funnel_to_dict(_funnel((report,)))

    lane = payload["lanes"][0]  # type: ignore[index]
    assert lane["admitted"] == ["hiringcafe:src:tok"]
    assert lane["refused"] == ["greenhouse:acme", "lever:beta"]

    markdown = funnel_to_markdown(_funnel((report,)))
    assert "`greenhouse:acme`" in markdown
    assert "`lever:beta`" in markdown


def test_the_persisted_reach_is_reported_beside_the_cap_approvals_in_both_halves() -> None:
    """T140. `admitted` is what the cap APPROVED before any body was fetched; an approval whose
    bodies were all unavailable never becomes a company row. Measured live, 214 of 1,342
    admissions across 27 of 27 runs were never persisted, so the gap is the normal case and not
    an edge — both renderers must carry the persisted number, because the JSON is what a later
    measurement reads and the Markdown is what the owner reads."""
    report = _report(
        "stub",
        "body_inline",
        admitted=(("hiringcafe", "src:lands"), ("hiringcafe", "src:bodyless")),
        persisted_new=(("hiringcafe", "src:lands"),),
    )

    lane = funnel_to_dict(_funnel((report,)))["lanes"][0]  # type: ignore[index]
    assert lane["admitted"] == ["hiringcafe:src:lands", "hiringcafe:src:bodyless"]
    assert lane["persisted_new"] == ["hiringcafe:src:lands"]

    markdown = funnel_to_markdown(_funnel((report,)))
    assert "2 new companies admitted · 1 persisted · 0 refused by the cap" in markdown
    assert "- **persisted:** `hiringcafe:src:lands`" in markdown
    # The two corrected sentences: the rendered note, and the docstring the note paraphrases.
    assert "the reach this run ADDED" not in markdown
    assert LaneReport.__doc__ is not None
    assert "so its length is the reach this run ADDED" not in LaneReport.__doc__


def test_the_markdown_section_is_absent_when_no_lane_ran() -> None:
    """The JSON half carries `lanes: []` for a machine; a human reading a lane-less run is not
    served by a heading over a sentence saying nothing happened."""
    assert "## Lanes" not in funnel_to_markdown(_funnel())
    assert "## Lanes" in funnel_to_markdown(_funnel((_report("stub", "body_inline"),)))


def test_both_halves_of_a_lanes_cost_reach_the_artifact() -> None:
    """D-346. The stage total could not say whether the lane stage's 6.5 min was upstream
    throttling or contention on the single writer; these two keys are what separate them."""
    payload = funnel_to_dict(
        _funnel((_report("hiringcafe", "body_inline", fetch_seconds=12.5, apply_seconds=3.25),))
    )
    lane = payload["lanes"][0]
    assert lane["fetch_seconds"] == 12.5
    assert lane["apply_seconds"] == 3.25


def test_an_unmeasured_lane_cost_is_null_and_never_zero() -> None:
    """`0.0` would claim a lane cost nothing; `null` says it was not measured. The distinction is
    the same one the ten `AcquisitionOutcome` zeros exist to preserve, in the other direction."""
    lane = funnel_to_dict(_funnel((_report("stub", "body_inline"),)))["lanes"][0]
    assert lane["fetch_seconds"] is None
    assert lane["apply_seconds"] is None
    assert "NOT MEASURED" in funnel_to_markdown(_funnel((_report("stub", "body_inline"),)))


def test_the_markdown_names_the_fetch_share_because_the_ratio_is_the_diagnostic() -> None:
    """A lane that is mostly fetch is throttled upstream and parallelising the lanes would help
    it; one that is mostly apply is queued behind the single writer and parallelising would not.
    The share is printed rather than left to the reader to divide, so the artifact answers the
    question it was added for."""
    markdown = funnel_to_markdown(
        _funnel((_report("linkedin", "body_inline", fetch_seconds=9.0, apply_seconds=1.0),))
    )
    assert "90% fetch" in markdown
    assert "10.0s total" in markdown
    assert "9.0s paced fetching" in markdown
    assert "1.0s applying" in markdown


def test_a_lane_with_no_measurable_cost_does_not_divide_by_zero() -> None:
    """Both halves at 0.0 is reachable — a lane whose work is below the clock's resolution — and
    the share is undefined there rather than 0%."""
    markdown = funnel_to_markdown(
        _funnel((_report("stub", "body_inline", fetch_seconds=0.0, apply_seconds=0.0),))
    )
    assert "no measurable cost" in markdown


_PAGES = (("https://a.test/s?q=1", 1), ("https://a.test/s?q=2", 1))
_OUTCOMES = (
    SearchOutcome("ended"),
    SearchOutcome("later_page_failed", "fetch_failure", 403),
)


def test_search_outcomes_reach_the_json_beside_search_pages() -> None:
    """T144: a new key, aligned with `search_pages`, the cause as typed fields. `search_pages`
    itself does not move."""
    lane = funnel_to_dict(
        _funnel((_report("hc", search_pages=_PAGES, search_outcomes=_OUTCOMES),))
    )["lanes"][0]  # type: ignore[index]

    assert lane["search_pages"] == [{"url": url, "pages": pages} for url, pages in _PAGES]
    assert lane["search_outcomes"] == [
        {"end": "ended", "failure": None, "status_code": None},
        {"end": "later_page_failed", "failure": "fetch_failure", "status_code": 403},
    ]


def test_a_lane_with_no_search_emits_an_empty_outcome_list() -> None:
    """Empty, never absent -- the `search_pages` convention."""
    lane = funnel_to_dict(_funnel((_report("jobapps"),)))["lanes"][0]  # type: ignore[index]
    assert lane["search_outcomes"] == []


def test_search_outcomes_render_beside_the_page_counts() -> None:
    markdown = funnel_to_markdown(
        _funnel((_report("hc", search_pages=_PAGES, search_outcomes=_OUTCOMES),))
    )

    assert "| search | pages fetched | ended |" in markdown
    assert "| https://a.test/s?q=1 | 1 | ended |" in markdown
    assert "| https://a.test/s?q=2 | 1 | later_page_failed (fetch_failure 403) |" in markdown


def test_a_lane_without_outcomes_renders_its_page_table_as_before() -> None:
    """Control: LinkedIn reports depth and no outcome, and no search at all renders no table."""
    paged = funnel_to_markdown(_funnel((_report("li", search_pages=_PAGES),)))
    assert "| search | pages fetched |\n|---|---:|" in paged
    assert "| https://a.test/s?q=1 | 1 |\n" in paged

    unpaged = funnel_to_markdown(_funnel((_report("jobapps"),)))
    assert "| search | pages fetched" not in unpaged


# --- T191: each lane's self-report, recounted from the store ---------------------------------

_TWO = (("hiringcafe", "src:a"), ("hiringcafe", "src:b"))


def _checks(funnel: RunFunnel) -> dict[str, tuple[int, int, bool]]:
    return {c.name: (c.in_memory, c.from_store, c.agrees) for c in funnel.cross_checks}


def test_a_lane_claiming_more_new_reach_than_the_store_holds_disagrees() -> None:
    """The red case F8 names: the lane says two companies were newly persisted, the store's
    first-capture recount finds one. The row lands in `disagreements`, so the run stops
    reconciling through the same property the three older cross-checks feed."""
    funnel = _funnel(
        (_report("stub", admitted=_TWO, persisted_new=_TWO, snapshots=2),),
        LaneCaptureCounts(first_captures={"stub": 1}, scan_rows=2, attributed_by_row=True),
    )
    assert _checks(funnel)["lane:stub:persisted_new"] == (2, 1, False)
    assert [c.name for c in funnel.disagreements] == ["lane:stub:persisted_new"]
    assert funnel.reconciles is False
    rows = {row["name"]: row for row in funnel_to_dict(funnel)["cross_checks"]}
    assert rows["lane:stub:persisted_new"]["agrees"] is False


def test_a_lane_whose_self_report_matches_the_store_agrees() -> None:
    """Control for the case above: same shape, the store agrees, nothing is flagged."""
    funnel = _funnel(
        (_report("stub", admitted=_TWO, persisted_new=_TWO, snapshots=2),),
        LaneCaptureCounts(first_captures={"stub": 2}, scan_rows=2, attributed_by_row=True),
    )
    assert _checks(funnel)["lane:stub:persisted_new"] == (2, 2, True)
    assert _checks(funnel)["lanes:board_scans"] == (2, 2, True)
    assert funnel.disagreements == ()


def test_the_reach_note_says_when_the_recount_fell_back_to_admission() -> None:
    """T199. A run whose lane rows name no lane is attributed by admission alone; the note says so
    rather than passing the number off as row-attributed. The row-attributed run's note does not."""

    def note(attributed_by_row: bool) -> str:
        funnel = _funnel(
            (_report("stub", admitted=_TWO, persisted_new=_TWO, snapshots=2),),
            LaneCaptureCounts(
                first_captures={"stub": 2}, scan_rows=2, attributed_by_row=attributed_by_row
            ),
        )
        return next(c.note for c in funnel.cross_checks if c.name == "lane:stub:persisted_new")

    assert "ATTRIBUTED BY ADMISSION ONLY" in note(False)
    assert "ATTRIBUTED BY ADMISSION ONLY" not in note(True)
    assert "naming this lane" in note(True)


def test_lane_scan_rows_the_lanes_did_not_report_disagree() -> None:
    """The row count is checked once, across every lane:
    the sum of the snapshots the lanes say they applied against the store's `scan_kind='lane'`
    rows for the run."""
    funnel = _funnel(
        (
            _report("a", snapshots=2),
            _report("b", snapshots=1),
        ),
        LaneCaptureCounts(first_captures={"a": 0, "b": 0}, scan_rows=4, attributed_by_row=True),
    )
    assert _checks(funnel)["lanes:board_scans"] == (3, 4, False)


def test_a_lane_that_did_not_run_has_no_row_and_absent_is_not_zero() -> None:
    """No lane ran: no lane rows at all, rather than rows of zeros that claim a check passed."""
    captures = LaneCaptureCounts(first_captures={}, scan_rows=0, attributed_by_row=True)
    names = set(_checks(_funnel((), captures)))
    assert not any(name.startswith("lane") for name in names)


def test_unmeasured_store_counts_emit_no_lane_rows() -> None:
    """A caller that did not read the store gets no lane rows, never a store count of 0."""
    names = set(_checks(_funnel((_report("stub", persisted_new=_TWO, snapshots=2),))))
    assert not any(name.startswith("lane") for name in names)


def test_an_unmeasured_snapshot_count_omits_only_the_scan_row_check() -> None:
    """`snapshots=None` is NOT MEASURED: comparing it as 0 against the store's rows would flag a
    healthy run. The per-lane reach check still runs, because both of its sides were measured."""
    checks = _checks(
        _funnel(
            (_report("stub", admitted=_TWO, persisted_new=_TWO),),
            LaneCaptureCounts(first_captures={"stub": 2}, scan_rows=2, attributed_by_row=True),
        )
    )
    assert "lanes:board_scans" not in checks
    assert checks["lane:stub:persisted_new"] == (2, 2, True)
