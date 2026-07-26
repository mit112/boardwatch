"""Application / decision-state store (net-new spine; CLI workflow is P5).

applications is mutable state; every status change also appends an immutable
application_events row (from -> to). attempt_no supports reapplications per job.
Functions take the caller's open Connection.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from sqlalchemy import Connection, Row, func, insert, select, update

from boardwatch.core.clock import utcnow
from boardwatch.store.tables import application_events, applications

ApplicationStatus = Literal[
    "interested", "applied", "interviewing", "offer", "rejected", "withdrawn"
]


def append_application_event(
    conn: Connection,
    *,
    application_id: int,
    event_type: str,
    source: str,
    from_status: str | None = None,
    to_status: str | None = None,
    note: str | None = None,
    occurred_at: datetime | None = None,
    detail: dict[str, Any] | None = None,
) -> int:
    return int(
        conn.execute(
            insert(application_events).values(
                application_id=application_id, event_type=event_type, from_status=from_status,
                to_status=to_status, occurred_at=occurred_at or utcnow(), recorded_at=utcnow(),
                source=source, note=note, detail_json=detail,
            )
        ).inserted_primary_key[0]  # type: ignore[index]
    )


def create_application(
    conn: Connection,
    *,
    job_id: int,
    posting_version_id: int | None = None,
    status: ApplicationStatus = "interested",
    source: str = "user",
) -> int:
    now = utcnow()
    next_attempt = int(
        conn.execute(
            select(func.coalesce(func.max(applications.c.attempt_no), 0) + 1).where(
                applications.c.job_id == job_id
            )
        ).scalar_one()
    )
    app_id = int(
        conn.execute(
            insert(applications).values(
                job_id=job_id, posting_version_id=posting_version_id, attempt_no=next_attempt,
                status=status, created_at=now, updated_at=now,
                submitted_at=now if status == "applied" else None,
            )
        ).inserted_primary_key[0]  # type: ignore[index]
    )
    append_application_event(
        conn, application_id=app_id, event_type="created", to_status=status,
        source=source, occurred_at=now,
    )
    return app_id


def get_application(conn: Connection, application_id: int) -> Row[Any] | None:
    return conn.execute(
        select(applications).where(applications.c.id == application_id)
    ).one_or_none()


def get_applications(conn: Connection, job_id: int) -> list[Row[Any]]:
    return list(
        conn.execute(
            select(applications)
            .where(applications.c.job_id == job_id)
            .order_by(applications.c.attempt_no)
        ).all()
    )


def set_application_status(
    conn: Connection,
    *,
    application_id: int,
    to_status: ApplicationStatus,
    source: str,
    note: str | None = None,
    occurred_at: datetime | None = None,
) -> None:
    current = conn.execute(
        select(applications.c.status, applications.c.submitted_at).where(
            applications.c.id == application_id
        )
    ).one()
    occurred = occurred_at or utcnow()
    submitted_at = current.submitted_at
    if submitted_at is None and to_status == "applied":
        submitted_at = occurred
    conn.execute(
        update(applications)
        .where(applications.c.id == application_id)
        .values(status=to_status, updated_at=utcnow(), submitted_at=submitted_at)
    )
    append_application_event(
        conn, application_id=application_id, event_type="status_change",
        from_status=current.status, to_status=to_status, source=source, note=note,
        occurred_at=occurred,
    )


def get_application_events(conn: Connection, application_id: int) -> list[Row[Any]]:
    return list(
        conn.execute(
            select(application_events)
            .where(application_events.c.application_id == application_id)
            .order_by(application_events.c.id)
        ).all()
    )
