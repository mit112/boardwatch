from typer.testing import CliRunner

from boardwatch.cli.app import app

runner = CliRunner()


def test_guide_prints_the_canonical_journey_in_order() -> None:
    result = runner.invoke(app, ["guide"])
    assert result.exit_code == 0
    out = result.stdout
    for command in [
        "boardwatch init",
        "boardwatch scan",
        "boardwatch top",
        "boardwatch show",
        "boardwatch track add",
    ]:
        assert command in out
    # the unattended alternative and the differentiator are named
    assert "boardwatch run" in out
    assert "eligibility" in out


def test_guide_needs_no_profile_or_store() -> None:
    # runs from a clean environment with no --data-dir and no init
    result = runner.invoke(app, ["guide"])
    assert result.exit_code == 0
    assert "no profile yet" not in result.stdout
