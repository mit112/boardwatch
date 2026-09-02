"""Lane 5: the `schema.org/JobPosting` resolver -- one lane in place of six vendor adapters.

One request shape, and no others:

    GET <a posting URL from a seed>    -- the body is IN the page, as JSON-LD

Plus the two GitHub new-grad list GETs this lane's discovery half already shares with
`lanes/github_lists.py`. **No key, no cookie, no TLS bypass, no app impersonation**, and the
`identifying_user_agent()` every board that answers us honestly is owed under D22.

WHY A RESOLVER AND NOT SIX ADAPTERS. Six unrelated vendors -- Hireology, CareerPlug, JazzHR
(`applytojob`), Breezy, Paylocity and iCIMS on a CUSTOM domain -- were measured on 2026-09-01
serving a complete `JobPosting` with a full `description` on the posting page itself, from one
unauthenticated GET (recon §3.2: 9,718 / 8,109 / 5,410 / 4,971 / 7,103 / 2,665 chars). Every one
of them is per-tenant with no cross-tenant search, so an adapter for each would be six search
surfaces that cannot be searched. What they share is the OUTPUT format, so the lane takes a
posting URL from any origin and reads the vendor-neutral half, with a closed per-vendor catalog
for the two facts JSON-LD does not carry: which employer this is, and which posting.

**THE BODY ARRIVES IN THE SAME REQUEST, BUT IT IS TALLIED `body_fetched`, NOT `body_inline`.**
`body_inline` means "at no extra request" -- hiring.cafe earns it because ONE board GET buys
every body at that company. Here the ratio is one GET per posting against a URL some other pass
discovered, which is exactly what `body_fetched` names: "a body arrived from a second request
against a resolvable posting URL". Recording the cheaper outcome would understate this lane's
per-posting cost in the one report that exists to show it.

---

## The seed, which is what decides whether this lane is worth anything

An adapter is only half a lane; the other half is where the tenant comes from. This lane reads
two seed sources and owns neither:

* **The two GitHub new-grad lists**, via `github_lists.fetch_listings` unchanged. That module
  fetches them, parses `(provider, slug)` COMPANIES out of them and **throws the posting URLs
  away** -- its docstring says so, because for the six real providers a posting URL is a company
  discovery problem. For a tier-D vendor it is not: there is no board to scan, so the posting URL
  is the only thing that exists. **This does not touch D-291.** That ruling is that a human sits
  between a public list and what the machine WATCHES, because a bad slug becomes a permanently
  failing board; it is about `watched=1` and `companies import`. Resolving a posting URL to the
  body the employer published at it is a different act, and it is the one `lanes/hiringcafe.py`
  already performs on `apply_url` every run. Nothing here sets `watched`.
* **`lane_seeds`**, the durable handoff, read through `LaneContext.pending_seeds`. A discovering
  lane records a URL it cannot resolve; this lane drains it. Today the Indeed lane's
  `recruit.viewJobUrl` is the intended filler, and it is a different lane in a different stage
  pass, which is why the handoff has to survive the run. **The read is filtered to this lane's
  own hosts** because the queue is shared and its ordering is global: an unfiltered draw of forty
  takes the forty oldest rows in the table whoever can resolve them, so a vendor with few seeds
  starves behind a vendor with many, and an attempt gets charged against a seed belonging to a
  resolver that does not exist yet. Neither failure is visible in a report; both look like a full
  budget and a clean tally. `seed_hosts()` builds that set and records, at its own site, the one
  thing an exact-hostname filter cannot express for a wildcard-subdomain vendor.

**DISCOVERY WRITES; THE DRAIN RESOLVES. A URL FOUND THIS RUN IS RESOLVED NEXT RUN.** One run of
latency, taken deliberately in exchange for one resolve path instead of two. The alternative --
resolving fresh URLs directly as well as draining stored ones -- needs a second dedup rule for
the fresh half, because a fresh URL this lane already resolved three runs ago is indistinguishable
from a new one without asking the store. `lane_seeds` IS that dedup: `resolved_at` is never
cleared, so a resolved seed can never re-enter the candidate set. Two paths would mean the fresh
one re-fetches, every run, forever, every posting the lane has ever delivered.

**THIS LANE SEEDS ONLY WHAT IT CAN ITSELF RESOLVE.** The lists carry 793 `*.icims.com` URLs, and
recording them would be a bucket with no drain -- rows nothing can resolve, occupying the ordered
candidate set that a real seed has to come through. Widening the discovery filter belongs to
whichever lane can resolve the rest. The DRAIN is deliberately not filtered the same way: seeds
arrive from other lanes under their own policy, so an out-of-catalog seed is an ordinary input
here, refused without a request and charged an attempt so that it ages out.

---

## The two numbers this lane must choose, and what they are sized against

MEASURED per-posting cost (recon §3.2): one GET, ~0.3-0.6 s. `Fetcher` adds its own per-host
floor of >=1.0 s, held inside the per-host lock for the request's full duration, so the real cost
of a seed is ~1.0-1.6 s of paced network work -- pacing-dominated, not fetch-dominated.

`SEED_MAX_ATTEMPTS = 3`. A dead URL costs exactly three GETs (~4.5 s) over its whole lifetime and
then leaves the candidate set for good. One would drop a real posting on a single transient 5xx,
which the fetcher's own tenacity backoff cannot always absorb inside one run; ten would spend ten
runs' budget slots on a URL that 404'd on day one, and **404 is the measured fate of a tier-D
miss, not a rare one** -- of the eight vendor URLs the recon re-probed, the two Paylocity ones and
both Jobvite ones had already closed. Three is two chances after the first failure, which is what
a daily lane needs to cross a weekend outage.

`SEED_REQUEST_BUDGET = 40`. Forty GETs at ~1.0-1.6 s is ~40-64 s of paced network work per run --
the same order as the hiring.cafe lane's 60-request ceiling, and small beside the ~166 requests
run 139 measured for the LinkedIn lane. MEASURED seed supply from the two lists today is 88
catalog-matching ACTIVE URLs (JazzHR 70, iCIMS-custom 17, Breezy 1), so 40 drains the standing
backlog in three runs and thereafter tracks the daily delta, which is far smaller.

`SEED_SCAN_LIMIT = 400`, ten times the request budget, and it is not a second budget. Reading a
seed row is a cheap indexed SELECT; REQUESTING one is the cost. Scanning wide is what lets an
out-of-catalog seed be refused without spending a request slot, so a `lane_seeds` table that is
90% URLs this lane cannot resolve still fills all forty request slots with ones it can.

A refusal by the company cap is NOT charged an attempt, and that is the one asymmetry here: the
cap deferred that company, it did not try it, and charging would age a seed out of the queue for
being unlucky three times. Every other non-resolution -- out of catalog, owned by a real provider,
fetch failed, body rejected -- IS charged, because the seed had its turn.

---

## Posture, per host, quoted

```
careers.hireology.com/robots.txt   HTTP 404      (no directive)          <- fetched 2026-09-01
careers.garmin.com/robots.txt      HTTP 200      "User-agent: *"         <- fetched 2026-09-01
                                                 "Allow: /"
                                                 "Sitemap: http://careers.garmin.com/sitemap.xml"
                                                 "crawl-delay: 5"
*.applytojob.com/robots.txt        "User-agent: SemrushBot / User-agent: dotbot / Disallow: /"
                                   "User-agent: * / Disallow: /cb"       <- /apply/ is ALLOWED
*.breezy.hr/robots.txt             "User-Agent: * / Disallow: /css /fonts /stylesheets
                                    /javascripts"                        <- /p/ is ALLOWED
*.careerplug.com                   (recon §3.2: clean, HTTP 200 on the posting itself)
```

The two the recon left as "not fetched -- record before shipping" were fetched, one request each,
and are the first two rows. **`careers.garmin.com` declares `crawl-delay: 5`, which is STRICTER
than the fetcher's >=1.0 s floor**, so this lane tops it up per host. `lanes/hiringcafe.py`
refuses a lane-local delay and is right to: its host's floor is already the stricter of the two.
The direction is what matters, not the principle -- a second, WEAKER pacing rule is a bug, and a
declared directive the shared pacer does not know about is a rule that has to be honoured
somewhere.

## What is deliberately NOT in the catalog, and why each is a refusal rather than an omission

* **iCIMS on `*.icims.com`.** `career-schwab.icims.com/robots.txt` is exactly `User-agent: *` /
  `Disallow: /`. **OWNER-DECLINED -- do not build it.** It is 793 URLs in the lists and 3 gate-1
  postings, and none of them is reachable from here. iCIMS on a CUSTOM domain is a different host
  with a different posture and IS in the catalog, per host, once that host's `robots.txt` has been
  fetched and quoted above.
* **Paylocity**, though its JSON-LD is clean and was measured at 7,103 chars.
  `recruiting.paylocity.com/Recruiting/Jobs/Details/{id}` carries NO tenant -- the employer is
  knowable only from `hiringOrganization.name` in the body, which is to say only AFTER the
  request. `Lane.collect` requires `admits` to be asked once per `(provider, slug)` BEFORE any
  body is fetched, and there is no identity to ask about. The measured cost of the exclusion is
  ZERO gate-1 postings: the one Paylocity posting in the miss set (Bectran) is `active: false` in
  the lists AND its URL was measured redirecting to `JobNotFound`. Ten live list URLs are given up
  with it. Re-admit it when a tenant is recoverable from the URL, not by keying a company on a
  display name.
* **Jobvite.** Its `description` was measured at **87,545 chars -- the whole rendered page,
  base64 images and all, not a JD**. Its two miss URLs 404. A catalog entry would ship a lane
  whose body for that vendor is a page dump into the frozen JD that every `INELIGIBLE` span is
  quoted from.

An out-of-catalog URL is refused and counted, never fetched and never guessed at: a resolver that
followed any URL handed to it would be a general-purpose web fetcher whose posture nobody has
reviewed, which is the opposite of what a closed catalog is for.

---

## The field mapping, and the four traps in it that were MEASURED rather than assumed

1. **`identifier` IS NOT THE POSTING ID. Parse the URL.** On Hireology the page at
   `.../hireology2/2855936/description` carries `identifier.value == 2855935` -- an integer, and
   **off by one from its own URL**. It is absent outright on Paylocity, Breezy and Garmin/iCIMS,
   and on JazzHR (which carries `uniqueJobCode` instead). A posting id that disagrees with the URL
   it came from collides on `UNIQUE(company_id, provider_posting_id)` and overwrites a real body
   as a revision, so the URL -- the thing that was actually requested -- is the only source used.
2. **CareerPlug's `description` is HTML-ESCAPED HTML inside the JSON string** (`&lt;div
   class=&quot;benefits&quot;&gt;`): 151 escaped tags and ZERO real ones. One `html_to_text` pass
   yields the MARKUP AS TEXT -- 6,493 characters of `<div><strong>Benefits:</strong>` that clears
   the quality floor comfortably and would be stored as the frozen JD. `_description_html`
   unescapes exactly once, on the closed condition that the value carries `&lt;` and no `<` at
   all.
3. **The JD is split across three properties on iCIMS.** Garmin's `description` is 2,665 chars and
   its `responsibilities` and `qualifications` are separate HTML fields carrying the Essential
   Functions and the Basic Qualifications -- which is to say the exact spans a years-of-experience
   or education rule has to quote. `_BODY_PROPERTIES` is the closed, ordered list; the same page
   writes the literal string `UNAVAILABLE` into four other properties, so that sentinel is
   refused rather than concatenated.
4. **`datePosted` was measured in four formats** -- `2026-08-26`, `2026-08-28T17:41:41+00:00`,
   `2026-08-28T20:50:00+0000` and `2026-08-28T14:12:10-05:00` -- and `datetime.fromisoformat`
   parses all four on this project's Python. Pinned as literals in the suite rather than trusted,
   because "the stdlib handles it" is a claim about an interpreter version.

`hiringOrganization` was MEASURED absent on MetLife and MEASURED as a bare STRING on Jobvite, so
both shapes are read and the fallback is the tenant host -- as `lanes/hiringcafe.py` falls back to
`board_token`, and for the same reason: `LaneCompanySnapshot.name` requires something evidenced,
never a placeholder. `jobLocation` was MEASURED as a dict on Garmin and a LIST on Jobvite.

**THE SEED IS DEREFERENCED BEFORE THE CATALOG IS CONSULTED.** If `parse_board_target` /
`parse_posting_target` resolves the URL to one of the six real providers, that provider owns it
and this lane does not file it -- the #304 hiring.cafe pattern, and what keeps an aggregator's
copy converging onto the board scan's row through `UNIQUE(company_id, provider_posting_id)`
instead of duplicating it under a lane-invented provider name.
"""

