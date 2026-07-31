"""The funnel display join: application -> job -> a posting -> company.

A tracked job can outlive the posting that started it (the posting closes, the job row
stays), so the join to postings is an OUTER join and the display fields are nullable.
A4: display context follows the posting_version_id the application was made against and
falls back to the job's lowest posting id only when that link is NULL.
"""

from pathlib import Path

import pytest
from sqlalchemy import Engine, insert
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.core.clock import utcnow
from boardwatch.store.applications import create_application, set_application_status
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.funnel_queries import job_id_for_posting, list_funnel
from boardwatch.store.tables import companies, jobs, posting_versions, postings

# Naive UTC, matching boardwatch.core.clock.utcnow() (A2).
NOW = utcnow()

runner = CliRunner()


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path)
    ensure_schema(eng)
    return eng


def _posting(conn, title: str) -> tuple[int, int]:
    company_id = int(
        conn.execute(
            insert(companies).values(
                name="Acme", provider="greenhouse", slug=f"acme-{title}",
                source="user", watched=True,
            )
        ).inserted_primary_key[0]
    )
    job_id = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
    posting_id = int(
        conn.execute(
            insert(postings).values(
                company_id=company_id, job_id=job_id, provider_posting_id=title,
                title=title, normalized_title=title, url=f"https://example.test/{title}",
                locations_json=["Remote"], remote_policy="remote",
                first_seen_at=NOW, last_seen_at=NOW, status="open",
                consecutive_missing=0, content_hash=title,
                body_text=f"We are hiring a {title} engineer.",
            )
        ).inserted_primary_key[0]
    )
    return posting_id, job_id


def test_job_id_for_posting_resolves(engine: Engine) -> None:
    with engine.begin() as conn:
        posting_id, job_id = _posting(conn, "alpha")
        assert job_id_for_posting(conn, posting_id) == job_id


def test_job_id_for_an_unknown_posting_is_none(engine: Engine) -> None:
    with engine.connect() as conn:
        assert job_id_for_posting(conn, 9999) is None


def test_list_funnel_carries_display_context(engine: Engine) -> None:
    with engine.begin() as conn:
        posting_id, job_id = _posting(conn, "alpha")
        create_application(conn, job_id=job_id, status="interested", source="user")
    with engine.connect() as conn:
        rows = list_funnel(conn)
    assert len(rows) == 1
    assert rows[0].title == "alpha"
    assert rows[0].company == "Acme"
    assert rows[0].posting_id == posting_id
    assert rows[0].status == "interested"
    assert rows[0].attempt_no == 1


def test_list_funnel_filters_by_status(engine: Engine) -> None:
    with engine.begin() as conn:
        _, job_a = _posting(conn, "alpha")
        _, job_b = _posting(conn, "beta")
        app_a = create_application(conn, job_id=job_a, status="interested", source="user")
        create_application(conn, job_id=job_b, status="interested", source="user")
        set_application_status(conn, application_id=app_a, to_status="applied", source="user")
    with engine.connect() as conn:
        applied = list_funnel(conn, status="applied")
    assert [r.title for r in applied] == ["alpha"]


def test_list_funnel_shows_the_tracked_posting_when_one_job_anchors_two(
    engine: Engine,
) -> None:
    """A4: display follows the tracked posting_version_id, not the job's lowest posting id."""
    with engine.begin() as conn:
        company_id = int(
            conn.execute(
                insert(companies).values(
                    name="Acme", provider="greenhouse", slug="acme-two",
                    source="user", watched=True,
                )
            ).inserted_primary_key[0]
        )
        job_id = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
        posting_ids: list[int] = []
        version_ids: list[int] = []
        for title in ("first", "second"):
            posting_id = int(
                conn.execute(
                    insert(postings).values(
                        company_id=company_id, job_id=job_id,
                        provider_posting_id=f"p-{title}", title=title,
                        normalized_title=title, url=f"https://example.test/{title}",
                        locations_json=["Remote"], remote_policy="remote",
                        first_seen_at=NOW, last_seen_at=NOW, status="open",
                        consecutive_missing=0, content_hash=f"h-{title}",
                        body_text=f"We are hiring a {title} engineer.",
                    )
                ).inserted_primary_key[0]
            )
            posting_ids.append(posting_id)
            version_ids.append(
                int(
                    conn.execute(
                        insert(posting_versions).values(
                            posting_id=posting_id, content_hash=f"h-{title}",
                            body_text=f"We are hiring a {title} engineer.",
                            captured_at=NOW, capture_reason="new",
                        )
                    ).inserted_primary_key[0]
                )
            )
        create_application(
            conn,
            job_id=job_id,
            posting_version_id=version_ids[1],  # the non-minimum posting is the tracked one
            status="interested",
            source="user",
        )
    with engine.connect() as conn:
        rows = list_funnel(conn)
    assert len(rows) == 1
    assert rows[0].posting_id == posting_ids[1]
    assert rows[0].title == "second"
    assert rows[0].company == "Acme"


def test_reapplication_shows_both_attempts(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A7: a second attempt goes through --new-attempt, and list_funnel shows both rows."""
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    with engine.begin() as conn:
        posting_id, _ = _posting(conn, "alpha")
    first = runner.invoke(app, ["--data-dir", str(tmp_path), "track", "add", str(posting_id)])
    assert first.exit_code == 0
    second = runner.invoke(
        app,
        ["--data-dir", str(tmp_path), "track", "add", str(posting_id), "--new-attempt"],
    )
    assert second.exit_code == 0
    with engine.connect() as conn:
        rows = list_funnel(conn)
    assert sorted(r.attempt_no for r in rows) == [1, 2]
