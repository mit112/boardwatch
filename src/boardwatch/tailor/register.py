"""Deterministic register guard (P4 item 3a): a Tier-B rewrite carrying an AI-résumé
cliché from a closed, versioned blocklist, or clustering too many hype words into one
bullet, reads as bot-written even when every token is fact-provenanced and lift-free.
Guards *register*, distinct from `provenance.py` (facts) and `overmatch.py` (verbatim
lift/caps). Empty list == clean. Mirrors `equivalences.py`'s load+frozen-dataclass+
content-hash-`.version` shape. Pure: no I/O beyond the YAML load in `load_register()`.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from importlib.resources import files
from typing import Any

import yaml

REGISTER_VERSION = "p4-register-1"


class RegisterError(ValueError):
    """The bundled register table is missing, malformed, or fails an invariant."""


@dataclass(frozen=True)
class RegisterTable:
    banned_phrases: tuple[str, ...]
    buzzwords: tuple[str, ...]
    buzzword_density_ceiling: int
    # P4 item 3b: the qualification-register cue catalog (see register.yaml). Not used
    # standalone -- a hit is signal (b) of requirement_echo.py's AND-gate, never a veto
    # on its own.
    qualification_cues: tuple[str, ...]
    version: str


# The safe no-op default for callers that predate this check (mirrors item 1's
# `canonical: frozenset[str] = frozenset()` precedent): empty catalogs can never flag
# anything, so existing `run_tier_b_core` callers that do not pass `register` keep
# behaving exactly as before.
EMPTY_REGISTER = RegisterTable(
    banned_phrases=(),
    buzzwords=(),
    buzzword_density_ceiling=0,
    qualification_cues=(),
    version="empty",
)


def _parse_str_list(data: dict[str, Any], key: str) -> tuple[str, ...]:
    entries = data.get(key)
    if not isinstance(entries, list) or not entries:
        raise RegisterError(f"register.yaml: '{key}' must be a non-empty list")
    out: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, str) or not entry.strip():
            raise RegisterError(f"register.yaml: {key} entry {entry!r} must be a non-empty string")
        low = entry.lower()
        if low in seen:
            raise RegisterError(f"register.yaml: duplicate {key} entry {entry!r}")
        seen.add(low)
        out.append(entry)
    return tuple(out)


def load_register() -> RegisterTable:
    raw = (files("boardwatch.tailor") / "register.yaml").read_bytes()
    version = hashlib.sha256(raw).hexdigest()
    try:
        data = yaml.safe_load(raw.decode("utf-8"))
    except yaml.YAMLError as exc:
        raise RegisterError(f"register.yaml: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise RegisterError("register.yaml: top-level document must be a mapping")
    banned_phrases = _parse_str_list(data, "banned_phrases")
    buzzwords = _parse_str_list(data, "buzzwords")
    qualification_cues = _parse_str_list(data, "qualification_cues")
    ceiling = data.get("buzzword_density_ceiling")
    # No bool check omission: `isinstance(True, int)` is True in Python, and a stray
    # `buzzword_density_ceiling: true` would silently become ceiling=1.
    if not isinstance(ceiling, int) or isinstance(ceiling, bool) or ceiling < 0:
        raise RegisterError("register.yaml: 'buzzword_density_ceiling' must be a non-negative int")
    return RegisterTable(
        banned_phrases=banned_phrases,
        buzzwords=buzzwords,
        buzzword_density_ceiling=ceiling,
        qualification_cues=qualification_cues,
        version=version,
    )


def _phrase_pattern(phrase: str) -> re.Pattern[str]:
    # Word-boundary match so a phrase never matches as a substring of a longer word;
    # case-insensitive so "Team Player" and "TEAM PLAYER" are caught the same as
    # "team player".
    return re.compile(rf"(?<!\w){re.escape(phrase)}(?!\w)", re.IGNORECASE)


def banned_register_reasons(text: str, banned_phrases: tuple[str, ...]) -> list[str]:
    """Zero-tolerance: any hit from the closed blocklist vetoes the bullet."""
    return [
        f"banned phrase: '{phrase}'"
        for phrase in banned_phrases
        if _phrase_pattern(phrase).search(text)
    ]


def buzzword_density_reasons(text: str, buzzwords: tuple[str, ...], ceiling: int) -> list[str]:
    """Per-bullet ceiling: occasional hype is tolerated, clustering is not. Every
    occurrence counts (a repeated buzzword still stuffs the bullet), and the ceiling is
    inclusive -- a bullet AT the ceiling is clean, only exceeding it flags."""
    hits = [word for word in buzzwords for _ in _phrase_pattern(word).finditer(text)]
    if len(hits) > ceiling:
        return [f"buzzword density {len(hits)} exceeds ceiling {ceiling}: {', '.join(hits)}"]
    return []


def qualification_cue_reasons(text: str, cues: tuple[str, ...]) -> list[str]:
    """Any hit signals the bullet reads as a qualification/capability statement
    ("Experience with...", "Ability to...") rather than a completed-action
    accomplishment -- P4 item 3b's structural signal (b). Not a veto on its own: the
    caller (`requirement_echo.py`) AND-gates this against a corroboration signal before
    flagging anything."""
    return [f"qualification cue: '{cue}'" for cue in cues if _phrase_pattern(cue).search(text)]
