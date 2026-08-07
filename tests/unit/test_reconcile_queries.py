"""The store half of `boardwatch verify` (P0 item 5).

These pin the scoping the pure core cannot: run_id filtering, kind filtering, and that
resume_tailored_llm rows are covered by the file check but NOT by the Class-A resume_tailored
count. Seeded through record_artifact / record_evaluation, the production write paths.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, insert

from boardwatch.core.clock import utcnow
from boardwatch.store.artifacts import record_artifact
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.reconcile_queries import db_counts_for_run, tailored_file_rows
from boardwatch.store.tables import companies, jobs, posting_versions, postings, runs

NOW = utcnow()


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path)
    ensure_schema(eng)
    return eng


def _run(conn: Connection, *, status: str = "ok") -> int:
    return int(conn.execute(
        insert(runs).values(started_at=NOW, boards_attempted=0, status=status)
    ).inserted_primary_key[0])


def _version(conn: Connection, tag: str) -> int:
    cid = int(conn.execute(insert(companies).values(
        name="Acme", provider="greenhouse", slug=f"b-{tag}", source="user", watched=True,
    )).inserted_primary_key[0])
    jid = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
    pid = int(conn.execute(insert(postings).values(
        company_id=cid, job_id=jid, provider_posting_id=tag, title="Eng", normalized_title="eng",
        first_seen_at=NOW, last_seen_at=NOW, status="open", consecutive_missing=0,
        content_hash=tag, body_text="b",
    )).inserted_primary_key[0])
    return int(conn.execute(insert(posting_versions).values(
        posting_id=pid, content_hash=tag, body_text="b", captured_at=NOW, run_id=None,
        capture_reason="new",
    )).inserted_primary_key[0])


def test_db_counts_scope_by_run_and_kind(engine: Engine) -> None:
    with engine.begin() as conn:
        run_id = _run(conn)
        other = _run(conn)
        v1, v2 = _version(conn, "v1"), _version(conn, "v2")
        v_other = _version(conn, "vo")
        record_artifact(conn, kind="resume_tailored", uri="/a.typ", posting_version_id=v1,
                        meta={"typst_pdf_built": True, "pdf_uri": "/a.pdf"}, run_id=run_id)
        record_artifact(conn, kind="resume_tailored", uri="/b.typ", posting_version_id=v2,
                        meta={"typst_pdf_built": False, "pdf_uri": None}, run_id=run_id)
        # excluded: wrong run, and an LLM row (not a resume_tailored count)
        record_artifact(conn, kind="resume_tailored", uri="/o.typ", posting_version_id=v_other,
                        meta={"typst_pdf_built": True, "pdf_uri": "/o.pdf"}, run_id=other)
        record_artifact(conn, kind="resume_tailored_llm", uri="/a.llm.typ",
                        posting_version_id=v1, meta={}, run_id=run_id)
    with engine.connect() as conn:
        counts = db_counts_for_run(conn, run_id)
    assert counts.tailored_rows == 2
    assert counts.tailored_with_pdf == 1
    assert counts.distinct_lead_postings == 2
    assert counts.run_status == "ok"


def test_null_run_id_artifacts_are_excluded(engine: Engine) -> None:
    with engine.begin() as conn:
        run_id = _run(conn)
        v1 = _version(conn, "v1")
        record_artifact(conn, kind="resume_tailored", uri="/n.typ", posting_version_id=v1,
                        meta={"typst_pdf_built": True, "pdf_uri": "/n.pdf"}, run_id=None)
    with engine.connect() as conn:
        counts = db_counts_for_run(conn, run_id)
    assert counts.tailored_rows == 0


def test_tailored_file_rows_covers_both_kinds(engine: Engine) -> None:
    with engine.begin() as conn:
        run_id = _run(conn)
        v1 = _version(conn, "v1")
        record_artifact(conn, kind="resume_tailored", uri="/a.typ", posting_version_id=v1,
                        meta={"typst_pdf_built": True, "pdf_uri": "/a.pdf"}, run_id=run_id)
        record_artifact(conn, kind="resume_tailored_llm", uri="/a.llm.typ",
                        posting_version_id=v1, meta={}, run_id=run_id)
    with engine.connect() as conn:
        rows = tailored_file_rows(conn, run_id)
    by_kind = {row.kind: row for row in rows}
    assert set(by_kind) == {"resume_tailored", "resume_tailored_llm"}
    assert by_kind["resume_tailored"].pdf_built is True
    assert by_kind["resume_tailored"].pdf_uri == "/a.pdf"
    assert by_kind["resume_tailored_llm"].pdf_built is False
    assert by_kind["resume_tailored_llm"].pdf_uri is None
