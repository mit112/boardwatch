"""TikTok contract tests.

The search API is a POST whose tenant is a HEADER (`website-path`), so the assertions pin the
request as much as the answer: without the header the measured answer is a 400. The other
property is the one every paged provider owes: a walk that collects fewer distinct ids than the
board's stated `count` is `partial`, because `complete` is the status that closes postings.
"""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from boardwatch.core.board_urls import parse_board_target
from boardwatch.core.models import BoardRequest
from boardwatch.core.politeness import Fetcher
from boardwatch.core.settings import Settings
from boardwatch.providers.base import BoardHealth
from boardwatch.providers.tiktok import TikTokProvider

pytestmark = pytest.mark.usefixtures("no_real_sleep")

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "tiktok"
SEARCH = "https://api.lifeattiktok.com/api/v1/public/supplier/search/job/posts"
BOARD_URL = f"{SEARCH}#site=tiktok"
PAGE_LIMIT = 5000

provider = TikTokProvider()


def _fixture_json(name: str) -> Any:
    return json.loads((FIXTURES / name).read_bytes())


def _fetcher(tmp_path: Path, retries: int = 1) -> Fetcher:
    return Fetcher(Settings(data_dir=tmp_path, config_dir=tmp_path, retry_attempts=retries))


def _request() -> BoardRequest:
    return BoardRequest(provider="tiktok", slug="tiktok", url=BOARD_URL)


def _page(jobs: list[Any], count: int) -> dict[str, Any]:
    """A page in the recorded envelope, carrying `jobs` and stating `count`."""
    page = _fixture_json("normal.json")
    page["data"]["job_post_list"] = jobs
    page["data"]["count"] = count
    return page


def _clone_rows(n: int, start: int) -> list[dict[str, Any]]:
    """`n` rows cloned from the pinned fixture's first row with unique ids, so a shape change in
    `normal.json` reaches the paging tests instead of leaving them on a stale hand-written row."""
    template = _fixture_json("normal.json")["data"]["job_post_list"][0]
    return [{**template, "id": str(start + i)} for i in range(n)]


def _offset(request: httpx.Request) -> int:
    return int(json.loads(request.content)["offset"])


