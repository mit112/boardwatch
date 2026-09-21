"""B8's volume half, as a per-run soft alert (T110).

The sibling `apply_lane_drought` detector and this one look at the same cohort and cannot see
each other's fault. That one is a ZERO-detector: it fires when a WINDOW of runs each delivered
placeable leads and **not one** reached the apply lane, and its evidence bar is a population
(`APPLY_LANE_DROUGHT_MIN_PLACEABLE`) sized so an all-zero window is not chance. Structurally it
cannot see a 19 against a bar of 20 — nineteen arrivals are nineteen reasons for it to stay
quiet, and it is right to: nothing is broken, the lane is simply thin.

B8's volume half is a BAR, not a zero, and a program gate is read against it. So the reading
needs an instrument of its own, per run, and this is it.

**It reports the cohort the funnel published, never a second count.** The value comes from
`reports.run_funnel.ApplyLaneCohort`, which `pipeline.funnel_writer` builds once from
`store.delivery_queries.apply_lane_cohort`. A detector that re-derived its own number would be
free to disagree with the artifact the gate is read from — the second opinion D-332 exists to
prevent — and the disagreement would surface as an alert nobody could reproduce.

**Two abstains, and both are borrowed rather than invented.**

* A cohort that was NOT READ abstains. `None` means the funnel was not collected (it raised, and
  the caller stayed fail-open per D-287), which is silence about the lane and not a reading of
  zero.
* A run with **zero placeable leads** abstains, which is `check_delivery_drought`'s story and the
  same anti-double-report guard `apply_lane_drought` applies per run. A `--no-scan` run, a run
  whose every lead was judged ineligible, and a run whose requisitions have all come down each
  land here — none of them is evidence about apply-lane volume.

It never sets `fatal` and it never blocks: the run succeeded, its leads are real, and a thin day
is a number the owner reads, not a fault the machine can fix.

**Known property, inherited from the cohort and stated rather than hidden.**
`apply_lane_cohort` re-runs the lane over TODAY's state and `delivered_unapplied` credits a job
to exactly one of the runs that delivered it. Read at finalize time — which is the only time this
runs — "today" is the run's own day, so the number is a delivery-day reading. The same cohort
re-read weeks later is a SURVIVAL count and is not what this alert reported.
"""

from __future__ import annotations

from collections import Counter

from boardwatch.reports.run_funnel import ApplyLaneCohort

#: B8's volume bar: apply-lane leads per day. From `PROGRAM.md` §1's B8 row, not tuned here.
APPLY_LANE_VOLUME_BAR = 20


def check_apply_lane_volume(
    cohort: ApplyLaneCohort | None, *, bar: int = APPLY_LANE_VOLUME_BAR
) -> str | None:
    """Return a soft-alert string when this run's apply-lane cohort is under B8's bar, else
    ``None``.

    The held-reason breakdown is part of the alert rather than left to the artifact because it is
    what makes the number actionable: "16 of 41" says the gate failed, and "25 held, 19 of them
    `no_requirements_found`" says which gate to look at.
    """
    if cohort is None or cohort.placeable == 0:
        return None
    if cohort.in_apply >= bar:
        return None
    held: Counter[str] = Counter(
        placement.review_reason or "unnamed"
        for placement in cohort.placements
        if placement.lane != ""
    )
    # Empty when every placeable lead reached the lane and the run was simply small — a real
    # and reportable way to miss the bar, so the clause is dropped rather than the alert.
    reasons = (
        f" ({', '.join(f'{reason} {count}' for reason, count in held.most_common())})"
        if held
        else ""
    )
    return (
        f"apply lane: {cohort.in_apply} lead(s) reached the blind-apply queue, under B8's bar "
        f"of {bar} — {cohort.placeable} placeable, {cohort.placeable - cohort.in_apply} held "
        f"for review{reasons}"
    )
