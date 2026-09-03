"""The `student_status` family (D-438): graduating-cohort and current-enrolment gating.

A blind two-judge audit of the live apply lane on 2026-09-03 found postings that exclude an
already-graduated candidate by stating a graduation WINDOW ("between December 2026 and May
2027") or requiring CURRENT ENROLMENT ("you are pursuing a bachelor's degree"). No family
could fire on either, so they were invisible by construction rather than by a pattern gap.

**The precision problem is the whole design, and it runs the other way.** A false `unmet`
here writes `ineligible` carrying a quoted JD span, which silently removes a job the
candidate can actually take. Four phrasings measured live MUST NOT fire:

    "Graduated with a CS degree BY Summer 2027"        an upper bound he satisfies
    "A 2025 OR 2026 graduate with OR PURSUING a B.S."  he is a 2025 graduate
    "Currently pursuing OR RECENTLY COMPLETED a degree" enrolment is one acceptable path
    "Computer Science GRADUATE OR currently enrolled"   same, reversed

Measured against the live 537-lead apply lane: 17 leads (3.2%) take an UNMET row, and none of
the four above is among them.

Nothing in the resolver reads the clock. The window is compared against a DECLARED graduation
date, so identical facts give an identical verdict on any day and `build_identity` stays a
complete description of the inputs.
"""

from __future__ import annotations

import pytest

from boardwatch.eligibility.catalog import RulesCatalog, load_rules
from boardwatch.eligibility.engine import evaluate
from boardwatch.eligibility.facts import EducationTimingFact, Facts, Policy

BLOCKER_ALL = Policy(
    families={
        f: "blocker"
        for f in (
            "work_auth", "clearance", "experience_years",
            "internship", "contract_not_fte", "degree", "student_status",
        )
    }
)

#: Graduated August 2025, no longer enrolled — the profile the audit was run against.
GRADUATED = Facts(
    education_timing=EducationTimingFact(currently_enrolled=False, graduation_yyyymm=202508)
)
#: The multi-tenancy mirror: a current student inside the window must CLEAR the same postings.
STUDENT = Facts(
    education_timing=EducationTimingFact(currently_enrolled=True, graduation_yyyymm=202705)
)
#: Declares nothing. Every branch must abstain, never decide.
UNDECLARED = Facts()

ENROLMENT_REQUIRED = (
    "You are pursuing a bachelor's or master's degree in computer science, engineering, "
    "or another related field and can start full-time in Summer 2027."
)
WINDOW_REQUIRED = (
    "Applicants must have a graduation date between December 2026 and May 2027 to be "
    "considered for this program."
)
# --- the four live phrasings that must NOT fire -------------------------------------------
UPPER_BOUND = "Graduated with a CS or Software Engineering degree by Summer 2027."
YEAR_DISJUNCTION = "A 2025 or 2026 graduate with or pursuing a B.S., M.S. in Computer Science."
COMPLETED_DISJUNCTION = (
    "Currently pursuing or recently completed a degree in Computer Science or a related field."
)
GRADUATE_OR_ENROLLED = (
    "Computer Science graduate or currently enrolled in a Computer Science, Computer "
    "Engineering or related field."
)
NOT_FIRING = pytest.mark.parametrize(
    "body",
    [UPPER_BOUND, YEAR_DISJUNCTION, COMPLETED_DISJUNCTION, GRADUATE_OR_ENROLLED],
    ids=["upper_bound", "year_disjunction", "completed_disjunction", "graduate_or_enrolled"],
)


@pytest.fixture()
def catalog(tmp_path_factory: pytest.TempPathFactory) -> RulesCatalog:
    return load_rules(tmp_path_factory.mktemp("no-override"))


def _rows(catalog: RulesCatalog, body: str, facts: Facts) -> list[tuple[str, str]]:
    result = evaluate(body, facts, BLOCKER_ALL, catalog)
    return [
        (req.rule_id, req.disposition)
        for req in result.requirements
        if req.rule_id and req.rule_id.startswith("student_status")
    ]


def _verdict(catalog: RulesCatalog, body: str, facts: Facts) -> str:
    return evaluate(body, facts, BLOCKER_ALL, catalog).verdict


class TestCurrentEnrolment:
    def test_a_graduate_is_ineligible_for_an_enrolment_requirement(
        self, catalog: RulesCatalog
    ) -> None:
        assert _verdict(catalog, ENROLMENT_REQUIRED, GRADUATED) == "ineligible"
        assert ("student_status:current_enrollment_required", "unmet") in _rows(
            catalog, ENROLMENT_REQUIRED, GRADUATED
        )

    def test_a_current_student_clears_the_same_posting(self, catalog: RulesCatalog) -> None:
        # Multi-tenancy: the family must not be a rule that only ever rejects.
        assert ("student_status:current_enrollment_required", "met") in _rows(
            catalog, ENROLMENT_REQUIRED, STUDENT
        )
        assert _verdict(catalog, ENROLMENT_REQUIRED, STUDENT) != "ineligible"

    def test_an_undeclared_profile_abstains(self, catalog: RulesCatalog) -> None:
        # Keystone: never `met`, never `unmet`, when the fact is absent.
        assert ("student_status:current_enrollment_required", "unknown") in _rows(
            catalog, ENROLMENT_REQUIRED, UNDECLARED
        )
        assert _verdict(catalog, ENROLMENT_REQUIRED, UNDECLARED) == "uncertain"


