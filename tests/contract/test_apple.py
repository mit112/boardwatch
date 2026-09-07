"""Apple contract tests. Apple is the FIRST provider with no JSON API at all: its data is a
double-encoded JSON blob inlined in a server-rendered HTML document, and its `totalRecords` is
a count of position-LOCATION rows rather than of postings. Every property asserted here was
measured live on 2026-09-07 -- see tests/fixtures/apple/README.md."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from boardwatch.core.models import BoardRequest, ResponseValidators
from boardwatch.core.politeness import Fetcher
from boardwatch.core.settings import Settings
from boardwatch.providers.apple import (
    AppleProvider,
    hydration_data,
    parse_posting,
)
from boardwatch.providers.base import BoardHealth

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "apple"
SLUG = "united-states"
FILTER = "united-states-USA"
PAGE1 = f"https://jobs.apple.com/en-us/search?location={FILTER}&page=1"

provider = AppleProvider()


def _fx(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _page(blob: dict[str, Any], *, nonce: str = "yX/RheVcP/f65gmq3e5kng==") -> bytes:
    """The hydration document in the RECORDED shape: `JSON.parse("<escaped json>")`, where the
    argument is a JSON string literal whose contents are themselves JSON.

    `json.dumps(json.dumps(blob))` is exactly that double encoding, so this exercises the
    provider's two-step decode against genuine `\\"` escaping rather than a hand-rolled
    approximation. Built here instead of being filed as an .html fixture because .html is
    outside DATA_SUFFIXES and a file would be pinned by nothing -- the same reasoning that
    keeps Eightfold's bootstrap page and Workday's maintenance page inline.
    """
    payload = json.dumps(json.dumps(blob))
    return (
        '<!DOCTYPE html><html><head><title>Careers - Careers at Acme</title></head>'
        '<body><div id="app"></div>'
        f'<script nonce="{nonce}">window.__staticRouterHydrationData = '
        f"JSON.parse({payload});</script>"
        '<div id="portal"></div></body></html>'
    ).encode()


#: A served document with no hydration blob at all -- the shape a front-end change takes.
NO_HYDRATION = (
    b"<!DOCTYPE html><html><head><title>Careers</title></head>"
    b'<body><div id="app"></div><script nonce="abc">window.__someOtherGlobal = 1;</script>'
    b"</body></html>"
)


def _fetcher(tmp_path: Path) -> Fetcher:
    return Fetcher(
        Settings(
            data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1,
            per_host_delay_seconds=0.25,
        )
    )


def _request(
    known: frozenset[str] = frozenset(), budget: int = 50,
    validators: ResponseValidators | None = None, slug: str = SLUG,
) -> BoardRequest:
    return BoardRequest(
        provider="apple", slug=slug, url=provider.board_url(slug),
        known_posting_ids=known, detail_budget=budget, validators=validators,
    )


def _search_url(page: int, filter_value: str = FILTER) -> str:
    return f"https://jobs.apple.com/en-us/search?location={filter_value}&page={page}"


def _detail_url(posting_id: str, slug: str) -> str:
    return f"https://jobs.apple.com/en-us/details/{posting_id}/{slug}"


def _detail_blob(row: dict[str, Any]) -> dict[str, Any]:
    """A detail document for a listing row, in the recorded shape, keyed off the row itself so
    a fixture with N rows needs no per-row hand-mocking. Sections are DISTINCT from the row's
    teaser `jobSummary`, which is what makes the teaser-fill assertions meaningful."""
    template = _fx("detail_normal.json")
    jobs = dict(template["loaderData"]["jobDetails"]["jobsData"])
    jobs.update(
        {
            "positionId": row["positionId"],
            "postingTitle": row["postingTitle"],
            "transformedPostingTitle": row["transformedPostingTitle"],
            "jobNumber": row["positionId"],
            "locations": row["locations"],
            "homeOffice": row["homeOffice"],
            "description": f"Detail body for {row['postingTitle']}.",
            "jobSummary": f"Detail summary for {row['postingTitle']}.",
        }
    )
    return {
        "loaderData": {
            "root": template["loaderData"]["root"],
            "jobDetails": {"jobsData": jobs, "requestUrl": "", "metaLinks": []},
        },
        "actionData": None,
        "errors": None,
    }


def _mock_search(page: int, blob: dict[str, Any], filter_value: str = FILTER) -> None:
    respx.get(_search_url(page, filter_value)).mock(
        return_value=httpx.Response(200, content=_page(blob))
    )


def _mock_details(*rows: dict[str, Any]) -> None:
    """One detail route per DISTINCT posting id in the given rows."""
    seen: set[str] = set()
    for row in rows:
        if row.get("positionId") is None or str(row["positionId"]) in seen:
            continue
        seen.add(str(row["positionId"]))
        respx.get(
            _detail_url(str(row["positionId"]), row["transformedPostingTitle"])
        ).mock(return_value=httpx.Response(200, content=_page(_detail_blob(row))))


# ---------------------------------------------------------------- slug contract


def test_the_location_catalog_is_closed_and_an_unknown_token_raises() -> None:
    """Property 2: an unknown location code is answered with `totalRecords: 0` and no error,
    so an out-of-catalog slug must be a REFUSAL. Were it accepted, the board would be watched
    forever as one that is merely empty today -- and an empty `complete` board is the one
    status that authorizes apply_board to close every posting it holds."""
    assert provider.normalize_slug("united-states") == "united-states"
    assert provider.normalize_slug("  United-States  ") == "united-states"
    for bad in ("", "usa", "united-states-USA", "narnia", "en-us", "australia/nsw"):
        with pytest.raises(ValueError, match="country boards"):
            provider.normalize_slug(bad)


def test_no_jobs_apple_com_path_can_name_a_board() -> None:
    """A board is a country and a country is a QUERY parameter, so every URL extracts nothing
    and the paste path falls through to `slug_help` rather than handing `normalize_slug` the
    locale segment (`en-us`) and producing a diagnostic about a word nobody typed."""
    assert AppleProvider.slug_from_path("jobs.apple.com", ["en-us", "search"]) is None
    assert AppleProvider.slug_from_path(
        "jobs.apple.com", ["en-us", "details", "900000001", "x"]
    ) is None
    assert "apple:united-states" in provider.slug_help


def test_the_catalog_maps_every_slug_to_a_distinct_location_code() -> None:
    """Property 3: the server reads ONLY the trailing `-CODE`, so two slugs mapping to the
    same code would be two names for one board -- and the coverage of one would be
    double-counted while the other looked live."""
    from boardwatch.providers.apple import _LOCATIONS

    codes = [value.rsplit("-", 1)[-1] for value in _LOCATIONS.values()]
    assert len(codes) == len(set(codes)) == len(_LOCATIONS)
    # every code is the UPPERCASE form the server requires (`united-states-usa` returns 0)
    assert all(code.isupper() for code in codes)


def test_board_url_always_carries_the_filter_and_is_the_page_one_key() -> None:
    """Property 1: a bare `/en-us/search` is 301'd to the US board, so a URL with no explicit
    `location` can be silently re-scoped to a different corpus by the redirect."""
    assert provider.board_url(SLUG) == PAGE1
    assert provider.board_url("  UNITED-STATES  ") == PAGE1
    for slug in ("india", "japan", "china"):
        assert "location=" in provider.board_url(slug)
        assert provider.board_url(slug).endswith("&page=1")


# ---------------------------------------------------------------- the happy path


@respx.mock
def test_a_complete_board_reports_postings_not_rows(tmp_path: Path) -> None:
    """Property 4: `search_normal.json` is 4 ROWS holding 3 DISTINCT postings -- rows 2 and 3
    are one multi-location requisition. `board_enumerated` counts postings (3), and
    `board_reported_total` is None because `totalRecords` (4) counts rows and would make the
    D-271 subtraction a permanent, uncloseable shortfall."""
    blob = _fx("search_normal.json")
    rows = blob["loaderData"]["search"]["searchResults"]
    _mock_search(1, blob)
    _mock_details(*rows)

    snap = provider.fetch_board(_fetcher(tmp_path), _request())

    assert snap.status == "complete", snap.error
    assert snap.error is None
    assert len(rows) == 4
    assert blob["loaderData"]["search"]["totalRecords"] == 4
    assert len(snap.postings) == 3
    assert snap.board_enumerated == 3
    assert snap.board_reported_total is None
    assert snap.detail_deferred == 0
    assert snap.listed_ids == {"900000001", "900000002", "900000003"}
    assert snap.url == PAGE1


@respx.mock
def test_one_detail_fetch_per_posting_not_per_row(tmp_path: Path) -> None:
    """The multi-location requisition is two rows and ONE document; fetching per row would
    spend the budget twice on the same detail page."""
    blob = _fx("search_normal.json")
    rows = blob["loaderData"]["search"]["searchResults"]
    _mock_search(1, blob)
    _mock_details(*rows)

    provider.fetch_board(_fetcher(tmp_path), _request())

    detail_calls = [
        call.request.url.path
        for call in respx.calls
        if "/details/" in call.request.url.path
    ]
    assert len(detail_calls) == 3
    assert len(set(detail_calls)) == 3


@respx.mock
def test_the_body_is_the_detail_sections_and_never_the_listing_teaser(
    tmp_path: Path,
) -> None:
    """The listing's `jobSummary` is a TEASER (measured 626..1055 chars). D-492 is the defect
    where a teaser was materialised as if it were a body; the four detail sections are the
    body, in order, and the teaser must appear nowhere in it."""
    blob = _fx("search_normal.json")
    rows = blob["loaderData"]["search"]["searchResults"]
    _mock_search(1, blob)
    _mock_details(*rows)

    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    posting = next(p for p in snap.postings if p.provider_posting_id == "900000001")

    teaser = rows[0]["jobSummary"]
    assert "This teaser is truncated by the listing endpoint." in teaser
    assert teaser.strip() not in posting.body_text
    assert "Detail summary for Widget Reliability Engineer." in posting.body_text
    assert "Detail body for Widget Reliability Engineer." in posting.body_text
    assert "Hold a widget certification." in posting.body_text
    assert "Read a sprocket schematic." in posting.body_text
    # the four sections keep their recorded order
    assert posting.body_text.index("Detail summary") < posting.body_text.index("Detail body")
    assert posting.body_text.index("Detail body") < posting.body_text.index("Hold a widget")
    assert posting.body_text.index("Hold a widget") < posting.body_text.index("Read a sprocket")


def test_the_detail_payload_supplies_every_location_of_a_multi_location_posting() -> None:
    """Property 4: a listing row names only the location it was served for, while the
    posting's own page carries all of them -- so `locations` is read from the detail first.
    Parsed directly from the recorded fixture rather than through a mocked fetch."""
    detail = _fx("detail_normal.json")["loaderData"]["jobDetails"]["jobsData"]
    row = next(
        r for r in _fx("search_normal.json")["loaderData"]["search"]["searchResults"]
        if r["positionId"] == "900000002"
    )
    assert len(row["locations"]) == 1

    posting = parse_posting(row, detail)

    assert posting.locations == ["Shelbyville", "Ogdenville"]
    assert posting.provider_posting_id == "900000002"
    assert posting.title == "Sprocket Design Lead"
    assert posting.url == (
        "https://jobs.apple.com/en-us/details/900000002/sprocket-design-lead"
    )
    # `teamNames` is a LIST; both teams are kept rather than one being dropped
    assert posting.department == "Acme Widgets, Acme Sprockets"
    assert posting.remote_policy == "remote"  # homeOffice: true
    assert posting.raw_json["listed"]["positionId"] == "900000002"
    assert posting.raw_json["detail"]["positionId"] == "900000002"


def test_posted_at_comes_from_the_iso_field_never_the_display_string() -> None:
    """`postingDate` is a human string ("Sep 07, 2026") whose month name would be read through
    the process locale; `postDateInGMT` is ISO 8601. The listing spells it with nanosecond
    precision and a `Z`, the detail with milliseconds and an offset."""
    rows = _fx("search_normal.json")["loaderData"]["search"]["searchResults"]
    detail = _fx("detail_normal.json")["loaderData"]["jobDetails"]["jobsData"]

    posting = parse_posting(rows[1], detail)
    assert posting.posted_at == datetime(2026, 9, 7, 12, 42, 42, 277000)
    assert posting.updated_at is None

    # the listing's own nanosecond `Z` form parses too, and truncates to microseconds
    listing_only = parse_posting(rows[0], {**detail, "postDateInGMT": None})
    assert rows[0]["postDateInGMT"] == "2026-09-07T05:22:08.324174937Z"
    assert listing_only.posted_at == datetime(2026, 9, 7, 5, 22, 8, 324174)


def test_no_salary_is_ever_mined(tmp_path: Path) -> None:
    """Neither payload carries a salary field, so all four scalars stay NULL (D19)."""
    rows = _fx("search_normal.json")["loaderData"]["search"]["searchResults"]
    detail = _fx("detail_normal.json")["loaderData"]["jobDetails"]["jobsData"]
    posting = parse_posting(rows[1], detail)
    assert posting.salary_min is None
    assert posting.salary_max is None
    assert posting.salary_currency is None
    assert posting.salary_period is None


def test_a_false_home_office_is_unknown_rather_than_onsite() -> None:
    """`homeOffice: false` is the feed's default for anything unstated, and no probe can
    separate "this role is onsite" from "the field was not set". There is also deliberately no
    location-TEXT fallback: measured over ~140 US rows no location name contained "remote" or
    "home" even once, so a text rule could never fire."""
    rows = _fx("search_normal.json")["loaderData"]["search"]["searchResults"]
    detail = _fx("detail_normal.json")["loaderData"]["jobDetails"]["jobsData"]
    assert parse_posting(rows[0], {**detail, "homeOffice": False}).remote_policy == "unknown"
    assert parse_posting(rows[0], {**detail, "homeOffice": True}).remote_policy == "remote"
    # a location literally named "Remote" must NOT move the verdict
    remote_named = {**detail, "homeOffice": False,
                    "locations": [{"id": "postLocation-X", "name": "Remote"}]}
    assert parse_posting(rows[0], remote_named).remote_policy == "unknown"


# ---------------------------------------------------------------- pagination


@respx.mock
def test_pagination_walks_pages_and_stops_on_a_short_page(tmp_path: Path) -> None:
    """Property 5: the page size is a server-fixed 20 and paging is 1-indexed. A page of 20
    forces another request; a page of 2 ends the walk. Page 3 is deliberately NOT mocked, so a
    walk that did not stop would raise on an unmocked route."""
    full = _fx("search_page_full.json")
    short = _fx("search_page_short.json")
    _mock_search(1, full)
    _mock_search(2, short)
    _mock_details(*full["loaderData"]["search"]["searchResults"])
    _mock_details(*short["loaderData"]["search"]["searchResults"])

    snap = provider.fetch_board(_fetcher(tmp_path), _request(budget=100))

    assert snap.status == "complete", snap.error
    assert len(snap.postings) == 22
    assert snap.board_enumerated == 22
    search_calls = [
        str(call.request.url) for call in respx.calls if "/search" in call.request.url.path
    ]
    assert search_calls == [_search_url(1), _search_url(2)]


@respx.mock
def test_total_records_is_read_from_page_one_only(tmp_path: Path) -> None:
    """Property 5: past the last page the server reports `totalRecords: 0`. Reading a later
    page's number would rewrite the denominator to zero and hide a truncated walk."""
    full = _fx("search_page_full.json")
    short = dict(_fx("search_page_short.json"))
    # page 2 reports 0, exactly as an over-page does live
    short["loaderData"]["search"]["totalRecords"] = 0
    _mock_search(1, full)
    _mock_search(2, short)
    _mock_details(*full["loaderData"]["search"]["searchResults"])
    _mock_details(*short["loaderData"]["search"]["searchResults"])

    snap = provider.fetch_board(_fetcher(tmp_path), _request(budget=100))

    # 22 rows collected against page 1's stated 22 -> complete, not a spurious shortfall
    assert snap.status == "complete", snap.error


