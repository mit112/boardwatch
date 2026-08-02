from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from importlib.resources import files
from typing import Any

import yaml


class EquivalenceError(ValueError):
    """The bundled equivalence table is missing, malformed, or fails an invariant."""


@dataclass(frozen=True)
class EquivalencePair:
    from_phrase: str
    to_phrase: str


@dataclass(frozen=True)
class EquivalenceTable:
    pairs: tuple[EquivalencePair, ...]
    version: str

    def as_pairs(self) -> tuple[EquivalencePair, ...]:
        return self.pairs

    def images(self) -> frozenset[str]:
        return frozenset(p.to_phrase for p in self.pairs)


_TOKEN = re.compile(r"^\w+$")


def _parse_pairs(data: dict[str, Any]) -> tuple[EquivalencePair, ...]:
    entries = data.get("pairs")
    if not isinstance(entries, list) or not entries:
        raise EquivalenceError("equivalences.yaml: 'pairs' must be a non-empty list")
    pairs: list[EquivalencePair] = []
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        if not isinstance(entry, dict) or "from" not in entry or "to" not in entry:
            raise EquivalenceError(f"bad pair: {entry!r}")
        frm = str(entry["from"])
        to = str(entry["to"])
        if not (_TOKEN.match(frm) and _TOKEN.match(to)):
            raise EquivalenceError(f"pair {frm!r}->{to!r} must be single \\w tokens")
        if (frm, to) in seen:
            raise EquivalenceError(f"duplicate pair {frm!r}->{to!r}")
        seen.add((frm, to))
        pairs.append(EquivalencePair(frm, to))
    return tuple(pairs)


def load_equivalences() -> EquivalenceTable:
    raw = (files("boardwatch.tailor") / "equivalences.yaml").read_bytes()
    version = hashlib.sha256(raw).hexdigest()
    try:
        data = yaml.safe_load(raw.decode("utf-8"))
    except yaml.YAMLError as exc:
        raise EquivalenceError(f"equivalences.yaml: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise EquivalenceError("equivalences.yaml: top-level document must be a mapping")
    pairs = _parse_pairs(data)
    return EquivalenceTable(pairs=pairs, version=version)
