"""Provider registry — the single source of truth for provider identity.

Enumerates the provider classes (which import only core/, never store/) and derives
every provider-set view the rest of the codebase needs: the runtime name->instance
map (scan coordinator, health report), the allowed-name set (catalog validation),
and the public paste-host map (board-URL parsing). Adding a provider's IDENTITY =
write its class (with name + board_hosts) + append it to PROVIDER_CLASSES; providers
with a novel fetch shape (e.g. multi-endpoint summary+detail) may additionally need
request/snapshot/coordinator changes.

This module must never import boardwatch.store.* — it feeds store-free entry points
(registry.health_report, core.board_urls); a subprocess guard in the tests enforces it.
"""

from __future__ import annotations

from boardwatch.providers.ashby import AshbyProvider
from boardwatch.providers.base import Provider
from boardwatch.providers.greenhouse import GreenhouseProvider
from boardwatch.providers.lever import LeverProvider

# Type intentionally left inferred (concrete class types). Annotating this as
# tuple[type[Provider], ...] would make `cls()` below a mypy error under --strict
# ("cannot instantiate protocol class"). Consumers only iterate and instantiate these.
PROVIDER_CLASSES = (GreenhouseProvider, LeverProvider, AshbyProvider)


def build_providers() -> dict[str, Provider]:
    """Fresh provider instances keyed by name (one per registered class)."""
    providers: dict[str, Provider] = {}
    for cls in PROVIDER_CLASSES:
        inst = cls()
        name = inst.name
        if name in providers:
            raise ValueError(f"duplicate provider name {name!r} in PROVIDER_CLASSES")
        providers[name] = inst
    return providers


PROVIDER_NAMES: frozenset[str] = frozenset(build_providers())


def host_provider_map() -> dict[str, str]:
    """Public paste-hostname -> provider name, from each provider's board_hosts."""
    hosts: dict[str, str] = {}
    for cls in PROVIDER_CLASSES:
        inst = cls()
        for host in inst.board_hosts:
            if host in hosts:
                raise ValueError(
                    f"duplicate board host {host!r}: claimed by both "
                    f"{hosts[host]!r} and {inst.name!r}"
                )
            hosts[host] = inst.name
    return hosts
