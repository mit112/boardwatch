"""Recall gaps found by re-measuring the LIVE apply lane on 2026-08-30, second pass.

Every span below was copied out of a posting that was sitting in the apply queue, where the
candidate could "instantly spot something that makes it ineligible" — the acceptance test this
whole sprint is against. All six patterns are DETECTION fixes: the resolver was never the
problem. `Must be a US citizen.` already decides `unmet` for `ead_or_similar` under D-322, and
`obtainable: false` already decides a clearable requirement. The engine simply produced NO ROW,
and a routing change cannot move a requirement that was never detected.

Diagnosis came BEFORE any pattern here was written, which is the F64 lesson: ten controls and
three findings once "covered" the sponsorship idiom while none of them declared the fact that
made the leak visible, so none could see it. The cause was forked four ways per the keystone
invariant — no row / abstain on a missing profile field / decided-but-unquoted / decided-but-
regrouped — and measured to be the FIRST in every one of the 26 citizenship cases.

The negative half of this file is not decoration. Widening any of these families pushes toward
MORE `ineligible`, which is the direction that silently deletes a real job, so each pattern is
pinned against the span that most nearly looks like the one it must catch.
"""

from __future__ import annotations

import pytest

from boardwatch.eligibility.catalog import RulesCatalog, load_rules
from boardwatch.eligibility.engine import evaluate
from boardwatch.eligibility.facts import ClearanceFact, Facts, Policy, WorkAuthFact

BLOCKER_ALL = Policy(
    families={
        f: "blocker"
        for f in ("work_auth", "clearance", "experience_years", "internship",
                  "contract_not_fte", "degree")
    }
)
#: Mit's real resolved facts, which is what makes these decisions rather than abstains.
EAD = Facts(
    work_authorization=WorkAuthFact(status="ead_or_similar", jurisdiction="us",
                                    needs_sponsorship=True),
    security_clearance=ClearanceFact(level="none", state="none", obtainable=False),
    total_years_experience=1,
)
#: THE MULTI-TENANCY GUARD. A pattern that cannot clear anyone is a blanket veto wearing a
#: rule's name, so every citizenship span must read `met` for a citizen and every clearance
#: span must clear someone who can actually be cleared.
CITIZEN = Facts(
    work_authorization=WorkAuthFact(status="citizen", jurisdiction="us",
                                    needs_sponsorship=False),
    security_clearance=ClearanceFact(level="none", state="none", obtainable=True),
    total_years_experience=1,
)


@pytest.fixture()
def catalog(tmp_path_factory: pytest.TempPathFactory) -> RulesCatalog:
    return load_rules(tmp_path_factory.mktemp("no-override"))


def _rules(catalog: RulesCatalog, body: str, facts: Facts, family: str) -> set[str]:
    return {
        (r.rule_id or "").split(":")[-1]
        for r in evaluate(body, facts, BLOCKER_ALL, catalog).requirements
        if (r.rule_id or "").startswith(f"{family}:")
    }


def _verdict(catalog: RulesCatalog, body: str, facts: Facts) -> str:
    return evaluate(body, facts, BLOCKER_ALL, catalog).verdict


# --------------------------------------------------------------------------------------
# work_auth — 26 apply-lane postings, four structurally distinct misses
# --------------------------------------------------------------------------------------

#: (span, the pattern that must claim it). The SpaceX clause accounts for 19 of the 26 on its
#: own; the roman-numeral enumerator is why the shared 0-3 word gap could never reach the noun,
#: because `\w+` does not cross a parenthesis.
CITIZENSHIP_SPANS = [
    (
        "To conform to U.S. Government export regulations, applicant must be a (i) U.S. "
        "citizen or national, (ii) U.S. lawful, permanent resident (aka green card holder), "
        "(iii) Refugee under 8 U.S.C. 1157.",
        "us_person_export_control_required",
    ),
    (
        "Experience in Object-Oriented design and multi-threaded programming. US Citizen. "
        "Applicant selected will be subject to a government security investigation.",
        "us_citizen_standalone_required",
    ),
    (
        "Basic Qualifications. US Citizenship with an active Secret clearance or higher.",
        "us_citizen_standalone_required",
    ),
    (
        "All work must be performed within the United States by individuals authorized to "
        "work in the U.S. and who are U.S. citizens.",
        "us_citizen_predicate_required",
    ),
    (
        "The contract mandates all personnel working on the contracts be United States "
        "citizens (naturalized or native).",
        "us_citizen_predicate_required",
    ),
]


