"""T340 shadow migration: `board_scans` gains `listing_pages`, `head_pages`, `head_missed`.

Stepped from the prior revision with a seeded row (a down/up round trip would drop the columns and
prove nothing about the old rows), and a retry on an already-migrated store must not fail. Old rows
read NULL: the provider computed nothing for them, which is not a zero.
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError

BASE = "p_empty_guarded"
HEAD = "p_head_shadow"
SHADOW = ("listing_pages", "head_pages", "head_missed")
MIGRATIONS = Path("src/boardwatch/store/migrations")


def _cfg(db: Path) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    return cfg


def _seed_scan(engine) -> None:  # type: ignore[no-untyped-def]
    """One scan row written before the shadow columns existed."""
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


def test_a_row_seeded_at_the_prior_revision_steps_forward_with_null_shadow(tmp_path: Path) -> None:
    db = tmp_path / "step.db"
    engine = create_engine(f"sqlite:///{db}")
    command.upgrade(_cfg(db), BASE)
    _seed_scan(engine)
    assert not set(SHADOW) & set(_columns(engine))
    with pytest.raises(OperationalError), engine.connect() as conn:
        conn.execute(text("SELECT head_pages FROM board_scans"))

    command.upgrade(_cfg(db), HEAD)

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT status, listing_pages, head_pages, head_missed FROM board_scans")
        ).one()
    assert tuple(row) == ("complete", None, None, None)


def test_the_upgrade_is_safe_to_retry_and_the_downgrade_keeps_the_row(tmp_path: Path) -> None:
    db = tmp_path / "down.db"
    engine = create_engine(f"sqlite:///{db}")
    command.upgrade(_cfg(db), HEAD)
    _seed_scan(engine)

    command.stamp(_cfg(db), BASE)  # a retry after a half-applied run
    command.upgrade(_cfg(db), HEAD)
    assert set(SHADOW) <= set(_columns(engine))

    command.downgrade(_cfg(db), BASE)
    assert not set(SHADOW) & set(_columns(engine))
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM board_scans")).scalar_one() == 1
