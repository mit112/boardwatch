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

### Session 2026-09-05 (execution): the 04:00 tick was NOT waited for — **run 3 was launched by hand at 22:39 and is STILL IN FLIGHT**; T31 and T32 are gate-green but **NOTHING IS MERGED**, and T33 is REFUSED on inspection at 0.701% held

**Read this before acting on anything below it.** Reasoning: **D-471**. Numbers: `METRICS.md`, the
`Session — 2026-09-05` block. **Written for the planning session:
`docs/program/REPORT-2026-09-05.md`. The remaining list: `docs/program/HANDOFF-2026-09-05-POSTRUN.md`.**

**`main` IS UNTOUCHED AT `84671523`.** The primary checkout runs the editable venv, so a live run
must not have its code swapped underneath it. Branch **`close-2026-09-05`** carries, in order,
`1fc61596` (T31: `init` seeds the bundled `resume_template.tex` when absent, never overwrites),
`d406a9f6` (T32: the résumé shell joins `projection_content_digest` and the approval screen), and
the close commit. **ONE `--ff-only` merge lands all three.** Full gate on the T31+T32 state: **exit
0, 9,462 passed / 0 failed / 1 skipped / 4 xfailed.** Worktrees `../bw-t31`, `../bw-t32`,
`../bw-close` are left in place; delete after merging.

**⚠ T32 STALES THE PROJECTION APPROVAL — Mit chose this at 23:26 on 09-04 on the condition that he
re-approves before the next `--project` run.** Until he does, any `--project` run scans in full and
then refuses at the P5a preflight. `boardwatch profile-bundle approve-projection`, controlling TTY.

**RUN 3 was launched by hand**, not by launchd: `run --project --top 40` with
`BOARDWATCH_HEARTBEAT_URL` and `BOARDWATCH_ALERT_URL` **unset**, so the 04:00 tick still owns the
heartbeat signal. Warm scan **283 of 288 boards in 79.3 min against run 2's cold 178.6 min**, and
the corpus GREW 61,927 → 81,777 open as `detail_fetch_budget` absorbs the backlog run 2 left
(`boards_partial` 70). **R1, T28 and T34 are CARRIED** — the run had not finished when the session
was wrapped.

**T33 IS CLOSED, AND THE RULING IS "NO".** The class D-470 authorised holds **429/61,232 =
0.701%** — inside its 1% bar, both null controls pass, and the threshold arm passes — but **14 of
20 printed held bodies are real JDs**, reproduced at ~11 of 20 on a second seed over a 24% larger
corpus. `MIN_BODY_CHARS` is an English-length constant that condemns complete Chinese JDs; a line
floor fails the same way. **The survivor is `residual_chars == 0`: 118 bodies / 0.193%, 10 of 10
chrome — sized as M, not S, and it is the one open question this session produced** (§4 of the
post-run handoff).

**T36 LOOKS WEAKER THAN IT DID.** The warm scan is 2.25x faster at `scan_workers` unchanged, so
the corpus warming up may already have paid the lever. `board_scans` cannot model this at all
(127 s of rows against a 10,716 s stage); only `funnel.scan.fetch_cost` can, and it double-counts
same-host blocking, so every projection from it is an UPPER bound. smartrecruiters is 24.0% of run
2's fetch cost on ONE host over 10 boards.

### Session 2026-09-04f (planning review): the 2026-09-04e report HOLDS on every claim checked against the code; T30 is MERGED and the venv rebuilt on 3.13 — **green is now `make check` exit 0** (9,457 passed, 0 failed); the five open questions are ruled in D-470 and the next execution list is `HANDOFF-2026-09-05.md`

**Read this before acting on anything below it.** Reasoning: **D-470**. Numbers: `METRICS.md`, the
`Session — 2026-09-04f` block. The planning session read T22, SP2, T16, T13, T15, T6 and T30 line by
line against the code and found the report accurate on each. **One correction to the report's
framing:** the `--project` preflight sits AFTER the scan (`runner.py`, "P5a"), so an unapproved
tick scans for ~3 h, refuses, exits 1 and **never reaches eligibility — the owed corpus re-key does
NOT land on a refused tick.** **Mit re-approved at 21:08 on 09-04** — the stamp now carries
`content_digest`, so the 09-05 tick is expected to deliver and to pay the re-key.

**T30 LANDED `8f44a3d3`** (rebased onto `main` first; it was 7 commits behind). `uv sync --frozen`
rebuilt the primary venv on **CPython 3.13.15**; `boardwatch --help` runs, `tectonic` 0.17.0
resolves, the plist is unchanged. Full gate on `main` after that: **exit 0, 9,457 passed / 0
failed / 1 skipped / 4 xfailed, 655.9 s.** The "exit 2 with two known failures" convention is
RETIRED everywhere; any failure is a real one. `make check` runs via `uv run`, which honours
`.python-version`, so every worktree's first gate builds a 3.13 venv.

