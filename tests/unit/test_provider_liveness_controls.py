"""Provider liveness controls: SmartRecruiters, Eightfold and ADP (D-684).

Every control under `tests/unit/provider_liveness_controls/` is a trimmed capture of a public,
unauthenticated response, taken 2026-11-09 from a posting whose state an INDEPENDENT oracle
already knew (each control names it): the scanner's own listing-absence close, the board's
latest complete scan, or the tenant's public listing. The expected verdicts here come from the
control's recorded fields, which the capture script wrote from the raw response, never from
re-running the detector.

What is pinned:

- the control matrix itself meets the bar (>=3 closed and >=3 open controls from >=2 tenants);
- the manifest fingerprints match, so a fixture cannot be edited to make a detector pass;
- every captured closed control that the signal can see is `dead`, no open control is, and the
  closed controls the signal cannot see are NOT read as `alive` or `dead` (they are misses);
- an access wall (403, 429, a challenge page, a CDN 404) is `unknown`, never `dead`;
- the new signals are only reachable through their own typed shape, never a substring.

Dayforce is deliberately absent: it did not meet the bar (D-684), so no rule exists to test.
No network: respx stands in for the host, behind the real `Fetcher`.
"""

from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from boardwatch.core.liveness import (
    verdict_for_adp_requisition,
    verdict_for_eightfold_position,
    verdict_for_smartrecruiters_posting,
)
from boardwatch.core.settings import Settings
from boardwatch.pipeline.liveness import build_prober

FIXTURES = Path(__file__).parent / "provider_liveness_controls"
PROVIDERS = ("smartrecruiters", "eightfold", "adp")
FILES: dict[str, dict[str, Any]] = {
    name: json.loads((FIXTURES / f"{name}.json").read_text()) for name in PROVIDERS
}
ENTRIES: list[dict[str, Any]] = [c for name in PROVIDERS for c in FILES[name]["controls"]]


def _entries(provider: str) -> list[dict[str, Any]]:
    return [e for e in ENTRIES if e["provider"] == provider]


def _payload(entry: dict[str, Any]) -> dict[str, Any]:
    return entry["payload"]  # type: ignore[no-any-return]


def _raw(entry: dict[str, Any]) -> bytes:
    """The captured (trimmed) body as the bytes a response would carry."""
    return json.dumps(entry["payload"]).encode()


def _ids(entries: list[dict[str, Any]]) -> list[str]:
    return [f"{e['tenant']}-{e['posting_id']}-{e['oracle']}" for e in entries]


def _settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path, config_dir=tmp_path, per_host_delay_seconds=0.25)


WALL = b"<html><head><title>Request Blocked</title></head><body>Request Blocked</body></html>"
CHALLENGE = b"<html><title>Just a moment...</title><div id='cf-chl-widget'></div></html>"


# --- the fixtures are what they say they are ----------------------------------------------


def test_every_control_matches_its_recorded_fingerprint() -> None:
    assert {p.name for p in FIXTURES.iterdir()} == {f"{name}.json" for name in PROVIDERS}
    for entry in ENTRIES:
        canonical = json.dumps(entry["payload"], sort_keys=True, separators=(",", ":")).encode()
        label = f"{entry['provider']}/{entry['tenant']}/{entry['posting_id']}"
        assert hashlib.sha256(canonical).hexdigest() == entry["body_sha256"], label
        assert entry["captured_at"].startswith("2026-11-09"), label
        assert entry["http_status"] in (200, 404), label


@pytest.mark.parametrize("provider", ["smartrecruiters", "eightfold", "adp"])
def test_the_control_matrix_meets_the_bar(provider: str) -> None:
    """>=3 known-closed and >=3 known-open from >=2 tenants. A control the store called open
    but that answered gone ~9h after its scan (`open-at-scan-stale`) counts as CLOSED, never as
    an open control it failed to be."""
    entries = _entries(provider)
    closed = [e for e in entries if e["oracle"] in ("closed", "closed-manual", "open-at-scan-stale")]
    opened = [e for e in entries if e["oracle"] == "open"]
    assert len(closed) >= 3 and len(opened) >= 3
    assert len({e["tenant"] for e in closed}) >= 2 and len({e["tenant"] for e in opened}) >= 2


