"""Boards named by the store's verified application destinations (D-692).

Every expected value comes from the measured replay of the store's table, not from the candidate
function: a read-only run over 406 destinations parsed 161 to a board, 36 of them the ATS chrome
class (greenhouse's `embed` widget), and 7 workday slugs were career-site spellings/slices of an
already-watched tenant. Fixture names are made up.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest
import yaml
from sqlalchemy import Connection, Engine, insert, select
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.lanes.destination_boards import (
    DestinationCensus,
    candidate_boards,
    candidate_document,
    workday_tenant,
)
from boardwatch.registry.validate import CompanyEntry
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.tables import application_destinations, companies, jobs, postings

TODAY = date(2026, 11, 10)
NOW = datetime(2026, 11, 10, 12, 0, 0)
runner = CliRunner()


def _boards(
    destinations: list[tuple[int, str]],
    *,
    watched: set[tuple[str, str]] | None = None,
    tenants: set[tuple[str, str]] | None = None,
) -> tuple[object, DestinationCensus]:
    return candidate_boards(
        destinations,
        watched=watched or set(),
        watched_workday_tenants=tenants or set(),
    )


def test_a_board_named_by_a_verified_destination_is_proposed() -> None:
    boards, census = _boards(
        [(1, "https://job-boards.greenhouse.io/acme/jobs/42")]
    )
    assert [(b.provider, b.slug) for b in boards] == [("greenhouse", "acme")]  # type: ignore[union-attr]
    assert boards[0].evidence_posting_id == 1  # type: ignore[index]
    assert census.unparsed == 0
    assert census.boards == 1


def test_an_already_watched_board_is_not_proposed() -> None:
    boards, census = _boards(
        [(1, "https://job-boards.greenhouse.io/acme/jobs/42")],
        watched={("greenhouse", "acme")},
    )
    assert boards == ()  # type: ignore[comparison-overlap]
    assert (census.already_watched, census.boards) == (1, 0)


def test_the_greenhouse_embed_widget_is_not_a_candidate() -> None:
    """`/embed/job_app?for=<slug>&token=...` parses as board `embed`; it is ATS chrome."""
    boards, census = _boards(
        [(1, "https://job-boards.greenhouse.io/embed/job_app?for=acme&token=1")],
        watched=set(),
    )
    assert boards == ()  # type: ignore[comparison-overlap]
    assert (census.false_candidates, census.boards) == (1, 0)


def test_the_shared_ats_chrome_catalog_is_refused_for_every_provider() -> None:
    """`lanes/common_crawl.ATS_CHROME` is the repo's existing closed list of ATS furniture."""
    boards, census = _boards(
        [
            (1, "https://job-boards.greenhouse.io/api/jobs/1"),
            (2, "https://jobs.lever.co/embed/00000000-0000-0000-0000-000000000001"),
            (
                3,
                "https://jobs.smartrecruiters.com/oneclick-ui/company/Acme/"
                "publication/7370000000000000001",
            ),
        ]
    )
    assert boards == ()  # type: ignore[comparison-overlap]
    assert (census.false_candidates, census.parsed) == (3, 3)


def test_a_workday_site_spelling_of_a_watched_tenant_is_not_a_candidate() -> None:
    watched_slug = "hpe.wd5.myworkdayjobs.com/hpe/acjobsite"
    boards, census = _boards(
        [
            (
                1,
                "https://hpe.wd5.myworkdayjobs.com/en-US/Jobsathpe/"
                "job/Roseville/Software-Engineer_1213624-1",
            )
        ],
        watched={("workday", watched_slug.lower())},
        tenants={workday_tenant(watched_slug)},  # type: ignore[arg-type]
    )
    assert boards == ()  # type: ignore[comparison-overlap]
    assert (census.workday_variants, census.boards) == (1, 0)


