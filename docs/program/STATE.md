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
> away** — fifteen passes so far, most recently **2026-09-21** (the 2026-09-20g, 2026-09-20f and
> 2026-09-19 blocks, 378 → 272 lines). **Nothing has been deleted on any pass.** Do not narrate a
> decision here that
> `DECISIONS.md` already holds — cite its number instead. **If this file passes ~250 lines again, the
> fix is to move settled blocks out, not to summarise them away.**

---

## Current standing

### 2026-09-21 — **THE ENGINE BATCH IS MERGED. RUN 469 SETTLES THE EXPANSION QUESTION AND IT INVERTS THE PROGRAM'S PRIORITY: THE BINDING CONSTRAINT IS THE SLATE CAP, NOT DISCOVERY (D-532). THE DRAIN IS MEASURED AND REFUSED (D-533). B8'S 9-OF-14 RECORD IS SUPERSEDED, NOT BLOCKING (D-534). THE NIGHTLY'S NEW WINDOWS RED IS A REAL PRODUCT GAP AND IS FIXED (D-535).**

**Read D-532 before proposing ANY discovery work.** Run 469 is the third tick on 1,807 boards
and the cohort read (null control passes: 1,155 boards, reproduces run 467's 28 of 40) gives:
new-board leads **28 → 25 → 5**, while the eligible RATE holds at **2.04%** across all three.
The mechanism is displacement, not exhaustion — only **75 of the cohort's 1,213 eligible have
ever been drawn (6.2%)**, and `capped_by_top_n` is **10,533** postings that cleared EVERY filter
and lost only on rank against a **40**-slot slate. The `--top 40` plist comment already named the
cause: **the ranker is recency-dominated and rank-cut postings are BURIED, not queued.**

**Consequence, and it is the session's main finding: anything sized in "eligible postings added"
is sized in the WRONG UNIT.** Stages 2–3 stay refused and are better evidenced than before.
**Gap C re-priced from "~74 eligible" to ~0.2 leads/day and was IMPORTED anyway** (29 of 37 boards, fleet 1,842 → 1,871; the 8 with zero swe-titled openings dropped) — cheap enough that the correction did not change the call. Precision work on the delivered 40
now pays better than discovery that adds to a pool already 263× the daily slate. **This is NOT a
decision to raise `--top`** — that trades against B8's precision half and is unmeasured.

**The batch merged with T100, T102, T103 and T104**, gated exit 0 on the merge commit (10,625
passed, 95.26%) with the code tree byte-identical to the Windows-green dispatch. **No drain**
(D-533): a two-arm blast radius over all 1,318 live-disposition postings found **1,316 unchanged,
1 loosening (on a self-draining `seen` row), 0 that a drain would buy.** The re-key still
re-judges the corpus at the next preflight — that is where T104's +91 `eligible` are released.

**B8 (D-534): the 9-of-14 record is retired, not weighed.** All 14 days are on the 652-board
fleet. Post-expansion `pdf.entered` reads **25 / 22 / 26 on runs 467/468/469 — 3 of 3, mean 24.3
against a bar of 20.** And the batch's `rules_hash` move **restarts the 14-day confirm by
`PROGRAM.md` §1's own rule**, so a fresh window begins at this merge regardless. **B8's PRECISION
half is the live risk and is where the work is.**

**The nightly was red on a NEW Windows failure and it was a real product gap (D-535).** Not
T128's three — those read zero. `promotion` commits by `os.replace`-ing `CURRENT`; that is atomic
on POSIX but on Windows denies every concurrent open for the instant of the swap, so the
lock-free reader saw **neither** revision — the third outcome §6 clause 1 says cannot happen.
The reader now waits it out, bounded at 1s, `PermissionError` only. **Only a Windows dispatch can
confirm the race is gone and ONE green run is not enough.**

**The 2026-09-17 autoapply pre-flight findings are now tracked and re-measured.** Its "single
largest fixable category" re-sizes: all five named dead postings have since CLOSED (2–4 days
later), so §8 is **closure LATENCY, not blindness**, and it is already instrumented by T117/T126
— do not re-ticket it. Population: 114 of 8,495 open+eligible carry `consecutive_missing ≥ 1`;
closure latency is mean **8.33 days**. **§5 (comp band as a seniority input) is the cheapest real
fix in the file** — `salary_min`/`salary_max` are already columns and the band gate already
exists; it is missing an input, not a subsystem.

### 2026-09-20g / 2026-09-20f / 2026-09-19 — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-21.**
Run 468's second reading (superseded by run 469, D-532); T104's refutation and rebuild (D-531, shipped);
the engine batch's opening (D-530 — it MERGED as `ea95c42c`); run 467, Gate 1's second reading clearing
all four employer-board bars, Indeed confirmed dead, and the stage-1 import that took the fleet 652 →
1,807 (D-521, D-522). **Do not re-derive any of it.** One correction carried forward: D-522 §3's sizing
rule (size from fleet density, predict yield from the sample) is **superseded by D-532** — both halves
are denominated in eligible postings, which is the wrong unit once the slate cap binds.

