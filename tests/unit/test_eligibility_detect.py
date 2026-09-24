"""Detection is clause- or sentence-bounded and drops anything whose polarity it cannot
account for. Spans are ABSOLUTE offsets into posting_versions.body_text, which is
immutable and append-only, so a span is a permanently valid locator. That property is what
makes the audit trail evidence rather than decoration."""

from pathlib import Path

import pytest

from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.detect import (
    _SENTENCE_SPLIT,
    Detection,
    detect,
    jd_locator,
    split_units,
)

ALL = frozenset({"work_auth", "experience_years", "clearance", "degree"})


@pytest.fixture()
def catalog(tmp_path: Path):
    return load_rules(tmp_path / "no-override")


def _ids(dets: list[Detection]) -> list[str]:
    return [d.pattern.id for d in dets]


# ---------------------------------------------------------------- unit splitting

def test_sentences_split_on_terminators() -> None:
    units = split_units("First one. Second one! Third one?", "sentence")
    assert [text for _offset, text in units] == ["First one.", "Second one!", "Third one?"]


def test_a_dotted_abbreviation_does_not_split_a_sentence() -> None:
    """REGRESSION LOCK. A naive (?<=[.!?])\\s+ split "Open to U.S. citizens or permanent
    residents." into two units, so the citizen-or-LPR pattern could never match and a US
    permanent resident silently got zero rows."""
    text = "Open to U.S. citizens or permanent residents."
    assert [t for _o, t in split_units(text, "sentence")] == [text]


def test_a_trailing_acronym_still_splits() -> None:
    """The guard must not over-merge: "AWS." sees "WS." and splits normally."""
    units = split_units("Experience with AWS. Candidates must apply.", "sentence")
    assert len(units) == 2


def test_clauses_split_on_punctuation_but_never_on_and_or() -> None:
    """Splitting on "or" would destroy the degree family's OR-escape, and splitting on
    "and" would separate a negation from what it negates."""
    units = [t for _o, t in split_units("A; B: C, D and E or F", "clause")]
    assert units == ["A", " B", " C", " D and E or F"]


def test_offsets_locate_the_unit_the_splitter_actually_produced() -> None:
    """The previous form asserted text[i : i + len(unit)] == unit for an `i` that came
    from text.find(unit, cursor), which str.find already guarantees: ~700k probe inputs
    produced zero failures, by construction. Rebuilding the expected pairs from the
    delimiter match spans can actually fail, which is the point of a test."""
    text = "5+ years required. 5+ years required."
    expected, cursor = [], 0
    for match in _SENTENCE_SPLIT.finditer(text):
        expected.append((cursor, text[cursor : match.start()]))
        cursor = match.end()
    expected.append((cursor, text[cursor:]))
    assert [(o, u) for o, u in split_units(text, "sentence") if u] == [
        (o, u) for o, u in expected if u
    ]


def test_a_bullet_line_is_its_own_unit() -> None:
    """The marker stays attached. `\\n+` sits earlier in _SENTENCE_SPLIT's alternation and
    consumes the newline, so the bullet branch never sees the leading \\s it needs, and `^`
    does not match mid-string without re.MULTILINE. Harmless to matching, because every
    pattern is word- or boundary-anchored, and offsets stay absolute either way. Do NOT
    reorder the alternation to strip the marker: the 108-case corpus was verified against
    these matching semantics."""
    body = "Requirements:\n- 5+ years of experience\n- Bachelor's degree required"
    units = [t.strip() for _o, t in split_units(body, "sentence")]
    assert "- 5+ years of experience" in units


# ---------------------------------------------------------------- spans

def test_spans_quote_the_real_text(catalog) -> None:
    body = "We are hiring. Candidates must be legally authorized to work in the United States."
    dets = detect(body, catalog, enabled_families=ALL)
    assert len(dets) == 1
    start, end = dets[0].span
    assert body[start:end] in body
    assert "authorized to work in the United States" in body[start:end]
    assert jd_locator(dets[0]) == {"field": "body_text", "span": [start, end]}


def test_spans_are_offset_correctly_in_a_later_sentence(catalog) -> None:
    prefix = "A" * 500 + ". "
    body = prefix + "Bachelor's degree required."
    dets = detect(body, catalog, enabled_families=ALL)
    assert dets
    start, _end = dets[0].span
    assert start >= len(prefix)


# ---------------------------------------------------------------- dropping rules

def test_a_negation_in_the_same_unit_drops_only_the_negated_clause(catalog) -> None:
    """The clearance sentence is a POSITIVE CONTROL. Asserting only the ABSENCE of rows
    cannot tell a fired drop rule from detection returning [] for every input, and seven
    of this file's tests passed against exactly that. Every drop test below carries one."""
    body = "We do not require 5+ years of experience. Active Secret clearance required."
    assert _ids(detect(body, catalog, enabled_families=ALL)) == ["active_secret_required"]


def test_a_trailing_negation_in_the_same_unit_drops_it(catalog) -> None:
    body = "5+ years of experience is not required. Active Secret clearance required."
    assert _ids(detect(body, catalog, enabled_families=ALL)) == ["active_secret_required"]


