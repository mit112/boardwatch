"""Amazon contract tests.

The amazon.jobs search API answers HTTP 200 for every one of its refusals, so the assertions
here are mostly about the `error` FIELD rather than a status code. The other thing this file
pins is the closed category catalog: a wrong category is answered with an empty board and
`error: null`, so nothing but the catalog stands between a typo and a `complete` empty
inventory that closes every posting the board holds.
"""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from boardwatch.core.models import BoardRequest, ResponseValidators
from boardwatch.core.politeness import Fetcher
from boardwatch.core.settings import Settings
from boardwatch.providers.amazon import _CATEGORIES, AmazonProvider
from boardwatch.providers.base import BoardHealth

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "amazon"
SLUG = "software-development"
CATEGORY = "Software Development"
PAGE_LIMIT = 100
SEARCH = "https://www.amazon.jobs/en/search.json"
BOARD_URL = (
    f"{SEARCH}?offset=0&result_limit={PAGE_LIMIT}&sort=recent"
    f"&category%5B%5D=Software%20Development"
)
HEALTH_URL = f"{SEARCH}?offset=0&result_limit=1&sort=recent&category%5B%5D=Software%20Development"


def _page_url(offset: int) -> str:
    return (
        f"{SEARCH}?offset={offset}&result_limit={PAGE_LIMIT}&sort=recent"
        f"&category%5B%5D=Software%20Development"
    )


def _fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _fixture_json(name: str) -> Any:
    return json.loads(_fixture_bytes(name))


def _fetcher(tmp_path: Path, retries: int = 1) -> Fetcher:
    return Fetcher(Settings(data_dir=tmp_path, config_dir=tmp_path, retry_attempts=retries))


def _request(validators: ResponseValidators | None = None) -> BoardRequest:
    return BoardRequest(provider="amazon", slug=SLUG, url=BOARD_URL, validators=validators)


def _envelope(jobs: list[Any], hits: int) -> bytes:
    """A page in the recorded envelope shape, carrying `jobs` and stating `hits`."""
    page = _fixture_json("normal.json")
    page["jobs"] = jobs
    page["hits"] = hits
    return json.dumps(page).encode()


def _clone_rows(count: int, start: int) -> list[dict[str, Any]]:
    """`count` rows cloned from the PINNED fixture's first row, with unique ids.

    Derived from the fixture rather than authored inline, so a shape change in `normal.json`
    reaches the pagination tests instead of leaving them asserting against a stale hand-written
    row (CLAUDE.md: a fixture that sits still while production churns)."""
    template = _fixture_json("normal.json")["jobs"][0]
    rows: list[dict[str, Any]] = []
    for offset in range(count):
        row = dict(template)
        row["id_icims"] = str(start + offset)
        row["id"] = f"b{start + offset:07d}-0000-4000-8000-000000000000"
        row["job_path"] = f"/en/jobs/{row['id_icims']}/senior-platform-engineer"
        rows.append(row)
    return rows


provider = AmazonProvider()


# ---------------------------------------------------------------------------------------
# Identity and the closed catalog.
# ---------------------------------------------------------------------------------------


def test_board_url_is_offset_zero_with_stable_parameter_order() -> None:
    assert provider.board_url(SLUG) == BOARD_URL


def test_normalize_slug_accepts_a_catalog_token_case_insensitively() -> None:
    assert provider.normalize_slug("  Software-Development ") == SLUG


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "software development",  # the raw category, spaces intact
        "Software Development",
        "totally-made-up",
        "en",  # what the default path extractor would hand us from a posting URL
        "software-developmen",
    ],
)
def test_normalize_slug_refuses_anything_outside_the_catalog(bad: str) -> None:
    """A category the API does not know answers `hits: 0`, `jobs: []` and `error: null` -- so
    an unguarded typo is watched forever as a board that merely happens to be empty, and one
    `complete` empty inventory closes every posting the real board holds."""
    with pytest.raises(ValueError, match="job categories"):
        provider.normalize_slug(bad)


