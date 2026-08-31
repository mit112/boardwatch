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

**RUN 137 IS VERIFIED CLEAN, AND IT IS THE FIRST PRODUCTION RUN AT THE NEW ENGINE.** Started
manually 2026-08-31 19:45:42 UTC, finished 21:44:14 UTC, **`status='ok'` and exit 0 read from a
per-launch sentinel** — never from a notification and never from `SELECT status`, because
`runs.finished_at` precedes process exit. 379 boards attempted, **0 failed**; board coverage
**91.6%** with **0 dark / 0 unscanned / 0 unreadable**; 114,250 evaluated; **40 shortlisted -> 40
tailored -> 40 PDF** with all three cross-checks agreeing. `partial` 7.9% (run 136: 8.2%), so the
pacing trial's revert trigger is NOT firing. Sole error: **hiring.cafe 14 of 14 facets — the known
D-369 outage**, not a regression. Heartbeat deliberately not sent on a manual run; its absence is
intentional, not an unclean run. Numbers in `METRICS.md` (2026-08-31f).

**THE JOB-APPS LANE REACHED DELIVERY ON ITS FIRST ARMED RUN — that is the headline, not the
ingest.** `161 attempted · 18 resolved · 10 new companies · 28 refused by the cap`. **10 admitted
against a cap of 10, so `lane_new_companies_per_run` was OBSERVED FIRING** — verified, not merely
armed. All 18 bodies arrived INLINE, so the lane cost **2.5 s** against linkedin's **245.2 s**: it
reads local files and is nearly free. It admitted Apple, ByteDance, DeepMind, AWS, Akamai and five
others — employers no board slug can reach — and **4 of the 40 delivered leads are lane-sourced**
(Akamai, **Apple**, **DeepMind**, Dewpoint), confirmed through the `artifacts` table rather than the
run log. **Delivery split, stated precisely: Akamai reached the APPLY queue; Apple, DeepMind and
Dewpoint went to `_review`.** All four pass the US gate and all four are `uncertain`, so the split is
neither location nor verdict: they fall past `eligible` in `review_gate.classify()`, and Akamai alone
carries neither `eligibility_unconfirmed` nor `experience_unconfirmed`. By design (D-332).

**#290 + #291 REPRODUCE THEIR PRE-MERGE PRICING AT PRODUCTION SCALE (D-392).** Pinned to the
**112,593 posting_versions shared** by runs 136 and 137, both complete: **2,398 `uncertain` ->
`ineligible`**, 1 -> `eligible`, and **zero transitions of any other kind**. Against the affected
population the rate is **2,398 / 4,053 = 59.17%**, versus the pre-merge full-population pricing of
**2,423 / 4,035 = 60.07%** — population within 0.4%, rate within 0.9 pp, and **100% of flips inside
the affected population, so zero collateral movement**.

**Do not quote 48.9% as the comparator.** That figure is a **newest-first SAMPLE** of ~46% of the
population, baselined on D-388's branch, so it prices #291's MARGINAL effect; runs 136 -> 137 measure
#290+#291 COMBINED over the whole population. Comparing them invents a 10 pp overshoot that does not
exist. The full-population figure's identity was confirmed by measurement, not assumption: the same
predicate over the rows still stored at that catalog gives 3,979 + 56 = **4,035 exactly**.

**A null control for this class of change is STRUCTURALLY UNAVAILABLE — do not manufacture one.**
Inputs are reused on `(posting_version_id, profile_hash, rules_hash)` and evaluations are UNIQUE on
`(input_id, engine_version)`, so a run that changes nothing re-evaluates nothing: runs 134 -> 135
share **0** posting_versions and a "0 changes" reading there is 0-out-of-0. Validate the instrument
with a **reference contrast** instead (133 -> 134: 108,969 shared, 9.14% changed). D-392.

**job-apps IS still running, and it is not producing into the queue.** `com.mitsheth.job-discovery`
fires 08:30 with `STAGE1_ONLY=1` and wrote `resumes/2026-08-31/`. Whether `STAGE1_ONLY` is meant to
stop it short of `APPLY_QUEUE` is an owner question, not a fault found here.

