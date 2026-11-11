"""The links already on disk: ledger entries and `grnh.se` short links (D-690).

Every fixture name and URL is made up. The catalog cases in `test_the_posting_link_test` are the
shapes the review measured on the live ledgers — a posting page versus a portal root, a shortener
token and an aggregator listing — so a regression in the ported rule fails here first.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
import yaml
from sqlalchemy import Connection, Engine, insert, select

from boardwatch.core.liveness import Liveness
from boardwatch.core.politeness import FetchFailure, FetchResult
from boardwatch.delivery.apply_routes import ApplyRoutes, load_apply_routes
from boardwatch.pipeline.on_disk_links import (
    EVIDENCE_GRNH_PREFIX,
    GRNH_CANDIDATE_FILENAME,
    drain_grnh_seeds,
    posting_link,
    record_on_disk_links,
)
from boardwatch.store.application_destinations import read_application_destinations
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import insert_run
from boardwatch.store.seed_queries import record_seeds, unresolved_seed_count
from boardwatch.store.tables import companies, jobs, lane_seeds, postings

NOW = datetime(2026, 11, 10, 12, 0, 0)
LATER = datetime(2026, 11, 11, 12, 0, 0)
POSTING_URL = "https://careers.example.com/jobs/12345/software-engineer"


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path / "data")
    ensure_schema(eng)
    return eng


def _company(conn: Connection, name: str = "Acme", provider: str = "greenhouse") -> int:
    return int(
        conn.execute(
            insert(companies).values(
                name=name,
                provider=provider,
                slug=name.lower().replace(" ", "-"),
                source="user",
                watched=True,
            )
        ).inserted_primary_key[0]
    )


def _posting(
    conn: Connection,
    company_id: int,
    url: str,
    *,
    key: str = "p1",
    title: str = "Software Engineer",
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
                url=url,
                locations_json=["Austin, TX"],
                remote_policy="unknown",
                first_seen_at=NOW,
                last_seen_at=NOW,
                status="open",
                consecutive_missing=0,
                content_hash=f"hash-{key}",
                body_text="body",
            )
        ).inserted_primary_key[0]
    )


def _routes(config_dir: Path, links: dict[str, dict[str, object]]) -> ApplyRoutes:
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "links.json").write_text(json.dumps(links), encoding="utf-8")
    (config_dir / "apply-routes.toml").write_text(
        f"""
