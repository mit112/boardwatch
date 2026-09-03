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


def test_the_disjunction_abstain_is_document_scoped(catalog) -> None:
    """SETTLED behaviour, locked so it is not misread as a bug. `abstain_by` is
    document-scoped by design (like the degree family's equivalence escape), so a
    disjunction anywhere in a posting abstains EVERY years bar in it, including a plain
    co-located floor. This is the safe direction — abstaining never deletes a real job, and
    the two-stage gate decides the abstained rows — and it kept the Gate-P5 blast radius to
    the single SpaceX row on the real 173-case set."""
    body = (
        "A Bachelor's degree in CS or 3+ years of experience is required. "
        "10+ years of professional experience is required."
    )
    dets = [d for d in detect(body, catalog, enabled_families=ALL)
            if d.pattern.id == "total_years_minimum"]
    assert len(dets) == 2 and all(d.abstained for d in dets)


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
