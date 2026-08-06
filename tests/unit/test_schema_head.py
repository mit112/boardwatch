from boardwatch.store.db import schema_revision


def test_head_is_the_run_attribution_spine() -> None:
    """Pinned deliberately: a new migration must state its new head here, not inherit it.

    Bumping this line is the acknowledgement that the head moved. `run_attribution` adds
    nullable run_id to eligibility_evaluations and artifacts.
    """
    assert schema_revision() == "run_attribution"
