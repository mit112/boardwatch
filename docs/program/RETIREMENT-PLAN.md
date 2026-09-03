# Retiring job-apps — the plan of record

**Established:** 2026-09-01, from run 140 and job-apps' own source code.
**Why this file exists:** every session since the `jobapps` lane shipped has re-derived the same
comparison and then reached for a boardwatch knob. The research is done. This file holds the
finished analysis so no future session repeats it, and states what to BUILD.

**Read this with `PROGRAM.md` §1.** That bar (B1-B7, 14 frozen days) measures whether boardwatch
works. **This file measures something different and narrower: whether boardwatch finds what
job-apps finds**, which is the owner's stated condition for switching job-apps off. B1 is already
met ~9.6x; this is not.

---

## 1. The bar, and where we stand

**GATE 1 IS NO LONGER A COVERAGE PERCENTAGE. It is PER-SOURCE RECALL, a rate (D-421, owner's call
2026-09-02).** D-399's ">= 80% of job-apps' eligible set" is **RETIRED**, and so is the "cover most
of what job-apps does daily" wording that briefly replaced it. Do not re-derive either.

**Why the old bar was withdrawn.** It counted `disposition_events` at `stage='eligibility'` with
`outcome IN ('eligible','protected_applied')` — a population that (a) changes and grows every day,
so no two readings share a denominator, and (b) **only exists once the owner manually works a
cohort.** It excluded `moved` (3,963 postings → the apply queue, three times larger than `eligible`)
and `review` (2,484), and 2026-08-31/09-01/09-02 carry zero `eligible` and zero `moved` at all. The
"216" tracked the owner's processing, not boardwatch's coverage.

**The instrument now:** for each source job-apps draws from, the fraction of its finds that
boardwatch holds INDEPENDENTLY — "independent" still meaning an origin that is not the `jobapps`
lane, keyed on the lane's own provenance stamp in `postings.raw_json` (D-399's discriminator, which
remains the only sound one). Script:
`.agent/2026-09-02-session/per_source_recall.py`, read-only.

**THE INSTRUMENT'S OWN PROPERTY, MEASURED 2026-09-03 AND NEVER PREVIOUSLY RECORDED — READ IT BEFORE
SETTING ANY THRESHOLD.** `status_of` unions THREE keys: normalised URL, ATS `(slug, posting-ref)`
identity, and normalised `(company, title)`. **For 87% of job-apps' volume only the third key can
ever fire**, so for those sources the headline is an *equivalent-role* match and NOT a
posting-identity match. Measured over the run-147 window: job-apps records an AGGREGATOR host as its
`canonical_direct_url` for **18,793 of 21,497** postings (linkedin 10,031, indeed 7,771, jobright
991), and **0.0% of those are ATS-parseable** — so neither the URL key nor the identity key can match
them even when boardwatch genuinely holds the job off the employer's own board. Remove the
`(company, title)` union from `status_of` and independent recall falls **25.7% -> 2.6%**.

**2.6% is NOT a lower bound on real recall.** It measures URL agreement, and the strict key is
structurally incapable on an aggregator host — 0.0% strict on every one of linkedin.com,
indeed.com and jobright.ai. Where identity IS checkable the two keys agree closely:
`job-boards.greenhouse.io` 55.7% strict / 55.7% loose, `boards.greenhouse.io` 85.0% / 90.0%,
`jobs.lever.co` 52.9% / 55.9%, `jobs.ashbyhq.com` 47.9% / 63.8%. **That 0–16 point spread does NOT
transfer to LinkedIn**, because those four are boards boardwatch scans directly, where a
`(company, title)` hit is near-certain to be the right requisition.

