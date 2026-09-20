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
> blocks), **on 2026-09-12** (the four settled 2026-09-06 session blocks), **on 2026-09-12b** (the 2026-09-07 early and mid blocks) **on 2026-09-13c** (the 2026-09-07 review block and the whole 2026-09-12 session) and **on 2026-09-14** (run 57's block, superseded twice) **and on 2026-09-16** (the 2026-09-14b → 09-15 block, condensed to its decision pointers) **and on 2026-09-17** (the 2026-09-16 block, the same way) **and on 2026-09-18** (both 2026-09-17 blocks, condensed to their decision pointers) **and on 2026-09-19e** (the five settled 2026-09-14b … 2026-09-18 blocks moved WHOLE, and 2026-09-19c condensed to its pointer — 324 → 273 lines) **and on 2026-09-20** (the 2026-09-19e block moved WHOLE, condensed to its pointer) **and on 2026-09-20c** (the 2026-09-20b astra-04 block condensed to its pointer, 46 lines → 1). Nothing was deleted on any of the twelve passes. **309 is still over the bar, deliberately:** what remains above it is run 467's 92-line block and this session's own, both CURRENT standing rather than settled history. **Run 467's is now HALF discharged and still not movable** — D-527 declares Gate 1 MET as recorded, but B8's volume reading is explicitly HELD OPEN by the same ruling, and its own condition requires both. Do not narrate a decision here that
> `DECISIONS.md` already holds — cite its number instead. **If this file passes ~250 lines again, the
> fix is to move settled blocks out, not to summarise them away.**

---

## Current standing

### 2026-09-20c — **ASTRA REVIEW 05 IS CONSUMED (D-527): ALL SEVEN FINDINGS CONFIRMED, THE RANKING INVERTS FOR THE THIRD REVIEW RUNNING, AND FOUR OWNER RULINGS LAND. T140–T143 SHIPPED AND **MERGED TO `main`** (PR #396, 26/26 CI checks). T144–T148 TICKETED in `TICKETS-2026-09-20-ASTRA-05.md`. NOTHING HERE TOUCHES THE ENGINE — no re-key, no drain, no confirm-clock restart.**

Every `file:symbol` opened by a read-only Opus verifier on the seat (`.agent/astra/verify/05-report.md`,
**70 turns, $5.19**). Nothing refuted. Astra supplied no falsifier for this slice, so the findings
rest on their cited symbols plus this session's live measurement. **One cited symbol does not exist
anywhere** — F2's `death_probe._population_predicate`; the real one is `unreachable_by_the_scanner`
(`death_probe.py:265`). **Seat spend $25.83 over five dispatches.**

**The ranking inverts AGAIN.** Astra's flagship `wrong-now` (**F3**, the hiring.cafe all-late
discard) has **ZERO** live population — 0 of 468 runs, and the only hiringcafe lane failure ever
recorded is run 57's all-EMPTY branch. Meanwhile **F1, filed `improvement`, is the one actively
refilling: 120 boards on a parseable provider sit `watched=0`, and 12 arrived in the two ticks
since the import closed.** F6 is **249 of 449 grnh.se seeds** unreachable at the default; **F7 is
214 of 1,342 admissions (15.9%) across 27 of 27 funnels.**

**F7 IMPEACHES A NUMBER THE PROGRAM ALREADY USED.** `funnel-467.md` — cited in D-522 §6 — prints
*"19 new companies admitted"* under a note claiming `admitted` is "the reach this run ADDED", and
**7** of the 19 exist as rows. The cap approves BEFORE bodies are fetched. Controls: 1,128/1,342
lookups resolve; 0 of 27 funnels overcounts the other way.

**FOUR OWNER RULINGS (Mit, 2026-09-20), all priced first.** (1) **The promotion gap: CENSUS +
AUTO-WATCH — this REVERSES D-521/D-522's stage-2/3 refusal for this one case.** (2) **Scheduler:
DO NOT BUILD** — scan runtime is not a product constraint. (3) **Pizza board: LEAVE IT** — company
139 is already `watched=0`; its 801 open rows are 0.31% of the corpus and can never close (D-314).
(4) **GATE 1 MET as recorded, B8 HELD OPEN** — M4's last condition discharged; no retirement today.

