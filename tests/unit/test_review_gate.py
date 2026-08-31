"""Delivery-time apply/review lane classifier (`delivery/review_gate.lane`).

Fixture strings are calibrated against the live `classify_location` / `role_verdict`
classifiers (2026-08-27): US cities classify `us`; "Kaunas Office" is `unknown`
(city without a country); "Kaunas, Lithuania"/"Zhubei, Taiwan" are `non_us`;
"Front Office Agent"/"Field Auto Appraiser" have no role signal → `uncertain`;
"Registered Nurse Practitioner" matches a deny pattern → `not_swe`. The two role
answers are asserted out loud where they are load-bearing rather than assumed, so a
gate that moves under the fixture fails here instead of passing vacuously.
"""

from __future__ import annotations

from boardwatch.delivery.review_gate import REVIEW_DIR, classify, lane
from boardwatch.rank.role_gate import role_verdict


def test_eligible_always_applies_regardless_of_location_or_role() -> None:
    assert lane(verdict="eligible", locations=["Kaunas, Lithuania"], title="Janitor") == ""


def test_verified_uncertain_us_swe_is_promoted_to_apply() -> None:
    assert (
        lane(
            verdict="uncertain",
            locations=["San Jose, CA, United States"],
            title="Software Engineer",
        )
        == ""
    )


def test_unknown_location_fails_open_to_apply() -> None:
    # A bare "Remote" (and any location the classifier cannot place) reads `unknown`; the location
    # check fails OPEN exactly as the hard US gate does, so it stays in the apply queue. An unlisted
    # foreign city like "Kaunas Office" also reads `unknown` and slips through here — that is a
    # classifier-coverage gap (D-294 pattern), not a reason to demote every remote lead.
    assert lane(verdict="uncertain", locations=["Remote"], title="Software Engineer") == ""
    assert (
        lane(
            verdict="uncertain",
            locations=["Kaunas Office"],
            title="Associate JAVA Software Engineer",
        )
        == ""
    )


def test_uncertain_foreign_location_routes_to_review() -> None:
    assert (
        lane(verdict="uncertain", locations=["Kaunas, Lithuania"], title="Software Engineer")
        == REVIEW_DIR
    )


def test_uncertain_non_swe_role_routes_to_review() -> None:
    assert (
        lane(
            verdict="uncertain",
            locations=["Chicago, Illinois, United States"],
            title="Front Office Agent",
        )
        == REVIEW_DIR
    )
    assert (
        lane(
            verdict="uncertain",
            locations=["USA - NY (Remote)"],
            title="Field Auto Appraiser",
        )
        == REVIEW_DIR
    )


def test_unevaluated_none_verdict_is_treated_like_uncertain() -> None:
    # None (unevaluated) is transient staleness or a body-less lead; location + title still decide.
    assert lane(verdict=None, locations=["Austin, TX"], title="Software Engineer") == ""
    assert lane(verdict=None, locations=["Kaunas, Lithuania"], title="Software Engineer") == REVIEW_DIR
    assert lane(verdict=None, locations=["Austin, TX"], title="Front Office Agent") == REVIEW_DIR


def test_ineligible_is_held_for_review_not_blind_applied() -> None:
    # Excluded upstream in practice; defensive here.
    assert lane(verdict="ineligible", locations=["Austin, TX"], title="Software Engineer") == REVIEW_DIR


def test_empty_locations_fail_open_to_apply() -> None:
    # No location named -> unknown -> fail open (never blind-drop / blind-demote an unplaced lead).
    assert lane(verdict="uncertain", locations=[], title="Software Engineer") == ""


# --------------------------------------------------------------- the reason, one case per branch


def test_ineligible_verdict_names_itself_as_the_reason() -> None:
    assert classify(
        verdict="ineligible", locations=["Austin, TX"], title="Software Engineer"
    ) == (REVIEW_DIR, "ineligible_verdict")


