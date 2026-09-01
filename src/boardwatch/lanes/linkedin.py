"""Lane 2: LinkedIn guest search (contract transcribed from D-290, 2026-08-24).

Contract: `docs/superpowers/research/2026-08-24-linkedin-lane-contract.md`. Three search request
shapes, and no others -- the search takes an optional keyword facet or geo-pinned net:

    GET .../seeMoreJobPostings/search?keywords={facet}&f_TPR=r86400  -- one facet's card list
    GET .../seeMoreJobPostings/search?f_TPR=r86400                   -- the same list, unfaceted
    GET .../seeMoreJobPostings/search?keywords={term}&location={hub}&distance={miles}&f_TPR=r86400
                                                                       -- one hub net's card list
    GET .../jobs-guest/jobs/api/jobPosting/{id}                      -- one body, one request

No key, no cookie, no TLS bypass, no app impersonation -- the search answers 200 with no User-Agent
at all, so there is nothing to spoof (D-290). That is why this lane can exist where Indeed could
not: Indeed's free body needed an iOS-app key with certificate verification off; this needs none.

**Permission is a separate axis and it is refused.** `robots.txt` disallows `/jobs-guest/` in all
77 agent groups and names `ClaudeBot` / `anthropic-ai` / `Claude-User` by name; User Agreement §8.2
forbids scripted scraping; the repo is public. Mit ruled BUILD with all of that in front of him
(D-290) -- an owner's call about the owner's own risk, recorded, not re-litigated. The lane ships
OFF by default (`lanes_enabled` is empty) and is not armed.

THE IDENTITY IS THE SLUG, AND THAT IS THE ONE STRUCTURAL DIFFERENCE FROM hiring.cafe. LinkedIn
exposes NO external apply URL (`externalApply` = 0), so a card carries no employer/ATS link to
dereference -- there is nothing for `parse_posting_target` to converge onto. Every posting is keyed
under `(provider="linkedin", slug=<company_slug>)`, where the slug is the `/company/{slug}` segment
on the card, a stable key (D-290: 0 opaque URNs). Cross-source convergence with an ATS copy of the
same role happens downstream through the P6 identity quad (company+title+location+body), never here
through a link -- exactly D-290's constraint.

THE ID IS THE URN, NOT THE URL. The job id is read from `data-entity-urn="urn:li:jobPosting:{id}"`.
The job-view URL's trailing number is NOT a reliable id and is never parsed for one -- see the
`URN_URL_MISMATCH_CARD` trap in `tests/unit/linkedin_shape.py`.

THE QUERY FACET SHIPPED; PAGING DID NOT (probed live 2026-08-26, through this repo's own
`Fetcher`). Unfaceted, this search returns the general labour market and not the user's: its 10
cards were dishwasher, crew member, dish steward, cleaner, retail cleaning associate, assembler and
bar back, and NONE were software. The same search with `keywords=software engineer` returned 10
software roles at 9 named employers and shared 0 of 10 ids with that baseline -- so `keywords=` is
honoured rather than decorative, which is what makes a facet worth a request.

THE FACETS COME FROM THE PROFILE, NEVER FROM THIS MODULE. They are `profile.target_titles_json`
read through `lanes.facets` and handed to the constructor. A role query written down here would fit
exactly one user and silently mislead every other one -- the multi-tenancy requirement names that
failure first, and it is why the contract deferred the facet rather than guessing at one. A profile
naming no target titles falls back to the unfaceted search, which is the behaviour that shipped.

`start` IS A REAL ITEM OFFSET AND IS NOW IMPLEMENTED, BEHIND `lane_search_pages` (default 1).
`&start=10` and `&start=25` each returned 10 cards whose ids were all new against `start=0`, so one
search page is 10 cards. Paging was deferred on the reasoning that a realistic facet set already
lists more cards than `DEFAULT_POSTING_BUDGET` can fetch bodies for, so a second page could only be
counted `not_attemptable`. **That reasoning was sound when written and the measurement falsified
it**: on runs 126/127 the lane fetched 49 and 53 bodies against a budget of 60, under it every time,
because one page per facet does not list enough cards to reach the budget at all. The ceiling is a
setting rather than a constant so that no existing user's request volume moves — `1` is the
single-page behaviour that shipped, byte for byte, and an operator opts into more.

PAGE 1 AND PAGE N ARE NOT THE SAME EVENT, and `_facet_pages` is where that is enforced. A page with
no cards is `card_nodes`' structural failure on the FIRST page and the ordinary end of a facet's
result set on any later one; a keyword with 23 matches has no page 3, so raising there would make a
normal run look like an outage the moment the ceiling is raised above 1.

`location=` and `distance=` are honored by this endpoint: a location-bound request returns a
geographically filtered card set that is disjoint from the same-term no-location set. They are sent
only for explicitly configured hub nets; facet and unfaceted URLs omit them so the default-off path
keeps its shipped request shape. `f_WT=2` remains measured as id-identical to the unfiltered set and
is never sent.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from itertools import zip_longest
from urllib.parse import quote, urlsplit

from selectolax.parser import HTMLParser, Node

from boardwatch.core.clock import to_naive_utc
from boardwatch.core.models import RawPosting
from boardwatch.core.politeness import Fetcher, FetchFailure
from boardwatch.lanes.base import CompanyAdmission, LaneCompanySnapshot, LaneResult, lane_snapshot
from boardwatch.lanes.outcomes import AcquisitionOutcome, AcquisitionTally
from boardwatch.lanes.quality import assess_body

LANE_NAME = "linkedin"

# The provider every LinkedIn posting is keyed under. There is no ATS to converge onto through a
# link (contract §2: no external apply URL), so unlike hiring.cafe this never resolves to a
# six-provider board -- convergence is the P6 identity quad's job, downstream.
LANE_PROVIDER = "linkedin"

# Contract §1: the guest search, last-24h filtered. `f_TPR=r86400` is the filter parameter the probe
# evidenced; `f_WT=2` (remote) remains id-identical to unfiltered and is never sent. `location=` and
# `distance=` are added only by the explicit hub-net URL shape below.
_SEARCH_ENDPOINT = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
_RECENCY_PARAM = "f_TPR=r86400"
SEARCH_URL = f"{_SEARCH_ENDPOINT}?{_RECENCY_PARAM}"
_JOB_POSTING_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/"

# The ceiling on body GETs per run. A hard cap, not a pacing knob: one search returns ~10 cards and
# the runner's company cap bounds companies, not postings.
DEFAULT_POSTING_BUDGET = 60

# `start` is an ITEM offset, not a page number: `&start=10` is page two. The probe pinned the page
# at 10 cards (`&start=10` and `&start=25` each returned 10, all new against `start=0`).
SEARCH_PAGE_SIZE = 10

# Search pages requested per search. 1 is the shipped single-page behaviour and stays the default
# here as well as in `Settings`, so a lane constructed directly in a test sends what it always did.
DEFAULT_SEARCH_PAGES = 1

DEFAULT_HUB_DISTANCE_MILES = 25


class SearchPageError(ValueError):
    """The search response carried no card nodes at all.

    A structural failure -- the fragment moved, or a challenge/error page answered in its place --
    that the runner must see, never a benign zero. Distinct from `FetchFailure` (transport/status).
    Both propagate: a lane is additive breadth, so the runner catches and records rather than the
    lane returning an empty result that reads like a quiet day. The zero-genuine-results shape was
    not pinned by the probe, so this errs LOUD by design (contract §4).
    """


class UnparseableCard(ValueError):
    """A card missing an id, a title, or a company slug -- none of which can be recovered.

    Typed at the raise site rather than signalled by a None return, so the one caller that tolerates
    it -- the grouping pass, which counts it `not_attemptable` and moves on -- says so explicitly.
    """


@dataclass(frozen=True)
class SearchCard:
    """One search-result card, in the fields D-290 recorded as 100/100 complete."""

    job_id: str
    title: str
    company_name: str
    company_slug: str
    location: str
    posted_date: str
    url: str


# One card node and the search page it was found on. The URL rides WITH the node rather than being
# tracked alongside it, so a card can never be attributed to a facet it was not listed under.
_SearchEntry = tuple[str, Node]


@dataclass
class _CompanyCards:
    """One company's cards, and the search page the company was FIRST seen on.

    First-seen rather than every page it appeared on: `BoardSnapshot.url` is a single string, and a
    company listed under three facets has no one truthful list to put there.
    """

    url: str
    cards: list[SearchCard]


def card_nodes(page_html: str) -> list[Node]:
    """The card containers in a guest search fragment: `div.base-card`, one per result.

    The card CONTAINER, and neither the enclosing `<li>` nor `div.base-card[data-entity-urn]`.
    The `<li>` is too loose — a challenge or login FULL page carries generic nav/footer `<li>`
    chrome that is not a card, and a card's own body can nest `<li>`; both would be miscounted as
    seen postings and skew `attempted` / `is_silent_outage`. Keying on the id is too tight — a
    card whose id is missing is still one that was SEEN and must be counted `not_attemptable`, so
    the container class (present on every card) is the unit and `parse_card` reads the id off it.

    Zero containers is a STRUCTURAL failure the runner must see — the fragment moved, or a
    challenge/error page answered in its place — never a benign quiet day.
    """
    nodes = HTMLParser(page_html).css("div.base-card")
    if not nodes:
        raise SearchPageError("no div.base-card card containers in the search fragment")
    return nodes


def parse_card(node: Node) -> SearchCard:
    """Pull the recorded fields out of one card node.

    Raises `UnparseableCard` when the id, title or company slug is absent -- the three fields a
    posting cannot be keyed or shown without. Location and date are allowed to be blank; a posting
    with no location is still rankable (it fails OPEN through the hard US gate, same as any
    unclassifiable location), and a missing date is not fatal.
    """
    job_id = _urn_job_id(node)
    title = _text(node.css_first("h3.base-search-card__title"))
    anchor = node.css_first("h4.base-search-card__subtitle a")
    company_name = _text(anchor)
    company_slug = _company_slug(anchor.attributes.get("href") if anchor else None)
    if not (job_id and title and company_slug):
        raise UnparseableCard(
            f"card missing id/title/company slug: id={job_id!r} title={title!r} "
            f"slug={company_slug!r}"
        )
    link = node.css_first("a.base-card__full-link")
    return SearchCard(
        job_id=job_id,
        title=title,
        company_name=company_name,
        company_slug=company_slug,
        location=_text(node.css_first("span.job-search-card__location")),
        posted_date=_time_attr(node.css_first("time")),
        url=(link.attributes.get("href") or "").strip() if link else "",
    )


def job_posting_url(job_id: str) -> str:
    return f"{_JOB_POSTING_URL}{job_id}"


def search_urls(facets: Sequence[str]) -> tuple[str, ...]:
    """One keyword search per facet, in order, or the unfaceted search when there are no facets.

    This builder creates facet and unfaceted searches, which omit `location` and `distance`. The
    endpoint honors those parameters for the separate explicit hub-net builder below.

    `quote` with no safe characters keeps a facet inside the one parameter it belongs to. A title
    arriving with an `&` in it would otherwise append a parameter of its own and reshape the
    request -- the facets come from user profile data, which no module here gets to assume about.

    The no-facet fallback is the behaviour that shipped, and it is a fallback rather than an error
    because a profile naming no target titles is a legitimate profile: it is what every user has
    before onboarding fills one in.
    """
    if not facets:
        return (SEARCH_URL,)
    return tuple(
        f"{_SEARCH_ENDPOINT}?keywords={quote(facet, safe='')}&{_RECENCY_PARAM}"
        for facet in facets
    )


def search_net_url(term: str, hub: str, distance_miles: int) -> str:
    """One geo-pinned keyword search, with the endpoint's parameters in contract order."""
    return (
        f"{_SEARCH_ENDPOINT}?keywords={quote(term, safe='')}&location={quote(hub, safe='')}&"
        f"distance={distance_miles}&{_RECENCY_PARAM}"
    )


