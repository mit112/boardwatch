"""Persisted, evidence-linked eligibility AUDIT ledger (D30).

Append-only and immutable. Keyed by all inputs the verdict depended on (posting
version + profile + rules), so a profile change yields a fresh input and a fresh
verdict — not a stale cache hit. Deterministic runs are idempotent on
(input, engine_version); LLM reruns are recorded (deduped only on an explicit
idempotency_key). No evaluator lives here — that is P2. Functions take the caller's
open Connection.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import Connection, Row, insert, select, text
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from boardwatch.core.clock import utcnow
from boardwatch.store.tables import (
    eligibility_evaluations,
    eligibility_inputs,
    eligibility_requirements,
    eligibility_support,
)

EligibilityEngine = Literal["deterministic", "llm"]
EligibilityVerdict = Literal["eligible", "ineligible", "uncertain"]
Requiredness = Literal["required", "preferred", "bonus"]
EvidenceDisposition = Literal["met", "unmet", "unknown"]


@dataclass(frozen=True)
class SupportItem:
    profile_locator: dict[str, Any]
    evidence_quote: str
    support_kind: str


@dataclass(frozen=True)
class RequirementItem:
    requiredness: Requiredness
    requirement_text: str
    jd_locator: dict[str, Any]
    disposition: EvidenceDisposition
    rule_id: str | None = None
    rationale: str | None = None
    support: Sequence[SupportItem] = field(default_factory=tuple)


def _get_or_create_input(
    conn: Connection, *, posting_version_id: int, profile_hash: str,
    profile_snapshot: dict[str, Any], rules_hash: str, rules_snapshot: dict[str, Any],
    input_fingerprint: str,
) -> int:
    """Insert-then-reselect, never pre-select-then-insert.

    The pre-SELECT raced its own insert, so two concurrent `top` runs turned a unique index
    into an IntegrityError rather than an idempotent success. The FIRST snapshot still wins
    on conflict, which is safe now only because P2 DERIVES input_fingerprint from the
    snapshots: two different snapshots can no longer share a fingerprint.
    """
    conn.execute(
        sqlite_insert(eligibility_inputs)
        .values(
            posting_version_id=posting_version_id, profile_hash=profile_hash,
            profile_snapshot_json=profile_snapshot, rules_hash=rules_hash,
            rules_snapshot_json=rules_snapshot, input_fingerprint=input_fingerprint,
            created_at=utcnow(),
        )
        .on_conflict_do_nothing(index_elements=[eligibility_inputs.c.input_fingerprint])
    )
    return int(
        conn.execute(
            select(eligibility_inputs.c.id).where(
                eligibility_inputs.c.input_fingerprint == input_fingerprint
            )
        ).scalar_one()
    )


def record_evaluation(
    conn: Connection,
    *,
    posting_version_id: int,
    profile_hash: str,
    profile_snapshot: dict[str, Any],
    rules_hash: str,
    rules_snapshot: dict[str, Any],
    input_fingerprint: str,
    engine_kind: EligibilityEngine,
    engine_version: str,
    verdict: EligibilityVerdict,
    score: float | None,
    requirements: Sequence[RequirementItem],
    provider: str | None = None,
    model: str | None = None,
    prompt_version: str | None = None,
    idempotency_key: str | None = None,
    raw_output: dict[str, Any] | None = None,
    run_id: int | None = None,
) -> int:
    input_id = _get_or_create_input(
        conn, posting_version_id=posting_version_id, profile_hash=profile_hash,
        profile_snapshot=profile_snapshot, rules_hash=rules_hash,
        rules_snapshot=rules_snapshot, input_fingerprint=input_fingerprint,
    )
    if engine_kind == "deterministic":
        # Insert-then-reselect against the partial unique index uq_eligibility_deterministic,
        # (input_id, engine_version) where engine_kind = 'deterministic'. The pre-SELECT raced
        # its own insert; two concurrent runs turned the index into an IntegrityError instead
        # of an idempotent no-op. Do NOT read inserted_primary_key on the conflict path: it
        # never raises and returns a stale last_insert_rowid, so the rowcount guard decides.
        inserted = conn.execute(
            sqlite_insert(eligibility_evaluations)
            .values(
                input_id=input_id, engine_kind=engine_kind, engine_version=engine_version,
                provider=provider, model=model, prompt_version=prompt_version,
                idempotency_key=idempotency_key, verdict=verdict, score=score,
                raw_output_json=raw_output, created_at=utcnow(), run_id=run_id,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    eligibility_evaluations.c.input_id,
                    eligibility_evaluations.c.engine_version,
                ],
                index_where=text("engine_kind = 'deterministic'"),
            )
        )
        if inserted.rowcount == 0:
            # an equal row already exists, so this call is a no-op and its children exist.
            # The row keeps the run_id of the run that FIRST produced it, which is correct:
            # "cache hit" is its own funnel stage counted from this rowcount, never inferred
            # from run_id. Reattributing here would erase the distinction D-013 added the
            # run_id column to preserve.
            return int(
                conn.execute(
                    select(eligibility_evaluations.c.id).where(
                        eligibility_evaluations.c.input_id == input_id,
                        eligibility_evaluations.c.engine_kind == "deterministic",
                        eligibility_evaluations.c.engine_version == engine_version,
                    )
                ).scalar_one()
            )
        eval_id = int(inserted.inserted_primary_key[0])  # type: ignore[index]
    elif idempotency_key is not None:
        # Insert-then-reselect against the unique idempotency_key, the same fix the
        # deterministic branch and _get_or_create_input use: a pre-SELECT races its own insert,
        # so two concurrent writers with the same key turned the unique index into an
        # IntegrityError instead of an idempotent no-op. Do NOT read inserted_primary_key on
        # the conflict path; the rowcount guard decides.
        inserted = conn.execute(
            sqlite_insert(eligibility_evaluations)
            .values(
                input_id=input_id, engine_kind=engine_kind, engine_version=engine_version,
                provider=provider, model=model, prompt_version=prompt_version,
                idempotency_key=idempotency_key, verdict=verdict, score=score,
                raw_output_json=raw_output, created_at=utcnow(), run_id=run_id,
            )
            .on_conflict_do_nothing(
                index_elements=[eligibility_evaluations.c.idempotency_key]
            )
        )
        if inserted.rowcount == 0:
            return int(
                conn.execute(
                    select(eligibility_evaluations.c.id).where(
                        eligibility_evaluations.c.idempotency_key == idempotency_key
                    )
                ).scalar_one()
            )
        eval_id = int(inserted.inserted_primary_key[0])  # type: ignore[index]
    else:
        # No idempotency key: nothing to dedupe on (a UNIQUE index allows many NULLs).
        eval_id = int(
            conn.execute(
                insert(eligibility_evaluations).values(
                    input_id=input_id, engine_kind=engine_kind, engine_version=engine_version,
                    provider=provider, model=model, prompt_version=prompt_version,
                    idempotency_key=idempotency_key, verdict=verdict, score=score,
                    raw_output_json=raw_output, created_at=utcnow(), run_id=run_id,
                )
            ).inserted_primary_key[0]  # type: ignore[index]
        )
    for r_ordinal, req in enumerate(requirements):
        req_id = int(
            conn.execute(
                insert(eligibility_requirements).values(
                    evaluation_id=eval_id, ordinal=r_ordinal, rule_id=req.rule_id,
                    requiredness=req.requiredness, requirement_text=req.requirement_text,
                    jd_locator_json=req.jd_locator, disposition=req.disposition,
                    rationale=req.rationale,
                )
            ).inserted_primary_key[0]  # type: ignore[index]
        )
        for s_ordinal, sup in enumerate(req.support):
            conn.execute(
                insert(eligibility_support).values(
                    requirement_id=req_id, ordinal=s_ordinal,
                    profile_locator_json=sup.profile_locator,
                    evidence_quote=sup.evidence_quote, support_kind=sup.support_kind,
                )
            )
    return eval_id


def get_evaluations(conn: Connection, posting_version_id: int) -> list[Row[Any]]:
    return list(
        conn.execute(
            select(eligibility_evaluations)
            .join(eligibility_inputs, eligibility_evaluations.c.input_id == eligibility_inputs.c.id)
            .where(eligibility_inputs.c.posting_version_id == posting_version_id)
            .order_by(eligibility_evaluations.c.id)
        ).all()
    )


def get_requirements(conn: Connection, evaluation_id: int) -> list[Row[Any]]:
    return list(
        conn.execute(
            select(eligibility_requirements)
            .where(eligibility_requirements.c.evaluation_id == evaluation_id)
            .order_by(eligibility_requirements.c.ordinal)
        ).all()
    )


def get_support(conn: Connection, requirement_id: int) -> list[Row[Any]]:
    return list(
        conn.execute(
            select(eligibility_support)
            .where(eligibility_support.c.requirement_id == requirement_id)
            .order_by(eligibility_support.c.ordinal)
        ).all()
    )


def get_support_bulk(
    conn: Connection, requirement_ids: Sequence[int]
) -> dict[int, list[Row[Any]]]:
    """All support rows for many requirements in ONE query, grouped by requirement_id.

    The audit render has a requirement per detected rule; fetching support per requirement is
    an N+1 over a single posting's requirements. This keeps it to one round trip, ordered so
    each requirement's support stays in ordinal order.
    """
    if not requirement_ids:
        return {}
    rows = conn.execute(
        select(eligibility_support)
        .where(eligibility_support.c.requirement_id.in_(requirement_ids))
        .order_by(eligibility_support.c.requirement_id, eligibility_support.c.ordinal)
    ).all()
    grouped: dict[int, list[Row[Any]]] = {}
    for row in rows:
        grouped.setdefault(int(row.requirement_id), []).append(row)
    return grouped
