"""Provider registry: the single source of truth for provider identity.

Enumerates the provider classes (which import only core/, never store/) and derives
every provider-set view the rest of the codebase needs. The allowed-name set (catalog
validation) and the public paste-host map (board-URL parsing) come from the classes'
declared identity (name + board_hosts) WITHOUT instantiating them; the runtime
name->instance map (scan coordinator, health report) is built on demand at call time.
Adding a provider's IDENTITY = write its class (with name + board_hosts) + append it to
PROVIDER_CLASSES; providers with a novel fetch shape (e.g. multi-endpoint summary+detail)
may additionally need request/snapshot/coordinator changes.

This module must never import boardwatch.store.*; it feeds store-free entry points
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


def _provider_identity() -> tuple[frozenset[str], dict[str, str]]:
    """Provider names + public paste-host->name map, read from class attributes only.

    No provider is instantiated here (P0-3 D-P0-3-4), so identity derivation stays
    config-free and does not break when a provider later needs constructor arguments.
    Fails fast on a duplicate provider name or a paste host claimed by two providers.
    """
    names: set[str] = set()
    hosts: dict[str, str] = {}
    for cls in PROVIDER_CLASSES:
        name = cls.name
        if name in names:
            raise ValueError(f"duplicate provider name {name!r} in PROVIDER_CLASSES")
        names.add(name)
        for host in cls.board_hosts:
            if host in hosts:
                raise ValueError(
                    f"duplicate board host {host!r}: claimed by both "
                    f"{hosts[host]!r} and {name!r}"
                )
            hosts[host] = name
    return frozenset(names), hosts


PROVIDER_NAMES: frozenset[str] = _provider_identity()[0]


def host_provider_map() -> dict[str, str]:
    """Public paste-hostname -> provider name, from each provider's board_hosts."""
    return _provider_identity()[1]


def build_providers() -> dict[str, Provider]:
    """Fresh provider instances keyed by name (one per registered class). Call-time only."""
    providers: dict[str, Provider] = {}
    for cls in PROVIDER_CLASSES:
        inst = cls()
        name = inst.name
        if name in providers:
            raise ValueError(f"duplicate provider name {name!r} in PROVIDER_CLASSES")
        providers[name] = inst
    return providers