def test_the_matrix_size_is_the_measured_one() -> None:
    """The report quotes these counts; a fixture added or dropped must change them on purpose."""
    counts = {
        (p, o): sum(1 for e in _entries(p) if e["oracle"] == o)
        for p in ("smartrecruiters", "eightfold", "adp")
        for o in ("closed", "open")
    }
    assert counts == {
        ("smartrecruiters", "closed"): 10,
        ("smartrecruiters", "open"): 8,
        ("eightfold", "closed"): 10,
        ("eightfold", "open"): 9,
        ("adp", "closed"): 6,
        ("adp", "open"): 6,
    }


# --- SmartRecruiters: `active: false` on the exact posting --------------------------------


def _sr_verdict(entry: dict[str, Any], status: int = 200, body: bytes | None = None, **kw: Any) -> Any:
    raw = body if body is not None else _raw(entry)
    return verdict_for_smartrecruiters_posting(
        1, status, raw, posting_ref=entry["posting_id"], **kw
    )


@pytest.mark.parametrize("entry", _entries("smartrecruiters"), ids=_ids(_entries("smartrecruiters")))
def test_smartrecruiters_active_false_separates_the_captured_controls(entry: dict[str, Any]) -> None:
    result = _sr_verdict(entry)
    if entry["detector_expected"] == "dead":
        assert entry["oracle"] in ("closed", "closed-manual")
        assert (result.verdict, result.signal) == ("dead", "smartrecruiters_inactive")
    else:
        # Zero false deaths on the open controls, and the closed ones that answer `active: true`
        # are recorded MISSES: no verdict at all, and in particular not `alive`, which on the
        # death-probe path would clear earned strikes.
        assert result.verdict == "unknown"


def test_smartrecruiters_misses_are_four_of_eleven_closed_controls() -> None:
    misses = [e for e in _entries("smartrecruiters") if e["oracle"].startswith("closed") and e["detector_expected"] != "dead"]
    seen = [e for e in _entries("smartrecruiters") if e["oracle"].startswith("closed")]
    assert (len(misses), len(seen)) == (4, 11)
    assert {e["tenant"] for e in misses} >= {"abbvie", "cityofnewyork", "northwesternmedicine"}


def test_a_smartrecruiters_answer_for_another_posting_id_is_not_this_postings_death() -> None:
    closed = next(e for e in _entries("smartrecruiters") if e["detector_expected"] == "dead")
    other = _sr_verdict({**closed, "posting_id": "744000000000000"})
    assert other.verdict == "unknown"


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (403, WALL),
        (429, b"Too Many Requests"),
        (503, b""),
        (200, WALL),
        (200, CHALLENGE),
        (200, b'{"active": false}'),  # no id: not this posting's record
        (200, b'{"id": "744000158460929", "active": "false"}'),  # a string is not the field
        (200, b'{"id": "744000158460929"}'),
        (404, b'{"active": false, "id": "744000158460929"}'),
        (200, b"[]"),
    ],
)
def test_smartrecruiters_access_walls_and_loose_shapes_are_unknown(status: int, body: bytes) -> None:
    entry = {"posting_id": "744000158460929"}
    assert _sr_verdict(entry, status, body).verdict == "unknown"


def test_a_smartrecruiters_inactive_flag_reached_through_a_redirect_is_served() -> None:
    closed = next(e for e in _entries("smartrecruiters") if e["detector_expected"] == "dead")
    result = _sr_verdict(closed, redirected=True)
    assert (result.verdict, result.signal) == ("unknown", "refetch_gone_after_redirect")


