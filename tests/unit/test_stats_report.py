from datetime import timedelta

from boardwatch.core.clock import utcnow
from boardwatch.reports.stats import PostingStat, summarize

NOW = utcnow()
OLD = NOW - timedelta(days=30)


def _p(pid, passes, verdict, posted_at=NOW):
    return PostingStat(posting_id=pid, posted_at=posted_at, passes_filters=passes, verdict=verdict)


def test_window_partition_is_disjoint_and_keeps_unevaluated_separate():
    stats = [
        _p(1, True, "eligible"),
        _p(2, True, "uncertain"),
        _p(3, True, "ineligible"),
        _p(4, True, None),           # unevaluated — must NOT count as qualified
        _p(5, False, "eligible"),    # fails filters — excluded from the window partition
        _p(6, True, "eligible", OLD),  # outside the 7-day window
    ]
    r = summarize(stats, now=NOW, window_days=7, seen=6, tracked=0)
    assert (r.qualified, r.uncertain, r.ineligible, r.unevaluated) == (1, 1, 1, 1)


def test_pipeline_stages_span_all_open_not_just_window():
    stats = [
        _p(1, True, "eligible", OLD),   # old but passes filters + not ineligible
        _p(2, True, "ineligible"),
        _p(3, False, None),
    ]
    r = summarize(stats, now=NOW, window_days=7, seen=3, tracked=2)
    assert (r.seen, r.passes_filters, r.not_ineligible, r.tracked) == (3, 2, 1, 2)


def test_posted_at_none_is_excluded_from_window_but_counts_in_pipeline():
    stats = [_p(1, True, "eligible", None)]
    r = summarize(stats, now=NOW, window_days=7, seen=1, tracked=0)
    assert r.qualified == 0
    assert r.passes_filters == 1


def test_window_boundary_is_inclusive():
    stats = [_p(1, True, "eligible", NOW - timedelta(days=7))]
    r = summarize(stats, now=NOW, window_days=7, seen=1, tracked=0)
    assert r.qualified == 1
