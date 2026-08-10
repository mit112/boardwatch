"""Strict base model, typed stable IDs, and the shared closed scalars (design §8, §10).

## Why IDs are constrained strings rather than wrapper models

Design §8 requires that "every reference field is typed to its target record kind, so an evidence
ID cannot satisfy a metric reference merely because the string exists". A `StringConstraints`
pattern per prefix delivers exactly that: `MetricId` will not accept `evidence.x`, and the refusal
happens at parse time, before any graph validation runs.

A `RootModel[str]` wrapper per prefix was rejected. Pydantic model equality compares the class as
well as the value, so `FactId("fact.a") != RecordId("fact.a")`, which would make the global ID
index — the thing that proves IDs are unique *across* kinds — silently partition by wrapper class.
The uniqueness check that matters most would then pass on a duplicate.

## Why set-like fields are sorted tuples rather than `frozenset`

Design §7 makes list order significant and requires that the same logical content always produce
the same digest. `frozenset` iterates in hash order, so `model_dump(mode="json")` would emit an
arbitrary list order and the bundle digest would depend on interpreter state. Set-like fields are
therefore normalised to a duplicate-free, canonically sorted tuple: their order carries no
meaning, so normalising it is safe, and it makes identity reproducible. Duplicates are *rejected*,
not folded, because a repeated surface in authored YAML is an authoring mistake worth a
diagnostic.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Final

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, StringConstraints

# --------------------------------------------------------------------------------------
# Strict base
# --------------------------------------------------------------------------------------


class StrictModel(BaseModel):
    """Every bundle record: unknown fields refused, instances immutable.

    `extra="forbid"` is load-bearing rather than tidy. A typo'd field name would otherwise be
    dropped silently, so an authored `allowed_surface: [resume]` would leave the record with no
    surfaces at all and the bundle would still validate.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


# --------------------------------------------------------------------------------------
# Set-like and ordered list normalisation
# --------------------------------------------------------------------------------------


def _comparable(item: Any) -> Any:
    """A hashable stand-in for duplicate detection over not-yet-validated input."""
    if isinstance(item, dict):
        return tuple(sorted((key, _comparable(val)) for key, val in item.items()))
    if isinstance(item, (list, tuple)):
        return tuple(_comparable(entry) for entry in item)
    return item


def _reject_duplicates(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        seen: list[Any] = []
        for item in value:
            key = _comparable(item)
            if key in seen:
                raise ValueError(f"duplicate list item {item!r}")
            seen.append(key)
    return value


def _unique_sorted(value: Any) -> Any:
    """Refuse duplicates, then order canonically. Only for fields whose order is meaningless."""
    _reject_duplicates(value)
    if isinstance(value, (list, tuple)):
        return sorted(value, key=lambda item: str(_comparable(item)))
    return value


#: For fields whose order carries no meaning: surfaces, evidence links, alias lists, kind sets.
UniqueSorted: Final = BeforeValidator(_unique_sorted)
#: For fields whose order IS meaningful: allowed phrasings, ledger sequences, scope locators.
UniqueOrdered: Final = BeforeValidator(_reject_duplicates)


# --------------------------------------------------------------------------------------
# Digests, dates, and small scalars
# --------------------------------------------------------------------------------------

Sha256Digest = Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]
BareSha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]

#: `YYYY-MM`. A year-month is a distinct value type in §10.1 and must not decay to a date.
YearMonth = Annotated[str, StringConstraints(pattern=r"^[0-9]{4}-(?:0[1-9]|1[0-2])$")]

