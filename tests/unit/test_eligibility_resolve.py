"""Claim-typed resolution (D-P2-11). A wrong `met` tells a job seeker they qualify when
they do not, which is the worst failure this design can produce, so every ambiguity
resolves to `unknown`."""

from pathlib import Path

import pytest

from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.detect import detect
from boardwatch.eligibility.facts import ClearanceFact, Facts, WorkAuthFact
from boardwatch.eligibility.resolve import (
    RegistryError,
    ResolverEntry,
    declared_fields,
    registry,
    resolve,
    verify_registry,
)

ALL = frozenset({"work_auth", "experience_years", "clearance", "degree"})


@pytest.fixture()
def catalog(tmp_path: Path):
    return load_rules(tmp_path / "no-override")


def _one(catalog, body: str, facts: Facts, pattern_id: str) -> str:
    dets = [d for d in detect(body, catalog, enabled_families=ALL) if d.pattern.id == pattern_id]
    assert len(dets) == 1, f"expected exactly one {pattern_id}, got {len(dets)}"
    return resolve(dets[0], facts, catalog.family(dets[0].family)).disposition


# ---- registry, both directions (a one-directional check is how P0-4 nearly shipped a
# ---- gate with an unregistered rule and passing unit tests)

def test_verify_registry_accepts_the_real_pair(catalog) -> None:
    verify_registry(catalog, registry(), Facts)


def test_a_catalog_family_with_no_resolver_is_rejected(catalog) -> None:
    trimmed = {k: v for k, v in registry().items() if k != "degree"}
    with pytest.raises(RegistryError, match="degree"):
        verify_registry(catalog, trimmed, Facts)


def test_a_resolver_naming_an_absent_family_is_rejected(catalog) -> None:
    extra = dict(registry())
    extra["salary"] = extra["degree"]
    with pytest.raises(RegistryError, match="salary"):
        verify_registry(catalog, extra, Facts)


def test_every_catalog_fact_must_be_a_field_on_the_facts_model(catalog) -> None:
    """Closes the third side of the loop: the catalog declares `fact` per family and the
    models declare TYPES, so a family whose fact has no field would abstain forever with
    no error anywhere."""
    for family in catalog.families:
        assert family.fact in Facts.model_fields


def test_a_catalog_fact_with_no_field_on_the_model_is_rejected(catalog) -> None:
    """The same third side of the loop, at the RAISE rather than as a property assertion.
    The test above asserts the property of the REAL pair, so it can never reach
    verify_registry's `family.fact not in model_fields` branch and that branch shipped
    unexecuted; an override adding a family with a typo'd `fact` would then abstain forever
    with no error anywhere. The model is derived from the real one minus exactly that field,
    so the test does not hard-code a fact name."""
    from typing import Any

    from pydantic import create_model

    degree = catalog.family("degree")
    narrowed = create_model(
        "FactsWithoutTheDegreeFact",
        **{
            name: (Any, None)
            for name in Facts.model_fields
            if name != degree.fact
        },
    )
    with pytest.raises(RegistryError, match=degree.fact):
        verify_registry(catalog, registry(), narrowed)  # type: ignore[arg-type]


def test_a_resolver_input_with_no_field_on_the_model_is_rejected(catalog) -> None:
    """The fourth side, and the one with teeth: `declared_fields` feeds build_identity's
    profile hash, so a misspelled input silently drops a field out of the fingerprint and a
    user who later edits that field never triggers the re-evaluation that would have read
    it. Also unexecuted until now."""
    entries = dict(registry())
    entries["degree"] = ResolverEntry(
        function=entries["degree"].function,
        inputs=(*entries["degree"].inputs, "no_such_fact"),
    )
    with pytest.raises(RegistryError, match="no_such_fact"):
        verify_registry(catalog, entries, Facts)


def test_declared_fields_covers_every_family(catalog) -> None:
    fields = declared_fields()
    assert set(fields) == {f.id for f in catalog.families}
    # the degree resolver reads the years fact for a measurable OR-alternative (D-P2-23)
    assert "total_years_experience" in fields["degree"]
    for names in fields.values():
        for name in names:
            assert name in Facts.model_fields


# ---- work_auth: jurisdiction equality is required for `met` (D-P2-19)

@pytest.mark.parametrize(
    ("status", "expected"),
    [("citizen", "met"), ("permanent_resident", "met"), ("ead_or_similar", "met"),
     ("needs_sponsorship", "unmet"), ("prefer_not_to_say", "unknown")],
)
def test_us_authorization_against_every_status(catalog, status: str, expected: str) -> None:
    facts = Facts(work_authorization=WorkAuthFact(status=status, jurisdiction="us"))
    body = "Must be authorized to work in the United States."
    assert _one(catalog, body, facts, "us_authorization_required") == expected


@pytest.mark.parametrize(
    ("status", "expected"),
    [("citizen", "met"), ("permanent_resident", "met"),
     # THE backwards-met case: an EAD holder needs no sponsorship yet is neither a citizen
     # nor an LPR, so a boolean needs_sponsorship=False wrongly satisfied this. Removing
     # that `met` first parked this at `unknown`, which UNDERSHOT: the catalog's status
     # choices are mutually exclusive, so `ead_or_similar` states the applicant is neither
     # a citizen nor an LPR. That is UNMET -- decisively -- exactly as `permanent_resident`
     # is decisively not a citizen against `us_citizen_required` (D-322).
     ("ead_or_similar", "unmet"),
     ("needs_sponsorship", "unmet"), ("prefer_not_to_say", "unknown")],
)
def test_citizen_or_lpr_against_every_status(catalog, status: str, expected: str) -> None:
    facts = Facts(work_authorization=WorkAuthFact(status=status, jurisdiction="us"))
    body = "This role is open to US citizens or green card holders only."
    assert _one(catalog, body, facts, "us_citizen_or_lpr_required") == expected


