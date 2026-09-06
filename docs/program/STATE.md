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

### Session 2026-09-06 (planning → the reset's SECOND config loss found and RESTORED; the apply lane blind-audited for B8): **the recovered config had also dropped `jsonld` + `indeed`, the seven LinkedIn hubs (33 combos/run), the caps `linkedin = 50` / `indeed = 50` and `pace_from_request_start`** — D-486 caught only the jobapps half, and runs 6–8 ran LinkedIn at the 10-company default. The last pre-reset `config.toml` was recovered VERBATIM from the transcript archive (2026-09-03T23:55Z) and restored 00:15 CDT on Mit's call ("before it"), read back through the loader; discovery only, the count holds. **Run 9 (06:00 CDT tick) is the first run on the restored five-lane config AND day 1 of the 14-day confirm.** Decision **D-487**; numbers in `METRICS.md`, `Session — 2026-09-06 · the pre-reset config…`.

**B8 measured for the first time (n = 128, the whole apply lane, two blind Sonnet passes, 40/40 inter-rater on the unapplyable axis): 22 of 128 UNAPPLYABLE = 17.2% against the ≤ 16% bar; 14.7% on the 95 gate-judged leads (runs 5–8), 24.2% on the 33 delivered before the judge existed; `jobapps:` targets 2.1% vs board fleet 26.2%.** Causes: six-family `ineligible` 10 (work_auth 4 — PayPal's "Visa Sponsorship … is not available … now or any time in the future" ×3; experience 5 — two U.S. Bank bars in WORDS, "Two to three years"), seniority 6 (Inferact "Member of Technical Staff" ×4), role 5 (Giant Eagle "Front End Lead" ×3), location 1. Report and key: `.agent/2026-09-06-audit/`. **The tier-0 headline is that same board: 46 of the 49 undelivered `eligible`+`swe` are Giant Eagle "Front End Lead Trainee" (`role_verdict` matches "Front End Lead"); tier 0 is drained and the slate already draws from tier 1 (1,644; 1,323 zero-row).** 46 of the 48 `jobapps:` apply leads were already promoted by job-apps itself — parity, not new reach.

### Session 2026-09-05d (jobapps lane audit → RE-ARMED; eligible count re-measured): **the `jobapps` lane had been UNARMED since the reset** — the recovered config was the 08-28 tuning, older than the 08-31 arming — so runs 2–5 ingested ZERO job-apps discovery (store: 0 tagged postings, 0 `jobapps` companies, 0 lane scans for it). Re-armed 19:15 CDT on Mit's call, BEFORE the 20:00 chain, with `resumes/` as the first root and a 96-link symlink staging root (`<data_dir>/jobapps-staging`, the D-423 vehicle) as the second, covering `APPLY_QUEUE`'s groups and every date's `_eligibility_review`: **1,460 direct-apply postings, 776 employers (692 new)**, cap override `unlimited`. Discovery only — `rules_hash`/`engine_version` untouched, the D-483 count holds. Decision **D-486**; numbers in `METRICS.md`.

**Live eligible, under run 5's identity (the last evaluated):** tier 0 (`eligible` + `swe`) **67 — 38 delivered, 29 undelivered**; tier 1 (`uncertain` + `swe`) 994, never folded in. **Under the code on `main` there are ZERO current verdicts until run 6 finishes re-evaluating** — T51 moved `engine_version`; `boardwatch web` reads every lead `unevaluated` until then. Five `Acme` test-fixture folders (06:59 CDT, pytest temp paths, `job_id 1` = a real posting) were removed from `~/boardwatch-queue`; apply lane is 40. **Owed:** the test path that reaches the real queue root (the conftest guard patches `pipeline.runner` only); after run 6, `track import "<home>/dev/Job apps/APPLY_QUEUE/_applied"` (25 records). **Do NOT re-point `jobapps_queue_dir` at `APPLY_QUEUE`** — Mit (19:35 CDT): `APPLY_QUEUE` is historical and no longer updates; `resumes/` is the daily feed and the lane already reads it directly. The open gap is FUTURE dates' `_eligibility_review` buckets (the staging links are static); a one-line link refresh in the launchd wrapper, outside the repo, is the proposed fix — owner's call tomorrow.

**READ AND CONFIRMED — runs 6, 7, 8 all `ok`, and the PROVISIONAL PASS IS MET (3 of 3).** The lane read 3,071 and resolved **1,460** on every run, admitting **682** companies on run 6 and **0** on runs 7 and 8 — the convergence a drained one-time harvest produces. Store: 1,460 tagged postings under 770 employers, 251 converged onto real boards. The judge worked on all three (40/39/38 judged, 0 batches failed open) and now REJECTS (6 on run 7, 11 on run 8). **Run 6 reconciled every stage — projection, tailor and PDF all 40 of 40, and 40 of 40 leads were software** (run 5: 9 PDFs of 30, and 20 of 30 non-software). Apply lane **128**, of which **48 carry a `jobapps:` board target** (TikTok, Apple, IBM, Google DeepMind, Toyota, Disney, Marriott, KLA, Garmin, PayPal). **End-of-line eligible: 189 (`eligible` + `swe`), 49 undelivered**; tier 1 `uncertain`+`swe` 1,644, never folded in. Numbers: `METRICS.md`, `Session — 2026-09-05 (later)`.

### Session 2026-09-05c (web viewer audit → fixed and SHIPPED): 25 findings from a browser-and-code audit of `boardwatch web`, all 25 closed by FOUR headless Opus executors on the enterprise seat (T56–T59, 30 commits, ~$35, 26 min wall) plus five integration commits; gated green on `web-audit` (9,586 passed), merged to `main` as `3df9ce1f`, **CI green after `e43b7caa`** (the docs push first went red on a quoted test address — D-485 records it). Decision: **D-485**. Nothing here touches eligibility, `rules.yaml`, `engine_version` or `delivery/queue.py`, so the count and the 20:00 chain are unaffected.

**What the owner sees now:** every page time in local zone (was +5h); a failed run's reason and the judge readout on the Runs page; a real undo after Mark applied; the review lane open by itself when the apply lane is empty, with a per-reason filter row and honest counts; the list keeps its columns beside the pane at 1440 and shows all eight at 2560; locations as a primary plus a count. **Owed from it:** `jurisdiction` still copies as a raw token (`us`); the badge's `REASONS` map and `lib/reviewReasons.ts` are held equal by a test, not an import; the ingest-side paragraph-boundary preservation the audit assumed turned out unnecessary (the frozen body carries newlines).

**The enterprise seat's OAuth session EXPIRED at ~17:04 CDT and was re-logged by Mit at 17:08.** The launchd judge uses the same config dir, so if it lapses again before 20:00 the chained runs' gate fails. Pre-run check: `CLAUDE_CONFIG_DIR=$HOME/.claude-boardwatch claude -p --model opus --output-format json --max-turns 1 "reply ok"` → `is_error: false`.

### Session 2026-09-05 (review + closure + run 5): the 09-09 execution REVIEWED and HOLDS; run 4 DISQUALIFIED; Track 1 CLOSED and the threshold STRUCTURE set; T49 shipped; the zero-row class MEASURED. Then **run 5 — the first launchd run on the armed configuration — FAILED (exit 1) while the judge WORKED for the first time**, exposing two defects in T42/T45's integration, both fixed (T54, T55). **The count starts at run 6.** Runs 6, 7, 8 are chained back to back on the owner's instruction.

**Read this before acting.** Decision: **D-482** (the rulings, the measurement, and three
corrections to D-481). Numbers: `METRICS.md`, `Session — 2026-09-05 · review`. D-481 and
`REPORT-2026-09-09.md` stand except where D-482 corrects them.

**Live configuration — unchanged since D-481, re-verified through a second path:**
`near_miss_years_ceilings: {"experience_years": 1}`, six families `blocker`, `rules_hash`
`033ea489f254`, `engine_version` `1+8c8694b96ca8`, `[gate]` enabled / haiku / expanded
`claude_config_dir` — now readable with `boardwatch config show` (T49). The launchd job is loaded
with a PATH that reaches `claude`, and reads **`runs = 0`**: nothing has run under it yet.

**THE TICK FIRES 06:00 CDT UNTIL A REBOOT.** launchd started 2026-09-03 23:43, the zone was set
to Chicago at 23:48, and launchd keeps its boot zone; run 1 fired 06:00:05 CDT on 09-04. D-481's
"04:00" was wrong; `STANDING-FACTS.md` had it right. Today's 06:00 was missed ON PURPOSE: the job
was booted out at 05:47 on Mit's request so T47 could land first (D-480 D2) and reloaded ~09:05.
**No run in this store has been tick-fired on a valid configuration** — run 1 tick-fired and
failed in 25 ms on the projection stamp; runs 2, 3 and 4 were launched by hand. The PATH fix, the
armed judge and the fence parser are all unexercised under launchd until **run 5 at 06:00 CDT on
2026-09-06**. Read three things when it lands: `runs = 1` in `launchctl print`, a fresh
`boardwatch-run.log` mtime, and `judged > 0` in the gate block. All three ⇒ run 5 is day 1 of 3.

**Owner rulings 2026-09-05 11:20–11:45 CDT (D-482) — none is to be re-asked:**
1. Run 4's 40 unjudged leads are **NOT re-judged**. There is no shipped path to them: fail-open
   wrote no gate row, and `built` retires a lead from every later slate; `gate request` ranks the
   OPEN shortlist. The handoff's "~$0.35" priced a mechanism that does not exist.
2. **Run 4 does NOT count** toward the provisional pass — judge inert, hand-launched, and T50
   changed the eligibility gate after it. The count starts at run 5.
3. **LinkedIn Track 1 is CLOSED: accept the loss** (D-453's own recommendation).
4. **Per-source thresholds, STRUCTURE now:** employer-board sources ≥ 85% independent recall;
   LinkedIn carries no bar. The **Indeed and hiring.cafe numbers are set at the first post-reset
   reading (~2026-09-17)**, when the 14-day window exists again.

**The zero-row class (M3's "no requirement rows") is MEASURED, not touched.** 33 of 120 delivered
leads had zero requirement rows — runs 2 and 3 only; **run 4 delivered none**, because T45's
verdict tiering put 40 `eligible` leads ahead of every `uncertain` one. Population: **32,602 of
96,266** current evaluations (33.9%) have zero rows, all `uncertain`, so none can reach the apply
lane. On a 2,000-posting random sample 49.0% carry a lexical requirement cue, "N years …
experience" phrasings 5.5% (~1,800 postings), degree words 34.8%. The years contexts are real
detection gaps: adjective-laden "0-1 years of professional software development experience",
en-dash/plus ranges "2–12+ years", "Experience Required: 3 to 5 years". **Rules are not touched —
that restarts the count.** Ticketed as **T51** for M3's window, corpus rows first.

**RUN 5 (D-483) — kickstarted under launchd 11:57 CDT, `runs = 1`, exit 1 after 59.3 min.** The
judge WORKED: 40 judged · 16 eligible · **10 ineligible** · 14 uncertain · 0 failed open · 241 s.
The PATH fix held. The FATAL was the cohort guard: a judge rejection was not a terminal state it
knew, so the 10 rejections read as "10 shortlisted candidates unaccounted". 30 leads were
delivered before the fatal (dispositions run 5 = 30 `built`), **20 of them non-software** — Urban
Park Ranger, Pediatric Pulmonologist, WM Affluent Associate — because T45's tier 0 was ANY
`eligible` verdict regardless of role; run 4 was already 14 of 40. Fixed on `main`:
- **T54** — a judge rejection is the fifth terminal state (`summary.gate_excluded_ids`), subtracted
  from the cohort and the render denominator; the gate test now seeds TWO postings and asserts
  `summary.fatal is None`, which it never did.
- **T55** — tier 0 requires role `swe` (both decided tiers do); an `eligible` lead with no role
  signal ranks in tier 2. **Taken in the owner's absence on the recommended option (no answer in
  300 s); CONFIRMED by Mit 13:43 CDT ("if you feel good about them, confirm"). A ranker change,
  not eligibility, so the freeze holds.**

**THE AFTERNOON (D-484): the first enterprise-executor fan-out, owner-approved 13:51 CDT.** Three
headless Opus executors on the enterprise seat (`CLAUDE_CONFIG_DIR=<home>/.claude-boardwatch`, one
worktree each) built **T52** (`review_reason` persisted in `details.json`, schema 2), **T53** (a
nested tier-1 admission budget for Indeed, keyed `"indeed.tier1"` in the overrides table — **INERT
until a value is set; owner to choose, 25/run recommended**) and **T51** (years detections widened:
`Yrs`, comma adjectives, new `labeled_years_minimum`, aside-owned hedges, an "18 years or older"
false rejection fixed). This session reviewed, re-ran, mutated and gated each sequentially. **T51
A/B on 4,000 pinned live postings:** 64 gain a row, 13 turn ineligible, every one quoting a real
bar; 3 false rejections removed; zero-row 1,373 → 1,361 (~0.9% of the class — D-482's 5.5% was an
upper bound). `engine_version` moved again; run 6 re-evaluates ~103k postings once. All three are on
`main` before the freeze. **Runs 6, 7, 8 are scheduled for 20:00 CDT** (owner: "so we dont waste
daylight"), kickstarted under launchd by a detached scheduler that waits out any gate.

**Next action.** Read run 9 (the first on the restored config): five `lane … →` lines, LinkedIn admitting up to 50, `indeed` and `jsonld` present, `judged > 0`, exit 0 — that is day 1 of the 14-day confirm. Then, in order: (1) the jobapps staging-link refresh (review bucket 48–164 records/day, ~half direct-apply; first loss is the 09-07 tick; **the plist has NO wrapper script**, so this is a wrapper or a second launchd job, Mit's call); (2) `"indeed.tier1"` (owner; live again now the lane is enabled, 25/run recommended); (3) `track import "<home>/dev/Job apps/APPLY_QUEUE/_applied"` (25 records, postings now exist); (4) the Giant Eagle role-gate false positive ("Front End Lead" at a grocery board) — a ranker/role-taxonomy fix, not eligibility, but check whether it moves any pinned hash before touching it; (5) the 31 `_review` leads held as `no_requirements_found` are real SWE titles worth Mit's eyes; the 40 `role_unconfirmed` are not. Mit's optional machine action: a reboot moves the
06:00 tick to 04:00 — not before the chain is done.

### Owed, and specifically NOT done

- **T51 SHIPPED (D-484) before the freeze.** Its residual: a hedged bar carrying a domain noun has no
  `*_preferred` sibling to land in and writes no row; a recall change for M3's window.
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

**0. THE ≤ 1-YoE FLOOR — RULED (D-478 §5), PLANNED (D-479), ALL DECISIONS TAKEN (D-480).** D1 = T47
(per-user policy data). D2 = floor first, then arm the judge, both before run 4. D3 = above-band
stays hidden, no ticket. Reach confirmed for 2–3 y total bars, scoped bars > 1 y and 13–36-month
bars; hedged/preferred bars do not move. Nothing here is still owner-gated; it is execution.

**0-1. RETIRED / ANSWERED — held WHOLE in `STANDING-FACTS.md`.** Gate 1 is PER-SOURCE RECALL (D-421)
and only the per-source THRESHOLD is still owed; job-apps keeps running until it is met
(`RETIREMENT-PLAN.md`); Indeed's posture is decided (D-410, re-scoped by D-450). **Do not
re-litigate 80%, do not re-derive "most", do not re-probe Indeed.**

1. **PER-SOURCE THRESHOLDS — STRUCTURE RULED (D-482):** employer-board sources ≥ 85% independent
   recall; LinkedIn no bar. **Owed: the Indeed and hiring.cafe numbers at the first post-reset
   reading (~2026-09-17)**, with D-450 on the page again. The instrument
   (`.agent/2026-09-02-session/per_source_recall.py`) still points at the OLD account home for
   job-apps' ledger — a one-line fix before it runs.
2. **TRACK 1 — CLOSED (D-482): accept the loss**, per D-453. Do not re-raise it from the 382 or
   the 113.
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
- **Provisional pass: MET — runs 6, 7, 8 all `ok` under launchd, 3 of 3 (D-483's count, discharged 2026-09-05).** 14-day confirm: day 1 = run 9 (2026-09-06 06:00 CDT), passive. **B8 first reading (D-487): 17.2% on n = 128, 14.7% gate-judged; bar ≤ 16%.**
  Not chased (D-351 item 2: work comes first), and every `rules_hash` bump restarts the count.

## Live blockers and carried gaps

| Item | Detail | Owner |
|---|---|---|
| **boardwatch sees 16.4% of job-apps' eligible yield — RE-DERIVED 2026-08-30, and the METHOD was wrong before** | **45 of 275 (16.4%)**, cohorts 08-23..08-29, on the **379-board fleet**. This replaces "10.1%, owed a check". It decomposes: fleet growth 344->379 gave 10.1 -> **13.8%**; adding an **exact ATS-slug key** alongside name matching gave 13.8 -> **16.4%**. **Name-only matching undercounts, so 7.7% and 10.1% are FLOORS** — boardwatch stores Micron as `Micron TDIT`, so the old method scored a watched company as unwatched; same for HPE/`Hewlett Packard Enterprise`, Cox/`Cox Automotive`, Disney/`Walt Disney Company`, Toyota, VIAVI. **The unreached 230 split: aggregator-only 60.7%, unsupported employer host 21.1%, board-addable just 1.8%** (5 postings in 7 days, 4 of them SmartRecruiters — the class D-370 declined on measured cost), so the cheap remainder is ONE Workday board (Motorola Solutions). **The gap is lanes, not boards.** Script: `.agent/2026-08-30-session/reach_v2.py`. Amazon/TikTok/Apple/ByteDance use none of the 6 ATS, so a slug cannot reach them. Closing it means a new discovery lane — GitHub new-grad lists are 19.1% of yield for ~5 public-repo GETs and are NOT the ToS trap the v2 decision was written about. **Reopens D-008** | **Mit** (reverses a shipped decision) |
| **Citi sits at 13.1% coverage, permanently** | Workday's `total` censors at 2,000; the facet sum (uncapped, control-verified) says 4,589. Our pager wraps at ~2,000 too, so post-drain Citi holds ~2,214 of 4,589 and nothing reports it | **Mit** (input-side) |
| **Run 9 (06:00 CDT 2026-09-06) is the first run on the RESTORED five-lane config (D-487) and day 1 of the 14-day confirm; runs 6–8 ran with `indeed`/`jsonld` off and LinkedIn capped at 10** | The launchd job invokes the **editable** venv at `boardwatch/.venv/bin/boardwatch`, so whatever branch that tree is parked on IS the unattended run's code and `rules.yaml`. **Park the primary checkout on `main` before ending every session**; a stray branch changes EVERY subsequent run. The tick fires **06:00 CDT until a reboot** — launchd keeps its boot zone, and the zone was set five minutes after the 09-03 boot — so a reboot moves it to 04:00. Verify a tick by `runs = N` in `launchctl print` and the log mtime, never by the run row alone: a hand run proves the code, only a tick proves the plist | **Mit** (reboot); every session (discipline) |