@respx.mock
def test_a_short_walk_against_the_stated_row_count_forces_partial(tmp_path: Path) -> None:
    """A short page is not proof the board ended: a degraded backend serving 3 rows on a full
    page would otherwise terminate the walk with `complete` and a truncated inventory, and
    `complete` is the status that authorizes apply_board to close what it no longer sees."""
    blob = _fx("search_normal.json")
    blob["loaderData"]["search"]["totalRecords"] = 40  # board claims far more rows than served
    rows = blob["loaderData"]["search"]["searchResults"]
    _mock_search(1, blob)
    _mock_details(*rows)

    snap = provider.fetch_board(_fetcher(tmp_path), _request())

    assert snap.status == "partial"
    assert snap.error is not None
    assert "collected 4 of 40 rows" in snap.error
    # the postings are still returned; only the status is downgraded
    assert len(snap.postings) == 3


# ---------------------------------------------------------------- RED-FIRST: the four guards


@respx.mock
def test_a_missing_hydration_blob_is_an_error_never_an_empty_board(
    tmp_path: Path,
) -> None:
    """RED FIRST. A served document with no hydration blob is the signature of Apple changing
    its front end. Reading it as EMPTY would report "this board has no jobs", and an empty
    `complete` board authorizes apply_board to close every posting it holds."""
    respx.get(_search_url(1)).mock(return_value=httpx.Response(200, content=NO_HYDRATION))

    fetcher = _fetcher(tmp_path)
    snap = provider.fetch_board(fetcher, _request())

    assert snap.status == "failed"
    assert snap.postings == []
    assert snap.error is not None
    assert "no window.__staticRouterHydrationData blob" in snap.error
    assert provider.healthcheck(fetcher, SLUG) is BoardHealth.ERROR
    assert provider.healthcheck(fetcher, SLUG) is not BoardHealth.EMPTY


