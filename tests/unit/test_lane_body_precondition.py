"""The lane-body ingest precondition: a body must be the EMPLOYER's own text (D-406).

Every fixture below is an excerpt of a REAL live body, and the two-sided design is what these
tests actually defend. The naive one-marker forms were measured against the live corpus on
2026-09-01 and both are wrong: the bare token `Jobright` appears in 50 bodies, 41 of them
LinkedIn-lane postings for the employer *Jobright.ai itself*, and `| LinkedIn` appears in 13
BlackRock Workday bodies that merely link their own social accounts. Those two are the
NEGATIVE fixtures here, and they are the reason the guard cannot be simplified to one marker.
"""

from __future__ import annotations

import pytest

from boardwatch.lanes.quality import (
    FOREIGN_BODY_CATALOG_VERSION,
    MIN_FOREIGN_MARKERS,
    ForeignBodyText,
    assess_body,
    foreign_body_markers,
    is_employer_body,
    require_employer_body,
)

# posting 135276, live store, trimmed. jobright's rendered PAGE: title, nav, apply CTA, its
# OWN derived sponsorship label, then the employer text, then jobright's product CTAs.
JOBRIGHT_PAGE = """Software Engineer @ Uber | Jobright.ai
SIGN IN JOIN NOW
Software Engineer jobs in United States
Overview
Company
Apply on Employer Site
APPLY NOW
Uber · 18 hours ago
Software Engineer
Seattle, WA
Marketplace Apps Transportation Software Mobile Apps Ride Sharing
H1B Sponsor Likely
Responsibilities
Design, develop, and test software applications
Solve production issues in product and system reliability
Qualification
Required
Employer will accept a Master's degree in Computer Science
Boost Your Interview Chances
Improve Resume Match Score
Apply With Autofill
"""

# posting 19278, live store, trimmed. A BlackRock Workday body — the employer's own text,
# which happens to link its own social accounts. `| LinkedIn` is IN it.
WORKDAY_WITH_SOCIAL_FOOTER = """About this role
Team Overview
The team is responsible for the Aladdin platform used by institutional clients.
Responsibilities
Partner with clients to deliver portfolio analytics.
Qualifications
Bachelor's degree and 5 years of relevant experience.
For additional information, please visit the Company's website at www.blackrock.com
| Twitter: @blackrock_news | Blog: www.blackrockblog.com | LinkedIn: www.linkedin.com/company/blackrock
"""

# posting 113038, live store, trimmed. boardwatch's OWN LinkedIn lane, employer `Jobright.ai`.
# The employer's own JD, which names the aggregator because the aggregator IS the employer.
LINKEDIN_LANE_JOBRIGHT_EMPLOYER = """About the role
Jobright.ai is building an AI job search copilot. We are hiring a Full Stack Engineer.
Responsibilities
Build and ship product surfaces across the Jobright web application.
Requirements
Strong Python and TypeScript. Experience with distributed systems.
What we offer
Competitive compensation and equity in Jobright.
"""


def test_the_catalog_is_closed_and_versioned() -> None:
    """Pinned as LITERALS. An assertion against the shared constant would be vacuous."""
    assert MIN_FOREIGN_MARKERS == 2
    assert FOREIGN_BODY_CATALOG_VERSION == 1


def test_jobright_page_text_fails_the_precondition() -> None:
    with pytest.raises(ForeignBodyText) as caught:
        require_employer_body(JOBRIGHT_PAGE)
    # The violation is TYPED and carries the markers as DATA. Nothing re-derives this by
    # string-matching the message.
    assert "h1b sponsor likely" in caught.value.markers
    assert "apply on employer site" in caught.value.markers
    assert caught.value.catalog_version == FOREIGN_BODY_CATALOG_VERSION


def test_the_derived_sponsorship_label_is_inside_what_would_be_the_frozen_jd() -> None:
    """The specific forward risk D-406 names: `work_auth` is a blocker family, so an
    `ineligible(work_auth)` quoting this span would present a third party's guess as the
    employer's stated requirement. The label must be IN the body for the risk to be real."""
    assert "H1B Sponsor Likely" in JOBRIGHT_PAGE
    assert not is_employer_body(JOBRIGHT_PAGE)


def test_a_workday_body_that_links_its_own_linkedin_passes() -> None:
    """The 13-row false positive a naive `| LinkedIn` marker would have taken."""
    assert "| LinkedIn" in WORKDAY_WITH_SOCIAL_FOOTER
    assert foreign_body_markers(WORKDAY_WITH_SOCIAL_FOOTER) == ()
    assert is_employer_body(WORKDAY_WITH_SOCIAL_FOOTER)
    require_employer_body(WORKDAY_WITH_SOCIAL_FOOTER)  # raises nothing


def test_a_posting_whose_employer_is_the_aggregator_passes() -> None:
    """The 41-row false positive a bare `Jobright` marker would have taken."""
    assert "Jobright" in LINKEDIN_LANE_JOBRIGHT_EMPLOYER
    assert foreign_body_markers(LINKEDIN_LANE_JOBRIGHT_EMPLOYER) == ()
    assert is_employer_body(LINKEDIN_LANE_JOBRIGHT_EMPLOYER)


def test_one_marker_alone_does_not_condemn_a_body() -> None:
    """Two-sided, for the same reason `is_login_wall` is: a one-sided test eats the corpus."""
    one_marker = WORKDAY_WITH_SOCIAL_FOOTER + "\nApply on Employer Site\n"
    assert len(foreign_body_markers(one_marker)) == 1
    assert is_employer_body(one_marker)


def test_the_markers_survive_a_line_break_and_a_case_change() -> None:
    """Folded before matching: the same phrase arrives inline from one lane and wrapped from
    another, and a marker that only matched one spelling would report a clean body."""
    wrapped = "APPLY ON\n   EMPLOYER SITE\nsign in\njoin now\n"
    assert set(foreign_body_markers(wrapped)) == {"apply on employer site", "sign in join now"}


def test_every_control_above_the_precondition_passes_the_jobright_page() -> None:
    """Why the precondition had to be added rather than a threshold tuned.

    `assess_body` is the pre-existing body gate: login wall, quality floor, role/body
    mismatch. It clears this body — it is long, structured and its heading matches the title.
    If this assertion ever flips, the precondition is no longer the thing standing between
    jobright's page text and the rules, and this file is testing something else.
    """
    _text, rejection = assess_body(
        JOBRIGHT_PAGE.replace("\n", "<br>"), title="Software Engineer"
    )
    assert rejection is None
