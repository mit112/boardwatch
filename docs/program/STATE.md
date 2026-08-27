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

**THE PROVISIONAL PASS WAS MET, AND THE OWNER HAS CHOSEN TO HOLD IT.** Runs **119-123** are five
consecutive clean scheduled ticks on frozen engine `1+af3a746837b1` — D-280 requires three. Verified per
run from the funnels, not from a self-report: 10 leads each, 10/10 PDFs, `reconciles=True`, 0 fatals,
0 errors, liveness `checked 10 / dead 0`, every cross-check agreeing, P5b 61,875-68,780 considered.
**40 leads across 119-122 with ZERO overlap in any of the six pairings**, so B1 net-new is confirmed
rather than assumed. B1 sits cap-bound at exactly 10 (`DEFAULT_TOP_N`) — the bar, not headroom.
**Mit's ruling 2026-08-27: do NOT start the 14-day acceptance; keep fixing precision first.** There is
therefore no clock pressure — batch eligibility changes, then freeze once.

**GATE P6 IS 4 OF 4.** The ledger span reached 8 days (2026-08-19 → 08-27), so the 7-day window finally
exists: `identities leakage --days 7` reads **601 surfaced / 600 identified / 600 distinct / 0 redundant
/ 0.00%**. The `exact_quad`-only blindness (D-294) still stands, and is now *measured* rather than merely
noted — see the `candidate_*` bound in #185 below.

**A THIRD ELIGIBILITY FAMILY COULD NEVER FIRE, AND IT DELIVERED NINE WRONG RÉSUMÉS (D-322, #182,
MERGED).** `us_citizen_required` and `us_citizen_or_lpr_required` abstained on **100% of their rows —
591 per run**. The funnel's own abstain block already reported both `fully_abstaining`; the report was
correct and unread. A declared `ead_or_similar` states the applicant is neither citizen nor LPR, which
is UNMET on exactly the ground `permanent_resident` already resolves UNMET (corpus m0005, pinned since
P2). Measured before the change: **402 `uncertain` → `ineligible`, 162 already ineligible, ZERO
`eligible` affected**; 393 of the 402 still open and never handled. **Nine résumés had already been
built** against citizenship the profile cannot meet — Thomson Reuters ×2, CrowdStrike ×2 (incl.
FedCloud), Agile Defense (CBP), Accenture ×3, CACI, whose JD reads verbatim *"This position requires
U.S. citizenship"*. They drain themselves via D-321's `_ineligible` filter. `engine_version`
`1+af3a746837b1` → moves on merge of the open stack.

**FIVE PRs ARE OPEN, ALL PUSHED, ALL WITH DECISION RECORDS, INDEX GATE GREEN ON EACH.** #183 (D-323,
lead locations + artifact v7) · #184 (D-326, clearance-obtainability + field-of-study facts) · #185
(near-duplicate measurement, **OWES D-327**) · #186 (D-324, `unverifiable` status) · #187 (D-325, measured-death
close). **#187's `make check` was NOT re-run after a rate-limit kill — CI is its verdict.** Nothing in
this stack is armed; merging it moves `engine_version` once, and a **ledger drain is owed** after.

**THE PRIMARY TREE IS DELIBERATELY UNPULLED AT `91f90d8`, ON THE OLD ENGINE.** That isolates run 124's
cost: 97 boards were imported cold (no ETag on a first scan) and an engine change would confound the
measurement. **Read run 124's duration before pulling anything.** Baselines: 234 boards = **14.0
s/board, ~55 min**; the first run after an engine move = **27.1 s/board, 106 min** (run 119). Cadence is
180 min.

**THE WATCHED FLEET IS 346, UP FROM 234 (owner-authorised 2026-08-27).** 97 boards imported via
`companies discover` → review → `import --verify`; the probe skipped `lever:cirrus` and
`ashby:Commure-Athelas` as dead, and `lever:cirrus` had been **hand-approved in error** — the adapter
lists `jobs.eu.lever.co` in `board_hosts` but the API call is `api.lever.co/v0/postings/{slug}`
regardless. **Always `--verify`.** `ashby:KAYAK` was removed pre-import for a CASE collision with
watched `ashby:kayak`. Separately, **15 lane companies on a registry ATS were promoted to `watched=1`**
(11 ashby, 3 greenhouse, 1 lever), so zero enumerable lane companies remain unwatched and the
cannot-close class went 745 → 722. **~765 discover candidates remain capped**; Workday 333 +
SmartRecruiters 107 ramp last (per-posting detail budget on first scan).

