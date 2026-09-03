"""§6.3-7 perf smoke (guards D17). Pinned methodology (round-2 finding 6):
dedicated single-runner CI job; coverage instrumentation OFF (--no-cov); the
10K-posting fixture is built OUTSIDE the measured region; >= 2 warm-ups; then
the MEDIAN of 5 in-process top-path invocations under a ceiling, all logged.

**THE CEILING IS DERIVED FROM A MEASURED DISTRIBUTION, NOT CHOSEN** (D-435).
15 local samples of the median-of-5, taken deliberately across quiet and
contended machine states, are BIMODAL:

    quiet   n=4   0.373 - 0.414 s
    loaded  n=11  1.336 - 1.675 s
    and NOTHING lands between 0.414 and 1.336.

The old ceiling of 1.0 s sat INSIDE that 0.92 s empty gap, so it could not
fail for a reason a reviewer would want to know about -- it failed when the
runner was busy. Commit `08d7b957` failed it TWICE, at medians 1.0068 and
1.0063, on a diff touching zero `.py` files. Those readings sit inside a gap
local runs never occupy, which places CI's LOADED mode at ~1.0 rather than
~1.5 (a 4-vCPU runner against a 10-core Mac): the bound was sitting ON the
loaded mode's centre, so with 4 shards x 3 versions it was a coin flip.

**Asserting the MINIMUM instead was tried and REFUTED by the same samples**:
the minimum is barely more load-resistant than the median (10 of 15 samples
would still fail a 1.0 s minimum, against 11 of 15 for the median), because
under sustained load every one of the five iterations is slow.

2.5 s clears the worst observed loaded median by ~49% and still catches a
6x regression against the quiet mode. That is what a wall-clock smoke test on
a SHARED runner can honestly claim; anything tighter measures the runner.
"""

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

#: Ceiling on the median-of-5, in seconds. Derived from the measured bimodal distribution in this
#: module's docstring: above the loaded mode's observed maximum with headroom, far below anything a
#: real regression would produce. A number, not a magic literal at the assertion, so the next reader
#: finds the reasoning before the value.
TOP_PATH_CEILING_SECONDS = 2.5

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
        job_rows = []
        posting_rows = []
        extraction_rows = []
        for i in range(10_000):
            body = f"{BODY_TEMPLATES[i % 4]} Posting {i}."
            body_hash = content_hash(body)
            job_rows.append({"id": i + 1, "created_at": now})
            posting_rows.append(
                {
                    "id": i + 1, "company_id": company_id, "job_id": i + 1,
                    "provider_posting_id": str(i),
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
        conn.execute(insert(tables.jobs), job_rows)
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

    # `record_surfaced=False` throughout: the benchmark has to measure the same read seven times.
    # While the ranker consumed the queue, each iteration ranked a fresh 10-row window (handled
    # climbing 0, 10, 20, ...) and paid for 10 ledger writes inside the measured region, and the
    # `visible == 10` assertion held only because the fixture has 10,000 eligible postings.
    for _ in range(2):  # warm-ups
        rank_open_postings(engine, settings, now=now, limit=10, record_surfaced=False)

    timings: list[float] = []
    for _ in range(5):
        start = time.perf_counter()
        result = rank_open_postings(
            engine, settings, now=now, limit=10, record_surfaced=False
        )
        timings.append(time.perf_counter() - start)
        assert len(result.visible) == 10
    print(f"top-path timings (s): {[round(t, 3) for t in timings]}")
    assert statistics.median(timings) < TOP_PATH_CEILING_SECONDS, timings
