from boardwatch.store.db import schema_revision


def test_head_is_the_artifacts_spine() -> None:
    assert schema_revision() == "p0_artifacts"
