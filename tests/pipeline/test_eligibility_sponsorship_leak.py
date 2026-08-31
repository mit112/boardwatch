"""The 2026-08-30 audit found the keystone work_auth rule clearing a candidate who
needs sponsorship on postings that state a sponsorship restriction in a form the
catalog did not detect. Two surfaces leaked:

1. "...authorized to work in the U.S. WITHOUT sponsorship" produced only an
   `authorization_required` row (MET for an ``ead_or_similar`` holder), never the
   sponsorship restriction it states -- a backwards ``eligible``.
2. "We will not consider candidates who require sponsorship" carries no refusal-verb
   frame, so `no_sponsorship_offered` never fired and it cleared by silence
   (``uncertain`` -> apply via the delivery fail-open).

Both must resolve ``ineligible`` for a declared ``needs_sponsorship`` candidate, and
-- the multi-tenancy guard -- stay ``eligible`` for a citizen on the identical JD,
because ``sponsorship_unavailable`` resolves MET when no sponsorship is needed.

These assertions FAIL against the pre-fix catalog (case 1 -> eligible, case 2 ->
uncertain), which is what makes them discriminating rather than vacuous.
"""

from __future__ import annotations

import pytest

from boardwatch.eligibility.catalog import RulesCatalog, load_rules
from boardwatch.eligibility.engine import evaluate
from boardwatch.eligibility.facts import Facts, Policy, WorkAuthFact

# All six families as blockers, matching a fully-armed profile; work_auth is a blocker
# by default anyway, so this only makes the intent explicit.
BLOCKER_ALL = Policy(
    families={
        f: "blocker"
        for f in (
            "work_auth",
            "clearance",
            "experience_years",
            "internship",
            "contract_not_fte",
            "degree",
        )
    }
)

EAD_NEEDS_SPONSORSHIP = Facts(
    work_authorization=WorkAuthFact(
        status="ead_or_similar", jurisdiction="us", needs_sponsorship=True
    )
)
US_CITIZEN = Facts(work_authorization=WorkAuthFact(status="citizen", jurisdiction="us"))

WITHOUT_SPONSORSHIP = (
    "We are building core services. Must be legally authorized to work in the U.S. "
    "without sponsorship. Strong Python skills required."
)
WILL_NOT_CONSIDER = (
    "We will not consider candidates who require sponsorship for a work-authorized "
    "visa, now or in the future."
)
PLAIN_AUTHORIZED = "Candidates must possess authorization to work in the United States."
EXPLICIT_REFUSAL = "We do not offer visa sponsorship for this position."


@pytest.fixture()
def catalog(tmp_path_factory: pytest.TempPathFactory) -> RulesCatalog:
    # A tmp dir with no rules.yaml -> the bundled catalog, same as the other suites.
    return load_rules(tmp_path_factory.mktemp("no-override"))


def _work_auth_rows(catalog: RulesCatalog, body: str, facts: Facts) -> list[tuple[str, str]]:
    result = evaluate(body, facts, BLOCKER_ALL, catalog)
    return [
        (req.rule_id, req.disposition)
        for req in result.requirements
        if req.rule_id and req.rule_id.startswith("work_auth")
    ]


def _verdict(catalog: RulesCatalog, body: str, facts: Facts) -> str:
    return evaluate(body, facts, BLOCKER_ALL, catalog).verdict


class TestSponsorshipLeak:
    def test_without_sponsorship_is_ineligible_for_an_ead_holder(
        self, catalog: RulesCatalog
    ) -> None:
        assert _verdict(catalog, WITHOUT_SPONSORSHIP, EAD_NEEDS_SPONSORSHIP) == "ineligible"
        assert ("work_auth:no_sponsorship_without_clause", "unmet") in _work_auth_rows(
            catalog, WITHOUT_SPONSORSHIP, EAD_NEEDS_SPONSORSHIP
        )

    def test_will_not_consider_sponsorship_is_ineligible_for_an_ead_holder(
        self, catalog: RulesCatalog
    ) -> None:
        assert _verdict(catalog, WILL_NOT_CONSIDER, EAD_NEEDS_SPONSORSHIP) == "ineligible"
        assert ("work_auth:no_sponsorship_will_not_consider", "unmet") in _work_auth_rows(
            catalog, WILL_NOT_CONSIDER, EAD_NEEDS_SPONSORSHIP
        )

    def test_ineligible_carries_a_quoted_jd_span(self, catalog: RulesCatalog) -> None:
        """Keystone: an INELIGIBLE row must cite a span from the frozen JD, or be
        downgraded to ABSTAIN. `requirement_text` cannot show that -- it is a static
        string on the catalog rule and is identical whatever the JD says -- so this
        resolves `jd_locator` against the body and asserts the span is the offending
        clause itself. Asserting only that the text is non-empty would pass against a
        rule that cited nothing."""
        result = evaluate(WITHOUT_SPONSORSHIP, EAD_NEEDS_SPONSORSHIP, BLOCKER_ALL, catalog)
        offending = [
            req
            for req in result.requirements
            if req.rule_id == "work_auth:no_sponsorship_without_clause"
            and req.disposition == "unmet"
        ]
        assert offending, "expected the without-sponsorship row to be present and unmet"
        locator = offending[0].jd_locator
        assert locator["field"] == "body_text"
        start, end = locator["span"]
        assert WITHOUT_SPONSORSHIP[start:end] == "without sponsorship"

    def test_plain_authorization_requirement_stays_eligible(
        self, catalog: RulesCatalog
    ) -> None:
        # An EAD holder IS authorized; a bare "must be authorized to work in the US" with
        # no sponsorship clause must NOT be turned into a rejection.
        assert _verdict(catalog, PLAIN_AUTHORIZED, EAD_NEEDS_SPONSORSHIP) == "eligible"

    def test_existing_refusal_surface_still_fires(self, catalog: RulesCatalog) -> None:
        assert _verdict(catalog, EXPLICIT_REFUSAL, EAD_NEEDS_SPONSORSHIP) == "ineligible"
        assert ("work_auth:no_sponsorship_offered", "unmet") in _work_auth_rows(
            catalog, EXPLICIT_REFUSAL, EAD_NEEDS_SPONSORSHIP
        )

    def test_multi_tenancy_a_citizen_clears_the_same_postings(
        self, catalog: RulesCatalog
    ) -> None:
        # The new patterns must not drop a citizen: sponsorship_unavailable resolves MET
        # when no sponsorship is needed, so both JDs stay eligible.
        assert _verdict(catalog, WITHOUT_SPONSORSHIP, US_CITIZEN) == "eligible"
        assert _verdict(catalog, WILL_NOT_CONSIDER, US_CITIZEN) == "eligible"
