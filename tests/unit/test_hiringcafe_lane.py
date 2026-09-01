"""lanes.hiringcafe against the authored payload in `hiringcafe_shape.py`.

Two halves, and the first exists to make the second worth anything. An authored fixture proves
only what our own code constructs, so before any client behaviour is asserted, the fixture is
checked against the counts the live probe recorded — 160 hits, 40 board tokens, the source mix,
8 greenhouse-reachable hits, and a `___` split of `objectID` that disagrees with the explicit
fields on exactly 36 of 160.

Those literals are written HERE, not imported, wherever the point is to catch the generator
drifting. A test that re-derives its expectation from the constant the code under test used
agrees with itself.

Every request is mocked. Nothing in this file reaches the network.
"""

from __future__ import annotations

import inspect
import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import httpx
import pytest
import respx
from hiringcafe_shape import (
    REVIEW_BY,
    ROBOTS_ALLOWED_PREFIX,
    ROBOTS_DISALLOWED_FORMS,
    SUPERSEDED_BY,
    board_token,
    job_description_payload,
    search_hits,
    search_page_html,
)

from boardwatch.core.politeness import Fetcher
from boardwatch.core.settings import Settings
from boardwatch.lanes import hiringcafe
from boardwatch.lanes.base import Lane
from boardwatch.lanes.hiringcafe import SEARCH_URL, HiringCafeLane, SearchPageError, hit_identity

_JD_PREFIX = "https://hiringcafe.com/api/job-description"


def _fetcher(tmp_path: Path) -> Fetcher:
    return Fetcher(
        Settings(
            data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1,
            per_host_delay_seconds=0.25,
        )
    )


def _split_object_id(object_id: str) -> tuple[str, str] | None:
    """The trap, written out: read `(source, board_token)` back out of `objectID`.

    Deliberately the most generous form of the mistake — three segments exactly, positional —
    so that what the tail proves is that NO positional split works, not that a careless one
    does not.
    """
    parts = object_id.split("___")
    return (parts[0], parts[1]) if len(parts) == 3 else None


def _expected_key(hit: dict[str, Any]) -> tuple[str, str]:
    """D2 restated independently of the module under test."""
    if hit["source"] == "grnhse":
        return ("greenhouse", hit["board_token"])
    return ("hiringcafe", f"{hit['source']}:{hit['board_token']}")


# ---------------------------------------------------------------------------------------
# The fixture traces to the probe's recorded counts.
# ---------------------------------------------------------------------------------------


def test_the_authored_payload_reproduces_the_recorded_search_result():
    hits = search_hits()
    assert len(hits) == 160  # contract §1
    assert len({hit["board_token"] for hit in hits}) == 40  # contract §4
    assert Counter(hit["source"] for hit in hits) == {
        "icims2": 36, "oraclecloud": 24, "saashr": 16, "taleo_careersection": 16,
        "fountain": 16, "adprecruiting": 12, "avature": 8, "adhoc": 8,
        "careerplug": 8, "grnhse": 8, "paylocity": 4, "appone_api": 4,
    }
    assert sum(1 for hit in hits if hit["is_expired"]) == 0
    assert sum(1 for hit in hits if not hit["apply_url"]) == 0
    # 8 of 160 = 5.0% reachable today; 95% are not. That ratio IS the lane's justification.
    assert sum(1 for hit in hits if hit["source"] == "grnhse") == 8


def test_every_hit_carries_a_company_name_and_no_body_or_location():
    """Plan §0: `enriched_company_data.name` 159/159; `job_information` has neither."""
    for hit in search_hits():
        assert hit["enriched_company_data"]["name"].strip()
        assert set(hit["job_information"]) == {
            "job_title_raw", "title", "num_views", "viewedByUsers"
        }
        # Location text lives ONLY under v5_processed_job_data; `_geoloc` is coordinates.
        assert set(hit["_geoloc"][0]) == {"lat", "lon"}
        assert hit["v5_processed_job_data"]["workplace_states"]


def test_splitting_object_id_disagrees_with_the_explicit_fields_on_the_recorded_tail():
    """The measured 22.5%, and the reason `objectID` is opaque.

    A fixture of only well-formed hits cannot fail this: the three counter-examples are what
    make the assertion have any content at all.
    """
    hits = search_hits()
    disagreeing = [
        hit for hit in hits
        if _split_object_id(hit["objectID"]) != (hit["source"], hit["board_token"])
    ]
    assert len(disagreeing) == 36
    assert round(100 * len(disagreeing) / len(hits), 1) == 22.5
    assert Counter(hit["source"] for hit in disagreeing) == {
        "taleo_careersection": 16, "fountain": 16, "saashr": 4,
    }


@pytest.mark.parametrize(
    "source,why",
    [
        ("taleo_careersection", "single underscores: a `___` split yields one segment"),
        ("fountain", "the board_token itself contains `___`: four segments"),
        ("saashr", "the objectID differs in case from the board_token"),
    ],
)
def test_each_named_counter_example_is_present_and_defeats_the_split(source, why):
    hits = [
        hit for hit in search_hits()
        if hit["source"] == source
        and _split_object_id(hit["objectID"]) != (hit["source"], hit["board_token"])
    ]
    assert hits, why
    for hit in hits:
        # ...and the lane still keys it correctly, because it never looks at objectID.
        identity = hit_identity(hit)
        assert identity.slug == f"{source}:{hit['board_token']}"
        assert identity.posting_id == hit["objectID"]


