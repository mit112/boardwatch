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

**RUN 127 LANDED THE WHOLE ELIGIBILITY STACK AND D-333 IS CONFIRMED BY MEASUREMENT.** Run 127 is the
first tick on engine `1+118c640ea50c` (derive it, never quote it — D-306): `ok`, **91m03s** against a
~116 min projection, 346 boards, 13,518 postings seen, 1,418 new, 340 closed. **Every required years
row with a threshold ≤ 3 flipped disposition `unmet` → `unknown`** — 10,757 → **0** unmet, 10,880
unknown — and **6,123 evaluations moved `ineligible` → `uncertain`** against D-333's predicted 5,980
(within 2.4%; the population itself grew by 126 in the same span). Corpus-wide `ineligible` fell
36,141 → 30,068. **Zero of those 9,324 evaluations became `eligible`**, which is the first EMPIRICAL
confirmation of D-333's central claim — until now it was only a code argument about `blocking(UNKNOWN)`
being tested before the `eligible` fallthrough. The 91-vs-116-minute result also means the linear
scaling model **over-predicts by ~22%**; do not size off it without that correction.

**CI IS SHARDED AND THE PR LOOP IS 3.3x FASTER (D-334, #198).** A pull request was **30-42 min**;
per-step timings showed the whole of it was one step (`pytest -n auto` at 1764/2480/1903s, everything
else totalling ~20s) on a **4 vCPU** runner. There was no hot spot to remove — the slowest single test
is **1.5%** of total CPU and the top 25 are **9%** — so the suite is split 4 ways per Python by SHA-256
of the node id. **Measured: 10.6 min.** Lint, all three `type` jobs, gitleaks, perf, generalization and
web bundle now report in **under a minute** instead of behind a 30-minute job. **Branch protection now
requires ONE context, `ci`** — not the six `test (3.x, ubuntu-latest)` ones. Shard count is **4 and that
is measured**: at 8, seven jobs queued behind the ~20-job concurrency ceiling, and since wall clock is
bounded by concurrency rather than by slicing, 8 paid double the per-job setup for the same ten minutes.

**THE LIVENESS PROBE THIS FILE SHIPPED WAS WRONG, AND IT FAILED TOWARD "SAFE TO WRITE" (D-335).** The
`awk '$2==1'` form below reported IDLE for the whole of run 127. Use the argv[0]-anchored form; the
reasoning is in D-335 and the block under **Next action** now carries the correct one.

**ANOTHER SESSION RAISED `detail_fetch_budget` 50 → 400 IN THE LIVE CONFIG (2026-08-28, not this
session).** Mit's local config only — deliberately NOT the code default, which would change behaviour
for every user of the published package. Backup: `config.toml.bak-predetailbudget-20260828`. **Expect
the next run to be ~27 min longer, ONCE**, as it absorbs the deferred-detail backlog; that is the
change working, not a regression. The measurements behind it are that session's and land under
**D-336 onward** — this file deliberately does not restate them.

**THE LIVE STORE WAS WRITTEN BY ANOTHER SESSION AFTER RUN 127 (2026-08-28).** Prior application
history imported (`applications` 0 → 22, all `attempt_no = 1`), and `identities backfill` run for the
p6.3 bump. **The backfill wrote p6.3 BESIDE p6.2 rather than replacing it** — `write_identities` only
deletes rows at the SAME version — so there is no window where suppression is off and old and new code
both work. Consequence to price: `posting_identities` roughly doubled and about half is now a dead
generation with **no reaper** (one is in flight on `feat/idhygiene`). Numbers and reasoning are that
session's, under **D-336 onward**; this file deliberately does not restate them.

**THE CADENCE CHANGE CUT AGGREGATOR INTAKE ~8x, AND THE MECHANISM IS RUN COUNT, NOT A BUDGET.** Moving
from ~8x/day to 1x/day on 2026-08-27 was decided on gate-speed grounds (local runs contend with the
local gate: the same suite measures 4m51s idle and 34m40s under load) and the intake consequence was
never costed. **Do not attribute it to `lane_posting_budget`** — that was checked and is NOT binding:
`body_fetched` was 55 on run 126 and 56 on run 127 against a budget of 60 (LinkedIn 49 and 53). What
caps a lane is that neither paginates its search. **The CI work does NOT weaken the original
justification** — `make check` is still local and still contends.

**Everything below this line is carried from the previous session and remains true.** The provisional
pass was met by runs 119-123 and the owner is holding it; Gate P6 is 4 of 4; `DEFAULT_TOP_N` is 10 and
is a HOLDING value (D-293); the fleet is 346 watched boards; breadth is argued on precision and
capacity, never on an application count (D-312). Board cost is provider-weighted and **s/board is a
lying unit** — `workday` is 73.4% of a run at 22.03 s of marginal wall clock per board at
`scan_workers = 4`; size every batch by provider mix, never by board count. Full tables in `METRICS.md`.

---

## Next action

1. **NOTHING OF THIS SESSION'S IS IN FLIGHT.** Run 127 finished 05:24:27Z (process exited 05:25:54Z),
   and the eligibility/CI work is merged and green on the new `ci` gate. **`main` has moved since, from
   another session** — a prior-application importer and a location canonicalization that bumps
   `IDENTITY_ALGORITHM_VERSION` **p6.2 → p6.3**; that session is writing those up under **D-336 onward**.
   Check `git log`, do not trust a sha here (D-017).

   **Before ANY pull or store write, guard on PROCESS liveness, never the `runs` table:**
   ```sh
   # ALIVE if this prints a PID; empty = idle.
   ps -o pid,command -ax | awk '$2 ~ /\/python[0-9.]*$/ && /boardwatch run --project/ {print $1}'
   ```
   **The form this file shipped before was WRONG in the dangerous direction (D-335).**
   `awk '$2==1'` keeps only launchd's DIRECT children — true for a scheduled tick, false for a manual
   run, which goes through a `nohup` wrapper so only the WRAPPER reparents to PID 1. It reported IDLE
   for the entire 91 minutes of run 127. Since Mit's 2026-08-27 ruling moved this program to manual
   invocation, that is now the common case. The form above anchors on **argv[0]**: a real run has
   `argv[0] = .../.venv/bin/python3`, while every decoy shell has `-c`. Verified against three live
   decoys — two `sh -c` and a Claude session's own zsh wrapper — where the older `[b]`-only form
   returned FOUR pids for one real run. `--project` additionally excludes the long-lived
   `boardwatch web --port 0` server. **On macOS do NOT reach for `ps -o comm`**: it returns the
   truncated executable PATH, not `python3`, so a comm-based filter matches nothing and reports a
   false IDLE.
   `runs.finished_at` is written BEFORE the process exits — funnel and morning artifacts come from a
   `finally` after the row closes (D-024). Run 127: `finished_at` 05:24:27, process gone 05:25:54 —
   **87 seconds**, the same gap as run 125's 92.

2. **Re-read the queue after the next run.** The D-333 band has moved 6,123 evaluations into
   `uncertain`, and D-332 routes them; `.agent/2026-08-27-queue-split/` holds the read-only harness
   (`lane_measure.py` for the delivered split). **`phase2_measure.py` now correctly reports 0 movers**
   — that is "already moved", not a broken query. The positive evidence is the disposition flip in
   **Current standing**; re-derive it that way, not from the absence.

3. **Batch 2 of the ~765 discover candidates is still a sizing question with an answer** — the ~325
   cheap ones go in ONE batch; SmartRecruiters 107 ≈ +40 min; Workday 333 ≈ +122 min and must be
   chunked at ~100. **Probe ~10 cold Workday boards first** — no cold Workday or SmartRecruiters board
   has ever been timed, and they are the two providers that burn a per-posting detail budget on a first
   scan. **Hold this off the next run**, which already carries the ~27 min detail-budget catch-up.

4. **One pre-existing defect remains, and it is deliberate:** `tests/unit/test_web_server.py:764`
   (`assert elapsed < 3.0`) is a genuine load-dependent flake — **do not weaken the threshold to green
   a gate; re-run the job.** It fired once this session, on `test (3.11, macos-latest)` at 3.42s, and
   passed on re-run. Note it now has MORE exposure per push, not less: macOS runs the suite unsharded,
   so the test is no longer split away onto one shard of four.

5. **Deferred with numbers, do not re-derive:** the residual years-detection gap is **24 leads, ~8 real
   (1.3%)** and widening the pattern rejects `18 years of age`; job-apps' preferred-vs-required HEADING
   state machine is **2 of 286** and architectural (D-320).

*(`.agent/` is gitignored working material — re-derive if pruned.)*

## Owner-gated — do NOT start or decide unilaterally

5. **Mit's two résumé content calls** — whether to send a document at all; the D-220 prose rewrites.
6. **P2 item 8 — the onboarding field-taxonomy gatherer.** Needs its own brainstorm; D-054 forbids us
   authoring non-tech field content.
7. **`add-evidence` takes no bundle lock** (D-143) — raise before two authoring agents run against one bundle.
8. **Phase 1b — whether the WEB page follows the queue split (D-332). RAISED, NOT YET RULED — put it to
   Mit before touching `queue_payload`; do not act on it unilaterally.** The folder tree now
   holds review leads in `_review`, but `api.py::queue_payload` still lists them. **State the gap
   precisely, because "they show up flagged `off_target`" is WRONG:** `api.py:248` is
   `off_target = facts.role == "not_swe"`, and the docstring says outright that `off_target` is
   `not_swe` only, **never `uncertain`** — deliberately, because "uncertain is not a veto" and badging it
   would assert a decision the gate declined to make. So of the ~204 review-lane leads, only the
   `not_swe` ones carry any marker; a role-`uncertain` title or a confirmed non-US location renders
   **completely unmarked**. Filtering reverses that design and needs a review SECTION in the React UI
   plus a bundle rebuild (`make web`, commit both). **Do not silently exclude review leads from
   `queue_payload`** — that drops ~204 leads off the page with nowhere for the owner to see them.

## Open questions — Mit's, not to be resolved by fiat

1. **The projection spec's six open questions** (§12) — soonest: whether `tailor run` should validate the
   projection manifest, and whether persona's `entries` list survives stage 2.
2. **The Snap `Level 5`/`Level 3` leak stays open by design** — with no bindings file every level token
   abstains, so a level-named title is shortlisted carrying its reason. boardwatch ships no verifiable
   claim about any company's ladder.
3. **Whether `censored` boards publish a coverage ratio, and the 17 silent boards.** The
   `detail_fetch_budget` half moved on 2026-08-28: another session raised it **50 → 400 in Mit's local
   config only** (never the code default — that is a multi-tenancy call). Its measurements of both fetch
   ceilings land under **D-336 onward**, by that session, with its own evidence. **The "four censored
   boards are short 18,927" figure elsewhere in this file is STALE against the 346-board fleet** and is
   corrected there, not here.

*(Resolved and no longer open: whether `runner.py` should keep swallowing a funnel-write failure — D-288
records it and the run still does not fail. Clearance IS a blocker (D-257). Seniority band = `entry`
(D-258). The launchd trigger fires (D-254); its cadence is now once daily at 04:00 and is a fallback, not the thing to plan around.)*

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
| 14-day acceptance | not started | **HELD BY THE OWNER (2026-08-27)** — the provisional pass was MET by runs 119-123, and Mit ruled to keep fixing precision first rather than start the clock. Starting it freezes eligibility, profile and the résumé gate for 14 days |
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
| **A metric that could not fail (D-267)** | `grep -ic buc funnel-N.json` was read as a Buc count; it counts the word "bucket" and is 4 on runs 61/63/65/66 regardless. The funnel enumerates **no ranked pool** and a `leads` row carries **no location** — so the hard location gate, the one gate whose failure is a visa-ineligible lead, leaves no trace in its own artifact. Closing it needs `locations` on `Lead` + an `artifact_version` bump. **Re-raised 2026-08-21c; still Mit's.** D-268 corrects this row's replacement metric too: "0 of 62" had the 0 robust under every bounded rule (27/27/69/70 matched, 0 surviving) but the **62 unreproducible** — match rule and corpus size were never recorded beside it, and a bare substring gives 103 matched / **39 surviving**. A ratio now records its match rule AND corpus size. **CLOSED 2026-08-27 (D-323): artifact v7** — `leads[].locations` (`null`, never `[]`, when the posting names no place) + `leads[].location_class` from the production `classify_location`, and `manifest.location_filter_mode` so the verdicts are readable. The Markdown names its match rule and corpus size, per this row's own lesson | **closed** |
| **boardwatch cannot see 92% of job-apps' eligible yield** | 41 of 530 records (7.7%) at a watched company; 352 companies in the set, 24 watched. Amazon/TikTok/Apple/ByteDance use none of the 6 ATS, so a slug cannot reach them. Closing it means a new discovery lane — GitHub new-grad lists are 19.1% of yield for ~5 public-repo GETs and are NOT the ToS trap the v2 decision was written about. **Reopens D-008** | **Mit** (reverses a shipped decision) |
| **Citi sits at 13.1% coverage, permanently** | Workday's `total` censors at 2,000; the facet sum (uncapped, control-verified) says 4,589. Our pager wraps at ~2,000 too, so post-drain Citi holds ~2,214 of 4,589 and nothing reports it | **Mit** (input-side) |
| ~~Five boards GREEN-and-zero + 12 dead~~ **RESOLVED (D-300)** | Diagnosed 2026-08-24: root cause is ATS migration, not typos. The 5 empty — HubSpot→`greenhouse:hubspotjobs`, Plaid→`ashby:plaid`, Vercel→`greenhouse:vercel` recovered; Qualcomm/Snyk unwatched. The 12 error/dead were all Workday: **5 GATED (401/403, unrecoverable)**, 7 wrong-site (422, recovered walmart wd504 + veeva→lever + purestorage→greenhouse, rest unwatched). Watched 135→124, **0 dead/error/empty**. `doctor` now suggests migrations (D-301, #161). Backoff/quarantine still absent but the fleet is clean | done |
| **`unchanged` staleness is now BOUNDED (D-298, #153)** | The `unchanged` verdict comes from the upstream HTTP validator (ETag/Last-Modified → 304), not a boardwatch payload hash. `validator_max_age_hours` (default 24) drops a validator older than the TTL, forcing an unconditional refetch, so a permanently-stale upstream can no longer freeze a board forever — the silent-staleness window is capped at the TTL, and a regression test now exercises the aged-validator refetch. Still open: within the TTL an `unchanged` is trusted with no independent check. The separate "59 of 135 boards listed nothing" figure was a **`postings_listed`-on-304 artifact — CORRECTED to 17 real dead-weight (D-300)**, now cleaned; the 118 `ok` boards hold 39,253 open postings | open (mitigated) |
| ~~`top`'s drain flags break in ~2 days~~ | **CLOSED by #145** (D-289): all six corpus-sized `IN` lists chunk through `store/param_chunks.id_chunks`, three merge shapes each mutation-tested, including `reopen_jobs`' summed rowcount | done |
| **No external missed-window alarm** | nothing outside a run can detect a missed 08:00; the funnel heartbeat is only written from inside `runner.py` | P3 |
| **`resume.yaml` is an IMPORT SOURCE, never hand-fixed** | D-155. Mit pins `resume_max_pages=1`; never advise 2 | Mit |
| **`boardwatch top` advances the queue by default** | records `seen` unless `--no-record`; relevant to Gate P6's clean window | P6 |
| **`add-evidence` takes no bundle lock** | two concurrent captures race on up to 13 files (D-143) | owner-gated |
| **A live store is readable ONLY via Python `sqlite3` `?mode=ro`** | the `sqlite3` CLI with `?mode=ro` fails `CANTOPEN(14)` on a cleanly-checkpointed store (no `-shm`; not the sandbox), and `?immutable=1` skips the WAL so it is STALE against a live writer. Mid-run progress: `SELECT COUNT(*) FROM eligibility_evaluations WHERE run_id=N` (D-268) | tooling |
| **Disk pressure now costs GATE TIME, silently** | The same suite ran **4m51s** at ~7.4 GiB free and **34m40s** at 5.7 GiB / 98% — no error, nothing logged, and a bounded waiter timed out, which reads as a hang. Cause was pytest's own temp trees at **1.1 GB** across 5 runs in `/private/var/folders/*/*/T/pytest-of-mitsheth/`; clearing the stale ones (keep the newest, it is live) plus branch cleanup took the volume to **9.1 GiB / 96%**. **RE-MEASURED AND CLEARED 2026-08-27: the same trees had grown to 4.9 GB across 15 runs** — 4.5x the figure that first caused this — and removing all but the newest took them to **5.4 MB** and the volume from **15 GiB to 20 GiB free**. Do this after any session that runs several full gates; it is the cheapest gate-time win there is. **The "two stale store backups, 1.67 GB" clause is STALE and is retired here** — no `.db` backup exists beside the live 3.1 GB store, only small yaml/profile ones. **There is therefore still no rollback snapshot** (take one before any destructive operation) | **tooling** |
| **CI is sharded and gates on ONE context (D-334)** | Branch protection requires `ci` and nothing else — not the six `test (3.x, ubuntu-latest)` contexts, which no longer exist. `ci` carries `always()` and derives what should have run from `github.event_name`, because **GitHub counts a SKIPPED required check as SUCCESS**. Two standing prohibitions are commented in `ci.yml` and are load-bearing: **no `if:` on `ci` beyond `always()`** (a condition there erases every gate at once) and **no `continue-on-error` on any job in its `needs`** (it makes a failed job report `success`). Shard count lives in ONE place, the `plan` job — a workflow-level `env` CANNOT be read from `jobs.<id>.strategy`. **Read CI job conclusions from `gh api .../actions/runs/<id>/jobs`, never `gh pr checks`**, which has misreported on this repo | tooling |
| **`make check` must be launched DETACHED** | the Bash tool clamps `timeout` to ~10 min; a longer gate reads as `make: *** [test] Error 143` — that is SIGTERM, not a build break. **`setsid` does not exist on macOS**: use `nohup sh -c '<export PATH>; make check > LOG 2>&1; echo $? > DONE' & disown`, set PATH INSIDE the subshell, and gate on the sentinel file, never the launcher's exit code. The clamp is WALL-CLOCK, so CPU contention converts a comfortable run into a kill — a suite that ran 5m17s alone was SIGTERMed at 62% while one subagent ran its own pytest. Never pipe the gate through `head`/`tail` | tooling |
