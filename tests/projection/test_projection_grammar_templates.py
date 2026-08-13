"""`{predicate}` and `{@field}` — the only two admitted forms."""

from __future__ import annotations

import pytest

from boardwatch.projection.errors import ProjectionError, ProjectionIssue
from boardwatch.projection.grammar import resolve_template


class _Entity:
    entity_type = "project"
    display_name = "Packet Pantry"
    status = "live_public"


class _Person:
    """`PersonEntity` genuinely has no `status` field (`models/entities.py:143-145`), so the stub
    genuinely omits it rather than setting it to None — `getattr` must miss, not find a null."""

    entity_type = "person"
    display_name = "Example Candidate"


def test_an_entity_display_field_resolves() -> None:
    assert (
        resolve_template(
            "{@display_name}",
            entity=_Entity(),
            facts_by_predicate={},
            open_range_label="Present",
            where="w",
        )
        == "Packet Pantry"
    )


def test_a_literal_the_owner_wrote_is_preserved_around_a_placeholder() -> None:
    """Boardwatch never invents a word; it also never drops one the owner wrote."""
    out = resolve_template(
        "{@display_name} (Volunteer)",
        entity=_Entity(),
        facts_by_predicate={},
        open_range_label="Present",
        where="w",
    )
    assert out == "Packet Pantry (Volunteer)"


def test_an_unknown_namespace_form_is_fatal() -> None:
    with pytest.raises(ProjectionError) as exc:
        resolve_template(
            "{%weird}",
            entity=_Entity(),
            facts_by_predicate={},
            open_range_label="Present",
            where="projection.yaml:12",
        )
    assert exc.value.violation.issue is ProjectionIssue.MALFORMED_PLACEHOLDER


def test_an_unresolvable_predicate_is_fatal_not_blank() -> None:
    with pytest.raises(ProjectionError) as exc:
        resolve_template(
            "{employment.title}",
            entity=_Entity(),
            facts_by_predicate={},
            open_range_label="Present",
            where="projection.yaml:12",
        )
    assert exc.value.violation.issue is ProjectionIssue.UNRESOLVED_PLACEHOLDER


def test_status_resolves_on_an_entity_that_has_one() -> None:
    """The positive control for the test below. Without it, a `resolve_template` that refused
    `{@status}` unconditionally would pass — a check that cannot fire reads as coverage."""
    out = resolve_template(
        "{@status}",
        entity=_Entity(),
        facts_by_predicate={},
        open_range_label="Present",
        where="w",
    )
    assert out == "live_public"


def test_status_on_a_person_entity_is_a_named_refusal_not_an_attribute_error() -> None:
    """`PersonEntity` has no `status` field, deliberately (`models/entities.py:143-145`), so the
    grammar table's `@status` is not universally resolvable and must say so."""
    with pytest.raises(ProjectionError) as exc:
        resolve_template(
            "{@status}",
            entity=_Person(),
            facts_by_predicate={},
            open_range_label="Present",
            where="projection.yaml:12",
        )
    assert exc.value.violation.issue is ProjectionIssue.UNRESOLVED_PLACEHOLDER
