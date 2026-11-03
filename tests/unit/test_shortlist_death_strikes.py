"""D-665: the shortlist probe's answers count toward the sweep's two-strike close.

What is under test is that it inherits every narrowing of D-325, because each is a way a daily
probe of the highest-ranked postings could quietly start closing live jobs.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from itertools import count
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert, select, update

from boardwatch.core.clock import utcnow
from boardwatch.core.liveness import Liveness
from boardwatch.pipeline.death_probe import (
    CLOSING_SIGNALS,
    LISTING_ENDPOINTS,
    strike_from_shortlist,
)
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import insert_run

TTL = 24
_serial = count()


def _dead(pid: int, signal: str = "refetch_gone") -> Liveness:
    return Liveness(posting_id=pid, verdict="dead", signal=signal, detail="gone")


def _alive(pid: int) -> Liveness:
    return Liveness(posting_id=pid, verdict="alive", signal="refetch_ok", detail="HTTP 200")


def _unknown(pid: int, signal: str = "refetch_error") -> Liveness:
    return Liveness(posting_id=pid, verdict="unknown", signal=signal, detail="timeout")


@pytest.fixture
def engine(tmp_path: Path) -> Engine:
    built = get_engine(tmp_path / "data")
    ensure_schema(built)
    return built


def _posting(
    engine: Engine,
    *,
    provider: str = "linkedin",
    watched: bool = False,
    status: str = "open",
    strikes: int = 0,
    probed_hours_ago: float | None = None,
) -> int:
    now = utcnow()
    serial = next(_serial)
    with engine.begin() as conn:
        company = conn.execute(
            insert(tables.companies).values(
                name="Acme",
                provider=provider,
                slug=f"acme-{serial}",
                source="lane",
                watched=watched,
            )
        ).inserted_primary_key[0]
        job = conn.execute(insert(tables.jobs).values(created_at=now)).inserted_primary_key[0]
        return int(
            conn.execute(
                insert(tables.postings).values(
                    company_id=company,
                    job_id=job,
                    provider_posting_id=f"p-{serial}",
                    title="Backend Engineer",
                    normalized_title="backend engineer",
                    url="https://example.test/j/1",
                    locations_json=["Remote"],
                    remote_policy="remote",
                    first_seen_at=now,
                    last_seen_at=now,
                    status=status,
                    consecutive_missing=0,
                    death_strikes=strikes,
                    last_death_probe_at=(
                        None
                        if probed_hours_ago is None
                        else now - timedelta(hours=probed_hours_ago)
                    ),
                    content_hash="h",
                    body_text="body",
                )
            ).inserted_primary_key[0]
        )


def _row(engine: Engine, pid: int) -> tuple[str, int, datetime | None]:
    with engine.connect() as conn:
        row = conn.execute(
            select(
                tables.postings.c.status,
                tables.postings.c.death_strikes,
                tables.postings.c.last_death_probe_at,
            ).where(tables.postings.c.id == pid)
        ).one()
    return str(row.status), int(row.death_strikes), row.last_death_probe_at


def _closed_events(engine: Engine, pid: int) -> int:
    with engine.connect() as conn:
        return len(
            conn.execute(
                select(tables.posting_events.c.id).where(
                    tables.posting_events.c.posting_id == pid,
                    tables.posting_events.c.kind == "closed",
                )
            ).all()
        )


def _strike(engine: Engine, *results: Liveness) -> tuple[int, int, int]:
    report = strike_from_shortlist(
        engine,
        {r.posting_id: r for r in results},
        run_id=insert_run(engine),
        ttl_hours=TTL,
    )
    return report.struck, report.closed, report.cleared


@pytest.mark.parametrize("signal", sorted(CLOSING_SIGNALS))
def test_each_closing_signal_strikes_and_one_strike_does_not_close(
    engine: Engine, signal: str
) -> None:
    pid = _posting(engine)
    assert _strike(engine, _dead(pid, signal)) == (1, 0, 0)
    status, strikes, stamped = _row(engine, pid)
    assert (status, strikes) == ("open", 1)
    assert stamped is not None
    assert _closed_events(engine, pid) == 0


def test_a_second_strike_a_ttl_later_closes_and_writes_the_event(engine: Engine) -> None:
    pid = _posting(engine, strikes=1, probed_hours_ago=TTL + 1)
    assert _strike(engine, _dead(pid)) == (1, 1, 0)
    assert _row(engine, pid)[:2] == ("closed", 2)
    assert _closed_events(engine, pid) == 1


def test_a_second_strike_inside_the_ttl_is_refused(engine: Engine) -> None:
    """The guard against the sweep and the shortlist closing one row inside a single run."""
    pid = _posting(engine, strikes=1, probed_hours_ago=TTL - 1)
    before = _row(engine, pid)
    assert _strike(engine, _dead(pid)) == (0, 0, 0)
    assert _row(engine, pid) == before


def test_a_short_ttl_cannot_close_a_row_inside_one_slow_run(engine: Engine) -> None:
    """The run began 3 h ago and the sweep struck this row 2 h ago. A 1 h TTL has elapsed; the
    second strike must still wait for another run."""
    pid = _posting(engine, strikes=1, probed_hours_ago=2)
    run_id = insert_run(engine)
    with engine.begin() as conn:
        conn.execute(
            update(tables.runs)
            .where(tables.runs.c.id == run_id)
            .values(started_at=utcnow() - timedelta(hours=3))
        )
    report = strike_from_shortlist(engine, {pid: _dead(pid)}, run_id=run_id, ttl_hours=1)
    assert (report.struck, report.closed) == (0, 0)
    assert _row(engine, pid)[:2] == ("open", 1)


def test_a_short_ttl_still_strikes_a_row_stamped_by_an_earlier_run(engine: Engine) -> None:
    pid = _posting(engine, strikes=1, probed_hours_ago=2)
    report = strike_from_shortlist(
        engine, {pid: _dead(pid)}, run_id=insert_run(engine), ttl_hours=1
    )
    assert (report.struck, report.closed) == (1, 1)


@pytest.mark.parametrize("signal", ["refetch_error", "refetch_gone_after_redirect"])
def test_an_unknown_answer_changes_nothing(engine: Engine, signal: str) -> None:
    pid = _posting(engine, strikes=1, probed_hours_ago=TTL + 1)
    before = _row(engine, pid)
    assert _strike(engine, _unknown(pid, signal)) == (0, 0, 0)
    assert _row(engine, pid) == before


@pytest.mark.parametrize("hours", [TTL - 1, TTL + 1])
def test_an_alive_answer_clears_on_both_sides_of_the_ttl(engine: Engine, hours: int) -> None:
    pid = _posting(engine, strikes=1, probed_hours_ago=hours)
    assert _strike(engine, _alive(pid)) == (0, 0, 1)
    assert _row(engine, pid)[:2] == ("open", 0)


def test_an_alive_answer_inside_the_ttl_does_not_slide_the_stamp(engine: Engine) -> None:
    pid = _posting(engine, strikes=1, probed_hours_ago=TTL - 1)
    before = _row(engine, pid)[2]
    _strike(engine, _alive(pid))
    assert _row(engine, pid)[2] == before


def test_an_alive_answer_past_the_ttl_spends_the_sweeps_turn(engine: Engine) -> None:
    pid = _posting(engine, probed_hours_ago=TTL + 1)
    before = _row(engine, pid)[2]
    assert before is not None
    _strike(engine, _alive(pid))
    after = _row(engine, pid)[2]
    assert after is not None and after > before


def test_a_watched_board_keeps_its_own_closing_path(engine: Engine) -> None:
    dead = _posting(engine, provider="ashby", watched=True, strikes=1, probed_hours_ago=TTL + 1)
    alive = _posting(engine, provider="jobapps", watched=True, strikes=1)
    assert _strike(engine, _dead(dead), _alive(alive)) == (0, 0, 0)
    assert _row(engine, dead)[:2] == ("open", 1)
    assert _row(engine, alive)[:2] == ("open", 1)


@pytest.mark.parametrize("provider", sorted(LISTING_ENDPOINTS))
def test_a_listing_path_row_is_never_touched_by_its_url(engine: Engine, provider: str) -> None:
    """T89: a dead Ashby row's URL answers 200, which must not clear the strike its listing earned."""
    struck = _posting(engine, provider=provider, strikes=1, probed_hours_ago=TTL + 1)
    dead = _posting(engine, provider=provider, strikes=1, probed_hours_ago=TTL + 1)
    assert _strike(engine, _alive(struck), _dead(dead)) == (0, 0, 0)
    assert _row(engine, struck)[:2] == ("open", 1)
    assert _row(engine, dead)[:2] == ("open", 1)


def test_a_row_already_closed_is_left_alone(engine: Engine) -> None:
    pid = _posting(engine, status="closed", strikes=2, probed_hours_ago=TTL + 1)
    assert _strike(engine, _dead(pid)) == (0, 0, 0)
    assert _strike(engine, _alive(pid)) == (0, 0, 0)
    assert _row(engine, pid)[:2] == ("closed", 2)
    assert _closed_events(engine, pid) == 0


def test_only_the_named_postings_change(engine: Engine) -> None:
    named = _posting(engine)
    other = _posting(engine, strikes=1, probed_hours_ago=TTL + 1)
    _strike(engine, _dead(named))
    assert _row(engine, other)[:2] == ("open", 1)
