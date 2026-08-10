"""Metric and claim record shapes (design §11, §15).

Metrics carry a number that a later projection will render into prose, so the fields that constrain
that rendering — allowed phrasings, forbidden phrasings, protected tokens, typed caveats — are
required structure rather than commentary. Claims carry the prose and the records that justify it.

The cross-record checks (does every numeral in the claim text trace to a referenced metric? is the
metric's unit in the active catalog?) need the whole tree and belong to semantic validation. What is
pinned here is that the shapes make those checks possible at all.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from boardwatch.profile_bundle.models.claims import (
    BULLET_CLAIM_TYPES,
    SUMMARY_CLAIM_TYPES,
    ClaimRecord,
    ClaimStatus,
    ClaimType,
    MetricRendering,
)
from boardwatch.profile_bundle.models.metrics import (
    CaveatSeverity,
    MetricKind,
    MetricQualifier,
    MetricRecord,
)


def _metric(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "metric_id": "metric.packet-pantry.throughput.001",
        "subject_id": "project.packet-pantry",
        "metric_kind": "throughput",
        "value": {"number": "120", "unit": "items_per_second", "qualifier": "approximate"},
        "display_value": "~120 items/s",
        "measurement_context": "Single-node local benchmark with one producer",
        "measurement_method": "Committed load profile run for five minutes",
        "evidence_ids": ["evidence.packet-pantry.benchmark.001"],
        "verification_state": "verified",
        "allowed_surfaces": ["resume", "public"],
        "allowed_phrasings": [
            "sustained approximately 120 items/s",
            "sustained ~120 items/s",
        ],
        "forbidden_phrasings": ["handled thousands of items per second"],
        "protected_tokens": ["120", "items/s"],
        "caveats": [
            {
                "severity": "context_required",
                "text": "Do not generalize this local result to production hardware.",
            }
        ],
        "reviewed_at": "2026-08-10",
    }
    payload.update(overrides)
    return payload


def _claim(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "claim_id": "claim.packet-pantry.backend.001",
        "subject_id": "project.packet-pantry",
        "claim_type": "accomplishment",
        "text": "Built a service with retry-safe ingestion and measured local throughput.",
        "required_fact_ids": ["fact.packet-pantry.language.001"],
        "required_metric_ids": ["metric.packet-pantry.throughput.001"],
        "metric_mentions": [
            {
                "metric_id": "metric.packet-pantry.throughput.001",
                "rendering": "qualitative_only",
            }
        ],
        "status": "approved",
        "allowed_surfaces": ["resume"],
        "assertion_tags": ["built"],
        "reviewed_at": "2026-08-10",
    }
    payload.update(overrides)
    return payload


# --------------------------------------------------------------------------------------
# metric catalogs
# --------------------------------------------------------------------------------------


def test_metric_kinds_are_the_closed_ten() -> None:
    assert {member.value for member in MetricKind} == {
        "count",
        "duration",
        "rate",
        "throughput",
        "latency",
        "percentage",
        "currency",
        "size",
        "rank",
        "score",
    }


def test_metric_qualifiers_are_the_closed_six() -> None:
    assert {member.value for member in MetricQualifier} == {
        "exact",
        "approximate",
        "at_least",
        "more_than",
        "at_most",
        "range",
    }


def test_caveat_severities_are_the_closed_three() -> None:
    assert {member.value for member in CaveatSeverity} == {
        "informational",
        "context_required",
        "disqualifying",
    }


# --------------------------------------------------------------------------------------
# metric records
# --------------------------------------------------------------------------------------


def test_a_complete_metric_parses() -> None:
    metric = MetricRecord.model_validate(_metric())
    assert metric.metric_kind is MetricKind.THROUGHPUT
    assert metric.value.qualifier is MetricQualifier.APPROXIMATE
    assert metric.value.number == "120"


def test_the_metric_number_is_a_decimal_string_not_a_float() -> None:
    with pytest.raises(ValidationError):
        MetricRecord.model_validate(
            _metric(value={"number": 120.0, "unit": "items_per_second", "qualifier": "exact"})
        )
    assert isinstance(
        MetricRecord.model_validate(
            _metric(value={"number": "0.5", "unit": "percent", "qualifier": "exact"})
        ).value.number,
        str,
    )


@pytest.mark.parametrize(
    "missing",
    [
        "subject_id",
        "metric_kind",
        "value",
        "display_value",
        "measurement_context",
        "measurement_method",
        "evidence_ids",
        "verification_state",
        "allowed_surfaces",
        "allowed_phrasings",
        "forbidden_phrasings",
        "protected_tokens",
        "caveats",
        "reviewed_at",
    ],
)
def test_every_metric_field_is_required(missing: str) -> None:
    payload = _metric()
    del payload[missing]
    with pytest.raises(ValidationError):
        MetricRecord.model_validate(payload)


def test_a_metric_needs_a_subject_evidence_and_at_least_one_allowed_phrasing() -> None:
    """§11: "Every metric requires a subject, method, context, evidence, and at least one allowed
    phrasing before it can be considered for a future résumé.\""""
    with pytest.raises(ValidationError):
        MetricRecord.model_validate(_metric(evidence_ids=[]))
    with pytest.raises(ValidationError):
        MetricRecord.model_validate(_metric(allowed_phrasings=[]))
    with pytest.raises(ValidationError):
        MetricRecord.model_validate(_metric(measurement_method="  "))
    with pytest.raises(ValidationError):
        MetricRecord.model_validate(_metric(measurement_context=""))


def test_metric_subject_must_be_an_entity_not_a_claim() -> None:
    with pytest.raises(ValidationError):
        MetricRecord.model_validate(_metric(subject_id="claim.packet-pantry.backend.001"))


def test_allowed_phrasings_keep_their_authored_order() -> None:
    """Order is a preference signal for a later projection, so it must not be normalised away."""
    metric = MetricRecord.model_validate(_metric(allowed_phrasings=["zeta form", "alpha form"]))
    assert metric.allowed_phrasings == ("zeta form", "alpha form")


def test_phrasing_and_token_lists_refuse_duplicates() -> None:
    for field in ("allowed_phrasings", "forbidden_phrasings", "protected_tokens"):
        with pytest.raises(ValidationError):
            MetricRecord.model_validate(_metric(**{field: ["same", "same"]}))


def test_protected_tokens_may_be_empty_but_the_key_is_required() -> None:
    assert MetricRecord.model_validate(_metric(protected_tokens=[])).protected_tokens == ()


def test_caveat_severity_helpers_report_the_designs_two_special_cases() -> None:
    informational = MetricRecord.model_validate(
        _metric(caveats=[{"severity": "informational", "text": "Measured on one node."}])
    )
    assert not informational.has_disqualifying_caveat
    assert informational.context_required_caveats == ()

    required = MetricRecord.model_validate(_metric())
    assert required.context_required_caveats[0].severity is CaveatSeverity.CONTEXT_REQUIRED

    disqualifying = MetricRecord.model_validate(
        _metric(caveats=[{"severity": "disqualifying", "text": "Superseded methodology."}])
    )
    assert disqualifying.has_disqualifying_caveat


def test_unknown_caveat_severity_and_blank_caveat_text_are_refused() -> None:
    with pytest.raises(ValidationError):
        MetricRecord.model_validate(_metric(caveats=[{"severity": "minor", "text": "x"}]))
    with pytest.raises(ValidationError):
        MetricRecord.model_validate(_metric(caveats=[{"severity": "informational", "text": " "}]))


def test_metric_unit_is_a_lowercase_catalog_token() -> None:
    for bad in ["Items", "items/s", "items per second", ""]:
        with pytest.raises(ValidationError):
            MetricRecord.model_validate(
                _metric(value={"number": "1", "unit": bad, "qualifier": "exact"})
            )


def test_unknown_metric_field_is_refused() -> None:
    with pytest.raises(ValidationError):
        MetricRecord.model_validate(_metric(confidence=0.9))


# --------------------------------------------------------------------------------------
# claims
# --------------------------------------------------------------------------------------


def test_claim_types_are_the_closed_four_split_across_two_owning_files() -> None:
    assert {member.value for member in ClaimType} == {
        "responsibility",
        "accomplishment",
        "project_summary",
        "professional_summary",
    }
    assert BULLET_CLAIM_TYPES | SUMMARY_CLAIM_TYPES == set(ClaimType)
    assert not (BULLET_CLAIM_TYPES & SUMMARY_CLAIM_TYPES)


def test_claim_statuses_are_the_closed_four() -> None:
    assert {member.value for member in ClaimStatus} == {
        "draft",
        "approved",
        "rejected",
        "superseded",
    }


def test_metric_rendering_distinguishes_a_rendered_figure_from_a_qualitative_reference() -> None:
    """§15 names `qualitative_only`; a metric whose figure DOES appear needs the other value."""
    assert {member.value for member in MetricRendering} == {"rendered", "qualitative_only"}


def test_a_complete_claim_parses() -> None:
    claim = ClaimRecord.model_validate(_claim())
    assert claim.claim_type is ClaimType.ACCOMPLISHMENT
    assert claim.status is ClaimStatus.APPROVED
    assert claim.mention_by_metric == {
        "metric.packet-pantry.throughput.001": MetricRendering.QUALITATIVE_ONLY
    }


@pytest.mark.parametrize(
    "missing",
    [
        "subject_id",
        "claim_type",
        "text",
        "required_fact_ids",
        "required_metric_ids",
        "metric_mentions",
        "status",
        "allowed_surfaces",
        "assertion_tags",
        "reviewed_at",
    ],
)
def test_every_claim_field_is_required(missing: str) -> None:
    payload = _claim()
    del payload[missing]
    with pytest.raises(ValidationError):
        ClaimRecord.model_validate(payload)


def test_a_draft_claim_may_reference_no_facts_yet() -> None:
    """"An approved claim must reference at least one fact" is status-dependent, so a draft that
    the owner is still assembling must remain representable."""
    claim = ClaimRecord.model_validate(
        _claim(status="draft", required_fact_ids=[], required_metric_ids=[], metric_mentions=[])
    )
    assert claim.required_fact_ids == ()


def test_claim_references_are_typed_to_their_kinds() -> None:
    with pytest.raises(ValidationError):
        ClaimRecord.model_validate(_claim(required_fact_ids=["metric.a.001"]))
    with pytest.raises(ValidationError):
        ClaimRecord.model_validate(_claim(required_metric_ids=["fact.a.001"]))
    with pytest.raises(ValidationError):
        ClaimRecord.model_validate(
            _claim(metric_mentions=[{"metric_id": "fact.a.001", "rendering": "rendered"}])
        )


def test_claim_subject_must_be_an_entity() -> None:
    with pytest.raises(ValidationError):
        ClaimRecord.model_validate(_claim(subject_id="skill.example-language"))


def test_unknown_rendering_and_unknown_status_are_refused() -> None:
    with pytest.raises(ValidationError):
        ClaimRecord.model_validate(
            _claim(metric_mentions=[{"metric_id": "metric.a.001", "rendering": "rounded"}])
        )
    with pytest.raises(ValidationError):
        ClaimRecord.model_validate(_claim(status="pending"))


def test_assertion_tags_are_lowercase_tokens_and_deduplicated_by_refusal() -> None:
    with pytest.raises(ValidationError):
        ClaimRecord.model_validate(_claim(assertion_tags=["built", "built"]))
    with pytest.raises(ValidationError):
        ClaimRecord.model_validate(_claim(assertion_tags=["Built"]))
    claim = ClaimRecord.model_validate(_claim(assertion_tags=["measured", "built"]))
    assert claim.assertion_tags == ("built", "measured")


def test_blank_claim_text_is_refused() -> None:
    with pytest.raises(ValidationError):
        ClaimRecord.model_validate(_claim(text="   "))


def test_unknown_claim_field_is_refused() -> None:
    with pytest.raises(ValidationError):
        ClaimRecord.model_validate(_claim(role_family="backend"))
