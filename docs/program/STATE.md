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

### Session 2026-09-04c: RUN 2, the first post-reset run, is CLEAN — the profile row and the board fleet turned out to be lost too, both are RECOVERED and RE-SEEDED, 288 boards scanned cold, 40 of 40 leads rendered one page against bundle revision 1, and a whole-tree ARCHITECTURE REVIEW records 26 findings for the next session

**Read this before acting on anything below it.** Reasoning: **D-466** (recovery + run 2) and
**D-467** (the review). Numbers: `METRICS.md`, the `Session — 2026-09-04c` block. Findings:
**`docs/program/REVIEW-2026-09-04.md`**. No code changed, no PR.

**THE PIPELINE IS RUNNING AGAIN.** The 06:00 tick (run 1) failed closed on the projection stamp AND
reported **0 watched boards** — D-464 missed that the singleton `profile` row and the `companies`
fleet live only in the store. Both were recovered from Bash tool-results in the transcript archive
and re-seeded through the CLI's own functions: the profile row whole (14 target / 22 exclude titles,
Houston/Remote/US, band `entry`, facts, six-family `blocker` policy, 52 skills from the rebuilt
text) and a **288-board fleet** (301 offered from the union of every surviving list, 13 skipped by
`--verify`). Lane rows were deliberately not restored; run 2's lanes re-discovered **265**. About 60
one-off `companies add` boards are unrecoverable. **Run 2** (manual, daily-driver flags, heartbeat
env unset, 06:32-09:52): `ok`, RECONCILES, **40 tailored / 40 PDFs / all one page**, header text
identical to the approved Desktop preview; 61,927 evaluated; scan **178.6 min = 89.2%** of 3 h 20
min; **74,596 Workday details still deferred**, so the 04:00 ticks stay scan-dominated. The store
holds one full corpus and `~/boardwatch-applications/2026-09-04/` the delivered slate.

**THE BUNDLE (revision 1, D-465) IS NOW EXERCISED END TO END.** 4 experience + 4 projects, no summary,
eight distinct project quartets across the 40 leads. One layout item for the formatting session:
experience follows declaration order, so SAKEC (Feb-Apr 2021) prints above Nakshatra (Mar 2021-Feb
2022); reordering `projection.yaml` re-stales the stamp. Everything from 2026-09-04b stands: the
runtime files in `{config_dir}`, the wiki at `~/dev/portfolio-website/`, the loaded `com.boardwatch.run`
job. **The global CLAUDE.md's "fresh machine" ritual is STALE for this repo — do not re-run it.**

### Session 2026-09-03e: the owed LEDGER DRAIN is REFUSED on measurement, the LLM FINAL GATE is ARMED for the first time and filters 38 of 95 delivered leads, and the armed drought alarm turns out to false-fire on 40 of 136 historical windows

Reasoning: **D-460** (the drain), **D-461** (the gate + the owner's years ruling), **D-462** (the
drought alarm), **D-463** (the aggregator refusal + the hiring.cafe ceiling correction). Numbers:
`METRICS.md`, the `Session — 2026-09-03e` block. Shipped: **#369, #370, #371, #372**.

**THE DRAIN D-455 LEFT OWED IS CLOSED BY REFUSAL, NOT BY DEFERRAL, AND THE OWNER RULED IT.** The
re-key ran first and is the half that paid — **151,626 postings re-evaluated** under
`1+bf844e01ebcb` (run 150). The drain itself relieves no scarcity: **83,168 open postings already
flow unsuppressed against 1,489 the ledger withholds (~56x)**, the ledger is **100% `built` / zero
`skipped`** so it can only re-deliver, and D-455's own win never needed it (those 996 postings were
never built and carry no disposition row). **The inherited "they rank low anyway" premise was FALSE
for this population** — p50 age **2 days**, so **1.41 score-points** lost, not the 9.7 the
2026-08-27 reading assumed. Stale stamps fail nothing; the drain stays available on his word.

**THE FINAL GATE IS ARMED AND HAS ROWS FOR THE FIRST TIME (0 → 95).** D-436's own architectural
answer, chosen by the owner over the deterministic topic net. **43 eligible / 38 ineligible / 14
uncertain**, 48 quoted spans, store-verified. **The owner ruled "a stated bar is a bar"** on the 28
`experience_years` verdicts — **and that ruling is bounded to the GATE, not to
`near_miss_years_ceiling`** (D-461, and see Owner-gated below).

## Next action

