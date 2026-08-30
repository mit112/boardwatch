"""D-371 migration: `runs` gains `corpus_open`, `corpus_evaluated` and `corpus_candidates`.

Three additive columns, no table rebuild — so the risk here is not data loss, it is the
DEFAULT and the rebuild.

**The default.** Every run that already exists was written before the corpus was recorded, and
the honest statement about it is "not measured": NULL, in all three. A `NOT NULL DEFAULT 0`
would make all 132 historic runs read as a run that measured an EMPTY corpus — which is
precisely the alarm state the corpus-regression detector exists to catch — and the detector
would page on the day it shipped, against a baseline of fabricated zeros.

**The rebuild, and what these assertions do and do NOT prove.** `runs` is referenced by FK from
six tables, and alembic builds its own engine so `store/db.py`'s `PRAGMA foreign_keys=ON`
connect listener never fires (D-269) — which is why every migration touching `runs` bans
`batch_alter_table` and why `PRAGMA foreign_key_check` is asserted empty after each step here,
with a child row seeded so the check has something to find.

That assertion was MEASURED against the banned version rather than assumed to catch it, and it
does not: rewriting this migration as `batch_alter_table('runs', recreate='always')` leaves the
run row, the child row, `foreign_key_check` and even the resulting column order identical on
this SQLite (`runs` carries no index for a rebuild to drop). So the ban is a rule enforced by
review, not by this file, and the checks below stand on what they DO catch — a downgrade that
loses the corpus row or its children, and the default.

Stepped, not round-tripped, for the NULL assertion: `command.downgrade` DROPs the columns, so
a full down/up cycle destroys exactly the values the assertion would read (the
`migration-backfill-test-needs-version-step` rule). The round trip is exercised separately,
for survival of the ROW rather than of the column.
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

BASE = "p_runs_board_split"  # the head this revision stacks on
HEAD = "p_runs_corpus_counts"
MIGRATIONS = Path("src/boardwatch/store/migrations")


def _cfg(db_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def _seed_run_with_a_child(engine, *, started_at: str) -> None:
    """One run plus one `artifacts` row that references it.

    The child is the point: a table rebuild that drops the FK target orphans it, and with
    `foreign_keys` OFF that is invisible unless something asks. `PRAGMA foreign_key_check`
    asks, but only ever finds a violation if a referencing row exists to violate.
    """
    with engine.begin() as conn:
        run_id = conn.execute(
            text(
                "INSERT INTO runs (started_at, status, boards_attempted) "
                "VALUES (:t, 'ok', 0) RETURNING id"
            ),
            {"t": started_at},
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO artifacts (kind, uri, created_at, run_id) "
                "VALUES ('resume_tailored', 'file://r1', :t, :run)"
            ),
            {"t": started_at, "run": run_id},
        )


def _corpus_columns(engine) -> list[tuple]:
    with engine.connect() as conn:
        return [
            tuple(r)
            for r in conn.execute(
                text(
                    "SELECT corpus_open, corpus_evaluated, corpus_candidates "
                    "FROM runs ORDER BY id"
                )
            )
        ]


def _fk_violations(engine) -> list[tuple]:
    with engine.connect() as conn:
        return [tuple(r) for r in conn.execute(text("PRAGMA foreign_key_check"))]


def test_a_run_seeded_at_the_prior_revision_steps_forward_unmeasured(tmp_path: Path) -> None:
    """The stepped assertion: seed at N-1, upgrade to N, read what the migration wrote.

    All three NULL. A run that predates the columns did not measure a corpus, and a zero would
    claim it measured one and found it empty — the detector's alarm state, asserted about 132
    runs that were all healthy.
    """
    db = tmp_path / "step.db"
    cfg = _cfg(f"sqlite:///{db}")
    engine = create_engine(f"sqlite:///{db}")

    command.upgrade(cfg, BASE)
    _seed_run_with_a_child(engine, started_at="2026-01-01 00:00:00")
    with pytest.raises(OperationalError):  # none of the three columns exists yet
        _corpus_columns(engine)

    command.upgrade(cfg, HEAD)

    assert _corpus_columns(engine) == [(None, None, None)]
    assert _fk_violations(engine) == []


def test_the_columns_hold_the_three_counts(tmp_path: Path) -> None:
    """The schema is only worth adding if it can carry the three facts the funnel writer
    stamps. Distinct values, so a migration that added the columns in the wrong order — or a
    writer that bound them positionally — cannot pass by symmetry."""
    db = tmp_path / "write.db"
    cfg = _cfg(f"sqlite:///{db}")
    engine = create_engine(f"sqlite:///{db}")
    command.upgrade(cfg, HEAD)
    _seed_run_with_a_child(engine, started_at="2026-01-02 00:00:00")

    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE runs SET corpus_open = 105935, corpus_evaluated = 105935, "
                "corpus_candidates = 68248"
            )
        )

    assert _corpus_columns(engine) == [(105935, 105935, 68248)]
    assert _fk_violations(engine) == []


def test_the_downgrade_drops_the_columns_and_keeps_the_run_and_its_child(
    tmp_path: Path,
) -> None:
    """A rollback loses the corpus history, which the pre-migration schema cannot express. It
    must not lose the run, and it must not orphan the six tables that reference it. Alembic's
    own engine has FK enforcement OFF, so a destructive downgrade — a `DROP TABLE runs`, or a
    recreate that does not carry the rows across — would orphan silently rather than fail,
    which is why the artifact row and `foreign_key_check` are both here."""
    db = tmp_path / "down.db"
    cfg = _cfg(f"sqlite:///{db}")
    engine = create_engine(f"sqlite:///{db}")
    command.upgrade(cfg, HEAD)
    _seed_run_with_a_child(engine, started_at="2026-01-03 00:00:00")
    with engine.begin() as conn:
        conn.execute(text("UPDATE runs SET corpus_open = 10, corpus_evaluated = 9, "
                          "corpus_candidates = 4"))

    command.downgrade(cfg, BASE)

    with pytest.raises(OperationalError):
        _corpus_columns(engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM runs")).scalar_one() == 1
        orphans = conn.execute(
            text(
                "SELECT a.id FROM artifacts a LEFT JOIN runs r ON r.id = a.run_id "
                "WHERE a.run_id IS NOT NULL AND r.id IS NULL"
            )
        ).all()
    assert orphans == []
    assert _fk_violations(engine) == []

    # Re-upgrading is clean, and the counts are GONE rather than resurrected — the downgrade
    # dropped the columns, so the values are not recoverable and the run is honestly unmeasured.
    command.upgrade(cfg, HEAD)
    assert _corpus_columns(engine) == [(None, None, None)]
    assert _fk_violations(engine) == []
