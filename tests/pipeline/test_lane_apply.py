"""A lane snapshot must not close the postings it did not mention (spec §4.2)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine, insert, select

from boardwatch.core.models import BoardSnapshot, RawPosting
from boardwatch.core.politeness import Fetcher
from boardwatch.core.settings import Settings
from boardwatch.lanes.base import (
    CompanyAdmission,
    Lane,
    LaneCompanySnapshot,
    LaneResult,
    lane_snapshot,
)
from boardwatch.lanes.outcomes import AcquisitionTally
from boardwatch.scan.apply import apply_board
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import get_watched_companies, insert_run


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path)
    ensure_schema(eng)
    return eng


def _insert_company(
    engine: Engine, *, provider: str = "greenhouse", slug: str = "acme", name: str = "Acme"
) -> int:
    with engine.begin() as conn:
        result = conn.execute(
            insert(tables.companies).values(
                name=name, provider=provider, slug=slug, source="user", watched=True,
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


# --------------------------------------------------------------------------------------
# The seam: what a LaneResult must carry for a runner to reach apply_board (spec §4.2)
# --------------------------------------------------------------------------------------


class _StubLane:
    """A minimal `Lane`. Collects nothing — the point is the shape it hands back."""

    name = "stub"

    def __init__(self, snapshots: tuple[LaneCompanySnapshot, ...]) -> None:
        self._snapshots = snapshots

    def collect(self, fetcher: Fetcher, admits: CompanyAdmission) -> LaneResult:
        # Asked once per company even though this stub admits unconditionally: the
        # protocol's contract is that the question is put BEFORE any body is fetched,
        # and a stub that never asks would let a runner regression through.
        kept = tuple(s for s in self._snapshots if admits(s.provider, s.slug))
        return LaneResult(snapshots=kept, tally=AcquisitionTally())


def _open_ids_by_company(engine: Engine) -> dict[int, set[str]]:
    by_company: dict[int, set[str]] = {}
    with engine.connect() as conn:
        rows = conn.execute(
            select(
                tables.postings.c.company_id,
                tables.postings.c.provider_posting_id,
                tables.postings.c.status,
            )
        ).all()
    for row in rows:
        if row.status == "open":
            by_company.setdefault(int(row.company_id), set()).add(row.provider_posting_id)
    return by_company


def test_a_lane_result_carries_the_company_identity_apply_board_needs(
    engine: Engine, tmp_path: Path
) -> None:
    """Drives the whole seam a runner must drive: collect() -> LaneResult.snapshots ->
    (provider, slug) -> company_id -> apply_board.

    Two boards SHARE the display name "Acme" and differ only by (provider, slug) — the
    identity `companies` is UNIQUE on. Resolving by name could not tell them apart, so a
    name-grouped LaneCompanySnapshot would write one board's postings under the other's
    company_id, where they can never converge and close after two misses. This fails if
    LaneCompanySnapshot stops carrying (provider, slug), or if LaneResult stops carrying
    its snapshots.
    """
    greenhouse_id = _insert_company(engine, provider="greenhouse", slug="acme", name="Acme")
    lever_id = _insert_company(engine, provider="lever", slug="acme", name="Acme")

    lane: Lane = _StubLane(
        (
            LaneCompanySnapshot(
                provider="greenhouse",
                slug="acme",
                name="Acme",
                snapshot=lane_snapshot([_raw("gh-1")], "https://example.test/search"),
            ),
            LaneCompanySnapshot(
                provider="lever",
                slug="acme",
                name="Acme",
                snapshot=lane_snapshot([_raw("lv-1")], "https://example.test/search"),
            ),
        )
    )
    result = lane.collect(
        Fetcher(Settings(data_dir=tmp_path, config_dir=tmp_path)), lambda _p, _s: True
    )

    run_id = insert_run(engine)
    for company in result.snapshots:
        with engine.connect() as conn:
            rows = get_watched_companies(conn, provider=company.provider, slug=company.slug)
        assert len(rows) == 1, f"{company.provider}:{company.slug} did not resolve to one row"
        apply_board(engine, company.snapshot, int(rows[0].id), run_id)

    assert _open_ids_by_company(engine) == {greenhouse_id: {"gh-1"}, lever_id: {"lv-1"}}
