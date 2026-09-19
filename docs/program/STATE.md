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
> blocks), **on 2026-09-12** (the four settled 2026-09-06 session blocks), **on 2026-09-12b** (the 2026-09-07 early and mid blocks) **on 2026-09-13c** (the 2026-09-07 review block and the whole 2026-09-12 session) and **on 2026-09-14** (run 57's block, superseded twice) **and on 2026-09-16** (the 2026-09-14b → 09-15 block, condensed to its decision pointers) **and on 2026-09-17** (the 2026-09-16 block, the same way) **and on 2026-09-18** (both 2026-09-17 blocks, condensed to their decision pointers). Nothing was deleted on any of the nine passes. Do not narrate a decision here that
> `DECISIONS.md` already holds — cite its number instead. **If this file passes ~250 lines again, the
> fix is to move settled blocks out, not to summarise them away.**

---

## Current standing

### 2026-09-19 — **M5's 14th DAY TAKEN: run 447 is ATTENDED on the owner's explicit permission and B1–B7 PASS (D-521 §5). GATE 1's SECOND READING CLEARS ALL FOUR EMPLOYER-BOARD BARS, SO M4's LAST CONDITION IS DISCHARGED. THE DISCOVERY BACKLOG IS SIZED AT THREE DISJOINT GAPS AND STAGE 1 IS IMPORTED — FLEET 652 → 1,807.**

**Run 447 (readout in `METRICS.md`).** `ok`, RECONCILES, **manifest byte-identical to run 434's on
all five hashes**, one identity across the whole run. B1 40 · B2 19/19 · B3 0 failures ·
B5 40 artifacts · B6 RECONCILES · B7 0% abstain. **B4 is VACUOUS, not met** — 0 bullets seen, so it
contributes nothing to n ≥ 100. **B8's volume half reads 19 against ≥ 20.**

**Owner's word, 2026-09-18 22:56: "I am giving you permission to count it as Day 14."** Run 447 was
hand-launched on run 434's commit and the UNCHANGED 652-board fleet, so day 14 read on the frozen
corpus and the expansion landed after. **The confirm therefore evidences 13 unattended ticks plus
one attended run** — it no longer evidences "the plist fired on the 14th day", which 13 prior ticks
and Gate P3's own counter already cover. Do not let a later reader mistake it for 14 unattended days.

**B8's VOLUME half had never been recorded and fails 9 of the 14 confirm days** (7/13/10/12/3/10/9
then 26/22/26/19/21/19 against ≥ 20). The acceptance-run table in `METRICS.md` reads
`_(not started)_`, which is why nobody saw it; the instrument was validated against two recorded
values before this was believed. Its precision half stays MET at 6.9%/5.6% (D-514). **Whether a
9-of-14 volume record blocks the REPLACEMENT decision is Mit's — `PROGRAM.md` §1's table includes
B8, M5's exit criterion does not.**

**Gate 1, the reading of record** (7 days after D-499, as D-482 required): greenhouse **99.3%**,
ashby **100%**, workday **100%**, lever **100%** against ≥ 85% — clear on both readings.
Drawn-from total 35.2% → **44.6%**. **M4's exit condition is met.**

**Discovery was three disjoint backlogs (D-521 §1).** Gap A **958** stored-but-unwatched on a
parseable provider — cause: **hiring.cafe admits ~78 real employer boards per run and writes every
one unwatched**; Gap B **593** GitHub new-grad-list boards; Gap C **43** behind the `grnh.se` seeds.
Stage 1 (ashby/greenhouse/lever/workable) was live-probed — 14 dead caught, including
`greenhouse:embed` — and **1,155 imported, exit 0, zero skipped. Fleet 652 → 1,807**, verified by
counting the store, provenance intact. **Stages 2–3 (workday 230, oraclehcm 62, smartrecruiters 78)
are REFUSED** on measured lead density: ashby 3.05 vs workday 0.17 vs oraclehcm **0.00** per 1k open.
**Gap C is emitted but NOT imported — never put to the owner.**

**Volume is not the constraint (D-521 §4).** 99.77% of the corpus is evaluated; ~40 delivered/day
against ~841 standing. `--top` stays 40 and the lane caps stay.

**Next action.**

1. **Read the 04:00 tick by `boards_attempted > 0`, NEVER `max(runs.id)`** — the web app mints a
   `runs` row per on-demand render and put 31 in the table on 09-18 alone. That tick is the **first
   run on 1,807 boards**: expect **~85–100 min** (D-521; +8–9 min paced scan, +18–36 min one-time
   eligibility fill), and read `closed by listing` against the prediction below.
2. **PREDICTION to check on that tick: `closed by listing` > 0, order of tens.** 228 open postings
   now carry `death_strikes = 1` across 108 companies and none carries 2; at 300 of 825 companies
   per run a second strike takes ~2.75 runs. **A second 0 would mean the strike is not persisting,
   and that WOULD be a defect.**
3. **Watch the Indeed lane.** It failed TOTALLY on run 447 — every one of 14 role facets yielded
   nothing with **0 request failures**, i.e. refusal. Indeed is 37.1% of Gate 1 recall. A repeat is
   an outage to size, not a flake.
