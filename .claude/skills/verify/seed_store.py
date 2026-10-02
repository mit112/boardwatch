"""Seed a synthetic, isolated boardwatch store for driving the web viewer.

Usage: .venv/bin/python .claude/skills/verify/seed_store.py <empty scratch dir>

It reuses the server test's own seeding helpers, so the rows have the shape the API reads. Nothing
here ever opens the owner's store: the data and config dirs are redirected into the scratch dir
before boardwatch is imported.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(sys.argv[1])
os.environ["BOARDWATCH_CONFIG_DIR"] = str(ROOT / "config")
os.environ["BOARDWATCH_DATA_DIR"] = str(ROOT / "data")
# The repo root, so the tests package imports.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sqlalchemy import insert, update  # noqa: E402

from boardwatch.core.clock import utcnow  # noqa: E402
from boardwatch.store.applications import create_application  # noqa: E402
from boardwatch.store.db import ensure_schema, get_engine  # noqa: E402
from boardwatch.store.tables import postings, runs  # noqa: E402
from tests.conftest import write_bundled_role_taxonomy  # noqa: E402
from tests.unit import test_web_server as helpers  # noqa: E402

JD_YEARS = "We build lovely software. Requires 3+ years of professional experience."
LONG_TITLE = (
    "Senior Staff Principal Distinguished Site Reliability and Platform Infrastructure Engineer, "
    "Cloud Data Services and Developer Experience (Remote-Eligible)"
)


def main() -> None:
    write_bundled_role_taxonomy(ROOT / "config")
    out = ROOT / "out"
    out.mkdir(parents=True, exist_ok=True)
    engine = get_engine(ROOT / "data")
    ensure_schema(engine)

    def pdf(key: str) -> str:
        path = out / key / "resume.pdf"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(helpers.PDF_BYTES)
        return str(path)

    with engine.begin() as conn:
        run1 = helpers._run(conn)
        deliver = helpers._deliver
        deliver(conn, "a1", title="Backend Engineer", pdf_uri=pdf("a1"))
        deliver(conn, "a2", title=LONG_TITLE, pdf_uri=pdf("a2"))
        deliver(conn, "a3", title="Data Engineer", pdf_uri=pdf("a3"), locations=[])
        deliver(
            conn, "a4", title="Platform Engineer", pdf_uri=pdf("a4"), url="javascript:alert(1)"
        )
        deliver(conn, "a5", title="ML Engineer", pdf_uri=None)
        deliver(
            conn,
            "a6",
            title="Student Program Engineer",
            body=helpers.JD_UNCERTAIN_STATED,
            pdf_uri=pdf("a6"),
        )
        deliver(
            conn, "a7", title="Experience Gate Engineer", body=JD_YEARS, pdf_uri=pdf("a7")
        )
        deliver(
            conn,
            "r1",
            title="Review Lane Engineer",
            body=helpers.JD_UNCERTAIN,
            pdf_uri=pdf("r1"),
        )
        closed, _ = deliver(conn, "c1", title="Closed Engineer", pdf_uri=pdf("c1"))
        conn.execute(
            update(postings)
            .where(postings.c.id == closed)
            .values(status="closed", closed_at=helpers.NOW)
        )
        # A manual re-render run: a row with NO funnel artifact (the "404 from /api/runs/N" case).
        conn.execute(
            insert(runs).values(
                started_at=helpers.NOW,
                finished_at=helpers.NOW,
                boards_attempted=0,
                boards_complete=0,
                postings_seen=0,
                new_count=0,
                status="ok",
            )
        )
        # Application history: one recorded today, one three days ago.
        first = helpers._undelivered(conn, "h1")
        second = helpers._undelivered(conn, "h2")
        create_application(
            conn, job_id=first, status="applied", source="import", occurred_at=utcnow()
        )
        create_application(
            conn,
            job_id=second,
            status="applied",
            source="import",
            occurred_at=utcnow() - timedelta(days=3),
        )

    day = out / "2026-08-26"
    day.mkdir(exist_ok=True)
    # A thin funnel. The Runs page needs a FULL-shape one (see SKILL.md); replace this file.
    thin = {"run_id": run1, "stages": [], "reconciles": True}
    (day / f"funnel-{run1}.json").write_text(json.dumps(thin), encoding="utf-8")
    print("seeded", ROOT)


main()
