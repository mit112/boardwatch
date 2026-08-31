"""The word-gap audit of `rules.yaml` (2026-08-31): every `\\w+` gap that cannot cross a
hyphen, every clause gap that a `.` inside an abbreviation ends, and one `consumes_cues`
omission that made a matching pattern drop itself.

All of these are DETECTION fixes. The resolver was never the problem in any of them -- each
sentence below produced ZERO rows, and a routing or severity change cannot move a requirement
that was never detected.

WHY EACH ROW CARRIES A CONTROL. A `\\w+` -> `[\\w-]+` widening is invisible in a green suite:
the pattern that missed the hyphen also matches the un-hyphenated sentence, so a test that
only asserts the fixed form passes against the broken catalog too. Every fix here is therefore
pinned as a PAIR -- the hyphenated span that used to miss, and the near-identical span that
already matched -- so the assertion is attributable to the gap and not to the vocabulary
around it.

WHY THE NEGATIVE HALF IS LOAD-BEARING. Widening work_auth or clearance pushes toward MORE
`ineligible`, the direction that silently deletes a real job. So each family also pins the
span that most nearly looks like the one it must catch and must NOT fire, and every
citizenship, authorization and clearance span is asserted `met` for someone it should clear.
A pattern that cannot clear anyone is a blanket veto wearing a rule's name.

WHAT `[\\w-]+` CANNOT DO, and why the widening is bounded rather than trusted. The engine's
clause boundaries are `[;:,]` plus `and|but|while|whereas` (`detect.py`), and `[\\w-]+`
consumes none of them, so a widened gap still cannot span what the engine counts as two
clauses. The abbreviation dot is scoped `\\.(?=\\s*[A-Za-z]\\.)` for the same reason: a bare
`.` would re-admit the sentence-final periods `_SENTENCE_SPLIT` exists to protect.
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
#: A holder who declares a future sponsorship need: the facts that make a sponsorship or
#: citizenship restriction DECIDE rather than abstain.
EAD = Facts(
    work_authorization=WorkAuthFact(status="ead_or_similar", jurisdiction="us",
                                    needs_sponsorship=True),
    security_clearance=ClearanceFact(level="none", state="none", obtainable=False),
    total_years_experience=1,
)
#: THE MULTI-TENANCY GUARD. Every span a widening reaches must still clear someone.
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
# `consumes_cues`: a matching pattern that drops itself
# --------------------------------------------------------------------------------------

WILL_NEVER = "We will never consider candidates who require visa sponsorship."
WILL_NOT = "We will not consider candidates who require visa sponsorship."


def test_the_never_form_of_will_not_consider_is_detected(catalog: RulesCatalog) -> None:
    """`will never` is IN the pattern's refusal alternation, so the regex always matched.

    It was then dropped as cue-inside, because `never` is a declared negation cue and this
    rule's `consumes_cues` listed only `not`/`cannot`/`won't`/`no`. That reads exactly like a
    recall gap while being a polarity bug -- the same shape the sibling
    `no_sponsorship_offered` already closed, which declares `never`, `neither` and `nor`.
    """
    assert _rules(catalog, WILL_NEVER, EAD, "work_auth") == {"no_sponsorship_will_not_consider"}
    assert _verdict(catalog, WILL_NEVER, EAD) == "ineligible"


def test_the_not_form_is_the_control_that_already_matched(catalog: RulesCatalog) -> None:
    """Attributes the fix to the cue declaration rather than to the pattern text.

    Without this row the test above passes against a catalog whose whole refusal alternation
    was rewritten, and the assertion would not be about `consumes_cues` at all.
    """
    assert _rules(catalog, WILL_NOT, EAD, "work_auth") == {"no_sponsorship_will_not_consider"}
    assert _verdict(catalog, WILL_NOT, EAD) == "ineligible"


@pytest.mark.parametrize("body", [WILL_NEVER, WILL_NOT])
def test_a_citizen_clears_both_forms(catalog: RulesCatalog, body: str) -> None:
    """The restriction is MET by someone who needs no sponsorship, in both surfaces."""
    assert _verdict(catalog, body, CITIZEN) == "eligible"


def test_a_never_refusal_about_something_else_fires_nothing(catalog: RulesCatalog) -> None:
    """The cue declaration widens ONE rule, not the family.

    `never` now being consumable must not let the rule attach to a refusal that names no
    sponsorship at all -- the sentence carries `never` and `without` and must still produce
    zero work_auth rows.
    """
    body = "We will never consider candidates without a strong systems background."
    assert _rules(catalog, body, EAD, "work_auth") == set()


# --------------------------------------------------------------------------------------
# HYPHEN, sponsorship: `\w+` cannot cross a hyphen
# --------------------------------------------------------------------------------------

#: The span the bug report was written about, and the highest-volume work_auth gate.
IMMIGRATION_RELATED = "We do not provide immigration-related sponsorship for this role."
#: Its un-hyphenated twin, which already matched. This is what attributes the fix to the gap.
PLAIN_VISA = "We do not provide visa sponsorship for this role."
VISA_RELATED = "We will not consider applicants requiring visa-related sponsorship."
PLAIN_REQUIRING = "We will not consider applicants requiring visa sponsorship."


@pytest.mark.parametrize(
    "body,rule",
    [
        (IMMIGRATION_RELATED, "no_sponsorship_offered"),
        (PLAIN_VISA, "no_sponsorship_offered"),
        (VISA_RELATED, "no_sponsorship_will_not_consider"),
        (PLAIN_REQUIRING, "no_sponsorship_will_not_consider"),
    ],
)
def test_a_hyphenated_modifier_no_longer_hides_a_sponsorship_refusal(
    catalog: RulesCatalog, body: str, rule: str
) -> None:
    """Each hyphenated span is paired with the plain span that already matched.

    The pair is the point. `immigration-related` and `visa-related` sit inside a word gap
    bounded at 4 and 3 words; `\\w+` stopped at the hyphen and the whole pattern failed, so the
    sentence produced ZERO rows and cleared by silence. Widening only the two UNGUARDED
    restriction-body gaps leaves the jurisdiction wrapper byte-identical to its
    `sponsorship_available` sibling, which is the parity findings 125-139 are about.
    """
    assert _rules(catalog, body, EAD, "work_auth") == {rule}
    assert _verdict(catalog, body, EAD) == "ineligible"


@pytest.mark.parametrize(
    "body", [IMMIGRATION_RELATED, PLAIN_VISA, VISA_RELATED, PLAIN_REQUIRING]
)
def test_a_citizen_clears_every_widened_sponsorship_span(
    catalog: RulesCatalog, body: str
) -> None:
    assert _verdict(catalog, body, CITIZEN) == "eligible"


def test_the_hyphen_reaches_the_bare_sponsor_verb_arm_too(catalog: RulesCatalog) -> None:
    """The second arm takes an immigration OBJECT rather than the word `sponsorship`."""
    body = "We cannot sponsor employment-based visas."
    assert _rules(catalog, body, EAD, "work_auth") == {"no_sponsorship_offered"}
    assert _verdict(catalog, body, CITIZEN) == "eligible"


@pytest.mark.parametrize(
    "body",
    [
        # A hyphenated compound that is NOT about immigration must stay at zero rows: the
        # widening admits the hyphen into the gap, it does not relax the object vocabulary.
        "We do not offer employer-paid relocation packages.",
        "We do not provide relocation or immigration-related legal advice.",
        # The word-count bound is still load-bearing after the widening: three words of gap
        # exceeds the {0,2} bound on the bare-verb arm.
        "We do not sponsor the annual robotics-championship visas for students.",
    ],
)
def test_a_hyphenated_compound_that_is_not_a_refusal_fires_nothing(
    catalog: RulesCatalog, body: str
) -> None:
    assert _rules(catalog, body, EAD, "work_auth") == set()
