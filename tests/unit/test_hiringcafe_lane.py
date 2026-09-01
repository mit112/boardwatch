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
from collections.abc import Sequence
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
    SSR_PROBED_PAGE_HITS,
    SSR_PROBED_PAGE_OVERLAP,
    SUPERSEDED_BY,
    board_token,
    greenhouse_board_payload,
    search_hits,
    search_page_html,
)

from boardwatch.core.politeness import Fetcher, identifying_user_agent
from boardwatch.core.settings import Settings
from boardwatch.lanes import hiringcafe
from boardwatch.lanes.base import Lane
from boardwatch.lanes.hiringcafe import SEARCH_URL, HiringCafeLane, SearchPageError, hit_identity
from boardwatch.providers.greenhouse import GreenhouseProvider
from boardwatch.providers.registry import build_providers

# The UA `pipeline.runner` gives the lane client. Spelled out here rather than imported: the
# point of `_browser_fetcher` is to reproduce a client whose identity DIFFERS from the one the
# board route must restore, and importing the runner's constant would make the two agree by
# construction if that constant ever changed to the identifying UA.
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1, per_host_delay_seconds=0.25
    )


def _fetcher(tmp_path: Path) -> Fetcher:
    return Fetcher(_settings(tmp_path))


def _browser_fetcher(tmp_path: Path) -> Fetcher:
    """A `Fetcher` shaped like `pipeline._lane_fetcher`'s: browser UA on the CLIENT."""
    return Fetcher(_settings(tmp_path), httpx.Client(headers={"User-Agent": _BROWSER_UA}))


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


def _mock_any_board() -> respx.Route:
    """A catch-all for every body-inlined provider host, so "no body was fetched" is asserted
    against a route that WOULD have answered rather than against an unmocked-request error."""
    hosts = tuple(
        {
            httpx.URL(build_providers()[name].board_url("probe")).host
            for name in ("greenhouse", "lever", "ashby", "workable")
        }
    )
    return respx.route(host__in=hosts).mock(
        return_value=httpx.Response(200, content=b'{"jobs": []}')
    )


def _as_greenhouse(hit: dict[str, Any], slug: str, posting_id: int) -> dict[str, Any]:
    """One recorded hit re-pointed at a greenhouse board -- the 14.7% the lane can body.

    Only `apply_url` and the two fields that describe where it lives are changed, so
    everything the lane reads OFF the hit (title, objectID, company block) stays the recorded
    shape. The fixture's own 8 grnhse hits sit on two boards, which is not enough companies to
    exercise a per-company budget, and inventing whole hits would drift from the recorded shape.
    """
    return dict(
        hit,
        source="grnhse",
        board_token=slug,
        apply_url=f"https://boards.greenhouse.io/{slug}/jobs/{posting_id}",
    )


def _unreachable(slug: str, offsets: Sequence[int]) -> list[dict[str, Any]]:
    """`len(offsets)` hits on an ATS this repo has NO body-inlined adapter for.

    iCIMS is the real majority shape in the recorded mix, and it is the shape that starved the
    reachable boards out of the company cap.
    """
    base = search_hits()
    return [
        dict(
            base[i],
            source="icims2",
            board_token=slug,
            apply_url=f"https://jobs.icims.com/{slug}/jobs/{7_100_000 + i}",
        )
        for i in offsets
    ]


def _reachable(slug: str, offsets: Sequence[int]) -> list[dict[str, Any]]:
    """`len(offsets)` hits at one greenhouse board, keyed off distinct recorded hits."""
    base = search_hits()
    return [_as_greenhouse(base[i], slug, 6_100_000 + i) for i in offsets]


def _board_url(slug: str) -> str:
    return GreenhouseProvider().board_url(slug)


