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

### Session 2026-09-06 (execution): T37, T38 and T39 SHIP — and T37's diagnosis was WRONG: the lost board is a WAL snapshot-upgrade conflict, not a `busy_timeout` starvation, so the prescribed fallback could never have worked; T28 is CLOSED on a positive control; dominos is UNWATCHED; `main` is still UNMOVED by Mit's ruling

**Read this before acting on anything below it.** Reasoning: **D-473**. Numbers: `METRICS.md`,
the `Session — 2026-09-06` block. Report: `REPORT-2026-09-06.md`. **`main` is still `84671523`.**
`close-2026-09-06` now carries SEVEN commits over it (T31, T32, the two 09-05 closes, then T37,
T39, T38 and this close) and **one `--ff-only` merge still lands them all**.

**MIT RULED TWICE AT THE TOP OF THE SESSION.** (a) **Do not merge** — `main` stays parked on the
T30 state so the 04:00 tick delivers with a valid projection stamp and pays SP3 its second warm
tailor measurement. The merge is still one step with the re-approval, in his sitting; §0 below is
unchanged. (b) **Drop dominos only** of the four smartrecruiters boards: `companies remove
smartrecruiters:dominos` is an UNWATCH, verified before and after — **288 → 287 watched**, its 800
open postings still held and now in the death-probe population (D-314), not in silence.

**T37 — THE HANDOFF'S MECHANISM WAS WRONG AND ITS FALLBACK IS IMPOSSIBLE.** D-472 read the lost
`FidelityCareers` apply as starvation past `busy_timeout` 5 s. **Starvation does not reproduce**:
a back-to-back stream of short transactions on one thread let a 200 / 2,000 / 20,000-insert writer
on another in after **0.003 / 0.039 / 0.160 s**. The real fault is a **WAL snapshot upgrade** —
`apply_board` opens a DEFERRED transaction and READS before it writes, so **ONE** commit from any
other connection in that gap fails the write with `SQLITE_BUSY_SNAPSHOT` (517), rendered as
`database is locked`, in **0.0006 s against a 5,000 ms timeout**. The busy handler is never
invoked, so **no value of `busy_timeout` changes the outcome** — pinned as a test on ELAPSED TIME
so it is not re-proposed. Fixed by the split the handoff preferred: the lane thread FETCHES only,
the join site applies. **Chosen consequence:** a run returning before the join lands NO lane rows
(pre-SP2 behaviour) — a shipped test asserted the opposite and was rewritten.

**T38 — THE READY QUEUE, because the static fix is a REGRESSION.** `host_diverse` is gone,
replaced by `host_queues` + `take_ready` and a `wait(FIRST_COMPLETED)` dispatch loop bounded at
`scan_workers`. Sized on the model D-344 was fitted to, recalibrated against run 3: today 95.0 min,
**static chain-first 105.5 (worse than doing nothing)**, ready queue **83.8**. Null control, both
arms on ONE fleet (287 boards, 131 hosts): the smartrecruiters chain moves from positions
3, 134, 147, 153… to **3, 11, 19, 27…** — the gap is now exactly `scan_workers` — with **0 of 131
hosts' own board order changed**. **This supersedes D-344's "not built (the model already prices
the loss)".** T36 is re-decided on the next tick's tail, not before.

**T39** — `scan.empty_complete_guarded` in the funnel and one run-log line; `ARTIFACT_VERSION`
deliberately not bumped (additive key, `fetch_cost` precedent).

**T28 — CLOSED, and the zero is STRUCTURAL.** The probe reaches the funnel's 40 for each run and
still finds 0 duplicate groups at every scope. The control that establishes it is a POSITIVE one:
the identical grouping over the 83,308 open postings finds **7,093 groups**. The cause is in run 3's
own funnel — the shortlist drops **46 `hidden_duplicate` + 5 `hidden_slate_cap`** and holds run 2's
40 as `hidden_handled` before the slate is cut, over a corpus-wide `dedup` that already suppressed
**1,498 / 83,308 (1.80%)**. The delivered set is the one population where this is zero by
construction; the 14-18% headline is **retired, not refuted**, and its replacement is already in
every funnel. No successor ticket.

