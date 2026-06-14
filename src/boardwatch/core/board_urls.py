"""Board-URL / provider:slug parsing (§2.1). Shared by `companies add` and
`init`'s paste path (no duplication)."""

from __future__ import annotations

from urllib.parse import urlparse

Target = tuple[str, str]


class UnknownBoardURL(ValueError):
    """A value that is neither provider:slug nor a recognized board URL."""


_HOST_PROVIDER = {
    "job-boards.greenhouse.io": "greenhouse",
    "boards.greenhouse.io": "greenhouse",
    "jobs.lever.co": "lever",
    "jobs.eu.lever.co": "lever",  # Lever EU boards (2nd real-world variant)
    "jobs.ashbyhq.com": "ashby",
}
_PROVIDERS = {"greenhouse", "lever", "ashby"}
_SUPPORTED = (
    "supported forms: provider:slug (provider in greenhouse|lever|ashby), or a board URL "
    "(job-boards.greenhouse.io/<slug>, jobs.lever.co/<slug>, jobs.ashbyhq.com/<slug>)"
)


def parse_board_target(value: str) -> Target:
    value = value.strip()
    if "://" not in value and ":" in value and "/" not in value:
        provider, _, slug = value.partition(":")
        if provider in _PROVIDERS and slug:
            return provider, slug
        raise UnknownBoardURL(f"unknown provider in {value!r}; {_SUPPORTED}")
    parsed = urlparse(value if "://" in value else f"https://{value}")
    url_provider = _HOST_PROVIDER.get((parsed.hostname or "").lower())
    parts = [p for p in parsed.path.split("/") if p]
    if url_provider and parts:
        return url_provider, parts[0]
    raise UnknownBoardURL(f"unrecognized board target {value!r}; {_SUPPORTED}")
