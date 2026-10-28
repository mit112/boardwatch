"""The PRODUCTION probe, driven through the real `Fetcher` (P6 item 6).

Every other liveness test injects a fake prober, which is right for the pipeline seam and blind
to the thing most likely to break: `Fetcher._send_once` raises `FetchFailure` for every non-200,
so the gone-status arrives as an exception attribute rather than a return value. If
`status_code` ever stops arriving as an `int` — a refactor, a wrapper, a provider-side change —
`status_code in GONE_STATUSES` is silently False forever and the probe finds nothing with the
whole suite green. That is this repo's silent-None class, and these tests exist for it.

respx + a real `Fetcher` is the repo's standard network seam (see `tests/contract/`).
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from boardwatch.core.settings import Settings
from boardwatch.pipeline.liveness import build_prober

URL = "https://boards.example.test/j/42"


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    return Settings(
        data_dir=tmp_path, config_dir=tmp_path, per_host_delay_seconds=0.25, **overrides
    )


@respx.mock
def test_a_404_from_the_real_fetcher_is_read_as_GONE(tmp_path: Path) -> None:  # noqa: N802
    """The path production actually takes. A 404 never reaches `verdict_for_status` — the
    Fetcher raises first — so this is the only test that proves the probe can find anything."""
    route = respx.get(URL).mock(return_value=httpx.Response(404))

    result = build_prober(_settings(tmp_path))(42, URL)

    assert result.verdict == "dead"
    assert result.signal == "refetch_gone"
    assert route.called


@respx.mock
def test_a_410_from_the_real_fetcher_is_read_as_GONE(tmp_path: Path) -> None:  # noqa: N802
    respx.get(URL).mock(return_value=httpx.Response(410))

    assert build_prober(_settings(tmp_path))(42, URL).verdict == "dead"


@respx.mock
def test_a_404_reached_THROUGH_A_REDIRECT_is_served(tmp_path: Path) -> None:  # noqa: N802
    """The client is built with `follow_redirects=True`, so this arrives as a bare `FetchFailure`
    with `status_code=404` and nothing in the message about the hop — indistinguishable, from the
    status alone, from the posting itself answering gone. An employer moving ATS whose old links
    redirect to a host with a dead deep-link path would have every live requisition withheld.

    Only the real client can prove this: the fake probers elsewhere never redirect, and reading
    `verdict_for_failure` alone shows a `redirected` flag with no evidence anything sets it."""
    respx.get(URL).mock(
        return_value=httpx.Response(302, headers={"Location": "https://new.example/careers"})
    )
    moved = respx.get("https://new.example/careers").mock(return_value=httpx.Response(404))

    result = build_prober(_settings(tmp_path))(42, URL)

    assert moved.called  # the chain really was followed, or this test proves nothing
    assert result.verdict == "unknown"
    assert result.signal == "refetch_gone_after_redirect"
    assert result.withholds is False


@respx.mock
def test_a_404_on_the_URL_ITSELF_still_withholds_after_the_redirect_rule(  # noqa: N802
    tmp_path: Path,
) -> None:
    """The other half of the pair, and the one that keeps the gate alive: forgiving redirected
    gone-statuses must not quietly forgive direct ones. `response.history` is empty here."""
    respx.get(URL).mock(return_value=httpx.Response(404))

    result = build_prober(_settings(tmp_path))(42, URL)

    assert result.verdict == "dead"
    assert result.signal == "refetch_gone"


@respx.mock
def test_a_200_is_alive(tmp_path: Path) -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, content=b"still hiring"))

    result = build_prober(_settings(tmp_path))(42, URL)

    assert result.verdict == "alive"
    assert result.signal == "refetch_ok"


@respx.mock
def test_a_403_is_UNKNOWN_and_is_served(tmp_path: Path) -> None:  # noqa: N802
    """Measured 2026-08-10: a live Pinterest posting answers 403 to an unfamiliar user agent."""
    respx.get(URL).mock(return_value=httpx.Response(403))

    result = build_prober(_settings(tmp_path))(42, URL)

    assert result.verdict == "unknown"
    assert result.withholds is False


@respx.mock
def test_a_transport_error_is_UNKNOWN_and_is_served(tmp_path: Path) -> None:  # noqa: N802
    respx.get(URL).mock(side_effect=httpx.ConnectError("refused"))

    result = build_prober(_settings(tmp_path))(42, URL)

    assert result.verdict == "unknown"
    assert result.withholds is False
    assert "refused" in result.detail  # the reason survives, so a run can be diagnosed


@respx.mock
def test_the_probe_requests_the_URL_it_was_GIVEN(tmp_path: Path) -> None:  # noqa: N802
    """The fake prober in the pipeline suite ignores its `url` argument, so nothing else pins
    the probe's only real input. Rewriting or truncating the URL would pass every other test."""
    route = respx.get(URL).mock(return_value=httpx.Response(200))

    build_prober(_settings(tmp_path))(42, URL)

    assert str(route.calls[0].request.url) == URL