**LANE-ACQUIRED POSTINGS CAN NEVER CLOSE, AND ABSENCE IS NOW PROVEN MEANINGLESS (D-314, extended
2026-08-27).** The mechanism is unchanged: `_process_missing` (`scan/apply.py`) is the only writer of
`status="closed"`, runs on **`complete`** snapshots only; `lanes/base.py::lane_snapshot` is always
`partial`; lane companies are upserted `watched=False`. **The new evidence is a natural experiment in
the store:** when the D-309 role facet changed what the lanes search for, **0 of 290** pre-facet lane
postings were ever re-seen — and probing 45 of them with the shipped prober found **40 alive (HTTP 200),
0 dead**. They did not close; we stopped asking. At 3h cadence a **live** lane posting is absent from
its own lane's results in **~19% of runs**, so a `CLOSE_AFTER_MISSES=2` analogue would have destroyed
**25 live postings in 33 hours**. **Age-based and missed-run closing are therefore REJECTED by
measurement, not merely unproven — do not propose either again.** The class was 282 at D-314 and is
**471**, growing **~182/day**. The honest predicate is `companies.watched = 0` ("nothing enumerates this
board") = **722 rows**, which includes ~274 unwatched `source='user'` companies with the identical
defect — `source='lane'` is wrong in both directions. **Owner ruled 2026-08-27: build the `unverifiable`
label (#186/D-324), promote registry-ATS lane companies (DONE — 15 of them), and add the 6.7%-power URL
probe (#187/D-325). He did NOT choose to cap how long a lane row stays DELIVERABLE — the only option
that shrinks the pool. Worth re-raising.**

**HOW TO REPORT YIELD — the owner's standing rule (D-312).** Every yield, coverage or job-apps comparison
quotes **the end of the line: affirmatively `eligible` jobs** — currently **~60/day** (eligible + software +
in-band + US + non-duplicate + unhandled). **Never** quote a broader upstream population as the headline:
"new postings/day" and "software-titled/day" are different quantities, and doing so overstated yield ~8× in
this session before Mit caught it (the hard US filter alone removes 57% of the corpus). **`uncertain` is
never folded into `eligible`** — the keystone invariant, not a preference; the ~82/day abstains get their own
line. Measure with `stats` / `top --no-record --json` / the run funnel, never ad-hoc SQL over `postings`.

> **A MANUAL RUN RACING A TICK EXITS 2 AND RESETS GATE P3**, and at 8 fires a day that is 8× likelier than
> it was. Check `launchctl print gui/$(id -u)/com.boardwatch.run | grep state` before starting one by hand.
> Two *scheduled* fires cannot collide — launchd never runs two instances of one label.

**The headline number: 0.** Zero job applications have ever been sent (`applications` has 0 rows) — the
machine produces leads, it never applies (out of scope). Against that: **4 published releases, latest
`0.5.0`**, ~53k lines of source, **7,584+ tests**, 71 leaf CLI commands, 6 ATS providers, a **~1.4 GB**
store holding **51,004 postings / 43,286 open** (2026-08-26).

> **PHANTOM run 118 (benign, mine, and STUCK `running`).** The production-path verification for D-319
> was a `boardwatch top --no-record` against the LIVE store, which calls `ensure_run`. It wrote **4,400
> eligibility evaluations** under `1+5bf77461f044` — the rows the paired old-vs-new comparison in METRICS
> is measured from, so they are real and correctly stamped — and was then stopped part-way, leaving
> `runs.id=118` at **`status='running'` forever** with `boards_attempted=0`, 0 artifacts and 0
> `job_dispositions`. Gate P3 is unaffected: its filter is `boards_attempted > 0`, which excludes this
> row exactly as it excludes run 91. Left in place for the same reason run 91 was — the production store
> has no rollback snapshot and deleting a row is riskier than an inert one. **Consequence: the first
> scheduled tick on the new engine is run 119, not 118.** Two lessons, both already known and both
> ignored here: `top` writes a run even with `--no-record` (that flag governs the `seen` cursor, not
> `ensure_run`), and a full-corpus read against the live store is a WRITE.

> **PHANTOM run 91 (benign, mine).** A `boardwatch tailor run 13549` verification without a scratch
> `BOARDWATCH_DATA_DIR` called `ensure_run` and wrote to the LIVE store: run 91 (empty, `boards_attempted=0`,
> 36ms) + one `artifacts` row (id 498, uri→`/tmp`). NO `job_dispositions`, posting 13549 NOT marked handled,
> dedup/ledger UNAFFECTED, streak intact (the `boards_attempted>0` filter excludes it). Left in place (prod
> store has no rollback snapshot; deleting is riskier than an empty row). Consequence: next scheduled tick is
> **run 92**. Lesson: to verify projection against real postings with the LIVE edited config you must hit the
> live store — use read-only `resume project`, never `tailor run` (it writes a run+artifact).

**THE STORE IS AT `p_lane_companies`, which is `main`'s head**, so `ensure_schema` on the next tick is a
no-op. **The rule this bought: after any PR that adds a migration, apply it to the live store deliberately
and verify, rather than letting the next unattended tick discover it** (D-279/D-286). **There is no
rollback snapshot** — all three stale backups were verified redundant and deleted (2026-08-23b, ~2.9 GB
reclaimed). Take one before any destructive operation rather than assuming one exists.

**THE LAUNCHD JOB RUNS AN EDITABLE VENV RESOLVING TO `src/` IN THE PRIMARY WORKING TREE**, so a scheduled
tick executes whatever branch is CHECKED OUT there. **Leave that tree on `main`.** Use a worktree for
parallel work, and never `git stash` — it is shared across worktrees.

**Every agent invocation needs BOTH `BOARDWATCH_DATA_DIR` and `BOARDWATCH_CONFIG_DIR` on a scratch dir**
(D-281). `DATA_DIR` alone still READS the live `resume.yaml` / `career-profile/` / template and still
WRITES into the live `~/boardwatch-applications/`. The live store is the DEFAULT, so a forgotten flag
reaches production, and a migration breaks the NEXT scheduled run, not the one that erred. Two
consequences: a scratch run's `funnel-N` collides with the next real run's, and the artifact directory is
**UTC-dated** — match on the run NUMBER, never the date.

**Standing tripwire (D-268):** all six known precision leaks are blocked by the current gates — five
non-SWE `Lead` titles in the role gate, GE HealthCare posting 31365 (`Buc` → `non_us`) in the hard filter.
Any of the six appearing in a funnel's `leads` is a real regression to investigate before anything else.

**`DEFAULT_TOP_N` is 10 — a HOLDING value until the precision work lands (D-293), and the uncapped set was
MEASURED, not estimated (D-292): 3,771 postings arriving ~220-430/day, of which 67.6% are `role=uncertain`,
so honest confirmed-software arrival is ~70/day. Quote neither figure without naming its population —
they differ by 4x.** Do **not** raise the cap before the precision work is merged, and do **not** set it to
0: that fails B1 (>= 10 net-new leads/day) outright while Gate P3's counter keeps running. The cap sets
**burn rate, not supply** — long-run output equals the arrival rate whatever it is. Lifting it is Mit's
call and is now informed on both sides (D-293, D-294).

---

## Next action

1. **READ RUN 124's DURATION BEFORE PULLING ANYTHING — the isolation expires.**
   ```sh
   .venv/bin/python -c "
   import sqlite3, os
   db = os.path.expanduser('~/Library/Application Support/boardwatch/boardwatch.db')
   con = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
   for r in con.execute('''SELECT id, boards_attempted,
     CAST((julianday(finished_at)-julianday(started_at))*86400 AS INT) secs
     FROM runs WHERE id>=122 ORDER BY id'''): print(r)
   "
   ```
   The primary tree sits at `91f90d8` on the OLD engine on purpose, so run 124 measures the cost of 97
   cold-first-scan boards **without** an engine change confounding it. Use the real seconds-per-board to
   size batch 2 of the ~765 remaining candidates. The old "~7s/board, ramp in 10s" figure is wrong —
   steady state is **14.0 s/board**.

2. **Merge the five-PR stack, then pull ONCE.** #185 owes **D-327** before it merges. After pulling,
   apply all three owner facts in a single pass so `engine_version` moves once:
   `eligibility facts set security_clearance.obtainable false`, the declared field of study
   (MS Software Engineering Systems / BE Computer Engineering, `highest_degree` stays `master`), and
   `eligibility policy set degree blocker`. Verify by direct SQL on `profile.eligibility_policy_json`,
   never by the CLI that wrote it. **Then run the owed ledger drain** — trust the tool, not raw SQL.

3. **Re-raise the delivery cap with Mit.** He chose three of four lane-closure options; the one he did
   not choose is the only one that shrinks a pool growing ~182/day.

4. **Two pre-existing defects found and deliberately NOT fixed, each its own change:**
   the degree field expression is bounded `{2,60}`, so a 74-char *"Computer Science, Computer
   Engineering, Mathematics, or a related discipline"* yields **zero** rows (fails safe to `uncertain`,
   silently degraded); and `tests/unit/test_web_server.py:678` (`assert elapsed < 3.0`) is a genuine
   load-dependent flake, still live — **do not weaken the threshold to green a gate.**

5. **Deferred with numbers, do not re-derive:** the residual years-detection gap is **24 leads, ~8 real
   (1.3%)** and widening the pattern rejects `18 years of age`; job-apps' preferred-vs-required HEADING
   state machine is **2 of 286** and architectural (D-320).

**Arming the remaining ~765 Part 4a boards is a SEPARATE owner decision.** Ramp only after run 124's
number is known. Do **not** add a defaulted `watched=` to `upsert_watch`. `companies.source` is
`CHECK (source IN ('registry','user','lane'))`.

*(`.agent/2026-08-27-session-handoff.md` holds the full session detail, and
`.agent/2026-08-25-craft-findings/` + `.agent/2026-08-26-lane-facet/` remain gitignored working
material — re-derive if pruned.)*

---

## Owner-gated — do NOT start or decide unilaterally

0. ~~**THE ARMED LANES LEAK non-SWE noise into delivery — pick one (D-308).**~~ **DECIDED by Mit
   2026-08-26: option (b), build the facet — shipped as D-309.** Recorded because the reasoning bounds the
   next lane: option (c) (extend the role deny-catalog) was measured and REJECTED, not merely passed over —
   the `uncertain` tail is Busser / Water Spider / Dish Steward / Donation Processor / Nannies / Janitorial,
   an unbounded list, and the same bucket holds Linux Engineer, Senior HPC Engineer and Principal Architect
   that a broad deny would lose. **Do not propose a lane-noise fix in the role taxonomy again**; the fix is
   always upstream in what the lane asks for. Item 1 below is also settled by the same probe: hiring.cafe
   showed 100% location fill, so the location fail-open was never the issue — the ROLE fail-open was.

0b. **NO DRAIN EXISTS FOR LANE-ACQUIRED POSTINGS (D-314).** 282 postings, all `open`, none ever closed, and
   the mechanism makes it structural rather than a bug: a lane re-acquires by SEARCH, so absence can never be
   evidence, and `lane_snapshot` is always `partial` so `_process_missing` never runs. An age-based close needs
   a trigger other than absence and a fail-safe direction chosen (closing a live job is the expensive error).
   Also decide whether anything may show an open/closed label for a lane row at all — `postings.status` reads
   `open` forever and cannot distinguish "still open" from "unverifiable".

1. ~~**hiring.cafe's `v5_processed_job_data.workplace_*` fields**~~ **ALREADY SHIPPED — this row was STALE.** D-286 Ruling 4 took the decision and `lanes/hiringcafe.py::_locations` has implemented it since PR #141 (refined in #169). Verified against the live store 2026-08-27: lane postings carry real values (e.g. `"McClellan, California, United States"`). Original text kept below for the reasoning only. ~~**hiring.cafe's fields**~~ — read as provider-asserted location
   metadata, at the level greenhouse's `location.name` is already trusted (D-286 Ruling 4). D-278 called
   that payload untrusted, reasoning from the keystone invariant — which governs eligibility RULES, and the
   engine is body-only so it cannot reach these. The measurement that decided it: `classify_location([])`
   returns `unknown` and the hard US gate PASSES `unknown`, so withholding locations does not filter a
   3.89M-posting board, it admits all of it. On a broader reading the lane needs another location source
   before arming. **One function either way.**
2. ~~**Oracle Cloud HCM / iCIMS as PROVIDERS**~~ **CLOSED by measurement (D-311): do NOT build them.** The
   "~45% of the non-six tail" figure was a share of a small tail. Over job-apps' 138,788-posting ledger,
   Oracle Cloud is **0.84%** and iCIMS **0.44%** — ~1.3% combined, and every remaining platform is under
   0.2%. LinkedIn is 49.7% and Indeed 23.4% of that corpus, so ~73% of the market sits on one lane boardwatch
   already has and one source that is out of scope. **The lever is the LinkedIn lane's budget/paging, not new
   adapters.** Reopen only if a measurement on a different corpus contradicts this.
3. ~~**Run-scoped rank attribution** — the only honest fix for B5~~ **DELIVERED + MERGED (D-302, PR #164 =
   `0fb50a7`).** Four run-scoped suppression twins + the reconciliation invariant; B5 is scoreable and armed
   on the live driver. No code left for B5.
4. ~~**`locations` on `Lead` + an `artifact_version` bump**~~ **AUTHORISED AND BUILT (D-323, PR open on
   `feat/lead-locations-artifact-v7`).** Each lead now carries `locations` and `location_class`, the manifest
   carries `location_filter_mode`, and `artifact_version` moves 6 → 7. No owner decision left.
5. **Mit's two résumé content calls** — whether to send a document at all; the D-220 prose rewrites.
6. **P2 item 8 — the onboarding field-taxonomy gatherer.** Needs its own brainstorm; D-054 forbids us
   authoring non-tech field content.
7. **`add-evidence` takes no bundle lock** (D-143) — raise before two authoring agents run against one bundle.
8. **Extending the leakage query past `exact_quad`** — the Gate P6 clause **cannot fail** for the
   `company_title_location` class, because `store/identity_queries.py:296` hardcodes `kind == "exact_quad"`.
   Dropping ruling 3 did not close this and made it sharper: those duplicates are now neither suppressed nor
   counted, and the corpus holds **1,597 redundant open postings (4.76%)** on that key. **Never cite a
   passing leakage number as evidence dedup works.** One join condition, but it reverses D-132/D-283's
   ratified "only `exact_quad` counts" **while the gate is being measured** (D-294/D-295).
9. **A redesign of same-role-same-place dedup on real discriminators** — the requisition slug in the
   posting's own URL, the city named in the body, the salary band, the YOE line. Ruling 3 is dropped because
   a fuzzy body score provably cannot do this (D-295), not because the duplicates are acceptable. Its own
   change, its own ruling.

---

## Open questions — Mit's, not to be resolved by fiat

1. **The projection spec's six open questions** (§12) — soonest: whether `tailor run` should validate the
   projection manifest, and whether persona's `entries` list survives stage 2.
2. **The Snap `Level 5`/`Level 3` leak stays open by design** — with no bindings file every level token
   abstains, so a level-named title is shortlisted carrying its reason. boardwatch ships no verifiable
   claim about any company's ladder.
3. **Whether `censored` boards publish a coverage ratio**, `detail_fetch_budget`, and the 17 silent boards.

*(Resolved and no longer open: whether `runner.py` should keep swallowing a funnel-write failure — D-288
records it and the run still does not fail. Clearance IS a blocker (D-257). Seniority band = `entry`
(D-258). The launchd trigger fires (D-254), and its cadence is now ~3h (D-288).)*

---

## Phase status

| Phase | Build | Gate |
|---|---|---|
| P0 Instrumentation | **COMPLETE** | **MET** (D-030) |
| P1 Résumé artifact gate | **COMPLETE** | **MET** (D-032/033) |
| P2 Profile + keystone | items 1–7 shipped; item 8 NOT STARTED | **MET AS RECONCILED** (D-075) |
| P3 Unattended one command | **COMPLETE, INSTALLED, FIRING** at ~3h (D-288) | **MET** — 8 consecutive clean scheduled ticks (runs 71-78), verified from the `runs` table + funnels |
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
| **Disk pressure now costs GATE TIME, silently** | The same suite ran **4m51s** at ~7.4 GiB free and **34m40s** at 5.7 GiB / 98% — no error, nothing logged, and a bounded waiter timed out, which reads as a hang. Cause was pytest's own temp trees at **1.1 GB** across 5 runs in `/private/var/folders/*/*/T/pytest-of-mitsheth/`; clearing the stale ones (keep the newest, it is live) plus branch cleanup took the volume to **9.1 GiB / 96%**. The two stale store backups beside the live database are a further **1.67 GB** | **Mit** (the backups) |
| **`make check` must be launched DETACHED** | the Bash tool clamps `timeout` to ~10 min; a longer gate reads as `make: *** [test] Error 143` — that is SIGTERM, not a build break. **`setsid` does not exist on macOS**: use `nohup sh -c '<export PATH>; make check > LOG 2>&1; echo $? > DONE' & disown`, set PATH INSIDE the subshell, and gate on the sentinel file, never the launcher's exit code. The clamp is WALL-CLOCK, so CPU contention converts a comfortable run into a kill — a suite that ran 5m17s alone was SIGTERMed at 62% while one subagent ran its own pytest. Never pipe the gate through `head`/`tail` | tooling |