@pytest.mark.parametrize("jurisdiction", ["ca", "uk", "eu", "unspecified", "other", None])
def test_a_non_matching_jurisdiction_always_abstains(catalog, jurisdiction) -> None:
    """A Canadian citizen storing `citizen` satisfied "must be a US citizen" while §4.1
    declared a scalar choice. `other` is a catch-all, not an identity, so other == other
    must NOT count as equality either."""
    facts = Facts(work_authorization=WorkAuthFact(status="citizen", jurisdiction=jurisdiction))
    assert _one(catalog, "Applicants must be US citizens.", facts,
                "us_citizen_required") == "unknown"


def test_a_matching_jurisdiction_resolves(catalog) -> None:
    facts = Facts(work_authorization=WorkAuthFact(status="citizen", jurisdiction="us"))
    assert _one(catalog, "Applicants must be US citizens.", facts,
                "us_citizen_required") == "met"


@pytest.mark.parametrize(
    ("status", "expected"),
    [("citizen", "met"), ("permanent_resident", "unmet"), ("ead_or_similar", "unmet"),
     ("needs_sponsorship", "unmet"), ("prefer_not_to_say", "unknown")],
)
def test_us_citizenship_against_every_status(catalog, status: str, expected: str) -> None:
    """The symmetric twin of the citizen-or-LPR table, which did not exist while
    `ead_or_similar` was the only status this rule could not decide. The catalog's five
    choices are MUTUALLY EXCLUSIVE (rules.yaml:86), so each of the three declared non-citizen
    statuses states a fact incompatible with a citizenship requirement and each is `unmet`.
    `prefer_not_to_say` is the single abstain, and it is the keystone invariant working:
    undeclared is never decided (D-322)."""
    facts = Facts(work_authorization=WorkAuthFact(status=status, jurisdiction="us"))
    assert _one(catalog, "Applicants must be US citizens.", facts,
                "us_citizen_required") == expected


def test_the_citizenship_inference_does_not_reach_the_sponsorship_branch(catalog) -> None:
    """The asymmetry is load-bearing and easy to over-apply. `ead_or_similar` DECIDES a
    citizenship requirement, because the catalog's statuses are mutually exclusive. It must
    still ABSTAIN against a sponsorship restriction when the bit is unset, because an EAD
    covers both an F-1 OPT holder whose runway that clause ends and an asylee who needs
    nothing -- status alone genuinely cannot tell them apart. D-322 narrows citizenship
    only; widening it to sponsorship would resurrect the guess D-P2-11 removed."""
    facts = Facts(work_authorization=WorkAuthFact(status="ead_or_similar", jurisdiction="us"))
    assert _one(catalog, "Applicants must be US citizens.", facts,
                "us_citizen_required") == "unmet"
    assert _one(catalog, "We do not offer visa sponsorship.", facts,
                "no_sponsorship_offered") == "unknown"


def test_an_unset_work_auth_fact_abstains(catalog) -> None:
    assert _one(catalog, "Applicants must be US citizens.", Facts(),
                "us_citizen_required") == "unknown"


def test_unavailable_sponsorship_is_unmet_only_for_a_sponsorship_need(catalog) -> None:
    body = "We do not offer visa sponsorship."
    needs = Facts(work_authorization=WorkAuthFact(status="needs_sponsorship", jurisdiction="us"))
    citizen = Facts(work_authorization=WorkAuthFact(status="citizen", jurisdiction="us"))
    assert _one(catalog, body, needs, "no_sponsorship_offered") == "unmet"
    # A jurisdiction-free "no sponsorship" clause that decides UNMET against a needs-
    # sponsorship applicant clears a citizen who needs none: a presumption strong enough to
    # declare someone BLOCKED is exactly strong enough to declare them UNBLOCKED (the
    # prototype's finding 50, which removed the old `no jurisdiction -> unknown` bias). Left
    # unknown, this rendered `uncertain` for a citizen the clause cannot possibly block.
    assert _one(catalog, body, citizen, "no_sponsorship_offered") == "met"


# ---- needs_sponsorship bit (P2a): disentangles sponsorship need from work-auth status so
# ---- an ead_or_similar holder can be DECIDED instead of forced to abstain (D-P2-11).

def test_needs_sponsorship_false_disentangles_an_ead_holder_from_unknown(catalog) -> None:
    """The bit's whole purpose: status alone cannot say whether an ead_or_similar holder
    needs sponsorship, so this used to be forced to `unknown`. The explicit bit answers it."""
    body = "We do not offer visa sponsorship."
    facts = Facts(work_authorization=WorkAuthFact(
        status="ead_or_similar", jurisdiction="us", needs_sponsorship=False
    ))
    assert _one(catalog, body, facts, "no_sponsorship_offered") == "met"


