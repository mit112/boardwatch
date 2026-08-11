# PROGRAM STATE — read this first

> The one file a fresh session with zero memory reads to know where the program stands.
> **If it disagrees with the repo, the repo wins** — fix this file and note the correction in
> `DECISIONS.md`. Plan: `PROGRAM.md`. Numbers: `METRICS.md`. Rationale: `DECISIONS.md`. What shipped:
> `CHANGELOG.md`.
>
> `DECISIONS.md` and `METRICS.md` each carry an **index spanning themselves and a closed archive**
> (`*-ARCHIVE.md`, D-108). Read the index, then the one range you need — never the whole file.

**This file states only what is true now**, and carries no commit sha or commit count on purpose — both go
stale inside a single session (D-017). `git log --oneline -1` and `git status --short --branch` are the
authority. **Rewrite it, never prepend to it**: it reached 1,386 lines by stacking superseded headers and
per-session retrospectives, which belong in `DECISIONS.md` / `CHANGELOG.md` / `METRICS.md`. Keep it near
170 lines. Git has every previous version.

---

## Current standing

**P6's build is COMPLETE — all six items — and the long-held commits are PUSHED.** Slices 1 and 2 were
merged and reviewed earlier (D-095, D-103…D-107, review D-110); Slice 3 is applied-state suppression
(item 5) and liveness (item 6), recorded as **D-111** and reviewed twice (D-113). Schema head is
**`p6_job_dispositions`**; Slice 3 added no migration.

**Read D-110 before touching the ledger, D-111 and D-113 before touching liveness.** D-113 is the one most
likely to be undone by accident: `Fetcher` sets `follow_redirects=True`, so a `302 → 404` chain arrives as a
bare 404, and `FetchFailure.redirected` is the only thing distinguishing a posting that is gone from one
whose old link points at a dead path on a new host.

**Next action: P6 has nothing left to BUILD — its last two gate clauses need the system RUN.** Duplicate
leakage needs 7 days of runs (the window must start after D-110, which changed which callers advance the
queue), and "0 dead postings" needs a real run whose leads are actually probed. So the useful work is, in
order: (1) start accumulating real daily runs, gated on Mit's `resume.yaml` fix below; (2) Gate A — finish
its review, then T11 onward; (3) P2 item 8 or P3 slice 5, both owner-gated and both wanting their own
context window.

**A green `make check` is NOT a green CI** (D-117). `gitleaks`, `perf` and `generalization` are separate CI
jobs `make check` never runs, and pushing turned `gitleaks` red for the first time in the project's history
with every local check green. This does not contradict "`make check` is the only gate" — that holds for *this
repo's own correctness*. Run `gitleaks git --log-opts=origin/main..HEAD` before pushing.

**0.3.0 is PUBLISHED (D-119)** — on PyPI, GHCR (`amd64` + `arm64`) and GitHub Releases, verified through
three paths independent of the workflow's own report. `v0.3.0` is a **lightweight** tag on `dc1ffec`,
matching `v0.1.0`/`v0.2.0`. Its precondition was `ci.yml` run `31442555052`: **12 of 12 green**, the first
fully green `ci.yml` in the project's history — which closed both the tectonic/poppler gap (D-114, 33
failures → 0) and the Windows cp1252 program-index defect.

**0.3.0 ships Gate A inside it, deliberately (D-119).** The wheel carries the whole `profile_bundle` package —
65 entries, 31 modules, 33 example YAML documents, 1 JSON Schema — and the `## [0.3.0]` section does not
enumerate them. **Mit was offered "hold until Gate A is reviewed" twice — once before the loader BLOCKERs were
known and once after — and declined both.** The basis held because the package is **inert**: no CLI command, no
bundle-to-`Resume` bridge, a test asserts both directions, and nothing in a shipped code path reaches it. It is
a defect in code that ships but never runs. **Publishing changed the release, not the review's standing** — the
review is still owed and Gate B is still prohibited.

**A PARALLEL TRACK exists: the canonical career-profile bundle, Gate A — 10 of 19 slices built (D-115,
D-118).** Not a P0–P7 phase; it has moved no program gate. Its design and plan live **untracked** under
`docs/superpowers/` — read them there, and never work this track from a fresh worktree, where they vanish.
`src/boardwatch/profile_bundle/` holds the typed outcomes, restricted YAML loader, the closed 33-document
grammar, every record model, the JSON Schema export, a packaged synthetic example, an isolated canonical
serializer, the global record index, structural + referential + evidence + **semantic** validation, the
**effectiveness derivation**, the blob store, and versioned secret scanning. **Gate A is NOT met, it is NOT
reviewed, and the bundle is wired to nothing** — no CLI command, and deliberately no bundle-to-`Resume`
bridge (a test asserts both directions). Its commits being on `origin/main` is **not** sign-off. **Gate B
stays prohibited until Gate A is implemented AND independently reviewed**; that review is owed.

