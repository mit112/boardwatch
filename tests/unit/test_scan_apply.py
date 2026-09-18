"""`_scan_row` persists the coverage numbers (D-271) — the four coverage columns on board_scans.

NULL means the board stated nothing; it must never be defaulted to zero, and a failed or
unchanged scan's coverage is undefined, not zero. `board_total_censored` is a tri-state:
True -> 1, False -> 0, None -> NULL, so False (a claim of "not censored") must not collapse
into the "no claim" NULL case.

The second half of this module is `_apply_listed`'s liveness contract — which observations count
as evidence a posting is still alive, and which only say a file still holds a record of it.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert, select

from boardwatch.core.models import (
    CONVERGED_SECONDHAND,
    BoardSnapshot,
    RawPosting,
    SecondhandField,
)
from boardwatch.core.normalize import content_hash
from boardwatch.scan.apply import ApplyResult, apply_board
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


# --- `"liveness"`: a listing that is not a sighting -----------------------------------------
#
# `_apply_listed` treats EVERY listing as positive evidence the posting is alive: it resets
# `consecutive_missing` (D23) and `death_strikes` (D-325), bumps `last_seen_at` and reopens a
# closed row. That premise holds for a fetch and breaks for `lanes/jobapps.py`, which fetches
# nothing — it walks a static local directory and re-lists every record in it on every run, so a
# miss the scanner measured an hour earlier is erased by a file read. Measured on the live store
# before this landed: Twilio #110283 and Cohere #188104 sit on WATCHED boards whose `complete`
# scans no longer list them, and both read `consecutive_missing = 0, status = open`; of the 2,481
# rows this lane created, 2,478 are open and 3 have ever closed, and 90 of the open ones are on
# watched boards whose own evidence is erased every run.
#
# The declaration is what the guard reads, never the lane's name (`SecondhandField`'s reason 3).

LANE_BODY = "We are hiring a backend engineer to work on Python and PostgreSQL services."
#: Both the seeded `last_seen_at` and the assertion target: `_mutable_fields` writes `utcnow()`,
#: so a moved timestamp is any value but this one.
SEEDED = datetime(2026, 9, 1, 12, 0, 0)


def _insert_posting(engine: Engine, company_id: int, *, status: str = "open") -> int:
    """One posting carrying a board-measured miss AND a death strike, last seen at `SEEDED`.

    `content_hash` is the REAL hash of the body the listings below replay, so the revision
    branch stays silent and these tests measure the liveness columns alone.
    """
    with engine.begin() as conn:
        job_id = int(
            conn.execute(insert(tables.jobs).values(created_at=SEEDED)).inserted_primary_key[0]
        )
        return int(
            conn.execute(
                insert(tables.postings).values(
                    company_id=company_id,
                    job_id=job_id,
                    provider_posting_id="p-1",
                    title="Backend Engineer",
                    normalized_title="backend engineer",
                    url="https://boards.greenhouse.io/acme/jobs/p-1",
                    locations_json=["Remote"],
                    remote_policy="remote",
                    first_seen_at=SEEDED,
                    last_seen_at=SEEDED,
                    status=status,
                    closed_at=SEEDED if status == "closed" else None,
                    consecutive_missing=1,
                    death_strikes=1,
                    content_hash=content_hash(LANE_BODY),
                    body_text=LANE_BODY,
                )
            ).inserted_primary_key[0]
        )


def _list_it(
    engine: Engine, company_id: int, secondhand: frozenset[SecondhandField]
) -> ApplyResult:
    """Re-list `p-1` in a lane's `partial` snapshot, declaring `secondhand`."""
    return apply_board(
        engine,
        BoardSnapshot(
            status="partial",
            url="file:///queue",
            postings=[
                RawPosting(
                    provider_posting_id="p-1",
                    title="Backend Engineer",
                    url="https://boards.greenhouse.io/acme/jobs/p-1",
                    locations=["Remote"],
                    body_text=LANE_BODY,
                    raw_json={},
                    secondhand=secondhand,
                )
            ],
        ),
        company_id,
        insert_run(engine),
        scan_kind="lane",
    )


