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
> Mit's ruling, and **again on 2026-08-26** (30 settled blocks, this file 511 → ~260 lines, verified
> line-for-line that nothing was lost); nothing was deleted either time. Do not narrate a decision here
> that `DECISIONS.md` already holds — cite its number instead. **If this file passes ~250 lines again,
> the fix is to move settled blocks out, not to summarise them away.**

---



## Current standing

### Session 2026-09-03: the queue is audited END TO END and the eligibility catalog is measured at 8% of the problem

Reasoning: **D-436**, **D-438**. Numbers: `METRICS.md` (Session 2026-09-03).
**No run** — the 04:00 tick produces run 145.

Prior session (2026-09-02d) is settled and NOT restated here: **D-432**, **D-433**, **D-434**,
**D-435**, **D-437**, with its numbers in `METRICS.md` (Session 2026-09-02d).

### The 2026-09-03 queue audit — the waste is catalog COVERAGE, not routing

Blind two-judge audits of what the owner actually opens, reproduced independently by two sessions.
Mechanism: **D-436** (extraction) and **D-442** (the routing read). Full method in METRICS.

**THE HEADLINE THIS SESSION FIRST PUBLISHED — "the catalog is 8% of the problem, routing is the
rest" — WAS WRONG, and it was wrong by reading a verdict DISTRIBUTION as a defect ATTRIBUTION.**
8% of the apply lane carries an `eligible` verdict; that says where verdicts land, not where the
defect lives. Three sessions handed `review_gate.lane()` forward as *the lever* and **none had read
it.**

| | |
|---|---|
| apply lane | **597** — 526 `uncertain`, 49 `eligible`, 22 unevaluated |
| **of the 526, with ZERO requirement rows** | **481-487** (two independent counts) |
| their JD bodies | median **4,636 chars**, only 4 under 200, **~390 over 2,000** |
| `_review` | **1,007** — `experience_requirement` 497, `ineligible_verdict` 288, `role_unconfirmed` 175 |

**The routing is deciding CORRECTLY.** `experience_unconfirmed` fires **497** times, so the flag
works; all 597 apply-lane leads carry both flags False **because nothing was extracted, not because
nothing is wrong**. `_no_evaluable_requirement` makes them `uncertain` and `review_gate` never reads
WHY. **So the ~36% unapplyable rate IS the extraction gap arriving from the other end** — the same
finding as D-436's "every miss was a missing row", and the same reason the abstain report cannot see
it: **a family that extracts nothing is silent, and silence is indistinguishable from "the JD says
nothing".**

**IT SPLITS, AND ONLY A QUARTER IS COVERAGE (D-442).** Probing the zero-row bodies: **128 (26.3%)
carry a years bar in some form** (14 escaped punctuation, 24 spelled-out, 10 parenthesised), 55
citizenship/LPR, 32 sponsorship, 6 clearance, 4 non-English, **0 degree-required**. The other **~74%
trip none of those probes** — for those the JD may genuinely state no catalogued requirement, making
`uncertain` correct and the only question what an apply lane should DO with it. **The negative half
is bounded by those probes and nothing wider**: widening them can only move leads from the second
population into the first, never the reverse.

**THE GATE IS MEASURED, NOT ESTIMATED.** 77 apply-lane leads, two independent judges, real schema,
nothing applied: **15 demoted (19.5%), and 15 of 15 rejections survive `accept_oracle_verdict`'s
keystone span guard — ZERO span failures.** Every rejection quotes the employer's own JD, and two are
cases no amount of pattern work reaches (a French-language JD; markdown-escaped punctuation). Scaled
to 597: ~**116 demoted, each with a checkable quote**. Verdicts at `{config_dir}/verdicts_a.json` /
`verdicts_b.json` — **spot-check, then `gate apply`**. The earlier "~50-100 wrongly removed" treated
inter-rater disagreement as error-against-truth and ignored the guard; **retired**.