@respx.mock
def test_a_blob_that_will_not_double_decode_is_an_error(tmp_path: Path) -> None:
    """RED FIRST. The payload is a JSON string literal whose contents are themselves JSON. A
    blob that decodes once and then fails is the half-broken case, and it must not read as an
    empty board either."""
    broken = (
        b"<!DOCTYPE html><html><body><script>window.__staticRouterHydrationData = "
        b'JSON.parse("{not json at all}");</script></body></html>'
    )
    respx.get(_search_url(1)).mock(return_value=httpx.Response(200, content=broken))

    fetcher = _fetcher(tmp_path)
    snap = provider.fetch_board(fetcher, _request())

    assert snap.status == "failed"
    assert snap.error is not None
    assert "hydration payload is not JSON" in snap.error
    assert provider.healthcheck(fetcher, SLUG) is BoardHealth.ERROR


@respx.mock
def test_a_redirect_that_changes_the_filter_is_an_error_not_a_board(
    tmp_path: Path,
) -> None:
    """RED FIRST, property 1. A bare search URL is 301'd to `location=united-states-USA`, and
    the two scopes report different totals (4,509 vs 6,108). If a fetch for one board is
    re-scoped to another, the rows served belong to a different corpus -- filing them under
    this slug would merge two boards under one name."""
    other = "india-INDC"
    respx.get(_search_url(1)).mock(
        return_value=httpx.Response(302, headers={"Location": _search_url(1, other)})
    )
    other_board = _fx("search_normal.json")
    _mock_search(1, other_board, other)
    # the re-scoped board's details are mocked too, so a provider WITHOUT the guard would
    # succeed and file another country's postings under this slug -- which is the failure this
    # asserts against, rather than tripping over an unmocked route.
    _mock_details(*other_board["loaderData"]["search"]["searchResults"])

    fetcher = _fetcher(tmp_path)
    snap = provider.fetch_board(fetcher, _request())

    assert snap.status == "failed"
    assert snap.postings == []
    assert snap.error is not None
    assert "re-scoped by a redirect" in snap.error
    assert f"location='{FILTER}'" in snap.error
    assert provider.healthcheck(fetcher, SLUG) is BoardHealth.ERROR


