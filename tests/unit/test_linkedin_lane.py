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
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

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
    assert posting.body_text.startswith(first.title)
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


def test_the_job_posting_url_is_built_from_the_id():
    assert linkedin.job_posting_url("4010000001") == (
        "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/4010000001"
    )


def test_the_lane_is_registered_but_off_by_default(tmp_path):
    """Registered makes it reachable; enabled runs it. D-290: it ships off and not armed."""
    from boardwatch.pipeline.runner import LANE_FACTORIES

    settings = Settings(data_dir=tmp_path, config_dir=tmp_path, lane_posting_budget=7)
    assert "linkedin" in LANE_FACTORIES
    built = LANE_FACTORIES["linkedin"](settings)
    assert isinstance(built, LinkedInLane)
    assert built._posting_budget == 7
    # Off by default: nothing in the registry runs until an operator names it.
    assert "linkedin" not in settings.lanes_enabled
