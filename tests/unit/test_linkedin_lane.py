"""lanes.linkedin against the authored payload in `linkedin_shape.py`.

Two halves, and the first exists to make the second worth anything. An authored fixture proves only
what our own code constructs, so before any client behaviour is asserted the fixture's two traps are
checked: the id is the URN's and not the URL tail's, and two cards sharing a display name under two
slugs are two companies. Neither can pass a fixture of merely well-formed cards.

Every request is mocked. Nothing in this file reaches the network -- the lane hits routes
`robots.txt` disallows for Claude by name (D-290), so the suite must never exercise them live.
"""

from __future__ import annotations

import inspect
from dataclasses import replace
from datetime import date
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx
import pytest
import respx
from linkedin_shape import (
    JOB_POSTING_PREFIX,
    NAME_COLLISION_CARDS,
    REVIEW_BY,
    URN_URL_MISMATCH_CARD,
    Card,
    card_html,
    card_html_missing_company,
    card_html_missing_title,
    card_html_missing_urn,
    dup_id_cards,
    job_posting_html,
    search_cards,
    search_page_html,
    view_url,
)

from boardwatch.core.politeness import Fetcher
from boardwatch.core.settings import Settings
from boardwatch.lanes import linkedin
from boardwatch.lanes.base import Lane
from boardwatch.lanes.linkedin import (
    LANE_PROVIDER,
    LinkedInLane,
    SearchPageError,
)

_SEARCH_PREFIX = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"


def _fetcher(tmp_path: Path) -> Fetcher:
    return Fetcher(
        Settings(
            data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1,
            per_host_delay_seconds=0.25,
        )
    )


def _one_card(html: str) -> linkedin.SearchCard:
    (node,) = linkedin.card_nodes(html)
    return linkedin.parse_card(node)


# ---------------------------------------------------------------------------------------
# The fixture traces to the recorded field list, and its two traps have content.
# ---------------------------------------------------------------------------------------


def test_the_authored_payload_reproduces_the_recorded_card_fields():
    """D-290: id, title, company (name + slug), location, ISO date, url -- 100/100 complete."""
    cards = search_cards()
    assert len(cards) == 8
    assert len({c.company_slug for c in cards}) == 4  # 8 postings on 4 companies
    for card in cards:
        parsed = _one_card(card_html(card))
        assert parsed.job_id == card.job_id
        assert parsed.title == card.title
        assert parsed.company_name == card.company_name
        assert parsed.company_slug == card.company_slug
        assert parsed.location == card.location
        assert parsed.posted_date == card.posted_date
        assert parsed.url == view_url(card)
        # The only URL a card exposes is LinkedIn's own job-view URL: `externalApply` is 0, so
        # there is no employer/ATS link, which is why identity rides on the slug.
        assert urlsplit(parsed.url).netloc == "www.linkedin.com"


def test_the_id_is_the_urn_not_the_url_tail():
    """The trap: a card whose view URL ends in a different number than its URN."""
    parsed = _one_card(card_html(URN_URL_MISMATCH_CARD))
    assert parsed.job_id == "4010000900"  # the URN's id
    assert parsed.url.endswith("1234567?refId=aB3&trackingId=xY9")  # the URL's tail differs
    assert "4010000900" not in parsed.url.rsplit("-", 1)[-1]


def test_the_company_slug_is_recovered_from_a_noisy_company_href():
    """The `/company/{slug}` href carries a trailing slash and tracking query on a real card."""
    parsed = _one_card(card_html(search_cards()[0]))
    assert parsed.company_slug == "acme-00"


def test_the_authored_shape_carries_a_review_deadline():
    """R15 in spirit: a shape that still parses can have been overtaken months ago.

    Red here is actionable at arm time: re-confirm the §2 field list and selectors against the live
    guest search, then roll `REVIEW_BY` in `tests/unit/linkedin_shape.py` forward with a reason.
    """
    assert date.today() <= REVIEW_BY, (
        f"the LinkedIn guest shape was last reviewed before {REVIEW_BY}. Re-confirm the contract's "
        "field list and selectors and roll the deadline forward with a reason."
    )


