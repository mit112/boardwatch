"""Per-board discovery coverage as a five-bucket partition (D-271).

Coverage is NOT one number. A board whose total we cannot obtain gets its own bucket and is
never folded into a neighbour — the same invariant that makes ABSTAIN load-bearing in the
eligibility engine. Folding `enumerated_only` into `measured` would print a ratio that is 100%
by arithmetic on every run forever: lever, ashby, and workable state no total at all, so the
only "total" available for them is our own array length, and held / held cannot ever fail.

The global ratio is a weighted roll-up over `measured` ONLY, published beside the counts of the
other four buckets. A `dark` board must not be averaged in as 100% coverage, but it must still
count toward `corpus_boards` — it does not stop being a board we watch just because today's scan
could not read it.

This module has no I/O and no database access. It consumes the coverage columns Task 2 added to
`board_scans` (already resolved to plain values by the caller) and classifies them.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Literal

CoverageBucket = Literal["measured", "enumerated_only", "censored", "dark", "stale"]

_ALL_BUCKETS: tuple[CoverageBucket, ...] = (
    "measured",
    "enumerated_only",
    "censored",
    "dark",
    "stale",
)


@dataclass(frozen=True)
class BoardCoverage:
    """One board's coverage verdict for one scan."""

    company_id: int
    name: str
    provider: str
    bucket: CoverageBucket
    held: int
    board_reported_total: int | None
    board_enumerated: int | None
    detail_deferred: int | None
    # Absolute, signed, and reported BESIDE the ratio: a 1-posting shortfall on a 1,129-posting
    # board is 99.91% and reads as noise, but it is a real parse defect. Negative means we hold
    # more than the board currently states — see test_over_full_coverage_is_reported_not_clamped.
    shortfall: int | None
    ratio: float | None


@dataclass(frozen=True)
class CoverageReport:
    """The whole corpus, partitioned. `global_ratio` covers `measured` boards only; the other
    four buckets are named in `bucket_counts` rather than merged into the ratio's denominator."""

    boards: list[BoardCoverage]
    bucket_counts: dict[CoverageBucket, int]
    measured_held: int
    measured_total: int
    global_ratio: float | None
    corpus_boards: int


def classify_board(
    *,
    status: str,
    board_reported_total: int | None,
    board_enumerated: int | None,
    held: int,
    censored: bool,
) -> CoverageBucket:
    """Order matters: dark and stale are properties of THIS SCAN and win over any stored total —
    a failed or skipped scan tells us nothing new about the board's real size, however complete
    a total it may have reported on some earlier run."""
    if status == "failed":
        return "dark"
    if status == "unchanged":
        return "stale"
    if censored:
        return "censored"
    if board_reported_total is None:
        return "enumerated_only"
    return "measured"


def build_report(boards: list[BoardCoverage]) -> CoverageReport:
    counts = Counter(b.bucket for b in boards)
    measured = [b for b in boards if b.bucket == "measured"]
    held = sum(b.held for b in measured)
    total = sum(b.board_reported_total or 0 for b in measured)
    return CoverageReport(
        boards=boards,
        bucket_counts={bucket: counts.get(bucket, 0) for bucket in _ALL_BUCKETS},
        measured_held=held,
        measured_total=total,
        # None, not 1.0 and not 0.0, when nothing is measurable. An empty average is not full
        # coverage.
        global_ratio=(held / total) if total > 0 else None,
        corpus_boards=len(boards),
    )