def test_a_pattern_that_consumes_its_own_negation_survives(catalog) -> None:
    """"Sponsorship is unavailable" carries its negation INSIDE the matched span, so the
    unit-scoped cue check must not delete it."""
    assert _ids(detect("Sponsorship is unavailable.", catalog, enabled_families=ALL)) == [
        "no_sponsorship_offered"
    ]


def test_a_negation_in_a_neighbouring_unit_does_not_drop_this_one(catalog) -> None:
    body = "A degree is not required. Active Secret clearance required."
    assert _ids(detect(body, catalog, enabled_families=ALL)) == ["active_secret_required"]


def test_a_clause_bounded_negation_spares_a_floor_in_another_clause(catalog) -> None:
    """MECHANISM AC (F8). Polarity is CLAUSE-bounded, not unit-bounded, so the `not` in the
    first clause cancels only the degree there; the experience floor in the SECOND clause of
    the same sentence survives. A unit-wide cue search dropped it and returned `eligible`
    with zero rows. This is the multi-clause POSITIVE row the mechanism update requires."""
    body = "We do not require a degree, but 5+ years of experience is required."
    ids = _ids(detect(body, catalog, enabled_families=ALL))
    assert "total_years_minimum" in ids  # the floor in clause two survives
    assert not any(i.endswith("degree_required") for i in ids)  # the negated degree is gone


def test_a_cross_sentence_escape_abstains_the_row_rather_than_dropping_it(catalog) -> None:
    """REGRESSION LOCK for corpus row D23, under the SETTLED mechanism. A qualifying escape
    in a later sentence may genuinely waive a requirement, but DROPPING it would return
    `eligible` by silence, the worst direction. `abstain_by` keeps the degree row VISIBLE
    and marks it, so the resolver can render UNKNOWN rather than a clean pass. The clearance
    sentence is the positive control: it is decided, not abstained."""
    body = (
        "Bachelor's degree required. Equivalent experience may be substituted at the "
        "hiring manager's discretion. Active Secret clearance required."
    )
    by_id = {d.pattern.id: d for d in detect(body, catalog, enabled_families=ALL)}
    assert set(by_id) == {"active_secret_required", "bachelor_required"}
    assert by_id["bachelor_required"].abstained  # kept visible, marked undecidable
    assert by_id["active_secret_required"].abstained is None  # positive control, decided


def test_the_unleveled_degree_pattern_stands_down_when_a_level_is_named(catalog) -> None:
    """REGRESSION LOCK. "A Bachelor's degree is required." also matches the substring
    "degree is required", and the extra unleveled row turned a correct `met` into an
    overall `uncertain`."""
    assert _ids(detect("A Bachelor's degree is required.", catalog, enabled_families=ALL)) == [
        "bachelor_required"
    ]


def test_company_side_years_are_suppressed(catalog) -> None:
    """REGRESSION LOCK. "Our founding team brings over 40 years of combined experience"
    produced a wrong `unmet` for every user, on a very common startup phrasing.

    Membership rather than equality, because "combined experience" also matches the SCOPED
    pattern, which carries no company-side suppressor and always resolves `unknown`.
    """
    body = (
        "Our founding team brings over 40 years of combined experience. "
        "Active Secret clearance required."
    )
    found = _ids(detect(body, catalog, enabled_families=ALL))
    assert "total_years_minimum" not in found
    assert "active_secret_required" in found  # positive control


def test_a_degree_gated_disjunction_abstains_the_pure_years_bar(catalog) -> None:
    """REGRESSION LOCK for the P5 SpaceX false positive (Gate-P5 precision).

    "A Bachelor's ... OR N years of experience" is a DISJUNCTION: the posting clears on
    EITHER the degree-gated path OR the pure-experience path. Reading the pure-years arm as
    a hard floor told a master's-plus-one-year candidate INELIGIBLE, deleting a real job —
    the unrecoverable direction. The degree branch is undecidable (field of study is not
    stored), so the years bar ABSTAINS rather than resolving `unmet`, exactly as the degree
    family abstains on "degree OR equivalent experience".
    """
    body = "A Bachelor's degree in Computer Science or 3+ years of professional experience is required."
    dets = detect(body, catalog, enabled_families=ALL)
    by_id = {d.pattern.id: d for d in dets}
    assert by_id["total_years_minimum"].abstained  # the "... or 3+ years ..." arm is undecidable
    assert any(d.family == "degree" for d in dets)  # positive control: degree family still fires


def test_a_plain_years_floor_with_no_degree_alternative_is_still_decided(catalog) -> None:
    """The positive control for the disjunction guard: a floor that is NOT part of an
    either-path disjunction must stay decidable, or the guard would spare every hard bar."""
    dets = [d for d in detect("8+ years of professional experience is required.",
                              catalog, enabled_families=ALL)
            if d.pattern.id == "total_years_minimum"]
    assert dets and all(d.abstained is None for d in dets)


