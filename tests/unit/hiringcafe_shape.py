"""An AUTHORED hiring.cafe search payload, generated from the probe's recorded counts.

NOT A CAPTURE, and that is a ruling rather than a convenience. Staging the real captures
failed `make check` on three counts, all correct: R2 found a live employer contact address
inside a JD body, and R7 refused the files as data absent from `SHIPPED_DATA`. Registering
them obliges a `provenance`, whose only honest value (`public`) obliges a `license` -- and
there is no license for a third party's job-description text in a public repository.
`synthetic` would be a lie. So nothing captured is committed, here or anywhere.

THE OPPOSITE TRAP, AND HOW THIS FILE AVOIDS IT. An authored fixture proves only what our own
code constructs -- that is how SmartRecruiters' round-trip test passed against a shape its own
README calls invented, and how five of six providers passed a dereference rule that was wrong.
The guard is that nothing below is a guess: every count is generated from a table transcribed
out of `docs/superpowers/research/2026-08-23-hiringcafe-lane-contract.md` and
`docs/superpowers/plans/2026-08-23-part3-lane-wiring-hiringcafe.md` §0, and the tests assert
the resulting numbers against literals written independently in the test file. All employer
names, tokens and body copy are invented; the SHAPES they are arranged in are the recorded
ones.

The three `objectID` counter-examples are the reason this file exists at all. A fixture of
well-formed hits cannot fail the test that a `___` split disagrees with the explicit
`source`/`board_token` fields, and the recorded disagreement rate is 22.5%.

DRIFT (fixture rule R15 in spirit -- R13's pinned-fixture-dir rule does not apply, because a
lane is not a registered provider and `tests/fixtures/<name>` for a non-provider is itself an
R13 violation). `ssrHits` is a live search result. `REVIEW_BY` is the date somebody must
re-run the two unauthenticated `curl` commands at the end of the contract and confirm the key
names and the source mix still hold. It is a review deadline, not a freshness claim. The drain
is a dated edit to `REVIEW_BY` below with the reason recorded beside it.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

# The probe session. Both documents are dated the same day.
PROBED = date(2026, 8, 23)
# PROBED + 90, the window `tools/generalization/fixtures.py` uses for the six ATS captures.
REVIEW_BY = date(2026, 11, 21)

# `robots.txt`, read 2026-08-26, when the role facet shipped. RECORDED rather than remembered
# because the lane's whole request shape follows from these three rules: the role route is a
# PATH precisely because the query forms are disallowed. If the Allow ever narrows, or a
# Disallow widens to cover `/jobs/`, the lane is in violation and nothing else in this repo
# would notice -- the requests would keep succeeding. Re-read these when rolling `REVIEW_BY`.
ROBOTS_READ = date(2026, 8, 26)
ROBOTS_ALLOWED_PREFIX = "/jobs/"
ROBOTS_DISALLOWED_FORMS: tuple[str, ...] = ("?searchState=", "?page=", "&page=")

# ---------------------------------------------------------------------------------------
# Recorded numbers. Everything below is generated from these; nothing else is a magic number.
# ---------------------------------------------------------------------------------------

# Contract §4, verbatim: the source mix over the 160 sampled hits.
SOURCE_MIX: tuple[tuple[str, int], ...] = (
    ("icims2", 36),
    ("oraclecloud", 24),
    ("saashr", 16),
    ("taleo_careersection", 16),
    ("fountain", 16),
    ("adprecruiting", 12),
    ("avature", 8),
    ("adhoc", 8),
    ("careerplug", 8),
    ("grnhse", 8),
    ("paylocity", 4),
    ("appone_api", 4),
)

TOTAL_HITS = 160  # contract §1 `ssrHits`
DISTINCT_BOARD_TOKENS = 40  # contract §4
# 160 / 40. Every recorded per-source count is divisible by 4, so a uniform four postings per
# board token reproduces BOTH recorded totals at once -- which is why the allocation below
# needs no per-source guess.
HITS_PER_BOARD_TOKEN = TOTAL_HITS // DISTINCT_BOARD_TOKENS

# Contract §3, verbatim: how many hits per source a `___` split of `objectID` mis-parses.
# Note saashr's 4 against its 16 hits in the mix above -- the case quirk is ONE employer's,
# not the source's, so three of its four board tokens are well-formed here.
MISPARSED_BY_SOURCE: tuple[tuple[str, int], ...] = (
    ("taleo_careersection", 16),
    ("fountain", 16),
    ("saashr", 4),
)
MISPARSED_HITS = sum(count for _, count in MISPARSED_BY_SOURCE)

# Contract §1's paging siblings. Recorded, never acted on: the parameter that turns a page is
# not in the contract, so the lane makes one GET.
SSR_PAGE = 0
SSR_PAGE_SIZE = 40
SSR_IS_LAST_PAGE = False
SSR_TOTAL_COUNT = 3_886_890
SSR_COMPANY_COUNT = 123_343

# ---------------------------------------------------------------------------------------
# Invented content. Shapes are recorded; every name, token and sentence here is made up.
# ---------------------------------------------------------------------------------------

def _allocation() -> tuple[tuple[str, int], ...]:
    """(source, board-token index) for each of the 40 tokens, in recorded-mix order."""
    rows: list[tuple[str, int]] = []
    index = 0
    for source, count in SOURCE_MIX:
        for _ in range(count // HITS_PER_BOARD_TOKEN):
            rows.append((source, index))
            index += 1
    return tuple(rows)


BOARD_TOKEN_ALLOCATION = _allocation()

# The one saashr employer whose objectID differs in case from its own board_token. Contract §3
# records 4 such hits against 16 saashr hits, so it is a single token's quirk; spreading it
# across the source would make the fixture's mis-parse rate 30% where the probe measured 22.5%.
_SAASHR_MIXED_CASE_INDEX = next(i for source, i in BOARD_TOKEN_ALLOCATION if source == "saashr")

_CITIES: tuple[tuple[str, str], ...] = (
    ("Seattle", "Washington"),
    ("Austin", "Texas"),
    ("Columbus", "Ohio"),
    ("Flagstaff", "Arizona"),
)

# Deliberately mixed: hiring.cafe is a general job board of 3.89M postings whose first sampled
# JD was a prep cook, so a fixture of nothing but engineering titles would misrepresent it.
_TITLES: tuple[str, ...] = (
    "Software Engineer, New Grad",
    "Backend Engineer",
    "Prep Cook",
    "Warehouse Associate",
)


def employer(index: int) -> str:
    return f"acme{index:02d}"


def employer_name(index: int) -> str:
    return f"Acme {index:02d}"


def board_token(source: str, index: int) -> str:
    """The explicit top-level `board_token`, in that source's recorded shape."""
    if source == "fountain":
        # Contract §3: fountain's board_token CONTAINS `___`, so any positional split of the
        # objectID mis-attributes it.
        return f"us-3.fountain.com___{employer(index)}"
    if source == "saashr":
        # Contract §3: lowercase here, mixed case inside the objectID.
        return f"{employer(index)}stores"
    return employer(index)


