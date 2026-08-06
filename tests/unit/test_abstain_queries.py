"""The observed half of the abstain metric — what the table actually says, and only that.

Seeds through `record_evaluation`, the production write path, so these counts are read back
out of rows written the way real ones are.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine, insert

from boardwatch.core.clock import utcnow
from boardwatch.store.abstain_queries import count_requirement_dispositions
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.eligibility import RequirementItem, record_evaluation
from boardwatch.store.tables import companies, jobs, posting_versions, postings

NOW = utcnow()


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path)
    ensure_schema(eng)
    return eng


def _version(conn, slug: str) -> int:
    cid = int(conn.execute(insert(companies).values(
        name="Acme", provider="greenhouse", slug=f"acme-{slug}", source="user", watched=True,
    )).inserted_primary_key[0])
    jid = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
    pid = int(conn.execute(insert(postings).values(
        company_id=cid, job_id=jid, provider_posting_id=slug, title="Eng",
        normalized_title="eng", first_seen_at=NOW, last_seen_at=NOW, status="open",
        consecutive_missing=0, content_hash=slug, body_text="b",
    )).inserted_primary_key[0])
    return int(conn.execute(insert(posting_versions).values(
        posting_id=pid, content_hash=slug, body_text="b", captured_at=NOW,
        run_id=None, capture_reason="new",
    )).inserted_primary_key[0])


def _requirement(rule_id: str | None, disposition: str) -> RequirementItem:
    return RequirementItem(
        requiredness="required", requirement_text="text", jd_locator={"span": [0, 1]},
        disposition=disposition, rule_id=rule_id, support=[],
    )


def _record(conn, slug: str, *pairs: tuple[str | None, str]) -> int:
    version_id = _version(conn, slug)
    return record_evaluation(
        conn, posting_version_id=version_id, profile_hash="ph",
        profile_snapshot={}, rules_hash="rh", rules_snapshot={},
        input_fingerprint=f"fp-{slug}", engine_kind="deterministic", engine_version="v1",
        verdict="uncertain", score=None,
        requirements=[_requirement(rule_id, disp) for rule_id, disp in pairs],
    )


def test_counts_group_by_rule_and_disposition(engine: Engine) -> None:
    rule = "work_auth:us_authorization_required"
    with engine.begin() as conn:
        eval_id = _record(conn, "a", (rule, "met"), (rule, "met"), (rule, "unknown"))
    with engine.connect() as conn:
        counts = count_requirement_dispositions(conn, [eval_id])

    assert counts == {(rule, "met"): 2, (rule, "unknown"): 1}


def test_a_null_rule_id_survives_as_a_none_key(engine: Engine) -> None:
    """The schema permits it, so dropping it here would silently lose rows from the funnel."""
    with engine.begin() as conn:
        eval_id = _record(conn, "b", (None, "unknown"))
    with engine.connect() as conn:
        counts = count_requirement_dispositions(conn, [eval_id])

    assert counts == {(None, "unknown"): 1}


def test_only_the_requested_evaluations_are_counted(engine: Engine) -> None:
    with engine.begin() as conn:
        wanted = _record(conn, "c", ("degree:degree_preferred", "met"))
        _record(conn, "d", ("degree:degree_preferred", "unmet"))
    with engine.connect() as conn:
        counts = count_requirement_dispositions(conn, [wanted])

    assert counts == {("degree:degree_preferred", "met"): 1}


def test_no_evaluations_means_no_query_and_no_counts(engine: Engine) -> None:
    with engine.connect() as conn:
        assert count_requirement_dispositions(conn, []) == {}
