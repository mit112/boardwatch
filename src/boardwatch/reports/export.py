"""Flat row projection for data portability (A6).

One row per open-or-tracked posting, with the funnel status and the eligibility
verdict joined on. Flat rather than nested because csv is a first-class format here and
a nested audit would only survive the jsonl path. Evidence quotes are deliberately not
exported: they are large, they are reachable through `boardwatch show`, and what this
snapshot carries is the evaluation identity (profile_hash, rules_hash, verdict) the row
was computed under, so a verdict can be matched to the profile and rules that produced
it. This is a flat snapshot, not full audit portability: it does not claim to be
recomputed or independently checkable after the fact.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Iterator
from datetime import datetime
from typing import IO, Any

from sqlalchemy import Connection, select

from boardwatch.store.funnel_queries import list_funnel
from boardwatch.store.tables import applications, companies, postings

CSV_COLUMNS: tuple[str, ...] = (
    "posting_id",
    "job_id",
    "company",
    "provider",
    "title",
    "url",
    "status",
    "remote_policy",
    "first_seen_at",
    "last_seen_at",
    "closed_at",
    "eligibility_verdict",
    "profile_hash",
    "rules_hash",
    "application_id",
    "application_status",
    "application_attempt",
    "submitted_at",
)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat(timespec="seconds") if value is not None else None


def export_rows(
    conn: Connection,
    *,
    verdicts: dict[int, str | None],
    profile_hash: str | None,
    rules_hash: str | None,
) -> Iterator[dict[str, Any]]:
    """Yield one flat row per open posting or tracked posting (A6.1).

    A tracked posting stays in the export after it closes: the predicate is open postings
    plus every job with an application, so the funnel never silently drops a row the user
    is still acting on. The funnel is job-level, so a posting shares its job's application
    fields; when a job has several attempts the highest attempt_no wins the display slot
    and the earlier attempts stay in the ledger.
    """
    funnel_by_job: dict[int, Any] = {}
    for funnel in list_funnel(conn):
        # Highest attempt wins the display slot; earlier attempts stay in the ledger.
        current = funnel_by_job.get(funnel.job_id)
        if current is None or funnel.attempt_no > current.attempt_no:
            funnel_by_job[funnel.job_id] = funnel
    tracked_jobs = select(applications.c.job_id)
    stmt = (
        select(
            postings.c.id,
            postings.c.job_id,
            postings.c.title,
            postings.c.url,
            postings.c.status,
            postings.c.remote_policy,
            postings.c.first_seen_at,
            postings.c.last_seen_at,
            postings.c.closed_at,
            companies.c.name.label("company_name"),
            companies.c.provider,
        )
        .join(companies, postings.c.company_id == companies.c.id)
        .where(
            (postings.c.status == "open")
            | (postings.c.job_id.in_(tracked_jobs))
        )
        .order_by(postings.c.id)
    )
    for row in conn.execute(stmt):
        job_id = int(row.job_id)
        tracked = funnel_by_job.get(job_id)
        yield {
            "posting_id": int(row.id),
            "job_id": job_id,
            "company": row.company_name,
            "provider": row.provider,
            "title": row.title,
            "url": row.url,
            "status": row.status,
            "remote_policy": row.remote_policy,
            "first_seen_at": _iso(row.first_seen_at),
            "last_seen_at": _iso(row.last_seen_at),
            "closed_at": _iso(row.closed_at),
            "eligibility_verdict": verdicts.get(int(row.id)),
            "profile_hash": profile_hash,
            "rules_hash": rules_hash,
            "application_id": tracked.application_id if tracked else None,
            "application_status": tracked.status if tracked else None,
            "application_attempt": tracked.attempt_no if tracked else None,
            "submitted_at": _iso(tracked.submitted_at) if tracked else None,
        }


def write_jsonl(rows: Iterable[dict[str, Any]], stream: IO[str]) -> int:
    count = 0
    for row in rows:
        stream.write(json.dumps(row, sort_keys=True) + "\n")
        count += 1
    return count


def write_csv(rows: Iterable[dict[str, Any]], stream: IO[str]) -> int:
    writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    count = 0
    for row in rows:
        writer.writerow({key: row[key] for key in CSV_COLUMNS})
        count += 1
    return count
