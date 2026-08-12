"""The closed logical-file grammar and owning-file rules (design §6).

The grammar is closed in both directions.

*Undeclared files are refused* so a later tailoring design cannot become authority by dropping
`policy/persona.yaml` into a revision: unknown-file validation is what makes "Gate A does not
accept those files yet" enforceable rather than aspirational.

*Declared files are required* so a bundle cannot lose its predicate catalog and still validate.
Without that half, "the catalog is empty" and "the catalog is gone" are the same observation, and
every predicate contract would silently stop being enforced.

Two directories are entity-owned: `facts/experience/<employment-id>.yaml` and
`facts/projects/<project-id>.yaml`. The basename must equal the contained entity ID — checked
syntactically here (prefix and ID grammar) and against the parsed content in structural
validation, because only the parse knows what the file actually contains.
"""

from __future__ import annotations

import re
import stat
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Final

from boardwatch.profile_bundle.errors import BundleLayoutError
from boardwatch.profile_bundle.paths import COMPLETE_FILE

DOCUMENT_SUFFIX: Final = ".yaml"

#: The record-kind grammar's tail, reused for the entity IDs that name entity-owned files.
_ID_TAIL: Final = r"[a-z0-9]+(?:[._-][a-z0-9]+)*"


class DocumentKind(StrEnum):
    """One kind per declared file. The kind, not the path, is what parsing dispatches on."""

    MANIFEST = "manifest"
    IDENTITY = "identity"
    EDUCATION = "education"
    EMPLOYMENT_FACTS = "employment_facts"
    PROJECT_FACTS = "project_facts"
    PUBLICATIONS = "publications"
    AWARDS = "awards"
    CERTIFICATIONS = "certifications"
    AFFILIATIONS = "affiliations"
    COURSES = "courses"
    PRESENTATIONS = "presentations"
    PATENTS = "patents"
    BULLET_CANDIDATES = "bullet_candidates"
    SUMMARY_CANDIDATES = "summary_candidates"
    SKILL_INVENTORY = "skill_inventory"
    METRIC_RECORDS = "metric_records"
    EVIDENCE_RECORDS = "evidence_records"
    CONFLICT_GROUPS = "conflict_groups"
    CONFLICT_RULINGS = "conflict_rulings"
    PREDICATE_CATALOG = "predicate_catalog"
    UNIT_CATALOG = "unit_catalog"
    RELATION_CATALOG = "relation_catalog"
    SOURCE_CATALOG = "source_catalog"
    SKILL_CATEGORY_CATALOG = "skill_category_catalog"
    ASSERTION_TAG_CATALOG = "assertion_tag_catalog"
    SECRET_SCAN_RULESET = "secret_scan_ruleset"
    RELATION_RECORDS = "relation_records"
    SOURCE_LEDGER = "source_ledger"
    IMPORT_CANDIDATES = "import_candidates"
    IMPORT_EXCLUSIONS = "import_exclusions"
    GATED_FACTS = "gated_facts"
    CHANGE_LEDGER = "change_ledger"
    APPROVAL_LEDGER = "approval_ledger"


FIXED_DOCUMENTS: Final[Mapping[PurePosixPath, DocumentKind]] = {
    PurePosixPath("manifest.yaml"): DocumentKind.MANIFEST,
    PurePosixPath("facts/identity.yaml"): DocumentKind.IDENTITY,
    PurePosixPath("facts/education.yaml"): DocumentKind.EDUCATION,
    PurePosixPath("facts/publications.yaml"): DocumentKind.PUBLICATIONS,
    PurePosixPath("facts/awards.yaml"): DocumentKind.AWARDS,
    PurePosixPath("facts/certifications.yaml"): DocumentKind.CERTIFICATIONS,
    PurePosixPath("facts/affiliations.yaml"): DocumentKind.AFFILIATIONS,
    PurePosixPath("facts/courses.yaml"): DocumentKind.COURSES,
    PurePosixPath("facts/presentations.yaml"): DocumentKind.PRESENTATIONS,
    PurePosixPath("facts/patents.yaml"): DocumentKind.PATENTS,
    PurePosixPath("claims/bullet-candidates.yaml"): DocumentKind.BULLET_CANDIDATES,
    PurePosixPath("claims/summary-candidates.yaml"): DocumentKind.SUMMARY_CANDIDATES,
    PurePosixPath("skills/inventory.yaml"): DocumentKind.SKILL_INVENTORY,
    PurePosixPath("metrics/records.yaml"): DocumentKind.METRIC_RECORDS,
    PurePosixPath("evidence/records.yaml"): DocumentKind.EVIDENCE_RECORDS,
    PurePosixPath("conflicts/groups.yaml"): DocumentKind.CONFLICT_GROUPS,
    PurePosixPath("conflicts/rulings.yaml"): DocumentKind.CONFLICT_RULINGS,
    PurePosixPath("policy/predicates.yaml"): DocumentKind.PREDICATE_CATALOG,
    PurePosixPath("policy/units.yaml"): DocumentKind.UNIT_CATALOG,
    PurePosixPath("policy/relations.yaml"): DocumentKind.RELATION_CATALOG,
    PurePosixPath("policy/sources.yaml"): DocumentKind.SOURCE_CATALOG,
    PurePosixPath("policy/skill-categories.yaml"): DocumentKind.SKILL_CATEGORY_CATALOG,
    PurePosixPath("policy/assertion-tags.yaml"): DocumentKind.ASSERTION_TAG_CATALOG,
    PurePosixPath("policy/secret-scan.yaml"): DocumentKind.SECRET_SCAN_RULESET,
    PurePosixPath("relations/records.yaml"): DocumentKind.RELATION_RECORDS,
    PurePosixPath("imports/source-ledger.yaml"): DocumentKind.SOURCE_LEDGER,
    PurePosixPath("imports/candidates.yaml"): DocumentKind.IMPORT_CANDIDATES,
    PurePosixPath("imports/exclusions.yaml"): DocumentKind.IMPORT_EXCLUSIONS,
    PurePosixPath("application/gated-facts.yaml"): DocumentKind.GATED_FACTS,
    PurePosixPath("history/changes.yaml"): DocumentKind.CHANGE_LEDGER,
    PurePosixPath("history/approvals.yaml"): DocumentKind.APPROVAL_LEDGER,
}

