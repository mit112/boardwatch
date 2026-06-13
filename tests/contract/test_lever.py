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
from boardwatch.providers.lever import LeverProvider

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "lever"
BOARD_URL = "https://api.lever.co/v0/postings/acme?mode=json"


def _fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _fixture_json(name: str) -> Any:
    return json.loads(_fixture_bytes(name))


def _fetcher(tmp_path: Path, retries: int = 1) -> Fetcher:
    return Fetcher(Settings(data_dir=tmp_path, config_dir=tmp_path, retry_attempts=retries))


def _request(validators: ResponseValidators | None = None) -> BoardRequest:
    return BoardRequest(provider="lever", slug="acme", url=BOARD_URL, validators=validators)


provider = LeverProvider()


def test_board_url_is_canonical_with_mode_json() -> None:
    assert provider.board_url("acme") == BOARD_URL  # the http_cache key (D22)


@respx.mock
def test_complete_snapshot_parses_array_of_postings(tmp_path: Path) -> None:
    headers = _fixture_json("normal_response_headers.json")
    respx.get(BOARD_URL).mock(
        return_value=httpx.Response(
            200,
            content=_fixture_bytes("normal.json"),
            headers={"ETag": headers["etag"], "Last-Modified": headers["last_modified"]},
        )
    )
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    raw = _fixture_json("normal.json")
    assert snapshot.status == "complete"
    assert snapshot.url == BOARD_URL
    assert len(snapshot.postings) == len(raw)
    for posting in snapshot.postings:
        assert posting.provider_posting_id
        assert posting.title
        assert posting.url
        assert posting.body_text  # joined from descriptionPlain + additionalPlain (no HTML path)
    assert snapshot.observed_validators is not None
    assert snapshot.observed_validators.etag == headers["etag"]


@respx.mock
def test_created_at_is_epoch_milliseconds_not_seconds(tmp_path: Path) -> None:
    # the ms-vs-s guard (issue #16): a 13-digit epoch-ms createdAt must land in this
    # decade, not 1970. If the provider divided by the wrong factor this fails loudly.
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, content=_fixture_bytes("normal.json")))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    dated = [p for p in snapshot.postings if p.posted_at is not None]
    assert dated, "fixture contract: >= 1 posting with createdAt"
    for posting in dated:
        assert posting.posted_at.year >= 2020


@respx.mock
def test_lever_never_mines_salary(tmp_path: Path) -> None:
    # D19: salary text appears in additionalPlain on some boards and is NEVER mined.
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, content=_fixture_bytes("normal.json")))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    with_salary_text = [
        p for p in snapshot.postings if "$" in (p.raw_json.get("additionalPlain") or "")
    ]
    assert with_salary_text, "fixture contract: >= 1 posting with salary text in additionalPlain"
    for posting in snapshot.postings:
        assert posting.salary_min is None
        assert posting.salary_max is None
        assert posting.salary_currency is None
        assert posting.salary_period is None


@respx.mock
def test_multi_location_posting_keeps_all_locations(tmp_path: Path) -> None:
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, content=_fixture_bytes("normal.json")))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert any(len(p.locations) >= 2 for p in snapshot.postings), "fixture: >= 1 multi-location"


@respx.mock
def test_empty_array_is_complete_empty_inventory(tmp_path: Path) -> None:
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, content=_fixture_bytes("empty.json")))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "complete"  # 200 [] IS an inventory (unlike a 304, D15)
    assert snapshot.postings == []


@respx.mock
def test_per_posting_parse_error_produces_partial(tmp_path: Path) -> None:
    payload = _fixture_json("normal.json")
    del payload[0]["text"]  # corrupt exactly one posting's title
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, json=payload))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "partial"
    assert len(snapshot.postings) == len(payload) - 1
    assert snapshot.error is not None and "1 of" in snapshot.error


@respx.mock
def test_dead_404_body_maps_to_failed_not_empty(tmp_path: Path) -> None:
    # the 404 {"ok":false,"error":"Document not found"} dead body -> failed, never an
    # empty inventory (issue #16: the dead-vs-empty distinction #20 depends on)
    respx.get(BOARD_URL).mock(
        return_value=httpx.Response(404, content=_fixture_bytes("dead_404.json"))
    )
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "failed"
    assert snapshot.postings == []
    assert snapshot.error


@respx.mock
def test_invalid_json_maps_to_failed(tmp_path: Path) -> None:
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, content=b"<html>nope</html>"))
    assert provider.fetch_board(_fetcher(tmp_path), _request()).status == "failed"


@respx.mock
def test_304_maps_to_unchanged(tmp_path: Path) -> None:
    headers = _fixture_json("normal_response_headers.json")
    route = respx.get(BOARD_URL).mock(return_value=httpx.Response(304))
    snapshot = provider.fetch_board(
        _fetcher(tmp_path),
        _request(ResponseValidators(etag=headers["etag"], last_modified=headers["last_modified"])),
    )
    assert route.calls[0].request.headers["If-None-Match"] == headers["etag"]
    assert snapshot.status == "unchanged"
    assert snapshot.postings == []  # a 304 is NOT an inventory (D15)
    assert snapshot.url == BOARD_URL


@respx.mock
@pytest.mark.parametrize(
    ("fixture", "status_code", "expected"),
    [
        ("normal.json", 200, BoardHealth.OK),
        ("empty.json", 200, BoardHealth.EMPTY),
        ("dead_404.json", 404, BoardHealth.DEAD),
        (None, 500, BoardHealth.ERROR),
    ],
)
def test_healthcheck_mapping(
    tmp_path: Path, fixture: str | None, status_code: int, expected: BoardHealth
) -> None:
    content = _fixture_bytes(fixture) if fixture else b""
    respx.get(BOARD_URL).mock(return_value=httpx.Response(status_code, content=content))
    assert provider.healthcheck(_fetcher(tmp_path), "acme") == expected


@respx.mock
def test_healthcheck_transport_failure_is_unreachable(tmp_path: Path) -> None:
    respx.get(BOARD_URL).mock(side_effect=httpx.ConnectError("boom"))
    assert provider.healthcheck(_fetcher(tmp_path), "acme") == BoardHealth.UNREACHABLE
