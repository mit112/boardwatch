"""T181: a hedge heading and a tail hedge reach every family's bare-noun bar, not only years.

The hedge channels are catalog keys read the same way for every family: `suppressed_by_unit` (the
clause hedge, its delimiter-only introducer, and the hedge heading replayed as the inline twin),
`hedged_by_tail` (the sentence-final predicate, after every abstain) and `hedged_as` (carry the bar
as a `preferred` twin instead of dropping it). Only `experience_years` declared them, so
"Preferred Qualifications:\\n- U.S. citizenship with the ability to obtain ... clearances" (pv 129842)
was a required `unmet` and the posting's only reason for `ineligible`.

The new families declare only the structural tail, not the clause-wide `suppressed_by_unit`:
the store is full of "(MBA preferred)" / "(TS/SCI preferred)" asides that hedge another noun, and
with no unit list a hedge heading lends its hedge by the introducer allowance alone.

A bar that states its own requirement marker ("Must be a US citizen") is deliberately NOT hedged:
under a hedge heading it contradicts itself, and it is the boilerplate an over-long heading reach
meets. The controls below pin that, and pin that the same bars unhedged stay required.

The profile is the live one's shape: not a citizen, no clearance and none obtainable, a master's,
not enrolled, one year. Every family is a blocker.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.engine import evaluate
from boardwatch.eligibility.facts import Facts, Policy

FACTS = Facts.model_validate(
    {
        "work_authorization": {
            "status": "ead_or_similar", "jurisdiction": "us", "needs_sponsorship": True,
        },
        "total_years_experience": 1,
        "security_clearance": {
            "scheme": None, "level": "none", "state": "none", "accesses": [], "obtainable": False,
        },
        "highest_degree": "master",
        "field_of_study": "software_engineering",
        "education_timing": {"currently_enrolled": False, "graduation_yyyymm": 202508},
    }
)

CITIZENSHIP_129842 = (
    "U.S. citizenship with the ability to obtain and maintain security clearances"
)

# (body, verdict, rows). A DROP that leaves nothing is `uncertain`, never a clear by silence.
HEDGED = [
    pytest.param(
        # T235: the heading's hedge now CARRIES the clearance bar as its preference, the row its
        # one-line form writes, instead of dropping it with no row.
        f"Preferred Qualifications:\n- {CITIZENSHIP_129842}", "eligible",
        [["clearance:clearance_preferred", "preferred", "unmet"]],
        id="work_auth-hedge-heading-pv129842",
    ),
    pytest.param(
        "Nice to have:\n- US citizenship", "uncertain", [], id="work_auth-nice-to-have-heading",
    ),
    pytest.param(
        "Nice to have:\n- Ability to obtain a Secret clearance", "eligible",
        [["clearance:clearance_preferred", "preferred", "unmet"]],
        id="clearance-hedge-heading",  # T235: carried, as above
    ),
    # Clause-scoped: the comma puts the predicate in another unit, so it is read over the sentence.
    pytest.param(
        "Ability to obtain a Secret clearance, preferred.", "eligible",
        [["clearance:clearance_preferred", "preferred", "unmet"]],
        id="clearance-tail-hedge-demoted-to-the-preferred-twin",
    ),
    pytest.param(
        "Eligible for a Top Secret clearance, not required but preferred.", "eligible",
        [["clearance:clearance_preferred", "preferred", "unmet"]],
        id="clearance-leveled-tail-hedge-demoted",
    ),
    pytest.param(
        "Preferred Qualifications:\n- Currently enrolled in a Master's degree program",
        "uncertain", [], id="student_status-enrollment-hedge-heading",
    ),
    pytest.param(
        "Currently enrolled in a Master's degree program, preferred.", "uncertain", [],
        id="student_status-enrollment-tail-hedge",
    ),
    pytest.param(
        "Nice to have:\n- Graduating between Fall 2026 and Summer 2027", "uncertain", [],
        id="student_status-window-hedge-heading",
    ),
    pytest.param(
        "Graduating between Fall 2026 and Summer 2027 is a plus.", "uncertain", [],
        id="student_status-window-inline-hedge",
    ),
    pytest.param(
        "Bachelor's degree or equivalent experience, preferred.", "eligible",
        [["degree:bachelor_or_equivalent_preferred", "preferred", "met"]],
        id="degree-tail-hedge-demoted-and-not-written-twice",
    ),
    pytest.param(
        "PhD or equivalent experience, preferred.", "uncertain", [],
        id="degree-tail-hedge-dropped-without-a-twin",
    ),
    # Already held on the base, pinned so the per-family matrix is complete: the anchored
    # citizenship noun cannot match a line that goes on past it, and degree's own unit hedge
    # already reached its heading.
    pytest.param(
        "US citizenship, preferred.", "uncertain", [], id="work_auth-tail-hedge-held-by-the-anchor",
    ),
    pytest.param(
        "Preferred Qualifications:\n- Bachelor's degree or equivalent experience", "eligible",
        [["degree:bachelor_or_equivalent_preferred", "preferred", "met"]],
        id="degree-hedge-heading",  # T235: carried, as above
    ),
]

# The same bars, unhedged or marker-bearing: each keeps its required row.
KEPT = [
    pytest.param(
        f"Requirements:\n- {CITIZENSHIP_129842}", "ineligible",
        [
            ["clearance:clearable_leveled_required", "required", "unmet"],
            ["clearance:clearable_required", "required", "unmet"],
            ["work_auth:us_citizen_standalone_required", "required", "unmet"],
        ],
        id="CONTROL-work_auth-under-a-requirements-heading",
    ),
    pytest.param(
        "US citizenship.", "ineligible",
        [["work_auth:us_citizen_standalone_required", "required", "unmet"]],
        id="CONTROL-work_auth-bare",
    ),
    # pv 161334: the aside hedges another noun, so the citizenship bar stays.
    pytest.param(
        "U.S. Citizen (Current clearance holder a plus)", "ineligible",
        [["work_auth:us_citizen_standalone_required", "required", "unmet"]],
        id="CONTROL-work_auth-aside-hedging-another-noun",
    ),
    pytest.param(
        "Preferred Qualifications:\n- Must be a US citizen", "ineligible",
        [["work_auth:us_citizen_required", "required", "unmet"]],
        id="CONTROL-work_auth-marker-bar-under-a-hedge-heading",
    ),
    pytest.param(
        "Ability to obtain a Secret clearance.", "ineligible",
        [
            ["clearance:clearable_leveled_required", "required", "unmet"],
            ["clearance:clearable_required", "required", "unmet"],
        ],
        id="CONTROL-clearance-bare",
    ),
    pytest.param(
        "Ability to obtain a Secret clearance, with TS/SCI preferred.", "ineligible",
        [
            ["clearance:clearable_leveled_required", "required", "unmet"],
            ["clearance:clearable_required", "required", "unmet"],
        ],
        id="CONTROL-clearance-hedge-on-a-sub-clause",
    ),
    # T197: the aside names its own noun, so its hedge reaches neither bar -- the leveled row, which
    # the aside's hedge used to drop, stays as it does in the bare and sub-clause forms above.
    pytest.param(
        "Ability to obtain a Secret clearance (TS/SCI preferred).", "ineligible",
        [
            ["clearance:clearable_leveled_required", "required", "unmet"],
            ["clearance:clearable_required", "required", "unmet"],
        ],
        id="CONTROL-clearance-aside-hedging-a-higher-level",
    ),
    # pv 124909 and pv 17357: the hedge is the MBA's, or one arm's, never the enrolment's.
    pytest.param(
        "Currently enrolled in a full-time Master’s degree program (MBA preferred).", "ineligible",
        [["student_status:current_enrollment_required", "required", "unmet"]],
        id="CONTROL-student_status-aside-hedging-another-noun",
    ),
    # A heading lends only its own hedge: the aside inside the item is not the heading's.
    pytest.param(
        "Requirements:\n- Currently enrolled in a full-time Master’s degree program (MBA preferred).",
        "ineligible", [["student_status:current_enrollment_required", "required", "unmet"]],
        id="CONTROL-student_status-aside-under-a-requirements-heading",
    ),
    pytest.param(
        "Currently pursuing a Master’s degree (preferred) or Bachelor’s degree in Business "
        "Administration, Economics, Finance, Data Science, Pharmacoeconomics or a related field.",
        "ineligible", [["student_status:current_enrollment_required", "required", "unmet"]],
        id="CONTROL-student_status-hedge-on-one-arm",
    ),
    pytest.param(
        "Nice to have:\n- Active Secret clearance required", "ineligible",
        [["clearance:active_secret_required", "required", "unmet"]],
        id="CONTROL-clearance-marker-bar-under-a-hedge-heading",
    ),
    pytest.param(
        "Currently enrolled in a Master's degree program.", "ineligible",
        [["student_status:current_enrollment_required", "required", "unmet"]],
        id="CONTROL-student_status-bare",
    ),
    pytest.param(
        "Requirements:\n- Graduating between Fall 2026 and Summer 2027", "ineligible",
        [["student_status:graduation_window_required", "required", "unmet"]],
        id="CONTROL-student_status-window-under-a-requirements-heading",
    ),
    pytest.param(
        "PhD required.", "ineligible", [["degree:doctorate_required", "required", "unmet"]],
        id="CONTROL-degree-marker-bar",
    ),
]


@pytest.fixture(scope="module")
def catalog(tmp_path_factory: pytest.TempPathFactory):  # type: ignore[no-untyped-def]
    return load_rules(Path(tmp_path_factory.mktemp("no-override")))


def _run(catalog, body: str) -> tuple[str, list[list[str]]]:  # type: ignore[no-untyped-def]
    policy = Policy(families={family.id: "blocker" for family in catalog.families})
    result = evaluate(body, FACTS, policy, catalog)
    rows = sorted([r.rule_id, r.requiredness, r.disposition] for r in result.requirements)
    return result.verdict, rows


@pytest.mark.parametrize(("body", "verdict", "rows"), HEDGED)
def test_a_hedged_bar_is_not_read_as_a_requirement(catalog, body: str, verdict: str, rows) -> None:  # type: ignore[no-untyped-def]
    assert _run(catalog, body) == (verdict, sorted(rows))


@pytest.mark.parametrize(("body", "verdict", "rows"), KEPT)
def test_an_unhedged_or_marker_bar_stays_required(catalog, body: str, verdict: str, rows) -> None:  # type: ignore[no-untyped-def]
    assert _run(catalog, body) == (verdict, sorted(rows))


def test_a_demoted_clearance_row_quotes_the_body_through_its_hedge(catalog) -> None:  # type: ignore[no-untyped-def]
    body = "Ability to obtain a Secret clearance, preferred."
    policy = Policy(families={family.id: "blocker" for family in catalog.families})
    (row,) = evaluate(body, FACTS, policy, catalog).requirements
    start, end = row.jd_locator["span"]
    assert body[start:end] == "Ability to obtain a Secret clearance, preferred"
