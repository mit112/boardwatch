"""Gate P6's duplicate-leakage rate (`reports/leakage.py`): pure aggregation, no DB.

Every expected number below is written as a hand-computed literal, not re-derived by
calling `len(set(...))` the way the implementation does — the point of a "second path" is
that a bug in `compute_leakage`'s own arithmetic cannot also be baked into the test's
expectation.
"""

from datetime import timedelta

from boardwatch.core.clock import utcnow
from boardwatch.reports.leakage import CandidateGroup, compute_leakage
from boardwatch.store.identity_queries import SurfacedJob

NOW = utcnow()
OLD = NOW - timedelta(days=30)


def _j(job_id: int, identity_key: str | None, first_decided_at=NOW) -> SurfacedJob:
    return SurfacedJob(job_id=job_id, first_decided_at=first_decided_at, identity_key=identity_key)


def test_zero_collisions_reports_zero_percent_with_a_stated_denominator():
    """Two jobs, two different exact_quad keys: nothing redundant, and the report says so
    with a denominator, not a bare "0%"."""
    jobs = [_j(1, "quad-a"), _j(2, "quad-b")]
    report = compute_leakage(jobs, candidates=(), now=NOW, window_days=7)
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
    report = compute_leakage(jobs, candidates=(), now=NOW, window_days=7)
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
    report = compute_leakage(jobs, candidates=(), now=NOW, window_days=7)
    assert report.identified == 1
    assert report.distinct_groups == 1
    assert report.redundant == 0
    assert report.rate == 0.0


def test_unidentified_jobs_are_their_own_bucket_never_folded_in():
    """A body-less posting's job has no exact_quad identity at all. It must show up in
    `unidentified`, and NOT be silently added to either `identified` or `distinct_groups`
    (folding a bucket into a neighbour is a defect, not a simplification)."""
    jobs = [_j(1, "quad-a"), _j(2, None), _j(3, None)]
    report = compute_leakage(jobs, candidates=(), now=NOW, window_days=7)
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
    report = compute_leakage(jobs, candidates=(), now=NOW, window_days=7)
    assert report.identified == 0
    assert report.rate is None


def test_an_empty_window_is_also_not_measurable():
    jobs: list[SurfacedJob] = []
    report = compute_leakage(jobs, candidates=(), now=NOW, window_days=7)
    assert report.surfaced_total == 0
    assert report.rate is None


def test_a_job_outside_the_window_is_excluded_entirely():
    """First reached leads 30 days ago: outside a 7-day window, it must not appear in ANY
    bucket — not surfaced_total, not unidentified, not identified."""
    jobs = [_j(1, "quad-a", first_decided_at=OLD), _j(2, "quad-a")]
    report = compute_leakage(jobs, candidates=(), now=NOW, window_days=7)
    assert report.surfaced_total == 1
    assert report.identified == 1
    assert report.redundant == 0


def test_window_boundary_is_inclusive():
    jobs = [_j(1, "quad-a", first_decided_at=NOW - timedelta(days=7))]
    report = compute_leakage(jobs, candidates=(), now=NOW, window_days=7)
    assert report.surfaced_total == 1


# --- the candidate near-duplicate bound (company_title_location) -----------------------
#
# A separate bucket, never folded into `identified`, `distinct_groups` or `rate`. It is an
# UPPER BOUND: on 2026-08-27 it read 7 redundant of 611 (1.15%) against a hand-adjudicated
# truth of 3 (0.49%), and 66.7% of the corpus-wide class is genuinely distinct jobs
# (FINDINGS.md). Every test below therefore checks that the bound can only be too HIGH.


def _c(identity_key: str, *jobs: SurfacedJob, distinguished: tuple[str, ...] = ()) -> CandidateGroup:
    return CandidateGroup(identity_key=identity_key, jobs=jobs, distinguished=distinguished)


def test_the_candidate_bucket_is_never_folded_into_the_exact_quad_rate():
    """The whole point of the change: a ctl-only redundancy is now VISIBLE, and the gate's
    own number is unmoved by it. Before this, `identity_queries` hardcoded `exact_quad` and
    the class could not be seen at all."""
    jobs = [_j(1, "quad-a"), _j(2, "quad-b")]
    candidates = (_c("ctl-x", _j(1, "ctl-x"), _j(2, "ctl-x")),)
    report = compute_leakage(jobs, candidates=candidates, now=NOW, window_days=7)
    # The gate clause is untouched.
    assert report.redundant == 0
    assert report.rate == 0.0
    assert report.distinct_groups == 2
    # And the wider class is reported beside it, not inside it.
    assert report.candidate_kind == "company_title_location"
    assert report.candidate_identified == 2
    assert report.candidate_groups == 1
    assert report.candidate_redundant == 1
    assert report.candidate_rate == 1 / 2


def test_a_candidate_group_with_proof_of_distinctness_leaves_the_bound():
    """Two Affirm postings under one title and one location, with disjoint pay bands and
    disjoint years floors. Proven distinct, so they are not a near-duplicate — and the
    removal is REPORTED, not silent."""
    jobs = [_j(1, "quad-a"), _j(2, "quad-b")]
    candidates = (
        _c(
            "ctl-x",
            _j(1, "ctl-x"),
            _j(2, "ctl-x"),
            distinguished=("salary_band", "experience_years"),
        ),
    )
    report = compute_leakage(jobs, candidates=candidates, now=NOW, window_days=7)
    assert report.candidate_identified == 2
    assert report.candidate_groups == 2
    assert report.candidate_redundant == 0
    assert report.candidate_distinguished == 1


