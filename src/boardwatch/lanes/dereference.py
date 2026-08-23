r"""URL -> posting-reference dereferencing (lane groundwork Part 2). No fetching here.

core.board_urls.parse_board_target turns a pasted board URL into (provider, slug) and
throws the rest of the path away. For four of the six providers that is fine: greenhouse,
lever, ashby and workable all inline every body in the board response, so a link to one
of their postings is a COMPANY DISCOVERY problem — parse_board_target -> upsert_watch ->
run_scan already turns it into that company's whole board with no new code. SmartRecruiters
and Workday are different: they are the only two providers that define a `_detail_url`
method, because their board list omits the body and a second per-posting request is
needed to get one. Dereferencing a posting LINK is therefore only necessary for
DEREFERENCE_REQUIRED_PROVIDERS — and, as of this module, NEITHER member of that set can
actually be dereferenced yet. Both are pending a live probe (see the SmartRecruiters and
Workday sections below). The utility's present value is `parse_posting_target` for the
four body-inlined providers, where a recovered `provider_posting_id` lets a later
aggregator-sourced posting converge with a board scan through
`UNIQUE(company_id, provider_posting_id)` instead of duplicating it.

This module supplies the missing half: reading the posting reference a detail fetch would
need back out of a posting URL, reusing parse_board_target for host/slug matching rather
than re-implementing it. There is no network code here (import nothing from
core/politeness.py) — every request contract that would consume a PostingTarget is
deferred to a later client plan whose first step is a live probe.

WHAT THE ROUND-TRIP TESTS ACTUALLY PROVE (read before trusting this rule against a live
URL). greenhouse (`absolute_url`, greenhouse.py:155), lever (`hostedUrl`, lever.py:120),
ashby (`jobUrl`, ashby.py:133) and workable (`url`/`shortlink`, workable.py:137) all read
`RawPosting.url` STRAIGHT OFF a field in the provider's own JSON payload — none of them
construct it. Every one of those providers' pinned fixtures states in its own README that
"All text is synthetic. No real company copy, names, URLs, ... was carried over from any
recorded board." So the round-trip test for those four providers proves this module's
extraction correctly inverts a URL VALUE THE FIXTURE'S AUTHOR CHOSE TO WRITE — evidence
that the code is internally consistent, not proof that a real greenhouse/lever/ashby/
workable URL takes this shape. (In practice these four are simple enough — and match the
public shapes documented by each provider — that this is a reasonable degree of
confidence; the point is narrower than "verified against a live URL", which it is not.)

SMARTRECRUITERS: the pinned fixture's `postingUrl` is doubly unevidenced, and a live probe
raised the reason this module now refuses it. `smartrecruiters.py:213-216` reads
`url = str(detail.get("postingUrl") or f"https://jobs.smartrecruiters.com/{identifier}/{posting_id}")`
— unlike the four above, this provider has a CONSTRUCTED FALLBACK, and the fixture's
`postingUrl` (`tests/fixtures/smartrecruiters/README.md`: "All text is synthetic... jobs.
smartrecruiters.com/acme... invented") was authored to mimic that fallback's
`.../{identifier}/{posting_id}` shape — a bare id as the last segment. SmartRecruiters'
own public API documentation shows a real posting URL combines the numeric id and a title
slug into a SINGLE path segment instead, e.g.
`https://www.smartrecruiters.com/SmartRecruiters/12308096-quality-assurance-manager`.
Against that real shape, `segments[-1]` is `"12308096-quality-assurance-manager"`, not the
id `"12308096"` — the "last path segment" rule this module uses for the other four
providers is WRONG for SmartRecruiters. Extracting a value a future fetch step would rely
on, when there is now positive reason to believe it is wrong, is exactly the fabricated
request contract this task exists to prevent — so every SmartRecruiters posting URL
refuses. UNVERIFIED CANDIDATE for a future fix, not the rule shipped here: the leading
digit run of the last path segment (`^\d+`) would recover `12308096` from both the real
shape above and the fixture's constructed-fallback shape (`744000000000001` is already
all digits). Adopting it needs a live probe pinning at least one real `postingUrl`, not an
inference from documentation plus a synthetic fixture.

WORKDAY: `_detail_url` needs an `externalPath` path-string, not an id, and the public
`en-US/{site}/job/...` URL's mapping back to that CXS path is verified nowhere in this
repo — the one recorded fixture (`externalUrl`) confirms a single tenant's shape, but
nothing here confirms the locale segment, host, or chrome segments are stable across
tenants. Guessing that mapping would fabricate a request contract, so every Workday
posting URL refuses instead of a guess.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from boardwatch.core.board_urls import parse_board_target
from boardwatch.providers.registry import PROVIDER_CLASSES

# Providers whose shipped parser reports a `provider_posting_id` that is always the URL's
# last non-empty path segment (see the module docstring for the fixture evidence behind
# each one, and its bounds). A closed catalog: any provider not in it refuses rather than
# guesses. SmartRecruiters is deliberately NOT in this set — see the module docstring.
_LAST_SEGMENT_PROVIDERS: frozenset[str] = frozenset(
    {"greenhouse", "lever", "ashby", "workable"}
)

# Providers whose board response does NOT inline the body, so dereferencing a posting link
# is the only way to get one. Discovered off the provider classes' own declared shape
# rather than hardcoded, so a provider that starts or stops defining `_detail_url` moves
# this set automatically instead of drifting silently out of sync with it. Neither current
# member can actually be dereferenced by this module yet — see the module docstring.
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
    posting segment, any SmartRecruiters posting URL, or any Workday posting URL (see the
    module docstring).
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
