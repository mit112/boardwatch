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

### Session 2026-09-02d: the buried live requisition is FIXED, LinkedIn gets a COMPANY axis, the `_reported` drain closes D-427, and the `perf` flake is CHARACTERISED as a load detector

Reasoning: **D-432**, **D-433**, **D-434**, **D-435**. Numbers: `METRICS.md`
(Session 2026-09-02d).
**No run** — the 04:00 tick produces run 145.

**1. THE BURIED LIVE REQUISITION IS FIXED (D-432, PR #336).** `delivered_unapplied` picked a
canonical job's winner by ARTIFACT RECENCY, so a dead lane copy tailored after the employer's own
live requisition decided the job: `closed_job_ids` reported the JOB closed and `reconcile_queue`
filed a live lead under `_closed`. Liveness now decides; recency only breaks its ties.
**THE CORRECTION RAN OPPOSITE TO THE ONE COMMISSIONED.** The handoff said D-430's "1 job" was wrong
and the figure was 16. Joined through the DELIVERED ARTIFACTS — the only postings the queue can
offer — it is **1**, eBay 35249, exactly the job D-430 named. The 16 counted every posting on a
canonical job and ranked by `last_seen_at`; the rule ranks by `artifacts.created_at`.
**Completeness measured separately:** 101 jobs have every delivered posting closed and **0** hold a
live posting anywhere, so no residual class exists that a winner rule cannot reach. The buried lead
walks out on run 145 by itself — reconcile precedes sync and `_entry_for` falls back to the by-job
index. **No `engine_version` bump, no ledger drain, no migration.**

**2. LINKEDIN GETS A COMPANY AXIS — TRACK 2 BUILT AND DISARMED (D-433, PR #337).** Every LinkedIn
search asked WHAT and WHERE, never AT WHOM. **342 absent postings sit at 65 employers boardwatch
ALREADY WATCHES.** **The plan's own shape was refuted by arithmetic before it was built**: 14
profile terms x 1,812 stored names = 25,368 cells, which at 83 runs/14 days is a **358-day**
rotation. Owner's call with four shapes priced: **1 term x 443 watched = 443 cells, 12/run, a full
pass every ~37 runs (~6.3 days)** — the only shape readable before the 2026-09-09 re-measure.
`lane_company_combos_per_run` ships at **0 (OFF)**. **It was armed on 2026-09-03 and DISARMED the
same night — the premise is REFUTED on live measurement (D-437, and Next action 0). The code stays
merged and inert.**
**The plan's "nothing in `lanes/linkedin.py` changes" was WRONG** — `card_nodes` treats zero cards
as a STRUCTURAL failure, correct for a facet and backwards for a cell naming one employer, so
folding them in would have pushed reported failures ~0 -> ~11 every run and buried the outage
signal. **The registration sites are FOUR and the fourth is `tools/generalization/snapshots.py`,
which holds TWO dicts** (`EXPECTED_SETTINGS_DEFAULTS` and `SETTINGS_FIELD_CLASS`) — not the
USE site, which is not a registration at all. **What is new is the ORDERING**: R10 runs at
the FIRST `make check` target, so a missed snapshot entry produces no pytest output and
reads like a broken gate rather than a missing row. Corrected by the peer session.

**3. THE `_reported` FOLDER DRAIN CLOSES D-427's DEFERRAL (D-434).** A reported lead was hidden
from the web queue but its folder stayed at the TOP LEVEL, so it was still in the pile the owner
works from. **The site a reconcile-only reading misses**: `_sync_queue` runs reconcile AND sync in
one call, so without withholding the reported job from `delivered_unapplied` the sync mints the
folder again while the reconcile count reads a healthy 1. Ranked below `applied`/`skipped`, above
`closed`. `_ineligible` refused — reconcile pulls those back the moment the verdict clears.

**4. THE `perf` CI FLAKE IS CHARACTERISED AND IT IS NOT A CODE SIGNAL.** 15 local samples of the
median-of-5: **quiet mode 0.373-0.414 (n=4), loaded mode 1.336-1.675 (n=11), and NOTHING between
0.414 and 1.336.** The distribution is BIMODAL with a 0.92 s empty gap and **the 1.0 s bound sits
inside the gap**. It is a machine-load detector, not a code-speed guard. The two CI failures read
1.0068 and 1.0063 — inside a gap local runs never occupy — which says CI's LOADED mode sits at ~1.0
rather than ~1.5 (4 vCPU runner vs a 10-core Mac), so on CI the bound sits ON the loaded mode's
centre: a coin flip whenever the runner is contended, which with 4 shards x 3 versions it usually
is. **FIXED (D-435): `TOP_PATH_CEILING_SECONDS = 2.5`**, derived from that distribution — it
clears the worst observed loaded median by ~49% and still catches a 6x regression against the quiet
mode. **Asserting the MINIMUM was tried and REFUTED by the same samples**: 10 of 15 would still fail
a 1.0 s minimum against 11 of 15 for the median, because under sustained load ALL FIVE iterations
are slow. Stated as a relaxation: detecting a 2-3x regression is what is given up.

**5. THREE REVIEWS BEAT THREE GREEN GATES, AGAIN.** #336 gated green with three caught mutations
and a review found four defects — including a stale mechanism paragraph in the ARMED
`apply_lane_drought`. #337 gated green with nine of ten mutations caught and a review found six,
including the `card_nodes` defect above. **None was reachable by mutation, because none is a
branch.** Two further lessons: a mutation of mine was MIS-SPECIFIED (it mutated the raw column,
where an unverifiable posting still reads `open`) and would have been read as a hole in the pin;
and one of my tests was VACUOUS (byte-identical output under the term cap) and only the campaign's
control revealed it. **A review's finding can also be OVERSTATED**: #337's largest said the company
ring was broken for "a large and growing share" of rows; re-measured, 145 of 453 watched names
equal their slug and almost all are CORRECT (`Anthropic`, `OpenAI`, `Airbnb`), so the fix is narrow
— a PATH is refused, a separator is not.

## Next action

**0. TRACK 2 IS REFUTED ON LIVE MEASUREMENT AND IS DISARMED. DO NOT RE-ARM IT.**
The owner armed `lane_company_combos_per_run = 12` on 2026-09-03; it was **dry-run against the live
host before the first tick and disarmed the same night at 01:34** (verified through
`load_settings()` and `config.toml`). Reasoning and the numbers: **D-437**.

**The central premise was false and had never been probed.** A quoted company name is NOT a company
filter on LinkedIn's guest endpoint — it is a relevance-ranked keyword. Running the exact 12 cells
run 145 would have issued, through the same builder and ring: **4 of 120 cards on target (3%)**.
`"Tailscale" software engineer` returned DoorDash, OpenAI, Reddit and Scale AI and **zero**
Tailscale; `"NBCUniversal" software engineer` returned Microsoft, Netflix and NVIDIA and **zero**
NBCUniversal.

**And the cap cost is the opposite of what D-433 estimated.** Those 12 cells present **78 distinct
companies, 61 of them new**, against a cap of 50 — and cells sit BEFORE the hub nets in the
interleave. Arming it takes **all 50 slots and leaves the hub nets zero**, so it is a straight
regression to the LinkedIn lane's actual breadth mechanism. D-433's "at least one slot per cell,
upper bound not established" was right to flag the gap and far too optimistic about its size.

**A CONTROL WAS NECESSARY AND THE FIRST READING WAS ENCOURAGING AND WRONG.** Six well-known
companies read **~20%** on target with result sets nearly disjoint from an unfaceted control, which
looks like the company name working. All twelve read **3%** — the six-company sample was biased
toward employers who post heavily on LinkedIn, and the ring is not.

**The obvious rescue is closed too, and it was probed.** LinkedIn's real filter is
`f_C=<numeric company id>`, and the guest fragment serves **no numeric company id** — a card carries
`urn:li:jobPosting:<id>` and a company SLUG only. Filtering by employer would need a slug-to-id
discovery mechanism on another LinkedIn surface, which is a **widening of D-290 and the owner's
call**, not a probe.

**The 342 already-watched misses are therefore STILL OPEN and the LinkedIn residual has no proposed
mechanism again.** Do not re-arm Track 2, and do not propose per-company cells without naming a
mechanism that actually filters by employer. The code stays merged and inert at `0`.

**1. READ THE 50-BOARD SAMPLE'S YIELD OVER RUNS 145-147, THEN DECIDE THE REMAINING 282.** Unchanged
(D-428; watched 403 → 453). Population 332 boards / 471 postings, **1.42 in-window postings per
board**; the remaining 282 cost ~15 min/run. Reversal:
`companies-prehcsample-20260902-183019.csv`.

**2. RE-MEASURE GATE 1 AROUND 2026-09-09** (D-424) with
`.agent/2026-09-02-session/per_source_recall.py`. **The residual is LinkedIn alone**, and Track 2 is
the only lever that has moved since — which is why arming it (item 0) belongs before this, not after.

**3. SET PER-SOURCE THRESHOLDS** (owner). Framing DECIDED: option D then C — decompose LinkedIn
first (**done**, D-431), then bar on `lane-only` exposure rather than recall. The numeric level is
still the owner's.

**4. TRACK 1 — admit the 92 already-admissible LinkedIn boards** (382 postings, ~4.9 min/run, no new
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
