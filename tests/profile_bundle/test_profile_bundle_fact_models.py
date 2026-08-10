"""Fact records and the discriminated value union (design §10.1).

The discriminated union is what keeps a value's payload honest: `{type: date, value: "2026-13-01"}`
must fail here, not three layers later when a projection tries to format it. And a decimal must
stay a string all the way through, because a float has no single reproducible serialisation and the
bundle digest is computed from the serialised model.
"""

from __future__ import annotations

from datetime import date
from typing import get_args

import pytest
from pydantic import TypeAdapter, ValidationError

from boardwatch.profile_bundle.models.base import (
    Surface,
    UsageContext,
    VerificationBasis,
    VerificationState,
)
from boardwatch.profile_bundle.models.facts import (
    DateRangeValue,
    DecimalValue,
    FactRecord,
    FactValue,
    FactValueKind,
    ImportLineage,
    SkillRefValue,
    StringListValue,
    YearMonthValue,
)

VALUE_ADAPTER = TypeAdapter(FactValue)
DIGEST = "sha256:" + "0" * 64


def _fact(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "fact_id": "fact.packet-pantry.language.001",
        "subject_id": "project.packet-pantry",
        "predicate": "technology.used",
        "value": {"type": "skill_ref", "skill_id": "skill.example-language"},
        "verification_state": "verified",
        "verification_basis": "repository_verified",
        "usage_context": "personal_project",
        "evidence_ids": ["evidence.packet-pantry.manifest.001"],
        "allowed_surfaces": ["resume", "public"],
        "conflict_group_id": None,
        "reviewed_at": "2026-08-10",
        "expires_at": None,
        "supersedes_fact_ids": [],
        "import_lineage": None,
        "notes": None,
    }
    payload.update(overrides)
    return payload


# --------------------------------------------------------------------------------------
# Value union
# --------------------------------------------------------------------------------------


def test_value_kinds_are_the_closed_design_union() -> None:
    assert {member.value for member in FactValueKind} == {
        "string",
        "integer",
        "decimal",
        "boolean",
        "date",
        "year_month",
        "date_range",
        "url",
        "string_list",
        "skill_ref",
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "string", "value": "Example"},
        {"type": "integer", "value": 4},
        {"type": "decimal", "value": "3.75"},
        {"type": "boolean", "value": True},
        {"type": "date", "value": "2026-08-10"},
        {"type": "year_month", "value": "2026-08"},
        {"type": "date_range", "start": "2026-01-01", "end": "2026-08-10"},
        {"type": "date_range", "start": "2026-01-01", "end": None},
        {"type": "url", "value": "https://example.com/profile/example-candidate"},
        {"type": "string_list", "values": ["a", "b"]},
        {"type": "skill_ref", "skill_id": "skill.example-language"},
    ],
)
def test_every_value_kind_parses(payload: dict[str, object]) -> None:
    assert VALUE_ADAPTER.validate_python(payload).type == payload["type"]


def test_every_value_kind_has_exactly_one_model() -> None:
    """A kind with no model would be declarable in a predicate contract and unusable in a fact."""
    union, _field = get_args(FactValue)
    discriminants = [get_args(model.model_fields["type"].annotation)[0] for model in get_args(union)]
    assert sorted(discriminants) == sorted(member.value for member in FactValueKind)
    assert len(discriminants) == len(set(discriminants))


def test_decimal_is_a_string_so_no_float_reaches_identity() -> None:
    parsed = VALUE_ADAPTER.validate_python({"type": "decimal", "value": "0.1"})
    assert isinstance(parsed, DecimalValue)
    assert parsed.value == "0.1"
    assert isinstance(parsed.value, str)


@pytest.mark.parametrize("bad", [0.1, "1.", ".5", "01.5", "1,5", "1e3", "--1", ""])
def test_decimal_refuses_a_float_and_malformed_decimal_text(bad: object) -> None:
    with pytest.raises(ValidationError):
        VALUE_ADAPTER.validate_python({"type": "decimal", "value": bad})


