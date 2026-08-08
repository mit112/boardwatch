"""TDD for Task 3 of the P5 final-gate plan: rank_open_postings hides a posting when
EITHER the deterministic verdict OR the final-gate verdict is `ineligible`.

See .superpowers/sdd/plan-p5-final-gate/task-3-brief.md. Mirrors test_top_accounting.py's
seeding pattern and test_final_gate_persistence.py's record_gate_verdict usage. `Facts()` /
`Policy(families={})` are what a profile saved via `save_profile` alone (no
`eligibility facts set` / `eligibility policy set`) parses to — eligibility_facts_json and
eligibility_policy_json are NULL columns, and parse_facts(None)/parse_policy(None) both fail
closed to their bare defaults — so record_gate_verdict's identity here lands on the SAME
(profile_hash, rules_hash) that rank_open_postings' own run_eligibility computes for the
seeded profile. Neither hash depends on posting_version_id (hashing.py:76-108), so a gate
row can be written against any posting_version_id under that identity and still be read back
by current_gate_verdicts for the postings actually ranked.
"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from sqlalchemy import Engine, insert

from boardwatch.cli.top_cmd import RankedResults, rank_open_postings
from boardwatch.core.clock import utcnow
from boardwatch.core.settings import Settings
from boardwatch.eligibility import final_gate
from boardwatch.eligibility.catalog import RulesCatalog, load_rules
from boardwatch.eligibility.facts import Facts, Policy
from boardwatch.eligibility.oracle import OracleVerdict
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import current_posting_versions, save_profile
from boardwatch.store.tables import companies, jobs, posting_versions, postings

NOW = utcnow()

# A plain body with no catalog keyword in it, so the deterministic engine never flags it —
# every fixture posting here starts out NOT hidden by the deterministic lane.
SAFE_BODY = "We are hiring a backend engineer to work on our platform."

# Literal substring of ITS OWN jd_text passed to record_gate_verdict below (not of
# SAFE_BODY): resolves provenance and yields a span, so accept_oracle_verdict persists
# `ineligible` rather than downgrading to `uncertain` (test_final_gate_persistence.py's
# pattern). record_gate_verdict's jd_text is only the keystone-span source; it need not
# equal the posting's stored body_text for current_gate_verdicts' read-back, which keys
# purely on posting_version_id/profile_hash/rules_hash.
CLEARANCE_JD = "This position requires an active Top Secret security clearance."
CLEARANCE_EVIDENCE = "requires an active Top Secret security clearance"


def _catalog(tmp_path: Path) -> RulesCatalog:
    return load_rules(tmp_path / "no-such-cfg-dir")


def _settings(data_dir: Path) -> Settings:
    return Settings(data_dir=data_dir, config_dir=data_dir)


def _seed(data_dir: Path, titles: list[str]) -> Engine:
    """One company, one open posting per title with SAFE_BODY, distinct posted_at so
    ranking is total. No facts/policy set — see the module docstring for why that makes
    the identity match record_gate_verdict's Facts()/Policy(families={})."""
    engine = get_engine(data_dir)
    ensure_schema(engine)
    with engine.begin() as conn:
        save_profile(
            conn, text="Backend engineer.", target_titles=[], exclude_titles=[],
            locations=[], remote_only=False, skills=[], taxonomy_version="t",
            resume_max_pages=1,
        )
        company_id = int(conn.execute(insert(companies).values(
            name="Acme", provider="greenhouse", slug="acme-gate-filter", source="user",
            watched=True,
        )).inserted_primary_key[0])
        for offset, title in enumerate(titles):
            job_id = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
            posting_id = int(conn.execute(insert(postings).values(
                company_id=company_id, job_id=job_id, provider_posting_id=f"pp-{offset}",
                title=title, normalized_title=title.casefold(),
                locations_json=["Remote"], remote_policy="remote",
                posted_at=NOW - timedelta(days=offset), first_seen_at=NOW, last_seen_at=NOW,
                status="open", consecutive_missing=0, content_hash=f"hh-{offset}",
                body_text=SAFE_BODY,
            )).inserted_primary_key[0])
            conn.execute(insert(posting_versions).values(
                posting_id=posting_id, content_hash=f"hh-{offset}", body_text=SAFE_BODY,
                captured_at=NOW, capture_reason="new",
            ))
    return engine


def _pv_id(engine: Engine, posting_id: int) -> int:
    with engine.connect() as conn:
        versions = current_posting_versions(conn, [posting_id])
    return versions[posting_id].posting_version_id


def _write_gate_verdict(
    engine: Engine, tmp_path: Path, *, posting_version_id: int, verdict: OracleVerdict,
) -> None:
    catalog = _catalog(tmp_path)
    with engine.begin() as conn:
        final_gate.record_gate_verdict(
            conn, posting_version_id=posting_version_id, jd_text=CLEARANCE_JD,
            facts=Facts(), policy=Policy(families={}), catalog=catalog, verdict=verdict,
        )


def test_non_ineligible_gate_rows_do_not_change_ranking(tmp_path: Path) -> None:
    """A gate row that is `uncertain` (not `ineligible`) must be purely additive: every
    field of RankedResults is identical before and after it is written (deepseek MAJOR-6:
    reading gate verdicts must not itself regress the deterministic-only ranking)."""
    engine = _seed(tmp_path, ["Backend Engineer", "Platform Engineer"])
    settings = _settings(tmp_path)
    before: RankedResults = rank_open_postings(engine, settings, limit=10, now=NOW)

    pv_id = _pv_id(engine, before.visible[0].posting_id)
    _write_gate_verdict(
        engine, tmp_path, posting_version_id=pv_id,
        verdict=OracleVerdict(
            label=str(before.visible[0].posting_id), decision="uncertain",
            reason=None, evidence="", confidence="low",
        ),
    )

    after: RankedResults = rank_open_postings(engine, settings, limit=10, now=NOW)
    assert after == before


def test_gate_ineligible_hides_a_posting_the_deterministic_engine_did_not(tmp_path: Path) -> None:
    """The deterministic lane never flags SAFE_BODY, so posting 1 is visible today. A
    final-gate `ineligible` row for it must hide it too, incrementing the SAME
    `hidden_ineligible` counter the deterministic lane uses, and `--include-ineligible`
    must reveal it again."""
    engine = _seed(tmp_path, ["Backend Engineer", "Platform Engineer"])
    settings = _settings(tmp_path)
    before = rank_open_postings(engine, settings, limit=10, now=NOW)
    assert before.hidden_ineligible == 0
    hidden_posting_id = before.visible[0].posting_id
    other_posting_id = before.visible[1].posting_id

    pv_id = _pv_id(engine, hidden_posting_id)
    _write_gate_verdict(
        engine, tmp_path, posting_version_id=pv_id,
        verdict=OracleVerdict(
            label=str(hidden_posting_id), decision="ineligible", reason="clearance",
            evidence=CLEARANCE_EVIDENCE, confidence="high",
        ),
    )

    after = rank_open_postings(engine, settings, limit=10, now=NOW)
    assert [p.posting_id for p in after.visible] == [other_posting_id]
    assert after.hidden_ineligible == 1
    assert after.considered == before.considered == 2

    revealed = rank_open_postings(engine, settings, limit=10, now=NOW, include_ineligible=True)
    assert hidden_posting_id in {p.posting_id for p in revealed.visible}