def test_the_disjunction_abstain_waives_only_the_bar_its_OR_joins(catalog) -> None:
    """T104/D-531 REPLACED the document-scoped form this test used to lock.

    It previously asserted that a disjunction ANYWHERE abstains EVERY years bar in the
    posting, "including a plain co-located floor" — which is astra finding 4's complaint
    stated as settled behaviour, and it contradicted D-449: the word `or` is what clears a
    bar, so it clears the bar it JOINS and not a separate floor stated elsewhere. The escape
    now reaches its own unit and the next, and only where that next unit states no
    requirement of its own.

    The 3-year arm is inside the disjunction and still abstains. The 10-year floor is a
    separate bar and now DECIDES."""
    body = (
        "A Bachelor's degree in CS or 3+ years of experience is required. "
        "10+ years of professional experience is required."
    )
    by_years = {d.values.get("years"): d
                for d in detect(body, catalog, enabled_families=ALL)
                if d.pattern.id == "total_years_minimum"}
    assert set(by_years) == {"3", "10"}
    assert by_years["3"].abstained          # joined by `or` to the degree
    assert by_years["10"].abstained is None  # a separate floor, decided


def test_reordering_unrelated_requirements_does_not_change_which_is_waived(catalog) -> None:
    """THE TICKET'S OWN CONTROL for T104, and it is only satisfiable under a bounded reach.

    The reach is forward-only, so without the ownership guard this pair would disagree:
    putting the disjunction FIRST would leave the floor untouched, and putting it SECOND
    would let it waive the floor in the sentence before. The guard makes the two orders
    agree for the right reason — in the second order the escape's own sentence carries its
    own years bar, so it belongs to that bar and cannot reach back.
    """
    first = ("A Bachelor's degree in CS or 3+ years of experience is required. "
             "10+ years of professional experience is required.")
    second = ("10+ years of professional experience is required. "
              "A Bachelor's degree in CS or 3+ years of experience is required.")

    def waived(body: str) -> dict[str, bool]:
        return {d.values["years"]: bool(d.abstained)
                for d in detect(body, catalog, enabled_families=ALL)
                if d.pattern.id == "total_years_minimum"}

    assert waived(first) == waived(second) == {"3": True, "10": False}


def test_a_SAME_sentence_disjunction_abstains_the_SCOPED_arm(catalog) -> None:
    """The owner's ruling, at the mechanism that carries it. D-449 is where the question
    was left open, and where the two populations it splits into are sized.

    "Bachelor's degree or 5+ years of software engineering experience." is one sentence with
    two paths, and the owner ruled the degree path clears it — "because of the wording of
    'or', degree should clear it". The bar therefore ABSTAINS on the scoped arm exactly as it
    already did on the total arm, and the word `software` stops deciding whether a posting is
    deleted from view.

    The escape reaching this pattern is `abstain_by_sentence`, NOT the document-scoped
    `abstain_by` the total arm uses. That distinction is the next test.
    """
    body = "Bachelor's degree or 5+ years of software engineering experience."
    dets = [d for d in detect(body, catalog, enabled_families=ALL)
            if d.pattern.id == "scoped_years_minimum"]
    assert dets and dets[0].abstained  # kept visible, marked undecidable


def test_a_CROSS_sentence_disjunction_does_NOT_reach_a_SCOPED_bar(catalog) -> None:
    """THE OWNER'S OTHER RULING, and the reason the escape above is sentence-scoped (D-449).

    Asked whether a degree disjunction waives a SEPARATE skill bar stated elsewhere, he ruled
    it does not, and his reasoning for the same-sentence case is what makes the two consistent:
    the word `or` is what clears the bar, and no `or` joins these two clauses. 7 live postings
    depend on this staying `ineligible`.

    So this test is the durable form of that ruling. It FAILS if the escape is ever widened to
    document scope — which is precisely the wiring D-447 built and D-449 refused, because it
    would have fixed the same-sentence class and broken this one silently.
    """
    body = (
        "A Bachelor's degree in CS or 3+ years of experience is required.\n"
        "8+ years of C++ experience is required."
    )
    dets = [d for d in detect(body, catalog, enabled_families=ALL)
            if d.pattern.id == "scoped_years_minimum"]
    assert dets, "the separate skill bar must still be DETECTED"
    assert all(d.abstained is None for d in dets), (
        "a disjunction in another sentence must not waive a separate skill bar"
    )
    # Positive control: the disjunction is real and IS reaching its own sentence's total arm,
    # so a green assertion above cannot be a regex that simply never matches this body.
    total = [d for d in detect(body, catalog, enabled_families=ALL)
             if d.pattern.id == "total_years_minimum"]
    assert total and total[0].abstained


def test_a_range_years_disjunction_with_a_degree_abstains(catalog) -> None:
    """The disjunction guard is on the range pattern too: "3-5 years of experience or a
    Master's degree" is the same either-path requirement as the total-years form."""
    body = "3-5 years of experience or a Master's degree is required."
    dets = [d for d in detect(body, catalog, enabled_families=ALL)
            if d.pattern.id == "range_years_minimum"]
    assert dets and dets[0].abstained  # kept visible, marked undecidable


def test_or_coordinating_fields_of_study_does_not_abstain_a_years_bar(catalog) -> None:
    """NEGATIVE control for the disjunction guard. "Bachelor's degree in X, Y, or a related
    field" coordinates FIELDS OF STUDY, not a degree-vs-experience choice, and the years bar
    lives in a separate sentence. Abstaining it would silently spare a genuine floor. The
    guard must require the `or` to bridge the degree directly to a years-of-experience arm,
    not cross a line break into an unrelated requirement."""
    body = (
        "Bachelor's degree in Computer Science, Software Engineering, or a related field.\n"
        "0-2 years of professional experience is required."
    )
    dets = [d for d in detect(body, catalog, enabled_families=ALL)
            if d.pattern.id in ("total_years_minimum", "range_years_minimum")]
    assert dets  # the years bar is detected
    assert all(d.abstained is None for d in dets)  # ...and decided, never abstained