def test_needs_sponsorship_true_is_unmet_even_for_an_ead_holder(catalog) -> None:
    body = "We do not offer visa sponsorship."
    facts = Facts(work_authorization=WorkAuthFact(
        status="ead_or_similar", jurisdiction="us", needs_sponsorship=True
    ))
    assert _one(catalog, body, facts, "no_sponsorship_offered") == "unmet"


@pytest.mark.parametrize(
    ("status", "expected"),
    [("citizen", "met"), ("permanent_resident", "met"), ("ead_or_similar", "unknown"),
     ("needs_sponsorship", "unmet"), ("prefer_not_to_say", "unknown")],
)
def test_needs_sponsorship_unset_falls_back_to_todays_status_inference(
    catalog, status: str, expected: str
) -> None:
    """The bit absent (None) must be byte-identical to behaviour before it existed."""
    body = "We do not offer visa sponsorship."
    facts = Facts(work_authorization=WorkAuthFact(status=status, jurisdiction="us"))
    assert _one(catalog, body, facts, "no_sponsorship_offered") == expected


# ---- needs_sponsorship bit on the sponsorship-OFFERED branch: it must read the bit the
# ---- same way its unavailable twin does, or the one rule that exists to CLEAR a
# ---- sponsorship-needing candidate on a sponsoring posting can never fire.

def test_sponsorship_offer_clears_an_ead_holder_who_declares_a_need(catalog) -> None:
    """An ead_or_similar holder who declares a sponsorship need is CLEARED by a posting that
    offers sponsorship -- previously forced to `unknown` because the branch read only status."""
    body = "Visa sponsorship is available."
    facts = Facts(work_authorization=WorkAuthFact(
        status="ead_or_similar", jurisdiction="us", needs_sponsorship=True
    ))
    assert _one(catalog, body, facts, "sponsorship_available") == "met"


def test_sponsorship_offer_is_nothing_to_decide_for_someone_who_needs_none(catalog) -> None:
    body = "Visa sponsorship is available."
    facts = Facts(work_authorization=WorkAuthFact(
        status="ead_or_similar", jurisdiction="us", needs_sponsorship=False
    ))
    assert _one(catalog, body, facts, "sponsorship_available") == "unknown"


@pytest.mark.parametrize(
    ("status", "expected"),
    [("citizen", "unknown"), ("permanent_resident", "unknown"),
     ("ead_or_similar", "unknown"), ("needs_sponsorship", "met"),
     ("prefer_not_to_say", "unknown")],
)
def test_sponsorship_offer_bit_unset_falls_back_to_status_inference(
    catalog, status: str, expected: str
) -> None:
    """Bit absent (None) must be byte-identical to the status-only behaviour before the bit
    was read on this branch."""
    body = "Visa sponsorship is available."
    facts = Facts(work_authorization=WorkAuthFact(status=status, jurisdiction="us"))
    assert _one(catalog, body, facts, "sponsorship_available") == expected


def test_needs_sponsorship_false_does_not_satisfy_a_citizenship_only_restriction(catalog) -> None:
    """CRITICAL SAFETY (facts.py:3-6): an EAD holder who needs no sponsorship is still not a
    citizen. The bit must only ever influence the sponsorship branch, never citizenship.
    `unmet`, not `unknown`: the bit is absent from this branch either way, and the status
    alone decides it (D-322). Asserting the exact value is what keeps `met` unreachable."""
    facts = Facts(work_authorization=WorkAuthFact(
        status="ead_or_similar", jurisdiction="us", needs_sponsorship=False
    ))
    assert _one(catalog, "Applicants must be US citizens.", facts,
                "us_citizen_required") == "unmet"


def test_needs_sponsorship_bit_does_not_leak_into_citizen_or_lpr_branch(catalog) -> None:
    """Same safety property against the other citizenship-adjacent branch: a citizen who
    (nonsensically) set needs_sponsorship=True still resolves on citizenship, not the bit."""
    facts = Facts(work_authorization=WorkAuthFact(
        status="citizen", jurisdiction="us", needs_sponsorship=True
    ))
    assert _one(catalog, "This role is open to US citizens or green card holders only.", facts,
                "us_citizen_or_lpr_required") == "met"


# ---- experience_years

@pytest.mark.parametrize(("total", "expected"), [(8, "met"), (5, "met"), (4, "unmet")])
def test_total_years_comparison_is_inclusive(catalog, total: int, expected: str) -> None:
    facts = Facts(total_years_experience=total)
    assert _one(catalog, "5+ years of experience required.", facts,
                "total_years_minimum") == expected


def test_a_range_resolves_on_its_lower_bound(catalog) -> None:
    assert _one(catalog, "3-5 years of experience.", Facts(total_years_experience=4),
                "range_years_minimum") == "met"


@pytest.mark.parametrize("total", [0, 1, 4])
def test_a_scoped_requirement_is_unmet_when_it_exceeds_total_experience(
    catalog, total: int
) -> None:
    """A duration scoped to one skill cannot exceed the whole career it sits inside, so
    `total < need` FORCES unmet with no per-skill data. Abstaining here is what let a
    1-year profile read `eligible` against "12 years of experience in software
    development": this pattern is 342 of the 441 experience rows in a measured delivered
    set, and every one of them abstained."""
    assert _one(catalog, "5+ years of experience with Kubernetes.",
                Facts(total_years_experience=total), "scoped_years_minimum") == "unmet"


