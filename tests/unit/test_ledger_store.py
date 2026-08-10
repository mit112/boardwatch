"""P6 slice 2: the decision ledger at the store (design §2, §6; §8 claims 4, 5, 6)."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert
from sqlalchemy.exc import IntegrityError

from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.ledger_queries import (
    live_dispositions,
    load_dispositions,
    record_disposition,
    reopen_jobs,
    stale_dispositions,
)

NOW = datetime(2026, 8, 10, 12, 0, 0)
TTL = timedelta(days=7)
POLICY = "policy-abc"


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path)
    ensure_schema(eng)
    return eng


def _seed_job(engine: Engine) -> int:
    with engine.begin() as conn:
        return int(
            conn.execute(insert(tables.jobs).values(created_at=NOW)).inserted_primary_key[0]
        )


def _mark_built(engine: Engine, job_id: int, *, now: datetime = NOW, policy: str = POLICY) -> bool:
    with engine.begin() as conn:
        return record_disposition(
            conn, job_id, disposition="built", reason="lead_built", policy_version=policy, now=now
        )


def _mark_seen(engine: Engine, job_id: int, *, now: datetime = NOW) -> bool:
    with engine.begin() as conn:
        return record_disposition(
            conn, job_id, disposition="seen", reason="surfaced", expires_at=now + TTL, now=now
        )


# --------------------------------------------------------------- upsert round-trip


def test_a_recorded_built_disposition_reads_back_as_live(engine: Engine) -> None:
    job_id = _seed_job(engine)
    assert _mark_built(engine, job_id) is True
    with engine.connect() as conn:
        live = live_dispositions(conn, now=NOW)
    assert live[job_id].disposition == "built"
    assert live[job_id].policy_version == POLICY


def test_built_is_not_downgraded_by_a_later_seen_and_nothing_is_written(engine: Engine) -> None:
    job_id = _seed_job(engine)
    _mark_built(engine, job_id)
    assert _mark_seen(engine, job_id, now=NOW + timedelta(hours=1)) is False
    with engine.connect() as conn:
        assert load_dispositions(conn)[job_id].disposition == "built"


def test_seen_is_raised_to_built_keeping_the_first_decision_time(engine: Engine) -> None:
    job_id = _seed_job(engine)
    _mark_seen(engine, job_id)
    later = NOW + timedelta(days=1)
    _mark_built(engine, job_id, now=later)
    with engine.connect() as conn:
        row = load_dispositions(conn)[job_id]
    assert row.disposition == "built"
    assert row.first_decided_at == NOW
    assert row.decided_at == later
    assert row.expires_at is None


# ------------------------------------------------- lazy read-time expiry (claim 4)


def test_an_expired_seen_row_stops_governing_but_is_not_deleted(engine: Engine) -> None:
    """Lazy expiry: nothing sweeps the table, so the drain can still report the lapsed row."""
    job_id = _seed_job(engine)
    _mark_seen(engine, job_id)
    after = NOW + TTL + timedelta(seconds=1)
    with engine.connect() as conn:
        assert live_dispositions(conn, now=after) == {}
        assert job_id in load_dispositions(conn)


def test_a_seen_row_governs_right_up_to_its_expiry(engine: Engine) -> None:
    job_id = _seed_job(engine)
    _mark_seen(engine, job_id)
    with engine.connect() as conn:
        assert job_id in live_dispositions(conn, now=NOW + TTL - timedelta(seconds=1))


# ------------------------------------------------------------------ the drain (claim 6)


def test_reopen_releases_a_built_job_without_deleting_its_row(engine: Engine) -> None:
    job_id = _seed_job(engine)
    _mark_built(engine, job_id)
    with engine.begin() as conn:
        assert reopen_jobs(conn, [job_id], now=NOW + timedelta(days=1)) == 1
    with engine.connect() as conn:
        assert live_dispositions(conn, now=NOW + timedelta(days=1)) == {}
        stored = load_dispositions(conn)[job_id]
    assert stored.disposition == "built"  # the record survives the drain
    assert stored.reopened_at is not None


def test_reopen_is_idempotent_and_does_not_restamp_an_already_reopened_row(engine: Engine) -> None:
    job_id = _seed_job(engine)
    _mark_built(engine, job_id)
    first = NOW + timedelta(days=1)
    with engine.begin() as conn:
        reopen_jobs(conn, [job_id], now=first)
    with engine.begin() as conn:
        assert reopen_jobs(conn, [job_id], now=NOW + timedelta(days=2)) == 0
    with engine.connect() as conn:
        assert load_dispositions(conn)[job_id].reopened_at == first


def test_a_reopened_job_can_be_decided_again_and_becomes_live(engine: Engine) -> None:
    job_id = _seed_job(engine)
    _mark_built(engine, job_id)
    with engine.begin() as conn:
        reopen_jobs(conn, [job_id], now=NOW + timedelta(days=1))
    later = NOW + timedelta(days=2)
    assert _mark_seen(engine, job_id, now=later) is True
    with engine.connect() as conn:
        row = live_dispositions(conn, now=later)[job_id]
    assert row.disposition == "seen"
    assert row.reopened_at is None


def test_stale_lists_only_permanent_rows_whose_stamp_moved(engine: Engine) -> None:
    """A stamp mismatch is reported, never auto-expired (design §2.4)."""
    current, moved, ttl_job = _seed_job(engine), _seed_job(engine), _seed_job(engine)
    _mark_built(engine, current, policy=POLICY)
    _mark_built(engine, moved, policy="policy-old")
    _mark_seen(engine, ttl_job)
    with engine.connect() as conn:
        stale = stale_dispositions(conn, policy_version=POLICY, now=NOW)
        assert set(stale) == {moved}
        # and the stale row still governs — listing is not releasing
        assert moved in live_dispositions(conn, now=NOW)


def test_a_reopened_row_is_not_reported_as_stale(engine: Engine) -> None:
    job_id = _seed_job(engine)
    _mark_built(engine, job_id, policy="policy-old")
    with engine.begin() as conn:
        reopen_jobs(conn, [job_id], now=NOW)
    with engine.connect() as conn:
        assert stale_dispositions(conn, policy_version=POLICY, now=NOW) == {}


# ------------------------------------------- the store enforces the contract too (claim 5)


def _raw_insert(engine: Engine, job_id: int, **overrides: object) -> None:
    values: dict[str, object] = {
        "job_id": job_id,
        "disposition": "built",
        "reason": "lead_built",
        "policy_version": POLICY,
        "expires_at": None,
        "reopened_at": None,
        "first_decided_at": NOW,
        "decided_at": NOW,
        "run_id": None,
    }
    values.update(overrides)
    with engine.begin() as conn:
        conn.execute(insert(tables.job_dispositions).values(**values))


def test_a_permanent_disposition_without_a_policy_stamp_is_rejected_by_the_store(
    engine: Engine,
) -> None:
    """Enforced twice on purpose: typed in core.ledger AND here, so a direct INSERT that skips
    the writer cannot store a permanent decision with no stamp."""
    job_id = _seed_job(engine)
    with pytest.raises(IntegrityError):
        _raw_insert(engine, job_id, policy_version=None)


def test_a_seen_row_without_a_ttl_is_rejected_by_the_store(engine: Engine) -> None:
    job_id = _seed_job(engine)
    with pytest.raises(IntegrityError):
        _raw_insert(engine, job_id, disposition="seen", reason="surfaced", policy_version=None)


def test_a_seen_row_carrying_a_policy_stamp_is_rejected_by_the_store(engine: Engine) -> None:
    job_id = _seed_job(engine)
    with pytest.raises(IntegrityError):
        _raw_insert(
            engine,
            job_id,
            disposition="seen",
            reason="surfaced",
            expires_at=NOW + TTL,
            policy_version=POLICY,
        )


def test_an_out_of_catalog_disposition_is_rejected_by_the_store(engine: Engine) -> None:
    job_id = _seed_job(engine)
    with pytest.raises(IntegrityError):
        _raw_insert(engine, job_id, disposition="dismissed", reason="lead_built")


def test_an_out_of_catalog_reason_is_rejected_by_the_store(engine: Engine) -> None:
    job_id = _seed_job(engine)
    with pytest.raises(IntegrityError):
        _raw_insert(engine, job_id, reason="because_i_said_so")


def test_a_disposition_for_a_nonexistent_job_is_rejected(engine: Engine) -> None:
    with pytest.raises(IntegrityError):
        _raw_insert(engine, 999999)