#: A decimal is carried as a string (§10.1) so no float ever enters an identity computation.
DecimalString = Annotated[str, StringConstraints(pattern=r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")]

#: `http`/`https` only, anchored, so every other scheme is refused. A mail-scheme URL in particular
#: is a contact channel wearing an `entity.url`'s clothes — contacts are typed records on the person
#: entity (§9) and have their own surface policy — and the repository's generalization scan treats
#: that shape as a personal profile URL, so it must never appear in tracked example data either.
HttpUrl = Annotated[str, StringConstraints(pattern=r"^https?://[^\s<>\"]+$", max_length=2048)]

NonBlankStr = Annotated[str, StringConstraints(min_length=1, pattern=r"\S")]

#: A lowercase snake token: unit IDs, assertion tag IDs, catalog keys.
LowerToken = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$")]

#: A lowercase kebab-or-snake token: secret-scan rule IDs, enumerator IDs.
LowerSlug = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*$")]

#: A dotted predicate name such as `technology.used` or `application.authorized_regions`.
PredicateId = Annotated[
    str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
]

#: A skill-category or relation-type identifier defined by revision-owned catalog data.
CatalogTokenId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")]


def _require_utc(value: datetime) -> datetime:
    """Normalise an aware timestamp to UTC; refuse a naive one.

    A naive timestamp has no single ISO 8601 rendering, so two bundles with identical logical
    content could hash differently depending on the writer's locale.

    This is an *After* validator on purpose. As a `BeforeValidator` it received the authored string
    rather than a `datetime`, so `2026-08-10T12:00:00` fell through untouched and Pydantic then
    produced a naive datetime — the exact input it exists to refuse.
    """
    if value.tzinfo is None:
        raise ValueError("timestamp must carry an explicit UTC offset")
    return value.astimezone(UTC)


UtcTimestamp = Annotated[datetime, AfterValidator(_require_utc)]


# --------------------------------------------------------------------------------------
# Stable IDs (design §8)
# --------------------------------------------------------------------------------------

#: The tail shared by every record-kind ID.
ID_TAIL: Final = r"[a-z0-9]+(?:[._-][a-z0-9]+)*"

#: The closed record-kind prefix catalog, in the design's declared order.
RECORD_KIND_PREFIXES: Final[tuple[str, ...]] = (
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

#: The eleven entity prefixes, which are the only ones a `subject_id` may name.
ENTITY_PREFIXES: Final[tuple[str, ...]] = (
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
)


def id_pattern(*prefixes: str) -> str:
    """An anchored pattern accepting exactly `prefixes` followed by the shared ID tail.

    Longest-first alternation matters: `source` would otherwise shadow `source-record`, and
    `approval` would shadow `approval-stamp`, so a stamp ID would satisfy a sub-approval
    reference.
    """
    ordered = sorted(prefixes, key=len, reverse=True)
    alternation = "|".join(re.escape(prefix) for prefix in ordered)
    return rf"^(?:{alternation})\.{ID_TAIL}$"


ProfileId = Annotated[str, StringConstraints(pattern=id_pattern("profile"))]
SourceId = Annotated[str, StringConstraints(pattern=id_pattern("source"))]
SourceRecordId = Annotated[str, StringConstraints(pattern=id_pattern("source-record"))]
CandidateId = Annotated[str, StringConstraints(pattern=id_pattern("candidate"))]
PersonId = Annotated[str, StringConstraints(pattern=id_pattern("person"))]
EducationId = Annotated[str, StringConstraints(pattern=id_pattern("education"))]
EmploymentId = Annotated[str, StringConstraints(pattern=id_pattern("employment"))]
ProjectId = Annotated[str, StringConstraints(pattern=id_pattern("project"))]
PublicationId = Annotated[str, StringConstraints(pattern=id_pattern("publication"))]
AwardId = Annotated[str, StringConstraints(pattern=id_pattern("award"))]
CertificationId = Annotated[str, StringConstraints(pattern=id_pattern("certification"))]
AffiliationId = Annotated[str, StringConstraints(pattern=id_pattern("affiliation"))]
CourseId = Annotated[str, StringConstraints(pattern=id_pattern("course"))]
PresentationId = Annotated[str, StringConstraints(pattern=id_pattern("presentation"))]
PatentId = Annotated[str, StringConstraints(pattern=id_pattern("patent"))]
ContactId = Annotated[str, StringConstraints(pattern=id_pattern("contact"))]
RelationId = Annotated[str, StringConstraints(pattern=id_pattern("relation"))]
FactId = Annotated[str, StringConstraints(pattern=id_pattern("fact"))]
MetricId = Annotated[str, StringConstraints(pattern=id_pattern("metric"))]
EvidenceId = Annotated[str, StringConstraints(pattern=id_pattern("evidence"))]
ConflictId = Annotated[str, StringConstraints(pattern=id_pattern("conflict"))]
RulingId = Annotated[str, StringConstraints(pattern=id_pattern("ruling"))]
SkillId = Annotated[str, StringConstraints(pattern=id_pattern("skill"))]
ClaimId = Annotated[str, StringConstraints(pattern=id_pattern("claim"))]
ApprovalId = Annotated[str, StringConstraints(pattern=id_pattern("approval"))]
ApprovalStampId = Annotated[str, StringConstraints(pattern=id_pattern("approval-stamp"))]
ChangeId = Annotated[str, StringConstraints(pattern=id_pattern("change"))]

#: Any of the eleven entity kinds. This is what a fact, metric, relation, or claim subject names.
EntityId = Annotated[str, StringConstraints(pattern=id_pattern(*ENTITY_PREFIXES))]

#: Any record kind at all. Used only where the target kind is genuinely open, such as an approval
#: sub-entry's target, whose legal kind is decided by its `action`.
RecordId = Annotated[str, StringConstraints(pattern=id_pattern(*RECORD_KIND_PREFIXES))]

_PREFIX_ALTERNATION: Final = "|".join(
    re.escape(prefix) for prefix in sorted(RECORD_KIND_PREFIXES, key=len, reverse=True)
)
_PREFIX_RE: Final = re.compile(rf"^({_PREFIX_ALTERNATION})\.")


def prefix_of(record_id: str) -> str:
    """The record-kind prefix of `record_id`, or `''` if it names no known kind."""
    match = _PREFIX_RE.match(record_id)
    return match.group(1) if match else ""


# --------------------------------------------------------------------------------------
# Shared closed catalogs (code-defined: a change here bumps `schema_version`)
# --------------------------------------------------------------------------------------


class EntityKind(StrEnum):
    """The closed initial entity catalog (design §9)."""

    PERSON = "person"
    EDUCATION = "education"
    EMPLOYMENT = "employment"
    PROJECT = "project"
    PUBLICATION = "publication"
    AWARD = "award"
    CERTIFICATION = "certification"
    AFFILIATION = "affiliation"
    COURSE = "course"
    PRESENTATION = "presentation"
    PATENT = "patent"


class Surface(StrEnum):
    """Where a record may be projected. Internal storage is implicit and is not a surface."""

    RESUME = "resume"
    PUBLIC = "public"
    APPLICATION = "application"


class VerificationState(StrEnum):
    """The closed fact-state catalog (§10.2).

    `owner_confirmed` is not a weaker synonym for `verified`: predicate contracts say when owner
    attestation is the appropriate authority, and it can never prove a repository implementation,
    a publication, or a measured result.
    """

    VERIFIED = "verified"
    OWNER_CONFIRMED = "owner_confirmed"
    UNRESOLVED = "unresolved"
    STALE = "stale"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class VerificationBasis(StrEnum):
    """How the assertion was established (§10.2)."""

    PUBLIC_RECORD_VERIFIED = "public_record_verified"
    PRIVATE_DOCUMENT_VERIFIED = "private_document_verified"
    REPOSITORY_VERIFIED = "repository_verified"
    MEASURED = "measured"
    OWNER_ATTESTED = "owner_attested"
    SECONDARY_ONLY = "secondary_only"
    MULTIPLE_SOURCES = "multiple_sources"


class UsageContext(StrEnum):
    """How the subject used or encountered the material (§10.1).

    Context does not change evidence strength. `incidental` can never ground a verified skill.
    """

    PROFESSIONAL = "professional"
    ACADEMIC = "academic"
    PERSONAL_PROJECT = "personal_project"
    CONTRIBUTION = "contribution"
    PUBLICATION = "publication"
    VOLUNTEER = "volunteer"
    INCIDENTAL = "incidental"


#: The two effective states. Everything else is retained and locally blocked, which is why a
#: correction by supersession cannot push a predicate over its cardinality.
EFFECTIVE_STATES: Final[frozenset[VerificationState]] = frozenset(
    {VerificationState.VERIFIED, VerificationState.OWNER_CONFIRMED}
)

#: States that make a fact unavailable downstream regardless of surfaces or evidence (§10.3).
UNAVAILABLE_STATES: Final[frozenset[VerificationState]] = frozenset(
    {
        VerificationState.UNRESOLVED,
        VerificationState.STALE,
        VerificationState.REJECTED,
        VerificationState.SUPERSEDED,
    }
)


def entity_kind_of(entity_id: str) -> EntityKind:
    """The entity kind an entity ID names.

    Raises `ValueError` for a non-entity ID: reaching here with one means a typed reference field
    was bypassed, and guessing a kind would let a fact hang off an evidence record.
    """
    prefix = prefix_of(entity_id)
    try:
        return EntityKind(prefix)
    except ValueError as exc:
        raise ValueError(f"{entity_id!r} does not name an entity kind") from exc
