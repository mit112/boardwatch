from boardwatch.store.db import schema_revision


def test_head_is_the_lane_companies_revision() -> None:
    """Pinned deliberately: a new migration must state its new head here, not inherit it.

    Bumping this line is the acknowledgement that the head moved.
    `p_lane_companies` widens `companies.source` to admit `'lane'` and adds
    `board_scans.scan_kind` (`'board'` | `'lane'`, defaulted `'board'`) so a lane's scan row
    cannot be counted as board coverage (D-285). Both are CHECK changes, so both rebuild their
    table. It follows `p_board_coverage`, which added the four nullable coverage columns.
    """
    assert schema_revision() == "p_lane_companies"