def _mock_boards(
    hits: Sequence[dict[str, Any]], *, status: int = 200, content: bytes | None = None
) -> dict[str, respx.Route]:
    """One route per greenhouse board these hits name. Nothing else can serve a body.

    Deliberately NOT a catch-all route: a lane that reached for a body anywhere else -- the
    retired `/api/job-description`, an employer's HTML page, an ATS this repo has no adapter
    for -- gets an unmocked-request error rather than a body, which is the assertion that the
    two-hop shape has really moved.
    """
    by_slug: dict[str, list[dict[str, Any]]] = {}
    for hit in hits:
        if hit["source"] == "grnhse":
            by_slug.setdefault(hit["board_token"], []).append(hit)
    routes: dict[str, respx.Route] = {}
    for slug, slug_hits in by_slug.items():
        response = (
            httpx.Response(status)
            if status != 200
            else httpx.Response(
                200, content=greenhouse_board_payload(slug_hits) if content is None else content
            )
        )
        routes[slug] = respx.get(_board_url(slug)).mock(return_value=response)
    return routes


@respx.mock
def test_admits_is_asked_once_per_distinct_company_never_once_per_posting(tmp_path):
    """D1's contract. 160 postings sit on 40 companies; the cap counts companies."""
    hits = search_hits()
    search = _mock_search(hits)
    boards = _mock_boards(hits)
    asked: list[tuple[str, str]] = []

    def _admits(provider: str, slug: str) -> bool:
        asked.append((provider, slug))
        return False

    result = HiringCafeLane().collect(_fetcher(tmp_path), _admits)

    # Once per COMPANY, never once per posting -- the contract this test exists for. The
    # fixture's 160 postings sit on 40 companies, of which 2 are greenhouse; only those two are
    # offered, because a company whose body can never be read must not charge the company cap.
    bodyable = {_expected_key(hit) for hit in hits if hit["source"] == "grnhse"}
    assert len(bodyable) == 2
    assert len(asked) == 2
    assert set(asked) == bodyable
    # The other 38 are never asked, so they cannot starve the reachable two out of the cap.
    assert len({_expected_key(hit) for hit in hits}) == 40
    # Refusal is free: no board was paid for, and one search GET was made, not two.
    assert search.call_count == 1
    assert all(route.call_count == 0 for route in boards.values())
    assert result.snapshots == ()
    # The 152 hits on unbodyable hosts are counted, and counted as NOT attempted, so a lane
    # that merely found nothing reachable does not read as an outage.
    assert result.tally.counts["not_attemptable"] == 152
    assert result.tally.is_silent_outage is False


@respx.mock
def test_one_board_get_serves_every_posting_at_that_company(tmp_path):
    """The shape of the second hop after D-393: one GET per COMPANY, not one per posting.

    That is the whole reason a body-inlined provider is the only one the lane resolves through:
    four postings arrive for one request, so `body_inline` is the honest outcome and the
    posting budget stops being the binding constraint it was against a per-posting endpoint.
    """
    hits = _reachable("acme-inline", range(4))
    search = _mock_search(hits)
    boards = _mock_boards(hits)

    result = HiringCafeLane().collect(
        _fetcher(tmp_path), lambda provider, slug: (provider, slug) == ("greenhouse", "acme-inline")
    )

    assert search.call_count == 1  # one page, because `search_pages` defaults to 1
    assert boards["acme-inline"].call_count == 1  # ONE board GET for all four postings
    assert result.tally.counts["body_inline"] == 4
    assert result.tally.counts["body_fetched"] == 0  # the per-posting endpoint is gone
    assert result.tally.resolved == 4
    assert result.tally.is_silent_outage is False

    (snapshot,) = result.snapshots
    assert (snapshot.provider, snapshot.slug) == ("greenhouse", "acme-inline")
    assert snapshot.snapshot.status == "partial"  # never `complete`; an empty one closes a board
    assert len(snapshot.snapshot.postings) == 4


