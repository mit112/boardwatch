"""Direct-share attribution: where direct-apply and other leads leave the slate, per rank tier.

`slate_direct_share` (D-674) reorders each rank tier so direct-apply leads take a share of its
positions, BEFORE the duplicate, handled, applied, cap, lane-copy and twin filters run, and with
no re-reservation after them. A reorder that a filter then undoes shows up nowhere: run 972
ranked 23 direct leads and delivered 10, and the per-route, per-tier rejected ids that would say
where 13 went were never kept. This module keeps them. It changes no decision: it COUNTS.

Two halves, joined by `attribute`:

- `DirectShareTally` is the ranker's side. It is armed only when the share is above zero and the
  routes file is readable, and `top_cmd` calls `drop` at each point a lead leaves the ranked
  list. It records the leads entering the interleave, the positions the share rule claimed, and
  every ranker exit by tier and route.
- `attribute` is the pipeline's side. It gives each lead that SURVIVED the ranker one fate from
  the id sets the runner already keeps (withheld as gone, rejected by the judge, cut beyond the
  slate, deferred, failed projection, failed tailoring, delivered) and returns the report the
  funnel publishes.

The report reconciles per tier and route: `entered == sum(removed) + delivered + unaccounted`,
with `unaccounted` derived and required to be 0. A step named in `STEPS` is the same name the
funnel's own drop counters use (see `RANKER_STEP_COUNTER`), so the funnel can cross-check each
step's total against the counter that already exists.

"Direct" is `ApplyRoutes.is_direct_auto` and nothing else; this module never classifies a link.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Literal

#: Steps the ranker's own loop counts, in the order a lead meets them.
RANKER_STEPS: tuple[str, ...] = (
    "hidden_duplicate",
    "hidden_handled",
    "hidden_applied",
    "hidden_lane_copy",
    "hidden_requisition_twin",
    "hidden_slate_cap",
    "hidden_cluster_cap",
    "capped_by_top_n",
)

#: Steps the runner applies to a lead that survived the ranker, in order.
RUN_STEPS: tuple[str, ...] = (
    "withheld_not_live",
    "gate_rejected",
    "beyond_slate",
    "execution_deferred",
    "projection_failed",
    "tailor_failed",
)

STEPS: tuple[str, ...] = RANKER_STEPS + RUN_STEPS

#: Step -> the `ShortlistCounts` field the funnel already counts it in. `beyond_slate` is absent
#: on purpose: the funnel folds it into `hidden_below_cutoff` beside `capped_by_top_n`.
RANKER_STEP_COUNTER: Mapping[str, str] = {
    "hidden_duplicate": "hidden_duplicate",
    "hidden_handled": "hidden_handled",
    "hidden_applied": "hidden_applied",
    "hidden_lane_copy": "hidden_lane_copy",
    "hidden_requisition_twin": "hidden_requisition_twin",
    "hidden_slate_cap": "hidden_slate_cap",
    "hidden_cluster_cap": "hidden_cluster_cap",
    "capped_by_top_n": "hidden_below_cutoff",
}

State = Literal["measured", "off", "inert", "not_measured"]
ROUTES: tuple[str, str] = ("direct", "non_direct")


class DirectShareTally:
    """The ranker's counters. Mutable, single-threaded, and read only by `attribute`."""

    def __init__(
        self,
        *,
        share: float,
        state: Literal["measured", "off", "inert"],
        detail: str = "",
        direct_ids: frozenset[int] = frozenset(),
        entered: Counter[tuple[int, bool]] | None = None,
        reserved: Mapping[int, int] | None = None,
    ) -> None:
        self.share = share
        self.state = state
        self.detail = detail
        self._direct_ids = direct_ids
        #: (tier, direct) -> leads that entered the interleave.
        self.entered: Counter[tuple[int, bool]] = entered or Counter()
        #: tier -> positions the share rule claimed for a direct lead.
        self.reserved: dict[int, int] = dict(reserved or {})
        #: (tier, direct, step) -> leads removed by a ranker step.
        self.removed: Counter[tuple[int, bool, str]] = Counter()
        #: (tier, step) -> posting ids of DIRECT leads removed by a ranker step, in the order met.
        self.dropped_ids: dict[tuple[int, str], list[int]] = {}
        #: posting id -> (tier, direct) for every lead still on the ranked list at the end.
        self.survivors: dict[int, tuple[int, bool]] = {}

    @classmethod
    def off(cls, share: float) -> DirectShareTally:
        return cls(share=share, state="off", detail="slate_direct_share is 0")

    @classmethod
    def inert(cls, share: float, detail: str) -> DirectShareTally:
        return cls(share=share, state="inert", detail=detail)

    @classmethod
    def measured(
        cls,
        share: float,
        *,
        leads: Iterable[tuple[int, int]],
        direct_ids: frozenset[int],
        reserved: Mapping[int, int],
    ) -> DirectShareTally:
        """`leads` is (posting_id, tier) for every lead handed to the interleave."""
        entered = Counter((tier, pid in direct_ids) for pid, tier in leads)
        return cls(
            share=share, state="measured", direct_ids=direct_ids, entered=entered,
            reserved=reserved,
        )

    def drop(self, step: str, tier: int, posting_id: int) -> None:
        """One lead left the ranked list at `step`."""
        direct = posting_id in self._direct_ids
        self.removed[(tier, direct, step)] += 1
        if direct:
            self.dropped_ids.setdefault((tier, step), []).append(posting_id)

    def finish(self, survivors: Iterable[tuple[int, int]]) -> None:
        """Record the leads still on the ranked list, `(posting_id, tier)` each."""
        self.survivors = {pid: (tier, pid in self._direct_ids) for pid, tier in survivors}


