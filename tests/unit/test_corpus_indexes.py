"""T291: the corpus-wide reads stay answered by their indexes, and the migration round-trips.

The plan is what is pinned, because the failure this guards is silent: a `body_is_empty` whose text
drifts from the index's expression, or a read given a new column, returns the same correct answer
through a table scan, and on the real store costs 100-200 s per statement with every test green.
"""

import sqlite3
from collections.abc import Callable
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine, event, func, insert, inspect, select, text

from boardwatch.core.clock import utcnow
from boardwatch.eligibility import read
from boardwatch.eligibility.read import _REVERSE_MAP_SCAN_ABOVE, _posting_by_version
from boardwatch.extract.preflight import _open_postings_missing_extraction
from boardwatch.pipeline.death_probe import unreachable_by_the_scanner
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import open_empty_body_posting_ids
from boardwatch.store.run_funnel_queries import (
    _colliding_open_posting_ids,
    count_stub_postings,
    count_stub_postings_by_company,
)
from boardwatch.store.tables import companies, jobs, posting_versions, postings

BASE = "p_board_scans_lane"
HEAD = "p_corpus_indexes"
MIGRATIONS = Path("src/boardwatch/store/migrations")


def _expression_read() -> str:
    """What this SQLite's EXPLAIN says about a read answered from an index EXPRESSION.

    SQLite 3.46.0 says "USING INDEX" and 3.53.1 says "USING COVERING INDEX" for the same read, and
    neither opens the row: over 831,691 open postings 3.46.0 took 1.0 s and 3.53.1 took 0.7 s, where
    reading the bodies takes 100-200 s. A drifted `body_is_empty` leaves the stub counts reading
    "USING INDEX ix_postings_corpus" too, so the strict text is demanded wherever SQLite can state
    it. Asked of SQLite itself because the version where the wording changed was not measured.
    """
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE t (a, b)")
    db.execute("CREATE INDEX i ON t (a, (b = ''))")
    plan = db.execute("EXPLAIN QUERY PLAN SELECT b = '' FROM t WHERE a = 1").fetchone()[3]
    db.close()
    return "COVERING INDEX ix_postings_corpus" if "COVERING" in plan else "INDEX ix_postings_corpus"


def count_open_postings_by_company(conn: Connection) -> object:
    """The shape behind the funnel's per-company denominators and the watched-board reads."""
    return conn.execute(
        select(postings.c.company_id, func.count())
        .where(postings.c.status == "open")
        .group_by(postings.c.company_id)
    ).all()


def _engine(tmp_path: Path) -> Engine:
    engine = get_engine(tmp_path)
    ensure_schema(engine)
    return engine


def _plans_of(engine: Engine, issue: Callable[[Connection], object]) -> list[str]:
    """The plan of each statement the REAL read issues, with the parameters it really binds.

    Through the production function, never a statement rebuilt here: a copy of the predicate once
    sat beside `body_is_empty`, so a test holding its own statement passed while the funnel's real
    read kept scanning every body. A parameter never matches an index's expression either, so
    these must be the bound statements and not literals rendered for the test.
    """
    issued: list[tuple[str, object]] = []

    def _record(_c, _cur, statement, parameters, _ctx, _many):  # type: ignore[no-untyped-def]
        if statement.startswith("SELECT"):  # the connection's BEGIN has no plan to read
            issued.append((statement, parameters))

    event.listen(engine, "before_cursor_execute", _record)
    with engine.connect() as conn:
        issue(conn)
    event.remove(engine, "before_cursor_execute", _record)
    with engine.connect() as conn:
        return [
            " | ".join(
                str(row[3])
                for row in conn.exec_driver_sql(f"EXPLAIN QUERY PLAN {statement}", parameters).all()
            )
            for statement, parameters in issued
        ]


