"""Bounded continuations from frozen posting 384269 / JD version 395826.

No private fixture or live profile is needed. Each family is tested independently so
one new hard stop cannot hide a missing sibling.
"""

from pathlib import Path

import pytest

from boardwatch.eligibility.catalog import RulesCatalog, load_rules
from boardwatch.eligibility.engine import evaluate
from boardwatch.eligibility.facts import ClearanceFact, Facts, Policy, WorkAuthFact

FROZEN_JD = """Are you looking for your next challenge? Are you ready to work with a performance-based small company? At Zantech, we are a dynamic Woman Owned Small Business focused on providing complex, mission-focused solutions with a proven track record of outstanding customer performance and high employee satisfaction. We would love to talk with you regarding the next step in your career. Come join our team!
Zantech is looking for a talented Secret Cleared Software Developer to contribute to the success of our Technical Infrastructure and Platform Support project for a hybrid role based out of DC area with work performed on-site at Joint Base Andrews two days per week.
You’ll be working on a close-nit team with a supportive customer for the Air National Guard. The team builds web-based applications using Microsoft ASP.NET and MS SQL Server.
Required Experience or Knowledge of the following technologies/functions:
Two plus years of experience with Microsoft .NET technologies
Excellent communication skills (verbal and written)
Able to work in a team environment
Able to work tasks independently
Good problem-solving skills
Desired Skills
Microsoft SQL Server (T-SQL)
MVC
DevOps
CI/CD pipeline
JavaScript
Full stack development
Experience with multiple software development methodologies (Agile, Scrum, Kanban, or Waterfall)
Experience with Git and Team Foundation Server
Required Education/Certifications:
Education Required:
None
Education Preferred:
Bachelor’s degree in Computer Science, Engineering or Math
Certifications Required:
Security+ certification or higher (must be acquired within the first 60 days)
Required Security Clearance:
US Citizenship and the ability to obtain and maintain an active Secret or higher clearance, per contract requirements.
“Outstanding Performance…Always!”
Our corporate motto represents our commitment to build long-term relationships with both our clients and our employees by providing the highest quality service in everything we do. We strive for excellence for our clients and for each other. We embrace the opportunity to hire individuals with new talents and fresh perspectives. Zantech offers competitive compensation, strong benefits, and a vacation package, as well as a fast-paced and exciting work environment. Come join our team!"""

CITIZENSHIP = "US Citizenship and the ability to obtain and maintain an active Secret clearance"
CLEARANCE = "Ability to obtain and maintain an active Secret or higher clearance"
POLICY = Policy(families={"work_auth": "blocker", "clearance": "blocker"})


@pytest.fixture(scope="module")
def catalog(tmp_path_factory: pytest.TempPathFactory) -> RulesCatalog:
    return load_rules(Path(tmp_path_factory.mktemp("no-override")))


@pytest.mark.parametrize(
    ("body", "rule", "quote"),
    [
        (CITIZENSHIP, "work_auth:us_citizen_standalone_required", "US Citizenship and the ability"),
        (CLEARANCE, "clearance:clearable_leveled_required", CLEARANCE),
    ],
)
def test_each_continuation_extracts_its_own_required_span(
    body: str, rule: str, quote: str, catalog: RulesCatalog,
) -> None:
    result = evaluate(body, Facts(), POLICY, catalog)
    rows = [r for r in result.requirements if r.rule_id == rule]
    assert len(rows) == 1
    row = rows[0]
    assert row.requiredness == "required"
    assert row.disposition == "unknown"
    assert body[slice(*row.jd_locator["span"])] == quote


@pytest.mark.parametrize(
    ("status", "obtainable", "want_auth", "want_clearance", "verdict"),
    [
        ("ead_or_similar", True, "unmet", "met", "ineligible"),
        ("citizen", False, "met", "unmet", "ineligible"),
        ("citizen", True, "met", "met", "eligible"),
    ],
)
def test_frozen_jd_decides_both_independent_requirements(
    status: str, obtainable: bool, want_auth: str, want_clearance: str,
    verdict: str, catalog: RulesCatalog,
) -> None:
    facts = Facts(
        work_authorization=WorkAuthFact(status=status, jurisdiction="us"),
        security_clearance=ClearanceFact(state="none", level="none", obtainable=obtainable),
        highest_degree="bachelor", field_of_study="computer_science",
    )
    result = evaluate(FROZEN_JD, facts, POLICY, catalog)
    assert result.verdict == verdict
    hard = [r for r in result.requirements if r.requiredness == "required"]
    assert sorted((r.rule_id, r.disposition) for r in hard) == [
        ("clearance:clearable_leveled_required", want_clearance),
        ("work_auth:us_citizen_standalone_required", want_auth),
    ]
    quotes = {r.rule_id: FROZEN_JD[slice(*r.jd_locator["span"])] for r in hard}
    assert quotes == {
        "work_auth:us_citizen_standalone_required": "US Citizenship and the ability",
        "clearance:clearable_leveled_required":
            "ability to obtain and maintain an active Secret or higher clearance",
    }
    degrees = [r for r in result.requirements if r.rule_id and r.rule_id.startswith("degree:")]
    assert degrees
    assert all(r.requiredness == "preferred" for r in degrees)


