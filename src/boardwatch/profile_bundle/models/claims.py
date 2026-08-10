"""Approved claim candidates (design §15).

The bundle stores owner-approved *wording* without making it runtime-generative. A claim is a
candidate sentence plus the exact records that justify it, so the checks that matter are
mechanical: every numeral in the text traces to one referenced metric's allowed rendering, every
referenced metric that does not appear in the text is declared `qualitative_only`, forbidden
phrasings are absent, and protected tokens survive.

The validator does not pretend to prove natural-language entailment. Owner approval plus structured
references establish that the wording is an *allowed candidate*; selection, composition, rewording,
and semantic judging are all deferred to the tailoring design.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated

from boardwatch.profile_bundle.models.base import (
    ClaimId,
    EntityId,
    FactId,
    LowerToken,
    MetricId,
    NonBlankStr,
    StrictModel,
    Surface,
    UniqueSorted,
)


class ClaimType(StrEnum):
    """The closed initial claim-type catalog (§15).

    The first three live in `claims/bullet-candidates.yaml`; `professional_summary` lives only in
    `claims/summary-candidates.yaml`. A type in the wrong file is a hard validation failure, which
    is what stops a summary from being selected as a bullet.
    """

    RESPONSIBILITY = "responsibility"
    ACCOMPLISHMENT = "accomplishment"
    PROJECT_SUMMARY = "project_summary"
    PROFESSIONAL_SUMMARY = "professional_summary"


#: The three types `claims/bullet-candidates.yaml` owns.
BULLET_CLAIM_TYPES: frozenset[ClaimType] = frozenset(
    {ClaimType.RESPONSIBILITY, ClaimType.ACCOMPLISHMENT, ClaimType.PROJECT_SUMMARY}
)
#: The one type `claims/summary-candidates.yaml` owns.
SUMMARY_CLAIM_TYPES: frozenset[ClaimType] = frozenset({ClaimType.PROFESSIONAL_SUMMARY})


class ClaimStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class MetricRendering(StrEnum):
    """How a referenced metric appears in the claim text.

    §15 names `qualitative_only` explicitly and requires it for "a referenced metric omitted from
    the text". A metric whose figure DOES appear needs a value too, and `rendered` is that value:
    the enum must have two members or the distinction the design draws is unrepresentable. The
    inference is recorded here rather than buried, because a third rendering would be a schema bump.
    """

    RENDERED = "rendered"
    QUALITATIVE_ONLY = "qualitative_only"


class MetricMention(StrictModel):
    metric_id: MetricId
    rendering: MetricRendering


class ClaimRecord(StrictModel):
    """One approved-or-proposed wording (§15).

    `required_fact_ids` may be empty at parse time: "an approved claim must reference at least one
    fact" is status-dependent, so enforcing it intrinsically would make a `draft` claim
    unrepresentable while the owner is still assembling its support.

    Every required record is *conjunctive* support for the complete wording, which is why §10.3
    makes claim surfaces a subset of the INTERSECTION of all required facts' and metrics' surfaces
    rather than the union.
    """

    claim_id: ClaimId
    subject_id: EntityId
    claim_type: ClaimType
    text: NonBlankStr
    required_fact_ids: Annotated[tuple[FactId, ...], UniqueSorted]
    required_metric_ids: Annotated[tuple[MetricId, ...], UniqueSorted]
    metric_mentions: tuple[MetricMention, ...]
    status: ClaimStatus
    allowed_surfaces: Annotated[tuple[Surface, ...], UniqueSorted]
    assertion_tags: Annotated[tuple[LowerToken, ...], UniqueSorted]
    reviewed_at: date

    @property
    def mention_by_metric(self) -> dict[str, MetricRendering]:
        return {mention.metric_id: mention.rendering for mention in self.metric_mentions}
