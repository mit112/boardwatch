from __future__ import annotations

import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from boardwatch.core.models import BoardRequest, ResponseValidators
from boardwatch.core.politeness import Fetcher
from boardwatch.core.settings import Settings
from boardwatch.providers.base import BoardHealth
from boardwatch.providers.smartrecruiters import SmartRecruitersProvider, _body_text

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


def test_body_text_converts_html_sections_and_preserves_list_item_order() -> None:
    detail = {
        "jobAd": {
            "sections": {
                "jobDescription": {"text": "<p>Lead the platform.</p>"},
                "qualifications": {
                    "text": (
                        "<p>Required skills:</p>"
                        "<ul><li>Python</li><li>SQL</li></ul>"
                    )
                },
                "additionalInformation": {"text": "<div></div>"},
            }
        }
    }

    body = _body_text(detail)

    # Tag syntax, not bare angle brackets: a correctly converted `5 &gt; 3` yields "5 > 3",
    # which a bare `">" not in body` would reject.
    assert "<p>" not in body and "<ul>" not in body and "<li>" not in body
    assert body == "Lead the platform.\n\nRequired skills:\nPython\nSQL"


def test_body_text_keeps_one_blank_line_between_converted_sections() -> None:
    detail = {
        "jobAd": {
            "sections": {
                "jobDescription": {"text": "<p>First section.</p>"},
                "qualifications": {"text": "<div>Second section.</div>"},
                "additionalInformation": {"text": "<br>Third section."},
            }
        }
    }

    assert _body_text(detail) == (
        "First section.\n\nSecond section.\n\nThird section."
    )


def test_body_text_skips_markup_only_sections_after_conversion() -> None:
    detail = {
        "jobAd": {
            "sections": {
                "jobDescription": {"text": "<p>First section.</p>"},
                "qualifications": {"text": "<p></p>"},
                "additionalInformation": {"text": "<p>Last section.</p>"},
            }
        }
    }

    assert _body_text(detail) == "First section.\n\nLast section."


@pytest.mark.usefixtures("no_real_sleep")
@respx.mock
def test_complete_snapshot_fetches_a_detail_per_posting(tmp_path: Path) -> None:
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, content=_fx("list_normal.json")))
    _mock_all_details()
    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snap.status == "complete"
    assert len(snap.postings) == _fx_json("list_normal.json")["totalFound"]
    assert snap.listed_ids == {str(e["id"]) for e in _fx_json("list_normal.json")["content"]}


@pytest.mark.usefixtures("no_real_sleep")
@respx.mock
def test_smartrecruiters_reports_totalfound_as_board_total(tmp_path: Path) -> None:
    """totalFound is the board's own count; the contract pins totalFound == len(content)."""
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, content=_fx("list_normal.json")))
    _mock_all_details()
    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snap.board_reported_total == 3
    assert snap.board_enumerated == 3
    assert snap.detail_deferred == 0


@pytest.mark.usefixtures("no_real_sleep")
@respx.mock
def test_company_description_is_excluded_from_body(tmp_path: Path) -> None:
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, content=_fx("list_normal.json")))
    _mock_all_details()
    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    assert all("must be EXCLUDED" not in p.body_text for p in snap.postings)
    assert all("Build synthetic platforms." in p.body_text for p in snap.postings)


@pytest.mark.usefixtures("no_real_sleep")
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


@pytest.mark.usefixtures("no_real_sleep")
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


@pytest.mark.usefixtures("no_real_sleep")
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


@pytest.mark.usefixtures("no_real_sleep")
@respx.mock
def test_inactive_postings_are_skipped_and_not_listed(tmp_path: Path) -> None:
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, content=_fx("list_normal.json")))
    _mock_all_details("detail_inactive.json")
    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snap.postings == []
    assert snap.listed_ids == frozenset()   # inactive -> removed from live inventory


@pytest.mark.usefixtures("no_real_sleep")
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
    # 3 unseen postings truncated to budget=1: a post-truncation read of `unseen` would give
    # 0 here, the exact regression detail_deferred exists to catch (D-271).
    assert snap.detail_deferred == 2


@respx.mock
def test_the_detail_phase_stops_before_the_board_clock_could_end_a_request(
    tmp_path: Path,
) -> None:
    """T243. aecom2 fetched 541 and 476 details on runs 474/475 and then, on 476, was failed at its
    cap with nothing persisted. Past the point where the board's clock could end a request, the
    rest are deferred — `partial`, with what was fetched — and the clock is never tripped."""
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, content=_fx("list_normal.json")))
    _mock_all_details()
    fetcher = _fetcher(tmp_path)
    listed = _fx_json("list_normal.json")["content"][0]
    first = str(listed["id"])
    body = {**_fx_json("detail_normal.json"), **{k: listed[k] for k in ("id", "name", "location")}}
    with fetcher.under_deadline(time.monotonic() + 1000.0, 1000.0) as clock:

        def _then_one_second_left(request: httpx.Request) -> httpx.Response:
            clock.at = time.monotonic() + 0.1  # under one 0.25 s pacing delay left
            return httpx.Response(200, json=body)

        respx.get(_detail_url(first)).mock(side_effect=_then_one_second_left)
        snap = provider.fetch_board(fetcher, _request())

    assert _detail_calls() == {first}
    assert [p.provider_posting_id for p in snap.postings] == [first]
    assert snap.status == "partial"
    assert snap.detail_deferred == 2
    assert "2 unseen postings deferred" in (snap.error or "")
    assert not clock.tripped


