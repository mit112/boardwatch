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

### Session 2026-09-04f (planning review): the 2026-09-04e report HOLDS on every claim checked against the code; T30 is MERGED and the venv rebuilt on 3.13 — **green is now `make check` exit 0** (9,457 passed, 0 failed); the five open questions are ruled in D-470 and the next execution list is `HANDOFF-2026-09-05.md`

**Read this before acting on anything below it.** Reasoning: **D-470**. Numbers: `METRICS.md`, the
`Session — 2026-09-04f` block. The planning session read T22, SP2, T16, T13, T15, T6 and T30 line by
line against the code and found the report accurate on each. **One correction to the report's
framing:** the `--project` preflight sits AFTER the scan (`runner.py`, "P5a"), so an unapproved
tick scans for ~3 h, refuses, exits 1 and **never reaches eligibility — the owed corpus re-key does
NOT land on a refused tick.** As of 20:55 on 09-04 the stamp still carries no `content_digest`.

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

### Session 2026-09-04e: the WHOLE 2026-09-04 ticket list is EXECUTED from a written handoff — 19 tickets merged, one worktree and one gate each, every gate exit 2 with exactly the two known environmental failures; THREE of the planning session's rulings were overturned on measurement, and FOUR tickets are blocked because the population they were written against died with the reset

**Read this before acting on anything below it.** Reasoning: **D-469**. Numbers: `METRICS.md`, the
`Session — 2026-09-04e` block. **Written for the planning session:
`docs/program/REPORT-2026-09-04e.md`** — it carries the ticket table, every place the spec was wrong,
and what is left.

**⚠ THE 2026-09-05 04:00 TICK WILL DELIVER NOTHING UNTIL MIT RE-APPROVES THE PROJECTION.** T22 gates
the approval on a digest of the resolved content, and a stamp without it fails CLOSED — the ruled
upgrade path. **Verified by reading the file**: the one live stamp
(`projection-approvals/sha256-3a292ad2…ce0ba.yaml`) carries no `content_digest`, so the `--project`
preflight refuses. Approval needs a controlling TTY, so it is his and cannot be done from a session:
`boardwatch profile-bundle approve-projection`, review the screen (it now prints every bullet AND
the resolved skills section), type `approve`.

**SHIPPED (local commits, unpushed — `gh` is still not installed):** T20 `a4f6c4de`, T7 `d8201f59`,
T6 `66d7c81d`, T8 `04211e1e`, T10 `e1dfa73c`, T9 `ab73046c`, T11 `891c030f`, T12 `5c29bd73`,
T13 `a90e993e`, T22 `81cfa093`, T27 `25e32dce`, T18 `78a43eec`, SP1 `49558a9d`, T25 `d9544125`,
T19 `db0c9b91`, T21 `ae64c0ee`, T16 `3abd92f8`, T26 `21c38b57`, T15 `4cb3679c`, T14 `43c7f1c6`,
T7b `e803c6a1`, SP2 `d22db2a2`, T17 `dd2db832` — **23 tickets**. One line each is in
`CHANGELOG.md` for the first 19; SP2 and T17 landed after that entry and are described in
`REPORT-2026-09-04e.md`.

**SP2 CHANGES THE UNATTENDED RUN'S SHAPE and lands the night before a tick**: the lanes now run on
one daemon thread overlapping the board scan. It is contract-bound never to fail the run, 2,327
pipeline tests pass and `test_two_writer_concurrency` ran 11/11 — but the first unattended exercise
of it is the 2026-09-05 04:00 tick. **Read `stage_durations` on that run**: `lanes` becomes the
residual join wait and the lane's own elapsed moves onto `LaneReport`. The stated prize is 6-13 min.

**THREE RULINGS WERE OVERTURNED, EACH ON A MEASUREMENT THE RULING DID NOT HAVE.** (1) **T16's ruled
`metadata.create_all` emits 0 of the schema's 20 triggers** — the ten append-only `RAISE(ABORT)`
pairs the keystone rests on among them — and `compare_metadata` cannot see triggers, so the ruling's
own safety argument was false. A DDL-template replay of the real chain ships instead: **92.9 ms →
2.9 ms (32x)**, schema identical. (2) **T18 ships 4 of its 6 words**: over 47,295 open titles the
four move 166 titles, while `data` adds 321 and `ai` 187, both dominated by business roles, and
`data` un-vetoes a title the repo's own suite pins as `not_swe`. (3) **T26 ships 1 of its 2 classes**:
chrome-only holds **4.81%** of open bodies against its own ~1% stop condition, on real JDs condemned
for non-English or off-catalog headings.

**THE PRE-RESET STORE IS GONE AND IT BLOCKED FOUR TICKETS.** `eligibility_evaluations` holds only
`('deterministic','1+bf844e01ebcb', 61927)` — **no final-gate rows at all**. M1's required null
control returned **0/0/0** against D-461's 43/38/14; T28 found **0 duplicate groups in 40 delivered
leads** against a 14-18% headline, so no identity change was taken; T27's markers hold 0; T26(b) has
no Eightfold body to fix against. **D-461's 43/38/14 describe a store that no longer exists — do not
re-quote them as live.**

**THE DELIVERED QUEUE CURRENTLY READS 0 APPLY / 40 REVIEW**, every lead `verdict=None`, because the
stored corpus is at `engine_version 1+bf844e01ebcb` while `current_identity` computes
`1+d89b423701e5`. That is the one-off re-evaluation the tick owes (T3+T4, now also T20), not a
defect; confirmed identical against pre-T20 code. The live profile row strict-validates.

