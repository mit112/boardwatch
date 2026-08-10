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
