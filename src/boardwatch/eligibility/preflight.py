"""Eligibility preflight: evaluate every OPEN posting's current version that has no
evaluation at the current engine version yet, in ONE set-oriented pass.

This mirrors extract/preflight.py: a single anti-join finds the pending work (never an
N+1 existence probe per posting), then the writes run in batches with a commit per batch
so a crash between batches leaves a consistent, resumable state. A NULL profile row is a
no-op rather than an error, because `top` calls preflight before its own NoProfileError
check, so preflight cannot be the thing that raises there.

No module-level string collection lives here (R9 scopes this module): the engine kind and
status literals sit inside the query builders, and the digested-module names come from the
engine helper, not a constant.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from rich.console import Console
from sqlalchemy import Connection, Engine, select, tuple_

from boardwatch.core.settings import Settings
from boardwatch.eligibility.catalog import RulesCatalog, load_rules
from boardwatch.eligibility.engine import ENGINE_KIND, engine_version, evaluate, write_evaluation
from boardwatch.eligibility.facts import Facts, Policy, parse_facts, parse_policy
from boardwatch.eligibility.hashing import build_identity
from boardwatch.eligibility.resolve import declared_fields
from boardwatch.store.queries import get_profile
from boardwatch.store.tables import (
    eligibility_evaluations,
    eligibility_inputs,
    posting_versions,
    postings,
)

BATCH_SIZE = 200


@dataclass
class EligibilityStats:
    evaluated: int = 0
    skipped_no_profile: bool = False
    # The identity this run computed, so a caller (top) can read verdicts for the same profile
    # without loading the catalog a second time. None when there is no profile.
    profile_hash: str | None = None
    rules_hash: str | None = None


def _pending(engine: Engine, profile_hash: str, rules_hash: str) -> list[tuple[int, str]]:
    """Current versions of OPEN postings with no evaluation for the CURRENT input identity.

    ONE query, an anti-join, mirroring extract/preflight.py:63-81. The `newer` correlated
    EXISTS restricts to each posting's newest version exactly as current_posting_versions
    does; the `evaluated` correlated EXISTS excludes anything already done at this engine
    version FOR THIS profile+rules identity, so a rerun after a crash resumes rather than
    repeats, while a corrected fact or policy (a new profile_hash/rules_hash) makes every
    posting pending again and re-keys the ledger, which is the whole point of D-P2-14.
    """
    newest = posting_versions.alias("pv_newer")
    newer = (
        select(newest.c.id)
        .where(
            newest.c.posting_id == posting_versions.c.posting_id,
            tuple_(newest.c.captured_at, newest.c.id)
            > tuple_(posting_versions.c.captured_at, posting_versions.c.id),
        )
        .exists()
    )
    evaluated = (
        select(eligibility_evaluations.c.id)
        .join(
            eligibility_inputs,
            eligibility_evaluations.c.input_id == eligibility_inputs.c.id,
        )
        .where(
            eligibility_inputs.c.posting_version_id == posting_versions.c.id,
            eligibility_inputs.c.profile_hash == profile_hash,
            eligibility_inputs.c.rules_hash == rules_hash,
            eligibility_evaluations.c.engine_kind == ENGINE_KIND,
            eligibility_evaluations.c.engine_version == engine_version(),
        )
        .exists()
    )
    stmt = (
        select(posting_versions.c.id, posting_versions.c.body_text)
        .join(postings, posting_versions.c.posting_id == postings.c.id)
        .where(postings.c.status == "open", ~newer, ~evaluated)
        .order_by(posting_versions.c.id)
    )
    with engine.connect() as conn:
        return [(int(row.id), str(row.body_text)) for row in conn.execute(stmt).all()]


def _identity_hashes(
    facts: Facts,
    policy: Policy,
    catalog: RulesCatalog,
    fields: Mapping[str, tuple[str, ...]],
) -> tuple[str, str]:
    """(profile_hash, rules_hash) for a profile, policy and catalog, without a posting.

    Both hashes are posting-independent, so this one pair selects the current-input
    evaluations across every posting. The sentinel posting id feeds build_identity only to
    reuse its snapshot logic; the fingerprint it also produces is discarded here.
    """
    identity = build_identity(
        posting_version_id=0,
        facts=facts,
        policy=policy,
        catalog=catalog,
        declared_fields=fields,
    )
    return identity.profile_hash, identity.rules_hash


def current_identity(conn: Connection, settings: Settings) -> tuple[str, str] | None:
    """The live profile's (profile_hash, rules_hash), or None when there is no profile.

    The read paths (top's verdict flags, `eligibility summary`, the `show` audit) call this
    so they select the evaluation the CURRENT profile produced, not merely any evaluation at
    the current engine version. Without it a corrected fact leaves a stale verdict on screen.
    """
    profile_row = get_profile(conn)
    if profile_row is None:
        return None
    facts = parse_facts(profile_row.eligibility_facts_json)
    policy = parse_policy(profile_row.eligibility_policy_json)
    catalog = load_rules(settings.config_dir)
    return _identity_hashes(facts, policy, catalog, declared_fields())


def run_eligibility(
    engine: Engine, settings: Settings, console: Console | None = None
) -> EligibilityStats:
    console = console or Console()
    with engine.connect() as conn:
        profile_row = get_profile(conn)
    if profile_row is None:
        return EligibilityStats(evaluated=0, skipped_no_profile=True)

    # The identity of the current profile+rules is needed before the pending scan, because a
    # posting is pending unless it already has an evaluation FOR THIS identity (not merely at
    # this engine version). That is what makes a corrected fact re-evaluate. The catalog parse
    # this costs runs on every top invocation, but the pending scan itself stays one query.
    facts = parse_facts(profile_row.eligibility_facts_json)
    policy = parse_policy(profile_row.eligibility_policy_json)
    catalog = load_rules(settings.config_dir)
    fields = declared_fields()
    profile_hash, rules_hash = _identity_hashes(facts, policy, catalog, fields)

    pending = _pending(engine, profile_hash, rules_hash)
    stats = EligibilityStats(profile_hash=profile_hash, rules_hash=rules_hash)
    if not pending:
        return stats

    console.print(f"evaluating eligibility for {len(pending)} postings…")
    for chunk_start in range(0, len(pending), BATCH_SIZE):
        chunk = pending[chunk_start : chunk_start + BATCH_SIZE]
        with engine.begin() as conn:  # one commit per batch: resumable
            for posting_version_id, body_text in chunk:
                result = evaluate(body_text, facts, policy, catalog)
                identity = build_identity(
                    posting_version_id=posting_version_id,
                    facts=facts,
                    policy=policy,
                    catalog=catalog,
                    declared_fields=fields,
                )
                write_evaluation(
                    conn,
                    posting_version_id=posting_version_id,
                    identity=identity,
                    result=result,
                )
                stats.evaluated += 1
    return stats