**A READ-ONLY REVIEW OF THE SESSION'S OWN 19 COMMITS FOUND TWO REAL DEFECTS, BOTH FROM T7** — fixed
in-session as T7b. `GET /api/answers` crashed uncaught and DROPPED the connection (the web dispatcher
catches three types and `ProfileRowInvalid` is none of them); `top`/`export`/`eligibility run`/`stats`
tracebacked instead of naming the column. Every gate had been green.

### Session 2026-09-04d: the owner-ruled TOP FOUR from the architecture review SHIP, plus T5 — five tickets, five worktrees, five gates, all merged to a local `main`; both eligibility changes were A/B'd over the live corpus first, and one of them turns out to move NOTHING

**Read this before acting on anything below it.** Reasoning: **D-468**. Numbers: `METRICS.md`, the
`Session — 2026-09-04d` block. **Written for a fresh reviewer: `docs/program/HANDOFF-REVIEW-2026-09-04d.md`.**

**SHIPPED (local commits, unpushed — `gh` is still not installed):** T1 `db6807da` the pysqlite
`begin` hook at the ENGINE, retiring the two hand `BEGIN IMMEDIATE`s; T3 `e88da1fd`
`(no|not) (less|fewer) than` as a cue idiom; T5 `b63b3ee9` `run --queue-root` plus a refusal when
`BOARDWATCH_DATA_DIR` alone moves the store; T4 `8c2b3ef2` bars stated in MONTHS; T2 `35ef0da1` the
résumé renderer failing CLOSED without `{config_dir}/resume_template.tex`. Every gate was **exit 2
with exactly the two known environmental failures** and was read from its own exit-code sentinel.

**THE TICKETS WERE WRONG IN THREE PLACES AND THE CORRECTIONS ARE MEASURED.** (1) **Review finding 3
does not reproduce** — "no less than 5 years" evaluates `uncertain` with ZERO rows, not `eligible`.
(2) **Review finding 6's direction is inverted for the policy half**: a corrupt FACTS row abstains,
but a corrupt POLICY row yields the CATALOG DEFAULTS, where only `work_auth` is `blocker` and the
other five families drop to `preference` — which can never yield `ineligible`. **T7 is a CLEARING
failure, not a conservative one, and is under-sized in the ticket list.** (3) **T4's stated
acceptance is impossible**: 18 months is 1.5 years, inside `near_miss_years_ceiling: 3`, so a months
bar under 36 months can only ever be `met` or `unknown`. Only 48 months (4 occurrences corpus-wide)
can reject.

**T3 CHANGES NO POSTING'S VERDICT TODAY, and that is the honest price of its re-key.** The idiom
occurs in **58 of 61,927** open bodies and never in front of a years bar; an A/B over exactly those
58 moved **0 verdicts and 0 rows**. **T4 does move**: over 3,668 pinned postings, 916 gain a row and
**29 verdicts move** (26 `uncertain`→`eligible`). Both change `rules_hash`, so **the next tick
re-evaluates the corpus once** — one re-key, not two, because both landed before it.

**THE OWED DRAIN IS ANSWERED, MEASURED, AND OWES NOTHING.** `engine_version` moved
`1+bf844e01ebcb` → **`1+d89b423701e5`**, which stales every permanent ledger stamp, and T4 moves
verdicts in the LOOSENING direction (26 `uncertain`→`eligible`) — so the D-319 test does apply here
rather than being waived by argument. It is answered by counting: the ledger holds **40 rows, all
`built`, all from run 2, none reopened, zero `skipped`.** Nothing is suppressed, so no loosening can
release anything and a drain could only re-deliver the same 40 leads. D-460's refusal stands, now on
a starker number than the one it was written against.

**THE NEXT 04:00 TICK IS THE FIRST UNATTENDED RUN OF ALL OF THIS.** It runs new transaction
behaviour, a re-keyed catalog, a new run refusal and a fail-closed renderer, on the rebuilt store.
`{config_dir}/resume_template.tex` must exist or **every lead is refused by design** — verify it
before the tick if there is any doubt.

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

## Next action

**0. RE-APPROVE THE PROJECTION — MIT, IN A REAL TERMINAL, BEFORE ANY RUN DELIVERS AGAIN.**
`boardwatch profile-bundle approve-projection`. T22 gates on a content digest and the one live stamp
predates it, so the `--project` preflight refuses and the run delivers nothing. Verified by reading
the stamp file. Needs a controlling TTY; no session can do it.

**0-1. THE EXECUTION SESSION RUNS `docs/program/HANDOFF-2026-09-05.md`**, in its order: R1 (the
09-05 tick readout, including `stage_durations` and each `LaneReport.stage_elapsed_seconds`) →
T28 → T33 → T34 → T31 → T32 → T36 → T35. **If the tick refused on the stamp, the readout covers
the scan and lane stages only and the re-key is still owed** — the next `--project` run after
approval pays it, and that run is Mit's to launch. Until then the delivered queue reads **0 apply
/ 40 review** with every lead `verdict=None`.

**0-2. NOT STARTED, BY RULING:** SP3 (+T23) is deferred on measurement (D-470) until three warm
ticks have reported the tailor stage; T18's `data`/`ai` and T24 are closed.

**0-3. STILL OWED AND UNTOUCHED — MIT'S:** **push `main`** (36 commits ahead of `origin`, the
whole post-reset rebuild on one machine; SSH to `origin` works: `git push origin main`); review
and import `.agent/2026-09-04c-session/discover-candidates.yaml` (80 GitHub-list boards, D-291
human step); the formatting session (per-lens skills, the SAKEC/Nakshatra order, the
`projection.{sde,ios}.yaml` drafts — do it in the same sitting as T32's re-approval, since both
re-stale the stamp); StreakSync `main`.

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
