from pathlib import Path

import pytest
from sqlalchemy import Engine, insert

from boardwatch.core.clock import utcnow
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.stats_queries import count_open_postings, count_tracked_submitted
from boardwatch.store.tables import applications, companies, jobs, postings

NOW = utcnow()


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path)
    ensure_schema(eng)
    return eng


def _company(conn) -> int:
    return int(conn.execute(insert(companies).values(
        name="Acme", provider="greenhouse", slug="acme", source="user", watched=True,
    )).inserted_primary_key[0])


def _posting(conn, company_id: int, slug: str, status: str) -> int:
    job_id = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
    return int(conn.execute(insert(postings).values(
        company_id=company_id, job_id=job_id, provider_posting_id=slug,
        title=slug, normalized_title=slug, url=f"https://example.test/{slug}",
        locations_json=["Remote"], remote_policy="remote", posted_at=NOW,
        first_seen_at=NOW, last_seen_at=NOW, status=status, consecutive_missing=0,
        content_hash=slug, body_text="body",
    )).inserted_primary_key[0])


def test_count_open_postings_counts_only_open(engine: Engine) -> None:
    with engine.begin() as conn:
        c = _company(conn)
        _posting(conn, c, "a", "open")
        _posting(conn, c, "b", "open")
        _posting(conn, c, "c", "closed")
    with engine.connect() as conn:
        assert count_open_postings(conn) == 2


def test_count_tracked_submitted_ignores_unsubmitted(engine: Engine) -> None:
    with engine.begin() as conn:
        job_id = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
        other = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
        conn.execute(insert(applications).values(
            job_id=job_id, attempt_no=1, status="applied",
            created_at=NOW, updated_at=NOW, submitted_at=NOW,
        ))
        conn.execute(insert(applications).values(
            job_id=other, attempt_no=1, status="interested",
            created_at=NOW, updated_at=NOW, submitted_at=None,
        ))
    with engine.connect() as conn:
        assert count_tracked_submitted(conn) == 1