# ---------------------------------------------------------------------------------------
# The client.
# ---------------------------------------------------------------------------------------


def test_the_lane_satisfies_the_protocol():
    assert LinkedInLane.name == "linkedin"
    assert list(inspect.signature(LinkedInLane.collect).parameters) == list(
        inspect.signature(Lane.collect).parameters
    ) == ["self", "fetcher", "admits"]


def _mock_search(cards: list[Card] | None = None, *, html: str | None = None) -> respx.Route:
    page = html if html is not None else search_page_html(cards)
    return respx.get(url__startswith=_SEARCH_PREFIX).mock(
        return_value=httpx.Response(200, text=page)
    )


def _mock_bodies(cards: list[Card], status: int = 200) -> respx.Route:
    by_id = {card.job_id: card for card in cards}

    def _respond(request: httpx.Request) -> httpx.Response:
        job_id = request.url.path.rsplit("/", 1)[-1]
        card = by_id.get(job_id)
        if card is None or status != 200:
            return httpx.Response(status if card is not None else 404, text="")
        return httpx.Response(200, text=job_posting_html(card))

    return respx.get(url__startswith=JOB_POSTING_PREFIX).mock(side_effect=_respond)


@respx.mock
def test_admits_is_asked_once_per_distinct_company_never_once_per_posting(tmp_path):
    """8 postings sit on 4 companies; the cap counts companies, not postings."""
    cards = search_cards()
    search = _mock_search(cards)
    bodies = _mock_bodies(cards)
    asked: list[tuple[str, str]] = []

    def _admits(provider: str, slug: str) -> bool:
        asked.append((provider, slug))
        return False

    result = LinkedInLane().collect(_fetcher(tmp_path), _admits)

    assert len(asked) == 4
    assert set(asked) == {(LANE_PROVIDER, f"acme-{i:02d}") for i in range(4)}
    # Refusal is free: no body paid for, one search GET, not two.
    assert search.call_count == 1
    assert bodies.call_count == 0
    assert result.snapshots == ()
    assert result.tally.attempted == 0
    assert result.tally.is_silent_outage is False


@respx.mock
def test_one_search_get_and_one_body_get_per_admitted_posting(tmp_path):
    cards = search_cards()
    search = _mock_search(cards)
    bodies = _mock_bodies(cards)
    wanted = (LANE_PROVIDER, "acme-00")

    result = LinkedInLane().collect(
        _fetcher(tmp_path), lambda provider, slug: (provider, slug) == wanted
    )

    assert search.call_count == 1  # the lane makes one search GET; paging is deferred (contract §4)
    assert bodies.call_count == 2  # two postings at the one admitted company
    assert result.tally.counts["body_fetched"] == 2
    assert result.tally.resolved == 2
    assert result.tally.is_silent_outage is False

    (snapshot,) = result.snapshots
    assert (snapshot.provider, snapshot.slug) == wanted
    assert snapshot.name == "Acme 00"
    assert snapshot.snapshot.status == "partial"  # never `complete`; an empty one closes a board
    assert len(snapshot.snapshot.postings) == 2


@respx.mock
def test_a_posting_carries_the_view_url_location_title_and_urn_id(tmp_path):
    cards = search_cards()
    _mock_search(cards)
    _mock_bodies(cards)
    first = cards[0]

    result = LinkedInLane().collect(
        _fetcher(tmp_path), lambda provider, slug: slug == "acme-00"
    )
    posting = next(
        p for s in result.snapshots for p in s.snapshot.postings
        if p.provider_posting_id == first.job_id
    )

    assert posting.url == view_url(first)  # the job-view URL, the only one exposed
    assert posting.title == first.title
    assert posting.locations == [first.location]
    # The title appears in the body prose, not as a synthetic leading heading (see the fixture's
    # note): the real body carries no title line, so asserting `startswith` would test only what
    # the fixture constructs.
    assert first.title.lower() in posting.body_text.lower()
    assert posting.posted_at is not None
    assert posting.posted_at.date().isoformat() == first.posted_date
    assert posting.remote_policy == "unknown"


