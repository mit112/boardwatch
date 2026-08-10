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
shortlisted posting immediately before its résumé is built and withholds one answering **404/410 at the
URL asked about** (D-113 narrowed this: a 404 reached through a redirect is served, and counted);
everything else is served. Funnel artifact is still **version 4** — the redirect counter is an additive
key, and every bump so far has signalled a new top-level section.

**The closed-phrase catalog was NOT shipped, deliberately — not an omission to correct.** `PROGRAM.md`
item 6 calls it the authoritative signal, inheriting that from job-apps, which scraped HTML. Providers
assemble `body_text` only from JSON-payload description fields and never see the rendered page, so page
chrome cannot reach that column. Measured: **11 of 23,455** matches, **all false positives**; a
high-precision catalog matches **0**. Full reasoning in D-111 and `core/liveness.py`'s docstring; the
older "3 open postings contain a closed phrase" figure is **superseded** — recorded without its catalog.

**Slice 3 has now been reviewed twice and is DONE.** Three in-session reviewers found two BLOCKERs
(D-111); Mit's fresh-context Codex review then found three more — a redirected 404 forging a gone-status,
a `Liveness` that validated its verdict and signal independently, and `top` swallowing its own hidden-bucket
notices on an empty result. **All three are fixed and mutation-checked (D-113).** No review of Slice 3 is
owed.

**Next action: P6 has nothing left to BUILD — its last two gate clauses need the system RUN.** Duplicate
leakage needs 7 days of runs (and the window must start after D-110, which changed which callers advance
the queue), and "0 dead postings" needs a real run whose leads are actually probed. Neither is a coding
task. So the useful work is, in order: (1) unblock and push the 4 held commits, confirm `ci.yml` green, then
re-release 0.3.0 (below — CI itself is already proven green on all three OSes);
(2) start accumulating real daily runs, which is gated on Mit's `resume.yaml` fix below; (3) P2 item 8 or
P3 slice 5, both owner-gated and both wanting their own context window; (4) the career-profile bundle's
Gate A, T10 onward — a parallel track that needs no owner decision to continue (below). Slice 3's
second-opinion review is **done** — do not re-run it from `.agent/review-prompt-p6-slice3.md`.

**`main` is 13 commits ahead of `origin` at the time of writing** — 4 from the P6/release work and 9 from
the Gate A track. `git status --short --branch` is the authority; that count goes stale immediately.

**0.3.0 is cut and TAGGED (`v0.3.0` → `426f45c`) but the release build FAILED and nothing published.**
33 tests died on the runner because no workflow installed `tectonic`/`poppler-utils`, a gap that predated
that session by three days. Nothing is burned — PyPI still 404s for 0.3.0, so the version is free.
**The cause is fixed and PROVEN on all three runner OSes (D-114):** run `31421520836` shows ubuntu and
macOS fully green and Windows passing 3,922 tests, so the 33 failures are gone everywhere. Clearing it
exposed one further Windows-only defect — the program-index gate decoded its logs as cp1252 and reported
all 114 rows as headless — which is fixed in the same range and pinned by an `EncodingWarning` test.
**Confirm `ci.yml` is green on all three before re-tagging.** Cutting the release is also what surfaced that
`README.md` and `docs/configuration.md` still described **Typst** and that `config show` reached only 4 of
10 settings, `seen_ttl_days` among them (D-112).

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

**A PARALLEL TRACK now exists: the canonical career-profile bundle, Gate A — 9 of 19 slices built
(D-115).** Not a P0–P7 phase, and it moved no program gate. Its design and implementation plan live
**untracked** under `docs/superpowers/` — read them there; do not work this track from a fresh worktree,
where they would disappear. `src/boardwatch/profile_bundle/` holds the typed outcomes, a restricted YAML
loader, the closed 33-document grammar, every record model, the JSON Schema export, a synthetic example
shipped as package data, an isolated canonical serializer with §7's identity algorithm, the global record
index, structural + referential validation, the blob store, and versioned secret scanning.

