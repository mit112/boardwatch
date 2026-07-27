"""Catalog schema + integrity validation (§6.2). No DB, no network. The set of
valid providers is sourced from the provider registry (single source of truth),
so adding a provider needs no change here."""

from __future__ import annotations

from collections import Counter

from pydantic import BaseModel, ConfigDict, field_validator

from boardwatch.providers.registry import PROVIDER_NAMES


class CatalogError(ValueError):
    """A schema or integrity error, message naming the offending entry."""


class CompanyEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")  # no fields beyond these (issue #19)

    name: str
    provider: str
    slug: str
    tags: list[str] = []

    @field_validator("provider")
    @classmethod
    def _known_provider(cls, value: str) -> str:
        if value not in PROVIDER_NAMES:
            known = ", ".join(sorted(PROVIDER_NAMES))
            raise ValueError(f"unknown provider {value!r}; known: {known}")
        return value


def validate_entries(entries: list[CompanyEntry]) -> list[CompanyEntry]:
    counts = Counter(f"{e.provider}:{e.slug}" for e in entries)
    dupes = sorted(key for key, n in counts.items() if n > 1)
    if dupes:
        raise CatalogError(f"duplicate registry entries (provider:slug): {', '.join(dupes)}")
    return entries