**Treatment vs cure.** The `final_gate:` LLM lane is the TREATMENT — it reads the JD directly and
catches what the patterns miss. **Catalog coverage is the CURE**, and the instrument is
**partial-match instrumentation of the patterns themselves** (a family that ALMOST matched), which a
cue vocabulary cannot substitute for: correct silence and a missed extraction look identical to a
cue and different to a near-miss. **D-442 holds the routing question** — ~360 of the 481 have no
detectable requirement at all, so it is "what should an apply lane do with a JD that states
nothing?", a decision about what the lane MEANS rather than a bug fix. Priced: apply **597 → 116**.

**The queue's 219 redundant leads are MOSTLY NOT A DEFECT (D-439).** 127 duplicate
`(company, normalised-title)` groups, but only **45 groups / 76 leads share one `content_hash`**;
the other **82 groups / 143 leads are genuinely distinct requisitions** (Evlo AI ×9 is nine real
reqs). An earlier reading called it identity resolution — **wrong**. The mechanism is D-345's cap
DEFERRING rather than dropping while scoped to one run, so a one-JD group delivers one member per
run forever. CGS Federal ×10 on a single hash is the shape that IS a defect.

**Sized and NOT built:** un-escaping markdown bodies 2.2% (owner-gated, re-versions postings);
`role_gate` missing the inverted `Engineer, Software` form (5 leads — the class D-305 fixed in
`seniority_gate` and never carried across); non-SWE residual in review only (apply-lane NOT_SWE was
0 of 40); `classify_location` fails open on Nottingham.

**`final_gate:` is built, keystone-guarded, identity-keyed, read by the ranker, and 0 rows on the
live store.** Request path VERIFIED live: **521 judgeable items of 537**, independence preserved,
read-only. **Ordering is forced** — `record_gate_verdict` keys on `build_identity(..., catalog, ...)`,
so any catalog change invalidates gate rows written before it. Land catalog PRs first, then arm ONCE.

## Next action

**0. TRACK 2 IS REFUTED ON LIVE MEASUREMENT AND IS DISARMED. DO NOT RE-ARM IT.** Armed at
`lane_company_combos_per_run = 12` on 2026-09-03, dry-run against the live host **before** the first
tick, disarmed 01:34. **4 of 120 cards on target (3%)**; 12 cells present **78 distinct companies,
61 new, against a cap of 50**, ahead of the hub nets, so arming it takes every slot. The rescue is
closed and was probed: the guest fragment serves **no numeric company id**, so `f_C=` is
unreachable and getting there is a **D-290 widening, the owner's**. Everything else: **D-437**.
**The 342 already-watched misses are STILL OPEN and the LinkedIn residual has no proposed mechanism
again.** Do not propose per-company cells without naming a mechanism that actually filters by
employer. The code stays merged and inert at `0`.

**1. ANSWER ONE QUESTION, AND IT DOES NOT WORK THE WAY AN EARLIER READING CLAIMED: does a stated
2-YEAR bar rule you out?** `near_miss_years_ceiling = 3` makes the engine ABSTAIN at or under 3
years, so those leads are held for review. **LOWERING IT DOES NOT RELEASE THEM — IT REJECTS THEM
(D-440).** Ceiling **2** rejects 290 postings; **0-1** rejects **505**. That reverses D-333 and takes
the expensive error direction: a wrong `unmet` writes `ineligible` with a quoted span and silently
removes a gettable job, and **the reject pile is never inspected**. Recommendation: do NOT lower it.
It also cannot deliver the range attributed to it — of 1,141 abstained rows, 583 are the band and
**465 are `scoped to a skill`**, which abstains whatever the ceiling is.

**AND THERE IS NO DATA FIX HIDING BEHIND IT — that was checked.** The résumé's dated Experience
section parses to **20 months / 1.67 years** across three roles: a 7-month SWE co-op plus **13
months of internships**, which these postings routinely exclude by name. The stored `1` understates
the raw total by ~8 months and **all of it is internship time**, so against a 2-year bar the résumé
and the stored fact agree. **The value is defensible and correcting it would not clear the bar.**

**Which leaves the question genuinely yours and not a data error**: it is whether you would apply to
a 2-year-bar posting anyway, knowing employers enforce those bars unevenly. Nobody but you can
answer that, and D-440 has priced every option so it is a row-pick rather than an opinion.

