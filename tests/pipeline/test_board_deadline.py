"""T192: one board whose fetch never returns must not hold the scan stage open.

Run 473 finished 2,058 boards and then sat 55 minutes with ONE worker blocked in a read while the
coordinator had nothing else to wait on. `board_deadline_seconds` bounds a board's wall clock in
the coordinator itself, independent of why the worker is stuck.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterable, Iterator
from concurrent import futures
from concurrent.futures import Future
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import Engine, func, insert, select

from boardwatch.core.models import BoardRequest, BoardSnapshot
from boardwatch.core.politeness import Fetcher, FetchFailure, HostPacing
from boardwatch.core.settings import Settings
from boardwatch.providers.base import BoardHealth
from boardwatch.providers.workday import WorkdayProvider
from boardwatch.scan import coordinator
from boardwatch.scan.coordinator import run_scan
from boardwatch.scan.workers import fetch_board_job
from boardwatch.store import tables


class _StuckProvider:
    """`stuck` blocks until released (or 5s pass); every other board completes at once.

    Board URLs carry the slug's host, except `later`, which shares `stuck`'s host. Boards on
    that host fetch under `host_lock`, standing in for `Fetcher`'s per-host lock, and record
    when they started and ended their fetch inside it."""

    name = "greenhouse"
    board_hosts: tuple[str, ...] = ()

    def __init__(self) -> None:
        self.release = threading.Event()
        self.host_lock = threading.Lock()
        self.fetches: dict[str, tuple[float, float]] = {}

    def board_url(self, slug: str) -> str:
        host = "stuck" if slug == "later" else slug
        return f"https://{host}.example/{slug}"

    def fetch_board(self, fetcher: Fetcher, request: BoardRequest) -> BoardSnapshot:
        if request.url.startswith("https://stuck."):
            with self.host_lock:
                started = time.monotonic()
                if request.slug == "stuck":
                    self.release.wait(timeout=5.0)
                self.fetches[request.slug] = (started, time.monotonic())
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
    ids = {slug: _add_company(engine, slug) for slug in ("stuck", "acme")}
    settings = Settings(
        data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1, scan_workers=2,
        board_deadline_seconds=0.3,
    )

    started = time.monotonic()
    summary = run_scan(engine, settings, providers={"greenhouse": provider})

    # Not joined on the stuck worker, which is still blocked when the stage ends.
    assert time.monotonic() - started < 3.0
    assert "stuck" not in provider.fetches
    assert summary.failed == 1
    assert summary.complete == 1
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
        ids["acme"]: ("complete", None),
    }
    assert boards_failed == 1


def test_a_board_behind_an_abandoned_one_on_its_host_waits_for_that_thread(
    engine: Engine, tmp_path: Path, provider: _StuckProvider
) -> None:
    """T192b. Releasing the overdue board's host handed `later` to a worker that only queued at
    the per-host lock the abandoned thread still held, so `later` was failed at its own cap
    without sending anything — and then fetched anyway once the lock came free. The host stays
    busy until the abandoned thread ends; `later` starts after it and completes."""
    ids = {slug: _add_company(engine, slug) for slug in ("stuck", "later")}
    settings = Settings(
        data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1, scan_workers=2,
        board_deadline_seconds=0.3,
    )
    threading.Timer(0.8, provider.release.set).start()  # the stuck fetch ends on its own

    summary = run_scan(engine, settings, providers={"greenhouse": provider})
    returned = time.monotonic()
    provider.release.wait()
    time.sleep(0.3)  # long enough for a thread queued at the lock to have fetched

    assert (summary.failed, summary.complete) == (1, 1)
    with engine.connect() as conn:
        statuses = dict(
            conn.execute(
                select(tables.board_scans.c.company_id, tables.board_scans.c.status)
            ).all()
        )
    assert statuses == {ids["stuck"]: "failed", ids["later"]: "complete"}
    assert provider.fetches["later"][0] >= provider.fetches["stuck"][1]
    # No board fetches after the stage has recorded it and returned.
    assert all(start < returned for start, _ in provider.fetches.values())


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


def _trickle(chunks: int, interval: float) -> Iterator[bytes]:
    for _ in range(chunks):
        time.sleep(interval)
        yield b"x"


class _DetailLoopProvider:
    """T192c. `slow` issues 20 sequential requests, each to its own host and each trickling,
    catching every `FetchFailure` and moving on — the shape of SmartRecruiters' detail loop. Any
    other board makes one quick request. Each host is distinct so pacing plays no part."""

    name = "greenhouse"
    board_hosts: tuple[str, ...] = ()

    def __init__(self, chunks: int, interval: float) -> None:
        self.chunks, self.interval = chunks, interval
        self.requests: list[str] = []
        self.ended: dict[str, float] = {}
        self.stop = threading.Event()  # teardown: a regression must not outlive the test by 4s

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(str(request.url))
        if request.url.host.startswith("slow-"):
            return httpx.Response(200, content=_trickle(self.chunks, self.interval))
        return httpx.Response(200, content=b"ok")

    def board_url(self, slug: str) -> str:
        return f"https://{slug}.example/{slug}"

    def fetch_board(self, fetcher: Fetcher, request: BoardRequest) -> BoardSnapshot:
        failures = 0
        urls = [f"https://slow-{i}.example/d" for i in range(20)] if request.slug == "slow" else [
            request.url
        ]
        for url in urls:
            if self.stop.is_set():
                break
            try:
                fetcher.get(url)
            except FetchFailure:
                failures += 1
        self.ended[request.slug] = time.monotonic()
        return BoardSnapshot(
            status="failed" if failures else "complete", postings=[], url=request.url,
            observed_validators=None, error=f"{failures} failed" if failures else None,
        )

    def healthcheck(self, fetcher: Fetcher, slug: str) -> BoardHealth:
        return BoardHealth.OK


def _loop_scan(
    engine: Engine, tmp_path: Path, provider: _DetailLoopProvider, **deadlines: float
) -> tuple[Any, float]:
    settings = Settings(
        data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1, scan_workers=1,
        per_host_delay_seconds=0.25, **deadlines,
    )
    fetcher = Fetcher(
        settings, client=httpx.Client(transport=httpx.MockTransport(provider.handler)),
        pacing=HostPacing(),
    )
    started = time.monotonic()
    summary = run_scan(engine, settings, providers={"greenhouse": provider}, fetcher=fetcher)
    return summary, started


@pytest.fixture
def looping() -> Iterator[_DetailLoopProvider]:
    loop = _DetailLoopProvider(chunks=40, interval=0.1)
    yield loop
    loop.stop.set()


def test_an_abandoned_board_stops_fetching_at_its_cap(
    engine: Engine, tmp_path: Path, looping: _DetailLoopProvider
) -> None:
    """T192c. The coordinator failing a board at its cap used to leave the thread running the
    provider's loop: each of its 20 requests got a fresh fetch deadline, so the worker stayed
    held for 20 × 0.2s. Under the board's own deadline the thread ends within one request of it."""
    ids = {"slow": _add_company(engine, "slow")}
    summary, started = _loop_scan(
        engine, tmp_path, looping, board_deadline_seconds=0.5, fetch_deadline_seconds=0.2
    )

    assert summary.failed == 1
    assert "slow: board deadline 0.5s exceeded" in summary.errors
    with engine.connect() as conn:
        status = conn.execute(
            select(tables.board_scans.c.status).where(
                tables.board_scans.c.company_id == ids["slow"]
            )
        ).scalar_one()
    assert status == "failed"
    deadline = started + 1.5
    while "slow" not in looping.ended and time.monotonic() < deadline:
        time.sleep(0.02)
    assert "slow" in looping.ended, "the abandoned thread was still fetching 1.5s in"
    assert looping.ended["slow"] - started < 1.0
    assert len(looping.requests) <= 5  # of 20


