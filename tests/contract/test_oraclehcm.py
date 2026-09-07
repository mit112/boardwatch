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
from boardwatch.lanes.dereference import UnresolvablePostingURL, parse_posting_target
from boardwatch.providers.base import BoardHealth
from boardwatch.providers.oraclehcm import (
    OracleHCMProvider,
    _body_text,
    _remote_policy,
    parse_posting,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "oraclehcm"

HOST = "acme.fa.us2.oraclecloud.com"
SITE = "CX_1"
SLUG = f"{HOST}/{SITE}"
LIST_URL = (
    f"https://{HOST}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
    "?onlyData=true&expand=requisitionList.secondaryLocations"
    "&finder=findReqs;siteNumber=CX_1,limit=200,offset=0,sortBy=POSTING_DATES_DESC"
)

provider = OracleHCMProvider()


def _fx(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _fx_json(name: str) -> dict[str, Any]:
    return json.loads(_fx(name))


def _rows(name: str = "list_normal.json") -> list[dict[str, Any]]:
    return list(_fx_json(name)["items"][0]["requisitionList"])


def _page_url(offset: int) -> str:
    return (
        f"https://{HOST}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
        "?onlyData=true&expand=requisitionList.secondaryLocations"
        f"&finder=findReqs;siteNumber=CX_1,limit=200,offset={offset}"
        ",sortBy=POSTING_DATES_DESC"
    )


def _detail_url(posting_id: str) -> str:
    return (
        f"https://{HOST}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails"
        f"?expand=all&onlyData=true&finder=ById;Id={posting_id},siteNumber=CX_1"
    )


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
        provider="oraclehcm", slug=SLUG, url=LIST_URL,
        known_posting_ids=known, detail_budget=budget, validators=validators,
    )


def _mock_all_details(fixture: str = "detail_normal.json") -> None:
    """One detail response per listed row, keyed by the row's own Id and Title."""
    base = _fx_json(fixture)["items"][0]
    for row in _rows():
        item = dict(base)
        item["Id"] = row["Id"]
        item["Title"] = row["Title"]
        item["PrimaryLocation"] = row["PrimaryLocation"]
        item["secondaryLocations"] = row["secondaryLocations"]
        item["WorkplaceTypeCode"] = row["WorkplaceTypeCode"]
        item["WorkplaceType"] = row["WorkplaceType"]
        body = {"items": [item], "count": 1, "hasMore": False, "limit": 499, "offset": 0}
        respx.get(_detail_url(row["Id"])).mock(return_value=httpx.Response(200, json=body))


def _detail_ids() -> set[str]:
    """Which posting ids actually had a detail request issued, read off respx's own call
    log rather than off the snapshot — a component's self-report is not verification."""
    ids: set[str] = set()
    for call in respx.calls:
        url = str(call.request.url)
        if "recruitingCEJobRequisitionDetails" not in url:
            continue
        _, _, tail = url.partition("finder=ById;Id=")
        ids.add(tail.partition(",")[0])
    return ids


# --------------------------------------------------------------------------- identity


def test_board_url_is_the_offset_zero_list_url() -> None:
    assert provider.board_url(SLUG) == LIST_URL


def test_board_url_parameter_order_is_stable_because_it_is_the_cache_key() -> None:
    assert provider.board_url(SLUG) == provider.board_url(SLUG)
    assert provider.board_url(f"{HOST.upper()}/{SITE}") == LIST_URL


def test_board_url_always_carries_expand_because_rows_vanish_without_it() -> None:
    # Trap 1: without `expand` the live API answers 200 with a real TotalJobsCount and NO
    # requisitionList key at all, so this parameter is correctness, not tuning.
    assert "expand=requisitionList.secondaryLocations" in provider.board_url(SLUG)


def test_normalize_slug_lowercases_the_host_and_preserves_site_case() -> None:
    assert OracleHCMProvider.normalize_slug(f"ACME.FA.US2.ORACLECLOUD.COM/{SITE}") == SLUG
    assert OracleHCMProvider.normalize_slug(f"{HOST}/CampusHiring") == f"{HOST}/CampusHiring"


@pytest.mark.parametrize(
    "slug",
    [
        "",
        "acme.fa.us2.oraclecloud.com",  # no site
        "acme.fa.us2.oraclecloud.com/CX_1/extra",  # three segments, not two
        "acme.fa.us2.oraclecloud.com/",  # empty site
        "/CX_1",  # empty host
        "acme.example.com/CX_1",  # wrong host suffix
        "notoraclecloud.com/CX_1",  # suffix without the label boundary
        ".oraclecloud.com/CX_1",  # suffix alone, no tenant label
        "acme.fa.us2.oraclecloud.com:8080/CX_1",  # authority-changing character
        "acme.fa.us2.oraclecloud.com/CX_1?x=1",  # query-introducing character
        "acme.fa.us2.oraclecloud.com/CX_1#frag",
        "acme.fa.us2.oraclecloud.com/CX_1,siteNumber=CX",  # finder-grammar injection
        "acme.fa.us2.oraclecloud.com/CX;limit=1",
        "acme.fa.us2.oraclecloud.com/CX 1",  # whitespace
        "acme.fa.us2.oraclecloud.com/CX\n1",
    ],
)
def test_normalize_slug_refuses_anything_reinterpretable(slug: str) -> None:
    with pytest.raises(ValueError):
        OracleHCMProvider.normalize_slug(slug)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (f"https://{HOST}/hcmUI/CandidateExperience/en/sites/CX_1", SLUG),
        (f"https://{HOST}/hcmUI/CandidateExperience/en/sites/CX_1/jobs", SLUG),
        (f"https://{HOST}/hcmUI/CandidateExperience/en/sites/CX_1/job/1001", SLUG),
        (f"https://{HOST}/hcmUI/CandidateExperience/fr-CA/sites/CX_1/job/1001", SLUG),
        # host case folds, site case does not
        (f"https://{HOST.upper()}/hcmUI/CandidateExperience/en/sites/CampusHiring",
         f"{HOST}/CampusHiring"),
    ],
)
def test_paste_url_parsing_through_board_urls(url: str, expected: str) -> None:
    assert parse_board_target(url) == ("oraclehcm", expected)


