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
> nothing.) The nineteenth, **2026-09-23b**, moved the 2026-09-23, 2026-09-22f and 2026-09-22c blocks
> WHOLE once run 471 was read and the pull to `de7ae153` done; the 22e block stays until run 472 is read. **Nothing has
> been deleted on any pass.** Do not narrate a decision here that `DECISIONS.md` already holds — cite its number
> instead. **If this file passes ~250 lines again, the
> fix is to move settled blocks out, not to summarise them away.**

---

## Current standing

### 2026-09-23b — **THE STACK FINISHED MERGING (D-568) AND SEVEN MORE TICKETS SHIPPED: T165 #427, T166 #428, T164 #429, T161 #430, T163 #431, T169 #432, T168 #433 (D-569 … D-571). RUN 471 IS READ: B8 VOLUME 20, ON THE BAR (D-572). THE PRIMARY CHECKOUT IS ON `de7ae153`. T170 IS MEASURED AND AWAITS A RULING; T172 IS BUILT AND HELD (D-573).**

The session ran 01:47 to ~07:50 CDT on 09-23, on the enterprise seat; the owner was asleep for most of
it and ruled up front (D-566).

**Next session, in order:**
1. **Read run 472 (04:00 on 09-24) as the eligibility batch's re-key run**, exactly as the 2026-09-22e
   block below predicts: the standing apply lane dips 529 → ~206 and heals at 130/run, and
   `refresh_pending_after` falls run over run; the corpus re-judge costs ~+20 min and the gate cache
   re-send ~+8 min. Identify the run by `boards_attempted > 0`; read the store with Python
   `sqlite3` `?mode=ro` only. **Run no local `make check`, mutation campaign or heavy probe between
   04:00 and the run's end** (D-572: this session's gates slowed run 471's scan several-fold).
2. **Only after 472 is read and its process has exited: `git -C boardwatch merge --ff-only
   origin/main`.** Run 473 is then the first on T161, T163, T164, T166, T168 and T169. It re-keys
   `engine_version` (T163, T169) and is **T161's live proof**: `readings_absent` 0, and the standing
   apply lane returns to about its pre-472 level AT ONCE (T161 reads the D-548 verdicts again) with no
   dip across 473's own re-key. **The refresh keeps re-judging at 130/run anyway, and that is correct:**
   none of the 947 stored `sonnet` gate rows records an effort (all predate T155's field, measured
   read-only 2026-09-23), and T155 treats a missing level as a different one. Expect
   `refresh_pending_after` to fall by ~130 a run, and the daily gate to re-send its slate (low `cached`)
   until that drains. Also read the funnel's `identity_drift` (`[]` expected) and `provenance` (the
   checkout's commit), both from T137.
3. **B8's volume window:** 471 read 20. 472 and 473 each re-key, so the 14-day count restarts; its
   day 1 is run 473.
4. **Owner calls** (Owner-gated, below): T170's ruling, which rides 473's re-key only if it merges
   before step 2; T172's merge; T171 only if the queue list's latency matters.

