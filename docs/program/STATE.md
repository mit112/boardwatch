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

### Session 2026-09-06b (planning review): the 2026-09-06 report HOLDS; the lane-pacing exposure is RE-SIZED to ~90 s on one host per run and the review's shared-`Fetcher` claim was WRONG, so the fix is T41; T40 is RECOMMENDED on run 3's apply distribution; T34's read-only form is APPROVED with a planted control and the gate's cadence is a RULE; T36 is a RULE; the fleet call is 0 wall minutes — next list `HANDOFF-2026-09-07.md`

**Read this before acting on anything below it.** Reasoning: **D-474**. Numbers: `METRICS.md`,
the `Session — 2026-09-06b` block. The 2026-09-06 execution block moved WHOLE into
`STANDING-FACTS.md`; D-473 holds its reasoning. **`main` is still `84671523`.**
`close-2026-09-06` carries FOURTEEN commits over it and **one `--ff-only` merge lands them all.**

**The five decisions the 09-06 session left are all ruled or sized (D-474):**
- **(a) Lane pacing (§0-A below).** Real, owner's, and **~90 s on `boards-api.greenhouse.io`
  per run**, seconds on ashby and lever — not 352 s: only hiringcafe's 94 per-board GETs reach
  scan hosts. The review's "a shared `Fetcher` re-serialises the lanes" was false (the lock is
  per HOST); the real coupling is the client's default UA. **Fix = T41**, a per-process pacing
  registry, two clients kept, SP2 untouched. Recommended; Mit's word.
- **(b) T40 RECOMMENDED.** Run 3 applies: p50 0.26 s, p90 5.15 s, max 16.4 s, **30 of 287 past
  the 5 s `busy_timeout`**. `BEGIN IMMEDIATE` makes a CLI write during one of those fail loudly
  instead of the scan losing a board. Mit's yes.
- **(c) T34 APPROVED read-only** (`HANDOFF-2026-09-07.md` §4) with a planted item that MUST
  come back `ineligible`. **Cadence rule:** apply lane is 5 of 80; ≥ 1 apply-lane
  gate-`ineligible` ⇒ per-run gate over the apply lane only; 0 ⇒ stays manual.
- **(d) T36 by rule** on the first post-merge run, against run 4 as the same-fleet pre-T38
  baseline: tail ≤ 3 min and `boards_failed` 0 ⇒ `scan_workers` 16 (model 83.8 → 45.2 min).
- **(e) Fleet: 0 wall minutes either way** — the 9-board chain (≈ 31 min) is under the Workday
  span at 8 or 16 workers. Dropping the three saves ~1,200 host-s/run and removes 97 `eligible`
  postings with 0 leads. Mit's.

**`ROADMAP.md` is NEW, at Mit's request** — five milestones with exit criteria; **M1 (land the merge, run
it once) is the open one: the merge LANDED at 04:13 (§0), the run is owed.** Work only what moves its
exit criterion.

**Run 4 is the launchd tick of 2026-09-05 on `main` UNCHANGED** (287 boards, no T37/T38/T39),
deliberately not postponed: SP3 measurement 2 of 3 and T38's baseline. **It did not fire at
04:00 CDT: launchd computes the calendar interval in the zone it BOOTED with, and the system
zone was set to Chicago five minutes after boot — so the tick fires at 06:00 CDT** (as 09-04's
did, 06:00:05) until a reboot or a plist edit, Mit's. Verify on run 4's `started_at`; read it
first (R2).

## Next action

**0. THE MERGE LANDED — 2026-09-05 04:13 CDT, IN MIT'S SITTING, WITH THE RE-APPROVAL.** `main` is
`b040ee90` on origin (`git merge --ff-only close-2026-09-06`, fifteen commits, after removing a
stale `.git/index.lock` from 09-04 22:54 with no git process alive). Mit ran
`profile-bundle approve-projection` on a controlling terminal at 04:14:01 CDT; the stamp's
`content_digest` was verified read-only against `projection_candidate(...)` — **MATCH**. The
seven worktrees are removed (`bw-int` last) and their branches deleted. **The editable venv now
runs T37, T38 and T39**, and the next `--project` run is M1's first acceptance reading (§5 of
`HANDOFF-2026-09-07.md`). **The formatting session is DONE (D-476), 04:45–05:00 CDT:** Nakshatra
now sits above SAKEC, the skills block is kept as shell-authored, `projection.{sde,ios}.yaml` exist;
`projection.yaml` re-approved at **04:59:45 CDT**, both lens files at 04:59:52 and 05:00:01, all three
`content_digest`s verified read-only — **MATCH**. The stamp is fresh for the 06:00 tick. The template's
spacing was then evened out (D-476 addendum; outside the stamp, re-verified MATCH).