def test_qualified_form_accepts_the_composite_slug() -> None:
    assert parse_board_target(f"oraclehcm:{SLUG}") == ("oraclehcm", SLUG)


@pytest.mark.parametrize(
    "url",
    [
        # An Oracle Fusion host serves the ERP/HCM application UIs from the same name; a
        # non-career-site path must not mint a company row for a board that does not exist.
        f"https://{HOST}/fscmUI/faces/FuseWelcome",
        f"https://{HOST}/hcmUI/CandidateExperience/en",  # no `sites` marker
        f"https://{HOST}/hcmUI/CandidateExperience/en/sites",  # marker, nothing after it
        f"https://{HOST}/",
    ],
)
def test_paste_url_without_a_career_site_refuses_rather_than_guessing(url: str) -> None:
    with pytest.raises(UnknownBoardURL):
        parse_board_target(url)


# ------------------------------------------------------------------------ dereference


def test_posting_url_round_trips_through_dereference() -> None:
    url = f"https://{HOST}/hcmUI/CandidateExperience/en/sites/{SITE}/job/1001"
    target = parse_posting_target(url)
    assert (target.provider, target.slug, target.posting_ref) == ("oraclehcm", SLUG, "1001")


def test_the_provider_constructed_url_is_the_one_dereference_reads() -> None:
    # The two halves must agree or a lane-sourced posting cannot converge with a board scan
    # on UNIQUE(company_id, provider_posting_id).
    posting = parse_posting(
        HOST, SITE, _rows()[0], _fx_json("detail_normal.json")["items"][0]
    )
    target = parse_posting_target(posting.url)
    assert target.posting_ref == posting.provider_posting_id
    assert target.slug == SLUG


@pytest.mark.parametrize(
    "url",
    [
        f"https://{HOST}/hcmUI/CandidateExperience/en/sites/{SITE}",  # board root
        f"https://{HOST}/hcmUI/CandidateExperience/en/sites/{SITE}/jobs",
        f"https://{HOST}/hcmUI/CandidateExperience/en/sites/{SITE}/job/1001/apply",
        f"https://{HOST}/hcmUI/CandidateExperience/en/sites/{SITE}/job/1001/extra/more",
    ],
)
def test_dereference_refuses_anything_that_is_not_the_posting_shape(url: str) -> None:
    with pytest.raises(UnresolvablePostingURL):
        parse_posting_target(url)


# ---------------------------------------------------------------------------- parsing