@respx.mock
def test_two_cards_sharing_a_name_under_two_slugs_form_two_companies(tmp_path):
    """The trap: grouping by display name would collapse two employers into one."""
    _mock_search(NAME_COLLISION_CARDS)
    _mock_bodies(NAME_COLLISION_CARDS)

    result = LinkedInLane().collect(_fetcher(tmp_path), lambda provider, slug: True)

    assert {(s.provider, s.slug) for s in result.snapshots} == {
        (LANE_PROVIDER, "vertex-analytics"),
        (LANE_PROVIDER, "vertex-robotics"),
    }


@respx.mock
def test_the_posting_budget_caps_body_gets_and_counts_what_it_skipped(tmp_path):
    cards = search_cards()
    _mock_search(cards)
    bodies = _mock_bodies(cards)

    result = LinkedInLane(posting_budget=1).collect(
        _fetcher(tmp_path), lambda provider, slug: slug == "acme-00"
    )

    assert bodies.call_count == 1
    assert result.tally.counts["body_fetched"] == 1
    # Seen and not requested is counted, never dropped silently.
    assert result.tally.counts["not_attemptable"] == 1
    assert result.tally.attempted == 2


@respx.mock
@pytest.mark.parametrize(
    "status,outcome",
    [(403, "fetch_refused"), (404, "fetch_gone"), (418, "fetch_unavailable")],
)
def test_a_failed_body_lands_in_its_own_bucket(tmp_path, status, outcome):
    """Folding these is exactly how the prior art hid an eleven-day outage."""
    cards = search_cards()
    _mock_search(cards)
    _mock_bodies(cards, status=status)

    result = LinkedInLane().collect(
        _fetcher(tmp_path), lambda provider, slug: slug == "acme-00"
    )

    assert result.tally.counts[outcome] == 2
    assert result.tally.resolved == 0
    assert result.tally.is_silent_outage is True
    # A company whose every body failed writes no snapshot, so no company row is owed for it.
    assert result.snapshots == ()


@respx.mock
def test_a_login_wall_body_is_rejected_rather_than_stored(tmp_path):
    cards = search_cards()[:1]
    _mock_search(cards)
    respx.get(url__startswith=JOB_POSTING_PREFIX).mock(
        return_value=httpx.Response(
            200,
            text=job_posting_html(
                cards[0],
                body="<h2>Sign in to continue</h2><p>You must be logged in. "
                "Create an account.</p>",
            ),
        )
    )

    result = LinkedInLane().collect(_fetcher(tmp_path), lambda provider, slug: True)

    assert result.tally.counts["rejected_login_wall"] == 1
    assert result.snapshots == ()


@respx.mock
def test_a_body_with_no_markup_div_is_extracted_empty(tmp_path):
    cards = search_cards()[:1]
    _mock_search(cards)
    respx.get(url__startswith=JOB_POSTING_PREFIX).mock(
        return_value=httpx.Response(200, text="<section>no markup div here</section>")
    )

    result = LinkedInLane().collect(_fetcher(tmp_path), lambda provider, slug: True)

    assert result.tally.counts["extracted_empty"] == 1


@respx.mock
@pytest.mark.parametrize(
    "builder", [card_html_missing_urn, card_html_missing_title, card_html_missing_company]
)
def test_a_card_missing_its_urn_title_or_company_is_counted_not_dropped(tmp_path, builder):
    """One malformed card must not cost the others; it is counted, never dropped silently."""
    broken = builder(search_cards()[0])
    search = _mock_search(html=search_page_html([]).replace("</ul>", f"{broken}</ul>"))
    bodies = _mock_bodies(search_cards())

    result = LinkedInLane().collect(_fetcher(tmp_path), lambda provider, slug: True)

    assert search.call_count == 1
    assert bodies.call_count == 0  # never fetched
    assert result.tally.counts["not_attemptable"] == 1
    assert result.snapshots == ()


