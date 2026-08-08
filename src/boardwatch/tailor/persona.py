"""Persona registry (P4 item 7).

A persona is a résumé-PRESENTATION lens: it reorders which résumé facts are
surfaced and under which headline title. It never touches eligibility, the
profile singleton, or a lead's ship/drop decision. A persona's `entries` subset
is a subset of the master résumé's ENTRIES — never of eligibility facts.

Multi-tenancy mirrors `taxonomy.load_taxonomy` / `catalog.load_rules`: the
registry ships as a bundled package resource; a user override at
{config_dir}/personas.yaml wins wholesale when present. `version` is
deterministic in installed wheels: SHA-256 of the CANONICAL effective YAML
(parsed, sorted, re-serialized) combined with PERSONA_REVISION, bumped whenever
persona *semantics* change.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml

from boardwatch.extract.role_family import ROLE_FAMILIES, classify_role_family
from boardwatch.tailor.model import Resume, SkillGroup

PERSONA_REVISION = 1

# The closed output set of `classify_role_family`, derived from the classifier itself so the
# two can never drift: every priority-ordered family plus the fall-through "general_swe".
VALID_ROLE_FAMILIES: frozenset[str] = frozenset(name for name, _ in ROLE_FAMILIES) | {"general_swe"}


class PersonaError(Exception):
    """A persona registry is malformed, or a persona references an unknown résumé fact.

    Typed at the raise site — never classified by string-matching the message. Surfaced as a
    load-time fatal (the pipeline aborts the run), never as a per-lead degrade."""


@dataclass(frozen=True)
class Persona:
    id: str
    title: str
    default: bool
    role_families: tuple[str, ...]
    skill_group_order: tuple[str, ...]
    entries: tuple[str, ...] | None


@dataclass(frozen=True)
class PersonaRegistry:
    personas: tuple[Persona, ...]
    version: str

    def default(self) -> Persona:
        for persona in self.personas:
            if persona.default:
                return persona
        # load_personas guarantees exactly one default; this is a defensive backstop.
        raise PersonaError("registry has no default persona")


def bundled_personas_text() -> str:
    return (files("boardwatch.tailor") / "personas.yaml").read_text(encoding="utf-8")


def load_personas(config_dir: Path) -> PersonaRegistry:
    """`{config_dir}/personas.yaml` overrides the bundled seed. Validates exactly-one-default,
    unique ids, and closed-catalog role_families; any violation raises `PersonaError`."""
    override = config_dir / "personas.yaml"
    if override.is_file():
        text, origin = override.read_text(encoding="utf-8"), str(override)
    else:
        text, origin = bundled_personas_text(), "bundled personas.yaml"
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise PersonaError(f"{origin}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise PersonaError(f"{origin}: the document must be a mapping")
    raw = data.get("personas")
    if not isinstance(raw, list) or not raw:
        raise PersonaError(f"{origin}: 'personas' must be a non-empty list")

    personas: list[Persona] = []
    seen: set[str] = set()
    defaults = 0
    for entry in raw:
        if not isinstance(entry, dict):
            raise PersonaError(f"{origin}: persona entries must be mappings: {entry!r}")
        pid = str(entry.get("id", "")).strip()
        title = str(entry.get("title", "")).strip()
        if not pid or not title:
            raise PersonaError(f"{origin}: persona missing id/title: {entry!r}")
        if pid in seen:
            raise PersonaError(f"{origin}: duplicate persona id {pid!r}")
        seen.add(pid)
        is_default = bool(entry.get("default", False))
        if is_default:
            defaults += 1
        role_families = _string_tuple(entry.get("role_families"), origin, pid, "role_families")
        for family in role_families:
            if family not in VALID_ROLE_FAMILIES:
                raise PersonaError(
                    f"{origin}: persona {pid!r} role_family {family!r} is not in the closed "
                    f"classify_role_family output set {sorted(VALID_ROLE_FAMILIES)}"
                )
        skill_group_order = _string_tuple(
            entry.get("skill_group_order"), origin, pid, "skill_group_order"
        )
        entries_raw = entry.get("entries")
        if entries_raw is None:
            entries: tuple[str, ...] | None = None
        else:
            entries = _string_tuple(entries_raw, origin, pid, "entries")
        personas.append(
            Persona(
                id=pid,
                title=title,
                default=is_default,
                role_families=role_families,
                skill_group_order=skill_group_order,
                entries=entries,
            )
        )
    if defaults != 1:
        raise PersonaError(
            f"{origin}: exactly one persona must be default (found {defaults})"
        )
    return PersonaRegistry(personas=tuple(personas), version=_version_of(data))


def _string_tuple(value: Any, origin: str, pid: str, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise PersonaError(f"{origin}: persona {pid!r} {field} must be a list of strings")
    return tuple(value)


def _version_of(document: Any) -> str:
    """SHA-256 of the CANONICAL effective YAML (parsed, sorted, compact JSON) combined with
    PERSONA_REVISION. Mirrors `taxonomy._version_of`: formatting never matters, content does."""
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"))
    raw = f"{canonical}|persona_revision={PERSONA_REVISION}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def select_persona(jd_title: str, registry: PersonaRegistry) -> Persona:
    """Deterministic, never a model call: classify the JD title into a role family, then pick
    the first persona (in registry order) that claims it; empty/whitespace title or a family no
    persona claims falls back to the default persona."""
    if not jd_title.strip():
        return registry.default()
    family = classify_role_family(jd_title)
    for persona in registry.personas:
        if family in persona.role_families:
            return persona
    return registry.default()


def apply_persona(master: Resume, persona: Persona, resolved_title: str) -> Resume:
    """Return a NEW frozen Resume shaped by the persona — never mutating `master`.

    `title` becomes `resolved_title`; `skill_groups` are reordered by `skill_group_order`
    (unlisted groups keep their relative order, appended after); `entries` are selected and
    ordered per `persona.entries` (unchanged when None). An unknown entry id raises
    `PersonaError` — a persona never silently drops a résumé fact."""
    order = persona.skill_group_order
    if order:
        rank = {label: i for i, label in enumerate(order)}
        # Stable sort: listed groups take their configured rank; unlisted groups share the
        # sentinel rank len(order) and keep their master-relative order after the listed ones.
        skill_groups: list[SkillGroup] = sorted(
            master.skill_groups, key=lambda g: rank.get(g.label, len(order))
        )
    else:
        skill_groups = list(master.skill_groups)

    if persona.entries is None:
        entries = list(master.entries)
    else:
        by_id = {e.entry_id: e for e in master.entries}
        missing = [eid for eid in persona.entries if eid not in by_id]
        if missing:
            raise PersonaError(
                f"persona {persona.id!r} references unknown entry_id(s) {missing} "
                "not present in the master résumé"
            )
        entries = [by_id[eid] for eid in persona.entries]

    return master.model_copy(
        update={"title": resolved_title, "skill_groups": skill_groups, "entries": entries}
    )
