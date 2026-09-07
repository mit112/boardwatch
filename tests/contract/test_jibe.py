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
from boardwatch.providers.jibe import JibeProvider

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "jibe"
HOST = "careers.acme.test"
PAGE_LIMIT = 100
BOARD_URL = f"https://{HOST}/api/jobs?page=1&limit={PAGE_LIMIT}"
HEALTH_URL = f"https://{HOST}/api/jobs?page=1&limit=1"


def _page_url(page: int) -> str:
    return f"https://{HOST}/api/jobs?page={page}&limit={PAGE_LIMIT}"


def _fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _fixture_json(name: str) -> Any:
    return json.loads(_fixture_bytes(name))


def _fetcher(tmp_path: Path, retries: int = 1) -> Fetcher:
    return Fetcher(Settings(data_dir=tmp_path, config_dir=tmp_path, retry_attempts=retries))


def _request(validators: ResponseValidators | None = None) -> BoardRequest:
    return BoardRequest(provider="jibe", slug=HOST, url=BOARD_URL, validators=validators)


def _envelope(rows: list[dict[str, Any]], total: int) -> bytes:
    """A page in the recorded envelope shape, carrying `rows` as its `jobs`."""
    page = _fixture_json("normal.json")
    page["jobs"] = rows
    page["totalCount"] = total
    page["count"] = total
    return json.dumps(page).encode()


def _clone_rows(count: int, start: int) -> list[dict[str, Any]]:
    """`count` rows cloned from the PINNED fixture's first row, with unique ids.

    Derived from the fixture rather than authored inline, so a shape change in `normal.json`
    reaches the pagination tests instead of leaving them asserting against a stale hand-written
    row (CLAUDE.md: a fixture that sits still while production churns)."""
    template = _fixture_json("normal.json")["jobs"][0]["data"]
    rows: list[dict[str, Any]] = []
    for offset in range(count):
        data = dict(template)
        data["req_id"] = str(start + offset)
        data["slug"] = data["req_id"]
        data["apply_url"] = f"https://careers-acme.icims.test/jobs/{data['req_id']}/login"
        rows.append({"data": data})
    return rows


provider = JibeProvider()


def test_board_url_is_page_one_with_stable_parameter_order() -> None:
    assert provider.board_url(HOST) == BOARD_URL


def test_normalize_slug_lowercases_the_host() -> None:
    assert provider.normalize_slug("Careers.ACME.Test") == HOST
    assert provider.normalize_slug("  careers.acme.test.  ") == HOST


@pytest.mark.parametrize(
    "bad",
    ["", "acme", "careers.acme.test:8080", "careers.acme.test?x=1", "careers acme.test"],
)
def test_normalize_slug_refuses_a_non_host(bad: str) -> None:
    with pytest.raises(ValueError):
        provider.normalize_slug(bad)


@respx.mock
def test_complete_snapshot_uses_html_to_text(tmp_path: Path) -> None:
    respx.get(BOARD_URL).mock(
        return_value=httpx.Response(200, content=_fixture_bytes("normal.json"))
    )
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "complete"
    assert snapshot.url == BOARD_URL
    assert len(snapshot.postings) == len(_fixture_json("normal.json")["jobs"])
    for posting in snapshot.postings:
        assert posting.body_text
        assert "<" not in posting.body_text


@respx.mock
def test_body_text_concatenates_the_three_sections_in_order(tmp_path: Path) -> None:
    respx.get(BOARD_URL).mock(
        return_value=httpx.Response(200, content=_fixture_bytes("normal.json"))
    )
    by_id = {p.provider_posting_id: p for p in provider.fetch_board(
        _fetcher(tmp_path), _request()).postings}
    body = by_id["1000001"].body_text
    assert body.index("Senior Platform Engineer") < body.index("distributed systems")
    assert body.index("distributed systems") < body.index("deployment pipeline")
    # blank sections are skipped, not rendered as empty blocks
    assert by_id["1000002"].body_text == "Build the Acme Corp analytics platform."


@respx.mock
def test_locations_fall_back_to_city_state_country(tmp_path: Path) -> None:
    respx.get(BOARD_URL).mock(
        return_value=httpx.Response(200, content=_fixture_bytes("normal.json"))
    )
    by_id = {p.provider_posting_id: p for p in provider.fetch_board(
        _fetcher(tmp_path), _request()).postings}
    assert by_id["1000001"].locations == ["Acme HQ, Springfield"]
    assert by_id["1000002"].locations == ["Riverton, Wyoming, United States"]