from __future__ import annotations

import html
import json
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from selectolax.parser import HTMLParser

from boardwatch.core.board_urls import UnknownBoardURL
from boardwatch.core.clock import to_naive_utc
from boardwatch.core.models import RawPosting
from boardwatch.core.politeness import Fetcher, FetchFailure, identifying_user_agent
from boardwatch.lanes.base import (
    CompanyAdmission,
    LaneCompanySnapshot,
    LaneResult,
    lane_snapshot,
)
from boardwatch.lanes.dereference import UnresolvablePostingURL, parse_posting_target
from boardwatch.lanes.github_lists import fetch_listings
from boardwatch.lanes.outcomes import AcquisitionOutcome, AcquisitionTally
from boardwatch.lanes.quality import assess_body
from boardwatch.store.seed_queries import SeedReader, seed_host

LANE_NAME = "jsonld"

# See the module docstring for what each is sized against. All three are module constants rather
# than `Settings` fields: an operator has no measurement this lane does not already state, and an
# unrequested knob on a request budget is a way to spend one without meaning to.
SEED_MAX_ATTEMPTS = 3
SEED_REQUEST_BUDGET = 40
SEED_SCAN_LIMIT = 400




@dataclass(frozen=True)
class Vendor:
    """One vendor this lane may request, and the two facts JSON-LD does not carry.

    `path` must FULLMATCH the URL's path with the leading and trailing slashes stripped, and it
    supplies the `id` group -- and, when the tenant lives in the path rather than the host, the
    `tenant` group. A closed rule per vendor rather than a shared "last segment" heuristic,
    because the measured shapes disagree: JazzHR's id is the FIRST path segment under `/apply`
    and its last segment is a title slug, Breezy's is a hex token glued to a title slug inside one
    segment, and iCIMS-custom's is followed by nothing but may be preceded by `careers-home`.

    `crawl_delay_seconds` is a directive THIS HOST DECLARES that is stricter than the fetcher's
    own >=1.0 s per-host floor. None means the shared pacer is already at least as strict, which
    is the case for every vendor here except one.
    """

    provider: str
    # An exact hostname, or a `.suffix` matched against the end of the host when the vendor gives
    # every tenant its own subdomain.
    host: str
    path: re.Pattern[str]
    # True when the tenant IS the subdomain (`{tenant}.careerplug.com`). False means the slug
    # comes from the `tenant` group when the pattern has one, and from the whole host when it does
    # not -- an iCIMS custom domain IS the tenant, one host per employer.
    tenant_is_subdomain: bool
    crawl_delay_seconds: float | None = None


