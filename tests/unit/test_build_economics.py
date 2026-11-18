"""T310: résumé build economics. Expected values are worked out by hand from the fixture days."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, insert, select, text, update

from boardwatch.store.build_economics_queries import built_per_run, lead_outcomes
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queue_state import SKIP_KEY_PREFIX
from boardwatch.store.tables import (
    app_state,
    application_events,
    applications,
    artifacts,
    posting_versions,
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


def _lead(
    conn: Connection, key: str, *, provider: str = "ashby", run_id: int | None = None
) -> tuple[int, int]:
    return _deliver(conn, key, delivered_at=D0, judge=False, provider=provider, run_id=run_id)


def _version(conn: Connection, posting: int) -> int:
    return int(
        conn.execute(
            select(posting_versions.c.id).where(posting_versions.c.posting_id == posting)
        ).scalar_one()
    )


def _stub(conn: Connection, posting: int) -> None:
    """Make the posting's delivery a review-lane stub: delivered, never rendered (T43)."""
    conn.execute(
        update(artifacts)
        .where(artifacts.c.posting_version_id == _version(conn, posting))
        .values(meta_json={"typst_pdf_built": False, "pdf_uri": None, "pending_tailor": True})
    )


def _apply(conn: Connection, job: int, at: datetime) -> None:
    conn.execute(
        insert(applications).values(
            job_id=job,
            attempt_no=1,
            status="applied",
            created_at=at,
            updated_at=at,
            submitted_at=at,
        )
    )


def _close(conn: Connection, posting: int, at: datetime) -> None:
    conn.execute(update(postings).where(postings.c.id == posting).values(closed_at=at))


def _skip(conn: Connection, job: int, stamp: str) -> None:
    conn.execute(insert(app_state).values(key=f"{SKIP_KEY_PREFIX}{job}", value=stamp))


def test_every_built_lead_ends_in_exactly_one_state(engine: Engine) -> None:
    with engine.begin() as conn:
        _, a = _lead(conn, "a")
        _apply(conn, a, D0 + timedelta(days=1))  # applied
        p_b, _ = _lead(conn, "b")
        _close(conn, p_b, D0 + timedelta(days=2))  # closed without applying: wasted
        _, c = _lead(conn, "c", provider="greenhouse")
        _skip(conn, c, "2026-11-01T18:00:00+00:00")  # skipped: wasted
        _lead(conn, "d", provider="greenhouse")  # nothing yet: open, NOT wasted
        p_e, e = _lead(conn, "e")
        _skip(conn, e, "2026-11-01T18:00:00+00:00")  # skipped day 0, closed day 3: skipped first
        _close(conn, p_e, D0 + timedelta(days=3))
        p_f, f = _lead(conn, "f")
        _close(conn, p_f, D0 + timedelta(days=1))  # closed day 1, skipped day 2: closed first
        _skip(conn, f, "2026-11-03T18:00:00+00:00")
        p_g, g = _lead(conn, "g")
        _close(conn, p_g, D0 + timedelta(days=2))
        _apply(conn, g, D0 + timedelta(days=5))  # closed, but applied: the build was used

        got = lead_outcomes(conn)

    assert got["not_rendered_leads"] == 0
    assert got["totals"] == {
        "built": 7,
        "applied": 2,
        "closed": 2,
        "skipped": 2,
        "open": 1,
        "apply_rate": 2 / 7,
        "settled_rate": 2 / 6,
    }
    # Largest board first. The open lead is on neither side of greenhouse's settled rate.
    assert got["boards"] == [
        {
            "board": "ashby",
            "built": 5,
            "applied": 2,
            "closed": 2,
            "skipped": 1,
            "open": 0,
            "apply_rate": 2 / 5,
            "settled_rate": 2 / 5,
        },
        {
            "board": "greenhouse",
            "built": 2,
            "applied": 0,
            "closed": 0,
            "skipped": 1,
            "open": 1,
            "apply_rate": 0.0,
            "settled_rate": 0.0,
        },
    ]


def test_an_empty_store_has_no_rates(engine: Engine) -> None:
    with engine.begin() as conn:
        got = lead_outcomes(conn)
        assert built_per_run(conn, []) == {}
    assert got["boards"] == []
    assert got["totals"] == {
        "built": 0,
        "applied": 0,
        "closed": 0,
        "skipped": 0,
        "open": 0,
        "apply_rate": None,
        "settled_rate": None,
    }


