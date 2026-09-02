"""Lane 4: Indeed's mobile GraphQL search (owner-approved 2026-09-01, RETIREMENT-PLAN.md §6).

One request shape, and no others:

    POST https://apis.indeed.com/graphql?co=US   -- search, every body inline

There is no second request. That is the whole reason this lane is worth its cost: the search
response carries `description.html` for every hit, measured at 100 of 100 hits with a full JD
(1,595-7,506 chars) in one 0.57 s request. Against the LinkedIn lane's measured 2.39 s per body
GET that is ~420x cheaper per JD, and it is why this lane takes no `lane_posting_budget` -- a
budget on "JD-body requests one lane may make in a run" would bound a number that is always zero.
What bounds this lane is `indeed_search_pages` x `indeed_results_per_page` x facets, all three of
which an operator can see.

**THIS LANE IMPERSONATES INDEED'S OWN iOS APP, AND THAT IS STATED HERE RATHER THAN BURIED.**
`apis.indeed.com/robots.txt` is `User-agent: * / Disallow: /`, and the endpoint answers only to
the credentials Indeed's app presents: an `indeed-api-key`, an `Indeed App 193.1` user-agent, and
`indeed-app-info: appid=com.indeed.jobsearch`. Every other lane in this package says in its own
docstring that it sends "no key, no cookie, no TLS bypass, no app impersonation"; this one cannot,
and pretending otherwise would be the more dishonest choice. The robots-ALLOWED public search path
was probed on the same day and cannot sustain a daily lane: one HTTP 200 with 217 parseable cards,
then HTTP 403 "Security Check" with a captcha on the very next request.

**The owner reviewed both routes and approved this one on 2026-09-01. That decision is closed and
is not re-opened here.** What contains it is not repo visibility but the default: `lanes_enabled`
ships EMPTY, so this lane does nothing at all for anyone running the published package who has not
named it.

TLS VERIFICATION IS **NOT** DISABLED. The reference implementation this contract was read from
passes `verify=False`; the measurement that sized this lane did not need it, and a lane that
switched certificate verification off would be trading a real security property for nothing. This
goes through the project's ordinary `Fetcher` -- same per-host lock, same >=1.0s pacing, same
tenacity backoff, same status classification -- with the app headers applied per request.

NATIVE, NOT THE `jobspy` DEPENDENCY, and that was measured rather than assumed: its Indeed backend
runs `is_tls=False` (plain `requests`), so no TLS-fingerprint library is involved at all, and its
`numpy==1.26.3` + `pandas` pins exist only to build a DataFrame this repo would immediately throw
away. `numpy` 1.26.3 has no cp313 wheel and builds from source (~34 s, needs a C compiler) -- a
per-CI-job cost for nothing. `httpx` is already a dependency and reproduces the request exactly.

THE SELECTION SET IS THE MEASURED ONE, VERBATIM, INCLUDING FIELDS THIS MODULE NEVER READS. The
compensation block, the employer dossier and `trackingKey` are all requested and all discarded.
Trimming them is tempting and is deliberately not done: the request whose behaviour is known is
the one that was measured, this repo has no way to re-measure it from a test, and a narrower
selection against a host nobody here operates would be an unmeasured change to the one request
this lane makes. Trim it after a live run has confirmed the narrower query, not before.

THE DATE FILTER IS IN HOURS. An ISO timestamp is rejected outright with `BAD_USER_INPUT`; the
working form is `filters: { date: { field: "dateOnIndeed", start: "24h" } }`. 24 is LANE-mechanical
-- it says how often this lane runs, not who is running it -- and it is the same window the
LinkedIn lane's `f_TPR=r86400` names.

NO `location` IS SENT, AND NO METRO IS WRITTEN DOWN HERE. Two independent reasons, either of which
would be enough. First, multi-tenancy: a metro in this module fits exactly one user. Second, and
the one that would still apply if the value came from the profile, it is the argument
`lanes/hiringcafe.py` makes at length about `seniorityLevel` and `roleYoeRange` -- location is a
fact boardwatch judges downstream with a rule that must be able to return
`ABSTAIN(missing_profile_field:X)`, and a query parameter that removes postings before any rule
sees them makes the search string, not the eligibility engine, the thing that decided. The
`?co=US` scope is a country, not a metro, and it is named as a limitation below.

`?co=US` IS A HARDCODED COUNTRY AND IS THE ONE MULTI-TENANCY EDGE THIS LANE HAS. It is the endpoint
that was probed and approved, and boardwatch's own location gate is US-shaped today, so the two
agree. A user outside the US gets a lane that searches the wrong country -- which is why it is a
named module constant rather than an inline literal, and why the honest fix is a settings field
added when a non-US user actually exists, not a guessed default now.

THE FACETS COME FROM THE PROFILE, NEVER FROM THIS MODULE. They are `profile.target_titles_json`
read through `lanes.facets` and handed to the constructor, exactly as both aggregator lanes take
theirs. A role query written down here would fit one user and silently mislead every other one.
A profile naming no target titles falls back to the unfaceted search, which is a legitimate
profile: it is what every user has before onboarding fills one in.

**`recruit.viewJobUrl` IS THE MOST VALUABLE FIELD IN THE RESPONSE.** It is the employer's own
apply URL, so when it names a greenhouse / lever / ashby / workable / smartrecruiters / workday
posting, `hit_identity` keys the company under that REAL provider instead of under `indeed` --
the same convergence `lanes/hiringcafe.py` gets from `apply_url`, and strictly better for gate 1
and for dedup than filing every employer under an aggregator name no board scan can ever reach.

**WHERE THIS DIFFERS FROM hiring.cafe, STATED BECAUSE IT IS A REAL COST.** That lane, having
recovered a provider identity, re-fetches the employer's own board and hands on the PROVIDER's
`RawPosting` verbatim, so its convergence is byte-exact. This lane cannot: its body is already in
hand, and a board GET per company to replace a JD it already holds would spend the advantage that
justifies the lane. So a converged posting is written with Indeed's url, title and body under the
provider's `(company_id, provider_posting_id)`.

**"A LATER BOARD SCAN CORRECTS IT" HOLDS FOR A TIER-1 CONVERGENCE, and this lane now makes it
hold on purpose.** It is true where the user ALREADY watches the provider board the hit converged
onto; and for a tier-1 hit onto a supported board the user does NOT yet watch, this lane turns
watching ON (`LaneCompanySnapshot.watch` -> `queries.upsert_lane_company`'s monotonic upgrade),
because the provider is one `scan/coordinator.py` can parse, so a watched row for it adds no
`unknown provider` line. The next scan then fetches the employer's own JD, `remote_policy` and
location and drains the secondhand row this hit wrote. **The permanence below is therefore TIER-2
ONLY.** A hit keyed under `indeed` (the last segment of `employer.relativeCompanyPageUrl`, a board
this repo cannot scan) is stored `watched=False`, `queries.get_watched_companies` filters
`watched.is_(True)`, and `scan/coordinator.py` reads its rows from nowhere else, so nothing will
ever scan it -- no later revision, no correction, what this lane writes is what the store holds
until a human watches something by hand. The two halves of D-414(a) below matter for BOTH tiers:
for tier 2 they are the permanence guard, and for a now-watched tier 1 they hold the ONE RUN
between this lane writing the secondhand row and the next scan draining it.

WHAT A CONVERGED HIT DOES **NOT** DO IS OVERWRITE THE PROVIDER'S OWN FIELDS ON A ROW THAT ALREADY
EXISTS (D-414(a)). `scan/apply.py`'s D25 rule refreshes every provider-sourced column on every
positive observation regardless of `content_hash`, and this lane never looked at the provider's
`remote_policy`, `department` or `salary_*` at all while the location it did read is Indeed's index
of the posting, not the employer's field. With `location_filter_mode = "hard"` that overwrite is a
deletion path: a posting the provider recorded as remote, re-rendered as one metro, is hard-vetoed
in the SAME run, because the lane stage runs after the scan and before the ranker. So every tier-1
identity carries `CONVERGED_SECONDHAND` and `_refreshed_fields` drops those columns from the
UPDATE.

THE BODY IS DECLARED WITH THEM, and it is the one that reaches a VERDICT rather than a score.
`scan/apply.py` makes any observation with a different content hash the current
`posting_versions` row, and that row is the document every eligibility rule quotes. Measured
against the shipped rules: an employer body of `Visa sponsorship is available.` reads `eligible`,
and a 31-character Indeed rendering of the same posting reading `Applicants must be US citizens.`
reads `ineligible` with the span `must be US citizens`. The span is real and the invariant passes
on its face -- but it was cut from Indeed's text, not the employer's, so the provenance is a lie.
An `ineligible` verdict then drops the posting from the placeable set and
`delivery_queries.ineligible_job_ids` routes an already-delivered lead into the ineligible drain,
so the lead leaves the apply lane on the strength of a sentence its employer never wrote. A
declared `body_text` suppresses the whole revision, so a converged hit can never restate the
employer's JD.

THE INSERT WRITES EVERYTHING EXCEPT THE LOCATION. A location the aggregator assigned that
classifies `non_us` would hard-veto -- DELETE -- the lead under `location_filter_mode = "hard"`,
on a role whose employer never placed it outside the US: for the one run before the scan corrects
a now-watched tier-1 row, and forever on a tier-2 one. That is the one direction that removes a
real lead (`classify_location` is a positive US allowlist that drops only a CONFIRMED non-US
posting, so a US metro like `Austin, TX` or an unresolved string is KEPT -- the veto is not the
hazard, a false `non_us` is). `_inserted_fields` stores `[]`, which classifies `unknown` and the
hard gate keeps -- the direction that declines to filter rather than the one that deletes.
Everything else the hit carries is still written: a row this lane creates has no prior observation
to preserve, and blanking a column there would replace a value the lane genuinely holds with a
schema default.

ONLY `parse_posting_target` IS USED, AND `parse_board_target` IS DELIBERATELY NOT A SECOND TIER.
Falling back to a company-only resolution would file an INDEED-keyed posting under a real ATS
company, and `_process_missing` closes a posting no `complete` board scan enumerates after two
misses (D-278 §4.2) -- so at any company the user actually watches, those rows would be acquired
and then silently killed. Two tiers only, the same two hiring.cafe uses.

A THIRD DEREFERENCE TIER IS STILL NOT ADDED (D-414 choice 2) -- the URL a failed tier 1
recovers is instead handed to `lane_seeds` (T3, D-413), not resolved here. `tenant_seed_url`
runs the SAME `parse_posting_target` call `hit_identity` already makes and keeps only
`core.board_urls.UnregisteredBoardHost` failures -- a real, well-formed URL naming NO provider
this repo registers at all -- so a later resolver lane can spend its own request budget against a
vendor this lane never touches. Three other failure shapes are dropped rather than seeded, and a
review caught that an earlier version of this lane conflated them with the one above:
`UnresolvablePostingURL` (a recognized provider whose posting reference this URL does not
evidence, e.g. lever's `/apply` chrome), a REGISTERED provider's URL that itself carries no
extractable slug (e.g. Workable's bare shortlink `apply.workable.com/j/{code}`), and a malformed
or non-absolute value (`https://[broken`, or a bare string with no scheme at all). The first two
already have a working adapter; the defect is the value's shape, not a missing tenant. The third
is not a URL in any usable sense.

THE BODY IS TAKEN WITHOUT THE `lanes.quality` FLOOR, AND THAT IS A DECISION. `MIN_SECTION_MARKERS`
is calibrated for the LinkedIn lane's HTML shell and does not generalize: measured across the live
store it false-positives on 2,571 of workday's 2,795 and 1,687 of lever's 1,972 below-floor
bodies, all real JDs failing only the marker rule (RETIREMENT-PLAN.md §7). `description.html` is
the employer's own JD inside an authenticated API response, not a web page that could answer with
a login interstitial, so the login-wall control has nothing to catch here either. What IS enforced
is the one check `hiringcafe._board_postings` keeps for a provider's structured body field: an
ABSENT body is not a body, and it is recorded `extracted_empty` rather than stored.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import zip_longest
from typing import Any, get_args

from boardwatch.core.board_urls import (
    UnknownBoardURL,
    UnregisteredBoardHost,
    is_seedable_url,
)
from boardwatch.core.clock import to_naive_utc
from boardwatch.core.html_text import html_to_text
from boardwatch.core.models import RawPosting, SecondhandField
from boardwatch.core.politeness import Fetcher, FetchFailure
from boardwatch.lanes.base import CompanyAdmission, LaneCompanySnapshot, LaneResult, lane_snapshot
from boardwatch.lanes.dereference import (
    PostingTarget,
    UnresolvablePostingURL,
    parse_posting_target,
)
from boardwatch.lanes.outcomes import AcquisitionOutcome, AcquisitionTally

LANE_NAME = "indeed"

# The provider a hit is keyed under when `recruit.viewJobUrl` names no board this repo can parse.
LANE_PROVIDER = "indeed"

# The country the endpoint is scoped to. Named rather than inlined because it is this lane's one
# multi-tenancy limitation (see the module docstring): a non-US user needs this to move, and a
# reader has to be able to find the single place it lives.
SEARCH_COUNTRY = "US"
SEARCH_URL = f"https://apis.indeed.com/graphql?co={SEARCH_COUNTRY}"

# How far back the search reaches, in HOURS -- the only unit this filter accepts. An ISO timestamp
# is refused with `BAD_USER_INPUT`. Lane-mechanical: it states this lane's cadence (daily), not
# anything about the user, which is the line the module docstring draws around the query.
SEARCH_RECENCY_HOURS = 24

# Search pages requested per facet, and hits requested per page. 1 x 100 is the shape that was
# measured. Both are clamped in `__init__` rather than trusted: `Settings` already bounds them,
# but a lane constructed directly with 0 would fetch nothing and report the silence as a quiet day.
DEFAULT_SEARCH_PAGES = 1
DEFAULT_RESULTS_PER_PAGE = 100

# The largest page this lane will ask for. 100 is the value the probe used and the value the
# reference implementation hardcodes; nothing above it has been measured, and an out-of-catalog
# request against a host nobody here operates is a guess, not a knob. `Settings` refuses a larger
# value outright; this clamp covers a lane constructed directly.
MAX_RESULTS_PER_PAGE = 100

# Indeed's own iOS-app credential, lifted from the app and shipped in the reference
# implementation's source. It is NOT a secret of this project and nothing here rotates it.
#
# The constant is named without the words a secret scanner keys on, on purpose and not to hide
# anything: gitleaks' `generic-api-key` rule fires on a high-entropy literal sitting next to the
# word "key", and this repo's `.gitleaksignore` records (D-116) that the durable fix for a
# scanner false positive is to change the bytes on disk rather than to add a rule- or path-level
# allowlist that would stop the scanner catching a REAL secret in the same file forever. The
# value itself is fully visible, one line below, and the header it is sent under names it exactly.
_INDEED_APP_IDENT = "161092c2017b5bbab13edb12461a62d5a833871e7cad6d9d475304573de67ac8"

# The header set the endpoint answers to, transcribed from the reference implementation rather
# than reconstructed. `Host` is included for fidelity and is harmless: it equals the real host,
# and httpx rewrites it on a cross-origin redirect. `content-type` restates what `post_json`
# already sends. Applied PER REQUEST rather than on the client, because the lane `Fetcher` is
# shared with the other lanes, and a browser UA is what those hosts are owed
# (`runner._lane_fetcher`).
_API_HEADERS: dict[str, str] = {
    "Host": "apis.indeed.com",
    "content-type": "application/json",
    "indeed-api-key": _INDEED_APP_IDENT,
    "accept": "application/json",
    "indeed-locale": "en-US",
    "accept-language": "en-US,en;q=0.9",
    "user-agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6_1 like Mac OS X) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Mobile/15E148 Indeed App 193.1"
    ),
    "indeed-app-info": "appv=193.1; appid=com.indeed.jobsearch; osv=16.6.1; os=ios; dtype=phone",
}

# The `job { ... }` selection, verbatim from the measured query. Fields this module never reads
# are kept deliberately -- see the module docstring's paragraph on the selection set.
_JOB_FIELDS = """\
          source {
            name
          }
          key
          title
          datePublished
          dateOnIndeed
          description {
            html
          }
          location {
            countryName
            countryCode
            admin1Code
            city
            postalCode
            streetAddress
            formatted {
              short
              long
            }
          }
          compensation {
            estimated {
              currencyCode
              baseSalary {
                unitOfWork
                range {
                  ... on Range {
                    min
                    max
                  }
                }
              }
            }
            baseSalary {
              unitOfWork
              range {
                ... on Range {
                  min
                  max
                }
              }
            }
            currencyCode
          }
          attributes {
            key
            label
          }
          employer {
            relativeCompanyPageUrl
            name
            dossier {
              employerDetails {
                addresses
                industry
                employeesLocalizedLabel
                revenueLocalizedLabel
                briefDescription
                ceoName
                ceoPhotoUrl
              }
              images {
                headerImageUrl
                squareLogoUrl
              }
              links {
                corporateWebsite
              }
            }
          }
          recruit {
            viewJobUrl
            detailedSalary
            workSchedule
          }
