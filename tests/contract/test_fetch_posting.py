"""`fetch_posting` for the five providers `postings refetch` repairs (T210).

WHAT THESE DEFEND. Each `fetch_posting` must hand `apply_refetched` the SAME `RawPosting` a board
scan of that posting would — the whole point of the repair is that the stored row ends up as the
board would have written it — so the central assertion per provider is equality with the scan's
own output over the same pinned fixtures (`tests/fixtures/<provider>/`, whose shapes the provider
contract suites already hold to the live API). Plus the two `None` paths, which must never be
confused with a fetch failure, and the seam's typed refusal for a provider with no refetch.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from boardwatch.core.models import BoardRequest, RawPosting
from boardwatch.core.politeness import Fetcher, FetchFailure
from boardwatch.core.settings import Settings
from boardwatch.providers.ashby import AshbyProvider
from boardwatch.providers.base import RefetchUnsupported, posting_refetcher
from boardwatch.providers.eightfold import EightfoldProvider
from boardwatch.providers.greenhouse import GreenhouseProvider
from boardwatch.providers.lever import LeverProvider
from boardwatch.providers.smartrecruiters import SmartRecruitersProvider
from boardwatch.providers.workday import WorkdayProvider

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _fx(provider: str, name: str) -> Any:
    return json.loads((FIXTURES / provider / name).read_text(encoding="utf-8"))


def _fetcher(tmp_path: Path) -> Fetcher:
    return Fetcher(
        Settings(
            data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1,
            per_host_delay_seconds=0.25,
        )
    )


def _scanned(provider: Any, fetcher: Fetcher, slug: str, pid: str, **kw: Any) -> RawPosting:
    snapshot = provider.fetch_board(
        fetcher, BoardRequest(provider=provider.name, slug=slug, url=provider.board_url(slug), **kw)
    )
    return next(p for p in snapshot.postings if p.provider_posting_id == pid)


# ---------------------------------------------------------------- the seam


def test_a_provider_without_fetch_posting_is_a_typed_refusal() -> None:
    with pytest.raises(RefetchUnsupported):
        posting_refetcher(LeverProvider())


@pytest.mark.parametrize(
    "provider",
    [
        GreenhouseProvider(), AshbyProvider(), SmartRecruitersProvider(), WorkdayProvider(),
        EightfoldProvider(),
    ],
)
def test_the_five_damaged_providers_refetch(provider: Any) -> None:
    assert posting_refetcher(provider) is provider


# ---------------------------------------------------------------- greenhouse

GH_JOB = (
    "https://boards-api.greenhouse.io/v1/boards/acme/jobs/6000001"
    "?questions=false&pay_transparency=true"
)


@respx.mock
def test_greenhouse_single_job_parses_as_the_listing_does(tmp_path: Path) -> None:
    listing = _fx("greenhouse", "normal.json")
    job = listing["jobs"][0]
    # The single-job endpoint serves the listing's job object; that is the fixture's shape.
    respx.get(GH_JOB).mock(return_value=httpx.Response(200, json=job))
    respx.get(GreenhouseProvider().board_url("acme")).mock(
        return_value=httpx.Response(200, json=listing)
    )
    fetcher = _fetcher(tmp_path)
    got = GreenhouseProvider().fetch_posting(fetcher, "acme", "6000001")
    assert got == _scanned(GreenhouseProvider(), fetcher, "acme", "6000001")
    assert got is not None and got.body_text and got.raw_json == job


@respx.mock
def test_greenhouse_404_is_gone_and_500_is_a_failure(tmp_path: Path) -> None:
    respx.get(GH_JOB).mock(
        return_value=httpx.Response(404, json=_fx("greenhouse", "dead_404.json"))
    )
    assert GreenhouseProvider().fetch_posting(_fetcher(tmp_path), "acme", "6000001") is None
    respx.get(GH_JOB).mock(return_value=httpx.Response(500))
    with pytest.raises(FetchFailure):
        GreenhouseProvider().fetch_posting(_fetcher(tmp_path), "acme", "6000001")


# ---------------------------------------------------------------- ashby


@respx.mock
def test_ashby_filters_the_listing_to_the_id(tmp_path: Path) -> None:
    respx.get(AshbyProvider().board_url("acme")).mock(
        return_value=httpx.Response(200, json=_fx("ashby", "normal.json"))
    )
    fetcher = _fetcher(tmp_path)
    got = AshbyProvider().fetch_posting(fetcher, "acme", "ashby-0003")
    assert got is not None and got.provider_posting_id == "ashby-0003"
    assert got == _scanned(AshbyProvider(), fetcher, "acme", "ashby-0003")
    # An id the board no longer lists — including a job-apps `pst_` reference — is gone.
    assert AshbyProvider().fetch_posting(fetcher, "acme", "pst_e52dc285a941f3e617481afb") is None


# ---------------------------------------------------------------- smartrecruiters

SR_DETAIL = "https://api.smartrecruiters.com/v1/companies/acme/postings/744000000000001"


@respx.mock
def test_smartrecruiters_detail_parses_as_the_scan_does(tmp_path: Path) -> None:
    detail = _fx("smartrecruiters", "detail_normal.json")
    respx.get(SR_DETAIL).mock(return_value=httpx.Response(200, json=detail))
    respx.get(SmartRecruitersProvider().board_url("acme")).mock(
        return_value=httpx.Response(200, json=_fx("smartrecruiters", "list_normal.json"))
    )
    fetcher = _fetcher(tmp_path)
    got = SmartRecruitersProvider().fetch_posting(fetcher, "acme", "744000000000001")
    scanned = _scanned(
        SmartRecruitersProvider(), fetcher, "acme", "744000000000001",
        known_posting_ids=frozenset({"744000000000002", "744000000000003"}),
    )
    assert got is not None
    # Every parsed field agrees; only `raw_json["listed"]` differs (the detail stands in for it).
    assert got.model_copy(update={"raw_json": {}}) == scanned.model_copy(update={"raw_json": {}})
    assert got.raw_json["detail"] == scanned.raw_json["detail"] == detail


@respx.mock
def test_smartrecruiters_inactive_or_404_is_gone(tmp_path: Path) -> None:
    respx.get(SR_DETAIL).mock(
        return_value=httpx.Response(200, json=_fx("smartrecruiters", "detail_inactive.json"))
    )
    sr = SmartRecruitersProvider()
    assert sr.fetch_posting(_fetcher(tmp_path), "acme", "744000000000001") is None
    respx.get(SR_DETAIL).mock(return_value=httpx.Response(404))
    assert sr.fetch_posting(_fetcher(tmp_path), "acme", "744000000000001") is None


# ---------------------------------------------------------------- workday

WD_SLUG = "acme.wd5.myworkdayjobs.com/acme/AcmeCareers"
WD_SEARCH = "https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/AcmeCareers/jobs"
WD_PID = "JR1000002"
WD_PATH = "/job/Santa-Clara-CA/Compiler-Intern-Summer-2027_JR1000002"


@respx.mock
def test_workday_searches_the_id_then_reads_its_detail(tmp_path: Path) -> None:
    search = respx.post(WD_SEARCH).mock(
        return_value=httpx.Response(200, json=_fx("workday", "list_normal.json"))
    )
    respx.get(f"https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/AcmeCareers{WD_PATH}").mock(
        return_value=httpx.Response(200, json=_fx("workday", "detail_normal.json"))
    )
    fetcher = _fetcher(tmp_path)
    got = WorkdayProvider().fetch_posting(fetcher, WD_SLUG, WD_PID)
    assert json.loads(search.calls[0].request.content)["searchText"] == WD_PID
    scanned = _scanned(
        WorkdayProvider(), fetcher, WD_SLUG, WD_PID,
        known_posting_ids=frozenset({"JR1000001-1", "JR1000003"}),
    )
    # The search row IS the listed row a scan would have: byte-identical, raw_json included.
    assert got == scanned
    # The scan's own search body is untouched by the new parameter.
    assert json.loads(search.calls[1].request.content)["searchText"] == ""


@respx.mock
def test_workday_keys_on_the_exact_id_not_a_search_hit(tmp_path: Path) -> None:
    """A full-text search returns near misses; `JR100000` must not resolve to `JR1000002`."""
    respx.post(WD_SEARCH).mock(
        return_value=httpx.Response(200, json=_fx("workday", "list_normal.json"))
    )
    assert WorkdayProvider().fetch_posting(_fetcher(tmp_path), WD_SLUG, "JR100000") is None


@respx.mock
def test_workday_detail_404_is_gone(tmp_path: Path) -> None:
    respx.post(WD_SEARCH).mock(
        return_value=httpx.Response(200, json=_fx("workday", "list_normal.json"))
    )
    respx.get(f"https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/AcmeCareers{WD_PATH}").mock(
        return_value=httpx.Response(404, json=_fx("workday", "dead_s21.json"))
    )
    assert WorkdayProvider().fetch_posting(_fetcher(tmp_path), WD_SLUG, WD_PID) is None


# ---------------------------------------------------------------- eightfold

EF_SLUG = "careers.acme.test"
EF_DETAIL = (
    "https://careers.acme.test/api/pcsx/position_details"
    "?domain=acme.test&position_id=1000000000001"
)


def _boot_html() -> bytes:
    """The career page's boot blob in the recorded shape (`test_eightfold._boot_html`)."""
    escaped = json.dumps({"domain": "acme.test"}).replace('"', "&#34;")
    return b'<html><body><code id="pcsx-data">' + escaped.encode() + b"</code></body></html>"


