# PROGRAM STATE — read this first

> The one file a fresh session with zero memory reads to know where the program stands.
> **If it disagrees with the repo, the repo wins** — fix this file and note the correction in
> `DECISIONS.md`. Plan: `PROGRAM.md`. Numbers: `METRICS.md`. Rationale: `DECISIONS.md`. What shipped:
> `CHANGELOG.md`.
>
> `DECISIONS.md` and `METRICS.md` each carry an **index spanning themselves and a closed archive**
> (`*-ARCHIVE.md`, D-108). Read the index, then the one range you need — never the whole file.

**This file states only what is true now**, and carries no commit sha or commit count on purpose — both go
stale inside a single session (D-017). `git log --oneline -1` is the authority. **Rewrite it, never prepend
to it**: it reached 1,386 lines by stacking superseded headers and per-session retrospectives, which belong
in `DECISIONS.md` / `CHANGELOG.md` / `METRICS.md`. Keep it near 170 lines. Git has every previous version.

---

## Current standing

**P6's BUILD IS COMPLETE — Slice 3 shipped, so items 1–6 all exist.** Slice 3 is applied-state suppression
(item 5) and liveness (item 6), recorded as **D-111**. Slices 1 and 2 were built, reviewed and pushed before
it (D-095, D-103 … D-107, review **D-110**). Schema head is **`p6_job_dispositions`** and Slice 3 adds no
migration.

**Read D-110 before touching the ledger and D-111 before touching liveness.** D-110 holds the Slice 2
review's findings, the two deliberately left unfixed, and why. D-111 holds Slice 3's design and — more
importantly — the measurements that shaped it.

**Slice 3, in one paragraph.** The ranker gained a `hidden_applied` bucket read straight from
`applications` (not mirrored into a ledger disposition — one fact, one home), drained by
`top --include-applied` and released by `track status <id> withdrawn`. Liveness re-fetches each
shortlisted posting immediately before its résumé is built and withholds one answering **404/410**;
everything else is served. Funnel artifact is now **version 4**.

**The closed-phrase catalog was NOT shipped, deliberately — not an omission to correct.** `PROGRAM.md`
item 6 calls it the authoritative signal, inheriting that from job-apps, which scraped HTML. Providers
assemble `body_text` only from JSON-payload description fields and never see the rendered page, so page
chrome cannot reach that column. Measured: **11 of 23,455** matches, **all false positives**; a
high-precision catalog matches **0**. Full reasoning in D-111 and `core/liveness.py`'s docstring; the
older "3 open postings contain a closed phrase" figure is **superseded** — recorded without its catalog.

**Slice 3 WAS reviewed in-session — three reviewers, two BLOCKERs, both fixed** (D-111). Both were
invisible to reading and found by executing the pipeline. A fresh-context review is a second opinion now,
not an owed first pass; Mit is running one through Codex.

**Next action: P6 has nothing left to BUILD — its last two gate clauses need the system RUN.** Duplicate
leakage needs 7 days of runs (and the window must start after D-110, which changed which callers advance
the queue), and "0 dead postings" needs a real run whose leads are actually probed. Neither is a coding
task. So the useful work is, in order: (1) start accumulating real daily runs, which is gated on Mit's
`resume.yaml` fix below; (2) optionally take a fresh-context second opinion on Slice 3 — a self-contained
prompt is written at `.agent/review-prompt-p6-slice3.md` (gitignored); (3) P2 item 8 or P3 slice 5, both
owner-gated and both wanting their own context window.

**0.3.0 is cut and TAGGED (`v0.3.0` → `426f45c`) but the release build FAILED and nothing published** —
33 tests died on the runner because no workflow installs `tectonic`/`poppler-utils`, a gap that predates
this session by three days. Nothing is burned; see the blockers table.
Version, changelog and lockfile are on `main`. Cutting it is also what surfaced that `README.md` and
`docs/configuration.md` still described **Typst** — replaced by tectonic eleven decisions earlier — and
that `config show` reached only 4 of 10 settings, `seen_ttl_days` among them (D-112). **Confirm the
publish on PyPI first thing next session.**

**Next session's first input: Mit's Codex review of Slice 3.** He is running it externally; the prompt is
`.agent/review-prompt-p6-slice3.md` (gitignored). Take the findings back and treat them like D-110's —
in-session reviewers already found two BLOCKERs here that reading alone had missed.

