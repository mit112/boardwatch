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
> blocks), **on 2026-09-12** (the four settled 2026-09-06 session blocks), **on 2026-09-12b** (the 2026-09-07 early and mid blocks) **on 2026-09-13c** (the 2026-09-07 review block and the whole 2026-09-12 session) and **on 2026-09-14** (run 57's block, superseded twice) **and on 2026-09-16** (the 2026-09-14b → 09-15 block, condensed to its decision pointers) **and on 2026-09-17** (the 2026-09-16 block, the same way) **and on 2026-09-18** (both 2026-09-17 blocks, condensed to their decision pointers) **and on 2026-09-19e** (the five settled 2026-09-14b … 2026-09-18 blocks moved WHOLE, and 2026-09-19c condensed to its pointer — 324 → 273 lines) **and on 2026-09-20** (the 2026-09-19e block moved WHOLE, condensed to its pointer) **and on 2026-09-20c** (the 2026-09-20b astra-04 block condensed to its pointer, 46 lines → 1) **and on 2026-09-20d** (ALL FIVE astra-consumption blocks condensed to ONE pointer now that D-528 closes the remediation, 313 → 267 lines). Nothing was deleted on any of the fourteen passes. **The file is now 327 lines and that is over the bar by more than the usual margin.** What holds it up is run 467's 92-line block plus the 2026-09-20d/e block; **the latter was MOVED WHOLE on 2026-09-20g** (43 lines → 1 pointer), which is the fourteenth such pass. **The next thing to move is run 467's 2026-09-19 block**: 2026-09-20g now carries the second reading that supersedes its expansion numbers, so only its B8 half is still live — but it is still NOT movable whole while D-527 holds that half open, and a session with the budget should split it rather than summarise it away. **Run 467's is still HALF discharged and still not movable** — D-527 declares Gate 1 MET as recorded, but B8's volume reading is explicitly HELD OPEN by the same ruling, and its own condition requires both. Do not narrate a decision here that
> `DECISIONS.md` already holds — cite its number instead. **If this file passes ~250 lines again, the
> fix is to move settled blocks out, not to summarise them away.**

---

## Current standing

### 2026-09-20g — **RUN 468 ANSWERS NEXT ACTION 1: the new boards' 2.05% RATE HOLDS EXACTLY, the VOLUME was a first-scan bulge (584x), and the 70%-of-slate share is now PURE BACKLOG DRAWDOWN — 25 of 25 new-board leads were first seen in run 467, ZERO in run 468. T104's DESIGN IS REFUTED AGAINST ITS OWN CASES (D-531); its mechanism ships UNUSED on `engine-batch`. `make check` IS BLOCKED BY MACHINE LOAD, NOT BY CODE.**

**Next action 1 is DISCHARGED. Both halves of the question were true at once.** Cohort = the 1,155
boards with `scan_kind='board'` in run 467 but not 447; it sizes to exactly 1,155 and the same
apparatus reproduces run 467's recorded **28 of 40** slate share, which is the null control.

| | run 467 | **run 468** |
|---|---:|---:|
| new-board **stock** open / eligible | 59,622 / 1,222 = **2.05%** | 59,618 / 1,219 = **2.04%** |
| new-board **flow** (`kind='new'`) / eligible | 56,635 / 1,159 = **2.05%** | 97 / 2 = **2.06%** |
| leads from the new boards | **28 of 40 (70%)** | **25 of 40 (62%)** |
| provenance of those leads | 27 first seen THAT run | **25 of 25 first seen run 467** |

**The rate generalises; the lead contribution does not, yet.** 28→25 is inside noise (z≈0.71), but
zero of run 468's own 97 fresh new-board postings produced a lead. Steady-state replenishment is
**~2 eligible/day** against a ~25/day draw, over **1,139 undrawn** eligible (of 1,219; only 80
carry a disposition). **Days-of-runway is UNSIZED and must not be quoted** — eligible is not
slate-reachable (8,518 eligible → 75 shortlisted → 40 delivered, `capped_by_top_n` 10,562). **A
third tick is what distinguishes decay from plateau.** Old boards read **3.69%**, denser per
posting than the new ones. Reconciles four ways against funnel-468's own stage counts.

**T104 IS REFUTED AS SPECIFIED (D-531) — do not build it from the ticket.** Regressions 8 and 9
both put the escape in the immediately following sentence, which is exactly what
`abstain_by_adjacent` is defined to see, so both keep reading `uncertain`; only sentence scope
reaches them, and sentence scope breaks the waiver control. They are **the same shape at the same
distance** — no distance-based reach separates them. Astra's own waiver example is a **vacuous**
control (it fires `master_required`, which the ticket never moves); re-positioned onto
`doctorate_required` it reverses. The ticket also names **2 of the 11** patterns holding those two
**shared YAML anchors**. A verified non-distance discriminator ("reach the next unit only if it
states no requirement of its own") satisfies **all six** cases and is held as a patch, NOT
committed — its failure direction is job-deleting and the live delta over the **67,587** movable
postings is unmeasured.

**MIT RULED (c) AND IT IS BUILT AT THE WIDER SCOPE.** `engine-batch` is PUSHED (no PR) and holds
the mechanism at `f0e5a009` plus the ownership-guarded reach with **all eleven** document-scoped
escapes moved. **`abstain_by` now has ZERO users**; the census pins the pair (`abstain_by: 0`,
`abstain_by_adjacent: 11`) so a future pattern taking the unbounded reach fails the gate.

**The scope was decided by measurement, and it inverts the risk framing.** Over the COMPLETE
67,587-posting movable population — completeness checked, `postings.body_text` is identical to the
current `posting_versions.body_text` for all 260,306 open rows — **adjALL is a strict superset of
adj2** (0 postings move under adj2 that do not under adjALL), and its extra **108** are **+91
`eligible` against +16 rejected**. adj2 would have been 209 rejections for 3 finds. Baseline
control: **67,400 of 67,446 re-evaluations match the LIVE stored verdict (99.93%)**. Three sampled
finds were each verified correct and each is adjALL-only. **Known residual, owned by T105 and NOT
to be folded into T104:** a bullet ladder (`261677`) whose bare-bachelor's arm clears now reads
`ineligible`.

**ONE golden re-baselined and it was pinning the bug** — `m0334`, where an escape on a *preferred*
PhD line was waiving a *required* master's. **F38's abstain-not-drop ruling is untouched** (m1063
pins a standalone waiver still abstaining); only its assumption about REACH moved, and
`rules.yaml`'s comment asserting document scope was corrected in the same change. Corpus 1,060 →
**1,064**; the `rules.yaml` pin was rewritten twice and the corpus pin once, each keyed on the
unique full old hash with the count asserted at **90** and one line changed.

**GATED: `make check` exit 0 on `c988383b`** — **10,625 passed**, 1 skipped, 4 xfailed, vitest
211/211, coverage **95.26%**, 11m28s on an idle machine. The same tree took **51m21s** under the
Dota-era load, which is the clearest measure of what that load was doing.

**Test-count delta, counted through a different path than the gate.** `main` collects 10,589,
`engine-batch` 10,630 — **+41**. Mine is **+9** (6 new test functions, 1 removed with the rename,
+4 corpus rows, verified by diffing `83c22796..c988383b`); the three prior batch commits are the
other **+32**. **That means the inherited figure is 4 low:** 2026-09-20f records `83c22796` at
10,612 passed, but working back from this measurement it was **10,616**. Small, but quote the
measured one.

**THE BATCH'S RE-KEY, WITH THE CONCRETE VALUES — owed at MERGE, not now.** Both keys have moved
off `main`, and D-528/D-530's whole point is that the batch pays for this **once**:

| | `main` | `engine-batch` |
|---|---|---|
| `engine_version` | `1+223421634827` | **`1+fcef17f526a3`** |
| `catalog.version` (drives `rules_hash`) | `f55a8b638aefdbdc…` | **`36d11ed322355a0b…`** |

So **every stored deterministic verdict is re-keyed on merge and a ledger drain is OWED** — see
`boardwatch ledger reopen --stale`. A drain reopens DISPOSITIONS, not verdicts, so it re-surfaces
already-built leads rather than changing any answer. **The confirm-clock restart is NOT a live cost
(D-351).** Do not merge without doing this, and do not do it before the batch is closed — T101,
T105, T92, `education_timing` and the Sonnet judge move would each re-key it again.

**`engine-batch` HAS NO CI.** `ci.yml` triggers `push` only on `branches: [main]`, so pushing a
branch fires nothing — the push bought off-machine backup, not a signal. **A `workflow_dispatch` is
the only CI this branch can get and the only way to see Windows, and it is OWED before merge.**

**The machine-load gate failure earlier in the session was environmental, and is recorded below
because it will recur.** It exited 2 at `web-test` before pytest ran. Three grounds it is environmental: the count varies (18, 6, 7 failures across runs);
it reproduces on `main`, whose tree is byte-identical to the last exit-0 gate (`git diff dcc594c7
21bb2403` empty); and the failures are `Test timed out in 5000ms`, not assertions. **Load average
13.23 on 10 cores, Dota 2 at 352% CPU.** Nothing was killed. Verified separately instead:
generalization OK, both indexes current, ruff, `mypy --strict` 365 files, and **1,668 eligibility
tests** including the 1,061-golden corpus. **THE GATE IS OWED ON AN IDLE MACHINE.**

**All three held items were RULED AND EXECUTED at session close.** `engine-batch` is pushed at
`c988383b`; the docs branch is **PR #401** with auto-merge armed; and **65 of 72 worktrees were
pruned** — every one clean AND fully merged into `origin/main`. **33 → 46 GiB free, 13 GB
reclaimed.** The seven kept are the primary checkout, `bw-engine` and `bw-docs20g` (both
unmerged), the three detached `bw-verify*`, and the dirty `bw-webaudit`. **Every branch survives**
(`t99`, `t122`, `astra05`, `close-2026-09-17` spot-checked), so any of them reverses with
`git worktree add`, and no `.git` lock was left behind. A `workflow_dispatch` was fired on the
final state — **run `35565660891`, IN FLIGHT at close.** **Read it by job NAME, never colour
(D-528's lesson), and confirm the Windows job actually RAN.** PR #400 merged as `21bb2403`; the
primary checkout is synced and still on `main`, so the 04:00 tick runs `main`.


### 2026-09-20f — **THE ENGINE BATCH IS OPEN ON AN UNMERGED BRANCH. `engine-batch` (worktree `bw-engine`) HOLDS T100, T102 AND T103, GATED exit 0 — 10,612 passed, 95.26%. IT IS DELIBERATELY NOT MERGED (D-530).**

**Read this before touching the engine.** Mit ruled on 2026-09-20e: build next action 4's batch,
**hold the merge until after the 04:00 tick** so the night runs the code the astra wave gated.
**The branch ACCUMULATES the batch** — landing three tickets now and the rest later costs ONE
`engine_version`/`rules_hash` re-key, not two. Continue ON `engine-batch`; do not open a second
branch, and do not merge until the batch is done. Its base `86d9b3e6` is in `origin/main`, so it
rebases cleanly. **The primary checkout stays on `main`** — the launchd driver runs its editable
venv, so a branch switch there changes what the tick executes.

**In: T100** (resolvers abstain on out-of-catalog choice values — the bug **inverts `unmet` to
`met`** on three of four fields), **T102** (`us_person_required`; stops calling refugee/asylee EAD
holders `unmet` on ITAR/EAR clauses they satisfy), **T103's unanimity half** (an all-`unmet` or
all-`met` exclusive group now decides instead of dissolving — Mit's 2026-09-19 ruling; it reads
`ineligible` on his own review-lane clearance holds). **T100 and T102 each move 0 of Mit's live
verdicts**; T103 is the live-moving one.

**T103's OTHER half — same-span subsumption — is REFUTED and NOT BUILT (D-530).** Its stated rule
("spans equal or nested") cannot reach its own case (real spans (0,38) vs (20,50), overlapping
but not nested); its headline example already resolves as same-`implies` corroboration; and
same-span mixed groups measure **0 across five profile shapes** over 8,000 postings, null-
controlled. **Do not re-raise it.** Corpus: 1,061 goldens pass, zero re-baselined.

**Still owed in the batch: T101, T105, T92, `education_timing`, the Sonnet judge move.**
**T104 is DONE (D-531).**
**`education_timing` ALREADY EXISTS as a family** in `rules.yaml` (`currently_enrolled`,
`graduation_yyyymm`) — re-read D-521 §8.5 against the catalog before building anything.

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

0. **ASTRA IS DONE — all five slices consumed AND the remediation closed (D-528).** 33 of 51
   tickets shipped. What is left is listed in the astra pointer block above; **T100–T105 are item
   4's batch and nothing else is owed to the reviews.** Mit's standing answer on the seat
   (2026-09-19 18:40, re-confirmed 2026-09-20): fan out **2–3 executors at once, never more**;
   ask for the usage reading again before a fan-out on a later day. **The pattern is proven** —
   three executors, zero merge conflicts, each gated by the dispatching session.
1. **DISCHARGED on run 468 (2026-09-20g block, D-531).** The rate HELD exactly (2.04% stock,
   2.06% flow); the volume WAS a first-scan bulge (56,635 → 97 new postings, 584x); the slate
   share held at 62% but is **pure drawdown** — 25 of 25 new-board leads were first seen in run
   467, zero in run 468. **What replaces it: read run 469 the same way.** Two readings cannot
   tell decay from plateau, and the ~2 eligible/day replenishment against a ~25/day draw is what
   the stage-2/3 argument now turns on. Same method: cohort by `scan_kind='board'` in 467 not
   447, and confirm it still reproduces run 467's 28 of 40 before reading anything new.
2. **Rule on Indeed** (above). If accepted, size it as a dead lane rather than fixing it.
3. **Rule on B8.** Its volume half now PASSES at 25, but it failed 9 of the 14 confirm days and
   `PROGRAM.md` §1's replacement table includes it while M5's exit criterion does not. Does the
   record block the retirement decision? **The 25 itself is now VERIFIED sound** — D-524 measured
   the one defect that could have inflated it (`pdf.entered` is counted before the form sweep
   re-routes) and it moved zero leads on run 467, with a null control proving the probe. So this
   is a question about the 9-of-14 RECORD, not about the instrument.
4. **The batched engine landing — OPEN AND UNDER WAY ON `engine-batch`, three tickets in
   (T100, T102, T103), gated exit 0, NOT merged. See the 2026-09-20f block above and D-530
   before doing anything here.** Still owed: T101, T105, T92, `education_timing`, and
   the Sonnet judge move (D-477, D-514). **T104 IS DONE (D-531).** Mit ruled (c), the
   ownership-guarded adjacent reach, and it shipped at the WIDER scope — all eleven
   document-scoped escapes moved, chosen because adjALL is a strict superset of adj2 whose
   extra 108 moves are +91 `eligible` against +16 rejected over the complete 67,587-posting
   population. **What T104 does NOT cover: bullet ladders — that residual is T105's.** The rest of this item is the original framing and
   still stands — the Sonnet judge move, T92, **and
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
6. **GAP C IS NOW SIZED (2026-09-20g), which was the thing missing from the ruling.** Its 43
   `grnh.se` boards priced at the live greenhouse density — **84.1 open postings per board**,
   measured over the 608 watched greenhouse boards holding 51,149 open postings — come to
   **~3,617 open postings**, and at the new boards' measured 2.05% rate **~74 eligible**. The
   scan cost is negligible: greenhouse fetch latency is **1.08 s/board** on run 468, so 43 boards
   is **~46 seconds** added to a 1,807-board run. For scale, stage 1 was 1,155 boards → 59,622
   postings → 1,222 eligible, so Gap C is ~6% of that yield for 3.7% of the boards. **Still the
   owner's call, but it is no longer unpriced.**
7. **The 801 Domino's rows are RULED: LEAVE THEM (D-527).** Company 139 is already `watched=0`,
   so astra's actual ask was already the state; the rows are 0.31% of the open corpus and can
   never close (D-314). Do not re-raise it. **Still open and unruled:** import Gap C's 43
   `grnh.se` boards — now reachable, since `discover-grnh --limit 0` reads all 449 seeds where the
   default read 200 (T141); the `--include-non-swe` / `--include-zero-signal` drains are inert at
   production N.
8. **LinkedIn is the untouched backlog** — still ~423 companies refused by its cap every run,
   while hiringcafe's admissions fell 78 → 19 and jobapps' to 0 as Gap A was absorbed.

**T96 and T97 are MERGED** (union gated before push: exit 0, 10,274 passed). Both were held off
`main` until run 467 was read so the expansion was measured as one variable.

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
