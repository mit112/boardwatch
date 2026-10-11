> **2026-10-06: GPT replacement authorized (D-623).** The scheduled judge uses Codex/ChatGPT,
> `codex:gpt-6.1-sol` at high effort. Claude is not expected back before October 23 (tentative).
> Live-store recovery remains separately owner-gated; run539 fails volume, with GPT precision still pending (D-628).

# PROGRAM STATE — read this first

> **2026-10-05: no Claude subscription is currently active (owner confirmation, D-621).**
> The retained judge sessions report `oauth_org_not_allowed`; the older October 1 seat note below is historical.
> Authentication changes, new model calls and live-store recovery still require the owner’s go-ahead.

> **2026-10-01: the enterprise seat ended; one Claude subscription now.** The gate judge runs on the personal
> login: `gate.claude_config_dir` is unset in `config.toml` and the launchd plist no longer sets
> `CLAUDE_CONFIG_DIR` (`~/.claude-boardwatch` archived as `~/.claude-boardwatch.retired-2026-10-01`). Every
> "enterprise seat" / "executors on the seat" line in this file or the logs is history. Headless fan-out
> now spends Mit's only window and needs his go-ahead.

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
> this file's old standing sections (five of their claims had gone stale — D-598). The twenty-third, **2026-09-26**, moved the 2026-09-25b block WHOLE once its day-1 read and opus census were done. The twenty-fourth, **2026-09-26b**, moved the 2026-09-26 block WHOLE once its day-2 read and census close were done. The twenty-fifth, **2026-09-28b**, moved the 2026-09-27b and 2026-09-27 blocks WHOLE once their day-2 read, #510 check, ruling-6 check and held-capture repair were done. The twenty-sixth, **2026-09-28d**, moved the 2026-09-28c block WHOLE once its T268–T270 step was done or ruled. The twenty-seventh, **2026-09-28f**, moved the 2026-09-28e, 2026-09-28b and 2026-09-28 blocks WHOLE once day 3 was read. The twenty-eighth, **2026-09-30**, moved the 2026-09-29 and 2026-09-28f blocks WHOLE once day 4 was read. The twenty-ninth, **2026-10-01**, moved the 2026-09-30 block WHOLE once day 5 was read. The thirtieth, **2026-10-02b**, moved the 2026-10-01b and 2026-10-01 blocks WHOLE once day 6 was read. The thirty-first, **2026-10-03**, moved the 2026-10-02b and 2026-10-02 blocks WHOLE once day 7 was read and the two viewer rulings were made. The thirty-second, **2026-10-04**, moved the 2026-10-03 block WHOLE once day 8 was read and the backup call was ruled. The nineteenth, **2026-09-23b**, moved the 2026-09-23, 2026-09-22f and 2026-09-22c blocks
> WHOLE once run 471 was read and the pull to `de7ae153` done; the 22e block stays until run 472 is read. **Nothing has
> been deleted on any pass.** Do not narrate a decision here that `DECISIONS.md` already holds — cite its number
> instead. **If this file passes ~250 lines again, the
> fix is to move settled blocks out, not to summarise them away.**

---

## Current standing

### 2026-10-10 — **APPLY-BY-HAND (MANUAL) STATE SHIPPED AND SEEDED** (D-629, #547). Code change plus one live-store seed; no profile, rule or config change. Days 9+ (runs 534–550) were NOT read this session.

**What exists:** `queue.manual.<job_id>` in `app_state`; the `_manual/` drain; a fourth web lens, "Apply by hand"; batch routes
`POST /api/queue/manual` and `/unmanual`; per-lead routes `/api/queue/<id>/manual` and `/unmanual`. Precedence: applied >
skipped > reported > closed > manual > ineligible > lane_copy > review. Manual keeps its slate slot.