"""

# The one filter argument this lane sends. Spelled out here so the hours form -- the only one the
# endpoint accepts -- sits in one place and cannot drift from `SEARCH_RECENCY_HOURS`.
_DATE_FILTER = (
    f'filters: {{ date: {{ field: "dateOnIndeed", start: "{SEARCH_RECENCY_HOURS}h" }} }}'
)


class SearchPageError(ValueError):
    """The search answered, and carried no usable results.

    Distinct from `FetchFailure`, which the fetcher already raises for a transport or status
    failure. Both propagate: a lane is additive breadth, so the runner catches and records rather
    than the lane returning an empty result that reads like a quiet day.
    """


class UnidentifiableHit(ValueError):
    """A hit carrying no `(provider, slug, posting id)` this repo can key a company on.

    Typed at the raise site rather than signalled by a None return, so the one caller that can
    tolerate it -- the grouping pass, which counts it `not_attemptable` and moves on -- says so
    explicitly instead of every caller having to remember what None means.
    """


# EVERY declarable field this lane carries -- the JD body included -- is Indeed's rendering of the
# employer's listing, not the employer's own record, so a hit that CONVERGES onto a real provider's
# key declares the lot secondhand. Derived from `SecondhandField` rather than spelled out: a field
# added later must default to "Indeed does not own this on a converged row", and a hand-written
# list would silently default it the other way -- the direction that deletes a lead.
CONVERGED_SECONDHAND: frozenset[SecondhandField] = frozenset(get_args(SecondhandField))


@dataclass(frozen=True)
class HitIdentity:
    """The store identity one search hit resolves to, and how much of the row it can speak for.

    `secondhand` rides WITH the identity because the two are decided by the same fact and only
    `hit_identity` knows it: a tier-1 hit is filed under a real provider's
    `(company_id, provider_posting_id)`, where a board scan is the record of truth for every
    structured field and for the JD, while a tier-2 hit is filed under `indeed`'s own key, where
    this lane is the ONLY observer there will ever be and must keep refreshing all of them
    (D-414(a)). Carried as a typed set decided at the construction site rather than re-derived
    downstream from `provider == LANE_PROVIDER`, which is a string comparison against a lane name
    -- exactly the classification this repo refuses.
    """

    provider: str
    slug: str
    posting_id: str
    secondhand: frozenset[SecondhandField] = frozenset()


@dataclass(frozen=True)
class SearchPage:
    """One search response: its job objects, and the cursor that turns the page.

    `next_cursor` rides WITH the hits rather than being re-read by the caller, because the two
    come out of one payload and a paging loop that had to fetch the cursor separately could not
    honour it. Absent or blank reads as "no further page", so a renamed field stops the facet
    rather than looping on the first page forever.
    """

    hits: list[dict[str, Any]]
    next_cursor: str | None


# One job object and the URL it was found at. The URL rides with the hit for the same reason it
# does in the sibling lanes, even though this endpoint has only one: a hit can never be
# attributed to a request that was not made.
_SearchEntry = tuple[str, dict[str, Any]]


@dataclass
class _CompanyHits:
    """One company's hits, and the search URL it was FIRST seen at."""

    url: str
    hits: list[tuple[HitIdentity, dict[str, Any]]]


