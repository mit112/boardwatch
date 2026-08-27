"""`boardwatch identities leakage` — Gate P6's "duplicate leakage over 7 days <= 5%" clause.

There is a corpus-wide dup rate already visible through `identities backfill`/`regroup`
output, and it is NOT what this measures — it is large and answers a different question
("how much of the stored corpus is duplicated"). This answers "of the postings that actually
reached the operator, how many were a duplicate of another one that ALSO reached the
operator" — the only thing the gate's "leaked" wording can mean, since a duplicate the
ranker suppressed before it ever surfaced never leaked anything.

**Only `exact_quad` counts as a duplicate**, per the owner's ruling (D-132/identity_kinds.py):
the catalog's other kinds are explicitly non-suppressing, and a hash-only or
company-title-location match routinely spans genuinely different jobs (727 of 809 measured
groups).

**The wider class is nonetheless MEASURED, as a separate bound that is never folded in.**
`store/identity_queries.py` used to hardcode `exact_quad`, so a job whose only identity was
`company_title_location` landed in `unidentified` and could never be counted redundant — the
rate read 0.00% for a structural reason rather than because dedup works, and CLAUDE.md is
explicit that a rule which cannot fire is a monitoring failure. So the report now carries a
second bucket, `candidate_*`, on `company_title_location`.

It is an **upper bound, not a duplicate count.** Hand-adjudicated on 2026-08-27: of 17 such
groups among the 601 jobs that reached leads in the window, **3 were true duplicates and 14
were genuinely different jobs** (Affirm's three pay-band pairs, Adobe Stock vs observability
tooling, Cisco 8000 vs the DSE group, …), and on a random corpus sample the split was 10 true
of 30. Suppressing on this key would delete four real leads per duplicate collapsed, which is
why `SUPPRESSING_KINDS` is unchanged and nothing here feeds `core/dedup`.

`core/near_duplicate` narrows the bound by removing groups that carry PROOF of distinctness —
disjoint pay bands, disjoint years floors, or a differing requisition slug in the posting's own
URL. That veto is the only thing that can make the bound smaller, so it fires only on proof:
see that module for the direction-of-failure argument.

**The unit that "reached leads" is a JOB, not a posting.** `job_dispositions` is keyed on
`job_id` (one row per job, upserted — `store/tables.py`), and `pipeline/runner.py` /
`cli/top_cmd.py` write a row there for exactly the jobs surfaced to the operator: `seen`
(shown), `skipped` (tailoring couldn't ship it) or `built` (a resume exists) all mean
"the operator saw this". Two POSTINGS that share an `exact_quad` identity and were correctly
merged by `identities regroup` end up anchored to the SAME job — one job_dispositions row,
one thing the operator saw — and must not be counted as a leak just because two posting rows
sit under it. A leak is when the SAME identity is split across two DIFFERENT jobs that both
reached leads, which is exactly what happens when the ranker's dedup and `regroup` have not
(yet) caught the pairing.

**The window is anchored on `first_decided_at`**, not on posting or run timestamps: it is the
moment a job first became a lead, so a job first surfaced 30 days ago that merely had its
`seen` TTL refreshed inside the last 7 does not read as a fresh surfacing event. This is a
judgement call — the alternative (posting `first_seen_at`, or `decided_at`'s TTL-refresh
timestamp) is defensible too; see the CLI docstring for what to confirm.

`identities regroup` can also move this timestamp: when a merge's survivor job has no
disposition row of its own, `store/regroup.py::_carry_dispositions` stamps its
`first_decided_at` at the merge's `now` rather than the loser's original surfacing time
(`core/ledger.py::plan_upsert`'s missing-row branch) — so window membership can depend on when
`regroup` last ran, not only on when the job first reached leads.

**Body-less/unidentified postings are their own bucket, never folded into either
neighbour** (CLAUDE.md: folding a bucket into a neighbour is a defect). A job with no
identified posting under it is `unidentified` and is excluded from both the numerator and
the denominator — the keystone invariant's ABSTAIN-shaped reasoning applied here: "this
posting has no suppressing identity" is not evidence it is unique.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import Engine

from boardwatch.core.clock import utcnow
from boardwatch.core.near_duplicate import PostingEvidence, distinguishing_evidence
from boardwatch.store.identity_queries import (
    SurfacedJob,
    load_near_duplicate_evidence,
    load_surfaced_exact_quad,
    load_surfaced_keys,
    load_surfaced_posting_ids,
)

DEFAULT_WINDOW_DAYS = 7

# The wider key the candidate bound is measured on. Not `SUPPRESSING_KINDS` and deliberately
# not configurable: `cross_host` cannot dereference an aggregator to exact evidence yet
# (design §3.1) and `content_hash_only` demonstrably collapses different jobs.
CANDIDATE_KIND = "company_title_location"


@dataclass(frozen=True)
class CandidateGroup:
    """Surfaced jobs sharing one `company_title_location` key, and any proof they differ.

    `distinguished` is non-empty only when EVERY pair in the group carries proof. A partially
    distinguished group stays whole on purpose: splitting it would let an unproven pair out of
    the bound, and the bound's only claim is that the real figure is no higher than it.
    """

    identity_key: str
    jobs: tuple[SurfacedJob, ...]
    distinguished: tuple[str, ...] = ()


@dataclass(frozen=True)
class LeakageReport:
    """Gate P6's leakage rate, with the denominator and bucket sizes that make it meaningful.

    `unidentified` is reported, never subtracted silently and never added to `identified` —
    a ratio without its match rule and corpus size is meaningless (CLAUDE.md), so every
    renderer of this report states `window_days`, `identified` (the denominator) and
    `unidentified` (what was excluded and why) alongside the rate.
    """

    window_days: int
    # Every job that reached leads in the window, identified or not.
    surfaced_total: int
    # Reached leads, but no current posting under the job carries an exact_quad identity.
    unidentified: int
    # surfaced_total - unidentified: the denominator for `rate`.
    identified: int
    # Distinct exact_quad identity keys among `identified`.
    distinct_groups: int
    # identified - distinct_groups: redundant surfacings — the numerator for `rate`.
    redundant: int
    # --- the candidate near-duplicate bound. Its own bucket, never folded into the above. ---
    candidate_kind: str
    # DISTINCT jobs that reached leads in the window AND carry an identity of `candidate_kind`.
    candidate_identified: int
    # Candidate groups, counting a fully-distinguished group as one group PER JOB.
    candidate_groups: int
    # The bound's numerator, summed per group. NOT `identified - groups`: a job carrying two
    # keys sits in two groups, and that subtraction can then go negative.
    candidate_redundant: int
    # Redundant surfacings `core/near_duplicate` proved distinct and removed from the bound.
    candidate_distinguished: int

    @property
    def rate(self) -> float | None:
        """None over zero identified jobs — "not measurable", never 0% or 100%."""
        return None if self.identified == 0 else self.redundant / self.identified

    @property
    def candidate_rate(self) -> float | None:
        """An UPPER BOUND on near-duplicate leakage, not a duplicate rate. Same "not
        measurable" rule as `rate` — nothing to measure is never 0%."""
        return (
            None
            if self.candidate_identified == 0
            else self.candidate_redundant / self.candidate_identified
        )


