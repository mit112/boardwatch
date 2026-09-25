# STANDING FACTS — what a fresh session should not re-derive

> Split out of `STATE.md` (D-139), which had grown to twice its stated length and was being read past.
> **`STATE.md` is still the read-first file**; this one is reference, read by section when you are about
> to touch the thing it describes.
>
> Claims only — the reasoning is in the cited decision, which is the point of the archive split. **Read
> the decision before changing the behaviour it describes.** If a fact here disagrees with the repo, the
> repo wins: fix this file and note the correction in `DECISIONS.md`.

| Section | Read it before |
|---|---|
| [Gates and process](#gates-and-process) | running a gate, committing, or dispatching an agent |
| [Gate A internals](#gate-a-internals) | touching `src/boardwatch/profile_bundle/` |
| [Liveness and the ledger](#liveness-and-the-ledger) | touching liveness, dedup, suppression or applied state |
| [The live store](#the-live-store) | anything that reads or migrates the real database |
| [Environment](#environment) | your first command in a new session |
| [Process lessons](#process-lessons-this-program-paid-real-time-for) | mutation testing, merging branches, reviewing |

---

## Gates and process

- **A docs-only commit owes `make generalization index-check`; anything else owes full `make check`** (D-116,
  resolving D-014). The boundary is the file extension, and `DATA_SUFFIXES` has **eleven** members —
  `.yaml .yml .json .jsonl .csv .tsv .toml .tex .typ .txt .mako`. `.md` is outside it; `.toml`, `.txt` and
  `.tex` are **not**, so they get no discount.
- **Two tests DO read the real `docs/` tree, and that is why the discount is sound** (correcting D-116's
  stated premise, which was "no test reads a `docs/` file" — D-140). `tests/generalization/test_real_tree.py`
  asserts `run(REPO_ROOT) == []`, and `tests/unit/test_program_index.py` runs the index checker with `cwd` at
  the repo root and asserts it exits 0. Each asserts **exactly** what one of the two owed commands asserts,
  so the short set is not a gap. **The discount breaks the day a test asserts something about a doc that
  `generalization` and `index-check` do not** — a link checker, a line-count cap, a spell check. Check for
  that before relying on it, rather than re-reading the premise.
- A doc in this program never quotes an exact catalog count, because no test can pin one and a stale number
  in a read-first file is worse than no number.
- **The gate runs in parallel and costs ~4½ minutes, not ~17** (D-150). `-n auto` is passed by
  `Makefile`'s `test:` target and `ci.yml`'s test job — **deliberately not in `addopts`**, because the
  `perf` job shares that config and measures wall-clock timings. `release.yml` inherits it through
  `make check`, which is intended. Two consequences worth knowing before reading a gate log: pytest is
  **~99% of the gate** (the other four phases cost about two seconds combined, so optimising them is
  worthless), and **xdist's summary drops the `1 deselected` tally** — reconcile counts against the
  `[N items]` figure instead. For a readable traceback while debugging, run serial with `-n 0`.
- **`make check` is the only gate for this repo's correctness** — pytest + ruff + mypy green is *not* green.
  Run it in a **detached worktree pinned to a sha**, capture the real exit code, never pipe it through
  `head`/`tail` (SIGPIPE gives a false negative — observed live giving a false `EXIT=0`), end a
  backgrounded gate with `exit $ec`. `All checks passed!` is the *lint* step and appears while pytest is
  still running; only `GATE_EXIT` and the pytest summary are the verdict.
- **A push run is 9 CI jobs, not 12** (D-151). Windows is off the per-push path: scheduled and
  `workflow_dispatch` runs get all three OSes, a push gets ubuntu + macOS, a PR ubuntu only. Any "all
  twelve green" claim in this program — including the Gate A one below — describes a *scheduled* run.
- **A contended gate produces FALSE failures, not merely slow ones.** Running `make check` beside a live
  subagent turned a green `main` **red** on three filesystem-timing-sensitive tests. A gate that ran under
  contention has produced no usable result — **re-run it alone before diagnosing anything it reported.**
  (§Process lessons records the other half: contention also stretches and SIGTERMs a gate. Slow is the
  visible symptom; a false red is the expensive one, because it sends you debugging code that is fine.)
- **Green locally ≠ green CI** (D-117), but the gap is **`gitleaks` and `perf` only**. `generalization` is
  inside `make check` and runs CI's exact command; the "three CI-only jobs" phrasing was wrong.
  `gitleaks git --log-opts=origin/main..HEAD` before a push is the cheap mitigation, not yet wired in.
- **`generalization` scans git-TRACKED files only** — it enumerates through `git ls-files`, so a new file
  that is not yet staged is invisible to it and a green gate says nothing about it. **`git add` before the
  gate run you intend to trust.**
- **Put the commit inside a guard that reads the check's exit code** — `if uv run ruff check . && uv run
  mypy --strict src tools; then git add <paths> && git commit …; fi`. Committing before reading an exit code
  shipped a `$HOME` path into a tracked file, a stale program index and a ruff failure, on three separate
  occasions in one session.
- **Re-check an agent's branch for late commits before gating.** A fix agent reported 10 commits after 9 had
  been merged; the gate was killed at 42% and restarted because the tree being gated was not the tree meant.
- **After appending to `DECISIONS.md`/`METRICS.md`, add the index row and run `make reindex`** — line numbers
  drift on any edit above a heading, and `make check` fails on a stale index (D-109).
- **The per-task fast-check set must include `test_store.py` and `test_schema_head.py`** for anything touching
  `tables.py`, a migration or the Alembic head (D-099). A new migration must bump the pinned head explicitly.
- **A violating fixture is assembled at runtime so the literal never exists on disk** (D-115, D-117) — for the
  generalization checker *and* `gitleaks`; both protect the repo's **bytes**. Never add a
  `HOME_PATH_EXCEPTIONS` row for a fixture: it excuses the string repo-wide and 31 shape tests assume those
  tables are empty. `.gitleaksignore` entries are fingerprint-pinned, excusing one blob rather than a pattern.
- **The tectonic pin has two homes and now a detector** — `Dockerfile`'s `ARG TECTONIC_VERSION` and the
  `setup-typesetting` action's default; `tests/unit/test_typesetting_pin.py` fails on drift (D-116).
- **`AGENTS.md` records no phase standing, test count or coverage figure, on purpose.** `STATE.md` is the only
  source of standing. `.agent/` and `.superpowers/` are gitignored working material; `CHANGELOG.md` is
  authoritative for what shipped. Review records that must outlive a session go in `.agent/`.
- **A finding's tier belongs to the OPERATION, not the code alone** (D-134). `tier_of()` is the catalog
  default; `outcome_with` reading `finding.tier` is correct. Every call-site override must carry a comment
  naming the operation-specific reason. `_TIER_RANK` is error 0, blocker 1, warning 2, information 3.

---


**GATE P4 IS MET — the owner blind craft review PASSED cleanly (2026-08-26).** Mit reviewed 13 anonymised
résumés (8 boardwatch + 5 job-apps decoys) rendered-page-only. All five he judged WORSE were job-apps decoys;
all three he judged BETTER were boardwatch (Perplexity/Anthropic/Figma); the other 5 boardwatch were on-par.
Both orphan-page-2 defects were decoys — the failure mode D-303's fill fix eliminated. **P4 objective half
(0 anti-slop violations) + subjective half both pass → P4 gate MET.** Assembler/key in
`.agent/2026-08-25-craft-findings/` (build_p4_blind_sample.py, p4_blind_key.md).

**SYSTEM PROVEN STABLE — 21 clean runs (92, 94–113), 1 failure (run 93, the pre-fix crash).** Corpus grew to
57,175 postings / 48,084 open; watched 140 (CMU's recurring-422 dead board removed as hygiene); 85 lane-
discovered companies recorded unwatched. 4 clean SCHEDULED ticks (92/95/101/108) + many clean manual runs; both
fixes hold every run; lanes healthy (no silent outage). Manual-run cadence was eased to scheduled-ticks-only at
session end to cut lane-leak accrual + conserve the rate-limit window. **The provisional pass (D-280) is
effectively met on quality** — P4 gate met, B1–B7 pass every run — but **the freeze is no longer stable:
D-319 moved `engine_version`, so the frozen-run count restarts from the first tick on `1+5bf77461f044`.

**FINISH-LINE INSTRUMENTATION BUILT (`.agent/2026-08-25-craft-findings/`, gitignored).** `finish_line_cert.py`
scores B1–B7 + freeze + P6 per run (validated on run 90: all PASS incl. independent pdfinfo 1-page; only
post_fill fails, correctly). B4 PASS + NON-VACUOUS (350 résumés / 3,426 bullets / 0 fabrications; negative
control catches drift+bogus-id). P4 objective checks (title-seniority / register / buzzword / requirement-echo
/ overmatch) 0 violations over delivered, non-vacuous (33 senior JDs stripped). **P6 leakage 0.00% over a FULL
7-day window** (ledger spans 08-19→08-26). B5 guard reviewed SOUND TO CERTIFY. **Remaining for provisional
pass: role fix live + 3 clean post-(fill+role) scheduled runs + the owner P4 blind review** (assembler ready:
`build_p4_blind_sample.py`, filters delivered by `e61a1956`).

**THE DAILY DRIVER IS FIXED AND THE CADENCE IS RAISED.** Run 70 (2026-08-23 08:00) died on a corpus-sized
`IN` list crossing SQLite's 32,766 bound-parameter cap at 32,771 open postings; six sites were over at
once. Fixed and merged (D-287). The launchd job now fires **eight times a day** — 02, 05, 08, 11, 14, 17,
20, 23 — instead of once (D-288).

**`runs` RESET TO 0 when the job was reloaded.** The pre-reload reading was `runs = 5, last exit code = 1`;
any absolute comparison against that number is void. The gate counts consecutive clean **ticks**, not
launchd invocations.

**GATE P3 IS MET — 20 CONSECUTIVE CLEAN SCHEDULED TICKS (runs 71-90), verified 2026-08-26.** All twenty carry
`runs.status='ok'` with `boards_attempted>0` at the scheduled 3h slots; run 70 (13:00 UTC 08-23) was the last
failure. **Verified from the live `runs` table + per-run funnels, not this file's count** — STATE lagged
because the job fires 8×/day and is written once per session. **7 required, 20 clean → MET.** Only a SCHEDULED
tick counts (`boards_attempted>0`) — a manual `run` and the phantom **run 91** (see below) move nothing; a
failed unattended run resets the streak.

**A BOUNDED PUBLIC-READINESS EFFORT SHIPPED AND `0.5.0` IS LIVE (D-299).** Scope was exactly three
workstreams — onboarding, README/ease-of-use, release currency — no feature expansion. `boardwatch guide`
and next-step CLI hints ship (PR #156); the README is compressed onto one canonical path with reference
depth moved into five linked guides (PR #156); a Windows-only nightly failure in the coverage-help test
was fixed test-only (PR #157); `0.5.0` is published to PyPI, GHCR, and a GitHub Release, verified with a
clean isolated install (PR #158) — the first release since `0.3.0`.

**PHASE 6 (COMMUNITY-HOME) GROUNDWORK IS OPEN AS DOCS-ONLY PR #160 — gate-neutral, `make check` green,
UNMERGED (Mit's to merge).** A GitHub Discussions launch plan (`docs/community.md`; **prep-and-hold** — Mit
enables Discussions manually at launch), a 6-provider capability matrix (`docs/provider-matrix.md`), and a
"Contributing a board" walkthrough in `CONTRIBUTING.md` (narrow local check = `pytest tests/unit/test_registry.py`).
Moves no program gate (the memo's continuation boundary). Stale nightly issue #142 closed — its commit
predates #157's fix, verified green on the full-matrix `workflow_dispatch` on `794eae2`. **Good-first issues
HELD** (Mit's call). Remaining owner launch decisions from the memo are still unsettled.

**The ASAP execution plan (D-280) governs.** "Done" is a **provisional pass** — 3 clean FROZEN runs meeting
all seven bar metrics (B1–B7) — after which the full 14-day acceptance runs PASSIVELY to confirm. Six
sessionized parts; the plan file at `~/.claude/plans/lets-use-this-session-staged-wren.md` **still names
Part 3 "Indeed" and Part 4 "hiring.cafe + GitHub lists" — that ordering was REVERSED by D-285 and the file
was never rewritten. Trust D-285/D-286, not the plan file.**

**B5 IS NOW SCOREABLE — the zero-output guard is ARMED on run-scoped rank attribution (D-302, PR #164 = `0fb50a7`, MERGED 2026-08-25 and armed on the live driver).**
The guard counts the four SUPPRESSION drops restricted to the postings judged this run
(`hidden_handled_this_run`/`hidden_applied_this_run`/`hidden_duplicate_this_run` + `dead_this_run`) and fires
when `J − Σsuppressions_this_run > 0` with 0 leads; a negative raises a typed reconciliation error. Rejections
(hard-filter/non-SWE/over-seniority/below-cutoff) are meant to FIRE the guard (D-246), by owner ruling. No
`artifact_version`/`engine_version` change → no drain; freeze-safe. `make check` green (7584); whole-branch
review APPROVE. The scheduled driver now runs it; B5 can be certified in the frozen runs.

**B1 caveat, still live (D-281).** A 14-day B1 pass does NOT evidence discovery health — it is close to
guaranteed for ~92 runs by ledger drain alone; the real threat is a **ledger reopen**, which re-serves built
jobs and scores them 0 net-new.

**HOW TO REPORT YIELD — the owner's standing rule (D-312).** Every yield, coverage or job-apps comparison
quotes **the end of the line: affirmatively `eligible` jobs** — currently **~60/day** (eligible + software +
in-band + US + non-duplicate + unhandled). **Never** quote a broader upstream population as the headline:
"new postings/day" and "software-titled/day" are different quantities, and doing so overstated yield ~8× in
this session before Mit caught it (the hard US filter alone removes 57% of the corpus). **`uncertain` is
never folded into `eligible`** — the keystone invariant, not a preference; the ~82/day abstains get their own
line. Measure with `stats` / `top --no-record --json` / the run funnel, never ad-hoc SQL over `postings`.

### Settled owner rulings (moved out of STATE 2026-08-27, verbatim)

Each was an owner-gated question and each is now DECIDED. They live here because the reasoning bounds
future work; STATE keeps only what is still awaiting a call.

0. ~~**THE ARMED LANES LEAK non-SWE noise into delivery — pick one (D-308).**~~ **DECIDED by Mit
   2026-08-26: option (b), build the facet — shipped as D-309.** Recorded because the reasoning bounds the
   next lane: option (c) (extend the role deny-catalog) was measured and REJECTED, not merely passed over —
   the `uncertain` tail is Busser / Water Spider / Dish Steward / Donation Processor / Nannies / Janitorial,
   an unbounded list, and the same bucket holds Linux Engineer, Senior HPC Engineer and Principal Architect
   that a broad deny would lose. **Do not propose a lane-noise fix in the role taxonomy again**; the fix is
   always upstream in what the lane asks for. Item 1 below is also settled by the same probe: hiring.cafe
   showed 100% location fill, so the location fail-open was never the issue — the ROLE fail-open was.

0b. ~~**NO DRAIN EXISTS FOR LANE-ACQUIRED POSTINGS (D-314).**~~ **DECIDED AND SHIPPED 2026-08-27 — all four
   sub-questions are closed.** The label question: a row nothing enumerates now renders **`unverifiable`**
   rather than `open` (D-324), keyed on `companies.watched` rather than `source='lane'`, which was wrong in
   both directions. The exit: a **measured** death — the posting's own URL answering 404/410 twice on
   different runs, never a redirect and never a timeout — can close it (D-325); it detects only **6.7%** of
   real closures, so *a run reporting zero closed is expected, not evidence of health*. The promotion: 15
   registry-ATS lane companies were promoted to `watched=1`, so zero enumerable lane companies remain
   unwatched. The cap: **the owner ruled the pool may GROW (D-329)** — age-based and missed-run closing are
   REJECTED BY MEASUREMENT (0 of 290 re-seen, yet 40 of 45 probed ALIVE), and a deliverability cap was
   declined because delivery is already bounded at 10/run. **Do not re-open any of the four.**

1. ~~**hiring.cafe's `v5_processed_job_data.workplace_*` fields**~~ **ALREADY SHIPPED — this row was STALE.** D-286 Ruling 4 took the decision and `lanes/hiringcafe.py::_locations` has implemented it since PR #141 (refined in #169). Verified against the live store 2026-08-27: lane postings carry real values (e.g. `"McClellan, California, United States"`). Original text kept below for the reasoning only. ~~**hiring.cafe's fields**~~ — read as provider-asserted location
   metadata, at the level greenhouse's `location.name` is already trusted (D-286 Ruling 4). D-278 called
   that payload untrusted, reasoning from the keystone invariant — which governs eligibility RULES, and the
   engine is body-only so it cannot reach these. The measurement that decided it: `classify_location([])`
   returns `unknown` and the hard US gate PASSES `unknown`, so withholding locations does not filter a
   3.89M-posting board, it admits all of it. On a broader reading the lane needs another location source
   before arming. **One function either way.**
2. ~~**Oracle Cloud HCM / iCIMS as PROVIDERS**~~ **CLOSED by measurement (D-311): do NOT build them.** The
   "~45% of the non-six tail" figure was a share of a small tail. Over job-apps' 138,788-posting ledger,
   Oracle Cloud is **0.84%** and iCIMS **0.44%** — ~1.3% combined, and every remaining platform is under
   0.2%. LinkedIn is 49.7% and Indeed 23.4% of that corpus, so ~73% of the market sits on one lane boardwatch
   already has and one source that is out of scope. **The lever is the LinkedIn lane's budget/paging, not new
   adapters.** Reopen only if a measurement on a different corpus contradicts this.
3. ~~**Run-scoped rank attribution** — the only honest fix for B5~~ **DELIVERED + MERGED (D-302, PR #164 =
   `0fb50a7`).** Four run-scoped suppression twins + the reconciliation invariant; B5 is scoreable and armed
   on the live driver. No code left for B5.
4. ~~**`locations` on `Lead` + an `artifact_version` bump**~~ **AUTHORISED AND BUILT (D-323, PR open on
   `feat/lead-locations-artifact-v7`).** Each lead now carries `locations` and `location_class`, the manifest
   carries `location_filter_mode`, and `artifact_version` moves 6 → 7. No owner decision left.
8. ~~**Extending the leakage query past `exact_quad`**~~ **CLOSED by D-327 (#185): the
   instrument was fixed and the reversal REFUSED.** The hardcoded `exact_quad` is gone, and the wider
   class is reported as a never-folded `candidate_*` UPPER BOUND beside the gate's own number. The
   4.76% figure below was WRONG as a duplicate count — only ~33% of that class are true duplicates
   (17.6% on the delivered population), so honest leakage is **0.50%**. Original text kept for the
   reasoning only.~~
   `company_title_location` class, because `store/identity_queries.py:296` hardcodes `kind == "exact_quad"`.
   Dropping ruling 3 did not close this and made it sharper: those duplicates are now neither suppressed nor
   counted, and the corpus holds **1,597 redundant open postings (4.76%)** on that key. **Never cite a
   passing leakage number as evidence dedup works.** One join condition, but it reverses D-132/D-283's
   ratified "only `exact_quad` counts" **while the gate is being measured** (D-294/D-295).
9. ~~**A redesign of same-role-same-place dedup on real discriminators**~~ **BUILT as D-327's
   `core/near_duplicate`: `requisition_slug`, `salary_band`, `experience_years`, proof by
   DISJOINTNESS not inequality. It vetoes rows OUT of a report bound and suppresses NOTHING — the
   suppression reversal is refused, permanently.~~
   posting's own URL, the city named in the body, the salary band, the YOE line. Ruling 3 is dropped because
   a fuzzy body score provably cannot do this (D-295), not because the duplicates are acceptable. Its own
   change, its own ruling.

---


## Settled session blocks moved out of STATE on 2026-09-07 (mid)

> Moved WHOLE from `STATE.md`, verbatim, when that file passed ~250 lines again — the fix its own
> header prescribes. Nothing was deleted or summarised. These are the 2026-09-05 sessions: the
> jobapps lane re-arming (D-486), the web-viewer audit (D-485), and the review/closure/run-5
> session (D-482/D-483/D-484). Their decisions are cited by number and resolve through the
> `DECISIONS.md` index as usual.

### Session 2026-09-05d (jobapps lane audit → RE-ARMED; eligible count re-measured): **the `jobapps` lane had been UNARMED since the reset** — the recovered config was the 08-28 tuning, older than the 08-31 arming — so runs 2–5 ingested ZERO job-apps discovery (store: 0 tagged postings, 0 `jobapps` companies, 0 lane scans for it). Re-armed 19:15 CDT on Mit's call, BEFORE the 20:00 chain, with `resumes/` as the first root and a 96-link symlink staging root (`<data_dir>/jobapps-staging`, the D-423 vehicle) as the second, covering `APPLY_QUEUE`'s groups and every date's `_eligibility_review`: **1,460 direct-apply postings, 776 employers (692 new)**, cap override `unlimited`. Discovery only — `rules_hash`/`engine_version` untouched, the D-483 count holds. Decision **D-486**; numbers in `METRICS.md`.

**Live eligible, under run 5's identity (the last evaluated):** tier 0 (`eligible` + `swe`) **67 — 38 delivered, 29 undelivered**; tier 1 (`uncertain` + `swe`) 994, never folded in. **Under the code on `main` there are ZERO current verdicts until run 6 finishes re-evaluating** — T51 moved `engine_version`; `boardwatch web` reads every lead `unevaluated` until then. Five `Acme` test-fixture folders (06:59 CDT, pytest temp paths, `job_id 1` = a real posting) were removed from `~/boardwatch-queue`; apply lane is 40. **Owed (both closed 2026-09-06, D-487/D-488):** the Acme leak was timed to the T44 gate on branch state `ca8ad906`, not reproduced on `main`; the `_applied` import wrote 18 applications after its url fan-out defect was fixed. **Do NOT re-point `jobapps_queue_dir` at `APPLY_QUEUE`** — Mit (19:35 CDT): `APPLY_QUEUE` is historical and no longer updates; `resumes/` is the daily feed and the lane already reads it directly. The FUTURE-dates gap (static staging links) is closed by `com.boardwatch.jobapps-links` (D-488).

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

**All five owed items are DONE (D-488, 00:40–00:50 CDT):** `com.boardwatch.jobapps-links` refreshes the staging links at 05:50 and 08:45 (separate job; the run plist is untouched); `"indeed.tier1" = 25`; 18 applications imported from the `_applied` tree after the dry run exposed a `track import` url fan-out (566 jobs from one Indeed url — fixed, refuses as `ambiguous`); the store "Front End" titles are vetoed by the role gate (74 postings, 0 software titles moved, `engine_version` untouched); 53 review holds triaged — **27 clear both blind passes and are listed in `.agent/2026-09-06-review-triage/REPORT.md` for Mit to promote from the review page**, 16 are confirmed holds with quoted bars.

**Next action.** Read run 10 (06:00 CDT 2026-09-07) — the first run whose funnel carries T60's buckets: `reconciliation: RECONCILES` is the check, plus `gate_rejected` and `routed_to_review_lane` on the projection stage. Then two owner rulings before any B8 work: (1) do runs 7 and 8 count toward the provisional pass; (2) 0-B, judge → lane promotion. The owner's own move stands: promote the 27 triaged review leads, apply from the 133-lead apply lane. Mit's optional machine action: a reboot moves the 06:00 tick to 04:00. The 2026-09-05 block below is the next candidate to move WHOLE into `STANDING-FACTS.md` when this file passes ~250 lines.


## Settled session blocks moved out of STATE on 2026-09-12b (verbatim; the 2026-09-07 early and mid sessions, settled by D-493 and D-494 — the review of them is D-495, still in STATE)

### Session 2026-09-07 (mid; ALL FIVE RULED CALLS EXECUTED — 15,640 postings closed, zero censored boards, four executors merged): **D-494.**

**The PDF drop 21 -> 5 is BENIGN and the question is closed.** The PDF stage converted 100% on both
runs (`21 in, 21 out`; `5 in, 5 out`; `no_pdf: 0`). The whole delta is the apply/review lane split
(`routed_to_review_lane` 19 -> 35): `review_gate.classify` promotes a deterministic `eligible` lead
unconditionally, run 10's slate carried **21** and run 11's carried **zero**. Cause: `new_count` was
779 on run 9, **30,706 on run 10**, 4,852 on run 11, and all 21 of run 10's `eligible` leads were
first seen on 09-07 — run 10 discovered them itself. It was the first-fill of the ~30 boards added
09-06 plus `amazon` and Jane Street. **~5 PDFs a run is the STEADY STATE; the apply lane is bounded
by the arrival rate of new `eligible`+`swe`+in-band postings, not by a backlog.**

**Fleet: 15,640 postings CLOSED by the slicing and censored boards 10 -> 0.** Workday facet slicing is applied
live to 13 slices across nine boards; open postings ~150,000 -> **137,810**; ~2,650 postings the
blind 2,000-walks had never seen. Per-board closes: Northrop 2,938 · Walmart 2,266 · Target 2,051 ·
T-Mobile 1,988 · PNC 1,897 · Citi 1,529 · Leidos 1,220 · BAH 1,008 · NVIDIA 743. **The ruling's
premise did not survive measurement:** `jobFamilyGroup=Technology` is the right descriptor for only
**3 of the 10** boards — T-Mobile uses a different PARAMETER (`Job_Family_Group`) and Abbott's biggest technology group is only 61 of 2,589, so Abbott is deliberately not sliced. **Northrop's workday row lost the
comparison** (3,000 of 3,791 on a page cap; its Engineering group is 2,182, above the 2,000 clamp,
so slicing does not fix it) and was DRAINED to 91 then unwatched — 2,938 closed through the absence
rule first, leaving 91 unclosable instead of 3,010. Eightfold keeps 3,424. **Fleet 341 watched.**

**Merged and pushed, six commits, final gate 10,090 passed:** `0e1690ac` **T72** (each judged lead's
shortlist rank recorded with its gate verdict, captured off the ranker's order BEFORE liveness;
`engine_version` unmoved, **no ledger drain owed**) · `aaa4aefc` **T70 `apple`** · `ad215b45` **T73**
(the ranking cap, 2 per company+title+location) · `f3466988` **T74** (the eightfold 405 retry +
employer naming) · `92781ce7` **T75** (`companies facets`) · `60e3efa2` the integration fix.

**T74 proved the planning session's own ticket WRONG, and it changes what item 4 delivers.**
`exact_quad` keys on **`company_id`**, not `normalize_company` — two boards are two `companies` rows,
so **no naming change can ever make it fire across them**. `cross_host` is the one keyed on the name
and it does not suppress, by design (§3.1). **So the cross-board duplicate is now GROUPED, not
SUPPRESSED: the 14-18% queue duplicate rate will NOT fall from this.** Acceptable because the
largest pair (Northrop) was dropped this session and the Qualcomm pair, the one the coverage fix
exposes, does group.

**Two defects found here that four green branch gates did not catch.** (a) T74's backfill selected
`name == slug` case-insensitively, which admits registry rows whose curated name is the slug
re-capitalised; it planned **129 rewrites, downcasing 100 names** (`OpenAI`, `SpaceX`, `AbbVie`) that
reach the résumé filename. Fixed casefolded: **31 rows**. (b) The MERGED-tree gate caught that
`apple` had no declared employer-name shape (T74 predates T70), so it would have named the company
after a COUNTRY. Backfill applied here: 31 rows renamed, `identities backfill` wrote 24,466.

**Next action.** (1) **Read run 12, the 06:00 tick on 09-08** — the first run carrying the shortlist
rank, the ranking cap, the sliced fleet and the eightfold retry. Then the rank-band measurement that
D-493 could not do becomes possible: read conversion by rank band out of
`raw_output_json.$.shortlist_rank` and answer whether `gate.depth = 150` is right. Expect a much
smaller corpus (137,810 open, not 150,000) and watch `hidden_cluster_cap` and the new
`throttle_retries` / `throttle_exhausted` lines. (2) **Thales may never close**: it serves 2-3 rows
with no `externalPath` on every scan, forcing `partial`, so its ~1,800 non-SOFTWARE postings are
stuck open — pre-existing provider behaviour that slicing exposed. (3) **The nightly WINDOWS CI has
failed every day since at least 08-31** on the fake-claude-on-PATH class; `push` CI is green on the
same shas. T61 fixed nine; this class remains and is worth a ticket. (4) Open questions the
executors raised and nobody has ruled on: whether to seed the cluster cap from the standing queue
(D-439's pattern) so a five-member group does not eventually deliver every member; whether 2 is the
right cap once `hidden_cluster_cap` has been observed live; and whether the guide needs a
"network, read-only" effect marker (T75 registered `("network",)` rather than invent one).

**Process note.** Three executors + a full gate + a scan pass at once drove load to 65 and memory
pressure killed six background waiters. Nothing was lost, but a gate under memory pressure can be
OOM-killed into a false red. **Gate BETWEEN executors, not across them.** Also: scans are serialized
by a global `scan.lock`, so a multi-board slicing pass is wall-clock bound and cannot be parallelized.

### Session 2026-09-07 (early; run 10 READ, the depth bet MEASURED, `amazon` and Workday FACET SLICING landed): **D-493.** Run 10 was launched BY HAND at 00:09 CDT on Mit's ruling (the handoff's "read run 10" was not actionable — `runs = 5`, no artifact dir; the tick had not fired). It ran **2h 40m** and came back **`ok`**: the first `gate.depth = 150` run reads `150 checked, 5 gone` → **145 judged (76 eligible, 22 ineligible, 47 uncertain), 0 batches failed open, 83 beyond the delivered slate**, funnel **`reconciles: True`**, `boards_failed` 0, `detail_deferred` 0 everywhere. **T63 has no first-live defect.** A manual run does NOT count toward the confirm streak, so the 06:00 tick still fires as run 11 and is the countable one. **T69 `amazon`** (merged `81fc956a`, CI green) — 22,282 postings over 38 categories, bodies INLINE so a 2,597-posting category costs 26 requests. **T71 Workday facet slicing** (merged `c3a5bc1e`) — `…/site#jobFamilyGroup=Technology`; live, sliced Citi enumerates **1,073 of 1,073 uncensored** against the unsliced board's `total: 2000` censor and 1,988 blind rows of a true 4,411. **Fleet 337** (+`amazon:software-development`, +`greenhouse:janestreet`, +3 lane-discovered). The recurring CI wall-clock flake (4.58 s on 09-06, 4.63 s on 09-07, both vs the same 4.5 s bar) is FIXED by rendezvous, not re-run (`1afd7d0f`).

**The depth bet is measured and it is NOT D-491's number.** Judge rows joined to the deterministic verdict on `input_id`: tier 1 (`uncertain`) **122 judged → 69 eligible = 56.6%**; tier 0 (`eligible`) **23 judged → 7 = 30.4%**. D-491's 85% was measured on the SHALLOW slate. The decision stands (69 judge-eligible leads no shallower run would have seen) but **the right value of `gate.depth` needs conversion BY RANK BAND, which needs each judged lead's rank — **not measured, and NOT computable retroactively: `score` is NULL on all 145 judge rows and no table persists a rank, so this needs a small instrumentation change (persist the shortlist rank with the gate verdict) before it can be answered.**

**Coverage — quote the run's own numbers.** `morning-10.md`: **discovery reach 90.4%** (109,065 of 120,606 stated, across 224 of 335 boards), and **10 censored boards short 35,645 postings** reported SEPARATELY with no ratio. A "67.7%" figure computed mid-session folded censored totals into one ratio and is WITHDRAWN. boardwatch already recovers true totals via facets; T71 extends that from totals to ENUMERATION.

**Run 11 (06:00 tick) READ — `ok`, 43 min, `reconciles`, `boards_failed` 0, `runs = 6`.** Both new boards work live: `amazon:software-development` **complete 2,598 of 2,598** and `greenhouse:janestreet` complete 231 of 231. **The depth cost AMORTIZES: 145 judged on run 10, only 62 on run 11** (a judged-undelivered lead keeps its verdict and is not re-judged) — so `gate.depth = 150` is cheaper after the first run than run 10 implied; read that beside the 56.6% conversion. Discovery reach **91.1%**. The slate is strong (LinkedIn, OpenAI, Apple, TikTok x3, Figma, Ramp, Audible) and run 10's 12-lead Goldman concentration is gone. Unexplained and NOT investigated: pdf 21 -> 5.

**Next action: SUPERSEDED — all five rulings were executed on 2026-09-07 (mid); see D-494 and the block above.** One claim in the removed text was WRONG and is corrected there: `exact_quad` keys on `company_id`, not `normalize_company`, and the hostname-named board count was 35 of 338, not 28 of 337.

## Settled session blocks moved out of STATE on 2026-09-12 (verbatim; the 2026-09-06 sessions, all settled by D-487..D-492)

### Session 2026-09-06 (late; phenom and eightfold LANDED): **D-492.** T66 `phenom` and T67 `eightfold` resumed ONE AT A TIME on the enterprise seat after Mit's go-ahead ($17.50 together), each reviewed, mutation-checked, live-verified in a scratch store and gated green; merged `0165a43e` / `67989c30`, integration `f17f11bc`, pushed. T67 found and fixed an id-less-row minting bug; its own "largest board is 1,958" correction was WRONG — Northrop Grumman is 3,817 live and the 300-page backstop cut it at 3,000, so the backstop is now 600 (rescan 3,817 = 3,817). **Fleet 332 watched** (+3 phenom: BAE Systems, P&G, Battelle; +4 eightfold: Qualcomm, Northrop, Applied Materials, Boston Scientific). Not started: SuccessFactors (no public JSON found), the bespoke majors (Amazon, Apple, Meta, Google, Jane Street). No `rules_hash`/`engine_version` change. (Run 10 was read in the session above.)

**Next action.** Read run 10 (06:00 CDT 09-07): the first depth run — expect `gate: ~150 judged … ~110 beyond the delivered slate`, gate stage ~15 min, `RECONCILES`; the first scans of 30 new boards (`boards_failed` 0; Oracle/Phenom/Eightfold boards `partial` on the 50-detail budget is by design; Northrop alone is ~10 min of paced requests). If judged ≠ ~150 or the funnel does not reconcile, read `.agent/2026-09-06-exec/RESULT-t63.md` §"reconciliation definition" first. Then the bespoke majors, one ticket each, after asking Mit the seat's usage. Mit ruled 23:53: runs may be as long as full coverage needs — `detail_fetch_budget` ceiling raised to 10,000 (`04e000bb`) and the live value set to 5,000, Northrop kept. Owner calls still pending: whether `config set` should reach gate keys (it does not); the phenom teaser-body rows have no drain.

### Session 2026-09-06 (evening; the Pinloop replacement begun on the enterprise seat): **D-490 + D-491.** Six branches merged and pushed, CI green: **t62** (generated `boardwatch guide` + `skill`, `--json` on eight read commands, 22 wrong claims corrected after a $6 review), **T63 `gate.depth`** (judge deeper than the run delivers; **LIVE at `gate.depth = 150`** in config.toml), **T64 `jibe`** and **T65 `oraclehcm`** providers (live-verified in scratch stores), **T68** (the Indeed control test was hitting the live API). Fleet 325 at that close (+18 Workday tenants, +AMD/JHU APL on jibe, +Oracle/AmEx/Goldman-campus on oraclehcm). Item 3 was REVERSED by measurement: tier-1 leads the judge sees convert 85%, so depth, not a pre-screen. The seat's window died under five parallel executors (~$103); the standing rule is one executor at a time after asking Mit the usage reading.

### Session 2026-09-06c (run 9 READ; B6 found NOT reconciling on runs 7–9 → T60; nightly Windows CI → T61; the B8 lever measured): **run 9 is a clean tick on the restored config** — `runs = 5`, exit 0, every hash identical to runs 6–8, LinkedIn admitted 50, Indeed 57, `jsonld` present (0 attempted is lane ordering, D-422), 37 judged / 31 eligible / 1 ineligible, 36 delivered = **7 apply (all PDF) + 29 review**. **But its funnel reads `DOES NOT RECONCILE`, and so do runs 7 and 8** — the 09-05 (later) session recorded the provisional pass from the run status without reading that line. Cause is REPORTING: `build_run_funnel` never learned T43's review lane or T54's judge rejection; the unnamed remainder is exactly `judge-rejected + review leads` on every run. **T60** (reports only; `rules_hash`/`engine_version` untouched, so the confirm is NOT restarted) adds `gate_rejected` and `routed_to_review_lane` to the projection stage and merges the review leads into the tailor stage's `entered`; `ARTIFACT_VERSION` 8. **T61** fixes the nightly Windows jobs, red every day since ≥ 09-01 on nine tests. Both built by headless Opus executors on the enterprise seat, reviewed and gated here: t60 gate green (9,604 passed); merged tree green (9,604); t61 gate green (9,595 passed); Windows verification run 34061956555: Windows 3.11 and 3.12, macOS and every Linux shard GREEN; 3.13 red on one unrelated wall-clock overlap test (4.58 s vs 4.5 s margin); attempt 2 re-ran that job GREEN, so the whole run is green and the overlap test is a flake. Both merged to `main` (`b240698d`, `67cba250`) and pushed after a green gate on the merged tree. Decision **D-489**; numbers in `METRICS.md`, `Session — 2026-09-06c`.

**The B8 lever, measured read-only:** `delivery/review_gate.classify` never reads the judge. 24 of run 9's 29 review holds carry a judge `eligible`; 46 of the 123 in the lane do. Tier 0 (`eligible`+`swe`) is DRAINED (171, 4 undelivered), so the `--top 40` cap bites on tier 1 only. Promoting on a judge `eligible` is **owner-gated (0-B below)** — it makes the judge an evidence source for `ELIGIBLE` with no span. **Owner ruling owed: whether runs 7 and 8 count toward the pass** (recommendation: they stand — the instrument was wrong, the pipeline was not). The `taxonomy changed — re-extracting N` line on every run is `preflight.py:53`'s wording for new postings, not drift.

### Session 2026-09-06 (planning → the reset's SECOND config loss found and RESTORED; the apply lane blind-audited for B8): **the recovered config had also dropped `jsonld` + `indeed`, the seven LinkedIn hubs (33 combos/run), the caps `linkedin = 50` / `indeed = 50` and `pace_from_request_start`** — D-486 caught only the jobapps half, and runs 6–8 ran LinkedIn at the 10-company default. The last pre-reset `config.toml` was recovered VERBATIM from the transcript archive (2026-09-03T23:55Z) and restored 00:15 CDT on Mit's call ("before it"), read back through the loader; discovery only, the count holds. **Run 9 (06:00 CDT tick) is the first run on the restored five-lane config AND day 1 of the 14-day confirm.** Decision **D-487**; numbers in `METRICS.md`, `Session — 2026-09-06 · the pre-reset config…`.

**B8 measured for the first time (n = 128, the whole apply lane, two blind Sonnet passes, 40/40 inter-rater on the unapplyable axis): 22 of 128 UNAPPLYABLE = 17.2% against the ≤ 16% bar; 14.7% on the 95 gate-judged leads (runs 5–8), 24.2% on the 33 delivered before the judge existed; `jobapps:` targets 2.1% vs board fleet 26.2%.** Causes: six-family `ineligible` 10 (work_auth 4 — PayPal's "Visa Sponsorship … is not available … now or any time in the future" ×3; experience 5 — two U.S. Bank bars in WORDS, "Two to three years"), seniority 6 (Inferact "Member of Technical Staff" ×4), role 5 (Giant Eagle "Front End Lead" ×3), location 1. Report and key: `.agent/2026-09-06-audit/`. **The tier-0 headline is that same board: 46 of the 49 undelivered `eligible`+`swe` are Giant Eagle "Front End Lead Trainee" (`role_verdict` matches "Front End Lead"); tier 0 is drained and the slate already draws from tier 1 (1,644; 1,323 zero-row).** 46 of the 48 `jobapps:` apply leads were already promoted by job-apps itself — parity, not new reach.

## Phase status — P0-P6, settled

*Moved WHOLE from `STATE.md` on 2026-09-01e, unedited, when that file passed 250 lines again. Every phase here is COMPLETE with its gate MET and none has moved since 2026-08-28. `STATE.md` keeps only the rows that are still live.*

| Phase | Build | Gate |
|---|---|---|
| P0 Instrumentation | **COMPLETE** | **MET** (D-030) |
| P1 Résumé artifact gate | **COMPLETE** | **MET** (D-032/033) |
| P2 Profile + keystone | items 1–7 shipped; item 8 NOT STARTED | **MET AS RECONCILED** (D-075) |
| P3 Unattended one command | **COMPLETE, INSTALLED, FIRING** once daily at 04:00 local (owner's call 2026-08-27; was ~3h under D-288). The agent is now a FALLBACK HEARTBEAT — Mit's ruling is to invoke a run manually as and when needed, so do not wait for the schedule | **MET** — 8 consecutive clean scheduled ticks (runs 71-78), verified from the `runs` table + funnels |
| P4 Craft gate | **COMPLETE** (under-fill fixed D-303; objective anti-slop 0 violations, non-vacuous) | **MET** — objective half certified AND the owner's blind craft review passed cleanly 2026-08-26 (all 5 judged worse were job-apps decoys; all 3 judged better were boardwatch) |
| P5 Eligibility decides | **COMPLETE** | **MET** — INELIGIBLE precision 16/16, 0 span violations |
| P6 Liveness + dedup | **BUILD COMPLETE** (D-110/111/113); leakage report shipped (D-283) | **MET — 4 of 4** (2026-08-27): liveness MET (D-281), leakage measurable over a true 7-day span and reading **0.00%**; see the clause table for the `exact_quad` caveat |
| 14-day acceptance | not started | **HELD BY THE OWNER (2026-08-27)** — the provisional pass was MET by runs 119-123, and Mit ruled to keep fixing precision first rather than start the clock. Starting it freezes eligibility, profile and the résumé gate for 14 days. **2026-08-28e: the provisional pass's remaining item — 3 clean post-fix runs — RESTARTED FROM ZERO**, because #218 bumps `rules_hash` and those runs are therefore pre-fix again. The P4 owner blind review is still PASSED (2026-08-26) and does not repeat. With runs on demand and Mit stepping back ~2026-08-31, that is 3 runs in ~3 days; **the trade (stricter eligibility now vs the pass possibly not closing before unattended operation) was raised to Mit and is his**. **2026-08-28f: #221 bumps `rules_hash` again, so the counter restarts again — and this is NOT being chased (D-351 item 2 stands: work comes first)** |
| P7 Breadth | **lane 1 (hiring.cafe) and Part 4b (LinkedIn) are BUILT AND ARMED and ran in run 122** (hiringcafe 70 attempted/56 resolved; linkedin 71/51) — the previous "not armed" text was stale. **Part 4a GitHub-lists discovery BUILT + LANDED (#149/D-296) and NOW PARTLY ARMED**: 97 boards imported 2026-08-27, ~765 candidates still capped. Remaining lanes not started | unlock MET (D-271/272) |
| *Gate A / Gate B* | *complete, merged* | ***MET*** — *has moved no program gate* |

### Gate P6 — MET, 4 of 4

The clause-by-clause table moved to `STANDING-FACTS.md` on 2026-08-28f: every clause is MET and
none has moved since 2026-08-27. Read it there before quoting the leakage figure — the `exact_quad`
caveat (D-294) is what makes 0.00% a structural reading rather than a clean one.

## Gate A internals

- **A closed review loop is evidence about the slices reviewed, not about the subsystem being
  defect-free** (D-161/D-162; carried here as D-149's fourth prerequisite so it survives the `STATE.md`
  trim, since STATE was the only place holding it). Earned, not cautionary: two silent-success defects
  (D-138/D-142, D-141) were found *after* the loop closed, in code six reviews and four gates had already
  passed. Gate A reading **MET** (D-157, green on all twelve CI jobs at `8475319`) says its slices were
  reviewed; it does not say the subsystem is clean.
- **`_root`, `.` and `..` are ESCAPED by the encoder, never refused** (`%5Froot`, `%2E`, `%2E.`). Refusing
  makes a legitimate document unenumerable. `normalize_locator` keeps a `.`/`..` guard for raw *paths*, where
  the same spelling means traversal (D-120, D-125).
- **The `_root` reservation is global on purpose**, and **`is_normalized_locator` is deliberately WEAKER than
  `emits_locator`** — it also serves owner-authored scope locators, so tightening it strands every legitimate
  selected scope.
- **The uniform JSON envelope on all twelve T18 commands is RIGHT** — both lenses upheld it independently. The
  **design text (§19) is what is wrong**; T19 amends it. `report_json`/`report_text` were production-dead and
  are deleted.
- **A two-document write is NAMED, not made atomic** (D-137). POSIX cannot rename two paths as one operation;
  a journal only moves the window; merging the documents would break the closed 33-document grammar. Hence
  `PARTIAL_EDIT_APPLIED`, deliberately **outside** `COULD_NOT_COMPLETE_CODES` because exit 3 would invite a
  retry guaranteed to refuse. The `rebase-draft` precedent for "two renames are fine" is **withdrawn** —
  those rename directories and stage no temporaries.
- **A missing bundle root is `bundle_not_found` on all twelve commands** (D-138, D-142). It is stated in
  **three** places, not one, and that is the fact worth knowing: `require_confined_root` (which
  `must_exist=True` makes the default for every reading surface, `init_draft` being the single opt-out),
  the pre-lock `is_dir()` checks in `promote` and `rebase-draft` (which must precede `filelock`, or it
  creates the directory), and `authoring._draft` plus the CLI's `_draft_tree` — because `add-evidence`,
  `resolve-conflict`, `approve` and `validate --draft` **reach no function that confines the root**.
  D-138 originally claimed one shared entry point covered the surface; it covered eight of twelve.
- **The guard asks `is_dir()`, never `exists()`.** A regular file, a device or a dangling symlink at the
  root all exist and are not bundles, and under `exists()` `inventory` reports a file root as a clean,
  empty bundle at exit 0. `is_dir()` also answers `False` for a symlink loop, which is why the refusal
  precedes `resolve()` — a loop used to escape as `RuntimeError` past every handler, carrying an absolute
  path. Both arms are pinned; only the file arm kills the `exists()` mutation.
- **`STATE_REFUSAL_CODES` has no production reader.** All thirteen members are documentation, so a code's
  membership in it cannot be wrong in a way any test can see. Do not treat that set as a mechanism.
- **The YAML `!!`-tag content-addressing bypass is CLOSED, not open.** `compose_node` refuses every explicit
  node tag; verified by probe (`!!omap` duplicate-key smuggling and `!!python/object/apply` both refused,
  plain YAML still loads) and by mutation (disabling the guard turns 12 tests red).
- **`METRIC_REVIEW_MISSING` is DELETED and metrics get no review interval** — a metric's freshness is its
  `reviewed_at` date alone (D-115, Mit's ruling). §20.6's clause binding an owner's approval to promoted
  content must fire for **every** revision, not only the first.
- **`Path.resolve()` on a symlink loop differs across the interpreters CI runs** — 3.11/3.12 raise
  `RuntimeError`, **3.13 returns the loop's own path**, which satisfies an equality check and admits the
  escape. Confinement therefore refuses on `is_symlink()`. **Keep a worktree on 3.13** — free cross-version
  coverage. `uv run --python X` inside the repo root **silently replaces `.venv`**; repair with
  `uv venv --clear --python 3.12 && uv sync --reinstall --all-groups`.
- **Import fixtures as `from tests.<package>.conftest import ...`, never bare `from conftest import`.** A bare
  import binds whichever `conftest.py` loaded first — under the full suite, `tests/unit/conftest.py`. This
  shipped in T15 and survived two lenses and a fix round; it is invisible to any narrow run.
- **The packaged example validates at 8 blocker, 0 error, exit 1.** That satisfies Gate A, whose clause is
  that the layers *run*, and **not** Gate B's separate "zero undispositioned blockers".
- **All three sites of the blocking-`open()` class are now closed.** A non-regular file is refused for a
  blob store entry (`storage._require_stored_blob`), for a compared tree (`storage.identical_trees`) and for
  a bundle **document** (`layout.discover_source_files`, D-141) — the last being the one that hung
  `validate --draft` and `promote` forever, `promote` while holding the bundle lock. The guard belongs at
  `discover_source_files` because every reader downstream of it (`load_documents`, promotion's verbatim
  copy, `checkout`'s tree copy) opens what it returns and none of them takes a timeout. **A fourth site is
  any new code that opens a path the layout did not hand it.**
- Upstream of T18 and deliberately not chased: a typo'd `--bundle` made `inventory` report clean at exit 0
  (**fixed**, D-138); `context.py:92` and `blobs.py:175` are deferred pre-existing `$HOME` leaks.
- `docs/superpowers/` holds the design and plan and is **tracked** (12 files under `git ls-files`), so a new
  worktree already has it. The directory that is untracked is the dotfile **`.superpowers/`**, excluded via
  `.git/info/exclude`, and that is the one a worktree needs copied in (D-171 corrects the conflation).

---

## Liveness and the ledger

- **Only a caller that DELIVERS a lead may consume the queue** (D-110). `eligibility gate request` and the
  pipeline pass `record_surfaced=False`; `top --no-record` is the operator's opt-out. The pipeline writes all
  three ledger tiers *after* the tailor loop. Do not move the `seen` write back into the ranker.
- **Liveness is never cached, and "never" includes `postings.status`** (D-111). One 404 from a flaky CDN would
  otherwise retire a live requisition **irreversibly**. That column belongs to the scanner's
  `CLOSE_AFTER_MISSES = 2` rule, which works: 0 open postings are stale beyond 7 days.
  **Corrected 2026-09-17:** that 0 was held there by the `jobapps` lane bumping `last_seen_at` on every
  row it re-listed each run, and now that a listing no longer writes liveness the same query reads true ages.
- **URL liveness is `unknown`, not `dead`, for a dead Ashby or Greenhouse posting.** A dead Ashby page answers
  200 with an empty shell and a dead Greenhouse page redirects to `<board>?error=true` and then answers 200, so
  `core/liveness.py` maps both to `refetch_ok` → alive. Only a board scan of a watched company, or the
  list-API membership half of the death probe for unwatched `ashby`/`greenhouse`/`lever`, can close that class
  — and a `jobapps`-lane listing is a local directory read that declares `"liveness"` secondhand, so it is
  never evidence in either direction.
- **Only 404/410 withholds a lead, and only from the URL asked about** (D-111, D-113). Timeout, 403, 5xx, a
  redirect and a NULL URL are all `unknown`. A live Pinterest posting answers 403 to an unfamiliar user agent.
- **`Fetcher` sets `follow_redirects=True`**, so a `302 → 404` chain arrives as a bare 404, and
  `FetchFailure.redirected` is the only thing distinguishing a posting that is gone from one whose old link
  points at a dead path on a new host. The single most likely thing to be undone by accident.
- **"Gone" means the URL asked about said so, not where it redirected** (D-113). `refetch_gone_after_redirect`
  is a **subset of `unknown`**: that count climbing while `dead` stays 0 is the detector **disarmed**, not a
  healthy corpus. `tests/unit/test_liveness_prober.py` is the only module driving the real `Fetcher` — its two
  redirect cases are the sole coverage; do not delete them as duplicates.
- **A `Liveness` verdict must be the one its signal carries** (D-113) — `dead` is reachable through
  `refetch_gone` and nothing else. **An unprobed run reports liveness as UNMEASURED, never 0 dead** (D-111);
  `run --no-check-liveness` opts out.
- **Applied state is read from `applications`, never mirrored into the ledger** (D-111). `interested` does not
  suppress (it is `track add`'s default); `withdrawn` is the drain.
- **Only a deterministic refusal earns a permanent `skipped`** (D-110). `DETERMINISTIC_GATE_REFUSALS` is the
  closed catalog; a non-zero `tectonic` exit is environmental and must be retried. Out-of-catalog ⇒ environmental.
- **No `policy_version` component covers the résumé or `resume_max_pages`** (D-110), so trimming `resume.yaml`
  does **not** make a decision stale — `ledger reopen --job <id>` is the only path, not `--stale`.
- **Regrouping carries the ledger decision with the postings** and releases the emptied row (D-110).
  `protected_job_ids` cannot catch a merge that leaves it behind: `artifacts.job_id` is NULL on all 44 rows.
- **A new ranker drop bucket has SIX hand-maintained mirror sites and only three are checked** (D-111).
  **Nothing catches `_shortlist_line`** — the full list is in `RankedResults`'s docstring.
- **`hidden_duplicate == 0` is ambiguous; `hidden_handled == 0` and `hidden_applied == 0` are not** (D-106,
  D-111). **`_verify_quad` has never fired** (D-097) — never cite "string-verified" as precision evidence.
- **`track` has never been used** — `applications` and `application_events` are both 0 rows, which is why P6
  item 5 ships as a mechanism with tests as its evidence.
- **The closed-phrase catalog was NOT shipped, deliberately** (D-111). Providers assemble `body_text` only
  from JSON-payload description fields, so page chrome cannot reach that column: **11 of 23,455** matched,
  **all false positives**; a high-precision catalog matches **0**.

---

## The live store

- **A 5 s `busy_timeout` can be STARVED by a competitor that commits in a tight loop (D-501, measured
  2026-09-12 on windows-latest).** SQLite's busy handler is sleep-and-retry on a fixed back-off; it does not
  interleave two writers, so the loser waits until the winner has run ALL of its commits (~1.1 s for 200
  unloaded, past 5 s under full-suite load). The scan applies ONE board per transaction, so production's
  shape is one long hold, not 200 short ones, and no production path has read `database is locked`; the
  two-writer guard's subprocesses carry 60 s for this reason and prove no corruption and no loss, not fairness.

- **Slice 2 IS APPLIED, and the ledger and regrouping both run on real data.** Corrected 2026-08-23d
  against the store (D-289); this bullet previously said the opposite and offered a read-only proof that no
  longer holds. Measured: head **`p_lane_companies`**, **both** Slice 2 tables present
  (`job_dispositions`, `job_grouping_events`), **184,304** identity rows at `p6.2`.
  **The old proof inverted:** `postings` **37,438** against `count(distinct job_id)` **37,341** — a
  difference of exactly **97**, matching the **97** `job_grouping_events`, so `identities regroup` has run
  and consolidated 97 postings onto canonical jobs. The ledger holds **100** rows, all `built`, from real
  runs. **The lesson this bullet is now an example of: a read-only proof is only a proof on the day it was
  taken.** It named a table's absence as its evidence, and the table arrived.
- **Still NOT demonstrated on real data:** the liveness probe against real leads at corpus scale, and
  `applications` remains **0 rows** — nothing has ever been applied to.
- **0.3.0 is PUBLISHED (D-119)** — PyPI, GHCR (`amd64` + `arm64`) and GitHub Releases, verified through three
  paths independent of the workflow's own report. `v0.3.0` is a **lightweight** tag on `dc1ffec`, like every
  prior tag. It **ships Gate A inside it, deliberately** — the wheel carries the whole `profile_bundle`
  package. **Mit was offered "hold until Gate A is reviewed" twice and declined both times.** The basis holds
  because the package is **inert**: no CLI command, no bundle-to-`Resume` bridge, a test asserts both
  directions. Publishing changed the release, **not** the review's standing.

---

> **PHANTOM run 118 (benign, mine, and STUCK `running`).** The production-path verification for D-319
> was a `boardwatch top --no-record` against the LIVE store, which calls `ensure_run`. It wrote **4,400
> eligibility evaluations** under `1+5bf77461f044` — the rows the paired old-vs-new comparison in METRICS
> is measured from, so they are real and correctly stamped — and was then stopped part-way, leaving
> `runs.id=118` at **`status='running'` forever** with `boards_attempted=0`, 0 artifacts and 0
> `job_dispositions`. Gate P3 is unaffected: its filter is `boards_attempted > 0`, which excludes this
> row exactly as it excludes run 91. Left in place for the same reason run 91 was — the production store
> has no rollback snapshot and deleting a row is riskier than an inert one. **Consequence: the first
> scheduled tick on the new engine is run 119, not 118.** Two lessons, both already known and both
> ignored here: `top` writes a run even with `--no-record` (that flag governs the `seen` cursor, not
> `ensure_run`), and a full-corpus read against the live store is a WRITE.

> **PHANTOM run 91 (benign, mine).** A `boardwatch tailor run 13549` verification without a scratch
> `BOARDWATCH_DATA_DIR` called `ensure_run` and wrote to the LIVE store: run 91 (empty, `boards_attempted=0`,
> 36ms) + one `artifacts` row (id 498, uri→`/tmp`). NO `job_dispositions`, posting 13549 NOT marked handled,
> dedup/ledger UNAFFECTED, streak intact (the `boards_attempted>0` filter excludes it). Left in place (prod
> store has no rollback snapshot; deleting is riskier than an empty row). Consequence: next scheduled tick is
> **run 92**. Lesson: to verify projection against real postings with the LIVE edited config you must hit the
> live store — use read-only `resume project`, never `tailor run` (it writes a run+artifact).

## Environment

- Neither `python` nor `boardwatch` is on PATH — always `uv run …`.
- No `__init__.py` under `tests/`, so test module basenames must be globally unique or collection aborts.
  `make check` runs mypy on `src` and `tools` only, ruff on everything.
- **A migration must never import a live catalog into its CHECK constraint** — it changes the constraint
  retroactively and diverges a fresh database from a migrated one. `tables.py` may (that is metadata, not
  history). Name constraints with `op.f()` or `test_migrations_match_metadata` sees permanent drift.
- **The résumé renderer is `tectonic`** compiling Mit's real LaTeX template, **not Typst** (D-058/D-060). A
  `typst` binary exists on this machine; nothing calls it. The tailoring architecture is already correct.
- **D-072, the model-tier benchmark, is DEFERRED INDEFINITELY** (D-102) — not owed, not blocking.
- `bwd` lives in gitignored `.agent/bin/bw-daily`, so its `top --no-record` fix is local to this machine.
- Foreground `sleep` is blocked in this harness; background a waiter instead. zsh does **not** word-split an
  unquoted parameter expansion, so a `for spec in "a --b" ...; do cmd $spec; done` loop passes one argument.
- **There is NO live urgency — job-apps is delivering.** `STAGE1_ONLY=1` is in job-apps' launchd plist, so
  its 08:30 run does stop after discovery, but résumés are produced anyway. Measured 2026-08-13 against
  `~/dev/Job apps/resumes/`: 08-09 **3 folders / 8 PDFs**, 08-10 **3 / 28**, 08-11 **5 / 24**, 08-12
  **4 / 18**. The former claim here — "nothing is generating Mit's résumés daily" — was **false**, and
  `PROGRAM.md` §2's output-side-first ordering argument rested on it (D-155). **Re-measure before citing:
  this is a fact about another repo's cron behaviour and it decays.**

---

> **A MANUAL RUN RACING A TICK EXITS 2 AND RESETS GATE P3**, and at 8 fires a day that is 8× likelier than
> it was. Check `launchctl print gui/$(id -u)/com.boardwatch.run | grep state` before starting one by hand.
> Two *scheduled* fires cannot collide — launchd never runs two instances of one label.

**THE LAUNCHD JOB RUNS AN EDITABLE VENV RESOLVING TO `src/` IN THE PRIMARY WORKING TREE**, so a scheduled
tick executes whatever branch is CHECKED OUT there. **Leave that tree on `main`.** Use a worktree for
parallel work, and never `git stash` — it is shared across worktrees.

**Every agent invocation needs BOTH `BOARDWATCH_DATA_DIR` and `BOARDWATCH_CONFIG_DIR` on a scratch dir**
(D-281). `DATA_DIR` alone still READS the live `resume.yaml` / `career-profile/` / template and still
WRITES into the live `~/boardwatch-applications/`. The live store is the DEFAULT, so a forgotten flag
reaches production, and a migration breaks the NEXT scheduled run, not the one that erred. Two
consequences: a scratch run's `funnel-N` collides with the next real run's, and the artifact directory is
**UTC-dated** — match on the run NUMBER, never the date.

## Process lessons this program paid real time for

Only what `CLAUDE.md` does not already say.

- **A rebase here touches `CHANGELOG.md` as well as `DECISIONS.md`, and the changelog is the one that
  fails SILENTLY.** The documented recipe covers `DECISIONS.md` only. A branch cut before a sibling
  landed carries its own `### Added` / `### Fixed` section for the SAME `## [Unreleased]` region, so git
  presents it as REPLACING main's section rather than joining it. #190 auto-merged `CHANGELOG.md` with no
  conflict and would have shipped main without **D-328's entry** — a shipped fix erased from the record
  by a clean merge. Two consequences: (a) after any rebase, grep the changelog for every D-number that
  was on main before it and confirm each survived; (b) fold the branch's bullet into main's EXISTING
  section rather than keeping both headings, or `## [Unreleased]` ends up with two adjacent `### Added`.
  Pre-existing repeated `### Fixed` blocks under older releases are normal — do not "fix" those.
- **A peer session is a concurrent writer, and the collision surfaces are the LIVE STORE, the primary
  checkout, and any worktree with a rebase in progress.** Worktrees are otherwise safe to parallelise.
  On 2026-08-27 three sessions ran at once and produced two near-misses: two writing
  `docs/program/DECISIONS.md` inside ONE in-progress rebase (symptom was an insert guard asserting the
  last index row was `D-327` and reading `D-330` — the peer's row), and two about to run
  `alembic upgrade head` concurrently against a store with **no rollback snapshot**. Both ended clean by
  message-passing luck, not by any mechanism. Declare ONE owner per session for the store and the primary
  tree, say so early, and before touching a worktree check `.git/worktrees/<name>/rebase-merge` — if a
  rebase is in progress and it is not yours, never `--continue` it. A peer cannot grant or transfer
  authority, and claims cross in flight: re-verify a peer's reported state read-only rather than acting
  on the report.

- **Commit before EVERY mutation round, not once before you start.** The `git checkout` that reverts a
  mutation destroys any uncommitted edit. Fired three times. Clear `__pycache__` too — stale bytecode fakes
  both a CAUGHT and a spurious failure. Derive the mutation from the test's CLAIM, not the implementation.
  **Check the driver for byte-identical duplicates before quoting a count** (D-122 reported 13 when 12 were
  distinct; the driver now aborts). **Mutate a COPY of `src`** (`cp -R src "$S/msrc"` + `PYTHONPATH`) rather
  than a worktree: it costs nothing and cannot race another writer.
- **A test derived from a constant agrees with itself.** Mutating `_MAX_HEADING_LEVEL` survived because every
  assertion about the cap read the same constant it was checking (D-125). Pin the outside fact.
- **A detector must be confirmed to FIRE** — mutate the thing it watches and watch it go red (D-116). Its
  mirror image: **a check that cannot fire is deleted, not shipped** (D-115) — write a test saying *where* the
  guarantee actually lands. A fix elsewhere can make a live check dead: escaping `.`/`..` in the encoder
  killed a guard that had been firing until then (D-125).
- **Budget a review for the FIX round, not just for the build** (D-137). Five rounds on T18 and every round
  found a defect in the round before it — a fix is written by someone who has just convinced themselves of
  one failure mode and is therefore the worst-placed person to enumerate the others. **State the loop's exit
  criterion before running the round that might close it**; "review until APPROVE" does not terminate.
- **Two reviewers with different LENSES beat two sequential rounds** (D-125). Reviewers that RUN the code find
  what reviewers that read it cannot (D-111). **Verify a finding's premise before ruling on it, including a
  reviewer's** — lens B's count and extent were both wrong (D-134). **Give the reviewer the attack list**: a
  reviewer told only "review this" reviews the happy path.
- **Enumerate the arms from the code's own catalog, not from the reproduction you were handed.** Replaying a
  reviewer's probe is a regression check, not verification. Probing eight of twelve commands and generalising
  is how D-138's fix was first written too narrow to reach `promote` and `rebase-draft`.
- **Look for the same thing under two names, and for a deletion that is really a rename.** Two byte-identical
  `OSError` helpers; a test `main` deleted that a branch kept; `main` fixing the FIFO in `rebase._tree_contents`
  while T16 fixed the same defect in the `storage.py` copy it had MOVED. **Two independently-green branches
  rewrote the same guard and neither was a superset** — resolve as the union, not by picking one.
- **Resolving conflict markers is not resolving the conflict** — files sit at `UU` until an explicit `git add`,
  which a passing test run will not tell you. **Sweep every `quoted_yaml(` call** in any branch being merged;
  a line-based grep gives false positives, only the suite settles it.
- **`git add -A` and `git add -u` both sweep another writer's work.** Stage explicit paths, always. Run
  `git status` immediately after stopping any agent.
- **When two sessions share a clone, a position in `git log` proves neither authorship nor order.** Push an
  explicit sha (`git push origin <sha>:main`) so a concurrent commit cannot ride along un-gated.
- **Concurrent subagents and a gate contend for the same CPU.** Load average 21 stretched a 65-second suite to
  eight minutes and SIGTERMed a gate. Pin the gate to a sha in its own worktree; do not start a second heavy
  suite beside it.
- **Measure the spec's premise before building it.** D-098 priced a deferral with the wrong subsystem's
  figures (D-105); D-111 found PROGRAM item 6's authoritative signal was 0-for-11 on the real corpus and
  structurally unable to reach the column it reads. A spec written against another codebase's data is a
  hypothesis, not a requirement.
- **A scheduled job is a standing claim about the repo, and it decays** (D-123, D-135). A prompt naming a
  starting sha must self-check or be deleted after it runs.

### "Breadth is last" is RETIRED (D-391, owner's call 2026-08-31)

*Moved WHOLE from `STATE.md` on 2026-09-01e, unedited, when that file passed 250 lines again. Settled since 2026-08-31; kept because meeting the retired phrase in an old decision entry is exactly the moment a session needs this paragraph.*

The `CLAUDE.md` section is **deleted** and the live pointers in `PROGRAM.md` and `STANDING-FACTS.md`
are gone. It reasoned about an ASSUMED downstream; that downstream is instrumented now, so the
question is answerable with numbers per change instead of settled in advance by an ordering rule.
**Nothing replaces it** — input work is sequenced on measured evidence like anything else.

**The decision logs are append-only and were deliberately left alone**, so D-280, D-296, D-345 and
others still argue from the principle. **Meeting the phrase in an old entry does not make it
current** — D-391 is the reason. Still live, and stated where they belong: every quarantine needs a
drain designed in the same change; a cap never observed firing is unverified; the keystone invariant
is untouched.

### Negation over-reach on strengthening clauses — REAL, MEASURED at 0.33%, and deliberately NOT fixed

A third way a years bar goes unread, distinct from D-443's escaping and D-447's modifier window:
**a `negation_cues` member occurring in the unit outside the matched span, in a clause that
STRENGTHENS or scopes the requirement rather than negating it.** Confirmed by removing only the
cue clause and re-running `detect()`:

| as written | cue removed | the cue |
|---|---|---|
| `2–12+ years of industry software engineering experience (does not include internships or co-ops)` | **0 → 1** `scoped_range_years_minimum` | `not` |
| `8+ years in … data engineering, including 2+ years directly managing engineers (not solely projects or tech leadership).` | **0 → 1** `domain_years_minimum` | `not` |
| `5+ years in applied machine learning … end to end rather than one stage of a large team.` | **0 → 1** `domain_years_minimum` | `rather than` |

`does not include internships or co-ops` makes the bar HARDER and deletes it instead. The harm is
in the hiding direction — the bar goes unread, the lead lands `uncertain` with zero requirement
rows, which is **D-442's symptom from a third direction**, invisible to the abstain report for the
same reason the other two are.

**Sized before proposing anything, and the size is what decides it.** Over 900 bodies: **72 (8.0%)
carry one of the candidate phrases, and only 3 (0.33%) gain a detection when it is removed.** So
the existing rule is well scoped 69 times out of 72 — the cue usually sits in a different unit and
the detection survives.

**DO NOT add these to `negation_cue_idioms`.** An idiom makes the cue invisible to BOTH cue
searches, so a genuine negation spelled the same way is then missed — and `rather than` is a listed
cue precisely because *"we want X rather than Y"* is a real polarity flip. **Widening polarity is
the fail-dangerous direction**: the failure mode is reading "you must NOT have X" as a requirement
to have it. A 0.33% recall gain does not buy that risk. Recorded so the mechanism is never
re-derived, and so the next session does not mistake "small" for "unknown".

Splitter fidelity was established first, because the whole finding rests on it: over 400 bodies,
engine and a punctuation splitter agree **302** times, disagree **4**, and the engine finds
something the splitter misses **0** times.

### Three times in one session the APPARATUS contaminated the measurement, not the sample — and none of the three looked like a tooling problem

The four instances above are a *sample* being unrepresentative. These are a different family, and
they are harder to catch because the number that comes out is clean, specific and confident:

1. **Wrong scope.** A guard asserted that every sentence released from `ineligible` must contain a
   degree token. `abstain_by` is DOCUMENT-scoped, so the disjunction sits elsewhere in the body and
   the guard could not find it at any sample size. It nearly passed a change on false evidence,
   then nearly rejected the same change on false evidence.
2. **Wrong splitter.** A probe split bodies on `[.!?;:]` and reported patterns that "match but
   write no row". `detect()` splits by the SCOPE a pattern declares. Fidelity had to be established
   first — 400 bodies, agree 302, disagree 4, engine-only 0 — before any of those 4 meant anything.
3. **Wrong `sys.path`.** A verification printed "what the primary checkout's venv would give" and
   got a row identical to the branch under test, because `sys.path.insert` pointed at that same
   branch's package and `bundled_rules_text()` read it. **A verification step that silently
   verified itself**, and it was one message away from being reported as independent corroboration.

**How to apply.** Before believing a measurement, ask what the apparatus would print **if the thing
were not true** — the null control — and confirm it prints something different. (2) was caught by
running the engine's own splitter beside the probe's; (3) by printing the catalog version and
finding three distinct ones where a null control returns identical rows. **The tell they share is
that all three produced a number, not an error.** A component's self-report is not verification;
neither is a probe's.

### A control can be mis-specified in the SCOPE it asserts over — and then it fails in BOTH directions

The four instances above are all a *sample* being wrong while the test was fine. This is the other
kind, and it is worse because nothing about it looks like a test problem.

A peer session, wiring `degree_alternative_to_years` onto the six scoped/domain patterns that
lacked it, wrote a control asserting that **every sentence released from `ineligible` must contain
a degree token.** It failed — `4 years of experience developing` (×54), `8+ years of programming
experience`, `4+ years C++ experience`, no degree anywhere. The first reading was "the wiring
over-reaches".

**The wiring was correct and the control was measuring nothing.** `abstain_by` is
**document-scoped** by design — the catalog's own comment says an abstain escape *elsewhere in the
posting* may waive it — so the disjunction sits somewhere other than the waived sentence, and
checking that sentence for a degree token cannot ever find it.

**The same broken assertion had already nearly passed a change on false evidence and then nearly
rejected it on false evidence.** A control asserting the wrong scope is not conservative in either
direction; it is noise that happens to look like signal twice.

**How to apply:** when a guard asserts a property of a *thing*, state the scope the engine actually
evaluates that property over, and check the guard reads at that scope. Document-scoped waiving,
unit-scoped negation cues and sentence-scoped patterns are three different scopes in this one
subsystem, and a guard written at the wrong one returns confident nonsense.

### A sample selected by the thing you are measuring cannot measure it — four instances, and the fourth broke the circle from INSIDE the change

The same error four times in two days, each time producing a number that was true about the sample
and false about the population:

1. **D-437** — six companies read ~20% on target; all twelve read **3%**. The six were picked for
   looking promising.
2. **D-441** — hiring.cafe's own in-window view gave **1.42 postings per board**, a true number
   about the aggregator's window. Admitting a board scans its **entire open inventory**: the 50
   sized at 79 postings delivered **8,303**.
3. **D-443's first write-up** — `four (4) years` read clean at 9 sentences on a 487-lead sample;
   store-wide the form is **1,006 sentences** dominated by DUI-conviction boilerplate and
   `Four (4) year undergraduate degree`. A class read as safe on a filtered sample was not safe.
4. **D-445** — the `gh_jid` join keyed on `(company_id, gh_jid)` and returned a confident **zero**.
   A Greenhouse job id is unique across **Greenhouse**, not per company row, so the key hid the
   only case worth finding. On the right key: 4, and all 4 are one employer under two rows.

**The fourth is the one worth transferring, and it is not the join.** In D-443 the circle broke
because a **test refused an exemplar chosen for being representative** — `3\+ years of
non-internship professional software development experience`, picked as the commonest escaped form,
still wrote zero rows unescaped. That was not a test of the fix catching the bug; it was a test of
the stated REASON, and the reason is precisely what a sample gets wrong. Writing the assertion
before believing the claim is what forced the population read.

**So the cheap defence is not "measure twice".** It is: state the mechanism you believe, pick the
case you think most representative, and assert it *before* you believe yourself. Instances 1, 2 and
4 were caught by a second measurement, which is expensive and only happens when someone is
suspicious. Instance 3 was caught by a test, which is cheap and happens whether or not anyone is.

## Discovery, coverage and the board backlog

> Moved WHOLE from `STATE.md` on 2026-08-23d (Mit's ruling). Nothing was reworded; these are the
> measurements as they were recorded. Decision numbers resolve in `DECISIONS.md`.

**Discovery is budget-capped, and the backlog DRAINS on a known clock (D-270, confirmed D-271).**
`detail_fetch_budget` is **50** unseen postings per board per run, so a day's "new postings" figure measures
our throughput, not the market — 19 Workday boards sit at exactly 600 rows and gain exactly 50 × runs each
day. Run 67 left **15,535 listed postings unmaterialised** on 20 boards (Citi 1,614 … Fidelity 104), visible
only as prose inside `board_scans.error` and absent from the funnel. Every board's backlog falls
**monotonically, 26–49 per scan**; 15 boards have already drained. **ETA to empty: 48 more runs (~7 weeks at
1/day)**, worst board Citi. A contrary claim that Workday's newest-first ordering means tails are never read
was FALSIFIED by `posted_at` — Databricks reaches 2019-11, Cisco 2025-12, Adobe 2026-03; Citi is an outlier.
Budget-skipped postings are **not** falsely closed (0 closures on the 20 partial boards).

**Workday's own `total` is censored at 2,000 — the facet counts are not (D-271).** Summing a partition
facet's `values[].count` is a second, uncapped aggregation path, and the known-positive control PASSED
(Adobe 740/740, Intel 645/645, Regeneron 592/592, Fidelity 565/565 agree exactly). Measured: **Citi's real
board is 4,589 postings against 600 held — 13.1%**; NVIDIA 2,656 against 600. Our pager also wraps at
~2,000, so **after the backlog drains Citi stays at ~2,214 of 4,589 — a permanent, invisible hole that is
NOT the budget.** Mirror defect: Regeneron 101.4% and Fidelity 106.2% coverage mean we hold postings the
board no longer lists, because a permanently `partial` board never runs `_process_missing`.

**Seventeen boards produce nothing, and five of them report GREEN (D-271).** Snyk, Vercel, HubSpot, Plaid
and Qualcomm scan cleanly, carry `last_health='empty'` and a current `last_ok_at`, and have returned zero
postings across 12 scans — the dangerous class, because a board that fails loudly gets fixed. The other 12
fail outright with exactly {401 × 4, 403 × 1, 422 × 7}; **Workday sends 422 for a malformed request body,
not for auth**, so those seven are probably wrong slugs and therefore recoverable. No backoff, no
auto-disable, no quarantine — `get_watched_companies` filters on `watched` alone.

**boardwatch cannot see 92% of what job-apps surfaces, and that REOPENS D-008 (D-271).** Of job-apps' 530
eligible records over 2026-08-12…08-21, **41 (7.7%)** are at a company boardwatch watches; the set spans
**352 distinct companies** and boardwatch watches **24**. Largest missing: Amazon 25, TikTok 20, AWS 8,
Apple 7, ByteDance 7, SpaceX 6 — **none uses any of the six supported ATS**, so adding a slug cannot reach
them. Lane value by loss-if-removed: commercial aggregators 421 of 446, **GitHub new-grad lists 73 of 103
(19.1% of yield for ~5 public-repo GETs)**, direct ATS 5 of 14; cross-lane overlap only 5.8%. Where
boardwatch is BETTER: on greenhouse/lever/ashby it stores what job-apps title-filters away at fetch, and
job-apps' Workday lane is 3 hardcoded queries × 2 pages × 12 details = 77 roles over 39 boards with 16
returning zero. Counterweight: ~1/5 of job-apps' yield is staffing firms and list artifacts. **The 8-vs-42
shortfall is a SEPARATE problem** — `capped_by_top_n` is 3,502 and job-apps has no top-N anywhere, so
raising the cap matches volume but not parity (~8% overlap). **RULED 2026-08-22 (D-272): three lanes go in.** **The ORDER then reversed (D-278): Indeed via
JobSpy first**, because its body arrives free inside the search response; then hiring.cafe (one
unauthenticated GET); then the GitHub lists **last**, because they carry no body at all and 53.3% of
their active entries duplicate boards already scanned. The lanes exist to reach companies no
existing route can reach — Mit's ruling — and D-272's ordering was set on yield, not on that. **Bespoke first-party adapters are OUT** (Amazon/Apple/TikTok): job-apps'
own dead sources are *all* bespoke adapters or niche APIs, never aggregators. `PROGRAM.md` §4's three
blocking rows are struck.

**The coverage instrument is SHIPPED and ON `main` (D-271/D-272/D-273, PR #125, green under
`make check` and full CI), and D-274 makes it report itself unattended — see below.**
`boardwatch coverage` reports every watched board as a
**seven-way partition** — `measured` / `enumerated_only` / `censored` / `dark` / `stale` /
`unscanned` / `unreadable` — that never folds a bucket into a neighbour, and prints "not
measurable" rather than 0% or 100% when nothing can be measured. Four nullable `board_scans`
columns carry it, populated from values the six providers already computed, at **zero additional
HTTP cost**.

**The coverage instrument is ARMED and reports itself unattended (D-274, PR #127).** A scheduled run
writes coverage into the two artifacts it already produces — a `board_coverage` section in the funnel
(**`artifact_version` 5 → 6**) and a `## Discovery reach` block in the morning digest (**1 → 2**) — plus one
`board coverage →` line on stdout, which is what a launchd run leaves in its log. The report is loaded
**once** in `runner.py`'s `finally` and the same object renders into both, because `held` has no run
dimension and two loads seconds apart can differ; `boardwatch coverage --json` shares that serializer, so
the command and the artifacts cannot describe one number two ways. A coverage failure costs the
**section**, never the artifact. (`notify` was never a candidate surface — it is a standalone command,
`runner.py` imports nothing from it, and the plist runs only `run --project`.)

**Three readings, and they agree.** Store-copy rehearsal **82.7%** (26,183 of 31,643), buckets summing to
exactly 135 — measured 90 · enumerated_only 11 · censored 4 · dark 12 · stale 18. First live reading, run
68: **82.4%** (26,075 of 31,629), within 0.3 points of the rehearsal. Run 69: **76.5% over 37 measured
boards** (16,602 of 21,697). **Target is the largest hole in the corpus and was invisible before this
work: 12,097 stated against 649 held, 5.4%.** Worst *measured*: Capital One 34.7%, Wells Fargo 36.4%,
Salesforce 42.3%.

**The 76.5% is NOT a regression** — it is the design refusing to lie. Run 69 ran ~3 hours after run 68, so
**81 boards answered `unchanged`** against run 68's 18; a 304 carries no fresh total, so those go to
`stale` and the ratio is withheld rather than pairing a carried total with a live numerator. That is the
design's own "304 staleness" lie-vector, refused the way it was meant to be. `enumerated_only` fell 11 → 0
for the same reason: `stale` is a property of THIS scan and wins over any stored total. **A back-to-back
run therefore reports a smaller measured set**; on the once-a-day cadence it barely bites.

**Runs 68 and 69 were both MANUAL, so neither moved the P3 counter.** Run 68: exit 0, ~24 minutes, 135
boards attempted / 85 complete / 12 failed, 14,238 postings seen, `capped_by_top_n` **3,628** — even at 40,
that many postings clear every gate and are cut by rank alone. Run 69: exit 0, 22m29s, both artifacts
carrying the section and the two **byte-identical** (the single-load property, observed rather than
asserted). Both produced 40 leads / 40 PDFs, roughly the wall clock 8 leads used to cost. **Cross-run
movement is real and visible:** Capital One 34.7% → 37.4% (650 → 700 held), the detail budget draining
50/run exactly as D-270 predicts.



**TWO SCAN-ROBUSTNESS FIXES SHIPPED + LIVE (D-306 #167, D-307 #168, 2026-08-26).** (1) `apply.py` now collapses
a duplicate `provider_posting_id` within one board snapshot — a Workable board (`alexander-dennis`) that lists
one shortcode twice was crashing the whole run on `UNIQUE(company_id, provider_posting_id)`. (2) `_scan_body`
now isolates a board's `apply_board` failure per-board (count failed, continue) instead of aborting the run.
Both TDD, both merged and pulled to the primary tree. Neither is an eligibility module →
`engine_version` unchanged, no drain, freeze-safe. Found by firing runs, not by review.

**COVERAGE vs job-apps — RE-MEASURED, and the earlier read was WRONG ABOUT WHERE THE GAP IS (D-310/D-311).**
The prior note said native ATS imports "top out at ~40%" and that only the lanes could close the gap. The
39.6% was the CEILING, not the position: boardwatch was watching boards for only **58 of job-apps' 465**
(12.5%). Re-derived by keying each queue posting to the `(provider, slug)` boardwatch would use — for Workday
the FULL composite `host/tenant/site`, which an earlier pass got wrong by comparing bare tenants and so
counted already-watched boards as new. Result: **125 postings across 97 boards were addable with ZERO new
code**. Imported with `--verify`: **95 watched, 2 skipped** (Comcast dead, CMU errored), so the fleet went
**140 → 235** and projected scan time 20 → **33 min** against the 180-min cadence. These are employers
job-apps never TARGETED — it found them through Indeed/JobRight — which is why last session's import of its
222-company target list netted only +7 and this one netted +95.

**NEW ATS PROVIDER ADAPTERS ARE NOT WORTH BUILDING — measured, and it inverts the standing assumption
(D-311).** Owner-gated item 2 recorded Oracle Cloud HCM + iCIMS as "~45% of the non-six tail". That was a
share of a small tail, not of the market. Over job-apps' full **138,788-posting** ledger: LinkedIn **49.7%**,
Indeed **23.4%**, Workday 10.0%, Greenhouse 3.4%, company-custom 3.6%, Ashby 1.1%, **Oracle Cloud 0.84%,
iCIMS 0.44%, Eightfold 0.28%**, and every other platform below 0.2%. So the two "big" candidates are ~1.3%
combined. **~73% of the market is LinkedIn + Indeed**: Indeed is out of scope, and LinkedIn is already a lane
— which is where leverage actually is, now that it has a keyword facet. `lane_posting_budget` is OUT of
`config_hash` (manifest.py), so raising the LinkedIn body budget is freeze-safe and is the cheapest next
experiment. Do NOT build per-ATS adapters at 0.1–0.8% each.

**BOARD FLEET CLEANED + DOCTOR DETECTS MIGRATIONS (2026-08-24, D-300/D-301).** The 135 watched boards were
diagnosed: exactly **17 contributed zero** — not the 59 STATE claimed, which was a `postings_listed`-on-304
measurement artifact (the 118 `ok` boards hold 39,253 open postings). Root cause was ATS migration; **6
boards recovered (~3,522 postings), 11 dead unwatched → 124 watched, 0 dead/error/empty**. `doctor` now
suggests cross-provider board migrations (#161, D-301). Precision was confirmed **already armed** on `main`
(no move owed). PR #160 (community-home prep) merged. Part-4a's capped ramp is already shipped — see below.

> **D-291's "920 boards, 887 new" is real but its stated corpus is wrong**, and the difference is 4x. The
> figure is the **two new-grad lists' `active=True` records** (3,778 → 927 boards / 898 new, reproduced), not
> "all 6,088 active records" as the ruling reads. All four lists, unfiltered, give **3,881 / 3,813**. A board
> count needs its list set AND its `active` filter stated beside it. Full table in METRICS 2026-08-24.

## Precision gates — eligibility, role, location, seniority

**Eligibility now decides AND removes.** `work_authorization.needs_sponsorship=true` set (D-249); a
zero-evidence `eligible` abstains to `uncertain` (D-250); two rules that could never resolve MET are fixed —
`degree:any_degree_required` and `work_auth:sponsorship_available` (D-256, #107); and **clearance is armed as
a `blocker`** with `security_clearance={state:none,level:none}` (D-257) so the ~138 clearance-required
postings resolve UNMET → ineligible → dropped.

**Application-form questions are not in the JD any gate reads, and Greenhouse is the only board that exposes
them:** its public job endpoint returns the form (`?questions=true`), and a citizenship / US-person /
export-control question routes the lead to `_review` under `form_question_hard_stop` without ever writing a
verdict, because the keystone requires a quoted span from the frozen JD and a form is not the frozen JD. Every
other ATS's form is invisible to this repo, so a hard stop that lives only there is a permanent miss and a
human read of the form is the last gate.

**The role gate is tight and holding.** Four passes of SOFT denies — pre-sales/support/BD, non-eng
managers/directors, Data Scientist/Analyst, business/ops/admin/pricing, and bare `Lead`
(D-252/253/255/259/262). All 8 of run 66's leads were software, against 3 of 8 in run 65. The
`_NOENG` guard spares any engineering noun and is the correct multi-tenant form even where Mit's
`exclude_titles` would also catch it. **Deferred to owner** (borderline): Team Leader, Data Center Engineer,
bare Administrator. **NOT excluding "User Researcher"** — it overlaps real ML/Research *Engineer* roles.

**Hard location gate is US-only, ARMED and verified firing (D-251).** `config.toml`
`location_filter_mode=hard`; `rank/location_gate.classify_location` is a positive US allowlist (fail-open on
the unclassifiable, Mit's visa ruling). Default stays `soft` for other users. The funnel's stale "never
measured firing" note is now corrected (D-265) — that bucket carried 17,189 drops in run 66.

**Two real defects in that gate are fixed (D-263, D-264).** (1) **D-263:** `_alternation` built its pattern
without grouping the alternation body, so the word-boundary lookarounds bound only to the first and last
token and everything between matched as a bare substring. Region token `uk` fired inside `Waukesha` and
`West Milwaukee`, and the gate silently dropped **41 real GE HealthCare Wisconsin postings** — `Software
Engineer` among them. It was INTERMITTENT: which token lands last follows `frozenset` order under per-process
hash randomisation, so 43 postings' drop decision differed between `PYTHONHASHSEED` 0 and 4 — the same store
and code disagreeing run to run. (2) **D-264:** the deferred Buc/France leak is closed by three independent
non-US signals — 57 curated foreign city tokens, a structural ISO alpha-3 country code, and a new
`rank/foreign_ad_gate` reading DACH `(m/w/d)` / French `(H/F)` / `Ingénieur` off the TITLE (the only signal
that reaches three postings whose `locations_json` is exactly `["Remote"]`). Net **299 corpus drops, 36 US
false drops recovered, 280 of 444 `unknown` survivors still passing** — fail-open intact. `Dublin` and ten
other US-namesake names are left leaking BY RULING; the rejected list lives in the `location_data` docstring
so a later pass does not "complete" it.

**Seniority band = `entry` and internships excluded — SET and verified live (D-258).** `profile edit` proved
to be pipeable (NOT one of the TTY-guarded gates), so this was applied without Mit's terminal: band `entry`
activates the merged-but-inert gate (ambiguous level tokens like "Level 3" still ABSTAIN and pass — ladders are
not guessed), and `exclude_titles` gained `Intern`/`Internship`/`Co-op` (title-based, trap-safe; the engine is
body-only, below). **Done (run 65):** `ledger reopen --stale` released **19** decisions — the one-time
`policy_version` re-key the band + `exclude_titles` edit forced. **Done again (after run 67):** 16 more,
D-266's fingerprint re-key. `engine_version` feeds `policy_version`, so the drain is owed after ANY change to
it; a stamp mismatch never re-opens on its own, so no run self-heals this.

**The eligibility engine is body-only** — `preflight.py` feeds it `posting_versions.body_text` with no title
column — so title-based filtering (internship, seniority words) lives in the ranker (`exclude_titles`,
`role_gate`, `seniority_gate`), never the engine. job-apps (consulted this session) detects intern/co-op BY
TITLE for exactly this reason; boardwatch's body-only `internship_role_declared` is 100%-precision/~27%-recall
and already suppresses the "internships count" trap.

**Reviews of the precision merges have found five false-drop defects; all are fixed** — the US+foreign
location segment (#111), the seniority product-noun collision (#112), the `Lead` hole those reopened (#114),
and the location gate's two (D-263/D-264). **The zero-output guard was NOT changed, and B5 has no working instrument (D-282).** Two record
corrections. (1) **The false alarm is not reachable on this store, so it was never a P3 blocker** — firing
needs `hidden_handled == 0` (measured **8 / 48 / 128** on runs 68 / 69 / 71) and an empty shortlist
(`capped_by_top_n` is 3,603–3,683, so `visible` is 40 every run). (2) **The docstring's "D-246" attribution
was never a ruling** — D-246 is the seniority-gate decision and says nothing about this guard. The obvious
fix was built and **rejected before merge**: disarming on a rejection bucket makes the fatal UNREACHABLE,
because `hidden_hard_filter` is corpus-scoped — **18,472–18,932** when this was written at runs 68/69/71, and **60,491** at run 140 (D-412), the corpus having grown ~6x while the sentence did not. The RANGE rotted; the argument did not, and the argument is the point. **Root cause, and it
generalises: the `hidden_*` buckets are an EXHAUSTIVE partition of the corpus, so "can this run explain the
empty day?" is always yes by construction — a complete partition cannot evidence a silent failure.** Only
the stale-premise docstrings were corrected, at both sites. **Owner call: run-scoped rank attribution is the
only honest fix, and until it exists B5 is unscoreable.**


**D-305 IS SOUND — do not re-investigate the "analyst titles still delivered" report.** Verified against
the live module (`Risk Strategy Execution Analyst` → `not_swe`) and the delivery path (`runner.py:895` passes
no `include_non_swe`). All three offending artifacts are from **run 90, pre-fix**; post-fix runs 92–114 carry
**220 artifacts, 0 `not_swe`**. The remaining delivery-side leak is the 69 `uncertain` (31.4%), and the split
is **46 noise / 13 real SOFTWARE / 10 real NON-software engineering** — Mit ruled hardware and silicon are
noise for him, so the honest noise rate is **56 of 69 and only 13 are roles he wants**. (An earlier draft of
this file said "about half are real engineering"; that was wrong in the direction that mattered and is
corrected here — D-313.) A taxonomy fix would still destroy the 13. Noise concentrates in BOARDS:
**AlphaHire unwatched** on Mit's ruling (59 open, 0 `swe`), fleet 235 → **234**; Genentech and
Walmart-external measured and ruled KEEP. Delivery-side work is owned by a separate session.

**PRECISION LEAK (10.3% non-SWE leads) FIXED + MERGED + LIVE (D-305, PR #166 = `cbe6df9`, 2026-08-25).**
Two distinct leaks, two gates: (1) non-SWE families (analyst/specialist/administrator/advisor) — `role_verdict`
returned `"uncertain"` for no-signal titles absent from the deny catalog and `top_cmd.py:350` vetoes only
`"not_swe"`; fixed by a `_NOENG`-guarded deny in `rank/role_gate.py`'s `_DENY_FAMILIES_SOFT`. (2) eng-managers
were a SENIORITY-gate bug — the management-word guard was comma-scoped, so the INVERTED form ("Manager, Software
Engineering") shipped `in_band` while "Engineering Manager" was already `above_band`; the comma is the
discriminator, fixed in `rank/seniority_gate.py`. **Ranker-only — engine_version unchanged, NO drain**
(D-294/D-295). Opus-reviewed; verdict-neutral over 37,979 live titles (role `uncertain→not_swe` 2,150; band
`in_band→above_band` 386; **ZERO swe demotions, ZERO backward band moves, ZERO newly-shipped**). Pulled into
the primary tree this session, so the next scheduled tick runs it. **Cert (3 clean B1–B7 runs) counts from the
first post-(fill+role) tick = run 92.** THREE autonomous owner calls flagged for Mit's veto (see
`rolegate-nonswe-and-eng-manager-precision-shipped` memory): option-(b) seniority home for eng-mgrs; broad
families; the bare-`security specialist` carve-out reversal.

**RULINGS 1, 2 AND 4 SHIP; RULING 3 IS DROPPED (D-294/D-295). PR #148 MERGED.** The role gate denies
non-software title families and blocks `Team Leader`; the foreign-location gate gained a CJK-script signal.
**Ranker-only — `engine_version` unchanged (`1+63c6f8fd5a3e`), no ledger drain.** Ruling 3
(`company_title_location` suppression) was implemented, audited over three rounds, and dropped: no
body-similarity floor separates a repost from a second opening (populations overlap).

**Round 3 found a production defect in EACH half — three rounds, three defects, each invisible to the round
before.** The standing lesson is now explicit: **a review round is not finished until a round finds
nothing.**

- **Role gate:** the front-end rescue's head nouns were `(engineer|...|lead)\w*`, so `lead` was
  **`lead\w*` and matched "Leader"**, re-rescuing as `swe` the exact retail rows ruling 2 denies — the same
  failure as the `manager` token D-294 had already rejected. The comment two lines below *and* D-294's own
  record both asserted `\blead\b` does not match "Leader"; the code never had that property. Fixed by an
  inner group, **verdict-neutral over 27,680 unique titles**, 0 live hits today — only breadth would have
  surfaced it.
- **Ruling 3:** its floor was calibrated at min-true-duplicate 0.9421 vs max-non-duplicate 0.8986. Reading
  the body diff of all 40 suppressions below 0.945 found **9 are different openings** — GE HealthCare's
  Lubbock / Salt Lake City / Chattanooga postings (all `locations=["Remote"]`), a Capital One pair whose
  loser's own URL reads `Lead-Software-Engineer--Front-End`, Thomson Reuters Indirect vs Direct Tax. Non-
  duplicates reach **0.9372**: the window is ~0.005 and **the populations overlap, so no floor separates
  them**. The char→word metric change made it *worse*. And no test constrained the constant — any floor in
  (0.1915, 0.9550] left the suite green.

**Dropping ruling 3 dissolved both dedup findings at once**, because each followed from admitting a second
suppressing kind; a forced single-kind control returns byte-identical suppressions (566/566). The cost was
measured before the choice: delivered duplicate leakage is **3 of 146 = 2.05%**, inside Gate P6's 5% bar
**without** ruling 3. A redesign on the real discriminators — requisition slug, the body's own city, salary
band, YOE, all of which lie *outside* the similarity number — is **deferred, not dismissed**.

**The precision work is a PREREQUISITE for raising the cap, not a yield gain.** Measured against delivered
output rather than the corpus: 6 of the 146 résumés ever built were for roles the new gate rejects, and
exactly **1 of run 71's 40 leads** would have been denied. D-292's "51.1% carries no software signal" is a
property of the *uncapped* 3,771 — the ranker already sorts most of it below the cap.

**Standing tripwire (D-268):** all six known precision leaks are blocked by the current gates — five
non-SWE `Lead` titles in the role gate, GE HealthCare posting 31365 (`Buc` → `non_us`) in the hard filter.
Any of the six appearing in a funnel's `leads` is a real regression to investigate before anything else.

**THE UNCAPPED SET WAS MEASURED, NOT ESTIMATED (D-292), and the two figures differ by 4x.** Lifting
`DEFAULT_TOP_N` was considered against real numbers: **3,771 postings arriving ~220-430/day, of which
67.6% are `role=uncertain`**, so honest confirmed-software arrival is **~70/day**. **Quote neither figure
without naming its population.** The cap sets **burn rate, not supply** — long-run output equals the
arrival rate whatever the cap is. STATE carries only the live instruction not to move it (D-293/D-294).

## Lanes and JD acquisition

**A discovery lane without a JD body produces ZERO leads (D-272).** The eligibility engine is
**body-only** — `eligibility/preflight.py` selects `posting_versions.body_text` and passes it alone to
`evaluate`. A stub is a whitespace-only body (`count_stub_postings`; currently 17 of 30,243 = 0.056%), and
under D-250 a zero-evidence verdict abstains to `uncertain`. Aggregator postings arrive as title + URL, so
any of the three approved lanes shipped without JD acquisition would add corpus and surface nothing. This
MEETS the condition `PROGRAM.md` §4 set when it deferred the 2,200-line JD chain to "P7 where a non-API
source might first appear". **boardwatch needs far less than job-apps' 2,200 lines**: P7 already requires a
dereferencing step for any aggregator lane, and that same step is the fix — an aggregator link mostly
resolves to a Greenhouse/Lever/Ashby/Workday posting whose parser already exists. A link that resolves to
nothing parseable stays a stub and is REPORTED as one, never quietly dropped.

**The JD-acquisition design is RECORDED and awaits Mit's review (D-278):**
`docs/superpowers/specs/2026-08-22-jd-acquisition-design.md`. Four rulings taken — purpose (reach the
unreachable), lane order (reversed), a per-run new-company cap because adding a board IS breadth, and
UA scope (honest on the six providers, browser UA only on new aggregator fetches). The decisive
measurement: **job-apps' headless-browser tier is worth 13% historically and 0% currently** — dead
since 2026-08-11, 11 consecutive runs at zero, invisible because one `except Exception: return ""`
makes a missing dependency, a timeout and an empty page the same empty string. So the no-browser
rule costs almost nothing. But **job-apps has no generic careers-page extraction either** — 14
hand-maintained host regexes gate every fetch, and Apple and TikTok have no handling at all — so the
honest route to those companies is an aggregator that carries the body, not a page reader. Still
Mit's: whether **Oracle Cloud HCM and iCIMS should be PROVIDERS** instead of or before any lane
(~45% of the non-six tail, fits the existing architecture, reaches neither Amazon nor Apple nor
TikTok), and whether LinkedIn earns its per-posting request cost.

**Lane work has STARTED (D-279).** The precondition shipped (#132) and **plan Task 2 shipped
(#134)** — the ten-outcome acquisition catalog, `boardwatch.lanes.outcomes`, with a counter per
outcome and a reportable `is_silent_outage`. Phase 1 has **no network code**; the remaining tasks are
in `docs/superpowers/plans/2026-08-22-lane-groundwork.md`: **Task 3** the `Lane` protocol whose
`lane_snapshot()` makes `status="complete"` unexpressible, **Task 4** per-source stub attribution,
**Task 5** the company cap. **Two LIVE, revisable assumptions** — offered to Mit with the measurements, no answer in window:
**lane 1 does NOT use JobSpy** (`python-jobspy` pins `NUMPY==1.26.3`, newest wheel `cp312`, against
`requires-python >=3.11` / CI 3.13 / a 3.13.12 venv, so it cannot install on a supported interpreter
and would break the published package; its own HTTP stack also escapes the politeness lock — use the
`httpx`/`Fetcher` already shipped, which leaves every D-278 ruling intact since only the client
changes), and **the cap is 10 companies/run**. The Indeed client is deferred to its own plan whose
first step pins the GraphQL document and headers against the live endpoint — unverified here, and not
transcribed from a summary. Owed with the client, not phase 1: §4.5's four quality controls, §4.7's
browser-UA `Fetcher`, and a drain for any stub bucket the lane creates.



**THE LANE ROLE FACET IS BUILT — the lanes now ask for the USER'S target roles (D-309).** Both aggregator
lanes searched FACET-LESS, which returns the general labour market rather than the user's. Measured on the
live store 2026-08-26 over 282 open lane-provider postings: **3 `swe` (1.1%), 82 `uncertain`, 197 `not_swe`**
— and the three real ones (Siemens ×2 semiconductor digital-twin SWE, Zensar data engineering) are
US-eligible but rank BELOW the N=10 cap. **The gates were not rejecting software work; there was almost none
to reject** — lane discovery turned up zaxbys, dominos, twinkletoesnanny, best-choice-roofing. The delivered
non-SWE résumés (Business Unit Leader, Front Office Agent, Instructional Aide — runs 106/112) came through
the `uncertain` role fail-open, not a gate failing to fire. Fixed UPSTREAM: `lanes/facets.py` derives search
facets from `profile.target_titles_json` (never a query written into a lane — that is the multi-tenancy
requirement and why both contracts deferred it), and each lane issues one search per facet, interleaved so
the body budget reaches every facet. hiring.cafe uses the robots-**PERMITTED** path route `/jobs/{role}` —
its own `?searchState=` query search is `Disallow`ed, so the obvious build would have broken a compliant
lane. LinkedIn uses `keywords=` (owner-probed: baseline 0/10 SWE → keyworded **10/10**; `start` pages but
buys nothing against the body budget; `location=` is silently ignored so it is never sent). Live end-to-end
through the real lane on the live profile: **16 `swe` + 2 technical `uncertain`, 0 `not_swe`**, 13 of 14
facets contributing, 0 duplicate `provider_posting_id`. `engine_version` **verified identical**
(`1+63c6f8fd5a3e`) in both trees and no new `Settings` field, so **no ledger drain and no freeze change**.
GitHub-lists arming (+10 boards) and the one-off import of job-apps' targets stand from D-308: coverage of
job-apps' 465-item eligible set is **13.1%** (native ceiling 39.6%, aggregator-only 60.4%).

**LANES ARE RE-ARMED WITH THE FACET LIVE (2026-08-26 18:51Z).** `lanes_enabled = ["hiringcafe","linkedin"]`,
fleet **234** boards. #169 merged (`2895dec`) and was pulled into the primary checkout; the editable venv was
verified to resolve `lanes/facets.py` and to build both PROBED request forms
(`hiringcafe.com/jobs/software-engineer` and `?keywords=software%20engineer&f_TPR=r86400`).
**Run 115 (19:00Z) is the FIRST faceted tick and was still in flight at session close** — 1,088 body captures
in 27 min against 234 boards, `boards_attempted` not yet written. **VERIFY IT FIRST NEXT SESSION** with
`.agent/2026-08-26-lane-facet/verify_facet_run.py 115`, which reports lane yield by role verdict against the
1.1%-SWE pre-facet baseline. Note today has FOUR regimes and no figure may be compared across them: fleet
140→235 at ~11:40 CDT, AlphaHire unwatched ~12:10, lanes disarmed 12:10→18:51, facet armed 18:51.

**FACET CONFIRMED LIVE ON RUN 116 (2026-08-27 ~00:20Z).** 10 delivered leads, both lanes contributing
(hiringcafe 21 attempted/20 resolved, linkedin 36/18); **7 clearly software** (MAG Aerospace, GM Software
System Architect, MeeBoss, Kimley-Horn, KION Software Support, Cellebrite iOS Reverse Eng, Copeland) vs the
~1.1% pre-facet baseline. The 3 residual non-SWE (Humana, Raymond James, KION Commissioning) are the
`uncertain` fail-open; run 116 ran on veto-LESS code (the primary checkout was pre-#171 until session close),
so the NEXT tick runs the zero-signal veto (#171) against exactly those.

**PARTS 1, 2, 3, 4a AND 4b ARE COMPLETE.** Part 4a (GitHub-lists) landed #149/D-296. **PART 4b (LinkedIn) IS
BUILT (D-297)** — a lane sibling of hiring.cafe, OFF by default (`linkedin` not in `lanes_enabled`), **NOT
armed, never run live**. Built from D-290's recorded contract, not a fresh probe (Mit's "build from recorded
contract" ruling), so the card **selectors are RECONSTRUCTED, not freshly pinned** — arm-time live
verification is owed before enabling. Identity keys on the company **slug** (`externalApply`=0, no apply URL);
id from the URN not the URL tail; only `f_TPR=r86400` sent. No capture committed; authored fixtures. Next is
**Part 6** (freeze + 3 frozen B1–B7 runs), with Part 5 anytime.

**The lane (hiring.cafe) is BUILT but NOT ARMED and has never run against the live service.**
`lanes_enabled` defaults empty. Part 3's exit criterion 2 — a lead at a company none of the six providers
reach, carrying a real JD body — is **unevidenced**; a scratch run is owed before arming, and arming waits
on Gate P3 anyway. Detail: D-286.

**LANE-ACQUIRED POSTINGS CAN NEVER CLOSE, AND ABSENCE IS NOW PROVEN MEANINGLESS (D-314, extended
2026-08-27).** The mechanism is unchanged: `_process_missing` (`scan/apply.py`) is the only writer of
`status="closed"`, runs on **`complete`** snapshots only; `lanes/base.py::lane_snapshot` is always
`partial`; lane companies are upserted `watched=False`. **The new evidence is a natural experiment in
the store:** when the D-309 role facet changed what the lanes search for, **0 of 290** pre-facet lane
postings were ever re-seen — and probing 45 of them with the shipped prober found **40 alive (HTTP 200),
0 dead**. They did not close; we stopped asking. At 3h cadence a **live** lane posting is absent from
its own lane's results in **~19% of runs**, so a `CLOSE_AFTER_MISSES=2` analogue would have destroyed
**25 live postings in 33 hours**. **Age-based and missed-run closing are therefore REJECTED by
measurement, not merely unproven — do not propose either again.** The class was 282 at D-314 and is
**471**, growing **~182/day**. The honest predicate is `companies.watched = 0` ("nothing enumerates this
board") = **722 rows**, which includes ~274 unwatched `source='user'` companies with the identical
defect — `source='lane'` is wrong in both directions. **Owner ruled 2026-08-27: build the `unverifiable`
label (#186/D-324), promote registry-ATS lane companies (DONE — 15 of them), and add the 6.7%-power URL
probe (#187/D-325). He did NOT choose to cap how long a lane row stays DELIVERABLE — the only option
that shrinks the pool. Worth re-raising.**


## CI health

**CI health — the nightly's THREE causes are fixed (D-269); #95 closes on a green scheduled run.** It had
failed **7 of its last 8** scheduled runs, which is not intermittency: ubuntu always passed, so every cause
sat in the schedule-only jobs and `make check` stayed green locally throughout. (1) A **production defect** —
`ensure_schema` runs alembic through an engine alembic builds itself, so the pragma listener never fires and a
store is **created in `delete` mode**; the deferred switch to WAL is a *conversion*, which no other
connection's lock permits (raises after the full busy timeout against a reader, **instantly** against a
writer), so two processes opening a fresh store race and the loser cannot open it. Mit's live store already
reads `wal`, so nothing needs migrating. (2) Five **deterministic** Windows `fs_safety` failures on all three
Windows jobs — `os.path.realpath` rewrites `/data` to `\data`, so the POSIX fixtures collapse onto the root
mount and the `None`-expecting cases passed **vacuously**. (3) tectonic: `actions/cache` only saves on a
**miss**, so the minimal-`article` warmup bundle was frozen forever and every run fetched the template's real
packages over the network — one hiccup cost ~52 render tests. **Windows/macOS evidence comes ONLY from a
`workflow_dispatch` of `ci.yml` and the nightly itself** — never from a PR's checks. **That evidence is now
IN: run 32514934447 is the first fully green full matrix — all 12 jobs, windows and macos 3.11/3.12/3.13
included.** Windows 3.11 went from 5 failed / 6888 passed / 50 skipped to **7003 passed / 58 skipped / 0
failed** (50m19s → 35m08s); the +8 skipped is exactly the eight `fs_safety` cases marked, so the pass is for
the right reason. **#95 stays OPEN by design** — `nightly-watch` is schedule-only, so it closes only on a
green scheduled nightly.

## Windows and the lock reclaim window

**Windows is best-effort (D-212)** — in the nightly, out of the pyproject classifiers, caveated in README. A
`nightly-watch` job files a "Nightly CI is failing" issue on a failed scheduled run and closes it on recovery
— **#95 is OPEN now** (the two CI flakes above); it will auto-close on the next green scheduled run.

**The stale-lock race is FIXED at the root; all four `xfail` markers are gone on `main`** (D-224/227).
`core/lock_reclaim.py` owns the constants — **1.0s on `win32`, 0.0 elsewhere, so POSIX is bit-identical**.
Windows evidence comes only from a `workflow_dispatch` of `ci.yml`. **One false-refusal exposure is left
standing DELIBERATELY (D-224):** POSIX `UnixFileLock` unlinks before releasing the flock, so a live-holder
handoff can report `bundle_lock_held` while nobody holds the lock. **Ruled: record, do not widen.**


## Résumé, bundle and render tracks

**The bundle → résumé + projection + render tracks are COMPLETE and merged; nothing is queued there.** Gate B
is **MET** (0 blockers, D-201); 11 entities refined within the 220-char ceiling; projection reaches the daily
pipeline behind opt-in `run --project` (D-225); the render stack shipped ATS-parsable PDFs (D-233),
`fill_to_page` (D-234), `link_in_first_bullet` + `sort_projects_by_date` (D-235). **What is left on the résumé
is Mit's alone**: whether to send a document, and the two owner-gated prose rewrites of D-220. `resume.yaml` is
an import source, never hand-fixed (D-155).

### Reference facts (do not re-derive)

- **Bundle track:** live revision 22, 11 entities. Do not quote its digest (restamps daily, D-017); re-derive
  with `profile-bundle inventory`. Facts stay `owner_attested` (D-191). Editing is incremental (D-190):
  `checkout --draft` → `edit-fact` → `validate --draft` → Mit's **TTY** `approve` → `promote`. `approve` does
  NOT validate; a plain `validate` cannot see Gate B; `_catalog_admits` is a DIFF — always `validate --draft`
  and diff the blocker COUNT before Mit approves.
- **Stage 2** is live; the one-page budget is a **character** budget ≤ **3,439** (D-219). `mean_per_bullet` is
  the default scorer; `ADMISSION_FLOOR` stays `Decimal(0)` (D-197/8).
- **P5b criteria NAMED (D-229):** 3 clean projected runs, ≥30 postings, 0 preflight fatals, 0 résumé-QA
  failures, 0 fabrications. Four of five evidenced on a store copy.
- **Settled — do not reopen:** Projection (D-156/163); Gate A MET (D-157); autonomous backlog COMPLETE
  (D-202…D-210, D-237); Education Slice C (D-239); D-184 finding 2 (D-238).
- **Fixture + corpus drift (D-228):** R13/R14/R15 in `tools/generalization/fixtures.py`. The corpus content
  pin was re-recorded this session for the m0105 fix (987 rows unchanged). **On 2026-09-11** the greenhouse
  fixture reds `make check` (enforced at `fixtures.py` R15, `now > review_by`) — and that tripwire already has
  its drain: `python -m tools.fixture_refresh --extend <provider> --days N --reason "..."` records an audited
  extension, or re-check the live API and re-record. **The corpus is regenerable in principle:** only
  `scratchpad/gen_corpus.py` is missing — its inputs all survive in `.agent/p2-catalog/` (`proto.py` the
  oracle, `matrix.py`, `adv.py`). They are **gitignored**, so a `.agent/` clean is what would make the 987-row
  oracle truly unrecoverable; committing a generator plus its inputs is an owner call, not done.


**THE DELIVERY QUEUE + LOCAL REVIEW WEB APP SHIPPED, ARMED AND POPULATED (D-318, PR #173 = `0361145`).** A
second root `~/boardwatch-queue` holds COPIES of every delivered-unapplied lead (résumé, apply link, frozen
JD, `details.json`), deduped by canonical `job_id`; the dated tree is NEVER touched (freshness/verify/the B4
fabrication audit all key on it). `boardwatch web` serves a triage queue + per-run diagnostics on loopback
with a per-install 0600 token; `prime_queue` runs on startup. `engine_version` unchanged, no ledger drain,
freeze-safe; the write surface is confined to the queue root (audited). Armed at session close: primary
checkout fast-forwarded to `0361145` and the queue primed to **588 leads**; served on a FREE port because the
owner's Bridge server holds the default 8787. The `finally`-block hook refreshes it every tick. A pre-existing
latent flaky test was fixed in the same PR (`test_contention_is_not_a_failure`, `Console` width pin vs a deep
xdist tmp path → raised to 10_000; the rebase was innocent).

**P4 CRAFT UNDER-FILL FIXED — the daily run now fills résumés to the page (D-303, 2026-08-25).** The P4
blind review FAILED on ~3 under-filled résumés: the daily run projected with base `projection.yaml`
(`runner.py:848`), whose `fill_to_page` defaults False; the earlier fill fix went only to the DORMANT
`projection.sde/ios/data.yaml` (persona routing is unwired — D-304). Fix = added `fill_to_page: true` +
`sort_projects_by_date: true` to base `projection.yaml`, owner-reapproved (digest `87513b4d`→`e61a1956`,
stamp on disk). Config-only; **no engine_version change, no ledger drain; freeze-safe.** Verified via a real
render path (thin postings 3→7 entries; compiled PDF 1 page) and the whole delivered set audits clean.
Fill overflow reviewed: it CANNOT ship 2 pages (two independent gates: select `_grow` + `run_tailor`
re-gate). First delivered filled résumés = the first scheduled tick after the 01:25 UTC approval (run 90
finished 01:21, pre-approval; a phantom run 91 took the id — see below), i.e. **run 92 onward**.

**PERSONA ROUTING INTO THE RUN — DEFERRED by owner (D-304).** `select_persona`/`apply_persona` run only in
the `tailor` REPORT path; the daily-run PROJECTION path is persona-blind and nothing maps
role-family→`projection.<persona>.yaml` (those 3 files are dormant). D-303 fixed the under-fill uniformly, so
per-persona projection is emphasis polish, not a fix — deferred; a real-discriminators redesign is future work.

## Moved out of STATE on 2026-08-28d — settled, kept verbatim

These blocks were true when written and remain true; they stopped being *what changed this session*.
Nothing was summarised away (the STATE rule): each is the paragraph as it stood.

**RUN 127 LANDED THE WHOLE ELIGIBILITY STACK AND D-333 IS CONFIRMED BY MEASUREMENT.** Run 127 is the
first tick on engine `1+118c640ea50c` (derive it, never quote it — D-306): `ok`, **91m03s** against a
~116 min projection, 346 boards, 13,518 postings seen, 1,418 new, 340 closed. **Every required years
row with a threshold ≤ 3 flipped disposition `unmet` → `unknown`** — 10,757 → **0** unmet, 10,880
unknown — and **6,123 evaluations moved `ineligible` → `uncertain`** against D-333's predicted 5,980
(within 2.4%; the population itself grew by 126 in the same span). Corpus-wide `ineligible` fell
36,141 → 30,068. **Zero of those 9,324 evaluations became `eligible`**, which is the first EMPIRICAL
confirmation of D-333's central claim — until now it was only a code argument about `blocking(UNKNOWN)`
being tested before the `eligible` fallthrough. The 91-vs-116-minute result also means the linear
scaling model **over-predicts by ~22%**; do not size off it without that correction.

**CI IS SHARDED AND THE PR LOOP IS 3.3x FASTER (D-334, #198).** A pull request was **30-42 min**;
per-step timings showed the whole of it was one step (`pytest -n auto` at 1764/2480/1903s, everything
else totalling ~20s) on a **4 vCPU** runner. There was no hot spot to remove — the slowest single test
is **1.5%** of total CPU and the top 25 are **9%** — so the suite is split 4 ways per Python by SHA-256
of the node id. **Measured: 10.6 min.** Lint, all three `type` jobs, gitleaks, perf, generalization and
web bundle now report in **under a minute** instead of behind a 30-minute job. **Branch protection now
requires ONE context, `ci`** — not the six `test (3.x, ubuntu-latest)` ones. Shard count is **4 and that
is measured**: at 8, seven jobs queued behind the ~20-job concurrency ceiling, and since wall clock is
bounded by concurrency rather than by slicing, 8 paid double the per-job setup for the same ten minutes.

**THE LIVENESS PROBE THIS FILE SHIPPED WAS WRONG, AND IT FAILED TOWARD "SAFE TO WRITE" (D-335).** The
`awk '$2==1'` form below reported IDLE for the whole of run 127. Use the argv[0]-anchored form; the
reasoning is in D-335 and the block under **Next action** now carries the correct one.

**ANOTHER SESSION RAISED `detail_fetch_budget` 50 → 400 IN THE LIVE CONFIG (2026-08-28, not this
session).** Mit's local config only — deliberately NOT the code default, which would change behaviour
for every user of the published package. Backup: `config.toml.bak-predetailbudget-20260828`. **MEASURED on run
128: it is NOT a one-off.** The run took **132 min (+41 over baseline)** — workday alone burned 19,225 s of
cumulative fetch (~80 min wall at 4 workers) — and `board_scans.detail_deferred` is **still 9,261 after the
run**, so the budget is a per-run ceiling that does not drain the backlog. Runs stay ~2h+ every run, not
once. **`lane_search_pages = 5` and `lane_posting_budget = 300` are set in the same local config** (D-340).
The measurements land under **D-336 onward** and **METRICS 2026-08-28c**; this file does not restate them.

**THE LIVE STORE WAS WRITTEN BY ANOTHER SESSION AFTER RUN 127 (2026-08-28).** Prior application
history imported (`applications` 0 → 22, all `attempt_no = 1`), and `identities backfill` run for the
p6.3 bump. **The backfill wrote p6.3 BESIDE p6.2 rather than replacing it** — `write_identities` only
deletes rows at the SAME version — so there is no window where suppression is off and old and new code
both work. **The dead generation has since been REAPED (#201):** `posting_identities` went 899,983 →
**423,706 rows, one generation**, in 9 s, and suppression stayed armed throughout (84,821 of 84,821 open
postings carry a p6.3 identity). `boardwatch identities reap` reports by default and deletes only under
`--apply`; it reaps **retired VERSIONS only** and deliberately never touches a closed posting's
current-version rows, because a reopen would take the corpus below `identities_complete()` and disarm
dedup store-wide. **It does not VACUUM** — pages return to SQLite's free list, the file does not shrink.
Numbers and reasoning are that session's, under **D-336 onward**; this file does not restate them.

**THE CADENCE CHANGE CUT AGGREGATOR INTAKE ~8x, AND THE MECHANISM IS RUN COUNT, NOT A BUDGET.** Moving
from ~8x/day to 1x/day on 2026-08-27 was decided on gate-speed grounds (local runs contend with the
local gate: the same suite measures 4m51s idle and 34m40s under load) and the intake consequence was
never costed. **Do not attribute it to `lane_posting_budget`** — that was checked and is NOT binding:
`body_fetched` was 55 on run 126 and 56 on run 127 against a budget of 60 (LinkedIn 49 and 53). What
caps a lane is that neither paginated its search. **THE LINKEDIN HALF IS NOW FIXED (D-340, #205):**
`Settings.lane_search_pages` ships defaulting to **1 — byte-for-byte the old behaviour**, page 0 emits
the URL unchanged rather than `&start=0`, so no other user's request SHAPE moves. Mit ruled **5 pages
+ `lane_posting_budget` 300**, both set in LOCAL config. **hiring.cafe stays one page and that is
STRUCTURAL, not a knob** — `robots.txt` disallows its `?page=` form and no pagination parameter was ever
found. **The cost is WALL CLOCK, not request count:** `Fetcher` already paces 1.0 s per host and
LinkedIn is one host, so ~370 requests/run against ~74 is **~1 min → ~6.2 min** of a run. **The CI work does NOT weaken the original
justification** — `make check` is still local and still contends.

## Moved out of STATE on 2026-08-28e — CLOSED blocker rows, kept verbatim

Three rows from STATE's `Live blockers and carried gaps` table that had reached `closed`/`done`.
Moved rather than summarised, per STATE's own rule when it passes ~250 lines. Nothing was
deleted and no wording was changed.

| Item | Detail | Owner |
|---|---|---|
| **A metric that could not fail (D-267)** | `grep -ic buc funnel-N.json` was read as a Buc count; it counts the word "bucket" and is 4 on runs 61/63/65/66 regardless. The funnel enumerates **no ranked pool** and a `leads` row carries **no location** — so the hard location gate, the one gate whose failure is a visa-ineligible lead, leaves no trace in its own artifact. Closing it needs `locations` on `Lead` + an `artifact_version` bump. **Re-raised 2026-08-21c; still Mit's.** D-268 corrects this row's replacement metric too: "0 of 62" had the 0 robust under every bounded rule (27/27/69/70 matched, 0 surviving) but the **62 unreproducible** — match rule and corpus size were never recorded beside it, and a bare substring gives 103 matched / **39 surviving**. A ratio now records its match rule AND corpus size. **CLOSED 2026-08-27 (D-323): artifact v7** — `leads[].locations` (`null`, never `[]`, when the posting names no place) + `leads[].location_class` from the production `classify_location`, and `manifest.location_filter_mode` so the verdicts are readable. The Markdown names its match rule and corpus size, per this row's own lesson | **closed** |
| ~~Five boards GREEN-and-zero + 12 dead~~ **RESOLVED (D-300)** | Diagnosed 2026-08-24: root cause is ATS migration, not typos. The 5 empty — HubSpot→`greenhouse:hubspotjobs`, Plaid→`ashby:plaid`, Vercel→`greenhouse:vercel` recovered; Qualcomm/Snyk unwatched. The 12 error/dead were all Workday: **5 GATED (401/403, unrecoverable)**, 7 wrong-site (422, recovered walmart wd504 + veeva→lever + purestorage→greenhouse, rest unwatched). Watched 135→124, **0 dead/error/empty**. `doctor` now suggests migrations (D-301, #161). Backoff/quarantine still absent but the fleet is clean | done |
| ~~`top`'s drain flags break in ~2 days~~ | **CLOSED by #145** (D-289): all six corpus-sized `IN` lists chunk through `store/param_chunks.id_chunks`, three merge shapes each mutation-tested, including `reopen_jobs`' summed rowcount | done |

## Moved out of STATE on 2026-08-28e — settled GATE/CI/tooling procedure, kept verbatim

Three long rows from STATE's `Live blockers and carried gaps` table. They are settled procedure a
fresh session needs when it runs a gate, not standing that changes between sessions, so they belong
here — STATE passed ~250 lines again and its own rule is to move settled blocks out rather than
summarise them away. Nothing was deleted and no wording was changed. (STATE's duplicate
`add-evidence` blocker row was also dropped; it is stated verbatim in STATE's owner-gated list.)

| Item | Detail | Owner |
|---|---|---|
| **Disk pressure now costs GATE TIME, silently** | The same suite ran **4m51s** at ~7.4 GiB free and **34m40s** at 5.7 GiB / 98% — no error, nothing logged, and a bounded waiter timed out, which reads as a hang. Cause was pytest's own temp trees at **1.1 GB** across 5 runs in `/private/var/folders/*/*/T/pytest-of-mitsheth/`; clearing the stale ones (keep the newest, it is live) plus branch cleanup took the volume to **9.1 GiB / 96%**. **RE-MEASURED AND CLEARED 2026-08-27: the same trees had grown to 4.9 GB across 15 runs** — 4.5x the figure that first caused this — and removing all but the newest took them to **5.4 MB** and the volume from **15 GiB to 20 GiB free**. Do this after any session that runs several full gates; it is the cheapest gate-time win there is. **The "two stale store backups, 1.67 GB" clause is STALE and is retired here** — no `.db` backup exists beside the live 3.1 GB store, only small yaml/profile ones. **There is therefore still no rollback snapshot** (take one before any destructive operation) | **tooling** |
| **CI is sharded and gates on ONE context (D-334)** | Branch protection requires `ci` and nothing else — not the six `test (3.x, ubuntu-latest)` contexts, which no longer exist. `ci` carries `always()` and derives what should have run from `github.event_name`, because **GitHub counts a SKIPPED required check as SUCCESS**. Two standing prohibitions are commented in `ci.yml` and are load-bearing: **no `if:` on `ci` beyond `always()`** (a condition there erases every gate at once) and **no `continue-on-error` on any job in its `needs`** (it makes a failed job report `success`). Shard count lives in ONE place, the `plan` job — a workflow-level `env` CANNOT be read from `jobs.<id>.strategy`. **Read CI job conclusions from `gh api .../actions/runs/<id>/jobs`, never `gh pr checks`**, which has misreported on this repo | tooling |
| **`make check` must be launched DETACHED** | the Bash tool clamps `timeout` to ~10 min; a longer gate reads as `make: *** [test] Error 143` — that is SIGTERM, not a build break. **`setsid` does not exist on macOS**: use `nohup sh -c '<export PATH>; make check > LOG 2>&1; echo $? > DONE' & disown`, set PATH INSIDE the subshell, and gate on the sentinel file, never the launcher's exit code. The clamp is WALL-CLOCK, so CPU contention converts a comfortable run into a kill — a suite that ran 5m17s alone was SIGTERMed at 62% while one subagent ran its own pytest. Never pipe the gate through `head`/`tail` | tooling |

### The mobile detail sheet's focus containment (moved from STATE 2026-08-28e, verbatim)

**THE MOBILE DETAIL SHEET IS FOCUS-CONTAINED, THE ONE THING #213 DISCLOSED RATHER THAN SHIPPED
(D-348, #216).** Below 64rem the pane is a full-screen sheet, i.e. a modal, and `Shift+Tab` reached a
grid row behind it — after which the single-key `a` acted on a row the reader could not see. Fixed
with the platform's `inert` on the four covered subtrees, **breakpoint-scoped**: zero inert subtrees
at or above 64rem, where the pane is a side-by-side column and containing focus would break the
Enter-then-↓ path. `SIDE_BY_SIDE` is exported and read by the pane's own focus effect so the Tailwind
`lg:` variants and the inerting cannot disagree. **The toaster is deliberately NOT inerted** — it
draws above the sheet and holds the only undo a mark-applied has. **Verified in a browser with a
non-vacuity check**: stripping only the four attributes reproduces the bug (covered row 20483 gets
focus and `a` marks it applied, 347→346). Chromium only; the pre-existing Escape-restores-focus bug
was proved pre-existing and left alone.

### The slate cap's body-less guard (moved from STATE 2026-08-28e, verbatim — D-345)

**THE GUARD THAT MADE THE CAP SAFE WAS FOUND BY MEASUREMENT, NOT BY DESIGN.** `content_hash` is NOT
NULL and never empty (0 of 96,767 open), so its presence proves nothing — **every body-less posting
hashes the empty string.** All **245** body-less open postings carry the same `e3b0c442…855` digest
and the corpus already holds **six colliding `(company, title, hash)` groups**, one of them a
`software engineer frontend` pair that could reach delivery. Uncaught, the cap would have dropped a
real distinct lead while claiming its JD matched. A body-less posting is therefore **never capped**,
reusing the `body_empty` flag the ranker's select already computes. Fail-OPEN, for the reason a
span-less `INELIGIBLE` downgrades to `ABSTAIN`.

### Which eligibility policy you mean (moved from STATE 2026-08-28e, verbatim — D-350)

**SAY WHICH ELIGIBILITY POLICY YOU MEAN, EVERY TIME (D-350).** The catalog and the live profile diverge
on **five of six** families: `rules.yaml` has `work_auth` as its only `blocker` default, the live store
has all six. The divergence is BY DESIGN — the catalog is the multi-tenancy artefact and arming is a
per-user act — but an unqualified severity claim is not checkable, and the gap is wide: #218's widened
floors give **1,228 verdict flips under the live policy and 0 under the published default**. Read the
store for what a RUN will do, `rules.yaml` for what a NEW USER gets, and record which one produced any
verdict count.

### Breadth re-check, 2026-08-28e — Mit's instruction was DOCUMENT NOW, ACT NEXT SESSION

Measured by a parallel session (`boardwatch-52`) and handed over at its close. **Re-derived here where
cheap; attributed where not** — the two figures below marked *verified* were counted independently
against the live store, the rest are that session's and are owed a check before anything is built on
them.

| quantity | value | provenance |
|---|---:|---|
| watched boards (fleet) | **344** (was 346) | **verified** here |
| open corpus | **96,767** (was 84,821) | **verified** here |
| company reach vs job-apps | **~10.1%** — supersedes the stale **7.7%** | relayed by that session from a PRIOR one (two hops), **NOT re-derived — owed a check** |
| fetch-latency backlog, deferred postings | **18,787 → 5,227** | **verified** here, both ends |

**The backlog drain is monotonic, which the two endpoints alone did not show.** Summing
`board_scans.detail_deferred` over `scan_kind='board'` per run:

| run | boards | `detail_deferred` |
|---|---:|---:|
| 126 | 346 | **18,787** |
| 127 | 346 | 17,411 |
| 128 | 345 | 9,261 |
| 129 | 344 | **5,227** |

So the `detail_fetch_budget` 50 → 400 raise is draining the backlog rather than holding it flat, and
**the drain is nearly done** — which matters for sizing the next run, because run 129 still carried
~27 min of catch-up and run 130 should carry materially less. `7.7%` remains the only company-reach
figure that has been counted twice; **~10.1% has been counted once, in a session that relayed it.**

**Remaining reach work**, from `.agent/2026-08-28-coverage-dedup-session/B-discovery-miss.md`
(~28 misses/day, and the class is **company reach, not ATS coverage**):

- **~22 misses are addable by simply adding a supported-ATS board** — a named list is in that doc
  (RTX, UCF, HP, Bosch, Siemens Healthineers, Domino's, ModMed, …). This is the cheap half.
- **~122 aggregator-URL misses need a dereference step** on the linkedin/hiringcafe lanes; low volume
  today.
- **~33 are unsupported-ATS and OUT OF SCOPE** — no new adapters (D-272).

**Note when starting this:** the slate cap (D-345) has not yet been observed firing on a single
run, so its behaviour under a wider input set is unverified.

### The in-flight-run liveness probe (moved from STATE 2026-08-28e, verbatim — D-335/D-024)

   **Before ANY pull or store write, guard on PROCESS liveness, never the `runs` table:**
   ```sh
   # ALIVE if this prints a PID; empty = idle.
   ps -o pid,command -ax | awk '$2 ~ /\/python[0-9.]*$/ && /boardwatch run --project/ {print $1}'
   ```
   Anchored on **argv[0]**: a real run has `argv[0] = .../.venv/bin/python3`, every decoy shell has
   `-c`. The `awk '$2==1'` form was WRONG in the dangerous direction (D-335) — it keeps only
   launchd's direct children, so it reported IDLE for all 91 minutes of run 127, and manual
   invocation is now the common case. On macOS do NOT use `ps -o comm` (truncated path, matches
   nothing, false IDLE). `runs.finished_at` precedes process exit by ~90 s (D-024).

   **`pkill -f "make check"` is NOT worktree-scoped** and will kill a parallel session's gate in a
   sibling checkout, where it reads as an unexplained `Error 143`. Kill by PID.

   **The scratchpad directory is SHARED with subagents, not per-agent.** A PR-body file written to a
   fixed name was overwritten mid-task by a worktree agent this session. Name per-launch files
   uniquely — gate logs, sentinels and PR bodies alike.

## Moved out of STATE on 2026-08-28f — settled 2026-08-28e shipments, kept verbatim

> Moved, not summarised: all four shipped, were verified, and are now either observed on a
> run (the cap, the cost split) or closed with no follow-up owed (the detail sheet). STATE
> keeps one line each; the account lives here.

**THE GUARD THAT MADE THE CAP SAFE WAS FOUND BY MEASUREMENT (D-345).** `content_hash` is NOT NULL
and never empty, so its presence proves nothing — every body-less posting hashes the empty string, so
all **245** share one digest and **six `(company,title,hash)` groups already collide**, one a
`software engineer frontend` pair. Body-less postings are exempt, fail-OPEN. Detail in
`STANDING-FACTS.md`.

**EACH LANE NOW REPORTS ITS COST SPLIT INTO FETCHING AND APPLYING (D-346, #217), AND THAT SPLIT IS
THE INSTRUMENT THAT CLOSES THE LANE QUESTION — NOT AN EXTRA.** D-343 left the lane stage's 6.5 min
unexplained because a stage total cannot separate upstream throttling from contention on
`apply_board`. `fetch_seconds`/`apply_seconds` per lane do, and the markdown names the fetch SHARE
because the ratio is the diagnostic. `None` = NOT MEASURED, never `0.0`. `ARTIFACT_VERSION` stays 7.
**No run has exercised it yet — read it on the next run before proposing anything else about lanes.**

**THE LANE FETCHES NOW OVERLAP, AND THAT LEVER IS NOW CLOSED (D-347, #219).** `_collect_lane` split
into `_fetch_lane` (off-thread) and `_apply_lane` (main thread only); fetches in a
`ThreadPoolExecutor`, applies in the consuming loop — `scan/coordinator.py`'s shape.
**`apply_board` remains the single writer** and a test COUNTS concurrent entries into it rather than
reading the code. **This was not the owner-gated pacing change:** `Fetcher` holds a per-host
`threading.Lock` for a request's full duration with `_pace` INSIDE it, so same-host requests still
serialize and the 1 req/s contract is untouched — concurrency across lanes adds **no** third-party
load. **Sized before building and the answer is modest:** run 129's hosts were ~85 (hiringcafe) and
~166 (linkedin) requests, so the pacing floor moves from their sum (251 s of a 390 s stage) to their
max (166 s) — **~2.2 min, ~4.9% of a 44.7 min run**. The stage is now **tail-bound on LinkedIn
alone**, the same shape D-344 found for the scan and `lowes.wd5`. **A third lane would be nearly
free; more lane parallelism buys nothing. Do not re-propose it.**

**THE MOBILE DETAIL SHEET IS FOCUS-CONTAINED (D-348, #216)** — the one thing #213 disclosed rather
than shipped. `inert` on the four subtrees the sheet covers, **below 64rem only**; the toaster is
deliberately excluded because it holds the only undo. Verified in a browser WITH a non-vacuity check
(stripping the attributes reproduces the bug). **Closed, no follow-up owed**; the full account moved to
`STANDING-FACTS.md` rather than being summarised away.

**FOUR MERGES FROM THIS SESSION, EVERY ONE GATED WITH A REAL EXIT CODE 0, PLUS ONE FROM A PARALLEL
SESSION.** #215 the slate cap (D-345) · #216 the detail-sheet focus containment (D-348) · #217 the
per-lane cost split (D-346) · #219 the lane fetch overlap (D-347). **#218 (years patterns, D-349) is a
PARALLEL SESSION's.** #219 was re-gated AFTER an `--onto` rebase onto the post-#217 `main`, because
#215 also touched `runner.py` so the merge candidate differed from the tree first gated — a clean
rebase can still break semantically. **All five verified present in `main` by CONTENT, not the PR page**
(pushing to a merged PR's branch lands nothing, silently): `main` `a1a69ff`.


## Moved out of STATE on 2026-08-28f — Gate P6's clause table, MET and unmoved, kept verbatim

### Gate P6, clause by clause

| Clause | Standing |
|---|---|
| Duplicate leakage over 7 days ≤ 5% | **MET 2026-08-27 — the span now exists (ledger 2026-08-19 → 08-27 = 8 days): 601 surfaced / 600 identified / 600 distinct / 0 redundant / 0.00%.** The blindness below is unchanged and is now MEASURED rather than argued: #185 adds a never-folded `candidate_redundant 7 / candidate_identified 610 = 1.15%` upper bound over a **0.50%** truth. Original standing: **CANNOT FAIL FOR ONE CLASS — see D-294 before quoting it.** `identity_queries.py:296` hardcodes `kind == "exact_quad"`, so a job whose only identity is `company_title_location` lands in `unidentified` and can never be counted redundant. Ruling 3 stopped those duplicates reaching leads but did NOT extend this metric, so it reads 0.00% for a structural reason. Measured honestly over the 146 delivered résumés (grouping by company+title+location) the real figure is **3 redundant = 2.05%** — under the bar, not zero. Extending the query reverses D-132/D-283 mid-gate and is the owner's. Original standing: **measurable, awaiting span (D-283).** `boardwatch identities leakage [--days N] [--json]` ships. **Live: 100 surfaced jobs / 100 distinct `exact_quad` groups / 0 redundant = 0.00%.** Only `exact_quad` counts (Mit's ruling, ratified); counted over jobs that REACHED LEADS, not the corpus; body-less jobs sit in their own `unidentified` bucket, never folded. **Not yet "over 7 days"** — the ledger starts 2026-08-19 so ~3.2 days exist, and the 7-day `seen` TTL cannot be observed faster than itself. First true window **~2026-08-26**, inside Parts 2–4, so off the critical path |
| **0** dead postings reaching leads | **MET (D-281).** Two runs on a scratch store copy: `checked 40, dead 0, unknown 2, alive 38, gone_after_redirect 0`, identical in both, agreeing across three read paths (funnel JSON, funnel markdown, stdout). Detector demonstrably ARMED — `checked > 0`, so not the disarmed 0/0 signature. The `runs` table has no liveness columns, so no DB-row path exists; those three are all there are |
| Injected hash-collision test | **MET** (D-100) |
| Audit of 20 sampled suppressions | **MET** (D-101) |

---


## Moved out of STATE on 2026-08-28f — the batch-2 discover sizing, superseded but kept verbatim

> Superseded by the concrete 39-board breadth prep (STATE's breadth item and
> `.agent/2026-08-28f-degree-audit/breadth-add.yaml`), which carries measured provider
> costs rather than an estimate. Kept because the cold-Workday timing question it raises
> is still open and still unmeasured.

8. **Batch 2 of the ~765 discover candidates is still a sizing question with an answer** — the ~325
   cheap ones go in ONE batch; SmartRecruiters 107 ≈ +40 min; Workday 333 ≈ +122 min and must be
   chunked at ~100. **Probe ~10 cold Workday boards first** — no cold Workday or SmartRecruiters
   board has ever been timed, and they are the two providers that burn a per-posting detail budget on
   a first scan.

## Moved out of STATE on 2026-08-28g — settled run-safety and worktree craft, kept verbatim

Carried unchanged out of STATE's "Next action" §2 when that file crossed 250 lines again. None of it
is a next action — it is standing craft that applies to every session that touches a live run, a
store, or a gate.

**Before ANY pull or store write, guard on PROCESS liveness, never the `runs` table** — the probe,
why the `awk '$2==1'` form was wrong in the dangerous direction (D-335), and why `ps -o comm` gives
a false IDLE on macOS are all in the "Liveness and the ledger" section above. `runs.finished_at`
precedes process exit by ~90 s (D-024). **`pkill -f "make check"` is NOT worktree-scoped** — kill by
PID.

**The venv is EDITABLE, so a branch switch MUTATES a live run's code and `rules.yaml`.** While a run
is in flight, do not check out any branch whose diff touches `src/boardwatch/**`. Park on the branch
the run started from; use a WORKTREE for parallel code work. The Bash tool's cwd also PERSISTS across
calls — use absolute paths for writes.

**The scratchpad directory is SHARED with subagents, not per-agent.** Name every per-launch file
uniquely; a shared *sentinel* is worse than a shared log, since reading it means reading someone
else's exit code.

**The 04:00 tick runs whatever branch the PRIMARY checkout is parked on.**
`~/Library/LaunchAgents/com.boardwatch.run.plist` invokes
`<repo>/.venv/bin/boardwatch run --project` by absolute path, and that venv is
editable, so the primary checkout's branch IS the unattended run's code and `rules.yaml`. **Park the
primary checkout on `main` before ending any session** — it matters more from ~2026-08-31, when a
branch left checked out changes every subsequent run rather than one. Pointing the plist at a
worktree pinned to `main` would close it mechanically, but that moves a scheduled job and a venv and
must keep the same config/data dir, so it is **Mit's call and has not been taken**.

## Moved out of STATE on 2026-08-28h — settled Phase 1b and deflake history, kept verbatim

Both items were retired in STATE on 2026-08-28h to keep that file under its own ~250-line rule. The
operative half of item 6 — the standing rule about what a timing test MEASURED versus what it CLAIMS
— deliberately stayed in STATE; only the incident history moved here.

### Phase 1b, complete including its follow-up (from STATE item 5, verbatim — D-354, D-359)

5. **PHASE 1B IS COMPLETE AND SO IS ITS FOLLOW-UP — retire the whole item (D-354, D-359).** Split
   #195, redesign #223, per-row hold reason #224, `ROLE VETOED`/`OFF TARGET` duplication #230.
   `role_vetoed` and `role_unconfirmed` stay separate — only `not_swe` is a veto. **#230 is
   deliberately NARROWER than D-354 specified: suppression is keyed on the `role_vetoed` MEMBER, not
   the review lane, because `classify` reaches `ineligible_verdict` and `non_us_location` first and
   either can carry a genuinely separate `off_target`. Do not re-broaden it to the lane** (D-359).

### `main` is green, and it took three fixes not two (from STATE item 6, verbatim — D-357, D-358)

6. **`main` IS GREEN — confirmed, and it took THREE fixes, not two (D-357, D-358).** Three
   consecutive green `main` runs after the deflake. The flakes were #225 (lane cost boundary), #227
   (`test_a_locked_store_answers_503_without_stalling`, which took all three macOS jobs at once —
   macOS runs unsharded) and **#222's own new pacing test**. **No threshold was weakened**; each is
   strictly tighter than what it replaced.

## Moved out of STATE on 2026-08-29 — settled lane and degree findings, kept verbatim

### The lane question, closed (from STATE current standing, verbatim — D-346/D-347)

**THE LANE QUESTION IS CLOSED (D-346/D-347).** Run 130's linkedin lane is
`fetch=277.3s apply=0.22s` — **100% fetch**. The lane stage is entirely upstream throttling and there
is **no contention on `apply_board`**, so D-347's estimate holds and no further lane work is
warranted. Do not re-propose lane parallelism.

### `degree` audited and closed (from STATE current standing, verbatim — D-352, #221)

**`degree` IS AUDITED AND CLOSED — NOTHING NEEDED SOFTENING (D-352, #221).** D-351's audit is DONE
and the item it raised is RETIRED. **Zero SWE-titled postings are blocked by any degree rule
anywhere in the live corpus.** Of 164 in-field `unmet` postings, 71 are sole-cause and every one was
read by hand: all non-SWE (accounting 24, finance/tax 12, nursing 11, engineering 11, other 13).
The abstain side costs 6 SWE postings and all six abstains are honest. **Two extraction defects were
fixed anyway, for MULTI-TENANCY not for Mit's yield** — the `education` surface matched equivalence
boilerplate (~1,200 frames vs ~57 genuine) and the relatedness escape could not read
`other`/`another` (483 postings). **One widening was REJECTED as measured NET HARMFUL:**
`degree_equivalence` for "equivalent combination of education and experience" would turn **30 `met`
rows into abstains to rescue 13 `unmet`**. Do not re-propose it without sentence-scoping it first.


## Moved out of STATE on 2026-08-29b — D-361/D-362's settled unattended risks, kept verbatim

*Closed by D-362 and not to be re-raised. Kept here because the REASONING — re-measuring a premise
before re-asking the question — is the transferable part.*

> **D-361's two unattended risks are ANSWERED AND CLOSED — do not re-raise either (D-362).** Both
> were re-measured before being re-asked and **both premises had moved.**
> **Disk is not a near-term risk:** **83%, 35 GiB free**, not 99%/3.8 GiB — real, not purgeable
> (`diskutil` 37.1 GB free; `tmutil listlocalsnapshots /` returns none). ~31 GiB was freed from
> **outside** this project, so do not credit boardwatch or assume it repeats. **The store did not
> grow** — 4,222,877,696 bytes is **3.93 GiB**, D-361's own figure, and 4.22 GB decimal; **quote the
> byte count when a size is load-bearing.** Runway **~70 days** worst-observed, ~250-640 at steady
> state, against the 8-19 that made it urgent. **Mit's call: no retention policy.** Guard stays
> unshipped.
> **Alerting is ARMED.** "No alerting path at all" was **wrong** — it generalised from the notify
> tiers to the whole system. The heartbeat (**D-260**, #110) was always wired **inside** `runner.py`,
> gated `summary.fatal is None`; it was off only because `BOARDWATCH_HEARTBEAT_URL` was unset. **Now
> set in the launchd plist and verified** — `launchctl print` shows launchd holding it, and a ping
> through `send_heartbeat()` returned `True`. The monitor alerts on a ping's **absence**, so a missed
> tick, a dead run and a sleeping Mac are all externally visible. **Disarm = delete the key + reload.**
> Tiers stay off: inert here, the job never invokes `notify`.
> **STILL OWED: confirm the first REAL ping landed.** Checked 2026-08-29 00:05 CDT and **the tick
> had not fired yet** — it is 04:00 daily, so the first unattended one was still ~4 h out. A setup
> ping already made the check green, so green alone still proves nothing.
> **`launchctl list` col 2 is the WRONG route and the previous version of this line was wrong to
> name it** — it printed `0` for a job that had **never run**, because `0` is that column's initial
> value after a `bootstrap`. Use `launchctl print gui/$(id -u)/com.boardwatch.run` and read
> **`runs = N`** plus `last exit code`; cross-check the **mtime** of `~/Library/Logs/boardwatch-run.log`,
> never its content, which survives reloads. At the check above, `runs = 0`, `last exit code =
> (never exited)`, log mtime 08-28 06:13.
> **Arming re-verified and the tick pre-cleared:** `launchctl print` shows launchd holding
> `BOARDWATCH_HEARTBEAT_URL`; `send_heartbeat()` reads env at CALL time, gated `summary.fatal is
> None`; `tectonic` resolves under the plist's hand-listed `PATH` (so "render tool unavailable"
> cannot fire); the editable venv resolves to this checkout and it is parked on `main`.
> **It cannot false-alarm on hiring.cafe** — a lane outage never sets `fatal` (verified).


## Moved out of STATE on 2026-08-29c — settled blocks, kept verbatim

### D-363 boundaries + suite

**THE WEB VIEWER NOW HAS ERROR BOUNDARIES, AT FOUR SCOPES (D-363).** D-360 named the structural
gap and left it open; it is closed. A component that throws while rendering now costs a card, not
the page: root, route switch, review lane, detail pane, each keeping a different thing alive. The
review lane is contained SEPARATELY from the apply lane on purpose. **Verified by reproducing the
pre-#232 defect** — 408 apply rows survived, and removing that one boundary took them **408 -> 0**.
**The "no frontend test suite" gap this left open is now CLOSED (#241).** vitest + jsdom run as a
`web-test` prerequisite of `make check` and as a CI step (nothing in CI runs `make check` on a PR). Eight
tests cover the four boundary scopes and the skew guards, and **each was confirmed RED against the broken
implementation** — removing any one boundary, or tightening any `== null` to `=== null`, fails the suite.
`make check` now needs node, deliberately not conditional: a check that skips itself where the toolchain
is missing reports green while verifying nothing.

### six-blocker map

**The live six-blocker map is the OWNER'S and is NOT to be reverted (D-350 found it, D-351 rules
it).** D-350 found `degree` armed where D-321 had recorded *"Owner's call, not taken"*; Mit confirmed
he wanted it. His constraint was precision — *"I just don't want it to reject jobs which are
genuinely for me"* — and D-352 above is the audit that answers it.

### main-is-green flake history

6. **`main` IS GREEN** — three consecutive green runs; which three flakes, and why each fix was
   strictly tighter, moved verbatim to `STANDING-FACTS.md` 2026-08-28h (D-357, D-358).

   **The standing rule, three instances behind it: when a timing test flakes, ask what it MEASURED
   versus what it CLAIMS** — all three measured a proxy whose noise straddled the bound, and none
   needed a wider bound. **A failure UNDER a sleep-derived bound proves the measurement wrong, not
   the machine slow.** **And mutate every new assertion:** two of the three also had the expected
   value reachable by a route the test did not intend (a constant the implementation also reads; a
   delay set equal to the floor it was meant to prove was overridden).


### breadth item-4 sizing detail

4. **BREADTH BATCH 1 IS APPLIED; BATCH 2 REMAINS DEFERRED — 39 boards, TWO batches (D-367).**
   Re-derived read-only from job-apps' `dedup_ledger.sqlite` and written to
   `.agent/2026-08-28f-degree-audit/breadth-add.yaml`; import with
   `boardwatch companies import --verify <file>` (`--verify` probes each board and skips anything
   unproven). **The cross-reference had to be NORMALISED:** boardwatch stores a Workday slug as the
   full composite `{tenant}.{wdN}.myworkdayjobs.com/{tenant}/{site}` while a job URL gives
   `.../[locale/]{site}`, so comparing raw marked **Micron and HPE as addable when both are already
   watched**. Normalising moved 14 into a duplicate bucket. Toyota IS a real addition — the tenant is
   watched at site `tmna`, this is the sibling site `tmna_professional` (the HPE precedent).

   **It is two batches because s/board is a lying unit:** ashby 7 + greenhouse 6 + lever 2 = **15
   cheap boards** (~30 s of added fetch) versus **20 workday + 4 smartrecruiters** that are COLD,
   spend `detail_fetch_budget` on a first scan, and have **never been timed cold** (STATE's own open
   question). **Batch 1 (the 15 cheap boards) SHIPPED 2026-08-29 — fleet 344 -> 359**, all 15
   re-verified `watched=1` against the source YAML rather than trusting the command's own report.
   The cold-scan objection was CHECKED and is **provider-specific**: only `workday` and
   `smartrecruiters` spend `detail_fetch_budget`, so the cheap batch carried none (D-367).
   **Batch 2 (the 24 cold boards) stays deferred** on the unchanged reason — hiring.cafe is still
   refusing us and those boards have never been timed cold. Not re-litigated.
   **Note: the slate cap is armed but has still not been observed FIRING.**

### D-361 disk half

> **D-361's two unattended risks are ANSWERED AND CLOSED — do not re-raise either (D-362).** Both were
> re-measured before being re-asked and **both premises had moved**: disk is **83%, 35 GiB free** with a
> ~70-day worst-observed runway (Mit's call: **no retention policy**), and alerting was never absent —
> the **D-260 heartbeat** was wired inside `runner.py` all along and is now armed in the launchd plist.
> The full reasoning moved to `STANDING-FACTS.md` at the 2026-08-29b close. **Edit that plist TEXTUALLY**
> — PlistBuddy strips the comments that carry the reasoning.
>

## Moved out of STATE on 2026-08-29d — settled, kept verbatim

These blocks were true and stayed true; they were moved whole, not summarised, because STATE
passed its ~250-line ceiling again. Each one's reasoning lives in the decision it cites.

### The slate cap firing (D-345 observed effective)

**THE SLATE CAP HAS NOW FIRED — D-345 IS OBSERVED EFFECTIVE, AND THE OPEN TEST IS CLOSED.**
`hidden_slate_cap` = **5** on run 131, against 0 on run 130. `SLATE_CAP_PER_KEY = 1` is per-key and
independent of N, so widening the slate to 40 (D-366) made the collision surface: the cap deferred 5
leads that were the same company, title and byte-identical JD as one already on the slate. STATE
carried this as *"observed CORRECT, not yet observed EFFECTIVE"* with "the next location-split day"
as the outstanding test — **it closed as a free side effect of the cap change, not by waiting**.
Design detail is in `STANDING-FACTS.md`.

### The lane-down reading superseded by D-368/D-369 (D-356)

**The lane was down and it is not our bug (D-356).** Run 130 raised
`SearchPageError("every role facet yielded nothing (14 searched, 14 request failures)")` — a TOTAL
outage after working on every run through 129 (85 attempted / 79 resolved). Probed: `/jobs/` returns
**403 with Cloudflare's `Just a moment...` interstitial**, while `/robots.txt` returns 200 and
**explicitly `Allow`s `/jobs/`** — so boardwatch is fully compliant and this is bot protection.
**Re-probed 2026-08-28 ~19:20 CDT and it has NOT lifted** — same 403, and the response now also
carries `cf-mitigated: challenge` and `server: cloudflare`, which names the mechanism outright.
`/robots.txt` still returns 200 and still `Allow`s `/jobs/`. 2026-08-28 ran FOUR runs against a
normal cadence of one, so our own volume remains a plausible trigger. **Browser automation /
challenge-solving is out of scope and is not the answer.** This is half the lane coverage that
job-apps' daily edge comes from. **It cannot make a run fatal** — `is_systemic_scan_outage` reads
board counts only, never lanes — so it costs coverage, not availability.

### The web viewer's boundaries and test suite (D-363/#241)

**The web viewer's error boundaries (D-363) and its test suite (#241) are BOTH SHIPPED and settled.**
Four scopes, the review lane contained separately from the apply lane on purpose, and eight vitest
tests in the gate — each confirmed RED against the broken implementation. Moved verbatim to
`STANDING-FACTS.md` 2026-08-29c.

### The delivery cap at 40 in the plist (D-366)

**THE DELIVERY CAP IS 40 AGAIN, SET IN THE PLIST AND NOT IN CODE (D-366).** D-293 ruling 5 held
`DEFAULT_TOP_N` at 10 *until rulings 1-4 landed*; 1/2/4 shipped, 3 was dropped (#148) and answered by the
D-345 slate cap, and #218/D-333/D-352 landed since — **the hold condition is met**. The measurement that
decides it also **corrects D-281**: runs 120-130 delivered **100% same-day** (median 0.00-0.73 d, 0% older
than 7 d), so the ranker is **recency-dominated** and run 130's **4,801 `capped_by_top_n`** postings are
**permanently buried, not queued**. At N=10 every unattended day discards its own surplus. The cost is a
RANGE driven by **JD richness**, not the LLM lane: **+5% to +23%** of a run. **`DEFAULT_TOP_N` in code
stays 10** — that is Mit's review capacity, not the mechanism. **No hash moves, so the provisional-pass
counter is NOT reset.** Revert = delete two `<string>` lines from the plist.

### Breadth batch 1 applied (D-367)

**BREADTH BATCH 1 IS APPLIED — the fleet is 359, not 344 (D-367).** The 15 cheap boards (ashby 7 /
greenhouse 6 / lever 2) imported with `--verify`, all 15 re-verified `watched=1` against the source YAML
rather than trusting the command. **The cold-scan objection turned out to be provider-specific**: only
`workday` and `smartrecruiters` spend `detail_fetch_budget`, so the cheap batch carries none. **The 24
cold boards stay deferred** on the unchanged reason.

### PROGRAM.md's B5 row corrected (D-365)

**PROGRAM.md's B5 row was STALE BY 20 DECISIONS and is corrected (D-365).** It read "the instrument is
DORMANT, see D-282" long after **D-302 (#164)** armed the zero-output guard on run-scoped rank
attribution. B5 is **scoreable**. The general lesson: **when a program document cites a decision for a
capability GAP, verify the gap against the CODE — the citation dates the claim, it does not renew it.**
### Run 131, the first clean unattended tick (D-366 / METRICS 2026-08-29c)

**RUN 131 IS THE FIRST CLEAN UNATTENDED TICK AND IT VALIDATES THE CAP CHANGE.** 96.7 min against run
130's 137.2, **with 15 more boards and 4x the leads** — `unchanged` went 36 → 101 and eligibility was
not a full recompute. **`tailor` was 168.1 s for 40 leads = 4.20 s/lead**, so D-366's predicted
+5%-+23% landed at the **bottom** of its range: tailoring is 2.9% of the run. **`capped_by_top_n` rose
4,801 → 5,338**, so the reservoir refills faster than 40/day drains it — the cap was never what
rationed supply. **Read the STAGE, never the total**, when judging anything about fetching.
Numbers: METRICS 2026-08-29c.

## Moved out of STATE on 2026-08-30 — settled by run 133's readout, kept verbatim

These four blocks were live questions until run 133 answered them. Nothing is deleted; each is the
STATE text as it stood, with the run-133 confirmation already folded in where it applies.

**A FAILED RUN NOW RECORDS WHY (D-375).** Run 132 sits in the store as `status='failed'` with
`errors_json='[]'`. Five fatal paths set `summary.fatal` without recording it — including the standalone
`run_scan` in `scan/coordinator.py`, which is what actually wrote run 132. The fix is a **choke point in
the `finally`**, not five patches, because the failure mode is the sixth path someone adds later.

**`clearance_preferred` RESOLVES, AND NO LEDGER DRAIN IS OWED (D-372/D-373).** It was a resolver bug, not a
missing fact: 1,094 rows, 0 decided, ever — and the run-122 audit that called it "correct" was wrong.
Verdict neutrality proven structurally, over the corpus, and by live replay over 198 postings under three
policies (0 diffs). The drain is **decided NO on measured evidence**, and D-373 refines the convention: ask
what could DIFFER, not whether the version moved.
**Run 133 paid the re-evaluation and CONFIRMED both claims on live data.** `engine_version` moved to
`1+6a9fb2164f5b`; the full re-evaluation of 109,696 postings cost **1h52m52s**, inside the ~1h45m estimate
and far inside the heartbeat budget. **The resolver fix works**: `clearance:clearance_preferred` held
**1,094 rows, every one `unknown`, ever** — and run 133 produces `unmet`. **And it is verdict-neutral in
fact, not just in argument**: the candidate rate reads 64.4657% (run 133) against 64.4244% (run 131), a
ratio of **1.0006**. Subsequent runs fall back to ~45 min.

**RUN NUMBERING SHIFTED AGAIN — run 132 ALREADY EXISTS.** It is the 18:03-18:13 cold-Workday timing probe
from D-370, `status='failed'` via the systemic-outage predicate on a single board. **The 04:00 tick is run
133.** Any manual few-board scan writes a `failed` run this way, so `runs.status` is a poor forensic
instrument for the retrospective.
*(Annotation, not part of the verbatim text: run 133 has since RUN and finished `status=ok`. The
standing lesson is the last sentence — a manual few-board scan mints a `failed` run and shifts the
numbering, so never infer a run's health from `runs.status` alone.)*

**THE PROJECTION APPROVAL SCARE WAS FALSE, AND THE REAL RISK IS NOW GATED (#251).** `run --project` never
reaches the TTY prompt — it only READS a durable digest-keyed stamp, proven by run 131 delivering 40
projected PDFs with no TTY. The genuine hazard was that a code change to `ProjectionDeclaration`,
`stamp.py` or `yaml_writer.document_bytes` invalidates every user's approval **with `make check` green**,
because both digest tests were relative. Measured: under the mutation, 330 projection tests passed and only
the new literal pin failed.

## Moved out of STATE on 2026-08-30b — answered/settled, kept verbatim

Both were live questions that this session closed. The hiring.cafe HEADER experiment is answered
(negative); the LIVE decision that remains — the `/jobs/*` endpoint call, and whether to leave the
lane enabled — stays in STATE's Next action item 1, not here.

**THE hiring.cafe HEADER LEVER FAILED — D-369 IS ANSWERED AND CLOSED (#245).** Run 133 reproduced run 131's
failure byte for byte, so the header set is eliminated and **that experiment must not be repeated**. What
survives is the endpoint hypothesis and it is the **owner's**; the detail and the second, smaller
"leave the lane enabled?" decision are in Next action item 1. **Still no probing; browser automation stays
out of scope.**

**BREADTH BATCH 2 IS HALF APPLIED — the fleet is 379 (D-370).** 20 Workday boards in, 4 SmartRecruiters out,
because every SR board shares the ONE host `api.smartrecruiters.com` which `Fetcher` serializes, so 4 boards
cost more wall clock than the 20 Workday ones combined.

4. **BREADTH BATCH 2 IS HALF APPLIED — fleet 379 — AND THE SPLIT IS MEASURED, NOT GUESSED (D-370).**
   D-367's blocker was "never timed cold". It was timed: one batch-2 Workday board scanned cold =
   **604 s, 420/420 enumerated, `postings_listed` 400 (the detail budget saturated exactly), 20
   deferred** — so **a cold Workday board is bounded by the BUDGET, not by board size**. 20 × 604 s at
   run 131's 5.90x parallelism = **~+34 min of scan on the FIRST run**, decaying toward ~+5 min.
   **The 20 Workday boards are IN** (20 distinct `{tenant}.wdN` hosts, absorbed by `scan_workers=8`),
   all re-verified `watched=1` against the source YAML. **The 4 SmartRecruiters boards are OUT, and
   the reason inverts the intuition**: every SR board shares the ONE host `api.smartrecruiters.com`,
   which `Fetcher` serializes and `scan_workers` provably cannot help (D-346/D-347), so **4 boards
   cost more wall clock than the 20 Workday ones combined**. That SR figure is **DERIVED, not
   measured** — measuring it spends the cost the decision avoids. File:
   `.agent/2026-08-28f-degree-audit/breadth-add.yaml`.

## Moved out of STATE on 2026-08-30c — settled and held elsewhere, kept verbatim

Both are fully recorded in the decision log (D-376 and D-374 respectively), and the ordering
invariant additionally now has a BEHAVIOURAL test pinning the escalation's position, added with
#258. Kept here verbatim because both remain required reading before touching `runner.py`'s
finalize block.

**WHAT ESCALATES IS THE FINALIZE-BLOCK SLICE, NOT `summary.errors`, AND THAT WAS MEASURED.**
`summary.errors` accumulates every stage error — one dead board slug, a lane that could not collect, a
per-lead tailor degradation. Over the last 25 runs **nine carried a non-empty `summary.errors` and not one
of the nine was a finalize-block alert**; runs 124-128 each carried `plaid: HTTP 404`. Escalating that list
would have driven the monitor DOWN on five ordinary `status=ok` runs. **Consequence to know: a dead LANE no
longer reaches the remote channel**, only the digest — closing that means a lane-health *detector*, not a
wider payload. On run 133 itself the channel would have posted **nothing**, which is correct.

**THE ORDERING INVARIANT IS LOAD-BEARING AND A MECHANICAL REBASE BREAKS IT SILENTLY (D-374).**
`[form sweep] -> _emit_funnel -> _sync_queue -> [ALL soft alerts] -> _emit_morning -> heartbeat gate`.
The form sweep joined the head of that chain in T96: it used to run INSIDE `_sync_queue`, which put
it downstream of the artifact its counts belong in, so they reached a console line and nothing else.
It sits ABOVE `escalatable_from` and appends NOTHING to `summary.errors` on any path — deliberately,
because an unfetched form produces a HOLD at worst and a hold that did not happen leaves the lead
where it already was. **That placement is why it is not an exception to the invariant below**: the
invariant governs ALERTS, and the sweep raises none. An alert appended
BELOW `_emit_morning` still fires, is still recorded, and is **invisible to the owner** — which is exactly
how the queue-sync note and #249's intake-death alert shipped. Three separate branches tried to union into
that region this session and two would have landed below the digest. **Verify the order in source after any
rebase touching the finalize block; do not assume a clean rebase preserved it.**

## Moved out of STATE on 2026-08-30d — run 133's readout and the absent-owner correction, kept verbatim

Both are history once run 134 exists: the readout's numbers are in `METRICS.md`, and the
absent-owner correction is recorded in full as D-376. What stays in STATE is the LIVE half — that
`BOARDWATCH_ALERT_URL` is still unset and arming it is one plist line.

**RUN 133 READ OUT: THE DIGEST HALF OF THE ALERT CHANNEL IS ACCEPTED, AND hiring.cafe FAILED AGAIN.**
`morning-133.md` opens with `## Alerts`, above `## Discovery reach`, rendering the run's one alert — the
acceptance criterion for the ten 2026-08-29f PRs, met. The baseline is proven on the artifact:
`morning-131.md` is 489 lines with **zero** `## Alerts` sections, while that run's identical lane failure
sat at **line 1390 of a 1,390-line, 116 KB funnel**. Run 133 was clean — `status=ok`, launchd exit 0,
**1h52m52s** (inside the ~1h45m estimate), 379 boards / 271 complete / 21 partial / **0 failed**, 23,166
seen, 4,300 net-new, 1,053 closed, 40 leads with 40 PDFs, reach 88.1%. The heartbeat fired (`errors_json`
holds the lane failure and no `heartbeat:` entry, which a refused ping would have left, D-375).

**THE ALERT CHANNEL TO AN ABSENT OWNER WAS *NOT* CLOSED ON 2026-08-29f. IT IS CLOSED NOW, AND IT SHIPS
DISARMED (D-376, #258).** What 2026-08-29f closed was the channel to someone *sitting at the machine*.
Verified this session, every link: the digest is a file under `~/boardwatch-applications/<date>/` and
neither it nor `~/boardwatch-queue` is inside iCloud Drive, Dropbox or Google Drive; the heartbeat gate is
`fatal is None and funnel is not None and morning is not None` — **`errors` is not in it**, so a run raising
every soft alert still pings **green**; `runner.py` never imports `WebhookChannel`; and the plist declares
exactly two environment variables with no `com.boardwatch.notify` job. **Runs 130 and 131 are the proof it
already bit** — both `status='ok'` with a dead hiring.cafe lane, both pinged green.
**Scope the claim precisely: the uncovered class is NON-FATAL DEGRADATION.** The dead-man's switch does
work; a crash or a sleeping machine leaves no ping and healthchecks.io alerts inside 1 day + 2 h grace.

## Moved out of STATE on 2026-08-30d — window properties, kept verbatim

Permanent properties of the 1-run/day cadence rather than session news. Both remain required
reading before trusting a quiet morning or counting corpus-regression as coverage.

**A STEP DETECTOR CANNOT HELP DURING A CODE FREEZE — do not count corpus-regression as coverage
for these two weeks.** Firing on a >50% step between runs is the documented design
(`corpus_regression.py`, "this is a STEP detector ... fires roughly three times, then ... goes
quiet" — that is a stated limitation, NOT a defect, and a sweep has now mistaken it for one once).
But a freeze removes every mechanism that produces a step: a rules edit, a profile fact that stops
resolving, a taxonomy change are all changes the freeze forbids. What a freeze permits is gradual
composition drift, which a step detector is blind to by construction. Combined with its cold start
(dark until ~run 138), treat it as unavailable for most of the absence.

**THE 2026-08-27 CADENCE CHANGE SILENTLY RESCALED EVERY WINDOW, because they count RUNS not TIME.**
At 8 runs/day `INTAKE_DEATH_WINDOW = 3` and `DELIVERY_DROUGHT_WINDOW = 3` meant ~9 h; at 1 run/day
they mean **3 days**. `CORPUS_REGRESSION_WINDOW = 5` (needing 6 runs) went ~18 h -> **6 days**. And
`death_probe_budget = 50` went 400/day -> **50/day** against 75-384 new unwatched-company postings a
day, so `due` grows monotonically (run 133: `due=1139, attempted=50, refused=1089`). The probe drift
is bounded in importance by its own 6.7% detection rate. **Detection latency during the absence is
3 days, not hours** — worth knowing before reading a quiet morning as healthy.

## Moved out of STATE on 2026-08-30e — the completed mutation campaign, kept verbatim

The campaign is finished and `METRICS.md` holds the full per-area table; what stays in STATE is the
part still awaiting a decision (the two residuals). Kept verbatim because the conclusion — no
vacuous test, no live defect, and all eleven survivors to be KEPT because their redundancy is
contingent — is the thing a future session must not re-derive.

**THE GUARDS ARE PINNED — 145 MUTATIONS, 130 CAUGHT, NO VACUOUS TEST AND NO LIVE DEFECT.**
Every guard the unattended path depends on was mutated and scored against its own tests: the six
detectors, the heartbeat gate, the tailor no-fabrication guards, the eligibility keystone and
verdict rollup, projection fidelity, scan/apply and identity/dedup, the review gate, and the rank
gates. Four gaps were real and three shipped as **test-only** PRs — **#263** (a closed posting was
being re-closable, the only one that COMPOUNDS nightly), **#264** (plan deviation 8: a reopen must
not swallow the revision), **#265** (`weight_sum <= 0.0`, the first gap reachable from a LEGAL
config) and **#267** (the funnel's JSON `reconciles` key could be hardcoded `True` — the artifact
Gate P0 is defined against, and the web viewer's run-list badge). Eleven survivors were proven
**unobservable** rather than untested, each by constructing the exact input the clause guards —
and each should be KEPT, because in every case the redundancy depends on a neighbouring
implementation detail that a refactor could change. **Every gap was correctness that was not PINNED, never
correctness that was wrong** — full table in `METRICS.md`.

**THE BIGGEST REMAINING RISK IS NOT IN THIS REPO — A NIGHTLY `brew upgrade` SITS 4 HOURS UPSTREAM
OF THE RÉSUMÉ RENDERER.** `com.mitsheth.nightly-maintenance` fires **00:00 daily** and runs
`brew update` -> `brew upgrade` -> `brew cleanup`. `reports/tailor.py` shells out to **`tectonic`**
and **`pdfinfo`**, both at `/opt/homebrew/bin/` (0.17.0 / poppler **26.08.0**). poppler versions as
`YY.MM.x`, so **26.09.0 is due in the first days of September — inside the window** — and it
already auto-upgraded 26.07.0 -> 26.08.0 on 2026-08-04. **The preflight checks EXISTENCE, not
executability**: `shutil.which` still succeeds for a binary broken by a dyld mismatch, so it does
NOT report `BINARY_MISSING` — it degrades to per-lead `COMPILE_FAILED` -> "every lead failed to
project or tailor" -> FATAL -> heartbeat withheld -> the monitor pages. **Detected but
MIS-DIAGNOSED, and every subsequent night fails identically.** Leads are NOT burned
(`COMPILE_FAILED` is excluded from `DETERMINISTIC_GATE_REFUSALS`), so a repair recovers everything.
**Mitigation is one reversible command and it is MIT'S CALL because it changes another job's
behaviour: `brew pin tectonic poppler`.** The principled in-repo fix — have the preflight PROBE the
binaries rather than only locate them — is deliberately NOT shipped before a freeze; it is a change
to the nightly render path and deserves its own review.

**TWO MORE MACHINE-LEVEL FACTS, both lower severity.** macOS **auto-installs on a BETA seed train**
(three OS installs in 18 days); each reboots, but auto-login is on and FileVault OFF so the
LaunchAgent returns, and a reboot inside the run window costs that night only. And
`com.mitsheth.cleanup-caches` fires at **exactly 04:00 on Sundays** — 09-06 and 09-13 — the same
minute boardwatch starts; pure I/O contention, it touches no boardwatch path.

**THE PLIST'S HEARTBEAT-GRACE REASONING COMPARES THE WRONG QUANTITY.** It argues *"run 130 took 137
min, so a slow day cannot false-alarm"*. The ping fires at `04:00 + duration`, so the 26 h window
constrains **`dur(N+1) - dur(N)`**, not absolute duration. Only runs 131 (96.7 min) and 133 (112.9
min) are genuine scheduled ticks — delta 16.2 min — so the real margin is **not yet pinnable**;
every other full-scan run in the store is from the ad-hoc era. Re-derive from consecutive scheduled
ticks once 134+ exist. Errs safe either way: the failure mode is a FALSE "down" email, never a
missed real failure.

---

## Moved out of STATE on 2026-09-02b — the gate-1 redefinition, run 143's readout, the pre-harvest jobapps-tree analysis and the seed-leak first reading, kept verbatim

All of this is settled and held by number elsewhere: gate 1's redefinition is **D-421**, the one-time harvest decision is **D-423** and it has now BEEN RUN (run 144, METRICS), the seed leak is **D-422** with its report shipped as **D-426**, and the retirement answer is **D-424**. Kept verbatim because the reasoning behind each number is worth not re-deriving.

### Session 2026-09-02: the five branches merged, Indeed is ARMED and has RUN, and gate 1 was replaced by a different instrument

**GATE 1 IS NO LONGER A COVERAGE PERCENTAGE.** The owner withdrew both the 80% bar (D-399) and the
"cover most of what job-apps does daily" wording that briefly replaced it. **It is now PER-SOURCE
RECALL, a rate** (D-421). Do not re-derive either retired bar.

**Why**, in the owner's words: *"what I want you to compare is the same methodology or the sources
that job apps have"* — job-apps' output grows daily so no two readings share a denominator, and he
had already processed past discovery into the apply queue. **The old gate was worse than unstable:**
it counted `eligibility` outcomes `eligible` (1,229) + `protected_applied` (45) and **excluded
`moved` (3,963 — the apply-queue set, three times larger)** and `review` (2,484). `eligible` and
`moved` only exist once he works a cohort, so 08-31, 09-01 and 09-02 carry zero of both. **Three of
the seven days contributed nothing.** The "216" tracked his activity, not boardwatch's coverage.

**First reading of the new gate — run 143, 14d window, 21,863 job-apps postings:**

| | value |
|---|---|
| **recall, drawn-from sources** | **4,913 of 20,653 = 23.8%** |
| employer's own board (lever/ashby/greenhouse/workday) | **94–100%** |
| aggregator + search (linkedin 32.5%, hiringcafe 17.0%, indeed 12.6%) | **12–33%** |
| **lane-only — dies the day job-apps stops** | **7,091 (32.4%)** |
| never held at all | 9,715 (44.4%) |
| **independent if job-apps stopped today** | **5,057 = 23.1%** |
| source coverage | **94.4%**, or 99.6% excluding the deliberate jobright refusal |

**The split is binary and falls on MECHANISM, not effort.** Reading the employer's own board gives
~100% recall; reading an aggregator gives 12–33%. **Source coverage is essentially solved** — only 15
of job-apps' 33 registered sources produce anything, and boardwatch draws from sources covering
94.4% of its volume. Gate 3 HELD at 49 (baseline 44). **No numeric threshold is set, deliberately:**
one number averages a solved mechanism against an unsolved one, which is how 80% hid that the
direct-ATS half was already done. Setting it per source is the owner's call.

### Run 143 — the first armed run

379 boards / 290 complete / 54 unchanged / 33 partial / 2 failed, 41m59s. **31,350 postings seen**
(142: 21,944), **2,894 new** (1,292), corpus 122,917. Verdicts **139 eligible** / 2,126 uncertain /
1,566 ineligible. 95 leads delivered. Board stage 379 boards in 20m11s = **3.2s per board**, which
is what auto-watch growth costs on every future run.

| lane | attempted | resolved | new companies | refused by cap |
|---|---:|---:|---:|---:|
| linkedin | 1,564 | 273 | 50 (cap) | 463 |
| **indeed** | **513** | **83** | **25 (CAP)** | **359** |
| jobapps | 432 | 237 | 46 | 0 |
| hiringcafe | 127 | 45 | 8 | 0 |
| jsonld | 0 | 0 | 0 | 0 |

**#331's body precondition fired in production:** 12 bodies withheld as "not the employer's own
text" — all 12 from `jobright.ai`, all ingested by the `jobapps` lane, `h1b sponsor likely` in 9 of
them, against 122,917 checks (0.01%, so precise rather than over-firing). **The contamination route
was job-apps, not a jobright lane** — refusing that lane never kept jobright's judgments out;
ingesting job-apps put them in. That is the sharpest argument for retirement the program has.

### `lane_seeds` fills to 773, and 85.9% of it is unreachable (D-422)

Zero → **773 rows in one run** (indeed 683, jsonld 90), **0 resolved, 0 attempts**. The
`jsonld → 0 attempted` is lane ORDERING, not a defect: the resolver runs before the producer and the
table was empty. **Run 144 must confirm the drain** — the handoff is unproven end to end until one
does. **The real defect: only 109 of 773 (14.1%) are claimable by any resolver's host catalog; 664
(85.9%) across 197 hosts are selected by nothing**, and `attempts` cannot bound them because an
unselected seed is never attempted. `grnh.se` (109) is the cheapest win — Greenhouse's own shortener,
and boardwatch already handles greenhouse. `eeho.fa.us2.oraclecloud.com` (Oracle HCM) and
`lockheedmartin.eightfold.ai` (Eightfold) are D-417's unbuilt levers whose seeds are already
arriving.

### The job-apps discovery tree is only a QUARTER ingested — measured 2026-09-02

The `jobapps` lane walks **exactly two levels** (`resumes/<date>/<posting>/`) and is deliberately
non-recursive so it cannot reach `_skipped/<reason>/`, whose directory names are job-apps' own
verdicts. **That intent is right** — reading them would inherit job-apps' judgments, the coupling
D-421 measured. But the depth limit excludes two further buckets as collateral. Confirmed through a
second path, not from reading the code: the tree holds exactly **432** `discovery_record.json` files
at the lane's depth and run 143 logged `lane jobapps → 432 attempted`.

| bucket | records | status |
|---|---:|---|
| lane's depth (top level per date) | **432** | read; **239** pass `is_direct_apply` |
| **`_eligibility_review`** | **1,374** (1,357 parse) | **MISSED — unintended.** 669 pass the filter |
| `_skipped` | 16,918 over 174 reasons | skipped by design |
| `_too_senior` | **0 records** (49,662 folders, each with `job_description.txt` + an apply URL) | unreachable by this lane |

> **SUPERSEDED 2026-09-03 — the harvest RAN and every count in the table above has moved. The table
> is kept verbatim; these are the current numbers.** lane depth **529** records (472 held, 57
> absent); **`_eligibility_review` 1,465 (1,442 held, 23 absent) — NO LONGER "MISSED": the owner's
> 2026-09-02 one-time harvest demonstrably executed**, verified on the EXACT-URL key alone with no
> fuzzy matching at **1,364 of 1,461 (93.4%)** present under the `jobapps` stamp, **1,341 of them
> first seen 2026-09-02**; `_review_later` 2 (1 held); `_skipped` **17,193** over its reasons (6,278
> held, 10,915 absent, excluded BY DESIGN); `_too_senior` **50,269 folders, still 0 records** and
> therefore still unreachable by ANY depth change, because the lane keys on `discovery_record.json`.
> **What is left in the buckets the lane is supposed to read is 81 records.** So the BACKLOG half of
> this section is closed; what is not closed is the DAILY FLOW — on 2026-09-03 job-apps found 1,619
> postings of which boardwatch held 551 (34.0%) independently, 530 (32.7%) only by reading job-apps'
> tree, and **538 (33.2%) not at all.** The two measures are not additive: `_skipped`'s 10,915
> absent are largely the same postings seen from the disk side.

`_eligibility_review` records are `schema_version: 2` with keys identical to what the lane reads —
fully readable, out of reach only by depth. **Root cause is a shape mismatch:** the lane's docstring
describes the tree as `<queue>/<ATS>/<posting>/`, so it was written expecting an ATS name at the
middle level; `resumes/` puts a DATE there and job-apps files its triage buckets at that same level,
one deeper than the walk goes.

**`_skipped`'s 174 reasons are NOT uniform in risk, which bounds any future decision to mine it:**
~45% is job-apps' own ROLE TAXONOMY (`non_swe_*`, 7,640 — and #330 corrected boardwatch's own role
gate this morning for the same class of error), ~28% is PROFILE-DEPENDENT eligibility
(`min_N_years_experience` ~3,100, `clearance_required` 589, `no_sponsorship`/visa ~330,
`international_location` 327, `senior_title`/`senior_level` 420), and only ~17% is objective posting
fact (`stub_jd` 1,922, `discovery_blocked_header` 606, `junk_folder_*` 373, `posting_closed`).
**Only that last class is safe to take on job-apps' word.**

**OWNER'S CALL (2026-09-02): harvest ONCE, build NO mechanism.** job-apps is being retired, so after
a certain date there is no more of this content and a permanent ingestion path would be dead code.
Process the top level plus `_eligibility_review` once and keep the eligible ones. Do **not** re-decide
`_too_senior` or `_skipped` through boardwatch's gates — job-apps' verdict is taken at its word
there. **Ingesting once is itself the record that stops re-processing**, because `posting_identities`
and the disposition ledger already make a second encounter cheap; no suppression list is needed, and
that is why none was built.

### Applied this session

- **Tier-A admission APPLIED** (owner-confirmed): 3 boards, watched **387 → 390**. Backed up first —
  `companies-pretierA-*.csv` (the exact reversal artifact) and a 5.5 GB `VACUUM INTO` snapshot.
- **Indeed cap raised 25 → 50** on the owner's call and on the 25-admitted/359-refused reading.
  **Carrying D-417's caveat: a binding cap is not proof that relieving it helps** — LinkedIn's went
  10 → 50 and bought ONE posting. Verify yield on runs 144/145 before raising again.
- **jobright company-discovery probe: REFUSED on measurement, against my own proposal.** Of 501
  employers, 373 unseen, only **44 (11.8%)** have a resolvable board (62 of 523 postings), 329
  (88.2%) none at all — and all 44 were discovered via hiringcafe/legacy/zapply/simplify, **not one
  via jobright**, so the reachable part needs no jobright lane.

### CAN job-apps BE RETIRED? NOT YET — and the residual is LinkedIn alone (D-424)

Asked directly at this session's close. **The original 80% goal was not achieved** (gate 1 never
passed 22.7%) but it was **withdrawn** rather than failed, because it counted a population the
owner's manual processing created. **And the backlog is the wrong axis:** D-423's one-time harvest of
18,726 on-disk records is pure gain, but retirement asks whether boardwatch finds TOMORROW's
postings. Processing the backlog cannot make retirement safe; skipping it cannot make it unsafe.

**Cost of switching off today, two independent measures:** discovery **7,091 of 21,863 (32.4%)
lane-only**; delivery **28 of 95 leads (29.5%)** in run 143 via the `jobapps` lane (140: 2.1%,
141: 17.9%, 142: 2.1%). **That delivery share is inflated by the backlog** — the lane ingests records
still unprocessed in the tree and they leave its view once the owner works them, so it tracks how
recently he processed rather than dependency. **Steady state is not measurable until the backlog is
cleared**, which is another reason to harvest first.

| | standing |
|---|---|
| source coverage | **DONE — 94.4%** (99.6% ex-jobright) |
| employer's own board | **94–100% recall — solved** |
| **indeed** | 12.6% but **0 absent**; armed, and **fixes itself in ~7 daily runs** (D-417), no new work |
| **hiringcafe** | **17.0% with a WORKING lane, 1,958 absent — UNEXPLAINED.** One investigation owed |
| **linkedin** | **32.5%, 6,789 absent**; 57 of 77 sampled misses are employers with no ATS board |

> **SUPERSEDED 2026-09-03 — the three rows above are run 143's and are kept verbatim; these are run
> 147's, window 2026-08-21..09-03.** indeed **15.5%, 0 absent, 6,568 `lane-only`**; hiringcafe
> **20.7%, 1,331 absent**; linkedin **34.8%, 5,650 absent**. Overall independent recall 26.5%,
> `lane-only` **8,244 (38.3%, UP from 32.4%)**, absent 7,719 (35.9%, down from 44.4%).
> **Two corrections to the row text itself, not just its numbers.** First, **"indeed … fixes itself
> in ~7 daily runs (D-417), no new work" is SCOPED TO A RETIRED 35-POSTING POPULATION and is false
> of the current one** — see `RETIREMENT-PLAN.md` §6's re-scoping note; Indeed is now 80% of the
> whole switch-off exposure, its `indeed_search_pages` sits at its floor of 1, and its `24h` date
> filter means the existing bucket can never be drained by it. Second, **the "57 of 77" linkedin
> figure is a SAMPLE and the population is 5,650** — do not carry the sample's proportions onto it.

**The test is decidable now: retire when `lane-only` falls to a level the owner accepts losing.** It
is measurable every run by D-421's script and is the exposure by construction. Sequence: harvest →
let Indeed reach steady state → diagnose hiring.cafe → **re-measure ~2026-09-09**. The residual is
then LinkedIn alone, which is a judgment about a population, not an engineering gap.

## Closed blockers, moved WHOLE out of STATE

> Lifted from `STATE.md`'s live-blocker table on 2026-09-03 when that file passed its size
> target again. **Nothing was summarised** — each row is byte-identical to the one removed,
> and each names the PR and decision that closed it. They are kept because a closed blocker
> records what the fix was FOR, which a decision entry alone does not always make obvious.

| Item | Detail | Owner |
|---|---|---|
| ~~The `experience_years` group reads a REFINEMENT as a CONTRADICTION~~ **CLOSED by #291 / D-389** | `refinement_groups` ships as a second group kind in versioned catalog DATA: `exclusive_groups` keeps PRESENCE semantics, `refinement_groups` dissolves only on a real `MET`/`UNMET` straddle. Only `experience_years` moved — **a global rule regresses 8 of 1,034 corpus cases** (D-388), because `clearable_required` is a DISJUNCTION not a weaker rung. **913 of a PINNED 1,868 flip `uncertain` -> `ineligible` (48.9%)**, corpus 0/1034 (predicted before review). **`engine_version` MOVES so a LEDGER DRAIN IS OWED.** Known property, direction deliberate: the refinement pass runs BEFORE stage 1b, so a same-implies split beside another present member dissolves the group where stage-1b-first would let a decisive `unmet` stand — the shipped order is the ABSTAIN direction | **CLOSED** |
| ~~Delivery-drought cannot see APPLY-LANE starvation~~ **CLOSED by #285 / D-384** | `delivery_drought.py` counts `artifacts.kind == TAILORED_KIND`, written **regardless of which lane `review_gate.lane()` routes to**, so a global misclassification shipped zero apply-ready leads with every existing alarm green. `check_apply_lane_drought` now fires when the last 3 clean runs each delivered PLACEABLE leads and none reached the apply lane. **The old sizing was wrong, not merely pessimistic**: it priced a guard inside `_sync_queue`, but the three job-id readers already take only a connection and `QueueRow` already carries `delivered_run_id`, so nothing in `review_gate`, `_sync_queue` or the web server's result type had to change. Known property, direction abstain-not-alarm: `delivered_unapplied` attributes a re-delivered job to the NEWER run, so an older run can read zero placeable and the window abstains | **CLOSED** |
| ~~Four detector fallbacks are print-only, not durable~~ **CLOSED by #260** | The `intake-death` / `delivery-drought` / `liveness-blindness` / `corpus-regression` "check not run" handlers now call `append_run_error` like the three artifact-write handlers beside them, so a DETECTOR that crashes leaves a row in `runs.errors_json` and not only a digest line. Four one-line additions, inert on the normal path; each pinned by its OWN parametrised test, because a single test crashing all four passes while three of the four calls are missing. **Known shared property:** `append_run_error` is not internally defensive and these sit inside `except` handlers — matched to the three existing handlers deliberately rather than diverging; it needs two simultaneous failures and fails loudly via the withheld heartbeat | **CLOSED** |

## Standing facts mis-filed as live blockers, moved WHOLE out of STATE

> Lifted from `STATE.md`'s live-blocker table on 2026-09-03. Neither is a blocker: both are
> permanent properties of the system that a fresh session needs before touching the queue or
> the live store, plus `resume.yaml`'s import-source rule. **All three are byte-identical to the
> rows removed.** The third was nearly DELETED on a false check: a grep for `resume.yaml`
> matched unrelated lines here and was read as "already carried". It is not carried anywhere
> else — verify the CLAIM, never a substring of it.

| Item | Detail | Owner |
|---|---|---|
| **`boardwatch top` advances the queue by default** | records `seen` unless `--no-record`; relevant to Gate P6's clean window | P6 |
| **A live store is readable ONLY via Python `sqlite3` `?mode=ro`** | the `sqlite3` CLI with `?mode=ro` fails `CANTOPEN(14)` on a cleanly-checkpointed store (no `-shm`; not the sandbox), and `?immutable=1` skips the WAL so it is STALE against a live writer. Mid-run progress: `SELECT COUNT(*) FROM eligibility_evaluations WHERE run_id=N` (D-268) | tooling |
| **`resume.yaml` is an IMPORT SOURCE, never hand-fixed** | D-155. Mit pins `resume_max_pages=1`; never advise 2 | Mit |


### hiring.cafe: #304 WORKED, and the method lesson that cost two wrong entries

Moved WHOLE out of `STATE.md` 2026-09-03 (settled: the finding is closed, the dead ends are
eliminated, and nothing here changes between sessions). Verbatim:

| **hiring.cafe: ONE unexplained POST-FIX failure (run 142) — and D-420 recorded two wrong framings before this one.** #304 (`11a1ae95`) merged **2026-09-01T07:56:34Z**. Against that boundary: **130, 131, 133, 134, 135, 136, 137 all FAILED and all seven PREDATE the fix** (132 ok, a single unexplained point); post-fix **138, 139, 140, 141, 143, 144 ok** and **142 is the only failure**. **So #304 WORKED** — this is neither a regression nor chronic flakiness. Not time-of-day: 138 also started 09:00Z and passed. **METHOD LESSON, which cost two wrong entries in one session: date a behaviour claim against the COMMIT that changed the behaviour, not against a run streak — a streak has no denominator until you know when the code changed.** Do NOT retry the eliminated dead ends: the header lever failed twice (D-369; run 133 reproduced the refusal byte for byte) and the UA and volume premises were both false. | **watch** |


## Moved out of STATE on 2026-09-03 — run 145's readout and three long-settled deferrals, kept verbatim

### Run 145 — read out; both of the night's queue fixes are CONFIRMED IN PRODUCTION

96.4 min, exit **ok**, 94 tailored leads. Queue **598 apply / 732 review / 274 ineligible / 107
closed / 0 reported**. Full numbers: `METRICS.md` (Run 145). **D-432 CONFIRMED** — the buried eBay
requisition (job 35249) left `_closed` for `_review` and its genuinely-dead same-titled sibling
(35247) correctly stayed. **D-434 CONFIRMED** — `_reported/` created and empty, exactly as "0
reported, 0 skipped on the live store" predicted, so a live reconcile could not have exercised that
drain either way and the unit tests were the only thing that could catch it.

**A count prediction and a mechanism prediction are different claims, and only the second was
D-432's.** `_closed` went 103 → **107**, not the predicted 102: a 96-minute rescan of 1,124 boards
found new closures, and the prediction implicitly held the world still for an hour and a half.

- **Track 2's cap cost has no measured UPPER bound.** A per-company cell costs *at least* one
  `lane_new_companies_per_run` slot, and would cost exactly one only if a quoted-phrase search
  returned cards solely from the named employer — which was never probed. **Read the funnel's
  per-lane `admitted`/`refused` split on the first armed run**; it measures this directly.

- **T1's concurrent case-variant duplicate race** — deferred, pre-existing, worst case a dead-weight
  row. Fix is a `(provider, lower(slug))` unique index plus a reconcile.

- **T3's exotic hostnames** — unicode-dot/fullwidth IDN and legacy IPv4 can still store an
  undrainable row. Dead weight only.

- **THE ABSTAIN REPORT CANNOT SEE AN EXTRACTION GAP, BY CONSTRUCTION (D-436).** `reports/abstain.py`
  aggregates per `rule_id` across the WHOLE corpus, so a pattern that matches most phrasings and
  misses a near-miss variant is neither `never_fired` nor `fully_abstaining` — its rate looks
  **healthy**. The keystone makes a rule that cannot resolve a profile FIELD visible as a 100%
  abstain rate; it says nothing about an extractor that cannot find the requirement in the TEXT,
  because the rule never got the chance to abstain. A blind two-judge audit put **24% of `eligible`
  wrong (13 of 54)** and **every single miss was `no requirement row written`**, not a rule
  deciding badly. **Unfixed.** The honest fix is a THIRD OUTCOME per family — "the extractor ran and
  matched nothing" and "the JD is silent" are collapsed into one today and the second one clears —
  not more patterns, which is whack-a-mole.

- **THE D-436 PATTERN FIXES CATCH *ZERO* OF THE 13 MEASURED FALSE POSITIVES — the 24% is UNCHANGED.**
  Measured, not assumed: the two fixed sentences came from the pre-correction 218-job sample and do
  not survive into the real 144. The fixes are safe (0 regressions) and close real leaks, but the
  delivered population's defect rate did not move. **The 13 have ~7 distinct root causes**, so more
  patterns is whack-a-mole. **The unarmed answer is the two-stage shape already built:**
  `boardwatch eligibility gate request`/`gate apply` (the `final_gate:` LLM lane — ineligible-capable,
  keystone-guarded, identity-keyed, read by the ranker) over the **~8-10 leads/day delivered**, which
  is the only population where zero-ineligible is reachable. **0 rows on the live store today.**
  Owner-gated.

| **`companies.last_health` / `last_ok_at` are a LYING instrument** | 178 of 379 watched boards read NULL, which looks like "never succeeded" — **all 178 were scanned by run 133** (128 complete, 7 partial, 43 unchanged). The scan path does not maintain these columns. **Judge fleet health from `board_scans` per run instead**: run 133 was 379 attempted / 271 complete / 87 unchanged / 21 partial / **0 failed** | tooling gotcha |

| **`unchanged` staleness is now BOUNDED (D-298, #153)** | The `unchanged` verdict comes from the upstream HTTP validator (ETag/Last-Modified → 304), not a boardwatch payload hash. `validator_max_age_hours` (default 24) drops a validator older than the TTL, forcing an unconditional refetch, so a permanently-stale upstream can no longer freeze a board forever — the silent-staleness window is capped at the TTL, and a regression test now exercises the aged-validator refetch. Still open: within the TTL an `unchanged` is trusted with no independent check. The separate "59 of 135 boards listed nothing" figure was a **`postings_listed`-on-304 artifact — CORRECTED to 17 real dead-weight (D-300)**, now cleaned; the 118 `ok` boards hold 39,253 open postings | open (mitigated) |

0. ~~gate 1 >= 80%~~ / ~~"cover most of what job-apps does daily"~~ **BOTH RETIRED. Gate 1 is now
   PER-SOURCE RECALL (D-421), and the only thing still owed from the owner is the THRESHOLD, per
   source.** The instrument is built and has a first reading (see Current standing). Set a bar per
   source rather than one number — the direct-ATS mechanism is already at 94–100% while the
   aggregator mechanism is at 12–33%, and any single average hides that. **Do not re-litigate 80%,
   and do not re-derive "most".**

1. ~~Does job-apps keep running, or is it retired?~~ **ANSWERED — it keeps running until gate 1 is
   met.** Both schedulers armed: boardwatch 04:00, job-apps 08:30. **The retirement work is now a
   written plan, not a question: `docs/program/RETIREMENT-PLAN.md`.** Do not re-raise WHETHER, and do
   not re-derive the gap analysis.
   ~~2. Indeed's dependency posture.~~ **DECIDED by Mit 2026-09-01 (D-410): approved.** Closed; do
   not re-open or re-probe.

*(Resolved and no longer open: the delivery slate cap — D-345, `(company_id, normalized_title,
content_hash)` at N=1; do not reopen as identity suppression, which is D-295 and is refused.
Whether `runner.py` should keep swallowing a funnel-write failure — D-288. Clearance IS a blocker
(D-257). Seniority band = `entry` (D-258), and it is **armed on the live profile**.)*

### The 2-year-bar question, moved out of STATE on 2026-09-03 (now A4)

**1. ANSWER ONE QUESTION, AND IT DOES NOT WORK THE WAY AN EARLIER READING CLAIMED: does a stated
2-YEAR bar rule you out?** `near_miss_years_ceiling = 3` makes the engine ABSTAIN at or under 3
years, so those leads are held for review. **LOWERING IT DOES NOT RELEASE THEM — IT REJECTS THEM
(D-440).** Ceiling **2** rejects 290 postings; **0-1** rejects **505**. That reverses D-333 and takes
the expensive error direction: a wrong `unmet` writes `ineligible` with a quoted span and silently
removes a gettable job, and **the reject pile is never inspected**. Recommendation: do NOT lower it.
It also cannot deliver the range attributed to it — of 1,141 abstained rows, 583 are the band and
**465 are `scoped to a skill`**, which abstains whatever the ceiling is.

**AND THERE IS NO DATA FIX HIDING BEHIND IT — that was checked.** The résumé's dated Experience
section parses to **20 months / 1.67 years** across three roles: a 7-month SWE co-op plus **13
months of internships**, which these postings routinely exclude by name. The stored `1` understates
the raw total by ~8 months and **all of it is internship time**, so against a 2-year bar the résumé
and the stored fact agree. **The value is defensible and correcting it would not clear the bar.**

**Which leaves the question genuinely yours and not a data error**: it is whether you would apply to
a 2-year-bar posting anyway, knowing employers enforce those bars unevenly. Nobody but you can
answer that, and D-440 has priced every option so it is a row-pick rather than an opinion.

## Moved out of STATE on 2026-09-03b — two CLOSED items kept verbatim

Both said "closed" or "do not re-arm" in their own first line while occupying ten lines of the next-action list. Kept whole because each is a refutation, and a refutation summarised is a refutation that gets re-proposed.

### Track 2 — refuted on live measurement and disarmed

**0. TRACK 2 IS REFUTED ON LIVE MEASUREMENT AND IS DISARMED. DO NOT RE-ARM IT.** Armed at
`lane_company_combos_per_run = 12` on 2026-09-03, dry-run against the live host **before** the first
tick, disarmed 01:34. **4 of 120 cards on target (3%)**; 12 cells present **78 distinct companies,
61 new, against a cap of 50**, ahead of the hub nets, so arming it takes every slot. The rescue is
closed and was probed: the guest fragment serves **no numeric company id**, so `f_C=` is
unreachable and getting there is a **D-290 widening, the owner's**. Everything else: **D-437**.
**The 342 already-watched misses are STILL OPEN and the LinkedIn residual has no proposed mechanism
again.** Do not propose per-company cells without naming a mechanism that actually filters by
employer. The code stays merged and inert at `0`.

### The 50-board hiring.cafe sample — read out and closed

**3. THE 50-BOARD SAMPLE IS READ AND THE REMAINING 282 ARE REFUSED (D-441). CLOSED — do not
re-open it from hiring.cafe's in-window counts, which is the number that was wrong.** Run 145
answered it in one run: the sample's **59 boards contributed 8,303 postings** against D-428's
predicted 79, and the run took **96.4 min writing 15,356 versions** against run 144's 21.9 min and
2,020 — **105x the postings, ~21-27x the minutes**, and 8,303 is a FLOOR because eleven of the top
twelve contributors hit `detail_fetch_budget = 400`. **It bought 10 delivered leads.** The sample is
NOT reverted; whether to keep paying ~60 min/run for 10 leads is the OWNER's, and is a different
question from adding 282 more, which is closed.

## Moved out of STATE on 2026-09-03c — the escaped-bars block, MERGED as #354, kept verbatim

Owner-gated for a day, merged 2026-09-03. Kept whole because it is the measurement that
justified re-versioning 478 postings, and a summary would not.

- **THE ESCAPED-BARS HALF IS BUILT AND AWAITING YOUR MERGE — #354, D-443.** The escapes are **one
  lane's**: jobapps **473 of 1,620 bodies (29.2%)**, workday 6, greenhouse 2, **every other provider
  0.0%**, so the fix is one unescape in `lanes/jobapps._body` and not a body-normalisation layer (a
  shared normaliser would have rewritten 137,057 bodies to fix zero). Measured through the real
  engine: **132 bodies go from ZERO requirement rows to some, 83 verdicts move, 11 leads leave
  `eligible`**, and nine of the new rows are sponsorship refusals that were unreadable. All 83 moves
  were read against the employer's own quoted span, including the single promotion. **Still
  owner-gated to MERGE** because it re-versions postings and changes what you are told you can apply
  to — not because anything about it is unmeasured.

## Moved out of STATE on 2026-09-03c — the queue audit, settled, kept verbatim

The measurement that redirected three sessions' worth of work from routing to extraction.
Kept whole because its numbers are what every later sizing is measured against.

### The 2026-09-03 queue audit — the waste is catalog COVERAGE, not routing

Blind two-judge audits of what the owner actually opens, reproduced independently by two sessions.
Mechanism: **D-436** (extraction) and **D-442** (the routing read). Full method in METRICS.

**THE HEADLINE THIS SESSION FIRST PUBLISHED — "the catalog is 8% of the problem, routing is the
rest" — WAS WRONG, and it was wrong by reading a verdict DISTRIBUTION as a defect ATTRIBUTION.**
8% of the apply lane carries an `eligible` verdict; that says where verdicts land, not where the
defect lives. Three sessions handed `review_gate.lane()` forward as *the lever* and **none had read
it.**

| | |
|---|---|
| apply lane | **597** — 526 `uncertain`, 49 `eligible`, 22 unevaluated |
| **of the 526, with ZERO requirement rows** | **481-487** (two independent counts) |
| their JD bodies | median **4,636 chars**, only 4 under 200, **~390 over 2,000** |
| `_review` | **1,007** — `experience_requirement` 497, `ineligible_verdict` 288, `role_unconfirmed` 175 |

**The routing is deciding CORRECTLY.** `experience_unconfirmed` fires **497** times, so the flag
works; all 597 apply-lane leads carry both flags False **because nothing was extracted, not because
nothing is wrong**. `_no_evaluable_requirement` makes them `uncertain` and `review_gate` never reads
WHY. **So the ~36% unapplyable rate IS the extraction gap arriving from the other end** — the same
finding as D-436's "every miss was a missing row", and the same reason the abstain report cannot see
it: **a family that extracts nothing is silent, and silence is indistinguishable from "the JD says
nothing".**

**IT SPLITS, AND ONLY A QUARTER IS COVERAGE (D-442).** Probing the zero-row bodies: **128 (26.3%)
carry a years bar in some form** (14 escaped punctuation, 24 spelled-out, 10 parenthesised), 55
citizenship/LPR, 32 sponsorship, 6 clearance, 4 non-English, **0 degree-required**. The other **~74%
trip none of those probes** — for those the JD may genuinely state no catalogued requirement, making
`uncertain` correct and the only question what an apply lane should DO with it. **The negative half
is bounded by those probes and nothing wider**: widening them can only move leads from the second
population into the first, never the reverse.

**THE GATE IS MEASURED, NOT ESTIMATED.** 77 apply-lane leads, two independent judges, real schema,
nothing applied: **15 demoted (19.5%), and 15 of 15 rejections survive `accept_oracle_verdict`'s
keystone span guard — ZERO span failures.** Every rejection quotes the employer's own JD, and two are
cases no amount of pattern work reaches (a French-language JD; markdown-escaped punctuation). Scaled
to 597: ~**116 demoted, each with a checkable quote**. Verdicts at `{config_dir}/verdicts_a.json` /
`verdicts_b.json` — **spot-check, then `gate apply`**. The earlier "~50-100 wrongly removed" treated
inter-rater disagreement as error-against-truth and ignored the guard; **retired**.

**Treatment vs cure.** The `final_gate:` LLM lane is the TREATMENT — it reads the JD directly and
catches what the patterns miss. **Catalog coverage is the CURE**, and the instrument is
**partial-match instrumentation of the patterns themselves** (a family that ALMOST matched), which a
cue vocabulary cannot substitute for: correct silence and a missed extraction look identical to a
cue and different to a near-miss. **D-442 holds the routing question** — ~360 of the 481 have no
detectable requirement at all, so it is "what should an apply lane do with a JD that states
nothing?", a decision about what the lane MEANS rather than a bug fix. Priced: apply **597 → 116**.

**The queue's 219 redundant leads are MOSTLY NOT A DEFECT (D-439).** 127 duplicate
`(company, normalised-title)` groups, but only **45 groups / 76 leads share one `content_hash`**;
the other **82 groups / 143 leads are genuinely distinct requisitions** (Evlo AI ×9 is nine real
reqs). An earlier reading called it identity resolution — **wrong**. The mechanism is D-345's cap
DEFERRING rather than dropping while scoped to one run, so a one-JD group delivers one member per
run forever. CGS Federal ×10 on a single hash is the shape that IS a defect.

**Sized and NOT built:** un-escaping markdown bodies 2.2% (owner-gated, re-versions postings);
`role_gate` missing the inverted `Engineer, Software` form (5 leads — the class D-305 fixed in
`seniority_gate` and never carried across); non-SWE residual in review only (apply-lane NOT_SWE was
0 of 40); `classify_location` fails open on Nottingham.

**`final_gate:` is built, keystone-guarded, identity-keyed, read by the ranker, and 0 rows on the
live store.** Request path VERIFIED live: **521 judgeable items of 537**, independence preserved,
read-only. **Ordering is forced** — `record_gate_verdict` keys on `build_identity(..., catalog, ...)`,
so any catalog change invalidates gate rows written before it. Land catalog PRs first, then arm ONCE.

## Moved out of STATE on 2026-09-03d — the nine-decision apparatus, every row executed or closed, kept verbatim

The owner-gated table that drove three sessions. **Every row is now executed or closed** — A1/A5/A6/A9
were already done, A3 and A8 shipped on 2026-09-03d (#367, #364), A7 was ruled and executed the same day
(revert, D-456), A2 is answered and its artifacts are not applyable, A4 is refused on measurement. Kept
whole because the pricing, the ordering constraints and the provenance caveat are what a future session
would otherwise re-derive; the rulings themselves are D-443, D-439/D-444, D-446, D-447, D-449, D-455,
D-456 and D-458.

**A. THE NINE DECISIONS — FOUR DONE, FOUR RULED, ONE OPEN. 2026-09-03; read the provenance line.**

> **FOUR OF THE NINE ARE DONE AND VERIFIED FROM THE REPO AND THE STORE, not from a merge
> message.** `main` carries **#354 (A1)**, **#357 (A9)** and **#344 (A5)**; the live store holds
> **87 `queue.skipped.*` rows and 0 ledger `skipped` dispositions**, which is **A6** executed
> through the reversible mechanism D-446 recommended. Reversal list:
> `a6-skipped-duplicates-20260903-114210.json` in the config dir.
>
> **The slate cap is confirmed live through the shipped code, not a proxy**: reading
> `standing_slate_keys` against the store gives **1,514 keys held, 3 still carrying more than one
> lead, 3 redundant leads** — down from 53 groups / 89 leads before A6. The 87 skips are correctly
> EXCLUDED from the seed, which is the property that makes every deferral end.
>
> **The RULINGS below (A2, A3, A4, A7, A8) were RELAYED through a peer session**, not read from
> Mit directly by the session that wrote this line. Recorded so the work is not re-litigated, and
> marked so a wrong relay is correctable rather than canon. **Confirm before acting on one that
> deletes or rejects.**

| # | ruling | status |
|---|---|---|
| **A1** | merge | **DONE** — `main` `113b91af` |
| **A2** | **yes — and the SPOT-CHECK IS DONE AND PASSED (15/15 correct against the employer's own words). The APPLY HALF IS IMPOSSIBLE.** | `gate apply` REFUSES `verdicts_a/b.json`: they carry `label`/`reason`/`evidence`, and `OracleVerdict` also requires `decision` and `confidence`. **They are audit notes, not gate verdicts** — nothing can be applied without fabricating a confidence the judges never gave. Applying anything needs a real `gate request` → judge → `gate apply` cycle. VERIFIED by reading both files and the dataclass |
| **A3** | **delegated — re-priced 598 → 90, and NOT YET IMPLEMENTABLE** | the unescape runs in `lanes/jobapps._body` **at INGEST**, while `preflight` reads `posting_versions.body_text` straight from the store — so **all 478 already-escaped bodies stay escaped until the lane re-ingests them**, and `eligibility run` cannot realise D-443. Price the predicate after those bodies refresh, not before. VERIFIED by reading both call sites |
| **A4** | **REFUSED after measurement** | his answer was a FACT, not an instruction — exactly the distinction D-440 exists to record. Measured cost against the CURRENT store is **1,458 postings rejected**, not D-440's 505. `near_miss_years_ceiling` STAYS at 3 |
| **A5** | merge | **DONE** — #344, `main` `6770608c`; gate 0 (9,336 passed), CI 24/24 |
| **A6** | executed | **DONE** — 87 skipped, reversible |
| **A7** | **hold one run** | re-read after the next full run before deciding |
| **A8** | **HALF CLOSED, HALF NEVER ASKED — do not read this row as settled** | **Cross-sentence** ("does a disjunction waive a SEPARATE `8+ years of C++`?") is his ruling, is **7 of 588 postings**, and is **already the shipped behaviour** — nothing to do. **Same-sentence** (`Bachelor's degree or 5+ years of software engineering experience` — does it waive ITSELF on the scoped arm?) is **581 postings and was NEVER PUT TO HIM.** The A8 row conflated the two |
| **A9** | merge | **DONE** — #357, `main` `268f904d` |

**A8's same-sentence half is the live question, and the asymmetry is ONE WORD.**
`…or 5+ years of experience` resolves `uncertain`; `…or 5+ years of **software engineering** experience` resolves `ineligible` — because only the total arm carries
`degree_alternative_to_years`. Mit holds a Master's and clears the degree arm in both. **D-073 already ruled this shape undecidable for the total arm and cites a real job deleted by getting it
wrong.** The D-447-era wiring is the WRONG instrument: being document-scoped it would fix the 581 and break the 7 he just ruled on. The right one is a **sentence-scoped escape** (`_suppressed` already takes `bounds`; `abstain_by` never passes one) — shared machinery, and its own decision.
Written up as **D-449**, on `main`.

**A4's answer is a FACT, not a policy move, and that distinction is the whole of D-440.**
"I don't have 2 years of work ex" answers the profile question; it does NOT by itself say
to lower `near_miss_years_ceiling`, because lowering it makes the engine REJECT those
postings rather than release them. Re-read D-440 before changing the value.

**The priced table below holds only the decisions still OPEN or delegated.** A1, A5, A6 and A9 are done and their pricing is in D-443, D-439/D-444, D-446 and D-447 — repeating it here would be a second copy that can drift.

| # | decision | what it costs / buys | where the numbers are |
|---|---|---|---|
| **A2** | **Spot-check the 15 judged rejections, then decide whether to run a FULL gate cycle** | `verdicts_a.json` (8) + `verdicts_b.json` (7) hold **15 rejections** from the 77-lead measurement, each quoting the employer; **15 of 15 spans survive the keystone guard, 0 failures**. Applying them demotes **15 postings, NOT ~116** — the ~116 is what a full `gate request` → judge → `gate apply` over all 597 would project at the measured 19.5%, and nobody has run that cycle. **MUST run AFTER A1 and D-447 land** (see below) | the two files, in the config dir |
| **A3** | **D-442's routing predicate** — zero requirement rows ⇒ `_review` | apply **597 → 116**, review 1,007 → 1,488. An **81% cut** to the pile you work from. **Not a bug fix** — it is what you want the apply lane to MEAN | D-442 |
| **A4** | **Does a stated 2-YEAR bar rule you out?** | `near_miss_years_ceiling`; **lowering it REJECTS rather than releases** (ceiling 2 rejects 290, 0-1 rejects 505). Recommendation: do NOT lower | D-440 |
| **A7** | **Keep paying for the 50-board hiring.cafe sample, or revert it** | ~**60 min/run forever** for **10 delivered leads** on run 145. Reverting is a `companies` restore from `companies-prehcsample-20260902-183019.csv`. **Adding the other 282 is CLOSED and is not this question** | D-441 |
| **A8** | **Does a degree disjunction reach a SCOPED bar?** — wire `degree_alternative_to_years` to the six scoped/domain minimum patterns | **365 SWE+US postings move `ineligible` → `uncertain`**, out of a reject pile that is never inspected and into review. Cost: `abstain_by` is **DOCUMENT-scoped**, so a JD saying "Bachelor's or 4 years" for its general bar would also waive a separate "8+ years of C++". Today the same sentence **abstains on the total arm and rejects on a scoped one**. **A claim about what a disjunction MEANS, not a consistency repair** | D-447; `test_experience_range_recall.py`, the defect pin |

**A1 and A3 interact and A1 comes first**: the unescape moves 132 leads out of the zero-rows
population A3 prices, so deciding A3 before A1 lands prices a population that is about to shrink.

**A2's ordering note still applies to the FULL cycle, not to the files.** The files cannot be applied at all (see the row); this is about whatever you judge next. **It is ORDER-FORCED and fails SILENTLY if you get it wrong.** `record_gate_verdict` builds its identity from the catalog and stores the `rules_hash`, so **any catalog change invalidates gate rows written before it** — verdicts applied ahead of #354 and D-447 are written under an identity the ranker no longer reads. No error, no warning, just no effect. Land the catalog PRs first, then judge, then apply.

**A8 is independent of A1 and A3** — it moves postings that are already `ineligible`, which neither the unescape nor the routing predicate touches. **A1 and A5 must be read out on ONE run, not two.** **A9 is STACKED on A1**: its base branch is #354's, so #354 merges first or #357 cannot. **A9 also moves the catalog**, so it is one of the two changes A2 must wait behind. #344 shrinks the delivered population and #354 changes the verdicts on it, so whichever lands second is measured against a population the first moved. **A6 is independent of both** — it touches only leads already on disk.

## Moved out of STATE on 2026-09-03d — run 145's readout, the Track 2 and `gh_jid` refutations, and the four next-action items they closed, kept verbatim

Superseded by runs 148 and 149 (`METRICS.md`, `Session — 2026-09-03d`) but kept whole: the Track 2 and
`gh_jid` paragraphs are refutations, and a refutation deleted is a refutation somebody repeats. Blank
lines separate blocks that were not adjacent in `STATE.md`; no line was changed.

**0. TRACK 2 IS REFUTED AND DISARMED. DO NOT RE-ARM IT, and do not propose per-company cells without naming a mechanism that actually filters by employer** — a quoted company name does not. Code stays merged and inert at `0`. **The 342 already-watched misses are STILL OPEN and the LinkedIn residual has no proposed mechanism again.** Measurement and the closed rescue: **D-437**, and this section verbatim in `STANDING-FACTS.md`.

**2a. THE RE-KEY IS RESOLVED — RUN 146 DID IT, AND THE "HOURS" ESTIMATE IN THIS FILE WAS WRONG BY ~10x.** Both hashes moved (`rules_hash` from the catalog change, `profile_hash` because D-438's resolver adds `education_timing` to `declared_fields()`), and this file said a full re-evaluation would write ~138k rows *over hours* so it was deliberately not triggered. **Run 146 wrote them in 10 minutes**, 12:18-12:28 on 2026-09-03: **138,582 of 138,677 open postings now carry a verdict under the live identity — 99.93%.**

**The lane split was RE-READ after the re-key rather than assumed, through `review_gate.lane()` itself and not a proxy: 597 apply / 1,007 review / 107 closed — UNCHANGED. So A3's pricing below is current, not stale.** What still disagrees is the folder tree, and by very little: run 146 ran no reconcile, so disk holds run 145's filing (598 / 732 / 274 `_ineligible` / 107 / 7 `_applied`) while the store now wants 597 / 719 / 288 / 107. **That is ~14 folders out of 1,711 — the re-key barely moved the lanes**, and the next full run closes it.

**Watch out for run 146 in the runs table: `boards_attempted = 0`, every scan column NULL, `status = ok`.** It was **a peer session's `boardwatch eligibility run`**, issued to clear the re-key — not a fleet failure, though it is indistinguishable from one at a glance and it consumed a run id. Do not read it as a lost discovery day and do not compare its minutes against runs 143-145.

**2. THE CATALOG WORK IS MERGED AND THE CHECKOUT IS PULLED — what remains is the DRAIN.** D-436 and
D-438 are on `main`; the checkout is pulled and its catalog loads 7 families / 57 patterns, with 400
live bodies evaluated through the tick's own path and no crash. **The owed ledger drain releases
1,595 of 1,609 decisions — 99.1% — so: precision work FIRST, drain LAST, staged with `--job <id>`.**

**3. THE 50-BOARD SAMPLE IS READ AND THE REMAINING 282 ARE REFUSED (D-441). CLOSED** — do not re-open it from hiring.cafe's in-window counts, which is the number that was wrong. It bought **10 delivered leads** for ~60 min/run. Whether to keep paying is the OWNER's (row **A7**) and is a different question from adding 282 more, which is closed. Full numbers verbatim in `STANDING-FACTS.md`.

**4. RE-MEASURE GATE 1 AROUND 2026-09-09** (D-424) with
`.agent/2026-09-02-session/per_source_recall.py`. **The residual is LinkedIn alone**, and Track 2 is
the only lever that has moved since — which is why arming it (item 0) belongs before this, not after.

*(Closed since the last close: Track 2 — BUILT and DISARMED, D-433. The buried live requisition —
FIXED, D-432, and its blast radius re-measured as 1 job, not 16. The `_reported` folder drain —
SHIPPED, D-434. The `perf` flaky bound — CHARACTERISED and FIXED, D-435.)*

### Run 145 — read out, and both of the night's queue fixes are CONFIRMED IN PRODUCTION

96.4 min, exit **ok**, 94 tailored leads. Queue **598 apply / 732 review / 274 ineligible /
107 closed / 0 reported**. D-432 and D-434 both confirmed in production. Full readout moved
WHOLE into `STANDING-FACTS.md` at this close; numbers in `METRICS.md` (Run 145).

- **The job-apps unescape is MERGED (#354, D-443) — the numbers are now history, kept in
  `STANDING-FACTS.md`.** One lane's problem: jobapps **473 of 1,620 bodies (29.2%)**, every other
  provider 0.0%. **132 bodies gained their first requirement row, 83 verdicts moved, 11 leads left
  `eligible`**, each read against the employer's own quoted span.

- **THE `gh_jid` CONVERGENCE ITEM IS REFUTED AS AN IDENTITY QUESTION, AND THE REAL MECHANISM IS BIGGER THAN IT WAS (D-445).** It proposed an `IDENTITY_ALGORITHM_VERSION` bump — re-keying **161,085 postings to reach 4 leads**. Measured store-wide first: **all 4 cases are one employer under TWO `companies` rows** (Peloton, Roblox, Stripe, Lyft), so identity is not failing — the employer exists twice. **303 employers have postings under more than one row**, and it costs the shipped slate cap **20 redundant standing leads it cannot see** (89 on the `company_id` key, 109 on a company-NAME key; all 20 read by hand, zero false merges). **Company-row consolidation is the lever, is a DATA change needing no re-key or drain, and is NOT TAKEN** — it re-parents postings on the live store and the merge RULE needs its own measurement. **The first measurement returned a confident, wrong ZERO** because the key included `company_id` and a Greenhouse job id is unique across GREENHOUSE.

## Moved out of STATE on 2026-09-03d — the A4 two-year-bar block and the A8 defect pin, both settled by the owner's rulings, kept verbatim

A4 was refused after measurement (`near_miss_years_ceiling` stays at 3) and A8 was ruled and shipped as
#364 (D-455), so neither is a live question. Kept whole because A4's block is the record of a FACT being
distinguished from an INSTRUCTION, and the A8 bullet describes the defect the shipped sentence-scoped
escape repairs.

**1. THE 2-YEAR-BAR QUESTION IS NOW ROW A4 IN "Owner-gated" BELOW — it is a decision, not an
action.** The two things a future session must not re-derive: **lowering
`near_miss_years_ceiling` REJECTS rather than releases** (D-440), and **there is no data fix
hiding behind it** — the résumé parses to 20 months, of which 13 are internships these
postings exclude by name, so the stored `1` and the résumé agree against a 2-year bar. Full
reasoning moved WHOLE into `STANDING-FACTS.md` at this close.

- **A DEGREE DISJUNCTION DECIDES DIFFERENTLY DEPENDING ON WHICH ARM MATCHES — PINNED, NOT FIXED (A8).** `total_years_minimum` and `range_years_minimum` carry `degree_alternative_to_years`; the six scoped/domain patterns never did. So "a Bachelor's OR N years of X" **abstains** on the total arm and **rejects** on a scoped one — same sentence, opposite outcome, decided by which pattern happens to match. A peer session's control caught it while wiring the recall fix, and the wiring is **reverted**: a test now pins the defect instead. **If that test starts passing, somebody made A8's decision without Mit.**
- **The 2-year-bar question is ROW A4, and is stated there once.** It was written out here, in
  next-action item 1, and in the table — one decision in three places. The numbers that matter
  (**2,809 `unknown` · 258 `unmet` · 43 `met`** across 475 review-lane leads; two blind judges
  swinging ~10 of 40, which is why the wrong-hold rate is a RANGE of **17%-47%**) live in D-440.

---

## Session 2026-09-03e, moved WHOLE out of `STATE.md` on 2026-09-04e

Moved because `STATE.md` passed its ~250-line threshold again and its own header rules that the
fix is to move settled blocks out, not to summarise them away. Nothing is deleted. **One number
below is now historical and must NOT be re-quoted as live: the 95 gate verdicts (43/38/14) were
written against the PRE-RESET store and no final-gate row survives in the current one** — see
D-469 and `REPORT-2026-09-04e.md`.

### Session 2026-09-03e: the owed LEDGER DRAIN is REFUSED on measurement, the LLM FINAL GATE is ARMED for the first time and filters 38 of 95 delivered leads, and the armed drought alarm turns out to false-fire on 40 of 136 historical windows

Reasoning: **D-460** (the drain), **D-461** (the gate + the owner's years ruling), **D-462** (the
drought alarm), **D-463** (the aggregator refusal + the hiring.cafe ceiling correction). Numbers:
`METRICS.md`, the `Session — 2026-09-03e` block. Shipped: **#369, #370, #371, #372**.

**THE DRAIN D-455 LEFT OWED IS CLOSED BY REFUSAL, NOT BY DEFERRAL, AND THE OWNER RULED IT.** The
re-key ran first and is the half that paid — **151,626 postings re-evaluated** under
`1+bf844e01ebcb` (run 150). The drain itself relieves no scarcity: **83,168 open postings already
flow unsuppressed against 1,489 the ledger withholds (~56x)**, the ledger is **100% `built` / zero
`skipped`** so it can only re-deliver, and D-455's own win never needed it (those 996 postings were
never built and carry no disposition row). **The inherited "they rank low anyway" premise was FALSE
for this population** — p50 age **2 days**, so **1.41 score-points** lost, not the 9.7 the
2026-08-27 reading assumed. Stale stamps fail nothing; the drain stays available on his word.

**THE FINAL GATE IS ARMED AND HAS ROWS FOR THE FIRST TIME (0 → 95).** D-436's own architectural
answer, chosen by the owner over the deterministic topic net. **43 eligible / 38 ineligible / 14
uncertain**, 48 quoted spans, store-verified. **The owner ruled "a stated bar is a bar"** on the 28
`experience_years` verdicts — **and that ruling is bounded to the GATE, not to
`near_miss_years_ceiling`** (D-461, and see Owner-gated below).

## Sessions 2026-09-04d and 2026-09-04c, moved WHOLE out of `STATE.md` on 2026-09-05

Both blocks are settled: 04d's five tickets and 04c's run 2 are merged and recorded in
`CHANGELOG.md`, `D-466`, `D-467` and `D-468`. Moved verbatim, nothing summarised away, because
`STATE.md` was 311 lines against its own ~250 ceiling and the fix for that is to move settled
blocks out (D-139).

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

## Session 2026-09-04e, moved WHOLE out of `STATE.md` on 2026-09-05

Settled: all 23 tickets merged, recorded in `CHANGELOG.md` and `D-469`, and reviewed line by
line against the code by the 2026-09-04f planning session, which found the report accurate on
every claim it checked. Moved verbatim on the same rule as 04c/04d above — `STATE.md` was over
its ~250 ceiling and the fix is to move settled blocks out, never to summarise them away.
**One statement in it is now SUPERSEDED and is kept only as the record of what was true then:**
its warning that the 09-05 tick would deliver nothing until Mit re-approved. He re-approved at
21:08 on 09-04; T32 then re-stales it, and the current standing is in `STATE.md`'s head block.

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

## Session 2026-09-04f, moved WHOLE out of `STATE.md` on 2026-09-05b

Moved verbatim by the planning session of 2026-09-05b to keep `STATE.md` under its ceiling. Its
rulings are D-470; nothing below was edited.

### Session 2026-09-04f (planning review): the 2026-09-04e report HOLDS on every claim checked against the code; T30 is MERGED and the venv rebuilt on 3.13 — **green is now `make check` exit 0** (9,457 passed, 0 failed); the five open questions are ruled in D-470 and the next execution list is `HANDOFF-2026-09-05.md`

**Read this before acting on anything below it.** Reasoning: **D-470**. Numbers: `METRICS.md`, the
`Session — 2026-09-04f` block. The planning session read T22, SP2, T16, T13, T15, T6 and T30 line by
line against the code and found the report accurate on each. **One correction to the report's
framing:** the `--project` preflight sits AFTER the scan (`runner.py`, "P5a"), so an unapproved
tick scans for ~3 h, refuses, exits 1 and **never reaches eligibility — the owed corpus re-key does
NOT land on a refused tick.** **Mit re-approved at 21:08 on 09-04** — the stamp now carries
`content_digest`, so the 09-05 tick is expected to deliver and to pay the re-key.

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

## Session 2026-09-05 (execution), moved WHOLE out of `STATE.md` on 2026-09-06

Moved because `STATE.md` reached its ceiling again and this session is settled: run 3 was
read out in 2026-09-05b, and T37/T38/T39 — the tickets it produced — all shipped on
2026-09-06. Nothing is summarised; the block is exactly as it stood.

### Session 2026-09-05 (execution): the 04:00 tick was NOT waited for — **run 3 was launched by hand at 22:39; it FINISHED 00:43 exit 0 and is read in 2026-09-05b**; T31 and T32 are gate-green but **NOTHING IS MERGED**, and T33 is REFUSED on inspection at 0.701% held

**Read this before acting on anything below it.** Reasoning: **D-471**. Numbers: `METRICS.md`, the
`Session — 2026-09-05` block. **Written for the planning session:
`docs/program/REPORT-2026-09-05.md`. The remaining list: `docs/program/HANDOFF-2026-09-05-POSTRUN.md`.**

**`main` IS UNTOUCHED AT `84671523`.** The primary checkout runs the editable venv, so a live run
must not have its code swapped underneath it. Branch **`close-2026-09-05`** carries, in order,
`1fc61596` (T31: `init` seeds the bundled `resume_template.tex` when absent, never overwrites),
`d406a9f6` (T32: the résumé shell joins `projection_content_digest` and the approval screen), and
the close commit. **ONE `--ff-only` merge lands all three.** Full gate on the T31+T32 state: **exit
0, 9,462 passed / 0 failed / 1 skipped / 4 xfailed.** Worktrees `../bw-t31`, `../bw-t32`,
`../bw-close` are left in place; delete after merging.

**⚠ T32 STALES THE PROJECTION APPROVAL — Mit chose this at 23:26 on 09-04 on the condition that he
re-approves before the next `--project` run.** Until he does, any `--project` run scans in full and
then refuses at the P5a preflight. `boardwatch profile-bundle approve-projection`, controlling TTY.

**RUN 3 was launched by hand**, not by launchd: `run --project --top 40` with
`BOARDWATCH_HEARTBEAT_URL` and `BOARDWATCH_ALERT_URL` **unset**, so the 04:00 tick still owns the
heartbeat signal. Warm scan **283 of 288 boards in 79.3 min against run 2's cold 178.6 min**, and
the corpus GREW 61,927 → 81,777 open as `detail_fetch_budget` absorbs the backlog run 2 left
(`boards_partial` 70). **R1, T28 and T34 are CARRIED** — the run had not finished when the session
was wrapped.

**T33 IS CLOSED, AND THE RULING IS "NO".** The class D-470 authorised holds **429/61,232 =
0.701%** — inside its 1% bar, both null controls pass, and the threshold arm passes — but **14 of
20 printed held bodies are real JDs**, reproduced at ~11 of 20 on a second seed over a 24% larger
corpus. `MIN_BODY_CHARS` is an English-length constant that condemns complete Chinese JDs; a line
floor fails the same way. **The survivor is `residual_chars == 0`: 118 bodies / 0.193%, 10 of 10
chrome — sized as M, not S, and it is the one open question this session produced** (§4 of the
post-run handoff).

**T36 LOOKS WEAKER THAN IT DID.** The warm scan is 2.25x faster at `scan_workers` unchanged, so
the corpus warming up may already have paid the lever. `board_scans` cannot model this at all
(127 s of rows against a 10,716 s stage); only `funnel.scan.fetch_cost` can, and it double-counts
same-host blocking, so every projection from it is an UPPER bound. smartrecruiters is 24.0% of run
2's fetch cost on ONE host over 10 boards.


## The manual-run flag fossil, moved WHOLE out of `STATE.md` on 2026-09-06

Moved because the incident it narrates is long past — it names runs 151 and 152, and the
2026-09-03 reset restarted run ids at 1 — while the two facts inside it are permanent. Kept
verbatim rather than summarised.

- **A run was launched with the wrong flags this session.** `boardwatch run` defaults to `--top 10`
  and no `--project`; the daily driver is **`run --project --top 40`** — CORRECTED 2026-09-04d from
  `--top 100`, which this file and memory both carried; `plutil -p` on the live plist says 40. Run 151 was killed ~17 min
  in and relaunched as 152. **Never set `BOARDWATCH_HEARTBEAT_URL` on a manual run** — it would ping
  the production healthcheck and mask a real 04:00 failure.

## Session 2026-09-05b (planning review), moved WHOLE out of `STATE.md` on 2026-09-06

Moved because every ticket it produced — T37, T38, T39 — shipped on 2026-09-06, and its two
rulings (T33's residual-zero successor refused, T36 closed) are held in D-472. Kept verbatim.
Note that its T37 paragraph states the mechanism D-473 later REPLACED: the lost apply was a
WAL snapshot-upgrade conflict, not a `busy_timeout` starvation.

### Session 2026-09-05b (planning review): the 2026-09-05 report HOLDS; run 3 is READ (106.8-min warm scan, SP2 paid in full, 35 verdict moves, 3 apply / 37 review); T33's residual-zero successor is REFUSED on consequence, T36 is CLOSED on the smartrecruiters critical path, and the merge of `close-2026-09-05` is BOUND to Mit's re-approval — next list `HANDOFF-2026-09-06.md`

**Read this before acting on anything below it.** Reasoning: **D-472**. Numbers: `METRICS.md`,
the `Session — 2026-09-05b` block. R1 is DONE — do not redo it. **`main` is still `84671523`;
`close-2026-09-05` now carries FOUR commits** (T31, T32, the execution close, this planning
close) and one `--ff-only` merge lands them all.

**THE MERGE IS ONE STEP WITH THE RE-APPROVAL, IN MIT'S SITTING.** The launchd tick runs the
editable venv from `main`; merging T32 stales the projection stamp; a `--project` run with a
stale stamp scans ~107 min, refuses at P5a, exits 1 and withholds the heartbeat — a false alert
for a chosen condition. Until Mit can type `approve` right after the merge, `main` stays on the
T30 state and the tick delivers.

**RUN 3, READ.** Scan **6,418.6 s = 106.8 min, 1.67x faster than cold** (the 79.3 min quoted at
283/288 hid a 27.6-min tail); `lanes` join wait **0.001 s** against 363.8 s serial; eligibility
**648.4 s over 83,308** (cheaper than 665.5 s over 61,927, not dearer); tailor 5.16 s/lead (SP3
measurement 1 of 3); **3 apply / 37 review**. **The readout's move count was an apparatus zero**
(`input_id` is the inputs ROW id); resolved through `eligibility_inputs`, the shared 61,927
postings moved **35** against T4's predicted 29. **One board FAILED — SP2's first production
defect**: FidelityCareers' apply lost the write lock to the lane thread's back-to-back short
writes at `busy_timeout` 5 s and the whole fetched snapshot was discarded (**T37**: fetch
concurrently, apply serially).

**RULED (D-472):** `residual_chars == 0` — **NO**: 128 bodies, 120 `uncertain` + 8
`ineligible`, ZERO eligible, zero leads, zero ever tailored; no chrome class is open. **T36 —
CLOSED as specified**: both runs end on the smartrecruiters host ALONE (47.9 min of run 2, 27.6
of run 3), 1,931 detail requests on one host that the ordering then in force emitted one board
per round behind 135 Workday singletons — the lever is ORDER (**T38**), and `scan_workers` is re-decided
only after it. T15's guard never reaches the funnel (**T39**). T28, T34 carried unchanged; T35
gated on 09-09.


## Session 2026-09-06 (execution), moved WHOLE out of `STATE.md` on 2026-09-06b

Moved verbatim by the 2026-09-06b planning session so `STATE.md` stays under its ceiling; its
reasoning is D-473 and its numbers are `METRICS.md`, the `Session — 2026-09-06` block.

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

---

## Session 2026-09-06b (planning review) — settled, moved WHOLE from STATE on 2026-09-08

Every decision below was EXECUTED in the 2026-09-08 session: T40, T41 and T34 are done,
T36 and the fleet call stand as the rules they state. Kept verbatim, nothing summarised
away. Reasoning: D-474 (the rulings) and D-478 (what execution found against them).

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

## Session 2026-09-08 (execution), moved WHOLE out of `STATE.md` on 2026-09-09

> **Superseded in one respect, and it is the headline.** This block says T42 "is built but
> OFF and its arming is BLOCKED on an owner decision". That decision was taken (D-480) and
> the judge WAS armed on 2026-09-05; see **D-481**. Everything else here — the six tickets,
> the haiku ruling and its numbers, the T44 unreachability finding — stands as written.
> Nothing was deleted in the move.

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

**T42's arming: two preconditions are DONE, the third is deliberately WITHHELD (2026-09-05).**
The dedicated config dir `~/.claude-boardwatch` is logged in and verified answering
(`is_error: False`) on an **enterprise** seat, so the unattended judge cannot bill the personal
sub; and the plist now carries `CLAUDE_CONFIG_DIR` under `EnvironmentVariables` (added textually
so its comments survive, `plutil -lint` OK, backup beside it). `CLAUDE_CONFIG_DIR` IS the right
variable — confirmed in the installed binary; there is no `--config-dir` flag.

**NOT done, on the owner's explicit call: the `[gate]` block itself.** `gate.enabled` is still
`False` and the tick is still unloaded, so nothing judges and nothing runs unattended. Writing
that block IS the decision to settle the near-miss band in the reject direction at LLM cost per
run — hold it until P1 is planned. When it is written it goes in
**`~/Library/Application Support/boardwatch/config.toml`**, which is what `Settings` reads
(`BOARDWATCH_CONFIG_DIR` > platformdirs) — **not** `~/.config/boardwatch/`, which does not exist
and would arm nothing silently. `model` defaults to `sonnet`, so it must say `haiku` explicitly or
the run silently uses the 2.04x costlier model. Read it back through `Settings` and assert: unknown
keys are ignored silently, so a typo looks identical to success.

## Session 2026-09-07 (review + run 43) — settled, moved WHOLE out of `STATE.md` on 2026-09-13c

**T74's merge STANDS** — the exposure the ruling guarded against is THREE lane-row Qualcomm postings against 1,588 on the watched board; the 14–18% queue duplicate rate is a job-grouping failure (D-337) that board naming never touched. **The largest cross-board duplicate pair is HPE, not Northrop:** `hpe/acjobsite` + `hpe/Jobsathpe` share 1,013 `cross_host` groups over 2,227 open postings, pre-existing. **The slice `#` fragment broke `companies names`** for the two sliced boards whose name was the host: BAH 1486 and Leidos 1488 (2,027 open) deliver host-named. **Thales' three slice rows held 405 requisitions twice** at review time (row 256 had not reached `complete` before its siblings were added) — **run 43 then resolved it** (row 256 `complete`, 1,786 closed, duplicates 0). Rule kept: reach `complete` on the narrowed slug BEFORE adding a sibling slice row.

**Run 43 (the 12th pipeline run) — hand-launched 11:29 CDT on Mit's call, does NOT count toward the confirm.** `ok`, 36 min, 341 boards, 0 failed, RECONCILES, 1,459 new, 2,463 closed, 136,808 open, reach **92.7%**, censored 1 (Abbott). Gate 53 judged (36 / 6 / 11), 0 failed open; **8 PDFs** + 32 review. Queue 40 new / 18 moved / 0 failed, name mismatches 0. Every new instrument read: `throttle_retries` 48 with four eightfold boards still `partial` on the 12-retry board budget, `hidden_cluster_cap` 0, `shortlist_rank` on 53 of 53 judge rows. **First rank-band table:** `uncertain` 91–120 = 73% (8/11), 121–150 = 66% (19/29) — flat, no evidence 150 is too deep; accumulate ≥ 3 runs before moving `gate.depth`.

**Rulings taken 11:24 CDT ("we'll do your recommendations"), not to be re-asked:** (a) HPE — measure which site enumerates completely, then drain-then-drop the other; (b) `companies names` — match on the slug with its fragment stripped, then `names --apply` + `identities backfill` for BAH/Leidos; (c) the Thales closing-rule ticket is WITHDRAWN (moot after run 43). Full review: `.agent/2026-09-07b/REVIEW-BY-FABLE.md`.

**Next action.** (1) Read the 06:00 tick on 09-08 = **confirm day 3**; watch the four `throttle_exhausted` eightfold boards (is the 12-retry budget right?) and the rank table's n. (2) Rulings (b) then (a), after the tick — never merge while a run is in flight. (3) Mit's 0-B call on B8 (17.2% vs ≤ 16%) is the one failing bar. (4) T35 Gate 1 re-measure ~09-09. Still open from D-494: seed the cluster cap from the standing queue; a "network, read-only" effect marker; ratify `apple`'s `board_reported_total = None`; the Windows fake-claude CI class.

## Session 2026-09-12 (runs 44–48 read, rulings (b) and (a) executed) — settled, moved WHOLE out of `STATE.md` on 2026-09-13c

**Five unattended ticks, all `ok`, all funnels reconcile — confirm days 3–7 (run 48 = day 7 of 14).**
No code, config or rules change since 09-07, so the count holds. The 09-09 reboot moved the tick from
06:00 to **04:00 CDT**, exactly as predicted below; `launchctl` reads `runs = 3` since the reboot. The
fleet grew itself 341 → 486 by lane admission (113 boards, 32,402 open) and the open corpus 137k →
184k; run wall clock 36 → 55–102 min; censored boards 1 → 7. Numbers per run in `METRICS.md`.

**Ruling (b) DONE.** `companies names` matches a sliced row by its slug without the fragment; BAH 1486
→ `bah`, Leidos 1488 → `leidos`, the drained Northrop 1487 → `ngc`; `identities backfill` 2,238.
**Ruling (a) DONE, on a measurement the ruling's condition could not make:** BOTH HPE sites enumerate
completely. Keyed on the base requisition number, `Jobsathpe`'s 60 unique postings are ALL interns or
graduates (13 US, every one an intern) against `acjobsite`'s 257; neither ever delivered. `Jobsathpe`
drained to 1 and unwatched (D-494's mechanism). **The lanes had RE-ADDED the whole BAH and NVIDIA
boards beside their slices on 09-10** — two censored 2,000-row duplicates — because `stored_slug`
compared the fragment too. Fixed one-directionally (a plain slug resolves to its sliced row; a sibling
slice is still a second row), both drained and unwatched, 4,312 closed. **Every failed-open judge
batch on runs 45 and 48 was a 12-of-13 answer** (39 leads lost); verdicts now bind by `label`, a
skipped lead is reported `partly failed open` and is the only one unjudged. Three fixture reviews
(ashby/greenhouse/lever) extended to 2026-12-11 after a live shape re-check. `ashby:whatnot` (404)
and `vhr-otsuka/Pharmavite` (422) unwatched. **Fleet 481 watched.**

**Later the same day (D-499): the Gate 1 instrument was WRONG in boardwatch's disfavour** — it read provenance
off `raw_json`, which the jobapps lane's revision replaces. Corrected (v2, per version source):
**greenhouse 97.2%, ashby 100%, workday 96.6%, lever 100%** — every employer-board bar is cleared and the
lever question below is withdrawn; overall 35.2%, LinkedIn 42.6%, Indeed 24.9%, hiring.cafe 22.1%.
Applied Materials' censored Workday row was drained and dropped beside its Eightfold board (**fleet 480**);
two review-found defects in the morning's code were fixed and gated (empty verdict array = failed batch;
`companies add` over a slice says so). `hidden_cluster_cap` read 0 on all five runs.

**Rank band, 308 ranked judge rows over runs 43–48: FLAT.** Deterministic `uncertain` converts 31 /
56 / 46 / 47 / **62%** across the five 30-rank bands; the deepest band is the best. `gate.depth = 150`
stands; whether deeper pays is unmeasured and a cost call. **Gate 1 (T35) re-measured: 34.8%
independent recall** (was 23.8% on 09-02); greenhouse 91.5%, ashby 92.6%, workday 96.6% clear the
≥ 85% employer-board bar, **lever 70.0% on n = 10 does not** — SUPERSEDED by D-499 below, lever is 100%;
linkedin 42.3%, indeed 24.7%, hiring.cafe 20.2%.

**Next action.** (1) Run 57 is READ (above). Read the 04:00 tick on 09-14 (**run 58** = confirm day 9): the `stale` count on the reach line, the T78 nightly count (2 of 10 if green), and expect `partly failed
open` lines instead of failed batches, BAH/NVIDIA/HPE-Jobsathpe absent, watched 480, and check that no
lane re-adds a sliced board (`select … from companies where slug not like '%#%' and lower(slug)
in (…sliced bases…)` must stay empty). (2) Mit's calls, in one batch: 0-B (unchanged, the one failing
bar); 0-C (D-498, the lane-copy suppression); 0-D (D-500, the lanes' secondhand declaration); whether to slice or drop the five new censored retail boards (Advance Auto 16,869 · Five Below ·
Cushman & Wakefield · Abbott — 8 software titles among ~6,850 open on the three retail ones, D-501). (3) The Indeed and
hiring.cafe per-source THRESHOLDS at ~09-17, against today's 24.7% / 20.2%. (4) **The nightly Windows class is CLOSED (D-497)** — the unmarked judge test is skipped and a dispatched full
matrix is green; **T78 is FIXED in the test (D-501)** — a Windows probe measured the busy handler
starving one writer for all 200 of its competitor's commits, the guard's writers now carry 60 s, green on
Windows 3.11/3.12/3.13 in a dispatched matrix — the t81 matrix is **fully green, all 27 jobs**, the first since 08-31; **closes after ≥ 10 clean 3.13 Windows nightlies** (the
`t78-probe` branch and its temporary workflow stay until then, never merge). `nightly-watch` (#95) will keep opening on it. Still open from D-494: seed the
cluster cap from the standing queue; ratify `apple`'s `board_reported_total = None`. The "network,
read-only" marker question is answered (D-497 §4): the vocabulary already says it.

## Run 57 (2026-09-13 tick) — settled, moved WHOLE out of `STATE.md` on 2026-09-14

Superseded twice: run 308 read the fleet and the drain behind it, and the `stale` spike this
block flagged as unverified is answered (139 → 51, transient).

**Run 57, the 04:00 tick, `ok` in 58 min: 480 boards, 0 failed, 5,098 new, 4,108 closed, 177,958 open,
funnel reconciles — confirm day 8 of 14.** Gate 58 judged (30 / 6 / 22), **0 batches failed open**, and the
new partial path worked live: batch 3/5 answered 12 of 13 and the run reads `partly failed open: 1 of 13
verdicts missing` with the 12 kept. 9 PDFs + 31 review, 10 withheld as gone, 6 gate-rejected; queue 40 new,
12 moved. No watched unsliced copy of a sliced board (the D-496 query is empty). The lanes admitted 32 more
boards → **watched 487**; censored 4 (short 15,242). One number to read again on run 58: the reach line's
`stale` jumped to 139 (26–42 on runs 44–48) — likely a quiet Sunday of 304s, unverified. **Nightly CI
2026-09-13 (34757609598): GREEN — the first scheduled green since 08-31; T78 clean-nightly count 1 of 10.**

## Next action

**0. THE 06:00 TICK IS STILL UNLOADED, AND RUN 4 HAS NOT HAPPENED — ON PURPOSE, until
`HANDOFF-2026-09-09.md` §4's sequence has run: T47 merged → `policy ceiling experience_years 1` →
`[gate]` block verified → tick.** Run 4 is the first COUNTED run of the provisional pass and must
reflect the ≤ 1-YoE ruling; an eligibility change after it restarts the count. `launchctl bootout`
was run at 05:47 CDT on 2026-09-05 so merges never landed under a live run of the editable venv.
`main` holds all six D-477 tickets and the primary checkout is parked on `main`, so once the
sequence is done the re-load is:

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

**0-1. T34 (M1) IS EXECUTED, read-only, blind two-judge steps included (D-478; METRICS `Session — 2026-09-08`).**
T35 (D-424) is gated on 09-09; `.agent/2026-09-02-session/per_source_recall.py`, standing 28.8%.

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

**1. THE YEARS RULING HAS PROPAGATED — RULED (D-478 §5), PLANNED (D-479), DECIDED (D-480), NOT
EXECUTED.** "I dont want jobs which have more than 1 YOE" is an instruction, not a fact, so A4's
distinction is satisfied. Nothing is left to ask: T47, the value, the gate block, the tick.

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

---

## The two 2026-09-13 close blocks, moved WHOLE from STATE.md on 2026-09-14b

Settled: run 308 read every prediction in them and tonight's session superseded the open items.
Nothing was deleted or summarised.

### 2026-09-13 close (c) — THE SENIORITY LEVER, RULE (b), THE 243 RENDERS, AND THE THRESHOLDS RULED: **D-504, D-505.** PR #375.

**Mit gave full authority for everything on the previous close's list, and all of it is done.**

**The apply lane's bottleneck MOVED, and that is the session's real finding (D-504).** After 0-B,
the dominant residual defect is not eligibility at all — **`seniority_fit` is 60% of the audit's
unapplyable calls and 13 of the 14 in the promoted cohort** — and the title ladder cannot see it,
because **every audited item read `in_band`**. So the judge that already reads the whole JD is asked
`seniority_fit` beside its verdict (never inside it: no verdict, no `rules_hash`, **the confirm is
not restarted**), and a `no` holds under its own reason `seniority_judged_above_band`.
**SHIPPED DISARMED** — validated against sonnet and opus on 149 items, haiku catches **14 of 15**
senior bodies and invents **18 of 134**, so arming projects **457 @ 16.3% → 364 @ 9.0%, volume
−20%**. That trade is Mit's; `gate.seniority_hold = true` is one line, needs no re-judge, and the
reading accumulates either way so it can be re-measured live first. **This is the open
recommendation: ARM IT** — 9.0% clears B8's ≤ 16% bar with room, and a held lead is still delivered.

**The 243 promoted leads all have résumés now, and the drain was recorded WRONG.**
`boardwatch tailor run <id>` alone returns `page_limit_exceeded` on every lead — it renders the
authored résumé, which does not fit the page budget. The real drain is **two** commands
(`resume project` then `tailor run --resume`), ~5.1 s. Ran over all 243: **243 ok, 0 failed**;
verified through `delivered_unapplied` at **244 with a PDF, 0 missing**. The `runner.py` comment is
corrected.

**0-D's repair half needs NO CODE.** Re-measured, the population GREW through run 57 (112 → 123
overwrites, 301 → 302 `raw_json`) — but **118 of the 123 are on WATCHED boards**, where the scan
already revises them every run and the lane simply overwrote it again afterwards. With the
declaration shipped the board body wins, so it drains itself. **Prediction for run 64: both counts
fall toward 0.** Residual: 5 postings on unwatched boards, measured and accepted.

**D-498 rule (b) shipped** (highest-ranked lane copy survives a lanes-only group).

**PR #375 is MERGED.** `main` carries all of it and the editable venv the tick runs is on it.
**Run 308 read it — see the block above.** What that close asked for: (1) the 04:00 tick, confirm
day 9 — and read it against four changed behaviours: a bigger apply lane and smaller review lane
(0-B), `hidden_lane_copy` non-zero (0-C + rule (b)), 484 boards, and the 0-D drain prediction above.
`seniority_judged_above_band` should be an EMPTY bucket until Mit arms it. (3) **Arm
`gate.seniority_hold`?** — Mit's, recommended yes, numbers above. (4) **The second Gate 1 reading is
owed ~09-19** and it is the LAST condition on M4: with D-505 ruling no bar for Indeed and
hiring.cafe, the employer-board half alone decides, and all four boards already clear 85%. If the
second reading holds, **job-apps switches off**. (5) Still open from D-494: seed the cluster cap
from the standing queue; ratify `apple`'s `board_reported_total = None`.

### 2026-09-13 close (b) — MIT'S FOUR OWNER CALLS TAKEN AT SESSION START AND ALL FOUR EXECUTED: **D-502, D-503.** PR #374.

**The batch, and the answers.** 0-B promote the two requirement holds, blind-audit first. 0-C rule (a)
only. 0-D declare on the converging lanes. Retail: drain and drop. Every one is now shipped, gated
(`make check` exit 0, zero failures) and on PR #374. **Nothing moved `engine_version` or `rules_hash`,
so the 14-day confirm is NOT restarted.**

**0-D shipped NARROWER than the ruling, because D-500's premise was wrong for two of the three lanes
(D-502).** hiring.cafe appends the PROVIDER's own `RawPosting` verbatim — only its recorded
`source_url` is the aggregator's, because the lane owns the GET — and `jsonld` has never converged
onto a board posting at all; declaring either would freeze firsthand data. **job-apps IS the defect**:
612 `revised` versions onto board postings, ALL tier 1, and the board's very next reading reverted
**87 of 436 (20.0%)** by more than half the body. Tier 1 declares `CONVERGED_SECONDHAND`; tiers 2 and
3 declare nothing. The REPAIR half (117 overwritten bodies, 301 lane-payload `raw_json` rows) is NOT
done — Mit chose the declaration, not the repair, and it stays available.

**0-B shipped BEHIND the audit Mit required, and the audit is the reason it is safe (D-503).** Three
arms of 56 shuffled into one pool, judges **sonnet and opus** (never haiku, the production judge under
test), 96.4% inter-rater agreement: **the apply lane as it stands 21.4% unapplyable, `experience_requirement` + judge 1.8%, `no_requirements_found` + judge 16.1%** — so promoting 248
leads into 209 gives **457 at 16.3%**, moving B8 toward its ≤ 16% bar instead of away from it. D-458's
**32%** for the same silent-clear class collapses to **16.1%** once the judge filters it, which is the
claim that was under test. It releases those two holds ONLY; `eligibility_unconfirmed` stands because
an abstain is not evidence. **No seniority refinement exists** — 13 of the 14 `nrf` failures are
`seniority_fit` and every item in all three arms reads `in_band`, so the title ladder cannot see them.
Report: `.agent/2026-09-13-session/promotion-audit/REPORT.md`.

**0-C shipped as rule (a):** 17 of the 34 multi-member `cross_host` groups on the 589-lead standing
queue, own bucket `shortlist.hidden_lane_copy`, `top --include-lane-copy` drain, keyed on
`PROVIDER_NAMES` and not `classify_host`.

**The three retail boards are GONE. Fleet 487 → 484, 6,884 postings closed, 3 residual open.** Measured
first against a control: 0 leads ever delivered from any of the three. Abbott stays (7 delivered).

**PR #374 is MERGED and main's CI is green.** `main` is `78068ef9`; the editable venv the tick runs
carries all three changes.

**Next action.** (1) Read the 04:00 tick on 09-14. **It is run 308** — superseded twice in one day:
the retail drain wrote 58–63 (six `boardwatch scan` invocations) and the 243 promoted renders then
wrote **64–307**, because **`resume project` and `tailor run` each open a run row too**. That is the
wider rule, and it is the second time in two sessions the tick's number was predicted wrong: **any
CLI command that builds a context writes a run**, not just `scan`, so predict the next tick's number
by reading `max(runs.id)` at the END of a session, never by adding one to the last tick. It is **confirm day 9** whichever number it carries; only the tick
counts toward the confirm, a hand scan never does. Read it knowing THREE delivery behaviours changed:
expect a bigger apply lane and a smaller review lane (0-B — **244 standing folders move `_review` →
apply on the first reconcile, all with `pdf_missing`**, see the résumé item below), `hidden_lane_copy`
non-zero in the funnel (0-C), and 484 watched boards. Also on the list: the reach line's `stale` (139
on run 57, 26–42 before) and the T78 nightly count (2 of 10 if green). (2) **The Indeed and hiring.cafe per-source THRESHOLD is the only
M4 item left and is still Mit's** — the numbers are in hand (24.9% / 22.1%, D-499) and the
recommendation put to him is NO BAR on either, same as LinkedIn, on the ground that they are reach
lanes into employers no board covers. (3) **The 244 promoted folders carry no résumé and were deliberately NOT rendered.** They were
delivered `pending_tailor`, and the tailor loop only renders the current run's shortlist, so no run
will pick them up. The drain is `boardwatch tailor run <posting_id>`, ~4.35 s each (~18 min for 244).
Held because **Mit's per-lens formatting session is still owed** (open questions item 3) — rendering
244 documents in a format he has not signed off is the wrong order. His call. (4) Still open from
D-494: seed the cluster cap from the standing queue; ratify `apple`'s `board_reported_total = None`.
(5) D-498's rule (b) (+18) and 0-D's REPAIR half (117 bodies, 301 `raw_json` rows) are sized and
unbuilt — neither was ruled on.


## The five settled 2026-09-14b … 2026-09-18 STATE blocks, moved WHOLE out of `STATE.md` on 2026-09-19e

Nothing deleted. Each was already a pointer to its decisions; they moved because adding D-524's block took `STATE.md` past its ~250-line bar, and the file's own rule is to move settled blocks out rather than summarise them away.

### 2026-09-18 — run 434 (confirm day 13), T88–T91 read live, six owner decisions ruled. **Held WHOLE in D-519, D-520 and `METRICS.md`; do not re-derive.** **One correction: D-519 ruling 6 records the years ceiling as 3; the LIVE value is 1** (run 434's own rules snapshot; `catalog.py:252` has the policy override beat the catalog default), so its "7 leads at a bar ≤ 3" sizing was taken against the wrong value and must be re-read before it is cited. The ruling — change nothing — stands.

### 2026-09-17b — the first autoapply pre-flight, verified and ticketed; T88–T91 + T93 shipped inside the freeze. **Held WHOLE in D-518 and `TICKETS-2026-09-17.md`; do not re-derive.**

16 of the 22 leads the owner withdrew were review-lane holds, not apply-lane leads — **source a
pre-flight from the apply lane alone**. The six real slips split into liveness (T88–T90) and the
Greenhouse form (T91); all read live on run 434 with the manifest unmoved. **Every owner decision
the tickets file left open is now RULED in D-519 — §3 carries nothing live.** T92 is parked for the
post-M5 batch.

### 2026-09-17 — run 433 (confirm day 12) and web wave 2 shipped after a blind review of a green union found six defects. **Held WHOLE in D-517 and `METRICS.md` (session 2026-09-17); do not re-derive.**

Run 433's manifest is byte-identical to run 432's across the wave-1 merge — D-515's claim that web
work cannot move the confirm window, measured, and reproduced again on run 434. The wave-2
features (follow-up dates, the applied history at `#/applied`) are shipped; **the job-keyed
follow-up route that made the 58 imported applications usable is T94 (D-520).**

### 2026-09-16 — run 432 (confirm day 11), the web-only-UI ruling, web wave 1 (PR #381). **Held WHOLE in D-515, D-516 and `METRICS.md` (session 2026-09-16); do not re-derive.**

`boardwatch web` is the ONLY UI — never publish an artifact, sheet or CSV of the queue — and web
work continues through the confirm window because `delivery/`, `store/delivery_queries.py` and
`web/` are outside the four digested engine modules (D-515). Wave 1: gate verdict on every row,
"new since last visit", ATS sort, bulk skip, `jurisdiction` in words, the dialog sheet; and
`judge_seniority_above_band` had never been on the wire (D-516). Stale-policy gate rows 36 → 5:
D-512 works.

### 2026-09-14b → 2026-09-15 — B8's PRECISION half MET (its VOLUME half was never read — see 2026-09-19); every bar clear except the two dated readings on 09-19, both since taken. **Held WHOLE in D-506 … D-514 and `METRICS.md` (sessions 2026-09-14b and 2026-09-15); do not re-derive.**

The apply lane read end to end by the production judge (D-507: 23% is NOT a defect rate); rule
(a)'s standing-side drain (D-506); the ≤1-YoE harvest (D-509); applied history imported 18 → 61;
D-508's corrected count; D-510's review of the live store; D-511's prefix-match defect and the
797-lead re-judge; **the judge does not reproduce (65.6% self-agreement on `decision`)**; D-512's
exact-version freshness fix; D-513's B8 mis-quote; **D-514: B8 MET post-drain at 6.9% / 5.6%**,
the hold demoting ~26 applyable leads per 160 as its cost. Owner's worklist
`~/boardwatch-apply-2026-09-14/` is superseded by the web app (D-515).

## The settled 2026-09-19e STATE block, moved WHOLE out of `STATE.md` on 2026-09-20

### 2026-09-19e — **ASTRA REVIEW 02 IS CONSUMED (D-524): ALL EIGHT FINDINGS CONFIRMED; T106, T107, T108, T109 AND T112 ALL SHIPPED; T110, T111 AND T113 TICKETED in `TICKETS-2026-09-19-ASTRA-02.md`. THREE OWNER QUESTIONS RULED. NOTHING HERE TOUCHES THE ENGINE — no ledger re-key, no drain, no confirm-clock restart. `main`'s FOUR-COMMIT CI RED IS FIXED and unrelated to the review.**

Both falsifiers re-run here (every row of five tables reproduces); every cited `file:symbol` opened
by a read-only Opus verifier on the seat (`.agent/astra/verify/02-report.md`, $3.56). **The apply
lane's defect is that its CONSUMERS do not honour the distinctions the stack draws:** the gate judge
does not fail open at three seams it claims to (F2, **fixed: T106**); a PARTIAL judge outage is
neither counted nor escalated — run 467 carried one (F4, **fixed: T107**); the gate row key does not vary
with the judge MODEL, so the pending model move would reach new leads only (F1, **fixed: T108**);
four standing call sites drop the title-seniority hold and none can see a judge NEGATIVE
(F3, **fixed: T109** — the 12 leads below leave the apply lane for review the day it lands); three lexical spellings classify inconsistently (F5, **fixed: T112**); B8's instrument is
the pre-form-sweep render count (F6, **T110**) and a routing change moves no manifest hash (**T111**);
a stale gate negative suppresses its own repair and the one manual path reads through the same hide
(F1, **T113**).

**Measured here, read-only, each with a null control:**
- **B8's 25 on run 467 is NOT an overcount** — 0 of its 25 rendered leads match a form hard stop
  (7 have a fetched form at all); the same call over all 48 forms store-wide returns 3. **Rule
  next-action 3 on 25 as recorded.** T110 is still owed — the base rate is ~6% of fetched forms.
- **F3's judge-negative half is 12 leads today**: 45 delivered versions carry a current judge
  `ineligible`, 17 of those also carry a deterministic `eligible` (⇒ APPLY via row 9), 12 open and
  unapplied. D-511's 19, still live.
- **97 of 984 delivered posting-versions have no current-identity gate row at all** — size T113 there.
- **T112's level-separator fix has NO live population**: 1,010 → 1,011 matches over 261,626 open
  postings, and the one new match is a false positive the role gate already vetoes. Kept; never
  cite it as a win.

**Owner's three rulings (2026-09-19 ~22:35).** (1) A current judge `ineligible` **HOLDS a standing
lead in review** under its own reason — folded into T109. (2) Routing gets a **SEPARATE lane-policy
fingerprint**, not a reclassification of `_GATE_IRRELEVANT` — T111; the five-hash manifest keeps its
meaning. (3) F7's targeted second reading is **NOT NOW** — ship the judge-model move first, one
variable at a time, and re-read repeatability on the new model before pricing it. **F8 (portability)
is DROPPED, not deferred** — D-477 point 4 already rules it; its seven confirmed hardcodings are
recorded as the v2 boundary.

**T108 must land before the judge-model move** (next-action 4): without it the move reaches new
leads only. It also collapses T99's pending one-time re-judge into the same run.

**The session's split, and its cost.** This session orchestrated, verified and gated; the enterprise
seat executed. **Seat total $43.57** — verify $3.56 (54 turns), T106 $4.75 (55), T107 $6.97 (66),
T108 $6.01 (88), T109 **$19.17 (165)**, T112 $3.11 (45). **T109 cost 3-4x every other ticket** and
is the number to size the next plumbing-shaped ticket against: it rewrote five call sites into one,
touched `web/` (the `ReviewReason` catalog is mirrored in TypeScript), and ran seven mutations.
Four `make check` runs were spent here, not on the seat (executors are barred from the gate):
union 10:39, docs 12:20, wave-2 08:14, final 07:19 — all exit 0, 10,348 then 10,383 passed.

**`main`'s CI was RED for four consecutive commits before this session and is now GREEN — the cause
was NOT the review.** Two tests in `web/src/__tests__/followUp.test.tsx` pinned `2026-09-20` as a
LITERAL future date; the follow-up chip reads "follow-up due <d>" once d is today or past, so the
assertion silently became a different one on arrival, and CI (UTC) crossed that boundary five hours
before local did. **A green local gate could not predict it and a re-run could not reproduce it** —
`TZ=UTC` reproduces it exactly (2 of 25 fail, the two CI named). Both now derive the date from
today. The other 14 date literals in that file compare dates to each other or to an input value,
never to today, and were left alone.

## The settled 2026-09-20d/e STATE block, moved WHOLE out of `STATE.md` on 2026-09-20g

### 2026-09-20d/e — **THE ASTRA REMEDIATION BACKLOG IS CLOSED TO THIRTEEN TICKETS IN ONE GATED WAVE, AND IT IS MERGED (D-528, PR #398 → `09df0e87`). WINDOWS IS GREEN AND THE FIVE-NIGHT RED IS OVER. THE ENGINE BATCH IS THE ONLY DEFERRAL. NOTHING HERE RE-KEYS — no drain, no confirm-clock restart.**

**The gate, on the commit that actually merged.** `make check` exit 0 on **`82ad88da`** — 10,584 passed (baseline 10,542), 1 skipped, 4 xfailed, coverage 95.25%, 9m16s, all six targets present. The earlier reading was on `42bc2696`, one commit short of HEAD; the gap was four program docs plus one line in `tests/unit/test_delivery_queries.py`. **After the merge, `git diff 82ad88da HEAD` is empty** — the merge tree is byte-identical, so this reading is valid for `09df0e87` and the 04:00 tick runs exactly the gated code.

Shipped: **T110, T111, T120, T121, T122, T126, T128, T131, T134, T136, T138 (per-file half),
T139 (doc half), T148.** Five came from three enterprise-seat executors in their own worktrees
(`t122`, `t134`, `t110`), **each gated here, never by itself**; all three merged with zero
conflicts. **Held WHOLE in D-528; do not re-derive.**

**T128 WAS THE ONLY THING ACTUALLY BROKEN, AND IT WAS WORSE THAN RECORDED.** The scheduled build
was red **five** consecutive nights (09-16…09-20), not four. Three Windows-only failures, invisible
to every push CI because **Windows runs on `schedule`/`workflow_dispatch` ONLY**. Validated by an
explicit `workflow_dispatch` on the branch — the only way to see that matrix before merge.

**NEXT ACTION 4's ONE-TIME RE-JUDGE HAS FIRED AND IS CLEAN — it was recorded as owed and was
already discharged.** Run **468**: `funnel-468.md` reads `120 candidates · 0 already current ·
120 sent`, 0 failed open / 0 missing / 0 refused; the store independently shows run 468 = **120
rows `model='haiku'`** against `model=NULL` on 434/447/467. **T108 is discharged and PROVEN LIVE** —
the gate row varies with the model, so the Sonnet move reaches standing verdicts, not only new leads.

**THREE MEASUREMENTS CLOSED ITEMS WITHOUT CODE.** (1) **The composite-title asymmetry is REFUTED**
— astra's "only harmful" long-qualifier case reads `uncertain` (held for review), NOT `not_swe`;
of 26,830 open "software" titles the 563 reading `not_swe` are 540 non-engineering nouns plus 23
correct vetoes, so **genuinely-SWE titles hidden: 0 of 260,306**, null-controlled. **Do not rewrite
the parser.** (2) **T136's `ge=1` deliberately NOT changed** — 12 of 25 real runs exceed 60 min
(median 59.3, max 200.2) so a one-hour reaper would close a LIVE run, but a flat floor breaks
multi-tenancy. **The number is Mit's; the missing test shipped.** (3) **T122 re-measured after run
468 reproduces exactly** — 16,510 under 8 boards, 6.34%, partition-verified.

**T113 IS RE-SIZED BY AN ORDER OF MAGNITUDE.** The freshness test compares `model`, so every
pre-T108 row is stale: **1,203 of 1,323** posting-versions, not the ticket's **97**. And **the
re-judge is a ROLLING backlog** bounded by `gate.depth` per tick, not one run — true of the SLATE,
false of the stored corpus. **Do not quote the 97 again.**

**Two executor judgment calls accepted, both flagged by the executor.** T134 made a RAISED form
sweep escalate (right — a failed sweep means T91 hard-stop leads shipped UNHELD). T110 kept the B8
volume reading OFF `summary.errors`, so it reaches the funnel but not the escalation channel;
**that one is Mit's to reverse** and one line at the call site does it.

**The finalize-block order was CHECKED after the three-way merge** (D-374's marker had drifted and
was repaired): `form-sweep → funnel → queue → intake → scan → drought → lane-volume → liveness →
corpus → morning → heartbeat`. Nothing below `_emit_morning`; heartbeat last.

## The DISCHARGED half of the 2026-09-19 STATE block, split out on 2026-09-20g

Run 467's expansion numbers are superseded by run 468's second reading (2026-09-20g block,
D-531 era). Held in **D-521** and **D-522**. The B8 and Indeed paragraphs stayed in `STATE.md`
because both are still unruled.

**Run 447 (readout in `METRICS.md`).** `ok`, RECONCILES, **manifest byte-identical to run 434's on
all five hashes**, one identity across the whole run. B1 40 · B2 19/19 · B3 0 failures ·
B5 40 artifacts · B6 RECONCILES · B7 0% abstain. **B4 is VACUOUS, not met** — 0 bullets seen, so it
contributes nothing to n ≥ 100. **B8's volume half reads 19 against ≥ 20.**

**Owner's word, 2026-09-18 22:56: "I am giving you permission to count it as Day 14."** Run 447 was
hand-launched on run 434's commit and the UNCHANGED 652-board fleet, so day 14 read on the frozen
corpus and the expansion landed after. **The confirm therefore evidences 13 unattended ticks plus
one attended run** — it no longer evidences "the plist fired on the 14th day", which 13 prior ticks
and Gate P3's own counter already cover. Do not let a later reader mistake it for 14 unattended days.

**Gate 1, the reading of record** (7 days after D-499, as D-482 required): greenhouse **99.3%**,
ashby **100%**, workday **100%**, lever **100%** against ≥ 85% — clear on both readings.
Drawn-from total 35.2% → **44.6%**. **M4's exit condition is met.**

**Discovery was three disjoint backlogs (D-521 §1).** Gap A **958** stored-but-unwatched on a
parseable provider — cause: **hiring.cafe admits ~78 real employer boards per run and writes every
one unwatched**; Gap B **593** GitHub new-grad-list boards; Gap C **43** behind the `grnh.se` seeds.
Stage 1 (ashby/greenhouse/lever/workable) was live-probed — 14 dead caught, including
`greenhouse:embed` — and **1,155 imported, exit 0, zero skipped. Fleet 652 → 1,807**, verified by
counting the store, provenance intact. **Stages 2–3 (workday 230, oraclehcm 62, smartrecruiters 78)
are REFUSED** on measured lead density: ashby 3.05 vs workday 0.17 vs oraclehcm **0.00** per 1k open.
**Gap C is emitted but NOT imported — never put to the owner.**

**Volume is not the constraint (D-521 §4).** 99.77% of the corpus is evaluated; ~40 delivered/day
against ~841 standing. `--top` stays 40 and the lane caps stay.

**RUN 467 — the first tick on 1,807 boards (readout in `METRICS.md`).** A REAL tick
(`launchctl runs = 9 → 10`); it is run **467**, not 448, because web renders consumed 446-466.
`ok`, **RECONCILES**, **manifest byte-identical to 447 and 434 on all five hashes** — the measured
proof that watching boards moves no hash. **65 min** on 2.8× the fleet. **1,155 of 1,155 new
boards scanned `complete`, zero failures added.** Corpus 208,847 → **261,626**; eligible verdicts
7,675 → **8,581**; **B8's volume half 19 → 25, MET** after failing 9 of 14 confirm days;
**28 of the 40 delivered leads came from the new boards.**

**THE SIZING RULE (D-522 §3), which inverts what was assumed:** a lane's secondhand sample of a
board is a **terrible** predictor of its SIZE (2.6 postings vs a real **51.6**, off 20×) and an
**excellent** predictor of its ELIGIBLE RATE (2.1% vs a measured **2.05%**). Size from fleet
density; predict yield from the sample. Never the reverse.

---

## Settled session blocks moved out of STATE on 2026-09-21 (verbatim)

Three blocks, all discharged by that session and held in D-532 … D-535 plus D-522/D-530/D-531.
**2026-09-20g** — run 468's reading, superseded by run 469's third tick (D-532), and T104's
refutation, shipped and merged. **2026-09-20f** — the engine batch's opening; it merged as
`ea95c42c`. **2026-09-19** — run 467, Gate 1's second reading, and the stage-1 import; every
condition in it is discharged and its sizing rule is superseded by D-532's unit correction.

### 2026-09-20g (moved whole)

### 2026-09-20g — **RUN 468 ANSWERS NEXT ACTION 1: the new boards' 2.05% RATE HOLDS EXACTLY, the VOLUME was a first-scan bulge (584x), and the 70%-of-slate share is now PURE BACKLOG DRAWDOWN — 25 of 25 new-board leads were first seen in run 467, ZERO in run 468. T104's DESIGN IS REFUTED AGAINST ITS OWN CASES (D-531); its mechanism ships UNUSED on `engine-batch`. `make check` IS BLOCKED BY MACHINE LOAD, NOT BY CODE.**

**Next action 1 is DISCHARGED. Both halves of the question were true at once.** Cohort = the 1,155
boards with `scan_kind='board'` in run 467 but not 447; it sizes to exactly 1,155 and the same
apparatus reproduces run 467's recorded **28 of 40** slate share, which is the null control.

| | run 467 | **run 468** |
|---|---:|---:|
| new-board **stock** open / eligible | 59,622 / 1,222 = **2.05%** | 59,618 / 1,219 = **2.04%** |
| new-board **flow** (`kind='new'`) / eligible | 56,635 / 1,159 = **2.05%** | 97 / 2 = **2.06%** |
| leads from the new boards | **28 of 40 (70%)** | **25 of 40 (62%)** |
| provenance of those leads | 27 first seen THAT run | **25 of 25 first seen run 467** |

**The rate generalises; the lead contribution does not, yet.** 28→25 is inside noise (z≈0.71), but
zero of run 468's own 97 fresh new-board postings produced a lead. Steady-state replenishment is
**~2 eligible/day** against a ~25/day draw, over **1,139 undrawn** eligible (of 1,219; only 80
carry a disposition). **Days-of-runway is UNSIZED and must not be quoted** — eligible is not
slate-reachable (8,518 eligible → 75 shortlisted → 40 delivered, `capped_by_top_n` 10,562). **A
third tick is what distinguishes decay from plateau.** Old boards read **3.69%**, denser per
posting than the new ones. Reconciles four ways against funnel-468's own stage counts.

**T104 IS REFUTED AS SPECIFIED (D-531) — do not build it from the ticket.** Regressions 8 and 9
both put the escape in the immediately following sentence, which is exactly what
`abstain_by_adjacent` is defined to see, so both keep reading `uncertain`; only sentence scope
reaches them, and sentence scope breaks the waiver control. They are **the same shape at the same
distance** — no distance-based reach separates them. Astra's own waiver example is a **vacuous**
control (it fires `master_required`, which the ticket never moves); re-positioned onto
`doctorate_required` it reverses. The ticket also names **2 of the 11** patterns holding those two
**shared YAML anchors**. A verified non-distance discriminator ("reach the next unit only if it
states no requirement of its own") satisfies **all six** cases and is held as a patch, NOT
committed — its failure direction is job-deleting and the live delta over the **67,587** movable
postings is unmeasured.

**MIT RULED (c) AND IT IS BUILT AT THE WIDER SCOPE.** `engine-batch` is PUSHED (no PR) and holds
the mechanism at `f0e5a009` plus the ownership-guarded reach with **all eleven** document-scoped
escapes moved. **`abstain_by` now has ZERO users**; the census pins the pair (`abstain_by: 0`,
`abstain_by_adjacent: 11`) so a future pattern taking the unbounded reach fails the gate.

**The scope was decided by measurement, and it inverts the risk framing.** Over the COMPLETE
67,587-posting movable population — completeness checked, `postings.body_text` is identical to the
current `posting_versions.body_text` for all 260,306 open rows — **adjALL is a strict superset of
adj2** (0 postings move under adj2 that do not under adjALL), and its extra **108** are **+91
`eligible` against +16 rejected**. adj2 would have been 209 rejections for 3 finds. Baseline
control: **67,400 of 67,446 re-evaluations match the LIVE stored verdict (99.93%)**. Three sampled
finds were each verified correct and each is adjALL-only. **Known residual, owned by T105 and NOT
to be folded into T104:** a bullet ladder (`261677`) whose bare-bachelor's arm clears now reads
`ineligible`.

**ONE golden re-baselined and it was pinning the bug** — `m0334`, where an escape on a *preferred*
PhD line was waiving a *required* master's. **F38's abstain-not-drop ruling is untouched** (m1063
pins a standalone waiver still abstaining); only its assumption about REACH moved, and
`rules.yaml`'s comment asserting document scope was corrected in the same change. Corpus 1,060 →
**1,064**; the `rules.yaml` pin was rewritten twice and the corpus pin once, each keyed on the
unique full old hash with the count asserted at **90** and one line changed.

**GATED: `make check` exit 0 on `c988383b`** — **10,625 passed**, 1 skipped, 4 xfailed, vitest
211/211, coverage **95.26%**, 11m28s on an idle machine. The same tree took **51m21s** under the
Dota-era load, which is the clearest measure of what that load was doing.

**Test-count delta, counted through a different path than the gate.** `main` collects 10,589,
`engine-batch` 10,630 — **+41**. Mine is **+9** (6 new test functions, 1 removed with the rename,
+4 corpus rows, verified by diffing `83c22796..c988383b`); the three prior batch commits are the
other **+32**. **That means the inherited figure is 4 low:** 2026-09-20f records `83c22796` at
10,612 passed, but working back from this measurement it was **10,616**. Small, but quote the
measured one.

**THE BATCH'S RE-KEY, WITH THE CONCRETE VALUES — owed at MERGE, not now.** Both keys have moved
off `main`, and D-528/D-530's whole point is that the batch pays for this **once**:

| | `main` | `engine-batch` |
|---|---|---|
| `engine_version` | `1+223421634827` | **`1+fcef17f526a3`** |
| `catalog.version` (drives `rules_hash`) | `f55a8b638aefdbdc…` | **`36d11ed322355a0b…`** |

So **every stored deterministic verdict is re-keyed on merge and a ledger drain is OWED** — see
`boardwatch ledger reopen --stale`. A drain reopens DISPOSITIONS, not verdicts, so it re-surfaces
already-built leads rather than changing any answer. **The confirm-clock restart is NOT a live cost
(D-351).** Do not merge without doing this, and do not do it before the batch is closed — T101,
T105, T92, `education_timing` and the Sonnet judge move would each re-key it again.

**`engine-batch` HAS NO CI.** `ci.yml` triggers `push` only on `branches: [main]`, so pushing a
branch fires nothing — the push bought off-machine backup, not a signal. **A `workflow_dispatch` is
the only CI this branch can get and the only way to see Windows, and it is OWED before merge.**

**The machine-load gate failure earlier in the session was environmental, and is recorded below
because it will recur.** It exited 2 at `web-test` before pytest ran. Three grounds it is environmental: the count varies (18, 6, 7 failures across runs);
it reproduces on `main`, whose tree is byte-identical to the last exit-0 gate (`git diff dcc594c7
21bb2403` empty); and the failures are `Test timed out in 5000ms`, not assertions. **Load average
13.23 on 10 cores, Dota 2 at 352% CPU.** Nothing was killed. Verified separately instead:
generalization OK, both indexes current, ruff, `mypy --strict` 365 files, and **1,668 eligibility
tests** including the 1,061-golden corpus. **THE GATE IS OWED ON AN IDLE MACHINE.**

**All three held items were RULED AND EXECUTED at session close.** `engine-batch` is pushed at
`c988383b`; the docs branch is **PR #401** with auto-merge armed; and **65 of 72 worktrees were
pruned** — every one clean AND fully merged into `origin/main`. **33 → 46 GiB free, 13 GB
reclaimed.** The seven kept are the primary checkout, `bw-engine` and `bw-docs20g` (both
unmerged), the three detached `bw-verify*`, and the dirty `bw-webaudit`. **Every branch survives**
(`t99`, `t122`, `astra05`, `close-2026-09-17` spot-checked), so any of them reverses with
`git worktree add`, and no `.git` lock was left behind. A `workflow_dispatch` was fired on the
final state — **run `35565660891`, IN FLIGHT at close.** **Read it by job NAME, never colour
(D-528's lesson), and confirm the Windows job actually RAN.** PR #400 merged as `21bb2403`; the
primary checkout is synced and still on `main`, so the 04:00 tick runs `main`.



### 2026-09-20f (moved whole)

### 2026-09-20f — **THE ENGINE BATCH IS OPEN ON AN UNMERGED BRANCH. `engine-batch` (worktree `bw-engine`) HOLDS T100, T102 AND T103, GATED exit 0 — 10,612 passed, 95.26%. IT IS DELIBERATELY NOT MERGED (D-530).**

**Read this before touching the engine.** Mit ruled on 2026-09-20e: build next action 4's batch,
**hold the merge until after the 04:00 tick** so the night runs the code the astra wave gated.
**The branch ACCUMULATES the batch** — landing three tickets now and the rest later costs ONE
`engine_version`/`rules_hash` re-key, not two. Continue ON `engine-batch`; do not open a second
branch, and do not merge until the batch is done. Its base `86d9b3e6` is in `origin/main`, so it
rebases cleanly. **The primary checkout stays on `main`** — the launchd driver runs its editable
venv, so a branch switch there changes what the tick executes.

**In: T100** (resolvers abstain on out-of-catalog choice values — the bug **inverts `unmet` to
`met`** on three of four fields), **T102** (`us_person_required`; stops calling refugee/asylee EAD
holders `unmet` on ITAR/EAR clauses they satisfy), **T103's unanimity half** (an all-`unmet` or
all-`met` exclusive group now decides instead of dissolving — Mit's 2026-09-19 ruling; it reads
`ineligible` on his own review-lane clearance holds). **T100 and T102 each move 0 of Mit's live
verdicts**; T103 is the live-moving one.

**T103's OTHER half — same-span subsumption — is REFUTED and NOT BUILT (D-530).** Its stated rule
("spans equal or nested") cannot reach its own case (real spans (0,38) vs (20,50), overlapping
but not nested); its headline example already resolves as same-`implies` corroboration; and
same-span mixed groups measure **0 across five profile shapes** over 8,000 postings, null-
controlled. **Do not re-raise it.** Corpus: 1,061 goldens pass, zero re-baselined.

**Still owed in the batch: T101, T105, T92, `education_timing`, the Sonnet judge move.**
**T104 is DONE (D-531).**
**`education_timing` ALREADY EXISTS as a family** in `rules.yaml` (`currently_enrolled`,
`graduation_yyyymm`) — re-read D-521 §8.5 against the catalog before building anything.


### 2026-09-19 (moved whole)

### 2026-09-19 — **THE EXPANSION IS MEASURED AND IT WORKS (run 467, D-522): 1,155 boards → 59,622 postings → 1,222 eligible → 28 of 40 DELIVERED LEADS, and B8's VOLUME half PASSES at 25. INDEED IS CONFIRMED DEAD. M5's 14th DAY TAKEN: run 447 is ATTENDED on the owner's explicit permission and B1–B7 PASS (D-521 §5). GATE 1's SECOND READING CLEARS ALL FOUR EMPLOYER-BOARD BARS, SO M4's LAST CONDITION IS DISCHARGED. THE DISCOVERY BACKLOG IS SIZED AT THREE DISJOINT GAPS AND STAGE 1 IS IMPORTED — FLEET 652 → 1,807.**

**The expansion half is DISCHARGED and was split out to `STANDING-FACTS.md` on 2026-09-20g** — run 447, M5 day 14, Gate 1's reading of record, the three discovery gaps, run 467's readout and the sizing rule. Held in **D-521** and **D-522**; run **468** is the second reading and supersedes its numbers (2026-09-20g block). **The two paragraphs below stayed because both are still UNRULED.**

**B8's VOLUME half had never been recorded and fails 9 of the 14 confirm days** (7/13/10/12/3/10/9
then 26/22/26/19/21/19 against ≥ 20). The acceptance-run table in `METRICS.md` reads
`_(not started)_`, which is why nobody saw it; the instrument was validated against two recorded
values before this was believed. Its precision half stays MET at 6.9%/5.6% (D-514). **Whether a
9-of-14 volume record blocks the REPLACEMENT decision is Mit's — `PROGRAM.md` §1's table includes
B8, M5's exit criterion does not.** **POST-EXPANSION READING 2 OF THE 5 D-529 ASKS FOR, TAKEN
2026-09-20g: run 468 = 22, MET.** So the post-expansion record is **25, 22 — two for two**, against
a 9-of-14 record that is entirely pre-expansion. **Verified three ways on run 468** — the funnel's
`pdf` stage (22), its own Leads table (`PDF: yes` = 22) and **22 `.pdf` files on disk**; and the 44
PDFs under `2026-09-19/` decompose as **25 (run 467) + 19 (run 447)**, which independently confirms
both of those recorded values too. Three more ticks and the condition is satisfiable either way.

**INDEED IS CONFIRMED DEAD** — a second consecutive silent refusal (HTTP 200, valid GraphQL,
`results: []`, identical 68-byte body across three probe shapes including unfaceted-and-unfiltered).
**Evasion is REFUSED** (D-368 precedent). **Accepting the loss is Mit's**: ~500 postings/day,
~75 new companies/day, **37.1% of Gate 1 recall**. Note run 467 met B8 *with Indeed dead*.

**Next action.**

0. **ASTRA IS DONE — all five slices consumed AND the remediation closed (D-528).** 33 of 51
   tickets shipped. What is left is listed in the astra pointer block above; **T100–T105 are item
   4's batch and nothing else is owed to the reviews.** Mit's standing answer on the seat
   (2026-09-19 18:40, re-confirmed 2026-09-20): fan out **2–3 executors at once, never more**;
   ask for the usage reading again before a fan-out on a later day. **The pattern is proven** —
   three executors, zero merge conflicts, each gated by the dispatching session.
1. **DISCHARGED on run 468 (2026-09-20g block, D-531).** The rate HELD exactly (2.04% stock,
   2.06% flow); the volume WAS a first-scan bulge (56,635 → 97 new postings, 584x); the slate
   share held at 62% but is **pure drawdown** — 25 of 25 new-board leads were first seen in run
   467, zero in run 468. **What replaces it: read run 469 the same way.** Two readings cannot
   tell decay from plateau, and the ~2 eligible/day replenishment against a ~25/day draw is what
   the stage-2/3 argument now turns on. Same method: cohort by `scan_kind='board'` in 467 not
   447, and confirm it still reproduces run 467's 28 of 40 before reading anything new.
2. **Rule on Indeed** (above). If accepted, size it as a dead lane rather than fixing it.
3. **Rule on B8.** Its volume half now PASSES at 25, but it failed 9 of the 14 confirm days and
   `PROGRAM.md` §1's replacement table includes it while M5's exit criterion does not. Does the
   record block the retirement decision? **The 25 itself is now VERIFIED sound** — D-524 measured
   the one defect that could have inflated it (`pdf.entered` is counted before the form sweep
   re-routes) and it moved zero leads on run 467, with a null control proving the probe. So this
   is a question about the 9-of-14 RECORD, not about the instrument.
4. **The batched engine landing — OPEN AND UNDER WAY ON `engine-batch`, three tickets in
   (T100, T102, T103), gated exit 0, NOT merged. See the 2026-09-20f block above and D-530
   before doing anything here.** Still owed: T101, T105, T92, `education_timing`, and
   the Sonnet judge move (D-477, D-514). **T104 IS DONE (D-531).** Mit ruled (c), the
   ownership-guarded adjacent reach, and it shipped at the WIDER scope — all eleven
   document-scoped escapes moved, chosen because adjALL is a strict superset of adj2 whose
   extra 108 moves are +91 `eligible` against +16 rejected over the complete 67,587-posting
   population. **What T104 does NOT cover: bullet ladders — that residual is T105's.** The rest of this item is the original framing and
   still stands — the Sonnet judge move, T92, **and
   `education_timing`** (D-521 §8.5: one nullable field, correctly rejects 7 unapplyable
   2027-start leads). **T108 (shipped, D-524) was its missing prerequisite**: until it landed,
   no component of the gate row key varied with `settings.gate.model`, so the move would have
   reached NEW leads only and left every standing verdict on the old judge. **THE RE-JUDGE HAS
   FIRED AND IS CLEAN — run 468, verified two ways (D-528). This condition is DISCHARGED; do not
   wait for it again.** `funnel-468.md` reads `120 candidates · 0 already current · 120 sent`,
   0 failed open / 0 missing / 0 refused, and the store shows run 468 = 120 rows `model='haiku'`
   against `model=NULL` on 434/447/467. **But note what it does NOT mean:** the SLATE was
   re-judged once; the stored corpus still holds **1,203 of 1,323** posting-versions on a stale
   key, and the judge clears at most `gate.depth` per tick. That backlog is T113's, re-sized.
5. **Stages 2-3 stay REFUSED for the density argument** (workday 0.17, smartrecruiters 0.08,
   oraclehcm **0.00** per 1k open) — but **D-527 REVERSES the refusal for ONE case**: a
   body-inlined board (ashby/greenhouse/lever/workable) that hiring.cafe resolved AND read is now
   auto-watched (T143). That is the inline-body population run 467's density win was measured on,
   and it is the only population the reversal covers. The **69** unwatched boards on
   workday/eightfold/oraclehcm/smartrecruiters are NOT reversed — they reach the fleet only
   through `companies unscanned` (T142) and the owner's `companies import`.
6. **GAP C IS NOW SIZED (2026-09-20g), which was the thing missing from the ruling.** Its 43
   `grnh.se` boards priced at the live greenhouse density — **84.1 open postings per board**,
   measured over the 608 watched greenhouse boards holding 51,149 open postings — come to
   **~3,617 open postings**, and at the new boards' measured 2.05% rate **~74 eligible**. The
   scan cost is negligible: greenhouse fetch latency is **1.08 s/board** on run 468, so 43 boards
   is **~46 seconds** added to a 1,807-board run. For scale, stage 1 was 1,155 boards → 59,622
   postings → 1,222 eligible, so Gap C is ~6% of that yield for 3.7% of the boards. **Still the
   owner's call, but it is no longer unpriced.**
7. **The 801 Domino's rows are RULED: LEAVE THEM (D-527).** Company 139 is already `watched=0`,
   so astra's actual ask was already the state; the rows are 0.31% of the open corpus and can
   never close (D-314). Do not re-raise it. **Still open and unruled:** import Gap C's 43
   `grnh.se` boards — now reachable, since `discover-grnh --limit 0` reads all 449 seeds where the
   default read 200 (T141); the `--include-non-swe` / `--include-zero-signal` drains are inert at
   production N.
8. **LinkedIn is the untouched backlog** — still ~423 companies refused by its cap every run,
   while hiringcafe's admissions fell 78 → 19 and jobapps' to 0 as Gap A was absorbed.

**T96 and T97 are MERGED** (union gated before push: exit 0, 10,274 passed). Both were held off
`main` until run 467 was read so the expansion was measured as one variable.

---

## Owner-gated items moved out of STATE on 2026-09-21 (verbatim) — all four say outright they are settled

0-B/0-C/0-D shipped (D-502/D-503); the <= 1-YoE floor is ruled, planned and executed (D-478/479/480);
0-1 was already marked RETIRED/ANSWERED; and the per-source thresholds are FULLY RULED (D-482, D-505)
with nothing owed. They sat in STATE's owner-gated section describing decisions nobody can still take.
**One live residual is kept in STATE rather than moved: 0-D's REPAIR half** (117 overwritten bodies,
301 lane-payload `raw_json` rows) was never part of the ruling and is still available if Mit wants it.

**0-B, 0-C and 0-D are ALL SHIPPED (2026-09-13, D-502/D-503) and are no longer owner-gated.** 0-D
shipped narrower than the ruling and the correction is in D-502; 0-D's REPAIR half (117 overwritten
bodies, 301 lane-payload `raw_json` rows) was not part of the ruling and remains available if Mit
wants it. **D-498's rule (b) IS BUILT and shipped under D-504** — `_suppress_lane_copies`
(`top_cmd.py:1062`) implements it; the previous "not ruled on and is not built" here was false
(D-521 §8.2). Rule (c) stays refused.

**0. THE ≤ 1-YoE FLOOR — RULED (D-478 §5), PLANNED (D-479), ALL DECISIONS TAKEN (D-480).** D1 = T47
(per-user policy data). D2 = floor first, then arm the judge, both before run 4. D3 = above-band
stays hidden, no ticket. Reach confirmed for 2–3 y total bars, scoped bars > 1 y and 13–36-month
bars; hedged/preferred bars do not move. Nothing here is still owner-gated; it is execution.

**0-1. RETIRED / ANSWERED — held WHOLE in `STANDING-FACTS.md`.** Gate 1 is PER-SOURCE RECALL (D-421)
and only the per-source THRESHOLD is still owed; job-apps keeps running until it is met
(`RETIREMENT-PLAN.md`); Indeed's posture is decided (D-410, re-scoped by D-450). **Do not
re-litigate 80%, do not re-derive "most", do not re-probe Indeed.**

1. **PER-SOURCE THRESHOLDS — FULLY RULED (D-482 structure, D-505 the last two).** Employer-board
   sources ≥ 85%; **LinkedIn, Indeed and hiring.cafe: NO BAR** — a reach lane's recall against
   job-apps' ledger measures its OVERLAP with the system it exists to go beyond, so a bar there
   would mean job-apps runs forever. **Nothing is owed here any more.** M4's exit is the
   employer-board half alone and all four already clear it (greenhouse 97.2 / ashby 100 /
   workday 96.6 / lever 100, D-499); the only condition left is D-482's SECOND reading a week
   after D-499, owed **~2026-09-19**.

## Changing `rules.yaml` — the full pin and corpus procedure (verified 2026-09-22)

**Written because three separate sessions have re-derived it.** Every path, line number and pin
value below was read off the file, not remembered. `make check` runs `generalization` FIRST, so a
stale pin fails before pytest ever starts.

**Two pins sit in the path of any catalog edit, in different files, moved by different means.**

1. **R7, the `rules.yaml` bytes.** `tools/generalization/allowlists.py`, the
   `src/boardwatch/eligibility/rules.yaml` entry's `pin="sha256:..."`. Checked by
   `check_inventory` (`tools/generalization/inventory.py:199-207`). **No tool regenerates it** —
   `fixture_refresh` does not touch `allowlists.py`. Compute `shasum -a 256` and hand-edit.
   **THE `sed` TRAP IS BIGGER THAN PREVIOUSLY RECORDED: that file now holds 90 `pin="sha256:`
   literals.** A shape-keyed `sed -E 's|pin="sha256:[0-9a-f]{64}"|...|'` rewrites **all 90** to one
   hash. Key the edit on the OLD value and assert `count == 1` before writing.
2. **R14, the corpus bytes plus an independent row count.** `tools/generalization/fixtures.py`:
   `CORPUS_PIN` (regenerated by `uv run python -m tools.fixture_refresh --record`) and
   `CORPUS_ROWS` (**deliberately NOT written by `--record`** — an earlier version let the tool
   write it and a truncated corpus went green on both; `--record` prints the measured count and
   stops). A human edits `CORPUS_ROWS`.

**A stale pin goes red in THREE places, so expect to see the same failure three times:**
`tests/generalization/test_real_tree.py` (`test_the_real_tree_is_clean` runs the checker over the
real repo inside pytest), `tests/generalization/test_fixtures.py` (asserts `_corpus_rows(repo) ==
CORPUS_ROWS` against the real tree), and the checker itself.

**Pins that LOOK relevant and are not:** `tests/unit/test_lane_body_precondition.py`'s
`catalog_fingerprint()` digests the foreign-body marker catalog in `lanes/quality.py`, not
`rules.yaml`; `tests/unit/jsonld_shape.py`'s `CATALOG_DIGEST` is the JSON-LD vendor catalog.
**No test anywhere pins `catalog.version` or `rules_hash` to a literal** —
`test_eligibility_catalog.py` only asserts `len(...) == 64` and `test_eligibility_hashing.py` only
asserts hex-ness.

**The corpus is a PYTHON TEST FILE, not data** — `tests/pipeline/test_eligibility_corpus.py`,
one flat `CASES` list of 6-tuples `(label, body_text, facts, policy, verdict, [[rule_id,
requiredness, disposition], ...])`, driven by `parametrize`, asserting its own length at the tail.
That is exactly why R7's data-suffix scope cannot see it and R14 exists. **The generator does NOT
exist** — the header still says "Regenerate with `scratchpad/gen_corpus.py`; do NOT hand-edit",
which is stale and self-refuting (a CAVEAT in the same docstring says the script is gone and the
oracle is gitignored). **Hand-editing IS the process**; six worked precedents are in the file
header — copy their shape: a header paragraph naming how many rows moved and why, and a corrected
*label* for any case whose stated claim the change contradicts. **Never `fixture_refresh --record`
your way through a corpus disagreement** — it re-pins from whatever is on disk and blesses the
regression. If you renumber, note `test_fixtures.py` truncates the corpus at a literal case-label
anchor and asserts the anchor still exists.

**Which hash moves.** `engine_version()` (`eligibility/engine.py:120-126`) is an AST digest over
`digested_modules()` = `catalog.py`, `detect.py`, `resolve.py`, `engine.py` — **`rules.yaml` is
NOT in it**. A YAML-only edit moves `catalog.version` (`catalog.py:757-765`, a sha256 over the
canonical parsed document — so indentation and key order do not matter but **pattern ORDER does**)
and therefore `rules_hash` (`hashing.py:104-107`). Declaring a profile FACT moves neither: it
moves `profile_hash` (`hashing.py:86-90`).

**Downstream obligations of a `rules_hash` move, in order.**
1. **Full re-evaluation at the next preflight** — every stored deterministic verdict is
   invalidated. Precedent: run 146 re-wrote 138,582 of 138,677 open postings in ~10 minutes.
2. **Every gate row written before the change goes dead, silently.** No error, no warning.
   **And per D-537 that does not merely fail to ADD a hold — it RELEASES leads the standing queue
   was already holding.** Land catalog PRs first, then judge, then apply.
3. **The drain is formally owed and then decided on measurement** — refused five times now
   (D-331, D-373, D-460, D-533, and D-388's catalog-only argument). Note a real contradiction in
   the record: D-388 says a catalog-only change owes no drain, but `pipeline/policy.py` passes
   `rules_hash` into `policy_version`, which digests it — so `ledger show --stale` WILL report.
   Decide it in writing; the two-arm probe scripts are kept under `.agent/2026-09-21/`.
4. **The 14-day confirm clock restarts.** Per D-351 item 2 this is not being chased.

**`exclusive_groups` vs `refinement_groups` — what an added ALTERNATION must check.** Both are
validated by `catalog.py:_groups()`, and a member appearing in both raises `CatalogError`.
`exclusive_groups` collects which `implies` values are present **document-wide** and rewrites both
rows to `UNKNOWN` on two different values — throwing away a decisive `unmet`. D-388/D-389 split
them: `exclusive_groups` keeps presence semantics for genuine mutual exclusions,
**`refinement_groups`** dissolves only on a real MET+UNMET straddle, and `experience_years`' three
members moved there. T103 later softened it again — a **unanimous** group is no longer a
contradiction. **Before widening a regex, read the family's group block and ask whether the wider
pattern can now fire on a document where a sibling with a DIFFERENT group member already fires.**
If it can, you have added a conflict, not recall. Not theoretical: T4's months patterns reused
their years twins' `implies`, inherited the refinement group, and deleted a genuine 7-year
rejection on 10 postings (D-468). And **`rule_id` is `family:pattern_id`, NOT `family:implies`** —
they coincide only for `experience_years`, and a measurement keyed on the wrong one reported
"identical" and was false.

**The generalization checker scans git-TRACKED files only** (`discovery._git_paths` runs
`git ls-files -z`, then reads the WORKING TREE). So an edit to a tracked file is seen with no
staging, but **a brand-new untracked file is invisible and `make check` can pass twice before CI
fails once the commit makes it tracked. `git add` new files before the gate run you intend to
trust.** R1-R4 scan every tracked text file including `rules.yaml` and `docs/program/` for home
paths, emails, phone numbers and personal profile URLs — use `example.com`, and **describe refused
strings rather than pasting them**. R15 turns the gate red on a calendar date and is drained with
`--extend`, never `--record`.

**Ordered checklist.** (1) Read the family's group block. (2) Capture the corpus baseline from the
CLEAN tree — `.agent/2026-08-31d-session/scripts/0831d-corpus-dump.py`, expect `golden mismatches:
0`; reproduce its construction, since a probe built through the wrong constructor reads `eligible`
for everything. (3) Record `engine_version()` and `catalog.version` before editing. (4) Edit the
regex. (5) Re-dump and diff — target zero verdict changes; **a zero diff is NOT sufficient**, two
measured do-not-ship patches were corpus-clean and still regressed, so pair it with two hand-written
sentences exercising the new alternation and its nearest false positive. (6) Hand-edit the corpus:
new rows plus **at least one CONTROL that must not move**, then the tail assertion and `CORPUS_ROWS`.
(7) `fixture_refresh --record` then `--check` (must print OK; if it quotes a hash you cannot grep,
clear `__pycache__` before suspecting anything else). (8) Update the R7 pin keyed on the old value
with a uniqueness assert. (9) `uv run python -m tools.generalization; echo exit=$?`. (10) Narrow
pytest with `--no-cov -n 0` over the eligibility modules, the corpus, `tests/generalization/`, and
**`tests/pipeline/test_ineligible_span_gate.py`** — not optional, it asserts every `ineligible`
corpus case carries a span slicing a non-empty quote out of the body. (11) **Revert the one-line
edit and confirm the new rows FAIL**, then restore. (12) If the pattern COUNT changed, grep the
tree for the old literal — known sites include the catalog pattern total and suppressor census,
the abstain report, the funnel artifact, the eligibility CLI's "N rules · N never fired" string,
and **`tests/unit/test_run_funnel.py`, which is NOT the `tests/pipeline/test_run_funnel_artifact.py`
beside it**. (13) `git add -A`. (14) `make check`, real exit code, one gate at a time, never piped
through `head`/`tail`. (15) Append the decision AND its index row, then `make reindex` and
`index-check`. (16) Decide the drain in writing.

## Moved out of STATE on 2026-09-22b — the 2026-09-22 rulings block, whole. Every one of its four
## rulings is now discharged: T149 SHIPPED (D-540), T150 SHIPPED, T92 SHIPPED (D-542), T101 REFUSED
## on measurement (D-544), T151 SHIPPED (D-543), T153 CORRECTED not built (D-545), T152/T105
## DESIGNED (D-546). Kept verbatim; nothing summarised away.

### 2026-09-22 — **§5 IS REFUTED AND WAS ALREADY FIXED (D-536). A CATALOG RE-KEY SILENTLY RELEASES 117 HELD LEADS INTO THE APPLY LANE (D-537). THE DEGREE-WAIVER GAP IS ENUMERATED AT 6,712 AND THE WIDENING IS RULED IN (D-538). FOUR TICKETS ARE RULED AND SPECCED (D-539).**

**Read `TICKETS-2026-09-22.md` before starting any of the four.** It holds implementation-ready
specs — verified paths, red-first cases reproducing on `main`, the measured regex verbatim, and
per-ticket "which hash does this re-key". The reusable catalog procedure moved to
`STANDING-FACTS.md` under **"Changing `rules.yaml`"**; three of the four need it. **Nothing was
built this session** — it was measurement and rulings only, and the tree is docs-only.

**§5 (comp band) is struck from the next-action list (D-536).** It was called "the cheapest real
fix in the file" on a premise that fails twice: the columns are populated on **0.83%** of open
postings and on **4 of 1,083** delivered leads with **ZERO above any ceiling**, and it is blind to
its own motivating posting (#170878 is NULL on all four comp columns; the figure is body text).
Re-specified over the body it has 92x the reach but is a **company pay-tier proxy** — 8.3% explicit
FPs at $200k including a *Graduate Software Engineer (2027 Start)* at a flat $200,000, and at
$250k **88% of what it fires on is at companies with zero entry-titled comp observations**.
**The class is ALREADY HELD:** the judge sees the whole JD and reads `seniority_fit = no` on
**25 of 29 (86%)** high-comp leads against **36%** in the control, routed to `_review` since
2026-09-14 — three days before the pre-flight that raised §5.

**THE LIVE ONE, AND IT IS NOT A BUG BUT A MEASURED COST OF A RULED FAIL-OPEN (D-537).** The
batch's `rules.yaml` change moved `rules_hash`, so **all 2,131 stored judge rows are dead** — their
hash is stable 09-06..09-21 and does not match the live identity. Dead readings do not merely fail
to ADD a hold; **they RELEASE leads the standing queue was already holding**, because both
gate-derived holds sit ABOVE the `eligible` short-circuit and the queue re-derives every lane on
every read. **NET 117 leads moved from `_review` into the apply lane** (floor; ceiling 350 — the
233 deterministic-`uncertain` ones were not computed). ~35 are Member of Technical Staff, the exact
class T109 exists for. **It does not self-heal** — a `built` disposition governs permanently, so
these never re-rank or re-judge. **Mit ruled: do NOT restore the holds, do NOT spend the
re-judge**, because the hold's own error floor is **38 of 339 (11.2%) explicit entry-level titles**
— Haiku false negatives against the target population. Triaged at zero cost into 16 look / 38 skip
/ 63 review. **Consequence: the Sonnet judge move is now JUSTIFIED, not merely owed** (D-477's bar
is "Sonnet unless Haiku holds >= 90%"; this is an 11.2% floor miss). **Spend the re-judge ONCE,
after it.**

**The degree-waiver gap is 6,712, not 3,762 (D-538), and all ten arms are RULED IN.** Enumerated
over 260,581 open postings with controls run before every counting pass — two fired and changed
the work — and cross-checked two ways. Ruled in **despite buying ~0 slate slots**, on the ground
that **D-532's unit rule governs how to SIZE new reach and does not license continuing to emit a
verdict already known to be wrong.** The HS/GED arm ships although inert for this profile, on
multi-tenancy; `or foreign equivalent` stays excluded; direction-blindness is pre-existing and not
widened.

## Moved out of STATE on 2026-09-22b — the 2026-09-19 expansion-measurement block, whole.
## Held in D-521 and D-522; every condition in it is discharged. Kept verbatim, nothing summarised.

### 2026-09-19 — **THE EXPANSION IS MEASURED AND IT WORKS (run 467, D-522): 1,155 boards → 59,622 postings → 1,222 eligible → 28 of 40 DELIVERED LEADS, and B8's VOLUME half PASSES at 25. INDEED IS CONFIRMED DEAD. M5's 14th DAY TAKEN: run 447 is ATTENDED on the owner's explicit permission and B1–B7 PASS (D-521 §5). GATE 1's SECOND READING CLEARS ALL FOUR EMPLOYER-BOARD BARS, SO M4's LAST CONDITION IS DISCHARGED. THE DISCOVERY BACKLOG IS SIZED AT THREE DISJOINT GAPS AND STAGE 1 IS IMPORTED — FLEET 652 → 1,807.**

**The expansion half is DISCHARGED and was split out to `STANDING-FACTS.md` on 2026-09-20g** — run 447, M5 day 14, Gate 1's reading of record, the three discovery gaps, run 467's readout and the sizing rule. Held in **D-521** and **D-522**; run **468** is the second reading and supersedes its numbers (2026-09-20g block). **The two paragraphs below stayed because both are still UNRULED.**

**B8's VOLUME half had never been recorded and fails 9 of the 14 confirm days** (7/13/10/12/3/10/9
then 26/22/26/19/21/19 against ≥ 20). The acceptance-run table in `METRICS.md` reads
`_(not started)_`, which is why nobody saw it; the instrument was validated against two recorded
values before this was believed. Its precision half stays MET at 6.9%/5.6% (D-514). **Whether a
9-of-14 volume record blocks the REPLACEMENT decision is Mit's — `PROGRAM.md` §1's table includes
B8, M5's exit criterion does not.** **POST-EXPANSION READING 2 OF THE 5 D-529 ASKS FOR, TAKEN
2026-09-20g: run 468 = 22, MET.** So the post-expansion record is **25, 22 — two for two**, against
a 9-of-14 record that is entirely pre-expansion. **Verified three ways on run 468** — the funnel's
`pdf` stage (22), its own Leads table (`PDF: yes` = 22) and **22 `.pdf` files on disk**; and the 44
PDFs under `2026-09-19/` decompose as **25 (run 467) + 19 (run 447)**, which independently confirms
both of those recorded values too. Three more ticks and the condition is satisfiable either way.

**INDEED IS CONFIRMED DEAD** — a second consecutive silent refusal (HTTP 200, valid GraphQL,
`results: []`, identical 68-byte body across three probe shapes including unfaceted-and-unfiltered).
**Evasion is REFUSED** (D-368 precedent). **Accepting the loss is Mit's**: ~500 postings/day,
~75 new companies/day, **37.1% of Gate 1 recall**. Note run 467 met B8 *with Indeed dead*.

**Next action.**

0. **FOUR TICKETS ARE RULED AND SPECCED — START FROM `TICKETS-2026-09-22.md`, NOT FROM THE
   ASTRA TICKET TEXT, WHICH IS STALE ON THREE OF THEM (D-539).** Every ticket there is standalone
   and ends in a **"Done when"** acceptance contract. Order: **T149** the degree escape, all ten
   arms, `rules.yaml` only, follow `STANDING-FACTS.md` "Changing `rules.yaml`"; **T150**
   `education_timing`, **ZERO lines**, two `facts set` commands, `profile_hash` only, and **not
   before run 470 is read**; **T92** re-scoped to a T91-style **review-lane hold** (~40-60 lines,
   moves NEITHER hash), not the engine change D-519 §3.5 already ruled against; **T101**'s closed
   `requires_cue` field (~45 lines, both hashes) — the cheap 2-line suppressor was probed green and
   REFUSED on fail-safety, kept as the fallback; then **T151** (staleness visible) and **T153** (the
   Sonnet judge move, now justified). **T152 and T105 are DESIGN-OWED — no code before the
   document.** T149 and T101 both touch `rules.yaml`: if both land in one session they share ONE
   re-key, one gate and one corpus pass. Still open and untouched: T113, T123, T124, T125,
   T127, T133, T135, T137, T139's stage extraction, T144, T138's two halves. Seat discipline:
   fan out **2-3 executors at once, never more**, and ask for the usage reading first.
1. **READ THE UNIT BEFORE SIZING ANY DISCOVERY WORK (D-532).** This replaces the old
   "read the next tick" item, which is discharged — 28 → 25 → 5 across runs 467/468/469 settles
   it. The live question is no longer whether boards yield; it is that **`capped_by_top_n` is
   10,533 against a 40-slot slate**, so eligible-posting counts do not convert. Anything proposed
   in "eligible added" must be restated in slate slots or refused.
2. **B8's PRECISION HALF IS STILL THE HIGHEST-VALUE AREA, BUT §5 IS NO LONGER THE ROUTE INTO IT
   (D-536).** §5 is struck: worth 0 slate slots as specified, blind to its own case, and the class
   is already held by T109 since 2026-09-14. **Do NOT re-ticket §5, and do not re-ticket §8** —
   both now carry the same disposition (already instrumented / already held). What the precision
   half actually needs is **the Sonnet judge move**, which D-537 moved from owed to justified by
   measuring an **11.2% floor error rate** on the live `haiku` gate against the new-grad
   population. The remaining unexamined classes in the pre-flight file are §1, §2 (the largest
   build — a scoring dimension), §3, §4, §6 and §7. **§10 is a permanent limitation; state it,
   do not chase it.**
3. **`--top` IS THE UNMEASURED LEVER AND IS NOT RULED.** Raising it converts buried postings into
   leads at unknown precision cost; B8's precision half is the instrument and it has never been
   read above n = 40/day. **Do not raise it without measuring leads 41–80 first.** Owner's call.
4. **THE D-537 RESIDUALS, DEFERRED BY MIT TO THE SESSION AFTER NEXT.** (a) **Stop keying a
   body-seniority reading on `rules_hash`** — a reading of a BODY is arguably not a function of the
   rules catalog, and the over-keying is what releases 117 held leads on every catalog change.
   **This is NOT D-380's fail-open direction, which STANDS**: D-380 governs what happens when a
   reading is absent, this governs what makes one absent. (b) **Make the staleness visible** —
   nothing counts standing leads whose stored reading went stale; `runner.py:3204` alerts on a
   different condition (absent from a judge RESPONSE). Any new soft alert sits **ABOVE
   `_emit_morning`** and must not go on `summary.errors` without re-reading D-529. (c) The
   standing-queue re-judge is **refused for now** and is spent ONCE, after the Sonnet move.
5. **Rule on Indeed** — deferred by Mit on 2026-09-21 to a later session. Second consecutive
   silent refusal; evasion refused (D-368). If accepted, size it as a dead lane rather than
   fixing it. Note run 467 met B8 with Indeed already dead.
6. **Stages 2–3 stay REFUSED and D-532 strengthens the refusal** (workday 0.17,
   smartrecruiters 0.08, oraclehcm **0.00** per 1k open). D-527's one reversal stands: a
   body-inlined board that hiring.cafe resolved AND read is auto-watched (T143). The **69**
   unwatched workday/eightfold/oraclehcm/smartrecruiters boards are NOT reversed.
7. **GAP C IS DONE (2026-09-21).** 449 seeds followed, 37 new boards found, all 37 probed live,
   **29 imported** and 8 dropped for carrying zero swe-titled openings. Fleet **1,842 → 1,871**.
   Measured at 1,319 open postings / 432 swe-titled / ~27 eligible — **not** the ~74 the
   extrapolation priced. The 801 Domino's rows stay (D-527); do not re-raise.
8. **LinkedIn is the untouched backlog** — ~423 companies refused by its cap every run. Size it
   in slate slots (D-532) before proposing work, not in companies reached.

## Moved out of STATE on 2026-09-22c — the 2026-09-22b and 2026-09-21 blocks, whole. Run 470 is read
## against the 2026-09-21 block's prediction (D-547), its last open condition. Kept verbatim.

### 2026-09-22b — **FOUR TICKETS SHIPPED IN ONE NIGHT AND THE HEADLINE IS A DEFECT NOBODY HAD TICKETED: THE DEGREE ESCAPE WAS ABSTAINING BARS THE PROFILE ALREADY MET, 5,579 ROWS OF IT (D-541). T149 ALONE WAS A NET −90 REGRESSION (D-540). T92 AND T151 SHIPPED (D-542, D-543). T101 IS REFUSED ON MEASUREMENT (D-544). T153's TWO RE-KEY CLAIMS ARE BOTH WRONG (D-545). T152/T105 DESIGNED (D-546).**

**Shipped and merged:** #407 (T149 + T154), #408 (T92), #409 (T151). **T150 declared live.**
Every gate exit 0, read from a sentinel: 10,643 / 10,656 / (T151) passed, coverage 95.26%.

**Read D-541 before touching `abstain_by_adjacent`.** Widening the degree escape (T149, ruled in by
D-538) turned out to be a **net −90 apply-lane regression on its own**: measured over the 6,964
open postings the new escape reaches and the old does not, it demoted **90** postings out of
`eligible` to rescue **3** from deletion. Cause was pre-existing and nobody had ticketed it —
`abstain_by_adjacent` applied at DETECT time, before resolution, so a waiver abstained a
requirement **the profile already satisfied**. A waiver RELAXES a bar; it cannot make a satisfied
bar undecidable. **5,579 of the 5,697 stored escape-abstained degree rows (97.9%) were discarding a
decisive `met`.** With the fix the same population reads **10 rescued, 0 demoted, 0 newly
ineligible** — and the rescues rose 3 → 10 because the bug was suppressing T149's own intended
rescues. Fixed as **T154** in the same commit, because T149 alone is a regression nobody should
bisect to. **D-531's owed measurement is also answered: the stage-1b job-deleting mode is 0 of
6,964**, and T154 removes the mechanism.

**T150 is live and its ticket was wrong by one.** `education_timing` declared
(`profile_hash` verified to move through the production helper, with a null control reproducing the
live persisted hash). Effect is **6 of the 7 named postings, not 7**: 110519 says *"graduating
between Fall 2026 and Summer 2027"* and the catalog **cannot read season names**, so it abstains
rather than guessing — a genuine gap sized at **457 of 260,581** open postings. Corpus-wide reach is
**7,869 rows**, not 7 leads; the ticket counted standing leads.

**T92's reach was 5× stale** (the ticket predated the 652 → 1,807 expansion): **10** leads were
reaching the blind-apply queue against the employer's own non-FullTime `employmentType`, not 2.

**T101 is REFUSED on measurement, both halves (D-544)** — the closed field would abstain **3,288
genuine requirements** to catch **~21**. **A JD carries its obligation STRUCTURALLY, not lexically**,
so Half A is **blocked on T105**. Half B sized at 49 rows and also not built.

**Next action: run 470 has still NOT been read.** The launchd job was booted out at 00:52 on the
owner's "postpone the run until all work is done" instruction and **restored at session close**, so
the 04:00 CDT tick fires on the final merged code. **All THREE hashes now move** (`rules_hash` +
`engine_version` from #407, `profile_hash` from T150), so the corpus re-judge is certain to fire and
D-532's 75–85 min prediction is readable; a ~56 min duration would mean the re-key did NOT fire, and
**that** is the finding. B8's volume half still owes its reading (`pdf.entered` vs bar 20).

### 2026-09-21 — **THE ENGINE BATCH IS MERGED. RUN 469 SETTLES THE EXPANSION QUESTION AND IT INVERTS THE PROGRAM'S PRIORITY: THE BINDING CONSTRAINT IS THE SLATE CAP, NOT DISCOVERY (D-532). THE DRAIN IS MEASURED AND REFUSED (D-533). B8'S 9-OF-14 RECORD IS SUPERSEDED, NOT BLOCKING (D-534). THE NIGHTLY'S NEW WINDOWS RED IS A REAL PRODUCT GAP AND IS FIXED (D-535).**

**Read D-532 before proposing ANY discovery work.** Run 469 is the third tick on 1,807 boards
and the cohort read (null control passes: 1,155 boards, reproduces run 467's 28 of 40) gives:
new-board leads **28 → 25 → 5**, while the eligible RATE holds at **2.04%** across all three.
The mechanism is displacement, not exhaustion — only **75 of the cohort's 1,213 eligible have
ever been drawn (6.2%)**, and `capped_by_top_n` is **10,533** postings that cleared EVERY filter
and lost only on rank against a **40**-slot slate. The `--top 40` plist comment already named the
cause: **the ranker is recency-dominated and rank-cut postings are BURIED, not queued.**

**Consequence, and it is the session's main finding: anything sized in "eligible postings added"
is sized in the WRONG UNIT.** Stages 2–3 stay refused and are better evidenced than before.
**Gap C re-priced from "~74 eligible" to ~0.2 leads/day and was IMPORTED anyway** (29 of 37 boards, fleet 1,842 → 1,871; the 8 with zero swe-titled openings dropped) — cheap enough that the correction did not change the call. Precision work on the delivered 40
now pays better than discovery that adds to a pool already 263× the daily slate. **This is NOT a
decision to raise `--top`** — that trades against B8's precision half and is unmeasured.

**The batch merged with T100, T102, T103 and T104**, gated exit 0 on the merge commit (10,625
passed, 95.26%) with the code tree byte-identical to the Windows-green dispatch. **No drain**
(D-533): a two-arm blast radius over all 1,318 live-disposition postings found **1,316 unchanged,
1 loosening (on a self-draining `seen` row), 0 that a drain would buy.** The re-key still
re-judges the corpus at the next preflight — that is where T104's +91 `eligible` are released.

**B8 (D-534): the 9-of-14 record is retired, not weighed.** All 14 days are on the 652-board
fleet. Post-expansion `pdf.entered` reads **25 / 22 / 26 on runs 467/468/469 — 3 of 3, mean 24.3
against a bar of 20.** And the batch's `rules_hash` move **restarts the 14-day confirm by
`PROGRAM.md` §1's own rule**, so a fresh window begins at this merge regardless. **B8's PRECISION
half is the live risk and is where the work is.**

**The nightly was red on a NEW Windows failure and it was a real product gap (D-535).** Not
T128's three — those read zero. `promotion` commits by `os.replace`-ing `CURRENT`; that is atomic
on POSIX but on Windows denies every concurrent open for the instant of the swap, so the
lock-free reader saw **neither** revision — the third outcome §6 clause 1 says cannot happen.
The reader now waits it out, bounded at 1s, `PermissionError` only. **Only a Windows dispatch can
confirm the race is gone and ONE green run is not enough.**

**PR #404 MERGED** (`a5cd9741`), and a Windows `workflow_dispatch` came back green on all three
`windows-latest` jobs. **That is ONE green run and D-535 says one is not enough** — read several
scheduled nightlies with `gh run list --branch main --json event,conclusion` filtered to
`event=="schedule"`; `--limit 1` shows the newest run of EITHER kind, which is how a red nightly
reads as green.

**STANDING, and it cost two sessions: a CONTENDED gate is a FALSE NEGATIVE.** Check `uptime` and
`ps -Ao pcpu,comm -r | head -3` BEFORE launching `make check`; above ~load 8 the vitest 5s
timeouts fail and **the count varies run to run, which is the tell**. The 09-21 session never got
a green local gate for this reason (2/11/13 vitest failures across three runs, all
`Test timed out in 5000ms`) while CI's `web-bundle` job — the uncontended reading, by design —
passed. This session's gate ran at load 2.7.


**PREDICTION FOR RUN 470, RECORDED SO IT CAN BE CHECKED.** The batch re-keys `rules_hash`, so
the next preflight re-judges the whole stored corpus rather than the day's new postings. D-460
timed a full re-key at 151,626 postings in ~13 min; the corpus is now ~261k, so expect **~20-25
min added** to a run that took 56 min — call it **75-85 min**, plus the 29 Gap C boards. That is
well inside the heartbeat's 1-day period plus 2h grace. **If run 470 comes in near 56 min, the
re-key did NOT fire and that is the thing to investigate**, not the duration. Also expect the
confirm clock to restart here (D-534) and B8's volume half to be read fresh from this run.

**The 2026-09-17 autoapply pre-flight findings are now tracked and re-measured.** Its "single
largest fixable category" re-sizes: all five named dead postings have since CLOSED (2–4 days
later), so §8 is **closure LATENCY, not blindness**, and it is already instrumented by T117/T126
— do not re-ticket it. Population: 114 of 8,495 open+eligible carry `consecutive_missing ≥ 1`;
closure latency is mean **8.33 days**. **§5 (comp band as a seniority input) is the cheapest real
fix in the file** — `salary_min`/`salary_max` are already columns and the band gate already
exists; it is missing an input, not a subsystem.

## Moved out of STATE on 2026-09-22e — the 2026-09-22d block, whole. Its one open condition (run
## 471's `refresh_*` reading) is restated in STATE's 2026-09-22e block. Kept verbatim.

### 2026-09-22d — **T159 READ: THE SONNET-ERA APPLY LANE IS 5.4% UNAPPLYABLE, SO B8's PRECISION HALF IS MET ON IT (D-550). T113 SHIPS AS A BOUNDED STANDING-QUEUE REFRESH, ARMED LIVE AT 130/RUN (D-551, D-552). T127 AND T158 SHIP. RUN 471 HAD NOT HAPPENED — IT IS STILL THE NEXT READING.**

**The session ran on the afternoon of 2026-09-22, BEFORE the 04:00 CDT tick.** Run 471, D-529's
n ≥ 5 revisit and B8's day 1 are all still owed, exactly as the 2026-09-22c block below states
them.

**T159 (D-550).** Two blind opus passes (the owner's ruling) over 134 items, with 95.5% agreement
on a 44-item overlap. The apply lane (529) reads **3/56 = 5.4% unapplyable (CI 2–15%)** against
the ≤ 16% bar; the haiku-era control on 09-13 was 21.4%. Sonnet's extra clears (the 150 leads
haiku would have held) read 7.8%. **Sonnet's seniority hold parks ~53% applyable leads** (the held
arm reads 46.7% unapplyable, ~109 of 204). It still pays for itself, because releasing all 204
would take the lane to ~16.9%. **Whether to refine it is the owner's call; nothing is built.**
The misses name two small tickets:
- **T160.** `classify_location` fails open on ISO-3 suffixes (`Dublin, IRL`): 777 open postings.
- **T105.** The one eligibility miss is an extraction gap under a "Desired Qualifications"
  heading, which is T105's shape.

**T113 (D-551).** `[gate] refresh_budget` re-judges up to that many stale standing-queue leads
per run, through `run_gate_stage` itself, one batch per commit, promotable holds first. The
funnel's `gate` block reports `refresh_*`. The shipped default is 0 (off). **The live config is
ARMED at 130/run on the owner's ruling (D-552).** Read back through `Settings`, not from the file.
That costs ~5–7% of the seat per run while a backlog exists, drains a full re-key in ~7 runs, and
costs ~0 in steady state. The standing queue was 0 of 833 stale when it was armed, so run 471
should read `refresh_candidates = 0`. The original T113 half is
split out as **T113b**: 66 stale negatives that `top_cmd` hides, which the batch's `rules_hash`
move frees anyway.

**NEXT WORK, IN ORDER** (`TICKETS-2026-09-22c.md`, with its 2026-09-22d status section):
0. **Read run 471** as the 2026-09-22c block below specifies, then **raise D-529 (n ≥ 5).**
1. **Check run 471's funnel `gate.refresh_*`**: budget 130, candidates 0 (D-552). A non-zero
   candidate count on a run with no re-key is a defect to read, not a backlog.
2. **The eligibility batch** (T152 + T156 + T157 + T105), now unblocked. The refresh heals its
   re-key over ~7 runs; watch `refresh_pending_after` fall run over run.
3. **T155** (owner question first), **T160**, and T113b only if a model/effort/facts change
   recreates the backlog.
4. **Parked, unchanged:** `TICKETS-2026-09-22c.md` §#5.

## Moved out of STATE on 2026-09-23b — the 2026-09-23, 2026-09-22f and 2026-09-22c blocks, whole.
## Run 471 is read (D-572) and the pull to `de7ae153` is done, which discharges every step in the
## 22c and 22f blocks; the 2026-09-23 block's run-472 step is restated in STATE's 2026-09-23b block.
## Kept verbatim.

### 2026-09-23 — **ALL SIX TICKETS SHIP IN ORDER, ONE SQUASH EACH (D-562): T144 #420, T133 #422, T137 #423, T138 #424, T139 #425, T125 #421. EVERY ASTRA-REVIEW TICKET IS NOW CLOSED. RUNS 471 AND 472 HAVE NOT BEEN READ; THE PRIMARY CHECKOUT IS STILL HELD ON `ccb52912`.**

The session ran 23:04–~02:30 CDT, before the 04:00 tick, on the enterprise seat. The owner was
away, and executors ran as in-session subagents. `make check` on the final combined tree (exactly
`main` after the six merges): EXIT=0, 10,898 passed, 1 skipped, 4 xfailed, vitest 220 (D-562).

**Next session: the owner decides the direction; nothing buildable is unblocked.** Do first:
1. **Read run 471** as the 2026-09-22e block says, then `git -C boardwatch merge --ff-only
   de7ae153` ONLY (D-557). **Read run 472** as the batch's re-key run (lane 529 → ~206, healing at
   130/run). Only then fast-forward to `origin/main`, so **run 473** is the first to run the six
   fixes.
2. **Watch runs 472–474.** B8's volume window restarts at 472 and must hold 14 days on the
   1,807-board fleet. From run 473, read the funnel's new `identity_drift` (`[]` expected) and
   `provenance` keys.

**Open tickets** (`TICKETS-2026-09-22c.md`, §2026-09-23):
- **T161: the owner's read is owed** (`DESIGN-T161-gate-verdict-identity.md`, which recommends BOTH
  halves). **T163 follows it**: it edits `detect.py`, a digested module, so it re-keys.
- T162 parked (D-557); T113b only if a stale-`ineligible` backlog recurs.
- **New, ticketed, not built (D-565):** T164 (T137's drift report fires once, falsely, after a
  taxonomy bump); T165 (`verify`'s missing-PDF e2e test always skips); T166 (`doctor`'s reap
  takes no lease).

**Owner calls on the table:** T161; D-550's leftover (about 53% of Sonnet's seniority holds read
applyable to Opus); switching job-apps off (size it first: 2,877 of its postings resolved on run
470); the résumé calls; `ServiceNow Developer` ranking; the 17 never-listable boards; the
projection spec's §12; the optional 0-D repair. **Roadmap:** M1–M3 are done and B8's precision
half is MET (5.4%, D-550). Its volume half is the live bar. M4's recall work is deprioritized
(D-532), because the 40-slot slate binds and recall does not. `ROADMAP.md` is not rewritten until a
milestone closes.

### 2026-09-22f — **T135 SHIPS (#418 → `04f9ba6d`, D-559). T144 AND T133 ARE BUILT AND REVIEWED ON A STACK, NOT MERGED; T125 (ANNOTATE) IS BUILT, UNREVIEWED. T123 AND T124 CLOSE ON MEASUREMENT (D-558). RUN 471 HAS NOT FIRED; THE PRIMARY CHECKOUT IS STILL HELD ON `ccb52912`.**

The session ran 21:10–22:25 CDT on 09-22, before the 04:00 tick. The owner checkpointed at 21:58
("don't fire anything new"), and every in-flight task finished before this was written.

**Next session, in order** (exact commands: `.agent/2026-09-22f-session/CHECKPOINT.md`):
1. **Read run 471** exactly as the 2026-09-22e block below says.
2. **Pull ONLY to `de7ae153`** (`git -C boardwatch merge --ff-only de7ae153`), NOT to `main`. `main`
   now also carries T135, and the owner ruled that shipped fixes reach the live run at **473**, so 472
   stays a clean read of the batch's re-key (D-557). Pull to `main` only after 472 is read.
3. **DONE 2026-09-23 (D-562):** the stack and T125 shipped, and T137 → T138 → T139 were built,
   reviewed and shipped after them. See the 2026-09-23 block above.
5. **Owner reads owed:** `DESIGN-T161-gate-verdict-identity.md`, which recommends BOTH halves.
   **T163 must follow T161**: it edits `detect.py`, a digested module, so it re-keys and would dip
   the lane again.

**Ruled this session (D-557):**
- The seat is under 30%, so executors run one at a time. **The planning session IS the enterprise
  seat**, and it shares that budget with its executors.
- T161 stays in its slot.
- T162 is parked until a switch of judge model or effort is planned.
- T125 is annotate-only.
- T138's reverse half is refused.

**Closed on measurement (D-558):**
- **T124:** 409 of 409 multi-posting jobs are justified and 0 have diverged (null-controlled).
- **T123:** in runs 468–470, 1 of 110 partial board scans was detail-only. The 16,869 postings on
  boards that never complete are **inventory-truncated** on 4 boards: Lowe's 150-page cap, the
  Abbott and Genpt 2,000 censor, and Oracle `eeho` at 2,199 of 2,218. That is a coverage question,
  not T123's.

**T161 measured** (its design note):
- Of the 970 standing leads, the live identity reads 833 gate verdicts (750 / 44 / 39). The
  post-batch identity reads **0**. T161's judge-input key reads the same 833.
- The freshness read is ALSO identity-scoped. A lane-only T161 therefore ends the dip but not the
  re-judge spend.

### 2026-09-22c — **RUN 470 READ: THE RE-KEY FIRED AS PREDICTED AND B8's VOLUME SITS ON THE BAR AT 20 (D-547). A RE-KEY ALSO DEMOTES — 237 LEADS 0-B HAD PROMOTED FELL OUT OF THE APPLY LANE, WHICH D-537 NEVER MEASURED. T153 EXECUTED ON THE OWNER'S RULING: THE JUDGE IS `sonnet`, THE STANDING QUEUE WAS RE-JUDGED ONCE (833 of 833) AND ITS APPLY LANE READS 529 (D-548). `gate.effort` SHIPS.**

**Run 470 (D-547).** 85m34s against 75–85. The re-key is verified in the store, not inferred from
the duration: **269,702** evaluations under the new identity (run 469: 1,524); the re-judge cost
+20.2 min, as predicted. The 34 s overshoot is a cost nobody budgeted: **a re-key also empties the
gate's cache** (0 cached vs 66; +8.0 min). **B8 volume: 20 against a bar of 20** — 25/22/26/20
post-expansion; D-529 is at n = 4 of 5.

**Read D-547 before predicting what any re-key costs the queue.** Dead gate rows cut BOTH ways:
D-537 counted the holds they release (101); they also kill every judge `eligible` that 0-B's
promotion needs, so **237** leads fell back to `no_requirements_found`/`experience_requirement`
(net **−136**, null-controlled 987 of 987). It started at the engine-batch merge and never
self-heals, because a `built` lead is never re-judged by the daily gate.

**The repair, ruled by the owner and done (D-548).** Live `config.toml` gate model `haiku` →
`sonnet`; the 833-lead standing queue re-judged once through the production `run_gate_stage` at
`--effort medium`, paced in owner-checked batches (seat 5% → 8% over the first 78 leads). **Apply
lane 283 → 529** (412 had the haiku readings survived); `no_requirements_found` 345 → 12. Sonnet
clears **25 of the 33** entry-titled leads haiku had called senior. **Sonnet's apply-lane
PRECISION is unmeasured — 529 is volume** — and Sonnet was the audit's independent arm, so the
next blind audit needs Opus.

**`gate.effort` ships** (`None` = the calibrated argv, no flag). The live config carries
`[gate] effort = "medium"`; `Settings` ignored it until the code merged, so it is verified by reading
it back AFTER the merge, never by the file. Known gap **T155**: effort is not in the gate's
freshness key, so a later change of level re-judges nothing already judged.

**Next reading: run 471**, day 1 of B8's fresh 14-day window (T153 is a change to eligibility under
`PROGRAM.md` §1). Read its `gate` block: the first daily gate on Sonnet, and the first whose
standing queue is fully current.

**NEXT WORK: superseded by the 2026-09-22e block above.** #1 (T159), #2 (T113) and the T127/T158
cleanups are done. `TICKETS-2026-09-22c.md` §0 still lists what is already measured: read it
before any probe.

## Sessions 2026-09-22e and 2026-09-23b, moved WHOLE out of `STATE.md` on 2026-09-24

Moved at the 2026-09-23c/24 close because every step in them is done (D-580, D-588). Nothing is deleted; the run-472/473 predictions they carry are answered in D-580 and D-584.

### 2026-09-22e — **THE ELIGIBILITY BATCH SHIPS AS ONE ENGINE BUMP (T105 + T156 + T157 + T152, T155 FOLDED IN; D-555): 2,771 OPEN VERDICTS MOVE, NET −2,199 `ineligible`. T160 SHIPS (D-553). D-529 IS RULED AND SHIPS (D-554). THE PRIMARY CHECKOUT IS HELD ON `ccb52912` FOR RUN 471.**

**Merged:** #414 (T160) → `609c099a`, #415 (the batch) → `8b46706f`, #416 (D-529) → `6146a41c`. Every
gate EXIT=0 was read from a sentinel: T160 10,712 passed; the batch 10,807 passed at 95.27%; D-529 on the
batch 10,807 passed.

**The primary checkout was deliberately NOT pulled** (owner's ruling). Run 471 (04:00 CDT 09-23)
runs on `ccb52912`, so it is a clean read of the T113 refresh with no re-key, and D-529's fifth
reading comes from the pre-merge code. **Next session, in order:**
1. **Read run 471 as the 2026-09-22c block below specifies.** Expect `gate.refresh_*` =
   130/0/0/0 (D-552). A non-zero candidate count with no re-key is a DEFECT.
2. **Then pull, but ONLY to `de7ae153` (#417), never to a later `main`** (the 2026-09-22f block,
   D-557). Run 472 becomes the batch's re-key run:
   - the corpus re-judge costs about +20 min and the gate cache re-send about +8 min, once;
   - B8's 14-day window restarts at 472.
3. **Watch runs 472–474.** The standing apply lane dips **529 → ~206** (D-556), then heals at
   130/run, promotable leads first. `refresh_pending_after` should fall run over run.

**What moved (D-555, measured).**
- 2,127 `ineligible` → `uncertain` and 240 → `eligible`. The big term is a years bar under a
  hedge heading; `Preferred Qualifications:` alone accounts for 1,047.
- 168 `uncertain` → `ineligible`, **correct**: a preferred-section straddle had masked a genuine
  basic bar.
- 111 `eligible` → `uncertain`: a met row under a hedge heading no longer counts.
- T152 keeps all 833 standing seniority readings through the re-key. **The drain is refused** a
  seventh time.

**Review discipline changed (owner, 2026-09-22e).** Codex ran 3 rounds on T160 and 5 on the batch.
The owner has now set a budget: **1 review + 1 verification**, and a third round only for a
genuine, reachable blocker. The model is `gpt-6-sol` (Codex CLI ≥ 0.156.0), with effort
`low`/`medium`/`high` only. Global CLAUDE.md "Codex reviews" holds the rule.

**NEXT WORK: superseded by the 2026-09-22f block above.** Wave A closed as T135 shipped, T144 built,
T123 and T124 closed on measurement (D-558); T125 was measured and rebuilt as an annotation.

### 2026-09-23b — **THE STACK FINISHED MERGING (D-568) AND SEVEN MORE TICKETS SHIPPED: T165 #427, T166 #428, T164 #429, T161 #430, T163 #431, T169 #432, T168 #433 (D-569 … D-571). RUN 471 IS READ: B8 VOLUME 20, ON THE BAR (D-572). THE PRIMARY CHECKOUT IS ON `de7ae153`. T170 IS MEASURED AND AWAITS A RULING; T172 IS BUILT AND HELD (D-573).**

The session ran 01:47 to ~07:50 CDT on 09-23, on the enterprise seat; the owner was asleep for most of
it and ruled up front (D-566).

**Next session, in order:**
1. **Read run 472 (04:00 on 09-24) as the eligibility batch's re-key run**, exactly as the 2026-09-22e
   block below predicts: the standing apply lane dips 529 → ~206 and heals at 130/run, and
   `refresh_pending_after` falls run over run; the corpus re-judge costs ~+20 min and the gate cache
   re-send ~+8 min. Identify the run by `boards_attempted > 0`; read the store with Python
   `sqlite3` `?mode=ro` only. **Run no local `make check`, mutation campaign or heavy probe between
   04:00 and the run's end** (D-572: this session's gates slowed run 471's scan several-fold).
2. **Only after 472 is read and its process has exited: `git -C boardwatch merge --ff-only
   origin/main`.** Run 473 is then the first on T161, T163, T164, T166, T168 and T169. It re-keys
   `engine_version` (T163, T169) and is **T161's live proof**: `readings_absent` 0, and the standing
   apply lane returns to about its pre-472 level AT ONCE (T161 reads the D-548 verdicts again) with no
   dip across 473's own re-key. **The refresh keeps re-judging at 130/run anyway, and that is correct:**
   none of the 947 stored `sonnet` gate rows records an effort (all predate T155's field, measured
   read-only 2026-09-23), and T155 treats a missing level as a different one. Expect
   `refresh_pending_after` to fall by ~130 a run, and the daily gate to re-send its slate (low `cached`)
   until that drains. Also read the funnel's `identity_drift` (`[]` expected) and `provenance` (the
   checkout's commit), both from T137.
3. **B8's volume window:** 471 read 20. 472 and 473 each re-key, so the 14-day count restarts; its
   day 1 is run 473.
4. **Owner calls** (Owner-gated, below): T170's ruling, which rides 473's re-key only if it merges
   before step 2; T172's merge; T171 only if the queue list's latency matters.

**Measured this session (D-567, D-572):**
- **job-apps' daily discovery IS processed daily**: every passing record from 09-02 … 09-21 is in the
  store, `_eligibility_review` included (D-486/488/509 superseded D-423's one-off harvest).
- **Run 471's refresh read 130 / 3 / 3 / 0**, not the 130 / 0 / 0 / 0 expected, and legitimately:
  two bodies revised by the run itself and one legacy lead whose gate rows name no judge.

**Machine change (T167, owner's ruling):** the job-apps link refresher runs once, at 03:45, before the
04:00 run. The plist backup is `com.boardwatch.jobapps-links.plist.bak-20260923-pre0345`.

**Open tickets** (`TICKETS-2026-09-22c.md` §2026-09-23b): T170 (ruling owed), T172 (merge held),
T171, T162 (parked), T113b (only if a stale-`ineligible` backlog recurs; T161 narrowed it to effort
changes).

## Settled session block moved out of STATE on 2026-09-24d (verbatim)

### 2026-09-24c — **THE "NO WAITING" SPRINT DAY (D-594): EIGHT OWNER RULINGS ANSWERED, TWELVE TICKETS BUILT AND REVIEWED ON THE SEAT, TWO SHIPPED BY THE CONTEXT CLEAR (T195 #459, BUNDLE B T205–T207 #460), SIX IN THE SEQUENTIAL SHIP CHAIN (T199, BUNDLE A T203–T204, T210, T209, T188, T208), ENGINE BATCH 4 IN ROUND 2, T173 REBASED AND MEASURED, BATCH 5 WRITTEN. WAVE GATING RULED. THE PRIMARY IS ON `main` AT #460.**

**The unattended state at the clear — chain, executors, gates, repair steps — is in
`.agent/2026-09-23c-session/HANDOFF.md`. Read it FIRST, then `notes.md`'s tail. Then verify against `gh pr list`,
`git log origin/main`, and the `<tag>.exit` sentinels: the chain and two executors kept running after this file was
written, so this block is already behind by the time it is read.**

**Next session, in order:**
1. **Read the chain** (`ship-chain.log`): what merged, whether it STOPPED (a CONFLICTING PR = the changelog collision:
   close it, re-run the chain from that tag). Pull the primary ff-only between runs after the last merge.
2. **Batch 4 round 2** (`bw-batch4`): read RESULT "## Round 2" and `batch4_aggregate_v2.txt` — the seven wrong clears
   must now read `ineligible`; Codex verification (medium); fill the placeholders in `entry/pr/sq-batch4`; **T173**
   (`bw-t173`): read its rebase-and-remeasure record, Codex review, rebase once more onto batch 4's round-2 head
   (`T173d`), write its ship texts; gate both as ONE wave-3 stack; ship batch 4 then T173. Then launch **batch 5**
   (`TB5.md`, base = T173's head).
3. **0-D repair** once T210 is on main and the primary pulled: HANDOFF §4 (backup, report-only, `--apply`, verify by
   the raw_json count). A live-store write — between runs only.
4. **Run 476** (04:00 CDT 09-25): re-keys on the new engine_version; `refresh_pending_after` from 767; T198's
   prediction (the four Workday boards complete on their second scan); hiring.cafe's recount now attributed by row.
5. Prune merged worktrees (HANDOFF §5); a final close commit for STATE once the chain and wave 3 land.

**Owner calls answered today (D-594):** T173 yes; T188 all three; refresh backlog → T195 (shipped); career_field →
taxonomy (T208); 0-D → repair now (T210); résumé (1)(2) dropped, (3) later. **Nothing is owner-gated now except**
the standing items below (0-D's repair is authorised; the résumé formatting session is Mit's to schedule).

**Open tickets** (`TICKETS-2026-09-22c.md` §2026-09-23c): in the chain T199, T203, T204, T208, T209, T210, T188;
in flight batch 4 (T200–T202 round 2), T173; written T211–T213 (batch 5), T214; T198 waits for run 476.

## Settled session block moved out of STATE on 2026-09-25a (verbatim)

### 2026-09-24e — **WAVE 3a SHIPPED (T218 #474, T226 #475, BUNDLE C #476, ENGINE BATCH 4 #477); THE PRIMARY IS ON `c45dc0e2`. WAVE 3b (T228, T227, T220, T229, T173, BATCH 5) GATED RED AT CLOSE — ONE TEST, A T173 RE-BASELINE — AND NOTHING OF IT SHIPPED; BATCH 6 IS WAVE 3c (ITS CODEX BLOCKER IS TB6b'S). MAIN'S macOS RED WAS A PRODUCT RACE (T228). THE GATE'S SLOWNESS WAS PURE-PYTHON YAML (T229). D-596.**

**Verify first** (the session paused on seat usage with unattended work): `gh pr list --state all --limit 12`,
`.agent/2026-09-23c-session/arm-wave3b.status`, `chain-wave3b.log`, `gate-wave3b.log`, then
`.agent/2026-09-23c-session/RESUME-2026-09-24e.md` (every item's branch, base and next step).

**Next, in order:**
1. **Fix wave 3b's one red and ship it.** The gate (`gate-wave3b.log`, 22:46, **1 failed / 11,898 passed in 5m03** — the
   first full gate with T229: 327 s against 945 s) fails
   `test_recall_citizenship_clearance_domain.py::test_experience_non_requirement_fires_nothing["5+ years of DevOps experience
   is preferred but not required."]`: T173's carrier (D-590) now writes `scoped_years_preferred` for it (reproduced on
   `exec-t173` alone). That is the ruled design, so the fix is T173's re-baseline: move the case out of
   `EXPERIENCE_NON_REQUIREMENTS` into an assertion that it writes ONLY `scoped_years_preferred` (preferred, never required),
   as a commit on `exec-t173`; rebuild the stack (RESUME file), ONE `make check`, then `arm_wave3b.sh`'s chain (t228, t227,
   t220, t173, batch5, t229 last). T229 may fail to MERGE (the `gh` token has no `workflow` scope; it edits `ci.yml`):
   `gh auth refresh -s workflow`, then re-run `ship_one.sh t229 …` with ABSOLUTE paths. Add
   `tests/pipeline/test_recall_*.py` to every engine executor's narrow suite.
2. **TB6b** (`.agent/2026-09-23c-session/TB6b.md`, base `83b9d6ef`): batch 6 rebased onto batch 5, the T214a object
   restriction, re-measure by scan closure; Codex verification; ship.
3. **Run 476** (04:00 CDT 09-25, on `c45dc0e2`): long by design — T208's facts key and batch 4's re-key together. Read
   with `read_run.py 476`; D-595's run-476 predictions (T198's four Workday boards, hiring.cafe by row, GitHub lists).
4. The speed tickets T230–T232, then the engine follow-ups T233–T238 (TICKETS §2026-09-24e).

**Owner questions (D-596, they change what the gate checks):** Python 3.13 only on PR CI (3.11/3.12 on push); one PR per
wave instead of per ticket; no local coverage (CI keeps the 85% bar).

**Correction to 2026-09-24d:** main's macOS red is 17 of 24 pushes since T192, not "4 of 5 since T209" (T228). Of the
24d block's steps, 1 and 2 are done except batch 6; 3 and 4 remain.

## Settled session blocks moved out of STATE on 2026-09-25b (verbatim)

*Moved because every step they listed is done, ruled or restated in the 2026-09-25b block: the 09-26 run read is restated there; engine batch 11 is parked by D-598; T248 shipped #497; T239/T240 parked (D-598). The 24d block's steps (wave 3, run 476, D-596) are all done (D-596, D-597).*

### 2026-09-25a — **WAVE 3b SHIPPED (T228 #479, T227 #480, T220 #481, T173 #482, BATCH 5 #483, T229 #484), THEN ENGINE BATCHES 6–10 (#485, #490, #491, #492, #494), T232 #486, T231 #487, T230 #488, T238 #489, T243 #493. PR CI 21–38 MIN → 6.4 MIN; THE LOCAL GATE ~2.5 MIN. RUNS 476 AND 477 EACH RE-KEYED ONCE. RUN 477's JUDGE WAS STARVED BY THIS SESSION'S OWN SEAT (T247). D-597.**

**Verify first:** `gh pr list --state all --limit 20`, `git log --oneline -18 origin/main`, the primary on `main` (pulled
between runs), `.agent/2026-09-23c-session/RESUME-2026-09-25a.md`. The next run is the 04:00 tick on 09-26; batch 10 moved
`engine_version`, so it re-evaluates once more.

**Owner calls pending (they change live behaviour — ask, do not decide):**
1. **T247 — the gate judge runs on the session's seat** (`CLAUDE_CONFIG_DIR=~/.claude-boardwatch` in the plist). A heavy
   session starved run 477's judge (judged 0; fail-open held). Options: keep session work off the seat in a run's window
   (the planner's default until ruled), move the judge to another config dir, or accept; plus a whole-run judge-outage alert.
2. **`board_deadline_seconds` 600 → 1800** in the live config (T243's recommendation; drains the Workday boards in 1–3 runs).
3. **A posting whose ONLY qualifications section is `Desired/Preferred X and Y`** now reads every bar in it as a preference
   (T219/T246, ~200 postings, the JD's own words). Keep, or require at least one required section before carrying?

**Next, in order:**
1. **Read the 09-26 04:00 run** (batch 10's re-key) with `read_run.py <id>` (`.agent/2026-09-23b-session`): the judge must be
   back (judged > 0, `failed_open_batches` 0); the Workday boards (db, hitachi, vfc, mtb, aecom2, dxc, Airbus) should now
   return `partial` and grow each scan (T243); no drain is owed (0 `skipped` dispositions) — re-check.
2. **Engine batch 11** from T244, T249, T242, T241c (the follow-ups the batches ruled): one executor, the same brief pattern
   (`TB10.md`), a two-arm over ALL pinned postings when heading/splitter logic moves, Codex round + verification only.
3. **T248** (T243's other providers: OracleHCM, Eightfold, Phenom, Apple; dominos; a cap-failed board's lost counts), **T240**,
   **T239**.

**Rulings this session (D-597):** Mit 22:53 09-24 — all three D-596 owner questions NO for now (3.11/3.12/3.13 on every PR,
one PR per ticket, coverage in the local gate); Mit 00:31 — the run clock moves to fit the work (prepone = `launchctl
kickstart`; postpone = `disable`, kick, `enable`). Planner: batch 6 and T243 each took a third Codex round (a reachable
blocker in the verification round); the other verification-round findings were ruled follow-ups on store counts.

### 2026-09-24d — **THE SESSION CLOSED ON MIT'S CALL BEFORE WAVE 3 (D-595). THE CHAIN SHIPPED (T199 #465, BUNDLE A #467, T210 #468, T209 #469, T188 #470, T208 #471) PLUS close6/close7 (#466, #472); THE 0-D REPAIR IS DONE (43 → 9 OPEN DAMAGED, THE NINE ARE `gone`); T173's TWO HEADING CLASSES ARE FIXED ON THE CARRIER (T215/T216, 1,189 CLEARS, ROUND 2 IN FLIGHT); A WHOLE-SWEEP REVIEW READ 0 BLOCKERS AND ITS FOLLOW-UPS ARE BUILT (T222–T226) AND REVIEWED; THE LIVE CONFIG'S GITHUB LISTS ARE RESTORED. THE PRIMARY IS ON `main` AT #472. THE NEXT SESSION IS HEADED BY THE ENTERPRISE SEAT.**

**Read `.agent/2026-09-23c-session/HANDOFF.md` FIRST — §0 says how the seat-headed session differs (memory by symlink,
executors share its window), §2 the four executors left RUNNING at close, §4 the wave-3 recipe.** Verify against
`git log origin/main`, `gh pr list` and the `<tag>.exit` sentinels before believing any of it.

**Next session, in order (do not start wave 3 until Mit says so — ruled 19:23 on 09-24):**
1. **Read the four executors' results** (HANDOFF §2): batch 4 round 2 (`bw-batch4`, the seven wrong clears must read
   `ineligible`), T173d round 2 (`bw-t173`, Codex's two T216 sentences must return to preference), batch 5
   (`bw-batch5`, T211–T213), batch 6 (`bw-batch6`, T214). Run the owed Codex rounds (batch 4 verification, T173d2
   verification, batch 5 and 6 review). Then T173e (rebase onto batch 4's round-2 head), rebase batch 5 and 6 behind it.
2. **Wave 3** (HANDOFF §4): stack t218, t226, fu3 (T222–T225), batch 4, T173, batch 5, batch 6 on `origin/main`; ONE
   `make check`; ship sequentially. Every engine ship re-keys `engine_version`.
3. **Read run 476** (04:00 CDT 09-25, on `6a7e548e`): LONG by design — T208 moves the facts key, so 298,389 open
   postings re-evaluate and gate verdicts re-judge through the refresh (D-595 F7). Also T198's prediction (db, hitachi,
   vfc, mtb complete on their second scan), hiring.cafe's recount by row, the GitHub lists fetching again.
4. Docs after wave 3: D-596 (what shipped, the two-arm readings), METRICS, this file.

**Rulings today (D-595):** do not start wave 3 this session; the seat heads the next; the planner's fix-first call on
T173 (D-590's 1,468 → 1,189 with the heading classes fixed) stood unopposed. **Config changed:** `lane_github_lists`
set to the two former defaults (review F4). **Store changed:** the 0-D repair (34 bodies), run 473 reaped.

**Open tickets** (`TICKETS-2026-09-22c.md` §2026-09-23c): READY for wave 3 — T218, T226, T222–T225; IN FLIGHT — batch 4
round 2 (T200–T202), T173 + T215/T216 (round 2), batch 5 (T211–T213), batch 6 (T214); WRITTEN — T219 (1,752 postings,
the largest engine lever left), T220, T221, T227; T198 waits for run 476.

### STATE's standing sections as they read before the 2026-09-25b rewrite (verbatim)

*Moved because five of their claims had gone stale (P2 item 8 "NOT STARTED" — it shipped as T184; the 0-D repair "live" — done 09-24d; the provisional pass "Mit's ruling" — superseded by D-521; the Windows nightly "green, n = 1" — red since 09-23, T251; "B8 precision MET 5.4%" — audit474 read 17.9%, the closing protocol is now D-598's opus census) and the rest is settled guidance. The heading levels are kept as they were.*

### Owed, and specifically NOT done

- **THE DEGREE-WAIVER WIDENING SHIPPED 2026-09-22b (D-540), all ten arms.** The enumeration
  (6,712) was a TEXT-MATCH count, not a verdict-change count: the live two-arm reading over the
  6,964-posting delta is **10 rescued from `ineligible`, 0 demoted, 0 newly ineligible** once
  D-541's `met`-abstain fix is included. `or foreign equivalent` stays excluded and is now pinned by
  a control; the **pre-existing** direction-blindness is unchanged and still not fixed. **The
  verdict-level effect over the 65,879 postings the OLD escape already matched is NOT attributable
  from persisted state** — run 470's re-judge bundles the engine batch, #407 and T150 (D-547). Do
  not re-derive it from the store; only a replay at each commit could separate them.
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

**0-D's REPAIR half is the one LIVE residual from the four settled owner-gated items moved to
`STANDING-FACTS.md` on 2026-09-21** (0-B/0-C/0-D shipped, the <= 1-YoE floor ruled and executed,
0-1 retired, per-source thresholds fully ruled — **nothing is owed on any of them**). The repair:
117 overwritten bodies and 301 lane-payload `raw_json` rows, never part of the ruling, still
available if Mit wants it. **D-498's rule (b) IS BUILT** (`_suppress_lane_copies`,
`top_cmd.py:1062`); rule (c) stays refused.

2. **TRACK 1 — CLOSED (D-482): accept the loss**, per D-453. Do not re-raise it from the 382 or
   the 113.
3. **Mit's résumé calls** — whether to send a document at all; the D-220 prose rewrite of the submitted "sole iOS developer" answer (outside the bundle); the per-lens formatting session.
4. **P2 item 8 — SHIPPED as T184 (#444, D-581).** 5. **The bundle lock — already shipped 2026-09-04 (`ae64c0ee`); closed.**
6. **T173 — RULED YES (D-594); re-measured with its heading classes fixed (D-595): 1,189 clears, ships in wave 3.** (History:
   Yes ⇒ 1,468 postings move `uncertain` → `eligible` (about five times today's `eligible`), all stated
   preferences (20/20 sampled), ~13 wrong clears inherited from two main-side defects (T196, T197). No ⇒ they
   stay `uncertain` with no row. Rebased on the batch in `bw-t173`; gate not yet run.)
7. **T188 — SHIPPED (#470, all three; D-594).** (History: D1 moves `PROMPT_VERSION`,
   so EVERY stored gate verdict re-judges once through the refresh at 130 a run; the owner accepted it.)
8. **`career_field` vs the taxonomy field — RULED and SHIPPED as T208 (#471, D-594): the taxonomy is the one source.** (History, D-586: the ranker's field gates read the taxonomy's field;
   `Facts.career_field` is NULL on the live profile and its catalog accepts only `software`. Reconcile
   (one source), or retire `career_field` from the eligibility facts.)
9. **The reviews' follow-ups** (§2026-09-23c): the `_recovered` reserved-name collision, the funnel's
   `location_class` column still the US reading, cross-check disagreements not soft-alerted, the
   STANDING-FACTS grounding key, T190's test-only drift, T192's trickled-headers limit; from run 475: T198 (the board cap vs slow Workday
   boards) and T199 (hiring.cafe's 9-vs-10 recount); from T173's measurement: T196 (`a plus` without a word
   boundary) and T197 (an aside about another noun hedges the bar) — both now IN batch 3; from batch 3's round 2
    (D-592): T200, T201, T202 — engine batch 4, round 2 in flight (D-594); T211–T214 written.
10. **The T179 refresh backlog — RULED: fixed by ORDER, T195 SHIPPED (#459, D-594).** (History, D-589: 315 top-level leads with no live verdict, 14 of them judged
    `ineligible` on 09-22 and standing in the apply lane. Options: raise `gate.refresh_budget` above 130
    for a few runs; have the refresh rank released holds first (T195); or let it drain at ~6 runs.)

## Open questions — Mit's, not to be resolved by fiat

**B8's RETIREMENT question is RULED and CLOSED (2026-09-21, D-534) — do not re-raise it.** The
9-of-14 volume record does not block: all 14 days are on the 652-board fleet, post-expansion
`pdf.entered` reads **25 / 22 / 26 (3 of 3, mean 24.3)**, and the engine batch's `rules_hash`
move restarts the 14-day confirm by `PROGRAM.md` §1's own rule anyway. **What is owed is B8's
volume half holding 14 days on the 1,807-board fleet.** Run 471 read 20; runs 472 (the batch) and
473 (T161/T163/T169) each re-key, so the window's day 1 is **run 473** (D-566, D-572). This is a
DIFFERENT question from item 0 below, which is about the alert CHANNEL.

0. **B8's volume reading on the escalation channel — CLOSED 2026-09-22e (D-554).** D-529's
   condition is met (post-expansion 25/22/26/20, and 1 of 5 at worst after run 471, against 9 of
   14 pre-expansion). The owner ruled: onto the channel. It is shipped; `summary.errors` now carries
   it.

1. **The projection spec's six open questions** (§12).
2. **The Snap `Level 3`/`Level 5` leak stays open by design** — with no bindings file every level
   token abstains. boardwatch ships no verifiable claim about any company's ladder.
3. **Whether `censored` boards publish a coverage ratio, and the 17 silent boards.** The class is
   **15 boards and 43,371 postings that can never be listed at all** (run 127) against an ~84,821
   open corpus. **Sized, not solved, and no budget can solve it.** See D-336.
4. **`ServiceNow Developer` — RULED (D-577 §1): excluded as personal policy data**, the seven
   platform-developer titles added to `exclude_titles` at the 2026-09-24 cutover (D-588).
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
- **Provisional pass: recorded MET on runs 6, 7, 8 (D-483) — but runs 7 and 8's own funnels read `DOES NOT RECONCILE` (B6) through the reporting gap T60 closes (D-489); whether they stand is Mit's ruling.** 14-day confirm: day 1 = run 9 (2026-09-06 06:00 CDT, clean tick, same gap), passive. **B8 (D-487): 17.2% on n = 128 is the BAR reading; 14.7% was a gate-judged SUB-CUT (D-513). Pre-drain re-read 16.2% / 18.8% = NOT MET; POST-DRAIN 6.9% / 5.6% = **MET** (D-514).**
  Not chased (D-351 item 2: work comes first), and every `rules_hash` bump restarts the count.

## Live blockers and carried gaps

**THE FIVE-NIGHT WINDOWS RED IS OVER, AND THE 2026-09-21 NIGHTLY WAS A DIFFERENT, REAL DEFECT
(D-535).** T128's three fixes and the `%s` strftime fix hold — all three read **zero occurrences**
on every run since. What took the 09-21 nightly (`35607814820`) red was ONE test on Windows 3.12
alone: `test_a_lock_free_reader_only_ever_sees_a_complete_tree`, `CURRENT is unreadable:
Permission denied`, on **1 failed / 10,499 passed**. It had passed on the 09-19 and 09-20
nightlies and on both dispatches, so it is an **intermittent race, not a break** — and the race is
real: `os.replace` on `CURRENT` denies concurrent opens on Windows, so the lock-free reader saw
neither revision. Fixed; see D-535. **Only a Windows dispatch can confirm the race is gone and ONE
green run is not enough** — at the observed rate a single pass proves almost nothing, so read
several nightlies before calling it closed. **The 2026-09-22 nightly (`35727396657`, on the fix) is the first
green scheduled nightly after four reds, all three `windows-latest` jobs green — n = 1.**

**READ A WINDOWS RESULT BY TEST NAME AND COUNT, NEVER BY COLOUR.** The dispatch before this one
(**35547739139**) was also red, and it did NOT mean the fix had failed: T128's three targets were
already at 0 occurrences while 46 *different* tests failed on the unrelated `%s` break. A red
dispatch is a list of names to compare against the ones you expect. The green one was confirmed a
real run the same way: Windows 3.13 read 10,500 passed / 85 skipped against local's 10,584 / 1, and
**10,584 − 10,500 = 85 − 1 = 84**, so every missing pass is an accounted-for platform skip rather
than a collection failure.

**WINDOWS IS STILL INVISIBLE TO ORDINARY CI, AND THIS DOES NOT CHANGE.** It is in the matrix for
`schedule` **and `workflow_dispatch`** only (`ci.yml`'s `os:` expression is the authority) — a green
27-job CI on a `main` push says **nothing** about Windows, and a PR cannot show it either.
**Validate any Windows-touching fix with `gh workflow run ci.yml --ref <branch>` before merging.**
Read the nightly with `gh run list --branch main --json event,conclusion` filtered to
`event=="schedule"`; `--limit 1` shows the newest run of EITHER kind, which is how a red nightly
reads as green.

| Item | Detail | Owner |
|---|---|---|
| **boardwatch sees 16.4% of job-apps' eligible yield — RE-DERIVED 2026-08-30, and the METHOD was wrong before** | **45 of 275 (16.4%)**, cohorts 08-23..08-29, on the **379-board fleet**. This replaces "10.1%, owed a check". It decomposes: fleet growth 344->379 gave 10.1 -> **13.8%**; adding an **exact ATS-slug key** alongside name matching gave 13.8 -> **16.4%**. **Name-only matching undercounts, so 7.7% and 10.1% are FLOORS** — boardwatch stores Micron as `Micron TDIT`, so the old method scored a watched company as unwatched; same for HPE/`Hewlett Packard Enterprise`, Cox/`Cox Automotive`, Disney/`Walt Disney Company`, Toyota, VIAVI. **The unreached 230 split: aggregator-only 60.7%, unsupported employer host 21.1%, board-addable just 1.8%** (5 postings in 7 days, 4 of them SmartRecruiters — the class D-370 declined on measured cost), so the cheap remainder is ONE Workday board (Motorola Solutions). **The gap is lanes, not boards.** Script: `.agent/2026-08-30-session/reach_v2.py`. Amazon/TikTok/Apple/ByteDance use none of the 6 ATS, so a slug cannot reach them. Closing it means a new discovery lane — GitHub new-grad lists are 19.1% of yield for ~5 public-repo GETs and are NOT the ToS trap the v2 decision was written about. **Reopens D-008** | **Mit** (reverses a shipped decision) |
| **Citi sits at 13.1% coverage, permanently** | Workday's `total` censors at 2,000; the facet sum (uncapped, control-verified) says 4,589. Our pager wraps at ~2,000 too, so post-drain Citi holds ~2,214 of 4,589 and nothing reports it | **Mit** (input-side) |
| **Run 9 (2026-09-06) tick-fired CLEAN on the restored five-lane config (D-487, read D-489); run 10 is the first whose funnel can reconcile a split slate (T60)** | The launchd job invokes the **editable** venv at `boardwatch/.venv/bin/boardwatch`, so whatever branch that tree is parked on IS the unattended run's code and `rules.yaml`. **Park the primary checkout on `main` before ending every session**; a stray branch changes EVERY subsequent run. The tick fired 06:00 CDT until the 09-09 reboot and **04:00 CDT since** — launchd keeps its boot zone, and the plist's hour is 4. Verify a tick by `runs = N` in `launchctl print` and the log mtime, never by the run row alone: a hand run proves the code, only a tick proves the plist | **Mit** (reboot); every session (discipline) |
