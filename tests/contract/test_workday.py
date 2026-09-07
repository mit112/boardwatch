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
    _facet_catalog,
    _facet_sum,
    _posting_id,
    _uncapped_total,
    parse_posting,
    split_slug,
    split_target,
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


def test_a_path_that_opens_with_a_posting_segment_carries_no_career_site() -> None:
    """REPLACES a test that asserted `["job", "AcmeCareers"]` yields site `AcmeCareers`.

    Its stated premise was that "'job' precedes the real site segment in some pasted URLs".
    That shape occurs in **zero of 113,074** real Workday URLs — 93,044 from this store's own
    scans and 4,521 from an independent ledger, plus every board URL in both — and the answer
    it pinned is the Red Hat defect in miniature: the segment after `job` is the LOCATION, so
    returning it invents a board. A path that opens with a posting segment carries no career
    site, and None is the honest answer.
    """
    assert (
        WorkdayProvider.slug_from_path("acme.wd5.myworkdayjobs.com", ["job", "AcmeCareers"])
        is None
    )
    assert (
        WorkdayProvider.slug_from_path("acme.wd5.myworkdayjobs.com", ["details", "X"]) is None
    )


def test_a_career_site_named_like_workday_chrome_is_still_the_career_site() -> None:
    """The live defect this rewrite exists for. `_CHROME_SEGMENTS` contains `jobs`, and the old
    rule skipped any segment in it — so Red Hat, whose career site is literally named `Jobs`,
    had its site skipped and the job's CITY returned instead.

    Both halves are asserted because both were broken and they fail independently: the posting
    URL derived `Canberra` (157 live URLs, one fictional company row per city), and the board
    URL derived None, which is why `redhat/jobs` and `paypal/jobs` — 325 postings, both watched
    — could only be added through the explicit `workday:host/tenant/site` form.

    `store/queries.py:stored_slug` does NOT cover this: it folds CASE, and `canberra` is not a
    case variant of `jobs`. Verified against a real store, not assumed.
    """
    assert (
        WorkdayProvider.slug_from_path(
            "redhat.wd5.myworkdayjobs.com", ["Jobs", "job", "Canberra", "Senior-Consultant_R-1"]
        )
        == "redhat.wd5.myworkdayjobs.com/redhat/Jobs"
    )
    assert (
        WorkdayProvider.slug_from_path("redhat.wd5.myworkdayjobs.com", ["jobs"])
        == "redhat.wd5.myworkdayjobs.com/redhat/jobs"
    )


def test_the_cxs_api_path_names_the_site_at_a_fixed_position() -> None:
    """`/wday/cxs/{tenant}/{site}/jobs` is the fetch URL `board_url` builds, so a user pasting
    one back is realistic. Read positionally, not by skipping: the old rule returned the TENANT
    here, because `wday` and `cxs` were skipped and the tenant came next."""
    assert (
        WorkdayProvider.slug_from_path(
            "acme.wd5.myworkdayjobs.com", ["wday", "cxs", "acme", "AcmeCareers", "jobs"]
        )
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
        parse_posting("acme.wd5.myworkdayjobs.com", "AcmeCareers", {}, None)


def test_parse_posting_raises_on_empty_title() -> None:
    listed = {"externalPath": "/job/x/Role_JR1", "title": ""}
    with pytest.raises(ValueError, match="empty title"):
        parse_posting("acme.wd5.myworkdayjobs.com", "AcmeCareers", listed, None)


def test_parse_posting_captures_detail_and_time_type() -> None:
    # the CAPTURE contract at the parse_posting seam, in isolation: raw_json["detail"] and
    # ["timeType"] are populated from arguments handed straight in. The fetch_board wiring
    # that produces those arguments is covered end-to-end by
    # test_detail_fetch_fills_body_text_and_captures_time_type.
    listed = _fx("list_normal.json")["jobPostings"][0]
    detail = _fx("detail_normal.json")
    posting = parse_posting("acme.wd5.myworkdayjobs.com", "AcmeCareers", listed, detail)
    assert posting.raw_json["detail"] == detail
    assert posting.raw_json["timeType"] == "Full time"
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
    posting = parse_posting("acme.wd5.myworkdayjobs.com", "AcmeCareers", listed, None)
    assert posting.remote_policy == expected


def test_posted_at_is_none_for_an_unparseable_start_date() -> None:
    listed = {"externalPath": "/job/x/Role_JR1", "title": "Role"}
    detail = {"jobPostingInfo": {"startDate": "not-a-date"}}
    posting = parse_posting("acme.wd5.myworkdayjobs.com", "AcmeCareers", listed, detail)
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
    posting = parse_posting("acme.wd5.myworkdayjobs.com", "AcmeCareers", listed, None)
    assert posting.remote_policy == "remote"


def test_posted_at_handles_a_timezone_aware_timestamp() -> None:
    # the ARITHMETIC is the point: 10:00+05:00 is 05:00Z, and posted_at is naive UTC. An
    # inverted conversion (15:00) or a dropped tzinfo (10:00) both survive `is not None`.
    listed = {"externalPath": "/job/x/Role_JR1", "title": "Role"}
    detail = {"jobPostingInfo": {"startDate": "2026-08-04T10:00:00+05:00"}}
    posting = parse_posting("acme.wd5.myworkdayjobs.com", "AcmeCareers", listed, detail)
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
def test_a_repeated_full_page_stops_at_the_offset_wrap_not_the_page_cap(tmp_path: Path) -> None:
    # Workday serves byte-identical FULL pages past a board's real count (Intel; every board
    # once offset >= 2000 wraps to page 1) instead of a short page. Without a no-forward-
    # progress break this burns every page up to _MAX_PAGES. Termination is on the first full
    # page that adds nothing new, kept `partial`.
    full = _fx("list_page_full.json")
    route = respx.post(LIST_URL).mock(return_value=httpx.Response(200, json=full))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request(budget=0))
    assert route.call_count == 2  # page 0 collects; page 1 repeats it and adds nothing -> stop
    assert snapshot.status == "partial"
    assert "added no new postings" in (snapshot.error or "")


