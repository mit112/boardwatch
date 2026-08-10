"""One typed wrapper per declared file, and the assembled `BundleDocuments` (design §6).

Design §6 assigns *ownership*: `facts/identity.yaml` owns the one person entity and its contacts,
`facts/education.yaml` owns education entities, each file under `facts/experience/` owns one
employment entity, and "entity-owned files also own their subjects' atomic facts except that
application-only facts live in `application/gated-facts.yaml`".

Ownership is enforced by the wrapper's TYPE, not by a later check. `AwardsDocument.entities` is a
tuple of `AwardEntity`, so a project cloned into `facts/awards.yaml` fails to parse. The same
discipline splits the two claim files: a `professional_summary` in `bullet-candidates.yaml` is a
parse error rather than something the semantic layer has to remember to look for.

The one wrapper-level *value* rule is the application-only one. §16 requires that a record in
`application/gated-facts.yaml` declare `[application]` or no surfaces at all; that is intrinsic to
the file, so it belongs here rather than in the surface graph.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Annotated, ClassVar

from pydantic import model_validator

from boardwatch.profile_bundle.models.base import (
    StrictModel,
    Surface,
    UniqueOrdered,
)
from boardwatch.profile_bundle.models.claims import (
    BULLET_CLAIM_TYPES,
    SUMMARY_CLAIM_TYPES,
    ClaimRecord,
    ClaimType,
)
from boardwatch.profile_bundle.models.entities import (
    AffiliationEntity,
    AwardEntity,
    CertificationEntity,
    ContactRecord,
    CourseEntity,
    EducationEntity,
    EmploymentEntity,
    PatentEntity,
    PersonEntity,
    PresentationEntity,
    ProjectEntity,
    PublicationEntity,
)
from boardwatch.profile_bundle.models.evidence import EvidenceRecord
from boardwatch.profile_bundle.models.facts import FactRecord
from boardwatch.profile_bundle.models.history import (
    ApprovalLedger,
    ChangeLedger,
    ConflictGroups,
    ConflictRulings,
)
from boardwatch.profile_bundle.models.imports import (
    CandidatePackage,
    ExclusionLedger,
    SourceLedger,
)
from boardwatch.profile_bundle.models.manifests import (
    BundleManifest,
    DraftManifest,
    RevisionManifest,
)
from boardwatch.profile_bundle.models.metrics import MetricRecord
from boardwatch.profile_bundle.models.policy import (
    AssertionTagCatalog,
    PredicateCatalog,
    RelationCatalog,
    SecretRuleset,
    SkillCategoryCatalog,
    SourceCatalog,
    UnitCatalog,
)
from boardwatch.profile_bundle.models.relations import RelationRecord
from boardwatch.profile_bundle.models.skills import SkillRecord

# --------------------------------------------------------------------------------------
# Fact-bearing documents
# --------------------------------------------------------------------------------------


class _FactBearing(StrictModel):
    """Any document that owns atomic facts. Order is preserved; duplicates are refused."""

    facts: Annotated[tuple[FactRecord, ...], UniqueOrdered]


class IdentityDocument(_FactBearing):
    """`facts/identity.yaml`: the one person entity, its contact channels, and its facts."""

    person: PersonEntity
    contacts: Annotated[tuple[ContactRecord, ...], UniqueOrdered]

    @model_validator(mode="after")
    def _contacts_belong_to_this_person(self) -> IdentityDocument:
        for contact in self.contacts:
            if contact.person_id != self.person.entity_id:
                raise ValueError(
                    f"{contact.contact_id}: person_id {contact.person_id!r} is not this document's "
                    f"person {self.person.entity_id!r}; there is exactly one person entity"
                )
        return self


class EducationDocument(_FactBearing):
    entities: Annotated[tuple[EducationEntity, ...], UniqueOrdered]


class PublicationsDocument(_FactBearing):
    entities: Annotated[tuple[PublicationEntity, ...], UniqueOrdered]


class AwardsDocument(_FactBearing):
    entities: Annotated[tuple[AwardEntity, ...], UniqueOrdered]


class CertificationsDocument(_FactBearing):
    entities: Annotated[tuple[CertificationEntity, ...], UniqueOrdered]


class AffiliationsDocument(_FactBearing):
    entities: Annotated[tuple[AffiliationEntity, ...], UniqueOrdered]


class CoursesDocument(_FactBearing):
    entities: Annotated[tuple[CourseEntity, ...], UniqueOrdered]


class PresentationsDocument(_FactBearing):
    entities: Annotated[tuple[PresentationEntity, ...], UniqueOrdered]


class PatentsDocument(_FactBearing):
    entities: Annotated[tuple[PatentEntity, ...], UniqueOrdered]


class EmploymentFactsDocument(_FactBearing):
    """`facts/experience/<employment-id>.yaml`: exactly one employment entity and its facts."""

    entity: EmploymentEntity


class ProjectFactsDocument(_FactBearing):
    """`facts/projects/<project-id>.yaml`: exactly one project entity and its facts."""

    entity: ProjectEntity


class GatedFactsDocument(_FactBearing):
    """`application/gated-facts.yaml` (§16).

    Professional facts that may be needed for an application but must never reach a résumé or a
    public artefact. The surface restriction is intrinsic to the file: a record here declaring
    `resume` would be an application-only fact widening itself — the exact leak §10.3's graph
    invariants exist to prevent — and the file-level check catches it before any graph is built.
    """

    @model_validator(mode="after")
    def _application_only_surfaces(self) -> GatedFactsDocument:
        for fact in self.facts:
            leaked = set(fact.allowed_surfaces) - {Surface.APPLICATION}
            if leaked:
                raise ValueError(
                    f"{fact.fact_id}: an application-only fact declares "
                    f"{sorted(surface.value for surface in leaked)}; only [application] or no "
                    "surfaces are legal here"
                )
        return self


# --------------------------------------------------------------------------------------
# Claim documents
# --------------------------------------------------------------------------------------


class _ClaimDocument(StrictModel):
    claims: Annotated[tuple[ClaimRecord, ...], UniqueOrdered]

    # ClassVar, not a field: an annotated non-ClassVar attribute would become a Pydantic
    # private attribute and `type(self)._owned_types` would hand back a descriptor, so the
    # ownership check would compare claim types against an object and never fire.
    _owned_types: ClassVar[frozenset[ClaimType]] = frozenset()

    @model_validator(mode="after")
    def _claim_types_match_the_owning_file(self) -> _ClaimDocument:
        owned = type(self)._owned_types
        for claim in self.claims:
            if claim.claim_type not in owned:
                raise ValueError(
                    f"{claim.claim_id}: claim_type {claim.claim_type.value!r} does not belong in "
                    f"this file, which owns {sorted(kind.value for kind in owned)}"
                )
        return self


class BulletCandidatesDocument(_ClaimDocument):
    """`claims/bullet-candidates.yaml`: responsibility, accomplishment, project_summary."""

    _owned_types = BULLET_CLAIM_TYPES


class SummaryCandidatesDocument(_ClaimDocument):
    """`claims/summary-candidates.yaml`: professional_summary only."""

    _owned_types = SUMMARY_CLAIM_TYPES


# --------------------------------------------------------------------------------------
# Remaining aggregate documents
# --------------------------------------------------------------------------------------


class SkillInventoryDocument(StrictModel):
    skills: Annotated[tuple[SkillRecord, ...], UniqueOrdered]


class MetricRecordsDocument(StrictModel):
    metrics: Annotated[tuple[MetricRecord, ...], UniqueOrdered]


class EvidenceRecordsDocument(StrictModel):
    """`evidence/records.yaml`. §7 step 2 reads evidence records ONLY from here, which is what makes
    the evidence-set digest a function of one document plus the blob bytes it names."""

    evidence: Annotated[tuple[EvidenceRecord, ...], UniqueOrdered]


class RelationRecordsDocument(StrictModel):
    relations: Annotated[tuple[RelationRecord, ...], UniqueOrdered]


# --------------------------------------------------------------------------------------
# The assembled tree
# --------------------------------------------------------------------------------------

#: Every wrapper a declared file may parse into.
DocumentModel = (
    DraftManifest
    | RevisionManifest
    | IdentityDocument
    | EducationDocument
    | EmploymentFactsDocument
    | ProjectFactsDocument
    | PublicationsDocument
    | AwardsDocument
    | CertificationsDocument
    | AffiliationsDocument
    | CoursesDocument
    | PresentationsDocument
    | PatentsDocument
    | BulletCandidatesDocument
    | SummaryCandidatesDocument
    | SkillInventoryDocument
    | MetricRecordsDocument
    | EvidenceRecordsDocument
    | ConflictGroups
    | ConflictRulings
    | PredicateCatalog
    | UnitCatalog
    | RelationCatalog
    | SourceCatalog
    | SkillCategoryCatalog
    | AssertionTagCatalog
    | SecretRuleset
    | RelationRecordsDocument
    | SourceLedger
    | CandidatePackage
    | ExclusionLedger
    | GatedFactsDocument
    | ChangeLedger
    | ApprovalLedger
)


@dataclass(frozen=True)
class BundleDocuments:
    """One parsed logical tree.

    A frozen dataclass rather than a Pydantic model on purpose: this is *assembled* from documents
    that have each already been validated, never parsed from YAML itself. Giving it a parser would
    invite a caller to build one from raw input and skip every wrapper's own checks, and Pydantic
    would additionally want to re-validate and re-serialise the mapping on every access — in a type
    whose whole job is to be hashed byte-for-byte.
    """

    manifest: BundleManifest
    by_path: Mapping[PurePosixPath, DocumentModel]

    def paths(self) -> tuple[PurePosixPath, ...]:
        """Sorted so every derived digest and diagnostic order is independent of discovery order."""
        return tuple(sorted(self.by_path, key=str))

    def items(self) -> Iterator[tuple[PurePosixPath, DocumentModel]]:
        for path in self.paths():
            yield path, self.by_path[path]

    def get(self, path: str) -> DocumentModel | None:
        return self.by_path.get(PurePosixPath(path))

    @property
    def is_draft(self) -> bool:
        return isinstance(self.manifest, DraftManifest)
