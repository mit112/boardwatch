"""Read-side joins for the application funnel (D31).

applications hang off the canonical `jobs` anchor, not off a posting, so a tracked
application survives its posting closing or being revised. Display context therefore
comes through an OUTER join and every display field is nullable. Kept separate from
queries.py, which is already the P0 catch-all.

A4: display context prefers the posting_version_id the application was made against
(application -> posting_versions -> postings -> companies), falling back to the job's
lowest posting id only when that link is NULL, so a tracked posting is never swapped
for a sibling on the same job.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Connection, func, select

from boardwatch.store.tables import applications, companies, posting_versions, postings


@dataclass(frozen=True)
class FunnelRow:
    application_id: int
    job_id: int
    posting_id: int | None
    title: str | None
    company: str | None
    status: str
    attempt_no: int
    updated_at: datetime
    submitted_at: datetime | None


def job_id_for_posting(conn: Connection, posting_id: int) -> int | None:
    return conn.execute(
        select(postings.c.job_id).where(postings.c.id == posting_id)
    ).scalar_one_or_none()


def list_funnel(conn: Connection, *, status: str | None = None) -> list[FunnelRow]:
    """The funnel, most recently touched first.

    The tracked posting is the one the application's posting_version_id points at. When
    that link is NULL (an application created before the version link existed), the job's
    lowest posting id is used for stability, so repeated runs render identically.
    """
    fallback = (
        select(
            postings.c.job_id.label("job_id"),
            func.min(postings.c.id).label("posting_id"),
        )
        .group_by(postings.c.job_id)
        .subquery()
    )
    fb_postings = postings.alias("fb_postings")
    fb_companies = companies.alias("fb_companies")
    stmt = (
        select(
            applications.c.id.label("application_id"),
            applications.c.job_id,
            applications.c.status,
            applications.c.attempt_no,
            applications.c.updated_at,
            applications.c.submitted_at,
            func.coalesce(postings.c.id, fb_postings.c.id).label("posting_id"),
            func.coalesce(postings.c.title, fb_postings.c.title).label("title"),
            func.coalesce(companies.c.name, fb_companies.c.name).label("company_name"),
        )
        .outerjoin(posting_versions, posting_versions.c.id == applications.c.posting_version_id)
        .outerjoin(postings, postings.c.id == posting_versions.c.posting_id)
        .outerjoin(companies, companies.c.id == postings.c.company_id)
        .outerjoin(fallback, fallback.c.job_id == applications.c.job_id)
        .outerjoin(fb_postings, fb_postings.c.id == fallback.c.posting_id)
        .outerjoin(fb_companies, fb_companies.c.id == fb_postings.c.company_id)
        .order_by(applications.c.updated_at.desc(), applications.c.id.desc())
    )
    if status is not None:
        stmt = stmt.where(applications.c.status == status)
    return [
        FunnelRow(
            application_id=int(row.application_id),
            job_id=int(row.job_id),
            posting_id=int(row.posting_id) if row.posting_id is not None else None,
            title=row.title,
            company=row.company_name,
            status=row.status,
            attempt_no=int(row.attempt_no),
            updated_at=row.updated_at,
            submitted_at=row.submitted_at,
        )
        for row in conn.execute(stmt).all()
    ]