@pytest.mark.parametrize("total", [5, 40])
def test_a_scoped_requirement_still_abstains_when_the_total_allows_it(
    catalog, total: int
) -> None:
    """Only the unmet direction is forced. `total >= need` says nothing about the
    candidate's duration in THAT skill, so a `met` here would be a wrong clear -- the
    worst failure this design can produce. The profile holds a skill SET, no durations."""
    assert _one(catalog, "5+ years of experience with Kubernetes.",
                Facts(total_years_experience=total), "scoped_years_minimum") == "unknown"


@pytest.mark.parametrize("body", [
    "5+ years building and deploying web applications.",
    "7+ years of architecting cloud platforms.",
])
def test_an_activity_gerund_states_a_floor_with_no_experience_noun(catalog, body: str) -> None:
    """No "experience" noun anywhere, so neither total nor scoped could see it.

    Measured against job-apps' labelled corpus, which carries this form as its own pattern and
    names the source: aggregator summaries phrase a floor this way. hiring.cafe is one of
    boardwatch's own lanes, so the miss lands on a population it actively ingests. Scoped, not
    total: the duration is scoped to an ACTIVITY, so it decides only in the forced direction.
    """
    assert _one(catalog, body, Facts(total_years_experience=1),
                "scoped_years_activity") == "unmet"


# ---- the NEAR-MISS band: a low bar abstains instead of rejecting (D-333)

@pytest.mark.parametrize(("body", "pattern_id"), [
    ("2+ years of experience required.", "total_years_minimum"),
    ("3+ years of experience required.", "total_years_minimum"),
    ("2-4 years of experience.", "range_years_minimum"),
    ("3+ years of experience with Kubernetes.", "scoped_years_minimum"),
    ("3 years developing distributed systems.", "scoped_years_activity"),
])
def test_a_bar_at_or_under_the_near_miss_ceiling_abstains(catalog, body, pattern_id) -> None:
    """A 1-year profile against a 2-3 year bar is a NEAR MISS, not a rejection.

    Internships, co-ops and project work routinely clear an early-career bar that a single
    declared `total_years_experience` integer cannot represent, and the reject pile is never
    inspected -- so a wrong `unmet` here is invisible by construction. Abstaining keeps the
    row VISIBLE and undecidable for the two-stage gate, which is the same choice
    `degree_alternative_to_years` already makes.

    `unknown`, deliberately, NOT a severity flip to `preference`: a preference row leaves
    `blocking()` entirely and the verdict falls through to `eligible`, asserting the
    candidate qualifies. `unknown` is caught by `blocking(UNKNOWN)` first and yields
    `uncertain`. The band can therefore never manufacture an `eligible`.
    """
    assert _one(catalog, body, Facts(total_years_experience=1), pattern_id) == "unknown"


@pytest.mark.parametrize(("body", "pattern_id"), [
    ("4+ years of experience required.", "total_years_minimum"),
    ("4-6 years of experience.", "range_years_minimum"),
    ("4+ years of experience with Kubernetes.", "scoped_years_minimum"),
    ("4 years developing distributed systems.", "scoped_years_activity"),
])
def test_the_first_bar_above_the_ceiling_still_rejects(catalog, body, pattern_id) -> None:
    """The boundary is CLOSED at the ceiling and the very next year still rejects.

    Pinned one year either side because an off-by-one here is silent: it would widen the
    band to 4 years and neither the verdict counts nor the gate would name the cause.
    """
    assert _one(catalog, body, Facts(total_years_experience=1), pattern_id) == "unmet"


def test_the_near_miss_band_does_not_fire_when_the_total_already_clears(catalog) -> None:
    """A bar inside the band that the profile MEETS still resolves `met`, not `unknown`.

    The band only ever replaces an `unmet`; it must not swallow a genuine clear, which would
    turn a qualifying lead into an abstention and cost recall in the opposite direction.
    """
    assert _one(catalog, "3+ years of experience required.",
                Facts(total_years_experience=5), "total_years_minimum") == "met"


def test_a_family_declaring_no_ceiling_is_unchanged(catalog) -> None:
    """The ceiling is opt-in per family. Every other family parses without it and keeps a
    zero ceiling, so no family that never declared one can start abstaining."""
    assert catalog.family("experience_years").near_miss_years_ceiling == 3
    for family in catalog.families:
        if family.id != "experience_years":
            assert family.near_miss_years_ceiling == 0, family.id


def test_an_activity_gerund_on_the_company_side_is_suppressed(catalog) -> None:
    """The subject suppressor has to reach the new pattern too. Without it the company's own
    tenure becomes the candidate's bar."""
    dets = [d for d in detect("Our engineers have 30 years working with distributed systems.",
                              catalog, enabled_families=ALL)
            if d.pattern.id == "scoped_years_activity"]
    assert dets == []


def test_up_to_n_years_is_a_cap_not_a_floor_for_the_gerund_form(catalog) -> None:
    """"Up to 3 years" bounds the candidate from ABOVE. Read as a floor it rejects exactly the
    new-grad postings this tool exists to find."""
    dets = [d for d in detect("Up to 3 years building web applications.", catalog,
                              enabled_families=ALL)
            if d.pattern.id == "scoped_years_activity"]
    assert dets == []


