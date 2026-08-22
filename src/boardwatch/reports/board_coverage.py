"""Per-board discovery coverage as a seven-bucket partition (D-271).

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
other six buckets and beside `censored_shortfall`, the absolute gap the censored boards carry
without a ratio. A `dark` board must not be averaged in as 100% coverage, but it must still
count toward `corpus_boards` — it does not stop being a board we watch just because today's scan
could not read it. Within `measured`, a board stating a total of `0` makes a real claim ("I have
nothing open") and keeps the bucket, but it is excluded from the global roll-up's numerator and
denominator — held postings against a stated total of zero would otherwise inflate the headline
ratio with a denominator contribution of nothing. Excluded boards are counted, not dropped, in
`CoverageReport.measured_zero_total`.

`unscanned` is a SEPARATE bucket from `dark` (fix round 1, finding 1): `dark` means a scan was
attempted this run and failed; `unscanned` means no `board_scans` row exists for this board in
the selected run at all — most commonly because `scan --company X` (`scan/coordinator.py`) mints
a run containing rows for only the filtered subset. Folding the two together would say "this
board failed" about a board that was never touched, and a LEFT JOIN that dropped it instead
would be worse: the board would vanish from `corpus_boards` rather than merely being
misclassified — exactly the leak this partition exists to prevent.

`unreadable` is the seventh bucket and the same argument one step further: a row whose own
columns contradict each other (a negative stated total, a status outside the closed catalog)
cannot be classified at all. Reproduced with a two-board store holding one
`board_reported_total=-5` row: the `ContradictoryCoverage` escaped `load_board_coverage` and
took the WHOLE report down, so the healthy board's number became unreachable — one bad row
hiding the other 134. Degrading that single board is right; degrading it into `dark` or
dropping it would not be, for the reason the paragraph above gives. It publishes no ratio and
no shortfall, and its raw column values are still rendered so the defect is debuggable.

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
from typing import Literal, get_args

from boardwatch.core.models import SnapshotStatus

CoverageBucket = Literal[
    "measured", "enumerated_only", "censored", "dark", "stale", "unscanned", "unreadable"
]

_ALL_BUCKETS: tuple[CoverageBucket, ...] = (
    "measured",
    "enumerated_only",
    "censored",
    "dark",
    "stale",
    "unscanned",
    "unreadable",
)

# The buckets that publish an absolute shortfall. `censored` is here and `measured` is not
# alone: a censored board whose facet sum recovered a real size states a real number to be
# short OF (Citi 600 held against 4,589), and while shortfall was tied to `measured` the
# largest hole in the corpus contributed nothing to any summary line. The RATIO stays
# withheld for `censored` — see `BoardCoverage.__post_init__`.
_SHORTFALL_BUCKETS: tuple[CoverageBucket, ...] = ("measured", "censored")

# Read off the emitter's own type rather than restated here, so a fifth status cannot be added
# to `core/models.SnapshotStatus` (and `store/tables.py`'s matching `status_enum` constraint)
# without this catalog following it.
_SCAN_STATUSES: frozenset[str] = frozenset(get_args(SnapshotStatus))


class ContradictoryCoverage(Exception):
    """A board's bucket disagrees with its ratio or its shortfall — a distinct fault from a
    bad classification.

    `bucket="enumerated_only"` with `ratio=1.0` is exactly the unfailable-ratio trap this module
    exists to prevent, and nothing downstream inspects `ratio` against `bucket` again once a
    `BoardCoverage` exists. Raising here, at construction, closes the hole for every future
    caller, not only the one who reads the module docstring.
    """

    def __init__(
        self,
        *,
        bucket: CoverageBucket,
        ratio: float | None,
        board_reported_total: int | None,
        shortfall: int | None = None,
    ) -> None:
        super().__init__(
            f"bucket {bucket!r} is inconsistent with ratio={ratio!r}, "
            f"shortfall={shortfall!r}, board_reported_total={board_reported_total!r}"
        )
        self.bucket = bucket
        self.ratio = ratio
        self.board_reported_total = board_reported_total
        self.shortfall = shortfall


class UnknownScanStatus(Exception):
    """`board_scans.status` held a value outside its closed catalog.

    The catalog is four values, enforced at the write side by `store/tables.py`'s `status_enum`
    CheckConstraint and typed as `core/models.SnapshotStatus`. A fifth value is a schema or
    ingest defect, and treating it as a good scan — which is what falling through to `measured`
    did — is how an out-of-catalog value becomes a silent new bucket. Typed at the raise site
    so no caller has to classify it by string-matching a message.
    """

    def __init__(self, status: str) -> None:
        super().__init__(
            f"board_scans.status={status!r} is outside the closed catalog "
            f"{sorted(_SCAN_STATUSES)}"
        )
        self.status = status


class UnknownCensorFlag(Exception):
    """`board_scans.board_total_censored` held a value outside its closed tri-state catalog
    `{0, 1, NULL}`.

    Unlike `status`, this column has no CheckConstraint at the schema level (`store/tables.py`'s
    `status_enum` covers `status` only), so nothing at the write side stops a bad value from
    existing. Typed at the raise site for the same reason as `UnknownScanStatus`: it needs a
    name `load_board_coverage`'s except tuple can catch specifically, rather than a bare
    `ValueError` broad enough to also swallow an unrelated bug.
    """

    def __init__(self, value: int) -> None:
        super().__init__(
            f"board_scans.board_total_censored={value!r} is outside the closed tri-state "
            f"catalog {{0, 1, NULL}}"
        )
        self.value = value


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
                ratio_ok = False
            elif self.board_reported_total > 0:
                ratio_ok = self.ratio is not None
            elif self.board_reported_total == 0:
                # The board's own ratio is genuinely undefined (no real number answers "held
                # against a claimed total of zero"), so `ratio=None` is REQUIRED here, exactly
                # as in the non-measured buckets below. Accepting any ratio at exactly zero was
                # the one input this guard still let past: `total=0, ratio=0.7` constructed
                # cleanly and published a number nothing supports.
                ratio_ok = self.ratio is None
            else:
                # A negative total can only come from a bad parse or a bad scrape — this
                # dataclass exists to turn that impossible combination into a loud construction
                # error, not a number that quietly flows into a report.
                ratio_ok = False
        else:
            ratio_ok = self.ratio is None
        # A shortfall is an absolute gap, so it needs a stated total to be a gap FROM, and it
        # is carried by `censored` as well as `measured` (see `_SHORTFALL_BUCKETS`). Both
        # directions are pinned: a bucket that cannot support one must not carry one, and a
        # bucket that can must not silently omit it — an omitted shortfall is what kept Citi's
        # 3,989-posting hole out of every summary line.
        expects_shortfall = (
            self.bucket in _SHORTFALL_BUCKETS and self.board_reported_total is not None
        )
        shortfall_ok = (self.shortfall is not None) == expects_shortfall
        if not (ratio_ok and shortfall_ok):
            raise ContradictoryCoverage(
                bucket=self.bucket,
                ratio=self.ratio,
                board_reported_total=self.board_reported_total,
                shortfall=self.shortfall,
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
    # Total postings the `censored` boards are short of their facet-recovered totals. Reported
    # because those boards publish NO ratio and so contribute nothing to `global_ratio`: Citi
    # alone is 600 held against 4,589, the largest single hole in the corpus, and it appeared
    # in no summary line at all. `None` — not 0 — when no censored board recovered a total:
    # a floor with no number is an unknown gap, and 0 would read as "no gap".
    censored_shortfall: int | None


def classify_board(
    *,
    status: str | None,
    board_reported_total: int | None,
    censored: bool,
) -> CoverageBucket:
    """Order matters: `unscanned` is checked first because it is a claim about a DIFFERENT run
    dimension than the rest — the caller passes `status=None` to mean "no `board_scans` row
    exists for this board in the selected run", which is not the same fact as `dark` (a row
    exists and its status is `failed`). `dark` and `stale` are then properties of THIS SCAN and
    win over any stored total — a failed or skipped scan tells us nothing new about the board's
    real size, however complete a total it may have reported on some earlier run.

    `board_enumerated` and `held` were parameters here and were read by nothing; a caller could
    pass either one wrong and no behaviour changed. Deleted rather than left as a signature
    that implies they steer the verdict.

    Raises `UnknownScanStatus` for a status outside the closed catalog: `complete` and
    `partial` are the only remaining values, and every OTHER value used to fall through to
    exactly the same place they do.
    """
    if status is None:
        return "unscanned"
    if status not in _SCAN_STATUSES:
        raise UnknownScanStatus(status)
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
    censored_gaps = [
        b.shortfall for b in boards if b.bucket == "censored" and b.shortfall is not None
    ]
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
        censored_shortfall=sum(censored_gaps) if censored_gaps else None,
    )
