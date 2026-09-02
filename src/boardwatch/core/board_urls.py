"""Board-URL / provider:slug parsing (§2.1). Shared by `companies add` and
`init`'s paste path (no duplication). Provider identity (names + public board
hostnames) is sourced from the provider registry — adding a provider needs no
change here."""

from __future__ import annotations

from urllib.parse import urlparse

from boardwatch.providers.registry import (
    PROVIDER_NAMES,
    composite_slug_providers,
    host_provider_map,
    host_suffix_provider_map,
    slug_extractor_map,
    slug_help_map,
    slug_normalizer_map,
)

Target = tuple[str, str]


class UnknownBoardURL(ValueError):
    """A value that is neither provider:slug nor a recognized board URL."""


class UnregisteredBoardHost(UnknownBoardURL):
    """The value names NO provider this repo registers at all -- not a malformed value, and not
    a REGISTERED provider whose slug this particular value happens not to carry.

    A subclass, not a sibling: every existing `except UnknownBoardURL` in this repo (`companies
    add`, `init`, the hiring.cafe/jobapps/indeed lanes, GitHub-lists discovery) catches this one
    unchanged, with the same message text at every OTHER raise site in `parse_board_target` --
    only the "matched no provider at all" branch below raises it, so a caller that cares about
    that distinction specifically (a lane deciding what to hand `lane_seeds`, D-413) can catch it
    on its own, and every caller that does not care sees no behaviour change at all.
    """


_HOST_PROVIDER = host_provider_map()
_HOST_SUFFIX_PROVIDER = host_suffix_provider_map()
_SLUG_EXTRACTORS = slug_extractor_map()
_SLUG_NORMALIZERS = slug_normalizer_map()
_SLUG_HELP = slug_help_map()
_COMPOSITE_SLUG = composite_slug_providers()


def _build_supported() -> str:
    providers = "|".join(sorted(PROVIDER_NAMES))
    example: dict[str, str] = {}
    for host, name in _HOST_PROVIDER.items():  # first host per provider, registration order
        example.setdefault(name, host)
    urls = ", ".join(f"{example[name]}/<slug>" for name in sorted(example))
    return f"supported forms: provider:slug (provider in {providers}), or a board URL ({urls})"


_SUPPORTED = _build_supported()


def _match_host(host: str) -> tuple[str, str] | None:
    """(provider name, MAP KEY) for an exact-host or suffix match, else None.

    The map key is what the extractor and help dicts are keyed by: the exact host when the
    host matched exactly, otherwise the matching suffix. Exact wins over suffix. Suffixes
    carry a leading dot, which is the label boundary that stops `notmyworkdayjobs.com` from
    matching `.myworkdayjobs.com`."""
    if host in _HOST_PROVIDER:
        return _HOST_PROVIDER[host], host
    for suffix, name in _HOST_SUFFIX_PROVIDER.items():
        if host.endswith(suffix):
            return name, suffix
    return None


def parse_board_target(value: str) -> Target:
    if "://" not in (value := value.strip()) and ":" in value:
        provider, _, slug = value.partition(":")
        # "/" is allowed in the slug ONLY for a composite-slug provider (workday's
        # host/tenant/site). Without that restriction `greenhouse:acme/jobs` parses as a
        # board whose every scan 404s, instead of getting the "supported forms" diagnostic.
        if provider in PROVIDER_NAMES and slug and ("/" not in slug or provider in _COMPOSITE_SLUG):
            return provider, _normalize_slug(provider, slug)
        # The "/" re-guard is load-bearing: a pasted host:port form (example.com:8080/careers)
        # must keep falling through to the URL branch rather than raising "unknown provider".
        if "/" not in value:
            raise UnknownBoardURL(f"unknown provider in {value!r}; {_SUPPORTED}")
    try:
        parsed = urlparse(value if "://" in value else f"https://{value}")
    except ValueError as exc:
        # `urlsplit` raises a BARE ValueError ("Invalid IPv6 URL") for an unbalanced `[` or `]`
        # anywhere in the authority -- a stray-bracket paste artifact does it. Every caller here
        # catches `UnknownBoardURL` and none catches ValueError, so without this a single such
        # string tracebacks out of `companies add`, `companies remove`, `init`, the hiring.cafe
        # lane and the GitHub-lists discovery, and in the last case it aborts a whole 20,000-record
        # run. `UnknownBoardURL` already subclasses ValueError, so no caller's except widens.
        raise UnknownBoardURL(f"unparseable board target {value!r}: {exc}; {_SUPPORTED}") from exc
    host = (parsed.hostname or "").lower()
    parts = [p for p in parsed.path.split("/") if p]
    matched = _match_host(host)
    if matched is not None:
        url_provider, map_key = matched
        if parts:
            extractor = _SLUG_EXTRACTORS.get(map_key)
            extracted_slug = extractor(host, parts) if extractor else parts[0]
            if extracted_slug:
                return url_provider, _normalize_slug(url_provider, extracted_slug)
        help_text = _SLUG_HELP.get(map_key)
        if help_text:
            raise UnknownBoardURL(f"cannot extract a board slug from {value!r}: {help_text}")
        # A REGISTERED provider, just not extractable from this value -- the same category as
        # the help_text case above, one provider short of a courtesy message. Deliberately the
        # base class: this value names a vendor this repo already has an adapter for.
        raise UnknownBoardURL(f"unrecognized board target {value!r}; {_SUPPORTED}")
    # No provider registers this host AT ALL, which is the one case `UnregisteredBoardHost`
    # exists to name. Same message as the branch above on purpose -- nothing about the TEXT
    # distinguishes the two cases to a human reader, only the exception class does, and every
    # existing caller matching on this message keeps matching it unchanged.
    raise UnregisteredBoardHost(f"unrecognized board target {value!r}; {_SUPPORTED}")


def _normalize_slug(provider: str, slug: str) -> str:
    normalizer = _SLUG_NORMALIZERS.get(provider)
    if normalizer is None:
        return slug
    try:
        return normalizer(slug)
    except ValueError as exc:
        raise UnknownBoardURL(f"invalid {provider} board target {slug!r}: {exc}") from exc
