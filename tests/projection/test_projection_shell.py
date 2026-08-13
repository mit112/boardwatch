"""The inert shell: model-only, never rendered, but required to exist and to be valid."""

from __future__ import annotations

from pathlib import Path

import pytest

from boardwatch.projection.errors import ProjectionError, ProjectionIssue
from boardwatch.projection.shell import load_shell

GOOD = "header:\n  - Example Candidate\n  - candidate@example.com\neducation:\n  - Example University\n"


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "master_resume.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_a_valid_shell_loads_verbatim(tmp_path: Path) -> None:
    header, education = load_shell(_write(tmp_path, GOOD))
    assert header == ("Example Candidate", "candidate@example.com")
    assert education == ("Example University",)


def test_a_missing_shell_source_is_fatal(tmp_path: Path) -> None:
    with pytest.raises(ProjectionError) as exc:
        load_shell(tmp_path / "absent.yaml")
    assert exc.value.violation.issue is ProjectionIssue.SHELL_SOURCE_UNREADABLE


def test_a_header_with_no_email_is_fatal(tmp_path: Path) -> None:
    body = "header:\n  - Example Candidate\neducation:\n  - Example University\n"
    with pytest.raises(ProjectionError) as exc:
        load_shell(_write(tmp_path, body))
    assert exc.value.violation.issue is ProjectionIssue.SHELL_SOURCE_UNREADABLE


def test_a_header_with_a_blank_first_line_is_fatal(tmp_path: Path) -> None:
    """`validate_master` rejects this separately from the email; the spec named only the email."""
    body = "header:\n  - '   '\n  - candidate@example.com\neducation:\n  - X\n"
    with pytest.raises(ProjectionError):
        load_shell(_write(tmp_path, body))


def test_a_template_artifact_in_the_shell_is_fatal(tmp_path: Path) -> None:
    """The third arm of `validate_master`, also unnamed by the spec."""
    body = "header:\n  - TODO\n  - candidate@example.com\neducation:\n  - X\n"
    with pytest.raises(ProjectionError):
        load_shell(_write(tmp_path, body))
