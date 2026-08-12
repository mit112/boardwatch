"""The closed logical-file grammar (design §6).

The grammar is closed in BOTH directions on purpose. An undeclared file is a validation error, so
a future tailoring policy cannot become authority by being dropped into `policy/`; and a declared
file that is absent is an error too, so a bundle cannot lose its predicate catalog and still
validate. Design §6 states the first half explicitly; the second is what stops "the catalog is
empty" from being indistinguishable from "the catalog is gone".
"""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

import pytest

from boardwatch.profile_bundle.errors import BundleLayoutError, IssueCode
from boardwatch.profile_bundle.layout import (
    ENTITY_DOCUMENT_DIRECTORIES,
    FIXED_DOCUMENTS,
    DocumentKind,
    discover_source_files,
    entity_id_for_path,
    missing_fixed_documents,
    owner_for_path,
)
from boardwatch.profile_bundle.validation.context import parse_error_diagnostics

DECLARED_TAILORING_REFUSALS = (
    "policy/persona.yaml",
    "policy/selection.yaml",
    "policy/role-families.yaml",
    "policy/summary.yaml",
)


def _write_tree(root: Path, paths: tuple[str, ...]) -> None:
    for rel in paths:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}\n", encoding="utf-8")


def _complete_tree() -> tuple[str, ...]:
    return tuple(str(path) for path in FIXED_DOCUMENTS) + (
        "facts/experience/employment.example-labs.yaml",
        "facts/projects/project.packet-pantry.yaml",
    )


def test_every_declared_file_has_exactly_one_owner_kind() -> None:
    assert len(set(FIXED_DOCUMENTS.values())) == len(FIXED_DOCUMENTS)


def test_the_declared_tree_is_the_design_tree() -> None:
    """A drifted grammar silently changes what 'a complete bundle' means."""
    assert {str(path) for path in FIXED_DOCUMENTS} == {
        "manifest.yaml",
        "facts/identity.yaml",
        "facts/education.yaml",
        "facts/publications.yaml",
        "facts/awards.yaml",
        "facts/certifications.yaml",
        "facts/affiliations.yaml",
        "facts/courses.yaml",
        "facts/presentations.yaml",
        "facts/patents.yaml",
        "claims/bullet-candidates.yaml",
        "claims/summary-candidates.yaml",
        "skills/inventory.yaml",
        "metrics/records.yaml",
        "evidence/records.yaml",
        "conflicts/groups.yaml",
        "conflicts/rulings.yaml",
        "policy/predicates.yaml",
        "policy/units.yaml",
        "policy/relations.yaml",
        "policy/sources.yaml",
        "policy/skill-categories.yaml",
        "policy/assertion-tags.yaml",
        "policy/secret-scan.yaml",
        "relations/records.yaml",
        "imports/source-ledger.yaml",
        "imports/candidates.yaml",
        "imports/exclusions.yaml",
        "application/gated-facts.yaml",
        "history/changes.yaml",
        "history/approvals.yaml",
    }


def test_entity_directories_are_exactly_experience_and_projects() -> None:
    assert {str(path) for path in ENTITY_DOCUMENT_DIRECTORIES} == {
        "facts/experience",
        "facts/projects",
    }


@pytest.mark.parametrize("declared", sorted(str(path) for path in FIXED_DOCUMENTS))
def test_every_declared_path_resolves_to_its_kind(declared: str) -> None:
    assert isinstance(owner_for_path(PurePosixPath(declared)), DocumentKind)


def test_entity_owned_paths_resolve_to_their_kind_and_id() -> None:
    experience = PurePosixPath("facts/experience/employment.example-labs.yaml")
    project = PurePosixPath("facts/projects/project.packet-pantry.yaml")
    assert owner_for_path(experience) is DocumentKind.EMPLOYMENT_FACTS
    assert owner_for_path(project) is DocumentKind.PROJECT_FACTS
    assert entity_id_for_path(experience) == "employment.example-labs"
    assert entity_id_for_path(project) == "project.packet-pantry"


@pytest.mark.parametrize(
    "path",
    [
        *DECLARED_TAILORING_REFUSALS,
        "facts/identity.yml",
        "facts/identity.json",
        "facts/identity.yaml.swp",
        ".facts/identity.yaml",
        "facts/.identity.yaml",
        "notes.md",
        "facts/experience.yaml",
        "facts/projects/project.packet-pantry.yml",
        "facts/experience/project.wrong-prefix.yaml",
        "facts/projects/employment.wrong-prefix.yaml",
        "facts/experience/Employment.Upper.yaml",
        "facts/experience/nested/employment.a.yaml",
        "policy/predicates/extra.yaml",
        "claims/other-candidates.yaml",
    ],
)
def test_undeclared_or_wrong_extension_paths_are_refused(path: str) -> None:
    with pytest.raises(BundleLayoutError):
        owner_for_path(PurePosixPath(path))


