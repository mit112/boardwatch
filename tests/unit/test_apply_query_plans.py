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
from boardwatch.pipeline.death_probe import Listing, sweep_unwatched_deaths
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


def _captured(engine: Engine, verb: str = "SELECT") -> list[tuple[str, Any]]:
    seen: list[tuple[str, Any]] = []
    target = "UPDATE postings" if verb == "UPDATE" else "FROM postings"

    @event.listens_for(engine, "before_cursor_execute")
    def _grab(conn: Any, cursor: Any, statement: str, parameters: Any, *_: Any) -> None:
        if statement.lstrip().upper().startswith(verb) and target in statement:
            seen.append((statement, parameters))

    return seen


def _plans(engine: Engine, statements: list[tuple[str, Any]]) -> list[str]:
    with engine.connect() as conn:
        return [
            " ".join(str(row[3]) for row in conn.exec_driver_sql(f"EXPLAIN QUERY PLAN {sql}", params))
            for sql, params in statements
        ]


def _reads_by_company(plans: list[str]) -> None:
    """Every plan walks neither the status index nor the whole table: it constrains `company_id`.

    `not WALK in plan` alone is vacuous where the plan is a bare `SCAN postings`, which names no
    index. SQLite 3.42 to 3.46 (the 3.11.9 Python builds bundle 3.46.0) answered the old
    `likely()` hint that way for three of these statements while this file stayed green.
    """
    assert plans
    assert not [plan for plan in plans if WALK in plan], plans
    assert all("company_id=?" in plan for plan in plans), plans


def test_closing_missing_postings_reads_the_board_from_the_company_index(tmp_path: Path) -> None:
    engine, company_id, run_id = _store(tmp_path)
    seen = _captured(engine)
    listed = BoardSnapshot(status="complete", postings=[], url="https://x/acme",
                           listed_ids=frozenset({"acme-0"}))
    apply_board(engine, listed, company_id, run_id)
    missing = [(sql, p) for sql, p in seen if "consecutive_missing" in sql]
    assert missing, "the closure read was not captured, so nothing below was checked"
    _reads_by_company(_plans(engine, missing))


def test_the_empty_board_guard_counts_from_the_company_index(tmp_path: Path) -> None:
    engine, company_id, run_id = _store(tmp_path)
    seen = _captured(engine)
    empty = BoardSnapshot(status="complete", postings=[], url="https://x/acme")
    apply_board(engine, empty, company_id, run_id)
    counts = [(sql, p) for sql, p in seen if "count(" in sql.lower()]
    assert counts, "the guard's count was not captured, so nothing below was checked"
    _reads_by_company(_plans(engine, counts))


def test_resetting_listed_but_unrefreshed_postings_reads_the_board_from_the_company_index(
    tmp_path: Path,
) -> None:
    """Run 489 (2026-09-28): the SELECTs above were fixed, but this UPDATE — which only the
    providers whose lists carry no bodies reach (Workday, SmartRecruiters…) — kept the bare status term. From
    three listed-but-unrefreshed ids the planner walks every open posting: ~41 s per Workday
    board on an 18 GB store with ~5 GB of page cache, the same crawl as run 478."""
    engine, company_id, run_id = _store(tmp_path)
    seen = _captured(engine, "UPDATE")
    listed = BoardSnapshot(status="partial", postings=[], url="https://x/acme",
                           listed_ids=frozenset({"acme-0", "acme-1", "acme-2"}))
    apply_board(engine, listed, company_id, run_id)
    resets = [(sql, p) for sql, p in seen if "consecutive_missing" in sql]
    assert resets, "the reset was not captured, so nothing below was checked"
    _reads_by_company(_plans(engine, resets))


def test_the_death_probe_reads_a_listed_company_from_the_company_index(tmp_path: Path) -> None:
    """T260: `pipeline/death_probe.py` re-reads one company's open postings inside each listing
    transaction with the same `company_id = ? AND status = 'open'` shape T256 fixed in
    `apply_board`, and carries the same `open_as_filter()`. What this pins is that SOME plan
    constrains `company_id`, so a change that loses it falls back to walking every open posting
    per asked company. It failed on SQLite 3.46 (Python 3.11.9) while the `likely()` hint was in:
    the plan was `SCAN postings`, with the T256 tests above green."""
    engine, company_id, run_id = _store(tmp_path)
    with engine.begin() as conn:
        conn.execute(
            companies.update().where(companies.c.id == company_id)
            .values(provider="ashby", watched=False)
        )
    seen = _captured(engine)
    sweep_unwatched_deaths(
        engine,
        prober=lambda posting_id, url: None,  # type: ignore[arg-type,return-value]
        listing_prober=lambda cid, provider, slug: Listing(company_id=cid, ids=frozenset({"acme-0"})),
        run_id=run_id,
        budget=0,
        company_budget=10,
        ttl_hours=24,
    )
    # Keyed on the read's own columns, not on the status term's text: a filter on that term would
    # find nothing once it changes and fail on the capture instead of on the plan.
    reads = [
        (sql, p) for sql, p in seen
        if "provider_posting_id" in sql and "death_strikes" in sql and "postings.company_id" in sql
    ]
    assert reads, "the per-company re-read was not captured, so nothing below was checked"
    # Either index that seeks by company is fine; a plan that does not constrain company_id is the
    # walk this pins against.
    _reads_by_company(_plans(engine, reads))

