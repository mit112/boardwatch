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

from boardwatch.delivery.review_gate import (
    CLOSED_DIR,
    REVIEW_DIR,
    LaneDecision,
    classify,
    lane,
)
from boardwatch.rank.role_gate import role_verdict


def test_eligible_still_faces_the_location_and_role_gates() -> None:
    """R1, and it REVERSES `test_eligible_always_applies_regardless_of_location_or_role`.

    `eligible` used to short-circuit above both gates, so an eligible posting was
    blindly-appliable however foreign or however far from software it was. The 2026-08-30
    audit found a "Field Auto Adjuster" marked eligible sitting in the apply queue, and an
    independent blind judge scored 5 role-family mismatches in 80 apply-lane items against a
    comparison system's 0 in 80. Eligibility answers the six blocker families; it says nothing
    about whether the role is software or the office is in the US.
    """
    assert lane(verdict="eligible", locations=["Kaunas, Lithuania"], title="Janitor") == REVIEW_DIR
    assert classify(
        verdict="eligible", locations=["Kaunas, Lithuania"], title="Software Engineer"
    ) == LaneDecision(REVIEW_DIR, "non_us_location")
    # `role_unconfirmed`, not `role_vetoed`: the title carries no software signal rather than a
    # positive veto. That is the reason ALL FIVE items this gate moves on the live queue read
    # `role=uncertain` — R1's population is the unconfirmed, not the vetoed.
    assert classify(
        verdict="eligible", locations=["Austin, TX"], title="Field Auto Adjuster"
    ) == LaneDecision(REVIEW_DIR, "role_unconfirmed")
    # ...and a confirmed US software role is still promoted, so the gate narrows rather than vetoes.
    assert lane(verdict="eligible", locations=["Austin, TX"], title="Software Engineer") == ""


