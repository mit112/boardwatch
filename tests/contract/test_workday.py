"""Workday contract tests. Workday is the FIRST provider with a composite slug
(host/tenant/site), the first that needs POST, and the first with a hard server-side
pagination cap. Every trap asserted here was measured live on 2026-08-04 — see
tests/fixtures/workday/README.md."""

from __future__ import annotations

import json
from datetime import datetime
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
from boardwatch.providers.workday import (
    WorkdayProvider,
    _posting_id,
    parse_posting,
    split_slug,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "workday"
SLUG = "acme.wd5.myworkdayjobs.com/acme/AcmeCareers"
LIST_URL = "https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/AcmeCareers/jobs"

provider = WorkdayProvider()


def _fx(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


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
        provider="workday", slug=SLUG, url=LIST_URL,
        known_posting_ids=known, detail_budget=budget, validators=validators,
    )


def _detail_url(external_path: str) -> str:
    return f"https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/AcmeCareers{external_path}"


def _all_listed_ids(*fixtures: str) -> frozenset[str]:
    """Every posting id across these list fixtures. Passed as `known`, it isolates the
    LISTING phase: nothing is unseen, so no detail is fetched and no detail-budget error is
    raised, and `status == "complete"` still means "the pager reported no problem"."""
    return frozenset(
        _posting_id(str(row["externalPath"]))
        for name in fixtures
        for row in _fx(name)["jobPostings"]
    )


# ---------------------------------------------------------------- slug contract

def test_board_url_is_the_cxs_search_endpoint() -> None:
    assert provider.board_url(SLUG) == LIST_URL


def test_normalize_lowercases_host_and_tenant_but_preserves_site_case() -> None:
    # site slugs ARE case-sensitive live: NVIDIAExternalCareerSite, External_Career_Site
    # and external_experienced are all real
    assert (
        WorkdayProvider.normalize_slug("ACME.WD5.MyWorkdayJobs.com/ACME/AcmeCareers")
        == "acme.wd5.myworkdayjobs.com/acme/AcmeCareers"
    )


def test_normalize_is_idempotent() -> None:
    once = WorkdayProvider.normalize_slug(SLUG)
    assert WorkdayProvider.normalize_slug(once) == once


@pytest.mark.parametrize(
    "bad",
    [
        "acme.wd5.myworkdayjobs.com/acme",             # two segments
        "acme.wd5.myworkdayjobs.com/acme/a/b",         # four segments
        "acme.wd5.myworkdayjobs.com//AcmeCareers",     # empty tenant
        "notmyworkdayjobs.com/acme/AcmeCareers",       # lookalike domain
        ".myworkdayjobs.com/acme/AcmeCareers",         # no tenant label before the suffix
        "@acme.wd5.myworkdayjobs.com/acme/Careers",        # userinfo injection, empty userinfo
        "acme.wd5.myworkdayjobs.com@/acme/Careers",        # userinfo injection, trailing @
        "acme.wd5.myworkdayjobs.com:8080/acme/Careers",   # port / scheme injection
        "acme.wd5.myworkdayjobs.com?x=1/acme/Careers",    # query injection
        "acme.wd5.myworkdayjobs.com#f/acme/Careers",      # fragment injection
        "acme wd5.myworkdayjobs.com/acme/Careers",        # whitespace in host
        "acme.wd5.myworkdayjobs.com/ac\tme/Careers",      # control character
    ],
)
def test_malformed_slug_is_rejected(bad: str) -> None:
    with pytest.raises(ValueError):
        split_slug(bad)


def test_userinfo_in_the_host_is_rejected_for_the_at_sign_not_the_suffix() -> None:
    # a lookalike host would also raise, but for a DIFFERENT reason; pin the real one
    with pytest.raises(ValueError, match="forbidden character"):
        split_slug("@acme.wd5.myworkdayjobs.com/acme/Careers")


def test_malformed_slug_surfaces_unknown_board_url_not_value_error() -> None:
    # a bare ValueError escapes companies_cmd.py:74's except UnknownBoardURL and tracebacks
    with pytest.raises(UnknownBoardURL, match="invalid workday board target"):
        parse_board_target("workday:not-a-triple")


def test_qualified_form_round_trips() -> None:
    assert parse_board_target(f"workday:{SLUG}") == ("workday", SLUG)


@pytest.mark.parametrize(
    ("pasted", "expected_site"),
    [
        ("https://acme.wd5.myworkdayjobs.com/AcmeCareers", "AcmeCareers"),
        ("https://acme.wd5.myworkdayjobs.com/en-US/AcmeCareers", "AcmeCareers"),
        ("https://acme.wd5.myworkdayjobs.com/en-US/AcmeCareers/job/Remote/Eng_JR1", "AcmeCareers"),
        ("acme.wd5.myworkdayjobs.com/AcmeCareers?utm=x", "AcmeCareers"),
    ],
)
def test_pasted_career_site_urls_resolve(pasted: str, expected_site: str) -> None:
    assert parse_board_target(pasted) == (
        "workday",
        f"acme.wd5.myworkdayjobs.com/acme/{expected_site}",
    )


def test_bare_host_paste_surfaces_slug_help() -> None:
    with pytest.raises(UnknownBoardURL, match="career-site path"):
        parse_board_target("https://acme.wd5.myworkdayjobs.com")


# ---------------------------------------------------------------- single-page board

@respx.mock
def test_single_page_board_parses_every_posting(tmp_path: Path) -> None:
    respx.post(LIST_URL).mock(return_value=httpx.Response(200, json=_fx("list_normal.json")))
    _mock_all_details()
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "complete"
    assert len(snapshot.postings) == 3
    assert len(snapshot.listed_ids) == 3
    assert snapshot.listed_ids == {"JR1000001-1", "JR1000002", "JR1000003"}


@respx.mock
def test_a_row_with_no_title_is_partial_not_an_exception(tmp_path: Path) -> None:
    payload = _fx("list_normal.json")
    untitled = {"externalPath": "/job/Nowhere/Untitled_JR1000009", "locationsText": "Remote"}
    payload["jobPostings"].append(untitled)
    respx.post(LIST_URL).mock(return_value=httpx.Response(200, json=payload))
    _mock_all_details()
    # its detail carries no title either, so parse_posting still raises — inside the detail
    # loop, which is where the per-row try/except now lives
    respx.get(_detail_url(untitled["externalPath"])).mock(
        return_value=httpx.Response(200, json={"jobPostingInfo": {}})
    )
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "partial"
    assert "empty title" in (snapshot.error or "")
    assert len(snapshot.postings) == 3          # the three good rows still applied
    # a row that FAILS TO PARSE still belongs to the live inventory, or _process_missing
    # closes a posting that is demonstrably still listed
    assert len(snapshot.listed_ids) == 4


@respx.mock
def test_every_request_body_pins_limit_20(tmp_path: Path) -> None:
    # limit=21 returns HTTP 400 live — this is a hard server cap, not a preference
    route = respx.post(LIST_URL).mock(
        return_value=httpx.Response(200, json=_fx("list_normal.json"))
    )
    provider.fetch_board(_fetcher(tmp_path), _request(budget=0))
    for call in route.calls:
        assert json.loads(call.request.content)["limit"] == 20


@respx.mock
def test_no_validators_are_observed(tmp_path: Path) -> None:
    # the live CXS POST sends no ETag and no Last-Modified (cache-control: no-store)
    respx.post(LIST_URL).mock(return_value=httpx.Response(200, json=_fx("list_normal.json")))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request(budget=0))
    assert snapshot.observed_validators is None


