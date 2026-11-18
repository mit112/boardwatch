"""Store and data hygiene (T313): quarantine drain, duplicate grouping, store size, big tables.

Four readings, each cheap on the 50 GB live store:

* **Quarantine and its drain.** `quarantined_bodies` holds a body withheld from the rules until
  the drain sets `reopened_at`; every quarantine needs a drain, so this shows whether it runs.
  Held is `reopened_at IS NULL`; drained is set. The drain stamps no run id, so drained-per-week
  is by `reopened_at`, beside quarantined-per-week by `quarantined_at`. A re-quarantine clears
  `reopened_at` (`quarantine_queries.record_quarantine`), so a version drained and held again
  counts as held only: the weekly drained column is a floor, not a full history. `stalled` is
  set when anything is held and nothing has drained for `STALL_DAYS`.
* **Duplicate grouping.** `job_grouping_events` rows are postings moved from one job into a
  survivor (`regroup.apply_merges`). Counted by method and algorithm version and per week, and
  as a rate per 1000 postings ever stored. Postings are counted by their highest rowid, not
  `COUNT(*)`: the table carries body text, and the rowid is exact until a row is deleted.
* **Store size.** The db file and its `-wal`, by `os.stat`. Nothing in the store or a run report
  records the size per run, so growth is reported as unrecorded; this adds no write path.
* **Largest tables.** `MAX(rowid)` per table, approximate: it counts rows ever inserted, so a
  table that deletes reads high. `dbstat` would read the whole file.

Read-only. The store mixes naive-UTC and offset-carrying text in every DateTime column, so no
SQL orders or compares a raw timestamp: they are read whole and normalised in Python.
"""

from __future__ import annotations

import os
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, select

from boardwatch.store.lead_aging_queries import _naive
from boardwatch.store.tables import job_grouping_events, quarantined_bodies

#: Held bodies with no drain for this long are flagged. The drain only releases a body whose
#: marker catalog was corrected, so a quiet fortnight is normal; a quiet month is not.
STALL_DAYS = 14
WEEKS = 8
TABLE_ROWS = 10
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
    rows = conn.execute(
        select(quarantined_bodies.c.quarantined_at, quarantined_bodies.c.reopened_at)
    ).all()
    held = [_naive(r.quarantined_at) for r in rows if r.reopened_at is None]
    drained = [_naive(r.reopened_at) for r in rows if r.reopened_at is not None]
    oldest = min(held) if held else None
    last_drain = max(drained) if drained else None
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
                _weekly(drained, now),
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


def _table_rows(conn: Connection) -> dict[str, int]:
    # Names come from the store's own catalog, never from a request.
    tables = [
        str(row[0])
        for row in conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    ]
    sizes: dict[str, int] = {}
    for name in tables:
        quoted = '"' + name.replace('"', '""') + '"'
        top = conn.exec_driver_sql(f"SELECT MAX(rowid) FROM {quoted}").scalar()  # noqa: S608
        sizes[name] = int(top or 0)
    return sizes


def store_hygiene(
    conn: Connection, db_path: Path, now: datetime | None = None
) -> dict[str, Any]:
    at = _naive(now) if now is not None else datetime.now(UTC).replace(tzinfo=None)
    sizes = _table_rows(conn)
    db_bytes = _file_bytes(db_path)
    wal_bytes = _file_bytes(db_path.with_name(db_path.name + "-wal"))
    largest = sorted(sizes.items(), key=lambda kv: (-kv[1], kv[0]))[:TABLE_ROWS]
    return {
        "quarantine": _quarantine(conn, at),
        "grouping": _grouping(conn, at, sizes.get("postings")),
        "store": {
            "db_bytes": db_bytes,
            "wal_bytes": wal_bytes,
            "total_bytes": db_bytes + wal_bytes,
            # Neither `runs` nor a run report records the size, so there is no series to draw.
            "growth_recorded": False,
        },
        "tables": {
            "approximate": True,
            "rows": [{"name": name, "rows": rows} for name, rows in largest],
        },
    }
