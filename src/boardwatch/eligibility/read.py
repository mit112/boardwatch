"""Public read paths into the eligibility ledger (A6).

current_verdicts replaces the private _current_verdicts that used to live in
cli/top_cmd.py. Unlike that helper it is NOT open-only: the caller supplies the
posting version ids it cares about (obtained from current_posting_versions), so a
closed posting's current version is eligible for a verdict lookup, which is what an
export of closed tracked postings needs.
"""

from __future__ import annotations

from sqlalchemy import Connection, func, select

from boardwatch.eligibility.engine import current_evaluations
from boardwatch.eligibility.final_gate import GATE_VERSION_PREFIX
from boardwatch.store.tables import eligibility_evaluations, eligibility_inputs, posting_versions


def current_verdicts(
    conn: Connection,
    posting_version_ids: list[int],
    profile_hash: str | None,
    rules_hash: str | None,
) -> dict[int, str | None]:
    """posting_id -> the CURRENT profile's verdict for its current version, or None.

    The caller controls the posting scope via posting_version_ids (the current
    versions from current_posting_versions), so this read is not restricted to open
    postings. Keyed on the identity the run already computed, so a corrected fact or
    policy is reflected the moment its re-evaluation lands, never a leftover verdict
    from an old profile. Returns {} when either hash is None, which is what the
    preflight reports for a store with no profile.
    """
    if profile_hash is None or rules_hash is None:
        return {}
    if not posting_version_ids:
        return {}
    evals = current_evaluations(conn, posting_version_ids, profile_hash, rules_hash)
    rows = conn.execute(
        select(posting_versions.c.id, posting_versions.c.posting_id).where(
            posting_versions.c.id.in_(posting_version_ids)
        )
    ).all()
    version_to_posting = {int(row.id): int(row.posting_id) for row in rows}
    return {
        version_to_posting[vid]: (evals.get(vid) or (None, None))[1]
        for vid in posting_version_ids
        if vid in version_to_posting
    }


def current_gate_verdicts(
    conn: Connection, posting_version_ids: list[int],
    profile_hash: str | None, rules_hash: str | None,
) -> dict[int, str | None]:
    """posting_id -> the LATEST final-gate verdict for its current version under this identity.

    Scoped to engine_kind='llm' AND engine_version LIKE 'final_gate:%' — so it never picks up the
    advisory extract_llm lane ('llm:%'), and the deterministic read (engine_kind='deterministic')
    never picks up either. The gate lane has no unique index; max(id) per posting_version means the
    most recent apply wins (a re-judge overrides), which is the intended semantics.
    """
    if profile_hash is None or rules_hash is None or not posting_version_ids:
        return {}
    latest = (
        select(eligibility_inputs.c.posting_version_id,
               func.max(eligibility_evaluations.c.id).label("eid"))
        .join(eligibility_inputs, eligibility_evaluations.c.input_id == eligibility_inputs.c.id)
        .where(
            eligibility_inputs.c.posting_version_id.in_(posting_version_ids),
            eligibility_inputs.c.profile_hash == profile_hash,
            eligibility_inputs.c.rules_hash == rules_hash,
            eligibility_evaluations.c.engine_kind == "llm",
            eligibility_evaluations.c.engine_version.like(f"{GATE_VERSION_PREFIX}%"),
        )
        .group_by(eligibility_inputs.c.posting_version_id)
        .subquery()
    )
    rows = conn.execute(
        select(eligibility_inputs.c.posting_version_id, eligibility_evaluations.c.verdict)
        .join(latest, eligibility_evaluations.c.id == latest.c.eid)
        .join(eligibility_inputs, eligibility_evaluations.c.input_id == eligibility_inputs.c.id)
    ).all()
    version_rows = conn.execute(
        select(posting_versions.c.id, posting_versions.c.posting_id)
        .where(posting_versions.c.id.in_(posting_version_ids))
    ).all()
    v2p = {int(r.id): int(r.posting_id) for r in version_rows}
    return {v2p[int(r.posting_version_id)]: str(r.verdict)
            for r in rows if int(r.posting_version_id) in v2p}
