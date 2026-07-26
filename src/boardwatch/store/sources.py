"""Authoritative source lineage for posting versions (the freshness/trust spine).

One row per scan-captured posting_version: which board URL, provider record, run, and
payload hash produced it. FK-enforced (unlike a generic provenance table). Backfilled
(pre-migration) versions have no source row — their provenance was not tracked and is
not invented. Immutable. Functions take the caller's open Connection.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Connection, Row, insert, select

from boardwatch.store.tables import posting_version_sources


def record_version_source(
    conn: Connection,
    *,
    posting_version_id: int,
    run_id: int | None,
    source_url: str,
    source_record_id: str,
    observed_at: datetime,
    payload_hash: str | None,
) -> None:
    conn.execute(
        insert(posting_version_sources).values(
            posting_version_id=posting_version_id,
            run_id=run_id,
            source_url=source_url,
            source_record_id=source_record_id,
            observed_at=observed_at,
            payload_hash=payload_hash,
        )
    )


def get_version_source(conn: Connection, posting_version_id: int) -> Row[Any] | None:
    return conn.execute(
        select(posting_version_sources).where(
            posting_version_sources.c.posting_version_id == posting_version_id
        )
    ).one_or_none()
