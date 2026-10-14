# PROGRAM STATE — read this first

> **2026-10-13: the judge is Claude (`sonnet`/`medium`, D-631) on the one personal subscription.** The GPT transport (D-623)
> stays in the code, unselected; the October 5 "no subscription" and October 1 seat notes are history (moved to
> `STANDING-FACTS.md`). Headless fan-out spends Mit's only window and needs his go-ahead.

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
> this file's old standing sections (five of their claims had gone stale — D-598). The twenty-third, **2026-09-26**, moved the 2026-09-25b block WHOLE once its day-1 read and opus census were done. The twenty-fourth, **2026-09-26b**, moved the 2026-09-26 block WHOLE once its day-2 read and census close were done. The twenty-fifth, **2026-09-28b**, moved the 2026-09-27b and 2026-09-27 blocks WHOLE once their day-2 read, #510 check, ruling-6 check and held-capture repair were done. The twenty-sixth, **2026-09-28d**, moved the 2026-09-28c block WHOLE once its T268–T270 step was done or ruled. The twenty-seventh, **2026-09-28f**, moved the 2026-09-28e, 2026-09-28b and 2026-09-28 blocks WHOLE once day 3 was read. The twenty-eighth, **2026-09-30**, moved the 2026-09-29 and 2026-09-28f blocks WHOLE once day 4 was read. The twenty-ninth, **2026-10-01**, moved the 2026-09-30 block WHOLE once day 5 was read. The thirtieth, **2026-10-02b**, moved the 2026-10-01b and 2026-10-01 blocks WHOLE once day 6 was read. The thirty-first, **2026-10-03**, moved the 2026-10-02b and 2026-10-02 blocks WHOLE once day 7 was read and the two viewer rulings were made. The thirty-second, **2026-10-04**, moved the 2026-10-03 block WHOLE once day 8 was read and the backup call was ruled. The thirty-third, **2026-10-13**, moved the 2026-10-10 (D-628), 2026-10-09c, 2026-10-09b, 2026-10-09, 2026-10-06b, 2026-09-26c and 2026-09-26b blocks and the October 1/5/6 banners WHOLE once runs 579/580 were read and the two-opus census run (D-633). The nineteenth, **2026-09-23b**, moved the 2026-09-23, 2026-09-22f and 2026-09-22c blocks
> WHOLE once run 471 was read and the pull to `de7ae153` done; the 22e block stays until run 472 is read. **Nothing has
> been deleted on any pass.** Do not narrate a decision here that `DECISIONS.md` already holds — cite its number
> instead. **If this file passes ~250 lines again, the
> fix is to move settled blocks out, not to summarise them away.**

---

## Current standing

### 2026-10-14 — **RUN 581 FAILS B8 VOLUME (19 < 20) AND THE GATE CHECK; THE CANDIDATE STREAK RESETS; CENSUS 1/77; TWO GATE FIXES** (D-634).

**Run 581 (10-14, day 18):** B1 36 net-new, B2–B7 pass (19/19 one-page PDFs, B4 0 unmatched), **B8 19 net-new apply — FAIL**
(17 held for review, 13 `no_requirements_found`). **Gate: 1 batch failed open** (`Extra data` after the verdict array, 13 leads
unjudged). `day_row.py` exit 1. Runs 579/580 can no longer be streak days 1–2. The streak restarts at the next passing day.

**B8 census:** run 581's 19 apply placements were added as batches 10–13 in both opus arms (`stage_extend.py`; batches 00–09
untouched). **Pooled 1/77 = 1.3% (Wilson 0.2–7.0)**, 0/19 this run, arms agree 77/77, null controls exit 1. n is still < 100.

**Fixed in D-634:** the gate now reads a verdict array followed by a prose note instead of failing the batch. The refresh
line reports `withheld` leads. The stalled refresh was not a budget fault: 22 of the 35 stale standing leads (read after run
581) are Jobright pages that D-406 never sends. They stay delivered and unjudged by design (D-463).

