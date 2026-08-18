"""`runs_status_backfill_repair`: close the rows `p0_run_status`'s `DEFAULT 'running'` backfilled
onto runs that had already finished, and touch nothing else.

Proven on a POPULATED database across the real `alembic upgrade`, seeded at the PREVIOUS head so
the migration under test is the only thing that runs between the two snapshots.

The seed walks every combination of (status, finished_at) rather than only the broken one: the
migration is an UPDATE with a two-clause predicate, and a predicate is as wrong when it matches too
much as when it matches too little. A repair that also laundered `failed` into `ok`, or that closed
a run still in flight, would pass a test that only asserted the broken row was fixed.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

BASE = "perf_eligibility_inputs_identity"  # the head this migration follows
HEAD = "runs_status_backfill_repair"  # the migration under test
MIGRATIONS = Path("src/boardwatch/store/migrations")

#: (label, status, finished_at) -> the status the row must carry AFTER the upgrade.
#: Only the first row is the backfill artifact; the other three are the shapes a live database
#: legitimately holds, and each one is a way the predicate could be too broad.
SEED = [
    # the defect: closed by the pre-status `finish_run`, then backfilled to `running`
    ("backfilled", "running", "2026-01-02 00:00:00", "ok"),
    # genuinely in flight — no `finished_at`, so the reaper owns it, not this migration
    ("in_flight", "running", None, "running"),
    # a real failure. Laundering this into `ok` would destroy the only record of it
    ("failed", "failed", "2026-01-02 00:00:00", "failed"),
    # already correct, and must stay byte-identical
    ("succeeded", "ok", "2026-01-02 00:00:00", "ok"),
]


def _cfg(db_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_repair_closes_only_the_backfilled_rows(tmp_path: Path) -> None:
    db = tmp_path / "repair.db"
    url = f"sqlite:///{db}"
    cfg = _cfg(url)
    engine = create_engine(url)

    command.upgrade(cfg, BASE)
    with engine.begin() as conn:
        for label, status, finished_at, _ in SEED:
            conn.execute(
                text(
                    "INSERT INTO runs (started_at, finished_at, boards_attempted, status) "
                    "VALUES ('2026-01-01 00:00:00', :f, 0, :s)"
                ),
                {"f": finished_at, "s": status},
            )
            assert label  # the label documents the row; the assert keeps it from being unused

    # The state the repair exists because of: it is real at BASE, so the test is not asserting
    # against a shape that only this file believes in.
    with engine.connect() as conn:
        unreachable = conn.execute(
            text("SELECT COUNT(*) FROM runs WHERE status = 'running' AND finished_at IS NOT NULL")
        ).scalar_one()
    assert unreachable == 1

    command.upgrade(cfg, HEAD)

    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id, status, finished_at FROM runs ORDER BY id")).all()
    assert [r.status for r in rows] == [expected for *_, expected in SEED]
    # `finished_at` is the migration's predicate, never its target: a repair that also stamped one
    # would invent a completion time for a run still in flight.
    assert [r.finished_at for r in rows] == [seeded for _, _, seeded, _ in SEED]

    # Idempotent: after the repair nothing matches the predicate, so a re-run is a no-op. This is
    # what makes it safe on a store the migration has already touched.
    with engine.connect() as conn:
        assert (
            conn.execute(
                text(
                    "SELECT COUNT(*) FROM runs WHERE status = 'running' "
                    "AND finished_at IS NOT NULL"
                )
            ).scalar_one()
            == 0
        )
