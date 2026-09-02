"""Authored `schema.org/JobPosting` pages for the JSON-LD resolver lane's suite.

**SYNTHETIC TEXT, MEASURED SHAPE.** No employer's copy, name or URL is carried over from any
recorded page. What IS carried over, verbatim, is the STRUCTURE each vendor was measured
serving on 2026-09-01 -- because the structure is what the lane has to survive, and every one of
these fixtures exists to reproduce a specific measured trap rather than a happy path:

* `HIREOLOGY_PAGE` -- `identifier.value` is an INTEGER and is **off by one from its own URL**
  (measured: the page at `.../2855936/description` carries `identifier.value == 2855935`).
* `CAREERPLUG_PAGE` -- the `description` is HTML-ESCAPED HTML inside the JSON string. Measured:
  151 `&lt;` and ZERO real tags.
* `ICIMS_PAGE` -- the JD is SPLIT across `description`, `responsibilities` and `qualifications`,
  and four sibling properties carry the literal string `UNAVAILABLE`.
* `JAZZHR_PAGE` -- no `identifier` at all (a `uniqueJobCode` instead), and a `url` property.
* `BREEZY_PAGE` -- no `identifier`, and a `url` property that DIFFERS from the page it was served
  on (measured: `?source=GoogleJobs` appended).
* `NO_ORG_PAGE` -- `hiringOrganization` absent entirely (measured on one vendor).
* `STRING_ORG_PAGE` -- `hiringOrganization` as a BARE STRING and `jobLocation` as a LIST.

DRIFT. `REVIEW_BY` is the date somebody must re-confirm these shapes against the live vendors.
There is no automatic refresh and the fixture cannot notice the vendors moving; the drain is a
dated edit to `REVIEW_BY` with the reason recorded beside it. R13's pinned-fixture-dir rule does
not reach a lane -- it keys on registered PROVIDERS -- so this is the only freshness claim these
fixtures make, and `test_the_authored_shapes_are_still_in_review` is what makes it fail rather
than expire quietly.

`CATALOG_DIGEST` is the second half of drift protection and it guards the opposite direction:
these fixtures pin what a VENDOR sends, and the digest pins what the LANE ADMITS. A vendor added,
removed or re-patterned changes it, so the catalog cannot grow a host whose posture nobody
recorded without a reviewer editing a literal in this file.
"""

from __future__ import annotations

import json
from datetime import date

# Re-confirm the seven shapes above against the live vendors by this date.
REVIEW_BY = date(2026, 12, 15)

# sha256 over the shipped vendor catalog, as `test_the_vendor_catalog_is_pinned` recomputes it.
# A LITERAL, never a recomputation of the value under test: an assertion that recomputes the
# thing it is checking passes against any catalog, which is the vacuity this repo has been bitten
# by before. Editing this line is the reviewer step for admitting a host.
CATALOG_DIGEST = "cba1969b33f55b761b07f5f5d272b6d7022f3e2381cc3d5909af12b6e8c317ac"

# A real JD needs to clear `lanes.quality`'s floor: >=500 chars, >=1 section marker, >=8 lines.
# Authored once and reused, so a fixture that fails the floor fails for the reason under test
# rather than for being short.
_JD_BODY = (
    "<h2>About the role</h2>"
    "<p>We are hiring an engineer to build and maintain internal tooling. "
    "You will work across the stack and own features end to end.</p>"
    "<h2>Responsibilities</h2>"
    "<ul>"
    "<li>Design, build and ship services used by the whole company.</li>"
    "<li>Review code and raise the quality bar for the team around you.</li>"
    "<li>Instrument what you build so its failures are visible.</li>"
    "<li>Write the documentation somebody joining next quarter will need.</li>"
    "</ul>"
    "<h2>Requirements</h2>"
    "<ul>"
    "<li>Comfortable in at least one general purpose programming language.</li>"
    "<li>Able to reason about correctness before reaching for a debugger.</li>"
    "<li>Willing to work in an existing codebase rather than around it.</li>"
    "</ul>"
    "<h2>Benefits</h2>"
    "<p>Health cover, paid time off and a hardware budget.</p>"
)


def page(posting: dict[str, object], *, extra_blocks: tuple[str, ...] = ()) -> str:
    """A posting page carrying `posting` as its `application/ld+json` JobPosting block.

    The block sits among ordinary page chrome and, where a test asks for them, sibling LD blocks
    -- because a real page carries several and the lane has to find the JobPosting among them
    rather than reading the first one.
    """
    blocks = "".join(f'<script type="application/ld+json">{raw}</script>' for raw in extra_blocks)
    return (
        "<!DOCTYPE html><html><head><title>A posting</title>"
        f"{blocks}"
        '<script type="application/ld+json">'
        f"{json.dumps(posting)}"
        "</script></head><body><p>Page chrome the lane must not read as a JD.</p></body></html>"
    )


