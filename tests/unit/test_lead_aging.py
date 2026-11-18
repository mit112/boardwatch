"""T298: lead aging, and leads that closed before anyone applied.

Expected values are worked out by hand from the fixture days below, not from the query.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, insert, text, update

from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.lead_aging_queries import lead_aging, source_yield
from boardwatch.store.queue_state import SKIP_KEY_PREFIX
from boardwatch.store.tables import (
    app_state,
    application_events,
    applications,
    artifacts,
    posting_events,
    postings,
)
from tests.unit.test_web_server import _deliver, _run

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


def _lead(conn: Connection, key: str, *, provider: str = "ashby") -> tuple[int, int]:
    return _deliver(conn, key, delivered_at=D0, judge=False, provider=provider)


def _apply(conn: Connection, job: int, at: datetime, *, attempt: int = 1) -> None:
    conn.execute(
        insert(applications).values(
            job_id=job,
            attempt_no=attempt,
            status="applied",
            created_at=at,
            updated_at=at,
            submitted_at=at,
        )
    )


def _close(conn: Connection, posting: int, at: datetime) -> None:
    conn.execute(update(postings).where(postings.c.id == posting).values(closed_at=at))


def test_each_outcome_takes_the_first_event(engine: Engine) -> None:
    with engine.begin() as conn:
        _, a1 = _lead(conn, "a1")
        _apply(conn, a1, D0 + timedelta(days=1))
        _, a2 = _lead(conn, "a2")
        _apply(conn, a2, D0 + timedelta(days=3))
        _apply(conn, a2, D0 + timedelta(days=9), attempt=2)  # a later attempt changes nothing
        p_c, c1 = _lead(conn, "c1", provider="greenhouse")
        _close(conn, p_c, D0 + timedelta(days=2))
        _apply(conn, c1, D0 + timedelta(days=5))  # applied AFTER it closed: closed first
        _, s1 = _lead(conn, "s1")
        conn.execute(
            insert(app_state).values(
                key=f"{SKIP_KEY_PREFIX}{s1}", value="2026-11-01T18:00:00+00:00"
            )
        )
        _lead(conn, "w1")  # nothing happened yet

        got = lead_aging(conn)

    assert got["leads"] == 5
    assert got["still_waiting"] == 1
    assert got["outcomes"]["applied"] == {"count": 2, "median_days": 2.0, "p90_days": 2.8}
    assert got["outcomes"]["closed"] == {"count": 1, "median_days": 2.0, "p90_days": 2.0}
    assert got["outcomes"]["skipped"] == {"count": 1, "median_days": 0.25, "p90_days": 0.25}
    assert got["closed_before_applied_by_board"] == {"greenhouse": 1}


def test_a_redelivered_lead_counts_once_from_its_first_delivery(engine: Engine) -> None:
    with engine.begin() as conn:
        posting, job = _lead(conn, "r1")
        version = conn.execute(
            artifacts.select().with_only_columns(artifacts.c.posting_version_id)
        ).scalar_one()
        conn.execute(
            insert(artifacts).values(
                posting_version_id=version,
                kind="resume_tailored",
                uri="/out/r1/again.typ",
                generator="boardwatch.tailor",
                media_type="text/x-tex",
                meta_json={},
                created_at=D0 + timedelta(days=4),
            )
        )
        _apply(conn, job, D0 + timedelta(days=5))
        got = lead_aging(conn)

    assert got["leads"] == 1
    # From the FIRST delivery (day 0), not the re-delivery (day 4).
    assert got["outcomes"]["applied"]["median_days"] == 5.0
    assert posting > 0


def test_an_empty_store_reports_no_figures(engine: Engine) -> None:
    with engine.begin() as conn:
        got = lead_aging(conn)
    assert got["leads"] == 0
    assert got["outcomes"]["applied"] == {"count": 0, "median_days": None, "p90_days": None}


def test_source_yield_credits_each_job_to_its_first_delivered_source(engine: Engine) -> None:
    with engine.begin() as conn:
        _, a = _lead(conn, "y1", provider="ashby")
        _apply(conn, a, D0 + timedelta(days=1))
        _lead(conn, "y2", provider="ashby")
        _, g = _lead(conn, "y3", provider="greenhouse")
        # The same job delivered again later from a lane: still credited to greenhouse, once.
        _deliver(
            conn,
            "y3-lane",
            job_id=g,
            delivered_at=D0 + timedelta(days=2),
            judge=False,
            provider="linkedin",
        )
        _apply(conn, g, D0 + timedelta(days=3))
        got = source_yield(conn)
    assert got == {
        "ashby": {"built": 2, "applied": 1},
        "greenhouse": {"built": 1, "applied": 1},
    }


def _imported(
    conn: Connection,
    job: int,
    at: datetime,
    *,
    occurred: datetime | None = None,
    status: str = "applied",
) -> None:
    """`create_application`'s shape for an import made at `at`, applied on `occurred` (the
    row's applied_at; None means the row gave no date, so it is `at`)."""
    when = occurred or at
    app = conn.execute(
        insert(applications).values(
            job_id=job,
            attempt_no=1,
            status=status,
            created_at=at,
            updated_at=at,
            submitted_at=when if status == "applied" else None,
        )
    ).inserted_primary_key[0]
    conn.execute(
        insert(application_events).values(
            application_id=app,
            event_type="created",
            from_status=None,
            to_status=status,
            occurred_at=when,
            recorded_at=at,
            source="import",
        )
    )


