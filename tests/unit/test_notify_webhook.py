"""Tests for the webhook delivery channel (P5). Uses httpx.MockTransport — no real network."""

from __future__ import annotations

import httpx

from boardwatch.notify.webhook import WEBHOOK_URL_ENV, WebhookChannel, build_payload
from boardwatch.reports.notify import NotifyItem

_ITEM = NotifyItem(1, "Backend Engineer", "Acme", "https://x/y", 0.7, None)


def _client(handler: object) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


def test_payload_is_dual_key() -> None:
    p = build_payload((_ITEM,), 0, 10)
    assert p["text"] and p["content"]
    board = p["boardwatch"]
    assert isinstance(board, dict)
    assert board["new_match_count"] == 1
    matches = board["matches"]
    assert isinstance(matches, list)
    assert matches[0]["posting_id"] == 1
    # privacy: no profile/eligibility evidence keys
    dumped = str(p)
    assert "resume" not in dumped and "evidence" not in dumped


def test_summary_capped_for_discord() -> None:
    many = tuple(
        NotifyItem(n, "X" * 200, "Y" * 200, "https://example/" + "z" * 200, 0.5, None)
        for n in range(50)
    )
    p = build_payload(many, 0, 99)
    content = p["content"]
    assert isinstance(content, str)
    assert len(content) <= 1900  # Discord 2000-char limit respected
    board = p["boardwatch"]
    assert isinstance(board, dict)
    assert board["new_match_count"] == 50  # structured list stays complete
    matches = board["matches"]
    assert isinstance(matches, list)
    assert len(matches) == 50


def test_missing_url_is_non_fatal() -> None:
    ch = WebhookChannel(payload=build_payload((_ITEM,), 0, 10), env={})
    r = ch.deliver((_ITEM,))
    assert r.ok is False and "url" in r.detail.lower()


def test_2xx_ok() -> None:
    calls: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["body"] = request.content
        return httpx.Response(200, text="ok")

    ch = WebhookChannel(
        _client(handler),
        payload=build_payload((_ITEM,), 0, 10),
        env={WEBHOOK_URL_ENV: "https://hook.example/x"},
    )
    r = ch.deliver((_ITEM,))
    assert r.ok is True and calls["body"]


def test_5xx_is_non_fatal_no_raise() -> None:
    ch = WebhookChannel(
        _client(lambda req: httpx.Response(500)),
        payload=build_payload((_ITEM,), 0, 10),
        env={WEBHOOK_URL_ENV: "https://hook.example/x"},
    )
    r = ch.deliver((_ITEM,))
    assert r.ok is False and "500" in r.detail


def test_transport_error_is_non_fatal() -> None:
    def boom(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    ch = WebhookChannel(
        _client(boom),
        payload=build_payload((_ITEM,), 0, 10),
        env={WEBHOOK_URL_ENV: "https://hook.example/x"},
    )
    r = ch.deliver((_ITEM,))
    assert r.ok is False