**2a. THE RE-KEY IS LIVE RIGHT NOW, NOT A PREDICTION.** The pull moved BOTH hashes — `rules_hash`
from the catalog change and `profile_hash` too, since D-438's resolver adds `education_timing` to
`declared_fields()`. Measured straight after: the live identity matches **no** stored
`eligibility_inputs` row, so a fresh read returns `None` for all ~138k open postings. **Nothing is
corrupted and it self-heals on the next run.** Until then the web view shows every lead unevaluated
and the apply lane reads INFLATED (`review_gate.lane` routes `None` like `uncertain`), while the
folders on disk still hold the last reconcile at 598 apply / 732 review. **Expect the web view and
the folder tree to disagree until the 04:00 tick.** A full re-evaluation was deliberately NOT
triggered: `eligibility run` would write ~138k rows over hours, duplicating what the tick does.

**2. THE CATALOG WORK IS MERGED AND THE CHECKOUT IS PULLED — what remains is the DRAIN.** D-436 and
D-438 are on `main`; the checkout is pulled and its catalog loads 7 families / 57 patterns, with 400
live bodies evaluated through the tick's own path and no crash. **The owed ledger drain releases
1,595 of 1,609 decisions — 99.1% — so: precision work FIRST, drain LAST, staged with `--job <id>`.**

**3. THE 50-BOARD SAMPLE IS READ AND THE REMAINING 282 ARE REFUSED (D-441). CLOSED — do not
re-open it from hiring.cafe's in-window counts, which is the number that was wrong.** Run 145
answered it in one run: the sample's **59 boards contributed 8,303 postings** against D-428's
predicted 79, and the run took **96.4 min writing 15,356 versions** against run 144's 21.9 min and
2,020 — **105x the postings, ~21-27x the minutes**, and 8,303 is a FLOOR because eleven of the top
twelve contributors hit `detail_fetch_budget = 400`. **It bought 10 delivered leads.** The sample is
NOT reverted; whether to keep paying ~60 min/run for 10 leads is the OWNER's, and is a different
question from adding 282 more, which is closed.

**4. RE-MEASURE GATE 1 AROUND 2026-09-09** (D-424) with
`.agent/2026-09-02-session/per_source_recall.py`. **The residual is LinkedIn alone**, and Track 2 is
the only lever that has moved since — which is why arming it (item 0) belongs before this, not after.

**5. SET PER-SOURCE THRESHOLDS** (owner). Framing DECIDED: option D then C — decompose LinkedIn
first (**done**, D-431), then bar on `lane-only` exposure rather than recall. The numeric level is
still the owner's.

**6. TRACK 1 — admit the 92 already-admissible LinkedIn boards** (382 postings, ~4.9 min/run, no new
code) and **ARM the `grnh.se` resolver** (D-429, ~90 boards, ~5 min/run). **Both still HELD until
run 147**: each admits boards, and landing either inside runs 145-147 makes the hiring.cafe sample's
yield unreadable. That is why "both levers" was rejected.

*(Closed since the last close: Track 2 — BUILT and DISARMED, D-433. The buried live requisition —
FIXED, D-432, and its blast radius re-measured as 1 job, not 16. The `_reported` folder drain —
SHIPPED, D-434. The `perf` flaky bound — CHARACTERISED and FIXED, D-435.)*

### Run 145 — read out; both of the night's queue fixes are CONFIRMED IN PRODUCTION

96.4 min, exit **ok**, 94 tailored leads. Queue **598 apply / 732 review / 274 ineligible / 107
closed / 0 reported**. Full numbers: `METRICS.md` (Run 145). **D-432 CONFIRMED** — the buried eBay
requisition (job 35249) left `_closed` for `_review` and its genuinely-dead same-titled sibling
(35247) correctly stayed. **D-434 CONFIRMED** — `_reported/` created and empty, exactly as "0
reported, 0 skipped on the live store" predicted, so a live reconcile could not have exercised that
drain either way and the unit tests were the only thing that could catch it.

