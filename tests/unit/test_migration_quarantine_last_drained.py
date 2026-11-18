"""T319 migration: `quarantined_bodies` gains the nullable `last_drained_at`.

Stepped from the prior revision with a seeded row (a down/up round trip would drop the column
and prove nothing about the backfill), and a retry on an already-migrated store must not fail.
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError

BASE = "p_board_scans_status_index"
HEAD = "p_quarantine_last_drained"
MIGRATIONS = Path("src/boardwatch/store/migrations")


def _cfg(db: Path) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    return cfg


def _seed_held_row(engine) -> None:  # type: ignore[no-untyped-def]
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO companies (name, provider, slug, source, watched)"
            " VALUES ('Acme', 'greenhouse', 'acme', 'lane', 0)"
        ))
        job = conn.execute(
            text("INSERT INTO jobs (created_at) VALUES ('2026-01-01 00:00:00') RETURNING id")
        ).scalar_one()
        conn.execute(text(
            "INSERT INTO postings (company_id, job_id, provider_posting_id, title,"
            " normalized_title, url, remote_policy, first_seen_at, last_seen_at, status,"
            " consecutive_missing, content_hash, body_text) VALUES (1, :j, 'p', 't', 't',"
            " 'https://x.test/1', 'remote', '2026-01-01', '2026-01-01', 'open', 0, 'h', 'b')"
        ), {"j": job})
        conn.execute(text(
            "INSERT INTO posting_versions (posting_id, content_hash, body_text, captured_at,"
            " capture_reason) VALUES (1, 'h', 'b', '2026-01-01', 'revised')"
        ))
        conn.execute(text(
            "INSERT INTO quarantined_bodies (posting_version_id, posting_id, markers_json,"
            " catalog_version, quarantined_at, reopened_at)"
            " VALUES (1, 1, '[]', 1, '2026-02-01 00:00:00', '2026-03-01 00:00:00')"
        ))


def _columns(engine) -> list[str]:  # type: ignore[no-untyped-def]
    return [c["name"] for c in inspect(engine).get_columns("quarantined_bodies")]


def test_a_row_seeded_at_the_prior_revision_steps_forward_with_a_null_last_drain(
    tmp_path: Path,
) -> None:
    db = tmp_path / "step.db"
    engine = create_engine(f"sqlite:///{db}")
    command.upgrade(_cfg(db), BASE)
    _seed_held_row(engine)
    assert "last_drained_at" not in _columns(engine)
    with pytest.raises(OperationalError), engine.connect() as conn:
        conn.execute(text("SELECT last_drained_at FROM quarantined_bodies"))

    command.upgrade(_cfg(db), HEAD)

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT quarantined_at, reopened_at, last_drained_at FROM quarantined_bodies")
        ).one()
        assert conn.execute(text("PRAGMA foreign_key_check")).all() == []
    # The existing drain stays where readers look for it; nothing is invented in the new column.
    assert tuple(row) == ("2026-02-01 00:00:00", "2026-03-01 00:00:00", None)


def test_the_upgrade_is_safe_to_retry_and_the_downgrade_keeps_the_row(tmp_path: Path) -> None:
    db = tmp_path / "down.db"
    engine = create_engine(f"sqlite:///{db}")
    command.upgrade(_cfg(db), HEAD)
    _seed_held_row(engine)

    # A retry after a half-applied run: the column exists but the revision is not stamped.
    command.stamp(_cfg(db), BASE)
    command.upgrade(_cfg(db), HEAD)
    assert "last_drained_at" in _columns(engine)

    command.downgrade(_cfg(db), BASE)
    assert "last_drained_at" not in _columns(engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM quarantined_bodies")).scalar_one() == 1
