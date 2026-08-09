"""The eligibility catalog: the SOLE source of family identity, questions, answer types,
choices, ranks, implies vocabularies, exclusive groups, superset relations, negation cues
and patterns (D-P2-4).

Nothing here is a source collection literal, because R9 flags any non-empty string
collection at a declaration position in a scoped module and has NO allowlist. A registry
dict, a degree ladder tuple, an implies vocabulary or a fact-to-type map in source would
each fail the gate this phase extends. They all live in rules.yaml instead.

Structurally this mirrors extract/taxonomy.py: a bundled package resource, a
{config_dir}/rules.yaml override that wins, and a content version that is the sha256 of
the CANONICAL parsed document combined with CATALOG_REVISION, so formatting never matters
and content always does.

The catalog is a TRUST ROOT and is content-pinned under R7 (D-P2-7): a wrong pattern is a
wrong verdict, which is the same treatment P0-5 gave its equivalence table.

Every optional pattern member is LOADED, COMPILED and CARRIED, never quietly ignored: the
five suppressor kinds, the jurisdiction map, the consumed cues and the doc-level cue
idioms are all mechanisms that keep a hedge, a company-side subject or a cross-sentence
escape from becoming a wrong verdict, so a loader that modelled only one of them would
report green while dropping the rest. Two of those drops were prototype findings 31 and
59, and their load-time guards (`_regex_list`, `_consumed_cues`) are ported here verbatim.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml

from boardwatch.eligibility.facts import Policy

CATALOG_REVISION = 2

_SCOPES = frozenset({"sentence", "clause"})
_REQUIREDNESS = frozenset({"required", "preferred", "bonus"})
_POLICIES = frozenset({"blocker", "preference", "ignore"})
_ANSWER_TYPES = frozenset({"bool", "int", "choice", "structured"})
_FIELD_TYPES = frozenset({"bool", "int", "choice", "choice_set"})
_TIERS = frozenset({"universal", "profile", "field"})


class CatalogError(ValueError):
    pass


@dataclass(frozen=True)
class FieldSpec:
    name: str
    type: str
    choices: tuple[str, ...]
    ranks: dict[str, int]


@dataclass(frozen=True)
class PatternSpec:
    id: str
    family: str
    requiredness: str
    implies: str
    scope: str
    regex: re.Pattern[str]
    requirement_text: str
    jurisdiction: str | None
    required_scheme: str | None
    required_level: str | None
    required_accesses: tuple[str, ...]
    required_rank: int | None
    # Document-scoped suppressor: any match anywhere in the posting stands the detection
    # down. Unused by the current catalog but kept so an override can express it.
    suppressed_by: tuple[re.Pattern[str], ...]
    # Unit-scoped (the sentence the match sits in): a hedge belongs here.
    suppressed_by_unit: tuple[re.Pattern[str], ...]
    # Unit-scoped and NOT clause-bounded: a same-sentence qualifying escape needs this
    # third scope, which is neither of the other two (finding 39).
    suppressed_by_sentence: tuple[re.Pattern[str], ...]
    # Must PRECEDE the detection inside its own clause: a grammatical subject only.
    subject_suppressors: tuple[re.Pattern[str], ...]
    # Document-scoped, but ABSTAINS instead of dropping: an escape that may waive the
    # requirement keeps the row visible rather than losing it to a wrong `eligible`.
    abstain_by: tuple[re.Pattern[str], ...]
    # Surface form -> jurisdiction code, for a pattern that CAPTURES the jurisdiction its
    # sentence scopes itself to. An absent surface resolves to `other`, which abstains.
    jurisdiction_map: dict[str, str]
    # Negation cues this pattern legitimately CONTAINS in its own match, so the cue-inside
    # guard does not drop it. Only a pattern whose subject IS the restriction qualifies.
    consumes_cues: tuple[str, ...]
    # Doc-level idioms in which a cue carries no polarity, stamped identically onto every
    # pattern by the loader. Catalog vocabulary, not a code constant.
    cue_idioms: tuple[re.Pattern[str], ...]

    @property
    def rule_id(self) -> str:
        """Composite identity, persisted as-is (D-P2-17).

        eligibility_requirements has no family column, so requirement identity has to
        survive inside this one string.
        """
        return f"{self.family}:{self.id}"


@dataclass(frozen=True)
class FamilySpec:
    id: str
    label: str
    fact: str
    answer_type: str
    default_policy: str
    question: str
    fields: tuple[FieldSpec, ...]
    implies_vocabulary: frozenset[str]
    exclusive_groups: tuple[frozenset[str], ...]
    patterns: tuple[PatternSpec, ...]
    superset_relations: tuple[dict[str, str], ...]
    tier: str
    applies_to: frozenset[str]

    @property
    def ranks(self) -> dict[str, int]:
        """The rank map, if this family declares one. The degree family carries a rank
        per choice instead of a ladder tuple in source (spec §4.1)."""
        for field_spec in self.fields:
            if field_spec.ranks:
                return field_spec.ranks
        return {}


@dataclass(frozen=True)
class RulesCatalog:
    families: tuple[FamilySpec, ...]
    negation_cues: tuple[str, ...]
    version: str
    source: str  # "override" | "bundled"
    career_fields: frozenset[str]

    def family(self, family_id: str) -> FamilySpec:
        for candidate in self.families:
            if candidate.id == family_id:
                return candidate
        raise KeyError(family_id)

    def pattern_for(self, rule_id: str) -> PatternSpec | None:
        """The pattern behind a persisted composite rule_id, or None.

        None is a normal outcome, not an error: the audit render reaches here with a
        rule_id from an OLD catalog version, and D-P2-21 handles that by version-gating
        the label rather than by guessing.
        """
        family_id, _, pattern_id = rule_id.partition(":")
        if not pattern_id:
            return None
        for candidate in self.families:
            if candidate.id != family_id:
                continue
            for pattern in candidate.patterns:
                if pattern.id == pattern_id:
                    return pattern
        return None

    def materialised_policy(self, policy: Policy) -> dict[str, str]:
        """family id -> severity for EVERY declared family (D-P2-2).

        The stored map may be empty or partial; the hashed map never is. A family the
        catalog no longer declares is dropped rather than carried, so deleting a family
        cannot leave a phantom entry deciding a verdict.
        """
        return {
            family.id: policy.families.get(family.id, family.default_policy)
            for family in self.families
        }


def bundled_rules_text() -> str:
    return (files("boardwatch.eligibility") / "rules.yaml").read_text(encoding="utf-8")


def load_rules(config_dir: Path) -> RulesCatalog:
    override = config_dir / "rules.yaml"
    if override.is_file():
        text, source, origin = override.read_text(encoding="utf-8"), "override", str(override)
    else:
        text, source, origin = bundled_rules_text(), "bundled", "bundled rules.yaml"
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise CatalogError(f"{origin}: invalid YAML: {exc}") from exc
    if not isinstance(document, dict):
        raise CatalogError(f"{origin}: the document must be a mapping")
    raw_families = document.get("families")
    if not isinstance(raw_families, list) or not raw_families:
        raise CatalogError(f"{origin}: 'families' must be a non-empty list")
    raw_cues = document.get("negation_cues")
    if not isinstance(raw_cues, list) or not raw_cues:
        raise CatalogError(f"{origin}: 'negation_cues' must be a non-empty list")
    for cue in raw_cues:
        # Same silent class as _consumed_cues (finding 59): an unquoted `no` is a YAML 1.1
        # boolean, so str(False) becomes the non-matching cue "False" and a negation is
        # never detected. Reject at load rather than let a negated requirement survive.
        if not isinstance(cue, str):
            raise CatalogError(
                f"{origin}: negation_cues entry {cue!r} loaded as {type(cue).__name__}, "
                "not a string. QUOTE it: unquoted no/yes/on/off/true/false are YAML booleans"
            )
    cues = tuple(raw_cues)
    idioms = _regex_list(document.get("negation_cue_idioms"), origin, "negation_cue_idioms")
    raw_career_fields = document.get("career_fields")
    if raw_career_fields is None:
        career_fields: frozenset[str] = frozenset()
    else:
        if not isinstance(raw_career_fields, list):
            raise CatalogError(f"{origin}: 'career_fields' must be a list")
        values: list[str] = []
        for entry in raw_career_fields:
            # Same silent class as negation_cues and _consumed_cues: an unquoted `no` is a
            # YAML 1.1 boolean, so str(False) would admit the career field "False", which no
            # user could ever type to match. A closed vocabulary rejects it instead.
            if not isinstance(entry, str):
                raise CatalogError(
                    f"{origin}: career_fields entry {entry!r} loaded as "
                    f"{type(entry).__name__}, not a string. QUOTE it: unquoted "
                    "no/yes/on/off/true/false are YAML booleans"
                )
            values.append(entry.strip())
        if any(v == "" for v in values):
            raise CatalogError(f"{origin}: 'career_fields' has a blank entry")
        if len(set(values)) != len(values):
            raise CatalogError(f"{origin}: 'career_fields' has a duplicate entry")
        career_fields = frozenset(values)

    families: list[FamilySpec] = []
    seen_families: set[str] = set()
    for raw in raw_families:
        if not isinstance(raw, dict):
            raise CatalogError(f"{origin}: family entries must be mappings: {raw!r}")
        family = _family(raw, origin, cues, idioms)
        if family.id in seen_families:
            raise CatalogError(f"{origin}: duplicate family id {family.id!r}")
        seen_families.add(family.id)
        families.append(family)
    catalog = RulesCatalog(
        families=tuple(families),
        negation_cues=cues,
        version=_version_of(document),
        source=source,
        career_fields=career_fields,
    )
    for family in catalog.families:
        if family.tier == "field" and not family.applies_to <= career_fields:
            outside = ", ".join(sorted(family.applies_to - career_fields))
            raise CatalogError(
                f"{origin}: family {family.id!r} applies_to values not in career_fields: {outside}"
            )
    _verify_families_are_wired(catalog, origin)
    return catalog


def _verify_families_are_wired(catalog: RulesCatalog, origin: str) -> None:
    """Every DECLARED family needs a resolver and a Facts field it can read.

    A custom override can declare a family whose fact is absent from Facts or that has no
    resolver; without this, the first command to touch it dies with a raw AttributeError,
    ValidationError or RegistryError depending on which ran first. This is the FORWARD
    direction only, deliberately not verify_registry's bidirectional check: a partial
    override that declares fewer families than the registry is legitimate (the dropped
    families simply are not evaluated), so requiring every REGISTERED resolver to be declared
    would reject it. The bundled catalog's completeness is the two-directional invariant that
    test_eligibility_resolve pins. Deferred imports avoid the resolve -> catalog cycle.
    """
    from boardwatch.eligibility.facts import Facts
    from boardwatch.eligibility.resolve import registry

    entries = registry()
    fields = Facts.model_fields
    for family in catalog.families:
        if family.id not in entries:
            raise CatalogError(f"{origin}: family {family.id!r} has no resolver")
        if family.fact not in fields:
            raise CatalogError(
                f"{origin}: family {family.id!r} declares fact {family.fact!r}, which is not "
                "a field on Facts"
            )


def _family(
    raw: dict[str, Any],
    origin: str,
    cues: tuple[str, ...],
    idioms: tuple[re.Pattern[str], ...],
) -> FamilySpec:
    family_id = str(raw.get("id", "")).strip()
    if not family_id:
        raise CatalogError(f"{origin}: a family entry is missing 'id'")
    where = f"{origin}: family {family_id!r}"
    fact = str(raw.get("fact", "")).strip()
    if not fact:
        raise CatalogError(f"{where} is missing 'fact'")
    answer_type = str(raw.get("answer_type", "")).strip()
    if not answer_type:
        raise CatalogError(f"{where} is missing 'answer_type'")
    if answer_type not in _ANSWER_TYPES:
        raise CatalogError(f"{where} has unknown answer_type {answer_type!r}")
    default_policy = str(raw.get("default_policy", "")).strip()
    if default_policy not in _POLICIES:
        raise CatalogError(f"{where} has unknown default_policy {default_policy!r}")
    question = str(raw.get("question", "")).strip()
    if not question:
        raise CatalogError(f"{where} is missing 'question'")
    label = str(raw.get("label", "")).strip()
    if not label:
        raise CatalogError(f"{where} is missing 'label'")

    tier = str(raw.get("tier", "")).strip()
    if not tier:
        raise CatalogError(f"{where} is missing 'tier'")
    if tier not in _TIERS:
        raise CatalogError(f"{where} has unknown tier {tier!r}")
    raw_applies_to = raw.get("applies_to")
    if tier == "field":
        if not isinstance(raw_applies_to, list) or not raw_applies_to:
            raise CatalogError(
                f"{where} is a field-tier family and must declare a non-empty 'applies_to'"
            )
        for entry in raw_applies_to:
            # An unquoted `no` is a YAML 1.1 boolean; str(False) would silently name the
            # career field "False", which is outside any closed career_fields vocabulary.
            if not isinstance(entry, str):
                raise CatalogError(
                    f"{where}: applies_to entry {entry!r} loaded as {type(entry).__name__}, "
                    "not a string. QUOTE it: unquoted no/yes/on/off/true/false are YAML "
                    "booleans"
                )
        applies_to = frozenset(entry.strip() for entry in raw_applies_to)
        if "" in applies_to:
            raise CatalogError(f"{where}: 'applies_to' has a blank entry")
    else:
        if raw_applies_to is not None:
            raise CatalogError(
                f"{where}: only a field-tier family may declare 'applies_to', not a {tier!r} one"
            )
        applies_to = frozenset()

    fields = _fields(raw.get("fields"), where, answer_type)
    vocabulary = raw.get("implies_vocabulary")
    if not isinstance(vocabulary, list) or not vocabulary:
        raise CatalogError(f"{where} must declare a non-empty 'implies_vocabulary'")
    declared = frozenset(str(value) for value in vocabulary)
    groups = _groups(raw.get("exclusive_groups"), where, declared)

    raw_patterns = raw.get("patterns")
    if not isinstance(raw_patterns, list) or not raw_patterns:
        raise CatalogError(f"{where} declares no patterns")
    patterns: list[PatternSpec] = []
    seen_patterns: set[str] = set()
    for raw_pattern in raw_patterns:
        if not isinstance(raw_pattern, dict):
            raise CatalogError(f"{where}: pattern entries must be mappings")
        pattern = _pattern(raw_pattern, family_id, where, declared, cues, idioms)
        if pattern.id in seen_patterns:
            raise CatalogError(f"{where}: duplicate pattern id {pattern.id!r}")
        seen_patterns.add(pattern.id)
        patterns.append(pattern)

    relations: list[dict[str, str]] = []
    for relation in raw.get("superset_relations") or []:
        if not isinstance(relation, dict):
            raise CatalogError(f"{where}: superset_relations entries must be mappings")
        relations.append({str(k): str(v) for k, v in relation.items()})

    return FamilySpec(
        id=family_id, label=label, fact=fact, answer_type=answer_type,
        default_policy=default_policy, question=question, fields=fields,
        implies_vocabulary=declared, exclusive_groups=groups, patterns=tuple(patterns),
        superset_relations=tuple(relations),
        tier=tier, applies_to=applies_to,
    )


def _fields(raw: object, where: str, answer_type: str) -> tuple[FieldSpec, ...]:
    """Every family declares 'fields', including the scalar ones.

    A uniform field list is what lets `init` dispatch over exactly two prompt call sites
    as families grow (D-P2-8), which is also what keeps R11's pin constant.
    """
    if not isinstance(raw, list) or not raw:
        raise CatalogError(f"{where} must declare a non-empty 'fields' list")
    fields: list[FieldSpec] = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise CatalogError(f"{where}: field entries must be mappings")
        name = str(entry.get("name", "")).strip()
        field_type = str(entry.get("type", "")).strip()
        if not name:
            raise CatalogError(f"{where}: a field is missing 'name'")
        if field_type not in _FIELD_TYPES:
            raise CatalogError(f"{where}: field {name!r} has unknown type {field_type!r}")
        choices = tuple(str(choice) for choice in (entry.get("choices") or ()))
        if field_type in ("choice", "choice_set") and not choices:
            raise CatalogError(f"{where}: field {name!r} declares no 'choices'")
        ranks = {str(k): int(v) for k, v in (entry.get("ranks") or {}).items()}
        for ranked in ranks:
            if ranked not in choices:
                raise CatalogError(
                    f"{where}: field {name!r} ranks a value that is not a choice: {ranked!r}"
                )
        fields.append(FieldSpec(name=name, type=field_type, choices=choices, ranks=ranks))
    if answer_type == "structured":
        if len(fields) < 2:
            raise CatalogError(f"{where}: a structured family needs at least two fields")
    elif len(fields) != 1 or fields[0].type != answer_type:
        raise CatalogError(
            f"{where}: a non-structured family needs exactly one field whose type equals "
            f"its answer_type {answer_type!r}"
        )
    return tuple(fields)


def _groups(
    raw: object, where: str, declared: frozenset[str]
) -> tuple[frozenset[str], ...]:
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        raise CatalogError(f"{where}: 'exclusive_groups' must be a list")
    groups: list[frozenset[str]] = []
    membership: dict[str, int] = {}
    for index, group in enumerate(raw):
        if not isinstance(group, list):
            raise CatalogError(f"{where}: exclusive_groups entries must be lists")
        members = [str(member) for member in group]
        if len(members) < 2:
            raise CatalogError(f"{where}: exclusive group {index} has fewer than 2 members")
        if len(set(members)) != len(members):
            raise CatalogError(f"{where}: exclusive group {index} repeats a member")
        for member in members:
            if member not in declared:
                raise CatalogError(
                    f"{where}: exclusive group member {member!r} is outside the family's "
                    "declared vocabulary"
                )
            if member in membership:
                raise CatalogError(
                    f"{where}: {member!r} appears in more than one group, which would make "
                    "the conflict rewrite order-dependent"
                )
            membership[member] = index
        groups.append(frozenset(members))
    return tuple(groups)


def _pattern(
    raw: dict[str, Any],
    family_id: str,
    where: str,
    declared: frozenset[str],
    cues: tuple[str, ...],
    idioms: tuple[re.Pattern[str], ...],
) -> PatternSpec:
    pattern_id = str(raw.get("id", "")).strip()
    if not pattern_id:
        raise CatalogError(f"{where}: a pattern is missing 'id'")
    requiredness = str(raw.get("requiredness", "")).strip()
    if requiredness not in _REQUIREDNESS:
        raise CatalogError(f"{where}: pattern {pattern_id!r} has unknown requiredness")
    implies = str(raw.get("implies", "")).strip()
    if implies not in declared:
        raise CatalogError(
            f"{where}: pattern {pattern_id!r} implies {implies!r}, outside the family's "
            "declared vocabulary"
        )
    scope = str(raw.get("scope", "")).strip()
    if scope not in _SCOPES:
        raise CatalogError(f"{where}: pattern {pattern_id!r} has unknown scope {scope!r}")
    requirement_text = str(raw.get("requirement_text", "")).strip()
    if not requirement_text:
        raise CatalogError(f"{where}: pattern {pattern_id!r} is missing 'requirement_text'")
    body = str(raw.get("pattern", ""))
    if not body:
        raise CatalogError(f"{where}: pattern {pattern_id!r} is missing 'pattern'")
    try:
        regex = re.compile(body, re.IGNORECASE)
    except re.error as exc:
        raise CatalogError(
            f"{where}: pattern {pattern_id!r} does not compile: {exc}"
        ) from exc
    at = f"{where}: pattern {pattern_id!r}"
    required_rank = raw.get("required_rank")
    return PatternSpec(
        id=pattern_id, family=family_id, requiredness=requiredness, implies=implies,
        scope=scope, regex=regex, requirement_text=requirement_text,
        jurisdiction=_optional_str(raw.get("jurisdiction")),
        required_scheme=_optional_str(raw.get("required_scheme")),
        required_level=_optional_str(raw.get("required_level")),
        required_accesses=tuple(str(a) for a in (raw.get("required_accesses") or ())),
        required_rank=None if required_rank is None else int(required_rank),
        suppressed_by=_regex_list(raw.get("suppressed_by"), at, "suppressed_by"),
        suppressed_by_unit=_regex_list(
            raw.get("suppressed_by_unit"), at, "suppressed_by_unit"
        ),
        suppressed_by_sentence=_regex_list(
            raw.get("suppressed_by_sentence"), at, "suppressed_by_sentence"
        ),
        subject_suppressors=_regex_list(
            raw.get("subject_suppressors"), at, "subject_suppressors"
        ),
        abstain_by=_regex_list(raw.get("abstain_by"), at, "abstain_by"),
        jurisdiction_map={
            str(k): str(v) for k, v in (raw.get("jurisdiction_map") or {}).items()
        },
        consumes_cues=_consumed_cues(raw.get("consumes_cues"), at, cues),
        cue_idioms=idioms,
    )


def _regex_list(raw: object, where: str, key: str) -> tuple[re.Pattern[str], ...]:
    """Compile a list of regexes, rejecting a bare string (prototype finding 31).

    A bare string is iterable, so `subject_suppressors: "our team"` silently compiled one
    regex per character, one of which was a space that matched every unit, and the family
    stopped producing rows with nothing raised. A list is the only accepted shape.
    """
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise CatalogError(
            f"{where}: {key} must be a list of patterns, got {type(raw).__name__}"
        )
    compiled: list[re.Pattern[str]] = []
    for entry in raw:
        try:
            compiled.append(re.compile(str(entry), re.IGNORECASE))
        except re.error as exc:
            raise CatalogError(
                f"{where}: {key} pattern {entry!r} does not compile: {exc}"
            ) from exc
    return tuple(compiled)


def _consumed_cues(
    raw: object, where: str, cues: tuple[str, ...]
) -> tuple[str, ...]:
    """Validate `consumes_cues` at LOAD time, because both failure modes are SILENT
    (prototype finding 59).

    Unquoted `no` is a YAML 1.1 boolean, so it arrives as False, str(False) is "False",
    and the `no` cue is never consumed; and an entry that is not a declared negation cue
    could never be consumed by anything, so a typo is a guard that does nothing. Both
    return a wrong `eligible` with zero rows and nothing raised, so both fail here.
    """
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise CatalogError(
            f"{where}: consumes_cues must be a list, got {type(raw).__name__}"
        )
    out: list[str] = []
    for entry in raw:
        if not isinstance(entry, str):
            raise CatalogError(
                f"{where}: consumes_cues entry {entry!r} loaded as {type(entry).__name__}, "
                "not a string. QUOTE it: unquoted no/yes/on/off/true/false are YAML booleans"
            )
        if entry not in cues:
            raise CatalogError(
                f"{where}: consumes_cues names {entry!r}, which is not a declared negation "
                "cue, so it could never be consumed"
            )
        out.append(entry)
    return tuple(out)


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def _version_of(document: object) -> str:
    """SHA-256 of the CANONICAL parsed document combined with CATALOG_REVISION.

    Same construction as extract/taxonomy.py:95-103. Formatting and mapping key order
    never matter; content does, including pattern order.
    """
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(
        f"{canonical}|catalog_revision={CATALOG_REVISION}".encode()
    ).hexdigest()
