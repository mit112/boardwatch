"""Skip state on the generic `app_state` KV table.

Skip has no home in `applications`: that table's status catalog is closed by a CHECK
constraint (adding a member means a full SQLite table rebuild), and an `applications` row
asserts "I engaged with this employer", which is the opposite of what skipping a lead says.
So a skip is one `app_state` row keyed `queue.skipped.<job_id>`.

Two properties are load-bearing and both are asserted against the SQL actually issued:
`skipped_job_ids` reads every skip in ONE statement (there will be hundreds), and it never
consults `applications` — skip and applied are independent dimensions, and a job may be
both.
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Connection, Engine, event, func, insert, select, text

from boardwatch.core.clock import utcnow
from boardwatch.store.app_state import set_digest_cursor, set_notify_cursor, set_state
from boardwatch.store.applications import create_application, get_application
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queue_state import (
    REPORT_KEY_PREFIX,
    SKIP_KEY_PREFIX,
    mark_job_reported,
    mark_job_skipped,
    reported_job_ids,
    skipped_job_ids,
    unmark_job_reported,
    unmark_job_skipped,
)
from boardwatch.store.tables import app_state, jobs

# Naive UTC, matching boardwatch.core.clock.utcnow() (A2).
NOW = utcnow()


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path)
    ensure_schema(eng)
    return eng


def _job(conn: Connection) -> int:
    return int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])


def _assert_fks_clean(engine: Engine) -> None:
    """FKs are OFF inside alembic, so a green migration does not prove the rows are sound."""
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_key_check")).all() == []


def _read_with_sql_log(engine: Engine) -> tuple[dict[int, str], list[str]]:
    statements: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def _record(
        conn: Any, cursor: Any, statement: str, params: Any, context: Any, executemany: bool
    ) -> None:
        statements.append(statement)

    try:
        with engine.connect() as conn:
            skipped = skipped_job_ids(conn)
    finally:
        event.remove(engine, "before_cursor_execute", _record)
    # PRAGMAs fire on connect, before any statement this function is measuring.
    return skipped, [s for s in statements if s.lstrip().upper().startswith("SELECT")]


def test_a_skip_round_trips_with_its_timestamp(engine: Engine) -> None:
    at = datetime(2026, 8, 26, 14, 30, 5)
    with engine.begin() as conn:
        job_id = _job(conn)
        mark_job_skipped(conn, job_id=job_id, at=at)
    with engine.connect() as conn:
        assert skipped_job_ids(conn) == {job_id: at.isoformat()}
        stored = conn.execute(
            select(app_state.c.key).where(app_state.c.key == f"{SKIP_KEY_PREFIX}{job_id}")
        ).scalar_one()
    assert stored == f"queue.skipped.{job_id}"
    _assert_fks_clean(engine)


def test_nothing_is_skipped_on_a_fresh_store(engine: Engine) -> None:
    with engine.connect() as conn:
        assert skipped_job_ids(conn) == {}


def test_unrelated_app_state_rows_are_ignored(engine: Engine) -> None:
    """The real store already holds the digest and notify cursors.

    `queue.revealed42` is the adversarial one: it is exactly as long as the skip prefix plus
    digits, so a read that slices off `len(SKIP_KEY_PREFIX)` characters without first scoping
    the query to the prefix reports job 42 as skipped.
    """
    with engine.begin() as conn:
        job_id = _job(conn)
        set_digest_cursor(conn, 4321)
        set_notify_cursor(conn, 4320)
        set_state(conn, "queue.revealed.7", NOW.isoformat())   # a neighbouring, non-skip namespace
        assert len("queue.revealed") == len(SKIP_KEY_PREFIX)
        set_state(conn, "queue.revealed42", NOW.isoformat())
        mark_job_skipped(conn, job_id=job_id, at=NOW)
    with engine.connect() as conn:
        assert skipped_job_ids(conn) == {job_id: NOW.isoformat()}
        assert conn.execute(select(func.count()).select_from(app_state)).scalar_one() == 5
    _assert_fks_clean(engine)


@pytest.mark.parametrize(
    "bad_key",
    [
        "queue.skipped.",            # no job id at all
        "queue.skipped.abc",         # not an integer
        "queue.skipped.12x",         # partly an integer
        "queue.skipped.7.1",         # a dotted suffix
        "queue.skipped.-3",          # negative: no job has this id
        "queue.skipped. 5",          # padded
        "queue.skipped.\u00b2",        # superscript two: str.isdigit() says yes, int() raises
    ],
)
def test_a_malformed_skip_key_is_ignored_not_fatal(engine: Engine, bad_key: str) -> None:
    with engine.begin() as conn:
        job_id = _job(conn)
        set_state(conn, bad_key, NOW.isoformat())
        mark_job_skipped(conn, job_id=job_id, at=NOW)
    with engine.connect() as conn:
        assert skipped_job_ids(conn) == {job_id: NOW.isoformat()}


def test_skipping_twice_is_idempotent(engine: Engine) -> None:
    """A text primary key: a second write must update the row, not raise."""
    later = NOW + timedelta(hours=2)
    with engine.begin() as conn:
        job_id = _job(conn)
        mark_job_skipped(conn, job_id=job_id, at=NOW)
        mark_job_skipped(conn, job_id=job_id, at=later)
    with engine.connect() as conn:
        assert skipped_job_ids(conn) == {job_id: later.isoformat()}
        assert conn.execute(select(func.count()).select_from(app_state)).scalar_one() == 1
    _assert_fks_clean(engine)


def test_unskip_removes_only_that_job(engine: Engine) -> None:
    with engine.begin() as conn:
        kept = _job(conn)
        dropped = _job(conn)
        mark_job_skipped(conn, job_id=kept, at=NOW)
        mark_job_skipped(conn, job_id=dropped, at=NOW)
        set_digest_cursor(conn, 99)
    with engine.begin() as conn:
        unmark_job_skipped(conn, job_id=dropped)
    with engine.connect() as conn:
        assert skipped_job_ids(conn) == {kept: NOW.isoformat()}
        assert conn.execute(select(func.count()).select_from(app_state)).scalar_one() == 2
    _assert_fks_clean(engine)


def test_unskipping_a_job_that_was_never_skipped_is_a_noop(engine: Engine) -> None:
    with engine.begin() as conn:
        job_id = _job(conn)
        mark_job_skipped(conn, job_id=job_id, at=NOW)
    with engine.begin() as conn:
        unmark_job_skipped(conn, job_id=job_id + 12345)
    with engine.connect() as conn:
        assert skipped_job_ids(conn) == {job_id: NOW.isoformat()}


def test_every_skip_is_read_in_one_statement(engine: Engine) -> None:
    """Hundreds of skips must not become hundreds of round trips."""
    with engine.begin() as conn:
        job_ids = [_job(conn) for _ in range(120)]
        for job_id in job_ids:
            mark_job_skipped(conn, job_id=job_id, at=NOW)
    skipped, selects = _read_with_sql_log(engine)
    assert sorted(skipped) == sorted(job_ids)
    assert len(selects) == 1


def test_skipped_job_ids_never_consults_applications(engine: Engine) -> None:
    """Skip and applied are independent: a job can be both, and neither read sees the other."""
    with engine.begin() as conn:
        job_id = _job(conn)
        create_application(conn, job_id=job_id, status="applied", source="user")
        mark_job_skipped(conn, job_id=job_id, at=NOW)
    skipped, selects = _read_with_sql_log(engine)
    assert skipped == {job_id: NOW.isoformat()}
    assert len(selects) == 1
    assert "applications" not in selects[0].lower()
    _assert_fks_clean(engine)


def test_an_applied_job_can_be_unskipped_without_touching_its_application(engine: Engine) -> None:
    with engine.begin() as conn:
        job_id = _job(conn)
        app_id = create_application(conn, job_id=job_id, status="applied", source="user")
        mark_job_skipped(conn, job_id=job_id, at=NOW)
    with engine.begin() as conn:
        unmark_job_skipped(conn, job_id=job_id)
    with engine.connect() as conn:
        assert skipped_job_ids(conn) == {}
        app = get_application(conn, app_id)
    assert app is not None
    assert app.status == "applied"
    _assert_fks_clean(engine)


# ---------------------------------------------------------------------------------------- report


def test_a_report_round_trips_with_its_timestamp(engine: Engine) -> None:
    at = datetime(2026, 9, 2, 17, 30, 5)
    with engine.begin() as conn:
        job_id = _job(conn)
        mark_job_reported(conn, job_id=job_id, at=at)
    with engine.connect() as conn:
        assert reported_job_ids(conn) == {job_id: at.isoformat()}
        stored = conn.execute(
            select(app_state.c.key).where(app_state.c.key == f"{REPORT_KEY_PREFIX}{job_id}")
        ).scalar_one()
    assert stored == f"queue.reported.{job_id}"
    _assert_fks_clean(engine)


def test_nothing_is_reported_on_a_fresh_store(engine: Engine) -> None:
    with engine.connect() as conn:
        assert reported_job_ids(conn) == {}


def test_reporting_twice_is_idempotent(engine: Engine) -> None:
    later = NOW + timedelta(hours=2)
    with engine.begin() as conn:
        job_id = _job(conn)
        mark_job_reported(conn, job_id=job_id, at=NOW)
        mark_job_reported(conn, job_id=job_id, at=later)
    with engine.connect() as conn:
        assert reported_job_ids(conn) == {job_id: later.isoformat()}
        assert conn.execute(select(func.count()).select_from(app_state)).scalar_one() == 1
    _assert_fks_clean(engine)


def test_unreport_removes_only_that_job(engine: Engine) -> None:
    with engine.begin() as conn:
        kept = _job(conn)
        dropped = _job(conn)
        mark_job_reported(conn, job_id=kept, at=NOW)
        mark_job_reported(conn, job_id=dropped, at=NOW)
    with engine.begin() as conn:
        unmark_job_reported(conn, job_id=dropped)
    with engine.connect() as conn:
        assert reported_job_ids(conn) == {kept: NOW.isoformat()}
    _assert_fks_clean(engine)


def test_report_and_skip_are_independent_dimensions(engine: Engine) -> None:
    """The same job can be both, on separate keys, and un-marking one leaves the other. This is
    the property that makes a report a distinct signal from a skip rather than a second name for
    it."""
    with engine.begin() as conn:
        job_id = _job(conn)
        mark_job_skipped(conn, job_id=job_id, at=NOW)
        mark_job_reported(conn, job_id=job_id, at=NOW)
    with engine.connect() as conn:
        assert skipped_job_ids(conn) == {job_id: NOW.isoformat()}
        assert reported_job_ids(conn) == {job_id: NOW.isoformat()}
        assert conn.execute(select(func.count()).select_from(app_state)).scalar_one() == 2
    with engine.begin() as conn:
        unmark_job_skipped(conn, job_id=job_id)
    with engine.connect() as conn:
        assert skipped_job_ids(conn) == {}
        assert reported_job_ids(conn) == {job_id: NOW.isoformat()}
    _assert_fks_clean(engine)
