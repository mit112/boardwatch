"""Bounded heading context for bullet lists (T105, docs/program/DESIGN-T105-heading-context.md).

The golden corpus is one row per line and holds no newline, so it cannot express a heading
over its bullets at all. `HEADING_CASES` is the multi-line surface in its place, and it is
content-pinned the way the corpus is (`tools/generalization/fixtures.py`, R14): an edited
expected verdict here turns a red test green exactly as it would there.

Context travels OUT OF BAND. `split_units` is untouched, and `SPLIT_UNITS_DIGEST` pins its
output over every corpus body plus every body below, so a later edit that moves a unit's
text, count, offset or order fails here instead of silently re-aiming `abstain_by_adjacent`.

Profile P is astra's: EAD needing sponsorship, one year, a master's in computer science, no
clearance and none obtainable, full-time only, internships excluded, every family a blocker.
No corpus row carries all of it, so it is assembled from the rows that carry each part.
"""

from __future__ import annotations

import hashlib

import pytest

from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.detect import governing_headings, split_units
from boardwatch.eligibility.engine import evaluate
from boardwatch.eligibility.facts import Facts, Policy
from tests.pipeline.test_eligibility_corpus import CASES


def _corpus(prefix: str) -> tuple:
    (row,) = [case for case in CASES if case[0].startswith(f"{prefix}:")]
    return row


# Work auth, clearance and years from m1046; degree and field from m0954. The two employment
# preferences are in no corpus row and come from the ticket's statement of P.
P_FACTS = {
    **_corpus("m1046")[2],
    **_corpus("m0954")[2],
    "employment_type_preference": "fte_only",
    "internship_preference": "exclude",
}
# Resolved against the loaded catalog, so a family added later is a blocker too.
ALL_BLOCKERS = None

LADDER_261677 = (
    "Requirements:\n"
    "- HS Diploma (or equivalent) AND 4+ years of experience\n"
    "- OR Associate's degree AND 2+ years of experience\n"
    "- OR Bachelor's degree"
)
# Posting 261677's own line: the whole ladder is ONE line of inline bullets, not the multi-line
# list the design paraphrased, so the OR link has to open at an inline bullet as well as a line.
LADDER_261677_INLINE = (
    "Required Knowledge and Experience: • High School Diploma (or equivalent) AND 4+ years "
    "experience* • OR Associate’s Degree AND 2+ years experience* • OR Bachelor’s Degree "
    "*Relevant sales, clinical, or related experience in medical devices, medtech, healthcare, "
    "or life sciences."
)
BOUND_CONTROL = (
    "Nice to have:\n- 5 years of experience.\nRequirements:\n- 8 years of experience."
)

