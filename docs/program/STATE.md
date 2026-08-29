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

**The live six-blocker map is the OWNER'S and is NOT to be reverted (D-350 found it, D-351 rules
it).** D-350 found `degree` armed where D-321 had recorded *"Owner's call, not taken"*; Mit confirmed
he wanted it. His constraint was precision — *"I just don't want it to reject jobs which are
genuinely for me"* — and D-352 above is the audit that answers it.

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
**Re-probed 2026-08-28 ~19:20 CDT and it has NOT lifted** — same 403, and the response now also
carries `cf-mitigated: challenge` and `server: cloudflare`, which names the mechanism outright.
`/robots.txt` still returns 200 and still `Allow`s `/jobs/`. 2026-08-28 ran FOUR runs against a
normal cadence of one, so our own volume remains a plausible trigger. **Browser automation /
challenge-solving is out of scope and is not the answer.** This is half the lane coverage that
job-apps' daily edge comes from. **It cannot make a run fatal** — `is_systemic_scan_outage` reads
board counts only, never lanes — so it costs coverage, not availability.

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

1. **hiring.cafe is STILL DOWN — re-probed at this close and it has not lifted (D-356).** It is
   the only thing losing real coverage. Re-probe with ONE polite
   `GET https://hiringcafe.com/jobs/software-engineer` carrying boardwatch's own UA: a 200 with
   `__NEXT_DATA__` means the challenge lifted and the lane self-heals on the next run; a 403 with
   `Just a moment...` and `cf-mitigated: challenge` means it has not. **One probe per session, not
   more** — IP reputation is the leading hypothesis, so probing hard is the one thing that could
   keep it closed. **Do not work around it**: browser automation is out of scope and this project
   does not circumvent bot protection. **The owner-side move is drafted and NOT sent** —
   `.agent/2026-08-28g-session/hiringcafe-access-request.md` holds a request for API access plus the
   evidence it rests on; it is Mit's to send, edit or discard, and it deliberately does not look up
   a contact address from this machine while we are being challenged. **Until it lifts, treat lane
   coverage as HALVED.**

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
   **Still deferred at the 2026-08-28g close on the SAME reason, re-checked: hiring.cafe is still
   refusing us**, so the condition that produced the deferral has not changed. Not re-litigated.
   **Read "Breadth is last" first — the slate cap is armed but has still not been observed FIRING.**

5. **PHASE 1B IS COMPLETE AND SO IS ITS FOLLOW-UP — retire the whole item (D-354, D-359).** Split
   #195, redesign #223, per-row hold reason #224, `ROLE VETOED`/`OFF TARGET` duplication #230.
   `role_vetoed` and `role_unconfirmed` stay separate — only `not_swe` is a veto. **#230 is
   deliberately NARROWER than D-354 specified: suppression is keyed on the `role_vetoed` MEMBER, not
   the review lane, because `classify` reaches `ineligible_verdict` and `non_us_location` first and
   either can carry a genuinely separate `off_target`. Do not re-broaden it to the lane** (D-359).

6. **`main` IS GREEN — confirmed, and it took THREE fixes, not two (D-357, D-358).** Verified at
   this close: `de65448` (#227), `b1ff14b` (#228) and `b0ecfe3` (#229) are three consecutive green
   `main` runs after the deflake. The day's flakes were **#225** (lane cost boundary, from #217),
   **#227** (`test_a_locked_store_answers_503_without_stalling`, which took all three macOS jobs at
   once — macOS runs unsharded), and **#222's own new pacing test**, found this session. **No
   threshold was weakened in any of the three** — each now asserts its property directly and is
   strictly tighter than what it replaced.

   **The standing rule, now with three instances behind it: when a timing test flakes, ask what it
   MEASURED versus what it CLAIMS.** All three measured a proxy whose noise straddled the bound;
   none needed a wider bound. **And mutate every new assertion** — two of the three had a *second*
   defect where the expected value was reachable by a route the test did not intend (#227 compared
   against a constant the implementation also reads; #222 set the delay equal to the floor it was
   supposed to prove was overridden).

