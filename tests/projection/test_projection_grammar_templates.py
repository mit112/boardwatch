"""`{predicate}` and `{@field}` — the only two admitted forms."""

from __future__ import annotations

from datetime import date
from typing import get_args

import pytest

from boardwatch.profile_bundle.models.base import PredicateId
from boardwatch.profile_bundle.models.entities import ProjectEntity, ProjectStatus
from boardwatch.projection.errors import ProjectionError, ProjectionIssue
from boardwatch.projection.grammar import _PREDICATE_RE, resolve_template


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


def test_the_predicate_pattern_is_derived_from_predicate_id_not_restated() -> None:
    """`_PREDICATE_RE` must track `PredicateId`'s own constraint pattern
    (`profile_bundle/models/base.py`), not a hand-copied string. If `PredicateId` is ever revised,
    a restated pattern here would keep enforcing the stale rule with nothing to catch the drift —
    this reads the emitter's own constant, so the two cannot diverge silently."""
    canonical_pattern = get_args(PredicateId)[1].pattern
    assert _PREDICATE_RE.pattern == canonical_pattern


def test_status_resolves_from_a_genuine_str_enum_member_not_a_stand_in() -> None:
    """Every stub above sets `status` to a plain `str`. On the real bundle, `@status` is always a
    `StrEnum` member (`ProjectStatus`, etc.). Pin the production shape directly rather than relying
    on a stand-in that could pass even if the renderer only worked for `str`."""
    entity = ProjectEntity(
        entity_id="project.example",
        entity_type="project",
        display_name="Packet Pantry",
        created_at=date(2025, 1, 1),
        reviewed_at=date(2025, 1, 1),
        status=ProjectStatus.LIVE_PUBLIC,
    )
    out = resolve_template(
        "{@status}",
        entity=entity,
        facts_by_predicate={},
        open_range_label="Present",
        where="w",
    )
    assert out == "live_public"


def test_an_unknown_display_field_is_malformed_not_unresolved() -> None:
    """`{@bogus}` names an `@`-field the catalog does not admit at all — distinct from `{@status}`
    merely being absent on a particular entity, which is `UNRESOLVED_PLACEHOLDER` instead."""
    with pytest.raises(ProjectionError) as exc:
        resolve_template(
            "{@bogus}",
            entity=_Entity(),
            facts_by_predicate={},
            open_range_label="Present",
            where="projection.yaml:12",
        )
    assert exc.value.violation.issue is ProjectionIssue.MALFORMED_PLACEHOLDER


def test_an_empty_template_resolves_to_an_empty_string() -> None:
    out = resolve_template(
        "",
        entity=_Entity(),
        facts_by_predicate={},
        open_range_label="Present",
        where="w",
    )
    assert out == ""


def test_a_whitespace_only_template_is_preserved_verbatim() -> None:
    out = resolve_template(
        "   ",
        entity=_Entity(),
        facts_by_predicate={},
        open_range_label="Present",
        where="w",
    )
    assert out == "   "
