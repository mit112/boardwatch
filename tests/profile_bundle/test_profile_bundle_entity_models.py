"""Entity, contact, relation, and skill record shapes (design §8, §9, §14).

The load-bearing assertion in this module is the *typed reference* one: design §8 says an evidence
ID cannot satisfy a metric reference merely because the string exists. Every reference field is
therefore probed with a valid ID of the wrong kind, and the refusal must come from Pydantic at
parse time — before any graph validation, which is what a bundle with a broken reference would
otherwise reach.
"""

from __future__ import annotations

import re

import pytest
from pydantic import TypeAdapter, ValidationError

from boardwatch.profile_bundle.models.base import (
    ENTITY_PREFIXES,
    RECORD_KIND_PREFIXES,
    EntityKind,
    Surface,
    VerificationState,
    entity_kind_of,
    id_pattern,
    prefix_of,
)
from boardwatch.profile_bundle.models.entities import (
    STATUS_CATALOGS,
    AffiliationEntity,
    AffiliationStatus,
    AwardEntity,
    CertificationEntity,
    ContactChannelType,
    ContactRecord,
    CourseEntity,
    EducationEntity,
    EducationStatus,
    EmploymentEntity,
    EntityRecord,
    PatentEntity,
    PersonEntity,
    PresentationEntity,
    ProjectEntity,
    ProjectStatus,
    PublicationEntity,
)
from boardwatch.profile_bundle.models.relations import RelationRecord
from boardwatch.profile_bundle.models.skills import SkillRecord

ENTITY_ADAPTER = TypeAdapter(EntityRecord)


def _entity_payload(kind: str, status: str | None) -> dict[str, object]:
    payload: dict[str, object] = {
        "entity_id": f"{kind}.example",
        "entity_type": kind,
        "display_name": "Example",
        "aliases": [],
        "created_at": "2026-08-10",
        "reviewed_at": "2026-08-10",
    }
    if status is not None:
        payload["status"] = status
    return payload


# --------------------------------------------------------------------------------------
# ID grammar
# --------------------------------------------------------------------------------------


def test_record_kind_prefix_catalog_is_the_design_catalog() -> None:
    assert RECORD_KIND_PREFIXES == (
        "profile",
        "source",
        "source-record",
        "candidate",
        "person",
        "education",
        "employment",
        "project",
        "publication",
        "award",
        "certification",
        "affiliation",
        "course",
        "presentation",
        "patent",
        "contact",
        "relation",
        "fact",
        "metric",
        "evidence",
        "conflict",
        "ruling",
        "skill",
        "claim",
        "approval",
        "approval-stamp",
        "change",
    )


def test_entity_prefixes_are_the_eleven_entity_kinds() -> None:
    assert set(ENTITY_PREFIXES) == {kind.value for kind in EntityKind}


@pytest.mark.parametrize("prefix", RECORD_KIND_PREFIXES)
def test_every_prefix_is_recognised_and_round_trips(prefix: str) -> None:
    assert prefix_of(f"{prefix}.example-01") == prefix


def test_longer_prefixes_win_so_a_stamp_is_not_an_approval() -> None:
    """`approval` would otherwise shadow `approval-stamp`, and `source` `source-record`."""
    assert prefix_of("approval-stamp.000002") == "approval-stamp"
    assert prefix_of("source-record." + "a" * 64) == "source-record"


@pytest.mark.parametrize(
    "candidate",
    [
        "project.Packet-Pantry",
        "project.",
        "project",
        ".project.x",
        "project.packet__pantry",
        "project.packet-",
        "project.-packet",
        "project.packet pantry",
        "unknown.x",
        "project.packet.pantry.001 ",
    ],
)
def test_malformed_ids_are_refused(candidate: str) -> None:
    """Every ID is a typed, pattern-constrained string, so malformation fails at parse time."""
    with pytest.raises(ValidationError):
        RelationRecord.model_validate(
            {
                "relation_id": "relation.x",
                "relation_type": "project_at_employment",
                "source_id": candidate,
                "target_id": "employment.b",
            }
        )


def test_id_pattern_matches_a_longer_prefix_before_its_own_prefix() -> None:
    pattern = re.compile(id_pattern("approval", "approval-stamp"))
    assert pattern.match("approval-stamp.000002")
    assert pattern.match("approval.evidence.x")


def test_entity_kind_of_refuses_a_non_entity_id() -> None:
    assert entity_kind_of("project.packet-pantry") is EntityKind.PROJECT
    with pytest.raises(ValueError):
        entity_kind_of("evidence.packet-pantry.benchmark.001")