@respx.mock
def test_mocked_304_maps_to_unchanged(tmp_path: Path) -> None:
    # unreachable against the live service (no validators are ever served) but the branch
    # exists for symmetry with every other provider, so it is exercised deliberately
    respx.post(LIST_URL).mock(return_value=httpx.Response(304))
    snapshot = provider.fetch_board(
        _fetcher(tmp_path), _request(validators=ResponseValidators(etag='W/"x"'))
    )
    assert snapshot.status == "unchanged"
    assert snapshot.postings == []


@respx.mock
def test_malformed_slug_fails_the_board_not_the_scan(tmp_path: Path) -> None:
    request = BoardRequest(provider="workday", slug="garbage", url=LIST_URL)
    snapshot = provider.fetch_board(_fetcher(tmp_path), request)
    assert snapshot.status == "failed"
    assert "invalid workday slug" in (snapshot.error or "")


@respx.mock
def test_non_json_maintenance_body_fails_cleanly(tmp_path: Path) -> None:
    # Walmart serves exactly this live: a 200 with an HTML maintenance page
    respx.post(LIST_URL).mock(
        return_value=httpx.Response(200, content=b"<html><body>Scheduled maintenance</body></html>")
    )
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "failed"
    assert "invalid board payload" in (snapshot.error or "")


# ---------------------------------------------------------------- healthcheck

@respx.mock
def test_healthcheck_ok(tmp_path: Path) -> None:
    respx.post(LIST_URL).mock(return_value=httpx.Response(200, json=_fx("list_normal.json")))
    assert provider.healthcheck(_fetcher(tmp_path), SLUG) is BoardHealth.OK


@respx.mock
def test_healthcheck_empty_board(tmp_path: Path) -> None:
    respx.post(LIST_URL).mock(return_value=httpx.Response(200, json=_fx("list_empty.json")))
    assert provider.healthcheck(_fetcher(tmp_path), SLUG) is BoardHealth.EMPTY


