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
> this file's old standing sections (five of their claims had gone stale — D-598). The twenty-third, **2026-09-26**, moved the 2026-09-25b block WHOLE once its day-1 read and opus census were done. The twenty-fourth, **2026-09-26b**, moved the 2026-09-26 block WHOLE once its day-2 read and census close were done. The twenty-fifth, **2026-09-28b**, moved the 2026-09-27b and 2026-09-27 blocks WHOLE once their day-2 read, #510 check, ruling-6 check and held-capture repair were done. The twenty-sixth, **2026-09-28d**, moved the 2026-09-28c block WHOLE once its T268–T270 step was done or ruled. The twenty-seventh, **2026-09-28f**, moved the 2026-09-28e, 2026-09-28b and 2026-09-28 blocks WHOLE once day 3 was read. The twenty-eighth, **2026-09-30**, moved the 2026-09-29 and 2026-09-28f blocks WHOLE once day 4 was read. The twenty-ninth, **2026-10-01**, moved the 2026-09-30 block WHOLE once day 5 was read. The nineteenth, **2026-09-23b**, moved the 2026-09-23, 2026-09-22f and 2026-09-22c blocks
> WHOLE once run 471 was read and the pull to `de7ae153` done; the 22e block stays until run 472 is read. **Nothing has
> been deleted on any pass.** Do not narrate a decision here that `DECISIONS.md` already holds — cite its number
> instead. **If this file passes ~250 lines again, the
> fix is to move settled blocks out, not to summarise them away.**

---

## Current standing

### 2026-10-02 — **THE WEB VIEWER IS REDESIGNED AROUND APPLYING — branch `viewer-workspace`, NOT merged, NOT pushed** (D-617). Delivery-side code only: no eligibility, ranking, résumé, discovery, config or live-store change; the pipeline never calls the changed read.

**Verify first:** `git log --oneline main..viewer-workspace` in `~/dev/projectY/bw-viewer` (a worktree; it has its own `.venv`, and `web/node_modules`
is a symlink to the primary's, excluded via the worktree's `info/exclude`). Nothing is pushed. The primary and the viewer on 8799 were not touched; the only
traffic to the live store was read-only (`mode=ro` reads and GETs).

**Done on the branch:** the Applied read was 101–108 s because SQLite scanned all 687k postings (no `sqlite_stat1`); it now drives from the applications,
rows identical, 0.06–0.07 s warm (in-process, live store, read-only — not measured over HTTP). The Runs "404" was run 529, a manual re-render with no funnel
artifact; the page falls back to the newest run that has one. The queue is task-first (Jobs to explore / Needs review / All jobs, a short summary instead of
sixteen counters, one honest note per row); status is four independent readings and unknown is "Check", never "Missing"; a workspace per job (what to check, the
résumé, answers, follow-up); an optional apply session; progress counted from the Applied ledger only after the server confirms (a failed write never counts).
The bundle is rebuilt and its manifest committed. Web: 349 vitest tests, `tsc` and `eslint` clean; detector 0 findings on 28 files; a fixture-data browser pass
(320–1440 px, 200 % zoom emulated, both themes) in two rounds. Gate: GATE_PENDING2

**Next, in order (all owner calls):**
1. Review, then merge `viewer-workspace` when you choose. Merging changes the code the daily run's editable venv imports; the pipeline does not call
   `applied_rows`, but time it away from the 04:00 run and read day 6 as usual.
2. **The viewer on :8799 still runs the old Python and bundle.** `/api/applied` stays slow (~106 s) until it is restarted on the merged code (stop it, then
   `(PYTHONUNBUFFERED=1 nohup .venv/bin/boardwatch web --no-open </dev/null > ~/Library/Logs/boardwatch-web.log 2>&1 &)`, never `--port 0`). The client now
   times out at 12 s and offers a retry, so a stale viewer degrades rather than blanks.