## Next action

**0. THE MERGE, AND IT IS STILL ONE STEP WITH THE RE-APPROVAL, IN MIT'S SITTING.** With Mit at
the keyboard and `pgrep -fl "boardwatch run"` finding nothing: `git merge --ff-only
close-2026-09-06`, then **immediately** `boardwatch profile-bundle approve-projection` on a
controlling TTY (the screen prints the shell's header and education above the entries), then the
formatting session in that same sitting — per-lens skills, the SAKEC/Nakshatra order,
`projection.{sde,ios}.yaml` — because each of those edits re-stales the stamp. Then verify the
gate read-only (`projection_candidate(...)`'s `content_digest` must equal the stamp's), then
`git push origin main`. **The branch to merge is `close-2026-09-06`** (it fast-forwards; it already
contains `close-2026-09-05`'s four commits). Only then delete the worktrees, and note there are
SEVEN: `../bw-close`, `../bw-t31`, `../bw-t32`, `../bw-t37`, `../bw-t38`, `../bw-t39` and
`../bw-int` — `bw-int` is the one holding `close-2026-09-06`, so remove it LAST, after the merge. **Without Mit: do not merge; do not move `main`.** The reason is
mechanical: the tick runs the editable venv from `main`, and a stale stamp costs a ~107-min scan,
a P5a refusal, exit 1 and a withheld heartbeat — a false alert for a condition we chose.

**0-1. T34 (M1) IS RESPECIFIED — DO NOT RUN IT AS WRITTEN; ITS APPARATUS CANNOT WORK.** Verified
read-only in the code and the store, not inferred: `gate request` builds its population from
`rank_open_postings(..., record_surfaced=False)`, which leaves `include_handled=False`, and
`cli/top_cmd.py` skips any posting whose job carries a live disposition. **All 80 delivered leads
carry `built`, permanently** — `job_dispositions` is 80/80 with `expires_at` and `reopened_at`
both NULL, and `core/ledger.py` calls that live forever. **So the judged population and
`delivered_unapplied` are DISJOINT BY CONSTRUCTION**, and every gate row would land in the probe's
"no longer in the queue" bucket. **It fails silently**: `m1_probe.py`'s null control checks only
the gate pass's OWN totals, computed before the lane join, so it PASSES while the lane join is
empty — the third apparatus zero of this kind in two sessions. `cli/top_cmd.py` also hides
gate-`ineligible` before the limit, so even a non-empty intersection could hold no
gate-`ineligible` row. There are **0 `llm` eligibility rows** in the store; D-461's 95 died with
the reset.
**The measurement is still reachable, and READ-ONLY.** `build_gate_request` is a pure function
over anything carrying `.posting_id`, so build the request directly over `delivered_unapplied()`'s
ids — never the `gate request` CLI, which is a write path AND the wrong population. Proven against
the live store on a `mode=ro` URI: 80 leads → 80 items, 0 dropped, 415,302 jd chars, the same order
as D-461's 95 items / 448,115. Precedent is in `METRICS.md` (the pre-reset lane-measured final
gate: leads sampled from the apply lane, two blind judges, verdicts to files, **nothing applied**).
Then: pin the posting-id set BEFORE judging (a two-arm read over a live store needs pinned ids);
judge blind on `jd_text` + `facts`; assert every `ineligible` evidence string is a RAW substring of
its own `jd_text`, because `accept_oracle_verdict` normalises and `record_gate_verdict`'s `span_of`
does not — a normalised-only match silently downgrades to `uncertain`. `gate apply` is a POLICY
action, not part of M1. Two probe fixes owed: its null control is hardcoded to D-461's totals and
must be re-pinned per pass, and its gate-side join does not scope by `profile_hash`/`rules_hash`,
which is wrong the moment a second pass exists. **T35** (gate 1 re-measure, D-424) is gated on
reaching 09-09; `.agent/2026-09-02-session/per_source_recall.py`, standing 28.8%.

**0-2. T40 IS PROPOSED AND NOT BUILT — the same defect class, one process wider.** T37 removed the
in-process second writer. It did NOT close the cross-process case: **every default-context CLI
command in this repo is a write path**, so anything run against the live store during a scan —
`top`, `doctor`, a `digest` — can kill a board through the identical snapshot upgrade. The
one-line hardening is `apply_board` taking `write_connection` (`BEGIN IMMEDIATE`), which makes a
contended apply QUEUE on `busy_timeout` instead of failing instantly. It is deliberately not
shipped inside a bug fix: it changes the scan's locking discipline for every board, holds the
write lock for a whole board apply, and is **Mit's call**.

**0-3. CLOSED, BY RULING:** T28 (this session — structurally zero, no successor). T33 and its
residual-zero successor, T36 as specified, T18 `data`/`ai`, T24, T26 (D-472 and earlier). **T36 is
re-decided only on the first tick after T38 lands**, on that tick's own smartrecruiters tail —
and `config.toml`'s comment still claims `le=8` against `Field(default=4, ge=1, le=32)`, to be
corrected in the next change that touches Mit's config, with his OK. SP3 (+T23) stays deferred
until three warm ticks report the tailor stage; run 3 is the first at 5.16 s/lead.

**0-4. STILL OWED AND UNTOUCHED — MIT'S:** `git push origin main` after the merge (nothing to push
before it); `.agent/2026-09-04c-session/discover-candidates.yaml` (80 GitHub-list boards, D-291);
the formatting session (with the re-approval, above); **the rest of the smartrecruiters fleet call**
— dominos is dropped, and boschgroup (4,018 deferred, 0 leads), cityofnewyork (1,084, 0) and
abbvie (1,074, 0) remain at ~400 host-seconds each per run, now overlapped by T38 rather than
serialised behind the fleet; StreakSync `main`.

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

