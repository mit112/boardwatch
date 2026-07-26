from pathlib import Path

import pytest
from sqlalchemy import Engine, insert
from sqlalchemy.exc import IntegrityError

from boardwatch.core.clock import utcnow
from boardwatch.store.artifacts import (
    add_derivation,
    get_derivations,
    list_artifacts,
    record_artifact,
)
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.tables import jobs


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path)
    ensure_schema(eng)
    return eng


@pytest.fixture()
def job_id(engine: Engine) -> int:
    with engine.begin() as conn:
        return int(conn.execute(insert(jobs).values(created_at=utcnow())).inserted_primary_key[0])


def test_record_with_lineage_and_list(engine, job_id):
    with engine.begin() as conn:
        record_artifact(conn, kind="resume", uri="/r/base.pdf", job_id=job_id,
                        generator="deterministic", media_type="application/pdf", byte_size=1024,
                        meta={"template": "modern"})
    with engine.connect() as conn:
        rows = list_artifacts(conn, job_id=job_id)
    assert len(rows) == 1
    assert rows[0].kind == "resume"
    assert rows[0].media_type == "application/pdf"
    assert rows[0].meta_json == {"template": "modern"}


def test_global_artifact_and_derivation(engine, job_id):
    with engine.begin() as conn:
        base = record_artifact(conn, kind="resume", uri="/r/base.pdf", job_id=job_id)
        tailored = record_artifact(conn, kind="tailored_resume", uri="/r/tailored.pdf", job_id=job_id)
        add_derivation(conn, artifact_id=tailored, parent_artifact_id=base, relation="tailored_from")
        record_artifact(conn, kind="export", uri="/e/all.jsonl")  # global (job_id None)
    with engine.connect() as conn:
        derivations = get_derivations(conn, tailored)
        all_rows = list_artifacts(conn)
    assert len(all_rows) == 3
    assert derivations[0].parent_artifact_id == base
    assert derivations[0].relation == "tailored_from"


def test_derivations_are_immutable(engine, job_id):
    from sqlalchemy import text
    with engine.begin() as conn:
        a = record_artifact(conn, kind="resume", uri="/r/a.pdf", job_id=job_id)
        b = record_artifact(conn, kind="tailored_resume", uri="/r/b.pdf", job_id=job_id)
        add_derivation(conn, artifact_id=b, parent_artifact_id=a, relation="tailored_from")
    with engine.begin() as conn, pytest.raises(IntegrityError):
        conn.execute(text("DELETE FROM artifact_derivations WHERE artifact_id=:b"), {"b": b})
