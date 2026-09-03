"""Lane 5: the `schema.org/JobPosting` resolver -- one lane in place of FIVE vendor adapters.

One request shape, and no others:

    GET <a posting URL from a seed>    -- the body is IN the page, as JSON-LD

Plus the two GitHub new-grad list GETs this lane's discovery half already shares with
`lanes/github_lists.py`. **No key, no cookie, no TLS bypass, no app impersonation**, and the
`identifying_user_agent()` every board that answers us honestly is owed under D22.

WHY A RESOLVER AND NOT A SET OF ADAPTERS. SIX unrelated vendors were measured on 2026-09-01
serving a complete `JobPosting` with a full `description` on the posting page itself, from one
unauthenticated GET (recon §3.2: Hireology 9,718 / CareerPlug 8,109 / JazzHR 5,410 / Breezy 4,971
/ Paylocity 7,103 / iCIMS-custom 2,665 chars). Every one is per-tenant with no cross-tenant
search, so an adapter for each would be search surfaces that cannot be searched. What they share
is the OUTPUT format, so the lane takes a posting URL from any origin and reads the vendor-neutral
half, with a closed per-vendor catalog for the two facts JSON-LD does not carry: which employer
this is, and which posting.

**FIVE OF THOSE SIX SHIP. `VENDORS` HAS FIVE ROWS AND PAYLOCITY IS NOT ONE OF THEM** -- see the
refusals below for why, and do not read "six vendors were measured" as "six vendors resolve".
The measurement is the recon's; the catalog is what this lane will actually request.

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
  own catalog** -- `SEED_HOSTS` for the two single-host vendors, `SEED_HOST_SUFFIXES` for the
  three that give every employer a subdomain -- because the queue is shared and its ordering is
  global: an unfiltered draw of forty takes the forty oldest rows in the table whoever can
  resolve them, so a vendor with few seeds starves behind a vendor with many, and an attempt gets
  charged against a seed belonging to a resolver that does not exist yet. Neither failure is
  visible in a report; both look like a full budget and a clean tally.

  The suffix arm is what makes a tenant NOBODY HAS SEEN reachable. An earlier version of this
  lane could only ask for tenants its own discovery pass had just named, and claimed that covered
  everything it discovered itself. **That claim was false in both directions** -- it reached
  nothing another lane found on an unseen tenant, and it silently dropped a seed of its own once
  the listing that named that tenant went inactive, leaving a row that was never selected, never
  charged and never aged out. The workaround is gone rather than documented.

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
whichever lane can resolve the rest.

**THE DRAIN'S FILTER IS LOOSER THAN DISCOVERY'S BY EXACTLY ONE HALF, AND NO MORE.** Discovery
needs host AND path (`match_vendor`); the drain selects on HOST alone. A seed another lane
recorded on a catalog HOST that this lane still cannot claim -- a path no vendor pattern
fullmatches, or a URL one of the six real providers owns -- is therefore an ordinary input here:
refused without a request and CHARGED, so the attempt ceiling ages it out.

**A SEED ON A HOST NO CATALOG CLAIMS IS NEVER SELECTED, SO NOTHING EVER CHARGES IT, AND THIS LANE
IS NOT ITS DRAIN.** That is the priced cost of the host filter above, not an oversight, and
widening the read is not the fix: `store.seed_queries.unresolved_seeds` offers no all-hosts form
on purpose (D-426), and `tests/unit/test_jsonld_lane.py` and `tests/unit/test_lane_seeds.py` both
fail any version of this read that claims hosts it cannot resolve. Such a row's re-entry path is a
resolver whose catalog claims its host -- D-422 measured the queue arriving AHEAD of its consumers,
and the Oracle HCM and Eightfold seeds it named are still waiting -- and `boardwatch seeds` (D-426)
is what keeps that population from accumulating unmeasured. MEASURED 2026-09-03: **1,377 of 1,481
unresolved rows, on 387 hosts, every one at `attempts = 0`.**

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
run 139 measured for the LinkedIn lane.

**THE REQUEST BUDGET IS NOT THE BINDING CONSTRAINT ON THE FIRST RUNS, AND AN EARLIER VERSION OF
THIS PARAGRAPH GOT THAT WRONG.** It claimed 40 requests drain the standing backlog in three runs.
Re-measured against the two lists: the 88 catalog-matching ACTIVE URLs are only **50 DISTINCT
TENANTS** (JazzHR 48, iCIMS-custom 1, Breezy 1), and postings are concentrated -- one tenant holds
17 of them, another 13. `lane_new_companies_per_run` defaults to **10** and this lane takes no
override, so a first run admits at most ten NEW companies however much budget is left. Fifty
tenants therefore need roughly **five runs to be admitted**, not three; the 40-request budget only
starts to bind once most tenants are already stored, because an already-known company is admitted
free. Both bounds are real and the smaller one is the cap.

An `lane_new_companies_per_run_overrides` entry would lift it -- `jobapps` and `hiringcafe` both
carry `unlimited` -- and there is a real argument for one, since a "new company" here costs no
board scan at all: this lane fetches exactly the seeds it holds, already bounded by the request
budget, so the company cap is a second and redundant bound. That is an owner decision about a
shipped default and is NOT taken here. The lane ships disarmed; the first armed run measures it.

`SEED_SCAN_LIMIT = 400`, ten times the request budget, and it is not a second budget. Reading a
seed row is a cheap indexed SELECT; REQUESTING one is the cost. Scanning wide is what lets a
CLAIMED-HOST seed this lane still cannot resolve -- wrong path shape, or a real provider's URL --
be refused without spending a request slot, so a scan that is mostly refusals still fills all
forty request slots with seeds it can resolve. It buys nothing against the rest of the table, and
does not need to: the read never returns a row on a host no catalog claims, so those cost no scan
slot either.

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
  ZERO gate-1 postings: the TWO Paylocity miss URLs the recon re-probed (4452707, 4461465) had
  both closed to `JobNotFound` since job-apps' cohort (tierD-recon note 1), so neither is a live
  posting this exclusion forgoes. Ten live list URLs are given up with it. Re-admit it when a
  tenant is recoverable from the URL, not by keying a company on a display name.
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
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from selectolax.parser import HTMLParser

from boardwatch.core.board_urls import UnknownBoardURL, is_seedable_url
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

# THE TWO ARMS OF THIS LANE'S SEED ROUTING, both DERIVED from the catalog rather than written out
# a second time. Two spellings of one set is how a vendor joins the catalog and never the query,
# and that failure is silent in the worst direction: a seed this lane can resolve, sitting in the
# queue, never selected, never charged, forever.
#
# The split is not cosmetic and the two arms are NOT interchangeable. `SEED_HOSTS` claims exactly
# one hostname each. `SEED_HOST_SUFFIXES` claims a vendor's whole TENANT SPACE -- `applytojob.com`
# matches `applytojob.com` and `brandnew.applytojob.com`, and does NOT match `notapplytojob.com`,
# which is a different registrable domain that merely ends in the same characters.
#
# A wildcard vendor gives every employer its own subdomain, so no finite host set can enumerate
# one, and a suffix is the only thing that reaches a tenant nobody has seen yet -- which is
# exactly the Indeed-discovered seed this lane exists to drain. Conversely a single-host vendor
# must NOT go in the suffix arm: a suffix would also claim every subdomain of it, and for a
# shared vendor host that is claiming other resolvers' tenants.
SEED_HOSTS: frozenset[str] = frozenset(
    vendor.host for vendor in VENDORS if not vendor.host.startswith(".")
)
SEED_HOST_SUFFIXES: frozenset[str] = frozenset(
    vendor.host.removeprefix(".") for vendor in VENDORS if vendor.host.startswith(".")
)

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

# A CLOSING tag with a name, matched against text that has ALREADY been through `html_to_text`.
# Nothing an employer writes in prose produces `</p>` or `</div>`; markup that survived
# extraction does. Deliberately narrower than `_TAG_RE`: an opening-tag shape alone matches
# ordinary prose such as "<script> tags are banned", where a CLOSING tag does not.
_RESIDUAL_MARKUP_RE = re.compile(r"</[A-Za-z][A-Za-z0-9]*\s*>")

# How many residual closing tags are tolerated in an extracted body. ZERO. This is a fail-safe
# gate, and the direction is chosen the way `CLAUDE.md` says to choose one -- per gate. What is
# at stake is the FROZEN JD: `INELIGIBLE` must carry a quoted span from it, so a body that is
# really markup produces evidence that quotes a tag at an employer. Dropping a real posting costs
# one lead; storing markup as a JD corrupts the evidence chain for every verdict drawn from it.
MAX_RESIDUAL_MARKUP = 0


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
    """The host EXACTLY as `lane_seeds` records it, plus the path.

    The host comes from `store.seed_queries.seed_host` rather than from a second spelling here,
    and that is a correctness rule and not a tidy-up. Routing and IDENTITY both key on this: a
    URL spelled `https://WWW.Example.careerplug.com/jobs/1` is routed under the stripped host the
    store recorded, and if identity used the unstripped one the same employer would be stored a
    second time under slug `www.example` -- two company rows, neither of which can ever converge
    on the other. One function, so the two can never disagree.
    """
    parsed = urlparse(url.strip() if "://" in url else f"https://{url.strip()}")
    return seed_host(url.strip()), parsed.path.strip("/")


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

        **EVERY SEED THAT HAS ITS TURN IS RETURNED FOR CHARGING, INCLUDING ONE THAT CRASHES THE
        RESOLVER.** The per-seed body below cannot raise: an unexpected failure is isolated,
        returned as a non-resolution, and reported to the runner through `resolver_errors` as a
        visible lane error rather than disguised as an empty extraction. The runner charges
        non-resolutions (`_persist_seed_work`) but deliberately leaves a resolved-but-unapplied
        seed uncharged, so charging is the runner's call, not an invariant this loop holds over
        every turn. Letting the failure escape would discard
        not just that seed but EVERY attempt already recorded this run, because the runner only
        ever charges what a returned `LaneResult` carries -- so a single malformed page would leave
        a whole run's seeds at the same attempt count, to be re-fetched at one GET each, every run,
        forever. That is the drain failing silently, which is the one failure this queue prevents.
        """
        discovered, refused = self._discover(fetcher)

        seeds = self._seeds(
            hosts=SEED_HOSTS,
            host_suffixes=SEED_HOST_SUFFIXES,
            max_attempts=self._max_attempts,
            limit=self._scan_limit,
        )
        tally = AcquisitionTally()
        attempts: list[tuple[int, bool]] = []
        # Seed ids the runner must close WITHOUT charging (redundant aliases resolved without a
        # GET), and unexpected-crash reports it must surface as a visible lane error. Both are
        # carried out rather than acted on here: the store write is the serial apply phase's.
        uncharged: list[int] = []
        resolver_errors: list[str] = []
        # `(provider, slug) -> posting id -> the seeds naming that posting`. TWO LEVELS, because
        # two seed URLs can name ONE posting: `lane_seeds` is unique on URL, not on identity, and
        # three vendors here serve one posting at two path shapes -- `/jobs/{id}` and
        # `/careers-home/jobs/{id}`, `/apply/{code}/{title}` and `/{code}/{title}`,
        # `/p/{id}-{title}` and `/p/{id}/apply`. Both shapes occur in the public lists.
        #
        # An earlier version suppressed the second URL at THIS point, before either was fetched,
        # and recorded that `apply_board` would otherwise abort the company. **That rationale was
        # false and is corrected rather than quietly dropped**: `scan/apply.py::_apply_listed`
        # has collapsed duplicate `provider_posting_id`s to the first occurrence since before this
        # lane existed, so the store was never at risk. What the suppression actually did was
        # lose postings -- if the first URL is dead and its alias is live, the live one was
        # discarded unfetched and both seeds aged out. Aliases are therefore tried IN ORDER until
        # one resolves.
        by_company: dict[tuple[str, str], dict[str, list[SeedPosting]]] = {}
        for seed in seeds:
            try:
                resolved = seed_identity(seed.url, seed.id)
            except UnsupportedSeedURL:
                # Seen, and deliberately NOT requested -- the catalog refused it, or a real
                # provider owns it. CHARGED anyway: the seed took one of this run's scanned slots
                # and nothing about it will change, so the attempt ceiling is what retires it.
                tally.record("not_attemptable")
                attempts.append((seed.id, False))
                continue
            company = by_company.setdefault((resolved.vendor.provider, resolved.slug), {})
            company.setdefault(resolved.posting_id, []).append(resolved)

        # EVERY admission is settled before ANY body is fetched, in one pass of its own. That is
        # the protocol's literal wording, and this lane is the first that can honour it without
        # giving anything up: an identity here is recoverable from the URL, so deciding a company
        # costs no request, where `lanes/hiringcafe.py` can only decide each company immediately
        # before its own board GET.
        #
        # Nothing is tallied and NOTHING IS CHARGED for a refusal. No request was attempted, so an
        # outcome here would inflate `attempted` with a non-attempt -- and charging the seed would
        # age a real posting out of the queue for having been deferred by a cap three times.
        # Refusals are reported by name through `admission.CompanyBudget.refused`.
        admitted = [key for key in by_company if admits(*key)]

        snapshots: list[LaneCompanySnapshot] = []
        remaining = self._request_budget
        for provider, slug in admitted:
            postings: list[RawPosting] = []
            name = slug
            source_url = ""
            for aliases in by_company[(provider, slug)].values():
                if remaining <= 0:
                    # Seen, not requested: the per-run request budget is spent. Uncharged, for the
                    # same reason a capped company is -- these seeds never had their turn.
                    for _ in aliases:
                        tally.record("not_attemptable")
                    continue
                posting, employer, spent = self._resolve_aliases(
                    fetcher, aliases, tally, attempts, uncharged, resolver_errors, budget=remaining
                )
                remaining -= spent
                if posting is None:
                    continue
                postings.append(posting)
                name = employer or name
                # THE SNAPSHOT URL IS ONE THAT ACTUALLY RESOLVED. `BoardSnapshot.url` is what
                # `apply_board` hands `record_version_source` as the source of every version in
                # it, so naming the group's FIRST seed would attribute a posting to a URL that
                # may have 404'd moments earlier -- provenance pointing at a request that
                # produced nothing. The first resolving URL is a request this run really made and
                # really got this body from.
                #
                # It is still ONE url for the whole company, and that is a limit of
                # `BoardSnapshot`, not a choice made here: `_apply_listed` takes a single
                # `source_url` for the batch, so genuine per-posting provenance would need either
                # a change to a signature all six providers share or one snapshot per posting --
                # and the second writes a `board_scans` row per posting, which double-counts the
                # company in every coverage bucket.
                source_url = source_url or posting.url
            if postings:
                # A company whose every body was refused yields NO snapshot: an empty one would
                # still write a `board_scans` row and oblige a company row for zero postings, and
                # every refusal is already counted in the tally.
                snapshots.append(
                    LaneCompanySnapshot(
                        provider=provider,
                        slug=slug,
                        name=name,
                        snapshot=lane_snapshot(postings, source_url),
                    )
                )
        return LaneResult(
            snapshots=tuple(snapshots),
            tally=tally,
            discovered_seeds=discovered,
            refused_seeds=refused,
            seed_attempts=tuple(attempts),
            uncharged_resolved=tuple(uncharged),
            resolver_errors=tuple(resolver_errors),
        )

    def _resolve_aliases(
        self,
        fetcher: Fetcher,
        aliases: list[SeedPosting],
        tally: AcquisitionTally,
        attempts: list[tuple[int, bool]],
        uncharged: list[int],
        resolver_errors: list[str],
        *,
        budget: int,
    ) -> tuple[RawPosting | None, str, int]:
        """Try each URL naming one posting until one resolves. Returns it, the employer, the GETs.

        Sequential rather than first-only, because these URLs are not interchangeable in practice:
        one shape may 404 while its alias serves the same live posting. Trying only the first
        discards a real posting AND ages both seeds out over three runs, which is the defect that
        replaced a pre-fetch duplicate suppression here.

        A seed whose alias already resolved is closed RESOLVED WITHOUT A REQUEST, and it is added to
        `uncharged` so the runner does NOT move its attempt counter. That is not a convenience:
        `resolved_at` is what retires a row permanently, and the posting this seed names
        demonstrably was produced this run, so closing it is true; but it cost no GET, so charging
        the fetch ceiling for it would be counting work that never happened. Charging it unresolved
        instead would leave it to be fetched again next run for a posting the store already holds.
        """
        employer = ""
        spent = 0
        for index, seed in enumerate(aliases):
            if spent >= budget:
                # Out of budget mid-alias-set. The rest had no turn, so they are uncharged.
                for _ in aliases[index:]:
                    tally.record("not_attemptable")
                return None, employer, spent
            spent += 1
            posting, found = self._resolve(fetcher, seed, tally, resolver_errors)
            employer = employer or found
            attempts.append((seed.seed_id, posting is not None))
            if posting is not None:
                # Every remaining alias names a posting this run just produced. Closed, unfetched,
                # and NOT charged: it never spent a request.
                for redundant in aliases[index + 1 :]:
                    attempts.append((redundant.seed_id, True))
                    uncharged.append(redundant.seed_id)
                return posting, employer, spent
        return None, employer, spent

    def _discover(self, fetcher: Fetcher) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Catalog-matching ACTIVE posting URLs from the two public new-grad lists, and every
        MALFORMED candidate dropped along the way.

        `active is not True` rather than falsiness, matching `github_lists.discover` exactly: the
        field is a real bool on 100% of records, so a truthy string would be the contract moving
        rather than an open posting. It is not a nicety -- a Paylocity miss posting is
        `active: false` in the lists here, and its URL was separately measured serving
        `JobNotFound`.

        Deduplicated in first-seen order. `record_seeds` is conflict-safe and would absorb a
        repeat anyway, but a caller reporting how many URLs it discovered should not count one
        twice.
        """
        found: list[str] = []
        refused: list[str] = []
        seen: set[str] = set()
        for rows in fetch_listings(fetcher).values():
            for row in rows:
                if row.get("active") is not True:
                    continue
                url = row.get("url")
                if not isinstance(url, str) or url.strip() in seen:
                    continue
                # The shared seed-URL gate, BEFORE `match_vendor`, so a bad-port / scheme-less /
                # control-char / IP-literal / multi-dot value never becomes a discovered seed.
                # `match_vendor` routes off `seed_host`, which drops the port and cleans up control
                # chars, so on its own it would match `newco.applytojob.com:99999/...` as JazzHR and
                # seed a row HTTPX rejects at fetch. A MALFORMED value is carried out in `refused`
                # for the runner to surface -- and added to `seen` so a repeat is not reported
                # twice -- rather than dropped silently past the visibility path. `record_seeds`
                # WOULD refuse it at the write point, but this branch never passes it there --
                # carrying it in `refused` spares the round trip AND is what makes the producer
                # refusal visible.
                if not is_seedable_url(url.strip()):
                    seen.add(url.strip())
                    refused.append(url.strip())
                    continue
                # A well-formed URL naming NO vendor this lane resolves -- the ordinary catalog miss
                # (an owner-declined `*.icims.com`, a greenhouse board a scan already owns). Not a
                # defect: NOT carried as a refusal, just not this lane's seed.
                if match_vendor(url) is None:
                    continue
                seen.add(url.strip())
                found.append(url.strip())
        return tuple(found), tuple(refused)

    def _resolve(
        self,
        fetcher: Fetcher,
        seed: SeedPosting,
        tally: AcquisitionTally,
        resolver_errors: list[str],
    ) -> tuple[RawPosting | None, str]:
        """One GET, one JSON-LD read, one quality verdict. Returns the posting and the employer.

        The UA is the IDENTIFYING one, not a browser string. These are the employer's own ATS
        pages -- the same category `lanes/hiringcafe.py` restores it for when it leaves the
        aggregator and touches a provider's own host -- and D22 is owed to a board that answers us
        honestly. Both live target hosts were probed with it and answered HTTP 200 with a full
        `JobPosting`, so this is measured rather than hoped for; a host that later refuses it
        shows up as `fetch_refused`, counted and named, rather than as a quiet zero.

        `min_host_delay` carries the vendor's DECLARED crawl-delay into the fetcher, which applies
        it before every physical attempt. It is not applied here, and that is the fix for a real
        defect: a lane-local sleep runs once per call, while `Fetcher` makes up to
        `retry_attempts` real requests inside one call with a backoff starting at 0.5s -- so a
        503 from a host asking for five seconds got its retries half a second apart, and the lane
        that believed it was pacing had no idea.

        **THIS FUNCTION DOES NOT RAISE.** The whole fetch-and-read body is wrapped: a vendor page
        that breaks the parser -- or a non-`FetchFailure` crash inside `fetcher.get` itself -- is
        one seed's problem, and the alternative is aborting `collect` and losing every attempt
        already charged this run. A typed `FetchFailure` stays typed and is classified as a fetch
        outcome; every OTHER exception, from the fetch or the read, is recorded into
        `resolver_errors` for the runner to report -- NOT folded into a content outcome, which
        would disguise a code defect as an empty page.
        """
        try:
            try:
                result = fetcher.get(
                    seed.url,
                    headers={"User-Agent": identifying_user_agent()},
                    min_host_delay=seed.vendor.crawl_delay_seconds,
                )
            except FetchFailure as exc:
                tally.record(_failure_outcome(exc))
                return None, ""
            return self._read(result.content, seed, tally)
        except Exception as exc:  # noqa: BLE001 - one crashing seed must not discard the charges
            # An UNEXPECTED exception from EITHER the fetch or the read, so a real code defect --
            # NOT a typed `FetchFailure` (classified just above) and NOT an expected content
            # failure (`_read` returns explicitly for `NoJobPosting`, a body rejection, an empty
            # title or residual markup, so nothing that merely produced an empty extraction reaches
            # here). A non-`FetchFailure` raised by `fetcher.get` -- a client `RuntimeError`, a
            # request-build failure -- lands here too and is isolated exactly like a `_read` crash,
            # rather than aborting `collect` and discarding every attempt already charged this run.
            # Recording `extracted_empty` would disguise the defect as "a response arrived and
            # extraction found nothing" and age a real seed out on a false claim. Carried out as a
            # visible lane error instead; the seed is still charged unresolved (`posting is None`).
            resolver_errors.append(f"{seed.url}: {exc!r}")
            return None, ""

    def _read(
        self, content: bytes, seed: SeedPosting, tally: AcquisitionTally
    ) -> tuple[RawPosting | None, str]:
        """The post-response half: block, body, quality, posting.

        Split out so `_resolve` can isolate every failure in it behind one boundary.
        """
        try:
            posting = job_posting(content.decode("utf-8", "replace"))
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
        residual = len(_RESIDUAL_MARKUP_RE.findall(body_text))
        if residual > MAX_RESIDUAL_MARKUP:
            # THE FAIL-SAFE, and it exists because the escape rule alone is not sufficient.
            # `_description_html` only unescapes a value that is escaped WHOLE. A description
            # that mixes REAL separators with ESCAPED block content -- `<br>` between
            # `&lt;h2&gt;...&lt;/h2&gt;` -- carries a real tag, so the rule correctly declines to
            # unescape it, and `html_to_text` then emits the escaped tags as literal text.
            # MEASURED on exactly that shape: 905 characters over 14 lines with a Responsibilities
            # marker, which `assess_body` accepts without a murmur.
            #
            # What that stores is markup as the FROZEN JD -- the document every `INELIGIBLE` span
            # is quoted from -- so a verdict would cite `</li>` at an employer. Rejected rather
            # than repaired: a second unescape pass here would be guessing at a shape nobody has
            # measured, and this gate is one where dropping a real posting is the cheaper error.
            tally.record("rejected_quality_gate")
            return None, employer
        # `body_fetched`, not `body_inline`: one request bought one body. See the module docstring.
        tally.record("body_fetched")
        return raw_posting(posting, seed, body_text), employer


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
