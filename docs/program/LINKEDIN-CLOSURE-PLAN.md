# The LinkedIn gap — sized, and the recommendation is ACCEPT THE LOSS

> **Read this before proposing any LinkedIn work.** It exists so the comparison below is never
> re-derived, and so JobSpy is not re-proposed. Reasoning: **D-431**, re-measured on the full
> population by **D-453**. Retirement context: `RETIREMENT-PLAN.md`, **D-421**, **D-424**.
>
> **The bottom line, so nobody reads three tracks as a work queue: the defensible residual is 395
> postings = 28/day (D-453). Track 1 is over-sized 3.4x, Track 2 is built and disarmed on
> measurement (D-437), and Track 3 is closed.** What is left in this file is the sizing, not a plan
> to execute.

## Where LinkedIn sits among the sources

Gate 1 is per-source recall (D-421). Standing per source, run 147:

| source | standing, run 147 (2026-09-03) |
|---|---|
| employer's own boards (lever/ashby/greenhouse/workday) | **86–100% — solved** |
| **indeed** | **0 absent, 6,568 lane-only — 80% of the entire switch-off exposure.** **It does NOT convert by itself (D-452).** Its binder is the new-company admission cap, which discards 24–51% of every fetched hit set and refused **80 tier-1 employer boards** in one run; and its `24h` window means postings already in `lane-only` are unreachable. **There IS new work here, and it is the largest lever on the board.** |
| hiringcafe | a board-fleet gap (D-425); the 50-board sample cost ~20x its sizing and the remaining 282 boards are refused (D-441). Lane throughput is nonetheless worth **1,331 postings / +6.19pp** (D-451) |
| jobright | REFUSED deliberately (D-406) |
| **linkedin** | **the largest residual — and the recommendation is ACCEPT THE LOSS (D-453)** |

**The retirement test is `lane-only` falling to a level the owner accepts losing (D-424).** **Indeed
is the bigger number and does not self-heal (D-452); LinkedIn is the bigger LOSS, because its
postings are absent rather than merely dependent.** So this file sizes LinkedIn; it no longer claims
LinkedIn alone decides retirement.

## The gap, decomposed — 5,650 absent LinkedIn postings, run-147 window to 2026-09-03

**Re-established on ALL 5,650 (D-453).** D-431 measured 5,876 in the previous window and D-417 used
a 77-posting sample; this reproduces D-431's shape **within 2pp**, so the decomposition is stable and
only the population moved.

| bucket | employers | postings | share | reachable how |
|---|---:|---:|---:|---|
| employer not in the store under **any** key | 1,609 | 2,606 | 46.1% | needs discovery |
| known, but only a **lane placeholder** row (no board) | 364 | 2,283 | 40.4% | **name is known** |
| known + **real ATS row → admissible today** | **108** | **403** | 7.1% | `companies import` |
| already watched (a real coverage miss) | 79 | 358 | 6.3% | search breadth |

**2,160 distinct employers**, and the loss is long-tailed rather than concentrated: top 10 = 737
postings (13.0%), top 100 = 2,233 (39.5%), and **1,392 employers have exactly one** absent posting
(24.6% of volume). The head is major employers on proprietary career sites — Google 115, Amazon 95,
AMD 86, Walmart 74, JPMorganChase 67, Qualcomm 66, Deloitte 63, AWS 62, GM 56, IBM 53 — **a class
D-311 already refused adapters for.**

**Three corrections this measurement forced (D-453), on top of D-431's two:**

1. **D-417's "these employers plausibly have no ATS board" is REFUTED at scale, and the not-in-store
   head needs two names struck: Perplexity and Illumio ARE in the store**, via `ashby:perplexity`
   and a workday-style slug key. The rest of that head (Raytheon, Netflix, Weights & Biases,
   Upstart, NinjaOne, U.S. Bank) stands. This is a **discovery** gap, not an architecture limit.