def test_the_catalog_matches_the_recorded_category_facet() -> None:
    """The catalog is pinned against the RECORDED facet capture, which is a different path from
    the code that consumes it: a hand-edited `_CATEGORIES` value no longer silently becomes a
    board that fetches nothing. `facets_category.json` is the 2026-09-07 capture."""
    recorded = _fixture_json("facets_category.json")["facets"]["category_facet"]
    counts = {name: count for entry in recorded for name, count in entry.items()}
    assert len(counts) == 38
    assert set(_CATEGORIES.values()) == set(counts)
    assert list(_CATEGORIES) == sorted(_CATEGORIES)
    # EVERY category under the 10,000 offset ceiling is what makes category-per-board a correct
    # enumeration strategy rather than a convenience. The unfiltered corpus is not.
    assert max(counts.values()) < 10000
    assert sum(counts.values()) > 10000


def test_board_url_refuses_an_out_of_catalog_slug() -> None:
    with pytest.raises(ValueError):
        provider.board_url("totally-made-up")


@respx.mock
def test_an_out_of_catalog_slug_never_reaches_the_network(tmp_path: Path) -> None:
    route = respx.get(url__startswith=SEARCH).mock(return_value=httpx.Response(200))
    snapshot = provider.fetch_board(
        _fetcher(tmp_path),
        BoardRequest(provider="amazon", slug="totally-made-up", url=BOARD_URL),
    )
    assert snapshot.status == "failed"
    assert snapshot.error is not None and "invalid amazon slug" in snapshot.error
    assert route.call_count == 0


# ---------------------------------------------------------------------------------------
# The happy path and the field mapping.
# ---------------------------------------------------------------------------------------


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


def _by_id(tmp_path: Path) -> dict[str, Any]:
    respx.get(BOARD_URL).mock(
        return_value=httpx.Response(200, content=_fixture_bytes("normal.json"))
    )
    return {
        p.provider_posting_id: p
        for p in provider.fetch_board(_fetcher(tmp_path), _request()).postings
    }


@respx.mock
def test_body_text_concatenates_the_three_sections_in_order(tmp_path: Path) -> None:
    by_id = _by_id(tmp_path)
    body = by_id["9000001"].body_text
    assert body.index("deployment platform") < body.index("distributed systems")
    assert body.index("distributed systems") < body.index("deployment pipeline")
    # blank sections are skipped, not rendered as empty blocks
    assert by_id["9000002"].body_text == "Build the Acme Corp analytics platform."


@respx.mock
def test_the_posting_id_is_id_icims_and_the_url_carries_it(tmp_path: Path) -> None:
    """`id` is a UUID; `id_icims` is the number the public posting URL carries, so it is the only
    one an aggregator's deep link could converge onto."""
    by_id = _by_id(tmp_path)
    assert set(by_id) == {"900000" + n for n in "12345"}
    for posting_id, posting in by_id.items():
        assert posting.url.startswith(f"https://www.amazon.jobs/en/jobs/{posting_id}/")
        assert posting.raw_json["id"] != posting_id  # the UUID is NOT the id we key on


@respx.mock
def test_locations_fall_back_to_city_state_country(tmp_path: Path) -> None:
    by_id = _by_id(tmp_path)
    assert by_id["9000001"].locations == ["Springfield, Illinois, USA"]
    assert by_id["9000003"].locations == ["Sparks, Nevada, USA"]  # normalized_location blank


@respx.mock
def test_remote_policy_reads_the_virtual_location_type_then_the_text(tmp_path: Path) -> None:
    """The location TEXT said remote 0 times in 770 live rows, so the structured
    `locations[].type` is the rule that actually fires. `onsite` is never asserted."""
    by_id = _by_id(tmp_path)
    assert by_id["9000004"].remote_policy == "remote"  # locations[].type == "VIRTUAL"
    assert by_id["9000005"].remote_policy == "remote"  # "Remote - Bellevue, ..." text
    assert by_id["9000001"].remote_policy == "unknown"  # ONSITE is NOT mapped to "onsite"


