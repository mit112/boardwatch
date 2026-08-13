from boardwatch.store.db import schema_revision


def test_head_is_the_eligibility_inputs_identity_index() -> None:
    """Pinned deliberately: a new migration must state its new head here, not inherit it.

    Bumping this line is the acknowledgement that the head moved.
    `perf_eligibility_inputs_identity` indexes `eligibility_inputs` by
    (posting_version_id, profile_hash, rules_hash) so `boardwatch top`'s pending anti-join
    seeks instead of re-scanning once per open posting. It adds no column and no table, and it
    follows `p6_job_dispositions`, which added the `job_dispositions` table.
    """
    assert schema_revision() == "perf_eligibility_inputs_identity"