@respx.mock
def test_healthcheck_wrong_site_slug_is_dead(tmp_path: Path) -> None:
    respx.post(LIST_URL).mock(return_value=httpx.Response(404, json=_fx("dead_s21.json")))
    assert provider.healthcheck(_fetcher(tmp_path), SLUG) is BoardHealth.DEAD


@respx.mock
@pytest.mark.parametrize("status", [401, 403, 410])
def test_healthcheck_gated_or_retired_tenant_is_dead(tmp_path: Path, status: int) -> None:
    respx.post(LIST_URL).mock(return_value=httpx.Response(status))
    assert provider.healthcheck(_fetcher(tmp_path), SLUG) is BoardHealth.DEAD


@respx.mock
def test_healthcheck_422_is_error(tmp_path: Path) -> None:
    respx.post(LIST_URL).mock(return_value=httpx.Response(422))
    assert provider.healthcheck(_fetcher(tmp_path), SLUG) is BoardHealth.ERROR


@respx.mock
def test_healthcheck_transport_failure_is_unreachable(tmp_path: Path) -> None:
    respx.post(LIST_URL).mock(side_effect=httpx.ConnectError("no route"))
    assert provider.healthcheck(_fetcher(tmp_path), SLUG) is BoardHealth.UNREACHABLE


def test_healthcheck_malformed_slug_is_error(tmp_path: Path) -> None:
    assert provider.healthcheck(_fetcher(tmp_path), "garbage") is BoardHealth.ERROR


# ------------------------------------------------- additional branch coverage (Task 5)
# These close branches the literal Step-1 test file above does not reach on its own, so
# this module (the largest provider in the repo) does not quietly drag down the global
# coverage floor. None of these reach into Tasks 6-8 scope (pagination, bounded detail
# fetches, facet capture): fetch_board here is still exactly one POST at offset 0.


def test_slug_from_path_skips_a_leading_chrome_segment() -> None:
    # "job" precedes the real site segment in some pasted URLs; it must not be mistaken
    # for the site itself (distinct from the locale-segment case already covered above)
    assert (
        WorkdayProvider.slug_from_path("acme.wd5.myworkdayjobs.com", ["job", "AcmeCareers"])
        == "acme.wd5.myworkdayjobs.com/acme/AcmeCareers"
    )


def test_slug_from_path_returns_none_when_every_segment_is_chrome() -> None:
    assert WorkdayProvider.slug_from_path("acme.wd5.myworkdayjobs.com", ["wday", "cxs"]) is None


@respx.mock
def test_fetch_board_transport_failure_is_a_failed_snapshot(tmp_path: Path) -> None:
    respx.post(LIST_URL).mock(side_effect=httpx.ConnectError("no route"))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "failed"


@respx.mock
def test_healthcheck_malformed_200_payload_is_error(tmp_path: Path) -> None:
    respx.post(LIST_URL).mock(return_value=httpx.Response(200, content=b"not json"))
    assert provider.healthcheck(_fetcher(tmp_path), SLUG) is BoardHealth.ERROR


@respx.mock
def test_duplicate_external_path_rows_are_deduped(tmp_path: Path) -> None:
    dup_row = {
        "title": "Senior Platform Engineer",
        "externalPath": "/job/Remote-USA/Senior-Platform-Engineer_JR1000001-1",
        "locationsText": "Remote, USA",
    }
    body = {"total": 2, "jobPostings": [dup_row, dict(dup_row)], "facets": []}
    respx.post(LIST_URL).mock(return_value=httpx.Response(200, json=body))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request(budget=0))
    assert snapshot.listed_ids == {"JR1000001-1"}


def test_parse_posting_raises_on_missing_external_path() -> None:
    with pytest.raises(ValueError, match="externalPath"):
        parse_posting("acme.wd5.myworkdayjobs.com", "AcmeCareers", {}, None, None)


def test_parse_posting_raises_on_empty_title() -> None:
    listed = {"externalPath": "/job/x/Role_JR1", "title": ""}
    with pytest.raises(ValueError, match="empty title"):
        parse_posting("acme.wd5.myworkdayjobs.com", "AcmeCareers", listed, None, None)


def test_parse_posting_captures_detail_and_worker_subtype() -> None:
    # the CAPTURE contract at the parse_posting seam, in isolation: raw_json["detail"],
    # ["timeType"] and ["workerSubType"] are populated from arguments handed straight in.
    # The fetch_board wiring that produces those arguments is covered end-to-end by
    # test_detail_fetch_fills_body_text_and_captures_time_type and
    # test_intern_bucket_is_queried_and_stamped_on_raw_json.
    listed = _fx("list_normal.json")["jobPostings"][0]
    detail = _fx("detail_normal.json")
    posting = parse_posting(
        "acme.wd5.myworkdayjobs.com", "AcmeCareers", listed, detail, "Regular Employee"
    )
    assert posting.raw_json["detail"] == detail
    assert posting.raw_json["timeType"] == "Full time"
    assert posting.raw_json["workerSubType"] == "Regular Employee"
    assert posting.remote_policy == "remote"  # detail's remoteType: "Fully Remote" wins
    assert posting.posted_at is not None


