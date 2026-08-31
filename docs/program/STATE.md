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

**A QUARTER OF THE APPLY QUEUE WAS DEAD, AND NO INSTRUMENT THIS PROGRAM HAS BUILT COULD SEE IT.**

Measured 2026-08-31 through two independent paths that agree — the `details.json` sidecars and
`postings.status` read directly off the live store — **52 of the 203 apply-queue folders named a
posting the store reports `closed`**, plus 18 more in `_review`. The oldest was delivered by
**run 71**. `_sync_queue` copied `postings.status` into `details.json` and nothing read it back, so
a requisition that came down left its folder in the blind-apply list forever.

**Apply-lane status in full: 118 open · 52 closed · 33 unverifiable** — only 58% confirmed live.

**Why the 2026-08-30 audit missed it: the blind judge read JD text, and liveness is not in the
text.** So this COMPOUNDS with its 44.2% rather than overlapping. The other system already knew —
job-apps' largest skip bucket is `_skipped/posting_closed/` at **466 folders**.

**Shipped as D-383 / #284.** A dedicated `_closed` drain, decided in `review_gate.classify` (the
one function the folder tree and the page share, D-332), read above every verdict/location/role
check, precedence `applied` > `skipped` > `closed` > `ineligible` > `review` > apply. It drains
BOTH ways for free — the set is recomputed every reconcile, so a reopened posting returns.
**`status == "closed"`, never `!= "open"`**: `unverifiable` is open-on-an-unenumerable-board
(D-324) and sweeping it would bury live work. **70 folders move; apply 203 -> 151.**

**It cost nothing expensive**, and that is why it was the right thing to ship the night before an
unattended fortnight: `engine_version()` resolves its four inputs sibling-only inside
`eligibility/`, so **no re-evaluation, no ledger drain, no acceptance-counter reset**.

### The seniority gate was the top next action. It is measured at 5 postings. Do not build it yet.

Two measurements overturned the plan, and both contradict what STATE said on 2026-08-30:

1. **`rank/seniority_gate.py` is LIVE, not missing** — wired at `top_cmd.py:468` — and Mit's profile
   reads `target_seniority_band = 'entry'`, so it is **armed, not inert**. "Nothing in the pipeline
   reads level" was WRONG about the ranker; it is only true of the DELIVERY lane.
2. The real gate, real catalog, all 203 apply-lane titles: **`in_band` 195 · `above_band` 5 ·
   `uncertain` 3.** The five are one Director, three Managers and one Software Development Manager.

The three `Member of Technical Staff` rows stay `in_band` **by design** (masking added after 94 SWE
MTS titles were falsely dropped over 26,997 postings). The 10 digit-level titles (eBay SWE 2/3,
MongoDB 2/3, Snap Level 3, Garmin 2, Twilio L2) ABSTAIN because `leveling-bindings.yaml` is empty —
per-operator data, open by design, and **not ours to write on Mit's behalf**.

**The seam is real but small:** `review_gate.classify` has six decision points, none reads
seniority, so a lead delivered before the gate was armed is never re-checked. That is a
**5-posting** seam. The judge's 28 of 77 is mostly JD-BODY level and years prose — the *experience*
family, not a title token — so a title-based gate cannot reach it.

---

## Next action

1. **job-apps ingestion — designed, blocked on ONE owner question** (below). Design at
   `.agent/2026-08-31-session/INGEST-JOBAPPS-DESIGN.md`. The architectural answer is settled: it is
   a **LANE, not a seventh provider** — the provider catalog is closed and gated in three places,
   while `lanes/base.py` exists for exactly this and inherits every persistence/identity/dedup
   invariant. Costs **zero** `engine_version` movement. Four points settled in discussion and not to
   be re-argued: ingest raw DISCOVERY not verdicts; STRIP the header and fail closed; dedup on the
   provider-namespaced ATS slug; import `_applied` FOLDERS never `applications.csv`.