#: directory -> (document kind, required entity-ID prefix)
ENTITY_DOCUMENT_DIRECTORIES: Final[Mapping[PurePosixPath, tuple[DocumentKind, str]]] = {
    PurePosixPath("facts/experience"): (DocumentKind.EMPLOYMENT_FACTS, "employment"),
    PurePosixPath("facts/projects"): (DocumentKind.PROJECT_FACTS, "project"),
}

_ENTITY_BASENAME_RE: Final[Mapping[str, re.Pattern[str]]] = {
    prefix: re.compile(rf"^{prefix}\.{_ID_TAIL}$")
    for _, prefix in ENTITY_DOCUMENT_DIRECTORIES.values()
}

#: Every directory the grammar admits. Anything else is an undeclared directory.
_DECLARED_DIRECTORIES: Final[frozenset[PurePosixPath]] = frozenset(
    {path.parent for path in FIXED_DOCUMENTS if path.parent != PurePosixPath(".")}
    | set(ENTITY_DOCUMENT_DIRECTORIES)
)


@dataclass(frozen=True)
class SourceFile:
    """One declared document: its revision-relative logical path, its bytes' location, its kind."""

    logical_path: PurePosixPath
    abspath: Path
    kind: DocumentKind


def owner_for_path(path: PurePosixPath) -> DocumentKind:
    """The document kind that owns `path`, or `BundleLayoutError` if nothing does."""
    fixed = FIXED_DOCUMENTS.get(path)
    if fixed is not None:
        return fixed
    entity = ENTITY_DOCUMENT_DIRECTORIES.get(path.parent)
    if entity is not None and path.suffix == DOCUMENT_SUFFIX:
        kind, prefix = entity
        if _ENTITY_BASENAME_RE[prefix].match(path.stem):
            return kind
        raise BundleLayoutError(
            f"{path}: an entity-owned file under {path.parent} must be named "
            f"<{prefix}-id>.yaml matching the record-kind grammar"
        )
    raise BundleLayoutError(f"{path}: not a declared bundle document")


def entity_id_for_path(path: PurePosixPath) -> str:
    """The entity ID an entity-owned file's basename declares.

    The parsed content must agree; that check needs the parse and lives in structural validation.
    """
    owner_for_path(path)
    if path.parent not in ENTITY_DOCUMENT_DIRECTORIES:
        raise BundleLayoutError(f"{path}: not an entity-owned document")
    return path.stem


def missing_fixed_documents(found: Iterable[SourceFile]) -> tuple[PurePosixPath, ...]:
    """Declared files absent from `found`, sorted.

    Required rather than optional: an absent catalog would otherwise be indistinguishable from an
    empty one, and every contract it holds would stop being enforced without a diagnostic.
    """
    present = {entry.logical_path for entry in found}
    return tuple(sorted(set(FIXED_DOCUMENTS) - present))


def discover_source_files(root: Path, *, final_revision: bool) -> tuple[SourceFile, ...]:
    """Every declared document under `root`, sorted by logical path.

    A final revision permits exactly one non-source file, `COMPLETE`; a draft permits none.
    Symlinks are refused before any bytes are read: a symlinked document would let content from
    outside the bundle enter its digest, and the bundle's self-containment claim would be false.

    Every entry this returns is later opened for reading — by `load_documents`, by promotion's
    verbatim copy, by `checkout`'s copy of a parent's tree — and none of those readers takes a
    timeout. A FIFO or a socket is neither a symlink nor a directory, so it would otherwise reach
    `found` and the first of those readers would block in `open()` forever, holding the bundle lock
    for `promote`. The regular-file check is one `lstat` per entry, the same shape
    `storage._require_stored_blob` uses for the blob store and for the same reason: the entry has
    already been proven not to be a symlink, so the only remaining question is whether it is content
    with bytes to read at all.
    """
    found: list[SourceFile] = []
    for abspath in sorted(root.rglob("*")):
        relative = PurePosixPath(abspath.relative_to(root).as_posix())
        if abspath.is_symlink():
            raise BundleLayoutError(
                f"{relative}: symlinks are refused inside a bundle tree; the bundle must be "
                "self-contained under one root"
            )
        if abspath.is_dir():
            if relative not in _DECLARED_DIRECTORIES:
                raise BundleLayoutError(f"{relative}: not a declared bundle directory")
            continue
        if relative == PurePosixPath(COMPLETE_FILE):
            if final_revision:
                continue
            raise BundleLayoutError(
                f"{COMPLETE_FILE} is permitted only inside a final revision, not in a draft"
            )
        if not stat.S_ISREG(abspath.lstat().st_mode):
            raise BundleLayoutError(
                f"{relative}: is not a regular file; a bundle document is read as bytes, and a "
                "directory, device or named pipe has none to give"
            )
        found.append(
            SourceFile(logical_path=relative, abspath=abspath, kind=owner_for_path(relative))
        )
    return tuple(found)
