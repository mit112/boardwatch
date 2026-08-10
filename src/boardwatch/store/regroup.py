"""Persist job regrouping (P6 slice 2, design §3.3).

Write order is load-bearing: `job_grouping_events` first, `postings.job_id` second. The events
table's own migration names itself the undo path for exactly this projection, and its
append-only triggers are what make that true.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import insert, select, update
from sqlalchemy.engine import Connection

from boardwatch.core.identity_kinds import IDENTITY_ALGORITHM_VERSION
from boardwatch.core.regroup import JobMerge
from boardwatch.store.tables import applications, artifacts, job_grouping_events, postings


def protected_job_ids(conn: Connection) -> frozenset[int]:
    """Jobs a regrouping may not move a posting off: those carrying tracking or artifact rows.

    `applications` is the tracking key (D-079) and `UNIQUE(job_id, attempt_no)` means two
    merged members with an attempt 1 each could never share a job anyway. `artifacts.job_id` is
    included because it is a real FK that `list_artifacts(job_id=...)` reads; measured
    2026-08-10 it is NULL on all 44 live rows (`record_artifact`'s two callers in `src/` never
    pass it), so this clause is latent — but latent is not unreachable, and the guard costs one
    OR.
    """
    rows = conn.execute(
        select(applications.c.job_id).union(
            select(artifacts.c.job_id).where(artifacts.c.job_id.is_not(None))
        )
    ).all()
    return frozenset(int(row[0]) for row in rows if row[0] is not None)


def job_anchors(conn: Connection, posting_ids: Sequence[int]) -> dict[int, int]:
    """`posting_id -> job_id` for the named postings, omitting any with no anchor.

    An omission is what `plan_regrouping` reads as `missing_job_anchor`, so a NULL `job_id`
    surfaces as a counted refusal instead of a merge onto nothing.
    """
    if not posting_ids:
        return {}
    rows = conn.execute(
        select(postings.c.id, postings.c.job_id).where(
            postings.c.id.in_(list(posting_ids)), postings.c.job_id.is_not(None)
        )
    ).all()
    return {int(row.id): int(row.job_id) for row in rows}


def apply_merges(
    conn: Connection,
    merges: Sequence[JobMerge],
    *,
    identity_kind: str,
    now: datetime,
) -> int:
    """Record each merge in the append-only trail, then move the projection. Returns rows moved.

    The event is written first on purpose: if the transaction fails between the two statements
    nothing is committed at all, and if a future change ever separates them the trail is the
    half that exists. `postings.job_id` is a projection and can be rebuilt from the trail; the
    trail cannot be rebuilt from the projection.
    """
    if not merges:
        return 0
    conn.execute(
        insert(job_grouping_events),
        [
            {
                "posting_id": merge.posting_id,
                "from_job_id": merge.from_job_id,
                "to_job_id": merge.to_job_id,
                "method": identity_kind,
                "algorithm_version": IDENTITY_ALGORITHM_VERSION,
                "evidence_json": {
                    "survivor_job_id": merge.to_job_id,
                    "identity_kind": identity_kind,
                },
                "created_at": now,
            }
            for merge in merges
        ],
    )
    moved = 0
    for merge in merges:
        result = conn.execute(
            update(postings)
            .where(postings.c.id == merge.posting_id, postings.c.job_id == merge.from_job_id)
            .values(job_id=merge.to_job_id)
        )
        moved += int(result.rowcount)
    return moved
