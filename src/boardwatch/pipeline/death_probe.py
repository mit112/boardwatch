"""Let a MEASURED death close a posting the scanner structurally cannot reach (D-325).

**The population, and why it needs its own mechanism.** `_process_missing` (`scan/apply.py`) is
the only writer of `status='closed'`, it runs on `complete` snapshots only, `lane_snapshot` is
always `partial`, and lane companies are inserted `watched=False` so the coordinator never
revisits them (D-314). A lane re-acquires by SEARCH, not by enumerating a board, so a posting
that drops out of the result set is simply never seen again — **absence can never be evidence**
for these rows, armed or disarmed. Age-based and missed-run closing were both measured and
REJECTED: when the role facet changed, 0 of 290 prior postings were re-seen, yet 40 of 45 probed
were still alive.

What is left is a POSITIVE observation: the stored URL itself answering gone. This module makes
exactly that, and nothing else, able to close a posting.

**The four narrowings, each of which is the whole safety argument.**

1. **Only `refetch_gone`.** A non-redirect 404/410 from the URL asked about. Never
   `refetch_gone_after_redirect` — `Fetcher` follows redirects, so an employer migrating ATS
   answers 404 from a host that was never asked about, and closing on it would retire live
   requisitions one employer at a time. Never `refetch_error`: a timeout, a 403 from a
   bot-blocker or a 5xx says nothing about the requisition. `core/liveness.py` owns that
   classification and this module reads its typed signal, never a status code or a message.
2. **Only `companies.watched = 0`.** Exactly the rows for which the scanner cannot produce a
   signal. A watched board enumerates itself and closes its own postings correctly; adding a
   second, weaker path over it would be a regression, not a fix. The predicate is the honest
   one — it covers unwatched `source='user'` companies too, which have the identical defect.
3. **Two consecutive strikes in different runs**, mirroring `CLOSE_AFTER_MISSES = 2`. An
   `unknown` probe neither increments nor resets, which mirrors the board path exactly: there a
   `failed` snapshot leaves `consecutive_missing` alone and only a POSITIVE observation resets
   it (D23). The alternative — unknown resets — disarms the check against any host that
   intermittently 403s.
4. **Its own column.** `death_strikes`, never `consecutive_missing`. One counter fed by two
   different signals could close a posting on one board absence plus one 404, and no report
   could then say which evidence closed it.

**The drain, on both sides of the gate.** An `alive` probe clears the counter here; a positive
board or lane sighting clears it in `_apply_listed`, alongside the `consecutive_missing` reset
it has always done. A posting this closes is reopened by the ordinary re-sighting path, which
runs on `partial` snapshots — verified in source: `apply_board` calls `_apply_listed` for every
non-failed, non-unchanged snapshot, and only `_process_missing` and `_persist_validators` are
gated on `complete`.

**What this is worth, stated plainly because it will otherwise be trusted.** Measured against a
control of postings the scanner PROVED closed (n=60) it detects **4 — 6.7%**, Wilson 95% CI
2.6%–15.9%. By provider: greenhouse 4/21, **workday 0/37** — every closed Workday requisition
still answers HTTP 200. Against 90 live lane postings it returned **0 false deaths**. It almost
never lies and it almost never fires. The lane corpus is worse ground than that control: only
5.1% of lane postings sit on a registry ATS host and 30.5% are LinkedIn, where 33 of 33 answered
200. This resolves roughly 7% of D-314; it does not close it.

**Cost.** A probe costs ~0.97 s. 471 lane rows is ~7.3 min of a run today and the class grows
~182/day, so an unbounded sweep would exceed the run itself within a month. Hence a per-run
budget and a TTL, both configurable, and both sides of the budget reported: a sweep that
refuses work must read as refused work, never as a clean corpus.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import ColumnElement, Engine, and_, case, func, or_, select, update

from boardwatch.core.clock import utcnow
from boardwatch.pipeline.liveness import LivenessProber
from boardwatch.reports.run_funnel import DeathProbeReport
from boardwatch.scan.apply import CLOSE_AFTER_MISSES
from boardwatch.store.events import append_event
from boardwatch.store.tables import companies, postings

# The ONE liveness signal permitted to close a posting, compared as a catalog member rather than
# re-derived from a status code: `core/liveness.py` owns what "gone" means, including the
# redirect rule, and a second derivation here would let the two drift.
CLOSING_SIGNAL = "refetch_gone"


def unreachable_by_the_scanner() -> ColumnElement[bool]:
    """Open postings under a company nothing enumerates — the D-314 defect predicate.

    `watched = 0` rather than `companies.source = 'lane'`: the defect is that no board scan
    covers the company, and 274 unwatched `source='user'` companies have it too. Naming the lane
    would have fixed the symptom for one acquirer and left the identical rows untouched under
    another.
    """
    return and_(postings.c.status == "open", companies.c.watched.is_(False))


def sweep_unwatched_deaths(
    engine: Engine,
    *,
    prober: LivenessProber,
    run_id: int,
    budget: int,
    ttl_hours: int,
) -> DeathProbeReport:
    """Probe up to `budget` unreachable-by-the-scanner postings and close the proven-dead ones.

    Writes, unlike `pipeline/liveness.py::check_leads` — that one probes the SHORTLIST and its
    "reads URLs; writes nothing, ever" contract is what stops a flaky CDN retiring a live lead.
    This is a different question over a different population, and that difference is the whole
    of D-325.
    """
    now = utcnow()
    cutoff = now - timedelta(hours=ttl_hours)
    due_predicate = and_(
        unreachable_by_the_scanner(),
        or_(
            postings.c.last_death_probe_at.is_(None),
            postings.c.last_death_probe_at < cutoff,
        ),
    )
    has_url = and_(postings.c.url.is_not(None), postings.c.url != "")
    board = postings.join(companies, companies.c.id == postings.c.company_id)

    with engine.connect() as conn:
        # One pass for both denominators. `unprobeable` is a row this mechanism can never reach
        # by any future refinement — `postings.url` is nullable — so it is reported rather than
        # filtered away, which would hide a permanently stuck slice inside a sweep claiming to be
        # complete.
        counts = conn.execute(
            select(
                func.coalesce(func.sum(case((has_url, 1), else_=0)), 0).label("due"),
                func.coalesce(func.sum(case((has_url, 0), else_=1)), 0).label("unprobeable"),
            )
            .select_from(board)
            .where(due_predicate)
        ).one()
        # Least-recently-probed first, NULL (never asked) ahead of everything. Ordering by `id`
        # would probe the same head every run for ever and never reach the tail, while
        # `attempted` reported a busy sweep. `LIMIT` IS the budget, so this is bounded by
        # construction and never binds a corpus-scaled `IN (...)` (D-287).
        candidates = conn.execute(
            select(postings.c.id, postings.c.url, postings.c.death_strikes)
            .select_from(board)
            .where(and_(due_predicate, has_url))
            .order_by(postings.c.last_death_probe_at.asc(), postings.c.id.asc())
            .limit(budget)
        ).all()

    gone = unknown = alive = closed = strikes_cleared = 0
    for row in candidates:
        result = prober(int(row.id), str(row.url))
        strikes = int(row.death_strikes)
        if result.signal == CLOSING_SIGNAL:
            gone += 1
            strikes += 1
        elif result.verdict == "alive":
            alive += 1
            # The drain. A strike is a suspicion, not a sentence.
            strikes_cleared += 1 if strikes else 0
            strikes = 0
        else:
            # Every remaining outcome, `refetch_gone_after_redirect` included. Counted, never
            # silently absorbed: that bucket is the one that can disarm this check with no other
            # number moving, exactly as it can for the shortlist probe (D-113).
            unknown += 1

        values: dict[str, object] = {
            "death_strikes": strikes,
            # Written on EVERY outcome, so one permanently-unreachable host cannot consume the
            # whole budget each run and starve the rest of the class — a failure indistinguishable
            # from a healthy sweep if only `attempted` is read.
            "last_death_probe_at": now,
        }
        closing = strikes >= CLOSE_AFTER_MISSES
        if closing:
            values["status"] = "closed"
            values["closed_at"] = now
            closed += 1
        # One transaction per posting, mirroring `apply_board`'s per-board atomicity: the row
        # update and its event commit or vanish together, and a probe that raises mid-sweep
        # leaves every earlier decision durable instead of rolling the whole sweep back.
        with engine.begin() as write:
            write.execute(update(postings).where(postings.c.id == row.id).values(**values))
            if closing:
                append_event(write, int(row.id), "closed", run_id)

    return DeathProbeReport(
        due=int(counts.due),
        unprobeable=int(counts.unprobeable),
        attempted=len(candidates),
        budget_refused=int(counts.due) - len(candidates),
        gone=gone,
        unknown=unknown,
        alive=alive,
        closed=closed,
        strikes_cleared=strikes_cleared,
    )


__all__ = ["CLOSING_SIGNAL", "sweep_unwatched_deaths", "unreachable_by_the_scanner"]
