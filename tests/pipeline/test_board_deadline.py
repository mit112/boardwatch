"""T192: one board whose fetch never returns must not hold the scan stage open.

Run 473 finished 2,058 boards and then sat 55 minutes with ONE worker blocked in a read while the
coordinator had nothing else to wait on. `board_deadline_seconds` bounds a board's wall clock in
the coordinator itself, independent of why the worker is stuck.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterable, Iterator
from concurrent import futures
from concurrent.futures import Future
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, insert, select

from boardwatch.core.models import BoardRequest, BoardSnapshot
from boardwatch.core.politeness import Fetcher
from boardwatch.core.settings import Settings
from boardwatch.providers.base import BoardHealth
from boardwatch.scan import coordinator
from boardwatch.scan.coordinator import run_scan
from boardwatch.store import tables


class _StuckProvider:
    """`stuck` blocks until released (or 5s pass); every other board completes at once.

    Board URLs carry the slug's host, except `later`, which shares `stuck`'s host — so it can
    only be scanned if the coordinator releases that host when it gives up on `stuck`."""

    name = "greenhouse"
    board_hosts: tuple[str, ...] = ()

    def __init__(self) -> None:
        self.release = threading.Event()

    def board_url(self, slug: str) -> str:
        host = "stuck" if slug == "later" else slug
        return f"https://{host}.example/{slug}"

    def fetch_board(self, fetcher: Fetcher, request: BoardRequest) -> BoardSnapshot:
        if request.slug == "stuck":
            self.release.wait(timeout=5.0)
        return BoardSnapshot(
            status="complete", postings=[], url=request.url,
            observed_validators=None, error=None,
        )

    def healthcheck(self, fetcher: Fetcher, slug: str) -> BoardHealth:
        return BoardHealth.OK


@pytest.fixture
def provider() -> Iterator[_StuckProvider]:
    stuck = _StuckProvider()
    yield stuck
    stuck.release.set()  # let the abandoned worker finish rather than outlive the test


def _add_company(engine: Engine, slug: str) -> int:
    with engine.begin() as conn:
        result = conn.execute(
            insert(tables.companies).values(
                name=slug.title(), provider="greenhouse", slug=slug,
                source="user", watched=True,
            )
        )
        return int(result.inserted_primary_key[0])


def test_a_board_past_its_deadline_is_failed_and_the_stage_completes(
    engine: Engine, tmp_path: Path, provider: _StuckProvider
) -> None:
    ids = {slug: _add_company(engine, slug) for slug in ("stuck", "later", "acme")}
    settings = Settings(
        data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1, scan_workers=2,
        board_deadline_seconds=0.3,
    )

    started = time.monotonic()
    summary = run_scan(engine, settings, providers={"greenhouse": provider})

    # Not joined on the stuck worker, which is still blocked when the stage ends.
    assert time.monotonic() - started < 3.0
    assert summary.failed == 1
    assert summary.complete == 2
    assert "stuck: board deadline 0.3s exceeded" in summary.errors
    with engine.connect() as conn:
        rows = conn.execute(
            select(tables.board_scans.c.company_id, tables.board_scans.c.status,
                   tables.board_scans.c.error)
        ).all()
        boards_failed = conn.execute(select(tables.runs.c.boards_failed)).scalar_one()
    by_id = {r.company_id: (r.status, r.error) for r in rows}
    assert by_id == {
        ids["stuck"]: ("failed", "board deadline 0.3s exceeded"),
        ids["later"]: ("complete", None),
        ids["acme"]: ("complete", None),
    }
    assert boards_failed == 1


def test_boards_inside_the_deadline_are_untouched(
    engine: Engine, tmp_path: Path, provider: _StuckProvider
) -> None:
    """Control: with no board near the cap, the scan is what it was."""
    for slug in ("later", "acme"):
        _add_company(engine, slug)
    settings = Settings(
        data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1, scan_workers=2,
        board_deadline_seconds=0.3,
    )
    summary = run_scan(engine, settings, providers={"greenhouse": provider})
    assert (summary.complete, summary.failed, summary.errors) == (2, 0, [])


def test_a_worker_freed_by_an_abandoned_board_is_reused(
    engine: Engine, tmp_path: Path, provider: _StuckProvider
) -> None:
    """With ONE worker, the abandoned board holds the only thread: the rest of the queue must
    wait for it to end and then run — not be dropped, and not queue behind it on a clock
    that started before it could run."""
    ids = {slug: _add_company(engine, slug) for slug in ("stuck", "acme", "beta")}
    settings = Settings(
        data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1, scan_workers=1,
        board_deadline_seconds=0.3,
    )
    threading.Timer(0.8, provider.release.set).start()  # the stuck fetch ends on its own
    summary = run_scan(engine, settings, providers={"greenhouse": provider})
    assert (summary.failed, summary.complete) == (1, 2)
    with engine.connect() as conn:
        statuses = dict(
            conn.execute(
                select(tables.board_scans.c.company_id, tables.board_scans.c.status)
            ).all()
        )
    assert statuses == {ids["stuck"]: "failed", ids["acme"]: "complete", ids["beta"]: "complete"}


def test_a_board_that_finishes_as_its_cap_trips_is_recorded_complete(
    engine: Engine, tmp_path: Path, provider: _StuckProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T192b. A future can finish between `wait()` timing out and the overdue check. It is then
    absent from `done` but already finished, and it must be collected, not failed."""
    ids = {"acme": _add_company(engine, "acme")}
    settings = Settings(
        data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1, scan_workers=1,
        board_deadline_seconds=0.3,
    )
    real_wait = futures.wait
    raced: list[bool] = []

    def racing_wait(
        fs: Iterable[Future[BoardSnapshot]], timeout: float | None = None, return_when: Any = None
    ) -> Any:
        pending = set(fs)
        if not raced:
            # The timeout fired, and in the same instant the board finished past its cap.
            raced.append(True)
            real_wait(pending)
            time.sleep(settings.board_deadline_seconds)
            return set(), pending
        return real_wait(pending, timeout=timeout, return_when=return_when)

    monkeypatch.setattr(coordinator, "wait", racing_wait)
    summary = run_scan(engine, settings, providers={"greenhouse": provider})

    assert raced == [True]
    assert (summary.complete, summary.failed, summary.errors) == (1, 0, [])
    with engine.connect() as conn:
        status = conn.execute(
            select(tables.board_scans.c.status).where(
                tables.board_scans.c.company_id == ids["acme"]
            )
        ).scalar_one()
        boards_failed = conn.execute(select(tables.runs.c.boards_failed)).scalar_one()
    assert (status, boards_failed) == ("complete", 0)
