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

import dataclasses
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


def test_an_attributable_compile_failure_is_not_a_toolchain_failure() -> None:
    """A `COMPILE_FAILED` whose prefix ADDED a candidate is attributable to that candidate: the same
    document without it compiled moments earlier. Reporting it as a toolchain fault sends the
    operator to reinstall a binary that is already fine, and because this fires inside the
    JD-dependent candidate loop it aborts the whole run for the postings where that entry is
    admitted. Note the claim is attribution, NOT cause — `COMPILE_FAILED` cannot tell content from
    environment (`reports/resume_gate.py:87-90`)."""
    with pytest.raises(ProjectionError) as exc_info:
        _fatal_if_infrastructure(
            GateResult(GateReason.COMPILE_FAILED, False, None, None, "! Misplaced alignment tab"),
            where="posting:1",
            candidate="proj-x",
        )
    assert exc_info.value.violation.issue is ProjectionIssue.CANDIDATE_COMPILE_FAILED
    # The entry is named, because naming it is the whole of the claim being made.
    assert "proj-x" in exc_info.value.violation.message


def test_an_unattributable_compile_failure_is_run_scoped() -> None:
    """The pinned-only base compile passes `candidate=None`: nothing smaller has compiled, so the
    environment and the pinned content are equally implicated and neither can be singled out. Fatal
    is right for both readings, and the pinned set is frozen anyway. Its own member rather than
    `COMPILE_INFRASTRUCTURE_FAILURE`, whose availability member would tell the operator to reinstall
    a tectonic that just ran."""
    with pytest.raises(ProjectionError) as exc_info:
        _fatal_if_infrastructure(
            GateResult(GateReason.COMPILE_FAILED, False, None, None, "! Undefined control sequence"),
            where="posting:1",
            candidate=None,
        )
    assert exc_info.value.violation.issue is ProjectionIssue.PINNED_SET_COMPILE_FAILED
    assert exc_info.value.violation.issue is not ProjectionIssue.CANDIDATE_COMPILE_FAILED


def test_a_missing_binary_is_a_toolchain_failure_at_either_site() -> None:
    """`BINARY_MISSING` is the one arm typed at its source — `evaluate_compile` separates it from
    `COMPILE_FAILED` — so it is the machine's fault wherever it is observed, and attribution does not
    enter into it. Both call sites must agree."""
    for candidate in ("proj-x", None):
        with pytest.raises(ProjectionError) as exc_info:
            _fatal_if_infrastructure(
                GateResult(GateReason.BINARY_MISSING, False, None, None, "not found"),
                where="posting:1",
                candidate=candidate,
            )
        assert exc_info.value.violation.issue is ProjectionIssue.COMPILE_INFRASTRUCTURE_FAILURE


def test_no_fatal_arm_mentions_a_page_budget_or_claims_a_cause() -> None:
    """Every arm keeps the "no candidate is dropped on its account" guarantee — no reason here is
    overflow — so no message may send the operator to `resume_max_pages`. And none may assert that
    the owner's content caused it: `CompileReason.COMPILE_FAILED` folds a non-zero exit, a missing
    PDF and an unreadable page count together, and `resume_gate.py` reasons that a non-zero exit is
    typically environmental, so a message claiming content would contradict a sibling catalog."""
    cases = (
        (GateReason.COMPILE_FAILED, "proj-x"),
        (GateReason.COMPILE_FAILED, None),
        (GateReason.BINARY_MISSING, "proj-x"),
        (GateReason.BINARY_MISSING, None),
    )
    for reason, candidate in cases:
        with pytest.raises(ProjectionError) as exc_info:
            _fatal_if_infrastructure(
                GateResult(reason, False, None, None, ""), where="posting:1", candidate=candidate
            )
        # Case-insensitive: the guarantee starts a sentence in one arm and continues one in another.
        message = exc_info.value.violation.message.lower()
        assert "never budget overflow" in message
        assert "resume_max_pages" not in message
        assert "most often" not in message


def test_an_ok_gate_is_not_fatal() -> None:
    """The guard fires on exactly two reasons; `OK` and `PAGE_LIMIT_EXCEEDED` fall through to the
    caller's own handling. A split that widened the guard would abort every successful compile."""
    for reason in (GateReason.OK, GateReason.PAGE_LIMIT_EXCEEDED):
        for candidate in ("proj-x", None):
            _fatal_if_infrastructure(
                GateResult(reason, reason is GateReason.OK, None, 1, ""),
                where="w",
                candidate=candidate,
            )


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


