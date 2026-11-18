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

from boardwatch.store.applications import APPLIED_STATUSES
from boardwatch.store.owner_close import owner_undo_runs
from boardwatch.store.queue_state import skipped_job_ids
from boardwatch.store.run_funnel_queries import TAILORED_KIND
from boardwatch.store.tables import (
    application_events,
    applications,
    artifacts,
    companies,
    posting_events,
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
    """job id -> its first tailored delivery, the source that found it, and when it closed.

    "First" is the earliest instant after normalising, never SQL `ORDER BY created_at`: the
    column mixes naive-UTC and offset-carrying text, and SQLite would order the text.
    """
    rows = sorted(
        conn.execute(
            select(
                postings.c.job_id,
                postings.c.id.label("posting_id"),
                artifacts.c.id,
                artifacts.c.created_at,
                postings.c.closed_at,
                companies.c.provider,
            )
            .join(posting_versions, artifacts.c.posting_version_id == posting_versions.c.id)
            .join(postings, posting_versions.c.posting_id == postings.c.id)
            .join(companies, postings.c.company_id == companies.c.id)
            .where(artifacts.c.kind == TAILORED_KIND, postings.c.job_id.is_not(None))
        ),
        key=lambda r: (_naive(r.created_at), int(r.id)),
    )
    picked: dict[int, Any] = {}
    for row in rows:
        picked.setdefault(int(row.job_id), row)

    # A scan clears `closed_at` on a reopen, so the posting's `closed` events are read too: a lead
    # that closed after delivery and later reopened still closed first (Codex #658).
    # A closure the owner then UNDID (`postings reopen`, recorded in `owner_undo_runs`) was a
    # mistake, not the posting closing: the closed event just before that undo is dropped.
    undo = owner_undo_runs(conn)
    history: dict[int, list[tuple[tuple[datetime, int], str, int]]] = {}
    for r in conn.execute(
        select(
            posting_events.c.id,
            posting_events.c.posting_id,
            posting_events.c.kind,
            posting_events.c.run_id,
            posting_events.c.created_at,
        ).where(posting_events.c.kind.in_(("closed", "reopened")))
    ):
        history.setdefault(int(r.posting_id), []).append(
            ((_naive(r.created_at), int(r.id)), str(r.kind), int(r.run_id))
        )
    close_events: dict[int, list[datetime]] = {}
    for pid, events in history.items():
        events.sort()
        undone = undo.get(pid, set())
        for i, (order, kind, _) in enumerate(events):
            if kind != "closed":
                continue
            following = events[i + 1] if i + 1 < len(events) else None
            if following is not None and following[1] == "reopened" and following[2] in undone:
                continue
            close_events.setdefault(pid, []).append(order[0])

    first: dict[int, _Lead] = {}
    for job_id, row in picked.items():
        delivered = _naive(row.created_at)
        closes = close_events.get(int(row.posting_id), [])
        if row.closed_at is not None:
            closes = [*closes, _naive(row.closed_at)]
        after = [c for c in closes if c >= delivered]
        first[job_id] = _Lead(delivered, str(row.provider), min(after) if after else None)
    return first


def _first_applied(conn: Connection) -> tuple[dict[int, datetime], set[int]]:
    """job id -> its first dated submitted application, and the jobs with an undated import.

    The earliest is taken in Python after normalising, never with SQL `MIN()`: the column holds
    both naive-UTC and offset-carrying text, and SQLite compares the text, so `MIN()` can pick a
    later instant. An import (created event `source = 'import'`) is dated only when its row
    supplied `applied_at`: `create_application` otherwise stamps the event's `occurred_at` with
    the same instant as `created_at`, the import time. A job with an undated import was applied
    to on a date nobody recorded, which may precede any later dated retry, so it is reported as
    applied with no measured wait whatever else it carries.
    """
    dated: dict[int, datetime] = {}
    undated: set[int] = set()
    # Imports first, from the created event: an imported `rejected`/`interviewing` row has no
    # `submitted_at`, but it was still applied to, on the event's `occurred_at` when the row gave
    # a date (otherwise that equals the application's `created_at`, the import time).
    imported: set[int] = set()
    for r in conn.execute(
        select(
            applications.c.id,
            applications.c.job_id,
            applications.c.created_at,
            application_events.c.occurred_at,
        )
        .join(application_events, application_events.c.application_id == applications.c.id)
        .where(
            application_events.c.event_type == "created",
            application_events.c.source == IMPORT_SOURCE,
            applications.c.status.in_(APPLIED_STATUSES),
        )
    ):
        imported.add(int(r.id))
        job = int(r.job_id)
        at = _naive(r.occurred_at)
        if at == _naive(r.created_at):
            undated.add(job)
        elif job not in dated or at < dated[job]:
            dated[job] = at
    # Only an application still in the applied set counts, as for the funnel and the ranker
    # (`APPLIED_STATUSES`): `withdrawn` is the store's drain out of it, and the Applied page's undo
    # of an accidental mark writes exactly that while `submitted_at` stays set.
    for r in conn.execute(
        select(applications.c.id, applications.c.job_id, applications.c.submitted_at).where(
            applications.c.submitted_at.is_not(None),
            applications.c.status.in_(APPLIED_STATUSES),
        )
    ):
        if int(r.id) in imported:
            continue
        job = int(r.job_id)
        at = _naive(r.submitted_at)
        if job not in dated or at < dated[job]:
            dated[job] = at
    for job in undated:
        dated.pop(job, None)
    return dated, undated


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
