"""The projection package's closed reason catalog."""

from __future__ import annotations

import dataclasses

import pytest

from boardwatch.projection.errors import (
    ProjectionError,
    ProjectionIssue,
    ProjectionViolation,
    raise_violation,
)


def test_every_issue_is_a_string_valued_member() -> None:
    """Derived from the enum itself, so a member added without a value fails here."""
    assert len(list(ProjectionIssue)) >= 12
    for issue in ProjectionIssue:
        assert isinstance(issue.value, str) and issue.value


def test_a_violation_carries_its_typed_issue_not_a_message_to_grep() -> None:
    with pytest.raises(ProjectionError) as exc:
        raise_violation(
            ProjectionIssue.UNRESOLVED_PLACEHOLDER, "nope", where="projection.yaml:12"
        )
    assert exc.value.violation.issue is ProjectionIssue.UNRESOLVED_PLACEHOLDER
    assert exc.value.violation.where == "projection.yaml:12"


def test_the_violation_record_is_frozen() -> None:
    v = ProjectionViolation(issue=ProjectionIssue.UNRESOLVED_PLACEHOLDER, message="m", where="w")
    with pytest.raises(dataclasses.FrozenInstanceError):
        v.message = "other"  # type: ignore[misc]