**The fuzzy key is also MANY-TO-ONE, in both directions.** 1,763 boardwatch postings carry the
`jobapps` provenance stamp, yet they account for **8,244** `lane-only` classifications — ~4.7
job-apps postings shadowed per stamped posting. One boardwatch record for `(amazon, software
engineer)` marks EVERY job-apps posting sharing that normalised pair. So `lane-only` overstates what
boardwatch actually holds, the true `absent` count is higher than the table below, and `independent`
inherits the same inflation. **The property is identical in every reading, so the SERIES is
comparable; what it bounds is the meaning of the LEVEL** — which is exactly what a numeric threshold
would fix. Do not set one without this on the page. Reproduce by re-running `status_of` with the
`by_ct` union deleted, and check it against a host whose URLs ARE parseable as the control.

**Where we stand — run 147, 14d window 2026-08-21..09-03, 21,497 postings; run 143's first reading
kept beside it so the direction is readable, NOT averaged with it (the windows differ by one day):**

| | run 143 (first reading) | **run 147 (current)** |
|---|---|---|
| **recall, drawn-from sources** | 4,913 of 20,653 = 23.8% | **5,377 of 20,289 = 26.5%** |
| employer's own board (lever/ashby/greenhouse/workday) | 94–100% | **86–100%** |
| aggregator + search (linkedin/hiringcafe/indeed) | 12–33% | **16–35%** |
| **lane-only — what dies at switch-off** | 7,091 (32.4%) | **8,244 (38.3%)** |
| never held at all | 9,715 (44.4%) | **7,719 (35.9%)** |
| **independent if job-apps stopped today** | 5,057 of 21,863 = 23.1% | **5,534 of 21,497 = 25.7%** |
| source coverage (sources boardwatch draws from) | 94.4%; 99.6% ex-jobright | unchanged |

**READ THE `lane-only` ROW, NOT THE TOP ONE. `absent` FELL 8.5 POINTS AND ONLY ~2.6 OF THEM BECAME
INDEPENDENT — THE OTHER ~5.9 BECAME DEPENDENCY.** Between the two readings the `jobapps` lane
harvested more of job-apps' own tree, which converts `absent` into `lane-only`: progress on HOLDING
the posting, regress on the only thing retirement needs. Switch-off exposure went UP, 32.4% ->
38.3%.

**The MARGINAL rate is well above the trailing average, and that part is real.** Per-day independent
recall: 08-21 20.4%, 08-27 23.8%, 09-02 32.3%, **09-03 34.0%** — the fleet went 379 -> 453 boards and
Indeed armed on 09-02, so the 14-day average is dragged down by days that ran a smaller system.
**Per-day `lane-only` shows NO such trend**: it sits at 32–42% on every one of the 14 days, 09-02 at
42.0% and 09-03 at 32.7%. So the exposure is steady-state, not a backlog artifact that will clear.

**`indeed` is 6,568 of the 8,244 — 80% of the entire switch-off exposure**, against linkedin 892 and
hiringcafe 459. See §6's re-scoping note before quoting D-417 at it.

**No numeric threshold is set, deliberately.** A single number averages a solved mechanism against
an unsolved one, which is precisely how the 80% bar concealed that the direct-ATS half was already
at ~100%. The threshold is the owner's to set **per source**.

Gate 3 (anti-degradation, independent count must not fall) **HELD at 49**, baseline 44.

---

## 2. The gap, decomposed — do not re-derive this

> **The "80%" figures below are the RETIRED bar (§1, D-421).** The tier decomposition, the per-tier
> ceilings and the "no path that skips both C and D" conclusion all still stand — they are statements
> about where job-apps' postings live, which did not change. **Only the threshold they are measured
> against was withdrawn.** Read them as sizing, not as a gate.

Of the **168** misses (131 held nowhere, 37 held only via the `jobapps` lane), grouped by the host
of job-apps' `canonical_direct_url`:

| tier | postings | what it needs |
|---|---:|---|
| **A. providers boardwatch ALREADY has** | **11** | company admission / a `gh_jid` resolver pattern. No new adapter. |
| **B. linkedin.com** | **77** | LinkedIn discovery method (§4). Existing lane, existing endpoint. |
| **C. indeed.com** | **35** | an Indeed source. **BLOCKED — owner decision, §6.** |
| **D. everything else** | **45** | new adapters across ~30 vendors (Oracle HCM 6, iCIMS 3, UKG 3, Avature, Paylocity, Breezy, Rippling, jibeapply, PageUp, governmentjobs, first-party career sites) |