def test_a_possessive_years_apostrophe_still_states_a_floor(catalog) -> None:
    """"5 years' experience" is a common formal phrasing of a floor. The `\\b` after `years`
    sat immediately before the apostrophe, so the `\\s+experience` connective never reached
    across it and the floor was silently lost — `eligible` by silence, the worst direction."""
    ids = _ids(detect("5 years' experience is required.", catalog, enabled_families=ALL))
    assert "total_years_minimum" in ids


def test_a_qualifier_before_a_multiword_scope_is_detected(catalog) -> None:
    """"5+ years of demonstrated full stack development experience" is a real floor. Until the
    experience-qualifier vocabulary grew, "demonstrated" was neither a whitelisted adjective
    nor consumable inside the scoped-noun window, so four words sat between `of` and
    `experience` and no floor pattern fired at all."""
    ids = _ids(detect(
        "5+ years of demonstrated full stack development experience is required.",
        catalog, enabled_families=ALL,
    ))
    assert "scoped_years_minimum" in ids


def test_an_age_requirement_never_reads_as_an_experience_floor(catalog) -> None:
    """REGRESSION LOCK for the widened vocabulary. "18 years of age" is a legal-age bar, not
    an experience floor; the scoped-noun arm excludes `age`/`old` as a leading token so no
    following clause is pulled into a spurious years bar. The real 5-year floor in the next
    sentence is the positive control — the guard must not silence a genuine floor."""
    body = "Must be at least 18 years of age. 5 years of professional experience is required."
    ids = _ids(detect(body, catalog, enabled_families=ALL))
    assert ids.count("total_years_minimum") == 1  # the real floor, detected once
    assert "scoped_years_minimum" not in ids  # nothing spurious from "years of age"


# ---------------------------------------------------------------- scoping and ordering

def test_an_ignored_family_is_never_matched(catalog) -> None:
    body = "Bachelor's degree required."
    assert detect(body, catalog, enabled_families=frozenset({"clearance"})) == []
    assert detect(body, catalog, enabled_families=frozenset({"degree"}))


def test_detections_are_ordered_by_family_then_span(catalog) -> None:
    """Requirement ordinal is dense from 0 in this order, and store/eligibility.py:128
    assigns ordinals by enumerate, so the ENGINE must pass a pre-sorted list."""
    body = (
        "Applicants must be US citizens. 5+ years of experience required. "
        "Active Secret clearance required. Bachelor's degree required."
    )
    dets = detect(body, catalog, enabled_families=ALL)
    families = [d.family for d in dets]
    assert families == ["work_auth", "experience_years", "clearance", "degree"]
    assert families == sorted(
        families, key=lambda f: [x.id for x in catalog.families].index(f)
    )


def test_captured_values_are_exposed(catalog) -> None:
    dets = detect("At least 6 years of industry experience.", catalog, enabled_families=ALL)
    assert dets[0].values["years"] == "6"


def test_a_range_captures_its_lower_bound(catalog) -> None:
    dets = detect("3-5 years of experience.", catalog, enabled_families=ALL)
    assert _ids(dets) == ["range_years_minimum"]
    assert dets[0].values["years"] == "3"


def test_an_empty_body_yields_nothing(catalog) -> None:
    """The second assertion is the positive control: an empty-body assertion on its own is
    the single easiest test in this file to pass with detection completely broken."""
    assert detect("", catalog, enabled_families=ALL) == []
    assert detect("Active Secret clearance required.", catalog, enabled_families=ALL)


def test_prose_with_no_requirement_yields_nothing(catalog) -> None:
    """Every sentence here is a near miss for a different family. The trailing clearance
    sentence is the positive control, so the prose producing nothing is a finding rather
    than an artefact of detection returning [] for everything."""
    body = (
        "Come experience the difference. Our team clears blockers fast. "
        "You will model degrees of freedom in the solver. We sponsor local meetups. "
        "Active Secret clearance required."
    )
    assert _ids(detect(body, catalog, enabled_families=ALL)) == ["active_secret_required"]


# ------------------------------------------------- the in-field bridge bound ({2,160})

def test_a_multi_field_degree_enumeration_produces_a_row_at_all(catalog) -> None:
    """REGRESSION LOCK. At {2,60} the lazy bridge between "in" and the requirement marker
    could not span a real field enumeration, so this sentence produced **zero rows** — not a
    truncated capture, no row. A posting stating a hard degree requirement therefore read as
    though it stated none, which is the "no flags is not cleared" failure the keystone names.
    """
    body = (
        "A Bachelor's degree in Computer Science, Computer Engineering, Mathematics, "
        "or a related discipline is required."
    )
    dets = detect(body, catalog, enabled_families=frozenset({"degree"}))
    assert [d.pattern.id for d in dets] == ["bachelor_in_field_required"]