2. **A "known" employer is usually NOT admissible.** `linkedin:google`, `jobapps:ibm`,
   `hiringcafe:adhoc:amazon` are lane-provenance placeholders, not boards; `companies import` takes
   only the six real ATS providers. Board admission therefore reaches **7.1%**, not 46%.
3. **The decorated-name undercount is real but ~1%, so it does not rescue the table.** A slug-exact
   key saved 13 employers / 46 postings and a name-prefix key 24 / 48, about half of the latter
   false positives (`Nike` → "Nike Consultant"). Null controls: 300 salted nonsense names → **0/300**
   in store; the `independent` set → **446/446 (100%)** against 53.9% for absent.

**53.9% (3,044) of the absent set is at an employer boardwatch ALREADY KNOWS BY NAME** (358 watched +
403 admissible + 2,283 placeholder).

## THE NUMBER THAT DECIDES THIS FILE — only 40.4% of the loss would ever be shown

**Run boardwatch's own live gates over the 5,650 and only 2,281 (40.4%) reach the shortlist at all.**
`exclude_titles` vetoes **3,130 = 55.4%** (Senior 1,617, Staff 461, Sr 354, II 300, III 196,
Principal 184); `role_gate` `not_swe` 87; `seniority_gate` `above_band` 152; **the location veto
fired ZERO times.**

**The controls are what make this honest rather than convenient.** The `independent` set keeps
**40.8%** — nearly identical, so **the absent set is NOT preferentially junk**, which is the
uncomfortable direction. `lane-only` keeps 97.0%, which it must, being job-apps' filtered output by
construction.

Intersected with **job-apps' own verdict** on the same 5,650 (its `disposition_events`): no
disposition **3,407 (60.3%)**, ended at prefilter 614 (10.9%), ended at scaffold 1,133 (20.1%),
**reached its apply pipeline 401 (7.1%)**. Control: the `independent` set reaches its pipeline at
8.1% — the same rate, so this is not a bucket artefact.

**THE TIGHTEST DEFENSIBLE LOSS: absent AND boardwatch would keep it AND job-apps itself carried it
= 395 postings = 28/day**, at 318 employers (1.24 each; Amazon 14, AWS 7, IBM 6, GM 5). Of those 395
only **176 (12.6/day)** sit at an employer boardwatch already has a row for — **176 is the entire
free ceiling of any query-shaped mechanism.**

**The recommendation is ACCEPT THE LOSS (D-453).** No track below changes 28/day by an order of
magnitude.

## JobSpy is REFUSED, on measurement (D-431)

The owner asked directly whether to adopt JobSpy as a side-lane. **It buys nothing boardwatch does
not already have**, and that is measured, not argued:

- **Identical transport.** JobSpy's LinkedIn backend calls
  `https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search` — **the same guest
  endpoint `lanes/linkedin.py:98` already calls**, with the same `f_TPR` recency parameter. Bodies:
  JobSpy GETs `/jobs/view/{id}`; boardwatch GETs `/jobs-guest/jobs/api/jobPosting/{id}`.
- **No new capability, only a browser UA and more queries.** The only substantive differences are a
  Chrome user-agent string and the number of query cells issued.
- **Cost of taking it:** `tls-client`, `numpy` and `pandas`, for a DataFrame boardwatch does not
  want. **D-414 already refused JobSpy for exactly this reason** when building the native Indeed
  lane, and built natively instead. Same answer, same grounds.
- **Its scrapers decay.** job-apps' own source: *"glassdoor + zip_recruiter removed 2026-07-01: 100%
  error rate since at least 06-29, Zip actively 429-blocking."*

**Do not re-propose JobSpy.** If a future session believes it has an argument, the argument must be a
*capability* boardwatch's guest-endpoint lane cannot reach — not volume, which is a config knob.