def test_a_board_its_own_clock_ended_is_failed_at_its_cap_when_the_thread_returns_first(
    engine: Engine, tmp_path: Path, looping: _DetailLoopProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T228. The thread's board clock and the coordinator's `wait` share ONE instant, so a loop
    that clock cuts short ends AT the cap, and which side sees it first is scheduling. Here the
    coordinator looks only after the thread has returned the snapshot its provider built from the
    clock's own failures ("20 failed"): the board is still failed under the cap's reason."""
    ids = {"slow": _add_company(engine, "slow")}
    real_wait = futures.wait
    raced: list[bool] = []

    def late_wait(
        fs: Iterable[Future[BoardSnapshot]], timeout: float | None = None, return_when: Any = None
    ) -> Any:
        pending = set(fs)
        if not raced:
            # The timeout fired, but the coordinator's thread ran only after the board's had
            # returned — a loaded macOS runner.
            raced.append(True)
            real_wait(pending)
            return set(), pending
        return real_wait(pending, timeout=timeout, return_when=return_when)

    monkeypatch.setattr(coordinator, "wait", late_wait)
    summary, _ = _loop_scan(
        engine, tmp_path, looping, board_deadline_seconds=0.5, fetch_deadline_seconds=0.2
    )

    assert raced == [True]
    assert len(looping.requests) <= 5  # the board's clock, not the provider's loop, ended it
    assert (summary.failed, summary.errors[0]) == (1, "slow: board deadline 0.5s exceeded")
    with engine.connect() as conn:
        row = conn.execute(
            select(tables.board_scans.c.status, tables.board_scans.c.error).where(
                tables.board_scans.c.company_id == ids["slow"]
            )
        ).one()
    assert tuple(row) == ("failed", "board deadline 0.5s exceeded")


def test_the_same_loop_under_generous_deadlines_makes_every_request(
    engine: Engine, tmp_path: Path
) -> None:
    """Control: the board-scoped deadline cuts nothing short that finishes inside it."""
    _add_company(engine, "slow")
    provider = _DetailLoopProvider(chunks=3, interval=0.02)
    summary, _ = _loop_scan(
        engine, tmp_path, provider, board_deadline_seconds=30.0, fetch_deadline_seconds=5.0
    )
    assert (summary.complete, summary.failed, summary.errors) == (1, 0, [])
    assert len(provider.requests) == 20


def test_a_board_queued_behind_an_abandoned_one_runs_soon_after_its_cap(
    engine: Engine, tmp_path: Path, looping: _DetailLoopProvider
) -> None:
    """T192c. With ONE worker, the abandoned thread holds the only slot: the healthy board behind
    it ran only when the provider's loop had run out — hours, on the live fleet."""
    ids = {slug: _add_company(engine, slug) for slug in ("slow", "acme")}
    summary, started = _loop_scan(
        engine, tmp_path, looping, board_deadline_seconds=0.5, fetch_deadline_seconds=0.2
    )

    assert (summary.failed, summary.complete) == (1, 1)
    assert looping.ended["acme"] - started < 2.0
    with engine.connect() as conn:
        statuses = dict(
            conn.execute(
                select(tables.board_scans.c.company_id, tables.board_scans.c.status)
            ).all()
        )
    assert statuses == {ids["slow"]: "failed", ids["acme"]: "complete"}
    assert not any("abandoned worker" in e for e in summary.errors)


def test_an_abandoned_worker_past_every_clock_is_reported_once(
    engine: Engine, tmp_path: Path, provider: _StuckProvider
) -> None:
    """T192c. `stuck` never touches the `Fetcher`, so no clock ends it — the stand-in for a peer
    trickling response headers. The wait on it is bounded per iteration: past its cap plus one
    fetch deadline it is reported as an error line, once, and the queue behind it still runs
    when it ends."""
    ids = {slug: _add_company(engine, slug) for slug in ("stuck", "acme")}
    settings = Settings(
        data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1, scan_workers=1,
        board_deadline_seconds=0.3, fetch_deadline_seconds=0.2,
    )
    threading.Timer(1.2, provider.release.set).start()
    summary = run_scan(engine, settings, providers={"greenhouse": provider})

    assert (summary.failed, summary.complete) == (1, 1)
    assert [e for e in summary.errors if "abandoned" in e] == [
        "scan: abandoned worker still running after 0.5s: stuck"
    ]
    with engine.connect() as conn:
        statuses = dict(
            conn.execute(
                select(tables.board_scans.c.company_id, tables.board_scans.c.status)
            ).all()
        )
    assert statuses == {ids["stuck"]: "failed", ids["acme"]: "complete"}


_WORKDAY_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "workday"
_WORKDAY_SLUG = "acme.wd5.myworkdayjobs.com/acme/AcmeCareers"


@pytest.mark.usefixtures("no_real_sleep")
def test_a_board_its_cap_would_cut_keeps_its_details_and_the_next_scan_fetches_only_the_rest(
    engine: Engine, tmp_path: Path
) -> None:
    """T243. db, hitachi, vfc and mtb failed at `board deadline 600s exceeded` on runs 475 AND
    476 with one stored posting each: a board the cap fails persists nothing, so its known ids
    never grow and every scan repeats the one before. Here the board's clock runs out after its
    first detail: the board is recorded `partial` with that posting, and the second scan fetches
    only the two it deferred, then completes."""
    listing = json.loads((_WORKDAY_FIXTURES / "list_normal.json").read_text(encoding="utf-8"))
    info = json.loads((_WORKDAY_FIXTURES / "detail_normal.json").read_text(encoding="utf-8"))
    details: list[str] = []
    out_of_time = [True]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json=listing)
        details.append(request.url.path)
        if out_of_time and out_of_time.pop():
            # The worker thread's own board clock (T192c): past it, as a slow host leaves it.
            fetcher._board.deadline.at = time.monotonic() - 1.0
        return httpx.Response(200, json=info)

    with engine.begin() as conn:
        company_id = int(
            conn.execute(
                insert(tables.companies).values(
                    name="Acme", provider="workday", slug=_WORKDAY_SLUG, source="user",
                    watched=True,
                )
            ).inserted_primary_key[0]
        )
    settings = Settings(
        data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1, scan_workers=1,
        per_host_delay_seconds=0.25,
    )
    fetcher = Fetcher(
        settings, client=httpx.Client(transport=httpx.MockTransport(handler)),
        pacing=HostPacing(),
    )

    def _scan() -> tuple[Any, int, Any]:
        summary = run_scan(
            engine, settings, providers={"workday": WorkdayProvider()}, fetcher=fetcher
        )
        with engine.connect() as conn:
            stored = conn.execute(
                select(func.count()).select_from(tables.postings).where(
                    tables.postings.c.company_id == company_id
                )
            ).scalar_one()
            scan = conn.execute(
                select(tables.board_scans.c.status, tables.board_scans.c.detail_deferred)
                .order_by(tables.board_scans.c.id.desc())
                .limit(1)
            ).one()
        return summary, int(stored), tuple(scan)

    first, stored, scan = _scan()
    assert (first.partial, first.failed, stored, scan) == (1, 0, 1, ("partial", 2))
    assert len(details) == 1

    second, stored, scan = _scan()
    assert (second.complete, second.failed, stored, scan) == (1, 0, 3, ("complete", 0))
    assert len(details) == 3  # the known-id skip: two more, not three


