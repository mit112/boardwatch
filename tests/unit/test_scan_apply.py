"""`_scan_row` persists the coverage numbers (D-271) — the four coverage columns on board_scans.

NULL means the board stated nothing; it must never be defaulted to zero, and a failed or
unchanged scan's coverage is undefined, not zero. `board_total_censored` is a tri-state:
True -> 1, False -> 0, None -> NULL, so False (a claim of "not censored") must not collapse
into the "no claim" NULL case.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine, insert, select

from boardwatch.core.models import BoardSnapshot
from boardwatch.scan.apply import apply_board
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import insert_run
from boardwatch.store.tables import board_scans


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path)
    ensure_schema(eng)
    return eng


def _insert_company(engine: Engine) -> int:
    with engine.begin() as conn:
        result = conn.execute(
            insert(tables.companies).values(
                name="Acme", provider="greenhouse", slug="acme", source="user", watched=True,
            )
        )
        return int(result.inserted_primary_key[0])


def test_apply_board_persists_coverage_numbers(engine: Engine) -> None:
    company_id = _insert_company(engine)
    run_id = insert_run(engine)
    snap = BoardSnapshot(
        status="partial", postings=[], url="https://x/y",
        board_reported_total=4589, board_enumerated=2214, detail_deferred=1614,
        board_total_censored=True,
    )
    apply_board(engine, snap, company_id, run_id)
    with engine.connect() as conn:
        row = conn.execute(select(board_scans)).one()
    assert row.board_reported_total == 4589
    assert row.board_enumerated == 2214
    assert row.detail_deferred == 1614
    assert row.board_total_censored == 1  # truthy -> stored as 1, not True


def test_failed_board_writes_null_not_zero(engine: Engine) -> None:
    """A dark board's coverage is UNDEFINED. Zero would claim the board is empty."""
    company_id = _insert_company(engine)
    run_id = insert_run(engine)
    snap = BoardSnapshot(status="failed", postings=[], url="https://x/y", error="HTTP 401")
    apply_board(engine, snap, company_id, run_id)
    with engine.connect() as conn:
        row = conn.execute(select(board_scans)).one()
    assert row.board_reported_total is None
    assert row.board_enumerated is None
    assert row.detail_deferred is None
    assert row.board_total_censored is None


def test_unchanged_board_writes_null(engine: Engine) -> None:
    company_id = _insert_company(engine)
    run_id = insert_run(engine)
    snap = BoardSnapshot(status="unchanged", postings=[], url="https://x/y")
    apply_board(engine, snap, company_id, run_id)
    with engine.connect() as conn:
        row = conn.execute(select(board_scans)).one()
    assert row.board_reported_total is None
    assert row.board_enumerated is None
    assert row.detail_deferred is None
    assert row.board_total_censored is None


def test_censored_none_persists_null_not_zero(engine: Engine) -> None:
    """A snapshot exists (complete), but board_total_censored was never stated -> NULL, not 0."""
    company_id = _insert_company(engine)
    run_id = insert_run(engine)
    snap = BoardSnapshot(status="complete", postings=[], url="https://x/y")
    apply_board(engine, snap, company_id, run_id)
    with engine.connect() as conn:
        row = conn.execute(select(board_scans)).one()
    assert row.board_total_censored is None


def test_censored_false_persists_as_zero_not_null(engine: Engine) -> None:
    """False is a claim ("not censored"); it must persist as 0, not collapse into NULL."""
    company_id = _insert_company(engine)
    run_id = insert_run(engine)
    snap = BoardSnapshot(
        status="complete", postings=[], url="https://x/y", board_total_censored=False,
    )
    apply_board(engine, snap, company_id, run_id)
    with engine.connect() as conn:
        row = conn.execute(select(board_scans)).one()
    assert row.board_total_censored == 0


def test_scan_kind_defaults_to_board(engine: Engine) -> None:
    """Every caller on the six-provider scan path IS a board scan, so the default states a
    fact. Coverage joins on this value, and a lane row that read `board` would double-count."""
    company_id = _insert_company(engine)
    run_id = insert_run(engine)
    snap = BoardSnapshot(status="complete", postings=[], url="https://x/y")
    apply_board(engine, snap, company_id, run_id)
    with engine.connect() as conn:
        assert conn.execute(select(board_scans.c.scan_kind)).scalar_one() == "board"


@pytest.mark.parametrize("status", ["complete", "partial", "failed", "unchanged"])
def test_a_lane_caller_marks_every_status_lane(engine: Engine, status: str) -> None:
    """`failed` and `unchanged` return before the main scan row is written, through their own
    `_scan_row` calls — a threading that stopped at the happy path would leave a lane's failed
    board indistinguishable from a board scan's, and back in the coverage corpus."""
    company_id = _insert_company(engine)
    run_id = insert_run(engine)
    snap = BoardSnapshot(
        status=status, postings=[], url="https://x/y",
        error="HTTP 401" if status == "failed" else None,
    )
    apply_board(engine, snap, company_id, run_id, scan_kind="lane")
    with engine.connect() as conn:
        assert conn.execute(select(board_scans.c.scan_kind)).scalar_one() == "lane"