def test_an_imported_application_is_applied_with_no_measured_wait(engine: Engine) -> None:
    with engine.begin() as conn:
        posting, job = _lead(conn, "i1")
        _imported(conn, job, D0 + timedelta(days=30))  # the import's own date, not the real one
        _close(conn, posting, D0 + timedelta(days=2))  # closing after does not make it "closed"
        got = lead_aging(conn)
        yielded = source_yield(conn)
    assert got["applied_date_unknown"] == 1
    assert got["outcomes"]["applied"]["count"] == 0
    assert got["outcomes"]["closed"]["count"] == 0
    assert got["still_waiting"] == 0
    assert yielded == {"ashby": {"built": 1, "applied": 1}}


def test_the_earliest_attempt_is_the_earliest_instant_not_the_smallest_text(
    engine: Engine,
) -> None:
    """Text order and UTC order disagree: naive '...T12:00' sorts before '...T13:00+02:00', but
    the offset one is 11:00 UTC. The wait must use 11:00."""
    with engine.begin() as conn:
        _, job = _lead(conn, "m1")
        _apply(conn, job, D0 + timedelta(days=1))  # day 1, 12:00 naive UTC
        _apply(conn, job, D0, attempt=2)
        # Stored as offset-carrying TEXT, the way the live store holds some rows (the DateTime type
        # would drop the offset on a normal insert): 13:00+02:00 is 11:00 UTC on day 1.
        conn.execute(
            text(
                "UPDATE applications SET submitted_at = '2026-11-02 13:00:00.000000+02:00'"
                " WHERE job_id = :job AND attempt_no = 2"
            ),
            {"job": job},
        )
        got = lead_aging(conn)
    assert got["outcomes"]["applied"]["median_days"] == round(23 / 24, 2)


def test_an_import_that_supplied_a_date_is_measured_from_that_date(engine: Engine) -> None:
    with engine.begin() as conn:
        _, job = _lead(conn, "i2")
        # Imported on day 30, with the row's own applied_at, day 1.
        _imported(conn, job, D0 + timedelta(days=30), occurred=D0 + timedelta(days=1))
        got = lead_aging(conn)
    assert got["applied_date_unknown"] == 0
    assert got["outcomes"]["applied"] == {"count": 1, "median_days": 1.0, "p90_days": 1.0}


def test_an_undated_import_stays_undated_when_a_dated_retry_follows(engine: Engine) -> None:
    """Imported with no date, closed day 2, retried day 5. Whenever the first application was
    made, nobody can say it closed before anyone applied."""
    with engine.begin() as conn:
        posting, job = _lead(conn, "i3")
        _imported(conn, job, D0 + timedelta(days=1))
        _close(conn, posting, D0 + timedelta(days=2))
        _apply(conn, job, D0 + timedelta(days=5), attempt=2)
        got = lead_aging(conn)
    assert got["applied_date_unknown"] == 1
    assert got["outcomes"]["closed"]["count"] == 0
    assert got["outcomes"]["applied"]["count"] == 0