def test_smartrecruiters_posting_target_maps_the_exact_shape_only() -> None:
    from boardwatch.providers.smartrecruiters import posting_api_target  # noqa: PLC0415

    page = "https://jobs.smartrecruiters.com/AECOM2/744000158460929-acoustics-noise-consultant"
    api = "https://api.smartrecruiters.com/v1/companies/aecom2/postings/744000158460929"
    assert posting_api_target(page) == (api, "744000158460929")
    assert posting_api_target(page + "?utm_source=Simplify&ref=Simplify") == (api, "744000158460929")
    assert posting_api_target("https://jobs.smartrecruiters.com/AECOM2/744000158460929") == (
        api,
        "744000158460929",
    )
    for bad in (
        "https://jobs.smartrecruiters.com/AECOM2",
        "https://jobs.smartrecruiters.com/AECOM2/abc",
        "https://jobs.smartrecruiters.com/AECOM2/744000158460929/apply",
        "https://jobs.smartrecruiters.com/a%2Fb/744000158460929",
        "https://jobs.smartrecruiters.com/a b/744000158460929",
        "https://evil.example/AECOM2/744000158460929",
        "https://jobs.smartrecruiters.com.evil.example/AECOM2/744000158460929",
        "https://careers.example/redirect?u=jobs.smartrecruiters.com/AECOM2/744000158460929",
    ):
        assert posting_api_target(bad) is None, bad


def _sr_urls(entry: dict[str, Any]) -> tuple[str, str]:
    page = f"https://jobs.smartrecruiters.com/{entry['tenant'].title()}/{entry['posting_id']}-role"
    api = f"https://api.smartrecruiters.com/v1/companies/{entry['tenant']}/postings/{entry['posting_id']}"
    return page, api


@pytest.mark.parametrize("entry", _entries("smartrecruiters"), ids=_ids(_entries("smartrecruiters")))
@respx.mock
def test_the_production_prober_reads_the_smartrecruiters_flag_before_the_page(
    tmp_path: Path, entry: dict[str, Any]
) -> None:
    page_url, api_url = _sr_urls(entry)
    page = respx.get(page_url).mock(return_value=httpx.Response(200, content=b"<html>apply</html>"))
    api = respx.get(api_url).mock(
        return_value=httpx.Response(200, content=_raw(entry))
    )

    result = build_prober(_settings(tmp_path))(7, page_url)

    assert api.call_count == 1
    assert api.calls[0].request.headers["accept"] == "application/json"
    if entry["detector_expected"] == "dead":
        assert (result.verdict, result.signal) == ("dead", "smartrecruiters_inactive")
        assert not page.called
    else:
        # Not decided by the flag: today's page probe answers, exactly as before this change.
        assert page.call_count == 1
        assert result.verdict == "alive"


@respx.mock
def test_a_smartrecruiters_api_wall_falls_back_to_the_page_and_never_closes(tmp_path: Path) -> None:
    entry = next(e for e in _entries("smartrecruiters") if e["detector_expected"] == "dead")
    page_url, api_url = _sr_urls(entry)
    respx.get(api_url).mock(return_value=httpx.Response(403, content=WALL))
    respx.get(page_url).mock(return_value=httpx.Response(403, content=WALL))

    result = build_prober(_settings(tmp_path))(7, page_url)

    assert (result.verdict, result.signal) == ("unknown", "refetch_error")


@respx.mock
def test_a_smartrecruiters_api_redirect_does_not_close(tmp_path: Path) -> None:
    entry = next(e for e in _entries("smartrecruiters") if e["detector_expected"] == "dead")
    page_url, api_url = _sr_urls(entry)
    respx.get(api_url).mock(
        return_value=httpx.Response(302, headers={"location": "https://api.smartrecruiters.com/v1/other"})
    )
    respx.get("https://api.smartrecruiters.com/v1/other").mock(
        return_value=httpx.Response(200, content=_raw(entry))
    )
    respx.get(page_url).mock(return_value=httpx.Response(200, content=b"<html>apply</html>"))

    assert build_prober(_settings(tmp_path))(7, page_url).verdict != "dead"


# --- Eightfold: `position_details` answering 404 `Position not found` ---------------------


def _ef_body(entry: dict[str, Any]) -> bytes:
    return json.dumps(_payload(entry)["position_details"]).encode()