@pytest.mark.parametrize(("body", "rule"), CITIZENSHIP_SPANS)
def test_citizenship_span_is_detected_and_decided(catalog: RulesCatalog, body: str,
                                                  rule: str) -> None:
    """Detection AND decision: a row that abstains would leave the lead in the apply lane."""
    assert rule in _rules(catalog, body, EAD, "work_auth")
    assert _verdict(catalog, body, EAD) == "ineligible"


@pytest.mark.parametrize(("body", "rule"), CITIZENSHIP_SPANS)
def test_citizenship_span_clears_a_citizen(catalog: RulesCatalog, body: str,
                                           rule: str) -> None:
    assert _verdict(catalog, body, CITIZEN) != "ineligible"


#: `U.S. Citizenship and Immigration Services` is the E-Verify boilerplate. It appears in a
#: large share of US postings, names no requirement whatsoever, and was matched by the first,
#: unanchored draft of `us_citizen_standalone_required`. It is the reason that pattern anchors
#: at the start of its sentence rather than searching anywhere inside it.
CITIZENSHIP_NON_REQUIREMENTS = [
    "E-Verify is an Internet-based employment eligibility verification system operated by the "
    "U.S. Citizenship and Immigration Services.",
    "Petitions are filed with U.S. Citizenship and Immigration Services on the employee's "
    "behalf.",
    "US citizenship is preferred but not required.",
    "We do not discriminate on the basis of citizenship status, race, or national origin.",
    "Our workforce includes US citizens, permanent residents, and visa holders from 30 "
    "countries.",
    "To conform to export regulations, our shipping team must label each package correctly.",
]


@pytest.mark.parametrize("body", CITIZENSHIP_NON_REQUIREMENTS)
def test_citizenship_non_requirement_fires_nothing(catalog: RulesCatalog, body: str) -> None:
    assert _rules(catalog, body, EAD, "work_auth") == set()
    assert _verdict(catalog, body, EAD) != "ineligible"


# --------------------------------------------------------------------------------------
# clearance — the ADJECTIVE STACK, 11 apply-lane postings
# --------------------------------------------------------------------------------------

#: The twin's object list is a single OPTIONAL group, so it admits exactly one modifier.
#: Every span here stacks two or more, or uses `eligible FOR` in place of `to obtain`.
CLEARABLE_SPANS = [
    "Eligible to obtain and maintain an active U.S. Secret security clearance.",
    "Ability to obtain and maintain a U.S. Top Secret SCI security clearance.",
    "Must be eligible to obtain and maintain a U.S. TS clearance.",
    "Must be eligible for a US DoD security clearance.",
]


@pytest.mark.parametrize("body", CLEARABLE_SPANS)
def test_clearable_stack_is_detected_and_decided(catalog: RulesCatalog, body: str) -> None:
    assert "clearable_leveled_required" in _rules(catalog, body, EAD, "clearance")
    assert _verdict(catalog, body, EAD) == "ineligible"


@pytest.mark.parametrize("body", CLEARABLE_SPANS)
def test_clearable_stack_clears_someone_who_can_be_cleared(catalog: RulesCatalog,
                                                           body: str) -> None:
    assert _verdict(catalog, body, CITIZEN) != "ineligible"


