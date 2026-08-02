"""Run enabled channels and aggregate results (P5). Unexpected exceptions from a channel
are contained here as ok=False so a misbehaving channel cannot kill the run."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from boardwatch.notify.channel import Channel, DeliveryResult
from boardwatch.reports.notify import NotifyItem


@dataclass(frozen=True)
class DispatchOutcome:
    results: tuple[DeliveryResult, ...]
    any_delivered: bool


def dispatch(items: tuple[NotifyItem, ...], channels: Sequence[Channel]) -> DispatchOutcome:
    results: list[DeliveryResult] = []
    for channel in channels:
        try:
            results.append(channel.deliver(items))
        except Exception as exc:  # containment boundary — one channel can't kill the run
            results.append(DeliveryResult(channel.name, False, f"unexpected error: {exc}"))
    return DispatchOutcome(results=tuple(results), any_delivered=any(r.ok for r in results))