def _ef_verdict(entry: dict[str, Any], status: int | None = None, body: bytes | None = None, **kw: Any) -> Any:
    st = status if status is not None else _payload(entry)["position_details"]["status"]
    return verdict_for_eightfold_position(
        1, st, body if body is not None else _ef_body(entry), position_id=entry["posting_id"], **kw
    )


@pytest.mark.parametrize("entry", _entries("eightfold"), ids=_ids(_entries("eightfold")))
def test_eightfold_position_not_found_separates_the_captured_controls(entry: dict[str, Any]) -> None:
    result = _ef_verdict(entry)
    if entry["oracle"] == "open":
        assert (result.verdict, result.signal) == ("alive", "refetch_ok")
    else:
        assert entry["oracle"] in ("closed", "open-at-scan-stale")
        assert (result.verdict, result.signal) == ("dead", "eightfold_unposted")


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (404, WALL),  # a CDN or WAF 404 page is not the application's answer
        (404, b""),
        (404, b'{"status": 404, "error": {"message": "Something else"}, "data": {}}'),
        (404, b'{"status": 500, "error": {"message": "Position not found"}, "data": {}}'),
        (403, WALL),
        (429, b"slow down"),
        (503, b""),
        (200, WALL),
        (200, CHALLENGE),
        (200, b'{"status": 200, "data": {}}'),
        (200, b'{"status": 200, "data": {"id": 999}}'),  # another position
        (200, b"[]"),
    ],
)
def test_eightfold_access_walls_and_loose_shapes_are_unknown(status: int, body: bytes) -> None:
    result = verdict_for_eightfold_position(1, status, body, position_id="1340074623482")
    assert result.verdict == "unknown"


def test_the_eightfold_not_found_body_is_read_as_fields_not_as_text() -> None:
    sneaky = b"<p>Position not found</p>"
    assert verdict_for_eightfold_position(1, 404, sneaky, position_id="1").verdict == "unknown"


def test_an_eightfold_not_found_reached_through_a_redirect_is_served() -> None:
    entry = next(e for e in _entries("eightfold") if e["oracle"] == "closed")
    result = _ef_verdict(entry, redirected=True)
    assert (result.verdict, result.signal) == ("unknown", "refetch_gone_after_redirect")


def test_eightfold_position_target_maps_the_exact_shape_only() -> None:
    from boardwatch.providers.eightfold import position_page_target  # noqa: PLC0415

    ok = "https://jobs.northropgrumman.com/careers/job/1340074623482"
    assert position_page_target(ok) == ("jobs.northropgrumman.com", "1340074623482")
    assert position_page_target(ok + "?domain=ngc.com&hl=en") == ("jobs.northropgrumman.com", "1340074623482")
    for bad in (
        "https://jobs.northropgrumman.com/careers/job/abc",
        "https://jobs.northropgrumman.com/careers/job/1340074623482/apply",
        "https://jobs.northropgrumman.com/careers?pid=1340074623482",
        "https://jobs.northropgrumman.com/careers/job",
        "http://jobs.northropgrumman.com/careers/job/1340074623482",
        "https://user" + "@jobs.northropgrumman.com/careers/job/1340074623482",
        "https://jobs.northropgrumman.com:8443/careers/job/1340074623482",
    ):
        assert position_page_target(bad) is None, bad


def _ef_pages(entry: dict[str, Any]) -> tuple[str, str, bytes]:
    page_url = entry["page_url"]
    host = page_url.split("/")[2]
    domain = _payload(entry)["career_page"]["pcsx_domain"]
    api_url = f"https://{host}/api/pcsx/position_details?domain={domain}&position_id={entry['posting_id']}"
    blob = html.escape(json.dumps({"domain": domain}), quote=True)
    page = f'<html><title>x</title><code id="pcsx-data" style="display:none">{blob}</code></html>'.encode()
    return page_url, api_url, page


