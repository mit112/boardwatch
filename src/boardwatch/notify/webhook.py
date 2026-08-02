"""Webhook delivery for `boardwatch notify` (P5). Zero new deps — uses the existing httpx.
One POST carries a dual-key payload so a single request renders on Slack incoming webhooks
(`text`), Discord webhooks (`content`), and generic/structured consumers (`boardwatch`).

The URL is a secret (a Slack/Discord webhook URL embeds a token), so it comes ONLY from the
environment via core.secrets — never from config.toml. Payload carries only public job facts
already shown by `top` (title, company, public URL, score, one-token verdict): never profile
text, resume, or eligibility evidence.

The payload is built once by the caller (the `notify` command, which owns the cursor context)
via `build_payload` and handed to `WebhookChannel` at construction time. `deliver` only POSTs
that fixed payload — it has no knowledge of `since`/`max_event_id`.
"""

from __future__ import annotations

from collections.abc import Mapping

import httpx

from boardwatch.core.secrets import resolve_secret
from boardwatch.notify.channel import DeliveryResult
from boardwatch.reports.notify import NotifyItem

WEBHOOK_URL_ENV = "BOARDWATCH_NOTIFY_WEBHOOK_URL"
_MAX_LINES = 10
_MAX_SUMMARY_CHARS = 1900  # Discord rejects a `content` over 2000; stay under with headroom
_TIMEOUT = httpx.Timeout(10.0)


def _summary(items: tuple[NotifyItem, ...]) -> str:
    head = f"boardwatch: {len(items)} new match{'es' if len(items) != 1 else ''}"
    lines = [
        f"• {i.title} — {i.company} ({i.score:.2f})" + (f" {i.url}" if i.url else "")
        for i in items[:_MAX_LINES]
    ]
    if len(items) > _MAX_LINES:
        lines.append(f"…and {len(items) - _MAX_LINES} more")
    text = "\n".join([head, *lines])
    if len(text) > _MAX_SUMMARY_CHARS:
        text = text[: _MAX_SUMMARY_CHARS - 1].rstrip() + "…"
    return text


def build_payload(
    items: tuple[NotifyItem, ...], since: int, max_event_id: int
) -> dict[str, object]:
    """Build the single dual-key payload shared by every channel construction. Public job
    facts only: no profile text, resume, or eligibility evidence keys."""
    summary = _summary(items)
    return {
        "text": summary,  # Slack incoming webhook
        "content": summary,  # Discord webhook
        "boardwatch": {  # generic / structured consumers
            "new_match_count": len(items),
            "since_event_id": since,
            "max_event_id": max_event_id,
            "matches": [
                {
                    "posting_id": i.posting_id,
                    "title": i.title,
                    "company": i.company,
                    "url": i.url,
                    "score": i.score,
                    "verdict": i.verdict,
                }
                for i in items
            ],
        },
    }


class WebhookChannel:
    name = "webhook"

    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        payload: dict[str, object],
        env: Mapping[str, str] | None = None,
    ) -> None:
        self._client = client
        self._payload = payload
        self._env = env

    def deliver(self, items: tuple[NotifyItem, ...]) -> DeliveryResult:
        url = resolve_secret(WEBHOOK_URL_ENV, env=self._env)
        if url is None:
            return DeliveryResult(self.name, False, f"no webhook url set ({WEBHOOK_URL_ENV})")
        client = self._client or httpx.Client(timeout=_TIMEOUT)
        try:
            resp = client.post(url, json=self._payload)
            if resp.is_success:
                return DeliveryResult(
                    self.name, True, f"posted {len(items)} ({resp.status_code})"
                )
            return DeliveryResult(self.name, False, f"http {resp.status_code}")
        except httpx.HTTPError as exc:
            return DeliveryResult(self.name, False, f"transport error: {exc}")
        finally:
            if self._client is None:
                client.close()
