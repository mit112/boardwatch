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

from sqlalchemy import Connection, select

from boardwatch.store.queue_state import skipped_job_ids
from boardwatch.store.run_funnel_queries import TAILORED_KIND
from boardwatch.store.tables import (
    application_events,
    applications,
    artifacts,
    companies,
    posting_versions,
    postings,
)

#: `application_events.source` on an imported application (`application_history.import_history`).
IMPORT_SOURCE = "import"

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


def _first_deliveries(conn: Connection) -> dict[int, _Lead]:
    """job id -> its first tailored delivery, the source that found it, and when it closed."""
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
    return first


def _first_applied(conn: Connection) -> tuple[dict[int, datetime], set[int]]:
    """job id -> its first submitted application, and the jobs whose ONLY submission date is an
    import's (unknown).

    The earliest is taken in Python after normalising, never with SQL `MIN()`: the column holds
    both naive-UTC and offset-carrying text, and SQLite compares the text, so `MIN()` can pick a
    later instant. An imported application's `submitted_at` is the import time, not when it was
    sent (`jobapps_history`); its created event says `source = 'import'`. Such a job still counts
    as applied, but it has no measured date unless a non-imported attempt supplies one.
    """
    imported = {
        int(r.application_id)
        for r in conn.execute(
            select(application_events.c.application_id).where(
                application_events.c.event_type == "created",
                application_events.c.source == IMPORT_SOURCE,
            )
        )
    }
    dated: dict[int, datetime] = {}
    undated: set[int] = set()
    for r in conn.execute(
        select(applications.c.id, applications.c.job_id, applications.c.submitted_at).where(
            applications.c.submitted_at.is_not(None)
        )
    ):
        job = int(r.job_id)
        if int(r.id) in imported:
            undated.add(job)
            continue
        at = _naive(r.submitted_at)
        if job not in dated or at < dated[job]:
            dated[job] = at
    return dated, undated - set(dated)


def source_yield(conn: Connection) -> dict[str, dict[str, int]]:
    """T306: per discovery source, all time — leads with a résumé built, and how many of those
    were applied to. A job is credited to the source of its FIRST delivered posting, the same
    attribution `lead_aging` uses, so a lead found twice is counted once."""
    dated, undated = _first_applied(conn)
    applied = set(dated) | undated
    out: dict[str, dict[str, int]] = {}
    for job_id, lead in _first_deliveries(conn).items():
        row = out.setdefault(lead.board, {"built": 0, "applied": 0})
        row["built"] += 1
        row["applied"] += job_id in applied
    return dict(sorted(out.items(), key=lambda kv: (-kv[1]["built"], kv[0])))


def lead_aging(conn: Connection) -> dict[str, Any]:
    first = _first_deliveries(conn)
    applied, undated = _first_applied(conn)
    skipped = {
        job: stamp
        for job, raw in skipped_job_ids(conn).items()
        if (stamp := _naive_utc(raw)) is not None
    }

    waits: dict[str, list[float]] = {name: [] for name in OUTCOMES}
    closed_first_by_board: dict[str, int] = {}
    waiting = 0
    applied_undated = 0
    for job_id, lead in first.items():
        events = [
            (when, name)
            for name, when in (
                ("applied", applied.get(job_id)),
                ("skipped", skipped.get(job_id)),
                ("closed", lead.closed_at),
            )
            # An application recorded before the first delivery still ends the wait (at 0 days).
            if when is not None
        ]
        if job_id in undated:
            # Applied, on a date nobody recorded: that is its outcome, whatever closed after,
            # but there is no wait to measure.
            applied_undated += 1
            continue
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
        "applied_date_unknown": applied_undated,
        "outcomes": {name: _summary(sorted(waits[name])) for name in OUTCOMES},
        "closed_before_applied_by_board": dict(
            sorted(closed_first_by_board.items(), key=lambda kv: (-kv[1], kv[0]))
        ),
    }
