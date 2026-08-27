from boardwatch.store.db import schema_revision


def test_head_is_the_death_probe_revision() -> None:
    """Pinned deliberately: a new migration must state its new head here, not inherit it.

    Bumping this line is the acknowledgement that the head moved.
    `p_death_probe` adds `postings.death_strikes` (INTEGER NOT NULL DEFAULT 0) and
    `postings.last_death_probe_at` (DATETIME NULL) so a measured death can close a posting no
    board scan enumerates (D-325). Both are additive with no table rebuild. It follows
    `p_lane_companies`, which widened `companies.source` to admit `'lane'` and added
    `board_scans.scan_kind`.
    """
    assert schema_revision() == "p_death_probe"