def test_a_partially_distinguished_group_stays_whole():
    """Three jobs, and only SOME pairs carry proof. The veto is the only thing that can
    shrink the bound, so it fires on the whole group or not at all — a partial split would
    let an unproven pair out of the bound and the number would stop being an upper bound."""
    jobs = [_j(1, "quad-a"), _j(2, "quad-b"), _j(3, "quad-c")]
    candidates = (_c("ctl-x", _j(1, "ctl-x"), _j(2, "ctl-x"), _j(3, "ctl-x")),)
    report = compute_leakage(jobs, candidates=candidates, now=NOW, window_days=7)
    assert report.candidate_identified == 3
    assert report.candidate_groups == 1
    assert report.candidate_redundant == 2
    assert report.candidate_distinguished == 0


def test_a_singleton_candidate_group_is_in_the_denominator_but_not_the_numerator():
    """One job is the only one under its ctl key: it is measurable and unique, so it belongs
    in the denominator. Dropping it would inflate the rate."""
    jobs = [_j(1, "quad-a"), _j(2, "quad-b"), _j(3, "quad-c")]
    candidates = (
        _c("ctl-x", _j(1, "ctl-x"), _j(2, "ctl-x")),
        _c("ctl-y", _j(3, "ctl-y")),
    )
    report = compute_leakage(jobs, candidates=candidates, now=NOW, window_days=7)
    assert report.candidate_identified == 3
    assert report.candidate_groups == 2
    assert report.candidate_redundant == 1
    assert report.candidate_rate == 1 / 3


def test_the_candidate_window_uses_the_same_cutoff_as_the_gate_clause():
    """Both halves anchor on `first_decided_at`. A candidate job outside the window must
    leave every candidate bucket, exactly as it leaves every exact_quad bucket."""
    jobs = [_j(1, "quad-a", first_decided_at=OLD), _j(2, "quad-b")]
    candidates = (_c("ctl-x", _j(1, "ctl-x", first_decided_at=OLD), _j(2, "ctl-x")),)
    report = compute_leakage(jobs, candidates=candidates, now=NOW, window_days=7)
    assert report.surfaced_total == 1
    assert report.candidate_identified == 1
    assert report.candidate_groups == 1
    assert report.candidate_redundant == 0


def test_no_candidate_identities_reports_none_not_zero_percent():
    """Same rule as the gate clause: nothing measurable is "not measurable", never 0%."""
    jobs = [_j(1, "quad-a")]
    report = compute_leakage(jobs, candidates=(), now=NOW, window_days=7)
    assert report.candidate_identified == 0
    assert report.candidate_rate is None


def test_a_job_under_two_candidate_keys_inflates_the_numerator_not_the_denominator():
    """`load_surfaced_keys` returns one row per key on purpose, so an ambiguous job appears in
    two groups. It must still be ONE job in the denominator: counting it twice would DILUTE
    the rate, and the bound is only allowed to be wrong upwards.

    Job 1 holds two keys — one shared with job 2, one of its own. There is exactly one
    redundant surfacing (jobs 1 and 2 said the same thing) among two distinct jobs."""
    jobs = [_j(1, "quad-a"), _j(2, "quad-b")]
    candidates = (
        _c("ctl-x", _j(1, "ctl-x"), _j(2, "ctl-x")),
        _c("ctl-y", _j(1, "ctl-y")),
    )
    report = compute_leakage(jobs, candidates=candidates, now=NOW, window_days=7)
    assert report.candidate_identified == 2
    assert report.candidate_redundant == 1
    assert report.candidate_rate == 1 / 2


def test_a_job_alone_under_two_keys_is_never_negative_redundancy():
    """The arithmetic must be group-local. `identified - groups` would read -1 here."""
    jobs = [_j(1, "quad-a")]
    candidates = (_c("ctl-x", _j(1, "ctl-x")), _c("ctl-y", _j(1, "ctl-y")))
    report = compute_leakage(jobs, candidates=candidates, now=NOW, window_days=7)
    assert report.candidate_identified == 1
    assert report.candidate_redundant == 0
    assert report.candidate_rate == 0.0


def test_the_candidate_bound_is_never_lower_than_the_exact_quad_rate():
    """Structural: every exact_quad group is a subset of a ctl group (the key is a prefix of
    the quad tuple), so an exact_quad redundancy is always also a candidate redundancy. If
    this ever inverts, one of the two halves is wrong."""
    jobs = [_j(1, "quad-x"), _j(2, "quad-x"), _j(3, "quad-y")]
    candidates = (
        _c("ctl-x", _j(1, "ctl-x"), _j(2, "ctl-x")),
        _c("ctl-y", _j(3, "ctl-y")),
    )
    report = compute_leakage(jobs, candidates=candidates, now=NOW, window_days=7)
    assert report.rate is not None and report.candidate_rate is not None
    assert report.candidate_rate >= report.rate
