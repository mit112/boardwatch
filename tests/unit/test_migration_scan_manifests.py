"""T353 migration: `scan_manifests` is created on a store at the prior head, and runs from before
it have no manifest, so `--continue-scan` can never pick one of them up."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

BASE = "p_head_shadow"
HEAD = "p_scan_manifests"
MIGRATIONS = Path("src/boardwatch/store/migrations")


def _cfg(db: Path) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    return cfg


def test_a_store_at_the_prior_head_gains_an_empty_manifest_table(tmp_path: Path) -> None:
    db = tmp_path / "step.db"
    engine = create_engine(f"sqlite:///{db}")
    command.upgrade(_cfg(db), BASE)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO runs (id, started_at, boards_attempted) "
                          "VALUES (1, '2026-01-01', 1)"))
    assert "scan_manifests" not in inspect(engine).get_table_names()

    command.upgrade(_cfg(db), HEAD)

    columns = {c["name"] for c in inspect(engine).get_columns("scan_manifests")}
    assert columns == {"run_id", "manifest_json", "scan_finalized_at"}
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM scan_manifests")).scalar_one() == 0
        assert conn.execute(text("SELECT COUNT(*) FROM runs")).scalar_one() == 1


def test_the_downgrade_drops_the_table(tmp_path: Path) -> None:
    db = tmp_path / "round.db"
    engine = create_engine(f"sqlite:///{db}")
    command.upgrade(_cfg(db), HEAD)
    command.downgrade(_cfg(db), BASE)
    assert "scan_manifests" not in inspect(engine).get_table_names()
