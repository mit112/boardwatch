from boardwatch.providers.base import BoardHealth
from boardwatch.registry.health_report import check_catalog, has_failures


def test_check_catalog_reports_every_entry(monkeypatch) -> None:
    rows = check_catalog(probe=lambda provider, slug: BoardHealth.OK)
    assert rows and all(r.status is BoardHealth.OK for r in rows)
    assert {r.provider for r in rows} == {"greenhouse", "lever", "ashby"}


def test_failures_count_dead_error_unreachable_but_not_empty() -> None:
    assert has_failures([BoardHealth.OK, BoardHealth.EMPTY]) is False
    for bad in (BoardHealth.DEAD, BoardHealth.ERROR, BoardHealth.UNREACHABLE):
        assert has_failures([BoardHealth.OK, bad]) is True


def test_module_never_imports_store_transitively() -> None:
    # a SOURCE-STRING check misses transitive imports; assert the real import graph in a
    # clean subprocess: importing health_report must not pull in any boardwatch.store.* module
    import subprocess
    import sys

    code = (
        "import boardwatch.registry.health_report; import sys; "
        "bad=[m for m in sys.modules if m.startswith('boardwatch.store')]; "
        "assert not bad, bad"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