@respx.mock
def test_posted_date_parses_both_spacings_and_survives_an_unparseable_one(
    tmp_path: Path,
) -> None:
    by_id = _by_id(tmp_path)
    double = by_id["9000001"].posted_at  # "September  4, 2026" -- a DOUBLE space
    single = by_id["9000002"].posted_at  # "October 12, 2026"
    assert double is not None and double.isoformat() == "2026-09-04T00:00:00"
    assert single is not None and single.isoformat() == "2026-10-12T00:00:00"
    # an unparseable date keeps posted_at NULL and does NOT fail the row
    assert by_id["9000005"].posted_at is None
    assert by_id["9000005"].title


@respx.mock
def test_updated_at_is_never_set_from_the_relative_updated_time(tmp_path: Path) -> None:
    """`updated_time` is "2 days" / "10 months" -- a duration, not a timestamp. It stays in
    raw_json; mapping it to a datetime column would rewrite itself on every scan."""
    by_id = _by_id(tmp_path)
    for posting in by_id.values():
        assert posting.updated_at is None
    assert by_id["9000001"].raw_json["updated_time"] == "2 days"


@respx.mock
def test_department_is_the_job_family_not_the_search_category(tmp_path: Path) -> None:
    by_id = _by_id(tmp_path)
    assert by_id["9000001"].department == "Platform Engineering"
    assert by_id["9000001"].raw_json["job_category"] == CATEGORY  # the board itself, not a dept
    assert by_id["9000002"].department is None  # blank job_family


@respx.mock
def test_no_salary_scalar_is_ever_written(tmp_path: Path) -> None:
    """The payload carries no pay field of any kind (checked over 2,597 live rows), so D19
    structured-only leaves all four NULL."""
    for posting in _by_id(tmp_path).values():
        assert posting.salary_min is None and posting.salary_max is None
        assert posting.salary_currency is None and posting.salary_period is None


@respx.mock
def test_raw_json_is_the_job_dict(tmp_path: Path) -> None:
    respx.get(BOARD_URL).mock(
        return_value=httpx.Response(200, content=_fixture_bytes("normal.json"))
    )
    posting = provider.fetch_board(_fetcher(tmp_path), _request()).postings[0]
    assert posting.raw_json == _fixture_json("normal.json")["jobs"][0]


@respx.mock
def test_a_row_with_no_usable_job_path_is_skipped_rather_than_given_a_made_up_url(
    tmp_path: Path,
) -> None:
    payload = _fixture_json("normal.json")
    del payload["jobs"][0]["job_path"]
    payload["jobs"][1]["job_path"] = "https://careers.acme.test/jobs/9000002"
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, json=payload))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "partial"
    assert len(snapshot.postings) == 3
    assert snapshot.error is not None and "unusable job_path" in snapshot.error
    assert snapshot.board_enumerated == 5  # both rows were LISTED; only the parse dropped them


# ---------------------------------------------------------------------------------------
# Coverage instrumentation.
# ---------------------------------------------------------------------------------------


@respx.mock
def test_board_reported_total_comes_from_hits(tmp_path: Path) -> None:
    respx.get(BOARD_URL).mock(
        return_value=httpx.Response(200, content=_fixture_bytes("normal.json"))
    )
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.board_reported_total == 5
    assert snapshot.board_enumerated == 5
    assert snapshot.board_total_censored is False
    assert snapshot.detail_deferred == 0  # there is no detail endpoint; never None


@respx.mock
def test_hits_at_the_cap_is_a_censored_total_and_never_a_count(tmp_path: Path) -> None:
    """`hits` is CAPPED at 10000, so at the cap it means ">= 10000" and the board has refused to
    state its size. Persisting 10000 as the total would make "holds 10,000" and "holds at least
    10,000" the same row -- the pair (NULL total, censored=1) is what tells them apart."""
    respx.get(BOARD_URL).mock(
        return_value=httpx.Response(200, content=_envelope(_fixture_json("normal.json")["jobs"], 10000))
    )
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.board_total_censored is True
    assert snapshot.board_reported_total is None
    assert snapshot.board_enumerated == 5


@respx.mock
def test_a_board_stating_no_hits_reports_none(tmp_path: Path) -> None:
    """None is a CLAIM that the board stated nothing; backfilling the row count would make
    coverage 100% by arithmetic, forever. `censored` is None too -- with no total there is
    nothing to have censored."""
    payload = _fixture_json("normal.json")
    del payload["hits"]
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, json=payload))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.board_reported_total is None
    assert snapshot.board_total_censored is None
    assert snapshot.board_enumerated == 5