def _one_posting_scan(
    engine: Engine, tmp_path: Path, *, out_of_time_before_the_detail: bool
) -> tuple[Any, int, tuple[Any, ...]]:
    """One Workday board listing ONE posting, under a valid 30 s cap — below one default 240 s
    fetch deadline plus pacing. Optionally the board's clock runs out as the listing returns."""
    listing = json.loads((_WORKDAY_FIXTURES / "list_normal.json").read_text(encoding="utf-8"))
    listing = {**listing, "total": 1, "jobPostings": listing["jobPostings"][:1]}
    info = json.loads((_WORKDAY_FIXTURES / "detail_normal.json").read_text(encoding="utf-8"))

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            if out_of_time_before_the_detail:
                fetcher._board.deadline.at = time.monotonic() - 1.0
            return httpx.Response(200, json=listing)
        return httpx.Response(200, json=info)

    with engine.begin() as conn:
        company_id = int(
            conn.execute(
                insert(tables.companies).values(
                    name="Acme", provider="workday", slug=_WORKDAY_SLUG, source="user",
                    watched=True,
                )
            ).inserted_primary_key[0]
        )
    settings = Settings(
        data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1, scan_workers=1,
        per_host_delay_seconds=0.25, board_deadline_seconds=30.0,
    )
    fetcher = Fetcher(
        settings, client=httpx.Client(transport=httpx.MockTransport(handler)),
        pacing=HostPacing(),
    )
    summary = run_scan(engine, settings, providers={"workday": WorkdayProvider()}, fetcher=fetcher)
    with engine.connect() as conn:
        stored = conn.execute(
            select(func.count()).select_from(tables.postings).where(
                tables.postings.c.company_id == company_id
            )
        ).scalar_one()
        scan = conn.execute(
            select(tables.board_scans.c.status, tables.board_scans.c.error)
        ).one()
    return summary, int(stored), tuple(scan)


