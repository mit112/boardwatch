"""Company hiring view (T308): who posts steadily, and how much of it is eligible.

Per company, over a trailing window (`WINDOW_DAYS`): new postings per week, how many of those are
ELIGIBLE NOW, and, over all time, the jobs applied to and withdrawn, plus the newest open eligible
role. The list is sorted by eligible per week, so a company that keeps opening roles the owner can
take comes first.

"New" is a `posting_events` row of kind `new` inside the window (a posting counts once). "Eligible"
is the posting's CURRENT deterministic verdict, the one `eligibility.read.current_verdicts` returns:
the evaluation under the live profile's (profile_hash, rules_hash) at the current engine version,
on the posting's newest version. `uncertain` (the engine's abstain) is neither eligible nor
ineligible and is not counted here at all: a company's `new` minus `eligible` is NOT "ineligible".
With no profile there is no current identity, so `eligible` is None for every company (unknown),
never 0.

How eligible is found. `current_verdicts` asks per posting version, which costs a lookup per
posting: a million for an 8-week window. So the read goes the other way, from the evaluations that
say `eligible` under the current identity (a full pass over the evaluation table, about 30 s on the
live 50 GB store, cold or warm), then keeps the postings whose newest version is the one that was
evaluated. The two readings agree by construction, and a test checks that on a fixture.

That pass is too slow to repeat, so the id-keyed aggregate is memoised in process. Its key is the
store file (path and inode), the latest finished run, the newest event id, the current identity and
engine version, and the UTC day (the window moves). The first view after a run pays the pass; every
later view is instant. Company names, the watched flag, applied and withdrawn counts and the
newest-role lookups are never memoised: they are read fresh for the rows shown.

A posting's company comes from `ix_postings_corpus` (the one index holding `company_id` next to the
rowid), read as a covering scan: a `postings` row carries the body text, so never read the table.

Applied counts jobs with an application whose status is in `APPLIED_STATUSES`; withdrawn counts
jobs with an application whose status is `withdrawn`. A job with two attempts, one of each, is in
both. A job is credited to the company of its newest posting, as the withdrawals read does.

Read-only. `created_at` mixes naive-UTC and offset-carrying text, so the window is cut in SQL with
`julianday` (which reads both as UTC), never by comparing raw text.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Connection, func, select, text

from boardwatch.eligibility.engine import ENGINE_KIND, engine_version
from boardwatch.eligibility.read import _posting_by_version
from boardwatch.store.applications import APPLIED_STATUSES
from boardwatch.store.lead_aging_queries import _naive
from boardwatch.store.param_chunks import id_chunks
from boardwatch.store.posting_lifetime_queries import _inode
from boardwatch.store.queries import current_posting_version_ids
from boardwatch.store.tables import (
    applications,
    companies,
    posting_events,
    posting_versions,
    postings,
    runs,
)
from boardwatch.store.tables import (
    eligibility_evaluations as ev,
)
from boardwatch.store.tables import (
    eligibility_inputs as ei,
)

WINDOW_DAYS = 56
ROWS_SHOWN = 50

# `INDEXED BY` is the point: without it the planner reads every posting row (see
# `posting_lifetime_queries`). The expression must name the index declared in `store/tables.py`.
_WINDOW_NEW = text(
    """
    SELECT e.posting_id AS posting_id, p.company_id AS company_id
    FROM (SELECT posting_id FROM posting_events
          WHERE kind = 'new' AND julianday(created_at) >= julianday(:now) - :days) AS e
    JOIN (SELECT id, company_id FROM postings INDEXED BY ix_postings_corpus) AS p
      ON p.id = e.posting_id
    """
)
_OPEN_OF_COMPANY = text(
    "SELECT id FROM postings INDEXED BY ix_postings_corpus"
    " WHERE status = 'open' AND company_id = :company"
)


@dataclass(frozen=True)
class _Aggregate:
    """Everything keyed by id; nothing here is a name or a flag the owner can change."""

    new: dict[int, int]  # company -> new postings in the window
    eligible_new: dict[int, int] | None  # company -> of those, eligible now; None: no identity
    eligible: frozenset[int]  # every posting eligible now, window or not (empty if unknown)


def _eligible_postings(conn: Connection, identity: tuple[str, str]) -> frozenset[int]:
    profile_hash, rules_hash = identity
    versions = {
        int(r.posting_version_id)
        for r in conn.execute(
            select(ei.c.posting_version_id)
            .join(ev, ev.c.input_id == ei.c.id)
            .where(
                ei.c.profile_hash == profile_hash,
                ei.c.rules_hash == rules_hash,
                ev.c.engine_kind == ENGINE_KIND,
                ev.c.engine_version == engine_version(),
                ev.c.verdict == "eligible",
            )
        )
    }
    by_posting = _posting_by_version(conn, sorted(versions))
    # An evaluation of a version the posting has since replaced is not its current verdict.
    newest = current_posting_version_ids(conn, sorted(set(by_posting.values())))
    return frozenset(pid for pid, vid in newest.items() if vid in versions)


def _aggregate(conn: Connection, identity: tuple[str, str] | None, now: datetime) -> _Aggregate:
    company_of: dict[int, int] = {}
    for r in conn.execute(_WINDOW_NEW, {"now": now.isoformat(sep=" "), "days": WINDOW_DAYS}):
        company_of[int(r.posting_id)] = int(r.company_id)  # a posting counts once
    new = Counter(company_of.values())
    if identity is None:
        return _Aggregate(dict(new), None, frozenset())
    eligible = _eligible_postings(conn, identity)
    eligible_new = Counter(company for pid, company in company_of.items() if pid in eligible)
    return _Aggregate(dict(new), dict(eligible_new), eligible)


_Key = tuple[
    str, int | None, int | None, int | None, int | None, tuple[str, str] | None, str, str
]
_memo: tuple[_Key, _Aggregate] | None = None


def _memo_key(conn: Connection, identity: tuple[str, str] | None, now: datetime) -> _Key:
    return (
        conn.engine.url.render_as_string(hide_password=True),
        _inode(conn.engine),
        conn.execute(select(func.max(runs.c.id)).where(runs.c.finished_at.is_not(None))).scalar(),
        conn.execute(select(func.max(posting_events.c.id))).scalar(),
        # `postings refetch --apply` adds a version with no run and no event (T320): without
        # this the warm memo could keep counting the verdict of the version it superseded.
        conn.execute(select(func.max(posting_versions.c.id))).scalar(),
        identity,
        engine_version(),
        now.date().isoformat(),
    )


def _cached_aggregate(
    conn: Connection, identity: tuple[str, str] | None, now: datetime
) -> _Aggregate:
    global _memo
    if _inode(conn.engine) is None:
        # No stat-able store file (in memory, or a path the URL escapes): nothing tells one store
        # from another, so never memoise.
        return _aggregate(conn, identity, now)
    key = _memo_key(conn, identity, now)
    held = _memo  # one read: the key and the payload tested and returned are the same tuple
    if held is not None and held[0] == key:
        return held[1]
    value = _aggregate(conn, identity, now)
    _memo = (key, value)
    return value


def _applications_by_company(conn: Connection) -> tuple[Counter[int], Counter[int]]:
    """(applied jobs, withdrawn jobs) per company, all time."""
    applied_jobs: set[int] = set()
    withdrawn_jobs: set[int] = set()
    for r in conn.execute(select(applications.c.job_id, applications.c.status)):
        if r.status in APPLIED_STATUSES:
            applied_jobs.add(int(r.job_id))
        elif r.status == "withdrawn":
            withdrawn_jobs.add(int(r.job_id))
    company_of: dict[int, int] = {}
    for chunk in id_chunks(sorted(applied_jobs | withdrawn_jobs)):
        for p in conn.execute(
            select(postings.c.job_id, postings.c.company_id)
            .where(postings.c.job_id.in_(chunk))
            .order_by(postings.c.id)
        ):
            company_of[int(p.job_id)] = int(p.company_id)  # the newest posting names the company
    applied = Counter(company_of[j] for j in applied_jobs if j in company_of)
    withdrawn = Counter(company_of[j] for j in withdrawn_jobs if j in company_of)
    return applied, withdrawn


def _newest_open_eligible(
    conn: Connection, company_id: int, eligible: frozenset[int], now: datetime
) -> dict[str, Any] | None:
    """The company's open, eligible-now posting that was first seen most recently.

    "Most recently first seen" is the highest posting id: ids are handed out when a posting is
    first stored and postings are never deleted, so no timestamp is compared.
    """
    open_ids = [int(r.id) for r in conn.execute(_OPEN_OF_COMPANY, {"company": company_id})]
    mine = [i for i in open_ids if i in eligible]
    if not mine:
        return None
    row = conn.execute(
        select(postings.c.id, postings.c.title, postings.c.first_seen_at).where(
            postings.c.id == max(mine)
        )
    ).one()
    return {
        "posting_id": int(row.id),
        "title": str(row.title),
        "age_days": round(max(0.0, (now - _naive(row.first_seen_at)).total_seconds() / 86_400), 1),
    }


def company_hiring(
    conn: Connection, identity: tuple[str, str] | None, now: datetime | None = None
) -> dict[str, Any]:
    """`identity` is the live profile's (profile_hash, rules_hash), or None when there is no
    profile (`eligibility.preflight.current_identity`)."""
    at = _naive(now) if now is not None else datetime.now(UTC).replace(tzinfo=None)
    base = _cached_aggregate(conn, identity, at)
    weeks = WINDOW_DAYS / 7
    known = base.eligible_new is not None

    meta = {
        int(r.id): r
        for r in conn.execute(
            select(companies.c.id, companies.c.name, companies.c.provider, companies.c.watched)
        )
    }
    watched = {i for i, r in meta.items() if r.watched}

    def rank(company_id: int) -> tuple[int, int, int]:
        got = base.eligible_new.get(company_id, 0) if base.eligible_new is not None else 0
        return (-got, -base.new[company_id], company_id)

    ordered = sorted((c for c in base.new if c in meta), key=rank)
    shown = ordered[:ROWS_SHOWN]
    shown_watched = [c for c in ordered if c in watched][:ROWS_SHOWN]

    applied, withdrawn = _applications_by_company(conn)

    def row(company_id: int) -> dict[str, Any]:
        info = meta[company_id]
        eligible = base.eligible_new.get(company_id, 0) if base.eligible_new is not None else None
        return {
            "company_id": company_id,
            "company": str(info.name),
            "provider": str(info.provider),
            "watched": company_id in watched,
            "new": base.new[company_id],
            "new_per_week": round(base.new[company_id] / weeks, 2),
            "eligible": eligible,
            "eligible_per_week": None if eligible is None else round(eligible / weeks, 2),
            "applied": applied.get(company_id, 0),
            "withdrawn": withdrawn.get(company_id, 0),
            "newest_open_eligible": (
                _newest_open_eligible(conn, company_id, base.eligible, at) if known else None
            ),
        }

    built = {c: row(c) for c in dict.fromkeys([*shown, *shown_watched])}
    return {
        "window_days": WINDOW_DAYS,
        "eligible_known": known,
        "new": sum(base.new.values()),
        "eligible": sum(base.eligible_new.values()) if base.eligible_new is not None else None,
        "companies": len(base.new),
        "rows": [built[c] for c in shown],
        "watched_rows": [built[c] for c in shown_watched],
    }
