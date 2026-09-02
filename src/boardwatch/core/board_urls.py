"""Board-URL / provider:slug parsing (§2.1). Shared by `companies add` and
`init`'s paste path (no duplication). Provider identity (names + public board
hostnames) is sourced from the provider registry — adding a provider needs no
change here."""

from __future__ import annotations

import re
from urllib.parse import ParseResult, urlparse

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
    # ONE trailing dot is the DNS ROOT and `boards.greenhouse.io.` resolves to exactly the same
    # host as `boards.greenhouse.io`. Stripped BEFORE `_match_host`, because otherwise a
    # registered provider fails to match and falls all the way through to `UnregisteredBoardHost`
    # -- which is a lane's signal to file the URL as a tier-D tenant seed. A single character
    # would put a greenhouse board into the tier-D queue.
    host = (parsed.hostname or "").lower().removesuffix(".")
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
    #
    # **The subclass is a HOST-REGISTRATION classification only: "no provider registers this
    # host". It does NOT promise the value was a well-formed absolute URL** -- a scheme was
    # prepended above, so `parse_board_target("a.test/x")` raises it for a bare host, and a control
    # char in the PATH leaves the host well-formed so it raises here too. Addressability is a
    # SEPARATE property a lane must validate with `is_seedable_url` before recording a tier-D seed.
    # The two checks below reject only the values whose HOST is unfit -- `https://` yields no host,
    # `not a url at all` a "hostname" of spaces, an out-of-range port fails `parsed.port` -- so a
    # host-shaped-but-unregistered value still takes the subclass, and a malformed host takes the
    # BASE class, the same class and message those inputs produced before the subclass existed.
    if not _is_hostname(host) or not _has_usable_port(parsed):
        raise UnknownBoardURL(f"unrecognized board target {value!r}; {_SUPPORTED}")
    raise UnregisteredBoardHost(f"unrecognized board target {value!r}; {_SUPPORTED}")


# A conservative DNS name: labels of alphanumerics, hyphen and underscore, 253 characters at most.
# Deliberately narrower than what `urlsplit` accepts -- it exists to decide whether a host is
# fit to be RECORDED as a seed, not whether some client could dial it. Rejecting a legitimate
# oddity costs the base exception class instead of the subclass, which every existing caller
# already handles identically; accepting a malformed one puts an unresolvable row in `lane_seeds`
# that nothing can ever drain.
_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)[a-z0-9_]([a-z0-9_-]{0,61}[a-z0-9_])?"
    r"(\.[a-z0-9_]([a-z0-9_-]{0,61}[a-z0-9_])?)*$"
)


def _is_hostname(host: str) -> bool:
    """Is this fit to be recorded as a seed's routing host?"""
    return bool(host) and _HOSTNAME_RE.match(host) is not None


def _has_usable_port(parsed: ParseResult) -> bool:
    """`ParseResult.port` validates LAZILY and raises on an out-of-range or non-numeric port.

    Reached only on the failure path, so the cost is nil -- but unreached, an invalid port
    tracebacks out of whichever caller later touches it rather than raising the `UnknownBoardURL`
    every caller here is written to catch.
    """
    try:
        _ = parsed.port
    except ValueError:
        return False
    return True


def is_seedable_url(value: str) -> bool:
    """Is `value` a well-formed absolute http(s) URL safe to RECORD as a `lane_seeds` row?

    The ONE gate every lane's seed passes before it can be stored, so the Indeed lane's pre-filter,
    the JSON-LD lane's discovery filter and `store.seed_queries.record_seeds` (the single write
    point) all decide the same thing the same way and cannot drift. Deliberately stricter than
    what `urlsplit` tolerates and than what `parse_board_target` accepts for a HUMAN paste (a bare
    host, a `provider:slug` shorthand): a seed URL is machine-emitted by a lane, so anything short
    of a genuine absolute URL is malformed input, not evidence of an as-yet-unregistered vendor.

    **This is separate from `UnregisteredBoardHost`, and must be, because that class does NOT
    promise addressability.** `parse_board_target` prepends a scheme to a bare host, so
    `parse_board_target("newco.applytojob.com/x")` raises the subclass for a value that is not an
    absolute URL at all, and a control char in the PATH leaves the host well-formed so the subclass
    is raised there too. The subclass answers "does any provider register this host"; this answers
    "is this string one a resolver could actually GET and a log could match". Both have to hold
    before a URL may seed.

    Rejects, in order:

    * a value with no `://` scheme separator -- a bare host or `provider:slug` paste, not a URL a
      resolver can GET;
    * an out-of-range or non-numeric port -- `parsed.port` validates 0-65535 LAZILY and raises
      `ValueError`, which `urlsplit` itself does not, so HTTPX would reject it only at fetch AFTER
      the row had persisted as undrainable dead weight;
    * a scheme other than http(s), or no hostname at all (`https://` yields neither);
    * ANY whitespace, C0 control char (0x00-0x1F) or DEL (0x7F) anywhere in the value. NUL and DEL
      slip past `isspace()` yet HTTPX rejects them as `InvalidURL`; and `urlsplit` follows WHATWG
      and STRIPS tabs/newlines before parsing, so a value it silently cleans up would ROUTE fine
      yet persist a URL string no fetch log or human could match against the one actually dialed.

    A valid `:443` and a single trailing DNS-root-dot URL both PASS -- `seed_host` still normalizes
    those to a routing host the resolver filters match, so they seed and stay drainable.
    """
    if "://" not in value:
        return False
    try:
        parsed = urlparse(value)
        _ = parsed.port  # validates the 0-65535 range; `urlparse` itself does not.
    except ValueError:
        # A bare `ValueError` from `urlsplit`: an unbalanced `[`/`]` in the authority
        # (`https://[broken`), or a port outside 0-65535 (`https://a.test:99999/x`).
        return False
    hostname = parsed.hostname
    if parsed.scheme not in ("http", "https") or not hostname:
        return False
    if any(ch.isspace() or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        return False
    return " " not in hostname


def _normalize_slug(provider: str, slug: str) -> str:
    normalizer = _SLUG_NORMALIZERS.get(provider)
    if normalizer is None:
        return slug
    try:
        return normalizer(slug)
    except ValueError as exc:
        raise UnknownBoardURL(f"invalid {provider} board target {slug!r}: {exc}") from exc