**THE RULING REACHES 51 OF THE 120, AND ONLY REVIEWING THE DIFF SHOWED IT.** T143's gate draws
`board` from `_body_inlined_providers()` = `build_providers()` filtered to `_BodyInlinedProvider`
— **ashby, greenhouse, lever, workable and nothing else.** The other **69** (workday 44,
eightfold 9, oraclehcm 8, smartrecruiters 8) come only through T142's census under human import.
**The ongoing leak IS closed:** all 12 arrivals since the import were on those four providers. The
69 are a standing backlog, not a leak. Fleet **1,807 → ~1,858** at ~3.2s/board/run.

**That gate is safe for a specific reason:** `scan/coordinator.py:402` appends `unknown provider`
for a watched row outside `build_providers()`, so T143 relies on the SAME dict rather than a second
catalog free to drift from the error site it exists to prevent. Its third condition is
`if postings:` — a board that resolved but served nothing is not proven live.

**THE VERIFIER FOUND A THIRD F7 CALL SITE ASTRA MISSED** — `lanes/jsonld.py:772`. T140's fix landed
in `_apply_lane`, which `_apply_lanes:831` calls for every lane, **so jsonld is covered by
construction — verified at review, not assumed.** It also narrowed F3 (any page-0 failure suppresses
the raise) and found that **`lanes/indeed.py:871-897` is the identical branch, with
`tests/unit/test_indeed_lane.py:1422` ASSERTING the discard** — which bounds T144.

**TWO EXECUTOR JUDGMENT CALLS ACCEPTED, BOTH BETTER THAN THE TICKET.** T141 **declined the resume
cursor the ticket offered**: the command writes nothing, so a resume token lives only in the
operator's hands and a shifted `(attempts, id)` order silently skips a batch — the failure class
the ticket exists to close. T142's **mutation #2 initially did NOT fire, and that found a real
defect** — a self-matching `superseded` EXISTS made `watched IS FALSE` redundant; fixed with
`peer.c.id != companies.c.id`. T142 also round-tripped its output through the importer's own
validator and **it FAILED**: a lane-written Workday slug the parser refuses would abort an entire
import file, so refused rows go to an `UNIMPORTABLE` block with the parser's verbatim reason.

**B8's volume could NOT be re-derived from the store** — `job_dispositions` holds only `built`
(1,007) and `seen` (219), and `built` is **40 on every run**: the `--top 40` slate cap, not
apply-lane volume. The recorded 9-of-14 stands, which is why Q1 was put rather than answered.

**Gate: `make check` exit 0, 10,542 passed (baseline 10,498), coverage 95.24%, 8m13s — run on the
integrated branch AND again on the merge commit. CI: all 26 checks passed; PR #396 merged at
`836025b8`. The wave is on `main`, not parked.**

**`store/queries.py:619 upsert_watched_company` has ZERO callers anywhere** — a dead wrapper, left
in place and ticketed (T148) rather than removed inside four other diffs.

### 2026-09-20b — astra review 04 (the runner, the store, concurrency) consumed: all ten findings confirmed, the ranking inverted under measurement, and the verifier found a wrong-now bug astra had filed as SOUND. T129/T130/T132 shipped in one gated wave; T131 and T133–T139 ticketed. Two owner questions ruled, both priced first. **Held WHOLE in D-526 and `TICKETS-2026-09-20-ASTRA-04.md`; do not re-derive.** Its live residual is T139's `RUN_CONTRACT.md` drift (the table lists **five** fatal conditions, the code has **13**, and it says `except Exception` where the code catches `BaseException`) and one recorded unpinned assumption: `_finish_run_with_one_retry`'s docstring claims the attempt that raised committed nothing, but the test's fake raises before calling through, so the commit-then-raise path is untested.

