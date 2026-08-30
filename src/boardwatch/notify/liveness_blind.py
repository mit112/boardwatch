"""Liveness-blindness detector: a prober that cannot reach anything, not a healthy corpus.

The liveness stage re-probes the shortlist immediately before the tailor loop and is
**fail-open by design** (`pipeline/liveness.py`): any transport fault — a timeout, a DNS
failure, an unexpected client error — returns `unknown`, and `unknown` is served. That is
the right direction, because nothing except an explicit gone-status may withhold a real
lead. What it also means is that a prober whose egress has broken entirely — DNS gone, a
proxy in front of it, the machine's IP blocked — returns `unknown` for **every** posting,
`dead` falls to zero, and the run ships the whole shortlist unverified while every count on
the run line still looks ordinary. Unattended, the owner receives dead requisitions
presented as live for as long as the break lasts.

The signal is the CONJUNCTION, not either half. A high `unknown` share on its own is a
normal bad afternoon on one provider. `dead == 0` on its own is the ordinary state — across
every instrumented run recorded to date, `dead` has been zero. Together they say something
neither says alone: the prober asked about the whole shortlist and did not get a single
definitive answer, which is a property of the prober rather than of the postings.

Soft and non-fatal, like the rest of this family. The alert is appended to `summary.errors`
(reprinted by the CLI, persisted onto the `runs` row) and this NEVER sets `summary.fatal`:
the run succeeded and the leads it produced are real, so the heartbeat must still fire. A
blind prober tickets; it does not trip the dead-man's switch.

**Single-run, and that is a limitation rather than a design preference.** The intended shape
was a rise sustained across consecutive runs, which is what separates one bad night from a
break. It is not buildable today: `liveness_checked` / `liveness_unknown` / `liveness_dead`
live only on the in-memory `PipelineSummary` and in the per-run funnel JSON written outside
the git tree — there is no persisted per-run column to read a window off, the way F4 reads
`runs.new_count`, and no reader that enumerates past funnels. The thresholds below are set
high enough that a single run can carry the claim on its own; persisting the counts would
let a lower rate over a window replace them.
"""

from __future__ import annotations

# Share of the probed shortlist that must come back `unknown` before this fires. Set against
# the recorded history rather than picked: across the 65 instrumented runs on record the
# highest share ever observed was 3 of 8 (0.375), and at the denominators this actually runs
# at it was 2 of 10 (0.20) and 3 of 40 (0.075). 0.75 is nearly four times the worst clean run
# at a real denominator, so no ordinary bad afternoon on one provider reaches it, while the
# failure this closes — an egress break, which returns `unknown` for everything — sits at 1.0.
# It is a rate and not a count on purpose: the shortlist size is `--top`, which has moved
# 8 -> 40 -> 10 -> 40 inside a fortnight, and a count threshold would silently change meaning
# every time it did.
LIVENESS_BLIND_RATE = 0.75

# Smallest probed shortlist this will judge. Below it a couple of unlucky timeouts are a large
# share of nothing: the worst clean run on record, 3 unknown of 8 probed, is 0.375 purely
# because 8 is small. Ten is the smallest shortlist the pipeline has run at, so this abstains
# on a hand-run `--top 5` rather than reporting a verdict a five-posting sample cannot carry.
LIVENESS_MIN_CHECKED = 10


def check_liveness_blind(
    checked: int | None,
    unknown: int | None,
    dead: int | None,
    *,
    rate: float = LIVENESS_BLIND_RATE,
    min_checked: int = LIVENESS_MIN_CHECKED,
) -> str | None:
    """Return a soft-alert string when this run's liveness probe looks blind, else ``None``.

    The three counts are `PipelineSummary.liveness_checked` / `_unknown` / `_dead`. ``None``
    on any of them means the shortlist was **not probed** — no prober was supplied — which is
    not the same as "probed and nothing was unknown" (the D-022/D-023 rule), so an unprobed
    run abstains rather than reporting a clean liveness result it never took.

    Abstains, never fires, in three more cases: fewer than ``min_checked`` postings probed, so
    a tiny sample cannot trip it; any ``dead`` at all, because a definitive gone-status proves
    the prober reached a board and the egress is therefore not broken; and an ``unknown`` share
    below ``rate``. ``checked == 0`` is caught by the denominator guard before the division.

    Note that `liveness_gone_after_redirect` is counted INSIDE ``unknown`` — those were
    gone-statuses forgiven for arriving through a redirect — so a run whose shortlist really
    had gone that way would raise the share here. It is deliberately not carved out: 30 of 40
    postings gone-after-redirect is itself a state worth a line in the run's errors.
    """
    if checked is None or unknown is None or dead is None:
        return None
    if checked < min_checked:
        return None
    if dead != 0:
        return None
    share = unknown / checked
    if share < rate:
        return None
    return (
        f"liveness: {unknown} of {checked} probes came back unknown ({share:.0%}) with 0 gone "
        f"— the prober may be blind (DNS, a proxy, or a blocked egress IP) and every lead this "
        f"run shipped went out unverified"
    )


__all__ = ["LIVENESS_BLIND_RATE", "LIVENESS_MIN_CHECKED", "check_liveness_blind"]