def test_an_unwatched_workday_tenant_is_proposed_with_its_tenant_name() -> None:
    boards, _ = _boards([(1, "https://acme.wd1.myworkdayjobs.com/en-US/AcmeCareers/job/Austin/Engineer_1")])
    assert [(b.provider, b.slug, b.name) for b in boards] == [  # type: ignore[union-attr]
        ("workday", "acme.wd1.myworkdayjobs.com/acme/AcmeCareers", "acme")
    ]


def test_two_destinations_on_one_board_are_one_candidate() -> None:
    boards, census = _boards(
        [
            (1, "https://job-boards.greenhouse.io/acme/jobs/42"),
            (2, "https://boards.greenhouse.io/acme/jobs/43"),
        ]
    )
    assert len(boards) == 1  # type: ignore[arg-type]
    assert boards[0].postings == 2  # type: ignore[index]
    assert census.parsed == 2


def test_a_destination_on_an_unregistered_host_is_counted_not_proposed() -> None:
    boards, census = _boards([(1, "https://joinbytedance.com/search/7668484998475663621")])
    assert boards == ()  # type: ignore[comparison-overlap]
    assert (census.unparsed, census.parsed) == (1, 0)


def test_the_document_is_a_registry_file_companies_import_validates() -> None:
    boards, census = _boards(
        [
            (1, "https://job-boards.greenhouse.io/acme/jobs/42"),
            (2, "https://acme.wd1.myworkdayjobs.com/en-US/AcmeCareers/job/Austin/Engineer_1"),
        ]
    )
    document = candidate_document(boards, census=census, generated_on=TODAY)  # type: ignore[arg-type]
    payload = yaml.safe_load(document)
    rows = payload["companies"]
    assert len(rows) == 2
    for row in rows:
        # `CompanyEntry` forbids extra fields, which is why provenance travels as comments.
        CompanyEntry.model_validate(row)
    assert "generated 2026-11-10" in document
    assert "#   greenhouse:acme | acme | 1 posting(s) |" in document


# --- the command ---------------------------------------------------------------------------


def _store(tmp_path: Path) -> Engine:
    engine = get_engine(tmp_path / "data")
    ensure_schema(engine)
    return engine


def _company(conn: Connection, name: str, provider: str, slug: str, *, watched: bool) -> int:
    return int(
        conn.execute(
            insert(companies).values(
                name=name, provider=provider, slug=slug, source="user", watched=watched
            )
        ).inserted_primary_key[0]
    )


def _destination(conn: Connection, company_id: int, url: str, key: str) -> None:
    job = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
    posting = int(
        conn.execute(
            insert(postings).values(
                company_id=company_id,
                job_id=job,
                provider_posting_id=key,
                title="Software Engineer",
                normalized_title="software engineer",
                url="https://www.linkedin.com/jobs/view/1",
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
    conn.execute(
        insert(application_destinations).values(
            posting_id=posting,
            url=url,
            source_url="https://www.linkedin.com/jobs/view/1",
            evidence_ref="browser:verified",
            verified_at=NOW,
        )
    )


def test_the_command_writes_the_file_and_watches_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _store(tmp_path)
    with engine.begin() as conn:
        lane = _company(conn, "Acme", "linkedin", "linkedin-acme", watched=False)
        _destination(conn, lane, "https://job-boards.greenhouse.io/newco/jobs/42", "a")
        watched = _company(conn, "Watched", "greenhouse", "watchedco", watched=True)
        _destination(conn, watched, "https://job-boards.greenhouse.io/watchedco/jobs/1", "b")
    monkeypatch.setenv("BOARDWATCH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    out = tmp_path / "candidates.yaml"
    result = runner.invoke(app, ["companies", "discover-destinations", "--out", str(out)])
    assert result.exit_code == 0, result.output
    payload = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert [row["slug"] for row in payload["companies"]] == ["newco"]
    with engine.connect() as conn:
        watched_after = conn.execute(
            select(companies.c.slug).where(companies.c.watched.is_(True))
        ).scalars().all()
    assert list(watched_after) == ["watchedco"]  # the command watched nothing
