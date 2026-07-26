"""P0 posting_versions migration: honest backfill (revised-event vs original) + immutability."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

BASE = "p0_job_grouping"
HEAD = "p0_posting_versions"
MIGRATIONS = Path("src/boardwatch/store/migrations")


def _cfg(db_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def _seed(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO companies (name, provider, slug, source, watched) "
                          "VALUES ('Acme','greenhouse','acme','user',1)"))
        conn.execute(text("INSERT INTO runs (started_at, boards_attempted) "
                          "VALUES ('2026-01-01 00:00:00', 1)"))
        conn.execute(text("INSERT INTO jobs (created_at) VALUES ('2026-01-01 00:00:00')"))
        conn.execute(text("INSERT INTO jobs (created_at) VALUES ('2026-01-01 00:00:00')"))
        # posting 1: revised once -> body appeared at the revised event time
        conn.execute(text(
            "INSERT INTO postings (company_id, job_id, provider_posting_id, title, normalized_title, "
            "remote_policy, first_seen_at, last_seen_at, status, consecutive_missing, content_hash, "
            "body_text) VALUES (1,1,'p-1','E','e','unknown','2026-01-01 00:00:00',"
            "'2026-03-01 00:00:00','open',0,'h1b','body current')"))
        conn.execute(text("INSERT INTO posting_events (posting_id, kind, run_id, created_at) "
                          "VALUES (1,'new',1,'2026-01-01 00:00:00')"))
        conn.execute(text("INSERT INTO posting_events (posting_id, kind, run_id, created_at) "
                          "VALUES (1,'revised',1,'2026-02-15 00:00:00')"))
        # posting 2: never revised -> body dates to first_seen
        conn.execute(text(
            "INSERT INTO postings (company_id, job_id, provider_posting_id, title, normalized_title, "
            "remote_policy, first_seen_at, last_seen_at, status, consecutive_missing, content_hash, "
            "body_text) VALUES (1,2,'p-2','F','f','unknown','2026-01-05 00:00:00',"
            "'2026-01-05 00:00:00','open',0,'h2','body two')"))
        conn.execute(text("INSERT INTO posting_events (posting_id, kind, run_id, created_at) "
                          "VALUES (2,'new',1,'2026-01-05 00:00:00')"))


def test_posting_versions_round_trip(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'rt.db'}"
    cfg = _cfg(url)
    engine = create_engine(url)

    command.upgrade(cfg, BASE)
    _seed(engine)

    command.upgrade(cfg, HEAD)
    with engine.begin() as conn:
        v1 = conn.execute(text("SELECT captured_at, capture_reason, run_id FROM posting_versions "
                               "WHERE posting_id=1")).one()
        v2 = conn.execute(text("SELECT captured_at, capture_reason FROM posting_versions "
                               "WHERE posting_id=2")).one()
        assert v1.captured_at == "2026-02-15 00:00:00"        # honest: latest revised event
        assert v1.capture_reason == "backfill_from_revised_event"
        assert v1.run_id is None
        assert v2.captured_at == "2026-01-05 00:00:00"        # honest: original -> first_seen
        assert v2.capture_reason == "backfill_original"
        with pytest.raises(IntegrityError):                   # immutable
            conn.execute(text("UPDATE posting_versions SET body_text='x' WHERE posting_id=1"))
        with pytest.raises(IntegrityError):
            conn.execute(text("DELETE FROM posting_versions WHERE posting_id=1"))

    command.downgrade(cfg, BASE)
    with engine.begin() as conn:
        names = {r[0] for r in conn.execute(
            text("SELECT name FROM sqlite_master WHERE type IN ('table','trigger','index')")).all()}
        assert conn.execute(text("PRAGMA foreign_key_check")).all() == []
    assert "posting_versions" not in names
    assert "posting_versions_no_update" not in names
    assert "ix_posting_versions_posting_captured" not in names
