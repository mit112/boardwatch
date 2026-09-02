"""An AUTHORED Indeed mobile-GraphQL search payload, built to the structure §6 recorded.

NOT A CAPTURE, and that is a ruling rather than a convenience (D-285/D-290). No employer name, no
job-description text and no URL below is copied from Indeed: the SHAPES are the recorded ones,
every string arranged in them is invented. Committing a capture would oblige a `provenance` whose
only honest value (`public`) obliges a `license`, and there is no license for a third party's
posting text in a public repository. `synthetic` would be a lie.

THE OPPOSITE TRAP, AND HOW THIS FILE AVOIDS IT. An authored fixture proves only what our own code
constructs -- that is how a round-trip test passed against an invented shape, and how five of six
providers passed a dereference rule that was wrong. Four independent traps guard against it, and
none of them can pass a fixture of merely well-formed hits:

  * `DEREFERENCE_HITS` give `recruit.viewJobUrl` values that are real greenhouse / lever / ashby
    POSTING URL SHAPES, so a client that filed every employer under `indeed` groups them wrong.
    The URLs match the shapes `lanes/dereference.py` pins from each provider's own payload field,
    which is the one place in this repo that rule is stated.
  * `TRAILING_CHROME_HIT` gives a lever posting URL with `/apply` appended -- the shape
    `parse_posting_target` REFUSES, because `apply` is constant per provider and reading it as a
    posting reference collides two real postings on UNIQUE(company_id, provider_posting_id). A
    client that read the last segment regardless would pass every other test in the file.
  * `NAME_COLLISION_HITS` give two hits sharing one employer display NAME under two different
    `/cmp/` keys. A client that grouped by name would collapse two employers into one.
  * `LOCAL_MIDNIGHT_HIT` gives a `datePublished` whose UTC date and US-local date DIFFER, so a
    client that read the epoch in the running machine's zone records a different day on a laptop
    than on a CI runner.

DRIFT. `REVIEW_BY` is the date somebody must re-confirm the field list and the response envelope
against the live endpoint. It is a review deadline, not a freshness claim; the drain is a dated
edit to `REVIEW_BY` with the reason recorded beside it. R13's pinned-fixture-dir rule does not
apply -- a lane is not a registered provider.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any

# The probe session (RETIREMENT-PLAN.md §6). PROBED + 90, matching the window the six ATS
# captures and the LinkedIn shape both use.
PROBED = date(2026, 9, 1)
REVIEW_BY = date(2026, 11, 30)

# The one request shape, and the one filter argument that is evidenced.
SEARCH_URL = "https://apis.indeed.com/graphql?co=US"


@dataclass(frozen=True)
class Hit:
    """One search hit, in the fields the field mapping reads."""

    key: str
    title: str
    employer_name: str
    location: str = "Austin, TX"
    # `/cmp/{employer key}`. None models a hit that carries no employer page at all, which the
    # lane must REFUSE rather than key on a slugified display name.
    employer_page: str | None = None
    # The employer's own apply URL. None models a hit that carries none.
    view_job_url: str | None = None
    # Epoch MILLISECONDS. 2026-08-31T12:00:00Z by default -- deliberately mid-day so an
    # accidental local-zone read still lands on the same date and cannot mask the bug; the
    # `LOCAL_MIDNIGHT_HIT` trap is what makes the zone observable.
    published_ms: int = 1_788_177_600_000
    # None models a hit whose description is absent, which is `extracted_empty` and not a body.
    description_html: str | None = None


def job_description_html(hit: Hit) -> str:
    """A JD body in the shape the endpoint returns: employer prose under real section headings.

    Comfortably over the `lanes.quality` floor in every dimension, which is deliberate even
    though this lane does not apply that floor: a fixture that only just cleared it would make
    the "no floor here" decision invisible if somebody later reinstated one.
    """
    return (
        f"<p>{hit.employer_name} is hiring a {hit.title.lower()} to join a small team that "
        "ships weekly.</p>"
        "<h2>Responsibilities</h2>"
        "<ul><li>Design and build services that other teams depend on.</li>"
        "<li>Review changes and keep the deployment path boring.</li>"
        "<li>Write the runbook before the incident, not after it.</li></ul>"
        "<h2>Requirements</h2>"
        "<ul><li>Comfortable reading code you did not write.</li>"
        "<li>Able to explain a trade-off to somebody who was not in the room.</li>"
        "<li>Willing to delete something that is not carrying its weight.</li></ul>"
        "<h2>What we offer</h2>"
        "<p>A short interview loop and a written decision either way.</p>"
    )


def job_dict(hit: Hit) -> dict[str, Any]:
    """One `results[].job` object, in the recorded nesting."""
    description = (
        hit.description_html if hit.description_html is not None else job_description_html(hit)
    )
    employer: dict[str, Any] = {
        "name": hit.employer_name,
        "relativeCompanyPageUrl": hit.employer_page,
        "dossier": None,
    }
    return {
        "source": {"name": "Employer"},
        "key": hit.key,
        "title": hit.title,
        "datePublished": hit.published_ms,
        "dateOnIndeed": hit.published_ms,
        "description": {"html": description} if description is not None else None,
        "location": {
            "countryName": "United States",
            "countryCode": "US",
            "admin1Code": "TX",
            "city": hit.location.split(",")[0],
            "postalCode": None,
            "streetAddress": None,
            "formatted": {"short": hit.location, "long": f"{hit.location}, United States"},
        },
        "compensation": None,
        "attributes": [{"key": "CF3CP", "label": "Full-time"}],
        "employer": employer,
        "recruit": {
            "viewJobUrl": hit.view_job_url,
            "detailedSalary": None,
            "workSchedule": None,
        },
    }


def search_response(hits: list[Hit], *, next_cursor: str | None = None) -> str:
    """The whole GraphQL envelope, as the endpoint returns it."""
    return json.dumps(
        {
            "data": {
                "jobSearch": {
                    "pageInfo": {"nextCursor": next_cursor},
                    "results": [
                        {"trackingKey": f"tk-{hit.key}", "job": job_dict(hit)} for hit in hits
                    ],
                }
            }
        }
    )


def error_response(message: str = "Variable 'start' has an invalid value") -> str:
    """A 200 carrying GraphQL `errors` -- how a rejected filter argument actually arrives.

    The ISO-timestamp date filter is refused exactly this way (`BAD_USER_INPUT`), so a client
    that read only `results` would see an empty list and record a quiet day.
    """
    return json.dumps(
        {"errors": [{"message": message, "extensions": {"code": "BAD_USER_INPUT"}}], "data": None}
    )


def search_hits(count: int = 8, *, companies: int = 4) -> list[Hit]:
    """`count` hits spread over `companies` employers, so grouping is observable."""
    return [
        Hit(
            key=f"key{index:04d}",
            title="Backend Engineer",
            employer_name=f"Acme {index % companies:02d}",
            employer_page=f"/cmp/Acme-{index % companies:02d}",
        )
        for index in range(count)
    ]


# --- The traps ------------------------------------------------------------------------------

# `recruit.viewJobUrl` values in the exact posting shapes `lanes/dereference.py` pins, one per
# body-inlined provider. A client that filed every employer under `indeed` groups all three wrong.
DEREFERENCE_HITS: list[Hit] = [
    Hit(
        key="key9001",
        title="Platform Engineer",
        employer_name="Vertex Systems",
        employer_page="/cmp/Vertex-Systems",
        view_job_url="https://boards.greenhouse.io/vertexsystems/jobs/6000001",
    ),
    Hit(
        key="key9002",
        title="Data Engineer",
        employer_name="Beacon Labs",
        employer_page="/cmp/Beacon-Labs",
        view_job_url="https://jobs.lever.co/beaconlabs/a1000000-0000-0000-0000-000000000001",
    ),
    Hit(
        key="key9003",
        title="Site Reliability Engineer",
        employer_name="Halcyon Works",
        employer_page="/cmp/Halcyon-Works",
        view_job_url="https://jobs.ashbyhq.com/halcyonworks/ashby-0001",
    ),
]

# A lever posting URL with the `/apply` chrome segment appended. `parse_posting_target` REFUSES
# it, so the lane must fall back to `indeed` rather than key the posting on the constant `apply`.
TRAILING_CHROME_HIT = Hit(
    key="key9101",
    title="Backend Engineer",
    employer_name="Beacon Labs",
    employer_page="/cmp/Beacon-Labs",
    view_job_url="https://jobs.lever.co/beaconlabs/a1000000-0000-0000-0000-000000000002/apply",
)

# Two employers, one display name, two `/cmp/` keys.
NAME_COLLISION_HITS: list[Hit] = [
    Hit(
        key="key9201",
        title="Backend Engineer",
        employer_name="Vertex",
        employer_page="/cmp/Vertex-Analytics",
    ),
    Hit(
        key="key9202",
        title="Backend Engineer",
        employer_name="Vertex",
        employer_page="/cmp/Vertex-Robotics",
    ),
]

# No `/cmp/` page at all: the lane must refuse to key it rather than slugify the display name.
NO_EMPLOYER_PAGE_HIT = Hit(
    key="key9301",
    title="Backend Engineer",
    employer_name="Unnamed Holdings",
    employer_page=None,
)

# `description` absent. A response arrived and extraction produced nothing -- `extracted_empty`.
NO_BODY_HIT = Hit(
    key="key9401",
    title="Backend Engineer",
    employer_name="Acme 00",
    employer_page="/cmp/Acme-00",
    description_html="",
)

# 2026-08-31T01:00:00Z. In every US zone that is still 2026-08-30, so a client that reads the
# epoch in the machine's local zone records the wrong DAY and this trap fails on a US runner
# while passing on a UTC one -- which is exactly the drift the assertion exists to catch.
LOCAL_MIDNIGHT_HIT = Hit(
    key="key9501",
    title="Backend Engineer",
    employer_name="Acme 00",
    employer_page="/cmp/Acme-00",
    published_ms=1_788_138_000_000,
)

# The tier-D case (D-413): a real employer board `core/board_urls.py` has never registered a
# host for. "careers.example-hcm.com" matches none of the six providers' host lists, so
# `parse_posting_target` raises `UnknownBoardURL` -- distinct from `TRAILING_CHROME_HIT` above,
# whose host IS a registered provider and raises `UnresolvablePostingURL` instead. This is the
# URL `lane_seeds` exists to carry to a later resolver lane.
TENANT_SEED_HIT = Hit(
    key="key9601",
    title="Software Engineer I",
    employer_name="Example Manufacturing",
    employer_page="/cmp/Example-Manufacturing",
    view_job_url="https://careers.example-hcm.com/en/sites/CX_1/job/9601",
)

# Same unrecognized host, but with NO `/cmp/` page either -- `hit_identity` REFUSES this hit
# entirely (`UnidentifiableHit`), and the seed must still be captured. Proves seeding is read off
# the raw search entries, not off `_group_by_company`'s output.
UNIDENTIFIABLE_TENANT_SEED_HIT = Hit(
    key="key9701",
    title="Software Engineer II",
    employer_name="Unnamed HCM Tenant",
    employer_page=None,
    view_job_url="https://careers.example-hcm.com/en/sites/CX_1/job/9701",
)

# A REGISTERED provider's own bare shortlink, which carries no org and so no extractable slug
# (`WorkableProvider.slug_from_path` returns None for it). `parse_posting_target` raises the
# `UnknownBoardURL` BASE class -- which an unregistered host's `UnregisteredBoardHost` SUBCLASSES,
# so both reach the same `except UnknownBoardURL` catcher, but only the subclass may seed. This is
# the trap a review caught: a client seeding on any `UnknownBoardURL` would file a KNOWN provider's
# posting into the tier-D queue. Must NOT be seeded.
KNOWN_PROVIDER_UNROUTABLE_SEED_HIT = Hit(
    key="key9801",
    title="Software Engineer III",
    employer_name="Beacon Labs",
    employer_page="/cmp/Beacon-Labs",
    view_job_url="https://apply.workable.com/j/ABC123",
)

# An unbalanced IPv6 bracket. `urlparse` raises a BARE `ValueError` on this ("Invalid IPv6 URL"),
# which `core/board_urls.py` converts to the `UnknownBoardURL` BASE class -- the same catcher, but
# NOT the `UnregisteredBoardHost` subclass an unregistered host raises. Must NOT be seeded: it is
# not a URL in any usable sense, let alone a tenant.
MALFORMED_VIEW_JOB_URL_HIT = Hit(
    key="key9802",
    title="Software Engineer IV",
    employer_name="Halcyon Works",
    employer_page="/cmp/Halcyon-Works",
    view_job_url="https://[broken",
)

# HAS a scheme and a hostname, so it clears `_is_addressable_url`'s scheme and hostname checks --
# but `urlparse` still tolerates it without raising anything, reading everything before the next
# `/` as a literal, space-containing "hostname". `parse_posting_target` then raises the
# `UnknownBoardURL` BASE class (that space-bearing host matches no provider), NOT the
# `UnregisteredBoardHost` subclass a real unrecognized vendor raises -- but the whitespace check
# inside `_is_addressable_url` rejects it before that, so the string that gets RECORDED is guarded
# regardless of the exception class. Must NOT be seeded.
GARBAGE_VIEW_JOB_URL_HIT = Hit(
    key="key9803",
    title="Software Engineer V",
    employer_name="Vertex Systems",
    employer_page="/cmp/Vertex-Systems",
    view_job_url="https://not a real host/job/1",
)