**A count prediction and a mechanism prediction are different claims, and only the second was
D-432's.** `_closed` went 103 → **107**, not the predicted 102: a 96-minute rescan of 1,124 boards
found new closures, and the prediction implicitly held the world still for an hour and a half.

### Owed, and specifically NOT done

- **`grnh.se` redirect-following is BUILT and SHIPPED (D-429), and deliberately NOT ARMED.**
  `boardwatch companies discover-grnh` emits candidates; `companies import` is the arming act.
  **Arming must wait for run 147** or it contaminates the board sample's reading — the two board
  levers cannot be read apart inside one window. Owner's call.
- **Per-source thresholds are not set** — the owner's.
- **THE OWNER'S CALL, and it outweighs every rule shipped this session: does a stated 2-YEAR
  experience bar rule you out?** `experience_years.near_miss_years_ceiling = 3` makes the engine
  ABSTAIN on bars at or under 3 years rather than reject. Across the **475** review-lane leads held
  for `experience_requirement` the rows are **2,809 `unknown` · 258 `unmet` · 43 `met`** — the engine
  declining to decide on exactly the bar he is closest to. **Two blind judges disagreed on this and it
  swung ~10 of 40 leads**, which is why the review lane's wrong-hold rate is a RANGE (**17%-47%**) and
  not a number. One sentence collapses it. Not free either way: D-333 records that each extra year
  moves genuinely-too-senior postings into the delivered pool, and the reject pile is never inspected.
- **THE ABSTAIN REPORT CANNOT SEE AN EXTRACTION GAP, BY CONSTRUCTION (D-436).** `reports/abstain.py`
  aggregates per `rule_id` across the WHOLE corpus, so a pattern that matches most phrasings and
  misses a near-miss variant is neither `never_fired` nor `fully_abstaining` — its rate looks
  **healthy**. The keystone makes a rule that cannot resolve a profile FIELD visible as a 100%
  abstain rate; it says nothing about an extractor that cannot find the requirement in the TEXT,
  because the rule never got the chance to abstain. A blind two-judge audit put **24% of `eligible`
  wrong (13 of 54)** and **every single miss was `no requirement row written`**, not a rule
  deciding badly. **Unfixed.** The honest fix is a THIRD OUTCOME per family — "the extractor ran and
  matched nothing" and "the JD is silent" are collapsed into one today and the second one clears —
  not more patterns, which is whack-a-mole.
- **THE D-436 PATTERN FIXES CATCH *ZERO* OF THE 13 MEASURED FALSE POSITIVES — the 24% is UNCHANGED.**
  Measured, not assumed: the two fixed sentences came from the pre-correction 218-job sample and do
  not survive into the real 144. The fixes are safe (0 regressions) and close real leaks, but the
  delivered population's defect rate did not move. **The 13 have ~7 distinct root causes**, so more
  patterns is whack-a-mole. **The unarmed answer is the two-stage shape already built:**
  `boardwatch eligibility gate request`/`gate apply` (the `final_gate:` LLM lane — ineligible-capable,
  keystone-guarded, identity-keyed, read by the ranker) over the **~8-10 leads/day delivered**, which
  is the only population where zero-ineligible is reachable. **0 rows on the live store today.**
  Owner-gated.
- **`experience_years` MISSES SPELLED-OUT AND ESCAPED YEARS BARS, and it is a BODY-NORMALISATION
  defect, not a regex one (D-436).** All eight patterns anchor on `\d{1,2}` adjacent to `years`, so
  `Six to eight years`, `four (4) years` (the `)` breaks digit→`years` adjacency) and `5\+ years`
  write zero rows. **477 open bodies carry markdown-escaped punctuation, 175 of them with a
  `\+ years` bar.** **Owner-gated because un-escaping at ingest RE-VERSIONS POSTINGS** — that is the
  sentence that stops someone doing it cheaply. Teaching eight regexes to tolerate stray backslashes
  fixes the symptom at the wrong layer.
- **`classify_location` FAILS OPEN on unrecognised cities**, so Nottingham (UK) postings reached a
  US-only queue in the D-436 audit. Not fixed; the fail-open direction is deliberate (D-294) and
  narrowing it is a precision/recall decision, not a bug fix.