### The arithmetic that decides the plan (DERIVED, ceilings — assumes a tier is FULLY solved)

```
have 48                                          22.2%
+ A existing providers  (11)  ->  59             27.3%
+ B linkedin            (77)  -> 136             63.0%
+ C indeed              (35)  -> 171             79.2%   <-- STILL ONE SHORT of 172
+ D new adapters        (45)  -> 216            100.0%
```

**Consequence, stated plainly: there is no path to 80% that skips both C and D.** Even solving
A + B + C perfectly lands at 79.2%. The goal requires tier D work regardless of the Indeed call.

Of tier B's 77: **58 are companies boardwatch has never seen at all**, 11 are companies present
via LinkedIn whose posting we missed, 8 are companies held only via another provider. MEASURED.
This is why page-depth knobs cannot close it — `lane_search_pages` reaches at most those 11.

---

## 3. job-apps' sources — the full list, and what boardwatch has

From `SOURCE_REGISTRY` in job-apps' `discovery_attribution.py`. **33 registered sources — but only
15 of them PRODUCE ANYTHING, measured 2026-09-02 (D-421).** Over the 14 days 2026-08-20..09-02
job-apps discovered 21,863 distinct postings, and the other 18 sources contributed **zero**: google,
themuse, remotive, remoteok, jobicy, himalayas, adzuna, higheredjobs, handshake, indeed_mcp, zapply,
amazon_api, eightfold_api, oracle_hcm_api, radancy_api (1 posting), smartrecruiters_api,
workable_api and hn's newsletter siblings. **So the replacement target is 15 sources, not 33** — the
"5 untried public APIs, no posture question" row below and the three `first_party` rows are NOT work
items until they produce something. Live volume is concentrated: **linkedin 46.3%, indeed 35.4%,
hiringcafe 11.4% = 93.1%**, and the sources are nearly disjoint (0.3% of postings found by more than
one). The number in parentheses is job-apps' own attribution ordinal (lower wins a tie).

| job-apps source | class | boardwatch |
|---|---|---|
| indeed (0), google (0) | JobSpy | **NO** |
| linkedin (0) | JobSpy | partial — own lane, different method (§4) |
| simplify (10), speedyapply (11), zapply (13), vanshb03 (14) | github_list | company discovery only, **not a posting source** (D-291: the lists carry no JD body) |
| jobright (12) | aggregator | **REFUSED** (D-406) |
| hiringcafe (30) | aggregator | **YES** |
| unemployed (20) | newsletter | NO |
| themuse (40), remotive (42), remoteok (44), jobicy (45), himalayas (46) | **public_api** | **NO — 5 untried public APIs, no posture question** |
| adzuna (43) | aggregator | NO |
| hn (41) | community | NO |
| higheredjobs (50), insidehighered (51) | university | NO |
| handshake (90) | university | NO |
| indeed_mcp (60) | indeed | NO |
| greenhouse / lever / ashby / workday / smartrecruiters / workable `_api` (80) | direct_ats | **YES — all six** |
| radancy_api (80) | direct_ats | NO |
| amazon_api, eightfold_api, oracle_hcm_api (80) | **first_party** | **NO — these map onto tier D** |

**job-apps' own measured yield** (6 cohorts, unique postings -> resumes actually built), from its
`docs/boardwatch/advice-to-boardwatch-2026-08-19.md`:

```
hn 11.43% · simplify 5.12% · hiringcafe 4.59% · speedyapply 3.12% · linkedin 1.95%
jobright 1.45% · insidehighered 1.30% · indeed 1.02% · vanshb03 0.91% · lever_api 0.89%
zapply 0.23% · ashby_api 0.13% · greenhouse_api 0.02% · workday_api 0.00%
```

