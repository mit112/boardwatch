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

### Session 2026-09-08 (execution): ALL SIX D-477 TICKETS LANDED on `main`, each gated exit 0 plus a final integration gate (9,497 passed); the judge model is RULED HAIKU; T42 is built but OFF and its arming is BLOCKED on an owner decision

**Read this before acting on anything below it.** Reasoning: **D-478**. Numbers: `METRICS.md`,
the `Session — 2026-09-08` block. Report: **`REPORT-2026-09-08.md`**.

T40, T41, T45, T44, T43, T42 are on `main`. T46 needed no code — B8's daily instrument is the
funnel's `pdf` stage `entered`, which T43 made apply-lane-only; its column is now on the
acceptance table. T34 was executed read-only, including its blind two-judge steps.

**Three things a fresh session must not re-derive:**

1. **The judge model is ruled: HAIKU** — 92.6% head-to-head with sonnet on the ineligible axis,
   kappa 0.847, planted control caught by both, 2.04x cheaper ($0.0086 vs $0.0176 per lead).
   §4's own bar could not be scored: there are **0 stored `final_gate:` verdicts** (the 95 died
   with the 09-03 reset), and the substituted slate has **no `ineligible` in its truth column**,
   which makes an agreement bar maximal for a judge that never decides. See D-478 §1.
2. **T42 is built, gated, and OFF by default — but arming it is an OPEN OWNER DECISION**, not a
   mechanical step. Under the owner's own 2026-09-05 ruling (bar floor <= 1 YOE) the judge is
   RIGHT to reject 2-3 year bars, but the engine abstains on them by policy
   (`near_miss_years_ceiling = 3`), so arming rejects **31-35% of the delivered slate** and
   settles that lever by fiat. The cheaper locus is a personal `rules.yaml` override, which owes
   a ledger drain. Left to planning — see `REPORT-2026-09-08.md` P1.
3. **T44 cannot fire on the pipeline path.** Its verdict is now computed for real (it defaulted
   `False` at every caller), but `runner.py` omits `include_over_seniority`, so the ranker drops
   above-band leads before any lane sees them. `moved = 0` was never "no lead is above band".
   A guard test pins this. See D-478 §2.

**The arming preconditions for T42 are NOT met, and one instruction is wrong.**
`~/.claude-boardwatch` does not exist; the plist carries no `CLAUDE_CONFIG_DIR` (that IS the
right variable — confirmed in the installed binary; there is no `--config-dir` flag). And the
gate block must go in **`~/Library/Application Support/boardwatch/config.toml`**, which is what
`Settings` reads (`BOARDWATCH_CONFIG_DIR` > platformdirs) — **not** `~/.config/boardwatch/`,
which does not exist and would arm nothing silently.

## Next action

**0. THE 06:00 TICK IS STILL UNLOADED, AND RUN 4 HAS NOT HAPPENED.** `launchctl bootout` was run
at 05:47 CDT on 2026-09-05 so merges never landed under a live run of the editable venv. `main`
now holds all six tickets, and the primary checkout is parked on `main`, so the re-load is
unblocked:

```
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.boardwatch.run.plist
launchctl print gui/$UID/com.boardwatch.run     # `list` shows 0 for a NEVER-RUN job; use print
```

It fires at **06:00 CDT, not 04:00**, until a reboot (launchd computes the interval in its
boot-time zone), or run `boardwatch run --project --top 40` by hand. Then take run 4's reading per
`HANDOFF-2026-09-07.md` §5. The healthchecks heartbeat (period 1 d, grace 2 h) will alert on the
missed ping unless paused in its dashboard; the ping-URL `/pause` returned 400 — do not retry it.

**Expect run 4's ledger-drift report to show EVERY permanent disposition stale.** That is landing
T42's new IN-classified `gate` setting re-stamping `run_policy_version` (`config_hash`
`f56a0166` -> `200396b9`), armed or not. It is not an eligibility re-key and nothing auto-reopens
(D-478 §3). Read cold on the first run after a long gap it looks like an incident; it is not.

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

**0-5. THE PRODUCT REVIEW IS RULED (D-477) AND TICKETED — `REVIEW-2026-09-05.md`, `HANDOFF-2026-09-08.md`.**
Mit agreed all six findings 05:39–05:45 CDT: the LLM judge goes on the daily path over the delivered slate
(enterprise sub, headless, fail-open, cost bounded by `--top`), tailor the apply lane only, B8 joins the bar,
Gate 1 thresholds are fixed, done = single-tenant. Execution order: the 09-07 handoff's T40/T41 first, then
09-08's T45, T44, T43, T42, T46. **THE 06:00 TICK OF 2026-09-05 IS UNLOADED (05:47 CDT, his request) so the
execution session can merge without a live run.** Run 4 is therefore NOT today's tick: re-load the plist
(`launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.boardwatch.run.plist`) or run by hand when the
merges are on `main`; the heartbeat will alert on the missed ping unless paused in its dashboard.

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