## Owner-gated — do NOT start or decide unilaterally

**0-A. SP2 TOOK THE LANE STAGE'S THIRD-PARTY PACING FROM A BOUNDARY TO A WINDOW, AND IT IS LIVE
NOW.** Found by review this session, verified in the code, **not introduced by anything shipped
this session** — SP2 is already on `main` and has run in production twice. `Fetcher._host_locks`
and `_last_request_at` are PER INSTANCE, and the lane stage runs its own `Fetcher` on a background
thread that overlaps the whole board scan. So for any host BOTH reach, the two per-host locks are
independent and up to **2 req/s** can go to that third party for the lane stage's entire duration
(run 3: ~352 s) — not the "one boundary request" `_lane_fetcher`'s docstring claimed, which was
true only while the stages were strictly sequential. The lane does reach provider hosts:
`lanes/hiringcafe.py` fetches a provider board directly, and `lanes/grnh_seeds.py` and
`lanes/jsonld.py` dereference ATS hosts. The docstring is corrected to state what is true; **the
behaviour is deliberately NOT changed**, because both fixes are owner questions: one shared
`Fetcher` re-serialises the lanes against the scan and hands back SP2's entire prize, and a
cross-instance per-host lock is new machinery on the politeness path. **Mit's call, and it is a
pacing promise to third parties, not a performance knob.**

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
5. **ANSWERED 2026-09-05 — T31 (`1fc61596`, on `close-2026-09-05`): `boardwatch init` seeds the
   bundled `resume_template.tex` when absent and never overwrites; the placeholder-phrase catalog
   still refuses the unedited copy, so the fail-closed guarantee is unchanged.**

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
| **Runs 1–3 were all launched by hand or failed closed; the first warm UNATTENDED tick is 2026-09-05 04:00, which runs whatever `main` is parked on** — the mechanism note is still true | The launchd job invokes the **editable** venv at `boardwatch/.venv/bin/boardwatch`, so whatever branch that tree is parked on IS the unattended run's code and `rules.yaml`. A stale `.git/index.lock` once silently blocked every `git pull` for a whole session — check the lock's MTIME and `pgrep -x git` before blaming contention. **Park the primary checkout on `main` before ending every session**; a stray branch changes EVERY subsequent run, not one. Closing it mechanically means pointing the plist at a worktree pinned to `main`, which moves a scheduled job and a venv. The plist was path-fixed from the pre-reset account home to the current one (`~`) | **Mit** (mechanism); every session (discipline) |