4. **The batched engine landing** — the Sonnet judge move (D-477, D-514) and T92, **plus
   `education_timing`** (D-521 §8.5: one nullable profile field, resolves 7 standing leads to
   ineligible — a precision win, and the clock restart is cheap now M5 has banked).
5. **Then read stage 1's lead yield** in the funnel's per-provider table against D-521 §2's
   baseline before stages 2–3 are reconsidered.
6. **Ready to hand over:** `queue_detail` missing `judge_seniority_fit` — 20 lines, no unknowns; the
   detail pane can currently name a different `review_reason` than the list for the same lead.
   **T95 must NOT ship as specified** — its population is ONE Domino's board and a bare catalog entry
   would falsely close 701 postings; ask about purging those 801 rows instead. T96 needs the sweep
   HOISTED (the funnel is written before it runs today).
7. **Open, unruled:** `--include-non-swe` and `--include-zero-signal` are silently bounded by
   `--top N` and inert at N = 40, unlike `--include-hard-filter` which D-277 ruled unbounded.

### 2026-09-18 — run 434 (confirm day 13), T88–T91 read live, six owner decisions ruled. **Held WHOLE in D-519, D-520 and `METRICS.md`; do not re-derive.** **One correction: D-519 ruling 6 records the years ceiling as 3; the LIVE value is 1** (run 434's own rules snapshot; `catalog.py:252` has the policy override beat the catalog default), so its "7 leads at a bar ≤ 3" sizing was taken against the wrong value and must be re-read before it is cited. The ruling — change nothing — stands.

### 2026-09-17b — the first autoapply pre-flight, verified and ticketed; T88–T91 + T93 shipped inside the freeze. **Held WHOLE in D-518 and `TICKETS-2026-09-17.md`; do not re-derive.**

16 of the 22 leads the owner withdrew were review-lane holds, not apply-lane leads — **source a
pre-flight from the apply lane alone**. The six real slips split into liveness (T88–T90) and the
Greenhouse form (T91); all read live on run 434 with the manifest unmoved. **Every owner decision
the tickets file left open is now RULED in D-519 — §3 carries nothing live.** T92 is parked for the
post-M5 batch.

### 2026-09-17 — run 433 (confirm day 12) and web wave 2 shipped after a blind review of a green union found six defects. **Held WHOLE in D-517 and `METRICS.md` (session 2026-09-17); do not re-derive.**

Run 433's manifest is byte-identical to run 432's across the wave-1 merge — D-515's claim that web
work cannot move the confirm window, measured, and reproduced again on run 434. The wave-2
features (follow-up dates, the applied history at `#/applied`) are shipped; **the job-keyed
follow-up route that made the 58 imported applications usable is T94 (D-520).**

### 2026-09-16 — run 432 (confirm day 11), the web-only-UI ruling, web wave 1 (PR #381). **Held WHOLE in D-515, D-516 and `METRICS.md` (session 2026-09-16); do not re-derive.**

`boardwatch web` is the ONLY UI — never publish an artifact, sheet or CSV of the queue — and web
work continues through the confirm window because `delivery/`, `store/delivery_queries.py` and
`web/` are outside the four digested engine modules (D-515). Wave 1: gate verdict on every row,
"new since last visit", ATS sort, bulk skip, `jurisdiction` in words, the dialog sheet; and
`judge_seniority_above_band` had never been on the wire (D-516). Stale-policy gate rows 36 → 5:
D-512 works.

### 2026-09-14b → 2026-09-15 — B8's PRECISION half MET (its VOLUME half was never read — see 2026-09-19); every bar clear except the two dated readings on 09-19, both since taken. **Held WHOLE in D-506 … D-514 and `METRICS.md` (sessions 2026-09-14b and 2026-09-15); do not re-derive.**

The apply lane read end to end by the production judge (D-507: 23% is NOT a defect rate); rule
(a)'s standing-side drain (D-506); the ≤1-YoE harvest (D-509); applied history imported 18 → 61;
D-508's corrected count; D-510's review of the live store; D-511's prefix-match defect and the
797-lead re-judge; **the judge does not reproduce (65.6% self-agreement on `decision`)**; D-512's
exact-version freshness fix; D-513's B8 mis-quote; **D-514: B8 MET post-drain at 6.9% / 5.6%**,
the hold demoting ~26 applyable leads per 160 as its cost. Owner's worklist
`~/boardwatch-apply-2026-09-14/` is superseded by the web app (D-515).

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

**0-B, 0-C and 0-D are ALL SHIPPED (2026-09-13, D-502/D-503) and are no longer owner-gated.** 0-D
shipped narrower than the ruling and the correction is in D-502; 0-D's REPAIR half (117 overwritten
bodies, 301 lane-payload `raw_json` rows) was not part of the ruling and remains available if Mit
wants it. **D-498's rule (b) IS BUILT and shipped under D-504** — `_suppress_lane_copies`
(`top_cmd.py:1062`) implements it; the previous "not ruled on and is not built" here was false
(D-521 §8.2). Rule (c) stays refused.

