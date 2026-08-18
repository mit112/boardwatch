from boardwatch.store.db import schema_revision


def test_head_is_the_runs_status_backfill_repair() -> None:
    """Pinned deliberately: a new migration must state its new head here, not inherit it.

    Bumping this line is the acknowledgement that the head moved.
    `runs_status_backfill_repair` closes the `runs` rows `p0_run_status`'s `DEFAULT 'running'`
    backfilled onto rows that had already finished, matching on
    `status='running' AND finished_at IS NOT NULL` rather than on row ids. It adds no column and
    no table, and it follows `perf_eligibility_inputs_identity`, which indexed
    `eligibility_inputs` by (posting_version_id, profile_hash, rules_hash).
    """
    assert schema_revision() == "runs_status_backfill_repair"