def test_a_reopen_does_not_erase_the_first_closure(engine: Engine) -> None:
    """Closed day 2 (an event), reopened (closed_at cleared), applied day 5: closed first."""
    with engine.begin() as conn:
        posting, job = _lead(conn, "o1")
        conn.execute(
            insert(posting_events).values(
                posting_id=posting, kind="closed", run_id=_run(conn),
                created_at=D0 + timedelta(days=2),
            )
        )
        _apply(conn, job, D0 + timedelta(days=5))
        got = lead_aging(conn)
    assert got["outcomes"]["closed"] == {"count": 1, "median_days": 2.0, "p90_days": 2.0}
    assert got["outcomes"]["applied"]["count"] == 0


def test_the_first_delivery_is_the_earliest_instant_not_the_smallest_text(
    engine: Engine,
) -> None:
    """ashby delivered at 12:00 naive UTC; greenhouse at '13:00+05:00', 08:00 UTC, earlier. Text
    order would credit ashby."""
    with engine.begin() as conn:
        _, job = _lead(conn, "t1", provider="ashby")
        _deliver(conn, "t1-gh", job_id=job, delivered_at=D0, judge=False, provider="greenhouse")
        gh_artifact = conn.execute(
            artifacts.select().with_only_columns(artifacts.c.id).order_by(artifacts.c.id.desc())
        ).first()
        assert gh_artifact is not None
        conn.execute(
            text("UPDATE artifacts SET created_at = :at WHERE id = :id"),
            {"at": "2026-11-01 13:00:00.000000+05:00", "id": gh_artifact.id},
        )
        got = source_yield(conn)
    assert got == {"greenhouse": {"built": 1, "applied": 0}}


def test_a_dated_rejected_import_is_applied_not_closed_first(engine: Engine) -> None:
    """A `rejected` import has no submitted_at; its created event dates it (day 1). It closed day
    3: applied first."""
    with engine.begin() as conn:
        posting, job = _lead(conn, "i4")
        _imported(
            conn, job, D0 + timedelta(days=30), occurred=D0 + timedelta(days=1), status="rejected"
        )
        _close(conn, posting, D0 + timedelta(days=3))
        got = lead_aging(conn)
        yielded = source_yield(conn)
    assert got["outcomes"]["applied"] == {"count": 1, "median_days": 1.0, "p90_days": 1.0}
    assert got["outcomes"]["closed"]["count"] == 0
    assert yielded == {"ashby": {"built": 1, "applied": 1}}


def test_a_closure_the_owner_undid_is_not_a_closure(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Owner-closed day 2 by mistake, undone day 3 (`postings reopen`), applied day 5: applied
    first. A scan reopen (no undo recorded) still counts the closure, per the test above."""
    from boardwatch.store import events
    from boardwatch.store.owner_close import close_postings, reopen_postings

    with engine.begin() as conn:
        posting, job = _lead(conn, "u1")
        monkeypatch.setattr(events, "utcnow", lambda: D0 + timedelta(days=2))
        close_postings(
            conn, [posting], run_id=_run(conn), evidence="looked closed", at=D0 + timedelta(days=2)
        )
        monkeypatch.setattr(events, "utcnow", lambda: D0 + timedelta(days=3))
        reopen_postings(conn, [posting], run_id=_run(conn))
        _apply(conn, job, D0 + timedelta(days=5))
        got = lead_aging(conn)
    assert got["outcomes"]["closed"]["count"] == 0
    assert got["outcomes"]["applied"]["count"] == 1


def test_reopening_a_probe_closure_by_hand_keeps_the_closure(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Probe-closed day 2 (no owner close), reopened by hand day 3, applied day 5: still closed
    first — only an owner undoing their OWN close marks a closure as a mistake."""
    from boardwatch.store import events
    from boardwatch.store.owner_close import reopen_postings

    with engine.begin() as conn:
        posting, job = _lead(conn, "u2")
        monkeypatch.setattr(events, "utcnow", lambda: D0 + timedelta(days=2))
        events.append_event(conn, posting, "closed", _run(conn))
        conn.execute(update(postings).where(postings.c.id == posting).values(status="closed"))
        monkeypatch.setattr(events, "utcnow", lambda: D0 + timedelta(days=3))
        reopen_postings(conn, [posting], run_id=_run(conn))
        _apply(conn, job, D0 + timedelta(days=5))
        got = lead_aging(conn)
    assert got["outcomes"]["closed"]["count"] == 1
    assert got["outcomes"]["applied"]["count"] == 0
