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
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
import pytest
import respx
from hiringcafe_shape import (
    REVIEW_BY,
    ROBOTS_ALLOWED_PREFIX,
    ROBOTS_DISALLOWED_FORMS,
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

    RE-READ `robots.txt` in the same pass. The role facet is a path only because the query
    forms are disallowed, so a narrowed `Allow: /jobs/` puts the lane in violation while every
    request keeps succeeding -- the one drift here that no assertion can catch by itself.
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


def _mock_search(hits: list[dict[str, Any]] | None = None) -> respx.Route:
    return respx.get(SEARCH_URL).mock(
        return_value=httpx.Response(200, text=search_page_html(hits))
    )


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

    assert search.call_count == 1  # `ssrPage`/`ssrIsLastPage` exist; the lane never pages
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


def test_search_hits_survives_a_closing_tag_inside_a_json_string_value():
    """The page is 1.28 MB and the JSON contains markup. A regex extractor stopped early."""
    hits = hiringcafe.search_hits(search_page_html(search_hits()[:2]))
    assert len(hits) == 2
    assert hits[0]["objectID"]


@pytest.mark.parametrize(
    "page",
    [
        "<html><body>no script here</body></html>",
        '<html><body><script id="__NEXT_DATA__" type="application/json">{</script></body></html>',
        '<html><body><script id="__NEXT_DATA__" type="application/json">'
        '{"props":{"pageProps":{"ssrHits":{}}}}</script></body></html>',
    ],
)
def test_an_unusable_search_page_raises_instead_of_returning_nothing(page):
    """An empty list would reach the runner as a quiet day. The runner must see the failure."""
    with pytest.raises(SearchPageError):
        hiringcafe.search_hits(page)


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


def test_a_facet_becomes_the_permitted_role_path_and_never_a_search_query(tmp_path):
    """`robots.txt` disallows `?searchState=` and allows `/jobs/`. The slug is a PATH segment.

    Asserted on the built string rather than trusted, because the disallowed form differs from
    the allowed one by punctuation alone and no downstream test would notice the difference.
    """
    urls = hiringcafe.search_urls(("software-engineer", "ios-engineer"))

    assert urls == (
        "https://hiringcafe.com/jobs/software-engineer",
        "https://hiringcafe.com/jobs/ios-engineer",
    )
    assert not any("?" in url or "searchState" in url or "page=" in url for url in urls)


def test_a_facet_TERM_is_hyphenated_into_the_path_and_never_sent_with_spaces():
    """`lanes.facets` yields a canonical term ("software engineer"); this route needs a hyphen.

    Pinned separately from the tests above, which pass already-hyphenated facets and so cannot
    fail if the conversion is dropped — a mutation removing `.replace(" ", "-")` passed all of
    them. The two lanes need OPPOSITE encodings of the same term (LinkedIn's probe evidenced
    `keywords=software%20engineer`), so the conversion has to be asserted where it happens.
    """
    assert hiringcafe.search_urls(("software engineer", "ios engineer")) == (
        "https://hiringcafe.com/jobs/software-engineer",
        "https://hiringcafe.com/jobs/ios-engineer",
    )
    assert not any("%20" in url for url in hiringcafe.search_urls(("machine learning engineer",)))


def test_no_facets_falls_back_to_the_unfaceted_search_exactly_as_before():
    """A user whose profile names no target titles keeps the behaviour that shipped."""
    assert hiringcafe.search_urls(()) == (SEARCH_URL,)


def _facet_url(slug: str) -> str:
    return f"https://hiringcafe.com/jobs/{slug}"


def _mock_facet(slug: str, hits: list[dict[str, Any]] | None) -> respx.Route:
    """One facet page. `None` means the 200-with-zero-results page a bogus slug returns."""
    return respx.get(_facet_url(slug)).mock(
        return_value=httpx.Response(200, text=search_page_html(hits if hits is not None else []))
    )


@respx.mock
def test_one_search_per_facet_and_the_unfaceted_page_is_never_requested(tmp_path):
    hits = search_hits()
    root = _mock_search(hits)
    swe = _mock_facet("software-engineer", hits[:4])
    ios = _mock_facet("ios-engineer", hits[4:8])
    _mock_bodies(hits)

    HiringCafeLane(search_facets=("software-engineer", "ios-engineer")).collect(
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
    _mock_facet("software-engineer", shared)
    _mock_facet("backend-engineer", shared)
    bodies = _mock_bodies(shared)

    result = HiringCafeLane(search_facets=("software-engineer", "backend-engineer")).collect(
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
    _mock_facet("software-engineer", first)
    _mock_facet("ios-engineer", second)
    _mock_bodies(hits)

    result = HiringCafeLane(
        posting_budget=6, search_facets=("software-engineer", "ios-engineer")
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
    _mock_facet("ios-engineer", hits)
    _mock_bodies(hits)

    result = HiringCafeLane(search_facets=("ios-engineer",)).collect(
        _fetcher(tmp_path), lambda provider, slug: True
    )

    assert {company.snapshot.url for company in result.snapshots} == {_facet_url("ios-engineer")}


@respx.mock
def test_every_facet_returning_nothing_raises_instead_of_reporting_a_quiet_day(tmp_path):
    """The outage case, and the reason this is not left to the tally.

    A bogus slug answers 200 with an EMPTY result list, not 404 — probed. So if the role route
    moves, every facet returns zero, no request fails, and the lane reports a clean run with no
    postings forever. That is exactly the prior art's 11-run silent outage. `attempted` cannot
    catch it either: with no hits, nothing is ever attempted, so `is_silent_outage` stays False.
    """
    _mock_facet("software-engineer", None)
    _mock_facet("ios-engineer", None)
    bodies = _mock_bodies([])

    with pytest.raises(SearchPageError, match="facet"):
        HiringCafeLane(search_facets=("software-engineer", "ios-engineer")).collect(
            _fetcher(tmp_path), lambda provider, slug: True
        )

    assert bodies.call_count == 0


@respx.mock
def test_one_empty_facet_among_several_is_tolerated_rather_than_fatal(tmp_path):
    """A single unproductive target title is a profile-data matter, not an outage. Raising here
    would let one odd title in a profile disable the whole lane.
    """
    hits = search_hits()[:3]
    _mock_facet("software-engineer", hits)
    _mock_facet("zzq-not-a-real-role", None)
    _mock_bodies(hits)

    result = HiringCafeLane(
        search_facets=("software-engineer", "zzq-not-a-real-role")
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
    _mock_facet("software-engineer", hits)
    respx.get(_facet_url("ios-engineer")).mock(return_value=httpx.Response(503))
    _mock_bodies(hits)

    result = HiringCafeLane(
        search_facets=("software-engineer", "ios-engineer")
    ).collect(_fetcher(tmp_path), lambda provider, slug: True)

    assert result.tally.counts["body_fetched"] == 3
    assert result.tally.is_silent_outage is False


@respx.mock
def test_every_facet_request_failing_raises_rather_than_reporting_a_quiet_day(tmp_path):
    """Isolation must not become suppression: if the host refuses every facet, that is the
    outage case and it has to reach the runner, exactly as an all-empty result does."""
    respx.get(url__startswith="https://hiringcafe.com/jobs/").mock(
        return_value=httpx.Response(403)
    )
    bodies = _mock_bodies([])

    with pytest.raises(SearchPageError, match="facet"):
        HiringCafeLane(search_facets=("software-engineer", "ios-engineer")).collect(
            _fetcher(tmp_path), lambda provider, slug: True
        )

    assert bodies.call_count == 0


@pytest.mark.parametrize(
    "facet",
    [
        "software-engineer",
        "a/b",                    # a slash would make `/jobs/a/b`, a different route
        "x?page=2",               # a disallowed query form smuggled in through the facet
        "y?searchState=z",
        "../admin",               # path traversal out of the permitted prefix
    ],
)
def test_no_facet_however_shaped_can_build_a_url_robots_disallows(facet):
    """The permission boundary, asserted against the recorded `robots.txt` rules.

    `lanes.facets` normalizes titles before they get here, so none of these can arrive on the
    live path today. The point is that the URL builder cannot be TALKED into a disallowed form
    by its input -- the guarantee has to hold at this boundary rather than depend on a caller
    upstream continuing to sanitize, because a future second caller would not know to.
    """
    (url,) = hiringcafe.search_urls((facet,))
    split = urlsplit(url)

    assert split.path.startswith(ROBOTS_ALLOWED_PREFIX)
    assert split.path.count("/") == 2, f"{facet!r} escaped its path segment: {split.path}"
    # No query string at all, so no disallowed query form can exist in one.
    assert split.query == ""
    assert not any(form in url for form in ROBOTS_DISALLOWED_FORMS)


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
    swe = _mock_facet("software-engineer", hits)
    _mock_bodies(hits)

    HiringCafeLane(search_facets=("software-engineer",)).collect(
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
    _mock_facet("software-engineer", hits)
    bodies = _mock_bodies(hits)

    HiringCafeLane(search_facets=("software-engineer",)).collect(
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
