# PROGRAM STATE — read this first

> The one file a fresh session with zero memory reads to know where the program stands.
> **If it disagrees with the repo, the repo wins** — fix this file and record the correction in
> `DECISIONS.md`. Plan: `PROGRAM.md`. Numbers: `METRICS.md`. Shipped: `CHANGELOG.md`. Settled
> per-subsystem background: **`STANDING-FACTS.md`** — read the one section for what you are touching,
> never the whole file (D-139). Both logs carry an index spanning themselves and a closed archive
> (D-108): read the index, then the one range.
>
> **States only what is true now**; no sha or commit count (D-017). **Rewrite it, never prepend.**
> **This file holds only what changes between sessions** — current standing, next action, live blockers,
> owner calls. Settled subsystem history was moved WHOLE into `STANDING-FACTS.md` on 2026-08-23d by
> Mit's ruling, and **again on 2026-08-26** (30 settled blocks, this file 511 → ~260 lines, verified
> line-for-line that nothing was lost); nothing was deleted either time. Do not narrate a decision here
> that `DECISIONS.md` already holds — cite its number instead. **If this file passes ~250 lines again,
> the fix is to move settled blocks out, not to summarise them away.**

---



## Current standing

### Did session 2026-09-01e reach its goal? NO — and the reason is that no run happened

**The goal, in the owner's words: "ensure that we are finding all the jobs that Job Apps is finding,
so we can retire Job Apps."** That is gate 1 (D-399): independent coverage of job-apps' eligible set
**>= 80%**.

| | |
|---|---|
| gate 1 at session start | **22.2%** (independent 48 of 216) |
| gate 1 at session end | **22.2% — UNCHANGED** |
| postings actually gained | **0** |

**Nothing this session moved the number, and nothing could have**: gate 1 is only re-read from a
pipeline run, and no run took place. Everything that landed is CAPABILITY plus three refutations.
**Run 141 is the first moment any of it can be scored.**

What the plan (`RETIREMENT-PLAN.md` §5) asked for, against what happened:

