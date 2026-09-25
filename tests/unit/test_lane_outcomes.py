"""The closed acquisition-outcome catalog (design §4.4)."""

import pytest

from boardwatch.lanes.outcomes import (
    ACQUISITION_OUTCOMES,
    AcquisitionTally,
    UnknownAcquisitionOutcome,
)


def test_the_catalog_is_the_ten_outcomes_the_design_names_plus_the_two_group_outcomes():
    assert set(ACQUISITION_OUTCOMES) == {
        "body_inline",
        "body_fetched",
        "fetch_refused",
        "fetch_gone",
        "fetch_unavailable",
        "dependency_missing",
        "extracted_empty",
        "rejected_login_wall",
        "rejected_quality_gate",
        "not_attemptable",
        # T220: counted per GROUP by the job-apps lane, not per posting.
        "dangling_group_link",
        # T238: likewise per GROUP -- one that resolves but cannot be listed.
        "unreadable_group",
    }


def test_an_out_of_catalog_outcome_raises_at_the_recording_site():
    """Out-of-catalog is a failure, never a new bucket."""
    tally = AcquisitionTally()
    with pytest.raises(UnknownAcquisitionOutcome) as excinfo:
        tally.record("body_probably_fine")
    assert excinfo.value.name == "body_probably_fine"


def test_every_outcome_carries_a_counter_even_at_zero():
    """A zero must be present and readable, not absent.

    An absent key is what let the prior art run 11 scheduled days at zero recoveries without
    anyone noticing. All ten are instrumented, so 0 here is a measured zero.
    """
    tally = AcquisitionTally()
    tally.record("body_inline")
    assert set(tally.counts) == set(ACQUISITION_OUTCOMES)
    assert tally.counts["body_inline"] == 1
    assert tally.counts["fetch_refused"] == 0


def test_counts_is_a_copy_so_a_reader_cannot_mutate_the_tally():
    tally = AcquisitionTally()
    snapshot = tally.counts
    tally.record("body_inline")
    assert snapshot["body_inline"] == 0
    assert tally.counts["body_inline"] == 1


def test_attempted_is_the_sum_of_the_record_unit_outcomes():
    """`attempted` counts RECORDS, the unit the funnel publishes as `lanes[].attempted`: the sum of
    every outcome except `dangling_group_link` and `unreadable_group`, which count source GROUPS
    (T220, T238)."""
    tally = AcquisitionTally()
    for outcome in (
        "body_inline", "body_inline", "fetch_gone", "rejected_login_wall", "dangling_group_link",
        "unreadable_group",
    ):
        tally.record(outcome)
    assert tally.attempted == 4
    assert tally.attempted == sum(
        count
        for name, count in tally.counts.items()
        if name not in {"dangling_group_link", "unreadable_group"}
    )


def test_resolved_counts_only_the_two_body_bearing_outcomes():
    tally = AcquisitionTally()
    for outcome in ("body_inline", "body_fetched", "extracted_empty", "fetch_refused"):
        tally.record(outcome)
    assert tally.resolved == 2


def test_a_dependency_failure_is_never_counted_as_a_fetch_failure():
    """The distinction that hid an 11-day outage: these are separate counters."""
    tally = AcquisitionTally()
    tally.record("dependency_missing")
    assert tally.counts["dependency_missing"] == 1
    assert tally.counts["fetch_unavailable"] == 0
    assert tally.resolved == 0


def test_a_tier_that_resolved_nothing_from_real_attempts_is_a_reportable_condition():
    tally = AcquisitionTally()
    for _ in range(53):
        tally.record("fetch_unavailable")
    assert tally.is_silent_outage


def test_a_tier_with_no_attempts_at_all_is_not_an_outage():
    """Nothing to do is not the same as everything failing."""
    assert not AcquisitionTally().is_silent_outage


def test_one_resolution_clears_the_outage_condition():
    tally = AcquisitionTally()
    tally.record("fetch_unavailable")
    tally.record("body_inline")
    assert not tally.is_silent_outage


def test_rejections_are_attempts_that_resolved_nothing_and_still_flag_an_outage():
    """A tier whose every body was a login wall is broken, not merely unlucky."""
    tally = AcquisitionTally()
    for _ in range(9):
        tally.record("rejected_login_wall")
    assert tally.attempted == 9
    assert tally.resolved == 0
    assert tally.is_silent_outage


def test_a_dangling_group_link_alone_is_seen_not_attempted_and_is_not_an_outage():
    """T220: a group link whose target is gone hides records the lane never saw, so nothing was
    attempted for them. Like `not_attemptable` it stays off the attempt side: a run whose only
    tally entries are dangling group links is not a SILENT OUTAGE, and the next run re-reads
    the link once the refresher finishes."""
    tally = AcquisitionTally()
    for _ in range(3):
        tally.record("dangling_group_link")
    assert tally.counts["dangling_group_link"] == 3
    assert tally.resolved == 0
    assert not tally.is_silent_outage


def test_a_dangling_group_link_leaves_attempted_unchanged():
    """T220: one broken group link adds a GROUP to the tally, never a record, so the record count
    `lanes[].attempted` publishes does not move."""
    tally = AcquisitionTally()
    tally.record("body_inline")
    tally.record("fetch_gone")
    before = tally.attempted
    tally.record("dangling_group_link")
    assert tally.attempted == before == 2


def test_a_dangling_group_link_beside_a_failed_fetch_is_still_an_outage():
    """The other half of the pair: a broken group link neither raises the alert nor masks one. A
    fetch that failed with nothing resolved is still a SILENT OUTAGE."""
    tally = AcquisitionTally()
    tally.record("dangling_group_link")
    tally.record("fetch_unavailable")
    assert tally.resolved == 0
    assert tally.is_silent_outage


def test_an_unreadable_group_leaves_attempted_unchanged_and_alone_is_not_an_outage():
    """T238: a group that cannot be listed adds a GROUP, never a record, so the record count does
    not move, and a run whose only entry is one is not a SILENT OUTAGE -- nothing was attempted."""
    tally = AcquisitionTally()
    tally.record("unreadable_group")
    assert tally.attempted == 0
    assert not tally.is_silent_outage
    tally.record("body_inline")
    tally.record("fetch_gone")
    before = tally.attempted
    tally.record("unreadable_group")
    assert tally.attempted == before == 2
    assert tally.counts["unreadable_group"] == 2


def test_an_unreadable_group_beside_a_failed_fetch_is_still_an_outage():
    """The other half of the pair: the group count must not mask a real failure beside it."""
    tally = AcquisitionTally()
    tally.record("unreadable_group")
    tally.record("fetch_unavailable")
    assert tally.is_silent_outage
