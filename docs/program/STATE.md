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
> Mit's ruling, **again on 2026-08-26** (30 settled blocks, 511 → ~260 lines), and **again on
> 2026-09-03d** (95 lines: the whole nine-decision apparatus, run 145's readout, and five closed
> blocks), and **on 2026-09-12** (the four settled 2026-09-06 session blocks). Nothing was deleted on any of the four passes. Do not narrate a decision here that
> `DECISIONS.md` already holds — cite its number instead. **If this file passes ~250 lines again, the
> fix is to move settled blocks out, not to summarise them away.**

---

## Current standing

### Session 2026-09-12 (Mit back after five days; runs 44–48 READ, rulings (b) and (a) EXECUTED, the lanes' re-added sliced boards found, the judge's 12-of-13 failure fixed, Gate 1 re-measured): **D-496.**

**Five unattended ticks, all `ok`, all funnels reconcile — confirm days 3–7 (run 48 = day 7 of 14).**
No code, config or rules change since 09-07, so the count holds. The 09-09 reboot moved the tick from
06:00 to **04:00 CDT**, exactly as predicted below; `launchctl` reads `runs = 3` since the reboot. The
fleet grew itself 341 → 486 by lane admission (113 boards, 32,402 open) and the open corpus 137k →
184k; run wall clock 36 → 55–102 min; censored boards 1 → 7. Numbers per run in `METRICS.md`.

