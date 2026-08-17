"""State test j (D20): a second concurrent scan is rejected fast with ZERO DB writes.

Cross-platform by construction: filelock + subprocess + sys.executable, no
POSIX-only APIs — Windows CI is the real reviewer here.
"""

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from filelock import Timeout
from provider_cases import ProviderCase
from sqlalchemy import Engine, func, select
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.core.lock_reclaim import RECLAIM_WINDOW_SECONDS
from boardwatch.core.settings import Settings
from boardwatch.scan import coordinator
from boardwatch.scan.coordinator import SCAN_LOCK_MESSAGE, ScanLockHeldError, run_scan
from boardwatch.store import tables
from boardwatch.store.db import DB_FILENAME, ensure_schema, get_engine

runner = CliRunner()

HOLDER_SCRIPT = """
import sys, time
from filelock import FileLock
lock = FileLock(sys.argv[1])
lock.acquire()
print("HELD", flush=True)
time.sleep(60)
"""


def _row_count(engine: Engine, table: object) -> int:
    with engine.connect() as conn:
        return int(conn.execute(select(func.count()).select_from(table)).scalar_one())


@pytest.fixture()
def held_lock(tmp_path: Path) -> object:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    proc = subprocess.Popen(
        [sys.executable, "-c", HOLDER_SCRIPT, str(data_dir / "scan.lock")],
        stdout=subprocess.PIPE, text=True,
    )
    assert proc.stdout is not None
    assert proc.stdout.readline().strip() == "HELD"  # wait until truly held
    yield data_dir
    proc.kill()
    proc.wait()


def test_j_second_scan_rejected_fast_with_zero_db_writes(
    held_lock: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: ProviderCase
) -> None:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    data_dir = held_lock  # NO database exists yet — rejection must not create one

    start = time.monotonic()
    result = runner.invoke(app, ["--data-dir", str(data_dir), "scan"])
    elapsed = time.monotonic() - start

    assert result.exit_code == 2
    assert SCAN_LOCK_MESSAGE in result.output
    # fail-fast: no fetch, no retries, no migration work. Read from the emitter rather than restated,
    # because on Windows a genuine refusal pays the reclaim window first (D-227) — zero off Windows,
    # so this stays the 2.0s budget everywhere the holder is alive and the OS answers at once.
    assert elapsed < RECLAIM_WINDOW_SECONDS + 2.0
    # ZERO DB writes — not even schema creation touched the disk:
    assert not (data_dir / DB_FILENAME).exists()

    engine = get_engine(data_dir)
    ensure_schema(engine)
    assert _row_count(engine, tables.runs) == 0  # no runs row
    assert _row_count(engine, tables.board_scans) == 0  # no board_scans, nothing


def test_lock_message_is_exact() -> None:
    assert SCAN_LOCK_MESSAGE == "another scan is already running; try again when it finishes."


def test_lock_released_on_success_and_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "data"
    engine = get_engine(data_dir)
    ensure_schema(engine)
    settings = Settings(data_dir=data_dir, config_dir=tmp_path)

    run_scan(engine, settings)  # no watched companies: trivially succeeds
    run_scan(engine, settings)  # would deadlock/raise if the lock leaked

    def boom(engine_: object) -> int:
        raise RuntimeError("injected failure after lock acquisition")

    monkeypatch.setattr("boardwatch.scan.coordinator.insert_run", boom)
    with pytest.raises(RuntimeError, match="injected failure"):
        run_scan(engine, settings)
    monkeypatch.undo()
    run_scan(engine, settings)  # lock was released on the failure path too


