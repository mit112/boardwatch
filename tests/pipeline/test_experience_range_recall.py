"""A RANGE could never reach the scoped tail, so the commonest way a JD states an experience
bar produced no requirement row at all.

The 2026-08-30 queue audit measured it: of 420 apply-lane leads, 168 stated a bar of 3+ years and
56 of those produced NO `experience_years` row, so nothing downstream could hold them — a routing
change cannot move a requirement that was never detected.

Neither existing rule could fire on `3-6 years of professional software engineering experience`:

* `scoped_years_minimum` is blocked at the LOW number (no bare `years` follows `3`) and at the
  HIGH number (its `(?<![-–—\\d])` lookbehind, which exists precisely to stop it reading `6` as a
  standalone bar).
* `range_years_minimum` demands `experience` immediately after the adjective run, so any domain
  noun ("... professional SOFTWARE ENGINEERING experience") ends the match, as does `experience IN`
  and `experience AS` — both excluded by its trailing negative lookahead.

`scoped_range_years_minimum` / `_activity` are the range head of `range_years_minimum` spliced onto
the scoped and activity tails verbatim. Every assertion below FAILS against the pre-fix catalog.
"""

from __future__ import annotations

import pytest

from boardwatch.eligibility.catalog import RulesCatalog, load_rules
from boardwatch.eligibility.engine import evaluate
from boardwatch.eligibility.facts import Facts, Policy

BLOCKER_ALL = Policy(
    families={
        f: "blocker"
        for f in ("work_auth", "clearance", "experience_years", "internship",
                  "contract_not_fte", "degree")
    }
)
NEW_GRAD = Facts(total_years_experience=1)
#: Ten years in, so the same bar is MET. The multi-tenancy guard: a new pattern that cannot
#: clear anyone is a blanket veto wearing a rule's name.
SENIOR = Facts(total_years_experience=10)


@pytest.fixture()
def catalog(tmp_path_factory: pytest.TempPathFactory) -> RulesCatalog:
    return load_rules(tmp_path_factory.mktemp("no-override"))


def _rows(catalog: RulesCatalog, body: str, facts: Facts) -> list[tuple[str, str]]:
    return [
        (r.rule_id or "", r.disposition)
        for r in evaluate(body, facts, BLOCKER_ALL, catalog).requirements
        if (r.rule_id or "").startswith("experience_years:")
    ]


def _verdict(catalog: RulesCatalog, body: str, facts: Facts) -> str:
    return evaluate(body, facts, BLOCKER_ALL, catalog).verdict


#: Every shape is a real sentence taken from a posting that was sitting in the apply queue.
RANGE_BARS = [
    "3-6 years of professional software engineering experience.",
    "3–6 years of professional software engineering experience.",  # EN-DASH, not a hyphen
    "6-8 years of relevant experience in managing complex compute infrastructure.",
    "4-8 years of professional experience in a DevOps, infrastructure, or software role.",
    "3-5+ years of experience in DevOps, Systems Engineering, or Software Development.",
    "6-10 years of relevant experience in an Apps Development role.",
    "3-6 years of professional front-end web development experience.",
    "5–6 years of experience as a backend-focused software engineer.",
    "Minimum of 3-5 years of experience in software engineering.",
]

#: The activity form: a range followed by a gerund rather than by "experience".
RANGE_ACTIVITIES = [
    "3-7 years working with a variety of programming languages such as Rust, Go and Python.",
    "3–5 years shipping commercial mobile apps on Android or iOS.",
]


@pytest.mark.parametrize("body", RANGE_BARS + RANGE_ACTIVITIES)
def test_a_scoped_range_is_DETECTED_and_never_clears_a_new_grad(
    catalog: RulesCatalog, body: str
) -> None:
    """The defect was SILENCE: no row at all, so nothing downstream could hold the lead.

    The claim is therefore detection plus a non-`met` disposition, NOT `ineligible`. Whether an
    unconfirmed bar becomes `ineligible` or `uncertain` is the resolver's call and depends on
    D-333's near-miss band -- a floor of 3 against a 1-year profile sits INSIDE the band and
    abstains. Either way the row now exists, which is what lets the delivery lane route it.
    Asserting `ineligible` here would pin the band, not the pattern, and would go red the day
    the band moves.
    """
    rows = _rows(catalog, body, NEW_GRAD)
    assert rows, f"no experience row at all -- the exact defect this closes: {body}"
    assert all(d != "met" for _, d in rows), rows
    assert _verdict(catalog, body, NEW_GRAD) != "eligible"


