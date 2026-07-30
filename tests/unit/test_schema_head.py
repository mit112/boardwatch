from boardwatch.store.db import schema_revision


def test_head_is_the_profile_eligibility_spine() -> None:
    assert schema_revision() == "p2_profile_eligibility"