@pytest.mark.parametrize(
    ("remote_type", "expected"),
    [
        ("On-site", "onsite"),
        ("Onsite", "onsite"),
    ],
)
def test_remote_policy_onsite_branch(remote_type: str, expected: str) -> None:
    listed = {
        "externalPath": "/job/x/Role_JR1",
        "title": "Role",
        "remoteType": remote_type,
    }
    posting = parse_posting("acme.wd5.myworkdayjobs.com", "AcmeCareers", listed, None, None)
    assert posting.remote_policy == expected


def test_posted_at_is_none_for_an_unparseable_start_date() -> None:
    listed = {"externalPath": "/job/x/Role_JR1", "title": "Role"}
    detail = {"jobPostingInfo": {"startDate": "not-a-date"}}
    posting = parse_posting("acme.wd5.myworkdayjobs.com", "AcmeCareers", listed, detail, None)
    assert posting.posted_at is None


def test_remote_policy_falls_back_to_location_text_for_an_unrecognized_remote_type() -> None:
    # a remoteType value that matches none of the three known buckets (a live tenant could
    # add a new one) must not raise; it falls through to the location-text heuristic
    listed = {
        "externalPath": "/job/x/Role_JR1",
        "title": "Role",
        "locationsText": "Remote, USA",
        "remoteType": "Flexible",
    }
    posting = parse_posting("acme.wd5.myworkdayjobs.com", "AcmeCareers", listed, None, None)
    assert posting.remote_policy == "remote"


def test_posted_at_handles_a_timezone_aware_timestamp() -> None:
    # the ARITHMETIC is the point: 10:00+05:00 is 05:00Z, and posted_at is naive UTC. An
    # inverted conversion (15:00) or a dropped tzinfo (10:00) both survive `is not None`.
    listed = {"externalPath": "/job/x/Role_JR1", "title": "Role"}
    detail = {"jobPostingInfo": {"startDate": "2026-08-04T10:00:00+05:00"}}
    posting = parse_posting("acme.wd5.myworkdayjobs.com", "AcmeCareers", listed, detail, None)
    assert posting.posted_at == datetime(2026, 8, 4, 5, 0)
    assert posting.posted_at is not None and posting.posted_at.tzinfo is None


# ---------------------------------------------------------------- pagination

@respx.mock
def test_pages_until_a_short_page(tmp_path: Path) -> None:
    respx.post(LIST_URL).mock(
        side_effect=[
            httpx.Response(200, json=_fx("list_page_full.json")),   # 20 rows -> keep going
            httpx.Response(200, json=_fx("list_page_short.json")),  # 5 rows  -> stop
        ]
    )
    known = _all_listed_ids("list_page_full.json", "list_page_short.json")
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request(known=known))
    assert snapshot.status == "complete"
    assert len(snapshot.listed_ids) == 25


@respx.mock
def test_offsets_advance_by_the_page_limit(tmp_path: Path) -> None:
    route = respx.post(LIST_URL).mock(
        side_effect=[
            httpx.Response(200, json=_fx("list_page_full.json")),
            httpx.Response(200, json=_fx("list_page_short.json")),
        ]
    )
    provider.fetch_board(_fetcher(tmp_path), _request(budget=0))
    assert [json.loads(c.request.content)["offset"] for c in route.calls] == [0, 20]


@respx.mock
def test_total_over_the_page_supply_does_not_loop(tmp_path: Path) -> None:
    # THE 2000-CAP / OFFSET-WRAP TRAP. list_page_full.json reports total=2000 while
    # supplying 20 rows; live, offset >= 2000 wraps to page 1 byte-identically, so
    # `while offset < total` never terminates. Termination MUST be on a short page.
    route = respx.post(LIST_URL).mock(
        side_effect=[
            httpx.Response(200, json=_fx("list_page_full.json")),
            httpx.Response(200, json=_fx("list_page_short.json")),
        ]
    )
    known = _all_listed_ids("list_page_full.json", "list_page_short.json")
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request(known=known))
    assert route.call_count == 2
    assert snapshot.status == "complete"


@respx.mock
def test_page_cap_bounds_a_server_that_never_returns_a_short_page(tmp_path: Path) -> None:
    full = _fx("list_page_full.json")
    respx.post(LIST_URL).mock(return_value=httpx.Response(200, json=full))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request(budget=0))
    assert snapshot.status == "partial"
    assert "page cap" in (snapshot.error or "")