def page_url(search_url: str, page_index: int) -> str:
    """`search_url` at page `page_index`, as the ITEM offset `start=` actually takes.

    **Page 0 is the URL UNCHANGED, not `&start=0`.** With `lane_search_pages` at its default of 1
    the lane must request byte-identically what it requested before paging existed, so that the
    knob's default moves no user's request shape and not merely their request count. `&start=0`
    was never probed and asserting it is equivalent would be inventing a response.

    The endpoint honors `location=` with `distance=` for a configured hub net, so those parameters
    are already present when this function receives a net URL. Facet and unfaceted URLs omit them
    by construction, preserving their existing request shapes. `f_WT=2` remains measured as
    id-identical to the unfiltered set and is never sent.
    """
    if page_index <= 0:
        return search_url
    return f"{search_url}&start={page_index * SEARCH_PAGE_SIZE}"


class LinkedInLane:
    name = LANE_NAME

    def __init__(
        self,
        posting_budget: int = DEFAULT_POSTING_BUDGET,
        search_facets: Sequence[str] = (),
        search_pages: int = DEFAULT_SEARCH_PAGES,
        search_nets: Sequence[tuple[str, str]] = (),
        hub_distance_miles: int = DEFAULT_HUB_DISTANCE_MILES,
    ) -> None:
        self._posting_budget = posting_budget
        # Injected rather than read here: the facets are derived from the user's profile row, which
        # lives in the store, and a lane must not reach into the store for its own configuration.
        self._search_facets = tuple(search_facets)
        # At most this many search pages per search. Clamped at 1 rather than trusted: `Settings`
        # already floors it, but a lane constructed directly with 0 would fetch no search page at
        # all and report an empty run as a quiet day.
        self._search_pages = max(1, search_pages)
        self._search_nets = tuple(search_nets)
        self._hub_distance_miles = hub_distance_miles

    def collect(self, fetcher: Fetcher, admits: CompanyAdmission) -> LaneResult:
        """One search GET per configured facet or hub net, then one body GET per posting at an
        admitted company.

        `admits` is asked once per distinct `(linkedin, slug)`, in first-seen order, BEFORE any body
        is fetched -- the protocol's contract, and the only ordering under which the per-run company
        cap saves requests instead of discarding paid-for ones.
        """
        entries, search_pages = self._search(fetcher)

        tally = AcquisitionTally()
        by_company = _group_by_company(entries, tally)
        snapshots: list[LaneCompanySnapshot] = []
        remaining = self._posting_budget
        for slug, company in by_company.items():
            if not admits(LANE_PROVIDER, slug):
                # Nothing tallied for a refused company: no request was attempted, and an outcome
                # here would inflate `attempted` with non-attempts. Refusals are reported by name
                # through `admission.CompanyBudget.refused`.
                continue
            postings: list[RawPosting] = []
            for card in company.cards:
                if remaining <= 0:
                    # Seen, not requested. `not_attemptable` is the closed catalog's only member
                    # meaning that; a silent drop is what the catalog exists to prevent.
                    tally.record("not_attemptable")
                    continue
                remaining -= 1
                posting = self._fetch_posting(fetcher, card, tally)
                if posting is not None:
                    postings.append(posting)
            if postings:
                # A company whose every body was refused yields no snapshot: an empty one would
                # still write a `board_scans` row and oblige a company row for zero postings.
                snapshots.append(
                    LaneCompanySnapshot(
                        provider=LANE_PROVIDER,
                        slug=slug,
                        name=company.cards[0].company_name or slug,
                        # The search page this company was actually found on. Citing the unfaceted
                        # URL would name a page a faceted run never requested.
                        snapshot=lane_snapshot(postings, company.url),
                    )
                )
        return LaneResult(snapshots=tuple(snapshots), tally=tally, search_pages=search_pages)

    def _search(self, fetcher: Fetcher) -> tuple[list[_SearchEntry], tuple[tuple[str, int], ...]]:
        """Every configured search page, its card nodes paired with the URL they came from.

        The result is INTERLEAVED across searches, round-robin, and that is load-bearing rather than
        tidy. The body budget is spent in iteration order, so concatenating instead would let the
        first search consume all of it and every later target title or hub contribute nothing.
        Paging does not change that: a search's own pages are read in order and the interleave is
        across searches, so search two's page 1 is still worked before search one's page 2.

        The second return value is how many pages were actually fetched per search, which is
        REPORTED rather than inferred: a search that stopped at page 2 of a 5-page ceiling ran out
        of results, and a search that filled every page is truncated. Those are different facts
        about the same posting count, and only the first is benign.
        """
        urls = search_urls(self._search_facets) + tuple(
            search_net_url(term, hub, self._hub_distance_miles)
            for term, hub in self._search_nets
        )
        if not self._search_facets and not self._search_nets:
            # The unfaceted fallback keeps the single-search contract it shipped with: a transport
            # or structural failure on its FIRST page propagates, because with one facet there are
            # no other results for it to cost, and `card_nodes`' own message is the most specific
            # one available.
            entries, pages = self._facet_pages(fetcher, urls[0])
            return entries, ((urls[0], pages),)

        per_search: list[list[_SearchEntry]] = []
        page_counts: list[tuple[str, int]] = []
        failed = 0
        for url in urls:
            try:
                entries, pages = self._facet_pages(fetcher, url)
            except (FetchFailure, SearchPageError):
                # Per-search isolation, the same shape D-307 gave a board's apply failure inside a
                # scan. One search per target title or hub net means a run makes many, so the
                # seventh must not discard the six already paid for; the fetcher has retried with
                # the time it raises, so this is a surviving failure rather than a blip.
                # `SearchPageError` belongs here too: `card_nodes` raises it on a page with no
                # cards, and one keyword matching nothing is a profile-data matter -- raising
                # would let a single odd target title disable the whole lane. Isolation must not
                # become suppression, which is what the all-empty check below is for.
                failed += 1
                per_search.append([])
                page_counts.append((url, 0))
                continue
            per_search.append(entries)
            page_counts.append((url, pages))

        if not any(per_search):
            # Not a quiet day, and the tally cannot see it either: with no cards nothing is ever
            # attempted, so `is_silent_outage` stays False and the lane reports a clean run with no
            # postings forever -- the prior art's 11-run silent outage. The all-FAILED case is the
            # same guard on purpose, and both counts are named so a host refusing us stays
            # distinguishable from a profile whose target titles match nothing.
            raise SearchPageError(
                "every keyword facet or hub net yielded nothing "
                f"({len(per_search)} searched, {failed} "
                "request failures): the card fragment has moved, the host is refusing us, or "
                "none of the profile's target titles match a posting"
            )
        interleaved = [
            entry for row in zip_longest(*per_search) for entry in row if entry is not None
        ]
        return interleaved, tuple(page_counts)

    def _facet_pages(self, fetcher: Fetcher, url: str) -> tuple[list[_SearchEntry], int]:
        """One facet's cards over at most `self._search_pages` pages, and the pages fetched.

        **A PAGE WITH NO CARDS MEANS TWO DIFFERENT THINGS AND THIS IS WHERE THEY SEPARATE.** On
        the FIRST page it is `card_nodes`' structural failure -- the fragment moved, or a
        challenge or error page answered in its place -- and it still propagates, unweakened, to
        the caller that has always handled it. On a LATER page it is the ordinary end of a
        facet's result set: a keyword matching 23 postings has no page 3, so every facet shorter
        than the ceiling would otherwise raise and a normal run would read as an outage the
        moment the ceiling rose above 1. Same split for `FetchFailure`: a facet whose first page
        is refused has produced nothing and is a failure the caller must count, while one refused
        on page 4 keeps the three pages already paid for.

        A full page that adds no new posting id ends the facet too. That is the offset-wrap tail
        `providers/workday.py` guards for the same reason: a host that answers past the end of a
        result set with a REPEAT page rather than an empty one would burn every remaining page on
        cards already held. Repeats within a facet are dropped here rather than carried, because
        they are a server artifact and not a second listing -- unlike the same posting appearing
        under two different facets, which is a real listing and stays counted `not_attemptable`
        by `_group_by_company`.

        The entry carries the PAGE's URL, not the facet's first page. It is a URL this run
        actually requested, which is the whole standard `BoardSnapshot.url` provenance is held to.
        """
        entries: list[_SearchEntry] = []
        seen: set[str] = set()
        pages = 0
        for page_index in range(self._search_pages):
            page = page_url(url, page_index)
            try:
                result = fetcher.get(page)
                nodes = card_nodes(result.content.decode("utf-8", "replace"))
            except (FetchFailure, SearchPageError):
                if page_index == 0:
                    raise
                break
            pages += 1
            fresh = [
                (page, node)
                for node in nodes
                if (job_id := _urn_job_id(node)) == "" or job_id not in seen
            ]
            new_ids = {
                job_id for node in nodes if (job_id := _urn_job_id(node)) and job_id not in seen
            }
            entries.extend(fresh)
            seen |= new_ids
            if not new_ids:
                # No id on this page was one this facet had not already listed. Either the host
                # is serving the wrap tail, or every card on it is unparseable; in both cases a
                # further page is a request spent on nothing.
                break
        return entries, pages

    def _fetch_posting(
        self, fetcher: Fetcher, card: SearchCard, tally: AcquisitionTally
    ) -> RawPosting | None:
        try:
            result = fetcher.get(job_posting_url(card.job_id))
        except FetchFailure as exc:
            tally.record(_failure_outcome(exc))
            return None
        body_text, rejection = assess_body(_description(result.content), title=card.title)
        if rejection is not None:
            tally.record(rejection.outcome)
            return None
        tally.record("body_fetched")
        return _raw_posting(card, body_text=body_text)