@respx.mock
def test_a_second_card_with_the_same_id_is_dropped_before_its_body(tmp_path):
    """An aggregator MAY serve one posting twice; the second must not reach `apply_board`."""
    cards = dup_id_cards()
    _mock_search(cards)
    bodies = _mock_bodies(cards)

    result = LinkedInLane().collect(_fetcher(tmp_path), lambda provider, slug: True)

    assert bodies.call_count == 1
    assert result.tally.counts["body_fetched"] == 1
    assert result.tally.counts["not_attemptable"] == 1


@pytest.mark.parametrize(
    "page",
    [
        "<html><body>no cards here</body></html>",
        "<html><body><ul class='jobs-search__results-list'></ul></body></html>",
    ],
)
def test_a_search_page_with_no_cards_raises_instead_of_returning_nothing(page):
    """No card nodes is a structural failure the runner must see, not a quiet day."""
    with pytest.raises(SearchPageError):
        linkedin.card_nodes(page)


def test_a_full_page_with_stray_list_items_but_no_cards_raises():
    """A challenge/error/login full page carries generic `<li>` nav/footer chrome but no job
    card. It must not read as a quiet day of bad cards: with no card container present,
    `card_nodes` raises so the runner sees the failure. Selecting `<li>` globally would find the
    chrome, return zero snapshots, and mask a refusal as an empty result."""
    page = (
        "<html><body><nav><ul>"
        "<li><a href='/'>Home</a></li><li><a href='/jobs'>Jobs</a></li>"
        "</ul></nav><main><p>Please verify you are human.</p>"
        "<ul><li>Help</li><li>Privacy</li></ul></main></body></html>"
    )
    with pytest.raises(SearchPageError):
        linkedin.card_nodes(page)


@respx.mock
def test_a_full_iso_datetime_on_a_card_still_parses_posted_at(tmp_path):
    """LinkedIn's `time[datetime]` may drift from the recorded date-only form to a full ISO
    timestamp. `posted_at` must survive that rather than silently going None and losing the
    freshness signal across the whole lane."""
    card = replace(search_cards()[0], posted_date="2026-08-23T00:00:00.000Z")
    _mock_search([card])
    _mock_bodies([card])

    result = LinkedInLane().collect(_fetcher(tmp_path), lambda provider, slug: True)
    posting = result.snapshots[0].snapshot.postings[0]

    assert posting.posted_at is not None
    assert posting.posted_at.date().isoformat() == "2026-08-23"


def test_the_job_posting_url_is_built_from_the_id():
    assert linkedin.job_posting_url("4010000001") == (
        "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/4010000001"
    )


def test_the_lane_is_registered_but_off_by_default(tmp_path):
    """Registered makes it reachable; enabled runs it. D-290: it ships off and not armed.

    The factory's second argument is the run's facets, and they are asserted through it rather
    than only on the constructor: a registry row that dropped them would leave every unit test
    here green while the live lane searched the general labour market.
    """
    from boardwatch.pipeline.runner import LANE_FACTORIES

    settings = Settings(data_dir=tmp_path, config_dir=tmp_path, lane_posting_budget=7)
    assert "linkedin" in LANE_FACTORIES
    built = LANE_FACTORIES["linkedin"](settings, ("software-engineer",))
    assert isinstance(built, LinkedInLane)
    assert built._posting_budget == 7
    assert built._search_facets == ("software-engineer",)
    # Off by default: nothing in the registry runs until an operator names it.
    assert "linkedin" not in settings.lanes_enabled


# ---------------------------------------------------------------------------------------
# The keyword facet -- contract §5's deferred half, probed live 2026-08-26.
#
# `keywords=` is honoured, and the evidence is an id set rather than a plausible-looking page:
# the faceted search returned 10 software roles at 9 named employers and shared ZERO of 10 ids
# with the unfaceted search, whose 10 cards were dishwasher, crew member, cleaner and bar back.
# `location=` is silently ignored -- id-identical to no-location, exactly like `f_WT=2` -- so it
# must never be sent, which is why the URL builder is asserted on the string it builds.
# ---------------------------------------------------------------------------------------


