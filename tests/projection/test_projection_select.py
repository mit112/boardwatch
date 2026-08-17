"""Task 23: `select` — admission floor, fallback, budget fit.

`ProjectionPool` and `PostingContext` are constructed directly rather than through
`project_pool`/`posting_context` — both are plain frozen dataclasses (see their own modules),
and `select` needs only their shape, not a real bundle or a real DB-backed posting. This mirrors
`test_projection_scoring.py`'s and `test_projection_agreement.py`'s own `_entry` fixture style:
build the smallest real value that exercises the algorithm, not a parallel construction helper.

`SCORERS["total_distinct"]` is passed explicitly to every `select` call, never as a default —
`select` takes no default scorer (D-163: all four candidates are falsified by one rank-agreement
probe or the other), so a test that wants readable output supplies one itself.
"""

from __future__ import annotations

import re
from decimal import Decimal

import pytest

from boardwatch.extract.taxonomy import Taxonomy, TaxonomyPattern
from boardwatch.projection.errors import ProjectionError, ProjectionIssue
from boardwatch.projection.pool import ProjectionPool
from boardwatch.projection.posting import PostingContext
from boardwatch.projection.scoring import SCORERS
from boardwatch.projection.select import Compiler, _fatal_if_infrastructure, select
from boardwatch.reports.resume_gate import GateReason, GateResult
from boardwatch.tailor.equivalences import EquivalenceTable
from boardwatch.tailor.model import Bullet, Entry, Resume

SCORER = SCORERS["total_distinct"]
TABLE = EquivalenceTable((), "v1")

#: Every token any fixture bullet mentions. A real `Taxonomy.extract` pattern per token, so
#: `effective_skills` finds exactly what the fixture text says and nothing else.
_TOKENS = ("airflow", "snowflake", "spark", "kafka", "swift", "kotlin")


def _taxonomy() -> Taxonomy:
    return Taxonomy(
        patterns=tuple(
            TaxonomyPattern(
                name=t,
                category="tool",
                pattern=t,
                case_sensitive=False,
                regex=re.compile(t, re.IGNORECASE),
            )
            for t in _TOKENS
        ),
        version="select-test-1",
        source="bundled",
    )


TAXONOMY = _taxonomy()


def _entry(entry_id: str, *texts: str) -> Entry:
    return Entry(
        entry_id=entry_id,
        heading=entry_id,
        bullets=[Bullet(bullet_id=f"{entry_id}.{i}", text=t) for i, t in enumerate(texts)],
    )


#: One pinned entry (never scored), four candidates: two data-flavoured, one mobile-flavoured,
#: one that overlaps no JD this file uses at all. `no_match_fallback_ids` names the two data
#: entries, so the "JD matches nothing" case has something distinctive to assert "exactly".
CORE = _entry("entry.core", "Led the platform team")
DATA_1 = _entry("entry.data1", "Built airflow DAGs and snowflake models")
DATA_2 = _entry("entry.data2", "Wrote spark jobs and kafka streams")
MOBILE_1 = _entry("entry.mobile1", "Shipped iOS features in swift and kotlin")
ZERO = _entry("entry.zero", "Organised the office holiday potluck")

POOL = ProjectionPool(
    resume=Resume(
        header=["Example Candidate"],
        education=[],
        skill_groups=[],
        entries=[CORE, DATA_1, DATA_2, MOBILE_1, ZERO],
    ),
    pinned_entry_ids=("entry.core",),
    candidate_entry_ids=("entry.data1", "entry.data2", "entry.mobile1", "entry.zero"),
    no_match_fallback_ids=("entry.data1", "entry.data2"),
    bundle_revision="1",
    bundle_digest="sha256:pool",
    projection_digest="sha256:decl",
)

JD_DATA = frozenset({"airflow", "snowflake", "spark", "kafka"})
JD_MOBILE = frozenset({"swift", "kotlin"})
JD_NONE = frozenset({"cobol"})  # matches no fixture bullet at all