Direct ATS 8,149 unique -> 13 built (0.16%). Aggregators/lists 16,913 -> 272 (1.61%). **10.1x.**
Read this as: the six providers boardwatch is built on are its *lowest*-yield sources, and the
high-yield ones are curated lists and aggregators. Caveat job-apps states itself: `built` is
downstream of ITS prefilter, so measure our own version before acting.

**MEASURED 2026-09-02, and it corrects the inference above (D-421).** Low *yield* is not low
*recall*, and the two point opposite ways. Per-source recall — the fraction of job-apps' finds from
a source that boardwatch holds INDEPENDENTLY — splits **binarily on mechanism**: where boardwatch
reads the employer's own board it is **94–100%** (lever 100%, ashby 98.2%, greenhouse 97.6%, workday
94.1%); where it reads an aggregator or a search surface it is **12–33%** (linkedin 32.5%,
hiringcafe 17.0%, indeed 12.6%). **The six ATS providers are the only part that fully works.** They
are a small share of job-apps' volume, so they cannot close the gap alone — but they are not the
weakness this table reads as.

---

## 4. How job-apps searches LinkedIn — the mechanism boardwatch lacks

job-apps runs **three** LinkedIn mechanisms through JobSpy (`site_name=["indeed","linkedin"]`).
boardwatch has none of them.

1. **Per-target-company queries.** `query = f'"{company}" software engineer'` over
   `target_companies.json` (222 entries), then verifies the RETURNED employer against the queried
   one (`match_target_company`). This reaches named companies deterministically, including ones
   whose boards are on no ATS boardwatch scans.
2. **Hub-pinned geo nets.** `NET_TERMS` (5 new-grad terms) x `HUB_LOCATIONS` (7 US metros) = 35
   combos, **12 rotated per run**, full matrix covered in 3 days, 8 results each. job-apps' own
   comment: *"Hub-pinned search nets: geo-listed roles that 'USA'-wide queries miss."*
3. Generic USA-wide terms — **off by default** on the scheduled path (`search_terms=[]` unless
   `--search` is passed).

**boardwatch's lane** sends 22 generic role facets derived from `profile.target_titles_json`, with
**no `location` parameter**, `f_TPR=r86400` (24h), paginated by `lane_search_pages`.

### The false claim that kept this closed — REFUTED 2026-09-01

`lanes/linkedin.py::page_url`'s docstring said `location=` "was measured to return an id-identical
set". **That is false.** Probed live against the lane's own endpoint
(`/jobs-guest/jobs/api/seeMoreJobPostings/search`), browser UA, `f_TPR=r604800`,
`keywords=software engineer new grad`:

| request | cards | overlap with no-location | geography |
|---|---:|---|---|
| no `location` (what we send today) | 10 | — | 0 of 10 in TX |
| `location=Austin, TX&distance=25` | 10 | **0 shared** | **9 of 10 in TX** |
| `location=Boston, MA&distance=25` | 10 | **0 shared** | **10 of 10 in MA** |

`location=` binds, filters geographically, and returns a **disjoint** population. The `f_WT=2` half
of that docstring was NOT re-probed and stands as recorded.

**JobSpy's LinkedIn backend uses the same endpoint boardwatch already calls, with a plain browser
UA and no credential** — so adopting its method is posture-neutral for LinkedIn. That is NOT true
of its Indeed backend (§6).

---

## 5. The plan — built for PARALLEL execution

**Optimize for wall-clock, not for tidiness.** The tracks below are independent BY FILE, which is
what makes them safe to run at once. The one thing that would force them to serialize is the
shared registration surface, so Wave 0 exists to remove it.

### The constraint that shapes everything

Every new lane wants `Settings` fields, and a new field must be registered in FOUR gated sites
plus `runner.py` (§8). Those five files are shared by every track. **Two agents editing them
concurrently conflict and you lose the parallelism you paid for.**

### Wave 0 — shared plumbing, ONE agent, land it first (~1 gate)