def test_the_stub_counts_read_no_body(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    expected = _expression_read()
    for count in (count_stub_postings, count_stub_postings_by_company, open_empty_body_posting_ids):
        plans = _plans_of(engine, count)
        assert plans, count
        assert all(expected in plan for plan in plans), (count, plans)


def test_the_per_company_count_reads_no_row(tmp_path: Path) -> None:
    plans = _plans_of(_engine(tmp_path), count_open_postings_by_company)
    assert plans
    assert all("COVERING INDEX ix_postings_corpus" in plan for plan in plans), plans


def test_a_corpus_sized_reverse_version_map_scans_an_index_and_reads_no_row(tmp_path: Path) -> None:
    corpus = list(range(1, _REVERSE_MAP_SCAN_ABOVE + 2))
    plans = _plans_of(_engine(tmp_path), lambda conn: _posting_by_version(conn, corpus))
    assert plans
    assert all("COVERING INDEX ix_posting_versions_posting_captured" in plan for plan in plans), plans


def test_the_reverse_map_returns_only_the_ids_asked_for_on_both_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The scan reads every version, so its filter is what keeps it the same answer as the chunks."""
    engine = _engine(tmp_path)
    now = utcnow()
    with engine.begin() as conn:
        company_id = conn.execute(
            insert(companies).values(
                name="Acme", provider="ashby", slug="acme", source="user", watched=True
            )
        ).inserted_primary_key[0]
        for version_id, posting_id in ((1, 10), (2, 20), (3, 30)):
            job_id = conn.execute(insert(jobs).values(created_at=now)).inserted_primary_key[0]
            conn.execute(
                insert(postings).values(
                    id=posting_id, company_id=company_id, provider_posting_id=str(posting_id),
                    title="t", normalized_title="t", remote_policy="unknown", first_seen_at=now,
                    last_seen_at=now, status="open", consecutive_missing=0, content_hash="h",
                    body_text="b", job_id=job_id,
                )
            )
            conn.execute(
                insert(posting_versions).values(
                    id=version_id, posting_id=posting_id, content_hash="h", body_text="b",
                    captured_at=now, capture_reason="new",
                )
            )
    with engine.connect() as conn:
        chunked = _posting_by_version(conn, [1, 3])
        monkeypatch.setattr(read, "_REVERSE_MAP_SCAN_ABOVE", 0)
        scanned = _posting_by_version(conn, [1, 3])
    assert chunked == scanned == {1: 10, 3: 30}


def test_the_duplicate_sweep_reads_no_row(tmp_path: Path) -> None:
    plans = _plans_of(_engine(tmp_path), _colliding_open_posting_ids)
    assert plans
    for plan in plans:
        assert "COVERING INDEX ix_posting_identities_key" in plan, plan
        assert "COVERING INDEX ix_postings_id_status" in plan, plan
        assert "INTEGER PRIMARY KEY" not in plan, plan


def test_the_extraction_check_reads_no_row_or_body_until_one_is_due(tmp_path: Path) -> None:
    """Nothing is due on an empty store, so its only statement is the check itself."""
    engine = _engine(tmp_path)
    plans = _plans_of(
        engine, lambda _conn: _open_postings_missing_extraction(engine, "taxonomy-version")
    )
    assert plans
    assert all("COVERING INDEX ix_postings_corpus" in plan for plan in plans), plans


def test_the_death_sweep_seeks_unwatched_companies_instead_of_walking_open_postings(
    tmp_path: Path,
) -> None:
    engine = _engine(tmp_path)
    board = postings.join(companies, companies.c.id == postings.c.company_id)
    stmt = select(postings.c.id).select_from(board).where(unreachable_by_the_scanner())
    plans = _plans_of(engine, lambda conn: conn.execute(stmt).all())
    assert plans
    assert all("ix_postings_corpus (status=? AND company_id=?)" in plan for plan in plans), plans


def test_the_scan_preflight_load_reads_no_row(tmp_path: Path) -> None:
    """The statement `scan/coordinator.py` issues before dispatch, inlined there."""
    stmt = select(postings.c.company_id, postings.c.provider_posting_id).where(
        postings.c.company_id.in_([1, 2]), postings.c.status == "open"
    )
    plans = _plans_of(_engine(tmp_path), lambda conn: conn.execute(stmt).all())
    assert all("COVERING INDEX ix_postings_corpus" in plan for plan in plans), plans


def test_the_migration_round_trips_and_keeps_every_row(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, BASE)
    command.upgrade(cfg, HEAD)
    engine = create_engine(url)
    with engine.connect() as conn:
        names = {
            row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='index'"))
        }
    assert {"ix_postings_corpus", "ix_postings_id_status", "ix_posting_identities_key"} <= names
    columns = [
        index["column_names"]
        for index in inspect(engine).get_indexes("posting_identities")
        if index["name"] == "ix_posting_identities_key"
    ]
    assert columns == [["kind", "identity_key", "algorithm_version", "posting_id"]]
    command.downgrade(cfg, BASE)
    columns = [
        index["column_names"]
        for index in inspect(create_engine(url)).get_indexes("posting_identities")
        if index["name"] == "ix_posting_identities_key"
    ]
    assert columns == [["kind", "identity_key"]]


@pytest.mark.parametrize(
    "interrupted_after",
    [
        pytest.param(("ix_postings_corpus",), id="first index built"),
        pytest.param(("ix_postings_corpus", "ix_postings_id_status"), id="both postings indexes"),
        pytest.param(
            ("ix_postings_corpus", "ix_postings_id_status", "DROP"), id="old identity index dropped"
        ),
    ],
)
def test_a_migration_killed_part_way_finishes_on_retry(
    tmp_path: Path, interrupted_after: tuple[str, ...]
) -> None:
    """Each statement commits alone, so the state a killed run leaves is real, at the old revision."""
    url = f"sqlite:///{tmp_path / 'm.db'}"
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, BASE)
    statements = {
        "ix_postings_corpus": "CREATE INDEX ix_postings_corpus ON postings (status, company_id, "
        "provider_posting_id, (trim(body_text, char(32, 9, 10, 13, 12, 11)) = ''), content_hash)",
        "ix_postings_id_status": "CREATE INDEX ix_postings_id_status ON postings (id, status)",
        "DROP": "DROP INDEX ix_posting_identities_key",
    }
    engine = create_engine(url)
    with engine.begin() as conn:
        for step in interrupted_after:
            conn.execute(text(statements[step]))
    engine.dispose()
    command.upgrade(cfg, HEAD)
    columns = [
        index["column_names"]
        for index in inspect(create_engine(url)).get_indexes("posting_identities")
        if index["name"] == "ix_posting_identities_key"
    ]
    assert columns == [["kind", "identity_key", "algorithm_version", "posting_id"]]
