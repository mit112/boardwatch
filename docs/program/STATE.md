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

### Did session 2026-09-01f reach its goal? PARTLY — the number moved by ONE POSTING, and the session's real product is that the goal itself is now priced

**The goal, in the owner's words: "ensure that we are finding all the jobs that Job Apps is
finding, so we can retire Job Apps."** That is gate 1 (D-399): independent coverage of job-apps'
eligible set **>= 80%**.

| | |
|---|---|
| gate 1 at session start | 22.2% (independent 48 of 216) |
| **gate 1 at session end** | **22.7% (independent 49 of 216)** |
| postings gained | **+1** |
| gate 3 anti-degradation | 49 vs baseline 44 — HELD (record 49) |

**RUN 141 HAPPENED and was read out in full** (D-417) — unlike last session, which shipped
capability and could score none of it.

### THE MOST IMPORTANT THING THIS SESSION PRODUCED IS AN ARITHMETIC, NOT A FEATURE

Priced end to end for the first time, against a bar of **173 of 216**:

| lever | postings | state |
|---|---:|---|
| Indeed armed (steady state, ~7 daily runs) | +35 | built, DISARMED, blocked |
| tier-A company admission | +3 | measured, owner-gated, NOT applied |
| JSON-LD resolver lane | +2 | built; **measured to deliver 1 by run 2, both by ~run 6** |
| Oracle HCM search lane | +6 | not built |
| Amazon / Rippling / Eightfold / BambooHR | +4 | not built |
| `gh_jid` resolver | +2 | built, PARKED (D-415) |
| **everything above, all of it** | **+52 → 101 of 216 = 46.8%** | |

**Every identified, buildable lever outside LinkedIn lands at 46.8%.** The whole remaining path to
80% runs through linkedin.com's 77 misses (35.6 points) — and **57 of those 77 are employers
boardwatch has never seen at all**, dominated by staffing agencies, consultancies and board
reposts that plausibly have no ATS board to admit. Reaching them means acquiring LinkedIn postings
at volume, from the worst-quality measured source (13.4 eligible per 1,000 open, against 33.4 for
curated boards and 45.9 for hiring.cafe).

**So gate 1 >= 80% is NOT REACHABLE by the levers currently identified.** That is an owner
question, not an engineering one, and it is question 1 below.

### The cap theory: direction confirmed, sizing refuted

The LinkedIn company cap went 10 -> 50 and geo nets shipped. Refusals **ROSE 344 -> 617** while the
lane admitted exactly the new cap. Admission still binds — D-411 was right about that — and
relieving it fivefold bought **+1 posting**. **Do not raise that cap again on this evidence**
(D-417). Fourth time this program has sized work off what a rule can MATCH rather than what it
would FIX, after D-415, D-413 and D-412.

The rotation contract HOLDS, verified against live config and profile rather than a fixture: 98
cells at 33/run, `2c <= m` holds, consecutive overlap 0, **union of three consecutive runs 98 of
98, no repeats.**

### What shipped, and what did not

**MERGED: #329 only** — Wave 0 (D-416): `LaneContext` plus `lane_seeds`, the durable
discoverer→resolver handoff. Reviewed, DO-NOT-SHIP'd on two structural blockers, fixed, green.

**FIVE BRANCHES BUILT AND NONE MERGED** (D-418). Each gated green with mutation-pinned guards, was
reviewed, had a fix round, and was **re-reviewed** — and all five failed the second pass on NEW
findings the fix rounds exposed:

| PR | branch | where it stands |
|---|---|---|
| **#334** | T1 `fix/lane-observation-fidelity` | D-414(a)'s two blockers CLOSED. **3 new blockers**: freezing the body leaves JD v1 deciding forever on an unwatched lane-first company; `remote_policy` has the same permanent false-drop path; a secondhand UPDATE can record a false `exact_quad` |
| **#333** | T2 `feat/jsonld-resolver-lane` | 4 of 6 blockers FIXED. **2 new**: a seed that RESOLVED at attempt two is written back unresolved at three and excluded forever; every exception becomes `extracted_empty` |
| **#332** | T3 `feat/indeed-tenant-seed` | blocker fixed, recurred through a DNS-root dot, fixed again by hand. Awaiting a third gate |
| **#331** | T5 `feat/lane-body-ingest-precondition` | 4 of 5 FIXED. **1 new blocker: a FOURTH eligibility seam** — the `eligibility label` oracle handshake, where a Jobright page was reproduced becoming an `ineligible` ANSWER-KEY row |
| **#330** | T4 `fix/vice-president-provenance` | verdict-neutral over 93,236 titles, precedence FIXED. The **web UI suppression is still present**, so the corrected reason does not reach the user |