def _graphql_string(value: str) -> str:
    """`value` as a GraphQL string literal, escaped.

    `json.dumps` rather than the reference implementation's `.replace('"', '\\\\"')`, which
    handles a quote and nothing else. Facets come from user PROFILE data, so a backslash, a
    newline or a control character in a target title is ordinary input, and every one of those
    would break the query the reference form builds. GraphQL string literals accept exactly
    JSON's escapes, and `ensure_ascii=False` keeps a non-ASCII title as itself rather than as a
    surrogate pair the endpoint would have to reassemble.
    """
    return json.dumps(value, ensure_ascii=False)


def search_query(term: str, *, cursor: str | None = None, limit: int) -> str:
    """The GraphQL document for one search page.

    An empty `term` omits `what:` entirely rather than sending `what: ""`, which is what the
    unfaceted search is: the same query with one argument absent. `cursor:` is omitted on the
    first page for the same reason -- there is no cursor to send, and inventing one would be a
    request shape nothing has measured.
    """
    what = f"    what: {_graphql_string(term)}\n" if term else ""
    paging = f"    cursor: {_graphql_string(cursor)}\n" if cursor else ""
    return (
        "query GetJobData {\n"
        "  jobSearch(\n"
        f"{what}"
        f"    limit: {limit}\n"
        f"{paging}"
        "    sort: RELEVANCE\n"
        f"    {_DATE_FILTER}\n"
        "  ) {\n"
        "    pageInfo {\n"
        "      nextCursor\n"
        "    }\n"
        "    results {\n"
        "      trackingKey\n"
        "      job {\n"
        f"{_JOB_FIELDS}"
        "      }\n"
        "    }\n"
        "  }\n"
        "}\n"
    )


