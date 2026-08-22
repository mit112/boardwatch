"""Per-board discovery coverage as a seven-bucket partition (D-271, D-273).

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
    UnknownScanStatus,
    board_coverage_headline,
    board_coverage_table,
    board_coverage_to_dict,
    build_report,
    classify_board,
)


def test_a_board_with_no_stated_total_never_gets_a_ratio() -> None:
    """THE unfailable-ratio guard. lever/ashby/workable state no total, so held/held == 1.0
    would be true on every run for every board and could never detect a leak."""
    assert classify_board(status="complete", board_reported_total=None,
                          censored=False) == "enumerated_only"


def test_censored_board_is_its_own_bucket() -> None:
    assert classify_board(status="partial", board_reported_total=4589,
                          censored=True) == "censored"


def test_failed_board_is_dark_not_zero_coverage() -> None:
    assert classify_board(status="failed", board_reported_total=None,
                          censored=False) == "dark"


def test_unchanged_board_is_stale_not_measured() -> None:
    assert classify_board(status="unchanged", board_reported_total=None,
                          censored=False) == "stale"


def test_unscanned_board_is_its_own_bucket_not_dark() -> None:
    """Fix round 1, finding 1: `status=None` means no `board_scans` row exists for this board
    in the selected run at all — a different fact from `dark` (a row exists and it failed).
    Reproduced live: an INNER JOIN on board_scans dropped these boards from the corpus
    entirely instead of classifying them, which this bucket exists to make visible."""
    assert classify_board(status=None, board_reported_total=None,
                          censored=False) == "unscanned"


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
                              censored=False) == "measured"


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


def test_measured_board_with_negative_total_is_a_construction_bug() -> None:
    """Fix round 3: the zero-total relaxation's `else` branch caught `board_reported_total < 0`
    too, so a negative total (only ever a bad parse or a bad scrape) constructed successfully
    with any ratio, including None. Pins the boundary at exactly zero."""
    with pytest.raises(ContradictoryCoverage):
        BoardCoverage(company_id=1, name="Bad", provider="workday", bucket="measured",
                      held=5, board_reported_total=-3, board_enumerated=0,
                      detail_deferred=0, shortfall=None, ratio=None)


def test_an_out_of_catalog_scan_status_is_a_failure_not_a_silent_measured_board() -> None:
    """`board_scans.status` is a closed catalog of four values (store/tables.py's `status_enum`
    CheckConstraint, typed as core/models.SnapshotStatus). Anything else fell straight through
    the `failed`/`unchanged` checks and was treated as a good scan — an out-of-catalog value
    becoming a silent new bucket, which this repo's rules forbid. Both directions are asserted:
    every catalog value still classifies, so the guard cannot pass by rejecting everything."""
    with pytest.raises(UnknownScanStatus):
        classify_board(status="succeeded", board_reported_total=740, censored=False)
    with pytest.raises(UnknownScanStatus):
        classify_board(status="", board_reported_total=None, censored=False)
    for status in ("complete", "partial", "failed", "unchanged"):
        classify_board(status=status, board_reported_total=740, censored=False)


def test_a_zero_stated_total_with_a_ratio_is_a_construction_bug() -> None:
    """`ContradictoryCoverage`'s docstring says it closes the unfailable-ratio hole for every
    future caller. At exactly zero it did not: the zero-total branch accepted ANY ratio, so
    `total=0, ratio=0.7` constructed cleanly and published a number nothing supports. `None` is
    the only answer to "held against a claimed total of zero"; it is now required, not merely
    permitted (test_measured_board_with_zero_total_accepts_no_ratio is the valid direction)."""
    with pytest.raises(ContradictoryCoverage):
        BoardCoverage(company_id=1, name="B", provider="workday", bucket="measured",
                      held=5, board_reported_total=0, board_enumerated=0,
                      detail_deferred=0, shortfall=-5, ratio=0.7)


def test_a_censored_board_carries_a_shortfall_but_still_no_ratio() -> None:
    """Citi: 600 held against a facet-recovered 4,589. While `shortfall` was tied to `measured`
    the largest hole in the corpus reached no summary line. The RATIO stays withheld — a facet
    sum is a second aggregation path, and publishing a ratio from it is a bigger claim than
    §3.1 authorised."""
    board = BoardCoverage(company_id=1, name="Citi", provider="workday", bucket="censored",
                          held=600, board_reported_total=4589, board_enumerated=2214,
                          detail_deferred=1614, shortfall=3989, ratio=None)
    assert board.shortfall == 3989
    assert board.ratio is None


def test_a_censored_board_with_a_recovered_total_may_not_omit_its_shortfall() -> None:
    """The invariant is two-directional on purpose. Withholding the shortfall is exactly the
    defect above, so it must raise rather than under-report."""
    with pytest.raises(ContradictoryCoverage):
        BoardCoverage(company_id=1, name="Citi", provider="workday", bucket="censored",
                      held=600, board_reported_total=4589, board_enumerated=2214,
                      detail_deferred=1614, shortfall=None, ratio=None)


def test_a_bucket_with_no_stated_total_may_not_carry_a_shortfall() -> None:
    """The other direction: a shortfall is a gap FROM a stated total. `enumerated_only` has no
    total, so any number here would be a gap from our own array length — the unfailable
    arithmetic this module exists to refuse, wearing a different field name."""
    with pytest.raises(ContradictoryCoverage):
        BoardCoverage(company_id=1, name="Lever Co", provider="lever", bucket="enumerated_only",
                      held=120, board_reported_total=None, board_enumerated=120,
                      detail_deferred=0, shortfall=0, ratio=None)


def test_an_unreadable_board_publishes_neither_ratio_nor_shortfall() -> None:
    """The degradation target for a row that cannot be classified (store/coverage_queries.py).
    Its raw column values survive so the defect is debuggable, but it makes no coverage claim."""
    board = BoardCoverage(company_id=1, name="Bad", provider="greenhouse", bucket="unreadable",
                          held=42, board_reported_total=-5, board_enumerated=None,
                          detail_deferred=None, shortfall=None, ratio=None)
    assert (board.ratio, board.shortfall) == (None, None)
    assert board.board_reported_total == -5


def test_the_censored_shortfall_total_reaches_the_report() -> None:
    """The censored boards publish no ratio, so they contribute nothing to `global_ratio`; the
    footer total is the only place their gap can appear. Two censored boards sum, and the
    measured board's own shortfall must NOT leak into that sum."""
    rep = build_report([
        BoardCoverage(company_id=1, name="Citi", provider="workday", bucket="censored",
                      held=600, board_reported_total=4589, board_enumerated=2214,
                      detail_deferred=1614, shortfall=3989, ratio=None),
        BoardCoverage(company_id=2, name="NVIDIA", provider="workday", bucket="censored",
                      held=600, board_reported_total=2656, board_enumerated=2000,
                      detail_deferred=1511, shortfall=2056, ratio=None),
        BoardCoverage(company_id=3, name="Adobe", provider="workday", bucket="measured",
                      held=600, board_reported_total=740, board_enumerated=740,
                      detail_deferred=140, shortfall=140, ratio=600 / 740),
    ])
    assert rep.censored_shortfall == 3989 + 2056
    assert rep.bucket_counts["censored"] == 2


