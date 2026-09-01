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

**SIX PRs MERGED, NO PRODUCTION RUN. Run 138 is still the latest**; every number below is measured
read-only against the live store or against job-apps' ledger as an independent set. **Run 139 is the
first run that can move a lane number** — the 2026-09-01 measurement window predates hiring.cafe's
first clean run, LinkedIn facet mining arming, and #307/#308 entirely.

Merged: **#306** SmartRecruiters dereference · **#307** aggregator slice · **#308** promoted-queue
root · **#310** Workday dereference · **#311** D-399 · **#312** the case-claim correction · **#313**
the `slug_from_path` chrome fix (gated green, auto-merge armed at close — **verify by main's
CONTENT**: `git grep -c "read by GRAMMAR" origin/main -- src/boardwatch/providers/workday.py`).

**WORKDAY IS DEREFERENCED, AND IT IS THE LARGEST CONVERGENCE ITEM THE PROGRAM HAS SHIPPED.** 87,413
of 93,044 provider-supplied `externalUrl`s resolve with the extracted reference equal to the stored
`provider_posting_id` and **ZERO mismatches**; an independent arm of 4,521 URLs across **606 hosts
against our own 117** resolves 4,456. **896 job-apps finds now converge onto a posting the board scan
already holds** — against D-397's measured 44-posting prize for the suppressor it declined to build.
The old refusal was aimed at the wrong contract: a `PostingTarget` is never fetched, so what had to
be recoverable was `provider_posting_id`, not the `externalPath`. That contract is still unproven.

**A NUMBER THIS PROGRAM PUBLISHED WAS WRONG FOR TWO HOURS, AND THE CORRECTION IS THE MORE USEFUL
RESULT (D-401).** #310 shipped "589 converge, 307 lost to site case". The 307 were never lost:
`stored_slug` folds case and `upsert_lane_company` calls it for every lane snapshot. The figure came
from joining `(slug, ref)` as STRINGS while production resolves the company case-insensitively
first — **a join only models convergence if it models the resolver**. Corrected in #312 to **896**.

**A MEASURED, OWNER-APPROVED, BUILT CHANGE WAS THEN REFUSED AT ZERO BENEFIT (D-401).** The premise
behind Workday site-case preservation *is* false — 60 of 133 watched companies already store a
lowercased site holding 31,395 clean-scanned postings, and a live CXS A/B returned identical totals
both ways (nvidia 2000/2000, bdx 576/576, roche 224/224). The migration was still discarded, because
`stored_slug` already delivers the convergence it was built to buy. **It was also already recorded as
D-339**, reachable with `tools.decisions --find slug case` in one command; the log was not searched
before the proposal was built.

**THE `slug_from_path` CHROME DEFECT IS FIXED (D-400, #313).** `_CHROME_SEGMENTS` contains `jobs`, so
a tenant whose career site is named `Jobs` had its site skipped and the job's **city** read as the
site — a fictional company row per city, 157 live URLs, and neither `redhat/jobs` nor `paypal/jobs`
(325 postings, both watched) could be added by pasting its URL. Site derivation is positional now;
misread URLs through `parse_board_target` go **157 -> 0** over 113,074 real URLs.

**JOB-APPS RETIREMENT NOW HAS A BAR, AND THE FIRST READING IS FAR FROM IT (D-399).** Coverage
**20.4%** against a bar of 80%; precision a **28-point** gap; and **17 of run 138's 96 delivered
leads flow through the jobapps lane**, so 17.7% of delivery dies on switch-off. Company reach re-run
on the identical window still reads 16.4% and is the WRONG instrument — structurally blind to
aggregator lane work.

## Next action

1. **Confirm #313 landed** (auto-merge was armed at close; gate exit 0, 8,848 passed). Check main's
   CONTENT, never the PR page.
2. **INVOKE RUN 139.** Nothing else can move a lane number. It is the first run carrying #304's
   hiring.cafe fix at full effect, #302's LinkedIn facet mining, #307's aggregator slice, #308's
   promoted-queue root, and the Workday/SmartRecruiters dereferences. Read it out against D-399's
   gates with `.agent/2026-09-01b-session/retirement_readiness.py`.
3. **Then, on evidence: the native Indeed and Jobright lanes.** They are 24.2% of job-apps' built
   output (D-393) and the only remaining work that moves D-399 gate 1. **#307 and #308 do NOT** —
   they consume more of job-apps' output rather than reproducing its discovery, which is defensible
   sequencing but must not be scored as progress (recorded in D-399 for exactly this reason).

### Owed, found this session, not yet scheduled

- **The aggregator slice and the promoted-queue root SHIPPED** — #307 and #308. `is_direct_apply`'s
  premise ("landing pages the user cannot apply from") was false for `indeed`/`jobright`, which carry
  posting-specific URLs and are how the owner already applies. `linkedin` stays out on a different,
  measured reason. **Neither advances job-apps retirement** — see D-399.
- **Cross-source dedup — RULED, do not build a suppressor (D-397). The minimum correct fix is now
  COMPLETE.** Six independent barriers, not one; flipping `cross_host.suppresses` is ACTIVELY UNSAFE
  because two call sites hardcode `identity_kind="exact_quad"`, and the measured prize was 22 groups
  / 44 postings. The targeted dereference expansion that D-397 named as the correct alternative is
  **done on both providers — SmartRecruiters (#306) and Workday (#310) — and Workday alone converges
  896**, twenty times the suppressor's prize. Unknown shapes still raise.
- **Do NOT propose lowercasing Workday slugs (D-401, and D-339 before it).** Proposed, sized,
  owner-approved, BUILT and abandoned this session at zero measured benefit. The premise it attacked
  is genuinely false — the CXS endpoint is case-insensitive, probed — but `stored_slug` already folds
  case, so there is nothing to gain and a 54-row irreversible migration to lose.
- **hiring.cafe pacing (D-397 defect 5) is DISCLOSED, not fixed** — one boundary request per run can
  fall inside the >=1.0s window; the only real fix is process-wide pacing state, which would wreck
  the gate.
- **`reports/abstain.STRUCTURALLY_UNDECIDABLE`** — data precondition now met, design question open
  (see below).
- The ledger drain stays DECLINED (D-390); re-check the `built`/`skipped` split before any future drain.
- The two held recall patches at `.agent/2026-08-31d-session/WIP-*.patch` are **DO NOT SHIP** on
  measured evidence. The corpus-regression detector stays dark until ~run 138; do NOT patch it.

## Session 2026-08-31f — what shipped

Read-out and records only; no source changed. **Run 137 verified clean from its sentinel**, the
job-apps lane's first armed run measured end-to-end **through delivery**, #290+#291 confirmed at
production scale against the correct comparator, and **D-392** recorded so the vacuous control and
the wrong comparator are not repeated. #293 (D-391) landed during the session; its diff was verified
docs-only and `DECISIONS.md` checked entry-by-entry (314 -> 315, nothing dropped).

Previous session: **#290** (D-388), **#291** (D-389), **#292** (D-390), **#293** (D-391).

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

1. ~~Does job-apps keep running, or is it retired?~~ **ANSWERED 2026-08-31 — it keeps running.**
   See Next action 3. Both schedulers are armed: boardwatch 04:00, job-apps 08:30. Do not
   re-raise; the remaining judgement is only WHEN to build, not WHETHER.
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