@respx.mock
def test_total_and_facets_are_read_from_offset_zero_only(tmp_path: Path) -> None:
    # live, offset=20 answers total=0 and facets=[]; re-reading them per page would make the
    # board look empty after page 1
    page_two = _fx("list_page_short.json") | {"total": 0, "facets": []}
    respx.post(LIST_URL).mock(
        side_effect=[
            httpx.Response(200, json=_fx("list_page_full.json")),
            httpx.Response(200, json=page_two),
        ]
    )
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request(budget=0))
    assert len(snapshot.listed_ids) == 25  # page 2's total=0 did not truncate the listing


@respx.mock
def test_a_failed_later_page_is_partial_not_failed(tmp_path: Path) -> None:
    respx.post(LIST_URL).mock(
        side_effect=[
            httpx.Response(200, json=_fx("list_page_full.json")),
            httpx.Response(500),
        ]
    )
    # `known` (not budget=0) isolates the page-2 failure: with nothing unseen, the
    # detail-budget branch cannot also force `partial` and mask a deleted error append.
    snapshot = provider.fetch_board(
        _fetcher(tmp_path), _request(known=_all_listed_ids("list_page_full.json"))
    )
    assert snapshot.status == "partial"
    assert "page at offset 20" in (snapshot.error or "")
    assert len(snapshot.listed_ids) == 20


@respx.mock
def test_duplicate_external_paths_are_deduped(tmp_path: Path) -> None:
    full = _fx("list_page_full.json")
    repeat = {"total": 2000, "jobPostings": full["jobPostings"][:5], "facets": []}
    respx.post(LIST_URL).mock(
        side_effect=[
            httpx.Response(200, json=full),
            httpx.Response(200, json=repeat),
        ]
    )
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request(budget=0))
    assert len(snapshot.listed_ids) == 20  # the 5 repeats collapsed


@respx.mock
def test_rows_with_no_external_path_force_partial_instead_of_shrinking_silently(
    tmp_path: Path,
) -> None:
    # THE SILENT-SHRINK GUARD. `complete` is the status that authorizes apply_board to close
    # everything missing from listed_ids, so a schema change that renames externalPath must
    # not yield `complete` with an empty inventory — at CLOSE_AFTER_MISSES the whole board's
    # open inventory would close. Dropped rows must be observable in `errors`.
    rows = [dict(row) for row in _fx("list_normal.json")["jobPostings"]]
    for row in rows:
        row.pop("externalPath")
    respx.post(LIST_URL).mock(
        return_value=httpx.Response(200, json={"total": 3, "jobPostings": rows, "facets": []})
    )
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request(budget=0))
    assert snapshot.listed_ids == frozenset()
    assert snapshot.status == "partial"
    assert "no externalPath" in (snapshot.error or "")


@respx.mock
def test_a_malformed_later_page_is_partial_not_failed(tmp_path: Path) -> None:
    # page 2 is valid JSON but not a usable page (jobPostings is not a list); only the
    # FIRST page's malformed-payload case is a hard failure
    respx.post(LIST_URL).mock(
        side_effect=[
            httpx.Response(200, json=_fx("list_page_full.json")),
            httpx.Response(200, json={"jobPostings": "oops"}),
        ]
    )
    # `known` (not budget=0) isolates the malformed page: see the sibling test above.
    snapshot = provider.fetch_board(
        _fetcher(tmp_path), _request(known=_all_listed_ids("list_page_full.json"))
    )
    assert snapshot.status == "partial"
    assert "page at offset 20: invalid payload" in (snapshot.error or "")
    assert len(snapshot.listed_ids) == 20


@respx.mock
def test_a_missing_total_on_the_first_page_does_not_fail(tmp_path: Path) -> None:
    # total is informational only; if the first page omits it entirely, fetch_board must
    # still succeed rather than raising on the int(...) conversion
    payload = dict(_fx("list_normal.json"))
    del payload["total"]
    respx.post(LIST_URL).mock(return_value=httpx.Response(200, json=payload))
    snapshot = provider.fetch_board(
        _fetcher(tmp_path), _request(known=_all_listed_ids("list_normal.json"))
    )
    assert snapshot.status == "complete"
    assert len(snapshot.listed_ids) == 3


# ---------------------------------------------------------------- detail fetches

def _mock_all_details() -> None:
    base = _fx("detail_normal.json")
    for row in _fx("list_normal.json")["jobPostings"]:
        info = dict(base["jobPostingInfo"])
        info["title"] = row["title"]
        info["location"] = row["locationsText"]
        respx.get(_detail_url(row["externalPath"])).mock(
            return_value=httpx.Response(200, json={"jobPostingInfo": info})
        )