@respx.mock
def test_a_redirect_that_preserves_the_filter_is_accepted(tmp_path: Path) -> None:
    """The guard is on the FILTER, not on redirection itself: a redirect that keeps the board
    the slug asked for must still be read, or an infrastructure change at Apple's edge would
    fail every board."""
    respx.get(_search_url(1)).mock(
        return_value=httpx.Response(
            302, headers={"Location": f"{_search_url(1)}&utm_source=x"}
        )
    )
    blob = _fx("search_normal.json")
    respx.get(f"{_search_url(1)}&utm_source=x").mock(
        return_value=httpx.Response(200, content=_page(blob))
    )
    _mock_details(*blob["loaderData"]["search"]["searchResults"])

    snap = provider.fetch_board(_fetcher(tmp_path), _request())

    assert snap.status == "complete", snap.error
    assert len(snap.postings) == 3


@respx.mock
def test_the_detail_budget_defers_rather_than_filling_the_body_with_the_teaser(
    tmp_path: Path,
) -> None:
    """RED FIRST, and the D-492 defect this ticket exists not to reproduce. With a budget of 1,
    two of the three postings must be DEFERRED: not materialised at all, still in
    `listed_ids` so apply_board does not close them, and counted in `detail_deferred`. The
    teaser must not be promoted into a body for them."""
    blob = _fx("search_normal.json")
    rows = blob["loaderData"]["search"]["searchResults"]
    _mock_search(1, blob)
    _mock_details(*rows)

    snap = provider.fetch_board(_fetcher(tmp_path), _request(budget=1))

    assert snap.status == "partial"
    assert snap.error is not None
    assert "detail budget of 1 exceeded (3 unseen postings)" in snap.error
    # exactly one materialised; the other two carry NOTHING rather than a teaser body
    assert len(snap.postings) == 1
    assert snap.detail_deferred == 2
    # the deferred ids are still the board's live inventory, so nothing is closed
    assert snap.listed_ids == {"900000001", "900000002", "900000003"}
    assert snap.board_enumerated == 3
    # only one detail document was fetched
    assert sum(1 for c in respx.calls if "/details/" in c.request.url.path) == 1