def test_a_company_side_we_bring_subject_is_suppressed(catalog) -> None:
    """"We bring 30 years of experience" is the company's tenure, not a requirement. The
    subject suppressor keyed on "our <noun> has", so a bare "we" subject fell through and
    resolved `unmet` against a one-year profile."""
    dets = [d for d in detect("We bring 30 years of experience to every engagement.", catalog,
                              enabled_families=ALL)
            if d.family == "experience_years"]
    assert dets == []


def test_coursework_prose_elsewhere_does_not_waive_a_genuine_years_floor(catalog) -> None:
    """A REJECTED transfer, pinned so it is not re-attempted.

    job-apps waives a years floor when the posting says prior non-professional experience
    counts, and it works there because its exceptions are evaluated LINE by line against the
    line carrying the years. boardwatch's nearest mechanism, `abstain_by`, is DOCUMENT-scoped.
    Dropped in as one, the same regex waived Anthropic's genuine "5+ years of experience as a
    software engineer" because a different sentence read "A field relevant to the role as
    demonstrated through coursework, training, or professional experience" -- prose about the
    FIELD OF STUDY, not about the floor. Measured: it spared 9 of 286 blocked leads, two of
    them Anthropic SWE roles whose 5- and 6-year floors are real.

    The pattern transfers; the enclosing scope does not. Re-attempting this needs a
    clause-scoped abstain that does not exist yet, not a wider regex.
    """
    body = ("Have 5+ years of experience as a software engineer.\n"
            "Required field of study: a field relevant to the role as demonstrated through "
            "coursework, training, or professional experience.\n")
    dets = [d for d in detect(body, catalog, enabled_families=ALL)
            if d.family == "experience_years"]
    assert dets, "the floor must still be detected"
    assert all(d.abstained is None for d in dets), (
        "document-scoped coursework prose must not waive a floor stated in another sentence"
    )


def test_an_unset_years_fact_abstains(catalog) -> None:
    assert _one(catalog, "5+ years of experience required.", Facts(),
                "total_years_minimum") == "unknown"


# ---- clearance: NO total order (D-P2-20)

def _clearance(**kwargs) -> Facts:
    return Facts(security_clearance=ClearanceFact(**kwargs))


def test_an_exact_match_is_met(catalog) -> None:
    facts = _clearance(scheme="us_dod", level="secret", state="active")
    assert _one(catalog, "Active Secret clearance required.", facts,
                "active_secret_required") == "met"


def test_a_ts_without_sci_never_satisfies_a_ts_sci_requirement(catalog) -> None:
    """Rev 2's ranked scale let an active TS outrank a TS/SCI requirement. TS does not
    imply SCI."""
    facts = _clearance(scheme="us_dod", level="top_secret", state="active", accesses=())
    assert _one(catalog, "An active TS/SCI clearance is required.", facts,
                "active_ts_sci_required") == "unknown"


def test_a_ts_sci_holder_satisfies_a_ts_sci_requirement(catalog) -> None:
    facts = _clearance(scheme="us_dod", level="top_secret", state="active", accesses=("sci",))
    assert _one(catalog, "An active TS/SCI clearance is required.", facts,
                "active_ts_sci_required") == "met"


def test_holding_nothing_is_decidably_unmet(catalog) -> None:
    """The decidable case carrying most of the real yield."""
    facts = _clearance(scheme="unspecified", level="none", state="none")
    assert _one(catalog, "An active TS/SCI clearance is required.", facts,
                "active_ts_sci_required") == "unmet"


def test_a_reviewed_superset_relation_resolves_met(catalog) -> None:
    facts = _clearance(scheme="us_dod", level="top_secret", state="active")
    assert _one(catalog, "Active Secret clearance required.", facts,
                "active_secret_required") == "met"


def test_a_different_scheme_abstains_in_both_directions(catalog) -> None:
    doe = _clearance(scheme="us_doe", level="q", state="active")
    assert _one(catalog, "Active Secret clearance required.", doe,
                "active_secret_required") == "unknown"
    dod = _clearance(scheme="us_dod", level="top_secret", state="active")
    assert _one(catalog, "An active Q clearance is required.", dod, "doe_q_required") == "unknown"


@pytest.mark.parametrize(("state", "level", "expected"),
                         [("active", "secret", "met"), ("current", "secret", "met"),
                          ("expired", "secret", "unknown"), ("interim", "secret", "unknown"),
                          ("unspecified", "secret", "unknown"),
                          # Holds-nothing is state none AND level none. Pairing state none with
                          # a named level is a half-filled form the incoherence guard abstains
                          # on (covered below); this row keeps the decidable-unmet yield.
                          ("none", "none", "unmet")])
def test_every_clearance_state(catalog, state: str, level: str, expected: str) -> None:
    facts = _clearance(scheme="us_dod", level=level, state=state)
    assert _one(catalog, "Active Secret clearance required.", facts,
                "active_secret_required") == expected


@pytest.mark.parametrize(("level", "state"), [("secret", "none"), ("none", "active")])
def test_an_incoherent_clearance_fact_abstains(catalog, level: str, state: str) -> None:
    """Cross-field coherence, checked BEFORE any comparison. A named level with state `none`
    is a half-filled form, and an `active` clearance at level `none` is not a clearance;
    comparing either produced a wrong `met` on a real gate, so a malformed fact abstains."""
    facts = _clearance(scheme="us_dod", level=level, state=state)
    assert _one(catalog, "Active Secret clearance required.", facts,
                "active_secret_required") == "unknown"