@pytest.mark.usefixtures("no_real_sleep")
def test_a_cap_below_one_fetch_deadline_still_fetches_the_first_detail(
    engine: Engine, tmp_path: Path
) -> None:
    """T243 round 2 (Codex). Guarded on the whole fetch deadline, a 30 s cap refused EVERY detail:
    `partial` with nothing fetched, the same posting deferred on every scan, forever."""
    summary, stored, scan = _one_posting_scan(engine, tmp_path, out_of_time_before_the_detail=False)
    assert (summary.complete, summary.partial, stored, scan) == (1, 0, 1, ("complete", None))


@pytest.mark.usefixtures("no_real_sleep")
def test_a_board_out_of_time_before_its_first_detail_is_failed_at_its_cap_as_before(
    engine: Engine, tmp_path: Path
) -> None:
    """T243 round 2. The first detail is never deferred, so a board cannot come back `partial`
    with nothing fetched — which the outage predicate would count as usable. It is sent, the
    board's clock cuts it, and the board takes the cap's `failed` exactly as before T243."""
    summary, stored, scan = _one_posting_scan(engine, tmp_path, out_of_time_before_the_detail=True)
    assert (summary.failed, summary.partial, stored) == (1, 0, 0)
    assert scan == ("failed", "board deadline 30s exceeded")