One small PR that adds **every** settings field all tracks need, all at once, and wires each lane's
factory slot in `runner.py`. No lane logic. After it lands, no track needs to touch these files
again.

| field | for | default |
|---|---|---|
| `lane_search_hubs: tuple[str, ...]` | Track A | `()` — inert |
| `lane_hub_combos_per_run: int` | Track A | 12 |
| `lane_hub_distance_miles: int` | Track A | 25 |
| `indeed_search_pages: int` | Track B | 1 |
| `indeed_results_per_page: int` | Track B | 100 |

Register each in: `cli/config_cmd.py::_SCALAR_KEYS`; `tools/generalization/snapshots.py` (BOTH
dicts); `reports/manifest.py::_CONFIG_IRRELEVANT`; `core/settings.py`. All are acquisition knobs —
`_CONFIG_IRRELEVANT`, never `_CONFIG_RELEVANT`.

### Wave 1 — four tracks, fully concurrent, one worktree each

| track | owner | files it OWNS (no overlap) | ceiling | depends on |
|---|---|---|---|---|
| **A. LinkedIn geo nets** | luna | `lanes/linkedin.py`, `lanes/facets.py` | part of +77 | Wave 0 |
| **B. Indeed lane** | luna | **new** `lanes/indeed.py` | +35 | Wave 0 |
| **C. `gh_jid` resolver** | luna or deepseek | `core/board_urls.py` / `lanes/dereference.py` | +5 gate-1, 7,406 store-wide | nothing |
| **D. Drop audit** | Claude | **no source files** — a script under `.agent/` | unknown, likely large | nothing |

Track D touches no source file, so it can run through the others' gate time for free. Start it
first and let it soak.

### Wave 2 — tier D adapters, after Wave 1 lands

~30 vendors, ranked: Oracle HCM (6), iCIMS (3), UKG/UltiPro (3), then singletons. **Mandatory** —
§2's arithmetic shows 80% is unreachable without part of this.

**CRITICAL DESIGN FACT, do not rediscover:** these must be **LANES, not `Provider`s.** Registering
a seventh provider is blocked two ways (D-278 §4.1) — `test_build_providers_one_instance_per_class_keyed_by_name`
asserts `set(built) == {the six names}` as a set EQUALITY, and fixture rule R13 demands a pinned
fixture dir per registered provider and fires immediately on one with none. A lane returns the same
`BoardSnapshot` and inherits every persistence invariant for free.

Vendors are independent of each other, so Wave 2 is itself N-way parallel once one adapter has set
the shape. Do the first one alone, then fan out.

### Gate scheduling — the real bottleneck

`make check` is ~6-12 min and CPU-bound. **Cap at TWO concurrent** — a contended gate reports
`Error 143` (SIGTERM under load) and reads as a false negative.

So: let agents WRITE concurrently (cheap, no CPU contention) and QUEUE the gates. Four tracks
finishing together means ~2 gate slots x 2 rounds ≈ 25 min of gate time, not 4 x 12 serial. Run
each gate from its own worktree venv and always print `boardwatch.__file__` to confirm which tree
is under test.

### Review

`gpt-5.6-sol` reviews each track read-only, delegation forbidden, findings in the RETURN not a
file. Reviews cost no gate time, so they overlap gates freely. **A review is worth it** — sol
caught a blocker on the SmartRecruiters change that the author and the orchestrator both missed
(the fix could not reach the 2,992 stored rows because `known_posting_ids` excludes them).

### Order of dispatch for the next session

1. Start Track D (drop audit) — no gate, no conflicts, soaks in the background.
2. Land Wave 0. One gate.
3. Dispatch A, B, C together with full briefs. Queue gates two at a time.
4. sol-review each as it lands; land the green ones.
5. Re-read gate 1 after one run. Then Wave 2.

**Do not stop to re-derive §2, §3 or §4.** They are measured and reproducible via §9.

## 6. Indeed — APPROVED by the owner 2026-09-01, and how to build it

Tier C is 35 postings / 16.2 points, and §2 shows the 80% bar is very hard without it.