@respx.mock
def test_a_deferred_posting_is_repaired_by_the_next_run(tmp_path: Path) -> None:
    """The deferral's drain: a deferred row was never stored, so it is still absent from
    `known_posting_ids` next scan and its detail is fetched then. Without this the budget
    would strand a posting permanently body-less."""
    blob = _fx("search_normal.json")
    rows = blob["loaderData"]["search"]["searchResults"]
    _mock_search(1, blob)
    _mock_details(*rows)
    fetcher = _fetcher(tmp_path)

    first = provider.fetch_board(fetcher, _request(budget=1))
    stored = frozenset(p.provider_posting_id for p in first.postings)
    second = provider.fetch_board(fetcher, _request(known=stored, budget=50))

    assert first.detail_deferred == 2
    assert len(stored) == 1
    # the second run picks up exactly the two the budget deferred, with real bodies
    assert second.detail_deferred == 0
    assert {p.provider_posting_id for p in second.postings} == (
        {"900000001", "900000002", "900000003"} - stored
    )
    assert all(p.body_text for p in second.postings)


@respx.mock
def test_board_enumerated_is_counted_before_a_parse_drop(tmp_path: Path) -> None:
    """RED FIRST, D-271. `board_enumerated` is a LISTING count: it must be taken off the raw
    rows before a detail failure drops a posting, or `total - enumerated` silently becomes a
    parse-failure count and the persisted column means something different for this provider
    than for every other one."""
    blob = _fx("search_normal.json")
    rows = blob["loaderData"]["search"]["searchResults"]
    _mock_search(1, blob)
    _mock_details(*rows)
    # one posting's detail answers the property-7 dead shape: a 200 with no jobDetails
    respx.get(_detail_url("900000003", "cog-quality-analyst")).mock(
        return_value=httpx.Response(200, content=_page(_fx("detail_missing.json")))
    )

    snap = provider.fetch_board(_fetcher(tmp_path), _request())

    assert snap.status == "partial"
    assert len(snap.postings) == 2          # the dropped one is NOT materialised
    assert snap.board_enumerated == 3       # but it WAS listed, and is counted as listed
    assert "900000003" in snap.listed_ids   # and it is not closed
    assert snap.error is not None
    assert "jobDetails" in snap.error


