"""Board-URL / provider:slug parsing (§2.1). Shared by `companies add` and
`init`'s paste path (no duplication). Provider identity (names + public board
hostnames) is sourced from the provider registry — adding a provider needs no
change here."""

from __future__ import annotations

from urllib.parse import urlparse

from boardwatch.providers.registry import (
    PROVIDER_NAMES,
    host_provider_map,
    slug_extractor_map,
    slug_help_map,
    slug_normalizer_map,
)

Target = tuple[str, str]


class UnknownBoardURL(ValueError):
    """A value that is neither provider:slug nor a recognized board URL."""


_HOST_PROVIDER = host_provider_map()
_SLUG_EXTRACTORS = slug_extractor_map()
_SLUG_NORMALIZERS = slug_normalizer_map()
_SLUG_HELP = slug_help_map()


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
            return provider, _normalize_slug(provider, slug)
        raise UnknownBoardURL(f"unknown provider in {value!r}; {_SUPPORTED}")
    parsed = urlparse(value if "://" in value else f"https://{value}")
    host = (parsed.hostname or "").lower()
    url_provider = _HOST_PROVIDER.get(host)
    parts = [p for p in parsed.path.split("/") if p]
    if url_provider and parts:
        extractor = _SLUG_EXTRACTORS.get(host)
        extracted_slug = extractor(host, parts) if extractor else parts[0]
        if extracted_slug:
            return url_provider, _normalize_slug(url_provider, extracted_slug)
        help_text = _SLUG_HELP.get(host)
        if help_text:
            raise UnknownBoardURL(f"cannot extract a board slug from {value!r}: {help_text}")
    raise UnknownBoardURL(f"unrecognized board target {value!r}; {_SUPPORTED}")


def _normalize_slug(provider: str, slug: str) -> str:
    normalizer = _SLUG_NORMALIZERS.get(provider)
    return normalizer(slug) if normalizer else slug
