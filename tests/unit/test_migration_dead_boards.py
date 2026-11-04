"""D-669 migrates populated stores without inventing dead-board evidence."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text


def test_old_evidence_stays_unknown_and_the_migration_round_trips(tmp_path: Path) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", "src/boardwatch/store/migrations")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{tmp_path / 'migration.db'}")
    engine = create_engine(cfg.get_main_option("sqlalchemy.url"))
    command.upgrade(cfg, "p_listing_gated")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO runs (id, started_at, boards_attempted) "
                          "VALUES (1, '2026-01-01', 1)"))
        conn.execute(text("INSERT INTO companies (id, name, provider, slug, source, watched) "
                          "VALUES (1, 'Acme', 'greenhouse', 'acme', 'user', 1)"))
        conn.execute(text("INSERT INTO board_scans (id, run_id, company_id, started_at, "
                          "finished_at, status, postings_listed, error) VALUES "
                          "(1, 1, 1, '2026-01-01', '2026-01-01', 'failed', 0, 'HTTP 404')"))
    command.upgrade(cfg, "p_dead_boards")
    with engine.begin() as conn:
        assert conn.execute(text("SELECT dead, pipeline_scan FROM board_scans")).one() == (0, 0)
        assert conn.execute(text("SELECT id, name, source FROM companies")).one() == (1, "Acme", "user")
        assert conn.execute(text("PRAGMA foreign_key_check")).all() == []
    command.downgrade(cfg, "p_listing_gated")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT id, source FROM companies ORDER BY id")).all() == [(1, "user")]
        assert conn.execute(text("SELECT id, company_id, error FROM board_scans")).one() == (1, 1, "HTTP 404")
        assert conn.execute(text("PRAGMA foreign_key_check")).all() == []
        columns = {r[1] for r in conn.execute(text("PRAGMA table_info(board_scans)"))}
        assert not {"dead", "pipeline_scan"} & columns
