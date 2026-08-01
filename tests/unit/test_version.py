import re
import tomllib
from pathlib import Path

from typer.testing import CliRunner

from boardwatch.cli.app import app

runner = CliRunner()


def test_help_exits_zero() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "boardwatch" in result.stdout


def test_version_prints_package_version_and_schema_revision() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0

    # Oracle 1: Read declared version from pyproject.toml (independent source)
    pyproject_path = Path(__file__).parent.parent.parent / "pyproject.toml"
    with open(pyproject_path, "rb") as f:
        pyproject_data = tomllib.load(f)
    declared_version = pyproject_data["project"]["version"]
    assert f"boardwatch {declared_version}" in result.stdout

    # Oracle 2: Verify version shape matches semantic versioning pattern
    assert re.search(r"boardwatch \d+\.\d+\.\d+", result.stdout)

    # Existing check (unchanged)
    assert "schema" in result.stdout
