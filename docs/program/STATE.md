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

### The 2026-09-03 queue audit — the catalog is 8% of the problem

Blind two-judge audits of what the owner actually opens. Full numbers and method in METRICS
(`Session — 2026-09-03`); the mechanism is D-436.

- **The apply lane is 481 `uncertain` / 44 `eligible` / 12 `None`** — only **8%** of what the owner
  sees carries an `eligible` verdict. The rest FAILED OPEN through `review_gate.lane()`. Fixing the
  eligibility catalog addresses 8% of his queue.
- **Apply lane: ~36% unapplyable** (n=80, two disjoint samples, 8/10 agreement) — ~175 dead leads.
  **All 13 of the first audit's false positives carried `uncertain`, not `eligible`** — a ROUTING
  fact, not a catalog fact.
- **The queue carries 219 redundant leads, and MOST ARE NOT A DEFECT (corrected — see D-439).**
  127 duplicate `(company, normalised-title)` groups, but only **45 groups / 76 leads share one
  `content_hash`**; the other **82 groups / 143 leads are genuinely distinct requisitions** (Evlo AI
  ×9 is nine real reqs, Haystack ×6 is six). An earlier reading of this called it an
  identity-resolution failure — **that was wrong.** The real mechanism is D-345's cap DEFERRING
  rather than dropping, scoped to one run while the queue is not, so a one-JD group delivers one
  member per run forever. CGS Federal ×10 on a single hash is the shape that IS a defect.
- Sized and NOT built: un-escaping markdown bodies 2.2% (owner-gated, re-versions postings);
  `role_gate` missing the inverted `Engineer, Software` form (5 leads — the class D-305 fixed in
  `seniority_gate` and never carried across); non-SWE residual in review only (apply-lane NOT_SWE
  was 0 of 40, so D-305 holds where it matters); `classify_location` fails open on Nottingham.

**The lever is the `final_gate:` LLM lane** — built, keystone-guarded, identity-keyed, read by the
ranker, and **0 rows on the live store**. It only has to run over the ~8-10 leads/day delivered.
**Request path VERIFIED on live data**: `build_gate_request` over the real apply lane produced **521
judgeable items of 537**, independence preserved, read-only. **Ordering is forced** —
`record_gate_verdict` keys on `build_identity(..., catalog, ...)`, so any catalog change invalidates
gate rows written before it. Land the catalog PRs first, then arm ONCE.

## Next action

**0. TRACK 2 IS REFUTED ON LIVE MEASUREMENT AND IS DISARMED. DO NOT RE-ARM IT.**
Armed at `lane_company_combos_per_run = 12` on 2026-09-03, dry-run against the live host before the
first tick, disarmed the same night at 01:34 (verified through `load_settings()` and `config.toml`).
Full reasoning: **D-437**. The numbers that entry does not carry, kept here:

- **On target: 4 of 120 cards (3%).** A quoted company name is a relevance-ranked KEYWORD on the
  guest endpoint, not a company filter. `"Tailscale" software engineer` returned zero Tailscale.
- **The cap cost is the opposite of D-433's estimate: those 12 cells present 78 distinct companies,
  61 of them new, against a cap of 50** — and cells sit BEFORE the hub nets in the interleave, so
  arming it takes all 50 slots and leaves the hub nets ZERO. A straight regression.
- **A control was necessary**: six well-known companies read ~20% on target; all twelve read 3%. The
  six-company sample was biased toward employers who post heavily on LinkedIn. The ring is not.
