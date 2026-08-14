"""Deterministic extraction: read enumerated records through the declarative mapping and propose
candidates (Gate B, Slice B).

The mapping lives in the bundle as data (D-172, D-174); this module is the interpreter that reads
it. It imports no `boardwatch.store` module and holds no I/O — it turns records plus rules into
`ProposedCandidate`s, which the existing `build_candidate_package` (`imports.py`) then types and
identifies.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from boardwatch.profile_bundle.enumerators import EnumeratedSourceRecord
from boardwatch.profile_bundle.imports import ProposedCandidate
from boardwatch.profile_bundle.models.facts import FactValue, SkillRefValue, StringValue


@dataclass(frozen=True)
class ExtractionRule:
    """One declarative mapping rule (§6.2a).

    `value_from` / `display_from` name a field of the record's `atomic_value`, or `.` for a scalar
    record. `predicate` is a literal here; the model-lookup and value-selector operations the spec
    also defines are added when the buckets that need them are built.
    """

    locator_pattern: str
    predicate: str
    value_from: str
    value_type: str
    display_from: str


def _field(atomic_value: object, name: str) -> object:
    if name == ".":
        return atomic_value
    if isinstance(atomic_value, Mapping):
        return atomic_value[name]
    raise KeyError(name)


_SKILL_ID_NON_SLUG = re.compile(r"[^a-z0-9]+")


def _derive_skill_id(item: str) -> str:
    """A deterministic, human-readable `skill.<slug>` id from a skill item string.

    Lossy on purpose — `C++` and `C#` both slug to `skill.c` — because identity is content-addressed
    and the verbatim item is preserved as `original_display_value`, so the real name is never lost,
    and referential validation of the id against the inventory is the promotion slice's job (§6.4),
    not this layer's. An item with no alphanumeric content yields no id — a `value_not_typeable`
    case.
    """
    slug = _SKILL_ID_NON_SLUG.sub("-", item.lower()).strip("-")
    if not slug:
        raise ValueError(f"skill item {item!r} has no alphanumeric content to derive an id from")
    return f"skill.{slug}"


def _build_value(value_type: str, raw: object) -> FactValue:
    if value_type == "string":
        return StringValue(type="string", value=str(raw))
    if value_type == "skill_ref":
        return SkillRefValue(type="skill_ref", skill_id=_derive_skill_id(str(raw)))
    raise NotImplementedError(f"value_type {value_type!r} is not built yet")


def extract_proposals(
    records: Sequence[EnumeratedSourceRecord], rules: Sequence[ExtractionRule]
) -> list[ProposedCandidate]:
    """Every candidate the rules propose over the records, in record-then-rule order.

    A record may match several rules that produce different candidates (multi-output emission,
    §6.2a); a rule whose pattern does not match a record produces nothing.
    """
    proposals: list[ProposedCandidate] = []
    for record in records:
        for rule in rules:
            if not locator_matches(rule.locator_pattern, record.normalized_locator):
                continue
            raw = _field(record.atomic_value, rule.value_from)
            display = str(_field(record.atomic_value, rule.display_from))
            proposals.append(
                ProposedCandidate(
                    source_record_id=record.source_record_id,
                    predicate=rule.predicate,
                    value=_build_value(rule.value_type, raw),
                    original_display_value=display,
                )
            )
    return proposals


def locator_matches(pattern: str, locator: str) -> bool:
    """Whether a segment-wise `pattern` matches a `normalized_locator`.

    Each pattern segment is either `*` (matches any one segment) or a literal (matches that segment
    exactly). Literal non-head segments are legal and load-bearing: `header/1` selects the
    professional name and does not match `header/2`, the email (§6.2a). A regex over locators would
    be a second grammar that drifts from the emitter, so there is none.
    """
    pattern_segments = pattern.split("/")
    locator_segments = locator.split("/")
    if len(pattern_segments) != len(locator_segments):
        return False
    return all(
        p == "*" or p == actual
        for p, actual in zip(pattern_segments, locator_segments, strict=True)
    )
