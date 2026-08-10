"""The global record index: every record by ID, by kind, and the graph lookups built on top.

Two decisions here carry weight.

**Indexing is keyed by the ID STRING, not by a typed wrapper.** Design §8 requires IDs to be
globally unique across record kinds, and that is exactly the check a per-kind index cannot make:
partitioning by wrapper class would let `fact.x` and a hypothetical `metric.x` coexist and report
clean.

**Dispatch is by record TYPE, not by field name.** `policy/relations.yaml` has a `relations` field
too, holding catalog rows; `policy/sources.yaml` and `imports/source-ledger.yaml` both have
`sources`. Name-based dispatch indexed catalog rows as records and reported a correct bundle as
having duplicate IDs.

**Duplicates are collected, not raised.** The index is built before validation runs, so it records
every collision with both owning paths and lets the structural layer report them all at once. A
first duplicate that aborted indexing would hide the second.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Final, TypeVar

from pydantic import BaseModel

from boardwatch.profile_bundle.models.base import ENTITY_PREFIXES, prefix_of
from boardwatch.profile_bundle.models.claims import ClaimRecord
from boardwatch.profile_bundle.models.documents import (
    BundleDocuments,
    DocumentModel,
    GatedFactsDocument,
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
from boardwatch.profile_bundle.models.evidence import (
    AnyEvidence,
    MeasuredResultEvidence,
    OwnerAttestationEvidence,
    PrivateDocumentEvidence,
    PublicRecordEvidence,
    RepositoryArtifactEvidence,
    SecondarySummaryEvidence,
)
from boardwatch.profile_bundle.models.facts import FactRecord
from boardwatch.profile_bundle.models.history import (
    ApprovalEntry,
    ApprovalStamp,
    ChangeRecord,
    ConflictRecord,
    ConflictState,
    RulingRecord,
)
from boardwatch.profile_bundle.models.imports import (
    CandidateRecord,
    ExclusionLedger,
    ExclusionRecord,
    SourceLedger,
    SourceLedgerRecord,
)
from boardwatch.profile_bundle.models.metrics import MetricRecord
from boardwatch.profile_bundle.models.policy import (
    AssertionTagCatalog,
    PredicateCatalog,
    RelationCatalog,
    SecretRuleset,
    SkillCategoryCatalog,
    SourceCatalog,
    SourceSpec,
    UnitCatalog,
)
from boardwatch.profile_bundle.models.relations import RelationRecord
from boardwatch.profile_bundle.models.skills import SkillRecord

#: Candidate ID field names, most specific first. `ruling_id` precedes `conflict_id` because a
#: ruling carries both, and `source_record_id` precedes `source_id` for the same reason. Getting
#: this order wrong would index a ruling under its conflict's ID and make the conflict look
#: duplicated.
_ID_FIELDS: Final[tuple[str, ...]] = (
    "approval_id",
    "approval_stamp_id",
    "change_id",
    "claim_id",
    "ruling_id",
    "conflict_id",
    "evidence_id",
    "metric_id",
    "skill_id",
    "relation_id",
    "fact_id",
    "contact_id",
    "entity_id",
    "candidate_id",
    "source_record_id",
    "source_id",
)


def record_id_of(record: BaseModel) -> str:
    """The stable ID a record carries.

    Raises for a model with none: reaching here with a catalog row or a value object means the
    caller is treating something unaddressable as a record, and inventing an ID would make it
    silently unreferenceable rather than obviously wrong.
    """
    for name in _ID_FIELDS:
        value = getattr(record, name, None)
        if isinstance(value, str):
            return value
    raise TypeError(f"{type(record).__name__} carries no stable record ID")


@dataclass(frozen=True)
class Collision:
    """One ID used by two records, with both owning documents so a diagnostic can name them."""

    record_id: str
    first_path: PurePosixPath
    second_path: PurePosixPath


@dataclass(frozen=True)
class BundleIndex:
    """Every addressable record in one revision, plus the graph lookups validation needs."""

    records: Mapping[str, BaseModel]
    paths: Mapping[str, PurePosixPath]
    by_kind: Mapping[str, tuple[BaseModel, ...]]
    collisions: tuple[Collision, ...]

    facts: tuple[FactRecord, ...]
    gated_fact_ids: frozenset[str]
    entities: Mapping[str, BaseModel]
    contacts: tuple[ContactRecord, ...]
    relations: tuple[RelationRecord, ...]
    skills: tuple[SkillRecord, ...]
    metrics: tuple[MetricRecord, ...]
    evidence: tuple[AnyEvidence, ...]
    conflicts: tuple[ConflictRecord, ...]
    rulings: tuple[RulingRecord, ...]
    claims: tuple[ClaimRecord, ...]
    changes: tuple[ChangeRecord, ...]
    stamps: tuple[ApprovalStamp, ...]
    approval_entries: Mapping[str, ApprovalEntry]
    ledger_records: tuple[SourceLedgerRecord, ...]
    candidates: tuple[CandidateRecord, ...]
    exclusions: tuple[ExclusionRecord, ...]

    predicates: PredicateCatalog | None
    units: UnitCatalog | None
    relation_catalog: RelationCatalog | None
    sources: SourceCatalog | None
    skill_categories: SkillCategoryCatalog | None
    assertion_tags: AssertionTagCatalog | None
    secret_ruleset: SecretRuleset | None
    source_ledger: SourceLedger | None

    #: record ID -> the evidence IDs that record cites. Built from the RECORD side, so the
    #: bidirectional check has an independent view of each direction.
    evidence_links: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def get(self, record_id: str) -> BaseModel | None:
        return self.records.get(record_id)

    def path_of(self, record_id: str) -> str | None:
        path = self.paths.get(record_id)
        return path.as_posix() if path is not None else None

    def fact(self, fact_id: str) -> FactRecord | None:
        record = self.records.get(fact_id)
        return record if isinstance(record, FactRecord) else None

    def metric(self, metric_id: str) -> MetricRecord | None:
        record = self.records.get(metric_id)
        return record if isinstance(record, MetricRecord) else None

    def conflict(self, conflict_id: str) -> ConflictRecord | None:
        record = self.records.get(conflict_id)
        return record if isinstance(record, ConflictRecord) else None

    @property
    def unresolved_conflict_ids(self) -> frozenset[str]:
        """Groups that block their candidates. `resolved` does not; `reopened` does.

        A reopened group is one where new evidence unsettled a previous ruling, so its candidates
        are again undecided — treating it as settled would let the superseded answer keep being
        used.
        """
        return frozenset(
            conflict.conflict_id
            for conflict in self.conflicts
            if conflict.state is not ConflictState.RESOLVED
        )


#: record model -> the kind it is indexed under. Dispatch is by TYPE, never by field name, and the
#: distinction is load-bearing: `policy/relations.yaml` holds `relations` too, but those are
#: `RelationSpec` catalog rows, and `policy/sources.yaml` and `imports/source-ledger.yaml` both hold
#: a field called `sources`. Name-based dispatch indexed catalog rows as records and reported the
#: catalog's own contents as duplicate IDs.
_RECORD_KINDS: Final[Mapping[type[BaseModel], str]] = {
    PersonEntity: "entity",
    EducationEntity: "entity",
    EmploymentEntity: "entity",
    ProjectEntity: "entity",
    PublicationEntity: "entity",
    AwardEntity: "entity",
    CertificationEntity: "entity",
    AffiliationEntity: "entity",
    CourseEntity: "entity",
    PresentationEntity: "entity",
    PatentEntity: "entity",
    ContactRecord: "contact",
    FactRecord: "fact",
    RelationRecord: "relation",
    SkillRecord: "skill",
    MetricRecord: "metric",
    PublicRecordEvidence: "evidence",
    PrivateDocumentEvidence: "evidence",
    RepositoryArtifactEvidence: "evidence",
    MeasuredResultEvidence: "evidence",
    OwnerAttestationEvidence: "evidence",
    SecondarySummaryEvidence: "evidence",
    ConflictRecord: "conflict",
    RulingRecord: "ruling",
    ClaimRecord: "claim",
    ChangeRecord: "change",
    ApprovalStamp: "approval-stamp",
    #: The catalog owns the `source.*` namespace. `SourceLedgerSource` is deliberately absent: it is
    #: one import's USE of a catalogued source, keyed by that source's ID, not a second record
    #: claiming it. `ExclusionRecord` is absent for the same reason — it is keyed by the ledger
    #: record it excludes.
    SourceSpec: "source",
    SourceLedgerRecord: "source-record",
    CandidateRecord: "candidate",
}


def _document_records(document: DocumentModel) -> Iterator[tuple[str, BaseModel]]:
    """Every addressable record one document owns, tagged with the kind it belongs to.

    Walks the document's declared fields and keeps only values whose model type is in
    `_RECORD_KINDS`; catalog rows and value objects fall through untouched.
    """
    for name in type(document).model_fields:
        value = getattr(document, name, None)
        candidates = value if isinstance(value, tuple) else (value,)
        for item in candidates:
            if not isinstance(item, BaseModel):
                continue
            kind = _RECORD_KINDS.get(type(item))
            if kind is not None:
                yield kind, item


def build_index(documents: BundleDocuments) -> BundleIndex:
    """Index one parsed logical tree. Never raises on a duplicate; it collects them."""
    records: dict[str, BaseModel] = {}
    paths: dict[str, PurePosixPath] = {}
    by_kind: dict[str, list[BaseModel]] = {}
    collisions: list[Collision] = []

    for path, document in documents.items():
        for kind, record in _document_records(document):
            by_kind.setdefault(kind, []).append(record)
            identifier = record_id_of(record)
            if identifier in records:
                collisions.append(Collision(identifier, paths[identifier], path))
                continue
            records[identifier] = record
            paths[identifier] = path

    def kind_of(kind: str) -> tuple[BaseModel, ...]:
        return tuple(by_kind.get(kind, ()))

    facts = tuple(record for record in kind_of("fact") if isinstance(record, FactRecord))
    gated = documents.by_path.get(PurePosixPath("application/gated-facts.yaml"))
    gated_ids = (
        frozenset(fact.fact_id for fact in gated.facts)
        if isinstance(gated, GatedFactsDocument)
        else frozenset()
    )

    links: dict[str, tuple[str, ...]] = {}
    for fact in facts:
        links[fact.fact_id] = fact.evidence_ids
    metrics = tuple(record for record in kind_of("metric") if isinstance(record, MetricRecord))
    for metric in metrics:
        links[metric.metric_id] = metric.evidence_ids

    return BundleIndex(
        records=records,
        paths=paths,
        by_kind={kind: tuple(values) for kind, values in by_kind.items()},
        collisions=tuple(collisions),
        facts=facts,
        gated_fact_ids=gated_ids,
        entities={record_id_of(record): record for record in kind_of("entity")},
        contacts=tuple(r for r in kind_of("contact") if isinstance(r, ContactRecord)),
        relations=tuple(r for r in kind_of("relation") if isinstance(r, RelationRecord)),
        skills=tuple(r for r in kind_of("skill") if isinstance(r, SkillRecord)),
        metrics=metrics,
        evidence=tuple(r for r in kind_of("evidence") if isinstance(r, AnyEvidence)),
        conflicts=tuple(r for r in kind_of("conflict") if isinstance(r, ConflictRecord)),
        rulings=tuple(r for r in kind_of("ruling") if isinstance(r, RulingRecord)),
        claims=tuple(r for r in kind_of("claim") if isinstance(r, ClaimRecord)),
        changes=tuple(r for r in kind_of("change") if isinstance(r, ChangeRecord)),
        stamps=tuple(r for r in kind_of("approval-stamp") if isinstance(r, ApprovalStamp)),
        approval_entries=_approval_entries(kind_of("approval-stamp")),
        ledger_records=tuple(
            r for r in kind_of("source-record") if isinstance(r, SourceLedgerRecord)
        ),
        candidates=tuple(r for r in kind_of("candidate") if isinstance(r, CandidateRecord)),
        # Read from its own document rather than the kind scan: exclusions claim no global ID, so
        # they are deliberately not indexed as records.
        exclusions=_exclusions_of(documents),
        predicates=_typed(documents, "policy/predicates.yaml", PredicateCatalog),
        units=_typed(documents, "policy/units.yaml", UnitCatalog),
        relation_catalog=_typed(documents, "policy/relations.yaml", RelationCatalog),
        sources=_typed(documents, "policy/sources.yaml", SourceCatalog),
        skill_categories=_typed(
            documents, "policy/skill-categories.yaml", SkillCategoryCatalog
        ),
        assertion_tags=_typed(documents, "policy/assertion-tags.yaml", AssertionTagCatalog),
        secret_ruleset=_typed(documents, "policy/secret-scan.yaml", SecretRuleset),
        source_ledger=_typed(documents, "imports/source-ledger.yaml", SourceLedger),
        evidence_links=links,
    )


def _exclusions_of(documents: BundleDocuments) -> tuple[ExclusionRecord, ...]:
    ledger = _typed(documents, "imports/exclusions.yaml", ExclusionLedger)
    return ledger.exclusions if ledger is not None else ()


def _approval_entries(stamps: Iterable[BaseModel]) -> dict[str, ApprovalEntry]:
    """Sub-approvals indexed globally. §13 makes their IDs globally unique across stamps, so a
    collision between two stamps must be visible — hence one flat index rather than per-stamp."""
    entries: dict[str, ApprovalEntry] = {}
    for stamp in stamps:
        if not isinstance(stamp, ApprovalStamp):
            continue
        for entry in stamp.entries:
            entries.setdefault(entry.approval_id, entry)
    return entries


def duplicate_approval_ids(stamps: Iterable[ApprovalStamp]) -> tuple[str, ...]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for stamp in stamps:
        for entry in stamp.entries:
            if entry.approval_id in seen and entry.approval_id not in duplicates:
                duplicates.append(entry.approval_id)
            seen.add(entry.approval_id)
    return tuple(duplicates)


_DocumentT = TypeVar("_DocumentT", bound=BaseModel)


def _typed(
    documents: BundleDocuments, path: str, model: type[_DocumentT]
) -> _DocumentT | None:
    document = documents.get(path)
    return document if isinstance(document, model) else None


def prefix_matches_kind(record_id: str, kind: str) -> bool:
    """Whether an ID's prefix agrees with the kind of record holding it.

    Entities are the one many-to-one case: eleven prefixes map to the `entity` kind, so the check is
    "is this prefix an entity prefix?" rather than a string equality.
    """
    prefix = prefix_of(record_id)
    if kind == "entity":
        return prefix in ENTITY_PREFIXES
    return prefix == kind