def test_a_greenhouse_apply_url_dereferences_to_the_underlying_board():
    """Contract §4's convergence case: 8/160 land on a board a provider already scans."""
    for hit in (h for h in search_hits() if h["source"] == "grnhse"):
        identity = hit_identity(hit)
        assert identity.provider == "greenhouse"
        assert identity.slug == hit["board_token"]
        # The posting id is greenhouse's, NOT the aggregator's opaque key. That is what lets
        # a later board scan converge through UNIQUE(company_id, provider_posting_id).
        assert identity.posting_id == hit["apply_url"].rsplit("/", 1)[-1]
        assert identity.posting_id != hit["objectID"]


def test_the_authored_shape_carries_a_review_deadline():
    """R15 in spirit: a shape that still parses can have been overtaken months ago.

    Red here is actionable with no network beyond the two `curl` commands the contract ends
    with. Confirm the key names and the source mix, then move `REVIEW_BY` in
    `tests/unit/hiringcafe_shape.py` and record the date and reason beside it.

    RE-READ `robots.txt` in the same pass and take the reading to the OWNER. D-393 approves the
    `?searchState=` form for this project over that file's `Disallow`, and an owner ruling is
    the only thing that can renew it -- a widened `Disallow` would not change a single request
    this lane makes, so nothing in the repo would notice on its own.
    """
    assert date.today() <= REVIEW_BY, (
        f"the hiring.cafe shape was last reviewed against the live service before {REVIEW_BY}. "
        "Re-run the contract's two curl commands and roll the deadline forward with a reason."
    )


# ---------------------------------------------------------------------------------------
# The client.
# ---------------------------------------------------------------------------------------


def test_the_lane_satisfies_the_widened_protocol():
    assert HiringCafeLane.name == "hiringcafe"
    assert list(inspect.signature(HiringCafeLane.collect).parameters) == list(
        inspect.signature(Lane.collect).parameters
    ) == ["self", "fetcher", "admits"]


def _search_url(facet: str = "") -> str:
    """The SSR search URL the lane builds for one facet, or the unfaceted one.

    Derived from the module under test on purpose, and ONLY for wiring: what URL is requested
    is asserted against independently written literals in the facet section below. A wiring
    test that re-spelled the URL would fail for the wrong reason every time the state changes.
    """
    return hiringcafe.search_urls((facet,) if facet else ())[0]


def _page(facet: str, index: int) -> str:
    return hiringcafe.page_url(_search_url(facet), index)


def _mock_page(
    facet: str,
    index: int,
    hits: list[dict[str, Any]] | None,
    *,
    is_last_page: bool = False,
) -> respx.Route:
    """One search page. `None` hits means the 200-with-zero-results a bogus facet returns."""
    return respx.get(_page(facet, index)).mock(
        return_value=httpx.Response(
            200,
            text=search_page_html(
                hits if hits is not None else [], page=index, is_last_page=is_last_page
            ),
        )
    )


def _mock_search(hits: list[dict[str, Any]] | None = None) -> respx.Route:
    return _mock_page("", 0, search_hits() if hits is None else hits)


def _mock_bodies(hits: list[dict[str, Any]], status: int = 200) -> respx.Route:
    by_id = {hit["objectID"]: hit for hit in hits}

    def _respond(request: httpx.Request) -> httpx.Response:
        hit = by_id.get(request.url.params["id"])
        if hit is None or status != 200:
            return httpx.Response(status, json={"error": "Job not found."})
        return httpx.Response(200, content=job_description_payload(hit))

    return respx.get(url__startswith=_JD_PREFIX).mock(side_effect=_respond)


@respx.mock
def test_admits_is_asked_once_per_distinct_company_never_once_per_posting(tmp_path):
    """D1's contract. 160 postings sit on 40 companies; the cap counts companies."""
    hits = search_hits()
    search = _mock_search(hits)
    bodies = _mock_bodies(hits)
    asked: list[tuple[str, str]] = []

    def _admits(provider: str, slug: str) -> bool:
        asked.append((provider, slug))
        return False

    result = HiringCafeLane().collect(_fetcher(tmp_path), _admits)

    assert len(asked) == 40
    assert len(set(asked)) == 40
    assert set(asked) == {_expected_key(hit) for hit in hits}
    # Refusal is free: no body was paid for, and one search GET was made, not two.
    assert search.call_count == 1
    assert bodies.call_count == 0
    assert result.snapshots == ()
    # Nothing attempted is not an outage — recording refusals here would say otherwise.
    assert result.tally.attempted == 0
    assert result.tally.is_silent_outage is False


@respx.mock
def test_one_search_get_and_one_body_get_per_admitted_posting(tmp_path):
    hits = search_hits()
    search = _mock_search(hits)
    bodies = _mock_bodies(hits)
    wanted = ("hiringcafe", f"icims2:{board_token('icims2', 0)}")

    result = HiringCafeLane().collect(
        _fetcher(tmp_path), lambda provider, slug: (provider, slug) == wanted
    )

    assert search.call_count == 1  # one page, because `search_pages` defaults to 1
    assert bodies.call_count == 4  # four postings at the one admitted company
    assert result.tally.counts["body_fetched"] == 4
    assert result.tally.resolved == 4
    assert result.tally.is_silent_outage is False

    (snapshot,) = result.snapshots
    assert (snapshot.provider, snapshot.slug) == wanted
    assert snapshot.snapshot.status == "partial"  # never `complete`; an empty one closes a board
    assert len(snapshot.snapshot.postings) == 4


