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
> blocks), **on 2026-09-12** (the four settled 2026-09-06 session blocks), **on 2026-09-12b** (the 2026-09-07 early and mid blocks) **on 2026-09-13c** (the 2026-09-07 review block and the whole 2026-09-12 session) and **on 2026-09-14** (run 57's block, superseded twice). Nothing was deleted on any of the seven passes. Do not narrate a decision here that
> `DECISIONS.md` already holds — cite its number instead. **If this file passes ~250 lines again, the
> fix is to move settled blocks out, not to summarise them away.**

---

## Current standing

### 2026-09-14b — THE WHOLE APPLY LANE READ BY THE JUDGE; ≤1-YoE HARVESTED; APPLIED HISTORY IMPORTED; RULE (a) DRAINED; THEN REVIEWED, THE GATE BACKFILLED, ITS FRESHNESS TEST FIXED, AND B8 RE-READ: **D-506 … D-513.** PRs #377, #378 both MERGED.

**Owner is mid-preparation for a mass-apply session.** Everything below is about the lane he opens.
Run 308's readout (confirm day 9, all five predictions held) moved to `METRICS.md`.

**The apply lane is no longer unverified.** All 505 leads read by the PRODUCTION judge (same prompt,
model, parser, config dir), 39 batches, **0 failed open**, deliberately NOT persisted — D-477 pt 5
forbids re-judging and 476 already carried a gate row. **116 above band (23.0%), 32 now `ineligible`.**
**Do NOT quote 23% as a defect rate** (D-507): D-503's 16.3% used two judges at 96.4% agreement over
ALL causes; this is one model over one cause, and ~13% of its flags are false.

**`gate.seniority_hold` is ARMED** — read back through `load_settings()`, not the file. It held **7
on run 419**, its first live reading.

**Rule (a)'s standing-side drain SHIPPED (D-506, PR #378) and is verified against the LIVE queue:
17 folders moved to `_lane_copy`, 0 failed, apply lane 505 → 488.** `cross_host` still suppresses
nothing; the discriminating test is §3.1's board-vs-board pair, mutation-verified.

**The ≤1-YoE slice of `_skipped` is harvested (D-509): 298 of 304 landed (98.0%).** The refresher
now maintains `_eligibility_review`, `_review_later` and both `min_1_year_*` buckets on FUTURE
dates, so **tomorrow only the new cohort is left**. Every other skip reason stays unlinked.

**Applied history imported: applications 18 → 61**, 59 on still-open postings. The 83 Indeed `jk=`
rows were correctly refused as `ambiguous` (D-488's fix holding).

**A REPORTED NUMBER WAS WRONG AND IS CORRECTED IN D-508.** The ≤1-YoE floor had already shipped
2026-09-09; the 35,941-row figure that said otherwise was an UNSCOPED count over
`eligibility_requirements`, which carries no identity column. **Confirm INTACT at day 9.**

**THE SESSION WAS THEN REVIEWED AGAINST THE LIVE STORE AND QUEUE — D-510.** Every identity-scoped
claim reproduces, including D-508's own correction (**zero `met` rows at any low end ≥ 2, so the
≤1-YoE floor IS in force**), `476`, `471`, all five store totals and `59 still-open`. **The FOLDER
counts were the ones that were wrong**: an empty `.staging-` leftover was counted as a lead, so the
lane was **505 → 488**, and `yes`/`eligible` were each one low. **`116/505 = 22.97%` — the 23.0%
headline and D-507's framing are UNCHANGED, and the owner's worklist audits CLEAN** (tier `1b` is
exactly the union of 116 + 32 + 17 = 140, zero unexplained, zero leak into tier 1). No code changed.

**WEB IS NOW AT PARITY WITH THE SHEET, AND THE REASON IT WAS NOT IS A DEFECT — D-511.**
`current_gate_verdicts` matches `engine_version` by **PREFIX** (`final_gate:%`) and `run_gate_stage`
uses it as the never-re-judge test, so the 09-13 `seniority_fit` policy bump left **434 of 505
apply-lane leads and 686 store-wide permanently unreachable** — reading `unclear` forever, and **no
nightly run would ever have fixed it.** Owner ruled judge-the-lane-now; **797 judged, 0 failed
open** (runs **427–430**), store-wide stale **686 → 36**. Web serves apply lane **144** above band
(was 11), review lane 101. **19 apply-lane leads are now gate-`ineligible`. A drain for them was
PREDICTED AND THE PREDICTION WAS WRONG** — `ineligible_job_ids` filters on `verdict` (the
DETERMINISTIC lane), not `judge_verdict`, so **0 of the 19 drain**. A gate `ineligible` filters
FUTURE shortlists; it never evicts a STANDING delivered lead.

**THE JUDGE DOES NOT REPRODUCE, and this outranks the parity work.** Same 462 leads, same prompt /
haiku / parser, two occasions: **`seniority_fit` 68.2%, `decision` 65.6%** agreement. Marginals are
stable, membership churns. **So D-507's 116 (23.0%) and tonight's 144 (28.5%) are the same
measurement with different dice — neither is a stable list.** Confound named and testable: batch
composition differs between runs. **Vindicates demote-not-delete; argues AGAINST `seniority_hold`
actually withholding.**

**THE PREFIX MATCH IS FIXED — D-512.** D-511 called it a defect too broadly: the prefix is
DELIBERATE and RIGHT for a display reader. The defect was ONE read serving TWO questions, so
`current_gate_verdicts` now takes a keyword-only `engine_version` and **only `run_gate_stage`
passes it**; the five display call sites and `current_gate_seniority` are untouched. Red-first test
verified to FAIL against the reverted fix. **A `POLICY_VERSION` bump now RE-OPENS every lead for
re-judging — the semantics the knob always claimed and never had, so bump it only when the corpus
should be re-judged.** Residual ~36 leads.

**B8 IS NOT MET, AND WHAT IT READS WAS MIS-QUOTED — D-513.** `17.2%` (D-487, whole lane, 22/128) is
the BAR reading; the `14.7%` this file quoted is a gate-judged SUB-CUT, so **B8 has never been
cleared**. Re-read on D-503's sonnet+opus instrument over 160 standing apply-lane leads, **run twice
on the IDENTICAL sample: 16.2% then 18.8%** — both FAIL. **The instrument's own spread is 2.6pp, so
a ≤16% bar cannot be adjudicated by one reading**; inter-rater agreement (98.1% / 96.2%) shows the
two models are ALIKE, not that the measurement is STABLE. **The miss is 28 seniority / 2 work_auth —
93% seniority**, the least reliable signal in the system. Batch composition is RULED OUT as the
cause of the judge's churn (same-grouping ≈ shuffled); it is model nondeterminism.

**THE DECISION IS OPEN AND IS MIT'S — three options put to him 2026-09-15, none answered:**
(1) apply `gate.seniority_hold` retroactively to the 505 standing leads (the same rule it already
applies to NEW leads; would read ~1.5%, but costs ~140 leads out of his Tier 1 mid-apply-session, so
**not done unilaterally**); (2) record B8 NOT MET and call done on D-280's provisional pass (B1–B7 +
P5b, met on runs 6–8), carrying B8 as debt; (3) re-set the bar, his under D-477. **Nothing was
mutated** — the lane, queue and config are untouched.

