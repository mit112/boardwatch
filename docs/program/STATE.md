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

**`degree` is AUDITED AND CLOSED — nothing needed softening (D-352, #221); the widening is measured NET HARMFUL.** Moved verbatim to `STANDING-FACTS.md` 2026-08-29.

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

**The lane question is CLOSED (D-346/D-347) — do not re-propose lane parallelism.** Moved verbatim to `STANDING-FACTS.md` 2026-08-29.

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

**THE WEB VIEWER NOW HAS ERROR BOUNDARIES, AT FOUR SCOPES (D-363).** D-360 named the structural
gap and left it open; it is closed. A component that throws while rendering now costs a card, not
the page: root, route switch, review lane, detail pane, each keeping a different thing alive. The
review lane is contained SEPARATELY from the apply lane on purpose. **Verified by reproducing the
pre-#232 defect** — 408 apply rows survived, and removing that one boundary took them **408 -> 0**.
**The "no frontend test suite" gap this left open is now CLOSED (#241).** vitest + jsdom run as a
`web-test` prerequisite of `make check` and as a CI step (nothing in CI runs `make check` on a PR). Eight
tests cover the four boundary scopes and the skew guards, and **each was confirmed RED against the broken
implementation** — removing any one boundary, or tightening any `== null` to `=== null`, fails the suite.
`make check` now needs node, deliberately not conditional: a check that skips itself where the toolchain
is missing reports green while verifying nothing.

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
(but see the restarted counter under Phase status); Gate P6 is 4 of 4; `DEFAULT_TOP_N` is 10 and is a
HOLDING value (D-293); the fleet is 359 watched boards; breadth is argued on precision and capacity,
never an application count (D-312). Board cost is provider-weighted and **s/board is a lying unit** —
`workday` is ~73% of a run; size batches by provider mix, never board count. **Raising the
`scan_workers` ceiling above `le=8` stays RETIRED** (D-344): run 129 finished 343 of 344 boards in
27.0 min, `lowes.wd5` taking 5.9 more alone. Run 129 was **44.7 min** vs run 128's 132.4 — **2.82x =
1.58x backlog drain x 1.78x parallelism**, only the 1.78x code. Numbers: `METRICS.md`.

---

## Next action

> **D-361's two unattended risks are ANSWERED AND CLOSED — do not re-raise either (D-362).** Both were
> re-measured before being re-asked and **both premises had moved**: disk is **83%, 35 GiB free** with a
> ~70-day worst-observed runway (Mit's call: **no retention policy**), and alerting was never absent —
> the **D-260 heartbeat** was wired inside `runner.py` all along and is now armed in the launchd plist.
> The full reasoning moved to `STANDING-FACTS.md` at the 2026-08-29b close. **Edit that plist TEXTUALLY**
> — PlistBuddy strips the comments that carry the reasoning.
>
> **STILL OWED: confirm the first REAL ping landed.** Re-checked at this close: `runs = 0`, `last exit
> code = (never exited)`, log mtime 08-28 06:13 — the counter was reset again by this session's plist
> reload for `--top 40`, which is expected and not a fault. The 04:00 tick on 2026-08-29 is the first
> unattended one. **A setup ping already made the monitor green, so green alone still proves nothing.**
> **`launchctl list` col 2 is the WRONG route** — it prints `0` for a job that has NEVER run. Use
> `launchctl print gui/$(id -u)/com.boardwatch.run` and read **`runs = N`** plus `last exit code`, and
> cross-check the **mtime** of `~/Library/Logs/boardwatch-run.log`, never its content.
> **It cannot false-alarm on hiring.cafe** — a lane outage never sets `fatal` (verified).

1. **hiring.cafe is STILL DOWN — re-probed 2026-08-29 ~02:05 CDT and it has NOT lifted (D-356).**
   Same `403`, still `cf-mitigated: challenge` and `server: cloudflare`, no `__NEXT_DATA__`,
   5,578-byte interstitial. It is
   the only thing losing real coverage. Re-probe with **ONE** polite
   `GET https://hiringcafe.com/jobs/software-engineer` under boardwatch's own UA — 200 +
   `__NEXT_DATA__` means it lifted and the lane self-heals next run. **One probe per session**: IP
   reputation is the leading hypothesis, so probing hard is the one thing that could keep it closed.
   **Do not work around it**: browser automation is out of scope. **The owner-side ask is
   drafted and NOT sent** in `.agent/2026-08-28g-session/hiringcafe-access-request.md` — Mit's to
   send, edit or discard. **Until it lifts, treat lane coverage as HALVED.**

   **THE OUTAGE HAS SELF-CLEARED BEFORE, SO 08-28 IS NOT PROVEN TO BE A STEP CHANGE (D-364).** The
   identical `SearchPageError` appears at `boardwatch-run.log:4547` in **run 116 (2026-08-26)** and
   the lane recovered unaided across the next ten runs. The earlier "worked on every run through
   129" reading was wrong. **Waiting is a stronger option than it looked.**

   **THE DISCRIMINATOR IS job-apps' 08:30 RUN AND IT COSTS US NOTHING (D-364).** job-apps reaches
   hiring.cafe **daily from this same machine — 10 of 10 days, zero errors, 381 roles on 08-28** —
   on a launchd schedule at 08:30. But its last fetch was **08:33 CDT on 08-28** and boardwatch's
   first 403 came from run 130 at **15:27 CDT**, so **it has not been tested since the block and IP
   reputation is NOT ruled out.** Its next scheduled run is the experiment. Read
   `resumes/_logs/2026-08-29_scheduled_discovery_0830.log` under job-apps for the `hiring.cafe`
   block, or query `acquisition_observations` for `source='hiringcafe'`. **Do NOT change our UA or
   endpoint before that reads out** — two changes at once spoils the only free experiment there is.

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

4. **BREADTH BATCH 1 IS APPLIED; BATCH 2 REMAINS DEFERRED — 39 boards, TWO batches (D-367).**
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
   question). **Batch 1 (the 15 cheap boards) SHIPPED 2026-08-29 — fleet 344 -> 359**, all 15
   re-verified `watched=1` against the source YAML rather than trusting the command's own report.
   The cold-scan objection was CHECKED and is **provider-specific**: only `workday` and
   `smartrecruiters` spend `detail_fetch_budget`, so the cheap batch carried none (D-367).
   **Batch 2 (the 24 cold boards) stays deferred** on the unchanged reason — hiring.cafe is still
   refusing us and those boards have never been timed cold. Not re-litigated.
   **Read "Breadth is last" first — the slate cap is armed but has still not been observed FIRING.**

5. **Phase 1b and its follow-up are COMPLETE — item RETIRED.** Detail moved verbatim to
   `STANDING-FACTS.md` 2026-08-28h, including why #230 is keyed on the `role_vetoed` MEMBER and
   must not be re-broadened to the review lane (D-354, D-359).

6. **`main` IS GREEN** — three consecutive green runs; which three flakes, and why each fix was
   strictly tighter, moved verbatim to `STANDING-FACTS.md` 2026-08-28h (D-357, D-358).

   **The standing rule, three instances behind it: when a timing test flakes, ask what it MEASURED
   versus what it CLAIMS** — all three measured a proxy whose noise straddled the bound, and none
   needed a wider bound. **A failure UNDER a sleep-derived bound proves the measurement wrong, not
   the machine slow.** **And mutate every new assertion:** two of the three also had the expected
   value reachable by a route the test did not intend (a constant the implementation also reads; a
   delay set equal to the floor it was meant to prove was overridden).
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
| **`boardwatch web` is NOT RUNNING — START it, don't restart it** | Re-checked 2026-08-29 00:00: still no process, 8787 still Bridge. **Do NOT start it while a run is live or imminent** — the viewer's context path is a write path and a WAL two-writer deadlock against a running pipeline is on record; start it AFTER a run lands. **Otherwise it is worth more than it was**: the D-363 error boundaries only protect a viewer that is actually up, and starting it is still what makes the viewer send `review_reason`. Original note — checked 2026-08-28: no `boardwatch web` process exists; port 8787 is an unrelated `python3.1` (Bridge). D-360's note said *restart* it so the viewer sends `review_reason`; since nothing is up, the accurate instruction is **start** it. The underlying skew is still structural (D-360): it serves the bundle from **disk** but the API from the Python it imported **at startup**, so any merge or branch switch under a running viewer separates the two. #232 makes a missing field degrade to the pre-#224 view instead of blanking the page. It binds `--port 0`, so **the port is whatever it picks** | **Mit** (start when convenient) |
| **The unattended 04:00 tick runs the PRIMARY checkout's branch** | The launchd job invokes the **editable** venv at `boardwatch/.venv/bin/boardwatch`, so whatever branch that tree is parked on IS the unattended run's code and `rules.yaml`. Checked at this close and currently harmless (the tree is on `main`). **Park it on `main` before ending every session** — from ~2026-08-31 a stray branch changes EVERY subsequent run, not one. Closing it mechanically means pointing the plist at a worktree pinned to `main`, which moves a scheduled job and a venv | **Mit** (mechanism); every session (discipline) |
| **hiring.cafe lane is DOWN behind Cloudflare** | Run 130: total outage, `403` + `Just a moment...` on `/jobs/` with boardwatch's own UA, while `/robots.txt` returns 200 and explicitly `Allow`s `/jobs/`. **Not a boardwatch defect and not a robots violation** — bot protection. Re-probe before assuming it is permanent; 2026-08-28 ran 4 runs against a cadence of 1, so our own volume is a plausible trigger. **Browser automation is out of scope and is not the remedy.** Half the lane coverage job-apps' edge comes from (D-356) | **Mit** (owner-side: ask for API access) |
