"""Evidence record shapes: classes, captures, redactions (design §12).

The discriminated union is the enforcement mechanism, so the tests probe it from both sides: a class
missing one of its required fields must fail, and a class carrying another class's field must fail
too. Without the second half, `private_document` could be authored with a `repository_commit` and a
reader would reasonably believe the capture was pinned to a commit.
"""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from boardwatch.profile_bundle.models.evidence import (
    BASIS_EVIDENCE_CLASSES,
    NON_VERIFYING_CLASSES,
    BlobCapture,
    Capture,
    CaptureMediaType,
    EvidenceClass,
    EvidenceRecord,
    InlineCapture,
    MeasuredResultEvidence,
    Redaction,
    RedactionReason,
    RepositoryArtifactEvidence,
    SufficiencyState,
)

EVIDENCE_ADAPTER = TypeAdapter(EvidenceRecord)
CAPTURE_ADAPTER = TypeAdapter(Capture)
BARE = "a" * 64
COMMIT = "0123456789abcdef0123456789abcdef01234567"


def _common(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "evidence_id": "evidence.packet-pantry.benchmark.001",
        "title": "Packet Pantry local throughput baseline",
        "capture": {
            "kind": "inline",
            "text": "Synthetic evidence excerpt sufficient to review the linked record.",
            "media_type": "text/plain",
        },
        "captured_at": "2026-08-10T12:00:00Z",
        "reviewed_at": "2026-08-10",
        "sufficiency_review": {"state": "owner_approved"},
        "redactions": [],
        "supports_record_ids": [],
        "contradicts_record_ids": [],
        "contextualizes_record_ids": [],
    }
    payload.update(overrides)
    return payload


def _measured(**overrides: object) -> dict[str, object]:
    payload = _common(
        evidence_class="measured_result",
        supports_record_ids=["metric.packet-pantry.throughput.001"],
    )
    payload.update(overrides)
    return payload


# --------------------------------------------------------------------------------------
# closed catalogs
# --------------------------------------------------------------------------------------


def test_evidence_classes_are_the_closed_six() -> None:
    assert {member.value for member in EvidenceClass} == {
        "public_record",
        "private_document",
        "repository_artifact",
        "measured_result",
        "owner_attestation",
        "secondary_summary",
    }


def test_sufficiency_states_are_unreviewed_and_owner_approved_only() -> None:
    assert {member.value for member in SufficiencyState} == {"unreviewed", "owner_approved"}


def test_redaction_reasons_are_the_closed_seven() -> None:
    assert {member.value for member in RedactionReason} == {
        "credential",
        "unrelated_personal",
        "demographic",
        "health",
        "financial",
        "third_party_private",
        "personal_path",
    }


def test_a_secondary_summary_can_never_verify_on_its_own() -> None:
    assert NON_VERIFYING_CLASSES == frozenset({EvidenceClass.SECONDARY_SUMMARY})
    assert BASIS_EVIDENCE_CLASSES["secondary_only"] == frozenset(
        {EvidenceClass.SECONDARY_SUMMARY}
    )
    assert EvidenceClass.SECONDARY_SUMMARY not in BASIS_EVIDENCE_CLASSES["multiple_sources"]


def test_every_verification_basis_maps_to_at_least_one_evidence_class() -> None:
    from boardwatch.profile_bundle.models.base import VerificationBasis

    assert set(BASIS_EVIDENCE_CLASSES) == {member.value for member in VerificationBasis}
    assert all(classes for classes in BASIS_EVIDENCE_CLASSES.values())


# --------------------------------------------------------------------------------------
# captures
# --------------------------------------------------------------------------------------


def test_inline_and_blob_captures_are_mutually_exclusive_variants() -> None:
    inline = CAPTURE_ADAPTER.validate_python(
        {"kind": "inline", "text": "excerpt", "media_type": "text/markdown"}
    )
    blob = CAPTURE_ADAPTER.validate_python(
        {"kind": "blob", "sha256": BARE, "media_type": "text/markdown"}
    )
    assert isinstance(inline, InlineCapture)
    assert isinstance(blob, BlobCapture)


def test_a_capture_cannot_be_both_inline_and_blob() -> None:
    with pytest.raises(ValidationError):
        CAPTURE_ADAPTER.validate_python(
            {"kind": "inline", "text": "x", "sha256": BARE, "media_type": "text/plain"}
        )
    with pytest.raises(ValidationError):
        CAPTURE_ADAPTER.validate_python(
            {"kind": "blob", "sha256": BARE, "text": "x", "media_type": "text/plain"}
        )


def test_a_capture_with_no_discriminant_is_refused() -> None:
    with pytest.raises(ValidationError):
        CAPTURE_ADAPTER.validate_python({"text": "x", "media_type": "text/plain"})


@pytest.mark.parametrize(
    "media",
    ["application/pdf", "image/png", "text/html", "application/octet-stream", "text/plain "],
)
def test_media_outside_the_allowlist_is_refused(media: str) -> None:
    with pytest.raises(ValidationError):
        CAPTURE_ADAPTER.validate_python({"kind": "inline", "text": "x", "media_type": media})


