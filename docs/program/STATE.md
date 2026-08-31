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

**THE EXCLUSIVE-GROUP CONFLICT IS NOW PART-FIXED, AND THE PART THAT SHIPPED IS THE SMALL ONE.**
D-387 sized it at 8,429 `uncertain` evaluations. The owner ruled this session: **dissolve only on a
real disagreement where a straddle is genuinely ambiguous, and let a refinement decide otherwise.**
D-388/#289 removes `[citizenship_required, citizen_or_lpr_required, authorization_required]` from
`work_auth`'s `exclusive_groups` — a strength ladder, not a mutual exclusion — with **no engine
change**, so **`engine_version` does not move and no ledger drain is owed**.

**The first implementation of that ruling was WRONG, and only the corpus caught it.** Applying stage
1b's disagreement test (`MET` and `UNMET` both present) globally at stage 1 is attractive — it is the
same question asked of a different key, twenty lines below in the same function — and it regressed
**8 of the 1,034 corpus cases**: a wrong `ineligible` on obtainable-clearance documents and a **wrong
`met`** for a doctorate holder. `clearable_required` is a **disjunction** ("hold one, or be able to
obtain one"), an escape hatch, NOT a weaker rung; seven corpus cases say so by name. The engine
change was reverted whole. **The verdict-level count never moved, so nothing but the corpus would
have caught it.**

**What shipped is a CORRECTNESS fix, not a volume fix, and this file says so plainly.** At the engine
version derived from run 135, exactly **8 `uncertain` evaluations carry a work_auth ladder
dissolution, 4 at run 135's catalog, and all 4 comparable flip `uncertain` -> `ineligible`**. It also
removes an abstain **no fact could ever resolve**: a US citizen reading "Applicants must be US
citizens. Must be authorized to work in the United States." was `uncertain` under the group and is
now `eligible` with both rows `met`. Corpus 0 mismatches over 1,034.

**THE 96% IS STILL OWED.** `experience_years` still dissolves **3,876** evaluations. Honouring the
owner's ruling there needs a **second group kind in the catalog (`refinement_groups`), as versioned
DATA** — because the corpus proves the rule cannot be applied globally. That is the next
eligibility change and its design is recorded in D-388.

**A measurement trap that produced a false number, recorded so it is not repeated.** `rule_id` is
`family:pattern_id`, **not** `family:implies`, and the two coincide only for `experience_years`'
three group members. An arm derived by matching one against the other saw ZERO straddles in
work_auth, degree and clearance. Re-measured by running the PATCHED ENGINE directly (control 400/400
reproducing on `main`): **2,423 of 4,035, not the derived 2,500**, leaving 275 dissolved
(`experience_years` 250, `degree` 12, `work_auth` 12, `contract_not_fte` 1). **Price the code, not a
model of the code.**

**THE JOB-APPS LANE IS ARMED — and its source is `resumes/`, NOT `APPLY_QUEUE/`.** The owner
corrected this: `APPLY_QUEUE` is where a posting goes AFTER it is worked, so it is a
post-processing destination, and its newest cohort is 2026-08-29 because nothing has been processed
since. The daily discovery output is `resumes/<YYYY-MM-DD>/<Company_Title>/discovery_record.json`,
which is **exactly** the two-level walk the lane already does — so arming needed **no code change**.
Measured before arming: **190 readable records over 9 date folders, all `schema_version` 2, 49
direct-apply** (2026-08-30: 18, 2026-08-31: 45; only 9 of the 172 date folders carry a record, the
older ones predate the format). The per-date `_skipped/`, `_too_senior/` and `_eligibility_review/`
folders sit one level DEEPER than the walk, so job-apps' own reject verdicts are excluded by
construction, which is what D-386 designed. Armed in local `config.toml` and **read back through
`load_settings()`**; backup at `config.toml.bak-prejobapps-20260831`. **The watched first run is
still owed** — run 136 read its config at startup, so it does NOT include the lane.

**job-apps IS still running, and it is not producing into the queue.** `com.mitsheth.job-discovery`
fires 08:30 with `STAGE1_ONLY=1`; it ran today (`dedup_ledger.sqlite` mtime 2026-08-31 08:51:31) and
wrote `resumes/2026-08-31/` (45 records). Whether `STAGE1_ONLY` is meant to stop it short of
`APPLY_QUEUE` is an owner question, not a fault found here.

**Run 136 is a MANUAL run started 2026-08-31 12:11 and was still executing at session close.**
It matches the launchd invocation (`run --project --top 40`) and was launched **deliberately WITHOUT
`BOARDWATCH_HEARTBEAT_URL`**: a manual ping resets the dead-man's switch and would delay detection of
a failed 04:00 tick by ~7.5 h. **A reader comparing 136 to 135 will see no ping; that is intentional,
not an unclean run.** Scan completed 379 boards (305 complete, 43 unchanged, 31 partial — `partial`
12.9% early against run 135's final 16%, so the pacing trial's revert trigger is NOT firing), then
`lanes`, then eligibility re-extracting 2,597 postings because #288 moved `rules_hash`. **Slow by
design; not a fault.**

### Corrections to this file, from the repo (the ritual's rule)

1. **NO `boardwatch web` process is running.** Verified three ways (`pgrep -fl`, `ps aux`, `lsof`);
   the only local listener is `bridge`. **The machine rebooted 2026-08-31 12:04**, which is what
   ended both viewers. The two blocker rows below that described a running viewer, an apply-lane
   over-report of ~52, and an OPEN D-279 restart window are **stale and have been removed** —
   there is nothing to restart and no skew to carry.
2. **Run 135 was today's 04:00 CDT tick and it PREDATES #288** (store timestamps are UTC:
   09:00:03 -> 09:47:15 UTC; db mtime 04:50 local). #288 merged 11:57 CDT.
