"""Atomic facts and the discriminated value union (design §10).

A fact is one typed assertion about one subject. The value union is discriminated on `type` so the
payload for each kind is checked at parse time rather than by a chain of `isinstance` branches
downstream, and so `{type: date, value: "2026-13-01"}` fails before any semantic layer runs.

Two shapes deserve a note:

- A **decimal** is carried as a string (`DecimalString`). No float ever enters the bundle, because
  `json.dumps(..., allow_nan=False)` is only half the problem: `0.1` has no exact binary
  representation, so two writers could serialise the "same" number differently and the bundle
  digest would depend on which one wrote it.
- A **date range** is closed or open (`end: null`), and "start <= end" is an *exclusivity* rule the
  predicate catalog declares, not an intrinsic property of the value — an open range has no end to
  compare, and §10.4 attaches the ordering requirement to `employment.date_range` explicitly.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, model_validator

from boardwatch.profile_bundle.models.base import (
    ConflictId,
    DecimalString,
    EntityId,
    EvidenceId,
    FactId,
    HttpUrl,
    NonBlankStr,
    PredicateId,
    Sha256Digest,
    SkillId,
    SourceId,
    StrictModel,
    Surface,
    UniqueOrdered,
    UniqueSorted,
    UsageContext,
    VerificationBasis,
    VerificationState,
    YearMonth,
)


class FactValueKind(StrEnum):
    """The closed initial value union (§10.1). A new kind bumps `schema_version`."""

    STRING = "string"
    INTEGER = "integer"
    DECIMAL = "decimal"
    BOOLEAN = "boolean"
    DATE = "date"
    YEAR_MONTH = "year_month"
    DATE_RANGE = "date_range"
    URL = "url"
    STRING_LIST = "string_list"
    SKILL_REF = "skill_ref"


class StringValue(StrictModel):
    type: Literal["string"]
    value: NonBlankStr


class IntegerValue(StrictModel):
    type: Literal["integer"]
    value: int


class DecimalValue(StrictModel):
    type: Literal["decimal"]
    value: DecimalString


class BooleanValue(StrictModel):
    type: Literal["boolean"]
    value: bool


class DateValue(StrictModel):
    type: Literal["date"]
    value: date


class YearMonthValue(StrictModel):
    type: Literal["year_month"]
    value: YearMonth


class DateRangeValue(StrictModel):
    """A closed range, or an open one with `end: null`.

    Ordering is not enforced here. §10.4 declares "start <= end" as `employment.date_range`'s and
    `affiliation.date_range`'s exclusivity rule, so enforcing it intrinsically would apply it to
    predicates whose catalog row does not ask for it.
    """

    type: Literal["date_range"]
    start: date
    end: date | None


class UrlValue(StrictModel):
    type: Literal["url"]
    value: HttpUrl


class StringListValue(StrictModel):
    """An ordered list. §18 sorts *set-like* candidate lists by canonical identity; a value that is
    genuinely a sequence keeps its order, so `values` rejects duplicates without reordering."""

    type: Literal["string_list"]
    values: Annotated[tuple[NonBlankStr, ...], UniqueOrdered] = Field(min_length=1)


class SkillRefValue(StrictModel):
    type: Literal["skill_ref"]
    skill_id: SkillId


FactValue = Annotated[
    StringValue
    | IntegerValue
    | DecimalValue
    | BooleanValue
    | DateValue
    | YearMonthValue
    | DateRangeValue
    | UrlValue
    | StringListValue
    | SkillRefValue,
    Field(discriminator="type"),
]


class ImportLineage(StrictModel):
    """Where an imported fact came from. Provenance only: §18 makes upstream sources historical
    after baseline promotion, and nothing downstream may resolve `source_locator` to read them."""

    source_id: SourceId
    source_locator: NonBlankStr
    source_content_digest: Sha256Digest


class FactRecord(StrictModel):
    """One atomic assertion (§10).

    `supersedes_fact_ids` is an edge, not a mutation: a corrected fact gets a NEW `fact_id` and the
    superseded record stays immutable, so history is derivable rather than overwritten. That is
    also why a correction cannot break cardinality — cardinality counts effective facts only.
    """

    fact_id: FactId
    subject_id: EntityId
    predicate: PredicateId
    value: FactValue
    verification_state: VerificationState
    verification_basis: VerificationBasis
    usage_context: UsageContext
    evidence_ids: Annotated[tuple[EvidenceId, ...], UniqueSorted]
    allowed_surfaces: Annotated[tuple[Surface, ...], UniqueSorted]
    conflict_group_id: ConflictId | None
    reviewed_at: date
    expires_at: date | None
    supersedes_fact_ids: Annotated[tuple[FactId, ...], UniqueSorted]
    import_lineage: ImportLineage | None
    notes: str | None

    @model_validator(mode="after")
    def _no_self_supersession(self) -> FactRecord:
        if self.fact_id in self.supersedes_fact_ids:
            raise ValueError(f"{self.fact_id} cannot supersede itself")
        return self

    @property
    def value_kind(self) -> FactValueKind:
        return FactValueKind(self.value.type)
