"""Project duplicate suppression onto canonical jobs (P6 slice 2, design §3).

Pure: no DB, no clock. Slice 1 annotated — identities stored beside the data, suppression
resolved at read time, `postings.job_id` untouched (D-079). This is the projection Slice 2 owes,
and the reason it is worth doing is not "so the read path gets simpler":

    Slice 1's suppression is completeness-gated, and D-098 established that completeness is the
    exceptional state. Discover one new posting anywhere in the corpus and suppression switches
    off — at which point a duplicate of an already-built job carries no disposition of its own
    and is built a second time. Regrouping makes the grouping durable in the data, so a
    disposition on one member covers the group whether or not the read-time gate is open.

There is no second survivor election here. The canonical job is the job of the survivor
`resolve_duplicates` already elected under D-086 `(host_class, first_seen_at, posting_id)`, so a
regrouping can never disagree with a suppression about which row is authoritative.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from boardwatch.core.dedup import Suppression

# Closed catalog. An out-of-catalog refusal is a failure, never a new bucket.
REGROUP_REFUSALS: tuple[str, ...] = ("tracked_job", "missing_job_anchor")


@dataclass(frozen=True)
class JobMerge:
    """One posting moving from its own job onto the group's canonical job."""

    posting_id: int
    from_job_id: int
    to_job_id: int


@dataclass(frozen=True)
class Refusal:
    """A group left ungrouped, named so it can be reported. A refusal that is invisible is a
    leak in the same way a suppression that cannot be listed is."""

    survivor_posting_id: int
    reason: str
    member_posting_ids: tuple[int, ...]


@dataclass(frozen=True)
class RegroupPlan:
    merges: tuple[JobMerge, ...]
    refusals: tuple[Refusal, ...]


def plan_regrouping(
    suppressions: Sequence[Suppression],
    job_by_posting: Mapping[int, int],
    *,
    protected_job_ids: frozenset[int],
) -> RegroupPlan:
    """Which postings move onto which canonical job, and which groups are refused.

    `protected_job_ids` are jobs carrying an `applications` or `artifacts` row. A group is
    refused **whole** when any non-survivor member sits on one.

    Why the whole group and not just the offending member: a partially-merged group is a third
    state — some members canonical, some not — that nothing downstream understands, and it makes
    the result depend on iteration order. Refusing is also the only safe direction, because
    `store/run_funnel_queries.py` and `reports/export.py` both reach applications through
    `applications.job_id == postings.job_id`; a merged loser job keeps its application row but
    loses every posting pointing at it, so a real applied count silently becomes wrong.

    Idempotent: a member already sitting on the canonical job yields no merge, so a second pass
    over an unchanged corpus plans nothing.
    """
    groups: dict[int, list[int]] = defaultdict(list)
    for suppression in suppressions:
        groups[suppression.survivor_posting_id].append(suppression.posting_id)

    merges: list[JobMerge] = []
    refusals: list[Refusal] = []
    for survivor_id, loser_ids in sorted(groups.items()):
        members = (survivor_id, *sorted(loser_ids))
        canonical = job_by_posting.get(survivor_id)
        # `postings.job_id` is NOT NULL by trigger and measured 0 NULLs live, so an absent
        # anchor is a data-integrity violation. Reported as a refusal rather than raised: this
        # runs inside a pipeline stage, and a corrupt row must not take the run down — but it
        # must not vanish either, which a silent `continue` would do.
        if canonical is None or any(job_by_posting.get(pid) is None for pid in loser_ids):
            refusals.append(Refusal(survivor_id, "missing_job_anchor", members))
            continue
        moving = [
            (pid, job_by_posting[pid]) for pid in sorted(loser_ids)
            if job_by_posting[pid] != canonical
        ]
        if any(job_id in protected_job_ids for _, job_id in moving):
            refusals.append(Refusal(survivor_id, "tracked_job", members))
            continue
        merges.extend(
            JobMerge(posting_id=pid, from_job_id=job_id, to_job_id=canonical)
            for pid, job_id in moving
        )
    return RegroupPlan(merges=tuple(merges), refusals=tuple(refusals))
