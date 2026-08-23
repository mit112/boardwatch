# Lane 1 request contract: hiring.cafe — pinned against the live service

**2026-08-23. One probe session, read-only. No credentials, no key, no impersonation, no TLS bypass.**
Every claim below was produced by a request made this session and is reproducible from the captured
artifacts beside this file. Nothing here is transcribed from a summary, a scraper library, or a
community write-up.

## Why lane 1 changed from Indeed to hiring.cafe

D-278 Ruling 2 put Indeed first because `description { html }` is a field of its GraphQL search
query, so the JD body cost zero extra requests. **The premise is true and the route is not
acceptable.** Read from `python-jobspy` 1.1.82's own source (`jobspy/indeed/constant.py`,
`jobspy/indeed/__init__.py`), the only route that delivers that free body is:

- `POST https://apis.indeed.com/graphql`
- `indeed-api-key: <64-hex, redacted>` — a key lifted from Indeed's iOS app, not issued
  to us. **Deliberately not reproduced here:** writing a working third-party key into this repo is
  the same act this section argues against. It is recoverable from `jobspy/indeed/constant.py` if a
  future session needs to re-verify.
- `user-agent: … Indeed App 193.1` and
  `indeed-app-info: appv=193.1; appid=com.indeed.jobsearch; osv=16.6.1; os=ios; dtype=phone`
- `verify=False` — TLS certificate verification disabled at the call site
- JobSpy additionally depends on `tls-client`, a TLS-fingerprint spoofing library

D-278 Ruling 4 governed *user-agent honesty* and permitted a browser UA on new aggregator fetches.
A browser UA says "I am a browser." This says "I am Indeed's iPhone app, and here is Indeed's own
key," inside a package boardwatch publishes for other people to self-host. The design doc's single
line on Indeed (`jd-acquisition-design.md:33`) records the free body and says nothing about
authentication, so the ruling was taken without this fact.

**Owner ruling, 2026-08-23: hiring.cafe becomes lane 1; Indeed is parked as its own decision.**
D-278 Ruling 2 is amended, not deleted — the reordering rationale ("body is free") no longer
distinguishes the two, because hiring.cafe also costs one GET per posting and is honest.

## The contract, as verified

### 1. Search — server-rendered, one GET, no API

`GET https://hiringcafe.com/` (and its search paths). **`hiring.cafe` 308-redirects to
`hiringcafe.com`** — the canonical host moved since the design was written; the `/api/` path still
answers on both.

Results are embedded in the page as `<script id="__NEXT_DATA__" type="application/json">`, at
`props.pageProps.ssrHits[]`. Sibling keys carry the paging state:

