# A fourth discovery lane — decision memo

**2026-08-22. Read-only research. No code changed, no dependency added, no request made to any job
site.** This memo evaluates candidates for a lane *beyond* the three already approved by D-272 (as
reordered by D-278): Indeed, hiring.cafe, GitHub new-grad lists. It recommends; it does not decide —
the owner rules, per this repo's standing practice (D-272, D-278 are both explicitly "owner ruling").

## The four constraints every candidate is measured against

Quoted, not paraphrased, from the binding sources:

1. **Body-or-nothing.** D-278: *"the eligibility engine is body-only... a lane without a
   JD-body acquisition step adds corpus and produces no leads at all — every row would sit in
   `uncertain`."* Design doc §2: Indeed was ordered first because *"`description { html }` is a
   field of the GraphQL search query itself, zero extra requests."*
2. **Aggregator, never adapter.** D-272: *"Every casualty is a bespoke first-party adapter or a
   small niche API; not one is an aggregator."* Design §5 (rejected): *"Bespoke first-party
   adapters (Amazon/Apple/TikTok direct). D-272's ruling stands and this session found more
   confirmation, not less."*
3. **Breadth is a cost, not a feature, until conversion is proven.** `CLAUDE.md`: *"Add input only
   after conversion is proven."* D-278 Ruling 3: *"adding a whole board IS breadth... permitted
   only under an explicit per-run cap on new companies, with every addition reported."* `CLAUDE.md`
   also requires the volume be filtered through the **hard US-only location gate**
   (`location_filter_mode=hard`, per program memory) before it counts for anything.
4. **No dependency that cannot install.** Plan doc, "Not in this plan": *"`python-jobspy` 1.1.82
   pins `NUMPY==1.26.3`, whose newest wheel is `cp312`. boardwatch is `requires-python = ">=3.11"`
   and CI tests 3.13... so the library cannot install on a supported interpreter."* Verified this
   session: `pyproject.toml` line 37 states `requires-python = ">=3.11"`; classifiers list 3.11,
   3.12, 3.13 explicitly (lines 30–32). Any new dependency must support the full range, not just
   the author's own interpreter.

Two more facts, verified by reading code this session, that bound every candidate below:

- **A lane is not a `Provider`.** Design §4.1, unchanged: registering a seventh provider breaks a
  test asserting set equality on the six provider names and a fixture rule that fires on any
  provider with no fixtures. A genuinely new *ATS family* (as opposed to an aggregator) is
  therefore architecturally a **provider candidate**, not a **lane candidate** — a different kind
  of change with a different bar, and this distinction matters for candidate 2 below.
- **`src/boardwatch/core/host_class.py` already carries a three-way host classification** used for
  dedup survivor election (P6 §3), not for fetching. `ATS_HOSTS` (17 entries) already includes
  `icims.com`, `taleo.net`, `successfactors.com`, `bamboohr.com`, `jobvite.com`, `teamtailor.com`,
  and others beyond the six supported providers. `AGGREGATOR_HOSTS` (13 entries) already includes
  `linkedin.com`, `indeed.com`, `wellfound.com`, `otta.com`, `jobright.ai`, `dice.com`,
  `glassdoor.com`, `ziprecruiter.com`, and more. **Neither table is a fetch client** — this is
  classification-only knowledge for scoring which of two colliding URLs wins survivor election. It
  means the *taxonomy* already anticipates several of these hosts; no code *reaches* any of them
  today. `hiring.cafe`, `github.com`, `remoteok.com`, and `adzuna.com` appear in **neither** table.

---

## Candidate 1 — LinkedIn (own `httpx` client, not JobSpy)

**What it is.** LinkedIn's own job search and posting pages, fetched directly — the design doc
already names this as **open question 3**: *"Whether the LinkedIn lane is worth its O(n) request
cost given Indeed's body is free."* D-272's own ledger measurement already exists in this repo:
job-apps ran LinkedIn 22,016 times over 22 of 23 days (14/14 in the last 14), but its
`materialization_state` is the **worst** of the five ranked lanes at **28.3% (8,623 pending)** —
worse than jobright (36.6%) and far worse than simplify (75.8%).

