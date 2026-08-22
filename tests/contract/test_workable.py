from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from boardwatch.core.board_urls import UnknownBoardURL, parse_board_target
from boardwatch.core.models import BoardRequest, ResponseValidators
from boardwatch.core.politeness import Fetcher
from boardwatch.core.settings import Settings
from boardwatch.providers.base import BoardHealth
from boardwatch.providers.workable import WorkableProvider

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "workable"
BOARD_URL = "https://apply.workable.com/api/v1/widget/accounts/acme?details=true"


def _fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _fixture_json(name: str) -> dict[str, Any]:
    return json.loads(_fixture_bytes(name))


def _fetcher(tmp_path: Path, retries: int = 1) -> Fetcher:
    return Fetcher(Settings(data_dir=tmp_path, config_dir=tmp_path, retry_attempts=retries))


def _request(validators: ResponseValidators | None = None) -> BoardRequest:
    return BoardRequest(provider="workable", slug="acme", url=BOARD_URL, validators=validators)


provider = WorkableProvider()


def test_board_url_is_canonical() -> None:
    assert provider.board_url("acme") == BOARD_URL


@respx.mock
def test_complete_snapshot_parses_all_jobs(tmp_path: Path) -> None:
    payload = _fixture_json("normal.json")
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, content=_fixture_bytes("normal.json")))
    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snap.status == "complete"
    assert len(snap.postings) == len(payload["jobs"])
    assert snap.url == BOARD_URL


@respx.mock
def test_workable_states_no_board_total(tmp_path: Path) -> None:
    """The {name, description, jobs} envelope carries no count field. None is a CLAIM: the
    board stated nothing.

    Backfilling len(postings) here would make coverage 100% by arithmetic, forever."""
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, content=_fixture_bytes("normal.json")))
    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snap.board_reported_total is None
    assert snap.board_enumerated == len(snap.postings)


@respx.mock
def test_per_job_parse_errors_produce_partial(tmp_path: Path) -> None:
    payload = _fixture_json("normal.json")
    del payload["jobs"][0]["title"]  # corrupt exactly one job
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, json=payload))
    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snap.status == "partial"
    assert len(snap.postings) == len(payload["jobs"]) - 1
    assert snap.error is not None and "1 of" in snap.error


@respx.mock
def test_telecommuting_maps_to_remote(tmp_path: Path) -> None:
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, content=_fixture_bytes("normal.json")))
    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    by_id = {p.provider_posting_id: p for p in snap.postings}
    for job in _fixture_json("normal.json")["jobs"]:
        expected = "remote" if job["telecommuting"] else "unknown"
        assert by_id[job["shortcode"]].remote_policy == expected


@respx.mock
def test_published_on_date_only_becomes_utc_midnight(tmp_path: Path) -> None:
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, content=_fixture_bytes("normal.json")))
    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    posted = snap.postings[0].posted_at
    assert posted is not None
    assert (posted.hour, posted.minute, posted.second, posted.tzinfo) == (0, 0, 0, None)


@respx.mock
def test_updated_at_is_always_none(tmp_path: Path) -> None:
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, content=_fixture_bytes("normal.json")))
    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    assert all(p.updated_at is None for p in snap.postings)


@respx.mock
def test_body_text_is_plain_not_html(tmp_path: Path) -> None:
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, content=_fixture_bytes("normal.json")))
    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    assert all("<p>" not in p.body_text for p in snap.postings)
    assert any(p.body_text.strip() for p in snap.postings)


@respx.mock
def test_empty_board_is_complete_with_no_postings(tmp_path: Path) -> None:
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, content=_fixture_bytes("empty.json")))
    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snap.status == "complete"
    assert snap.postings == []


@respx.mock
def test_transport_failure_is_failed_snapshot(tmp_path: Path) -> None:
    respx.get(BOARD_URL).mock(side_effect=httpx.ConnectError("boom"))
    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snap.status == "failed"
    assert snap.postings == []
    assert snap.error


@respx.mock
def test_invalid_payload_is_failed_snapshot(tmp_path: Path) -> None:
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, content=b"not json"))
    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snap.status == "failed"
    assert "invalid board payload" in (snap.error or "")


@respx.mock
def test_non_dict_payload_is_failed(tmp_path: Path) -> None:
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, content=b"[1, 2, 3]"))
    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snap.status == "failed"


@pytest.mark.parametrize(
    ("status", "expected"),
    [(404, BoardHealth.DEAD), (500, BoardHealth.ERROR)],
)
@respx.mock
def test_healthcheck_status_mapping(tmp_path: Path, status: int, expected: BoardHealth) -> None:
    respx.get(BOARD_URL).mock(return_value=httpx.Response(status))
    assert provider.healthcheck(_fetcher(tmp_path), "acme") == expected


@respx.mock
def test_healthcheck_ok_and_empty(tmp_path: Path) -> None:
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, content=_fixture_bytes("normal.json")))
    assert provider.healthcheck(_fetcher(tmp_path), "acme") == BoardHealth.OK
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, content=_fixture_bytes("empty.json")))
    assert provider.healthcheck(_fetcher(tmp_path), "acme") == BoardHealth.EMPTY


def test_slug_from_path_rejects_shortlink_and_accepts_org() -> None:
    assert WorkableProvider.slug_from_path("apply.workable.com", ["acme", "j", "X1"]) == "acme"
    assert WorkableProvider.slug_from_path("apply.workable.com", ["j", "X1"]) is None


def test_pasted_shortlink_is_rejected_end_to_end_with_canonical_guidance() -> None:
    """L1: real parse_board_target path, not just the staticmethod. Requires Workable
    registered (Step 5), so board_urls' module maps already include it."""
    with pytest.raises(UnknownBoardURL, match=r"apply\.workable\.com/\{org\}/j/"):
        parse_board_target("apply.workable.com/j/ABC123")
    assert parse_board_target("apply.workable.com/acme/j/ABC123") == ("workable", "acme")


@respx.mock
def test_board_enumerated_counts_listed_shortcodes_not_surviving_postings(
    tmp_path: Path,
) -> None:
    """`board_enumerated` means the same thing on every provider: DISTINCT POSTING IDS LISTED,
    before the detail budget and before parse failures drop anything (core/models.py). Workable
    keys on `shortcode`, never `id` (see this module's header), so that is the field counted."""
    payload = {"name": "Acme", "jobs": [
        {"shortcode": "AAA", "title": "Engineer A", "url": "https://apply.workable.com/acme/j/AAA",
         "description": "<p>body</p>"},
        {"shortcode": "BBB", "url": "https://apply.workable.com/acme/j/BBB",
         "description": "<p>body</p>"},
        {"title": "No shortcode", "url": "https://apply.workable.com/acme/j/CCC",
         "description": "<p>body</p>"},
    ]}
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, json=payload))
    snap = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snap.board_enumerated == 2  # AAA and BBB; the shortcode-less row cannot be keyed
    assert len(snap.postings) == 1  # BBB has no title
    assert snap.board_reported_total is None
