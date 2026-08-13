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