| Key | Observed |
|---|---|
| `ssrHits` | 160 postings on the homepage |
| `ssrPageSize` | 40 |
| `ssrPage` | 0 |
| `ssrIsLastPage` | `false` |
| `ssrTotalCount` | **3,886,890** |
| `ssrCompanyCount` | **123,343** |
| `ssrTimings` | `{"esLatencyMs": 365}` |
| `initialSearchState` | defaults to `United States` (derived from the caller's IP) |

**`/ssr/search-jobs` is not an endpoint.** It appears in the JS bundles and looks like one; it is a
PostHog telemetry label for the server-side fetch. `GET` and `POST` both return **404**. Checked
rather than assumed.

### 2. Body — one unauthenticated GET per posting

`GET https://hiringcafe.com/api/job-description?id={objectID}`

- Real id → **`200 application/json`**, 7,602 bytes, shaped `{"job": {"job_information":
  {"description": "<H1>…"}}}` — HTML JD body.
- Bogus id → **`404 {"error":"Job not found."}`** — a structured answer, not a block page.
- No key, no cookie, no token. Plain UA accepted.

The body is **not** in the search response: `ssrHits[].job_information` carries only
`job_title_raw`, `title`, `num_views`, `viewedByUsers`. The design doc's "one extra GET" was
accurate.

### 3. The `objectID` trap — do NOT parse it

`objectID` *looks* like `{source}___{board_token}___{id}` and is that for 128 of 160 hits. Splitting
on `___` mis-parses **36 of 160 (22.5%)**, in three distinct ways:

| Source | Count | Shape | Why a split fails |
|---|---|---|---|
| `taleo_careersection` | 16 | `taleo_careersection_harristeeter_2619805` | single underscores — a `___` split yields **one** segment |
| `fountain` | 16 | `fountain___us-3.fountain.com___wireless-vision___d545…` | the `board_token` **itself contains `___`** → 4 segments, any positional split mis-attributes |
| `saashr` | 4 | `saashr___ClairesStores___537204545` vs `board_token='clairesstores'` | case differs from the explicit field |

**`source` and `board_token` are explicit top-level keys and are non-blank on all 160 hits.** So:
read those two fields; treat `objectID` as an **opaque key for the JD endpoint only**. This is the
third appearance of one pattern — Part 2's `posting_ref='apply'` seam bug and SmartRecruiters'
constructed-URL fixture were the first two: *a value that is structured for most of the corpus is not
structured, and inverting it silently mis-attributes the tail.*

### 4. Reach — this is what the lane is for

Source mix over the 160 sampled hits, 40 distinct `board_token`s, 0 expired, 0 missing `apply_url`:

| Source | n | On our six providers? |
|---|---|---|
| `icims2` | 36 | no |
| `oraclecloud` | 24 | no |
| `saashr` | 16 | no |
| `taleo_careersection` | 16 | no |
| `fountain` | 16 | no |
| `adprecruiting` | 12 | no |
| `avature` | 8 | no |
| `adhoc` | 8 | no |
| `careerplug` | 8 | no |
| **`grnhse`** | **8** | **yes — greenhouse** |
| `paylocity` | 4 | no |
| `appone_api` | 4 | no |

**8 of 160 = 5.0% are reachable today; 95% are not.** That is D-278 Ruling 1 ("reach companies no
existing route can reach") measured directly, and it corroborates the design doc's line 34 (iCIMS /
Oracle Cloud / Taleo / UltiPro). The 5% that *are* greenhouse are the convergence case Part 2's
dereference work serves.

### 5. Other fields the payload carries

`apply_url` (the employer's real URL, e.g. `https://www.cakecareers.com/jobs/2910?lang=en-us`),
`requisition_id`, `is_expired`, `source_and_board_token`, `strict_dedup_cluster_id`,
`liberal_dedup_cluster`, `enriched_company_data`, `_geoloc`, and `v5_processed_job_data` with **91**
pre-extracted fields.

**`v5_processed_job_data` stays untrusted** — D-278 already rejected trusting it, because those
fields cite no span from the frozen JD and the keystone invariant requires a quoted span. This probe
does not reopen that.

## What this means for the build

1. **Breadth here is enormous and mostly irrelevant.** 3.89M postings, 123k companies, and the first
   sampled JD is a **Prep Cook at Cheesecake Factory** at $19.50–22.75/hour. hiring.cafe is a general
   job board, not a tech board. The US location gate, the role gate and `DEFAULT_TOP_N = 40` carry
   the entire burden of relevance, and the per-run new-company cap of 10 is the only thing standing
   between this lane and 123k company rows.
2. **Cost is one GET per posting for the body**, so the lane's request budget is the thing to design
   against — the same shape D-278 worried about for LinkedIn.
3. **The fixture must be fingerprinted, not frozen.** `ssrHits` is a live search result; a fixture
   captured today drifts by tomorrow. Per `CLAUDE.md`, derive it from live config or fingerprint it
   so drift reds the gate, and give it a `review_by` tripwire in the shape of fixture rule R15.
   A lane is **not** a registered provider, so R13's pinned-fixture-dir requirement does not apply.
4. **No dereferencing needed.** The body comes from hiring.cafe keyed by its own `objectID`; there is
   nothing to resolve to an underlying ATS in order to read the JD.

## Captured artifacts — deliberately NOT committed

The probe captured the search page (1.28 MB), the 48 JS bundles that disprove `/ssr/search-jobs`, the
verbatim `200` job-description body, and a 3-hit sample of `ssrHits`. **None of it is in this repo,
and the reason is worth recording because the gate is what caught it.**

Staging the two small JSON captures failed `make check` on three counts, all correct: R2 flagged a
real employer contact address (`ats@…`) inside the JD body, and R7 refused both files as data not
registered in `SHIPPED_DATA`. Registering them means declaring a `provenance` — and the only honest
value, `public`, obliges the entry to state a **license**. There is no license for a third party's
job-description text. boardwatch would be redistributing scraped employer content from a public
repository, and "none granted" is not a license.

So the rule stands as written: **do not ship it.** What the build actually needs from this probe is
the *shape* — endpoint, method, status, key names, nesting, and the `objectID` counter-examples — and
all of that is in this document, in prose, with the counts that make it checkable.

**Every claim here is re-derivable with two unauthenticated requests and no credentials:**

```
curl -s https://hiringcafe.com/ | \
  python3 -c 'import sys,re,json; d=json.loads(re.search(r"__NEXT_DATA__\" type=\"application/json\">(.*?)</script>", sys.stdin.read(), re.S).group(1)); h=d["props"]["pageProps"]["ssrHits"]; print(len(h), h[0]["objectID"], h[0]["source"], h[0]["board_token"])'

curl -s "https://hiringcafe.com/api/job-description?id=<objectID>" | head -c 300
```

When the lane build needs a real fixture, it must be **authored to the observed shape** rather than
captured wholesale, and it needs the drift guard named above — a fixture that freezes a live search
result is precisely the one `CLAUDE.md` warns sits still while the service churns. Note the tension
and do not resolve it by reflex: an authored fixture only proves what our own code constructs
(D-284's SmartRecruiters lesson), so the shape it is authored to must trace back to the counts in
this document, not to a later session's guess.
