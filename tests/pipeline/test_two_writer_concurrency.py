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
import threading
import time
from pathlib import Path
from time import perf_counter

import pytest
from sqlalchemy import insert, text
from sqlalchemy.exc import OperationalError

from boardwatch.core.models import BoardSnapshot, RawPosting
from boardwatch.scan import apply as apply_module
from boardwatch.scan.apply import ApplyResult, apply_board
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import insert_run

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


def _insert_company(engine) -> int:
    with engine.begin() as conn:
        result = conn.execute(
            insert(tables.companies).values(
                name="Acme", provider="greenhouse", slug="acme", source="user", watched=True,
            )
        )
        return int(result.inserted_primary_key[0])


def _posting(pid: str, body: str = "b") -> RawPosting:
    return RawPosting(
        provider_posting_id=pid, title=f"Job {pid}", url=f"https://x/{pid}",
        locations=[], body_text=body, raw_json={"id": pid},
    )


def test_a_deferred_apply_loses_a_board_when_a_concurrent_write_lands_mid_apply(
    tmp_path: Path,
) -> None:
    """D-475's fix, pinned against the REAL `apply_board` rather than the bare probe above.

    Unfixed, `apply_board` opens its DEFERRED transaction, reads inside `_apply_listed` (the
    `existing` postings query), and only then writes. If a second connection commits in that
    window, the write fails with SQLITE_BUSY_SNAPSHOT within milliseconds -- run 3's lost board.
    Fixed, `apply_board` takes the write lock at BEGIN (`write_connection` + `conn.begin()`), so
    the second connection's commit cannot land until the apply's transaction is done: it queues
    on the write lock instead of racing the snapshot, and the second writer's commit timestamp
    lands AFTER the apply has already returned.

    The second writer runs on its own thread and is never joined until after `apply_board`
    returns: under the fix, its commit blocks on the write lock the whole time `apply_board`
    holds it, so joining it first would deadlock the test against itself.
    """
    engine = get_engine(tmp_path / "store", busy_timeout_ms=5000)
    ensure_schema(engine)
    company_id = _insert_company(engine)
    run_id = insert_run(engine)
    snap = BoardSnapshot(
        status="complete",
        postings=[_posting("A"), _posting("B")],
        url="https://x/y",
        listed_ids=frozenset({"A", "B"}),
    )

    real_apply_listed = apply_module._apply_listed
    second_commit_at: list[float] = []
    second_writer_thread = threading.Thread(target=lambda: _second_writer(engine, second_commit_at))

    def wrapper(conn, raw_postings, company_id_, run_id_, source_url):
        # The read half of a read-modify-write: this is what takes the snapshot.
        conn.execute(text("SELECT count(*) FROM postings")).one()
        # Started on its own thread, and deliberately NOT joined here: under the fix its commit
        # blocks on the write lock this connection already holds, so joining now would deadlock.
        second_writer_thread.start()
        time.sleep(0.5)
        return real_apply_listed(conn, raw_postings, company_id_, run_id_, source_url)

    apply_module._apply_listed = wrapper  # type: ignore[assignment]
    try:
        result: ApplyResult = apply_board(engine, snap, company_id, run_id)
    finally:
        apply_module._apply_listed = real_apply_listed
    apply_returned_at = time.monotonic()

    second_writer_thread.join(timeout=10)
    assert not second_writer_thread.is_alive(), "second writer never finished -- deadlock"

    assert result.status != "failed"
    assert second_commit_at, "second writer thread never recorded a commit"
    assert second_commit_at[0] > apply_returned_at, (
        "the second writer's commit landed BEFORE apply_board returned -- it never queued on "
        "the write lock, so this run did not exercise the fix"
    )

    with engine.connect() as conn:
        posting_count = conn.execute(text("SELECT count(*) FROM postings")).scalar_one()
        run_count = conn.execute(text("SELECT count(*) FROM runs")).scalar_one()
    assert posting_count == 2  # both postings from the apply landed
    assert run_count == 2  # the setup run plus the second writer's run both landed


def _second_writer(engine, commit_times: list[float]) -> None:
    insert_run(engine)  # its own connection and transaction; commits internally
    commit_times.append(time.monotonic())
