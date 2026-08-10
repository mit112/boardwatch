"""Metrics as first-class typed facts (design §11).

"A number embedded only in claim prose is not an authoritative metric." That is the whole point of
this module: the figure, its unit, its qualifier, the method that produced it, the context it is
valid in, and the wordings it may appear in are all separate typed fields, so a later projection
cannot round `~120 requests/s` into "thousands of requests per second" without failing a check.

Changing a protected value, unit, subject, or qualifier creates a NEW metric record that supersedes
the old one. It is never an in-place prose edit, which is why nothing here is mutable.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated

from pydantic import Field

from boardwatch.profile_bundle.models.base import (
    DecimalString,
    EntityId,
    EvidenceId,
    LowerToken,
    MetricId,
    NonBlankStr,
    StrictModel,
    Surface,
    UniqueOrdered,
    UniqueSorted,
    VerificationState,
)


class MetricKind(StrEnum):
    """The closed initial `metric_kind` catalog (§11)."""

    COUNT = "count"
    DURATION = "duration"
    RATE = "rate"
    THROUGHPUT = "throughput"
    LATENCY = "latency"
    PERCENTAGE = "percentage"
    CURRENCY = "currency"
    SIZE = "size"
    RANK = "rank"
    SCORE = "score"


class MetricQualifier(StrEnum):
    """How exactly the number should be read (§11)."""

    EXACT = "exact"
    APPROXIMATE = "approximate"
    AT_LEAST = "at_least"
    MORE_THAN = "more_than"
    AT_MOST = "at_most"
    RANGE = "range"


class CaveatSeverity(StrEnum):
    """A `context_required` caveat must travel with any later projection of the figure; a
    `disqualifying` one makes the metric ineligible until a new metric supersedes it (§11)."""

    INFORMATIONAL = "informational"
    CONTEXT_REQUIRED = "context_required"
    DISQUALIFYING = "disqualifying"


class MetricValue(StrictModel):
    """The number, its unit key, and its qualifier.

    `number` is a decimal string, never a float: `0.1` has no exact binary form, so two writers
    could serialise the same measurement differently and the bundle digest would disagree.
    `unit` is a key into the revision-owned `policy/units.yaml`; closure is checked semantically.
    """

    number: DecimalString
    unit: LowerToken
    qualifier: MetricQualifier


class MetricCaveat(StrictModel):
    """A typed caveat. Severity is enforced; the text is for the human reading the projection."""

    severity: CaveatSeverity
    text: NonBlankStr


class MetricRecord(StrictModel):
    """One measured claim about one subject (§11).

    `allowed_phrasings` is non-empty by contract — §11 requires "at least one allowed phrasing"
    before a metric can be considered for a future résumé — and `evidence_ids` is non-empty because
    a metric with no evidence is a number somebody remembered.

    `protected_tokens` may be empty: §15 cross-checks "any rendered protected metric tokens", so a
    metric that declares none simply has nothing to preserve. It is a required key rather than a
    defaulted one, so "we decided there are none" is visible in the diff.
    """

    metric_id: MetricId
    subject_id: EntityId
    metric_kind: MetricKind
    value: MetricValue
    display_value: NonBlankStr
    measurement_context: NonBlankStr
    measurement_method: NonBlankStr
    evidence_ids: Annotated[tuple[EvidenceId, ...], UniqueSorted] = Field(min_length=1)
    verification_state: VerificationState
    allowed_surfaces: Annotated[tuple[Surface, ...], UniqueSorted]
    allowed_phrasings: Annotated[tuple[NonBlankStr, ...], UniqueOrdered] = Field(min_length=1)
    forbidden_phrasings: Annotated[tuple[NonBlankStr, ...], UniqueOrdered]
    protected_tokens: Annotated[tuple[NonBlankStr, ...], UniqueOrdered]
    caveats: tuple[MetricCaveat, ...]
    reviewed_at: date

    @property
    def has_disqualifying_caveat(self) -> bool:
        return any(caveat.severity is CaveatSeverity.DISQUALIFYING for caveat in self.caveats)

    @property
    def context_required_caveats(self) -> tuple[MetricCaveat, ...]:
        return tuple(
            caveat for caveat in self.caveats if caveat.severity is CaveatSeverity.CONTEXT_REQUIRED
        )
