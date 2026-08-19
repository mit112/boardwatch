# SQLite concurrency & WAL discipline (P3 item 8)

**This documents the concurrency stance in code, and the test plus runtime guard that now enforce it
(D-241).** Verified against `src/boardwatch/store/db.py`, `src/boardwatch/store/fs_safety.py`, and
`src/boardwatch/scan/coordinator.py`.

## The configuration (every connection)
`store/db.py::get_engine` sets, via a SQLAlchemy `connect` event hook that runs on EVERY new DBAPI
connection (`db.py:26-31`):
- `PRAGMA journal_mode=WAL` — Write-Ahead Logging: concurrent readers are never blocked by the single
  writer, and a reader sees a consistent snapshot.
- `PRAGMA busy_timeout=5000` (default; `Settings.busy_timeout_ms`) — a connection that hits a locked DB
  waits up to 5s for the lock rather than failing immediately with `SQLITE_BUSY`.
- `PRAGMA foreign_keys=ON` — FK enforcement (the eligibility/artifacts FKs are load-bearing).

## The single-writer discipline
1. **The scan lock serializes whole SCANS, not the database.** `scan/coordinator.py` takes a
   `filelock.FileLock` on `scan.lock` before schema setup / the run insert / any fetch. It ensures at most
   ONE scan (the large, sustained writer) runs at a time; a second scan is rejected fast (`ScanLockHeldError`
   → exit 2) with zero DB writes. It is NOT a database lock.
2. **Within a scan, `apply_board` is the serial single writer** — board snapshots are applied one at a time,
   so there is never concurrent scan-write contention inside a run.
3. **WAL + busy_timeout make the rest safe alongside a running scan (D-020):** read-mostly paths (`top`,
   `show`, `stats`, `verify`, the eligibility read path) and small writes (a single evaluation/artifact row,
   `finish_run`, `track`) coexist with a running scan — readers use the WAL snapshot, a small write that
   momentarily contends waits out the 5s busy_timeout. This is why the scan lock does not need to be a
   database lock.

## Why this holds for the unattended daily driver
`boardwatch run` scan→eligibility→tailor runs under the scan lock (the run row is minted inside it). No
second scan can interleave. The eligibility and tailor stages are the same process writing serially. So the
only cross-process concurrency in normal operation is (a running scan) × (an ad-hoc read like `verify`/
`show`), which WAL handles by construction.

## The two-writer test (same-OS) and the cross-OS guard
The two halves of item 8's risk are handled differently, because only one of them can run in CI.

- **Same-OS — a real test.** `tests/pipeline/test_two_writer_concurrency.py` spawns two subprocesses that
  each append 200 run rows to `boardwatch.db` concurrently, then asserts `PRAGMA integrity_check == "ok"` and
  that all 400 writes landed (no lost write, no corruption). Genuine kernel-level concurrency — real
  processes, not an in-process double. This is the regression guard for WAL + busy_timeout under contention.
- **Cross-OS — a runtime refusal, not a test.** boardwatch ships a Docker image over a host-mounted DB — the
  **Linux-container-plus-macOS-host** configuration that corrupted job-apps' primary key. WAL over a
  network/host-mounted filesystem, or across the container/host boundary, has known fragility, and **a
  same-OS test would pass and prove nothing about it.** GitHub's macOS runners cannot run Docker, so that
  config can never be a green CI check. The mitigation is prevention: `store/fs_safety.py::unsafe_wal_filesystem`
  reads `/proc/self/mountinfo` and `get_engine` **refuses** (`WalUnsafeFilesystemError`) when the store sits
  on a WAL-unsafe filesystem — a host bind-mount reads inside the container as `virtiofs`/`fuse.grpcfuse`/etc.,
  while a named Docker volume reads as the container's own `ext4`/`overlay` and is cleared. Detection is
  Linux-only; on macOS/Windows there is no `/proc/self/mountinfo`, the host side is normal local disk, and
  the guard is a no-op, so it never refuses a legitimate local run.

## Fail-safe posture
The discipline fails CLOSED at three points: the scan lock rejects a second scan rather than running
half-corrupting; busy_timeout makes contention WAIT rather than error; and `get_engine` refuses outright on a
WAL-unsafe filesystem rather than opening a store that concurrent writers could corrupt. Refusal on a
network share is a false-positive cost the operator resolves by moving the store to local disk — a recoverable
inconvenience, deliberately chosen over the unrecoverable data loss of silent corruption.