@respx.mock
def test_an_id_less_row_is_excluded_from_the_enumeration_rather_than_counted(
    tmp_path: Path,
) -> None:
    """A row with no `positionId` is a posting we cannot fetch, dedupe or close, so it is
    excluded from `board_enumerated` and reported as a shortfall. Keeping it would mint a
    posting keyed by the literal "None", colliding with every other id-less row under
    UNIQUE(company_id, provider_posting_id) -- the D-492 defect."""
    blob = _fx("search_idless.json")
    rows = blob["loaderData"]["search"]["searchResults"]
    _mock_search(1, blob)
    _mock_details(*rows)

    snap = provider.fetch_board(_fetcher(tmp_path), _request())

    assert snap.status == "partial"
    assert snap.board_enumerated == 2
    assert snap.listed_ids == {"900000001", "900000003"}
    assert "None" not in snap.listed_ids
    assert all(p.provider_posting_id != "None" for p in snap.postings)
    assert snap.error is not None
    assert "skipped 1 rows with no positionId" in snap.error


# ---------------------------------------------------------------- failure modes


@respx.mock
def test_a_dead_detail_is_a_200_and_never_closes_the_posting(tmp_path: Path) -> None:
    """Property 7: an unknown posting id answers HTTP 200 with a valid hydration blob whose
    `loaderData` holds only `root`. Indistinguishable from an edge blip, so the id stays in
    the live inventory and the posting is simply not materialised this run."""
    blob = _fx("search_normal.json")
    rows = blob["loaderData"]["search"]["searchResults"]
    _mock_search(1, blob)
    for row in rows:
        if row["positionId"] is None:
            continue
        respx.get(
            _detail_url(str(row["positionId"]), row["transformedPostingTitle"])
        ).mock(return_value=httpx.Response(200, content=_page(_fx("detail_missing.json"))))

    snap = provider.fetch_board(_fetcher(tmp_path), _request())

    assert snap.status == "partial"
    assert snap.postings == []
    assert snap.listed_ids == {"900000001", "900000002", "900000003"}
    assert snap.board_enumerated == 3
    assert snap.error is not None
    assert "all 3 detail fetches failed" in snap.error