@respx.mock
def test_a_company_the_lane_cannot_body_costs_no_request_and_is_counted(tmp_path):
    """The 85.3%: an aggregator-only host has no evidenced body source, so nothing is fetched.

    `not_attemptable` is the closed catalog's member for "seen and NOT fetched", and every one
    of those hits has to reach it -- a silent drop is exactly what the catalog exists to stop,
    and it is what would make this change look like a quiet lane instead of a bounded one.
    """
    hits = search_hits()[:8]  # icims2 and friends: `apply_url` names no board this repo parses
    _mock_search(hits)
    boards = _mock_boards(hits)

    result = HiringCafeLane().collect(_fetcher(tmp_path), lambda provider, slug: True)

    assert boards == {}  # no board route was even needed
    assert result.tally.counts["not_attemptable"] == 8
    assert result.tally.resolved == 0
    assert result.snapshots == ()
    # NOT an outage, reversing this test's original assertion. `not_attemptable` means the item
    # was seen and deliberately NOT requested, so it is not an attempt, and the predicate's own
    # docstring is "attempts were made and none produced a body". The reversal is measured, not
    # stylistic: 152 of the 160 recorded hits sit on an ATS with no body-inlined board, so
    # all-aggregator is the ORDINARY result here and flagging it would fire on most healthy runs
    # -- the cry-wolf the predicate exists to avoid. Real breakage is untouched: a board that
    # 403s, 404s or returns an unreadable payload records `fetch_*`/`extracted_empty`, which are
    # attempts and still raise the signal.
    assert result.tally.is_silent_outage is False


@respx.mock
def test_the_posting_taken_is_the_provider_s_own_row_not_a_rebuilt_one(tmp_path):
    """Verbatim, and this is the assertion that says so field by field.

    Rebuilding the row from the aggregator hit would put the hiring.cafe `apply_url`, the
    `workplace_*` location text and the hit itself into a row that a later board scan writes
    differently for the SAME `(company_id, provider_posting_id)` -- so the two converge onto one
    row and rewrite each other as revisions forever. Taking greenhouse's row means the lane
    hands `apply_board` what the scan stage would have handed it.
    """
    hits = _reachable("acme-inline", range(2))
    _mock_search(hits)
    _mock_boards(hits)
    board = GreenhouseProvider().parse_payload(greenhouse_board_payload(hits), url="x")
    expected = {posting.provider_posting_id: posting for posting in board.postings}

    result = HiringCafeLane().collect(_fetcher(tmp_path), lambda provider, slug: True)

    for posting in result.snapshots[0].snapshot.postings:
        assert posting == expected[posting.provider_posting_id]
    posting = result.snapshots[0].snapshot.postings[0]
    # Greenhouse's own fields, none of them the aggregator's.
    assert posting.url.startswith("https://boards.greenhouse.io/acme-inline/jobs/")
    assert posting.body_text and "hiring.cafe" not in posting.body_text
    assert posting.raw_json.get("absolute_url") == posting.url
    assert "hit" not in posting.raw_json
    # The synthesized summary the SSR payload does carry never becomes the frozen JD.
    assert "v5_processed_job_data" not in posting.raw_json


@respx.mock
def test_the_synthesized_summary_never_reaches_a_stored_body(tmp_path):
    """The keystone invariant, as a trap rather than a claim.

    `v5_processed_job_data.requirements_summary` is hiring.cafe's OWN synthesis, not the
    employer's prose, so an `INELIGIBLE` quoting it would attribute words to an employer that
    never wrote them. The marker below appears in that field and NOWHERE in the greenhouse
    board response, so it can only reach `body_text` by the summary being used as the body.
    """
    marker = "SYNTHESIZED-SUMMARY-MUST-NOT-BE-QUOTED"
    hits = _reachable("acme-inline", range(2))
    hits = [
        dict(hit, v5_processed_job_data=dict(hit["v5_processed_job_data"],
                                             requirements_summary=marker,
                                             technical_tools=[marker]))
        for hit in hits
    ]
    _mock_search(hits)
    _mock_boards(hits)

    result = HiringCafeLane().collect(_fetcher(tmp_path), lambda provider, slug: True)

    stored = [
        posting
        for company in result.snapshots
        for posting in company.snapshot.postings
    ]
    assert stored, "nothing was stored, so this trap proved nothing"
    for posting in stored:
        assert marker not in posting.body_text
        assert marker not in json.dumps(posting.raw_json)


