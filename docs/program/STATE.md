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
authority. **Rewrite it, never prepend to it.** Keep it near 170 lines. Git has every previous version.

---

## Current standing

**Two tracks are live.** The **P0–P7 replacement program** is at P6, whose build is complete and whose
last two gate clauses need the system *run*. The **canonical career-profile bundle (Gate A)** is
code-complete on one integration branch and green, but **not met** — it owes reviews and one document.

### The P0–P7 program

**P6's build is COMPLETE — all six items — and its commits are PUSHED.** Detail in D-095, D-103…D-107,
D-110 (ledger), D-111 + D-113 (applied state, liveness). Schema head is **`p6_job_dispositions`**.
**Read D-110 before touching the ledger, D-111 and D-113 before touching liveness.** The one most likely
to be undone by accident: `Fetcher` sets `follow_redirects=True`, so a `302 → 404` chain arrives as a bare
404, and `FetchFailure.redirected` is the only thing distinguishing a posting that is gone from one whose
old link points at a dead path on a new host.

**P6 has nothing left to BUILD — its last two gate clauses need the system RUN**: duplicate leakage needs
7 days of runs (the window must start after D-110, which changed which callers advance the queue), and
"0 dead postings" needs a real run whose leads are actually probed. Accumulating those runs is gated on
Mit's `resume.yaml` fix below.

### Gate A — code-complete, gate green, NOT met

**The integration branch `t18-cli` HEAD `a64e6fa` carries all nineteen Gate A slices, and its
`make check` is GREEN: exit 0 · 5,906 passed · 1 deselected · 95.63% · 16m42s · Python 3.13.12.**
Evidence and the four facts binding that log to that sha: `.agent/GATE-A-FINAL-GATE.md` (D-135).
This retires the branch-by-branch table that stood here — every slice's code is in one place and
gated together. `t18-cli` is local only; **nothing on this track is pushed.**

Containment verified with `git merge-base --is-ancestor`, not from any note: `t13-followup`,
`t14-storage`, `t15-rebase`, `t16-promotion` **plus its 11-commit fix round** (`735dfe7`),
`t16-validate-quarantine`, `t17-schema`, T18 **plus its 10-commit fix round** (`c7d88b4`), and
`t19-contract`. **`main` is NOT an ancestor of `a64e6fa`** — `main` holds three docs-only commits the
gate did not see, which owe only `generalization` + `index-check` under D-116. All Gate A **code** is
inside the gate. `t19-authoring-guide` is an alias for an already-merged ancestor: **no commits, no
stash, nothing lost** — safe to delete.

**A green gate is not a review.** Still owed, and the reason Gate A is not met:

1. **T18's fix round owes an INDEPENDENT REVIEW.** D-126's stopping rule is not satisfied — **both**
   T18 lenses found a qualifying BLOCKING. T14/T15's and T16's fix rounds were each independently
   reviewed and **every one found something**.
2. **The authoring guide is entirely unwritten** — `docs/profile-bundle-authoring.md` does not exist
   (T19 Step 2, with `docs/configuration.md` and `README.md`). **It is blocked on open question 3
   below**, because §19's authoring flow is exactly what that question is about.
3. **T19 owes a separate docs-only reviewer**, which must check the Gate A claim itself.

**`.agent/NEXT-SESSION-GATE-A.md` remains the ordered plan for items 2–4 of its own owed list**; its
item 1 (read the gate result) is done and superseded by `.agent/GATE-A-FINAL-GATE.md`. Start any Gate A
session with `git worktree prune`. Worktrees live under `../bw-wt/` (`integrate`, `t18fix`, `guide`);
`docs/superpowers/` holds the design and plan, is **untracked**, and must be copied into any new worktree.

**Gate A is NOT met and Gate B stays prohibited until Gate A is implemented AND independently
reviewed.** `origin/main` is `88c5857` (T11); the published 0.3.0 wheel (`dc1ffec`) is T1–T10 —
verified with `git cat-file -e` and `git ls-tree`, not from a note (D-133 corrects D-130's escalation
to "T1–T12", which was wrong). **Everything from T12 onward is unpushed.**

**Next action, in order:** (1) review T18's fix round — one lens on the tailor boundary; (2) get Mit's
ruling on `evidence_link_asymmetry`, then write the authoring guide and dispatch its docs-only reviewer;
(3) start accumulating real daily runs; (4) P2 item 8 or P3 slice 5, both owner-gated, both wanting
their own context window.

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
| P6 Liveness + dedup | **BUILD COMPLETE — all six items**, all three slices merged, reviewed and pushed (D-110, D-111, D-113) | **NOT MET — 2 of 4 clauses met**, below |
| 14-day acceptance | not started | — |
| P7 Breadth | not started | — |
| *Gate A (parallel track)* | *code-complete on `t18-cli`, gate green* | ***NOT MET*** — *see above; has moved no program gate* |

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