def test_a_confirmed_foreign_location_names_the_location_as_the_reason() -> None:
    # The title is software and the verdict is not ineligible, so location is the ONLY thing that
    # can be holding it. Before this reason existed the row rendered bare.
    assert classify(
        verdict="uncertain", locations=["Kaunas, Lithuania"], title="Software Engineer"
    ) == (REVIEW_DIR, "non_us_location")


def test_a_vetoed_title_and_an_unconfirmed_one_are_DIFFERENT_reasons() -> None:
    """The role gate's veto and its abstain must not share one reason string.

    `Registered Nurse Practitioner` matches a deny pattern (`not_swe`) and `Front Office Agent`
    carries no role signal at all (`uncertain`). Both are held, but only the first is a decision
    the gate made: reporting the second as "not software" would assert a claim it declined to
    make, which is folding an abstain into its neighbour. They therefore differ HERE, at the
    classifier, and not merely in how the page words them.
    """
    assert role_verdict("Registered Nurse Practitioner")[0] == "not_swe"
    assert role_verdict("Front Office Agent")[0] == "uncertain"

    vetoed = classify(
        verdict="uncertain", locations=["Chicago, Illinois, United States"],
        title="Registered Nurse Practitioner",
    )
    unconfirmed = classify(
        verdict="uncertain", locations=["Chicago, Illinois, United States"],
        title="Front Office Agent",
    )
    assert vetoed == (REVIEW_DIR, "role_vetoed")
    assert unconfirmed == (REVIEW_DIR, "role_unconfirmed")
    assert vetoed.reason != unconfirmed.reason


def test_the_apply_lane_carries_no_reason() -> None:
    assert classify(
        verdict="eligible", locations=["Kaunas, Lithuania"], title="Janitor"
    ) == ("", None)
    assert classify(
        verdict="uncertain", locations=["San Jose, CA, United States"], title="Software Engineer"
    ) == ("", None)
    assert classify(verdict="uncertain", locations=["Remote"], title="Software Engineer") == (
        "",
        None,
    )


# --------------------------------------------------------------------------------- they AGREE


#: Every case above and below, as one table. `lane` is a projection of `classify`, so the point of
#: the table is that the projection is not a second opinion: a reason without the lane to match it
#: is exactly how the page and the `_review` folder start disagreeing about one lead (D-332).
_CASES: list[tuple[str | None, list[str], str]] = [
    ("eligible", ["Kaunas, Lithuania"], "Janitor"),
    ("eligible", ["Austin, TX"], "Software Engineer"),
    ("ineligible", ["Austin, TX"], "Software Engineer"),
    ("ineligible", ["Kaunas, Lithuania"], "Front Office Agent"),
    ("uncertain", ["Kaunas, Lithuania"], "Software Engineer"),
    ("uncertain", ["Zhubei, Taiwan"], "Front Office Agent"),
    ("uncertain", ["Chicago, Illinois, United States"], "Front Office Agent"),
    ("uncertain", ["Chicago, Illinois, United States"], "Registered Nurse Practitioner"),
    ("uncertain", ["San Jose, CA, United States"], "Software Engineer"),
    ("uncertain", ["Remote"], "Software Engineer"),
    ("uncertain", [], "Software Engineer"),
    (None, ["Austin, TX"], "Software Engineer"),
    (None, ["Kaunas, Lithuania"], "Software Engineer"),
    (None, ["Austin, TX"], "Front Office Agent"),
]


def test_lane_is_exactly_the_classifiers_lane_and_a_reason_appears_iff_it_is_review() -> None:
    for verdict, locations, title in _CASES:
        decision = classify(verdict=verdict, locations=locations, title=title)
        assert decision.lane == lane(verdict=verdict, locations=locations, title=title)
        assert (decision.reason is not None) == (decision.lane == REVIEW_DIR), (
            verdict,
            locations,
            title,
        )


# ------------------------------------------------- the two requirement gates (R2, D-380)


