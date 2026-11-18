"""T313: store hygiene. Every expected value below is worked out by hand from the fixture rows."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, insert, text
from sqlalchemy.exc import OperationalError

from boardwatch.store import store_hygiene_queries as hygiene
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.store_hygiene_queries import store_hygiene
from boardwatch.store.tables import jobs, posting_versions, runs
from tests.unit.test_web_server import _deliver

# A Tuesday. The eight weeks shown start on Mondays 2026-09-28 ... 2026-11-16.
NOW = datetime(2026, 11, 17, 12, 0, 0)
UNUSED = Path("/nonexistent/boardwatch.db")


@pytest.fixture(autouse=True)
def _scratch_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("BOARDWATCH_DATA_DIR", str(tmp_path / "data"))


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path / "data")
    ensure_schema(eng)
    return eng


def _version(conn: Connection, posting_id: int, n: int) -> int:
    return int(
        conn.execute(
            insert(posting_versions).values(
                posting_id=posting_id,
                content_hash=f"h{n}",
                body_text="body",
                captured_at=NOW,
                capture_reason="revised",
            )
        ).inserted_primary_key[0]
    )


def _quarantine(
    conn: Connection, posting_id: int, n: int, quarantined: str, reopened: str | None
) -> None:
    """Raw text, so a row can carry an offset; the table is read back through SQLAlchemy."""
    conn.execute(
        text(
            "INSERT INTO quarantined_bodies (posting_version_id, posting_id, markers_json,"
            " catalog_version, quarantined_at, reopened_at)"
            " VALUES (:v, :p, '[]', 1, :q, :r)"
        ),
        {"v": _version(conn, posting_id, n), "p": posting_id, "q": quarantined, "r": reopened},
    )


def test_quarantine_is_ordered_and_bucketed_by_instant_not_text(engine: Engine) -> None:
    """Now is 2026-11-17 12:00 UTC.

    * A held, quarantined '2026-11-10 12:00'.
    * B held, '2026-11-10 06:00-12:00' = 18:00 UTC: later than A though it sorts BEFORE it as text.
      The oldest held is A: 7.0 days. (Taken by text, B: 6.75 days, shown 6.8.)
    * C held, '2026-11-16 09:00'.
    * D drained '2026-11-16 01:00'; E drained '2026-11-15 22:00-05:00' = 2026-11-16 03:00 UTC:
      the later drain though it sorts BEFORE D as text, and it falls in the week of 11-16, not 11-09.
      Last drain 11-16 03:00 is 33 h = 1.4 days ago (by text, D: 35 h = 1.5).
    """
    with engine.begin() as conn:
        posting, _ = _deliver(conn, "q1", judge=False)
        _quarantine(conn, posting, 1, "2026-11-10 12:00:00.000000", None)
        _quarantine(conn, posting, 2, "2026-11-10 06:00:00.000000-12:00", None)
        _quarantine(conn, posting, 3, "2026-11-16 09:00:00.000000", None)
        _quarantine(conn, posting, 4, "2026-10-01 00:00:00.000000", "2026-11-16 01:00:00.000000")
        _quarantine(
            conn, posting, 5, "2026-11-12 00:00:00.000000", "2026-11-15 22:00:00.000000-05:00"
        )
        got = store_hygiene(conn, UNUSED, now=NOW)["quarantine"]

    assert (got["held"], got["drained"]) == (3, 2)
    assert got["oldest_held_days"] == 7.0
    assert got["last_drained_at"] == "2026-11-16T03:00:00"
    assert got["days_since_drain"] == 1.4
    assert got["stalled"] is False
    weekly = got["weekly"]
    assert [w["week_start"] for w in weekly] == [
        "2026-09-28",
        "2026-10-05",
        "2026-10-12",
        "2026-10-19",
        "2026-10-26",
        "2026-11-02",
        "2026-11-09",
        "2026-11-16",
    ]
    # Quarantined: D on 10-01 (week 09-28); A, B, E in the week of 11-09; C in 11-16.
    assert [w["quarantined"] for w in weekly] == [1, 0, 0, 0, 0, 0, 3, 1]
    # Drained: D and E both in the week of 11-16 (E's text date would put it a week earlier).
    assert [w["drained"] for w in weekly] == [0, 0, 0, 0, 0, 0, 0, 2]


@pytest.mark.parametrize(
    ("held", "last_drain", "stalled"),
    [
        (True, "2026-10-28 12:00:00", True),  # 20 days ago
        (True, "2026-11-07 12:00:00", False),  # 10 days ago
        (True, "2026-11-03 12:00:00", False),  # exactly 14 days: the bar is "more than"
        (True, "2026-11-03 11:00:00", True),  # 14 days and 1 hour
        (True, None, True),  # held, never drained
        (False, "2026-01-01 00:00:00", False),  # nothing held, nothing to drain
        (False, None, False),
    ],
)
def test_the_drain_is_stalled_only_when_something_is_held_and_nothing_drained_lately(
    engine: Engine, held: bool, last_drain: str | None, stalled: bool
) -> None:
    with engine.begin() as conn:
        posting, _ = _deliver(conn, "q2", judge=False)
        n = 0
        if held:
            n += 1
            _quarantine(conn, posting, n, "2026-09-01 00:00:00.000000", None)
        if last_drain is not None:
            n += 1
            _quarantine(conn, posting, n, "2026-08-01 00:00:00.000000", last_drain)
        got = store_hygiene(conn, UNUSED, now=NOW)["quarantine"]
    assert got["stalled"] is stalled
    if not held:
        assert got["oldest_held_days"] is None


def test_an_empty_quarantine_reports_none_not_zero_days(engine: Engine) -> None:
    with engine.begin() as conn:
        got = store_hygiene(conn, UNUSED, now=NOW)["quarantine"]
    assert (got["held"], got["drained"]) == (0, 0)
    assert got["oldest_held_days"] is None
    assert got["last_drained_at"] is None
    assert got["days_since_drain"] is None
    assert all((w["quarantined"], w["drained"]) == (0, 0) for w in got["weekly"])


def _event(
    conn: Connection, posting: int, frm: int | None, to: int, method: str, version: str, at: str
) -> None:
    conn.execute(
        text(
            "INSERT INTO job_grouping_events (posting_id, from_job_id, to_job_id, method,"
            " algorithm_version, created_at) VALUES (:p, :f, :t, :m, :v, :at)"
        ),
        {"p": posting, "f": frm, "t": to, "m": method, "v": version, "at": at},
    )


def test_grouping_counts_merges_by_method_week_and_per_thousand_postings(engine: Engine) -> None:
    """Four postings, so the highest postings id is 4. Two further jobs are merged away.

    Events: two exact_quad moves out of the first, one out of the second, one fuzzy move out of
    the second, and one event with no source job (an initial assignment, not a duplicate).
    So merges = 4, from 2 distinct jobs, 1 event without a source; 4 * 1000 / 4 = 1000.0 per 1,000.
    Weekly: the week of 11-02 has the naive 11-03 event; the week of 11-09 the fuzzy 11-10 one;
    the week of 11-16 has the naive 11-16 02:00 event and '2026-11-15 23:00-05:00' (= 11-16 04:00
    UTC, not the week of 11-09 its text date names).
    """
    with engine.begin() as conn:
        ids = [_deliver(conn, f"g{i}", judge=False)[0] for i in range(4)]
        assert max(ids) == 4
        merged_a = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
        merged_b = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
        quad, fuzzy = ("exact_quad", "p6.3"), ("fuzzy_title", "p7.0")
        _event(conn, ids[0], merged_a, 1, *quad, "2026-11-03 10:00:00.000000")
        _event(conn, ids[1], merged_a, 2, *quad, "2026-11-16 02:00:00.000000")
        _event(conn, ids[2], merged_b, 3, *quad, "2026-11-15 23:00:00.000000-05:00")
        _event(conn, ids[3], merged_b, 4, *fuzzy, "2026-11-10 09:00:00.000000")
        _event(conn, ids[3], None, 4, *quad, "2026-11-10 09:00:00.000000")
        got = store_hygiene(conn, UNUSED, now=NOW)["grouping"]

    assert got["merges"] == 4
    assert got["merged_jobs"] == 2
    assert got["without_source_job"] == 1
    assert got["postings_approx"] == 4
    assert got["per_1000_postings"] == 1000.0
    assert got["methods"] == [
        {"method": "exact_quad", "algorithm_version": "p6.3", "count": 3},
        {"method": "fuzzy_title", "algorithm_version": "p7.0", "count": 1},
    ]
    assert [w["merges"] for w in got["weekly"]] == [0, 0, 0, 0, 0, 1, 1, 2]


def test_grouping_with_no_postings_has_no_rate(engine: Engine) -> None:
    with engine.begin() as conn:
        got = store_hygiene(conn, UNUSED, now=NOW)["grouping"]
    assert (got["merges"], got["postings_approx"], got["per_1000_postings"]) == (0, 0, None)


def test_store_size_is_the_database_plus_its_wal_and_says_growth_is_unrecorded(
    engine: Engine, tmp_path: Path
) -> None:
    db = tmp_path / "sized" / "boardwatch.db"
    db.parent.mkdir()
    db.write_bytes(b"x" * 1234)
    (db.parent / "boardwatch.db-wal").write_bytes(b"y" * 56)
    with engine.begin() as conn:
        got = store_hygiene(conn, db, now=NOW)["store"]
        assert got == {
            "db_bytes": 1234,
            "wal_bytes": 56,
            "total_bytes": 1290,
            "growth_recorded": False,
        }
        (db.parent / "boardwatch.db-wal").unlink()  # no WAL yet: zero, not an error
        assert store_hygiene(conn, db, now=NOW)["store"]["total_bytes"] == 1234


def test_sparse_and_deleting_tables_are_counted_exactly(engine: Engine) -> None:
    """25 jobs inserted and the first 20 deleted: 5 survive, highest rowid 25. One delivery adds
    1 row to each of jobs, posting_versions, postings, companies, artifacts, board_scans (it
    reuses an existing run).
    Three more posting_versions have ids 1001, 5000, 9000, each quarantined: the quarantine
    table has 3 rows but its highest rowid is 9000. 3 runs. Exact counts: jobs 5+1 = 6,
    posting_versions 1+3 = 4, quarantined_bodies 3, runs 3, then the one-row tables.
    The 3-way tie breaks by name (quarantined_bodies before runs). Ranked by highest rowid the quarantine
    would come first."""
    with engine.begin() as conn:
        for _ in range(25):
            conn.execute(insert(jobs).values(created_at=NOW))
        conn.execute(text("DELETE FROM jobs WHERE id <= 20"))
        for _ in range(3):
            conn.execute(insert(runs).values(started_at=NOW))
        posting, _ = _deliver(conn, "sparse", judge=False)
        for version_id in (1001, 5000, 9000):
            conn.execute(
                insert(posting_versions).values(
                    id=version_id,
                    posting_id=posting,
                    content_hash=f"s{version_id}",
                    body_text="body",
                    captured_at=NOW,
                    capture_reason="revised",
                )
            )
            conn.execute(
                text(
                    "INSERT INTO quarantined_bodies (posting_version_id, posting_id, markers_json,"
                    " catalog_version, quarantined_at) VALUES (:v, :p, '[]', 1, :q)"
                ),
                {"v": version_id, "p": posting, "q": NOW.isoformat()},
            )
        got = store_hygiene(conn, UNUSED, now=NOW)["tables"]
    assert "approximate" not in got
    assert got["rows"][:5] == [
        {"name": "jobs", "rows": 6, "exact": True},
        {"name": "posting_versions", "rows": 4, "exact": True},
        {"name": "quarantined_bodies", "rows": 3, "exact": True},
        {"name": "runs", "rows": 3, "exact": True},
        {"name": "alembic_version", "rows": 1, "exact": True},
    ]
    assert len(got["rows"]) == 10
    assert "sqlite_sequence" not in {r["name"] for r in got["rows"]}


def test_a_table_that_cannot_be_counted_in_time_falls_back_to_its_highest_rowid(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the count of `jobs` is made to time out: it reads its highest rowid (25) and is marked
    not exact, the other tables stay exact counts. The postings figure follows the same rule."""
    real = hygiene._scalar_within

    def timeout_on_jobs(conn: Connection, sql: str, budget: float) -> int | None:
        return None if 'FROM "jobs"' in sql else real(conn, sql, budget)

    monkeypatch.setattr(hygiene, "_scalar_within", timeout_on_jobs)
    with engine.begin() as conn:
        for _ in range(25):
            conn.execute(insert(jobs).values(created_at=NOW))
        conn.execute(text("DELETE FROM jobs WHERE id <= 20"))
        for _ in range(3):
            conn.execute(insert(runs).values(started_at=NOW))
        rows = {r["name"]: r for r in store_hygiene(conn, UNUSED, now=NOW)["tables"]["rows"]}
    assert rows["jobs"] == {"name": "jobs", "rows": 25, "exact": False}
    assert rows["runs"] == {"name": "runs", "rows": 3, "exact": True}


def test_a_statement_past_its_budget_is_interrupted_and_the_connection_survives(
    engine: Engine,
) -> None:
    endless = (
        "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) SELECT COUNT(*) FROM c"
    )
    with engine.begin() as conn:
        started = time.perf_counter()
        assert hygiene._scalar_within(conn, endless, 0.05) is None
        assert time.perf_counter() - started < 5
        assert hygiene._scalar_within(conn, "SELECT 7", 5) == 7  # not poisoned by the interrupt


def test_a_database_error_that_is_not_our_timeout_is_not_swallowed(engine: Engine) -> None:
    with engine.begin() as conn, pytest.raises(OperationalError):
        hygiene._scalar_within(conn, 'SELECT COUNT(*) FROM "no_such_table"', 5)