def test_the_media_allowlist_is_the_declared_four() -> None:
    assert {member.value for member in CaptureMediaType} == {
        "text/plain",
        "text/markdown",
        "application/json",
        "text/csv",
    }


def test_blob_digest_must_be_bare_lowercase_hex() -> None:
    for bad in ["sha256:" + BARE, BARE.upper(), "a" * 63, ""]:
        with pytest.raises(ValidationError):
            CAPTURE_ADAPTER.validate_python(
                {"kind": "blob", "sha256": bad, "media_type": "text/plain"}
            )


def test_inline_capture_refuses_blank_text() -> None:
    with pytest.raises(ValidationError):
        CAPTURE_ADAPTER.validate_python(
            {"kind": "inline", "text": "   ", "media_type": "text/plain"}
        )


# --------------------------------------------------------------------------------------
# per-class contracts
# --------------------------------------------------------------------------------------


def test_public_record_requires_a_portable_origin_and_locator() -> None:
    record = EVIDENCE_ADAPTER.validate_python(
        _common(
            evidence_class="public_record",
            origin={"kind": "journal_article", "reference": "Example Journal 12(3), 2026"},
            locator={"kind": "section", "value": "Results"},
        )
    )
    assert record.evidence_class == "public_record"
    with pytest.raises(ValidationError):
        EVIDENCE_ADAPTER.validate_python(
            _common(
                evidence_class="public_record",
                locator={"kind": "section", "value": "Results"},
            )
        )


def test_private_document_requires_a_logical_source_id_and_locator() -> None:
    record = EVIDENCE_ADAPTER.validate_python(
        _common(
            evidence_class="private_document",
            source_id="source.example-transcript",
            locator={"kind": "page", "value": "2"},
        )
    )
    assert record.evidence_class == "private_document"
    with pytest.raises(ValidationError):
        EVIDENCE_ADAPTER.validate_python(
            _common(evidence_class="private_document", locator={"kind": "page", "value": "2"})
        )


def test_repository_artifact_requires_the_full_commit() -> None:
    record = EVIDENCE_ADAPTER.validate_python(
        _common(
            evidence_class="repository_artifact",
            source_id="source.packet-pantry-repository",
            path="docs/baseline.md",
            repository_commit=COMMIT,
        )
    )
    assert isinstance(record, RepositoryArtifactEvidence)
    for bad in [COMMIT[:7], COMMIT.upper(), COMMIT + "0", ""]:
        with pytest.raises(ValidationError):
            EVIDENCE_ADAPTER.validate_python(
                _common(
                    evidence_class="repository_artifact",
                    source_id="source.x",
                    path="docs/baseline.md",
                    repository_commit=bad,
                )
            )


def test_measured_result_requires_at_least_one_supported_metric() -> None:
    record = EVIDENCE_ADAPTER.validate_python(_measured())
    assert isinstance(record, MeasuredResultEvidence)
    with pytest.raises(ValidationError):
        EVIDENCE_ADAPTER.validate_python(
            _common(evidence_class="measured_result", supports_record_ids=[])
        )
    with pytest.raises(ValidationError):
        EVIDENCE_ADAPTER.validate_python(
            _common(
                evidence_class="measured_result",
                supports_record_ids=["fact.packet-pantry.language.001"],
            )
        )


def test_owner_attestation_requires_attested_at_and_a_supported_fact() -> None:
    record = EVIDENCE_ADAPTER.validate_python(
        _common(
            evidence_class="owner_attestation",
            attested_at="2026-08-10",
            supports_record_ids=["fact.example.headline.001"],
        )
    )
    assert record.evidence_class == "owner_attestation"
    with pytest.raises(ValidationError):
        EVIDENCE_ADAPTER.validate_python(
            _common(
                evidence_class="owner_attestation",
                supports_record_ids=["fact.example.headline.001"],
            )
        )
    with pytest.raises(ValidationError):
        EVIDENCE_ADAPTER.validate_python(
            _common(
                evidence_class="owner_attestation",
                attested_at="2026-08-10",
                supports_record_ids=["metric.a.001"],
            )
        )


def test_secondary_summary_must_declare_authoritative_false() -> None:
    record = EVIDENCE_ADAPTER.validate_python(
        _common(
            evidence_class="secondary_summary",
            source_id="source.legacy-notes",
            locator={"kind": "section", "value": "Stack"},
            authoritative=False,
        )
    )
    assert record.evidence_class == "secondary_summary"
    with pytest.raises(ValidationError):
        EVIDENCE_ADAPTER.validate_python(
            _common(
                evidence_class="secondary_summary",
                source_id="source.legacy-notes",
                locator={"kind": "section", "value": "Stack"},
                authoritative=True,
            )
        )