**Viability of the endpoint itself is confirmed, so the lane is not the doubt.** Probed live
2026-09-02 through JobSpy: two queries, **25/25 rows carried a description each time**, median
**5,771** and **5,121** characters, **28s per 25-posting query with bodies**. LinkedIn serves long,
usable JDs to an unauthenticated guest request today.

## The plan — three tracks, cheapest first

### Track 1 — admit the already-admissible boards (no new code) — **OVER-SIZED 3.4x (D-453) — CLOSED 2026-09-05: the owner ruled ACCEPT THE LOSS (D-482)**

**403 absent postings sit at 108 employers whose `companies` row already carries a real ATS
provider+slug — but 382/92 was never the yield, and neither is 403/108.** Priced on what boardwatch
would actually keep:

| basis | postings | per day | boards |
|---|---:|---:|---:|
| raw absent at an admissible employer | 403 | 29 | 108 |
| **survives boardwatch's own gates** | **113** | **8** | **52** |
| **and job-apps itself carried it** | **13** | **0.9** | **10** |

- **Cost: 108 boards × 3.2 s ≈ 5.8 min/run, forever** — paid in full whichever basis you believe.
- **Owner's call before importing.** It spends run budget permanently for 8/day at best.
- Generate candidates with the D-428 pattern, `companies import --verify`.
- Snapshot `companies` to CSV first; that is the reversal artifact, not a DB copy.
- **D-441 is the caution to read, not D-417's:** the last board sample admitted on a per-board
  posting estimate cost ~20x its sizing, because admitting a board scans its **entire open
  inventory**, not its in-window slice.

### Track 2 — per-company query cells in the EXISTING native lane — **BUILT, DISARMED (D-433)**

> **SHIPPED 2026-09-02, and this section's own sizing was REFUTED before it was.** The shape below —
> every profile term crossed with every company — is **25,368 cells** against the live store, and at
> the measured cadence of 83 runs in 14 days a full pass at 12 cells a run takes **358 days**.
> Nothing is ever revisited, so nothing it buys can be read. **What shipped is ONE term × the 443
> WATCHED companies = 443 cells, a full pass every ~37 runs (~6.3 days)** — the owner's call with
> four shapes priced, and the only one readable before the 2026-09-09 gate-1 re-measure.
> `facets.MAX_COMPANY_FACET_TERMS = 1` records the term ceiling; `lane_company_combos_per_run`
> ships at **0 (OFF)** and **12** is the sized value. **Read D-433 before touching any of this.**
>
> Two things this section asked to be checked, both checked and both binding:
> **(1)** `admits` is free only for an existing `linkedin:` row, and **48 of the 65 gate employers
> have none**, so each costs a cap slot. **(2)** The live cap is **50**, not the 10 recorded here —
> runs 141-144 admitted 29/49/47/32 — so a company cell displaces a hub-net company roughly 1:1.
> Bounded and priced, not starvation: `_search` interleaves round-robin, so a cell's own employer
> lands in the first pass. **The cap is still NOT to be raised (D-417).**
>
> The original sizing follows, unedited, because it is what the refutation is against.



This is the one thing job-apps does that boardwatch does not. `job_discovery.py:2438` issues
`query = f'"{company}" software engineer'` per target company. boardwatch only ever issues
**facet × hub** cells: `profile.target_titles_json` × `lane_search_hubs`, sliced per run.

**It needs NO new URL shape.** The guest endpoint already takes `keywords=`, and
`linkedin.search_url` already `quote()`s the term — so a company cell is just a composed facet
string, `"Acme Corp" software engineer`, handed to the facet path that already exists. This is a
smaller change than "a third URL builder", which an earlier draft of this plan called for.

**Concrete shape, mirroring `hub_nets` exactly:**

