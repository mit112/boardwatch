"""The B5 zero-output guard, rewritten to reason at run scope (design
`docs/superpowers/specs/2026-08-25-b5-run-scoped-rank-attribution-design.md`).

`test_guard_fires_on_mixed_day_with_some_handled` is the discriminating case: it must FAIL
against the OLD corpus-scoped guard body (which returns `None` whenever `hidden_handled != 0`,
regardless of magnitude) and PASS against the new arithmetic reconciliation. A test that cannot
tell the two apart is vacuous.
"""

from __future__ import annotations

import pytest

from boardwatch.pipeline.runner import ZeroOutputReconciliationError, _zero_output_guard


def test_guard_fires_on_mixed_day_with_some_handled() -> None:
    """J=5 judged this run; 2 honestly handled-this-run; 3 rejected/lost; 0 leads.

    The OLD guard fired only on `hidden_handled == 0` — a non-zero corpus-scoped
    `hidden_handled` (even 2, even far short of covering all 5) disarmed it entirely. The NEW
    guard reasons arithmetically: 2 of 5 explained leaves 3 unexplained, and it fires.
    """
    msg = _zero_output_guard(
        5, handled_this_run=2, applied_this_run=0, duplicate_this_run=0, dead_this_run=0
    )
    assert msg is not None
    assert "3 of 5" in msg


def test_guard_silent_when_all_this_run_candidates_suppressed() -> None:
    assert (
        _zero_output_guard(
            4, handled_this_run=1, applied_this_run=1, duplicate_this_run=1, dead_this_run=1
        )
        is None
    )


def test_guard_silent_on_steady_state_cache_hit_day() -> None:
    assert _zero_output_guard(0) is None


def test_guard_raises_on_reconciliation_miscount() -> None:
    with pytest.raises(ZeroOutputReconciliationError):
        _zero_output_guard(2, handled_this_run=3)


# --- T131: a valid final-gate rejection is an honest suppression -----------------------------


def test_a_slate_the_gate_validly_rejected_is_not_an_empty_day() -> None:
    """One new candidate, one gate `ineligible` carrying a quoted span, zero leads.

    Before T131 this produced a FALSE fatal — and withheld the heartbeat — on a run where the
    judge did exactly its job. The keystone forces such a verdict to quote the frozen JD, so it
    is the opposite of a filter silently eating the shortlist (D-246).
    """
    assert _zero_output_guard(1, gate_rejected_this_run=1) is None


def test_the_same_candidate_with_no_gate_rejection_still_fires() -> None:
    """The control for the test above. Without it, that assertion is satisfied by a guard that
    was simply deleted: same denominator, same zero leads, only the explainer removed."""
    msg = _zero_output_guard(1)
    assert msg is not None
    assert "1 of 1" in msg


def test_a_gate_rejection_explains_only_itself() -> None:
    """Five judged, two validly rejected, three vanished with no terminal reason: still fatal,
    and the count names the three rather than being disarmed by the presence of any rejection."""
    msg = _zero_output_guard(5, gate_rejected_this_run=2)
    assert msg is not None
    assert "3 of 5" in msg


def test_all_five_explainers_reconcile_to_zero() -> None:
    assert (
        _zero_output_guard(
            5,
            handled_this_run=1,
            applied_this_run=1,
            duplicate_this_run=1,
            dead_this_run=1,
            gate_rejected_this_run=1,
        )
        is None
    )


def test_an_over_counted_gate_rejection_raises_rather_than_clamping() -> None:
    """The failure mode the call site's intersection exists to prevent: a gate-excluded lead
    judged in a PRIOR run is not in the denominator, so subtracting the raw count underflows.
    The guard must raise rather than clamp, and the message must name the new term."""
    with pytest.raises(ZeroOutputReconciliationError) as excinfo:
        _zero_output_guard(1, gate_rejected_this_run=2)
    assert "+2)" in str(excinfo.value)