def _group_by_company(
    entries: list[_SearchEntry], tally: AcquisitionTally
) -> dict[str, _CompanyCards]:
    """Cards bucketed by company slug, first-seen order preserved.

    Grouping by slug rather than display name is the point the `NAME_COLLISION_CARDS` trap makes: a
    name-keyed group applies two employers' postings against one `company_id`. An unparseable card,
    or a second card resolving to a posting already taken this run, is counted `not_attemptable` and
    dropped here rather than raised -- one malformed row must not cost the others, and the duplicate
    drop is not tidiness: without it the run aborts. `apply.py` snapshots `existing` once before its
    loop, so two rows with one `provider_posting_id` both take the INSERT branch and the second
    violates UNIQUE(company_id, provider_posting_id) inside `apply_board`'s single transaction,
    rolling the whole board back and taking every later company's results with it. An aggregator MAY
    serve one posting twice; every ATS provider enumerates a board once and may assume distinct ids.
    Two facets returning one posting is the ordinary case of that -- `software engineer` and
    `backend engineer` overlap by design -- so the same `seen` set spends one body GET on it, not
    two, and the second listing is counted rather than dropped in silence.
    """
    grouped: dict[str, _CompanyCards] = {}
    seen: set[tuple[str, str]] = set()
    for url, node in entries:
        try:
            card = parse_card(node)
        except UnparseableCard:
            tally.record("not_attemptable")
            continue
        key = (card.company_slug, card.job_id)
        if key in seen:
            tally.record("not_attemptable")
            continue
        seen.add(key)
        group = grouped.setdefault(card.company_slug, _CompanyCards(url, []))
        group.cards.append(card)
    return grouped