@respx.mock
def test_a_posting_carries_the_employer_url_and_the_workplace_location(tmp_path):
    hits = search_hits()
    _mock_search(hits)
    _mock_bodies(hits)
    wanted = ("hiringcafe", f"icims2:{board_token('icims2', 0)}")

    result = HiringCafeLane().collect(
        _fetcher(tmp_path), lambda provider, slug: (provider, slug) == wanted
    )
    posting = result.snapshots[0].snapshot.postings[0]
    source_hit = posting.raw_json["hit"]

    assert posting.url == source_hit["apply_url"]
    assert posting.provider_posting_id == source_hit["objectID"]
    assert posting.title == source_hit["job_information"]["title"]
    assert posting.body_text.startswith(source_hit["job_information"]["title"])
    # Location text, never a coordinate: `rank.location_gate` matches text, so a lat/lon would
    # resolve `unknown` and fail OPEN through the hard US gate.
    assert posting.locations == [
        source_hit["v5_processed_job_data"]["formatted_workplace_location"]
    ]
    assert not any("lat" in location for location in posting.locations)
    assert posting.remote_policy == "unknown"  # `workplace_type`'s vocabulary is unrecorded


@respx.mock
def test_the_greenhouse_convergence_case_is_keyed_on_greenhouse(tmp_path):
    hits = search_hits()
    _mock_search(hits)
    _mock_bodies(hits)

    result = HiringCafeLane().collect(
        _fetcher(tmp_path), lambda provider, slug: provider == "greenhouse"
    )

    assert {(s.provider, s.slug) for s in result.snapshots} == {
        ("greenhouse", board_token("grnhse", 36)),
        ("greenhouse", board_token("grnhse", 37)),
    }
    for snapshot in result.snapshots:
        for posting in snapshot.snapshot.postings:
            # The greenhouse id a board scan would produce, so the two rows converge.
            assert posting.provider_posting_id == posting.url.rsplit("/", 1)[-1]


@respx.mock
def test_the_posting_budget_caps_body_gets_and_counts_what_it_skipped(tmp_path):
    hits = search_hits()
    _mock_search(hits)
    bodies = _mock_bodies(hits)
    wanted = ("hiringcafe", f"icims2:{board_token('icims2', 0)}")

    result = HiringCafeLane(posting_budget=2).collect(
        _fetcher(tmp_path), lambda provider, slug: (provider, slug) == wanted
    )

    assert bodies.call_count == 2
    assert result.tally.counts["body_fetched"] == 2
    # Seen and not requested is counted, never dropped silently.
    assert result.tally.counts["not_attemptable"] == 2
    assert result.tally.attempted == 4


@respx.mock
@pytest.mark.parametrize(
    "status,outcome",
    [(403, "fetch_refused"), (404, "fetch_gone"), (418, "fetch_unavailable")],
)
def test_a_failed_body_lands_in_its_own_bucket(tmp_path, status, outcome):
    """Folding these is exactly how the prior art hid an eleven-day outage."""
    hits = search_hits()
    _mock_search(hits)
    _mock_bodies(hits, status=status)
    wanted = ("hiringcafe", f"icims2:{board_token('icims2', 0)}")

    result = HiringCafeLane().collect(
        _fetcher(tmp_path), lambda provider, slug: (provider, slug) == wanted
    )

    assert result.tally.counts[outcome] == 4
    assert result.tally.resolved == 0
    assert result.tally.is_silent_outage is True
    # A company whose every body failed writes no snapshot, so no company row is owed for it.
    assert result.snapshots == ()


@respx.mock
def test_a_login_wall_body_is_rejected_rather_than_stored(tmp_path):
    hits = search_hits()[:4]
    _mock_search(hits)
    respx.get(url__startswith=_JD_PREFIX).mock(
        return_value=httpx.Response(
            200,
            json={"job": {"job_information": {"description":
                "<h2>Sign in to continue</h2><p>You must be logged in. Create an account.</p>"
            }}},
        )
    )

    result = HiringCafeLane().collect(_fetcher(tmp_path), lambda provider, slug: True)

    assert result.tally.counts["rejected_login_wall"] == 4
    assert result.snapshots == ()


@respx.mock
def test_a_body_payload_the_endpoint_cannot_serve_is_extracted_empty(tmp_path):
    hits = search_hits()[:4]
    _mock_search(hits)
    respx.get(url__startswith=_JD_PREFIX).mock(
        return_value=httpx.Response(200, json={"job": {}})
    )

    result = HiringCafeLane().collect(_fetcher(tmp_path), lambda provider, slug: True)

    assert result.tally.counts["extracted_empty"] == 4


def test_parsing_survives_a_closing_tag_inside_a_json_string_value():
    """The page is 1.28 MB and the JSON contains markup. A regex extractor stopped early.

    The reference implementation regexes this payload and gets away with it; this repo measured
    the failure, so selectolax stays even though the surface moved to that implementation's.
    """
    page = hiringcafe.parse_search_page(search_page_html(search_hits()[:2]))
    assert len(page.hits) == 2
    assert page.hits[0]["objectID"]
    assert page.is_last_page is False


def test_the_last_page_flag_is_read_off_the_payload_and_defaults_to_not_last():
    """`ssrIsLastPage` is what ends a facet, so a renamed flag must not read as "stop"."""
    assert hiringcafe.parse_search_page(search_page_html([], is_last_page=True)).is_last_page
    without_flag = (
        '<html><body><script id="__NEXT_DATA__" type="application/json">'
        '{"props":{"pageProps":{"ssrHits":[]}}}</script></body></html>'
    )
    # Absent reads as "keep going": the ceiling and the empty page still stop the loop, whereas
    # defaulting to True would truncate every facet to one page and report nothing wrong.
    assert hiringcafe.parse_search_page(without_flag).is_last_page is False