- **Aggregator or adapter:** Aggregator. Already classified as such in `host_class.py`
  (`AGGREGATOR_HOSTS` includes `linkedin.com`).
- **Body inline or per-posting fetch:** **Per-posting fetch, confirmed by both this project's own
  design doc and independent web search this session (unverified beyond community scraper
  documentation, since LinkedIn ships no first-party developer API for job search).** The design
  doc states the guest search endpoint returns listings without bodies and a **separate** guest
  endpoint (`jobs-guest/jobs/api/jobPosting/{id}`) returns the full description — one GET per
  posting, O(n). Job-apps' own measured hit rate for this pattern was strong (97.7%, no browser),
  but the cost is exactly the two-request shape Indeed was chosen to avoid.
- **Needs the URL-dereferencing capability being built now:** **No.** The body lives on LinkedIn's
  own guest endpoint; there is nothing to dereference to an underlying ATS. (A separate, smaller
  question — not scored here — is that some LinkedIn postings are Easy-Apply-only with no
  employer-side URL at all, which the design's evidence chain has not addressed for any lane.)
- **Volume / US relevance:** High volume, filterable by location facet in the search query; US
  relevance is plausible but not verified this session.
- **New dependency:** **None.** Uses the existing `httpx`-based `Fetcher`
  (`core/politeness.py:67`) with the browser-UA instance the design already plans to build for the
  three approved lanes (§4.7). No package to install, no interpreter-compatibility question.
- **Already reached in the repo:** No fetch client. Only the dedup classification noted above.
- **Strongest argument against:** LinkedIn ships **no documented, supported API** for this — every
  fact above about the endpoint shape comes from third-party scraper write-ups, not an
  Anthropic/LinkedIn-equivalent developer doc, and LinkedIn's terms of service prohibit automated
  access to these endpoints. That is a materially different risk posture than Indeed's GraphQL
  search query or hiring.cafe's plain unauthenticated GET, both of which the design doc verified by
  calling them directly and recording a real response. Layered on top: the O(n) fetch cost the
  design doc already flagged, job-apps' own measured worst-materialization-quality data for this
  exact lane, and the design's own note that "LinkedIn guest rate-limits hard — retry fails at 3
  workers + backoff." Nothing here disqualifies it outright (Indeed and hiring.cafe are also
  reverse-engineered relative to a published contract, and job-apps ran it 14/14 days without a
  ban), but the confidence in the request contract is markedly lower than for the three already
  approved, and this is exactly the class of unverified-request-contract claim this project's own
  practice (D-275's corrections) treats as disqualifying until someone probes the live endpoint and
  pins a fixture.

## Candidate 2 — Oracle Cloud HCM / iCIMS as new *providers* (not lanes)

**What it is.** Not an aggregator at all — these are real ATS families, structurally identical in
kind to the six already-supported providers, just unsupported today. This is **D-278's own open
question 1**, carried over from D-272, unresolved: *"Whether Oracle Cloud HCM and iCIMS should
become providers instead of, or before, any lane... ~45% of the non-six tail... This does not reach
Amazon/Apple/TikTok."* I include it here because the owner's prompt was "a fourth lane," and this is
the most likely candidate to be *conflated* with a lane — the memo's job is to name that conflation
explicitly rather than let it happen silently.

- **Aggregator or adapter:** **Neither, in the D-272 sense.** It is a genuine seventh/eighth
  `Provider` (design §4.1's own boundary), not a `Lane`. The aggregator-vs-adapter fragility
  argument from D-272 (adapters die, aggregators don't) does not directly transfer — a Provider is
  neither; it is a first-party API integration against a real ATS vendor, the same shape as the six
  that already work reliably.
- **Body inline or per-posting fetch:** **Unverified this session.** Web search found Oracle's
  documented REST API (`/hcmRestApi/resources/latest/recruitingCEJobRequisitions`, a "get all
  requisitions" list endpoint distinct from a "get a job requisition" single-item endpoint) but did
  not establish from official documentation alone whether the list endpoint inlines the full
  description or only requisition metadata (title, location, category) with description requiring
  the per-item endpoint — the same two-tier shape as hiring.cafe. Treat as **inferred, not
  verified**: probably a per-posting fetch, pending an actual probe against a live Oracle Cloud HCM
  career site.
- **Needs the URL-dereferencing capability being built now:** No — this would be a first-party
  Provider with its own board fetch, not a link resolved from an aggregator.
- **Volume / US relevance:** Design doc: Oracle Cloud HCM is **31.3%** of the non-six tail, iCIMS
  **13.6%** — together roughly 45%, the single largest opportunity by volume of any candidate in
  this memo. But the design doc's own premise check names the largest individual non-six company as
  **Sainsbury's at 1,639 postings, a UK grocer on Oracle Cloud that the US-only gate discards
  anyway** — a concrete, already-measured example that a meaningful share of this volume is not
  US-relevant.
- **New dependency:** None expected — same `httpx` + `selectolax`/JSON stack as the six existing
  providers.
- **Already reached in the repo:** `host_class.py`'s `ATS_HOSTS` already lists `icims.com` (and,
  suggestively, `taleo.net` and `successfactors.com`, two more ATS families outside today's six) —
  again, classification only, not a fetch path.
- **Strongest argument against:** It is not what was asked for. The owner's ruling in D-278 already
  set the lane purpose as *"reach companies no existing route can reach"* and immediately noted
  Oracle/iCIMS **do not reach Amazon/Apple/TikTok** — the companies that motivated the whole lane
  program (§1 of the design doc: "24 of 352" companies reachable, Amazon/TikTok/Apple/ByteDance
  named as the gap). Pursuing this well answers "more ATS coverage," not "more discovery breadth,"
  and it is explicitly still owner-gated as its own open question rather than a lane decision. It
  also carries job-apps' own weak counter-evidence, already on the record: *"job-apps'
  `oracle_hcm_api` dying is weak counter-evidence — its `smartrecruiters_api` and `workable_api`
  died too, and boardwatch's own versions of both work."*

## Candidate 3 — RemoteOK's public JSON API

**What it is.** `remoteok.com/api`, an unauthenticated JSON feed of remote-tagged postings. Not
discussed in any prior boardwatch decision or spec — genuinely new to this memo.

- **Aggregator or adapter:** Aggregator (a single feed spanning many employers), but a small,
  narrow-niche one rather than a broad multi-source aggregator like Indeed or hiring.cafe.
- **Body inline or per-posting fetch:** **Unverified — inferred from third-party sources only.**
  Web search (Apify scraper listings, not RemoteOK's own documentation) describes a `description`
  field present per item in the JSON payload, which if accurate would put this in the same
  free-body class as Indeed. I did not fetch the endpoint myself (out of scope per this memo's
  instructions), so this is a claim to verify with a single probe, not a fact to build on.
- **Needs the URL-dereferencing capability being built now:** Likely no for the body (if the field
  is real, the body is already inline); a `apply_url`/company-site link may still need
  dereferencing to identify the employer for company-level dedup, unverified.
- **Volume / US relevance:** Small relative to the three approved lanes — RemoteOK is a
  niche/boutique board, not comparable in scale to Indeed or hiring.cafe. **US relevance is the
  weak point by construction**: it is a *remote-first* board, so a large share of listings are
  "worldwide remote," "EU remote," etc., which the hard US-only gate will discard; the yield after
  gating is likely thin.
- **New dependency:** None — plain JSON GET via the existing `Fetcher`.
- **Already reached in the repo:** Nothing — absent from `host_class.py` and every provider/lane
  file.
- **Strongest argument against:** Even taking the best case (body inline, no dependency), the
  volume is small and skews non-US by the nature of the source, which is precisely the combination
  `CLAUDE.md`'s "breadth is last" warns against funding: work to add a source whose post-gate yield
  is unproven and likely marginal. It would also need its own first-session probe (Indeed's own
  design doc did exactly this before being trusted) before any of the "body inline" claim above can
  be relied on — right now it is a scraper community's claim, not a verified one.

## Candidate 4 — Adzuna Jobs API

**What it is.** A documented, registration-gated job aggregator API (`developer.adzuna.com`) with a
free tier (app ID + key).

- **Aggregator or adapter:** Aggregator, and unusually well-documented as APIs in this space go.
- **Body inline or per-posting fetch:** **Disqualifying, and reasonably well corroborated by
  multiple independent web sources this session (still not first-party verified by a call from
  this repo).** The free-tier response ships only a `description` **snippet capped at roughly 500
  characters**, and its `redirect_url` routes through Adzuna's own domain, not directly to the
  employer or the underlying ATS — the opposite of Indeed's shape, and worse than hiring.cafe's
  (hiring.cafe's second GET at least returns the real 3,463-character body directly; Adzuna's
  redirect is to Adzuna, an extra un-dereferenceable hop).
- **Needs the URL-dereferencing capability being built now:** Would need it, and it is unclear the
  capability being built (aggregator-link → six-provider board) even applies, since the redirect
  target is Adzuna-branded rather than a guaranteed ATS URL.
- **Volume / US relevance:** Multi-country by design (has a US locale), but the **free tier is
  capped at 250 requests/day, 25/minute** — for a body-per-posting design this caps usable volume
  at a level far below any of the three approved lanes regardless of gating.
- **New dependency:** No Python package required (plain HTTP + JSON), but it is the one candidate
  here that requires a **new kind of external dependency this project doesn't have today: a
  registered API key/credential**, which is an operational and secrets-management cost none of the
  three approved lanes or the other three candidates in this memo carry.
- **Already reached in the repo:** Nothing.
- **Strongest argument against:** Fails the primary criterion outright on the best available
  evidence — the body is not free, the redirect doesn't resolve to something dereferenceable the
  way Indeed's or hiring.cafe's does, and the free-tier request budget is small enough to make the
  per-posting-fetch problem worse, not better, than hiring.cafe's already-accepted one extra GET.

---

## Comparison and recommendation

Of the four, three fail or weaken on the same axis: Adzuna fails constraint 1 outright (body is a
capped snippet behind an un-dereferenceable redirect, plus a request budget too small to matter);
RemoteOK's constraint-1 answer is unverified community claim rather than a checked response, and its
constraint-3 answer (US relevance) is structurally weak because it's a remote-first board; and Oracle
Cloud HCM/iCIMS is not a lane at all under this project's own architecture split (design §4.1) — it's
the still-open provider question from D-278, doesn't reach the companies the whole lane program
exists for (D-278's own words), and its constraint-1 answer is unverified. LinkedIn is the only
candidate that clears constraint 4 outright (no dependency, existing `Fetcher`) and constraint 2
cleanly (unambiguously an aggregator, already present in `host_class.py`'s aggregator table), has the
best-documented request shape of the four (two named guest endpoints, a job-apps-measured 97.7% hit
rate on the fetch pattern), and needs no dereferencing step at all — but it is the only one of the
four where "aggregator, not adapter" collides with "no supported API, ToS-prohibited," and it already
carries the worst measured downstream conversion (28.3% materialization) of any lane job-apps ran.

**Recommendation, clearly overridable: if a fourth lane is added next, make it LinkedIn — but treat
it exactly as the plan doc treated Indeed, not as a inherited assumption.** That means: before
writing any client code, run the single verifying probe the Indeed plan describes (pin the guest
search endpoint, the per-posting endpoint, required headers, and one recorded response as a fixture)
rather than transcribing the community-sourced shape above, and decide explicitly whether ToS
exposure on a published, self-hosted package is acceptable to the owner — that is a values call this
memo cannot make. If the owner instead wants to close the coverage gap that motivated the lane
program in the first place (Amazon/Apple/TikTok, none of which LinkedIn as a lane would newly reach
beyond what hiring.cafe/GitHub lists already surface, per the design doc's own accounting), Oracle
Cloud HCM/iCIMS is the more honest route to that goal — but it is provider work, already flagged as
its own open question, and should be scoped and gated as such rather than folded into "lane" language.
RemoteOK and Adzuna are not worth building under the current evidence: one is unverified and thin,
the other fails the central constraint on documented, corroborated grounds.
