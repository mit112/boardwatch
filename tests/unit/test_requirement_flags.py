"""`eligibility.read.current_requirement_flags` — the DB read behind the delivery lane's two
requirement gates.

Seeds through `record_evaluation`, the production write path, so the flags are read back out of
rows written the way real ones are. This exists because the lane tests
(`test_review_gate.py`) pass the two booleans in LITERALLY: they pin what the router does with a
flag and say nothing about whether the flag is ever computed. A read that silently returned `{}`
would leave both new gates fully open and every one of those tests still green.

The two flags are deliberately asymmetric and each asymmetry is pinned below:

* experience takes `unmet` AND `unknown` — both mean "not confirmed satisfied", which is what the
  lane asks.
* the hard families take `unknown` ONLY. An `unmet` work_auth row makes the verdict `ineligible`,
  which has its own drain; counting it here would relabel that lead's hold.
* neither takes a non-`required` row. `engine.blocking` counts only `required` rows, so a
  `preferred` bar can never block, and holding a lead for one would be a hold on a requirement
  that cannot decide anything.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine, insert

from boardwatch.core.clock import utcnow
from boardwatch.eligibility.engine import engine_version
from boardwatch.eligibility.read import current_requirement_flags
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.eligibility import RequirementItem, record_evaluation
from boardwatch.store.tables import companies, jobs, posting_versions, postings

NOW = utcnow()
#: DERIVED, never pinned: `engine_version` is a digest that moves on any edit to a digested
#: module, and `current_evaluations` scopes to the CURRENT one. A literal here would select
#: nothing the day it drifts, and every assertion below would pass vacuously on an empty read.
PROFILE, RULES = "ph", "rh"


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path)
    ensure_schema(eng)
    return eng


def _version(conn, slug: str) -> tuple[int, int]:
    """(posting_id, posting_version_id) — the read keys BY POSTING, so both are needed."""
    cid = int(conn.execute(insert(companies).values(
        name="Acme", provider="greenhouse", slug=f"acme-{slug}", source="user", watched=True,
    )).inserted_primary_key[0])
    jid = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
    pid = int(conn.execute(insert(postings).values(
        company_id=cid, job_id=jid, provider_posting_id=slug, title="Eng",
        normalized_title="eng", first_seen_at=NOW, last_seen_at=NOW, status="open",
        consecutive_missing=0, content_hash=slug, body_text="b",
    )).inserted_primary_key[0])
    vid = int(conn.execute(insert(posting_versions).values(
        posting_id=pid, content_hash=slug, body_text="b", captured_at=NOW,
        run_id=None, capture_reason="new",
    )).inserted_primary_key[0])
    return pid, vid


def _seed(conn, slug: str, *rows: tuple[str, str, str]) -> tuple[int, int]:
    """Seed one evaluation from (rule_id, requiredness, disposition) triples."""
    pid, vid = _version(conn, slug)
    record_evaluation(
        conn, posting_version_id=vid, profile_hash=PROFILE,
        profile_snapshot={}, rules_hash=RULES, rules_snapshot={},
        input_fingerprint=f"fp-{slug}", engine_kind="deterministic", engine_version=engine_version(),
        verdict="uncertain", score=None,
        requirements=[
            RequirementItem(
                requiredness=requiredness, requirement_text="text", jd_locator={"span": [0, 1]},
                disposition=disposition, rule_id=rule_id, support=[],
            )
            for rule_id, requiredness, disposition in rows
        ],
    )
    return pid, vid


def _flags(engine: Engine, vids: list[int], *, profile: str = PROFILE, rules: str = RULES):
    with engine.connect() as conn:
        return current_requirement_flags(conn, vids, profile, rules)


def test_an_unconfirmed_required_experience_bar_sets_only_the_experience_flag(
    engine: Engine,
) -> None:
    with engine.begin() as conn:
        pid, vid = _seed(conn, "a", ("experience_years:total_years_minimum", "required", "unmet"))
    flags = _flags(engine, [vid])
    assert flags[pid].experience_unconfirmed is True
    assert flags[pid].eligibility_unconfirmed is False


def test_an_abstained_required_hard_rule_sets_only_the_eligibility_flag(engine: Engine) -> None:
    with engine.begin() as conn:
        pid, vid = _seed(conn, "b", ("work_auth:us_authorization_required", "required", "unknown"))
    flags = _flags(engine, [vid])
    assert flags[pid].eligibility_unconfirmed is True
    assert flags[pid].experience_unconfirmed is False


def test_clearance_is_a_hard_family_too(engine: Engine) -> None:
    with engine.begin() as conn:
        pid, vid = _seed(conn, "c", ("clearance:clearance_required", "required", "unknown"))
    assert _flags(engine, [vid])[pid].eligibility_unconfirmed is True


def test_an_experience_bar_ABSTAINING_also_counts(engine: Engine) -> None:
    """`unknown` is the commonest experience outcome on a real body (`scoped_years_minimum`)."""
    with engine.begin() as conn:
        pid, vid = _seed(conn, "d", ("experience_years:scoped_years_minimum", "required", "unknown"))
    assert _flags(engine, [vid])[pid].experience_unconfirmed is True


def test_an_UNMET_hard_rule_does_NOT_set_the_eligibility_flag(engine: Engine) -> None:
    """It makes the verdict `ineligible`, which has its own drain. Counting it here would
    relabel that lead's hold as an abstain — the exact fold this catalog refuses."""
    with engine.begin() as conn:
        pid, vid = _seed(conn, "e", ("work_auth:us_authorization_required", "required", "unmet"))
    flags = _flags(engine, [vid])
    assert flags[pid].eligibility_unconfirmed is False


