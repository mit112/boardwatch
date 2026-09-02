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

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Connection
from sqlalchemy.sql.elements import ColumnElement

from boardwatch.store.tables import lane_seeds


class UnroutableSeedURL(ValueError):
    """A seed URL that cannot be routed to any resolver, raised where it is detected.

    Typed rather than a bare `ValueError` because the caller has to tell "this one row is
    unusable" from "the statement failed": the first must cost that seed alone, and the second
    must fail the transaction. `urlparse` raises a BARE `ValueError` ("Invalid IPv6 URL") for an
    unbalanced bracket, which is indistinguishable from any other `ValueError` a caller might be
    catching for another reason.
    """


@dataclass(frozen=True)
class SeedWrite:
    """What `record_seeds` did: rows INSERTED, and the URLs it could not route.

    `unroutable` is returned rather than logged or swallowed. Swallowed, a lane emitting
    malformed URLs looks exactly like a lane finding nothing, which is the absent-versus-zero
    confusion the acquisition tally exists to prevent; raised, one bad row would roll back every
    good seed in the same batch AND cost the lane its whole report, because `_apply_lane` runs
    inside `_run_lanes`' broad per-lane `except`.
    """

    inserted: int
    unroutable: tuple[str, ...] = ()


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
        self,
        *,
        hosts: frozenset[str],
        host_suffixes: frozenset[str],
        max_attempts: int,
        limit: int,
    ) -> tuple[LaneSeed, ...]: ...


def seed_host(url: str) -> str:
    """The host a seed is routed by. Derived here so every writer agrees on the spelling.

    Lower-cased and `www.`-stripped: a resolver's strategy table lists a vendor host once, and a
    seed recorded as `WWW.Breezy.HR` that no `hosts` filter matches is a row that can never be
    drained and never reports itself as stuck.

    Raises `UnroutableSeedURL` for a URL with no host, rather than storing one. An empty `host`
    matches no resolver's filter, so such a row would sit unresolved and unattempted forever and
    report itself as nothing at all — invisible work, which is worse than a refusal.
    """
    try:
        parsed = urlparse(url if "://" in url else f"https://{url}")
    except ValueError as exc:
        # `urlsplit` raises a BARE ValueError ("Invalid IPv6 URL") for an unbalanced bracket, the
        # same trap `core/board_urls.py` records at its own `urlparse` call.
        raise UnroutableSeedURL(f"cannot parse a host from {url!r}: {exc}") from exc
    host = parsed.netloc.lower().removeprefix("www.")
    if not host:
        raise UnroutableSeedURL(f"no host in {url!r}")
    return host


def record_seeds(
    conn: Connection,
    urls: tuple[str, ...],
    *,
    discovered_by: str,
    run_id: int,
    now: datetime,
) -> SeedWrite:
    """Record every URL this lane found and cannot resolve itself.

    On conflict this touches NOTHING, `discovered_by` included, the same rule
    `upsert_lane_company` states and for the same reason: the second lane to see a URL did not
    discover it, and overwriting the provenance makes the store's own account of where something
    came from a lie with no recoverable prior value. It also means re-seeing a seed cannot reset
    its `attempts` — a permanently unresolvable URL that some lane re-lists every run would
    otherwise never age out of the candidate set, which is the cost leak the counter exists to
    bound.

    The return carries the count actually INSERTED, not `len(urls)`, so a caller reporting "seeds
    discovered" reports NEW ones and a re-listed backlog can never read as fresh reach.

    **A URL with no parseable host costs that URL and nothing else.** It is skipped, named in
    `SeedWrite.unroutable`, and the rest of the batch is written. Letting it raise would abort the
    whole statement inside `_apply_lane`'s transaction — losing every valid seed beside it AND, via
    `_run_lanes`' broad per-lane `except`, the lane's entire report. One malformed value from an
    aggregator must not be able to do that.

    Takes a tuple rather than one URL per call because the caller has the whole batch in hand and
    this runs inside the lane stage's single-writer transaction. An empty batch and an in-batch
    duplicate both fall out of the conflict clause and need no separate handling — an earlier
    version guarded each explicitly and a vacuity check showed neither guard could ever fire.
    """
    rows = []
    unroutable = []
    for url in urls:
        try:
            # Derived, never passed in: a discovering lane knows nothing about which resolver
            # will claim a URL, and a caller-supplied host is a caller-supplied routing bug.
            host = seed_host(url)
        except UnroutableSeedURL:
            unroutable.append(url)
            continue
        rows.append(
            {
                "url": url,
                "host": host,
                "discovered_by": discovered_by,
                "first_seen_run_id": run_id,
                "first_seen_at": now,
            }
        )
    inserted = 0
    for row in rows:
        result = conn.execute(
            sqlite_insert(lane_seeds).values(**row).on_conflict_do_nothing(index_elements=["url"])
        )
        inserted += result.rowcount
    return SeedWrite(inserted=inserted, unroutable=tuple(unroutable))


