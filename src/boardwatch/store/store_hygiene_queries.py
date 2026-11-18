"""Store and data hygiene (T313): quarantine drain, duplicate grouping, store size, big tables.

Four readings, each cheap on the 50 GB live store:

* **Quarantine and its drain.** `quarantined_bodies` holds a body withheld from the rules until
  the drain sets `reopened_at`; every quarantine needs a drain, so this shows whether it runs.
  Held is `reopened_at IS NULL`; drained is set. The drain stamps no run id, so drained-per-week
  is by `reopened_at`, beside quarantined-per-week by `quarantined_at` (the FIRST time a version was
  held: a re-record never resets it). A re-quarantine clears `reopened_at`
  (`quarantine_queries.record_quarantine`) but copies it to `last_drained_at` first, so a version
  drained and held again counts as held, and its drain still counts in the last-drain time, the
  stall test and the weekly drained column. Only the latest drain of a re-held version is kept.
  `stalled` is set when anything is held and nothing has drained for `STALL_DAYS`.
* **Duplicate grouping.** `job_grouping_events` rows are postings moved from one job into a
  survivor (`regroup.apply_merges`). Counted by method and algorithm version and per week, and
  as a rate per 1000 postings ever stored. Postings come from the largest-tables reading below:
  exact when `COUNT(*)` finishes inside its budget, the highest rowid otherwise.
* **Store size.** The db file and its `-wal`, by `os.stat`, now. Each nightly run's funnel
  artifact records both at assembly (T317), so the last runs' sizes are read back from those files
  (`api.run_trends_payload` hands them in) and growth is the db file's change since the run
  before. A run whose funnel predates the field, or whose stat failed, has no figure and no
  growth, never 0; so has the first run of the series. The WAL is shown, not differenced: it
  swings with checkpoints. This adds no write path.
* **Largest tables.** `COUNT(*)` per table, each given `COUNT_BUDGET_SECONDS` and then
  interrupted. A table that cannot be counted in time (the big ones: a full count is minutes
  on the 50 GB store) falls back to `MAX(rowid)` and is marked not exact: the rowid counts rows
  ever inserted, so it reads high on a table that deletes, and far too high on a sparse one
  (a quarantine keyed by posting version id). `dbstat` would read the whole file.

Read-only. The store mixes naive-UTC and offset-carrying text in every DateTime column, so no
SQL orders or compares a raw timestamp: they are read whole and normalised in Python.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, select
from sqlalchemy.exc import OperationalError

from boardwatch.store.lead_aging_queries import _naive
from boardwatch.store.tables import job_grouping_events, quarantined_bodies

#: Held bodies with no drain for this long are flagged. The drain only releases a body whose
#: marker catalog was corrected, so a quiet fortnight is normal; a quiet month is not.
STALL_DAYS = 14
WEEKS = 8
TABLE_ROWS = 10
#: Time one exact `COUNT(*)` may take before it is interrupted and the table is estimated instead.
#: Measured on the live store (cold, 29 tables): 15 count in 0.15 s or less; the other 14 take
#: 0.35 s to 29 s. The worst case is 14 x 0.1 s spent on interrupted counts.
COUNT_BUDGET_SECONDS = 0.1
_SECONDS_PER_DAY = 86400


def _week_start(stamp: datetime) -> datetime:
    day = stamp.replace(hour=0, minute=0, second=0, microsecond=0)
    return day - timedelta(days=day.weekday())


def _weekly(stamps: list[datetime], now: datetime) -> list[tuple[str, int]]:
    """Counts for the last `WEEKS` Monday-start weeks, oldest first, empty weeks as zero."""
    this_week = _week_start(now)
    starts = [this_week - timedelta(weeks=n) for n in range(WEEKS - 1, -1, -1)]
    counts = Counter(_week_start(s) for s in stamps)
    return [(start.date().isoformat(), counts.get(start, 0)) for start in starts]


def _quarantine(conn: Connection, now: datetime) -> dict[str, Any]:
    # `last_drained_at` arrives with migration p_quarantine_last_drained, which runs on the next
    # pipeline start; a viewer restarted on the new code before that reads a store without it.
    # Read-only, so it cannot migrate: it reads without the column and keeps the current drains.
    migrated = any(
        str(r[1]) == "last_drained_at"
        for r in conn.exec_driver_sql("PRAGMA table_info(quarantined_bodies)")
    )
    columns = [quarantined_bodies.c.quarantined_at, quarantined_bodies.c.reopened_at]
    if migrated:
        columns.append(quarantined_bodies.c.last_drained_at)
    rows = conn.execute(select(*columns)).all()
    held = [_naive(r.quarantined_at) for r in rows if r.reopened_at is None]
    drained = [_naive(r.reopened_at) for r in rows if r.reopened_at is not None]
    # Every drain still on record: the current ones, plus the earlier drain of a version that was
    # held again. `drained` (the count) stays the versions drained NOW.
    drains = drained + [
        _naive(r.last_drained_at) for r in rows if migrated and r.last_drained_at is not None
    ]
    oldest = min(held) if held else None
    last_drain = max(drains) if drains else None
    since_drain = (now - last_drain).total_seconds() / _SECONDS_PER_DAY if last_drain else None
    return {
        "held": len(held),
        "drained": len(drained),
        # Age of the longest-held body, in days; None when nothing is held.
        "oldest_held_days": (
            round(max(0.0, (now - oldest).total_seconds() / _SECONDS_PER_DAY), 1)
            if oldest
            else None
        ),
        "last_drained_at": last_drain.isoformat() if last_drain else None,
        "days_since_drain": round(max(0.0, since_drain), 1) if since_drain is not None else None,
        "stall_days": STALL_DAYS,
        # Anything held, and either no drain ever or none inside the window.
        "stalled": bool(held) and (since_drain is None or since_drain > STALL_DAYS),
        "weekly": [
            {"week_start": week, "quarantined": q, "drained": d}
            for (week, q), (_, d) in zip(
                _weekly([_naive(r.quarantined_at) for r in rows], now),
                _weekly(drains, now),
                strict=True,
            )
        ],
    }


def _grouping(conn: Connection, now: datetime, postings_approx: int | None) -> dict[str, Any]:
    rows = conn.execute(
        select(
            job_grouping_events.c.from_job_id,
            job_grouping_events.c.method,
            job_grouping_events.c.algorithm_version,
            job_grouping_events.c.created_at,
        )
    ).all()
    # A merge moves a posting OUT of another job. An event with no source job is not a duplicate.
    merges = [r for r in rows if r.from_job_id is not None]
    methods = Counter((r.method, r.algorithm_version) for r in merges)
    return {
        "merges": len(merges),
        "merged_jobs": len({int(r.from_job_id) for r in merges}),
        "without_source_job": len(rows) - len(merges),
        "postings_approx": postings_approx,
        "per_1000_postings": (
            round(len(merges) * 1000 / postings_approx, 2) if postings_approx else None
        ),
        "methods": [
            {"method": m, "algorithm_version": v, "count": n}
            for (m, v), n in sorted(
                methods.items(), key=lambda kv: (-kv[1], kv[0][0], kv[0][1] or "")
            )
        ],
        "weekly": [
            {"week_start": week, "merges": n}
            for week, n in _weekly([_naive(r.created_at) for r in merges], now)
        ],
    }


def _file_bytes(path: Path) -> int:
    try:
        return os.stat(path).st_size
    except FileNotFoundError:
        return 0


def _scalar_within(conn: Connection, sql: str, budget: float) -> int | None:
    """The single integer `sql` returns, or None when it ran past `budget` seconds.

    SQLite's progress handler never fires inside `COUNT(*)` (one opcode), so the statement is
    cut short with `interrupt()` from a timer. `timed_out` is set by the timer, so only our own
    interrupt is swallowed; any other database error still raises.
    """
    raw = conn.connection.driver_connection
    timed_out = threading.Event()
    # The statement and the timer race: a callback already past `cancel()` could interrupt the
    # NEXT statement on this connection (Codex T318). `done` is set under the lock before this
    # returns, and the callback interrupts only while holding it and seeing `done` unset.
    lock = threading.Lock()
    done = False

    def _stop() -> None:
        with lock:
            if done:
                return
            timed_out.set()
            raw.interrupt()  # type: ignore[union-attr]

    timer = threading.Timer(budget, _stop)
    timer.start()
    try:
        return int(conn.exec_driver_sql(sql).scalar() or 0)
    except OperationalError as exc:
        code = getattr(exc.orig, "sqlite_errorcode", None)
        if not timed_out.is_set() or code != sqlite3.SQLITE_INTERRUPT:
            raise
        return None
    finally:
        with lock:
            done = True
        timer.cancel()
        timer.join()


def _table_rows(
    conn: Connection, budget: float = COUNT_BUDGET_SECONDS
) -> dict[str, tuple[int, bool]]:
    """Per table: (rows, exact). Exact is `COUNT(*)`; otherwise the highest rowid."""
    # Names come from the store's own catalog, never from a request.
    tables = [
        str(row[0])
        for row in conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    ]
    sizes: dict[str, tuple[int, bool]] = {}
    for name in tables:
        quoted = '"' + name.replace('"', '""') + '"'
        exact = _scalar_within(conn, f"SELECT COUNT(*) FROM {quoted}", budget)  # noqa: S608
        if exact is not None:
            sizes[name] = (exact, True)
        else:
            top = conn.exec_driver_sql(f"SELECT MAX(rowid) FROM {quoted}").scalar()  # noqa: S608
            sizes[name] = (int(top or 0), False)
    return sizes


def _size_series(recorded: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per run, oldest first, with the db file's growth since the run before it.

    `recorded` is the nightly runs as `api.run_trends_payload` returns them. Growth needs both
    this run and the one before it to have a db size; otherwise it is `None`, never 0.
    """
    series: list[dict[str, Any]] = []
    previous: int | None = None
    for point in recorded:
        size = point.get("store_size")
        db = size.get("db_bytes") if isinstance(size, dict) else None
        wal = size.get("wal_bytes") if isinstance(size, dict) else None
        series.append(
            {
                "run_id": point["id"],
                "finished": point.get("finished"),
                "db_bytes": db,
                "wal_bytes": wal,
                "growth_bytes": db - previous if db is not None and previous is not None else None,
            }
        )
        previous = db
    return series


def store_hygiene(
    conn: Connection,
    db_path: Path,
    now: datetime | None = None,
    recorded: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    at = _naive(now) if now is not None else datetime.now(UTC).replace(tzinfo=None)
    sizes = _table_rows(conn)
    db_bytes = _file_bytes(db_path)
    wal_bytes = _file_bytes(db_path.with_name(db_path.name + "-wal"))
    series = _size_series(recorded or [])
    largest = sorted(sizes.items(), key=lambda kv: (-kv[1][0], kv[0]))[:TABLE_ROWS]
    return {
        "quarantine": _quarantine(conn, at),
        "grouping": _grouping(conn, at, sizes.get("postings", (0, False))[0]),
        "store": {
            "db_bytes": db_bytes,
            "wal_bytes": wal_bytes,
            "total_bytes": db_bytes + wal_bytes,
            # True once at least one of the runs shown has a recorded db size.
            "growth_recorded": any(row["db_bytes"] is not None for row in series),
            "series": series,
        },
        # `exact` is per row: a table counted in time is a count, the rest are a highest rowid.
        "tables": {
            "rows": [
                {"name": name, "rows": rows, "exact": exact} for name, (rows, exact) in largest
            ],
        },
    }