# --------------------------------------------------------------------------------------
# Entities
# --------------------------------------------------------------------------------------


def test_all_eleven_entity_kinds_parse_through_the_discriminated_union() -> None:
    first_status = {kind: sorted(catalog)[0] for kind, catalog in STATUS_CATALOGS.items()}
    parsed = [
        ENTITY_ADAPTER.validate_python(_entity_payload(kind.value, first_status.get(kind.value)))
        for kind in EntityKind
    ]
    assert {type(entity) for entity in parsed} == {
        PersonEntity,
        EducationEntity,
        EmploymentEntity,
        ProjectEntity,
        PublicationEntity,
        AwardEntity,
        CertificationEntity,
        AffiliationEntity,
        CourseEntity,
        PresentationEntity,
        PatentEntity,
    }


def test_person_has_no_status_because_the_design_declares_no_catalog_for_it() -> None:
    assert "person" not in STATUS_CATALOGS
    assert "status" not in PersonEntity.model_fields
    with pytest.raises(ValidationError):
        ENTITY_ADAPTER.validate_python(_entity_payload("person", "active"))


@pytest.mark.parametrize(
    ("kind", "statuses"),
    [
        ("education", {"in_progress", "completed", "withdrawn"}),
        ("employment", {"planned", "offer_only", "active", "completed"}),
        (
            "project",
            {
                "concept",
                "prototype",
                "active_development",
                "completed",
                "shipped_private",
                "shipped_open_source",
                "live_public",
                "sunset",
            },
        ),
        ("publication", {"draft", "submitted", "accepted", "published"}),
        ("award", {"nominated", "awarded"}),
        ("certification", {"active", "expired", "revoked"}),
        ("affiliation", {"planned", "active", "past"}),
        ("course", {"planned", "in_progress", "completed", "withdrawn"}),
        ("presentation", {"proposed", "accepted", "delivered", "cancelled"}),
        ("patent", {"draft", "filed", "published", "granted", "abandoned"}),
    ],
)
def test_status_catalogs_are_exactly_the_design_catalogs(kind: str, statuses: set[str]) -> None:
    assert {member.value for member in STATUS_CATALOGS[kind]} == statuses


def test_one_entitys_status_cannot_satisfy_another() -> None:
    """`prototype` is a project state; an award that accepted it could claim shipped work."""
    with pytest.raises(ValidationError):
        ENTITY_ADAPTER.validate_python(_entity_payload("award", "prototype"))
    with pytest.raises(ValidationError):
        ENTITY_ADAPTER.validate_python(_entity_payload("project", "awarded"))


def test_entity_id_prefix_must_match_the_declared_entity_type() -> None:
    payload = _entity_payload("project", "concept")
    payload["entity_id"] = "employment.example"
    with pytest.raises(ValidationError):
        ENTITY_ADAPTER.validate_python(payload)


def test_unknown_field_on_an_entity_is_refused() -> None:
    payload = _entity_payload("project", "concept")
    payload["role_family"] = "backend"
    with pytest.raises(ValidationError):
        ENTITY_ADAPTER.validate_python(payload)


def test_blank_display_name_and_duplicate_aliases_are_refused() -> None:
    blank = _entity_payload("project", "concept")
    blank["display_name"] = "   "
    with pytest.raises(ValidationError):
        ENTITY_ADAPTER.validate_python(blank)
    duplicated = _entity_payload("project", "concept")
    duplicated["aliases"] = ["a", "a"]
    with pytest.raises(ValidationError):
        ENTITY_ADAPTER.validate_python(duplicated)


def test_aliases_are_normalised_to_a_canonical_order() -> None:
    payload = _entity_payload("project", "concept")
    payload["aliases"] = ["zeta", "alpha"]
    entity = ENTITY_ADAPTER.validate_python(payload)
    assert entity.aliases == ("alpha", "zeta")


def test_entities_are_frozen() -> None:
    entity = ENTITY_ADAPTER.validate_python(_entity_payload("project", "concept"))
    with pytest.raises(ValidationError):
        entity.display_name = "other"  # type: ignore[misc]


def test_shipped_project_statuses_are_the_four_reached_users_states() -> None:
    from boardwatch.profile_bundle.models.entities import SHIPPED_PROJECT_STATUSES

    assert SHIPPED_PROJECT_STATUSES == frozenset(
        {
            ProjectStatus.SHIPPED_PRIVATE,
            ProjectStatus.SHIPPED_OPEN_SOURCE,
            ProjectStatus.LIVE_PUBLIC,
            ProjectStatus.SUNSET,
        }
    )
    assert ProjectStatus.COMPLETED not in SHIPPED_PROJECT_STATUSES


