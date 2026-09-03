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

### Session 2026-09-02c: the board sample is ADMITTED, the `grnh.se` resolver and the queue fix SHIP, `click.appcast.io` is REFUSED, and a figure the docs carried was wrong

Reasoning: **D-428**. Numbers: `METRICS.md` (Session 2026-09-02c). **No run** — the 04:00 tick
produces run 145, the first run that reads any of this.

**1. THE OWNER'S BOARD-ADMISSION CALL IS TAKEN AND APPLIED.** Asked with all three options priced;
the owner chose **a 50-board sample**, rejecting `grnh.se`-first, both-levers, and hold-until-09-09.
Applied via `companies import --verify` (D-291 decision 2): **watched 403 → 453**, rows
2,122 → 2,166, `0 skipped / 0 empty / 0 recased`. **Verified by counting the store, not by the CLI's
"Imported 50 watches"** — the +44/+6 split reconciles exactly against 44 addable / 6 known-unwatched.
Sample is **RANDOM on pinned seed 20260902, deliberately not top-by-yield**, carrying 79 in-window
postings at **+2.7 min/run**. Reversal: `companies-prehcsample-20260902-183019.csv`.
**READ THE YIELD OVER RUNS 145-147**, then decide the remaining 282 boards.

**2. D-425's "471 BOARDS" WAS POSTINGS. It is 471 postings across 332 DISTINCT BOARDS** (293
never-seen employers / 377 postings; 39 known-unwatched / 94). Budget is charged per BOARD, so full
admission is **~17.7 min/run, not the ~25 min this file and the handoff both carried**, and yield is
**1.42 in-window postings per board**. The lever is cheaper AND weaker than recorded; neither
correction was visible while the unit was a posting.

**3. `click.appcast.io` IS REFUSED AS A RESOLVER TARGET, ON MEASUREMENT.** It was the largest
unclaimed seed host (144) and a candidate to outrank `grnh.se`. It does not. **It redirects in
JAVASCRIPT**, so an HTTP redirect-follower reads `200 hops=0` — the first pass's "0 of 12 resolve"
measured THE PROBE, not the host. Extracting the JS target: **40 of 40, 0 errors**, but only
**1 of 40 (2.5%)** parses to a supported board; the 144 seeds collapse onto ~6 employers
(CVS 26, Cox 9) on the **same unsupported-adapter tail D-422 and D-425 already named** — a third
instrument naming one missing adapter class. **Do not build an appcast resolver.**

**4. DISK RECLAIMED: 5.2 GB free at 98% → 11 GB at 95%** — the 5.52 GB pre-tier-A store
backup was deleted on the owner's call; it was frozen at run 143, so restoring it would have
discarded run 144's harvest. The CSVs are the artifacts that reverse an admission, not a DB copy.

**5. THE PEER'S WORK LANDED.** `boardwatch-d3` shipped the review app's Report action and D-427 in
`08d7b957`; CI on the combined main is green. The two sessions serialised their DECISIONS/index
writes by message rather than colliding.

**6. THE `grnh.se` RESOLVER IS BUILT AND SHIPPED, AND DELIBERATELY NOT ARMED (D-429).**
`boardwatch companies discover-grnh` follows each stored short link to the board behind it and
emits a registry-format candidate file. **Not a `Lane`, not in `LANE_FACTORIES`, so it costs a run
zero seconds**; arming is `companies import`, a separate act, and **should wait for run 147** or the
two board levers cannot be read apart. Writes nothing — not the store, not `watched`, not
`resolved_at`. Live: 8 seeds → 8 boards, 0 off-board, 0 failed.
**The sizing in this file was incomplete: `FetchResult` DISCARDED the redirect destination**, so the
resolver was impossible without growing the shared fetch contract (3 construction sites, safe).
`FetchFailure` needed it too — a 404 target has already NAMED its board, and an aged backlog is
mostly live boards with expired requisitions.

