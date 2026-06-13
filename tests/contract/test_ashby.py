import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from boardwatch.core.models import BoardRequest, ResponseValidators
from boardwatch.core.politeness import Fetcher
from boardwatch.core.settings import Settings
from boardwatch.providers.ashby import AshbyProvider
from boardwatch.providers.base import BoardHealth

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "ashby"
BOARD_URL = "https://api.ashbyhq.com/posting-api/job-board/acme?includeCompensation=true"


def _fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _fixture_json(name: str) -> Any:
    return json.loads(_fixture_bytes(name))


def _fetcher(tmp_path: Path, retries: int = 1) -> Fetcher:
    return Fetcher(Settings(data_dir=tmp_path, config_dir=tmp_path, retry_attempts=retries))


def _request(validators: ResponseValidators | None = None) -> BoardRequest:
    return BoardRequest(provider="ashby", slug="acme", url=BOARD_URL, validators=validators)


provider = AshbyProvider()


def test_board_url_includes_compensation_stable_order() -> None:
    assert provider.board_url("acme") == BOARD_URL


@respx.mock
def test_complete_snapshot_uses_html_to_text(tmp_path: Path) -> None:
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, content=_fixture_bytes("normal.json")))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "complete"
    assert snapshot.url == BOARD_URL
    assert len(snapshot.postings) == len(_fixture_json("normal.json")["jobs"])
    for posting in snapshot.postings:
        assert posting.body_text  # via html_to_text(descriptionHtml)
        assert "<" not in posting.body_text  # HTML was stripped


@respx.mock
def test_single_range_recognized_interval_maps_salary_scalars(tmp_path: Path) -> None:
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, content=_fixture_bytes("normal.json")))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    priced = [p for p in snapshot.postings if p.salary_min is not None]
    assert priced, "fixture contract: >= 1 posting with single-range structured comp"
    for posting in priced:
        assert posting.salary_currency
        assert posting.salary_period in {"year", "month", "week", "day", "hour"}


@respx.mock
def test_one_sided_range_maps_present_side_only(tmp_path: Path) -> None:
    # the attended fixture includes a one-sided (minValue-only) posting
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, content=_fixture_bytes("normal.json")))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    one_sided = [p for p in snapshot.postings if p.salary_min is not None and p.salary_max is None]
    assert one_sided, "fixture contract: >= 1 one-sided (minValue-only) posting"
    for posting in one_sided:
        assert posting.salary_currency and posting.salary_period


@respx.mock
def test_multi_tier_fixture_posting_leaves_all_scalars_null(tmp_path: Path) -> None:
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, content=_fixture_bytes("normal.json")))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    multi = [
        p
        for p in snapshot.postings
        if len((p.raw_json.get("compensation") or {}).get("compensationTiers") or []) > 1
    ]
    assert multi, "fixture contract: >= 1 multi-tier posting"
    for posting in multi:
        assert posting.salary_min is None and posting.salary_max is None
        assert posting.salary_currency is None and posting.salary_period is None
        assert posting.raw_json.get("compensation") is not None  # raw_json intact


def _comp(*components: dict) -> dict:
    # one tier holding `components` (the live per-tier monetary list; deviation-5 field names ONLY)
    return {"compensationTiers": [{"components": list(components)}]}


def _salary(min_v=180000, max_v=220000, interval="1 YEAR", currency="USD") -> dict:
    return {"compensationType": "Salary", "interval": interval,
            "currencyCode": currency, "minValue": min_v, "maxValue": max_v}


