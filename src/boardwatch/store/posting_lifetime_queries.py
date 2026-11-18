"""Posting lifetime against time to apply (T307): how long postings stay open vs how fast we apply.

Lifetime is `new` -> first `closed` in `posting_events`. A posting that NEVER closed is censored: it
is counted as `never_closed` and is in no median, so a median of closed lifetimes reads short (the
long-lived postings are still open). A posting that closed, reopened and closed again is counted
once, at its first close; one that reopened and is open now is in the closed cohort too, so
`never_closed` is not "currently open". The reopen rate says how often a first close was premature.

Why the event log and not `postings.first_seen_at` / `closed_at`: a `postings` row carries the whole
body text, so one pass over the table costs minutes on the 50 GB live store (a primary-key join from
the events cost 69 s). `posting_events` rows are narrow and the table is 2.1M rows. Its company
comes from `ix_postings_corpus`, the one index that holds `company_id` next to the rowid, read as a
covering scan. About 1.2 s warm and 8.6 s with a cold OS cache, so the id-keyed aggregate is also
memoised in process. Its key is the store file (path and inode), the latest finished run, the newest
event id and the companies' providers. Company NAMES are never memoised: they are read fresh for
the rows shown, so a rename shows at once.

Time to apply (first seen -> earliest submitted application) reads only the applied jobs' postings
and is never cached: an application the owner records between runs must show at once. An
application that `track import` created is stamped with the IMPORT time, not the application date
(`store/jobapps_history.py`), so it is left out and counted in `excluded_imports`.

Read-only. Dates in the store are naive UTC and offset-carrying, and SQLite compares them as text,
so no SQL takes a MIN of a raw timestamp. SQL differences go through `julianday` (which reads both
as UTC) before MIN; Python-side ones through `_naive`.
"""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, Engine, exists, func, select, text

from boardwatch.store.lead_aging_queries import _days, _naive, _summary
from boardwatch.store.tables import (
    application_events,
    applications,
    companies,
    posting_events,
    postings,
    runs,
)

COMPANY_MIN_CLOSED = 5
COMPANY_ROWS = 25
_CHUNK = 500

# `import_history`'s `source` (its only caller, `track import`, passes "import"). The created event
# of such an application has `occurred_at` equal to `recorded_at` when the file gave no date; a row
# with a real applied date has the two days apart and is kept.
_IMPORT_SOURCE = "import"
_IMPORT_STAMP_SECONDS = 60

# `INDEXED BY` is the point: without it the planner joins by primary key and reads every posting
# row (the 69 s plan). The expression must name the index declared in `store/tables.py`.
_LIFETIMES = text(
    """
    WITH life AS (
      SELECT posting_id,
             MIN(CASE kind WHEN 'new' THEN julianday(created_at) END) AS born,
             MIN(CASE kind WHEN 'closed' THEN julianday(created_at) END) AS died,
             SUM(kind = 'reopened') AS reopens
      FROM posting_events
      WHERE kind IN ('new', 'closed', 'reopened')
      GROUP BY posting_id
    )
    SELECT p.company_id AS company_id,
           COUNT(*) AS postings,
           SUM(life.reopens) AS reopen_events,
           SUM(life.reopens > 0) AS reopened_postings,
           GROUP_CONCAT(life.died - life.born) AS days
    FROM (SELECT id, company_id FROM postings INDEXED BY ix_postings_corpus) AS p
    JOIN life ON life.posting_id = p.id
    WHERE life.born IS NOT NULL
    GROUP BY p.company_id
    """
)


@dataclass
class _Tally:
    lifetimes: list[float]
    never_closed: int = 0
    reopen_events: int = 0
    reopened_postings: int = 0

    def merge(self, other: _Tally) -> None:
        self.lifetimes.extend(other.lifetimes)
        self.never_closed += other.never_closed
        self.reopen_events += other.reopen_events
        self.reopened_postings += other.reopened_postings


@dataclass(frozen=True)
class _Aggregate:
    """Everything keyed by id or provider; nothing here is a company name."""

    closed: dict[str, Any]
    never_closed: int
    reopen: dict[str, Any]
    providers: tuple[dict[str, Any], ...]
    companies: tuple[tuple[int, dict[str, Any]], ...]


def _reopen(tally: _Tally) -> dict[str, Any]:
    closed = len(tally.lifetimes)
    return {
        "events": tally.reopen_events,
        "postings": tally.reopened_postings,
        # Reopened postings over postings that ever closed. None when nothing closed.
        "rate": round(tally.reopened_postings / closed, 4) if closed else None,
    }


