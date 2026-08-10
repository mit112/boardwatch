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

# Statuses that imply a submission actually happened. `interested` is excluded because it is
# `create_application`'s default and means only that a lead was tracked; `withdrawn` because it
# cannot distinguish withdrawing an application from withdrawing interest before applying.
#
# One catalog, two callers, and the reasons coincide rather than merely agreeing: the funnel
# counts these as conversions (`count_applied_for_postings`) and the ranker suppresses them
# (P6 item 5). Both ask the same question — did this job already receive an application? — so a
# status that should not count as a conversion is exactly one that should not suppress a lead.
# `withdrawn` falling outside the set is what makes `track status <id> withdrawn` the drain.
APPLIED_STATUSES = ("applied", "interviewing", "offer", "rejected")


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


def applied_job_ids(conn: Connection) -> dict[int, str]:
    """Jobs that already carry a submitted application, mapped to the status that says so.

    The whole table, unfiltered by job: `applications` has 0 rows on every store measured so
    far and cannot plausibly outgrow the shortlist it is joined against, so paying for an `IN`
    list here would buy nothing and would reintroduce the 32,766-parameter cap that
    `load_dispositions` documents.

    Keyed on `job_id`, the canonical anchor, so an application survives its posting being
    revised, closed, or regrouped onto another job. The status is returned rather than a bare
    set because the `--include-applied` drain shows it: "already applied" and "already
    rejected" are different things to be told about a lead you are looking at again.

    When a job has several attempts, the winner is the last **submitted** one by `attempt_no` —
    the filter runs before the ordering. So `track add --new-attempt` does NOT supersede an
    earlier submission: it writes a fresh row at `create_application`'s default `interested`,
    which is outside the catalog, so an attempt 1 of `rejected` keeps governing and the job
    stays suppressed as "already applied (rejected)".

    That is the intended direction — the question this answers is "did this job already receive
    an application?", and one that was rejected still did — but it means the drain for a
    deliberate re-application is `top --include-applied`, or withdrawing the OLD attempt, not
    starting a new one. Recorded because the natural reading of `--new-attempt` is the opposite.
    """
    rows = conn.execute(
        select(applications.c.job_id, applications.c.status)
        .where(applications.c.status.in_(APPLIED_STATUSES))
        .order_by(applications.c.job_id, applications.c.attempt_no)
    ).all()
    return {int(row.job_id): str(row.status) for row in rows}


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