**Owner's worklist is `~/boardwatch-apply-2026-09-14/`** (not a repo artifact): 365 Tier 1 rows of
which **345 are distinct work** (20 are rendered but marked duplicates — the sheet's "345" is that
net figure, verified correct on review) / 140
Tier 1b demoted / 163 Tier 2, artifacts copied locally so links survive a reconcile. Its checkboxes
do NOT reach boardwatch — applications need `boardwatch track add <posting_id>`.

**Next action.** (1) **Read the 04:00 tick on 09-15 — read `max(runs.id)` for its number, do not
guess it**; the gate backfill minted **427–430**, so expect **431**. It is
**confirm day 10 of 14**. Watch `seniority_judged_above_band` now the hold is ARMED, and
`to_lane_copy` on the first unattended reconcile. (2) **The second Gate 1 reading is owed ~09-19 and
is the LAST condition on M4** — D-505 ruled no bar for Indeed and hiring.cafe, so the employer-board
half alone decides and all four already clear 85%. If it holds, **job-apps switches off.** (3) Still
open from D-494: seed the cluster cap from the standing queue; ratify `apple`'s
`board_reported_total = None`. (4) NOT built, sized only: ATS sort in `boardwatch web` needs
`provider` carried store → API → type → sort (never the URL host class, `delivery_queries.py:527`);
and `details.json` naming WHICH lead supersedes a drained lane copy (`DETAILS_SCHEMA` is versioned).

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
wants it. D-498's rule (b) — collapsing a lanes-only group to one member, +18 on today's queue — was
not ruled on and is not built; rule (c) stays refused.

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
- **Provisional pass: recorded MET on runs 6, 7, 8 (D-483) — but runs 7 and 8's own funnels read `DOES NOT RECONCILE` (B6) through the reporting gap T60 closes (D-489); whether they stand is Mit's ruling.** 14-day confirm: day 1 = run 9 (2026-09-06 06:00 CDT, clean tick, same gap), passive. **B8 (D-487): 17.2% on n = 128 is the BAR reading; 14.7% is a gate-judged SUB-CUT, not the bar (D-513). Re-read 2026-09-15: 16.2% then 18.8% on the same 160. NOT MET.**
  Not chased (D-351 item 2: work comes first), and every `rules_hash` bump restarts the count.

