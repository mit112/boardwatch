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

### 2026-09-18 — **RUN 434 CLEAN (confirm day 13) AND T88–T91 ALL READ LIVE WITH THE MANIFEST UNMOVED; SIX OWNER DECISIONS SIZED THEN RULED — FOUR PRECISION FAMILIES REFUSED, THE YEARS CEILING HELD, THE PROBE BUDGETS RAISED (D-519); T94 SHIPPED (D-520).**

**Run 434 (readout in `METRICS.md`).** 04:00 tick, `ok`, 57 min to the funnel, RECONCILES.
**Manifest byte-identical to run 433's**, which is what D-518 asked of T88–T91. Both `death probe:`
lines, the `application forms:` line and the `p_form_questions` migration all landed. `0 closed by
listing` is the EXPECTED first reading — two strikes in different runs close, so **run 435 is the
first that can close a listing-absent row; read the listing half there.** `postman` Greenhouse 404
and Magnite Workday 422 are on their second day.

**The lane the owner opens:** apply **381** (147 affirmatively `eligible`, 234 `uncertain`, never
summed), review **379**, applied-ever **104** (was 400 / 370 / 61 on 09-17). Two paths agree on the size (API counts
and the on-disk queue). T91's first three live catches are in the review lane as
`form_question_hard_stop`. **The owner's autoapply is already in the ledger** (28 applied + 18
withdrawn on 09-18, notes carrying `autoapply 2026-09-18`); job-apps' `_applied` tree is unchanged
since 08-15, so **no applied-history import is owed**.

**D-519 closed the whole §3 list and the web calls.** Every option was measured against the 760
standing leads before being put to the owner, and five of six answers are "no" because the reach
is 0–9 leads: 3.1 visa classes → the judge; 3.2 `defense_employer` → not built; 3.3 title entropy
→ REFUSED; 3.4 structured salary → REFUSED (0 standing leads carry one); 3.5 **a structured field
is NOT the frozen JD**, so T92 holds for review and can never say `ineligible`;
`near_miss_years_ceiling` **stays at 3** — and its "biggest lever" framing is RETIRED (475
review-lane holds on 09-03, 26 today; bound: that is a LANE reading, not the corpus). Every D-516
and D-517 web call is ratified as shipped. **Nothing from §3 is carried.**

**Operator numbers set (D-519).** `death_probe_budget` 50 → 300, `death_probe_company_budget`
100 → 300 in the owner's `config.toml`, read back through `load_settings`. **Residual: 660 of the
760 standing leads are on the URL path** (510 under an unwatched company), so 300 reaches ~59% of
them per run — a held lead is asked about roughly every second run, not every run.

**Next action — the two dated readings land tomorrow.**

1. **Read the 04:00 tick by `max(runs.id)`** — 435 on 09-19, **confirm day 14, M5's exit**. Read
   the listing half of the death probe: this is the run that can close.
2. **M4: the second Gate 1 reading (D-482) is owed ~09-19** and is the last condition.
3. **The moment M5 closes, ONE batched engine landing** (D-519): the Sonnet judge move (D-477,
   D-514) **and** T92 together, so the clock restarts once. NOT web work, NOT a new family.
4. **Then ticket the GitHub new-grad-lists lane** — approved 09-18, reopens D-008 by the owner's
   hand: 19.1% of job-apps' yield for ~5 public-repo GETs against a 16.4% reach.
5. **Still owed and small:** the form-sweep counts are console-only and not in the funnel (the
   sweep's report is not threaded to `run_funnel` at all — T96); `smartrecruiters` is the next
   T89 list endpoint (812 unwatched rows, 8 companies — T95); `queue_detail` does not carry
   `judge_seniority_fit`; a newly delivered Greenhouse lead renders once before the form sweep
   holds it.
6. **Web: nothing is ticketed.** Open: the below-the-cap "rest" view (spec D5, needs the ranker
   path the daily driver calls — owner's call after 09-19).

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

### 2026-09-14b → 2026-09-15 — B8 MET; every bar clear except the two dated readings on 09-19. **Held WHOLE in D-506 … D-514 and `METRICS.md` (sessions 2026-09-14b and 2026-09-15); do not re-derive.**

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
- **Provisional pass: recorded MET on runs 6, 7, 8 (D-483) — but runs 7 and 8's own funnels read `DOES NOT RECONCILE` (B6) through the reporting gap T60 closes (D-489); whether they stand is Mit's ruling.** 14-day confirm: day 1 = run 9 (2026-09-06 06:00 CDT, clean tick, same gap), passive. **B8 (D-487): 17.2% on n = 128 is the BAR reading; 14.7% was a gate-judged SUB-CUT (D-513). Pre-drain re-read 16.2% / 18.8% = NOT MET; POST-DRAIN 6.9% / 5.6% = **MET** (D-514).**
  Not chased (D-351 item 2: work comes first), and every `rules_hash` bump restarts the count.

## Live blockers and carried gaps

| Item | Detail | Owner |
|---|---|---|
| **boardwatch sees 16.4% of job-apps' eligible yield — RE-DERIVED 2026-08-30, and the METHOD was wrong before** | **45 of 275 (16.4%)**, cohorts 08-23..08-29, on the **379-board fleet**. This replaces "10.1%, owed a check". It decomposes: fleet growth 344->379 gave 10.1 -> **13.8%**; adding an **exact ATS-slug key** alongside name matching gave 13.8 -> **16.4%**. **Name-only matching undercounts, so 7.7% and 10.1% are FLOORS** — boardwatch stores Micron as `Micron TDIT`, so the old method scored a watched company as unwatched; same for HPE/`Hewlett Packard Enterprise`, Cox/`Cox Automotive`, Disney/`Walt Disney Company`, Toyota, VIAVI. **The unreached 230 split: aggregator-only 60.7%, unsupported employer host 21.1%, board-addable just 1.8%** (5 postings in 7 days, 4 of them SmartRecruiters — the class D-370 declined on measured cost), so the cheap remainder is ONE Workday board (Motorola Solutions). **The gap is lanes, not boards.** Script: `.agent/2026-08-30-session/reach_v2.py`. Amazon/TikTok/Apple/ByteDance use none of the 6 ATS, so a slug cannot reach them. Closing it means a new discovery lane — GitHub new-grad lists are 19.1% of yield for ~5 public-repo GETs and are NOT the ToS trap the v2 decision was written about. **Reopens D-008** | **Mit** (reverses a shipped decision) |
| **Citi sits at 13.1% coverage, permanently** | Workday's `total` censors at 2,000; the facet sum (uncapped, control-verified) says 4,589. Our pager wraps at ~2,000 too, so post-drain Citi holds ~2,214 of 4,589 and nothing reports it | **Mit** (input-side) |
| **Run 9 (2026-09-06) tick-fired CLEAN on the restored five-lane config (D-487, read D-489); run 10 is the first whose funnel can reconcile a split slate (T60)** | The launchd job invokes the **editable** venv at `boardwatch/.venv/bin/boardwatch`, so whatever branch that tree is parked on IS the unattended run's code and `rules.yaml`. **Park the primary checkout on `main` before ending every session**; a stray branch changes EVERY subsequent run. The tick fired 06:00 CDT until the 09-09 reboot and **04:00 CDT since** — launchd keeps its boot zone, and the plist's hour is 4. Verify a tick by `runs = N` in `launchctl print` and the log mtime, never by the run row alone: a hand run proves the code, only a tick proves the plist | **Mit** (reboot); every session (discipline) |