@pytest.mark.parametrize(
    "page",
    [
        "<html><body>no script here</body></html>",
        '<html><body><script id="__NEXT_DATA__" type="application/json">{</script></body></html>',
        '<html><body><script id="__NEXT_DATA__" type="application/json">'
        '{"props":{"pageProps":{"ssrHits":{}}}}</script></body></html>',
        # A 200 that reports its own failure. `ssrHits` is absent, so a reader that only asked
        # for the hits would record the quiet day this whole lane is designed against.
        '<html><body><script id="__NEXT_DATA__" type="application/json">'
        '{"props":{"pageProps":{"ssrError":"search backend unavailable"}}}</script></body></html>',
    ],
)
def test_an_unusable_search_page_raises_instead_of_returning_nothing(page):
    """An empty list would reach the runner as a quiet day. The runner must see the failure."""
    with pytest.raises(SearchPageError):
        hiringcafe.parse_search_page(page)


def test_a_reported_ssr_error_raises_even_when_hits_are_present():
    """The host can serve a stale or partial result set ALONGSIDE its own error.

    Pinned separately: the parametrized case above omits `ssrHits` entirely, so a reader that
    checked `ssrError` only after finding no hits would still pass it.
    """
    with pytest.raises(SearchPageError, match="ssrError"):
        hiringcafe.parse_search_page(
            search_page_html(search_hits()[:2], error="search backend unavailable")
        )


@respx.mock
def test_a_hit_with_no_usable_identity_is_counted_not_dropped(tmp_path):
    broken = dict(search_hits()[0], source="", board_token="", apply_url="")
    _mock_search([broken])

    result = HiringCafeLane().collect(_fetcher(tmp_path), lambda provider, slug: True)

    assert result.tally.counts["not_attemptable"] == 1
    assert result.snapshots == ()


def test_a_recognized_board_url_with_no_posting_reference_falls_back_to_the_lane_key():
    """`UnresolvablePostingURL` is ordinary here, not an error: lever's `/apply` chrome."""
    hit = dict(
        search_hits()[0],
        source="lever",
        board_token="acme",
        objectID="lever___acme___a1000000",
        apply_url="https://jobs.lever.co/acme/a1000000-0000-0000-0000-000000000001/apply",
    )
    identity = hit_identity(hit)
    assert (identity.provider, identity.slug) == ("hiringcafe", "lever:acme")
    assert identity.posting_id == "lever___acme___a1000000"


def test_the_company_name_reads_the_enriched_block_and_falls_back_to_the_board_token():
    """The only route from a `LaneResult` back to a display name: see `company_name`'s note."""
    hit = search_hits()[0]
    assert hiringcafe.company_name(hit) == hit["enriched_company_data"]["name"]
    assert hiringcafe.company_name(dict(hit, enriched_company_data={})) == hit["board_token"]
    assert hiringcafe.company_name({"board_token": "acme"}) == "acme"


def test_the_object_id_is_percent_encoded_into_the_jd_url():
    """`fountain`'s board_token carries dots and a `___` run; it must survive as one value."""
    url = hiringcafe.job_description_url("fountain___us-3.fountain.com___acme23___d545")
    assert url == (
        "https://hiringcafe.com/api/job-description?id="
        "fountain___us-3.fountain.com___acme23___d545"
    )
    assert hiringcafe.job_description_url("a&b=c").endswith("id=a%26b%3Dc")


@respx.mock
def test_locations_fall_back_to_the_workplace_arrays_and_tolerate_a_bare_string(tmp_path):
    """The probe recorded the `workplace_*` key names, not their types."""
    hit = dict(
        search_hits()[0],
        v5_processed_job_data={
            "workplace_cities": "Seattle",  # bare string rather than a list
            "workplace_states": ["Washington", "Washington"],  # deduped, order kept
            "workplace_countries": None,  # a key the live payload sometimes nulls
        },
    )
    _mock_search([hit])
    _mock_bodies([hit])

    result = HiringCafeLane().collect(_fetcher(tmp_path), lambda provider, slug: True)
    posting = result.snapshots[0].snapshot.postings[0]
    assert posting.locations == ["Seattle", "Washington"]


@respx.mock
def test_a_hit_with_no_title_is_refused_before_its_body_is_paid_for(tmp_path):
    """A posting with no title cannot be ranked or shown, and one GET would buy nothing."""
    untitled = dict(search_hits()[0], job_information=None)
    unlocated = dict(search_hits()[1])
    unlocated.pop("v5_processed_job_data")
    search = _mock_search([untitled, unlocated])
    bodies = _mock_bodies([untitled, unlocated])

    result = HiringCafeLane().collect(_fetcher(tmp_path), lambda provider, slug: True)

    assert search.call_count == 1
    assert bodies.call_count == 1  # the untitled hit was never fetched
    assert result.tally.counts["not_attemptable"] == 1
    # A hit with no processed block reports NO location rather than a coordinate.
    assert result.snapshots[0].snapshot.postings[0].locations == []


# --- the role facet (contract §4's deferred extension) -------------------------------------
#
# Probed live 2026-08-26. `robots.txt` decides the SHAPE of this feature and is the reason it is
# a path and not a query: `Disallow: /*?searchState=*` rules out the site's own query-parameter
# search, while `Allow: /jobs/` and a `job-search-sitemap.xml` listing 10,000+ role pages make
# the path route explicitly permitted. Building the query form would have taken this lane from
# compliant to disallowed, which is why the URL builder is tested rather than assumed.


