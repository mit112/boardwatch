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

### Session 2026-09-02: the five branches merged, Indeed is ARMED and has RUN, and gate 1 was replaced by a different instrument

**GATE 1 IS NO LONGER A COVERAGE PERCENTAGE.** The owner withdrew both the 80% bar (D-399) and the
"cover most of what job-apps does daily" wording that briefly replaced it. **It is now PER-SOURCE
RECALL, a rate** (D-421). Do not re-derive either retired bar.

**Why**, in the owner's words: *"what I want you to compare is the same methodology or the sources
that job apps have"* — job-apps' output grows daily so no two readings share a denominator, and he
had already processed past discovery into the apply queue. **The old gate was worse than unstable:**
it counted `eligibility` outcomes `eligible` (1,229) + `protected_applied` (45) and **excluded
`moved` (3,963 — the apply-queue set, three times larger)** and `review` (2,484). `eligible` and
`moved` only exist once he works a cohort, so 08-31, 09-01 and 09-02 carry zero of both. **Three of
the seven days contributed nothing.** The "216" tracked his activity, not boardwatch's coverage.

**First reading of the new gate — run 143, 14d window, 21,863 job-apps postings:**

| | value |
|---|---|
| **recall, drawn-from sources** | **4,913 of 20,653 = 23.8%** |
| employer's own board (lever/ashby/greenhouse/workday) | **94–100%** |
| aggregator + search (linkedin 32.5%, hiringcafe 17.0%, indeed 12.6%) | **12–33%** |
| **lane-only — dies the day job-apps stops** | **7,091 (32.4%)** |
| never held at all | 9,715 (44.4%) |
| **independent if job-apps stopped today** | **5,057 = 23.1%** |
| source coverage | **94.4%**, or 99.6% excluding the deliberate jobright refusal |

**The split is binary and falls on MECHANISM, not effort.** Reading the employer's own board gives
~100% recall; reading an aggregator gives 12–33%. **Source coverage is essentially solved** — only 15
of job-apps' 33 registered sources produce anything, and boardwatch draws from sources covering
94.4% of its volume. Gate 3 HELD at 49 (baseline 44). **No numeric threshold is set, deliberately:**
one number averages a solved mechanism against an unsolved one, which is how 80% hid that the
direct-ATS half was already done. Setting it per source is the owner's call.

### Run 143 — the first armed run

379 boards / 290 complete / 54 unchanged / 33 partial / 2 failed, 41m59s. **31,350 postings seen**
(142: 21,944), **2,894 new** (1,292), corpus 122,917. Verdicts **139 eligible** / 2,126 uncertain /
1,566 ineligible. 95 leads delivered. Board stage 379 boards in 20m11s = **3.2s per board**, which
is what auto-watch growth costs on every future run.

| lane | attempted | resolved | new companies | refused by cap |
|---|---:|---:|---:|---:|
| linkedin | 1,564 | 273 | 50 (cap) | 463 |
| **indeed** | **513** | **83** | **25 (CAP)** | **359** |
| jobapps | 432 | 237 | 46 | 0 |
| hiringcafe | 127 | 45 | 8 | 0 |
| jsonld | 0 | 0 | 0 | 0 |

**#331's body precondition fired in production:** 12 bodies withheld as "not the employer's own
text" — all 12 from `jobright.ai`, all ingested by the `jobapps` lane, `h1b sponsor likely` in 9 of
them, against 122,917 checks (0.01%, so precise rather than over-firing). **The contamination route
was job-apps, not a jobright lane** — refusing that lane never kept jobright's judgments out;
ingesting job-apps put them in. That is the sharpest argument for retirement the program has.

### `lane_seeds` fills to 773, and 85.9% of it is unreachable (D-422)