@respx.mock
def test_remote_policy_from_location_text_and_location_type(tmp_path: Path) -> None:
    respx.get(BOARD_URL).mock(
        return_value=httpx.Response(200, content=_fixture_bytes("normal.json"))
    )
    by_id = {p.provider_posting_id: p for p in provider.fetch_board(
        _fetcher(tmp_path), _request()).postings}
    assert by_id["1000003"].remote_policy == "remote"  # "Remote - United States"
    assert by_id["1000004"].remote_policy == "remote"  # location_type: "REMOTE"
    assert by_id["1000001"].remote_policy == "unknown"  # never inferred as onsite/hybrid


@respx.mock
def test_posting_url_falls_back_to_the_board_host(tmp_path: Path) -> None:
    """Every live `apply_url` was on an icims.com host, so the fallback is the measured path."""
    respx.get(BOARD_URL).mock(
        return_value=httpx.Response(200, content=_fixture_bytes("normal.json"))
    )
    for posting in provider.fetch_board(_fetcher(tmp_path), _request()).postings:
        assert posting.url == f"https://{HOST}/jobs/{posting.provider_posting_id}"


@respx.mock
def test_posting_url_prefers_a_payload_url_on_the_same_host(tmp_path: Path) -> None:
    payload = _fixture_json("normal.json")
    payload["jobs"] = payload["jobs"][:1]
    payload["jobs"][0]["data"]["apply_url"] = f"https://{HOST}/careers-home/jobs/1000001"
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, json=payload))
    posting = provider.fetch_board(_fetcher(tmp_path), _request()).postings[0]
    assert posting.url == f"https://{HOST}/careers-home/jobs/1000001"


@respx.mock
def test_posted_and_updated_timestamps_are_naive_utc(tmp_path: Path) -> None:
    respx.get(BOARD_URL).mock(
        return_value=httpx.Response(200, content=_fixture_bytes("normal.json"))
    )
    posting = provider.fetch_board(_fetcher(tmp_path), _request()).postings[0]
    assert posting.posted_at is not None and posting.posted_at.tzinfo is None
    assert posting.posted_at.isoformat() == "2026-09-01T12:00:00"
    assert posting.updated_at is not None
    assert posting.updated_at.isoformat() == "2026-09-03T09:30:00"


@respx.mock
def test_salary_scalars_only_for_positive_numbers(tmp_path: Path) -> None:
    """Zero is the live "not published" value on every probed tenant, not a figure of $0."""
    respx.get(BOARD_URL).mock(
        return_value=httpx.Response(200, content=_fixture_bytes("normal.json"))
    )
    by_id = {p.provider_posting_id: p for p in provider.fetch_board(
        _fetcher(tmp_path), _request()).postings}
    priced = by_id["1000001"]
    assert (priced.salary_min, priced.salary_max) == (185000.0, 225000.0)
    # the payload states neither a currency nor a period, anywhere
    assert priced.salary_currency is None and priced.salary_period is None
    one_sided = by_id["1000005"]  # salary_min_value 0, salary_max_value 96000
    assert one_sided.salary_min is None and one_sided.salary_max == 96000.0
    for absent in (by_id["1000002"], by_id["1000003"]):  # zeroes, and nulls
        assert absent.salary_min is None and absent.salary_max is None
        assert absent.salary_currency is None and absent.salary_period is None


@respx.mock
def test_blank_department_maps_to_none(tmp_path: Path) -> None:
    respx.get(BOARD_URL).mock(
        return_value=httpx.Response(200, content=_fixture_bytes("normal.json"))
    )
    by_id = {p.provider_posting_id: p for p in provider.fetch_board(
        _fetcher(tmp_path), _request()).postings}
    assert by_id["1000001"].department == "Platform"
    assert by_id["1000002"].department is None  # "" live on 228/228 probed postings
    assert by_id["1000002"].raw_json["categories"] == [{"name": "Engineering"}]  # not mined


@respx.mock
def test_raw_json_is_the_data_dict(tmp_path: Path) -> None:
    respx.get(BOARD_URL).mock(
        return_value=httpx.Response(200, content=_fixture_bytes("normal.json"))
    )
    posting = provider.fetch_board(_fetcher(tmp_path), _request()).postings[0]
    assert posting.raw_json == _fixture_json("normal.json")["jobs"][0]["data"]


