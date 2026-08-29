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

**THE SLATE CAP HAS NOW FIRED — D-345 IS OBSERVED EFFECTIVE, AND THE OPEN TEST IS CLOSED.**
`hidden_slate_cap` = **5** on run 131, against 0 on run 130. `SLATE_CAP_PER_KEY = 1` is per-key and
independent of N, so widening the slate to 40 (D-366) made the collision surface: the cap deferred 5
leads that were the same company, title and byte-identical JD as one already on the slate. STATE
carried this as *"observed CORRECT, not yet observed EFFECTIVE"* with "the next location-split day"
as the outstanding test — **it closed as a free side effect of the cap change, not by waiting**.
Design detail is in `STANDING-FACTS.md`.

**`degree` is AUDITED AND CLOSED — nothing needed softening (D-352, #221); the widening is measured NET HARMFUL.** Moved verbatim to `STANDING-FACTS.md` 2026-08-29.

**The live six-blocker map is the OWNER'S and is NOT to be reverted (D-350/D-351).** Moved verbatim to
`STANDING-FACTS.md` 2026-08-29c.

**SAY WHICH ELIGIBILITY POLICY YOU MEAN, EVERY TIME (D-350)** — catalog and live profile diverge on
**five of six** families (`rules.yaml`: only `work_auth` is a `blocker` default; live store: all six).
By design, but it makes an unqualified severity claim uncheckable, and the gap is wide: #218's floors
give **1,228 verdict flips live vs 0 published**. Full rule in `STANDING-FACTS.md`.

**RUN 131 IS THE FIRST CLEAN UNATTENDED TICK AND IT VALIDATES THE CAP CHANGE.** 96.7 min against run
130's 137.2, **with 15 more boards and 4x the leads** — `unchanged` went 36 → 101 and eligibility was
not a full recompute. **`tailor` was 168.1 s for 40 leads = 4.20 s/lead**, so D-366's predicted
+5%-+23% landed at the **bottom** of its range: tailoring is 2.9% of the run. **`capped_by_top_n` rose
4,801 → 5,338**, so the reservoir refills faster than 40/day drains it — the cap was never what
rationed supply. **Read the STAGE, never the total**, when judging anything about fetching.
Numbers: METRICS 2026-08-29c.

**The lane question is CLOSED (D-346/D-347) — do not re-propose lane parallelism.** Moved verbatim to `STANDING-FACTS.md` 2026-08-29.

**THE DISCRIMINATOR READ OUT: IP REPUTATION IS RULED OUT AND THE CAUSE IS HOW BOARDWATCH ASKS
(D-368).** On 2026-08-29, same machine and same IP: **boardwatch run 131 FAILED** at 04:00-05:36
(`SearchPageError`, `boardwatch-run.log:5157`) and **job-apps SUCCEEDED at 08:30 — 248 roles, 8 terms,
zero errors**, three hours later. D-364 pre-registered exactly this rule. **"Wait it out" is retired**:
waiting cannot fix a difference in how we present ourselves. **The fix space is UNBLOCKED and ranked —
(1) volume, (2) UA, (3) endpoint — and must be changed ONE AT A TIME.** Browser automation stays out of
scope and is not the remedy. **Nothing was changed this session; it is next-session, owner-facing work.**

**The lane was down and it is not our bug (D-356).** Run 130 raised
`SearchPageError("every role facet yielded nothing (14 searched, 14 request failures)")` — a TOTAL
outage after working on every run through 129 (85 attempted / 79 resolved). Probed: `/jobs/` returns
**403 with Cloudflare's `Just a moment...` interstitial**, while `/robots.txt` returns 200 and
**explicitly `Allow`s `/jobs/`** — so boardwatch is fully compliant and this is bot protection.
**Re-probed 2026-08-28 ~19:20 CDT and it has NOT lifted** — same 403, and the response now also
carries `cf-mitigated: challenge` and `server: cloudflare`, which names the mechanism outright.
`/robots.txt` still returns 200 and still `Allow`s `/jobs/`. 2026-08-28 ran FOUR runs against a
normal cadence of one, so our own volume remains a plausible trigger. **Browser automation /
challenge-solving is out of scope and is not the answer.** This is half the lane coverage that
job-apps' daily edge comes from. **It cannot make a run fatal** — `is_systemic_scan_outage` reads
board counts only, never lanes — so it costs coverage, not availability.

**The web viewer's error boundaries (D-363) and its test suite (#241) are BOTH SHIPPED and settled.**
Four scopes, the review lane contained separately from the apply lane on purpose, and eight vitest
tests in the gate — each confirmed RED against the broken implementation. Moved verbatim to
`STANDING-FACTS.md` 2026-08-29c.

**THE DELIVERY CAP IS 40 AGAIN, SET IN THE PLIST AND NOT IN CODE (D-366).** D-293 ruling 5 held
`DEFAULT_TOP_N` at 10 *until rulings 1-4 landed*; 1/2/4 shipped, 3 was dropped (#148) and answered by the
D-345 slate cap, and #218/D-333/D-352 landed since — **the hold condition is met**. The measurement that
decides it also **corrects D-281**: runs 120-130 delivered **100% same-day** (median 0.00-0.73 d, 0% older
than 7 d), so the ranker is **recency-dominated** and run 130's **4,801 `capped_by_top_n`** postings are
**permanently buried, not queued**. At N=10 every unattended day discards its own surplus. The cost is a
RANGE driven by **JD richness**, not the LLM lane: **+5% to +23%** of a run. **`DEFAULT_TOP_N` in code
stays 10** — that is Mit's review capacity, not the mechanism. **No hash moves, so the provisional-pass
counter is NOT reset.** Revert = delete two `<string>` lines from the plist.

**BREADTH BATCH 1 IS APPLIED — the fleet is 359, not 344 (D-367).** The 15 cheap boards (ashby 7 /
greenhouse 6 / lever 2) imported with `--verify`, all 15 re-verified `watched=1` against the source YAML
rather than trusting the command. **The cold-scan objection turned out to be provider-specific**: only
`workday` and `smartrecruiters` spend `detail_fetch_budget`, so the cheap batch carries none. **The 24
cold boards stay deferred** on the unchanged reason.

**PROGRAM.md's B5 row was STALE BY 20 DECISIONS and is corrected (D-365).** It read "the instrument is
DORMANT, see D-282" long after **D-302 (#164)** armed the zero-output guard on run-scoped rank
attribution. B5 is **scoreable**. The general lesson: **when a program document cites a decision for a
capability GAP, verify the gap against the CODE — the citation dates the claim, it does not renew it.**

**Everything below this line is carried and remains true.** The provisional pass is held by the owner
(but see the restarted counter under Phase status); Gate P6 is 4 of 4; **the delivery cap is 40, set in
the plist (D-366)** — the code default `DEFAULT_TOP_N` stays 10 and D-293's hold on it is RELEASED, not
standing; the fleet is 359 watched boards; breadth is argued on precision and capacity,
never an application count (D-312). Board cost is provider-weighted and **s/board is a lying unit** —
`workday` is ~73% of a run; size batches by provider mix, never board count. **Raising the
`scan_workers` ceiling above `le=8` stays RETIRED** (D-344): run 129 finished 343 of 344 boards in
27.0 min, `lowes.wd5` taking 5.9 more alone. Run 129 was **44.7 min** vs run 128's 132.4 — **2.82x =
1.58x backlog drain x 1.78x parallelism**, only the 1.78x code. Numbers: `METRICS.md`.

---

## Next action

> **Mit's instruction at the 2026-08-29c close: the owner-facing items below are NEXT-SESSION work.**
> Nothing in them was started. The one thing that changed under them is item 1 — the hiring.cafe
> discriminator read out, so that item is now a FIX to decide, not a probe to repeat.

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

1. **hiring.cafe: THE DISCRIMINATOR HAS READ OUT — the next move is a FIX, not a probe (D-368).**
   On 2026-08-29, same machine and same IP: boardwatch run 131 **failed** (04:00-05:36,
   `SearchPageError`, `boardwatch-run.log:5157`); job-apps **succeeded** at 08:30 with **248 roles
   across 8 terms, zero errors**. D-364 pre-registered the rule, so this is decisive: **IP reputation
   is RULED OUT and the cause is HOW BOARDWATCH ASKS.** **Stop re-probing** — a probe can no longer
   tell us anything a fix would not, and more requests from this IP is the one move that could keep it
   closed. **Do NOT read lane absence as recovery either.**
   **The fix space, ranked, change ONE at a time:** (1) **volume** — 14 facets plus up to 60
   `/api/job-description` bodies per run (`DEFAULT_POSTING_BUDGET=60`) against job-apps' ~20-25
   GETs/day; largest measured gap, cheapest to change. (2) **UA** — we self-identify as a bot, job-apps
   sends real Chrome. (3) **endpoint** — `hiringcafe.com/jobs/{role}` plus an `/api/` endpoint job-apps
   never touches. **Browser automation stays OUT OF SCOPE and is not the remedy** — job-apps passes on
   plain stdlib `urllib.request`. **Robots compliance is not what Cloudflare scores**: robots disallows
   job-apps' `?searchState=` and allows our `/jobs/`, so the compliant client is the blocked one; stay
   on the allowed path. The owner-side access request is still drafted and unsent in
   `.agent/2026-08-28g-session/hiringcafe-access-request.md`. **Until it lifts, lane coverage is HALVED.**

2. **THE PACING TRIAL IS HELD, NOT CANCELLED (D-355).** #222 **is merged now** — the previous
   STATE claimed that while the PR was still OPEN and RED, and the repo won (D-358). The lever ships
   **disarmed**; arming is one config line plus a read-back check, and the whole procedure is in
   `.agent/2026-08-28f-degree-audit/RUN131-CHECKLIST.md`. Mit held it on 2026-08-28 because
   hiring.cafe began refusing us on a day that ran FOUR runs against a cadence of one, and
   **raising the per-host rate 0.6 -> 1.0 req/s on that day is the wrong direction**. Revisit once
   hiring.cafe is healthy and the run cadence is back to normal. **`Settings` does NOT forbid extra
   keys, so a typo'd config key arms NOTHING silently — always read the value back through
   `load_settings()`.**

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

4. **BREADTH BATCH 1 IS APPLIED; BATCH 2 REMAINS DEFERRED (D-367).** The 15 cheap boards
   (ashby 7 / greenhouse 6 / lever 2) shipped 2026-08-29 — **fleet 344 → 359**, all re-verified
   `watched=1` against the source YAML. Already producing: Relativity Space 346 open postings,
   OKX 341, NYT 178, Zip 122, Voleon 59. **The cold-scan objection was checked and is
   provider-specific** — only `workday` and `smartrecruiters` spend `detail_fetch_budget`.
   **Batch 2 (20 workday + 4 smartrecruiters) stays deferred**: never timed cold, and Workday is
   ~73% of a run's fetch cost. Sizing detail and the normalisation trap are in D-367 and
   `STANDING-FACTS.md`; the file is `.agent/2026-08-28f-degree-audit/breadth-add.yaml`.
   **Read "Breadth is last" first.**

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
| **`boardwatch web` is NOT RUNNING — START it, don't restart it** | Re-checked 2026-08-29 00:00: still no process, 8787 still Bridge. **Run 131 finished 05:36, so the window is OPEN until the next 04:00 tick — this is the time to start it.** Still **never while a run is live**: the viewer's context path is a write path and a WAL two-writer deadlock against a running pipeline is on record. **It is worth more than it was**: the D-363 error boundaries only protect a viewer that is actually up, and starting it is still what makes the viewer send `review_reason`. Original note — checked 2026-08-28: no `boardwatch web` process exists; port 8787 is an unrelated `python3.1` (Bridge). D-360's note said *restart* it so the viewer sends `review_reason`; since nothing is up, the accurate instruction is **start** it. The underlying skew is still structural (D-360): it serves the bundle from **disk** but the API from the Python it imported **at startup**, so any merge or branch switch under a running viewer separates the two. #232 makes a missing field degrade to the pre-#224 view instead of blanking the page. It binds `--port 0`, so **the port is whatever it picks** | **Mit** (start when convenient) |
| **The unattended 04:00 tick runs the PRIMARY checkout's branch — and it is now PROVEN to fire** | Run 131 (2026-08-29, `runs = 1`, exit 0) was the first real unattended tick. The launchd job invokes the **editable** venv at `boardwatch/.venv/bin/boardwatch`, so whatever branch that tree is parked on IS the unattended run's code and `rules.yaml`. Checked at this close and currently harmless (the tree is on `main`). **Park it on `main` before ending every session** — from ~2026-08-31 a stray branch changes EVERY subsequent run, not one. Closing it mechanically means pointing the plist at a worktree pinned to `main`, which moves a scheduled job and a venv | **Mit** (mechanism); every session (discipline) |
| **hiring.cafe lane is DOWN, and the cause is now KNOWN** | **The discriminator read out 2026-08-29 (D-368): same machine, same IP, same day — boardwatch run 131 FAILED at 04:00-05:36, job-apps SUCCEEDED at 08:30 with 248 roles / 8 terms / 0 errors.** IP reputation is **RULED OUT**; the cause is **how boardwatch asks**. **Stop probing — the next move is a fix**, ranked: (1) volume (14 facets + up to 60 `/api/job-description` bodies/run vs job-apps' ~20-25 GETs/day), (2) UA (we self-identify as a bot), (3) endpoint. **Change ONE at a time.** Browser automation stays out of scope and is NOT the remedy. Half the lane coverage job-apps' edge comes from | **Mit** (next session: pick the lever, or send the drafted access request) |
