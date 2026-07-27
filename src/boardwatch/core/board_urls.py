"""Board-URL / provider:slug parsing (§2.1). Shared by `companies add` and
`init`'s paste path (no duplication). Provider identity (names + public board
hostnames) is sourced from the provider registry — adding a provider needs no
change here."""

from __future__ import annotations

from urllib.parse import urlparse

from boardwatch.providers.registry import PROVIDER_NAMES, host_provider_map

Target = tuple[str, str]


class UnknownBoardURL(ValueError):
    """A value that is neither provider:slug nor a recognized board URL."""


_HOST_PROVIDER = host_provider_map()


def _build_supported() -> str:
    providers = "|".join(sorted(PROVIDER_NAMES))
    example: dict[str, str] = {}
    for host, name in _HOST_PROVIDER.items():  # first host per provider, registration order
        example.setdefault(name, host)
    urls = ", ".join(f"{example[name]}/<slug>" for name in sorted(example))
    return f"supported forms: provider:slug (provider in {providers}), or a board URL ({urls})"


_SUPPORTED = _build_supported()


def parse_board_target(value: str) -> Target:
    value = value.strip()
    if "://" not in value and ":" in value and "/" not in value:
        provider, _, slug = value.partition(":")
        if provider in PROVIDER_NAMES and slug:
            return provider, slug
        raise UnknownBoardURL(f"unknown provider in {value!r}; {_SUPPORTED}")
    parsed = urlparse(value if "://" in value else f"https://{value}")
    url_provider = _HOST_PROVIDER.get((parsed.hostname or "").lower())
    parts = [p for p in parsed.path.split("/") if p]
    if url_provider and parts:
        return url_provider, parts[0]
    raise UnknownBoardURL(f"unrecognized board target {value!r}; {_SUPPORTED}")
