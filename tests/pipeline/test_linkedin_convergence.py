"""One LinkedIn job is ONE posting, whether job-apps or boardwatch's LinkedIn lane saw it first.

The LinkedIn lane keys a card `(linkedin, <true company slug>, <job id>)`. The job-apps lane holds
the job id and never a LinkedIn company slug, so a job the store has not seen files under a
namespaced guess (`jobapps.linkedin_identity`). What makes the two converge is the runner filing a
LinkedIn posting by its JOB ID at apply (`runner._route_by_stored_posting`), and what keeps the
converged row honest is that a directory read landing on a stored job writes nothing over it.

Driven through `_collect_lane`, the real fetch-then-apply seam, with the REAL `JobAppsLane` and a
stub standing in for the LinkedIn lane's network half. Every assertion reads the store back.
"""

from __future__ import annotations

import json
from collections.abc import Collection, Mapping
from pathlib import Path

import pytest
from sqlalchemy import Engine, func, select

from boardwatch.core.models import RawPosting
from boardwatch.core.politeness import Fetcher
from boardwatch.core.settings import Settings
from boardwatch.lanes.base import (
    CompanyAdmission,
    LaneCompanySnapshot,
    LaneResult,
    lane_snapshot,
    no_stored_postings,
)
from boardwatch.lanes.jobapps import JobAppsLane
from boardwatch.lanes.outcomes import AcquisitionTally
from boardwatch.pipeline.runner import _collect_lane
from boardwatch.reports.run_funnel import _lane_cross_checks
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import insert_run, posting_slugs
from boardwatch.store.run_funnel_queries import count_lane_captures

JOB_ID = "4458214586"
LANE_BODY = "LinkedIn lane body: we are hiring a new grad software engineer to build services."
JOBAPPS_BODY = "job-apps body: Associate Software Engineer, 0-2 years of Python, Austin TX.\n"


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path / "store")
    ensure_schema(eng)
    return eng


def _settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path / "store", config_dir=tmp_path / "cfg")


class _LinkedInStub:
    """The LinkedIn lane's output for one card, without the network: a live listing, so it
    declares nothing secondhand -- exactly what `linkedin._raw_posting` builds."""

    name = "linkedin"

    def __init__(
        self, slug: str, job_id: str = JOB_ID, body: str = LANE_BODY, *more_ids: str
    ) -> None:
        self._slug, self._job_ids, self._body = slug, (job_id, *more_ids), body

    def collect(self, fetcher: Fetcher, admits: CompanyAdmission) -> LaneResult:
        raws = [
            RawPosting(
                provider_posting_id=job_id,
                title="Associate Software Engineer",
                url=f"https://www.linkedin.com/jobs/view/associate-at-acme-{job_id}?refId=x",
                locations=["Austin, TX"],
                body_text=self._body,
                raw_json={"card": {}},
            )
            for job_id in self._job_ids
        ]
        snapshots = ()
        if admits("linkedin", self._slug):
            snapshots = (
                LaneCompanySnapshot(
                    provider="linkedin",
                    slug=self._slug,
                    name="Acme",
                    snapshot=lane_snapshot(raws, "https://www.linkedin.com/search"),
                ),
            )
        tally = AcquisitionTally()
        tally.record("body_fetched")
        return LaneResult(snapshots=snapshots, tally=tally)


def _tree(root: Path, job_id: str = JOB_ID, company: str = "Acme") -> Path:
    """One job-apps LinkedIn record, shaped as the live tree shapes it."""
    folder = root / "LinkedIn" / f"rec-{job_id}"
    folder.mkdir(parents=True)
    (folder / "discovery_record.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "posting_id": f"pst_{job_id}",
                "primary_acquisition": "linkedin",
                "cohort_date": "2026-09-26",
                "canonical": {
                    "company": company,
                    "title": "Associate Software Engineer",
                    "direct_url": f"https://www.linkedin.com/jobs/view/{job_id}",
                    "location": "Austin, TX",
                },
            }
        ),
        encoding="utf-8",
    )
    rule = "=" * 80
    (folder / "job_description.txt").write_text(
        f"Company: {company}\nFit: 60/100\n\n{rule}\nJOB DESCRIPTION\n{rule}\n\n{JOBAPPS_BODY}",
        encoding="utf-8",
    )
    return root


