"""Seniority leveling catalog (D-246).

Structurally mirrors `eligibility/catalog.py` and `extract/taxonomy.py`: a bundled YAML with a
`{config_dir}` override that wins, closed vocabularies that raise rather than bucket, and a
content digest so a run's manifest can name the catalog it ran under.

The catalog is UNCACHED on purpose, for the same reason its two siblings are: an override may
appear between calls. Callers load it ONCE per rank and pass the result into the loop —
`role_verdict` is tuned to 0.30s over 19,262 postings, so a per-row load is a real regression.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Literal

import yaml

LEVELING_VERSION = 1

SeniorityBand = Literal["entry", "mid", "senior", "staff_plus"]

_BANDS: frozenset[str] = frozenset({"entry", "mid", "senior", "staff_plus"})
_GRAMMAR_KINDS: frozenset[str] = frozenset({"self_describing", "ambiguous"})
# Closed vocabulary of grammar NAMES. `seniority_gate` owns the matching regex for each
# and asserts at import that it covers exactly this set, so the catalog can never declare
# a grammar nothing can match -- which would be declared data that silently does nothing.
KNOWN_GRAMMARS: frozenset[str] = frozenset(
    {"level_n", "l_prefix", "e_prefix", "ic_prefix", "t_prefix"}
)
# YAML 1.1 turns these into bools when unquoted, which would silently become a token.
_YAML_BOOLISH = "unquoted no/yes/on/off/true/false are YAML booleans"


class LevelingError(ValueError):
    """A schema or vocabulary error, message naming the offending value."""


@dataclass(frozen=True)
class LevelScheme:
    name: str
    grammar: str
    levels: Mapping[str, SeniorityBand]


@dataclass(frozen=True)
class FieldTier:
    words: Mapping[str, SeniorityBand]
    roman: Mapping[str, SeniorityBand]


@dataclass(frozen=True)
class LevelingCatalog:
    version: int
    ambiguous_grammars: frozenset[str]
    self_describing_grammars: frozenset[str]
    schemes: Mapping[str, LevelScheme]
    fields: Mapping[str, FieldTier]
    digest: str


def _text(config_dir: Path) -> str:
    override = config_dir / "leveling.yaml"
    if override.is_file():
        return override.read_text(encoding="utf-8")
    return (files("boardwatch.rank") / "leveling.yaml").read_text(encoding="utf-8")


def _band(value: object, where: str) -> SeniorityBand:
    if not isinstance(value, str):
        raise LevelingError(f"{where}: band {value!r} is {type(value).__name__}, not a string. "
                            f"QUOTE it: {_YAML_BOOLISH}")
    if value not in _BANDS:
        raise LevelingError(f"{where}: unknown band {value!r}; known: {', '.join(sorted(_BANDS))}")
    return value  # type: ignore[return-value]


def _key(value: object, where: str) -> str:
    if not isinstance(value, str):
        raise LevelingError(f"{where}: key {value!r} is {type(value).__name__}, not a string. "
                            f"QUOTE it: {_YAML_BOOLISH}")
    return value


def load_leveling(config_dir: Path) -> LevelingCatalog:
    raw = yaml.safe_load(_text(config_dir)) or {}
    if not isinstance(raw, dict):
        raise LevelingError("leveling.yaml: top level must be a mapping")

    version = raw.get("leveling_version")
    if version != LEVELING_VERSION:
        raise LevelingError(
            f"leveling.yaml: leveling_version {version!r} disagrees with the builtin "
            f"{LEVELING_VERSION}"
        )

    ambiguous: set[str] = set()
    self_describing: set[str] = set()
    for name, body in (raw.get("grammars") or {}).items():
        gname = _key(name, "grammars")
        if gname not in KNOWN_GRAMMARS:
            raise LevelingError(
                f"grammar {gname!r} is not a known grammar; known: "
                f"{', '.join(sorted(KNOWN_GRAMMARS))}"
            )
        kind = (body or {}).get("kind")
        if kind not in _GRAMMAR_KINDS:
            raise LevelingError(f"grammar {gname!r}: unknown kind {kind!r}")
        (ambiguous if kind == "ambiguous" else self_describing).add(gname)

    schemes: dict[str, LevelScheme] = {}
    for name, body in (raw.get("schemes") or {}).items():
        sname = _key(name, "schemes")
        grammar = (body or {}).get("grammar")
        if grammar not in self_describing:
            raise LevelingError(
                f"scheme {sname!r}: grammar {grammar!r} is not a self-describing grammar; "
                f"known: {', '.join(sorted(self_describing))}"
            )
        levels = {
            _key(k, f"scheme {sname!r}"): _band(v, f"scheme {sname!r} level {k!r}")
            for k, v in ((body or {}).get("levels") or {}).items()
        }
        schemes[sname] = LevelScheme(name=sname, grammar=grammar, levels=levels)

    fields: dict[str, FieldTier] = {}
    for name, body in (raw.get("fields") or {}).items():
        fname = _key(name, "fields")
        words = {
            _key(k, f"field {fname!r} words").casefold(): _band(v, f"field {fname!r} word {k!r}")
            for k, v in ((body or {}).get("words") or {}).items()
        }
        roman = {
            _key(k, f"field {fname!r} roman").upper(): _band(v, f"field {fname!r} roman {k!r}")
            for k, v in ((body or {}).get("roman") or {}).items()
        }
        fields[fname] = FieldTier(words=words, roman=roman)

    # Hash the PARSED document, not the file: the consumer reads the parsed object, so a
    # digest over raw bytes would move on a comment edit and miss a semantic one via override.
    canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(
        f"{canonical}|leveling_version={LEVELING_VERSION}".encode()
    ).hexdigest()

    return LevelingCatalog(
        version=LEVELING_VERSION,
        ambiguous_grammars=frozenset(ambiguous),
        self_describing_grammars=frozenset(self_describing),
        schemes=schemes,
        fields=fields,
        digest=digest,
    )


def load_bindings(config_dir: Path) -> dict[tuple[str, str], str]:
    """Company -> scheme, keyed on (provider, slug) — the pair the store and registry agree on.

    User config, never shipped: which companies you watch is yours. Absent file => no bindings
    => every level token abstains and is reported, which is the honest default.
    """
    path = config_dir / "leveling-bindings.yaml"
    if not path.is_file():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: dict[tuple[str, str], str] = {}
    for row in raw.get("bindings") or []:
        provider, slug, scheme = row.get("provider"), row.get("slug"), row.get("scheme")
        for label, value in (("provider", provider), ("slug", slug), ("scheme", scheme)):
            if not isinstance(value, str) or not value:
                raise LevelingError(f"leveling-bindings.yaml: {label} must be a non-empty string")
        out[(provider, slug)] = scheme
    return out
