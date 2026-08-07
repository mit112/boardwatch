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
from provider_cases import ProviderCase
from sqlalchemy import Engine, func, select
from typer.testing import CliRunner

from boardwatch.cli.app import app
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
    assert elapsed < 2.0  # fail-fast: no fetch, no retries, no migration work
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