def test_the_field_capture_reaches_the_related_field_escape(catalog) -> None:
    """The capture length is the load-bearing half, not just whether a row exists.

    The escape ("or a related discipline") sits at the END of the enumeration, so a capture
    that stops early keeps the row but drops the escape — and a posting that plainly opened
    its field list then reads as naming one specific field. That is the wrong direction: it
    turns an abstain into a decidable-looking narrow requirement.
    """
    body = (
        "A Bachelor's degree in Computer Science, Computer Engineering, Mathematics, "
        "or a related discipline is required."
    )
    (det,) = detect(body, catalog, enabled_families=frozenset({"degree"}))
    captured = det.values.get("study_field") or det.values.get("study_field_alt")
    assert captured is not None
    assert "Computer Science" in captured
    assert "related discipline" in captured


def test_the_field_bridge_is_still_closed(catalog) -> None:
    """The bound is WIDER, not gone. `[^.;:]` plus `scope: sentence` already confine a match
    to one sentence, but an unbounded lazy bridge over a long sentence lets a field named in
    one clause reach a `required` that belongs to another. Padding past 160 characters must
    still yield no row — this is what fails if the bound is ever replaced with `{2,}`.
    """
    padding = "and broad exposure to distributed systems at scale in production " * 4
    body = f"A Bachelor's degree in Computer Science {padding} is required."
    assert len(padding) > 160
    dets = detect(body, catalog, enabled_families=frozenset({"degree"}))
    assert "bachelor_in_field_required" not in [d.pattern.id for d in dets]


def test_the_field_bridge_never_crosses_a_clause_terminator(catalog) -> None:
    """`[^.;:]` is what stops the bridge, not the sentence splitter: a semicolon does not end
    a sentence unit, so if the class were relaxed to `.` this row would appear and attribute a
    requirement marker from a different clause to the degree's field.
    """
    body = "A Bachelor's degree in Computer Science; prior production experience is required."
    dets = detect(body, catalog, enabled_families=frozenset({"degree"}))
    assert "bachelor_in_field_required" not in [d.pattern.id for d in dets]


# ---------------------------------------------------------------- unit-splitting cost