### 2026-09-20d/e — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-20g.** The astra remediation wave: thirteen tickets in one gated wave, merged (D-528, PR #398 → `09df0e87`); Windows green and the five-night red over; the composite-title asymmetry REFUTED; T136's `ge=1` deliberately unchanged; next action 4's one-time re-judge FIRED and CLEAN on run 468. **Held in D-528 — do not re-derive.**

### Astra reviews 01–05 — **CONSUMED AND CLOSED.** All five slices, 42 findings, nothing refuted. Held WHOLE in **D-523 … D-527** and the five `TICKETS-2026-09-*-ASTRA-0*.md` files; the remediation that followed is **D-528**. **Do not re-derive any of it.** Of T98–T148 (51 tickets), **33 shipped**; **T145/T146/T147 are not build work** (owner DO-NOT-BUILD, future-reading guidance, LinkedIn posture); **T100–T105 are held as ONE engine bump** with next action 4; and **T113, T123, T124, T125, T127, T133, T135, T137, T139's stage extraction, T144 and T138's two remaining halves stay open.**

### 2026-09-19 — **THE EXPANSION IS MEASURED AND IT WORKS (run 467, D-522): 1,155 boards → 59,622 postings → 1,222 eligible → 28 of 40 DELIVERED LEADS, and B8's VOLUME half PASSES at 25. INDEED IS CONFIRMED DEAD. M5's 14th DAY TAKEN: run 447 is ATTENDED on the owner's explicit permission and B1–B7 PASS (D-521 §5). GATE 1's SECOND READING CLEARS ALL FOUR EMPLOYER-BOARD BARS, SO M4's LAST CONDITION IS DISCHARGED. THE DISCOVERY BACKLOG IS SIZED AT THREE DISJOINT GAPS AND STAGE 1 IS IMPORTED — FLEET 652 → 1,807.**

**The expansion half is DISCHARGED and was split out to `STANDING-FACTS.md` on 2026-09-20g** — run 447, M5 day 14, Gate 1's reading of record, the three discovery gaps, run 467's readout and the sizing rule. Held in **D-521** and **D-522**; run **468** is the second reading and supersedes its numbers (2026-09-20g block). **The two paragraphs below stayed because both are still UNRULED.**

**B8's VOLUME half had never been recorded and fails 9 of the 14 confirm days** (7/13/10/12/3/10/9
then 26/22/26/19/21/19 against ≥ 20). The acceptance-run table in `METRICS.md` reads
`_(not started)_`, which is why nobody saw it; the instrument was validated against two recorded
values before this was believed. Its precision half stays MET at 6.9%/5.6% (D-514). **Whether a
9-of-14 volume record blocks the REPLACEMENT decision is Mit's — `PROGRAM.md` §1's table includes
B8, M5's exit criterion does not.** **POST-EXPANSION READING 2 OF THE 5 D-529 ASKS FOR, TAKEN
2026-09-20g: run 468 = 22, MET.** So the post-expansion record is **25, 22 — two for two**, against
a 9-of-14 record that is entirely pre-expansion. **Verified three ways on run 468** — the funnel's
`pdf` stage (22), its own Leads table (`PDF: yes` = 22) and **22 `.pdf` files on disk**; and the 44
PDFs under `2026-09-19/` decompose as **25 (run 467) + 19 (run 447)**, which independently confirms
both of those recorded values too. Three more ticks and the condition is satisfiable either way.

**INDEED IS CONFIRMED DEAD** — a second consecutive silent refusal (HTTP 200, valid GraphQL,
`results: []`, identical 68-byte body across three probe shapes including unfaceted-and-unfiltered).
**Evasion is REFUSED** (D-368 precedent). **Accepting the loss is Mit's**: ~500 postings/day,
~75 new companies/day, **37.1% of Gate 1 recall**. Note run 467 met B8 *with Indeed dead*.

**Next action.**

0. **ASTRA IS DONE and its engine batch is MERGED.** 37 of 51 tickets shipped (T100, T102, T103,
   T104 landed today as `ea95c42c`). Still open from the reviews: **T101, T105, T92,
   `education_timing`, the Sonnet judge move**, plus T113, T123, T124, T125, T127, T133, T135,
   T137, T139's stage extraction, T144 and T138's two remaining halves. Mit's standing answer on
   the seat: fan out **2–3 executors at once, never more**; ask for the usage reading again
   before a fan-out on a later day.
1. **READ THE UNIT BEFORE SIZING ANY DISCOVERY WORK (D-532).** This replaces the old
   "read the next tick" item, which is discharged — 28 → 25 → 5 across runs 467/468/469 settles
   it. The live question is no longer whether boards yield; it is that **`capped_by_top_n` is
   10,533 against a 40-slot slate**, so eligible-posting counts do not convert. Anything proposed
   in "eligible added" must be restated in slate slots or refused.
