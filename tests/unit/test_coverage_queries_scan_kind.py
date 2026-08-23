"""`load_board_coverage` counts BOARD scans only (D-285, D-284 debt a).

`apply_board` writes one `board_scans` row per call and `load_board_coverage` emits one
`BoardCoverage` per joined row. A lane that touches an already-watched board — the greenhouse
convergence case, which is the entire point of dereferencing an aggregator's `apply_url` —
therefore produced a SECOND row for one `(company_id, run_id)`, and the company appeared twice
in the corpus: once `measured` and once `enumerated_only`, inflating `corpus_boards` and
`bucket_counts` and skewing `global_ratio`.

The fix belongs in the JOIN CONDITION, never a `WHERE`. `coverage_queries`' own docstring says
why, and `test_a_never_scanned_board_is_still_unscanned` below is the test that catches getting
it wrong: under a `WHERE scan_kind = 'board'` the LEFT JOIN collapses to an inner join, because
SQL evaluates `NULL = 'board'` as NULL rather than true, and every never-scanned watched board
silently leaves the corpus instead of being bucketed `unscanned`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Connection, insert

from boardwatch.core.clock import utcnow
from boardwatch.reports.board_coverage import build_report
from boardwatch.store.coverage_queries import load_board_coverage
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.tables import board_scans, companies, jobs, postings, runs


@pytest.fixture()
def conn(tmp_path: Path):
    engine = get_engine(tmp_path / "data")
    ensure_schema(engine)
    with engine.connect() as c:
        yield c


def _company(conn: Connection, *, name: str, watched: bool = True, source: str = "user") -> int:
    result = conn.execute(
        insert(companies).values(
            name=name, provider="greenhouse", slug=name.lower(), source=source, watched=watched,
        )
    )
    return int(result.inserted_primary_key[0])


def _run(conn: Connection, run_id: int) -> None:
    conn.execute(insert(runs).values(id=run_id, started_at=utcnow(), boards_attempted=0))


def _scan(
    conn: Connection,
    *,
    company_id: int,
    run_id: int,
    scan_kind: str,
    status: str = "complete",
    board_reported_total: int | None = None,
) -> None:
    now = utcnow()
    conn.execute(
        insert(board_scans).values(
            run_id=run_id, company_id=company_id, started_at=now, finished_at=now,
            status=status, postings_listed=0, scan_kind=scan_kind,
            board_reported_total=board_reported_total,
        )
    )


def _hold(conn: Connection, company_id: int, count: int) -> None:
    now = utcnow()
    for i in range(count):
        job_id = int(conn.execute(insert(jobs).values(created_at=now)).inserted_primary_key[0])
        conn.execute(
            insert(postings).values(
                company_id=company_id, job_id=job_id, provider_posting_id=f"p-{company_id}-{i}",
                title="Software Engineer", normalized_title="software engineer",
                remote_policy="unknown", first_seen_at=now, last_seen_at=now, status="open",
                consecutive_missing=0, content_hash=f"h-{company_id}-{i}", body_text="body",
            )
        )


def test_a_lane_row_does_not_double_count_an_already_watched_board(conn: Connection) -> None:
    """One company, one run, both a board scan and a lane scan. The board is counted ONCE."""
    company_id = _company(conn, name="Acme")
    _run(conn, 1)
    _scan(conn, company_id=company_id, run_id=1, scan_kind="board", board_reported_total=10)
    _scan(conn, company_id=company_id, run_id=1, scan_kind="lane", status="partial")
    _hold(conn, company_id, 6)

    coverage = load_board_coverage(conn, run_id=1)

    assert len(coverage) == 1, f"one board, one row — got {[c.bucket for c in coverage]}"
    assert coverage[0].bucket == "measured"
    assert coverage[0].board_reported_total == 10
    report = build_report(coverage)
    assert report.corpus_boards == 1
    assert report.bucket_counts["measured"] == 1
    assert report.global_ratio == 0.6


def test_a_never_scanned_board_is_still_unscanned(conn: Connection) -> None:
    """The LEFT JOIN must survive the scan_kind filter. A `WHERE scan_kind = 'board'` drops
    this board out of the corpus entirely instead of bucketing it — SQL reads the NULL from
    the unmatched side as neither true nor false."""
    scanned = _company(conn, name="Scanned")
    _company(conn, name="Never")
    _run(conn, 1)
    _scan(conn, company_id=scanned, run_id=1, scan_kind="board", board_reported_total=4)
    _hold(conn, scanned, 4)

    coverage = load_board_coverage(conn, run_id=1)

    assert {c.name: c.bucket for c in coverage} == {"Scanned": "measured", "Never": "unscanned"}
    assert build_report(coverage).corpus_boards == 2


def test_a_board_touched_only_by_a_lane_reads_unscanned(conn: Connection) -> None:
    """A lane samples an aggregator; it enumerates no board and states no total, so it makes
    no coverage claim. Letting its row satisfy the join would report the board as covered."""
    company_id = _company(conn, name="Acme")
    _run(conn, 1)
    _scan(conn, company_id=company_id, run_id=1, scan_kind="lane", status="partial")
    _hold(conn, company_id, 3)

    coverage = load_board_coverage(conn, run_id=1)

    assert len(coverage) == 1
    assert coverage[0].bucket == "unscanned"


def test_a_lane_company_is_outside_the_coverage_corpus(conn: Connection) -> None:
    """`upsert_lane_company` stores unwatched, and the corpus is `watched.is_(True)`."""
    watched = _company(conn, name="Acme")
    lane_only = _company(conn, name="Hiringcafe", watched=False, source="lane")
    _run(conn, 1)
    _scan(conn, company_id=watched, run_id=1, scan_kind="board", board_reported_total=1)
    _scan(conn, company_id=lane_only, run_id=1, scan_kind="lane", status="partial")

    assert [c.name for c in load_board_coverage(conn, run_id=1)] == ["Acme"]


def test_the_default_run_is_the_latest_run_that_board_scanned_something(conn: Connection) -> None:
    """A lane-only run measures no board. Defaulting to it would report the whole corpus
    `unscanned` and make `boardwatch coverage` read as a total outage."""
    company_id = _company(conn, name="Acme")
    _run(conn, 1)
    _run(conn, 2)
    _scan(conn, company_id=company_id, run_id=1, scan_kind="board", board_reported_total=5)
    _scan(conn, company_id=company_id, run_id=2, scan_kind="lane", status="partial")
    _hold(conn, company_id, 5)

    coverage = load_board_coverage(conn)

    assert len(coverage) == 1
    assert coverage[0].bucket == "measured"
    assert coverage[0].board_reported_total == 5