**One earlier review fix does not ship.** `bwd` lives in `.agent/bin/bw-daily`, which is gitignored, so its
`top --no-record` fix is local to this machine. The *defect* was in shipped behaviour and the shipped fix is
the `--no-record` flag itself; a fresh clone's `bwd` will need the same one-line edit.

**The live store has NOT had Slice 2 applied to it.** It is migrated and backfilled for Slice 1 (head
`p6_posting_identities`, 117,254 identity rows, `identities verify` exit 0, 147 groups / 186 surplus rows /
0.79%). Slice 2 was verified on an **isolated copy**. Running `boardwatch identities regroup` against the
live store is a deliberate, still-unrun step that would move 186 postings onto 147 canonical jobs;
**Mit declined it on 2026-08-10** — not blocked, just not now. It would need the `p6_job_dispositions`
migration first, or there are no dispositions to carry.

**Re-verified read-only 2026-08-10 (third time):** head `p6_posting_identities`, **no `job_dispositions`
table**, `postings` 24,073 and `count(distinct job_id)` **24,073 — still exactly 1:1**. That is the cheap
proof, since a regrouped store would read **23,887**. Two things get misremembered as "we already did the
live store": the Slice 1 backfill (which genuinely did write those rows here) and the regroup's
**idempotence** check, which ran on the copy. The 769 MB backup is still beside it; disk is fine.

**What has NOT been demonstrated on real data:** the ledger's end-to-end behaviour and the liveness probe
against real leads. A `boardwatch top 5` against the 23,455-posting copy ran past 20 minutes without
finishing and was stopped — it pays for `run_preflight` + `run_eligibility` over the whole corpus. Both are
covered by mutation-checked tests; neither has been exercised at corpus scale.

---

## Phase status

| Phase | Build | Gate |
|---|---|---|
| P0 Instrumentation | **COMPLETE** — all nine items 0–8 | **MET** (D-030); item 5 supplements without re-anchoring (D-031) |
| P1 Résumé artifact gate | **COMPLETE** — P1a + P1b | **MET** (D-032; D-033 closes item 3c without changing the standing) |
| P2 Profile + keystone | **items 1–7 shipped.** Item 4 ships a *mechanism*, inert for the bundled `[software]` catalog; item 7 is done for `work_auth` only. Item 8 NOT STARTED | **MET AS RECONCILED** (D-075) — evidence is test fixtures, not a live run; the "three different verdicts" clause is deferred to item 8, not retired |
| P3 Unattended one command | **COMPLETE** for everything needing neither Mit's domain input nor Docker | **NOT MET** — 7 consecutive unattended runs, plus the cross-OS two-writer test. Slice 5 remains |
| P4 Craft gate | **COMPLETE** — items 1–7 | **NOT MET** — the blind craft review is the owner's, and has not been run |
| P5 Eligibility decides | **COMPLETE** — D-073 + D-074 | **MET** — INELIGIBLE precision 16/16, 0 span violations, `eligibility score` exits 0 |
| P6 Liveness + dedup | **BUILD COMPLETE — all six items.** Slices 1 and 2 merged, reviewed and pushed (review D-110); Slice 3 (items 5, 6) built, reviewed in-session and gate-green (D-111) | **NOT MET — 2 of 4 clauses met**, below |
| 14-day acceptance | not started | — |
| P7 Breadth | not started | — |

### Gate P6, clause by clause

| Clause | Standing |
|---|---|
| Duplicate leakage measured over 7 days, ≤ 5% | **NOT met — now genuinely measurable.** Slice 1 made `unique` a number; Slice 2 (D-105) stopped a single newly-discovered posting from silently disabling suppression, without which it was `None` on essentially every real run. Needs 7 days of runs — and note D-110 changed which callers advance the queue, so a 7-day window started before it is not comparable with one started after |
| **0** dead postings reaching the lead list | **NOT met — but now buildable and measurable**, which it was not before Slice 3 (D-111). The check exists and runs on every `boardwatch run`; meeting the clause needs a real run whose leads are probed. Note the probe's recall is low by design — 7 of 8 known-dead Workday/Ashby URLs still answer 200 — so it supplements the scanner's `CLOSE_AFTER_MISSES = 2` rule and never replaces it |
| A deliberately-injected hash-collision test | **MET** (D-100) — `test_string_verify_blocks_suppression_when_bodies_diverge` forges `identity_key` equality over divergent bodies and the group is refused. A test, not a measurement, so met outright |
| Audit of 20 sampled suppressions | **MET** (D-101) — 20/20 genuine, zero false positives, 13 employers, sampled deterministically so it can be re-run. Slice 2 adds **no new precision evidence** |

