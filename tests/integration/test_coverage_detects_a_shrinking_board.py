"""Task 9: a behaviour test this branch did not author code against.

Every test on this branch so far was written alongside the code it checks, so each one agrees
with its author. This one asserts an end-to-end behaviour nobody wrote code against: when a
board's stated total rises and our holdings do not, coverage must FALL. If it cannot fall, the
whole instrument is decorative — a metric that has only ever seen agreement has not been shown
to detect disagreement.

Exercises the real `load_board_coverage` against a real SQLite engine and feeds its real
output to the real `build_report` — neither is mocked. Mocking the thing under test is how a
test like this becomes decorative too.
"""

from __future__ import annotations

from boardwatch.reports.board_coverage import build_report
from boardwatch.store.coverage_queries import load_board_coverage


def test_coverage_falls_when_a_board_grows_and_we_do_not(store_conn, board_factory) -> None:
    """The instrument must be able to REPORT A LOSS. A metric that only ever prints 100% has
    not been shown to detect anything."""
    board = board_factory(provider="workday", name="Citi")
    board.scan(run_id=1, status="partial", board_reported_total=1000,
               board_enumerated=1000, detail_deferred=400, held=600)
    before = build_report(load_board_coverage(store_conn, run_id=1))

    board.scan(run_id=2, status="partial", board_reported_total=4589,
               board_enumerated=2214, detail_deferred=1614, held=600)
    after = build_report(load_board_coverage(store_conn, run_id=2))

    assert before.global_ratio == 0.6
    assert after.global_ratio < before.global_ratio
    assert after.boards[0].shortfall == 3989


def test_a_board_that_goes_dark_does_not_read_as_full_coverage(store_conn, board_factory) -> None:
    board = board_factory(provider="workday", name="Snowflake")
    board.scan(run_id=1, status="failed", board_reported_total=None,
               board_enumerated=None, detail_deferred=None, held=0)
    report = build_report(load_board_coverage(store_conn, run_id=1))
    assert report.bucket_counts["dark"] == 1
    assert report.global_ratio is None
    assert report.corpus_boards == 1