def _aggregate(conn: Connection, provider_of: dict[int, str]) -> _Aggregate:
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

    overall = _Tally([])
    by_provider: dict[str, _Tally] = defaultdict(lambda: _Tally([]))
    for company_id, tally in tallies.items():
        overall.merge(tally)
        by_provider[provider_of.get(company_id, "")].merge(tally)

    # Ties go by id: a name is display text, and a rename must not reorder a memoised ranking.
    ranked = sorted(
        (
            (company_id, tally)
            for company_id, tally in tallies.items()
            if len(tally.lifetimes) >= COMPANY_MIN_CLOSED
        ),
        key=lambda item: (-len(item[1].lifetimes), item[0]),
    )[:COMPANY_ROWS]

    return _Aggregate(
        closed=_summary(sorted(overall.lifetimes)),
        never_closed=overall.never_closed,
        reopen=_reopen(overall),
        providers=tuple(
            sorted(
                (
                    {
                        "provider": provider,
                        **_summary(sorted(t.lifetimes)),
                        "never_closed": t.never_closed,
                        "reopen_rate": _reopen(t)["rate"],
                    }
                    for provider, t in by_provider.items()
                ),
                key=lambda row: (-row["count"], row["provider"]),
            )
        ),
        companies=tuple(
            (company_id, {**_summary(sorted(t.lifetimes)), "never_closed": t.never_closed})
            for company_id, t in ranked
        ),
    )


_Key = tuple[str, int | None, int | None, int | None, int]
_memo: tuple[_Key, _Aggregate] | None = None


def _store_file(engine: Engine) -> str | None:
    path = engine.url.database
    if not path or path == ":memory:":
        return None
    return path.removeprefix("file:")


def _inode(engine: Engine) -> int | None:
    """The store file's inode: a path alone cannot tell a replaced file from the one it replaced."""
    path = _store_file(engine)
    if path is None:
        return None
    try:
        return os.stat(path).st_ino
    except OSError:
        return None


def _memo_key(conn: Connection, provider_of: dict[int, str]) -> _Key:
    return (
        conn.engine.url.render_as_string(hide_password=True),
        _inode(conn.engine),
        conn.execute(select(func.max(runs.c.id)).where(runs.c.finished_at.is_not(None))).scalar(),
        conn.execute(select(func.max(posting_events.c.id))).scalar(),
        hash(tuple(sorted(provider_of.items()))),
    )


def _cached_aggregate(conn: Connection, provider_of: dict[int, str]) -> _Aggregate:
    global _memo
    key = _memo_key(conn, provider_of)
    held = _memo  # one read: the key and the payload tested and returned are the same tuple
    if held is not None and held[0] == key:
        return held[1]
    value = _aggregate(conn, provider_of)
    _memo = (key, value)
    return value


def _applied_waits(conn: Connection) -> tuple[list[tuple[str, float]], int]:
    """(provider, days from first seen to the earliest submission) per applied job, and the number
    of applied jobs left out because every submission is an import-time stamp."""
    imported = exists().where(
        application_events.c.application_id == applications.c.id,
        application_events.c.event_type == "created",
        application_events.c.source == _IMPORT_SOURCE,
        func.abs(
            func.julianday(application_events.c.occurred_at)
            - func.julianday(application_events.c.recorded_at)
        )
        * 86_400
        < _IMPORT_STAMP_SECONDS,
    )
    submitted: dict[int, datetime] = {}
    seen_jobs: set[int] = set()
    for r in conn.execute(
        select(applications.c.job_id, applications.c.submitted_at, imported.label("imported"))
        .where(applications.c.submitted_at.is_not(None))
    ):
        job = int(r.job_id)
        seen_jobs.add(job)
        if r.imported:
            continue
        stamp = _naive(r.submitted_at)
        if job not in submitted or stamp < submitted[job]:
            submitted[job] = stamp
    excluded = len(seen_jobs - submitted.keys())

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
    # An application recorded before the first sighting waited no time at all.
    waits = [
        (provider, max(0.0, _days(seen, submitted[job]))) for job, (seen, provider) in first.items()
    ]
    return waits, excluded


def _urgent(lifetime: float | None, to_apply: float | None) -> bool | None:
    """True when postings close faster than we apply. None when either side is unmeasured."""
    return None if lifetime is None or to_apply is None else lifetime < to_apply


def posting_lifetime(conn: Connection) -> dict[str, Any]:
    provider_of = {
        int(r.id): str(r.provider)
        for r in conn.execute(select(companies.c.id, companies.c.provider))
    }
    base = _cached_aggregate(conn, provider_of)

    names = {
        int(r.id): str(r.name)
        for r in conn.execute(
            select(companies.c.id, companies.c.name).where(
                companies.c.id.in_([company_id for company_id, _ in base.companies])
            )
        )
    }

    all_waits, excluded = _applied_waits(conn)
    waits_by_provider: dict[str, list[float]] = defaultdict(list)
    for provider, days in all_waits:
        waits_by_provider[provider].append(days)
    to_apply = _summary(sorted(days for _, days in all_waits))

    providers = []
    for row in base.providers:
        mine = _summary(sorted(waits_by_provider.get(row["provider"], [])))
        providers.append(
            {**row, "to_apply": mine, "urgent": _urgent(row["median_days"], mine["median_days"])}
        )
    return {
        "closed": dict(base.closed),
        "never_closed": base.never_closed,
        "reopen": dict(base.reopen),
        "to_apply": {**to_apply, "excluded_imports": excluded},
        "urgent": _urgent(base.closed["median_days"], to_apply["median_days"]),
        "providers": providers,
        "companies": [
            {
                "company": names.get(company_id, ""),
                "provider": provider_of.get(company_id, ""),
                **row,
            }
            for company_id, row in base.companies
        ],
    }
