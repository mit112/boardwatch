"""D-686: "which boards ever completed a scan" is answered from an index, and the migration adds it.

The queue refresh asks that question once per lead (`_delivered_select`). Without the index each
ask scans every `board_scans` row and sorts them; on the measured store (476,261 rows, 2,381 asks)
that was 91.8 s of one refresh's 94 s of SQL. The answer is the same either way, so only the plan
shows the regression, and the tests read the plan of the statements the real functions issue.
"""

from collections.abc import Callable
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine, event, inspect, select, text

from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.delivery_queries import _board_ever_complete, queue_detail

INDEX = "ix_board_scans_status_company"
BASE = "p_apply_destinations"
HEAD = "p_board_scans_status_index"
MIGRATIONS = Path("src/boardwatch/store/migrations")


def _indexes(engine: Engine) -> dict[str, list[str]]:
    return {
        index["name"]: list(index["column_names"])
        for index in inspect(engine).get_indexes("board_scans")
    }


def _board_scans_plans(engine: Engine, issue: Callable[[Connection], object]) -> list[str]:
    """The plan of every statement the REAL reader issues that touches `board_scans`."""
    issued: list[tuple[str, object]] = []

    def _record(_c, _cur, statement, parameters, _ctx, _many):  # type: ignore[no-untyped-def]
        if statement.startswith("SELECT") and "board_scans" in statement:
            issued.append((statement, parameters))

    event.listen(engine, "before_cursor_execute", _record)
    with engine.connect() as conn:
        issue(conn)
    event.remove(engine, "before_cursor_execute", _record)
    with engine.connect() as conn:
        return [
            " | ".join(
                str(row[3])
                for row in conn.exec_driver_sql(f"EXPLAIN QUERY PLAN {statement}", parameters).all()
            )
            for statement, parameters in issued
        ]


def _config(url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def test_a_fresh_store_has_the_index(tmp_path: Path) -> None:
    engine = get_engine(tmp_path)
    ensure_schema(engine)
    assert _indexes(engine)[INDEX] == ["status", "company_id"]


def test_the_migration_adds_it_to_a_store_that_predates_it(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    cfg = _config(url)
    command.upgrade(cfg, BASE)
    assert INDEX not in _indexes(create_engine(url))
    command.upgrade(cfg, HEAD)
    assert _indexes(create_engine(url))[INDEX] == ["status", "company_id"]
    command.downgrade(cfg, BASE)
    assert INDEX not in _indexes(create_engine(url))


def test_the_migration_finishes_when_the_index_was_already_built(tmp_path: Path) -> None:
    """A run killed after the build but before the revision stamp must retry, not fail."""
    url = f"sqlite:///{tmp_path / 'm.db'}"
    cfg = _config(url)
    command.upgrade(cfg, BASE)
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text(f"CREATE INDEX {INDEX} ON board_scans (status, company_id)"))
    command.upgrade(cfg, HEAD)
    assert _indexes(create_engine(url))[INDEX] == ["status", "company_id"]


def test_the_ever_complete_subquery_is_answered_from_the_index(tmp_path: Path) -> None:
    engine = get_engine(tmp_path)
    ensure_schema(engine)
    plans = _board_scans_plans(
        engine, lambda conn: conn.execute(select(_board_ever_complete().c.company_id)).all()
    )
    assert plans
    for plan in plans:
        assert f"COVERING INDEX {INDEX}" in plan, plan
        assert "SCAN board_scans" not in plan and "TEMP B-TREE" not in plan, plan


def test_the_refresh_reads_it_from_the_index_once_per_lead(tmp_path: Path) -> None:
    """`queue_detail` is the per-lead read the refresh repeats; the subquery sits inside it."""
    engine = get_engine(tmp_path)
    ensure_schema(engine)
    plans = _board_scans_plans(engine, lambda conn: queue_detail(conn, 1))
    assert plans
    for plan in plans:
        assert f"COVERING INDEX {INDEX}" in plan, plan
        assert "SCAN board_scans" not in plan, plan


def test_the_helper_can_see_a_scan(tmp_path: Path) -> None:
    """Null control: with the index dropped the same reader's plan must show the scan."""
    engine = get_engine(tmp_path)
    ensure_schema(engine)
    with engine.begin() as conn:
        conn.execute(text(f"DROP INDEX {INDEX}"))
    plans = _board_scans_plans(
        engine, lambda conn: conn.execute(select(_board_ever_complete().c.company_id)).all()
    )
    assert plans
    assert all("SCAN board_scans" in plan and INDEX not in plan for plan in plans), plans