def _liveness_columns(engine: Engine, posting_id: int) -> tuple[int, int, object, str, object]:
    with engine.connect() as conn:
        row = conn.execute(
            select(
                tables.postings.c.consecutive_missing,
                tables.postings.c.death_strikes,
                tables.postings.c.last_seen_at,
                tables.postings.c.status,
                tables.postings.c.closed_at,
            ).where(tables.postings.c.id == posting_id)
        ).one()
    return (
        int(row.consecutive_missing), int(row.death_strikes), row.last_seen_at,
        str(row.status), row.closed_at,
    )


def _events(engine: Engine, posting_id: int) -> list[str]:
    with engine.connect() as conn:
        return [
            str(r.kind)
            for r in conn.execute(
                select(tables.posting_events.c.kind)
                .where(tables.posting_events.c.posting_id == posting_id)
                .order_by(tables.posting_events.c.id)
            )
        ]


def test_a_declared_listing_erases_no_evidence_the_scanner_measured(engine: Engine) -> None:
    """The defect, stated as the three columns it touched: a file read is not a sighting.

    `consecutive_missing` is the board scan's own count, `death_strikes` the probe's, and
    `last_seen_at` is what `postings stale` and the digest read. All three are the scanner's
    measurement of a board this observation never asked.
    """
    company_id = _insert_company(engine)
    posting_id = _insert_posting(engine, company_id)

    _list_it(engine, company_id, frozenset({"liveness"}))

    assert _liveness_columns(engine, posting_id) == (1, 1, SEEDED, "open", None)


def test_a_declared_listing_leaves_a_closed_posting_closed(engine: Engine) -> None:
    """The reopen is the same premise and the costlier half of it.

    `delivery/review_gate.py` drains `_closed` from the queue automatically (D-383), so a row
    this lane reopens every run is a dead lead that can never leave the apply lane. The
    `reopened` event is withheld too: an event log that records a reopen the store did not
    perform is worse than silence, because the ledger is read as history.
    """
    company_id = _insert_company(engine)
    posting_id = _insert_posting(engine, company_id, status="closed")

    result = _list_it(engine, company_id, frozenset({"liveness"}))

    assert _liveness_columns(engine, posting_id) == (1, 1, SEEDED, "closed", SEEDED)
    assert result.reopened == 0
    assert _events(engine, posting_id) == []


def test_a_tier_one_declaration_withholds_every_column_and_still_applies(
    engine: Engine,
) -> None:
    """The shape `lanes/jobapps.py` tier 1 actually emits: every column PLUS `"liveness"`.

    Nothing is left to write, and an empty `values` is not a no-op: SQLAlchemy emits `UPDATE
    postings SET  WHERE postings.id = ?` and SQLite answers `near "WHERE": syntax error`, which
    aborts the board's whole transaction. Pinned because this is the only declaration that
    empties the dict, and it is the production one.
    """
    company_id = _insert_company(engine)
    posting_id = _insert_posting(engine, company_id)

    result = _list_it(engine, company_id, CONVERGED_SECONDHAND | {"liveness"})

    assert result.listed == 1
    assert result.revised == 0
    assert _liveness_columns(engine, posting_id) == (1, 1, SEEDED, "open", None)


def test_an_undeclared_listing_still_clears_both_counters_and_reopens(engine: Engine) -> None:
    """CONTROL — a board scan and every live-index lane must behave exactly as before.

    A provider reading the employer's own board, hiring.cafe re-fetching it, and the
    LinkedIn / Indeed / jsonld lanes served by a live index are all genuine sightings. If this
    goes red the change has stopped being keyed on the declaration.
    """
    company_id = _insert_company(engine)
    posting_id = _insert_posting(engine, company_id, status="closed")

    result = _list_it(engine, company_id, frozenset())

    missing, strikes, last_seen, status, closed_at = _liveness_columns(engine, posting_id)
    assert (missing, strikes, status, closed_at) == (0, 0, "open", None)
    assert last_seen != SEEDED  # bumped to `utcnow()`
    assert result.reopened == 1
    assert _events(engine, posting_id) == ["reopened"]
