from boardwatch.store.db import schema_revision


def test_head_is_the_posting_identities_table() -> None:
    """Pinned deliberately: a new migration must state its new head here, not inherit it.

    Bumping this line is the acknowledgement that the head moved. `p6_posting_identities`
    adds the `posting_identities` table (P6 slice 1's stored per-posting identities, one row
    per posting per kind per algorithm version). It follows `p1_resume_max_pages`, which
    added the `resume_max_pages` column to `profile`.
    """
    assert schema_revision() == "p6_posting_identities"