@respx.mock
def test_the_greenhouse_convergence_case_is_keyed_on_greenhouse(tmp_path):
    """The recorded 8/160: a hit whose `apply_url` names a board a provider already scans."""
    hits = search_hits()
    _mock_search(hits)
    _mock_boards(hits)

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
def test_the_request_budget_caps_board_gets_and_counts_what_it_skipped(tmp_path):
    """The budget's unit is REQUESTS, as it always was; here one request is one company."""
    hits = (
        _reachable("acme-one", range(4))
        + _reachable("acme-two", range(4, 8))
        + _reachable("acme-three", range(8, 12))
    )
    _mock_search(hits)
    boards = _mock_boards(hits)

    result = HiringCafeLane(posting_budget=2).collect(
        _fetcher(tmp_path), lambda provider, slug: True
    )

    assert sum(route.call_count for route in boards.values()) == 2
    assert result.tally.counts["body_inline"] == 8
    # The third company was seen and never requested, and every one of its hits is counted.
    assert result.tally.counts["not_attemptable"] == 4
    assert result.tally.attempted == 12


@respx.mock
def test_a_board_row_with_an_empty_body_is_not_reported_as_resolved(tmp_path):
    """An ABSENT body is not a body, however structured the field it arrived in.

    The old two-hop path ran `assess_body` and rejected this as `extracted_empty`. Taking the
    provider's row verbatim dropped that floor along with the login-wall check, and an empty
    `content` then stored a posting with a blank body, counted `body_inline`, and raised no
    outage. The keystone invariant needs a real span to quote, and a blank body has none.
    """
    hits = _reachable("acme-blank", range(2))
    _mock_search(hits)
    # Derived from the pinned greenhouse capture and then BLANKED, so the row is otherwise a
    # real one: same shape, same ids, only the body emptied.
    blanked = json.loads(greenhouse_board_payload(hits))
    for job in blanked["jobs"]:
        job["content"] = ""
    _mock_boards(hits, content=json.dumps(blanked).encode())

    result = HiringCafeLane().collect(_fetcher(tmp_path), lambda provider, slug: True)

    assert result.tally.counts["body_inline"] == 0
    assert result.tally.counts["extracted_empty"] == 2
    assert result.tally.resolved == 0
    assert result.snapshots == ()


@respx.mock
def test_an_unbodyable_company_never_spends_the_company_cap(tmp_path):
    """The cap rations REQUESTS, and no request is reachable for an unbodyable company.

    This is the defect that made the whole lane deliver nothing: `admits` used to be asked
    before provider support was checked, so aggregator-only companies drank the budget and the
    greenhouse boards -- the only ones a body can be read from -- were refused. Worse, an
    unsupported company writes no snapshot and so is never persisted, making it "new" again on
    the next run and charging the cap forever.

    The cap here admits only the first TWO companies it is offered, and the two unbodyable ones
    are offered first in search order.
    """
    hits = (
        _unreachable("icims-one", range(0, 3))
        + _unreachable("icims-two", range(3, 6))
        + _reachable("acme-inline", range(6, 10))
    )
    _mock_search(hits)
    boards = _mock_boards(hits)

    offered: list[tuple[str, str]] = []

    def admits(provider: str, slug: str) -> bool:
        offered.append((provider, slug))
        return len(offered) <= 2

    result = HiringCafeLane().collect(_fetcher(tmp_path), admits)

    # The two unbodyable companies are never OFFERED, so they cannot spend the cap.
    assert offered == [("greenhouse", "acme-inline")]
    # And the reachable board was actually read.
    assert sum(route.call_count for route in boards.values()) == 1
    assert result.tally.counts["body_inline"] == 4
    # Their hits are still accounted for -- seen, not fetched, never silently dropped.
    assert result.tally.counts["not_attemptable"] == 6


