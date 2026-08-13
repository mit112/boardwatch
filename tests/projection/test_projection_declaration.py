"""`projection.yaml`: closed catalogs, and a digest that moves when content moves."""

from __future__ import annotations

from pathlib import Path

import pytest

from boardwatch.projection.declaration import (
    EntryKind,
    load_declaration,
    projection_digest,
)
from boardwatch.projection.errors import ProjectionError, ProjectionIssue

MINIMAL = """\
projection_version: 1
shell_source: {shell}
open_range_label: Present
skill_groups:
  - label: Languages
    skills: [skill.example-language]
entries:
  - entity_id: project.packet-pantry
    kind: project
    pinned: true
    heading: '{{@display_name}}'
    claims: [claim.packet-pantry.backend.001]
no_match_fallback: []
extracurricular: []
"""


def _write(tmp_path: Path, body: str) -> Path:
    shell = tmp_path / "master_resume.yaml"
    shell.write_text("header: []\neducation: []\n", encoding="utf-8")
    path = tmp_path / "projection.yaml"
    path.write_text(body.format(shell=shell.as_posix()), encoding="utf-8")
    return path


def test_a_minimal_declaration_loads(tmp_path: Path) -> None:
    decl = load_declaration(_write(tmp_path, MINIMAL))
    assert decl.projection_version == 1
    assert decl.entries[0].kind is EntryKind.PROJECT
    assert decl.entries[0].pinned is True
    assert decl.open_range_label == "Present"


def test_an_out_of_catalog_kind_is_fatal_and_names_the_entity(tmp_path: Path) -> None:
    """The catalog exists because `Entry.kind` is an open `str` and an out-of-catalog value
    makes the renderer drop the entry from the PDF silently (`tailor/render/latex.py:155,170`)."""
    body = MINIMAL.replace("kind: project", "kind: publication")
    with pytest.raises(ProjectionError) as exc:
        load_declaration(_write(tmp_path, body))
    assert exc.value.violation.issue is ProjectionIssue.UNKNOWN_ENTRY_KIND
    assert "project.packet-pantry" in exc.value.violation.where


def test_a_duplicated_entity_id_is_fatal(tmp_path: Path) -> None:
    """Without this, `entry_id = "entry." + entity_id` is not total and the failure surfaces
    much later as the frozen model's bare `duplicate entry_id` with no projection context."""
    # The second entry must attach to the `entries:` list, so rebuild rather than concatenate.
    body = MINIMAL.replace(
        "no_match_fallback: []",
        "  - entity_id: project.packet-pantry\n"
        "    kind: project\n"
        "    pinned: false\n"
        "    heading: 'Again'\n"
        "    claims: []\n"
        "no_match_fallback: []",
    )
    with pytest.raises(ProjectionError) as exc:
        load_declaration(_write(tmp_path, body))
    assert exc.value.violation.issue is ProjectionIssue.DUPLICATE_ENTITY_ID


def test_a_missing_open_range_label_is_fatal(tmp_path: Path) -> None:
    """No default: `end: null` has to render as the owner's own word, and inventing one would
    put authored English in code."""
    body = MINIMAL.replace("open_range_label: Present\n", "")
    with pytest.raises(ProjectionError) as exc:
        load_declaration(_write(tmp_path, body))
    assert exc.value.violation.issue is ProjectionIssue.MISSING_OPEN_RANGE_LABEL


def test_a_non_string_open_range_label_is_malformed_not_missing(tmp_path: Path) -> None:
    """`open_range_label: 0` is falsy but present. The old guard (`not raw.get(...)`) misreported
    this as a missing label; it is really a type error, and pydantic's own `str` validation is
    the truthful refusal."""
    body = MINIMAL.replace("open_range_label: Present", "open_range_label: 0")
    with pytest.raises(ProjectionError) as exc:
        load_declaration(_write(tmp_path, body))
    assert exc.value.violation.issue is ProjectionIssue.MALFORMED_DECLARATION


def test_a_missing_declaration_file_is_unreadable(tmp_path: Path) -> None:
    """`load_declaration` never reads a path that is not a file (`declaration.py:85`)."""
    path = tmp_path / "does-not-exist.yaml"
    with pytest.raises(ProjectionError) as exc:
        load_declaration(path)
    assert exc.value.violation.issue is ProjectionIssue.DECLARATION_UNREADABLE


def test_invalid_yaml_is_a_malformed_declaration(tmp_path: Path) -> None:
    """An unclosed flow sequence is invalid YAML, caught as `yaml.YAMLError` before any mapping
    check runs (`declaration.py:93`)."""
    path = tmp_path / "projection.yaml"
    path.write_text("projection_version: [1, 2\n", encoding="utf-8")
    with pytest.raises(ProjectionError) as exc:
        load_declaration(path)
    assert exc.value.violation.issue is ProjectionIssue.MALFORMED_DECLARATION


def test_a_non_mapping_document_is_a_malformed_declaration(tmp_path: Path) -> None:
    """Valid YAML that parses to a list, not a mapping, trips the `isinstance(raw, dict)` guard
    (`declaration.py:97`), distinct from the invalid-YAML guard above."""
    path = tmp_path / "projection.yaml"
    path.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(ProjectionError) as exc:
        load_declaration(path)
    assert exc.value.violation.issue is ProjectionIssue.MALFORMED_DECLARATION


def test_a_pydantic_validation_error_is_a_malformed_declaration(tmp_path: Path) -> None:
    """A well-formed mapping that is missing a required field (`shell_source` has no default)
    passes every pre-model guard and fails only at `ProjectionDeclaration.model_validate`
    (`declaration.py:119`)."""
    path = tmp_path / "projection.yaml"
    path.write_text(
        "projection_version: 1\n"
        "open_range_label: Present\n"
        "skill_groups: []\n"
        "entries: []\n"
        "no_match_fallback: []\n"
        "extracurricular: []\n",
        encoding="utf-8",
    )
    with pytest.raises(ProjectionError) as exc:
        load_declaration(path)
    assert exc.value.violation.issue is ProjectionIssue.MALFORMED_DECLARATION


def test_the_digest_changes_when_a_template_literal_changes(tmp_path: Path) -> None:
    """This is what reopens the owner gate. Editing a literal must not keep the old approval."""
    first = projection_digest(load_declaration(_write(tmp_path, MINIMAL)))
    changed = MINIMAL.replace("{{@display_name}}", "Senior {{@display_name}}")
    second = projection_digest(load_declaration(_write(tmp_path, changed)))
    assert first != second
    assert first.startswith("sha256:")


def test_the_digest_is_stable_across_formatting(tmp_path: Path) -> None:
    """Non-vacuity for the test above: the digest tracks content, not bytes."""
    first = projection_digest(load_declaration(_write(tmp_path, MINIMAL)))
    reflowed = MINIMAL.replace(
        "skills: [skill.example-language]", "skills:\n      - skill.example-language"
    )
    second = projection_digest(load_declaration(_write(tmp_path, reflowed)))
    assert first == second