**Next:** read run 582 (10-15) with `day_row.py` (scratch copy with `?immutable=1`, only after `lsof` shows no writer) and
`b4_audit.py`. Extend the census with `python3 stage_extend.py <date>:<run>`, then `judge.py A` and `judge.py B`, `score.py`,
`validate.py`. Once n ≥ 100, a passing day is certified only if the pooled rate is ≤ 16%. Check the refresh line's `withheld`
against `still stale`. If they differ, the refresh has a real backlog.

### 2026-10-13 — **RUNS 579 AND 580 PASS EVERY MEASURED BAR; THE TWO-OPUS CENSUS READS 1/58; B8 NOT YET CERTIFIED (n < 100)** (D-633).

**The first two Claude-judged days.** Run 579 (10-12): 54 net-new, 27 net-new apply. Run 580 (10-13): 41 net-new, 31
net-new apply. Both: 100% one-page PDFs, 0 tailor_failed, B4 0 unmatched, B5–B7 pass, gate 0 failed-open, `day_row.py`
exit 0. Run 550 (10-11, the last GPT run; its backlog stopped on two `codex exited 1` batches) is not scored.

**B8 census:** two `claude-opus-5-5` arms, each judging all 58 apply placements: **1/58 = 1.7% (Wilson 0.3–9.1)**, arms
agree 58/58. The bar pools to n ≥ 100. **Days 16–17 are candidate streak days 1–2, certified only once the pooled census
reaches n ≥ 100.**

### 2026-10-11 — **PRIMARY CHECKOUT COMMITTED AND CURRENT; OWNER CLOSE COMMAND SHIPPED; THE JUDGE IS CLAUDE AGAIN** (D-630, D-631, #549, #551).

**Primary:** the six days of uncommitted work the primary carried (the Codex judge transport, the eligibility filter, the
records for runs 534–539 and D-621 to D-628) are committed as #549, byte-identical to the working copy. The apply-by-hand
decision is renumbered D-629. The primary is clean on `main`, apart from the untracked pilot doc and `.agents/skills/verify/`
(left alone on purpose). The exact pre-commit state is kept at `refs/backup/primary-wip-2026-10-11`. The viewer on 8799
runs from the primary again: Jobs to explore 395, Needs review 445, Apply by hand 98.

**Judge:** the owner has Claude access again, so `gate.model`/`effort` are back to `sonnet`/`medium` (D-631). The config
is byte-identical to `config.toml.bak-before-gpt-20261006`, with a fresh backup at
`config.toml.bak-before-claude-return-20261011`. The judge's exact headless call answered (`claude-sonnet-5-5`, no error)
before the switch. **Next run (2026-10-12 04:00) is the first Claude-judged run since 10-04: read its gate line**
(judged vs failed-open batches). GPT-era cached verdicts are not current for `sonnet` and are re-judged within
`refresh_budget`.