def _jobapps(engine: Engine, root: Path, *, blind: bool = False) -> JobAppsLane:
    """The real lane, reading the store the way the runner's factory wires it. `blind` is a
    lane whose fetch half ran BEFORE another lane stored the job this run -- its view of the
    store is empty, which is what a same-run race looks like from inside the lane."""

    def reader(provider: str, posting_ids: Collection[str]) -> Mapping[str, str]:
        with engine.connect() as conn:
            return posting_slugs(conn, provider=provider, posting_ids=posting_ids)

    return JobAppsLane(source_dir=root, stored_posting_slugs=no_stored_postings if blind else reader)


def _run(engine: Engine, tmp_path: Path, lane: object):
    settings = _settings(tmp_path)
    return _collect_lane(engine, settings, lane, Fetcher(settings), insert_run(engine))  # type: ignore[arg-type]


def _run_checked(engine: Engine, tmp_path: Path, lane: object):
    """`_run`, returning the report AND the funnel's T191 lane cross-checks for that run -- the
    lane's self-report against the store's own recount, through `count_lane_captures`."""
    settings = _settings(tmp_path)
    run_id = insert_run(engine)
    report = _collect_lane(engine, settings, lane, Fetcher(settings), run_id)  # type: ignore[arg-type]
    with engine.connect() as conn:
        captures = count_lane_captures(conn, run_id, {report.name: report.admitted})
    return report, _lane_cross_checks([report], captures)


def _rows(engine: Engine) -> list[tuple[str, str, str, str]]:
    """(company slug, provider_posting_id, body, locations) of every stored posting."""
    with engine.connect() as conn:
        return [
            (row.slug, row.provider_posting_id, row.body_text, json.dumps(row.locations_json))
            for row in conn.execute(
                select(
                    tables.companies.c.slug,
                    tables.postings.c.provider_posting_id,
                    tables.postings.c.body_text,
                    tables.postings.c.locations_json,
                )
                .join(tables.companies, tables.companies.c.id == tables.postings.c.company_id)
                .order_by(tables.postings.c.id)
            ).all()
        ]


def _versions(engine: Engine) -> int:
    with engine.connect() as conn:
        return int(conn.execute(select(func.count()).select_from(tables.posting_versions)).scalar_one())


def _company_slugs(engine: Engine) -> set[str]:
    with engine.connect() as conn:
        return {row.slug for row in conn.execute(select(tables.companies.c.slug)).all()}


def test_a_job_the_linkedin_lane_stored_is_not_stored_again_by_job_apps(
    engine: Engine, tmp_path: Path
) -> None:
    """LinkedIn lane first, job-apps on a later run: ONE posting, the lane's body untouched, no
    second version, and no namespaced company row minted for a job the store already holds."""
    _run(engine, tmp_path, _LinkedInStub("acme-corp"))
    report = _run(engine, tmp_path, _jobapps(engine, _tree(tmp_path / "ja")))

    assert _rows(engine) == [("acme-corp", JOB_ID, LANE_BODY, '["Austin, TX"]')]
    assert _versions(engine) == 1
    assert _company_slugs(engine) == {"acme-corp"}
    assert report.admitted == () and report.persisted_new == ()


def test_a_job_job_apps_stored_first_is_updated_in_place_by_the_linkedin_lane(
    engine: Engine, tmp_path: Path
) -> None:
    """job-apps first, under the namespaced guess; then the LinkedIn lane lists the same job
    under its TRUE slug. Keyed by company that is a second posting. Filed by job id it is the
    same row, and the live listing -- the record of truth -- replaces job-apps' body. The true
    slug gets no company row: nothing landed on it, so it is not reach (`persisted_new`)."""
    _run(engine, tmp_path, _jobapps(engine, _tree(tmp_path / "ja")))
    assert _rows(engine) == [("jobapps:acme", JOB_ID, JOBAPPS_BODY, '["Austin, TX"]')]

    report = _run(engine, tmp_path, _LinkedInStub("acme-corp"))

    assert _rows(engine) == [("jobapps:acme", JOB_ID, LANE_BODY, '["Austin, TX"]')]
    assert _company_slugs(engine) == {"jobapps:acme"}
    assert report.admitted == (("linkedin", "acme-corp"),)
    assert report.persisted_new == ()


def test_job_apps_re_listing_a_row_the_linkedin_lane_refreshed_does_not_revert_it(
    engine: Engine, tmp_path: Path
) -> None:
    """The ping-pong this must not have: job-apps, then the LinkedIn lane, then job-apps again.
    The third listing is a directory read of a stored job, so it writes nothing -- the row keeps
    the lane's body and gains no third version."""
    root = _tree(tmp_path / "ja")
    _run(engine, tmp_path, _jobapps(engine, root))
    _run(engine, tmp_path, _LinkedInStub("acme-corp"))
    versions = _versions(engine)

    _run(engine, tmp_path, _jobapps(engine, root))

    assert _rows(engine) == [("jobapps:acme", JOB_ID, LANE_BODY, '["Austin, TX"]')]
    assert _versions(engine) == versions