def test_body_text_joins_the_three_external_sections_in_a_fixed_order() -> None:
    detail = {
        "ExternalDescriptionStr": "<p>Build the platform.</p>",
        "ExternalQualificationsStr": "<p>Required:</p><ul><li>Python</li><li>SQL</li></ul>",
        "ExternalResponsibilitiesStr": "<p>Own delivery.</p>",
    }

    body = _body_text(detail)

    # Tag syntax, not bare angle brackets: a correctly converted `5 &gt; 3` yields "5 > 3".
    assert "<p>" not in body and "<ul>" not in body and "<li>" not in body
    assert body == "Build the platform.\n\nRequired:\nPython\nSQL\n\nOwn delivery."


def test_body_text_excludes_the_corporate_and_organization_boilerplate() -> None:
    # Identical across a tenant's whole board; including it would pollute content_hash and
    # make revision detection useless.
    detail = {
        "ExternalDescriptionStr": "<p>Build the platform.</p>",
        "CorporateDescriptionStr": "<p>BOILERPLATE ABOUT THE EMPLOYER.</p>",
        "OrganizationDescriptionStr": "<p>MORE BOILERPLATE.</p>",
        "InternalResponsibilitiesStr": "<p>INTERNAL ONLY.</p>",
        "InternalQualificationsStr": "<p>INTERNAL ONLY.</p>",
    }

    assert _body_text(detail) == "Build the platform."


def test_body_text_of_a_posting_with_no_external_sections_is_empty_not_an_error() -> None:
    detail = _fx_json("detail_empty_sections.json")["items"][0]
    assert _body_text(detail) == ""


@pytest.mark.parametrize(
    ("code", "label", "expected"),
    [
        ("ORA_REMOTE", "Remote", "remote"),
        ("ORA_HYBRID", "Hybrid", "hybrid"),
        ("ORA_ON_SITE", "On-site", "onsite"),
        # the code wins over a disagreeing label: it is the closed, locale-independent field
        ("ORA_REMOTE", "Hybrid", "remote"),
        # label-only tenants (the code is null) still resolve
        (None, "Hybrid", "hybrid"),
        (None, "Remote", "remote"),
        (None, "On-site", "onsite"),
        # present-but-EMPTY, which is how "no workplace type" actually arrives
        (None, "", "unknown"),
        # out of catalog is `unknown`, never a new bucket
        ("ORA_SOMETHING_NEW", "", "unknown"),
    ],
)
def test_remote_policy_prefers_the_closed_code_over_the_localized_label(
    code: str | None, label: str, expected: str
) -> None:
    row = {"WorkplaceTypeCode": code, "WorkplaceType": label}
    assert _remote_policy({}, row) == expected


def test_parse_posting_reads_id_title_url_and_the_detail_timestamp() -> None:
    listed = _rows()[0]
    detail = _fx_json("detail_normal.json")["items"][0]

    posting = parse_posting(HOST, SITE, listed, detail)

    assert posting.provider_posting_id == "1001"
    assert posting.title == "Senior Platform Engineer"
    assert posting.url == (
        f"https://{HOST}/hcmUI/CandidateExperience/en/sites/{SITE}/job/1001"
    )
    # the detail's full instant, not the list's date-only PostedDate
    assert posting.posted_at is not None
    assert posting.posted_at.isoformat() == "2026-09-01T10:30:00"
    assert posting.salary_min is None and posting.salary_max is None  # D19


def test_locations_concatenate_primary_and_secondaries_and_dedupe_in_order() -> None:
    rows = {row["Id"]: row for row in _rows()}
    detail = _fx_json("detail_normal.json")["items"][0]

    one = parse_posting(HOST, SITE, rows["1001"], detail)
    assert one.locations == ["Springfield, United States", "Shelbyville, United States"]

    # row 1003's first secondary duplicates its primary; it must appear once
    third = dict(detail)
    third["PrimaryLocation"] = rows["1003"]["PrimaryLocation"]
    third["secondaryLocations"] = rows["1003"]["secondaryLocations"]
    assert parse_posting(HOST, SITE, rows["1003"], third).locations == [
        "Ogdenville, United States",
        "North Haverbrook, United States",
    ]


