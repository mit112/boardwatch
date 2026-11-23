"""T334 migration: `board_scans` gains the nullable `empty_guarded`.

Stepped from the prior revision with a seeded row (a down/up round trip would drop the column and
prove nothing about the backfill), and a retry on an already-migrated store must not fail.
Nothing is inferred for the old rows: a scan that was in fact guarded before the column existed
reads NULL, which is not evidence, so a board's guarded streak starts after the migration.
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError

BASE = "p_quarantine_last_drained"
HEAD = "p_empty_guarded"
MIGRATIONS = Path("src/boardwatch/store/migrations")


def _cfg(db: Path) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    return cfg


def _seed_scan(engine) -> None:  # type: ignore[no-untyped-def]
    """A `complete` scan listing 0 for a board: exactly the row the guard's own would look like."""
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO runs (id, started_at, boards_attempted) "
                          "VALUES (1, '2026-01-01', 1)"))
        conn.execute(text("INSERT INTO companies (id, name, provider, slug, source, watched) "
                          "VALUES (1, 'Acme', 'lever', 'acme', 'user', 1)"))
        conn.execute(text("INSERT INTO board_scans (id, run_id, company_id, started_at, "
                          "finished_at, status, postings_listed, pipeline_scan) VALUES "
                          "(1, 1, 1, '2026-01-01', '2026-01-01', 'complete', 0, 1)"))


def _columns(engine) -> list[str]:  # type: ignore[no-untyped-def]
    return [c["name"] for c in inspect(engine).get_columns("board_scans")]


def test_a_row_seeded_at_the_prior_revision_steps_forward_with_a_null_flag(
    tmp_path: Path,
) -> None:
    db = tmp_path / "step.db"
    engine = create_engine(f"sqlite:///{db}")
    command.upgrade(_cfg(db), BASE)
    _seed_scan(engine)
    assert "empty_guarded" not in _columns(engine)
    with pytest.raises(OperationalError), engine.connect() as conn:
        conn.execute(text("SELECT empty_guarded FROM board_scans"))

    command.upgrade(_cfg(db), HEAD)

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT status, postings_listed, pipeline_scan, empty_guarded FROM board_scans")
        ).one()
        assert conn.execute(text("PRAGMA foreign_key_check")).all() == []
    # `postings_listed = 0` on a pipeline scan is NOT turned into a guarded scan.
    assert tuple(row) == ("complete", 0, 1, None)


def test_the_upgrade_is_safe_to_retry_and_the_downgrade_keeps_the_row(tmp_path: Path) -> None:
    db = tmp_path / "down.db"
    engine = create_engine(f"sqlite:///{db}")
    command.upgrade(_cfg(db), HEAD)
    _seed_scan(engine)

    # A retry after a half-applied run: the column exists but the revision is not stamped.
    command.stamp(_cfg(db), BASE)
    command.upgrade(_cfg(db), HEAD)
    assert "empty_guarded" in _columns(engine)

    command.downgrade(_cfg(db), BASE)
    assert "empty_guarded" not in _columns(engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM board_scans")).scalar_one() == 1
        assert conn.execute(text("PRAGMA foreign_key_check")).all() == []