def test_a_facet_becomes_the_ssr_search_state_and_never_the_retired_role_path(tmp_path):
    """D-393's surface, asserted on the built string rather than trusted.

    The whole outage was a SURFACE mistake: `/jobs/{role}` answers a refusal, `?searchState=`
    answers 200. The two differ by punctuation alone, so no downstream test would notice a
    revert — this one is written as an independent literal for that reason.
    """
    urls = hiringcafe.search_urls(("software engineer",))

    assert urls == (
        "https://hiringcafe.com/?searchState=%7B%22searchQuery%22%3A%20%22software%20"
        "engineer%22%2C%20%22sortBy%22%3A%20%22date%22%2C%20%22dateFetchedPastNDays"
        "%22%3A%207%7D",
    )
    # The retired path route must not survive anywhere in the built URL.
    assert not any(url.startswith("https://hiringcafe.com/jobs/") for url in urls)
    assert ROBOTS_ALLOWED_PREFIX not in urls[0]
    # The rules recorded in `hiringcafe_shape` are now what the builder PRODUCES, because
    # D-393 supersedes them. Inverted rather than deleted: a silent revert to the compliant
    # path form restores the outage, and this is the assertion that catches it.
    assert SUPERSEDED_BY == "D-393"
    assert ROBOTS_DISALLOWED_FORMS[0] in urls[0]


def test_a_facet_TERM_is_sent_verbatim_and_never_reshaped_for_the_old_path_route():
    """`lanes.facets` yields a canonical term ("software engineer"); the JSON takes it as is.

    The retired path route hyphenated it. Keeping that conversion would ask the host for
    `software-engineer`, a phrase the profile does not name and the search box would never be
    given, so the removal is asserted where it happened rather than assumed downstream.
    """
    (url,) = hiringcafe.search_urls(("machine learning engineer",))

    assert unquote(urlsplit(url).query.removeprefix("searchState=")) == (
        '{"searchQuery": "machine learning engineer", "sortBy": "date", '
        '"dateFetchedPastNDays": 7}'
    )
    assert "machine-learning-engineer" not in url


def test_the_search_state_sends_no_user_specific_facet_at_all():
    """The keystone-adjacent decision, pinned as an exact key set.

    The reference implementation pre-filters on `seniorityLevel`, `roleYoeRange`,
    `commitmentTypes`, `securityClearances` and a fixed United States `locations` entry. Every
    one of those is a fact about ONE user that boardwatch judges downstream with a rule that
    must be able to ABSTAIN, so sending it would let a query parameter decide what the
    eligibility engine is supposed to — and would hard-code that user into this module.

    An exact-equality assertion, not a set of `not in` checks: those pass against a state that
    grew a sixth pre-filter nobody listed here.
    """
    state = hiringcafe.search_state("software engineer")

    assert set(state) == {"searchQuery", "sortBy", "dateFetchedPastNDays"}
    assert state["searchQuery"] == "software engineer"
    # The two survivors describe the LANE's cadence, not the user.
    assert state["sortBy"] == "date"
    assert state["dateFetchedPastNDays"] == 7


def test_no_facets_falls_back_to_the_unfaceted_search_with_the_same_request_shape():
    """A user whose profile names no target titles gets an empty query, not a different route.

    The retired path form had a second URL for this case. One shape means the unfaceted user
    pages exactly as the faceted one does, instead of silently keeping a one-page ceiling.
    """
    (url,) = hiringcafe.search_urls(())

    assert url.startswith(f"{SEARCH_URL}?searchState=")
    assert hiringcafe.search_state("")["searchQuery"] == ""
    assert "%22searchQuery%22%3A%20%22%22" in url


def _mock_facet(facet: str, hits: list[dict[str, Any]] | None) -> respx.Route:
    """One facet's FIRST page. `None` means the 200-with-zero-results page a bogus facet gets."""
    return _mock_page(facet, 0, hits)


@respx.mock
def test_one_search_per_facet_and_the_unfaceted_page_is_never_requested(tmp_path):
    hits = search_hits()
    root = _mock_search(hits)
    swe = _mock_facet("software engineer", hits[:4])
    ios = _mock_facet("ios engineer", hits[4:8])
    _mock_bodies(hits)

    HiringCafeLane(search_facets=("software engineer", "ios engineer")).collect(
        _fetcher(tmp_path), lambda provider, slug: True
    )

    assert (swe.call_count, ios.call_count) == (1, 1)
    # The whole point of the feature: the general-market listing is not fetched at all.
    assert root.call_count == 0


@respx.mock
def test_a_posting_listed_under_two_facets_costs_one_body_get_not_two(tmp_path):
    """Overlapping facets are normal — `Software Engineer` and `Backend Engineer` return the
    same posting — and a second body GET for it is a paid-for duplicate. It is also the crash
    D-306 fixed: two rows with one `provider_posting_id` violate UNIQUE inside one transaction.
    """
    shared = search_hits()[:3]
    _mock_facet("software engineer", shared)
    _mock_facet("backend engineer", shared)
    bodies = _mock_bodies(shared)

    result = HiringCafeLane(search_facets=("software engineer", "backend engineer")).collect(
        _fetcher(tmp_path), lambda provider, slug: True
    )

    assert bodies.call_count == 3
    assert result.tally.counts["body_fetched"] == 3
    # The three re-listed hits were SEEN and not fetched; a silent drop is what the catalog exists
    # to prevent.
    assert result.tally.counts["not_attemptable"] == 3
    stored = [
        posting.provider_posting_id
        for company in result.snapshots
        for posting in company.snapshot.postings
    ]
    assert len(stored) == len(set(stored)) == 3


