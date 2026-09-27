"""The "buried good lead" read: a judge-cleared posting the program never delivered.

The final gate judges `gate.depth` leads a run and only `--top` of them are delivered, so a posting
the judge called `eligible` with seniority fit `yes` can rank below the cut run after run until it
closes. Measured on the live store 2026-09-26: 36 of 1,283 judged postings over runs 43-480, 6 of
them since closed — each a good job lost with nothing in the funnel or the alerts saying so. This is
the read that makes that population visible. It is REPORTED, never a drop bucket: these postings are
not leaving any stage, they are standing outside the delivered set.

A second, separately-labelled population sits beside it: postings the judge cleared under an OLDER
key (another prompt, model, facts, band or body) that have no verdict under the current key. The
T113 refresh re-judges delivered rows only, so a lead cleared once and never delivered is never
asked again, and the current-key read above cannot see it. On the live store 2026-09-26 this was
29 of the 40 never-built postings ever cleared, and 5 of the 6 lost.

Every current-key verdict comes through the lane's own gate reads (`current_gate_verdicts`,
`current_gate_seniority`) on each posting's CURRENT version, keyed on the profile's judge inputs,
so this can never call a lead cleared that the delivery queue would not.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Connection, func, select

from boardwatch.core.settings import Settings
from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.final_gate import GATE_VERSION_PREFIX, gate_effort_key
from boardwatch.eligibility.preflight import current_judge_inputs
from boardwatch.eligibility.read import current_gate_seniority, current_gate_verdicts
from boardwatch.store.param_chunks import id_chunks
from boardwatch.store.queries import current_posting_version_ids
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
    #: The same two halves for postings cleared only under an OLDER judge key and never re-judged
    #: under the current one. Disjoint from `open`/`closed` by construction.
    stale_open: tuple[int, ...]
    stale_closed: dict[int, datetime]


def buried_good_leads(conn: Connection, settings: Settings) -> BuriedLeads:
    """Every posting whose current final-gate verdict is `eligible` with seniority fit `yes` and
    whose job has no `built` disposition.

    `built` is matched whether or not the drain has since reopened it: a reopened job WAS
    delivered, and "never delivered" is the question. A posting with no `job_id` has no
    disposition and counts.

    Under `target_seniority_band = any` the seniority question is not asked (T188), so no reading
    can be `yes`; there the verdict alone clears, or this read could never fire for such a tenant.

    `stale_*` holds a posting only when it has NO current-key verdict and its NEWEST final-gate row
    (over every version, under any key) is `eligible` with seniority fit `yes` — or `eligible` under
    a recorded band of `any`, the same exception. Newest, not any: a lead an older judge cleared
    and a later one held was not left cleared.

    Empty when there is no profile, like every read keyed on the judge's inputs.
    """
    facts, target_band = current_judge_inputs(conn, settings)
    if facts is None:
        return BuriedLeads(open=(), closed={}, stale_open=(), stale_closed={})
    built = select(job_dispositions.c.job_id).where(job_dispositions.c.disposition == "built")
    # Narrowed to postings with ANY final-gate row, so the key-matched reads below see hundreds
    # of versions rather than the whole corpus. Which row is current is theirs.
    #
    # This is a FULL SCAN of `eligibility_evaluations`: no index reaches the gate rows (the
    # table's indexes lead on `input_id`, and its one partial index covers `deterministic` rows
    # only). Measured 1-12 s warm-to-cold on the 2.7M-row store, so a run reads it ONCE — the
    # funnel does, and the alert is handed the result.
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
            eligibility_evaluations.c.engine_version.startswith(
                GATE_VERSION_PREFIX, autoescape=True
            ),
            postings.c.job_id.is_(None) | postings.c.job_id.not_in(built),
        )
    ).all()
    closed_at = {int(row.id): row.closed_at for row in rows}
    version_ids = list(current_posting_version_ids(conn, list(closed_at)).values())
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
    # `current_gate_verdicts` holds a posting exactly when it has a current-key verdict, whatever
    # that verdict is — so a posting it holds is never stale, however it was cleared before.
    unjudged = [pid for pid in closed_at if pid not in verdicts]
    stale = sorted(
        pid for pid, (verdict, raw) in _newest_gate_rows(conn, unjudged).items()
        if verdict == "eligible" and _cleared_seniority(raw)
    )
    return BuriedLeads(
        open=tuple(pid for pid in cleared if closed_at[pid] is None),
        closed={pid: closed_at[pid] for pid in cleared if closed_at[pid] is not None},
        stale_open=tuple(pid for pid in stale if closed_at[pid] is None),
        stale_closed={pid: closed_at[pid] for pid in stale if closed_at[pid] is not None},
    )


def _cleared_seniority(raw: object) -> bool:
    """A stored row's seniority reading clears it: `yes`, or a row asked under band `any`."""
    if not isinstance(raw, dict):
        return False
    gate = raw.get("gate_verdict")
    fit = gate.get("seniority_fit") if isinstance(gate, dict) else None
    return fit == "yes" or raw.get("target_band") == "any"


def _newest_gate_rows(
    conn: Connection, posting_ids: list[int]
) -> dict[int, tuple[str, object]]:
    """posting_id -> (verdict, raw_output_json) of its newest final-gate row, over all of its
    versions and under ANY key — `read.newest_gate_verdicts`' selection, with the raw output the
    seniority reading lives in. Chunked on the group key, so chunking cannot change the answer."""
    out: dict[int, tuple[str, object]] = {}
    for chunk in id_chunks(posting_ids):
        latest = (
            select(posting_versions.c.posting_id,
                   func.max(eligibility_evaluations.c.id).label("eid"))
            .join(eligibility_inputs, eligibility_evaluations.c.input_id == eligibility_inputs.c.id)
            .join(posting_versions,
                  posting_versions.c.id == eligibility_inputs.c.posting_version_id)
            .where(
                posting_versions.c.posting_id.in_(chunk),
                eligibility_evaluations.c.engine_kind == "llm",
                eligibility_evaluations.c.engine_version.startswith(
                    GATE_VERSION_PREFIX, autoescape=True
                ),
            )
            .group_by(posting_versions.c.posting_id)
            .subquery()
        )
        rows = conn.execute(
            select(latest.c.posting_id, eligibility_evaluations.c.verdict,
                   eligibility_evaluations.c.raw_output_json)
            .join(latest, eligibility_evaluations.c.id == latest.c.eid)
        ).all()
        out.update({int(r.posting_id): (str(r.verdict), r.raw_output_json) for r in rows})
    return out
