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
order: (1) start accumulating real daily runs, gated on Mit's `resume.yaml` fix below; (2) Gate A — T13
onward, with T12's independent review owed; (3) P2 item 8 or P3 slice 5, both owner-gated and both
wanting their own context window.

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

**A PARALLEL TRACK exists: the canonical career-profile bundle, Gate A — 12 of 19 slices built (D-115,
D-118, D-120).** Not a P0–P7 phase; it has moved no program gate. Its design and plan live **untracked** under
`docs/superpowers/` — read them there, and never work this track from a fresh worktree, where they vanish.
`src/boardwatch/profile_bundle/` holds the typed outcomes, restricted YAML loader, the closed 33-document
grammar, every record model, the JSON Schema export, a packaged synthetic example, an isolated canonical
serializer, the global record index, structural + referential + evidence + **semantic** validation, the
**effectiveness derivation**, the blob store, versioned secret scanning, owner-gate derivation and
append-only history, and now the four deterministic source adapters with candidate identity and import
validation. **Gate A is NOT met, T12 is NOT reviewed, and the bundle is wired to nothing** — no CLI command, and deliberately no bundle-to-`Resume`
bridge (a test asserts both directions). Its commits being on `origin/main` is **not** sign-off. **Gate B
stays prohibited until Gate A is implemented AND independently reviewed**; that review is owed.

**T1–T11 are implemented and independently reviewed. T12 has been REVIEWED THREE TIMES, all three
verdicts REWORK. Rounds one and two are fixed; round three is NOT started.** T12 (D-120)
is deterministic enumeration, candidate identity, and idempotent import — the four approved adapters, NFC
percent-encoded locators, the derived `source-record.<64hex>` and `candidate.<64hex>` IDs, predicate-
authorized value canonicalization, idempotent package merging, and the import validation layer. Its
`make check` exited 0 and 59 mutations were each caught — **and the review still found five BLOCKING
defects** (D-121), the worst of which left repository Markdown unimportable for any heading containing
a space. `ce0a8de` fixed those; the **re-review of that fix returned REWORK again** (D-122) with four
more BLOCKING findings — one created by the fix itself, two contracts that had never been enforced
anywhere, and one only partly closed. A verification agent added a fifth, and a docs reviewer showed
that one of the round-two declines rested on a false premise. All are fixed, with 20 distinct
mutations caught; gate exit 0, 5,200 tests, 95.40%.

**The third review (D-124) returned REWORK again: 4 BLOCKING + 1 SHOULD-FIX, all four in code written
to close round two.** The worst repeats round one's defect class exactly — `ROOT_SEGMENT` is not
reserved by the encoder, so a heading literally named `_root` shares a namespace with pre-heading
content, and round two's `_root` scope refusal makes that legitimate source unimportable. **The cause
is structural, not four bugs: the locator grammar restates the emitter instead of reading its
constants**, so it drifts on the first input no fixture contained. Read D-124 before touching
locators, and D-120 before touching identity derivation — the résumé adapter's stage order and `~N`
locator preservation are both load-bearing for stored IDs, and four checks were deleted there for
being unable to fire.

**Next slice is T13** — and it is **STARTED, uncommitted**: `src/boardwatch/profile_bundle/reports.py`
(222 lines, design §19–§21) and `tests/profile_bundle/test_profile_bundle_reports.py` (279 lines) sit
**untracked** in the working tree, written by a session that did not commit them. They are somebody
else's in-flight work: **stage explicit paths, never `git add -A`/`-u`**. Collection is unaffected —
5,200 of 5,201 tests collect with them present. T13 covers completeness, digest validation, ancestor
traversal, and deterministic reports. It
inherits the promoted-revision fixture T11 built and the digest primitives from T8 (`record_digest`,
`candidate_content_digest`, `candidate_digest_from_revision`, `source_scope_target_digest`,
`source_exclusion_target_digest`). Note that `validate_imports` and `imports_completeness` are deliberately
NOT exported from `validation/__init__.py` yet — T13 owns wiring them into the report layer.

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
| **T12 owes a THIRD round of fixes (D-124) — 4 BLOCKING, none started** | Three reviews, three REWORKs. Round three: `_root` is not reserved so a legitimate heading named `_root` is unimportable (round one's defect class, repeated); `emits_locator` accepts heading paths deeper than the six levels `_HEADING_RE` allows; the raw `~N` exception is adapter-blind so `synthetic~2` validates although only `synthetic%7E2` can be emitted; `portable_locator` accepts an embedded NUL. Plus the JSON-schema gap D-122 wrongly accepted. **Fix the cause — make the grammar read the emitter's constants — not the four instances.** Start in fresh context: both prior rounds were authored by the context that caused them. | next |
| **T13 is partially built on branch `t13-digest`, unmerged** | `reports.py` + `validation/digest.py` + the promoted-revision fixture (`promote_example_tree`, `promote_next_revision`); 70 targeted tests, ruff and `mypy --strict` clean, no full gate. `validation/completeness.py` and `validation/run.py` are not written. Two open rulings recorded in D-124's session metrics: `METRIC_REVIEW_MISSING` has no interval to be past and no way to be absent (delete-or-resolve under D-115, **needs Mit's call**), and `STALE_FACT` is ruled to mean the declared state while the computed condition is `EXPIRED_REVIEW`. | T13 |
| **The 03:10 launchd job re-fires a task that already shipped** | `com.mitsheth.boardwatch-p6.plist` is a *daily* `StartCalendarInterval` job carrying the *one-shot* "execute P6 Slice 1" prompt, which asserts `main` at `fb0386a` — now an ancestor 110 commits back. It misfired on 2026-08-11 and will misfire nightly. Benign and self-detecting (the session-start ritual catches it in a few read-only commands), **not** self-correcting. Fix: `launchctl bootout gui/$UID/com.mitsheth.boardwatch-p6`, or repoint `~/.claude/scheduled/p6-slice1-run.sh` at a fresh prompt (D-123) | Mit (automation) |
| **No local pre-push check for the three CI-only jobs** | `gitleaks`, `perf` and `generalization` run in CI and not under `make check`; `gitleaks` is not installed by project tooling. `gitleaks git --log-opts=origin/main..HEAD` is the cheap mitigation (D-117) | open |
| **Five Gate A fix commits are independently reviewed** | The current `origin/main` contains `1de10c7`, `20ff50c`, `8d32294`, `9d78450`, and `bbec2c0`; each exact diff and the untracked design correction were checked against the original findings with executable reproductions and negative controls. Their prior `make check` results were not used as sign-off. | complete |
| **The earlier partial-review findings are resolved or separately fixed** | Explicit tags, typed YAML codes, scalar allowlisting, predicate evidence routes, `legal_surfaces`, and dead-check removals were rechecked. The independent review also found and fixed the broad YAML-loader exception classification (`dfa655e`) and the Windows personal-path scan gap (`f166d18`). No BLOCKING or unresolved SHOULD-FIX findings remain. | review |
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
