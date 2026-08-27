"""Review-queue skip state, stored on the generic `app_state` KV table.

Skip deliberately does NOT live in `applications`. Two independent reasons, and either one
alone would be enough:

* `ApplicationStatus` is a closed catalog and `applications` carries a matching CHECK
  constraint, so adding a `skipped` member means a full SQLite table rebuild — for state that
  is neither a decision about an employer nor part of the immutable event log.
* An `applications` row asserts "I engaged with this employer", which is the opposite of what
  skipping a lead says. `applied_job_ids` and the funnel both read that table as conversions;
  a skip landing in it would inflate every one of those counts.

So a skip is one row: `queue.skipped.<job_id>` -> the ISO-8601 instant it was skipped. Keyed
on the canonical `job_id`, matching `applications`, so a skip survives its posting being
revised, closed, or regrouped. Skip and applied are independent dimensions and a job may be
both; nothing here reads `applications`.

Functions take the caller's open Connection and never begin or commit.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Connection, delete, select

from boardwatch.store.app_state import set_state
from boardwatch.store.tables import app_state

SKIP_KEY_PREFIX = "queue.skipped."


def _skip_key(job_id: int) -> str:
    return f"{SKIP_KEY_PREFIX}{job_id}"


def mark_job_skipped(conn: Connection, *, job_id: int, at: datetime) -> None:
    """Skip a job. Idempotent: a repeat re-stamps `at` rather than failing on the text PK."""
    set_state(conn, _skip_key(job_id), at.isoformat())


def unmark_job_skipped(conn: Connection, *, job_id: int) -> None:
    """Un-skip a job. A job that was never skipped is a no-op, not an error."""
    conn.execute(delete(app_state).where(app_state.c.key == _skip_key(job_id)))


def skipped_job_ids(conn: Connection) -> dict[int, str]:
    """job_id -> the ISO-8601 instant it was skipped, for every skipped job.

    ONE statement for the whole set: the queue holds hundreds of leads and asks this question
    once per render, so a key lookup per job would be hundreds of round trips. The prefix
    contains no LIKE metacharacter (`%` or `_`), so it needs no ESCAPE clause.

    `app_state` is shared with the digest and notify cursors, so the prefix match is a filter
    over a mixed namespace and anything that is not a skip key is ignored. A key whose suffix
    is not a decimal integer is ignored too: `isdecimal` rather than `isdigit` because
    `"²".isdigit()` is True while `int("²")` raises, which would turn one hand-edited row into
    a crashed queue.
    """
    rows = conn.execute(
        select(app_state.c.key, app_state.c.value).where(
            app_state.c.key.like(f"{SKIP_KEY_PREFIX}%")
        )
    ).all()
    skipped: dict[int, str] = {}
    for row in rows:
        suffix = str(row.key)[len(SKIP_KEY_PREFIX) :]
        if not suffix.isdecimal():
            continue
        # The key's presence is the skip; `value` is nullable, so a NULL reads as no timestamp
        # rather than un-skipping the job.
        skipped[int(suffix)] = "" if row.value is None else str(row.value)
    return skipped