def test_complete_marker_is_not_a_source_document() -> None:
    with pytest.raises(BundleLayoutError):
        owner_for_path(PurePosixPath("COMPLETE"))


def test_discovery_accepts_a_complete_draft_tree(tmp_path: Path) -> None:
    _write_tree(tmp_path, _complete_tree())
    found = discover_source_files(tmp_path, final_revision=False)
    assert {str(entry.logical_path) for entry in found} == set(_complete_tree())
    assert missing_fixed_documents(found) == ()


def test_discovery_reports_a_missing_declared_file(tmp_path: Path) -> None:
    tree = tuple(p for p in _complete_tree() if p != "policy/predicates.yaml")
    _write_tree(tmp_path, tree)
    found = discover_source_files(tmp_path, final_revision=False)
    assert missing_fixed_documents(found) == (PurePosixPath("policy/predicates.yaml"),)


def test_empty_entity_directories_are_legal(tmp_path: Path) -> None:
    """A profile with no employment yet is incomplete, not structurally invalid."""
    _write_tree(tmp_path, tuple(str(p) for p in FIXED_DOCUMENTS))
    (tmp_path / "facts" / "experience").mkdir(parents=True, exist_ok=True)
    (tmp_path / "facts" / "projects").mkdir(parents=True, exist_ok=True)
    found = discover_source_files(tmp_path, final_revision=False)
    assert missing_fixed_documents(found) == ()


@pytest.mark.parametrize("stray", [*DECLARED_TAILORING_REFUSALS, "policy/anything.yaml", "extra.yaml"])
def test_discovery_refuses_an_undeclared_file(tmp_path: Path, stray: str) -> None:
    _write_tree(tmp_path, (*_complete_tree(), stray))
    with pytest.raises(BundleLayoutError) as excinfo:
        discover_source_files(tmp_path, final_revision=False)
    assert stray in str(excinfo.value)


def test_complete_marker_is_permitted_only_in_a_final_revision(tmp_path: Path) -> None:
    _write_tree(tmp_path, _complete_tree())
    (tmp_path / "COMPLETE").write_bytes(
        ("sha256:" + "0" * 64 + "\n").encode("utf-8")
    )
    found = discover_source_files(tmp_path, final_revision=True)
    assert "COMPLETE" not in {str(entry.logical_path) for entry in found}
    with pytest.raises(BundleLayoutError):
        discover_source_files(tmp_path, final_revision=False)


def test_symlinked_document_is_refused_before_its_bytes_are_read(tmp_path: Path) -> None:
    _write_tree(tmp_path, _complete_tree())
    outside = tmp_path.parent / "outside.yaml"
    outside.write_text("{}\n", encoding="utf-8")
    (tmp_path / "facts" / "identity.yaml").unlink()
    (tmp_path / "facts" / "identity.yaml").symlink_to(outside)
    with pytest.raises(BundleLayoutError):
        discover_source_files(tmp_path, final_revision=False)


@pytest.mark.skipif(os.name != "posix", reason="mkfifo is POSIX-only")
def test_fifo_document_is_refused_before_its_bytes_are_read(tmp_path: Path) -> None:
    """A FIFO at a declared document's path must be refused, never opened.

    `discover_source_files` only classifies each entry; nothing here calls `open()`, so this test
    cannot hang even if the guard regresses — it would instead fail `pytest.raises` outright,
    because an unguarded `discover_source_files` returns the FIFO as an ordinary `SourceFile`
    without reading it. The hang, if any, happens one layer up, in whichever caller then tries to
    read the bytes this function handed back.
    """
    _write_tree(tmp_path, _complete_tree())
    fifo_path = tmp_path / "facts" / "education.yaml"
    fifo_path.unlink()
    os.mkfifo(fifo_path)
    with pytest.raises(BundleLayoutError) as excinfo:
        discover_source_files(tmp_path, final_revision=False)
    assert "facts/education.yaml" in str(excinfo.value)
    assert "not a regular file" in str(excinfo.value)
    # The field a consumer actually branches on: the diagnostic code this exception maps to at the
    # command boundary, not just the message a human reads.
    diagnostics = parse_error_diagnostics(excinfo.value)
    assert len(diagnostics) == 1
    assert diagnostics[0].code == IssueCode.UNKNOWN_FILE


def test_symlinked_directory_is_refused(tmp_path: Path) -> None:
    _write_tree(tmp_path, _complete_tree())
    outside = tmp_path.parent / "outside-dir"
    outside.mkdir(exist_ok=True)
    extra = tmp_path / "policy" / "linked"
    extra.symlink_to(outside, target_is_directory=True)
    with pytest.raises(BundleLayoutError):
        discover_source_files(tmp_path, final_revision=False)


def test_discovery_is_sorted_so_diagnostics_are_deterministic(tmp_path: Path) -> None:
    _write_tree(tmp_path, _complete_tree())
    found = discover_source_files(tmp_path, final_revision=False)
    paths = [str(entry.logical_path) for entry in found]
    assert paths == sorted(paths)