@respx.mock
@pytest.mark.parametrize(
    "status,outcome",
    [(403, "fetch_refused"), (404, "fetch_gone"), (418, "fetch_unavailable")],
)
def test_a_failed_board_get_lands_in_its_own_bucket(tmp_path, status, outcome):
    """Folding these is exactly how the prior art hid an eleven-day outage.

    Keeping them apart is also why the lane issues this GET itself: `Provider.fetch_board`
    turns a typed `FetchFailure` into a status plus a message, and recovering 403 from 404 out
    of that message would be classifying behaviour by string-matching it.
    """
    hits = _reachable("acme-inline", range(4))
    _mock_search(hits)
    _mock_boards(hits, status=status)

    result = HiringCafeLane().collect(_fetcher(tmp_path), lambda provider, slug: True)

    assert result.tally.counts[outcome] == 4
    assert result.tally.resolved == 0
    assert result.tally.is_silent_outage is True
    # A company whose board failed writes no snapshot, so no company row is owed for it.
    assert result.snapshots == ()


@respx.mock
def test_an_unreadable_board_payload_is_extracted_empty(tmp_path):
    """A 200 that decodes to nothing is not a fetch failure and must not read as one."""
    hits = _reachable("acme-inline", range(4))
    _mock_search(hits)
    _mock_boards(hits, content=b"{}")

    result = HiringCafeLane().collect(_fetcher(tmp_path), lambda provider, slug: True)

    assert result.tally.counts["extracted_empty"] == 4
    assert result.tally.counts["fetch_gone"] == 0
    assert result.snapshots == ()


@respx.mock
def test_a_posting_the_employers_board_no_longer_lists_is_gone_not_empty(tmp_path):
    """The aggregator's index lags the employer's board, and that is not a defect here.

    Split from the unreadable-payload case above on purpose: both produce no posting, and only
    one of them means something is wrong with us.
    """
    listed, delisted = _reachable("acme-inline", range(2)), _reachable("acme-inline", range(2, 4))
    _mock_search(listed + delisted)
    respx.get(_board_url("acme-inline")).mock(
        return_value=httpx.Response(200, content=greenhouse_board_payload(listed))
    )

    result = HiringCafeLane().collect(_fetcher(tmp_path), lambda provider, slug: True)

    assert result.tally.counts["body_inline"] == 2
    assert result.tally.counts["fetch_gone"] == 2
    assert result.tally.counts["extracted_empty"] == 0
    assert len(result.snapshots[0].snapshot.postings) == 2


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


@respx.mock
def test_the_retired_per_posting_body_endpoint_is_never_requested(tmp_path):
    """`/api/job-description?id=` was refused on every attempt from run 129 onward.

    Asserted BEHAVIOURALLY, against a route that would have answered: a dead endpoint left in
    place keeps producing measured zeros, which reads as a lane that tried, and the whole point
    of dropping it is that the tally now says "seen and not fetched" instead of "refused". The
    hits below are the aggregator-only case, which is the one that used to reach it.
    """
    retired = respx.route(host="hiringcafe.com", path__startswith="/api/").mock(
        return_value=httpx.Response(200, json={"job": {"job_information": {"description": "x"}}})
    )
    _mock_search(search_hits()[:8])

    result = HiringCafeLane().collect(_fetcher(tmp_path), lambda provider, slug: True)

    assert retired.call_count == 0
    assert result.tally.counts["not_attemptable"] == 8
    assert not hasattr(hiringcafe, "job_description_url")