@pytest.mark.parametrize("entry", _entries("eightfold"), ids=_ids(_entries("eightfold")))
@respx.mock
def test_the_production_prober_asks_eightfold_position_details_with_the_pages_domain(
    tmp_path: Path, entry: dict[str, Any]
) -> None:
    page_url, api_url, page_body = _ef_pages(entry)
    page = respx.get(page_url).mock(return_value=httpx.Response(200, content=page_body))
    status = _payload(entry)["position_details"]["status"]
    api = respx.get(api_url).mock(return_value=httpx.Response(status, content=_ef_body(entry)))

    result = build_prober(_settings(tmp_path))(7, page_url)

    assert page.call_count == 1 and api.call_count == 1
    assert api.calls[0].request.headers["accept"] == "application/json"
    expected = ("alive", "refetch_ok") if entry["oracle"] == "open" else ("dead", "eightfold_unposted")
    assert (result.verdict, result.signal) == expected


@respx.mock
def test_an_eightfold_career_page_wall_is_unknown_and_asks_nothing_more(tmp_path: Path) -> None:
    entry = next(e for e in _entries("eightfold") if e["oracle"] == "closed")
    page_url, api_url, _ = _ef_pages(entry)
    respx.get(page_url).mock(return_value=httpx.Response(403, content=WALL))
    api = respx.get(api_url).mock(return_value=httpx.Response(404, content=_ef_body(entry)))

    result = build_prober(_settings(tmp_path))(7, page_url)

    assert (result.verdict, result.signal) == ("unknown", "refetch_error")
    assert not api.called


@respx.mock
def test_an_eightfold_page_without_a_boot_blob_keeps_todays_page_reading(tmp_path: Path) -> None:
    entry = next(e for e in _entries("eightfold") if e["oracle"] == "closed")
    page_url, api_url, _ = _ef_pages(entry)
    respx.get(page_url).mock(return_value=httpx.Response(200, content=b"<html>an employer page</html>"))
    api = respx.get(api_url).mock(return_value=httpx.Response(404, content=_ef_body(entry)))

    result = build_prober(_settings(tmp_path))(7, page_url)

    assert (result.verdict, result.signal) == ("alive", "refetch_ok")
    assert not api.called


@pytest.mark.parametrize(
    ("status", "body"),
    [(403, WALL), (404, WALL), (429, b"x"), (200, CHALLENGE)],
)
@respx.mock
def test_an_eightfold_position_details_wall_is_unknown(tmp_path: Path, status: int, body: bytes) -> None:
    entry = next(e for e in _entries("eightfold") if e["oracle"] == "closed")
    page_url, api_url, page_body = _ef_pages(entry)
    respx.get(page_url).mock(return_value=httpx.Response(200, content=page_body))
    respx.get(api_url).mock(return_value=httpx.Response(status, content=body))

    assert build_prober(_settings(tmp_path))(7, page_url).verdict == "unknown"


# --- ADP: the requisition resource answering an empty requisition -------------------------


def _adp_verdict(entry: dict[str, Any], body: bytes | None = None, status: int = 200, **kw: Any) -> Any:
    return verdict_for_adp_requisition(
        1, status, body if body is not None else _raw(entry), **kw
    )


@pytest.mark.parametrize("entry", _entries("adp"), ids=_ids(_entries("adp")))
def test_adp_empty_requisition_separates_the_captured_controls(entry: dict[str, Any]) -> None:
    result = _adp_verdict(entry)
    expected = ("dead", "adp_unposted") if entry["oracle"] == "closed" else ("alive", "refetch_ok")
    assert (result.verdict, result.signal) == expected


EMPTY_REQUISITION = {
    "postingInstructions": [],
    "links": [],
    "organizationalUnits": [],
    "requisitionLocations": [],
    "screeningRequirements": [],
    "sponsoredVisaTypeCodes": [],
}


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (403, WALL),
        (429, b"x"),
        (404, json.dumps(EMPTY_REQUISITION).encode()),
        (200, WALL),
        (200, CHALLENGE),
        (200, b"{}"),
        (200, b"[]"),
        (200, json.dumps({**EMPTY_REQUISITION, "requisitionLocations": [{"x": 1}]}).encode()),
        (200, json.dumps({**EMPTY_REQUISITION, "extra": []}).encode()),
        (200, json.dumps({k: v for k, v in EMPTY_REQUISITION.items() if k != "links"}).encode()),
    ],
)
def test_adp_walls_and_loose_shapes_are_unknown(status: int, body: bytes) -> None:
    result = verdict_for_adp_requisition(1, status, body)
    assert result.verdict == "unknown"


