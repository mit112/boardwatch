"""A resolved jobright record through the real fetch-then-apply seam (`runner._collect_lane`).

One posting per job, whichever way the store first met it: a record first seen resolved lands on
the employer's posting and watches its board; a record first seen unresolved keeps job-apps' key
after the resolver rewrites its folder, and no second posting appears.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from pathlib import Path

import pytest
from sqlalchemy import Engine, func, select

from boardwatch.core.models import RawPosting
from boardwatch.core.politeness import Fetcher
from boardwatch.core.settings import Settings
from boardwatch.lanes.base import CompanyAdmission, LaneCompanySnapshot, LaneResult, lane_snapshot
from boardwatch.lanes.jobapps import JobAppsLane
from boardwatch.lanes.outcomes import AcquisitionTally
from boardwatch.pipeline.runner import _collect_lane
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import insert_run, posting_slugs
from tests.unit.test_jobapps_jobright_resolution import (
    _WEBLOC,
    JOBRIGHT_URL,
    WORKDAY,
    WORKDAY_URL,
    _record,
)

EMPLOYER_JD = "Cboe's own posting: build low-latency trading systems. 0-2 years of experience."


class _BoardScan:
    """The workday board's own listing of the job, standing in for the scan the watch turns on:
    a live listing, so it declares nothing secondhand and writes the employer's JD."""

    name = "boardscan"

    def collect(self, fetcher: Fetcher, admits: CompanyAdmission) -> LaneResult:
        admits(WORKDAY[0], WORKDAY[1])
        raw = RawPosting(
            provider_posting_id=WORKDAY[2],
            title="Software Engineer",
            url=WORKDAY_URL,
            locations=["Chicago, IL"],
            body_text=EMPLOYER_JD,
            raw_json={},
        )
        company = LaneCompanySnapshot(
            provider=WORKDAY[0],
            slug=WORKDAY[1],
            name="Cboe",
            snapshot=lane_snapshot([raw], "https://cboe.wd1.myworkdayjobs.com"),
        )
        return LaneResult(snapshots=(company,), tally=AcquisitionTally())


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path / "store")
    ensure_schema(eng)
    return eng


def _run(engine: Engine, tmp_path: Path, root: Path | _BoardScan) -> None:
    def reader(provider: str, posting_ids: Collection[str]) -> Mapping[str, str]:
        with engine.connect() as conn:
            return posting_slugs(conn, provider=provider, posting_ids=posting_ids)

    settings = Settings(data_dir=tmp_path / "store", config_dir=tmp_path / "cfg")
    lane = root if isinstance(root, _BoardScan) else JobAppsLane(root, stored_posting_slugs=reader)
    _collect_lane(engine, settings, lane, Fetcher(settings), insert_run(engine))  # type: ignore[arg-type]


def _postings(engine: Engine) -> list[tuple[str, str, str, bool, str]]:
    """`(provider, slug, posting ref, company watched, url)` of every stored posting."""
    with engine.connect() as conn:
        return [
            (row.provider, row.slug, row.provider_posting_id, bool(row.watched), row.url)
            for row in conn.execute(
                select(
                    tables.companies.c.provider,
                    tables.companies.c.slug,
                    tables.companies.c.watched,
                    tables.postings.c.provider_posting_id,
                    tables.postings.c.url,
                )
                .join(tables.companies, tables.companies.c.id == tables.postings.c.company_id)
                .order_by(tables.postings.c.id)
            ).all()
        ]


def _bodies(engine: Engine) -> list[str]:
    with engine.connect() as conn:
        return [row.body_text for row in conn.execute(select(tables.postings.c.body_text)).all()]


def _versions(engine: Engine) -> int:
    with engine.connect() as conn:
        return int(conn.execute(select(func.count()).select_from(tables.posting_versions)).scalar_one())


def test_a_first_sighting_resolved_lands_on_the_employers_posting_and_watches_it(
    engine: Engine, tmp_path: Path
) -> None:
    """The store gets the employer's posting on the board's own key, on a WATCHED company so the
    scan fetches the employer's JD; the scan's JD is a newer version (the quarantine's drain), and
    a later job-apps read writes nothing over it. Catches the watch not reaching the store, and
    the columns not declared secondhand (the re-read reverts the employer's JD to jobright's)."""
    root = tmp_path / "queue"
    _record(root)
    _run(engine, tmp_path, root)
    assert _postings(engine) == [(*WORKDAY, True, WORKDAY_URL)]

    _run(engine, tmp_path, _BoardScan())
    assert _bodies(engine) == [EMPLOYER_JD]
    assert _versions(engine) == 2

    _run(engine, tmp_path, root)
    assert _postings(engine) == [(*WORKDAY, True, WORKDAY_URL)]
    assert _bodies(engine) == [EMPLOYER_JD]
    assert _versions(engine) == 2


def test_a_record_stored_before_it_was_resolved_is_never_filed_twice(
    engine: Engine, tmp_path: Path
) -> None:
    """Stored under job-apps' key, then resolved in job-apps' tree: the next read keeps that key,
    so the store still holds ONE posting for the job and no board was watched on its account.
    Catches the lane's store read for job-apps' own key not reaching the real store."""
    root = tmp_path / "queue"
    _record(root, webloc=JOBRIGHT_URL, source=None)
    _run(engine, tmp_path, root)
    assert _postings(engine) == [("jobapps", "cbre", "pst_cboe", False, JOBRIGHT_URL)]

    folder = root / "Jobright" / "Cboe_Software_Engineer"
    (folder / "1_apply.webloc").write_text(_WEBLOC.format(url=WORKDAY_URL), encoding="utf-8")
    (folder / "jobright_source.url").write_text(JOBRIGHT_URL + "\n", encoding="utf-8")
    _run(engine, tmp_path, root)
    assert _postings(engine) == [("jobapps", "cbre", "pst_cboe", False, JOBRIGHT_URL)]
