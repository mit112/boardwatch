from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, insert

from boardwatch.core.clock import utcnow
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.eligibility import (
    RequirementItem,
    SupportItem,
    get_evaluations,
    get_requirements,
    get_support,
    record_evaluation,
)
from boardwatch.store.tables import companies, jobs, posting_versions, postings


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path)
    ensure_schema(eng)
    return eng


@pytest.fixture()
def version_id(engine: Engine) -> int:
    now = utcnow()
    with engine.begin() as conn:
        cid = int(conn.execute(insert(companies).values(
            name="Acme", provider="greenhouse", slug="acme", source="user", watched=True,
        )).inserted_primary_key[0])
        jid = int(conn.execute(insert(jobs).values(created_at=now)).inserted_primary_key[0])
        pid = int(conn.execute(insert(postings).values(
            company_id=cid, job_id=jid, provider_posting_id="p-1", title="Eng",
            normalized_title="eng", first_seen_at=now, last_seen_at=now, status="open",
            consecutive_missing=0, content_hash="h1", body_text="b",
        )).inserted_primary_key[0])
        return int(conn.execute(insert(posting_versions).values(
            posting_id=pid, content_hash="h1", body_text="b", captured_at=now,
            run_id=None, capture_reason="new",
        )).inserted_primary_key[0])


def _requirements() -> list[RequirementItem]:
    return [
        RequirementItem(
            requiredness="required", requirement_text="5+ years Python",
            jd_locator={"span": [10, 25]}, disposition="met", rule_id="py_years",
            support=[
                SupportItem(profile_locator={"section": "experience", "idx": 0},
                            evidence_quote="8 years Python", support_kind="explicit"),
                SupportItem(profile_locator={"section": "skills"},
                            evidence_quote="Python (expert)", support_kind="corroborating"),
            ],
        ),
        RequirementItem(
            requiredness="required", requirement_text="US work authorization",
            jd_locator={"span": [40, 60]}, disposition="unknown",
        ),
    ]


def _kw(version_id: int, **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = dict(
        posting_version_id=version_id, profile_hash="pf1",
        profile_snapshot={"skills": ["python"]}, rules_hash="rl1",
        rules_snapshot={"min_years": 5}, input_fingerprint="fp-A",
        engine_kind="deterministic", engine_version="1", verdict="uncertain",
        score=0.5, requirements=_requirements(),
    )
    base.update(over)
    return base


def test_record_and_read_back_with_linked_evidence(engine, version_id):
    with engine.begin() as conn:
        eval_id = record_evaluation(conn, **_kw(version_id))
    with engine.connect() as conn:
        evals = get_evaluations(conn, version_id)
        reqs = get_requirements(conn, eval_id)
        support0 = get_support(conn, reqs[0].id)
    assert len(evals) == 1 and evals[0].verdict == "uncertain"
    assert [r.disposition for r in reqs] == ["met", "unknown"]
    assert reqs[0].jd_locator_json == {"span": [10, 25]}
    assert len(support0) == 2                     # N support items per requirement
    assert support0[0].evidence_quote == "8 years Python"


def test_deterministic_is_idempotent(engine, version_id):
    with engine.begin() as conn:
        first = record_evaluation(conn, **_kw(version_id))
    with engine.begin() as conn:
        second = record_evaluation(conn, **_kw(version_id))     # identical inputs
    assert first == second
    with engine.connect() as conn:
        assert len(get_evaluations(conn, version_id)) == 1      # no duplicate audit row


def test_llm_reruns_are_recorded_not_suppressed(engine, version_id):
    with engine.begin() as conn:
        a = record_evaluation(conn, **_kw(version_id, engine_kind="llm", provider="ollama",
                                          model="llama3", verdict="eligible"))
    with engine.begin() as conn:
        b = record_evaluation(conn, **_kw(version_id, engine_kind="llm", provider="ollama",
                                          model="llama3", verdict="ineligible"))
    assert a != b                                                # nondeterministic reruns kept
    with engine.connect() as conn:
        assert len(get_evaluations(conn, version_id)) == 2


def test_evaluation_is_immutable(engine, version_id):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    with engine.begin() as conn:
        record_evaluation(conn, **_kw(version_id))
    with engine.begin() as conn, pytest.raises(IntegrityError):
        conn.execute(text("UPDATE eligibility_evaluations SET verdict='eligible' WHERE id=1"))
