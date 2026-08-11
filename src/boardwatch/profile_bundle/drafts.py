"""`init` and `checkout`: the two ways a writable draft comes into existence (design §6, §19).

Both commands end in the same place — a populated `drafts/<name>/` or a refusal that wrote nothing —
and differ in everything before it.

## `init` authors, `checkout` copies

`init` has no parent to copy from, so it *writes* every declared document in its empty form. There
is exactly one it cannot write: `facts/identity.yaml` requires a person, and a person requires a
display name and review dates — content the owner has and this package does not (it reads no clock
and invents no names). So the empty draft is deliberately one file short, and the structural layer
reports that file as the owner's first task. Filling it with a placeholder would be worse: a
placeholder that survives to promotion is a fact nobody authored.

`checkout` copies the selected revision's documents **byte for byte** and rewrites only
`manifest.yaml`. Re-emitting the other documents would rewrite bytes the owner never touched and
make the first diff after a checkout unreadable, which is the diff that matters most.

## The private sidecar is not filtered out, it is unrepresentable

§6 says `checkout` never copies `local-sources.yaml`. There is no filter here for it, because there
is nothing to filter: the sidecar lives at the bundle ROOT and the closed logical grammar refuses
it inside any tree, so it is never among the files a revision contains. A second check would read as
coverage for a case that cannot occur (D-115); the test names where the guarantee actually lands.

## A quarantined blob does not block a checkout

§6's single recovery exception: a parent whose documents parse but whose evidence blob is missing or
fails its digest can still be checked out, recaptured, and promoted as a replacement. Refusing the
checkout would leave the owner with a bundle they cannot repair through any supported path. So the
quarantine is *reported* — as a blocker, so the exit code says the result is not usable as-is — and
the draft is produced with its parent digest intact.

## Installation is atomic

Every draft is built in a temporary directory beside its destination and renamed into place. A
refusal therefore cannot leave a partial draft that a later command would mistake for a real one,
and `init`'s own "this name already exists" check cannot be defeated by its own wreckage.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Final

from boardwatch.profile_bundle import secret_scan
from boardwatch.profile_bundle.blobs import (
    BlobDigestMismatchError,
    BlobNotFoundError,
    read_blob,
)
from boardwatch.profile_bundle.canonical import (
    MappingBlobReader,
    evidence_set_digest,
    referenced_blob_digests,
)
from boardwatch.profile_bundle.errors import (
    BundleIoError,
    Diagnostic,
    IssueCode,
    OperationOutcome,
    ProfileBundleError,
    diagnostic,
    outcome_with,
)
from boardwatch.profile_bundle.layout import DocumentKind, SourceFile, discover_source_files
from boardwatch.profile_bundle.models.documents import (
    AffiliationsDocument,
    AwardsDocument,
    BulletCandidatesDocument,
    BundleDocuments,
    CertificationsDocument,
    CoursesDocument,
    DocumentModel,
    EducationDocument,
    EvidenceRecordsDocument,
    GatedFactsDocument,
    MetricRecordsDocument,
    PatentsDocument,
    PresentationsDocument,
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
    SourceLedger,
)
from boardwatch.profile_bundle.models.manifests import DraftManifest, RevisionManifest
from boardwatch.profile_bundle.models.policy import (
    AssertionTagCatalog,
    PredicateCatalog,
    RelationCatalog,
    SkillCategoryCatalog,
    SourceCatalog,
    UnitCatalog,
)
from boardwatch.profile_bundle.models.sidecars import EMPTY_SIDECAR
from boardwatch.profile_bundle.paths import (
    LOCAL_SOURCES_FILE,
    approvals_dir,
    blobs_dir,
    current_path,
    draft_root,
    drafts_dir,
    local_sources_path,
    require_draft_name,
    revisions_dir,
)
from boardwatch.profile_bundle.schema import CURRENT_SCHEMA_VERSION
from boardwatch.profile_bundle.storage import (
    SelectedRevision,
    SelectionError,
    read_current_once,
)
from boardwatch.profile_bundle.validation.context import load_documents
from boardwatch.profile_bundle.yaml_writer import document_bytes

MANIFEST_PATH: Final = PurePosixPath("manifest.yaml")
EVIDENCE_PATH: Final = PurePosixPath("evidence/records.yaml")

#: The version every catalog an `init` writes declares, and therefore the version its manifest pins.
#: The manifest's copy is derived from the catalogs below rather than restated, so the two cannot
#: drift into a `catalog_version_mismatch` the writer itself produced.
INITIAL_CATALOG_VERSION: Final = 1

#: Generic on purpose. The bundle is built to fit anyone who runs it, so `init` cannot know whose
#: profile this is or what field they work in; both are ordinary draft content the owner edits
#: before the first promotion, and neither is referenced by any rule.
DEFAULT_PROFILE_ID: Final = "profile.owner"
DEFAULT_CAREER_FIELD: Final = "unspecified"

#: Declared directories that hold one file per entity. Created empty so an owner can see where an
#: employment or project file belongs; the grammar admits them empty.
_ENTITY_DIRECTORIES: Final[tuple[PurePosixPath, ...]] = (
    PurePosixPath("facts/experience"),
    PurePosixPath("facts/projects"),
)


class BlobQuarantineReason(StrEnum):
    """Why a referenced blob could not be used. A closed catalog, never a free-text explanation."""

    MISSING = "missing"
    DIGEST_MISMATCH = "digest_mismatch"


@dataclass(frozen=True)
class DraftHandle:
    """One writable draft and the revision it descends from.

    Both parent fields are null together for the revision-1 draft `init` creates and set together
    for every checkout, mirroring `DraftManifest`'s own all-or-nothing rule so a caller cannot read
    a parentage from the handle that the manifest on disk does not state.
    """

    name: str
    root: Path
    draft_of_revision: int | None
    parent_bundle_digest: str | None


def init_draft(bundle_root: Path, *, name: str) -> OperationOutcome[DraftHandle]:
    """Create the bundle skeleton and one empty, parentless revision-1 draft (§19).

    Refuses once `CURRENT` exists: after a first promotion the only writable path is `checkout`, and
    a second parentless draft could otherwise be promoted as a revision 1 that replaced history.
    """
    draft_name = require_draft_name(name)
    if current_path(bundle_root).exists():
        return _refusal(
            IssueCode.CURRENT_ALREADY_EXISTS,
            f"{bundle_root} already selects a revision; use checkout to create a draft from it",
        )
    target = draft_root(bundle_root, draft_name)
    if target.exists():
        return _refusal(
            IssueCode.DRAFT_ALREADY_EXISTS,
            f"drafts/{draft_name} already exists; choose another draft name",
        )

    documents = _empty_documents()
    manifest = _initial_manifest(documents)
    try:
        _ensure_skeleton(bundle_root)
        _write_local_sources(bundle_root)
        _install(bundle_root, target, lambda staging: _write_tree(staging, manifest, documents))
    except OSError as exc:
        return _refusal(IssueCode.IO_ERROR, f"could not create {target}: {exc}")

    return OperationOutcome.clean(
        DraftHandle(
            name=draft_name, root=target, draft_of_revision=None, parent_bundle_digest=None
        )
    )


def checkout_current(bundle_root: Path, *, name: str) -> OperationOutcome[DraftHandle]:
    """Copy the selected revision into a writable draft that names it as its parent (§19)."""
    draft_name = require_draft_name(name)
    target = draft_root(bundle_root, draft_name)
    if target.exists():
        return _refusal(
            IssueCode.DRAFT_ALREADY_EXISTS,
            f"drafts/{draft_name} already exists; choose another draft name",
        )
    try:
        selection = read_current_once(bundle_root)
    except SelectionError as exc:
        return _refusal(exc.code, str(exc))
    try:
        sources = discover_source_files(selection.root, final_revision=True)
        parent = load_documents(selection.root, mode="revision")
    except SelectionError as exc:
        return _refusal(exc.code, str(exc))
    except ProfileBundleError as exc:
        return _refusal(_code_for(exc), f"{selection.root.name}: {exc}")

    manifest = _draft_manifest_of(parent.manifest, selection)
    quarantined = _blob_quarantine(bundle_root, parent)
    try:
        _install(
            bundle_root,
            target,
            lambda staging: _copy_tree(staging, sources, manifest),
        )
    except OSError as exc:
        return _refusal(IssueCode.IO_ERROR, f"could not create {target}: {exc}")

    handle = DraftHandle(
        name=draft_name,
        root=target,
        draft_of_revision=manifest.draft_of_revision,
        parent_bundle_digest=manifest.parent_bundle_digest,
    )
    return outcome_with(handle, quarantined)


# --------------------------------------------------------------------------------------
# The empty tree an `init` authors
# --------------------------------------------------------------------------------------


def _empty_documents() -> Mapping[PurePosixPath, DocumentModel]:
    """Every declared document that has a representable empty form.

    `policy/secret-scan.yaml` is the exception to "empty": §12.2 makes a revision's recorded ruleset
    its assertion about what its captures passed, and `validate_evidence_structural` compares those
    rows against this build's catalog. An empty ruleset would make the first revision claim a scan
    it never ran. The catalog is read from the module at call time rather than bound at import, so a
    build that retains a newer head writes the newer head.
    """
    ruleset = secret_scan.builtin_ruleset(secret_scan.CURRENT_RULESET_VERSION)
    empty_facts: dict[str, object] = {"facts": [], "entities": []}
    version = INITIAL_CATALOG_VERSION
    return {
        PurePosixPath("facts/education.yaml"): EducationDocument.model_validate(empty_facts),
        PurePosixPath("facts/publications.yaml"): PublicationsDocument.model_validate(empty_facts),
        PurePosixPath("facts/awards.yaml"): AwardsDocument.model_validate(empty_facts),
        PurePosixPath("facts/certifications.yaml"): CertificationsDocument.model_validate(
            empty_facts
        ),
        PurePosixPath("facts/affiliations.yaml"): AffiliationsDocument.model_validate(empty_facts),
        PurePosixPath("facts/courses.yaml"): CoursesDocument.model_validate(empty_facts),
        PurePosixPath("facts/presentations.yaml"): PresentationsDocument.model_validate(
            empty_facts
        ),
        PurePosixPath("facts/patents.yaml"): PatentsDocument.model_validate(empty_facts),
        PurePosixPath("claims/bullet-candidates.yaml"): BulletCandidatesDocument.model_validate(
            {"claims": []}
        ),
        PurePosixPath("claims/summary-candidates.yaml"): SummaryCandidatesDocument.model_validate(
            {"claims": []}
        ),
        PurePosixPath("skills/inventory.yaml"): SkillInventoryDocument.model_validate(
            {"skills": []}
        ),
        PurePosixPath("metrics/records.yaml"): MetricRecordsDocument.model_validate(
            {"metrics": []}
        ),
        EVIDENCE_PATH: EvidenceRecordsDocument.model_validate({"evidence": []}),
        PurePosixPath("conflicts/groups.yaml"): ConflictGroups.model_validate({"conflicts": []}),
        PurePosixPath("conflicts/rulings.yaml"): ConflictRulings.model_validate({"rulings": []}),
        PurePosixPath("policy/predicates.yaml"): PredicateCatalog.model_validate(
            {"predicates_version": version, "predicates": []}
        ),
        PurePosixPath("policy/units.yaml"): UnitCatalog.model_validate(
            {"units_version": version, "units": []}
        ),
        PurePosixPath("policy/relations.yaml"): RelationCatalog.model_validate(
            {"relations_version": version, "relations": []}
        ),
        PurePosixPath("policy/sources.yaml"): SourceCatalog.model_validate(
            {"sources_version": version, "sources": []}
        ),
        PurePosixPath("policy/skill-categories.yaml"): SkillCategoryCatalog.model_validate(
            {
                "catalog_version": version,
                "career_field": DEFAULT_CAREER_FIELD,
                "categories": [],
            }
        ),
        PurePosixPath("policy/assertion-tags.yaml"): AssertionTagCatalog.model_validate(
            {"assertion_tags_version": version, "assertion_tags": []}
        ),
        PurePosixPath("policy/secret-scan.yaml"): ruleset,
        PurePosixPath("relations/records.yaml"): RelationRecordsDocument.model_validate(
            {"relations": []}
        ),
        PurePosixPath("imports/source-ledger.yaml"): SourceLedger.model_validate(
            {"ledger_version": version, "sources": [], "records": []}
        ),
        PurePosixPath("imports/candidates.yaml"): CandidatePackage.model_validate(
            {"candidates_version": version, "candidates": []}
        ),
        PurePosixPath("imports/exclusions.yaml"): ExclusionLedger.model_validate(
            {"exclusions_version": version, "exclusions": []}
        ),
        PurePosixPath("application/gated-facts.yaml"): GatedFactsDocument.model_validate(
            {"facts": []}
        ),
        PurePosixPath("history/changes.yaml"): ChangeLedger.model_validate({"changes": []}),
        PurePosixPath("history/approvals.yaml"): ApprovalLedger.model_validate({"approvals": []}),
    }


def _initial_manifest(documents: Mapping[PurePosixPath, DocumentModel]) -> DraftManifest:
    """The revision-1 draft manifest, with every catalog version read off the catalog it pins.

    `evidence_set_digest` is computed from these documents rather than authored: it is the one
    manifest field that is a statement about content, and a placeholder would make the first
    `validate` report a mismatch against a bundle nobody had edited.
    """
    catalogs = _catalog_versions(documents)
    provisional = DraftManifest.model_validate(
        {
            "state": "draft",
            "schema_version": CURRENT_SCHEMA_VERSION,
            "profile_id": DEFAULT_PROFILE_ID,
            "draft_of_revision": None,
            "parent_bundle_digest": None,
            "bundle_digest": "",
            "evidence_set_digest": "sha256:" + "0" * 64,
            "approved_candidate_digest": "",
            "approval_stamp_id": "",
            "change_id": "",
            **catalogs,
        }
    )
    # The empty evidence document names no blobs, so the reader is never consulted; supplying an
    # empty one keeps the computation on the same code path every other caller uses.
    digest = evidence_set_digest(
        BundleDocuments(manifest=provisional, by_path=dict(documents)), MappingBlobReader({})
    )
    return provisional.model_copy(update={"evidence_set_digest": digest})


def _catalog_versions(documents: Mapping[PurePosixPath, DocumentModel]) -> dict[str, int]:
    predicates = documents[PurePosixPath("policy/predicates.yaml")]
    units = documents[PurePosixPath("policy/units.yaml")]
    relations = documents[PurePosixPath("policy/relations.yaml")]
    categories = documents[PurePosixPath("policy/skill-categories.yaml")]
    tags = documents[PurePosixPath("policy/assertion-tags.yaml")]
    ruleset = documents[PurePosixPath("policy/secret-scan.yaml")]
    assert isinstance(predicates, PredicateCatalog)
    assert isinstance(units, UnitCatalog)
    assert isinstance(relations, RelationCatalog)
    assert isinstance(categories, SkillCategoryCatalog)
    assert isinstance(tags, AssertionTagCatalog)
    assert isinstance(ruleset, secret_scan.SecretRuleset)
    return {
        "predicate_catalog_version": predicates.predicates_version,
        "unit_catalog_version": units.units_version,
        "relation_catalog_version": relations.relations_version,
        "skill_category_catalog_version": categories.catalog_version,
        "assertion_tag_catalog_version": tags.assertion_tags_version,
        "secret_scan_ruleset_version": ruleset.ruleset_version,
    }


# --------------------------------------------------------------------------------------
# The draft a `checkout` derives
# --------------------------------------------------------------------------------------


def _draft_manifest_of(
    manifest: DraftManifest | RevisionManifest, selection: SelectedRevision
) -> DraftManifest:
    """The parent's manifest, re-stated as a draft of that parent.

    Everything content-derived is carried across unchanged — schema version, profile ID, catalog
    versions, evidence-set digest — because the documents beside it are copied unchanged. Only the
    fields that describe *this tree's* state are rewritten.
    """
    return DraftManifest.model_validate(
        {
            "state": "draft",
            "schema_version": manifest.schema_version,
            "profile_id": manifest.profile_id,
            "draft_of_revision": selection.revision,
            "parent_bundle_digest": selection.bundle_digest,
            "bundle_digest": "",
            "evidence_set_digest": manifest.evidence_set_digest,
            "approved_candidate_digest": "",
            "approval_stamp_id": "",
            "change_id": "",
            "predicate_catalog_version": manifest.predicate_catalog_version,
            "unit_catalog_version": manifest.unit_catalog_version,
            "relation_catalog_version": manifest.relation_catalog_version,
            "skill_category_catalog_version": manifest.skill_category_catalog_version,
            "assertion_tag_catalog_version": manifest.assertion_tag_catalog_version,
            "secret_scan_ruleset_version": manifest.secret_scan_ruleset_version,
        }
    )


def _blob_quarantine(bundle_root: Path, documents: BundleDocuments) -> tuple[Diagnostic, ...]:
    """Report every referenced blob that is absent or does not hash to the digest naming it.

    `read_blob` is the one reader that verifies, and its two typed failures are exactly the two
    reasons §6 admits for the recovery path — so the classification comes from the exception type,
    never from its message.
    """
    findings: list[Diagnostic] = []
    for declared in referenced_blob_digests(documents):
        reason: BlobQuarantineReason | None = None
        try:
            read_blob(bundle_root, declared)
        except BlobNotFoundError:
            reason = BlobQuarantineReason.MISSING
        except BlobDigestMismatchError:
            reason = BlobQuarantineReason.DIGEST_MISMATCH
        except BundleIoError as exc:
            findings.append(diagnostic(IssueCode.IO_ERROR, str(exc), path=EVIDENCE_PATH.as_posix()))
            continue
        if reason is None:
            continue
        findings.append(
            diagnostic(
                IssueCode.CORRUPT_BLOB_QUARANTINE,
                f"blob sha256:{declared} is quarantined ({reason.value}); the draft was created so "
                "the evidence can be recaptured, and nothing was moved or deleted",
                path=EVIDENCE_PATH.as_posix(),
                reason=reason.value,
                blob=declared,
            )
        )
    return tuple(findings)


# --------------------------------------------------------------------------------------
# Filesystem
# --------------------------------------------------------------------------------------


def _ensure_skeleton(bundle_root: Path) -> None:
    for directory in (
        approvals_dir(bundle_root),
        revisions_dir(bundle_root),
        drafts_dir(bundle_root),
        blobs_dir(bundle_root),
    ):
        directory.mkdir(parents=True, exist_ok=True)


def _write_local_sources(bundle_root: Path) -> None:
    """Write the private sidecar, empty, unless the owner already has one.

    Present-and-empty rather than absent: "no local originals are mapped" is then a state an owner
    can see and `inventory` can report a parse failure for, instead of an absent file that every
    reader has to treat as an empty one.
    """
    path = local_sources_path(bundle_root)
    if path.exists():
        return
    path.write_bytes(
        document_bytes(
            EMPTY_SIDECAR.model_dump(mode="json"), logical_path=PurePosixPath(LOCAL_SOURCES_FILE)
        )
    )
    path.chmod(0o600)


def _install(bundle_root: Path, target: Path, populate: Callable[[Path], None]) -> None:
    """Build the draft beside its destination and rename it into place.

    A partial draft left by an interrupted copy would satisfy the "already exists" check of every
    later command while holding half a revision.
    """
    drafts_dir(bundle_root).mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(dir=drafts_dir(bundle_root), prefix=".tmp-draft-"))
    try:
        populate(staging)
        os.replace(staging, target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _write_tree(
    staging: Path, manifest: DraftManifest, documents: Mapping[PurePosixPath, DocumentModel]
) -> None:
    for logical in _ENTITY_DIRECTORIES:
        (staging / logical).mkdir(parents=True, exist_ok=True)
    _write_document(staging, MANIFEST_PATH, manifest)
    for logical, document in sorted(documents.items(), key=str):
        _write_document(staging, logical, document)


def _write_document(staging: Path, logical: PurePosixPath, document: DocumentModel) -> None:
    path = staging / logical
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(document_bytes(document.model_dump(mode="json"), logical_path=logical))


def _copy_tree(
    staging: Path, sources: Sequence[SourceFile], manifest: DraftManifest
) -> None:
    """Copy the declared documents verbatim and write the derived manifest over the parent's.

    `sources` comes from `discover_source_files`, which has already refused symlinks, undeclared
    files, and anything outside the closed grammar — so this loop copies exactly the revision's
    documents and `COMPLETE`, which is not among them, cannot follow the tree into a draft.
    """
    for source in sources:
        if source.kind is DocumentKind.MANIFEST:
            continue
        target = staging / source.logical_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source.abspath, target)
    for logical in _ENTITY_DIRECTORIES:
        (staging / logical).mkdir(parents=True, exist_ok=True)
    _write_document(staging, MANIFEST_PATH, manifest)


def _refusal(code: IssueCode, message: str) -> OperationOutcome[DraftHandle]:
    return outcome_with(None, (diagnostic(code, message),))


def _code_for(exc: ProfileBundleError) -> IssueCode:
    """The typed load failures a revision tree can produce, mapped from the exception TYPE."""
    return IssueCode.IO_ERROR if isinstance(exc, BundleIoError) else IssueCode.UNKNOWN_FILE


__all__ = [
    "DEFAULT_CAREER_FIELD",
    "DEFAULT_PROFILE_ID",
    "BlobQuarantineReason",
    "DraftHandle",
    "checkout_current",
    "init_draft",
]