@respx.mock
def test_an_empty_board_is_complete_and_empty_not_failed(tmp_path: Path) -> None:
    """A live but vacant board is a 200 with `searchResults: []` -- a complete, empty
    inventory. Distinct from a missing blob, which is ERROR."""
    _mock_search(1, _fx("search_empty.json"))

    fetcher = _fetcher(tmp_path)
    snap = provider.fetch_board(fetcher, _request())

    assert snap.status == "complete"
    assert snap.postings == []
    assert snap.listed_ids == frozenset()
    assert snap.board_enumerated == 0
    assert provider.healthcheck(fetcher, SLUG) is BoardHealth.EMPTY


@respx.mock
def test_a_first_page_failure_is_failed_and_a_later_page_failure_is_partial(
    tmp_path: Path,
) -> None:
    """Nothing was read when page 1 fails, so the board is `failed`. A later page failing
    still leaves a real, if short, inventory -- so it is `partial` and closes nothing."""
    respx.get(_search_url(1)).mock(return_value=httpx.Response(500))
    fetcher = _fetcher(tmp_path)
    assert provider.fetch_board(fetcher, _request()).status == "failed"

    respx.reset()
    full = _fx("search_page_full.json")
    _mock_search(1, full)
    respx.get(_search_url(2)).mock(return_value=httpx.Response(500))
    _mock_details(*full["loaderData"]["search"]["searchResults"])

    snap = provider.fetch_board(_fetcher(tmp_path), _request(budget=100))
    assert snap.status == "partial"
    assert len(snap.postings) == 20
    assert snap.board_enumerated == 20


@respx.mock
def test_fetch_board_never_raises_on_a_malformed_payload(tmp_path: Path) -> None:
    """Every JSON level is validated before use, so a blob that decodes to the wrong SHAPE is
    a failed snapshot rather than a traceback out of the scan worker."""
    fetcher = _fetcher(tmp_path)
    for payload in ([], {"loaderData": []}, {"loaderData": {"search": []}},
                    {"loaderData": {"search": {"searchResults": {}}}}):
        respx.get(_search_url(1)).mock(
            return_value=httpx.Response(200, content=_page(payload))  # type: ignore[arg-type]
        )
        snap = provider.fetch_board(fetcher, _request())
        assert snap.status == "failed"
        assert snap.postings == []
        respx.reset()


