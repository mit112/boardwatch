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

**THE WHOLE STACK IS MERGED; THE ENGINE MOVES ON THE NEXT PULL, ONCE.** #183 (D-323, lead locations + artifact v7) ·
#184 (D-326, clearance-obtainability + field-of-study facts) · #185 (D-327, the near-duplicate
measurement and the refused reversal) · #186 (D-324, `unverifiable` status) · #187 (D-325, measured-death
close) · the degree-bridge fix (D-328). **`engine_version` moves the moment the primary tree is pulled** —
it is DERIVED from the digested modules, so quote `doctor`, never a pinned constant (D-306). The live
store is still on `1+af3a746837b1` because the tree is deliberately unpulled.

**THE THREE OWNER FACTS ARE APPLIED, AND THE STORE IS ON THE NEW ENGINE (2026-08-27 ~22:52Z).**
`security_clearance.obtainable=false`, `field_of_study=software_engineering`,
`policy.families.degree=blocker`, written in one pass; `highest_degree` remains `master` and
`work_authorization` / `total_years_experience` were untouched. **NO ledger drain ran and none is owed
(D-331)** — verified independently: `job_dispositions.reopened_at` is set on 12 rows, the same 12 as
before. **`engine_version` was `1+af3a746837b1` and read `1+7485e3a85f38` after the move — but DERIVE it,
never quote either** (D-306): `python -c "from boardwatch.eligibility.engine import engine_version;
print(engine_version())"`. This line has gone stale three times in one day; the value is a timestamp, the
derivation is the fact.

**BOARD COST IS PROVIDER-WEIGHTED, AND s/board IS A LYING UNIT (run 124).** Run 124 ran the OLD engine
on the ramped fleet, which isolates fleet cost from engine cost: **346 boards, 3,424 s (57.1 min)**
against run 123's **234 boards, 3,370 s (56.2 min)** — **+112 boards for +54 s, i.e. 0.48 s per ADDED
board.** The old **14.0 s/board** figure predicted 81 min and was wrong by **24 minutes**. Two further
models also died on this run: cold first scans are the CHEAPEST rows in it (lever 1.11 s, greenhouse
0.46 s, ashby 0.38 s, workable 0.26 s — a registry ATS board arrives in one JSON call), and per-posting
work is not the constraint either (attribution advanced **2,299 → 10,168**, 4.4×, for that same +54 s).
**One provider is 73.4% of the run: `workday`, 114 boards contributing 22.03 s of wall clock each =
2,512 s.** SmartRecruiters is the same order. Everything else is 0.26-3.3 s/board, cold or warm.
**That unit is MARGINAL WALL CLOCK at `scan_workers = 4`, not per-board latency** — the scan fetches
concurrently, so inter-completion gaps sum to wall clock by construction; true latency is ~4x (Workday
~88 s, derived). It is still the right unit for sizing, because concurrency does not change when boards
are added. `board_scans.started_at` cannot answer this at all: `apply_board` is handed an already-fetched
snapshot, so those timestamps time only the DB write (26.5 s of a 3,286 s run) — **the missing
instrument, and the next thing worth building.** **Size every future batch by
provider mix, never by board count.** Cadence is 180 min. Full table in `METRICS.md`.

**THE FIRST RUN ON THE NEW ENGINE PROJECTS TO ~124 MIN — 56 min of headroom, the tightest a run has
ever been, and a ONE-OFF.** Derived, not guessed: run 119's full re-evaluation cost **3,064 s (51 min)**
over 61,875 considered postings; the corpus is now 80,737 open (x1.30), so the surcharge scales to
**~67 min** on top of run 124's steady 57 min. Check the real number against this before assuming the
cadence is safe for the NEXT engine move — and note this is exactly why the whole eligibility stack was
batched into one move.

**THE WATCHED FLEET IS 346, UP FROM 234 (owner-authorised 2026-08-27).** 97 boards imported via
`companies discover` → review → `import --verify`; the probe skipped `lever:cirrus` and
`ashby:Commure-Athelas` as dead, and `lever:cirrus` had been **hand-approved in error** — the adapter
lists `jobs.eu.lever.co` in `board_hosts` but the API call is `api.lever.co/v0/postings/{slug}`
regardless. **Always `--verify`.** `ashby:KAYAK` was removed pre-import for a CASE collision with
watched `ashby:kayak`. Separately, **15 lane companies on a registry ATS were promoted to `watched=1`**
(11 ashby, 3 greenhouse, 1 lever), so zero enumerable lane companies remain unwatched and the
cannot-close class went 745 → 722. **~765 discover candidates remain capped, and run 124 sizes them.** The
~325 non-Workday/non-SmartRecruiters candidates cost **~3-6 min total** — take them in ONE batch, the
trickle is no longer justified. SmartRecruiters 107 ≈ **+40 min**. Workday 333 ≈ **+122 min**, which puts
the run AT the 180-min cadence, so it must be chunked at ~100 (+37 min each). **Unmeasured and the one
that matters: no COLD Workday or SmartRecruiters board has ever been timed**, and those are the two
providers that burn a per-posting detail budget on a first scan — import ~10, read the next run's delta,
then size the chunk.