def test_censored_shortfall_is_none_not_zero_when_no_total_was_recovered() -> None:
    """A censored board whose facets yielded nothing states a FLOOR, not a total
    (workday.py:_uncapped_total returns `(None, True)`), so its gap is unknown. Zero would read
    as "no gap" — the same fold this partition exists to refuse."""
    rep = build_report([
        BoardCoverage(company_id=1, name="Opaque", provider="workday", bucket="censored",
                      held=600, board_reported_total=None, board_enumerated=2000,
                      detail_deferred=1400, shortfall=None, ratio=None),
    ])
    assert rep.censored_shortfall is None
    assert rep.bucket_counts["censored"] == 1


# --------------------------------------------------------------------------------------
# The reporting surfaces (D-274). The instrument was correct and mute; these pin what an
# unattended run actually says, which is the only part the operator ever reads.
# --------------------------------------------------------------------------------------


def _board(
    *,
    name: str = "Acme",
    bucket: str = "measured",
    held: int = 500,
    stated: int | None = 1000,
    ratio: float | None = 0.5,
    shortfall: int | None = 500,
    deferred: int | None = None,
) -> BoardCoverage:
    return BoardCoverage(
        company_id=1,
        name=name,
        provider="greenhouse",
        bucket=bucket,  # type: ignore[arg-type]
        held=held,
        board_reported_total=stated,
        board_enumerated=None,
        detail_deferred=deferred,
        shortfall=shortfall,
        ratio=ratio,
    )