@respx.mock
def test_page_cap_bounds_a_board_that_keeps_yielding_new_full_pages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The _MAX_PAGES cap is the last-ditch bound for a genuinely huge board that keeps
    # returning FULL pages of NEW postings (so neither a short page nor the no-new-progress
    # break ever fires). Shrink the cap so the fixture stays small.
    monkeypatch.setattr("boardwatch.providers.workday._MAX_PAGES", 3)
    base = _fx("list_page_full.json")["jobPostings"]

    def _distinct_page(i: int) -> dict[str, Any]:
        rows = [dict(r) | {"externalPath": f"/job/P{i}-{j}"} for j, r in enumerate(base)]
        return {"total": 2000, "jobPostings": rows, "facets": []}

    respx.post(LIST_URL).mock(
        side_effect=[httpx.Response(200, json=_distinct_page(i)) for i in range(3)]
    )
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
def test_fetch_board_issues_no_facet_filtered_post(tmp_path: Path) -> None:
    # T14: the workerSubType facet probe is DELETED. list_normal.json's facets block
    # carries an intern-shaped bucket ("Intern (Fixed Term)"); a board fetch must not
    # issue any extra facet-filtered POST for it. call_count must equal the plain
    # pagination requests only (1, for this single short page).
    route = respx.post(LIST_URL).mock(
        return_value=httpx.Response(200, json=_fx("list_normal.json"))
    )
    _mock_all_details()
    provider.fetch_board(_fetcher(tmp_path), _request())
    assert route.call_count == 1  # board page only; zero extra facet-filtered POSTs


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
def test_coverage_fields_are_populated_on_a_normal_board(tmp_path: Path) -> None:
    respx.post(LIST_URL).mock(return_value=httpx.Response(200, json=_fx("list_normal.json")))
    _mock_all_details()
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.board_reported_total == 3
    assert snapshot.board_enumerated == 3
    assert snapshot.board_total_censored is False
    assert snapshot.detail_deferred == 0


@respx.mock
def test_detail_deferred_counts_the_pre_truncation_unseen_list(tmp_path: Path) -> None:
    # THE SUBTLE PART: `unseen` is rebound by the detail-budget slice, so
    # detail_deferred must be computed from a copy taken before that slice runs. Getting
    # this backwards yields a constant 0 no matter how much was actually deferred.
    respx.post(LIST_URL).mock(return_value=httpx.Response(200, json=_fx("list_normal.json")))
    _mock_all_details()
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request(budget=1))
    assert snapshot.board_enumerated == 3
    assert snapshot.detail_deferred == 2  # 3 unseen, 1 detailed -> 2 deferred, never 0


@respx.mock
def test_board_reported_total_reads_the_uncapped_facet_sum(tmp_path: Path) -> None:
    respx.post(LIST_URL).mock(
        return_value=httpx.Response(200, json=_fx("list_censored_with_facets.json"))
    )
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.board_reported_total == 4589
    assert snapshot.board_total_censored is True
    assert snapshot.status == "partial"
    assert "censored at 2000" in (snapshot.error or "")


@respx.mock
def test_an_unrecovered_censor_persists_no_total_beside_the_censored_flag(
    tmp_path: Path,
) -> None:
    """The persisted pair is the whole signal. A censored board whose facets carried nothing
    used to persist `board_reported_total=2000` — indistinguishable from the recovered case in
    the very column the instrument added, with the difference surviving only as English in
    `error`. Asserted against the recovered board above: same flag, different total."""
    payload = dict(_fx("list_censored_with_facets.json"))
    payload["facets"] = []
    respx.post(LIST_URL).mock(return_value=httpx.Response(200, json=payload))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.board_total_censored is True
    assert snapshot.board_reported_total is None
    # and the run-log note is not emitted, because there is no recovered number to report
    assert "censored at 2000" not in (snapshot.error or "")