def test_reads_work_while_scan_lock_is_held(
    held_lock: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The lock serializes `scan` only — it is not a database lock (D20: WAL +
    # busy_timeout keep reads and small writes safe alongside a running scan).
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    engine = get_engine(held_lock)
    ensure_schema(engine)
    version_result = runner.invoke(app, ["version"])
    assert version_result.exit_code == 0
    assert _row_count(engine, tables.postings) == 0  # direct reads succeed too


def test_sidecar_written_on_acquire_and_removed_on_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P3 slice 2 item 1 (notify-loudly): the sidecar exists while the lock is held, with this
    process's pid/hostname/started_at, and is gone once the lock is released."""
    data_dir = tmp_path / "data"
    engine = get_engine(data_dir)
    ensure_schema(engine)
    settings = Settings(data_dir=data_dir, config_dir=tmp_path)
    meta_path = data_dir / "scan.lock.meta"

    real_insert_run = coordinator.insert_run
    seen: dict[str, object] = {}

    def spy_insert_run(engine_: object) -> int:
        # insert_run runs INSIDE the scan lock, so this is the moment to check the sidecar.
        assert meta_path.exists()
        seen["meta"] = json.loads(meta_path.read_text())
        return real_insert_run(engine_)  # type: ignore[arg-type]

    monkeypatch.setattr(coordinator, "insert_run", spy_insert_run)
    run_scan(engine, settings)

    meta = seen["meta"]
    assert isinstance(meta, dict)
    assert meta["pid"] == os.getpid()
    assert meta["hostname"] == socket.gethostname()
    assert isinstance(meta["started_at"], str) and meta["started_at"]
    assert not meta_path.exists()


def test_contention_with_valid_sidecar_names_blocking_pid(
    held_lock: Path, tmp_path: Path
) -> None:
    data_dir = held_lock
    meta_path = data_dir / "scan.lock.meta"
    meta_path.write_text(
        json.dumps(
            {"pid": 999999, "hostname": "some-other-host", "started_at": "2026-08-07T00:00:00"}
        )
    )
    engine = get_engine(data_dir)
    ensure_schema(engine)
    settings = Settings(data_dir=data_dir, config_dir=tmp_path)

    with pytest.raises(ScanLockHeldError) as exc_info:
        run_scan(engine, settings)

    message = str(exc_info.value)
    assert "999999" in message
    assert "some-other-host" in message


def test_contention_with_missing_sidecar_falls_back_to_generic_message(
    held_lock: Path, tmp_path: Path
) -> None:
    data_dir = held_lock  # no scan.lock.meta written by anyone
    engine = get_engine(data_dir)
    ensure_schema(engine)
    settings = Settings(data_dir=data_dir, config_dir=tmp_path)

    with pytest.raises(ScanLockHeldError) as exc_info:
        run_scan(engine, settings)

    assert str(exc_info.value) == SCAN_LOCK_MESSAGE


def test_contention_with_malformed_sidecar_falls_back_to_generic_message(
    held_lock: Path, tmp_path: Path
) -> None:
    data_dir = held_lock
    (data_dir / "scan.lock.meta").write_bytes(b"\x00\x01not-json{{{")
    engine = get_engine(data_dir)
    ensure_schema(engine)
    settings = Settings(data_dir=data_dir, config_dir=tmp_path)

    with pytest.raises(ScanLockHeldError) as exc_info:
        run_scan(engine, settings)

    assert str(exc_info.value) == SCAN_LOCK_MESSAGE


def test_second_in_process_scan_raises_typed_error(tmp_path: Path) -> None:
    from filelock import FileLock

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    engine = get_engine(data_dir)
    ensure_schema(engine)
    lock = FileLock(str(data_dir / "scan.lock"))
    lock.acquire()
    try:
        with pytest.raises(ScanLockHeldError):
            run_scan(engine, Settings(data_dir=data_dir, config_dir=tmp_path))
    finally:
        lock.release()


# --------------------------------------------------------------------------------------
# The reclaim window (D-227). The scan lock inherits the same platform defect as the bundle
# writer lock: `filelock` swallows the EACCES Windows returns while a killed holder's handles are
# torn down, so an acquire lands on `Timeout` for a lock nobody holds. These run on every platform
# by driving the window directly — the Windows path itself cannot be exercised here.
# --------------------------------------------------------------------------------------


class _ScriptedLock:
    """A `FileLock` stand-in that refuses a scripted number of asks before it yields.

    Models only what `run_scan` uses: `acquire(blocking=False)` and `release()`. Refuses to be asked
    past a ceiling so that a wait which lost its deadline fails loudly instead of hanging — a hang is
    not a failure.
    """

    def __init__(self, refusals: int, ceiling: int = 1_000) -> None:
        self.refusals = refusals
        self.ceiling = ceiling
        self.attempts = 0
        self.releases = 0

    def __call__(self, path: str) -> "_ScriptedLock":
        return self

    def acquire(self, *, blocking: bool) -> None:
        assert blocking is False, "the acquire must stay non-blocking; the window is run_scan's"
        self.attempts += 1
        if self.attempts > self.ceiling:
            raise AssertionError(
                f"the scan lock was asked {self.attempts} times: the wait has lost its deadline"
            )
        if self.attempts <= self.refusals:
            raise Timeout("scripted refusal")

    def release(self) -> None:
        self.releases += 1


#: The window these tests drive. Named so the bounded-wait assertion derives its budget from the
#: window rather than restating a number.
_WINDOW = 0.05


def _prepared(tmp_path: Path) -> tuple[Engine, Settings]:
    """An engine with the schema already created, plus settings pointing at it.

    Deliberately a separate step so no timed region contains it. `get_engine` + `ensure_schema`
    create a SQLite file and run the whole DDL: ~50ms here, but **over a second on a Windows CI
    runner**. Timing that alongside the acquire is what made this file's bounded-wait assertion
    measure the filesystem instead of the window, and it failed on Windows only (D-227).
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    engine = get_engine(data_dir)
    ensure_schema(engine)
    return engine, Settings(data_dir=data_dir, config_dir=tmp_path)


def test_a_refusal_that_clears_inside_the_window_is_retried_not_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The point of the window: a killed scan's leftover lock must not refuse the next scan.

    On the unattended path this is the difference between a run and a silent empty day.
    """
    engine, settings = _prepared(tmp_path)
    lock = _ScriptedLock(refusals=2)
    monkeypatch.setattr(coordinator, "FileLock", lock)
    monkeypatch.setattr(coordinator, "RECLAIM_WINDOW_SECONDS", 1.0)
    monkeypatch.setattr(coordinator, "RECLAIM_POLL_SECONDS", 0.001)

    run_scan(engine, settings)

    assert lock.attempts == 3, "the window must re-ask, not believe the first refusal"
    assert lock.releases == 1, "the scan still releases what it took"


def test_a_refusal_that_stands_is_reported_after_the_window_and_the_wait_is_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A live holder still gets the typed refusal, and the window bounds the wait."""
    engine, settings = _prepared(tmp_path)
    lock = _ScriptedLock(refusals=10_000)
    monkeypatch.setattr(coordinator, "FileLock", lock)
    monkeypatch.setattr(coordinator, "RECLAIM_WINDOW_SECONDS", _WINDOW)
    monkeypatch.setattr(coordinator, "RECLAIM_POLL_SECONDS", 0.001)

    # Only the acquire is timed. The stand-in never yields, so `run_scan` raises before it reaches
    # any scan work at all — what is left in here is the wait and nothing else.
    started = time.monotonic()
    with pytest.raises(ScanLockHeldError):
        run_scan(engine, settings)
    elapsed = time.monotonic() - started

    assert lock.attempts > 1, "a window that asks once is not a window"
    assert elapsed < _WINDOW + 1.0, "the wait is bounded by the window, never by the holder"
    assert lock.releases == 0, "nothing was acquired, so nothing may be released"


def test_without_a_window_the_scan_lock_is_asked_exactly_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POSIX's behaviour, unchanged: one ask, no wait, and state test j's fail-fast still holds."""
    engine, settings = _prepared(tmp_path)
    lock = _ScriptedLock(refusals=1)
    monkeypatch.setattr(coordinator, "FileLock", lock)
    monkeypatch.setattr(coordinator, "RECLAIM_WINDOW_SECONDS", 0.0)

    with pytest.raises(ScanLockHeldError):
        run_scan(engine, settings)

    assert lock.attempts == 1


def test_the_window_is_asked_for_on_windows_only() -> None:
    """Both locks read one constant, so this pins the shared platform contract from the scan side."""
    if sys.platform == "win32":  # pragma: win32 cover
        assert coordinator.RECLAIM_WINDOW_SECONDS > 0
    else:  # pragma: win32 no cover
        assert coordinator.RECLAIM_WINDOW_SECONDS == 0.0


def test_the_two_locks_share_one_window_rather_than_agreeing_by_coincidence(
    tmp_path: Path,
) -> None:
    """The bundle lock and the scan lock must not drift apart.

    Both bind the constant by name from `core.lock_reclaim`, so this compares the two bindings
    against the source rather than against each other's literals.
    """
    from boardwatch.core import lock_reclaim
    from boardwatch.profile_bundle import locking

    assert coordinator.RECLAIM_WINDOW_SECONDS == lock_reclaim.RECLAIM_WINDOW_SECONDS
    assert locking.RECLAIM_WINDOW_SECONDS == lock_reclaim.RECLAIM_WINDOW_SECONDS
    assert coordinator.RECLAIM_POLL_SECONDS == lock_reclaim.RECLAIM_POLL_SECONDS
    assert locking.RECLAIM_POLL_SECONDS == lock_reclaim.RECLAIM_POLL_SECONDS