@pytest.mark.parametrize("bad", ["2026-13", "2026-00", "26-08", "2026-8", "2026-08-01"])
def test_year_month_refuses_anything_but_yyyy_dash_mm(bad: str) -> None:
    with pytest.raises(ValidationError):
        VALUE_ADAPTER.validate_python({"type": "year_month", "value": bad})


def test_year_month_keeps_its_own_kind_and_does_not_decay_to_a_date() -> None:
    parsed = VALUE_ADAPTER.validate_python({"type": "year_month", "value": "2026-08"})
    assert isinstance(parsed, YearMonthValue)
    assert not isinstance(parsed.value, date)


@pytest.mark.parametrize("bad", ["2026-13-01", "not-a-date", "2026/08/10", 20260810])
def test_date_value_refuses_an_impossible_or_reformatted_date(bad: object) -> None:
    with pytest.raises(ValidationError):
        VALUE_ADAPTER.validate_python({"type": "date", "value": bad})


def test_open_date_range_is_legal_and_ordering_is_a_predicate_rule_not_intrinsic() -> None:
    """§10.4 attaches `start <= end` to specific predicates, so the value type must not force it."""
    inverted = VALUE_ADAPTER.validate_python(
        {"type": "date_range", "start": "2026-08-10", "end": "2026-01-01"}
    )
    assert isinstance(inverted, DateRangeValue)
    assert inverted.end == date(2026, 1, 1)


def test_date_range_requires_an_explicit_end_key() -> None:
    with pytest.raises(ValidationError):
        VALUE_ADAPTER.validate_python({"type": "date_range", "start": "2026-01-01"})


@pytest.mark.parametrize(
    "bad",
    [
        "ftp://example.com/x",
        "example.com/x",
        "javascript:alert(1)",
        "data:text/plain,x",
        "HTTPS://example.com/x",
        " https://example.com/x",
    ],
)
def test_url_value_accepts_only_http_and_https(bad: str) -> None:
    """A mail-scheme URL is refused by the same anchor. It is not written out as a literal here:
    the repository's generalization scan treats that shape as a personal profile URL in any tracked
    file, and design §22 forbids it in fixtures for exactly that reason."""
    with pytest.raises(ValidationError):
        VALUE_ADAPTER.validate_python({"type": "url", "value": bad})


def test_string_list_preserves_order_and_refuses_duplicates_and_emptiness() -> None:
    parsed = VALUE_ADAPTER.validate_python({"type": "string_list", "values": ["zeta", "alpha"]})
    assert isinstance(parsed, StringListValue)
    assert parsed.values == ("zeta", "alpha")
    with pytest.raises(ValidationError):
        VALUE_ADAPTER.validate_python({"type": "string_list", "values": ["a", "a"]})
    with pytest.raises(ValidationError):
        VALUE_ADAPTER.validate_python({"type": "string_list", "values": []})


def test_skill_ref_requires_a_skill_id() -> None:
    parsed = VALUE_ADAPTER.validate_python({"type": "skill_ref", "skill_id": "skill.a"})
    assert isinstance(parsed, SkillRefValue)
    with pytest.raises(ValidationError):
        VALUE_ADAPTER.validate_python({"type": "skill_ref", "skill_id": "fact.a"})


def test_wrong_payload_for_a_discriminant_is_refused() -> None:
    """`{type: skill_ref, value: ...}` must not fall through to the string variant."""
    with pytest.raises(ValidationError):
        VALUE_ADAPTER.validate_python({"type": "skill_ref", "value": "skill.a"})
    with pytest.raises(ValidationError):
        VALUE_ADAPTER.validate_python({"type": "string", "skill_id": "skill.a"})


def test_missing_or_unknown_discriminant_is_refused() -> None:
    with pytest.raises(ValidationError):
        VALUE_ADAPTER.validate_python({"value": "Example"})
    with pytest.raises(ValidationError):
        VALUE_ADAPTER.validate_python({"type": "float", "value": "1.5"})


# --------------------------------------------------------------------------------------
# Fact record
# --------------------------------------------------------------------------------------