def test_an_unnamed_level_is_satisfied_by_any_active_clearance(catalog) -> None:
    """Requiring an exact level here would abstain on a decidable case; defaulting the
    level would fabricate a requirement."""
    facts = _clearance(scheme="us_dod", level="secret", state="active")
    assert _one(catalog, "A security clearance is required.", facts,
                "generic_clearance_required") == "met"


def test_an_access_only_requirement_is_decidable(catalog) -> None:
    body = "A current polygraph is required for this role."
    with_poly = _clearance(scheme="us_dod", level="top_secret", state="active",
                           accesses=("sci", "poly"))
    without = _clearance(scheme="us_dod", level="top_secret", state="active", accesses=("sci",))
    assert _one(catalog, body, with_poly, "polygraph_required") == "met"
    assert _one(catalog, body, without, "polygraph_required") == "unknown"


_OBTAIN = "Must be able to obtain a security clearance."


def test_obtain_after_hire_abstains_while_obtainability_is_undeclared(catalog) -> None:
    """The keystone: obtainability is its OWN declared field, so an absent value can only
    abstain. Neither holding nothing nor holding an active clearance answers it."""
    for facts in (_clearance(scheme="unspecified", level="none", state="none"),
                  _clearance(scheme="us_dod", level="secret", state="active"),
                  Facts()):
        assert _one(catalog, _OBTAIN, facts, "clearable_required") == "unknown"


@pytest.mark.parametrize(("obtainable", "expected"), [(True, "met"), (False, "unmet")])
def test_obtain_after_hire_resolves_on_the_declared_obtainability(
    catalog, obtainable: bool, expected: str
) -> None:
    facts = _clearance(scheme="unspecified", level="none", state="none",
                       obtainable=obtainable)
    assert _one(catalog, _OBTAIN, facts, "clearable_required") == expected


def test_obtainability_is_orthogonal_to_the_clearance_held(catalog) -> None:
    """An F-1 OPT holder can hold nothing and never become clearable; a Secret holder who
    declares themselves unclearable is still unmet. Reading the HELD level here would invert
    both, which is the claim-typed hazard ClearanceFact exists to prevent."""
    holds_secret = _clearance(scheme="us_dod", level="secret", state="active",
                              obtainable=False)
    assert _one(catalog, _OBTAIN, holds_secret, "clearable_required") == "unmet"


def test_an_incoherent_clearance_fact_abstains_on_obtainability_too(catalog) -> None:
    """A half-filled form is not trusted for the obtainability bit either: `met` there is a
    wrong clear, the worst failure this design can produce."""
    facts = _clearance(scheme="us_dod", level="secret", state="none", obtainable=True)
    assert _one(catalog, _OBTAIN, facts, "clearable_required") == "unknown"


def test_the_obtainability_resolution_cites_the_field_it_read(catalog) -> None:
    facts = _clearance(scheme="unspecified", level="none", state="none", obtainable=False)
    dets = [d for d in detect(_OBTAIN, catalog, enabled_families=ALL)
            if d.pattern.id == "clearable_required"]
    support = resolve(dets[0], facts, catalog.family("clearance")).support
    assert [s.profile_locator["field"] for s in support] == [
        "facts.security_clearance.obtainable"
    ]


# ---- degree

@pytest.mark.parametrize(("attained", "expected"),
                         [("doctorate", "met"), ("master", "met"), ("bachelor", "met"),
                          ("associate", "unmet"), ("none", "unmet"),
                          ("prefer_not_to_say", "unknown")])
def test_degree_rank_comparison(catalog, attained: str, expected: str) -> None:
    assert _one(catalog, "Bachelor's degree required.", Facts(highest_degree=attained),
                "bachelor_required") == expected


def test_an_unmeasurable_or_escape_abstains_and_stays_required(catalog) -> None:
    """Rev 1 downgraded this to `preferred`, which made a real requirement a silent pass:
    a blocker-policy user with neither degree nor measurable equivalent got `eligible`."""
    dets = [d for d in detect("Bachelor's degree or equivalent experience required.",
                              catalog, enabled_families=ALL)
            if d.pattern.id == "bachelor_or_equivalent_required"]
    assert len(dets) == 1
    assert dets[0].pattern.requiredness == "required"
    assert resolve(dets[0], Facts(highest_degree="none"),
                   catalog.family("degree")).disposition == "unknown"


def test_a_measurable_or_escape_resolves(catalog) -> None:
    body = "Bachelor's degree or 4 years of equivalent experience."
    enough = Facts(highest_degree="none", total_years_experience=8)
    short = Facts(highest_degree="none", total_years_experience=2)
    assert _one(catalog, body, enough, "bachelor_or_equivalent_required") == "met"
    assert _one(catalog, body, short, "bachelor_or_equivalent_required") == "unmet"


def test_the_degree_itself_satisfies_an_or_escape(catalog) -> None:
    assert _one(catalog, "Bachelor's degree or equivalent experience required.",
                Facts(highest_degree="master"), "bachelor_or_equivalent_required") == "met"


