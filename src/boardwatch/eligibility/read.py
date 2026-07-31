"""Public read paths into the eligibility ledger (A6).

current_verdicts replaces the private _current_verdicts that used to live in
cli/top_cmd.py. Unlike that helper it is NOT open-only: the caller supplies the
posting version ids it cares about (obtained from current_posting_versions), so a
closed posting's current version is eligible for a verdict lookup, which is what an
export of closed tracked postings needs.
"""

from __future__ import annotations

from sqlalchemy import Connection, select

from boardwatch.eligibility.engine import current_evaluations
from boardwatch.store.tables import posting_versions


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