def _raw_posting(card: SearchCard, *, body_text: str) -> RawPosting:
    return RawPosting(
        provider_posting_id=card.job_id,
        title=card.title,
        # The LinkedIn job-view URL -- the only URL a card exposes. There is no employer apply URL.
        url=card.url,
        locations=[card.location] if card.location else [],
        # `remote_policy` stays `unknown`: `f_WT` is silently ignored, so no reliable remote signal
        # is available and unknown is the honest default.
        posted_at=_parse_posted_at(card.posted_date),
        body_text=body_text,
        raw_json={"card": asdict(card)},
    )


def _description(content: bytes) -> str:
    """The `.show-more-less-html__markup` body -- the field the search omits.

    `Node.html` is the div's OUTER HTML (the wrapper div included), which is harmless here: it is
    handed straight to `assess_body`, whose `html_to_text` drops every tag. An absent markup div
    returns "" rather than raising: `assess_body` then reports `extracted_empty`, the catalog's
    name for "a response arrived and extraction produced nothing".
    """
    node = HTMLParser(content.decode("utf-8", "replace")).css_first(
        "div.show-more-less-html__markup"
    )
    return node.html or "" if node is not None else ""


def _failure_outcome(exc: FetchFailure) -> AcquisitionOutcome:
    """Status -> outcome. A transport failure has no status and is `fetch_unavailable`.

    Kept apart because they mean different things to a reader: 403 is the host refusing us, 404 is a
    posting gone, a timeout is neither. Folding them is how the prior art hid an eleven-day outage.
    """
    if exc.status_code in (401, 403):
        return "fetch_refused"
    if exc.status_code in (404, 410):
        return "fetch_gone"
    return "fetch_unavailable"


