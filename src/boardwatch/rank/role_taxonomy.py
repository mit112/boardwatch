"""The user's role taxonomy: which titles are on target for THEIR field (P2 item 8, D-054).

Per-user DATA at `{config_dir}/role-taxonomy.yaml`, gathered at onboarding and never shipped
with content: boardwatch ships knowledge of one field only (software, the bundled classifier in
`role_gate`), and every other field's vocabulary is the user's own answer. There is no bundled
fallback file on purpose — a missing file is a missing profile field, so the role gate ABSTAINS
(`missing_profile_field:role_taxonomy`) instead of classifying a nurse against software titles.

Loaded ONCE per command, like `leveling`, and passed into the per-row loop. A malformed file is a
typed `RoleTaxonomyError` at load, never a silent default. The digest covers the PARSED document
(a comment edit does not move it, a semantic edit does) and enters the ranker's identity through
`reports.manifest.profile_row_hash`, the way `leveling`'s digest does.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROLE_TAXONOMY_FILE = "role-taxonomy.yaml"
ROLE_TAXONOMY_VERSION = 1
# The profile field the role gate names when it abstains.
MISSING_ROLE_TAXONOMY = "missing_profile_field:role_taxonomy"
# The fields boardwatch ships role knowledge for (D-054: tech only). `bundled: true` is valid for
# these and nothing else.
BUNDLED_FIELDS: frozenset[str] = frozenset({"software"})

_TOKEN = re.compile(r"[a-z0-9][a-z0-9_-]*")
_TOP_KEYS: frozenset[str] = frozenset(
    {"version", "field", "bundled", "role_families", "exclude_words"}
)
_FAMILY_KEYS: frozenset[str] = frozenset({"id", "title_words"})


class RoleTaxonomyError(ValueError):
    """A malformed role taxonomy, message naming the offending value."""


@dataclass(frozen=True)
class RoleFamily:
    id: str
    title_words: tuple[str, ...]
    pattern: re.Pattern[str]


@dataclass(frozen=True)
class RoleTaxonomy:
    field: str
    # True: classify with the shipped software gate. False: with `families`/`exclude`.
    bundled: bool
    families: tuple[RoleFamily, ...]
    exclude_words: tuple[str, ...]
    exclude: re.Pattern[str] | None
    digest: str


def _words_pattern(words: tuple[str, ...]) -> re.Pattern[str]:
    # Literal words, never regex: whitespace inside a phrase matches any run of whitespace.
    parts = (r"\s+".join(re.escape(part) for part in word.split()) for word in words)
    return re.compile(r"\b(?:" + "|".join(parts) + r")\b", re.IGNORECASE)


def role_token(value: object, where: str) -> str:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise RoleTaxonomyError(
            f"{ROLE_TAXONOMY_FILE}: {where} {value!r} must be a lowercase token "
            "(letters, digits, '_' or '-')"
        )
    return value


def _words(value: object, where: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise RoleTaxonomyError(f"{ROLE_TAXONOMY_FILE}: {where} must be a list of words")
    words: list[str] = []
    for entry in value:
        if not isinstance(entry, str) or not entry.strip():
            raise RoleTaxonomyError(
                f"{ROLE_TAXONOMY_FILE}: {where} entry {entry!r} must be a non-blank string"
            )
        word = " ".join(entry.split())
        if word.casefold() in (seen.casefold() for seen in words):
            raise RoleTaxonomyError(f"{ROLE_TAXONOMY_FILE}: {where} repeats {word!r}")
        words.append(word)
    return tuple(words)


def parse_role_taxonomy(raw: object) -> RoleTaxonomy:
    """Validate a parsed document. Every violation raises; nothing is defaulted."""
    if not isinstance(raw, dict):
        raise RoleTaxonomyError(f"{ROLE_TAXONOMY_FILE}: top level must be a mapping")
    unknown = sorted(str(key) for key in raw if key not in _TOP_KEYS)
    if unknown:
        raise RoleTaxonomyError(f"{ROLE_TAXONOMY_FILE}: unknown key(s) {unknown}")
    version = raw.get("version")
    if version != ROLE_TAXONOMY_VERSION or isinstance(version, bool):
        raise RoleTaxonomyError(
            f"{ROLE_TAXONOMY_FILE}: version {version!r} is not supported; "
            f"expected {ROLE_TAXONOMY_VERSION}"
        )
    field = role_token(raw.get("field"), "field")
    bundled = raw.get("bundled", False)
    if not isinstance(bundled, bool):
        raise RoleTaxonomyError(f"{ROLE_TAXONOMY_FILE}: bundled {bundled!r} must be true or false")
    has_own = "role_families" in raw or "exclude_words" in raw
    if bundled:
        if field not in BUNDLED_FIELDS:
            raise RoleTaxonomyError(
                f"{ROLE_TAXONOMY_FILE}: bundled is only available for "
                f"{', '.join(sorted(BUNDLED_FIELDS))}, not {field!r}"
            )
        if has_own:
            raise RoleTaxonomyError(
                f"{ROLE_TAXONOMY_FILE}: bundled: true cannot also declare role_families "
                "or exclude_words"
            )
    raw_families = raw.get("role_families")
    families: list[RoleFamily] = []
    if not bundled:
        if not isinstance(raw_families, list) or not raw_families:
            raise RoleTaxonomyError(
                f"{ROLE_TAXONOMY_FILE}: role_families must be a non-empty list "
                "(or set bundled: true for a bundled field)"
            )
        for entry in raw_families:
            if not isinstance(entry, dict):
                raise RoleTaxonomyError(
                    f"{ROLE_TAXONOMY_FILE}: role_families entry {entry!r} must be a mapping"
                )
            extra = sorted(str(key) for key in entry if key not in _FAMILY_KEYS)
            if extra:
                raise RoleTaxonomyError(
                    f"{ROLE_TAXONOMY_FILE}: role family has unknown key(s) {extra}"
                )
            family_id = role_token(entry.get("id"), "role family id")
            if any(family.id == family_id for family in families):
                raise RoleTaxonomyError(
                    f"{ROLE_TAXONOMY_FILE}: duplicate role family id {family_id!r}"
                )
            words = _words(entry.get("title_words"), f"role family {family_id!r} title_words")
            if not words:
                raise RoleTaxonomyError(
                    f"{ROLE_TAXONOMY_FILE}: role family {family_id!r} has no title_words"
                )
            families.append(RoleFamily(family_id, words, _words_pattern(words)))
    exclude_words = _words(raw.get("exclude_words", []), "exclude_words")
    canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(
        f"{canonical}|role_taxonomy_version={ROLE_TAXONOMY_VERSION}".encode()
    ).hexdigest()
    return RoleTaxonomy(
        field=field,
        bundled=bundled,
        families=tuple(families),
        exclude_words=exclude_words,
        exclude=_words_pattern(exclude_words) if exclude_words else None,
        digest=digest,
    )


def load_role_taxonomy(config_dir: Path) -> RoleTaxonomy | None:
    """The user's taxonomy, or `None` when they have none (the gate then abstains)."""
    path = config_dir / ROLE_TAXONOMY_FILE
    if not path.is_file():
        return None
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RoleTaxonomyError(f"{ROLE_TAXONOMY_FILE}: not valid YAML ({exc})") from exc
    return parse_role_taxonomy(raw)


def role_taxonomy_digest(taxonomy: RoleTaxonomy | None) -> str:
    """The identity component: `""` for no taxonomy, which no real digest can equal."""
    return taxonomy.digest if taxonomy is not None else ""


def write_role_taxonomy(config_dir: Path, document: dict[str, Any]) -> RoleTaxonomy:
    """Validate THEN write, so onboarding can never leave a file the ranker would refuse."""
    taxonomy = parse_role_taxonomy(document)
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / ROLE_TAXONOMY_FILE).write_text(
        yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    return taxonomy