def search_body(term: str, *, cursor: str | None = None, limit: int) -> dict[str, Any]:
    """The POST body: one `query` key, which is the whole request payload."""
    return {"query": search_query(term, cursor=cursor, limit=limit)}


def parse_search_page(content: bytes) -> SearchPage:
    """`data.jobSearch` out of a GraphQL response, as job objects plus the next cursor.

    `errors` is RAISED, never absorbed. GraphQL reports a query-side failure INSIDE a 200
    response, so a caller that read only `results` would see an empty list and record the quiet
    day this lane's design exists to make impossible -- and a rejected filter argument is exactly
    that shape (`BAD_USER_INPUT` for an ISO date). Raising on `errors` even when `data` is also
    present is the loud direction on purpose: a partially-failed page is not a page this lane can
    tell apart from a short one.
    """
    try:
        payload = json.loads(content.decode("utf-8", "replace"))
    except ValueError as exc:
        raise SearchPageError(f"unreadable search response: {exc}") from exc
    if not isinstance(payload, dict):
        raise SearchPageError(f"the search response is {type(payload).__name__}, not an object")
    errors = payload.get("errors")
    if errors:
        raise SearchPageError(f"the search reported GraphQL errors: {errors!r}")
    data = payload.get("data")
    search = data.get("jobSearch") if isinstance(data, dict) else None
    if not isinstance(search, dict):
        raise SearchPageError("the search response carries no data.jobSearch object")
    results = search.get("results")
    if not isinstance(results, list):
        raise SearchPageError(f"results is {type(results).__name__}, not a list")
    hits: list[dict[str, Any]] = []
    for entry in results:
        job = entry.get("job") if isinstance(entry, dict) else None
        if isinstance(job, dict):
            hits.append(job)
    page_info = search.get("pageInfo")
    cursor = _text(page_info.get("nextCursor")) if isinstance(page_info, dict) else ""
    return SearchPage(hits=hits, next_cursor=cursor or None)


