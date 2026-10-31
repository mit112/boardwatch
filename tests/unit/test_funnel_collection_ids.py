"""The corpus-wide abstain read needs current version IDs, never frozen JD bodies."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import event, insert, select

from boardwatch.pipeline import funnel_writer
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import current_posting_version_ids, current_posting_versions
from tests.conftest import write_bundled_role_taxonomy
from tests.unit.test_apply_lane_cohort import _funnel, _run
from tests.unit.test_apply_lane_drought import APPLY_LOCATION, NOW, _lead


@pytest.fixture()
def corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("BOARDWATCH_DATA_DIR", str(tmp_path / "data"))
    write_bundled_role_taxonomy(tmp_path / "config")
    engine = get_engine(tmp_path / "data")
    ensure_schema(engine)
    run_id = _run(engine)
    with engine.begin() as conn:
        first, version = _lead(conn, run_id=run_id, locations=APPLY_LOCATION)
        second, _ = _lead(conn, run_id=run_id, locations=APPLY_LOCATION)
        closed, _ = _lead(conn, run_id=run_id, locations=APPLY_LOCATION, status="closed")
        # An older capture with a larger ID must not become current.
        conn.execute(insert(tables.posting_versions).values(
            posting_id=first, content_hash="old-capture", body_text="obsolete body",
            captured_at=NOW - timedelta(days=1), capture_reason="new",
        ))
        # Same timestamp: the larger ID wins, leaving second's old evaluation stale.
        latest = int(conn.execute(insert(tables.posting_versions).values(
            posting_id=second, content_hash="tie-winner", body_text="changed body",
            captured_at=NOW, capture_reason="revised",
        )).inserted_primary_key[0])
        # No delivered leads: bounded, body-dependent lane reads are outside this test.
        conn.execute(tables.artifacts.delete())
    return engine, run_id, {first: version, second: latest}, closed


def test_ids_only_open_sweep_matches_current_versions_without_reading_bodies(corpus) -> None:
    engine, _, expected, closed = corpus
    with engine.connect() as conn:
        assert {
            pid: version.posting_version_id
            for pid, version in current_posting_versions(conn, None).items()
        } == expected, "guard: the reference must exercise status and both tie-break fields"
        actual = current_posting_version_ids(conn, None)
        assert actual == expected
        assert current_posting_version_ids(conn, []) == {}
        assert closed in current_posting_version_ids(conn, [closed])


def test_collection_preserves_funnel_counts_without_materializing_corpus_bodies(
    corpus, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, run_id, _, _ = corpus
    # Force the old reader as an independent reference, also after production switches readers.
    with monkeypatch.context() as reference_patch:
        if hasattr(funnel_writer, "current_posting_version_ids"):
            reference_patch.setattr(
                funnel_writer, "current_posting_version_ids",
                lambda conn, ids: {
                    pid: cv.posting_version_id
                    for pid, cv in current_posting_versions(conn, ids).items()
                },
            )
        reference = _funnel(engine, run_id, [])
    body_selects = []

    def record(_conn, clause, *_args):
        columns = getattr(clause, "selected_columns", ())
        if any(column.name == "body_text" for column in columns):
            body_selects.append(str(clause))

    event.listen(engine, "before_execute", record)
    try:
        actual = _funnel(engine, run_id, [])
    finally:
        event.remove(engine, "before_execute", record)

    assert actual.stages == reference.stages
    assert actual.abstain == reference.abstain
    assert actual.sources == reference.sources
    with engine.connect() as conn:
        assert conn.execute(select(tables.postings.c.id)).all(), "guard: nonempty corpus"
    assert not body_selects, "funnel collection materialized body_text for the open corpus"