def test_department_reads_the_department_field_and_falls_back_to_the_list_job_family() -> None:
    """`Department` is on BOTH payloads and wins; `JobFamily` is on the LISTED ROW only.

    Both were null on all three tenants probed on 2026-09-06, so the populated case is built
    here rather than pinned into a fixture that would then misdescribe the live shape. The
    detail payload has no `JobFamily` key at all -- it carries `JobFamilyId` -- so a read of
    `detail["JobFamily"]` is one that can never hit.
    """
    listed = _rows()[0]
    detail = _fx_json("detail_normal.json")["items"][0]
    assert "JobFamily" not in detail and "Department" in detail  # the live shape
    assert listed["JobFamily"] == "Engineering"

    populated = dict(detail, Department="Cloud Platform")
    assert parse_posting(HOST, SITE, listed, populated).department == "Cloud Platform"

    # Department null on both sides falls back to the listed row's JobFamily...
    assert parse_posting(HOST, SITE, listed, detail).department == "Engineering"
    # ...and a row carrying neither yields None rather than an empty string.
    assert parse_posting(HOST, SITE, _rows()[1], detail).department is None


def test_parse_posting_raises_on_an_empty_title_so_one_bad_row_cannot_pass() -> None:
    listed = dict(_rows()[0])
    listed["Title"] = "   "
    with pytest.raises(ValueError):
        parse_posting(HOST, SITE, listed, {})


# ------------------------------------------------------------------------- fetch_board


@respx.mock
def test_fetch_board_lists_and_details_a_single_page_board(tmp_path: Path) -> None:
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, content=_fx("list_normal.json")))
    _mock_all_details()

    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())

    assert snapshot.status == "complete"
    assert snapshot.error is None
    assert {p.provider_posting_id for p in snapshot.postings} == {"1001", "1002", "1003"}
    assert snapshot.board_reported_total == 3
    assert snapshot.board_enumerated == 3
    assert snapshot.detail_deferred == 0


@respx.mock
def test_listed_ids_is_the_full_live_inventory_not_the_fetched_subset(
    tmp_path: Path,
) -> None:
    """RED FIRST. `listed_ids` must carry EVERY id the board listed, including the ones whose
    detail fetch was skipped because they are already known. A provider that built it from
    `postings` instead would hand apply_board an inventory missing 1001 and 1002, and
    `_process_missing` would close two live postings on the next scan."""
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, content=_fx("list_normal.json")))
    _mock_all_details()

    snapshot = provider.fetch_board(
        _fetcher(tmp_path), _request(known=frozenset({"1001", "1002"}))
    )

    assert snapshot.listed_ids == frozenset({"1001", "1002", "1003"})
    # and it is genuinely a SUPERSET of what was materialised this run
    assert {p.provider_posting_id for p in snapshot.postings} == {"1003"}
    assert snapshot.board_enumerated == 3


@respx.mock
def test_detail_fetches_skip_ids_already_known(tmp_path: Path) -> None:
    """RED FIRST. Counted off respx's call log, not off the snapshot: the point is that the
    REQUEST was never issued, which a snapshot assertion cannot distinguish from a request
    whose result was discarded."""
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, content=_fx("list_normal.json")))
    _mock_all_details()

    snapshot = provider.fetch_board(
        _fetcher(tmp_path), _request(known=frozenset({"1001", "1002"}))
    )

    assert _detail_ids() == {"1003"}
    assert snapshot.status == "complete"


@respx.mock
def test_a_board_whose_postings_are_all_known_issues_no_detail_request(
    tmp_path: Path,
) -> None:
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, content=_fx("list_normal.json")))
    _mock_all_details()

    snapshot = provider.fetch_board(
        _fetcher(tmp_path), _request(known=frozenset({"1001", "1002", "1003"}))
    )

    assert _detail_ids() == set()
    assert snapshot.postings == []
    assert snapshot.listed_ids == frozenset({"1001", "1002", "1003"})
    assert snapshot.status == "complete"


@respx.mock
def test_detail_budget_caps_the_fetches_and_is_reported(tmp_path: Path) -> None:
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, content=_fx("list_normal.json")))
    _mock_all_details()

    snapshot = provider.fetch_board(_fetcher(tmp_path), _request(budget=2))

    assert len(_detail_ids()) == 2
    assert len(snapshot.postings) == 2
    assert snapshot.status == "partial"
    assert snapshot.error is not None and "detail budget of 2 exceeded" in snapshot.error
    assert snapshot.detail_deferred == 1
    # the budget must NOT shrink the live inventory, or apply_board closes the deferred one
    assert snapshot.listed_ids == frozenset({"1001", "1002", "1003"})