# A sibling block of a type the lane must skip. Measured shape: real pages carry these beside the
# JobPosting, and one of them being unparseable must not cost the page.
BREADCRUMB_BLOCK = json.dumps(
    {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": []}
)
BROKEN_BLOCK = "{ this is not json"


HIREOLOGY_URL = "https://careers.hireology.com/exampletenant/2855936/description"
HIREOLOGY_POSTING: dict[str, object] = {
    "@context": "http://schema.org",
    "@type": "JobPosting",
    "title": "Associate Software Engineer",
    "datePosted": "2026-08-26",
    "employmentType": "FULL_TIME",
    # THE TRAP: an integer, and one less than the id in the URL above.
    "identifier": {"@type": "PropertyValue", "name": "Example", "value": 2855935},
    "hiringOrganization": {"@type": "Organization", "name": "Example Tooling Co"},
    "jobLocation": {
        "@type": "Place",
        "address": {
            "@type": "PostalAddress",
            "addressLocality": "Springfield",
            "addressRegion": "IL",
            "addressCountry": "US",
        },
    },
    "description": _JD_BODY,
}
HIREOLOGY_PAGE = page(HIREOLOGY_POSTING, extra_blocks=(BREADCRUMB_BLOCK,))


CAREERPLUG_URL = "https://example-partners-llc.careerplug.com/jobs/3570902"
# THE TRAP: the JD arrives HTML-escaped inside the JSON string, so one extraction pass yields the
# markup as text. Built by escaping the same body every other fixture carries raw, which is
# exactly what the vendor was measured doing.
CAREERPLUG_POSTING: dict[str, object] = {
    "@context": "https://schema.org",
    "@type": "JobPosting",
    "title": "Software Developer",
    "datePosted": "2026-08-28T17:41:41+00:00",
    "identifier": {"@type": "PropertyValue", "name": "Example Job ID", "value": "3570902"},
    "hiringOrganization": {"@type": "Organization", "name": "Example Partners LLC"},
    "jobLocation": {
        "@type": "Place",
        "address": {
            "@type": "PostalAddress",
            "addressLocality": "Saint Louis",
            "addressRegion": "MO",
            "addressCountry": "US",
        },
    },
    "description": (
        _JD_BODY.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    ),
}
CAREERPLUG_PAGE = page(CAREERPLUG_POSTING)


JAZZHR_URL = "https://exampletenant.applytojob.com/apply/AbC123xyz/Junior-Product-Engineer"
# The SECOND measured shape for this vendor: the same reference with no `/apply` segment.
JAZZHR_SHORT_URL = "https://exampletenant.applytojob.com/AbC123xyz/Junior-Product-Engineer"
JAZZHR_POSTING: dict[str, object] = {
    "@context": "http://schema.org/",
    "@type": "JobPosting",
    "title": "Junior Product Engineer",
    "datePosted": "2026-08-28",
    "employmentType": "FULL_TIME",
    # THE TRAP: no `identifier` at all. This vendor carries its own code under another name.
    "uniqueJobCode": "job_20260819122304_EXAMPLE",
    "url": JAZZHR_URL,
    "hiringOrganization": {"@type": "Organization", "name": "Example Security Inc"},
    "jobLocation": {
        "@type": "Place",
        "address": {
            "@type": "PostalAddress",
            "addressLocality": "Alpharetta",
            "addressRegion": "GA",
        },
    },
    "description": _JD_BODY,
}
JAZZHR_PAGE = page(JAZZHR_POSTING)


BREEZY_URL = "https://example-improvements.breezy.hr/p/824adfc228b2-full-stack-developer"
# The one ACTIVE record of this vendor in the two public lists carries the apply suffix.
BREEZY_APPLY_URL = "https://example-improvements.breezy.hr/p/824adfc228b2/apply"
BREEZY_POSTING: dict[str, object] = {
    "@context": "https://schema.org/",
    "@type": "JobPosting",
    "title": "Full-Stack Developer",
    "datePosted": "2025-01-28",
    "employmentType": "FULL_TIME",
    # THE TRAP: the vendor's own `url` differs from the page it was served on.
    "url": f"{BREEZY_URL}?source=GoogleJobs",
    "hiringOrganization": {
        "@type": "Organization",
        "name": "Example Home Improvements",
        "logo": None,
    },
    "jobLocation": {
        "@type": "Place",
        "address": {
            "@type": "PostalAddress",
            "addressCountry": "US",
            "addressRegion": "MO",
            "addressLocality": "Wentzville",
        },
    },
    "description": _JD_BODY,
}
BREEZY_PAGE = page(BREEZY_POSTING)


ICIMS_URL = "https://careers.garmin.com/jobs/19732?icims=1"
ICIMS_HOME_URL = "https://careers.garmin.com/careers-home/jobs/15924"
# THE TRAP: the JD is split three ways, and four sibling properties carry a sentinel string.
ICIMS_DESCRIPTION = (
    "<p><strong>Overview</strong></p>"
    "<p>We are seeking a full-time engineer for our aviation web backend team.</p>"
)
ICIMS_RESPONSIBILITIES = (
    "<p><strong>Essential Functions</strong></p>"
    "<ul>"
    "<li>Design and develop new product and application software.</li>"
    "<li>Maintain the services already in production.</li>"
    "<li>Participate in design and code reviews across the team.</li>"
    "<li>Support the release process for the components you own.</li>"
    "</ul>"
)
ICIMS_QUALIFICATIONS = (
    "<p><strong>Basic Qualifications</strong></p>"
    "<ul>"
    "<li>Bachelor's degree in computer science or a related field.</li>"
    "<li>Demonstrated experience writing production software.</li>"
    "<li>Excellent written and verbal communication.</li>"
    "<li>Able to prioritise and multi-task in a fast paced environment.</li>"
    "</ul>"
)
ICIMS_POSTING: dict[str, object] = {
    "@context": "http://schema.org",
    "@type": "JobPosting",
    "title": "Software Engineer 1 - Aviation Backend Web",
    "datePosted": "2026-08-28T20:50:00+0000",
    "employmentType": "FULL_TIME",
    "educationRequirements": "UNAVAILABLE",
    "industry": "UNAVAILABLE",
    "skills": "UNAVAILABLE",
    "workHours": "UNAVAILABLE",
    "jobBenefits": "",
    "url": ICIMS_URL,
    "hiringOrganization": {"@type": "Organization", "name": "Example Instruments, Inc."},
    "jobLocation": {
        "@type": "Place",
        "address": {
            "@type": "PostalAddress",
            "addressLocality": "Chanhassen",
            "addressRegion": "Minnesota",
            "addressCountry": "United States",
        },
    },
    "description": ICIMS_DESCRIPTION,
    "responsibilities": ICIMS_RESPONSIBILITIES,
    "qualifications": ICIMS_QUALIFICATIONS,
}
ICIMS_PAGE = page(ICIMS_POSTING)


# The SAME vendor's sentinel convention, applied to a property this lane actually READS.
#
# This fixture exists because a mutation campaign proved the sentinel guard VACUOUS without it.
# The measured page writes the literal `UNAVAILABLE` into four properties the lane ignores
# (`skills`, `industry`, `workHours`, `educationRequirements`), so deleting the sentinel filter
# changed nothing that any fixture could see -- the guard passed against the broken version. A
# control can only catch what its fixture's FACT VALUES contain, and this is the missing fact: the
# same page with nothing to say under `qualifications`, which is where that convention lands next.
SENTINEL_BODY_POSTING: dict[str, object] = {**ICIMS_POSTING, "qualifications": "UNAVAILABLE"}


# `hiringOrganization` ABSENT -- measured on one vendor, and the reason the lane needs a fallback
# that is not a placeholder.
NO_ORG_POSTING: dict[str, object] = {
    "@context": "https://schema.org/",
    "@type": "JobPosting",
    "title": "Software Engineer",
    "datePosted": "2026-08-25",
    "description": _JD_BODY,
}
NO_ORG_PAGE = page(NO_ORG_POSTING)


# `hiringOrganization` as a BARE STRING and `jobLocation` as a LIST -- both measured.
STRING_ORG_POSTING: dict[str, object] = {
    "@context": "http://schema.org",
    "@type": "JobPosting",
    "title": "Software Engineer",
    "datePosted": "2026-08-26",
    "hiringOrganization": "Example Venue Group",
    "jobLocation": [
        {
            "@type": "Place",
            "address": {
                "@type": "PostalAddress",
                "addressLocality": "Braselton",
                "addressRegion": "Georgia",
                "addressCountry": "United States",
            },
        }
    ],
    "description": _JD_BODY,
}
STRING_ORG_PAGE = page(STRING_ORG_POSTING)


# A `@graph` envelope -- the third block shape schema.org permits and real pages use.
GRAPH_PAGE = page(
    {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "Organization", "name": "Example Tooling Co"},
            dict(HIREOLOGY_POSTING),
        ],
    }
)