@respx.mock
def test_an_unknown_slug_fails_the_snapshot_rather_than_raising(tmp_path: Path) -> None:
    """`fetch_board` is handed a request whose slug it must re-validate: a board watched
    before a catalog revision must fail its snapshot, not traceback."""
    request = BoardRequest(
        provider="apple", slug="narnia", url=PAGE1, detail_budget=50,
    )
    snap = provider.fetch_board(_fetcher(tmp_path), request)
    assert snap.status == "failed"
    assert snap.error is not None
    assert "invalid apple slug" in snap.error


@respx.mock
def test_a_304_reports_unchanged_even_though_the_live_host_never_sends_one(
    tmp_path: Path,
) -> None:
    """Property 6: Apple sends an ETag and answers 200 to a conditional GET carrying it, so
    `unchanged` is unreachable live. The branch is kept for symmetry and covered by a mock."""
    respx.get(_search_url(1)).mock(return_value=httpx.Response(304))
    snap = provider.fetch_board(
        _fetcher(tmp_path), _request(validators=ResponseValidators(etag='W/"x"'))
    )
    assert snap.status == "unchanged"
    assert snap.postings == []
    assert snap.observed_validators is None


@respx.mock
def test_the_observed_etag_is_echoed_rather_than_discarded(tmp_path: Path) -> None:
    """Property 6: the live host DOES send an ETag (and no Last-Modified). It never yields a
    304 today, but the observation is echoed rather than hardcoded to None so a service that
    starts honouring it needs no code change."""
    headers = _fx("normal_response_headers.json")
    assert headers["last_modified"] is None
    blob = _fx("search_empty.json")
    respx.get(_search_url(1)).mock(
        return_value=httpx.Response(
            200, content=_page(blob), headers={"ETag": headers["etag"]}
        )
    )
    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snap.observed_validators is not None
    assert snap.observed_validators.etag == headers["etag"]
    assert snap.observed_validators.last_modified is None


# ---------------------------------------------------------------- healthcheck


@respx.mock
def test_healthcheck_reports_every_state(tmp_path: Path) -> None:
    fetcher = _fetcher(tmp_path)

    _mock_search(1, _fx("search_normal.json"))
    assert provider.healthcheck(fetcher, SLUG) is BoardHealth.OK
    respx.reset()

    _mock_search(1, _fx("search_empty.json"))
    assert provider.healthcheck(fetcher, SLUG) is BoardHealth.EMPTY
    respx.reset()

    respx.get(_search_url(1)).mock(return_value=httpx.Response(404))
    assert provider.healthcheck(fetcher, SLUG) is BoardHealth.DEAD
    respx.reset()

    respx.get(_search_url(1)).mock(return_value=httpx.Response(403))
    assert provider.healthcheck(fetcher, SLUG) is BoardHealth.ERROR
    respx.reset()

    respx.get(_search_url(1)).mock(side_effect=httpx.ConnectError("no route"))
    assert provider.healthcheck(fetcher, SLUG) is BoardHealth.UNREACHABLE
    respx.reset()

    # an out-of-catalog slug never reaches the network
    assert provider.healthcheck(fetcher, "narnia") is BoardHealth.ERROR


# ---------------------------------------------------------------- the decoder itself


def test_the_hydration_decoder_reads_the_recorded_double_encoding() -> None:
    """The argument to `JSON.parse` is a JSON string literal containing JSON, so it decodes
    twice. Asserted against the shape the live document carries."""
    blob = {"loaderData": {"search": {"searchResults": [], "totalRecords": 0}}}
    assert hydration_data(_page(blob)) == blob
    # the recorded document really is double-encoded: the raw bytes carry \" escapes
    assert b'{\\"loaderData\\"' in _page(blob)


def test_the_decoder_refuses_every_broken_shape() -> None:
    for content, message in (
        (b"<html><body>nothing here</body></html>", "no window.__staticRouterHydrationData"),
        (b'<script>window.__staticRouterHydrationData = JSON.parse("\\q");</script>',
         "not a JSON string literal"),
        (b'<script>window.__staticRouterHydrationData = JSON.parse("nope");</script>',
         "hydration payload is not JSON"),
        (b'<script>window.__staticRouterHydrationData = JSON.parse("[1,2]");</script>',
         "not a JSON object"),
    ):
        with pytest.raises(ValueError, match=message):
            hydration_data(content)