@respx.mock
def test_every_diagnostic_survives_never_truncated(tmp_path: Path) -> None:
    # REGRESSION: `error` used to truncate at errors[:3], so a board with several page-level
    # notes silently dropped its LATE detail-budget note — the only record of a board's
    # inventory size (measured on Citi). Every note must survive, however many precede it.
    def _page(i: int, valid: int) -> dict[str, Any]:
        rows: list[dict[str, Any]] = [
            {"externalPath": f"/job/P{i}-{j}"} for j in range(valid)
        ]
        rows.append({"title": "no externalPath"})  # one "dropped 1 rows" note per page
        return {"total": 2000, "jobPostings": rows, "facets": []}

    respx.post(LIST_URL).mock(
        side_effect=[
            httpx.Response(200, json=_page(0, 20)),
            httpx.Response(200, json=_page(1, 20)),
            httpx.Response(200, json=_page(2, 20)),
            httpx.Response(200, json={"total": 2000, "jobPostings": [], "facets": []}),
        ]
    )
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request(budget=0))
    err = snapshot.error or ""
    assert err.count("dropped 1 rows") == 3  # three page-level notes lead
    assert "detail budget" in err  # the fourth, late note is NOT truncated away


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
    assert parse_posting("h", "S", rows[0], None).remote_policy == "remote"
    # "Partially Remote" is HYBRID, not remote — the location text says "Santa Clara, CA",
    # so a text-only heuristic would have returned "unknown" here
    assert parse_posting("h", "S", rows[1], None).remote_policy == "hybrid"


def test_remote_policy_falls_back_to_location_text_without_remote_type() -> None:
    # not every tenant sets remoteType (Etsy does, NVIDIA does not)
    from boardwatch.providers.workday import parse_posting

    rows = _fx("list_normal.json")["jobPostings"]
    assert "remoteType" not in rows[2]
    assert parse_posting("h", "S", rows[2], None).remote_policy == "unknown"


def test_facet_sum_beats_the_2000_censor() -> None:
    """Workday caps `total` at 2000; facets are aggregated by another path and are not capped."""
    payload = _fx("list_censored_with_facets.json")
    total, censored = _uncapped_total(payload)
    assert censored is True
    assert total == 4589


def test_uncensored_board_is_not_flagged_censored_and_keeps_its_own_total() -> None:
    """The CENSOR-DETECTION control, and only that: `_uncapped_total` returns at `if total !=
    _TOTAL_CENSOR` before any facet code runs, so this would pass with the whole facet block
    deleted. The facet arithmetic's control is
    `test_facet_sum_agrees_with_an_uncensored_boards_total` below — this test used to claim to
    be it."""
    payload = {
        "total": 740, "jobPostings": [],
        "facets": [{"facetParameter": "jobFamilyGroup",
                    "values": [{"id": "a", "descriptor": "Eng", "count": 740}]}],
    }
    total, censored = _uncapped_total(payload)
    assert censored is False
    assert total == 740


def test_facet_sum_agrees_with_an_uncensored_boards_total() -> None:
    """THE KNOWN-POSITIVE CONTROL for the facet arithmetic itself, run against a payload whose
    `total` is BELOW the censor so the answer is independently known. Live 2026-08-22 this held
    on four real boards: Adobe 740/740, Intel 645/645, Regeneron 592/592, Fidelity 565/565.

    `list_normal.json` is the strongest available in-repo case because it was authored for the
    pager contract, long before this instrument existed, so its facets were not built to yield
    a number this assertion wants — `workerSubType` sums to its `total` of 3 while `locations`
    sums to 1, which also pins the largest-non-zero-dimension rule against a smaller sibling.

    Deleting the facet block makes this red; the fixture's own `total` is the oracle."""
    payload = _fx("list_normal.json")
    assert payload["total"] < 2000, "the control must run on an UNCENSORED board"
    assert _facet_sum(payload) == payload["total"]

    # And on the shape the live control measured: several dimensions, all partitioning the
    # same 740 postings, one of them split across values.
    adobe = {
        "total": 740,
        "facets": [
            {"facetParameter": "jobFamilyGroup",
             "values": [{"id": "a", "count": 500}, {"id": "b", "count": 240}]},
            {"facetParameter": "timeType", "values": [{"id": "ft", "count": 740}]},
            {"facetParameter": "locationMainGroup", "values": [{"id": "z", "count": 0}]},
        ],
    }
    assert _facet_sum(adobe) == adobe["total"]


def test_facet_sum_is_none_when_the_facets_carry_no_number() -> None:
    """`None`, never 0: an absent aggregate is not an empty board. Pairs with the test above so
    the helper is pinned in both directions."""
    assert _facet_sum({"facets": []}) is None
    assert _facet_sum({"facets": [{"values": [{"count": 0}]}]}) is None
    assert _facet_sum({}) is None


def test_missing_facets_falls_back_to_total_and_is_not_invented() -> None:
    total, censored = _uncapped_total({"total": 512, "jobPostings": [], "facets": []})
    assert (total, censored) == (512, False)


def test_absent_total_yields_none_never_zero() -> None:
    """None means the board stated nothing. Zero would be a claim we cannot support, and so
    is `censored=False`: with no total there is nothing to have been censored, and `False`
    would falsely claim we know this board was NOT censored."""
    assert _uncapped_total({"jobPostings": []}) == (None, None)


