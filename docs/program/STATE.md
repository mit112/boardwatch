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

### Session 2026-09-04b: the RUNTIME IS RESTORED and the CAREER-PROFILE BUNDLE IS REBUILT — revision 1 of a new lineage, owner-approved and promoted, projection re-stamped; the store is still EMPTY and nothing has run since run 152

**Read this before acting on anything below it.** Reasoning: **D-464** (what the reset destroyed)
and **D-465** (what this session rebuilt, and the owner's content rulings). Numbers: `METRICS.md`,
the `Session — 2026-09-04` and `Session — 2026-09-04b` blocks. No code changed, no PR, no run.

**THE PIPELINE HAS NOT RUN SINCE RUN 152 (2026-09-03).** `{config_dir}` exists again and holds
`config.toml`, `resume_template.tex`, `projection.yaml` and a regenerated `resume.yaml`, and
**`com.boardwatch.run` is loaded and will fire at 04:00** — but the store is empty, so the first
tick is a cold full scan. Every number in the blocks below was measured against a store that is
gone; they remain true as history and must not be re-read as live state.

**THE BUNDLE IS BACK, AND IT IS A NEW LINEAGE.** `career-profile/` revision 1 (bundle `4c8a7e65…`):
16 entities (person, 2 education, 4 employment, **9 projects — Anghkooey and Gamified Learning are
new**), 118 facts, 5 evidence records, 0 errors / 0 blockers at the completeness tier; the owner's
TTY `approve`/`promote`/`approve-projection` all ran 2026-09-04 ~06:04. Every résumé now pins **4
experience entries** (Nakshatra joins Saayam, NIO, SAKEC) and the static summary is **gone** from
the personal template — measured: 4+4 fits one page only without it. The single content source is
`.agent/2026-09-04-resume-profile-session/content.py` (gitignored, personal); `build_bundle.py`
there rebuilds the bundle from it end to end. **Do not re-derive the content rulings — D-465 lists
them.**

**WHAT SURVIVED THE RESET** (unchanged from the morning session): git history and working tree, all
docs, tests, tooling and the whole toolchain. **The global CLAUDE.md's "fresh machine, assume
nothing installed" ritual is STALE for this repo — do not re-run it.** The wiki is back on live disk
at `~/dev/portfolio-website/` (71 files, byte-identical to the backup); `~/dev/hookrail` is
re-cloned; `~/cosmos` stays gone and is not needed (D-220 stands).

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

**0. WATCH THE FIRST POST-RESET RUN, THEN THE FORMATTING SESSION.** The 04:00 tick is the first
run against an empty store: expect a long cold scan and `--project` rendering against bundle
revision 1 for the first time. Read `~/Library/Logs/boardwatch-run.log`, confirm the heartbeat
pinged, and compare a delivered `tailored-*.pdf` against `~/Desktop/boardwatch-preview-2026-09-04/`.
Then the owner's next résumé session is **formatting**: per-lens skills (the iOS list is in
`content.py`), the dormant `projection.{sde,ios,data}.yaml` coverage declarations (lost in the
reset, not yet re-authored), and how a JD picks its project set. **StreakSync's evidence is pinned
to `overnight-2026-08-31` — merge it to `main`.**

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
| **The unattended 04:00 tick is LOADED AGAIN (2026-09-04b) but has NOT YET FIRED on this machine** — the mechanism note is pre-reset history and still true of the mechanism | The launchd job invokes the **editable** venv at `boardwatch/.venv/bin/boardwatch`, so whatever branch that tree is parked on IS the unattended run's code and `rules.yaml`. A stale `.git/index.lock` once silently blocked every `git pull` for a whole session — check the lock's MTIME and `pgrep -x git` before blaming contention. **Park the primary checkout on `main` before ending every session**; a stray branch changes EVERY subsequent run, not one. Closing it mechanically means pointing the plist at a worktree pinned to `main`, which moves a scheduled job and a venv. The plist was path-fixed from the pre-reset account home to the current one (`~`) | **Mit** (mechanism); every session (discipline) |
