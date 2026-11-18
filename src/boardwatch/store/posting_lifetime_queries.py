"""Posting lifetime against time to apply (T307): how long postings stay open vs how fast we apply.

Lifetime is `new` -> first `closed` in `posting_events`. A posting that never closed is CENSORED: it
is counted as open and is in no median, so a median of closed lifetimes reads short (the long-lived
postings are still open). A posting that reopened after its first close is counted with the first
close, and the reopen rate says how often that first close was premature.

Why the event log and not `postings.first_seen_at` / `closed_at`: a `postings` row carries the whole
body text, so one pass over the table costs minutes on the 50 GB live store (a primary-key join from
the events cost 69 s). `posting_events` rows are narrow and the table is 2.1M rows. Its company
comes from `ix_postings_corpus`, the one index that holds `company_id` next to the rowid, read as a
covering scan. About 1.1 s warm and 8.6 s with a cold OS cache, so the aggregate is also memoised in
process, keyed by the store, the latest finished run and the newest event id.

Time to apply (first seen -> earliest submitted application) reads only the applied jobs' postings
and is never cached: an application the owner records between runs must show at once.

Read-only. Dates in the store are naive UTC and offset-carrying; SQL differences go through
`julianday`, which reads both, and Python-side ones through `_naive`.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, func, select, text

from boardwatch.store.lead_aging_queries import _days, _naive, _summary
from boardwatch.store.tables import applications, companies, posting_events, postings, runs

COMPANY_MIN_CLOSED = 5
COMPANY_ROWS = 25
_CHUNK = 500

# `INDEXED BY` is the point: without it the planner joins by primary key and reads every posting
# row (the 69 s plan). The expression must name the index declared in `store/tables.py`.
_LIFETIMES = text(
    """
    WITH life AS (
      SELECT posting_id,
             MIN(CASE kind WHEN 'new' THEN created_at END) AS born,
             MIN(CASE kind WHEN 'closed' THEN created_at END) AS died,
             SUM(kind = 'reopened') AS reopens
      FROM posting_events
      WHERE kind IN ('new', 'closed', 'reopened')
      GROUP BY posting_id
    )
    SELECT p.company_id AS company_id,
           COUNT(*) AS postings,
           SUM(life.reopens) AS reopen_events,
           SUM(life.reopens > 0) AS reopened_postings,
           GROUP_CONCAT(julianday(life.died) - julianday(life.born)) AS days
    FROM (SELECT id, company_id FROM postings INDEXED BY ix_postings_corpus) AS p
    JOIN life ON life.posting_id = p.id
    WHERE life.born IS NOT NULL
    GROUP BY p.company_id
    """
)


@dataclass
class _Tally:
    lifetimes: list[float]
    open: int = 0
    reopen_events: int = 0
    reopened_postings: int = 0

    def merge(self, other: _Tally) -> None:
        self.lifetimes.extend(other.lifetimes)
        self.open += other.open
        self.reopen_events += other.reopen_events
        self.reopened_postings += other.reopened_postings


def _reopen(tally: _Tally) -> dict[str, Any]:
    closed = len(tally.lifetimes)
    return {
        "events": tally.reopen_events,
        "postings": tally.reopened_postings,
        # Reopened postings over postings that ever closed. None when nothing closed.
        "rate": round(tally.reopened_postings / closed, 4) if closed else None,
    }


def _events_view(conn: Connection) -> dict[str, Any]:
    tallies: dict[int, _Tally] = {}
    for row in conn.execute(_LIFETIMES):
        # GROUP_CONCAT skips NULL, so a posting that never closed adds a count and no lifetime.
        lifetimes = [max(0.0, float(v)) for v in row.days.split(",")] if row.days else []
        tallies[int(row.company_id)] = _Tally(
            lifetimes,
            int(row.postings) - len(lifetimes),
            int(row.reopen_events or 0),
            int(row.reopened_postings or 0),
        )

    names = {
        int(r.id): (str(r.name), str(r.provider))
        for r in conn.execute(select(companies.c.id, companies.c.name, companies.c.provider))
    }
    overall = _Tally([])
    by_provider: dict[str, _Tally] = defaultdict(lambda: _Tally([]))
    for company_id, tally in tallies.items():
        provider = names.get(company_id, ("", ""))[1]
        overall.merge(tally)
        by_provider[provider].merge(tally)

    ranked = sorted(
        (
            (company_id, tally)
            for company_id, tally in tallies.items()
            if len(tally.lifetimes) >= COMPANY_MIN_CLOSED
        ),
        key=lambda item: (-len(item[1].lifetimes), names.get(item[0], ("", ""))[0]),
    )[:COMPANY_ROWS]

    return {
        "closed": _summary(sorted(overall.lifetimes)),
        "open": overall.open,
        "reopen": _reopen(overall),
        "providers": sorted(
            (
                {
                    "provider": provider,
                    **_summary(sorted(t.lifetimes)),
                    "open": t.open,
                    "reopen_rate": _reopen(t)["rate"],
                }
                for provider, t in by_provider.items()
            ),
            key=lambda row: (-row["count"], row["provider"]),
        ),
        "companies": [
            {
                "company": names.get(company_id, ("", ""))[0],
                "provider": names.get(company_id, ("", ""))[1],
                **_summary(sorted(t.lifetimes)),
                "open": t.open,
            }
            for company_id, t in ranked
        ],
    }


_memo: tuple[tuple[str, int | None, int | None], dict[str, Any]] | None = None


def _memo_key(conn: Connection) -> tuple[str, int | None, int | None]:
    return (
        conn.engine.url.render_as_string(hide_password=True),
        conn.execute(select(func.max(runs.c.id)).where(runs.c.finished_at.is_not(None))).scalar(),
        conn.execute(select(func.max(posting_events.c.id))).scalar(),
    )


def _cached_events_view(conn: Connection) -> dict[str, Any]:
    global _memo
    key = _memo_key(conn)
    if _memo is None or _memo[0] != key:
        _memo = (key, _events_view(conn))
    return _memo[1]


def _applied_waits(conn: Connection) -> Iterator[tuple[str, float]]:
    """(provider, days from first seen to the earliest submitted application) per applied job."""
    submitted = {
        int(r.job_id): _naive(r.at)
        for r in conn.execute(
            select(applications.c.job_id, func.min(applications.c.submitted_at).label("at"))
            .where(applications.c.submitted_at.is_not(None))
            .group_by(applications.c.job_id)
        )
    }
    jobs = list(submitted)
    first: dict[int, tuple[datetime, str]] = {}
    for start in range(0, len(jobs), _CHUNK):
        for r in conn.execute(
            select(postings.c.job_id, postings.c.first_seen_at, companies.c.provider)
            .join(companies, postings.c.company_id == companies.c.id)
            .where(postings.c.job_id.in_(jobs[start : start + _CHUNK]))
        ):
            seen = _naive(r.first_seen_at)
            job = int(r.job_id)
            if job not in first or seen < first[job][0]:
                first[job] = (seen, str(r.provider))
    for job, (seen, provider) in first.items():
        # An application recorded before the first sighting (an import) waited no time at all.
        yield provider, max(0.0, _days(seen, submitted[job]))


def _urgent(lifetime: float | None, to_apply: float | None) -> bool | None:
    """True when postings close faster than we apply. None when either side is unmeasured."""
    return None if lifetime is None or to_apply is None else lifetime < to_apply


def posting_lifetime(conn: Connection) -> dict[str, Any]:
    base = _cached_events_view(conn)

    waits: list[float] = []
    waits_by_provider: dict[str, list[float]] = defaultdict(list)
    for provider, days in _applied_waits(conn):
        waits.append(days)
        waits_by_provider[provider].append(days)

    to_apply = _summary(sorted(waits))
    providers = []
    for row in base["providers"]:
        mine = _summary(sorted(waits_by_provider.get(row["provider"], [])))
        providers.append(
            {
                **row,
                "to_apply": mine,
                "urgent": _urgent(row["median_days"], mine["median_days"]),
            }
        )
    return {
        "closed": dict(base["closed"]),
        "open": base["open"],
        "reopen": dict(base["reopen"]),
        "to_apply": to_apply,
        "urgent": _urgent(base["closed"]["median_days"], to_apply["median_days"]),
        "providers": providers,
        "companies": [dict(row) for row in base["companies"]],
    }