def test_an_unrecovered_censor_yields_no_total_not_the_censor_value() -> None:
    """`censored=1` used to collapse two different epistemic states into one persisted row:
    `(4589, True)` — a real size recovered by a second aggregation path — and `(2000, True)` —
    facets unusable, so 2,000 is only a FLOOR. Returning the censor value as a total is the
    server refusing to answer, recorded as an answer.

    With `(None, True)`, `censored and board_reported_total is not None` means "facet-recovered"
    and nothing has to parse a message to learn it. Both states are asserted side by side here,
    because the defect was that they were indistinguishable."""
    recovered = _uncapped_total(_fx("list_censored_with_facets.json"))
    unrecovered = _uncapped_total({"total": 2000, "facets": [{"values": [{"count": 0}]}]})
    assert recovered == (4589, True)
    assert unrecovered == (None, True)
    assert recovered[0] is not None and unrecovered[0] is None


def test_a_facet_dimension_summing_to_exactly_the_censor_value_is_still_a_recovery() -> None:
    """The old note guard was `board_total != _TOTAL_CENSOR`, so a board whose facets
    legitimately sum to 2,000 was silently treated as unrecovered. It is a recovery: the facets
    are a second, uncapped aggregation path that happens to agree with the cap."""
    payload = {"total": 2000, "facets": [{"values": [{"count": 2000}]}]}
    assert _uncapped_total(payload) == (2000, True)


def test_a_non_numeric_total_yields_none_not_a_crash() -> None:
    assert _uncapped_total({"total": "not-a-number"}) == (None, None)
    assert _uncapped_total({"total": {}}) == (None, None)


def test_ragged_facets_never_raise() -> None:
    """Live payloads are not schema-validated. Every one of these shapes was observed to raise
    before this fix, which turns the whole board `status="failed"` via coordinator.py's
    belt-and-braces except — for precisely the large, censored tenants this instrument exists
    to measure."""
    # facets is not a list at all (unusable => no total recovered, NOT the censor value)
    assert _uncapped_total({"total": 2000, "facets": {"not": "a list"}}) == (None, True)
    # a facet in the list is not a dict
    assert _uncapped_total({"total": 2000, "facets": ["not a dict", 7]}) == (None, True)
    # a facet's "values" contains a non-dict entry alongside a real one
    payload = {"total": 2000, "facets": [{"values": ["nope", {"count": 5}]}]}
    assert _uncapped_total(payload) == (5, True)
    # "count" is a present JSON null, not an absent key — .get(key, default) does not catch it
    payload = {"total": 2000, "facets": [{"values": [{"count": None}, {"count": 10}]}]}
    assert _uncapped_total(payload) == (10, True)


# ------------------------------------------------- facet slicing (T71, property 6)
# Workday clamps `total` at 2000 and wraps the pager past it, so a board larger than that is
# enumerated blind and partially: live 2026-09-07 Citi's 4,376 postings reported 2000 and
# yielded 1,988, of which 1,075 were technology roles and we held 566. The facets are NOT
# clamped, so a slug may name ONE facet bucket and the sliced `total` reads that bucket's true
# size. The absolute requirement is that a slug with NO fragment behaves as it always did.

SLICED_SLUG = f"{SLUG}#jobFamilyGroup=Technology"
SLICED_URL = f"{LIST_URL}#jobFamilyGroup=Technology"
# The tenant's own opaque hash for "Technology" in list_facet_catalog.json. Never hardcoded in
# a slug or a catalog in production — resolved from the live board on every fetch.
TECHNOLOGY_ID = "3f2c9a1e708d01575bddff0c12010001"


def _sliced_request(
    slug: str = SLICED_SLUG, url: str = SLICED_URL,
    known: frozenset[str] = frozenset(), budget: int = 50,
) -> BoardRequest:
    return BoardRequest(
        provider="workday", slug=slug, url=url,
        known_posting_ids=known, detail_budget=budget,
    )


def _sliced_ids() -> frozenset[str]:
    return _all_listed_ids("list_sliced_page_full.json", "list_sliced_page_short.json")


def _bodies(route: respx.Route) -> list[dict[str, Any]]:
    return [json.loads(call.request.content) for call in route.calls]


# ---- the backwards-compatibility contract: an unsliced slug must not move at all ----------

@respx.mock
def test_an_unsliced_request_body_is_byte_identical_to_the_shipped_one(tmp_path: Path) -> None:
    """THE BACKWARDS-COMPATIBILITY ASSERTION. 157 live boards use the three-part slug, and
    `appliedFacets` was already in the body and already empty, so slicing must POPULATE that
    field rather than change the body's bytes, key order or key set for an unsliced board.

    Pinned as BYTES, not as a parsed dict: a parsed comparison passes for a version that
    reorders the keys or renders `{}` as `null`, and the body is the only thing that decides
    which postings the server returns. Break `_search_body` by making it inject a group key
    unconditionally and this is the assertion that fails, on the first page's bytes."""
    route = respx.post(LIST_URL).mock(
        side_effect=[
            httpx.Response(200, json=_fx("list_page_full.json")),
            httpx.Response(200, json=_fx("list_page_short.json")),
        ]
    )
    provider.fetch_board(_fetcher(tmp_path), _request(budget=0))
    assert [call.request.content for call in route.calls] == [
        b'{"appliedFacets":{},"limit":20,"offset":0,"searchText":""}',
        b'{"appliedFacets":{},"limit":20,"offset":20,"searchText":""}',
    ]


