"""Typed access to the app_state text KV table.

app_state holds small pieces of cross-command state that are not domain rows. The digest
cursor (D18) is one key: the highest posting_events id the user has already been shown
in a digest. The notify cursor is a second, independent key: the highest posting_events
id the user has already been notified about. It is a text PK table, so writes are
delete-then-insert rather than an upsert dialect feature, keeping this portable across
the SQLAlchemy Core surface the rest of the store uses. Functions take the caller's open
Connection and never begin or commit.

A crash after terminal output can still re-render a window. Exactly-once terminal
rendering is not achievable transactionally, and claiming it would be false.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from typing import NamedTuple

from sqlalchemy import Connection, delete, insert, select

from boardwatch.store.tables import app_state

DIGEST_CURSOR_KEY = "last_digest_event_id"


def get_state(conn: Connection, key: str) -> str | None:
    return conn.execute(
        select(app_state.c.value).where(app_state.c.key == key)
    ).scalar_one_or_none()


def set_state(conn: Connection, key: str, value: str) -> None:
    conn.execute(delete(app_state).where(app_state.c.key == key))
    conn.execute(insert(app_state).values(key=key, value=value))


def get_digest_cursor(conn: Connection) -> int:
    """The highest event id already digested. Absent means nothing has been digested yet."""
    raw = get_state(conn, DIGEST_CURSOR_KEY)
    return int(raw) if raw is not None else 0


def set_digest_cursor(conn: Connection, event_id: int) -> None:
    """Advance the cursor. Never lowers a stored value (A1: monotonic guard)."""
    current = get_digest_cursor(conn)
    if event_id <= current:
        return
    set_state(conn, DIGEST_CURSOR_KEY, str(event_id))


NOTIFY_CURSOR_KEY = "last_notified_event_id"


def get_notify_cursor(conn: Connection) -> int:
    """The highest event id already notified. Absent means nothing notified yet."""
    raw = get_state(conn, NOTIFY_CURSOR_KEY)
    return int(raw) if raw is not None else 0


def set_notify_cursor(conn: Connection, event_id: int) -> None:
    """Advance the notify cursor. Never lowers a stored value (monotonic guard)."""
    current = get_notify_cursor(conn)
    if event_id <= current:
        return
    set_state(conn, NOTIFY_CURSOR_KEY, str(event_id))


HOST_BUSY_KEY = "scan.host_busy.v1"


class HostBusy(NamedTuple):
    """What each host cost the last complete pipeline scan (T360): that run's id and, per
    `politeness.host_key`, the seconds its requests held the host (service plus pacing)."""

    run_id: int
    seconds: dict[str, float]


def get_host_busy(conn: Connection) -> HostBusy | None:
    """The last recorded host busy times, or None: never recorded, or not readable.

    It only orders the scan, so a value that does not parse is no record, never a failed scan.
    """
    raw = get_state(conn, HOST_BUSY_KEY)
    if raw is None:
        return None
    try:
        data = json.loads(raw)
        seconds = {str(h): float(s) for h, s in data["seconds"].items()}
        if not all(math.isfinite(s) and s >= 0 for s in seconds.values()):
            return None  # one bad value makes the whole record untrusted, as an unparsable one is
        return HostBusy(int(data["run_id"]), seconds)
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


def set_host_busy(conn: Connection, run_id: int, seconds: Mapping[str, float]) -> None:
    """Replace the record with `run_id`'s. One value, not one row per run: the next scan reads
    only the last one, and a record that outlived its scan would be older than it claims."""
    set_state(
        conn, HOST_BUSY_KEY,
        json.dumps({"run_id": run_id, "seconds": {h: round(s, 3) for h, s in seconds.items()}}),
    )