def test_a_field_of_study_constraint_blocks_met_but_keeps_unmet(catalog) -> None:
    """A rank-only comparison returns `met` for any bachelor's holder including one with
    an unrelated degree. The field is unmeasurable, so a satisfied rank abstains, while a
    rank below the bar stays decidable: no field can rescue a missing degree."""
    body = "Bachelor's degree in Computer Science or a related field is required."
    assert _one(catalog, body, Facts(highest_degree="bachelor"),
                "bachelor_in_field_required") == "unknown"
    assert _one(catalog, body, Facts(highest_degree="none"),
                "bachelor_in_field_required") == "unmet"


def test_an_unleveled_requirement_is_unmet_only_with_no_degree(catalog) -> None:
    assert _one(catalog, "A degree is required.", Facts(highest_degree="none"),
                "any_degree_required") == "unmet"
    # A degree is REQUIRED with no level named: any completed degree satisfies it. This must
    # be `met`, not `unknown` -- the unleveled bar previously had no MET path at all.
    assert _one(catalog, "A degree is required.", Facts(highest_degree="bachelor"),
                "any_degree_required") == "met"


# ---- degree: field of study

_CS_OR_RELATED = "Bachelor's degree in Computer Science or a related field is required."
_CS_ONLY = "Bachelor's degree in Computer Science is required."


def _degree(**kwargs) -> Facts:
    return Facts(highest_degree="bachelor", **kwargs)


def test_the_field_the_posting_names_resolves_met(catalog) -> None:
    assert _one(catalog, _CS_ONLY, _degree(field_of_study="computer_science"),
                "bachelor_in_field_required") == "met"


def test_a_reviewed_related_field_is_met_only_when_the_posting_offers_the_escape(
    catalog,
) -> None:
    """The catalog's relatedness partition says two fields are interchangeable; the POSTING
    says whether it will accept an interchangeable one. Both are required for `met`, because
    "must have a CS degree" means CS, and answering `met` to it with a neighbouring degree is
    the wrong clear this family exists to avoid."""
    related = _degree(field_of_study="software_engineering")
    assert _one(catalog, _CS_OR_RELATED, related, "bachelor_in_field_required") == "met"
    assert _one(catalog, _CS_ONLY, related, "bachelor_in_field_required") == "unknown"


def test_an_unrelated_named_field_is_decidably_unmet(catalog) -> None:
    """The one direction this fact makes decidable: the posting names a closed set of
    catalogued fields, none of which the profile holds or is reviewed-related to."""
    assert _one(catalog, "Bachelor's degree in Nursing is required.",
                _degree(field_of_study="computer_science"),
                "bachelor_in_field_required") == "unmet"


def test_an_unrelated_named_field_with_an_escape_abstains(catalog) -> None:
    """A posting that says it accepts related fields has stated that relatedness it did not
    enumerate may qualify. The catalog cannot refute that, so `unmet` would be a guess."""
    assert _one(catalog, "Bachelor's degree in Nursing or a related field is required.",
                _degree(field_of_study="computer_science"),
                "bachelor_in_field_required") == "unknown"


@pytest.mark.parametrize("article", ["another", "other"])
def test_the_relatedness_escape_reads_other_and_another(catalog, article) -> None:
    """`or another related field` is the same escape as `or a related field`, and an article
    slot that only held `a`/`an` could not consume either word -- so the posting had opened
    the requirement and the row decided `unmet` anyway."""
    body = f"Bachelor's degree in Nursing or {article} related field is required."
    assert _one(catalog, body, _degree(field_of_study="computer_science"),
                "bachelor_in_field_required") == "unknown"


#: What precedes `education` when it is the equivalence/accreditation MASS NOUN rather than
#: the named field. Measured over the open postings: `equivalent combination of` is the bulk
#: of it, the accreditation bodies and the military/lieu-of frames the rest.
_EDUCATION_BOILERPLATE = [
    "Engineering or educational equivalent is ",
    "Biology or an equivalent combination of education ",
    "Computer Science or foreign education equivalent",
    "Nursing from a program accredited by the Commission on Collegiate Nursing Education",
    "Nursing accredited by the Accreditation Commission for Education in Nursing",
    "Business or combination of formal education ",
    "Engineering or equivalent military education ",
    "Engineering, experience in lieu of education ",
    "Engineering or the equivalent in education",
    "Business or combination of education ",
]

#: The field sense, which heads its own noun phrase. These must keep matching.
_EDUCATION_FIELD = [
    "Education",
    "Higher Education",
    "Early Childhood Education",
    "Instructional Design, Education",
    "Social Work, Education",
    "Special Education",
]


def _education_surfaces(catalog):
    spec = next(s for s in catalog.family("degree").fields_of_study if s.id == "education")
    return spec.surfaces


@pytest.mark.parametrize("phrase", _EDUCATION_BOILERPLATE)
def test_the_education_surface_rejects_equivalence_boilerplate(catalog, phrase) -> None:
    """Reading the mass noun as the named field decided `ineligible` against postings that
    named no field at all -- "or educational equivalent" is not a degree in education."""
    assert not any(rx.search(phrase) for rx in _education_surfaces(catalog))


@pytest.mark.parametrize("phrase", _EDUCATION_FIELD)
def test_the_education_surface_still_reads_the_field_sense(catalog, phrase) -> None:
    """The other half of the same regex: narrowing it must not delete the field itself."""
    assert any(rx.search(phrase) for rx in _education_surfaces(catalog))


