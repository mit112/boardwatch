"""Bundled-catalog loader (§3.2). Distinct from DB watches — health lives in
the DB / workflow, never in this YAML."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from boardwatch.registry.validate import CatalogError, CompanyEntry, validate_entries

_BUNDLED = Path(__file__).resolve().parent / "companies.yaml"


def load_catalog_raw(path: Path | None = None) -> list[CompanyEntry]:
    """Parse + schema-validate every entry, WITHOUT the cross-entry duplicate check."""
    raw = yaml.safe_load((path or _BUNDLED).read_text(encoding="utf-8")) or {}
    rows = raw.get("companies") or []
    entries: list[CompanyEntry] = []
    for i, row in enumerate(rows):
        try:
            entries.append(CompanyEntry.model_validate(row))
        except ValidationError as exc:
            ident = (row or {}).get("slug", f"index {i}") if isinstance(row, dict) else f"index {i}"
            msg = exc.errors()[0]["msg"]
            raise CatalogError(f"invalid registry entry {ident!r}: {msg}") from exc
    return entries


def load_catalog(path: Path | None = None) -> list[CompanyEntry]:
    """Parse, schema-validate, AND reject duplicate (provider, slug) pairs."""
    return validate_entries(load_catalog_raw(path))


def starter_entries(entries: list[CompanyEntry]) -> list[CompanyEntry]:
    return [e for e in entries if "starter" in e.tags]
