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
def test_greenhouse_reports_meta_total(tmp_path: Path) -> None:
    """Confirmed live 2026-08-22: stripe meta.total=576, databricks 818."""
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, content=_fixture_bytes("normal.json")))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.board_reported_total == 5  # tests/fixtures/greenhouse/normal.json meta.total
    assert snapshot.board_enumerated == 5
    assert snapshot.detail_deferred == 0


@respx.mock
def test_greenhouse_meta_total_is_not_backfilled_from_posting_count(tmp_path: Path) -> None:
    """meta.total (97) deliberately differs from len(jobs) (2), so this fails immediately
    under a len(postings) backfill — the fixture's normal.json cannot discriminate the two
    because its meta.total happens to equal its job count (D-271, D-028)."""
    payload = {
        "meta": {"total": 97},
        "jobs": [{"id": 1, "title": "Engineer A"}, {"id": 2, "title": "Engineer B"}],
    }
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, json=payload))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.board_reported_total == 97
    assert snapshot.board_enumerated == 2


_ABSENT_META = object()  # sentinel: omit the "meta" key entirely, distinct from meta=None


@respx.mock
@pytest.mark.parametrize(
    ("meta_value", "why"),
    [
        ({"total": None}, "total key present but null"),
        ({"total": "unknown"}, "total is non-numeric"),
        # `True` is an `int` in Python, so the numeric isinstance check admitted it and
        # `meta: {"total": true}` persisted board_reported_total = 1 — a 500-job board reading
        # "500 held of 1 stated". workday.py:_uncapped_total already excludes bool explicitly.
        ({"total": True}, "total is a bool, not a count"),
        ("not-a-dict", "meta is not a dict"),
        (_ABSENT_META, "meta key absent entirely"),
    ],
)
def test_malformed_meta_total_falls_back_to_none_not_a_crash(
    tmp_path: Path, meta_value: Any, why: str
) -> None:
    """A metadata glitch must never fail the whole board over postings that parsed fine —
    the identical defect class fixed in workday.py's _uncapped_total this round."""
    payload: dict[str, Any] = {
        "jobs": [{"id": 1, "title": "Engineer A"}, {"id": 2, "title": "Engineer B"}],
    }
    if meta_value is not _ABSENT_META:
        payload["meta"] = meta_value
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, json=payload))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "complete", why
    assert len(snapshot.postings) == 2, why
    assert snapshot.board_reported_total is None, why


@respx.mock
@pytest.mark.parametrize(
    ("total_token", "why"),
    [
        ("NaN", "NaN -> int() raises ValueError"),
        ("Infinity", "Infinity -> int() raises OverflowError"),
        ("-Infinity", "-Infinity -> int() raises OverflowError"),
    ],
)
def test_meta_total_nan_or_infinity_falls_back_to_none_not_a_crash(
    tmp_path: Path, total_token: str, why: str
) -> None:
    """json.loads accepts NaN/Infinity by default and int() raises on them (ValueError for NaN,
    OverflowError for Infinity) — the one numeric input that clears _meta_total's
    isinstance(int | float) guard yet must not fail the board over postings that parsed fine.
    Guards greenhouse.py _meta_total's `except (ValueError, OverflowError)`; the dict-valued
    parametrization above can never carry a non-finite float, so without this case removing that
    except leaves the suite green while a live board crashes on json.loads' NaN."""
    content = (
        '{"meta": {"total": ' + total_token + '}, '
        '"jobs": [{"id": 1, "title": "Engineer A"}, {"id": 2, "title": "Engineer B"}]}'
    ).encode()
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, content=content))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "complete", why
    assert len(snapshot.postings) == 2, why
    assert snapshot.board_reported_total is None, why


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


@respx.mock
def test_healthcheck_http_500_maps_to_error(tmp_path: Path) -> None:
    # an HTTP response WAS received but unhealthy → ERROR (not UNREACHABLE) — D27
    respx.get(HEALTH_URL).mock(return_value=httpx.Response(500, content=b""))
    assert provider.healthcheck(_fetcher(tmp_path), "acme") == BoardHealth.ERROR


