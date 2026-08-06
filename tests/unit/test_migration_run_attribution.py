"""Run-attribution migration round-trip.

Two additive nullable run_id columns, no table rebuild. The load-bearing assertions are that
the *unnamed* inline REFERENCES still enforces under PRAGMA foreign_keys=ON (SQLite cannot add
a named table-level constraint after the fact, so the FK had to be added inline), that
pre-existing rows read NULL rather than 0, and that adding the column did not disturb the
append-only triggers on eligibility_evaluations.
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

BASE = "p2_profile_eligibility"
HEAD = "run_attribution"
MIGRATIONS = Path("src/boardwatch/store/migrations")


def _cfg(db_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def _seed(conn) -> None:
    """A run, plus the posting->version->input chain an evaluation needs, plus an artifact."""
    conn.execute(text(
        "INSERT INTO runs (started_at, boards_attempted) VALUES ('2026-01-01 00:00:00', 1)"))
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
        "capture_reason) VALUES (1,'h1','b1','2026-01-01 00:00:00',1,'new')"))
    conn.execute(text(
        "INSERT INTO eligibility_inputs (posting_version_id, profile_hash, profile_snapshot_json, "
        "rules_hash, rules_snapshot_json, input_fingerprint, created_at) "
        "VALUES (1,'pf','{}','rl','{}','fp1','2026-01-02 00:00:00')"))
    conn.execute(text("INSERT INTO eligibility_evaluations (input_id, engine_kind, engine_version, "
                      "verdict, score, created_at) VALUES "
                      "(1,'deterministic','1','eligible',1.0,'2026-01-02 00:00:00')"))
    conn.execute(text("INSERT INTO artifacts (kind, uri, created_at) "
                      "VALUES ('resume','/r/base.pdf','2026-01-01 00:00:00')"))


def test_run_attribution_round_trip(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'rt.db'}"
    cfg = _cfg(url)
    engine = create_engine(url)

    command.upgrade(cfg, BASE)
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        _seed(conn)

    command.upgrade(cfg, HEAD)
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        for table in ("eligibility_evaluations", "artifacts"):
            cols = {r[1] for r in conn.execute(text(f"PRAGMA table_info({table})")).all()}
            assert "run_id" in cols, table

        # Rows written before the migration read NULL, not 0. The two are different claims:
        # NULL means "predates attribution", 0 would be a run id that does not exist.
        assert conn.execute(text(
            "SELECT run_id FROM eligibility_evaluations WHERE id = 1")).scalar_one() is None
        assert conn.execute(text(
            "SELECT run_id FROM artifacts WHERE id = 1")).scalar_one() is None

        # The inline (unnamed) REFERENCES still enforces.
        with pytest.raises(IntegrityError):
            conn.execute(text("INSERT INTO eligibility_evaluations (input_id, engine_kind, "
                              "engine_version, verdict, score, created_at, run_id) VALUES "
                              "(1,'llm','1','uncertain',0.5,'2026-01-03 00:00:00',999)"))
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        with pytest.raises(IntegrityError):
            conn.execute(text("INSERT INTO artifacts (kind, uri, created_at, run_id) "
                              "VALUES ('resume','/r/x.pdf','2026-01-01 00:00:00',999)"))

    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        # A real run id is accepted on both tables.
        conn.execute(text("INSERT INTO eligibility_evaluations (input_id, engine_kind, "
                          "engine_version, verdict, score, created_at, run_id) VALUES "
                          "(1,'llm','1','uncertain',0.5,'2026-01-03 00:00:00',1)"))
        conn.execute(text("INSERT INTO artifacts (kind, uri, created_at, run_id) "
                          "VALUES ('resume','/r/tailored.pdf','2026-01-01 00:00:00',1)"))
        assert conn.execute(text(
            "SELECT run_id FROM eligibility_evaluations WHERE engine_kind = 'llm'"
        )).scalar_one() == 1

        # Adding the column did not disturb append-only, so run_id can never be backfilled
        # here — it is set at INSERT or it stays NULL forever.
        with pytest.raises(IntegrityError):
            conn.execute(text("UPDATE eligibility_evaluations SET run_id = 1 WHERE id = 1"))

    command.downgrade(cfg, BASE)
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        for table in ("eligibility_evaluations", "artifacts"):
            cols = {r[1] for r in conn.execute(text(f"PRAGMA table_info({table})")).all()}
            assert "run_id" not in cols, table
        # the pre-existing rows survive the round trip
        assert conn.execute(text(
            "SELECT verdict FROM eligibility_evaluations WHERE id = 1")).scalar_one() == "eligible"
        assert conn.execute(text(
            "SELECT uri FROM artifacts WHERE id = 1")).scalar_one() == "/r/base.pdf"
        assert conn.execute(text("PRAGMA foreign_key_check")).all() == []