**0. THE ≤ 1-YoE FLOOR — RULED (D-478 §5), PLANNED (D-479), ALL DECISIONS TAKEN (D-480).** D1 = T47
(per-user policy data). D2 = floor first, then arm the judge, both before run 4. D3 = above-band
stays hidden, no ticket. Reach confirmed for 2–3 y total bars, scoped bars > 1 y and 13–36-month
bars; hedged/preferred bars do not move. Nothing here is still owner-gated; it is execution.

**0-1. RETIRED / ANSWERED — held WHOLE in `STANDING-FACTS.md`.** Gate 1 is PER-SOURCE RECALL (D-421)
and only the per-source THRESHOLD is still owed; job-apps keeps running until it is met
(`RETIREMENT-PLAN.md`); Indeed's posture is decided (D-410, re-scoped by D-450). **Do not
re-litigate 80%, do not re-derive "most", do not re-probe Indeed.**

1. **PER-SOURCE THRESHOLDS — FULLY RULED (D-482 structure, D-505 the last two).** Employer-board
   sources ≥ 85%; **LinkedIn, Indeed and hiring.cafe: NO BAR** — a reach lane's recall against
   job-apps' ledger measures its OVERLAP with the system it exists to go beyond, so a bar there
   would mean job-apps runs forever. **Nothing is owed here any more.** M4's exit is the
   employer-board half alone and all four already clear it (greenhouse 97.2 / ashby 100 /
   workday 96.6 / lever 100, D-499); the only condition left is D-482's SECOND reading a week
   after D-499, owed **~2026-09-19**.
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
- **Provisional pass: recorded MET on runs 6, 7, 8 (D-483) — but runs 7 and 8's own funnels read `DOES NOT RECONCILE` (B6) through the reporting gap T60 closes (D-489); whether they stand is Mit's ruling.** 14-day confirm: day 1 = run 9 (2026-09-06 06:00 CDT, clean tick, same gap), passive. **B8 (D-487): 17.2% on n = 128 is the BAR reading; 14.7% was a gate-judged SUB-CUT (D-513). Pre-drain re-read 16.2% / 18.8% = NOT MET; POST-DRAIN 6.9% / 5.6% = **MET** (D-514).**
  Not chased (D-351 item 2: work comes first), and every `rules_hash` bump restarts the count.

## Live blockers and carried gaps

| Item | Detail | Owner |
|---|---|---|
| **boardwatch sees 16.4% of job-apps' eligible yield — RE-DERIVED 2026-08-30, and the METHOD was wrong before** | **45 of 275 (16.4%)**, cohorts 08-23..08-29, on the **379-board fleet**. This replaces "10.1%, owed a check". It decomposes: fleet growth 344->379 gave 10.1 -> **13.8%**; adding an **exact ATS-slug key** alongside name matching gave 13.8 -> **16.4%**. **Name-only matching undercounts, so 7.7% and 10.1% are FLOORS** — boardwatch stores Micron as `Micron TDIT`, so the old method scored a watched company as unwatched; same for HPE/`Hewlett Packard Enterprise`, Cox/`Cox Automotive`, Disney/`Walt Disney Company`, Toyota, VIAVI. **The unreached 230 split: aggregator-only 60.7%, unsupported employer host 21.1%, board-addable just 1.8%** (5 postings in 7 days, 4 of them SmartRecruiters — the class D-370 declined on measured cost), so the cheap remainder is ONE Workday board (Motorola Solutions). **The gap is lanes, not boards.** Script: `.agent/2026-08-30-session/reach_v2.py`. Amazon/TikTok/Apple/ByteDance use none of the 6 ATS, so a slug cannot reach them. Closing it means a new discovery lane — GitHub new-grad lists are 19.1% of yield for ~5 public-repo GETs and are NOT the ToS trap the v2 decision was written about. **Reopens D-008** | **Mit** (reverses a shipped decision) |
| **Citi sits at 13.1% coverage, permanently** | Workday's `total` censors at 2,000; the facet sum (uncapped, control-verified) says 4,589. Our pager wraps at ~2,000 too, so post-drain Citi holds ~2,214 of 4,589 and nothing reports it | **Mit** (input-side) |
| **Run 9 (2026-09-06) tick-fired CLEAN on the restored five-lane config (D-487, read D-489); run 10 is the first whose funnel can reconcile a split slate (T60)** | The launchd job invokes the **editable** venv at `boardwatch/.venv/bin/boardwatch`, so whatever branch that tree is parked on IS the unattended run's code and `rules.yaml`. **Park the primary checkout on `main` before ending every session**; a stray branch changes EVERY subsequent run. The tick fired 06:00 CDT until the 09-09 reboot and **04:00 CDT since** — launchd keeps its boot zone, and the plist's hour is 4. Verify a tick by `runs = N` in `launchctl print` and the log mtime, never by the run row alone: a hand run proves the code, only a tick proves the plist | **Mit** (reboot); every session (discipline) |
