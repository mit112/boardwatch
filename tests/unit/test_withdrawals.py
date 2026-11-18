"""T311: withdrawals with their reasons. Expected values are by hand."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, insert, text

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


def test_the_newest_withdrawal_stands_ordered_by_instant_not_text(engine: Engine) -> None:
    """Declined before sending (day 0), applied day 1 (11-02 12:00), pulled back at '2026-11-04
    10:00' naive and again at '2026-11-04 07:00-05:00', which is 12:00 UTC: the newer instant,
    though it sorts BEFORE '10:00' as text. The standing withdrawal is the 12:00 one, 2.0 days."""
    with engine.begin() as conn:
        _, job = _deliver(conn, "w3", judge=False)
        app = _app(conn, job, "withdrawn", D0 + timedelta(days=1))
        _event(conn, app, "created", None, "withdrawn", D0, "pre-flight: unsure")
        _event(conn, app, "status_change", "withdrawn", "applied", D0 + timedelta(days=1))
        _event(conn, app, "status_change", "applied", "withdrawn", D0 + timedelta(days=2, hours=22))
        conn.execute(
            text(
                "INSERT INTO application_events (application_id, event_type, from_status,"
                " to_status, occurred_at, recorded_at, source, note) VALUES (:a, 'status_change',"
                " 'applied', 'withdrawn', '2026-11-04 07:00:00.000000-05:00',"
                " '2026-11-04 12:00:00.000000', 'user', 'pay too low')"
            ),
            {"a": app},
        )
        got = withdrawals(conn)["withdrawals"]
    assert [(w["kind"], w["days_after_applying"], w["note"]) for w in got] == [
        ("after_applying", 2.0, "pay too low")
    ]


def test_an_import_withdrawal_is_after_applying_and_dated_only_when_the_import_was(
    engine: Engine,
) -> None:
    with engine.begin() as conn:
        _, j1 = _deliver(conn, "w4", judge=False)
        undated = _app(conn, j1, "withdrawn", None)  # imported as interviewing, no date given
        conn.execute(
            insert(application_events).values(
                application_id=undated, event_type="created", from_status=None,
                to_status="interviewing", occurred_at=D0, recorded_at=D0, source="import",
            )
        )
        _event(conn, undated, "status_change", "interviewing", "withdrawn", D0 + timedelta(days=4))
        _, j2 = _deliver(conn, "w5", judge=False)
        dated = _app(conn, j2, "withdrawn", None)  # imported on D0, applied 2 days earlier
        conn.execute(
            insert(application_events).values(
                application_id=dated, event_type="created", from_status=None,
                to_status="rejected", occurred_at=D0 - timedelta(days=2), recorded_at=D0,
                source="import",
            )
        )
        _event(conn, dated, "status_change", "rejected", "withdrawn", D0 + timedelta(days=1))
        got = {w["application_id"]: w for w in withdrawals(conn)["withdrawals"]}
    assert (got[undated]["kind"], got[undated]["days_after_applying"]) == ("after_applying", None)
    assert (got[dated]["kind"], got[dated]["days_after_applying"]) == ("after_applying", 3.0)


def test_days_count_from_the_standing_cycles_submission(engine: Engine) -> None:
    """Applied day 0, withdrawn day 1, reapplied day 9, withdrawn day 10: 1.0 day, not 10."""
    with engine.begin() as conn:
        _, job = _deliver(conn, "w6", judge=False)
        app = _app(conn, job, "withdrawn", D0)
        _event(conn, app, "created", None, "applied", D0)
        _event(conn, app, "status_change", "applied", "withdrawn", D0 + timedelta(days=1))
        _event(conn, app, "status_change", "withdrawn", "applied", D0 + timedelta(days=9))
        _event(conn, app, "status_change", "applied", "withdrawn", D0 + timedelta(days=10))
        (got,) = withdrawals(conn)["withdrawals"]
    assert (got["kind"], got["days_after_applying"]) == ("after_applying", 1.0)


def test_an_undated_interested_import_is_dated_by_its_later_move_to_applied(
    engine: Engine,
) -> None:
    """Imported as `interested` on D0 (no date), moved to applied day 2, withdrawn day 3."""
    with engine.begin() as conn:
        _, job = _deliver(conn, "w7", judge=False)
        app = _app(conn, job, "withdrawn", D0 + timedelta(days=2))
        conn.execute(
            insert(application_events).values(
                application_id=app, event_type="created", from_status=None,
                to_status="interested", occurred_at=D0, recorded_at=D0, source="import",
            )
        )
        _event(conn, app, "status_change", "interested", "applied", D0 + timedelta(days=2))
        _event(conn, app, "status_change", "applied", "withdrawn", D0 + timedelta(days=3))
        (got,) = withdrawals(conn)["withdrawals"]
    assert (got["kind"], got["days_after_applying"]) == ("after_applying", 1.0)


def test_a_withdrawal_is_named_by_the_posting_its_application_names(engine: Engine) -> None:
    """One job, two delivered postings. The application was made against the FIRST; the newer
    one is a sibling. The row names the first, as the Applied page does."""
    from boardwatch.store.tables import posting_versions

    with engine.begin() as conn:
        first, job = _deliver(conn, "n1", judge=False, title="Platform Engineer")
        second, _ = _deliver(conn, "n2", job_id=job, judge=False, title="Platform Engineer II")
        version = conn.execute(
            posting_versions.select()
            .with_only_columns(posting_versions.c.id)
            .where(posting_versions.c.posting_id == first)
        ).scalar_one()
        app = int(
            conn.execute(
                insert(applications).values(
                    job_id=job, posting_version_id=version, attempt_no=1, status="withdrawn",
                    created_at=D0, updated_at=D0, submitted_at=D0,
                )
            ).inserted_primary_key[0]
        )
        _event(conn, app, "created", None, "applied", D0)
        _event(conn, app, "status_change", "applied", "withdrawn", D0 + timedelta(days=1))
        (got,) = withdrawals(conn)["withdrawals"]
    assert (got["posting_id"], got["title"]) == (first, "Platform Engineer")
    assert second > first