def _urn_job_id(node: Node) -> str:
    """The posting id from `data-entity-urn="urn:li:jobPosting:{id}"`, never from the URL tail.

    Read off the card container itself, falling back to a descendant so the parser survives the
    attribute sitting one level in — `css_first` searches descendants only, not the node itself.
    """
    holder = node if node.attributes.get("data-entity-urn") else node.css_first("[data-entity-urn]")
    urn = (holder.attributes.get("data-entity-urn") or "") if holder is not None else ""
    return urn.rsplit(":", 1)[-1].strip() if "urn:li:jobPosting:" in urn else ""


def _company_slug(href: str | None) -> str:
    """The `{slug}` in `/company/{slug}`, stripped of query and trailing slash."""
    if not href:
        return ""
    parts = [segment for segment in urlsplit(href).path.split("/") if segment]
    if "company" in parts:
        index = parts.index("company")
        if index + 1 < len(parts):
            return parts[index + 1]
    return ""


def _time_attr(node: Node | None) -> str:
    return (node.attributes.get("datetime") or "").strip() if node is not None else ""


def _text(node: Node | None) -> str:
    return node.text(strip=True) if node is not None else ""


def _parse_posted_at(value: str) -> datetime | None:
    """The card's `datetime` as naive UTC.

    The probe recorded it date-only ("2026-08-23"), but it is parsed with `fromisoformat` rather
    than a fixed `%Y-%m-%d`, so a drift to a full ISO timestamp does not silently drop the
    freshness signal for every posting. Naive UTC matches every provider's `posted_at`
    (`core.clock.to_naive_utc`); an aware value would compare unequal against the store's naive
    column. `fromisoformat` reads a date-only string as midnight, so no branch is needed.
    """
    text = value.strip()
    if not text:
        return None
    try:
        return to_naive_utc(datetime.fromisoformat(text.replace("Z", "+00:00")))
    except ValueError:
        return None