def test_a_same_run_race_still_writes_nothing_over_the_linkedin_lanes_row(
    engine: Engine, tmp_path: Path
) -> None:
    """Both lanes fetch before either applies, so job-apps' lane saw an EMPTY store and filed the
    job as a first sighting. The LinkedIn lane applies first and stores it; job-apps' apply then
    finds it by id and must not overwrite it -- the decision can only be right at apply time."""
    _run(engine, tmp_path, _LinkedInStub("acme-corp"))
    _run(engine, tmp_path, _jobapps(engine, _tree(tmp_path / "ja"), blind=True))

    assert _rows(engine) == [("acme-corp", JOB_ID, LANE_BODY, '["Austin, TX"]')]
    assert _versions(engine) == 1
    assert _company_slugs(engine) == {"acme-corp"}


def test_a_job_apps_listing_of_a_stored_job_leaves_its_death_strikes_alone(
    engine: Engine, tmp_path: Path
) -> None:
    """Liveness: a directory read is not a sighting, so it cannot clear a strike the death probe
    earned on the LinkedIn lane's row -- the same rule every job-apps row already has."""
    _run(engine, tmp_path, _LinkedInStub("acme-corp"))
    with engine.begin() as conn:
        conn.execute(tables.postings.update().values(death_strikes=1))

    _run(engine, tmp_path, _jobapps(engine, _tree(tmp_path / "ja")))

    with engine.connect() as conn:
        assert conn.execute(select(tables.postings.c.death_strikes)).scalar_one() == 1


def test_a_first_sighting_keeps_its_location_on_insert(engine: Engine, tmp_path: Path) -> None:
    """A job nobody stored yet is written with job-apps' location. Declaring every column on a
    first sighting would blank it (`_inserted_fields`), and the location gate and every
    location-bearing identity would then have nothing to read."""
    _run(engine, tmp_path, _jobapps(engine, _tree(tmp_path / "ja")))
    assert _rows(engine) == [("jobapps:acme", JOB_ID, JOBAPPS_BODY, '["Austin, TX"]')]


def test_an_ats_posting_id_shared_across_two_boards_is_two_postings(
    engine: Engine, tmp_path: Path
) -> None:
    """The control: routing by id is for a provider whose id is provider-wide. An ATS id is
    unique within ONE board, so the same number on two greenhouse boards is two jobs."""

    class _Board(_LinkedInStub):
        def collect(self, fetcher: Fetcher, admits: CompanyAdmission) -> LaneResult:
            result = super().collect(fetcher, admits)
            return LaneResult(
                snapshots=tuple(
                    LaneCompanySnapshot(
                        provider="greenhouse", slug=s.slug, name=s.name, snapshot=s.snapshot
                    )
                    for s in result.snapshots
                ),
                tally=result.tally,
            )

    _run(engine, tmp_path, _Board("alpha"))
    _run(engine, tmp_path, _Board("beta"))

    assert [(slug, ref) for slug, ref, _, _ in _rows(engine)] == [
        ("alpha", JOB_ID), ("beta", JOB_ID),
    ]


def test_a_split_snapshot_is_counted_as_the_board_scans_rows_it_writes(
    engine: Engine, tmp_path: Path
) -> None:
    """ONE collected LinkedIn snapshot, two cards: one job job-apps stored first under its
    placeholder, one new. Routing lands it as TWO applies -- two `scan_kind='lane'` rows -- so the
    lane must report two snapshots, or the funnel's `lanes:board_scans` check disagrees and the
    run records an error on every run the LinkedIn lane lists such an employer."""
    _run(engine, tmp_path, _jobapps(engine, _tree(tmp_path / "ja")))

    report, checks = _run_checked(
        engine, tmp_path, _LinkedInStub("acme-corp", JOB_ID, LANE_BODY, "5550001")
    )

    assert sorted((slug, ref) for slug, ref, _, _ in _rows(engine)) == [
        ("acme-corp", "5550001"), ("jobapps:acme", JOB_ID),
    ]
    assert report.snapshots == 2
    by_name = {check.name: check for check in checks}
    assert (by_name["lanes:board_scans"].in_memory, by_name["lanes:board_scans"].from_store) == (2, 2)
    assert all(check.agrees for check in checks), checks
