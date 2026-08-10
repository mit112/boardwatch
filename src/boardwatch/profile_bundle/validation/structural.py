"""Layer 1: the tree is shaped the way the grammar says, and every record is addressable.

This layer answers questions no single document can answer about itself. A model validator sees one
file; only the assembled tree can say that two files claim the same ID, that a basename disagrees
with the entity inside it, or that the manifest's catalog versions disagree with the catalogs.

Everything here is derived from the parsed tree, never from the bytes. Re-reading a file to answer a
structural question would let a document validate under one reading and be indexed under another.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import PurePosixPath
from typing import Final

from boardwatch.profile_bundle.errors import Diagnostic, IssueCode, diagnostic
from boardwatch.profile_bundle.index import (
    duplicate_approval_ids,
    prefix_matches_kind,
    record_id_of,
)
from boardwatch.profile_bundle.layout import (
    ENTITY_DOCUMENT_DIRECTORIES,
    FIXED_DOCUMENTS,
    entity_id_for_path,
)
from boardwatch.profile_bundle.models.documents import (
    EmploymentFactsDocument,
    FactBearingDocument,
    ProjectFactsDocument,
)
from boardwatch.profile_bundle.validation.context import ValidationContext

#: The one document allowed to hold facts about a subject it does not own (§6, §16).
_GATED_FACTS: Final[PurePosixPath] = PurePosixPath("application/gated-facts.yaml")

#: manifest field -> (catalog attribute on the index, the catalog's own version field, its path).
#: Kept as data because the manifest pins six catalog versions and a seventh added in code but not
#: here would simply stop being checked — silently.
_CATALOG_VERSION_PINS: tuple[tuple[str, str, str, str], ...] = (
    ("predicate_catalog_version", "predicates", "predicates_version", "policy/predicates.yaml"),
    ("unit_catalog_version", "units", "units_version", "policy/units.yaml"),
    (
        "relation_catalog_version",
        "relation_catalog",
        "relations_version",
        "policy/relations.yaml",
    ),
    (
        "skill_category_catalog_version",
        "skill_categories",
        "catalog_version",
        "policy/skill-categories.yaml",
    ),
    (
        "assertion_tag_catalog_version",
        "assertion_tags",
        "assertion_tags_version",
        "policy/assertion-tags.yaml",
    ),
    (
        "secret_scan_ruleset_version",
        "secret_ruleset",
        "ruleset_version",
        "policy/secret-scan.yaml",
    ),
)


def validate_structural(ctx: ValidationContext) -> tuple[Diagnostic, ...]:
    """Every structural finding in the tree, unsorted (the report layer orders them)."""
    return tuple(
        finding
        for check in (
            _missing_declared_documents,
            _duplicate_record_ids,
            _record_kinds_match_their_ids,
            _entity_basenames_match_their_content,
            _facts_live_with_their_subjects,
            _catalog_versions_match_the_manifest,
            _duplicate_approval_entry_ids,
        )
        for finding in check(ctx)
    )


def _missing_declared_documents(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """Declared files absent from the tree.

    Computed against the parsed tree rather than the discovered files, so a file that was present
    but unparseable is reported by the load layer and not doubly reported here.
    """
    present = set(ctx.documents.by_path) | {PurePosixPath("manifest.yaml")}
    for path in sorted(set(FIXED_DOCUMENTS) - present):
        yield diagnostic(
            IssueCode.MISSING_REQUIRED_FILE,
            f"{path} is declared by the grammar but absent; an absent catalog is not an empty one",
            path=path.as_posix(),
        )


def _duplicate_record_ids(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """IDs claimed twice. §8 makes the namespace global, so the two owning paths are the finding."""
    for collision in ctx.index.collisions:
        yield diagnostic(
            IssueCode.DUPLICATE_RECORD_ID,
            f"{collision.record_id} is defined in both {collision.first_path} and "
            f"{collision.second_path}; record IDs are unique across the whole bundle",
            path=collision.second_path.as_posix(),
            record_id=collision.record_id,
            first_path=collision.first_path.as_posix(),
        )


def _record_kinds_match_their_ids(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """§20.1: "Record-kind prefixes agree with model kinds."

    Worth being straight about what this can and cannot catch. Every record's own ID field is
    pattern-pinned to its own prefix — `FactRecord.fact_id` is a `FactId`, and an employment
    entity's is an `EmploymentId` — so authored YAML cannot reach it: the model refuses first. It
    guards the models, not the data, and stays because §20.1 names it and because a future field
    widened to a bare `RecordId` would otherwise lose the guarantee with nothing failing.
    `test_prefix_matches_kind_*` exercises it directly for that reason.
    """
    for kind, records in sorted(ctx.index.by_kind.items()):
        for record in records:
            try:
                identifier = record_id_of(record)
            except TypeError:
                continue
            if prefix_matches_kind(identifier, kind):
                continue
            yield diagnostic(
                IssueCode.RECORD_KIND_MISMATCH,
                f"{identifier} is a {kind} record but its ID prefix does not say so",
                path=ctx.index.path_of(identifier),
                record_id=identifier,
                expected_kind=kind,
            )


def _entity_basenames_match_their_content(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """`facts/experience/<employment-id>.yaml` must contain that exact employment entity.

    The basename is what the digest's leaf key is built from (§7), so a file whose name and content
    disagree would give one entity two identities depending on which the reader trusted.
    """
    for path, document in ctx.documents.items():
        if path.parent not in ENTITY_DOCUMENT_DIRECTORIES:
            continue
        if not isinstance(document, EmploymentFactsDocument | ProjectFactsDocument):
            continue
        declared = entity_id_for_path(path)
        if document.entity.entity_id == declared:
            continue
        yield diagnostic(
            IssueCode.BASENAME_ID_MISMATCH,
            f"{path}: the file is named for {declared} but contains "
            f"{document.entity.entity_id}",
            path=path.as_posix(),
            record_id=document.entity.entity_id,
            basename_declares=declared,
        )


def _facts_live_with_their_subjects(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """§6: "Entity-owned files also own their subjects' atomic facts."

    The single exception the design names is `application/gated-facts.yaml`, which holds facts
    about any subject precisely so that application-only material is not scattered through the
    résumé-facing files.

    This matters for identity, not tidiness. §7 builds each document's digest leaf from its logical
    path, so filing a fact under the wrong entity changes which leaf carries it while leaving the
    fact's own bytes untouched — a record that reads correctly and hashes into the wrong place.
    """
    for path, document in ctx.documents.items():
        if path == _GATED_FACTS or not isinstance(document, FactBearingDocument):
            continue
        for fact in document.facts:
            owning = ctx.index.paths.get(fact.subject_id)
            if owning is None or owning == path:
                continue  # an unresolvable subject is a referential finding, not this one
            yield diagnostic(
                IssueCode.WRONG_OWNING_FILE,
                f"{path} holds {fact.fact_id}, whose subject {fact.subject_id} is owned by "
                f"{owning}; an entity's facts live in the file that owns the entity",
                path=path.as_posix(),
                record_id=fact.fact_id,
                subject_id=fact.subject_id,
                owning_file=owning.as_posix(),
            )


def _catalog_versions_match_the_manifest(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """The manifest's pinned catalog versions must equal the catalogs actually present.

    §7 puts these versions in the manifest so a revision records which policy it was validated
    against. A manifest claiming predicate catalog 3 beside catalog 2 would attribute this
    revision's clearances to rules it never ran.
    """
    manifest = ctx.manifest
    for manifest_field, index_attribute, version_field, path in _CATALOG_VERSION_PINS:
        catalog = getattr(ctx.index, index_attribute, None)
        if catalog is None:
            continue  # absence is already reported as a missing declared file
        pinned = getattr(manifest, manifest_field)
        actual = getattr(catalog, version_field)
        if pinned == actual:
            continue
        yield diagnostic(
            IssueCode.CATALOG_VERSION_MISMATCH,
            f"manifest.{manifest_field} is {pinned} but {path} declares {actual}",
            path="manifest.yaml",
            catalog_path=path,
            manifest_declares=pinned,
            catalog_declares=actual,
        )


def _duplicate_approval_entry_ids(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """Sub-approval IDs are globally unique across stamps (§13).

    Two stamps reusing an approval ID would let one revision's approval be cited as authority for
    another's, which is precisely the binding an approval stamp exists to make unforgeable.
    """
    for approval_id in duplicate_approval_ids(ctx.index.stamps):
        yield diagnostic(
            IssueCode.DUPLICATE_APPROVAL_ID,
            f"{approval_id} is used by more than one approval entry",
            path="history/approvals.yaml",
            record_id=approval_id,
        )