---

## Open questions — Mit's, not to be resolved by fiat

**1. Should `pipeline/runner.py` keep swallowing a funnel-write failure into a printed warning?** (D-076.)
It once turned a renderer `TypeError` into a silent half-written artifact pair — `.json` written, `.md`
missing, run still exit 0. The crash is fixed; the swallow will hide the next renderer bug identically. Also
defensible as a fail-open. Options: leave it; make it fatal; keep it non-fatal but surface it in the run's
`errors` so `verify`/`doctor` can see the artifact is incomplete.

**2. Should any family other than `work_auth` default to `blocker` severity** (e.g. `clearance`)? Owner-gated
since D-035, unchanged by everything since.

**3. Do docs-only commits owe a full `make check`?** D-014 says yes; practice has been
`make generalization && make index-check`. D-109 chose a design correct either way rather than resolving it.

---

## Live blockers and carried gaps

| Item | Detail | Owner |
|---|---|---|
| **Three `resume.yaml` bullets exceed the 220-char layout gate** | Forces an untailored-master degrade on every posting. The file also lacks Knowledge Forge, has stale `skill_groups`, and an empty extracurricular block. **Mit pins `resume_max_pages=1` — do not advise setting it to 2.** | Mit (content) |
| **P2 item 8 — the onboarding gatherer** | The thing that would make the field tier fire for anyone. D-054 forbids us authoring non-tech field content, so it must be gathered per user. Needs its own brainstorm | owner-gated |
| **0.3.0 did NOT publish — the release build FAILED, and nothing was uploaded** | Tag `v0.3.0` → `426f45c` is pushed, but run `31412535583` failed in `build + smoke test` and all three publish jobs (**PyPI, GHCR, GitHub Release**) were correctly **skipped**. PyPI still 404s for 0.3.0, so **no version is burned** — the same tag can be re-run once the cause below is fixed. Fix, then re-tag (delete and re-push `v0.3.0`, or cut `v0.3.1`) — Mit's call | Mit (release) |
| **ROOT CAUSE: no workflow installs `tectonic` or `poppler-utils`, and the suite now requires them** | 33 tests failed on the runner, every one of them `tectonic binary not found on PATH` or `_pdf_page_count` returning None (needs `pdfinfo`). **Pre-existing, not a regression from Slice 3**: tectonic became a hard dependency in D-058/D-060 (`e9c0393`, 2026-08-07), *after* v0.2.0 was tagged on 2026-08-04, and `ci.yml` runs on `5f0150d` and `101bc67` — both predating this session — fail identically. The `Dockerfile` installs both (`curl … tectonic@0.17.0` + `poppler-utils`); **no workflow does**. It went unnoticed because CI was not acquiring runners, so nothing ever ran | Mit (scope) |
| **Fixing it is a real scope decision, not a one-liner** | `ci.yml` runs a 3-OS matrix (ubuntu/macos/windows × py3.11–3.13); tectonic + poppler on Windows is awkward. Options: (a) install on all three, (b) install in `release.yml` + ubuntu only and narrow the matrix, (c) skip the tectonic-dependent tests when the binary is absent — **(c) is the tempting one and is against this repo's ethos**, since it would silently stop verifying P1a's hard résumé gate on CI while reporting green. Do not pick (c) by default | Mit |
| **CI IS acquiring runners again** | The standing "never acquires" failure has **resolved** — `ci.yml` and `release.yml` both ran on 2026-08-10. This session predicted the release would queue forever and was **wrong**. CI now reports real, pre-existing failures (see above), so it is once again a signal worth reading — but it is red for the tectonic reason, not for a code reason | GitHub |
| **P3 Slice 5 — LLM economics** | Substantial and design-heavy; use a fresh context window | P3 |
| **P3 item 8 — cross-OS two-writer WAL test** | A same-OS test proves nothing; needs a Docker-Linux-container + macOS-host harness. The documented-stance half shipped (D-041) | P3 |
| **A `SIGKILL`ed run leaves a dangling `runs` row** | `try/finally` covers exceptions and Ctrl-C, not SIGKILL. Largely drained by the age-based reaper (D-046); a heartbeat-column reaper is the deferred correct fix | P3 |
| **CI never acquires a runner** | Runs queue forever unacquired; `gh workflow run ci` returns 422 (the workflow has no `workflow_dispatch` trigger). **Not a repo problem — do not re-diagnose it as a test or config failure.** Local `make check` is the authority. Check run `status`, never mere presence | GitHub |