- **THE LIVE STORE HAS 0 REPORTED AND 0 SKIPPED JOBS**, so run 145 cannot exercise the new
  `_reported` drain (D-434) in either direction. **A clean live reconcile is NOT evidence it
  works** — the unit tests are the only thing that can catch it. Measured by a peer session.
- **Track 2's cap cost has no measured UPPER bound.** A per-company cell costs *at least* one
  `lane_new_companies_per_run` slot, and would cost exactly one only if a quoted-phrase search
  returned cards solely from the named employer — which was never probed. **Read the funnel's
  per-lane `admitted`/`refused` split on the first armed run**; it measures this directly.
- **No alert wiring for the seed leak.** `boardwatch seeds` is a command you must run. The
  finalize-block alert-ordering invariant makes wiring it a separate change with its own review.
- **T1's concurrent case-variant duplicate race** — deferred, pre-existing, worst case a dead-weight
  row. Fix is a `(provider, lower(slug))` unique index plus a reconcile.
- **T3's exotic hostnames** — unicode-dot/fullwidth IDN and legacy IPv4 can still store an
  undrainable row. Dead weight only.

## Owner-gated — do NOT start or decide unilaterally

0. ~~gate 1 >= 80%~~ / ~~"cover most of what job-apps does daily"~~ **BOTH RETIRED. Gate 1 is now
   PER-SOURCE RECALL (D-421), and the only thing still owed from the owner is the THRESHOLD, per
   source.** The instrument is built and has a first reading (see Current standing). Set a bar per
   source rather than one number — the direct-ATS mechanism is already at 94–100% while the
   aggregator mechanism is at 12–33%, and any single average hides that. **Do not re-litigate 80%,
   and do not re-derive "most".**

1. ~~Does job-apps keep running, or is it retired?~~ **ANSWERED — it keeps running until gate 1 is
   met.** Both schedulers armed: boardwatch 04:00, job-apps 08:30. **The retirement work is now a
   written plan, not a question: `docs/program/RETIREMENT-PLAN.md`.** Do not re-raise WHETHER, and do
   not re-derive the gap analysis.
   ~~2. Indeed's dependency posture.~~ **DECIDED by Mit 2026-09-01 (D-410): approved.** Closed; do
   not re-open or re-probe.
2. **Mit's two résumé content calls** — whether to send a document at all; the D-220 prose rewrites.
3. **P2 item 8 — the onboarding field-taxonomy gatherer. DEFERRED by Mit 2026-08-28.** The last
   multi-tenancy gap of its kind; D-054 forbids us authoring non-tech field content.
4. **`add-evidence` takes no bundle lock** (D-143) — raise before two authoring agents run against
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

*(Resolved and no longer open: the delivery slate cap — D-345, `(company_id, normalized_title,
content_hash)` at N=1; do not reopen as identity suppression, which is D-295 and is refused.
Whether `runner.py` should keep swallowing a funnel-write failure — D-288. Clearance IS a blocker
(D-257). Seniority band = `entry` (D-258), and it is **armed on the live profile**.)*

## Phase status

**P0–P6 are all COMPLETE and their gates all MET, and none has moved in weeks — the full table
moved WHOLE into `STANDING-FACTS.md` on 2026-09-01e when this file passed 250 lines again.** Read it
there. Only these are not settled:

- **P2 item 8** (field-taxonomy gatherer) **NOT STARTED** — the last multi-tenancy gap, owner-gated.
- **P7 Breadth**: LinkedIn, GitHub-lists, jobapps, **`jsonld` and `indeed` are all built and
  ARMED** (D-420; `indeed`'s cap raised to 50 on 2026-09-02). **hiring.cafe is armed and WORKING** —
  runs 143 and 144 both succeeded; its 17% RECALL is a board-fleet gap, not a lane defect (D-425),
  and its one post-fix failure is run 142 alone (blocker table). Remaining tier-D lanes not started
  (D-413 ranks them).
- **14-day acceptance: not started, HELD BY THE OWNER.** The provisional pass is **not being
  chased** (D-351 item 2: work comes first), and every `rules_hash` bump restarts its counter.

## Live blockers and carried gaps

| Item | Detail | Owner |
|---|---|---|
| **boardwatch sees 16.4% of job-apps' eligible yield — RE-DERIVED 2026-08-30, and the METHOD was wrong before** | **45 of 275 (16.4%)**, cohorts 08-23..08-29, on the **379-board fleet**. This replaces "10.1%, owed a check". It decomposes: fleet growth 344->379 gave 10.1 -> **13.8%**; adding an **exact ATS-slug key** alongside name matching gave 13.8 -> **16.4%**. **Name-only matching undercounts, so 7.7% and 10.1% are FLOORS** — boardwatch stores Micron as `Micron TDIT`, so the old method scored a watched company as unwatched; same for HPE/`Hewlett Packard Enterprise`, Cox/`Cox Automotive`, Disney/`Walt Disney Company`, Toyota, VIAVI. **The unreached 230 split: aggregator-only 60.7%, unsupported employer host 21.1%, board-addable just 1.8%** (5 postings in 7 days, 4 of them SmartRecruiters — the class D-370 declined on measured cost), so the cheap remainder is ONE Workday board (Motorola Solutions). **The gap is lanes, not boards.** Script: `.agent/2026-08-30-session/reach_v2.py`. Amazon/TikTok/Apple/ByteDance use none of the 6 ATS, so a slug cannot reach them. Closing it means a new discovery lane — GitHub new-grad lists are 19.1% of yield for ~5 public-repo GETs and are NOT the ToS trap the v2 decision was written about. **Reopens D-008** | **Mit** (reverses a shipped decision) |
| **`companies.last_health` / `last_ok_at` are a LYING instrument** | 178 of 379 watched boards read NULL, which looks like "never succeeded" — **all 178 were scanned by run 133** (128 complete, 7 partial, 43 unchanged). The scan path does not maintain these columns. **Judge fleet health from `board_scans` per run instead**: run 133 was 379 attempted / 271 complete / 87 unchanged / 21 partial / **0 failed** | tooling gotcha |
| **Citi sits at 13.1% coverage, permanently** | Workday's `total` censors at 2,000; the facet sum (uncapped, control-verified) says 4,589. Our pager wraps at ~2,000 too, so post-drain Citi holds ~2,214 of 4,589 and nothing reports it | **Mit** (input-side) |
| **`unchanged` staleness is now BOUNDED (D-298, #153)** | The `unchanged` verdict comes from the upstream HTTP validator (ETag/Last-Modified → 304), not a boardwatch payload hash. `validator_max_age_hours` (default 24) drops a validator older than the TTL, forcing an unconditional refetch, so a permanently-stale upstream can no longer freeze a board forever — the silent-staleness window is capped at the TTL, and a regression test now exercises the aged-validator refetch. Still open: within the TTL an `unchanged` is trusted with no independent check. The separate "59 of 135 boards listed nothing" figure was a **`postings_listed`-on-304 artifact — CORRECTED to 17 real dead-weight (D-300)**, now cleaned; the 118 `ok` boards hold 39,253 open postings | open (mitigated) |
| **The unattended 04:00 tick runs the PRIMARY checkout's branch — and it is now PROVEN to fire** | Run 131 (2026-08-29, `runs = 1`, exit 0) was the first real unattended tick. The launchd job invokes the **editable** venv at `boardwatch/.venv/bin/boardwatch`, so whatever branch that tree is parked on IS the unattended run's code and `rules.yaml`. **Verified at the 2026-08-29f close: the tree is on `main` at `10baad5`, clean, and all six alert modules import through the editable venv.** A stale 8-hour-old `.git/index.lock` had silently blocked every `git pull` that session — check the lock's MTIME and `pgrep -x git` before blaming contention. **Park it on `main` before ending every session** — from ~2026-08-31 a stray branch changes EVERY subsequent run, not one. Closing it mechanically means pointing the plist at a worktree pinned to `main`, which moves a scheduled job and a venv | **Mit** (mechanism); every session (discipline) |