| step | outcome |
|---|---|
| Track D — drop audit, first | **DONE.** Refuted its own premise (D-412): 0 of 216, so filters are not a lever at all. |
| Wave 0 — shared settings PR | **SKIPPED deliberately.** Track A already carried the registration sites. Cost: 4 rebase conflicts on exactly the surface Wave 0 existed to remove, and one of my resolutions shipped a syntax error the gate caught. The wall-clock call was probably still right; it was not free. |
| Track A — LinkedIn geo nets | **MERGED (#326, D-411)**, and the owner's config armed afterwards. |
| Track B — native Indeed lane | **MERGED (#327, D-414) but DISARMED**, and must stay so until D-414's two owed items close. Contributes **0** until armed. |
| Track C — `gh_jid` resolver | **PARKED unmerged (D-415).** Built and green; measured to fix **2** rows, not 7,406. |
| Review each track | **DONE.** #326 came back DO-NOT-SHIP on two false claims, one already in `DECISIONS.md`. |
| Re-read gate 1 after one run | **NOT DONE — no run.** |
| Wave 2 — tier-D adapters | **RECON ONLY (D-413).** No adapter built. |

**Where the 168 misses stand, honestly:**

| tier | size | status |
|---|---:|---|
| A — providers already held | 11 | `gh_jid` half parked (worth 2, not 7,406); company-admission half not started |
| B — linkedin.com | 77 | mechanism shipped + admission cap raised 10 -> 50. **Yield unknown until run 141** |
| C — indeed.com | 35 | lane built, **disarmed**. Realised 0 |
| D — ~30 other vendors | 45 | recon only. One generic JSON-LD lane would be worth 7 and clear the bar |

**So the honest summary: the session bought three things — a mechanism that should unlock tier B, a
lane that is ready but not switched on, and the removal of three wrong beliefs about where the gap
was. It bought zero postings.**


**THE DROP AUDIT IS DONE AND IT REFUTED ITS OWN HYPOTHESIS (D-412).** Of job-apps' 216 eligible
postings boardwatch drops **ZERO** at the hard filter and the non-SWE gate, on both join paths.
**Relaxing both gates completely buys 0.0 gate-1 points.** Gate 1 sits where it does because
**131 of 216 postings are not in the store at all**: it is an ACQUISITION problem, not a filtering
one. That retires a cheap-points theory permanently and confirms Tracks A/B and tier-D adapters are
the only levers. The instrument was verified first — the two pure functions reproduce run 140's own
counters exactly (118,463 / 60,491 / 39,404). Measured false-drop rate **0.022%**, a lower bound.

**LINKEDIN GEO NETS SHIPPED (#326, D-411) AND THE OWNER'S CONFIG IS ARMED.** `location=` is not
inert (D-409), so the lane now searches term x hub. Live config, applied 2026-09-01e and read back
through `load_settings`: **7 metros** (job-apps' `HUB_LOCATIONS`), `lane_hub_combos_per_run` **33**
(98-cell matrix, `2c <= m` holds, so consecutive runs are disjoint and full cover takes **3 runs**),
`lane_search_pages` **10 -> 5**, and **`linkedin` new-company cap 10 -> 50**.

**THE CAP IS THE POINT, AND IT IS WHY THE NETS ALONE WOULD HAVE BOUGHT NOTHING.** Review caught it:
LinkedIn's `lane_new_companies_per_run` was the default **10** while run 139 refused 267 and run 140
refused 344, and `_search` builds `search_urls(facets) + net_urls` so the facets exhaust the cap
before a single net card is considered. **Tier B is ADMISSION-bound, not discovery-bound** — geo
nets are necessary and not sufficient (D-411). Sized to stay inside the existing 300 posting budget:
lane companies carry a mean 3.47 open postings and run 139 resolved 149.

**THE NATIVE INDEED LANE IS BUILT AND SHIPS DISARMED (#327, D-414).** Every JD arrives inline, so
the lane makes zero body requests; no dependency added. **DO NOT ARM IT** until D-414's two owed
items close — chiefly that a converged posting's `locations_json`/`remote_policy`/`department` are
overwritten unconditionally, which under this owner's `location_filter_mode = "hard"` can delete a
lead the pipeline already held.

**TIER D IS A SEED PROBLEM, NOT AN ADAPTER PROBLEM (D-413).** Every tier-D vendor is per-tenant with
no cross-tenant search; of 39 misses only **6** have a seeded posting URL and **18 have no seed at
all**. **ONE generic JSON-LD lane is worth 7 postings and clears the 80% bar (82.4%)** — build a URL
resolver with a per-vendor strategy table, not ten search lanes. Avature is REFUSED (AWS WAF
challenge ⇒ browser automation, out of scope), UKG DECLINED, iCIMS SKIPPED on the owner's call.

**Track C (`gh_jid`) is built, green and PARKED UNMERGED (D-415)** — the plan's "7,406" counts URLs
the rule can parse, not duplicates it would fix; the real number is **2**.

## Next action

**RUN 141, AND READ GATE 1 OFF IT.** Everything else this session was capability; this is the
measurement that says whether tier B was really admission-bound. Expect the LinkedIn lane to admit
up to 50 new companies and to spend up to 165 extra search requests on the nets.

Read out of run 141, in this order:
1. **Gate 1** (`retirement_readiness.py`) — independent coverage against the same 216 population.
2. **Whether the cap still binds.** `linkedin ... refused by the cap` should fall sharply from 344.
   If it does not, admission was not the constraint and D-411's reasoning needs revisiting.
3. **Cost.** Total run time against run 140's 44m55s, and the lane's own `search_pages` table.
4. **The rotation.** Three consecutive runs must cover all 98 cells with no repeats (D-411).

Then **Wave 2 rank #1** — the generic JSON-LD resolver lane (D-413) — and **D-414's two owed items**
before Indeed is armed.

### Owed, found earlier, not yet scheduled

- **D-414 (a): a converged Indeed posting overwrites the provider's structured fields**, not gated
  on `content_hash`, in the same run the ranker reads. **Blocks arming the Indeed lane.**
- **D-414 (b): the Indeed lane has no `lane_new_companies_per_run` override**, so it would discard
  companies whose JDs already arrived, permanently — its window is 24h, not a recirculating pool.
- **`Vice President` is doing seniority work inside the ROLE gate** (D-412) — 31 of 70 cases. The
  outcome is defensible; the reason the audit trail records, "not software", is false.
- **357 US postings the role gate itself calls `swe` are dropped by `excluded_title: II`/`III`**
  (D-412). Correct by configuration, and the same call that costs the one Valon gate-1 point.
  Owner-facing, not a defect.
- **`boardwatch config set` STRIPS every comment from `config.toml`** — it round-trips through
  `tomli_w`, which has no comment support. The live file carries 85 comment lines of recorded
  reasoning, so **edit it textually**. (Learned the hard way this session: a scripted write
  destroyed all 52 then-existing comments and they had to be restored from the backup.)
- **`ashby:Lightfield` duplicate pair stays as recorded residue (D-405, Mit's call).** 19 duplicated
  open postings, **zero artifacts ever delivered**. Drain owed when something next touches company
  identity or the Ashby lane.
- **One queue failure survives #316 and is pre-existing**: `posting 131368: eBay_..._59eb81b3 already
  exists at its destination`. A null control confirms unfixed `main` performs the same rename.
- **`_identity_hash` reads the mutable `apply_url`; exposure is 239 of 861 offered leads (27.8%)**.
  **DEFERRED by Mit 2026-09-01** as the lowest-value of four.
- **9 postings carry jobright PAGE TEXT as their JD (D-406).** Mit ruled 2026-09-01: add a lane-body
  ingest precondition and quarantine the 9 with a drain. **Not started.**
- The ledger drain stays DECLINED (D-390). The two held recall patches at
  `.agent/2026-08-31d-session/WIP-*.patch` are **DO NOT SHIP** on measured evidence.

## Session 2026-09-01e — what shipped

**Two PRs, four decision entries, one live-config change, and two hypotheses killed with numbers.**

- **#326 — LinkedIn geo-pinned hub nets** (D-411). Shipped inert; armed via config afterwards.
- **#327 — the native Indeed lane** (D-414). Shipped **disarmed**, and must stay so until D-414's
  owed items close.
- **D-412** the drop audit, **D-413** tier-D recon, **D-415** Track C parked.
- `STANDING-FACTS.md` corrected: `hidden_hard_filter` is **60,491**, not the recorded
  18,472-18,932 from runs 68/69/71. The load-bearing claim (the `hidden_*` buckets are an exhaustive
  partition, so they can never evidence a silent failure) survives; only the range rotted.

**REVIEW EARNED ITS KEEP TWICE, AND BOTH FINDINGS WERE IN CLAIMS RATHER THAN CODE.** #326's first
review returned DO-NOT-SHIP: its rotation contract asserted disjointness **unconditionally** (true
only for `2c <= m`; at the default 12 combos every matrix under 24 cells overlaps) and that false
claim had **already been written into `DECISIONS.md`** — the exact failure D-409 exists to punish.
The same review found the rotation was keyed on the **calendar date**, so two runs in one day drew
the identical slice and a weekly cadence would starve a fixed subset of the matrix forever. Both
fixed; the index is now the run's own id.

**Three sizing errors were caught by measuring rather than by reading the plan**, all the same
shape — *a count of things a rule can MATCH is not a count of things it would FIX*: Track C's 7,406
(real answer 2), tier D's vendor ranking (the seed, not the adapter, binds), and the drop audit's
whole premise (zero). None was a bad measurement; each answered a question next to the one that
mattered.

## Owner-gated — do NOT start or decide unilaterally

1. ~~Does job-apps keep running, or is it retired?~~ **ANSWERED — it keeps running until gate 1 is
   met.** Both schedulers armed: boardwatch 04:00, job-apps 08:30. **The retirement work is now a
   written plan, not a question: `docs/program/RETIREMENT-PLAN.md`.** Do not re-raise WHETHER, and do
   not re-derive the gap analysis.
   ~~2. Indeed's dependency posture.~~ **DECIDED by Mit 2026-09-01 (D-410): approved.** Closed; do
   not re-open or re-probe.
2. **Mit's two résumé content calls** — whether to send a document at all; the D-220 prose rewrites.
3. **P2 item 8 — the onboarding field-taxonomy gatherer. DEFERRED by Mit 2026-08-28.** The last
   multi-tenancy gap of its kind; D-054 forbids us authoring non-tech field content.
4. **`add-evidence` takes no bundle lock** (D-143) — raise before two authoring agents run against
   one bundle.

## Open questions — Mit's, not to be resolved by fiat

1. **The projection spec's six open questions** (§12).
2. **The Snap `Level 3`/`Level 5` leak stays open by design** — with no bindings file every level
   token abstains. boardwatch ships no verifiable claim about any company's ladder.
3. **Whether `censored` boards publish a coverage ratio, and the 17 silent boards.** The class is
   **15 boards and 43,371 postings that can never be listed at all** (run 127) against an ~84,821
   open corpus. **Sized, not solved, and no budget can solve it.** See D-336.
4. **Whether `ServiceNow Developer` should rank at all against a new-grad SWE target.** Role
   TAXONOMY, not dedup. D-345 bounds the delivery damage; it does not answer this.

*(Resolved and no longer open: the delivery slate cap — D-345, `(company_id, normalized_title,
content_hash)` at N=1; do not reopen as identity suppression, which is D-295 and is refused.
Whether `runner.py` should keep swallowing a funnel-write failure — D-288. Clearance IS a blocker
(D-257). Seniority band = `entry` (D-258), and it is **armed on the live profile**.)*

## Phase status

| Phase | Build | Gate |
|---|---|---|
| P0 Instrumentation | **COMPLETE** | **MET** (D-030) |
| P1 Résumé artifact gate | **COMPLETE** | **MET** (D-032/033) |
| P2 Profile + keystone | items 1–7 shipped; item 8 NOT STARTED | **MET AS RECONCILED** (D-075) |
| P3 Unattended one command | **COMPLETE, INSTALLED, FIRING** once daily at 04:00 local (owner's call 2026-08-27; was ~3h under D-288). The agent is now a FALLBACK HEARTBEAT — Mit's ruling is to invoke a run manually as and when needed, so do not wait for the schedule | **MET** — 8 consecutive clean scheduled ticks (runs 71-78), verified from the `runs` table + funnels |
| P4 Craft gate | **COMPLETE** (under-fill fixed D-303; objective anti-slop 0 violations, non-vacuous) | **MET** — objective half certified AND the owner's blind craft review passed cleanly 2026-08-26 (all 5 judged worse were job-apps decoys; all 3 judged better were boardwatch) |
| P5 Eligibility decides | **COMPLETE** | **MET** — INELIGIBLE precision 16/16, 0 span violations |
| P6 Liveness + dedup | **BUILD COMPLETE** (D-110/111/113); leakage report shipped (D-283) | **MET — 4 of 4** (2026-08-27): liveness MET (D-281), leakage measurable over a true 7-day span and reading **0.00%**; see the clause table for the `exact_quad` caveat |
| 14-day acceptance | not started | **HELD BY THE OWNER (2026-08-27)** — the provisional pass was MET by runs 119-123, and Mit ruled to keep fixing precision first rather than start the clock. Starting it freezes eligibility, profile and the résumé gate for 14 days. **2026-08-28e: the provisional pass's remaining item — 3 clean post-fix runs — RESTARTED FROM ZERO**, because #218 bumps `rules_hash` and those runs are therefore pre-fix again. The P4 owner blind review is still PASSED (2026-08-26) and does not repeat. With runs on demand and Mit stepping back ~2026-08-31, that is 3 runs in ~3 days; **the trade (stricter eligibility now vs the pass possibly not closing before unattended operation) was raised to Mit and is his**. **2026-08-28f: #221 bumps `rules_hash` again, so the counter restarts again — and this is NOT being chased (D-351 item 2 stands: work comes first)** |
| P7 Breadth | **lane 1 (hiring.cafe) and Part 4b (LinkedIn) are BUILT AND ARMED and ran in run 122** (hiringcafe 70 attempted/56 resolved; linkedin 71/51) — the previous "not armed" text was stale. **Part 4a GitHub-lists discovery BUILT + LANDED (#149/D-296) and NOW PARTLY ARMED**: 97 boards imported 2026-08-27, ~765 candidates still capped. Remaining lanes not started | unlock MET (D-271/272) |
| *Gate A / Gate B* | *complete, merged* | ***MET*** — *has moved no program gate* |

### Gate P6 — MET, 4 of 4

The clause-by-clause table moved to `STANDING-FACTS.md` on 2026-08-28f: every clause is MET and
none has moved since 2026-08-27. Read it there before quoting the leakage figure — the `exact_quad`
caveat (D-294) is what makes 0.00% a structural reading rather than a clean one.

## Live blockers and carried gaps

| Item | Detail | Owner |
|---|---|---|
| ~~The `experience_years` group reads a REFINEMENT as a CONTRADICTION~~ **CLOSED by #291 / D-389** | `refinement_groups` ships as a second group kind in versioned catalog DATA: `exclusive_groups` keeps PRESENCE semantics, `refinement_groups` dissolves only on a real `MET`/`UNMET` straddle. Only `experience_years` moved — **a global rule regresses 8 of 1,034 corpus cases** (D-388), because `clearable_required` is a DISJUNCTION not a weaker rung. **913 of a PINNED 1,868 flip `uncertain` -> `ineligible` (48.9%)**, corpus 0/1034 (predicted before review). **`engine_version` MOVES so a LEDGER DRAIN IS OWED.** Known property, direction deliberate: the refinement pass runs BEFORE stage 1b, so a same-implies split beside another present member dissolves the group where stage-1b-first would let a decisive `unmet` stand — the shipped order is the ABSTAIN direction | **CLOSED** |
| **boardwatch sees 16.4% of job-apps' eligible yield — RE-DERIVED 2026-08-30, and the METHOD was wrong before** | **45 of 275 (16.4%)**, cohorts 08-23..08-29, on the **379-board fleet**. This replaces "10.1%, owed a check". It decomposes: fleet growth 344->379 gave 10.1 -> **13.8%**; adding an **exact ATS-slug key** alongside name matching gave 13.8 -> **16.4%**. **Name-only matching undercounts, so 7.7% and 10.1% are FLOORS** — boardwatch stores Micron as `Micron TDIT`, so the old method scored a watched company as unwatched; same for HPE/`Hewlett Packard Enterprise`, Cox/`Cox Automotive`, Disney/`Walt Disney Company`, Toyota, VIAVI. **The unreached 230 split: aggregator-only 60.7%, unsupported employer host 21.1%, board-addable just 1.8%** (5 postings in 7 days, 4 of them SmartRecruiters — the class D-370 declined on measured cost), so the cheap remainder is ONE Workday board (Motorola Solutions). **The gap is lanes, not boards.** Script: `.agent/2026-08-30-session/reach_v2.py`. Amazon/TikTok/Apple/ByteDance use none of the 6 ATS, so a slug cannot reach them. Closing it means a new discovery lane — GitHub new-grad lists are 19.1% of yield for ~5 public-repo GETs and are NOT the ToS trap the v2 decision was written about. **Reopens D-008** | **Mit** (reverses a shipped decision) |
| ~~Delivery-drought cannot see APPLY-LANE starvation~~ **CLOSED by #285 / D-384** | `delivery_drought.py` counts `artifacts.kind == TAILORED_KIND`, written **regardless of which lane `review_gate.lane()` routes to**, so a global misclassification shipped zero apply-ready leads with every existing alarm green. `check_apply_lane_drought` now fires when the last 3 clean runs each delivered PLACEABLE leads and none reached the apply lane. **The old sizing was wrong, not merely pessimistic**: it priced a guard inside `_sync_queue`, but the three job-id readers already take only a connection and `QueueRow` already carries `delivered_run_id`, so nothing in `review_gate`, `_sync_queue` or the web server's result type had to change. Known property, direction abstain-not-alarm: `delivered_unapplied` attributes a re-delivered job to the NEWER run, so an older run can read zero placeable and the window abstains | **CLOSED** |
| ~~Four detector fallbacks are print-only, not durable~~ **CLOSED by #260** | The `intake-death` / `delivery-drought` / `liveness-blindness` / `corpus-regression` "check not run" handlers now call `append_run_error` like the three artifact-write handlers beside them, so a DETECTOR that crashes leaves a row in `runs.errors_json` and not only a digest line. Four one-line additions, inert on the normal path; each pinned by its OWN parametrised test, because a single test crashing all four passes while three of the four calls are missing. **Known shared property:** `append_run_error` is not internally defensive and these sit inside `except` handlers — matched to the three existing handlers deliberately rather than diverging; it needs two simultaneous failures and fails loudly via the withheld heartbeat | **CLOSED** |
| **`companies.last_health` / `last_ok_at` are a LYING instrument** | 178 of 379 watched boards read NULL, which looks like "never succeeded" — **all 178 were scanned by run 133** (128 complete, 7 partial, 43 unchanged). The scan path does not maintain these columns. **Judge fleet health from `board_scans` per run instead**: run 133 was 379 attempted / 271 complete / 87 unchanged / 21 partial / **0 failed** | tooling gotcha |
| **Citi sits at 13.1% coverage, permanently** | Workday's `total` censors at 2,000; the facet sum (uncapped, control-verified) says 4,589. Our pager wraps at ~2,000 too, so post-drain Citi holds ~2,214 of 4,589 and nothing reports it | **Mit** (input-side) |
| **`unchanged` staleness is now BOUNDED (D-298, #153)** | The `unchanged` verdict comes from the upstream HTTP validator (ETag/Last-Modified → 304), not a boardwatch payload hash. `validator_max_age_hours` (default 24) drops a validator older than the TTL, forcing an unconditional refetch, so a permanently-stale upstream can no longer freeze a board forever — the silent-staleness window is capped at the TTL, and a regression test now exercises the aged-validator refetch. Still open: within the TTL an `unchanged` is trusted with no independent check. The separate "59 of 135 boards listed nothing" figure was a **`postings_listed`-on-304 artifact — CORRECTED to 17 real dead-weight (D-300)**, now cleaned; the 118 `ok` boards hold 39,253 open postings | open (mitigated) |
| **`resume.yaml` is an IMPORT SOURCE, never hand-fixed** | D-155. Mit pins `resume_max_pages=1`; never advise 2 | Mit |
| **`boardwatch top` advances the queue by default** | records `seen` unless `--no-record`; relevant to Gate P6's clean window | P6 |
| **A live store is readable ONLY via Python `sqlite3` `?mode=ro`** | the `sqlite3` CLI with `?mode=ro` fails `CANTOPEN(14)` on a cleanly-checkpointed store (no `-shm`; not the sandbox), and `?immutable=1` skips the WAL so it is STALE against a live writer. Mid-run progress: `SELECT COUNT(*) FROM eligibility_evaluations WHERE run_id=N` (D-268) | tooling |
| **The unattended 04:00 tick runs the PRIMARY checkout's branch — and it is now PROVEN to fire** | Run 131 (2026-08-29, `runs = 1`, exit 0) was the first real unattended tick. The launchd job invokes the **editable** venv at `boardwatch/.venv/bin/boardwatch`, so whatever branch that tree is parked on IS the unattended run's code and `rules.yaml`. **Verified at the 2026-08-29f close: the tree is on `main` at `10baad5`, clean, and all six alert modules import through the editable venv.** A stale 8-hour-old `.git/index.lock` had silently blocked every `git pull` that session — check the lock's MTIME and `pgrep -x git` before blaming contention. **Park it on `main` before ending every session** — from ~2026-08-31 a stray branch changes EVERY subsequent run, not one. Closing it mechanically means pointing the plist at a worktree pinned to `main`, which moves a scheduled job and a venv | **Mit** (mechanism); every session (discipline) |
| ~~**hiring.cafe lane is DOWN**~~ **CLOSED — run 138 reports NO hiring.cafe error**, the first clean run since 129, ending a 14-of-14 refusal. The lane was re-pointed at the SSR surface (#304, D-397) and resolves bodies through the EMPLOYER's own board, so its postings land under greenhouse/lever/ashby/workable and NOT under a `hiringcafe` provider — do not read that absence as failure. Historical detail follows | **History, kept only so the dead ends are not retried.** The header lever FAILED (D-369/#245, run 133 reproduced the refusal byte for byte) and headers are ELIMINATED — do not repeat that experiment. The UA and volume premises were both false. The cause was the ENDPOINT: our `/jobs/` calls were refused 14 of 14 while job-apps succeeded on `/`. **D-393 decision 1 reversed the do-not-probe hold on Mit's explicit call**, and #304 re-pointed the lane at the SSR surface, which is what run 138 proves works | **CLOSED** |