def object_id(source: str, index: int, seq: int) -> str:
    """The opaque JD-endpoint key, in that source's recorded shape.

    128 of 160 look like `{source}___{board_token}___{id}`. The three sources below do not,
    and the lane must never learn the difference -- it reads `source` and `board_token`.
    """
    if source == "taleo_careersection":
        # Contract §3: SINGLE underscores throughout, so a `___` split yields one segment.
        return f"taleo_careersection_{employer(index)}_{2619805 + seq}"
    if source == "saashr" and index == _SAASHR_MIXED_CASE_INDEX:
        # Contract §3: case differs from the explicit board_token.
        return f"saashr___Acme{index:02d}Stores___{537204545 + seq}"
    return f"{source}___{board_token(source, index)}___{100000 + seq}"


def apply_url(source: str, index: int, seq: int) -> str:
    """The employer's own URL.

    `grnhse` resolves to a real greenhouse posting shape -- contract §4's 8/160 convergence
    case, the one `lanes.dereference` was built for. Everything else lands on an employer host
    no provider in this repo recognizes, which is the other 95% and the point of the lane.
    """
    if source == "grnhse":
        return f"https://boards.greenhouse.io/{employer(index)}/jobs/{6000001 + seq}"
    return f"https://careers.{employer(index)}.test/jobs/{4200 + seq}"


def job_description_html(title: str, employer_label: str) -> str:
    """A JD body in the recorded shape: `<H1>` first, then real section headings.

    The `Sign in` in the footer is load-bearing, not decoration. Nearly every real posting page
    carries one, so a one-sided login-wall test rejects the whole corpus; this fixture makes
    that regression fail rather than pass.
    """
    return (
        f"<H1>{title}</H1>"
        f"<p>{employer_label} is hiring a {title.lower()} to join a small team that ships "
        "weekly. This posting is open to applicants already able to work in the United "
        "States, and the team works on site four days a week.</p>"
        "<h2>Responsibilities</h2>"
        "<ul>"
        "<li>Own a service end to end, from design through operation.</li>"
        "<li>Review your teammates' changes and keep the build green.</li>"
        "<li>Write down what you learned so the next person does not relearn it.</li>"
        "<li>Answer the on-call pager one week in six.</li>"
        "</ul>"
        "<h2>Qualifications</h2>"
        "<ul>"
        "<li>Comfortable reading code you did not write.</li>"
        "<li>Some experience with a relational database.</li>"
        "<li>Able to explain a tradeoff in writing.</li>"
        "</ul>"
        "<h2>Benefits</h2>"
        "<p>Health cover from day one, a training budget, and paid time off that the team "
        "actually takes.</p>"
        "<footer><a href='/account'>Sign in</a></footer>"
    )