1. **`lanes/facets.py`** — add `company_nets(terms, companies, *, rotation_index, combos_per_run)
   -> tuple[str, ...]`, a sibling of `hub_nets` returning composed keyword strings. Reuse
   `hub_nets`' matrix arithmetic and its stated contract verbatim: dedupe **both inputs**
   order-preserving (not the product, so the matrix stays rectangular), slice
   `(rotation_index * combos_per_run) % len(matrix)`. **State the overlap condition**: disjoint
   consecutive runs need `2c <= m`, and with hundreds of companies `m` is large, so that holds
   easily — but write the assertion down rather than inheriting it.
2. **`pipeline/runner.py::_linkedin_lane`** — append the company cells to `search_facets`, after
   `ctx.facets.profile + ctx.facets.mined`. Nothing in the lane changes.
3. **The company list comes from the STORE, never the module** (multi-tenancy; the lane's own
   docstring is explicit that a role query written into the module fits exactly one user). Order:
   **watched first, then known-unwatched**, so the 342 already-watched misses are hit first — they
   are the falsifiable gate below.
4. **`Settings`** — one new knob, `lane_company_combos_per_run`, defaulting to **0 (OFF)**, exactly
   as every lane here ships disarmed. Remember a `Settings` field has **four gated registration
   sites** including the manifest config-hash.

**Budget is the binding constraint, not the company count.** `lane_posting_budget = 300` bounds
JD-body requests per lane per run, and a LinkedIn body was measured at **2.39 s** (D-414) — so 300
bodies is already ~12 min. Search GETs are cheaper but not free. **Size `combos_per_run` so the new
cells do not starve the hub nets that already work**, and read the split on the first armed run.

**Admission interacts, and must be checked before sizing.** `collect` asks `admits(LANE_PROVIDER,
slug)` once per distinct company before any body is fetched, and the per-run company cap is what
D-417 proved is NOT the lever. A company-faceted cell returns postings at a company that is
*already known* in most target cases — confirm an already-stored company is not charged against the
cap (the `select()` rule elsewhere is that an already-stored company is FREE), or the cap will eat
the very cells this track adds.

### Track 3 — widen the facets — **CLOSED (D-453). Already built, already at budget, and the premise was false.**

This section said "measure before building". **It was measured, and the answer closes it twice
over.**

**It is already built and armed.** `_lane_facets` mines extra terms at the full budget
(`MAX_MINED_FACETS_PER_RUN = 8`, `lanes/facets.py:65`) and already holds `junior software engineer`
and `full stack developer`; the candidate pool before the cap is 32. Null control:
`mined_facet_candidates([], profile)` → `()`.

**And the premise it rested on — that absent postings carry titles no facet matches — is FALSE,
because LinkedIn fuzzes its own matching.** 565 of the lane's 1,972 holdings (**28.7%**) carry **no
facet phrase at all**, including exactly the terms a wider facet list would add (`full stack
developer`, `java developer`, `ai engineer`, `frontend developer`, `python developer`). So the term
is not what fetched them, and adding terms does not explain what is missing. The instrument
discriminates, which is the control: ATS-board rows are 7.8% phrase-covered, hiringcafe 16.7%,
indeed 45.9%, **linkedin 71.3%**.

**Geometry is not the edge either.** `HUB_LOCATIONS` is **byte-identical** to `lane_search_hubs`
(same 7 metros, `job_discovery.py:136`; D-411 copied it exactly) and both ask a 24h window. Per run
boardwatch issues 33 hub cells × 5 pages × 10 + 22 no-location terms × 5 pages ≈ **1,650+ card
slots** against job-apps' 222 × 5 + 12 × 8 = **1,206**. Normalised per DAY — mandatory, because both
ask 24h and boardwatch's ~6.6 runs/day re-sample one pool, so a per-run comparison would be
dishonest — boardwatch acquires **219 postings/day** against job-apps' **716/day** (3.3x) while
spending **4.9 search requests per posting** against job-apps' **0.33**. **The gap is redundancy, not
geometry.**

