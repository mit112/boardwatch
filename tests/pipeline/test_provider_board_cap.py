"""T323: a provider's `max_boards_in_flight` holds across all of its hosts, through `run_scan`.

`Fetcher` paces per HOST, and Eightfold's tenants are different hosts on one backend whose HTTP 405
throttle spans them. Five of its boards running together spent their retry budgets and failed every
detail, nightly. `tests/unit/test_scan_dispatch_order.py` pins the ready queue; these pin that the
scan LOOP holds the count the way it holds a host — released when a board is collected, and kept
while an abandoned thread still runs.
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert, select

from boardwatch.core.models import BoardRequest, BoardSnapshot
from boardwatch.core.politeness import Fetcher
from boardwatch.core.settings import Settings
from boardwatch.providers.base import BoardHealth
from boardwatch.scan.coordinator import run_scan
from boardwatch.store import tables

#: A real-time 0.3 s board cap raced against thread scheduling; flaky on windows-latest only
#: (the same reason `test_board_deadline.py` gives).
_windows_timing = pytest.mark.skipif(
    sys.platform == "win32", reason="0.3 s real-time board cap is flaky on windows-latest runners"
)


class _Boards:
    """A provider whose boards each sit on their own host and record how many overlap.

    With `parties` > 1 the boards wait for each other at a barrier, so the peak is the true width
    the scan ran at rather than whatever a sleep happened to overlap: a scan that ran two at a
    time reaches the barrier in pairs, one that ran six reaches it six at a time."""

    def __init__(self, name: str, *, parties: int = 1, cap: int | None = None) -> None:
        self.name = name
        self.board_hosts: tuple[str, ...] = ()
        if cap is not None:
            self.max_boards_in_flight = cap
        self._barrier = threading.Barrier(parties, timeout=10.0) if parties > 1 else None
        self._lock = threading.Lock()
        self.now = 0
        self.peak = 0
        self.starts: dict[str, float] = {}
        self.ends: dict[str, float] = {}
        self.release = threading.Event()  # `stuck` blocks on this
        self.release_after: float | None = None

    def board_url(self, slug: str) -> str:
        return f"https://{slug}.{self.name}.example/{slug}"

    def fetch_board(self, fetcher: Fetcher, request: BoardRequest) -> BoardSnapshot:
        with self._lock:
            self.starts[request.slug] = time.monotonic()
            self.now += 1
            self.peak = max(self.peak, self.now)
        try:
            if request.slug == "stuck":
                if self.release_after is not None:
                    threading.Timer(self.release_after, self.release.set).start()
                self.release.wait(timeout=30.0)
            elif self._barrier is not None:
                self._barrier.wait()
        finally:
            with self._lock:
                self.now -= 1
                self.ends[request.slug] = time.monotonic()
        return BoardSnapshot(
            status="complete", postings=[], url=request.url, observed_validators=None, error=None
        )

    def healthcheck(self, fetcher: Fetcher, slug: str) -> BoardHealth:
        return BoardHealth.OK


def _add(engine: Engine, provider: str, slug: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            insert(tables.companies).values(
                name=slug, provider=provider, slug=slug, source="user", watched=True
            )
        )


def _settings(tmp_path: Path, **overrides: float) -> Settings:
    return Settings(
        data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1, scan_workers=16, **overrides
    )


def test_a_capped_provider_runs_at_its_cap_and_does_not_hold_back_another_provider(
    engine: Engine, tmp_path: Path
) -> None:
    """Six capped boards and six uncapped ones, sixteen workers. The capped provider peaks at
    exactly its cap of two, ALL SIX are still scanned (the loop terminates with nothing stranded),
    and the other provider still runs all six at once even though the capped boards are queued
    first and sit skipped while it does — the barrier would time out if they were serialized."""
    capped = _Boards("capped", parties=2, cap=2)
    free = _Boards("free", parties=6)
    for i in range(6):
        _add(engine, "capped", f"c{i}")
    for i in range(6):
        _add(engine, "free", f"f{i}")

    summary = run_scan(engine, _settings(tmp_path), providers={"capped": capped, "free": free})

    assert capped.peak == 2, f"capped provider peaked at {capped.peak} boards in flight, not 2"
    assert free.peak == 6, f"uncapped provider ran {free.peak} wide, not 6"
    assert (summary.complete, summary.failed, summary.errors) == (12, 0, [])
    assert sorted(capped.ends) == [f"c{i}" for i in range(6)]
    with engine.connect() as conn:
        statuses = conn.execute(select(tables.board_scans.c.status)).scalars().all()
    assert statuses.count("complete") == 12


@_windows_timing
def test_an_abandoned_board_still_counts_against_its_providers_cap(
    engine: Engine, tmp_path: Path
) -> None:
    """The abandoned thread is still on the backend, so it still holds the provider's slot, the
    way it holds its host (T192b). `stuck` is failed at its 0.3 s board cap; `next`, of the same
    capped provider on ANOTHER host, must wait until that thread ends (0.8 s) rather than start
    beside it. Releasing the count at the cap instead would start `next` at ~0.3 s, inside
    `stuck`'s window — which is the assertion."""
    provider = _Boards("capped", cap=1)
    provider.release_after = 0.8
    _add(engine, "capped", "stuck")
    _add(engine, "capped", "next")

    summary = run_scan(
        engine, _settings(tmp_path, board_deadline_seconds=0.3), providers={"capped": provider}
    )
    provider.release.set()

    assert (summary.failed, summary.complete) == (1, 1)
    assert "stuck" in provider.ends, "`next` ran while `stuck`'s abandoned thread was still going"
    assert provider.starts["next"] >= provider.ends["stuck"]