3. **Nine leftover worktrees were all merged PRs** (checked with `gh pr list --head`, never
   `merge-base`). Eight clean ones were removed on the owner's call; `bw-citizen` is preserved
   with its 8 dirty files.

### The seniority hold is 3 postings, not 5. It is dead, not deferred.

Re-measured with the real gate and catalog against the lane that **survives** D-383's drain:
`in_band` 146 / `above_band` **3** / `uncertain` 2 over 151, against 195/5/3 over the pre-drain 203.
The two that vanished are **already `closed`**, so #284 removes them for free. **Not built:**
`seniority_verdict` needs four inputs a conn-only store read cannot reach without pushing profile and
config into `store/`. Three postings does not buy a layering change.

---

## Next action

1. **Build `refinement_groups` for `experience_years` — the 96%, and the largest remaining
   precision item.** 3,876 evaluations. A second group kind in the catalog as versioned DATA:
   groups that dissolve only when their rows actually DISAGREE, against `exclusive_groups` which
   dissolve on presence. **The corpus proves it cannot be a global rule** (D-388): applied globally
   it regresses 8 cases including a wrong `met`. Needs its own schema, validation, engine branch,
   `rules.yaml` move, tests and measurement.
2. **Run the WATCHED first job-apps run.** The lane is armed and verified through `load_settings()`
   but run 136 predates the arming. Expect ~190 records read / 49 direct-apply. D-385's "first run
   watched" is still unsatisfied.
3. **Read out run 136 when it finishes**, and confirm #288's 262-posting effect against the live
   store. The 3-clean-post-fix provisional counter restarts with it (D-351 item 2 stands: not being
   chased). **The corpus-regression detector is still dark until ~run 138 (~2026-09-04)** — do NOT
   patch it.
4. **The two HELD recall patches: DO NOT SHIP. This is a measured answer, not a hold.**
   `.agent/2026-08-31d-session/WIP-*.patch`. Both build, both probe correctly, both are
   corpus-clean, and they move **ZERO verdicts over the 25,264 evaluations whose bodies carry their
   own target surfaces**. Their one row-level effect is an evidence-chain DEGRADATION. **Do not
   re-raise them as a recall opportunity.**
5. **`reports/abstain.STRUCTURALLY_UNDECIDABLE` is stale for
   `experience_years:scoped_years_minimum`** and it is NOT a one-line fix. D-319 made that rule
   decidable (55,520 `unmet` against 7,634 genuine unconditional abstains). Removing the entry would
   misreport those 7,634 as fixable. **Decide what membership MEANS before touching it.**

## Session 2026-08-31e — what shipped

| PR | what |
|---|---|
| **#289** | the `work_auth` restriction ladder stops being an exclusive group; the other four groups stay, each for a different stated reason (D-388) |