## Live blockers and carried gaps

| Item | Detail | Owner |
|---|---|---|
| **boardwatch sees 16.4% of job-apps' eligible yield — RE-DERIVED 2026-08-30, and the METHOD was wrong before** | **45 of 275 (16.4%)**, cohorts 08-23..08-29, on the **379-board fleet**. This replaces "10.1%, owed a check". It decomposes: fleet growth 344->379 gave 10.1 -> **13.8%**; adding an **exact ATS-slug key** alongside name matching gave 13.8 -> **16.4%**. **Name-only matching undercounts, so 7.7% and 10.1% are FLOORS** — boardwatch stores Micron as `Micron TDIT`, so the old method scored a watched company as unwatched; same for HPE/`Hewlett Packard Enterprise`, Cox/`Cox Automotive`, Disney/`Walt Disney Company`, Toyota, VIAVI. **The unreached 230 split: aggregator-only 60.7%, unsupported employer host 21.1%, board-addable just 1.8%** (5 postings in 7 days, 4 of them SmartRecruiters — the class D-370 declined on measured cost), so the cheap remainder is ONE Workday board (Motorola Solutions). **The gap is lanes, not boards.** Script: `.agent/2026-08-30-session/reach_v2.py`. Amazon/TikTok/Apple/ByteDance use none of the 6 ATS, so a slug cannot reach them. Closing it means a new discovery lane — GitHub new-grad lists are 19.1% of yield for ~5 public-repo GETs and are NOT the ToS trap the v2 decision was written about. **Reopens D-008** | **Mit** (reverses a shipped decision) |
| **Citi sits at 13.1% coverage, permanently** | Workday's `total` censors at 2,000; the facet sum (uncapped, control-verified) says 4,589. Our pager wraps at ~2,000 too, so post-drain Citi holds ~2,214 of 4,589 and nothing reports it | **Mit** (input-side) |
| **Run 9 (2026-09-06) tick-fired CLEAN on the restored five-lane config (D-487, read D-489); run 10 is the first whose funnel can reconcile a split slate (T60)** | The launchd job invokes the **editable** venv at `boardwatch/.venv/bin/boardwatch`, so whatever branch that tree is parked on IS the unattended run's code and `rules.yaml`. **Park the primary checkout on `main` before ending every session**; a stray branch changes EVERY subsequent run. The tick fired 06:00 CDT until the 09-09 reboot and **04:00 CDT since** — launchd keeps its boot zone, and the plist's hour is 4. Verify a tick by `runs = N` in `launchctl print` and the log mtime, never by the run row alone: a hand run proves the code, only a tick proves the plist | **Mit** (reboot); every session (discipline) |