def test_a_board_with_only_open_leads_has_no_settled_rate(engine: Engine) -> None:
    with engine.begin() as conn:
        _lead(conn, "young")
        got = lead_outcomes(conn)
    assert got["boards"][0]["open"] == 1
    assert got["boards"][0]["apply_rate"] == 0.0
    assert got["boards"][0]["settled_rate"] is None


def test_a_stub_is_not_a_build_until_a_rendered_row_promotes_it(engine: Engine) -> None:
    with engine.begin() as conn:
        p_stub, _ = _lead(conn, "stub")
        _stub(conn, p_stub)
        p_promoted, promoted = _lead(conn, "promoted")
        _stub(conn, p_promoted)
        conn.execute(  # `boardwatch tailor run`: a NEW row with neither key
            insert(artifacts).values(
                posting_version_id=_version(conn, p_promoted),
                kind="resume_tailored",
                uri="/out/p.typ",
                media_type="text/x-tex",
                meta_json={"pdf_uri": None},
                created_at=D0 + timedelta(days=1),
            )
        )
        _apply(conn, promoted, D0 + timedelta(days=2))
        got = lead_outcomes(conn)
    assert got["not_rendered_leads"] == 1
    assert got["totals"]["built"] == 1
    assert got["totals"]["applied"] == 1


def test_a_redelivered_lead_is_one_build_credited_to_its_first_board(engine: Engine) -> None:
    """ashby delivered at 12:00 naive UTC; greenhouse at '13:00+05:00', 08:00 UTC and earlier.
    Text order would credit ashby."""
    with engine.begin() as conn:
        _, job = _lead(conn, "t1", provider="ashby")
        _deliver(conn, "t1-gh", job_id=job, delivered_at=D0, judge=False, provider="greenhouse")
        newest = conn.execute(select(artifacts.c.id).order_by(artifacts.c.id.desc())).first()
        assert newest is not None
        conn.execute(
            text("UPDATE artifacts SET created_at = :at WHERE id = :id"),
            {"at": "2026-11-01 13:00:00.000000+05:00", "id": newest.id},
        )
        got = lead_outcomes(conn)
    assert [(b["board"], b["built"]) for b in got["boards"]] == [("greenhouse", 1)]


def test_a_skip_is_compared_to_the_close_as_instants_not_text(engine: Engine) -> None:
    """Skipped '13:00+05:00' on day 1 is 08:00 UTC, before the 10:00 close. As text, 'T' sorts
    after ' ', which would put the skip later and call the lead closed."""
    with engine.begin() as conn:
        posting, job = _lead(conn, "o1")
        _close(conn, posting, datetime(2026, 11, 2, 10, 0, 0))
        _skip(conn, job, "2026-11-02T13:00:00+05:00")
        got = lead_outcomes(conn)
    assert got["totals"]["skipped"] == 1
    assert got["totals"]["closed"] == 0


def test_an_import_with_an_unknown_date_is_applied_and_never_measured(engine: Engine) -> None:
    """Imported on day 30 with no applied date (event time == import time). The posting closed
    day 2: whenever it was applied to, the build was used, so it is not a wasted build."""
    with engine.begin() as conn:
        posting, job = _lead(conn, "i1")
        _close(conn, posting, D0 + timedelta(days=2))
        at = D0 + timedelta(days=30)
        app = conn.execute(
            insert(applications).values(
                job_id=job,
                attempt_no=1,
                status="applied",
                created_at=at,
                updated_at=at,
                submitted_at=at,
            )
        ).inserted_primary_key[0]
        conn.execute(
            insert(application_events).values(
                application_id=app,
                event_type="created",
                from_status=None,
                to_status="applied",
                occurred_at=at,
                recorded_at=at,
                source="import",
            )
        )
        got = lead_outcomes(conn)
    assert (got["totals"]["applied"], got["totals"]["closed"]) == (1, 0)


