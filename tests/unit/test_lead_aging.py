"""T298: lead aging, and leads that closed before anyone applied.

Expected values are worked out by hand from the fixture days below, not from the query.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, insert, update

from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.lead_aging_queries import lead_aging, source_yield
from boardwatch.store.queue_state import SKIP_KEY_PREFIX
from boardwatch.store.tables import app_state, applications, artifacts, postings
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
