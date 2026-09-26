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
> owner calls. **Settled subsystem history is moved WHOLE into `STANDING-FACTS.md`, never summarised
> away** — sixteen passes through 2026-09-22b; the seventeenth, **2026-09-22c**, moved the
> 2026-09-21 and 2026-09-22b blocks WHOLE once run 470 had been read against the 2026-09-21 block's
> recorded prediction, which was the last condition inside either; the eighteenth, **2026-09-22e**,
> moved the 2026-09-22d block WHOLE once its run-471 expectation was restated above. (2026-09-22f and 2026-09-23 moved
> nothing.) The twentieth, **2026-09-24d**, moved the 2026-09-24c block WHOLE once its chain, repair and
> owner calls were all done; the twenty-first, **2026-09-25a**, moved the 2026-09-24e block WHOLE once every step it
> listed was done; the twenty-second, **2026-09-25b**, moved the 2026-09-25a and 2026-09-24d blocks WHOLE and, with them,
> this file's old standing sections (five of their claims had gone stale — D-598). The twenty-third, **2026-09-26**, moved the 2026-09-25b block WHOLE once its day-1 read and opus census were done. The twenty-fourth, **2026-09-26b**, moved the 2026-09-26 block WHOLE once its day-2 read and census close were done. The nineteenth, **2026-09-23b**, moved the 2026-09-23, 2026-09-22f and 2026-09-22c blocks
> WHOLE once run 471 was read and the pull to `de7ae153` done; the 22e block stays until run 472 is read. **Nothing has
> been deleted on any pass.** Do not narrate a decision here that `DECISIONS.md` already holds — cite its number
> instead. **If this file passes ~250 lines again, the
> fix is to move settled blocks out, not to summarise them away.**

---

## Current standing

### 2026-09-26b — **THE COUNT RESTARTED: DAY 1 IS THE 2026-09-27 04:00 RUN, DAY 14 THE 10-10 RUN** (D-600). Run 480 (day 2) met every bar on the funnel, but read NET-NEW — as B1 says — runs 478 and 480 delivered **8 and 1** new jobs of 40: D-588's 09-24 ledger drain had re-served ~1,000 delivered leads. **The drain is re-closed** (1,018 rows, owner's ruling); the guard is T264. **The opus B8 census closed at 7/125 = 5.6% (Wilson 3–11).** The apply lane is ready: 527 leads, every one open with a one-page PDF.

