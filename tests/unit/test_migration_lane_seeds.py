"""The `p_lane_seeds` migration: a new table for the discovering-lane -> resolving-lane handoff.

A CREATE TABLE carries none of the risk an ALTER on `runs` does — nothing references it, so
there is no child to orphan while alembic runs with `foreign_keys` OFF (D-269). What it CAN get
wrong is silent in a different way, and that is what is asserted here:

  * the migration and `store/tables.py` disagreeing. Two hand-written descriptions of one schema
    drift, and the drift only shows up as a runtime `OperationalError` on the first live run of
    whichever lane happens to touch the missing column. Compared column for column below,
    against the metadata's OWN compiled DDL rather than against a list retyped from it.
  * a UNIQUE that is not there. The whole provenance rule — first discoverer keeps the row —
    rests on it, and without it `on_conflict_do_nothing` has no conflict to do nothing about,
    so every re-listing inserts a duplicate and every duplicate is resolved and fetched again.
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, OperationalError

BASE = "p_runs_corpus_counts"  # the head this revision stacks on
HEAD = "p_lane_seeds"
MIGRATIONS = Path("src/boardwatch/store/migrations")


def _cfg(db_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def _columns(engine) -> list[tuple]:
    with engine.connect() as conn:
        return [
            (r[1], r[2], r[3])  # name, type, notnull
            for r in conn.execute(text("PRAGMA table_info(lane_seeds)"))
        ]


def _seed_run(engine, *, started_at: str) -> int:
    with engine.begin() as conn:
        return conn.execute(
            text(
                "INSERT INTO runs (started_at, status, boards_attempted) "
                "VALUES (:t, 'ok', 0) RETURNING id"
            ),
            {"t": started_at},
        ).scalar_one()


def test_the_table_does_not_exist_before_the_revision_and_does_after(tmp_path: Path) -> None:
    db = tmp_path / "step.db"
    cfg = _cfg(f"sqlite:///{db}")
    engine = create_engine(f"sqlite:///{db}")

    command.upgrade(cfg, BASE)
    with engine.connect() as conn:
        with pytest.raises(OperationalError):
            conn.execute(text("SELECT id FROM lane_seeds"))

    command.upgrade(cfg, HEAD)

    # Pinned as LITERALS, not by importing the table the implementation uses — an assertion
    # against the shared constant would pass however wrong both halves were together.
    assert _columns(engine) == [
        ("id", "INTEGER", 1),
        ("url", "TEXT", 1),
        ("discovered_by", "TEXT", 1),
        ("first_seen_run_id", "INTEGER", 1),
        ("first_seen_at", "DATETIME", 1),
        ("attempts", "INTEGER", 1),
        ("last_attempt_run_id", "INTEGER", 0),
        ("last_attempt_at", "DATETIME", 0),
        ("resolved_at", "DATETIME", 0),
    ]


def test_the_migration_and_the_metadata_describe_the_same_table(tmp_path: Path) -> None:
    """Two hand-written descriptions of one schema drift, and the drift is invisible until a
    live run hits the column that is missing on whichever side was not edited."""
    from sqlalchemy.dialects import sqlite
    from sqlalchemy.schema import CreateTable

    from boardwatch.store.tables import lane_seeds

    migrated = tmp_path / "migrated.db"
    command.upgrade(_cfg(f"sqlite:///{migrated}"), HEAD)
    engine = create_engine(f"sqlite:///{migrated}")
    with engine.connect() as conn:
        actual = conn.execute(
            text("SELECT sql FROM sqlite_master WHERE name = 'lane_seeds'")
        ).scalar_one()

    def normalise(ddl: str) -> str:
        return " ".join(ddl.replace("\n", " ").replace("\t", " ").split())

    expected = normalise(str(CreateTable(lane_seeds).compile(dialect=sqlite.dialect())))
    assert normalise(actual) == expected


def test_the_unique_on_url_is_real(tmp_path: Path) -> None:
    """Without it the provenance rule has nothing to stand on: every re-listing inserts a
    duplicate, and every duplicate is separately attempted, resolved and fetched."""
    db = tmp_path / "unique.db"
    cfg = _cfg(f"sqlite:///{db}")
    engine = create_engine(f"sqlite:///{db}")
    command.upgrade(cfg, HEAD)
    run_id = _seed_run(engine, started_at="2026-09-02 00:00:00")

    insert = text(
        "INSERT INTO lane_seeds (url, discovered_by, first_seen_run_id, first_seen_at) "
        "VALUES ('https://x.test/a', :who, :run, '2026-09-02 00:00:00')"
    )
    with engine.begin() as conn:
        conn.execute(insert, {"who": "github_lists", "run": run_id})
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(insert, {"who": "indeed", "run": run_id})


def test_the_downgrade_drops_the_table_and_keeps_the_run(tmp_path: Path) -> None:
    """A rollback loses the seed backlog, which the pre-migration schema cannot express. What it
    must NOT lose is the `runs` rows the table pointed at."""
    db = tmp_path / "down.db"
    cfg = _cfg(f"sqlite:///{db}")
    engine = create_engine(f"sqlite:///{db}")
    command.upgrade(cfg, HEAD)
    run_id = _seed_run(engine, started_at="2026-09-02 00:00:00")
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO lane_seeds (url, discovered_by, first_seen_run_id, first_seen_at) "
                "VALUES ('https://x.test/a', 'indeed', :run, '2026-09-02 00:00:00')"
            ),
            {"run": run_id},
        )

    command.downgrade(cfg, BASE)

    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM runs")).scalar_one() == 1
        assert [tuple(r) for r in conn.execute(text("PRAGMA foreign_key_check"))] == []
        with pytest.raises(OperationalError):
            conn.execute(text("SELECT id FROM lane_seeds"))

    command.upgrade(cfg, HEAD)  # and the round trip re-creates it, empty
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM lane_seeds")).scalar_one() == 0