def _always_compile_failed(resume: Resume) -> GateResult:
    """`COMPILE_FAILED` from the very first compile, so the PINNED-ONLY prefix takes it. Every other
    fixture in this file returns `OK` for `len(entries) <= 1`, which is why the pinned-base arm of
    `_fatal_if_infrastructure` went untested through `select` until now — and it is the arm reached
    FIRST on every lead, not an edge case."""
    return GateResult(GateReason.COMPILE_FAILED, False, None, None, "! Undefined control sequence")


def test_pinned_only_compile_failure_is_run_scoped_not_one_candidates_fault() -> None:
    """The pinned prefix compiles before any candidate exists, so a failure there cannot be pinned on
    a candidate and must not claim to be. The pinned set is fixed by the frozen declaration, so it is
    run-invariant by exactly the `PINNED_SET_EXCEEDS_BUDGET` argument — per-lead, it would skip every
    lead in turn and report N candidate failures for one cause."""
    with pytest.raises(ProjectionError) as exc_info:
        select(
            POOL,
            _context(JD_DATA),
            SCORER,
            table=TABLE,
            taxonomy=TAXONOMY,
            compile_prefix=_always_compile_failed,
        )
    assert exc_info.value.violation.issue is ProjectionIssue.PINNED_SET_COMPILE_FAILED


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


# -- opt-in "fill the page": a second, floor-bypassing growth phase --------------------------
#
# `JD_MOBILE` matches only `entry.mobile1`; `entry.data1`, `entry.data2` and `entry.zero` all
# score exactly `ADMISSION_FLOOR` against it and so are unreachable in the ranked phase. That is
# the whole point of these tests: the fill phase must reach what the ranked phase provably cannot.


def test_fill_to_page_tops_off_the_page_from_the_remaining_candidates_in_order() -> None:
    """Feature ON, a JD matching one candidate, a roomy page: the ranked phase admits only the
    JD match, then the fill phase tops the page off from every remaining candidate in DECLARATION
    order — including the zero-overlap ones the ranked phase could never admit. Strictly more
    entries reach the page than ranked-only, and the fill admits are recorded separately."""
    filling_pool = dataclasses.replace(POOL, fill_to_page=True)
    roomy = _budget_compiler(10)

    ranked_only = select(
        POOL, _context(JD_MOBILE), SCORER, table=TABLE, taxonomy=TAXONOMY, compile_prefix=roomy
    )
    filled = select(
        filling_pool, _context(JD_MOBILE), SCORER, table=TABLE, taxonomy=TAXONOMY,
        compile_prefix=roomy,
    )

    # The ranked phase is untouched by the flag: only the JD match clears the floor either way.
    assert ranked_only.selected_candidate_ids == ("entry.mobile1",)
    assert filled.selected_candidate_ids == ("entry.mobile1",)

    # The fill phase adds the remaining candidates in declaration order (mobile1 is already
    # admitted, so it is skipped); the ranked-only run adds nothing.
    assert filled.fill_added_ids == ("entry.data1", "entry.data2", "entry.zero")
    assert ranked_only.fill_added_ids == ()

    # Strictly more entries reach the page, filling toward the budget.
    filled_ids = {e.entry_id for e in filled.resume.entries}
    ranked_ids = {e.entry_id for e in ranked_only.resume.entries}
    assert filled_ids > ranked_ids
    assert filled_ids == {"entry.core", "entry.mobile1", "entry.data1", "entry.data2", "entry.zero"}

    # A zero-overlap entry reached the page ONLY through the fill phase, never the ranked one.
    assert "entry.zero" not in filled.selected_candidate_ids
    assert "entry.zero" in filled.fill_added_ids


def test_fill_to_page_off_is_the_ranked_only_selection_unchanged() -> None:
    """Regression guard: with the flag off (the default), the same posting yields exactly the
    ranked-only selection — the zero-overlap candidates stay off the page and `fill_added_ids`
    is empty. This is what makes the feature backward compatible."""
    result = select(
        POOL, _context(JD_MOBILE), SCORER, table=TABLE, taxonomy=TAXONOMY,
        compile_prefix=_budget_compiler(10),
    )
    assert POOL.fill_to_page is False
    assert result.fill_added_ids == ()
    assert result.selected_candidate_ids == ("entry.mobile1",)
    assert {e.entry_id for e in result.resume.entries} == {"entry.core", "entry.mobile1"}


