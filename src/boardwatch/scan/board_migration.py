"""Cross-provider migration detection.

When a watched board goes DEAD/ERROR/EMPTY, the company has often not stopped hiring — it moved
its board to a different ATS (observed live: veeva workday->lever, purestorage workday->greenhouse,
plaid lever->ashby, vercel ashby->greenhouse). A static watch cannot follow that move, so it sits
at zero forever. This module probes the OTHER simple-slug providers for the same company handle and,
if one answers OK, proposes the migration. It suggests only; a human re-points the watch (the same
human-in-the-loop rule `companies discover`/`import` already follow).

Pure and network-free: `suggest_migrations` takes an injected `probe`, so the same logic serves
`doctor`'s live probe and a unit test. It imports no store and no fetcher."""

from __future__ import annotations

from collections.abc import Callable, Container, Iterable
from dataclasses import dataclass

from boardwatch.providers.base import BoardHealth

# The health states that warrant a migration check. UNREACHABLE is excluded: it is a transient
# transport failure, not evidence a board moved. OK needs no check.
MIGRATION_TRIGGER = frozenset(
    {BoardHealth.DEAD, BoardHealth.ERROR, BoardHealth.EMPTY}
)

# Providers whose slug IS the bare company handle, so a company can be probed on them by name.
# workday is excluded as a TARGET: its slug is host/tenant/site and cannot be built from a handle
# alone. smartrecruiters is excluded because it returns EMPTY (not an error) for an unknown slug,
# so a coincidental same-handle hit could not be told from a real board — it would manufacture
# false OK suggestions. In target order: the order a single suggestion is chosen in.
_MIGRATION_TARGETS: tuple[str, ...] = ("greenhouse", "lever", "ashby", "workable")

Probe = Callable[[list[tuple[str, str]]], dict[tuple[str, str], BoardHealth]]


@dataclass(frozen=True)
class MigrationSuggestion:
    """A watched board that is unhealthy while the same company is live on `new_provider`."""

    old_provider: str
    old_slug: str
    new_provider: str
    new_slug: str


def company_key(provider: str, slug: str) -> str:
    """The company handle used to probe OTHER providers.

    A workday slug is `host/tenant/site`; the tenant (segment 1) is the handle the other providers
    key on (veeva.wd5.myworkdayjobs.com/veeva/veeva_external -> `veeva`). For the simple-slug
    providers the slug already IS the handle.
    """
    if provider == "workday":
        parts = slug.split("/")
        return parts[1] if len(parts) >= 2 else slug
    return slug


def migration_candidates(provider: str, slug: str) -> list[tuple[str, str]]:
    """The `(other_provider, handle)` pairs to probe for a possible migration of this board."""
    key = company_key(provider, slug)
    return [(p, key) for p in _MIGRATION_TARGETS if p != provider]


def suggest_migrations(
    unhealthy: Iterable[tuple[str, str]],
    probe: Probe,
    *,
    skip: Container[tuple[str, str]] = frozenset(),
) -> list[MigrationSuggestion]:
    """Propose a migration for each unhealthy `(provider, slug)` whose company answers OK elsewhere.

    `probe` is injected (testable without a network) and is called ONCE with the de-duplicated set
    of all candidate targets, so two dead boards for the same company do not probe it twice. `skip`
    holds `(provider, handle)` pairs already watched: a company still covered elsewhere is not a
    migration and must not be re-suggested. A candidate counts only if its probe is OK — an EMPTY or
    DEAD candidate is not a live board. When several answer OK, the first in target order is chosen.
    """
    boards = list(unhealthy)
    per_board: list[tuple[tuple[str, str], list[tuple[str, str]]]] = []
    targets: dict[tuple[str, str], None] = {}
    for prov, slug in boards:
        cands = [c for c in migration_candidates(prov, slug) if c not in skip]
        per_board.append(((prov, slug), cands))
        for cand in cands:
            targets[cand] = None
    if not targets:
        return []
    results = probe(list(targets))
    suggestions: list[MigrationSuggestion] = []
    for (prov, slug), cands in per_board:
        for cand in cands:
            if results.get(cand) is BoardHealth.OK:
                suggestions.append(MigrationSuggestion(prov, slug, cand[0], cand[1]))
                break  # first OK in target order is enough; a human reviews the suggestion
    return suggestions