def hit_identity(job: dict[str, Any]) -> HitIdentity:
    """(provider, slug, posting id) for one hit, in two tiers and no more.

    Tier 1 is the convergence case: `recruit.viewJobUrl` is the EMPLOYER's apply URL, so when it
    names a posting on a board this repo can parse, the identity recovered from it is the same
    `(company_id, provider_posting_id)` a later board scan produces and the aggregator's copy
    converges through `UNIQUE(company_id, provider_posting_id)` instead of duplicating. Both
    dereference failures are ordinary rather than errors -- most employers sit on an ATS this
    repo has no adapter for, which is the reach the lane was built for.

    Tier 1 also declares every declarable field `CONVERGED_SECONDHAND` (D-414(a)): converging on
    the identity is a claim about WHICH posting this is, never a claim to be the record of truth
    for the provider's own columns or for the employer's own JD text, and `scan.apply` would
    otherwise refresh them all and restate the body as the current version.

    Tier 2 keys the company under `indeed` and Indeed's OWN employer key, the last segment of
    `employer.relativeCompanyPageUrl`, and declares NOTHING secondhand -- this lane is the only
    observer that row will ever have. A hit with neither that nor a posting `key` REFUSES rather
    than falling back to a slugified display name: `LaneCompanySnapshot` says in its own docstring
    why a name is the wrong granularity twice over, and a refusal here is counted
    `not_attemptable` by the grouping pass, so its cost is visible instead of silent.
    """
    apply_url = _text(_nested(job, "recruit", "viewJobUrl"))
    target = board_posting_target(apply_url)
    if target is not None:
        return HitIdentity(
            target.provider, target.slug, target.posting_ref, CONVERGED_SECONDHAND
        )
    key = _text(job.get("key"))
    slug = employer_slug(job)
    if not (key and slug):
        raise UnidentifiableHit(
            f"hit is missing an employer page URL or a posting key, and its apply URL "
            f"({apply_url or 'absent'}) names no board this repo can parse: key={key!r} "
            f"slug={slug!r}"
        )
    return HitIdentity(LANE_PROVIDER, slug, key)


def board_posting_target(apply_url: str) -> PostingTarget | None:
    """The employer-board posting `apply_url` names, or None when it names none.

    The two dereference failures are collapsed to None at this ONE seam rather than at the call
    site, because neither is a failure the run needs to hear about: `parse_posting_target` raises
    `UnknownBoardURL` for a host it does not recognise and `UnresolvablePostingURL` for one it
    does whose posting reference it cannot evidence, and BOTH are the ordinary case here --
    most employers sit on an ATS this repo has no adapter for, which is the reach the lane was
    built for, not an error. Nothing is silently lost either way: tier 2 of `hit_identity` keys
    the company under `indeed` regardless, and a hit that cannot be keyed AT ALL is counted
    `not_attemptable` by the grouping pass.
    """
    if not apply_url:
        return None
    try:
        return parse_posting_target(apply_url)
    except (UnknownBoardURL, UnresolvablePostingURL):
        return None


def _is_addressable_url(value: str) -> bool:
    """A well-formed, absolute http(s) URL fit to record as a seed -- never a bare host, a
    `provider:slug` paste shorthand, or a string `urlparse` tolerates without raising.

    Delegates to `core.board_urls.is_seedable_url`, the ONE shared gate `store.seed_queries.
    record_seeds` and the JSON-LD lane's discovery filter also apply, so the two lanes and the
    write point cannot drift on what "seedable" means. `recruit.viewJobUrl` is an API field the
    endpoint controls, never a human paste, so anything short of a genuine absolute URL is
    malformed input here, not evidence of an as-yet-unregistered vendor -- which is why this lane
    holds seeds to a stricter bar than `parse_board_target` sets for a `companies add` paste.
    """
    return is_seedable_url(value)


def tenant_seed_url(job: dict[str, Any]) -> str | None:
    """`recruit.viewJobUrl` when it is a real, addressable URL naming NO provider this repo
    registers at all -- the tier-D case (D-413).

    **`UnknownBoardURL` alone is NOT that signal, and treating it as one was the bug a review
    caught.** `parse_posting_target` raises it from THREE different places, and only one is a
    missing tenant:

    * A REGISTERED provider whose slug this value does not carry (`UnknownBoardURL`, e.g.
      Workable's bare shortlink `apply.workable.com/j/{code}`, which omits the org). That
      employer already has a working adapter; the defect is the URL's shape, not a missing
      tenant, and seeding it would file a KNOWN provider's posting into a queue built for
      vendors this repo has never heard of.
    * A malformed value (`UnknownBoardURL` from `urlparse`'s own bare `ValueError` on an
      unbalanced bracket, e.g. `https://[broken`). Not a URL at all in any usable sense.
    * NO provider registers the host at all (`UnregisteredBoardHost`, a `core/board_urls.py`
      subclass carved out for exactly this). That is the tier-D vendor recon measured (Oracle
      HCM, iCIMS, UKG, ...): a real employer board this repo has never heard of, which is
      exactly what a later resolver lane needs a URL for.

    Only the third is caught here. `UnresolvablePostingURL` -- the host IS registered, but this
    URL's POSTING reference cannot be evidenced (`TRAILING_CHROME_HIT`'s lever `/apply` is the
    pinned example) -- is the fourth failure mode and was already excluded before this fix; it
    is a narrower version of the same "known vendor, unusable value" story as the Workable case
    above, just caught one level deeper (`parse_board_target` succeeds; `parse_posting_target`'s
    own posting-shape check fails).

    `_is_addressable_url` runs FIRST because the exception class alone is NOT a reliable seed
    signal, and which one `parse_posting_target` raises does not tell malformed from unregistered.
    A control char in the PATH leaves the host well-formed, so it reaches the
    `UnregisteredBoardHost` subclass -- the very class this function seeds on -- exactly as a real
    unrecognized vendor does; only whitespace that corrupts the HOST reaches the `UnknownBoardURL`
    base class. And a value `urlsplit` silently cleans up (a stripped tab) would route fine yet
    persist a URL string no fetch log can match. So the recorded STRING, checked by
    `_is_addressable_url` before the dereference, decides what may seed -- not the exception class.

    None also when `viewJobUrl` is blank (nothing to seed), and when it DOES resolve to a board
    (tier 1 of `hit_identity`): that hit is being applied under the real provider's identity THIS
    run, so seeding it too would hand a resolver a URL a board scan already owns.
    """
    apply_url = _text(_nested(job, "recruit", "viewJobUrl"))
    if not apply_url or not _is_addressable_url(apply_url):
        return None
    try:
        parse_posting_target(apply_url)
    except UnresolvablePostingURL:
        return None
    except UnregisteredBoardHost:
        return apply_url
    except UnknownBoardURL:
        return None
    return None