@respx.mock
def test_a_hit_with_no_title_is_refused_before_its_company_is_paid_for(tmp_path):
    """A posting with no title cannot be ranked or shown, and no GET would buy one.

    The untitled hit sits on its OWN board, so if it were not dropped before the request the
    board GET for it would be made -- which is what the unmocked-route error would show.
    """
    (untitled,) = _reachable("acme-untitled", range(1))
    untitled = dict(untitled, job_information=None)
    titled = _reachable("acme-inline", range(1, 3))
    search = _mock_search([untitled, *titled])
    boards = _mock_boards(titled)

    result = HiringCafeLane().collect(_fetcher(tmp_path), lambda provider, slug: True)

    assert search.call_count == 1
    assert "acme-untitled" not in boards
    assert boards["acme-inline"].call_count == 1
    assert result.tally.counts["not_attemptable"] == 1
    assert result.tally.counts["body_inline"] == 2


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
    _mock_boards(hits)

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
    shared = _reachable("acme-inline", range(3))
    _mock_facet("software engineer", shared)
    _mock_facet("backend engineer", shared)
    boards = _mock_boards(shared)

    result = HiringCafeLane(search_facets=("software engineer", "backend engineer")).collect(
        _fetcher(tmp_path), lambda provider, slug: True
    )

    # ONE board GET covers all three postings across both facets, not one per facet.
    assert boards["acme-inline"].call_count == 1
    assert result.tally.counts["body_inline"] == 3
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
    first = [_reachable(f"acme-a{n}", [n]) [0] for n in range(20)]
    second = [_reachable(f"acme-b{n}", [20 + n])[0] for n in range(20)]
    _mock_facet("software engineer", first)
    _mock_facet("ios engineer", second)
    _mock_boards(first + second)

    result = HiringCafeLane(
        posting_budget=6, search_facets=("software engineer", "ios engineer")
    ).collect(_fetcher(tmp_path), lambda provider, slug: True)

    reached = {company.slug for company in result.snapshots}
    from_first = {hit["board_token"] for hit in first} & reached
    from_second = {hit["board_token"] for hit in second} & reached
    assert len(reached) == 6  # the budget's six requests, one company each
    assert from_first and from_second, "one facet took the entire body budget"


@respx.mock
def test_the_snapshot_records_the_facet_page_a_company_was_found_on(tmp_path):
    """Provenance has to name the URL actually requested. Recording the unfaceted root would
    cite a page this run never fetched.
    """
    hits = _reachable("acme-inline", range(2))
    _mock_facet("ios engineer", hits)
    _mock_boards(hits)

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
    boards = _mock_any_board()

    with pytest.raises(SearchPageError, match="facet"):
        HiringCafeLane(search_facets=("software engineer", "ios engineer")).collect(
            _fetcher(tmp_path), lambda provider, slug: True
        )

    assert boards.call_count == 0


@respx.mock
def test_one_empty_facet_among_several_is_tolerated_rather_than_fatal(tmp_path):
    """A single unproductive target title is a profile-data matter, not an outage. Raising here
    would let one odd title in a profile disable the whole lane.
    """
    hits = _reachable("acme-inline", range(3))
    _mock_facet("software engineer", hits)
    _mock_facet("zzq not a real role", None)
    _mock_boards(hits)

    result = HiringCafeLane(
        search_facets=("software engineer", "zzq not a real role")
    ).collect(_fetcher(tmp_path), lambda provider, slug: True)

    assert result.tally.counts["body_inline"] == 3
    assert result.tally.is_silent_outage is False