def _pages(*bodies: Any) -> Any:
    """A side effect serving `bodies` by the request's offset, in page order."""
    def serve(request: httpx.Request) -> httpx.Response:
        body = bodies[_offset(request) // PAGE_LIMIT]
        if isinstance(body, httpx.Response):
            return body
        return httpx.Response(200, json=body)
    return serve


# --- identity ----------------------------------------------------------------------------------


def test_the_slug_is_a_closed_catalog_of_tenant_sites() -> None:
    assert provider.normalize_slug("  TikTok ") == "tiktok"
    for bad in ("", "bytedance", "tiktokusds", "search"):
        with pytest.raises(ValueError, match="expected one of tiktok"):
            provider.normalize_slug(bad)


def test_the_board_url_carries_the_site_in_a_fragment_that_is_never_sent() -> None:
    assert provider.board_url("tiktok") == BOARD_URL
    assert httpx.URL(BOARD_URL).copy_with(fragment=None) == httpx.URL(SEARCH)


def test_any_careers_page_names_the_one_tenant_board() -> None:
    assert parse_board_target("https://lifeattiktok.com/search/7509598272319719687") == (
        "tiktok", "tiktok"
    )
    assert parse_board_target("https://lifeattiktok.com/search") == ("tiktok", "tiktok")


def test_the_employer_is_named_by_the_site() -> None:
    assert provider.employer_name_from_slug("tiktok") == "TikTok"


# --- the request ---------------------------------------------------------------------------


@respx.mock
def test_the_request_is_a_post_with_the_tenant_header_and_the_pinned_page(tmp_path: Path) -> None:
    route = respx.post(SEARCH).mock(return_value=httpx.Response(200, json=_fixture_json("normal.json")))

    provider.fetch_board(_fetcher(tmp_path), _request())

    sent = route.calls.last.request
    assert sent.headers["website-path"] == "tiktok"
    body = json.loads(sent.content)
    assert (body["limit"], body["offset"], body["keyword"]) == (PAGE_LIMIT, 0, "")
    assert body["location_code_list"] == [] and body["job_category_id_list"] == []


# --- a normal board ----------------------------------------------------------------------------


@respx.mock
def test_a_normal_board_is_complete_and_every_field_is_read(tmp_path: Path) -> None:
    respx.post(SEARCH).mock(return_value=httpx.Response(200, json=_fixture_json("normal.json")))

    snap = provider.fetch_board(_fetcher(tmp_path), _request())

    assert (snap.status, snap.error) == ("complete", None)
    assert (snap.board_reported_total, snap.board_enumerated, snap.detail_deferred) == (3, 3, 0)
    first, second, third = snap.postings
    assert first.provider_posting_id == "9000000000000000001"
    assert first.url == "https://lifeattiktok.com/search/9000000000000000001"
    assert first.title == "Software Engineer, Widgets"
    assert first.locations == ["Austin, Texas, United States of America"]
    assert second.locations == ["Singapore, Singapore"]  # a city with no state
    assert (first.department, third.department) == ("R&D", "Sales")
    assert first.body_text.startswith("About the Team\nAcme Corp's")
    assert "\n\nMinimum Qualifications" in first.body_text  # the requirement follows
    assert (first.posted_at, first.updated_at, first.remote_policy) == (None, None, "unknown")
    assert first.raw_json["code"] == "A90001"


@respx.mock
def test_an_empty_board_is_complete_and_empty_never_failed(tmp_path: Path) -> None:
    respx.post(SEARCH).mock(return_value=httpx.Response(200, json=_fixture_json("empty.json")))

    snap = provider.fetch_board(_fetcher(tmp_path), _request())

    assert (snap.status, snap.postings, snap.board_reported_total) == ("complete", [], 0)


# --- paging --------------------------------------------------------------------------------


@respx.mock
def test_a_full_page_is_followed_and_a_short_page_ends_the_walk(tmp_path: Path) -> None:
    route = respx.post(SEARCH).mock(
        side_effect=_pages(
            _page(_clone_rows(PAGE_LIMIT, 1), PAGE_LIMIT + 2),
            _page(_clone_rows(2, 1 + PAGE_LIMIT), PAGE_LIMIT + 2),
        )
    )

    snap = provider.fetch_board(_fetcher(tmp_path), _request())

    assert [_offset(c.request) for c in route.calls] == [0, PAGE_LIMIT]
    assert (snap.status, snap.board_enumerated, len(snap.postings)) == (
        "complete", PAGE_LIMIT + 2, PAGE_LIMIT + 2
    )


@respx.mock
def test_a_row_served_twice_across_pages_is_kept_once_and_the_shortfall_is_partial(
    tmp_path: Path,
) -> None:
    """No sort key was found, so a row can move across a page boundary mid-walk. The re-serve
    is deduped, and the one row that was missed makes the walk `partial`, not `complete`."""
    respx.post(SEARCH).mock(
        side_effect=_pages(
            _page(_clone_rows(PAGE_LIMIT, 1), PAGE_LIMIT + 2),
            _page(_clone_rows(2, PAGE_LIMIT), PAGE_LIMIT + 2),  # row N again
        )
    )

    snap = provider.fetch_board(_fetcher(tmp_path), _request())

    assert (snap.status, snap.board_enumerated, len(snap.postings)) == (
        "partial", PAGE_LIMIT + 1, PAGE_LIMIT + 1
    )
    assert f"collected {PAGE_LIMIT + 1} of {PAGE_LIMIT + 2}" in (snap.error or "")


@respx.mock
def test_a_count_that_moves_between_pages_is_partial_even_when_the_totals_match(
    tmp_path: Path,
) -> None:
    """Page 1 states N+2 and serves 1..N; a posting lands, page 2 states N+3 and serves N, N+3
    and N+2. N+2 distinct ids match the FIRST count, yet N+1 slipped past the boundary unread:
    `complete` would close it."""
    first = _page(_clone_rows(PAGE_LIMIT, 1), PAGE_LIMIT + 2)
    ids = (str(PAGE_LIMIT), str(PAGE_LIMIT + 3), str(PAGE_LIMIT + 2))
    moved = [{**r, "id": i} for r, i in zip(_clone_rows(3, 1), ids, strict=True)]
    respx.post(SEARCH).mock(side_effect=_pages(first, _page(moved, PAGE_LIMIT + 3)))

    snap = provider.fetch_board(_fetcher(tmp_path), _request())

    assert (snap.board_enumerated, snap.board_reported_total) == (PAGE_LIMIT + 2, PAGE_LIMIT + 2)
    assert snap.status == "partial"
    assert f"board count moved during the walk ({PAGE_LIMIT + 2}, {PAGE_LIMIT + 3})" in (
        snap.error or ""
    )


@respx.mock
def test_a_first_page_without_a_count_does_not_switch_the_shortfall_check_off(
    tmp_path: Path,
) -> None:
    first = _page(_clone_rows(PAGE_LIMIT, 1), 0)
    del first["data"]["count"]
    respx.post(SEARCH).mock(
        side_effect=_pages(first, _page(_clone_rows(1, PAGE_LIMIT + 1), PAGE_LIMIT + 2))
    )

    snap = provider.fetch_board(_fetcher(tmp_path), _request())

    assert snap.status == "partial"
    assert f"collected {PAGE_LIMIT + 1} of {PAGE_LIMIT + 2}" in (snap.error or "")


@respx.mock
def test_a_short_first_page_against_a_larger_count_is_partial(tmp_path: Path) -> None:
    respx.post(SEARCH).mock(return_value=httpx.Response(200, json=_page(_clone_rows(2, 1), 5)))

    snap = provider.fetch_board(_fetcher(tmp_path), _request())

    assert snap.status == "partial"
    assert "collected 2 of 5" in (snap.error or "")


# --- refusals --------------------------------------------------------------------------------


@respx.mock
def test_the_recorded_refusal_on_the_first_page_fails_the_board(tmp_path: Path) -> None:
    body = (FIXTURES / "refused.txt").read_text()
    respx.post(SEARCH).mock(return_value=httpx.Response(400, text=body))

    snap = provider.fetch_board(_fetcher(tmp_path), _request())

    assert (snap.status, snap.postings) == ("failed", [])


@respx.mock
def test_a_refusal_after_the_first_page_is_partial(tmp_path: Path) -> None:
    respx.post(SEARCH).mock(
        side_effect=_pages(
            _page(_clone_rows(PAGE_LIMIT, 1), 2 * PAGE_LIMIT),
            httpx.Response(400, text="invalid request"),
        )
    )

    snap = provider.fetch_board(_fetcher(tmp_path), _request())

    assert (snap.status, len(snap.postings)) == ("partial", PAGE_LIMIT)


@respx.mock
def test_a_nonzero_code_is_a_refusal_even_on_http_200(tmp_path: Path) -> None:
    refused = {**_fixture_json("empty.json"), "code": 1, "message": "busy"}
    respx.post(SEARCH).mock(return_value=httpx.Response(200, json=refused))

    snap = provider.fetch_board(_fetcher(tmp_path), _request())

    assert snap.status == "failed"
    assert "code 1: busy" in (snap.error or "")


@respx.mock
def test_an_unreadable_row_is_never_dropped_silently(tmp_path: Path) -> None:
    rows: list[Any] = [*_clone_rows(2, 1), "not a row", {**_clone_rows(1, 9)[0], "id": ""}]
    respx.post(SEARCH).mock(return_value=httpx.Response(200, json=_page(rows, 2)))

    snap = provider.fetch_board(_fetcher(tmp_path), _request())

    assert (snap.status, len(snap.postings)) == ("partial", 2)
    assert "dropped 1 entries that are not objects" in (snap.error or "")
    assert "skipped 1 rows with no id" in (snap.error or "")


def test_an_out_of_catalog_slug_fails_without_a_request(tmp_path: Path) -> None:
    with respx.mock(assert_all_called=False) as mock:
        route = mock.post(SEARCH)
        snap = provider.fetch_board(
            _fetcher(tmp_path), BoardRequest(provider="tiktok", slug="bytedance", url=BOARD_URL)
        )
    assert snap.status == "failed"
    assert not route.called


# --- healthcheck ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "response,expected",
    [
        (httpx.Response(200, json=_fixture_json("normal.json")), BoardHealth.OK),
        (httpx.Response(200, json=_fixture_json("empty.json")), BoardHealth.EMPTY),
        (httpx.Response(400, text="invalid request"), BoardHealth.ERROR),
        (httpx.Response(200, text="<html/>"), BoardHealth.ERROR),
    ],
)
@respx.mock
def test_healthcheck(tmp_path: Path, response: httpx.Response, expected: BoardHealth) -> None:
    route = respx.post(SEARCH).mock(return_value=response)

    assert provider.healthcheck(_fetcher(tmp_path), "tiktok") == expected
    assert json.loads(route.calls.last.request.content)["limit"] == 1