**0-0. OWNER RULINGS 2026-09-05 04:13 (D-475): T40 — YES, build. T41 — FIX, build.** Both are
now plain tickets for the next execution session, in that order, after R2.

**0-1. T34 (M1) IS RESPECIFIED AND ITS READ-ONLY FORM IS APPROVED (D-474 choice 4).** The
apparatus as written cannot work — `gate request` ranks with `include_handled=False` and all 80
delivered leads carry `built` permanently, so the judged population and `delivered_unapplied`
are DISJOINT BY CONSTRUCTION, and `m1_probe.py`'s null control passes on the gate pass's own
totals while the lane join is empty (D-473 choice 8). **Run it ONLY as `HANDOFF-2026-09-07.md`
§4 says**: pin ids first, `build_gate_request` on a `mode=ro` engine, a PLANTED item that must
return `ineligible`, two blind judges, raw-substring `span_of` as the persisted-equivalent,
nothing written. Only with no run in flight. **T35** (D-424) is gated on 09-09;
`.agent/2026-09-02-session/per_source_recall.py`, standing 28.8%.

**0-2. T40 AND T41 ARE RULED (§0-0) AND TICKETED.** T40:
`apply_board` on `write_connection` (`BEGIN IMMEDIATE`), one line; the stated consequence is a
CLI write failing loudly during one of the ~30 boards whose apply exceeds 5 s. T41: one
per-process per-host pacing registry shared by every `Fetcher`, two clients kept; priced at 94
waits of ≤ 1 s per run. Specs, red-first tests and blast radius in the handoff §3.

**0-3. CLOSED, BY RULING:** T28 (this session — structurally zero, no successor). T33 and its
residual-zero successor, T36 as specified, T18 `data`/`ai`, T24, T26 (D-472 and earlier). **T36 is
re-decided only on the first tick after T38 lands**, on that tick's own smartrecruiters tail —
and `config.toml`'s comment still claims `le=8` against `Field(default=4, ge=1, le=32)`, to be
corrected in the next change that touches Mit's config, with his OK. SP3 (+T23) stays deferred
until three warm ticks report the tailor stage; run 3 is the first at 5.16 s/lead. **T36's rule is

in the handoff §5**; the `le=8` comment is corrected in that same config change.

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

**0-A. THE LANE STAGE'S THIRD-PARTY PACING IS WEAKENED ON THREE SCAN HOSTS, AND IT IS LIVE
NOW.** Found by the 09-06 review, re-sized by D-474 choice 1 from run 3's funnel, **not
introduced by anything shipped since SP2** (already on `main`, run in production twice).
`Fetcher._host_locks` and `_last_request_at` are PER INSTANCE and the lane stage's own instance
overlaps the scan, so a host both reach can see 2 in flight and 2 req/s. **The only such
traffic is hiringcafe's one GET per admitted board** — 94 in run 3: 40 to
`boards-api.greenhouse.io` (the scan spends 90.0 s there), 44 to `api.ashbyhq.com` (10.1 s),
10 to `api.lever.co` (12.0 s) — so the exposure is ≤ ~90 s on one host per run, not the lane
stage's 352 s. `grnh_seeds` is a CLI command and `jsonld`'s hosts are not scan hosts. **The
fix is T41** (shared pacing STATE, not a shared client — the client's default UA is what
linkedin and github_lists rely on). **Mit's call, and it is a pacing promise to third parties,
not a performance knob.**

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
| **Runs 1–3 were all launched by hand or failed closed; the first warm UNATTENDED tick is 2026-09-05 04:00, which runs whatever `main` is parked on** — the mechanism note is still true | The launchd job invokes the **editable** venv at `boardwatch/.venv/bin/boardwatch`, so whatever branch that tree is parked on IS the unattended run's code and `rules.yaml`. A stale `.git/index.lock` once silently blocked every `git pull` for a whole session — check the lock's MTIME and `pgrep -x git` before blaming contention. **Park the primary checkout on `main` before ending every session**; a stray branch changes EVERY subsequent run, not one. Closing it mechanically means pointing the plist at a worktree pinned to `main`, which moves a scheduled job and a venv. The plist was path-fixed from the pre-reset account home to the current one (`~`). **The 04:00 schedule fires at 06:00 CDT** until the next reboot: launchd started five minutes before the timezone was set (2026-09-06b) | **Mit** (mechanism); every session (discipline) |