def test_units_are_split_once_per_scope_not_once_per_pattern(
    catalog, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`split_units` is pure in (body_text, scope), so `detect` must call it once per DISTINCT
    scope, not once per pattern.

    Every other test in this file asserts detection OUTPUT, which is identical either way, so
    none of them can see this: the unmemoized loop called `split_units` once for each of the
    catalog's 55 patterns and returned exactly the same rows. The cost was real — that repeated
    split was ~37% of an `evaluate()` profile over real bodies.

    The pattern-count assertion is what stops the call-count bound being trivially satisfied:
    a two-pattern catalog would meet `<= 2` with no memoisation at all.
    """
    from boardwatch.eligibility import detect as detect_module

    every_family = frozenset(family.id for family in catalog.families)
    patterns_walked = sum(len(family.patterns) for family in catalog.families)
    scopes = {pattern.scope for family in catalog.families for pattern in family.patterns}
    assert patterns_walked >= 20, patterns_walked
    assert len(scopes) >= 2, scopes

    calls: list[str] = []
    real = detect_module.split_units

    def spy(text: str, scope: str) -> list[tuple[int, str]]:
        calls.append(scope)
        return real(text, scope)

    monkeypatch.setattr(detect_module, "split_units", spy)
    body = (
        "Senior Backend Engineer. A Bachelor's degree in Computer Science is required. "
        "Candidates must have 5+ years of experience with distributed systems, and an "
        "active Secret clearance is required. We do not sponsor work visas; applicants "
        "must be authorized to work in the United States."
    )
    detect_module.detect(body, catalog, enabled_families=every_family)

    assert calls, "the spy never fired, so this test proves nothing"
    assert len(calls) == len(set(calls)), calls  # no scope split twice
    assert len(calls) <= len(scopes)
    assert len(calls) <= 2  # the literal contract, independent of the catalog's shape


# ------------------------------------ experience-years recall, the 2026-09-05 widenings
#
# MEASURED: 32,602 of 96,266 current evaluations carry ZERO requirement rows, and on a
# 2,000-posting random sample 5.5% state an "N years ... experience" bar the catalog matched
# nothing on. Each test below quotes a span verbatim from a real posting in that residue and
# names which pattern now catches it. The controls under them are the other half of the same
# measurement: the phrasings that look like a years bar and are not.

def _by_id(dets: list[Detection]) -> dict[str, Detection]:
    return {d.pattern.id: d for d in dets}


def test_a_range_bar_survives_a_parenthetical_that_hedges_a_DIFFERENT_bar(catalog) -> None:
    """"0-1 years of professional software development experience (1+ years of internship
    experience desirable)" is one clause: no comma, no conjunction. So the aside's
    `desirable` was the whole sentence's hedge, it stood the floor down, and the posting
    wrote NO experience row at all.

    The aside states its own duration, which is what says the hedge has a bar of its own to
    belong to. The floor outside it is real and stays required; the aside's own `1+ years of
    internship experience` stays hedged, which is the second assertion.
    """
    body = ("0-1 years of professional software development experience "
            "(1+ years of internship experience desirable)")
    dets = detect(body, catalog, enabled_families=ALL)
    found = _by_id(dets)
    assert "scoped_range_years_minimum" in found
    detection = found["scoped_range_years_minimum"]
    assert detection.values["years"] == "0"
    start, end = detection.span
    assert body[start:end] == "0-1 years of professional software development experience"
    # the aside is a PREFERENCE: nothing inside it may become a second required bar
    aside = body.index("(")
    assert [d.pattern.id for d in dets if d.span[0] > aside] == []


@pytest.mark.parametrize("body,hedge", [
    ("5+ years of experience (preferred).", "preferred"),
    ("5+ years of experience (strongly preferred).", "strongly preferred"),
    ("5+ years of experience (nice to have).", "nice to have"),
    ("5+ years of experience (a plus).", "a plus"),
])
def test_a_bare_parenthetical_hedge_still_stands_the_bar_down(catalog, body, hedge) -> None:
    """THE CONTROL THAT BOUNDS THE TEST ABOVE, and the reason the aside rule asks for a
    duration rather than merely for parentheses. A trailing "(preferred)" IS the sentence's
    hedge; reading it as a hard floor is the worst wrong verdict this family can produce.

    `total_years_preferred` is the positive control: the bar is still SEEN, as a preference.
    """
    dets = detect(body, catalog, enabled_families=ALL)
    assert "total_years_minimum" not in _ids(dets), hedge
    assert "total_years_preferred" in _ids(dets)


def test_comma_separated_adjectives_no_longer_break_the_run(catalog) -> None:
    """"2-4 years of professional, post University experience". The adjective run was
    `(?:\\s+ADJ)*` and cannot cross a COMMA, so it stopped at `professional,` and no tail
    could reach `experience`. The posting wrote no row.

    The comma allowance is `(?:\\s*,)?`, NOT `\\s*,?`: inside the atomic group the greedy
    form ate the space separating the run from the domain phrase and could not give it back,
    which silently broke `2-12+ years of industry software engineering experience` — the
    control in the next test.
    """
    body = "2-4 years of professional, post University experience"
    found = _by_id(detect(body, catalog, enabled_families=ALL))
    assert "scoped_range_years_minimum" in found
    detection = found["scoped_range_years_minimum"]
    assert detection.values["years"] == "2"
    assert body[detection.span[0]:detection.span[1]] == body


def test_an_en_dash_range_with_a_plus_on_the_upper_bound_still_fires(catalog) -> None:
    """CONTROL, green before and after: "Minimum Requirements 2–12+ years of industry
    software engineering experience" already matched, and the comma allowance above is the
    change most likely to break it (see that test's second paragraph)."""
    body = "Minimum Requirements 2–12+ years of industry software engineering experience"
    found = _by_id(detect(body, catalog, enabled_families=ALL))
    assert "scoped_range_years_minimum" in found
    detection = found["scoped_range_years_minimum"]
    assert detection.values["years"] == "2"
    assert body[detection.span[0]:detection.span[1]] == (
        "2–12+ years of industry software engineering experience"
    )


def test_an_abbreviated_year_unit_is_the_same_bar(catalog) -> None:
    """"2+ Yrs of experience". Every pattern in the family spelled the unit `years?`, so a
    posting that abbreviates it wrote no row — the same class as the months forms, one
    spelling further down."""
    body = "2+ Yrs of experience"
    found = _by_id(detect(body, catalog, enabled_families=ALL))
    assert "total_years_minimum" in found
    detection = found["total_years_minimum"]
    assert detection.values["years"] == "2"
    assert body[detection.span[0]:detection.span[1]] == "2+ Yrs of experience"


@pytest.mark.parametrize("body,span,years", [
    ("Experience Required: 3 to 5 years", "Experience Required: 3 to 5 years", "3"),
    ("Experience Required: 1 to 3 years", "Experience Required: 1 to 3 years", "1"),
    ("Experience Required -6+ Years", "Experience Required -6+ Years", "6"),
])
def test_the_noun_first_labelled_bar_is_detected(catalog, body, span, years) -> None:
    """Every pattern in the family reads left to right from the NUMBER and needs the bar's
    noun, a domain phrase or a gerund to FOLLOW it. When the posting labels the block instead
    there is no tail to anchor on, and these three wrote no row at all.

    The range form captures the LOW end, exactly as `range_years_minimum` does: a "3 to 5
    years" bar is unmet for a one-year profile on its floor alone.
    """
    found = _by_id(detect(body, catalog, enabled_families=ALL))
    assert "labeled_years_minimum" in found, _ids(detect(body, catalog, enabled_families=ALL))
    detection = found["labeled_years_minimum"]
    assert detection.values["years"] == years
    assert body[detection.span[0]:detection.span[1]] == span


def test_a_hedged_scoped_bar_never_becomes_a_REQUIRED_row(catalog) -> None:
    """"Minimum of 2 years of frontend engineering experience preferred" — the one phrasing
    in the residue whose only wrong answer is a REQUIRED row. `scoped_years_minimum` matches
    the sentence and `years_hedges` stands it down, which is what this pins.

    It writes no row at all today: the family carries `total_years_preferred` and
    `range_years_preferred` but no scoped/domain preferred sibling, so a hedged bar carrying
    a domain noun is invisible rather than recorded as a preference. That gap is NOT closed
    here — a new preferred pattern is a recall change with its own measurement — so this
    asserts only the half that decides a verdict.
    """
    body = "Minimum of 2 years of frontend engineering experience preferred"
    dets = detect(body, catalog, enabled_families=ALL)
    assert [d for d in dets if d.pattern.requiredness == "required"] == []


@pytest.mark.parametrize("body", [
    "$100,000 - $115,000 year",
    "We have grown a great deal over the years.",
    "Must be 18 years of age or older.",
    "Applicants must be 18 years or older.",
    "This is a year-end bonus.",
    "The fiscal year begins in July.",
])
def test_the_years_word_without_a_bar_writes_no_experience_row(catalog, body) -> None:
    """THE NEGATIVE CONTROLS for every widening above. Salary text, ordinary prose, and an
    AGE floor are the three ways `years` appears in a JD without stating an experience bar.

    "Applicants must be 18 years or older." is the one that was NOT green before: nothing
    followed `years` that `domain_years_minimum`'s stopword head knew about, so `or` was read
    as the head of a domain phrase and an 18-year AGE floor resolved `unmet` against every
    profile this tool is for. `age` and `old` were already in that head; `or` and `older`
    were not, and one word decided whether the posting was deleted from view.
    """
    dets = [d for d in detect(body, catalog, enabled_families=ALL)
            if d.family == "experience_years"]
    assert dets == [], _ids(dets)


# ------------------------------------------------- abstain_by_adjacent (T104 mechanism)

_ADJACENT_CATALOG = """
version: 1
negation_cues: ["not"]
families:
  - id: degree
    label: Degree
    tier: profile
    fact: highest_degree
    answer_type: choice
    default_policy: blocker
    question: "Highest degree?"
    fields:
      - name: highest_degree
        type: choice
        choices: [none, bachelor]
        ranks: {none: 0, bachelor: 3}
    implies_vocabulary: [degree_required]
    exclusive_groups: []
    patterns:
      - id: bachelor_required
        requiredness: required
        implies: degree_required
        scope: sentence
        required_rank: 3
        requirement_text: "A bachelor's degree is required"
        %(key)s:
          - "may be substituted"
        pattern: "A degree is required"
"""


def _reach(tmp_path: Path, key: str, body: str) -> bool:
    """Whether the lone `bachelor_required` detection in `body` abstained, under `key`."""
    config = tmp_path / key
    config.mkdir(parents=True, exist_ok=True)
    (config / "rules.yaml").write_text(_ADJACENT_CATALOG % {"key": key}, encoding="utf-8")
    dets = detect(body, load_rules(config), enabled_families=frozenset({"degree"}))
    assert len(dets) == 1, f"fixture broke: expected one detection, got {_ids(dets)}"
    return bool(dets[0].abstained)


_OWN = "A degree is required, though it may be substituted."
_NEXT = "A degree is required. Equivalent experience may be substituted."
_TWO_AWAY = "A degree is required. We write Python. Equivalent experience may be substituted."


def test_abstain_by_adjacent_reaches_its_own_unit_and_the_next_one(tmp_path: Path) -> None:
    """An equivalence escape is normally written as the FOLLOWING sentence, which is why
    `abstain_by_sentence` cannot carry it and `abstain_by` (document) over-reaches."""
    assert _reach(tmp_path, "abstain_by_adjacent", _OWN)
    assert _reach(tmp_path, "abstain_by_adjacent", _NEXT)


def test_abstain_by_adjacent_stops_at_the_next_unit(tmp_path: Path) -> None:
    """THE WHOLE POINT OF THE SCOPE, and the assertion that makes the pair above non-vacuous.

    One sentence further and the escape no longer reaches — that is the difference between
    this scope and `abstain_by`, and without this the new field would be indistinguishable
    from the document-scoped one it narrows (astra finding 4).
    """
    assert not _reach(tmp_path, "abstain_by_adjacent", _TWO_AWAY)


def test_the_document_scope_DOES_reach_two_units_away(tmp_path: Path) -> None:
    """The control for the test above: same body, same escape, only the scope differs.

    If this ever stops abstaining, the test above starts passing for the wrong reason — the
    escape would be failing to match at all rather than being held back by its reach.
    """
    assert _reach(tmp_path, "abstain_by", _TWO_AWAY)


def test_abstain_by_sentence_does_NOT_reach_the_next_unit(tmp_path: Path) -> None:
    """The other neighbour, pinned for the same reason: `abstain_by_adjacent` is a SIXTH
    scope only if it differs from the fifth. Same body as the adjacent test that passes."""
    assert not _reach(tmp_path, "abstain_by_sentence", _NEXT)


# ------------------------------------- the heading view adds only a NEW reading (T163)

def _readings(dets: list[Detection]) -> list[tuple[str, tuple[int, int], dict[str, str]]]:
    return [(d.pattern.id, d.span, d.values) for d in dets]


@pytest.mark.parametrize("body,pattern_id,span,values", [
    (
        "Preferred Qualifications:\n- 5 years of experience preferred.",
        "total_years_preferred", (28, 59), {"years": "5"},
    ),
    (
        "Preferred:\n- 3-5 years of experience preferred.",
        "range_years_preferred", (13, 46), {"years": "3"},
    ),
])
def test_a_hedged_bullet_under_a_hedge_heading_writes_its_preferred_row_once(
    catalog, body, pattern_id, span, values
) -> None:
    """The bullet states its own hedge, so its own view already reads the bar as preferred.
    The heading view then read the SAME bar a second time, through the pattern's other layout
    (`years_alt`), and the posting persisted two rows for one requirement.

    The own view's row is the one that stands: the heading view exists to add a reading the
    bullet alone does not produce, and here it adds none.
    """
    dets = detect(body, catalog, enabled_families=ALL)
    assert _readings(dets) == [(pattern_id, span, values)]


@pytest.mark.parametrize("body,readings", [
    (
        "Nice to have:\n- 5 years of experience.",
        [("total_years_preferred", (16, 37), {"years_alt": "5"})],
    ),
    (
        "Nice to have:\n- 5 years of experience preferred.\n- 5 years of experience.",
        [
            ("total_years_preferred", (16, 47), {"years": "5"}),
            ("total_years_preferred", (51, 72), {"years_alt": "5"}),
        ],
    ),
])
def test_a_bare_bullet_under_a_hedge_heading_still_gets_its_preferred_row(
    catalog, body, readings
) -> None:
    """CONTROL: the heading view's reason to exist. A bullet that states no hedge gets no
    preferred row from its own view, so its one row comes from the heading view.

    The record is per UNIT: the second body's first bullet reads the same bar on its own, and
    that does not stand down the heading view's row for the bare bullet after it.
    """
    dets = detect(body, catalog, enabled_families=ALL)
    assert _readings(dets) == readings


REACHES_ACROSS_A_COMMA = r"""
version: 1
negation_cues: ["not"]
families:
  - id: degree
    label: Degree
    tier: profile
    fact: highest_degree
    answer_type: choice
    default_policy: preference
    question: "Highest degree?"
    fields:
      - name: highest_degree
        type: choice
        choices: [none, bachelor]
        ranks: {none: 0, bachelor: 3}
    implies_vocabulary: [degree_preferred]
    exclusive_groups: []
    patterns:
      - id: bachelor_preferred
        requiredness: preferred
        implies: degree_preferred
        scope: sentence
        required_rank: 3
        requirement_text: "A bachelor's degree is preferred"
        pattern: 'bachelor degree[^.]{0,30}?preferred|preferred:\s*-?\s*bachelor degree'
"""


def test_a_suppressed_own_view_match_does_not_hide_the_heading_view_row(tmp_path: Path) -> None:
    """CONTROL: the comparison is against what the own view APPENDED, not what it matched.

    The bullet's own layout matches from the number through `preferred` and holds the `not`
    inside its span, so `_cue_inside` drops it. The heading view's span stops at `degree`,
    and the `not` sits in the next clause, so its row stands exactly as it did before T163.

    A catalog of its own since T174: the shipped twins no longer reach a hedge across a comma,
    so no shipped pattern can put the `not` inside its own-view span and outside its heading
    view's clause.
    """
    (tmp_path / "rules.yaml").write_text(REACHES_ACROSS_A_COMMA, encoding="utf-8")
    catalog = load_rules(tmp_path)
    body = "Preferred Qualifications:\n- Bachelor degree, not required but preferred."
    bullet = body.split("\n")[1]
    (pattern,) = catalog.family("degree").patterns
    assert pattern.regex.search(bullet) is not None, "fixture broke: the own view must match"
    dets = detect(body, catalog, enabled_families=ALL)
    # The heading-view row is quoted from its bar, not from the heading (T180 F7), so the span
    # starts at `Bachelor`, not at `Preferred Qualifications:`.
    assert _readings(dets) == [("bachelor_preferred", (28, 43), {})]


def test_a_required_bar_under_a_hedge_heading_is_unchanged(catalog) -> None:
    """CONTROL: a required pattern never gets the heading view, so nothing here touches it.

    The bullet states the SAME number twice, hedged and then required, so the required row and
    the heading view's preferred row share their captures. The record is per pattern: the
    required row does not stand the preferred one down, and neither is duplicated.
    """
    body = "Nice to have:\n- 5 years of experience; 5 years of experience is required."
    dets = detect(body, catalog, enabled_families=ALL)
    assert _readings(dets) == [
        ("total_years_preferred", (16, 37), {"years_alt": "5"}),
        ("total_years_minimum", (39, 60), {"years": "5"}),
    ]


def test_a_different_bar_with_the_same_captures_in_one_bullet_keeps_its_row(catalog) -> None:
    """Review round 1 (T163): the record must key on the SAME TEXT, not only equal captures.

    Both bars capture a lower bound of 3. The own view reads `3-7 ... preferred`; the heading
    view reads `Preferred: 3-5 years of experience`, a different bar whose text lies elsewhere in
    the bullet. It must stand, exactly as it did before T163.
    """
    body = (
        "Preferred:\n- 3-5 years of experience, across many industries; "
        "3-7 years of experience preferred."
    )
    readings = _readings(detect(body, catalog, enabled_families=ALL))
    assert [(p, values) for p, _, values in readings] == [
        ("range_years_preferred", {"years_alt": "3"}),
        ("range_years_preferred", {"years": "3"}),
    ], readings
