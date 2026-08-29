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

**`degree` is AUDITED AND CLOSED — nothing needed softening (D-352, #221); the widening is measured NET HARMFUL.** Moved verbatim to `STANDING-FACTS.md` 2026-08-29.

**The live six-blocker map is the OWNER'S and is NOT to be reverted (D-350/D-351).** Moved verbatim to
`STANDING-FACTS.md` 2026-08-29c.

**SAY WHICH ELIGIBILITY POLICY YOU MEAN, EVERY TIME (D-350)** — catalog and live profile diverge on
**five of six** families (`rules.yaml`: only `work_auth` is a `blocker` default; live store: all six).
By design, but it makes an unqualified severity claim uncheckable, and the gap is wide: #218's floors
give **1,228 verdict flips live vs 0 published**. Full rule in `STANDING-FACTS.md`.

**The lane question is CLOSED (D-346/D-347) — do not re-propose lane parallelism.** Moved verbatim to `STANDING-FACTS.md` 2026-08-29.

**THE hiring.cafe LEVER IS PULLED, AND THE NEXT RUN IS ITS READOUT (D-369, #245).** D-368 ranked the
fix space (1) volume, (2) UA, (3) endpoint. **Reading the two clients side by side falsifies the UA
premise outright** — `runner._LANE_USER_AGENT` has been a Chrome string since the lane shipped and
`tests/pipeline/test_lane_stage.py` has pinned it that long, so **BOTH clients send Chrome** — **and the
volume premise did not survive the run log**: run 128, the last search that WORKED, spent 14 search GETs
and 14 body GETs (**~28 requests**, the reference client's own order of magnitude), and run 131 was
refused on its **FIRST** request 14 hours later. **A rate counter decays over 14 hours; a classification
does not.** What shipped instead is the **SEARCH ROUTE'S HEADER SET**: we sent httpx's `Accept: */*`
under a Chrome UA, while the working client sets `Accept: text/html` by hand and is **SPARSER** than us
everywhere else and is not refused — which rules out "too few browser headers" and leaves
**contradiction with the claimed UA**. Applied to the **search route only**: `/api/job-description` is an
XHR and is the half of the lane that still works. **THE NEXT RUN IS THE READOUT** — facets resolve, or
`SearchPageError` again. **If it fails, headers are ELIMINATED and the strongest remaining hypothesis is
PATH-SCOPED protection on `/jobs/*`** — evidenced already and without a probe: job-apps succeeds on `/`,
our `/api/` calls succeeded every run through 128, our `/jobs/` calls fail **14 of 14**. That branch is
**the OWNER'S**, because robots **allows** `/jobs/` and **disallows** job-apps' query form. **Still no
probing, and browser automation is still out of scope.**

**BREADTH BATCH 2 IS HALF APPLIED, ON A MEASURED COLD SCAN — the fleet is 379 (D-370).** D-367's stated
blocker was "never timed cold", so it was timed: one batch-2 Workday board scanned cold = **604 s,
420/420 enumerated, 0 censored, `postings_listed` 400 — the `detail_fetch_budget` SATURATED exactly, 20
deferred**. **A cold Workday board is therefore bounded by the BUDGET, not by board size.** 20 × 604 s
against run 131's **5.90x** parallelism (10,339.9 s latency / 1,752.0 s `scan`) = **~+34 min of scan wall
clock on the FIRST run**, decaying toward ~+5 min once they hold validators. **The 4 SmartRecruiters
boards are NOT applied, and the reason inverts the intuition**: every SR board is served from the ONE
host `api.smartrecruiters.com`, which `Fetcher` serializes and `scan_workers` provably cannot help
(D-346/D-347), so **4 boards cost more wall clock than the 20 Workday ones combined**. All 20 Workday
boards re-verified `watched=1` by querying the store back against the source YAML.

**Everything below this line is carried and remains true.** The provisional pass is held by the owner
(but see the restarted counter under Phase status); Gate P6 is 4 of 4; **the delivery cap is 40, set in
the plist (D-366)** — the code default `DEFAULT_TOP_N` stays 10 and D-293's hold on it is RELEASED, not
standing; the fleet is 379 watched boards; breadth is argued on precision and capacity,
never an application count (D-312). Board cost is provider-weighted and **s/board is a lying unit** —
`workday` is ~73% of a run; size batches by provider mix, never board count. **Raising the
`scan_workers` ceiling above `le=8` stays RETIRED** (D-344): run 129 finished 343 of 344 boards in
27.0 min, `lowes.wd5` taking 5.9 more alone. Run 129 was **44.7 min** vs run 128's 132.4 — **2.82x =
1.58x backlog drain x 1.78x parallelism**, only the 1.78x code. Numbers: `METRICS.md`.

---

## Next action

> **Mit's instruction at the 2026-08-29c close scoped the owner-facing items to the NEXT session;
> that session ran on 2026-08-29d.** Items 1, 2 and 4 were worked. **1 is SHIPPED and awaiting its
> readout (D-369/#245), 2 stays HELD and now for a MECHANICAL reason, 4 is HALF APPLIED on a
> measurement (D-370).** Items 9-11 remain the owner's and were not started.

> **D-361's two unattended risks are ANSWERED AND CLOSED — do not re-raise either (D-362).** Disk is
> not near-term (83%, 35 GiB free, ~70-day worst runway; Mit's call: **no retention policy**), and
> alerting was never absent. Full reasoning in `STANDING-FACTS.md`. **Edit the plist TEXTUALLY** —
> PlistBuddy strips the comments that carry the reasoning.
>
> **THE FIRST REAL UNATTENDED TICK FIRED AND WAS CLEAN (2026-08-29, run 131).** `launchctl print` now
> reads **`runs = 1`, `last exit code = 0`**, log mtime 05:38, and the run row is `ok` — 04:00 to 05:36,
> 40 leads, 359 boards, no fatal. The two-session-old owed item is answered on the half that is
> observable here. **`launchctl list` col 2 is still the WRONG route** — it prints `0` for a job that has
> NEVER run; use `launchctl print` and read `runs = N` plus `last exit code`, cross-checked against the
> log's **mtime**, never its content.
>
> **What is STILL unconfirmed, and cannot be confirmed from this machine:** `send_heartbeat()` returns a
> `bool`, never raises and **logs nothing**, so no local artifact records whether the GET reached
> healthchecks.io. What is proven is the gate it fires on — `status=ok` and exit 0 mean
> `summary.fatal is None` held, so the call was made. **Receipt is Mit's to confirm in the
> healthchecks.io dashboard.** Do NOT GET the ping URL to check: that manufactures a green.
> **It cannot false-alarm on hiring.cafe** — a lane outage never sets `fatal` (verified).

1. **hiring.cafe: THE LEVER IS PULLED — the next move is to READ THE RUN, not to change anything
   (D-369, #245).** D-368's ranking was corrected on evidence, not overridden: its **UA premise is
   FALSE** (we have sent a Chrome UA since the lane shipped) and its **volume premise did not survive
   the run log** (run 128, the last search that worked, spent ~28 requests; run 131 was refused on its
   FIRST request 14 h later — a rate counter decays over 14 hours, a classification does not). What
   shipped is the **search route's header set**: httpx's `Accept: */*` under a Chrome UA was the one
   thing the working client does differently, and it sets `Accept: text/html` by hand while being
   sparser than us in every other respect. **The 04:00 run is the readout. Change NOTHING before it
   reads out, and do NOT probe the site.**
   **If it fails, headers are ELIMINATED**, and the ranked remainder is **volume** (now the weaker
   case) and **endpoint** — where the strongest hypothesis is **path-scoped protection on `/jobs/*`**
   (job-apps succeeds on `/`, our `/api/` calls succeeded through run 128, our `/jobs/` calls fail 14
   of 14). **The endpoint branch is the OWNER'S**: robots **allows** `/jobs/` and **disallows**
   job-apps' `?searchState=` form, so moving off the allowed path is a compliance decision, not a
   repair. The owner-side access request is still drafted and unsent in
   `.agent/2026-08-28g-session/hiringcafe-access-request.md`. **Until it lifts, lane coverage is
   HALVED.** Browser automation and challenge-solving stay out of scope.

2. **THE PACING TRIAL IS HELD, NOT CANCELLED (D-355).** #222 **is merged now** — the previous
   STATE claimed that while the PR was still OPEN and RED, and the repo won (D-358). The lever ships
   **disarmed**; arming is one config line plus a read-back check, and the whole procedure is in
   `.agent/2026-08-28f-degree-audit/RUN131-CHECKLIST.md`. Mit held it on 2026-08-28 because
   hiring.cafe began refusing us on a day that ran FOUR runs against a cadence of one, and
   **raising the per-host rate 0.6 -> 1.0 req/s on that day is the wrong direction**. Revisit once
   hiring.cafe is healthy and the run cadence is back to normal. **`Settings` does NOT forbid extra
   keys, so a typo'd config key arms NOTHING silently — always read the value back through
   `load_settings()`.**

   **2026-08-29d — there is now a MECHANICAL reason too, not just a judgement call.** `_lane_fetcher`
   builds its `Fetcher` from the **same `Settings`**, so `pace_from_request_start` applies to the
   **LANE** as well as the scan. Arming it cuts the hiring.cafe facet interval from "1.0 s + response
   time" to a flat 1.0 s — **2-4x faster against the host that is currently refusing us**, and a
   **second variable in the D-369 readout**. Keep it disarmed at least until that run reads out. Live
   config confirmed at this close: `per_host_delay_seconds=1.0`, `pace_from_request_start=False`,
   `scan_workers=8`, `detail_fetch_budget=400`.

   **The revert trigger is the PARTIAL RATE AMONG FETCHED BOARDS, and the two earlier versions were
   both wrong (D-353).** Revert on **+5 pts or worse**; run 130 read 9.7%. Do NOT use a raw
   `complete -> partial` count (background rate 3-6 EVERY run) and do NOT use the net of the two
   (it read **-10 on run 130, which had no pacing change**, because `unchanged` collapsed 153 -> 36
   when the validator TTL expired). Any `board_scans` query MUST filter `scan_kind='board'`.

   **Run safety, worktrees and the shared scratchpad have moved to `STANDING-FACTS.md`** ("Moved out
   of STATE on 2026-08-28g") — process-liveness guarding, the EDITABLE venv, PID-scoped kills, and
   per-launch log/sentinel naming. Read that section before touching a live run or launching a gate.

3. **THE PROVISIONAL PASS IS ALLOWED TO SLIP — "work comes first" (D-351).** #218 reset the
   3-clean-run counter and it is **not being chased**. **Read it as UNBLOCKING: eligibility is NOT
   frozen**, so rules work may land freely and a `rules_hash` bump is not costly on this basis until
   the owner reopens the pass. The P4 blind review remains passed and does not repeat.

4. **BREADTH BATCH 2 IS HALF APPLIED — fleet 379 — AND THE SPLIT IS MEASURED, NOT GUESSED (D-370).**
   D-367's blocker was "never timed cold". It was timed: one batch-2 Workday board scanned cold =
   **604 s, 420/420 enumerated, `postings_listed` 400 (the detail budget saturated exactly), 20
   deferred** — so **a cold Workday board is bounded by the BUDGET, not by board size**. 20 × 604 s at
   run 131's 5.90x parallelism = **~+34 min of scan on the FIRST run**, decaying toward ~+5 min.
   **The 20 Workday boards are IN** (20 distinct `{tenant}.wdN` hosts, absorbed by `scan_workers=8`),
   all re-verified `watched=1` against the source YAML. **The 4 SmartRecruiters boards are OUT, and
   the reason inverts the intuition**: every SR board shares the ONE host `api.smartrecruiters.com`,
   which `Fetcher` serializes and `scan_workers` provably cannot help (D-346/D-347), so **4 boards
   cost more wall clock than the 20 Workday ones combined**. That SR figure is **DERIVED, not
   measured** — measuring it spends the cost the decision avoids. File:
   `.agent/2026-08-28f-degree-audit/breadth-add.yaml`. **Read "Breadth is last" first.**

5. **Phase 1b and its follow-up are COMPLETE — item RETIRED.** Detail moved verbatim to
   `STANDING-FACTS.md` 2026-08-28h, including why #230 is keyed on the `role_vetoed` MEMBER and
   must not be re-broadened to the review lane (D-354, D-359).

6. **`main` IS GREEN** and stayed green across #240-#243. The three deflakes behind that, and the
   standing rule they produced — **when a timing test flakes, ask what it MEASURED versus what it
   CLAIMS**, and **mutate every new assertion** — are in `STANDING-FACTS.md`.

7. **Re-read the queue after the next run.** The D-333 band moved 6,123 evaluations into `uncertain`
   and D-332 routes them; `.agent/2026-08-27-queue-split/` holds the read-only harness.
   `phase2_measure.py` correctly reports 0 movers — that is "already moved", not a broken query.

8. **Deferred with numbers, do not re-derive:** job-apps' preferred-vs-required HEADING state
   machine is **2 of 286** and architectural (D-320). The years-detection gap that sat here was
   addressed by #218 — read that PR, not the old 24-leads/1.3% figure.

## Owner-gated — do NOT start or decide unilaterally

9. **Mit's two résumé content calls** — whether to send a document at all; the D-220 prose rewrites.
10. **P2 item 8 — the onboarding field-taxonomy gatherer. DEFERRED by Mit 2026-08-28**: no time before
   he steps back from active work (~2026-08-31, unattended after). **Not dropped — an accepted known
   gap**, and the last multi-tenancy gap of its kind. Still owner-gated and still needs its own
   brainstorm; D-054 forbids us authoring non-tech field content.
11. **`add-evidence` takes no bundle lock** (D-143) — raise before two authoring agents run against
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
| **boardwatch cannot see ~90% of job-apps' eligible yield** | 41 of 530 records (7.7%) at a watched company — **a parallel session re-measured reach at ~10.1% on the 344-board fleet on 2026-08-28; NOT re-derived here, so treat 7.7% as the reproducible figure and 10.1% as owed a check**; 352 companies in the set, 24 watched. Amazon/TikTok/Apple/ByteDance use none of the 6 ATS, so a slug cannot reach them. Closing it means a new discovery lane — GitHub new-grad lists are 19.1% of yield for ~5 public-repo GETs and are NOT the ToS trap the v2 decision was written about. **Reopens D-008** | **Mit** (reverses a shipped decision) |
| **Citi sits at 13.1% coverage, permanently** | Workday's `total` censors at 2,000; the facet sum (uncapped, control-verified) says 4,589. Our pager wraps at ~2,000 too, so post-drain Citi holds ~2,214 of 4,589 and nothing reports it | **Mit** (input-side) |
| **`unchanged` staleness is now BOUNDED (D-298, #153)** | The `unchanged` verdict comes from the upstream HTTP validator (ETag/Last-Modified → 304), not a boardwatch payload hash. `validator_max_age_hours` (default 24) drops a validator older than the TTL, forcing an unconditional refetch, so a permanently-stale upstream can no longer freeze a board forever — the silent-staleness window is capped at the TTL, and a regression test now exercises the aged-validator refetch. Still open: within the TTL an `unchanged` is trusted with no independent check. The separate "59 of 135 boards listed nothing" figure was a **`postings_listed`-on-304 artifact — CORRECTED to 17 real dead-weight (D-300)**, now cleaned; the 118 `ok` boards hold 39,253 open postings | open (mitigated) |
| **`resume.yaml` is an IMPORT SOURCE, never hand-fixed** | D-155. Mit pins `resume_max_pages=1`; never advise 2 | Mit |
| **`boardwatch top` advances the queue by default** | records `seen` unless `--no-record`; relevant to Gate P6's clean window | P6 |
| **A live store is readable ONLY via Python `sqlite3` `?mode=ro`** | the `sqlite3` CLI with `?mode=ro` fails `CANTOPEN(14)` on a cleanly-checkpointed store (no `-shm`; not the sandbox), and `?immutable=1` skips the WAL so it is STALE against a live writer. Mid-run progress: `SELECT COUNT(*) FROM eligibility_evaluations WHERE run_id=N` (D-268) | tooling |
| **`boardwatch web` IS RUNNING — started 2026-08-29d** | Started from the primary checkout on `main` with `--port 0 --no-open` and **verified through a second path**: `GET /` returns 200 and `GET /api/runs` returns **401 without a token and 200 with the bearer**. The session URL is `http://127.0.0.1:<port>/#<token>` — the token rides in the **fragment** so it never reaches a server log or a `Referer`, it is stable, and it lives at `~/Library/Application Support/boardwatch/web-token` (mode 0600). **The port is whatever `--port 0` picked**, so read it from the process rather than assuming: `lsof -nP -iTCP -sTCP:LISTEN -a -p $(pgrep -f 'boardwatch web')`. It was stopped and restarted once during this session to take the store lock for the D-370 cold scan — **never write to the store with the viewer up**, a WAL two-writer deadlock against a running pipeline is on record. The underlying skew is still structural (D-360): the bundle is served from **disk** and the API from the Python imported **at startup**, so any merge or branch switch under a running viewer separates the two — **it is now stale against `main` the moment #245 landed, so restart it after any merge.** #232 makes a missing field degrade to the pre-#224 view instead of blanking the page | **Mit** (restart after merges) |
| **The unattended 04:00 tick runs the PRIMARY checkout's branch — and it is now PROVEN to fire** | Run 131 (2026-08-29, `runs = 1`, exit 0) was the first real unattended tick. The launchd job invokes the **editable** venv at `boardwatch/.venv/bin/boardwatch`, so whatever branch that tree is parked on IS the unattended run's code and `rules.yaml`. Checked at this close and currently harmless (the tree is on `main`). **Park it on `main` before ending every session** — from ~2026-08-31 a stray branch changes EVERY subsequent run, not one. Closing it mechanically means pointing the plist at a worktree pinned to `main`, which moves a scheduled job and a venv | **Mit** (mechanism); every session (discipline) |
| **hiring.cafe lane is DOWN; the cause is known and the FIRST LEVER IS PULLED** | **D-369/#245 shipped the search route's browser navigation header set, and the 04:00 run is its readout.** D-368's ranking was corrected on evidence: its **UA premise is FALSE** (we have sent a Chrome UA since the lane shipped) and its **volume premise did not survive the run log** (run 128, the last working search, spent ~28 requests; run 131 was refused on its FIRST request 14 h later). **Do NOT probe, and do NOT change anything else until the run reads out.** If it fails, headers are eliminated and the remainder is volume (weaker) and endpoint — where **path-scoped protection on `/jobs/*`** is the strongest hypothesis and the **owner's** call, because robots allows `/jobs/` and disallows job-apps' query form. Half the lane coverage job-apps' edge comes from | **Mit** (read the 04:00 run; then the endpoint call, or send the drafted access request) |