def test_an_adp_empty_requisition_reached_through_a_redirect_is_served() -> None:
    entry = next(e for e in _entries("adp") if e["oracle"] == "closed")
    result = _adp_verdict(entry, redirected=True)
    assert (result.verdict, result.signal) == ("unknown", "refetch_gone_after_redirect")


ADP_CID = "6bab2611-6eca-4dda-bd57-f4dea7b477ff"
ADP_PAGE = (
    "https://workforcenow.adp.com/mascsr/default/mdf/recruitment/recruitment.html"
    f"?cid={ADP_CID}&ccId=19000101_000001&jobId=630511&lang=en_US"
)
ADP_API = (
    "https://workforcenow.adp.com/mascsr/default/careercenter/public/events/staffing/v1/"
    f"job-requisitions/630511?cid={ADP_CID}&ccId=19000101_000001&lang=en_US&locale=en_US"
)


def test_adp_requisition_url_maps_the_measured_shape_only() -> None:
    from boardwatch.providers.adp import requisition_url_for_page  # noqa: PLC0415

    assert requisition_url_for_page(ADP_PAGE) == ADP_API
    # Aggregator tracking parameters are not identity.
    assert requisition_url_for_page(ADP_PAGE.replace("&lang=en_US", "&source=IN&lang=en_US")) == ADP_API
    for bad in (
        ADP_PAGE.replace("19000101_000001", "9200970237951_3"),  # a career center never measured
        ADP_PAGE.replace("workforcenow.adp.com", "workforcenow.cloud.adp.com"),
        ADP_PAGE.replace("workforcenow.adp.com", "workforcenow.adp.com.evil.example"),
        ADP_PAGE.replace("jobId=630511", "jobId=abc"),
        ADP_PAGE.replace("jobId=630511", "jobId=630511%26x"),
        ADP_PAGE.replace(ADP_CID, "not-a-uuid"),
        ADP_PAGE.replace("&jobId=630511", ""),
        ADP_PAGE.replace("recruitment.html", "other.html"),
        "https://recruiting.adp.com/srccsh/public/RTI.home?r=5001226959506&c=2201039&d=ExternalCareerSite",
    ):
        assert requisition_url_for_page(bad) is None, bad


@pytest.mark.parametrize("entry", _entries("adp"), ids=_ids(_entries("adp")))
@respx.mock
def test_the_production_prober_asks_adps_requisition_resource_never_the_page(
    tmp_path: Path, entry: dict[str, Any]
) -> None:
    page = respx.get(ADP_PAGE).mock(return_value=httpx.Response(200, content=b"<html>shell</html>"))
    api = respx.get(ADP_API).mock(
        return_value=httpx.Response(200, content=_raw(entry))
    )

    result = build_prober(_settings(tmp_path))(7, ADP_PAGE)

    assert not page.called
    assert api.call_count == 1 and api.calls[0].request.headers["accept"] == "application/json"
    expected = ("dead", "adp_unposted") if entry["oracle"] == "closed" else ("alive", "refetch_ok")
    assert (result.verdict, result.signal) == expected


@pytest.mark.parametrize("status", [403, 429, 503])
@respx.mock
def test_an_adp_access_wall_is_unknown(tmp_path: Path, status: int) -> None:
    respx.get(ADP_API).mock(return_value=httpx.Response(status, content=WALL))

    result = build_prober(_settings(tmp_path))(7, ADP_PAGE)

    assert (result.verdict, result.signal) == ("unknown", "refetch_error")


@respx.mock
def test_an_unmeasured_adp_shape_keeps_the_page_probe(tmp_path: Path) -> None:
    url = ADP_PAGE.replace("19000101_000001", "9200970237951_3")
    page = respx.get(url).mock(return_value=httpx.Response(200, content=b"<html>shell</html>"))

    result = build_prober(_settings(tmp_path))(7, url)

    assert page.called and (result.verdict, result.signal) == ("alive", "refetch_ok")
