"""lanes.quality: the §4.5 body controls. No network anywhere in this file.

Every rejection asserted here names an outcome that is ALREADY in the closed catalog, and the
last test proves the catalog would reject anything else — a control whose verdict cannot be
recorded is a control that reports nothing.
"""

from __future__ import annotations

import pytest

from boardwatch.lanes.outcomes import ACQUISITION_OUTCOMES, AcquisitionTally
from boardwatch.lanes.quality import (
    MIN_BODY_CHARS,
    assess_body,
    count_section_markers,
    count_wall_markers,
    declared_role_line,
    is_login_wall,
    meets_body_floor,
    role_body_mismatch,
)

_REAL_JD = (
    "<h1>Backend Engineer</h1>"
    "<p>Acme runs a small platform team and is hiring one more engineer to work on its "
    "billing services. The role is on site three days a week, and the team owns everything "
    "it ships, from the first design note through to the pager that wakes someone up.</p>"
    "<h2>Responsibilities</h2>"
    "<ul><li>Own a service end to end.</li><li>Review changes.</li>"
    "<li>Carry the pager one week in six.</li><li>Write things down.</li></ul>"
    "<h2>Qualifications</h2>"
    "<ul><li>Reads code you did not write.</li><li>Knows a relational database.</li>"
    "<li>Explains a tradeoff in writing.</li></ul>"
    "<h2>Benefits</h2><p>Health cover from day one and a training budget.</p>"
    # The chrome every real posting page carries. A one-sided wall test rejects this body.
    "<footer><a href='/account'>Sign in</a> or <a href='/new'>Create an account</a></footer>"
)

_LOGIN_WALL = (
    "<div><h2>Sign in to continue</h2>"
    "<p>You must be logged in to view this job. Create an account or log in.</p>"
    "<p>Please enable cookies and try again.</p></div>"
)


def test_a_real_jd_with_sign_in_chrome_is_not_a_login_wall():
    """The two-sided test's whole reason: the one-sided form rejects the corpus."""
    text, rejection = assess_body(_REAL_JD, title="Backend Engineer")
    assert count_wall_markers(text) >= 2  # both markers really are present
    assert count_section_markers(text) >= 1
    assert is_login_wall(text) is False
    assert rejection is None


def test_a_login_wall_is_rejected_as_a_login_wall_and_not_as_a_thin_body():
    _, rejection = assess_body(_LOGIN_WALL, title="Backend Engineer")
    assert rejection is not None
    # Ordering matters: a wall is ALSO below the floor, and reporting it as one would lose the
    # distinction §4.5 exists to draw.
    assert rejection.outcome == "rejected_login_wall"


def test_one_wall_marker_alone_never_fires():
    text = "Sign in\nAbout the role\nWe are hiring."
    assert count_wall_markers(text) == 1
    assert is_login_wall(text) is False


def test_wall_markers_are_word_bounded_so_design_intent_is_not_a_sign_in():
    """'de-sign in-tent' contains 'sign in'. A substring test flags a design JD as a wall."""
    assert count_wall_markers("We value design intent and cosign integrity.") == 0


def test_a_typographic_apostrophe_still_matches_a_section_marker():
    """selectolax decodes entities, so a real JD reaches us with a curly apostrophe."""
    assert count_section_markers("What you’ll do") == 1


def test_the_floor_needs_all_three_of_length_structure_and_lines():
    long_unstructured = "\n".join(["a paragraph of prose with no heading at all."] * 20)
    assert len(long_unstructured) >= MIN_BODY_CHARS
    assert meets_body_floor(long_unstructured) is False  # no section marker

    short_structured = "Responsibilities\n" + "\n".join(f"line {n}" for n in range(10))
    assert len(short_structured) < MIN_BODY_CHARS
    assert meets_body_floor(short_structured) is False  # too short

    few_lines = "Responsibilities. " + "x" * MIN_BODY_CHARS
    assert meets_body_floor(few_lines) is False  # one line


def test_a_thin_body_is_rejected_at_the_quality_gate():
    _, rejection = assess_body("<p>Apply on our website.</p>", title="Backend Engineer")
    assert rejection is not None
    assert rejection.outcome == "rejected_quality_gate"
    assert "below the floor" in rejection.reason


def test_an_empty_extraction_is_reported_as_extracted_empty_not_as_a_quality_failure():
    _, rejection = assess_body("<div><span></span></div>", title="Backend Engineer")
    assert rejection is not None
    assert rejection.outcome == "extracted_empty"


def test_role_mismatch_fires_only_when_both_sides_declare_a_specific_family():
    mobile_body = "iOS Engineer\nResponsibilities\n" + "\n".join(f"line {n}" for n in range(10))
    assert role_body_mismatch("Backend Engineer", mobile_body) is True
    assert role_body_mismatch("iOS Engineer", mobile_body) is False
    # The body's heading resolves to the classifier's fallback: no declaration, no mismatch.
    generic_body = "Acme Corporation\nResponsibilities\n" + "\n".join(f"l{n}" for n in range(10))
    assert role_body_mismatch("Backend Engineer", generic_body) is False
    # ... and symmetrically, an unspecific TITLE cannot disagree with anything.
    assert role_body_mismatch("Prep Cook", mobile_body) is False


def test_a_body_opening_with_prose_declares_no_role():
    """A first line long enough to be a sentence is not a heading, so it classifies nothing."""
    prose = (
        "Acme is a distributed api platform company and we are hiring across the whole "
        "organisation this quarter, in every discipline we run.\nResponsibilities\n"
        + "\n".join(f"line {n}" for n in range(10))
    )
    assert role_body_mismatch("Prep Cook", prose) is False


def test_a_mismatched_body_is_rejected_at_the_quality_gate():
    mismatched = (
        "<h1>iOS Engineer</h1><h2>Responsibilities</h2>"
        "<ul>" + "".join(f"<li>duty number {n} on the weekly team roster</li>" for n in range(16)) + "</ul>"
        "<h2>Qualifications</h2><p>Ships mobile software and keeps the crash rate low.</p>"
    )
    _, rejection = assess_body(mismatched, title="Backend Engineer")
    assert rejection is not None
    assert rejection.outcome == "rejected_quality_gate"
    assert "role family" in rejection.reason


@pytest.mark.parametrize(
    "html,title",
    [
        (_LOGIN_WALL, "Backend Engineer"),
        ("<p>Apply on our website.</p>", "Backend Engineer"),
        ("<div></div>", "Backend Engineer"),
    ],
)
def test_every_rejection_is_recordable_against_the_closed_catalog(html, title):
    """`record()` raises off-catalog, so this is the test that a new outcome name would fail."""
    _, rejection = assess_body(html, title=title)
    assert rejection is not None
    assert rejection.outcome in ACQUISITION_OUTCOMES
    AcquisitionTally().record(rejection.outcome)  # raises UnknownAcquisitionOutcome otherwise


def test_a_body_that_is_all_whitespace_declares_no_role_line():
    assert declared_role_line("   \n\n \n") is None
    assert declared_role_line("\n\n  Backend Engineer  \nrest of the body") == "Backend Engineer"
