"""Read-only: join the latest `board_scans` row per watched board to what the store holds.

The only data-access path behind `boardwatch coverage`. Every statement here is a SELECT;
nothing is inserted, updated, or committed — `coverage` is a read-only command, unlike
`doctor` (`cli/doctor_cmd.py`), which writes `companies.last_health` as a side effect.

Fix round 1, finding 1: this is a LEFT JOIN from `companies`, never an INNER JOIN on
`board_scans`. `scan/coordinator.py`'s `run_scan(company=..., provider=...)` mints a fresh
`run_id` containing rows for only the filtered subset, so an inner join silently dropped every
other watched board from the corpus the moment someone ran `boardwatch scan --company X`
followed by a bare `boardwatch coverage` (which defaults to the latest run). A board with no
`board_scans` row for the selected run is classified `unscanned` — see `classify_board`.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, Row, func, select

from boardwatch.reports.board_coverage import (
    BoardCoverage,
    ContradictoryCoverage,
    UnknownCensorFlag,
    UnknownScanStatus,
    classify_board,
)
from boardwatch.store.tables import board_scans, companies, postings


def _resolve_censored(raw: int | None) -> bool:
    """`board_scans.board_total_censored` is a tri-state, not a bool: `1` (the provider states
    its total is censored), `0` (the provider states it is NOT censored), or `NULL` (the
    provider made no claim either way — most providers have no concept of a censored total).

    `classify_board` only accepts a plain `bool`, so both `0` and `NULL` end up steering
    classification the same way (onward to the size-based checks rather than straight to
    `"censored"`) — but they are not the same claim, and collapsing them with a bare `bool(raw)`
    would blur that distinction by accident instead of by decision. Branching explicitly here
    keeps the NULL case visible to the next reader, and raises loudly if the column ever holds
    anything else rather than silently misreading it as either state.
    """
    if raw is None or raw == 0:
        return False
    if raw == 1:
        return True
    raise UnknownCensorFlag(raw)


def load_board_coverage(conn: Connection, *, run_id: int | None = None) -> list[BoardCoverage]:
    """Every watched board's coverage verdict for one scan run (default: the latest run that
    has any `board_scans` rows).

    `held` is counted straight out of `postings` (status='open'), independently of whatever the
    scan itself wrote to `board_scans.postings_listed` — the same "count the deliverable through
    a different path than the one that produced it" rule `run_funnel_queries.py` follows.
    """
    if run_id is None:
        # The latest run that BOARD-scanned something. A run whose only board_scans rows are a
        # lane's has measured no board, so defaulting to it would report the whole corpus
        # `unscanned` — a WHERE is safe here because this aggregate never sees a NULL run_id.
        run_id = conn.execute(
            select(func.max(board_scans.c.run_id)).where(board_scans.c.scan_kind == "board")
        ).scalar_one_or_none()
    held_stmt = (
        select(postings.c.company_id, func.count())
        .where(postings.c.status == "open")
        .group_by(postings.c.company_id)
    )
    held_by_company: dict[int, int] = {row[0]: row[1] for row in conn.execute(held_stmt).all()}
    # LEFT JOIN: a watched company with no board_scans row for run_id (never scanned this run,
    # not scanned-and-failed) must still appear in the corpus. The join condition carries the
    # run filter — putting `run_id` in a WHERE instead would silently turn this back into an
    # inner join, since SQL compares NULL = run_id as NULL (dropped), not true.
    #
    # `scan_kind` rides the SAME join condition for the SAME reason (D-285). A lane writes its
    # own board_scans row, and when it touches an already-watched board that is a second row
    # for one (company_id, run_id) — one BoardCoverage each, so the company is counted twice
    # and corpus_boards inflates. Only board scans measure a board's coverage; a lane samples
    # an aggregator and makes no claim about the board's total.
    join_condition = (
        (board_scans.c.company_id == companies.c.id)
        & (board_scans.c.run_id == run_id)
        & (board_scans.c.scan_kind == "board")
    )
    rows = conn.execute(
        select(
            companies.c.id,
            companies.c.name,
            companies.c.provider,
            board_scans.c.status,
            board_scans.c.board_reported_total,
            board_scans.c.board_enumerated,
            board_scans.c.detail_deferred,
            board_scans.c.board_total_censored,
        )
        .select_from(companies.outerjoin(board_scans, join_condition))
        .where(companies.c.watched.is_(True))
    ).all()
    out: list[BoardCoverage] = []
    for r in rows:
        held = int(held_by_company.get(r.id, 0))
        try:
            out.append(_board_coverage(r, held))
        except (UnknownScanStatus, ContradictoryCoverage, UnknownCensorFlag):
            # ONE board degrades, never the whole report. Reproduced with a two-board store
            # holding a single `board_reported_total=-5` row: the exception escaped this
            # function and the healthy board's coverage became unreachable — a single bad row
            # hiding the other 134. The row keeps its raw column values so the defect stays
            # debuggable, and lands in `unreadable` rather than being dropped or folded into a
            # bucket that would make a claim about it (`dark` says "the scan failed"; this scan
            # may well have succeeded and written a column we cannot read). `UnknownCensorFlag`
            # joins this tuple for the same reason: `board_total_censored` carries no
            # CheckConstraint (`store/tables.py`), so a malformed value there reached
            # `_resolve_censored` and crashed the whole report exactly the way an unknown
            # status once did.
            out.append(
                BoardCoverage(
                    company_id=int(r.id),
                    name=str(r.name),
                    provider=str(r.provider),
                    bucket="unreadable",
                    held=held,
                    board_reported_total=r.board_reported_total,
                    board_enumerated=r.board_enumerated,
                    detail_deferred=r.detail_deferred,
                    shortfall=None,
                    ratio=None,
                )
            )
    return out


def _board_coverage(r: Row[Any], held: int) -> BoardCoverage:
    censored = _resolve_censored(r.board_total_censored)
    # r.status is None when the LEFT JOIN found no board_scans row at all for this run —
    # classify_board's first check turns that into "unscanned", never "measured" or "dark".
    bucket = classify_board(
        status=r.status, board_reported_total=r.board_reported_total, censored=censored
    )
    stated = r.board_reported_total
    # A shortfall needs a stated total to be a gap FROM, and `censored` boards now publish one:
    # their facet-recovered total is a real number (Citi 4,589) even though no RATIO is
    # published against it, and while shortfall was `measured`-only the biggest hole in the
    # corpus reached no summary line. `board_coverage.BoardCoverage.__post_init__` pins the
    # same pairing, so a caller that gets this wrong raises rather than under-reports.
    bears_shortfall = bucket in ("measured", "censored") and stated is not None
    return BoardCoverage(
        company_id=int(r.id),
        name=str(r.name),
        provider=str(r.provider),
        bucket=bucket,
        held=held,
        board_reported_total=stated,
        board_enumerated=r.board_enumerated,
        detail_deferred=r.detail_deferred,
        shortfall=(stated - held) if bears_shortfall else None,
        ratio=(held / stated) if bucket == "measured" and stated else None,
    )