**Seeded (measured from the store, not from the script's output):** 105 posting ids, from Job apps' `autoapply/manual_apply.json`
(98) plus 7 leads its prep state routed as manual. 101 jobs marked: 98 standing and 3 closed. Not marked: 833120 (already
applied), and Vantive 808587, AAON 111453 and Dexcom 787619, which the owner had already skipped. Keys went 0 → 101; the manual
list went 0 → 98. Folders: `_manual` 0 → 98, top level 469 → 384, `_review` 450 → 437. `/api/queue` reads 384 / 437 / 98.
Run 550 (2026-10-11 04:00 tick, `ok`) left all three folder counts unchanged.

**Live viewer:** port 8799 is served from the worktree `../bw-manual` (pid 80427), not from the primary checkout. The primary is
still on 38d6fea2 with **23 dirty entries owned by another session**: a staged eligibility filter in `QueueToolbar` /
`QueuePage` / the bundle, `codex_gate.py`, and STATE / DECISIONS / STANDING-FACTS edits. They conflict with #547's files, so
the primary could not be pulled without touching that work. **Next:** the owner of that work commits or parks it, then
`git pull` on the primary, then restart the viewer from the primary and remove the `bw-manual` worktree.

**Handed off:** session `job-apps-8e` was told the routes and asked to move any other appropriate jobs into manual, including
anything added to `manual_apply.json` after ~22:10 CDT on 2026-10-10.

**Open:** Needs-review rows cannot be selected in the UI, so review leads move through the API. `adopt()` clears every
pending optimistic removal (follow-up). A "closed by owner" state waits on the owner's call. Artifact row 2964 (a scratch
`/private/tmp` path) is untouched; `boardwatch verify` was not run. This file is over 250 lines: the next session that reads
day 9 should move settled blocks out (blocked today by the uncommitted STATE edits on the primary).


### 2026-10-10 — **B8 DAILY VOLUME FAILS; GPT PRECISION STILL UNCERTIFIED** (D-628). Scheduled run539 read against538.

Historical day **14** delivers **24 net-new leads**, **19 net-new apply** (<20),19/19 one-page
PDFs,0 tailor_failed. `day_row.py` exits1 solely on B8 volume; B1–B3 and B5–B7 pass,
0 work-auth abstain on13,939. Independent B4:321 bullets and817 skills across19 PDFs,
0 unmatched; real/fabricated controls discriminate. This is NOT product completion:
certified streak **0**,14 consecutive frozen daily runs still required,no completion date.
All dated work holds remain unchanged; calendar day14 does not discharge them.

**Judging:** main30 (20 E/8 I/2 U),refresh130 (108 E/3 I/19 U),backlog150 (138 E/2 I/10 U).
Independent310 persisted codex-agent rows (266 E/13 I/31 U),all effort high; main ranks present,
refresh/backlog separated by persisted order and recorded budgets. Fresh ledger boundary3483173
follows run538 id3483172. No failed-open,missing/refused or breaker skips;two readings absent.
Refresh130/650,520 pending (538:654);backlog7,359 candidates. No extra model calls.

**Standing coverage:** API677 apply/626 PDFs/51 unavailable,450 review;physical677 open
folders/628 one-page PDFs/49 missing (538:577/531/46). Posting-ID sets agree;Humana215454/
204689 remain the two physical/API disagreements from out-root stored paths. API383 judge-
eligible/1 uncertain/293 unjudged;13.72s. Three already-applied jobs,31 cross-host/82 loose
redundancies are standing diagnostics. No queue repair,recovery,render or ledger drain.

**Controls:** buried204 current-key open/8 cumulative closed/17 stale open/14 stale closed
(538:150/1/96/14). Seven newly closed undelivered current-cleared postings624708,675473,
696393,696432,698711,723622,723655 independently have no job disposition;prior closed
controls remain closed without disposition. Held9/9 jobapps+35/35 LinkedIn released,1 Oracle
held. Deadline3 vs3. Boards3,130 attempted,2,465 complete/566 unchanged/75 partial/24 failed.
Scan6,891/6,725s;eligibility1,092/1,093;gate407/454;tailor4,162/4,964 (19/24 PDFs).
DB09:00:06–12:40:44 UTC;funnel13:14:49 (~34min reporting). No scheduled process at arrival;
launchd exited0,04:00 tick loaded. DB finish is not process completion. No current-run
WalUnsafe/locked/Traceback/refresh failure or config-dir DB;boot13.34GiB,SSD296.09GiB free.
D-620 same-SSD backup ruling unchanged. Viewer absent;restored loopback8799,PID61499,
existing token kept internal. All prerequisites present;prior dirty work and linked worktrees preserved.

**Precision:** today’s19 frozen pre-finish version bodies retained without judging;84 distinct
scheduled placements accumulated,16 more needed for n100. D-627 remains65 judged,diagnostic
only;four unresolved readings and two single-read flags unchanged. Two independent opus judges
or an explicit owner methodology ruling still required;additional calls need fresh authorization.
No production/config/profile/policy/auth changes,pull,commit or publication. Evidence:
`.agent/2026-10-10-daily/`;full gate `check.log`/`check.exit` there.
**Next:** read next actual scheduled run against539 with the same independent checks;do not
start a manual run or treat the census,calendar date or volume alone as acceptance.

