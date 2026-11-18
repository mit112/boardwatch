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
from sqlalchemy import Connection, Engine, func, insert, select, text, update

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


def _event_text(conn: Connection, posting: int, kind: str, stamp: str, run: int) -> None:
    """An event whose timestamp is written as text, so it can carry a UTC offset."""
    conn.execute(
        text(
            "INSERT INTO posting_events (posting_id, kind, run_id, created_at)"
            " VALUES (:p, :k, :r, :s)"
        ),
        {"p": posting, "k": kind, "r": run, "s": stamp},
    )


def _apply(
    conn: Connection,
    job: int,
    stamp: str,
    *,
    attempt: int = 1,
    imported_recorded: str | None = None,
) -> None:
    """A submitted application. `imported_recorded` makes it a `track import` row made at that
    stamp, `create_application`'s shape: `created_at` is the import time, `submitted_at` the
    applied date (equal to it when the file gave no date)."""
    made = imported_recorded or stamp
    app_id = conn.execute(
        text(
            "INSERT INTO applications (job_id, attempt_no, status, created_at, updated_at,"
            " submitted_at) VALUES (:j, :n, 'applied', :c, :c, :s)"
        ),
        {"j": job, "n": attempt, "s": stamp, "c": made},
    ).lastrowid
    if imported_recorded is not None:
        conn.execute(
            text(
                "INSERT INTO application_events (application_id, event_type, to_status,"
                " occurred_at, recorded_at, source) VALUES (:a, 'created', 'applied', :o, :r,"
                " 'import')"
            ),
            {"a": app_id, "o": stamp, "r": imported_recorded},
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


def test_lifetimes_never_closed_count_and_reopen_rate(engine: Engine) -> None:
    with engine.begin() as conn:
        _seed(conn)
        got = posting_lifetime(conn)

    # Closed lifetimes [1, 3, 2, 10]: median (2 + 3) / 2; p90 3 + 0.7 * (10 - 3) = 7.9.
    assert got["closed"] == {"count": 4, "median_days": 2.5, "p90_days": 7.9}
    assert got["never_closed"] == 1
    # One reopen event on one posting, of four postings that ever closed.
    assert got["reopen"] == {"events": 1, "postings": 1, "rate": 0.25}


def test_providers_split_lifetime_reopen_and_time_to_apply(engine: Engine) -> None:
    with engine.begin() as conn:
        _seed(conn)
        got = posting_lifetime(conn)

    by = {row["provider"]: row for row in got["providers"]}
    assert [row["provider"] for row in got["providers"]] == ["ashby", "greenhouse"]
    ashby, greenhouse = by["ashby"], by["greenhouse"]
    assert (ashby["count"], ashby["median_days"], ashby["p90_days"], ashby["never_closed"]) == (
        2,
        2.0,
        2.8,
        1,
    )
    assert ashby["reopen_rate"] == 0.0
    # Applied on day 5 -> a 5.0-day wait, longer than the 2.0-day median lifetime: urgent.
    assert ashby["to_apply"] == {"count": 1, "median_days": 5.0, "p90_days": 5.0}
    assert ashby["urgent"] is True
    assert (greenhouse["count"], greenhouse["median_days"], greenhouse["never_closed"]) == (2, 6.0, 0)
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
    assert got["to_apply"] == {
        "count": 2,
        "median_days": 3.0,
        "p90_days": 4.6,
        "excluded_imports": 0,
    }
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

    assert got["to_apply"] == {
        "count": 1,
        "median_days": 2.0,
        "p90_days": 2.0,
        "excluded_imports": 0,
    }


def test_never_closed_postings_are_not_in_the_median_and_nothing_closed_is_a_dash(engine: Engine) -> None:
    with engine.begin() as conn:
        run = _run(conn)
        acme = _company(conn, "Acme", "ashby")
        _posting(conn, acme, "p1", run=run)
        _posting(conn, acme, "p2", run=run)
        got = posting_lifetime(conn)

    assert got["closed"] == {"count": 0, "median_days": None, "p90_days": None}
    assert got["never_closed"] == 2
    assert got["reopen"]["rate"] is None
    assert got["urgent"] is None
    assert got["to_apply"] == {
        "count": 0,
        "median_days": None,
        "p90_days": None,
        "excluded_imports": 0,
    }


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

    # Small has 4 closed (< 5). Of the rest, the two with the most; Mid and Tie tie on 5, by id.
    assert [(row["company"], row["count"], row["never_closed"]) for row in got["companies"]] == [
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
    assert got["never_closed"] == 0




def test_first_close_is_the_earliest_instant_not_the_smallest_text(engine: Engine) -> None:
    with engine.begin() as conn:
        run = _run(conn)
        acme = _company(conn, "Acme", "ashby")
        p, _ = _posting(conn, acme, "p1", run=run)
        # Day 2 12:00 UTC written naive, and 13:00+02:00 the same day = 11:00 UTC, one hour
        # EARLIER. As text the naive one sorts first (" " < "T"), so a text MIN picks day 2.0.
        _event_text(conn, p, "closed", "2026-11-03 12:00:00", run)
        _event_text(conn, p, "closed", "2026-11-03T13:00:00+02:00", run)
        got = posting_lifetime(conn)

    # 1 day 23 hours = 1.9583 days, rounded to 1.96.
    assert got["closed"] == {"count": 1, "median_days": 1.96, "p90_days": 1.96}


def test_the_earliest_application_is_the_earliest_instant_not_the_smallest_text(
    engine: Engine,
) -> None:
    with engine.begin() as conn:
        run = _run(conn)
        acme = _company(conn, "Acme", "ashby")
        _, job = _posting(conn, acme, "p1", run=run)
        # Attempt 1: day 1 12:00 UTC (naive). Attempt 2: 13:00+02:00 = 11:00 UTC, an hour earlier,
        # though its text sorts after attempt 1's.
        _apply(conn, job, "2026-11-02 12:00:00", attempt=1)
        _apply(conn, job, "2026-11-02T13:00:00+02:00", attempt=2)
        got = posting_lifetime(conn)

    # 23 hours = 0.9583 days, rounded to 0.96 (the text MIN gives 1.0).
    assert got["to_apply"]["median_days"] == 0.96


def test_a_reclosed_posting_counts_once_at_its_first_close(engine: Engine) -> None:
    with engine.begin() as conn:
        run = _run(conn)
        acme = _company(conn, "Acme", "ashby")
        p, _ = _posting(conn, acme, "p1", run=run)
        _event(conn, p, "closed", D0 + timedelta(days=2), run)
        _event(conn, p, "reopened", D0 + timedelta(days=3), run)
        _event(conn, p, "closed", D0 + timedelta(days=6), run)
        got = posting_lifetime(conn)

    assert got["closed"] == {"count": 1, "median_days": 2.0, "p90_days": 2.0}
    assert got["never_closed"] == 0
    assert got["reopen"] == {"events": 1, "postings": 1, "rate": 1.0}


def test_a_reopened_posting_that_is_open_now_is_not_counted_as_never_closed(
    engine: Engine,
) -> None:
    with engine.begin() as conn:
        run = _run(conn)
        acme = _company(conn, "Acme", "ashby")
        p, _ = _posting(conn, acme, "p1", run=run)
        _event(conn, p, "closed", D0 + timedelta(days=4), run)
        _event(conn, p, "reopened", D0 + timedelta(days=5), run)
        got = posting_lifetime(conn)

    assert got["closed"]["count"] == 1
    assert got["never_closed"] == 0


def test_import_stamped_applications_are_left_out_and_counted(engine: Engine) -> None:
    with engine.begin() as conn:
        run = _run(conn)
        acme = _company(conn, "Acme", "ashby")
        _, only_import = _posting(conn, acme, "a", run=run)
        _, mixed = _posting(conn, acme, "b", run=run)
        _, dated = _posting(conn, acme, "c", run=run)
        # a: submitted_at is the import time (equal to created_at, source "import").
        stamp = "2026-11-06 12:00:00"
        _apply(conn, only_import, stamp, imported_recorded=stamp)
        # b: an import-stamped attempt 1, then a real attempt 2 on day 3 -> 3.0 days.
        _apply(conn, mixed, "2026-11-07 12:00:00", attempt=1, imported_recorded="2026-11-07 12:00:00")
        _apply(conn, mixed, "2026-11-04 12:00:00", attempt=2)
        # c: imported WITH a real date (recorded 17 days after it happened) -> kept, 2.0 days.
        _apply(conn, dated, "2026-11-03 12:00:00", imported_recorded="2026-11-20 09:00:00")
        got = posting_lifetime(conn)

    # Waits [3.0, 2.0] -> median 2.5, p90 2 + 0.9 * 1 = 2.9. Job a is the one left out.
    assert got["to_apply"] == {
        "count": 2,
        "median_days": 2.5,
        "p90_days": 2.9,
        "excluded_imports": 1,
    }


def _counting(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    calls: list[int] = []
    real = plq._aggregate

    def counting(conn: Connection, provider_of: dict[int, str]) -> plq._Aggregate:
        calls.append(1)
        return real(conn, provider_of)

    monkeypatch.setattr(plq, "_aggregate", counting)
    return calls


def test_applications_do_not_invalidate_the_memo_but_show_at_once(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _counting(monkeypatch)
    with engine.begin() as conn:
        j2 = _seed(conn)
        first = posting_lifetime(conn)
        assert posting_lifetime(conn) == first
        assert len(calls) == 1
        _apply(conn, j2, "2026-11-02 12:00:00")
        third = posting_lifetime(conn)

    assert len(calls) == 1
    assert third["to_apply"]["count"] == first["to_apply"]["count"] + 1
    assert third["closed"] == first["closed"]


def test_a_new_run_alone_invalidates_the_memo(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _counting(monkeypatch)
    with engine.begin() as conn:
        _seed(conn)
        posting_lifetime(conn)
        _run(conn)  # a finished run, and no new event
        posting_lifetime(conn)

    assert len(calls) == 2


def test_a_new_event_alone_invalidates_the_memo(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _counting(monkeypatch)
    with engine.begin() as conn:
        _seed(conn)
        before = posting_lifetime(conn)
        # Same latest run, one more event.
        run = conn.execute(select(func.max(runs.c.id))).scalar_one()
        late, _ = _posting(conn, _company(conn, "Cedar", "lever"), "late", run=run)
        _event(conn, late, "closed", D0 + timedelta(days=1), run)
        after = posting_lifetime(conn)

    assert len(calls) == 2
    assert after["closed"]["count"] == before["closed"]["count"] + 1


def test_a_changed_provider_or_store_file_invalidates_the_memo(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _counting(monkeypatch)
    with engine.begin() as conn:
        _seed(conn)
        posting_lifetime(conn)
        conn.execute(update(companies).where(companies.c.name == "Birch").values(provider="lever"))
        moved = posting_lifetime(conn)
        assert len(calls) == 2
        assert [row["provider"] for row in moved["providers"]] == ["ashby", "lever"]
        # The same path under a different inode is a different store.
        monkeypatch.setattr(plq, "_inode", lambda _engine: 987_654_321)
        posting_lifetime(conn)

    assert len(calls) == 3


def test_a_renamed_company_shows_at_once_without_recomputing(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _counting(monkeypatch)
    with engine.begin() as conn:
        run = _run(conn)
        company = _company(conn, "Acme", "ashby")
        for i in range(5):
            p, _ = _posting(conn, company, f"p{i}", run=run)
            _event(conn, p, "closed", D0 + timedelta(days=2), run)
        assert [row["company"] for row in posting_lifetime(conn)["companies"]] == ["Acme"]
        conn.execute(update(companies).where(companies.c.id == company).values(name="Renamed"))
        again = posting_lifetime(conn)

    assert [row["company"] for row in again["companies"]] == ["Renamed"]
    assert len(calls) == 1


def test_an_import_with_a_date_seconds_before_the_import_is_measured(engine: Engine) -> None:
    """Applied day 1 12:00:00, imported 15 s later with that date: the date is real, 1.0 day."""
    with engine.begin() as conn:
        run = _run(conn)
        acme = _company(conn, "Acme", "ashby")
        _, job = _posting(conn, acme, "a", run=run)
        _apply(conn, job, "2026-11-02 12:00:00", imported_recorded="2026-11-02 12:00:15")
        got = posting_lifetime(conn)
    assert (got["to_apply"]["count"], got["to_apply"]["median_days"]) == (1, 1.0)
    assert got["to_apply"]["excluded_imports"] == 0
