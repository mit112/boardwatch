"""Delivery-channel contract for `boardwatch notify` (P5). A channel is best-effort and
total: it returns a DeliveryResult for expected failures (missing config, absent binary,
non-2xx) rather than raising, so one channel can never abort another or the command."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from boardwatch.reports.notify import NotifyItem


@dataclass(frozen=True)
class DeliveryResult:
    channel: str
    ok: bool
    detail: str


class Channel(Protocol):
    name: str

    def deliver(self, items: tuple[NotifyItem, ...]) -> DeliveryResult: ...