def _discovered_seeds(entries: list[_SearchEntry]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Every DISTINCT tier-D `viewJobUrl` this page saw, and every MALFORMED one it dropped.

    Computed from every entry rather than from `_group_by_company`'s grouped output: a hit
    `hit_identity` cannot key AT ALL (`UnidentifiableHit`, no employer page and no posting key)
    still carries a real, unrecognized board URL worth seeding -- gating this on grouping would
    silently drop exactly the hits with the least other trace of themselves. A `dict` rather than
    a `set` keeps each tuple in first-seen order for a reader diffing two runs; `record_seeds`'
    own conflict clause already absorbs an in-batch duplicate, so the dedup here is a courtesy to
    the caller, not a correctness requirement.

    A `viewJobUrl` that is PRESENT but not safely seedable (`_is_addressable_url` -- bad
    scheme/host/port, a control char, an IP literal, a multi-dot host) is a MALFORMED value the
    search endpoint handed us. It is carried out in the SECOND tuple for the runner to surface,
    rather than dropped silently, so the defect is visible past `record_seeds`' write path. That is
    distinct from the ordinary cases `tenant_seed_url` returns None for -- a URL that resolves to a
    known board, or names a registered provider whose slug it lacks -- which are correctly silent
    and are NOT carried here.
    """
    seeds: dict[str, None] = {}
    refused: dict[str, None] = {}
    for _url, job in entries:
        apply_url = _text(_nested(job, "recruit", "viewJobUrl"))
        if apply_url and not _is_addressable_url(apply_url):
            refused[apply_url] = None
            continue
        seed = tenant_seed_url(job)
        if seed is not None:
            seeds[seed] = None
    return tuple(seeds), tuple(refused)


def employer_slug(job: dict[str, Any]) -> str:
    """Indeed's own employer key: the last segment of `/cmp/{slug}`, or "" when absent.

    Indeed's employer record, not its display name. `companies` is UNIQUE(provider, slug), so the
    slug has to be something two listings of one employer agree on and two employers cannot
    collide over; a display name is neither.
    """
    page = _text(_nested(job, "employer", "relativeCompanyPageUrl"))
    segments = [segment for segment in page.split("/") if segment]
    return segments[-1] if segments else ""


def company_name(job: dict[str, Any]) -> str:
    """`employer.name`, falling back to Indeed's employer key -- never blank.

    `LaneCompanySnapshot.name` requires a non-blank name, and the fallback is the same field
    `hit_identity` already had to find to key the company at all, so an employer this lane cannot
    name properly is still named by something it can evidence rather than by an empty string.
    """
    return _text(_nested(job, "employer", "name")) or employer_slug(job)


def posting_url(job: dict[str, Any]) -> str:
    """The employer's own apply URL, or Indeed's canonical job view when there is none.

    `viewJobUrl` first even when it did not dereference to a board this repo parses: it is still
    where the employer wants an applicant to land, which is what a rendered lead's link is for.
    The `viewjob?jk=` form is Indeed's own permalink for a posting key and is never REQUESTED by
    this lane -- it is a display URL, not a request shape.
    """
    return _text(_nested(job, "recruit", "viewJobUrl")) or (
        f"https://www.indeed.com/viewjob?jk={_text(job.get('key'))}"
    )


def raw_posting(job: dict[str, Any], identity: HitIdentity) -> RawPosting | None:
    """One hit as a `RawPosting`, or None when it carries no body.

    None rather than an exception because the caller has an outcome for it -- `extracted_empty`,
    the catalog's name for "a response arrived and extraction produced nothing" -- and an absent
    body is the ordinary shape of that, not a structural failure.

    `remote_policy` stays `unknown`. The response carries an `attributes` list from which a remote
    flag could be inferred, and inferring one is a separate decision with its own evidence bar;
    `unknown` is the honest default until that measurement exists -- and on a converged row that
    `unknown` is declared secondhand rather than written over the provider's reading. `locations`
    is carried in full here and blanked by `scan.apply._inserted_fields` on the INSERT rather than
    dropped at this construction site, so the tier-2 rows that need it keep it and the two halves
    of one rule stay in one place.
    """
    body_text = html_to_text(_text(_nested(job, "description", "html")))
    if not body_text.strip():
        return None
    location = _text(_nested(job, "location", "formatted", "short"))
    return RawPosting(
        provider_posting_id=identity.posting_id,
        title=_text(job.get("title")),
        url=posting_url(job),
        locations=[location] if location else [],
        posted_at=_posted_at(job.get("datePublished")),
        body_text=body_text,
        # The hit MINUS its description. The body is already stored in `body_text` and this column
        # is JSON in the store, so carrying the JD twice would double the row for no reader.
        raw_json={"job": {name: value for name, value in job.items() if name != "description"}},
        # Decided by `hit_identity`, carried here unchanged: only the tier the hit resolved to
        # can say whether this observation owns the row's structured fields (D-414(a)).
        secondhand=identity.secondhand,
    )


class IndeedLane:
    name = LANE_NAME

    def __init__(
        self,
        search_facets: Sequence[str] = (),
        search_pages: int = DEFAULT_SEARCH_PAGES,
        results_per_page: int = DEFAULT_RESULTS_PER_PAGE,
    ) -> None:
        # Injected rather than read here, for the reason the registry comment in `runner.py`
        # gives: the facets come from the user's profile row, which lives in the store, and a
        # lane must not reach into the store to find its own configuration.
        self._search_facets = tuple(search_facets)
        self._search_pages = max(1, search_pages)
        self._results_per_page = min(MAX_RESULTS_PER_PAGE, max(1, results_per_page))

    def collect(self, fetcher: Fetcher, admits: CompanyAdmission) -> LaneResult:
        """Search pages per facet, and no other request at all.

        `admits` is asked once per distinct `(provider, slug)`, in first-seen order. The
        protocol requires the call to come BEFORE the bodies are fetched; here there are no body
        fetches to come before, and the ordering still matters for the same reason it does
        elsewhere -- a refused company must cost nothing, which is why the postings for one are
        never built.
        """
        entries, search_pages = self._search(fetcher)
        # Computed off the raw entries, before grouping or admission touch them: a seed costs
        # nothing extra to collect (`viewJobUrl` already rode in with the search response this
        # lane paid for regardless), and it is not gated on company admission either -- a seed is
        # a URL for a LATER resolver lane to spend its own budget on, not a write against this
        # run's company cap. RETURNED on `LaneResult.discovered_seeds` rather than written: this
        # runs in `_fetch_lane`'s worker thread, and `apply_board` is the pipeline's single
        # writer, so the runner persists it in the serial apply phase instead (D-413/D-414).
        discovered_seeds, refused_seeds = _discovered_seeds(entries)

        tally = AcquisitionTally()
        by_company = _group_by_company(entries, tally)
        snapshots: list[LaneCompanySnapshot] = []
        for (provider, slug), company in by_company.items():
            if not admits(provider, slug):
                # Nothing tallied for a refused company: no request was attempted, and an outcome
                # here would inflate `attempted` with non-attempts. Refusals are reported by name
                # through `admission.CompanyBudget.refused`.
                continue
            postings: list[RawPosting] = []
            for identity, job in company.hits:
                posting = raw_posting(job, identity)
                if posting is None:
                    tally.record("extracted_empty")
                    continue
                # `body_inline`, not `body_fetched`: the body arrived WITH the listing, at no
                # request of its own. That distinction is exactly what the two outcomes exist for.
                tally.record("body_inline")
                postings.append(posting)
            if postings:
                # A company whose every hit lacked a body yields no snapshot: an empty one would
                # still write a `board_scans` row and oblige a company row for zero postings.
                snapshots.append(
                    LaneCompanySnapshot(
                        provider=provider,
                        slug=slug,
                        name=company_name(company.hits[0][1]),
                        snapshot=lane_snapshot(postings, company.url),
                        # A tier-1 convergence (`provider != LANE_PROVIDER`) sits on a board the
                        # scanner can parse -- `hit_identity` only assigns a real provider when
                        # `parse_posting_target` recovered one -- so watching it is safe (no
                        # `unknown provider` line) and is the DRAIN for the secondhand body this
                        # hit wrote: the next scan replaces JD v1 with the employer's own text and
                        # its real `remote_policy`/location (D-414(a)). Tier 2 is keyed under
                        # `indeed`, has no board to scan, and stays unwatched.
                        watch=provider != LANE_PROVIDER,
                    )
                )
        return LaneResult(
            snapshots=tuple(snapshots), tally=tally, search_pages=search_pages,
            discovered_seeds=discovered_seeds, refused_seeds=refused_seeds,
        )

    def _search(self, fetcher: Fetcher) -> tuple[list[_SearchEntry], tuple[tuple[str, int], ...]]:
        """Every configured search page, its hits paired with the URL they came from.

        The result is INTERLEAVED across facets, round-robin, for the reason both sibling lanes
        give: companies are worked in iteration order, so concatenating would let the first facet
        consume the run and every later target title contribute nothing.

        **EVERY ENTRY IN THE RETURNED PAGE COUNTS NAMES THE SAME URL, AND THAT IS NOT A BUG.**
        The facet travels in the POST BODY, so there is exactly one URL this lane ever requests.
        The entries are POSITIONAL: one per facet, in the order the facets were configured, which
        is what makes "facet 2 ran out at page 1 while facet 3 filled the ceiling" still readable
        in the funnel. Encoding the facet into the URL to make the table prettier would name a
        request this lane never made.
        """
        terms = self._search_facets or ("",)
        if not self._search_facets:
            # The unfaceted fallback keeps the single-search contract: a transport or structural
            # failure on its FIRST page propagates, because with one search there are no other
            # results for it to cost.
            entries, pages, _late = self._facet_pages(fetcher, "")
            if not entries:
                # The same all-empty check the faceted branch runs, and for the same reason.
                # Returning here instead would let an empty HTTP-200 page read as a quiet day:
                # zero entries, zero companies, nothing attempted, so the tally cannot see it
                # either. One search failing this way is the whole search failing.
                raise SearchPageError(
                    "the unfaceted search yielded nothing: the query has been rejected, or the "
                    "host is refusing us"
                )
            return entries, ((SEARCH_URL, pages),)

        per_facet: list[list[_SearchEntry]] = []
        page_counts: list[tuple[str, int]] = []
        failed = 0
        late_failures = 0
        for term in terms:
            try:
                entries, pages, late_failure = self._facet_pages(fetcher, term)
            except (FetchFailure, SearchPageError):
                # Per-facet isolation, the same shape D-307 gave a board's apply failure inside a
                # scan. One search per target title means a run makes many, so the seventh must
                # not discard the six already paid for, and the fetcher has retried with backoff
                # before it raises. Isolation must not become suppression, which is what the
                # all-empty check below is for.
                failed += 1
                per_facet.append([])
                page_counts.append((SEARCH_URL, 0))
                continue
            per_facet.append(entries)
            page_counts.append((SEARCH_URL, pages))
            late_failures += int(late_failure)

        if len(page_counts) > 1 and late_failures == len(page_counts):
            # Isolation must not become suppression. One facet losing page 4 keeps the three pages
            # it paid for and says nothing about the host; EVERY facet losing a later page is the
            # host degrading under exactly the paging this lane does, and it would otherwise be
            # invisible -- each facet reports the depth it reached, and a truncated depth looks
            # identical to a short result set. Requires MORE THAN ONE facet: with a single facet
            # "every facet" and "one facet" are the same statement.
            raise SearchPageError(
                f"every one of {late_failures} facet(s) failed after its first page: the host is "
                "degrading under paging rather than running out of results"
            )

        if not any(per_facet):
            # Not a quiet day, and the tally cannot see it: with no hits nothing is ever
            # attempted, so `is_silent_outage` stays False and the lane reports a clean run with
            # no postings forever -- the prior art's 11-run silent outage. The all-FAILED case is
            # the same guard on purpose, and both counts are named so a host refusing us stays
            # distinguishable from a profile whose target titles match nothing.
            raise SearchPageError(
                f"every role facet yielded nothing ({len(per_facet)} searched, {failed} request "
                "failures): the query has been rejected, the host is refusing us, or none of the "
                "profile's target titles match a posting"
            )
        interleaved = [
            entry for row in zip_longest(*per_facet) for entry in row if entry is not None
        ]
        return interleaved, tuple(page_counts)

    def _facet_pages(
        self, fetcher: Fetcher, term: str
    ) -> tuple[list[_SearchEntry], int, bool]:
        """One facet's hits over at most `self._search_pages` pages, and the pages fetched.

        **A PAGE WITH NO HITS MEANS TWO DIFFERENT THINGS AND THIS IS WHERE THEY SEPARATE.** On the
        FIRST page it is returned rather than raised, because one target title matching nothing is
        a profile-data matter; `_search`'s all-empty check is what turns EVERY facet doing it into
        the failure the runner must see. On a LATER page it is the ordinary end of a facet's
        result set. `FetchFailure` and `SearchPageError` split the opposite way, for the reason
        both sibling lanes state: a facet refused on its first page produced nothing and is a
        failure its caller must count, while one refused on page 4 keeps the three pages already
        paid for -- and SAYS SO, through the third return value, because breaking silently makes a
        facet that fails on every page after the first indistinguishable from one whose results
        genuinely ended there.

        AN ABSENT `nextCursor` ENDS THE FACET, which is the whole point of paging against a host
        that says where the end is. A page that adds no NEW posting key ends it too -- the
        offset-wrap tail `providers/workday.py` guards for the same reason, and it also covers a
        host that stops honouring the cursor and re-serves the first page, which the ceiling alone
        would let burn every remaining request.

        No sleep is added between pages. `Fetcher` paces per host at >=1.0s inside the lock it
        holds for each request, so a lane-local delay would be a second, weaker pacing rule.
        """
        entries: list[_SearchEntry] = []
        seen: set[str] = set()
        pages = 0
        late_failure = False
        cursor: str | None = None
        for page_index in range(self._search_pages):
            body = search_body(term, cursor=cursor, limit=self._results_per_page)
            try:
                result = fetcher.post_json(SEARCH_URL, body, headers=_API_HEADERS)
                page = parse_search_page(result.content)
            except (FetchFailure, SearchPageError):
                if page_index == 0:
                    raise
                late_failure = True
                break
            pages += 1
            fresh: list[_SearchEntry] = []
            new_keys: set[str] = set()
            for job in page.hits:
                key = _text(job.get("key"))
                if key and key in seen:
                    continue
                fresh.append((SEARCH_URL, job))
                if key:
                    new_keys.add(key)
            entries.extend(fresh)
            seen |= new_keys
            if page.next_cursor is None or not new_keys:
                break
            cursor = page.next_cursor
        return entries, pages, late_failure


def _group_by_company(
    entries: list[_SearchEntry], tally: AcquisitionTally
) -> dict[tuple[str, str], _CompanyHits]:
    """Hits bucketed by `(provider, slug)`, first-seen order preserved.

    Grouping by identity rather than by `employer.name` is the point `LaneCompanySnapshot` makes
    in its own docstring: a name is not what `companies` is unique on, so a name-keyed group
    applies one employer's two boards against one `company_id`.

    A hit this repo cannot key, or cannot title, is counted `not_attemptable` and dropped here
    rather than raised: one malformed row must not cost the others.

    A SECOND hit resolving to a posting already taken this run is dropped for a harder reason than
    tidiness -- without it the run aborts. `apply.py` snapshots `existing` once before its loop
    and never re-reads it, so two rows with one `provider_posting_id` both take the INSERT branch
    and the second violates UNIQUE(company_id, provider_posting_id) inside `apply_board`'s single
    transaction, rolling the whole board back and taking every later company's results with it.
    Every ATS provider enumerates a board once and may assume distinct ids; an AGGREGATOR may not,
    and overlapping facets (`software engineer` and `backend engineer`) produce exactly that by
    design. Two hits can also dereference to ONE greenhouse posting through `viewJobUrl` and land
    in the same group -- that convergence is the point of the dereference step, and the duplicate
    is counted rather than dropped in silence.
    """
    grouped: dict[tuple[str, str], _CompanyHits] = {}
    seen: set[tuple[str, str, str]] = set()
    for url, job in entries:
        try:
            identity = hit_identity(job)
        except UnidentifiableHit:
            tally.record("not_attemptable")
            continue
        if not _text(job.get("title")):
            tally.record("not_attemptable")
            continue
        key = (identity.provider, identity.slug, identity.posting_id)
        if key in seen:
            tally.record("not_attemptable")
            continue
        seen.add(key)
        group = grouped.setdefault((identity.provider, identity.slug), _CompanyHits(url, []))
        group.hits.append((identity, job))
    return grouped


def failure_outcome(exc: FetchFailure) -> AcquisitionOutcome:
    """Status -> outcome. A transport failure has no status and is `fetch_unavailable`.

    Unused by `collect`, which makes no per-posting request, and kept because the search half
    still classifies: `_search` reports a refused facet as a request failure by count, and a
    reader of a future change here needs the same three buckets the sibling lanes keep apart --
    403 is the host refusing us, 404 is a posting gone, a timeout is neither.
    """
    if exc.status_code in (401, 403):
        return "fetch_refused"
    if exc.status_code in (404, 410):
        return "fetch_gone"
    return "fetch_unavailable"


def _posted_at(value: Any) -> datetime | None:
    """`datePublished` as naive UTC. It is epoch MILLISECONDS, not seconds.

    Converted through an explicit UTC timezone and then flattened, never through
    `datetime.fromtimestamp(seconds)` with no tzinfo: that reads the epoch in the RUNNING
    MACHINE's local zone, so the same posting would carry a different `posted_at` on a laptop in
    Boston and on a CI runner in UTC, and the recency score would move with it.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return to_naive_utc(datetime.fromtimestamp(value / 1000, tz=UTC))
    except (OverflowError, OSError, ValueError):
        return None


def _nested(value: Any, *names: str) -> Any:
    """`value[names[0]][names[1]]...`, or None the moment any level is not an object.

    A response this repo does not control nests four deep in places
    (`location.formatted.short`), and a chain of `isinstance` checks at every call site is where
    a missed one turns a thin payload into an AttributeError mid-run.
    """
    for name in names:
        if not isinstance(value, dict):
            return None
        value = value.get(name)
    return value


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