@respx.mock
def test_board_reported_total_comes_from_total_count(tmp_path: Path) -> None:
    respx.get(BOARD_URL).mock(
        return_value=httpx.Response(200, content=_fixture_bytes("normal.json"))
    )
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.board_reported_total == 5
    assert snapshot.board_enumerated == 5


@respx.mock
def test_a_board_stating_no_total_reports_none(tmp_path: Path) -> None:
    """None is a CLAIM that the board stated nothing; backfilling the row count would make
    coverage 100% by arithmetic, forever."""
    payload = _fixture_json("normal.json")
    del payload["totalCount"]
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, json=payload))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.board_reported_total is None
    assert snapshot.board_enumerated == 5


@respx.mock
def test_pages_until_a_short_page(tmp_path: Path) -> None:
    """`limit` is pinned at 100 and paging past the end answers 200 with an empty `jobs`, so a
    103-posting board is page 1 (full) + page 2 (short) and MUST NOT stop at page 1."""
    respx.get(_page_url(1)).mock(
        return_value=httpx.Response(200, content=_envelope(_clone_rows(100, 2000000), 103))
    )
    respx.get(_page_url(2)).mock(
        return_value=httpx.Response(200, content=_envelope(_clone_rows(3, 2000100), 103))
    )
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "complete"
    assert len(snapshot.postings) == 103
    assert snapshot.board_reported_total == 103
    assert snapshot.board_enumerated == 103


@respx.mock
def test_an_empty_page_terminates_without_a_further_request(tmp_path: Path) -> None:
    """Past the last page the API answers 200 with `"jobs": []` — measured, it does not 4xx
    and it does not wrap to page 1."""
    page1 = respx.get(_page_url(1)).mock(
        return_value=httpx.Response(200, content=_envelope(_clone_rows(100, 3000000), 100))
    )
    page2 = respx.get(_page_url(2)).mock(
        return_value=httpx.Response(200, content=_envelope([], 100))
    )
    page3 = respx.get(_page_url(3)).mock(
        return_value=httpx.Response(200, content=_envelope([], 100))
    )
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "complete"
    assert len(snapshot.postings) == 100
    assert (page1.call_count, page2.call_count, page3.call_count) == (1, 1, 0)


@respx.mock
def test_a_failing_later_page_is_partial_not_failed(tmp_path: Path) -> None:
    respx.get(_page_url(1)).mock(
        return_value=httpx.Response(200, content=_envelope(_clone_rows(100, 4000000), 150))
    )
    respx.get(_page_url(2)).mock(return_value=httpx.Response(500))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "partial"
    assert len(snapshot.postings) == 100
    assert snapshot.error is not None and "page 2" in snapshot.error


@respx.mock
def test_board_enumerated_counts_listed_ids_not_surviving_postings(tmp_path: Path) -> None:
    """`board_enumerated` means DISTINCT POSTING IDS LISTED on every provider, counted BEFORE a
    per-row parse failure drops one (core/models.py) — and here, across ALL pages. Counting
    survivors makes it a parse-failure count, and one persisted column then means two things."""
    rows = _clone_rows(100, 5000000)
    del rows[0]["data"]["title"]  # a row that will fail to parse
    rows[1]["data"].pop("req_id")  # a row that cannot be keyed at all
    page2 = _clone_rows(2, 5000100)
    respx.get(_page_url(1)).mock(return_value=httpx.Response(200, content=_envelope(rows, 102)))
    respx.get(_page_url(2)).mock(
        return_value=httpx.Response(200, content=_envelope(page2, 102))
    )
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "partial"
    assert len(snapshot.postings) == 100  # 102 listed, minus the untitled and the unkeyed row
    assert snapshot.board_enumerated == 101  # the unkeyed row cannot be counted; the other can
    assert snapshot.board_reported_total == 102


@respx.mock
def test_duplicate_ids_across_pages_are_counted_once(tmp_path: Path) -> None:
    rows = _clone_rows(100, 6000000)
    respx.get(_page_url(1)).mock(return_value=httpx.Response(200, content=_envelope(rows, 100)))
    respx.get(_page_url(2)).mock(
        return_value=httpx.Response(200, content=_envelope(rows[:1], 100))
    )
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.board_enumerated == 100


@respx.mock
def test_empty_board_is_complete_empty(tmp_path: Path) -> None:
    respx.get(BOARD_URL).mock(
        return_value=httpx.Response(200, content=_fixture_bytes("empty.json"))
    )
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "complete"
    assert snapshot.postings == []
    assert snapshot.board_reported_total == 0
    assert snapshot.board_enumerated == 0


