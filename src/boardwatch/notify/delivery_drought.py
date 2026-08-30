"""Delivery-drought detector (unattended observability).

Intake can be healthy — boards up, net-new postings arriving — while the tailor, rank, or
delivery path silently ships nothing: an over-suppression bug, a ranker that drops every
candidate, a broken résumé render. The run still reaches a clean outcome, so the heartbeat
fires green, and the intake-death detector stays quiet because net-new is not zero.

This raises a SOFT, non-fatal alert when the last `window` clean runs each judged at least
one new eligible/uncertain candidate yet delivered zero leads. The candidate guard is what
keeps it honest: a quiet steady-state run that simply had nothing new to judge, and a full
eligibility collapse where nothing was judged eligible, both judge zero candidates and so
abstain — this fires only when the pipeline is finding deliverable postings and then
dropping all of them. (A collapse that empties the standing eligible corpus itself is a
different signal — a corpus regression — not this one, and is out of scope here.)

Delivered leads are counted from the `resume_tailored` artifacts the tailor writes;
candidates from the run's own `eligibility_evaluations`, across lanes — one deliverable
verdict is enough to say the run found something to ship.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.engine import Engine

from boardwatch.store.queries import RUN_OK
from boardwatch.store.run_funnel_queries import TAILORED_KIND
from boardwatch.store.tables import artifacts, eligibility_evaluations, runs

DELIVERY_DROUGHT_WINDOW = 3

# The verdicts that can become a delivered lead. `ineligible` cannot, so a run that judged
# only ineligible postings has found no candidate and this detector abstains on it.
_CANDIDATE_VERDICTS = ("eligible", "uncertain")


def check_delivery_drought(engine: Engine, *, window: int = DELIVERY_DROUGHT_WINDOW) -> str | None:
    """Return a soft-alert string when the last `window` clean runs each judged a candidate
    yet delivered nothing, else ``None``.

    Only `status = 'ok'` runs count, newest first — a crashed or in-flight run carries no
    delivery signal. Fewer than `window` clean runs of history abstains rather than firing on
    a fresh store, mirroring the intake-death detector.
    """
    with engine.connect() as conn:
        run_ids = [
            int(rid)
            for (rid,) in conn.execute(
                select(runs.c.id)
                .where(runs.c.status == RUN_OK)
                .order_by(runs.c.id.desc())
                .limit(window)
            ).all()
        ]
        if len(run_ids) < window:
            return None
        delivered = {
            int(rid): int(count)
            for rid, count in conn.execute(
                select(artifacts.c.run_id, func.count())
                .where(artifacts.c.kind == TAILORED_KIND, artifacts.c.run_id.in_(run_ids))
                .group_by(artifacts.c.run_id)
            ).all()
        }
        candidates = {
            int(rid): int(count)
            for rid, count in conn.execute(
                select(eligibility_evaluations.c.run_id, func.count())
                .where(
                    eligibility_evaluations.c.run_id.in_(run_ids),
                    eligibility_evaluations.c.verdict.in_(_CANDIDATE_VERDICTS),
                )
                .group_by(eligibility_evaluations.c.run_id)
            ).all()
        }
    if any(delivered.get(rid, 0) != 0 for rid in run_ids):
        return None
    if any(candidates.get(rid, 0) == 0 for rid in run_ids):
        return None
    ids = ", ".join(str(rid) for rid in run_ids)
    return (
        f"delivery: 0 leads shipped across the last {window} clean runs (runs {ids}) while each "
        f"judged new eligible candidates — the tailor, rank, or delivery path may be broken"
    )
