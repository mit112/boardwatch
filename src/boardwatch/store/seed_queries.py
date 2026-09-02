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

from sqlalchemy import and_, case, func, literal, or_, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Connection
from sqlalchemy.sql.elements import ColumnElement

from boardwatch.core.board_urls import is_seedable_url
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
    """What `record_seeds` did: rows INSERTED, and the URLs it REFUSED to seed.

    `unroutable` carries every URL the single write point would not store -- one with no parseable
    host, and (since the tier-D URL boundary closed) one that is not a safely seedable URL at all:
    no scheme, a bad port, or a control char HTTPX would reject at fetch. Both are the same kind of
    defect from a reader's seat -- a lane emitted a value nothing can ever resolve -- so they share
    one channel.

    It is returned rather than logged or swallowed. Swallowed, a lane emitting malformed URLs looks
    exactly like a lane finding nothing, which is the absent-versus-zero confusion the acquisition
    tally exists to prevent; raised, one bad row would roll back every good seed in the same batch
    AND cost the lane its whole report, because `_apply_lane` runs inside `_run_lanes`' broad
    per-lane `except`.
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

    Derived from validated `parsed.hostname`, not `parsed.netloc`: `.hostname` drops any `user@`
    and `:port` and lower-cases for us, so a seed on an explicit port (`newco.applytojob.com:443`)
    routes by bare host rather than storing `newco.applytojob.com:443`, a key no `hosts`/suffix
    filter can ever match. One trailing DNS root dot and a leading `www.` are stripped for the same
    reason: `newco.applytojob.com.` and `WWW.Breezy.HR` name the same host a strategy table lists
    once, and a row no filter matches can never be drained and never reports itself as stuck.

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
    host = (parsed.hostname or "").removesuffix(".").removeprefix("www.")
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

    **This is the ONE place a seed URL is validated, so ANY lane's seeds are checked once.** A URL
    that is not safely seedable -- no `://` scheme, a bad port, a control char HTTPX rejects at
    fetch, or no parseable host -- is skipped, named in `SeedWrite.unroutable`, and the rest of the
    batch is written. `is_seedable_url` is the same gate the Indeed and JSON-LD lanes apply before
    seeding, enforced here so a lane that skipped it (or a future one that forgets) still cannot
    persist a row nothing can ever resolve: the blocker that closed the tier-D boundary was exactly
    a lane reaching `lane_seeds` by a path that did not validate. Letting a bad value raise would
    abort the whole statement inside `_apply_lane`'s transaction — losing every valid seed beside it
    AND, via `_run_lanes`' broad per-lane `except`, the lane's entire report. One malformed value
    from an aggregator must not be able to do that.

    Takes a tuple rather than one URL per call because the caller has the whole batch in hand and
    this runs inside the lane stage's single-writer transaction. An empty batch and an in-batch
    duplicate both fall out of the conflict clause and need no separate handling — an earlier
    version guarded each explicitly and a vacuity check showed neither guard could ever fire.
    """
    rows = []
    unroutable = []
    for url in urls:
        if not is_seedable_url(url):
            # Not a URL a resolver could GET (no scheme, a bad port, a control char, no host).
            # Refused here at the single write point, before `seed_host` -- a value HTTPX would
            # reject at fetch must never persist as an undrainable row.
            unroutable.append(url)
            continue
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


