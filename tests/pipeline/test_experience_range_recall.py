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
