"""`{predicate}` and `{@field}` — the only two admitted forms."""

from __future__ import annotations

from datetime import date

import pytest

from boardwatch.profile_bundle.models.base import (
    Surface,
    UsageContext,
    VerificationBasis,
    VerificationState,
)
from boardwatch.profile_bundle.models.entities import ProjectEntity, ProjectStatus
from boardwatch.profile_bundle.models.facts import FactRecord, StringValue
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


def test_a_valid_dotted_predicate_is_accepted_and_resolves() -> None:
    """`employment.title` is the predicate shape the grammar must admit. Round-tripped through a
    real `FactRecord` so acceptance is proven by an actual render, not merely by the absence of
    `MALFORMED_PLACEHOLDER`."""
    fact = FactRecord(
        fact_id="fact.example-1",
        subject_id="employment.example",
        predicate="employment.title",
        value=StringValue(type="string", value="Founding Engineer"),
        verification_state=VerificationState.OWNER_CONFIRMED,
        verification_basis=VerificationBasis.OWNER_ATTESTED,
        usage_context=UsageContext.PROFESSIONAL,
        evidence_ids=(),
        allowed_surfaces=(Surface.RESUME,),
        conflict_group_id=None,
        reviewed_at=date(2025, 1, 1),
        expires_at=None,
        supersedes_fact_ids=(),
        import_lineage=None,
        notes=None,
    )
    out = resolve_template(
        "{employment.title}",
        entity=_Entity(),
        facts_by_predicate={"employment.title": fact},
        open_range_label="Present",
        where="w",
    )
    assert out == "Founding Engineer"


@pytest.mark.parametrize(
    "token",
    [
        "employment",
        "_employment.title",
        "1employment.title",
        "employment.Title",
        "employment.title.",
    ],
    ids=["no_dot", "leading_underscore", "leading_digit", "uppercase_segment", "trailing_dot"],
)
def test_a_malformed_predicate_shape_is_rejected(token: str) -> None:
    """These literal shapes are facts about what a predicate token looks like, independent of both
    `PredicateId` and its derivation in `grammar.py` — pinning them here is what actually catches a
    future widening of either. Each is asserted through `resolve_template`, the real code path,
    not by poking the regex directly."""
    with pytest.raises(ProjectionError) as exc:
        resolve_template(
            f"{{{token}}}",
            entity=_Entity(),
            facts_by_predicate={},
            open_range_label="Present",
            where="projection.yaml:12",
        )
    assert exc.value.violation.issue is ProjectionIssue.MALFORMED_PLACEHOLDER, (
        f"{token!r} was expected to be rejected as malformed"
    )


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