#: The twin carries NO hedge suppressor, which survives only because its reach is narrow —
#: measured across all three live lanes, zero postings hedge a phrasing it can see. This
#: sibling reaches wider, so the guard is added where the reach is added.
CLEARANCE_HEDGES = [
    "Willingness to obtain a US Secret security clearance is a plus.",
    "Ability to obtain and maintain an active U.S. Secret security clearance is preferred.",
    "Eligible for a US DoD security clearance — nice to have.",
    "Ability to obtain a U.S. Top Secret SCI security clearance is not required.",
]


@pytest.mark.parametrize("body", CLEARANCE_HEDGES)
def test_hedged_clearance_is_not_a_blocker(catalog: RulesCatalog, body: str) -> None:
    assert "clearable_leveled_required" not in _rules(catalog, body, EAD, "clearance")
    assert _verdict(catalog, body, EAD) != "ineligible"


# --------------------------------------------------------------------------------------
# experience_years — the two shapes left after the range fix
# --------------------------------------------------------------------------------------

#: SHAPE 1: a domain LIST before `experience`. The scoped tail allows a head word plus two
#: more and its word run cannot cross a comma.
DOMAIN_LIST_SPANS = [
    "4+ years of software engineering or SRE experience.",
    "5+ years of DevOps, platform engineering, or SRE experience in an enterprise environment.",
    "3+ years of professional software or data engineering experience.",
    "3+ years of software development, software systems engineering, or software validation "
    "experience with related tooling.",
]


@pytest.mark.parametrize("body", DOMAIN_LIST_SPANS)
def test_domain_list_reaches_the_experience_noun(catalog: RulesCatalog, body: str) -> None:
    assert "domain_list_years_minimum" in _rules(catalog, body, EAD, "experience_years")


#: SHAPE 2: no `experience` noun anywhere. The number and the domain carry the requirement.
DOMAIN_ONLY_SPANS = [
    "5+ years' embedded SW; strong RTOS expertise.",
    "15+ Years of Systems Engineering: proven track record of operating production systems.",
    "2 years in SaaS, PaaS, or IaaS software development.",
    "Minimum of 5 years of service in a related hardware/software position.",
    "EXPERIENCE: 3+ year web development, in-house or agency.",
]


@pytest.mark.parametrize("body", DOMAIN_ONLY_SPANS)
def test_domain_only_bar_is_detected(catalog: RulesCatalog, body: str) -> None:
    assert "domain_years_minimum" in _rules(catalog, body, EAD, "experience_years")


#: Every one of these is company-side tenure prose lifted from the measured residue, and every
#: one carries a number a candidate could never be asked for. The 2-19 bound is what keeps them
#: out; `(?<!to\s)` keeps an ABOVE bound out, which would reject the new grads this tool exists
#: to find.
EXPERIENCE_NON_REQUIREMENTS = [
    "30+ years of pioneering robotics research and 150+ professionals driving innovation.",
    "For 25 years it has been a unique legacy of innovation fuelled by great technology.",
    "For 10 years, helping more than half a million families improve their transportation.",
    "Up to 3 years web development is all we expect from a new graduate.",
    "5+ years of DevOps experience is preferred but not required.",
]


@pytest.mark.parametrize("body", EXPERIENCE_NON_REQUIREMENTS)
def test_experience_non_requirement_fires_nothing(catalog: RulesCatalog, body: str) -> None:
    assert _rules(catalog, body, EAD, "experience_years") == set()


def test_domain_years_defers_when_the_experience_noun_is_present(catalog: RulesCatalog) -> None:
    """`domain_years_minimum` exists for spans with NO `experience` noun, and its lookahead is
    what makes that definition enforceable. Without it three rows landed on one span; the
    verdict was unchanged, but the abstain report counts ROWS, so the noise would have read as
    a real jump in experience detections."""
    body = "2+ years of industry software engineering experience."
    rules = _rules(catalog, body, EAD, "experience_years")
    assert "domain_years_minimum" not in rules
    assert "scoped_years_minimum" in rules
