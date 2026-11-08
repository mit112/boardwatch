"""Explicit job-scoped owner holds, independent of skips, reports and applications.

Only explicit release restores admission; JD/profile/policy changes do not erase owner intent.
Callers own transactions. A hold cannot cancel work that has already passed its execution check.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import Connection, select

from boardwatch.store.app_state import set_state
from boardwatch.store.tables import app_state, postings

HOLD_KEY_PREFIX = "queue.held."


class OwnerHoldError(ValueError):
    """Held work or unreadable owner intent cannot authorize a build."""


class OwnerHold(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1]
    reason: str = Field(min_length=1)
    held_at: datetime
    released_at: datetime | None = None


def owner_holds(conn: Connection, *, include_released: bool = False) -> dict[int, OwnerHold]:
    """Read the independent audit/drain in one statement; malformed intent fails visibly."""
    records: dict[int, OwnerHold] = {}
    for row in conn.execute(select(app_state.c.key, app_state.c.value).where(
        app_state.c.key.like(f"{HOLD_KEY_PREFIX}%")
    )):
        suffix = str(row.key)[len(HOLD_KEY_PREFIX):]
        if not suffix.isdecimal():
            continue
        try:
            record = OwnerHold.model_validate_json(row.value or "")
        except ValidationError as exc:
            raise OwnerHoldError(f"unreadable owner hold for job {suffix}") from exc
        if include_released or record.released_at is None:
            records[int(suffix)] = record
    return records


def hold_job(conn: Connection, *, job_id: int, reason: str, at: datetime) -> None:
    record = OwnerHold(version=1, reason=reason.strip(), held_at=at)
    set_state(conn, f"{HOLD_KEY_PREFIX}{job_id}", record.model_dump_json())


def release_job_hold(conn: Connection, *, job_id: int, at: datetime) -> None:
    record = owner_holds(conn).get(job_id)
    if record is not None:
        released = record.model_copy(update={"released_at": at})
        set_state(conn, f"{HOLD_KEY_PREFIX}{job_id}", released.model_dump_json())


def require_unheld_posting(conn: Connection, posting_id: int) -> None:
    job = conn.execute(
        select(postings.c.job_id).where(postings.c.id == posting_id)
    ).scalar_one_or_none()
    hold = owner_holds(conn).get(int(job)) if job is not None else None
    if hold is not None:
        raise OwnerHoldError(f"posting {posting_id} is held by its owner: {hold.reason}")