---

## Standing facts a fresh session should not re-derive

- **Only a caller that DELIVERS a lead may consume the queue** (D-110). `rank_open_postings` takes
  `record_surfaced`; `eligibility gate request` and the pipeline pass `False`, and `top --no-record` is the
  operator's opt-out. The pipeline writes all three ledger tiers *after* the tailor loop and gates the `seen`
  tier on the stage completing. Do not move the `seen` write back into the ranker's unconditional path.
- **Liveness is never cached, and "never" includes `postings.status`** (D-111). A `dead` probe withholds the
  lead from that run only. Writing the status would let one 404 from a flaky CDN retire a live requisition
  **irreversibly** — a closed posting stops being ranked and so stops being probed. That column belongs to
  the scanner's `CLOSE_AFTER_MISSES = 2` rule, which measurably works: 0 open postings are stale beyond 7 days.
- **Only 404/410 withholds a lead; everything else is served** (D-111). Timeout, 403, 5xx, redirect and a
  NULL URL are all `unknown`. 403 is not hypothetical — a live Pinterest posting answers 403 to an
  unfamiliar user agent, so treating it as gone would silently blacklist whole employers.
- **An unprobed run reports liveness as UNMEASURED, never 0 dead** (D-111). `run_pipeline` takes an injected
  prober and does no network I/O of its own; `run --no-check-liveness` opts out.
