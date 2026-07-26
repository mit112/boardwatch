"""P0 applications migration: attempt_no uniqueness, immutable events, clean downgrade."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, OperationalError

BASE = "p0_eligibility"
HEAD = "p0_applications"
MIGRATIONS = Path("src/boardwatch/store/migrations")


def _cfg(db_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_applications_round_trip(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'rt.db'}"
    cfg = _cfg(url)
    engine = create_engine(url)

    command.upgrade(cfg, HEAD)
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.execute(text("INSERT INTO jobs (created_at) VALUES ('2026-01-01 00:00:00')"))
        conn.execute(text("INSERT INTO applications (job_id, attempt_no, status, created_at, "
                          "updated_at) VALUES (1,1,'interested','2026-01-01 00:00:00',"
                          "'2026-01-01 00:00:00')"))
        conn.execute(text("INSERT INTO application_events (application_id, event_type, to_status, "
                          "occurred_at, recorded_at, source) VALUES "
                          "(1,'created','interested','2026-01-01 00:00:00','2026-01-01 00:00:00','user')"))
        with pytest.raises(IntegrityError):    # UNIQUE(job_id, attempt_no)
            conn.execute(text("INSERT INTO applications (job_id, attempt_no, status, created_at, "
                              "updated_at) VALUES (1,1,'applied','2026-01-02 00:00:00',"
                              "'2026-01-02 00:00:00')"))
        with pytest.raises(IntegrityError):    # events immutable
            conn.execute(text("DELETE FROM application_events WHERE id=1"))

    command.downgrade(cfg, BASE)
    with engine.begin() as conn:
        names = {r[0] for r in conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type IN ('table','trigger','index')")).all()}
        assert conn.execute(text("PRAGMA foreign_key_check")).all() == []
    assert "applications" not in names
    assert "application_events" not in names
    assert "application_events_no_update" not in names
    assert "application_events_no_delete" not in names
    assert "ix_application_events_application_id" not in names
    with engine.connect() as conn, pytest.raises(OperationalError):
        conn.execute(text("SELECT 1 FROM applications"))
