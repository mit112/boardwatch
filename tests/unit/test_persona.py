from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from boardwatch.tailor.model import Bullet, Entry, Resume, SkillGroup
from boardwatch.tailor.persona import (
    Persona,
    PersonaError,
    PersonaRegistry,
    apply_persona,
    load_personas,
    select_persona,
)

_VALID = (
    "personas:\n"
    "  - id: general_swe\n"
    '    title: "Software Engineer"\n'
    "    default: true\n"
    "    role_families: [backend, frontend, fullstack, general_swe]\n"
    "    skill_group_order: [Languages, Backend]\n"
    "    entries: null\n"
    "  - id: ios\n"
    '    title: "iOS Engineer"\n'
    "    default: false\n"
    "    role_families: [mobile]\n"
    "    skill_group_order: [Languages]\n"
    "    entries: null\n"
)


def _write(tmp_path: Path, text: str) -> Path:
    (tmp_path / "personas.yaml").write_text(text, encoding="utf-8")
    return tmp_path


# --- load_personas -------------------------------------------------------------------


def test_bundled_registry_loads() -> None:
    reg = load_personas(Path("/nonexistent-config-dir"))
    assert isinstance(reg, PersonaRegistry)
    assert reg.default().id == "general_swe"
    assert any(p.id == "ios" for p in reg.personas)


def test_config_dir_override_wins(tmp_path: Path) -> None:
    cfg = _write(
        tmp_path,
        "personas:\n"
        "  - id: only\n"
        '    title: "Only One"\n'
        "    default: true\n"
        "    role_families: [general_swe]\n"
        "    skill_group_order: []\n"
        "    entries: null\n",
    )
    reg = load_personas(cfg)
    assert [p.id for p in reg.personas] == ["only"]


def test_zero_default_is_an_error(tmp_path: Path) -> None:
    cfg = _write(
        tmp_path,
        "personas:\n"
        "  - id: a\n"
        '    title: "A"\n'
        "    default: false\n"
        "    role_families: [general_swe]\n"
        "    skill_group_order: []\n"
        "    entries: null\n",
    )
    with pytest.raises(PersonaError):
        load_personas(cfg)


def test_more_than_one_default_is_an_error(tmp_path: Path) -> None:
    cfg = _write(
        tmp_path,
        "personas:\n"
        "  - id: a\n"
        '    title: "A"\n'
        "    default: true\n"
        "    role_families: [general_swe]\n"
        "    skill_group_order: []\n"
        "    entries: null\n"
        "  - id: b\n"
        '    title: "B"\n'
        "    default: true\n"
        "    role_families: [backend]\n"
        "    skill_group_order: []\n"
        "    entries: null\n",
    )
    with pytest.raises(PersonaError):
        load_personas(cfg)


def test_duplicate_id_is_an_error(tmp_path: Path) -> None:
    cfg = _write(
        tmp_path,
        "personas:\n"
        "  - id: dup\n"
        '    title: "A"\n'
        "    default: true\n"
        "    role_families: [general_swe]\n"
        "    skill_group_order: []\n"
        "    entries: null\n"
        "  - id: dup\n"
        '    title: "B"\n'
        "    default: false\n"
        "    role_families: [backend]\n"
        "    skill_group_order: []\n"
        "    entries: null\n",
    )
    with pytest.raises(PersonaError):
        load_personas(cfg)


def test_duplicate_entries_id_is_an_error(tmp_path: Path) -> None:
    # A hand-authored override that repeats an entry_id must fail loudly at load time,
    # not silently render the same fact twice (model_copy skips Resume._unique_ids).
    cfg = _write(
        tmp_path,
        "personas:\n"
        "  - id: a\n"
        '    title: "A"\n'
        "    default: true\n"
        "    role_families: [general_swe]\n"
        "    skill_group_order: []\n"
        "    entries: [acme, acme]\n",
    )
    with pytest.raises(PersonaError):
        load_personas(cfg)


def test_role_family_outside_closed_set_is_an_error(tmp_path: Path) -> None:
    cfg = _write(
        tmp_path,
        "personas:\n"
        "  - id: a\n"
        '    title: "A"\n'
        "    default: true\n"
        "    role_families: [not_a_real_family]\n"
        "    skill_group_order: []\n"
        "    entries: null\n",
    )
    with pytest.raises(PersonaError):
        load_personas(cfg)