@pytest.mark.parametrize(
    "body",
    [
        "6-8 years of relevant experience in managing complex compute infrastructure.",
        "6-10 years of relevant experience in an Apps Development role.",
        "4-8 years of professional experience in a DevOps, infrastructure, or software role.",
    ],
)
def test_a_floor_CLEAR_of_the_near_miss_band_resolves_unmet(
    catalog: RulesCatalog, body: str
) -> None:
    """Above the band the row DECIDES rather than abstaining, and the lead is ineligible.

    This is the half of the behaviour the band hides in the test above, and it is what proves
    the captured `years` really is the floor and really reaches the resolver.
    """
    assert _verdict(catalog, body, NEW_GRAD) == "ineligible"
    assert any(d == "unmet" for _, d in _rows(catalog, body, NEW_GRAD))


@pytest.mark.parametrize("body", RANGE_BARS + RANGE_ACTIVITIES)
def test_the_same_bar_CLEARS_someone_who_meets_it(catalog: RulesCatalog, body: str) -> None:
    """The floor of the range is what decides, so ten years clears every one of them.

    Asserted on the ROW, not the verdict: these fixtures declare only `total_years_experience`,
    so the other blocker families abstain and the document can never reach `eligible`. A verdict
    assertion here would be testing the fixture's silence, not the pattern.

    And the claim is NOT-`unmet` rather than `met`, because `met` is unreachable for a SCOPED bar
    by design (D-319): a duration scoped to one skill cannot exceed the career it sits inside, so
    `total < need` decides UNMET, while a total that clears the floor still cannot prove that many
    years *of that domain* and abstains. These inherit that semantics from the twins they splice,
    which is the point — the guard here is that the bar does not BLOCK someone who meets it.
    """
    rows = _rows(catalog, body, SENIOR)
    assert rows, "the range must still be DETECTED for someone who meets it"
    assert all(d != "unmet" for _, d in rows), rows


def test_the_LOW_end_of_the_range_is_the_bar(catalog: RulesCatalog) -> None:
    """`2-12+ years` is a 2-year bar, not a 12-year one — the conservative read, and the same
    one `range_years_minimum` already takes. A pattern that captured the ceiling would call a
    3-year candidate ineligible against a bar they clear."""
    body = "2-12+ years of industry software engineering experience."
    low = _rows(catalog, body, Facts(total_years_experience=1))
    assert low and all(d != "met" for _, d in low), low
    # 5 clears a 2-year floor; it would NOT clear a 12-year ceiling, which is the whole point.
    cleared = _rows(catalog, body, Facts(total_years_experience=5))
    assert cleared and all(d != "unmet" for _, d in cleared), cleared


def test_a_company_side_range_does_NOT_block(catalog: RulesCatalog) -> None:
    """The suppressors are inherited from the twins, and this is what they are for: a range in
    a sentence about the COMPANY is not a bar on the applicant."""
    body = "Our team has 10-15 years of combined software engineering experience."
    assert _verdict(catalog, body, NEW_GRAD) != "ineligible"


def test_a_HEDGED_range_does_NOT_hard_block(catalog: RulesCatalog) -> None:
    """`years_hedges` stands the required form down; `range_years_preferred` already owns this
    sentence. Without the inherited hedge suppressor a preference would read as a veto."""
    body = "3-6 years of professional software engineering experience preferred."
    assert _verdict(catalog, body, NEW_GRAD) != "ineligible"


def test_company_history_prose_is_untouched(catalog: RulesCatalog) -> None:
    """Not a range, and not a requirement. These sentences are why the audit's raw text scan
    over-counted, and a pattern that fired here would veto on a company's founding date."""
    for body in (
        "For more than 90 years, our innovative drive has kept us ahead of our customers.",
        "Here we are 25 years later, having pioneered an industry.",
        "30+ years of pioneering robotics research.",
    ):
        assert _verdict(catalog, body, NEW_GRAD) != "ineligible", body