auto_hosts = ["ashbyhq.com"]
link_ledgers = ['{config_dir / "links.json"}']
no_employer_statuses = ["none", "aggregator", "linkedin_is_channel"]
""",
        encoding="utf-8",
    )
    return load_apply_routes(config_dir)


class _StubFetcher:
    """A Fetcher-shaped client: one final URL per requested URL, or a typed failure."""

    def __init__(
        self, *, landing: dict[str, str] | None = None, failures: dict[str, FetchFailure] | None = None
    ) -> None:
        self._landing = landing or {}
        self._failures = failures or {}
        self.calls: list[str] = []

    def get(
        self,
        url: str,
        validators: object | None = None,
        *,
        headers: object | None = None,
        min_host_delay: float | None = None,
    ) -> FetchResult:
        self.calls.append(url)
        failure = self._failures.get(url)
        if failure is not None:
            raise failure
        return FetchResult(
            status_code=200,
            content=b"",
            not_modified=False,
            observed_validators=None,
            final_url=self._landing.get(url, url),
        )


def _alive(posting_id: int, url: str) -> Liveness:
    return Liveness(posting_id=posting_id, verdict="alive", signal="refetch_ok")


def _dead_verdict(posting_id: int, url: str) -> Liveness:
    return Liveness(posting_id=posting_id, verdict="dead", signal="refetch_gone")


def _unknown(posting_id: int, url: str) -> Liveness:
    return Liveness(posting_id=posting_id, verdict="unknown", signal="refetch_error")


def _destination(engine: Engine, posting_id: int) -> tuple[str, str] | None:
    with engine.connect() as conn:
        found = read_application_destinations(conn, [posting_id]).get(posting_id)
    return None if found is None else (found.url, found.evidence_ref)


def _record(
    engine: Engine,
    posting_ids: list[int],
    routes: ApplyRoutes,
    *,
    prober: object = _alive,
    fetcher: object = None,
) -> object:
    return record_on_disk_links(
        engine,
        posting_ids,
        routes=routes,
        prober=prober,  # type: ignore[arg-type]
        fetcher=fetcher,  # type: ignore[arg-type]
        now=NOW,
    )


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        # The shapes the review measured as one employer posting.
        (POSTING_URL, POSTING_URL),
        (
            "https://joinbytedance.com/search/7668484998475663621",
            "https://joinbytedance.com/search/7668484998475663621",
        ),
        (
            "https://lifeattiktok.com/search/7665989305914984709",
            "https://lifeattiktok.com/search/7665989305914984709",
        ),
        (
            "https://jobs.apple.com/en-us/details/200682058-0836/system-software-developer",
            "https://jobs.apple.com/en-us/details/200682058-0836/system-software-developer",
        ),
        ("https://careers-daddario.icims.com/jobs/2680/job", "https://careers-daddario.icims.com/jobs/2680/job"),
        (
            "https://careers.hpe.com/us/en/job/HPE1US1213648EXTERNALENUS/Systems-Software-Engineer-I-Graduate",
            "https://careers.hpe.com/us/en/job/HPE1US1213648EXTERNALENUS/Systems-Software-Engineer-I-Graduate",
        ),
        ("https://lsijax.hua.hrsmart.com/hr/ats/Posting/view/536", "https://lsijax.hua.hrsmart.com/hr/ats/Posting/view/536"),
        # `src` is not in the ported tracking catalog (job-apps does not strip it either).
        (
            "https://www.theladders.com/linkedin/89393523?src=LinkedIn",
            "https://www.theladders.com/linkedin/89393523?src=LinkedIn",
        ),
        # The shapes it must refuse: a portal root, a shortener token, a careers search page.
        ("https://ars2.equest.com/", None),
        ("https://dsp.prng.co/jkRaQwb", None),
        ("https://usource.ripplehire.com/candidate/", None),
        ("https://acme.com/careers", None),
        ("https://www.linkedin.com/jobs/view/4468637940", None),
        ("https://grnh.se/ohlkpc0d1us", None),
        ("not a url", None),
        ("", None),
    ],
)
def test_the_posting_link_test(url: str, expected: str | None) -> None:
    assert posting_link(url) == expected


def test_a_live_ledger_link_is_recorded_as_the_destination(
    engine: Engine, tmp_path: Path
) -> None:
    with engine.begin() as conn:
        company = _company(conn)
        posting = _posting(conn, company, "https://www.linkedin.com/jobs/view/1")
    routes = _routes(
        tmp_path / "config",
        {str(posting): {"company": POSTING_URL, "company_status": "live"}},
    )

    report = _record(engine, [posting], routes)
    assert (report.ledger_considered, report.ledger_dead) == (1, 0)  # type: ignore[attr-defined]
    assert _destination(engine, posting) == (
        POSTING_URL,
        f"ledger:links.json:{posting}",
    )


def test_a_dead_ledger_link_is_reported_and_not_written(
    engine: Engine, tmp_path: Path
) -> None:
    with engine.begin() as conn:
        company = _company(conn)
        posting = _posting(conn, company, "https://www.linkedin.com/jobs/view/2")
    routes = _routes(
        tmp_path / "config",
        {str(posting): {"company": POSTING_URL, "company_status": "unverified"}},
    )

    report = _record(engine, [posting], routes, prober=_dead_verdict)
    assert (report.ledger_dead, report.ledger_written) == (1, 0)  # type: ignore[attr-defined]
    assert _destination(engine, posting) is None


def test_an_unreachable_ledger_link_is_unknown_never_dead(
    engine: Engine, tmp_path: Path
) -> None:
    """A failed check is not a negative result: it writes nothing and is not counted dead."""
    with engine.begin() as conn:
        company = _company(conn)
        posting = _posting(conn, company, "https://www.linkedin.com/jobs/view/3")
    routes = _routes(
        tmp_path / "config",
        {str(posting): {"company": POSTING_URL, "company_status": "unknown"}},
    )

    report = _record(engine, [posting], routes, prober=_unknown)
    assert (report.ledger_dead, report.ledger_unknown) == (0, 1)  # type: ignore[attr-defined]
    assert _destination(engine, posting) is None


def test_a_portal_root_in_the_ledger_is_not_even_probed(
    engine: Engine, tmp_path: Path
) -> None:
    def boom(posting_id: int, url: str) -> Liveness:
        raise AssertionError("a portal root must not be probed as a posting")

    with engine.begin() as conn:
        company = _company(conn)
        posting = _posting(conn, company, "https://www.linkedin.com/jobs/view/4")
    routes = _routes(
        tmp_path / "config",
        {str(posting): {"company": "https://ars2.equest.com/", "company_status": "live"}},
    )

    report = _record(engine, [posting], routes, prober=boom)
    assert (report.ledger_not_a_posting, report.ledger_written) == (1, 0)  # type: ignore[attr-defined]
    assert _destination(engine, posting) is None


@pytest.mark.parametrize("status", ["none", "aggregator", "linkedin_is_channel"])
def test_a_status_that_means_no_employer_link_is_not_a_candidate(
    engine: Engine, tmp_path: Path, status: str
) -> None:
    with engine.begin() as conn:
        company = _company(conn)
        posting = _posting(conn, company, "https://www.linkedin.com/jobs/view/5")
    routes = _routes(
        tmp_path / "config",
        {str(posting): {"company": POSTING_URL, "company_status": status}},
    )

    report = _record(engine, [posting], routes)
    assert report.ledger_considered == 0  # type: ignore[attr-defined]
    assert _destination(engine, posting) is None


def test_a_browser_verified_destination_is_never_overwritten(
    engine: Engine, tmp_path: Path
) -> None:
    """The ledger entry is older evidence than a destination the browser already verified."""
    from boardwatch.store.application_destinations import record_application_destination

    with engine.begin() as conn:
        company = _company(conn)
        posting = _posting(conn, company, "https://www.linkedin.com/jobs/view/6")
        record_application_destination(
            conn,
            posting_id=posting,
            url="https://employer.example.com/job/999",
            source_url="https://www.linkedin.com/jobs/view/6",
            evidence_ref="browser:verified",
            verified_at=NOW,
        )
    routes = _routes(
        tmp_path / "config",
        {str(posting): {"company": POSTING_URL, "company_status": "live"}},
    )

    def boom(posting_id: int, url: str) -> Liveness:
        raise AssertionError("a posting with a destination must not be probed again")

    report = _record(engine, [posting], routes, prober=boom)
    assert report.ledger_considered == 0  # type: ignore[attr-defined]
    assert _destination(engine, posting) == ("https://employer.example.com/job/999", "browser:verified")


def test_a_second_run_writes_nothing(engine: Engine, tmp_path: Path) -> None:
    with engine.begin() as conn:
        company = _company(conn)
        posting = _posting(conn, company, "https://www.linkedin.com/jobs/view/7")
    routes = _routes(
        tmp_path / "config",
        {str(posting): {"company": POSTING_URL, "company_status": "live"}},
    )

    first = _record(engine, [posting], routes)
    second = _record(engine, [posting], routes)
    assert (first.ledger_written, second.ledger_written) == (1, 0)  # type: ignore[attr-defined]


def test_a_grnh_short_link_resolves_to_the_employer_posting(
    engine: Engine, tmp_path: Path
) -> None:
    seed_url = "https://grnh.se/ohlkpc0d1us"
    landing = "https://job-boards.greenhouse.io/acme/jobs/42"
    routes = _routes(tmp_path / "config", {})
    with engine.begin() as conn:
        company = _company(conn)
        posting = _posting(conn, company, seed_url)

    report = _record(engine, [posting], routes, prober=None, fetcher=_StubFetcher(landing={seed_url: landing}))
    assert report.grnh_written == 1  # type: ignore[attr-defined]
    assert _destination(engine, posting) == (landing, f"{EVIDENCE_GRNH_PREFIX}{posting}")


def test_a_grnh_short_link_whose_posting_has_expired_is_dead(
    engine: Engine, tmp_path: Path
) -> None:
    seed_url = "https://grnh.se/expired1"
    landing = "https://job-boards.greenhouse.io/acme/jobs/7"
    routes = _routes(tmp_path / "config", {})
    with engine.begin() as conn:
        company = _company(conn)
        posting = _posting(conn, company, seed_url)

    fetcher = _StubFetcher(
        failures={seed_url: FetchFailure("HTTP 404", 404, final_url=landing)}
    )
    report = _record(engine, [posting], routes, prober=None, fetcher=fetcher)
    assert (report.grnh_dead, report.grnh_written) == (1, 0)  # type: ignore[attr-defined]
    assert _destination(engine, posting) is None


def _seed(engine: Engine, url: str, *, discovered_by: str = "indeed") -> int:
    run = insert_run(engine)
    with engine.begin() as conn:
        record_seeds(conn, (url,), discovered_by=discovered_by, run_id=run, now=NOW)
    with engine.connect() as conn:
        return int(conn.execute(select(lane_seeds.c.id).where(lane_seeds.c.url == url)).scalar_one())


def _seed_count(engine: Engine) -> int:
    with engine.connect() as conn:
        return unresolved_seed_count(
            conn, hosts=frozenset({"grnh.se"}), max_attempts=3
        )


def test_the_drain_resolves_a_seed_and_proposes_its_board(engine: Engine, tmp_path: Path) -> None:
    seed = _seed(engine, "https://grnh.se/abc")
    landing = "https://job-boards.greenhouse.io/acme/jobs/42"
    run = insert_run(engine)
    report = drain_grnh_seeds(
        engine,
        fetcher=_StubFetcher(landing={"https://grnh.se/abc": landing}),  # type: ignore[arg-type]
        run_id=run,
        now=NOW,
        data_dir=tmp_path,
    )
    assert (report.followed, report.resolved, report.proposed) == (1, 1, 1)
    assert report.candidates_path == tmp_path / GRNH_CANDIDATE_FILENAME
    payload = yaml.safe_load(report.candidates_path.read_text(encoding="utf-8"))
    assert payload["companies"] == [
        {"name": "acme", "provider": "greenhouse", "slug": "acme", "tags": []}
    ]
    with engine.connect() as conn:
        row = conn.execute(select(lane_seeds).where(lane_seeds.c.id == seed)).one()
    assert row.resolved_at is not None
    assert _seed_count(engine) == 0


def test_the_drain_does_not_propose_a_board_already_watched(engine: Engine, tmp_path: Path) -> None:
    with engine.begin() as conn:
        _company(conn, "Acme", "greenhouse")
    _seed(engine, "https://grnh.se/abc")
    run = insert_run(engine)
    report = drain_grnh_seeds(
        engine,
        fetcher=_StubFetcher(landing={"https://grnh.se/abc": "https://job-boards.greenhouse.io/acme/jobs/42"}),  # type: ignore[arg-type]
        run_id=run,
        now=NOW,
        data_dir=tmp_path,
    )
    assert (report.resolved, report.already_known, report.proposed) == (1, 1, 0)
    assert not (tmp_path / GRNH_CANDIDATE_FILENAME).exists()


def test_the_drain_charges_a_failed_seed_and_retires_it_over_runs(
    engine: Engine, tmp_path: Path
) -> None:
    """A dead link costs one attempt and retires through the existing ceiling, not on the spot."""
    seed = _seed(engine, "https://grnh.se/dead")
    fetcher = _StubFetcher(failures={"https://grnh.se/dead": FetchFailure("boom")})
    for _ in range(3):
        run = insert_run(engine)
        report = drain_grnh_seeds(
            engine, fetcher=fetcher, run_id=run, now=NOW, data_dir=tmp_path  # type: ignore[arg-type]
        )
    with engine.connect() as conn:
        row = conn.execute(select(lane_seeds).where(lane_seeds.c.id == seed)).one()
    assert row.resolved_at is None
    assert row.attempts == 3
    assert (report.failed, report.proposed) == (1, 0)
    assert _seed_count(engine) == 0


def test_the_drain_merges_into_an_existing_candidate_file(engine: Engine, tmp_path: Path) -> None:
    path = tmp_path / GRNH_CANDIDATE_FILENAME
    path.write_text(
        yaml.safe_dump(
            {"companies": [{"name": "Old Co", "provider": "greenhouse", "slug": "oldco", "tags": []}]}
        ),
        encoding="utf-8",
    )
    _seed(engine, "https://grnh.se/new")
    run = insert_run(engine)
    report = drain_grnh_seeds(
        engine,
        fetcher=_StubFetcher(landing={"https://grnh.se/new": "https://job-boards.greenhouse.io/acme/jobs/1"}),  # type: ignore[arg-type]
        run_id=run,
        now=NOW,
        data_dir=tmp_path,
    )
    assert report.proposed == 1
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert [row["slug"] for row in payload["companies"]] == ["oldco", "acme"]


def test_the_drain_never_rewrites_an_unreadable_candidate_file(engine: Engine, tmp_path: Path) -> None:
    """Rewriting a file this step could not parse would discard the owner's edits."""
    path = tmp_path / GRNH_CANDIDATE_FILENAME
    path.write_text("companies: [not: [closed", encoding="utf-8")
    before = path.read_text(encoding="utf-8")
    seed = _seed(engine, "https://grnh.se/abc")
    run = insert_run(engine)
    report = drain_grnh_seeds(
        engine,
        fetcher=_StubFetcher(landing={"https://grnh.se/abc": "https://job-boards.greenhouse.io/acme/jobs/1"}),  # type: ignore[arg-type]
        run_id=run,
        now=NOW,
        data_dir=tmp_path,
    )
    assert report.problem is not None
    assert path.read_text(encoding="utf-8") == before
    with engine.connect() as conn:
        row = conn.execute(select(lane_seeds).where(lane_seeds.c.id == seed)).one()
    assert row.resolved_at is None  # no retirement without the board on disk
    assert row.attempts == 0


def test_the_drain_respects_its_cap(engine: Engine, tmp_path: Path) -> None:
    for token in ("a", "b", "c"):
        _seed(engine, f"https://grnh.se/{token}")
    run = insert_run(engine)
    report = drain_grnh_seeds(
        engine,
        fetcher=_StubFetcher(),  # type: ignore[arg-type]
        run_id=run,
        now=NOW,
        data_dir=tmp_path,
        limit=2,
    )
    assert (report.followed, report.selectable) == (2, 3)
    # The un-followed seed is still selectable; the two followed ones were charged an attempt and
    # remain selectable until the ceiling retires them.
    assert _seed_count(engine) == 3