### 2026-09-20 — astra review 03 (identity, liveness, ledger, dedup, queue) consumed: all seven findings confirmed, T114–T119 shipped in two gated waves and **merged to `main`**, T120–T128 ticketed, one owner ruling. **The follow-up docs PR left on auto-merge DID land — verified here, PRs #394 and #395 both MERGED; that check is discharged, do not re-run it.** **Held WHOLE in D-525 and `TICKETS-2026-09-20-ASTRA-03.md`; do not re-derive.** Its live residual is F6's **16,510 open postings (6.3%) under 8 boards that have never scanned `complete`** — T122 corrects `_status`'s `watched` column, and T123 builds on that argument, not on "expand sweep selection".

### 2026-09-19e — astra review 02 (the apply-lane stack) consumed: all eight findings confirmed, T106–T109 and T112 shipped, T110/T111/T113 ticketed, three owner questions ruled. **Held WHOLE in D-524 and `TICKETS-2026-09-19-ASTRA-02.md`; do not re-derive.** Its live residual is next action 4's one-time re-judge (with T108 folded in) and T113's 97 uncovered delivered versions. `main`'s four-commit CI red — two `web/` tests pinning a literal future date, reproducible only under `TZ=UTC` — was fixed there and is unrelated to the review.

### 2026-09-19c — astra review 01 (the deterministic eligibility engine) consumed: all ten findings confirmed, T98 and T99 shipped, T100–T105 ticketed. **Held WHOLE in D-523 and `TICKETS-2026-09-19-ASTRA-01.md`; do not re-derive.** Its live residual is in next action 4: **the first armed run after T99 (and now T108) re-judges the delivered slate ONCE** (≤ `--top`, ~3 batches on the 04:00 tick) — read the funnel's gate block on that run, not just the verdicts.

### 2026-09-19b — **AN EXTERNAL DESIGN REVIEW IS COMMISSIONED. Five prompts for GPT astra sit in `.agent/astra/prompts/` (gitignored); the owner runs each in its own astra session and brings the findings file back to a NEW boardwatch session, one review per session.** No run was read, no code changed, no metric moved.

The slices, in the order to consume them: **01** the deterministic eligibility engine; **02** the
apply-lane stack (rank gates → judge → `review_gate` → B8); **03** identity, liveness, the ledger,
dedup and the on-disk queue; **04** `run_pipeline`, the coordinator, the WAL/`BEGIN` model and the
run contract; **05** discovery strategy (optional). `.agent/astra/README.md` is the index. Astra
writes `.agent/astra/findings/<NN>-<slice>.md` under a fixed schema (verdict → ranked findings
with `file:symbol` evidence, proposal, what it re-keys, falsifier, confidence → checked-and-sound →
owner questions → not read).

**How a session consumes one.** A finding is a POINTER, not proof: re-verify every cited symbol
against the code, run the stated falsifier, and only then ticket it. Anything that touches a
digested engine module re-keys the ledger and restarts the confirm window — say so in the ticket.
Anything astra proposes inside the refused scope (automation, evasion, re-opening a cited ruling
without new evidence) is dropped with one line, not argued. The prompts ask astra to cite the
`D-nnn` it disagrees with, so a disagreement is a review item for the owner, not a re-litigation.

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

0. **Consume astra reviews 03 → 04 (05 if it exists) as they arrive** — one findings file per
   session, the way 01 and 02 were: probes re-run here, symbols verified on the seat, then
   ticketed. **From review 01: T98 and T99 shipped; T100–T104 join item 4's batch; T105 needs a
   design. From review 02 (D-524): T106, T107, T108, T109 and T112 ALL SHIPPED; T110, T111 and
   T113 ticketed.** Mit's standing answer on the seat (2026-09-19 18:40): fan out
   **2–3 executors at once, never more**; ask for the usage reading again before a fan-out on a
   later day.
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
   reached NEW leads only and left every standing verdict on the old judge. The first armed run
   after T99+T108 re-judges the delivered slate ONCE (≤ `--top`) and comes back keyed on facts
   AND model — read the funnel's gate block on that run, not just the verdicts.
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