@respx.mock
def test_board_enumerated_counts_listed_ids_not_surviving_postings(tmp_path: Path) -> None:
    """`board_enumerated` means DISTINCT POSTING IDS LISTED, counted BEFORE a per-row parse
    failure drops one (core/models.py) -- and here, across ALL pages. Counting survivors makes
    it a parse-failure count, and one persisted column then means two things."""
    rows = _clone_rows(100, 5000000)
    del rows[0]["title"]  # a row that will fail to parse
    rows[1].pop("id_icims")  # a row that cannot be keyed at all
    respx.get(_page_url(0)).mock(return_value=httpx.Response(200, content=_envelope(rows, 102)))
    respx.get(_page_url(100)).mock(
        return_value=httpx.Response(200, content=_envelope(_clone_rows(2, 5000100), 102))
    )
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "partial"
    assert len(snapshot.postings) == 100  # 102 listed, minus the untitled and the unkeyed row
    assert snapshot.board_enumerated == 101  # the unkeyed row cannot be counted; the other can
    assert snapshot.board_reported_total == 102


# ---------------------------------------------------------------------------------------
# Pagination.
# ---------------------------------------------------------------------------------------


@respx.mock
def test_pages_until_a_short_page(tmp_path: Path) -> None:
    """`result_limit` is pinned at 100 and `offset` steps by 100, so a 103-posting category is
    offset 0 (full) + offset 100 (short) and MUST NOT stop at the first page."""
    page0 = respx.get(_page_url(0)).mock(
        return_value=httpx.Response(200, content=_envelope(_clone_rows(100, 2000000), 103))
    )
    page1 = respx.get(_page_url(100)).mock(
        return_value=httpx.Response(200, content=_envelope(_clone_rows(3, 2000100), 103))
    )
    page2 = respx.get(_page_url(200)).mock(
        return_value=httpx.Response(200, content=_envelope(_clone_rows(3, 2000200), 103))
    )
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "complete"
    assert len(snapshot.postings) == 103
    assert snapshot.board_reported_total == 103
    assert snapshot.board_enumerated == 103
    assert (page0.call_count, page1.call_count, page2.call_count) == (1, 1, 0)


@respx.mock
def test_an_empty_page_terminates_without_a_further_request(tmp_path: Path) -> None:
    """Past the end of a category the API answers 200 with `"jobs": []`, `error: null` and a
    still-correct `hits` -- measured; it neither errors nor wraps to offset 0."""
    page0 = respx.get(_page_url(0)).mock(
        return_value=httpx.Response(200, content=_envelope(_clone_rows(100, 3000000), 100))
    )
    page1 = respx.get(_page_url(100)).mock(
        return_value=httpx.Response(200, content=_envelope([], 100))
    )
    page2 = respx.get(_page_url(200)).mock(
        return_value=httpx.Response(200, content=_envelope([], 100))
    )
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "complete"
    assert len(snapshot.postings) == 100
    assert (page0.call_count, page1.call_count, page2.call_count) == (1, 1, 0)


@respx.mock
def test_a_row_re_served_by_the_shifting_sort_is_kept_once(tmp_path: Path) -> None:
    """`sort=recent` is not a stable snapshot: a posting landing mid-walk shifts every later
    page by one, so the last row of one page reappears as the first of the next."""
    rows = _clone_rows(100, 6000000)
    respx.get(_page_url(0)).mock(return_value=httpx.Response(200, content=_envelope(rows, 101)))
    respx.get(_page_url(100)).mock(
        return_value=httpx.Response(200, content=_envelope(rows[-1:], 101))
    )
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "complete"
    assert len(snapshot.postings) == 100
    assert snapshot.board_enumerated == 100