def test_eligible_short_circuits_above_the_requirement_flag_gates() -> None:
    """The SCOPE of R1, and the reason it does not open D-380's known R2 gap.

    `eligible` falls through location and role, and stops there. Those flags ignore family
    SEVERITY — which is policy-level and not stored per row — so a `preference`-family row that
    could never block would hold an eligible lead for review. D-380 records that gap as reachable
    only once this short-circuit moves BELOW the flags; this asserts it has not.
    """
    assert lane(
        verdict="eligible",
        locations=["Austin, TX"],
        title="Software Engineer",
        experience_unconfirmed=True,
        eligibility_unconfirmed=True,
    ) == ""


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
    # check fails OPEN exactly as the hard US gate does, so it stays in the apply queue. A foreign
    # city the catalog does not list also reads `unknown` and slips through here — that is a
    # classifier-coverage gap (D-294 pattern), not a reason to demote every remote lead.
    #
    # The example is "Dublin" rather than a city that is merely missing, and that is the durable
    # choice: `location_data` excludes it ON PURPOSE, because Dublin OH is Cardinal Health's
    # headquarters and the gate must never silently delete a US role. So this case cannot be
    # closed by a later data edit the way "Kaunas Office" was — it stood here until the
    # 2026-08-30 audit added Kaunas to NON_US_CITIES and quietly broke this assertion.
    assert lane(verdict="uncertain", locations=["Remote"], title="Software Engineer") == ""
    assert (
        lane(
            verdict="uncertain",
            locations=["Dublin"],
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


def test_an_unevaluated_lead_is_held_for_review() -> None:
    """A3, and it REVERSES `test_unevaluated_none_verdict_is_treated_like_uncertain`.

    A `None` verdict used to be treated like `uncertain` — location and title decided, and a US
    software lead nothing had evaluated went into the blind-apply queue. That is the same
    clear-by-silence the zero-row gate below closes, one step earlier: with no evaluation there is
    no requirement row, so no rule cleared anything. 34 of the 646 apply-lane leads measured on
    2026-09-03 were in it for exactly that reason.

    The location and role gates still outrank it, because each of those is a DECIDED fact about
    the lead and "nothing has been evaluated" is the absence of one.
    """
    assert classify(verdict=None, locations=["Austin, TX"], title="Software Engineer") == (
        REVIEW_DIR,
        "unevaluated",
    )
    assert classify(
        verdict=None, locations=["Kaunas, Lithuania"], title="Software Engineer"
    ) == (REVIEW_DIR, "non_us_location")
    assert classify(verdict=None, locations=["Austin, TX"], title="Front Office Agent") == (
        REVIEW_DIR,
        "role_unconfirmed",
    )


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
    # Was `eligible` + Kaunas + Janitor, which R1 now holds for review. An eligible lead reaches
    # the apply lane only when it is also confirmed US and confirmed software.
    assert classify(
        verdict="eligible", locations=["Austin, TX"], title="Software Engineer"
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
        # The same lead with a dead requisition: the lane moves and the reason must NOT survive
        # into it. A closed posting held under a review reason would be a lane carrying a reason
        # drawn from a catalog that does not describe it.
        closed_decision = classify(
            verdict=verdict, locations=locations, title=title, posting_closed=True
        )
        assert closed_decision == LaneDecision(CLOSED_DIR, None), (verdict, locations, title)


def test_a_closed_posting_outranks_every_other_branch() -> None:
    """`posting_closed` is read FIRST, so no verdict, location or role below can override it.

    Asserted against the strongest competitor in each direction: an `eligible` US software lead
    (which short-circuits to the apply queue) and an `ineligible` one (which is the very first
    review branch). Both go to `_closed`, because neither answer is reachable any more.
    """
    for verdict in ("eligible", "ineligible", "uncertain", None):
        assert classify(
            verdict=verdict,
            locations=("Boston, MA",),
            title="Software Engineer",
            posting_closed=True,
        ) == LaneDecision(CLOSED_DIR, None), verdict


def test_the_closed_gate_is_inert_when_the_posting_is_open() -> None:
    """The default is False, so every pre-existing caller keeps its exact behaviour.

    This is the arm that fails if the branch is ever written as `if not posting_open:` — a lead
    whose openness nobody stated would then drain as dead.
    """
    for verdict in ("eligible", "ineligible", "uncertain", None):
        assert classify(
            verdict=verdict, locations=("Boston, MA",), title="Software Engineer"
        ) == classify(
            verdict=verdict,
            locations=("Boston, MA",),
            title="Software Engineer",
            posting_closed=False,
        )
        assert classify(
            verdict=verdict, locations=("Boston, MA",), title="Software Engineer"
        ).lane != CLOSED_DIR


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


# ------------------------------------------------------- the zero-row gate (A3) and its ranking


def test_a_zero_row_evaluation_is_held_for_review_not_blind_applied() -> None:
    """A3. US, software, `uncertain`, and neither older flag set — held because the eligibility
    catalog produced NO requirement row for this JD at all.

    Not a bug fix: it is what the apply lane MEANS. Such a lead reached the blind-apply queue
    because nothing was found in the body, never because a rule cleared anything — a clear by
    silence with an empty evidence chain, which is the one thing "No flags != cleared" forbids.
    MEASURED on the live store on 2026-09-03 through `delivered_unapplied` + `lane`, before and
    after on one snapshot: 521 of the 646 apply-lane leads (81%) were there for this reason and
    no other, and the apply lane went 646 -> 91.
    """
    assert classify(
        verdict="uncertain",
        locations=["San Jose, CA, United States"],
        title="Software Engineer",
        no_requirement_rows=True,
    ) == (REVIEW_DIR, "no_requirements_found")


def test_a_lead_carrying_at_least_one_requirement_row_still_reaches_apply() -> None:
    """The other side of the predicate, so it narrows rather than closes the lane.

    91 of the 646 measured apply-lane leads carry >=1 requirement row, and those are exactly the
    ones the change keeps: a row means the catalog read the JD and reached a disposition, which is
    the evidence the apply lane is supposed to rest on.
    """
    assert classify(
        verdict="uncertain",
        locations=["San Jose, CA, United States"],
        title="Software Engineer",
        no_requirement_rows=False,
    ) == ("", None)


def test_eligible_short_circuits_ABOVE_the_zero_row_gate_too() -> None:
    """The `eligible` short-circuit is not moved, and MEASUREMENT is why it costs nothing.

    Live store, 2026-09-03, through the production path: of the 646 apply-lane leads, 521 carry
    zero requirement rows and ALL 521 are `uncertain` — ZERO are `eligible`. Every one of the 55
    `eligible` apply-lane leads carries >=1 row. So the population this placement holds back is
    empty, measured.

    It is also empty by construction for a default policy: `engine.evaluate`'s zero-row branch
    already returns `uncertain` whenever no family — enabled or user-EXCLUDED — could have found a
    requirement (`_no_evaluable_requirement`), which is precisely the clear-by-silence A3 targets.
    `eligible` with zero rows is reachable only when an excluded family WOULD have detected one:
    the JD stated a requirement and the user's own policy opted out of it. That is a decision, not
    silence, and holding it here would re-open a settled question — the same reason the two older
    flags sit below the short-circuit (D-380).
    """
    assert classify(
        verdict="eligible",
        locations=["Austin, TX"],
        title="Software Engineer",
        no_requirement_rows=True,
    ) == ("", None)


def test_the_absence_holds_are_ranked_ABOVE_the_two_unconfirmed_row_flags() -> None:
    """Ordering, and it is observable. `unevaluated` > `no_requirements_found` > the two flags.

    Each earlier reason EXPLAINS the later ones' silence: with no evaluation there are no rows, and
    with no rows there is no unconfirmed row either. So reporting a row-derived reason for a lead
    that has no rows would name evidence that does not exist — the same error, in reverse, as
    reporting the experience bar when a hard-family rule abstained.

    Both combinations below are incoherent inputs (a zero-row evaluation cannot also carry an
    `unmet`/`unknown` row — `current_requirement_flags` derives all three from one query, and
    `test_the_zero_row_flag_excludes_the_two_unconfirmed_flags` pins that). They are asserted
    anyway: the ranking is the only thing that decides what a caller who passes both is told.
    """
    assert classify(
        verdict=None,
        locations=["San Jose, CA, United States"],
        title="Software Engineer",
        no_requirement_rows=True,
        experience_unconfirmed=True,
        eligibility_unconfirmed=True,
    ) == (REVIEW_DIR, "unevaluated")
    assert classify(
        verdict="uncertain",
        locations=["San Jose, CA, United States"],
        title="Software Engineer",
        no_requirement_rows=True,
        experience_unconfirmed=True,
        eligibility_unconfirmed=True,
    ) == (REVIEW_DIR, "no_requirements_found")
    # ...and the pre-existing ranking between the two flags is untouched.
    assert classify(
        verdict="uncertain",
        locations=["San Jose, CA, United States"],
        title="Software Engineer",
        experience_unconfirmed=True,
        eligibility_unconfirmed=True,
    ) == (REVIEW_DIR, "eligibility_unconfirmed")


def test_an_earlier_gate_still_wins_over_the_zero_row_gate() -> None:
    """A decided fact outranks an absence, exactly as it does for the two older flags.

    Without this the new branch could silently capture leads the location and role gates own, and
    the reader would lose the reason they act on.
    """
    assert classify(
        verdict="uncertain",
        locations=["Kaunas, Lithuania"],
        title="Software Engineer",
        no_requirement_rows=True,
    ) == (REVIEW_DIR, "non_us_location")
    assert classify(
        verdict="uncertain",
        locations=["Chicago, Illinois, United States"],
        title="Registered Nurse Practitioner",
        no_requirement_rows=True,
    ) == (REVIEW_DIR, "role_vetoed")
    assert classify(
        verdict="ineligible",
        locations=["Austin, TX"],
        title="Software Engineer",
        no_requirement_rows=True,
    ) == (REVIEW_DIR, "ineligible_verdict")
    # A dead requisition still outranks everything, and carries NO reason into `_closed`.
    assert classify(
        verdict="uncertain",
        locations=["Austin, TX"],
        title="Software Engineer",
        no_requirement_rows=True,
        posting_closed=True,
    ) == LaneDecision(CLOSED_DIR, None)


def test_the_zero_row_gate_is_inert_when_the_caller_states_rows_exist() -> None:
    """The default is False, so a caller that says nothing keeps its exact old behaviour.

    This is the arm that fails if the branch is ever written inverted (`if not no_requirement_rows`)
    — every lead in the queue would then be held for a reason that describes almost none of them.
    """
    for verdict, locations, title in _CASES:
        assert classify(verdict=verdict, locations=locations, title=title) == classify(
            verdict=verdict, locations=locations, title=title, no_requirement_rows=False
        )
    assert classify(
        verdict="uncertain", locations=["Austin, TX"], title="Software Engineer"
    ) == ("", None)


def test_lane_projects_the_zero_row_gate_too() -> None:
    """`lane` must not become a second opinion now that `classify` takes one more input (D-332)."""
    for verdict in ("uncertain", "eligible", None):
        for no_rows in (False, True):
            decision = classify(
                verdict=verdict,
                locations=["San Jose, CA, United States"],
                title="Software Engineer",
                no_requirement_rows=no_rows,
            )
            assert decision.lane == lane(
                verdict=verdict,
                locations=["San Jose, CA, United States"],
                title="Software Engineer",
                no_requirement_rows=no_rows,
            )
            assert (decision.reason is not None) == (decision.lane == REVIEW_DIR)