def test_a_NON_required_row_sets_NOTHING(engine: Engine) -> None:
    """`engine.blocking` counts only `required` rows, so a `preferred`/`bonus` bar can never make
    a verdict `ineligible` or `uncertain`. Holding a lead for one would be a hold on a
    requirement that cannot decide anything — 2,790 such rows on the live store when this was
    written, `clearance_preferred` the bulk of them."""
    with engine.begin() as conn:
        pid, vid = _seed(
            conn, "f",
            ("experience_years:total_years_minimum", "preferred", "unmet"),
            ("clearance:clearance_preferred", "preferred", "unknown"),
            ("work_auth:us_authorization_required", "bonus", "unknown"),
        )
    assert pid not in _flags(engine, [vid])


def test_a_fully_met_evaluation_sets_nothing(engine: Engine) -> None:
    with engine.begin() as conn:
        pid, vid = _seed(conn, "g", ("work_auth:us_authorization_required", "required", "met"))
    assert pid not in _flags(engine, [vid])


def test_flags_are_keyed_to_the_RIGHT_posting(engine: Engine) -> None:
    """Two postings with DIFFERENT flags, read in one call. A read that mixed up the
    evaluation -> version -> posting mapping would pass every single-posting test above and
    hold the wrong lead here."""
    with engine.begin() as conn:
        exp_pid, exp_vid = _seed(
            conn, "h", ("experience_years:total_years_minimum", "required", "unmet")
        )
        auth_pid, auth_vid = _seed(
            conn, "i", ("work_auth:us_authorization_required", "required", "unknown")
        )
    flags = _flags(engine, [exp_vid, auth_vid])
    assert flags[exp_pid].experience_unconfirmed is True
    assert flags[exp_pid].eligibility_unconfirmed is False
    assert flags[auth_pid].eligibility_unconfirmed is True
    assert flags[auth_pid].experience_unconfirmed is False


def test_a_DIFFERENT_identity_reads_no_flags(engine: Engine) -> None:
    """Identity scoping is what keeps the summary and the verdict beside it on one evaluation.

    It is also the silent failure mode: a mismatched hash yields `{}`, which reads as "nothing
    unconfirmed" and opens BOTH new gates for every lead at once. Pinned in both directions so
    the scoping cannot be dropped without a red test.
    """
    with engine.begin() as conn:
        pid, vid = _seed(conn, "j", ("work_auth:us_authorization_required", "required", "unknown"))
    assert _flags(engine, [vid])[pid].eligibility_unconfirmed is True
    assert _flags(engine, [vid], profile="other") == {}
    assert _flags(engine, [vid], rules="other") == {}


def test_no_versions_and_no_identity_are_both_empty(engine: Engine) -> None:
    with engine.begin() as conn:
        _seed(conn, "k", ("work_auth:us_authorization_required", "required", "unknown"))
    assert _flags(engine, []) == {}
    with engine.connect() as conn:
        assert current_requirement_flags(conn, [1], None, RULES) == {}
        assert current_requirement_flags(conn, [1], PROFILE, None) == {}
