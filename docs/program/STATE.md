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
> blocks), **on 2026-09-12** (the four settled 2026-09-06 session blocks), **on 2026-09-12b** (the 2026-09-07 early and mid blocks) **on 2026-09-13c** (the 2026-09-07 review block and the whole 2026-09-12 session) and **on 2026-09-14** (run 57's block, superseded twice) **and on 2026-09-16** (the 2026-09-14b → 09-15 block, condensed to its decision pointers) **and on 2026-09-17** (the 2026-09-16 block, the same way) **and on 2026-09-18** (both 2026-09-17 blocks, condensed to their decision pointers) **and on 2026-09-19e** (the five settled 2026-09-14b … 2026-09-18 blocks moved WHOLE, and 2026-09-19c condensed to its pointer — 324 → 273 lines) **and on 2026-09-20** (the 2026-09-19e block moved WHOLE, condensed to its pointer) **and on 2026-09-20c** (the 2026-09-20b astra-04 block condensed to its pointer, 46 lines → 1) **and on 2026-09-20d** (ALL FIVE astra-consumption blocks condensed to ONE pointer now that D-528 closes the remediation, 313 → 267 lines). Nothing was deleted on any of the thirteen passes. **The file is now 285 lines and that is over the bar by more than the usual margin.** What holds it up is run 467's 92-line block plus the 2026-09-20d/e block; **the latter is now SETTLED — the wave is merged and held in D-528 — and is the next thing to move WHOLE**, which a session with the budget should do rather than summarising it away. It was left in place on 2026-09-20e deliberately: that session's owner questions went unanswered, and condensing a block while its open items are still being put to Mit risks dropping one. **Run 467's is still HALF discharged and still not movable** — D-527 declares Gate 1 MET as recorded, but B8's volume reading is explicitly HELD OPEN by the same ruling, and its own condition requires both. Do not narrate a decision here that
> `DECISIONS.md` already holds — cite its number instead. **If this file passes ~250 lines again, the
> fix is to move settled blocks out, not to summarise them away.**

---

## Current standing

### 2026-09-20d/e — **THE ASTRA REMEDIATION BACKLOG IS CLOSED TO THIRTEEN TICKETS IN ONE GATED WAVE, AND IT IS MERGED (D-528, PR #398 → `09df0e87`). WINDOWS IS GREEN AND THE FIVE-NIGHT RED IS OVER. THE ENGINE BATCH IS THE ONLY DEFERRAL. NOTHING HERE RE-KEYS — no drain, no confirm-clock restart.**

**The gate, on the commit that actually merged.** `make check` exit 0 on **`82ad88da`** — 10,584 passed (baseline 10,542), 1 skipped, 4 xfailed, coverage 95.25%, 9m16s, all six targets present. The earlier reading was on `42bc2696`, one commit short of HEAD; the gap was four program docs plus one line in `tests/unit/test_delivery_queries.py`. **After the merge, `git diff 82ad88da HEAD` is empty** — the merge tree is byte-identical, so this reading is valid for `09df0e87` and the 04:00 tick runs exactly the gated code.

Shipped: **T110, T111, T120, T121, T122, T126, T128, T131, T134, T136, T138 (per-file half),
T139 (doc half), T148.** Five came from three enterprise-seat executors in their own worktrees
(`t122`, `t134`, `t110`), **each gated here, never by itself**; all three merged with zero
conflicts. **Held WHOLE in D-528; do not re-derive.**

**T128 WAS THE ONLY THING ACTUALLY BROKEN, AND IT WAS WORSE THAN RECORDED.** The scheduled build
was red **five** consecutive nights (09-16…09-20), not four. Three Windows-only failures, invisible
to every push CI because **Windows runs on `schedule`/`workflow_dispatch` ONLY**. Validated by an
explicit `workflow_dispatch` on the branch — the only way to see that matrix before merge.

**NEXT ACTION 4's ONE-TIME RE-JUDGE HAS FIRED AND IS CLEAN — it was recorded as owed and was
already discharged.** Run **468**: `funnel-468.md` reads `120 candidates · 0 already current ·
120 sent`, 0 failed open / 0 missing / 0 refused; the store independently shows run 468 = **120
rows `model='haiku'`** against `model=NULL` on 434/447/467. **T108 is discharged and PROVEN LIVE** —
the gate row varies with the model, so the Sonnet move reaches standing verdicts, not only new leads.

**THREE MEASUREMENTS CLOSED ITEMS WITHOUT CODE.** (1) **The composite-title asymmetry is REFUTED**
— astra's "only harmful" long-qualifier case reads `uncertain` (held for review), NOT `not_swe`;
of 26,830 open "software" titles the 563 reading `not_swe` are 540 non-engineering nouns plus 23
correct vetoes, so **genuinely-SWE titles hidden: 0 of 260,306**, null-controlled. **Do not rewrite
the parser.** (2) **T136's `ge=1` deliberately NOT changed** — 12 of 25 real runs exceed 60 min
(median 59.3, max 200.2) so a one-hour reaper would close a LIVE run, but a flat floor breaks
multi-tenancy. **The number is Mit's; the missing test shipped.** (3) **T122 re-measured after run
468 reproduces exactly** — 16,510 under 8 boards, 6.34%, partition-verified.

**T113 IS RE-SIZED BY AN ORDER OF MAGNITUDE.** The freshness test compares `model`, so every
pre-T108 row is stale: **1,203 of 1,323** posting-versions, not the ticket's **97**. And **the
re-judge is a ROLLING backlog** bounded by `gate.depth` per tick, not one run — true of the SLATE,
false of the stored corpus. **Do not quote the 97 again.**

**Two executor judgment calls accepted, both flagged by the executor.** T134 made a RAISED form
sweep escalate (right — a failed sweep means T91 hard-stop leads shipped UNHELD). T110 kept the B8
volume reading OFF `summary.errors`, so it reaches the funnel but not the escalation channel;
**that one is Mit's to reverse** and one line at the call site does it.

**The finalize-block order was CHECKED after the three-way merge** (D-374's marker had drifted and
was repaired): `form-sweep → funnel → queue → intake → scan → drought → lane-volume → liveness →
corpus → morning → heartbeat`. Nothing below `_emit_morning`; heartbeat last.

### Astra reviews 01–05 — **CONSUMED AND CLOSED.** All five slices, 42 findings, nothing refuted. Held WHOLE in **D-523 … D-527** and the five `TICKETS-2026-09-*-ASTRA-0*.md` files; the remediation that followed is **D-528**. **Do not re-derive any of it.** Of T98–T148 (51 tickets), **33 shipped**; **T145/T146/T147 are not build work** (owner DO-NOT-BUILD, future-reading guidance, LinkedIn posture); **T100–T105 are held as ONE engine bump** with next action 4; and **T113, T123, T124, T125, T127, T133, T135, T137, T139's stage extraction, T144 and T138's two remaining halves stay open.**

### 2026-09-19 — **THE EXPANSION IS MEASURED AND IT WORKS (run 467, D-522): 1,155 boards → 59,622 postings → 1,222 eligible → 28 of 40 DELIVERED LEADS, and B8's VOLUME half PASSES at 25. INDEED IS CONFIRMED DEAD. M5's 14th DAY TAKEN: run 447 is ATTENDED on the owner's explicit permission and B1–B7 PASS (D-521 §5). GATE 1's SECOND READING CLEARS ALL FOUR EMPLOYER-BOARD BARS, SO M4's LAST CONDITION IS DISCHARGED. THE DISCOVERY BACKLOG IS SIZED AT THREE DISJOINT GAPS AND STAGE 1 IS IMPORTED — FLEET 652 → 1,807.**

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

**RUN 467 — the first tick on 1,807 boards (readout in `METRICS.md`).** A REAL tick
(`launchctl runs = 9 → 10`); it is run **467**, not 448, because web renders consumed 446-466.
`ok`, **RECONCILES**, **manifest byte-identical to 447 and 434 on all five hashes** — the measured
proof that watching boards moves no hash. **65 min** on 2.8× the fleet. **1,155 of 1,155 new
boards scanned `complete`, zero failures added.** Corpus 208,847 → **261,626**; eligible verdicts
7,675 → **8,581**; **B8's volume half 19 → 25, MET** after failing 9 of 14 confirm days;
**28 of the 40 delivered leads came from the new boards.**

**THE SIZING RULE (D-522 §3), which inverts what was assumed:** a lane's secondhand sample of a
board is a **terrible** predictor of its SIZE (2.6 postings vs a real **51.6**, off 20×) and an
**excellent** predictor of its ELIGIBLE RATE (2.1% vs a measured **2.05%**). Size from fleet
density; predict yield from the sample. Never the reverse.

**INDEED IS CONFIRMED DEAD** — a second consecutive silent refusal (HTTP 200, valid GraphQL,
`results: []`, identical 68-byte body across three probe shapes including unfaceted-and-unfiltered).
**Evasion is REFUSED** (D-368 precedent). **Accepting the loss is Mit's**: ~500 postings/day,
~75 new companies/day, **37.1% of Gate 1 recall**. Note run 467 met B8 *with Indeed dead*.

**Next action.**

0. **ASTRA IS DONE — all five slices consumed AND the remediation closed (D-528).** 33 of 51
   tickets shipped. What is left is listed in the astra pointer block above; **T100–T105 are item
   4's batch and nothing else is owed to the reviews.** Mit's standing answer on the seat
   (2026-09-19 18:40, re-confirmed 2026-09-20): fan out **2–3 executors at once, never more**;
   ask for the usage reading again before a fan-out on a later day. **The pattern is proven** —
   three executors, zero merge conflicts, each gated by the dispatching session.
1. **Read the 04:00 tick by `boards_attempted > 0`, NEVER `max(runs.id)`.** Watch whether the
   new boards' 2.05% rate and 70%-of-slate share HOLD on a second run, or whether run 467 was a
   first-scan bulge — the whole stage-2/3 argument turns on that.
2. **Rule on Indeed** (above). If accepted, size it as a dead lane rather than fixing it.
3. **Rule on B8.** Its volume half now PASSES at 25, but it failed 9 of the 14 confirm days and
   `PROGRAM.md` §1's replacement table includes it while M5's exit criterion does not. Does the
   record block the retirement decision? **The 25 itself is now VERIFIED sound** — D-524 measured
   the one defect that could have inflated it (`pdf.entered` is counted before the form sweep
   re-routes) and it moved zero leads on run 467, with a null control proving the probe. So this
   is a question about the 9-of-14 RECORD, not about the instrument.
4. **The batched engine landing** — the Sonnet judge move (D-477, D-514), T92, **and
   `education_timing`** (D-521 §8.5: one nullable field, correctly rejects 7 unapplyable
   2027-start leads). **T108 (shipped, D-524) was its missing prerequisite**: until it landed,
   no component of the gate row key varied with `settings.gate.model`, so the move would have
   reached NEW leads only and left every standing verdict on the old judge. **THE RE-JUDGE HAS
   FIRED AND IS CLEAN — run 468, verified two ways (D-528). This condition is DISCHARGED; do not
   wait for it again.** `funnel-468.md` reads `120 candidates · 0 already current · 120 sent`,
   0 failed open / 0 missing / 0 refused, and the store shows run 468 = 120 rows `model='haiku'`
   against `model=NULL` on 434/447/467. **But note what it does NOT mean:** the SLATE was
   re-judged once; the stored corpus still holds **1,203 of 1,323** posting-versions on a stale
   key, and the judge clears at most `gate.depth` per tick. That backlog is T113's, re-sized.
5. **Stages 2-3 stay REFUSED for the density argument** (workday 0.17, smartrecruiters 0.08,
   oraclehcm **0.00** per 1k open) — but **D-527 REVERSES the refusal for ONE case**: a
   body-inlined board (ashby/greenhouse/lever/workable) that hiring.cafe resolved AND read is now
   auto-watched (T143). That is the inline-body population run 467's density win was measured on,
   and it is the only population the reversal covers. The **69** unwatched boards on
   workday/eightfold/oraclehcm/smartrecruiters are NOT reversed — they reach the fleet only
   through `companies unscanned` (T142) and the owner's `companies import`.
6. **The 801 Domino's rows are RULED: LEAVE THEM (D-527).** Company 139 is already `watched=0`,
   so astra's actual ask was already the state; the rows are 0.31% of the open corpus and can
   never close (D-314). Do not re-raise it. **Still open and unruled:** import Gap C's 43
   `grnh.se` boards — now reachable, since `discover-grnh --limit 0` reads all 449 seeds where the
   default read 200 (T141); the `--include-non-swe` / `--include-zero-signal` drains are inert at
   production N.
7. **LinkedIn is the untouched backlog** — still ~423 companies refused by its cap every run,
   while hiringcafe's admissions fell 78 → 19 and jobapps' to 0 as Gap A was absorbed.

**T96 and T97 are MERGED** (union gated before push: exit 0, 10,274 passed). Both were held off
`main` until run 467 was read so the expansion was measured as one variable.

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

**THE WINDOWS RED IS OVER — VERIFIED GREEN AND MERGED (2026-09-20e).** The scheduled build was
red five consecutive nights (09-16 … 09-20; last green 2026-09-15 `2b980ebb`). T128's three fixes
and the `%s` strftime fix both hold: `workflow_dispatch` **35549392270** on `astra-closeout` came
back **`success`, 30 of 31 jobs**, all three `windows-latest` jobs green, 1 correctly skipped
(`nightly-watch`, schedule-only). **PR #398 merged as `09df0e87`.** Numbers and the
reconciliation are in `METRICS.md` (session 2026-09-20e); the four failures themselves are history
and are held in D-528. **Tonight's nightly is expected green — confirm it, do not assume it.**

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
