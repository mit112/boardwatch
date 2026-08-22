"""Per-board discovery coverage as a six-bucket partition (D-271).

Coverage is NOT one number. A board whose total we cannot obtain gets its own bucket and is
never folded into a neighbour — the same invariant that makes ABSTAIN load-bearing in the
eligibility engine. Folding `enumerated_only` into `measured` would print a ratio that is 100%
by arithmetic on every run forever: lever, ashby, and workable state no total at all, so the
only "total" available for them is our own array length, and held / held cannot ever fail.
`BoardCoverage.__post_init__` enforces the pairing between `bucket` and `ratio` at construction,
the same way `Liveness.__post_init__` (core/liveness.py) enforces verdict/signal pairing —
because `build_report` filters only on `bucket` and never inspects `ratio`, so a caller that
built `enumerated_only` with `ratio=1.0` would sail through undetected.

The global ratio is a weighted roll-up over `measured` ONLY, published beside the counts of the
other five buckets. A `dark` board must not be averaged in as 100% coverage, but it must still
count toward `corpus_boards` — it does not stop being a board we watch just because today's scan
could not read it. Within `measured`, a board stating a total of `0` makes a real claim ("I have
nothing open") and keeps the bucket, but it is excluded from the global roll-up's numerator and
denominator — held postings against a stated total of zero would otherwise inflate the headline
ratio with a denominator contribution of nothing. Excluded boards are counted, not dropped, in
`CoverageReport.measured_zero_total`.

`unscanned` is a SEPARATE bucket from `dark` (fix round 4, finding 1): `dark` means a scan was
attempted this run and failed; `unscanned` means no `board_scans` row exists for this board in
the selected run at all — most commonly because `scan --company X` (`scan/coordinator.py`) mints
a run containing rows for only the filtered subset. Folding the two together would say "this
board failed" about a board that was never touched, and a LEFT JOIN that dropped it instead
would be worse: the board would vanish from `corpus_boards` rather than merely being
misclassified — exactly the leak this partition exists to prevent.

A zero-stated-total board's OWN `ratio` is genuinely undefined — there is no real number for
"postings held against a board that claims to have none" — and `None` is the right word for
that, the same word the four non-measured buckets already use for "no claim". `inf` was
considered and rejected: `json.dumps({"ratio": float("inf")})` emits `{"ratio": Infinity}`,
which RFC 8259 forbids (Python accepts it only as a non-standard extension), and the next
task's `--json` output is a real consumer. Inventing a sentinel to satisfy a type is how a
metric starts lying.

This module has no I/O and no database access. It consumes the coverage columns Task 2 added to
`board_scans` (already resolved to plain values by the caller) and classifies them.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Literal

CoverageBucket = Literal[
    "measured", "enumerated_only", "censored", "dark", "stale", "unscanned"
]

_ALL_BUCKETS: tuple[CoverageBucket, ...] = (
    "measured",
    "enumerated_only",
    "censored",
    "dark",
    "stale",
    "unscanned",
)


class ContradictoryCoverage(Exception):
    """A board's bucket and its ratio disagree — a distinct fault from a bad classification.

    `bucket="enumerated_only"` with `ratio=1.0` is exactly the unfailable-ratio trap this module
    exists to prevent, and nothing downstream inspects `ratio` against `bucket` again once a
    `BoardCoverage` exists. Raising here, at construction, closes the hole for every future
    caller, not only the one who reads the module docstring.
    """

    def __init__(
        self, *, bucket: CoverageBucket, ratio: float | None, board_reported_total: int | None
    ) -> None:
        super().__init__(
            f"bucket {bucket!r} is inconsistent with ratio={ratio!r}, "
            f"board_reported_total={board_reported_total!r}"
        )
        self.bucket = bucket
        self.ratio = ratio
        self.board_reported_total = board_reported_total


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

    def __post_init__(self) -> None:
        if self.bucket == "measured":
            if self.board_reported_total is None:
                consistent = False
            elif self.board_reported_total > 0:
                consistent = self.ratio is not None
            elif self.board_reported_total == 0:
                # The board's own ratio is genuinely undefined (no real number answers "held
                # against a claimed total of zero"), so `ratio=None` is accepted here exactly
                # like the four non-measured buckets below.
                consistent = True
            else:
                # A negative total can only come from a bad parse or a bad scrape — this
                # dataclass exists to turn that impossible combination into a loud construction
                # error, not a number that quietly flows into a report.
                consistent = False
        else:
            consistent = self.ratio is None
        if not consistent:
            raise ContradictoryCoverage(
                bucket=self.bucket,
                ratio=self.ratio,
                board_reported_total=self.board_reported_total,
            )


@dataclass(frozen=True)
class CoverageReport:
    """The whole corpus, partitioned. `global_ratio` covers `measured` boards only; the other
    five buckets are named in `bucket_counts` rather than merged into the ratio's denominator."""

    boards: list[BoardCoverage]
    bucket_counts: dict[CoverageBucket, int]
    measured_held: int
    measured_total: int
    global_ratio: float | None
    corpus_boards: int
    # `measured` boards excluded from the roll-up because their stated total is 0 — visible here
    # rather than silently absorbed into either `measured_total` (as a no-op denominator) or a
    # neighbouring bucket.
    measured_zero_total: int


def classify_board(
    *,
    status: str | None,
    board_reported_total: int | None,
    board_enumerated: int | None,
    held: int,
    censored: bool,
) -> CoverageBucket:
    """Order matters: `unscanned` is checked first because it is a claim about a DIFFERENT run
    dimension than the rest — the caller passes `status=None` to mean "no `board_scans` row
    exists for this board in the selected run", which is not the same fact as `dark` (a row
    exists and its status is `failed`). `dark` and `stale` are then properties of THIS SCAN and
    win over any stored total — a failed or skipped scan tells us nothing new about the board's
    real size, however complete a total it may have reported on some earlier run."""
    if status is None:
        return "unscanned"
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
    # A board stating total == 0 stays `measured` (it is a real claim), but contributes no
    # numerator without a denominator: (500,1000) + (5,0) must roll up to 0.5, never 505/1000.
    ratable = [b for b in measured if (b.board_reported_total or 0) > 0]
    held = sum(b.held for b in ratable)
    total = sum(b.board_reported_total or 0 for b in ratable)
    return CoverageReport(
        boards=boards,
        bucket_counts={bucket: counts.get(bucket, 0) for bucket in _ALL_BUCKETS},
        measured_held=held,
        measured_total=total,
        # None, not 1.0 and not 0.0, when nothing is measurable. An empty average is not full
        # coverage.
        global_ratio=(held / total) if total > 0 else None,
        corpus_boards=len(boards),
        measured_zero_total=len(measured) - len(ratable),
    )
