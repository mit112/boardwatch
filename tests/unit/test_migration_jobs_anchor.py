"""P0 jobs-anchor migration round-trip: real FK + NOT-NULL triggers + 1:1 backfill,
proven on a populated DB with child rows (posting_events) and a clean
PRAGMA foreign_key_check after downgrade."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

BASE = "b7e41c0a9f23"
HEAD = "p0_jobs_anchor"
MIGRATIONS = Path("src/boardwatch/store/migrations")


def _cfg(db_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def _seed(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.execute(text("INSERT INTO companies (name, provider, slug, source, watched) "
                          "VALUES ('Acme','greenhouse','acme','user',1)"))
        conn.execute(text("INSERT INTO runs (started_at, boards_attempted) "
                          "VALUES ('2026-01-01 00:00:00', 1)"))
        conn.execute(text(
            "INSERT INTO postings (company_id, provider_posting_id, title, normalized_title, "
            "remote_policy, first_seen_at, last_seen_at, status, consecutive_missing, "
            "content_hash, body_text) VALUES "
            "(1,'p-1','Eng','eng','unknown','2026-01-01 00:00:00','2026-01-01 00:00:00',"
            "'open',0,'h1','body one')"))
        conn.execute(text("INSERT INTO posting_events (posting_id, kind, run_id, created_at) "
                          "VALUES (1,'new',1,'2026-01-01 00:00:00')"))


def test_jobs_anchor_round_trip(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'rt.db'}"
    cfg = _cfg(url)
    engine = create_engine(url)

    command.upgrade(cfg, BASE)
    _seed(engine)

    command.upgrade(cfg, HEAD)
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        jobs = conn.execute(text("SELECT id, created_at FROM jobs")).all()
        job_id = conn.execute(text("SELECT job_id FROM postings WHERE id=1")).scalar_one()
        assert len(jobs) == 1
        assert jobs[0].created_at == "2026-01-01 00:00:00"   # dated to first_seen_at
        assert job_id == jobs[0].id                          # 1:1 anchored
        # NOT-NULL trigger rejects a job-less insert
        with pytest.raises(IntegrityError):
            conn.execute(text(
                "INSERT INTO postings (company_id, provider_posting_id, title, normalized_title, "
                "remote_policy, first_seen_at, last_seen_at, status, consecutive_missing, "
                "content_hash, body_text) VALUES "
                "(1,'p-2','E2','e2','unknown','2026-01-02 00:00:00','2026-01-02 00:00:00',"
                "'open',0,'h2','b2')"))
        # real FK rejects a dangling job_id
        with pytest.raises(IntegrityError):
            conn.execute(text("UPDATE postings SET job_id=999 WHERE id=1"))

    command.downgrade(cfg, BASE)
    with engine.begin() as conn:
        cols = {r[1] for r in conn.execute(text("PRAGMA table_info(postings)")).all()}
        names = {r[0] for r in conn.execute(
            text("SELECT name FROM sqlite_master WHERE type IN ('table','trigger')")).all()}
        assert conn.execute(text("SELECT body_text FROM postings WHERE id=1")).scalar_one() == "body one"
        assert conn.execute(text("SELECT COUNT(*) FROM posting_events")).scalar_one() == 1
        fk = conn.execute(text("PRAGMA foreign_key_check")).all()
    assert "job_id" not in cols
    assert "jobs" not in names
    assert "postings_job_required_insert" not in names
    assert fk == []  # no dangling references after downgrade
