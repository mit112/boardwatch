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

    # `None`, not an alert: the heartbeat is off by default for every user who never set the
    # variable, and "your heartbeat failed" for a heartbeat nobody configured is pure noise.
    assert send_heartbeat(env={}, client=_client(handler)) is None
    assert calls == []  # never touches the network when the URL is unset


def test_success_pings_the_url() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, text="ok")

    assert send_heartbeat(env={HEARTBEAT_URL_ENV: _URL}, client=_client(handler)) is None
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

    assert send_heartbeat(env={HEARTBEAT_URL_ENV: _URL}, client=_client(handler)) is None
    assert "/landed" in seen  # the redirect was actually followed


def test_a_refused_ping_returns_an_alert_naming_the_status() -> None:
    """The failure this closes: a rotated token, a deleted check, or a monitor answering 500
    produced NO local trace at all, so boardwatch's silence read as health. The status IS the
    diagnosis here — 401 the token, 404 the check, 5xx the monitor itself."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(404)

    alert = send_heartbeat(env={HEARTBEAT_URL_ENV: _URL}, client=_client(handler))

    assert alert is not None, "a refused ping reported nothing"
    assert "404" in alert, alert
    assert calls == [_URL], "a refused ping must not be retried — never a second ping"


def test_transport_error_returns_an_alert_and_never_raises() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    # Must never raise: a telemetry ping can never fail a real run (D-076).
    alert = send_heartbeat(env={HEARTBEAT_URL_ENV: _URL}, client=_client(boom))

    assert alert is not None
    assert "ConnectError" in alert, alert


def test_no_alert_ever_carries_the_token_bearing_url() -> None:
    """The alert is persisted to `runs.errors_json` and reprinted by the CLI, and the monitor
    URL embeds a token — the same reason it is read only from the environment. Both failure
    branches are checked, since each builds its string from a different source."""

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"cannot reach {_URL}")

    refused = send_heartbeat(
        env={HEARTBEAT_URL_ENV: _URL},
        client=_client(lambda req: httpx.Response(500)),
    )
    unreachable = send_heartbeat(env={HEARTBEAT_URL_ENV: _URL}, client=_client(boom))

    assert refused is not None and unreachable is not None
    for alert in (refused, unreachable):
        assert "ping-token" not in alert, f"the alert leaked the monitor token: {alert}"
        assert "hc.example" not in alert, f"the alert leaked the monitor URL: {alert}"
