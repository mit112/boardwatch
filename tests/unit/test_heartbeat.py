"""Tests for the run success heartbeat (dead-man's-switch). Uses httpx.MockTransport —
no real network. The heartbeat pings an external monitor URL on a successful run; a
missing ping is what lets the monitor alert that the daily run never happened."""

from __future__ import annotations

import httpx

from boardwatch.notify.heartbeat import HEARTBEAT_URL_ENV, send_heartbeat

_URL = "https://hc.example/ping-token"


def _client(handler: object) -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(handler),  # type: ignore[arg-type]
        follow_redirects=True,
    )


def test_missing_url_is_noop() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200)

    assert send_heartbeat(env={}, client=_client(handler)) is False
    assert calls == []  # never touches the network when the URL is unset


def test_success_pings_the_url() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, text="ok")

    ok = send_heartbeat(env={HEARTBEAT_URL_ENV: _URL}, client=_client(handler))
    assert ok is True
    assert calls == [_URL]


def test_redirect_is_followed() -> None:
    # Dead-man's-switch endpoints (healthchecks.io, cronitor) commonly answer a ping with
    # a 302; the ping must still register, so the client follows redirects.
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path.endswith("ping-token"):
            return httpx.Response(302, headers={"Location": "https://hc.example/landed"})
        return httpx.Response(200, text="ok")

    ok = send_heartbeat(env={HEARTBEAT_URL_ENV: _URL}, client=_client(handler))
    assert ok is True
    assert "/landed" in seen  # the redirect was actually followed


def test_non_2xx_is_false() -> None:
    ok = send_heartbeat(
        env={HEARTBEAT_URL_ENV: _URL},
        client=_client(lambda req: httpx.Response(500)),
    )
    assert ok is False


def test_transport_error_is_swallowed() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    # Must never raise: a telemetry ping can never fail a real run.
    assert send_heartbeat(env={HEARTBEAT_URL_ENV: _URL}, client=_client(boom)) is False