def _context(jd_skills: frozenset[str], *, page_budget: int = 10) -> PostingContext:
    return PostingContext(
        posting_id=1, posting_version_id=1, jd_skills=jd_skills, page_budget=page_budget
    )


def _budget_compiler(budget: int) -> Compiler:
    """One "page" per entry, deterministic and toolchain-free: exactly what a test needs to
    control the compile gate's four arms without a real `LatexRenderer`/tectonic/pdfinfo."""

    def compile_prefix(resume: Resume) -> GateResult:
        page_count = len(resume.entries)
        reason = GateReason.OK if page_count <= budget else GateReason.PAGE_LIMIT_EXCEEDED
        return GateResult(reason, reason is GateReason.OK, None, page_count, "")

    return compile_prefix


# -- required case 1 & 2: different JDs select different candidates; pinned is unmoved -------


def test_different_jds_select_different_candidates_with_an_unmoved_pinned_set() -> None:
    roomy = _budget_compiler(10)
    result_data = select(
        POOL, _context(JD_DATA), SCORER, table=TABLE, taxonomy=TAXONOMY, compile_prefix=roomy
    )
    result_mobile = select(
        POOL, _context(JD_MOBILE), SCORER, table=TABLE, taxonomy=TAXONOMY, compile_prefix=roomy
    )

    assert set(result_data.selected_candidate_ids) == {"entry.data1", "entry.data2"}
    assert set(result_mobile.selected_candidate_ids) == {"entry.mobile1"}
    assert result_data.selected_candidate_ids != result_mobile.selected_candidate_ids

    # The pinned set: byte-identical across both, because it is never scored.
    assert result_data.pinned_entry_ids == result_mobile.pinned_entry_ids == ("entry.core",)
    pinned_from_data = [
        e for e in result_data.resume.entries if e.entry_id in result_data.pinned_entry_ids
    ]
    pinned_from_mobile = [
        e for e in result_mobile.resume.entries if e.entry_id in result_mobile.pinned_entry_ids
    ]
    assert pinned_from_data == pinned_from_mobile == [CORE]


# -- required case 3: a roomy budget still excludes a zero-score candidate --------------------


def test_a_roomy_budget_still_excludes_an_unrelated_zero_score_candidate() -> None:
    """The test revision 1's design was missing: a candidate with NO JD overlap must stay out
    however much room the budget has, because it never clears `ADMISSION_FLOOR` in the first
    place — it never even enters the compile loop."""
    result = select(
        POOL,
        _context(JD_DATA, page_budget=50),
        SCORER,
        table=TABLE,
        taxonomy=TAXONOMY,
        compile_prefix=_budget_compiler(50),
    )
    assert "entry.zero" not in result.selected_candidate_ids


# -- required case 4: a JD matching nothing yields exactly no_match_fallback ------------------


def test_a_jd_matching_nothing_yields_exactly_the_no_match_fallback() -> None:
    result = select(
        POOL,
        _context(JD_NONE),
        SCORER,
        table=TABLE,
        taxonomy=TAXONOMY,
        compile_prefix=_budget_compiler(10),
    )
    assert result.used_fallback is True
    assert result.selected_candidate_ids == POOL.no_match_fallback_ids


def test_used_fallback_is_false_when_the_fallback_list_is_itself_empty() -> None:
    """`used_fallback` means the fallback list was actually consulted, not merely that ranking
    came up empty (M2). With `no_match_fallback_ids=()`, growth has nothing to grow from — a run
    that used no fallback at all — and this must not be misreported as `True`."""
    pool = ProjectionPool(
        resume=Resume(
            header=["Example Candidate"],
            education=[],
            skill_groups=[],
            entries=[CORE, DATA_1, DATA_2],
        ),
        pinned_entry_ids=("entry.core",),
        candidate_entry_ids=("entry.data1", "entry.data2"),
        no_match_fallback_ids=(),
        bundle_revision="1",
        bundle_digest="sha256:pool-no-fallback",
        projection_digest="sha256:decl-no-fallback",
    )
    result = select(
        pool,
        _context(JD_NONE),
        SCORER,
        table=TABLE,
        taxonomy=TAXONOMY,
        compile_prefix=_budget_compiler(10),
    )
    assert result.used_fallback is False
    assert result.selected_candidate_ids == ()


