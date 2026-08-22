"""Read-only: join the latest `board_scans` row per watched board to what the store holds.

The only data-access path behind `boardwatch coverage`. Every statement here is a SELECT;
nothing is inserted, updated, or committed — `coverage` is a read-only command, unlike
`doctor` (`cli/doctor_cmd.py`), which writes `companies.last_health` as a side effect.
"""

from __future__ import annotations

from sqlalchemy import Connection, func, select

from boardwatch.reports.board_coverage import BoardCoverage, classify_board
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
    raise ValueError(f"board_total_censored must be 0, 1, or NULL; got {raw!r}")


def load_board_coverage(conn: Connection, *, run_id: int | None = None) -> list[BoardCoverage]:
    """Every watched board's coverage verdict for one scan run (default: the latest run that
    has any `board_scans` rows).

    `held` is counted straight out of `postings` (status='open'), independently of whatever the
    scan itself wrote to `board_scans.postings_listed` — the same "count the deliverable through
    a different path than the one that produced it" rule `run_funnel_queries.py` follows.
    """
    if run_id is None:
        run_id = conn.execute(select(func.max(board_scans.c.run_id))).scalar_one_or_none()
    held_stmt = (
        select(postings.c.company_id, func.count())
        .where(postings.c.status == "open")
        .group_by(postings.c.company_id)
    )
    held_by_company: dict[int, int] = {row[0]: row[1] for row in conn.execute(held_stmt).all()}
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
        .select_from(companies.join(board_scans, board_scans.c.company_id == companies.c.id))
        .where(board_scans.c.run_id == run_id)
        .where(companies.c.watched.is_(True))
    ).all()
    out: list[BoardCoverage] = []
    for r in rows:
        held = int(held_by_company.get(r.id, 0))
        censored = _resolve_censored(r.board_total_censored)
        bucket = classify_board(
            status=str(r.status),
            board_reported_total=r.board_reported_total,
            board_enumerated=r.board_enumerated,
            held=held,
            censored=censored,
        )
        measured = bucket == "measured"
        out.append(
            BoardCoverage(
                company_id=int(r.id),
                name=str(r.name),
                provider=str(r.provider),
                bucket=bucket,
                held=held,
                board_reported_total=r.board_reported_total,
                board_enumerated=r.board_enumerated,
                detail_deferred=r.detail_deferred,
                shortfall=(r.board_reported_total - held) if measured else None,
                ratio=(held / r.board_reported_total)
                if measured and r.board_reported_total
                else None,
            )
        )
    return out