**Next slice is T11, owner gates and append-only history** — and it needs something the previous ten did
not: **a promoted-revision fixture.** The packaged example is a revision-1 *draft* with `changes: []` and
`approvals: []`, and its manifest is a `DraftManifest`, so it can never be parsed as a promoted revision.
Every owner-gate trigger in §13 fires at promotion, not in a draft, where `owner_confirmed` and
`status: approved` are legitimately only *proposals*. So T11 must first build a revision manifest, one
change record and one stamp — work T13 and T16 need too, and worth doing once, deliberately, rather than
inside whichever slice trips over it first. The digest primitives it will call already exist from T8
(`record_digest`, `candidate_content_digest`, `candidate_digest_from_revision`,
`source_scope_target_digest`, `source_exclusion_target_digest`). Note also that `ApprovalEntry` already
refuses a wrong target kind and a wrong resulting state at parse time, so two of the plan's Step-1 failure
modes are D-115 cases, not checks.

**The live store has NOT had Slice 2 applied.** Migrated and backfilled for Slice 1 only (head
`p6_posting_identities`, 117,254 identity rows, `identities verify` exit 0, 147 groups / 186 surplus /
0.79%); Slice 2 was verified on an **isolated copy**. Re-verified read-only three times on 2026-08-10:
**no `job_dispositions` table**, `postings` 24,073 and `count(distinct job_id)` **24,073 — exactly 1:1**,
the cheap proof, since a regrouped store would read 23,887. `identities regroup` would move 186 postings
onto 147 canonical jobs and needs the `p6_job_dispositions` migration first; **Mit declined it on
2026-08-10** — not blocked, just not now. The 769 MB backup sits beside it.

**What has NOT been demonstrated on real data:** the ledger end to end, and the liveness probe against real
leads. A `boardwatch top 5` against the 23,455-posting copy ran past 20 minutes and was stopped — it pays
for `run_preflight` + `run_eligibility` over the whole corpus. Both are mutation-checked by tests; neither
has run at corpus scale.

**The closed-phrase catalog was NOT shipped, deliberately — not an omission to correct.** Providers assemble
`body_text` only from JSON-payload description fields and never see the rendered page, so page chrome cannot
reach that column. Measured **11 of 23,455** matches, **all false positives**; a high-precision catalog
matches **0**. The older "3 open postings contain a closed phrase" figure is **superseded**.

**One earlier review fix does not ship.** `bwd` lives in gitignored `.agent/bin/bw-daily`, so its
`top --no-record` fix is local to this machine; the shipped fix is the flag itself.

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
| P6 Liveness + dedup | **BUILD COMPLETE — all six items**, all three slices merged, reviewed and now pushed (D-110, D-111, D-113) | **NOT MET — 2 of 4 clauses met**, below |
| 14-day acceptance | not started | — |
| P7 Breadth | not started | — |

### Gate P6, clause by clause

| Clause | Standing |
|---|---|
| Duplicate leakage measured over 7 days, ≤ 5% | **NOT met — now genuinely measurable.** Slice 1 made `unique` a number; Slice 2 (D-105) stopped one newly-discovered posting from silently disabling suppression, without which it was `None` on essentially every real run. Needs 7 days of runs, and D-110 changed which callers advance the queue, so a window started before it is not comparable with one after |
| **0** dead postings reaching the lead list | **NOT met — but buildable and measurable**, which it was not before Slice 3. The check runs on every `boardwatch run`; meeting the clause needs a real run whose leads are probed. Recall is low **by design** — 7 of 8 known-dead Workday/Ashby URLs still answer 200 — so it supplements the scanner's `CLOSE_AFTER_MISSES = 2` rule and never replaces it |
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

*(The third question — whether docs-only commits owe a full `make check` — was **resolved** by D-116.)*

---

## Live blockers and carried gaps

