"""The import ledger, candidate package, and exclusions (design §18).

The denominator is the point. Gate B's measurement is `len(source-ledger.records)` — the set of
deterministic `source_record` units enumerated *before* any LLM candidate extraction — and its
imported, excluded, and review-required counts must sum to exactly that with no missing or duplicate
IDs. An LLM may extract zero or more candidate assertions from one source record, but it cannot
create, omit, renumber, or assign IDs to the denominator.

That is why identity here is *derived*, never authored in the sense of "proposed":
`source-record.<64hex>` comes from `["source-record", source_id, normalized_locator]` and
`candidate.<64hex>` from `["candidate", source_record_id, predicate, canonicalized_typed_value]`.
Content digests are *occurrence lineage*, not identity, so changed bytes at the same logical locator
append an occurrence rather than churning the denominator and every downstream candidate ID.

`record_count` is deliberately not a field. §18 derives it as `len(records)`; an authored count is a
second source of truth for the one number Gate B is measured against.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, PositiveInt, model_validator

from boardwatch.profile_bundle.models.base import (
    CandidateId,
    LowerSlug,
    NonBlankStr,
    PredicateId,
    Sha256Digest,
    SourceId,
    SourceRecordId,
    StrictModel,
    UniqueOrdered,
    UniqueSorted,
)
from boardwatch.profile_bundle.models.facts import FactValue


class Disposition(StrEnum):
    """Every enumerated record gets exactly one (§18). `review_required` is a Gate B blocker:
    an undispositioned record is the "unexplained record" the gate requires to be zero."""

    IMPORTED = "imported"
    EXCLUDED = "excluded"
    REVIEW_REQUIRED = "review_required"


class ExclusionReason(StrEnum):
    """The closed exclusion reasons (§18)."""

    DUPLICATE = "duplicate"
    ADMINISTRATIVE_NOISE = "administrative_noise"
    NON_PROFESSIONAL = "non_professional"
    PROHIBITED_SENSITIVE = "prohibited_sensitive"
    SUPERSEDED_SOURCE = "superseded_source"
    NO_CANDIDATE_ASSERTION = "no_candidate_assertion"
    OWNER_EXCLUDED = "owner_excluded"


class CompleteFileScope(StrictModel):
    kind: Literal["complete_file"]


class SelectedSectionsScope(StrictModel):
    """A repository-Markdown source's approved scope.

    `locators` is a non-empty, order-preserving list of normalised heading paths. Order is preserved
    because widening or reordering the approved scope changes the `approve_source_scope` target
    digest, which is the whole point: a scope change must cost a new owner approval.
    """

    kind: Literal["selected_sections"]
    locators: Annotated[tuple[NonBlankStr, ...], UniqueOrdered] = Field(min_length=1)


#: A discriminated object, never a scalar (§18): `approved_scope: complete_file` as a bare string
#: could not later grow locators without changing its type.
ApprovedScope = Annotated[CompleteFileScope | SelectedSectionsScope, Field(discriminator="kind")]


class SourceLedgerSource(StrictModel):
    """One enumerated source's ledger entry (§18).

    Owns only enumeration, scope, digest, and record state. `source_kind` and `portable_locator`
    live in `policy/sources.yaml` and are deliberately not repeated here — two homes for one field
    is two chances to disagree.
    """

    source_id: SourceId
    enumerator_id: LowerSlug
    enumerator_version: PositiveInt
    source_content_digest: Sha256Digest
    approved_scope: ApprovedScope
    source_record_ids: Annotated[tuple[SourceRecordId, ...], UniqueOrdered]


class SourceLedgerRecord(StrictModel):
    """One deterministically enumerated source record — one unit of the Gate B denominator."""

    source_record_id: SourceRecordId
    source_id: SourceId
    normalized_locator: NonBlankStr
    disposition: Disposition
    candidate_ids: Annotated[tuple[CandidateId, ...], UniqueSorted]

    @model_validator(mode="after")
    def _imported_records_name_a_candidate(self) -> SourceLedgerRecord:
        """§18: "Imported records must name at least one deterministic candidate ID."

        A record imported with no candidate has been counted in the denominator's numerator while
        contributing nothing, which is how a denominator silently stops meaning anything.
        """
        if self.disposition is Disposition.IMPORTED and not self.candidate_ids:
            raise ValueError(
                f"{self.source_record_id}: disposition is imported but names no candidate; use "
                "`excluded` with reason `no_candidate_assertion` instead"
            )
        if self.disposition is not Disposition.IMPORTED and self.candidate_ids:
            raise ValueError(
                f"{self.source_record_id}: disposition is {self.disposition.value} but names "
                f"{len(self.candidate_ids)} candidate(s)"
            )
        return self


class SourceLedger(StrictModel):
    """`imports/source-ledger.yaml`."""

    ledger_version: PositiveInt
    sources: tuple[SourceLedgerSource, ...]
    records: tuple[SourceLedgerRecord, ...]

    @model_validator(mode="after")
    def _per_source_lists_match_the_records_exactly(self) -> SourceLedger:
        """§18: per-source ID lists must equal the matching records' IDs in adapter order, with no
        extra, missing, reordered, or duplicate ID on either side."""
        seen: set[str] = set()
        for record in self.records:
            if record.source_record_id in seen:
                raise ValueError(f"duplicate source_record_id {record.source_record_id!r}")
            seen.add(record.source_record_id)

        source_ids = [source.source_id for source in self.sources]
        if len(set(source_ids)) != len(source_ids):
            raise ValueError("duplicate source_id in the ledger's `sources`")

        by_source: dict[str, list[str]] = {source_id: [] for source_id in source_ids}
        for record in self.records:
            if record.source_id not in by_source:
                raise ValueError(
                    f"{record.source_record_id}: source {record.source_id!r} is not enumerated in "
                    "this ledger"
                )
            by_source[record.source_id].append(record.source_record_id)

        for source in self.sources:
            expected = list(source.source_record_ids)
            actual = by_source[source.source_id]
            if expected != actual:
                raise ValueError(
                    f"{source.source_id}: source_record_ids disagree with the ledger records "
                    f"({len(expected)} declared, {len(actual)} present, order significant)"
                )
        return self

    @property
    def record_count(self) -> int:
        """The Gate B denominator. Derived, never authored (§18)."""
        return len(self.records)

    def counts_by_disposition(self) -> dict[Disposition, int]:
        counts = dict.fromkeys(Disposition, 0)
        for record in self.records:
            counts[record.disposition] += 1
        return counts


class CandidateOccurrence(StrictModel):
    """One (source snapshot, normalised record bytes) sighting of a candidate value.

    Re-enumerating changed source bytes at the same locator APPENDS an occurrence rather than
    replacing prior lineage, so the history of where a value was seen survives a source edit.
    """

    source_content_digest: Sha256Digest
    record_content_digest: Sha256Digest


class CandidateRecord(StrictModel):
    """One typed candidate assertion with its append-only occurrences (§18)."""

    candidate_id: CandidateId
    source_record_id: SourceRecordId
    predicate: PredicateId
    canonicalized_typed_value: FactValue
    original_display_value: NonBlankStr
    occurrences: tuple[CandidateOccurrence, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _occurrence_pairs_are_unique(self) -> CandidateRecord:
        """§18: "The pair is unique within one candidate." A repeated pair is the same sighting
        recorded twice, which would inflate lineage without adding evidence."""
        pairs = [
            (occurrence.source_content_digest, occurrence.record_content_digest)
            for occurrence in self.occurrences
        ]
        if len(set(pairs)) != len(pairs):
            raise ValueError(f"{self.candidate_id}: duplicate source/record digest occurrence")
        return self


class CandidatePackage(StrictModel):
    """`imports/candidates.yaml`."""

    candidates_version: PositiveInt
    candidates: tuple[CandidateRecord, ...]

    @model_validator(mode="after")
    def _candidate_ids_are_unique(self) -> CandidatePackage:
        seen: set[str] = set()
        for candidate in self.candidates:
            if candidate.candidate_id in seen:
                raise ValueError(f"duplicate candidate_id {candidate.candidate_id!r}")
            seen.add(candidate.candidate_id)
        return self

    @property
    def by_id(self) -> dict[str, CandidateRecord]:
        return {candidate.candidate_id: candidate for candidate in self.candidates}


class ExclusionRecord(StrictModel):
    """One excluded source record and why (§18). Every exclusion requires a rationale.

    `owner_excluded` additionally requires an `approve_source_record_exclusion` sub-approval bound
    to the excluded record's target-content digest — a graph check, since it needs the stamp.
    """

    source_record_id: SourceRecordId
    reason: ExclusionReason
    rationale: NonBlankStr


class ExclusionLedger(StrictModel):
    """`imports/exclusions.yaml`."""

    exclusions_version: PositiveInt
    exclusions: tuple[ExclusionRecord, ...]

    @model_validator(mode="after")
    def _one_exclusion_per_record(self) -> ExclusionLedger:
        seen: set[str] = set()
        for exclusion in self.exclusions:
            if exclusion.source_record_id in seen:
                raise ValueError(
                    f"{exclusion.source_record_id!r} is excluded twice; two reasons for one "
                    "record makes the exclusion-by-reason totals overcount the denominator"
                )
            seen.add(exclusion.source_record_id)
        return self

    def counts_by_reason(self) -> dict[ExclusionReason, int]:
        counts = dict.fromkeys(ExclusionReason, 0)
        for exclusion in self.exclusions:
            counts[exclusion.reason] += 1
        return counts

    @property
    def by_record(self) -> dict[str, ExclusionRecord]:
        return {exclusion.source_record_id: exclusion for exclusion in self.exclusions}


class ExtractionReportReason(StrEnum):
    """The closed reasons a `review_required` record stays unresolved (§6.3a).

    The report is the drain's durable carrier: exactly one reason is attached to every
    `review_required` record, and none to an `imported` or `excluded` one. It explains the resulting
    unresolved state and never asserts a disposition — disposition stays derived from candidates and
    exclusions. Out-of-catalog is a failure, never a new bucket.
    """

    NO_MAPPING_FOR_LOCATOR = "no_mapping_for_locator"
    UNSUPPORTED_ENTRY_KIND = "unsupported_entry_kind"
    SPAN_NOT_GROUNDED = "span_not_grounded"
    VALUE_NOT_TYPEABLE = "value_not_typeable"
    FREE_TEXT_DEFERRED = "free_text_deferred"
    NO_PREDICATE_EXISTS = "no_predicate_exists"


class ExtractionReportEntry(StrictModel):
    """One `review_required` record and the closed reason it stays unresolved (§6.3a)."""

    source_record_id: SourceRecordId
    reason: ExtractionReportReason


class ExtractionReport(StrictModel):
    """`imports/extraction-report.yaml`.

    Keyed by `source_record_id` and bound into the candidate digest, it explains every
    `review_required` record without asserting disposition (§6.3a). A fresh bundle has no sources,
    so the seed is empty.
    """

    report_version: PositiveInt
    entries: tuple[ExtractionReportEntry, ...]

    @model_validator(mode="after")
    def _one_reason_per_record(self) -> ExtractionReport:
        seen: set[str] = set()
        for entry in self.entries:
            if entry.source_record_id in seen:
                raise ValueError(
                    f"{entry.source_record_id!r} is explained twice; two reasons for one record "
                    "makes the reason-by-reason totals overcount the denominator"
                )
            seen.add(entry.source_record_id)
        return self

    def counts_by_reason(self) -> dict[ExtractionReportReason, int]:
        counts = dict.fromkeys(ExtractionReportReason, 0)
        for entry in self.entries:
            counts[entry.reason] += 1
        return counts

    @property
    def by_record(self) -> dict[str, ExtractionReportEntry]:
        return {entry.source_record_id: entry for entry in self.entries}