**Both Indeed routes were probed live on 2026-09-01:**

1. **JobSpy's Indeed backend** works (15 full JDs in 1.2 s; `job_url_direct` resolves to employer
   boards). It reaches `apis.indeed.com/graphql`, whose `robots.txt` is
   `User-agent: * / Disallow: /`, by presenting Indeed's **own iOS app credentials** —
   `indeed-api-key`, `user-agent: ... Indeed App 193.1`, `indeed-app-info: appid=com.indeed.jobsearch`
   — plus `tls-client` for TLS-fingerprint impersonation.
2. **The robots-ALLOWED public search path** (`Allow: /*&start=0&` ... `&start=90&`) returned one
   HTTP 200 with 217 parseable cards, then **HTTP 403 "Security Check - Indeed.com"** with a
   captcha on the next request. It cannot sustain a daily lane.

**The owner reviewed both routes and approved route 1 on 2026-09-01. The decision is closed; do
not re-open it.** Containment that matters more than repo visibility: `lanes_enabled` ships EMPTY,
so the lane is opt-in and changes nothing for anyone running the published package who does not
name it.

**Build it NATIVELY, not via the JobSpy dependency.** Measured 2026-09-01: JobSpy's Indeed backend
runs `is_tls=False` (plain `requests`), so `tls-client` is not needed, and `numpy==1.26.3` +
`pandas` exist only for its DataFrame output. `numpy` 1.26.3 has no cp313 wheel and builds from
source (~34 s locally, needs a C compiler) — a per-CI-job cost for nothing.

A plain `httpx` POST reproduces it exactly. MEASURED: **one request, 0.57 s, 100 postings, 100 of
100 carrying a full inline JD** (1,595-7,506 chars), plus a `nextCursor` for pagination. Against
the LinkedIn lane's measured 2.39 s per body, that is ~420x cheaper per JD.

    POST https://apis.indeed.com/graphql?co=US
    headers + `job_search_query` template: read them from jobspy/indeed/constant.py
    date filter format is HOURS: filters: { date: { field: "dateOnIndeed", start: "24h" } }