**Closing by the owner:** `boardwatch postings close --ids … --evidence … --apply` and `postings reopen` (D-630, #551). The
Job apps session's 28 hand-closed LinkedIn postings (2026-10-11 12:59 UTC; skips 381 → 353) first carried their `closed`
events under daily run 550. On the owner's call they were moved to run 551, a run of their own, with an evidence row each (D-632):
run 550's closed events went 11,314 → 11,286.

**Queue cleanup:** the 98 duplicate manual folders the Job apps session parked in its scratchpad were compared with
`_manual/` (377 identical files, 12 regenerated `details.json`, nothing unique) and deleted.

**Open:** the Codex transport stays in the code, unused. If it is selected again, fix two things first: it loads the owner's
`~/.codex/AGENTS.md` into the judge, and a timeout orphans the native `codex` process (#549 body). The adopt()/review-lane
follow-ups from the 2026-10-10 block stand.

### 2026-10-10 — **APPLY-BY-HAND (MANUAL) STATE SHIPPED AND SEEDED** (D-629, #547). Code change plus one live-store seed; no profile, rule or config change. Days 9+ (runs 534–550) were NOT read this session.

**What exists:** `queue.manual.<job_id>` in `app_state`; the `_manual/` drain; a fourth web lens, "Apply by hand"; batch routes
`POST /api/queue/manual` and `/unmanual`; per-lead routes `/api/queue/<id>/manual` and `/unmanual`. Precedence: applied >
skipped > reported > closed > manual > ineligible > lane_copy > review. Manual keeps its slate slot.

**Seeded (measured from the store, not from the script's output):** 105 posting ids, from Job apps' `autoapply/manual_apply.json`
(98) plus 7 leads its prep state routed as manual. 101 jobs marked: 98 standing and 3 closed. Not marked: 833120 (already
applied), and Vantive 808587, AAON 111453 and Dexcom 787619, which the owner had already skipped. Keys went 0 → 101; the manual
list went 0 → 98. Folders: `_manual` 0 → 98, top level 469 → 384, `_review` 450 → 437. `/api/queue` reads 384 / 437 / 98.
Run 550 (2026-10-11 04:00 tick, `ok`) left all three folder counts unchanged.

**Live viewer:** served from the primary checkout again since 2026-10-11 (see the 2026-10-11 block); the `bw-manual` worktree is removed.

**Handed off:** session `job-apps-8e` was told the routes and asked to move any other appropriate jobs into manual, including
anything added to `manual_apply.json` after ~22:10 CDT on 2026-10-10.

**Open:** Needs-review rows cannot be selected in the UI, so review leads move through the API. `adopt()` clears every
pending optimistic removal (follow-up). A "closed by owner" state waits on the owner's call. Artifact row 2964 (a scratch
`/private/tmp` path) is untouched; `boardwatch verify` was not run. This file is over 250 lines: the next session that reads
day 9 should move settled blocks out (blocked today by the uncommitted STATE edits on the primary).


### 2026-10-10 — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-10-13.** Run 539 failed B8 volume (D-628); runs 579/580 are read above (D-633).

### 2026-10-09c — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-10-13.** The Apply-first viewer filter, implemented and committed in #549.

### 2026-10-09b — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-10-13.** The GPT-era sol census, diagnostic only (D-627); superseded by the two-opus census above (D-633).

### 2026-10-09 — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-10-13.** Run 538 cleared volume, GPT precision pending (D-626).

### 2026-10-08 — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-10-09.** Run537 volume passes, GPT precision pending (D-625); run538 is read above.

### 2026-10-07 — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-10-08.** Run536 first scheduled GPT proof, failed B8 volume (D-624); run537 is read above.

### 2026-10-06b — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-10-13.** The GPT judge replacement (D-623); the judge is Claude again (D-631).

### 2026-10-06 — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-10-06b.** Run 535 fails B8 and judge health; historical day 10, streak zero (D-622). The owner-directed GPT replacement is above (D-623).

### 2026-10-05 — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-10-06.** Run 534 remains a failed historical day 9 (D-621); run 535 is now read and also fails (D-622). The access diagnosis and owner’s no-subscription confirmation still apply.

### 2026-10-04 — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-10-05.** Run 533 remains a failed historical day 8 (D-620); its judge failure is diagnosed and the next daily run is read (D-621).

### 2026-10-03 — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-10-04.** Day 7 read and PDFs repaired (D-619); its day-8 read is done, failed, and the backup call is ruled (D-620).

### 2026-10-02b — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-10-03.** Day 6 read as run 530 (D-618); its day-7 read is done (D-619) and the disk question is ruled (leave it).

### 2026-10-02 — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-10-03.** The web viewer redesigned around applying, merged (#541) and served (D-617); its rulings (a) and (b) are made — both keep what ships (D-619).

### 2026-10-01b — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-10-02b.** The viewer's lifecycle, triage, Rejected tab and stale/reuse check (#535–#538, D-616); its day-6 check is done (D-618) and T278–T280 are restated above.

### 2026-10-01 — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-10-02b.** Day 5 read as run 528 and the Uber/Sally Beauty re-render as manual run 529 (D-615); its day-6 read is done (D-618).

### 2026-09-30 — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-10-01.** Day 4 read as run 527, a same-day rerun after a macOS update killed run 526 (D-614); its day-5 read is done (D-615) and its open owner call is restated above.

### 2026-09-29b — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-10-05.** The SSD cutover and rollback cleanup are done (D-613, D-614); backups stay as-is (D-620). Current store checks remain in the latest block.

### 2026-09-29 — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-30.** T276's five out-root PDFs re-rendered (manual run 525, D-612) and the owner's keep-as-is ruling on item 7 and the gate backlog; its day-4 read is done (D-614).

### 2026-09-28f — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-30.** T275's 359 boards imported and day 3 (run 524) read (D-611); its day-4 read, T276 and owner calls 4–5 are done or ruled (D-612, D-614).

### 2026-09-28e — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-28f.** The PANW board watched and scanned by hand (run 490, scan-only), 32 résumés, the 308 + 83 backlog found (D-610); its day-3 read and T275 are done (D-611).

### 2026-09-28d — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-10-05.** T269/T270, T268 item 1 and T251 ship (D-609); the day-3 read is done. T268 items 2–4 and T272 remain held as recorded below.

### 2026-09-28c — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-28d.** The public docs refresh and v0.6.0 published (D-607); its T268–T270 step is done or ruled (D-609).

### 2026-09-28b — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-28f.** D-605's three rulings carried out before day 3 (D-606); day 3 read them: held-35 released 35/35, `slate_ceiling` 100 still all tier 0 (D-611).

### 2026-09-28 — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-28f.** Day 2 (run 489) and the #513 scan fix (D-604, D-605); day 3 confirmed #513 on the old fleet (D-611).

### 2026-09-27b — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-28b.** The viewer's out-root PDFs re-rendered (130, runs 487/488, D-603); its day-2 read is done (D-604).

### 2026-09-27 — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-28b.** Day 1 (run 486), the LinkedIn JD slice (#509) and jobright resolution (#510, D-602); its day-2 read, #510's effect and ruling 6's check are done (D-604), the 35 held captures repaired (D-606), and D-601's follow-up list filed as T266/T267.

### 2026-09-26c — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-10-13.** The new-grad never-missed ruling and four PRs before day 1 (D-601). Live config: `slate_ceiling` 100, `gate.backlog_budget` 150 (D-612).

### 2026-09-26b — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-10-13.** The count restarted net-new (D-600); the drain re-closed; the opus census closed at 7/125. Its `day_row.py`/`b4_audit.py` usage is restated above.

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

0. **The 35 held `linkedin:jobapps:*` LinkedIn captures** (D-602; ByteDance Graduate, NetApp Emerging Talent ×2, Skillstorm
   Entry Level among them): days 1 and 2 released 0. **RULED 2026-09-28 12:26 (D-605); DONE 2026-09-28b (D-606); day 3 released 35/35 (D-611).** The
   one-time ADDITIVE repair (append the
   sliced JD as a new version through `store/body_revision.record_body_revision`, the `postings reparse-bodies` path; the
   drain then releases them) — 35 postings, 17 distinct JDs, all slice to a body the
   detector passes; the LinkedIn lane has never written a second version for any of its 2,942 job-apps postings. A live-store
   write, not an eligibility change. Measure: `.agent/2026-09-28-session/held35_measure.py`.
1. **The v0.6.0 PyPI publish** (T255) — **RULED 2026-09-28 14:51 and DONE 2026-09-28c (D-607)**: published after the docs refresh.
2. **Puerto Rico for a USA-target profile** (T253 d) — measured 2026-09-25: PR locations resolve `unknown`, fail open and
   ARE delivered (5 built, HPE graduate roles). Default while unruled: keep them. Excluding them is profile data and restarts the count.
3. **dominos** (SmartRecruiters; 2,271 open after run 478, 0 ever delivered, 2 software-ish titles; holds the shared SR
   host up to the 1800 s cap) — keep, facet-slice, per-board cap, or unwatch; recommendation: unwatch.
4. **The résumé formatting session** — Mit's to schedule; résumé calls (1) and (2) were dropped (D-594).
5. **How job-apps summary leads count in the B8 census** — closed census: short bodies 0/38, long 7/87 (a short reading is
   a floor). Default until ruled: counted, with the split reported beside the pooled number.
6. **When to fix T258** (graduation-window wording; 52 open postings) — an eligibility change, so it restarts the count.
7. **Tier 0 vs judge-cleared leads** (D-604) — **RULED 2026-09-28 12:26 (D-605); DONE 2026-09-28b (D-606): the live `slate_ceiling` is 100.** **OPEN AGAIN after day 3 (D-611): all 59 leads were tier 0 and buried-open rose 116 → 131 — 100 did not let a judge-cleared lead in, and T275's boards add tier-0 postings. The remaining options are ranking changes (reserve slots) or keeping it.** **RULED AGAIN 2026-09-29 15:56 (D-612): keep as is through day 14 — `slate_ceiling` 100, `backlog_budget` 150; after the 10-10 run, T277 (audit, then a ~10-slot tier-1 reserve, then a larger backlog budget).** Tier 0 fills all 80 ranked places, so 116 judge-cleared open roles wait (growing
   ~46 a day). Options: raise `slate_ceiling` 80 → 100 (config only; tier 0 stays first, up to ~20 judge-cleared a day
   behind it; the judge sees up to 100 a run) — **recommended**; reserve slots within 80 (ranking code); or keep as is.
   The ruling did not address the count separately; D-598 r5's restart list (eligibility, profile, résumé gate) does not name it.
8. **The gate refresh's poisoned batch** (D-604) — **RULED 2026-09-28 12:26 (D-605): fix after day 14 — filed as T265 (D-606).** Posting 29849 fails its
   batch of 13 every run
   (fail-open, so the cost is 12 stale readings, not lost jobs). Candidate fixes, none built: isolate a failed batch by
   re-sending its items singly; read one fenced array out of a response that carries prose around it; withhold a body
   carrying AI-directed text. Any of them changes the final gate, which restarts the count.
9. **When T268 merges** (D-608) — **RULED 2026-09-28 18:42 (D-609): split.** Item 1 shipped (#524). Items 2–3 wait until
   after the 2026-10-10 run and need a redesign first (T268's status block). Item 4 is option A (`top` records only with
   `--record`), built after day 14.

## Open questions and carried gaps (settled guidance is in `STANDING-FACTS.md`)

- **v2, parked on purpose (D-598 r4):** field-dependent eligibility as data (a non-software user still needs code —
  `eligibility/catalog.py` lists `career_fields: [software]`), a real second user, public release and community launch.
- **Location still fails open on `unknown`** (T253): 241 open Workday rows stay `unknown`, 271411 among them; country catalog
  gaps (Türkiye, Nicaragua); some US towns misread as non-US. Watch for it in the census; fix only from a delivered lead.
- **The standing apply queue** can hold leads released after a re-key until the 130/run refresh reaches them (321 pending
  after run 480). It is not the B8 population (D-598 r6) but it is what the owner reads.
- **Windows:** T251 shipped test-only (#525), and Windows CI on its branch was green on 3.11/3.12/3.13; the production bugs it found are T272. Read a Windows result by test name, never by colour.
- **The primary checkout IS the daily run's code** (editable venv): park it on `main`, never pull while a run is active
  (`ps -Ao args | grep -Eq '(^|/)boardwatch run '`).
- **Citi sits at ~13% coverage permanently** (Workday's 2,000 cap; facet sum 4,589) — input-side, no bar.
- **The run clock moves to fit the work** (D-597): prepone = `launchctl kickstart gui/$(id -u)/com.boardwatch.run`;
  postpone = `disable` before the tick, kickstart, `enable` — never leave it disabled.
