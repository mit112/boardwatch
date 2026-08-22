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
from boardwatch.core.posting_identity import IdentityInputs, compute_identities
from boardwatch.store.events import append_event
from boardwatch.store.identity_queries import write_identities
from boardwatch.store.sources import record_version_source
from boardwatch.store.tables import (
    board_scans,
    companies,
    http_cache,
    jobs,
    posting_versions,
    postings,
)

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
        result = _apply_listed(conn, snapshot.postings, company_id, run_id, snapshot.url)
        result.status = snapshot.status
        if snapshot.status in ("complete", "partial"):
            _reset_listed_but_unrefreshed(
                conn, snapshot.postings, snapshot.listed_ids, company_id
            )
        if snapshot.status == "complete":
            result.closed = _process_missing(
                conn, snapshot.postings, snapshot.listed_ids, company_id, run_id
            )
            _persist_validators(conn, snapshot)
        _scan_row(
            conn, run_id, company_id, started_at, snapshot.status,
            len(snapshot.postings), snapshot.error, snapshot=snapshot,
        )
        return result


def _apply_listed(
    conn: Connection, raw_postings: list[RawPosting], company_id: int, run_id: int, source_url: str
) -> ApplyResult:
    now = utcnow()
    result = ApplyResult(status="", listed=len(raw_postings))
    existing = {
        row.provider_posting_id: row
        for row in conn.execute(
            select(postings).where(postings.c.company_id == company_id)
        ).all()
    }
    # One query per board, for the `cross_host` identity component (P6 slice 2 §4).
    company_name = str(
        conn.execute(select(companies.c.name).where(companies.c.id == company_id)).scalar_one()
    )
    for raw in raw_postings:
        new_hash = content_hash(raw.body_text)
        row = existing.get(raw.provider_posting_id)
        if row is None:
            job_id = int(conn.execute(insert(jobs).values(created_at=now)).inserted_primary_key[0])  # type: ignore[index]
            inserted = conn.execute(
                insert(postings).values(
                    company_id=company_id,
                    job_id=job_id,
                    provider_posting_id=raw.provider_posting_id,
                    first_seen_at=now,
                    status="open",
                    consecutive_missing=0,
                    content_hash=new_hash,
                    body_text=raw.body_text,
                    **_mutable_fields(raw, now),
                )
            )
            posting_id = int(inserted.inserted_primary_key[0])  # type: ignore[index]
            vid = _insert_version(conn, posting_id, new_hash, raw.body_text, now, run_id, "new")
            record_version_source(
                conn, posting_version_id=vid, run_id=run_id, source_url=source_url,
                source_record_id=raw.provider_posting_id, observed_at=now, payload_hash=new_hash,
            )
            append_event(conn, posting_id, "new", run_id)
            _write_posting_identity(
                conn, raw, posting_id=posting_id, company_id=company_id,
                company_name=company_name, content_hash=new_hash, first_seen_at=now, now=now,
            )
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
            vid = _insert_version(conn, row.id, new_hash, raw.body_text, now, run_id, "revised")
            record_version_source(
                conn, posting_version_id=vid, run_id=run_id, source_url=source_url,
                source_record_id=raw.provider_posting_id, observed_at=now, payload_hash=new_hash,
            )
            append_event(conn, row.id, "revised", run_id)
            result.revised += 1
        conn.execute(update(postings).where(postings.c.id == row.id).values(**values))
        # AFTER the update, so the identity is computed from what was just persisted. The
        # observation may have moved title or locations without producing a revision (the D25
        # rule above refreshes them regardless of content_hash), which moves an identity key.
        _write_posting_identity(
            conn, raw, posting_id=int(row.id), company_id=company_id,
            company_name=company_name,
            content_hash=values.get("content_hash", row.content_hash),
            first_seen_at=row.first_seen_at, now=now,
        )
    return result


