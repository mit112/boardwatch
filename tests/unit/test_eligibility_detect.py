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
