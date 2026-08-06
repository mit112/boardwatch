from boardwatch.store.db import schema_revision


def test_head_is_the_run_status_column() -> None:
    """Pinned deliberately: a new migration must state its new head here, not inherit it.

    Bumping this line is the acknowledgement that the head moved. `p0_run_status` adds the
    `status` column to `runs` — the closed catalog `running | ok | failed` that P0 item 4's
    manifest reports as exit status. It follows `run_attribution`, which added nullable
    run_id to eligibility_evaluations and artifacts.
    """
    assert schema_revision() == "p0_run_status"
