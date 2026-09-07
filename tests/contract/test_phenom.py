"""Phenom People contract tests. Fixture shapes and the widget bodies they mirror are recorded
in tests/fixtures/phenom/README.md (captured 2026-09-06)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from boardwatch.core.models import BoardRequest, ResponseValidators
from boardwatch.core.politeness import Fetcher
from boardwatch.core.settings import Settings
from boardwatch.providers.base import BoardHealth
from boardwatch.providers.phenom import PhenomProvider, split_slug

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "phenom"
HOST = "jobs.acme.test"
SLUG = f"{HOST}/global/en_global"
POST_URL = f"https://{HOST}/widgets"
BOARD_URL = f"https://{HOST}/widgets#refineSearch/global/en_global"

provider = PhenomProvider()


def _fx(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _fx_json(name: str) -> dict[str, Any]:
    return json.loads(_fx(name))


def _listed() -> list[dict[str, Any]]:
    rows = _fx_json("list_normal.json")["refineSearch"]["data"]["jobs"]
    assert isinstance(rows, list)
    return rows


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
        provider="phenom", slug=slug, url=BOARD_URL,
        known_posting_ids=known, detail_budget=budget, validators=validators,
    )


def _body(request: httpx.Request) -> dict[str, Any]:
    parsed = json.loads(request.content)
    assert isinstance(parsed, dict)
    return parsed


def _mock_widgets(
    pages: list[dict[str, Any]] | None = None,
    detail: dict[str, Any] | None = None,
    detail_status: int = 200,
) -> None:
    """One route for the ONE URL this provider posts to; the body's ddoKey and `from` decide
    which canned answer comes back. That mirrors the live endpoint, where a single URL serves
    both widgets, and is what makes "which detail was fetched" readable off respx.calls."""
    list_pages = pages if pages is not None else [_fx_json("list_normal.json")]
    detail_payload = detail if detail is not None else _fx_json("detail_normal.json")

    rows_by_id = {
        str(row["jobId"]): row
        for page in list_pages
        for row in page["refineSearch"]["data"]["jobs"]
        if row.get("jobId") is not None
    }

    def _answer(request: httpx.Request) -> httpx.Response:
        body = _body(request)
        if body["ddoKey"] == "jobDetail":
            # The live detail payload repeats the listed row's own structured fields, so a
            # single canned job would leak posting 1's location onto every other posting and
            # make the per-row assertions below vacuous.
            answer = detail_payload
            job = (answer.get("jobDetail") or {}).get("data", {}).get("job")
            row = rows_by_id.get(str(body["jobId"]))
            if isinstance(job, dict) and row is not None:
                answer = json.loads(json.dumps(answer))
                answer["jobDetail"]["data"]["job"] = {**job, **row, "description": job["description"]}
            return httpx.Response(detail_status, json=answer)
        index = int(body["from"]) // 500
        if index < len(list_pages):
            return httpx.Response(200, json=list_pages[index])
        empty = _fx_json("list_empty.json")
        empty["refineSearch"]["totalHits"] = list_pages[0]["refineSearch"]["totalHits"]
        return httpx.Response(200, json=empty)

    respx.post(POST_URL).mock(side_effect=_answer)


def _detail_calls() -> list[str]:
    return [
        str(_body(call.request)["jobId"])
        for call in respx.calls
        if _body(call.request)["ddoKey"] == "jobDetail"
    ]


def _list_offsets() -> list[int]:
    return [
        int(_body(call.request)["from"])
        for call in respx.calls
        if _body(call.request)["ddoKey"] == "refineSearch"
    ]


def test_board_url_is_a_stable_pseudo_key_per_board() -> None:
    """It is NEVER fetched: the fragment is not sent by any client and exists only to keep two
    boards on one host distinct in http_cache."""
    assert provider.board_url(SLUG) == BOARD_URL
    assert provider.board_url(f"{HOST}/us/en") == f"https://{HOST}/widgets#refineSearch/us/en"


def test_normalize_slug_lowercases_the_host_only() -> None:
    assert PhenomProvider.normalize_slug("JOBS.Acme.TEST/global/en_GLOBAL") == (
        f"{HOST}/global/en_GLOBAL"
    )


@pytest.mark.parametrize(
    "bad", ["jobs.acme.test", "jobs.acme.test/global", "jobs.acme.test/global/en/extra",
            "jobs.acme.test//en_global", "jobs.acme.test:8080/global/en_global"],
)
def test_a_malformed_slug_raises_rather_than_building_a_wrong_url(bad: str) -> None:
    with pytest.raises(ValueError):
        split_slug(bad)


@respx.mock
def test_complete_snapshot_fetches_a_detail_per_unseen_posting(tmp_path: Path) -> None:
    _mock_widgets()
    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snap.status == "complete", snap.error
    assert len(snap.postings) == 3
    assert snap.listed_ids == {row["jobId"] for row in _listed()}
    assert sorted(_detail_calls()) == ["100001BR", "100002BR", "100003BR"]
    assert snap.board_reported_total == 3
    assert snap.board_enumerated == 3
    assert snap.detail_deferred == 0


@respx.mock
def test_body_text_is_the_detail_description_converted_from_html(tmp_path: Path) -> None:
    _mock_widgets()
    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    body = snap.postings[0].body_text
    assert "<p>" not in body and "<ul>" not in body and "<li>" not in body
    assert body == "Job Description\nBuild synthetic platforms.\nPython\nSQL"


@respx.mock
def test_posting_url_falls_back_to_the_career_site_job_page(tmp_path: Path) -> None:
    """`applyUrl` is the underlying ATS's link on two of the three measured sites and empty on
    the third, so the constructed URL is the normal path. `lang_short` is load-bearing:
    `/global/en_global/job/{id}` redirects to the board root live, `/global/en/job/{id}` does
    not."""
    _mock_widgets()
    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    by_id = {p.provider_posting_id: p for p in snap.postings}
    assert by_id["100001BR"].url == f"https://{HOST}/global/en/job/100001BR"   # foreign host
    assert by_id["100002BR"].url == f"https://{HOST}/global/en/job/100002BR"   # empty applyUrl
    # own host -> used verbatim
    assert by_id["100003BR"].url == f"https://{HOST}/global/en/job/100003BR/apply"


@respx.mock
def test_remote_policy_comes_from_a_remote_location_and_nothing_else(tmp_path: Path) -> None:
    _mock_widgets()
    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    by_id = {p.provider_posting_id: p.remote_policy for p in snap.postings}
    assert by_id["100002BR"] == "remote"          # city == "Remote"
    assert by_id["100001BR"] == "unknown"         # never "onsite": the payload cannot say
    assert by_id["100003BR"] == "unknown"


@respx.mock
def test_locations_and_department_survive_empty_fields(tmp_path: Path) -> None:
    _mock_widgets()
    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    by_id = {p.provider_posting_id: p for p in snap.postings}
    assert by_id["100001BR"].locations == ["Springfield, Ohio, United States"]
    assert by_id["100003BR"].locations == ["Shelbyville, United States"]  # no cityStateCountry
    assert by_id["100003BR"].department is None                          # empty category
    assert by_id["100001BR"].department == "Engineering & Technology"


@respx.mock
def test_known_posting_ids_skip_detail_fetches_but_stay_listed(tmp_path: Path) -> None:
    """C1: a known posting must stay in the live inventory or apply_board closes it."""
    _mock_widgets()
    snap = provider.fetch_board(_fetcher(tmp_path), _request(known=frozenset({"100001BR"})))
    assert "100001BR" not in _detail_calls()
    assert snap.status == "complete", snap.error
    assert {p.provider_posting_id for p in snap.postings} == {"100002BR", "100003BR"}
    assert "100001BR" in snap.listed_ids


@respx.mock
def test_a_failed_detail_falls_back_to_the_teaser_and_says_so(tmp_path: Path) -> None:
    """The row must not be lost, and the compromise must not be silent: a teaser body is never
    re-detailed once the id is known."""
    _mock_widgets(detail_status=500)
    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snap.status == "partial"
    by_id = {p.provider_posting_id: p.body_text for p in snap.postings}
    assert by_id["100001BR"] == "Teaser for the platform role."
    assert by_id["100002BR"] == "Teaser for the analyst role."
    assert "descriptionTeaser" in (snap.error or "")
    assert "100001BR" in (snap.error or "")


@respx.mock
def test_a_refused_detail_widget_also_falls_back_to_the_teaser(tmp_path: Path) -> None:
    """A wrong/withdrawn ddoKey answers 200 with `{"status": "failure"}` and no envelope."""
    _mock_widgets(detail=_fx_json("widget_failure.json"))
    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snap.status == "partial"
    assert len(snap.postings) == 3
    assert all(p.body_text.startswith("Teaser for") for p in snap.postings)


@respx.mock
def test_pagination_pages_with_from_and_stops_on_a_short_page(tmp_path: Path) -> None:
    def _row(i: int) -> dict[str, Any]:
        return {
            "jobId": f"{200000 + i}BR", "title": f"Job {i}",
            "descriptionTeaser": f"Teaser {i}", "category": "Engineering",
            "city": "Springfield", "state": "Ohio", "country": "United States",
            "cityStateCountry": "Springfield, Ohio, United States",
            "postedDate": "2026-09-01T09:00:00.000+0000", "applyUrl": "",
        }

    def _page(rows: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "refineSearch": {
                "status": 200, "hits": len(rows), "totalHits": 503,
                "data": {"jobs": rows},
            }
        }

    pages = [_page([_row(i) for i in range(500)]), _page([_row(i) for i in range(500, 503)])]
    _mock_widgets(pages=pages)
    # Every id is already known, so the detail phase is empty and this test measures LISTING
    # alone -- 503 paced detail POSTs would make it a two-minute test of something else.
    known = frozenset(f"{200000 + i}BR" for i in range(503))
    snap = provider.fetch_board(_fetcher(tmp_path), _request(known=known))
    assert snap.status == "complete", snap.error
    assert _list_offsets() == [0, 500]          # stopped on the short page, no third request
    assert _detail_calls() == []
    assert snap.board_reported_total == 503
    assert snap.board_enumerated == 503
    assert len(snap.listed_ids) == 503


@respx.mock
def test_a_short_listing_is_partial_not_complete(tmp_path: Path) -> None:
    """Inventory safety: fewer ids than the board's own total must never read `complete`, or
    _process_missing closes live postings that were simply never listed."""
    payload = _fx_json("list_normal.json")
    payload["refineSearch"]["totalHits"] = 5
    _mock_widgets(pages=[payload])
    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snap.status == "partial"
    assert "incomplete listing" in (snap.error or "")
    assert snap.board_reported_total == 5
    assert snap.board_enumerated == 3


@respx.mock
def test_an_id_less_row_lowers_board_enumerated_so_the_shortfall_is_visible(
    tmp_path: Path,
) -> None:
    payload = _fx_json("list_normal.json")
    del payload["refineSearch"]["data"]["jobs"][2]["jobId"]
    _mock_widgets(pages=[payload])
    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snap.board_reported_total == 3
    assert snap.board_enumerated == 2
    assert "collected 2 of 3" in (snap.error or "")
    assert "100003BR" not in _detail_calls()   # an id-less row costs no doomed request


@respx.mock
def test_budget_exceeded_is_partial_and_counts_what_was_cut(tmp_path: Path) -> None:
    _mock_widgets()
    snap = provider.fetch_board(_fetcher(tmp_path), _request(budget=1))
    assert snap.status == "partial"
    assert len(snap.postings) == 1
    assert len(_detail_calls()) == 1
    assert "budget" in (snap.error or "").lower()
    # A post-truncation read of `unseen` would give 0 here (D-271).
    assert snap.detail_deferred == 2
    assert len(snap.listed_ids) == 3           # C1: the deferred two stay listed


@respx.mock
def test_validators_are_never_sent_and_no_conditional_request_is_made(tmp_path: Path) -> None:
    """The endpoint issues no ETag and answers no-store, so `unchanged` is unreachable."""
    _mock_widgets()
    snap = provider.fetch_board(
        _fetcher(tmp_path), _request(validators=ResponseValidators(etag='W/"abc123"'))
    )
    assert snap.status == "complete", snap.error
    assert snap.observed_validators is None
    assert all("If-None-Match" not in call.request.headers for call in respx.calls)


@respx.mock
def test_an_empty_board_is_complete_and_empty(tmp_path: Path) -> None:
    _mock_widgets(pages=[_fx_json("list_empty.json")])
    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snap.status == "complete", snap.error
    assert snap.postings == []
    assert snap.listed_ids == frozenset()
    assert snap.board_reported_total == 0


@respx.mock
def test_a_refused_list_widget_is_failed_not_empty(tmp_path: Path) -> None:
    """`{"status": "failure"}` carries no envelope. Reading it as an empty board would close
    every posting the company has."""
    respx.post(POST_URL).mock(
        return_value=httpx.Response(200, content=_fx("widget_failure.json"))
    )
    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snap.status == "failed"
    assert snap.postings == []


@respx.mock
def test_a_non_json_list_answer_is_failed(tmp_path: Path) -> None:
    respx.post(POST_URL).mock(return_value=httpx.Response(200, content=b"<html>nope</html>"))
    assert provider.fetch_board(_fetcher(tmp_path), _request()).status == "failed"


@respx.mock
def test_a_missing_totalhits_is_failed(tmp_path: Path) -> None:
    payload = _fx_json("list_normal.json")
    del payload["refineSearch"]["totalHits"]
    _mock_widgets(pages=[payload])
    assert provider.fetch_board(_fetcher(tmp_path), _request()).status == "failed"


@respx.mock
def test_an_unreachable_host_is_failed_without_raising(tmp_path: Path) -> None:
    respx.post(POST_URL).mock(side_effect=httpx.ConnectError("boom"))
    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snap.status == "failed"
    assert snap.error


def test_a_malformed_stored_slug_is_failed_not_a_traceback(tmp_path: Path) -> None:
    snap = provider.fetch_board(_fetcher(tmp_path), _request(slug="jobs.acme.test"))
    assert snap.status == "failed"
    assert "invalid phenom slug" in (snap.error or "")


@respx.mock
def test_healthcheck_ok(tmp_path: Path) -> None:
    _mock_widgets()
    assert provider.healthcheck(_fetcher(tmp_path), SLUG) == BoardHealth.OK


@respx.mock
def test_healthcheck_empty_board_is_empty(tmp_path: Path) -> None:
    _mock_widgets(pages=[_fx_json("list_empty.json")])
    assert provider.healthcheck(_fetcher(tmp_path), SLUG) == BoardHealth.EMPTY


@respx.mock
def test_healthcheck_404_is_error_not_dead(tmp_path: Path) -> None:
    """The host is the EMPLOYER's own domain and serves a whole website, so a 404 from it is a
    retired site or a WAF blip — not proof the board is gone."""
    respx.post(POST_URL).mock(return_value=httpx.Response(404))
    assert provider.healthcheck(_fetcher(tmp_path), SLUG) == BoardHealth.ERROR


@respx.mock
def test_healthcheck_unreachable_host_is_unreachable(tmp_path: Path) -> None:
    respx.post(POST_URL).mock(side_effect=httpx.ConnectError("boom"))
    assert provider.healthcheck(_fetcher(tmp_path), SLUG) == BoardHealth.UNREACHABLE


@respx.mock
def test_healthcheck_refused_widget_is_error(tmp_path: Path) -> None:
    respx.post(POST_URL).mock(
        return_value=httpx.Response(200, content=_fx("widget_failure.json"))
    )
    assert provider.healthcheck(_fetcher(tmp_path), SLUG) == BoardHealth.ERROR


def test_healthcheck_malformed_slug_is_error(tmp_path: Path) -> None:
    assert provider.healthcheck(_fetcher(tmp_path), "jobs.acme.test") == BoardHealth.ERROR