@respx.mock
def test_an_unsliced_board_issues_no_facet_catalog_request(tmp_path: Path) -> None:
    # The catalog request is the whole extra cost of slicing and an unsliced board must not
    # pay it: one POST for a one-page board, exactly as before.
    route = respx.post(LIST_URL).mock(
        return_value=httpx.Response(200, json=_fx("list_normal.json"))
    )
    provider.fetch_board(
        _fetcher(tmp_path), _request(known=_all_listed_ids("list_normal.json"))
    )
    assert route.call_count == 1


def test_an_unsliced_slug_still_yields_the_bare_triple_and_the_bare_url() -> None:
    assert WorkdayProvider.normalize_slug(SLUG) == SLUG
    assert provider.board_url(SLUG) == LIST_URL
    assert split_target(SLUG) == ("acme.wd5.myworkdayjobs.com", "acme", "AcmeCareers", None)


# ---- slug identity -----------------------------------------------------------------------

def test_a_facet_fragment_is_parsed_off_before_the_triple_split() -> None:
    # NOT a fourth path component: `split_slug` requires exactly three and every stored slug
    # uses that form, so a fourth would collide with the invariant and with 157 live boards.
    host, tenant, site, facet = split_target(SLICED_SLUG)
    assert (host, tenant, site) == ("acme.wd5.myworkdayjobs.com", "acme", "AcmeCareers")
    assert facet == ("jobFamilyGroup", "Technology")


def test_a_sliced_slug_normalizes_and_round_trips() -> None:
    once = WorkdayProvider.normalize_slug(
        "ACME.WD5.MyWorkdayJobs.com/ACME/AcmeCareers#jobFamilyGroup=Technology"
    )
    assert once == SLICED_SLUG
    assert WorkdayProvider.normalize_slug(once) == once


def test_a_sliced_slug_round_trips_through_the_qualified_form() -> None:
    assert parse_board_target(f"workday:{SLICED_SLUG}") == ("workday", SLICED_SLUG)


def test_board_url_makes_two_slices_of_one_tenant_two_distinct_cache_keys() -> None:
    """`board_url` IS the `http_cache` key and the `board_scans` url. Without the fragment,
    every slice of one tenant collapses onto the unsliced board's row and they overwrite each
    other's validators in turn."""
    technology = provider.board_url(SLICED_SLUG)
    operations = provider.board_url(f"{SLUG}#jobFamilyGroup=Operations")
    assert technology == SLICED_URL
    assert operations == f"{LIST_URL}#jobFamilyGroup=Operations"
    assert technology != operations != provider.board_url(SLUG)
    # the fragment goes at the END, after `/jobs` — not spliced into the path, which is what
    # reading it as part of the site segment produces
    assert technology.startswith(f"{LIST_URL}#")


@pytest.mark.parametrize(
    "bad",
    [
        "acme.wd5.myworkdayjobs.com/acme/AcmeCareers#jobFamilyGroup",   # no '='
        "acme.wd5.myworkdayjobs.com/acme/AcmeCareers#=Technology",      # no group
        "acme.wd5.myworkdayjobs.com/acme/AcmeCareers#jobFamilyGroup=",  # no descriptor
        "acme.wd5.myworkdayjobs.com/acme/AcmeCareers#job Family=Tech",  # whitespace in group
        "acme.wd5.myworkdayjobs.com/acme/AcmeCareers#jobFamilyGroup=T\tech",  # control char
        "acme.wd5.myworkdayjobs.com/acme#jobFamilyGroup=Technology",    # not a triple
        "acme.wd5.myworkdayjobs.com/acme/AcmeCareers#",                 # empty fragment
    ],
)
def test_a_malformed_facet_fragment_is_rejected(bad: str) -> None:
    with pytest.raises(ValueError):
        split_target(bad)


def test_a_descriptor_keeps_its_spaces_punctuation_and_later_equals_signs() -> None:
    # "Software Engineering and Architecture" is a real jobFamily; a live descriptor carries
    # spaces, '&' and ','. The fragment splits on the FIRST '=' only and decodes nothing,
    # because the descriptor is compared to the live catalog verbatim.
    _, _, _, facet = split_target(f"{SLUG}#jobFamilyGroup=Operations, Sales & Marketing")
    assert facet == ("jobFamilyGroup", "Operations, Sales & Marketing")
    _, _, _, with_equals = split_target(f"{SLUG}#jobFamilyGroup=A=B")
    assert with_equals == ("jobFamilyGroup", "A=B")