@respx.mock
def test_pagination_follows_a_full_page_and_stops_on_a_short_one(tmp_path: Path) -> None:
    respx.get(LIST_URL).mock(
        return_value=httpx.Response(200, content=_fx("list_page_full.json"))
    )
    respx.get(_page_url(200)).mock(
        return_value=httpx.Response(200, content=_fx("list_page_short.json"))
    )
    for row in _rows("list_page_full.json") + _rows("list_page_short.json"):
        item = dict(_fx_json("detail_normal.json")["items"][0])
        item["Id"] = row["Id"]
        item["Title"] = row["Title"]
        respx.get(_detail_url(row["Id"])).mock(
            return_value=httpx.Response(200, json={"items": [item], "count": 1})
        )

    snapshot = provider.fetch_board(_fetcher(tmp_path), _request(budget=500))

    assert snapshot.board_enumerated == 202
    assert len(snapshot.listed_ids) == 202
    # the total is read from page 0 only; page 1 reports TotalJobsCount 0 (trap 3), and
    # trusting it there would make this board look like a 202-of-0 overshoot
    assert snapshot.board_reported_total == 202
    assert snapshot.status == "complete"


@respx.mock
def test_a_missing_requisition_list_fails_rather_than_reading_as_an_empty_board(
    tmp_path: Path,
) -> None:
    """Trap 1. A 200 carrying TotalJobsCount 2273 and no rows is the dropped-`expand`
    signature. Read as an empty board it would close every posting the company has."""
    respx.get(LIST_URL).mock(
        return_value=httpx.Response(200, content=_fx("list_no_expand.json"))
    )

    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())

    assert snapshot.status == "failed"
    assert snapshot.postings == []
    assert snapshot.listed_ids == frozenset()
    assert snapshot.error is not None and "requisitionList" in snapshot.error


@respx.mock
def test_an_empty_board_is_complete_and_empty(tmp_path: Path) -> None:
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, content=_fx("list_empty.json")))

    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())

    assert snapshot.status == "complete"
    assert snapshot.postings == []
    assert snapshot.listed_ids == frozenset()
    assert snapshot.board_reported_total == 0
    assert snapshot.board_enumerated == 0


@respx.mock
def test_a_withdrawn_requisition_is_dropped_from_the_inventory(tmp_path: Path) -> None:
    """Trap 5: detail answers 200 with items:[] rather than 404. The posting must leave
    `listed_ids` so apply_board closes it, exactly as SmartRecruiters treats active:false."""
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, content=_fx("list_normal.json")))
    _mock_all_details()
    respx.get(_detail_url("1002")).mock(
        return_value=httpx.Response(200, content=_fx("detail_gone.json"))
    )

    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())

    assert snapshot.listed_ids == frozenset({"1001", "1003"})
    assert {p.provider_posting_id for p in snapshot.postings} == {"1001", "1003"}
    # not an error: a withdrawn posting is a normal event
    assert snapshot.status == "complete"


@respx.mock
def test_one_failed_detail_is_partial_and_keeps_the_rest(tmp_path: Path) -> None:
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, content=_fx("list_normal.json")))
    _mock_all_details()
    respx.get(_detail_url("1002")).mock(return_value=httpx.Response(500))

    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())

    assert snapshot.status == "partial"
    assert {p.provider_posting_id for p in snapshot.postings} == {"1001", "1003"}
    # a TRANSPORT failure is not evidence the posting is gone, so it stays in the inventory
    assert snapshot.listed_ids == frozenset({"1001", "1002", "1003"})
    assert snapshot.error is not None and "1002" in snapshot.error


@respx.mock
def test_a_malformed_detail_body_is_a_failure_not_a_withdrawal(tmp_path: Path) -> None:
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, content=_fx("list_normal.json")))
    _mock_all_details()
    respx.get(_detail_url("1002")).mock(
        return_value=httpx.Response(200, content=b"<html>maintenance</html>")
    )

    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())

    assert snapshot.status == "partial"
    assert snapshot.listed_ids == frozenset({"1001", "1002", "1003"})
    assert snapshot.error is not None and "malformed payload" in snapshot.error


@respx.mock
def test_every_detail_failing_fails_the_whole_board(tmp_path: Path) -> None:
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, content=_fx("list_normal.json")))
    for row in _rows():
        respx.get(_detail_url(row["Id"])).mock(return_value=httpx.Response(500))

    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())

    assert snapshot.status == "failed"
    assert snapshot.postings == []


