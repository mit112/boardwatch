"""Repo-side registry health (§3.2/§6.2). Probes every catalog entry's
healthcheck with politeness defaults and reports per-entry status. NO database:
catalog maintenance is repo-side (§1.2-4), local health is doctor's (#24)."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from boardwatch.core.politeness import Fetcher
from boardwatch.core.settings import load_settings
from boardwatch.providers.ashby import AshbyProvider
from boardwatch.providers.base import BoardHealth, Provider
from boardwatch.providers.greenhouse import GreenhouseProvider
from boardwatch.providers.lever import LeverProvider
from boardwatch.registry.loader import load_catalog

# Provider map built HERE from the store-free provider classes (providers/* import only
# core/, never store/). We deliberately do NOT reuse scan.coordinator.default_providers:
# coordinator imports scan.apply → store.*, which would drag the DB into this repo-side,
# no-user-DB workflow entry point (Codex round-1 plan finding, verified transitive import).
_FAILURES = {BoardHealth.DEAD, BoardHealth.ERROR, BoardHealth.UNREACHABLE}


def _providers() -> dict[str, Provider]:
    return {"greenhouse": GreenhouseProvider(), "lever": LeverProvider(), "ashby": AshbyProvider()}


@dataclass(frozen=True)
class HealthRow:
    name: str
    provider: str
    slug: str
    status: BoardHealth


def check_catalog(probe: Callable[[str, str], BoardHealth] | None = None) -> list[HealthRow]:
    entries = load_catalog()
    if probe is None:
        fetcher = Fetcher(load_settings())  # one shared politeness-paced Fetcher across the run
        providers = _providers()

        def probe(provider: str, slug: str) -> BoardHealth:
            return providers[provider].healthcheck(fetcher, slug)

    return [HealthRow(e.name, e.provider, e.slug, probe(e.provider, e.slug)) for e in entries]


def has_failures(statuses: Iterable[BoardHealth]) -> bool:
    return any(s in _FAILURES for s in statuses)


def _render_summary(rows: list[HealthRow]) -> str:
    lines = ["| entry | provider | status |", "|---|---|---|"]
    lines += [f"| {r.name} | {r.provider} | {r.status.value} |" for r in rows]
    return "\n".join(lines)


def main() -> int:
    """Entrypoint: probe the catalog, write a Markdown table to GITHUB_STEP_SUMMARY (or stdout),
    and return a non-zero code iff any entry is DEAD/ERROR/UNREACHABLE (EMPTY does not fail)."""
    rows = check_catalog()
    summary = _render_summary(rows)
    out = os.environ.get("GITHUB_STEP_SUMMARY")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(summary + "\n")
    else:
        print(summary)
    return 1 if has_failures(r.status for r in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
