"""get_or_create_master_artifact: idempotent by (kind='resume_master', content_hash).

A master résumé is content-addressed: re-tailoring from the same authored master must
reuse the one master artifact, never accrete duplicates (P7 lineage). These tests seed
directly through the store, mirroring tests/unit/test_reports_notify.py's engine helper.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine

from boardwatch.store.artifacts import get_or_create_master_artifact
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.tables import artifacts


def _engine(tmp_path: Path) -> Engine:
    engine = get_engine(tmp_path / "data")
    ensure_schema(engine)
    return engine


def test_same_content_hash_is_reselected_not_duplicated(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    with engine.begin() as conn:
        first = get_or_create_master_artifact(
            conn, content_hash="abc", uri="/r.yaml", generator_version="tier-a-1", meta={"k": "v"}
        )
    with engine.begin() as conn:
        second = get_or_create_master_artifact(
            conn, content_hash="abc", uri="/r.yaml", generator_version="tier-a-1", meta={"k": "v"}
        )
    assert first == second
    with engine.connect() as conn:
        masters = [
            r for r in conn.execute(artifacts.select()).fetchall() if r.kind == "resume_master"
        ]
    assert len(masters) == 1
    assert masters[0].id == first


def test_different_content_hash_creates_a_second_master(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    with engine.begin() as conn:
        a = get_or_create_master_artifact(
            conn, content_hash="h1", uri="/r.yaml", generator_version="tier-a-1", meta={}
        )
        b = get_or_create_master_artifact(
            conn, content_hash="h2", uri="/r.yaml", generator_version="tier-a-1", meta={}
        )
    assert a != b
    with engine.connect() as conn:
        masters = [
            r for r in conn.execute(artifacts.select()).fetchall() if r.kind == "resume_master"
        ]
    assert len(masters) == 2