**THE SCHEDULED (WINDOWS) BUILD HAS BEEN RED FOR FOUR CONSECUTIVE NIGHTS AND NOBODY OWNS IT —
found 2026-09-19, NOT caused by that session's work.** Last green scheduled run **2026-09-15
(`2b980ebb`)**; red on 09-16 `70b99689`, 09-17 `1882e198`, 09-18 `15531462`, 09-19 `a2366bbf`.
**Every PUSH ci run in that window is GREEN** — Windows runs ONLY on the schedule, which is why
this is structurally invisible to a PR and to `make check` on macOS. Three failures, all
Windows-only:

- `tests/unit/test_web_server.py::test_local_today_is_the_servers_own_zone_and_never_utc` —
  **`AttributeError: module 'time' has no attribute 'tzset'`** at lines 2918 and 2928.
  `time.tzset()` is Unix-only and does not exist on Windows. Introduced by **`3652f583`
  (2026-09-17, "Pin a follow-up date to a lead")** — three days before it was noticed.
- `tests/pipeline/test_gate_stage.py::test_gate_rejudges_a_lead_whose_only_gate_row_is_a_superseded_policy`
  — `assert fake_claude.exists()` fails; the D-511/D-512 superseded-policy path.

**Attribution checked, not assumed:** the breakage predates 2026-09-19's commits by three days and
none of them touch those files. Read it with `gh run list --branch main --json event,conclusion`
and filter `event=="schedule"` — `--limit 1` shows the newest run of EITHER kind and will report
whichever landed last, which is how a red nightly reads as green.

| Item | Detail | Owner |
|---|---|---|
| **boardwatch sees 16.4% of job-apps' eligible yield — RE-DERIVED 2026-08-30, and the METHOD was wrong before** | **45 of 275 (16.4%)**, cohorts 08-23..08-29, on the **379-board fleet**. This replaces "10.1%, owed a check". It decomposes: fleet growth 344->379 gave 10.1 -> **13.8%**; adding an **exact ATS-slug key** alongside name matching gave 13.8 -> **16.4%**. **Name-only matching undercounts, so 7.7% and 10.1% are FLOORS** — boardwatch stores Micron as `Micron TDIT`, so the old method scored a watched company as unwatched; same for HPE/`Hewlett Packard Enterprise`, Cox/`Cox Automotive`, Disney/`Walt Disney Company`, Toyota, VIAVI. **The unreached 230 split: aggregator-only 60.7%, unsupported employer host 21.1%, board-addable just 1.8%** (5 postings in 7 days, 4 of them SmartRecruiters — the class D-370 declined on measured cost), so the cheap remainder is ONE Workday board (Motorola Solutions). **The gap is lanes, not boards.** Script: `.agent/2026-08-30-session/reach_v2.py`. Amazon/TikTok/Apple/ByteDance use none of the 6 ATS, so a slug cannot reach them. Closing it means a new discovery lane — GitHub new-grad lists are 19.1% of yield for ~5 public-repo GETs and are NOT the ToS trap the v2 decision was written about. **Reopens D-008** | **Mit** (reverses a shipped decision) |
| **Citi sits at 13.1% coverage, permanently** | Workday's `total` censors at 2,000; the facet sum (uncapped, control-verified) says 4,589. Our pager wraps at ~2,000 too, so post-drain Citi holds ~2,214 of 4,589 and nothing reports it | **Mit** (input-side) |
| **Run 9 (2026-09-06) tick-fired CLEAN on the restored five-lane config (D-487, read D-489); run 10 is the first whose funnel can reconcile a split slate (T60)** | The launchd job invokes the **editable** venv at `boardwatch/.venv/bin/boardwatch`, so whatever branch that tree is parked on IS the unattended run's code and `rules.yaml`. **Park the primary checkout on `main` before ending every session**; a stray branch changes EVERY subsequent run. The tick fired 06:00 CDT until the 09-09 reboot and **04:00 CDT since** — launchd keeps its boot zone, and the plist's hour is 4. Verify a tick by `runs = N` in `launchctl print` and the log mtime, never by the run row alone: a hand run proves the code, only a tick proves the plist | **Mit** (reboot); every session (discipline) |