@pytest.mark.parametrize(
    ("facts", "auth_reason"),
    [
        (Facts(), "no work authorization declared"),
        (Facts(work_authorization=WorkAuthFact(status="prefer_not_to_say", jurisdiction="us")),
         "status or jurisdiction not declared or not identifying"),
        (Facts(work_authorization=WorkAuthFact(status="invalid", jurisdiction="us")),
         "missing_profile_field:work_authorization.status"),
    ],
)
def test_unresolvable_facts_abstain_for_both_requirements(
    facts: Facts, auth_reason: str, catalog: RulesCatalog,
) -> None:
    result = evaluate(FROZEN_JD, facts, POLICY, catalog)
    hard = [r for r in result.requirements if r.requiredness == "required"]
    assert {r.rule_id for r in hard} == {
        "work_auth:us_citizen_standalone_required", "clearance:clearable_leveled_required",
    }
    assert all(r.disposition == "unknown" for r in hard)
    assert {r.rule_id: r.rationale for r in hard} == {
        "work_auth:us_citizen_standalone_required": auth_reason,
        "clearance:clearable_leveled_required":
            "missing_profile_field:security_clearance.obtainable",
    }
    assert result.verdict == "uncertain"


@pytest.mark.parametrize(
    "body",
    [
        "Preferred Qualifications:\n- " + CITIZENSHIP,
        CITIZENSHIP + ", preferred.",
        "US Citizenship and Immigration Services operates E-Verify.",
        "US Citizenship and international experience enrich our team.",
        "US Citizenship and the ability to communicate are valued.",
        "US citizenship is not required.",
        CITIZENSHIP + " is not required.",
    ],
)
def test_citizenship_continuation_does_not_create_false_hard_stops(
    body: str, catalog: RulesCatalog,
) -> None:
    result = evaluate(body, Facts(work_authorization=WorkAuthFact(
        status="ead_or_similar", jurisdiction="us",
    )), POLICY, catalog)
    assert not [r for r in result.requirements if r.rule_id and r.rule_id.startswith("work_auth:")]
    assert result.verdict != "ineligible"


@pytest.mark.parametrize(
    "body",
    [
        "Preferred Qualifications:\n- " + CLEARANCE,
        CLEARANCE + ", preferred.",
        CLEARANCE + " is not required.",
    ],
)
def test_clearance_continuation_preserves_preferences_and_negation(
    body: str, catalog: RulesCatalog,
) -> None:
    result = evaluate(body, Facts(security_clearance=ClearanceFact(
        state="none", level="none", obtainable=False,
    )), POLICY, catalog)
    assert not [r for r in result.requirements if r.requiredness == "required"]
    assert result.verdict != "ineligible"


def test_citizenship_alternative_still_accepts_a_permanent_resident(catalog: RulesCatalog) -> None:
    result = evaluate(
        "Must be a US citizen or a lawful permanent resident.",
        Facts(work_authorization=WorkAuthFact(status="permanent_resident", jurisdiction="us")),
        POLICY, catalog,
    )
    assert result.verdict == "eligible"
    assert [(r.rule_id, r.disposition) for r in result.requirements] == [
        ("work_auth:us_citizen_or_lpr_required", "met"),
    ]


def test_holding_clearance_does_not_answer_obtainability(catalog: RulesCatalog) -> None:
    result = evaluate(CLEARANCE, Facts(security_clearance=ClearanceFact(
        scheme="us_dod", state="active", level="secret",
    )), POLICY, catalog)
    assert [(r.rule_id, r.disposition, r.rationale) for r in result.requirements] == [
        ("clearance:clearable_leveled_required", "unknown",
         "missing_profile_field:security_clearance.obtainable"),
    ]
    assert result.verdict == "uncertain"
