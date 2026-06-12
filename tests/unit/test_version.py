from typer.testing import CliRunner

from boardwatch.cli.app import app

runner = CliRunner()


def test_help_exits_zero() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "boardwatch" in result.stdout


def test_version_prints_package_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "boardwatch 0.1.0.dev0" in result.stdout