# --------------------------------------------------------------------------------------
# Contacts
# --------------------------------------------------------------------------------------


def _contact(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "contact_id": "contact.example.email",
        "person_id": "person.example-candidate",
        "channel_type": "email",
        "value": "candidate@example.com",
        "allowed_surfaces": ["resume", "application"],
        "verification_state": "owner_confirmed",
    }
    payload.update(overrides)
    return payload


def test_contact_channel_types_are_the_closed_four() -> None:
    assert {member.value for member in ContactChannelType} == {
        "email",
        "phone",
        "profile_url",
        "location",
    }


def test_contact_parses_and_normalises_surfaces() -> None:
    contact = ContactRecord.model_validate(_contact())
    assert contact.allowed_surfaces == (Surface.APPLICATION, Surface.RESUME)
    assert contact.verification_state is VerificationState.OWNER_CONFIRMED


def test_contact_person_reference_must_be_a_person_id() -> None:
    with pytest.raises(ValidationError):
        ContactRecord.model_validate(_contact(person_id="project.packet-pantry"))


def test_contact_with_no_surfaces_is_private_knowledge_and_is_legal() -> None:
    assert ContactRecord.model_validate(_contact(allowed_surfaces=[])).allowed_surfaces == ()


def test_contact_rejects_an_unknown_channel_type_and_a_duplicate_surface() -> None:
    with pytest.raises(ValidationError):
        ContactRecord.model_validate(_contact(channel_type="fax"))
    with pytest.raises(ValidationError):
        ContactRecord.model_validate(_contact(allowed_surfaces=["resume", "resume"]))


# --------------------------------------------------------------------------------------
# Relations
# --------------------------------------------------------------------------------------


def test_relation_carries_no_surface_field_in_this_phase() -> None:
    """Design §10.3: relations expose no surfaces, and the field is absent rather than empty."""
    assert "allowed_surfaces" not in RelationRecord.model_fields


def test_relation_parses_with_entity_endpoints() -> None:
    relation = RelationRecord.model_validate(
        {
            "relation_id": "relation.packet-pantry.at-example-labs",
            "relation_type": "project_at_employment",
            "source_id": "project.packet-pantry",
            "target_id": "employment.example-labs",
        }
    )
    assert relation.relation_type == "project_at_employment"


@pytest.mark.parametrize("field", ["source_id", "target_id"])
def test_relation_endpoints_must_be_entities_not_facts(field: str) -> None:
    payload = {
        "relation_id": "relation.x",
        "relation_type": "project_at_employment",
        "source_id": "project.a",
        "target_id": "employment.b",
    }
    payload[field] = "fact.packet-pantry.language.001"
    with pytest.raises(ValidationError):
        RelationRecord.model_validate(payload)


# --------------------------------------------------------------------------------------
# Skills
# --------------------------------------------------------------------------------------


def _skill(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "skill_id": "skill.example-language",
        "canonical_name": "Example Language",
        "aliases": ["example-lang"],
        "category": "language",
        "supporting_fact_ids": ["fact.packet-pantry.language.001"],
        "verification_state": "verified",
        "allowed_surfaces": ["resume", "public"],
    }
    payload.update(overrides)
    return payload


def test_skill_parses_with_a_supporting_fact() -> None:
    skill = SkillRecord.model_validate(_skill())
    assert skill.supporting_fact_ids == ("fact.packet-pantry.language.001",)


def test_skill_with_no_supporting_fact_is_refused_at_parse_time() -> None:
    """A skill supported by nothing is the exact failure §14 exists to prevent."""
    with pytest.raises(ValidationError):
        SkillRecord.model_validate(_skill(supporting_fact_ids=[]))


def test_skill_support_must_be_facts_not_metrics_or_claims() -> None:
    with pytest.raises(ValidationError):
        SkillRecord.model_validate(
            _skill(supporting_fact_ids=["metric.packet-pantry.throughput.001"])
        )


def test_skill_has_no_role_family_field_because_that_is_deferred_selection_policy() -> None:
    assert "role_families" not in SkillRecord.model_fields
    assert "role_family" not in SkillRecord.model_fields


def test_skill_category_is_a_catalog_key_not_a_code_enum() -> None:
    """Any well-formed token parses; membership is checked against the revision-owned catalog."""
    assert SkillRecord.model_validate(_skill(category="clinical-technique")).category == (
        "clinical-technique"
    )


def test_education_and_affiliation_statuses_are_distinct_namespaces() -> None:
    assert EducationStatus.COMPLETED.value == "completed"
    assert "completed" not in {member.value for member in AffiliationStatus}