### 2026-10-09c — APPLY FIRST VIEWER FILTER IMPLEMENTED LOCALLY.

Owner clarified eligible-only as the jobs to apply to first: both checks eligible and no known
negatives. The visible Eligibility → Apply first control requires both affirmative readings,
an open posting, prepared PDF and usable application link; excludes review holds, off-target/
thin descriptions, seniority flags and already-applied identical descriptions. Existing sort
and filters compose; reload and saved-view persistence work. Built bundle updated locally.
Isolated real viewer: 5→1→5 rows, reload retained filter, no overflow at 375/640/1280 px;
light/dark labels, focus and targets pass. Full `make check` exit 0: 351 web tests,
12,906 pytest passed / 4 xfailed, 95.28% coverage. Evidence `.agent/apply-first-*`;
final session-close gate `.agent/apply-first-check-close.log` / `.exit`.
No live-store/config change, model call, commit or publication; dated program holds remain.

### 2026-10-09b — **FRESH SOL CENSUS: DIAGNOSTIC ONLY; B8 STILL PENDING** (D-627).

Owner-authorized GPT-era census of65 frozen run536/537/538 apply placements: **2/65 unapplyable=3.1%
(Wilson95 0.8–10.5)**,per-run2/14,0/27,0/24. Sol high arms38/39,12 shared,12/12 agreement;
both flags single-read. Four additional uncertain placements remain unresolved,never cleared.
Short0/1,long2/64;net-new daily volume separately12/26/24. Owner directed sol,initial astra outputs excluded.
Same model as production means blind repeat-session evidence,not model independence. Existing **two opus
judges and n>=100** still unmet (35 more unique placements minimum);no acceptance-definition ruling.
Certified streak **0**,14 consecutive frozen daily runs,no completion date,all dated holds unchanged.
No production/queue/config/auth changes. Evidence `.agent/2026-10-09-gpt-census/REPORT.md`;
full gate `check.log`/`check.exit` there. Next census step: retain frozen inputs,accumulate actual scheduled
placements to n>=100,and obtain required independent judging or an explicit owner methodology ruling.

### 2026-10-09 — **DAILY VOLUME AND PDF CHECKS PASS; GPT PRECISION STILL PENDING** (D-626). Scheduled run538 read against537.

Historical day **13**: **29 net-new leads** of30 delivered, **24 net-new apply**,24/24 one-page
PDFs,0 tailor_failed. `day_row.py` exits0; B5–B7 pass,0 work-auth abstain on13,818.
Independent B4:403 bullets across24 PDFs,0 unmatched;1,032 skills sourced; real/fabricated
controls discriminate. GPT precision has no fresh census: certified qualifying streak **0**,
14 consecutive frozen daily runs still required, no completion date or relaxed dated work holds.

**Judging:** main37 (24 E/9 I/4 U),0 failed-open/missing/refused,cached0,two readings absent.
Refresh130/784,654 pending (537:792); arithmetic108 E/5 I/17 U. Backlog150/150 (143 E/0 I/7 U),
7,427 candidates,0 failures/breaker skips. Independent317 GPT ledger rows (275 E/14 I/28 U),
sampled effort high. Fresh run538 boundary id3457596 follows run537 id3457595. No new model calls.

**Standing coverage remains incomplete:** API577 apply/529 PDFs/48 unavailable,533 review;
physical577 open folders/531 one-page PDFs/46 missing (537:478/436/42). Posting-ID sets agree;
two PDF availability disagreements: Humana215454 and204689 have physical PDFs, but stored
PDF paths are outside the applications root and the viewer refuses them. API279 judge-eligible/
1 uncertain/297 unjudged;16.00s. Two already-applied jobs,26 cross-host/72 loose redundancies
are standing diagnostics, not fresh per-run dedup findings. No recovery or PDF render performed.

**Controls:** buried150 current-key open/1 current-key closed/96 stale open/14 stale closed
(537:112/0/136/12). Current-cleared693005 and stale-cleared605485/652127 closed undelivered;
independent left joins find no job disposition.603524/669977 remain closed. Held9/9 jobapps+
35/35 LinkedIn released,1 Oracle held. Deadline3 vs5. Boards3,091 attempted,2,253 complete/
733 unchanged/83 partial/22 failed. Scan6,725/7,083s;eligibility1,093/1,618;gate454/420;
tailor4,964/5,927 (24/27 PDFs). DB09:00:05–12:51:15 UTC;funnel13:23:22 (~32min reporting).
No scheduled process visible at arrival: process completion is bounded by arrival, not DB finish.
No current-run WalUnsafe/locked/Traceback/refresh failure or config-dir DB;boot16.53GiB,
SSD296.60GiB free. D-620's same-SSD store/newest-backup ruling remains unchanged.

