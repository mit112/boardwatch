"""Typed professional entities and contact channels (design §9).

The schema uses entities, not résumé sections: a `project` is a project whether or not it ever
reaches a résumé, and a `course` is not a demoted `education`. Status catalogs are per entity kind
and closed, so `prototype`, `shipped_open_source`, and `live_public` cannot be conflated — which is
what design §24 requires and what the assertion-tag authorizations in §15 depend on.

`person` deliberately has no status field: design §9's status table declares one for every entity
kind except `person`, and inventing a catalog for it would be a code-defined enum the design never
approved.

Status does not itself prove an accomplishment. An `active` volunteer affiliation with no
contribution facts is a legitimate record; §15's tag authorizations, not the status alone, decide
what may be claimed about it.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field

from boardwatch.profile_bundle.models.base import (
    AffiliationId,
    AwardId,
    CertificationId,
    ContactId,
    CourseId,
    EducationId,
    EmploymentId,
    NonBlankStr,
    PatentId,
    PersonId,
    PresentationId,
    ProjectId,
    PublicationId,
    StrictModel,
    Surface,
    UniqueSorted,
    VerificationState,
)

# --------------------------------------------------------------------------------------
# Status catalogs (§9). A change to any of these bumps `schema_version`.
# --------------------------------------------------------------------------------------


class EducationStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    WITHDRAWN = "withdrawn"


class EmploymentStatus(StrEnum):
    PLANNED = "planned"
    OFFER_ONLY = "offer_only"
    ACTIVE = "active"
    COMPLETED = "completed"


class ProjectStatus(StrEnum):
    CONCEPT = "concept"
    PROTOTYPE = "prototype"
    ACTIVE_DEVELOPMENT = "active_development"
    COMPLETED = "completed"
    SHIPPED_PRIVATE = "shipped_private"
    SHIPPED_OPEN_SOURCE = "shipped_open_source"
    LIVE_PUBLIC = "live_public"
    SUNSET = "sunset"


class PublicationStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    PUBLISHED = "published"


class AwardStatus(StrEnum):
    NOMINATED = "nominated"
    AWARDED = "awarded"


class CertificationStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class AffiliationStatus(StrEnum):
    PLANNED = "planned"
    ACTIVE = "active"
    PAST = "past"


class CourseStatus(StrEnum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    WITHDRAWN = "withdrawn"


class PresentationStatus(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class PatentStatus(StrEnum):
    DRAFT = "draft"
    FILED = "filed"
    PUBLISHED = "published"
    GRANTED = "granted"
    ABANDONED = "abandoned"


class ContactChannelType(StrEnum):
    """The closed initial channel types (§9)."""

    EMAIL = "email"
    PHONE = "phone"
    PROFILE_URL = "profile_url"
    LOCATION = "location"


# --------------------------------------------------------------------------------------
# Entity records
# --------------------------------------------------------------------------------------


class _EntityBase(StrictModel):
    """Fields every entity carries. `entity_type` is the union discriminant."""

    display_name: NonBlankStr
    aliases: Annotated[tuple[NonBlankStr, ...], UniqueSorted] = ()
    created_at: date
    reviewed_at: date


class PersonEntity(_EntityBase):
    entity_id: PersonId
    entity_type: Literal["person"]


class EducationEntity(_EntityBase):
    entity_id: EducationId
    entity_type: Literal["education"]
    status: EducationStatus


class EmploymentEntity(_EntityBase):
    entity_id: EmploymentId
    entity_type: Literal["employment"]
    status: EmploymentStatus


class ProjectEntity(_EntityBase):
    entity_id: ProjectId
    entity_type: Literal["project"]
    status: ProjectStatus


class PublicationEntity(_EntityBase):
    entity_id: PublicationId
    entity_type: Literal["publication"]
    status: PublicationStatus


class AwardEntity(_EntityBase):
    entity_id: AwardId
    entity_type: Literal["award"]
    status: AwardStatus


class CertificationEntity(_EntityBase):
    entity_id: CertificationId
    entity_type: Literal["certification"]
    status: CertificationStatus


class AffiliationEntity(_EntityBase):
    entity_id: AffiliationId
    entity_type: Literal["affiliation"]
    status: AffiliationStatus


class CourseEntity(_EntityBase):
    entity_id: CourseId
    entity_type: Literal["course"]
    status: CourseStatus


class PresentationEntity(_EntityBase):
    entity_id: PresentationId
    entity_type: Literal["presentation"]
    status: PresentationStatus


class PatentEntity(_EntityBase):
    entity_id: PatentId
    entity_type: Literal["patent"]
    status: PatentStatus


#: Discriminated on `entity_type`, so a project status can never validate against an award.
EntityRecord = Annotated[
    PersonEntity
    | EducationEntity
    | EmploymentEntity
    | ProjectEntity
    | PublicationEntity
    | AwardEntity
    | CertificationEntity
    | AffiliationEntity
    | CourseEntity
    | PresentationEntity
    | PatentEntity,
    Field(discriminator="entity_type"),
]

#: entity kind -> its status enum. `person` is absent because §9 declares no catalog for it.
STATUS_CATALOGS: dict[str, type[StrEnum]] = {
    "education": EducationStatus,
    "employment": EmploymentStatus,
    "project": ProjectStatus,
    "publication": PublicationStatus,
    "award": AwardStatus,
    "certification": CertificationStatus,
    "affiliation": AffiliationStatus,
    "course": CourseStatus,
    "presentation": PresentationStatus,
    "patent": PatentStatus,
}

#: Project statuses that mean the work reached users. §15's `shipped` tag authorizes on this set.
SHIPPED_PROJECT_STATUSES: frozenset[ProjectStatus] = frozenset(
    {
        ProjectStatus.SHIPPED_PRIVATE,
        ProjectStatus.SHIPPED_OPEN_SOURCE,
        ProjectStatus.LIVE_PUBLIC,
        ProjectStatus.SUNSET,
    }
)


class ContactRecord(StrictModel):
    """One typed contact channel on the single `person` entity (§9).

    Contact values and their surfaces require a `confirm_contact` sub-approval in the revision's
    approval stamp; a `verification_state` of `owner_confirmed` in the YAML alone establishes
    nothing.
    """

    contact_id: ContactId
    person_id: PersonId
    channel_type: ContactChannelType
    value: NonBlankStr
    allowed_surfaces: Annotated[tuple[Surface, ...], UniqueSorted]
    verification_state: VerificationState