**7. THE RECURRING `QueueConflictError` IS FIXED (D-430)** — a TWO-folder identity convergence.
Both postings had folders, the loser's planned name collided with the winner's, and nothing ever
removed a folder. Fixed by DELETING the duplicate (owner's call); `SyncReport` gains `retired`.
No `engine_version` bump, no ledger drain, no migration.
**LEFT OPEN and BIGGER: a LIVE requisition is buried in `_closed`.** `delivered_unapplied` picks a
job's winner by ARTIFACT RECENCY, not liveness, so a dead lane copy's `closed` flag decides the job
— an actual lost delivery, not noise, and NOT fixed by the folder consolidation. Own decision owed.

**8. TWO REVIEWS AGAIN BEAT A GREEN GATE.** The resolver's first cut gated green (9,197 passed) with
six mutations caught and a no-op control; a review then found **nine** findings, including a default
stdout path whose rich word-wrap broke the YAML it emitted, a census that counted a deduplicated
seed in NO bucket, and a dedupe test with **no negative control**. A second mutation campaign found
a tenth. **A mutation campaign only tests the bugs you already imagined** — three findings sat where
no mutation could reach.

**9. THE LINKEDIN RESIDUAL IS PLANNED AND JOBSPY IS REFUSED (D-431).** The owner asked whether to
adopt JobSpy. **It calls the SAME guest endpoint `lanes/linkedin.py` already calls** — no capability
boardwatch lacks, only a Chrome UA and more query cells, at the price of `tls-client`+`numpy`+
`pandas`. D-414 refused it once already on the same grounds. **D-417's "these employers have no ATS
board" is REFUTED at scale**: n=77 read 74% not-in-store, the full 5,876-posting set reads **48.3%**,
led by Raytheon/Netflix/Perplexity/Upstart — a **discovery** gap, not an architecture limit. Also:
a "known" employer is usually a lane PLACEHOLDER (`linkedin:google`), so board admission reaches
**6.5%, not 45.9%**. **The next session builds from `LINKEDIN-CLOSURE-PLAN.md`.**

## Next action

**0. BUILD TRACK 2 OF `LINKEDIN-CLOSURE-PLAN.md` — per-company LinkedIn query cells.** LinkedIn is
the ENTIRE retirement residual (D-424): every other source is solved or self-solving, and Indeed is
**0 absent / 6,740 lane-only**, which converts with no new work. Track 2 targets the **3,037 absent
postings (51.7%)** at employers boardwatch already knows by name. **It needs NO new URL shape** —
the guest endpoint already takes `keywords=`, so a company cell is a composed facet string: add a
`hub_nets` sibling in `lanes/facets.py` and append its cells to `search_facets` in `_linkedin_lane`.
Seed from the store, watched first. **Facets come from the PROFILE and the STORE, never the module** (multi-tenancy).
**Size it against `lane_posting_budget = 300` and the measured 2.39 s/body, not against the company
count** — new cells must not starve the hub nets that already work.
**Falsifiable first gate: the 342 ALREADY-WATCHED misses.** Nothing but query coverage can explain
them, so if they do not move, Track 2 did not work. **Do NOT raise the company cap** (D-417: 10 → 50
bought +1 posting). **Do NOT re-propose JobSpy** (D-431).

**1. READ THE 50-BOARD SAMPLE'S YIELD OVER RUNS 145-147, THEN DECIDE THE REMAINING 282.** The
sample is ADMITTED and armed (D-428; watched 403 → 453). **This is the only thing runs 145-147 are
for, and it is spoiled by arming a second board lever in the same window** — that is why the owner
rejected "both". Population: 332 boards / 471 postings, **1.42 in-window postings per board**;
the remaining 282 cost ~15 min/run. Reversal: `companies-prehcsample-20260902-183019.csv`.

**2. `grnh.se` RESOLVER — BUILT AND SHIPPED (D-429); ARMING IS STILL OWED AND IS THE OWNER'S.** The premise is MEASURED: 12 of 12 seeds followed their
redirect to a URL `parse_board_target` accepts, 0 misses / 0 errors, yielding **9 distinct greenhouse
boards from 12 seeds** (~1.3 seeds/board, so 122 seeds ≈ 90 boards); **0 of the 9 already watched,
6 absent from `companies` entirely** — board-fleet growth, not re-discovery. `parse_board_target`
already accepts `boards.greenhouse.io/<slug>` and `job-boards.greenhouse.io/<slug>`, so no new ATS
adapter is needed. **ARMING IS THE OWNER'S CALL AND SHOULD WAIT FOR RUN 147** — ~90 boards is ~5
min/run forever, and arming before the sample is read makes the two yields inseparable.

**3. RE-MEASURE GATE 1 AROUND 2026-09-09** (D-424), once Indeed has reached steady state. Three of
the four inputs have moved: the harvest is in, Indeed is armed and uncapped at 50, hiring.cafe is
diagnosed. **The residual is LinkedIn alone**, and that is a judgment about a population.

**4. SET PER-SOURCE THRESHOLDS** (owner). **Framing DECIDED 2026-09-02: option D then C** —
decompose LinkedIn first (**done**, D-431), then set the bar on `lane-only` exposure rather than on
recall, because a recall bar would score boardwatch against a population it structurally does not
serve. The numeric level is still the owner's.

**5. TRACK 1 — admit the 92 already-admissible LinkedIn boards** (382 postings, ~4.9 min/run,
no new code). **Owner's call, and it COMPETES with the hiring.cafe sample's window**: landing both
inside runs 145-147 makes neither yield separable, which is why "both levers" was rejected.

*(Closed since the last close: the board-admission call — TAKEN and applied, D-428.
`click.appcast.io` — PROBED and REFUSED at 1 of 40; **do not build an appcast resolver**.)*

### Owed, and specifically NOT done

- **`grnh.se` redirect-following is BUILT and SHIPPED (D-429), and deliberately NOT ARMED.**
  `boardwatch companies discover-grnh` emits candidates; `companies import` is the arming act.
  **Arming must wait for run 147** or it contaminates the board sample's reading — the two board
  levers cannot be read apart inside one window. Owner's call.
- **Per-source thresholds are not set** — the owner's.
- **`perf` CI IS A FLAKY BOUND AND CAN REDDEN `main` ON AN UNRELATED COMMIT.**
  `tests/perf/test_top_perf.py::test_top_path_median_under_one_second` asserts a median < 1.0s over
  5 runs. `08d7b957` failed it TWICE (medians 1.0068, 1.0063) while `git diff 27a23a6a..08d7b957`
  touched **zero `.py` files** — the measured path was byte-identical to a CI-green parent. It is
  CI-only (not in `make check`), so it never blocks local work. Characterise the distribution before
  widening the bound; do not just re-run.
- **The `_reported` on-disk folder drain is NOT built** (D-427's deliberate deferral). The Report
  action hides a lead from the web queue but leaves its folder at top level. Parity needs a drain
  keyed on `reported_job_ids` exactly as `_skipped` is, touching `names.DRAIN_DIRS`,
  `reconcile_queue`'s disposition, `ReconcileReport` and the one-source drain set. **Do NOT reuse
  `_ineligible`** — reconcile pulls those back, because a reported lead's verdict is still
  `eligible`.
- **`delivered_unapplied` picks a job's winner by ARTIFACT RECENCY, not liveness** — see D-430. One
  live requisition is buried today.
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
