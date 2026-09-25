"""Fetch-only worker job (D16): workers have no DB access in either direction.

This module must never import boardwatch.store (lint-enforced). The thread
pool runs exactly this function; everything stateful happens in the
coordinator, serially.
"""

from __future__ import annotations

from time import perf_counter

from boardwatch.core.models import BoardRequest, BoardSnapshot
from boardwatch.core.politeness import Fetcher
from boardwatch.providers.base import Provider


def fetch_board_job(
    provider: Provider, fetcher: Fetcher, request: BoardRequest, deadline_at: float, cap: float
) -> BoardSnapshot:
    """Fetch one board, and record how long the FETCH took.

    Timed here rather than in the coordinator because this is the one seam every scanned
    board passes through, and because the coordinator sees boards only as they complete,
    where the gap between two completions is a function of `scan_workers`, not of either
    board. `perf_counter` rather than `utcnow`: this is a duration, and a wall-clock
    subtraction is wrong across an NTP step.

    A provider that maps its own failure into a `failed` snapshot is still timed — a board
    that spends 30 s timing out cost the run those 30 s, and attributing it only on success
    would make the expensive failures invisible.

    `deadline_at` is the coordinator's own `board_deadline_seconds` instant for this board, passed
    in rather than recomputed so the thread's clock and the coordinator's agree (T192c): once the
    coordinator has failed the board, every further request of this thread fails at once.

    That clock ends the thread AT the cap, so the thread can return before the coordinator looks,
    which it did on a loaded macOS runner (T228); its snapshot is then the provider's account of
    the clock's failures — "20 failed", or a `partial` the coordinator would apply. A board the
    clock cut short returns the cap's verdict instead, so it reads the same whichever side sees
    the cap first.
    """
    started = perf_counter()
    with fetcher.under_deadline(deadline_at, cap) as clock:
        snapshot = provider.fetch_board(fetcher, request)
    if clock.tripped:
        snapshot = board_deadline_snapshot(request.url, cap)
    return snapshot.model_copy(update={"fetch_seconds": perf_counter() - started})


def board_deadline_snapshot(
    url: str, cap: float, fetch_seconds: float | None = None
) -> BoardSnapshot:
    """The verdict on a board `board_deadline_seconds` cut short, for both halves of the cap:
    the coordinator failing it at the cap, and its own thread cut short by the same clock."""
    return BoardSnapshot(
        status="failed", postings=[], url=url, observed_validators=None,
        error=f"board deadline {cap:g}s exceeded", fetch_seconds=fetch_seconds,
    )