**Gate A is NOT met and the bundle is wired to nothing.** There is no `profile-bundle` CLI command, and
there is deliberately **no bundle-to-`Resume` bridge** — `tailor_cmd._resume_path` still returns
`settings.config_dir / "resume.yaml"` and nothing under `src/boardwatch/tailor/` imports the package (a
test asserts both directions). No SQLite schema, store-head, or Alembic change. **Gate B, the private
canonical baseline, stays prohibited until Gate A is implemented AND independently reviewed** — that
review is owed and has not happened. Next slice is **T10, semantics** (design §20.4); T11–T19 follow.
Read D-115 first: it records why several §20 rows deliberately have no check beside them.

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
| P6 Liveness + dedup | **BUILD COMPLETE — all six items.** Slices 1 and 2 merged, reviewed and pushed (review D-110); Slice 3 (items 5, 6) built, reviewed twice and gate-green (D-111, D-113) | **NOT MET — 2 of 4 clauses met**, below |
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
| **0.3.0 did NOT publish, and the re-release form is undecided** | Tag `v0.3.0` → `426f45c` is pushed, but run `31412535583` failed in `build + smoke test` and all three publish jobs (**PyPI, GHCR, GitHub Release**) were correctly **skipped**. PyPI still 404s for 0.3.0, so **no version is burned**. The cause is fixed (row below); what remains is Mit's choice between deleting and re-pushing `v0.3.0` and cutting `v0.3.1`. He deferred it until the fix is verified. **Either way the tag must land on a commit that CONTAINS the CI fix** — `v0.3.0` currently names `426f45c`, which has no `.github/actions/setup-typesetting`, so re-pushing it unmoved re-runs the identical failure. The new CHANGELOG entries sit under `[Unreleased]` and fold into whichever section that choice creates | Mit (release) |
| **The tectonic/poppler gap is FIXED but has never run on a runner** | `.github/actions/setup-typesetting` installs both on ubuntu, macOS and Windows, and is used by `ci.yml`'s matrix job and `release.yml`'s build job (D-114). Asset layouts and the Linux/macOS binaries were verified locally; **the Windows path is constructed from a verified zip layout, not from a green run**. The first push is the experiment. **Do not re-tag until `ci.yml` is green on all three OSes** — re-tagging on the strength of a plausible YAML diff is the same mistake that produced the failed build, with more confidence behind it | verify |
| **CI IS acquiring runners again** | The old "never acquires" failure has **resolved** — `ci.yml` and `release.yml` both ran on 2026-08-10, and `release.yml` picked up a runner in seconds. CI is a signal worth reading again. Do not generalise one workflow's failure to the whole account | GitHub |
| **4 commits are UNPUSHED, interleaved with another writer's** | `861ea74`, `a729609`, `eef6127`, `0eeef82` gate green **in isolation** cherry-picked onto `origin/main` (exit 0, 3,924 passed, 95.12%). A **concurrent session** is committing `profile_bundle` work into the same clone — its commits sit both below *and* above ours and the count keeps growing, so do not assume a position in the log. Its tree is **red**: a committed test imports `boardwatch.profile_bundle.secret_scan`, which exists only as an untracked file, so those commits pass on this machine and fail in a clean checkout. Pushing publishes someone else's in-flight work and a red `main`. Not ours to fix — hand the finding back | Mit |
| **P3 Slice 5 — LLM economics** | Substantial and design-heavy; use a fresh context window | P3 |
| **P3 item 8 — cross-OS two-writer WAL test** | A same-OS test proves nothing; needs a Docker-Linux-container + macOS-host harness. The documented-stance half shipped (D-041) | P3 |
| **A `SIGKILL`ed run leaves a dangling `runs` row** | `try/finally` covers exceptions and Ctrl-C, not SIGKILL. Largely drained by the age-based reaper (D-046); a heartbeat-column reaper is the deferred correct fix | P3 |

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
- **Only 404/410 withholds a lead, and only from the URL asked about; everything else is served**
  (D-111, narrowed by D-113). Timeout, 403, 5xx, a redirect, and a NULL URL are all `unknown`. 403 is not hypothetical — a live Pinterest posting answers 403 to an
  unfamiliar user agent, so treating it as gone would silently blacklist whole employers.
- **"Gone" means the URL asked about said so, not somewhere it was redirected to** (D-113). `Fetcher` sets
  `follow_redirects=True`, so a `302 → 404` chain arrives as a bare 404; `FetchFailure.redirected` is what
  distinguishes them, and a redirected gone-status is `unknown` under `refetch_gone_after_redirect`.
  The count is a **subset of `unknown`** and is emitted on the run line and in the artifact: a
  gone-after-redirect count that climbs while `dead` stays 0 is the detector being disarmed, not a
  healthy corpus. `tests/unit/test_liveness_prober.py` is the only module driving the real `Fetcher`
  (the pipeline suite's probers are fakes, which cannot redirect), so the two redirect cases there are
  the only coverage of this — do not delete them as duplicates of the core-module tests.
- **A `Liveness` verdict must be the one its signal carries** (D-113). `SIGNAL_VERDICTS` is total and
  `__post_init__` enforces it, so `dead` is reachable through `refetch_gone` and nothing else. Constructing
  a contradictory pair raises `ContradictoryLiveness` rather than silently withholding a posting.
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
- **A check that cannot fire is deleted, not shipped.** Gate A found design-named validation rows whose
  condition the Pydantic models already refuse at parse time. Implementing them anyway produces code that
  can never run — the same defect class as a never-resolving eligibility rule reporting 100% abstain. Remove
  the duplicate and write a test that says **where** the guarantee actually lands, so the spec row does not
  merely look uncovered (D-115).
- **A generalization exception entry is repo-wide, and the shape tests assume the tables are empty.**
  Adding two `HOME_PATH_EXCEPTIONS` rows to satisfy a fixture broke 31 tests, because the checker reports an
  unused entry as stale against every synthetic tree. The convention is to **assemble the offending literal
  at runtime** so it never exists on disk — the rule protects the repo's bytes, not the checker's opinion.
- **Measure the spec's premise before building it.** D-098 priced a deferral with the wrong subsystem's
  figures (D-105); D-111 found PROGRAM item 6's authoritative signal was 0-for-11 on the real corpus and
  structurally unable to reach the column it reads. A spec written against a different codebase's data is
  a hypothesis, not a requirement.
