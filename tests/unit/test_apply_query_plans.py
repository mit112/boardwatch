"""The per-board apply must read one board's open postings from the COMPANY index.

Run 478 (2026-09-25): with no ANALYZE statistics SQLite answers `company_id = ? AND status = ?`
from `ix_postings_status_posted_at`, which walks every open posting in the store to find one
board's. Cached, that is invisible; on a 16 GB store under memory pressure it cost ~40 s per applied
board and the scan crawled at 141 boards in 88 minutes. These tests capture the SQL `apply_board`
actually sends and ask SQLite for each statement's plan — the production store has no statistics
either, so the fixture's plan is the production plan.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import Engine, event, insert

from boardwatch.core.clock import utcnow
from boardwatch.core.models import BoardSnapshot
from boardwatch.scan.apply import apply_board
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.tables import companies, jobs, postings, runs

WALK = "ix_postings_status_posted_at"


def _store(tmp_path: Path) -> tuple[Engine, int, int]:
    engine = get_engine(tmp_path)
    ensure_schema(engine)
    now = utcnow()
    with engine.begin() as conn:
        run_id = int(conn.execute(insert(runs).values(started_at=now, status="running"))
                     .inserted_primary_key[0])
        ids = []
        for slug in ("acme", "beta"):
            company_id = int(conn.execute(insert(companies).values(
                name=slug, provider="greenhouse", slug=slug, source="user", watched=True,
            )).inserted_primary_key[0])
            ids.append(company_id)
            for i in range(3):
                job_id = int(conn.execute(insert(jobs).values(created_at=now)).inserted_primary_key[0])
                conn.execute(insert(postings).values(
                    company_id=company_id, job_id=job_id, provider_posting_id=f"{slug}-{i}", title="Engineer",
                    normalized_title="engineer", locations_json=["Austin, TX"],
                    remote_policy="onsite", first_seen_at=now, last_seen_at=now, status="open",
                    consecutive_missing=0, content_hash=f"h-{slug}-{i}", body_text="JD",
                ))
    return engine, ids[0], run_id


def _captured(engine: Engine) -> list[tuple[str, Any]]:
    seen: list[tuple[str, Any]] = []

    @event.listens_for(engine, "before_cursor_execute")
    def _grab(conn: Any, cursor: Any, statement: str, parameters: Any, *_: Any) -> None:
        if statement.lstrip().upper().startswith("SELECT") and "FROM postings" in statement:
            seen.append((statement, parameters))

    return seen


def _plans(engine: Engine, statements: list[tuple[str, Any]]) -> list[str]:
    with engine.connect() as conn:
        return [
            " ".join(str(row[3]) for row in conn.exec_driver_sql(f"EXPLAIN QUERY PLAN {sql}", params))
            for sql, params in statements
        ]


def test_closing_missing_postings_reads_the_board_from_the_company_index(tmp_path: Path) -> None:
    engine, company_id, run_id = _store(tmp_path)
    seen = _captured(engine)
    listed = BoardSnapshot(status="complete", postings=[], url="https://x/acme",
                           listed_ids=frozenset({"acme-0"}))
    apply_board(engine, listed, company_id, run_id)
    missing = [(sql, p) for sql, p in seen if "consecutive_missing" in sql]
    assert missing, "the closure read was not captured, so nothing below was checked"
    assert not [plan for plan in _plans(engine, missing) if WALK in plan]


def test_the_empty_board_guard_counts_from_the_company_index(tmp_path: Path) -> None:
    engine, company_id, run_id = _store(tmp_path)
    seen = _captured(engine)
    empty = BoardSnapshot(status="complete", postings=[], url="https://x/acme")
    apply_board(engine, empty, company_id, run_id)
    counts = [(sql, p) for sql, p in seen if "count(" in sql.lower()]
    assert counts, "the guard's count was not captured, so nothing below was checked"
    assert not [plan for plan in _plans(engine, counts) if WALK in plan]
