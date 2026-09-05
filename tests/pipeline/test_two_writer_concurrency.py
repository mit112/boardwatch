"""Two OS processes writing one WAL store concurrently must not corrupt it or lose a write.

This is P3 item 8's same-OS half (PROGRAM.md §3.P3, WAL_DISCIPLINE.md). Concurrency here is
genuine: each writer is a real subprocess, because the property under test — that WAL +
busy_timeout let two processes append to `boardwatch.db` without corruption — belongs to the
operating system, and an in-process double would hold no kernel lock and prove nothing.

It is a regression guard for the discipline that already exists, not a red-first test. The
cross-OS half (a Linux container writing a macOS host bind-mount) cannot run in GitHub CI —
its mitigation is the runtime refusal in `store/fs_safety.py`, exercised by test_fs_safety.
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path
from time import perf_counter

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from boardwatch.store.db import ensure_schema, get_engine

#: Open the store as a fresh process and append `count` run rows, each its own transaction —
#: the smallest realistic write path (what every scan mints). Two of these racing is the test.
_WRITER = """
import sys
from pathlib import Path

from boardwatch.store.db import get_engine
from boardwatch.store.queries import insert_run

data_dir = Path(sys.argv[1])
count = int(sys.argv[2])
engine = get_engine(data_dir)
for _ in range(count):
    insert_run(engine)
print("OK", count, flush=True)
"""

_WRITES_EACH = 200


def test_two_processes_writing_concurrently_never_corrupt_or_lose_a_write(tmp_path: Path) -> None:
    data_dir = tmp_path / "store"
    engine = get_engine(data_dir)
    ensure_schema(engine)  # create the schema once, before the racers open it
    engine.dispose()  # release the parent's handle so the subprocesses are the only writers

    processes = [
        subprocess.Popen(
            [sys.executable, "-c", _WRITER, str(data_dir), str(_WRITES_EACH)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    outputs = [process.communicate(timeout=180) for process in processes]

    for (stdout, stderr), process in zip(outputs, processes, strict=True):
        assert process.returncode == 0, stderr  # a SQLITE_BUSY escape would fail here, loudly
        assert stdout.strip() == f"OK {_WRITES_EACH}"

    check_engine = get_engine(data_dir)
    with check_engine.connect() as conn:
        integrity = conn.execute(text("PRAGMA integrity_check")).scalar_one()
        total = conn.execute(text("SELECT COUNT(*) FROM runs")).scalar_one()
    assert integrity == "ok"  # no page corruption survived the concurrent writers
    assert total == 2 * _WRITES_EACH  # every write from both processes landed; none was lost


def test_a_deferred_read_then_write_loses_its_snapshot_the_moment_another_connection_commits(
    tmp_path: Path,
) -> None:
    """WHY T37 moved the lane apply off the background thread instead of raising `busy_timeout`.

    `apply_board` opens a DEFERRED transaction (`engine.begin()`) and READS -- to decide insert
    versus update -- before it writes. In WAL, upgrading that read snapshot to a write when any
    other connection has committed since the snapshot was taken fails with SQLITE_BUSY_SNAPSHOT,
    surfaced by the driver as `database is locked`. It is NOT a queueing failure: SQLite does not
    invoke the busy handler at all here, because no amount of waiting can make a stale snapshot
    writable -- the transaction has to be rolled back and retried from a fresh read.

    So the elapsed time is the load-bearing assertion, not the error. `busy_timeout` is 5,000 ms
    on this engine and run 3's lost board was read as a 5-second starvation; a failure that
    returns in milliseconds says the timeout was never consulted, and therefore that raising it
    -- T37's stated fallback -- could not have fixed anything. Removing the second writer is the
    only fix, which is what moving the apply to the join site does.
    """
    engine = get_engine(tmp_path / "store", busy_timeout_ms=5000)
    ensure_schema(engine)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE probe (id INTEGER PRIMARY KEY, v TEXT)"))

    started = perf_counter()
    with pytest.raises(OperationalError) as caught:
        with engine.begin() as coordinator:
            # The read half of a read-modify-write: this is what takes the snapshot.
            coordinator.execute(text("SELECT count(*) FROM probe")).one()
            # One commit from a SECOND connection, exactly as the lane stage had while the scan
            # coordinator was mid-`apply_board`. ONE is enough; a stream is not needed.
            with engine.connect() as lane:
                lane.execute(text("INSERT INTO probe (v) VALUES ('lane')"))
                lane.commit()
            coordinator.execute(text("INSERT INTO probe (v) VALUES ('board')"))
    elapsed = perf_counter() - started

    # The extended result code, not the message: `database is locked` is what a genuine
    # busy-timeout expiry says too, and the two demand opposite fixes.
    assert caught.value.orig is not None
    assert caught.value.orig.sqlite_errorcode == sqlite3.SQLITE_BUSY_SNAPSHOT
    assert elapsed < 1.0, (
        f"the write failed after {elapsed:.2f}s against a 5.0s busy_timeout -- if it ever does "
        "queue, this is a starvation failure and raising the timeout becomes a real option"
    )
