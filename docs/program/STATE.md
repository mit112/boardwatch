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

**RUN 140 IS VERIFIED CLEAN AND EVERY PREDICTION IT WAS INVOKED TO TEST CONFIRMED.** Sentinel exit
**0**, `status='ok'`, **44m55s**. 379 boards attempted, 1 failed (marqeta 404, the same dead board),
293 complete. 27,747 seen, 1,785 new, 843 closed, **96 tailored résumés**. `engine_version`
**UNCHANGED at `1+532b917626c0`** — the run's "taxonomy changed" line is the EXTRACTION taxonomy, not
the eligibility engine, so **no ledger drain is owed**.

| prediction | result |
|---|---|
| hiring.cafe cap -> 0 refused, ~291 new companies | **0 refused, 291 new** (resolved bodies 262 -> 801) |
| delivery queue failures 4 -> 0 | **1** — and it is the predicted pre-existing eBay 131368 conflict |
| onX / WellSky / Generalmotors get queue folders | **all three have folders** |

**GATE 1 MOVED FOR THE FIRST TIME: 20.4% -> 22.2%** (independent 44 -> 48, same 216 population).
Gate 3 **HELD at 48**; carry 48 forward as the baseline. **The coupling COLLAPSED: `jobapps` lane
share of delivered leads 49.0% -> 2.1%** (2 of 96). Run 139's 49.0% was the artifact — it was the
lane's first armed run, admitting 102 companies from a one-off backfill; run 140 admitted **0**.

**THE SESSION'S REAL OUTPUT IS `docs/program/RETIREMENT-PLAN.md` (#324).** Every session since the
`jobapps` lane shipped had re-run the comparison against job-apps and then reached for a boardwatch
knob. That file holds the finished analysis — the gap decomposed by tier with the arithmetic,
job-apps' full 33-source list against boardwatch's 8, job-apps' three LinkedIn mechanisms, the
settled-and-refused list, and reproduction commands. **Read it before proposing any discovery work.**

**THE FINDING THAT UNBLOCKS GATE 1: `location=` on LinkedIn's guest endpoint is NOT inert, and a
shipped docstring said it was (D-409).** `page_url` claimed it "was measured to return an id-identical
set". Probed live: no location -> 0 of 10 cards in TX; `location=Austin, TX&distance=25` -> **0 shared
ids, 9 of 10 in TX**; Boston -> **0 shared, 10 of 10 in MA**. It binds, filters, and returns a
DISJOINT population. **A wrong measurement in a docstring is worse than none — it stopped every later
session from looking**, and it is why the lever was hunted in page depth and caps instead.

**SMARTRECRUITERS WAS STORING RAW HTML IN 99.9% OF ITS BODIES, AND IT IS NOW FIXED AND DRAINED
(D-408, #323).** 2,992 of 2,996 open postings carried markup against 0.0% for every other converting
provider. The parser fix alone would have repaired NOTHING — `known_posting_ids` keeps stored
postings out of detail fetching — which **an adversarial review caught against my own briefed
premise**. Drain applied over 3,311 rows: **3,307 rewritten**, verified through five paths other than
the command's own report (markup 0, hash mismatches 0, 3,307 `revised` versions with NULL `run_id`,
originals still holding the HTML, 0 open postings missing an identity row).

## Next action

**EXECUTE `docs/program/RETIREMENT-PLAN.md`, IN PARALLEL. Do not re-derive its analysis.** The owner's
instruction is to prioritise wall-clock and run as much concurrently as possible.

1. **Start the drop audit first** (plan §5 Track D). No source files, no gate, no conflicts — it
   soaks through every other track's gate time. Run 140 dropped **60,491 hard-filtered + 39,404
   non-SWE**, unaudited, and nothing in `src/` or `tools/` implements a false-drop measurement. It
   bears on gate 1 AND gate 2.
2. **Land Wave 0** — one PR adding every settings field every track needs, registered in all four
   gated sites, so the shared edit surface stops forcing serialization. One gate.
3. **Dispatch Tracks A, B, C together**, one worktree each: LinkedIn geo nets; the native Indeed
   lane; the `gh_jid` resolver. Queue gates **two at a time** — a contended `make check` reports
   `Error 143` and reads as a false negative. sol-review each; reviews cost no gate time.
4. **Re-read gate 1 after one run**, then Wave 2 (tier-D adapters, which **must be LANES, not a
   seventh `Provider`**).

