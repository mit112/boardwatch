"""Task 15: refuse a persona that declares `entries`, before any selection runs.

`apply_persona` (`tailor/persona.py`) raises `PersonaError` when a persona's declared `entries`
names an id absent from whatever résumé it is applied to. Stage 2's own selection can legitimately
drop any candidate entry, so a persona shaped `entries: [e1, e2]` collides with selection the
moment stage 2 omits one of them — a crash deep inside `tailor run`, not a diagnosis. v1 forbids
the shape outright, checked here, before selection ever runs.

Both bundled personas ship `entries: null` (`tailor/personas.yaml:31,37`), so the positive control
below is the REAL no-override path, not a hand-built stand-in for it. The failing fixture must be
authored: nothing shipped can reproduce this collision.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from boardwatch.projection.errors import ProjectionError, ProjectionIssue
from boardwatch.projection.persona_preflight import reject_entry_declaring_personas
from boardwatch.tailor.persona import bundled_personas_text

_DEFAULT_DECLARES_ENTRIES = """
personas:
  - id: general_swe
    title: "Software Engineer"
    default: true
    role_families: [backend]
    skill_group_order: []
    entries: [entry.x, entry.y]
"""

_SECOND_DECLARES_ENTRIES = """
personas:
  - id: general_swe
    title: "Software Engineer"
    default: true
    role_families: [backend]
    skill_group_order: []
  - id: ios
    title: "iOS Engineer"
    default: false
    role_families: [mobile]
    skill_group_order: []
    entries: [entry.x]
"""


def test_persona_declaring_entries_is_refused_before_any_selection(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "personas.yaml").write_text(_DEFAULT_DECLARES_ENTRIES, encoding="utf-8")

    with pytest.raises(ProjectionError) as exc_info:
        reject_entry_declaring_personas(config_dir)

    assert exc_info.value.violation.issue == ProjectionIssue.PERSONA_DECLARES_ENTRIES
    assert "general_swe" in exc_info.value.violation.where


def test_a_non_default_persona_declaring_entries_is_also_refused(tmp_path: Path) -> None:
    """Proves the check iterates every persona, not just the first/default one."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "personas.yaml").write_text(_SECOND_DECLARES_ENTRIES, encoding="utf-8")

    with pytest.raises(ProjectionError) as exc_info:
        reject_entry_declaring_personas(config_dir)

    assert exc_info.value.violation.issue == ProjectionIssue.PERSONA_DECLARES_ENTRIES
    assert "ios" in exc_info.value.violation.where


def test_the_bundled_registry_passes_the_preflight(tmp_path: Path) -> None:
    """Positive control: with no override present, `load_personas` falls back to the bundled
    seed, whose two personas both ship `entries: null` — nothing shipped is affected."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    # The premise: the bundled seed really exists and really is non-empty, or a "no override"
    # test that happened to raise for an unrelated reason (a missing bundled resource) would
    # look identical to a passing preflight.
    assert bundled_personas_text().strip()

    reject_entry_declaring_personas(config_dir)  # must not raise
