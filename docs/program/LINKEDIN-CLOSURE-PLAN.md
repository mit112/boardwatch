# Closing the LinkedIn gap — the plan, measured 2026-09-02

> **Read this before proposing any LinkedIn work.** It exists so the comparison below is never
> re-derived, and so JobSpy is not re-proposed. Reasoning: **D-431**. Numbers: METRICS
> (Session 2026-09-02c). Retirement context: `RETIREMENT-PLAN.md`, **D-421**, **D-424**.

## Why this is the only thing left

Gate 1 is per-source recall (D-421). Every other source is solved or self-solving:

| source | standing 2026-09-02 |
|---|---|
| employer's own boards (lever/ashby/greenhouse/workday) | **94–100% — solved** |
| **indeed** | **0 absent, 6,740 lane-only.** boardwatch already holds everything job-apps finds; the native lane converts it as it reaches steady state. **No new work.** |
| hiringcafe | diagnosed as a board-fleet gap (D-425); the 50-board sample is admitted and reads out over runs 145–147 (D-428) |
| jobright | REFUSED deliberately (D-406) |
| **linkedin** | **the whole residual** |

**The retirement test is `lane-only` falling to a level the owner accepts losing (D-424).** Indeed is
87% of today's lane-only and converts by itself. So LinkedIn is what decides retirement.

## The gap, decomposed — 5,876 absent LinkedIn postings, 14d to 2026-09-02

| bucket | postings | share | employers | reachable how |
|---|---:|---:|---:|---|
| employer not in the store at all | 2,839 | 48.3% | 1,730 | needs discovery |
| known, but only a **lane placeholder** row (no board) | 2,313 | 39.4% | 349 | **name is known** |
| known + **real ATS row → admissible today** | 382 | 6.5% | 92 | `companies import` |
| already watched (a real coverage miss) | 342 | 5.8% | 65 | search breadth |

**Two corrections this measurement forced, both recorded in D-431:**

1. **D-417's "these employers plausibly have no ATS board" is REFUTED at scale.** That was n=77 and
   read 74% not-in-store; the full population reads **48.3%**, and the not-in-store bucket is led by
   **Raytheon, Netflix, Perplexity, Weights & Biases, Upstart, Illumio, NinjaOne, U.S. Bank** —
   companies that plainly do have ATS boards. This is a **discovery** gap, not an architecture limit.
2. **A "known" employer is usually NOT admissible.** `linkedin:google`, `jobapps:ibm`,
   `hiringcafe:adhoc:amazon` are lane-provenance placeholders, not boards; `companies import` takes
   only the six real ATS providers. Board admission therefore reaches **6.5%**, not 45.9%.

**51.7% (3,037) of the absent set is at an employer boardwatch ALREADY KNOWS BY NAME** (342 watched +
382 admissible + 2,313 placeholder). That is the population Track 2 targets.

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

### Track 1 — admit the 92 already-admissible boards (no new code)
382 absent postings sit at employers whose `companies` row already carries a **real ATS
provider+slug**. This is the mechanism D-428 already used for hiring.cafe.

- Generate candidates with the D-428 pattern (random or full; 92 is small), `companies import --verify`.
- **Cost: 92 boards × 3.2s ≈ 4.9 min/run, forever.** Weigh against D-417's caveat.
- **Owner's call before importing** — it spends run budget permanently.
- Snapshot `companies` to CSV first; that is the reversal artifact, not a DB copy.

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

### Track 3 — widen the facets (optional, measure before building)
job-apps also feeds up to **20 learned terms** into its sweep. boardwatch takes facets from
`target_titles_json` alone. Adding learned terms is a *profile* question, not a code one.
**Measure first**: how many of the 5,876 absent postings carry a title no current facet would match?
If the answer is small, do not build it.

## How to know it worked

The instrument exists and is read-only: `.agent/2026-09-02c-session/linkedin_reach.py` (this
decomposition) and `.agent/2026-09-02-session/per_source_recall.py` (gate 1).

| | now | target |
|---|---:|---|
| linkedin independent | 32.9% | rises |
| linkedin absent | 5,876 | falls |
| **linkedin lane-only** | **922** | **falls — this is the retirement exposure** |
| already-watched misses | 342 | → ~0 (pure search breadth; nothing else explains them) |

**The 342 already-watched misses are the honest first gate on Track 2.** boardwatch watches those
boards and still missed those postings, so no admission, no discovery and no dependency can explain
them — only query coverage can. If Track 2 does not move that number, it did not work.

## Traps

- **Do not raise the LinkedIn company cap again.** D-417 ran the experiment: 10 → 50 bought **+1
  posting** while refusals rose 344 → 617. It is admission-bound in appearance only.
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