def unresolved_seeds(
    conn: Connection,
    *,
    hosts: frozenset[str],
    host_suffixes: frozenset[str] = frozenset(),
    max_attempts: int,
    limit: int,
) -> tuple[LaneSeed, ...]:
    """Seeds no resolver has turned into a posting yet, on hosts THIS resolver can handle.

    **A host set is required and there is no all-hosts form.** Without one the table is a single
    pool and the `limit` picks by age alone: a resolver taking one seed a run is handed whatever
    is oldest, so a vendor it cannot parse starves every vendor behind it forever, and charging
    an attempt against a seed some future resolver owns spends a budget that is not this lane's.

    **`host_suffixes` exists because most per-tenant vendors give every employer its own
    subdomain**, and those tenants CANNOT be enumerated in advance. JazzHR is
    `<tenant>.applytojob.com`, Breezy `<tenant>.breezy.hr`, CareerPlug
    `<tenant>.careerplug.com`. With exact hosts alone, a seed another lane discovered on a tenant
    this resolver has never seen is invisible: nothing selects it, so nothing attempts it, so the
    attempt bound never ages it out and no report ever names it. That is a bucket with no drain —
    invisible work, which is worse than a refusal. A suffix matches the bare host AND any
    subdomain of it (`applytojob.com` and `x.applytojob.com`, never `notapplytojob.com`).

    Both are offered rather than only suffixes, because they say different things: `hosts` claims
    ONE host, `host_suffixes` claims a vendor's whole tenant space. A resolver serving a
    single-host vendor (`recruiting.paylocity.com`) should not silently also claim
    `anything.recruiting.paylocity.com`.

    **Cost, stated because it is a real trade:** the suffix arm is a `LIKE` and cannot use
    `ix_lane_seeds_resolved_at_host_attempts` beyond its `resolved_at` prefix, so it scans the
    UNRESOLVED rows. That set is bounded by design — the attempt ceiling and the resolvers'
    drains are what keep it small — and it is the only shape that does not require either a
    public-suffix dependency or a routing key the discovering lane would have to guess.

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
    if not hosts and not host_suffixes:
        return ()
    routes: list[ColumnElement[bool]] = (
        [lane_seeds.c.host.in_(sorted(hosts))] if hosts else []
    )
    for suffix in sorted(host_suffixes):
        # The bare host AND any subdomain of it. `like` with an explicit `.` separator rather
        # than `host LIKE '%' || suffix`, which would also match `notapplytojob.com` — a
        # different vendor's registrable domain that merely ends in the same characters.
        routes.append(
            or_(lane_seeds.c.host == suffix, lane_seeds.c.host.like(f"%.{suffix}"))
        )
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
            or_(*routes),
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
    conn: Connection,
    seed_id: int,
    *,
    run_id: int,
    now: datetime,
    resolved: bool,
    charge: bool = True,
) -> None:
    """Record one turn against a seed, and close it if the resolver succeeded.

    **`attempts` counts the fetch attempts CHARGED TOWARD THE RETIREMENT CEILING, not turns.**
    It moves on a charged success too, so it is "how much work has this seed cost" rather than
    "how many times has it failed" — the question a cost bound is actually about, and the reason
    `unresolved_seeds` retires a row at `attempts >= max_attempts`. `resolved` and `charge` are
    independent because a turn has two independent facts: did it produce a posting, and did it
    spend a request that the ceiling should count.

    **`charge=False` records the turn WITHOUT moving `attempts`.** `last_attempt_run_id` and
    `last_attempt_at` still advance, and `resolved_at` is still set iff `resolved`, but the
    ceiling counter does not. Two turns are deliberately not charged, because in neither did the
    seed's own fetch fail: a seed that resolved but whose batch apply did not prove its snapshot
    landed (applies are PER-COMPANY transactions, so a later company aborting leaves this one
    unproven -- the FETCH ceiling must not retire it before a clean run can land it), and a
    redundant alias closed without a GET (it cost no request at all). The default charges,
    preserving the behaviour of every existing caller.

    A resolved seed keeps its row with `resolved_at` set rather than being deleted, matching
    `job_dispositions.reopened_at`: draining a bucket must not erase the evidence it held
    something. `resolved_at` is never cleared, so a seed cannot re-enter the candidate set after
    a resolver has already produced a posting from it.
    """
    conn.execute(
        update(lane_seeds)
        .where(lane_seeds.c.id == seed_id)
        .values(
            **({"attempts": lane_seeds.c.attempts + 1} if charge else {}),
            last_attempt_run_id=run_id,
            last_attempt_at=now,
            **({"resolved_at": now} if resolved else {}),
        )
    )