def _facet_url(facet: str) -> str:
    """The faceted search URL, built here rather than by calling `search_urls`.

    Independent of the builder on purpose: a routing test that asked the implementation for the
    URL it was about to assert would agree with any URL the implementation chose, including one
    carrying `location=`.
    """
    return f"{_SEARCH_PREFIX}?keywords={quote(facet, safe='')}&f_TPR=r86400"


def _mock_facet(facet: str, cards: list[Card] | None) -> respx.Route:
    """One facet's search page. `None` is the no-card page, which `card_nodes` refuses."""
    return respx.get(_facet_url(facet)).mock(
        return_value=httpx.Response(
            200, text=search_page_html(cards if cards is not None else [])
        )
    )


def _mock_facet_refused(facet: str, status: int = 403) -> respx.Route:
    """One facet's search REFUSED. The fetcher raises `FetchFailure` for it, not `SearchPageError`.

    403 rather than a timeout because it is the failure this host actually threatens: the guest
    routes are the ones `robots.txt` disallows, so a refusal is the expected way for one request
    in a run to die.
    """
    return respx.get(_facet_url(facet)).mock(return_value=httpx.Response(status, text=""))


def _one_card_per_company(prefix: str, id_base: int, count: int) -> list[Card]:
    """`count` cards at `count` DISTINCT companies, so the group order is the card order.

    Distinct companies are what makes an interleave observable at all: `_group_by_company`
    collapses a facet's cards by slug and the budget is spent company by company, so a fixture
    with several postings per company reads the same either way round.
    """
    return [
        Card(
            job_id=str(id_base + index),
            title="Backend Engineer",
            company_name=f"{prefix.title()} {index:02d}",
            company_slug=f"{prefix}-{index:02d}",
            location="Austin, TX",
            posted_date="2026-08-23",
        )
        for index in range(count)
    ]


def test_a_facet_becomes_a_keywords_query_and_never_a_location_one():
    """`keywords=` is honoured (0 of 10 ids shared with the unfaceted set); `location=` is not.

    A silently ignored parameter is worse than an absent one: the run would report that it had
    constrained the search to the US while the response was the same one no-location returns.
    """
    urls = linkedin.search_urls(("software engineer", "site reliability engineer"))

    assert urls == (
        "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
        "?keywords=software%20engineer&f_TPR=r86400",
        "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
        "?keywords=site%20reliability%20engineer&f_TPR=r86400",
    )
    assert not any("location" in url or "start=" in url for url in urls)


def test_no_facets_falls_back_to_the_search_url_that_shipped():
    """A profile that names no target titles is a legitimate profile, not an error."""
    assert linkedin.search_urls(()) == (linkedin.SEARCH_URL,)


def test_the_facets_are_a_second_keyword_argument_and_stored_as_a_tuple():
    """`collect`'s parameter list belongs to the protocol, so the facets are constructor state.

    Position is asserted because the runner's factory passes `posting_budget` by name and a
    facet argument that landed in front of it would still typecheck.
    """
    assert list(inspect.signature(LinkedInLane.__init__).parameters) == [
        "self",
        "posting_budget",
        "search_facets",
    ]
    assert LinkedInLane(search_facets=["software engineer"])._search_facets == (
        "software engineer",
    )


@respx.mock
def test_one_search_per_facet_and_the_unfaceted_url_is_never_requested(tmp_path):
    """The whole point of the feature: the general labour market is not fetched at all."""
    cards = search_cards()
    root = respx.get(linkedin.SEARCH_URL).mock(
        return_value=httpx.Response(200, text=search_page_html(cards))
    )
    swe = _mock_facet("software engineer", cards[:4])
    data = _mock_facet("data engineer", cards[4:])
    _mock_bodies(cards)

    LinkedInLane(search_facets=("software engineer", "data engineer")).collect(
        _fetcher(tmp_path), lambda provider, slug: True
    )

    assert (swe.call_count, data.call_count) == (1, 1)
    assert root.call_count == 0


