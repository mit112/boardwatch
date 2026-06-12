"""§6.3-7 perf smoke (guards D17). Pinned methodology (round-2 finding 6):
dedicated single-runner CI job; coverage instrumentation OFF (--no-cov); the
10K-posting fixture is built OUTSIDE the measured region; >= 2 warm-ups; then
the MEDIAN of 5 in-process top-path invocations < 1 s, all timings logged."""

import statistics
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import insert

from boardwatch.cli.top_cmd import rank_open_postings
from boardwatch.core.normalize import content_hash
from boardwatch.core.settings import Settings
from boardwatch.extract.taxonomy import load_taxonomy
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine

BODY_TEMPLATES = [
    "Python and PostgreSQL services on AWS.",
    "Go microservices with Kubernetes and Terraform.",
    "React and TypeScript frontend with GraphQL.",
    "Kafka streaming pipelines in Java.",
]


@pytest.mark.perf
def test_top_path_median_under_one_second(tmp_path: Path) -> None:
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    settings = Settings(data_dir=tmp_path / "data", config_dir=cfg)
    engine = get_engine(settings.data_dir)
    ensure_schema(engine)
    taxonomy = load_taxonomy(cfg)
    now = datetime(2026, 6, 11)

    # ---------- fixture built OUTSIDE the measured region ----------
    template_hits = [sorted(taxonomy.extract(body)) for body in BODY_TEMPLATES]
    with engine.begin() as conn:
        company_id = int(
            conn.execute(
                insert(tables.companies).values(
                    name="Acme", provider="greenhouse", slug="acme", source="user", watched=True
                )
            ).inserted_primary_key[0]
        )
        posting_rows = []
        extraction_rows = []
        for i in range(10_000):
            body = f"{BODY_TEMPLATES[i % 4]} Posting {i}."
            body_hash = content_hash(body)
            posting_rows.append(
                {
                    "id": i + 1, "company_id": company_id, "provider_posting_id": str(i),
                    "title": "Backend Engineer" if i % 3 else "Platform Engineer",
                    "normalized_title": "backend engineer", "url": f"https://x.example/{i}",
                    "locations_json": ["Remote — US"], "remote_policy": "remote",
                    "posted_at": now - timedelta(days=i % 60),
                    "first_seen_at": now, "last_seen_at": now, "status": "open",
                    "consecutive_missing": 0, "content_hash": body_hash, "body_text": body,
                }
            )
            hits = template_hits[i % 4]
            extraction_rows.append(
                {
                    "posting_id": i + 1, "content_hash": body_hash, "kind": "taxonomy",
                    "engine_version": taxonomy.version,
                    "json": {"skills": hits, "categories": {}}, "created_at": now,
                }
            )
        conn.execute(insert(tables.postings), posting_rows)
        conn.execute(insert(tables.extractions), extraction_rows)
        conn.execute(
            insert(tables.profile).values(
                id=1, text="perf profile", skills_json=["Python", "Go", "PostgreSQL"],
                taxonomy_version=taxonomy.version,
                target_titles_json=["Backend Engineer"], exclude_titles_json=[],
                locations_json=["Remote"], remote_only=False, updated_at=now,
            )
        )

    for _ in range(2):  # warm-ups
        rank_open_postings(engine, settings, now=now, limit=10)

    timings: list[float] = []
    for _ in range(5):
        start = time.perf_counter()
        result = rank_open_postings(engine, settings, now=now, limit=10)
        timings.append(time.perf_counter() - start)
        assert len(result) == 10
    print(f"top-path timings (s): {[round(t, 3) for t in timings]}")
    assert statistics.median(timings) < 1.0, timings
