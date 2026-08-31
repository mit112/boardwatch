"""Apply-lane drought detector (unattended observability).

The sibling `delivery_drought` detector counts `resume_tailored` artifacts, which the tailor
writes **regardless of which lane `review_gate.lane` routes the lead to**. So the one fault it
cannot see is the one that costs the owner everything: if location classification, the role gate
or a requirement flag broke globally, every lead would route to `_review`, artifacts would keep
appearing at the normal rate, `delivery_drought` would abstain because delivery is non-zero, the
heartbeat would stay green — and an unattended machine would ship **zero apply-ready leads for a
fortnight with nothing firing**.

This is the instrument for exactly that: a SOFT alert when the last `window` clean runs each
delivered placeable leads and **none of them reached the apply lane**.

The honesty guard is the conjunction, and it is what keeps this from double-reporting a fault
that already has an owner:

* A run with **zero placeable leads abstains.** Zero delivery is `delivery_drought`'s fault to
  report, and firing both on one fault would state two diagnoses for one cause.
* `ineligible` and `closed` leads are **not placeable** and are excluded upstream in
  `apply_lane_placements`. Each has its own drain (D-321, D-383), so a run whose leads were all
  judged ineligible, or whose requisitions have all since come down, is not evidence about the
  location/role/requirement gates and must not be reported as though it were.

It never sets `fatal`. The run succeeded and the leads it produced are real — they are sitting in
`_review`, reviewable and not lost — so this tickets, it does not trip the dead-man's switch.

**Known property, and its direction is abstain rather than alarm.** `delivered_unapplied` returns
one row per canonical JOB at its MOST RECENT delivery, so a job an older run in the window
delivered and a newer run re-delivered is attributed to the newer run alone. An older run can
therefore read zero placeable leads because its work was re-delivered, not because it delivered
nothing — and this detector then abstains on that window. That is a false NEGATIVE, never a false
positive, which is the right direction for an alarm nobody is present to dismiss. It is also rare
in practice: delivery is recency-dominated and runs 120-130 shipped 100% same-day postings, so
consecutive runs re-delivering one job is not the normal shape.

**Why a count and not a rate.** `corpus_regression` deliberately uses a rate because an identity
re-key legitimately drops its count by 96% on a clean run. This detector is immune to that
problem by construction: it compares a run's apply-lane arrivals against that SAME run's
placeable leads, so both sides move together and the ratio is the signal. The threshold is zero —
not a fraction — because a healthy run puts *some* work in the blind-apply list, and any non-zero
arrival is enough to prove the gates still pass something.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.engine import Engine

from boardwatch.store.delivery_queries import apply_lane_placements
from boardwatch.store.queries import RUN_OK
from boardwatch.store.tables import runs

APPLY_LANE_DROUGHT_WINDOW = 3


def check_apply_lane_drought(
    engine: Engine, *, window: int = APPLY_LANE_DROUGHT_WINDOW
) -> str | None:
    """Return a soft-alert string when the last `window` clean runs each delivered placeable
    leads yet routed every one of them away from the apply lane, else ``None``.

    Only `status = 'ok'` runs count, newest first — a crashed or in-flight run carries no
    delivery signal. Fewer than `window` clean runs of history abstains rather than firing on a
    fresh store, mirroring both sibling detectors.
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
        placed = apply_lane_placements(conn, run_ids=set(run_ids))
    # Abstain before firing. Reading order first, arrivals second, states the precedence the
    # docstring claims — a run that placed nothing is the sibling detector's story.
    #
    # Mutation-pinned, with ONE survivor proven unobservable: SWAPPING these two checks changes
    # nothing, because arrivals are a subset of placeable leads, so `[0] == 0` implies `[1] == 0`
    # and the second check is False wherever the first is True. Both orders return `None` on the
    # same runs. It is written this way for the reader, not for the result — do not "fix" the
    # order on the strength of a test that cannot see it.
    if any(placed.get(rid, (0, 0))[0] == 0 for rid in run_ids):
        return None
    if any(placed.get(rid, (0, 0))[1] != 0 for rid in run_ids):
        return None
    ids = ", ".join(str(rid) for rid in run_ids)
    placeable = sum(placed[rid][0] for rid in run_ids)
    return (
        f"apply lane: 0 of {placeable} placeable lead(s) reached the blind-apply queue across "
        f"the last {window} clean runs (runs {ids}) — every one was routed to review, so the "
        f"location, role or requirement gate may be misclassifying globally"
    )