Viewer absent on arrival; restored loopback8799,PID64635; no token output or authentication change.
Prior dirty adapter/docs/tests,owner paths and both worktrees preserved;no pull/commit/publication.
Evidence and full gate log/real exit: `.agent/2026-10-09-daily/check.log` and `check.exit`.
**Next:** read next actual scheduled run against538 with the same main/refresh/backlog,net-new,
independent B4,API/physical,buried/held/deadline,reporting and store-health checks. GPT census,
manual recovery/render and ledger drains remain separately owner-gated. Keep all dated work holds.

### 2026-10-08 — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-10-09.** Run537 volume passes, GPT precision pending (D-625); run538 is read above.

### 2026-10-07 — **SETTLED, moved WHOLE to `STANDING-FACTS.md` on 2026-10-08.** Run536 first scheduled GPT proof, failed B8 volume (D-624); run537 is read above.

### 2026-10-06b — **THE SCHEDULED JUDGE NOW USES GPT THROUGH THE EXISTING CHATGPT LOGIN** (D-623). Owner-directed model replacement; local code and config changed, no live-store re-judge or rerun.

**Owner:** Claude access is most likely unavailable until **October 23** (tentative). Use GPT models;
the owner selected **existing Codex/ChatGPT login**, not API credentials. No automatic switch-back is
scheduled. The original October-1 enterprise-seat notes above remain historical and verbatim.

**Implemented locally:** `gate.model = "codex:gpt-6.1-sol"`, `gate.effort = "high"` replace `sonnet` /
`medium`; all other controls unchanged (batch 13, timeout 300 s, depth 150, refresh 130, backlog 150,
seniority hold on). Config backup: `config.toml.bak-before-gpt-20261006` beside the live config.
The opt-in adapter uses isolated ephemeral `codex exec`, forces ChatGPT authentication, disables
coding context, tools, skills, plugins, hooks and memory, and reuses the existing verdict/evidence
checks and fail-open behavior. The full `codex:` name keys stored/cache readings; provider is
`codex-agent`. Claude remains the repository default. No schema, eligibility-policy, profile,
resume-gate or deterministic-engine change; no ledger drain. Changes are **uncommitted on primary**;
main's merged state remains the D-620 record. All prior dirty docs and owner paths are preserved.

**Evidence:** installed Codex 0.160.1; login also works in the launch job’s minimal environment;
loaded job points at this checkout, tick enabled. Twelve adversarial controls pass (all seven
hard-stop families, clean/preferred, missing facts, instruction injection), plus four full stored
JDs with fictional declared facts: two accepted hard stops with exact evidence, two clean entry
roles kept. Labels and engine verdicts were absent from model requests. This bounded smoke test
is **not a fresh B8 precision census**. Forty-seven targeted tests pass; bad transcript validation
fails five boundary tests under its null control. Final `make check` exits **0** after the migration
and index corrections: 349 web tests, 12,906 pytest passed / 4 xfailed, 95.28% coverage. Evidence:
`.agent/2026-10-06-gpt/check-final.log` and `check-final.exit`; session-close recheck is `check-close.*`.

**Cutover consequence:** viewer restarted with the new config on loopback 8799 (PID 94237).
Before the switch, API **638/638 PDFs**; after it, **310 apply / 300 PDFs**, **760 review** and all
310 apply readings unjudged under GPT. The model key makes Claude readings stale as designed:
The net apply count falls by 328; ten previously held PDF-less leads become visible. Physical
folders and PDFs were not changed. Missing-PDF posting ids are saved in the scratch evidence.
No stored verdict was rewritten or discarded. Recovery is **pending**, not complete; normal daily
refresh budgets now use GPT. A manual standing-queue recovery or PDF render still needs separate
owner authorization. Other LLM lanes are off, so the daily Claude dependency was this judge.

**Acceptance:** run 535 remains failed historical day 10 (D-622); qualifying streak **0**. No October-10
completion claim, threshold exception or relaxed freeze. A changed judge needs its own frozen-run
proof; the next scheduled run is the first live GPT reading, not an already-evidenced pass. Keep
the old closed precision census as historical evidence without extending it to GPT placements.
Read the next daily run against 535, checking main/refresh/backlog judging, apply volume, independent
B4, viewer PDF availability and held/buried controls. All existing dated work holds and the backup
ruling remain unchanged.

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
