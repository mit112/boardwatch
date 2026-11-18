"""T311: withdrawals with their reasons. Expected values are by hand."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, insert

from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.tables import application_events, applications
from boardwatch.store.withdrawal_queries import withdrawals
from tests.unit.test_web_server import _deliver

D0 = datetime(2026, 11, 1, 12, 0, 0)


@pytest.fixture(autouse=True)
def _scratch_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("BOARDWATCH_DATA_DIR", str(tmp_path / "data"))


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path / "data")
    ensure_schema(eng)
    return eng


def _app(conn: Connection, job: int, status: str, submitted: datetime | None) -> int:
    return int(
        conn.execute(
            insert(applications).values(
                job_id=job,
                attempt_no=1,
                status=status,
                created_at=D0,
                updated_at=D0,
                submitted_at=submitted,
            )
        ).inserted_primary_key[0]
    )


def _event(
    conn: Connection,
    app: int,
    kind: str,
    frm: str | None,
    to: str,
    at: datetime,
    note: str | None = None,
) -> None:
    conn.execute(
        insert(application_events).values(
            application_id=app,
            event_type=kind,
            from_status=frm,
            to_status=to,
            occurred_at=at,
            recorded_at=at,
            source="user",
            note=note,
        )
    )


def test_withdrawals_count_once_per_application_and_keep_the_two_kinds_apart(
    engine: Engine,
) -> None:
    with engine.begin() as conn:
        _, j1 = _deliver(conn, "w1", judge=False)
        a1 = _app(conn, j1, "withdrawn", D0)
        _event(conn, a1, "created", None, "applied", D0)
        # Offset-aware, 1.5 days after a naive submission.
        at = (D0 + timedelta(days=1, hours=12)).replace(tzinfo=UTC)
        _event(conn, a1, "status_change", "applied", "withdrawn", at, "recruiter said role filled")
        _event(conn, a1, "status_change", "withdrawn", "withdrawn", at + timedelta(days=1))
        _, j2 = _deliver(conn, "w2", judge=False)
        a2 = _app(conn, j2, "withdrawn", None)
        _event(conn, a2, "created", None, "withdrawn", D0, "pre-flight: not a real job")
        got = withdrawals(conn)["withdrawals"]

    assert [(w["application_id"], w["kind"], w["days_after_applying"], w["note"]) for w in got] == [
        (a1, "after_applying", 1.5, "recruiter said role filled"),
        (a2, "before_applying", None, "pre-flight: not a real job"),
    ]
    assert got[0]["title"] == "Software Engineer"