# THE CLOSED CATALOG. Every pattern below is derived from URLs MEASURED in the two GitHub lists on
# 2026-09-01 or from the recon's own probe set, and the counts are the ACTIVE records each shape
# was seen on. A vendor absent from here is refused without a request; see the module docstring
# for the three refusals that are deliberate and what each costs.
VENDORS: tuple[Vendor, ...] = (
    # `careers.hireology.com/{tenant}/{id}/description`. One host serves every tenant, so the
    # tenant is the FIRST path segment and not the subdomain. Zero seeds in the lists today; kept
    # because the vendor is measured clean and `lane_seeds` is the seed source it is waiting on.
    Vendor(
        provider="hireology",
        host="careers.hireology.com",
        path=re.compile(r"(?P<tenant>[^/]+)/(?P<id>\d+)/description"),
        tenant_is_subdomain=False,
    ),
    # `{tenant}.careerplug.com/jobs/{id}`. Zero seeds in the lists today, same reasoning.
    Vendor(
        provider="careerplug",
        host=".careerplug.com",
        path=re.compile(r"jobs/(?P<id>\d+)"),
        tenant_is_subdomain=True,
    ),
    # `{tenant}.applytojob.com/apply/{code}/{title-slug}` -- 68 active list records -- and
    # `{tenant}.applytojob.com/{code}/{title-slug}` -- 2. BOTH shapes ship: the second is not a
    # variant of the first with a segment missing, it is the same posting reference at a different
    # position, and reading the last segment on either would key the company on a title slug.
    Vendor(
        provider="jazzhr",
        host=".applytojob.com",
        path=re.compile(r"(?:apply/)?(?P<id>[A-Za-z0-9]+)/[^/]+"),
        tenant_is_subdomain=True,
    ),
    # `{tenant}.breezy.hr/p/{id}[-{title-slug}][/apply]`. The id is the hex run before the first
    # hyphen INSIDE one segment. The trailing `/apply` is admitted rather than refused, which is
    # the opposite of what `lanes/dereference.py` does for lever and ashby -- and the difference
    # is positional, not a relaxation: there the reference is the LAST segment, so `apply` would
    # BE the reference and every posting at one employer would collide on it. Here the id is at a
    # fixed position under `/p/`, so a trailing chrome segment cannot be mistaken for it. The one
    # active Breezy record in the lists today carries exactly that suffix.
    Vendor(
        provider="breezy",
        host=".breezy.hr",
        path=re.compile(r"p/(?P<id>[0-9a-f]+)(?:-[^/]*)?(?:/apply)?"),
        tenant_is_subdomain=True,
    ),
    # iCIMS on a CUSTOM domain, one host per employer, so the HOST is the tenant. Per host, and
    # only once that host's own `robots.txt` has been fetched and quoted in the module docstring:
    # posture is a property of a host, and `*.icims.com` -- a different host, `Disallow: /`, and
    # owner-declined -- is the proof that it does not travel with the vendor. `/jobs/{id}` (14
    # active) and `/careers-home/jobs/{id}` (1) are both measured; the `?icims=1` marker rides in
    # the query and is not part of the path.
    Vendor(
        provider="icims",
        host="careers.garmin.com",
        path=re.compile(r"(?:careers-home/)?jobs/(?P<id>\d+)"),
        tenant_is_subdomain=False,
        # Quoted from the host's own robots.txt, fetched 2026-09-01: `crawl-delay: 5`.
        crawl_delay_seconds=5.0,
    ),
)