Zero → **773 rows in one run** (indeed 683, jsonld 90), **0 resolved, 0 attempts**. The
`jsonld → 0 attempted` is lane ORDERING, not a defect: the resolver runs before the producer and the
table was empty. **Run 144 must confirm the drain** — the handoff is unproven end to end until one
does. **The real defect: only 109 of 773 (14.1%) are claimable by any resolver's host catalog; 664
(85.9%) across 197 hosts are selected by nothing**, and `attempts` cannot bound them because an
unselected seed is never attempted. `grnh.se` (109) is the cheapest win — Greenhouse's own shortener,
and boardwatch already handles greenhouse. `eeho.fa.us2.oraclecloud.com` (Oracle HCM) and
`lockheedmartin.eightfold.ai` (Eightfold) are D-417's unbuilt levers whose seeds are already
arriving.

### The job-apps discovery tree is only a QUARTER ingested — measured 2026-09-02

The `jobapps` lane walks **exactly two levels** (`resumes/<date>/<posting>/`) and is deliberately
non-recursive so it cannot reach `_skipped/<reason>/`, whose directory names are job-apps' own
verdicts. **That intent is right** — reading them would inherit job-apps' judgments, the coupling
D-421 measured. But the depth limit excludes two further buckets as collateral. Confirmed through a
second path, not from reading the code: the tree holds exactly **432** `discovery_record.json` files
at the lane's depth and run 143 logged `lane jobapps → 432 attempted`.

| bucket | records | status |
|---|---:|---|
| lane's depth (top level per date) | **432** | read; **239** pass `is_direct_apply` |
| **`_eligibility_review`** | **1,374** (1,357 parse) | **MISSED — unintended.** 669 pass the filter |
| `_skipped` | 16,918 over 174 reasons | skipped by design |
| `_too_senior` | **0 records** (49,662 folders, each with `job_description.txt` + an apply URL) | unreachable by this lane |

`_eligibility_review` records are `schema_version: 2` with keys identical to what the lane reads —
fully readable, out of reach only by depth. **Root cause is a shape mismatch:** the lane's docstring
describes the tree as `<queue>/<ATS>/<posting>/`, so it was written expecting an ATS name at the
middle level; `resumes/` puts a DATE there and job-apps files its triage buckets at that same level,
one deeper than the walk goes.

**`_skipped`'s 174 reasons are NOT uniform in risk, which bounds any future decision to mine it:**
~45% is job-apps' own ROLE TAXONOMY (`non_swe_*`, 7,640 — and #330 corrected boardwatch's own role
gate this morning for the same class of error), ~28% is PROFILE-DEPENDENT eligibility
(`min_N_years_experience` ~3,100, `clearance_required` 589, `no_sponsorship`/visa ~330,
`international_location` 327, `senior_title`/`senior_level` 420), and only ~17% is objective posting
fact (`stub_jd` 1,922, `discovery_blocked_header` 606, `junk_folder_*` 373, `posting_closed`).
**Only that last class is safe to take on job-apps' word.**

**OWNER'S CALL (2026-09-02): harvest ONCE, build NO mechanism.** job-apps is being retired, so after
a certain date there is no more of this content and a permanent ingestion path would be dead code.
Process the top level plus `_eligibility_review` once and keep the eligible ones. Do **not** re-decide
`_too_senior` or `_skipped` through boardwatch's gates — job-apps' verdict is taken at its word
there. **Ingesting once is itself the record that stops re-processing**, because `posting_identities`
and the disposition ledger already make a second encounter cheap; no suppression list is needed, and
that is why none was built.

### Applied this session

- **Tier-A admission APPLIED** (owner-confirmed): 3 boards, watched **387 → 390**. Backed up first —
  `companies-pretierA-*.csv` (the exact reversal artifact) and a 5.5 GB `VACUUM INTO` snapshot.
- **Indeed cap raised 25 → 50** on the owner's call and on the 25-admitted/359-refused reading.
  **Carrying D-417's caveat: a binding cap is not proof that relieving it helps** — LinkedIn's went
  10 → 50 and bought ONE posting. Verify yield on runs 144/145 before raising again.