def test_the_non_range_twins_still_behave(catalog: RulesCatalog) -> None:
    """The splice must not disturb the patterns it was cut from."""
    assert _verdict(catalog, "5+ years of professional software engineering experience.", NEW_GRAD) == "ineligible"
    assert _verdict(catalog, "5+ years of experience.", NEW_GRAD) == "ineligible"


# ---------------------------------------------------------------------------------------
# The FOUR-modifier domain phrase (D-447).
#
# `5+ years of professional software engineering experience` already worked: `professional` is
# a listed adjective and `software engineering` is two arbitrary words, inside the {0,2} run.
# `5+ years of full stack software engineering experience` did NOT, because `full stack
# software engineering` is four. One word over, and the posting wrote no row at all.
#
# Every sentence below is a real span from the live store, and each is the reason the window
# moved. Measured before shipping, over all 138,677 open bodies: the widening adds 2,355
# matches across 1,474 distinct spans, and every one of them begins with a year count.
# ---------------------------------------------------------------------------------------

#: Verbatim from postings that produced ZERO `experience_years` rows at {0,2}. The titles they
#: came from are Senior, Staff, Lead, Principal and Vice President -- exactly the too-senior
#: postings that were reaching the apply lane as blindly-appliable.
FOUR_MODIFIER_BARS = [
    "5+ years of full stack software engineering experience.",
    "6+ years of Full Stack software engineering experience.",
    "10+ years of Full Stack software engineering experience.",
    "4+ years of full stack software engineering experience.",
    "5+ years of full stack software development experience.",
    "5+ years of full software development lifecycle experience.",
    "7 years minimum professional software development experience.",
    "5+ years of related big data engineering experience.",
    "5+ years of data engineering related development experience.",
    "5+ years of full time Software Engineering experience.",
    "6+ years of enterprise full stack engineering experience.",
    "8+ years of NAND design relevant proven experience.",
]

#: The same form UNDER the near-miss ceiling. It must write a row and NOT reject -- the row is
#: the fix, `uncertain` is D-333's band doing its job, and conflating the two would let a later
#: ceiling change silently look like a recall regression.
FOUR_MODIFIER_BARS_INSIDE_THE_BAND = [
    "3+ years of non-internship professional software development experience.",
    "2+ years of full stack software engineering experience.",
]


@pytest.mark.parametrize("body", FOUR_MODIFIER_BARS)
def test_a_four_modifier_domain_phrase_is_read_as_a_bar(catalog: RulesCatalog, body: str) -> None:
    """Each of these FAILS against the {0,2} catalog, which is what makes the widening
    non-vacuous: at {0,2} they produce no row, so the verdict is `uncertain`, not `ineligible`."""
    assert _verdict(catalog, body, NEW_GRAD) == "ineligible", body


@pytest.mark.parametrize("body", FOUR_MODIFIER_BARS_INSIDE_THE_BAND)
def test_a_four_modifier_bar_inside_the_near_miss_band_writes_a_row_and_abstains(
    catalog: RulesCatalog, body: str
) -> None:
    """The recall fix and the near-miss band are separate claims, so they are asserted apart.

    At {0,2} these wrote NOTHING, which is `uncertain` by silence -- indistinguishable from a JD
    that states no bar. Now they write a row that resolves `unknown`, which is `uncertain` for a
    stated REASON. Same verdict, completely different evidence chain, and only the second can be
    reviewed.
    """
    result = evaluate(body, NEW_GRAD, BLOCKER_ALL, catalog)
    rows = [i for i in result.requirements if (i.rule_id or "").startswith("experience_years:")]
    assert rows, body
    assert result.verdict != "ineligible", body


@pytest.mark.parametrize("body", FOUR_MODIFIER_BARS)
def test_the_same_bars_CLEAR_a_senior_profile(catalog: RulesCatalog, body: str) -> None:
    """The multi-tenancy guard, restated for the wider window: a run that cannot clear anyone is
    a blanket veto wearing a rule's name. Ten years in, none of these may reject."""
    assert _verdict(catalog, body, SENIOR) != "ineligible", body


