from boardwatch.providers.base import BoardHealth
from boardwatch.registry.health_report import check_catalog, has_failures


def test_check_catalog_reports_every_entry(monkeypatch) -> None:
    rows = check_catalog(probe=lambda provider, slug: BoardHealth.OK)
    assert rows and all(r.status is BoardHealth.OK for r in rows)
    assert {r.provider for r in rows} == {
        "greenhouse", "lever", "ashby", "workable", "smartrecruiters",
    }


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


def test_main_names_every_not_ok_entry_in_the_log_when_the_table_goes_to_the_summary(
    monkeypatch, tmp_path, capsys
) -> None:
    # T330: with GITHUB_STEP_SUMMARY set the table goes to the summary tab only, so the step log
    # must still name each entry that is not OK, or a failed run's log names nothing.
    from boardwatch.registry import health_report
    from boardwatch.registry.health_report import HealthRow

    rows = [
        HealthRow("Palantir", "lever", "palantir", BoardHealth.OK),
        HealthRow("Mistral AI", "lever", "mistral", BoardHealth.DEAD),
        HealthRow("Quiet Co", "ashby", "quietco", BoardHealth.EMPTY),
    ]
    monkeypatch.setattr(health_report, "check_catalog", lambda: rows)
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

    assert health_report.main() == 1
    log = capsys.readouterr().out
    assert "Mistral AI (lever:mistral): dead" in log
    assert "Quiet Co (ashby:quietco): empty" in log
    assert "Palantir" not in log
    assert "| Palantir | lever | ok |" in summary.read_text(encoding="utf-8")