**Verify first:** `git log --oneline -5 origin/main`, the primary on `main`, the tick enabled, `.agent/2026-09-26-session/notes.md`.
Read a day with `python3 .agent/acceptance/day_row.py <run_id> <day>` — **B1 and B8 volume are now read net-new** (a lead whose
job the run decided first; the log's `N new` folders printed beside it). Exit 1 = a bar or the judge failed. B4: `.venv/bin/python
.agent/acceptance/b4_audit.py --run <run_id>`.

**Day 2, run 480** (METRICS "Acceptance run"): B1 40 funnel / **1 net-new** · B2 28/28 · B3 one page · B4 0 on 28 (0 on all 157
PDFs of the day) · B5–B7 ok · B8 28 funnel / **1 net-new** · gate judged 5, failed-open 0. First run on T256/T257: wall 1 h 28 m
(478: 4 h 42 m), `hidden_lane_copy` 15.

**What the session found and did:**
- **Repeat delivery.** Runs 467–474 repeated 0 of 40 leads; 475–480 repeated 32–40, one of them a lead the owner had reported.
  Cause: `ledger reopen --stale` at the T186 cutover (D-588 §2) reopened 1,206 `built` rows; the shortlist hides only live
  dispositions. Re-closed: `reopened_at` → NULL on the 1,018 still stamped 2026-09-24 07:17:55 UTC (ids saved,
  `lane/reclose-drain-rows.json`); verified 1,018/1,018 live through `live_dispositions`. **Do not run `ledger reopen --stale`
  until T264 ships** — `ledger show --stale` lists these rows and draining them repeats the defect.
- **B8 census closed** (D-598 r6): run 480 3/28, all `seniority_fit`; pooled 7/125 = 5.6%; overlap 22/22; short bodies 0/38,
  long 7/87. Apparatus `bw-review/.agent/auditB8-opus/` (stage480.py; score.py knows arm `run480`).
- **Apply lane:** 18 more T259 stubs (released by the gate's refresh) rendered under manual run row **481**; both opus judges on
  the 103 never-judged leads: 99 clean, 3 split, 1 both → Dexcom 157510 reported (owner). Four leads went to `_review` as
  `revised_since_build` once their `built` was live again (designed, T119).

**Next, in order:**
1. **Read the 09-27 04:00 run as day 1** (`day_row.py <id> 1`, B4 `--run`). Expect net-new near run 474's 40 now that the drain
   is closed; if it is not, the re-close did not take — read `hidden_handled` (474: 1,089).
2. **Each following day:** the same, plus `inventory.py` (`pdf missing` must be 0; render T259 stubs with `render_pending.py`).
   The census is closed; spot-check a day's placements only if a defect is suspected.
3. **T264** is a delivery-side fix and may ship under the freeze; it is not urgent while nobody drains.
4. **T255 v0.6.0:** `release-0.6.0` (worktree `bw-t255`) HELD — rebase onto `main`, re-gate, merge and tag together on the
   owner's confirmation.

**Changed this session (live store / machine):** 1,018 `job_dispositions.reopened_at` cleared; 18 `resume_tailored` artifacts and
their folders (run 481); 1 `queue.reported.*` row.

### 2026-09-26 — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-26b.** Day 1 as run 478 (superseded: read net-new it failed B1/B8 volume, D-600), the 4/97 census (closed at 7/125), the apply lane made ready, T256/T257 shipped (D-599).

### 2026-09-25b — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-26.** The finish line and the freeze rule (D-598, restated in `ROADMAP.md`); its day-1 read and opus census are done above.

### 2026-09-25a — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-25b.** Wave 3b and engine batches 6–10 shipped, T229–T232 and T243, runs 476/477 re-keyed; its next steps are restated above or parked by D-598.

### 2026-09-24e — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-25a.** Wave 3a shipped; wave 3b's one red (a T173 re-baseline), the ship chain, TB6b, run 476 and T230–T238 — every step it listed is done (D-597).

### 2026-09-24d — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-25b.** The chain (T199, bundle A, T210, T209, T188, T208), the 0-D repair (done: 43 → 9 open damaged, the nine are `gone`), T173's heading classes and wave 3's recipe (D-595); every step is done (D-596, D-597).

### 2026-09-24c — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-24d.** The "no waiting" sprint day (D-594): eight rulings, the chain, wave gating. Every step it listed is done or restated above.

### 2026-09-23b — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-24.** Runs 472 and 473/474 read (D-580, D-588); the post-472 pull done; the owner calls it listed are all ruled (D-577); T170 (#439) and T172 (#434) shipped; T171 (#438) and T162 (#441) shipped.

### 2026-09-23 — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-23b.** The six-ticket stack (D-562), which finished merging only by rebase (D-568). Its run-472 step is restated in the block above.

### 2026-09-22f — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-23b.** T135 shipped (D-559), T123/T124 closed on measurement (D-558), the D-557 rulings, T161 measured and now SHIPPED (D-569). Every step in it is done.

### 2026-09-22e — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-24.** The eligibility batch's re-key ran as run 472 (D-580): judged 117, cached 0, apply lane 29, refresh 130 of 861; its predictions held.

### 2026-09-22d — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-22e.** T159 read (D-550: apply lane 5.4% unapplyable, B8 precision MET); T113 shipped and armed at 130/run (D-551, D-552); T127/T158 shipped. Its run-471 expectation is restated in the block above.

### 2026-09-22c — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-23b.** Run 470 read (D-547), T153 executed and the standing queue re-judged on `sonnet` (D-548), `gate.effort` shipped. Its last open item, run 471's reading, is answered in D-572.

### 2026-09-22b — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-22c.** T149 + T154 shipped (**read D-541 before touching `abstain_by_adjacent`**: the degree escape was abstaining bars the profile already met, 5,579 rows), T150 live, T92 and T151 shipped, T101 refused on measurement (D-544), T153 corrected (D-545) and now EXECUTED (D-548), T152/T105 designed (D-546). **Held in D-540 … D-546 — do not re-derive.**

### 2026-09-22 (earlier) — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-22b.** §5 refuted and already held by T109 (D-536); a catalog re-key RELEASES 117 held leads (D-537); the degree-waiver gap enumerated at 6,712 and ruled in (D-538); four tickets ruled and specced (D-539). **All four rulings are now discharged — see the block above.**

### 2026-09-21 — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-22c.** Run 469 inverted the priority: **the binding constraint is the SLATE CAP, not discovery** — read D-532 before proposing ANY discovery work; anything sized in "eligible postings added" is in the wrong unit. The drain refused (D-533); B8's 9-of-14 record superseded (D-534); the Windows `os.replace` race fixed (D-535). Its recorded prediction for run 470 is answered in D-547. **Standing from it: a CONTENDED `make check` is a FALSE NEGATIVE** — check `uptime` first; above ~load 8 vitest's 5 s timeouts fail and the count varies run to run.

### 2026-09-20g / 2026-09-20f / 2026-09-19 — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-21.**
Run 468's second reading (superseded by run 469, D-532); T104's refutation and rebuild (D-531, shipped);
the engine batch's opening (D-530 — it MERGED as `ea95c42c`); run 467, Gate 1's second reading clearing
all four employer-board bars, Indeed confirmed dead, and the stage-1 import that took the fleet 652 →
1,807 (D-521, D-522). **Do not re-derive any of it.** One correction carried forward: D-522 §3's sizing
rule (size from fleet density, predict yield from the sample) is **superseded by D-532** — both halves
are denominated in eligible postings, which is the wrong unit once the slate cap binds.

### 2026-09-20d/e — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-20g.** The astra remediation wave: thirteen tickets in one gated wave, merged (D-528, PR #398 → `09df0e87`); Windows green and the five-night red over; the composite-title asymmetry REFUTED; T136's `ge=1` deliberately unchanged; next action 4's one-time re-judge FIRED and CLEAN on run 468. **Held in D-528 — do not re-derive.**

### Astra reviews 01–05 — **CONSUMED AND CLOSED.** All five slices, 42 findings, nothing refuted. Held WHOLE in **D-523 … D-527** and the five `archive/TICKETS-2026-09-*-ASTRA-0*.md` files; the remediation that followed is **D-528**. **Do not re-derive any of it.** Of T98–T148 (51 tickets), **33 shipped**; **T145/T146/T147 are not build work** (owner DO-NOT-BUILD, future-reading guidance, LinkedIn posture); **T100–T105 are held as ONE engine bump** with next action 4; and of what stayed open, **T113 and T127 shipped (22d), T135 shipped (22f), T123 and T124 closed on measurement (D-558), T125 was rebuilt as an annotation, and T138's reverse half is refused (D-557); T144, T133, T137, T138's per-kind half, T139's stage extraction and T125 all SHIPPED on 2026-09-23 (D-562, D-568). Every astra ticket is closed.**

### 2026-09-19 — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-22b.** The expansion is measured and works (run 467, D-522); Indeed confirmed dead; M5's 14th day taken and B1–B7 pass (D-521 §5); Gate 1's second reading discharges M4's last condition; the discovery backlog sized at three disjoint gaps and stage 1 imported, fleet 652 → 1,807. **Held in D-521 and D-522 — do not re-derive.**

## Owner-gated — do NOT start or decide unilaterally

1. **The v0.6.0 PyPI publish** (T255) — the tag is outward-facing and effectively irreversible.
2. **Puerto Rico for a USA-target profile** (T253 d) — measured 2026-09-25: PR locations resolve `unknown`, fail open and
   ARE delivered (5 built, HPE graduate roles). Default while unruled: keep them. Excluding them is profile data and restarts the count.
3. **dominos** (SmartRecruiters; 2,271 open after run 478, 0 ever delivered, 2 software-ish titles; holds the shared SR
   host up to the 1800 s cap) — keep, facet-slice, per-board cap, or unwatch; recommendation: unwatch.
4. **The résumé formatting session** — Mit's to schedule; résumé calls (1) and (2) were dropped (D-594).
5. **How job-apps summary leads count in the B8 census** — closed census: short bodies 0/38, long 7/87 (a short reading is
   a floor). Default until ruled: counted, with the split reported beside the pooled number.
6. **When to fix T258** (graduation-window wording; 52 open postings) — an eligibility change, so it restarts the count.

## Open questions and carried gaps (settled guidance is in `STANDING-FACTS.md`)

- **v2, parked on purpose (D-598 r4):** field-dependent eligibility as data (a non-software user still needs code —
  `eligibility/catalog.py` lists `career_fields: [software]`), a real second user, public release and community launch.
- **Location still fails open on `unknown`** (T253): 241 open Workday rows stay `unknown`, 271411 among them; country catalog
  gaps (Türkiye, Nicaragua); some US towns misread as non-US. Watch for it in the census; fix only from a delivered lead.
- **The standing apply queue** can hold leads released after a re-key until the 130/run refresh reaches them (321 pending
  after run 480). It is not the B8 population (D-598 r6) but it is what the owner reads.
- **Windows nightly red since 09-23** (T251; best-effort platform, no bar). Read a Windows result by test name, never colour.
- **The primary checkout IS the daily run's code** (editable venv): park it on `main`, never pull while a run is active
  (`ps -Ao args | grep -Eq '(^|/)boardwatch run '`).
- **Citi sits at ~13% coverage permanently** (Workday's 2,000 cap; facet sum 4,589) — input-side, no bar.
- **The run clock moves to fit the work** (D-597): prepone = `launchctl kickstart gui/$(id -u)/com.boardwatch.run`;
  postpone = `disable` before the tick, kickstart, `enable` — never leave it disabled.