def test_a_descriptors_case_is_preserved_because_the_catalog_match_is_exact() -> None:
    _, _, _, facet = split_target(f"{SLUG}#Country_and_Jurisdiction=United States of America")
    assert facet == ("Country_and_Jurisdiction", "United States of America")


# ---- the facet catalog -------------------------------------------------------------------

def test_the_facet_catalog_reads_a_group_nested_inside_another_groups_values() -> None:
    """Live Citi 2026-09-07 answers a `locationMainGroup` whose single value is itself a GROUP
    (`facetParameter: "locations"`) carrying the buckets, with no `id`/`count` of its own. A
    top-level-only read reports `locations` absent, and an absent group is a board-level ERROR
    here — so that reading refuses a slice the tenant really offers."""
    catalog = _facet_catalog(_fx("list_facet_catalog.json"))
    assert catalog["jobFamilyGroup"]["Technology"] == TECHNOLOGY_ID
    assert "locations" in catalog
    assert catalog["locations"]["1 ACME WAY  SPRINGFIELD"]


def test_the_facet_catalog_never_raises_on_a_ragged_payload() -> None:
    # same defensive contract as `_facet_sum`: a live payload is not schema-validated and one
    # odd entry must not fail the whole board
    assert _facet_catalog({}) == {}
    assert _facet_catalog({"facets": "not a list"}) == {}
    assert _facet_catalog({"facets": ["nope", 7]}) == {}
    assert _facet_catalog({"facets": [{"facetParameter": "g", "values": "nope"}]}) == {}
    # a bucket with no id, and one with a null descriptor, are both unusable as a slice target
    payload = {"facets": [{"facetParameter": "g", "values": [
        {"descriptor": "NoId", "count": 3}, {"id": "x", "descriptor": None},
        {"id": "y", "descriptor": "Real"}]}]}
    assert _facet_catalog(payload) == {"g": {"Real": "y"}}


# ---- a sliced fetch ----------------------------------------------------------------------

@respx.mock
def test_a_sliced_board_reads_its_total_from_the_slice_not_the_2000_censor(
    tmp_path: Path,
) -> None:
    """THE MEASURED POINT OF THE WHOLE TICKET. Unfiltered, this board reports the 2000 censor
    and its facets recover 4589; sliced, `total` reads the bucket's TRUE 25 and the pager
    enumerates every one of them. Live on Citi 2026-09-07: unfiltered total=2000 / 1,988
    enumerated, sliced total=1074 / 1,074 enumerated."""
    respx.post(LIST_URL).mock(
        side_effect=[
            httpx.Response(200, json=_fx("list_facet_catalog.json")),
            httpx.Response(200, json=_fx("list_sliced_page_full.json")),
            httpx.Response(200, json=_fx("list_sliced_page_short.json")),
        ]
    )
    snapshot = provider.fetch_board(
        _fetcher(tmp_path), _sliced_request(known=_sliced_ids(), budget=0)
    )
    assert snapshot.status == "complete"
    assert snapshot.board_reported_total == 25
    assert snapshot.board_total_censored is False
    assert snapshot.board_enumerated == 25
    assert len(snapshot.listed_ids) == 25
    # and the unfiltered control, on the same fixture, still reads the censored 4589
    assert _uncapped_total(_fx("list_facet_catalog.json")) == (4589, True)


@respx.mock
def test_a_sliced_board_sends_the_id_resolved_from_this_boards_own_catalog(
    tmp_path: Path,
) -> None:
    """One unfiltered POST reads the catalog, every page after it carries the resolved id.
    The id is an opaque tenant hash and appears in NO slug and NO catalog in this repo —
    a slug names the DESCRIPTOR and the id is resolved at fetch time."""
    route = respx.post(LIST_URL).mock(
        side_effect=[
            httpx.Response(200, json=_fx("list_facet_catalog.json")),
            httpx.Response(200, json=_fx("list_sliced_page_full.json")),
            httpx.Response(200, json=_fx("list_sliced_page_short.json")),
        ]
    )
    provider.fetch_board(_fetcher(tmp_path), _sliced_request(known=_sliced_ids()))
    bodies = _bodies(route)
    assert route.call_count == 3  # 1 catalog + 2 pages, and the pager stopped on the short one
    assert bodies[0]["appliedFacets"] == {}          # the catalog read is UNFILTERED
    assert bodies[0]["offset"] == 0
    assert [b["appliedFacets"] for b in bodies[1:]] == [
        {"jobFamilyGroup": [TECHNOLOGY_ID]}, {"jobFamilyGroup": [TECHNOLOGY_ID]},
    ]
    assert [b["offset"] for b in bodies[1:]] == [0, 20]  # the slice is paged from 0 again
    # The fragment is IDENTITY, not address: every POST targets the bare CXS endpoint — the
    # same one an unsliced board posts to, which is why one host lock and one delay still
    # serialize every slice of a tenant. NOTE this assertion cannot fail: httpx drops a
    # fragment when the client builds the request, so it holds even for a version that posts
    # to the fragment-bearing url. `fetch_board`'s own strip keeps the intent local instead of
    # delegating it to that normalization; it is belt and braces, not the thing pinned here.
    assert {str(call.request.url) for call in route.calls} == {LIST_URL}


