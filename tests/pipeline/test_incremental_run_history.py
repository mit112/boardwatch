"""D-670: extra scans/delivery passes do not consume nightly history windows."""

from datetime import timedelta
from pathlib import Path

from sqlalchemy import Engine, insert, inspect, text, update

from boardwatch.core.clock import utcnow
from boardwatch.delivery.api import _last_finished_run
from boardwatch.notify.buried_good_lead import check_buried_good_lead
from boardwatch.notify.corpus_regression import check_corpus_regression
from boardwatch.notify.delivery_drought import check_delivery_drought
from boardwatch.notify.intake_death import check_intake_death
from boardwatch.store import tables
from boardwatch.store.buried_queries import BuriedLeads
from tests.unit.test_delivery_drought import _run, _seed_input


def _mark(engine: Engine, run_id: int) -> None:
    # Supply the future storage shape when testing the old reader, so red means a polluted
    # window, not a missing-column error. Migration backfill is tested separately.
    with engine.begin() as conn:
        if "incremental" not in {col["name"] for col in inspect(conn).get_columns("runs")}:
            conn.execute(text("ALTER TABLE runs ADD COLUMN incremental BOOLEAN NOT NULL DEFAULT 0"))
        conn.execute(text("UPDATE runs SET incremental=1 WHERE id=:id"), {"id": run_id})


def test_filtered_scans_do_not_form_an_intake_death_window(engine: Engine) -> None:
    with engine.begin() as conn:
        nightly = conn.execute(
            insert(tables.runs).values(started_at=utcnow(), new_count=5)
        ).inserted_primary_key[0]
        extra = [
            int(
                conn.execute(
                    insert(tables.runs).values(started_at=utcnow(), new_count=0, boards_attempted=4)
                ).inserted_primary_key[0]
            )
            for _ in range(3)
        ]
    for rid in extra:
        _mark(engine, rid)
    assert nightly is not None
    assert check_intake_death(engine) is None


def test_extra_runs_cannot_hide_a_real_delivery_drought(engine: Engine) -> None:
    input_id = _seed_input(engine)
    for _ in range(3):
        _run(engine, input_id, candidates=1, delivered=0)
    extra = _run(engine, input_id, candidates=0, delivered=0)
    _mark(engine, extra)
    assert check_delivery_drought(engine) is not None


def test_extra_corpus_read_cannot_become_regression_subject(engine: Engine) -> None:
    from tests.unit.test_corpus_regression import _baseline
    from tests.unit.test_corpus_regression import _run as corpus_run

    _baseline(engine, evaluated=100, candidates=80)
    extra = corpus_run(engine, open_postings=100, evaluated=100, candidates=1)
    _mark(engine, extra)
    assert check_corpus_regression(engine) is None


def test_extra_run_cannot_advance_buried_closure_baseline(engine: Engine) -> None:
    now = utcnow()
    with engine.begin() as conn:
        conn.execute(
            insert(tables.runs).values(
                started_at=now - timedelta(hours=12),
                finished_at=now - timedelta(hours=10),
                corpus_open=1,
            )
        )
        extra = int(
            conn.execute(
                insert(tables.runs).values(
                    started_at=now - timedelta(hours=2),
                    finished_at=now - timedelta(hours=1),
                    corpus_open=1,
                )
            ).inserted_primary_key[0]
        )
        subject = int(
            conn.execute(
                insert(tables.runs).values(started_at=now, corpus_open=1)
            ).inserted_primary_key[0]
        )
    _mark(engine, extra)
    buried = BuriedLeads(
        open=(), closed={7: now - timedelta(hours=4)}, stale_open=(), stale_closed={}
    )
    assert check_buried_good_lead(engine, buried, run_id=subject) is not None


def test_queue_last_run_read_ignores_incremental_rows(engine: Engine) -> None:
    with engine.begin() as conn:
        nightly = int(
            conn.execute(
                insert(tables.runs).values(started_at=utcnow(), finished_at=utcnow())
            ).inserted_primary_key[0]
        )
        extra = int(
            conn.execute(
                insert(tables.runs).values(started_at=utcnow(), finished_at=utcnow())
            ).inserted_primary_key[0]
        )
    _mark(engine, extra)
    with engine.connect() as conn:
        assert _last_finished_run(conn).id == nightly


def test_migration_keeps_existing_runs_nonincremental(tmp_path: Path) -> None:
    from alembic import command
    from sqlalchemy import create_engine

    from tests.unit.test_migration_runs_corpus_counts import _cfg

    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    cfg = _cfg(str(engine.url))
    command.upgrade(cfg, "p_listing_gated")
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO runs (started_at, boards_attempted) VALUES ('2026-11-03', 4)")
        )
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT incremental FROM runs")).scalar_one() == 0
        assert conn.execute(text("PRAGMA foreign_key_check")).all() == []
        assert not conn.execute(text("PRAGMA index_info(ix_postings_first_seen)")).all()


def test_incremental_rows_do_not_advance_lane_rotation(engine: Engine) -> None:
    from boardwatch.pipeline.runner import _rotation_index

    with engine.begin() as conn:
        first = int(
            conn.execute(insert(tables.runs).values(started_at=utcnow())).inserted_primary_key[0]
        )
        extra = int(
            conn.execute(insert(tables.runs).values(started_at=utcnow())).inserted_primary_key[0]
        )
        second = int(
            conn.execute(insert(tables.runs).values(started_at=utcnow())).inserted_primary_key[0]
        )
    _mark(engine, extra)
    assert _rotation_index(engine, first) == first
    assert _rotation_index(engine, second) == first + 1


def test_the_fresh_filter_adds_no_time_index_the_applied_page_would_scan_from(
    engine: Engine,
) -> None:
    with engine.connect() as conn:
        names = {row.name for row in conn.execute(text("PRAGMA index_list(postings)"))}
    assert "ix_postings_first_seen" not in names


def test_daytime_intake_keeps_zero_nightly_scans_from_reading_as_death(engine: Engine) -> None:
    with engine.begin() as conn:
        ids = [
            int(conn.execute(
                insert(tables.runs).values(started_at=utcnow(), new_count=count)
            ).inserted_primary_key[0])
            for count in (0, 25, 0, 0)
        ]
    _mark(engine, ids[1])
    assert check_intake_death(engine) is None
    with engine.begin() as conn:
        conn.execute(
            update(tables.runs).where(tables.runs.c.id == ids[1]).values(new_count=0)
        )
    assert check_intake_death(engine) is not None