| Item | Detail | Owner |
|---|---|---|
| **Three `resume.yaml` bullets exceed the 220-char layout gate** | Forces an untailored-master degrade on every posting, which is what blocks accumulating real runs. The file also lacks Knowledge Forge, has stale `skill_groups`, and an empty extracurricular block. **Mit pins `resume_max_pages=1` — do not advise setting it to 2.** | Mit (content) |
| **Gate A T1–T10's review is ~⅓ DONE and was stopped on usage grounds** | A 3-wide dispatch became **11 agents** through nesting; Mit stopped the remaining 7. **Completed:** the closed-catalog checks (9 catalogs and all 41 predicate rows × 14 columns match the design exactly, negative-controlled) and a full restricted-YAML-loader audit. **Still owed:** the code-running T10 pass, canonical identity vs §7, blobs + secret scanning, the dead-check sweep, the packaged-example audit, and a docs-only pass. Gate B stays prohibited; `origin/main` is not sign-off and neither is being published | review |
| **No local pre-push check for the three CI-only jobs** | `gitleaks`, `perf` and `generalization` run in CI and not under `make check`; `gitleaks` is not installed by project tooling. `gitleaks git --log-opts=origin/main..HEAD` is the cheap mitigation (D-117) | open |
| **The two YAML-loader BLOCKERs are FIXED but the fix is UNREVIEWED** | `compose_node` now refuses any event carrying an explicit `tag`, which closes both: the `!!bool`/`!!int`/`!!timestamp`/`!!omap` bypass that let **four byte-different spellings produce one `bundle_digest`**, and the raw builtins that escaped `load_documents`. Committed as `1de10c7` + `20ff50c` by a session that ended without pushing them; **gated green independently here — exit 0, 4,883 passed, 95.22%**, which also proves the tag refusal does not over-reject, since the packaged 33-document bundle still loads. Both commits have **empty bodies**, against convention. Two observations, neither blocking: (1) the catch-all `except Exception` in `load_yaml_bytes` relabels *our own* internal defects as the user's "invalid YAML", which is the wrong attribution even if fail-safe at a parse boundary; (2) BLOCKER 2's documented trigger (`!!bool y` -> `KeyError`) is now **unreachable**, because the tag is refused before construction — so that clause is exercised only by monkeypatching `yaml.load_all`, which is a D-115 question worth asking. The reproduction in `METRICS.md` is correspondingly stale for that route | Gate A review |
| **Three MAJORs and six MINORs also open from the partial review** | Chief among them: §10.4's "every legal verification basis must be backed by its corresponding evidence class" is unvalidated at catalog level (`models/policy.py:124-171`), so a tenant-authored predicate row can declare an unreachable evidence route; `IssueCode.INVALID_YAML` is **permanently dead** because one exception type covers 8+ violations classified by message text; and out-of-contract scalars use a 2-pattern blocklist where §20.1 implies an allowlist (unquoted `2026-08` and `'2026-08'` reach the same digest). Full tables in `METRICS.md`'s T10 record. **None fixed: batched behind one `make check` rather than ~7.5 min per finding** | Gate A |
| **P2 item 8 — the onboarding gatherer** | The thing that would make the field tier fire for anyone. D-054 forbids us authoring non-tech field content, so it must be gathered per user. Needs its own brainstorm | owner-gated |
| **P3 Slice 5 — LLM economics** | Substantial and design-heavy; use a fresh context window | P3 |
| **P3 item 8 — cross-OS two-writer WAL test** | A same-OS test proves nothing; needs a Docker-Linux-container + macOS-host harness. The documented-stance half shipped (D-041) | P3 |
| **A `SIGKILL`ed run leaves a dangling `runs` row** | `try/finally` covers exceptions and Ctrl-C, not SIGKILL. Largely drained by the age-based reaper (D-046); a heartbeat-column reaper is the deferred correct fix | P3 |

---

## Standing facts a fresh session should not re-derive

Claims only — the reasoning is in the cited decision, which is the point of the archive split. Read the
decision before changing the behaviour it describes.

**Gates and process**

- **A docs-only commit owes `make generalization index-check`; anything else owes full `make check`** (D-116,
  resolving D-014). The boundary is the file extension. **Void if a new test ever reads a `docs/` file.**
- **`make check` is the only gate for this repo's correctness** — pytest + ruff + mypy green is *not* green.
  Run it in a **detached worktree pinned to a sha**, capture the real exit code, never pipe it through
  `head`/`tail` (SIGPIPE gives a false negative), end a backgrounded gate with `exit $ec`.