2. **THE HIGHEST-VALUE OPEN WORK IS B8's PRECISION HALF, NOT RECALL.** With the slate cap
   binding, every unapplyable lead removed is replaced from a 10,533-deep queue — so a precision
   fix converts one-for-one into an applyable lead. The 2026-09-17 autoapply pre-flight file
   (now tracked, re-measured 2026-09-21) is the ranked list. **Cheapest real fix: §5, comp band
   as an input to the seniority gate** — `salary_min`/`salary_max` are already columns and the
   gate already exists. **Do NOT re-ticket §8** (dead postings): it is closure LATENCY, already
   instrumented by T117/T126, and all five of its named postings have since closed.
3. **`--top` IS THE UNMEASURED LEVER AND IS NOT RULED.** Raising it converts buried postings into
   leads at unknown precision cost; B8's precision half is the instrument and it has never been
   read above n = 40/day. **Do not raise it without measuring leads 41–80 first.** Owner's call.
4. **Still owed in the engine line:** T101, T105 (bullet-ladder inheritance — T104's known
   residual, posting `261677`), T92, `education_timing` (D-521 §8.5 — **the family ALREADY
   EXISTS** in `rules.yaml` as `currently_enrolled`/`graduation_yyyymm`; re-read D-521 §8.5
   against the catalog before building), and **the Sonnet judge move** (D-477, D-514), whose
   prerequisite T108 is shipped and whose one-time re-judge fired clean on run 468. Each re-keys
   `engine_version`, so batch them on one branch again.
5. **Rule on Indeed** — deferred by Mit on 2026-09-21 to a later session. Second consecutive
   silent refusal; evasion refused (D-368). If accepted, size it as a dead lane rather than
   fixing it. Note run 467 met B8 with Indeed already dead.
6. **Stages 2–3 stay REFUSED and D-532 strengthens the refusal** (workday 0.17,
   smartrecruiters 0.08, oraclehcm **0.00** per 1k open). D-527's one reversal stands: a
   body-inlined board that hiring.cafe resolved AND read is auto-watched (T143). The **69**
   unwatched workday/eightfold/oraclehcm/smartrecruiters boards are NOT reversed.
7. **GAP C IS DONE (2026-09-21).** 449 seeds followed, 37 new boards found, all 37 probed live,
   **29 imported** and 8 dropped for carrying zero swe-titled openings. Fleet **1,842 → 1,871**.
   Measured at 1,319 open postings / 432 swe-titled / ~27 eligible — **not** the ~74 the
   extrapolation priced. The 801 Domino's rows stay (D-527); do not re-raise.
8. **LinkedIn is the untouched backlog** — ~423 companies refused by its cap every run. Size it
   in slate slots (D-532) before proposing work, not in companies reached.

### Owed, and specifically NOT done

- **NEW, found while pressure-testing T104 and NOT in T104's scope: the equivalence escape's
  VOCABULARY has a recall gap that deletes jobs.** `degree_equivalence` is
  `or\s+equivalent|equivalent\s+(?:experience|work)|in\s+lieu\s+of|may\s+be\s+substituted`, so
  **"An equivalent combination of education and experience is acceptable."** — a very common JD
  phrasing — matches NOTHING. `A PhD is required. An equivalent combination of education and
  experience is acceptable.` reads **`ineligible`** against a bachelor's, and it read that way on
  `main` BEFORE T104 as well: verified against the unmodified catalog, so this is a pre-existing
  vocabulary gap, not a reach bug and not a T104 regression. Five other waiver phrasings were
  checked and all hold. **NOW SIZED: 3,762 open postings** state an out-of-vocabulary waiver AND
  carry no in-vocabulary escape either, out of **141,756** that mention a degree (2.65%); a
  further 3,365 have both, so the catalog already sees those. **That 3,762 is a LOWER BOUND** —
  the probe searched phrasings chosen by hand (`equivalent combination`, `combination of education
  and experience`, `comparable experience`, `equivalent qualification/education/training/skills`,
  `experience in place of`), not an enumeration, so an unlisted phrasing is uncounted. Widening
  the escape moves verdicts toward `uncertain`, which is its own trade and needs its own ruling.
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

**B8's RETIREMENT question is RULED and CLOSED (2026-09-21, D-534) — do not re-raise it.** The
9-of-14 volume record does not block: all 14 days are on the 652-board fleet, post-expansion
`pdf.entered` reads **25 / 22 / 26 (3 of 3, mean 24.3)**, and the engine batch's `rules_hash`
move restarts the 14-day confirm by `PROGRAM.md` §1's own rule anyway. **What is owed is B8's
volume half holding 14 days on the 1,807-board fleet, counted from `ea95c42c`.** This is a
DIFFERENT question from item 0 below, which is about the alert CHANNEL.

0. **B8's volume reading on the escalation channel — RULED 2026-09-20e, held WHOLE in D-529.**
   Keep it OFF `summary.errors`; **no code change**, and `pipeline/runner.py:3083` plus its pinning
   test stand as T110 shipped them. **This is a deferral with a CONDITION, not a closed question:**
   the "near-daily noise" argument rests on 9 of 14 confirm days under the bar and **all 14 are
   pre-expansion**; run 467's **25** is the only reading on the 1,807-board fleet, so the firing
   rate now is unmeasured at n = 1. **Revisit at n ≥ 5 post-expansion readings.** Do not re-derive
   the argument — read D-529.

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
several nightlies before calling it closed.

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
