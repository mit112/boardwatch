"""P0 eligibility ledger migration: profile-inclusive inputs, deterministic partial-unique,
LLM reruns allowed, immutability, clean downgrade."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, OperationalError

BASE = "p0_version_sources"
HEAD = "p0_eligibility"
MIGRATIONS = Path("src/boardwatch/store/migrations")


def _cfg(db_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def _seed_version(conn) -> None:
    conn.execute(text("INSERT INTO companies (name, provider, slug, source, watched) "
                      "VALUES ('Acme','greenhouse','acme','user',1)"))
    conn.execute(text("INSERT INTO jobs (created_at) VALUES ('2026-01-01 00:00:00')"))
    conn.execute(text(
        "INSERT INTO postings (company_id, job_id, provider_posting_id, title, normalized_title, "
        "remote_policy, first_seen_at, last_seen_at, status, consecutive_missing, content_hash, "
        "body_text) VALUES (1,1,'p-1','E','e','unknown','2026-01-01 00:00:00',"
        "'2026-01-01 00:00:00','open',0,'h1','b1')"))
    conn.execute(text(
        "INSERT INTO posting_versions (posting_id, content_hash, body_text, captured_at, run_id, "
        "capture_reason) VALUES (1,'h1','b1','2026-01-01 00:00:00',NULL,'new')"))
    conn.execute(text(
        "INSERT INTO eligibility_inputs (posting_version_id, profile_hash, profile_snapshot_json, "
        "rules_hash, rules_snapshot_json, input_fingerprint, created_at) "
        "VALUES (1,'pf','{}','rl','{}','fp1','2026-01-02 00:00:00')"))


def test_eligibility_round_trip(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'rt.db'}"
    cfg = _cfg(url)
    engine = create_engine(url)

    command.upgrade(cfg, HEAD)
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        _seed_version(conn)
        conn.execute(text("INSERT INTO eligibility_evaluations (input_id, engine_kind, "
                          "engine_version, verdict, score, created_at) VALUES "
                          "(1,'deterministic','1','eligible',1.0,'2026-01-02 00:00:00')"))
        # deterministic partial-unique blocks a second (input, engine_version)
        with pytest.raises(IntegrityError):
            conn.execute(text("INSERT INTO eligibility_evaluations (input_id, engine_kind, "
                              "engine_version, verdict, score, created_at) VALUES "
                              "(1,'deterministic','1','ineligible',0.0,'2026-01-03 00:00:00')"))
        # LLM reruns of the same input/version are allowed
        conn.execute(text("INSERT INTO eligibility_evaluations (input_id, engine_kind, "
                          "engine_version, verdict, score, created_at) VALUES "
                          "(1,'llm','1','uncertain',0.5,'2026-01-03 00:00:00')"))
        conn.execute(text("INSERT INTO eligibility_evaluations (input_id, engine_kind, "
                          "engine_version, verdict, score, created_at) VALUES "
                          "(1,'llm','1','eligible',0.9,'2026-01-04 00:00:00')"))
        # score range CHECK
        with pytest.raises(IntegrityError):
            conn.execute(text("INSERT INTO eligibility_evaluations (input_id, engine_kind, "
                              "engine_version, verdict, score, created_at) VALUES "
                              "(1,'llm','1','eligible',9.0,'2026-01-05 00:00:00')"))
        # immutable
        with pytest.raises(IntegrityError):
            conn.execute(text("UPDATE eligibility_evaluations SET verdict='eligible' WHERE id=1"))

    command.downgrade(cfg, BASE)
    with engine.begin() as conn:
        names = {r[0] for r in conn.execute(
            text("SELECT name FROM sqlite_master WHERE type IN ('table','trigger','index')")).all()}
        assert conn.execute(text("PRAGMA foreign_key_check")).all() == []
    assert "eligibility_evaluations" not in names
    assert "uq_eligibility_deterministic" not in names
    with engine.connect() as conn, pytest.raises(OperationalError):
        conn.execute(text("SELECT 1 FROM eligibility_inputs"))
