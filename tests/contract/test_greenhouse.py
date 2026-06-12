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
from boardwatch.providers.greenhouse import GreenhouseProvider

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "greenhouse"
BOARD_URL = (
    "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true&pay_transparency=true"
)
HEALTH_URL = "https://boards-api.greenhouse.io/v1/boards/acme/jobs"


def _fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _fixture_json(name: str) -> dict[str, Any]:
    return json.loads(_fixture_bytes(name))


def _fetcher(tmp_path: Path, retries: int = 1) -> Fetcher:
    return Fetcher(
        Settings(data_dir=tmp_path, config_dir=tmp_path, retry_attempts=retries)
    )


def _request(validators: ResponseValidators | None = None) -> BoardRequest:
    return BoardRequest(provider="greenhouse", slug="acme", url=BOARD_URL, validators=validators)


provider = GreenhouseProvider()


def test_board_url_is_canonical_with_stable_param_order() -> None:
    assert provider.board_url("acme") == BOARD_URL  # this string IS the http_cache key (D22)


@respx.mock
def test_complete_snapshot_parses_all_jobs(tmp_path: Path) -> None:
    headers = _fixture_json("normal_response_headers.json")
    respx.get(BOARD_URL).mock(
        return_value=httpx.Response(
            200,
            content=_fixture_bytes("normal.json"),
            headers={"ETag": headers["etag"], "Last-Modified": headers["last_modified"]},
        )
    )
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    jobs = _fixture_json("normal.json")["jobs"]
    assert snapshot.status == "complete"
    assert snapshot.url == BOARD_URL
    assert len(snapshot.postings) == len(jobs)
    for posting in snapshot.postings:
        assert posting.provider_posting_id
        assert posting.title
        assert posting.url
        assert posting.body_text
    assert snapshot.observed_validators is not None
    assert snapshot.observed_validators.etag == headers["etag"]


@respx.mock
def test_pay_input_ranges_captured_in_raw_json_never_projected(tmp_path: Path) -> None:
    respx.get(BOARD_URL).mock(
        return_value=httpx.Response(200, content=_fixture_bytes("normal.json"))
    )
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    with_ranges = [p for p in snapshot.postings if p.raw_json.get("pay_input_ranges")]
    assert with_ranges, "fixture contract: >= 1 posting with pay_input_ranges"
    assert any(
        len(p.raw_json["pay_input_ranges"]) >= 2 for p in with_ranges
    ), "fixture contract: >= 1 posting with multiple ranges"
    for posting in snapshot.postings:  # D25: capture, never surface as scalars
        assert posting.salary_min is None
        assert posting.salary_max is None
        assert posting.salary_currency is None
        assert posting.salary_period is None


@respx.mock
def test_empty_board_is_a_complete_empty_inventory(tmp_path: Path) -> None:
    respx.get(BOARD_URL).mock(
        return_value=httpx.Response(200, content=_fixture_bytes("empty.json"))
    )
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "complete"  # 200 + [] IS an inventory (unlike a 304, D15)
    assert snapshot.postings == []


@respx.mock
def test_per_job_parse_errors_produce_partial(tmp_path: Path) -> None:
    payload = _fixture_json("normal.json")
    del payload["jobs"][0]["title"]  # corrupt exactly one job
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, json=payload))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "partial"
    assert len(snapshot.postings) == len(payload["jobs"]) - 1
    assert snapshot.error is not None and "1 of" in snapshot.error


@respx.mock
def test_transport_failure_maps_to_failed(tmp_path: Path) -> None:
    respx.get(BOARD_URL).mock(side_effect=httpx.ConnectError("boom"))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "failed"
    assert snapshot.postings == []
    assert snapshot.error


@respx.mock
def test_invalid_json_maps_to_failed(tmp_path: Path) -> None:
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, content=b"<html>nope</html>"))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "failed"


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
    assert snapshot.postings == []  # an empty 304 is NOT an inventory (D15)
    assert snapshot.url == BOARD_URL


@respx.mock
def test_remote_policy_derivation(tmp_path: Path) -> None:
    payload = _fixture_json("normal.json")
    payload["jobs"] = payload["jobs"][:2]
    payload["jobs"][0]["location"] = {"name": "Remote — United States"}
    payload["jobs"][1]["location"] = {"name": "New York, NY"}
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, json=payload))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.postings[0].remote_policy == "remote"
    assert snapshot.postings[1].remote_policy == "unknown"


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
    respx.get(HEALTH_URL).mock(return_value=httpx.Response(status_code, content=content))
    assert provider.healthcheck(_fetcher(tmp_path), "acme") == expected