@respx.mock
def test_healthcheck_transport_failure_maps_to_unreachable(tmp_path: Path) -> None:
    # no HTTP response (transport-level after retries) → UNREACHABLE — D27
    respx.get(HEALTH_URL).mock(side_effect=httpx.ConnectError("boom"))
    assert provider.healthcheck(_fetcher(tmp_path), "acme") == BoardHealth.UNREACHABLE


@respx.mock
def test_board_enumerated_counts_listed_ids_not_surviving_postings(tmp_path: Path) -> None:
    """`board_enumerated` means DISTINCT POSTING IDS THE BOARD LISTED, identically across all
    six providers (core/models.py). `len(postings)` counted what SURVIVED parsing, so
    `board_reported_total - board_enumerated` reported a parse-failure count on four providers
    and a listing shortfall on the other two — a persisted column with mixed semantics.

    Both halves are pinned separately, because either one alone can be satisfied by accident.
    A parse failure must NOT lower the count (3 listed, 1 unparseable, 2 parsed -> 3), and a
    duplicate id must NOT raise it (2 rows, 1 id -> 1)."""
    dropped = {
        "meta": {"total": 3},
        "jobs": [
            {"id": 1, "title": "Engineer A"},
            {"id": 2, "title": ""},  # parse failure: empty title
            {"id": 3, "title": "Engineer C"},
        ],
    }
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, json=dropped))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.board_enumerated == 3
    assert len(snapshot.postings) == 2
    assert snapshot.board_reported_total == 3

    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, json={
        "meta": {"total": 1},
        "jobs": [{"id": 7, "title": "Engineer A"}, {"id": 7, "title": "Engineer A again"}],
    }))
    duped = provider.fetch_board(_fetcher(tmp_path / "dup"), _request())
    assert duped.board_enumerated == 1
    assert len(duped.postings) == 2


@respx.mock
def test_an_id_less_row_is_excluded_from_board_enumerated(tmp_path: Path) -> None:
    """The live Mastercard shape: the board states one more than we can key. A row with no id
    is a posting we can never fetch, dedupe or close, so it must LOWER `board_enumerated` and
    make the shortfall visible, not be counted as enumerated."""
    payload = {
        "meta": {"total": 2},
        "jobs": [{"id": 1, "title": "Engineer A"}, {"title": "No id at all"}],
    }
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, json=payload))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.board_reported_total == 2
    assert snapshot.board_enumerated == 1


@respx.mock
@pytest.mark.parametrize(
    ("raw_total", "why"),
    [(b"NaN", "NaN"), (b"Infinity", "Infinity"), (b"-Infinity", "-Infinity")],
)
def test_a_non_finite_meta_total_does_not_fail_the_board(
    tmp_path: Path, raw_total: bytes, why: str
) -> None:
    """`json.loads` accepts NaN/Infinity by default (a non-standard extension it enables), and
    `int()` raises on both. That call sat OUTSIDE the payload try/except, so one non-finite
    metadata value failed the whole board — breaking the promise made two lines above it.
    Sent as raw bytes because a JSON encoder would refuse to emit these."""
    body = b'{"meta": {"total": ' + raw_total + b'}, "jobs": [{"id": 1, "title": "A"}]}'
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, content=body))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "complete", why
    assert len(snapshot.postings) == 1, why
    assert snapshot.board_reported_total is None, why


@respx.mock
def test_a_negative_meta_total_is_clamped_like_its_siblings(tmp_path: Path) -> None:
    """`workday.py:232` and `smartrecruiters.py:103` both clamp with `max(0, int(...))`; this
    one did not. Reproduced: one row at `board_reported_total=-5` raised
    `ContradictoryCoverage` out of `boardwatch coverage` and took the WHOLE report down with
    it, so every healthy board's number became unreachable."""
    payload = {"meta": {"total": -5}, "jobs": [{"id": 1, "title": "Engineer A"}]}
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, json=payload))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.board_reported_total == 0
