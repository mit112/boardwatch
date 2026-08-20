from boardwatch.store.db import schema_revision


def test_head_is_the_seniority_band() -> None:
    """Pinned deliberately: a new migration must state its new head here, not inherit it.

    Bumping this line is the acknowledgement that the head moved.
    `p_seniority_band` adds `profile.target_seniority_band` — one additive TEXT column,
    NOT NULL DEFAULT 'any', so every existing install backfills to the inert band and the
    seniority gate changes no behaviour until the operator narrows it (D-246). It follows
    `runs_status_backfill_repair`, which closed the `runs` rows `p0_run_status`'s
    `DEFAULT 'running'` backfilled onto rows that had already finished.
    """
    assert schema_revision() == "p_seniority_band"