class TestGraduationWindow:
    def test_a_graduation_outside_the_window_is_ineligible(
        self, catalog: RulesCatalog
    ) -> None:
        assert _verdict(catalog, WINDOW_REQUIRED, GRADUATED) == "ineligible"
        assert ("student_status:graduation_window_required", "unmet") in _rows(
            catalog, WINDOW_REQUIRED, GRADUATED
        )

    def test_a_graduation_inside_the_window_clears(self, catalog: RulesCatalog) -> None:
        # 202705 sits inside 202612..202705, and the bound is CLOSED at both ends.
        assert ("student_status:graduation_window_required", "met") in _rows(
            catalog, WINDOW_REQUIRED, STUDENT
        )

    def test_the_boundary_months_are_inclusive(self, catalog: RulesCatalog) -> None:
        """Asserting only the interior would pass against a strict `<`/`>` comparison."""
        for yyyymm in (202612, 202705):
            facts = Facts(education_timing=EducationTimingFact(graduation_yyyymm=yyyymm))
            assert ("student_status:graduation_window_required", "met") in _rows(
                catalog, WINDOW_REQUIRED, facts
            ), yyyymm

    def test_an_undeclared_graduation_date_abstains(self, catalog: RulesCatalog) -> None:
        assert ("student_status:graduation_window_required", "unknown") in _rows(
            catalog, WINDOW_REQUIRED, UNDECLARED
        )

    def test_an_unreadable_month_abstains_rather_than_deciding(
        self, catalog: RulesCatalog
    ) -> None:
        body = "Applicants must have a graduation date between Fructidor 2026 and May 2027."
        rows = _rows(catalog, body, GRADUATED)
        assert rows == [] or ("student_status:graduation_window_required", "unknown") in rows
        assert _verdict(catalog, body, GRADUATED) != "ineligible"

    def test_an_inverted_window_abstains(self, catalog: RulesCatalog) -> None:
        body = "Applicants must have a graduation date between May 2027 and December 2026."
        assert ("student_status:graduation_window_required", "unknown") in _rows(
            catalog, body, GRADUATED
        )


class TestTheFamilyDoesNotOverReach:
    """The controls. Each body is verbatim live JD text from the apply lane that the
    candidate is genuinely eligible for; a row here is a job silently deleted."""

    @NOT_FIRING
    def test_no_row_is_written(self, catalog: RulesCatalog, body: str) -> None:
        assert _rows(catalog, body, GRADUATED) == []

    @NOT_FIRING
    def test_and_the_verdict_is_never_ineligible(
        self, catalog: RulesCatalog, body: str
    ) -> None:
        assert _verdict(catalog, body, GRADUATED) != "ineligible"

    def test_an_ordinary_posting_is_untouched(self, catalog: RulesCatalog) -> None:
        body = (
            "We are hiring a software engineer to build and operate web services. "
            "We are relentlessly pursuing excellence in everything we ship."
        )
        assert _rows(catalog, body, GRADUATED) == []

    def test_a_benefits_enrolment_sentence_is_not_a_degree_requirement(
        self, catalog: RulesCatalog
    ) -> None:
        body = "Employees enrolled in the plan receive dental and vision coverage."
        assert _rows(catalog, body, GRADUATED) == []


class TestSeverity:
    """The family ships `blocker`, and the reason is that it makes the family ABSTAIN.

    Severity is resolved per FAMILY, so a `preference` row leaves `engine.blocking()`
    entirely and the verdict falls through to `eligible`. Shipping `preference` was tried
    and measured worse: an enrolment requirement read `uncertain` before this family existed
    (zero rows, so `_no_evaluable_requirement` fired) and `eligible` after, for a profile
    declaring nothing about enrolment -- a backwards `eligible` hitting every user who never
    opted in.
    """

    def test_the_shipped_default_is_blocker(self, catalog: RulesCatalog) -> None:
        assert catalog.family("student_status").default_policy == "blocker"

    def test_an_undeclared_profile_can_never_be_rejected_by_this_family(
        self, catalog: RulesCatalog
    ) -> None:
        """What makes `blocker` safe here, and the half that must never regress: the fact is
        optional, an absent fact resolves UNKNOWN and never UNMET, so a user who has not
        opted in reads `uncertain`. Only a DECLARED value can reach `unmet`."""
        default_only = Policy(families={})
        for body in (WINDOW_REQUIRED, ENROLMENT_REQUIRED):
            assert evaluate(body, UNDECLARED, default_only, catalog).verdict == "uncertain"

    def test_the_shipped_default_still_abstains_rather_than_clearing(
        self, catalog: RulesCatalog
    ) -> None:
        """The regression `preference` caused, pinned directly: an enrolment requirement
        against an undeclared profile must NOT read `eligible`."""
        default_only = Policy(families={})
        assert (
            evaluate(ENROLMENT_REQUIRED, UNDECLARED, default_only, catalog).verdict != "eligible"
        )