Field mapping for `RawPosting`: `employer.name` -> company; `title`; `key` ->
`provider_posting_id`; `description.html` -> `html_to_text` -> `body_text`;
`location.formatted.short` -> locations; `datePublished`; and **`recruit.viewJobUrl` is the
employer-board URL** — dereference it with `parse_board_target`/`parse_posting_target` and register
the company under its REAL provider when it resolves, exactly as the hiring.cafe lane does (#304).
That is better for gate 1 and for dedup than registering everything under `indeed`.

**RE-SCOPED 2026-09-03: THE "35" BELOW IS A RETIRED POPULATION, AND D-417's "FIXES ITSELF IN ~7
DAILY RUNS" MUST NOT BE QUOTED AT THE CURRENT ONE.** D-417 measured Indeed against the old
216-posting gate, where tier C was 35 postings. Under the current instrument Indeed carries
**7,771 job-apps finds, 15.5% independent recall, and 6,568 `lane-only` — 80% of boardwatch's
entire switch-off exposure.** Three things make "self-healing" false at that scale, all MEASURED
2026-09-03: `indeed_search_pages` is at its FLOOR of 1 and `indeed_results_per_page` at its MAX of
100, so the per-run ceiling is fixed at facets x 100; run 145's lane contributed **158** new
postings against job-apps' **~555/day** off the same endpoint; and the lane's date filter is
**`24h`**, so postings already in the `lane-only` bucket can never be found by it — they only leave
the metric as the 14-day window slides. Per-day `lane-only` confirms it empirically: 32–42% on
every one of the 14 days, with no downward trend. **Indeed is the largest and cheapest remaining
lever, and it needs a sizing, not a wait.**

Note the 35 are `lane-only`, not absent: boardwatch **already holds** these postings via the
`jobapps` lane. They fail gate 1 only because that lane is their sole origin. So a second
possibility exists and is untested: **Phase 1/2 may pick some of them up from LinkedIn**, since a
job posted to Indeed is often posted to LinkedIn too. Measure that after Phase 1 before treating
tier C as blocked.

---

## 7. Settled — do not re-litigate

- **Jobright lane: REFUSED both shapes** (D-406). No JSON-LD, no employer JD field, no employer
  board URL, `parse_board_target` resolves 0 of 882 README links.
- **GitHub lists are company discovery, not a posting source** (D-291). 34,984 records, zero
  description-shaped fields; the engine is body-only.
- **`lane_posting_budget` is not the LinkedIn constraint** (D-407/#320). Run 139: the lane reached
  162 of 300, and its 520 `not_attemptable` are 76.2% cross-facet duplicates.
- **`lane_search_pages` reaches at most 11 of the 77.** Raised 5->10 on 2026-09-01; recommend
  reverting to 5 once Phase 1 lands, since it costs ~+2.3 min/run and doubles hiring.cafe's volume
  on a robots-disallowed path for <=11 postings.
- **A JD-body recovery layer does not close this gap.** 0 of 61 `jobapps`-lane stubs dereference
  to a provider posting or a board. The genuinely-thin population is low hundreds, not thousands.
- **The body floor does not generalize beyond the LinkedIn lane.** `MIN_SECTION_MARKERS >= 1` is
  calibrated for LinkedIn's HTML shell: it false-positives on 2,571 of workday's 2,795 and 1,687
  of lever's 1,972 below-floor bodies, which are real JDs failing only the marker rule. Extending
  it to the ATS path as-is would drop ~4,500 real JDs. Fix the rule before reusing it.
- **Workday slugs are not lowercased** (D-401/D-339). No cross-source suppressor (D-397). The
  ranker is not recency-dominated (D-395).

---

## 8. Mechanics a future session should not rediscover

- **Adding a `Settings` field trips FOUR gated sites**, none caught by targeted pytest:
  `cli/config_cmd.py::_SCALAR_KEYS`; `tools/generalization/snapshots.py` (BOTH
  `EXPECTED_SETTINGS_DEFAULTS` and `SETTINGS_FIELD_CLASS`); `reports/manifest.py`
  (`_CONFIG_RELEVANT` vs `_CONFIG_IRRELEVANT`); the field itself.
- **Lane/acquisition knobs go in `_CONFIG_IRRELEVANT`.** They decide how much corpus arrives, not
  how it is judged. Classifying one IN restamps `policy_version` and stales every permanent
  disposition — a corpus-wide drain from a knob that judged nothing.
- **A lane must emit `status="partial"`, never `"complete"`** — `_process_missing` runs on
  `complete` only, and an empty `complete` marks every open posting of that company missing
  (D-278 §4.2).
- `postings.raw_json` is a **JSON column**: a SELECT hands back a decoded dict, not a string. A
  fixture that seeds a JSON *string* tests the code against itself.
- `runs.status='ok'` and `finished_at` are written **before** the tailor/pdf/delivery phases, so
  neither is a completion signal. Read the process, or a per-launch sentinel.
- Read the live store only via Python `sqlite3` with `?mode=ro`.

## 9. Reproducing every number here

```sh
# gate 1 / gate 3 / coupling
./.venv/bin/python .agent/2026-09-01b-session/retirement_readiness.py

# the tier decomposition and the 80% arithmetic (§2)
./.venv/bin/python .agent/2026-09-01d-session/gate1_gap.py

# why tier B is missed: never-seen vs present-but-missing (§2)
./.venv/bin/python .agent/2026-09-01d-session/li_miss.py
```

job-apps' own sources of truth, read-only: `SOURCE_REGISTRY` in `discovery_attribution.py`;
`HUB_LOCATIONS`/`NET_TERMS`/`hub_search_nets` and `_scrape_single_target` in `job_discovery.py`;
`target_companies.json`; `docs/boardwatch/advice-to-boardwatch-2026-08-19.md`.
