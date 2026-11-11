"""Closed-twin triage (D-691): queue the wrapper for the probe, never close it from the match.

The rule is Plan 03's matcher asked of every status: a lane wrapper whose ONLY place-matching
employer posting is closed is a suspicion. An employer reposts under a new requisition, so the
wrapper may be live while its old twin retired; only the existing probe's own evidence closes one.
Every fixture name and URL below is made up.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, insert, select, update

from boardwatch.core.liveness import Liveness
from boardwatch.pipeline.death_probe import sweep_unwatched_deaths
from boardwatch.pipeline.local_twin import find_closed_twin_wrappers
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import insert_run
from boardwatch.store.tables import companies, jobs, postings

NOW = datetime(2026, 11, 10, 12, 0, 0)
WRAPPER_URL = "https://www.linkedin.com/jobs/view/4000000001"


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path / "data")
    ensure_schema(eng)
    return eng


def _company(
    conn: Connection, name: str, provider: str, *, watched: bool = True
) -> int:
    return int(
        conn.execute(
            insert(companies).values(
                name=name,
                provider=provider,
                slug=f"{provider}-{name.lower().replace(' ', '-')}",
                source="user",
                watched=watched,
            )
        ).inserted_primary_key[0]
    )


def _posting(
    conn: Connection,
    company_id: int,
    key: str,
    *,
    title: str = "Software Engineer",
    locations: list[str] | None = None,
    url: str | None = None,
    status: str = "open",
    remote_policy: str = "unknown",
) -> int:
    job = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
    return int(
        conn.execute(
            insert(postings).values(
                company_id=company_id,
                job_id=job,
                provider_posting_id=key,
                title=title,
                normalized_title=title.lower(),
                url=url or f"https://boards.example.com/acme/jobs/{key}",
                locations_json=["Austin, TX"] if locations is None else locations,
                remote_policy=remote_policy,
                first_seen_at=NOW,
                last_seen_at=NOW,
                status=status,
                closed_at=NOW if status == "closed" else None,
                consecutive_missing=0,
                death_strikes=0,
                content_hash=f"hash-{key}",
                body_text="body",
            )
        ).inserted_primary_key[0]
    )


def _wrapper(
    conn: Connection, *, locations: list[str] | None = None, status: str = "open"
) -> int:
    lane = _company(conn, "Acme", "linkedin", watched=False)
    return _posting(conn, lane, "w1", url=WRAPPER_URL, locations=locations, status=status)


def _queued(engine: Engine, ids: list[int], **kwargs: object) -> tuple[int, ...]:
    with engine.connect() as conn:
        return find_closed_twin_wrappers(conn, ids, **kwargs)  # type: ignore[arg-type]


def test_a_wrapper_whose_only_twin_is_closed_is_queued(engine: Engine) -> None:
    with engine.begin() as conn:
        board = _company(conn, "Acme", "greenhouse")
        _posting(conn, board, "t1", locations=["US,TX,Austin"], status="closed")
        wrapper = _wrapper(conn)
    assert _queued(engine, [wrapper]) == (wrapper,)


def test_an_open_twin_is_the_local_twin_writers_case_not_this_one(engine: Engine) -> None:
    with engine.begin() as conn:
        board = _company(conn, "Acme", "greenhouse")
        _posting(conn, board, "t1", locations=["US,TX,Austin"], status="open")
        wrapper = _wrapper(conn)
    assert _queued(engine, [wrapper]) == ()


def test_two_matching_twins_are_not_one_even_when_both_are_closed(engine: Engine) -> None:
    """A second requisition in the same place is exactly the repost this rule refuses to read."""
    with engine.begin() as conn:
        board = _company(conn, "Acme", "greenhouse")
        _posting(conn, board, "t1", locations=["US,TX,Austin"], status="closed")
        _posting(conn, board, "t2", locations=["Austin, Texas, United States"], status="closed")
        wrapper = _wrapper(conn)
    assert _queued(engine, [wrapper]) == ()


def test_a_closed_twin_in_another_city_is_not_a_match(engine: Engine) -> None:
    with engine.begin() as conn:
        board = _company(conn, "Acme", "greenhouse")
        _posting(conn, board, "t1", locations=["Denver, CO"], status="closed")
        wrapper = _wrapper(conn)
    assert _queued(engine, [wrapper]) == ()


def test_a_wrapper_with_a_destination_is_not_queued(engine: Engine) -> None:
    from boardwatch.store.application_destinations import record_application_destination

    with engine.begin() as conn:
        board = _company(conn, "Acme", "greenhouse")
        _posting(conn, board, "t1", locations=["US,TX,Austin"], status="closed")
        wrapper = _wrapper(conn)
        record_application_destination(
            conn,
            posting_id=wrapper,
            url="https://employer.example.com/job/1",
            source_url=WRAPPER_URL,
            evidence_ref="browser:verified",
            verified_at=NOW,
        )
    assert _queued(engine, [wrapper]) == ()


def test_a_wrapper_naming_its_own_requisition_is_not_queued(engine: Engine) -> None:
    with engine.begin() as conn:
        board = _company(conn, "Acme", "greenhouse")
        _posting(conn, board, "t1", locations=["US,TX,Austin"], status="closed")
        lane = _company(conn, "Acme", "linkedin", watched=False)
        wrapper = _posting(
            conn, lane, "CHINUSR30757", url="https://boards.greenhouse.io/acme/jobs/7000002"
        )
    assert _queued(engine, [wrapper]) == ()


def test_an_applied_wrapper_is_not_queued(engine: Engine) -> None:
    with engine.begin() as conn:
        board = _company(conn, "Acme", "greenhouse")
        _posting(conn, board, "t1", locations=["US,TX,Austin"], status="closed")
        wrapper = _wrapper(conn)
        job_id = int(
            conn.execute(select(postings.c.job_id).where(postings.c.id == wrapper)).scalar_one()
        )
    assert _queued(engine, [wrapper], exclude_job_ids=frozenset({job_id})) == ()


# --- the probe, not the match, decides ------------------------------------------------------


def _alive(posting_id: int, url: str) -> Liveness:
    return Liveness(posting_id=posting_id, verdict="alive", signal="refetch_ok")


def _gone(posting_id: int, url: str) -> Liveness:
    return Liveness(posting_id=posting_id, verdict="dead", signal="refetch_gone")


def _sweep(
    engine: Engine,
    prober: object,
    *,
    priority_ids: frozenset[int],
    budget: int = 10,
) -> object:
    return sweep_unwatched_deaths(
        engine,
        prober=prober,  # type: ignore[arg-type]
        listing_prober=None,
        run_id=insert_run(engine),
        budget=budget,
        company_budget=0,
        ttl_hours=24,
        priority_ids=priority_ids,
    )


def _unwatched_posting(engine: Engine, key: str) -> int:
    with engine.begin() as conn:
        company = _company(conn, f"Employer {key}", "jobapps", watched=False)
        return _posting(conn, company, key, url=f"https://jobs.example.test/{key}")


def _state(engine: Engine, posting_id: int) -> tuple[str, int, object]:
    with engine.connect() as conn:
        row = conn.execute(
            select(postings.c.status, postings.c.death_strikes, postings.c.last_death_probe_at)
            .where(postings.c.id == posting_id)
        ).one()
    return str(row.status), int(row.death_strikes), row.last_death_probe_at


def test_the_priority_reorders_the_budget_and_never_widens_it(engine: Engine) -> None:
    first = _unwatched_posting(engine, "first")
    priority = _unwatched_posting(engine, "priority")  # a LARGER id, so id order would miss it
    probed: list[int] = []

    def probe(posting_id: int, url: str) -> Liveness:
        probed.append(posting_id)
        return Liveness(posting_id=posting_id, verdict="alive", signal="refetch_ok")

    with engine.begin() as conn:
        # The id order the sweep would otherwise use puts `first` at the head of the queue.
        conn.execute(
            update(postings)
            .where(postings.c.id.in_([first, priority]))
            .values(last_death_probe_at=None)
        )
    _sweep(engine, probe, priority_ids=frozenset({priority}), budget=1)
    assert probed == [priority]


def test_an_alive_probe_still_serves_a_prioritised_wrapper(engine: Engine) -> None:
    """Two alive answers later the wrapper is open with no strike: the match closed nothing."""
    posting_id = _unwatched_posting(engine, "wrapper")
    _sweep(engine, _alive, priority_ids=frozenset({posting_id}))
    with engine.begin() as conn:
        conn.execute(
            update(postings)
            .where(postings.c.id == posting_id)
            .values(last_death_probe_at=NOW - timedelta(hours=25))
        )
    _sweep(engine, _alive, priority_ids=frozenset({posting_id}))
    assert _state(engine, posting_id)[:2] == ("open", 0)


def test_a_prioritised_wrapper_closes_only_on_the_probes_second_gone(engine: Engine) -> None:
    posting_id = _unwatched_posting(engine, "wrapper")
    _sweep(engine, _gone, priority_ids=frozenset({posting_id}))
    assert _state(engine, posting_id)[:2] == ("open", 1)
    with engine.begin() as conn:
        conn.execute(
            update(postings)
            .where(postings.c.id == posting_id)
            .values(last_death_probe_at=NOW - timedelta(hours=25))
        )
    _sweep(engine, _gone, priority_ids=frozenset({posting_id}))
    assert _state(engine, posting_id)[:2] == ("closed", 2)


def test_a_priority_id_outside_the_due_set_is_not_probed(engine: Engine) -> None:
    """A watched board has its own closing path; the priority may not widen the sweep's class."""
    with engine.begin() as conn:
        watched = _company(conn, "Watched Co", "jobapps", watched=True)
        posting_id = _posting(conn, watched, "watched", url="https://jobs.example.test/w")
    probed: list[int] = []

    def probe(pid: int, url: str) -> Liveness:
        probed.append(pid)
        return Liveness(posting_id=pid, verdict="alive", signal="refetch_ok")

    _sweep(engine, probe, priority_ids=frozenset({posting_id}))
    assert probed == []
