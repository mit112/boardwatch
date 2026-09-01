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

import os
from collections.abc import Mapping
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from sqlalchemy import Connection, Engine, select, tuple_

from boardwatch.core.settings import Settings
from boardwatch.eligibility.catalog import RulesCatalog, load_rules
from boardwatch.eligibility.engine import (
    ENGINE_KIND,
    EvaluationResult,
    engine_version,
    evaluate,
    write_evaluation,
)
from boardwatch.eligibility.facts import Facts, Policy, parse_facts, parse_policy
from boardwatch.eligibility.hashing import build_identity
from boardwatch.eligibility.resolve import declared_fields
from boardwatch.store.queries import ensure_run, finish_run, get_profile
from boardwatch.store.tables import (
    eligibility_evaluations,
    eligibility_inputs,
    posting_versions,
    postings,
)

BATCH_SIZE = 200
# Below this many pending postings the pool costs more than it saves: a spawn-mode child pays
# an interpreter start plus a catalog parse before it evaluates anything. Chosen above every
# fixture in the suite so the tests keep taking the serial path unless they ask for the other
# one, and a caller that wants the parallel path in a small run passes its own.
PARALLEL_THRESHOLD = 500


@dataclass
class EligibilityStats:
    evaluated: int = 0
    skipped_no_profile: bool = False
    # The identity this run computed, so a caller (top) can read verdicts for the same profile
    # without loading the catalog a second time. None when there is no profile.
    profile_hash: str | None = None
    rules_hash: str | None = None
    # The run these evaluations were attributed to. None when nothing was evaluated, because
    # a stage that judged nothing mints no run.
    run_id: int | None = None


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


# Rebuilt per child process by `_init_worker`, never pickled: a RulesCatalog carries every
# compiled pattern, and shipping one per posting would cost more than the evaluation it feeds.
_WORKER_INPUTS: tuple[Facts, Policy, RulesCatalog] | None = None


def _init_worker(
    config_dir: Path,
    facts_raw: object,
    policy_raw: object,
    profile_hash: str,
    rules_hash: str,
    version: str,
) -> None:
    """Rebuild the evaluation inputs inside a child, and REFUSE a different identity.

    Only picklable values cross the boundary: the config dir and the profile's two stored
    JSON payloads, parsed here with the same two parsers the parent used.

    The identity check is not defensive. `rules.yaml` is read from disk at child start, and
    the digested modules are read from disk by `engine_version()`, so a child can load a
    different catalog or a different engine than the parent hashed — an editable install
    whose branch moves mid-run is the live way that happens. The parent attributes every row
    to the identity IT computed, so the mismatch would persist rows under an identity nothing
    evaluated under, and the four eligibility tables carry BEFORE UPDATE/DELETE RAISE(ABORT)
    triggers: such a row can only ever be superseded, never corrected. Raising here breaks
    the pool and aborts the stage, which is the recoverable direction. There is deliberately
    no serial fallback: it would turn this into a run that looks successful.
    """
    global _WORKER_INPUTS
    facts = parse_facts(facts_raw)
    policy = parse_policy(policy_raw)
    catalog = load_rules(config_dir)
    got_profile, got_rules = _identity_hashes(facts, policy, catalog, declared_fields())
    got = (got_profile, got_rules, engine_version())
    if got != (profile_hash, rules_hash, version):
        raise RuntimeError(
            "eligibility worker loaded a different input identity than the parent hashed: "
            f"{got} != {(profile_hash, rules_hash, version)}"
        )
    _WORKER_INPUTS = (facts, policy, catalog)


def _evaluate_in_worker(body_text: str) -> EvaluationResult:
    """One posting's verdict, in a child. Returns the RESULT only.

    Not the InputIdentity: it carries `rules_snapshot` and `profile_snapshot`, so returning
    it would pickle a catalog snapshot back per posting. `build_identity` stays in the parent,
    where it is cheap — the two snapshots are posting-independent and only the fingerprint
    digest changes per row.
    """
    if _WORKER_INPUTS is None:  # the initializer runs before any task; narrowing for mypy
        raise RuntimeError("eligibility worker ran before its initializer")
    facts, policy, catalog = _WORKER_INPUTS
    return evaluate(body_text, facts, policy, catalog)


def run_eligibility(
    engine: Engine,
    settings: Settings,
    console: Console | None = None,
    *,
    run_id: int | None = None,
    workers: int | None = None,
    parallel_threshold: int = PARALLEL_THRESHOLD,
) -> EligibilityStats:
    """Judge every posting pending under the current profile+rules identity.

    `run_id` attributes the evaluations to the pipeline run that produced them. When the
    caller has none — `top`, `export`, `stats` and `eligibility run` all trigger this as a
    preflight side-effect — one is minted, but ONLY once there is pending work. A preflight
    that finds nothing to judge writes no run row, so a `runs` table stays a ledger of runs
    that did something rather than a log of every `top` invocation.

    `evaluate` is ~94% of this stage and is pure CPU inside `re`, which holds the GIL, so a
    big backlog is spread over PROCESSES. `workers` and `parallel_threshold` are parameters
    rather than Settings fields: neither is a user preference, and a Settings field would add
    four registration sites for a number only this function reads.
    """
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
    owns_run = run_id is None
    run_id = ensure_run(engine, run_id)
    stats.run_id = run_id
    # ONE pool for the whole stage, outside the chunk loop: a pool per 200-row chunk would
    # start `workers` interpreters and reparse the catalog in each of them ~570 times over a
    # 114k backlog, which costs more than the evaluation it parallelises.
    count = (os.cpu_count() or 1) if workers is None else workers
    pool = (
        ProcessPoolExecutor(
            max_workers=min(count, len(pending)),
            initializer=_init_worker,
            initargs=(
                settings.config_dir,
                profile_row.eligibility_facts_json,
                profile_row.eligibility_policy_json,
                profile_hash,
                rules_hash,
                engine_version(),
            ),
        )
        if count > 1 and len(pending) >= parallel_threshold
        else None
    )
    try:
        for chunk_start in range(0, len(pending), BATCH_SIZE):
            chunk = pending[chunk_start : chunk_start + BATCH_SIZE]
            bodies = [body_text for _id, body_text in chunk]
            # `map`, not `submit`+`as_completed`: the writes below must stay in the chunk's
            # own order, and `map` is the ordered one.
            results = (
                list(pool.map(_evaluate_in_worker, bodies))
                if pool is not None
                else [evaluate(body_text, facts, policy, catalog) for body_text in bodies]
            )
            # The write stays SERIAL and in the parent: one commit per batch, so a crash
            # between batches leaves a consistent, resumable state exactly as before.
            with engine.begin() as conn:
                for (posting_version_id, _body), result in zip(chunk, results, strict=True):
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
                        run_id=run_id,
                    )
                    stats.evaluated += 1
    finally:
        if pool is not None:
            pool.shutdown()
    if owns_run:
        # A run minted here spans only this stage, so it is complete the moment the last
        # batch commits. A run passed in belongs to the pipeline, which finishes it.
        finish_run(engine, run_id)
    return stats