# -- required case 5: COMPILE_FAILED is fatal, fails named, drops nothing --------------------


def _fails_once_grown(resume: Resume) -> GateResult:
    """OK for the pinned-only prefix; `COMPILE_FAILED` the moment anything is added to it — a
    non-zero tectonic exit over the candidate's own content mid-growth, never overflow."""
    if len(resume.entries) <= 1:
        return GateResult(GateReason.OK, True, None, 1, "")
    return GateResult(GateReason.COMPILE_FAILED, False, None, None, "tectonic exploded")


def test_compile_failed_mid_growth_fails_named_and_drops_nothing() -> None:
    with pytest.raises(ProjectionError) as exc_info:
        select(
            POOL,
            _context(JD_DATA),
            SCORER,
            table=TABLE,
            taxonomy=TAXONOMY,
            compile_prefix=_fails_once_grown,
        )
    assert exc_info.value.violation.issue is ProjectionIssue.CANDIDATE_COMPILE_FAILED


# -- task 5b part 1: the two fatal arms are two different faults ------------------------------


def test_a_content_compile_failure_is_not_a_toolchain_failure() -> None:
    """`COMPILE_FAILED` means tectonic exited non-zero — owner content, e.g. an unescaped `%` in a
    bullet. Reporting it as a toolchain fault sends the operator to reinstall a binary that is
    already fine, and because this fires inside the JD-dependent candidate loop it aborts the whole
    run for the postings where one entry happens to be admitted."""
    with pytest.raises(ProjectionError) as exc_info:
        _fatal_if_infrastructure(
            GateResult(GateReason.COMPILE_FAILED, False, None, None, "! Misplaced alignment tab"),
            where="posting:1",
        )
    assert exc_info.value.violation.issue is ProjectionIssue.CANDIDATE_COMPILE_FAILED


def test_a_missing_binary_is_still_a_toolchain_failure() -> None:
    """The other arm must not move: an absent tectonic really is run-scoped."""
    with pytest.raises(ProjectionError) as exc_info:
        _fatal_if_infrastructure(
            GateResult(GateReason.BINARY_MISSING, False, None, None, "tectonic not found"),
            where="posting:1",
        )
    assert exc_info.value.violation.issue is ProjectionIssue.COMPILE_INFRASTRUCTURE_FAILURE


def test_neither_fatal_arm_mentions_a_page_budget() -> None:
    """Both arms keep the "no candidate is dropped on its account" guarantee — neither reason is
    overflow — so neither message may send the operator to `resume_max_pages`. Splitting the issue
    members must not cost that shared property."""
    for reason in (GateReason.COMPILE_FAILED, GateReason.BINARY_MISSING):
        with pytest.raises(ProjectionError) as exc_info:
            _fatal_if_infrastructure(
                GateResult(reason, False, None, None, ""), where="posting:1"
            )
        message = exc_info.value.violation.message
        assert "never budget overflow" in message
        assert "resume_max_pages" not in message


def test_an_ok_gate_is_not_fatal() -> None:
    """The guard fires on exactly two reasons; `OK` and `PAGE_LIMIT_EXCEEDED` fall through to the
    caller's own handling. A split that widened the guard would abort every successful compile."""
    for reason in (GateReason.OK, GateReason.PAGE_LIMIT_EXCEEDED):
        _fatal_if_infrastructure(GateResult(reason, reason is GateReason.OK, None, 1, ""), where="w")


# -- fix round 1, finding 2: BINARY_MISSING, the other fatal arm, was untested ----------------