@pytest.mark.parametrize(
    ("evidence_class", "illegal_field", "value"),
    [
        ("measured_result", "repository_commit", COMMIT),
        ("measured_result", "source_id", "source.x"),
        ("private_document", "repository_commit", COMMIT),
        ("private_document", "authoritative", False),
        ("repository_artifact", "locator", {"kind": "section", "value": "x"}),
        ("owner_attestation", "source_id", "source.x"),
    ],
)
def test_a_field_illegal_for_a_class_is_rejected(
    evidence_class: str, illegal_field: str, value: object
) -> None:
    payload = _common(evidence_class=evidence_class)
    if evidence_class == "measured_result":
        payload["supports_record_ids"] = ["metric.a.001"]
    if evidence_class == "owner_attestation":
        payload["attested_at"] = "2026-08-10"
        payload["supports_record_ids"] = ["fact.a.001"]
    if evidence_class == "private_document":
        payload["source_id"] = "source.x"
        payload["locator"] = {"kind": "page", "value": "1"}
    if evidence_class == "repository_artifact":
        payload["source_id"] = "source.x"
        payload["path"] = "docs/a.md"
        payload["repository_commit"] = COMMIT
    payload[illegal_field] = value
    with pytest.raises(ValidationError):
        EVIDENCE_ADAPTER.validate_python(payload)


def test_unknown_evidence_class_is_refused() -> None:
    with pytest.raises(ValidationError):
        EVIDENCE_ADAPTER.validate_python(_common(evidence_class="hearsay"))


# --------------------------------------------------------------------------------------
# relationships
# --------------------------------------------------------------------------------------


def test_relationship_directions_are_mutually_exclusive_per_target() -> None:
    """A record that both supports and contradicts the same target asserts nothing."""
    with pytest.raises(ValidationError):
        EVIDENCE_ADAPTER.validate_python(
            _measured(contradicts_record_ids=["metric.packet-pantry.throughput.001"])
        )
    with pytest.raises(ValidationError):
        EVIDENCE_ADAPTER.validate_python(
            _measured(contextualizes_record_ids=["metric.packet-pantry.throughput.001"])
        )


def test_a_contextual_target_may_differ_from_a_supported_one() -> None:
    record = EVIDENCE_ADAPTER.validate_python(
        _measured(contextualizes_record_ids=["fact.packet-pantry.language.001"])
    )
    assert record.contextualizes_record_ids == ("fact.packet-pantry.language.001",)


def test_relationship_lists_refuse_duplicates_and_normalise_order() -> None:
    with pytest.raises(ValidationError):
        EVIDENCE_ADAPTER.validate_python(
            _measured(supports_record_ids=["metric.a.001", "metric.a.001"])
        )
    record = EVIDENCE_ADAPTER.validate_python(
        _measured(supports_record_ids=["metric.z.001", "metric.a.001"])
    )
    assert record.supports_record_ids == ("metric.a.001", "metric.z.001")


# --------------------------------------------------------------------------------------
# redactions
# --------------------------------------------------------------------------------------


def test_redaction_marker_is_derived_from_its_reason() -> None:
    redaction = Redaction.model_validate({"start": 4, "end": 25, "reason": "credential"})
    assert redaction.marker == "[REDACTED:credential]"


@pytest.mark.parametrize(
    "payload",
    [
        {"start": 5, "end": 5, "reason": "credential"},
        {"start": 5, "end": 4, "reason": "credential"},
        {"start": -1, "end": 4, "reason": "credential"},
        {"start": 0, "end": 4, "reason": "because"},
        {"start": 0, "end": 4},
        {"start": 0, "end": 4, "reason": "credential", "text": "removed"},
    ],
)
def test_malformed_redactions_are_refused(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Redaction.model_validate(payload)


def test_redaction_never_stores_the_removed_content() -> None:
    """The validator verifies a redaction against RETAINED bytes; storing the removal would
    reintroduce exactly the material the redaction exists to drop."""
    assert set(Redaction.model_fields) == {"start", "end", "reason"}


def test_overlapping_redactions_are_refused() -> None:
    with pytest.raises(ValidationError):
        EVIDENCE_ADAPTER.validate_python(
            _measured(
                redactions=[
                    {"start": 0, "end": 20, "reason": "credential"},
                    {"start": 10, "end": 30, "reason": "financial"},
                ]
            )
        )


def test_adjacent_redactions_are_legal() -> None:
    record = EVIDENCE_ADAPTER.validate_python(
        _measured(
            redactions=[
                {"start": 0, "end": 20, "reason": "credential"},
                {"start": 20, "end": 40, "reason": "financial"},
            ]
        )
    )
    assert len(record.redactions) == 2


# --------------------------------------------------------------------------------------
# timestamps
# --------------------------------------------------------------------------------------


def test_captured_at_must_carry_an_explicit_offset() -> None:
    with pytest.raises(ValidationError):
        EVIDENCE_ADAPTER.validate_python(_measured(captured_at="2026-08-10T12:00:00"))


def test_captured_at_is_normalised_to_utc() -> None:
    record = EVIDENCE_ADAPTER.validate_python(_measured(captured_at="2026-08-10T14:00:00+02:00"))
    assert record.captured_at.isoformat() == "2026-08-10T12:00:00+00:00"
