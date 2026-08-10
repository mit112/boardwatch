from boardwatch.store.db import schema_revision


def test_head_is_the_job_dispositions_table() -> None:
    """Pinned deliberately: a new migration must state its new head here, not inherit it.

    Bumping this line is the acknowledgement that the head moved. `p6_job_dispositions` adds the
    `job_dispositions` table (P6 slice 2's durable decision ledger, one row per job). It follows
    `p6_posting_identities`, which added the `posting_identities` table.
    """
    assert schema_revision() == "p6_job_dispositions"