def test_equivalence_boilerplate_names_no_field_of_study(catalog) -> None:
    """End to end, on the live sentence that produced the wrong `unmet`: the only catalogued
    field the phrase appeared to name was the boilerplate `education`, so removing it leaves
    the posting naming nothing and the row abstains instead of blocking."""
    body = "Bachelor of Science Degree in Engineering or educational equivalent is required."
    assert _one(catalog, body, _degree(field_of_study="computer_science"),
                "bachelor_in_field_required") == "unknown"


def test_a_field_the_catalog_does_not_know_abstains(catalog) -> None:
    """Out of catalog is a FAILURE, never a new bucket: an unrecognised phrase cannot be
    compared, so it can neither clear nor block."""
    assert _one(catalog, "Bachelor's degree in Basket Weaving is required.",
                _degree(field_of_study="computer_science"),
                "bachelor_in_field_required") == "unknown"


@pytest.mark.parametrize("declared", [None, "underwater_basket_weaving"])
def test_an_absent_or_uncatalogued_declared_field_abstains(catalog, declared) -> None:
    """KEYSTONE. Both are unresolvable profile values, so both abstain in both directions."""
    facts = Facts(highest_degree="bachelor", field_of_study=declared)
    assert _one(catalog, _CS_ONLY, facts, "bachelor_in_field_required") == "unknown"
    assert _one(catalog, "Bachelor's degree in Nursing is required.", facts,
                "bachelor_in_field_required") == "unknown"


def test_the_rank_bar_still_decides_before_the_field(catalog) -> None:
    """No field can rescue a missing degree, so a rank below the bar stays decidable even
    when the declared field is exactly the one named."""
    assert _one(catalog, _CS_ONLY,
                Facts(highest_degree="none", field_of_study="computer_science"),
                "bachelor_in_field_required") == "unmet"


def test_a_masters_in_a_related_field_clears_a_bachelors_in_field_bar(catalog) -> None:
    """The realistic shape: a higher rank in a neighbouring field against the commonest
    degree sentence in existence."""
    facts = Facts(highest_degree="master", field_of_study="software_engineering")
    assert _one(catalog, _CS_OR_RELATED, facts, "bachelor_in_field_required") == "met"


def test_the_field_resolution_cites_the_field_of_study_fact(catalog) -> None:
    dets = [d for d in detect(_CS_ONLY, catalog, enabled_families=ALL)
            if d.pattern.id == "bachelor_in_field_required"]
    resolution = resolve(dets[0], _degree(field_of_study="computer_science"),
                         catalog.family("degree"))
    assert [s.profile_locator["field"] for s in resolution.support] == ["facts.field_of_study"]


@pytest.mark.parametrize("pattern_id", ["bachelor_in_field_required",
                                        "master_in_field_required",
                                        "doctorate_in_field_required"])
def test_every_in_field_pattern_captures_the_field_it_names(catalog, pattern_id) -> None:
    """A capture on one level and not its siblings is exactly the parity class findings
    115-124 closed: the level that lacks it would abstain forever with nothing raised."""
    body = {
        "bachelor_in_field_required": "Must have a Bachelor's degree in Computer Science.",
        "master_in_field_required": "Must have a Master's degree in Computer Science.",
        "doctorate_in_field_required": "Must have a Ph.D. in Computer Science.",
    }[pattern_id]
    dets = [d for d in detect(body, catalog, enabled_families=ALL)
            if d.pattern.id == pattern_id]
    assert len(dets) == 1
    captured = dets[0].values.get("study_field") or dets[0].values.get("study_field_alt")
    assert captured is not None and "Computer Science" in captured


# ---- support and rationale

def test_a_declared_fact_carries_its_canonical_rendering_as_the_quote(catalog) -> None:
    """eligibility_support's own comment describes support as "the profile text that
    produced it", so for a declared fact the quote is stated to be the canonical rendering
    of the VALUE, not a quotation (spec §4.3)."""
    dets = detect("Bachelor's degree required.", catalog, enabled_families=ALL)
    resolution = resolve(dets[0], Facts(highest_degree="bachelor"), catalog.family("degree"))
    assert len(resolution.support) == 1
    support = resolution.support[0]
    assert support.support_kind == "declared_fact"
    assert support.profile_locator == {"field": "facts.highest_degree"}
    assert support.evidence_quote == "bachelor"


def test_an_abstention_from_an_unset_fact_carries_no_support(catalog) -> None:
    dets = detect("Bachelor's degree required.", catalog, enabled_families=ALL)
    resolution = resolve(dets[0], Facts(), catalog.family("degree"))
    assert resolution.support == ()
    assert resolution.rationale


def test_every_resolution_carries_a_rationale(catalog) -> None:
    body = (
        "Applicants must be US citizens. 5+ years of experience required. "
        "Active Secret clearance required. Bachelor's degree required."
    )
    facts = Facts(
        work_authorization=WorkAuthFact(status="citizen", jurisdiction="us"),
        total_years_experience=8,
        security_clearance=ClearanceFact(scheme="us_dod", level="secret", state="active"),
        highest_degree="bachelor",
    )
    for det in detect(body, catalog, enabled_families=ALL):
        resolution = resolve(det, facts, catalog.family(det.family))
        assert resolution.rationale.strip()
        assert resolution.disposition in {"met", "unmet", "unknown"}
