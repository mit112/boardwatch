"""P0 job_grouping_events migration: append-only annotate-only regroup ledger.
Insertable + immutable at head; gone after downgrade."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

BASE = "p0_jobs_anchor"
HEAD = "p0_job_grouping"
MIGRATIONS = Path("src/boardwatch/store/migrations")


def _cfg(db_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_job_grouping_round_trip(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'rt.db'}"
    cfg = _cfg(url)
    engine = create_engine(url)

    command.upgrade(cfg, HEAD)
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.execute(text("INSERT INTO companies (name, provider, slug, source, watched) "
                          "VALUES ('Acme','greenhouse','acme','user',1)"))
        conn.execute(text("INSERT INTO jobs (created_at) VALUES ('2026-01-01 00:00:00')"))
        conn.execute(text(
            "INSERT INTO postings (company_id, job_id, provider_posting_id, title, "
            "normalized_title, remote_policy, first_seen_at, last_seen_at, status, "
            "consecutive_missing, content_hash, body_text) VALUES "
            "(1,1,'p-1','E','e','unknown','2026-01-01 00:00:00','2026-01-01 00:00:00',"
            "'open',0,'h1','b1')"))
        conn.execute(text(
            "INSERT INTO job_grouping_events (posting_id, from_job_id, to_job_id, method, "
            "algorithm_version, created_at) VALUES (1, NULL, 1, 'initial', 'v0', "
            "'2026-01-01 00:00:00')"))
    with engine.begin() as conn:
        assert conn.execute(text("SELECT method FROM job_grouping_events")).scalar_one() == "initial"
        with pytest.raises(IntegrityError):  # immutable: no UPDATE
            conn.execute(text("UPDATE job_grouping_events SET method='x' WHERE id=1"))
        with pytest.raises(IntegrityError):  # immutable: no DELETE
            conn.execute(text("DELETE FROM job_grouping_events WHERE id=1"))

    command.downgrade(cfg, BASE)
    with engine.connect() as conn:
        names = {r[0] for r in conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type IN ('table','trigger','index')")).all()}
        fk = conn.execute(text("PRAGMA foreign_key_check")).all()
    assert "job_grouping_events" not in names
    assert "job_grouping_events_no_update" not in names
    assert "job_grouping_events_no_delete" not in names
    assert "ix_job_grouping_events_posting_id" not in names
    assert fk == []
