from pathlib import Path

import pytest
from sqlalchemy import Engine, insert

from boardwatch.core.clock import utcnow
from boardwatch.store.applications import (
    create_application,
    get_application,
    get_application_events,
    get_applications,
    set_application_status,
)
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.tables import jobs


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path)
    ensure_schema(eng)
    return eng


@pytest.fixture()
def job_id(engine: Engine) -> int:
    with engine.begin() as conn:
        return int(conn.execute(insert(jobs).values(created_at=utcnow())).inserted_primary_key[0])


def test_create_logs_initial_event_and_assigns_attempt_one(engine, job_id):
    with engine.begin() as conn:
        app_id = create_application(conn, job_id=job_id)
    with engine.connect() as conn:
        app = get_application(conn, app_id)
        events = get_application_events(conn, app_id)
    assert app.attempt_no == 1
    assert app.status == "interested"
    assert [e.event_type for e in events] == ["created"]
    assert events[0].to_status == "interested"


def test_reapplication_increments_attempt_no(engine, job_id):
    with engine.begin() as conn:
        create_application(conn, job_id=job_id)
        second = create_application(conn, job_id=job_id)
    with engine.connect() as conn:
        assert get_application(conn, second).attempt_no == 2      # UNIQUE(job_id, attempt_no)
        assert len(get_applications(conn, job_id)) == 2


def test_status_change_logs_from_to_and_sets_submitted(engine, job_id):
    with engine.begin() as conn:
        app_id = create_application(conn, job_id=job_id)
    with engine.begin() as conn:
        set_application_status(conn, application_id=app_id, to_status="applied", source="user")
    with engine.connect() as conn:
        app = get_application(conn, app_id)
        last = get_application_events(conn, app_id)[-1]
    assert app.status == "applied"
    assert app.submitted_at is not None
    assert (last.from_status, last.to_status) == ("interested", "applied")


def test_application_events_are_immutable(engine, job_id):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    with engine.begin() as conn:
        app_id = create_application(conn, job_id=job_id)
    with engine.begin() as conn, pytest.raises(IntegrityError):
        conn.execute(text("UPDATE application_events SET note='x' WHERE application_id=:a"),
                     {"a": app_id})