def _seed_routes(
    hosts: frozenset[str], host_suffixes: frozenset[str]
) -> list[ColumnElement[bool]]:
    """The predicate "this seed's host is claimed by a catalog spelling `hosts`/`host_suffixes`".

    Shared, so `unresolved_seeds` (what a resolver SELECTS) and `read_seed_claims` (what NO
    resolver can select) can never disagree about what "claimed" means. Two spellings of one
    routing rule is how a vendor joins the catalog and never the report — the same failure
    `jsonld.SEED_HOSTS` warns about one layer up — and here it is silent in the worse direction:
    a host the report calls unclaimed while a resolver quietly drains it sends someone to build a
    resolver that already exists.
    """
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
    return routes


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
    routes = _seed_routes(hosts, host_suffixes)
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
    ceiling counter does not. Two turns are deliberately not charged toward the ceiling -- not
    because the fetch failed (a charged resolution's fetch succeeded too), but because charging
    either would retire a seed that still owes work: a seed that resolved but whose batch apply did
    not prove its snapshot
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


@dataclass(frozen=True)
class ResolverCatalog:
    """One resolver's seed routing, as `unresolved_seeds` actually selects by it.

    Carries `max_attempts` alongside the host sets because `unresolved_seeds` filters on BOTH — a
    seed on a claimed host that has exhausted the ceiling is never selected again. Splitting the
    report on host alone would count that permanently-undrainable row as `claimable`, and since the
    retired pile only grows, the unclaimed share would drift toward "drained" precisely as the leak
    got worse.
    """

    hosts: frozenset[str]
    host_suffixes: frozenset[str]
    max_attempts: int


def _claimable(catalogs: tuple[ResolverCatalog, ...]) -> ColumnElement[bool] | None:
    """"Some registered resolver would SELECT this seed", or `None` if none ever could.

    Per catalog rather than over a merged host set, because the ceiling is per resolver: a seed can
    be past one resolver's limit and inside another's, and merging would answer neither question.
    `None` (not a false literal) when nothing is registered, so the caller can distinguish "no
    resolver claims anything" from "this predicate excludes everything".
    """
    clauses = []
    for catalog in catalogs:
        routes = _seed_routes(catalog.hosts, catalog.host_suffixes)
        if not routes:
            continue
        clauses.append(
            and_(or_(*routes), lane_seeds.c.attempts < catalog.max_attempts)
        )
    return or_(*clauses) if clauses else None


@dataclass(frozen=True)
class UnclaimedHost:
    """One host holding unresolved seeds that no registered resolver's catalog claims."""

    host: str
    seeds: int
    discovered_by: tuple[str, ...]
    first_seen_run_id: int
    # The largest `attempts` on this host. 0 means no catalog ever covered it; a value at some
    # resolver's ceiling means one did and gave up. Different problems, different fixes.
    max_attempts_spent: int


@dataclass(frozen=True)
class SeedClaimReading:
    """One reading of the seed queue: its size, and the hosts nothing can drain."""

    unresolved: int
    unclaimed_hosts: tuple[UnclaimedHost, ...]


def read_seed_claims(
    conn: Connection, *, catalogs: tuple[ResolverCatalog, ...]
) -> SeedClaimReading:
    """The unresolved queue split by whether any ENABLED resolver would ever select the row.

    **ONE statement, deliberately, and a transaction would not have been enough.** The obvious
    shape — count the queue, then group the unclaimed part — is two statements, and on SQLite that
    is two SNAPSHOTS: pysqlite does not begin a transaction for a `SELECT`, so even inside
    `conn.begin()` each read sees the database as of its own execution. A concurrent run inserting
    seeds between them makes the breakdown larger than the total, and since the report publishes
    `claimed = unresolved - unclaimed`, it prints a NEGATIVE count and a share above 100%.
    Reproduced at `unresolved: 9, unclaimed: 12, claimable -3 (133.3%)` before this was one query.
    Grouping on the claim predicate itself removes the hazard by construction rather than relying
    on driver transaction semantics.

    The unclaimed test is the exact negation of `unresolved_seeds`' selection — host routing AND the
    attempt ceiling, per resolver — because a bound on work only bounds work that happens: a seed no
    catalog covers is never attempted, so `attempts` never retires it, and it sits invisible rather
    than merely slow.

    **`catalogs` should be the ENABLED resolvers, not merely the registered ones.**
    `settings.lanes_enabled` is empty by default and the runner builds only the lanes it names, so a
    resolver that exists but is switched off drains nothing; counting its hosts as claimable would
    report the leak's worst case as its healthy half. No catalogs therefore means every unresolved
    seed is unclaimed — the honest answer, and it makes a registry that failed to load read as a
    total leak rather than as a drained queue.
    """
    claimable = _claimable(catalogs)
    claimed_flag = (
        case((claimable, literal(1)), else_=literal(0)) if claimable is not None else literal(0)
    ).label("claimed")
    stmt = (
        select(
            claimed_flag,
            lane_seeds.c.host,
            func.count().label("seeds"),
            func.group_concat(lane_seeds.c.discovered_by.distinct()).label("discovered_by"),
            func.min(lane_seeds.c.first_seen_run_id).label("first_seen_run_id"),
            func.max(lane_seeds.c.attempts).label("max_attempts_spent"),
        )
        .where(lane_seeds.c.resolved_at.is_(None))
        .group_by(claimed_flag, lane_seeds.c.host)
        .order_by(func.count().desc(), lane_seeds.c.host)
    )
    rows = conn.execute(stmt).all()
    return SeedClaimReading(
        unresolved=sum(row.seeds for row in rows),
        unclaimed_hosts=tuple(
            UnclaimedHost(
                host=row.host,
                seeds=row.seeds,
                discovered_by=tuple(sorted((row.discovered_by or "").split(","))),
                first_seen_run_id=row.first_seen_run_id,
                max_attempts_spent=row.max_attempts_spent,
            )
            for row in rows
            if not row.claimed
        ),
    )