def compute_leakage(
    jobs: Sequence[SurfacedJob],
    *,
    candidates: Sequence[CandidateGroup],
    now: datetime,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> LeakageReport:
    """Pure aggregation over every surfaced job the store knows about.

    Windowing lives here, not in the query, mirroring `reports/stats.summarize`'s split
    between a dumb store read and the one place window logic lives — so there is exactly one
    definition of "in the window" for a reader to disagree with. Both halves share the one
    cutoff, so a job cannot be inside one bucket and outside the other.

    `candidates` is required, not defaulted. A default of `()` would silently report a zero
    candidate bound for any caller that forgot it, and "zero" is the direction that makes the
    gate easier to pass.
    """
    cutoff = now - timedelta(days=window_days)
    in_window = [job for job in jobs if job.first_decided_at >= cutoff]
    identified = [job for job in in_window if job.identity_key is not None]
    unidentified = len(in_window) - len(identified)
    distinct_groups = len({job.identity_key for job in identified})
    redundant = len(identified) - distinct_groups

    windowed = [
        (group, [job for job in group.jobs if job.first_decided_at >= cutoff])
        for group in candidates
    ]
    live = [(group, members) for group, members in windowed if members]
    # DISTINCT jobs. `load_surfaced_keys` returns one row per key, so a job carrying two keys
    # sits in two groups — deliberately, because that inflates the NUMERATOR. Counting it
    # twice here as well would inflate the denominator too and DILUTE the rate, and the bound
    # is only allowed to be wrong upwards.
    candidate_identified = len({job.job_id for _, members in live for job in members})
    # A group proven distinct throughout counts as one group per job — nothing in it is
    # redundant. Everything else counts as one group, so its extra jobs stay in the bound.
    candidate_groups = sum(len(members) if group.distinguished else 1 for group, members in live)
    # Group-local, not `identified - groups`: with a job under two keys that subtraction can go
    # NEGATIVE, and a negative leakage rate is not a number anyone can act on.
    candidate_redundant = sum(
        0 if group.distinguished else len(members) - 1 for group, members in live
    )
    candidate_distinguished = sum(
        len(members) - 1 for group, members in live if group.distinguished
    )
    return LeakageReport(
        window_days=window_days,
        surfaced_total=len(in_window),
        unidentified=unidentified,
        identified=len(identified),
        distinct_groups=distinct_groups,
        redundant=redundant,
        candidate_kind=CANDIDATE_KIND,
        candidate_identified=candidate_identified,
        candidate_groups=candidate_groups,
        candidate_redundant=candidate_redundant,
        candidate_distinguished=candidate_distinguished,
    )


def build_candidate_groups(
    surfacings: Sequence[SurfacedJob],
    posting_ids: Mapping[int, Sequence[int]],
    evidence: Mapping[int, PostingEvidence],
) -> tuple[CandidateGroup, ...]:
    """Group surfaced jobs by candidate key and mark the groups that are provably distinct.

    Pure, so the veto's arithmetic is testable without a database. A job with no candidate
    identity is not a candidate at all and simply does not appear — it is already counted in
    the `unidentified` bucket and must not be folded in here either.

    A group is marked distinguished only when every pair of its jobs carries proof, and a job
    with no readable evidence proves nothing — both keep the group inside the bound.

    The proof is computed over the whole group, before `compute_leakage` applies the window.
    So a group whose only unproven pair involves an out-of-window job stays in the bound even
    though its in-window members are provably distinct. That asymmetry only ever raises the
    bound, which is the direction it is allowed to be wrong in.
    """
    grouped: dict[str, list[SurfacedJob]] = {}
    for job in surfacings:
        if job.identity_key is not None:
            grouped.setdefault(job.identity_key, []).append(job)
    out: list[CandidateGroup] = []
    for key in sorted(grouped):
        members = grouped[key]
        proof: tuple[str, ...] = ()
        if len(members) > 1:
            proof = _group_proof(members, posting_ids, evidence)
        out.append(CandidateGroup(identity_key=key, jobs=tuple(members), distinguished=proof))
    return tuple(out)


def _group_proof(
    members: Sequence[SurfacedJob],
    posting_ids: Mapping[int, Sequence[int]],
    evidence: Mapping[int, PostingEvidence],
) -> tuple[str, ...]:
    """Discriminators proving EVERY pair in the group is a different opening, or nothing.

    A job can anchor several postings; the pair is proven only when every posting of one job
    is proven against every posting of the other, so one ambiguous posting keeps the whole
    group in the bound.
    """
    names: list[str] = []
    for i, left in enumerate(members):
        for right in members[i + 1 :]:
            pair = _pair_proof(left, right, posting_ids, evidence)
            if not pair:
                return ()
            names.extend(pair)
    return tuple(dict.fromkeys(names))


def _pair_proof(
    left: SurfacedJob,
    right: SurfacedJob,
    posting_ids: Mapping[int, Sequence[int]],
    evidence: Mapping[int, PostingEvidence],
) -> tuple[str, ...]:
    lefts = [evidence[p] for p in posting_ids.get(left.job_id, ()) if p in evidence]
    rights = [evidence[p] for p in posting_ids.get(right.job_id, ()) if p in evidence]
    if not lefts or not rights:
        return ()
    names: list[str] = []
    for a in lefts:
        for b in rights:
            pair = distinguishing_evidence(a, b)
            if not pair:
                return ()
            names.extend(pair)
    return tuple(dict.fromkeys(names))


def compute_leakage_report(
    engine: Engine, *, window_days: int = DEFAULT_WINDOW_DAYS, now: datetime | None = None
) -> LeakageReport:
    """I/O wrapper: read every surfaced job from the store, then hand off to the pure core."""
    when = now if now is not None else utcnow()
    with engine.connect() as conn:
        jobs = load_surfaced_exact_quad(conn)
        surfacings = load_surfaced_keys(conn, kind=CANDIDATE_KIND)
        anchored = load_surfaced_posting_ids(conn)
        wanted = sorted({p for job in surfacings for p in anchored.get(job.job_id, ())})
        evidence = {e.posting_id: e for e in load_near_duplicate_evidence(conn, wanted)}
    candidates = build_candidate_groups(surfacings, anchored, evidence)
    return compute_leakage(jobs, candidates=candidates, now=when, window_days=window_days)
