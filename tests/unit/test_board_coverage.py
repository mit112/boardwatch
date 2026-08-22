"""Per-board discovery coverage as a five-bucket partition (D-271).

The test that matters most here is the unfailable-ratio guard: lever/ashby/workable state no
total at all, so the only "total" available for them is our own array length. A ratio of
held / held is 1.0 on every run for every board forever, and can never detect a leak. Those
boards get `enumerated_only` with `ratio is None`, never `1.0`.
"""

from __future__ import annotations

import pytest

from boardwatch.reports.board_coverage import (
    BoardCoverage,
    ContradictoryCoverage,
    build_report,
    classify_board,
)


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


def test_classify_board_returns_measured_when_total_is_known() -> None:
    """Fix round 1, finding 1: every other test in this suite constructs `measured`
    BoardCoverage instances directly, so nothing ever called classify_board with inputs that
    should yield "measured" — deleting the final `return "measured"` (or falling through to
    `enumerated_only`) would red nothing without this test."""
    for status in ("complete", "partial"):
        assert classify_board(status=status, board_reported_total=740,
                              board_enumerated=740, held=600, censored=False) == "measured"


def test_global_ratio_is_none_for_an_empty_report() -> None:
    """Fix round 1, finding 2: the module docstring states global_ratio is None when nothing
    is measurable, but no test ever called build_report([]) or with zero measured boards."""
    rep = build_report([])
    assert rep.global_ratio is None
    assert rep.corpus_boards == 0


def test_global_ratio_is_none_with_no_measured_boards() -> None:
    """The one existing "unmeasurable" test mixes a measured board in, so global_ratio was
    never actually asserted to be None — only pytest.approx'd against a real ratio."""
    rep = build_report([
        BoardCoverage(company_id=1, name="Snowflake", provider="workday", bucket="dark",
                      held=0, board_reported_total=None, board_enumerated=None,
                      detail_deferred=None, shortfall=None, ratio=None),
        BoardCoverage(company_id=2, name="Peloton", provider="workday", bucket="stale",
                      held=430, board_reported_total=None, board_enumerated=None,
                      detail_deferred=None, shortfall=None, ratio=None),
    ])
    assert rep.global_ratio is None
    assert rep.corpus_boards == 2


def test_measured_board_with_ratio_and_total_constructs_cleanly() -> None:
    """Fix round 1, finding 3, the valid direction."""
    BoardCoverage(company_id=1, name="Adobe", provider="workday", bucket="measured",
                  held=600, board_reported_total=740, board_enumerated=740,
                  detail_deferred=140, shortfall=140, ratio=600 / 740)


def test_enumerated_only_board_with_ratio_1_0_is_a_construction_bug() -> None:
    """Fix round 1, finding 3, the inconsistent direction: precedent is
    `Liveness.__post_init__` (core/liveness.py:127-146) raising `ContradictoryLiveness` for an
    inconsistent verdict/signal pair. `bucket="enumerated_only"` with `ratio=1.0` is exactly the
    unfailable-ratio trap this module exists to prevent, and build_report filters only on
    `bucket` — it never inspects `ratio` — so this must be caught at construction."""
    with pytest.raises(ContradictoryCoverage):
        BoardCoverage(company_id=1, name="Lever Co", provider="lever", bucket="enumerated_only",
                      held=120, board_reported_total=None, board_enumerated=120,
                      detail_deferred=0, shortfall=None, ratio=1.0)


def test_measured_board_missing_a_ratio_is_a_construction_bug() -> None:
    """Also covers fix round 2's "tightened case still raises" requirement: a positive stated
    total with no ratio is still a construction bug after the zero-total relaxation below."""
    with pytest.raises(ContradictoryCoverage):
        BoardCoverage(company_id=1, name="Adobe", provider="workday", bucket="measured",
                      held=600, board_reported_total=740, board_enumerated=740,
                      detail_deferred=140, shortfall=140, ratio=None)


def test_measured_board_missing_a_total_is_a_construction_bug() -> None:
    with pytest.raises(ContradictoryCoverage):
        BoardCoverage(company_id=1, name="Adobe", provider="workday", bucket="measured",
                      held=600, board_reported_total=None, board_enumerated=740,
                      detail_deferred=140, shortfall=140, ratio=0.81)


def test_a_zero_stated_total_does_not_inflate_the_global_ratio() -> None:
    """Fix round 1, finding 4: a board stating total==0 makes a real claim ("nothing open")
    and stays `measured`, but must never contribute a numerator with no denominator. Without
    the fix, 500/1000 held elsewhere plus 5 held against a stated total of 0 silently becomes
    505/1000 = 50.5% instead of the correct 50.0%."""
    rep = build_report([
        BoardCoverage(company_id=1, name="A", provider="workday", bucket="measured",
                      held=500, board_reported_total=1000, board_enumerated=1000,
                      detail_deferred=500, shortfall=500, ratio=500 / 1000),
        BoardCoverage(company_id=2, name="B", provider="workday", bucket="measured",
                      held=5, board_reported_total=0, board_enumerated=0,
                      detail_deferred=0, shortfall=-5, ratio=None),
    ])
    assert rep.global_ratio == pytest.approx(0.5)
    assert rep.measured_zero_total == 1


def test_measured_board_with_zero_total_accepts_no_ratio() -> None:
    """Fix round 2: the ratio for a zero-stated-total board is genuinely undefined — no real
    number answers "held against a claimed total of zero" — so `ratio=None` is the right word
    for it, the same word the four non-measured buckets already use for "no claim". `inf` was
    rejected: it is not valid JSON (RFC 8259) and the next task emits `--json`."""
    BoardCoverage(company_id=1, name="B", provider="workday", bucket="measured",
                  held=5, board_reported_total=0, board_enumerated=0,
                  detail_deferred=0, shortfall=-5, ratio=None)
