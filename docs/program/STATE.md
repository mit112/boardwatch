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
> blocks), **on 2026-09-12** (the four settled 2026-09-06 session blocks), **on 2026-09-12b** (the 2026-09-07 early and mid blocks) **on 2026-09-13c** (the 2026-09-07 review block and the whole 2026-09-12 session) and **on 2026-09-14** (run 57's block, superseded twice) **and on 2026-09-16** (the 2026-09-14b → 09-15 block, condensed to its decision pointers) **and on 2026-09-17** (the 2026-09-16 block, the same way) **and on 2026-09-18** (both 2026-09-17 blocks, condensed to their decision pointers) **and on 2026-09-19e** (the five settled 2026-09-14b … 2026-09-18 blocks moved WHOLE, and 2026-09-19c condensed to its pointer — 324 → 273 lines). Nothing was deleted on any of the ten passes. **273 is still over the bar, deliberately:** what remains above it is run 467's 92-line block, which is the CURRENT standing rather than settled history. Do not narrate a decision here that
> `DECISIONS.md` already holds — cite its number instead. **If this file passes ~250 lines again, the
> fix is to move settled blocks out, not to summarise them away.**

---

## Current standing

### 2026-09-19e — **ASTRA REVIEW 02 IS CONSUMED (D-524): ALL EIGHT FINDINGS CONFIRMED; T106, T107, T108, T109 AND T112 ALL SHIPPED; T110, T111 AND T113 TICKETED in `TICKETS-2026-09-19-ASTRA-02.md`. THREE OWNER QUESTIONS RULED. NOTHING HERE TOUCHES THE ENGINE — no ledger re-key, no drain, no confirm-clock restart. `main`'s FOUR-COMMIT CI RED IS FIXED and unrelated to the review.**

Both falsifiers re-run here (every row of five tables reproduces); every cited `file:symbol` opened
by a read-only Opus verifier on the seat (`.agent/astra/verify/02-report.md`, $3.56). **The apply
lane's defect is that its CONSUMERS do not honour the distinctions the stack draws:** the gate judge
does not fail open at three seams it claims to (F2, **fixed: T106**); a PARTIAL judge outage is
neither counted nor escalated — run 467 carried one (F4, **fixed: T107**); the gate row key does not vary
with the judge MODEL, so the pending model move would reach new leads only (F1, **fixed: T108**);
four standing call sites drop the title-seniority hold and none can see a judge NEGATIVE (F3, **fixed:
**T109**); three lexical spellings classify inconsistently (F5, **fixed: T112**); B8's instrument is
the pre-form-sweep render count (F6, **T110**) and a routing change moves no manifest hash (**T111**);
a stale gate negative suppresses its own repair and the one manual path reads through the same hide
(F1, **T113**).

**Measured here, read-only, each with a null control:**
- **B8's 25 on run 467 is NOT an overcount** — 0 of its 25 rendered leads match a form hard stop
  (7 have a fetched form at all); the same call over all 48 forms store-wide returns 3. **Rule
  next-action 3 on 25 as recorded.** T110 is still owed — the base rate is ~6% of fetched forms.
- **F3's judge-negative half is 12 leads today**: 45 delivered versions carry a current judge
  `ineligible`, 17 of those also carry a deterministic `eligible` (⇒ APPLY via row 9), 12 open and
  unapplied. D-511's 19, still live.
- **97 of 984 delivered posting-versions have no current-identity gate row at all** — size T113 there.
- **T112's level-separator fix has NO live population**: 1,010 → 1,011 matches over 261,626 open
  postings, and the one new match is a false positive the role gate already vetoes. Kept; never
  cite it as a win.

**Owner's three rulings (2026-09-19 ~22:35).** (1) A current judge `ineligible` **HOLDS a standing
lead in review** under its own reason — folded into T109. (2) Routing gets a **SEPARATE lane-policy
fingerprint**, not a reclassification of `_GATE_IRRELEVANT` — T111; the five-hash manifest keeps its
meaning. (3) F7's targeted second reading is **NOT NOW** — ship the judge-model move first, one
variable at a time, and re-read repeatability on the new model before pricing it. **F8 (portability)
is DROPPED, not deferred** — D-477 point 4 already rules it; its seven confirmed hardcodings are
recorded as the v2 boundary.

**T108 must land before the judge-model move** (next-action 4): without it the move reaches new
leads only. It also collapses T99's pending one-time re-judge into the same run.

**`main`'s CI was RED for four consecutive commits before this session and is now GREEN — the cause
was NOT the review.** Two tests in `web/src/__tests__/followUp.test.tsx` pinned `2026-09-20` as a
LITERAL future date; the follow-up chip reads "follow-up due <d>" once d is today or past, so the
assertion silently became a different one on arrival, and CI (UTC) crossed that boundary five hours
before local did. **A green local gate could not predict it and a re-run could not reproduce it** —
`TZ=UTC` reproduces it exactly (2 of 25 fail, the two CI named). Both now derive the date from
today. The other 14 date literals in that file compare dates to each other or to an input value,
never to today, and were left alone.

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
5. **Stages 2-3 stay REFUSED** on measured lead density (workday 0.17, smartrecruiters 0.08,
   oraclehcm **0.00** per 1k open). Run 467 does not revisit that — its density win is an
   INLINE-BODY figure.
6. **Still open and unruled:** purge the 801 Domino's rows (T95 is one pizza board and would
   falsely close 701 postings as specified); import Gap C's 43 `grnh.se` boards; the
   `--include-non-swe` / `--include-zero-signal` drains are inert at production N.
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