**RULED (D-470):** T18 `data`/`ai` — NO, closed. T26 chrome-only — rebuild as a BOARD-SCOPED
boilerplate detector, measured first (T33). M1 and T28 — re-run after the first delivery under
`1+d89b423701e5`; M1 takes one gate pass (T34). **SP3 (+T23) — DEFERRED on measurement, not
refused**: run 2's tailor stage was 162 s (4.06 s/lead, 1.35% of a cold run), but the per-lead
cost is a 4-64 s range set by the slate, so the prize is 2-30 min/run; the first three warm ticks
decide it. The LLM gate's cadence waits on M1. **The real run-time lever is `scan_workers`, still
8 in Mit's `config.toml` against a ceiling of 32** — T36, only after the first warm scan is read.

## Next action

**0. THE NEXT THREE THINGS, IN THIS ORDER — `docs/program/HANDOFF-2026-09-05-POSTRUN.md` §1.**
(a) **Wait for run 3**: `pgrep -fl "boardwatch run"` must find nothing. Do not merge, do not switch
`main`'s branch, do not touch `{config_dir}` until it does. (b) **R1 — read run 3**:
`.venv/bin/python .agent/2026-09-05-session/r1_readout.py 3` prints the run row, all eight
`stage_durations` against run 2's pinned baseline, each lane's own scalars (SP2's
`stage_elapsed_seconds` vs the residual `lanes` join wait), and the verdict distribution at BOTH
engine keys with the per-posting move count. **It carries its own null control: run against run 2
it reproduces the pinned baseline exactly.** (c) **`git merge --ff-only close-2026-09-05`**, then
**Mit re-approves the projection** — T32 stales it and he chose that at 23:26 on 09-04 on exactly
that condition.

**0-1. CARRIED, ALL THREE BLOCKED ON RUN 3 FINISHING:** R1, **T28** (the probe unchanged, null
control first: it must find the funnel's own delivered count before grouping) and **T34** (M1 —
`gate request` → two blind judges → `gate apply` → the m1 probe; the judging pass is the cost, and
the **planning session** rules on the cadence). **T36 is re-opened, not carried**: the warm scan is
2.25x faster at `scan_workers` unchanged, so re-decide it on run 3's own numbers. **T35** is still
gated on reaching 09-09.

**0-2. NOT STARTED, BY RULING:** SP3 (+T23) is deferred on measurement (D-470) until three warm
ticks have reported the tailor stage; T18's `data`/`ai` and T24 are closed. **T33 is closed NO**
(D-471); its survivor `residual_chars == 0` is an open question for the planning session, not work.

**0-3. STILL OWED AND UNTOUCHED — MIT'S:** **push `main`** — but only AFTER the merge above;
`main` has not moved this session, so there is nothing new to push before it (SSH to `origin`
works: `git push origin main`). Review and import
`.agent/2026-09-04c-session/discover-candidates.yaml` (80 GitHub-list boards, D-291 human step);
the formatting session (per-lens skills, the SAKEC/Nakshatra order, the `projection.{sde,ios}.yaml`
drafts — **do it in the same sitting as T32's re-approval, since both re-stale the stamp**);
StreakSync `main`.

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
  and no `--project`; the daily driver is **`run --project --top 40`** — CORRECTED 2026-09-04d from
  `--top 100`, which this file and memory both carried; `plutil -p` on the live plist says 40. Run 151 was killed ~17 min
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
5. **NEW 2026-09-04d — whether a fresh install should be handed a `resume_template.tex` to edit.**
   T2 made the renderer fail CLOSED when `{config_dir}/resume_template.tex` is absent, which is the
   right direction: the bundled fallback's header is literally "Your Name / Example University", and
   the 09-03 reset deleted exactly that file. But **nothing in the product writes it** — neither
   `boardwatch init` nor `tailor init` — so a new user is now refused until they author one from
   scratch. The alternative is for `init` to write the bundled template into the config dir, where
   the new placeholder-phrase catalog would then refuse it until edited: same fail-closed guarantee,
   an actionable file instead of an absent one. **Multi-tenancy question, so it is Mit's**, and it
   is a new onboarding step either way.

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
| **The unattended 04:00 tick FIRED ONCE on this machine (06:00 local 2026-09-04, run 1: failed closed by design) and the first CLEAN run (2) was MANUAL; the first warm unattended tick is 2026-09-05 04:00** — the mechanism note is still true| The launchd job invokes the **editable** venv at `boardwatch/.venv/bin/boardwatch`, so whatever branch that tree is parked on IS the unattended run's code and `rules.yaml`. A stale `.git/index.lock` once silently blocked every `git pull` for a whole session — check the lock's MTIME and `pgrep -x git` before blaming contention. **Park the primary checkout on `main` before ending every session**; a stray branch changes EVERY subsequent run, not one. Closing it mechanically means pointing the plist at a worktree pinned to `main`, which moves a scheduled job and a venv. The plist was path-fixed from the pre-reset account home to the current one (`~`) | **Mit** (mechanism); every session (discipline) |