7. **Re-read the queue after the next run.** The D-333 band moved 6,123 evaluations into `uncertain`
   and D-332 routes them; `.agent/2026-08-27-queue-split/` holds the read-only harness.
   `phase2_measure.py` correctly reports 0 movers — that is "already moved", not a broken query.

8. **Deferred with numbers, do not re-derive:** job-apps' preferred-vs-required HEADING state machine
   is **2 of 286** and architectural (D-320). *(The residual years-detection gap was the other item
   here; #218 addressed it — read that PR rather than the old 24-leads/1.3% figure.)*

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
| **No alerting path AT ALL — a failed unattended run is SILENT** | Nothing outside a run can detect a missed tick (the funnel heartbeat is written only from inside `runner.py`), **and a run that DOES fire and fails is equally silent**: both notify tiers are OFF (`desktop_enabled=False`, `webhook_enabled=False`, no `[notify]` section) and **`notify` is a SEPARATE command the launchd job never invokes** — the plist runs `boardwatch run --project` and nothing else. Compounds D-361: disk fills, runs fail, nobody is told | P3 / **Mit** |
| **`resume.yaml` is an IMPORT SOURCE, never hand-fixed** | D-155. Mit pins `resume_max_pages=1`; never advise 2 | Mit |
| **`boardwatch top` advances the queue by default** | records `seen` unless `--no-record`; relevant to Gate P6's clean window | P6 |
| **A live store is readable ONLY via Python `sqlite3` `?mode=ro`** | the `sqlite3` CLI with `?mode=ro` fails `CANTOPEN(14)` on a cleanly-checkpointed store (no `-shm`; not the sandbox), and `?immutable=1` skips the WAL so it is STALE against a live writer. Mid-run progress: `SELECT COUNT(*) FROM eligibility_evaluations WHERE run_id=N` (D-268) | tooling |
| **DISK is the binding constraint on unattended running — RAISED, UNANSWERED, nothing done** | Volume at **99%, 3.8 GiB free**; store **3.93 GB** growing **~200-500 MB/day** = **~8-19 days** of headroom, against unattended running from ~08-31. **`VACUUM` reclaims 0** (freelist empty) and closed postings hold only 0.20 GB, so neither is the answer. Four options priced in D-361. **A preflight guard was written up and deliberately NOT shipped: a new fatal path can halt EVERY run, and silence is not approval.** Freeing this session's worktrees returned 589 MB (99% -> 98%) | **Mit** — RE-ASK |
| **The running `boardwatch web` viewer is STALE and must be restarted** | It serves the bundle from **disk** but the API from the Python it imported **at startup** (D-360), so it was serving a 19:30 bundle off an 06:25 process and returning all 222 review rows with **no `review_reason` key**. Before #232 that blanked the page — no error boundary, so the throw unmounted everything. #232 makes it degrade to the pre-#224 view instead, but **only a restart makes the viewer correct**, and it binds `--port 0` so the port changes | **Mit** (restart when convenient) |
| **The unattended 04:00 tick runs the PRIMARY checkout's branch** | The launchd job invokes the **editable** venv at `boardwatch/.venv/bin/boardwatch`, so whatever branch that tree is parked on IS the unattended run's code and `rules.yaml`. Checked at this close and currently harmless (the tree is on `main`). **Park it on `main` before ending every session** — from ~2026-08-31 a stray branch changes EVERY subsequent run, not one. Closing it mechanically means pointing the plist at a worktree pinned to `main`, which moves a scheduled job and a venv | **Mit** (mechanism); every session (discipline) |
| **hiring.cafe lane is DOWN behind Cloudflare** | Run 130: total outage, `403` + `Just a moment...` on `/jobs/` with boardwatch's own UA, while `/robots.txt` returns 200 and explicitly `Allow`s `/jobs/`. **Not a boardwatch defect and not a robots violation** — bot protection. Re-probe before assuming it is permanent; 2026-08-28 ran 4 runs against a cadence of 1, so our own volume is a plausible trigger. **Browser automation is out of scope and is not the remedy.** Half the lane coverage job-apps' edge comes from (D-356) | **Mit** (owner-side: ask for API access) |