def _binary_missing_once_grown(resume: Resume) -> GateResult:
    """OK for the pinned-only prefix; `BINARY_MISSING` the moment anything is added — the other
    fatal arm of `_fatal_if_infrastructure`, which since task 5b raises a DIFFERENT issue from
    `COMPILE_FAILED`. A mutation that drops `BINARY_MISSING` from that guard does NOT go undetected
    without this test: `_grow` falls through to `_reject_unless_ok`, whose "anything that is not
    exactly OK" catch-all backs it up and raises the identical `COMPILE_INFRASTRUCTURE_FAILURE`
    regardless. This test still earns its place — it pins the fatal-and-drops-nothing behaviour
    itself — but the guard backstopping a regression here is `_reject_unless_ok`, not this test.
    Dropping the `COMPILE_FAILED` arm, by contrast, IS now caught: the catch-all would report
    `COMPILE_INFRASTRUCTURE_FAILURE` where `CANDIDATE_COMPILE_FAILED` is required."""
    if len(resume.entries) <= 1:
        return GateResult(GateReason.OK, True, None, 1, "")
    return GateResult(GateReason.BINARY_MISSING, False, None, None, "pdfinfo not found")


def test_binary_missing_mid_growth_fails_named_and_drops_nothing() -> None:
    with pytest.raises(ProjectionError) as exc_info:
        select(
            POOL,
            _context(JD_DATA),
            SCORER,
            table=TABLE,
            taxonomy=TAXONOMY,
            compile_prefix=_binary_missing_once_grown,
        )
    assert exc_info.value.violation.issue is ProjectionIssue.COMPILE_INFRASTRUCTURE_FAILURE


# -- fix round 1, finding 1: an unhandled (non-OK, non-fatal, non-overflow) gate reason must
# fail named, never be silently admitted by falling through the compile gate's implicit else ---


def _layout_reason_once_grown(resume: Resume) -> GateResult:
    """OK for the pinned-only prefix; `BULLET_TOO_LONG` the moment anything is added — a
    layout-validation reason that `evaluate_compile` never itself returns (only
    `validate_layout`/`validate_slots` do), but `Compiler = Callable[[Resume], GateResult]`
    types accept any `GateResult`, so a caller could wire one in."""
    if len(resume.entries) <= 1:
        return GateResult(GateReason.OK, True, None, 1, "")
    return GateResult(GateReason.BULLET_TOO_LONG, False, None, None, "bullet exceeds width")


def test_unhandled_gate_reason_mid_growth_fails_named_and_drops_nothing() -> None:
    """A layout-validating compiler's reason must never be admitted by elimination: it is
    neither `OK`, nor a fatal infrastructure arm, nor `PAGE_LIMIT_EXCEEDED`, so it must raise
    rather than fall through the implicit "it fits, keep growing" branch."""
    with pytest.raises(ProjectionError) as exc_info:
        select(
            POOL,
            _context(JD_DATA),
            SCORER,
            table=TABLE,
            taxonomy=TAXONOMY,
            compile_prefix=_layout_reason_once_grown,
        )
    assert exc_info.value.violation.issue is ProjectionIssue.COMPILE_INFRASTRUCTURE_FAILURE


def _always_layout_reason(resume: Resume) -> GateResult:
    return GateResult(GateReason.TOO_MANY_BULLETS, False, None, len(resume.entries), "")


def test_unhandled_gate_reason_on_pinned_only_fails_named() -> None:
    """Same guard, at the pinned-only site: even before any candidate is ranked or scored, a
    layout-validating compiler's reason must fail named rather than pass the pinned prefix
    through as though it fit."""
    with pytest.raises(ProjectionError) as exc_info:
        select(
            POOL,
            _context(JD_DATA),
            SCORER,
            table=TABLE,
            taxonomy=TAXONOMY,
            compile_prefix=_always_layout_reason,
        )
    assert exc_info.value.violation.issue is ProjectionIssue.COMPILE_INFRASTRUCTURE_FAILURE


# -- required case 6: a pinned-only overflow names the typed failure + the knob ---------------


def _always_over_budget(resume: Resume) -> GateResult:
    return GateResult(GateReason.PAGE_LIMIT_EXCEEDED, False, None, len(resume.entries), "")


