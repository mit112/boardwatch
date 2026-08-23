"""URL -> posting-reference dereferencing (lane groundwork Part 2). No fetching here.

core.board_urls.parse_board_target turns a pasted board URL into (provider, slug) and
throws the rest of the path away. For four of the six providers that is fine: greenhouse,
lever, ashby and workable all inline every body in the board response, so a link to one
of their postings is a COMPANY DISCOVERY problem — parse_board_target -> upsert_watch ->
run_scan already turns it into that company's whole board with no new code. SmartRecruiters
and Workday are different: they are the only two providers that define a `_detail_url`
method, because their board list omits the body and a second per-posting request is
needed to get one. Dereferencing a posting LINK is therefore only necessary for
DEREFERENCE_REQUIRED_PROVIDERS.

This module supplies the missing half: reading the posting reference a detail fetch would
need back out of a posting URL, reusing parse_board_target for host/slug matching rather
than re-implementing it. There is no network code here (import nothing from
core/politeness.py) — every request contract that would consume a PostingTarget is
deferred to a later client plan whose first step is a live probe.

Evidence for the URL shapes below comes from feeding each provider's PINNED fixtures
through its own shipped parser (see tests/unit/test_dereference.py), never from a URL
written by hand. Doing that shows greenhouse (.../{slug}/jobs/{id}), lever
(.../{slug}/{id}), ashby (.../{slug}/{id}), workable (.../{slug}/j/{shortcode}) and
smartrecruiters (.../{slug}/{id}) all report a `provider_posting_id` that is exactly the
URL's last non-empty path segment. Workday is the excepted case: `_detail_url` needs an
`externalPath` path-string, not an id, and the public `en-US/{site}/job/...` URL's mapping
back to that CXS path is verified nowhere in this repo — the one recorded fixture
(`externalUrl`) confirms a single tenant's shape, but nothing here confirms the locale
segment, host, or chrome segments are stable across tenants. Guessing that mapping would
fabricate a request contract, so every Workday posting URL refuses instead of a guess.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from boardwatch.core.board_urls import parse_board_target
from boardwatch.providers.registry import PROVIDER_CLASSES

# Providers whose shipped parser reports a `provider_posting_id` that is always the URL's
# last non-empty path segment (see the module docstring for the fixture evidence behind
# each one). A closed catalog: any provider not in it refuses rather than guesses.
_LAST_SEGMENT_PROVIDERS: frozenset[str] = frozenset(
    {"greenhouse", "lever", "ashby", "workable", "smartrecruiters"}
)

# Providers whose board response does NOT inline the body, so dereferencing a posting link
# is the only way to get one. Discovered off the provider classes' own declared shape
# rather than hardcoded, so a provider that starts or stops defining `_detail_url` moves
# this set automatically instead of drifting silently out of sync with it.
DEREFERENCE_REQUIRED_PROVIDERS: frozenset[str] = frozenset(
    cls.name for cls in PROVIDER_CLASSES if hasattr(cls, "_detail_url")
)


class UnresolvablePostingURL(ValueError):
    """A recognized board URL that carries no posting reference this repo can evidence.

    Kept distinct from board_urls.UnknownBoardURL, which means "not a recognized board
    target at all" — that one is left to propagate unchanged from parse_board_target so a
    caller can tell the two conditions apart.
    """


@dataclass(frozen=True)
class PostingTarget:
    provider: str
    slug: str
    posting_ref: str


def _path_segments(url: str) -> list[str]:
    return [part for part in urlparse(url).path.split("/") if part]


def parse_posting_target(url: str) -> PostingTarget:
    """(provider, slug, posting_ref) for a posting URL.

    Raises board_urls.UnknownBoardURL, unchanged, when `url` is not a recognized board
    target at all. Raises UnresolvablePostingURL when it IS recognized but this repo has
    no evidenced way to read a posting reference back out of it: a board root with no
    posting segment, or any Workday posting URL (see the module docstring).
    """
    provider, slug = parse_board_target(url)
    if provider not in _LAST_SEGMENT_PROVIDERS:
        raise UnresolvablePostingURL(
            f"{provider!r} posting URLs carry no posting reference evidenced in this "
            f"repo: {url!r}"
        )
    segments = _path_segments(url)
    if len(segments) < 2:
        raise UnresolvablePostingURL(f"no posting segment in board URL: {url!r}")
    return PostingTarget(provider=provider, slug=slug, posting_ref=segments[-1])
