# LinkedIn guest lane — contract

**Transcribed 2026-08-24 from D-290, which recorded a read-only probe (24 unauthenticated HTTP
requests, no credential, no browser automation, prior session).** This file records the request
shapes and response *structure* the probe observed. It commits **no capture**: no employer name, no
job-description text, no captured card HTML. The generalization gate refuses a third party's JD body
as unregistered data obliging a licence that does not exist, and this repo is public (D-285/D-290).

**One clause is reconstructed, not freshly pinned, and is flagged as such: the exact CSS selectors in
§2.** D-290 recorded that every card *field* is present and complete (§2's field list, 100/100), not
the selector each field is read from. On Mit's ruling (2026-08-24, "build from recorded contract")
the client is built against the field list plus LinkedIn's public guest-search card structure,
without a fresh live request. The selectors below are therefore the shape the parser **assumes**;
they are the review target when the lane is verified against the live service at arm time. The lane
ships **off by default and not armed**, exactly as hiring.cafe did, so this reconstruction gates
nothing until an operator names `linkedin` in `lanes_enabled` and a live run confirms it.

---

## 1. Endpoints — two, and no others

    GET https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?f_TPR=r86400
    GET https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{id}

No key, no cookie, no TLS bypass, no app impersonation. D-290: the search returns **200 with no
credential, no lifted key, no spoofed app identity, no `verify=False`, and no User-Agent header at
all** — an honest UA, a browser UA and *no* UA are indistinguishable (200 / 31,195 · 30,099 · 27,761
bytes), so there is no UA gate to evade. The lane still sends a browser UA, because that is the
posture D-278 set for aggregator fetches and it costs nothing here. Zero HTTP 999s across 24 requests.

**Permission is a separate axis from reachability, and it is recorded as refused.** `robots.txt`
(4,862 lines, 77 agent groups) names `Disallow: /jobs-guest/` in **every** group, closes with
`User-agent: *` / `Disallow: /`, and disallows `anthropic-ai` / `ClaudeBot` / `Claude-Web` /
`Claude-User` **by name**. User Agreement §8.2 forbids scripted scraping. Mit ruled BUILD with all of
this stated in front of him (D-290); this is the owner's call about the owner's own risk, recorded,
not re-litigated. Reading an absence of bans as a grant is the same error class as reading a green
check as a passing test.

## 2. Search response — an HTML card list

`seeMoreJobPostings/search` returns an HTML fragment: a `<ul>` of `<li>` job cards. D-290 recorded
**100/100 field completeness** over 100 collected cards for: **id, title, company (a plain string
*plus* a stable slug — 0 opaque URNs), location, ISO posted date, URL**. And two functional gaps:

- **No external apply URL** — `externalApply` appears **0 times**. The apply button is a signup wall.
  So a card carries no employer/ATS link to dedup against the six providers; the only URL it exposes
  is the LinkedIn job-view URL. Company identity therefore rides on the **slug**, never a link.
- **`f_WT=2` (remote) is silently ignored** — it returned a byte-identical id set to unfiltered, so
  it is not a usable filter. **`f_TPR=r86400`** (last 24h) genuinely works and is the one filter
  parameter evidenced. The client sends `f_TPR=r86400` and nothing else.

**Reconstructed selectors (see the header caveat).** The client reads each field from:

| field | selector | note |
|---|---|---|
| job id | `div.base-card[data-entity-urn]` → `urn:li:jobPosting:{id}` tail | the numeric posting id |
| title | `h3.base-search-card__title` (text) | |
| company name | `h4.base-search-card__subtitle a` (text) | the plain string |
| company slug | same anchor's `href` → `.../company/{slug}` last path segment | the stable convergence key |
| location | `span.job-search-card__location` (text) | provider-asserted, gated downstream |
| posted date | `time[datetime]` attribute | ISO `YYYY-MM-DD` |
| url | `a.base-card__full-link` `href` | the job-view URL, the only URL exposed |

A card missing an id, a title, or a company slug is **not attemptable** and is counted, never
dropped — the same per-card isolation every provider's board parse applies.

## 3. Body response — one request per posting

`jobPosting/{id}` returns an HTML fragment whose description lives in
**`div.show-more-less-html__markup`**. D-290: **4 of 4 real bodies, no stubs**, 3,835 / 5,252 /
6,457 / 7,715 characters. A **bogus id returns a clean 404 of zero bytes** (→ `fetch_gone`). The
body is extracted with `html_to_text` and judged by the existing `lanes.quality.assess_body`
(login-wall test, then the ≥500-char / ≥1-section-marker / ≥8-line floor, then role/body mismatch),
identical to hiring.cafe.

## 4. Paging — deferred, not built

D-290's cost model ("15 searches at 10 cards each") implies `start`-offset paging, but the probe did
not pin the `start` parameter as a confirmed contract, and inventing a paging contract the probe did
not observe is the exact defect `lanes/dereference.py` refuses SmartRecruiters and Workday for. So
the client makes **one search GET** and takes the ~10 cards it returns, the same deliberate refusal
hiring.cafe makes for its own `ssrPage` siblings. Paging needs its own probe at arm time.

## 5. Keywords / location — deliberately omitted

The search sends no `keywords` and no `location` facet. Baking a role query into the client would
make it Mit-specific and break multi-tenancy (a lane is generic mechanism; targeting is profile data
layered on top). The hard US-only location gate and the role gate run **downstream**, so a broad
recent-jobs search is filtered there, the same way the whole corpus already is. A profile-sourced
`keywords`/`location` facet is a clean later extension through `Settings`, not a hardcoded value.

## 6. Cost — recorded, for the arm-time budget conversation only

D-290: ~157 requests/day to yield ~40 usable postings (142 O(n) body fetches plus 15 searches),
~90% of it bodies — a **floor**, since LinkedIn's 28.3% materialization sits upstream of boardwatch's
US / new-grad / eligibility gates and a read-only probe cannot measure that pass rate. **Stated gaps,
not guesses:** the throttle ceiling at production volume is unmeasured (24 requests probed); the stub
rate rests on n=4; `f_E` was not tested in isolation; `/voyager/api/*` was not probed (needs an
`li_at` cookie). None of this is load-bearing for a not-armed build; it is the input to the separate
owner decision to arm.
