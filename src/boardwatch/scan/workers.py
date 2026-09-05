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


def fetch_board_job(provider: Provider, fetcher: Fetcher, request: BoardRequest) -> BoardSnapshot:
    """Fetch one board, and record how long the FETCH took.

    Timed here rather than in the coordinator because this is the one seam every scanned
    board passes through, and because the coordinator sees boards only as they complete,
    where the gap between two completions is a function of `scan_workers`, not of either
    board. `perf_counter` rather than `utcnow`: this is a duration, and a wall-clock
    subtraction is wrong across an NTP step.

    A provider that maps its own failure into a `failed` snapshot is still timed — a board
    that spends 30 s timing out cost the run those 30 s, and attributing it only on success
    would make the expensive failures invisible.
    """
    started = perf_counter()
    snapshot = provider.fetch_board(fetcher, request)
    return snapshot.model_copy(update={"fetch_seconds": perf_counter() - started})