def test_built_per_run_counts_renders_and_stubs_apart_for_the_runs_asked(engine: Engine) -> None:
    with engine.begin() as conn:
        r1, r2, r3 = _run(conn), _run(conn), _run(conn)
        _lead(conn, "r1a", run_id=r1)
        _lead(conn, "r1b", run_id=r1)
        p_stub, _ = _lead(conn, "r1c", run_id=r1)
        _stub(conn, p_stub)
        _lead(conn, "r3a", run_id=r3)  # a run that was not asked for
        got = built_per_run(conn, [r1, r2])
    assert got == {r1: {"built": 2, "not_rendered": 1}, r2: {"built": 0, "not_rendered": 0}}


def test_a_lead_applied_to_before_its_build_is_counted_apart(engine: Engine) -> None:
    """Built (rendered) on D0. a: applied D0 + 1 day, after the build: applied. b: applied D0 - 1
    day, before the build existed: outside the cohort, in `applied_before_build_leads`."""
    with engine.begin() as conn:
        _, a = _lead(conn, "a")
        _apply(conn, a, D0 + timedelta(days=1))
        _, b = _lead(conn, "b")
        _apply(conn, b, D0 - timedelta(days=1))
        got = lead_outcomes(conn)
    assert got["applied_before_build_leads"] == 1
    assert (got["totals"]["built"], got["totals"]["applied"]) == (1, 1)


def test_a_tailor_whose_pdf_failed_is_not_a_build(engine: Engine) -> None:
    """Not a stub (`pending_tailor` absent), but `typst_pdf_built` false: no PDF reached the owner,
    so the lead is not rendered, exactly as a stub is."""
    with engine.begin() as conn:
        p_a, _ = _lead(conn, "a")
        conn.execute(
            update(artifacts)
            .where(artifacts.c.posting_version_id == _version(conn, p_a))
            .values(meta_json={"typst_pdf_built": False, "pdf_uri": None})
        )
        _lead(conn, "b")
        got = lead_outcomes(conn)
    assert got["not_rendered_leads"] == 1
    assert got["totals"]["built"] == 1


def test_a_dated_attempt_before_the_build_counts_apart_even_beside_an_undated_import(
    engine: Engine,
) -> None:
    """T310 review. Built D0. An undated import (event time == import time, day 30) and a dated
    retry on D0 - 1 day: the dated attempt shows the owner applied before the build existed."""
    with engine.begin() as conn:
        _, job = _lead(conn, "u1")
        at = D0 + timedelta(days=30)
        app = conn.execute(
            insert(applications).values(
                job_id=job, attempt_no=1, status="applied", created_at=at, updated_at=at,
                submitted_at=at,
            )
        ).inserted_primary_key[0]
        conn.execute(
            insert(application_events).values(
                application_id=app, event_type="created", from_status=None, to_status="applied",
                occurred_at=at, recorded_at=at, source="import",
            )
        )
        early = D0 - timedelta(days=1)
        conn.execute(
            insert(applications).values(
                job_id=job, attempt_no=2, status="applied", created_at=early, updated_at=early,
                submitted_at=early,
            )
        )
        got = lead_outcomes(conn)
    assert got["applied_before_build_leads"] == 1
    assert got["totals"]["built"] == 0


def test_the_cutoff_is_the_first_render_as_an_instant_not_text(engine: Engine) -> None:
    """Rendered twice: '2026-11-01 10:00:00+05:00' (05:00 UTC) and then D0 (12:00 UTC, naive).
    Applied 08:00 UTC, between them: after the first build, so applied. As text the naive D0
    sorts first, which would put the cutoff at 12:00 and the application before the build."""
    with engine.begin() as conn:
        _, job = _lead(conn, "m1")
        _deliver(conn, "m1-gh", job_id=job, delivered_at=D0, judge=False, provider="greenhouse")
        newest = conn.execute(select(artifacts.c.id).order_by(artifacts.c.id.desc())).first()
        assert newest is not None
        conn.execute(
            text("UPDATE artifacts SET created_at = :at WHERE id = :id"),
            {"at": "2026-11-01 10:00:00.000000+05:00", "id": newest.id},
        )
        _apply(conn, job, datetime(2026, 11, 1, 8, 0, 0))
        got = lead_outcomes(conn)
    assert got["applied_before_build_leads"] == 0
    assert got["totals"]["applied"] == 1
