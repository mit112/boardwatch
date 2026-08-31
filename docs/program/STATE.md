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

**THE ENGINE READS A REFINEMENT AS A CONTRADICTION, and that is now the biggest measured precision
item on the board.** `engine.py` stage 1 treats two distinct `implies` values from one
`exclusive_groups` entry as a CONFLICT and rewrites every row in that group to `unknown`. The
`work_auth` group is `[citizenship_required, citizen_or_lpr_required, authorization_required]`, so
this document resolves `uncertain` with both rows `unknown` — on `main`, today, with no patch:

    "Applicants must be authorized to work in the United States.
     A natural-born U.S. citizen is required."

Those sentences are not in conflict. Citizenship is strictly STRONGER than authorization; the second
refines the first, and a decisive `unmet` is discarded. The same shape sits in `experience_years`
("5+ years of software engineering experience" plus "3+ years of Python" is two requirements, not a
contradiction), in `degree` and in `clearance`. `rules.yaml` says of the experience group that "the
regexes are tuned so the common forms fire exactly once; the group is the safety net."

**Sized, read-only, at the engine version DERIVED from run 135 (`1+6a9fb2164f5b`, 222,614
evaluations): 8,429 of 124,980 `uncertain` evaluations carry a conflict-dissolved row, and NOT ONE of
them has any other `required` row already `unmet`** — so for each of the 8,429 the dissolution is the
only thing between it and a decided verdict. Counted again through a different path (re-run with
every family's `exclusive_groups` emptied, reading the frozen JD and the stored profile snapshot and
policy out of the store), **2,674 of the 4,035 comparable at the current catalog — 66.3% — flip
`uncertain` -> `ineligible`**, with the control reproducing the stored verdict on 0 of 4,035 failures. Full numbers, method and caveats: D-387 and
`.agent/2026-08-31d-session/FINDINGS.md`. **One `engine_version` spans TWO `catalog_version`s here
(4,035 current / 4,394 stale), so filter on the catalog, not only the engine.**

**AND IT IS 96 PERCENT AN `experience_years` PROBLEM — which is why the ordering below is not what
the finding first suggested.** By the family whose rows were dissolved, at the CURRENT catalog (4,035
of the 8,429): `experience_years` **3,876**, `degree` 119, `clearance` 19, `work_auth` **14**,
`contract_not_fte` 1. A document has to state BOTH an authorization and a citizenship requirement for
the collision to be possible at all, and live postings rarely do. **So the group decision is an
`experience_years` decision**, and it is NOT a reason to hold a work_auth or clearance recall fix.

**PRICED A/B/C against the live corpus, control first, on the surfaces the changes actually reach**
(main = the store's catalog and the control, branch = the two shipped fixes, held = branch + both
held patches, patched catalogs loaded as config-dir overrides; 25,639 rows, 375 skipped for a stale
catalog, **25,264 compared, control 0 failures**):

- **the shipped pair moves 262 evaluations — 253 `uncertain` -> `ineligible` and 9
  `eligible` -> `ineligible`.** The nine are postings stating a sponsorship refusal that were reading
  `eligible` and could have reached the apply queue.
- **the held pair moves ZERO**, over the whole population carrying its own target surfaces.

Script: `.agent/2026-08-31d-session/` (`0831d-price-held-targeted.py`).

**Two word-gap recall fixes are ready on PR #288 and TWO MORE ARE HELD BEHIND THAT DECISION.** The
shipped pair is unconditionally correct and corpus-clean. The held pair (the shared `work_auth`
hyphen gap; the clearance clause gap admitting an abbreviation dot, which turns `Active Secret
clearance for U.S. Government work is required.` from zero rows into `ineligible`) each make a
hyphenated or dotted document reach the conflict its PLAIN TWIN ALREADY HITS — so each removes an
inconsistency rather than creating one, and the cost is documents moving from a correct `ineligible`
into the review queue. Fix the group first and both are clean wins; ship them first and `rules_hash`
re-keys twice over the same ground.

**Run 135 remains verified and the closed-posting drain remains correct** (previous session, now
settled): `_closed` 70 = the store's `closed_job_ids` 70, `_review` 377 = 377, `ineligible` 261 =
261, apply lane **163 = 151 post-drain + run 135's own 17 arrivals**, which is not a fault. `#285`'s
apply-lane drought detector reads the live store and is correctly silent — run 135 (40, 17), 134
(40, 15), 133 (28, 5).

