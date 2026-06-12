"""Taxonomy engine (§3.6, D21, D24).

The taxonomy ships as a bundled package resource; a user override at
{config_dir}/taxonomy.yaml wins when present (D24). taxonomy_version is
deterministic in installed wheels: SHA-256 of the CANONICAL effective YAML
(parsed, sorted, re-serialized — formatting never matters) combined with
EXTRACTOR_REVISION, an integer bumped whenever extraction *semantics* change.
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
from sqlalchemy import Connection
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from boardwatch.core.clock import utcnow
from boardwatch.store.tables import extractions

EXTRACTOR_REVISION = 1


class TaxonomyError(ValueError):
    pass


@dataclass(frozen=True)
class TaxonomyPattern:
    name: str
    category: str
    pattern: str
    case_sensitive: bool
    regex: re.Pattern[str]


@dataclass(frozen=True)
class Taxonomy:
    patterns: tuple[TaxonomyPattern, ...]
    version: str
    source: str  # "override" | "bundled"

    def extract(self, text: str) -> set[str]:
        return {p.name for p in self.patterns if p.regex.search(text)}

    def categories(self) -> dict[str, str]:
        return {p.name: p.category for p in self.patterns}


def bundled_taxonomy_text() -> str:
    return (files("boardwatch.extract") / "taxonomy.yaml").read_text(encoding="utf-8")


def load_taxonomy(config_dir: Path) -> Taxonomy:
    override = config_dir / "taxonomy.yaml"
    if override.is_file():
        text, source, origin = override.read_text(encoding="utf-8"), "override", str(override)
    else:
        text, source, origin = bundled_taxonomy_text(), "bundled", "bundled taxonomy.yaml"
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise TaxonomyError(f"{origin}: invalid YAML: {exc}") from exc
    entries = (data or {}).get("patterns") if isinstance(data, dict) else None
    if not isinstance(entries, list) or not entries:
        raise TaxonomyError(f"{origin}: 'patterns' must be a non-empty list")
    patterns: list[TaxonomyPattern] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise TaxonomyError(f"{origin}: pattern entries must be mappings: {entry!r}")
        name = str(entry.get("name", "")).strip()
        category = str(entry.get("category", "")).strip()
        pattern = str(entry.get("pattern", ""))
        case_sensitive = bool(entry.get("case_sensitive", False))
        if not name or not category or not pattern:
            raise TaxonomyError(f"{origin}: entry missing name/category/pattern: {entry!r}")
        if name in seen:
            raise TaxonomyError(f"{origin}: duplicate pattern name {name!r}")
        seen.add(name)
        try:
            regex = re.compile(pattern, 0 if case_sensitive else re.IGNORECASE)
        except re.error as exc:
            raise TaxonomyError(f"{origin}: pattern {name!r} does not compile: {exc}") from exc
        patterns.append(TaxonomyPattern(name, category, pattern, case_sensitive, regex))
    return Taxonomy(patterns=tuple(patterns), version=_version_of(data), source=source)


def _version_of(document: Any) -> str:
    """D24: SHA-256 of the CANONICAL effective YAML — the full parsed document
    re-serialized as sorted-key compact JSON. Formatting and mapping key order
    never matter; content does, including top-level keys and pattern-list
    order (reordering patterns changes the version, triggering a harmless
    backfill)."""
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"))
    raw = f"{canonical}|extractor_revision={EXTRACTOR_REVISION}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def write_extraction(
    conn: Connection,
    taxonomy: Taxonomy,
    posting_id: int,
    body_content_hash: str,
    body_text: str,
) -> bool:
    """Insert one extraction row keyed (posting_id, content_hash, 'taxonomy', version).

    Idempotent under the UNIQUE constraint: returns False when the row already
    exists. The payload is recomputed only on a real insert path's behalf —
    callers batch over postings missing a row at the current version (D21).
    """
    hits = sorted(taxonomy.extract(body_text))
    categories = taxonomy.categories()
    payload: dict[str, Any] = {
        "skills": hits,
        "categories": {name: categories[name] for name in hits},
    }
    stmt = (
        sqlite_insert(extractions)
        .values(
            posting_id=posting_id,
            content_hash=body_content_hash,
            kind="taxonomy",
            engine_version=taxonomy.version,
            json=payload,
            created_at=utcnow(),
        )
        .on_conflict_do_nothing(
            index_elements=[
                extractions.c.posting_id,
                extractions.c.content_hash,
                extractions.c.kind,
                extractions.c.engine_version,
            ]
        )
    )
    return conn.execute(stmt).rowcount > 0