- **jobright company-discovery probe: REFUSED on measurement, against my own proposal.** Of 501
  employers, 373 unseen, only **44 (11.8%)** have a resolvable board (62 of 523 postings), 329
  (88.2%) none at all — and all 44 were discovered via hiringcafe/legacy/zapply/simplify, **not one
  via jobright**, so the reachable part needs no jobright lane.

## Next action

**1. RUN THE ONE-TIME job-apps HARVEST, AND TAKE THE SEED-DRAIN CONFIRMATION WITH IT.** Both need
the lane stage, so one `--no-scan` run serves both (~22 min; `--no-scan` skips only the 20-minute
board stage, lanes still run). Vehicle, all of it reverted afterwards so nothing persists:
`jobapps_queue_dir` → a staging directory of 79 symlinks to each date's `_eligibility_review`
(verified against the lane's own reader: 1,357 records), plus a TEMPORARY working-tree addition of
`linkedin` to `_DIRECT_APPLY_SOURCES` (no test pins that set) which newly ingests **877** LinkedIn
records — 686 from `_eligibility_review` and 191 from the top level — that the closed set drops
because boardwatch runs its own LinkedIn lane, a lane D-421 measures at only 32.5% recall. Expect
#331 to withhold the ~176 jobright-sourced bodies, correctly. **Revert both, then re-run the gate.**

**2. READ OUT RUN 144 AND CONFIRM THE SEED DRAIN.** `lane jsonld` must attempt the 109 claimable
seeds. If it attempts 0 again, the handoff is broken and not merely ordered.

**3. BUILD THE "SEEDS NO RESOLVER CLAIMS" REPORT** (D-422). It is the one thing standing between a
durable handoff and a silent 664-row leak, and it now has a first reading to build against.

**4. FOLLOW `grnh.se` REDIRECTS INTO THE EXISTING GREENHOUSE HANDLER.** 109 seeds, no new adapter,
no new vendor posture question.

**5. SET PER-SOURCE THRESHOLDS** (owner). The instrument exists and has a reading; the bar does not.

### Owed, and specifically NOT done

- **Per-source thresholds are not set** — that is item 4 and it is the owner's.
- **The recurring delivery `QueueConflictError` on posting 131368** has been in every run since 140
  and is still unfixed.
- **hiring.cafe has one unexplained post-fix failure** (run 142). #304 worked; 130–137's failures all
  predate it. Not a regression and not chronic flakiness — see the blocker table.
- **T1's concurrent case-variant duplicate race** — deferred, pre-existing, worst case a dead-weight
  row. Fix is a `(provider, lower(slug))` unique index plus a reconcile.
- **T3's exotic hostnames** — unicode-dot/fullwidth IDN and legacy IPv4 can still store an
  undrainable row. Dead weight only.
- A few T4/T5 test docstrings still carry round-3 framing. SHIP-approved; no assertion depends on
  them.

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
  ARMED** (D-420; `indeed` capped at 25 new companies/run). **hiring.cafe is armed but currently
  FAILING** — see the blocker table. Remaining tier-D lanes not started (D-413 ranks them).
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
| **hiring.cafe: ONE unexplained POST-FIX failure (run 142) — and D-420 recorded two wrong framings before this one.** #304 (`11a1ae95`) merged **2026-09-01T07:56:34Z**. Against that boundary: **130, 131, 133, 134, 135, 136, 137 all FAILED and all seven PREDATE the fix** (132 ok, a single unexplained point); post-fix **138, 139, 140, 141, 143 ok** and **142 is the only failure**. **So #304 WORKED** — this is neither a regression nor chronic flakiness. Not time-of-day: 138 also started 09:00Z and passed. **METHOD LESSON, which cost two wrong entries in one session: date a behaviour claim against the COMMIT that changed the behaviour, not against a run streak — a streak has no denominator until you know when the code changed.** Do NOT retry the eliminated dead ends: the header lever failed twice (D-369; run 133 reproduced the refusal byte for byte) and the UA and volume premises were both false. | **watch** |