2. **The `rules.yaml` word-gap audit — MEASURED, NOT SHIPPED.**
   `.agent/2026-08-31-session/HYPHEN-GAP-AUDIT.md`. 55 patterns: **9 HYPHEN, 9 PUNCTUATION, 18 SAFE,
   19 no gap**, each verified through the real pipeline with a control. Two `consumes_cues` findings
   sit beside it, one of which (`no_sponsorship_will_not_consider` omits `never`) is a **one-word
   fix against a false `eligible`**. Held deliberately: `rules.yaml` re-keys `rules_hash` ->
   `policy_version`, forces a ~111k re-evaluation, and re-arms the `exclusive_group` dissolution
   trap a live-lane harness **cannot** see. Assert ZERO corpus verdict changes before recording.
3. **A seniority hold in `review_gate` is worth 5 postings** — cheap and structurally right, but do
   not present it as the big lever. See above.
4. **Sponsorship recall round 2 — BUILT, MEASURED, DELIBERATELY NOT SHIPPED.** Patch and rationale
   at `.agent/2026-08-30-audit-sprint/WIP-sponsorship-recall-NOT-SHIPPED.patch`. Upside is **5**
   apply-lane postings, not the 27 an agent sweep found — that sweep predates run 134.
5. **`does not include internships` kills EVERY experience row on ~6 Stripe postings**, and
   **`(F/H)` is unreachable by `foreign_ad_gate`** (`_FRENCH_GENDER_MARKER` requires `h/f` order and
   parentheses). Both measured, both left alone; zero apply-lane escapes today for the second.

---

## Session 2026-08-31 — what shipped

| PR | what |
|---|---|
| **#284** | a closed posting drains to its own `_closed` lane (D-383) — apply 203 -> 151 |

`make check` exit 0 (8656 passed, 4 xfailed, 7m08s); CI green on every job. **Guards
mutation-pinned: 10 mutants, a no-op control, 8 CAUGHT, 2 survivors PROVEN UNOBSERVABLE and
documented at the site.** The first mutation pass caught a defect in the *tests*: the precedence arm
asserted `applied`, which `delivered_unapplied` excludes unconditionally, making it **unobservable
by construction** — retargeted to `skipped`, which is reachable.

**A sidecar in `_ineligible` can go STALE** — sync excludes ineligible rows so their `details.json`
is never rewritten; two claim `closed` while the store says `open`. Read the store, not the sidecar.

## Owner-gated — do NOT start or decide unilaterally