# A `@type` expressed as a LIST, which schema.org permits.
LIST_TYPE_PAGE = page({**HIREOLOGY_POSTING, "@type": ["JobPosting", "Thing"]})


# A login interstitial: several wall markers, no JD section marker. The two-sided test in
# `lanes.quality` is what has to reject this, and the lane has to route it to the right outcome.
LOGIN_WALL_PAGE = page(
    {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "Software Engineer",
        "datePosted": "2026-08-26",
        "hiringOrganization": {"@type": "Organization", "name": "Example Tooling Co"},
        "description": (
            "<p>Please sign in to continue.</p>"
            "<p>You must be logged in to view this posting.</p>"
            "<p>Forgot your password? Create an account to apply.</p>"
        ),
    }
)


# A page with no LD block at all.
NO_LD_PAGE = "<!DOCTYPE html><html><body><p>Nothing structured here.</p></body></html>"


# The four `datePosted` formats measured across the vendors, with what each must become as naive
# UTC. LITERALS on both sides: an expectation computed by the same parser under test would pass
# against any parser at all.
MEASURED_DATE_FORMATS: tuple[tuple[str, str], ...] = (
    ("2026-08-26", "2026-08-26 00:00:00"),
    ("2026-08-28T17:41:41+00:00", "2026-08-28 17:41:41"),
    ("2026-08-28T20:50:00+0000", "2026-08-28 20:50:00"),
    ("2026-08-28T14:12:10-05:00", "2026-08-28 19:12:10"),
)