def test_the_widening_does_not_reach_a_FIFTH_word(catalog: RulesCatalog) -> None:
    """{0,3} is a measured stopping point, not a step toward {0,4} (D-447).

    Each extra word is another clause boundary the run may cross. This pins the boundary so a
    later widening is a deliberate act with its own span read, not a quiet increment.
    """
    assert _verdict(
        catalog, "5+ years of one two three four five experience.", NEW_GRAD
    ) != "ineligible"


@pytest.mark.parametrize(
    "body",
    [
        # A CEILING, not a floor -- the `(?<!to\s)` guard, still holding at the wider window.
        "Up to 3 years of professional software development lifecycle experience.",
        # Company tenure. The subject suppressor must still win over four modifiers.
        "Our engineering team has 25 years of full stack software engineering experience.",
        "We bring 30 years of deep enterprise data platform experience to every engagement.",
        # A stated PREFERENCE read as a hard floor is the worst verdict this family can produce.
        "5+ years of full stack software engineering experience preferred.",
        "Ideally 6+ years of Full Stack software engineering experience.",
    ],
)
def test_the_wider_window_does_not_defeat_an_existing_guard(catalog: RulesCatalog, body: str) -> None:
    """The widening adds reach, and reach is exactly what walks into a suppressor's blind spot.

    These are the four guards `scoped_years_minimum` already carries -- the `to` lookbehind, the
    company-side subject, the hedge vocabulary and the degree disjunction -- each re-asserted
    with four modifiers in the span, because a guard verified at two words is not verified at
    four.
    """
    assert _verdict(catalog, body, NEW_GRAD) != "ineligible", body


# ---------------------------------------------------------------------------------------
# The degree-vs-experience disjunction, now SENTENCE-SCOPED across the family — and this
# block is the record of WHY, because it used to pin the opposite.
#
# `total_years_minimum` and `range_years_minimum` have carried `degree_alternative_to_years`
# since D-073; the six scoped/domain minimum patterns did not. So "a Bachelor's OR N years of
# X experience" ABSTAINED when the phrasing landed on the total arm and REJECTED when it
# landed on a scoped one — same semantics, opposite verdict, decided by whether the JD wrote
# the word `software`. This file asserted that as a DEFECT rather than fixing it, because
# whether a disjunction reaches a SCOPED bar is a claim about what the disjunction MEANS, not
# a consistency repair, and the claim was the owner's to make (row A8, D-449).
#
# HE MADE IT. Asked whether "Bachelor's degree or 5+ years of software engineering
# experience" rules out a master's holder, he ruled it does not: "because of the wording of
# 'or', degree should clear it."
#
# THE RULING IS EXACTLY AS WIDE AS THE SENTENCE, because the word `or` is the reason he gave.
# Where an `or` joins the degree clause to the years bar, the degree clears the bar; where the
# two sit in different sentences with no `or` between them, nothing clears it — which is the
# owner's SEPARATE, earlier ruling, and 7 live postings rest on it. So the escape wired onto
# the six scoped/domain patterns is `abstain_by_sentence`, evaluated inside the sentence
# carrying the bar. The document-scoped `abstain_by` wiring D-447 built and D-449 refused
# would have fixed the class below and broken the cross-sentence one in the same change.
# ---------------------------------------------------------------------------------------