**Measured this session (D-567, D-572):**
- **job-apps' daily discovery IS processed daily**: every passing record from 09-02 … 09-21 is in the
  store, `_eligibility_review` included (D-486/488/509 superseded D-423's one-off harvest).
- **Run 471's refresh read 130 / 3 / 3 / 0**, not the 130 / 0 / 0 / 0 expected, and legitimately:
  two bodies revised by the run itself and one legacy lead whose gate rows name no judge.

**Machine change (T167, owner's ruling):** the job-apps link refresher runs once, at 03:45, before the
04:00 run. The plist backup is `com.boardwatch.jobapps-links.plist.bak-20260923-pre0345`.

**Open tickets** (`TICKETS-2026-09-22c.md` §2026-09-23b): T170 (ruling owed), T172 (merge held),
T171, T162 (parked), T113b (only if a stale-`ineligible` backlog recurs; T161 narrowed it to effort
changes).

### 2026-09-23 — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-23b.** The six-ticket stack (D-562), which finished merging only by rebase (D-568). Its run-472 step is restated in the block above.

### 2026-09-22f — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-23b.** T135 shipped (D-559), T123/T124 closed on measurement (D-558), the D-557 rulings, T161 measured and now SHIPPED (D-569). Every step in it is done.

### 2026-09-22e — **THE ELIGIBILITY BATCH SHIPS AS ONE ENGINE BUMP (T105 + T156 + T157 + T152, T155 FOLDED IN; D-555): 2,771 OPEN VERDICTS MOVE, NET −2,199 `ineligible`. T160 SHIPS (D-553). D-529 IS RULED AND SHIPS (D-554). THE PRIMARY CHECKOUT IS HELD ON `ccb52912` FOR RUN 471.**

**Merged:** #414 (T160) → `609c099a`, #415 (the batch) → `8b46706f`, #416 (D-529) → `6146a41c`. Every
gate EXIT=0 was read from a sentinel: T160 10,712 passed; the batch 10,807 passed at 95.27%; D-529 on the
batch 10,807 passed.

**The primary checkout was deliberately NOT pulled** (owner's ruling). Run 471 (04:00 CDT 09-23)
runs on `ccb52912`, so it is a clean read of the T113 refresh with no re-key, and D-529's fifth
reading comes from the pre-merge code. **Next session, in order:**
1. **Read run 471 as the 2026-09-22c block below specifies.** Expect `gate.refresh_*` =
   130/0/0/0 (D-552). A non-zero candidate count with no re-key is a DEFECT.
2. **Then pull, but ONLY to `de7ae153` (#417), never to a later `main`** (the 2026-09-22f block,
   D-557). Run 472 becomes the batch's re-key run:
   - the corpus re-judge costs about +20 min and the gate cache re-send about +8 min, once;
   - B8's 14-day window restarts at 472.
3. **Watch runs 472–474.** The standing apply lane dips **529 → ~206** (D-556), then heals at
   130/run, promotable leads first. `refresh_pending_after` should fall run over run.

**What moved (D-555, measured).**
- 2,127 `ineligible` → `uncertain` and 240 → `eligible`. The big term is a years bar under a
  hedge heading; `Preferred Qualifications:` alone accounts for 1,047.
- 168 `uncertain` → `ineligible`, **correct**: a preferred-section straddle had masked a genuine
  basic bar.
- 111 `eligible` → `uncertain`: a met row under a hedge heading no longer counts.
- T152 keeps all 833 standing seniority readings through the re-key. **The drain is refused** a
  seventh time.

**Review discipline changed (owner, 2026-09-22e).** Codex ran 3 rounds on T160 and 5 on the batch.
The owner has now set a budget: **1 review + 1 verification**, and a third round only for a
genuine, reachable blocker. The model is `gpt-6-sol` (Codex CLI ≥ 0.156.0), with effort
`low`/`medium`/`high` only. Global CLAUDE.md "Codex reviews" holds the rule.

**NEXT WORK: superseded by the 2026-09-22f block above.** Wave A closed as T135 shipped, T144 built,
T123 and T124 closed on measurement (D-558); T125 was measured and rebuilt as an annotation.

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
4. **P2 item 8 — the onboarding field-taxonomy gatherer. DEFERRED by Mit 2026-08-28.** The last
   multi-tenancy gap of its kind; D-054 forbids us authoring non-tech field content.
5. **`add-evidence` takes no bundle lock** (D-143) — raise before two authoring agents run against
   one bundle.
6. **T170 — read a years bar its own sentence calls preferred as a preference** (`DESIGN-T170-sentence-final-hedge.md`,
   D-573): 266 verdicts leave `ineligible` (194 `uncertain`, 72 `eligible`), 16 of 20 movers read right.
   Rides run 473's re-key ONLY if merged before the post-472 pull. A second call inside it: hedged
   SCOPED bars (186 of the new `uncertain` movers would clear).
7. **T172's merge** (draft PR #434, gated EXIT=0 and reviewed): the SingleStore Helios folder lands in
   `_applied` with an id suffix; nothing else is renamed.

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