@respx.mock
def test_a_full_page_holding_an_unreadable_entry_still_pages_on(tmp_path: Path) -> None:
    """Termination is counted off the RAW `jobs` array, not off the readable rows. An entry we
    cannot key still occupied a slot on the page, so filtering before the comparison reads a
    FULL page as a short one and stops the walk with the rest of the category unread."""
    rows: list[Any] = list(_clone_rows(99, 8000000))
    rows.append(None)  # a 100th entry that is not an object
    page0 = respx.get(_page_url(0)).mock(
        return_value=httpx.Response(200, content=_envelope(rows, 102))
    )
    page1 = respx.get(_page_url(100)).mock(
        return_value=httpx.Response(200, content=_envelope(_clone_rows(2, 8000100), 102))
    )
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert (page0.call_count, page1.call_count) == (1, 1)
    assert len(snapshot.postings) == 101
    assert snapshot.status == "partial"
    assert snapshot.error is not None and "dropped 1 entries" in snapshot.error


@respx.mock
def test_a_failing_later_page_is_partial_not_failed(tmp_path: Path) -> None:
    respx.get(_page_url(0)).mock(
        return_value=httpx.Response(200, content=_envelope(_clone_rows(100, 4000000), 150))
    )
    respx.get(_page_url(100)).mock(return_value=httpx.Response(500))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "partial"
    assert len(snapshot.postings) == 100
    assert snapshot.error is not None and "offset 100" in snapshot.error


# ---------------------------------------------------------------------------------------
# `error` is the failure signal, because every refusal is an HTTP 200.
# ---------------------------------------------------------------------------------------


@respx.mock
def test_a_stated_error_on_the_first_page_is_failed_and_keeps_the_message(
    tmp_path: Path,
) -> None:
    """HTTP 200 with `error` set and `jobs: null`. `error` must be read BEFORE `jobs`: reading
    `jobs` first reports "invalid payload" and throws away the only sentence the server said."""
    respx.get(BOARD_URL).mock(
        return_value=httpx.Response(200, content=_fixture_bytes("error_result_limit.json"))
    )
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "failed"
    assert snapshot.postings == []
    assert snapshot.error is not None
    assert "Result limit cannot be greater than 100" in snapshot.error


@respx.mock
def test_the_offset_ceiling_error_on_a_later_page_is_partial_not_a_failure(
    tmp_path: Path,
) -> None:
    """The server refuses `offset >= 10000` with an HTTP 200 `error`. `_MAX_PAGES` is set so
    that offset can never be requested, but if the ceiling were ever lowered the walk must keep
    what it already read: a partial listing, not a `failed` board and not an empty `complete`
    one. Classified by WHICH PAGE refused, never by matching the message text."""
    respx.get(_page_url(0)).mock(
        return_value=httpx.Response(200, content=_envelope(_clone_rows(100, 7000000), 250))
    )
    respx.get(_page_url(100)).mock(
        return_value=httpx.Response(200, content=_fixture_bytes("error_offset_ceiling.json"))
    )
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "partial"
    assert len(snapshot.postings) == 100
    assert snapshot.error is not None
    assert "Cannot return more than 10000 results at once" in snapshot.error
    assert snapshot.board_reported_total == 250


def test_the_page_cap_is_the_servers_own_offset_ceiling() -> None:
    """A backstop that is ALSO the server's hard limit: 100 pages x 100 rows = 10,000, and
    `offset=10000` is refused. Raising `_MAX_PAGES` walks into that refusal rather than reading
    more, which is why this arithmetic is asserted rather than left in a comment."""
    from boardwatch.providers.amazon import _HITS_CENSOR, _MAX_PAGES, _PAGE_LIMIT

    assert _MAX_PAGES * _PAGE_LIMIT == _HITS_CENSOR == 10000


@respx.mock
def test_an_empty_board_is_complete_empty(tmp_path: Path) -> None:
    respx.get(BOARD_URL).mock(
        return_value=httpx.Response(200, content=_fixture_bytes("empty.json"))
    )
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "complete"
    assert snapshot.postings == []
    assert snapshot.board_reported_total == 0
    assert snapshot.board_enumerated == 0
    assert snapshot.board_total_censored is False