**54% of the 5,650 is outside every hub metro at `distance=25`**, so only a no-location cell can
reach it — and boardwatch's own holdings are **56.2% inside** a hub metro against job-apps' 33%.
**The hub nets work; they are aimed at the smaller half of the loss.**

### The ONE open probe — do NOT run it without the owner

Whether N non-company **no-location** strings return disjoint card sets: 12 strings drawn from the 24
unused mined candidates, measuring card-id disjointness against the current 22, **~15 s**. It either
establishes a ceiling for raising `MAX_MINED_FACETS_PER_RUN` 8 → 32 (+45 GETs/run ≈ +0.9 min/run,
DERIVED) or closes the last idea in this file. **It runs straight into the company cap for the 55% of
the loss at unknown employers** — D-437 measured 12 nationwide cells presenting 61 new companies
against a cap of 50. It issues live requests against an endpoint whose permission is a recorded owner
ruling (D-290), which is why it is his call and not a session's.

## How to know it worked

The instrument exists and is read-only: `.agent/2026-09-02c-session/linkedin_reach.py` (this
decomposition) and `.agent/2026-09-02-session/per_source_recall.py` (gate 1).

| | now (run 147) | target |
|---|---:|---|
| linkedin independent | 34.8% | rises |
| linkedin absent | 5,650 | falls |
| **linkedin lane-only** | **892** | **falls — this is the retirement exposure** |
| already-watched misses | 358 | → ~0 (pure search breadth; nothing else explains them) |
| **absent · would be kept · job-apps carried it** | **395 = 28/day** | **this is the LOSS being accepted (D-453)** |

**The 358 already-watched misses are the honest first gate on Track 2.** boardwatch watches those
boards and still missed those postings, so no admission, no discovery and no dependency can explain
them — only query coverage can. If Track 2 does not move that number, it did not work.

**And read the last row before reading any of the others.** 395 postings/day-adjusted is the whole
prize; a track that moves `absent` without moving that number has bought postings boardwatch's own
gates then discard.

## Traps

- **Do not raise the LinkedIn company cap again.** D-417 ran the experiment: 10 → 50 bought **+1
  posting** while refusals rose 344 → 617. It is admission-bound in appearance only.
  **This trap is LinkedIn's ALONE and does NOT transfer to Indeed (D-452).** It holds here because
  **LinkedIn's tier-1 count is exactly 0** — the lane exposes no external apply URL, so a cap slot
  can only ever buy a `linkedin:` placeholder row. On Indeed a slot can buy a scannable employer
  board (~54 per run), and 80 tier-1 companies were refused in a single run. **A trap transfers only
  as far as the mechanism it was measured on.**
- **`lane_search_pages` is shared.** It was reverted 10 → 5; one page knob cannot mean the same
  thing for LinkedIn's ~10 cards, hiring.cafe's ~150 and Indeed's 100 (D-414 §1).
- **A LinkedIn body must be declared `secondhand`** if it is ever written over a posting an employer
  board also serves — an aggregator rendering silently becomes the document every eligibility rule
  quotes (`core/models.py:83`, D-414(a)). For a LinkedIn-only posting there is no employer body to
  overwrite, but the declaration is what keeps the evidence chain honest.
- **Permission is settled, not open.** `robots.txt` disallows `/jobs-guest/` and names `ClaudeBot`;
  User Agreement §8.2 forbids scripted scraping. **Mit ruled BUILD with all of it in front of him
  (D-290).** Recorded, not re-litigated — and equally, not quietly widened without him.
- **The lane's identity is the company slug**, because LinkedIn exposes no external apply URL
  (`externalApply = 0`). There is nothing for `parse_posting_target` to converge onto; convergence
  happens downstream through the P6 identity quad.
- **Sequencing against the board sample.** D-428 admitted 50 hiring.cafe boards to be read over runs
  145–147. Track 1 admits more boards. **Landing both in the same window makes neither yield
  separable** — that is exactly why "both levers" was rejected on 2026-09-02.
