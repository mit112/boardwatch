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

**THE QUEUE-AUDIT SPRINT IS COMPLETE AND MEASURED BY AN INDEPENDENT JUDGE. The acceptance test
PARTLY PASSED, and the honest number is not the one the engine forecast.**

Mit's test: *"I don't want to see a job in the apply queue where I can instantly spot something that
makes it ineligible."* Four PRs shipped tonight (#276, #278, #280, #281) plus #275 earlier.
**Apply lane 420 -> 203.**

Two instruments, reported apart on purpose — blending them is what made the old forecast wrong:

| instrument | before | after |
|---|---|---|
| **engine census** (the same engine that would verify itself) | 208 of 420 = 49.5% | **48 of 203 = 23.6%** |
| **independent blind judge**, apply lane, decoys excluded | 44 of 76 = 57.9% | **34 of 77 = 44.2%** |

**THE TWO DISAGREE, AND THAT IS THE FINDING.** The forecast "208 -> roughly 40" was computed with
the engine's own regexes and the engine delivered it (48). The blind judge, which never sees
boardwatch's verdicts, still calls **44%** of the apply lane spottable. The engine cannot see what
it has no rule for, so a census built from its own nets under-reports by construction. **Never quote
23.6% as the queue's quality** — quote it as the engine's own view, next to the judge's 44.2%.

What the judge still finds in the apply lane (n=77, decoys excluded): **seniority mismatch 28**,
**experience 21**, work_auth 5, role-family 6, clearance 1, degree 1. Vacuity control passed — 4 of 4
known-answer decoys caught. Zero `ineligible` without a quoted span, both runs.

**SENIORITY IS NOW THE LARGEST CLASS AND BOARDWATCH HAS NO GATE FOR IT.** `role_gate` decides role
FAMILY, not level. 28 of 77 is bigger than any eligibility family. This is the top candidate for the
next session, and it is exactly where job-apps wins (below).

**job-apps FILTERS BETTER — measured, same judge, same facts, same night, neither system grading
itself.** boardwatch apply **44.2% spottable** vs job-apps **16.2%** (13 of 80); role-family
mismatch **6 vs 0**. **The mechanism is upstream pre-filtering:** job-apps keeps a curated H-1B
sponsor allowlist and draws 65% of its queue from LinkedIn/Indeed, where the aggregator supplies a
literal `Entry Level` facet (10 of 80 carry it; **0 of 80** on boardwatch, which sources direct from
ATS boards that expose no such facet). This CORRECTS the standing "the gap is throughput, NOT an
eligibility defect" line — true of REACH, false of filtering QUALITY.

**Three caveats that bound every number above, all found by cross-checking rather than assumed:**
1. The first job-apps staging was **NOT blind** — its `job_description.txt` carries a job-apps
   header (`Template: <family>` on 80 of 80, `Fit: N/100`, a live `URL:`) against 0 of 150 on the
   boardwatch side. `stage_jobapps.py` now strips it and **fails closed**. Re-judged; the conclusion
   held (16.2% vs the leaked 15.0%).
2. **Judge sessions are NOT calibrated across runs** — `eligible` came back 0/150 one run and 47/80
   another. Only the evidence-anchored `ineligible` axis and the part-B fit axes survive a
   cross-session comparison. Never compare `eligible` rates.
3. boardwatch's 80 includes **4 force-included decoys**; 76/77 is the unbiased denominator.

**Run 134 succeeded** (exit 0, ~1h45m; the full 111,361-posting re-evaluation is the cost of a rules
change). `engine_version` is now `1+6a9fb2164f5b`. hiring.cafe failed again exactly as D-369
predicts — expected, not new.

---

## Next action

1. **A SENIORITY GATE.** 28 of 77 apply-lane items, the largest single class, and nothing in the
   pipeline reads level. Note the shape job-apps uses: an upstream aggregator facet, not JD prose.
2. **Sponsorship recall round 2 — BUILT, MEASURED, DELIBERATELY NOT SHIPPED.** Patch and full
   rationale at `.agent/2026-08-30-audit-sprint/WIP-sponsorship-recall-NOT-SHIPPED.patch` and its
   README. It cannot be made correct without CAPTURING jurisdiction the way `no_sponsorship_offered`
   does: a foreign-only guard produced a wrong `ineligible` on "For the London position…", and an
   any-jurisdiction guard stands the patterns down on the three spans worth catching. **Upside is 5
   apply-lane postings, not the 27 the sweep found** — that sweep predates run 134.
