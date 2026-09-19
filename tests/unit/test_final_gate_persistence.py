"""TDD for the final-gate persistence lane: keystone-span downgrade, a clean
provenanced ineligible write, and the identity-scoped read-back via
current_gate_verdicts. See .superpowers/sdd/plan-p5-final-gate/task-1-brief.md."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import Connection, Engine, create_engine, insert, select

from boardwatch.core.clock import utcnow
from boardwatch.eligibility import final_gate
from boardwatch.eligibility.catalog import RulesCatalog, load_rules
from boardwatch.eligibility.facts import Facts, Policy
from boardwatch.eligibility.hashing import build_identity
from boardwatch.eligibility.oracle import OracleVerdict
from boardwatch.eligibility.read import current_gate_verdicts
from boardwatch.eligibility.resolve import declared_fields
from boardwatch.store.db import ensure_schema
from boardwatch.store.tables import (
    companies,
    eligibility_evaluations,
    jobs,
    posting_versions,
    postings,
)


def _catalog(tmp_path: Path) -> RulesCatalog:
    # load_rules(config_dir) falls back to the bundled catalog when config_dir/rules.yaml
    # doesn't exist — matches the pattern in tests/unit/test_eligibility_engine.py and
    # tests/pipeline/test_llm_lane.py (load_rules(tmp_path / "no-such-cfg-dir")).
    return load_rules(tmp_path / "no-such-cfg-dir")


def seed_posting_version(conn: Connection, *, body_text: str, slug: str = "acme-gate") -> int:
    """Minimal insert of a company/job/posting/posting_version row, mirroring the helper
    inlined in tests/unit/test_eligibility_engine.py and tests/pipeline/test_llm_lane.py.
    No dedicated tests/helpers/eligibility module exists to import instead."""
    now = utcnow()
    company_id = int(conn.execute(insert(companies).values(
        name="Acme", provider="greenhouse", slug=slug, source="user", watched=True,
    )).inserted_primary_key[0])
    job_id = int(conn.execute(insert(jobs).values(created_at=now)).inserted_primary_key[0])
    posting_id = int(conn.execute(insert(postings).values(
        company_id=company_id, job_id=job_id, provider_posting_id=f"p-{slug}",
        title="Eng", normalized_title="eng", first_seen_at=now, last_seen_at=now,
        status="open", consecutive_missing=0, content_hash=f"h-{slug}", body_text=body_text,
    )).inserted_primary_key[0])
    return int(conn.execute(insert(posting_versions).values(
        posting_id=posting_id, content_hash=f"h-{slug}", body_text=body_text,
        captured_at=now, run_id=None, capture_reason="new",
    )).inserted_primary_key[0])


def test_ineligible_without_resolvable_span_downgrades_to_uncertain(tmp_path: Path) -> None:
    engine: Engine = create_engine(f"sqlite:///{tmp_path / 't.db'}")
    ensure_schema(engine)
    catalog = _catalog(tmp_path)
    # Evidence that resolves provenance (normalized substring) but whose RAW form is NOT a
    # literal substring of jd_text, so span_of returns None and accept yields ineligible with
    # spans=().
    jd = "We require U.S.-based work authorization for this role and cannot sponsor."
    evidence = "U.S.–based work authorization"  # unicode en-dash normalizes to '-'
    v = OracleVerdict(label="1", decision="ineligible", reason="work_auth",
                       evidence=evidence, confidence="high")
    with engine.begin() as conn:
        pv_id = seed_posting_version(conn, body_text=jd)
        eval_id = final_gate.record_gate_verdict(
            conn, posting_version_id=pv_id, jd_text=jd,
            facts=Facts(), policy=Policy(families={}), catalog=catalog, verdict=v,
        )
    # The verdict persisted must be 'uncertain' (fail-open), never a span-less 'ineligible'.
    with engine.connect() as conn:
        row = conn.execute(select(eligibility_evaluations.c.verdict)
                            .where(eligibility_evaluations.c.id == eval_id)).one()
    assert row.verdict == "uncertain"


def test_high_confidence_provenanced_ineligible_is_written_with_span(tmp_path: Path) -> None:
    engine: Engine = create_engine(f"sqlite:///{tmp_path / 't.db'}")
    ensure_schema(engine)
    catalog = _catalog(tmp_path)
    jd = "This position requires an active Top Secret security clearance."
    evidence = "requires an active Top Secret security clearance"  # raw literal substring
    v = OracleVerdict(label="1", decision="ineligible", reason="clearance",
                       evidence=evidence, confidence="high")
    with engine.begin() as conn:
        pv_id = seed_posting_version(conn, body_text=jd)
        final_gate.record_gate_verdict(conn, posting_version_id=pv_id, jd_text=jd,
            facts=Facts(), policy=Policy(families={}), catalog=catalog, verdict=v)
    # Read it back via current_gate_verdicts under the SAME (profile_hash, rules_hash) the
    # deterministic run computes — proving the identity-join lands (deepseek BLOCKER-1).
    ident = build_identity(posting_version_id=0, facts=Facts(), policy=Policy(families={}),
                            catalog=catalog, declared_fields=declared_fields())
    with engine.connect() as conn:
        got = current_gate_verdicts(conn, [pv_id], ident.profile_hash, ident.rules_hash)
    # got maps posting_id -> verdict; resolve pv_id -> posting_id in the helper or assert by value
    assert "ineligible" in got.values()


def test_a_gate_row_carries_the_facts_key_the_judge_was_sent(tmp_path: Path) -> None:
    """T99. `raw_output.facts_key` digests `facts_payload(facts)` — the exact object
    `gate_handshake.build_gate_request` puts in every item — so the freshness read can see a
    fact the row identity drops. Under `work_auth: ignore` the identity is byte-identical for
    two different statuses; the key is not, and that difference is the whole fix."""
    engine: Engine = create_engine(f"sqlite:///{tmp_path / 't.db'}")
    ensure_schema(engine)
    catalog = _catalog(tmp_path)
    jd = "We are hiring a backend engineer for our Python services."
    policy = Policy(families={"work_auth": "ignore"})
    citizen = Facts.model_validate({"work_authorization": {"status": "citizen"}})
    sponsored = Facts.model_validate({"work_authorization": {"status": "needs_sponsorship"}})
    v = OracleVerdict(label="1", decision="eligible", reason=None, evidence="",
                       confidence="high")
    with engine.begin() as conn:
        pv_id = seed_posting_version(conn, body_text=jd)
        eval_id = final_gate.record_gate_verdict(
            conn, posting_version_id=pv_id, jd_text=jd, facts=citizen, policy=policy,
            catalog=catalog, verdict=v,
        )
    with engine.connect() as conn:
        raw = conn.execute(select(eligibility_evaluations.c.raw_output_json)
                            .where(eligibility_evaluations.c.id == eval_id)).scalar_one()
    assert raw["facts_key"] == final_gate.gate_facts_key(citizen)
    # The identity these two share is exactly what made the defect invisible.
    ident_a = build_identity(posting_version_id=pv_id, facts=citizen, policy=policy,
                             catalog=catalog, declared_fields=declared_fields())
    ident_b = build_identity(posting_version_id=pv_id, facts=sponsored, policy=policy,
                             catalog=catalog, declared_fields=declared_fields())
    assert ident_a.input_fingerprint == ident_b.input_fingerprint
    assert final_gate.gate_facts_key(citizen) != final_gate.gate_facts_key(sponsored)


def test_a_legacy_gate_row_with_no_facts_key_is_readable_but_never_fresh(
    tmp_path: Path,
) -> None:
    """T99, and the one-time consequence stated as a test. A row written before the key
    existed carries `raw_output = {"gate_verdict": ...}` and nothing else. It must stay
    READABLE through the display read — blanking the viewer would trade a write-side bug for
    a read-side one, the trade D-512 already refused — while never satisfying a freshness
    read that supplies a key, so every such lead is re-judged ONCE and comes back keyed."""
    from boardwatch.eligibility.oracle import PROMPT_VERSION
    from boardwatch.store.eligibility import record_evaluation

    engine: Engine = create_engine(f"sqlite:///{tmp_path / 't.db'}")
    ensure_schema(engine)
    catalog = _catalog(tmp_path)
    jd = "We are hiring a backend engineer for our Python services."
    policy = Policy(families={"work_auth": "ignore"})
    facts = Facts.model_validate({"work_authorization": {"status": "citizen"}})
    ident = build_identity(posting_version_id=0, facts=facts, policy=policy,
                           catalog=catalog, declared_fields=declared_fields())
    with engine.begin() as conn:
        pv_id = seed_posting_version(conn, body_text=jd)
        # Written through the store writer rather than by UPDATEing a fresh row: the four
        # eligibility tables carry BEFORE UPDATE RAISE(ABORT) triggers, and this is the exact
        # raw_output `record_gate_verdict` produced before T99.
        record_evaluation(
            conn, posting_version_id=pv_id,
            profile_hash=ident.profile_hash, profile_snapshot=ident.profile_snapshot,
            rules_hash=ident.rules_hash, rules_snapshot=ident.rules_snapshot,
            input_fingerprint=build_identity(
                posting_version_id=pv_id, facts=facts, policy=policy, catalog=catalog,
                declared_fields=declared_fields(),
            ).input_fingerprint,
            engine_kind="llm", engine_version=final_gate.gate_engine_version(),
            verdict="eligible", score=None, requirements=[],
            provider=None, model=None, prompt_version=PROMPT_VERSION,
            idempotency_key=None, run_id=None,
            raw_output={"gate_verdict": {"decision": "eligible"}},
        )

    with engine.connect() as conn:
        display = current_gate_verdicts(conn, [pv_id], ident.profile_hash, ident.rules_hash)
        fresh = current_gate_verdicts(
            conn, [pv_id], ident.profile_hash, ident.rules_hash,
            engine_version=final_gate.gate_engine_version(),
            facts_key=final_gate.gate_facts_key(facts),
        )
    assert "eligible" in display.values(), "the display read must be unchanged by T99"
    assert fresh == {}, "a row with no facts_key can never prove it was judged on these facts"
