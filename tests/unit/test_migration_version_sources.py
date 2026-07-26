"""P0 posting_version_sources migration: FK-enforced, immutable, insertable at head."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, OperationalError

BASE = "p0_posting_versions"
HEAD = "p0_version_sources"
MIGRATIONS = Path("src/boardwatch/store/migrations")


def _cfg(db_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_version_sources_round_trip(tmp_path: Path) -> None:
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
            "INSERT INTO postings (company_id, job_id, provider_posting_id, title, normalized_title, "
            "remote_policy, first_seen_at, last_seen_at, status, consecutive_missing, content_hash, "
            "body_text) VALUES (1,1,'p-1','E','e','unknown','2026-01-01 00:00:00',"
            "'2026-01-01 00:00:00','open',0,'h1','b1')"))
        conn.execute(text(
            "INSERT INTO posting_versions (posting_id, content_hash, body_text, captured_at, "
            "run_id, capture_reason) VALUES (1,'h1','b1','2026-01-01 00:00:00',NULL,'new')"))
        conn.execute(text(
            "INSERT INTO posting_version_sources (posting_version_id, source_url, source_record_id, "
            "observed_at, payload_hash) VALUES (1,'https://boards/acme','p-1','2026-01-01 00:00:00','h1')"))
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        assert conn.execute(text("SELECT source_url FROM posting_version_sources")).scalar_one() \
            == "https://boards/acme"
        with pytest.raises(IntegrityError):     # FK: dangling version
            conn.execute(text("INSERT INTO posting_version_sources (posting_version_id, source_url, "
                              "source_record_id, observed_at) VALUES (999,'u','r','2026-01-01 00:00:00')"))
        with pytest.raises(IntegrityError):     # immutable
            conn.execute(text("UPDATE posting_version_sources SET source_url='x' WHERE posting_version_id=1"))

    command.downgrade(cfg, BASE)
    with engine.begin() as conn:
        names = {r[0] for r in conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type IN ('table','trigger','index')")).all()}
        assert conn.execute(text("PRAGMA foreign_key_check")).all() == []
    assert "posting_version_sources" not in names
    assert "posting_version_sources_no_update" not in names
    assert "posting_version_sources_no_delete" not in names
    with engine.connect() as conn, pytest.raises(OperationalError):
        conn.execute(text("SELECT 1 FROM posting_version_sources"))
