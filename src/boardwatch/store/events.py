"""Append-only posting_events writer (D18).

Events are written ONLY inside per-board transactions — callers pass the open
connection; this module never begins or commits one. The AUTOINCREMENT id is
the monotonic cursor space; rows are never updated or deleted.
"""

from __future__ import annotations

from typing import Literal

from sqlalchemy import Connection, insert

from boardwatch.core.clock import utcnow
from boardwatch.store.tables import posting_events

EventKind = Literal["new", "reopened", "closed", "revised"]


def append_event(conn: Connection, posting_id: int, kind: EventKind, run_id: int) -> int:
    result = conn.execute(
        insert(posting_events).values(
            posting_id=posting_id, kind=kind, run_id=run_id, created_at=utcnow()
        )
    )
    return int(result.inserted_primary_key[0])  # type: ignore[index]