@pytest.mark.usefixtures("no_real_sleep")
@respx.mock
def test_the_detail_phase_never_defers_before_it_has_kept_a_posting(tmp_path: Path) -> None:
    """T243 round 3 (Codex). An INACTIVE first detail keeps nothing, and a stop right after it
    left a `partial` with 0 kept and the rest deferred — every scan, because the inactive id is not
    remembered. Until a posting is kept the stop does not apply: the scan either keeps one or the
    cap cuts it and the board is failed, as before T243."""
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, content=_fx("list_normal.json")))
    _mock_all_details()
    fetcher = _fetcher(tmp_path)
    listed = _fx_json("list_normal.json")["content"]
    first, second = str(listed[0]["id"]), str(listed[1]["id"])
    with fetcher.under_deadline(time.monotonic() + 1000.0, 1000.0) as clock:

        def _inactive_then_little_left(request: httpx.Request) -> httpx.Response:
            clock.at = time.monotonic() + 0.1  # under one 0.25 s pacing delay left
            return httpx.Response(200, json={"id": first, "active": False})

        respx.get(_detail_url(first)).mock(side_effect=_inactive_then_little_left)
        snap = provider.fetch_board(fetcher, _request())

    assert _detail_calls() == {first, second}
    assert [p.provider_posting_id for p in snap.postings] == [second]
    assert snap.status == "partial"
    assert snap.detail_deferred == 1


@pytest.mark.usefixtures("no_real_sleep")
@respx.mock
def test_one_detail_failure_is_partial(tmp_path: Path) -> None:
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, content=_fx("list_normal.json")))
    _mock_all_details()
    first = str(_fx_json("list_normal.json")["content"][0]["id"])
    respx.get(_detail_url(first)).mock(return_value=httpx.Response(500))
    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snap.status == "partial"
    assert first not in {p.provider_posting_id for p in snap.postings}


@pytest.mark.usefixtures("no_real_sleep")
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


@pytest.mark.usefixtures("no_real_sleep")
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


@pytest.mark.usefixtures("no_real_sleep")
@respx.mock
def test_an_id_less_row_lowers_board_enumerated_so_the_shortfall_is_visible(
    tmp_path: Path,
) -> None:
    """THE Mastercard case, run 67: the board reported 1129 and only 1128 could be keyed.
    SmartRecruiters already DETECTS that (the "incomplete listing" note, built from
    `listed_ids`) and then persisted `len(listed)` — every raw row, id-less ones included — so
    `board_reported_total - board_enumerated` was 0 and the defect was invisible in the very
    column added to expose it. `board_enumerated` is now DISTINCT LISTED IDS, the same meaning
    every other provider carries (core/models.py).

    Scaled to the fixture: 3 stated, 3 rows, one with no `id`."""
    payload = _fx_json("list_normal.json")
    del payload["content"][2]["id"]
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, json=payload))
    _mock_all_details()
    # Pre-existing, unchanged by this test: the detail loop keys on `str(entry.get("id"))`, so
    # an id-less row still costs one doomed request. Mocked, not asserted on.
    respx.get(_detail_url("None")).mock(return_value=httpx.Response(404))
    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snap.board_reported_total == 3
    assert snap.board_enumerated == 2
    assert snap.board_reported_total - snap.board_enumerated == 1  # the id-less row, visible
    assert "collected 2 of 3" in (snap.error or "")


@pytest.mark.usefixtures("no_real_sleep")
@respx.mock
def test_a_cross_page_duplicate_is_counted_once_in_board_enumerated(tmp_path: Path) -> None:
    """The other half of `len(listed)`: it also counted a posting twice when two pages carried
    it, which could push `board_enumerated` ABOVE the board's own stated total and turn the
    shortfall negative for a reason that has nothing to do with coverage."""
    first = _fx_json("list_normal.json")
    first["totalFound"] = 4
    second = {"totalFound": 4, "content": [dict(first["content"][0])]}  # the same posting again
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, json=first))
    respx.get(_page_url(100)).mock(return_value=httpx.Response(200, json=second))
    _mock_all_details()
    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snap.board_reported_total == 4
    assert snap.board_enumerated == 3  # 4 rows collected, 3 distinct ids


def test_a_list_page_that_trickles_past_the_fetch_deadline_is_a_failed_board(
    tmp_path: Path,
) -> None:
    """T192, run 473: `api.smartrecruiters.com` trickled a response for 55 minutes. The fetch
    deadline must reach the provider as a `failed` board naming the deadline — never
    `unchanged`, never an exception out of the scan."""

    def trickle() -> Iterator[bytes]:
        for _ in range(40):
            time.sleep(0.1)
            yield b" "

    fetcher = Fetcher(
        Settings(
            data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1,
            per_host_delay_seconds=0.25, fetch_deadline_seconds=0.5,
        )
    )
    with respx.mock:
        respx.get(LIST_URL).mock(return_value=httpx.Response(200, content=trickle()))
        snap = SmartRecruitersProvider().fetch_board(fetcher, _request())
    assert snap.status == "failed"
    assert snap.error is not None and "fetch deadline 0.5s exceeded" in snap.error