1. **Does job-apps keep running as a discovery engine feeding boardwatch, or is it retired once
   boardwatch is the daily driver?** Ingestion creates a hard dependency on it continuing to run.
   Measured, and it sharpens the question: the live queue's newest cohort is **2026-08-29** (already
   2 days stale on 08-31), cadence is ~30-55/day on weekdays with **hard zero days at weekends** —
   and per D-376 a dead LANE does not escalate, so a feed that stops is silent.
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
| **boardwatch sees 16.4% of job-apps' eligible yield — RE-DERIVED 2026-08-30, and the METHOD was wrong before** | **45 of 275 (16.4%)**, cohorts 08-23..08-29, on the **379-board fleet**. This replaces "10.1%, owed a check". It decomposes: fleet growth 344->379 gave 10.1 -> **13.8%**; adding an **exact ATS-slug key** alongside name matching gave 13.8 -> **16.4%**. **Name-only matching undercounts, so 7.7% and 10.1% are FLOORS** — boardwatch stores Micron as `Micron TDIT`, so the old method scored a watched company as unwatched; same for HPE/`Hewlett Packard Enterprise`, Cox/`Cox Automotive`, Disney/`Walt Disney Company`, Toyota, VIAVI. **The unreached 230 split: aggregator-only 60.7%, unsupported employer host 21.1%, board-addable just 1.8%** (5 postings in 7 days, 4 of them SmartRecruiters — the class D-370 declined on measured cost), so the cheap remainder is ONE Workday board (Motorola Solutions). **The gap is lanes, not boards.** Script: `.agent/2026-08-30-session/reach_v2.py`. Amazon/TikTok/Apple/ByteDance use none of the 6 ATS, so a slug cannot reach them. Closing it means a new discovery lane — GitHub new-grad lists are 19.1% of yield for ~5 public-repo GETs and are NOT the ToS trap the v2 decision was written about. **Reopens D-008** | **Mit** (reverses a shipped decision) |
| **Delivery-drought cannot see APPLY-LANE starvation** | `delivery_drought.py` counts `artifacts.kind == TAILORED_KIND`, which is written **regardless of which lane `review_gate.lane()` routes to**. If location classification broke globally every lead would go to `_review`, artifacts would keep appearing, drought would abstain, and the owner would get **zero apply-ready leads for a fortnight with nothing firing**. Verified open. Current split is healthy (run 133: 40 new to apply; 420 apply / 189 `_review` = 31%). NOT built: the lane decision lives in `_sync_queue`'s copy step (`delivery/queue.py:385`) and its result type is shared with the web server, so a guard is a materially bigger change than it looks — wrong thing to ship days before an absence | **Mit** (on return) |
| ~~Four detector fallbacks are print-only, not durable~~ **CLOSED by #260** | The `intake-death` / `delivery-drought` / `liveness-blindness` / `corpus-regression` "check not run" handlers now call `append_run_error` like the three artifact-write handlers beside them, so a DETECTOR that crashes leaves a row in `runs.errors_json` and not only a digest line. Four one-line additions, inert on the normal path; each pinned by its OWN parametrised test, because a single test crashing all four passes while three of the four calls are missing. **Known shared property:** `append_run_error` is not internally defensive and these sit inside `except` handlers — matched to the three existing handlers deliberately rather than diverging; it needs two simultaneous failures and fails loudly via the withheld heartbeat | **CLOSED** |
| **`companies.last_health` / `last_ok_at` are a LYING instrument** | 178 of 379 watched boards read NULL, which looks like "never succeeded" — **all 178 were scanned by run 133** (128 complete, 7 partial, 43 unchanged). The scan path does not maintain these columns. **Judge fleet health from `board_scans` per run instead**: run 133 was 379 attempted / 271 complete / 87 unchanged / 21 partial / **0 failed** | tooling gotcha |
| **Citi sits at 13.1% coverage, permanently** | Workday's `total` censors at 2,000; the facet sum (uncapped, control-verified) says 4,589. Our pager wraps at ~2,000 too, so post-drain Citi holds ~2,214 of 4,589 and nothing reports it | **Mit** (input-side) |
| **`unchanged` staleness is now BOUNDED (D-298, #153)** | The `unchanged` verdict comes from the upstream HTTP validator (ETag/Last-Modified → 304), not a boardwatch payload hash. `validator_max_age_hours` (default 24) drops a validator older than the TTL, forcing an unconditional refetch, so a permanently-stale upstream can no longer freeze a board forever — the silent-staleness window is capped at the TTL, and a regression test now exercises the aged-validator refetch. Still open: within the TTL an `unchanged` is trusted with no independent check. The separate "59 of 135 boards listed nothing" figure was a **`postings_listed`-on-304 artifact — CORRECTED to 17 real dead-weight (D-300)**, now cleaned; the 118 `ok` boards hold 39,253 open postings | open (mitigated) |
| **`resume.yaml` is an IMPORT SOURCE, never hand-fixed** | D-155. Mit pins `resume_max_pages=1`; never advise 2 | Mit |
| **`boardwatch top` advances the queue by default** | records `seen` unless `--no-record`; relevant to Gate P6's clean window | P6 |
| **A live store is readable ONLY via Python `sqlite3` `?mode=ro`** | the `sqlite3` CLI with `?mode=ro` fails `CANTOPEN(14)` on a cleanly-checkpointed store (no `-shm`; not the sandbox), and `?immutable=1` skips the WAL so it is STALE against a live writer. Mid-run progress: `SELECT COUNT(*) FROM eligibility_evaluations WHERE run_id=N` (D-268) | tooling |
| **`boardwatch web` WILL OVER-REPORT THE APPLY LANE BY ~70 UNTIL RESTARTED** | #284 moves 70 folders to `_closed` on the next run, but the running viewer (pid from 2026-08-29d) holds **pre-merge Python in memory** (D-360: bundle from disk, API from the import at startup), so its `/api/queue` keeps counting them as apply-lane work. **#284 adds NO migration**, so restarting is safe as soon as a run has finished — that is the D-279 window. Until then the page over-reports and the FOLDER TREE is the truth. **A second, stray `boardwatch web` was also running** at this session's start, launched by a shell carrying another session's transcript path, alongside a 0-byte 8h-old `.git/index.lock` (cleared after confirming no git process held it). **If a peer session is live in the primary tree, declare ONE owner before merging there** | **Mit** (restart after a run) |
| **`boardwatch web` IS RUNNING — started 2026-08-29d** | Started from the primary checkout on `main` with `--port 0 --no-open` and **verified through a second path**: `GET /` returns 200 and `GET /api/runs` returns **401 without a token and 200 with the bearer**. The session URL is `http://127.0.0.1:<port>/#<token>` — the token rides in the **fragment** so it never reaches a server log or a `Referer`, it is stable, and it lives at `~/Library/Application Support/boardwatch/web-token` (mode 0600). **The port is whatever `--port 0` picked**, so read it from the process rather than assuming: `lsof -nP -iTCP -sTCP:LISTEN -a -p $(pgrep -f 'boardwatch web')`. It was stopped and restarted once during this session to take the store lock for the D-370 cold scan — **never write to the store with the viewer up**, a WAL two-writer deadlock against a running pipeline is on record. The underlying skew is still structural (D-360): the bundle is served from **disk** and the API from the Python imported **at startup**, so any merge or branch switch under a running viewer separates the two — **DO NOT RESTART IT AS OF 2026-08-29f.** `main` now carries the `p_runs_corpus_counts` migration while the store is still at `p_runs_board_split` until the 04:00 run migrates it, and the viewer NEVER migrates (D-279) — restarting against a checkout AHEAD of the store 500s it. The running process holds the pre-merge code in memory and is correct either side of an additive migration, so leaving it alone is the safe action. Restart only AFTER a run has migrated the store; the bundle it serves is built on disk (`web/dist` is untracked) and only `make web` changes it. #232 makes a missing field degrade to the pre-#224 view instead of blanking the page | **Mit** (restart after merges) |
| **The unattended 04:00 tick runs the PRIMARY checkout's branch — and it is now PROVEN to fire** | Run 131 (2026-08-29, `runs = 1`, exit 0) was the first real unattended tick. The launchd job invokes the **editable** venv at `boardwatch/.venv/bin/boardwatch`, so whatever branch that tree is parked on IS the unattended run's code and `rules.yaml`. **Verified at the 2026-08-29f close: the tree is on `main` at `10baad5`, clean, and all six alert modules import through the editable venv.** A stale 8-hour-old `.git/index.lock` had silently blocked every `git pull` that session — check the lock's MTIME and `pgrep -x git` before blaming contention. **Park it on `main` before ending every session** — from ~2026-08-31 a stray branch changes EVERY subsequent run, not one. Closing it mechanically means pointing the plist at a worktree pinned to `main`, which moves a scheduled job and a venv | **Mit** (mechanism); every session (discipline) |
| **hiring.cafe lane is DOWN; the HEADER LEVER FAILED and the remaining call is the OWNER'S** | **D-369/#245 shipped the search route's browser-navigation header set and run 133 is its readout: NEGATIVE.** Run 133 reproduced run 131's `SearchPageError` byte for byte (14 facets, 14 refusals), so **headers are ELIMINATED and that experiment must not be repeated.** D-368's other premises were already dead: the UA premise is FALSE (we have sent a Chrome UA since the lane shipped) and the volume premise did not survive the run log (run 128 spent ~28 requests; run 131 was refused on its FIRST request 14 h later). **What remains is the ENDPOINT — path-scoped protection on `/jobs/*`**: job-apps succeeds on `/`, our `/api/` calls succeeded every run through 128, our `/jobs/` calls have failed **14 of 14 on two separate runs**. That is a **compliance decision, not a repair** — robots.txt ALLOWS `/jobs/` and DISALLOWS job-apps' `?searchState=` form. **Still do NOT probe.** Half the lane coverage job-apps' edge comes from. **Second, smaller call:** ~196 refused requests over an unattended fortnight if the lane stays enabled (balanced; see Next action item 1) | **Mit** (the endpoint call, or send the drafted access request; and whether to leave the lane enabled) |
