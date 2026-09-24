"""T199 migration: `board_scans.lane`, the lane that wrote a lane row.

Additive and nullable, so the proof is a POPULATED round trip: a lane row written before the
migration survives it with a NULL lane, and `count_lane_captures` over that run takes the
admission-only fallback and says it did — the pre-migration behaviour, never a silent zero.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from boardwatch.store.run_funnel_queries import LaneCaptureCounts, count_lane_captures

BASE = "p_target_countries"  # the head this migration follows
HEAD = "p_board_scans_lane"  # the migration under test
MIGRATIONS = Path("src/boardwatch/store/migrations")
_T = "2026-01-01 00:00:00"


def _cfg(db_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def _seed_pre_migration_lane_capture(conn) -> None:  # type: ignore[no-untyped-def]
    """One run, one lane company first captured by a lane row in the pre-migration shape."""
    conn.execute(
        text("INSERT INTO runs (id, started_at, boards_attempted) VALUES (1, :t, 0)"), {"t": _T}
    )
    conn.execute(text("INSERT INTO jobs (id, created_at) VALUES (1, :t)"), {"t": _T})
    conn.execute(
        text(
            "INSERT INTO companies (id, name, provider, slug, source, watched) "
            "VALUES (1, 'EvenUp', 'ashby', 'evenup', 'lane', 0)"
        )
    )
    conn.execute(
        text(
            "INSERT INTO board_scans (run_id, company_id, started_at, finished_at, status, "
            "postings_listed, scan_kind) VALUES (1, 1, :t, :t, 'complete', 1, 'lane')"
        ),
        {"t": _T},
    )
    conn.execute(
        text(
            "INSERT INTO postings (id, company_id, provider_posting_id, title, normalized_title, "
            "remote_policy, first_seen_at, last_seen_at, status, consecutive_missing, "
            "death_strikes, content_hash, body_text, job_id) VALUES (1, 1, 'e-1', 'Engineer', "
            "'engineer', 'unknown', :t, :t, 'open', 0, 0, 'h', 'body', 1)"
        ),
        {"t": _T},
    )
    conn.execute(
        text(
            "INSERT INTO posting_events (posting_id, kind, run_id, created_at) "
            "VALUES (1, 'new', 1, :t)"
        ),
        {"t": _T},
    )


def test_a_pre_migration_lane_row_reads_null_and_takes_the_admission_fallback(
    tmp_path: Path,
) -> None:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    cfg = _cfg(url)
    engine = create_engine(url)
    command.upgrade(cfg, BASE)
    with engine.begin() as conn:
        _seed_pre_migration_lane_capture(conn)

    command.upgrade(cfg, HEAD)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT lane FROM board_scans")).scalar_one() is None
        counts = count_lane_captures(
            conn, 1, {"hiringcafe": (("ashby", "evenup"),), "indeed": (("ashby", "evenup"),)}
        )
    assert counts == LaneCaptureCounts(
        first_captures={"hiringcafe": 1, "indeed": 1}, scan_rows=1, attributed_by_row=False
    )

    command.downgrade(cfg, BASE)
    with engine.connect() as conn:
        cols = {r[1] for r in conn.execute(text("PRAGMA table_info(board_scans)"))}
        assert conn.execute(text("SELECT scan_kind FROM board_scans")).scalar_one() == "lane"
    assert "lane" not in cols