@respx.mock
def test_per_job_parse_error_produces_partial(tmp_path: Path) -> None:
    payload = _fixture_json("normal.json")
    del payload["jobs"][0]["data"]["title"]
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, json=payload))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "partial"
    assert len(snapshot.postings) == len(payload["jobs"]) - 1
    assert snapshot.error is not None and "empty title" in snapshot.error


@respx.mock
def test_dead_maps_to_failed(tmp_path: Path) -> None:
    respx.get(BOARD_URL).mock(
        return_value=httpx.Response(404, content=_fixture_bytes("dead_404.json"))
    )
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "failed"
    assert snapshot.postings == []


@respx.mock
def test_unreachable_maps_to_failed(tmp_path: Path) -> None:
    respx.get(BOARD_URL).mock(side_effect=httpx.ConnectError("boom"))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "failed"
    assert snapshot.postings == []


@respx.mock
def test_html_shell_on_a_200_is_failed(tmp_path: Path) -> None:
    """A live careers host answers 200 with an Angular shell on a path it does not recognize."""
    respx.get(BOARD_URL).mock(
        return_value=httpx.Response(200, content=b"<!DOCTYPE html><html></html>")
    )
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "failed"
    assert snapshot.error is not None and "invalid board payload" in snapshot.error


@respx.mock
def test_304_maps_to_unchanged(tmp_path: Path) -> None:
    headers = _fixture_json("normal_response_headers.json")
    assert headers["last_modified"] is None  # the live host sends an ETag and no Last-Modified
    route = respx.get(BOARD_URL).mock(return_value=httpx.Response(304))
    snapshot = provider.fetch_board(
        _fetcher(tmp_path), _request(ResponseValidators(etag=headers["etag"]))
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
        ("dead_404.json", 404, BoardHealth.DEAD),
        (None, 500, BoardHealth.ERROR),
    ],
)
def test_healthcheck_mapping(
    tmp_path: Path, fixture: str | None, status_code: int, expected: BoardHealth
) -> None:
    content = _fixture_bytes(fixture) if fixture else b""
    respx.get(HEALTH_URL).mock(return_value=httpx.Response(status_code, content=content))
    assert provider.healthcheck(_fetcher(tmp_path), HOST) == expected


@respx.mock
def test_healthcheck_non_json_is_error(tmp_path: Path) -> None:
    respx.get(HEALTH_URL).mock(
        return_value=httpx.Response(200, content=b"<!DOCTYPE html><html></html>")
    )
    assert provider.healthcheck(_fetcher(tmp_path), HOST) == BoardHealth.ERROR


@respx.mock
def test_healthcheck_transport_failure_is_unreachable(tmp_path: Path) -> None:
    respx.get(HEALTH_URL).mock(side_effect=httpx.ConnectError("boom"))
    assert provider.healthcheck(_fetcher(tmp_path), HOST) == BoardHealth.UNREACHABLE


@respx.mock
def test_an_entry_with_no_data_object_is_counted_and_reported(tmp_path: Path) -> None:
    """A `jobs` entry we cannot read is a posting we cannot key. Dropping it SILENTLY would
    shrink the listing while `status` stayed "complete" — the one status that authorizes
    apply_board to close everything it no longer sees."""
    payload = _fixture_json("normal.json")
    payload["jobs"].append({"data": None})
    payload["jobs"].append({})
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, json=payload))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "partial"
    assert snapshot.error is not None and "dropped 2 entries" in snapshot.error
    assert len(snapshot.postings) == 5
    assert snapshot.board_enumerated == 5


@respx.mock
def test_a_partial_names_how_many_rows_failed(tmp_path: Path) -> None:
    payload = _fixture_json("normal.json")
    for job in payload["jobs"][:2]:
        del job["data"]["title"]
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, json=payload))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "partial"
    assert snapshot.error is not None and "2 of 5 jobs failed to parse" in snapshot.error


@respx.mock
def test_all_rows_failing_is_failed_not_partial(tmp_path: Path) -> None:
    payload = _fixture_json("normal.json")
    for job in payload["jobs"]:
        del job["data"]["title"]
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, json=payload))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "failed"
    assert snapshot.postings == []
    assert snapshot.error is not None and "all 5 jobs failed to parse" in snapshot.error