@respx.mock
def test_the_body_budget_spreads_across_facets_instead_of_being_eaten_by_the_first(tmp_path):
    """Without interleaving, facet 1 consumes the whole budget and every later target title
    contributes nothing — the feature would deliver only the profile's first title while
    reporting that fourteen facets ran.
    """
    hits = search_hits()
    first, second = hits[:20], hits[20:40]
    _mock_facet("software engineer", first)
    _mock_facet("ios engineer", second)
    _mock_bodies(hits)

    result = HiringCafeLane(
        posting_budget=6, search_facets=("software engineer", "ios engineer")
    ).collect(_fetcher(tmp_path), lambda provider, slug: True)

    fetched = {
        posting.provider_posting_id
        for company in result.snapshots
        for posting in company.snapshot.postings
    }
    from_first = {hit["objectID"] for hit in first} & fetched
    from_second = {hit["objectID"] for hit in second} & fetched
    assert len(fetched) == 6
    assert from_first and from_second, "one facet took the entire body budget"


@respx.mock
def test_the_snapshot_records_the_facet_page_a_company_was_found_on(tmp_path):
    """Provenance has to name the URL actually requested. Recording the unfaceted root would
    cite a page this run never fetched.
    """
    hits = search_hits()[:2]
    _mock_facet("ios engineer", hits)
    _mock_bodies(hits)

    result = HiringCafeLane(search_facets=("ios engineer",)).collect(
        _fetcher(tmp_path), lambda provider, slug: True
    )

    assert {company.snapshot.url for company in result.snapshots} == {_page("ios engineer", 0)}


@respx.mock
def test_every_facet_returning_nothing_raises_instead_of_reporting_a_quiet_day(tmp_path):
    """The outage case, and the reason this is not left to the tally.

    A bogus slug answers 200 with an EMPTY result list, not 404 — probed. So if the role route
    moves, every facet returns zero, no request fails, and the lane reports a clean run with no
    postings forever. That is exactly the prior art's 11-run silent outage. `attempted` cannot
    catch it either: with no hits, nothing is ever attempted, so `is_silent_outage` stays False.
    """
    _mock_facet("software engineer", None)
    _mock_facet("ios engineer", None)
    bodies = _mock_bodies([])

    with pytest.raises(SearchPageError, match="facet"):
        HiringCafeLane(search_facets=("software engineer", "ios engineer")).collect(
            _fetcher(tmp_path), lambda provider, slug: True
        )

    assert bodies.call_count == 0


@respx.mock
def test_one_empty_facet_among_several_is_tolerated_rather_than_fatal(tmp_path):
    """A single unproductive target title is a profile-data matter, not an outage. Raising here
    would let one odd title in a profile disable the whole lane.
    """
    hits = search_hits()[:3]
    _mock_facet("software engineer", hits)
    _mock_facet("zzq not a real role", None)
    _mock_bodies(hits)

    result = HiringCafeLane(
        search_facets=("software engineer", "zzq not a real role")
    ).collect(_fetcher(tmp_path), lambda provider, slug: True)

    assert result.tally.counts["body_fetched"] == 3
    assert result.tally.is_silent_outage is False


@respx.mock
def test_one_facet_whose_request_fails_does_not_cost_the_others_their_results(tmp_path):
    """Per-facet isolation, the same shape D-307 gave a board's apply failure.

    The unfaceted lane made ONE search request, so a failure there could only cost that one
    request. A faceted lane makes fourteen, and letting the seventh abort the collection
    discards six facets' worth of already-paid-for work. The fetcher has already retried with
    backoff by the time it raises, so this is the surviving-failure case, not a transient one.
    """
    hits = search_hits()[:3]
    _mock_facet("software engineer", hits)
    respx.get(_page("ios engineer", 0)).mock(return_value=httpx.Response(503))
    _mock_bodies(hits)

    result = HiringCafeLane(
        search_facets=("software engineer", "ios engineer")
    ).collect(_fetcher(tmp_path), lambda provider, slug: True)

    assert result.tally.counts["body_fetched"] == 3
    assert result.tally.is_silent_outage is False


@respx.mock
def test_every_facet_request_failing_raises_rather_than_reporting_a_quiet_day(tmp_path):
    """Isolation must not become suppression: if the host refuses every facet, that is the
    outage case and it has to reach the runner, exactly as an all-empty result does."""
    respx.get(url__startswith=f"{SEARCH_URL}?searchState=").mock(
        return_value=httpx.Response(403)
    )
    bodies = _mock_bodies([])

    with pytest.raises(SearchPageError, match="facet"):
        HiringCafeLane(search_facets=("software engineer", "ios engineer")).collect(
            _fetcher(tmp_path), lambda provider, slug: True
        )

    assert bodies.call_count == 0


# --- paging (D-393; `&page=N` measured live 2026-08-31) ------------------------------------
#
# The lane shipped without paging because no page parameter had been evidenced and the
# `?page=` form was disallowed. Both premises are gone: two GETs 1.5s apart returned 143 hits
# on page 0 and 133 on page 1 with ZERO id overlap, so the parameter turns a page rather than
# re-serving one. `LaneResult.search_pages` was `()` for this lane before and is now real
# depth, which is the difference between "the facet ran out" and "the ceiling truncated it".


@respx.mock
def test_the_default_ceiling_requests_exactly_one_page_and_names_it_page_zero(tmp_path):
    """`lane_search_pages` defaults to 1, and page 0 is spelled `&page=0`.

    The default must move no user's request COUNT, and the URL it requests has to be the one
    the probe measured -- suppressing `&page=0` for tidiness would make the default path a
    shape nothing has ever been observed to answer.
    """
    hits = search_hits()[:2]
    first = _mock_page("ios engineer", 0, hits)
    later = _mock_page("ios engineer", 1, hits)
    _mock_bodies(hits)

    result = HiringCafeLane(search_facets=("ios engineer",)).collect(
        _fetcher(tmp_path), lambda provider, slug: True
    )

    assert (first.call_count, later.call_count) == (1, 0)
    assert str(first.calls[0].request.url).endswith("&page=0")
    assert result.search_pages == ((_search_url("ios engineer"), 1),)


