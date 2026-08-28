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

**THE SLATE CAP IS ARMED AND REPORTING, AND ITS FIRST OBSERVATION IS A MEASURED ZERO (D-345, #215;
run 130).** `hidden_slate_cap = 0`. The bucket is never identity-gated, so that 0 is a real reading
and not a disarmed detector. Run 130 delivered **10 leads across 10 DISTINCT companies** where run
129 spent 9 of 10 slots on one CGS Federal requisition — but **that diversity was natural ranking,
not the cap**; the cap freed nothing. So D-345 is observed CORRECT, **not yet observed EFFECTIVE**,
and the next location-split day is still the test. Design detail moved to `STANDING-FACTS.md`.

**`degree` IS AUDITED AND CLOSED — NOTHING NEEDED SOFTENING (D-352, #221).** D-351's audit is DONE
and the item it raised is RETIRED. **Zero SWE-titled postings are blocked by any degree rule
anywhere in the live corpus.** Of 164 in-field `unmet` postings, 71 are sole-cause and every one was
read by hand: all non-SWE (accounting 24, finance/tax 12, nursing 11, engineering 11, other 13).
The abstain side costs 6 SWE postings and all six abstains are honest. **Two extraction defects were
fixed anyway, for MULTI-TENANCY not for Mit's yield** — the `education` surface matched equivalence
boilerplate (~1,200 frames vs ~57 genuine) and the relatedness escape could not read
`other`/`another` (483 postings). **One widening was REJECTED as measured NET HARMFUL:**
`degree_equivalence` for "equivalent combination of education and experience" would turn **30 `met`
rows into abstains to rescue 13 `unmet`**. Do not re-propose it without sentence-scoping it first.

**`degree` BLOCKING IS CONFIRMED BY THE OWNER — WHAT IS OWED IS AN AUDIT, NOT A REVERT (D-350 found
it, D-351 rules it).** D-350 found `degree` armed where D-321 had recorded *"Owner's call, not taken"*;
Mit confirmed he wanted it, so **the live six-blocker map is correct and is NOT to be reverted.** His
constraint is about PRECISION: *"I just don't want it to reject jobs which are genuinely for me."*
**So the 410 degree-attributed `ineligible` evaluations are owed an audit and the 298 on the
`_in_field` rules are the target** — field-of-study matching, live-capable only since D-326, and a
wrong field match is exactly the failure he named. **Soften nothing before the audit.**

**SAY WHICH ELIGIBILITY POLICY YOU MEAN, EVERY TIME (D-350)** — catalog and live profile diverge on
**five of six** families (`rules.yaml`: only `work_auth` is a `blocker` default; live store: all six).
By design, but it makes an unqualified severity claim uncheckable, and the gap is wide: #218's floors
give **1,228 verdict flips live vs 0 published**. Full rule in `STANDING-FACTS.md`.

**RUN 130 WAS TAKEN AND IT IS THE FIRST FULL RECOMPUTE ON #218's `rules_hash`** — 137.2 min against
run 129's 44.7, of which **eligibility alone is 84.7 min**. Read the STAGE, never the total, when
judging anything about fetching. It closes two open reads: `hidden_slate_cap` above, and the lane
cost split below. Numbers: METRICS 2026-08-28f.

**THE LANE QUESTION IS CLOSED (D-346/D-347).** Run 130's linkedin lane is
`fetch=277.3s apply=0.22s` — **100% fetch**. The lane stage is entirely upstream throttling and there
is **no contention on `apply_board`**, so D-347's estimate holds and no further lane work is
warranted. Do not re-propose lane parallelism.

**THE hiring.cafe LANE IS DOWN, AND IT IS NOT OUR BUG (D-356).** Run 130 raised
`SearchPageError("every role facet yielded nothing (14 searched, 14 request failures)")` — a TOTAL
outage after working on every run through 129 (85 attempted / 79 resolved). Probed: `/jobs/` returns
**403 with Cloudflare's `Just a moment...` interstitial**, while `/robots.txt` returns 200 and
**explicitly `Allow`s `/jobs/`** — so boardwatch is fully compliant and this is bot protection.
**Back off and re-probe**; 2026-08-28 ran FOUR runs against a normal cadence of one, so our own
volume is a plausible trigger. **Browser automation / challenge-solving is out of scope and is not
the answer.** This is half the lane coverage that job-apps' daily edge comes from.

**Everything below this line is carried and remains true.** The provisional pass is held by the owner
(but see the restarted counter under Phase status); Gate P6 is 4 of 4; `DEFAULT_TOP_N` is 10 and is a
HOLDING value (D-293); the fleet is 344 watched boards; breadth is argued on precision and capacity,
never an application count (D-312). Board cost is provider-weighted and **s/board is a lying unit** —
`workday` is ~73% of a run; size batches by provider mix, never board count. **Raising the
`scan_workers` ceiling above `le=8` stays RETIRED** (D-344): run 129 finished 343 of 344 boards in
27.0 min, `lowes.wd5` taking 5.9 more alone. Run 129 was **44.7 min** vs run 128's 132.4 — **2.82x =
1.58x backlog drain x 1.78x parallelism**, only the 1.78x code. Numbers: `METRICS.md`.

---

## Next action

1. **RE-PROBE hiring.cafe FIRST — it is the only thing losing real coverage right now (D-356).**
   One polite `GET https://hiringcafe.com/jobs/software-engineer` with boardwatch's own UA. A 200
   with `__NEXT_DATA__` means the challenge lifted and the lane self-heals on the next run; a 403
   with `Just a moment...` means it has not. **Do not work around a Cloudflare challenge** — browser
   automation is out of scope and this project does not circumvent bot protection. If it persists,
   the owner-side move is to ask hiring.cafe for API access (`/jobs/` is explicitly `Allow`ed in
   their robots.txt). **Until it lifts, treat lane coverage as HALVED.**

2. **THE PACING TRIAL IS HELD, NOT CANCELLED (D-355).** #222 is merged and the lever ships
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

   **Before ANY pull or store write, guard on PROCESS liveness, never the `runs` table** — the probe,
   why the `awk '$2==1'` form was wrong in the dangerous direction (D-335), and why `ps -o comm` gives
   a false IDLE on macOS are all in `STANDING-FACTS.md`. `runs.finished_at` precedes process exit by
   ~90 s (D-024). **`pkill -f "make check"` is NOT worktree-scoped** — kill by PID.

   **The venv is EDITABLE, so a branch switch MUTATES a live run's code and `rules.yaml`.** While a
   run is in flight, do not check out any branch whose diff touches `src/boardwatch/**`. Park on the
   branch the run started from; use a WORKTREE for parallel code work. The Bash tool's cwd also
   PERSISTS across calls — use absolute paths for writes.

   **The scratchpad directory is SHARED with subagents, not per-agent.** Name every per-launch file
   uniquely; a shared *sentinel* is worse than a shared log, since reading it means reading someone
   else's exit code.

3. **THE PROVISIONAL PASS IS ALLOWED TO SLIP — Mit's ruling at this close: "work comes first"
   (D-351).** #218 reset the 3-clean-post-fix-run counter and it is **not being chased** before he
   steps back ~2026-08-31. **Read this as UNBLOCKING, and it is the more useful half:** eligibility is
   **NOT frozen** — the freeze was only ever implied by wanting the 3 runs — so rules and eligibility
   work may land freely, including whatever the `degree` audit turns up. **Stop pricing a `rules_hash`
   bump as costly on this basis** until the owner reopens the pass. The P4 blind review remains passed
   (2026-08-26) and does not repeat.

4. **BREADTH IS PREPPED BUT NOT APPLIED — 39 boards, TWO batches, and the naive list was WRONG.**
   Re-derived read-only from job-apps' `dedup_ledger.sqlite` and written to
   `.agent/2026-08-28f-degree-audit/breadth-add.yaml`; import with
   `boardwatch companies import --verify <file>` (`--verify` probes each board and skips anything
   unproven). **The cross-reference had to be NORMALISED:** boardwatch stores a Workday slug as the
   full composite `{tenant}.{wdN}.myworkdayjobs.com/{tenant}/{site}` while a job URL gives
   `.../[locale/]{site}`, so comparing raw marked **Micron and HPE as addable when both are already
   watched**. Normalising moved 14 into a duplicate bucket. Toyota IS a real addition — the tenant is
   watched at site `tmna`, this is the sibling site `tmna_professional` (the HPE precedent).

   **It is two batches because s/board is a lying unit:** ashby 7 + greenhouse 6 + lever 2 = **15
   cheap boards** (~30 s of added fetch) versus **20 workday + 4 smartrecruiters** that are COLD,
   spend `detail_fetch_budget` on a first scan, and have **never been timed cold** (STATE's own open
   question). **Deferred on 2026-08-28** because Mit held the pacing trial and chose to back off
   third-party load for the night, and adding 24 cold boards is the opposite of backing off.
   **Read "Breadth is last" first — the slate cap is armed but has still not been observed FIRING.**

5. **PHASE 1B IS COMPLETE (D-354) — retire it from this list.** The split was ALREADY shipped in
   #195 (STATE was stale on that; the repo won), the redesign landed as **#223**, and the per-row
   hold reason as **#224**. D-351's named defect is closed: every review row now names why it was
   held (`ROLE UNCONFIRMED` / `ROLE VETOED` / `OUTSIDE THE US`), verified by rendering the merged
   tree. `role_vetoed` and `role_unconfirmed` are separate on purpose — only `not_swe` is a veto and
   the gate's `uncertain` is an abstain. **One cosmetic follow-up:** `ROLE VETOED` and `OFF TARGET`
   now duplicate on the same row; suppress `off_target` on REVIEW rows only, since it is still the
   sole signal on an APPLY row (an `eligible` off-target lead correctly sits there wearing it).

6. **`main` WAS RED ALL DAY AND #225 IS THE FIX (D-357).** `test_the_cost_boundary_sits_between_fetching_and_applying`
   from #217 was a wall-clock flake — a 50 ms window on a 300 ms sleep — and failed six of the last
   eight `main` pushes. **It was not weakened:** the clock was removed and the assertion is now
   EXACT EQUALITY against a counter the test advances, which is strictly tighter, and all three
   original mutants still fail. **A red `main` is how real failures get ignored** — check it is green
   before trusting any CI result, and note that a green PR today may only be green because a job was
   re-run.

7. **Re-read the queue after the next run.** The D-333 band moved 6,123 evaluations into `uncertain`
   and D-332 routes them; `.agent/2026-08-27-queue-split/` holds the read-only harness.
   `phase2_measure.py` correctly reports 0 movers — that is "already moved", not a broken query.

8. **Batch 2 of the ~765 discover candidates is still a sizing question with an answer** — the ~325
   cheap ones go in ONE batch; SmartRecruiters 107 ≈ +40 min; Workday 333 ≈ +122 min and must be
   chunked at ~100. **Probe ~10 cold Workday boards first** — no cold Workday or SmartRecruiters
   board has ever been timed, and they are the two providers that burn a per-posting detail budget on
   a first scan.

9. **One pre-existing defect remains, and it is deliberate:** `tests/unit/test_web_server.py:764`
   (`assert elapsed < 3.0`) is a genuine load-dependent flake — **do not weaken the threshold to
   green a gate; re-run the job.** macOS runs the suite unsharded, so it has MORE exposure per push.

10. **Deferred with numbers, do not re-derive:** job-apps' preferred-vs-required HEADING state machine
   is **2 of 286** and architectural (D-320). *(The residual years-detection gap was the other item
   here; #218 addressed it — read that PR rather than the old 24-leads/1.3% figure.)*

## Owner-gated — do NOT start or decide unilaterally

11. **Mit's two résumé content calls** — whether to send a document at all; the D-220 prose rewrites.
12. **P2 item 8 — the onboarding field-taxonomy gatherer. DEFERRED by Mit 2026-08-28**: no time before
   he steps back from active work (~2026-08-31, unattended after). **Not dropped — an accepted known
   gap**, and the last multi-tenancy gap of its kind. Still owner-gated and still needs its own
   brainstorm; D-054 forbids us authoring non-tech field content.
13. **`add-evidence` takes no bundle lock** (D-143) — raise before two authoring agents run against
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
| **No external missed-window alarm** | nothing outside a run can detect a missed 08:00; the funnel heartbeat is only written from inside `runner.py` | P3 |
| **`resume.yaml` is an IMPORT SOURCE, never hand-fixed** | D-155. Mit pins `resume_max_pages=1`; never advise 2 | Mit |
| **`boardwatch top` advances the queue by default** | records `seen` unless `--no-record`; relevant to Gate P6's clean window | P6 |
| **A live store is readable ONLY via Python `sqlite3` `?mode=ro`** | the `sqlite3` CLI with `?mode=ro` fails `CANTOPEN(14)` on a cleanly-checkpointed store (no `-shm`; not the sandbox), and `?immutable=1` skips the WAL so it is STALE against a live writer. Mid-run progress: `SELECT COUNT(*) FROM eligibility_evaluations WHERE run_id=N` (D-268) | tooling |
| **hiring.cafe lane is DOWN behind Cloudflare** | Run 130: total outage, `403` + `Just a moment...` on `/jobs/` with boardwatch's own UA, while `/robots.txt` returns 200 and explicitly `Allow`s `/jobs/`. **Not a boardwatch defect and not a robots violation** — bot protection. Re-probe before assuming it is permanent; 2026-08-28 ran 4 runs against a cadence of 1, so our own volume is a plausible trigger. **Browser automation is out of scope and is not the remedy.** Half the lane coverage job-apps' edge comes from (D-356) | **Mit** (owner-side: ask for API access) |