**LANE POSTINGS CANNOT CLOSE, AND ABSENCE IS PROVEN MEANINGLESS — SETTLED, DO NOT REOPEN
(D-314/D-324/D-325/D-329).** The class is **722** rows on the honest predicate `companies.watched = 0`
("nothing enumerates this board"), growing **~182/day**, and **the owner has ruled the pool may grow
(D-329)**: the three honesty options shipped and the deliverability cap was declined against the
measurement. **Age-based and missed-run closing are REJECTED BY MEASUREMENT — do not propose either
again**; the mechanism, the natural experiment behind it and the probe's 6.7% power are in
`STANDING-FACTS.md` § Lanes and JD acquisition.
**SCALE (2026-08-27, measured after run 124).** **4 published releases, latest `0.5.0`**, ~53k lines of
source, **8,000+ tests**, 71 leaf CLI commands, 6 ATS providers, **346 watched boards**, 124 runs, and a
**2.9 GB** store holding **90,915 postings / 80,737 open**. Output is bounded by `DEFAULT_TOP_N = 10` leads per run, so
**breadth is argued on precision and capacity — never on an application count** (D-312, owner's standing
rule, reaffirmed 2026-08-27). boardwatch produces leads and deliberately does not apply: auto-apply is
out of scope, and `applications` rows exist only where the user marks one.

**THE STORE IS AT `p_death_probe`, which IS `main`'s head — verify, do not assume.** #187's migration was
applied deliberately ahead of the fact write on 2026-08-27 and confirmed: `alembic_version` =
`p_death_probe`, both `postings.death_strikes` and `postings.last_death_probe_at` present,
`PRAGMA foreign_key_check` empty. **Check this rather than trusting this sentence** — it has been wrong
before, and `SELECT * FROM alembic_version` answers it in a second. The ordering that made it safe is
worth keeping: any `boardwatch` command with a default context runs `alembic upgrade head` through
`build_context`, so an unremarkable `eligibility facts set` would otherwise apply a schema change as a
silent side effect. **The rule this bought: after any PR that adds a migration, apply it to the live
store deliberately and verify, rather than letting the next unattended tick discover it.** **There is no
rollback snapshot** — all three stale backups were verified redundant and deleted (2026-08-23b, ~2.9 GB
reclaimed). Take one before any destructive operation rather than assuming one exists.