3. Rulings wanted: (a) key `a` records the focused row, including the one the cursor moved to after `s` skipped the previous job (Undo toast, 7 s) — keep or
   require the workspace to be open; (b) "this week" = the past 7 days, not Monday–Sunday; (c) offer Impeccable `init` so PRODUCT.md captures this surface.
4. Suggested usability comparison (not yet observed): time from opening Jobs to a recorded application, and the share of opened jobs that reach a record,
   old viewer vs this one, on the same fixture or isolated store with the same person; plus whether someone can say why a job is flagged.

**Not verified, so not claimed:** applications made, motivation or retention; any screen reader; real zoom; Safari, Firefox, touch; a slow device; long titles and
a missing location (fixtures have neither). Open cosmetic: one stat cell wraps alone at 1280. A `/verify` pass on the real viewer (isolated synthetic store, real bundle) found two defects the branch then fixed: the Runs page threw on a funnel file missing fields, and focus fell to `<body>` after a toast button was used; the sticky-pane band and the literal backticks in the empty Applied table were fixed with them.

### 2026-10-01b — **THE WEB VIEWER GAINS THE APPLICATION LIFECYCLE, TRIAGE ACCELERATORS, A REJECTED TAB, AND A STALE/REUSE CHECK** (#535–#538, D-616). Delivery-side code only: no eligibility, ranking, config or live-store change; the 2026-10-01 block's items below are unchanged.

