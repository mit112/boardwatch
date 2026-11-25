"""T355 migration: `http_cache` gains a nullable `gate_key`.

Stepped from the prior revision with a seeded validator: the old row reads NULL, which a gating
provider never reuses (one full read, then rewritten with its key). A retry on a migrated store
must not fail.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

BASE = "p_scan_manifests"
HEAD = "p_http_cache_gate_key"
MIGRATIONS = Path("src/boardwatch/store/migrations")


def _cfg(db: Path) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    return cfg


def test_a_validator_stored_before_the_column_reads_null(tmp_path: Path) -> None:
    db = tmp_path / "step.db"
    engine = create_engine(f"sqlite:///{db}")
    command.upgrade(_cfg(db), BASE)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO http_cache (url, etag, fetched_at, status) "
                          "VALUES ('https://x.test/l', '\"v1\"', '2026-01-01', 200)"))

    command.upgrade(_cfg(db), HEAD)

    with engine.connect() as conn:
        row = conn.execute(text("SELECT etag, gate_key FROM http_cache")).one()
    assert tuple(row) == ('"v1"', None)


def test_a_retry_and_a_round_trip_succeed(tmp_path: Path) -> None:
    db = tmp_path / "round.db"
    engine = create_engine(f"sqlite:///{db}")

    def columns() -> list[str]:
        with engine.connect() as conn:
            return [r[1] for r in conn.execute(text("PRAGMA table_info(http_cache)"))]

    command.upgrade(_cfg(db), HEAD)
    command.downgrade(_cfg(db), BASE)
    assert "gate_key" not in columns()
    command.upgrade(_cfg(db), HEAD)
    assert "gate_key" in columns()