**THE QUEUE ROOT IS NO LONGER A BLIND-APPLY SURFACE CARRYING UNVERIFIED LEADS (D-332, #192).** The
queue was **82% `uncertain`** (314/383, only 27 `eligible`), and a lead is `uncertain` precisely BECAUSE
a ranker gate failed open on it — the hard US gate passes location `unknown` (the visa ruling) and the
role gate passes role `uncertain`. Live leaks, all US-located non-software delivered across runs 115-125:
**Allstate "Field Auto Appraiser", Humana care-support, ITW "Recycle Operator", Hyatt "Front Office
Agent"**. A fourth drain `_review` now sits beside `_ineligible`, and
`delivery/review_gate.lane(verdict, locations, title)` is the **one** definition of the split, called by
both writers. `eligible`→apply; `ineligible`→review (defensive); `uncertain` OR `None`→apply only if
**confirmed US and confirmed SWE**. **`_review` is a sync-MANAGED lane, not an exclusion** — leads are
BORN there and are drawn back up if their class changes, so it self-heals both ways. **Location fails
OPEN, role does not**: demote on `== "non_us"`, NEVER `!= "us"` — bare `"Remote"` reads `unknown` and
remote is most of the SWE set. Measured read-only mid-run-126: **668 rows → 464 apply / 204 review**, of
which **198 are non-software titles** and 6 confirmed non-US. That same snapshot showed **all 668 rows at
`verdict = None`** (every evaluation staled on the engine move), which is why `None` routes like
`uncertain` — the alternative empties the whole queue. **No engine change, no migration, no drain.**
**The web page is NOT filtered — Phase 1b, owner-gated** (see below).

**`DEFAULT_TOP_N` is 10 — a HOLDING value until the precision work lands (D-293).** Do **not** raise it
before the precision work is merged, and do **not** set it to 0 (that fails B1 outright while Gate P3's
counter keeps running). Lifting it is Mit's call and is informed on both sides — the measured uncapped
set and the population caveat are in `STANDING-FACTS.md` § Precision gates (D-292/D-293/D-294).

---

## Next action

1. **RUN 126 (01:00Z) MEASURES TWO THINGS AT ONCE — the live work is DONE and this is the check on it.**
   (a) **The re-evaluation surcharge.** The migration and the three owner facts were applied
   2026-08-27 ~22:52Z, so 126 is the first tick on engine `1+7485e3a85f38` and carries the full spike:
   **projected ~124 min against a 180-min cadence, 56 min of headroom, the tightest a run has ever been
   and a ONE-OFF.** Read the real number against the projection in `METRICS.md` rather than re-deriving
   it; if it overruns, that projection is the first thing to check, not the fleet size.
   (b) **The FIRST real per-provider fetch cost**, because the tree was pulled to `3619546` so 126 also
   carries D-330's instrument. That replaces the inferred completion-gap numbers behind the batch-2
   sizing with measured `scan.fetch_cost` — read it out of `funnel-126.json` and compare against the
   inferred table in `METRICS.md`. Pulling #190 in was safe and checked: it adds no migration, touches no
   `tables.py`, and `engine_version` is UNCHANGED across the pull, so there is no second re-evaluation.
   **Expect the measured latency to be ~4x the inferred marginal figure** (a Workday board ~88 s vs the
   ~22 s of wall clock it contributes at `scan_workers=4`) — if it is not, one of the two is wrong.

   **Before ANY pull or store write, guard on PROCESS liveness, never the `runs` table:**
   ```sh
   pgrep -f "bin/boardwatch run"   # empty = idle; any PID = still working, wait for it to exit
   ```
   **Match on `bin/boardwatch run`, not `boardwatch run`.** `pgrep -f` matches full command lines, so the
   bare pattern also matches the agent's OWN shell whenever the probe command contains that string — it
   reports a phantom PID and a session waits forever for a run that already exited. Confirm any hit with
   `ps -o pid,ppid,command -p <PID>`: the real run's parent is `1` (launchd) and its command line starts
   with the venv's `python3`.
   `runs.finished_at` is written BEFORE the process exits — funnel and morning artifacts are emitted from
   a `finally` after the row closes (D-024). Run 125: `finished_at` 22:50:08.8, artifacts at 22:51,
   process gone at 22:51:40 — **92 seconds of work after the table read `ok`.**

2. **#192 (D-332, the apply/review queue split) is the one thing open**, on
   `feat/apply-review-queue-split`, rebased on `main` `86da8cd`, auto-merge armed (squash). The earlier
   stack all landed: #185 (D-327) 22:42Z, #190 (D-330) 23:13Z, #188 (STATE/METRICS/STANDING-FACTS)
   23:52Z, #191 (D-329/D-331) . **Read CI job conclusions from
   `gh api repos/mit112/boardwatch/actions/runs/<id>/jobs`, not `gh pr checks`** — the latter has
   misreported on this repo. Two rebase traps were paid for and now live in `STANDING-FACTS.md`
   § Process lessons — the silent `CHANGELOG.md` one is the dangerous half.

3. **Batch 2 of the ~765 discover candidates is now a SIZING question with an answer** — see the
   provider-weighted table above and in `METRICS.md`. The ~325 cheap ones go in ONE batch. **Probe ~10
   cold Workday boards first**: no cold Workday or SmartRecruiters board has ever been timed, and they are
   the two providers that burn a per-posting detail budget on a first scan. **Held OFF run 126
   deliberately** — 126 is the ~124-min spike against a 180-min cadence, and the probe is free on 127.
   Do NOT generalise from the cheap providers: their cold scans were the CHEAPEST rows in run 124
   (0.26-1.11 s/board), and Workday is the one case where a first scan also burns a detail budget.

4. **One pre-existing defect remains, and it is deliberate:** `tests/unit/test_web_server.py:678`
   (`assert elapsed < 3.0`) is a genuine load-dependent flake — **do not weaken the threshold to green a
   gate.** The other one from this session, the `{2,60}` degree bridge, is FIXED (D-328).

5. **Deferred with numbers, do not re-derive:** the residual years-detection gap is **24 leads, ~8 real
   (1.3%)** and widening the pattern rejects `18 years of age`; job-apps' preferred-vs-required HEADING
   state machine is **2 of 286** and architectural (D-320).

*(`.agent/2026-08-27-session-handoff.md` holds the earlier session detail; `.agent/` is gitignored
working material — re-derive if pruned.)*

---

## Owner-gated — do NOT start or decide unilaterally

5. **Mit's two résumé content calls** — whether to send a document at all; the D-220 prose rewrites.
6. **P2 item 8 — the onboarding field-taxonomy gatherer.** Needs its own brainstorm; D-054 forbids us
   authoring non-tech field content.
7. **`add-evidence` takes no bundle lock** (D-143) — raise before two authoring agents run against one bundle.
8. **Phase 1b — whether the WEB page follows the queue split (D-332).** The folder tree now holds review
   leads in `_review`, but `api.py::queue_payload` still LISTS uncertain/not-swe leads flagged
   `off_target`, which is the documented **"uncertain is not a veto"** design. Filtering them out reverses
   that design and needs a review SECTION in the React UI plus a bundle rebuild (`make web`, commit both).
   **Do not silently exclude review leads from `queue_payload`** — that drops ~204 leads off the page with
   nowhere for the owner to see them. Mit's call: filter + section, keep as-is, or a third framing.

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