@respx.mock
@pytest.mark.parametrize(
    ("comp", "why"),
    [
        (_comp(_salary(), _salary(min_v=90000, max_v=110000)), "multiple salary ranges"),
        (_comp(_salary(), {"compensationType": "Equity", "interval": "1 YEAR",
                           "currencyCode": "USD", "minValue": 1, "maxValue": 2}),
         "salary plus a non-monetary component"),
        (_comp(_salary(interval="1 QUARTER")), "unrecognized interval"),
        (_comp({"compensationType": "Equity", "interval": "1 YEAR",
                "currencyCode": "USD", "minValue": 1, "maxValue": 2}), "no salary component"),
    ],
)
def test_non_single_range_cases_leave_all_scalars_null(
    tmp_path: Path, comp: dict, why: str
) -> None:
    payload = _fixture_json("normal.json")
    payload["jobs"] = payload["jobs"][:1]
    payload["jobs"][0]["compensation"] = comp
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, content=json.dumps(payload).encode()))
    posting = provider.fetch_board(_fetcher(tmp_path), _request()).postings[0]
    assert posting.salary_min is None and posting.salary_max is None, why
    assert posting.salary_currency is None and posting.salary_period is None, why
    assert posting.raw_json["compensation"] == comp  # raw_json intact


@respx.mock
def test_max_only_one_sided_maps_present_side(tmp_path: Path) -> None:
    payload = _fixture_json("normal.json")
    payload["jobs"] = payload["jobs"][:1]
    payload["jobs"][0]["compensation"] = _comp(_salary(min_v=None, max_v=200000))
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, content=json.dumps(payload).encode()))
    posting = provider.fetch_board(_fetcher(tmp_path), _request()).postings[0]
    assert posting.salary_min is None and posting.salary_max == 200000.0
    assert posting.salary_currency == "USD" and posting.salary_period == "year"


@respx.mock
def test_no_compensation_leaves_scalars_null(tmp_path: Path) -> None:
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, content=_fixture_bytes("normal.json")))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    # specifically the postings with NO compensation block (fixture has ≥1) — not just "any None"
    no_comp = [p for p in snapshot.postings if not (p.raw_json.get("compensation") or {})]
    assert no_comp, "fixture contract: >= 1 posting without compensation"
    for posting in no_comp:
        assert posting.salary_min is None and posting.salary_max is None
        assert posting.salary_currency is None and posting.salary_period is None


@respx.mock
def test_empty_board_is_complete_empty(tmp_path: Path) -> None:
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, content=_fixture_bytes("empty.json")))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "complete"
    assert snapshot.postings == []


@respx.mock
def test_per_job_parse_error_produces_partial(tmp_path: Path) -> None:
    payload = _fixture_json("normal.json")
    del payload["jobs"][0]["title"]
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, json=payload))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "partial"
    assert len(snapshot.postings) == len(payload["jobs"]) - 1


@respx.mock
def test_dead_maps_to_failed(tmp_path: Path) -> None:
    respx.get(BOARD_URL).mock(return_value=httpx.Response(404, content=_fixture_bytes("dead.json")))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "failed"
    assert snapshot.postings == []


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
    assert snapshot.postings == []


@respx.mock
@pytest.mark.parametrize(
    ("fixture", "status_code", "expected"),
    [
        ("normal.json", 200, BoardHealth.OK),
        ("empty.json", 200, BoardHealth.EMPTY),
        ("dead.json", 404, BoardHealth.DEAD),
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


def test_huge_board_parses_under_memory_ceiling(capsys: pytest.CaptureFixture[str]) -> None:
    """D26: the 1.7 MB worst case parses in a SUBPROCESS with peak tracemalloc ≤ 64 MiB
    over the COMPLETE provider path — fetch_board(fetcher) → BoardSnapshot, not just
    json.loads. The probe goes through fetch_board with a fixture-backed Fetcher; the
    parent emits the report so the measured peak is always logged, even on success."""
    result = subprocess.run(
        [sys.executable, "-m", "tests.contract._ashby_huge_probe", str(FIXTURES / "huge.json")],
        capture_output=True,
        text=True,
        check=True,
    )
    report = json.loads(result.stdout)
    with capsys.disabled():  # pytest captures stdout by default; surface the peak on success too
        print(f"ashby huge-board D26 measurement: {report}")
    assert report["status"] == "complete"
    assert report["postings"] >= 100
    assert report["peak_bytes"] <= 64 * 1024 * 1024, report