@respx.mock
def test_paging_stops_where_the_host_says_the_results_end(tmp_path):
    """`ssrIsLastPage` ends the facet, and the pages actually fetched are what gets reported.

    A ceiling of 5 against a 2-page result set must spend 2 requests, not 5, and must report 2
    -- a facet that stopped short RAN OUT, while one that filled the ceiling was TRUNCATED, and
    a posting count cannot tell those apart.
    """
    hits = search_hits()
    pages = [
        _mock_page("ios engineer", 0, hits[:4]),
        _mock_page("ios engineer", 1, hits[4:8], is_last_page=True),
        _mock_page("ios engineer", 2, hits[8:12]),
    ]
    _mock_bodies(hits)

    result = HiringCafeLane(search_facets=("ios engineer",), search_pages=5).collect(
        _fetcher(tmp_path), lambda provider, slug: True
    )

    assert [route.call_count for route in pages] == [1, 1, 0]
    assert result.search_pages == ((_search_url("ios engineer"), 2),)
    # Both pages' hits reached the tally; the second page is reach, not bookkeeping.
    assert result.tally.counts["body_fetched"] == 8


@respx.mock
def test_a_page_that_re_serves_hits_already_held_ends_the_facet(tmp_path):
    """The offset-wrap tail `providers/workday.py` guards, and the stop-honouring-page case.

    A host that answers past the end of a result set with a REPEAT rather than an empty page
    would otherwise burn every remaining request on hits this facet already listed -- and so
    would one that quietly stopped honouring `&page=` at all, which is the failure mode that
    matters here because `&page=` is one parameter on a URL nobody here operates.
    """
    hits = search_hits()[:4]
    pages = [
        _mock_page("ios engineer", 0, hits),
        _mock_page("ios engineer", 1, hits),  # the same four hits again
        _mock_page("ios engineer", 2, search_hits()[4:8]),
    ]
    _mock_bodies(search_hits())

    result = HiringCafeLane(search_facets=("ios engineer",), search_pages=4).collect(
        _fetcher(tmp_path), lambda provider, slug: True
    )

    assert [route.call_count for route in pages] == [1, 1, 0]
    assert result.search_pages == ((_search_url("ios engineer"), 2),)
    assert result.tally.counts["body_fetched"] == 4


@respx.mock
def test_a_later_page_failing_keeps_the_pages_already_paid_for(tmp_path):
    """Page 1 and page N are not the same event.

    A facet refused on its FIRST page produced nothing and is a failure its caller must count;
    one refused on page 4 keeps the three pages already bought. Folding them would either
    discard paid-for reach or hide the refusal.
    """
    hits = search_hits()[:4]
    _mock_page("ios engineer", 0, hits)
    respx.get(_page("ios engineer", 1)).mock(return_value=httpx.Response(503))
    _mock_bodies(hits)

    result = HiringCafeLane(search_facets=("ios engineer",), search_pages=3).collect(
        _fetcher(tmp_path), lambda provider, slug: True
    )

    assert result.tally.counts["body_fetched"] == 4
    assert result.search_pages == ((_search_url("ios engineer"), 1),)


@respx.mock
def test_depth_is_reported_per_facet_including_the_one_that_failed(tmp_path):
    """One number per search, not one for the lane: the facets read to different depths.

    The failed facet reports 0 pages rather than being absent, for the reason the acquisition
    tally exists at all -- an absent row reads as "not measured", and a facet the host refused
    is measured and empty.
    """
    hits = search_hits()
    _mock_page("software engineer", 0, hits[:4])
    _mock_page("software engineer", 1, hits[4:8], is_last_page=True)
    respx.get(_page("ios engineer", 0)).mock(return_value=httpx.Response(403))
    _mock_bodies(hits)

    result = HiringCafeLane(
        search_facets=("software engineer", "ios engineer"), search_pages=4
    ).collect(_fetcher(tmp_path), lambda provider, slug: True)

    assert result.search_pages == (
        (_search_url("software engineer"), 2),
        (_search_url("ios engineer"), 0),
    )


@respx.mock
def test_the_unfaceted_search_pages_exactly_as_a_faceted_one_does(tmp_path):
    """The fallback is now the same request shape, so it must not keep a one-page ceiling.

    Pinned separately because `_search` has two arms and the tests above exercise only the
    faceted one -- paging added to that arm alone would pass every one of them.
    """
    hits = search_hits()
    _mock_page("", 0, hits[:4])
    _mock_page("", 1, hits[4:8], is_last_page=True)
    _mock_bodies(hits)

    result = HiringCafeLane(search_pages=3).collect(
        _fetcher(tmp_path), lambda provider, slug: True
    )

    assert result.search_pages == ((_search_url(), 2),)
    assert result.tally.counts["body_fetched"] == 8


def test_a_search_pages_ceiling_below_one_still_fetches_a_page(tmp_path):
    """0 would fetch nothing and report the silence as a quiet day. `Settings` floors it at 1;
    a lane constructed directly must not be able to route around that."""
    assert HiringCafeLane(search_pages=0)._search_pages == 1


