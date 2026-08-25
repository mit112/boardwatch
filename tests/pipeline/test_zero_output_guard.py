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