### Corrections to this file, from the repo (the ritual's rule)

1. The previous revision carried the **same "Also this session, no PR: the job-apps lane ARMED…"
   paragraph twice**, with different tails. Removed in this rewrite; nothing else was lost.
2. **Run 137's config hash equals run 136's even though the lane was armed between them, and that
   is CORRECT.** `manifest.py` classifies `lanes_enabled`, the `lane_*` knobs and
   `jobapps_discovery_dir` (D-385 by name) as `_CONFIG_IRRELEVANT`: lanes are ACQUISITION, not
   judgement, and `policy_version` derives from `config_hash`, so classifying them IN would stale
   every permanent disposition the moment a lane is armed. Checked before it was reported as a gap.
3. The six soft detectors still sit **above** `_emit_morning` in `runner.py`; the ordering invariant
   survived the four PRs merged 2026-08-31e.

### The seniority hold is 3 postings, not 5. It is dead, not deferred.

Re-measured with the real gate and catalog against the lane that **survives** D-383's drain:
`in_band` 146 / `above_band` **3** / `uncertain` 2 over 151, against 195/5/3 over the pre-drain 203.
The two that vanished are **already `closed`**, so #284 removes them for free. **Not built:**
`seniority_verdict` needs four inputs a conn-only store read cannot reach without pushing profile and
config into `store/`. Three postings does not buy a layering change.

---

## Next action

**THE PROGRAM HAS A NEW SHAPE: absorb job-apps into boardwatch and retire it (D-393).** The full
sequenced plan, with every measurement behind it, is
`.agent/2026-08-31f-session/INVESTIGATION-next-session.md`. Read that before starting.

**Phase 0 — nothing to record; D-393/D-394 already carry the owner decisions.**

1. **SPEED — approved, independent of everything else, do it first (D-394).**
   (a) memoize `split_units` (`detect.py:73`, pure, called ~55x per posting on one body with TWO
   scopes); (b) parallelize `eligibility/preflight.py:175` with a **PROCESS** pool — regex holds the
   GIL — keeping `write_evaluation` serial and one-commit-per-batch resumability; (c) arm
   `pace_from_request_start`, **absent from the live config AND all four backups**, so the approved
   trial never ran. Expect the eligibility stage **75.6 min -> ~8-12 min** on a rules-change run.
2. **PER-LANE COMPANY CAP — approved.** Make `lane_new_companies_per_run` overridable per lane at
   `runner.py:576`: jobapps unlimited, **linkedin stays 10**, because lane-discovered ashby/greenhouse/
   lever companies become `watched=1` and would balloon the 379-board scan permanently. Adding a
   `Settings` field has FOUR gated sites. **This does NOT increase what reaches the queue** — only
   `--top 40` in the plist does, and that is still undecided.