def _write_posting_identity(
    conn: Connection,
    raw: RawPosting,
    *,
    posting_id: int,
    company_id: int,
    company_name: str,
    content_hash: str,
    first_seen_at: datetime,
    now: datetime,
) -> None:
    """Keep this posting's stored identities current, inside the board's own transaction.

    P6 slice 2 §4, closing D-098: before this, `write_identities` had exactly one caller in
    `src/` — the manual `boardwatch identities backfill`. Nothing in the scan or pipeline path
    wrote identities, so **any** run that discovered one new posting left it uncovered,
    `identities_complete()` went False and duplicate suppression silently switched off
    corpus-wide.

    Written here rather than as a sweep in the pipeline, which is what D-098 had in mind when it
    priced this work at a second corpus-wide `body_text` load: every field `IdentityInputs`
    needs is already in hand at this point, so the cost is O(postings this board listed) and no
    body is loaded that was not already in memory.

    Deliberately NOT wrapped in a try/except. A failure fails the board's transaction, so the
    posting and its identity commit or vanish together — the D16 property this module is built
    on. A posting stored without its identity is exactly the state that disables suppression.
    """
    write_identities(
        conn,
        posting_id,
        compute_identities(
            IdentityInputs(
                posting_id=posting_id,
                company_id=company_id,
                company_name=company_name,
                provider_posting_id=raw.provider_posting_id,
                title=raw.title,
                # Mirrors identity_queries.load_identity_inputs' coercion: non-string elements
                # are dropped, not stringified, so a JSON `[null]` cannot become the truthy
                # location component `["none"]` and let two postings suppress on evidence
                # neither one has.
                locations=(
                    [x for x in raw.locations if isinstance(x, str)]
                    if isinstance(raw.locations, list)
                    else None
                ),
                content_hash=content_hash,
                body_text=raw.body_text,
                url=raw.url,
                first_seen_at=first_seen_at,
            )
        ),
        now=now,
    )


def _insert_version(
    conn: Connection, posting_id: int, content_hash: str, body_text: str,
    captured_at: datetime, run_id: int, capture_reason: str,
) -> int:
    """Append an immutable content version (D29). Called on new and body-revision only."""
    return int(
        conn.execute(
            insert(posting_versions).values(
                posting_id=posting_id, content_hash=content_hash, body_text=body_text,
                captured_at=captured_at, run_id=run_id, capture_reason=capture_reason,
            )
        ).inserted_primary_key[0]  # type: ignore[index]
    )


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


def _reset_listed_but_unrefreshed(
    conn: Connection,
    raw_postings: list[RawPosting],
    listed_ids: frozenset[str],
    company_id: int,
) -> None:
    """D23 for subset-detail providers, on BOTH complete and partial snapshots: a posting
    positively LISTED but not among the refreshed postings (SmartRecruiters known/skipped)
    is untouched by _apply_listed, so reset its miss counter here. No-op when listed_ids is
    empty — single-request providers already reset every listed posting via _apply_listed."""
    if not listed_ids:
        return
    applied = {raw.provider_posting_id for raw in raw_postings}
    to_reset = tuple(listed_ids - applied)
    if not to_reset:
        return
    conn.execute(
        update(postings)
        .where(
            postings.c.company_id == company_id,
            postings.c.status == "open",
            postings.c.provider_posting_id.in_(to_reset),
            postings.c.consecutive_missing != 0,
        )
        .values(consecutive_missing=0)
    )


def _process_missing(
    conn: Connection,
    raw_postings: list[RawPosting],
    listed_ids: frozenset[str],
    company_id: int,
    run_id: int,
) -> int:
    """Close postings absent from the board (complete snapshots only). `listed_ids` is the
    full live inventory when the provider fetched only a subset of details (SmartRecruiters
    skips known postings); it falls back to the applied postings for single-request providers
    that return the whole board. Listed-but-skipped rows already had their miss counter reset
    by _reset_listed_but_unrefreshed, so this loop only skips or closes."""
    applied = {raw.provider_posting_id for raw in raw_postings}
    effective = listed_ids or frozenset(applied)
    open_rows = conn.execute(
        select(
            postings.c.id, postings.c.provider_posting_id, postings.c.consecutive_missing
        ).where(postings.c.company_id == company_id, postings.c.status == "open")
    ).all()
    closed = 0
    now = utcnow()
    for row in open_rows:
        if row.provider_posting_id in effective:
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
    *,
    snapshot: BoardSnapshot | None = None,
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
            # NULL, not 0, when there is no snapshot: a failed board's coverage is undefined.
            board_reported_total=None if snapshot is None else snapshot.board_reported_total,
            board_enumerated=None if snapshot is None else snapshot.board_enumerated,
            detail_deferred=None if snapshot is None else snapshot.detail_deferred,
            board_total_censored=(
                None
                if snapshot is None or snapshot.board_total_censored is None
                else int(snapshot.board_total_censored)
            ),
        )
    )