@respx.mock
def test_a_dead_list_endpoint_fails_without_raising(tmp_path: Path) -> None:
    respx.get(LIST_URL).mock(return_value=httpx.Response(404))

    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())

    assert snapshot.status == "failed"
    assert snapshot.postings == []


@respx.mock
def test_an_unreachable_host_fails_without_raising(tmp_path: Path) -> None:
    respx.get(LIST_URL).mock(side_effect=httpx.ConnectError("no route"))

    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())

    assert snapshot.status == "failed"
    assert snapshot.error is not None


@respx.mock
def test_a_non_json_body_fails_rather_than_raising(tmp_path: Path) -> None:
    respx.get(LIST_URL).mock(
        return_value=httpx.Response(200, content=b"<html>maintenance</html>")
    )

    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())

    assert snapshot.status == "failed"
    assert snapshot.error is not None and "items" in snapshot.error


@respx.mock
def test_a_304_is_unchanged(tmp_path: Path) -> None:
    # Unreachable against the live service (it sends no validators and answers no-store);
    # kept for symmetry with every other provider and exercised only by this mock.
    respx.get(LIST_URL).mock(return_value=httpx.Response(304))

    snapshot = provider.fetch_board(
        _fetcher(tmp_path), _request(validators=ResponseValidators(etag='W/"abc"'))
    )

    assert snapshot.status == "unchanged"
    assert snapshot.postings == []


@respx.mock
def test_a_malformed_stored_slug_fails_without_raising(tmp_path: Path) -> None:
    request = BoardRequest(provider="oraclehcm", slug="not-a-pair", url=LIST_URL)

    snapshot = provider.fetch_board(_fetcher(tmp_path), request)

    assert snapshot.status == "failed"
    assert snapshot.error is not None and "invalid oraclehcm slug" in snapshot.error


@respx.mock
def test_id_less_rows_are_excluded_from_the_enumeration(tmp_path: Path) -> None:
    payload = _fx_json("list_normal.json")
    payload["items"][0]["requisitionList"][1]["Id"] = None
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, json=payload))
    _mock_all_details()

    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())

    # board_reported_total - board_enumerated must read as a LISTING shortfall (2 of 3)
    assert snapshot.board_enumerated == 2
    assert snapshot.board_reported_total == 3
    assert snapshot.listed_ids == frozenset({"1001", "1003"})
    assert snapshot.status == "partial"


# ------------------------------------------------------------------------ healthcheck


@respx.mock
def test_healthcheck_ok(tmp_path: Path) -> None:
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, content=_fx("list_normal.json")))
    assert provider.healthcheck(_fetcher(tmp_path), SLUG) == BoardHealth.OK


@respx.mock
def test_healthcheck_empty(tmp_path: Path) -> None:
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, content=_fx("list_empty.json")))
    assert provider.healthcheck(_fetcher(tmp_path), SLUG) == BoardHealth.EMPTY


@respx.mock
def test_healthcheck_never_reports_dead_because_a_typo_serves_a_real_board(
    tmp_path: Path,
) -> None:
    """Trap 4. An unknown siteNumber returns the host's DEFAULT board, so a 404 here is a
    CDN/WAF blip or an API change — never the dead-board signature. Classifying it DEAD
    would retire a live company on a transient edge failure."""
    respx.get(LIST_URL).mock(return_value=httpx.Response(404))
    assert provider.healthcheck(_fetcher(tmp_path), SLUG) == BoardHealth.ERROR


@respx.mock
def test_healthcheck_unreachable_on_a_transport_failure(tmp_path: Path) -> None:
    respx.get(LIST_URL).mock(side_effect=httpx.ConnectError("no route"))
    assert provider.healthcheck(_fetcher(tmp_path), SLUG) == BoardHealth.UNREACHABLE


@respx.mock
def test_healthcheck_error_on_a_missing_requisition_list(tmp_path: Path) -> None:
    respx.get(LIST_URL).mock(
        return_value=httpx.Response(200, content=_fx("list_no_expand.json"))
    )
    assert provider.healthcheck(_fetcher(tmp_path), SLUG) == BoardHealth.ERROR


def test_healthcheck_errors_on_a_malformed_slug_without_raising(tmp_path: Path) -> None:
    assert provider.healthcheck(_fetcher(tmp_path), "not-a-pair") == BoardHealth.ERROR
