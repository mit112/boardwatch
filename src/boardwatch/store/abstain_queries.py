"""The raw half of the per-rule abstain rate: observed dispositions, nothing else.

Deliberately does NOT know what the catalog declares. This returns exactly what the table
says and no more; reconciling it against the catalog enumeration — which is where a
never-fired rule becomes visible — is `reports/abstain.build_abstain_report`'s job. Keeping
the two apart is what stops the enumeration from being quietly re-derived from the data.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Connection, func, select

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
    rows = conn.execute(
        select(
            eligibility_requirements.c.rule_id,
            eligibility_requirements.c.disposition,
            func.count(),
        )
        .where(eligibility_requirements.c.evaluation_id.in_(evaluation_ids))
        .group_by(eligibility_requirements.c.rule_id, eligibility_requirements.c.disposition)
    ).all()
    return {(row[0], row[1]): int(row[2]) for row in rows}
