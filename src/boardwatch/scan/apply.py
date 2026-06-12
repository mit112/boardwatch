"""Per-board transactional apply — the §3.5 status table, verbatim.

Exactly ONE transaction per BoardSnapshot (D16). A crash anywhere rolls the
whole board back: inventory, events, validators, and the scan row commit or
vanish together (state test h — the 304-trap regression).

Rules folded in:
- D23: every posting listed in a complete or partial snapshot has
  consecutive_missing reset to 0; increments happen only on complete.
- D25 persistence rule: every positive observation refreshes ALL
  provider-sourced mutable fields and raw_json regardless of content_hash;
  only a body-hash change emits `revised` (extraction is hash-keyed, so it
  stays current through metadata-only updates).
- D22: http_cache is upserted from observed_validators inside this same
  transaction, for `complete` snapshots only; `unchanged`/`partial`/`failed`
  never touch it. `unchanged` writes exactly one board_scans row (D15).
- Plan deviation 8: a closed posting reappearing with a changed body emits
  both `reopened` and `revised`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, Engine, insert, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from boardwatch.core.clock import utcnow
from boardwatch.core.models import BoardSnapshot, RawPosting
from boardwatch.core.normalize import content_hash, normalize_title
from boardwatch.store.events import append_event
from boardwatch.store.tables import board_scans, http_cache, postings

CLOSE_AFTER_MISSES = 2  # not configurable (plan Conventions)


@dataclass
class ApplyResult:
    status: str
    listed: int = 0
    new: int = 0
    revised: int = 0
    reopened: int = 0
    closed: int = 0


def apply_board(
    engine: Engine, snapshot: BoardSnapshot, company_id: int, run_id: int
) -> ApplyResult:
    started_at = utcnow()
    with engine.begin() as conn:
        if snapshot.status == "failed":
            _scan_row(conn, run_id, company_id, started_at, "failed", 0, snapshot.error)
            return ApplyResult(status="failed")
        if snapshot.status == "unchanged":
            _scan_row(conn, run_id, company_id, started_at, "unchanged", 0, None)
            return ApplyResult(status="unchanged")
        result = _apply_listed(conn, snapshot.postings, company_id, run_id)
        result.status = snapshot.status
        if snapshot.status == "complete":
            result.closed = _process_missing(conn, snapshot.postings, company_id, run_id)
            _persist_validators(conn, snapshot)
        _scan_row(
            conn, run_id, company_id, started_at, snapshot.status,
            len(snapshot.postings), snapshot.error,
        )
        return result


def _apply_listed(
    conn: Connection, raw_postings: list[RawPosting], company_id: int, run_id: int
) -> ApplyResult:
    now = utcnow()
    result = ApplyResult(status="", listed=len(raw_postings))
    existing = {
        row.provider_posting_id: row
        for row in conn.execute(
            select(postings).where(postings.c.company_id == company_id)
        ).all()
    }
    for raw in raw_postings:
        new_hash = content_hash(raw.body_text)
        row = existing.get(raw.provider_posting_id)
        if row is None:
            inserted = conn.execute(
                insert(postings).values(
                    company_id=company_id,
                    provider_posting_id=raw.provider_posting_id,
                    first_seen_at=now,
                    status="open",
                    consecutive_missing=0,
                    content_hash=new_hash,
                    body_text=raw.body_text,
                    **_mutable_fields(raw, now),
                )
            )
            append_event(conn, int(inserted.inserted_primary_key[0]), "new", run_id)  # type: ignore[index]
            result.new += 1
            continue
        values: dict[str, Any] = _mutable_fields(raw, now)  # D25: regardless of content_hash
        values["consecutive_missing"] = 0  # D23: reset on every positive observation
        if row.status == "closed":
            values["status"] = "open"
            values["closed_at"] = None
            append_event(conn, row.id, "reopened", run_id)
            result.reopened += 1
        if row.content_hash != new_hash:
            values["content_hash"] = new_hash
            values["body_text"] = raw.body_text
            append_event(conn, row.id, "revised", run_id)
            result.revised += 1
        conn.execute(update(postings).where(postings.c.id == row.id).values(**values))
    return result


def _mutable_fields(raw: RawPosting, now: datetime) -> dict[str, Any]:
    """All provider-sourced mutable fields + raw_json (the D25 persistence rule)."""
    return {
        "title": raw.title,
        "normalized_title": normalize_title(raw.title),
        "url": raw.url,
        "locations_json": raw.locations,
        "remote_policy": raw.remote_policy,
        "department": raw.department,
        "posted_at": raw.posted_at,
        "updated_at": raw.updated_at,
        "salary_min": raw.salary_min,
        "salary_max": raw.salary_max,
        "salary_currency": raw.salary_currency,
        "salary_period": raw.salary_period,
        "raw_json": raw.raw_json,
        "last_seen_at": now,
    }


def _process_missing(
    conn: Connection, raw_postings: list[RawPosting], company_id: int, run_id: int
) -> int:
    listed_ids = {raw.provider_posting_id for raw in raw_postings}
    open_rows = conn.execute(
        select(
            postings.c.id, postings.c.provider_posting_id, postings.c.consecutive_missing
        ).where(postings.c.company_id == company_id, postings.c.status == "open")
    ).all()
    closed = 0
    now = utcnow()
    for row in open_rows:
        if row.provider_posting_id in listed_ids:
            continue
        misses = row.consecutive_missing + 1
        if misses >= CLOSE_AFTER_MISSES:
            conn.execute(
                update(postings)
                .where(postings.c.id == row.id)
                .values(consecutive_missing=misses, status="closed", closed_at=now)
            )
            append_event(conn, row.id, "closed", run_id)
            closed += 1
        else:
            conn.execute(
                update(postings)
                .where(postings.c.id == row.id)
                .values(consecutive_missing=misses)
            )
    return closed


def _persist_validators(conn: Connection, snapshot: BoardSnapshot) -> None:
    """D22: complete snapshots only; same transaction as the applied inventory."""
    observed = snapshot.observed_validators
    if observed is None:
        return
    stmt = sqlite_insert(http_cache).values(
        url=snapshot.url,
        etag=observed.etag,
        last_modified=observed.last_modified,
        fetched_at=utcnow(),
        status=200,
    )
    conn.execute(
        stmt.on_conflict_do_update(
            index_elements=[http_cache.c.url],
            set_={
                "etag": stmt.excluded.etag,
                "last_modified": stmt.excluded.last_modified,
                "fetched_at": stmt.excluded.fetched_at,
                "status": stmt.excluded.status,
            },
        )
    )


def _scan_row(
    conn: Connection,
    run_id: int,
    company_id: int,
    started_at: datetime,
    status: str,
    listed: int,
    error: str | None,
) -> None:
    conn.execute(
        insert(board_scans).values(
            run_id=run_id,
            company_id=company_id,
            started_at=started_at,
            finished_at=utcnow(),
            status=status,
            postings_listed=listed,
            error=error,
        )
    )
