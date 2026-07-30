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

from dataclasses import dataclass

from rich.console import Console
from sqlalchemy import Engine, select, tuple_

from boardwatch.core.settings import Settings
from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.engine import ENGINE_KIND, engine_version, evaluate, write_evaluation
from boardwatch.eligibility.facts import parse_facts, parse_policy
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


def _pending(engine: Engine) -> list[tuple[int, str]]:
    """Current versions of OPEN postings with no current-engine deterministic evaluation.

    ONE query, an anti-join, mirroring extract/preflight.py:63-81. The `newer` correlated
    EXISTS restricts to each posting's newest version exactly as current_posting_versions
    does; the `evaluated` correlated EXISTS excludes anything already done at this engine
    version, so a rerun after a crash resumes rather than repeats.
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


def run_eligibility(
    engine: Engine, settings: Settings, console: Console | None = None
) -> EligibilityStats:
    console = console or Console()
    with engine.connect() as conn:
        profile_row = get_profile(conn)
    if profile_row is None:
        return EligibilityStats(evaluated=0, skipped_no_profile=True)

    # The pending scan comes first so the common no-op path (nothing to evaluate) never pays
    # the catalog parse and regex compile. This keeps run_eligibility cheap on the top path,
    # where it runs on every invocation.
    pending = _pending(engine)
    stats = EligibilityStats()
    if not pending:
        return stats

    facts = parse_facts(profile_row.eligibility_facts_json)
    policy = parse_policy(profile_row.eligibility_policy_json)
    catalog = load_rules(settings.config_dir)
    fields = declared_fields()
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