@respx.mock
def test_the_catalog_requests_own_rows_never_enter_the_slices_inventory(
    tmp_path: Path,
) -> None:
    """The catalog request is the UNFILTERED board's first page. Enumerating its rows would put
    non-slice postings into the slice's `listed_ids`, and `listed_ids` is what authorizes
    apply_board to close everything it no longer sees."""
    respx.post(LIST_URL).mock(
        side_effect=[
            httpx.Response(200, json=_fx("list_facet_catalog.json")),
            httpx.Response(200, json=_fx("list_sliced_page_full.json")),
            httpx.Response(200, json=_fx("list_sliced_page_short.json")),
        ]
    )
    snapshot = provider.fetch_board(
        _fetcher(tmp_path), _sliced_request(known=_sliced_ids(), budget=0)
    )
    unfiltered = _all_listed_ids("list_facet_catalog.json")
    assert unfiltered  # the fixture really does carry rows the slice must not claim
    assert snapshot.listed_ids.isdisjoint(unfiltered)
    assert snapshot.listed_ids == _sliced_ids()


@respx.mock
def test_a_sliced_pager_stops_on_a_short_page_and_fetches_details_for_the_slice(
    tmp_path: Path,
) -> None:
    # the whole existing termination and detail machinery is unchanged under a slice
    respx.post(LIST_URL).mock(
        side_effect=[
            httpx.Response(200, json=_fx("list_facet_catalog.json")),
            httpx.Response(200, json=_fx("list_sliced_page_full.json")),
            httpx.Response(200, json=_fx("list_sliced_page_short.json")),
        ]
    )
    detail = _fx("detail_normal.json")
    for name in ("list_sliced_page_full.json", "list_sliced_page_short.json"):
        for row in _fx(name)["jobPostings"]:
            info = dict(detail["jobPostingInfo"]) | {"title": row["title"]}
            respx.get(_detail_url(row["externalPath"])).mock(
                return_value=httpx.Response(200, json={"jobPostingInfo": info})
            )
    snapshot = provider.fetch_board(_fetcher(tmp_path), _sliced_request())
    assert snapshot.status == "complete"
    assert len(snapshot.postings) == 25
    assert snapshot.detail_deferred == 0


@respx.mock
def test_the_facet_id_is_resolved_per_board_and_never_reused_across_tenants(
    tmp_path: Path,
) -> None:
    """`e32326e1...` is ONE tenant's id for "Technology" and means nothing on another, so
    caching it — in a module constant, a catalog file, or across two boards in one run — sends
    a second tenant a filter it does not recognise. Two boards, same descriptor, ids that must
    differ on the wire."""
    other_slug = "other.wd5.myworkdayjobs.com/other/OtherCareers#jobFamilyGroup=Technology"
    other_url = "https://other.wd5.myworkdayjobs.com/wday/cxs/other/OtherCareers/jobs"
    other_id = "9999aaaa708d01575bddff0c1201ffff"
    other_catalog = dict(_fx("list_facet_catalog.json"))
    other_catalog["facets"] = [
        {"facetParameter": "jobFamilyGroup",
         "values": [{"id": other_id, "descriptor": "Technology", "count": 25}]}
    ]

    acme = respx.post(LIST_URL).mock(
        side_effect=[
            httpx.Response(200, json=_fx("list_facet_catalog.json")),
            httpx.Response(200, json=_fx("list_sliced_page_short.json")),
        ]
    )
    other = respx.post(other_url).mock(
        side_effect=[
            httpx.Response(200, json=other_catalog),
            httpx.Response(200, json=_fx("list_sliced_page_short.json")),
        ]
    )
    fetcher = _fetcher(tmp_path)
    provider.fetch_board(fetcher, _sliced_request(known=_sliced_ids()))
    provider.fetch_board(
        fetcher,
        _sliced_request(slug=other_slug, url=f"{other_url}#jobFamilyGroup=Technology",
                        known=_sliced_ids()),
    )
    assert _bodies(acme)[1]["appliedFacets"] == {"jobFamilyGroup": [TECHNOLOGY_ID]}
    assert _bodies(other)[1]["appliedFacets"] == {"jobFamilyGroup": [other_id]}
    assert TECHNOLOGY_ID != other_id


# ---- the fail-safe direction: out of catalog is an ERROR, never an unfiltered fetch -------

