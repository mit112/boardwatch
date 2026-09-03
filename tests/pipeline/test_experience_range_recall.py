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
# The degree-vs-experience disjunction is INCONSISTENT ACROSS THE FAMILY — pinned, NOT fixed.
#
# `total_years_minimum` and `range_years_minimum` carry `degree_alternative_to_years`; the six
# scoped/domain minimum patterns do not. So "a Bachelor's OR N years of X experience" ABSTAINS
# when it lands on the total arm and REJECTS when it lands on a scoped one -- same sentence,
# opposite outcome, decided by which pattern happened to match.
#
# NOT fixed here, and the reason is not effort. Wiring the escape to the other six was built and
# measured: it moves 365 SWE+US postings from `ineligible` to `uncertain`. But `abstain_by` is
# DOCUMENT-scoped -- the catalog's own comment says an escape "ELSEWHERE in the posting may
# waive it" -- so wiring it means a JD stating "Bachelor's or 4 years" for its general bar also
# waives a separate "8+ years of C++". Whether a disjunction reaches a SCOPED bar is a claim
# about what the disjunction MEANS, not a consistency repair, and it is the owner's (row A8).
#
# The widening above does NOT extend it: measured, 0 of the 17 SWE+US postings this change
# demotes carry a disjunction at all. The two were separable and the coupling was rhetorical.
# ---------------------------------------------------------------------------------------

#: Verbatim from the live store. Each clears on the DEGREE arm, so today's `ineligible` removes
#: a job the owner can actually get -- and the reject pile is never inspected, so nothing
#: downstream will ever contradict it. This test asserts the DEFECT so it stays visible.
DEGREE_DISJUNCTIONS_ON_A_SCOPED_ARM = [
    # Already broken at {0,2} -- this is the pre-existing defect, not something this change made.
    "Bachelor's degree or 5+ years of software engineering experience.",
    # And this one the widening DOES newly reach, which is stated rather than hidden: at {0,2} it
    # wrote no row and read `uncertain` by silence; it now reads `ineligible` by a bar whose
    # disjunction the scoped arm cannot see. Measured over the live store, ZERO of the 17 SWE+US
    # postings this change demotes carry a disjunction, so the class is real and currently empty.
    "Bachelor's degree or 5+ years of full stack software engineering experience.",
]


@pytest.mark.parametrize("body", DEGREE_DISJUNCTIONS_ON_A_SCOPED_ARM)
def test_a_disjunction_on_a_SCOPED_arm_still_rejects_and_that_is_the_open_defect(
    catalog: RulesCatalog, body: str
) -> None:
    """PINS A DEFECT, deliberately. If this starts failing, someone wired the escape to the
    scoped patterns -- which is row A8 and the owner's call, not a green-tests decision."""
    assert _verdict(catalog, body, NEW_GRAD) == "ineligible", body


def test_the_SAME_sentence_on_the_TOTAL_arm_abstains(catalog: RulesCatalog) -> None:
    """The asymmetry itself, in one assertion: identical semantics, opposite verdicts, and the
    only difference is which pattern the phrasing happens to reach."""
    assert _verdict(catalog, "Bachelor's degree or 5+ years of experience.", NEW_GRAD) != "ineligible"
    assert _verdict(
        catalog, "Bachelor's degree or 5+ years of software engineering experience.", NEW_GRAD
    ) == "ineligible"
