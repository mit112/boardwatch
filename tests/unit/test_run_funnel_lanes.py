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
from boardwatch.store.run_funnel_queries import CorpusCounts, TailoredArtifactCounts


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
    )


def _funnel(lanes: tuple[LaneReport, ...] = ()) -> RunFunnel:
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


def test_the_markdown_section_is_absent_when_no_lane_ran() -> None:
    """The JSON half carries `lanes: []` for a machine; a human reading a lane-less run is not
    served by a heading over a sentence saying nothing happened."""
    assert "## Lanes" not in funnel_to_markdown(_funnel())
    assert "## Lanes" in funnel_to_markdown(_funnel((_report("stub", "body_inline"),)))