# The half of this lane's host filter that is knowable ahead of time, DERIVED from the catalog
# rather than written out a second time -- two spellings of one set is how a vendor joins the
# catalog and never the query, and that failure is silent in the worst direction: a seed this
# lane can resolve, sitting in the queue, never selected.
#
# **ONLY THE FIXED-HOST VENDORS CAN BE LISTED HERE, AND THAT IS A REAL LIMIT, NOT A TIDY-UP.**
# `unresolved_seeds` matches `lane_seeds.host` with `IN (...)` over FULL hostnames, and three of
# the five vendors give every employer its own subdomain -- `{tenant}.careerplug.com`,
# `{tenant}.applytojob.com`, `{tenant}.breezy.hr`. There is no finite set to enumerate for those,
# so their hosts are contributed per run by `seed_hosts()` below, from the tenants this lane's
# own discovery pass just saw. See that function for what the arrangement cannot reach.
FIXED_SEED_HOSTS: frozenset[str] = frozenset(
    vendor.host for vendor in VENDORS if not vendor.host.startswith(".")
)


def seed_hosts(discovered: tuple[str, ...]) -> frozenset[str]:
    """The host set this lane hands `pending_seeds`: its fixed hosts plus this run's tenants.

    **THE GAP THIS LEAVES IS STATED RATHER THAN HIDDEN.** A wildcard vendor's tenant host is
    knowable only from a URL that names it, so this lane can ask for exactly the tenants its own
    discovery pass found. That covers 100% of what it discovers itself -- the two public lists are
    re-read every run, so a tenant seeded in one run is still named in the next -- and it covers
    NOTHING that another lane discovers on a tenant this lane has never seen. When the Indeed
    lane's `recruit.viewJobUrl` starts filling `lane_seeds`, its JazzHR, CareerPlug and Breezy
    tenants will be invisible here until the same employer also appears in the public lists.

    The fix is a contract change, not a workaround in this module: either `lane_seeds` carries the
    registrable domain beside the host, or the filter matches by suffix. Faking it here -- reading
    a wider host set and discarding what does not match -- would charge attempts against seeds
    belonging to resolvers that do not exist yet, which is the exact failure `hosts` was added to
    prevent.
    """
    return FIXED_SEED_HOSTS | {seed_host(url) for url in discovered}

