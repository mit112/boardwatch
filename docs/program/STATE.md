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

**STATE §0 IS RULED AND SHIPPED: THE DELIVERY SLATE IS CAPPED AT ONE LEAD PER COMPANY, TITLE AND
BYTE-IDENTICAL JD (D-345, #215).** Run 129 spent 9 of its 10 slots on one CGS Federal
`ServiceNow Developer` — one `company_id`, one `normalized_title`, one byte-identical `content_hash`,
nine cities — and nothing suppressed it because `exact_quad`, the only suppressing kind, **includes
`locations`**. Mit's ruling: `(company_id, normalized_title, content_hash)` at **N=1**, delivery-time.
Sized over DELIVERED leads, not the corpus: over runs 119-129's 110 delivered leads it frees **9
slots, firing on exactly two runs (r120:1, r129:8), with ZERO collateral**. **The hash is in the key
because of run 125**, whose two Evlo AI leads share company and title but carry DIFFERENT hashes —
two real requisitions that a `(company, title)` key at N=1 would have cut to one. **This is NOT
D-295** (identity suppression, refused three times): nothing asserts sameness, nothing is suppressed
permanently, and a capped row is never recorded `seen` so it ranks again next run — **the re-entry
path is the next run itself**, which is why this quarantine alone needs no scheduled drain. The cap
sits INSIDE `kept < limit`, so freed slots **refill** and the slate never shrinks.

**THE GUARD THAT MADE THE CAP SAFE WAS FOUND BY MEASUREMENT, NOT BY DESIGN.** `content_hash` is NOT
NULL and never empty (0 of 96,767 open), so its presence proves nothing — **every body-less posting
hashes the empty string.** All **245** body-less open postings carry the same `e3b0c442…855` digest
and the corpus already holds **six colliding `(company, title, hash)` groups**, one of them a
`software engineer frontend` pair that could reach delivery. Uncaught, the cap would have dropped a
real distinct lead while claiming its JD matched. A body-less posting is therefore **never capped**,
reusing the `body_empty` flag the ranker's select already computes. Fail-OPEN, for the reason a
span-less `INELIGIBLE` downgrades to `ABSTAIN`.

**EACH LANE NOW REPORTS ITS COST SPLIT INTO FETCHING AND APPLYING (D-346, #217), AND THAT SPLIT IS
THE INSTRUMENT THAT CLOSES THE LANE QUESTION — NOT AN EXTRA.** D-343 left the lane stage's 6.5 min
unexplained because a stage total cannot separate upstream throttling from contention on
`apply_board`. `fetch_seconds`/`apply_seconds` per lane do, and the markdown names the fetch SHARE
because the ratio is the diagnostic. `None` = NOT MEASURED, never `0.0`. `ARTIFACT_VERSION` stays 7.
**No run has exercised it yet — read it on the next run before proposing anything else about lanes.**

**THE LANE FETCHES NOW OVERLAP, AND THAT LEVER IS NOW CLOSED (D-347, #219).** `_collect_lane` split
into `_fetch_lane` (off-thread) and `_apply_lane` (main thread only); fetches in a
`ThreadPoolExecutor`, applies in the consuming loop — `scan/coordinator.py`'s shape.
**`apply_board` remains the single writer** and a test COUNTS concurrent entries into it rather than
reading the code. **This was not the owner-gated pacing change:** `Fetcher` holds a per-host
`threading.Lock` for a request's full duration with `_pace` INSIDE it, so same-host requests still
serialize and the 1 req/s contract is untouched — concurrency across lanes adds **no** third-party
load. **Sized before building and the answer is modest:** run 129's hosts were ~85 (hiringcafe) and
~166 (linkedin) requests, so the pacing floor moves from their sum (251 s of a 390 s stage) to their
max (166 s) — **~2.2 min, ~4.9% of a 44.7 min run**. The stage is now **tail-bound on LinkedIn
alone**, the same shape D-344 found for the scan and `lowes.wd5`. **A third lane would be nearly
free; more lane parallelism buys nothing. Do not re-propose it.**

**THE MOBILE DETAIL SHEET IS FOCUS-CONTAINED, THE ONE THING #213 DISCLOSED RATHER THAN SHIPPED
(D-348, #216).** Below 64rem the pane is a full-screen sheet, i.e. a modal, and `Shift+Tab` reached a
grid row behind it — after which the single-key `a` acted on a row the reader could not see. Fixed
with the platform's `inert` on the four covered subtrees, **breakpoint-scoped**: zero inert subtrees
at or above 64rem, where the pane is a side-by-side column and containing focus would break the
Enter-then-↓ path. `SIDE_BY_SIDE` is exported and read by the pane's own focus effect so the Tailwind
`lg:` variants and the inerting cannot disagree. **The toaster is deliberately NOT inerted** — it
draws above the sheet and holds the only undo a mark-applied has. **Verified in a browser with a
non-vacuity check**: stripping only the four attributes reproduces the bug (covered row 20483 gets
focus and `a` marks it applied, 347→346). Chromium only; the pre-existing Escape-restores-focus bug
was proved pre-existing and left alone.

**THREE MERGES AND ONE PR IN FLIGHT, EVERY ONE GATED WITH A REAL EXIT CODE 0.** **MERGED:** #215 the
slate cap (D-345) · #216 the detail-sheet focus containment (D-348) · #217 the per-lane cost split
(D-346). **OPEN, gated green, auto-merge armed, CI clean at session close:** **#219** the lane fetch
overlap (D-347) — re-gated AFTER rebasing onto the post-#217 `main` with `--onto`, because #215 also
touched `runner.py` so the merge candidate differed from the tree first gated (a clean rebase can
still break semantically). **Verify #219 actually landed by `main`'s CONTENT, not by the PR page** —
pushing to a merged PR's branch lands nothing, silently. A fourth PR, **#218 (eligibility years
patterns), is a PARALLEL SESSION's**, not this one's.

**No run was taken** — every number above is measured against the existing corpus or the runs 119-129
delivery history, and says so. **Every new test was confirmed to FAIL against the wrong
implementation** before being counted; the mutation table is in METRICS 2026-08-28e.

**Everything below this line is carried from the previous session and remains true.** The provisional
pass was met by runs 119-123 and the owner is holding it; Gate P6 is 4 of 4; `DEFAULT_TOP_N` is 10 and
is a HOLDING value (D-293); the fleet is 344 watched boards; breadth is argued on precision and
capacity, never on an application count (D-312). Board cost is provider-weighted and **s/board is a
lying unit** — `workday` is ~73% of a run; size every batch by provider mix, never by board count.
**Raising the `scan_workers` ceiling above `le=8` stays RETIRED** (D-344): run 129 proved the scan
tail-bound on one board, 343 of 344 finishing in 27.0 min and `lowes.wd5` taking 5.9 more alone.
Run 129 itself: `ok`, **44.7 min** against run 128's 132.4, **2.82x = 1.58x backlog drain x 1.78x
parallelism** — only the 1.78x was code. Full numbers in `METRICS.md`.

---

## Next action

1. **NOTHING IS IN FLIGHT AND NO RUN HAS EXERCISED THIS SESSION'S WORK.** Four changes merged
   (#215, #216, #217, #219) and one landed from a parallel session (#218, eligibility). Runs are
   **ON DEMAND** (Mit's 2026-08-27 ruling); the 04:00 tick is a fallback, do not wait for it.
   **The next run is worth taking for three specific reads, in this order:**

   - **`hidden_slate_cap` in the funnel's shortlist drops.** It equals the delivery slots the cap
     freed. Expected 0 on most runs and non-zero on a location-split day — 0 is a MEASURED zero, not
     a disarmed detector, because the bucket is never identity-gated.
   - **`fetch_seconds`/`apply_seconds` per lane (D-346).** This is the number that closes the lane
     stage's 4x swing. If the cost is mostly `apply`, the swing is contention on the single writer
     and D-347 bought less than its estimate; if mostly `fetch`, it is upstream throttling and the
     estimate holds. **Do not propose anything further about lanes before reading it.**
   - **The eligibility recompute from #218's `rules_hash` bump.** Strictly stricter, so no drain is
     owed, but it re-evaluates the corpus.

   **Before ANY pull or store write, guard on PROCESS liveness, never the `runs` table:**
   ```sh
   # ALIVE if this prints a PID; empty = idle.
   ps -o pid,command -ax | awk '$2 ~ /\/python[0-9.]*$/ && /boardwatch run --project/ {print $1}'
   ```
   Anchored on **argv[0]**: a real run has `argv[0] = .../.venv/bin/python3`, every decoy shell has
   `-c`. The `awk '$2==1'` form was WRONG in the dangerous direction (D-335) — it keeps only
   launchd's direct children, so it reported IDLE for all 91 minutes of run 127, and manual
   invocation is now the common case. On macOS do NOT use `ps -o comm` (truncated path, matches
   nothing, false IDLE). `runs.finished_at` precedes process exit by ~90 s (D-024).

   **`pkill -f "make check"` is NOT worktree-scoped** and will kill a parallel session's gate in a
   sibling checkout, where it reads as an unexplained `Error 143`. Kill by PID.

   **The scratchpad directory is SHARED with subagents, not per-agent.** A PR-body file written to a
   fixed name was overwritten mid-task by a worktree agent this session. Name per-launch files
   uniquely — gate logs, sentinels and PR bodies alike.

2. **The provisional pass's clean-run counter RESTARTED, and that is the session's one live tension.**
   STATE has had it NEARLY MET with the P4 owner blind review already PASSED (2026-08-26), leaving
   only **3 clean post-fix runs**. #218 bumps `rules_hash`, so those runs are pre-fix again and the
   counter is back to zero — with runs on demand and Mit stepping back ~2026-08-31, that is 3 runs in
   about 3 days. **Raised to Mit; the trade (stricter eligibility now vs the provisional pass
   possibly not closing before unattended operation) is his, not a session's.**

3. **Re-read the queue after the next run.** The D-333 band moved 6,123 evaluations into `uncertain`
   and D-332 routes them; `.agent/2026-08-27-queue-split/` holds the read-only harness.
   `phase2_measure.py` correctly reports 0 movers — that is "already moved", not a broken query.

4. **Batch 2 of the ~765 discover candidates is still a sizing question with an answer** — the ~325
   cheap ones go in ONE batch; SmartRecruiters 107 ≈ +40 min; Workday 333 ≈ +122 min and must be
   chunked at ~100. **Probe ~10 cold Workday boards first** — no cold Workday or SmartRecruiters
   board has ever been timed, and they are the two providers that burn a per-posting detail budget on
   a first scan.

5. **One pre-existing defect remains, and it is deliberate:** `tests/unit/test_web_server.py:764`
   (`assert elapsed < 3.0`) is a genuine load-dependent flake — **do not weaken the threshold to
   green a gate; re-run the job.** macOS runs the suite unsharded, so it has MORE exposure per push.

6. **Deferred with numbers, do not re-derive:** job-apps' preferred-vs-required HEADING state machine
   is **2 of 286** and architectural (D-320). *(The residual years-detection gap was the other item
   here; #218 addressed it — read that PR rather than the old 24-leads/1.3% figure.)*

## Owner-gated — do NOT start or decide unilaterally

7. **Mit's two résumé content calls** — whether to send a document at all; the D-220 prose rewrites.
8. **P2 item 8 — the onboarding field-taxonomy gatherer. DEFERRED by Mit 2026-08-28**: no time before
   he steps back from active work (~2026-08-31, unattended after). **Not dropped — an accepted known
   gap**, and the last multi-tenancy gap of its kind. Still owner-gated and still needs its own
   brainstorm; D-054 forbids us authoring non-tech field content.
9. **`add-evidence` takes no bundle lock** (D-143) — raise before two authoring agents run against
   one bundle.
10. **Phase 1b — whether the WEB page follows the queue split (D-332). RAISED, NOT YET RULED — put it
    to Mit before touching `queue_payload`.** The folder tree holds review leads in `_review`, but
    `api.py::queue_payload` still lists them. **State the gap precisely, because "they show up
    flagged `off_target`" is WRONG:** `api.py:248` is `off_target = facts.role == "not_swe"` and the
    docstring says outright that `off_target` is `not_swe` only, **never `uncertain`** — deliberately,
    because "uncertain is not a veto". So of the ~204 review-lane leads only the `not_swe` ones carry
    any marker; a role-`uncertain` title or a confirmed non-US location renders **completely
    unmarked**. Filtering reverses that design and needs a review SECTION in the React UI plus a
    bundle rebuild (`make web`, commit both). **Do not silently exclude review leads from
    `queue_payload`** — that drops ~204 leads off the page with nowhere for the owner to see them.

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
| 14-day acceptance | not started | **HELD BY THE OWNER (2026-08-27)** — the provisional pass was MET by runs 119-123, and Mit ruled to keep fixing precision first rather than start the clock. Starting it freezes eligibility, profile and the résumé gate for 14 days. **2026-08-28e: the provisional pass's remaining item — 3 clean post-fix runs — RESTARTED FROM ZERO**, because #218 bumps `rules_hash` and those runs are therefore pre-fix again. The P4 owner blind review is still PASSED (2026-08-26) and does not repeat. With runs on demand and Mit stepping back ~2026-08-31, that is 3 runs in ~3 days; **the trade (stricter eligibility now vs the pass possibly not closing before unattended operation) was raised to Mit and is his** |
| P7 Breadth | **lane 1 (hiring.cafe) and Part 4b (LinkedIn) are BUILT AND ARMED and ran in run 122** (hiringcafe 70 attempted/56 resolved; linkedin 71/51) — the previous "not armed" text was stale. **Part 4a GitHub-lists discovery BUILT + LANDED (#149/D-296) and NOW PARTLY ARMED**: 97 boards imported 2026-08-27, ~765 candidates still capped. Remaining lanes not started | unlock MET (D-271/272) |
| *Gate A / Gate B* | *complete, merged* | ***MET*** — *has moved no program gate* |

### Gate P6, clause by clause

| Clause | Standing |
|---|---|
| Duplicate leakage over 7 days ≤ 5% | **MET 2026-08-27 — the span now exists (ledger 2026-08-19 → 08-27 = 8 days): 601 surfaced / 600 identified / 600 distinct / 0 redundant / 0.00%.** The blindness below is unchanged and is now MEASURED rather than argued: #185 adds a never-folded `candidate_redundant 7 / candidate_identified 610 = 1.15%` upper bound over a **0.50%** truth. Original standing: **CANNOT FAIL FOR ONE CLASS — see D-294 before quoting it.** `identity_queries.py:296` hardcodes `kind == "exact_quad"`, so a job whose only identity is `company_title_location` lands in `unidentified` and can never be counted redundant. Ruling 3 stopped those duplicates reaching leads but did NOT extend this metric, so it reads 0.00% for a structural reason. Measured honestly over the 146 delivered résumés (grouping by company+title+location) the real figure is **3 redundant = 2.05%** — under the bar, not zero. Extending the query reverses D-132/D-283 mid-gate and is the owner's. Original standing: **measurable, awaiting span (D-283).** `boardwatch identities leakage [--days N] [--json]` ships. **Live: 100 surfaced jobs / 100 distinct `exact_quad` groups / 0 redundant = 0.00%.** Only `exact_quad` counts (Mit's ruling, ratified); counted over jobs that REACHED LEADS, not the corpus; body-less jobs sit in their own `unidentified` bucket, never folded. **Not yet "over 7 days"** — the ledger starts 2026-08-19 so ~3.2 days exist, and the 7-day `seen` TTL cannot be observed faster than itself. First true window **~2026-08-26**, inside Parts 2–4, so off the critical path |
| **0** dead postings reaching leads | **MET (D-281).** Two runs on a scratch store copy: `checked 40, dead 0, unknown 2, alive 38, gone_after_redirect 0`, identical in both, agreeing across three read paths (funnel JSON, funnel markdown, stdout). Detector demonstrably ARMED — `checked > 0`, so not the disarmed 0/0 signature. The `runs` table has no liveness columns, so no DB-row path exists; those three are all there are |
| Injected hash-collision test | **MET** (D-100) |
| Audit of 20 sampled suppressions | **MET** (D-101) |

---

## Live blockers and carried gaps

| Item | Detail | Owner |
|---|---|---|
| **boardwatch cannot see ~90% of job-apps' eligible yield** | 41 of 530 records (7.7%) at a watched company — **a parallel session re-measured reach at ~10.1% on the 344-board fleet on 2026-08-28; NOT re-derived here, so treat 7.7% as the reproducible figure and 10.1% as owed a check**; 352 companies in the set, 24 watched. Amazon/TikTok/Apple/ByteDance use none of the 6 ATS, so a slug cannot reach them. Closing it means a new discovery lane — GitHub new-grad lists are 19.1% of yield for ~5 public-repo GETs and are NOT the ToS trap the v2 decision was written about. **Reopens D-008** | **Mit** (reverses a shipped decision) |
| **Citi sits at 13.1% coverage, permanently** | Workday's `total` censors at 2,000; the facet sum (uncapped, control-verified) says 4,589. Our pager wraps at ~2,000 too, so post-drain Citi holds ~2,214 of 4,589 and nothing reports it | **Mit** (input-side) |
| **`unchanged` staleness is now BOUNDED (D-298, #153)** | The `unchanged` verdict comes from the upstream HTTP validator (ETag/Last-Modified → 304), not a boardwatch payload hash. `validator_max_age_hours` (default 24) drops a validator older than the TTL, forcing an unconditional refetch, so a permanently-stale upstream can no longer freeze a board forever — the silent-staleness window is capped at the TTL, and a regression test now exercises the aged-validator refetch. Still open: within the TTL an `unchanged` is trusted with no independent check. The separate "59 of 135 boards listed nothing" figure was a **`postings_listed`-on-304 artifact — CORRECTED to 17 real dead-weight (D-300)**, now cleaned; the 118 `ok` boards hold 39,253 open postings | open (mitigated) |
| **No external missed-window alarm** | nothing outside a run can detect a missed 08:00; the funnel heartbeat is only written from inside `runner.py` | P3 |
| **`resume.yaml` is an IMPORT SOURCE, never hand-fixed** | D-155. Mit pins `resume_max_pages=1`; never advise 2 | Mit |
| **`boardwatch top` advances the queue by default** | records `seen` unless `--no-record`; relevant to Gate P6's clean window | P6 |
| **`add-evidence` takes no bundle lock** | two concurrent captures race on up to 13 files (D-143) | owner-gated |
| **A live store is readable ONLY via Python `sqlite3` `?mode=ro`** | the `sqlite3` CLI with `?mode=ro` fails `CANTOPEN(14)` on a cleanly-checkpointed store (no `-shm`; not the sandbox), and `?immutable=1` skips the WAL so it is STALE against a live writer. Mid-run progress: `SELECT COUNT(*) FROM eligibility_evaluations WHERE run_id=N` (D-268) | tooling |
| **Disk pressure now costs GATE TIME, silently** | The same suite ran **4m51s** at ~7.4 GiB free and **34m40s** at 5.7 GiB / 98% — no error, nothing logged, and a bounded waiter timed out, which reads as a hang. Cause was pytest's own temp trees at **1.1 GB** across 5 runs in `/private/var/folders/*/*/T/pytest-of-mitsheth/`; clearing the stale ones (keep the newest, it is live) plus branch cleanup took the volume to **9.1 GiB / 96%**. **RE-MEASURED AND CLEARED 2026-08-27: the same trees had grown to 4.9 GB across 15 runs** — 4.5x the figure that first caused this — and removing all but the newest took them to **5.4 MB** and the volume from **15 GiB to 20 GiB free**. Do this after any session that runs several full gates; it is the cheapest gate-time win there is. **The "two stale store backups, 1.67 GB" clause is STALE and is retired here** — no `.db` backup exists beside the live 3.1 GB store, only small yaml/profile ones. **There is therefore still no rollback snapshot** (take one before any destructive operation) | **tooling** |
| **CI is sharded and gates on ONE context (D-334)** | Branch protection requires `ci` and nothing else — not the six `test (3.x, ubuntu-latest)` contexts, which no longer exist. `ci` carries `always()` and derives what should have run from `github.event_name`, because **GitHub counts a SKIPPED required check as SUCCESS**. Two standing prohibitions are commented in `ci.yml` and are load-bearing: **no `if:` on `ci` beyond `always()`** (a condition there erases every gate at once) and **no `continue-on-error` on any job in its `needs`** (it makes a failed job report `success`). Shard count lives in ONE place, the `plan` job — a workflow-level `env` CANNOT be read from `jobs.<id>.strategy`. **Read CI job conclusions from `gh api .../actions/runs/<id>/jobs`, never `gh pr checks`**, which has misreported on this repo | tooling |
| **`make check` must be launched DETACHED** | the Bash tool clamps `timeout` to ~10 min; a longer gate reads as `make: *** [test] Error 143` — that is SIGTERM, not a build break. **`setsid` does not exist on macOS**: use `nohup sh -c '<export PATH>; make check > LOG 2>&1; echo $? > DONE' & disown`, set PATH INSIDE the subshell, and gate on the sentinel file, never the launcher's exit code. The clamp is WALL-CLOCK, so CPU contention converts a comfortable run into a kill — a suite that ran 5m17s alone was SIGTERMed at 62% while one subagent ran its own pytest. Never pipe the gate through `head`/`tail` | tooling |
