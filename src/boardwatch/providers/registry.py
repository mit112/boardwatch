"""Provider registry: the single source of truth for provider identity.

Enumerates the provider classes (which import only core/, never store/) and derives
every provider-set view the rest of the codebase needs. The allowed-name set (catalog
validation) and the public paste-host map (board-URL parsing) come from the classes'
declared identity (name + board_hosts) WITHOUT instantiating them; the runtime
name->instance map (scan coordinator, health report) is built on demand at call time.
Adding a provider's IDENTITY = write its class (with name + board_hosts, or
board_host_suffixes when its hostnames are unbounded) + append it to PROVIDER_CLASSES;
providers with a novel fetch shape (e.g. multi-endpoint summary+detail) may additionally
need request/snapshot/coordinator changes.

This module must never import boardwatch.store.*; it feeds store-free entry points
(registry.health_report, core.board_urls); a subprocess guard in the tests enforces it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from boardwatch.providers.ashby import AshbyProvider
from boardwatch.providers.base import Provider
from boardwatch.providers.greenhouse import GreenhouseProvider
from boardwatch.providers.lever import LeverProvider
from boardwatch.providers.smartrecruiters import SmartRecruitersProvider
from boardwatch.providers.workable import WorkableProvider

# Type intentionally left inferred (concrete class types). Annotating this as
# tuple[type[Provider], ...] would make `cls()` below a mypy error under --strict
# ("cannot instantiate protocol class"). Consumers only iterate and instantiate these.
PROVIDER_CLASSES = (
    GreenhouseProvider, LeverProvider, AshbyProvider, WorkableProvider, SmartRecruitersProvider,
)


def _host_keys(cls: Any) -> tuple[str, ...]:
    """Every key a HOST-KEYED map must register for this provider: its exact paste hosts
    PLUS its host suffixes. Workday's hosts are unbounded ({tenant}.wd{N}.myworkdayjobs.com)
    so it declares board_hosts = () and the SUFFIX is the map key. Iterating board_hosts
    alone would silently register no extractor and no help text for such a provider, and
    every pasted URL would fall through to UnknownBoardURL."""
    suffixes = cast(tuple[str, ...], getattr(cls, "board_host_suffixes", ()))
    return tuple(cls.board_hosts) + suffixes


def _provider_identity() -> tuple[frozenset[str], dict[str, str], dict[str, str]]:
    """Provider names + public paste-host->name map + host-suffix->name map, read from
    class attributes only.

    No provider is instantiated here (P0-3 D-P0-3-4), so identity derivation stays
    config-free and does not break when a provider later needs constructor arguments.
    Fails fast on a duplicate provider name, a paste host claimed by two providers, or a
    host suffix claimed by two providers.
    """
    names: set[str] = set()
    hosts: dict[str, str] = {}
    suffixes: dict[str, str] = {}
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
        for suffix in cast(tuple[str, ...], getattr(cls, "board_host_suffixes", ())):
            if suffix in suffixes:
                raise ValueError(
                    f"duplicate board host suffix {suffix!r}: claimed by both "
                    f"{suffixes[suffix]!r} and {name!r}"
                )
            suffixes[suffix] = name
    return frozenset(names), hosts, suffixes


PROVIDER_NAMES: frozenset[str] = _provider_identity()[0]


def host_provider_map() -> dict[str, str]:
    """Public paste-hostname -> provider name, from each provider's board_hosts."""
    return _provider_identity()[1]


def host_suffix_provider_map() -> dict[str, str]:
    """Public host SUFFIX -> provider name, from each provider's board_host_suffixes.
    Matched only after an exact host lookup misses (see board_urls._match_host)."""
    return _provider_identity()[2]


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


SlugExtractor = Callable[[str, list[str]], str | None]
SlugNormalizer = Callable[[str], str]


def slug_extractor_map() -> dict[str, SlugExtractor]:
    """Host -> optional slug extractor, for providers whose paste host serves more
    than one URL shape. Providers opt in with a `slug_from_path` staticmethod; hosts
    with no extractor keep board_urls' default (first path segment)."""
    extractors: dict[str, SlugExtractor] = {}
    for cls in PROVIDER_CLASSES:
        fn = getattr(cls, "slug_from_path", None)
        if fn is None:
            continue
        for host in _host_keys(cls):
            extractors[host] = cast(SlugExtractor, fn)
    return extractors


def slug_normalizer_map() -> dict[str, SlugNormalizer]:
    """Provider name -> optional slug normalizer, applied to BOTH the provider:slug
    and pasted-URL forms so a case-insensitive provider canonicalizes identically
    regardless of how the board was named."""
    normalizers: dict[str, SlugNormalizer] = {}
    for cls in PROVIDER_CLASSES:
        fn = getattr(cls, "normalize_slug", None)
        if fn is not None:
            normalizers[cls.name] = cast(SlugNormalizer, fn)
    return normalizers


def slug_help_map() -> dict[str, str]:
    """Host -> actionable guidance shown when the host matches but no slug is
    extractable (e.g. a Workable shortlink). Plain class-attribute string, so no
    provider needs to import board_urls (which would create an import cycle)."""
    help_by_host: dict[str, str] = {}
    for cls in PROVIDER_CLASSES:
        message = getattr(cls, "slug_help", None)
        if isinstance(message, str):
            for host in _host_keys(cls):
                help_by_host[host] = message
    return help_by_host
