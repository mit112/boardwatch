"""T191: the store-side recount each lane's self-report is cross-checked against.

Written through the real writers a lane apply uses (`upsert_lane_company` + `apply_board` with
`scan_kind="lane"`), so the recount is pinned to what the store actually holds after a lane run
rather than to hand-inserted rows that could drift from the writer.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine, insert

from boardwatch.core.clock import utcnow
from boardwatch.core.models import RawPosting
from boardwatch.lanes.base import lane_snapshot
from boardwatch.scan.apply import apply_board
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import upsert_lane_company
from boardwatch.store.run_funnel_queries import LaneCaptureCounts, count_lane_captures
from boardwatch.store.tables import runs


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path)
    ensure_schema(eng)
    return eng


def _run(engine: Engine) -> int:
    with engine.begin() as conn:
        return int(
            conn.execute(
                insert(runs).values(started_at=utcnow(), boards_attempted=0)
            ).inserted_primary_key[0]
        )


def _raw(posting_id: str) -> RawPosting:
    return RawPosting(
        provider_posting_id=posting_id,
        title="Software Engineer",
        url=f"https://aggregator.test/jobs/{posting_id}",
        locations=["Seattle, WA"],
        body_text=f"body of {posting_id} for a software engineer",
        raw_json={},
    )


def _land(
    engine: Engine,
    run_id: int,
    provider: str,
    slug: str,
    *posting_ids: str,
    lane: str | None = "stub",
) -> None:
    """What `runner._apply_snapshots` does for one lane company. `lane=None` writes the row a
    pre-migration run left: a lane row carrying no lane name."""
    with engine.begin() as conn:
        company_id = upsert_lane_company(conn, provider=provider, slug=slug, name=slug)
    snapshot = lane_snapshot([_raw(pid) for pid in posting_ids], "https://aggregator.test/s")
    apply_board(engine, snapshot, company_id, run_id, scan_kind="lane", lane=lane)


def test_first_captures_are_split_from_a_company_the_store_already_scanned(
    engine: Engine,
) -> None:
    """`old` was first captured in an EARLIER run and only re-applied now — an overwrite, not
    new reach — so only `new` counts, even though the lane named both."""
    earlier = _run(engine)
    _land(engine, earlier, "hiringcafe", "old", "o-1")
    current = _run(engine)
    _land(engine, current, "hiringcafe", "old", "o-1", "o-2")
    _land(engine, current, "hiringcafe", "new", "n-1")

    with engine.connect() as conn:
        counts = count_lane_captures(
            conn, current, {"stub": (("hiringcafe", "old"), ("hiringcafe", "new"))}
        )

    assert counts == LaneCaptureCounts(first_captures={"stub": 1}, scan_rows=2, attributed_by_row=True)


def test_a_company_row_with_no_landed_scan_is_not_counted(engine: Engine) -> None:
    """The F8 failure: the company row was written but its board never landed. The store holds
    no lane capture for it, so the recount does not count it however the lane reports it."""
    current = _run(engine)
    _land(engine, current, "hiringcafe", "a", "a-1")
    with engine.begin() as conn:
        upsert_lane_company(conn, provider="hiringcafe", slug="b", name="b")

    with engine.connect() as conn:
        counts = count_lane_captures(
            conn, current, {"stub": (("hiringcafe", "a"), ("hiringcafe", "b"))}
        )

    assert counts == LaneCaptureCounts(first_captures={"stub": 1}, scan_rows=1, attributed_by_row=True)


def test_a_snapshot_that_landed_no_posting_is_not_new_reach(engine: Engine) -> None:
    """A lane board applied with zero postings writes a `board_scans` row and captured nothing.
    It counts toward the scan rows and not toward first captures."""
    current = _run(engine)
    _land(engine, current, "hiringcafe", "empty")

    with engine.connect() as conn:
        counts = count_lane_captures(conn, current, {"stub": (("hiringcafe", "empty"),)})

    assert counts == LaneCaptureCounts(first_captures={"stub": 0}, scan_rows=1, attributed_by_row=True)


def test_each_lane_is_counted_over_its_own_admissions_and_other_runs_are_ignored(
    engine: Engine,
) -> None:
    other = _run(engine)
    _land(engine, other, "hiringcafe", "elsewhere", "e-1")
    current = _run(engine)
    _land(engine, current, "hiringcafe", "Acme", "h-1", lane="hiringcafe")
    _land(engine, current, "linkedin", "beta", "l-1", lane="linkedin")

    with engine.connect() as conn:
        counts = count_lane_captures(
            conn,
            current,
            {
                # Admission spells the slug in another case than the store row: still the company.
                "hiringcafe": (("hiringcafe", "ACME"),),
                "linkedin": (("linkedin", "beta"), ("linkedin", "never-landed")),
            },
        )

    assert counts == LaneCaptureCounts(
        first_captures={"hiringcafe": 1, "linkedin": 1}, scan_rows=2, attributed_by_row=True
    )


def test_a_company_two_lanes_admitted_is_credited_only_to_the_lane_that_landed_it(
    engine: Engine,
) -> None:
    """T199, run 475's `ashby:evenup`: hiring.cafe and Indeed both admitted it and only Indeed's
    snapshot landed. Attributed by admission alone, both lanes read 1; the row names Indeed."""
    current = _run(engine)
    _land(engine, current, "ashby", "evenup", "e-1", lane="indeed")

    with engine.connect() as conn:
        counts = count_lane_captures(
            conn,
            current,
            {"hiringcafe": (("ashby", "evenup"),), "indeed": (("ashby", "evenup"),)},
        )

    assert counts.first_captures["hiringcafe"] == 0
    assert counts.first_captures["indeed"] == 1
    assert counts.scan_rows == 1
    assert counts.attributed_by_row


def test_a_company_both_lanes_admitted_and_landed_counts_once_for_each(engine: Engine) -> None:
    """Control: two rows, one per lane, so each lane's own row credits it."""
    current = _run(engine)
    _land(engine, current, "ashby", "evenup", "e-1", lane="hiringcafe")
    _land(engine, current, "ashby", "evenup", "e-1", lane="indeed")

    with engine.connect() as conn:
        counts = count_lane_captures(
            conn,
            current,
            {"hiringcafe": (("ashby", "evenup"),), "indeed": (("ashby", "evenup"),)},
        )

    assert counts == LaneCaptureCounts(
        first_captures={"hiringcafe": 1, "indeed": 1}, scan_rows=2, attributed_by_row=True
    )


def test_a_run_whose_lane_rows_carry_no_lane_name_falls_back_to_admission(
    engine: Engine,
) -> None:
    """Pre-migration rows name no lane. The recount falls back to admission-only attribution —
    both lanes are credited, as before T199 — and says it did."""
    current = _run(engine)
    _land(engine, current, "ashby", "evenup", "e-1", lane=None)

    with engine.connect() as conn:
        counts = count_lane_captures(
            conn,
            current,
            {"hiringcafe": (("ashby", "evenup"),), "indeed": (("ashby", "evenup"),)},
        )

    assert counts == LaneCaptureCounts(
        first_captures={"hiringcafe": 1, "indeed": 1}, scan_rows=1, attributed_by_row=False
    )
