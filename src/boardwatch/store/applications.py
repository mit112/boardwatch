"""Application / decision-state store (net-new spine; CLI workflow is P5).

applications is mutable state; every status change also appends an immutable
application_events row (from -> to). attempt_no supports reapplications per job.
Functions take the caller's open Connection.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from sqlalchemy import Connection, Row, func, insert, select, update

from boardwatch.core.clock import utcnow
from boardwatch.store.funnel_queries import job_id_for_posting
from boardwatch.store.queries import current_posting_versions
from boardwatch.store.tables import application_events, applications, postings

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


class MarkOutcome(StrEnum):
    """What `mark_job_applied` did, typed so no caller classifies it by string-matching prose.

    `NO_POSTING` and `NO_JOB` are separate members because `track add` collapses them into one
    message ("no posting <id>") while they are different faults: an id the user mistyped versus a
    posting the grouper never anchored. `postings.job_id` is nullable in the table and held NOT
    NULL by a trigger, so `NO_JOB` is the defensive branch for a store written before that trigger
    existed, not a state this codebase can produce.
    """

    CREATED = "created"
    TRANSITIONED = "transitioned"
    UNCHANGED = "unchanged"
    NO_POSTING = "no_posting"
    NO_JOB = "no_job"


@dataclass(frozen=True)
class MarkResult:
    """The outcome plus the ids it applies to. Both ids are None on a lookup failure."""

    outcome: MarkOutcome
    job_id: int | None = None
    application_id: int | None = None


def mark_job_applied(conn: Connection, *, posting_id: int, source: str) -> MarkResult:
    """Record "I applied to this" for the job behind `posting_id`, idempotently.

    The single writer for that intent: `track add` returns early when the job carries ANY
    application (including the `interested` one it just made), `track status` needs an
    application id rather than a posting id, and `set_application_status` appends an event
    unconditionally. None of the three is safe for an endpoint a browser can re-POST.

    So the applied-already case returns `UNCHANGED` and appends **no** `application_events`
    row and touches no column — not even `updated_at`. An immutable event log is only readable
    if every row in it records something that happened, and a refresh is not an event.

    The unit is the canonical `job_id`, never the posting (`applications` keys on it), so
    marking one posting applied makes every sibling posting on the same job read as applied.
    `submitted_at` is set by `set_application_status` on the first transition into applied and
    is never re-stamped, because the `UNCHANGED` path never writes.

    Runs entirely in the caller's transaction; it never begins or commits.
    """
    job_id = job_id_for_posting(conn, posting_id)
    if job_id is None:
        # job_id_for_posting returns None for both "no such posting" and "posting has no job",
        # so the posting's existence is what separates them.
        found = conn.execute(
            select(postings.c.id).where(postings.c.id == posting_id)
        ).scalar_one_or_none()
        return MarkResult(MarkOutcome.NO_POSTING if found is None else MarkOutcome.NO_JOB)
    attempts = get_applications(conn, job_id)
    if attempts:
        # Ordered by attempt_no, so the last row is the live attempt. A `--new-attempt` row
        # sitting at `interested` above a submitted one is what the user is now marking.
        latest = attempts[-1]
        application_id = int(latest.id)
        if latest.status in APPLIED_STATUSES:
            return MarkResult(MarkOutcome.UNCHANGED, job_id=job_id, application_id=application_id)
        set_application_status(
            conn, application_id=application_id, to_status="applied", source=source
        )
        return MarkResult(MarkOutcome.TRANSITIONED, job_id=job_id, application_id=application_id)
    # A4: link the version the application was made against. A posting with no version row
    # links nothing rather than failing.
    current = current_posting_versions(conn, [posting_id]).get(posting_id)
    return MarkResult(
        MarkOutcome.CREATED,
        job_id=job_id,
        application_id=create_application(
            conn,
            job_id=job_id,
            posting_version_id=current.posting_version_id if current is not None else None,
            status="applied",
            source=source,
        ),
    )


def mark_job_unapplied(conn: Connection, *, posting_id: int, source: str) -> MarkResult:
    """Undo "I applied to this" for the job behind `posting_id`, idempotently.

    The exact inverse of `mark_job_applied`, and it exists because the review page's undo
    otherwise only restores a row on screen: the `applications` row it just wrote stays
    `applied` forever, `applied_job_ids` keeps reporting the job as a conversion, and
    `delivered_unapplied` never offers the lead again. An undo that leaves the store asserting
    the opposite of what the owner now says is worse than no undo at all.

    The transition is to **`withdrawn`**, which is deliberately outside `APPLIED_STATUSES` — so
    the lead returns to the queue by itself, through the same read that removed it, with no
    second mechanism to keep in step. `track status <id> withdrawn` is already documented as
    that drain; this is the same drain reached from a posting id.

    **The applied event is never deleted or rewritten.** `set_application_status` appends a
    second `status_change` row, so the log reads "applied, then withdrawn" — which is what
    happened. `submitted_at` is left standing for the same reason: it is stamped once, on the
    first transition into applied, and erasing it would make an application that really was
    submitted read as one that never was.

    Idempotency mirrors `mark_job_applied` and is the exact complement of it. That function
    returns `UNCHANGED` precisely when the latest attempt is in `APPLIED_STATUSES`; this one
    acts precisely then, and returns `UNCHANGED` with **no** event for every other state — a
    job with no attempts at all, an attempt still at `interested`, and an attempt already
    `withdrawn`. All three already read as not-applied, so there is nothing to undo, and a
    re-POST from a browser must not append an event that records nothing.

    Runs entirely in the caller's transaction; it never begins or commits.
    """
    job_id = job_id_for_posting(conn, posting_id)
    if job_id is None:
        found = conn.execute(
            select(postings.c.id).where(postings.c.id == posting_id)
        ).scalar_one_or_none()
        return MarkResult(MarkOutcome.NO_POSTING if found is None else MarkOutcome.NO_JOB)
    attempts = get_applications(conn, job_id)
    if not attempts:
        return MarkResult(MarkOutcome.UNCHANGED, job_id=job_id)
    latest = attempts[-1]
    application_id = int(latest.id)
    if latest.status not in APPLIED_STATUSES:
        return MarkResult(MarkOutcome.UNCHANGED, job_id=job_id, application_id=application_id)
    set_application_status(
        conn, application_id=application_id, to_status="withdrawn", source=source
    )
    return MarkResult(MarkOutcome.TRANSITIONED, job_id=job_id, application_id=application_id)