- **Applied state is read from `applications`, never mirrored into the ledger** (D-111). `interested` does
  not suppress (it is `track add`'s default) and neither does `withdrawn`, which is the drain. Checked
  *before* the ledger, so a job that is both applied-to and `built` reports the applied reason — `ledger
  reopen` releases the ledger row and nothing releases an application.
- **A new ranker drop bucket has SIX hand-maintained mirror sites and only three are checked** (D-111,
  after two reviews corrected the count upward). `RankedResults` + its increment site; `runner.py`'s
  mapping into `ShortlistCounts`; `ShortlistCounts` and the shortlist `Drop` list; a **tailor**-stage
  `Drop` if the bucket removes postings after ranking; `_zero_output_guard` if it can explain an empty
  day; and `_shortlist_line`. The stage `reconciled` identities catch the middle ones at runtime.
  **Nothing catches `_shortlist_line`** — the full list is in `RankedResults`'s docstring.
- **Only a deterministic refusal earns a permanent `skipped`** (D-110). `LeadArtifactError` carries both gate
  reasons as data and `DETERMINISTIC_GATE_REFUSALS` is the closed catalog; a non-zero `tectonic` exit is
  environmental and must be retried, never buried. Out-of-catalog is treated as environmental.
- **No `policy_version` component covers the résumé or `resume_max_pages`** (D-110). The stamp is the run
  manifest's five fields, and `profile_row_hash` hashes only the five columns the *ranker* reads. So trimming
  `resume.yaml` or changing the page limit does **not** make a permanent decision stale, and
  `ledger reopen --stale` will not release it — `ledger reopen --job <id>` is the only path. Do not repeat
  D-103's claim that such a lead "stays suppressed until somebody runs the drain".
- **Regrouping carries the ledger decision with the postings** (`_carry_dispositions`) and releases the
  emptied row (D-110). `protected_job_ids` cannot catch a merge that leaves it behind: `artifacts.job_id` is
  NULL on all 44 live rows.
- **`AGENTS.md` records no phase standing, test count or coverage figure, on purpose** — it once asserted
  "P6 and P7 have not started" in the commit range that shipped two P6 slices. This file is the only source
  of standing.
- **`make check` is the only gate.** pytest + ruff + mypy green is *not* green — the generalization checker
  only runs under `make check`. Run it in a detached worktree pinned to a commit
  (`git worktree add --detach /tmp/bw-gate <sha>`) so editing the main tree cannot corrupt a run in flight,
  capture the real exit code, and **never** pipe it through `head`/`tail` (SIGPIPE gives a false negative).
  End a backgrounded gate with `exit $ec`. For a docs-only change the practice has been
  `make generalization && make index-check` (1.3 s together) — but note **D-014 rules that docs-only commits
  are not exempt** from `make check` at all, and the practice quietly relaxes it. D-109 chose a design that
  is correct either way rather than resolving the contradiction; resolving it is Mit's.
- **After appending to `DECISIONS.md` or `METRICS.md`, add the index row and run `make reindex`.** The
  spanning indexes' line numbers drift on *any* edit above a heading; appending D-109's own row shifted 32 of
  them. `make check` fails on a stale index (D-109).
- **The per-task fast-check set must include `tests/unit/test_store.py` and `tests/unit/test_schema_head.py`**
  for anything touching `tables.py`, a migration, or the Alembic head (D-099). `test_schema_head.py` pins the
  head, so a new migration must bump it explicitly.
- Neither `python` nor `boardwatch` is on PATH — always `uv run …`.
- No `__init__.py` under `tests/`, so test module basenames must be globally unique or collection aborts with
  an import-mismatch error. `make check` runs mypy on `src` and `tools` only, but ruff on everything
  including `tests/`.
- **A migration must never import a live catalog into its CHECK constraint** — it makes the constraint change
  retroactively and diverges a fresh database from an already-migrated one. `tables.py` may import it (that is
  metadata, not history); `test_migrations_match_metadata` holds the two in agreement. Name constraints with
  `op.f()` or that test sees permanent drift.
- **The résumé renderer is `tectonic`** compiling Mit's real LaTeX template, **not Typst** (D-058/D-060).
  A `typst` binary is on this machine; nothing calls it. The tailoring architecture is already correct —
  do not rebuild it (`PROGRAM.md` §5.1).
- **`track` has never been used** — `applications` and `application_events` are both 0 rows. That is why P6
  item 5 ships as a mechanism with tests as its evidence, and why regrouping's tracked-job refusal is
  *latent* rather than unreachable (D-104).
- **`hidden_duplicate == 0` is ambiguous; `hidden_handled == 0` and `hidden_applied == 0` are not.** The
  first can mean "dedup never ran"; the others are never completeness-gated, because a stored disposition
  and an application each record a decision already taken (D-106, D-111).
- **`_verify_quad` has never fired** (D-097). It guards a SHA-256 collision and staleness but not
  normalizer lossiness. **Never cite "string-verified" as precision evidence.**
- **D-072, the model-tier benchmark, is DEFERRED INDEFINITELY** (D-102) — not owed, not blocking.
- **`.agent/` and `.superpowers/` are gitignored** working material, not a source of truth for released
  behaviour. `CHANGELOG.md` is authoritative for what shipped.
- **Live urgency.** `STAGE1_ONLY=1` is active in job-apps' launchd plist; its 08:30 run stops after
  discovery. Nothing is generating Mit's résumés daily right now.

---

## Process lessons this program paid real time for

Only what `CLAUDE.md` does not already say. Everything general — a failed command is not a negative
result, a self-report is not verification — lives there.

- **Commit before EVERY mutation round, not once before you start.** The `git checkout` that reverts each
  mutation destroys any uncommitted edit, including a fix written five minutes earlier. This has now fired
  three times; the narrower phrasing is what let it fire the third (D-111). Clear `__pycache__` too —
  stale bytecode fakes both a CAUGHT and a spurious failure. Derive the mutation from the test's stated
  CLAIM, never from the implementation.
- **Reviewers that RUN the code find what reviewers that read it cannot.** Both of D-111's BLOCKERs were
  invisible to reading and obvious to one pipeline execution. Dispatch a **separate** docs-only reviewer
  as well — they keep finding blockers in documentation written about already-reviewed code.
- **Measure the spec's premise before building it.** D-098 priced a deferral with the wrong subsystem's
  figures (D-105); D-111 found PROGRAM item 6's authoritative signal was 0-for-11 on the real corpus and
  structurally unable to reach the column it reads. A spec written against a different codebase's data is
  a hypothesis, not a requirement.
