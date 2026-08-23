"""The raw half of the per-rule abstain rate: observed dispositions, nothing else.

Deliberately does NOT know what the catalog declares. This returns exactly what the table
says and no more; reconciling it against the catalog enumeration — which is where a
never-fired rule becomes visible — is `reports/abstain.build_abstain_report`'s job. Keeping
the two apart is what stops the enumeration from being quietly re-derived from the data.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Connection, func, select

from boardwatch.store.param_chunks import id_chunks
from boardwatch.store.tables import eligibility_requirements


def count_requirement_dispositions(
    conn: Connection, evaluation_ids: Sequence[int]
) -> dict[tuple[str | None, str], int]:
    """Row counts keyed by (rule_id, disposition) for the given evaluations.

    rule_id is nullable in the schema, so a None key is a legitimate result and is passed
    through rather than dropped — the report surfaces it as its own bucket.
    """
    if not evaluation_ids:
        return {}
    # Chunked past SQLite's bound-parameter cap: the funnel passes one id per open posting
    # with a current evaluation (33,429 today) and the corpus only grows. See
    # store.param_chunks.
    #
    # The counts are ADDED, not merged. Unlike the ledger reads, the GROUP BY key here is
    # (rule_id, disposition) — NOT the chunked column — so one key legitimately appears in
    # every chunk, and a dict update would silently return the last chunk's count as the
    # whole answer. That would understate a rule's abstain rate, which is the one number the
    # keystone invariant is monitored by, and it would raise nothing while doing it.
    out: dict[tuple[str | None, str], int] = {}
    for chunk in id_chunks(evaluation_ids):
        rows = conn.execute(
            select(
                eligibility_requirements.c.rule_id,
                eligibility_requirements.c.disposition,
                func.count(),
            )
            .where(eligibility_requirements.c.evaluation_id.in_(chunk))
            .group_by(
                eligibility_requirements.c.rule_id, eligibility_requirements.c.disposition
            )
        ).all()
        for row in rows:
            key = (row[0], row[1])
            out[key] = out.get(key, 0) + int(row[2])
    return out