@respx.mock
def test_an_unknown_descriptor_is_an_error_with_zero_rows_and_no_unfiltered_fallback(
    tmp_path: Path,
) -> None:
    """THE LOAD-BEARING DECISION. An unfiltered fallback would silently restore the blind
    2,000-row listing while the operator believed the board was sliced — the same class of
    failure as an ignored facet parameter or an unknown Oracle siteNumber. So: ERROR, a reason
    naming the descriptor, ZERO rows, and exactly ONE request — the catalog read.

    `route.call_count == 1` is the assertion that catches the fallback specifically: a version
    that fell back would fetch the unfiltered board's pages and enumerate them."""
    route = respx.post(LIST_URL).mock(
        return_value=httpx.Response(200, json=_fx("list_facet_catalog.json"))
    )
    snapshot = provider.fetch_board(
        _fetcher(tmp_path),
        _sliced_request(
            slug=f"{SLUG}#jobFamilyGroup=Warehouse Operations",
            url=f"{LIST_URL}#jobFamilyGroup=Warehouse Operations",
            budget=0,
        ),
    )
    assert snapshot.status == "failed"
    assert "Warehouse Operations" in (snapshot.error or "")
    assert snapshot.postings == []
    assert snapshot.listed_ids == frozenset()
    assert snapshot.board_enumerated is None
    assert route.call_count == 1  # the catalog read only; NO unfiltered listing was fetched
    # and the message names the group it looked in, plus what that group does offer
    assert "jobFamilyGroup" in (snapshot.error or "")
    assert "Technology" in (snapshot.error or "")


@respx.mock
def test_an_unknown_facet_group_is_an_error_naming_the_groups_the_tenant_returns(
    tmp_path: Path,
) -> None:
    """Tenants expose DIFFERENT groups: Citi, Target and Lowes offer `jobFamilyGroup` and no
    `jobFamily` at all. Naming an absent GROUP is as much an error as naming an absent
    descriptor, and the message must list what the tenant actually returned — the planning
    session's first probe read only `jobFamily` and reported "0 SWE roles" for three boards
    that in fact carry thousands."""
    route = respx.post(LIST_URL).mock(
        return_value=httpx.Response(200, json=_fx("list_facet_catalog.json"))
    )
    snapshot = provider.fetch_board(
        _fetcher(tmp_path),
        _sliced_request(
            slug=f"{SLUG}#jobFamily=Software Engineering and Architecture",
            url=f"{LIST_URL}#jobFamily=Software Engineering and Architecture",
            budget=0,
        ),
    )
    assert snapshot.status == "failed"
    assert "jobFamily" in (snapshot.error or "")
    assert "Software Engineering and Architecture" in (snapshot.error or "")
    assert "jobFamilyGroup" in (snapshot.error or "")  # what the tenant DOES offer
    assert snapshot.listed_ids == frozenset()
    assert route.call_count == 1


@respx.mock
def test_a_catalog_request_that_fails_is_a_failed_board_not_an_unfiltered_fetch(
    tmp_path: Path,
) -> None:
    route = respx.post(LIST_URL).mock(return_value=httpx.Response(500))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _sliced_request())
    assert snapshot.status == "failed"
    assert "facet catalog" in (snapshot.error or "")
    assert snapshot.listed_ids == frozenset()
    assert route.call_count == 1


@respx.mock
def test_a_catalog_response_with_no_facets_is_an_error_not_an_unfiltered_fetch(
    tmp_path: Path,
) -> None:
    # a tenant that stopped serving facets is exactly the case where a fallback would restore
    # the blind listing invisibly
    payload = dict(_fx("list_facet_catalog.json")) | {"facets": []}
    route = respx.post(LIST_URL).mock(return_value=httpx.Response(200, json=payload))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _sliced_request())
    assert snapshot.status == "failed"
    assert "Technology" in (snapshot.error or "")
    assert snapshot.listed_ids == frozenset()
    assert route.call_count == 1


@respx.mock
def test_a_non_json_catalog_response_is_an_error_not_an_unfiltered_fetch(
    tmp_path: Path,
) -> None:
    route = respx.post(LIST_URL).mock(
        return_value=httpx.Response(200, content=b"<html>maintenance</html>")
    )
    snapshot = provider.fetch_board(_fetcher(tmp_path), _sliced_request())
    assert snapshot.status == "failed"
    assert "facet catalog unreadable" in (snapshot.error or "")
    assert route.call_count == 1


# ---- healthcheck under a slice -----------------------------------------------------------

@respx.mock
def test_healthcheck_on_a_slice_the_tenant_offers_is_ok(tmp_path: Path) -> None:
    # the unfiltered response already carries the catalog, so this costs no extra request
    route = respx.post(LIST_URL).mock(
        return_value=httpx.Response(200, json=_fx("list_facet_catalog.json"))
    )
    assert provider.healthcheck(_fetcher(tmp_path), SLICED_SLUG) is BoardHealth.OK
    assert route.call_count == 1


@respx.mock
def test_healthcheck_on_a_slice_the_tenant_does_not_offer_is_error(tmp_path: Path) -> None:
    # otherwise a mistyped descriptor reads OK here and then fails every scan forever
    respx.post(LIST_URL).mock(
        return_value=httpx.Response(200, json=_fx("list_facet_catalog.json"))
    )
    health = provider.healthcheck(_fetcher(tmp_path), f"{SLUG}#jobFamily=Warehouse")
    assert health is BoardHealth.ERROR


def test_healthcheck_on_a_malformed_facet_fragment_is_error(tmp_path: Path) -> None:
    assert provider.healthcheck(_fetcher(tmp_path), f"{SLUG}#nope") is BoardHealth.ERROR