#: The first two are VERBATIM from the live store; the third is the sentence the owner was
#: actually shown, which is also D-449's own worked example.
#:
#: THE SECOND ONE IS THE POPULATION, AND IT IS NOT THE SHAPE THE OWNER WAS ASKED ABOUT.
#: Measured over all 147,642 open bodies, 996 postings move and 232 of them are SWE+US — and
#: of those 232, exactly ONE reads "degree OR N years". 219 read "BS + N years OR MS + M
#: years", where the degree arm carries its own floor, so a master's does not clear it on its
#: own. That is deliberately in the list rather than hidden from it: `degree_alternative_to_
#: years` has abstained on precisely these sentences on the TOTAL arm since D-073, so what
#: this change does is stop the arms disagreeing — it does not widen what the escape MEANS.
#: The direction is the safe one either way (abstain, never delete), and the two-stage gate
#: is what decides an abstained row.
SAME_SENTENCE_DISJUNCTIONS_ON_A_SCOPED_ARM = [
    # Live store, and the owner's literal shape: one bar, two paths, joined by `OR`.
    "Bachelor's degree in engineering, computer science, or STEM discipline; "
    "OR 9+ years of professional experience as a software engineer",
    # Live store, and the shape 219 of the 232 SWE+US moves actually carry.
    "Bachelor's degree in Computer Science, AI, Electrical Engineering, Computer "
    "Engineering, or related fields plus at least 6 years of experience developing AI and "
    "ML algorithms or technologies, or Master's degree plus at least 4 years of experience "
    "developing AI and ML algorithms.",
    # D-449's worked example, and the sentence the owner was shown verbatim.
    "Bachelor's degree or 5+ years of software engineering experience.",
    # The range sibling is wired too, and reaches the escape by its degree-AFTER arm. The
    # floor is 6, deliberately CLEAR of D-333's 3-year near-miss band: at "3-6" the band
    # abstains the row on its own and the case would pass with the escape absent, which is a
    # test of the band rather than of this change.
    "6-8 years of software engineering experience or a Bachelor's degree is required.",
]


@pytest.mark.parametrize("body", SAME_SENTENCE_DISJUNCTIONS_ON_A_SCOPED_ARM)
def test_a_SAME_sentence_disjunction_on_a_scoped_arm_no_longer_rejects(
    catalog: RulesCatalog, body: str
) -> None:
    """The owner's ruling, as a verdict. The row still EXISTS — abstaining is not dropping,
    and dropping would return `eligible` by silence — it is merely undecidable."""
    rows = _rows(catalog, body, NEW_GRAD)
    assert rows, f"the bar must still be detected, only undecided: {body}"
    assert _verdict(catalog, body, NEW_GRAD) != "ineligible", body


def test_the_escape_still_cannot_bridge_a_FOUR_WORD_domain_phrase(catalog: RulesCatalog) -> None:
    """A NAMED RESIDUAL, pinned rather than fixed, and it is not a scope problem.

    D-447 widened the BAR's arbitrary-word run to {0,3} so `5+ years of full stack software
    engineering experience` writes a row at all. `degree_alternative_to_years` has its own,
    separate window — `[^.\n]{0,25}?experience` between the years and the noun — and 35
    characters of domain phrase do not fit it. So the escape does not match this sentence,
    the bar is decided, and the posting is still `ineligible`.

    That is OUTSIDE the owner's ruling, which was about whether an `or` reaches the bar, not
    about how many words an escape may cross. Widening this second window is its own change
    with its own span read, exactly as {0,3} was — and this assertion is what makes it a
    deliberate act rather than a quiet increment.
    """
    body = "Bachelor's degree or 5+ years of full stack software engineering experience."
    assert _verdict(catalog, body, NEW_GRAD) == "ineligible"


def test_the_TOTAL_and_SCOPED_arms_now_agree(catalog: RulesCatalog) -> None:
    """The asymmetry itself, in one assertion — and it is now an equality.

    Identical semantics, and the only difference between the two sentences is which pattern
    the phrasing happens to reach. Before the ruling the second was `ineligible`.
    """
    assert _verdict(catalog, "Bachelor's degree or 5+ years of experience.", NEW_GRAD) != "ineligible"
    assert _verdict(
        catalog, "Bachelor's degree or 5+ years of software engineering experience.", NEW_GRAD
    ) != "ineligible"


def test_a_CROSS_sentence_disjunction_still_rejects_a_separate_skill_bar(
    catalog: RulesCatalog,
) -> None:
    """THE OWNER'S OTHER RULING, pinned at the verdict so a later widening cannot take it
    back quietly.

    A degree disjunction stated for the general bar does NOT waive a separate `8+ years of
    C++` elsewhere in the posting: there is no `or` joining them, which is the same reasoning
    that clears the same-sentence case above. This is the assertion that fails if the escape
    is ever moved to document scope, and 7 live postings are what it protects.
    """
    body = (
        "A Bachelor's degree in CS or 3+ years of experience is required.\n"
        "8+ years of C++ experience is required."
    )
    rows = _rows(catalog, body, NEW_GRAD)
    assert any(d == "unmet" for _, d in rows), rows
    assert _verdict(catalog, body, NEW_GRAD) == "ineligible"