def test_fill_to_page_stops_at_the_first_overflow_and_honours_declaration_order() -> None:
    """The fill phase keeps each candidate while it still fits and stops at the first overflow,
    just like the ranked phase — it does not skip an overflowing candidate to try a later one.
    Budget for pinned + the JD match + exactly ONE fill candidate: the first in declaration order
    (`entry.data1`) is kept; `entry.data2`/`entry.zero` must never appear."""
    filling_pool = dataclasses.replace(POOL, fill_to_page=True)
    result = select(
        filling_pool, _context(JD_MOBILE, page_budget=3), SCORER, table=TABLE, taxonomy=TAXONOMY,
        compile_prefix=_budget_compiler(3),
    )
    assert result.selected_candidate_ids == ("entry.mobile1",)
    assert result.fill_added_ids == ("entry.data1",)
    assert {e.entry_id for e in result.resume.entries} == {
        "entry.core", "entry.mobile1", "entry.data1"
    }


# -- opt-in reverse-chronological PROJECT ordering -------------------------------------------
#
# `sort_projects_by_date` reorders the FINAL selected PROJECT entries by the pool's precomputed
# `project_order` (newest structured start first — the date computation itself is covered in
# test_projection_pool.py), leaving experience entries where they are. The pool is built directly
# with a hand-authored `project_order`, so these tests isolate the reorder from the fact-reading.


def _proj(entry_id: str) -> Entry:
    return Entry(
        entry_id=entry_id,
        heading=entry_id,
        kind="project",
        bullets=[Bullet(bullet_id=f"{entry_id}.0", text="Built a thing")],
    )


# Declaration order is deliberately out of date order and interleaves an experience entry:
#   pold (oldest, pinned) · exp (experience) · ppresent (newest / open-ended) · pmid.
_SORT_ENTRIES = [
    _proj("entry.pold"),
    _entry("entry.exp", "Led the platform team"),
    _proj("entry.ppresent"),
    _proj("entry.pmid"),
]
#: Newest structured start first, exactly as `pool._project_order` would compute it.
_PROJECT_ORDER = ("entry.ppresent", "entry.pmid", "entry.pold")


def _sort_pool(**overrides: object) -> ProjectionPool:
    pool = ProjectionPool(
        resume=Resume(header=["C"], education=[], skill_groups=[], entries=list(_SORT_ENTRIES)),
        pinned_entry_ids=("entry.pold", "entry.exp", "entry.ppresent", "entry.pmid"),
        candidate_entry_ids=(),
        no_match_fallback_ids=(),
        bundle_revision="1",
        bundle_digest="sha256:sortpool",
        projection_digest="sha256:sortdecl",
        project_order=_PROJECT_ORDER,
    )
    return dataclasses.replace(pool, **overrides)


def test_sort_projects_by_date_renders_projects_newest_first_and_leaves_experience_in_place() -> None:
    pool = _sort_pool(sort_projects_by_date=True)
    result = select(
        pool, _context(JD_NONE), SCORER, table=TABLE, taxonomy=TAXONOMY,
        compile_prefix=_budget_compiler(50),
    )
    ids = [e.entry_id for e in result.resume.entries]
    # Projects are reordered newest-first; the experience entry keeps its own slot (index 1).
    assert ids == ["entry.ppresent", "entry.exp", "entry.pmid", "entry.pold"]
    projects = [e.entry_id for e in result.resume.entries if e.kind == "project"]
    assert projects == ["entry.ppresent", "entry.pmid", "entry.pold"]
    # It reorders only — no entry is added or dropped.
    assert set(ids) == {"entry.pold", "entry.exp", "entry.ppresent", "entry.pmid"}


def test_sort_projects_by_date_off_preserves_declaration_order() -> None:
    """Regression: with the flag off (the default) the final résumé keeps declaration order — the
    pinned older project still sits where it was declared, above the newer ones."""
    pool = _sort_pool()
    assert pool.sort_projects_by_date is False
    result = select(
        pool, _context(JD_NONE), SCORER, table=TABLE, taxonomy=TAXONOMY,
        compile_prefix=_budget_compiler(50),
    )
    ids = [e.entry_id for e in result.resume.entries]
    assert ids == ["entry.pold", "entry.exp", "entry.ppresent", "entry.pmid"]