# The JD, in the order a reader would meet it on the page. CLOSED: schema.org defines a dozen
# further text properties and the measured pages fill them with sentinels, page chrome or
# nothing. `description` alone is what the recon's mapping table specifies and is right for five
# of the six vendors; iCIMS is the one that splits, and dropping its two extra properties would
# drop the Basic Qualifications block -- the spans an eligibility rule has to quote.
_BODY_PROPERTIES: tuple[str, ...] = ("description", "responsibilities", "qualifications")

# The literal a measured page writes into a property it has nothing for. Garmin fills FOUR
# (`skills`, `industry`, `workHours`, `educationRequirements`) with it, so a `qualifications` that
# said the same would concatenate the word UNAVAILABLE into a job description.
_UNAVAILABLE = "UNAVAILABLE"

# A tag, for the double-escape test. `<` followed by a letter or a slash: bare `<` in prose ("<5
# years") must not read as markup, or an ordinary JD would be unescaped a second time.
_TAG_RE = re.compile(r"<[A-Za-z/]")


class NoJobPosting(ValueError):
    """A 200 that carries no `schema.org/JobPosting` block this lane can read.

    Typed at the raise site rather than signalled by None, because the caller has an outcome for
    it -- `extracted_empty`, "a response arrived and extraction produced nothing substantive" --
    and every other caller would otherwise have to remember what None meant.
    """


class UnsupportedSeedURL(ValueError):
    """A seed URL outside the closed vendor catalog, or one a real provider owns.

    Both are ordinary inputs, not failures: seeds arrive from lanes with their own discovery
    policy, and most of what they find is not this lane's to resolve. Refused BEFORE any request,
    which is the whole value of keying the catalog on the URL.
    """


@dataclass(frozen=True)
class SeedPosting:
    """One seed resolved to a store identity, entirely from its URL. No request has been made."""

    vendor: Vendor
    slug: str
    posting_id: str
    url: str
    seed_id: int


def _host_and_path(url: str) -> tuple[str, str]:
    parsed = urlparse(url.strip() if "://" in url else f"https://{url.strip()}")
    return (parsed.hostname or "").lower(), parsed.path.strip("/")


def match_vendor(url: str) -> Vendor | None:
    """The catalog entry whose host AND path shape both accept `url`, or None.

    Both halves are required. A host match alone would admit every page on a vendor's domain --
    a search page, a tenant's landing page, an apply form -- and each of those returns a 200 with
    no `JobPosting`, so the lane would spend its whole request budget earning `extracted_empty`.
    """
    host, path = _host_and_path(url)
    if not host:
        return None
    for vendor in VENDORS:
        matches_host = (
            host.endswith(vendor.host) if vendor.host.startswith(".") else host == vendor.host
        )
        if matches_host and vendor.path.fullmatch(path):
            return vendor
    return None


def owning_provider(url: str) -> str | None:
    """Why one of the six real providers owns `url`, or None when none of them does.

    A message rather than a bool so the refusal can say WHICH condition fired, and a plain return
    rather than a raise because "no provider owns this" is the ordinary answer here -- no tier-D
    host is a board target -- and an exception for the common case reads as an error path.
    """
    try:
        parse_posting_target(url)
    except UnknownBoardURL:
        return None
    except UnresolvablePostingURL as exc:
        # A RECOGNIZED board target whose posting reference this repo cannot read: a board root,
        # or a canonical posting URL with chrome. It is still that provider's URL, so this lane
        # must not claim it either.
        return f"a known provider owns {url!r} but cannot resolve it here: {exc}"
    return f"a known provider owns {url!r} and resolves it itself"


def seed_identity(url: str, seed_id: int) -> SeedPosting:
    """`(provider, slug, posting id)` for a seed URL, from the URL alone.

    THE DEREFERENCE RUNS FIRST and its success is a REFUSAL here. A URL that resolves to one of
    the six real providers is that provider's posting; filing it under a lane-invented provider
    name would mint a second company row for a board the scan stage already enumerates, and the
    two copies of the posting could never converge.
    """
    owned = owning_provider(url)
    if owned is not None:
        raise UnsupportedSeedURL(owned)

    vendor = match_vendor(url)
    if vendor is None:
        raise UnsupportedSeedURL(f"no catalog vendor serves {url!r}")
    host, path = _host_and_path(url)
    matched = vendor.path.fullmatch(path)
    assert matched is not None  # noqa: S101 - match_vendor fullmatched this same pattern
    groups = matched.groupdict()
    if vendor.tenant_is_subdomain:
        slug = host[: -len(vendor.host)]
    else:
        slug = groups.get("tenant") or host
    if not slug:
        # A wildcard vendor addressed at its bare apex (`careerplug.com/jobs/1`) has no tenant.
        raise UnsupportedSeedURL(f"no tenant is recoverable from {url!r}")
    return SeedPosting(
        vendor=vendor, slug=slug, posting_id=groups["id"], url=url.strip(), seed_id=seed_id
    )