**Verify first:** `git log --oneline -3 origin/main` (this correction on top of #539). The primary is on `main` at #539 or later,
pulled ~21:58 CDT on the owner's word; it still carries the owner's UNCOMMITTED `STATE.md`/`STANDING-FACTS.md` edits (the
enterprise-seat note, 15:55) — stash them around any pull (`git stash push -m <name> -- <the two files>`, pull, `git stash pop
<that ref>`; the stash list is shared across worktrees, so pop by ref). ONE viewer runs, on the new code: pid 3970, port **8799**
(the default; re-read with `lsof -nP -iTCP:8799 -sTCP:LISTEN`). Checked on the live store at close: `/api/version` bundle =
disk, `code_changed` false; `/api/rejected` 98 = the queue's `ineligible` 98 (0 gate-eligible, 0 disputed); `/api/applied` 268
total, 229 submitted, 0 responded, 18 quiet; apply lane 685/685 PDFs (review lane 50/382, unchanged by this work); a second
`boardwatch web` printed the running viewer's URL and exited 0.

**Done:** #535 Applied page — status select through `set_application_status` with undo, a History panel over `application_events`
with notes (new `note` event type; `_mark_sources` reads state events only), a server-decided "no reply" flag (still `applied`, no
event for 21 days), "responses N of M"; and the Applied table's header no longer covers its first row. #536 queue — "Did you
apply?" when the TAB returns after opening an apply page, "×N similar" + "Collapse similar roles", `c` / pane button to select a
company, follow-up presets, "Show in description" for evidence quotes, saved views (localStorage). #537 Rejected tab — `GET
/api/rejected` (one `_rejected` predicate shared with the queue's `ineligible` cell), gate-eligible first, "Why", apply anyway,
dispute flag `queue.disputed.<job_id>` (moves nothing; joins `queue_action_job_ids`). #538 — `GET /api/version` + a stale banner
(restart / Reload), and `boardwatch web` on a port held by this store's own viewer prints its URL (proved by `GET /api/hello`, an
HMAC over a nonce and the server's own address and store; the token is never sent). Each reviewed by GPT-6.1 Sol (review +
verification; #538 a third scoped round), every blocker fixed, `make check` exit 0 on each merged state.

**Next, in order:**
1. **DONE ~21:58 CDT on the owner's word:** primary pulled, both old viewers stopped, one started on 8799 with
   `(PYTHONUNBUFFERED=1 nohup .venv/bin/boardwatch web --no-open </dev/null > ~/Library/Logs/boardwatch-web.log 2>&1 &)` — never
   `--port 0`. **The 2026-10-02 04:00 run (day 6) is the first on this code**: its delivery-path changes are the shared `_rejected`
   predicate (equivalent) and the regroup set (empty until a dispute exists); read day 6 for any change in delivered / drained
   counts against run 528.
2. The 2026-10-01 block's items (day 6 read, then the post-day-14 list), unchanged.
3. Filed for after day 14: T278 (port hand-off after a probe), T279 (always-on viewer; needs T133), T280 (the below-the-cap view, an
   owner call).

### 2026-10-01 — **DAY 5 IS RUN 528, THE 04:00 TICK, AND IT MEETS EVERY BAR; THE FASTEST RUN OF THE 14 SO FAR (3 h 26 m); A SECOND OUT-ROOT PDF (SALLY BEAUTY) JOINS UBER; BOTH RE-RENDERED AS MANUAL RUN 529 ON THE OWNER'S WORD, THE VIEWER SERVES 707/707** (D-615). No code, profile, rule or config change; live-store writes only (manual run 529).

**Verify first:** `git log --oneline -3 origin/main` (this record on top of #530); the primary on `main`; no run active; the tick
**enabled**; the viewer alive (superseded: see the 2026-10-01b block — one viewer, port 8799). Read the
store at `/Volumes/mit/boardwatch/boardwatch.db` (D-613; the 2026-09-29b block below). Watched boards 2,754 before run 528.

**Done:** #530 had merged and the primary was already clean on it. Run **528** (04:00 tick) `ok`, 09:00:05 → 12:26:07 UTC.
**Day 5:** B1 36 · B2 32/32 · B3 one page · B4 0 on 32 · B5–B7 ok · B8 32 · gate 51 judged, 0 failed open. `stage_durations` vs run
527: scan 6,161 vs 10,643 s, eligibility 972 vs 1,419, tailor 4,606 vs 6,684 (32 vs 42 PDFs), gate 59 vs 59. Board-deadline hits
9 → 6, partial 125 → 83. No `WalUnsafe`, lock error, traceback or `gate refresh batch` failure in run 528's log section; no
`boardwatch.db` under the config dir. Daily checks: `inventory.py` 707 apply-lane, pdf missing 0; buried-open 165 → 187; held
captures 9/9 and 35/35 released (oraclehcm 1 held); disk 47 GiB free.

**Next, in order:**
1. **Read the 2026-10-02 04:00 run as DAY 6** (`python3 .agent/acceptance/day_row.py <id> 6`, `b4_audit.py --run <id>`, after its PID
   exits). "Previous ok run" will be 529, a render row (item 2); compare against 528 by hand. The daily checks above, unchanged.
2. **DONE 15:20 CDT on the owner's word (D-615):** Uber 110225 and Sally Beauty 110865 were re-rendered into the out-root as
   manual run **529** (`render_pending.py`, viewer stopped and restarted). `/api/queue` serves **707/707**. **`day_row.py` will name
   run 529 as day 6's "previous ok run"**: read the board-deadline comparison against run 528 by hand.
3. After the 2026-10-10 run: T277, T273, T274, T265, T268 items 2–4, T272.

### 2026-09-30 — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-10-01.** Day 4 read as run 527, a same-day rerun after a macOS update killed run 526 (D-614); its day-5 read is done (D-615) and its open owner call is restated above.

### 2026-09-29b — **THE LIVE STORE NOW LIVES ON THE OWNER'S EXTERNAL NVMe SSD (config `data_dir`); THE NIGHTLY RUN STARTS THROUGH A MOUNT GUARD** (D-613). No repo code change; machine-local config, launchd and a copied store. **The store is NOT under the config dir any more** — anything that read the old location (a probe, a scratch clone, a hand-typed `sqlite3` path) reads a STALE frozen copy.

**Verify first (adds to the block below):** `python -c "from boardwatch.core.settings import load_settings; print(load_settings().data_dir)"` prints the SSD path; **no `boardwatch.db*` exists under the config dir** (a file there means something re-created the old store); the SSD volume is mounted; the viewer's open handle is the SSD store (`lsof -p <pid> | grep boardwatch.db`).

**Done:** online backup → `quick_check` ok, 28/28 tables equal, same alembic head; `tailored/` and `projected/` copied byte-identical and the old paths left as **symlinks** (423 `artifacts.uri` rows point at the old `tailored/`; all resolve); config backed up; plist edited textually and reloaded; viewer restarted. The old store sits in a rollback folder under the config dir (its README says what to check) until **one clean run on the SSD store**; a one-shot reminder fires 2026-09-30 09:00.

**Next, in order (the 2026-09-29 block's items follow):**
1. **Day 4 (the 2026-09-30 04:00 run) is also the FIRST run on the SSD store.** **DONE 2026-09-30 (D-614): the 04:00 run (526) was killed by a reboot; the rerun, run 527, is the first clean SSD run.** Read it for that too: the run id is above 525 in the SSD store, the wrapper did not exit 75, the log has no `WalUnsafe`/lock errors, and **`stage_durations` against run 524 are the only measure of any speed change** (unmeasured). If it failed on the store, do NOT delete the rollback copy; reversal is the `config.toml.bak-…` and plist `.bak-…` beside the originals.
2. Only after a clean read: delete the rollback folder (~21 GB internal). **DONE 2026-09-30 19:27 (D-614): deleted, disk 52 GiB free.** Then re-take the disk-free number — it will step up ~21 GiB.
3. **Not armed:** the store and its newest full backup are on the same SSD. A backup to a different disk is an owner call; a manual `boardwatch` command with the SSD unmounted is unguarded (it would create an empty store on the boot disk).

### 2026-09-29 — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-30.** T276's five out-root PDFs re-rendered (manual run 525, D-612) and the owner's keep-as-is ruling on item 7 and the gate backlog; its day-4 read is done (D-614).

### 2026-09-28f — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-30.** T275's 359 boards imported and day 3 (run 524) read (D-611); its day-4 read, T276 and owner calls 4–5 are done or ruled (D-612, D-614).

### 2026-09-28e — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-28f.** The PANW board watched and scanned by hand (run 490, scan-only), 32 résumés, the 308 + 83 backlog found (D-610); its day-3 read and T275 are done (D-611).

### 2026-09-28d — **T269 AND T270 SHIP; T268 IS SPLIT — its one-refusal half ships, the rest waits for day 14 AND a redesign; T251 (Windows) ships test-only** (D-609). The owner ruled five calls at 18:42 ("go with your recommendations"). Nothing touched the live store, the config or a run. **Day 3 (the 2026-09-29 04:00 run) is UNREAD: its read is the next session's first job** — the 2026-09-28b block's items 1–4, unchanged.

**Verify first:** `git log --oneline -6 origin/main` (this record, T251 #525, T268a #524, #523 T269, #522 T270); the primary on
`main` at this record, with `git -C boardwatch pull --ff-only` only when no run is active (it is the daily run's code); no run active.

**Done:** #522 (T270: `config show` text, `config set lanes_enabled` check, the web-token mode, the Docker/CI warm-up that
now renders offline), #523 (T269), #524 (T268 item 1), #525 (T251). T271 (the text residuals) and T272 (T251's
Windows production bugs) filed. Branch `t268-resume-setup` (T268 items 2–3) is kept UNMERGED.

**Next:** (1) DONE 2026-09-28f — the day-3 read (D-611). (2) After the 2026-10-10 run: T268 items 2–3 **after redesign** (Codex found
two real defects in the owner-name check, see T268's status block), T268 item 4 as ruled (option A), T272, T265.
Worktrees `bw-t268`, `bw-t268a`, `bw-t269`, `bw-t270`, `bw-t251`, `bw-warmup`, `bw-record` are this session's; they are safe to remove once merged.

### 2026-09-28c — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-28d.** The public docs refresh and v0.6.0 published (D-607); its T268–T270 step is done or ruled (D-609).

### 2026-09-28b — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-28f.** D-605's three rulings carried out before day 3 (D-606); day 3 read them: held-35 released 35/35, `slate_ceiling` 100 still all tier 0 (D-611).

### 2026-09-28 — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-28f.** Day 2 (run 489) and the #513 scan fix (D-604, D-605); day 3 confirmed #513 on the old fleet (D-611).

### 2026-09-27b — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-28b.** The viewer's out-root PDFs re-rendered (130, runs 487/488, D-603); its day-2 read is done (D-604).

### 2026-09-27 — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-09-28b.** Day 1 (run 486), the LinkedIn JD slice (#509) and jobright resolution (#510, D-602); its day-2 read, #510's effect and ruling 6's check are done (D-604), the 35 held captures repaired (D-606), and D-601's follow-up list filed as T266/T267.

### 2026-09-26c — **A NEW-GRAD ROLE MUST NEVER BE MISSED (owner ruling) — four PRs merged before day 1, the frozen config set** (D-601). Measured on a read-only clone: 1,600 open postings titled new grad / early career, 81 ever delivered; **354 passed every filter and ranked at a median of ~2,955 behind the 40-lead slate**; 22 judge-cleared leads were stranded by an old judge key. Shipped (#504 #505 #506 #507, all before the 04:00 day-1 tick, owner-approved override of D-598's freeze): entry-level titles rank first for an entry profile (tier 0), role-gate misses, `slate_ceiling`, the buried-good-lead count + alert, entry markers v2 (title + JD body), job-apps' LinkedIn finds admitted, `gate.backlog_budget`, 251 false-ineligible verdicts released. **Live config: `slate_ceiling = 80`, `gate.backlog_budget = 150`** (backup `config.toml.bak-preslateceiling-20260926`).

**Verify first:** `git log --oneline -6 origin/main` (top: `523c067e`), the primary on `main`, `.agent/2026-09-26c-crash/followups.md`.

**Drain (manual `run --no-scan --project --top 150`, owner-approved):** run 483 delivered 118 (107 entry-marked; 21 apply
with PDF, 97 review), run 485 delivered 94 (55 apply, 39 review; 67 via LinkedIn). Blind two-opus audit of run 483: agreement
108/118; apply lane 1/21 unapplyable. Runs **482** (Mac crash mid-rank, 0 delivered) and **484** (interrupted in lanes) are
phantom `running` rows — inert, reaped by age. Batches 3–5 were skipped on the owner's word.

**Expect on day 1 (09-27 04:00):** a LONGER run — the new rules re-evaluate the corpus; the slate may grow past 40 (up to 80) with
tier 0-1 leads; the gate also judges up to 150 backlog postings after tailoring (fail-open, 2-failure breaker); the funnel carries a
`buried` section and a backlog block. The 26b block's next steps (read day 1 net-new with `day_row.py`) stand unchanged.

**Found, not fixed:** 473 open jobapps-lane postings (202 new-grad software) sit in the body quarantine with **no working exit**
(jobright paraphrases; the drain needs a new version that never comes). They reach `_review` unevaluated and unrendered.
395 of 450 jobright rows carry no employer URL (job-apps' resolver last ran 08-27). Both branches this block held are
merged — #509 and #510 (D-602); the resolver runs again from 09-27.

**Changed this session (live store / machine):** config.toml (+2 keys); runs 482–485; 212 queue folders; a 17 GB COW store clone
used for read-only measurement, deleted at close.

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
4. **T255 v0.6.0 — DONE 2026-09-28c (D-607).** Was: `release-0.6.0` (worktree `bw-t255`) HELD — rebase onto `main`, re-gate, merge and tag together on the
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