@pytest.mark.parametrize(
    "facet",
    [
        "software engineer",
        "a/b",                    # a slash must not become a path segment
        "x&page=2",               # a second parameter smuggled in through the facet
        "y#fragment",
        "../admin",               # path traversal out of the site root
    ],
)
def test_no_facet_however_shaped_can_reshape_the_request(facet):
    """The containment boundary, moved from the path to the query value by D-393.

    `lanes.facets` normalizes titles before they get here, so none of these can arrive on the
    live route today. The point is that the URL builder cannot be TALKED into a different
    request by its input -- the guarantee has to hold at this boundary rather than depend on a
    caller upstream continuing to sanitize, because a future second caller would not know to.

    A facet that escaped its value would be worse here than under the retired path form: it
    could ADD a searchState key, and the keys this module refuses to send are the ones the
    eligibility engine is supposed to decide.
    """
    (url,) = hiringcafe.search_urls((facet,))
    split = urlsplit(url)

    # The site root, whatever the facet says. Nothing reaches the path.
    assert split.path == "/"
    assert ROBOTS_ALLOWED_PREFIX not in url
    assert split.fragment == ""
    # Exactly one parameter, and the facet is inside its value rather than beside it.
    assert split.query.count("=") == 1
    assert split.query.count("&") == 0
    assert split.query.startswith("searchState=")
    assert json.loads(unquote(split.query.removeprefix("searchState=")))["searchQuery"] == facet
    # `&page=` is appended by `page_url`, never by the facet. Both disallowed forms D-393
    # supersedes are now BUILT deliberately, and only here.
    assert ROBOTS_DISALLOWED_FORMS[0] in url
    assert ROBOTS_DISALLOWED_FORMS[2] not in url
    assert ROBOTS_DISALLOWED_FORMS[2] in hiringcafe.page_url(url, 1)


# --- how the search request PRESENTS itself (D-369) ----------------------------------------
#
# The lane has carried a Chrome UA since it shipped; what it did not carry was any of the
# headers that UA implies, and httpx's defaults contradict it -- `Accept: */*` is not something
# a browser sends when navigating to an HTML page. These tests pin the search route's header
# set and, just as load-bearing, pin that it does NOT reach the JSON body endpoint.


@respx.mock
def test_a_search_get_presents_itself_as_the_navigation_its_user_agent_claims(tmp_path):
    """The facet page is fetched with a browser's navigation headers, not httpx's defaults.

    `Accept` is asserted on its VALUE rather than on presence: httpx always sends an `Accept`,
    so a presence check passes against the unpatched lane and proves nothing.
    """
    hits = search_hits()[:2]
    swe = _mock_facet("software engineer", hits)
    _mock_bodies(hits)

    HiringCafeLane(search_facets=("software engineer",)).collect(
        _fetcher(tmp_path), lambda provider, slug: True
    )

    sent = swe.calls[0].request.headers
    assert sent["Accept"].startswith("text/html")
    assert sent["Accept"] != "*/*"
    assert sent["Accept-Language"] == "en-US,en;q=0.9"
    assert sent["Sec-Fetch-Mode"] == "navigate"
    assert sent["Sec-Fetch-Dest"] == "document"
    assert sent["Upgrade-Insecure-Requests"] == "1"
    # The UA is the CLIENT's and is pinned in `tests/pipeline/test_lane_stage.py`, which is also
    # where the coupling is asserted: this set is coherent only against a browser UA.


@respx.mock
def test_the_unfaceted_fallback_search_presents_itself_the_same_way(tmp_path):
    """A profile with no target titles requests a different URL, not a different kind of request.

    Pinned separately because `_search` has two arms and the faceted one is the only one the
    test above exercises -- a patch applied to one arm alone passes it.
    """
    hits = search_hits()[:2]
    root = _mock_search(hits)
    _mock_bodies(hits)

    HiringCafeLane().collect(_fetcher(tmp_path), lambda provider, slug: True)

    assert root.calls[0].request.headers["Accept"].startswith("text/html")


@respx.mock
def test_the_navigation_headers_never_reach_the_json_body_endpoint(tmp_path):
    """`/api/job-description` is an XHR, and it is the half of this lane that still WORKS.

    A browser fetching JSON sends `Accept: */*` and `Sec-Fetch-Dest: empty`, so putting the
    navigation set on the shared client would have made every body GET incoherent in the
    opposite direction -- and would have changed the other lane on that client at the same
    time, which is the second variable D-364's one-at-a-time rule exists to prevent.
    """
    hits = search_hits()[:2]
    _mock_facet("software engineer", hits)
    bodies = _mock_bodies(hits)

    HiringCafeLane(search_facets=("software engineer",)).collect(
        _fetcher(tmp_path), lambda provider, slug: True
    )

    assert bodies.call_count == 2
    for call in bodies.calls:
        assert call.request.headers["Accept"] == "*/*"
        assert "Sec-Fetch-Mode" not in call.request.headers
        assert "Upgrade-Insecure-Requests" not in call.request.headers


def test_the_search_header_set_asserts_nothing_the_user_agent_does_not_already(tmp_path):
    """The boundary, written down: restate the UA's claim, never extend it.

    `sec-ch-ua*` client hints are a fresh assertion -- a server asks for them with `Accept-CH`
    and we have no recorded evidence this one does -- and `Accept-Encoding` is httpx's to set,
    because this client cannot decode the `br`/`zstd` a real Chrome advertises and advertising
    an encoding we cannot read trades a header mismatch for a corrupted body. Both omissions
    are deliberate, so both are pinned: without this, "make it look more like a browser" has no
    stopping point and the next reader adds them.
    """
    keys = {key.lower() for key in hiringcafe._SEARCH_HEADERS}

    assert not any(key.startswith("sec-ch-ua") for key in keys)
    assert "accept-encoding" not in keys
    assert "cookie" not in keys
    assert "referer" not in keys
    assert "user-agent" not in keys  # the client owns identity; the lane owns request shape