@respx.mock
def test_detail_fetch_fills_body_text_and_captures_time_type(tmp_path: Path) -> None:
    respx.post(LIST_URL).mock(return_value=httpx.Response(200, json=_fx("list_normal.json")))
    _mock_all_details()
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert len(snapshot.postings) == 3
    assert all(p.body_text for p in snapshot.postings)
    assert all("Own a service end to end" in p.body_text for p in snapshot.postings)
    # timeType is captured because backfilling it means re-scanning every Workday board.
    # It is NOT an intern signal: it reads "Full time" on a real PhD-intern requisition.
    assert all(p.raw_json["timeType"] == "Full time" for p in snapshot.postings)


@respx.mock
def test_known_postings_are_not_refetched_but_stay_in_the_inventory(tmp_path: Path) -> None:
    respx.post(LIST_URL).mock(return_value=httpx.Response(200, json=_fx("list_normal.json")))
    _mock_all_details()
    snapshot = provider.fetch_board(
        _fetcher(tmp_path), _request(known=frozenset({"JR1000001-1", "JR1000002"}))
    )
    assert {p.provider_posting_id for p in snapshot.postings} == {"JR1000003"}
    # the full live inventory, or apply_board would close the two known postings
    assert snapshot.listed_ids == {"JR1000001-1", "JR1000002", "JR1000003"}


@respx.mock
def test_detail_budget_is_respected_and_reported(tmp_path: Path) -> None:
    respx.post(LIST_URL).mock(return_value=httpx.Response(200, json=_fx("list_normal.json")))
    _mock_all_details()
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request(budget=1))
    assert len(snapshot.postings) == 1
    assert snapshot.status == "partial"
    assert "detail budget" in (snapshot.error or "")
    assert len(snapshot.listed_ids) == 3


@respx.mock
def test_one_failed_detail_is_partial(tmp_path: Path) -> None:
    respx.post(LIST_URL).mock(return_value=httpx.Response(200, json=_fx("list_normal.json")))
    _mock_all_details()
    first = _fx("list_normal.json")["jobPostings"][0]["externalPath"]
    respx.get(_detail_url(first)).mock(return_value=httpx.Response(500))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "partial"
    assert len(snapshot.postings) == 2
    assert len(snapshot.listed_ids) == 3  # a failed DETAIL must not shrink the inventory


@respx.mock
def test_a_malformed_detail_payload_is_partial(tmp_path: Path) -> None:
    # the detail endpoint can answer 200 with an HTML maintenance page just as the list POST
    # can (observed on Walmart); that is one bad posting, not a bad board
    respx.post(LIST_URL).mock(return_value=httpx.Response(200, json=_fx("list_normal.json")))
    _mock_all_details()
    first = _fx("list_normal.json")["jobPostings"][0]["externalPath"]
    respx.get(_detail_url(first)).mock(
        return_value=httpx.Response(200, content=b"<html>maintenance</html>")
    )
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "partial"
    assert "malformed payload" in (snapshot.error or "")
    assert len(snapshot.postings) == 2
    assert len(snapshot.listed_ids) == 3


@respx.mock
def test_all_details_failing_fails_the_board(tmp_path: Path) -> None:
    respx.post(LIST_URL).mock(return_value=httpx.Response(200, json=_fx("list_normal.json")))
    for row in _fx("list_normal.json")["jobPostings"]:
        respx.get(_detail_url(row["externalPath"])).mock(return_value=httpx.Response(500))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "failed"


@respx.mock
def test_posted_at_comes_from_start_date_not_posted_on(tmp_path: Path) -> None:
    # postedOn is a human string ("Posted Today") and is never parsed. startDate is the
    # posting date: on a requisition reporting postedOn "Posted Today", startDate equalled
    # the probe date exactly.
    respx.post(LIST_URL).mock(return_value=httpx.Response(200, json=_fx("list_normal.json")))
    _mock_all_details()
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert all(p.posted_at is not None for p in snapshot.postings)
    assert snapshot.postings[0].posted_at.isoformat().startswith("2026-08-04")


@respx.mock
def test_missing_start_date_is_none_not_a_guess(tmp_path: Path) -> None:
    respx.post(LIST_URL).mock(return_value=httpx.Response(200, json=_fx("list_normal.json")))
    info = {k: v for k, v in _fx("detail_normal.json")["jobPostingInfo"].items()
            if k != "startDate"}
    for row in _fx("list_normal.json")["jobPostings"]:
        respx.get(_detail_url(row["externalPath"])).mock(
            return_value=httpx.Response(200, json={"jobPostingInfo": info})
        )
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert all(p.posted_at is None for p in snapshot.postings)


