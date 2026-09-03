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
> Mit's ruling, **again on 2026-08-26** (30 settled blocks, 511 → ~260 lines), and **again on
> 2026-09-03d** (95 lines: the whole nine-decision apparatus, run 145's readout, and five closed
> blocks). Nothing was deleted on any of the three passes. Do not narrate a decision here that
> `DECISIONS.md` already holds — cite its number instead. **If this file passes ~250 lines again, the
> fix is to move settled blocks out, not to summarise them away.**

---

## Current standing

### Session 2026-09-03d: gate 1 moves 26.5% → 28.8% with dependency AND absence falling TOGETHER — the Indeed admission cap was the binder, the 50-board hiring.cafe sample is reverted, and every one of the nine owner decisions is now executed or closed

Reasoning: **D-455** (A8, ruled and shipped), **D-456** (A7, ruled and reverted), **D-457** (the
delivered PDF's name and metadata), **D-458** (A3, shipped), **D-459** (the Indeed uncap). Numbers:
`METRICS.md`, `Session — 2026-09-03d`, which reads out **runs 148 and 149**. **Seven PRs merged** —
#360, #361, #362, #364, #365, #366, #367 — each verified against `main`'s CONTENT, never a merge
message.

**Gate 1, run 149 against run 147 — LIKE FOR LIKE**: same 14-day window (2026-08-21..09-03), same
21,497-posting population, same instrument.

| | run 147 | run 149 |
|---|---|---|
| independent recall (drawn-from) | 5,377/20,289 = **26.5%** | 5,838/20,289 = **28.8%** |
| lane-only (dies at switch-off) | 8,244 (38.3%) | **7,984** (−260) |
| absent | 7,719 (35.9%) | **7,508** (−211) |
| whole population | 5,534/21,497 = 25.7% | 6,005/21,497 = **27.9%** |

Per source: linkedin 34.8 → **37.0%**, indeed 15.5 → **17.2%**, hiringcafe 20.7 → **25.5%**, jobright
14.3 → 15.1%, greenhouse 95.4 → 96.9%. Marginal day 2026-09-03: 34.0% → **42.2%**.

**`lane-only` and `absent` fell TOGETHER**, which is the opposite of run 147's reading, where
two-thirds of the gain went to lane-only. **That is what closes D-452's own honesty bound**: the
uncap FIXED the gate rather than merely MATCHING more postings. **Read D-450 before treating any
level here as posting-level recall** — for 87% of the population only the fuzzy `(company, title)`
key can fire, so this measures equivalent-role coverage.

**The honest residual is still LinkedIn, and the decision on it is ACCEPT THE LOSS (D-453): 395
postings = 28/day**, at 318 employers. No track priced there changes its order of magnitude.

### The nine owner decisions are CLOSED — the whole apparatus moved WHOLE into `STANDING-FACTS.md`

A1/A5/A6/A9 were already done; **A3 and A8 shipped in session 2026-09-03d** (#367, #364); **A7 was ruled and
executed the same day** (revert); A2 is answered and its artifacts turn out not to be gate verdicts; A4 is refused on
measurement. Nothing in that table is still a question. Mechanisms: D-443, D-439/D-444, D-446,
D-447, D-449, **D-455**, **D-456**, **D-458**.

## Next action

**THE SEVEN THINGS OWED INTO THE NEXT SESSION. The drain is first, and it is first because the owner
put it there.**

1. **THE LEDGER DRAIN — DEFERRED BY THE OWNER EXPLICITLY (2026-09-03 18:03, "next session").** #364
   moved `engine_version` (now `1+bf844e01ebcb`), so a drain **is** owed; it releases ~99% of 1,703
   dispositions ≈ **1,689 leads re-delivered**. A3 landed first, so they route correctly (D-458).
   **Best order: let the 04:00 tick re-key first, THEN drain against fresh verdicts** — draining now
   re-delivers leads judged under the old catalog. Stage it with `--job <id>`.
2. **A TIER-AWARE INDEED CAP** (code). `lane_new_companies_per_run_overrides` is keyed by **lane, not
   tier**, so refusing tier 2 freely while admitting tier 1 under its own bound needs a change. The
   interim value is **50, restored at the end of this session** — the owner ruled *keep the 58
   boards*, which is not *leave the cap off* (D-459).
3. **D-436's THIRD OUTCOME per rule family — DEFERRED by the owner (2026-09-03 14:51).** Make "the
   extractor found nothing in the TEXT" distinguishable from "a rule decided". It is the root cause
   of the **43-48% requirement-row band across every secondhand lane** (jobapps 48.4%, jazzhr 47.4%,
   hiringcafe 46.2%, workable 43.5%) against greenhouse 84.9% / linkedin 84.2%. The abstain report
   cannot see an extraction gap by construction, and more catalog patterns measure at ZERO.
4. **THE REFUSED-AGGREGATOR FILTER — DEFERRED by the owner (2026-09-03 14:51).** Should the jobapps
   lane ingest records whose only URL is a refused aggregator? **186 jobright.ai-hosted records**: 70
   caught by #331's body guard, 115 judged anyway, delivering a tailored résumé at **24.7%** against
   13.4% for the rest of the lane — and **31 of those 46 delivered leads (67.4%) carried ZERO
   requirement rows**. One-line filter; drops 186.
5. **hiring.cafe LANE THROUGHPUT** — ceiling **1,331 postings (+6.19pp)** for zero vendor work
   (D-451). Highest unstarted gate-1 lever now that Indeed is proven.
6. **`projection/run.py:502`'s preview PDF still has no `/Title` or `/Author`.** One line; out of
   scope for #366, which fixed the delivered PDF only (D-457).
7. **The ~83 self-referential `indeed.com` seeds** — a genuine WRITE-TIME defect in
   `lanes/indeed.py::tenant_seed_url` (D-454). It touches the armed Indeed lane, so it needs its own
   review.

### Owed, and specifically NOT done

- **`grnh.se` redirect-following is BUILT and SHIPPED (D-429), and deliberately NOT ARMED.**
  `boardwatch companies discover-grnh` emits candidates; `companies import` is the arming act. The
  board sample that made arming unreadable is gone, so the only thing holding it now is the owner's
  call on ~90 boards at ~5 min/run.
- **Per-source thresholds are not set** — the owner's, and the act that ends the retirement
  programme.
- **THE ABSTAIN REPORT CANNOT SEE AN EXTRACTION GAP, BY CONSTRUCTION — D-436, unfixed.** The keystone
  makes a rule that cannot resolve a profile FIELD visible; it says nothing about an extractor that
  cannot find the requirement in the TEXT. Reasoning whole in `STANDING-FACTS.md`. The honest fix is
  next-action item 3, not more patterns.
- **THE D-436 PATTERN FIXES CATCH *ZERO* OF THE 13 MEASURED FALSE POSITIVES (D-436).** The 13 have
  ~7 distinct root causes, so more patterns is whack-a-mole; D-443 and D-447 are the first two fixed
  at their actual layer.
- **The 382-body repair CLOSED the escaped-body residual in the STORE, and 129 superseded rows are
  still escaped ON PURPOSE.** Verified through a different path than the repair loop: **0 of 1,828**
  lane-sourced postings carry an escaped current version; history is preserved because the store is
  append-only (D-443's lane fix plus #365's writer).
- **Unescaping is NECESSARY, NOT SUFFICIENT, and a test pins the residual.** `3+ years of
  non-internship professional software development experience` writes zero rows even unescaped,
  because no catalog arm allows four modifiers between `of` and `experience`. D-447 widened the
  scoped run to four words; the residual class is wider than that one pattern.
- **The spelled-out and parenthesised halves are REFUSED on measurement (D-443).** Over the whole
  store `four (4) years` is **1,006 distinct sentences** dominated by DUI boilerplate and degree
  names, and spelled-out numerals include **`Up to three years…` — a CEILING a minimum-bar pattern
  would invert.** A class read as safe on a filtered sample was not safe on the population.
- **`classify_location` FAILS OPEN on unrecognised cities**, so Nottingham (UK) postings reached a
  US-only queue in the D-436 audit. Not fixed; the fail-open direction is deliberate (D-294) and
  narrowing it is a precision/recall decision, not a bug fix.
- **THE APPLY-LANE DROUGHT MARGIN HAS COLLAPSED AND NOTHING ALERTS ON IT YET.** A3 cut per-run apply
  arrivals from **40-77 to 3-15** (D-458), which is the intended behaviour and also removes almost
  all the headroom the D-384 detector was tuned against. It is silent as of 2026-09-03d; re-read
  its threshold before the next drought, not after.
- **No alert wiring for the seed leak.** `boardwatch seeds` is a command you must run. The
  finalize-block alert-ordering invariant makes wiring it a separate change with its own review.

## Owner-gated — do NOT start or decide unilaterally

**0-1. RETIRED / ANSWERED — held WHOLE in `STANDING-FACTS.md`.** Gate 1 is PER-SOURCE RECALL (D-421)
and only the per-source THRESHOLD is still owed; job-apps keeps running until it is met
(`RETIREMENT-PLAN.md`); Indeed's posture is decided (D-410, re-scoped by D-450). **Do not
re-litigate 80%, do not re-derive "most", do not re-probe Indeed.**

1. **SET PER-SOURCE THRESHOLDS.** Framing DECIDED: option D then C — decompose LinkedIn first
   (**done**, D-431/D-453), then bar on `lane-only` exposure rather than recall. The numeric level is
   the owner's, and **D-450 must be on the page when it is set.**
2. **TRACK 1 — the already-admissible LinkedIn boards.** Re-sized by D-453 from 382 postings to
   **113 on the gate-survivor basis, 13 on the carried basis**, over **108 boards** at 3.2 s each ≈
   **5.8 min/run forever**. Still his; the board-sample confound that held it is gone.
3. **Mit's two résumé content calls** — whether to send a document at all; the D-220 prose rewrites.
4. **P2 item 8 — the onboarding field-taxonomy gatherer. DEFERRED by Mit 2026-08-28.** The last
   multi-tenancy gap of its kind; D-054 forbids us authoring non-tech field content.
5. **`add-evidence` takes no bundle lock** (D-143) — raise before two authoring agents run against
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

## Phase status

**P0–P6 are all COMPLETE and their gates all MET, and none has moved in weeks — the full table
moved WHOLE into `STANDING-FACTS.md` on 2026-09-01e.** Read it there. Only these are not settled:

- **P2 item 8** (field-taxonomy gatherer) **NOT STARTED** — the last multi-tenancy gap, owner-gated.
- **P7 Breadth**: LinkedIn, GitHub-lists, jobapps, **`jsonld` and `indeed` are all built and ARMED**
  (D-420). Indeed's cap is **50 again** after one uncapped measurement run (D-459). **hiring.cafe is
  armed and WORKING**, and its 50-board sample is **reverted** (D-456) — watched boards 482 → 432,
  then 490 after run 149's Indeed convergences. Remaining tier-D lanes are **DECIDED AGAINST**, not
  deferred (D-451).
- **14-day acceptance: not started, HELD BY THE OWNER.** The provisional pass is **not being chased**
  (D-351 item 2: work comes first), and every `rules_hash` bump restarts its counter — #364 bumped
  it on 2026-09-03d.

## Live blockers and carried gaps

| Item | Detail | Owner |
|---|---|---|
| **boardwatch sees 16.4% of job-apps' eligible yield — RE-DERIVED 2026-08-30, and the METHOD was wrong before** | **45 of 275 (16.4%)**, cohorts 08-23..08-29, on the **379-board fleet**. This replaces "10.1%, owed a check". It decomposes: fleet growth 344->379 gave 10.1 -> **13.8%**; adding an **exact ATS-slug key** alongside name matching gave 13.8 -> **16.4%**. **Name-only matching undercounts, so 7.7% and 10.1% are FLOORS** — boardwatch stores Micron as `Micron TDIT`, so the old method scored a watched company as unwatched; same for HPE/`Hewlett Packard Enterprise`, Cox/`Cox Automotive`, Disney/`Walt Disney Company`, Toyota, VIAVI. **The unreached 230 split: aggregator-only 60.7%, unsupported employer host 21.1%, board-addable just 1.8%** (5 postings in 7 days, 4 of them SmartRecruiters — the class D-370 declined on measured cost), so the cheap remainder is ONE Workday board (Motorola Solutions). **The gap is lanes, not boards.** Script: `.agent/2026-08-30-session/reach_v2.py`. Amazon/TikTok/Apple/ByteDance use none of the 6 ATS, so a slug cannot reach them. Closing it means a new discovery lane — GitHub new-grad lists are 19.1% of yield for ~5 public-repo GETs and are NOT the ToS trap the v2 decision was written about. **Reopens D-008** | **Mit** (reverses a shipped decision) |
| **Citi sits at 13.1% coverage, permanently** | Workday's `total` censors at 2,000; the facet sum (uncapped, control-verified) says 4,589. Our pager wraps at ~2,000 too, so post-drain Citi holds ~2,214 of 4,589 and nothing reports it | **Mit** (input-side) |
| **The unattended 04:00 tick runs the PRIMARY checkout's branch — and it is PROVEN to fire** | The launchd job invokes the **editable** venv at `boardwatch/.venv/bin/boardwatch`, so whatever branch that tree is parked on IS the unattended run's code and `rules.yaml`. A stale `.git/index.lock` once silently blocked every `git pull` for a whole session — check the lock's MTIME and `pgrep -x git` before blaming contention. **Park the primary checkout on `main` before ending every session**; from ~2026-08-31 a stray branch changes EVERY subsequent run, not one. Closing it mechanically means pointing the plist at a worktree pinned to `main`, which moves a scheduled job and a venv | **Mit** (mechanism); every session (discipline) |
