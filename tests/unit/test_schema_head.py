from boardwatch.store.db import schema_revision


def test_head_is_the_runs_board_split_revision() -> None:
    """Pinned deliberately: a new migration must state its new head here, not inherit it.

    Bumping this line is the acknowledgement that the head moved.
    `p_runs_board_split` adds `runs.boards_partial`, `runs.boards_unchanged` and
    `runs.boards_failed` (all INTEGER NULL) so the store carries ScanSummary's full four-way
    board split, not only complete/attempted (D-341's other half, D-342). All three are additive
    with no table rebuild. It follows `p_death_probe`, which added `postings.death_strikes`
    (INTEGER NOT NULL DEFAULT 0) and `postings.last_death_probe_at` (DATETIME NULL) so a measured
    death can close a posting no board scan enumerates (D-325).
    """
    assert schema_revision() == "p_runs_board_split"
