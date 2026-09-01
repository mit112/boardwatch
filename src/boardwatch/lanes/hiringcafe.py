"""Lane 1: hiring.cafe (SSR search surface, re-pointed 2026-08-31 under D-393).

Every request shape here is one this repo has actually made. One of them, and no others:

    GET https://hiringcafe.com/?searchState={json}&page={n}   -- search, server-rendered

No key, no cookie, no TLS bypass, no app impersonation. That last clause is why this lane
exists at all: Indeed's free body is reachable only behind a key lifted from its iOS app with
certificate verification switched off, so Indeed is parked and hiring.cafe took lane 1.

WHY THE SURFACE MOVED. The lane shipped against the PATH form (`/jobs/{role}`) because
`robots.txt` disallows `/*?searchState=*` and `/*?page=*`. From run 129 the path form was
refused on its first request of every run -- 14 facets, 14 refusals, an outage that survived
D-369's header work because the headers were never the cause. **The owner reversed the hold
(D-393): the `?searchState=` form is approved for this project, superseding D-369 and this
host's `robots.txt`.** The reference implementation this repo is absorbing has used that form
in production for months. So the facet is a JSON query value again, and the disallowed-form
assertions that used to guard `search_urls` are inverted rather than deleted -- see
`tests/unit/hiringcafe_shape.py`, which records the rules and the ruling that supersedes them.

WHAT THE searchState CARRIES, AND THE FOUR KEYS IT DELIBERATELY OMITS. The reference
implementation pre-filters at the source on `seniorityLevel`, `roleYoeRange`,
`commitmentTypes`, `securityClearances` and a fixed United States `locations` entry. **None of
those are sent from here.** Every one is a fact about a particular USER -- their seniority,
their years, their clearance, their country -- and boardwatch judges all four downstream with
rules that must be able to return `ABSTAIN(missing_profile_field:X)`. A query parameter that
removes those postings before any rule sees them makes the search string, not the eligibility
engine, the thing that decided; the abstain rate would read 0% for a rule that never got the
chance to fire. It also hard-codes one persona into a module, which is the first thing the
multi-tenancy requirement forbids: facets come from the PROFILE, never from here. What IS sent
is `searchQuery` (the profile's target title, via `lanes.facets`) plus two lane-MECHANICAL
keys, `sortBy: "date"` and `dateFetchedPastNDays`, which describe how often this lane runs
rather than who is running it.

WHY A FACET AT ALL. Unfaceted, this lane returns the general labour market: of the 282 open
postings the armed lanes had acquired by 2026-08-26, 3 were software roles and 197 were
explicitly not (nurse, barista, crew member, dishwasher). The downstream role gate was not at
fault -- the lane was not rejecting software postings, it was barely surfacing any. The probed
role page returned 20 of 20 software roles. The facets come from `profile.target_titles_json`
via `lanes.facets`, never from a query written down here, which is what keeps the lane fit for
a user whose targets are not software at all.

A BOGUS FACET ANSWERS 200 WITH ZERO HITS, NOT 404 -- probed. So an empty result does NOT report
itself: if the search route ever moves, every facet returns nothing, no request fails, and the
lane reports a clean quiet day forever -- the prior art's 11-run silent outage exactly. The
tally cannot catch it either, because with no hits nothing is ever attempted and
`is_silent_outage` stays False. Hence EVERY facet empty raises `SearchPageError`, while one
empty facet among several does not: that is a profile-data matter, not an outage, and raising
would let one odd target title disable the whole lane.

PAGING IS REAL NOW, and `&page=N` is measured rather than inferred. Two GETs on 2026-08-31,
1.5s apart, against the exact searchState this module builds: page 0 returned 143 hits and
page 1 returned 133, `ssrIsLastPage` False on both, `ssrPage` echoing the requested number,
and **zero id overlap between the two pages** -- so the parameter turns a page instead of
re-serving one. `LaneResult.search_pages` therefore reports true depth for this lane at last:
a facet that stopped short of the ceiling ran out of results, and one that filled every page
was truncated, which a posting count alone cannot tell apart. Pacing is the `Fetcher`'s
per-host floor (>=1.0s), which is already stricter than the reference implementation's 0.5s
sleep, so no lane-local delay is added.

`objectID` IS AN OPAQUE KEY. It looks like `{source}___{board_token}___{id}` and is exactly
that for 128 of 160 sampled hits, which is what makes it dangerous: a round-trip test over a
typical sample passes. Splitting on `___` mis-attributes 36 of 160 (22.5%) in three ways --
`taleo_careersection` separates with single underscores, `fountain`'s `board_token` itself
contains `___`, and `saashr` differs in case from its own `board_token`. `source` and
`board_token` are explicit top-level keys and non-blank on all 160. This module reads those and
uses `objectID` for nothing but the JD endpoint's `id` parameter.

WHAT THE LANE TRUSTS FROM THE PAYLOAD, AND WHAT IT DOES NOT. `v5_processed_job_data` is
untrusted for eligibility (D-278) and stays that way: the eligibility engine is body-only, so
it structurally cannot read these fields. The location TEXT lives nowhere else in the payload
(`_geoloc` is coordinates, and `rank/location_gate` matches text), so `workplace_*` populates
`RawPosting.locations` as provider-asserted metadata at exactly the trust level greenhouse's
`location.name` already has -- and never as evidence for a verdict.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import zip_longest
from typing import Any
from urllib.parse import quote

from selectolax.parser import HTMLParser

from boardwatch.core.board_urls import UnknownBoardURL
from boardwatch.core.models import RawPosting
from boardwatch.core.politeness import Fetcher, FetchFailure
from boardwatch.lanes.base import CompanyAdmission, LaneCompanySnapshot, LaneResult, lane_snapshot
from boardwatch.lanes.dereference import UnresolvablePostingURL, parse_posting_target
from boardwatch.lanes.outcomes import AcquisitionOutcome, AcquisitionTally
from boardwatch.lanes.quality import assess_body

LANE_NAME = "hiringcafe"

# The provider a hit is keyed under when its `apply_url` names no board this repo can parse --
# which is 95% of them, and is the point of the lane.
LANE_PROVIDER = "hiringcafe"

# `hiring.cafe` 308-redirects to `hiringcafe.com`; the canonical host moved since the design
# was written. Recorded so a future reader does not "correct" it back -- the 2026-08-31 probe
# addressed `hiring.cafe` and read its 200 back from `hiringcafe.com`, so naming the canonical
# host here is what keeps a redirect off every page request.
SEARCH_URL = "https://hiringcafe.com/"
_JOB_DESCRIPTION_URL = "https://hiringcafe.com/api/job-description?id="

# D8's ceiling on body GETs per lane per run. A hard cap rather than a pacing knob: the search
# page returns ~159 hits and the runner's company cap does not bound postings, only companies.
DEFAULT_POSTING_BUDGET = 60

# Search pages requested per facet. 1 is the single-page behaviour the lane shipped with and
# stays the default; `Settings.lane_search_pages` is what raises it. Clamped in `__init__`
# rather than trusted, so a lane constructed directly with 0 cannot fetch no page at all and
# report the resulting silence as a quiet day.
DEFAULT_SEARCH_PAGES = 1

# How far back the search reaches, in days. A LANE-mechanical number, not a user-specific one:
# it says how often this lane runs (daily, with slack for a missed day), not who is running it,
# which is the line the module docstring draws around the searchState's other keys. It also
# bounds the result set so that paging terminates on `ssrIsLastPage` rather than on the ceiling.
SEARCH_RECENCY_DAYS = 7

# The header set a browser sends for a top-level navigation, applied to the SEARCH route only
# (D-369). The lane client has always carried a Chrome UA; what it did not carry was any of the
# headers that UA implies, and two of httpx's defaults CONTRADICT it outright -- `Accept: */*`,
# which no browser sends when navigating to an HTML page, and no `Accept-Language` at all.
#
# Ranked FIRST against D-368's ordering, which had this second behind volume on the premise that
# "we self-identify as a bot". That premise was false -- the UA above is a Chrome string and has
# been since the lane shipped -- and the volume premise did not survive either: run 128, the last
# search that WORKED, spent 14 search GETs and 14 body GETs against the reference client's
# ~20-25 a day, and the run after it was refused on its FIRST request 14 hours later. A rate
# counter decays over 14 hours; a classification does not.
#
# What the reference client does differently is the one header it sets by hand: `Accept:
# text/html`. It is otherwise SPARSER than ours in every respect -- no `Accept-Language`, no
# `Sec-Fetch-*`, `Connection: close` -- and it is not refused, which is what rules out "too few
# browser headers" and leaves CONTRADICTION with the claimed UA as the difference worth removing.
#
# THE LINE THIS DOES NOT CROSS, and it is the same line the module docstring already draws: every
# header here RESTATES, in the form a browser uses, the claim the UA already makes, and asserts
# nothing new. No TLS shaping, no cookie, no `sec-ch-ua` client hints (a server negotiates those
# via `Accept-CH`; sending them unasked would be a fresh assertion, not a restatement), and no
# attempt to answer a challenge. `Accept-Encoding` is deliberately LEFT TO httpx: Chrome
# advertises `br` and `zstd`, this client can decode neither, and advertising an encoding we
# cannot read trades a header mismatch for a corrupted body. If the host still refuses us after
# this, the remedy is the access request, not a further step in this direction.
_SEARCH_HEADERS = {
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,"
        "image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    # `none` and `?1`: this lane types a URL in directly. It follows no link and sends no
    # `Referer`, so any other value here would be the fresh assertion the note above refuses.
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}


class SearchPageError(ValueError):
    """The search page was served but carried no usable `ssrHits`.

    Distinct from `FetchFailure`, which the fetcher already raises for a transport or status
    failure. Both propagate: a lane is additive breadth, so the runner catches and records
    rather than the lane returning an empty result that reads like a quiet day.
    """


class UnidentifiableHit(ValueError):
    """A hit carrying no `(provider, slug, posting id)` this repo can key a company on.

    Typed at the raise site rather than signalled by a None return, so the one caller that
    can tolerate it -- the grouping pass, which counts it and moves on -- says so explicitly
    instead of every caller having to remember that None means "skip".
    """


@dataclass(frozen=True)
class HitIdentity:
    """The store identity one search hit resolves to (design D2)."""

    provider: str
    slug: str
    posting_id: str


# One hit and the search page it was found on. The URL rides with the hit rather than being
# tracked alongside it, so a hit can never be attributed to the wrong facet.
_SearchEntry = tuple[str, dict[str, Any]]


@dataclass
class _CompanyHits:
    """One company's hits, and the search page it was FIRST seen on.

    First-seen rather than a set of every page it appeared on: `BoardSnapshot.url` is one
    string, and a company found under three facets has no single truthful list to put there.
    """

    url: str
    hits: list[tuple[HitIdentity, dict[str, Any]]]


@dataclass(frozen=True)
class SearchPage:
    """One server-rendered search page: its hits, and whether the host says it is the last.

    `is_last_page` rides WITH the hits rather than being re-read by the caller, because the two
    come out of one payload and a paging loop that had to fetch the flag separately could not
    honour it. `True` only when the payload says so explicitly -- an absent or non-boolean
    `ssrIsLastPage` reads as "not the last", so a renamed flag costs the ceiling's worth of
    requests and stops on an empty page rather than silently truncating every facet to one.
    """

    hits: list[dict[str, Any]]
    is_last_page: bool


def parse_search_page(page_html: str) -> SearchPage:
    """`props.pageProps` out of the `__NEXT_DATA__` script block, as hits + the last-page flag.

    Parsed with selectolax rather than a regex over the 1.28 MB page: the JSON contains
    `</div>` inside string values, so a regex terminated on the wrong tag boundary. (The
    reference implementation regexes it and gets away with it; this repo measured the failure.)

    `ssrError` is raised, never absorbed. The host reports a search-side failure IN a 200
    response, so a caller that read only `ssrHits` would see an empty list and record the
    quiet day this lane's whole design exists to make impossible.
    """
    node = HTMLParser(page_html).css_first("script#__NEXT_DATA__")
    if node is None:
        raise SearchPageError("no <script id='__NEXT_DATA__'> in the search page")
    try:
        props = json.loads(node.text())["props"]["pageProps"]
    except (ValueError, KeyError, TypeError) as exc:
        raise SearchPageError(f"unreadable __NEXT_DATA__: {exc}") from exc
    if not isinstance(props, dict):
        raise SearchPageError(f"pageProps is {type(props).__name__}, not an object")
    error = props.get("ssrError")
    if error is not None:
        raise SearchPageError(f"the search page reported ssrError: {error!r}")
    hits = props.get("ssrHits")
    if not isinstance(hits, list):
        raise SearchPageError(f"ssrHits is {type(hits).__name__}, not a list")
    return SearchPage(
        hits=[hit for hit in hits if isinstance(hit, dict)],
        is_last_page=props.get("ssrIsLastPage") is True,
    )


def hit_identity(hit: dict[str, Any]) -> HitIdentity:
    """(provider, slug, posting id) for one hit, D2's order.

    The `apply_url` attempt comes first and is the convergence case: when the employer's real
    URL is a greenhouse / lever / ashby / workable posting, the identity recovered from it is
    the SAME `(company_id, provider_posting_id)` a later board scan produces, so the
    aggregator's copy converges through `UNIQUE(company_id, provider_posting_id)` instead of
    duplicating. Both dereference failures are ordinary here -- 95% of hits sit on an ATS this
    repo has no adapter for, which is the reach the lane was built for, not an error.
    """
    apply_url = _text(hit.get("apply_url"))
    if apply_url:
        try:
            target = parse_posting_target(apply_url)
        except (UnknownBoardURL, UnresolvablePostingURL):
            pass
        else:
            return HitIdentity(target.provider, target.slug, target.posting_ref)
    source = _text(hit.get("source"))
    board_token = _text(hit.get("board_token"))
    object_id = _text(hit.get("objectID"))
    if not (source and board_token and object_id):
        raise UnidentifiableHit(
            "hit is missing source / board_token / objectID, all of which the contract "
            f"records as non-blank on every sampled hit: {object_id or hit.get('id')!r}"
        )
    return HitIdentity(LANE_PROVIDER, f"{source}:{board_token}", object_id)


def company_name(hit: dict[str, Any]) -> str:
    """`enriched_company_data.name` -- non-blank on 159/159 probed hits -- else `board_token`.

    Never blank, which is what `LaneCompanySnapshot.name` requires: the fallback is a field the
    contract records as non-blank on every hit, so an employer this lane cannot name properly is
    still named by something it can evidence rather than by an empty string.
    """
    enriched = hit.get("enriched_company_data")
    name = _text(enriched.get("name")) if isinstance(enriched, dict) else ""
    return name or _text(hit.get("board_token"))


def job_description_url(object_id: str) -> str:
    return f"{_JOB_DESCRIPTION_URL}{quote(object_id, safe='')}"


def search_state(query: str) -> dict[str, Any]:
    """The search request's whole state object: ONE profile-derived key and two mechanical ones.

    `searchQuery` is the user's target title, handed down from `profile.target_titles_json` via
    `lanes.facets`. `sortBy` and `dateFetchedPastNDays` describe the lane's own cadence.

    THE OMISSIONS ARE THE DESIGN. `seniorityLevel`, `roleYoeRange`, `commitmentTypes`,
    `securityClearances` and a fixed `locations` entry are all available here and all left out,
    for the reason the module docstring gives at length: each is a fact about one user that
    boardwatch already judges with a rule that must be able to ABSTAIN, and filtering on it in
    the query would let a URL decide what the eligibility engine is supposed to. Adding one is a
    keystone-invariant change, not a tuning knob.

    Key ORDER is fixed because the serialization is: `json.dumps` preserves insertion order, so
    a reordering silently changes every URL this lane requests and every cache key derived from
    one.
    """
    return {"searchQuery": query, "sortBy": "date", "dateFetchedPastNDays": SEARCH_RECENCY_DAYS}


def search_urls(facets: Sequence[str]) -> tuple[str, ...]:
    """One SSR search URL per facet, or the unfaceted search when there are none.

    `lanes.facets` hands over a canonical TERM ("software engineer") and it is sent VERBATIM as
    the JSON `searchQuery`: the hyphenation the retired path form needed was that route's own
    encoding, and applying it here would ask the host for a different phrase than the profile
    names. `quote` with no safe characters percent-encodes the serialized state whole, so no
    character a facet can contain -- `&`, `#`, `/`, `?` -- can escape the one query value it
    belongs to and add a parameter of its own.

    The no-facet fallback is the behaviour that shipped, and it is a fallback rather than an
    error because a profile that names no target titles is a legitimate profile -- it is what
    every user has before onboarding fills one in. It is now the SAME request shape with an
    empty `searchQuery` rather than a different route, so the unfaceted user pages exactly as
    the faceted one does.
    """
    terms = tuple(facets) or ("",)
    return tuple(
        f"{SEARCH_URL}?searchState={quote(json.dumps(search_state(term)), safe='')}"
        for term in terms
    )


def page_url(search_url: str, page_index: int) -> str:
    """`search_url` at page `page_index`, as the `&page=` parameter the probe measured.

    **Page 0 is `&page=0`, spelled out.** That is the request the 2026-08-31 probe actually
    made and the shape the reference implementation has used in production, so the first page
    carries it too; suppressing it for page 0 would make the default configuration request a
    URL nothing has ever measured, purely to look tidier.
    """
    return f"{search_url}&page={page_index}"


class HiringCafeLane:
    name = LANE_NAME

    def __init__(
        self,
        posting_budget: int = DEFAULT_POSTING_BUDGET,
        search_facets: Sequence[str] = (),
        search_pages: int = DEFAULT_SEARCH_PAGES,
    ) -> None:
        self._posting_budget = posting_budget
        # Injected rather than read here, for the reason the registry comment in `runner.py`
        # gives: the facets come from the user's profile row, which lives in the store, and a
        # lane must not reach into the store to find its own configuration.
        self._search_facets = tuple(search_facets)
        self._search_pages = max(1, search_pages)

    def collect(self, fetcher: Fetcher, admits: CompanyAdmission) -> LaneResult:
        """One search GET per role facet, then one body GET per posting at an admitted company.

        `admits` is asked once per distinct `(provider, slug)`, in first-seen order, BEFORE any
        body is fetched -- the protocol's contract, and the only ordering under which the
        per-run company cap saves requests instead of discarding paid-for ones.
        """
        entries, search_pages = self._search(fetcher)

        tally = AcquisitionTally()
        by_company = _group_by_company(entries, tally)
        snapshots: list[LaneCompanySnapshot] = []
        remaining = self._posting_budget
        for (provider, slug), company_hits in by_company.items():
            if not admits(provider, slug):
                # Nothing is tallied for a refused company: no request was attempted, and an
                # outcome recorded here would inflate `attempted` with non-attempts. Refusals
                # are reported by name through `admission.CompanyBudget.refused`, which is the
                # channel designed for them.
                continue
            postings: list[RawPosting] = []
            for identity, hit in company_hits.hits:
                if remaining <= 0:
                    # Seen, not requested. The catalog is closed, and `not_attemptable` is its
                    # only member meaning that -- its stated reason (no resolvable URL) is
                    # narrower than this condition, but counting is the invariant and a silent
                    # drop is what the catalog exists to prevent.
                    tally.record("not_attemptable")
                    continue
                remaining -= 1
                posting = self._fetch_posting(fetcher, identity, hit, tally)
                if posting is not None:
                    postings.append(posting)
            if postings:
                # A company whose every body was refused yields no snapshot: an empty one would
                # still write a `board_scans` row and oblige a company row for zero postings,
                # and the refusal is already counted in the tally.
                snapshots.append(
                    LaneCompanySnapshot(
                        provider=provider,
                        slug=slug,
                        # Taken from the first hit in the group. Every hit in it shares one
                        # `(source, board_token)`, so they describe one employer; the probe
                        # found `enriched_company_data.name` non-blank on 159 of 159 hits, and
                        # `company_name` falls back to `board_token` rather than to a blank.
                        name=company_name(company_hits.hits[0][1]),
                        # The page this company was actually found on. Citing the unfaceted
                        # root would name a URL a faceted run never requested.
                        snapshot=lane_snapshot(postings, company_hits.url),
                    )
                )
        return LaneResult(snapshots=tuple(snapshots), tally=tally, search_pages=search_pages)

    def _search(self, fetcher: Fetcher) -> tuple[list[_SearchEntry], tuple[tuple[str, int], ...]]:
        """Every configured search page, its hits paired with the URL they came from.

        The result is INTERLEAVED across facets, round-robin, and that is load-bearing rather
        than tidy. The body budget is spent in iteration order, so concatenating instead would
        let the first facet consume all of it and every later target title contribute nothing --
        a lane reporting fourteen facets while delivering only the profile's first one. Paging
        does not change that: a facet's own pages are read in order and the interleave is across
        facets, so facet two's page 1 is still worked before facet one's page 2.

        The second return value is how many pages were actually fetched per facet, which is
        REPORTED rather than inferred: a facet that stopped at page 2 of a 5-page ceiling ran
        out of results, and a facet that filled every page is truncated. Those are different
        facts about the same posting count and only the first is benign.
        """
        urls = search_urls(self._search_facets)
        if not self._search_facets:
            # The unfaceted fallback keeps the single-search contract it shipped with: a
            # transport or structural failure on its FIRST page propagates, because with one
            # search there are no other results for it to cost.
            entries, pages = self._facet_pages(fetcher, urls[0])
            return entries, ((urls[0], pages),)

        per_facet: list[list[_SearchEntry]] = []
        page_counts: list[tuple[str, int]] = []
        failed = 0
        for url in urls:
            try:
                entries, pages = self._facet_pages(fetcher, url)
            except (FetchFailure, SearchPageError):
                # Per-facet isolation, the same shape D-307 gave a board's apply failure.
                # Fourteen requests means the seventh must not discard the six before it, and
                # the fetcher has already retried with backoff by the time it raises, so this
                # is a surviving failure rather than a blip. Isolation must not become
                # suppression, which is what the all-empty check below is for.
                failed += 1
                per_facet.append([])
                page_counts.append((url, 0))
                continue
            per_facet.append(entries)
            page_counts.append((url, pages))

        if not any(per_facet):
            # Not a quiet day. A bogus facet answers 200 with an empty list, so if the search
            # route moves, every facet empties, nothing raises, and no counter moves -- the
            # tally cannot see it either, because nothing was ever attempted.
            raise SearchPageError(
                f"every role facet yielded nothing ({len(per_facet)} searched, {failed} request "
                "failures): the search route has moved, the host is refusing us, or none of the "
                "profile's target titles match a posting"
            )
        interleaved = [
            entry for row in zip_longest(*per_facet) for entry in row if entry is not None
        ]
        return interleaved, tuple(page_counts)

    def _facet_pages(self, fetcher: Fetcher, url: str) -> tuple[list[_SearchEntry], int]:
        """One facet's hits over at most `self._search_pages` pages, and the pages fetched.

        **A PAGE WITH NO HITS MEANS TWO DIFFERENT THINGS AND THIS IS WHERE THEY SEPARATE.** On
        the FIRST page it is the outage case a bogus facet also produces -- 200 with an empty
        list -- and it is returned rather than raised, because one target title matching nothing
        is a profile-data matter; `_search`'s all-empty check is what turns EVERY facet doing it
        into the failure the runner must see. On a LATER page it is the ordinary end of a
        facet's result set. `FetchFailure` and `SearchPageError` split the opposite way and for
        the reason `linkedin._facet_pages` states: a facet refused on its first page produced
        nothing and is a failure its caller must count, while one refused on page 4 keeps the
        three pages already paid for.

        `ssrIsLastPage` ends the facet, which is the whole point of paging against a host that
        says where the end is. A page that adds no NEW hit ends it too -- that is the offset-wrap
        tail `providers/workday.py` guards for the same reason, and it also covers a host that
        stops honouring `&page=` and re-serves page 0, which the ceiling alone would let burn
        every remaining request.

        The entry carries the PAGE's URL, not the facet's first page. It is a URL this run
        actually requested, which is the standard `BoardSnapshot.url` provenance is held to.

        No sleep is added between pages. `Fetcher` paces per host at >=1.0s inside the lock it
        holds for each request, which is already stricter than the reference implementation's
        0.5s, so a lane-local delay would be a second, weaker pacing rule.
        """
        entries: list[_SearchEntry] = []
        seen: set[str] = set()
        pages = 0
        for page_index in range(self._search_pages):
            page = page_url(url, page_index)
            try:
                result = fetcher.get(page, headers=_SEARCH_HEADERS)
                search_page = parse_search_page(result.content.decode("utf-8", "replace"))
            except (FetchFailure, SearchPageError):
                if page_index == 0:
                    raise
                break
            pages += 1
            fresh: list[_SearchEntry] = []
            new_ids: set[str] = set()
            for hit in search_page.hits:
                object_id = _text(hit.get("objectID"))
                if object_id and object_id in seen:
                    continue
                fresh.append((page, hit))
                if object_id:
                    new_ids.add(object_id)
            entries.extend(fresh)
            seen |= new_ids
            if search_page.is_last_page or not new_ids:
                break
        return entries, pages

    def _fetch_posting(
        self,
        fetcher: Fetcher,
        identity: HitIdentity,
        hit: dict[str, Any],
        tally: AcquisitionTally,
    ) -> RawPosting | None:
        object_id = _text(hit.get("objectID"))
        try:
            result = fetcher.get(job_description_url(object_id))
        except FetchFailure as exc:
            tally.record(_failure_outcome(exc))
            return None
        title = _title(hit)
        body_text, rejection = assess_body(_description(result.content), title=title)
        if rejection is not None:
            tally.record(rejection.outcome)
            return None
        tally.record("body_fetched")
        return _raw_posting(identity, hit, title=title, body_text=body_text)


def _failure_outcome(exc: FetchFailure) -> AcquisitionOutcome:
    """Status -> outcome. A transport failure has no status and is `fetch_unavailable`.

    The three buckets are kept apart because they mean different things to a reader of the
    run: 403 is the host refusing us, 404 is a posting that has gone, and a timeout is neither.
    Folding them is precisely how the prior art hid an eleven-day outage.
    """
    if exc.status_code in (401, 403):
        return "fetch_refused"
    if exc.status_code in (404, 410):
        return "fetch_gone"
    return "fetch_unavailable"


def _description(content: bytes) -> str:
    """`job.job_information.description` -- the HTML body, the one field the search omits.

    An unreadable payload returns "" rather than raising: `assess_body` then reports
    `extracted_empty`, which is what the catalog means by "a response arrived and extraction
    produced nothing substantive". A second failure mode here would need a second outcome name
    and the catalog is closed.
    """
    try:
        payload = json.loads(content)
        description = payload["job"]["job_information"]["description"]
    except (ValueError, KeyError, TypeError):
        return ""
    return description if isinstance(description, str) else ""


def _group_by_company(
    entries: list[_SearchEntry], tally: AcquisitionTally
) -> dict[tuple[str, str], _CompanyHits]:
    """Hits bucketed by `(provider, slug)`, first-seen order preserved.

    Grouping by identity rather than by `enriched_company_data.name` is the same point
    `LaneCompanySnapshot` makes in its own docstring: a name is not what `companies` is unique
    on, so a name-keyed group applies one employer's two boards against one `company_id`.

    A hit this repo cannot key, or cannot title, is counted `not_attemptable` and dropped here
    rather than raised: one malformed row must not cost the other 159, which is the
    per-posting isolation every provider's board parse already applies. Dropping it BEFORE the
    body GET is the point -- `smartrecruiters.parse_posting` refuses an empty title for the
    same reason, and a lane can refuse it a whole request earlier.
    """
    grouped: dict[tuple[str, str], _CompanyHits] = {}
    seen: set[tuple[str, str, str]] = set()
    for url, hit in entries:
        try:
            identity = hit_identity(hit)
        except UnidentifiableHit:
            tally.record("not_attemptable")
            continue
        if not _title(hit):
            tally.record("not_attemptable")
            continue
        key = (identity.provider, identity.slug, identity.posting_id)
        if key in seen:
            # A SECOND hit resolving to a posting already taken this run. Dropped here, and the
            # drop is not defensive tidiness -- without it the run aborts. `apply.py` snapshots
            # `existing` once before its loop and never re-reads it, so two rows with one
            # `provider_posting_id` both take the INSERT branch and the second violates
            # UNIQUE(company_id, provider_posting_id). That raises inside `apply_board`'s single
            # transaction, rolling the whole board back, and the exception escapes to the lane
            # stage's handler -- so every company after this one is skipped and the tally that
            # would have explained it is discarded with the report.
            #
            # Every ATS provider enumerates a board once and may assume distinct ids. An
            # AGGREGATOR may not, and this one says so in its own payload: `ssrHits` carry
            # `strict_dedup_cluster_id` and `liberal_dedup_cluster`, which exist precisely
            # because the index holds duplicate listings. Two hits from different `source`s can
            # also dereference to one greenhouse posting through `apply_url`, landing in the
            # same group by design -- that convergence is the point of the dereference step.
            tally.record("not_attemptable")
            continue
        seen.add(key)
        group = grouped.setdefault((identity.provider, identity.slug), _CompanyHits(url, []))
        group.hits.append((identity, hit))
    return grouped


def _raw_posting(
    identity: HitIdentity, hit: dict[str, Any], *, title: str, body_text: str
) -> RawPosting:
    return RawPosting(
        provider_posting_id=identity.posting_id,
        title=title,
        # The employer's own URL, not a hiring.cafe permalink: it is what the user clicks, and
        # in the convergence case it is the same URL the ATS provider would have recorded.
        url=_text(hit.get("apply_url")),
        locations=_locations(hit),
        # `posted_at`/`updated_at`/`remote_policy` stay unset. No date field appears in the
        # recorded top-level key list, and `v5_processed_job_data.workplace_type` is recorded
        # as present but its value vocabulary is not -- mapping it would be a guess, and an
        # unknown remote policy is already the honest default.
        body_text=body_text,
        # The JD HTML is deliberately NOT duplicated in here: `body_text` already carries it,
        # and `raw_json` is persisted per posting version.
        raw_json={"hit": hit},
    )


def _title(hit: dict[str, Any]) -> str:
    info = hit.get("job_information")
    if not isinstance(info, dict):
        return ""
    return _text(info.get("title")) or _text(info.get("job_title_raw"))


def _locations(hit: dict[str, Any]) -> list[str]:
    """Location TEXT out of `v5_processed_job_data.workplace_*`, the only place it exists.

    `_geoloc` is `[{"lat": ..., "lon": ...}]` and is never read: `rank/location_gate` matches
    text, so a coordinate reaches it as an unrecognized segment and resolves `unknown`, which
    fails OPEN through the hard US gate. A silently useless location is worse than none.

    Each `workplace_*` value is accepted as either a string or a list of them. The probe
    recorded the key names, not their types, and the gate classifies per segment either way.
    """
    processed = hit.get("v5_processed_job_data")
    if not isinstance(processed, dict):
        return []
    formatted = _text(processed.get("formatted_workplace_location"))
    if formatted:
        return [formatted]
    segments: list[str] = []
    for key in ("workplace_cities", "workplace_states", "workplace_countries"):
        for value in _text_list(processed.get(key)):
            if value not in segments:
                segments.append(value)
    return segments


def _text(value: Any) -> str:
    return str(value).strip() if isinstance(value, str) else ""


def _text_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    return []
