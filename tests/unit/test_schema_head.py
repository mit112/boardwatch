from boardwatch.store.db import schema_revision


def test_head_is_the_resume_max_pages_column() -> None:
    """Pinned deliberately: a new migration must state its new head here, not inherit it.

    Bumping this line is the acknowledgement that the head moved. `p1_resume_max_pages` adds
    the `resume_max_pages` column to `profile` (P1a's page-count gate, default 1). It follows
    `p0_run_status`, which added the `status` column to `runs`.
    """
    assert schema_revision() == "p1_resume_max_pages"
