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
from boardwatch.store.param_chunks import id_chunks
from boardwatch.store.tables import application_events, applications, companies, postings


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

    # When each was applied to. An import's created event dates it when the row gave a date (it
    # then differs from the application's `created_at`, the import time); an undated import has
    # no applied date at all. Anything else uses `submitted_at`.
    imported: dict[int, datetime | None] = {}
    for chunk in id_chunks(sorted(first)):
        for r in conn.execute(
            select(application_events.c.application_id, application_events.c.occurred_at).where(
                application_events.c.application_id.in_(chunk),
                application_events.c.event_type == "created",
                application_events.c.source == "import",
            )
        ):
            imported[int(r.application_id)] = _naive(r.occurred_at)

    # The newest posting per job names it, looked up for these jobs only.
    label: dict[int, tuple[int, str, str]] = {}
    for chunk in id_chunks(sorted({int(e.job_id) for e in first.values()})):
        for p in conn.execute(
            select(postings.c.id, postings.c.job_id, postings.c.title, companies.c.name)
            .join(companies, companies.c.id == postings.c.company_id)
            .where(postings.c.job_id.in_(chunk))
            .order_by(postings.c.id)
        ):
            label[int(p.job_id)] = (int(p.id), str(p.title), str(p.name))

    out = []
    for e in sorted(first.values(), key=lambda e: (_naive(e.occurred_at), e.id), reverse=True):
        after = e.from_status in APPLIED_STATUSES
        app_id = int(e.application_id)
        if app_id in imported:
            at = imported[app_id]
            applied_on = None if at == _naive(e.created_at) else at
        else:
            applied_on = None if e.submitted_at is None else _naive(e.submitted_at)
        named = label.get(int(e.job_id))
        out.append(
            {
                "application_id": app_id,
                "kind": "after_applying" if after else "before_applying",
                "withdrawn_at": _naive(e.occurred_at).replace(tzinfo=UTC).isoformat(),
                "days_after_applying": (
                    round((_naive(e.occurred_at) - applied_on).total_seconds() / 86_400, 2)
                    if after and applied_on is not None
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
