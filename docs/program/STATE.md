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
> moved the 2026-09-22d block WHOLE once its run-471 expectation was restated above. (2026-09-22f moved
> nothing: every block above still waits on run 471, which is why the file is ~30 lines over; the 22c
> and 22e blocks move WHOLE once runs 471 and 472 are read.) **Nothing has
> been deleted on any pass.** Do not narrate a decision here that `DECISIONS.md` already holds — cite its number
> instead. **If this file passes ~250 lines again, the
> fix is to move settled blocks out, not to summarise them away.**

---

## Current standing

### 2026-09-22f — **T135 SHIPS (#418 → `04f9ba6d`, D-559). T144 AND T133 ARE BUILT AND REVIEWED ON A STACK, NOT MERGED; T125 (ANNOTATE) IS BUILT, UNREVIEWED. T123 AND T124 CLOSE ON MEASUREMENT (D-558). RUN 471 HAS NOT FIRED; THE PRIMARY CHECKOUT IS STILL HELD ON `ccb52912`.**

The session ran 21:10–22:25 CDT on 09-22, before the 04:00 tick. The owner checkpointed at 21:58
("don't fire anything new"), and every in-flight task finished before this was written.

**Next session, in order** (exact commands: `.agent/2026-09-22f-session/CHECKPOINT.md`):
1. **Read run 471** exactly as the 2026-09-22e block below says.
2. **Pull ONLY to `de7ae153`** (`git -C boardwatch merge --ff-only de7ae153`), NOT to `main`. `main`
   now also carries T135, and the owner ruled that shipped fixes reach the live run at **473**, so 472
   stays a clean read of the batch's re-key (D-557). Pull to `main` only after 472 is read.
3. **Ship the stack, one gate at a time.** Each branch sits on the one before, and each code delta
   is patch-id-equal to what was reviewed.
   - **T144** (`bw-t156`, `exec-t144` @ `e5969050`, stacked on T135's gated tree, which is
     byte-identical to `04f9ba6d`). The stacked gate was EXIT=0 with 10,835 passed; Codex found no
     blocker. Rebase onto `origin/main` (a no-op in tree), prove the diff empty, push, open a PR
     (`pr-t144.md`), arm auto-merge.
   - **T133** (`bw-t152`, `exec-t133` @ `29aebdae`, stacked on T144). Codex found no blocker, and
     its one follow-up is fixed and proven red on the old source. **Not yet gated.** It changes one
     thing an operator will see: a tick that fires while another run is finalizing now exits 2, and
     the D-260 heartbeat catches it.
   - **T125 (annotate)** (`bw-t105`, `exec-t125` @ `99640f24`) is **unreviewed**. Before its gate,
     run `make web` and commit `src/boardwatch/web/static/` and `web/bundle-inputs.sha256`. **The
     bundle IS tracked**; the handoff wrongly said otherwise (D-561).
4. **Then one executor at a time:** T137 → T138 (the per-kind half only) → T139 (the stage
   extraction only, since its doc half was done in D-528). The handoffs are in `.agent/executor/`.
5. **Owner reads owed:** `DESIGN-T161-gate-verdict-identity.md`, which recommends BOTH halves.
   **T163 must follow T161**: it edits `detect.py`, a digested module, so it re-keys and would dip
   the lane again.

**Ruled this session (D-557):**
- The seat is under 30%, so executors run one at a time. **The planning session IS the enterprise
  seat**, and it shares that budget with its executors.
- T161 stays in its slot.
- T162 is parked until a switch of judge model or effort is planned.
- T125 is annotate-only.
- T138's reverse half is refused.

**Closed on measurement (D-558):**
- **T124:** 409 of 409 multi-posting jobs are justified and 0 have diverged (null-controlled).
- **T123:** in runs 468–470, 1 of 110 partial board scans was detail-only. The 16,869 postings on
  boards that never complete are **inventory-truncated** on 4 boards: Lowe's 150-page cap, the
  Abbott and Genpt 2,000 censor, and Oracle `eeho` at 2,199 of 2,218. That is a coverage question,
  not T123's.

**T161 measured** (its design note):
- Of the 970 standing leads, the live identity reads 833 gate verdicts (750 / 44 / 39). The
  post-batch identity reads **0**. T161's judge-input key reads the same 833.
- The freshness read is ALSO identity-scoped. A lane-only T161 therefore ends the dip but not the
  re-judge spend.

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