def job_posting(page_html: str) -> dict[str, Any]:
    """The `JobPosting` object out of the page's `application/ld+json` blocks.

    Parsed with selectolax rather than a regex over the page, for the reason
    `hiringcafe.parse_search_page` records: a JSON string value may contain `</script>`, and a
    regex terminates on the wrong tag boundary. A block may be one object, a list of them, or a
    `@graph` -- all three occur in the wild -- and a `@type` may itself be a list.
    """
    for node in HTMLParser(page_html).css('script[type="application/ld+json"]'):
        try:
            payload = json.loads(node.text())
        except ValueError:
            # One malformed block must not cost the others on the same page: a vendor that emits
            # a broken `BreadcrumbList` beside a valid `JobPosting` is a page this lane can read.
            continue
        for candidate in _ld_objects(payload):
            types = candidate.get("@type")
            names = types if isinstance(types, list) else [types]
            if "JobPosting" in names:
                return candidate
    raise NoJobPosting("no schema.org JobPosting block in the page")


def _ld_objects(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        graph = payload.get("@graph")
        if isinstance(graph, list):
            return [item for item in graph if isinstance(item, dict)]
        return [payload]
    return []


def _description_html(value: str) -> str:
    """One HTML property, un-escaped exactly once when the vendor escaped it.

    The condition is CLOSED and both halves are load-bearing: the value must carry `&lt;` and
    must carry NO tag at all. CareerPlug's measured description has 151 of the first and 0 of the
    second; an ordinary JD that happens to mention `&lt;` in a code sample has real tags around
    it and is left alone. Exactly once, never in a loop -- a second pass on already-decoded text
    would strip a literal `&amp;lt;` an employer wrote on purpose.
    """
    if "&lt;" in value and not _TAG_RE.search(value):
        return html.unescape(value)
    return value


def body_html(posting: Mapping[str, Any]) -> str:
    """The JD as HTML: the closed property list, in order, sentinels and blanks dropped."""
    parts = [
        _description_html(text)
        for name in _BODY_PROPERTIES
        if (text := _text(posting.get(name))) and text != _UNAVAILABLE
    ]
    return "\n".join(parts)


def posted_at(posting: Mapping[str, Any]) -> datetime | None:
    """`datePosted` as naive UTC, across the four measured formats.

    `fromisoformat` covers all four on this project's Python -- including the colon-less `+0000`
    and a bare date -- so there is no format list to drift. A value it cannot read yields None
    rather than raising: a posting with an unreadable date is still a posting, and the recency
    score already treats None as unknown.
    """
    value = _text(posting.get("datePosted"))
    if not value:
        return None
    try:
        return to_naive_utc(datetime.fromisoformat(value))
    except ValueError:
        return None


def locations(posting: Mapping[str, Any]) -> list[str]:
    """`jobLocation.address` as `"Locality, Region"` strings -- dict AND list shapes.

    Both were measured: a dict on Garmin, a list on Jobvite. A locality with no region yields the
    locality alone rather than a dangling comma, and an address carrying neither yields nothing
    rather than an empty string, which `rank.location_gate` would have to treat as a real place.
    """
    found: list[str] = []
    value = posting.get("jobLocation")
    for place in value if isinstance(value, list) else [value]:
        if not isinstance(place, dict):
            continue
        address = place.get("address")
        for entry in address if isinstance(address, list) else [address]:
            if not isinstance(entry, dict):
                continue
            parts = [
                _text(entry.get("addressLocality")),
                _text(entry.get("addressRegion")),
            ]
            joined = ", ".join(part for part in parts if part)
            if joined and joined not in found:
                found.append(joined)
    return found


def company_name(posting: Mapping[str, Any], *, fallback: str) -> str:
    """`hiringOrganization.name`, the bare-string form, or the tenant -- never blank.

    All three are measured: a dict on five vendors, a bare string on Jobvite, and ABSENT on
    MetLife. `LaneCompanySnapshot.name` requires a non-blank name and the fallback is the tenant
    this lane already keyed the company on, so an employer it cannot name properly is still named
    by something it can evidence -- the rule `hiringcafe.company_name` states for `board_token`.
    """
    org = posting.get("hiringOrganization")
    if isinstance(org, dict):
        return _text(org.get("name")) or fallback
    return _text(org) or fallback


def raw_posting(
    posting: Mapping[str, Any], seed: SeedPosting, body_text: str
) -> RawPosting:
    """One resolved seed as a `RawPosting`.

    `provider_posting_id` comes from the URL, NEVER from `identifier` -- see the module
    docstring's trap 1, where the two were measured disagreeing by one on the same page.

    `url` is the seed URL this lane actually requested. Two vendors carry a `url` of their own in
    the JSON-LD and BOTH were measured differing from the page they were served on -- Breezy's
    appends `?source=GoogleJobs` -- so echoing it would file a lead under a link this run never
    fetched.

    `remote_policy` stays `unknown`. `jobLocation.additionalProperty` was measured carrying
    `TELECOMMUTE` on one vendor, and reading a remote policy off one vendor's optional property
    is a separate decision with its own evidence bar.
    """
    return RawPosting(
        provider_posting_id=seed.posting_id,
        title=_text(posting.get("title")),
        url=seed.url,
        locations=locations(posting),
        posted_at=posted_at(posting),
        body_text=body_text,
        # The JobPosting MINUS the properties whose text is already stored in `body_text`. This
        # column is JSON in the store, so carrying the JD twice would double the row for no
        # reader -- the rule `lanes/indeed.py` applies to `description.html`.
        raw_json={
            "job_posting": {
                name: value for name, value in posting.items() if name not in _BODY_PROPERTIES
            }
        },
    )


class JsonLdLane:
    name = LANE_NAME

    def __init__(
        self,
        seeds: SeedReader,
        request_budget: int = SEED_REQUEST_BUDGET,
        max_attempts: int = SEED_MAX_ATTEMPTS,
        scan_limit: int = SEED_SCAN_LIMIT,
    ) -> None:
        # Injected rather than reached for, the rule every lane here follows: the reader needs a
        # store connection and a lane must not open one of its own.
        self._seeds = seeds
        # Clamped rather than trusted, as `hiringcafe` clamps `search_pages`: a lane constructed
        # with 0 would make no request at all and report the resulting silence as a quiet day.
        self._request_budget = max(1, request_budget)
        self._max_attempts = max(1, max_attempts)
        self._scan_limit = max(1, scan_limit)
        self._last_request_at: dict[str, float] = {}

    def collect(self, fetcher: Fetcher, admits: CompanyAdmission) -> LaneResult:
        """Discover seeds from the public lists, then drain the durable queue under the budget.

        DISCOVERY RUNS FIRST AND ITS FAILURE PROPAGATES, which costs a run and nothing more --
        `fetch_listings` states in its own docstring that a half-read corpus must not be reported
        as a smaller list, and the seed table is what makes that safe here: an undrained seed
        keeps its row, uncharged, and is first in line next run.

        `admits` is asked ONCE per distinct `(provider, slug)`, in first-seen order, BEFORE any
        body is fetched. That ordering is free for this lane and it is the reason the catalog is
        keyed on the URL: every identity is recoverable without a request, so the cap rations
        requests that have not been paid for yet rather than discarding ones that have.
        """
        discovered = self._discover(fetcher)

        seeds = self._seeds(
            hosts=seed_hosts(discovered),
            max_attempts=self._max_attempts,
            limit=self._scan_limit,
        )
        tally = AcquisitionTally()
        attempts: list[tuple[int, bool]] = []
        by_company: dict[tuple[str, str], list[SeedPosting]] = {}
        # TWO SEED URLS CAN NAME ONE POSTING, and without this the run does not merely waste a
        # request -- it ABORTS. `lane_seeds` is unique on URL, not on identity, and three vendors
        # here serve one posting at two path shapes: `/jobs/{id}` and `/careers-home/jobs/{id}`,
        # `/apply/{code}/{title}` and `/{code}/{title}`, `/p/{id}-{title}` and `/p/{id}/apply`.
        # Both shapes occur in the public lists. `scan/apply.py` snapshots `existing` once before
        # its loop and never re-reads it, so two postings sharing a `provider_posting_id` both
        # take the INSERT branch and the second violates UNIQUE(company_id, provider_posting_id) --
        # inside `apply_board`'s single transaction, so the whole company rolls back and the
        # exception escapes to the lane stage. `lanes/hiringcafe.py` records the same failure for
        # the same reason; an ATS provider enumerating its own board may assume distinct ids, and
        # a resolver reading a queue of URLs may not.
        seen: set[tuple[str, str, str]] = set()
        for seed in seeds:
            try:
                resolved = seed_identity(seed.url, seed.id)
            except UnsupportedSeedURL:
                # Seen, and deliberately NOT requested -- the catalog refused it, or a real
                # provider owns it. CHARGED anyway: the seed took one of this run's scanned slots
                # and nothing about it will change, so the attempt ceiling is what retires it.
                # The host filter should have excluded most of these before they were read; the
                # ones that survive it are a host this lane serves at a path shape it does not.
                tally.record("not_attemptable")
                attempts.append((seed.id, False))
                continue
            identity = (resolved.vendor.provider, resolved.slug, resolved.posting_id)
            if identity in seen:
                # A SECOND URL for a posting this run already holds. Charged, because it can never
                # become anything else: whichever URL resolves first closes the posting, and this
                # row would otherwise sit in the queue being skipped forever.
                tally.record("not_attemptable")
                attempts.append((seed.id, False))
                continue
            seen.add(identity)
            by_company.setdefault((resolved.vendor.provider, resolved.slug), []).append(resolved)

        # EVERY admission is settled before ANY body is fetched, in one pass of its own. That is
        # the protocol's literal wording, and this lane is the first that can honour it without
        # giving anything up: an identity here is recoverable from the URL, so deciding a company
        # costs no request, where `lanes/hiringcafe.py` can only decide each company immediately
        # before its own board GET. Settling them together also means the per-run cap is spent
        # against the whole run's companies rather than against however many happened to be
        # reached before the budget ran out.
        #
        # Nothing is tallied and NOTHING IS CHARGED for a refusal. No request was attempted, so an
        # outcome here would inflate `attempted` with a non-attempt -- and charging the seed would
        # age a real posting out of the queue for having been deferred by a cap three times.
        # Refusals are reported by name through `admission.CompanyBudget.refused`.
        admitted = [key for key in by_company if admits(*key)]

        snapshots: list[LaneCompanySnapshot] = []
        remaining = self._request_budget
        for provider, slug in admitted:
            group = by_company[(provider, slug)]
            postings: list[RawPosting] = []
            name = slug
            for seed_posting in group:
                if remaining <= 0:
                    # Seen, not requested: the per-run request budget is spent. Uncharged, for the
                    # same reason a capped company is -- this seed never had its turn.
                    tally.record("not_attemptable")
                    continue
                remaining -= 1
                posting, employer = self._resolve(fetcher, seed_posting, tally)
                attempts.append((seed_posting.seed_id, posting is not None))
                if posting is None:
                    continue
                postings.append(posting)
                name = employer or name
            if postings:
                # A company whose every body was refused yields NO snapshot: an empty one would
                # still write a `board_scans` row and oblige a company row for zero postings, and
                # every refusal is already counted in the tally.
                snapshots.append(
                    LaneCompanySnapshot(
                        provider=provider,
                        slug=slug,
                        name=name,
                        snapshot=lane_snapshot(postings, group[0].url),
                    )
                )
        return LaneResult(
            snapshots=tuple(snapshots),
            tally=tally,
            discovered_seeds=discovered,
            seed_attempts=tuple(attempts),
        )

    def _discover(self, fetcher: Fetcher) -> tuple[str, ...]:
        """Catalog-matching ACTIVE posting URLs from the two public new-grad lists.

        `active is not True` rather than falsiness, matching `github_lists.discover` exactly: the
        field is a real bool on 100% of records, so a truthy string would be the contract moving
        rather than an open posting. It is not a nicety -- the one Paylocity posting in the gate-1
        miss set is `active: false` here, and its URL was separately measured serving
        `JobNotFound`.

        Deduplicated in first-seen order. `record_seeds` is conflict-safe and would absorb a
        repeat anyway, but a caller reporting how many URLs it discovered should not count one
        twice.
        """
        found: list[str] = []
        seen: set[str] = set()
        for rows in fetch_listings(fetcher).values():
            for row in rows:
                if row.get("active") is not True:
                    continue
                url = row.get("url")
                if not isinstance(url, str) or url.strip() in seen:
                    continue
                if match_vendor(url) is None:
                    continue
                seen.add(url.strip())
                found.append(url.strip())
        return tuple(found)

    def _resolve(
        self, fetcher: Fetcher, seed: SeedPosting, tally: AcquisitionTally
    ) -> tuple[RawPosting | None, str]:
        """One GET, one JSON-LD read, one quality verdict. Returns the posting and the employer.

        The UA is the IDENTIFYING one, not the browser string the recon probed with. These are the
        employer's own ATS pages -- the same category `lanes/hiringcafe.py` restores it for when
        it leaves the aggregator and touches a provider's own host -- and D22 is owed to a board
        that answers us honestly. It is stated because it is a real risk taken deliberately: the
        200s in the recon were measured under a Chrome UA, so a host that refuses this one will
        show up as `fetch_refused`, counted and named, rather than as a quiet zero.
        """
        self._pace(seed.vendor, seed.url)
        try:
            result = fetcher.get(seed.url, headers={"User-Agent": identifying_user_agent()})
        except FetchFailure as exc:
            tally.record(_failure_outcome(exc))
            return None, ""
        try:
            posting = job_posting(result.content.decode("utf-8", "replace"))
        except NoJobPosting:
            tally.record("extracted_empty")
            return None, ""
        title = _text(posting.get("title"))
        employer = company_name(posting, fallback="")
        body_text, rejection = assess_body(body_html(posting), title=title)
        if rejection is not None:
            tally.record(rejection.outcome)
            return None, employer
        if not title:
            # A posting with a body and no title. `RawPosting.title` feeds the role gate, the
            # ranker and the rendered lead, and an empty one is not a posting a reader could act
            # on -- `smartrecruiters.parse_posting` refuses the same thing for the same reason.
            tally.record("extracted_empty")
            return None, employer
        # `body_fetched`, not `body_inline`: one request bought one body. See the module docstring.
        tally.record("body_fetched")
        return raw_posting(posting, seed, body_text), employer

    def _pace(self, vendor: Vendor, url: str) -> None:
        """Top the shared per-host pace up to a stricter delay THIS HOST declares.

        Only ever ADDS delay, and only for a vendor carrying a measured directive. The fetcher
        paces every host at >=1.0 s inside the lock it holds for a request's full duration, so
        for every other vendor here this does nothing at all and correctly so -- a second, weaker
        pacing rule is the thing `lanes/hiringcafe.py` refuses.
        """
        if vendor.crawl_delay_seconds is None:
            return
        host, _ = _host_and_path(url)
        last = self._last_request_at.get(host)
        if last is not None:
            remaining = vendor.crawl_delay_seconds - (time.monotonic() - last)
            if remaining > 0:
                time.sleep(remaining)
        self._last_request_at[host] = time.monotonic()


def _failure_outcome(exc: FetchFailure) -> AcquisitionOutcome:
    """Status -> outcome. A transport failure has no status and is `fetch_unavailable`.

    The three buckets are kept apart because they mean different things to a reader of the run:
    403 is the host refusing us, 404 is a posting that has gone, and a timeout is neither.
    """
    if exc.status_code in (401, 403):
        return "fetch_refused"
    if exc.status_code in (404, 410):
        return "fetch_gone"
    return "fetch_unavailable"


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
