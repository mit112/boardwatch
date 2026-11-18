"""Withdrawals, with their reasons (T311).

One row per application that moved to `withdrawn`, from its NEWEST such event: an application
declined, then applied to and withdrawn again, is shown by the withdrawal that stands. A
`withdrawn -> withdrawn` event is a repeat, not a withdrawal. Two kinds, kept apart:
`after_applying` (it left a status that means it was sent, `APPLIED_STATUSES`) and
`before_applying` (recorded as withdrawn without being sent, such as a pre-flight decline). Days
to withdraw is defined for the first kind only, and only when the applied date is known: an
import that gave no date carries the import time, not when it was sent. Events are ordered in
Python, since `occurred_at` mixes naive-UTC and offset-carrying text. Read-only; a few hundred
rows at most.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Connection, select

from boardwatch.store.applications import APPLIED_STATUSES
from boardwatch.store.delivery_queries import applied_rows
from boardwatch.store.param_chunks import id_chunks
from boardwatch.store.tables import application_events, applications


def _naive(stamp: datetime) -> datetime:
    return stamp if stamp.tzinfo is None else stamp.astimezone(UTC).replace(tzinfo=None)


def withdrawals(conn: Connection) -> dict[str, Any]:
    events = conn.execute(
        select(
            application_events.c.id,
            application_events.c.application_id,
            application_events.c.from_status,
            application_events.c.occurred_at,
            application_events.c.note,
            applications.c.job_id,
            applications.c.created_at,
            applications.c.submitted_at,
        )
        .join(applications, application_events.c.application_id == applications.c.id)
        .where(
            application_events.c.to_status == "withdrawn",
            # A repeat on an application already withdrawn is not a withdrawal.
            application_events.c.from_status.is_distinct_from("withdrawn"),
        )
    ).all()
    first: dict[int, Any] = {}  # application -> its newest withdrawal
    for e in sorted(events, key=lambda e: (_naive(e.occurred_at), e.id)):
        first[int(e.application_id)] = e

    # When the standing withdrawal's cycle was applied to: the LAST time, before it, that the
    # application entered a submitted status (created in one, or moved into one from outside the
    # set), so an apply -> withdraw -> reapply -> withdraw cycle counts from the reapply. An
    # import that gave no date (its created event's `occurred_at` equals the application's
    # `created_at`, the import time) entered on an unknown date. No entering event at all (rows
    # written before events) falls back to `submitted_at`.
    history: dict[int, list[Any]] = {}
    for chunk in id_chunks(sorted(first)):
        for r in conn.execute(
            select(
                application_events.c.id,
                application_events.c.application_id,
                application_events.c.event_type,
                application_events.c.from_status,
                application_events.c.to_status,
                application_events.c.occurred_at,
                application_events.c.source,
            ).where(application_events.c.application_id.in_(chunk))
        ):
            history.setdefault(int(r.application_id), []).append(r)

    def applied_on(e: Any) -> datetime | None:
        stop = (_naive(e.occurred_at), e.id)
        seen, at = False, None
        events = history.get(int(e.application_id), [])
        for r in sorted(events, key=lambda r: (_naive(r.occurred_at), r.id)):
            if (_naive(r.occurred_at), r.id) >= stop:
                break
            if r.to_status in APPLIED_STATUSES and (
                r.event_type == "created" or r.from_status not in APPLIED_STATUSES
            ):
                seen = True
                when = _naive(r.occurred_at)
                undated = r.source == "import" and when == _naive(e.created_at)
                at = None if undated else when
        if not seen and e.submitted_at is not None:
            return _naive(e.submitted_at)
        return at

    # Named by the SAME posting the Applied page shows for that application (`applied_rows`:
    # the posting the application names, else the delivered one, else a fallback), so the panel
    # and the row above it never disagree.
    label: dict[int, tuple[int | None, str | None, str | None]] = {
        row.application_id: (row.posting_id, row.title, row.company) for row in applied_rows(conn)
    }

    out = []
    for e in sorted(first.values(), key=lambda e: (_naive(e.occurred_at), e.id), reverse=True):
        after = e.from_status in APPLIED_STATUSES
        app_id = int(e.application_id)
        since = applied_on(e) if after else None
        named = label.get(app_id)
        out.append(
            {
                "application_id": app_id,
                "kind": "after_applying" if after else "before_applying",
                "withdrawn_at": _naive(e.occurred_at).replace(tzinfo=UTC).isoformat(),
                "days_after_applying": (
                    round((_naive(e.occurred_at) - since).total_seconds() / 86_400, 2)
                    if since is not None
                    else None
                ),
                "note": e.note,
                "job_id": int(e.job_id),
                "posting_id": None if named is None else named[0],
                "title": None if named is None else named[1],
                "company": None if named is None else named[2],
            }
        )
    return {"withdrawals": out}