@dataclass(frozen=True)
class RouteCounts:
    """One route inside one tier."""

    entered: int
    #: step -> leads removed there. Every applicable step is present, a measured 0 included.
    removed: Mapping[str, int]
    delivered: int
    #: Of `delivered`: leads the lane split sent to the review folder. Delivered, not lost.
    delivered_review_lane: int
    #: entered - sum(removed) - delivered. Anything but 0 is a lead the attribution lost.
    unaccounted: int
    #: step -> ids of the DIRECT leads removed there. Empty for the non-direct route.
    dropped_ids: Mapping[str, tuple[int, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class TierCounts:
    reserved: int
    direct: RouteCounts
    non_direct: RouteCounts

    def route(self, name: str) -> RouteCounts:
        return self.direct if name == "direct" else self.non_direct


@dataclass(frozen=True)
class DirectShareReport:
    """What `slate_direct_share` did to each tier's leads. `tiers` is empty unless `measured`."""

    state: State
    share: float | None
    detail: str
    steps: tuple[str, ...] = ()
    tiers: Mapping[int, TierCounts] = field(default_factory=dict)
    #: Delivered leads whose link was written AFTER the ranker classified them (D-689/D-690) and
    #: whose new link changed the route: counted under the ranker's route above, delivered under
    #: the other. The store recount sees the new route, so these are the known difference.
    relinked_to_direct: int = 0
    relinked_off_direct: int = 0

    @property
    def measured(self) -> bool:
        return self.state == "measured"

    def total(self, route: str, attribute_name: str) -> int:
        """Sum of `entered`, `delivered`, `delivered_review_lane` or `unaccounted` over tiers."""
        return sum(getattr(tier.route(route), attribute_name) for tier in self.tiers.values())

    def step_total(self, step: str, route: str | None = None) -> int:
        routes = ROUTES if route is None else (route,)
        return sum(
            tier.route(name).removed.get(step, 0)
            for tier in self.tiers.values()
            for name in routes
        )

    @property
    def reserved(self) -> int:
        return sum(tier.reserved for tier in self.tiers.values())

    @property
    def unaccounted(self) -> int:
        """Leads the attribution could not place, as a magnitude so errors cannot cancel."""
        return sum(
            abs(tier.route(name).unaccounted) for tier in self.tiers.values() for name in ROUTES
        )

    @property
    def reconciles(self) -> bool | None:
        """None unless measured: an uncomputable identity is not a pass."""
        return None if not self.measured else self.unaccounted == 0


def not_measured(detail: str) -> DirectShareReport:
    return DirectShareReport(state="not_measured", share=None, detail=detail)


def attribute(
    tally: DirectShareTally | None,
    *,
    liveness_ran: bool,
    gate_armed: bool,
    projection_ran: bool,
    dead_ids: Iterable[int],
    gate_excluded_ids: Iterable[int],
    beyond_slate_ids: Iterable[int],
    execution_deferred_ids: Iterable[int],
    projection_failed_ids: Iterable[int],
    tailor_failed_ids: Iterable[int],
    delivered: Mapping[int, bool],
    relinked: Mapping[int, bool] | None = None,
) -> DirectShareReport:
    """Give every lead that survived the ranker one fate and total it by tier and route.

    `delivered` maps a delivered posting id to whether the lane split sent it to review (no
    render). The id sets are the ones the runner keeps for its cohort guard, so a lead in two of
    them takes the EARLIER fate here and the funnel's per-step cross-check disagrees: the sets
    are meant to be disjoint and this does not repair them. A step the run did not take (no
    liveness probe, gate off, no `--project`) is absent from the report, never a column of zeros.
    A survivor in no set at all is `unaccounted`.

    `relinked` maps a posting id whose link was written after the ranker ran to whether the new
    link is direct, as the caller classified it. It moves no lead between routes here; it only
    counts the delivered leads it re-routed, so the funnel can account for them.
    """
    if tally is None:
        return not_measured("the ranker did not run")
    if tally.state != "measured":
        return DirectShareReport(state=tally.state, share=tally.share, detail=tally.detail)

    steps = tuple(
        step for step in STEPS
        if not (
            (step == "withheld_not_live" and not liveness_ran)
            or (step == "gate_rejected" and not gate_armed)
            or (step == "projection_failed" and not projection_ran)
        )
    )
    run_fates: list[tuple[str, frozenset[int]]] = [
        ("withheld_not_live", frozenset(dead_ids)),
        ("gate_rejected", frozenset(gate_excluded_ids)),
        ("beyond_slate", frozenset(beyond_slate_ids)),
        ("execution_deferred", frozenset(execution_deferred_ids)),
        ("projection_failed", frozenset(projection_failed_ids)),
        ("tailor_failed", frozenset(tailor_failed_ids)),
    ]
    removed: Counter[tuple[int, bool, str]] = Counter(tally.removed)
    dropped: dict[tuple[int, str], list[int]] = {k: list(v) for k, v in tally.dropped_ids.items()}
    delivered_count: Counter[tuple[int, bool]] = Counter()
    review_count: Counter[tuple[int, bool]] = Counter()
    unplaced: Counter[tuple[int, bool]] = Counter()
    to_direct = off_direct = 0
    for posting_id, (tier, direct) in tally.survivors.items():
        key = (tier, direct)
        for step, ids in run_fates:
            if posting_id in ids:
                removed[(tier, direct, step)] += 1
                if direct:
                    dropped.setdefault((tier, step), []).append(posting_id)
                break
        else:
            if posting_id in delivered:
                delivered_count[key] += 1
                review_count[key] += int(delivered[posting_id])
                now_direct = (relinked or {}).get(posting_id, direct)
                to_direct += int(now_direct and not direct)
                off_direct += int(direct and not now_direct)
            else:
                unplaced[key] += 1

    # A step outside `steps` is not folded into a bucket: `by_step` below iterates `steps` only, so
    # a mistyped or unexpected step leaves its leads out of the sum and the lead shows up as
    # `unaccounted`, which fails the reconciliation instead of balancing on a lost count.
    tiers: dict[int, TierCounts] = {}
    for tier in sorted({t for t, _ in tally.entered} | {t for t, _, _ in removed}
                       | {t for t, _ in delivered_count} | {t for t, _ in unplaced}):
        def counts(direct: bool, tier: int = tier) -> RouteCounts:
            by_step = {step: removed[(tier, direct, step)] for step in steps}
            entered = tally.entered[(tier, direct)]
            delivered_here = delivered_count[(tier, direct)]
            return RouteCounts(
                entered=entered,
                removed=by_step,
                delivered=delivered_here,
                delivered_review_lane=review_count[(tier, direct)],
                unaccounted=entered - sum(by_step.values()) - delivered_here,
                dropped_ids=(
                    {
                        step: tuple(dropped[(tier, step)])
                        for step in steps if dropped.get((tier, step))
                    }
                    if direct else {}
                ),
            )

        tiers[tier] = TierCounts(
            reserved=tally.reserved.get(tier, 0), direct=counts(True), non_direct=counts(False)
        )
    return DirectShareReport(
        state="measured", share=tally.share, detail="", steps=steps, tiers=tiers,
        relinked_to_direct=to_direct, relinked_off_direct=off_direct,
    )


def direct_share_to_dict(report: DirectShareReport | None) -> dict[str, object]:
    """The artifact's `direct_share` section. Counts appear only when they were measured."""
    if report is None:
        report = not_measured("no direct-share attribution was collected for this run")
    if not report.measured:
        return {
            "instrumented": False,
            "state": report.state,
            "share": report.share,
            "detail": report.detail,
        }

    def route_dict(counts: RouteCounts, *, ids: bool) -> dict[str, object]:
        out: dict[str, object] = {
            "entered": counts.entered,
            "removed": dict(counts.removed),
            "delivered": counts.delivered,
            "delivered_review_lane": counts.delivered_review_lane,
            "unaccounted": counts.unaccounted,
        }
        if ids:
            out["dropped_ids"] = {step: list(v) for step, v in counts.dropped_ids.items()}
        return out

    def totals(route: str) -> dict[str, object]:
        return {
            "entered": report.total(route, "entered"),
            "removed": {step: report.step_total(step, route) for step in report.steps},
            "delivered": report.total(route, "delivered"),
            "delivered_review_lane": report.total(route, "delivered_review_lane"),
            "unaccounted": report.total(route, "unaccounted"),
        }

    return {
        "instrumented": True,
        "state": "measured",
        "share": report.share,
        "detail": None,
        "steps": list(report.steps),
        "reconciles": report.reconciles,
        "reserved": report.reserved,
        "relinked": {
            "to_direct": report.relinked_to_direct, "off_direct": report.relinked_off_direct
        },
        "totals": {"direct": totals("direct"), "non_direct": totals("non_direct")},
        "tiers": {
            str(tier): {
                "reserved": counts.reserved,
                "direct": route_dict(counts.direct, ids=True),
                "non_direct": route_dict(counts.non_direct, ids=False),
            }
            for tier, counts in sorted(report.tiers.items())
        },
    }


def direct_share_lines(report: DirectShareReport | None) -> list[str]:
    """The human half: one totals table, the unreconciled warning, the dropped direct ids."""
    lines = ["", "## Direct share", ""]
    if report is None:
        return lines + ["*NOT MEASURED. No attribution was collected for this run.*"]
    if report.state == "not_measured":
        return lines + [f"*NOT MEASURED. {report.detail}.*"]
    if report.state == "off":
        return lines + [
            f"*OFF. `slate_direct_share` is {report.share:g}, so no lead was classified as "
            "direct or given a reserved position. Nothing here is a zero reading; it was not "
            "taken.*"
        ]
    if report.state == "inert":
        return lines + [
            f"*INERT. `slate_direct_share` is {report.share:g} but the share did nothing: "
            f"{report.detail}. Nothing was classified.*"
        ]
    d, n = "direct", "non_direct"
    rows = [
        ("entered the interleave", report.total(d, "entered"), report.total(n, "entered")),
        ("reserved positions", report.reserved, None),
    ]
    rows += [
        (step, report.step_total(step, d), report.step_total(step, n))
        for step in report.steps
        if report.step_total(step) > 0
    ]
    rows += [
        ("delivered", report.total(d, "delivered"), report.total(n, "delivered")),
        ("unaccounted", report.total(d, "unaccounted"), report.total(n, "unaccounted")),
    ]
    lines += [
        f"`slate_direct_share` {report.share:g}, over {len(report.tiers)} rank tier(s).",
        "",
        "| step | direct | non-direct |",
        "|---|---:|---:|",
        *(f"| {name} | {a} | {'—' if b is None else b} |" for name, a, b in rows),
        "",
        "*Each lead is counted once, at the first step that removed it, and `entered = removed "
        "+ delivered` holds per tier and route. Steps that removed nothing on either route are "
        "left out; the artifact's JSON has every step by tier. `reserved positions` are the "
        "slots the share's quota clause claimed for a direct lead (one already next in score "
        "order is counted too), so it is a direct count only. `capped_by_top_n` is the "
        "ranker's cutoff and `beyond_slate` the cut after the judge; the funnel's "
        "`capped_by_top_n` drop is their sum.*",
    ]
    if report.relinked_to_direct or report.relinked_off_direct:
        lines += [
            "",
            f"Re-linked after ranking: {report.relinked_to_direct} delivered lead(s) counted "
            f"non-direct above were delivered with a direct link, {report.relinked_off_direct} "
            "the other way. The link steps run after the ranker (D-689, D-690).",
        ]
    if report.reconciles is False:
        lines += [
            "",
            f"**DOES NOT RECONCILE: {report.unaccounted} lead(s) are in no step and were not "
            "delivered.** A drop was attributed to the wrong tier or route, or a lead left the "
            "run without a step. Do not read the table above as a measurement.",
        ]
    ids_by_step: dict[str, list[int]] = {}
    for tier in report.tiers.values():
        for step, ids in tier.direct.dropped_ids.items():
            ids_by_step.setdefault(step, []).extend(ids)
    if ids_by_step:
        lines += ["", "Direct leads removed, by step:", ""]
        lines += [
            f"- `{step}`: {', '.join(str(i) for i in sorted(ids_by_step[step]))}"
            for step in report.steps if step in ids_by_step
        ]
    return lines
