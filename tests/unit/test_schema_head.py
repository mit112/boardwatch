from boardwatch.store.db import schema_revision


def test_head_is_the_board_coverage_columns() -> None:
    """Pinned deliberately: a new migration must state its new head here, not inherit it.

    Bumping this line is the acknowledgement that the head moved.
    `p_board_coverage` adds four additive nullable INTEGER columns to `board_scans`:
    `board_reported_total`, `board_enumerated`, `detail_deferred`, `board_total_censored`
    (D-271). NULL means the board stated no total; it must never read as zero. It follows
    `p_seniority_band`, which added `profile.target_seniority_band`.
    """
    assert schema_revision() == "p_board_coverage"
