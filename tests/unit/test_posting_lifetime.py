"""T307: how long postings stay open, against how fast we apply.

Expected values are worked out by hand from the fixture days below, not from the query.

Fixture (day 0 is D0, 12:00 UTC):
  ashby      "Acme":   p1 closes day 1, p2 closes day 3, p3 never closes (open).
  greenhouse "Birch":  p4 closes day 2 and REOPENS day 3, p5 closes day 10.
  Applications: p1's job on day 5 (written +02:00, so 12:00 UTC), p4's job on day 1.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, insert, text

from boardwatch.store import posting_lifetime_queries as plq
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.posting_lifetime_queries import posting_lifetime
from boardwatch.store.tables import companies, jobs, posting_events, postings, runs

D0 = datetime(2026, 11, 1, 12, 0, 0)


@pytest.fixture(autouse=True)
def _scratch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("BOARDWATCH_DATA_DIR", str(tmp_path / "data"))
    plq._memo = None


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path / "data")
    ensure_schema(eng)
    return eng


def _company(conn: Connection, name: str, provider: str) -> int:
    return int(
        conn.execute(
            insert(companies).values(
                name=name, provider=provider, slug=name.lower(), source="user", watched=True
            )
        ).inserted_primary_key[0]
    )


def _run(conn: Connection) -> int:
    return int(conn.execute(insert(runs).values(started_at=D0, finished_at=D0)).inserted_primary_key[0])


def _posting(
    conn: Connection,
    company: int,
    key: str,
    *,
    new_at: datetime | None = D0,
    first_seen: str | datetime = D0,
    run: int,
) -> tuple[int, int]:
    """A posting with its own job and a `new` event on `new_at` (None: no event at all)."""
    job = int(conn.execute(insert(jobs).values(created_at=D0)).inserted_primary_key[0])
    posting = int(
        conn.execute(
            insert(postings).values(
                company_id=company,
                job_id=job,
                provider_posting_id=key,
                title="Engineer",
                normalized_title="engineer",
                remote_policy="remote",
                first_seen_at=D0,
                last_seen_at=D0,
                status="open",
                consecutive_missing=0,
                content_hash=f"hash-{key}",
                body_text="body",
            )
        ).inserted_primary_key[0]
    )
    if isinstance(first_seen, str):  # an offset-carrying stamp, written as text
        conn.execute(
            text("UPDATE postings SET first_seen_at = :s WHERE id = :i"),
            {"s": first_seen, "i": posting},
        )
    else:
        conn.execute(
            text("UPDATE postings SET first_seen_at = :s WHERE id = :i"),
            {"s": first_seen.isoformat(sep=" "), "i": posting},
        )
    if new_at is not None:
        _event(conn, posting, "new", new_at, run)
    return posting, job


def _event(conn: Connection, posting: int, kind: str, at: datetime, run: int) -> None:
    conn.execute(
        insert(posting_events).values(posting_id=posting, kind=kind, run_id=run, created_at=at)
    )


def _apply(conn: Connection, job: int, stamp: str) -> None:
    conn.execute(
        text(
            "INSERT INTO applications (job_id, attempt_no, status, created_at, updated_at,"
            " submitted_at) VALUES (:j, 1, 'applied', :s, :s, :s)"
        ),
        {"j": job, "s": stamp},
    )


def _seed(conn: Connection) -> int:
    """Returns the job of p2, which nothing has applied to."""
    run = _run(conn)
    acme = _company(conn, "Acme", "ashby")
    birch = _company(conn, "Birch", "greenhouse")
    p1, j1 = _posting(conn, acme, "p1", run=run)
    p2, j2 = _posting(conn, acme, "p2", run=run)
    _posting(conn, acme, "p3", run=run)
    p4, j4 = _posting(conn, birch, "p4", run=run)
    p5, _ = _posting(conn, birch, "p5", run=run)
    _event(conn, p1, "closed", D0 + timedelta(days=1), run)
    _event(conn, p2, "closed", D0 + timedelta(days=3), run)
    _event(conn, p4, "closed", D0 + timedelta(days=2), run)
    _event(conn, p4, "reopened", D0 + timedelta(days=3), run)
    _event(conn, p5, "closed", D0 + timedelta(days=10), run)
    # Day 5 at 12:00 UTC written with an offset; day 1 written naive.
    _apply(conn, j1, "2026-11-06T14:00:00+02:00")
    _apply(conn, j4, "2026-11-02 12:00:00")
    return j2


def test_lifetimes_open_count_and_reopen_rate(engine: Engine) -> None:
    with engine.begin() as conn:
        _seed(conn)
        got = posting_lifetime(conn)

    # Closed lifetimes [1, 3, 2, 10]: median (2 + 3) / 2; p90 3 + 0.7 * (10 - 3) = 7.9.
    assert got["closed"] == {"count": 4, "median_days": 2.5, "p90_days": 7.9}
    assert got["open"] == 1
    # One reopen event on one posting, of four postings that ever closed.
    assert got["reopen"] == {"events": 1, "postings": 1, "rate": 0.25}


def test_providers_split_lifetime_reopen_and_time_to_apply(engine: Engine) -> None:
    with engine.begin() as conn:
        _seed(conn)
        got = posting_lifetime(conn)

    by = {row["provider"]: row for row in got["providers"]}
    assert [row["provider"] for row in got["providers"]] == ["ashby", "greenhouse"]
    ashby, greenhouse = by["ashby"], by["greenhouse"]
    assert (ashby["count"], ashby["median_days"], ashby["p90_days"], ashby["open"]) == (
        2,
        2.0,
        2.8,
        1,
    )
    assert ashby["reopen_rate"] == 0.0
    # Applied on day 5 -> a 5.0-day wait, longer than the 2.0-day median lifetime: urgent.
    assert ashby["to_apply"] == {"count": 1, "median_days": 5.0, "p90_days": 5.0}
    assert ashby["urgent"] is True
    assert (greenhouse["count"], greenhouse["median_days"], greenhouse["open"]) == (2, 6.0, 0)
    assert greenhouse["p90_days"] == 9.2
    assert greenhouse["reopen_rate"] == 0.5
    assert greenhouse["to_apply"]["median_days"] == 1.0
    assert greenhouse["urgent"] is False


def test_time_to_apply_normalises_offset_stamps_and_flags_urgency(engine: Engine) -> None:
    with engine.begin() as conn:
        _seed(conn)
        got = posting_lifetime(conn)

    # Waits [5.0, 1.0]: median 3.0; p90 1 + 0.9 * 4 = 4.6. The 5.0 only comes out right if the
    # "+02:00" stamp is read as 12:00 UTC (read as 14:00 it would be 5.08).
    assert got["to_apply"] == {"count": 2, "median_days": 3.0, "p90_days": 4.6}
    # Median lifetime 2.5 < median wait 3.0.
    assert got["urgent"] is True


def test_an_offset_first_seen_is_compared_as_utc(engine: Engine) -> None:
    with engine.begin() as conn:
        run = _run(conn)
        acme = _company(conn, "Acme", "ashby")
        # 14:00+02:00 is D0 (12:00 UTC); applied day 2 at 12:00 naive UTC -> exactly 2.0 days.
        _, job = _posting(conn, acme, "p1", first_seen="2026-11-01T14:00:00+02:00", run=run)
        _apply(conn, job, "2026-11-03 12:00:00")
        got = posting_lifetime(conn)

    assert got["to_apply"] == {"count": 1, "median_days": 2.0, "p90_days": 2.0}


def test_open_postings_are_not_in_the_median_and_nothing_closed_is_a_dash(engine: Engine) -> None:
    with engine.begin() as conn:
        run = _run(conn)
        acme = _company(conn, "Acme", "ashby")
        _posting(conn, acme, "p1", run=run)
        _posting(conn, acme, "p2", run=run)
        got = posting_lifetime(conn)

    assert got["closed"] == {"count": 0, "median_days": None, "p90_days": None}
    assert got["open"] == 2
    assert got["reopen"]["rate"] is None
    assert got["urgent"] is None
    assert got["to_apply"] == {"count": 0, "median_days": None, "p90_days": None}


def test_companies_need_five_closed_postings_and_are_capped_by_count(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(plq, "COMPANY_ROWS", 2)
    with engine.begin() as conn:
        run = _run(conn)
        for name, closed, still_open in (("Big", 6, 1), ("Mid", 5, 0), ("Small", 4, 0), ("Tie", 5, 0)):
            company = _company(conn, name, "ashby")
            for i in range(closed):
                p, _ = _posting(conn, company, f"{name}{i}", run=run)
                _event(conn, p, "closed", D0 + timedelta(days=2), run)
            for i in range(still_open):
                _posting(conn, company, f"{name}open{i}", run=run)
        got = posting_lifetime(conn)

    # Small has 4 closed (< 5). Of the rest, the two with the most; Mid and Tie tie on 5, by name.
    assert [(row["company"], row["count"], row["open"]) for row in got["companies"]] == [
        ("Big", 6, 1),
        ("Mid", 5, 0),
    ]
    assert got["companies"][0]["median_days"] == 2.0


def test_a_posting_with_no_new_event_is_left_out(engine: Engine) -> None:
    with engine.begin() as conn:
        run = _run(conn)
        acme = _company(conn, "Acme", "ashby")
        p, _ = _posting(conn, acme, "p1", new_at=None, run=run)
        _event(conn, p, "closed", D0 + timedelta(days=1), run)
        got = posting_lifetime(conn)

    assert got["closed"]["count"] == 0
    assert got["open"] == 0


def test_the_event_aggregate_is_memoised_per_store_state_but_applications_are_not(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0
    real = plq._events_view

    def counting(conn: Connection) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return real(conn)

    monkeypatch.setattr(plq, "_events_view", counting)
    with engine.begin() as conn:
        j2 = _seed(conn)
        first = posting_lifetime(conn)
        again = posting_lifetime(conn)
        assert calls == 1
        assert again == first
        # A new application shows at once; the cached lifetimes are not recomputed.
        _apply(conn, j2, "2026-11-02 12:00:00")
        third = posting_lifetime(conn)
        assert calls == 1
        assert third["to_apply"]["count"] == first["to_apply"]["count"] + 1
        assert third["closed"] == first["closed"]
        # A new posting event is a new store state, so the aggregate is recomputed.
        _posting(conn, _company(conn, "Cedar", "lever"), "p6", run=_run(conn))
        assert posting_lifetime(conn)["open"] == first["open"] + 1
        assert calls == 2
