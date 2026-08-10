"""Evidence records, captures, and redactions (design §12).

Evidence is what makes a fact re-checkable without re-reading the upstream source, so the *capture*
is the load-bearing part: "the captured material must be sufficient to evaluate the linked fact
without resolving its origin". The origin is provenance, not the evidence.

Evidence classes are a discriminated union rather than one record with optional metadata. That is
the difference between "a repository artifact happens to have a commit" and "a repository artifact
without a full commit is not a repository artifact" — with a union, the second is a parse error and
fields illegal for a class are rejected outright.

There is deliberately **no numeric confidence score**. The record states its class and whether it
meets the predicate's explicit contract; a 0.85 would invite arithmetic on judgement.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, model_validator

from boardwatch.profile_bundle.models.base import (
    BareSha256,
    EvidenceId,
    LowerToken,
    NonBlankStr,
    RecordId,
    SourceId,
    StrictModel,
    UniqueSorted,
    UtcTimestamp,
    prefix_of,
)


class CaptureMediaType(StrEnum):
    """The initial capture media allowlist (§12.2). Closed — no other media is accepted.

    It lives with the record shape it constrains rather than with the scanner that reads it, so the
    models package stays importable without the scanner and there is no import cycle between them.
    Other media require a later reviewed design, because "scan it as UTF-8 text" is the only
    inspection this phase implements.
    """

    TEXT_PLAIN = "text/plain"
    TEXT_MARKDOWN = "text/markdown"
    APPLICATION_JSON = "application/json"
    TEXT_CSV = "text/csv"


class EvidenceClass(StrEnum):
    """The closed evidence-class catalog (§12)."""

    PUBLIC_RECORD = "public_record"
    PRIVATE_DOCUMENT = "private_document"
    REPOSITORY_ARTIFACT = "repository_artifact"
    MEASURED_RESULT = "measured_result"
    OWNER_ATTESTATION = "owner_attestation"
    SECONDARY_SUMMARY = "secondary_summary"


class SufficiencyState(StrEnum):
    """Whether an owner has reviewed the capture for sufficiency (§12).

    `owner_approved` must match an approval-stamp sub-entry bound to this record's target-content
    digest. The record embeds no approval ID, which is what keeps that binding acyclic.
    """

    UNREVIEWED = "unreviewed"
    OWNER_APPROVED = "owner_approved"


class RedactionReason(StrEnum):
    """The closed redaction reasons (§12.2)."""

    CREDENTIAL = "credential"
    UNRELATED_PERSONAL = "unrelated_personal"
    DEMOGRAPHIC = "demographic"
    HEALTH = "health"
    FINANCIAL = "financial"
    THIRD_PARTY_PRIVATE = "third_party_private"
    PERSONAL_PATH = "personal_path"


class InlineCapture(StrictModel):
    """A small capture stored directly in `evidence/records.yaml`.

    Inline text contributes to identity through the normalised evidence document and has no
    separate blob leaf, so two records quoting the same excerpt do not deduplicate.
    """

    kind: Literal["inline"]
    text: NonBlankStr
    media_type: CaptureMediaType


class BlobCapture(StrictModel):
    """A larger capture stored once under `blobs/sha256/`.

    `sha256` is the bare raw-byte digest of the POST-redaction bytes. The filesystem path is never
    an identity input, which is what lets a bundle be relocated for encrypted backup.
    """

    kind: Literal["blob"]
    sha256: BareSha256
    media_type: CaptureMediaType


Capture = Annotated[InlineCapture | BlobCapture, Field(discriminator="kind")]


class Redaction(StrictModel):
    """One removed region over the UTF-8 bytes of the stored post-redaction capture (§12.2).

    Half-open `[start, end)`. The range must contain exactly the ASCII marker
    `[REDACTED:<reason>]`, so the validator can verify every recorded redaction against retained
    bytes without ever storing what was removed. Multiple removed regions therefore need multiple
    markers and multiple entries.
    """

    start: int = Field(ge=0)
    end: int = Field(ge=1)
    reason: RedactionReason

    @model_validator(mode="after")
    def _range_is_non_empty(self) -> Redaction:
        if self.end <= self.start:
            raise ValueError(f"redaction range [{self.start}, {self.end}) is empty or inverted")
        return self

    @property
    def marker(self) -> str:
        return f"[REDACTED:{self.reason.value}]"


class Locator(StrictModel):
    """Where inside the origin the capture came from.

    The design declares no closed locator-kind catalog, so `kind` is an open lowercase token rather
    than an invented enum: a fabricated catalog would reject legitimate authoring (a page range, a
    heading path, a cell reference) with no design authority behind the refusal.
    """

    kind: LowerToken
    value: NonBlankStr


class PortableOrigin(StrictModel):
    """A public record's origin, expressed portably.

    One `reference` field rather than a url/citation pair: §12 requires the origin be *portable*,
    and validation rejects absolute personal paths in it. Two optional fields would let a record
    satisfy the contract with neither filled in.
    """

    kind: LowerToken
    reference: NonBlankStr


class SufficiencyReview(StrictModel):
    state: SufficiencyState


class _EvidenceBase(StrictModel):
    """Fields every evidence record carries, whatever its class."""

    evidence_id: EvidenceId
    title: NonBlankStr
    capture: Capture
    captured_at: UtcTimestamp
    reviewed_at: date
    sufficiency_review: SufficiencyReview
    redactions: tuple[Redaction, ...]
    supports_record_ids: Annotated[tuple[RecordId, ...], UniqueSorted]
    contradicts_record_ids: Annotated[tuple[RecordId, ...], UniqueSorted]
    contextualizes_record_ids: Annotated[tuple[RecordId, ...], UniqueSorted]

    @model_validator(mode="after")
    def _redactions_do_not_overlap(self) -> _EvidenceBase:
        ordered = sorted(self.redactions, key=lambda entry: entry.start)
        for earlier, later in zip(ordered, ordered[1:], strict=False):
            if later.start < earlier.end:
                raise ValueError(
                    f"redaction ranges [{earlier.start}, {earlier.end}) and "
                    f"[{later.start}, {later.end}) overlap"
                )
        return self

    @model_validator(mode="after")
    def _one_relationship_per_target(self) -> _EvidenceBase:
        """Support, contradiction, and context are directional and mutually exclusive (§12).

        A record that both supports and contradicts the same target says nothing, and a contextual
        source that also claims support would satisfy a verification requirement it must not.
        """
        groups = (
            set(self.supports_record_ids),
            set(self.contradicts_record_ids),
            set(self.contextualizes_record_ids),
        )
        for index, first in enumerate(groups):
            for second in groups[index + 1 :]:
                shared = first & second
                if shared:
                    raise ValueError(
                        f"{self.evidence_id} declares more than one relationship to "
                        f"{sorted(shared)}"
                    )
        return self


class PublicRecordEvidence(_EvidenceBase):
    evidence_class: Literal["public_record"]
    origin: PortableOrigin
    locator: Locator


class PrivateDocumentEvidence(_EvidenceBase):
    evidence_class: Literal["private_document"]
    source_id: SourceId
    locator: Locator


class RepositoryArtifactEvidence(_EvidenceBase):
    """A repository artifact needs the FULL commit, not an abbreviated one.

    An abbreviation is ambiguous across a repository's lifetime, so it cannot identify the bytes
    the capture was taken from — which is the only thing that makes the capture re-checkable.
    """

    evidence_class: Literal["repository_artifact"]
    source_id: SourceId
    path: NonBlankStr
    repository_commit: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]


class MeasuredResultEvidence(_EvidenceBase):
    evidence_class: Literal["measured_result"]

    @model_validator(mode="after")
    def _supports_at_least_one_metric(self) -> MeasuredResultEvidence:
        if not any(prefix_of(target) == "metric" for target in self.supports_record_ids):
            raise ValueError(
                f"{self.evidence_id}: a measured_result must support at least one metric ID"
            )
        return self


class OwnerAttestationEvidence(_EvidenceBase):
    """An owner attestation needs `attested_at` and at least one supported fact.

    That the supported fact is `owner_confirmed` and carries a `confirm_fact` sub-approval is a
    graph property, checked in semantic validation: it needs the fact record and the stamp.
    """

    evidence_class: Literal["owner_attestation"]
    attested_at: date

    @model_validator(mode="after")
    def _supports_at_least_one_fact(self) -> OwnerAttestationEvidence:
        if not any(prefix_of(target) == "fact" for target in self.supports_record_ids):
            raise ValueError(
                f"{self.evidence_id}: an owner_attestation must support at least one fact ID"
            )
        return self


class SecondarySummaryEvidence(_EvidenceBase):
    """Import evidence, not final verification.

    `authoritative` is `Literal[False]`: §12 makes a secondary summary non-authoritative unless a
    predicate contract explicitly permits it, so a `true` here would be a contradiction in terms
    rather than a stronger claim.
    """

    evidence_class: Literal["secondary_summary"]
    source_id: SourceId
    locator: Locator
    authoritative: Literal[False]


EvidenceRecord = Annotated[
    PublicRecordEvidence
    | PrivateDocumentEvidence
    | RepositoryArtifactEvidence
    | MeasuredResultEvidence
    | OwnerAttestationEvidence
    | SecondarySummaryEvidence,
    Field(discriminator="evidence_class"),
]

#: Evidence classes that can never satisfy a verification requirement on their own (§12.1).
NON_VERIFYING_CLASSES: frozenset[EvidenceClass] = frozenset({EvidenceClass.SECONDARY_SUMMARY})

#: verification basis -> the evidence classes that can back it (§10.2, §12.1).
BASIS_EVIDENCE_CLASSES: dict[str, frozenset[EvidenceClass]] = {
    "public_record_verified": frozenset({EvidenceClass.PUBLIC_RECORD}),
    "private_document_verified": frozenset({EvidenceClass.PRIVATE_DOCUMENT}),
    "repository_verified": frozenset({EvidenceClass.REPOSITORY_ARTIFACT}),
    "measured": frozenset({EvidenceClass.MEASURED_RESULT}),
    "owner_attested": frozenset({EvidenceClass.OWNER_ATTESTATION}),
    "secondary_only": frozenset({EvidenceClass.SECONDARY_SUMMARY}),
    # `multiple_sources` is satisfied by two or more independently sufficient classes; which ones
    # is the predicate contract's business, so the set here is every verifying class.
    "multiple_sources": frozenset(EvidenceClass) - NON_VERIFYING_CLASSES,
}
