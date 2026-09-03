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


# The 2026-09-03 audit. Two Sonnet judges blind-read a 54-posting sample of the live
# `eligible` population and returned 24% INELIGIBLE; tracing those back to the ledger found
# work_auth writing NO row at all on two more surfaces. Both bodies below are VERBATIM live
# JD text, not hand-authored near-misses -- which is the point. The corpus already carried
# `m0362` ("...without the need for VISA sponsorship now or in the future"), one word short
# of EMPLOYMENT_BASED below, and that near-miss is exactly why a green suite shipped the gap.
#
# The failures were one token wide in each case:
#   EMPLOYMENT_BASED  the `without ... sponsorship` object slot was a FIXED one-token noun
#                     list, so the compound `employment-based visa` could not be crossed.
#   SPONSOR_INDIVIDUALS  `no_sponsorship_offered`'s filler gap between `sponsor` and the visa
#                     noun was `{0,2}`, and `individuals for employment-based` needs three.
EMPLOYMENT_BASED = (
    "Applicants must be authorized to work in the U.S. without the need for "
    "employment-based visa sponsorship now or in the future."
)
SPONSOR_INDIVIDUALS = (
    "Allstate generally does not sponsor individuals for employment-based visas "
    "for this position."
)
#: The negative control this pair needs. Widening a gap risks turning an ordinary posting
#: into a rejection, and a suite that only asserts the two new hits cannot see that.
#: Deliberately states NO requirement of any family -- an earlier draft said "Bachelor\'s
#: degree required" and read `uncertain`, because these Facts declare no degree and the
#: degree rule correctly abstained. That is the right behaviour and the wrong control: it
#: would have failed for a reason having nothing to do with sponsorship.
NO_SPONSORSHIP_LANGUAGE = (
    "We are hiring a software engineer. You will build and operate web services "
    "alongside a small team, and help shape how we ship."
)


class TestCompoundSponsorshipSurfaces:
    """The two live surfaces the 2026-09-03 audit found still leaking.

    These assertions FAIL against the pre-fix catalog -- both bodies produced zero
    `work_auth` rows and verdict `eligible` -- which is what makes them discriminating.
    """

    def test_employment_based_visa_sponsorship_is_ineligible(
        self, catalog: RulesCatalog
    ) -> None:
        assert _verdict(catalog, EMPLOYMENT_BASED, EAD_NEEDS_SPONSORSHIP) == "ineligible"
        assert ("work_auth:no_sponsorship_without_clause", "unmet") in _work_auth_rows(
            catalog, EMPLOYMENT_BASED, EAD_NEEDS_SPONSORSHIP
        )

    def test_sponsor_individuals_for_visas_is_ineligible(
        self, catalog: RulesCatalog
    ) -> None:
        assert _verdict(catalog, SPONSOR_INDIVIDUALS, EAD_NEEDS_SPONSORSHIP) == "ineligible"
        assert ("work_auth:no_sponsorship_offered", "unmet") in _work_auth_rows(
            catalog, SPONSOR_INDIVIDUALS, EAD_NEEDS_SPONSORSHIP
        )

    def test_the_span_is_the_offending_clause_not_the_whole_sentence(
        self, catalog: RulesCatalog
    ) -> None:
        """Keystone: the INELIGIBLE must cite the clause that disqualifies, and the
        widened gap must not swallow the sentence. Asserting merely that a span exists
        would pass against a pattern that matched from the first character."""
        result = evaluate(EMPLOYMENT_BASED, EAD_NEEDS_SPONSORSHIP, BLOCKER_ALL, catalog)
        offending = [
            req
            for req in result.requirements
            if req.rule_id == "work_auth:no_sponsorship_without_clause"
            and req.disposition == "unmet"
        ]
        assert offending, "expected the compound without-sponsorship row to be unmet"
        start, end = offending[0].jd_locator["span"]
        assert (
            EMPLOYMENT_BASED[start:end]
            == "without the need for employment-based visa sponsorship"
        )

    def test_a_posting_with_no_sponsorship_language_stays_eligible(
        self, catalog: RulesCatalog
    ) -> None:
        # The control for the widened gaps: an ordinary JD must not become a rejection.
        # The ROWS are the real assertion. The verdict here is `uncertain`, not `eligible`,
        # and that is D-P2-18 working as designed -- a body stating no catalogued
        # requirement at all takes the `_no_evaluable_requirement` branch, because zero
        # rows is never a clean bill of health. Asserting `eligible` here would be
        # asserting the opposite of the keystone.
        assert _work_auth_rows(catalog, NO_SPONSORSHIP_LANGUAGE, EAD_NEEDS_SPONSORSHIP) == []
        assert (
            _verdict(catalog, NO_SPONSORSHIP_LANGUAGE, EAD_NEEDS_SPONSORSHIP) != "ineligible"
        )

    def test_multi_tenancy_a_citizen_clears_both_new_surfaces(
        self, catalog: RulesCatalog
    ) -> None:
        assert _verdict(catalog, EMPLOYMENT_BASED, US_CITIZEN) == "eligible"
        assert _verdict(catalog, SPONSOR_INDIVIDUALS, US_CITIZEN) == "eligible"


