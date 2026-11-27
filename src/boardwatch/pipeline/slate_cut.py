"""T368 step 1: the post-gate survivor list, recorded at the slate cut and ordering nothing.

The cut (T63) takes the post-gate survivors in ranker order, and `_slate_size` reads pre-judge
tiers, so a lead the judge has just read above band can take a slot before the lane split sends
it to review. Whether ordering the cut by the current seniority reading would deliver more needs
a replay, and a replay needs each survivor as the cut saw it: its ranker position, tier and
reading as of that run. Gate rows alone cannot give that, because a survivor with a current
reading is not re-judged and gets no new row (`gate_judge.run_gate_stage`'s `already_gated`).

So every gated run writes `slate-cut-<run>.json` beside the funnel: every survivor in ranker
order with its position, shortlist rank, tier, the gate's reading, whether that reading was
judged this run or already stood, whether it made the slate, and, once the lane split has run,
its lane. The header says whether the run scanned (`scan_ran`), so a nightly can be told from an
intraday pass sharing its day folder. `tools.slate_cut_replay` reads N of these files.

**Nothing reads this back.** The readings come through the same two reads `_lead_lanes` makes,
and the record is never an input to the cut, a lane, a disposition, a `seen` write or a hash, so
it cannot become, change or count as a verdict or an abstain (the keystone invariant). A failure
is held and raised by `finish`, which the caller records like the near-miss report's failure;
neither `capture` nor `set_lanes` raises into the run.
"""

from __future__ import annotations

import json
from collections.abc import Collection, Mapping, Sequence
from pathlib import Path

from sqlalchemy import Engine

from boardwatch.cli.top_cmd import RankedPosting
from boardwatch.core.settings import Settings
from boardwatch.delivery.review_gate import REVIEW_DIR
from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.final_gate import gate_effort_key
from boardwatch.eligibility.preflight import current_judge_inputs
from boardwatch.eligibility.read import current_gate_seniority, current_gate_verdicts
from boardwatch.store.queries import current_posting_versions

SLATE_CUT_PREFIX = "slate-cut-"

#: How a survivor's reading relates to this run: judged by this run's request, a reading that
#: already stood (no new row was written for it), or no current reading at all.
READING_JUDGED = "judged"
READING_CACHED = "cached"
READING_ABSENT = "absent"


def _lane_name(lane: str) -> str:
    return "apply" if lane == "" else "review" if lane == REVIEW_DIR else lane


class SlateCutRecord:
    """One run's survivor list. `capture` at the cut, `set_lanes` after the lane split, `finish`
    in the finalize block."""

    def __init__(self, run_id: int) -> None:
        self._run_id = run_id
        self._report: dict[str, object] | None = None
        self._survivors: list[dict[str, object]] = []
        self._failure: Exception | None = None

    def capture(
        self,
        engine: Engine,
        settings: Settings,
        survivors: Sequence[RankedPosting],
        *,
        shortlist_ranks: Mapping[int, int],
        sent_ids: Collection[int],
        beyond_slate_ids: Collection[int],
        top_n: int,
        slate_size: int,
        scan_ran: bool,
    ) -> None:
        """Record `survivors` (the post-gate list in ranker order, BEFORE the cut) with their
        readings. Read-only: the same two reads `_lead_lanes` makes, over every survivor."""
        try:
            ids = [posting.posting_id for posting in survivors]
            with engine.connect() as conn:
                facts, target_band = current_judge_inputs(conn, settings)
                versions = current_posting_versions(conn, ids)
                version_ids = [v.posting_version_id for v in versions.values()]
                decisions = current_gate_verdicts(
                    conn, version_ids, facts, load_rules(settings.config_dir),
                    model=settings.gate.model, effort=gate_effort_key(settings.gate.effort),
                    target_band=target_band,
                )
                seniority = current_gate_seniority(
                    conn, version_ids, facts, model=settings.gate.model, target_band=target_band
                )
            sent = frozenset(sent_ids)
            beyond = frozenset(beyond_slate_ids)
            rows: list[dict[str, object]] = []
            for position, posting in enumerate(survivors, start=1):
                pid = posting.posting_id
                reading = (
                    READING_ABSENT if pid not in decisions
                    else READING_JUDGED if pid in sent else READING_CACHED
                )
                rows.append({
                    "position": position,
                    "posting_id": pid,
                    "shortlist_rank": shortlist_ranks.get(pid),
                    "tier": posting.tier,
                    "decision": decisions.get(pid),
                    "seniority_fit": seniority.get(pid),
                    "reading": reading,
                    "in_slate": pid not in beyond,
                    "lane": None,
                })
            self._survivors = rows
            self._report = {
                "version": 1,
                "run_id": self._run_id,
                "scan_ran": scan_ran,
                "top_n": top_n,
                "slate_ceiling": settings.slate_ceiling,
                "slate_size": slate_size,
                "target_band": target_band,
                "survivors": rows,
            }
        except Exception as exc:  # noqa: BLE001 - reporting must never reach the run
            self._failure = exc

    def set_lanes(self, lane_of: Mapping[int, tuple[str, int | None]]) -> None:
        """Fill in each delivered survivor's lane from the run's lane split."""
        try:
            for row in self._survivors:
                lane = lane_of.get(int(str(row["posting_id"])))
                if lane is not None:
                    row["lane"] = _lane_name(lane[0])
        except Exception as exc:  # noqa: BLE001 - reporting must never reach the run
            self._failure = self._failure or exc

    def finish(self, day_dir: Path) -> Path | None:
        """Write the file (atomically), or raise what `capture` or `set_lanes` held. None when the
        run never reached the cut."""
        if self._failure is not None:
            raise self._failure
        if self._report is None:
            return None
        day_dir.mkdir(parents=True, exist_ok=True)
        target = day_dir / f"{SLATE_CUT_PREFIX}{self._run_id}.json"
        partial = target.with_suffix(".json.partial")
        partial.write_text(json.dumps(self._report) + "\n", encoding="utf-8")
        partial.replace(target)  # atomic: a reader never sees a half-written file
        return target
