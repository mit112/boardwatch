"""D-325 migration: `postings` gains `death_strikes` and `last_death_probe_at`.

Two additive columns, no table rebuild — so the risk is not data loss but the DEFAULT. Every
posting that already exists was written before any probe ran, and the honest statement about it
is "never probed, no strikes": `death_strikes = 0` and `last_death_probe_at = NULL`. A default
of anything else would either hand every legacy row a free strike or claim a probe that never
happened, and the second is worse — it would suppress the whole legacy corpus from the first
sweep for a full TTL while the funnel reported an empty due set.

Stepped, not round-tripped. `command.downgrade` DROPs both columns, so a full down/up cycle
destroys exactly the values a backfill assertion would read: the only way to prove what the
upgrade wrote is to seed at N-1 and step forward (the `migration-backfill-test-needs-version-step`
rule). The round trip is exercised separately, for survival of the ROW rather than the column.

FK enforcement is OFF inside alembic — it builds its own engine, so `store/db.py`'s
`PRAGMA foreign_keys=ON` connect listener never fires (D-269). `PRAGMA foreign_key_check` is
asserted empty after each step for that reason.
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

BASE = "p_lane_companies"  # the head this revision stacks on
HEAD = "p_death_probe"
MIGRATIONS = Path("src/boardwatch/store/migrations")

# `job_id` is a real FK with a NOT-NULL trigger (D28), so a posting cannot be seeded without
# its canonical job row.
_POSTING_COLS = (
    "company_id, job_id, provider_posting_id, title, normalized_title, url, remote_policy, "
    "first_seen_at, last_seen_at, status, consecutive_missing, content_hash, body_text"
)


def _cfg(db_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def _seed_posting(engine, *, pid: str) -> None:
    with engine.begin() as conn:
        # UNIQUE(provider, slug), so OR IGNORE keeps this callable more than once per store.
        conn.execute(
            text(
                "INSERT OR IGNORE INTO companies (name, provider, slug, source, watched) "
                "VALUES ('Acme', 'greenhouse', 'acme', 'lane', 0)"
            )
        )
        job_id = conn.execute(
            text("INSERT INTO jobs (created_at) VALUES (:t) RETURNING id"),
            {"t": "2026-01-01 00:00:00"},
        ).scalar_one()
        conn.execute(
            text(
                f"INSERT INTO postings ({_POSTING_COLS}) VALUES "
                "((SELECT id FROM companies WHERE slug = 'acme'), :job, :pid, "
                "'Backend Engineer', 'backend engineer', 'https://example.test/j/1', 'remote', "
                ":t, :t, 'open', 0, 'h', 'body')"
            ),
            {"job": job_id, "pid": pid, "t": "2026-01-01 00:00:00"},
        )


def _probe_columns(engine) -> list[tuple]:
    with engine.connect() as conn:
        return [
            tuple(r)
            for r in conn.execute(
                text(
                    "SELECT provider_posting_id, death_strikes, last_death_probe_at "
                    "FROM postings ORDER BY provider_posting_id"
                )
            )
        ]


def _fk_violations(engine) -> list[tuple]:
    with engine.connect() as conn:
        return [tuple(r) for r in conn.execute(text("PRAGMA foreign_key_check"))]


def test_a_row_seeded_at_the_prior_revision_steps_forward_unprobed(tmp_path: Path) -> None:
    """The stepped assertion: seed at N-1, upgrade to N, read what the migration wrote.

    A row that predates the probe has never been probed and carries no strike. NULL, not a
    timestamp — a defaulted `last_death_probe_at` of "now" would hide the entire legacy corpus
    from the first sweep for a full TTL, with the funnel honestly reporting `due = 0`.
    """
    db = tmp_path / "step.db"
    cfg = _cfg(f"sqlite:///{db}")
    engine = create_engine(f"sqlite:///{db}")

    command.upgrade(cfg, BASE)
    _seed_posting(engine, pid="legacy")
    with pytest.raises(OperationalError):  # neither column exists yet
        _probe_columns(engine)

    command.upgrade(cfg, HEAD)

    assert _probe_columns(engine) == [("legacy", 0, None)]
    assert _fk_violations(engine) == []


def test_the_columns_hold_a_strike_and_a_probe_time(tmp_path: Path) -> None:
    """The schema is only worth adding if it can carry the two facts the sweep writes."""
    db = tmp_path / "write.db"
    cfg = _cfg(f"sqlite:///{db}")
    engine = create_engine(f"sqlite:///{db}")
    command.upgrade(cfg, HEAD)
    _seed_posting(engine, pid="probed")

    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE postings SET death_strikes = 1, "
                "last_death_probe_at = '2026-08-27 09:00:00'"
            )
        )

    assert _probe_columns(engine) == [("probed", 1, "2026-08-27 09:00:00")]


def test_the_downgrade_drops_the_columns_and_keeps_the_posting(tmp_path: Path) -> None:
    """A rollback loses the strike history, which the pre-migration schema cannot express. It
    must not lose the posting — `postings` is the corpus, and alembic's own engine has FK
    enforcement OFF, so a destructive downgrade would orphan silently rather than fail."""
    db = tmp_path / "down.db"
    cfg = _cfg(f"sqlite:///{db}")
    engine = create_engine(f"sqlite:///{db}")
    command.upgrade(cfg, HEAD)
    _seed_posting(engine, pid="survivor")
    with engine.begin() as conn:
        conn.execute(text("UPDATE postings SET death_strikes = 1"))

    command.downgrade(cfg, BASE)

    with pytest.raises(OperationalError):
        _probe_columns(engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM postings")).scalar_one() == 1
        orphans = conn.execute(
            text(
                "SELECT p.id FROM postings p LEFT JOIN companies c ON c.id = p.company_id "
                "WHERE c.id IS NULL"
            )
        ).all()
    assert orphans == []
    assert _fk_violations(engine) == []

    # Re-upgrading is clean, and the strike is GONE rather than resurrected — the downgrade
    # dropped the column, so the value is not recoverable and the row is honestly unprobed.
    command.upgrade(cfg, HEAD)
    assert _probe_columns(engine) == [("survivor", 0, None)]
