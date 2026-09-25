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
> owner calls. **Settled subsystem history is moved WHOLE into `STANDING-FACTS.md`, never summarised
> away** — sixteen passes through 2026-09-22b; the seventeenth, **2026-09-22c**, moved the
> 2026-09-21 and 2026-09-22b blocks WHOLE once run 470 had been read against the 2026-09-21 block's
> recorded prediction, which was the last condition inside either; the eighteenth, **2026-09-22e**,
> moved the 2026-09-22d block WHOLE once its run-471 expectation was restated above. (2026-09-22f and 2026-09-23 moved
> nothing.) The twentieth, **2026-09-24d**, moved the 2026-09-24c block WHOLE once its chain, repair and
> owner calls were all done. The nineteenth, **2026-09-23b**, moved the 2026-09-23, 2026-09-22f and 2026-09-22c blocks
> WHOLE once run 471 was read and the pull to `de7ae153` done; the 22e block stays until run 472 is read. **Nothing has
> been deleted on any pass.** Do not narrate a decision here that `DECISIONS.md` already holds — cite its number
> instead. **If this file passes ~250 lines again, the
> fix is to move settled blocks out, not to summarise them away.**

---

## Current standing

### 2026-09-24d — **THE SESSION CLOSED ON MIT'S CALL BEFORE WAVE 3 (D-595). THE CHAIN SHIPPED (T199 #465, BUNDLE A #467, T210 #468, T209 #469, T188 #470, T208 #471) PLUS close6/close7 (#466, #472); THE 0-D REPAIR IS DONE (43 → 9 OPEN DAMAGED, THE NINE ARE `gone`); T173's TWO HEADING CLASSES ARE FIXED ON THE CARRIER (T215/T216, 1,189 CLEARS, ROUND 2 IN FLIGHT); A WHOLE-SWEEP REVIEW READ 0 BLOCKERS AND ITS FOLLOW-UPS ARE BUILT (T222–T226) AND REVIEWED; THE LIVE CONFIG'S GITHUB LISTS ARE RESTORED. THE PRIMARY IS ON `main` AT #472. THE NEXT SESSION IS HEADED BY THE ENTERPRISE SEAT.**

**Read `.agent/2026-09-23c-session/HANDOFF.md` FIRST — §0 says how the seat-headed session differs (memory by symlink,
executors share its window), §2 the four executors left RUNNING at close, §4 the wave-3 recipe.** Verify against
`git log origin/main`, `gh pr list` and the `<tag>.exit` sentinels before believing any of it.

