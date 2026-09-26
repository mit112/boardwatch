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
> this file's old standing sections (five of their claims had gone stale — D-598). The twenty-third, **2026-09-26**, moved the 2026-09-25b block WHOLE once its day-1 read and opus census were done. The nineteenth, **2026-09-23b**, moved the 2026-09-23, 2026-09-22f and 2026-09-22c blocks
> WHOLE once run 471 was read and the pull to `de7ae153` done; the 22e block stays until run 472 is read. **Nothing has
> been deleted on any pass.** Do not narrate a decision here that `DECISIONS.md` already holds — cite its number
> instead. **If this file passes ~250 lines again, the
> fix is to move settled blocks out, not to summarise them away.**

---

## Current standing

### 2026-09-26 — **DAY 1 OF THE 14 IS RUN 478 AND IT MEETS B1–B8** (kickstarted 2026-09-25 21:03 CDT under the D-597 prepone ruling; the 09-26 04:00 tick is day 2; day 14 = the 10-08 run if nothing restarts it). **The opus B8 census reads 4/97 = 4.1%.** The apply lane was made ready on the owner's instruction: **87 PDF-less leads rendered, 61 unapplyable leads reported.** T256 #500 and T257 #501 shipped (D-599).

**Verify first:** `git log --oneline -5 origin/main`, the primary on `main` (it was pulled to #500 at 01:59; #501 and this docs PR land after it), the tick enabled, `.agent/2026-09-26-session/notes.md`. Read a day with `python3 .agent/acceptance/day_row.py <run_id> <day>` (exit 1 = a bar or the judge failed) and `.venv/bin/python .agent/acceptance/b4_audit.py --run <run_id>`.

**Day 1, run 478** (METRICS "Acceptance run"): B1 40 · B2 29/29 · B3 all one page · B4 0 on 29 · B5 ok · B6 reconciles · B7 0% abstain · B8 29/day · gate judged 45, failed-open 0. **B8 precision, opus census** of runs 476–478 placements: **4/97 = 4.1% (Wilson 1.6–10.1)**; overlap 17/17; short job-apps summaries 0/31, long bodies 4/66. n ≥ 100 closes with day 2's placements.

**What the session found and did:**
- **The scan crawled** (141 boards in 88 min): `scan/apply`'s two per-board reads walked all ~305k open postings through the status index; disk-bound under memory pressure on the 16 GB machine (a game was running); ~140 boards/min again once it closed. **T256 (#500)** moves them onto the company index (`likely()` hint). Run 478's wall clock was 4 h 42 m.
- **The 1800 s cap works:** Deutsche Bank 1 → 1,142 open, Hitachi 1 → 1,555, Timberland 1 → 1,386, M&T 1 → 799. dominos grew 802 → 2,271, none ever delivered (owner call 3).
- **The seat:** this session's 403-lead opus lane audit exhausted the enterprise seat 00:25–01:30; run 478's gate ran on the reset window and judged cleanly. Size any opus fan-out against the next gate stage.
- **Apply-lane readiness** (the owner, 00:02: "making sure the jobs i can apply to are all ready to go"): 87 apply-lane leads had NO PDF — review-lane stubs that the review gate later released into the apply lane, which nothing renders (T259). All 87 rendered through the runner's own path (`lane/render_pending.py`, one manual run row 479); B4 0 on them. Both opus judges read every lead (agreement 97.5%); the 61 unapplyable were **marked reported** on the owner's ruling (`_reported/`, list in `lane/reported-2026-09-26.json`, reversible). **The apply lane now holds 429: 418 clean by both judges + 11 split, every one with a one-page PDF, every posting open.**
- **T257 (#501):** a never-delivered lane copy is held while a delivered copy of its `cross_host` group is open and unreported, applied or not (41 of 578 deliveries since run 308 were repeats; one role applied to twice). Delivery-side; the count does not restart.
- **Graduation windows written `graduation date of X – Y`** escape `graduation_window_required` (52 open postings; 3 delivered, all Adobe, now reported). **Recorded, not fixed** (owner, 02:13): it is an eligibility change and would restart the count — T258.

**Next, in order:**
1. **Read the 04:00 run as day 2** (`day_row.py <id> 2`, B4 `--run`), add its apply-lane placements to the opus census (`bw-review/.agent/auditB8-opus/stage478.py`, change the run id) to close n ≥ 100, add the METRICS row. Keep the seat quiet from ~03:00 until its gate stage ends.
2. **Each following day:** the same. Nothing else is owed.
3. **T255 v0.6.0:** branch `release-0.6.0` (worktree `bw-t255`, gate EXIT=0 on #500) is HELD unmerged — rebase it onto `main` again, then merge and tag together once the owner confirms the PyPI publish.

**Changed this session (live store / machine):** 87 `resume_tailored` artifacts and their queue folders (manual run 479); 61 `queue.reported.*` rows; the primary pulled to #500; a stale `.git/index.lock` (from 2026-09-25 19:16, no git process) removed.

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
5. **How job-apps summary leads count in the B8 census** — short bodies read 0/31, long 4/66 on the opus census (a short
   reading is a floor). Default until ruled: counted, with the split reported beside the pooled number.
6. **When to fix T258** (graduation-window wording; 52 open postings) — an eligibility change, so it restarts the count.

## Open questions and carried gaps (settled guidance is in `STANDING-FACTS.md`)

- **v2, parked on purpose (D-598 r4):** field-dependent eligibility as data (a non-software user still needs code —
  `eligibility/catalog.py` lists `career_fields: [software]`), a real second user, public release and community launch.
- **Location still fails open on `unknown`** (T253): 241 open Workday rows stay `unknown`, 271411 among them; country catalog
  gaps (Türkiye, Nicaragua); some US towns misread as non-US. Watch for it in the census; fix only from a delivered lead.
- **The standing apply queue** can hold leads released after a re-key until the 130/run refresh reaches them (649 pending
  after run 477). It is not the B8 population (D-598 r6) but it is what the owner reads.
- **Windows nightly red since 09-23** (T251; best-effort platform, no bar). Read a Windows result by test name, never colour.
- **The primary checkout IS the daily run's code** (editable venv): park it on `main`, never pull while a run is active
  (`ps -Ao args | grep -Eq '(^|/)boardwatch run '`).
- **Citi sits at ~13% coverage permanently** (Workday's 2,000 cap; facet sum 4,589) — input-side, no bar.
- **The run clock moves to fit the work** (D-597): prepone = `launchctl kickstart gui/$(id -u)/com.boardwatch.run`;
  postpone = `disable` before the tick, kickstart, `enable` — never leave it disabled.
