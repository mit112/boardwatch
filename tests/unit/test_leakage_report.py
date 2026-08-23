"""Gate P6's duplicate-leakage rate (`reports/leakage.py`): pure aggregation, no DB.

Every expected number below is written as a hand-computed literal, not re-derived by
calling `len(set(...))` the way the implementation does — the point of a "second path" is
that a bug in `compute_leakage`'s own arithmetic cannot also be baked into the test's
expectation.
"""

from datetime import timedelta

from boardwatch.core.clock import utcnow
from boardwatch.reports.leakage import compute_leakage
from boardwatch.store.identity_queries import SurfacedJob

NOW = utcnow()
OLD = NOW - timedelta(days=30)


def _j(job_id: int, identity_key: str | None, first_decided_at=NOW) -> SurfacedJob:
    return SurfacedJob(job_id=job_id, first_decided_at=first_decided_at, identity_key=identity_key)


def test_zero_collisions_reports_zero_percent_with_a_stated_denominator():
    """Two jobs, two different exact_quad keys: nothing redundant, and the report says so
    with a denominator, not a bare "0%"."""
    jobs = [_j(1, "quad-a"), _j(2, "quad-b")]
    report = compute_leakage(jobs, now=NOW, window_days=7)
    assert report.identified == 2
    assert report.distinct_groups == 2
    assert report.redundant == 0
    assert report.rate == 0.0
    assert report.window_days == 7
    assert report.unidentified == 0


def test_a_real_collision_is_counted_once_per_extra_job():
    """Three jobs share one identity, a fourth is unique: 3 surfacings of one thing is 2
    REDUNDANT surfacings, not 3 — the rate is over how many extra jobs said the same thing.
    """
    jobs = [_j(1, "quad-x"), _j(2, "quad-x"), _j(3, "quad-x"), _j(4, "quad-y")]
    report = compute_leakage(jobs, now=NOW, window_days=7)
    # Hand count, not the implementation's set(): {quad-x, quad-y} -> 2 groups; 4 identified
    # jobs minus 2 groups leaves 2 redundant.
    assert report.identified == 4
    assert report.distinct_groups == 2
    assert report.redundant == 2
    assert report.rate == 2 / 4


def test_a_suppressed_duplicate_that_never_reached_a_second_job_is_not_leakage():
    """Only ONE job for the identity ever reached `job_dispositions` — the ranker's dedup (or
    `identities regroup`) already merged the would-be duplicate onto this one job before it
    could surface a second time. That must read as zero leakage, not as "1 posting, 1
    group, therefore fine by luck" — there is nothing here to even LOOK like a collision.
    """
    jobs = [_j(1, "quad-z")]
    report = compute_leakage(jobs, now=NOW, window_days=7)
    assert report.identified == 1
    assert report.distinct_groups == 1
    assert report.redundant == 0
    assert report.rate == 0.0


def test_unidentified_jobs_are_their_own_bucket_never_folded_in():
    """A body-less posting's job has no exact_quad identity at all. It must show up in
    `unidentified`, and NOT be silently added to either `identified` or `distinct_groups`
    (folding a bucket into a neighbour is a defect, not a simplification)."""
    jobs = [_j(1, "quad-a"), _j(2, None), _j(3, None)]
    report = compute_leakage(jobs, now=NOW, window_days=7)
    assert report.surfaced_total == 3
    assert report.unidentified == 2
    assert report.identified == 1
    assert report.distinct_groups == 1
    assert report.redundant == 0
    # The unidentified jobs must not have inflated the denominator.
    assert report.identified + report.unidentified == report.surfaced_total


def test_nothing_measurable_reports_none_not_a_percentage():
    """Every surfaced job in the window is unidentified: the rate is UNDEFINED, not 0%."""
    jobs = [_j(1, None), _j(2, None)]
    report = compute_leakage(jobs, now=NOW, window_days=7)
    assert report.identified == 0
    assert report.rate is None


def test_an_empty_window_is_also_not_measurable():
    jobs: list[SurfacedJob] = []
    report = compute_leakage(jobs, now=NOW, window_days=7)
    assert report.surfaced_total == 0
    assert report.rate is None


def test_a_job_outside_the_window_is_excluded_entirely():
    """First reached leads 30 days ago: outside a 7-day window, it must not appear in ANY
    bucket — not surfaced_total, not unidentified, not identified."""
    jobs = [_j(1, "quad-a", first_decided_at=OLD), _j(2, "quad-a")]
    report = compute_leakage(jobs, now=NOW, window_days=7)
    assert report.surfaced_total == 1
    assert report.identified == 1
    assert report.redundant == 0


def test_window_boundary_is_inclusive():
    jobs = [_j(1, "quad-a", first_decided_at=NOW - timedelta(days=7))]
    report = compute_leakage(jobs, now=NOW, window_days=7)
    assert report.surfaced_total == 1