def test_pinned_only_overflow_reports_the_typed_failure_with_its_knob() -> None:
    with pytest.raises(ProjectionError) as exc_info:
        select(
            POOL,
            _context(JD_DATA),
            SCORER,
            table=TABLE,
            taxonomy=TAXONOMY,
            compile_prefix=_always_over_budget,
        )
    assert exc_info.value.violation.issue is ProjectionIssue.PINNED_SET_EXCEEDS_BUDGET
    assert "resume_max_pages" in exc_info.value.violation.message
    assert "entry.core" in exc_info.value.violation.message


# -- bonus: the algorithm's own compile-count contract ----------------------------------------


def test_growth_stops_at_the_first_overflow_and_drops_only_that_candidate() -> None:
    """Budget for exactly the pinned entry plus one candidate: the ranked order is
    `data1, data2` (both score 2, tied on total_distinct, so declared order — `data1` first in
    `candidate_entry_ids` — decides). `data1` must be admitted; `data2` must be the one dropped,
    not both."""
    result = select(
        POOL,
        _context(JD_DATA, page_budget=2),
        SCORER,
        table=TABLE,
        taxonomy=TAXONOMY,
        compile_prefix=_budget_compiler(2),
    )
    assert result.selected_candidate_ids == ("entry.data1",)


def test_growth_stops_rather_than_skipping_a_lower_ranked_candidate_that_would_fit() -> None:
    """The algorithm's contract is "drop the last-added candidate AND STOP" — not "skip it and
    try the next-ranked one anyway." A uniform per-entry page count cannot distinguish "stop"
    from "skip, keep trying": both give the same admitted set when every entry costs the same.
    A per-entry-weighted compiler can: `entry.data3` (rank 3, weight 0) would fit if tried after
    `entry.data2` (rank 2) overflows, but growth must never reach it."""
    data3 = _entry(
        "entry.data3", "Reviewed airflow logs"
    )  # 1 distinct match: ranks below data1/data2
    pool = ProjectionPool(
        resume=Resume(
            header=["Example Candidate"],
            education=[],
            skill_groups=[],
            entries=[CORE, DATA_1, DATA_2, data3],
        ),
        pinned_entry_ids=("entry.core",),
        candidate_entry_ids=("entry.data1", "entry.data2", "entry.data3"),
        no_match_fallback_ids=(),
        bundle_revision="1",
        bundle_digest="sha256:pool2",
        projection_digest="sha256:decl2",
    )
    weights = {"entry.core": 1, "entry.data1": 1, "entry.data2": 1, "entry.data3": 0}

    def weighted_compiler(resume: Resume) -> GateResult:
        total = sum(weights[e.entry_id] for e in resume.entries)
        reason = GateReason.OK if total <= 2 else GateReason.PAGE_LIMIT_EXCEEDED
        return GateResult(reason, reason is GateReason.OK, None, total, "")

    result = select(
        pool,
        _context(JD_DATA, page_budget=2),
        SCORER,
        table=TABLE,
        taxonomy=TAXONOMY,
        compile_prefix=weighted_compiler,
    )
    assert result.selected_candidate_ids == ("entry.data1",)


def test_at_most_n_plus_one_compiles_never_two_n() -> None:
    calls: list[int] = []

    def counting(resume: Resume) -> GateResult:
        calls.append(len(resume.entries))
        return GateResult(GateReason.OK, True, None, len(resume.entries), "")

    select(POOL, _context(JD_DATA), SCORER, table=TABLE, taxonomy=TAXONOMY, compile_prefix=counting)
    # n = 2 ranked candidates (data1, data2) clear the floor for this JD; 1 pinned-only compile
    # + 2 growth compiles = 3, never `2 * n` (4).
    assert len(calls) == 3


def test_admission_floor_constant_is_zero_and_strict() -> None:
    """Non-vacuity for the floor itself: pinned to `Decimal(0)`, and every registered scorer
    really does return exactly that for a zero-overlap entry against this file's own JD/taxonomy
    — the premise the floor's strictness depends on."""
    from boardwatch.projection.select import ADMISSION_FLOOR

    assert ADMISSION_FLOOR == Decimal(0)
    for scorer in SCORERS.values():
        assert scorer(ZERO, set(JD_DATA), TABLE, TAXONOMY) == Decimal(0)