**0. THE NEXT SESSION WORKS `docs/program/TICKETS-2026-09-04.md` IN ORDER — the orchestrator drives cheaper
agents one ticket at a time (owner's ruling, D-467); the top four first, each in a worktree with its own commit:** (1) the pysqlite `begin` hook in `store/db.py` — then retire the two
hand `BEGIN IMMEDIATE`s; (2) the résumé renderer's silent fallback to the bundled placeholder
template (`tailor/render/latex.py:93-107`) — fail closed; (3) `rules.yaml` `experience_years`: "no
less than N years" and "N months" both evaluate `eligible` today; (4) an override for the delivery
queue root on `run` (`delivery/queue.py:90`). Then the rest of `REVIEW-2026-09-04.md`'s confirmed
list. **Behind them, the three run-speed items** (memory `run-speed-queue-workers-lanes-overlap-parallel-tailor`):
`scan_workers` ceiling > 8 (local config value, never the code default), lanes overlapped with the
scan, parallel tailoring. **Also owed:** the formatting session (per-lens skills, the SAKEC/Nakshatra
order, `.agent/2026-09-04c-session/projection.{sde,ios}.yaml` drafts, how a JD picks its projects);
review and import `.agent/2026-09-04c-session/discover-candidates.yaml` (80 GitHub-list boards, D-291
human step); push `main` (`gh` still not installed) and StreakSync `main` (fast-forwarded locally to
`6377723`, 6 ahead of origin). **Read the 04:00 tick of 2026-09-05 first** — the first WARM
unattended run on the rebuilt store: `~/Library/Logs/boardwatch-run.log`, heartbeat pinged.

**1. THE YEARS RULING'S PROPAGATION IS OWNER-GATED AND MUST NOT BE ASSUMED.** He ruled on **28
verdicts on the delivered shortlist**. `near_miss_years_ceiling` abstains on that same 2-3 year band
across **~78,615 open `uncertain` postings**. Different blast radius, different question, still his.
D-449 governs: a ruling is only as wide as the question put.

**2. RE-READ THE GATE ON THE NEXT RUN, AND DECIDE WHETHER IT BECOMES ROUTINE.** The gate now filters
38 postings from future shortlists. It is a **manual handshake** — `gate request` → judge →
`gate apply` — and nothing schedules it. Whether it runs every day, and who judges, is undecided.
**Its cost is the judging pass, not the CLI.**

**3. THE DROUGHT ALARM'S LOW-VOLUME COVERAGE IS STILL PARTIAL.** #371 fixed the false-alarm
direction and made the window grow to its population. What remains: the per-run `placeable == 0`
abstain still silences **63 of 136 windows**, deliberately, because it is also the anti-double-report
guard. Recovering those is a **detector-separation** question and was not folded in.

**4. FOUR DELIVERY DEFECTS FOUND BY THE GATE JUDGES, NONE FIXED.** One lead's `jd_text` is **98 KB of
Eightfold page-config JSON**; one is **entirely site chrome**; one says **"INDEED INTERNAL TEST JOB …
NOT A REAL JOB"**; and one 95-lead shortlist carried **SpaceX ×3 identical plus NetJets, USAA, Wipro
and Applied Materials pairs**. The last corroborates the standing 14-18% duplicate rate from a new
direction.

**5. THE TIER-AWARE INDEED CAP IS DESIGNED AND UNBUILT** (D-459 deferred it; the design is settled).
The tier IS known before admission at zero extra requests — `CompanyAdmission` already carries the
provider — so it is buildable as specified. **Two numbers are the owner's**: the tier-1 rate, and
whether a per-run RATE is the right instrument at all, since the cost is `watched_boards × 9.33 s ×
every future run` and any positive rate grows the fleet without bound. A fleet-size ceiling is the
alternative that actually bounds it.

**6. RE-MEASURE GATE 1 AROUND 2026-09-09** (D-424) with
`.agent/2026-09-02-session/per_source_recall.py`. Standing at **28.8%** (5,838/20,289), lane-only
7,984, absent 7,508.

### Owed, and specifically NOT done

- **`near_miss_years_ceiling` itself is untouched.** See item 1.
- **D-436's per-family topic net is SIZED and NOT BUILT.** Sizing is in D-461: the all-family form
  takes `eligible` to **0**, and the `work_auth` form is worth **245 of 4,617 (5.3%)** — about a
  quarter of the measured defect. **Do not re-derive it, and do not quote the naive 29.9%**, which is
  EEO boilerplate contamination.
- **The hiring.cafe +6.19pp / 1,331-posting ceiling is RETIRED as a fossil (D-463).** Its null
  control rests on an endpoint PR #304 deleted on 2026-09-01, two days before D-451 was written.
  Real value ~**+0.6pp**. **Do not re-size other work off the 1,331.** The lane's dominant problem is
  **availability** — 2 total refusals and 2 near-total in the last 7 armed runs.
- **The refused-aggregator filter is REFUSED (D-463)**, not deferred. Its premise inverts on the
  actual variable. Do not re-raise it from the 24.7%/13.4% figures, which are the wrong comparison.
- **A run was launched with the wrong flags this session.** `boardwatch run` defaults to `--top 10`
  and no `--project`; the daily driver is **`run --project --top 100`**. Run 151 was killed ~17 min
  in and relaunched as 152. **Never set `BOARDWATCH_HEARTBEAT_URL` on a manual run** — it would ping
  the production healthcheck and mask a real 04:00 failure.

## Owner-gated — do NOT start or decide unilaterally

**0. WHETHER THE YEARS RULING PROPAGATES BEYOND THE GATE.** He ruled **"a stated bar is a bar"**
on **28 final-gate verdicts over the delivered shortlist** (D-461). `near_miss_years_ceiling` in the
DETERMINISTIC engine abstains on the same 2-3 year band across **~78,615 open `uncertain` postings**.
**Do not move it on the strength of the gate ruling** — different population, different blast radius,
and lowering the ceiling REJECTS rather than releases (D-440).

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
3. **Mit's résumé calls** — whether to send a document at all; the D-220 prose rewrite of the submitted "sole iOS developer" answer (outside the bundle); the per-lens formatting session.
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
| **`make check` is RED on `main` for TWO ENVIRONMENTAL tests, and the cause is an UNPINNED INTERPRETER (found 2026-09-04)** | Both fail at pristine `979ddcdf` with no working-tree changes, so this is not a code regression: `tests/unit/test_ground.py::test_fail_closed_on_deeply_nested_json` (its own precondition `pytest.raises(RecursionError)` on 20,000-deep JSON **DID NOT RAISE** — CPython 3.14 no longer recurses there, so the test can no longer prove the guard rather than the guard being broken) and `tests/profile_bundle/test_profile_bundle_cli_exit_codes.py::test_an_unreadable_drafts_directory_could_not_complete` (`chmod 0o000` no longer yields `PermissionError`/exit 3 on this macOS; the probe reports `draft_not_found`/exit 1). **The venv is now Python 3.14.7 because `pyproject.toml` says only `requires-python = ">=3.11"` and there is no `.python-version`, so the post-reset rebuild silently moved the interpreter forward** — the pre-reset venv was 3.12/3.13 (evidenced by the rehydrated transcripts: 872 `.venv/lib/python3.12` and 499 `python3.13` references against 31 for 3.14). **9,394 tests pass; only these two fail.** Every other gate target is green (`generalization`, `index-check`, `ruff`, `mypy --strict` 351 files, `web-test`). The fix is a choice — pin the interpreter, or rewrite both tests to assert the behaviour without depending on the old environment — and it is not obviously the former | **Mit** (chooses pin vs. rewrite) |
| **Citi sits at 13.1% coverage, permanently** | Workday's `total` censors at 2,000; the facet sum (uncapped, control-verified) says 4,589. Our pager wraps at ~2,000 too, so post-drain Citi holds ~2,214 of 4,589 and nothing reports it | **Mit** (input-side) |
| **The unattended 04:00 tick FIRED ONCE on this machine (06:00 local 2026-09-04, run 1: failed closed by design) and the first CLEAN run (2) was MANUAL; the first warm unattended tick is 2026-09-05 04:00** — the mechanism note is still true| The launchd job invokes the **editable** venv at `boardwatch/.venv/bin/boardwatch`, so whatever branch that tree is parked on IS the unattended run's code and `rules.yaml`. A stale `.git/index.lock` once silently blocked every `git pull` for a whole session — check the lock's MTIME and `pgrep -x git` before blaming contention. **Park the primary checkout on `main` before ending every session**; a stray branch changes EVERY subsequent run, not one. Closing it mechanically means pointing the plist at a worktree pinned to `main`, which moves a scheduled job and a venv. The plist was path-fixed from the pre-reset account home to the current one (`~`) | **Mit** (mechanism); every session (discipline) |
