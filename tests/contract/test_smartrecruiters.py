from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import respx

from boardwatch.core.models import BoardRequest, ResponseValidators
from boardwatch.core.politeness import Fetcher
from boardwatch.core.settings import Settings
from boardwatch.providers.base import BoardHealth
from boardwatch.providers.smartrecruiters import SmartRecruitersProvider

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "smartrecruiters"
LIST_URL = "https://api.smartrecruiters.com/v1/companies/acme/postings?limit=100&offset=0"


def _fx(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _fx_json(name: str) -> dict[str, Any]:
    return json.loads(_fx(name))


def _detail_url(pid: str) -> str:
    return f"https://api.smartrecruiters.com/v1/companies/acme/postings/{pid}"


def _page_url(offset: int) -> str:
    return f"https://api.smartrecruiters.com/v1/companies/acme/postings?limit=100&offset={offset}"


def _fetcher(tmp_path: Path) -> Fetcher:
    return Fetcher(
        Settings(
            data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1,
            per_host_delay_seconds=0.25,
        )
    )


def _request(
    known: frozenset[str] = frozenset(), budget: int = 50,
    validators: ResponseValidators | None = None,
) -> BoardRequest:
    return BoardRequest(
        provider="smartrecruiters", slug="acme", url=LIST_URL,
        known_posting_ids=known, detail_budget=budget, validators=validators,
    )


provider = SmartRecruitersProvider()


def _mock_all_details(detail_fixture: str = "detail_normal.json") -> None:
    base = _fx_json(detail_fixture)
    for listed in _fx_json("list_normal.json")["content"]:
        body = dict(base)
        body["id"] = listed["id"]
        body["name"] = listed["name"]
        body["location"] = listed["location"]
        respx.get(_detail_url(listed["id"])).mock(return_value=httpx.Response(200, json=body))


def _detail_calls() -> set[str]:
    return {
        str(c.request.url).rsplit("/", 1)[-1]
        for c in respx.calls
        if "/postings/" in str(c.request.url)
    }


def test_board_url_is_canonical() -> None:
    assert provider.board_url("acme") == LIST_URL


def test_normalize_slug_lowercases() -> None:
    assert SmartRecruitersProvider.normalize_slug("Visa") == "visa"
    assert SmartRecruitersProvider.normalize_slug("VISA") == "visa"


@respx.mock
def test_complete_snapshot_fetches_a_detail_per_posting(tmp_path: Path) -> None:
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, content=_fx("list_normal.json")))
    _mock_all_details()
    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snap.status == "complete"
    assert len(snap.postings) == _fx_json("list_normal.json")["totalFound"]
    assert snap.listed_ids == {str(e["id"]) for e in _fx_json("list_normal.json")["content"]}


@respx.mock
def test_company_description_is_excluded_from_body(tmp_path: Path) -> None:
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, content=_fx("list_normal.json")))
    _mock_all_details()
    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    assert all("must be EXCLUDED" not in p.body_text for p in snap.postings)
    assert all("Build synthetic platforms." in p.body_text for p in snap.postings)


@respx.mock
def test_known_posting_ids_skip_detail_fetches_but_stay_listed(tmp_path: Path) -> None:
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, content=_fx("list_normal.json")))
    _mock_all_details()
    listed = _fx_json("list_normal.json")["content"]
    known = frozenset({str(listed[0]["id"])})
    snap = provider.fetch_board(_fetcher(tmp_path), _request(known=known))
    assert str(listed[0]["id"]) not in _detail_calls()          # detail skipped
    assert snap.status == "complete"
    assert len(snap.postings) == len(listed) - 1                 # only unseen parsed
    assert str(listed[0]["id"]) in snap.listed_ids               # C1: still in live inventory


@respx.mock
def test_not_modified_is_unchanged_with_zero_detail_fetches(tmp_path: Path) -> None:
    respx.get(LIST_URL).mock(return_value=httpx.Response(304))
    req = _request(validators=ResponseValidators(etag='W/"abc123"'))
    snap = provider.fetch_board(_fetcher(tmp_path), req)
    assert snap.status == "unchanged"
    assert snap.postings == []
    assert len(respx.calls) == 1                                  # ONLY the list URL
    assert str(respx.calls[0].request.url) == LIST_URL
    assert respx.calls[0].request.headers.get("If-None-Match") == 'W/"abc123"'


@respx.mock
def test_pagination_follows_offsets(tmp_path: Path) -> None:
    def _entry(i: int) -> dict[str, Any]:
        return {
            "id": str(900000 + i), "name": f"Job {i}",
            "location": {"city": "Austin", "region": "TX", "country": "us",
                         "remote": False, "hybrid": False},
            "company": {"identifier": "acme"},
        }
    page0 = {"offset": 0, "limit": 100, "totalFound": 103,
             "content": [_entry(i) for i in range(100)]}
    page1 = {"offset": 100, "limit": 100, "totalFound": 103,
             "content": [_entry(i) for i in range(100, 103)]}
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, json=page0))
    respx.get(_page_url(100)).mock(return_value=httpx.Response(200, json=page1))
    detail = _fx_json("detail_normal.json")
    for i in range(103):
        body = dict(detail)
        body["id"] = str(900000 + i)
        body["name"] = f"Job {i}"
        body["location"] = {"remote": False, "hybrid": False}
        respx.get(_detail_url(str(900000 + i))).mock(return_value=httpx.Response(200, json=body))
    snap = provider.fetch_board(_fetcher(tmp_path), _request(budget=200))
    assert snap.status == "complete"
    assert len(snap.postings) == 103
    assert any(str(c.request.url) == _page_url(100) for c in respx.calls)  # page 2 fetched


