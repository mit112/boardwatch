"""The "buried good lead" read: a judge-cleared posting the program never delivered.

The final gate judges `gate.depth` leads a run and only `--top` of them are delivered, so a posting
the judge called `eligible` with seniority fit `yes` can rank below the cut run after run until it
closes. Measured on the live store 2026-09-26: 36 of 1,283 judged postings over runs 43-480, 6 of
them since closed — each a good job lost with nothing in the funnel or the alerts saying so. This is
the read that makes that population visible. It is REPORTED, never a drop bucket: these postings are
not leaving any stage, they are standing outside the delivered set.

Every verdict comes through the lane's own gate reads (`current_gate_verdicts`,
`current_gate_seniority`) on each posting's CURRENT version, keyed on the profile's judge inputs,
so this can never call a lead cleared that the delivery queue would not.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Connection, select

from boardwatch.core.settings import Settings
from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.final_gate import gate_effort_key, gate_engine_version
from boardwatch.eligibility.preflight import current_judge_inputs
from boardwatch.eligibility.read import current_gate_seniority, current_gate_verdicts
from boardwatch.store.queries import current_posting_versions
from boardwatch.store.tables import (
    eligibility_evaluations,
    eligibility_inputs,
    job_dispositions,
    posting_versions,
    postings,
)


@dataclass(frozen=True)
class BuriedLeads:
    """Judge-cleared postings whose job was never built, split by whether the posting is live."""

    #: posting ids still open — recoverable.
    open: tuple[int, ...]
    #: posting id -> `postings.closed_at` — lost. The timestamp is what lets the alert tell a loss
    #: THIS run from one an earlier run already reported.
    closed: dict[int, datetime]


def buried_good_leads(conn: Connection, settings: Settings) -> BuriedLeads:
    """Every posting whose current final-gate verdict is `eligible` with seniority fit `yes` and
    whose job has no `built` disposition.

    `built` is matched whether or not the drain has since reopened it: a reopened job WAS
    delivered, and "never delivered" is the question. A posting with no `job_id` has no
    disposition and counts.

    Under `target_seniority_band = any` the seniority question is not asked (T188), so no reading
    can be `yes`; there the verdict alone clears, or this read could never fire for such a tenant.

    Empty when there is no profile, like every read keyed on the judge's inputs.
    """
    facts, target_band = current_judge_inputs(conn, settings)
    if facts is None:
        return BuriedLeads(open=(), closed={})
    built = select(job_dispositions.c.job_id).where(job_dispositions.c.disposition == "built")
    # Narrowed to postings with ANY row under the current gate version, so the key-matched reads
    # below see hundreds of versions rather than the whole corpus. Which row is current is theirs.
    rows = conn.execute(
        select(postings.c.id, postings.c.closed_at)
        .distinct()
        .join(posting_versions, posting_versions.c.posting_id == postings.c.id)
        .join(eligibility_inputs,
              eligibility_inputs.c.posting_version_id == posting_versions.c.id)
        .join(eligibility_evaluations,
              eligibility_evaluations.c.input_id == eligibility_inputs.c.id)
        .where(
            eligibility_evaluations.c.engine_kind == "llm",
            eligibility_evaluations.c.engine_version == gate_engine_version(),
            postings.c.job_id.is_(None) | postings.c.job_id.not_in(built),
        )
    ).all()
    closed_at = {int(row.id): row.closed_at for row in rows}
    versions = current_posting_versions(conn, list(closed_at))
    version_ids = [version.posting_version_id for version in versions.values()]
    verdicts = current_gate_verdicts(
        conn, version_ids, facts, load_rules(settings.config_dir), model=settings.gate.model,
        effort=gate_effort_key(settings.gate.effort), target_band=target_band,
    )
    seniority = current_gate_seniority(
        conn, version_ids, facts, model=settings.gate.model, target_band=target_band
    )
    cleared = sorted(
        posting_id for posting_id, verdict in verdicts.items()
        if verdict == "eligible" and (target_band == "any" or seniority.get(posting_id) == "yes")
    )
    return BuriedLeads(
        open=tuple(pid for pid in cleared if closed_at[pid] is None),
        closed={pid: closed_at[pid] for pid in cleared if closed_at[pid] is not None},
    )
