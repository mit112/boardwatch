"""Lead aging: how long a delivered lead waits before it is applied to, closed or skipped (T298).

The cohort is every job with a tailored delivery. Its clock starts at its FIRST delivery, so a
lead re-delivered after a reopen counts once. Its outcome is whichever came first of: the first
submitted application, the owner's skip, or the delivered posting closing. A lead that closed
before anyone applied is the cost of a thin fill session, and is counted per board.

Read-only. One pass over `artifacts` joined out to postings and companies (a few thousand rows),
one over submitted applications and one over the skip keys.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from statistics import median, quantiles
from typing import Any

from sqlalchemy import Connection, func, select

from boardwatch.store.queue_state import skipped_job_ids
from boardwatch.store.run_funnel_queries import TAILORED_KIND
from boardwatch.store.tables import applications, artifacts, companies, posting_versions, postings

OUTCOMES = ("applied", "closed", "skipped")


@dataclass(frozen=True)
class _Lead:
    delivered_at: datetime
    board: str
    closed_at: datetime | None


def _naive(stamp: datetime) -> datetime:
    """The store holds both naive-UTC and offset-carrying instants; compare them as naive UTC."""
    return stamp if stamp.tzinfo is None else stamp.astimezone(UTC).replace(tzinfo=None)


def _naive_utc(value: str) -> datetime | None:
    try:
        return _naive(datetime.fromisoformat(value))
    except ValueError:
        return None


def _days(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds() / 86_400


def _summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "median_days": None, "p90_days": None}
    p90 = values[0] if len(values) == 1 else quantiles(values, n=10, method="inclusive")[-1]
    return {
        "count": len(values),
        "median_days": round(median(values), 2),
        "p90_days": round(p90, 2),
    }


def lead_aging(conn: Connection) -> dict[str, Any]:
    first: dict[int, _Lead] = {}
    rows = conn.execute(
        select(
            postings.c.job_id,
            artifacts.c.created_at,
            postings.c.closed_at,
            companies.c.provider,
        )
        .join(posting_versions, artifacts.c.posting_version_id == posting_versions.c.id)
        .join(postings, posting_versions.c.posting_id == postings.c.id)
        .join(companies, postings.c.company_id == companies.c.id)
        .where(artifacts.c.kind == TAILORED_KIND, postings.c.job_id.is_not(None))
        .order_by(artifacts.c.created_at, artifacts.c.id)
    )
    for row in rows:
        job_id = int(row.job_id)
        if job_id not in first:
            first[job_id] = _Lead(
                _naive(row.created_at),
                str(row.provider),
                None if row.closed_at is None else _naive(row.closed_at),
            )

    applied = {
        int(r.job_id): _naive(r.at)
        for r in conn.execute(
            select(applications.c.job_id, func.min(applications.c.submitted_at).label("at"))
            .where(applications.c.submitted_at.is_not(None))
            .group_by(applications.c.job_id)
        )
    }
    skipped = {
        job: stamp
        for job, raw in skipped_job_ids(conn).items()
        if (stamp := _naive_utc(raw)) is not None
    }

    waits: dict[str, list[float]] = {name: [] for name in OUTCOMES}
    closed_first_by_board: dict[str, int] = {}
    waiting = 0
    for job_id, lead in first.items():
        events = [
            (when, name)
            for name, when in (
                ("applied", applied.get(job_id)),
                ("skipped", skipped.get(job_id)),
                ("closed", lead.closed_at),
            )
            # An application recorded before the first delivery (an import) still ends the wait.
            if when is not None
        ]
        if not events:
            waiting += 1
            continue
        when, name = min(events)
        waits[name].append(max(0.0, _days(lead.delivered_at, when)))
        if name == "closed":
            closed_first_by_board[lead.board] = closed_first_by_board.get(lead.board, 0) + 1

    return {
        "leads": len(first),
        "still_waiting": waiting,
        "outcomes": {name: _summary(sorted(waits[name])) for name in OUTCOMES},
        "closed_before_applied_by_board": dict(
            sorted(closed_first_by_board.items(), key=lambda kv: (-kv[1], kv[0]))
        ),
    }