**The structural lesson (D-418): in three of five, the FIX CREATED THE NEXT FINDING**, each by
removing a bad behaviour without supplying what it stood in for. When a fix withdraws something
downstream depended on — a refresh, a retry, a re-check — **name what now supplies it, in the same
change.**

**And the method finding (D-419): six branches, six first-round DO-NOT-SHIPs, and every one turned
on a CLAIM the code did not honour.** Not one finding was a failing test. A green gate cannot see a
false recorded claim, and three of the six had already been ACTED ON. Reviews cost no gate time.

## Next action

**1. FINISH THE FIVE OPEN PRs.** Each needs ONE more round, not a rewrite; every finding is
recorded in `.agent/2026-09-01f-session/reviews/` with file:line and a minimal fix. Order matters:

- **#333 (T2) merges BEFORE #332 (T3).** T3 produces `lane_seeds` rows and T2 is the only consumer;
  landing the producer first is a bucket with no drain. Indeed is disarmed so nothing can produce
  today, but do not arm it until the resolver is merged AND armed.
- **#334 (T1) gates arming Indeed** together with D-414(b).

**2. THEN ARM INDEED — the cheapest 16.2 points on the board, and no new discovery work.** Needs
D-414(a) (#334) closed, D-414(b) (an `indeed` row in `lane_new_companies_per_run_overrides`), and
T2's resolver merged. **Expect a FRACTION on the first armed run**: the lane's window is 24h and
the 35 misses spread 3/6/17/3/6 by cohort day, so the full figure takes ~7 daily runs. Reading the
first run as failure would be wrong.

**3. PUT QUESTION 1 BELOW TO THE OWNER WITH THE 46.8% ARITHMETIC.** Do not build more first — three
of four sizings in this program have counted the wrong thing, and this is the first one that prices
the whole remaining gap.

### Owed, and specifically NOT done

- **The primary tree is on `8069007a`, one merge behind `origin/main` (`f7b5b56d`).** It was NOT
  pulled because **run 142 (the 04:00 tick) was in flight off its editable venv** and a pull swaps
  code and `rules.yaml` under a live run. **Pull it once run 142 finishes.**
- **Run 142 has not been read out.** It ran on `8069007a`, i.e. pre-Wave-0 code, so it measures the
  same configuration as run 141.
- **Tier-A admission is NOT applied.** 3 admissible boards (Motorola Solutions, Keenfinity, Bosch
  Group), worth at most 1.4 points. Candidate file ready at
  `.agent/2026-09-01f-session/staging/t6/tierA-candidates.yaml`. `companies import` is a live-store
  write and the owner has not confirmed it.
- **`lane_seeds` has no "seeds no resolver claims" report.** `attempts` bounds a seed something has
  TRIED; a seed nothing ever selects is never attempted, never aged out, and invisible.
- Everything in the previous session's owed list that this one did not touch.

## Owner-gated — do NOT start or decide unilaterally

0. **NEW, AND IT IS NOW THE PROGRAM'S BIGGEST OPEN QUESTION: gate 1 >= 80% is not reachable by any
   lever currently identified.** Priced end to end (D-417, METRICS 2026-09-01f), everything
   buildable outside LinkedIn lands at **46.8%**. The remaining path runs entirely through
   linkedin.com's 77 misses, and **57 of them are employers with no ATS board to admit** —
   staffing agencies, consultancies and board reposts. Three options, and only the owner can pick:
   **(a)** a much larger LinkedIn acquisition, accepting a measured 2.5-3.4x worse
   eligible-per-posting rate and the corpus growth behind it; **(b)** accept that those 57 are a
   class boardwatch will not serve and **move the bar** — D-399 set 80% before any of this was
   measured; **(c)** a different discovery source for that population. **Do not build more toward
   80% before this is answered.**

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
- **P7 Breadth**: hiring.cafe, LinkedIn and GitHub-lists lanes are built and armed; **`indeed` is
  built and DISARMED** (D-414). Remaining tier-D lanes not started (D-413 ranks them).
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
| ~~**hiring.cafe lane is DOWN**~~ **CLOSED — run 138 reports NO hiring.cafe error**, the first clean run since 129, ending a 14-of-14 refusal. The lane was re-pointed at the SSR surface (#304, D-397) and resolves bodies through the EMPLOYER's own board, so its postings land under greenhouse/lever/ashby/workable and NOT under a `hiringcafe` provider — do not read that absence as failure. Historical detail follows | **History, kept only so the dead ends are not retried.** The header lever FAILED (D-369/#245, run 133 reproduced the refusal byte for byte) and headers are ELIMINATED — do not repeat that experiment. The UA and volume premises were both false. The cause was the ENDPOINT: our `/jobs/` calls were refused 14 of 14 while job-apps succeeded on `/`. **D-393 decision 1 reversed the do-not-probe hold on Mit's explicit call**, and #304 re-pointed the lane at the SSR surface, which is what run 138 proves works | **CLOSED** |
