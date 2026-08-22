"""Per-board discovery coverage as a five-bucket partition (D-271).

The test that matters most here is the unfailable-ratio guard: lever/ashby/workable state no
total at all, so the only "total" available for them is our own array length. A ratio of
held / held is 1.0 on every run for every board forever, and can never detect a leak. Those
boards get `enumerated_only` with `ratio is None`, never `1.0`.
"""

from __future__ import annotations

import pytest

from boardwatch.reports.board_coverage import BoardCoverage, build_report, classify_board


def test_a_board_with_no_stated_total_never_gets_a_ratio() -> None:
    """THE unfailable-ratio guard. lever/ashby/workable state no total, so held/held == 1.0
    would be true on every run for every board and could never detect a leak."""
    assert classify_board(status="complete", board_reported_total=None,
                          board_enumerated=120, held=120, censored=False) == "enumerated_only"


def test_censored_board_is_its_own_bucket() -> None:
    assert classify_board(status="partial", board_reported_total=4589,
                          board_enumerated=2214, held=600, censored=True) == "censored"


def test_failed_board_is_dark_not_zero_coverage() -> None:
    assert classify_board(status="failed", board_reported_total=None,
                          board_enumerated=None, held=0, censored=False) == "dark"


def test_unchanged_board_is_stale_not_measured() -> None:
    assert classify_board(status="unchanged", board_reported_total=None,
                          board_enumerated=None, held=430, censored=False) == "stale"


def test_measured_board_gets_a_ratio_and_an_absolute_shortfall() -> None:
    rep = build_report([
        BoardCoverage(company_id=1, name="Adobe", provider="workday", bucket="measured",
                      held=600, board_reported_total=740, board_enumerated=740,
                      detail_deferred=140, shortfall=140, ratio=600 / 740),
    ])
    assert rep.bucket_counts["measured"] == 1
    assert rep.global_ratio == pytest.approx(600 / 740)
    assert rep.boards[0].shortfall == 140


def test_global_ratio_ignores_unmeasurable_boards_but_still_counts_them() -> None:
    """A dark board must not be averaged in as 100%, and must not vanish from the denominator."""
    rep = build_report([
        BoardCoverage(company_id=1, name="Adobe", provider="workday", bucket="measured",
                      held=600, board_reported_total=740, board_enumerated=740,
                      detail_deferred=140, shortfall=140, ratio=600 / 740),
        BoardCoverage(company_id=2, name="Snowflake", provider="workday", bucket="dark",
                      held=0, board_reported_total=None, board_enumerated=None,
                      detail_deferred=None, shortfall=None, ratio=None),
    ])
    assert rep.global_ratio == pytest.approx(600 / 740)
    assert rep.corpus_boards == 2
    assert rep.bucket_counts["dark"] == 1


def test_over_full_coverage_is_reported_not_clamped() -> None:
    """Measured live: Regeneron 101.4%, Fidelity 106.2%. We hold postings the board dropped,
    because a permanently `partial` board never runs _process_missing. Clamping to 1.0 would
    hide the defect."""
    rep = build_report([
        BoardCoverage(company_id=3, name="Fidelity", provider="workday", bucket="measured",
                      held=600, board_reported_total=565, board_enumerated=565,
                      detail_deferred=104, shortfall=-35, ratio=600 / 565),
    ])
    assert rep.global_ratio > 1.0