@respx.mock
def test_eightfold_bootstraps_then_reads_the_detail(tmp_path: Path) -> None:
    detail = _fx("eightfold", "detail_normal.json")
    respx.get(f"https://{EF_SLUG}/careers").mock(
        return_value=httpx.Response(200, content=_boot_html())
    )
    respx.get(EF_DETAIL).mock(return_value=httpx.Response(200, json=detail))
    respx.get(url__startswith=f"https://{EF_SLUG}/api/pcsx/search").mock(
        side_effect=lambda request: httpx.Response(
            200,
            json=_fx("eightfold", "search_normal.json")
            if request.url.params["start"] == "0"
            else {"status": 200, "data": {"positions": []}},
        )
    )
    fetcher = _fetcher(tmp_path)
    got = EightfoldProvider().fetch_posting(fetcher, EF_SLUG, "1000000000001")
    scanned = _scanned(
        EightfoldProvider(), fetcher, EF_SLUG, "1000000000001",
        known_posting_ids=frozenset({"1000000000002", "1000000000003", "1000000000004"}),
    )
    assert got is not None
    assert got.model_copy(update={"raw_json": {}}) == scanned.model_copy(update={"raw_json": {}})
    assert got.raw_json["detail"] == scanned.raw_json["detail"] == detail["data"]


@respx.mock
def test_eightfold_detail_404_is_gone(tmp_path: Path) -> None:
    respx.get(f"https://{EF_SLUG}/careers").mock(
        return_value=httpx.Response(200, content=_boot_html())
    )
    respx.get(EF_DETAIL).mock(
        return_value=httpx.Response(404, json=_fx("eightfold", "detail_not_found.json"))
    )
    assert EightfoldProvider().fetch_posting(_fetcher(tmp_path), EF_SLUG, "1000000000001") is None
