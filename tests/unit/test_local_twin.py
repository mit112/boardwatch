"""The local twin link writer (D-689): a lane copy gets its employer posting's URL, or nothing.

Every negative below has the shape of a real past false match; the names and URLs are made up.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import Connection, insert, select
from sqlalchemy.engine import Engine

from boardwatch.pipeline.local_twin import EVIDENCE_PREFIX, record_local_twins
from boardwatch.store.application_destinations import (
    read_application_destinations,
    record_application_destination,
)
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.tables import application_destinations, companies, jobs, postings

NOW = datetime(2026, 11, 10, 12, 0, 0)
WRAPPER_URL = "https://www.linkedin.com/jobs/view/4000000001"


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path / "data")
    ensure_schema(eng)
    return eng


def _company(
    conn: Connection, name: str, provider: str, *, slug: str | None = None, watched: bool = True
) -> int:
    return int(
        conn.execute(
            insert(companies).values(
                name=name,
                provider=provider,
                slug=slug or f"{provider}-{name.lower().replace(' ', '-')}",
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
                content_hash=f"hash-{key}",
                body_text="body",
            )
        ).inserted_primary_key[0]
    )


def _wrapper(conn: Connection, company: str = "Acme", **kwargs: object) -> int:
    lane = _company(conn, company, "linkedin", watched=False)
    return _posting(conn, lane, "w1", url=WRAPPER_URL, **kwargs)  # type: ignore[arg-type]


def _run(engine: Engine, ids: list[int], **kwargs: object) -> int:
    with engine.begin() as conn:
        return record_local_twins(conn, ids, now=NOW, **kwargs).written  # type: ignore[arg-type]


def _destination(engine: Engine, posting_id: int) -> tuple[str, str] | None:
    with engine.connect() as conn:
        found = read_application_destinations(conn, [posting_id]).get(posting_id)
    return None if found is None else (found.url, found.evidence_ref)


def test_one_open_twin_at_the_same_company_title_and_city_is_recorded(engine: Engine) -> None:
    with engine.begin() as conn:
        board = _company(conn, "Acme", "greenhouse")
        twin = _posting(conn, board, "t1", locations=["US,TX,Austin"])
        _posting(conn, board, "t2", title="Data Engineer")
        _posting(conn, board, "t3", locations=["Denver, CO"])
        wrapper = _wrapper(conn)

    assert _run(engine, [wrapper, twin]) == 1
    assert _destination(engine, wrapper) == (
        "https://boards.example.com/acme/jobs/t1", f"{EVIDENCE_PREFIX}{twin}"
    )
    # The board's own posting is not a lane copy and gets nothing.
    assert _destination(engine, twin) is None
    # Idempotent: the second pass finds nothing left to write.
    assert _run(engine, [wrapper, twin]) == 0


@pytest.mark.parametrize(
    ("wrapper_locations", "twin_locations"),
    [
        (["Salt Lake City, UT, United States"], ["San Francisco, California, United States"]),
        (["Clearwater, FL", "Phoenix, AZ"], ["Singapore"]),
        (["Columbus, OH"], ["Columbus, GA"]),
        (["Washington, DC"], ["Seattle, Washington, USA"]),
        (["United States"], ["Austin, TX"]),
        (["New York"], ["New York, NY"]),
        ([], ["Austin, TX"]),
    ],
)
def test_a_twin_in_another_city_is_not_one(
    engine: Engine, wrapper_locations: list[str], twin_locations: list[str]
) -> None:
    with engine.begin() as conn:
        board = _company(conn, "Acme", "greenhouse")
        _posting(conn, board, "t1", locations=twin_locations)
        wrapper = _wrapper(conn, locations=wrapper_locations)

    assert _run(engine, [wrapper]) == 0
    assert _destination(engine, wrapper) is None


def test_two_open_postings_with_the_title_in_the_city_decide_nothing(engine: Engine) -> None:
    """Two requisitions with one title in one city, or one requisition on two sibling sites."""
    with engine.begin() as conn:
        board = _company(conn, "Acme", "workday", slug="acme.wd1.example.com/acme/site_1")
        sibling = _company(conn, "Acme", "workday", slug="acme.wd1.example.com/acme/site_2")
        _posting(conn, board, "R100-1")
        _posting(conn, sibling, "R100-2")
        wrapper = _wrapper(conn)

    assert _run(engine, [wrapper]) == 0


def test_a_wrapper_that_already_names_another_requisition_is_left_alone(engine: Engine) -> None:
    with engine.begin() as conn:
        board = _company(conn, "Acme", "greenhouse")
        _posting(conn, board, "t1", url="https://boards.greenhouse.io/acme/jobs/7000001")
        lane = _company(conn, "Acme", "jobapps", watched=False)
        wrapper = _posting(
            conn, lane, "w1", url="https://boards.greenhouse.io/acme/jobs/7000002"
        )
        # The same holds when the twin's own URL names no readable requisition.
        other = _company(conn, "Bolt Works", "greenhouse")
        _posting(conn, other, "t9", url="https://careers.example.com/bolt/open-roles")
        lane_other = _company(conn, "Bolt Works", "jobapps", watched=False)
        second = _posting(
            conn, lane_other, "w2", url="https://boards.greenhouse.io/boltworks/jobs/7000003"
        )

    assert _run(engine, [wrapper, second]) == 0


@pytest.mark.parametrize("name", ["↳", "AB", "Other Co"])
def test_a_company_name_that_names_no_employer_never_matches(engine: Engine, name: str) -> None:
    with engine.begin() as conn:
        board = _company(conn, name if name != "Other Co" else "Acme", "greenhouse")
        _posting(conn, board, "t1")
        wrapper = _wrapper(conn, company=name)

    assert _run(engine, [wrapper]) == 0


@pytest.mark.parametrize(
    ("lane_name", "board_name", "board_slug"),
    [
        ("Acme, Inc.", "Acme", None),
        ("Acme Robotics Group", "Acme Robotics", None),
        ("Acme Robotics", "Acme Robotics Holdings", None),
        ("Acme-Robotics", "Acme Robotics Worldwide", "acmerobotics"),
    ],
)
def test_the_three_ways_a_company_name_matches(
    engine: Engine, lane_name: str, board_name: str, board_slug: str | None
) -> None:
    with engine.begin() as conn:
        board = _company(conn, board_name, "greenhouse", slug=board_slug)
        _posting(conn, board, "t1")
        wrapper = _wrapper(conn, company=lane_name)

    assert _run(engine, [wrapper]) == 1


def test_only_an_open_posting_on_a_watched_registry_board_is_a_twin(engine: Engine) -> None:
    with engine.begin() as conn:
        _posting(conn, _company(conn, "Acme", "greenhouse"), "closed", status="closed")
        _posting(conn, _company(conn, "Acme", "ashby", watched=False), "unwatched")
        _posting(conn, _company(conn, "Acme", "indeed", watched=True), "lane")
        wrapper = _wrapper(conn)

    assert _run(engine, [wrapper]) == 0


def test_a_year_in_the_title_and_a_remote_pair_still_match(engine: Engine) -> None:
    with engine.begin() as conn:
        board = _company(conn, "Acme", "greenhouse")
        twin = _posting(
            conn, board, "t1", title="software engineer new grad",
            locations=["Remote - US"], remote_policy="remote",
        )
        wrapper = _wrapper(
            conn, title="software engineer new grad 2027", locations=["United States (Remote)"]
        )

    assert _run(engine, [wrapper]) == 1
    assert _destination(engine, wrapper) == (
        "https://boards.example.com/acme/jobs/t1", f"{EVIDENCE_PREFIX}{twin}"
    )


def test_a_destination_from_another_source_is_never_replaced(engine: Engine) -> None:
    with engine.begin() as conn:
        board = _company(conn, "Acme", "greenhouse")
        _posting(conn, board, "t1")
        wrapper = _wrapper(conn)
        record_application_destination(
            conn, posting_id=wrapper, url="https://careers.example.com/acme/42",
            source_url=WRAPPER_URL, evidence_ref="browser:2026-11-09", verified_at=NOW,
        )

    assert _run(engine, [wrapper]) == 0
    assert _destination(engine, wrapper) == (
        "https://careers.example.com/acme/42", "browser:2026-11-09"
    )


def test_a_job_the_owner_applied_to_is_not_linked(engine: Engine) -> None:
    with engine.begin() as conn:
        board = _company(conn, "Acme", "greenhouse")
        _posting(conn, board, "t1")
        wrapper = _wrapper(conn)
        job_id = conn.execute(
            select(postings.c.job_id).where(postings.c.id == wrapper)
        ).scalar_one()

    assert _run(engine, [wrapper], exclude_job_ids={job_id}) == 0
    with engine.connect() as conn:
        assert conn.execute(select(application_destinations)).all() == []
