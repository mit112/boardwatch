r"""URL -> posting-reference dereferencing (lane groundwork Part 2). No fetching here.

core.board_urls.parse_board_target turns a pasted board URL into (provider, slug) and
throws the rest of the path away. For four of the six providers that is fine: greenhouse,
lever, ashby and workable all inline every body in the board response, so a link to one
of their postings is a COMPANY DISCOVERY problem — parse_board_target -> upsert_watch ->
run_scan already turns it into that company's whole board with no new code. SmartRecruiters
and Workday are different: they are the only two providers that define a `_detail_url`
method, because their board list omits the body and a second per-posting request is
needed to get one. Dereferencing a posting LINK is therefore only necessary for those two
— and, as of this module, NEITHER of them can actually be dereferenced yet. Both are
pending a live probe (see the SmartRecruiters and Workday sections below). The utility's
present value is `parse_posting_target` for the four body-inlined providers, where a
recovered `provider_posting_id` lets a later aggregator-sourced posting converge with a
board scan through `UNIQUE(company_id, provider_posting_id)` instead of duplicating it.

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

THE SHAPE RULE IS EXACT, AND WHY IT HAS TO BE. Each of those four providers' posting URL
is one fixed path shape, read off the provider's own board_url host list plus the URL its
parser reports (`_POSTING_PATH_SHAPES` below): greenhouse `{slug}/jobs/{id}` (fixture
`absolute_url`: boards.greenhouse.io/acme/jobs/6000001), lever `{slug}/{id}` (`hostedUrl`:
jobs.lever.co/acme/a1000000-...-000000000001), ashby `{slug}/{id}` (`jobUrl`:
jobs.ashbyhq.com/acme/ashby-0001), workable `{slug}/j/{code}` (`url`:
apply.workable.com/acme/j/AAAA111111). A path LONGER than its provider's shape refuses
instead of reading the last segment, because a trailing chrome segment is not a posting
reference and the same pinned fixtures carry those URLs as siblings of the canonical one:
lever's `applyUrl` is `{id}/apply`, ashby's is `{id}/application`, workable's
`application_url` is `{code}/apply`. Aggregator listings deep-link to exactly those. Read
as a posting reference, `apply` and `application` are CONSTANT per provider, so two
different postings at one employer collide on
`UNIQUE(company_id, provider_posting_id)`: the second is applied as a REVISION of the
first, one real body is overwritten, and no `complete` board scan ever lists `apply`, so
it closes after two misses. That is the same defect class this module already refuses
SmartRecruiters for. An exact shape per provider is a CLOSED rule; a list of chrome
suffixes to exclude would have to grow for every one a provider or an aggregator invents.

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

# Provider -> the FIXED path segments that sit between the board slug and the posting
# reference. A posting URL's path must be exactly `{slug}/{*fixed}/{ref}` — nothing
# shorter, nothing longer. See the module docstring for the evidence behind each shape and
# for why a longer path must refuse rather than read its last segment. A closed catalog:
# any provider absent from it refuses rather than guesses. SmartRecruiters is deliberately
# NOT in it, and neither is Workday — see the module docstring.
_POSTING_PATH_SHAPES: dict[str, tuple[str, ...]] = {
    "greenhouse": ("jobs",),
    "lever": (),
    "ashby": (),
    "workable": ("j",),
}


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
    """Path segments, normalized EXACTLY as parse_board_target normalizes.

    parse_board_target deliberately accepts scheme-less input by prefixing `https://`
    (`boards.greenhouse.io/acme` is a valid board target). Without the same prefix here,
    urlparse reads the hostname as the first path segment, so a bare board root would parse
    as a posting whose reference is the slug. Two functions in one call chain must not
    disagree about their input domain.
    """
    url = url.strip()
    parsed = urlparse(url if "://" in url else f"https://{url}")
    return [part for part in parsed.path.split("/") if part]


def parse_posting_target(url: str) -> PostingTarget:
    """(provider, slug, posting_ref) for a posting URL.

    Raises board_urls.UnknownBoardURL, unchanged, when `url` is not a recognized board
    target at all. Raises UnresolvablePostingURL when it IS recognized but this repo has
    no evidenced way to read a posting reference back out of it: any SmartRecruiters or
    Workday posting URL, and any path that is not exactly its provider's posting shape —
    a bare board root, or a canonical posting URL with a trailing chrome segment such as
    lever's `/apply` or ashby's `/application` (see the module docstring).
    """
    provider, slug = parse_board_target(url)
    shape = _POSTING_PATH_SHAPES.get(provider)
    if shape is None:
        raise UnresolvablePostingURL(
            f"{provider!r} posting URLs carry no posting reference evidenced in this "
            f"repo: {url!r}"
        )
    segments = _path_segments(url)
    if len(segments) != len(shape) + 2 or tuple(segments[1:-1]) != shape:
        expected = "/".join(("{slug}", *shape, "{posting_ref}"))
        raise UnresolvablePostingURL(
            f"{provider!r} posting URLs are {expected}; {url!r} is not that shape"
        )
    return PostingTarget(provider=provider, slug=slug, posting_ref=segments[-1])