# (label, body, facts, policy, verdict, [[rule_id, requiredness, disposition], ...])
HEADING_CASES: list[tuple] = [
    ('h01:T105a the hedge comes from the heading', 'Nice to have:\n- 5 years of experience.', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:total_years_preferred', 'preferred', 'unmet']]),
    ("h02:T105c an OR line between bullets is the inline alternative", "You must meet either of the following:\n- A master's degree.\nOR\n- 5 years of experience.", P_FACTS, ALL_BLOCKERS, 'uncertain', [['experience_years:total_years_minimum', 'required', 'unknown']]),
    ('h03:261677 a bullet ladder abstains on every rung and never rejects', LADDER_261677, P_FACTS, ALL_BLOCKERS, 'uncertain', [['experience_years:total_years_minimum', 'required', 'unknown'], ['experience_years:total_years_minimum', 'required', 'unknown']]),
    ('h04:BOUND the hedge stops at the next heading, so the second bar still rejects', BOUND_CONTROL, P_FACTS, ALL_BLOCKERS, 'ineligible', [['experience_years:total_years_preferred', 'preferred', 'unmet'], ['experience_years:total_years_minimum', 'required', 'unmet']]),
    ('h05:CONTROL a requirements heading over a bullet with no bar writes no row', 'Requirements:\n- Strong written communication skills.', P_FACTS, ALL_BLOCKERS, 'uncertain', []),
    ("h06:CONTROL a must-have heading never lends its marker to a bare degree bullet", "Must Have:\n- A bachelor's degree.", P_FACTS, ALL_BLOCKERS, 'uncertain', []),
    ("h07:CONTROL a heading never turns an abstaining row unmet", "Requirements:\n- A bachelor's degree or 5 years of experience.", P_FACTS, ALL_BLOCKERS, 'uncertain', [['experience_years:total_years_minimum', 'required', 'unknown']]),
    ('h08:list twin of m0163', 'Nice to have:\n- 10 years of experience.', _corpus('m0163')[2], _corpus('m0163')[3], 'eligible', [['experience_years:total_years_preferred', 'preferred', 'unmet']]),
    ('h09:list twin of m0669', 'Nice to have:\n- 8-10 years of experience.', _corpus('m0669')[2], _corpus('m0669')[3], 'eligible', [['experience_years:range_years_preferred', 'preferred', 'unmet']]),
    ('h10:BOUND a blank line after the bullets ends the heading, so the paragraph bar rejects', 'Nice to have:\n- Go experience\n\nWe require 8 years of experience.', P_FACTS, ALL_BLOCKERS, 'ineligible', [['experience_years:total_years_minimum', 'required', 'unmet']]),
    ('h11:BOUND an unmarked line after bulleted ones ends the heading, so its bar rejects', 'Nice to have:\n- Go experience\nWe require 8 years of experience.', P_FACTS, ALL_BLOCKERS, 'ineligible', [['experience_years:total_years_minimum', 'required', 'unmet']]),
    ('h12:a blank line straight after the heading still governs its bullets', 'Nice to have:\n\n- 5 years of experience.', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:total_years_preferred', 'preferred', 'unmet']]),
    ('h13:BOUND a blank line after a list of plain lines ends the heading, so the paragraph bar rejects', 'Nice to have:\nGo experience\n\nWe require 8 years of experience.', P_FACTS, ALL_BLOCKERS, 'ineligible', [['experience_years:total_years_minimum', 'required', 'unmet']]),
    ('h14:a loose list keeps its heading across the blank line between its bullets', 'Nice to have:\n- Go experience\n\n- 5 years of experience.', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:total_years_preferred', 'preferred', 'unmet']]),
    ("h15:an unmarked OR line under a heading joins its bullets rather than ending the list", "Requirements:\n- A master's degree.\nOR\n- 5 years of experience.", P_FACTS, ALL_BLOCKERS, 'uncertain', [['experience_years:total_years_minimum', 'required', 'unknown']]),
    ('h16:261677 as posted, one line of inline bullets, abstains on every rung and never rejects', LADDER_261677_INLINE, P_FACTS, ALL_BLOCKERS, 'uncertain', [['experience_years:total_years_minimum', 'required', 'unknown'], ['experience_years:total_years_minimum', 'required', 'unknown']]),
    ("h17:CONTROL inline bullets with no OR are separate bars, so the years bar rejects", "Requirements: • 5+ years of experience • A bachelor's degree", P_FACTS, ALL_BLOCKERS, 'ineligible', [['experience_years:total_years_minimum', 'required', 'unmet']]),
    ('h18:BOUND a heading that opens an inline-bulleted line ends the earlier heading, so its bar rejects', 'Nice to have:\nRequirements: • 8 years of experience.', P_FACTS, ALL_BLOCKERS, 'ineligible', [['experience_years:total_years_minimum', 'required', 'unmet']]),
    ('h19:a hedge heading that opens an inline-bulleted line governs the bullet after it', 'Nice to have: • 5 years of experience.', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:total_years_preferred', 'preferred', 'unmet']]),
    ('h20:BOUND a heading item later on the SAME inline-bulleted line ends the hedge, so its bar rejects', 'Nice to have: • Go experience • Requirements: • 8 years of experience.', P_FACTS, ALL_BLOCKERS, 'ineligible', [['experience_years:total_years_minimum', 'required', 'unmet']]),
    ('h21:BOUND a labelled line after plain lines ends the hedge, so its bar rejects', 'Nice to have:\nGo experience\nRequirements: 8 years of experience.', P_FACTS, ALL_BLOCKERS, 'ineligible', [['experience_years:total_years_minimum', 'required', 'unmet']]),
    ('h22:a hedge followed by a section noun is still a hedge heading', 'Preferred Qualifications:\n- 5 years of experience.', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:total_years_preferred', 'preferred', 'unmet']]),
    ('h23:Desired Qualifications hedges its bullets as Preferred does', 'Desired Qualifications:\n- 5 years of experience.', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:total_years_preferred', 'preferred', 'unmet']]),
    ('h24:CONTROL a heading that names required AND preferred is not a hedge', 'Required & Preferred Qualifications:\n- 5 years of experience.', P_FACTS, ALL_BLOCKERS, 'ineligible', [['experience_years:total_years_minimum', 'required', 'unmet']]),
    ('h25:CONTROL Minimum Qualifications is not a hedge', 'Minimum Qualifications:\n- 5 years of experience.', P_FACTS, ALL_BLOCKERS, 'ineligible', [['experience_years:total_years_minimum', 'required', 'unmet']]),
    ('h26:a field label opening a bullet is read through by the hedge', 'Nice to have:\n- Experience: 5 years of experience.', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:total_years_preferred', 'preferred', 'unmet']]),
    ('h27:a field label after an inline bullet is read through by the hedge', 'Nice to have: • Experience: 5 years of experience.', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:total_years_preferred', 'preferred', 'unmet']]),
    ('h28:CONTROL a Required label inside a hedged list keeps its bar', 'Nice to have:\n- Required: 5 years of experience.', P_FACTS, ALL_BLOCKERS, 'ineligible', [['experience_years:total_years_minimum', 'required', 'unmet']]),
    ('h29:BOUND a requirement-section line without a colon ends a plain-line hedge, so its bar rejects', 'Nice to have:\nKubernetes experience\nRequired skills\n5+ years of experience.', P_FACTS, ALL_BLOCKERS, 'ineligible', [['experience_years:total_years_minimum', 'required', 'unmet']]),
    ('h30:BOUND a label-alone line ends a plain-line hedge, so its bar rejects', "Nice to have:\nKubernetes experience\nWhat you'll bring:\n5+ years of experience.", P_FACTS, ALL_BLOCKERS, 'ineligible', [['experience_years:total_years_minimum', 'required', 'unmet']]),
    ('h31:BOUND Who you are ends a plain-line hedge', 'Nice to have:\nKubernetes experience\nWho you are:\n5+ years of experience.', P_FACTS, ALL_BLOCKERS, 'ineligible', [['experience_years:total_years_minimum', 'required', 'unmet']]),
    ('h32:BOUND Must haves ends a plain-line hedge', 'Preferred Qualifications:\nGo experience\nMust haves\n5+ years of experience.', P_FACTS, ALL_BLOCKERS, 'ineligible', [['experience_years:total_years_minimum', 'required', 'unmet']]),
    ("h33:BOUND What we're looking for ends a plain-line hedge", "Bonus:\nGo experience\nWhat we’re looking for\n5+ years of experience.", P_FACTS, ALL_BLOCKERS, 'ineligible', [['experience_years:total_years_minimum', 'required', 'unmet']]),
    ('h34:CONTROL a hedge heading still hedges its own list of plain lines', 'Nice to have:\nKubernetes experience\n5+ years of experience.', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:total_years_preferred', 'preferred', 'unmet']]),
    ('h35:CONTROL a catalogued heading with a colon still bounds a plain-line hedge', 'Nice to have:\nKubernetes experience\nRequirements:\n5+ years of experience.', P_FACTS, ALL_BLOCKERS, 'ineligible', [['experience_years:total_years_minimum', 'required', 'unmet']]),
    ('h36:CONTROL a label-alone line only ends a reach and is never promoted to a heading, so a hedge it holds reaches nothing (the conservative miss)', 'Requirements:\nGo experience\nNice to have skills:\n5+ years of experience.', P_FACTS, ALL_BLOCKERS, 'ineligible', [['experience_years:total_years_minimum', 'required', 'unmet']]),
]

# Each list-form case against the one-line body the engine already reads.
INLINE_TWINS: list[tuple[str, str]] = [
    ("h02", "A master's degree or 5 years of experience."),
    ("h15", "A master's degree or 5 years of experience."),
    ("h19", "Nice to have: 5 years of experience."),
    ("h16", "High School Diploma (or equivalent) AND 4+ years experience* or Associate’s Degree AND 2+ years experience* or Bachelor’s Degree *Relevant sales, clinical, or related experience in medical devices, medtech, healthcare, or life sciences."),
    ("h03", "HS Diploma (or equivalent) AND 4+ years of experience or Associate's degree AND 2+ years of experience or Bachelor's degree"),
    ("h08", _corpus("m0163")[1]),
    ("h09", _corpus("m0669")[1]),
]

# sha256 over repr((scope, body, split_units(body, scope))) for every corpus body and every
# body above, both scopes, in order. Recorded against the UNCHANGED splitter.
SPLIT_UNITS_DIGEST = "4e4105444756c0288c8a701a7585a0431c7c902970130512b846fed2a84a6800"


@pytest.fixture(scope="module")
def catalog(tmp_path_factory):
    return load_rules(tmp_path_factory.mktemp("no-override"))


def _policy(catalog, policy):
    if policy is ALL_BLOCKERS:
        return Policy(families={family.id: "blocker" for family in catalog.families})
    return Policy(families=policy)


def _case(label: str) -> tuple:
    (row,) = [case for case in HEADING_CASES if case[0].startswith(f"{label}:")]
    return row


def _run(catalog, body, facts, policy):
    result = evaluate(body, Facts.model_validate(facts), _policy(catalog, policy), catalog)
    rows = sorted([r.rule_id, r.requiredness, r.disposition] for r in result.requirements)
    return result.verdict, rows


@pytest.mark.parametrize(
    "label,body,facts,policy,verdict,rows",
    HEADING_CASES,
    ids=[case[0] for case in HEADING_CASES],
)
def test_heading_case(catalog, label, body, facts, policy, verdict, rows) -> None:
    assert _run(catalog, body, facts, policy) == (verdict, sorted(rows))


@pytest.mark.parametrize("label,inline", INLINE_TWINS, ids=[t[0] for t in INLINE_TWINS])
def test_the_list_form_agrees_with_its_inline_twin(catalog, label, inline) -> None:
    _label, body, facts, policy, _verdict, _rows = _case(label)
    assert _run(catalog, body, facts, policy) == _run(catalog, inline, facts, policy)


def test_the_inline_twins_of_m0163_and_m0669_are_their_corpus_goldens() -> None:
    """The pair is only a check if the inline side is the reviewed golden, not whatever the
    engine happens to say today."""
    for label, corpus_label in (("h08", "m0163"), ("h09", "m0669")):
        _l, _b, _f, _p, verdict, rows = _case(label)
        assert (verdict, rows) == (_corpus(corpus_label)[4], _corpus(corpus_label)[5])


def test_a_heading_governs_forward_to_the_next_heading_only() -> None:
    units = split_units(BOUND_CONTROL, "sentence")
    assert governing_headings(BOUND_CONTROL, units) == [None, 0, None, 2]


def test_a_bullet_before_any_heading_is_ungoverned() -> None:
    body = "- 5 years of experience.\nNice to have:\n- Go."
    assert governing_headings(body, split_units(body, "sentence")) == [None, None, 1]


def test_split_units_is_byte_identical_over_every_body() -> None:
    running = hashlib.sha256()
    for body in [case[1] for case in CASES] + [case[1] for case in HEADING_CASES]:
        for scope in ("sentence", "clause"):
            running.update(repr((scope, body, split_units(body, scope))).encode("utf-8"))
    assert running.hexdigest() == SPLIT_UNITS_DIGEST


def test_the_surface_is_complete() -> None:
    assert len(HEADING_CASES) == 36