3. **Two real bugs worth keeping whatever shape (2) takes:** `cannot CONFIRM that sponsorship is
   available` answered `ineligible`; and a `\w+` word gap **cannot cross a hyphen**
   (`immigration-related`) — the same class as the parenthesis in D-381, so audit every gap in the
   catalog for it.
4. **`does not include internships` kills EVERY experience row on ~6 Stripe postings.** A negation
   cue inside a parenthetical suppresses the requirement it qualifies. Shared negation machinery —
   too broad to change unattended, measured and left alone.
5. **`(F/H)` is unreachable by `foreign_ad_gate`** — `_FRENCH_GENDER_MARKER` requires `h/f` order and
   parentheses, so `(F/H)`, bare `H/F` and bare `F/H` all miss. Zero apply-lane escapes today.

---

## Session 2026-08-30b — what shipped

| PR | what |
|---|---|
| **#276** | unconfirmed-requirement leads route to `_review` (D-380) |
| **#278** | experience bar stated as a RANGE |
| **#280** | six recall patterns: citizenship, clearance stack, domain-years (D-381) |
| **#281** | `eligible` no longer skips the role/location gates — R1 (D-382) |

`make check` exit 0 on every one. **Two first-draft loosenings were caught by the gate, not by
review**, and both are now memory entries: a pattern implying a DIFFERENT value from the same
`exclusive_group` as a sibling makes the group CONFLICT and rewrites BOTH rows to `unknown` — seven
corpus cases fell `ineligible` -> `uncertain`.

**Harness, all preserved under `.agent/2026-08-30-audit-sprint/audit-harness/`:** `stage_audit.py`
(now searches ALL lanes for the decoys and **hard-fails** if one is missing — the old apply-only
lookup would have silently dropped two once #276 re-laned them), `stage_jobapps.py`, `CODEX-PROMPT.md`,
`JOBAPPS-PROMPT.md`, the before-baseline (`*-before-baseline.*`) and both after-runs.
**Codex needs `-s workspace-write`; `--full-auto` is not a flag in codex-cli 0.151.0.**

## Owner-gated — do NOT start or decide unilaterally

8. **Mit's two résumé content calls** — whether to send a document at all; the D-220 prose rewrites.
9. **P2 item 8 — the onboarding field-taxonomy gatherer. DEFERRED by Mit 2026-08-28**: no time before
   he steps back from active work (~2026-08-31, unattended after). **Not dropped — an accepted known
   gap**, and the last multi-tenancy gap of its kind. Still owner-gated and still needs its own
   brainstorm; D-054 forbids us authoring non-tech field content.
10. **`add-evidence` takes no bundle lock** (D-143) — raise before two authoring agents run against
   one bundle.
## Open questions — Mit's, not to be resolved by fiat

1. **The projection spec's six open questions** (§12) — soonest: whether `tailor run` should validate
   the projection manifest, and whether persona's `entries` list survives stage 2.
2. **The Snap `Level 5`/`Level 3` leak stays open by design** — with no bindings file every level
   token abstains, so a level-named title is shortlisted carrying its reason. boardwatch ships no
   verifiable claim about any company's ladder.
3. **Whether `censored` boards publish a coverage ratio, and the 17 silent boards.** The
   `detail_fetch_budget` half moved 2026-08-28: raised **50 → 400 in Mit's local config only** (never
   the code default — a multi-tenancy call). **The "four censored boards are short 18,927" figure is
   STALE against the current fleet**: the class is **15 boards and 43,371 postings that can never be
   listed at all** (run 127), against an ~84,821-posting open corpus. **Sized, not solved, and no
   budget can solve it** — those postings are never enumerated. See D-336.
4. **Whether `ServiceNow Developer` should rank at all against a new-grad SWE target.** Surfaced by
   run 129's location-split failure and **left unexamined** — it is role TAXONOMY, not dedup, and
   possibly upstream of the whole slate-cap question. D-345 bounds the delivery damage; it does not
   answer this.

*(Resolved and no longer open: **how to cap the delivery slate when one requisition is split across
cities — RULED by Mit and shipped as D-345**, `(company_id, normalized_title, content_hash)` at N=1;
do not reopen it as identity suppression, which is D-295 and is refused. Whether `runner.py` should
keep swallowing a funnel-write failure — D-288. Clearance IS a blocker (D-257). Seniority band =
`entry` (D-258). The launchd trigger fires (D-254), once daily at 04:00, a fallback rather than the
thing to plan around.)*

