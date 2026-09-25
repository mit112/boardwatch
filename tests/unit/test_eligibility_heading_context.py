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
from boardwatch.eligibility.detect import (
    _heading_text,
    _looks_like_header,
    governing_headings,
    split_units,
)
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
# Posting 129842's preferred section verbatim (T181): the citizenship bar is its last plain line,
# and it was the posting's only reason for `ineligible`.
PREFERRED_129842 = (
    'Preferred Qualifications\n'
    'Ph.D.; or M.S. plus 5 years of experience; or B.S. plus 10 years of experience in biochemistry, biophysics, computational biology, structural biology, or a closely related field\n'
    'Deep expertise in computational protein engineering, including AI/ML enabled protein design, structural modeling, or optimization\n'
    'Extensive expertise using protein design tools (e.g. RFdiffusion, ProteinMPNN, AlphaFold, Rosetta based workflows, etc.) for protein-binder and enzyme design\n'
    'Demonstrated ability to reproducibly script and code using Python and/or Bash/Unix shell\n'
    'Experience with scientific computing and data analysis libraries (e.g., NumPy, pandas, SciPy, PyTorch/JAX, matplotlib)\n'
    'Hands on experience installing, maintaining, and operating open source protein modeling and simulation tools\n'
    'Experience with containerized software environments (e.g., Conda, Docker, Apptainer/ Singularity)\n'
    'Strong fundamental understanding of protein biochemistry and common laboratory procedures relevant to protein expression, purification, and characterization\n'
    'Proven ability to work effectively in multidisciplinary team environments\n'
    'Ability to independently troubleshoot technical challenges and rapidly adopt new modeling tools or workflows\n'
    'Strong written and oral communication skills\n'
    'U.S. citizenship with the ability to obtain and maintain required security clearances'
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
    ('h29:129842 a hedge heading reaches a bare citizenship bar', PREFERRED_129842, P_FACTS, ALL_BLOCKERS, 'uncertain', [['experience_years:scoped_years_minimum', 'required', 'unknown'], ['experience_years:total_years_minimum', 'required', 'unknown']]),
    ('h30:CONTROL the same citizenship line under the posting\'s own Key Qualifications heading keeps its bar', 'Key Qualifications\nU.S. citizenship with the ability to obtain and maintain required security clearances', P_FACTS, ALL_BLOCKERS, 'ineligible', [['work_auth:us_citizen_standalone_required', 'required', 'unmet']]),
    ("h31:T215 a hedge after a heading's coordinator is not the heading's, so the bar under it rejects", "Education & Preferred Qualifications\nBachelor's degree in finance\n5+ years of experience in audit\n3+ years of Kubernetes experience preferred", P_FACTS, ALL_BLOCKERS, 'ineligible', [['experience_years:scoped_years_minimum', 'required', 'unmet'], ['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ('h32:T215 CONTROL a hedge before the heading\'s coordinator still hedges', 'Preferred Skills & Experience\n- 5+ years of experience in audit', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ('h33:T215 a heading naming required AND preferred without a colon is not a hedge either', 'Required & Preferred Qualifications\n- 5+ years of experience in audit', P_FACTS, ALL_BLOCKERS, 'ineligible', [['experience_years:scoped_years_minimum', 'required', 'unmet']]),
    ('h34:T215 CONTROL a hedge ending the heading after its own noun hedges the whole list', 'Qualifications/Education Desired\n- 5+ years of experience in audit', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ('h35:T216 an item\'s own must beats its heading\'s hedge', 'PREFERRED:\n- Must have 5 years of experience', P_FACTS, ALL_BLOCKERS, 'ineligible', [['experience_years:total_years_minimum', 'required', 'unmet']]),
    ("h36:T216 an item's own required predicate beats its heading's hedge", "Desired:\n- 20+ years' experience in construction supervision required", P_FACTS, ALL_BLOCKERS, 'ineligible', [['experience_years:scoped_years_minimum', 'required', 'unmet']]),
    ('h37:T216 CONTROL the same heading over a bar with no cue still hedges it', 'PREFERRED:\n- 5 years of experience', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:total_years_preferred', 'preferred', 'unmet']]),
    ('h38:T216 CONTROL required as an adjective is no cue', 'Preferred:\n- 5 years of experience with the required tooling', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ('h39:T216 CONTROL minimum under a hedge heading states the preference\'s threshold, not a mandate', 'Preferred Qualifications:\n- Minimum 5 years of experience in audit', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ('h40:T216 a mandated item is not read through the heading view either', 'Preferred Qualifications:\n- A minimum of 10 years of experience is required', P_FACTS, ALL_BLOCKERS, 'ineligible', [['experience_years:total_years_minimum', 'required', 'unmet']]),
    ('h41:T216 CONTROL an item hedged inline stays hedged', 'Preferred:\n- 5 years of experience with Python a plus', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ('h42:T216 CONTROL a conditional required is no mandate', 'Bonus Points:\n- Ability to obtain security clearance if required.', P_FACTS, ALL_BLOCKERS, 'ineligible', [['clearance:clearable_required', 'required', 'unmet'], ['clearance:generic_clearance_required', 'required', 'unmet']]),
    ('h43:T216 CONTROL to the extent required is no mandate', 'Preferred:\n- 3 years of experience in audit to the extent required by the role', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ("h44:T216 a must inside a relative clause binds the clause's own verb, not the bar", 'Preferred:\n- 5 years of experience in audit for candidates who must travel to client sites', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ('h45:T216 should it be required is a conditional, no mandate', 'Preferred:\n- 5 years of experience in audit should it be required by the role', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ('h46:T216 should ... be required is a conditional whatever its subject', 'Preferred:\n- 5 years of experience in audit should travel be required', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ("h47:T216 a required reached across a to infinitive is not the bar's predicate", 'Preferred:\n- 5 years of experience in audit with a willingness to travel required', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ("h48:T216 CONTROL is required as the bar's own predicate beats the heading's hedge", 'Preferred:\n- 5 years of experience in audit is required', P_FACTS, ALL_BLOCKERS, 'ineligible', [['experience_years:scoped_years_minimum', 'required', 'unmet']]),
    ("h49:T216 CONTROL a sentence-final required beats the heading's hedge", 'Preferred:\n- 5 years of experience in audit required.', P_FACTS, ALL_BLOCKERS, 'ineligible', [['experience_years:scoped_years_minimum', 'required', 'unmet']]),
    ("h50:T216 CONTROL is a must as the bar's own predicate beats the heading's hedge", 'Preferred:\n- 5 years of experience in audit is a must', P_FACTS, ALL_BLOCKERS, 'ineligible', [['experience_years:scoped_years_minimum', 'required', 'unmet']]),
    ("h51:T216 a required reached across a where clause is not the bar's predicate", 'Preferred:\n- 5 years of audit experience in a firm where overtime is required', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ("h52:T216 a required reached across for candidates is not the bar's predicate", 'Preferred:\n- 5 years of experience in audit for candidates required to travel', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ("h53:T216 CONTROL a for phrase that names no person keeps the bar's predicate", 'Preferred:\n- 5 years of experience in audit for this role is required', P_FACTS, ALL_BLOCKERS, 'ineligible', [['experience_years:scoped_years_minimum', 'required', 'unmet']]),
    ("h54:T216 a required before the bar is another subject's predicate, not the bar's", 'Preferred:\n- Travel is required with 5 years of experience in audit', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ("h55:T216 CONTROL an item opening with its own subject's must beats the heading's hedge", 'Preferred Qualifications:\n- Candidates must have 5 years of experience in audit', P_FACTS, ALL_BLOCKERS, 'ineligible', [['experience_years:scoped_years_minimum', 'required', 'unmet']]),
    ("h56:T216 CONTROL an item opening must be beats the heading's hedge", 'Preferred Qualifications:\n- Must be able to obtain a Public Trust Clearance', P_FACTS, ALL_BLOCKERS, 'ineligible', [['clearance:clearable_leveled_required', 'required', 'unmet'], ['clearance:clearable_required', 'required', 'unmet']]),
    ("h57:T215 the hyphenated nice-to-have before the heading's coordinator hedges the whole list", 'Nice-to-Have / Bonus\n- 5+ years of experience in audit', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ('h58:T215 CONTROL a hedge before a coordinator naming requirements still hedges', 'Bonus / Requirements\n- 5+ years of experience in audit', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ('h59:the hyphenated nice-to-have heading carries a total bar as its preference', 'Nice-to-have:\n- 5+ years of experience', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:total_years_preferred', 'preferred', 'unmet']]),
    ('h60:the hyphenated nice-to-have hedges a degree bar as the spaced form does', 'Qualifications:\n- PhD degree nice-to-have', P_FACTS, ALL_BLOCKERS, 'eligible', [['degree:degree_preferred', 'preferred', 'met']]),
    ('h61:the hyphenated nice-to-have hedges a clearance bar as the spaced form does', 'Qualifications:\n- Security clearance nice-to-have', P_FACTS, ALL_BLOCKERS, 'eligible', [['clearance:clearance_preferred', 'preferred', 'unmet']]),
    ('h62:the hyphenated nice-to-have hedges a range bar as the spaced form does', 'Qualifications:\n- 3-5 years of experience nice-to-have', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:range_years_preferred', 'preferred', 'unmet']]),
    ('h63:the hyphenated nice-to-have hedges an or-equivalent degree bar as the spaced form does', 'Qualifications:\n- Bachelor\'s degree or equivalent experience nice-to-have', P_FACTS, ALL_BLOCKERS, 'eligible', [['degree:bachelor_or_equivalent_preferred', 'preferred', 'met']]),
    ('h64:T219 a hedge before an and-coordinated colon heading governs the whole heading', 'PREFERRED SKILLS AND EXPERIENCE:\n- 5+ years of experience in audit', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ('h65:T219 a hedge before an ampersand-coordinated colon heading governs the whole heading', 'Preferred Skills & Experience:\n- 5+ years of experience in audit', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ('h66:T219 a hedge before a slash-coordinated colon heading governs the whole heading', 'Preferred Skills/Experience:\n- 3-5 years of experience', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:range_years_preferred', 'preferred', 'unmet']]),
    ('h67:T219 a coordinated hedge heading carries a total bar as its preference', 'PREFERRED QUALIFICATIONS AND SKILLS:\n- 5 years of experience.', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:total_years_preferred', 'preferred', 'unmet']]),
    ('h68:T219 minimum under a coordinated hedge heading states the preference\'s threshold, as under Preferred Qualifications', 'PREFERRED SKILLS AND EXPERIENCE:\n- Minimum 5 years of experience in audit', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ('h69:T219 CONTROL a coordinated hedge heading over an item\'s own must keeps the bar', 'Preferred Skills & Experience:\n- Must have 5+ years of experience in audit', P_FACTS, ALL_BLOCKERS, 'ineligible', [['experience_years:scoped_years_minimum', 'required', 'unmet']]),
    ('h70:T219 CONTROL a preference word before no section noun is no hedge heading', 'Preferred Candidates Must Have:\n- 5+ years of experience in audit', P_FACTS, ALL_BLOCKERS, 'ineligible', [['experience_years:scoped_years_minimum', 'required', 'unmet']]),
    ('h71:T219 CONTROL a coordinated part that names a requirement is no hedge heading', 'Preferred Qualifications & Required Skills:\n- 5+ years of experience in audit', P_FACTS, ALL_BLOCKERS, 'ineligible', [['experience_years:scoped_years_minimum', 'required', 'unmet']]),
    ('h72:T219 CONTROL a coordinated required heading is no hedge heading', 'REQUIRED SKILLS AND EXPERIENCE:\n- 5+ years of experience in audit', P_FACTS, ALL_BLOCKERS, 'ineligible', [['experience_years:scoped_years_minimum', 'required', 'unmet']]),
    ("h73:T245 an item-final required past an and beats the heading's hedge (pv 156487)", 'DESIRED SKILLS AND EXPERIENCE\nMinimum 5 years of experience in Warehouse and Logistics required.', P_FACTS, ALL_BLOCKERS, 'ineligible', [['experience_years:scoped_years_minimum', 'required', 'unmet']]),
    ("h74:T245 an item-final required past a comma beats the heading's hedge (pv 152199)", 'DESIRED SKILLS AND EXPERIENCE\n3 years Lean Continuous Improvement experience, required. Lead kaizen events, conduct time studies.', P_FACTS, ALL_BLOCKERS, 'uncertain', [['experience_years:scoped_years_minimum', 'required', 'unknown']]),
    ("h75:T245 an item-final required past an and/or and a comma beats the heading's hedge (pv 156503)", 'DESIRED SKILLS AND EXPERIENCE\n3 years’ experience as a Quality Assistant or similar role in a fast-paced manufacturing and/or lab environment, required', P_FACTS, ALL_BLOCKERS, 'uncertain', [['experience_years:scoped_years_minimum', 'required', 'unknown']]),
    ("h76:T245 an item-final required past an and/or beats the heading's hedge (pv 156568)", 'DESIRED SKILLS AND EXPERIENCE\n5+ years’ experience designing or engineering prefabricated wood trusses and/or engineered wood products (EWP) required', P_FACTS, ALL_BLOCKERS, 'ineligible', [['experience_years:scoped_years_minimum', 'required', 'unmet']]),
    ("h77:T245 an item-final (required) past an and beats the heading's hedge (pv 32584)", 'Preferred Qualifications:\n- 12-15 years of general knowledge in EFT settlement and transaction processing (required)', P_FACTS, ALL_BLOCKERS, 'ineligible', [['experience_years:domain_range_years_minimum', 'required', 'unmet']]),
    ('h78:T245 CONTROL a required past a hedge and a second credential binds nothing to the first', "Preferred Qualifications:\n- Bachelor's degree preferred, high school diploma or equivalent required.", P_FACTS, ALL_BLOCKERS, 'eligible', [['degree:degree_preferred', 'preferred', 'met']]),
    ('h79:T245 CONTROL a required past a second credential binds nothing to the first', "Preferred Qualifications:\n- Bachelor's degree, high school diploma or equivalent required.", P_FACTS, ALL_BLOCKERS, 'uncertain', []),
    ("h80:T245 CONTROL a required past a second duration is that bar's, not the first's", 'Preferred Qualifications:\n- 5 years of experience in audit, 2 years of SQL required.', P_FACTS, ALL_BLOCKERS, 'uncertain', [['experience_years:domain_years_minimum', 'required', 'unknown'], ['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ('h81:T245 CONTROL a required past an inline hedge binds nothing to the bar', 'Preferred Qualifications:\n- 5 years of experience in audit, Python preferred, SQL required.', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ('h82:T245 CONTROL a negated required past the clause is no mandate', 'Preferred Qualifications:\n- 5 years of experience in audit, not required.', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ('h83:T245 CONTROL a required that does not end the item is no item-final mandate', 'Preferred Qualifications:\n- 5 years of experience in audit, required for the senior level.', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ("h84:T245 CONTROL a required past a semicolon is the next item's", 'Preferred Qualifications:\n- 5 years of experience in audit; SOX required.', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ('h85:T245 CONTROL an item-final required past a contrast is no mandate on the bar', 'Preferred Qualifications:\n- 5 years of experience in audit, but SOX is required.', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ('h86:T245 CONTROL a required past a relative clause binds that clause, not the bar', 'Preferred Qualifications:\n- 5 years of experience in audit, with candidates who travel required.', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ('h87:T245 CONTROL an item-final conditional required is no mandate', 'Preferred Qualifications:\n- 5 years of experience in audit and travel if required.', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ('h88:T245 CONTROL will not be considered is no bar predicate (pv 326450, not built)', 'Desired Skills & Experience\n5+ years of Amazon marketing experience with demonstrated ownership of both demand generation AND on-site content/SEO — candidates with expertise in only one area will not be considered.', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ('h89:T245 CONTROL a required past a credential is the credential\'s, not the bar\'s', 'Preferred Qualifications:\n- 5 years of experience in audit, CPA license required.', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ('h90:T245 CONTROL an item-final should ... be required is a conditional, no mandate', 'Preferred Qualifications:\n- 5 years of experience in audit, should travel be required.', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ('h91:T245 CONTROL a required past a degree is the degree\'s, not the bar\'s', 'Preferred Qualifications:\n- 5 years of experience in audit, bachelor\'s degree required.', P_FACTS, ALL_BLOCKERS, 'eligible', [['degree:bachelor_required', 'required', 'met'], ['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ("h92:T245 CONTROL a must inside an aside of its own binds the aside's noun (pv 140845)", 'Preferred Qualifications:\n- 10+ years of strong automation experience with test case development (C/C++, Python a must).', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ("h93:T245 CONTROL a required past a second experience head is that head's (pv 346998)", 'Nice to haves\n- 4+ years of product management experience with a clear track record of shipping meaningful consumer-facing products, and prior crypto, Web3, trading, gaming or banking experience is required', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ("h94:T245 CONTROL a required past a sentence break the splitter missed is the next sentence's (pv 318063)", 'Preferred Qualifications\n5+ years of people-management experience, including leading managers and/or operational teams.Proven leadership in building large teams.Excellent negotiation is required.', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ('h95:T246 a Title-case heading with a lowercase and is a heading, and its hedge governs its list', 'Preferred Skills and Experience\n- 5+ years of experience in audit', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ('h96:T246 the same heading with a colon', 'Desired Skills and Experience:\n- 5+ years of experience in audit', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ('h97:T246 an ALL-CAPS heading with a lowercase and ends nothing it should not, and the hedge heading after it governs', 'DUTIES and RESPONSIBILITIES:\n- Lead audits\nPreferred Skills and Experience\n- 5+ years of experience in audit', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ('h98:T246 a hedge before technical and professional nouns governs the whole heading', 'Preferred Technical and Professional Experience\n- 5+ years of experience in audit', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ('h99:T246 a hedge before education and experience governs the whole heading', 'Preferred Education and Experience\n- 5+ years of experience in audit', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ('h100:T246 a new hedge heading keeps the hedge an earlier one gave its plain lines (pv 352300)', "Preferred Skills\nExperience with Python.\nPreferred Education and Experience\nMaster's degree preferred.\n12+ years of digital design verification experience.", P_FACTS, ALL_BLOCKERS, 'eligible', [['degree:degree_preferred', 'preferred', 'met'], ['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ('h101:T246 a single education noun after the hedge is a hedge heading too', 'Preferred Education:\n- 5+ years of experience in audit', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ('h102:T246 CONTROL a required technical and professional heading is no hedge heading', 'Required Technical and Professional Expertise\n- 5+ years of experience in audit', P_FACTS, ALL_BLOCKERS, 'ineligible', [['experience_years:scoped_years_minimum', 'required', 'unmet']]),
    ("h103:T246 CONTROL a hedge after the new heading's coordinator is not the heading's (T215)", 'Education and Preferred Qualifications\n- 5+ years of experience in audit', P_FACTS, ALL_BLOCKERS, 'ineligible', [['experience_years:scoped_years_minimum', 'required', 'unmet']]),
    ('h104:T246 CONTROL a sentence-case heading is still no heading (not built)', 'Preferred skills and experience\n- 5+ years of experience in audit', P_FACTS, ALL_BLOCKERS, 'ineligible', [['experience_years:scoped_years_minimum', 'required', 'unmet']]),
    ('h105:T246 CONTROL a Title-case content line with a lowercase and is no heading, so the hedge still reaches past it', 'Preferred Qualifications:\nPython and SQL\n5+ years of experience in audit', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ('h106:T246 CONTROL a bulleted Title-case line with a lowercase and is no heading', 'Preferred Qualifications:\n- Python and SQL\n- 5+ years of experience in audit', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ('h107:T241a a level label does not hide its hedge heading (pv 245092)', 'Preferred Qualifications:\nSpecialist: 2 - 5 years of relevant work experience.', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:range_years_preferred', 'preferred', 'unmet']]),
    ('h108:T241a a modified field label is read through as a field label is', 'Preferred Qualifications:\n- Extensive Experience: 12+ years of professional software development experience', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ('h109:T241a a numbered level label is read through', 'Desired:\n- Level 3: 5+ years of experience in design of vehicle Avionics systems', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ('h110:T241a a coordinated field label is read through', 'Preferred Qualifications:\n- Purchasing / Supply Planning Expertise: 5+ years of hands-on purchasing experience', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ('h111:T241a a hedged label is read through', 'Preferred Qualifications:\n- Desired Experience: Minimum 8 years of experience related to the labor category', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:total_years_preferred', 'preferred', 'unmet']]),
    ('h112:T241a CONTROL a label naming a requirement keeps its bar', 'Preferred Qualifications:\n- Experience requirement: Minimum 5 years in SaaS solution environment', P_FACTS, ALL_BLOCKERS, 'ineligible', [['experience_years:domain_years_minimum', 'required', 'unmet']]),
    ('h113:T241a CONTROL a notice label keeps its bar', 'Preferred Qualifications:\n- Note: 8 years of industrial maintenance experience', P_FACTS, ALL_BLOCKERS, 'ineligible', [['experience_years:scoped_years_minimum', 'required', 'unmet']]),
    ('h114:T241a CONTROL a non-negotiable label keeps its bar', 'Preferred Qualifications:\n- Non-negotiable: 5 years of experience in audit', P_FACTS, ALL_BLOCKERS, 'ineligible', [['experience_years:scoped_years_minimum', 'required', 'unmet']]),
    ('h115:T241a CONTROL a label that opens on a number is not read through', 'Preferred Qualifications:\n- 3 year(s): 2-4 years of experience in full stack development', P_FACTS, ALL_BLOCKERS, 'uncertain', [['experience_years:scoped_range_years_minimum', 'required', 'unknown']]),
    ('h116:T241a CONTROL a labelled item under a requirements heading keeps its bar', 'Requirements:\n- Specialist: 2 - 5 years of relevant work experience.', P_FACTS, ALL_BLOCKERS, 'uncertain', [['experience_years:range_years_minimum', 'required', 'unknown']]),
    ("h117:T241a CONTROL a required label inside the label keeps the item's bar", "Preferred Qualifications:\n- Education (required): Bachelor's degree or equivalent.", P_FACTS, ALL_BLOCKERS, 'eligible', [['degree:bachelor_or_equivalent_required', 'required', 'met'], ['degree:bachelor_required', 'required', 'met']]),
    ("h118:T241b CONTROL a hedge ending a flattened line still hedges the next line's bar (pv 130715, 1 store posting, not built)", 'Qualifications\nBachelor’s degree or equivalent preferred 3 - 5 years of experience supporting asset management distribution.', P_FACTS, ALL_BLOCKERS, 'eligible', [['degree:bachelor_or_equivalent_preferred', 'preferred', 'met'], ['experience_years:scoped_years_preferred', 'preferred', 'unmet']]),
    ('h119:T246 CONTROL a verb-initial skill line with a lowercase and is no heading (Codex r1)', 'Preferred Skills:\nDesign and Build Pipelines\n5 years of experience.', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:total_years_preferred', 'preferred', 'unmet']]),
    ('h120:T246 CONTROL develop and maintain is a skill line, not a heading', 'Preferred Skills:\nDevelop and Maintain Services\n5 years of experience.', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:total_years_preferred', 'preferred', 'unmet']]),
    ('h121:T246 CONTROL plan and execute is a skill line, not a heading', 'Preferred Skills:\nPlan and Execute Campaigns\n5 years of experience.', P_FACTS, ALL_BLOCKERS, 'eligible', [['experience_years:total_years_preferred', 'preferred', 'unmet']]),
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
SPLIT_UNITS_DIGEST = "d42d78a1c65047407010941ef8bbe37b0b88564b5da046658c64baf2722f4510"


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


@pytest.mark.parametrize(
    ("line", "header"),
    [
        ("Preferred Skills and Experience", True),
        ("DUTIES and RESPONSIBILITIES:", True),
        ("Compensation and Benefits", True),
        ("Roles and Responsibilities", True),
        ("Design and Build Pipelines", False),
        ("Develop and Maintain Services", False),
        ("Preferred skills and experience", False),
        ("Experience with Python and SQL", False),
        ("Skills and experience", False),
    ],
)
def test_a_lowercase_and_between_capitalised_words_is_glue(line: str, header: bool) -> None:
    """T246: `and` is not a significant word to the Title-case test, as `&` is not."""
    assert _looks_like_header(line) is header


@pytest.mark.parametrize(
    "noun",
    ["Experiences", "Education", "Expertise", "Background", "Certifications", "Capabilities",
     "Aptitudes", "Training", "Technical Expertise", "Professional and Technical Experience"],
)
def test_each_section_noun_a_new_heading_names_is_hedged(noun: str) -> None:
    """T246: every noun the newly detected hedge headings name reads as the hedge alone."""
    assert _heading_text(f"Preferred Skills and {noun}:") == "Preferred:"


def test_an_open_noun_after_the_hedge_is_no_hedge_heading() -> None:
    assert _heading_text("Preferred Skills and Tools:") == "Preferred Skills and Tools:"


def test_the_surface_is_complete() -> None:
    assert len(HEADING_CASES) == 121