@respx.mock
def test_cards_from_several_facets_are_interleaved_round_robin(tmp_path):
    """Round-robin, not concatenated: the order the companies are worked in IS the order the
    body budget is spent in, so concatenating puts every later target title behind the first
    facet's entire yield.
    """
    first = _one_card_per_company("acme", 4_020_000_000, 3)
    second = _one_card_per_company("beacon", 4_020_001_000, 3)
    _mock_facet("software engineer", first)
    _mock_facet("data engineer", second)
    _mock_bodies(first + second)

    result = LinkedInLane(search_facets=("software engineer", "data engineer")).collect(
        _fetcher(tmp_path), lambda provider, slug: True
    )

    assert [snapshot.slug for snapshot in result.snapshots] == [
        "acme-00",
        "beacon-00",
        "acme-01",
        "beacon-01",
        "acme-02",
        "beacon-02",
    ]


@respx.mock
def test_the_body_budget_reaches_every_facet_not_just_the_first(tmp_path):
    """The consequence the interleave exists for. Concatenated, facet one eats the whole budget
    and the lane reports fourteen facets while delivering only the profile's first title.
    """
    first = _one_card_per_company("acme", 4_020_000_000, 3)
    second = _one_card_per_company("beacon", 4_020_001_000, 3)
    _mock_facet("software engineer", first)
    _mock_facet("data engineer", second)
    _mock_bodies(first + second)

    result = LinkedInLane(
        posting_budget=2, search_facets=("software engineer", "data engineer")
    ).collect(_fetcher(tmp_path), lambda provider, slug: True)

    fetched = {
        posting.provider_posting_id
        for snapshot in result.snapshots
        for posting in snapshot.snapshot.postings
    }
    assert len(fetched) == 2
    assert fetched & {card.job_id for card in first}
    assert fetched & {card.job_id for card in second}, "one facet took the entire body budget"


@respx.mock
def test_a_card_listed_under_two_facets_costs_one_body_get_not_two(tmp_path):
    """Overlapping facets are normal -- `software engineer` and `backend engineer` return the
    same posting -- and a second body GET for it is both a paid-for duplicate and the crash
    this repo already had to fix: two rows with one `provider_posting_id` violate
    UNIQUE(company_id, provider_posting_id) inside one transaction and roll the board back.
    """
    cards = search_cards()[:2]
    _mock_facet("software engineer", cards)
    _mock_facet("backend engineer", cards)
    bodies = _mock_bodies(cards)

    result = LinkedInLane(search_facets=("software engineer", "backend engineer")).collect(
        _fetcher(tmp_path), lambda provider, slug: True
    )

    assert bodies.call_count == 2
    assert result.tally.counts["body_fetched"] == 2
    # Seen on the second facet and not requested again. A silent drop is what the catalog exists
    # to prevent.
    assert result.tally.counts["not_attemptable"] == 2
    stored = [
        posting.provider_posting_id
        for snapshot in result.snapshots
        for posting in snapshot.snapshot.postings
    ]
    assert len(stored) == len(set(stored)) == 2


@respx.mock
def test_the_snapshot_cites_the_facet_url_the_company_was_first_seen_on(tmp_path):
    """Provenance has to name a URL the run actually requested, and `BoardSnapshot.url` is one
    string -- so a company found under two facets records the first, never the unfaceted root.
    """
    shared = search_cards()[:1]
    only_second = _one_card_per_company("beacon", 4_020_001_000, 1)
    _mock_facet("software engineer", shared)
    _mock_facet("data engineer", shared + only_second)
    _mock_bodies(shared + only_second)

    result = LinkedInLane(search_facets=("software engineer", "data engineer")).collect(
        _fetcher(tmp_path), lambda provider, slug: True
    )
    urls = {snapshot.slug: snapshot.snapshot.url for snapshot in result.snapshots}

    assert urls["acme-00"] == _facet_url("software engineer")
    assert urls["beacon-00"] == _facet_url("data engineer")
    assert linkedin.SEARCH_URL not in urls.values()


