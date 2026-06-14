"""Run bookkeeping and small read queries.

insert_run commits immediately at scan start so the running scan's started_at
is queryable while it runs (§0.3 — the scan lock carries no holder metadata).
Run counts are derived conveniences; posting_events is the source of truth (§4).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Connection, Engine, Row, func, insert, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from boardwatch.core.clock import utcnow
from boardwatch.core.models import ResponseValidators
from boardwatch.store.tables import board_scans, companies, http_cache, profile, runs


def insert_run(engine: Engine) -> int:
    with engine.begin() as conn:
        result = conn.execute(insert(runs).values(started_at=utcnow(), boards_attempted=0))
        return int(result.inserted_primary_key[0])  # type: ignore[index]


def finalize_run(
    engine: Engine,
    run_id: int,
    *,
    boards_attempted: int,
    boards_complete: int,
    postings_seen: int,
    new_count: int,
    closed_count: int,
    reopened_count: int,
    errors: list[str],
) -> None:
    with engine.begin() as conn:
        conn.execute(
            update(runs)
            .where(runs.c.id == run_id)
            .values(
                finished_at=utcnow(),
                boards_attempted=boards_attempted,
                boards_complete=boards_complete,
                postings_seen=postings_seen,
                new_count=new_count,
                closed_count=closed_count,
                reopened_count=reopened_count,
                errors_json=errors,
            )
        )


def get_validators(conn: Connection, url: str) -> ResponseValidators | None:
    row = conn.execute(
        select(http_cache.c.etag, http_cache.c.last_modified).where(http_cache.c.url == url)
    ).one_or_none()
    if row is None:
        return None
    return ResponseValidators(etag=row.etag, last_modified=row.last_modified)


def get_watched_companies(
    conn: Connection, *, slug: str | None = None, provider: str | None = None
) -> list[Row[Any]]:
    stmt = select(companies).where(companies.c.watched.is_(True))
    if slug is not None:
        stmt = stmt.where(companies.c.slug == slug)
    if provider is not None:
        stmt = stmt.where(companies.c.provider == provider)
    return list(conn.execute(stmt).all())


def upsert_watch(conn: Connection, *, provider: str, slug: str, name: str, source: str) -> None:
    stmt = sqlite_insert(companies).values(
        name=name, provider=provider, slug=slug, source=source, watched=True
    )
    conn.execute(
        stmt.on_conflict_do_update(
            index_elements=[companies.c.provider, companies.c.slug], set_={"watched": True}
        )
    )


# keep the P0 signature working — it is now a thin wrapper (no caller churn)
def upsert_watched_company(conn: Connection, *, provider: str, slug: str, name: str) -> None:
    upsert_watch(conn, provider=provider, slug=slug, name=name, source="user")


def unwatch(conn: Connection, *, provider: str, slug: str) -> int:
    result = conn.execute(
        update(companies)
        .where(companies.c.provider == provider, companies.c.slug == slug)
        .values(watched=False)
    )
    return int(result.rowcount)


def list_watches(conn: Connection) -> list[Row[Any]]:
    return list(
        conn.execute(
            select(
                companies.c.provider, companies.c.slug, companies.c.source,
                companies.c.watched, companies.c.last_health, companies.c.last_ok_at,
            ).where(companies.c.watched.is_(True)).order_by(companies.c.provider, companies.c.slug)
        ).all()
    )


def get_profile(conn: Connection) -> Row[Any] | None:
    return conn.execute(select(profile).where(profile.c.id == 1)).one_or_none()


def save_profile(
    conn: Connection,
    *,
    text: str,
    target_titles: list[str],
    exclude_titles: list[str],
    locations: list[str],
    remote_only: bool,
    skills: list[str],
    taxonomy_version: str,
) -> None:
    stmt = sqlite_insert(profile).values(
        id=1,
        text=text,
        skills_json=skills,
        taxonomy_version=taxonomy_version,
        target_titles_json=target_titles,
        exclude_titles_json=exclude_titles,
        locations_json=locations,
        remote_only=remote_only,
        updated_at=utcnow(),
    )
    conn.execute(
        stmt.on_conflict_do_update(
            index_elements=[profile.c.id],
            set_={
                "text": stmt.excluded.text,
                "skills_json": stmt.excluded.skills_json,
                "taxonomy_version": stmt.excluded.taxonomy_version,
                "target_titles_json": stmt.excluded.target_titles_json,
                "exclude_titles_json": stmt.excluded.exclude_titles_json,
                "locations_json": stmt.excluded.locations_json,
                "remote_only": stmt.excluded.remote_only,
                "updated_at": stmt.excluded.updated_at,
            },
        )
    )


def last_complete_scan_ages(conn: Connection) -> dict[int, datetime]:
    """company_id → finished_at of its most recent complete-or-unchanged board_scan."""
    stmt = (
        select(board_scans.c.company_id, func.max(board_scans.c.finished_at))
        .where(board_scans.c.status.in_(("complete", "unchanged")))
        .group_by(board_scans.c.company_id)
    )
    return {row[0]: row[1] for row in conn.execute(stmt).all()}