@respx.mock
def test_one_facet_whose_request_fails_does_not_cost_the_others_their_results(tmp_path):
    """Per-facet isolation, the same shape D-307 gave a board's apply failure.

    The unfaceted lane made ONE search request, so a failure there could only cost that one
    request. A faceted lane makes fourteen, and letting the seventh abort the collection
    discards six facets' worth of already-paid-for work. The fetcher has already retried with
    backoff by the time it raises, so this is the surviving-failure case, not a transient one.
    """
    hits = _reachable("acme-inline", range(3))
    _mock_facet("software engineer", hits)
    respx.get(_page("ios engineer", 0)).mock(return_value=httpx.Response(503))
    _mock_boards(hits)

    result = HiringCafeLane(
        search_facets=("software engineer", "ios engineer")
    ).collect(_fetcher(tmp_path), lambda provider, slug: True)

    assert result.tally.counts["body_inline"] == 3
    assert result.tally.is_silent_outage is False


@respx.mock
def test_every_facet_request_failing_raises_rather_than_reporting_a_quiet_day(tmp_path):
    """Isolation must not become suppression: if the host refuses every facet, that is the
    outage case and it has to reach the runner, exactly as an all-empty result does."""
    respx.get(url__startswith=f"{SEARCH_URL}?searchState=").mock(
        return_value=httpx.Response(403)
    )
    boards = _mock_any_board()

    with pytest.raises(SearchPageError, match="facet"):
        HiringCafeLane(search_facets=("software engineer", "ios engineer")).collect(
            _fetcher(tmp_path), lambda provider, slug: True
        )

    assert boards.call_count == 0


# --- paging (D-393; `&page=N` measured live 2026-08-31) ------------------------------------
#
# The lane shipped without paging because no page parameter had been evidenced and the
# `?page=` form was disallowed. Both premises are gone: two GETs 1.5s apart returned 143 hits
# on page 0 and 133 on page 1 with ZERO id overlap, so the parameter turns a page rather than
# re-serving one. `LaneResult.search_pages` was `()` for this lane before and is now real
# depth, which is the difference between "the facet ran out" and "the ceiling truncated it".


def test_the_paging_fixture_reproduces_the_probe_s_disjoint_pages():
    """The two recorded numbers, and the one that carries the argument.

    143 and 133 hits are counts; ZERO shared ids is the finding -- it is what separates a real
    offset from a host that re-serves page 0, which is the failure mode paging against someone
    else's `&page=` would otherwise hide. Written as literals here rather than imported, so the
    recorded constants in `hiringcafe_shape` cannot drift without this going red.
    """
    hits = _reachable("acme-inline", range(8))
    page_zero = hiringcafe.parse_search_page(search_page_html(hits[:4], page=0))
    page_one = hiringcafe.parse_search_page(search_page_html(hits[4:], page=1))
    ids = ({hit["objectID"] for hit in page_zero.hits}, {hit["objectID"] for hit in page_one.hits})

    assert SSR_PROBED_PAGE_HITS == (143, 133)
    assert len(ids[0] & ids[1]) == SSR_PROBED_PAGE_OVERLAP == 0


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
    _mock_boards(hits)

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
    hits = _reachable("acme-inline", range(12))
    pages = [
        _mock_page("ios engineer", 0, hits[:4]),
        _mock_page("ios engineer", 1, hits[4:8], is_last_page=True),
        _mock_page("ios engineer", 2, hits[8:12]),
    ]
    _mock_boards(hits[:8])

    result = HiringCafeLane(search_facets=("ios engineer",), search_pages=5).collect(
        _fetcher(tmp_path), lambda provider, slug: True
    )

    assert [route.call_count for route in pages] == [1, 1, 0]
    assert result.search_pages == ((_search_url("ios engineer"), 2),)
    # Both pages' hits reached the tally; the second page is reach, not bookkeeping.
    assert result.tally.counts["body_inline"] == 8


