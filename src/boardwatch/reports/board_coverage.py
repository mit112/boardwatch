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
from dataclasses import asdict, dataclass
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
    six buckets are named in `bucket_counts` rather than merged into the ratio's denominator."""

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


# --- Reporting surfaces -----------------------------------------------------
#
# The instrument above was mute: `boardwatch coverage` had to be typed by hand, so a scheduled
# run persisted its four columns and reported nothing. These renderers exist so the funnel and
# the morning artifact can each show the SAME report object without either one recomputing it.
# Recomputing would not merely duplicate work — `held` is a live count of open postings with no
# run dimension, so two loads seconds apart can legitimately disagree, and two artifacts from
# one run disagreeing about coverage is worse than neither reporting it.

# Stated in both artifacts' JSON, not only in their prose, so a machine consumer reads the same
# caveat the CLI prints in its footer. `held` is counted straight out of `postings` and is not
# scoped to a run (store/coverage_queries.py), so a stamped section is accurate as of the moment
# it was written and is NOT a historical record of the run it is stamped into.
HELD_NOTE = (
    "stated totals are this run's; `held` is a live count of open postings and has no run "
    "dimension, so this section describes the store as of the moment the artifact was written, "
    "not a frozen record of the run"
)

# `total` arrives in the same response as the array it describes, so it is the board's own claim
# and never an independent audit of it. The word is load-bearing: calling it independent is one
# of the eight ways this metric could lie (design §3.3).
_STATED = "board-stated"


def board_coverage_to_dict(report: CoverageReport | None) -> dict[str, object] | None:
    """`None` — never a dict of zeros — when the report could not be built.

    A zeroed dict would claim every board was measured at nothing, which is the opposite of
    "we did not measure". Keys mirror `boardwatch coverage --json` exactly so the artifact and
    the command cannot drift into describing the same numbers differently.
    """
    if report is None:
        return None
    return {
        "bucket_counts": dict(report.bucket_counts),
        "measured_held": report.measured_held,
        "measured_total": report.measured_total,
        "measured_zero_total": report.measured_zero_total,
        "global_ratio": report.global_ratio,
        "censored_shortfall": report.censored_shortfall,
        "corpus_boards": report.corpus_boards,
        "boards": [asdict(board) for board in report.boards],
        "note": HELD_NOTE,
    }


def _ratio_text(ratio: float | None) -> str:
    """`—`, never `0.0%`: no ratio means no claim, and a printed zero is a claim."""
    return "—" if ratio is None else f"{100 * ratio:.1f}%"


def _count_text(value: int | None) -> str:
    return "—" if value is None else f"{value:,}"


def board_coverage_headline(report: CoverageReport | None) -> list[str]:
    """The run-level roll-up as markdown lines, shared verbatim by both artifacts.

    Every line is emitted unconditionally, including the ones that read as "nothing to report".
    A "0" line is evidence the check ran; an absent line is ambiguous between "checked, found
    none" and "never checked" — the same reason `coverage_cmd.py` prints its notes at zero.
    """
    if report is None:
        # No trailing blank line here would merge this into whatever the caller appends next,
        # which is a `Per-board detail:` line in the morning artifact. The measured branch below
        # ends with one for the same reason.
        #
        # "the load failed OR was never attempted" rather than a flat "failed": `None` also
        # reaches here when a caller omits the argument entirely, and in that case no
        # `! board coverage not measured:` line was ever printed. Naming only the cause that
        # leaves a log line would send a reader looking for an entry that is not there.
        return [
            "**not measured this run** — the coverage load failed or was never attempted. A "
            "failed load prints `! board coverage not measured:` in the run log; nothing is "
            "logged when the report was simply not requested.",
            "",
        ]
    ratio = (
        "**not measurable**"
        if report.global_ratio is None
        else f"**{100 * report.global_ratio:.1f}%**"
    )
    lines = [
        f"{ratio} — {report.measured_held:,} held of {report.measured_total:,} {_STATED} "
        f"postings, across the {report.bucket_counts['measured']} of {report.corpus_boards} "
        "watched boards that state a total we can trust.",
        "",
        " · ".join(f"{bucket} {count}" for bucket, count in report.bucket_counts.items()),
        "",
        f"*The ratio covers `measured` boards only. The other six buckets are counted above "
        f"and never folded into it — a `dark` board is a board we could not read, not a board "
        f"with no jobs. `{_STATED}` is the board's own claim, arriving in the same response as "
        f"the listing it describes; it is not an independent audit of it.*",
        "",
    ]
    lines.append(
        f"- **{report.measured_zero_total}** measured board(s) state a total of 0 and are "
        "excluded from that ratio's numerator and denominator, not folded into it."
    )
    censored = report.bucket_counts["censored"]
    if report.censored_shortfall is None:
        lines.append(
            f"- **{censored}** censored board(s) recovered no uncapped total, so their "
            "shortfall is UNKNOWN, not zero. No ratio is published for them."
        )
    else:
        lines.append(
            f"- **{censored}** censored board(s) are short **{report.censored_shortfall:,}** "
            "postings against their facet-recovered totals. No ratio is published for them, "
            "so they contribute nothing to the figure above — these are the largest known "
            "holes in the corpus."
        )
    lines += ["", f"*{HELD_NOTE}.*", ""]
    return lines


def board_coverage_table(report: CoverageReport | None) -> list[str]:
    """Every watched board, worst measurable coverage first. Boards with no ratio sort after
    every real ratio, in the order they arrived — `is not None`, not truthiness, so a genuine
    0.0% sorts with the real ratios instead of joining the no-claim boards at the bottom."""
    if report is None:
        return []
    lines = [
        "| ratio | bucket | board | held | stated | shortfall | deferred |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for board in sorted(
        report.boards,
        key=lambda b: (b.ratio is None, b.ratio if b.ratio is not None else 0.0),
    ):
        shortfall = "—" if board.shortfall is None else f"{board.shortfall:+,}"
        lines.append(
            f"| {_ratio_text(board.ratio)} | {board.bucket} | "
            f"{board.provider}:{board.name} | {board.held:,} | "
            f"{_count_text(board.board_reported_total)} | {shortfall} | "
            f"{_count_text(board.detail_deferred)} |"
        )
    lines.append("")
    return lines
