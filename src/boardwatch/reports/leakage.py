"""`boardwatch identities leakage` — Gate P6's "duplicate leakage over 7 days <= 5%" clause.

There is a corpus-wide dup rate already visible through `identities backfill`/`regroup`
output, and it is NOT what this measures — it is large and answers a different question
("how much of the stored corpus is duplicated"). This answers "of the postings that actually
reached the operator, how many were a duplicate of another one that ALSO reached the
operator" — the only thing the gate's "leaked" wording can mean, since a duplicate the
ranker suppressed before it ever surfaced never leaked anything.

**Only `exact_quad` counts**, per the owner's ruling (D-132/identity_kinds.py): the catalog's
other kinds are explicitly non-suppressing, and a hash-only or company-title-location match
routinely spans genuinely different jobs (727 of 809 measured groups).

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

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import Engine

from boardwatch.core.clock import utcnow
from boardwatch.store.identity_queries import SurfacedJob, load_surfaced_exact_quad

DEFAULT_WINDOW_DAYS = 7


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

    @property
    def rate(self) -> float | None:
        """None over zero identified jobs — "not measurable", never 0% or 100%."""
        return None if self.identified == 0 else self.redundant / self.identified


def compute_leakage(
    jobs: Sequence[SurfacedJob], *, now: datetime, window_days: int = DEFAULT_WINDOW_DAYS
) -> LeakageReport:
    """Pure aggregation over every surfaced job the store knows about.

    Windowing lives here, not in the query, mirroring `reports/stats.summarize`'s split
    between a dumb store read and the one place window logic lives — so there is exactly one
    definition of "in the window" for a reader to disagree with.
    """
    cutoff = now - timedelta(days=window_days)
    in_window = [job for job in jobs if job.first_decided_at >= cutoff]
    identified = [job for job in in_window if job.identity_key is not None]
    unidentified = len(in_window) - len(identified)
    distinct_groups = len({job.identity_key for job in identified})
    redundant = len(identified) - distinct_groups
    return LeakageReport(
        window_days=window_days,
        surfaced_total=len(in_window),
        unidentified=unidentified,
        identified=len(identified),
        distinct_groups=distinct_groups,
        redundant=redundant,
    )


def compute_leakage_report(
    engine: Engine, *, window_days: int = DEFAULT_WINDOW_DAYS, now: datetime | None = None
) -> LeakageReport:
    """I/O wrapper: read every surfaced job from the store, then hand off to the pure core."""
    when = now if now is not None else utcnow()
    with engine.connect() as conn:
        jobs = load_surfaced_exact_quad(conn)
    return compute_leakage(jobs, now=when, window_days=window_days)
