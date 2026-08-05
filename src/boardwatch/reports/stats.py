"""`boardwatch stats` — a one-screen read-only readout over the local DB.

summarize() is pure and holds the honesty-critical rule: the window partition is disjoint
and keeps `unevaluated` (no current verdict) separate from `qualified`, so an empty
eligibility ledger reads as "N unevaluated", never as "0 qualified". compute_stats() (below)
is the thin I/O wrapper that reuses top's preflight/eligibility/filter seams.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class PostingStat:
    posting_id: int
    posted_at: datetime | None
    passes_filters: bool
    verdict: str | None  # "eligible" | "uncertain" | "ineligible" | None (unevaluated)


@dataclass(frozen=True)
class StatsReport:
    window_days: int
    qualified: int
    uncertain: int
    ineligible: int
    unevaluated: int
    seen: int
    passes_filters: int
    not_ineligible: int
    tracked: int


def summarize(
    stats: list[PostingStat], *, now: datetime, window_days: int, seen: int, tracked: int
) -> StatsReport:
    cutoff = now - timedelta(days=window_days)
    in_window = [
        s for s in stats
        if s.passes_filters and s.posted_at is not None and s.posted_at >= cutoff
    ]
    qualified = sum(1 for s in in_window if s.verdict == "eligible")
    uncertain = sum(1 for s in in_window if s.verdict == "uncertain")
    ineligible = sum(1 for s in in_window if s.verdict == "ineligible")
    unevaluated = sum(1 for s in in_window if s.verdict is None)
    passes = sum(1 for s in stats if s.passes_filters)
    not_ineligible = sum(1 for s in stats if s.passes_filters and s.verdict != "ineligible")
    return StatsReport(
        window_days=window_days,
        qualified=qualified, uncertain=uncertain, ineligible=ineligible, unevaluated=unevaluated,
        seen=seen, passes_filters=passes, not_ineligible=not_ineligible, tracked=tracked,
    )
