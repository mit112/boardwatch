# SQLite concurrency & WAL discipline (P3 item 8 — the documented-stance half)

**This documents the concurrency stance that already exists in code, and names the one untested,
highest-risk configuration.** The two-writer *test* (esp. the cross-OS case) is item 8's remaining hard
half — deliberately NOT built yet (see "Known gap"). Verified against `src/boardwatch/store/db.py` and
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

## Known gap — item 8's REMAINING hard half (NOT built; needs fresh context + a real harness)
- **No two-writer TEST exists.** `tests/pipeline/test_scan_lock.py` proves the scan lock REJECTS a second
  scan (State-test j: second scan rejected, zero DB writes) — it does NOT exercise two processes writing the
  DB concurrently.
- **No cross-OS test.** boardwatch ships a Docker image over a host-mounted DB — the
  **Linux-container-plus-macOS-host** configuration that corrupted job-apps' primary key (PROGRAM.md §3.P3
  item 8). WAL over a network/host-mounted filesystem, or across an OS boundary, has known fragility that a
  same-OS test cannot surface. **A same-OS two-writer test would pass and prove nothing about the failure
  actually at risk.**
- **The remaining work:** a genuine cross-process (and ideally cross-OS: container writer + host writer over
  the mounted DB) concurrent-writer harness that asserts no corruption / no lost write / the PK stays
  intact. This is a hard test-infrastructure problem, deliberately left for a fresh context window.

## Fail-safe posture
The discipline is conservative: the scan lock fails CLOSED (a second scan is rejected, never runs
half-corrupting), and busy_timeout makes contention WAIT rather than error. The untested cross-OS path is a
monitoring/verification gap, not a known-broken behavior — but until the harness exists, running two writers
across the container/host boundary is NOT proven safe and should be avoided operationally.
