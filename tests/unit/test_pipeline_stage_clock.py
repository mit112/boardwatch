"""`_StageClock` — the pipeline's own stage timer.

The integration test in `tests/pipeline/test_pipeline_run.py` proves the marks reach the
artifact in run order and do not exceed the run. It does NOT pin the numbers: a `mark` that
recorded a fixed positive epsilon for every stage satisfies it, and so does one that never
advances its cursor and therefore reports cumulative times as if they were per-stage. Both
produce a table that looks like a plausible cost breakdown and is not one.

Every assertion here is one-sided or an invariant, never a threshold on how long something
took: `sleep` is a lower bound, and `sum <= elapsed` holds under any machine load. A timing
test with an upper bound on a duration is a load-dependent flake, and this repo already
carries one it refuses to weaken.
"""

from __future__ import annotations

from time import perf_counter, sleep

from boardwatch.pipeline.runner import _StageClock

_TICK = 0.05


def test_each_mark_is_charged_only_the_stage_BEHIND_it() -> None:  # noqa: N802
    """The whole contract. A clock that records the same epsilon for every stage, or that
    reports each mark's distance from the START of the run rather than from the previous mark,
    passes "the names are right and the total fits in the run" — and reports a breakdown in
    which no number means anything."""
    started = perf_counter()
    clock = _StageClock()
    sleep(_TICK)
    clock.mark("first")
    sleep(_TICK)
    clock.mark("second")
    elapsed = perf_counter() - started

    assert [stage.name for stage in clock.durations] == ["first", "second"]
    # Kills the fixed-epsilon clock: each stage really did sleep, and `sleep` cannot return early.
    assert all(stage.seconds >= _TICK * 0.8 for stage in clock.durations), clock.durations
    # Kills the clock that never advances its cursor: it would charge `second` with both sleeps,
    # so the rows would sum to ~1.5x the run. An invariant, not a threshold — true at any load.
    total = sum(stage.seconds for stage in clock.durations)
    assert total <= elapsed, f"the stages claim {total:.4f}s of a {elapsed:.4f}s window"


def test_an_unmarked_stage_is_charged_to_the_mark_that_FOLLOWS_it() -> None:  # noqa: N802
    """Why the pipeline marks boundaries instead of wrapping each stage: work that raised or
    returned before its own mark must still be paid for by somebody, or the rows stop summing
    to the run and an unaccounted block becomes invisible rather than visible."""
    started = perf_counter()
    clock = _StageClock()
    sleep(_TICK)  # a stage that never reached its mark
    sleep(_TICK)
    clock.mark("survivor")
    elapsed = perf_counter() - started

    assert len(clock.durations) == 1
    assert clock.durations[0].seconds >= _TICK * 1.6, "the unmarked stage was dropped"
    assert clock.durations[0].seconds <= elapsed


def test_a_clock_nobody_marked_reports_nothing_rather_than_a_zero_stage() -> None:
    """`()` is "timed, no boundary reached". A single zero-second row would be a stage nobody
    ran, which is the fabricated-measurement shape the funnel's `None`/`()` split exists for."""
    assert _StageClock().durations == []