### 2026-09-22c — **RUN 470 READ: THE RE-KEY FIRED AS PREDICTED AND B8's VOLUME SITS ON THE BAR AT 20 (D-547). A RE-KEY ALSO DEMOTES — 237 LEADS 0-B HAD PROMOTED FELL OUT OF THE APPLY LANE, WHICH D-537 NEVER MEASURED. T153 EXECUTED ON THE OWNER'S RULING: THE JUDGE IS `sonnet`, THE STANDING QUEUE WAS RE-JUDGED ONCE (833 of 833) AND ITS APPLY LANE READS 529 (D-548). `gate.effort` SHIPS.**

**Run 470 (D-547).** 85m34s against 75–85. The re-key is verified in the store, not inferred from
the duration: **269,702** evaluations under the new identity (run 469: 1,524); the re-judge cost
+20.2 min, as predicted. The 34 s overshoot is a cost nobody budgeted: **a re-key also empties the
gate's cache** (0 cached vs 66; +8.0 min). **B8 volume: 20 against a bar of 20** — 25/22/26/20
post-expansion; D-529 is at n = 4 of 5.

**Read D-547 before predicting what any re-key costs the queue.** Dead gate rows cut BOTH ways:
D-537 counted the holds they release (101); they also kill every judge `eligible` that 0-B's
promotion needs, so **237** leads fell back to `no_requirements_found`/`experience_requirement`
(net **−136**, null-controlled 987 of 987). It started at the engine-batch merge and never
self-heals, because a `built` lead is never re-judged by the daily gate.

**The repair, ruled by the owner and done (D-548).** Live `config.toml` gate model `haiku` →
`sonnet`; the 833-lead standing queue re-judged once through the production `run_gate_stage` at
`--effort medium`, paced in owner-checked batches (seat 5% → 8% over the first 78 leads). **Apply
lane 283 → 529** (412 had the haiku readings survived); `no_requirements_found` 345 → 12. Sonnet
clears **25 of the 33** entry-titled leads haiku had called senior. **Sonnet's apply-lane
PRECISION is unmeasured — 529 is volume** — and Sonnet was the audit's independent arm, so the
next blind audit needs Opus.

**`gate.effort` ships** (`None` = the calibrated argv, no flag). The live config carries
`[gate] effort = "medium"`; `Settings` ignored it until the code merged, so it is verified by reading
it back AFTER the merge, never by the file. Known gap **T155**: effort is not in the gate's
freshness key, so a later change of level re-judges nothing already judged.

**Next reading: run 471**, day 1 of B8's fresh 14-day window (T153 is a change to eligibility under
`PROGRAM.md` §1). Read its `gate` block: the first daily gate on Sonnet, and the first whose
standing queue is fully current.

**NEXT WORK: superseded by the 2026-09-22e block above.** #1 (T159), #2 (T113) and the T127/T158
cleanups are done. `TICKETS-2026-09-22c.md` §0 still lists what is already measured: read it
before any probe.

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

### Astra reviews 01–05 — **CONSUMED AND CLOSED.** All five slices, 42 findings, nothing refuted. Held WHOLE in **D-523 … D-527** and the five `TICKETS-2026-09-*-ASTRA-0*.md` files; the remediation that followed is **D-528**. **Do not re-derive any of it.** Of T98–T148 (51 tickets), **33 shipped**; **T145/T146/T147 are not build work** (owner DO-NOT-BUILD, future-reading guidance, LinkedIn posture); **T100–T105 are held as ONE engine bump** with next action 4; and of what stayed open, **T113 and T127 shipped (22d), T135 shipped (22f), T123 and T124 closed on measurement (D-558), T125 was rebuilt as an annotation, T133 and T144 are built, and T138's reverse half is refused (D-557); T137, T138's per-kind half and T139's stage extraction stay open.**

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

## Open questions — Mit's, not to be resolved by fiat

**B8's RETIREMENT question is RULED and CLOSED (2026-09-21, D-534) — do not re-raise it.** The
9-of-14 volume record does not block: all 14 days are on the 652-board fleet, post-expansion
`pdf.entered` reads **25 / 22 / 26 (3 of 3, mean 24.3)**, and the engine batch's `rules_hash`
move restarts the 14-day confirm by `PROGRAM.md` §1's own rule anyway. **What is owed is B8's
volume half holding 14 days on the 1,807-board fleet, counted from run 471** — #407
restarted the window at run 470 and the T153 judge switch restarts it again (D-548). This is a
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
