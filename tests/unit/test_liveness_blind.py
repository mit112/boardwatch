"""The liveness-blindness detector: an `unknown` share that means the prober, not the corpus.

Every test that expects the detector to FIRE names, inline, the wrong version it rejects, so
none of them pass vacuously. The two boundary tests exist because both guards are one
character from a mutant that still passes the obvious cases: `<` vs `<=` on the denominator,
and `<` vs `<=` on the rate.

`test_no_clean_run_on_record_fires` is the important one. This repo has already had two revert
triggers fire on runs where nothing had changed, and the lesson drawn was to test a threshold
against runs that were fine. It is parametrised over every distinct liveness triple in the
per-run funnel artifacts of the 65 instrumented runs on record — the whole observed population,
not a sample — which is what makes it a claim about clean runs rather than about nine of them.
"""

from __future__ import annotations

import pytest

from boardwatch.notify.liveness_blind import (
    LIVENESS_BLIND_RATE,
    LIVENESS_MIN_CHECKED,
    check_liveness_blind,
)


def test_fires_when_every_probe_came_back_unknown() -> None:
    # The failure this closes: egress gone, so nothing answered and `dead` fell to zero.
    # Rejects any version that cannot fire at all.
    alert = check_liveness_blind(40, 40, 0)
    assert alert is not None
    assert "40 of 40" in alert
    assert "100%" in alert


def test_silent_when_the_unknown_share_is_below_the_rate() -> None:
    # 29 of 40 is 0.725. Rejects a version that fires on any elevated share.
    assert check_liveness_blind(40, 29, 0) is None


def test_fires_exactly_at_the_rate() -> None:
    # 30 of 40 is exactly 0.75. Rejects `share <= rate: return None`, which would go silent here
    # while `test_silent_when_the_unknown_share_is_below_the_rate` above stayed green.
    assert check_liveness_blind(40, 30, 0) is not None


def test_silent_when_the_prober_reached_a_gone_posting() -> None:
    # 9 of 10 unknown clears the rate, but one definitive gone-status proves the prober got out
    # to a board, so the egress is not broken and this is a bad afternoon on one provider.
    # Rejects dropping the `dead == 0` conjunct — the half of the signal that makes it a signal.
    assert check_liveness_blind(10, 9, 1) is None


def test_abstains_below_the_minimum_denominator() -> None:
    # Every probe unknown, but on a shortlist of nine. Rejects a version without the denominator
    # guard, which would let a hand-run `--top 5` with two timeouts report an egress break.
    assert check_liveness_blind(9, 9, 0) is None


def test_judges_at_exactly_the_minimum_denominator() -> None:
    # Rejects `checked <= min_checked: return None`, which would blind the detector at the
    # shortlist size the pipeline spent most of August running at.
    assert check_liveness_blind(10, 10, 0) is not None


def test_abstains_when_the_shortlist_was_never_probed() -> None:
    # `liveness_prober=None` leaves all three counts None. Unmeasured is not zero (D-022/D-023).
    # Rejects a version that coerces None to 0: it would divide by zero, or report a clean
    # liveness result for a run that never took one.
    assert check_liveness_blind(None, None, None) is None
    assert check_liveness_blind(40, None, 0) is None
    assert check_liveness_blind(40, 40, None) is None


@pytest.mark.parametrize(
    ("checked", "unknown", "dead"),
    [
        (8, 3, 0),  # run 63 — the highest unknown share on record, 0.375
        (8, 1, 0),
        (8, 0, 0),
        (10, 2, 0),  # run 110 — the worst clean run at the `--top 10` cap, 0.20
        (10, 1, 0),
        (10, 0, 0),
        (40, 3, 0),  # run 68 — the worst clean run at the `--top 40` cap, 0.075
        (40, 2, 0),  # run 71
        (40, 1, 0),  # runs 69 and 131 — the most recent unattended run
    ],
)
def test_no_clean_run_on_record_fires(checked: int, unknown: int, dead: int) -> None:
    """Every distinct `(checked, unknown, dead)` triple on record — all nine, read off the funnel
    artifacts of the 65 instrumented runs to date, so this is the whole observed population and
    not a sample of it. A threshold that fires on any of these is a threshold that would page the
    owner on a night when nothing was wrong."""
    assert check_liveness_blind(checked, unknown, dead) is None


def test_default_thresholds_are_pinned() -> None:
    # Literals on both sides, and the behavioural pin is taken WITHOUT passing the keywords, so
    # this cannot be satisfied by a mutant that moves the constant and the call site together.
    assert LIVENESS_BLIND_RATE == 0.75
    assert LIVENESS_MIN_CHECKED == 10
    assert check_liveness_blind(10, 8, 0) is not None  # 0.80
    assert check_liveness_blind(10, 7, 0) is None  # 0.70
    assert check_liveness_blind(9, 9, 0) is None
