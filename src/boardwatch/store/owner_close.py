"""Closing — and reopening — a posting on the OWNER's observation rather than a probe's.

The death probe and a complete scan snapshot are the only things that close a posting on their
own, and neither can see every closure: a LinkedIn listing the owner finds closed in the browser
stays `open` here until something re-lists or probes it. This is the owner's path for that case,
and it writes EXACTLY the shape the native closers write — `status = 'closed'`, `closed_at`, and a
`closed` row in `posting_events` — so every reader that already honours a closed posting (the
queue's `_closed` drain, the slate seeds, the lane-copy rules) honours this one with no change.

Two things it adds, and they are the reason this is a command rather than a hand-written UPDATE:

* **Its own run.** `posting_events.run_id` is NOT NULL, and the caller passes a run minted for
  THIS write (`ensure_run(engine, None)`). Borrowing the latest daily run's id would make that run
  claim closures it never observed and skew every per-run closed count.
* **The evidence.** `posting.ownerclosed.<posting_id>` in `app_state` -> JSON
  `{"at", "run_id", "evidence"}`, so a later reader can tell an owner's closure from a probe's and
  see why. Keyed on the POSTING, not the job: closure is a fact about one listing.

It self-heals exactly as a probe's closure does: a scan that lists the posting again reopens it
(`scan/apply.py`, D23). The evidence row is then history, not state — nothing reads it to decide
anything. `reopen_postings` is the owner's undo for a mistaken close.

Functions take the caller's open Connection and never begin or commit.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Connection, delete, select, update

from boardwatch.store.app_state import set_state
from boardwatch.store.events import append_event
from boardwatch.store.param_chunks import id_chunks
from boardwatch.store.tables import app_state, postings

#: No LIKE metacharacter (`%` or `_`) in it, so the prefix scan below needs no ESCAPE clause.
OWNER_CLOSED_KEY_PREFIX = "posting.ownerclosed."


class OwnerClose(StrEnum):
    """What one id came to. Closed catalog: an id is always exactly one of these."""

    CLOSED = "closed"  # was open, is now closed
    REOPENED = "reopened"  # was closed, is now open
    UNCHANGED = "unchanged"  # already in the requested state; nothing written
    MISSING = "missing"  # no such posting


def _key(posting_id: int) -> str:
    return f"{OWNER_CLOSED_KEY_PREFIX}{posting_id}"


def _statuses(conn: Connection, posting_ids: Sequence[int]) -> dict[int, str]:
    # Chunked (D-288): an id list bound whole hits SQLite's bound-parameter cap.
    status: dict[int, str] = {}
    for chunk in id_chunks(posting_ids):
        for row in conn.execute(
            select(postings.c.id, postings.c.status).where(postings.c.id.in_(chunk))
        ):
            status[int(row.id)] = str(row.status)
    return status


def plan(conn: Connection, posting_ids: Sequence[int], *, close: bool) -> dict[int, OwnerClose]:
    """What `close_postings` / `reopen_postings` WOULD do per id, writing nothing."""
    status = _statuses(conn, posting_ids)
    wanted, verb = ("closed", OwnerClose.CLOSED) if close else ("open", OwnerClose.REOPENED)
    return {
        pid: (
            OwnerClose.MISSING
            if pid not in status
            else OwnerClose.UNCHANGED
            if status[pid] == wanted
            else verb
        )
        for pid in posting_ids
    }


def close_postings(
    conn: Connection, posting_ids: Sequence[int], *, run_id: int, evidence: str, at: datetime
) -> dict[int, OwnerClose]:
    """Close every named OPEN posting on the owner's word, under `run_id`. Idempotent."""
    outcome = plan(conn, posting_ids, close=True)
    for pid, result in outcome.items():
        if result is not OwnerClose.CLOSED:
            continue
        conn.execute(
            update(postings).where(postings.c.id == pid).values(status="closed", closed_at=at)
        )
        append_event(conn, pid, "closed", run_id)
        set_state(
            conn,
            _key(pid),
            json.dumps({"at": at.isoformat(), "run_id": run_id, "evidence": evidence}),
        )
    return outcome


def reopen_postings(
    conn: Connection, posting_ids: Sequence[int], *, run_id: int
) -> dict[int, OwnerClose]:
    """Reopen every named CLOSED posting: the undo for a mistaken close. Idempotent.

    Any closed posting, not only an owner-closed one: an owner who sees a probe-closed listing
    live again is the same evidence a re-listing is. The probe may close it again if it later
    measures it dead, which is the probe's job.
    """
    outcome = plan(conn, posting_ids, close=False)
    for pid, result in outcome.items():
        if result is not OwnerClose.REOPENED:
            continue
        conn.execute(
            update(postings).where(postings.c.id == pid).values(status="open", closed_at=None)
        )
        append_event(conn, pid, "reopened", run_id)
        conn.execute(delete(app_state).where(app_state.c.key == _key(pid)))
    return outcome


def owner_closures(conn: Connection) -> dict[int, dict[str, object]]:
    """posting_id -> the recorded `{"at", "run_id", "evidence"}` for every owner closure."""
    rows = conn.execute(
        select(app_state.c.key, app_state.c.value).where(
            app_state.c.key.like(f"{OWNER_CLOSED_KEY_PREFIX}%")
        )
    ).all()
    found: dict[int, dict[str, object]] = {}
    for row in rows:
        suffix = str(row.key)[len(OWNER_CLOSED_KEY_PREFIX) :]
        if not suffix.isdecimal() or row.value is None:
            continue
        try:
            found[int(suffix)] = json.loads(str(row.value))
        except ValueError:
            continue
    return found