**IN FLIGHT AT CLOSE:** Track A is built and pushed on `feat/linkedin-hub-nets` (worktree
`../bw-hubnets`) — the nets, the rotation, the `location=`/`distance=` URL builder, the docstring
correction, and all four gated registration sites. **NOT MERGED, and it FAILED its first gate**
(`mypy --strict`: `Returning Any from function declared to return "int"` at `runner.py:470`, from
`scalar_one()` being typed `Any`); fixed with an `int()` cast and re-gated, result unread at close.
**A `gpt-5.6-sol` review was also unread at close.** Its author's handoff asserted "no unresolved
implementation ambiguity remains" while the gate was red — so verify both before landing, and treat
the delegated handoff as a claim rather than evidence.

### Owed, found earlier, not yet scheduled

- **`ashby:Lightfield` duplicate pair stays as recorded residue (D-405, Mit's call).** 19 duplicated
  open postings, **zero artifacts ever delivered**. Drain owed — merge onto company 323, delete 348 —
  when something next touches company identity or the Ashby lane.
- **One queue failure survives #316 and is pre-existing**: `posting 131368: eBay_..._59eb81b3 already
  exists at its destination`. A null control confirms unfixed `main` performs the same rename, so it
  is neither caused nor fixed by #316. Still present in run 140.
- **`_identity_hash` reads the mutable `apply_url`; exposure is 239 of 861 offered leads (27.8%)**
  carrying the eight-hex suffix in their folder name. A rename is reported as `moved` and keeps its
  contents, so the cost is the owner's open path changing, not data loss. Dropping `apply_url` would
  re-key 239 folders in one run. **DEFERRED by Mit 2026-09-01** as the lowest-value of four.
- **9 postings carry jobright PAGE TEXT as their JD, including its own `H1B Sponsor Likely` label
  (D-406).** ZERO evidence spans quote it and the keystone invariant holds, but `work_auth` is a
  blocker family. Mit ruled 2026-09-01: **add a lane-body ingest precondition and quarantine the 9
  with a drain.** Not started. (Measured wider than recorded: 12 postings carry a `jobright.ai` URL,
  9 with full page-text bodies and 3 stubs; 8 carry the H1B label.)
- **`lane_search_pages` was raised 5 -> 10 on the owner's call, and it reaches at most 11 of the 77
  LinkedIn misses.** Recommend reverting to 5 once the geo nets land: it costs ~+2.3 min/run and
  doubles hiring.cafe's volume on a robots-disallowed path. Owner's call, not unilateral.
- The ledger drain stays DECLINED (D-390). The two held recall patches at
  `.agent/2026-08-31d-session/WIP-*.patch` are **DO NOT SHIP** on measured evidence.

## Session 2026-09-01d — what shipped

**Three PRs merged, one open, one config change, and the drain applied to the live store.**

- **#320** — `outcomes.py`: `not_attemptable` outside hiring.cafe is not "the budget was spent".
- **#322** — STATE's shipped section named all seven of session 2026-09-01c's PRs.
- **#323 — D-408.** SmartRecruiters HTML -> text, plus `boardwatch postings reparse-bodies`, the
  drain the scan path cannot reach. **Applied: 3,307 postings, 5,984 identity rows.**
- **#324 — D-409.** `RETIREMENT-PLAN.md`, arranged for parallel execution, indexed in `CLAUDE.md`.
- **Config:** `lane_search_pages` 5 -> 10, verified through `load_settings()` rather than the file.
- **D-410:** Indeed **APPROVED by the owner**, and measured to need **no JobSpy dependency** — one
  `httpx` POST returns 100 postings with full inline JDs in 0.57 s, ~420x cheaper per JD than the
  LinkedIn lane.

**Three proposals were refused with measurements rather than opinions**, two of them mine: a native
Indeed lane on the robots-allowed path (one 200, then a captcha), a JD-body recovery layer (**0 of 61**
`jobapps` stubs dereference to anything), and the `gh_jid` resolver as a gate-1 lever (**5 of 216** —
real, cheap, but not a lever). **And one claim of mine was retracted mid-session:** "31.6% of
delivered leads are below the body floor" measured the INSTRUMENT, not the leads — 2,571 of workday's
2,795 below-floor postings fail on `<1 section marker`, and posting 59284 is 3,397 chars over 20
lines with 0 markers. Extending the floor to the ATS path as-is would have dropped ~4,500 real JDs.

## Doctrine change — "breadth is last" is RETIRED (D-391, owner's call 2026-08-31)

The `CLAUDE.md` section is **deleted** and the live pointers in `PROGRAM.md` and `STANDING-FACTS.md`
are gone. It reasoned about an ASSUMED downstream; that downstream is instrumented now, so the
question is answerable with numbers per change instead of settled in advance by an ordering rule.
**Nothing replaces it** — input work is sequenced on measured evidence like anything else.

**The decision logs are append-only and were deliberately left alone**, so D-280, D-296, D-345 and
others still argue from the principle. **Meeting the phrase in an old entry does not make it
current** — D-391 is the reason. Still live, and stated where they belong: every quarantine needs a
drain designed in the same change; a cap never observed firing is unverified; the keystone invariant
is untouched.

## Owner-gated — do NOT start or decide unilaterally

1. ~~Does job-apps keep running, or is it retired?~~ **ANSWERED — it keeps running until gate 1 is
   met.** Both schedulers armed: boardwatch 04:00, job-apps 08:30. **The retirement work is now a
   written plan, not a question: `docs/program/RETIREMENT-PLAN.md`.** Do not re-raise WHETHER, and do
   not re-derive the gap analysis.
   ~~2. Indeed's dependency posture.~~ **DECIDED by Mit 2026-09-01 (D-410): approved.** Closed; do
   not re-open or re-probe.
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
| ~~The `experience_years` group reads a REFINEMENT as a CONTRADICTION~~ **CLOSED by #291 / D-389** | `refinement_groups` ships as a second group kind in versioned catalog DATA: `exclusive_groups` keeps PRESENCE semantics, `refinement_groups` dissolves only on a real `MET`/`UNMET` straddle. Only `experience_years` moved — **a global rule regresses 8 of 1,034 corpus cases** (D-388), because `clearable_required` is a DISJUNCTION not a weaker rung. **913 of a PINNED 1,868 flip `uncertain` -> `ineligible` (48.9%)**, corpus 0/1034 (predicted before review). **`engine_version` MOVES so a LEDGER DRAIN IS OWED.** Known property, direction deliberate: the refinement pass runs BEFORE stage 1b, so a same-implies split beside another present member dissolves the group where stage-1b-first would let a decisive `unmet` stand — the shipped order is the ABSTAIN direction | **CLOSED** |
| **boardwatch sees 16.4% of job-apps' eligible yield — RE-DERIVED 2026-08-30, and the METHOD was wrong before** | **45 of 275 (16.4%)**, cohorts 08-23..08-29, on the **379-board fleet**. This replaces "10.1%, owed a check". It decomposes: fleet growth 344->379 gave 10.1 -> **13.8%**; adding an **exact ATS-slug key** alongside name matching gave 13.8 -> **16.4%**. **Name-only matching undercounts, so 7.7% and 10.1% are FLOORS** — boardwatch stores Micron as `Micron TDIT`, so the old method scored a watched company as unwatched; same for HPE/`Hewlett Packard Enterprise`, Cox/`Cox Automotive`, Disney/`Walt Disney Company`, Toyota, VIAVI. **The unreached 230 split: aggregator-only 60.7%, unsupported employer host 21.1%, board-addable just 1.8%** (5 postings in 7 days, 4 of them SmartRecruiters — the class D-370 declined on measured cost), so the cheap remainder is ONE Workday board (Motorola Solutions). **The gap is lanes, not boards.** Script: `.agent/2026-08-30-session/reach_v2.py`. Amazon/TikTok/Apple/ByteDance use none of the 6 ATS, so a slug cannot reach them. Closing it means a new discovery lane — GitHub new-grad lists are 19.1% of yield for ~5 public-repo GETs and are NOT the ToS trap the v2 decision was written about. **Reopens D-008** | **Mit** (reverses a shipped decision) |
| ~~Delivery-drought cannot see APPLY-LANE starvation~~ **CLOSED by #285 / D-384** | `delivery_drought.py` counts `artifacts.kind == TAILORED_KIND`, written **regardless of which lane `review_gate.lane()` routes to**, so a global misclassification shipped zero apply-ready leads with every existing alarm green. `check_apply_lane_drought` now fires when the last 3 clean runs each delivered PLACEABLE leads and none reached the apply lane. **The old sizing was wrong, not merely pessimistic**: it priced a guard inside `_sync_queue`, but the three job-id readers already take only a connection and `QueueRow` already carries `delivered_run_id`, so nothing in `review_gate`, `_sync_queue` or the web server's result type had to change. Known property, direction abstain-not-alarm: `delivered_unapplied` attributes a re-delivered job to the NEWER run, so an older run can read zero placeable and the window abstains | **CLOSED** |
| ~~Four detector fallbacks are print-only, not durable~~ **CLOSED by #260** | The `intake-death` / `delivery-drought` / `liveness-blindness` / `corpus-regression` "check not run" handlers now call `append_run_error` like the three artifact-write handlers beside them, so a DETECTOR that crashes leaves a row in `runs.errors_json` and not only a digest line. Four one-line additions, inert on the normal path; each pinned by its OWN parametrised test, because a single test crashing all four passes while three of the four calls are missing. **Known shared property:** `append_run_error` is not internally defensive and these sit inside `except` handlers — matched to the three existing handlers deliberately rather than diverging; it needs two simultaneous failures and fails loudly via the withheld heartbeat | **CLOSED** |
| **`companies.last_health` / `last_ok_at` are a LYING instrument** | 178 of 379 watched boards read NULL, which looks like "never succeeded" — **all 178 were scanned by run 133** (128 complete, 7 partial, 43 unchanged). The scan path does not maintain these columns. **Judge fleet health from `board_scans` per run instead**: run 133 was 379 attempted / 271 complete / 87 unchanged / 21 partial / **0 failed** | tooling gotcha |
| **Citi sits at 13.1% coverage, permanently** | Workday's `total` censors at 2,000; the facet sum (uncapped, control-verified) says 4,589. Our pager wraps at ~2,000 too, so post-drain Citi holds ~2,214 of 4,589 and nothing reports it | **Mit** (input-side) |
| **`unchanged` staleness is now BOUNDED (D-298, #153)** | The `unchanged` verdict comes from the upstream HTTP validator (ETag/Last-Modified → 304), not a boardwatch payload hash. `validator_max_age_hours` (default 24) drops a validator older than the TTL, forcing an unconditional refetch, so a permanently-stale upstream can no longer freeze a board forever — the silent-staleness window is capped at the TTL, and a regression test now exercises the aged-validator refetch. Still open: within the TTL an `unchanged` is trusted with no independent check. The separate "59 of 135 boards listed nothing" figure was a **`postings_listed`-on-304 artifact — CORRECTED to 17 real dead-weight (D-300)**, now cleaned; the 118 `ok` boards hold 39,253 open postings | open (mitigated) |
| **`resume.yaml` is an IMPORT SOURCE, never hand-fixed** | D-155. Mit pins `resume_max_pages=1`; never advise 2 | Mit |
| **`boardwatch top` advances the queue by default** | records `seen` unless `--no-record`; relevant to Gate P6's clean window | P6 |
| **A live store is readable ONLY via Python `sqlite3` `?mode=ro`** | the `sqlite3` CLI with `?mode=ro` fails `CANTOPEN(14)` on a cleanly-checkpointed store (no `-shm`; not the sandbox), and `?immutable=1` skips the WAL so it is STALE against a live writer. Mid-run progress: `SELECT COUNT(*) FROM eligibility_evaluations WHERE run_id=N` (D-268) | tooling |
| **The unattended 04:00 tick runs the PRIMARY checkout's branch — and it is now PROVEN to fire** | Run 131 (2026-08-29, `runs = 1`, exit 0) was the first real unattended tick. The launchd job invokes the **editable** venv at `boardwatch/.venv/bin/boardwatch`, so whatever branch that tree is parked on IS the unattended run's code and `rules.yaml`. **Verified at the 2026-08-29f close: the tree is on `main` at `10baad5`, clean, and all six alert modules import through the editable venv.** A stale 8-hour-old `.git/index.lock` had silently blocked every `git pull` that session — check the lock's MTIME and `pgrep -x git` before blaming contention. **Park it on `main` before ending every session** — from ~2026-08-31 a stray branch changes EVERY subsequent run, not one. Closing it mechanically means pointing the plist at a worktree pinned to `main`, which moves a scheduled job and a venv | **Mit** (mechanism); every session (discipline) |
| ~~**hiring.cafe lane is DOWN**~~ **CLOSED — run 138 reports NO hiring.cafe error**, the first clean run since 129, ending a 14-of-14 refusal. The lane was re-pointed at the SSR surface (#304, D-397) and resolves bodies through the EMPLOYER's own board, so its postings land under greenhouse/lever/ashby/workable and NOT under a `hiringcafe` provider — do not read that absence as failure. Historical detail follows | **History, kept only so the dead ends are not retried.** The header lever FAILED (D-369/#245, run 133 reproduced the refusal byte for byte) and headers are ELIMINATED — do not repeat that experiment. The UA and volume premises were both false. The cause was the ENDPOINT: our `/jobs/` calls were refused 14 of 14 while job-apps succeeded on `/`. **D-393 decision 1 reversed the do-not-probe hold on Mit's explicit call**, and #304 re-pointed the lane at the SSR surface, which is what run 138 proves works | **CLOSED** |
