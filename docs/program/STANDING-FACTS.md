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
because `hidden_hard_filter` is corpus-scoped at **18,472–18,932** every run. **Root cause, and it
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
| company reach vs job-apps | **~10.1%** — supersedes the stale **7.7%** | parallel session, NOT re-derived |
| fetch-latency backlog, deferred postings | **18,787 → 5,227**, self-draining after `detail_fetch_budget` 50 → 400 | parallel session, NOT re-derived |

**Remaining reach work**, from `.agent/2026-08-28-coverage-dedup-session/B-discovery-miss.md`
(~28 misses/day, and the class is **company reach, not ATS coverage**):

- **~22 misses are addable by simply adding a supported-ATS board** — a named list is in that doc
  (RTX, UCF, HP, Bosch, Siemens Healthineers, Domino's, ModMed, …). This is the cheap half.
- **~122 aggregator-URL misses need a dereference step** on the linkedin/hiringcafe lanes; low volume
  today.
- **~33 are unsupported-ATS and OUT OF SCOPE** — no new adapters (D-272).

**Do not start this without re-reading `CLAUDE.md`'s "Breadth is last".** Adding input multiplies
whatever is downstream of it, and the slate cap (D-345) has not yet been observed on a single run.

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