def hit(source: str, index: int, seq: int) -> dict[str, Any]:
    """One `ssrHits` entry, carrying every top-level key plan §0 recorded."""
    token = board_token(source, index)
    oid = object_id(source, index, seq)
    title = _TITLES[seq % len(_TITLES)]
    city, state = _CITIES[index % len(_CITIES)]
    return {
        # Coordinates only -- no place name. Present so a test can assert the lane never reads
        # it: `rank.location_gate` matches text, and a coordinate resolves `unknown`, which
        # fails OPEN through the hard US gate.
        "_geoloc": [{"lat": 35.1983, "lon": -111.6513}],
        "apply_url": apply_url(source, index, seq),
        "board_token": token,
        "collapse_key": f"{token}-{seq}",
        "enriched_company_data": {
            "name": employer_name(index),
            "homepage_uri": f"https://{employer(index)}.test/",
            "hq_country": "United States",
            "industries": ["Retail"],
            "nb_employees": 500 + index,
            "organization_type": "Private",
            "tagline": "An invented company.",
            "year_founded": 1990 + (index % 30),
            "status": "active",
        },
        "id": f"{token}-{seq}",
        "is_expired": False,
        # No body and no location here -- both confirmed absent from the search response.
        "job_information": {
            "job_title_raw": title,
            "title": title,
            "num_views": 10 + seq,
            "viewedByUsers": [],
        },
        "liberal_dedup_cluster": f"lib-{index}",
        "objectID": oid,
        "requisition_id": f"REQ-{index:02d}-{seq}",
        "source": source,
        "source_and_board_token": f"{source}|{token}",
        "strict_dedup_cluster_id": f"strict-{index}-{seq}",
        # The ONLY place location text lives. Untrusted for eligibility (D-278); read here as
        # provider-asserted metadata at the trust level every other provider's location field
        # already has.
        "v5_processed_job_data": {
            "workplace_cities": [city],
            "workplace_states": [state],
            "workplace_countries": ["United States"],
            "workplace_continents": ["North America"],
            "workplace_counties": [],
            "formatted_workplace_location": f"{city}, {state}",
            "workplace_type": "Onsite",
            "is_workplace_worldwide_ok": False,
        },
    }


def search_hits() -> list[dict[str, Any]]:
    """All 160 hits: each source's recorded count, spread four to a board token."""
    hits: list[dict[str, Any]] = []
    for token_number, (source, index) in enumerate(BOARD_TOKEN_ALLOCATION):
        base = token_number * HITS_PER_BOARD_TOKEN
        for offset in range(HITS_PER_BOARD_TOKEN):
            hits.append(hit(source, index, base + offset))
    return hits


def search_page_html(hits: list[dict[str, Any]] | None = None) -> str:
    """The server-rendered page, with the payload inside `<script id="__NEXT_DATA__">`.

    The surrounding markup carries a `</script>`-free `</div>` inside a JSON string value on
    purpose: that is what defeated a regex extractor on the real page.
    """
    payload = {
        "props": {
            "pageProps": {
                "ssrHits": search_hits() if hits is None else hits,
                "ssrPage": SSR_PAGE,
                "ssrPageSize": SSR_PAGE_SIZE,
                "ssrIsLastPage": SSR_IS_LAST_PAGE,
                "ssrTotalCount": SSR_TOTAL_COUNT,
                "ssrCompanyCount": SSR_COMPANY_COUNT,
                "ssrTimings": {"esLatencyMs": 365},
                "initialSearchState": {"country": "United States", "note": "</div>"},
            }
        }
    }
    return (
        "<!DOCTYPE html><html><head><title>hiring.cafe</title></head><body>"
        "<div id='__next'>rendered results</div>"
        '<script id="__NEXT_DATA__" type="application/json">'
        f"{json.dumps(payload)}"
        "</script></body></html>"
    )


def job_description_payload(one_hit: dict[str, Any]) -> bytes:
    """`GET /api/job-description?id=...` -> `{"job": {"job_information": {"description": ...}}}`."""
    info = one_hit["job_information"]
    body = job_description_html(info["title"], one_hit["enriched_company_data"]["name"])
    return json.dumps({"job": {"job_information": {"description": body}}}).encode("utf-8")