**Next session, in order (do not start wave 3 until Mit says so — ruled 19:23 on 09-24):**
1. **Read the four executors' results** (HANDOFF §2): batch 4 round 2 (`bw-batch4`, the seven wrong clears must read
   `ineligible`), T173d round 2 (`bw-t173`, Codex's two T216 sentences must return to preference), batch 5
   (`bw-batch5`, T211–T213), batch 6 (`bw-batch6`, T214). Run the owed Codex rounds (batch 4 verification, T173d2
   verification, batch 5 and 6 review). Then T173e (rebase onto batch 4's round-2 head), rebase batch 5 and 6 behind it.
2. **Wave 3** (HANDOFF §4): stack t218, t226, fu3 (T222–T225), batch 4, T173, batch 5, batch 6 on `origin/main`; ONE
   `make check`; ship sequentially. Every engine ship re-keys `engine_version`.
3. **Read run 476** (04:00 CDT 09-25, on `6a7e548e`): LONG by design — T208 moves the facts key, so 298,389 open
   postings re-evaluate and gate verdicts re-judge through the refresh (D-595 F7). Also T198's prediction (db, hitachi,
   vfc, mtb complete on their second scan), hiring.cafe's recount by row, the GitHub lists fetching again.
4. Docs after wave 3: D-596 (what shipped, the two-arm readings), METRICS, this file.

**Rulings today (D-595):** do not start wave 3 this session; the seat heads the next; the planner's fix-first call on
T173 (D-590's 1,468 → 1,189 with the heading classes fixed) stood unopposed. **Config changed:** `lane_github_lists`
set to the two former defaults (review F4). **Store changed:** the 0-D repair (34 bodies), run 473 reaped.

**Open tickets** (`TICKETS-2026-09-22c.md` §2026-09-23c): READY for wave 3 — T218, T226, T222–T225; IN FLIGHT — batch 4
round 2 (T200–T202), T173 + T215/T216 (round 2), batch 5 (T211–T213), batch 6 (T214); WRITTEN — T219 (1,752 postings,
the largest engine lever left), T220, T221, T227; T198 waits for run 476.

### 2026-09-24c — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-24d.** The "no waiting" sprint day (D-594): eight rulings, the chain, wave gating. Every step it listed is done or restated above.

### 2026-09-23b — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-24.** Runs 472 and 473/474 read (D-580, D-588); the post-472 pull done; the owner calls it listed are all ruled (D-577); T170 (#439) and T172 (#434) shipped; T171 (#438) and T162 (#441) shipped.

### 2026-09-23 — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-23b.** The six-ticket stack (D-562), which finished merging only by rebase (D-568). Its run-472 step is restated in the block above.

### 2026-09-22f — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-23b.** T135 shipped (D-559), T123/T124 closed on measurement (D-558), the D-557 rulings, T161 measured and now SHIPPED (D-569). Every step in it is done.

### 2026-09-22e — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-24.** The eligibility batch's re-key ran as run 472 (D-580): judged 117, cached 0, apply lane 29, refresh 130 of 861; its predictions held.

### 2026-09-22d — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-22e.** T159 read (D-550: apply lane 5.4% unapplyable, B8 precision MET); T113 shipped and armed at 130/run (D-551, D-552); T127/T158 shipped. Its run-471 expectation is restated in the block above.

### 2026-09-22c — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-23b.** Run 470 read (D-547), T153 executed and the standing queue re-judged on `sonnet` (D-548), `gate.effort` shipped. Its last open item, run 471's reading, is answered in D-572.

### 2026-09-22b — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-22c.** T149 + T154 shipped (**read D-541 before touching `abstain_by_adjacent`**: the degree escape was abstaining bars the profile already met, 5,579 rows), T150 live, T92 and T151 shipped, T101 refused on measurement (D-544), T153 corrected (D-545) and now EXECUTED (D-548), T152/T105 designed (D-546). **Held in D-540 … D-546 — do not re-derive.**

### 2026-09-22 (earlier) — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-22b.** §5 refuted and already held by T109 (D-536); a catalog re-key RELEASES 117 held leads (D-537); the degree-waiver gap enumerated at 6,712 and ruled in (D-538); four tickets ruled and specced (D-539). **All four rulings are now discharged — see the block above.**

### 2026-09-21 — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-22c.** Run 469 inverted the priority: **the binding constraint is the SLATE CAP, not discovery** — read D-532 before proposing ANY discovery work; anything sized in "eligible postings added" is in the wrong unit. The drain refused (D-533); B8's 9-of-14 record superseded (D-534); the Windows `os.replace` race fixed (D-535). Its recorded prediction for run 470 is answered in D-547. **Standing from it: a CONTENDED `make check` is a FALSE NEGATIVE** — check `uptime` first; above ~load 8 vitest's 5 s timeouts fail and the count varies run to run.

### 2026-09-20g / 2026-09-20f / 2026-09-19 — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-21.**
Run 468's second reading (superseded by run 469, D-532); T104's refutation and rebuild (D-531, shipped);
the engine batch's opening (D-530 — it MERGED as `ea95c42c`); run 467, Gate 1's second reading clearing
all four employer-board bars, Indeed confirmed dead, and the stage-1 import that took the fleet 652 →
1,807 (D-521, D-522). **Do not re-derive any of it.** One correction carried forward: D-522 §3's sizing
rule (size from fleet density, predict yield from the sample) is **superseded by D-532** — both halves
are denominated in eligible postings, which is the wrong unit once the slate cap binds.

### 2026-09-20d/e — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-20g.** The astra remediation wave: thirteen tickets in one gated wave, merged (D-528, PR #398 → `09df0e87`); Windows green and the five-night red over; the composite-title asymmetry REFUTED; T136's `ge=1` deliberately unchanged; next action 4's one-time re-judge FIRED and CLEAN on run 468. **Held in D-528 — do not re-derive.**

### Astra reviews 01–05 — **CONSUMED AND CLOSED.** All five slices, 42 findings, nothing refuted. Held WHOLE in **D-523 … D-527** and the five `TICKETS-2026-09-*-ASTRA-0*.md` files; the remediation that followed is **D-528**. **Do not re-derive any of it.** Of T98–T148 (51 tickets), **33 shipped**; **T145/T146/T147 are not build work** (owner DO-NOT-BUILD, future-reading guidance, LinkedIn posture); **T100–T105 are held as ONE engine bump** with next action 4; and of what stayed open, **T113 and T127 shipped (22d), T135 shipped (22f), T123 and T124 closed on measurement (D-558), T125 was rebuilt as an annotation, and T138's reverse half is refused (D-557); T144, T133, T137, T138's per-kind half, T139's stage extraction and T125 all SHIPPED on 2026-09-23 (D-562, D-568). Every astra ticket is closed.**

### 2026-09-19 — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-22b.** The expansion is measured and works (run 467, D-522); Indeed confirmed dead; M5's 14th day taken and B1–B7 pass (D-521 §5); Gate 1's second reading discharges M4's last condition; the discovery backlog sized at three disjoint gaps and stage 1 imported, fleet 652 → 1,807. **Held in D-521 and D-522 — do not re-derive.**

### Owed, and specifically NOT done

- **THE DEGREE-WAIVER WIDENING SHIPPED 2026-09-22b (D-540), all ten arms.** The enumeration
  (6,712) was a TEXT-MATCH count, not a verdict-change count: the live two-arm reading over the
  6,964-posting delta is **10 rescued from `ineligible`, 0 demoted, 0 newly ineligible** once
  D-541's `met`-abstain fix is included. `or foreign equivalent` stays excluded and is now pinned by
  a control; the **pre-existing** direction-blindness is unchanged and still not fixed. **The
  verdict-level effect over the 65,879 postings the OLD escape already matched is NOT attributable
  from persisted state** — run 470's re-judge bundles the engine batch, #407 and T150 (D-547). Do
  not re-derive it from the store; only a replay at each commit could separate them.
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

**0-D's REPAIR half is the one LIVE residual from the four settled owner-gated items moved to
`STANDING-FACTS.md` on 2026-09-21** (0-B/0-C/0-D shipped, the <= 1-YoE floor ruled and executed,
0-1 retired, per-source thresholds fully ruled — **nothing is owed on any of them**). The repair:
117 overwritten bodies and 301 lane-payload `raw_json` rows, never part of the ruling, still
available if Mit wants it. **D-498's rule (b) IS BUILT** (`_suppress_lane_copies`,
`top_cmd.py:1062`); rule (c) stays refused.

2. **TRACK 1 — CLOSED (D-482): accept the loss**, per D-453. Do not re-raise it from the 382 or
   the 113.
3. **Mit's résumé calls** — whether to send a document at all; the D-220 prose rewrite of the submitted "sole iOS developer" answer (outside the bundle); the per-lens formatting session.
4. **P2 item 8 — SHIPPED as T184 (#444, D-581).** 5. **The bundle lock — already shipped 2026-09-04 (`ae64c0ee`); closed.**
6. **T173 — RULED YES (D-594); re-measured with its heading classes fixed (D-595): 1,189 clears, ships in wave 3.** (History:
   Yes ⇒ 1,468 postings move `uncertain` → `eligible` (about five times today's `eligible`), all stated
   preferences (20/20 sampled), ~13 wrong clears inherited from two main-side defects (T196, T197). No ⇒ they
   stay `uncertain` with no row. Rebased on the batch in `bw-t173`; gate not yet run.)
7. **T188 — SHIPPED (#470, all three; D-594).** (History: D1 moves `PROMPT_VERSION`,
   so EVERY stored gate verdict re-judges once through the refresh at 130 a run; the owner accepted it.)
8. **`career_field` vs the taxonomy field — RULED and SHIPPED as T208 (#471, D-594): the taxonomy is the one source.** (History, D-586: the ranker's field gates read the taxonomy's field;
   `Facts.career_field` is NULL on the live profile and its catalog accepts only `software`. Reconcile
   (one source), or retire `career_field` from the eligibility facts.)
9. **The reviews' follow-ups** (§2026-09-23c): the `_recovered` reserved-name collision, the funnel's
   `location_class` column still the US reading, cross-check disagreements not soft-alerted, the
   STANDING-FACTS grounding key, T190's test-only drift, T192's trickled-headers limit; from run 475: T198 (the board cap vs slow Workday
   boards) and T199 (hiring.cafe's 9-vs-10 recount); from T173's measurement: T196 (`a plus` without a word
   boundary) and T197 (an aside about another noun hedges the bar) — both now IN batch 3; from batch 3's round 2
    (D-592): T200, T201, T202 — engine batch 4, round 2 in flight (D-594); T211–T214 written.
10. **The T179 refresh backlog — RULED: fixed by ORDER, T195 SHIPPED (#459, D-594).** (History, D-589: 315 top-level leads with no live verdict, 14 of them judged
    `ineligible` on 09-22 and standing in the apply lane. Options: raise `gate.refresh_budget` above 130
    for a few runs; have the refresh rank released holds first (T195); or let it drain at ~6 runs.)

## Open questions — Mit's, not to be resolved by fiat

**B8's RETIREMENT question is RULED and CLOSED (2026-09-21, D-534) — do not re-raise it.** The
9-of-14 volume record does not block: all 14 days are on the 652-board fleet, post-expansion
`pdf.entered` reads **25 / 22 / 26 (3 of 3, mean 24.3)**, and the engine batch's `rules_hash`
move restarts the 14-day confirm by `PROGRAM.md` §1's own rule anyway. **What is owed is B8's
volume half holding 14 days on the 1,807-board fleet.** Run 471 read 20; runs 472 (the batch) and
473 (T161/T163/T169) each re-key, so the window's day 1 is **run 473** (D-566, D-572). This is a
DIFFERENT question from item 0 below, which is about the alert CHANNEL.

0. **B8's volume reading on the escalation channel — CLOSED 2026-09-22e (D-554).** D-529's
   condition is met (post-expansion 25/22/26/20, and 1 of 5 at worst after run 471, against 9 of
   14 pre-expansion). The owner ruled: onto the channel. It is shipped; `summary.errors` now carries
   it.

1. **The projection spec's six open questions** (§12).
2. **The Snap `Level 3`/`Level 5` leak stays open by design** — with no bindings file every level
   token abstains. boardwatch ships no verifiable claim about any company's ladder.
3. **Whether `censored` boards publish a coverage ratio, and the 17 silent boards.** The class is
   **15 boards and 43,371 postings that can never be listed at all** (run 127) against an ~84,821
   open corpus. **Sized, not solved, and no budget can solve it.** See D-336.
4. **`ServiceNow Developer` — RULED (D-577 §1): excluded as personal policy data**, the seven
   platform-developer titles added to `exclude_titles` at the 2026-09-24 cutover (D-588).
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

**THE FIVE-NIGHT WINDOWS RED IS OVER, AND THE 2026-09-21 NIGHTLY WAS A DIFFERENT, REAL DEFECT
(D-535).** T128's three fixes and the `%s` strftime fix hold — all three read **zero occurrences**
on every run since. What took the 09-21 nightly (`35607814820`) red was ONE test on Windows 3.12
alone: `test_a_lock_free_reader_only_ever_sees_a_complete_tree`, `CURRENT is unreadable:
Permission denied`, on **1 failed / 10,499 passed**. It had passed on the 09-19 and 09-20
nightlies and on both dispatches, so it is an **intermittent race, not a break** — and the race is
real: `os.replace` on `CURRENT` denies concurrent opens on Windows, so the lock-free reader saw
neither revision. Fixed; see D-535. **Only a Windows dispatch can confirm the race is gone and ONE
green run is not enough** — at the observed rate a single pass proves almost nothing, so read
several nightlies before calling it closed. **The 2026-09-22 nightly (`35727396657`, on the fix) is the first
green scheduled nightly after four reds, all three `windows-latest` jobs green — n = 1.**

**READ A WINDOWS RESULT BY TEST NAME AND COUNT, NEVER BY COLOUR.** The dispatch before this one
(**35547739139**) was also red, and it did NOT mean the fix had failed: T128's three targets were
already at 0 occurrences while 46 *different* tests failed on the unrelated `%s` break. A red
dispatch is a list of names to compare against the ones you expect. The green one was confirmed a
real run the same way: Windows 3.13 read 10,500 passed / 85 skipped against local's 10,584 / 1, and
**10,584 − 10,500 = 85 − 1 = 84**, so every missing pass is an accounted-for platform skip rather
than a collection failure.

**WINDOWS IS STILL INVISIBLE TO ORDINARY CI, AND THIS DOES NOT CHANGE.** It is in the matrix for
`schedule` **and `workflow_dispatch`** only (`ci.yml`'s `os:` expression is the authority) — a green
27-job CI on a `main` push says **nothing** about Windows, and a PR cannot show it either.
**Validate any Windows-touching fix with `gh workflow run ci.yml --ref <branch>` before merging.**
Read the nightly with `gh run list --branch main --json event,conclusion` filtered to
`event=="schedule"`; `--limit 1` shows the newest run of EITHER kind, which is how a red nightly
reads as green.

| Item | Detail | Owner |
|---|---|---|
| **boardwatch sees 16.4% of job-apps' eligible yield — RE-DERIVED 2026-08-30, and the METHOD was wrong before** | **45 of 275 (16.4%)**, cohorts 08-23..08-29, on the **379-board fleet**. This replaces "10.1%, owed a check". It decomposes: fleet growth 344->379 gave 10.1 -> **13.8%**; adding an **exact ATS-slug key** alongside name matching gave 13.8 -> **16.4%**. **Name-only matching undercounts, so 7.7% and 10.1% are FLOORS** — boardwatch stores Micron as `Micron TDIT`, so the old method scored a watched company as unwatched; same for HPE/`Hewlett Packard Enterprise`, Cox/`Cox Automotive`, Disney/`Walt Disney Company`, Toyota, VIAVI. **The unreached 230 split: aggregator-only 60.7%, unsupported employer host 21.1%, board-addable just 1.8%** (5 postings in 7 days, 4 of them SmartRecruiters — the class D-370 declined on measured cost), so the cheap remainder is ONE Workday board (Motorola Solutions). **The gap is lanes, not boards.** Script: `.agent/2026-08-30-session/reach_v2.py`. Amazon/TikTok/Apple/ByteDance use none of the 6 ATS, so a slug cannot reach them. Closing it means a new discovery lane — GitHub new-grad lists are 19.1% of yield for ~5 public-repo GETs and are NOT the ToS trap the v2 decision was written about. **Reopens D-008** | **Mit** (reverses a shipped decision) |
| **Citi sits at 13.1% coverage, permanently** | Workday's `total` censors at 2,000; the facet sum (uncapped, control-verified) says 4,589. Our pager wraps at ~2,000 too, so post-drain Citi holds ~2,214 of 4,589 and nothing reports it | **Mit** (input-side) |
| **Run 9 (2026-09-06) tick-fired CLEAN on the restored five-lane config (D-487, read D-489); run 10 is the first whose funnel can reconcile a split slate (T60)** | The launchd job invokes the **editable** venv at `boardwatch/.venv/bin/boardwatch`, so whatever branch that tree is parked on IS the unattended run's code and `rules.yaml`. **Park the primary checkout on `main` before ending every session**; a stray branch changes EVERY subsequent run. The tick fired 06:00 CDT until the 09-09 reboot and **04:00 CDT since** — launchd keeps its boot zone, and the plist's hour is 4. Verify a tick by `runs = N` in `launchctl print` and the log mtime, never by the run row alone: a hand run proves the code, only a tick proves the plist | **Mit** (reboot); every session (discipline) |