**Ruling (b) DONE.** `companies names` matches a sliced row by its slug without the fragment; BAH 1486
→ `bah`, Leidos 1488 → `leidos`, the drained Northrop 1487 → `ngc`; `identities backfill` 2,238.
**Ruling (a) DONE, on a measurement the ruling's condition could not make:** BOTH HPE sites enumerate
completely. Keyed on the base requisition number, `Jobsathpe`'s 60 unique postings are ALL interns or
graduates (13 US, every one an intern) against `acjobsite`'s 257; neither ever delivered. `Jobsathpe`
drained to 1 and unwatched (D-494's mechanism). **The lanes had RE-ADDED the whole BAH and NVIDIA
boards beside their slices on 09-10** — two censored 2,000-row duplicates — because `stored_slug`
compared the fragment too. Fixed one-directionally (a plain slug resolves to its sliced row; a sibling
slice is still a second row), both drained and unwatched, 4,312 closed. **Every failed-open judge
batch on runs 45 and 48 was a 12-of-13 answer** (39 leads lost); verdicts now bind by `label`, a
skipped lead is reported `partly failed open` and is the only one unjudged. Three fixture reviews
(ashby/greenhouse/lever) extended to 2026-12-11 after a live shape re-check. `ashby:whatnot` (404)
and `vhr-otsuka/Pharmavite` (422) unwatched. **Fleet 481 watched.**

**Rank band, 308 ranked judge rows over runs 43–48: FLAT.** Deterministic `uncertain` converts 31 /
56 / 46 / 47 / **62%** across the five 30-rank bands; the deepest band is the best. `gate.depth = 150`
stands; whether deeper pays is unmeasured and a cost call. **Gate 1 (T35) re-measured: 34.8%
independent recall** (was 23.8% on 09-02); greenhouse 91.5%, ashby 92.6%, workday 96.6% clear the
≥ 85% employer-board bar, **lever 70.0% on n = 10 does not**; linkedin 42.3%, indeed 24.7%,
hiring.cafe 20.2%.

**Next action.** (1) Read the 04:00 tick on 09-13 (run 49 = confirm day 8): expect `partly failed
open` lines instead of failed batches, BAH/NVIDIA/HPE-Jobsathpe absent, watched 481, and check that no
lane re-adds a sliced board (`select … from companies where slug not like '%#%' and lower(slug)
in (…sliced bases…)` must stay empty). (2) Mit's calls, in one batch: 0-B (unchanged, the one failing
bar); 0-C (D-498, the lane-copy suppression); whether to slice or drop the five new censored retail boards (Advance Auto 16,869 · Five Below ·
Cushman & Wakefield · Applied Materials · Abbott); the lever bar on n = 10. (3) The Indeed and
hiring.cafe per-source THRESHOLDS at ~09-17, against today's 24.7% / 20.2%. (4) **The nightly Windows class is CLOSED (D-497)** — the unmarked judge test is skipped and a dispatched full
matrix is green except **T78**: Windows 3.13's two-writer test reads `database is locked` on 2 of the
last 6 runs (busy-handler starvation; ticketed, not fixed — a flake fix needs Windows fan-out, Mit's
call on the seat). `nightly-watch` (#95) will keep opening on it. Still open from D-494: seed the
cluster cap from the standing queue; ratify `apple`'s `board_reported_total = None`. The "network,
read-only" marker question is answered (D-497 §4): the vocabulary already says it.

### Session 2026-09-07 (review + run 43; the mid session REVIEWED, three rulings taken, run 43 CLEAN on the sliced fleet): **D-495.**

**T74's merge STANDS** — the exposure the ruling guarded against is THREE lane-row Qualcomm postings against 1,588 on the watched board; the 14–18% queue duplicate rate is a job-grouping failure (D-337) that board naming never touched. **The largest cross-board duplicate pair is HPE, not Northrop:** `hpe/acjobsite` + `hpe/Jobsathpe` share 1,013 `cross_host` groups over 2,227 open postings, pre-existing. **The slice `#` fragment broke `companies names`** for the two sliced boards whose name was the host: BAH 1486 and Leidos 1488 (2,027 open) deliver host-named. **Thales' three slice rows held 405 requisitions twice** at review time (row 256 had not reached `complete` before its siblings were added) — **run 43 then resolved it** (row 256 `complete`, 1,786 closed, duplicates 0). Rule kept: reach `complete` on the narrowed slug BEFORE adding a sibling slice row.

**Run 43 (the 12th pipeline run) — hand-launched 11:29 CDT on Mit's call, does NOT count toward the confirm.** `ok`, 36 min, 341 boards, 0 failed, RECONCILES, 1,459 new, 2,463 closed, 136,808 open, reach **92.7%**, censored 1 (Abbott). Gate 53 judged (36 / 6 / 11), 0 failed open; **8 PDFs** + 32 review. Queue 40 new / 18 moved / 0 failed, name mismatches 0. Every new instrument read: `throttle_retries` 48 with four eightfold boards still `partial` on the 12-retry board budget, `hidden_cluster_cap` 0, `shortlist_rank` on 53 of 53 judge rows. **First rank-band table:** `uncertain` 91–120 = 73% (8/11), 121–150 = 66% (19/29) — flat, no evidence 150 is too deep; accumulate ≥ 3 runs before moving `gate.depth`.

**Rulings taken 11:24 CDT ("we'll do your recommendations"), not to be re-asked:** (a) HPE — measure which site enumerates completely, then drain-then-drop the other; (b) `companies names` — match on the slug with its fragment stripped, then `names --apply` + `identities backfill` for BAH/Leidos; (c) the Thales closing-rule ticket is WITHDRAWN (moot after run 43). Full review: `.agent/2026-09-07b/REVIEW-BY-FABLE.md`.

**Next action.** (1) Read the 06:00 tick on 09-08 = **confirm day 3**; watch the four `throttle_exhausted` eightfold boards (is the 12-retry budget right?) and the rank table's n. (2) Rulings (b) then (a), after the tick — never merge while a run is in flight. (3) Mit's 0-B call on B8 (17.2% vs ≤ 16%) is the one failing bar. (4) T35 Gate 1 re-measure ~09-09. Still open from D-494: seed the cluster cap from the standing queue; a "network, read-only" effect marker; ratify `apple`'s `board_reported_total = None`; the Windows fake-claude CI class.

### Session 2026-09-07 (mid; ALL FIVE RULED CALLS EXECUTED — 15,640 postings closed, zero censored boards, four executors merged): **D-494.**

**The PDF drop 21 -> 5 is BENIGN and the question is closed.** The PDF stage converted 100% on both
runs (`21 in, 21 out`; `5 in, 5 out`; `no_pdf: 0`). The whole delta is the apply/review lane split
(`routed_to_review_lane` 19 -> 35): `review_gate.classify` promotes a deterministic `eligible` lead
unconditionally, run 10's slate carried **21** and run 11's carried **zero**. Cause: `new_count` was
779 on run 9, **30,706 on run 10**, 4,852 on run 11, and all 21 of run 10's `eligible` leads were
first seen on 09-07 — run 10 discovered them itself. It was the first-fill of the ~30 boards added
09-06 plus `amazon` and Jane Street. **~5 PDFs a run is the STEADY STATE; the apply lane is bounded
by the arrival rate of new `eligible`+`swe`+in-band postings, not by a backlog.**

**Fleet: 15,640 postings CLOSED by the slicing and censored boards 10 -> 0.** Workday facet slicing is applied
live to 13 slices across nine boards; open postings ~150,000 -> **137,810**; ~2,650 postings the
blind 2,000-walks had never seen. Per-board closes: Northrop 2,938 · Walmart 2,266 · Target 2,051 ·
T-Mobile 1,988 · PNC 1,897 · Citi 1,529 · Leidos 1,220 · BAH 1,008 · NVIDIA 743. **The ruling's
premise did not survive measurement:** `jobFamilyGroup=Technology` is the right descriptor for only
**3 of the 10** boards — T-Mobile uses a different PARAMETER (`Job_Family_Group`) and Abbott's biggest technology group is only 61 of 2,589, so Abbott is deliberately not sliced. **Northrop's workday row lost the
comparison** (3,000 of 3,791 on a page cap; its Engineering group is 2,182, above the 2,000 clamp,
so slicing does not fix it) and was DRAINED to 91 then unwatched — 2,938 closed through the absence
rule first, leaving 91 unclosable instead of 3,010. Eightfold keeps 3,424. **Fleet 341 watched.**

**Merged and pushed, six commits, final gate 10,090 passed:** `0e1690ac` **T72** (each judged lead's
shortlist rank recorded with its gate verdict, captured off the ranker's order BEFORE liveness;
`engine_version` unmoved, **no ledger drain owed**) · `aaa4aefc` **T70 `apple`** · `ad215b45` **T73**
(the ranking cap, 2 per company+title+location) · `f3466988` **T74** (the eightfold 405 retry +
employer naming) · `92781ce7` **T75** (`companies facets`) · `60e3efa2` the integration fix.

**T74 proved the planning session's own ticket WRONG, and it changes what item 4 delivers.**
`exact_quad` keys on **`company_id`**, not `normalize_company` — two boards are two `companies` rows,
so **no naming change can ever make it fire across them**. `cross_host` is the one keyed on the name
and it does not suppress, by design (§3.1). **So the cross-board duplicate is now GROUPED, not
SUPPRESSED: the 14-18% queue duplicate rate will NOT fall from this.** Acceptable because the
largest pair (Northrop) was dropped this session and the Qualcomm pair, the one the coverage fix
exposes, does group.

**Two defects found here that four green branch gates did not catch.** (a) T74's backfill selected
`name == slug` case-insensitively, which admits registry rows whose curated name is the slug
re-capitalised; it planned **129 rewrites, downcasing 100 names** (`OpenAI`, `SpaceX`, `AbbVie`) that
reach the résumé filename. Fixed casefolded: **31 rows**. (b) The MERGED-tree gate caught that
`apple` had no declared employer-name shape (T74 predates T70), so it would have named the company
after a COUNTRY. Backfill applied here: 31 rows renamed, `identities backfill` wrote 24,466.

**Next action.** (1) **Read run 12, the 06:00 tick on 09-08** — the first run carrying the shortlist
rank, the ranking cap, the sliced fleet and the eightfold retry. Then the rank-band measurement that
D-493 could not do becomes possible: read conversion by rank band out of
`raw_output_json.$.shortlist_rank` and answer whether `gate.depth = 150` is right. Expect a much
smaller corpus (137,810 open, not 150,000) and watch `hidden_cluster_cap` and the new
`throttle_retries` / `throttle_exhausted` lines. (2) **Thales may never close**: it serves 2-3 rows
with no `externalPath` on every scan, forcing `partial`, so its ~1,800 non-SOFTWARE postings are
stuck open — pre-existing provider behaviour that slicing exposed. (3) **The nightly WINDOWS CI has
failed every day since at least 08-31** on the fake-claude-on-PATH class; `push` CI is green on the
same shas. T61 fixed nine; this class remains and is worth a ticket. (4) Open questions the
executors raised and nobody has ruled on: whether to seed the cluster cap from the standing queue
(D-439's pattern) so a five-member group does not eventually deliver every member; whether 2 is the
right cap once `hidden_cluster_cap` has been observed live; and whether the guide needs a
"network, read-only" effect marker (T75 registered `("network",)` rather than invent one).

**Process note.** Three executors + a full gate + a scan pass at once drove load to 65 and memory
pressure killed six background waiters. Nothing was lost, but a gate under memory pressure can be
OOM-killed into a false red. **Gate BETWEEN executors, not across them.** Also: scans are serialized
by a global `scan.lock`, so a multi-board slicing pass is wall-clock bound and cannot be parallelized.

### Session 2026-09-07 (early; run 10 READ, the depth bet MEASURED, `amazon` and Workday FACET SLICING landed): **D-493.** Run 10 was launched BY HAND at 00:09 CDT on Mit's ruling (the handoff's "read run 10" was not actionable — `runs = 5`, no artifact dir; the tick had not fired). It ran **2h 40m** and came back **`ok`**: the first `gate.depth = 150` run reads `150 checked, 5 gone` → **145 judged (76 eligible, 22 ineligible, 47 uncertain), 0 batches failed open, 83 beyond the delivered slate**, funnel **`reconciles: True`**, `boards_failed` 0, `detail_deferred` 0 everywhere. **T63 has no first-live defect.** A manual run does NOT count toward the confirm streak, so the 06:00 tick still fires as run 11 and is the countable one. **T69 `amazon`** (merged `81fc956a`, CI green) — 22,282 postings over 38 categories, bodies INLINE so a 2,597-posting category costs 26 requests. **T71 Workday facet slicing** (merged `c3a5bc1e`) — `…/site#jobFamilyGroup=Technology`; live, sliced Citi enumerates **1,073 of 1,073 uncensored** against the unsliced board's `total: 2000` censor and 1,988 blind rows of a true 4,411. **Fleet 337** (+`amazon:software-development`, +`greenhouse:janestreet`, +3 lane-discovered). The recurring CI wall-clock flake (4.58 s on 09-06, 4.63 s on 09-07, both vs the same 4.5 s bar) is FIXED by rendezvous, not re-run (`1afd7d0f`).

**The depth bet is measured and it is NOT D-491's number.** Judge rows joined to the deterministic verdict on `input_id`: tier 1 (`uncertain`) **122 judged → 69 eligible = 56.6%**; tier 0 (`eligible`) **23 judged → 7 = 30.4%**. D-491's 85% was measured on the SHALLOW slate. The decision stands (69 judge-eligible leads no shallower run would have seen) but **the right value of `gate.depth` needs conversion BY RANK BAND, which needs each judged lead's rank — **not measured, and NOT computable retroactively: `score` is NULL on all 145 judge rows and no table persists a rank, so this needs a small instrumentation change (persist the shortlist rank with the gate verdict) before it can be answered.**

**Coverage — quote the run's own numbers.** `morning-10.md`: **discovery reach 90.4%** (109,065 of 120,606 stated, across 224 of 335 boards), and **10 censored boards short 35,645 postings** reported SEPARATELY with no ratio. A "67.7%" figure computed mid-session folded censored totals into one ratio and is WITHDRAWN. boardwatch already recovers true totals via facets; T71 extends that from totals to ENUMERATION.

**Run 11 (06:00 tick) READ — `ok`, 43 min, `reconciles`, `boards_failed` 0, `runs = 6`.** Both new boards work live: `amazon:software-development` **complete 2,598 of 2,598** and `greenhouse:janestreet` complete 231 of 231. **The depth cost AMORTIZES: 145 judged on run 10, only 62 on run 11** (a judged-undelivered lead keeps its verdict and is not re-judged) — so `gate.depth = 150` is cheaper after the first run than run 10 implied; read that beside the 56.6% conversion. Discovery reach **91.1%**. The slate is strong (LinkedIn, OpenAI, Apple, TikTok x3, Figma, Ramp, Audible) and run 10's 12-lead Goldman concentration is gone. Unexplained and NOT investigated: pdf 21 -> 5.

**Next action: SUPERSEDED — all five rulings were executed on 2026-09-07 (mid); see D-494 and the block above.** One claim in the removed text was WRONG and is corrected there: `exact_quad` keys on `company_id`, not `normalize_company`, and the hostname-named board count was 35 of 338, not 28 of 337.

### Owed, and specifically NOT done

- **T51 SHIPPED (D-484) before the freeze.** Its residual: a hedged bar carrying a domain noun has no
  `*_preferred` sibling to land in and writes no row; a recall change for M3's window.
- **D-436's per-family topic net is SIZED and NOT BUILT.** Sizing is in D-461: the all-family form
  takes `eligible` to **0**, and the `work_auth` form is worth **245 of 4,617 (5.3%)** — about a
  quarter of the measured defect. **Do not re-derive it, and do not quote the naive 29.9%**, which is
  EEO boilerplate contamination.
- **The hiring.cafe +6.19pp / 1,331-posting ceiling is RETIRED as a fossil (D-463).** Its null
  control rests on an endpoint PR #304 deleted on 2026-09-01, two days before D-451 was written.
  Real value ~**+0.6pp**. **Do not re-size other work off the 1,331.** The lane's dominant problem is
  **availability** — 2 total refusals and 2 near-total in the last 7 armed runs.
- **The refused-aggregator filter is REFUSED (D-463)**, not deferred. Its premise inverts on the
  actual variable. Do not re-raise it from the 24.7%/13.4% figures, which are the wrong comparison.

## Owner-gated — do NOT start or decide unilaterally

**0-C. SUPPRESS A LANE COPY WHEN THE EMPLOYER BOARD'S POSTING IS IN ITS GROUP (D-498).** The queue
duplicate rate is 10.1% apply / 12.8% review after the cap; 45 of the 71 redundant leads are already
grouped under `cross_host` and delivered by design. Rule (a): drop a lane member of a `cross_host`
group when an employer-board member is in it — up to 28 of 71, never hides a board posting. Rule (b):
collapse lanes-only groups to one — +11. Refuse (c), suppressing within any `cross_host` group: that
is Microsoft's four real Redmond requisitions. Delivery policy only; no `rules_hash` move. **Not
built. Mit's call.**

**0-B. JUDGE → LANE PROMOTION (D-489).** The review gate routes on the engine verdict alone; 46 of
the 123 review holds carry a judge `eligible` (16 `experience_requirement`, 21 `no_requirements_found`,
9 `role_unconfirmed`). Run 9 would have delivered ~31 apply-lane leads instead of 7. Promoting on a
judge `eligible` makes the judge an evidence source for `ELIGIBLE` with no quoted span (keystone,
D-458). Recommended: promote the two requirement holds only, never the role holds, blind-audit the
promoted cohort first. **Not built. Mit's call.**

**0-A. THE LANE STAGE'S THIRD-PARTY PACING IS WEAKENED ON THREE SCAN HOSTS, AND IT IS LIVE
NOW.** Found by the 09-06 review, re-sized by D-474 choice 1 from run 3's funnel, **not
introduced by anything shipped since SP2** (already on `main`, run in production twice).
`Fetcher._host_locks` and `_last_request_at` are PER INSTANCE and the lane stage's own instance
overlaps the scan, so a host both reach can see 2 in flight and 2 req/s. **The only such
traffic is hiringcafe's one GET per admitted board** — 94 in run 3: 40 to
`boards-api.greenhouse.io` (the scan spends 90.0 s there), 44 to `api.ashbyhq.com` (10.1 s),
10 to `api.lever.co` (12.0 s) — so the exposure is ≤ ~90 s on one host per run, not the lane
stage's 352 s. `grnh_seeds` is a CLI command and `jsonld`'s hosts are not scan hosts. **The
fix is T41** (shared pacing STATE, not a shared client — the client's default UA is what
linkedin and github_lists rely on). **Mit's call, and it is a pacing promise to third parties,
not a performance knob.**

**0. THE ≤ 1-YoE FLOOR — RULED (D-478 §5), PLANNED (D-479), ALL DECISIONS TAKEN (D-480).** D1 = T47
(per-user policy data). D2 = floor first, then arm the judge, both before run 4. D3 = above-band
stays hidden, no ticket. Reach confirmed for 2–3 y total bars, scoped bars > 1 y and 13–36-month
bars; hedged/preferred bars do not move. Nothing here is still owner-gated; it is execution.

**0-1. RETIRED / ANSWERED — held WHOLE in `STANDING-FACTS.md`.** Gate 1 is PER-SOURCE RECALL (D-421)
and only the per-source THRESHOLD is still owed; job-apps keeps running until it is met
(`RETIREMENT-PLAN.md`); Indeed's posture is decided (D-410, re-scoped by D-450). **Do not
re-litigate 80%, do not re-derive "most", do not re-probe Indeed.**

1. **PER-SOURCE THRESHOLDS — STRUCTURE RULED (D-482):** employer-board sources ≥ 85% independent
   recall; LinkedIn no bar. **Owed: the Indeed and hiring.cafe numbers at the first post-reset
   reading (~2026-09-17)**, with D-450 on the page again. The instrument
   (`.agent/2026-09-02-session/per_source_recall.py`) still points at the OLD account home for
   job-apps' ledger — a one-line fix before it runs.
2. **TRACK 1 — CLOSED (D-482): accept the loss**, per D-453. Do not re-raise it from the 382 or
   the 113.
3. **Mit's résumé calls** — whether to send a document at all; the D-220 prose rewrite of the submitted "sole iOS developer" answer (outside the bundle); the per-lens formatting session.
4. **P2 item 8 — the onboarding field-taxonomy gatherer. DEFERRED by Mit 2026-08-28.** The last
   multi-tenancy gap of its kind; D-054 forbids us authoring non-tech field content.
5. **`add-evidence` takes no bundle lock** (D-143) — raise before two authoring agents run against
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
5. **ANSWERED 2026-09-05 — T31 (`1fc61596`, on `close-2026-09-05`): `boardwatch init` seeds the
   bundled `resume_template.tex` when absent and never overwrites; the placeholder-phrase catalog
   still refuses the unedited copy, so the fail-closed guarantee is unchanged.**

## Phase status

**P0–P6 are all COMPLETE and their gates all MET, and none has moved in weeks — the full table
moved WHOLE into `STANDING-FACTS.md` on 2026-09-01e.** Read it there. Only these are not settled:

- **P2 item 8** (field-taxonomy gatherer) **NOT STARTED** — the last multi-tenancy gap, owner-gated.
- **P7 Breadth**: LinkedIn, GitHub-lists, jobapps, **`jsonld` and `indeed` are all built and ARMED**
  (D-420). Indeed's cap is **50 again** after one uncapped measurement run (D-459). **hiring.cafe is
  armed and WORKING**, and its 50-board sample is **reverted** (D-456) — watched boards 482 → 432,
  then 490 after run 149's Indeed convergences. Remaining tier-D lanes are **DECIDED AGAINST**, not
  deferred (D-451).
- **Provisional pass: recorded MET on runs 6, 7, 8 (D-483) — but runs 7 and 8's own funnels read `DOES NOT RECONCILE` (B6) through the reporting gap T60 closes (D-489); whether they stand is Mit's ruling.** 14-day confirm: day 1 = run 9 (2026-09-06 06:00 CDT, clean tick, same gap), passive. **B8 first reading (D-487): 17.2% on n = 128, 14.7% gate-judged; bar ≤ 16%.**
  Not chased (D-351 item 2: work comes first), and every `rules_hash` bump restarts the count.

## Live blockers and carried gaps

| Item | Detail | Owner |
|---|---|---|
| **boardwatch sees 16.4% of job-apps' eligible yield — RE-DERIVED 2026-08-30, and the METHOD was wrong before** | **45 of 275 (16.4%)**, cohorts 08-23..08-29, on the **379-board fleet**. This replaces "10.1%, owed a check". It decomposes: fleet growth 344->379 gave 10.1 -> **13.8%**; adding an **exact ATS-slug key** alongside name matching gave 13.8 -> **16.4%**. **Name-only matching undercounts, so 7.7% and 10.1% are FLOORS** — boardwatch stores Micron as `Micron TDIT`, so the old method scored a watched company as unwatched; same for HPE/`Hewlett Packard Enterprise`, Cox/`Cox Automotive`, Disney/`Walt Disney Company`, Toyota, VIAVI. **The unreached 230 split: aggregator-only 60.7%, unsupported employer host 21.1%, board-addable just 1.8%** (5 postings in 7 days, 4 of them SmartRecruiters — the class D-370 declined on measured cost), so the cheap remainder is ONE Workday board (Motorola Solutions). **The gap is lanes, not boards.** Script: `.agent/2026-08-30-session/reach_v2.py`. Amazon/TikTok/Apple/ByteDance use none of the 6 ATS, so a slug cannot reach them. Closing it means a new discovery lane — GitHub new-grad lists are 19.1% of yield for ~5 public-repo GETs and are NOT the ToS trap the v2 decision was written about. **Reopens D-008** | **Mit** (reverses a shipped decision) |
| **Citi sits at 13.1% coverage, permanently** | Workday's `total` censors at 2,000; the facet sum (uncapped, control-verified) says 4,589. Our pager wraps at ~2,000 too, so post-drain Citi holds ~2,214 of 4,589 and nothing reports it | **Mit** (input-side) |
| **Run 9 (2026-09-06) tick-fired CLEAN on the restored five-lane config (D-487, read D-489); run 10 is the first whose funnel can reconcile a split slate (T60)** | The launchd job invokes the **editable** venv at `boardwatch/.venv/bin/boardwatch`, so whatever branch that tree is parked on IS the unattended run's code and `rules.yaml`. **Park the primary checkout on `main` before ending every session**; a stray branch changes EVERY subsequent run. The tick fired 06:00 CDT until the 09-09 reboot and **04:00 CDT since** — launchd keeps its boot zone, and the plist's hour is 4. Verify a tick by `runs = N` in `launchctl print` and the log mtime, never by the run row alone: a hand run proves the code, only a tick proves the plist | **Mit** (reboot); every session (discipline) |