def test_posting_id_prefers_the_requisition_token() -> None:
    from boardwatch.providers.workday import _posting_id

    # the real live shape carries a -N posting-instance suffix on the requisition token
    assert _posting_id("/job/Remote-USA/Senior-Platform-Engineer_JR1000001-1") == "JR1000001-1"
    assert _posting_id("/job/Austin-TX/Staff-Data-Engineer_JR1000003") == "JR1000003"
    # no digit in the final token -> the whole externalPath, which is unique within a board
    assert _posting_id("/job/Remote-USA/Engineer") == "/job/Remote-USA/Engineer"


def test_remote_policy_prefers_the_structured_remote_type() -> None:
    # Workday exposes remoteType on the list row itself; preferring it over substring-matching
    # the location text is the same choice Ashby makes with its isRemote boolean
    from boardwatch.providers.workday import parse_posting

    rows = _fx("list_normal.json")["jobPostings"]
    assert parse_posting("h", "S", rows[0], None, None).remote_policy == "remote"
    # "Partially Remote" is HYBRID, not remote — the location text says "Santa Clara, CA",
    # so a text-only heuristic would have returned "unknown" here
    assert parse_posting("h", "S", rows[1], None, None).remote_policy == "hybrid"


def test_remote_policy_falls_back_to_location_text_without_remote_type() -> None:
    # not every tenant sets remoteType (Etsy does, NVIDIA does not)
    from boardwatch.providers.workday import parse_posting

    rows = _fx("list_normal.json")["jobPostings"]
    assert "remoteType" not in rows[2]
    assert parse_posting("h", "S", rows[2], None, None).remote_policy == "unknown"


# ---------------------------------------------------------------- employment type

def _intern_facet_id() -> str:
    group = next(
        g for g in _fx("list_normal.json")["facets"] if g["facetParameter"] == "workerSubType"
    )
    return next(v["id"] for v in group["values"] if "Intern" in v["descriptor"])


@respx.mock
def test_intern_bucket_is_queried_and_stamped_on_raw_json(tmp_path: Path) -> None:
    route = respx.post(LIST_URL).mock(
        side_effect=[
            httpx.Response(200, json=_fx("list_normal.json")),
            httpx.Response(200, json=_fx("list_facet_intern.json")),
        ]
    )
    _mock_all_details()
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    by_id = {p.provider_posting_id: p for p in snapshot.postings}
    assert by_id["JR1000002"].raw_json["workerSubType"] == "Intern (Fixed Term)"
    assert "workerSubType" not in by_id["JR1000001-1"].raw_json
    # the facet query used the TENANT'S OWN id, read from the facets block
    facet_call = json.loads(route.calls[1].request.content)
    assert facet_call["appliedFacets"] == {"workerSubType": [_intern_facet_id()]}
    assert facet_call["limit"] == 20


@respx.mock
def test_regular_employee_bucket_is_not_queried(tmp_path: Path) -> None:
    # descriptor matching is conservative: only intern/new-grad-shaped buckets are worth a
    # request, and "Regular Employee" (the 2354-count bucket) must never be paged
    route = respx.post(LIST_URL).mock(
        side_effect=[
            httpx.Response(200, json=_fx("list_normal.json")),
            httpx.Response(200, json=_fx("list_facet_intern.json")),
        ]
    )
    _mock_all_details()
    provider.fetch_board(_fetcher(tmp_path), _request())
    assert route.call_count == 2  # the board page + ONE facet query, not two


@respx.mock
def test_no_matching_bucket_costs_no_extra_request(tmp_path: Path) -> None:
    # a tenant with different vocabulary must cost ZERO extra requests
    payload = _fx("list_normal.json")
    for group in payload["facets"]:
        if group["facetParameter"] == "workerSubType":
            group["values"] = [
                {"descriptor": "Regular Employee", "id": "x1", "count": 3},
                {"descriptor": "Management", "id": "x2", "count": 1},
            ]
    route = respx.post(LIST_URL).mock(return_value=httpx.Response(200, json=payload))
    _mock_all_details()
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert route.call_count == 1
    assert all("workerSubType" not in p.raw_json for p in snapshot.postings)


@respx.mock
def test_absent_facets_block_is_not_an_error(tmp_path: Path) -> None:
    payload = {k: v for k, v in _fx("list_normal.json").items() if k != "facets"}
    respx.post(LIST_URL).mock(return_value=httpx.Response(200, json=payload))
    _mock_all_details()
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "complete"


@respx.mock
def test_a_failed_facet_query_is_partial_not_failed(tmp_path: Path) -> None:
    respx.post(LIST_URL).mock(
        side_effect=[
            httpx.Response(200, json=_fx("list_normal.json")),
            httpx.Response(500),
        ]
    )
    _mock_all_details()
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "partial"
    assert len(snapshot.postings) == 3  # the board itself still applied


