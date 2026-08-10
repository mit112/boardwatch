"""Read/write the durable decision ledger (P6 slice 2, design §2, §6).

Every decision about whether a job still governs goes through `core.ledger.is_live`, never
through a hand-written SQL predicate here. A SQL `WHERE expires_at > :now` that drifts from the
Python one is the reader/writer disagreement §2.2 exists to prevent, so the SQL narrows the rows
and Python decides.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import Row, insert, select, update
from sqlalchemy.engine import Connection

from boardwatch.core.ledger import LedgerRow, is_live, plan_upsert
from boardwatch.store.tables import job_dispositions


def _row(raw: Row[Any]) -> LedgerRow:
    return LedgerRow(
        disposition=str(raw.disposition),
        reason=str(raw.reason),
        policy_version=raw.policy_version,
        expires_at=raw.expires_at,
        reopened_at=raw.reopened_at,
        first_decided_at=raw.first_decided_at,
        decided_at=raw.decided_at,
    )


def load_dispositions(
    conn: Connection, job_ids: Sequence[int] | None = None
) -> dict[int, LedgerRow]:
    """Every stored disposition, live or not, for the named jobs or for all of them.

    `job_ids=None` issues no `IN` list — SQLite caps bound parameters at 32766 on the bundled
    3.45.1 and the corpus is already 24,073 jobs, so an unconditional `IN` would make the
    audit path itself a scheduled failure as breadth grows (the same reasoning as
    `load_identities`). An empty list means an empty result, not "all".
    """
    if job_ids is not None and not job_ids:
        return {}
    stmt = select(job_dispositions)
    if job_ids is not None:
        stmt = stmt.where(job_dispositions.c.job_id.in_(list(job_ids)))
    return {int(raw.job_id): _row(raw) for raw in conn.execute(stmt).all()}


def live_dispositions(
    conn: Connection, *, now: datetime, job_ids: Sequence[int] | None = None
) -> dict[int, LedgerRow]:
    """The dispositions that still govern — lazy read-time expiry, no sweeper, no DELETE.

    Filtered in Python by `core.ledger.is_live`, deliberately: the writer plans its upsert
    against the same predicate, so the two cannot disagree about whether a row counts.
    """
    return {
        job_id: row
        for job_id, row in load_dispositions(conn, job_ids).items()
        if is_live(expires_at=row.expires_at, reopened_at=row.reopened_at, now=now)
    }


def record_disposition(
    conn: Connection,
    job_id: int,
    *,
    disposition: str,
    reason: str,
    policy_version: str | None = None,
    expires_at: datetime | None = None,
    now: datetime,
    run_id: int | None = None,
) -> bool:
    """Monotonically upsert one job's decision. True when a row was written.

    Returns False — writing nothing — when a live row already outranks the incoming decision,
    which is what keeps a built lead from being downgraded to merely surfaced.
    """
    existing = load_dispositions(conn, [job_id]).get(job_id)
    planned = plan_upsert(
        existing,
        disposition=disposition,
        reason=reason,
        policy_version=policy_version,
        expires_at=expires_at,
        now=now,
    )
    if planned is None:
        return False
    values = {
        "disposition": planned.disposition,
        "reason": planned.reason,
        "policy_version": planned.policy_version,
        "expires_at": planned.expires_at,
        # Cleared on every write: a new decision is live by definition, so a job that was
        # reopened and then re-decided must not stay invisible to the reader.
        "reopened_at": None,
        "decided_at": planned.decided_at,
        "run_id": run_id,
    }
    if existing is None:
        conn.execute(
            insert(job_dispositions).values(
                job_id=job_id, first_decided_at=planned.first_decided_at, **values
            )
        )
    else:
        # first_decided_at is never rewritten — it is the first decision ever taken for this
        # job, not the first of the current lifetime.
        conn.execute(
            update(job_dispositions).where(job_dispositions.c.job_id == job_id).values(**values)
        )
    return True


def stale_dispositions(
    conn: Connection, *, policy_version: str, now: datetime
) -> dict[int, LedgerRow]:
    """Live PERMANENT dispositions whose policy stamp is not the current one.

    The drain's read side. A stamp mismatch never re-opens a row on its own (design §2.4):
    auto-expiry on mismatch would rebuild the whole shortlist on any settings tweak, and an
    automatic re-open cannot be reviewed before it happens. This lists them; `reopen_jobs`
    releases them.
    """
    return {
        job_id: row
        for job_id, row in live_dispositions(conn, now=now).items()
        if row.policy_version is not None and row.policy_version != policy_version
    }


def reopen_jobs(conn: Connection, job_ids: Sequence[int], *, now: datetime) -> int:
    """Release dispositions so their jobs re-enter the shortlist. Returns rows affected.

    Sets `reopened_at` rather than deleting: draining a bucket must not erase the record that
    the bucket ever held anything, and `ledger show` can still report a drained decision.
    """
    if not job_ids:
        return 0
    result = conn.execute(
        update(job_dispositions)
        .where(
            job_dispositions.c.job_id.in_(list(job_ids)),
            job_dispositions.c.reopened_at.is_(None),
        )
        .values(reopened_at=now)
    )
    return int(result.rowcount)