3. **YIELD WORK, biggest first** (shares of job-apps' attributed `built` output, D-393):
   LinkedIn depth **46.5%** (lane exists, just throttled; port job-apps' query expansion) ->
   hiring.cafe re-pointed at the **SSR surface 17.9%** (`/?searchState=`, parse `__NEXT_DATA__`;
   **discovery only**, take `apply_url` and fetch the real JD) -> ingest the aggregator slice already
   on disk **24.2%** (indeed + jobright, zero network) -> register/arm the GitHub-lists lane **8.1%**
   (`lanes/github_lists.py` is BUILT but absent from `LANE_FACTORIES` and `lanes_enabled`) -> port
   `linkedin_direct_backfill.py`'s stub recovery (~92% of LinkedIn stubs, plain GET + browser UA).
4. **ONE QUEUE.** Import `APPLY_QUEUE/_applied/` (**64 folders**) into `hidden_applied` (built but
   STARVED) — the FOLDERS, not the stale `applications.csv`. Then the **935 active** folders, which is
   NOT a copy: they sit on Eightfold/iCIMS/Jobvite/Oracle/Rippling, boards with no adapter, against a
   CLOSED six-provider catalog.
5. **RETIRE job-apps ON EVIDENCE, last.** It keeps running until then (D-393).

### Owed, found this session, not yet scheduled

- **The jobapps lane's outage detector is UNSOUND.** Its docstring premise — "`attempted` is stable by
  construction" — is false: `attempted` tracks Mit's UNPROCESSED BACKLOG. It was 737 when the lane was
  designed and is **190** now purely because he drained the tree into `APPLY_QUEUE`. A zero reads as
  "Mit caught up", which is exactly what the detector was built to exclude. Replace with a STRUCTURAL
  check (source dir exists, holds >=1 date folder), never a record count.
- **Cross-source dedup gap.** **24 employers are double-listed and 222 open postings share a title**
  across a lane row and a board row. Only `exact_quad` suppresses and it folds in the body hash, so
  two sources can never collide: **zero cross-provider groupings in 130,989 jobs**. It has not bitten
  because job-apps' first 10 employers are unreachable by our boards; it will as the lanes ramp.
- **`reports/abstain.STRUCTURALLY_UNDECIDABLE`** — data precondition now met, design question open
  (see below).
- The ledger drain stays DECLINED (D-390); re-check the `built`/`skipped` split before any future drain.
- The two held recall patches at `.agent/2026-08-31d-session/WIP-*.patch` are **DO NOT SHIP** on
  measured evidence. The corpus-regression detector stays dark until ~run 138; do NOT patch it.

## Session 2026-08-31f — what shipped

Read-out and records only; no source changed. **Run 137 verified clean from its sentinel**, the
job-apps lane's first armed run measured end-to-end **through delivery**, #290+#291 confirmed at
production scale against the correct comparator, and **D-392** recorded so the vacuous control and
the wrong comparator are not repeated. #293 (D-391) landed during the session; its diff was verified
docs-only and `DECISIONS.md` checked entry-by-entry (314 -> 315, nothing dropped).

Previous session: **#290** (D-388), **#291** (D-389), **#292** (D-390), **#293** (D-391).

## Doctrine change — "breadth is last" is RETIRED (D-391, owner's call 2026-08-31)

The `CLAUDE.md` section is **deleted** and the live pointers in `PROGRAM.md` and `STANDING-FACTS.md`
are gone. It reasoned about an ASSUMED downstream; that downstream is instrumented now, so the
question is answerable with numbers per change instead of settled in advance by an ordering rule.
**Nothing replaces it** — input work is sequenced on measured evidence like anything else.

**The decision logs are append-only and were deliberately left alone**, so D-280, D-296, D-345 and
others still argue from the principle. **Meeting the phrase in an old entry does not make it
current** — D-391 is the reason. Still live, and stated where they belong: every quarantine needs a
drain designed in the same change; a cap never observed firing is unverified; the keystone invariant
is untouched.

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
| **hiring.cafe lane is DOWN; the HEADER LEVER FAILED and the remaining call is the OWNER'S** | **D-369/#245 shipped the search route's browser-navigation header set and run 133 is its readout: NEGATIVE.** Run 133 reproduced run 131's `SearchPageError` byte for byte (14 facets, 14 refusals), so **headers are ELIMINATED and that experiment must not be repeated.** D-368's other premises were already dead: the UA premise is FALSE (we have sent a Chrome UA since the lane shipped) and the volume premise did not survive the run log (run 128 spent ~28 requests; run 131 was refused on its FIRST request 14 h later). **What remains is the ENDPOINT — path-scoped protection on `/jobs/*`**: job-apps succeeds on `/`, our `/api/` calls succeeded every run through 128, our `/jobs/` calls have failed **14 of 14 on two separate runs**. That is a **compliance decision, not a repair** — robots.txt ALLOWS `/jobs/` and DISALLOWS job-apps' `?searchState=` form. **Still do NOT probe.** Half the lane coverage job-apps' edge comes from. **Second, smaller call:** ~196 refused requests over an unattended fortnight if the lane stays enabled (balanced; see Next action item 1) | **Mit** (the endpoint call, or send the drafted access request; and whether to leave the lane enabled) |