@respx.mock
def test_incomplete_listing_is_partial_not_complete(tmp_path: Path) -> None:
    """Inventory-safety: if totalFound overcounts (or a page is short/filtered), the
    collected id count can fall short of totalFound. That must downgrade to `partial` —
    never `complete` — so _process_missing (complete-only) never closes a live posting
    that was simply never returned by the list."""
    def _entry(i: int) -> dict[str, Any]:
        return {
            "id": str(800000 + i), "name": f"Job {i}",
            "location": {"city": "Austin", "region": "TX", "country": "us",
                         "remote": False, "hybrid": False},
            "company": {"identifier": "acme"},
        }
    page0 = {"offset": 0, "limit": 100, "totalFound": 5,
             "content": [_entry(i) for i in range(3)]}
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, json=page0))
    detail = _fx_json("detail_normal.json")
    for i in range(3):
        body = dict(detail)
        body["id"] = str(800000 + i)
        body["name"] = f"Job {i}"
        body["location"] = {"remote": False, "hybrid": False}
        respx.get(_detail_url(str(800000 + i))).mock(return_value=httpx.Response(200, json=body))
    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snap.status == "partial"
    assert "incomplete listing" in (snap.error or "")
    assert len(snap.listed_ids) == 3


@respx.mock
def test_inactive_postings_are_skipped_and_not_listed(tmp_path: Path) -> None:
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, content=_fx("list_normal.json")))
    _mock_all_details("detail_inactive.json")
    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snap.postings == []
    assert snap.listed_ids == frozenset()   # inactive -> removed from live inventory


@respx.mock
def test_empty_sections_yield_empty_body_not_an_error(tmp_path: Path) -> None:
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, content=_fx("list_normal.json")))
    _mock_all_details("detail_empty_sections.json")
    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snap.status == "complete"
    assert all(p.body_text == "" for p in snap.postings)


@respx.mock
def test_budget_exceeded_is_partial(tmp_path: Path) -> None:
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, content=_fx("list_normal.json")))
    _mock_all_details()
    snap = provider.fetch_board(_fetcher(tmp_path), _request(budget=1))
    assert snap.status == "partial"
    assert len(snap.postings) == 1
    assert "budget" in (snap.error or "").lower()


@respx.mock
def test_one_detail_failure_is_partial(tmp_path: Path) -> None:
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, content=_fx("list_normal.json")))
    _mock_all_details()
    first = str(_fx_json("list_normal.json")["content"][0]["id"])
    respx.get(_detail_url(first)).mock(return_value=httpx.Response(500))
    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snap.status == "partial"
    assert first not in {p.provider_posting_id for p in snap.postings}


@respx.mock
def test_malformed_detail_is_partial_and_skipped(tmp_path: Path) -> None:
    """H2: a detail that isn't a JSON object must not raise; skip it, mark partial."""
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, content=_fx("list_normal.json")))
    _mock_all_details()
    first = str(_fx_json("list_normal.json")["content"][0]["id"])
    respx.get(_detail_url(first)).mock(return_value=httpx.Response(200, content=b"[1,2,3]"))
    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snap.status == "partial"
    assert first not in {p.provider_posting_id for p in snap.postings}


@respx.mock
def test_all_detail_failures_is_failed(tmp_path: Path) -> None:
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, content=_fx("list_normal.json")))
    for listed in _fx_json("list_normal.json")["content"]:
        respx.get(_detail_url(listed["id"])).mock(return_value=httpx.Response(500))
    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snap.status == "failed"
    assert snap.postings == []


@respx.mock
def test_list_failure_is_failed(tmp_path: Path) -> None:
    respx.get(LIST_URL).mock(side_effect=httpx.ConnectError("boom"))
    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snap.status == "failed"
    assert snap.error


@respx.mock
def test_non_dict_list_payload_is_failed(tmp_path: Path) -> None:
    """H2: content not a list -> failed, no raise."""
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, json={"content": 5, "totalFound": 0}))
    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snap.status == "failed"


@respx.mock
def test_healthcheck_empty_board_is_empty_not_dead(tmp_path: Path) -> None:
    """An unknown org returns 200/totalFound:0 — DEAD is unreachable for this provider."""
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, content=_fx("list_empty.json")))
    assert provider.healthcheck(_fetcher(tmp_path), "acme") == BoardHealth.EMPTY


@respx.mock
def test_healthcheck_ok(tmp_path: Path) -> None:
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, content=_fx("list_normal.json")))
    assert provider.healthcheck(_fetcher(tmp_path), "acme") == BoardHealth.OK


@respx.mock
def test_healthcheck_404_is_error_not_dead(tmp_path: Path) -> None:
    """DEAD is unreachable for this provider (an unknown org 200s with totalFound:0), so a
    genuine 404 must never be misclassified as DEAD."""
    respx.get(LIST_URL).mock(return_value=httpx.Response(404))
    result = provider.healthcheck(_fetcher(tmp_path), "acme")
    assert result != BoardHealth.DEAD
    assert result == BoardHealth.ERROR
