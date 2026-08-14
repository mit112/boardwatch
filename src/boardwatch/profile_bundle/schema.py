"""Bundle schema head, supported set, the document-kind registry, and JSON Schema export.

## The bootstrap rule

Schema v1 is the bootstrap release and supports exactly `{1}` (design §7). There is deliberately
no invented v0 document shape and no `0 -> 1` migration: fabricating a previous version would mean
shipping a fixture nothing ever wrote and a migration nothing ever needs, and the first real bump
would then have two "previous" schemas to reason about.

From v2 onward, readers support the current version and the immediately preceding one, and the
design for every bump must include the exact previous-version fixture and the forward migration.

## What bumps the version

A record-shape change, or an addition to a **code-defined** closed enum — entity kinds,
verification states, evidence classes, claim states, ruling decisions — bumps `schema_version`.
Adding a row to a revision-owned catalog (a predicate, unit, relation, source, skill category,
assertion tag) changes that catalog's version and the bundle digest, and bumps nothing here.

## Why the JSON Schema is committed rather than generated on demand

An LLM authoring a bundle needs the schema without running the code, so it ships as package data.
A parity test asserts the committed bytes equal `schema_json()` exactly, which is what stops the
shipped contract from drifting away from the models it claims to describe.
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Final

from pydantic import BaseModel, ConfigDict

from boardwatch.profile_bundle.errors import UnsupportedSchemaVersionError
from boardwatch.profile_bundle.layout import DocumentKind
from boardwatch.profile_bundle.models.documents import (
    AffiliationsDocument,
    AwardsDocument,
    BulletCandidatesDocument,
    CertificationsDocument,
    CoursesDocument,
    EducationDocument,
    EmploymentFactsDocument,
    EvidenceRecordsDocument,
    GatedFactsDocument,
    IdentityDocument,
    MetricRecordsDocument,
    PatentsDocument,
    PresentationsDocument,
    ProjectFactsDocument,
    PublicationsDocument,
    RelationRecordsDocument,
    SkillInventoryDocument,
    SummaryCandidatesDocument,
)
from boardwatch.profile_bundle.models.history import (
    ApprovalLedger,
    ChangeLedger,
    ConflictGroups,
    ConflictRulings,
)
from boardwatch.profile_bundle.models.imports import (
    CandidatePackage,
    ExclusionLedger,
    ExtractionReport,
    SourceLedger,
)
from boardwatch.profile_bundle.models.manifests import DraftManifest, RevisionManifest
from boardwatch.profile_bundle.models.policy import (
    AssertionTagCatalog,
    ExtractionMappingsDocument,
    PredicateCatalog,
    RelationCatalog,
    SecretRuleset,
    SkillCategoryCatalog,
    SourceCatalog,
    UnitCatalog,
)
from boardwatch.profile_bundle.models.sidecars import LocalSourcesSidecar

CURRENT_SCHEMA_VERSION: Final = 2

#: Exactly `{CURRENT_SCHEMA_VERSION}`. Not a range, not "anything at or below the head": a bundle
#: written by a newer build must be refused with a typed outcome, not misread as an unknown enum
#: value. v2 adds two documents (`policy/extraction-mappings.yaml`, `imports/extraction-report.yaml`)
#: and changes no v1 model. A `1 -> 2` forward migration is deliberately NOT shipped yet: no v1
#: bundle exists, so a v1 tree is refused fail-safe (`unsupported_schema_version`, exit 3) rather
#: than migrated by a transform whose only exerciser would be a fabricated previous-version fixture
#: (schema.py's own bootstrap argument). Widening this set to `{1, 2}` is the change that then owes
#: the fixture and the transform — the tripwire pins that (`test_..._owed_at_v2`).
SUPPORTED_SCHEMA_VERSIONS: Final[frozenset[int]] = frozenset({CURRENT_SCHEMA_VERSION})

SCHEMA_RESOURCE_PACKAGE: Final = "boardwatch.profile_bundle.resources"
SCHEMA_RESOURCE_NAME: Final = "career-profile.schema.json"

#: The one place a declared file's kind becomes a parser. Every `DocumentKind` must appear; a
#: missing entry would make its file unparseable while the layout grammar still claimed the file
#: was declared, so a test asserts totality.
DOCUMENT_MODELS: Final[dict[DocumentKind, type[BaseModel]]] = {
    DocumentKind.IDENTITY: IdentityDocument,
    DocumentKind.EDUCATION: EducationDocument,
    DocumentKind.EMPLOYMENT_FACTS: EmploymentFactsDocument,
    DocumentKind.PROJECT_FACTS: ProjectFactsDocument,
    DocumentKind.PUBLICATIONS: PublicationsDocument,
    DocumentKind.AWARDS: AwardsDocument,
    DocumentKind.CERTIFICATIONS: CertificationsDocument,
    DocumentKind.AFFILIATIONS: AffiliationsDocument,
    DocumentKind.COURSES: CoursesDocument,
    DocumentKind.PRESENTATIONS: PresentationsDocument,
    DocumentKind.PATENTS: PatentsDocument,
    DocumentKind.BULLET_CANDIDATES: BulletCandidatesDocument,
    DocumentKind.SUMMARY_CANDIDATES: SummaryCandidatesDocument,
    DocumentKind.SKILL_INVENTORY: SkillInventoryDocument,
    DocumentKind.METRIC_RECORDS: MetricRecordsDocument,
    DocumentKind.EVIDENCE_RECORDS: EvidenceRecordsDocument,
    DocumentKind.CONFLICT_GROUPS: ConflictGroups,
    DocumentKind.CONFLICT_RULINGS: ConflictRulings,
    DocumentKind.PREDICATE_CATALOG: PredicateCatalog,
    DocumentKind.UNIT_CATALOG: UnitCatalog,
    DocumentKind.RELATION_CATALOG: RelationCatalog,
    DocumentKind.SOURCE_CATALOG: SourceCatalog,
    DocumentKind.SKILL_CATEGORY_CATALOG: SkillCategoryCatalog,
    DocumentKind.ASSERTION_TAG_CATALOG: AssertionTagCatalog,
    DocumentKind.SECRET_SCAN_RULESET: SecretRuleset,
    DocumentKind.EXTRACTION_MAPPINGS: ExtractionMappingsDocument,
    DocumentKind.RELATION_RECORDS: RelationRecordsDocument,
    DocumentKind.SOURCE_LEDGER: SourceLedger,
    DocumentKind.IMPORT_CANDIDATES: CandidatePackage,
    DocumentKind.IMPORT_EXCLUSIONS: ExclusionLedger,
    DocumentKind.EXTRACTION_REPORT: ExtractionReport,
    DocumentKind.GATED_FACTS: GatedFactsDocument,
    DocumentKind.CHANGE_LEDGER: ChangeLedger,
    DocumentKind.APPROVAL_LEDGER: ApprovalLedger,
}


def model_for_kind(kind: DocumentKind) -> type[BaseModel]:
    """The wrapper that parses `kind`.

    `MANIFEST` is absent from `DOCUMENT_MODELS` because it is a discriminated union of two states
    rather than one model, and the loader dispatches it explicitly.
    """
    if kind is DocumentKind.MANIFEST:
        raise KeyError(
            "the manifest is a draft/revision union, not a single document model; parse it with "
            "`BundleManifest`"
        )
    return DOCUMENT_MODELS[kind]


def require_supported_schema(found: int) -> int:
    """Return `found` if this build supports it, else raise the typed refusal (exit 3)."""
    if found not in SUPPORTED_SCHEMA_VERSIONS:
        raise UnsupportedSchemaVersionError(found, sorted(SUPPORTED_SCHEMA_VERSIONS))
    return found


class _BundleSchemaRoot(BaseModel):
    """A synthetic root whose only purpose is to pull every document model into one `$defs` block.

    Nothing constructs it. The alternative — one schema file per document — would give an authoring
    agent thirty-three files to fetch and no single place to see the whole contract.
    """

    model_config = ConfigDict(extra="forbid")

    draft_manifest: DraftManifest
    revision_manifest: RevisionManifest
    identity: IdentityDocument
    education: EducationDocument
    employment_facts: EmploymentFactsDocument
    project_facts: ProjectFactsDocument
    publications: PublicationsDocument
    awards: AwardsDocument
    certifications: CertificationsDocument
    affiliations: AffiliationsDocument
    courses: CoursesDocument
    presentations: PresentationsDocument
    patents: PatentsDocument
    bullet_candidates: BulletCandidatesDocument
    summary_candidates: SummaryCandidatesDocument
    skill_inventory: SkillInventoryDocument
    metric_records: MetricRecordsDocument
    evidence_records: EvidenceRecordsDocument
    conflict_groups: ConflictGroups
    conflict_rulings: ConflictRulings
    predicate_catalog: PredicateCatalog
    unit_catalog: UnitCatalog
    relation_catalog: RelationCatalog
    source_catalog: SourceCatalog
    skill_category_catalog: SkillCategoryCatalog
    assertion_tag_catalog: AssertionTagCatalog
    secret_scan_ruleset: SecretRuleset
    extraction_mappings: ExtractionMappingsDocument
    relation_records: RelationRecordsDocument
    source_ledger: SourceLedger
    import_candidates: CandidatePackage
    import_exclusions: ExclusionLedger
    extraction_report: ExtractionReport
    gated_facts: GatedFactsDocument
    change_ledger: ChangeLedger
    approval_ledger: ApprovalLedger
    local_sources_sidecar: LocalSourcesSidecar


def bundle_json_schema() -> dict[str, object]:
    """The generated JSON Schema for every bundle document, as a plain dict."""
    schema = _BundleSchemaRoot.model_json_schema(mode="validation")
    schema["title"] = "boardwatch career-profile bundle"
    schema["x-bundle-schema-version"] = CURRENT_SCHEMA_VERSION
    return schema


def schema_json() -> str:
    """The exact committed rendering: sorted keys, two-space indent, no trailing newline.

    Sorted keys make the file's diff meaningful — Pydantic's `$defs` order tracks declaration order,
    so an unrelated import reshuffle would otherwise rewrite the whole schema.
    """
    return json.dumps(bundle_json_schema(), indent=2, sort_keys=True, ensure_ascii=False)


def committed_schema_json() -> str:
    """The schema as shipped in the wheel, without its trailing newline."""
    text = (
        resources.files(SCHEMA_RESOURCE_PACKAGE).joinpath(SCHEMA_RESOURCE_NAME).read_text("utf-8")
    )
    return text.rstrip("\n")
