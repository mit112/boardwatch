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

import subprocess
import sys
from pathlib import Path

from sqlalchemy import text

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
