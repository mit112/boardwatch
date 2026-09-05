"""The lane-body ingest precondition: a body must be the EMPLOYER's own text (D-406).

Every fixture below is an excerpt of a REAL live body. What they defend is the CATALOG's
membership, and that distinction is worth stating because the first version of this docstring
got it wrong. Measured against the live corpus on 2026-09-01: the bare token `Jobright` appears
in 50 bodies, 41 of them postings for the employer *Jobright.ai itself*, and `| LinkedIn` in 13
BlackRock Workday bodies that merely link their own social accounts. Neither string is in the
catalog, and those two negative fixtures are why — they justify EXCLUDING those tokens, not
requiring two of the eight members that ARE catalogued.

The threshold itself is not decided by any live body. The corpus-wide marker-count histogram is
`{0: 139713, 5: 1, 6: 8}` — **nothing anywhere matches exactly one** — so the one-marker guard
below necessarily uses a SYNTHETIC fixture, and says so.
"""

from __future__ import annotations

import json

import pytest

from boardwatch.lanes.quality import (
    FOREIGN_BODY_CATALOG_VERSION,
    MACHINE_SHAPED_DENSITY_THRESHOLD,
    MIN_FOREIGN_MARKERS,
    ForeignBodyText,
    assess_body,
    catalog_fingerprint,
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


def test_the_catalog_is_closed_and_fingerprinted() -> None:
    """Pinned as LITERALS, INCLUDING the membership. An assertion against the shared constant
    would be vacuous, and a version-only pin is nearly as weak: adding or removing a marker no
    test exercises would survive `version == 1` untouched.

    The fingerprint is the executable half — `body_precondition_checks` stores it, so any change
    here re-checks every stored body. Bumping this literal is the acknowledgement that a catalog
    edit invalidates the whole corpus's checks, which is a real cost and must not be silent.
    """
    assert MIN_FOREIGN_MARKERS == 2
    assert FOREIGN_BODY_CATALOG_VERSION == 3
    assert catalog_fingerprint() == "cfdc9b21f466ed57"
    assert foreign_body_markers(" ".join(_EXPECTED_MARKERS)) == tuple(_EXPECTED_MARKERS)


# The catalog spelled out where a diff shows it, so a member added or removed without an
# explicit decision fails the pin above rather than passing unnoticed.
_EXPECTED_MARKERS = (
    "apply on employer site",
    "sign in join now",
    "apply with autofill",
    "improve resume match score",
    "boost your interview chances",
    "h1b sponsor likely",
    "join or sign in to find your next job",
    "agree & join linkedin",
    "internal test job",
    "not a real job",
)


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
    """The two-marker threshold, pinned — and SYNTHETIC, deliberately and unavoidably.

    No live body sits at exactly one marker (histogram `{0: 139713, 5: 1, 6: 8}`), so this
    appends one catalogued phrase to a real employer body. That makes the threshold a
    conservative policy with a guard, NOT a measured discriminator, and nobody reading this
    later should mistake the fixture for a case the corpus actually contains. Lowering the
    threshold to 1 would change no verdict today; the guard exists so that the day a marker
    does show up once inside a long employer JD, the change is a decision rather than an
    accident.
    """
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


# The offending body's own words, as the two blind gate judges reported them on 2026-09-03e.
# Reconstructed rather than quoted from the store: the posting was lost with the pre-reset
# corpus (2026-09-03), and the rebuilt corpus carries ZERO bodies matching either phrase — so
# the marker pair costs nothing today and closes the class for the next one.
INDEED_TEST_JOB = (
    "Responsibilities\n"
    "INDEED INTERNAL TEST JOB. Please do not apply.\n"
    "This is not a real job and no application will be reviewed.\n"
    "Qualifications\n"
    "None. This posting exists to exercise the Indeed job pipeline end to end.\n"
    "Benefits\n"
    "None.\n"
)


def test_an_aggregators_own_test_posting_fails_the_precondition() -> None:
    """T27. A gate judge found this on the 2026-09-03e shortlist: a lead whose entire body says
    it is not a job. It reached the owner's queue with a résumé rendered for it.

    Closed through the foreign-body catalog rather than an Indeed-side filter, because this
    catalog already carries its own drain — `catalog_fingerprint` moves on any marker edit, and
    the sweep re-checks every stored body against the current detector, so the fix reaches
    bodies already banked as well as future ones. A lane-side filter would only ever see new
    ones.
    """
    with pytest.raises(ForeignBodyText) as caught:
        require_employer_body(INDEED_TEST_JOB)
    assert set(caught.value.markers) == {"internal test job", "not a real job"}


def test_a_real_test_automation_jd_is_not_held() -> None:
    """The control, and it is the reason the markers are the two long phrases rather than the
    word "test". Verbatim opening of a live Lever posting for a Test Automation engineer
    (posting 41039 on 2026-09-04), a title family that says "test" in every paragraph."""
    veeva = (
        "Veeva Systems is a mission-driven organization and pioneer in industry cloud, helping "
        "life sciences companies bring therapies to patients faster.\n"
        "The Role\n"
        "As an Associate Software Engineer in Test Automation you will build and maintain the "
        "automated test suites that gate every release. You will write test plans, review test "
        "coverage, and own the internal test infrastructure our engineers depend on.\n"
        "Requirements\n"
        "Experience with automated testing frameworks.\n"
    )
    assert foreign_body_markers(veeva) == ()
    require_employer_body(veeva)  # raises nothing


# ---------------------------------------------------------------------------
# T26(a): the two STRUCTURAL foreign-body classes measured against the live corpus
# (2026-09-04, 61,927 current open bodies). Only ONE of the two ships here -- see below.
# ---------------------------------------------------------------------------

# A realistic ATS page-config JSON blob: the shape of the 98KB Eightfold body two blind gate
# judges found (posting since lost with the pre-reset corpus destroyed 2026-09-03). Built as a
# plausible SSR page-config payload rather than reproduced verbatim, since the original no
# longer exists to quote. Deliberately smaller than 98KB -- the CLASS is what is under test
# (data, not prose), not the byte count.
EIGHTFOLD_PAGE_CONFIG = json.dumps(
    {
        "pageProps": {
            "requisitionId": "REQ-2026-04471",
            "job": {
                "title": "Software Engineer",
                "department": "Engineering",
                "locations": ["Seattle, WA", "Remote - US"],
                "employmentType": "Full-time",
                "postedDate": "2026-08-01",
                "descriptionHtml": "<p>See the employer site for the full description.</p>",
            },
            "company": {"name": "Example Corp", "id": "ex-01827"},
            "seo": {"title": "Software Engineer at Example Corp", "canonical": "https://example.com/jobs/4471"},
            "featureFlags": {"showSalaryBand": False, "enableReferral": True, "showEEOStatement": True},
            "analytics": {"gtmId": "GTM-ABCDEF", "pixelId": "1234567890"},
        },
        "runtimeConfig": {"apiBase": "https://api.example-ats.com/v2", "locale": "en-US"},
    },
    indent=2,
)


def test_a_machine_shaped_page_config_body_is_held() -> None:
    """The FIRST of the two structural classes: the body is data, not prose. Today (before
    T26) this passes every existing control -- it is long, and `json.loads` succeeding says
    nothing to `assess_body`, which only reads prose markers."""
    assert not is_employer_body(EIGHTFOLD_PAGE_CONFIG)
    with pytest.raises(ForeignBodyText) as caught:
        require_employer_body(EIGHTFOLD_PAGE_CONFIG)
    assert "structural:machine_shaped" in caught.value.markers


def test_machine_shaped_density_alone_condemns_a_body_that_is_not_valid_json() -> None:
    """The second half of the machine-shaped test: a body that is NOT parseable JSON (e.g. a
    truncated or concatenated page-config dump) but is still overwhelmingly `{}[]":` punctuation
    is held on density alone. Built by repeating structural punctuation past the measured
    threshold; not a shape any real JD -- prose, however dense with quotes -- has ever reached
    (max observed live density was 0.0495; this fixture clears 0.15)."""
    dense_but_unparseable = ('{"a": "1", "b": [1, 2, 3], "c": {"d": "e"}}, ' * 20) + "trailing junk"
    with pytest.raises(json.JSONDecodeError):
        json.loads(dense_but_unparseable)
    assert not is_employer_body(dense_but_unparseable)
    with pytest.raises(ForeignBodyText) as caught:
        require_employer_body(dense_but_unparseable)
    assert "structural:machine_shaped" in caught.value.markers


def test_machine_shaped_threshold_is_the_measured_value() -> None:
    """Pinned so a future edit to the threshold is a decision, not an accident."""
    assert MACHINE_SHAPED_DENSITY_THRESHOLD == 0.15


# The SECOND structural class the ticket asked for -- "chrome-only": `count_section_markers ==
# 0` and the body clears `MIN_BODY_CHARS` -- is NOT implemented. Measured against the same
# 61,927-body live corpus it holds 2,979 bodies (4.81%), stopping well past the ticket's own
# ~1% ceiling. Inspection of the held bodies (Palantir "Deployment Strategist", Toyota "Vehicle
# Development Engineer", TransPerfect roles, a Korean-language Coupang posting, a Spanish
# SmartRecruiters posting) shows they are REAL job descriptions that simply don't use any of the
# 17 phrases in `_SECTION_MARKERS` -- non-English text, or headings like "The Role" and "What
# We're About" outside the catalog -- not site chrome. Per the ticket's own stop condition, the
# predicate is wrong to ship and wrong to fix by widening `_SECTION_MARKERS` to chase this
# corpus's phrasing (see the T26 session report for the full breakdown by provider).


# ---------------------------------------------------------------------------
# Controls: five REAL job descriptions from five DIFFERENT providers, plus one short real JD
# with exactly one section marker. All excerpted from the live store (2026-09-04), truncated to
# a few hundred characters but each keeping the section-marker hit and enough prose to exercise
# the density check honestly. None of these existed as fixtures before T26.
# ---------------------------------------------------------------------------

# posting 44525, live store, ashby. Modal Labs, "Member of Technical Staff - Systems".
ASHBY_MODAL_JD = (
    "Our team includes creators of popular open-source projects (e.g.,Seaborn,Luigi), academic "
    "researchers, international olympiad medalists, and experienced engineering and product "
    "leaders with decades of experience.\n"
    "The Role:\n"
    "We are looking for strong engineers with experience and interest in designing, building, "
    "and maintaining the novel, high-performance systems that make up our serverless platform.\n"
    "Requirements:\n"
    "5+ years of experience writing high-quality production code\n"
    "Experience building high-performance distributed systems at a large scale\n"
)

# posting 49672, live store, greenhouse. Kargo, "Sales Development Representative".
GREENHOUSE_KARGO_JD = (
    "We care deeply about delivering the best solutions for our customers. As a member of the "
    "Kargo team, you will have the opportunity to develop and deploy tomorrow's hardware & "
    "software solutions and help revolutionize logistics.\n"
    "Responsibilities\n"
    "Work with Account Executives and commercial leadership to drive outbound prospecting "
    "activities, including cold calling, emailing, and communicating our value proposition.\n"
)

# posting 40988, live store, lever. Veeva Systems, "Associate Consultant".
LEVER_VEEVA_JD = (
    "Veeva Systems is a mission-driven organization and pioneer in industry cloud, helping life "
    "sciences companies bring therapies to patients faster. As one of the fastest-growing SaaS "
    "companies in history, we surpassed $3B in revenue in our last fiscal year.\n"
    "The Role\n"
    "As part of this team, the Associate Consultant will assist our life sciences customers by "
    "participating in business process due diligence, requirements definition, solution design "
    "and configuration, and system and training documentation.\n"
)

# posting 59013, live store, smartrecruiters. A Thai back-office role, "Intern".
SMARTRECRUITERS_THAI_JD = (
    "Role & Responsibilities:\n"
    "Prepare authorization letters and other letters related to the BT businesses and propose "
    "for authorized signatures.\n"
    "Sort, file, and maintain hard copy and electronic records of supplier tax invoices to "
    "support compliance with Thai tax regulations.\n"
    "Qualifications:\n"
    "Bachelor's degree in Accounting, Business Administrative or related fields\n"
    "Minimum of 2-3 years of experience in Accounting, or administrative tasks\n"
)

# posting 32915, live store, workable. AMAX Ireland, "Sales Executive (Hardware Solutions)".
WORKABLE_AMAX_JD = (
    "AMAX is seeking a high-performing Sales Executive to drive new business and revenue growth "
    "in the fast-moving world of AI, GPU computing, and high-performance infrastructure.\n"
    "What You Will Do:\n"
    "Own the entire sales cycle, from prospecting to closing, with a focus on bringing in new "
    "customers.\n"
    "Sell GPU-accelerated infrastructure solutions to AI startups, enterprise customers, OEMs, "
    "and cloud/service providers\n"
    "Requirements\n"
    "Proven success in B2B technology sales in related industry.\n"
)

# posting 33437, live store, workday. Cadence Design Systems, "Product Validation Engineer II".
# Short (1077 chars live) and carries EXACTLY one distinct section marker ("Requirements", via
# "Position Requirements:").
WORKDAY_CADENCE_JD_ONE_MARKER = (
    "At Cadence, we hire and develop leaders and innovators who want to make an impact on the "
    "world of technology.\n"
    "This position may cover SPICE: Spectre, SpectreRF, analog mixed-signal simulators product "
    "validation. The engineer will be responsible for developing procedures, test cases, and "
    "designs to test, troubleshooting, and debugging to make sure the products are performing "
    "up to the specifications and upholding software quality standards.\n"
    "Position Requirements:\n"
    "MS in Microelectronics, EE, or relevant.\n"
    "Understanding of semiconductor concepts and Custom IC design.\n"
)

_REAL_JD_CONTROLS = (
    ("ashby", 44525, ASHBY_MODAL_JD),
    ("greenhouse", 49672, GREENHOUSE_KARGO_JD),
    ("lever", 40988, LEVER_VEEVA_JD),
    ("smartrecruiters", 59013, SMARTRECRUITERS_THAI_JD),
    ("workable", 32915, WORKABLE_AMAX_JD),
)


@pytest.mark.parametrize("provider, posting_id, body", _REAL_JD_CONTROLS)
def test_five_real_jds_from_five_providers_pass(provider: str, posting_id: int, body: str) -> None:
    """The control the machine-shaped and (rejected) chrome-only classes must not eat: five
    real, currently-open bodies from five different lane providers, none of them structurally
    foreign."""
    assert is_employer_body(body)
    require_employer_body(body)  # raises nothing
    assert not body.strip().startswith(("{", "["))


def test_a_short_real_jd_with_exactly_one_section_marker_passes() -> None:
    """The one-marker control `meets_body_floor` already exercises, re-checked here against the
    structural classes: a real JD short enough to be borderline, carrying exactly one of the 17
    catalogued section markers, must not be swept up as machine-shaped."""
    from boardwatch.lanes.quality import count_section_markers

    assert count_section_markers(WORKDAY_CADENCE_JD_ONE_MARKER) == 1
    assert is_employer_body(WORKDAY_CADENCE_JD_ONE_MARKER)
    require_employer_body(WORKDAY_CADENCE_JD_ONE_MARKER)  # raises nothing