#: The over-reach control, kept BESIDE the recall cases as a pair. `test_recall_word_gaps`
#: already owns this sentence; it is repeated here because it is the specific case THIS
#: change threatened, and a reader of this file must see both directions at once.
#:
#: The first attempt at the fix widened `no_sponsorship_offered`'s blind filler gap from
#: {0,2} to {0,3}, which bought "sponsor individuals for employment-based visas" AND this
#: sentence, where a company sponsors a robotics championship. The errors are NOT symmetric:
#: a missed refusal costs one application that could not have been made anyway, while a
#: spurious one writes `ineligible` WITH a quoted span, silently removing a real job from
#: the queue -- and nothing reports that. So the discriminator is the OBJECT NOUN (a person
#: being sponsored FOR a visa), never the distance.
EVENT_SPONSORSHIP = "We do not sponsor the annual robotics-championship visas for students."
PERSON_OBJECT_VARIANTS = (
    "We do not sponsor candidates for employment visas.",
    "The firm does not sponsor applicants for work visas.",
)


class TestSponsorshipRefusalDiscriminatesOnObjectNotDistance:
    def test_event_sponsorship_is_not_a_refusal(self, catalog: RulesCatalog) -> None:
        # Fires nothing at all -- not an abstain, not a MET row. A `no_sponsorship_offered`
        # hit here would be a wrong `ineligible` carrying a real JD span.
        assert _work_auth_rows(catalog, EVENT_SPONSORSHIP, EAD_NEEDS_SPONSORSHIP) == []
        assert _verdict(catalog, EVENT_SPONSORSHIP, EAD_NEEDS_SPONSORSHIP) != "ineligible"

    @pytest.mark.parametrize("body", PERSON_OBJECT_VARIANTS)
    def test_a_person_object_refusal_still_fires(
        self, catalog: RulesCatalog, body: str
    ) -> None:
        assert ("work_auth:no_sponsorship_offered", "unmet") in _work_auth_rows(
            catalog, body, EAD_NEEDS_SPONSORSHIP
        )


# Found by a SILENCE AUDIT, not by reading patterns: over 700 random live bodies, count the
# documents whose text plainly raises a family's topic where that family wrote ZERO rows. As a
# RATE that measure is useless -- `internship` reads 75% because its trigger is a
# self-declaration and never a mention (by design, and worth 40.1% -> 100.0% precision), and
# `degree` reads 79% because "Bachelor's preferred" is a preference. As a DISCOVERY tool it
# works: two of the `work_auth` silences were real, and both are D-436's class.
PASSIVE_REFUSAL = (
    "Legal authorization to work in the United States - Sponsorship will not be provided "
    "for this position."
)
#: The negator sits between the modal and the copula ("will NOT be"), so neither the
#: `(is|are|will be)?` arm nor the `(not|no longer|never)` arm could consume it.
CITIZENS_ONLY_PARENTHETICAL = "US Citizens only (onsite role)."
#: The clause ends in a parenthetical rather than a full stop, and the terminator is what stops
#: the standalone pattern swallowing a sentence that merely BEGINS with the phrase -- so it is
#: widened by one character rather than removed.
SPONSORSHIP_OFFERED = "Sponsorship will be provided for the right candidate."
COMPANY_NAMED_VISA = (
    "Visa is a world leader in payments technology, facilitating transactions worldwide."
)
EEO_BOILERPLATE = (
    "We provide equal employment without regard to race, color, national origin, citizenship, "
    "ancestry, religion, creed, sex, or veteran status."
)


class TestSilenceAuditFindings:
    def test_a_passive_refusal_is_ineligible(self, catalog: RulesCatalog) -> None:
        assert _verdict(catalog, PASSIVE_REFUSAL, EAD_NEEDS_SPONSORSHIP) == "ineligible"
        assert ("work_auth:no_sponsorship_offered", "unmet") in _work_auth_rows(
            catalog, PASSIVE_REFUSAL, EAD_NEEDS_SPONSORSHIP
        )

    def test_a_citizens_only_clause_ending_in_a_parenthetical_fires(
        self, catalog: RulesCatalog
    ) -> None:
        assert ("work_auth:us_citizen_standalone_required", "unmet") in _work_auth_rows(
            catalog, CITIZENS_ONLY_PARENTHETICAL, EAD_NEEDS_SPONSORSHIP
        )

    def test_the_mirror_offer_is_not_read_as_a_refusal(self, catalog: RulesCatalog) -> None:
        """The control the passive arm most needs: `will BE provided` is the OPPOSITE claim and
        must resolve as an OFFER, never a refusal. A widened negation arm that swallowed this
        would reject every posting that offers sponsorship."""
        rows = _work_auth_rows(catalog, SPONSORSHIP_OFFERED, EAD_NEEDS_SPONSORSHIP)
        assert ("work_auth:no_sponsorship_offered", "unmet") not in rows
        assert _verdict(catalog, SPONSORSHIP_OFFERED, EAD_NEEDS_SPONSORSHIP) != "ineligible"

    @pytest.mark.parametrize(
        "body", [COMPANY_NAMED_VISA, EEO_BOILERPLATE], ids=["company_named_visa", "eeo"]
    )
    def test_topic_MENTIONS_stay_silent(self, catalog: RulesCatalog, body: str) -> None:
        """The other half of what the silence audit measured. These are why its RATE overstates:
        a body can raise the topic without stating a requirement, and silence is then correct."""
        assert _work_auth_rows(catalog, body, EAD_NEEDS_SPONSORSHIP) == []
