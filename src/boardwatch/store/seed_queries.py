"""Reads and writes for `lane_seeds` — the durable handoff from a discovering lane to a
resolving one.

Three functions and no more, because the POLICY belongs to the resolver: this module stores an
attempt counter and never decides what ceiling it means, exactly as `lanes/admission.py` owns the
company cap rather than `queries.upsert_lane_company`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Connection

from boardwatch.store.tables import lane_seeds


@dataclass(frozen=True)
class LaneSeed:
    """One unresolved seed, as a resolver reads it."""

    id: int
    url: str
    discovered_by: str
    attempts: int


def record_seeds(
    conn: Connection,
    urls: tuple[str, ...],
    *,
    discovered_by: str,
    run_id: int,
    now: datetime,
) -> int:
    """Record every URL this lane found and cannot resolve itself. Returns the number INSERTED.

    On conflict this touches NOTHING, `discovered_by` included, the same rule
    `upsert_lane_company` states and for the same reason: the second lane to see a URL did not
    discover it, and overwriting the provenance makes the store's own account of where something
    came from a lie with no recoverable prior value. It also means re-seeing a seed cannot reset
    its `attempts` — a permanently unresolvable URL that some lane re-lists every run would
    otherwise never age out of the candidate set, which is the cost leak the counter exists to
    bound.

    The return is the count actually inserted, not `len(urls)`, so a caller reporting "seeds
    discovered" reports NEW ones and a re-listed backlog can never read as fresh reach.

    Takes a tuple rather than one URL per call because the caller has the whole batch in hand and
    this runs inside the lane stage's single-writer transaction. An empty batch and an in-batch
    duplicate both fall out of the conflict clause and need no separate handling — an earlier
    version guarded each explicitly and a vacuity check showed neither guard could ever fire.
    """
    rows = [
        {
            "url": url,
            "discovered_by": discovered_by,
            "first_seen_run_id": run_id,
            "first_seen_at": now,
        }
        for url in urls
    ]
    inserted = 0
    for row in rows:
        result = conn.execute(
            sqlite_insert(lane_seeds).values(**row).on_conflict_do_nothing(index_elements=["url"])
        )
        inserted += result.rowcount
    return inserted


def unresolved_seeds(
    conn: Connection, *, max_attempts: int, limit: int
) -> tuple[LaneSeed, ...]:
    """Seeds no resolver has turned into a posting yet, under the caller's attempt ceiling.

    `max_attempts` and `limit` are keyword-only and have NO defaults. A default ceiling here
    would be this module quietly setting the resolver's retry policy, and a default limit would
    be it quietly setting the resolver's request budget — both are the caller's to state, and
    both are silent-cost paths if inherited.

    Ordered by `attempts` then `id`: a seed that has never been tried is tried before one that
    has already failed twice, so a budget too small to drain the backlog still makes progress on
    new discoveries instead of spending every run re-failing the same oldest rows.
    """
    stmt = (
        select(lane_seeds.c.id, lane_seeds.c.url, lane_seeds.c.discovered_by, lane_seeds.c.attempts)
        .where(lane_seeds.c.resolved_at.is_(None), lane_seeds.c.attempts < max_attempts)
        .order_by(lane_seeds.c.attempts, lane_seeds.c.id)
        .limit(limit)
    )
    return tuple(
        LaneSeed(id=row.id, url=row.url, discovered_by=row.discovered_by, attempts=row.attempts)
        for row in conn.execute(stmt)
    )


def record_seed_attempt(
    conn: Connection, seed_id: int, *, run_id: int, now: datetime, resolved: bool
) -> None:
    """Charge one attempt against a seed, and close it if the resolver succeeded.

    **The counter moves on success too, and `attempts` is therefore "times tried", not "times
    failed".** Anything else needs the caller to remember which of two calls to make, and the
    failure mode of forgetting is unbounded retries — the exact thing the column exists to stop.

    A resolved seed keeps its row with `resolved_at` set rather than being deleted, matching
    `job_dispositions.reopened_at`: draining a bucket must not erase the evidence it held
    something. `resolved_at` is never cleared, so a seed cannot re-enter the candidate set after
    a resolver has already produced a posting from it.
    """
    conn.execute(
        update(lane_seeds)
        .where(lane_seeds.c.id == seed_id)
        .values(
            attempts=lane_seeds.c.attempts + 1,
            last_attempt_run_id=run_id,
            last_attempt_at=now,
            **({"resolved_at": now} if resolved else {}),
        )
    )
