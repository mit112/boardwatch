"""A lane snapshot must not close the postings it did not mention (spec §4.2)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine, insert, select

from boardwatch.core.models import BoardSnapshot, RawPosting
from boardwatch.lanes.base import lane_snapshot
from boardwatch.scan.apply import apply_board
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import insert_run


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


def _raw(pid: str) -> RawPosting:
    return RawPosting(
        provider_posting_id=pid,
        title="Software Engineer, New Grad",
        url=f"https://boards.greenhouse.io/acme/jobs/{pid}",
        locations=["Seattle, WA"],
        body_text="we are hiring a new grad engineer",
        raw_json={},
    )


def _open_ids(engine: Engine) -> set[str]:
    with engine.connect() as conn:
        return {
            row.provider_posting_id
            for row in conn.execute(
                select(tables.postings.c.provider_posting_id, tables.postings.c.status)
            ).all()
            if row.status == "open"
        }


def test_two_consecutive_lane_scans_do_not_close_a_companys_other_postings(engine: Engine) -> None:
    """CLOSE_AFTER_MISSES is 2, so ONE scan would not have proved this."""
    company_id = _insert_company(engine)
    seeded = BoardSnapshot(
        status="complete",
        postings=[_raw("a"), _raw("b"), _raw("c")],
        url="https://boards.greenhouse.io/acme",
    )
    apply_board(engine, seeded, company_id, insert_run(engine))
    assert _open_ids(engine) == {"a", "b", "c"}

    only_one = lane_snapshot([_raw("a")], "https://example.test/search")
    apply_board(engine, only_one, company_id, insert_run(engine))
    apply_board(engine, only_one, company_id, insert_run(engine))

    assert _open_ids(engine) == {"a", "b", "c"}


def test_the_same_two_scans_marked_complete_would_have_closed_them(engine: Engine) -> None:
    """The counterexample, so the test above cannot pass for the wrong reason.

    Without it, `test_two_consecutive...` passes even if `apply_board` never closes anything
    at all — a test that cannot distinguish the fix from a no-op. Build the identical scans
    with status="complete" and assert b and c close, proving `partial` is what saved them.
    """
    company_id = _insert_company(engine)
    seeded = BoardSnapshot(
        status="complete",
        postings=[_raw("a"), _raw("b"), _raw("c")],
        url="https://boards.greenhouse.io/acme",
    )
    apply_board(engine, seeded, company_id, insert_run(engine))
    assert _open_ids(engine) == {"a", "b", "c"}

    only_one = BoardSnapshot(
        status="complete",
        postings=[_raw("a")],
        url="https://boards.greenhouse.io/acme",
    )
    apply_board(engine, only_one, company_id, insert_run(engine))
    apply_board(engine, only_one, company_id, insert_run(engine))

    assert _open_ids(engine) == {"a"}
