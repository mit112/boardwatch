"""Buried-good-lead detector (unattended observability).

The final gate judges `gate.depth` leads a run and only `--top` are delivered, so a posting the
judge cleared — `eligible`, seniority fit `yes` — can rank below the cut every run until its
requisition comes down. Nothing else sees that: the lead was never delivered, so no delivery or
lane detector counts it, and its closing is an ordinary scan event. Measured 2026-09-26: 6 such
postings closed over runs 43-480 with no signal anywhere.

A SOFT alert when at least one judge-cleared, never-built posting closed since the previous clean
run — `buried_closed` grew, i.e. a good job was lost this run. Growth is read off `closed_at`
rather than off a count stored by the previous run, so a re-judge or a sibling build that shrinks
the population cannot mask a loss in the same run, and no new column is needed.

It never sets `fatal`: the run succeeded, and the loss is a ranking outcome to look at, not a
fault that should trip the dead-man's switch.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.engine import Engine

from boardwatch.core.settings import Settings
from boardwatch.store.buried_queries import buried_good_leads
from boardwatch.store.queries import RUN_OK
from boardwatch.store.tables import runs


def check_buried_good_lead(engine: Engine, settings: Settings, *, run_id: int) -> str | None:
    """Return a soft-alert string when a judge-cleared, never-delivered posting closed after the
    newest clean run before `run_id` finished, else ``None``.

    No earlier clean run abstains: on a fresh store "since the previous run" is all of history,
    and reporting every past closure as this run's loss would be a false alarm.
    """
    with engine.connect() as conn:
        since = conn.execute(
            select(runs.c.finished_at)
            .where(runs.c.status == RUN_OK, runs.c.id < run_id)
            .order_by(runs.c.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if since is None:
            return None
        buried = buried_good_leads(conn, settings)
    lost = sorted(pid for pid, closed_at in buried.closed.items() if closed_at > since)
    if not lost:
        return None
    ids = ", ".join(str(pid) for pid in lost)
    return (
        f"buried: {len(lost)} judge-cleared lead(s) closed since the previous clean run without "
        f"ever being delivered (posting {ids}) — {len(buried.open)} more are eligible, "
        f"seniority-fit and still open below the delivery cut"
    )