def test_facet_buckets_are_matched_on_descriptor_never_on_a_hardcoded_wid() -> None:
    from boardwatch.providers.workday import _worker_subtype_buckets

    facets = [
        {
            "facetParameter": "workerSubType",
            "descriptor": "Job Type",
            "values": [
                {"descriptor": "Regular Employee", "id": "a", "count": 2354},
                {"descriptor": "Intern (Fixed Term)", "id": "b", "count": 11},
                {"descriptor": "New College Graduate", "id": "c", "count": 80},
                {"descriptor": "Management", "id": "d", "count": 197},
            ],
        },
        {"facetParameter": "locations", "descriptor": "Location", "values": [
            {"descriptor": "Intern City", "id": "e", "count": 1}
        ]},
    ]
    assert _worker_subtype_buckets(facets) == [
        ("Intern (Fixed Term)", "b"),
        ("New College Graduate", "c"),
    ]


@respx.mock
def test_a_facet_bucket_pages_until_a_short_page(tmp_path: Path) -> None:
    # _FACET_MAX_PAGES exists because a bucket can exceed one page. A FULL facet page must
    # advance the offset and only a SHORT page terminates the bucket — trap 2 applies to the
    # facet-filtered query exactly as it does to the unfiltered board.
    route = respx.post(LIST_URL).mock(
        side_effect=[
            httpx.Response(200, json=_fx("list_normal.json")),
            httpx.Response(200, json=_fx("list_page_full.json")),
            httpx.Response(200, json=_fx("list_page_short.json")),
        ]
    )
    _mock_all_details()
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert route.call_count == 3  # board page + two pages of the ONE intern bucket
    assert [json.loads(c.request.content)["offset"] for c in route.calls] == [0, 0, 20]
    assert snapshot.status == "complete"


@respx.mock
def test_a_malformed_facet_page_is_partial_not_failed(tmp_path: Path) -> None:
    # a facet query can answer 200 with an HTML maintenance page just as the board POST can
    # (observed on Walmart); that costs the workerSubType stamp, never the board
    respx.post(LIST_URL).mock(
        side_effect=[
            httpx.Response(200, json=_fx("list_normal.json")),
            httpx.Response(200, content=b"<html>maintenance</html>"),
        ]
    )
    _mock_all_details()
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "partial"
    assert "invalid payload" in (snapshot.error or "")
    assert len(snapshot.postings) == 3
    assert all("workerSubType" not in p.raw_json for p in snapshot.postings)


@pytest.mark.parametrize(
    "descriptor",
    [
        "Intern", "Intern (Fixed Term)", "Internship", "Interns", "Summer Intern",
        "Co-op", "Coop", "Co-Op Student", "Apprentice", "Apprenticeship", "Trainee",
        "New College Graduate", "New Grad",
    ],
)
def test_a_real_early_career_descriptor_is_matched(descriptor: str) -> None:
    from boardwatch.providers.workday import _worker_subtype_buckets

    facets = [{
        "facetParameter": "workerSubType",
        "values": [{"descriptor": descriptor, "id": "x"}],
    }]
    assert _worker_subtype_buckets(facets) == [(descriptor, "x")]


@pytest.mark.parametrize(
    "descriptor", ["Internal Employee", "International Assignee", "Cooperative Education"]
)
def test_a_lookalike_descriptor_is_not_matched(descriptor: str) -> None:
    # SUBSTRING matching accepted all three: "intern" is inside Internal/International and
    # "coop" is inside Cooperative. Each false positive costs up to _FACET_MAX_PAGES extra
    # POSTs and stamps a bogus workerSubType on up to 400 unrelated postings — which a future
    # intern-detection consumer would read as an intern signal. Note that \bintern\b alone
    # would fix these while REGRESSING on "Internship" (pinned by the sibling test above).
    from boardwatch.providers.workday import _worker_subtype_buckets

    facets = [{
        "facetParameter": "workerSubType",
        "values": [{"descriptor": descriptor, "id": "x"}],
    }]
    assert _worker_subtype_buckets(facets) == []


def test_worker_subtype_buckets_tolerates_a_ragged_facets_block() -> None:
    from boardwatch.providers.workday import _worker_subtype_buckets

    # live payloads are not schema-validated, and this runs before any of them is trusted
    assert _worker_subtype_buckets(["not a dict", 7]) == []
    assert _worker_subtype_buckets([{"facetParameter": "workerSubType", "values": "nope"}]) == []
    # a non-dict value is skipped, and a matching descriptor with no id is unusable
    assert _worker_subtype_buckets(
        [{"facetParameter": "workerSubType", "values": ["nope", {"descriptor": "Intern"}]}]
    ) == []