@respx.mock
def test_every_facet_returning_no_cards_raises_instead_of_reporting_a_quiet_day(tmp_path):
    """The outage case, and the reason it cannot be left to the tally.

    If the card fragment moves or a challenge page answers, every facet comes back with no
    cards, nothing was ever attempted, and `is_silent_outage` stays False -- so the lane would
    report a clean quiet day forever, which is the prior art's 11-run silent outage.
    """
    _mock_facet("software engineer", None)
    _mock_facet("data engineer", None)
    bodies = _mock_bodies([])

    with pytest.raises(SearchPageError, match="facet"):
        LinkedInLane(search_facets=("software engineer", "data engineer")).collect(
            _fetcher(tmp_path), lambda provider, slug: True
        )

    assert bodies.call_count == 0


@respx.mock
def test_one_facet_whose_request_fails_does_not_cost_the_others_their_results(tmp_path):
    """Per-facet isolation, the same shape D-307 gave a board's apply failure inside a scan.

    One search per target title means a run makes many, and letting the seventh propagate throws
    away the six facets' results already paid for. The fetcher has retried with backoff before it
    raises, so the failure is a surviving one, not a blip worth aborting a run over.
    """
    cards = search_cards()[:2]
    refused = _mock_facet_refused("software engineer")
    survivor = _mock_facet("data engineer", cards)
    bodies = _mock_bodies(cards)

    result = LinkedInLane(search_facets=("software engineer", "data engineer")).collect(
        _fetcher(tmp_path), lambda provider, slug: True
    )

    assert (refused.call_count, survivor.call_count) == (1, 1)
    assert bodies.call_count == 2
    assert result.tally.counts["body_fetched"] == 2
    # The surviving facet's postings are kept, and they cite the page they were found on.
    assert {snapshot.snapshot.url for snapshot in result.snapshots} == {
        _facet_url("data engineer")
    }


@respx.mock
def test_every_facet_request_failing_raises_rather_than_reporting_a_quiet_day(tmp_path):
    """Isolation must not become suppression: swallowing per facet and stopping there would turn
    a host that refuses every request into a clean run with no postings, which is the outage the
    tally cannot see. The message names both counts so a refusal stays distinguishable from a
    profile whose target titles match nothing.
    """
    _mock_facet_refused("software engineer")
    _mock_facet_refused("data engineer")
    bodies = _mock_bodies([])

    with pytest.raises(SearchPageError, match="2 request failures"):
        LinkedInLane(search_facets=("software engineer", "data engineer")).collect(
            _fetcher(tmp_path), lambda provider, slug: True
        )

    assert bodies.call_count == 0


@respx.mock
def test_one_empty_facet_among_several_is_tolerated_rather_than_fatal(tmp_path):
    """One keyword matching nothing is a profile-data matter, not an outage. Raising here would
    let a single odd target title in a profile disable the whole lane.
    """
    cards = search_cards()[:2]
    _mock_facet("software engineer", cards)
    _mock_facet("zzq not a real role", None)
    _mock_bodies(cards)

    result = LinkedInLane(search_facets=("software engineer", "zzq not a real role")).collect(
        _fetcher(tmp_path), lambda provider, slug: True
    )

    assert result.tally.counts["body_fetched"] == 2
    assert result.tally.is_silent_outage is False


@respx.mock
def test_the_unfaceted_lane_still_raises_on_a_page_with_no_cards(tmp_path):
    """The all-empty raise is gated on there BEING facets, so the shipped behaviour is intact:
    no cards on the one page is still the structural failure the runner must see, and it still
    carries `card_nodes`' own message rather than the facet one.
    """
    _mock_search(html=search_page_html([]))

    with pytest.raises(SearchPageError, match="base-card"):
        LinkedInLane().collect(_fetcher(tmp_path), lambda provider, slug: True)
