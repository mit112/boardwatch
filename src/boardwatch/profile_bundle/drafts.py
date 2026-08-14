"""`init` and `checkout`: the two ways a writable draft comes into existence (design §6, §19).

Both commands end in the same place — a populated `drafts/<name>/`, or a refusal that created no
draft — and differ in everything before it.

"No draft" rather than "nothing at all", deliberately: `init` also creates the root skeleton and the
empty private sidecar, and those are outside the draft's rollback because they are what the *next*
attempt needs in order to run. A bundle root holding four empty directories is the state `init`
exists to produce, not wreckage from one that failed, and re-running is idempotent.

That only holds while every write it leaves behind is a *complete* one, which is why the sidecar is
staged and renamed rather than written in place. A truncated `local-sources.yaml` would be reported
by `inventory` as an error, and the retry — which skips an existing sidecar — would never repair it.

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

The same reasoning is why a blob the store cannot *read at all* refuses before installation: §21's
exit 3 says the check could not run, and a caller retrying it must not be met with
`draft_already_exists` from the attempt that reported it could not run. A blob that is missing or
fails its digest is a different case — that is §6's recovery path, and it produces the draft.

## The operator-facing wording is not settled here

The structural layer names `facts/identity.yaml` as a missing required file, which reads as
corruption rather than as "author your identity here". Translating that for a human is T18's, at the
command boundary; this module deliberately reports the machine-readable fact.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final

from boardwatch.profile_bundle import predicate_catalog, secret_scan
from boardwatch.profile_bundle.blobs import quarantined_blobs
from boardwatch.profile_bundle.canonical import (
    EVIDENCE_PATH,
    CanonicalizationError,
    MappingBlobReader,
    evidence_set_digest,
    referenced_blob_digests,
)
from boardwatch.profile_bundle.errors import (
    Diagnostic,
    IssueCode,
    OperationOutcome,
    ProfileBundleError,
    diagnostic,
    io_reason,
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
    require_confined_root,
    selected_documents,
)
from boardwatch.profile_bundle.validation.context import parse_error_diagnostics
from boardwatch.profile_bundle.yaml_writer import document_bytes

MANIFEST_PATH: Final = PurePosixPath("manifest.yaml")

#: The version every catalog an `init` writes declares, and therefore the version its manifest pins.
#: The manifest's copy is derived from the catalogs below rather than restated, so the two cannot
#: drift into a `catalog_version_mismatch` the writer itself produced.
INITIAL_CATALOG_VERSION: Final = 1

#: Generic on purpose. The bundle is built to fit anyone who runs it, so `init` cannot know whose
#: profile this is or what field they work in; both are ordinary draft content the owner edits
#: before the first promotion, and neither is referenced by any rule.
DEFAULT_PROFILE_ID: Final = "profile.owner"
DEFAULT_CAREER_FIELD: Final = "unspecified"

#: The prefix every draft installation temporary uses. `inventory` reads this constant and reports
#: an entry carrying it as an interrupted install rather than as an artefact that does not belong
#: under `drafts/` at all.
DRAFT_TEMP_PREFIX: Final = ".tmp-draft-"

#: The prefix the private sidecar's staged write uses. It sits at the bundle root because that is
#: where its destination is, and an atomic rename needs both on one filesystem. Unlike a declared
#: member, a leftover one is genuinely outside the root grammar, so `inventory`'s existing
#: undeclared-entry finding says the right thing about it and no second rule is needed.
SIDECAR_TEMP_PREFIX: Final = ".tmp-local-sources-"

#: Declared directories that hold one file per entity. Created empty so an owner can see where an
#: employment or project file belongs; the grammar admits them empty.
_ENTITY_DIRECTORIES: Final[tuple[PurePosixPath, ...]] = (
    PurePosixPath("facts/experience"),
    PurePosixPath("facts/projects"),
)


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
    # The one caller that runs before the root exists: `_ensure_skeleton` below creates it, so an
    # absent root is this command's normal input rather than a mistyped argument.
    if (refusal := _unconfined(bundle_root, must_exist=False)) is not None:
        return refusal
    if current_path(bundle_root).exists():
        return _refusal(
            IssueCode.CURRENT_ALREADY_EXISTS,
            "this bundle already selects a revision; use checkout to create a draft from it",
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
    except OSError as exc:
        # Reported apart from the draft: a failure here has not touched `drafts/` at all, and a
        # message naming the draft would send the owner looking in the wrong place.
        return _refusal(
            IssueCode.IO_ERROR, f"could not create the bundle skeleton: {io_reason(exc)}"
        )
    try:
        _install(bundle_root, target, lambda staging: _write_tree(staging, manifest, documents))
    except OSError as exc:
        return _refusal(
            IssueCode.IO_ERROR, f"could not create drafts/{draft_name}: {io_reason(exc)}"
        )

    return OperationOutcome.clean(
        DraftHandle(
            name=draft_name, root=target, draft_of_revision=None, parent_bundle_digest=None
        )
    )


def checkout_current(bundle_root: Path, *, name: str) -> OperationOutcome[DraftHandle]:
    """Copy the selected revision into a writable draft that names it as its parent (§19)."""
    draft_name = require_draft_name(name)
    # Before the name is examined: a draft name that collides with something outside the bundle is
    # not a name collision, and reporting one would name the wrong problem.
    if (refusal := _unconfined(bundle_root)) is not None:
        return refusal
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
        # `selected_documents` rather than a bare parse: §6 clause 4 makes the reader verify the
        # manifest's identity against the pointer, and a draft that recorded the wrong parent digest
        # would be refused at promotion with nothing left to explain it.
        parent = selected_documents(selection)
        manifest = _draft_manifest_of(parent.manifest, selection)
        quarantined = _blob_quarantine(bundle_root, parent)
    except SelectionError as exc:
        return _refusal(exc.code, str(exc))
    except CanonicalizationError as exc:
        # Ahead of the load-failure arm, and not routed through it: reading the parent's evidence
        # set is not a load, so `parse_error_diagnostics` has no arm for it and fell through to
        # `internal_error` — "file a bug" for a revision whose evidence document is merely absent,
        # which the control and `inventory` both report as the missing file it is.
        return outcome_with(
            None,
            (
                diagnostic(
                    IssueCode.MISSING_REQUIRED_FILE,
                    f"{exc}; the parent's blob references were not read, so no draft was created",
                    path=EVIDENCE_PATH.as_posix(),
                ),
            ),
        )
    except ProfileBundleError as exc:
        # `parse_error_diagnostics` is already the mapping from a typed load failure to its code,
        # and it keeps every finding a `BundleParseError` carries instead of collapsing a list of
        # broken fields into one. A second copy here reported a future schema version as an unknown
        # file and a grammar violation as "could not run at all".
        return outcome_with(None, parse_error_diagnostics(exc))

    try:
        _install(
            bundle_root,
            target,
            lambda staging: _copy_tree(staging, sources, manifest),
        )
    except OSError as exc:
        return _refusal(
            IssueCode.IO_ERROR, f"could not create drafts/{draft_name}: {io_reason(exc)}"
        )

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
    predicates = predicate_catalog.builtin_catalog(predicate_catalog.CURRENT_CATALOG_VERSION)
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
        PurePosixPath("policy/predicates.yaml"): predicates,
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

    The classification is `blobs.quarantined_blobs` — shared with promotion, which asks the same
    question about the parent revision and must not answer it differently. Only the sentence is
    this command's: what an owner does next depends on which command found the quarantine.
    """
    return tuple(
        diagnostic(
            IssueCode.CORRUPT_BLOB_QUARANTINE,
            f"blob sha256:{declared} is quarantined ({reason.value}); the draft was created so "
            "the evidence can be recaptured, and nothing was moved or deleted",
            path=EVIDENCE_PATH.as_posix(),
            reason=reason.value,
            blob=declared,
        )
        for declared, reason in quarantined_blobs(
            bundle_root, referenced_blob_digests(documents)
        )
    )


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

    Written through a temporary and renamed, for the same reason a draft is: a plain write that
    failed halfway would leave a *truncated* sidecar, and `inventory` reports an unparseable one as
    an error — so a failed `init` would hand the owner a corrupt file that the retry, which skips an
    existing sidecar, would never repair. An interrupted write leaves a `.tmp-` entry at the root
    instead, which is genuinely undeclared and reported as such.

    The temporary is created by `mkstemp`, so the file is never briefly readable by anyone else on
    the way to its final mode.
    """
    path = local_sources_path(bundle_root)
    if path.exists():
        return
    handle, temporary = tempfile.mkstemp(dir=bundle_root, prefix=SIDECAR_TEMP_PREFIX)
    staged = Path(temporary)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(
                document_bytes(
                    EMPTY_SIDECAR.model_dump(mode="json"),
                    logical_path=PurePosixPath(LOCAL_SOURCES_FILE),
                )
            )
        staged.chmod(0o600)
        os.replace(staged, path)
    except BaseException:
        staged.unlink(missing_ok=True)
        raise


def _install(bundle_root: Path, target: Path, populate: Callable[[Path], None]) -> None:
    """Build the draft beside its destination and rename it into place.

    A partial draft left by an interrupted copy would satisfy the "already exists" check of every
    later command while holding half a revision.
    """
    drafts_dir(bundle_root).mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(dir=drafts_dir(bundle_root), prefix=DRAFT_TEMP_PREFIX))
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


def _unconfined(
    bundle_root: Path, *, must_exist: bool = True
) -> OperationOutcome[DraftHandle] | None:
    """`require_confined_root` as a refusal, so both commands enter through the one check."""
    try:
        require_confined_root(bundle_root, must_exist=must_exist)
    except SelectionError as exc:
        return _refusal(exc.code, str(exc))
    return None


__all__ = [
    "DEFAULT_CAREER_FIELD",
    "DEFAULT_PROFILE_ID",
    "DraftHandle",
    "checkout_current",
    "init_draft",
]