@respx.mock
def test_a_non_object_jobs_entry_is_counted_and_reported(tmp_path: Path) -> None:
    payload = _fixture_json("normal.json")
    payload["jobs"].extend([None, "not a job"])
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, json=payload))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "partial"
    assert snapshot.error is not None and "dropped 2 entries" in snapshot.error
    assert len(snapshot.postings) == 5
    assert snapshot.board_enumerated == 5


@respx.mock
def test_per_job_parse_error_produces_partial(tmp_path: Path) -> None:
    payload = _fixture_json("normal.json")
    del payload["jobs"][0]["title"]
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, json=payload))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "partial"
    assert len(snapshot.postings) == 4
    assert snapshot.error is not None and "empty title" in snapshot.error


@respx.mock
def test_all_rows_failing_is_failed_not_partial(tmp_path: Path) -> None:
    payload = _fixture_json("normal.json")
    for job in payload["jobs"]:
        del job["title"]
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, json=payload))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "failed"
    assert snapshot.postings == []
    assert snapshot.error is not None and "all 5 jobs failed to parse" in snapshot.error


@respx.mock
def test_dead_maps_to_failed(tmp_path: Path) -> None:
    """The measured dead signature: HTTP 404, `Content-Type: text/html`, ZERO-BYTE body. There is
    no `dead.json` fixture because there is no body to record."""
    respx.get(BOARD_URL).mock(
        return_value=httpx.Response(404, content=b"", headers={"content-type": "text/html"})
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
def test_an_html_body_on_a_200_is_failed(tmp_path: Path) -> None:
    respx.get(BOARD_URL).mock(
        return_value=httpx.Response(200, content=b"<!DOCTYPE html><html></html>")
    )
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "failed"
    assert snapshot.error is not None and "invalid board payload" in snapshot.error


@respx.mock
def test_304_maps_to_unchanged(tmp_path: Path) -> None:
    headers = _fixture_json("normal_response_headers.json")
    assert headers["last_modified"] is None  # the live host sends a weak ETag and no Last-Modified
    route = respx.get(BOARD_URL).mock(return_value=httpx.Response(304))
    snapshot = provider.fetch_board(
        _fetcher(tmp_path), _request(ResponseValidators(etag=headers["etag"]))
    )
    assert route.calls[0].request.headers["If-None-Match"] == headers["etag"]
    assert snapshot.status == "unchanged"
    assert snapshot.postings == []


# ---------------------------------------------------------------------------------------
# Healthcheck.
# ---------------------------------------------------------------------------------------


@respx.mock
@pytest.mark.parametrize(
    ("fixture", "status_code", "expected"),
    [
        ("normal.json", 200, BoardHealth.OK),
        ("empty.json", 200, BoardHealth.EMPTY),
        ("error_result_limit.json", 200, BoardHealth.ERROR),
        (None, 404, BoardHealth.DEAD),
        (None, 500, BoardHealth.ERROR),
    ],
)
def test_healthcheck_mapping(
    tmp_path: Path, fixture: str | None, status_code: int, expected: BoardHealth
) -> None:
    content = _fixture_bytes(fixture) if fixture else b""
    respx.get(HEALTH_URL).mock(return_value=httpx.Response(status_code, content=content))
    assert provider.healthcheck(_fetcher(tmp_path), SLUG) == expected


@respx.mock
def test_healthcheck_non_json_is_error(tmp_path: Path) -> None:
    respx.get(HEALTH_URL).mock(
        return_value=httpx.Response(200, content=b"<!DOCTYPE html><html></html>")
    )
    assert provider.healthcheck(_fetcher(tmp_path), SLUG) == BoardHealth.ERROR


@respx.mock
def test_healthcheck_transport_failure_is_unreachable(tmp_path: Path) -> None:
    respx.get(HEALTH_URL).mock(side_effect=httpx.ConnectError("boom"))
    assert provider.healthcheck(_fetcher(tmp_path), SLUG) == BoardHealth.UNREACHABLE


@respx.mock
def test_healthcheck_refuses_an_out_of_catalog_slug_without_a_request(tmp_path: Path) -> None:
    route = respx.get(url__startswith=SEARCH).mock(return_value=httpx.Response(200))
    assert provider.healthcheck(_fetcher(tmp_path), "totally-made-up") == BoardHealth.ERROR
    assert route.call_count == 0