_COUNTS = (
    "board_reported_total", "board_enumerated", "detail_deferred", "board_total_censored",
    "throttle_retries", "throttle_exhausted",
)


def _counted(url: str) -> BoardSnapshot:
    """A provider's account of a board it listed and then lost to its cap: every count set."""
    return BoardSnapshot(
        status="partial", postings=[], url=url, error="1 detail failed",
        board_reported_total=9, board_enumerated=7, detail_deferred=2,
        board_total_censored=False, throttle_retries=3, throttle_exhausted=1,
    )


def test_a_board_its_own_clock_cut_keeps_its_provider_counts_on_the_caps_verdict(
    tmp_path: Path,
) -> None:
    """T248. When the board's own clock cuts it, the thread returns the cap's `failed` in place
    of the provider's snapshot (T228) — and that replaced the provider's counts too, so a board
    failed at its cap recorded no listing size and lost its throttle counts. The verdict is still
    the cap's; the counts are the provider's. No wall clock: the board's instant is already past."""

    class _Listed:
        def fetch_board(self, fetcher: Fetcher, request: BoardRequest) -> BoardSnapshot:
            with pytest.raises(FetchFailure):
                fetcher.get("https://acme.example/detail")  # the clock trips; nothing is sent
            return _counted(request.url)

    request = BoardRequest(provider="greenhouse", slug="acme", url="https://acme.example/b")
    fetcher = Fetcher(Settings(data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1))
    snapshot = fetch_board_job(
        _Listed(), fetcher, request, time.monotonic() - 1.0, 60.0  # type: ignore[arg-type]
    )

    assert (snapshot.status, snapshot.error, snapshot.postings) == (
        "failed", "board deadline 60s exceeded", []
    )
    assert {k: getattr(snapshot, k) for k in _COUNTS} == {
        k: getattr(_counted(request.url), k) for k in _COUNTS
    }