- **Green locally ≠ green CI** (D-117). `gitleaks`, `perf` and `generalization` are CI jobs `make check` never
  runs. `gitleaks git --log-opts=origin/main..HEAD` before a push is the cheap mitigation, not yet wired in.
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
- **`AGENTS.md` records no phase standing, test count or coverage figure, on purpose.** This file is the only
  source of standing. `.agent/` and `.superpowers/` are gitignored working material; `CHANGELOG.md` is
  authoritative for what shipped.

**Liveness and the ledger**

- **Only a caller that DELIVERS a lead may consume the queue** (D-110). `eligibility gate request` and the
  pipeline pass `record_surfaced=False`; `top --no-record` is the operator's opt-out. The pipeline writes all
  three ledger tiers *after* the tailor loop. Do not move the `seen` write back into the ranker.
- **Liveness is never cached, and "never" includes `postings.status`** (D-111). One 404 from a flaky CDN would
  otherwise retire a live requisition **irreversibly**. That column belongs to the scanner's
  `CLOSE_AFTER_MISSES = 2` rule, which works: 0 open postings are stale beyond 7 days.
- **Only 404/410 withholds a lead, and only from the URL asked about** (D-111, D-113). Timeout, 403, 5xx, a
  redirect and a NULL URL are all `unknown`. A live Pinterest posting answers 403 to an unfamiliar user agent.
- **"Gone" means the URL asked about said so, not where it redirected** (D-113). `refetch_gone_after_redirect`
  is a **subset of `unknown`**, on the run line and in the artifact: that count climbing while `dead` stays 0
  is the detector **disarmed**, not a healthy corpus. `tests/unit/test_liveness_prober.py` is the only module
  driving the real `Fetcher` — its two redirect cases are the sole coverage; do not delete them as duplicates.
- **A `Liveness` verdict must be the one its signal carries** (D-113) — `dead` is reachable through
  `refetch_gone` and nothing else.
- **An unprobed run reports liveness as UNMEASURED, never 0 dead** (D-111). `run --no-check-liveness` opts out.
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

**Environment**

- Neither `python` nor `boardwatch` is on PATH — always `uv run …`.
- No `__init__.py` under `tests/`, so test module basenames must be globally unique or collection aborts.
  `make check` runs mypy on `src` and `tools` only, ruff on everything.
- **A migration must never import a live catalog into its CHECK constraint** — it changes the constraint
  retroactively and diverges a fresh database from a migrated one. `tables.py` may (that is metadata, not
  history). Name constraints with `op.f()` or `test_migrations_match_metadata` sees permanent drift.
- **The résumé renderer is `tectonic`** compiling Mit's real LaTeX template, **not Typst** (D-058/D-060). A
  `typst` binary exists on this machine; nothing calls it. The tailoring architecture is already correct.
- **D-072, the model-tier benchmark, is DEFERRED INDEFINITELY** (D-102) — not owed, not blocking.
- **Live urgency.** `STAGE1_ONLY=1` is active in job-apps' launchd plist; its 08:30 run stops after discovery.
  Nothing is generating Mit's résumés daily right now.

---

## Process lessons this program paid real time for

Only what `CLAUDE.md` does not already say.

- **Commit before EVERY mutation round, not once before you start.** The `git checkout` that reverts a
  mutation destroys any uncommitted edit. Fired three times. Clear `__pycache__` too — stale bytecode fakes
  both a CAUGHT and a spurious failure. Derive the mutation from the test's CLAIM, not the implementation.
- **A detector must be confirmed to FIRE** — mutate the thing it watches and watch it go red (D-116). Its
  mirror image: **a check that cannot fire is deleted, not shipped** (D-115) — write a test saying *where* the
  guarantee actually lands, so the spec row does not merely look uncovered.
- **`git add -A` and `git add -u` both sweep another writer's work.** `-u` feels safer because it cannot take
  untracked files, which is exactly why it is easy to forget it takes *every* tracked modification in the
  tree. Stage explicit paths, always.
- **When two sessions share a clone, a position in `git log` proves neither authorship nor order.** Commits
  land above *and* below yours. Push an explicit sha (`git push origin <sha>:main`) so a concurrent commit
  cannot ride along un-gated.
- **Reviewers that RUN the code find what reviewers that read it cannot.** Both of D-111's BLOCKERs were
  invisible to reading and obvious to one pipeline execution. Dispatch a **separate** docs-only reviewer too.
- **Measure the spec's premise before building it.** D-098 priced a deferral with the wrong subsystem's
  figures (D-105); D-111 found PROGRAM item 6's authoritative signal was 0-for-11 on the real corpus and
  structurally unable to reach the column it reads. A spec written against another codebase's data is a
  hypothesis, not a requirement.