def test_version_is_deterministic_over_content(tmp_path: Path) -> None:
    a = load_personas(_write(tmp_path, _VALID))
    b = load_personas(_write(tmp_path, _VALID))  # same content, second load
    assert a.version == b.version


def test_changed_content_changes_version(tmp_path: Path) -> None:
    a = load_personas(_write(tmp_path, _VALID))
    changed = _VALID.replace('"iOS Engineer"', '"iOS Developer"')
    b = load_personas(_write(tmp_path, changed))
    assert a.version != b.version


# --- select_persona ------------------------------------------------------------------


def _reg(tmp_path: Path) -> PersonaRegistry:
    return load_personas(_write(tmp_path, _VALID))


def test_select_mobile_title_picks_ios(tmp_path: Path) -> None:
    reg = _reg(tmp_path)
    assert select_persona("Senior iOS Engineer", reg).id == "ios"


def test_select_backend_title_picks_general(tmp_path: Path) -> None:
    reg = _reg(tmp_path)
    assert select_persona("Backend Engineer", reg).id == "general_swe"
    assert select_persona("Full Stack Developer", reg).id == "general_swe"
    assert select_persona("Software Engineer", reg).id == "general_swe"


def test_select_empty_title_is_default(tmp_path: Path) -> None:
    reg = _reg(tmp_path)
    assert select_persona("", reg).id == "general_swe"
    assert select_persona("   ", reg).id == "general_swe"


def test_select_unclaimed_family_falls_back_to_default(tmp_path: Path) -> None:
    # A registry whose only persona claims backend; a security title matches no persona.
    cfg = _write(
        tmp_path,
        "personas:\n"
        "  - id: be\n"
        '    title: "Backend Engineer"\n'
        "    default: true\n"
        "    role_families: [backend]\n"
        "    skill_group_order: []\n"
        "    entries: null\n",
    )
    reg = load_personas(cfg)
    assert select_persona("Security Engineer", reg).id == "be"


def test_select_is_deterministic(tmp_path: Path) -> None:
    reg = _reg(tmp_path)
    assert select_persona("Senior iOS Engineer", reg).id == select_persona(
        "Senior iOS Engineer", reg
    ).id


# --- apply_persona -------------------------------------------------------------------


def _master() -> Resume:
    return Resume(
        header=["Ada", "ada@example.com"],
        education=["BSc"],
        skill_groups=[
            SkillGroup(label="Backend", items=["Django"]),
            SkillGroup(label="Frontend", items=["React"]),
            SkillGroup(label="Languages", items=["Python"]),
        ],
        entries=[
            Entry(entry_id="e1", heading="h1", bullets=[Bullet(bullet_id="b1", text="one")]),
            Entry(entry_id="e2", heading="h2", bullets=[Bullet(bullet_id="b2", text="two")]),
        ],
    )


def _persona(**kw: object) -> Persona:
    base: dict[str, object] = {
        "id": "p",
        "title": "Software Engineer",
        "default": True,
        "role_families": ("backend",),
        "skill_group_order": (),
        "entries": None,
    }
    base.update(kw)
    return Persona(**base)  # type: ignore[arg-type]


def test_apply_reorders_skill_groups_unlisted_appended() -> None:
    m = _master()
    p = _persona(skill_group_order=("Languages", "Backend"))
    out = apply_persona(m, p, "Backend Engineer")
    assert [g.label for g in out.skill_groups] == ["Languages", "Backend", "Frontend"]
    # master untouched
    assert [g.label for g in m.skill_groups] == ["Backend", "Frontend", "Languages"]


def test_apply_entries_none_keeps_all_in_master_order() -> None:
    out = apply_persona(_master(), _persona(entries=None), "T")
    assert [e.entry_id for e in out.entries] == ["e1", "e2"]


def test_apply_entries_list_selects_and_orders_subset() -> None:
    out = apply_persona(_master(), _persona(entries=("e2",)), "T")
    assert [e.entry_id for e in out.entries] == ["e2"]


def test_apply_unknown_entry_id_raises() -> None:
    with pytest.raises(PersonaError):
        apply_persona(_master(), _persona(entries=("nope",)), "T")


def test_apply_sets_title_and_result_is_frozen_master_unmutated() -> None:
    m = _master()
    out = apply_persona(m, _persona(), "iOS Engineer")
    assert out.title == "iOS Engineer"
    assert m.title is None  # master unchanged
    with pytest.raises(ValidationError):
        out.title = "mutated"  # frozen model rejects attribute reassignment