**THE JOB-APPS INGESTION LANE IS BUILT, MERGED AND INERT (D-386, #286)** and verified inert in the
live config through `load_settings()`: `lanes_enabled = ('hiringcafe', 'linkedin')`,
`jobapps_discovery_dir = None`. Merging changed no unattended run. Only ARMING remains, and it is
Mit's, on return, first run watched. Of 737 discovery records 189 are direct-apply, 160 absent from
this store by URL, and **126 of the 189 arrived through job-apps' own hiring.cafe acquisition** — the
reach boardwatch's own hiring.cafe lane cannot get while it is refused 14 of 14 facets.

### The seniority hold is 3 postings, not 5. It is dead, not deferred.

Re-measured with the real gate and catalog against the lane that **survives** D-383's drain:
`in_band` 146 / `above_band` **3** / `uncertain` 2 over 151, against 195/5/3 over the pre-drain 203.
The two that vanished — Capital One `Director, Software Engineer` and Chewy `Software Development
Manager` — are **already `closed`**, so #284 removes them for free. **Not built:**
`seniority_verdict` needs four inputs (per-company scheme, target band, field tier, catalog) that a
conn-only store read cannot reach without pushing profile and config into `store/`. Three postings
does not buy a layering change, and **D-383's precedent does not transfer** — `row.closed` was
already on `QueueRow` from a column the store already read.

---

## Next action

1. **DECIDE the `experience_years` `exclusive_groups` question — the largest measured precision item
   on the board.** See Current standing and D-387. `[total_years_minimum, range_years_minimum,
   scoped_years_minimum]` treats "5+ years of software engineering experience" beside "3+ years of
   Python" as a CONTRADICTION and dissolves both rows to `unknown`: **3,876 evaluations at the
   current catalog, none of which has any other `required` row already `unmet`**. It is a semantics
   decision on the highest-volume family in the system, so it is the owner's. **The
   `contract_not_fte` precedent does NOT transfer** — that family collapsed three patterns onto one
   `implies` value so they corroborate, licensed by "the three already resolve IDENTICALLY in
   `resolve.py`", and these do not. The `work_auth` and `clearance` groups have the same defect and
   14 and 19 evaluations respectively, so they are cleanup, not the lever.
2. **PR #288 — merge or hold, but read its "held" section first.** `make check` exit 0 on the branch
   (8738 passed, 4 xfailed, 9m15s, read from the sentinel). Auto-merge deliberately NOT armed. Two
   corpus-clean sponsorship recall fixes plus D-387, the CHANGELOG entry, STATE and METRICS. Holding
   it costs nothing except that STATE and D-387 land later.
3. **ARM the job-apps lane — OWNER'S CALL, ON RETURN, FIRST RUN WATCHED.** The build is DONE (D-386,
   #286) and merged inert. D-385 ruled the arming question already and it is **not re-litigable**.
   **Two lines of local `config.toml` and no code change**: add `jobapps` to `lanes_enabled` and set
   `jobapps_discovery_dir` to job-apps' `APPLY_QUEUE`. Read both back through `load_settings()` — a
   typo arms nothing while looking armed. Expect ~188 postings across ~146 companies on the first
   armed run, with `lane_new_companies_per_run` (10) ramping ~103 new employers over ~10 runs.
4. **The two HELD recall patches: DO NOT SHIP. This is a measured answer, not a hold.**
   `.agent/2026-08-31d-session/WIP-workauth-hyphen-rows3to8-NOT-SHIPPED.patch` and
   `WIP-clearance-abbreviation-dot-NOT-SHIPPED.patch`. Both build, both probe correctly in both
   directions against three profiles, and both are corpus-clean — and they move **ZERO verdicts over
   the 25,264 evaluations whose bodies carry their own target surfaces**. No verdict-level upside,
   and they can reach the conflict class in item 1. They stay on disk as evidence, not as pending
   work. **Do not re-raise them as a recall opportunity** — the measurement is in D-387, and the
   surfaces they fix are real but change no decision this profile makes.
5. **`reports/abstain.STRUCTURALLY_UNDECIDABLE` is stale for `experience_years:scoped_years_minimum`
   and the fix is one line.** D-319 made that rule decidable: at the current engine version it
   resolves `unmet` on 55,520 rows against 7,634 carrying the unconditional abstain. The report
   effect is nil today (it is nowhere near fully abstaining, so `fully_abstaining` never includes it)
   — but the docstring describes behaviour the resolver no longer has, and D-380's "a reason that can
   never clear" reading was measured on the SHORTLIST population, not this one.

*(No longer a next action: the `rules.yaml` word-gap audit as an open item — it was worked, and D-387
records what shipped, what is held and behind what. The WIP `cannot confirm` lookahead is WITHDRAWN,
not deferred: it fixes UNSHIPPED code, `main` already returns zero rows on that sentence. Re-measuring
the sponsorship round-2 upside is WITHDRAWN too: its blocker is jurisdiction CAPTURE, which is design,
not sizing. The audit's row 18 does not reproduce as a dot bug — `MS` and `M.S.` give identical rows.
A seniority hold in `review_gate`: re-measured at 3 postings, needs profile+config in `store/`.)*

## Session 2026-08-31d — what shipped

| PR | what |
|---|---|
| **#288** | two sponsorship recall fixes: `never` declared in `consumes_cues`, and `\w+` -> `[\w-]+` so a hyphenated modifier stops hiding a refusal (D-387) |

Previous session: **#286** the job-apps ingestion lane (disarmed, D-386) and **#285** the apply-lane
drought detector (D-384); before that **#284**, the `_closed` drain (D-383), apply 203 -> 151.

**The corpus was the baseline, not the check.** All 1034 cases were dumped with their production
verdict and requirement rows BEFORE any edit — zero golden mismatches — and re-dumped after every
commit. Zero verdict changes and zero row changes each time. That is also what made the held pair
visible: **their corpus diff is zero too, and they still regress**, so the discriminating test here
is a two-sentence probe, not the corpus.

**Both shipped fixes proven non-vacuous by reverting the catalog:** 2 of 5 new tests fail for the cue
fix, 5 of 17 for the hyphen fix, and the tests that stay green are exactly the controls.

`make check` exit 0 on the branch (8738 passed, 4 xfailed, 9m15s, coverage 95.67%), read from the
sentinel rather than a completion notification.

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
| **The engine reads a REFINEMENT as a CONTRADICTION — 8,429 `uncertain` evaluations** | `engine.py` stage 1 makes two DISTINCT `implies` values from one `exclusive_groups` entry a CONFLICT and rewrites BOTH rows to `unknown`. `work_auth`'s group is `[citizenship_required, citizen_or_lpr_required, authorization_required]`, so "must be authorized to work in the US" plus "a natural-born U.S. citizen is required" resolves `uncertain` with a decisive `unmet` discarded — citizenship REFINES authorization. Same shape in `experience_years`, `degree`, `clearance`. **8,429 of 124,980 `uncertain` evaluations at the engine version derived from run 135 carry a conflict-dissolved row, and NOT ONE has any other `required` row already `unmet`**; re-running with the groups emptied flips **2,674 of 4,035 comparable (66.3%)** to `ineligible`, control 0 of 4,035. **By family, at the current catalog: `experience_years` 3,876 · `degree` 119 · `clearance` 19 · `work_auth` 14** — so this is an `experience_years` decision, and it does NOT gate the two held recall patches, which price at ZERO verdict changes on 1,500 live evaluations (D-387). One `engine_version` spans TWO `catalog_version`s here — filter on the catalog. Do not copy the `contract_not_fte` collapse: its licensing condition ("the three resolve IDENTICALLY") fails for these | **Mit** (semantics call on the highest-volume family) |
| **boardwatch sees 16.4% of job-apps' eligible yield — RE-DERIVED 2026-08-30, and the METHOD was wrong before** | **45 of 275 (16.4%)**, cohorts 08-23..08-29, on the **379-board fleet**. This replaces "10.1%, owed a check". It decomposes: fleet growth 344->379 gave 10.1 -> **13.8%**; adding an **exact ATS-slug key** alongside name matching gave 13.8 -> **16.4%**. **Name-only matching undercounts, so 7.7% and 10.1% are FLOORS** — boardwatch stores Micron as `Micron TDIT`, so the old method scored a watched company as unwatched; same for HPE/`Hewlett Packard Enterprise`, Cox/`Cox Automotive`, Disney/`Walt Disney Company`, Toyota, VIAVI. **The unreached 230 split: aggregator-only 60.7%, unsupported employer host 21.1%, board-addable just 1.8%** (5 postings in 7 days, 4 of them SmartRecruiters — the class D-370 declined on measured cost), so the cheap remainder is ONE Workday board (Motorola Solutions). **The gap is lanes, not boards.** Script: `.agent/2026-08-30-session/reach_v2.py`. Amazon/TikTok/Apple/ByteDance use none of the 6 ATS, so a slug cannot reach them. Closing it means a new discovery lane — GitHub new-grad lists are 19.1% of yield for ~5 public-repo GETs and are NOT the ToS trap the v2 decision was written about. **Reopens D-008** | **Mit** (reverses a shipped decision) |
| ~~Delivery-drought cannot see APPLY-LANE starvation~~ **CLOSED by #285 / D-384** | `delivery_drought.py` counts `artifacts.kind == TAILORED_KIND`, written **regardless of which lane `review_gate.lane()` routes to**, so a global misclassification shipped zero apply-ready leads with every existing alarm green. `check_apply_lane_drought` now fires when the last 3 clean runs each delivered PLACEABLE leads and none reached the apply lane. **The old sizing was wrong, not merely pessimistic**: it priced a guard inside `_sync_queue`, but the three job-id readers already take only a connection and `QueueRow` already carries `delivered_run_id`, so nothing in `review_gate`, `_sync_queue` or the web server's result type had to change. Known property, direction abstain-not-alarm: `delivered_unapplied` attributes a re-delivered job to the NEWER run, so an older run can read zero placeable and the window abstains | **CLOSED** |
| ~~Four detector fallbacks are print-only, not durable~~ **CLOSED by #260** | The `intake-death` / `delivery-drought` / `liveness-blindness` / `corpus-regression` "check not run" handlers now call `append_run_error` like the three artifact-write handlers beside them, so a DETECTOR that crashes leaves a row in `runs.errors_json` and not only a digest line. Four one-line additions, inert on the normal path; each pinned by its OWN parametrised test, because a single test crashing all four passes while three of the four calls are missing. **Known shared property:** `append_run_error` is not internally defensive and these sit inside `except` handlers — matched to the three existing handlers deliberately rather than diverging; it needs two simultaneous failures and fails loudly via the withheld heartbeat | **CLOSED** |
| **`companies.last_health` / `last_ok_at` are a LYING instrument** | 178 of 379 watched boards read NULL, which looks like "never succeeded" — **all 178 were scanned by run 133** (128 complete, 7 partial, 43 unchanged). The scan path does not maintain these columns. **Judge fleet health from `board_scans` per run instead**: run 133 was 379 attempted / 271 complete / 87 unchanged / 21 partial / **0 failed** | tooling gotcha |
| **Citi sits at 13.1% coverage, permanently** | Workday's `total` censors at 2,000; the facet sum (uncapped, control-verified) says 4,589. Our pager wraps at ~2,000 too, so post-drain Citi holds ~2,214 of 4,589 and nothing reports it | **Mit** (input-side) |
| **`unchanged` staleness is now BOUNDED (D-298, #153)** | The `unchanged` verdict comes from the upstream HTTP validator (ETag/Last-Modified → 304), not a boardwatch payload hash. `validator_max_age_hours` (default 24) drops a validator older than the TTL, forcing an unconditional refetch, so a permanently-stale upstream can no longer freeze a board forever — the silent-staleness window is capped at the TTL, and a regression test now exercises the aged-validator refetch. Still open: within the TTL an `unchanged` is trusted with no independent check. The separate "59 of 135 boards listed nothing" figure was a **`postings_listed`-on-304 artifact — CORRECTED to 17 real dead-weight (D-300)**, now cleaned; the 118 `ok` boards hold 39,253 open postings | open (mitigated) |
| **`resume.yaml` is an IMPORT SOURCE, never hand-fixed** | D-155. Mit pins `resume_max_pages=1`; never advise 2 | Mit |
| **`boardwatch top` advances the queue by default** | records `seen` unless `--no-record`; relevant to Gate P6's clean window | P6 |
| **A live store is readable ONLY via Python `sqlite3` `?mode=ro`** | the `sqlite3` CLI with `?mode=ro` fails `CANTOPEN(14)` on a cleanly-checkpointed store (no `-shm`; not the sandbox), and `?immutable=1` skips the WAL so it is STALE against a live writer. Mid-run progress: `SELECT COUNT(*) FROM eligibility_evaluations WHERE run_id=N` (D-268) | tooling |
| **`boardwatch web` IS NOW OVER-REPORTING THE APPLY LANE BY ~52, AND THE D-279 RESTART WINDOW IS OPEN** | **Run 135 has executed**, so this is no longer a prediction: 70 folders moved to `_closed` (52 of them out of the apply lane) while the running viewer (pid from 2026-08-29d) holds **pre-merge Python in memory** (D-360: bundle from disk, API from the import at startup), so its `/api/queue` keeps counting them as apply-lane work. **#284 adds no migration and #286 adds none either**, and run 135 has now migrated the store, so the checkout is NOT ahead of it — **the D-279 window is OPEN and a restart is safe as of 2026-08-31c**. Left running deliberately rather than restarted: it is a live process and the call is Mit's. Until it is restarted the page over-reports and the FOLDER TREE is the truth (apply **163**, `_closed` **70**, `_review` **377**, `_ineligible` **261**, all four reconciled against the store this session). **A second, stray `boardwatch web` was also running** at this session's start, launched by a shell carrying another session's transcript path, alongside a 0-byte 8h-old `.git/index.lock` (cleared after confirming no git process held it). **If a peer session is live in the primary tree, declare ONE owner before merging there** | **Mit** (restart after a run) |
| **`boardwatch web` IS RUNNING — started 2026-08-29d** | Started from the primary checkout on `main` with `--port 0 --no-open` and **verified through a second path**: `GET /` returns 200 and `GET /api/runs` returns **401 without a token and 200 with the bearer**. The session URL is `http://127.0.0.1:<port>/#<token>` — the token rides in the **fragment** so it never reaches a server log or a `Referer`, it is stable, and it lives at `~/Library/Application Support/boardwatch/web-token` (mode 0600). **The port is whatever `--port 0` picked**, so read it from the process rather than assuming: `lsof -nP -iTCP -sTCP:LISTEN -a -p $(pgrep -f 'boardwatch web')`. It was stopped and restarted once during this session to take the store lock for the D-370 cold scan — **never write to the store with the viewer up**, a WAL two-writer deadlock against a running pipeline is on record. The underlying skew is still structural (D-360): the bundle is served from **disk** and the API from the Python imported **at startup**, so any merge or branch switch under a running viewer separates the two. The 2026-08-29f "DO NOT RESTART" instruction was conditional on the store being BEHIND the checkout; **run 135 has since migrated it, so that condition no longer holds** and a restart is safe (Mit's call). `main` now carries the `p_runs_corpus_counts` migration while the store is still at `p_runs_board_split` until the 04:00 run migrates it, and the viewer NEVER migrates (D-279) — restarting against a checkout AHEAD of the store 500s it. The running process holds the pre-merge code in memory and is correct either side of an additive migration, so leaving it alone is the safe action. Restart only AFTER a run has migrated the store; the bundle it serves is built on disk (`web/dist` is untracked) and only `make web` changes it. #232 makes a missing field degrade to the pre-#224 view instead of blanking the page | **Mit** (restart after merges) |
| **The unattended 04:00 tick runs the PRIMARY checkout's branch — and it is now PROVEN to fire** | Run 131 (2026-08-29, `runs = 1`, exit 0) was the first real unattended tick. The launchd job invokes the **editable** venv at `boardwatch/.venv/bin/boardwatch`, so whatever branch that tree is parked on IS the unattended run's code and `rules.yaml`. **Verified at the 2026-08-29f close: the tree is on `main` at `10baad5`, clean, and all six alert modules import through the editable venv.** A stale 8-hour-old `.git/index.lock` had silently blocked every `git pull` that session — check the lock's MTIME and `pgrep -x git` before blaming contention. **Park it on `main` before ending every session** — from ~2026-08-31 a stray branch changes EVERY subsequent run, not one. Closing it mechanically means pointing the plist at a worktree pinned to `main`, which moves a scheduled job and a venv | **Mit** (mechanism); every session (discipline) |
| **hiring.cafe lane is DOWN; the HEADER LEVER FAILED and the remaining call is the OWNER'S** | **D-369/#245 shipped the search route's browser-navigation header set and run 133 is its readout: NEGATIVE.** Run 133 reproduced run 131's `SearchPageError` byte for byte (14 facets, 14 refusals), so **headers are ELIMINATED and that experiment must not be repeated.** D-368's other premises were already dead: the UA premise is FALSE (we have sent a Chrome UA since the lane shipped) and the volume premise did not survive the run log (run 128 spent ~28 requests; run 131 was refused on its FIRST request 14 h later). **What remains is the ENDPOINT — path-scoped protection on `/jobs/*`**: job-apps succeeds on `/`, our `/api/` calls succeeded every run through 128, our `/jobs/` calls have failed **14 of 14 on two separate runs**. That is a **compliance decision, not a repair** — robots.txt ALLOWS `/jobs/` and DISALLOWS job-apps' `?searchState=` form. **Still do NOT probe.** Half the lane coverage job-apps' edge comes from. **Second, smaller call:** ~196 refused requests over an unattended fortnight if the lane stays enabled (balanced; see Next action item 1) | **Mit** (the endpoint call, or send the drafted access request; and whether to leave the lane enabled) |
