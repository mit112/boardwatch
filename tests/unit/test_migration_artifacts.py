"""P0 artifacts migration: lineage FKs, immutable derivations, clean downgrade."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, OperationalError

BASE = "p0_applications"
HEAD = "p0_artifacts"
MIGRATIONS = Path("src/boardwatch/store/migrations")


def _cfg(db_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_artifacts_round_trip(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'rt.db'}"
    cfg = _cfg(url)
    engine = create_engine(url)

    command.upgrade(cfg, HEAD)
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.execute(text("INSERT INTO artifacts (kind, uri, created_at) "
                          "VALUES ('export','/e/all.jsonl','2026-01-01 00:00:00')"))
        conn.execute(text("INSERT INTO artifacts (kind, uri, created_at) "
                          "VALUES ('resume','/r/base.pdf','2026-01-01 00:00:00')"))
        conn.execute(text("INSERT INTO artifact_derivations (artifact_id, parent_artifact_id, "
                          "relation, created_at) VALUES (2,1,'tailored_from','2026-01-01 00:00:00')"))
        with pytest.raises(IntegrityError):    # FK: dangling parent
            conn.execute(text("INSERT INTO artifact_derivations (artifact_id, parent_artifact_id, "
                              "relation, created_at) VALUES (2,999,'x','2026-01-01 00:00:00')"))
        with pytest.raises(IntegrityError):    # derivations immutable
            conn.execute(text("UPDATE artifact_derivations SET relation='y' WHERE artifact_id=2"))

    command.downgrade(cfg, BASE)
    with engine.begin() as conn:
        names = {r[0] for r in conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type IN ('table','trigger','index')")).all()}
        assert conn.execute(text("PRAGMA foreign_key_check")).all() == []
    assert "artifacts" not in names
    assert "artifact_derivations" not in names
    assert "artifact_derivations_no_update" not in names
    assert "artifact_derivations_no_delete" not in names
    assert "ix_artifacts_job_id" not in names
    with engine.connect() as conn, pytest.raises(OperationalError):
        conn.execute(text("SELECT 1 FROM artifacts"))