@respx.mock
def test_a_page_that_re_serves_hits_already_held_ends_the_facet(tmp_path):
    """The offset-wrap tail `providers/workday.py` guards, and the stop-honouring-page case.

    A host that answers past the end of a result set with a REPEAT rather than an empty page
    would otherwise burn every remaining request on hits this facet already listed -- and so
    would one that quietly stopped honouring `&page=` at all, which is the failure mode that
    matters here because `&page=` is one parameter on a URL nobody here operates.
    """
    hits = _reachable("acme-inline", range(8))
    pages = [
        _mock_page("ios engineer", 0, hits[:4]),
        _mock_page("ios engineer", 1, hits[:4]),  # the same four hits again
        _mock_page("ios engineer", 2, hits[4:]),
    ]
    _mock_boards(hits[:4])

    result = HiringCafeLane(search_facets=("ios engineer",), search_pages=4).collect(
        _fetcher(tmp_path), lambda provider, slug: True
    )

    assert [route.call_count for route in pages] == [1, 1, 0]
    assert result.search_pages == ((_search_url("ios engineer"), 2),)
    assert result.tally.counts["body_inline"] == 4


@respx.mock
def test_a_later_page_failing_keeps_the_pages_already_paid_for(tmp_path):
    """Page 1 and page N are not the same event.

    A facet refused on its FIRST page produced nothing and is a failure its caller must count;
    one refused on page 4 keeps the three pages already bought. Folding them would either
    discard paid-for reach or hide the refusal.
    """
    hits = _reachable("acme-inline", range(4))
    _mock_page("ios engineer", 0, hits)
    respx.get(_page("ios engineer", 1)).mock(return_value=httpx.Response(503))
    _mock_boards(hits)

    result = HiringCafeLane(search_facets=("ios engineer",), search_pages=3).collect(
        _fetcher(tmp_path), lambda provider, slug: True
    )

    assert result.tally.counts["body_inline"] == 4
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
    _mock_boards(hits)

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
    hits = _reachable("acme-inline", range(8))
    _mock_page("", 0, hits[:4])
    _mock_page("", 1, hits[4:8], is_last_page=True)
    _mock_boards(hits)

    result = HiringCafeLane(search_pages=3).collect(
        _fetcher(tmp_path), lambda provider, slug: True
    )

    assert result.search_pages == ((_search_url(), 2),)
    assert result.tally.counts["body_inline"] == 8


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
    _mock_boards(hits)

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
    _mock_boards(hits)

    HiringCafeLane().collect(_fetcher(tmp_path), lambda provider, slug: True)

    assert root.calls[0].request.headers["Accept"].startswith("text/html")


@respx.mock
def test_a_provider_board_gets_the_identifying_ua_the_aggregator_does_not(tmp_path):
    """D22, restored per request on the one route that is owed it.

    `pipeline._lane_fetcher` gives this lane's client a BROWSER UA, because the aggregator
    refused the honest one's request shape (D-369). An ATS provider's own board is a different
    matter: it answers us honestly and is owed our name. So the board GET puts the identifying
    UA back, and the navigation header set -- which describes a top-level HTML navigation --
    must not follow it onto a JSON API.

    Driven through a browser-UA client on purpose. Against the default `Fetcher` the client's
    UA is ALREADY the identifying one, so this test would pass with the per-request header
    deleted and prove nothing.
    """
    hits = _reachable("acme-inline", range(2))
    search = _mock_facet("software engineer", hits)
    boards = _mock_boards(hits)

    HiringCafeLane(search_facets=("software engineer",)).collect(
        _browser_fetcher(tmp_path), lambda provider, slug: True
    )

    assert boards["acme-inline"].call_count == 1
    board_request = boards["acme-inline"].calls[0].request
    assert board_request.headers["User-Agent"] == identifying_user_agent()
    assert board_request.headers["User-Agent"].startswith("boardwatch/")
    assert "Sec-Fetch-Mode" not in board_request.headers
    assert "Upgrade-Insecure-Requests" not in board_request.headers
    assert board_request.headers["Accept"] == "*/*"
    # ...and the aggregator still gets the browser UA the lane client carries.
    assert search.calls[0].request.headers["User-Agent"] == _BROWSER_UA
    assert search.calls[0].request.headers["Accept"].startswith("text/html")


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
