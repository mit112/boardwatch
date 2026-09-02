"""Reads and writes for `lane_seeds` — the durable handoff from a discovering lane to a
resolving one.

Three functions and no more, because the POLICY belongs to the resolver: this module stores an
attempt counter and never decides what ceiling it means, exactly as `lanes/admission.py` owns the
company cap rather than `queries.upsert_lane_company`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from urllib.parse import urlparse

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Connection

from boardwatch.store.tables import lane_seeds


@dataclass(frozen=True)
class LaneSeed:
    """One unresolved seed, as a resolver reads it."""

    id: int
    url: str
    host: str
    discovered_by: str
    attempts: int


class SeedReader(Protocol):
    """How a lane reads pending seeds without ever touching a `Connection`.

    The runner owns the connection and hands a lane this closure, exactly as it hands one
    `CompanyAdmission`: the decision needs store access, the lane runs in a fetch worker, and
    `apply_board` is the pipeline's single writer. A lane that opened its own engine would be a
    second writer's worth of risk for a read.

    Keyword-only, so a caller cannot silently swap `max_attempts` and `limit` — two ints whose
    transposition is a cost bug no type checker would see.
    """

    def __call__(
        self, *, hosts: frozenset[str], max_attempts: int, limit: int
    ) -> tuple[LaneSeed, ...]: ...


def seed_host(url: str) -> str:
    """The host a seed is routed by. Derived here so every writer agrees on the spelling.

    Lower-cased and `www.`-stripped: a resolver's strategy table lists a vendor host once, and a
    seed recorded as `WWW.Breezy.HR` that no `hosts` filter matches is a row that can never be
    drained and never reports itself as stuck.
    """
    parsed = urlparse(url if "://" in url else f"https://{url}")
    return parsed.netloc.lower().removeprefix("www.")


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
            # Derived, never passed in: a discovering lane knows nothing about which resolver
            # will claim a URL, and a caller-supplied host is a caller-supplied routing bug.
            "host": seed_host(url),
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
    conn: Connection, *, hosts: frozenset[str], max_attempts: int, limit: int
) -> tuple[LaneSeed, ...]:
    """Seeds no resolver has turned into a posting yet, on hosts THIS resolver can handle.

    **`hosts` is required and there is no all-hosts form.** Without it the table is one pool and
    the `limit` picks by age alone: a resolver taking one seed a run is handed whatever is
    oldest, so a vendor it cannot parse starves every vendor behind it forever, and charging an
    attempt against a seed some future resolver owns spends a budget that is not this lane's.
    Each resolver passes the exact hosts its own strategy table covers.

    `max_attempts` and `limit` are keyword-only with NO defaults, for the same reason: a default
    ceiling would be this module quietly setting the retry policy and a default limit would be it
    quietly setting the request budget. Both are the caller's to state.

    Both ints are validated rather than trusted. A negative `limit` is not a smaller bound — it
    is SQLite's spelling of NO bound (`LIMIT -1`), so the one thing this argument exists to
    promise would be silently defeated by a caller that computed a budget and got a subtraction
    wrong. A negative `max_attempts` selects nothing, which reads as a drained backlog.

    Ordered by `attempts` then `id`: a seed that has never been tried is tried before one that
    has already failed twice, so a budget too small to drain the backlog still makes progress on
    new discoveries instead of spending every run re-failing the same oldest rows.
    """
    if limit < 0 or max_attempts < 0:
        raise ValueError(
            f"limit and max_attempts must be non-negative; got {limit}, {max_attempts}"
        )
    if not hosts:
        return ()
    stmt = (
        select(
            lane_seeds.c.id,
            lane_seeds.c.url,
            lane_seeds.c.host,
            lane_seeds.c.discovered_by,
            lane_seeds.c.attempts,
        )
        .where(
            lane_seeds.c.resolved_at.is_(None),
            lane_seeds.c.host.in_(sorted(hosts)),
            lane_seeds.c.attempts < max_attempts,
        )
        .order_by(lane_seeds.c.attempts, lane_seeds.c.id)
        .limit(limit)
    )
    return tuple(
        LaneSeed(
            id=row.id,
            url=row.url,
            host=row.host,
            discovered_by=row.discovered_by,
            attempts=row.attempts,
        )
        for row in conn.execute(stmt)
    )


def record_seed_attempt(
    conn: Connection, seed_id: int, *, run_id: int, now: datetime, resolved: bool
) -> None:
    """Charge one attempt against a seed, and close it if the resolver succeeded.

    **The counter moves on success too, so `attempts` is "times tried", not "times failed".**
    That is an AUDIT-SEMANTICS contract, not a retry-safety requirement, and the earlier note
    here claiming otherwise was false: this function already receives `resolved` and could
    increment conditionally, and doing so could not make retries unbounded because every row that
    re-enters the candidate set is necessarily one that failed. What the contract buys is that
    `attempts` answers "how much work has this seed cost" — the question a cost bound is actually
    about — rather than "how many times has it disappointed us".

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