def test_the_serializer_says_nothing_rather_than_zero_when_there_is_no_report() -> None:
    """`None`, never a zeroed block. A dict of zeros would claim every board was measured at
    nothing, which is the opposite of "we could not measure" — the same distinction the seven
    buckets exist to keep."""
    assert board_coverage_to_dict(None) is None


def test_the_serializer_carries_the_held_caveat_into_the_json() -> None:
    """`held` is a live count with no run dimension, so a section stamped into a per-run
    artifact is not a historical record. A machine consumer must be able to read that without
    parsing prose."""
    payload = board_coverage_to_dict(build_report([_board()]))

    assert payload is not None
    assert "no run dimension" in str(payload["note"])


def test_a_report_with_nothing_measurable_renders_not_measurable_never_zero_percent() -> None:
    """0% is a claim that boards were read and found empty. Not measurable is the honest word
    for a corpus where no board stated a total we can trust."""
    report = build_report(
        [_board(bucket="dark", stated=None, ratio=None, shortfall=None)]
    )

    rendered = "\n".join(board_coverage_headline(report))

    assert report.global_ratio is None
    assert "not measurable" in rendered
    assert "0.0%" not in rendered


def test_an_absent_report_reads_differently_from_an_unmeasurable_one() -> None:
    """Two different failures: we could not READ the columns, versus we read them and no board
    stated a trustworthy total. Collapsing them would hide a broken query behind a real
    result."""
    absent = "\n".join(board_coverage_headline(None))
    unmeasurable = "\n".join(
        board_coverage_headline(
            build_report([_board(bucket="dark", stated=None, ratio=None, shortfall=None)])
        )
    )

    assert "not measured this run" in absent
    assert "not measurable" in unmeasurable
    assert absent != unmeasurable


def test_the_headline_names_all_seven_buckets_even_at_zero() -> None:
    """An absent line is ambiguous between "checked, found none" and "never checked" — the
    reason `coverage_cmd.py` prints its notes unconditionally too."""
    rendered = "\n".join(board_coverage_headline(build_report([_board()])))

    for bucket in (
        "measured",
        "enumerated_only",
        "censored",
        "dark",
        "stale",
        "unscanned",
        "unreadable",
    ):
        assert bucket in rendered


def test_the_headline_publishes_the_censored_shortfall_and_still_no_ratio() -> None:
    """The censored boards hold the largest known holes in the corpus (Target: 649 held of a
    facet-recovered 12,096) and publish NO ratio, so they contribute nothing to the headline
    figure. The absolute shortfall is the only thing that makes them visible at all."""
    report = build_report(
        [_board(name="Target", bucket="censored", held=649, stated=12096, ratio=None,
                shortfall=11447)]
    )

    rendered = "\n".join(board_coverage_headline(report))

    assert "11,447" in rendered
    assert "No ratio is published for them" in rendered


def test_the_headline_calls_the_total_board_stated_not_independent() -> None:
    """`total` arrives in the same response as the listing it describes, so it is the board's
    own claim. Calling it independent is one of the eight ways this metric could lie."""
    rendered = "\n".join(board_coverage_headline(build_report([_board()])))

    assert "board-stated" in rendered
    assert "independent audit of it" in rendered


def test_the_table_sorts_boards_with_no_ratio_after_a_genuine_zero_percent() -> None:
    """`is not None`, not truthiness: a real 0.0% is a measured board with a stated total and
    nothing held, and it belongs with the ratios, not with the boards making no claim."""
    rows = board_coverage_table(
        build_report(
            [
                _board(name="NoClaim", bucket="enumerated_only", stated=None, ratio=None,
                       shortfall=None),
                _board(name="RealZero", held=0, stated=10, ratio=0.0, shortfall=10),
            ]
        )
    )

    body = [row for row in rows if row.startswith("|") and "---" not in row][1:]
    assert "RealZero" in body[0]
    assert "NoClaim" in body[1]


def test_the_table_is_empty_rather_than_a_header_when_there_is_no_report() -> None:
    assert board_coverage_table(None) == []


def test_a_board_with_no_ratio_renders_a_dash_never_a_percentage() -> None:
    rows = board_coverage_table(
        build_report(
            [_board(bucket="dark", stated=None, ratio=None, shortfall=None)]
        )
    )

    assert any("| — | dark |" in row for row in rows)