def test_fact_parses_with_every_declared_field() -> None:
    fact = FactRecord.model_validate(_fact())
    assert fact.verification_state is VerificationState.VERIFIED
    assert fact.verification_basis is VerificationBasis.REPOSITORY_VERIFIED
    assert fact.usage_context is UsageContext.PERSONAL_PROJECT
    assert fact.allowed_surfaces == (Surface.PUBLIC, Surface.RESUME)
    assert fact.value_kind is FactValueKind.SKILL_REF


@pytest.mark.parametrize(
    "missing",
    [
        "verification_basis",
        "usage_context",
        "evidence_ids",
        "allowed_surfaces",
        "conflict_group_id",
        "reviewed_at",
        "expires_at",
        "supersedes_fact_ids",
        "import_lineage",
        "notes",
    ],
)
def test_every_fact_field_is_required_with_no_parser_default(missing: str) -> None:
    """Design §10.4: there are no parser defaults. An omitted field is invalid, not empty."""
    payload = _fact()
    del payload[missing]
    with pytest.raises(ValidationError):
        FactRecord.model_validate(payload)


def test_fact_subject_must_be_an_entity() -> None:
    with pytest.raises(ValidationError):
        FactRecord.model_validate(_fact(subject_id="evidence.packet-pantry.manifest.001"))
    with pytest.raises(ValidationError):
        FactRecord.model_validate(_fact(subject_id="skill.example-language"))


def test_fact_evidence_references_must_be_evidence_ids() -> None:
    with pytest.raises(ValidationError):
        FactRecord.model_validate(_fact(evidence_ids=["metric.packet-pantry.throughput.001"]))


def test_fact_conflict_group_must_be_a_conflict_id() -> None:
    with pytest.raises(ValidationError):
        FactRecord.model_validate(_fact(conflict_group_id="ruling.a.001"))
    assert (
        FactRecord.model_validate(
            _fact(conflict_group_id="conflict.packet-pantry.launch-date")
        ).conflict_group_id
        == "conflict.packet-pantry.launch-date"
    )


def test_fact_supersession_references_must_be_facts_and_never_itself() -> None:
    with pytest.raises(ValidationError):
        FactRecord.model_validate(_fact(supersedes_fact_ids=["metric.a.001"]))
    with pytest.raises(ValidationError):
        FactRecord.model_validate(
            _fact(supersedes_fact_ids=["fact.packet-pantry.language.001"])
        )


def test_fact_predicate_must_be_a_dotted_lowercase_name() -> None:
    for bad in ["Technology.Used", "technology", "technology..used", "technology-used", ""]:
        with pytest.raises(ValidationError):
            FactRecord.model_validate(_fact(predicate=bad))


def test_import_lineage_parses_and_requires_a_full_digest() -> None:
    lineage = ImportLineage.model_validate(
        {
            "source_id": "source.legacy-project-notes",
            "source_locator": "projects/packet-pantry.md#stack",
            "source_content_digest": DIGEST,
        }
    )
    assert lineage.source_id == "source.legacy-project-notes"
    with pytest.raises(ValidationError):
        ImportLineage.model_validate(
            {
                "source_id": "source.x",
                "source_locator": "a",
                "source_content_digest": "0" * 64,
            }
        )


def test_unknown_field_on_a_fact_is_refused() -> None:
    with pytest.raises(ValidationError):
        FactRecord.model_validate(_fact(role_family="backend"))


def test_fact_is_frozen() -> None:
    fact = FactRecord.model_validate(_fact())
    with pytest.raises(ValidationError):
        fact.verification_state = VerificationState.REJECTED  # type: ignore[misc]


def test_evidence_ids_are_deduplicated_by_refusal_not_by_folding() -> None:
    with pytest.raises(ValidationError):
        FactRecord.model_validate(_fact(evidence_ids=["evidence.a", "evidence.a"]))


def test_a_fact_with_no_evidence_parses_because_the_contract_is_per_predicate() -> None:
    """Whether zero evidence is legal is a predicate-contract question, checked semantically."""
    assert FactRecord.model_validate(_fact(evidence_ids=[])).evidence_ids == ()