**3. `evidence_link_asymmetry` is now a permanent outcome of every successful `add-evidence`.** An
`owner_attestation` must support a fact, §12 requires that fact to cite it back, and `add_evidence` only
appends to the evidence document — so a capture supporting a fact *always* leaves that finding until the
owner edits the fact. **§19's authoring flow therefore cannot end clean on this shape**, which is why the
authoring guide is blocked on this. Same class as the BLOCKING T18's fix round just closed: a correct
operation leaving a standing error. Neither T18 reviewer raised it (lens A hand-fixed it in a probe and
moved on).

*(A fourth — whether docs-only commits owe a full `make check` — was **resolved** by D-116.)*

---

## Live blockers and carried gaps

| Item | Detail | Owner |
|---|---|---|
| **T18's fix round is unreviewed** | The one thing standing between Gate A and "implemented and independently reviewed". D-126's stopping rule is explicitly not satisfied. Brief two lenses, one on the tailor boundary. | Gate A |
| **The authoring guide is unwritten** | Blocked on open question 3, not on effort. Under D-116 it owes only `generalization` + `index-check`: `.md` is outside `DATA_SUFFIXES` and no test reads a real repo doc — both measured. | Gate A / Mit |
| **T16's two BLOCKINGs have fixes committed, inside the green gate** | The `promotion.py:426` `if not quarantined:` guard that let one quarantined blob disable the *entire* parent digest recomputation, and the symlinked draft root promoting outside content into an immutable revision. Both closed by T16's 11-commit fix round (`735dfe7`), which is in `a64e6fa`, and that fix round was independently reviewed. Do not re-open from the old blocker text — read D-132. | closed |
| **Three `resume.yaml` bullets exceed the 220-char layout gate** | Forces an untailored-master degrade on every posting, which is what blocks accumulating real runs. The file also lacks Knowledge Forge, has stale `skill_groups`, and an empty extracurricular block. **Mit pins `resume_max_pages=1` — do not advise setting it to 2.** Mit deprioritized this 2026-08-11; do not gate other work behind it. | Mit (content) |
| **The 03:10 launchd job re-fires a task that shipped 209 commits ago** | `com.mitsheth.boardwatch-p6.plist` is a *daily* `StartCalendarInterval` job carrying the *one-shot* "execute P6 Slice 1" prompt, asserting `main` at `fb0386a`. It has now misfired **twice** — 2026-08-11 and 2026-08-12 (D-123, D-135). Benign and self-detecting in five read-only commands, **not** self-correcting, and it spends a real usage window each night. Fix: `launchctl bootout gui/$UID/com.mitsheth.boardwatch-p6`, or repoint `~/.claude/scheduled/p6-slice1-run.sh` at a fresh prompt. | Mit (automation) |
| **No local pre-push check for the three CI-only jobs** | `gitleaks`, `perf` and `generalization` run in CI and not under `make check`; `gitleaks` is not installed by project tooling. `gitleaks git --log-opts=origin/main..HEAD` is the cheap mitigation (D-117) | open |
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
  `head`/`tail` (SIGPIPE gives a false negative — observed live giving a false `EXIT=0`), end a
  backgrounded gate with `exit $ec`. `All checks passed!` is the *lint* step and appears while pytest is
  still running; only `GATE_EXIT` and the pytest summary are the verdict.
- **Green locally ≠ green CI** (D-117). `gitleaks`, `perf` and `generalization` are CI jobs `make check` never
  runs. `gitleaks git --log-opts=origin/main..HEAD` before a push is the cheap mitigation, not yet wired in.
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
- **`AGENTS.md` records no phase standing, test count or coverage figure, on purpose.** This file is the only
  source of standing. `.agent/` and `.superpowers/` are gitignored working material; `CHANGELOG.md` is
  authoritative for what shipped. Review records that must outlive a session go in `.agent/`.
- **A finding's tier belongs to the OPERATION, not the code alone** (D-134). `tier_of()` is the catalog
  default; `outcome_with` reading `finding.tier` is correct. Every call-site override must carry a comment
  naming the operation-specific reason.

**Gate A internals**

- **`_root`, `.` and `..` are ESCAPED by the encoder, never refused** (`%5Froot`, `%2E`, `%2E.`). Refusing
  makes a legitimate document unenumerable. `normalize_locator` keeps a `.`/`..` guard for raw *paths*, where
  the same spelling means traversal (D-120, D-125).
- **The `_root` reservation is global on purpose**, and **`is_normalized_locator` is deliberately WEAKER than
  `emits_locator`** — it also serves owner-authored scope locators, so tightening it strands every legitimate
  selected scope.
- **The uniform JSON envelope on all twelve T18 commands is RIGHT** — both lenses upheld it independently. The
  **design text (§19) is what is wrong**; T19 amends it. `report_json`/`report_text` were production-dead and
  are deleted.
