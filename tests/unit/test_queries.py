from pathlib import Path

import pytest
from sqlalchemy import Engine, insert, select

from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import finalize_run, get_validators, insert_run


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path)
    ensure_schema(eng)
    return eng


def test_insert_run_is_visible_immediately(engine: Engine) -> None:
    run_id = insert_run(engine)
    # A separate connection sees the row while the scan is still running —
    # this is what doctor surfaces instead of lock-holder metadata (§0.3).
    with engine.connect() as conn:
        row = conn.execute(select(tables.runs).where(tables.runs.c.id == run_id)).one()
    assert row.started_at is not None
    assert row.finished_at is None


def test_finalize_run_records_derived_counts(engine: Engine) -> None:
    run_id = insert_run(engine)
    finalize_run(
        engine, run_id,
        boards_attempted=3, boards_complete=2, postings_seen=40,
        new_count=5, closed_count=1, reopened_count=0, errors=["acme: HTTP 503"],
    )
    with engine.connect() as conn:
        row = conn.execute(select(tables.runs).where(tables.runs.c.id == run_id)).one()
    assert row.finished_at is not None
    assert row.boards_attempted == 3
    assert row.boards_complete == 2
    assert row.postings_seen == 40
    assert row.new_count == 5
    assert row.closed_count == 1
    assert row.errors_json == ["acme: HTTP 503"]


def test_get_validators_round_trip(engine: Engine) -> None:
    from datetime import datetime

    with engine.begin() as conn:
        conn.execute(
            insert(tables.http_cache).values(
                url="https://x.example/board", etag='W/"v1"', last_modified=None,
                fetched_at=datetime(2026, 1, 1), status=200,
            )
        )
    with engine.connect() as conn:
        validators = get_validators(conn, "https://x.example/board")
        assert validators is not None and validators.etag == 'W/"v1"'
        assert get_validators(conn, "https://other.example/") is None