- **The obvious rescue is closed and was probed**: LinkedIn's real filter is `f_C=<numeric company
  id>` and the guest fragment serves no numeric id, only a slug. Employer filtering needs a
  slug-to-id mechanism on another surface — a widening of D-290 and the owner's call, not a probe.

**The 342 already-watched misses are STILL OPEN and the LinkedIn residual has no proposed mechanism
again.** Do not propose per-company cells without naming a mechanism that actually filters by
employer. The code stays merged and inert at `0`.

**1. ANSWER ONE QUESTION — but note it does NOT work the way an earlier reading of it claimed:
does a stated 2-YEAR experience bar rule you out?** `experience_years.near_miss_years_ceiling = 3`
makes the engine ABSTAIN on bars at or under 3 years, so those leads are HELD FOR REVIEW.

**LOWERING THE CEILING DOES NOT RELEASE THEM — IT REJECTS THEM (D-440).** A lower ceiling resolves
those bars `unmet`, which makes the posting `ineligible` and removes it from the pile because the
engine has started declaring you unqualified. Priced: ceiling **2** rejects 290 postings at exactly
a 3-year bar; ceiling **0-1** rejects **505** (259 at 2y + 290 at 3y). That reverses D-333's
recorded ruling rather than tuning a parameter, and it takes the EXPENSIVE error direction — a wrong
`unmet` writes `ineligible` with a quoted span and silently removes a gettable job, while a wrong
abstain costs a look. **The reject pile is never inspected, so no outcome loop can ever contradict
it.** Recommendation on the numbers: do NOT lower it.

**And the ceiling cannot deliver the range that was attributed to it.** Of 1,141 abstained
`experience_years` rows on delivered leads, **583 are the near-miss band and 465 are `scoped to a
skill`** — which abstains in both directions whatever the ceiling is (corpus-wide: 186,553 scoped
against 27,823 near-miss). **If one declared year understates you, the thing to change is
`total_years_experience` — profile DATA — not this policy threshold.**

**2. MERGE #341 (D-436) AND #343 (D-438) ATTENDED, THEN ARM THE `final_gate:` LANE — in that order,
and the order is FORCED.** Both PRs move `rules_hash`; `record_gate_verdict` keys on
`build_identity(..., catalog, ...)`, so any catalog change invalidates gate rows written before it.
**Merge attended**: the first run after either lands re-evaluates the corpus and relocates real
leads — measured, every delivered lead reads verdict `None` and the apply lane goes **537 → 1,222**
as `None` routes like `uncertain`. A **ledger drain is owed** and D-351's counter restarts. Then run
the gate ONCE: `eligibility gate request` → judge → `gate apply`. The request path is verified on
live data (521 judgeable items of 537, independence preserved); `gate apply` writes **immutable**
evaluations, so it is an attended act.

**3. READ THE 50-BOARD SAMPLE'S YIELD OVER RUNS 145-147, THEN DECIDE THE REMAINING 282.** Unchanged
(D-428; watched 403 → 453). Population 332 boards / 471 postings, **1.42 in-window postings per
board**; the remaining 282 cost ~15 min/run. Reversal:
`companies-prehcsample-20260902-183019.csv`.

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
| ~~The `experience_years` group reads a REFINEMENT as a CONTRADICTION~~ **CLOSED by #291 / D-389** | `refinement_groups` ships as a second group kind in versioned catalog DATA: `exclusive_groups` keeps PRESENCE semantics, `refinement_groups` dissolves only on a real `MET`/`UNMET` straddle. Only `experience_years` moved — **a global rule regresses 8 of 1,034 corpus cases** (D-388), because `clearable_required` is a DISJUNCTION not a weaker rung. **913 of a PINNED 1,868 flip `uncertain` -> `ineligible` (48.9%)**, corpus 0/1034 (predicted before review). **`engine_version` MOVES so a LEDGER DRAIN IS OWED.** Known property, direction deliberate: the refinement pass runs BEFORE stage 1b, so a same-implies split beside another present member dissolves the group where stage-1b-first would let a decisive `unmet` stand — the shipped order is the ABSTAIN direction | **CLOSED** |
| **boardwatch sees 16.4% of job-apps' eligible yield — RE-DERIVED 2026-08-30, and the METHOD was wrong before** | **45 of 275 (16.4%)**, cohorts 08-23..08-29, on the **379-board fleet**. This replaces "10.1%, owed a check". It decomposes: fleet growth 344->379 gave 10.1 -> **13.8%**; adding an **exact ATS-slug key** alongside name matching gave 13.8 -> **16.4%**. **Name-only matching undercounts, so 7.7% and 10.1% are FLOORS** — boardwatch stores Micron as `Micron TDIT`, so the old method scored a watched company as unwatched; same for HPE/`Hewlett Packard Enterprise`, Cox/`Cox Automotive`, Disney/`Walt Disney Company`, Toyota, VIAVI. **The unreached 230 split: aggregator-only 60.7%, unsupported employer host 21.1%, board-addable just 1.8%** (5 postings in 7 days, 4 of them SmartRecruiters — the class D-370 declined on measured cost), so the cheap remainder is ONE Workday board (Motorola Solutions). **The gap is lanes, not boards.** Script: `.agent/2026-08-30-session/reach_v2.py`. Amazon/TikTok/Apple/ByteDance use none of the 6 ATS, so a slug cannot reach them. Closing it means a new discovery lane — GitHub new-grad lists are 19.1% of yield for ~5 public-repo GETs and are NOT the ToS trap the v2 decision was written about. **Reopens D-008** | **Mit** (reverses a shipped decision) |
| ~~Delivery-drought cannot see APPLY-LANE starvation~~ **CLOSED by #285 / D-384** | `delivery_drought.py` counts `artifacts.kind == TAILORED_KIND`, written **regardless of which lane `review_gate.lane()` routes to**, so a global misclassification shipped zero apply-ready leads with every existing alarm green. `check_apply_lane_drought` now fires when the last 3 clean runs each delivered PLACEABLE leads and none reached the apply lane. **The old sizing was wrong, not merely pessimistic**: it priced a guard inside `_sync_queue`, but the three job-id readers already take only a connection and `QueueRow` already carries `delivered_run_id`, so nothing in `review_gate`, `_sync_queue` or the web server's result type had to change. Known property, direction abstain-not-alarm: `delivered_unapplied` attributes a re-delivered job to the NEWER run, so an older run can read zero placeable and the window abstains | **CLOSED** |
| ~~Four detector fallbacks are print-only, not durable~~ **CLOSED by #260** | The `intake-death` / `delivery-drought` / `liveness-blindness` / `corpus-regression` "check not run" handlers now call `append_run_error` like the three artifact-write handlers beside them, so a DETECTOR that crashes leaves a row in `runs.errors_json` and not only a digest line. Four one-line additions, inert on the normal path; each pinned by its OWN parametrised test, because a single test crashing all four passes while three of the four calls are missing. **Known shared property:** `append_run_error` is not internally defensive and these sit inside `except` handlers — matched to the three existing handlers deliberately rather than diverging; it needs two simultaneous failures and fails loudly via the withheld heartbeat | **CLOSED** |
| **`companies.last_health` / `last_ok_at` are a LYING instrument** | 178 of 379 watched boards read NULL, which looks like "never succeeded" — **all 178 were scanned by run 133** (128 complete, 7 partial, 43 unchanged). The scan path does not maintain these columns. **Judge fleet health from `board_scans` per run instead**: run 133 was 379 attempted / 271 complete / 87 unchanged / 21 partial / **0 failed** | tooling gotcha |
| **Citi sits at 13.1% coverage, permanently** | Workday's `total` censors at 2,000; the facet sum (uncapped, control-verified) says 4,589. Our pager wraps at ~2,000 too, so post-drain Citi holds ~2,214 of 4,589 and nothing reports it | **Mit** (input-side) |
| **`unchanged` staleness is now BOUNDED (D-298, #153)** | The `unchanged` verdict comes from the upstream HTTP validator (ETag/Last-Modified → 304), not a boardwatch payload hash. `validator_max_age_hours` (default 24) drops a validator older than the TTL, forcing an unconditional refetch, so a permanently-stale upstream can no longer freeze a board forever — the silent-staleness window is capped at the TTL, and a regression test now exercises the aged-validator refetch. Still open: within the TTL an `unchanged` is trusted with no independent check. The separate "59 of 135 boards listed nothing" figure was a **`postings_listed`-on-304 artifact — CORRECTED to 17 real dead-weight (D-300)**, now cleaned; the 118 `ok` boards hold 39,253 open postings | open (mitigated) |
| **`resume.yaml` is an IMPORT SOURCE, never hand-fixed** | D-155. Mit pins `resume_max_pages=1`; never advise 2 | Mit |
| **`boardwatch top` advances the queue by default** | records `seen` unless `--no-record`; relevant to Gate P6's clean window | P6 |
| **A live store is readable ONLY via Python `sqlite3` `?mode=ro`** | the `sqlite3` CLI with `?mode=ro` fails `CANTOPEN(14)` on a cleanly-checkpointed store (no `-shm`; not the sandbox), and `?immutable=1` skips the WAL so it is STALE against a live writer. Mid-run progress: `SELECT COUNT(*) FROM eligibility_evaluations WHERE run_id=N` (D-268) | tooling |
| **The unattended 04:00 tick runs the PRIMARY checkout's branch — and it is now PROVEN to fire** | Run 131 (2026-08-29, `runs = 1`, exit 0) was the first real unattended tick. The launchd job invokes the **editable** venv at `boardwatch/.venv/bin/boardwatch`, so whatever branch that tree is parked on IS the unattended run's code and `rules.yaml`. **Verified at the 2026-08-29f close: the tree is on `main` at `10baad5`, clean, and all six alert modules import through the editable venv.** A stale 8-hour-old `.git/index.lock` had silently blocked every `git pull` that session — check the lock's MTIME and `pgrep -x git` before blaming contention. **Park it on `main` before ending every session** — from ~2026-08-31 a stray branch changes EVERY subsequent run, not one. Closing it mechanically means pointing the plist at a worktree pinned to `main`, which moves a scheduled job and a venv | **Mit** (mechanism); every session (discipline) |
| **hiring.cafe: ONE unexplained POST-FIX failure (run 142) — and D-420 recorded two wrong framings before this one.** #304 (`11a1ae95`) merged **2026-09-01T07:56:34Z**. Against that boundary: **130, 131, 133, 134, 135, 136, 137 all FAILED and all seven PREDATE the fix** (132 ok, a single unexplained point); post-fix **138, 139, 140, 141, 143, 144 ok** and **142 is the only failure**. **So #304 WORKED** — this is neither a regression nor chronic flakiness. Not time-of-day: 138 also started 09:00Z and passed. **METHOD LESSON, which cost two wrong entries in one session: date a behaviour claim against the COMMIT that changed the behaviour, not against a run streak — a streak has no denominator until you know when the code changed.** Do NOT retry the eliminated dead ends: the header lever failed twice (D-369; run 133 reproduced the refusal byte for byte) and the UA and volume premises were both false. | **watch** |
