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

import httpx
import pytest
import respx
from hiringcafe_shape import (
    REVIEW_BY,
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
