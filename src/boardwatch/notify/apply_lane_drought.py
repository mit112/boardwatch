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
one row per canonical JOB, and attribution follows whichever of the job's postings that read
offers, so a job two runs in the window both delivered is credited to exactly one of them. An
older run can therefore read zero placeable leads because its work is credited elsewhere, not
because it delivered nothing — and this detector then abstains on that window. That is a false
NEGATIVE, never a false positive, which is the right direction for an alarm nobody is present to
dismiss.

**The selection rule changed under this paragraph and the old wording is kept out deliberately.**
It said the winner was "the MOST RECENT delivery" and bounded the effect with "delivery is
recency-dominated". Since D-432 the winner is the job's LIVE posting, and recency only breaks a
tie between equally live ones — so a job whose live posting was delivered at run 73 is credited to
run 73 however many later runs re-deliver a closed sibling, and a recency argument no longer bounds
anything. The detector's DIRECTION is unchanged and no run loses credit it previously had: a closed
winner was already excluded here by `row.closed`, so the only movement is an older run gaining
credit it should always have had.

**Why a count and not a rate, and why the count now needs a POPULATION FLOOR.**
`corpus_regression` deliberately uses a rate because an identity re-key legitimately drops its
count by 96% on a clean run. This detector avoids that by construction: it compares apply-lane
arrivals against the placeable leads of the SAME runs, so both sides move together.

The threshold is still zero rather than a fraction, but the sentence that used to justify it —
"a healthy run puts *some* work in the blind-apply list" — **was an assumption about the
conversion rate, and D-458 falsified it.** Routing a lead cleared only by SILENCE away from the
apply lane took the rate from **44.77% to 6.66%**, measured over one 1,472-lead snapshot by
toggling `no_requirement_rows` alone (the pre-change arm differs, so the probe reads the flag).
A zero is only evidence of a fault if a healthy window would not produce one by chance, and
`(1 - p)**N` moved the smallest safe population from **12 placeable leads to 101** — an 8.4x
shift against code whose only guard was `!= 0`. Replayed over all 136 historical windows, the
unfloored form meets its own fire condition on **40 of them, every one healthy.**

So the population is checked explicitly instead of being assumed:
`APPLY_LANE_DROUGHT_MIN_PLACEABLE` holds the per-window false-alarm probability at <= 0.1%
(~1 in 370 runs) at the measured rate — `ceil(log(0.001) / log(1 - 0.0666))`. It is summed over
the WINDOW because that is the population the arithmetic is over.

**It is ADDED to the per-run `placeable == 0` abstain, and deliberately does not replace it.**
Folding the two into one window total was tried and is wrong: that per-run abstain is also the
anti-double-report guard, so a run that delivered nothing stays `check_delivery_drought`'s story
and one cause never gets two diagnoses. It costs coverage — that abstain silences roughly half of
all windows — but recovering those is a detector-separation question, not a false-alarm one, and
it is not folded in here.

**The trade is deliberate and its direction is the module's own.** Below the floor the detector
goes QUIET rather than guessing — a false negative, never a false positive, "the right direction
for an alarm nobody is present to dismiss". At the 8-18 placeable/run volume of runs 119-131 that
means silence; arming it there needs an adaptive window, which is a different change.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.engine import Engine

from boardwatch.store.delivery_queries import apply_lane_placements
from boardwatch.store.queries import RUN_OK
from boardwatch.store.tables import runs

APPLY_LANE_DROUGHT_WINDOW = 3
# Derived, not chosen: ceil(log(0.001) / log(1 - 0.0666)) at the measured post-D-458 apply
# rate, i.e. the smallest window population whose all-zero outcome is <= 0.1% likely when the
# lane is healthy. Re-derive it if that rate moves; do not tune it by eye.
APPLY_LANE_DROUGHT_MIN_PLACEABLE = 101


def check_apply_lane_drought(
    engine: Engine,
    *,
    window: int = APPLY_LANE_DROUGHT_WINDOW,
    min_placeable: int = APPLY_LANE_DROUGHT_MIN_PLACEABLE,
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
    # Abstain before firing, in three steps, and the ORDER is the precedence the docstring claims.
    #
    # 1. A run that placed nothing is the sibling detector's story — this is the anti-double-report
    #    guard, not merely a false-positive guard, so it stays per-run and stays FIRST.
    # 2. A window too small to tell a drought from chance is not evidence either way.
    # 3. Only then do arrivals decide.
    #
    # Mutation-pinned, with ONE survivor proven unobservable: swapping 1 and 3 changes nothing,
    # because arrivals are a subset of placeable leads, so `[0] == 0` implies `[1] == 0` and the
    # arrival check is False wherever the first is True. Both orders return `None` on the same
    # runs. It is written this way for the reader — do not "fix" it on a test that cannot see it.
    # Step 2 is NOT in that class: it is observable, and moving it after step 3 would fire on an
    # under-populated window.
    if any(placed.get(rid, (0, 0))[0] == 0 for rid in run_ids):
        return None
    placeable = sum(placed[rid][0] for rid in run_ids)
    if placeable < min_placeable:
        return None
    if any(placed.get(rid, (0, 0))[1] != 0 for rid in run_ids):
        return None
    ids = ", ".join(str(rid) for rid in run_ids)
    return (
        f"apply lane: 0 of {placeable} placeable lead(s) reached the blind-apply queue across "
        f"the last {window} clean runs (runs {ids}) — every one was routed to review, so the "
        f"location, role or requirement gate may be misclassifying globally"
    )