def test_a_hard_family_abstain_holds_an_otherwise_appliable_lead() -> None:
    """US, software, and past every older gate — held only because a BLOCKING rule abstained.

    This is the lead the fail-open was spending: `uncertain` says the verdict could not be
    settled, but not WHICH requirement was unsettled, so a work_auth or clearance abstain was
    indistinguishable from a clean lead and rode into the blindly-appliable queue.
    """
    assert classify(
        verdict="uncertain",
        locations=["San Jose, CA, United States"],
        title="Software Engineer",
        eligibility_unconfirmed=True,
    ) == (REVIEW_DIR, "eligibility_unconfirmed")


def test_an_unconfirmed_experience_bar_holds_an_otherwise_appliable_lead() -> None:
    assert classify(
        verdict="uncertain",
        locations=["San Jose, CA, United States"],
        title="Software Engineer",
        experience_unconfirmed=True,
    ) == (REVIEW_DIR, "experience_requirement")


def test_the_two_new_holds_are_DIFFERENT_reasons_and_the_abstain_OUTRANKS_the_bar() -> None:
    """Both hold the lead, and when both apply the abstain is the one reported.

    Same principle as `role_vetoed` vs `role_unconfirmed`: the reader acts on them
    differently. A blocking rule that could not be decided has to be resolved before anything
    is spent; a stated experience bar is a lead that may still be worth applying to. Reporting
    the weaker one when both hold would understate the hold.
    """
    both = classify(
        verdict="uncertain",
        locations=["San Jose, CA, United States"],
        title="Software Engineer",
        experience_unconfirmed=True,
        eligibility_unconfirmed=True,
    )
    assert both == (REVIEW_DIR, "eligibility_unconfirmed")
    experience_only = classify(
        verdict="uncertain",
        locations=["San Jose, CA, United States"],
        title="Software Engineer",
        experience_unconfirmed=True,
    )
    assert both.reason != experience_only.reason


def test_an_earlier_gate_still_wins_over_the_new_flags() -> None:
    """Precedence is unchanged where it already existed: the flags are the LAST gates.

    A foreign lead carrying an unconfirmed bar is still reported as foreign — the location is
    the stronger, already-decided fact, and relabelling it would lose the reason the reader
    needs. Without this the two new branches could silently capture leads the older gates own.
    """
    assert classify(
        verdict="uncertain",
        locations=["Kaunas, Lithuania"],
        title="Software Engineer",
        experience_unconfirmed=True,
        eligibility_unconfirmed=True,
    ) == (REVIEW_DIR, "non_us_location")
    assert classify(
        verdict="uncertain",
        locations=["Chicago, Illinois, United States"],
        title="Registered Nurse Practitioner",
        eligibility_unconfirmed=True,
    ) == (REVIEW_DIR, "role_vetoed")


def test_both_flags_false_is_byte_for_byte_the_old_behaviour() -> None:
    """The defaults are the old contract, so every un-updated call site is unaffected."""
    for verdict, locations, title in _CASES:
        assert classify(verdict=verdict, locations=locations, title=title) == classify(
            verdict=verdict,
            locations=locations,
            title=title,
            experience_unconfirmed=False,
            eligibility_unconfirmed=False,
        )


def test_lane_projects_the_new_gates_too() -> None:
    """`lane` must not become a second opinion now that `classify` takes more inputs."""
    for experience, eligibility in ((False, False), (True, False), (False, True), (True, True)):
        decision = classify(
            verdict="uncertain",
            locations=["San Jose, CA, United States"],
            title="Software Engineer",
            experience_unconfirmed=experience,
            eligibility_unconfirmed=eligibility,
        )
        assert decision.lane == lane(
            verdict="uncertain",
            locations=["San Jose, CA, United States"],
            title="Software Engineer",
            experience_unconfirmed=experience,
            eligibility_unconfirmed=eligibility,
        )
        assert (decision.reason is not None) == (decision.lane == REVIEW_DIR)
