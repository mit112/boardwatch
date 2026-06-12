"""Run bookkeeping and small read queries.

insert_run commits immediately at scan start so the running scan's started_at
is queryable while it runs (§0.3 — the scan lock carries no holder metadata).
Run counts are derived conveniences; posting_events is the source of truth (§4).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, Engine, Row, insert, select, update

from boardwatch.core.clock import utcnow
from boardwatch.core.models import ResponseValidators
from boardwatch.store.tables import companies, http_cache, runs


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
