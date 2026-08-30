"""Tests for soft-alert escalation. Uses httpx.MockTransport — no real network.

A real POST here is worse than a failing test: the configured endpoint is a live monitor, and a
test report would register as a genuine degradation on the owner's dashboard. Every test injects
a client, exactly as `test_heartbeat.py` does for the same reason.
"""

from __future__ import annotations

import httpx

from boardwatch.notify.alert_escalation import (
    ALERT_URL_ENV,
    MAX_BODY_CHARS,
    build_alert_body,
    escalate_alerts,
)

_URL = "https://hc.example/ping-token/fail"


def _client(handler: object) -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(handler),  # type: ignore[arg-type]
        follow_redirects=True,
    )


def _recorder() -> tuple[list[httpx.Request], object]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text="ok")

    return seen, handler


def test_a_clean_run_never_posts() -> None:
    """The load-bearing negative. This channel fires only on trouble, so an empty alert list
    must not reach the network at all — an endpoint that receives a message on every clean run
    learns nothing from receiving one, which is the failure the heartbeat's inverse polarity
    already avoids."""
    seen, handler = _recorder()

    assert escalate_alerts(133, (), env={ALERT_URL_ENV: _URL}, client=_client(handler)) is None
    assert seen == []


def test_missing_url_is_noop_even_with_alerts() -> None:
    """Unset is the default for every user who never configured an endpoint. Alerts present and
    no URL is not an error; it is the off state."""
    seen, handler = _recorder()

    assert escalate_alerts(133, ("intake death",), env={}, client=_client(handler)) is None
    assert seen == []


def test_every_alert_reaches_the_body_with_the_run_id_and_the_count() -> None:
    seen, handler = _recorder()
    alerts = ("intake: no net-new postings", "corpus: rate collapsed to 0.00%")

    assert escalate_alerts(133, alerts, env={ALERT_URL_ENV: _URL}, client=_client(handler)) is None

    assert len(seen) == 1
    assert str(seen[0].url) == _URL
    assert seen[0].method == "POST"
    body = seen[0].content.decode("utf-8")
    assert "boardwatch run 133" in body
    assert "2 alert(s)" in body
    for alert in alerts:
        assert alert in body


def test_a_refused_report_returns_an_alert_naming_the_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    alert = escalate_alerts(133, ("x",), env={ALERT_URL_ENV: _URL}, client=_client(handler))
    assert alert is not None
    assert "404" in alert


def test_a_transport_error_returns_an_alert_naming_the_exception_class() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    alert = escalate_alerts(133, ("x",), env={ALERT_URL_ENV: _URL}, client=_client(handler))
    assert alert is not None
    assert "ConnectError" in alert


def test_neither_the_url_nor_the_exception_message_reaches_the_returned_string() -> None:
    """The returned string is persisted to `runs.errors_json` and reprinted by the CLI, and the
    URL embeds a token. Rejects the obvious `f"...{url}: {exc}"` phrasing."""

    def refusing(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    def raising(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connect to hc.example/ping-token/fail failed", request=request)

    for handler in (refusing, raising):
        alert = escalate_alerts(133, ("x",), env={ALERT_URL_ENV: _URL}, client=_client(handler))
        assert alert is not None
        assert "ping-token" not in alert
        assert _URL not in alert


def test_truncation_announces_itself_and_respects_the_cap() -> None:
    """A body cut at the endpoint's own 10 KB limit ends mid-sentence and says nothing about
    what it lost. Cutting below that limit is what buys the ability to say so."""
    alerts = tuple(f"alert number {i} " + "x" * 200 for i in range(200))

    body = build_alert_body(133, alerts)

    assert len(body) <= MAX_BODY_CHARS
    assert "200 alert(s)" in body  # the COUNT is honest even when the list is not complete
    assert "more, in this run's morning digest" in body
    assert "alert number 0" in body  # kept from the front, not an arbitrary slice


def test_a_short_body_is_not_truncated() -> None:
    body = build_alert_body(7, ("one", "two"))

    assert body == "boardwatch run 7: 2 alert(s)\n- one\n- two"
    assert "more, in this run" not in body