---

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
| **boardwatch sees 16.4% of job-apps' eligible yield — RE-DERIVED 2026-08-30, and the METHOD was wrong before** | **45 of 275 (16.4%)**, cohorts 08-23..08-29, on the **379-board fleet**. This replaces "10.1%, owed a check". It decomposes: fleet growth 344->379 gave 10.1 -> **13.8%**; adding an **exact ATS-slug key** alongside name matching gave 13.8 -> **16.4%**. **Name-only matching undercounts, so 7.7% and 10.1% are FLOORS** — boardwatch stores Micron as `Micron TDIT`, so the old method scored a watched company as unwatched; same for HPE/`Hewlett Packard Enterprise`, Cox/`Cox Automotive`, Disney/`Walt Disney Company`, Toyota, VIAVI. **The unreached 230 split: aggregator-only 60.7%, unsupported employer host 21.1%, board-addable just 1.8%** (5 postings in 7 days, 4 of them SmartRecruiters — the class D-370 declined on measured cost), so the cheap remainder is ONE Workday board (Motorola Solutions). **The gap is lanes, not boards.** Script: `.agent/2026-08-30-session/reach_v2.py`. Amazon/TikTok/Apple/ByteDance use none of the 6 ATS, so a slug cannot reach them. Closing it means a new discovery lane — GitHub new-grad lists are 19.1% of yield for ~5 public-repo GETs and are NOT the ToS trap the v2 decision was written about. **Reopens D-008** | **Mit** (reverses a shipped decision) |
| **Delivery-drought cannot see APPLY-LANE starvation** | `delivery_drought.py` counts `artifacts.kind == TAILORED_KIND`, which is written **regardless of which lane `review_gate.lane()` routes to**. If location classification broke globally every lead would go to `_review`, artifacts would keep appearing, drought would abstain, and the owner would get **zero apply-ready leads for a fortnight with nothing firing**. Verified open. Current split is healthy (run 133: 40 new to apply; 420 apply / 189 `_review` = 31%). NOT built: the lane decision lives in `_sync_queue`'s copy step (`delivery/queue.py:385`) and its result type is shared with the web server, so a guard is a materially bigger change than it looks — wrong thing to ship days before an absence | **Mit** (on return) |
| ~~Four detector fallbacks are print-only, not durable~~ **CLOSED by #260** | The `intake-death` / `delivery-drought` / `liveness-blindness` / `corpus-regression` "check not run" handlers now call `append_run_error` like the three artifact-write handlers beside them, so a DETECTOR that crashes leaves a row in `runs.errors_json` and not only a digest line. Four one-line additions, inert on the normal path; each pinned by its OWN parametrised test, because a single test crashing all four passes while three of the four calls are missing. **Known shared property:** `append_run_error` is not internally defensive and these sit inside `except` handlers — matched to the three existing handlers deliberately rather than diverging; it needs two simultaneous failures and fails loudly via the withheld heartbeat | **CLOSED** |
| **`companies.last_health` / `last_ok_at` are a LYING instrument** | 178 of 379 watched boards read NULL, which looks like "never succeeded" — **all 178 were scanned by run 133** (128 complete, 7 partial, 43 unchanged). The scan path does not maintain these columns. **Judge fleet health from `board_scans` per run instead**: run 133 was 379 attempted / 271 complete / 87 unchanged / 21 partial / **0 failed** | tooling gotcha |
| **Citi sits at 13.1% coverage, permanently** | Workday's `total` censors at 2,000; the facet sum (uncapped, control-verified) says 4,589. Our pager wraps at ~2,000 too, so post-drain Citi holds ~2,214 of 4,589 and nothing reports it | **Mit** (input-side) |
| **`unchanged` staleness is now BOUNDED (D-298, #153)** | The `unchanged` verdict comes from the upstream HTTP validator (ETag/Last-Modified → 304), not a boardwatch payload hash. `validator_max_age_hours` (default 24) drops a validator older than the TTL, forcing an unconditional refetch, so a permanently-stale upstream can no longer freeze a board forever — the silent-staleness window is capped at the TTL, and a regression test now exercises the aged-validator refetch. Still open: within the TTL an `unchanged` is trusted with no independent check. The separate "59 of 135 boards listed nothing" figure was a **`postings_listed`-on-304 artifact — CORRECTED to 17 real dead-weight (D-300)**, now cleaned; the 118 `ok` boards hold 39,253 open postings | open (mitigated) |
| **`resume.yaml` is an IMPORT SOURCE, never hand-fixed** | D-155. Mit pins `resume_max_pages=1`; never advise 2 | Mit |
| **`boardwatch top` advances the queue by default** | records `seen` unless `--no-record`; relevant to Gate P6's clean window | P6 |
| **A live store is readable ONLY via Python `sqlite3` `?mode=ro`** | the `sqlite3` CLI with `?mode=ro` fails `CANTOPEN(14)` on a cleanly-checkpointed store (no `-shm`; not the sandbox), and `?immutable=1` skips the WAL so it is STALE against a live writer. Mid-run progress: `SELECT COUNT(*) FROM eligibility_evaluations WHERE run_id=N` (D-268) | tooling |
| **`boardwatch web` IS RUNNING — started 2026-08-29d** | Started from the primary checkout on `main` with `--port 0 --no-open` and **verified through a second path**: `GET /` returns 200 and `GET /api/runs` returns **401 without a token and 200 with the bearer**. The session URL is `http://127.0.0.1:<port>/#<token>` — the token rides in the **fragment** so it never reaches a server log or a `Referer`, it is stable, and it lives at `~/Library/Application Support/boardwatch/web-token` (mode 0600). **The port is whatever `--port 0` picked**, so read it from the process rather than assuming: `lsof -nP -iTCP -sTCP:LISTEN -a -p $(pgrep -f 'boardwatch web')`. It was stopped and restarted once during this session to take the store lock for the D-370 cold scan — **never write to the store with the viewer up**, a WAL two-writer deadlock against a running pipeline is on record. The underlying skew is still structural (D-360): the bundle is served from **disk** and the API from the Python imported **at startup**, so any merge or branch switch under a running viewer separates the two — **DO NOT RESTART IT AS OF 2026-08-29f.** `main` now carries the `p_runs_corpus_counts` migration while the store is still at `p_runs_board_split` until the 04:00 run migrates it, and the viewer NEVER migrates (D-279) — restarting against a checkout AHEAD of the store 500s it. The running process holds the pre-merge code in memory and is correct either side of an additive migration, so leaving it alone is the safe action. Restart only AFTER a run has migrated the store; the bundle it serves is built on disk (`web/dist` is untracked) and only `make web` changes it. #232 makes a missing field degrade to the pre-#224 view instead of blanking the page | **Mit** (restart after merges) |
| **The unattended 04:00 tick runs the PRIMARY checkout's branch — and it is now PROVEN to fire** | Run 131 (2026-08-29, `runs = 1`, exit 0) was the first real unattended tick. The launchd job invokes the **editable** venv at `boardwatch/.venv/bin/boardwatch`, so whatever branch that tree is parked on IS the unattended run's code and `rules.yaml`. **Verified at the 2026-08-29f close: the tree is on `main` at `10baad5`, clean, and all six alert modules import through the editable venv.** A stale 8-hour-old `.git/index.lock` had silently blocked every `git pull` that session — check the lock's MTIME and `pgrep -x git` before blaming contention. **Park it on `main` before ending every session** — from ~2026-08-31 a stray branch changes EVERY subsequent run, not one. Closing it mechanically means pointing the plist at a worktree pinned to `main`, which moves a scheduled job and a venv | **Mit** (mechanism); every session (discipline) |
| **hiring.cafe lane is DOWN; the HEADER LEVER FAILED and the remaining call is the OWNER'S** | **D-369/#245 shipped the search route's browser-navigation header set and run 133 is its readout: NEGATIVE.** Run 133 reproduced run 131's `SearchPageError` byte for byte (14 facets, 14 refusals), so **headers are ELIMINATED and that experiment must not be repeated.** D-368's other premises were already dead: the UA premise is FALSE (we have sent a Chrome UA since the lane shipped) and the volume premise did not survive the run log (run 128 spent ~28 requests; run 131 was refused on its FIRST request 14 h later). **What remains is the ENDPOINT — path-scoped protection on `/jobs/*`**: job-apps succeeds on `/`, our `/api/` calls succeeded every run through 128, our `/jobs/` calls have failed **14 of 14 on two separate runs**. That is a **compliance decision, not a repair** — robots.txt ALLOWS `/jobs/` and DISALLOWS job-apps' `?searchState=` form. **Still do NOT probe.** Half the lane coverage job-apps' edge comes from. **Second, smaller call:** ~196 refused requests over an unattended fortnight if the lane stays enabled (balanced; see Next action item 1) | **Mit** (the endpoint call, or send the drafted access request; and whether to leave the lane enabled) |
