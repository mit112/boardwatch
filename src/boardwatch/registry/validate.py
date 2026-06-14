"""Catalog schema + integrity validation (§6.2). Pure: YAML + Pydantic only,
no DB, no network — a leaf module."""

from __future__ import annotations

from collections import Counter
from typing import Literal

from pydantic import BaseModel, ConfigDict

Provider = Literal["greenhouse", "lever", "ashby"]


class CatalogError(ValueError):
    """A schema or integrity error, message naming the offending entry."""


class CompanyEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")  # no fields beyond these (issue #19)

    name: str
    provider: Provider
    slug: str
    tags: list[str] = []


def validate_entries(entries: list[CompanyEntry]) -> list[CompanyEntry]:
    counts = Counter(f"{e.provider}:{e.slug}" for e in entries)
    dupes = sorted(key for key, n in counts.items() if n > 1)
    if dupes:
        raise CatalogError(f"duplicate registry entries (provider:slug): {', '.join(dupes)}")
    return entries