class _CountedStuckProvider(_StuckProvider):
    """`stuck` blocks until released and then reports every count; every other board completes
    at once, each on its own host."""

    def fetch_board(self, fetcher: Fetcher, request: BoardRequest) -> BoardSnapshot:
        if request.slug == "stuck":
            # A deadlock bound, not a race bound: the coordinator's own wait releases it, and a
            # short timeout here would let a descheduled CI worker return the board before the
            # coordinator could see it overdue.
            self.release.wait(timeout=120.0)
            return _counted(request.url)
        return super().fetch_board(fetcher, request)


def test_a_board_the_coordinator_failed_at_its_cap_keeps_the_counts_its_thread_returns(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T248. The coordinator fails a board still running at its cap before its thread has
    returned anything (run 475: db, hitachi, mtb, vfc), so the counts the provider took were
    lost. The board is now recorded when its thread ends — still `failed`, still under the cap's
    reason and seconds — carrying those counts into `board_scans` and the throttle totals.

    Released from inside the coordinator's own wait, not on a timer: the first wait times out at
    the cap with `stuck` blocked, and only a wait issued after the cap has failed it is bounded by
    the abandoned-thread report (cap plus a fetch deadline) rather than by the cap."""
    ids = {slug: _add_company(engine, slug) for slug in ("stuck", "acme")}
    settings = Settings(
        data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1, scan_workers=1,
        board_deadline_seconds=0.3,
    )
    assert settings.fetch_deadline_seconds > settings.board_deadline_seconds
    provider = _CountedStuckProvider()
    real_wait = futures.wait

    def releasing_wait(
        fs: Iterable[Future[BoardSnapshot]], timeout: float | None = None, return_when: Any = None
    ) -> Any:
        if timeout is not None and timeout > settings.board_deadline_seconds:
            provider.release.set()  # `stuck` is abandoned: its thread returns only now
        return real_wait(set(fs), timeout=timeout, return_when=return_when)

    monkeypatch.setattr(coordinator, "wait", releasing_wait)
    try:
        summary = run_scan(engine, settings, providers={"greenhouse": provider})
    finally:
        provider.release.set()

    assert (summary.failed, summary.complete) == (1, 1)
    assert "stuck: board deadline 0.3s exceeded" in summary.errors
    assert (summary.throttle_retries, summary.throttle_exhausted) == (3, ["stuck"])
    with engine.connect() as conn:
        row = conn.execute(
            select(tables.board_scans).where(tables.board_scans.c.company_id == ids["stuck"])
        ).one()
    assert (row.status, row.error, row.postings_listed) == (
        "failed", "board deadline 0.3s exceeded", 0
    )
    assert (
        row.board_reported_total, row.board_enumerated, row.detail_deferred,
        row.board_total_censored,
    ) == (9, 7, 2, 0)
    cost = summary.fetch_cost["greenhouse"]
    assert cost.untimed == 0 and cost.seconds >= settings.board_deadline_seconds
