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
from boardwatch.core.ledger import is_live
from boardwatch.core.regroup import JobMerge
from boardwatch.store.ledger_queries import load_dispositions, record_disposition, reopen_jobs
from boardwatch.store.tables import applications, artifacts, job_grouping_events, postings


def protected_job_ids(conn: Connection) -> frozenset[int]:
    """Jobs a regrouping may not move a posting off: those carrying tracking or artifact rows.

    `applications` is the tracking key (D-079) and `UNIQUE(job_id, attempt_no)` means two
    merged members with an attempt 1 each could never share a job anyway. `artifacts.job_id` is
    included because it is a real FK that `list_artifacts(job_id=...)` reads; measured
    2026-08-10 it is NULL on all 44 live rows (`record_artifact`'s three call sites in `src/`
    never pass it), and no setting or config path reaches that argument — so unlike the
    `applications` half (which `boardwatch track` reaches today) this clause needs a code change to
    fire. It is kept because the guard costs one OR, not because it is currently latent.
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
    """Record each merge in the trail, move the projection, carry the ledger. Returns rows moved.

    The event is written first on purpose: if the transaction fails between the two statements
    nothing is committed at all, and if a future change ever separates them the trail is the
    half that exists. `postings.job_id` is a projection and can be rebuilt from the trail; the
    trail cannot be rebuilt from the projection — which is why only merges that actually move a
    row get an event (see below), since a trail full of moves that never happened cannot rebuild
    anything.

    `_carry_dispositions` runs last, inside the same transaction: the postings and the decision
    that governs them move together or not at all.
    """
    if not merges:
        return 0
    # Only merges whose anchor still reads what the plan was built against. Re-checked HERE, in
    # the writing transaction, because the trail is the documented undo path: an event for an
    # UPDATE that then matches 0 rows claims a move that never happened, and rebuilding the
    # projection from a trail like that would move a posting nobody moved. The guard on the UPDATE
    # below still stands — this narrows what gets a trail entry, it does not replace the guard.
    current = {
        int(row.id): row.job_id
        for row in conn.execute(
            select(postings.c.id, postings.c.job_id).where(
                postings.c.id.in_([merge.posting_id for merge in merges])
            )
        ).all()
    }
    live = [merge for merge in merges if current.get(merge.posting_id) == merge.from_job_id]
    if not live:
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
            for merge in live
        ],
    )
    moved = 0
    for merge in live:
        result = conn.execute(
            update(postings)
            .where(postings.c.id == merge.posting_id, postings.c.job_id == merge.from_job_id)
            .values(job_id=merge.to_job_id)
        )
        moved += int(result.rowcount)
    _carry_dispositions(conn, live, now=now)
    return moved


def _carry_dispositions(conn: Connection, merges: Sequence[JobMerge], *, now: datetime) -> None:
    """Move each emptied job's ledger decision onto the canonical job, then release the original.

    Without this a merge silently un-suppresses an already-handled group. The decision is keyed on
    a job; regrouping moves the postings off that job onto the survivor's, so a `built` row is left
    governing a job nothing anchors while the canonical job carries nothing — and the lead the
    program already built is surfaced and tailored a second time. That is the exact defect this
    slice exists to remove, reintroduced through the projection it added.

    `record_disposition` is monotonic, so carrying is safe in both directions: the strongest
    decision among the group's members wins and a canonical job already `built` is left alone.
    The source row is then `reopened_at`-stamped rather than deleted — the same drain the ledger
    uses everywhere else — so it stops governing without erasing that it ever did. A live row on a
    job that anchors no postings would be a quarantine with no re-entry path, which CLAUDE.md
    forbids outright.
    """
    from_jobs = {merge.from_job_id for merge in merges}
    to_by_from = {merge.from_job_id: merge.to_job_id for merge in merges}
    carried = load_dispositions(conn, sorted(from_jobs))
    released: list[int] = []
    for from_job, row in carried.items():
        if not is_live(expires_at=row.expires_at, reopened_at=row.reopened_at, now=now):
            continue
        to_job = to_by_from[from_job]
        if to_job == from_job:
            continue
        record_disposition(
            conn,
            to_job,
            disposition=row.disposition,
            reason=row.reason,
            policy_version=row.policy_version,
            expires_at=row.expires_at,
            now=now,
        )
        released.append(from_job)
    reopen_jobs(conn, released, now=now)