- **`METRIC_REVIEW_MISSING` is DELETED and metrics get no review interval** — a metric's freshness is its
  `reviewed_at` date alone (D-115, Mit's ruling). §20.6's clause binding an owner's approval to promoted
  content must fire for **every** revision, not only the first.
- **`Path.resolve()` on a symlink loop differs across the interpreters CI runs** — 3.11/3.12 raise
  `RuntimeError`, **3.13 returns the loop's own path**, which satisfies an equality check and admits the
  escape. Confinement therefore refuses on `is_symlink()`. **Keep a worktree on 3.13** — free cross-version
  coverage. `uv run --python X` inside the repo root **silently replaces `.venv`**; repair with
  `uv venv --clear --python 3.12 && uv sync --reinstall --all-groups`.
- **A FIFO in place of a bundle document still hangs `validate --draft` and `promote` forever** — the third
  site of that class, upstream of T18. Recorded, not chased.
- **Import fixtures as `from tests.<package>.conftest import ...`, never bare `from conftest import`.** A bare
  import binds whichever `conftest.py` loaded first — under the full suite, `tests/unit/conftest.py`. This
  shipped in T15 and survived two lenses and a fix round; it is invisible to any narrow run.

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

**The live store**

- **The live store has NOT had Slice 2 applied**, and that is a standing fact, not a to-do. Migrated and
  backfilled for Slice 1 only (head `p6_posting_identities`, 117,254 identity rows, `identities verify` exit
  0). The cheap read-only proof: **no `job_dispositions` table**, and `postings` 24,073 against
  `count(distinct job_id)` **24,073 — exactly 1:1**, where a regrouped store would read 23,887.
  `identities regroup` would move 186 postings onto 147 canonical jobs and needs the `p6_job_dispositions`
  migration first; **Mit declined it on 2026-08-10** — not blocked, just not now. A 769 MB backup sits beside it.
- **Not demonstrated on real data:** the ledger end to end, and the liveness probe against real leads. A
  `boardwatch top 5` against the 23,455-posting copy ran past 20 minutes and was stopped — it pays for
  `run_preflight` + `run_eligibility` over the whole corpus. Both are mutation-checked by tests; neither has
  run at corpus scale.
- **0.3.0 is PUBLISHED (D-119)** — PyPI, GHCR (`amd64` + `arm64`) and GitHub Releases, verified through three
  paths independent of the workflow's own report. `v0.3.0` is a **lightweight** tag on `dc1ffec`, like every
  prior tag. It **ships Gate A inside it, deliberately** — the wheel carries the whole `profile_bundle`
  package. **Mit was offered "hold until Gate A is reviewed" twice and declined both times.** The basis holds
  because the package is **inert**: no CLI command, no bundle-to-`Resume` bridge, a test asserts both
  directions. Publishing changed the release, **not** the review's standing.

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
- `bwd` lives in gitignored `.agent/bin/bw-daily`, so its `top --no-record` fix is local to this machine.
- **Live urgency.** `STAGE1_ONLY=1` is active in job-apps' launchd plist; its 08:30 run stops after discovery.
  Nothing is generating Mit's résumés daily right now.

---

## Process lessons this program paid real time for

Only what `CLAUDE.md` does not already say.

- **Commit before EVERY mutation round, not once before you start.** The `git checkout` that reverts a
  mutation destroys any uncommitted edit. Fired three times. Clear `__pycache__` too — stale bytecode fakes
  both a CAUGHT and a spurious failure. Derive the mutation from the test's CLAIM, not the implementation.
  **Check the driver for byte-identical duplicates before quoting a count** (D-122 reported 13 when 12 were
  distinct; the driver now aborts).
- **A test derived from a constant agrees with itself.** Mutating `_MAX_HEADING_LEVEL` survived because every
  assertion about the cap read the same constant it was checking (D-125). Pin the outside fact.
- **A detector must be confirmed to FIRE** — mutate the thing it watches and watch it go red (D-116). Its
  mirror image: **a check that cannot fire is deleted, not shipped** (D-115) — write a test saying *where* the
  guarantee actually lands. A fix elsewhere can make a live check dead: escaping `.`/`..` in the encoder
  killed a guard that had been firing until then (D-125).
- **Two reviewers with different LENSES beat two sequential rounds** (D-125). Reviewers that RUN the code find
  what reviewers that read it cannot (D-111). **Verify a finding's premise before ruling on it, including a
  reviewer's** — lens B's count and extent were both wrong (D-134).
- **Look for the same thing under two names, and for a deletion that is really a rename.** Two byte-identical
  `OSError` helpers; a test `main` deleted that a branch kept; `main` fixing the FIFO in `rebase._tree_contents`
  while T16 fixed the same defect in the `storage.py` copy it had MOVED. **Two independently-green branches
  rewrote the same guard and neither was a superset** — resolve as the union, not by picking one.
- **Resolving conflict markers is not resolving the conflict** — files sit at `UU` until an explicit `git add`,
  which a passing test run will not tell you. **Sweep every `quoted_yaml(` call** in any branch being merged;
  a line-based grep gives false positives, only the suite settles it.
- **`git add -A` and `git add -u` both sweep another writer's work.** Stage explicit paths, always.
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