@respx.mock
def test_the_probe_does_NOT_retry(tmp_path: Path) -> None:  # noqa: N802
    """`retry_attempts=1` is the docstring's whole latency argument, and 503 is in the Fetcher's
    retryable set — so with the default of 3 this route would be called three times and a
    shortlist of 20 against a sick host would cost the operator their morning."""
    route = respx.get(URL).mock(return_value=httpx.Response(503))

    result = build_prober(_settings(tmp_path, retry_attempts=3))(42, URL)

    assert route.call_count == 1
    assert result.verdict == "unknown"


@respx.mock
def test_a_500_never_withholds_however_the_client_reports_it(tmp_path: Path) -> None:
    """A server having a bad minute says nothing about the requisition."""
    respx.get(URL).mock(return_value=httpx.Response(500))

    assert build_prober(_settings(tmp_path))(42, URL).withholds is False


def test_the_probe_survives_a_client_that_raises_something_unforeseen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The broad `except Exception` is deliberate: nothing except an explicit gone-status may
    withhold a lead, so an unforeseen client fault must not become a silent veto."""
    import boardwatch.pipeline.liveness as module  # noqa: PLC0415

    class Boom:
        def get(self, url: str, validators: object = None) -> object:
            raise RuntimeError("something nobody predicted")

    monkeypatch.setattr(module, "Fetcher", lambda settings: Boom())

    result = build_prober(_settings(tmp_path))(42, URL)

    assert result.verdict == "unknown"
    assert result.withholds is False
    assert "RuntimeError" in result.detail


# --- Workday: the CXS endpoint, never the page ---------------------------------------------
#
# Every closed Workday requisition measured answered HTTP 200 on its PAGE (0 of 37, D-325), so a
# page probe can only ever say `alive`. The expected shapes below are the ones measured on the
# CXS endpoint 2026-10-25/27 (23 known-closed, 9 known-open, 9 more S22 closures), not values
# read back from the classifier.

WD_PAGE = "https://acme.wd5.myworkdayjobs.com/en-US/Acme_Careers/job/Austin-TX/Engineer_R123?src=li"
WD_CXS = "https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/Acme_Careers/job/Austin-TX/Engineer_R123"
# The body measured live 2026-10-27, error-case id aside.
S22_BODY = b'{"errorCode":"S22","errorCaseId":"X","httpStatus":403,"message":"permission denied"}'


@pytest.mark.parametrize(
    ("page", "cxs"),
    [
        (WD_PAGE, WD_CXS),
        (
            "https://acme.wd1.myworkdayjobs.com/Acme_Careers/job/Remote/Engineer_JR42",
            "https://acme.wd1.myworkdayjobs.com/wday/cxs/acme/Acme_Careers/job/Remote/Engineer_JR42",
        ),
        (
            "https://wd1.myworkdaysite.com/en-US/recruiting/uchicago/External/job/Chicago-IL/Analyst_JR1",
            "https://wd1.myworkdaysite.com/wday/cxs/uchicago/External/job/Chicago-IL/Analyst_JR1",
        ),
        # A 2-letter locale, peeled only because what remains is the exact posting shape.
        (
            "https://acme.wd5.myworkdayjobs.com/es/Acme_Careers/job/Madrid/Ingeniero_R7",
            "https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/Acme_Careers/job/Madrid/Ingeniero_R7",
        ),
        # ...and a 2-letter SITE is still a site: peeling it would leave three segments.
        (
            "https://acme.wd5.myworkdayjobs.com/US/job/Austin-TX/Engineer_R8",
            "https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/US/job/Austin-TX/Engineer_R8",
        ),
    ],
)
def test_a_workday_page_maps_to_its_cxs_endpoint(page: str, cxs: str) -> None:
    from boardwatch.providers.workday import cxs_job_url  # noqa: PLC0415

    assert cxs_job_url(page) == cxs


@pytest.mark.parametrize(
    "url",
    [
        "https://acme.wd5.myworkdayjobs.com/Acme_Careers",  # a board, not a posting
        "https://acme.wd5.myworkdayjobs.com/Acme_Careers/details/Engineer_R123",
        "https://acme.wd5.myworkdayjobs.com/Acme_Careers/job/Austin-TX/Engineer_R123/apply",
        "https://acme.wd5.myworkdayjobs.com/Acme_Careers/job/Engineer_R123",
        "https://wd1.myworkdaysite.com/recruiting/uchicago/External",
        "https://boards.greenhouse.io/acme/jobs/1",
        "https://notmyworkdayjobs.com/Acme/job/X/Y_R1",
    ],
)
def test_anything_else_keeps_the_page_probe(url: str) -> None:
    from boardwatch.providers.workday import cxs_job_url  # noqa: PLC0415

    assert cxs_job_url(url) is None


@respx.mock
def test_a_workday_page_is_never_fetched_its_cxs_endpoint_is(tmp_path: Path) -> None:
    page = respx.get(WD_PAGE).mock(return_value=httpx.Response(200))
    cxs = respx.get(WD_CXS).mock(return_value=httpx.Response(403, content=S22_BODY))

    build_prober(_settings(tmp_path))(42, WD_PAGE)

    assert not page.called
    assert cxs.call_count == 1
    assert cxs.calls[0].request.headers["accept"] == "application/json"


@respx.mock
def test_a_cxs_403_naming_S22_is_DEAD(tmp_path: Path) -> None:  # noqa: N802
    respx.get(WD_CXS).mock(return_value=httpx.Response(403, content=S22_BODY))

    result = build_prober(_settings(tmp_path))(42, WD_PAGE)

    assert result.verdict == "dead"
    assert result.signal == "workday_unposted"


@pytest.mark.parametrize(
    "body",
    [
        b"<html>Access denied</html>",
        b"<html>Blocked. Reference S22-4471</html>",  # the code as text, not as the error field
        b'{"errorCode":"S21","message":"S22"}',
    ],
)
@respx.mock
def test_a_cxs_403_WITHOUT_the_S22_error_code_is_unknown(  # noqa: N802
    tmp_path: Path, body: bytes
) -> None:
    """A bot-blocker answers 403 too. The body code is the evidence, not the status."""
    respx.get(WD_CXS).mock(return_value=httpx.Response(403, content=body))

    result = build_prober(_settings(tmp_path))(42, WD_PAGE)

    assert result.verdict == "unknown"
    assert result.withholds is False


@pytest.mark.parametrize("status", [404, 410])
@respx.mock
def test_a_cxs_404_or_410_is_DEAD(tmp_path: Path, status: int) -> None:  # noqa: N802
    respx.get(WD_CXS).mock(return_value=httpx.Response(status))

    result = build_prober(_settings(tmp_path))(42, WD_PAGE)

    assert result.verdict == "dead"
    assert result.signal == "refetch_gone"


@respx.mock
def test_a_cxs_S22_reached_through_a_redirect_is_served(tmp_path: Path) -> None:  # noqa: N802
    respx.get(WD_CXS).mock(
        return_value=httpx.Response(302, headers={"Location": "https://other.example/x"})
    )
    moved = respx.get("https://other.example/x").mock(
        return_value=httpx.Response(403, content=S22_BODY)
    )

    result = build_prober(_settings(tmp_path))(42, WD_PAGE)

    assert moved.called
    assert result.verdict == "unknown"
    assert result.signal == "refetch_gone_after_redirect"


@respx.mock
def test_a_cxs_200_with_a_posting_is_ALIVE(tmp_path: Path) -> None:  # noqa: N802
    body = json.dumps({"jobPostingInfo": {"title": "Engineer", "canApply": True}})
    respx.get(WD_CXS).mock(return_value=httpx.Response(200, content=body.encode()))

    result = build_prober(_settings(tmp_path))(42, WD_PAGE)

    assert result.verdict == "alive"
    assert result.signal == "refetch_ok"


@pytest.mark.parametrize(
    "body",
    [
        b'{"jobPostingInfo": {"title": "Engineer", "canApply": false}}',
        b'{"hiringOrganization": {}}',
        b"<html>not json</html>",
        b"[]",
    ],
)
@respx.mock
def test_a_cxs_200_without_a_live_posting_is_unknown(tmp_path: Path, body: bytes) -> None:
    """Never `alive`: on the death-probe path an `alive` RESETS earned strikes."""
    respx.get(WD_CXS).mock(return_value=httpx.Response(200, content=body))

    result = build_prober(_settings(tmp_path))(42, WD_PAGE)

    assert result.verdict == "unknown"