Also this session, no PR: the **job-apps lane ARMED** against `resumes/` (owner's corrected source),
**8 merged-PR worktrees removed**, and **run 136** started manually.

Previous session: **#288** two sponsorship recall fixes (D-387).

## Owner-gated — do NOT start or decide unilaterally

1. ~~Does job-apps keep running, or is it retired?~~ **ANSWERED 2026-08-31 — it keeps running.**
   See Next action 3. Both schedulers are armed: boardwatch 04:00, job-apps 08:30. Do not
   re-raise; the remaining judgement is only WHEN to build, not WHETHER.
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

| Phase | Build | Gate |
|---|---|---|
| P0 Instrumentation | **COMPLETE** | **MET** (D-030) |
| P1 Résumé artifact gate | **COMPLETE** | **MET** (D-032/033) |
| P2 Profile + keystone | items 1–7 shipped; item 8 NOT STARTED | **MET AS RECONCILED** (D-075) |
| P3 Unattended one command | **COMPLETE, INSTALLED, FIRING** once daily at 04:00 local (owner's call 2026-08-27; was ~3h under D-288). The agent is now a FALLBACK HEARTBEAT — Mit's ruling is to invoke a run manually as and when needed, so do not wait for the schedule | **MET** — 8 consecutive clean scheduled ticks (runs 71-78), verified from the `runs` table + funnels |
| P4 Craft gate | **COMPLETE** (under-fill fixed D-303; objective anti-slop 0 violations, non-vacuous) | **MET** — objective half certified AND the owner's blind craft review passed cleanly 2026-08-26 (all 5 judged worse were job-apps decoys; all 3 judged better were boardwatch) |
| P5 Eligibility decides | **COMPLETE** | **MET** — INELIGIBLE precision 16/16, 0 span violations |
| P6 Liveness + dedup | **BUILD COMPLETE** (D-110/111/113); leakage report shipped (D-283) | **MET — 4 of 4** (2026-08-27): liveness MET (D-281), leakage measurable over a true 7-day span and reading **0.00%**; see the clause table for the `exact_quad` caveat |
| 14-day acceptance | not started | **HELD BY THE OWNER (2026-08-27)** — the provisional pass was MET by runs 119-123, and Mit ruled to keep fixing precision first rather than start the clock. Starting it freezes eligibility, profile and the résumé gate for 14 days. **2026-08-28e: the provisional pass's remaining item — 3 clean post-fix runs — RESTARTED FROM ZERO**, because #218 bumps `rules_hash` and those runs are therefore pre-fix again. The P4 owner blind review is still PASSED (2026-08-26) and does not repeat. With runs on demand and Mit stepping back ~2026-08-31, that is 3 runs in ~3 days; **the trade (stricter eligibility now vs the pass possibly not closing before unattended operation) was raised to Mit and is his**. **2026-08-28f: #221 bumps `rules_hash` again, so the counter restarts again — and this is NOT being chased (D-351 item 2 stands: work comes first)** |
| P7 Breadth | **lane 1 (hiring.cafe) and Part 4b (LinkedIn) are BUILT AND ARMED and ran in run 122** (hiringcafe 70 attempted/56 resolved; linkedin 71/51) — the previous "not armed" text was stale. **Part 4a GitHub-lists discovery BUILT + LANDED (#149/D-296) and NOW PARTLY ARMED**: 97 boards imported 2026-08-27, ~765 candidates still capped. Remaining lanes not started | unlock MET (D-271/272) |
| *Gate A / Gate B* | *complete, merged* | ***MET*** — *has moved no program gate* |

### Gate P6 — MET, 4 of 4

The clause-by-clause table moved to `STANDING-FACTS.md` on 2026-08-28f: every clause is MET and
none has moved since 2026-08-27. Read it there before quoting the leakage figure — the `exact_quad`
caveat (D-294) is what makes 0.00% a structural reading rather than a clean one.

## Live blockers and carried gaps

| Item | Detail | Owner |
|---|---|---|
| **The `experience_years` group still reads a REFINEMENT as a CONTRADICTION — 3,876 evaluations** | D-388/#289 fixed the `work_auth` ladder half (4 of 4 comparable flip `uncertain` -> `ineligible`, corpus 0/1034, **no `engine_version` movement so no ledger drain**). **The 96% remains**: `experience_years`' `[total_years_minimum, range_years_minimum, scoped_years_minimum]` are PARALLEL BARS, and the owner ruled they must keep abstaining on a REAL straddle (met on one, unmet on another) while deciding otherwise. **That cannot be a global engine rule** — applying stage 1b's disagreement test at stage 1 regresses **8 of 1,034 corpus cases**, reintroducing a wrong `ineligible` on obtainable-clearance documents and a **wrong `met`** for a doctorate holder, because `clearable_required` is a DISJUNCTION not a weaker rung. It needs a second group kind in the catalog (`refinement_groups`) as versioned DATA. Arm A (empty every group) is 2,674 of 4,035; the measured disagreement arm is 2,423 of 4,035. **`rule_id` is `family:pattern_id`, NOT `family:implies`** — they coincide only for this family's three members, and a derived arm therefore reports false zeros elsewhere. Price the code, not a model of it | **next eligibility change** (design settled in D-388) |
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
| **hiring.cafe lane is DOWN; the HEADER LEVER FAILED and the remaining call is the OWNER'S** | **D-369/#245 shipped the search route's browser-navigation header set and run 133 is its readout: NEGATIVE.** Run 133 reproduced run 131's `SearchPageError` byte for byte (14 facets, 14 refusals), so **headers are ELIMINATED and that experiment must not be repeated.** D-368's other premises were already dead: the UA premise is FALSE (we have sent a Chrome UA since the lane shipped) and the volume premise did not survive the run log (run 128 spent ~28 requests; run 131 was refused on its FIRST request 14 h later). **What remains is the ENDPOINT — path-scoped protection on `/jobs/*`**: job-apps succeeds on `/`, our `/api/` calls succeeded every run through 128, our `/jobs/` calls have failed **14 of 14 on two separate runs**. That is a **compliance decision, not a repair** — robots.txt ALLOWS `/jobs/` and DISALLOWS job-apps' `?searchState=` form. **Still do NOT probe.** Half the lane coverage job-apps' edge comes from. **Second, smaller call:** ~196 refused requests over an unattended fortnight if the lane stays enabled (balanced; see Next action item 1) | **Mit** (the endpoint call, or send the drafted access request; and whether to leave the lane enabled) |
