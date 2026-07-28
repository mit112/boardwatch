"""P2 migration round-trip: two additive nullable JSON columns on the profile
singleton, native DROP COLUMN in downgrade per the p0_jobs_anchor precedent, and a
clean PRAGMA foreign_key_check afterwards."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

BASE = "p0_artifacts"
HEAD = "p2_profile_eligibility"
MIGRATIONS = Path("src/boardwatch/store/migrations")


def _cfg(db_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def _seed(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.execute(text(
            "INSERT INTO profile (id, text, remote_only, updated_at) "
            "VALUES (1, 'existing profile', 0, '2026-01-01 00:00:00')"))


def test_profile_eligibility_round_trip(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'rt.db'}"
    cfg = _cfg(url)
    engine = create_engine(url)

    command.upgrade(cfg, BASE)
    _seed(engine)

    command.upgrade(cfg, HEAD)
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        cols = {r[1] for r in conn.execute(text("PRAGMA table_info(profile)")).all()}
        assert "eligibility_facts_json" in cols
        assert "eligibility_policy_json" in cols
        # the pre-existing row survives and both new columns read as NULL
        row = conn.execute(text(
            "SELECT text, eligibility_facts_json, eligibility_policy_json "
            "FROM profile WHERE id = 1")).one()
        assert row.text == "existing profile"
        assert row.eligibility_facts_json is None
        assert row.eligibility_policy_json is None
        conn.execute(text(
            "UPDATE profile SET eligibility_facts_json = '{\"highest_degree\": \"bachelor\"}' "
            "WHERE id = 1"))
        assert conn.execute(text(
            "SELECT eligibility_facts_json FROM profile WHERE id = 1")).scalar_one() == (
            '{"highest_degree": "bachelor"}')

    command.downgrade(cfg, BASE)
    with engine.begin() as conn:
        cols = {r[1] for r in conn.execute(text("PRAGMA table_info(profile)")).all()}
        assert "eligibility_facts_json" not in cols
        assert "eligibility_policy_json" not in cols
        assert conn.execute(
            text("SELECT text FROM profile WHERE id = 1")).scalar_one() == "existing profile"
        assert conn.execute(text("PRAGMA foreign_key_check")).all() == []
