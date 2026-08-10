# PROGRAM STATE — read this first

> The one file a fresh session with zero memory reads to know where the program stands.
> **If it disagrees with the repo, the repo wins** — fix this file and note the correction in
> `DECISIONS.md`. Plan: `PROGRAM.md`. Numbers: `METRICS.md`. Rationale: `DECISIONS.md`. What shipped:
> `CHANGELOG.md`.

**This file states only what is true now.** It carries no commit sha and no commit count on purpose — both
go stale inside a single session, and a cold session following the ritual hits the disagreement on its first
check (D-017). `git log --oneline -1` is the authority.

**Rewritten 2026-08-10**, from 1,387 lines to this. It had accumulated ten sessions of narrative —
per-session retrospectives, frozen snapshots of resolved questions, superseded headers stacked on top of one
another — which is *history*, and history belongs in `DECISIONS.md` / `CHANGELOG.md` / `METRICS.md`, all of
which already held it. Nothing had to be moved out first. The previous version is in git if you want the
prose. CLAUDE.md's rule is the reason: a file that narrates its own history stops being read.

---

## Current standing

**P6 Slice 2 is BUILT** — the durable decision ledger, its drain, and job regrouping (`PROGRAM.md` §3.P6
item 4). `make check` **exit 0**: 3822 passed, 1 deselected, `generalization: OK`, ruff and `mypy --strict`
clean, 4m42s, in a detached worktree pinned to the commit. Decisions **D-103 … D-107**.

**It is committed to local `main` and deliberately NOT pushed, and it has had no independent review.**
Seven commits sit ahead of `origin/main`. Slice 1, a comparable checkpoint, went to a branch and merged only
after a three-reviewer fresh-context review (D-095) plus Mit's explicit authorization; this slice was
committed straight to `main` under standing "commit freely" permission, which is a process divergence worth
naming rather than discovering. **The owed step is a fresh-context whole-branch review before pushing** —
`origin/main..main` is the range. Standing permission to push is conditional on the work being both
confident *and* reviewed; only the first holds.

Schema head is **`p6_job_dispositions`**.

**Next action: P6 Slice 3** — applied-state suppression (`PROGRAM.md` §3.P6 item 5) and liveness (item 6).
Liveness is what the remaining "0 dead postings" gate clause needs. Two things to know before planning it:
item 5 has **no live population** (`applications` = 0 rows), and item 6's is tiny — 3 open postings contain a
closed phrase, 0 are stale beyond 30 days. Size the slice to that reality rather than to the spec's ambition.

**The live store has NOT had Slice 2 applied to it.** It is migrated and backfilled for Slice 1 (head
`p6_posting_identities`, 117,254 identity rows at `p6.2`, `identities verify` exit 0, 147 groups / 186
surplus rows / 0.79%). Slice 2 was verified on an **isolated copy**, which is why the live figures below are
Slice 1's. Running `boardwatch identities regroup` against the live store is a deliberate, still-unrun step:
it moves 186 postings onto 147 canonical jobs.

**What was NOT demonstrated on real data:** the ledger's own end-to-end behaviour. A `boardwatch top 5`
against the 23,455-posting copy ran past 20 minutes without finishing and was stopped — it pays for
`run_preflight` + `run_eligibility` over the whole corpus, the same reason Slice 1's live top-20 smoke never
completed either. The queue-advance behaviour is proven by
`tests/pipeline/test_ledger_advances_the_queue.py` (mutation-checked) and the *regrouping* half was verified
on the real copy; the display path at corpus scale was not. Re-run it if you want that exercised. A pre-migration backup sits beside the store
(`boardwatch.db.pre-p6-backup-20260810`, 769 MB); the disk pressure that made deleting it worth considering
has resolved (root at 39%, 18 GiB free), so it was left alone.

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
| P6 Liveness + dedup | **Slices 1 and 2 merged.** Slice 3 (items 5, 6) not started | **NOT MET — 2 of 4 clauses met**, below |
| 14-day acceptance | not started | — |
| P7 Breadth | not started | — |

### Gate P6, clause by clause

| Clause | Standing |
|---|---|
| Duplicate leakage measured over 7 days, ≤ 5% | **NOT met — now genuinely measurable.** Slice 1 made `unique` a number; Slice 2 (D-105) stopped a single newly-discovered posting from silently disabling suppression, without which it was `None` on essentially every real run. Needs 7 days of runs |
| **0** dead postings reaching the lead list | **NOT met, not buildable yet** — needs liveness, which is Slice 3 |
| A deliberately-injected hash-collision test | **MET** (D-100) — `test_string_verify_blocks_suppression_when_bodies_diverge` forges `identity_key` equality over divergent bodies and the group is refused. A test, not a measurement, so met outright |
| Audit of 20 sampled suppressions | **MET** (D-101) — 20/20 genuine, zero false positives, 13 employers, sampled deterministically so it can be re-run. Slice 2 adds **no new precision evidence** |

---

## Open questions — Mit's, not to be resolved by fiat

**1. Should `pipeline/runner.py` keep swallowing a funnel-write failure into a printed warning?** Raised by
D-076 and deliberately left open. It once turned a renderer `TypeError` into a silent half-written artifact
pair — `funnel-<id>.json` written, `.md` missing, run still exit 0. The crash is fixed; the swallow will hide
the next renderer bug identically. It is also defensible as a fail-open — do not kill a finished run over a
report — and CLAUDE.md says the fail-safe direction is chosen per gate and these legitimately differ.
Options: leave it; make it fatal; keep it non-fatal but surface it in the run's `errors` so `verify`/`doctor`
can see the artifact is incomplete.

**2. Should any family other than `work_auth` default to `blocker` severity** (e.g. `clearance`)? Owner-gated
since D-035, unchanged by everything since.

---

## Live blockers and carried gaps

| Item | Detail | Owner |
|---|---|---|
| **Three `resume.yaml` bullets exceed the 220-char layout gate** | Forces an untailored-master degrade on every posting. The file also lacks Knowledge Forge, has stale `skill_groups`, and an empty extracurricular block. **Mit pins `resume_max_pages=1` — do not advise setting it to 2.** | Mit (content) |
| **P2 item 8 — the onboarding gatherer** | The thing that would make the field tier fire for anyone. D-054 forbids us authoring non-tech field content, so it must be gathered per user. Needs its own brainstorm | owner-gated |
| **P3 Slice 5 — LLM economics** | Substantial and design-heavy; use a fresh context window | P3 |
| **P3 item 8 — cross-OS two-writer WAL test** | A same-OS test proves nothing; needs a Docker-Linux-container + macOS-host harness. The documented-stance half shipped (D-041) | P3 |
| **A `SIGKILL`ed run leaves a dangling `runs` row** | `try/finally` covers exceptions and Ctrl-C, not SIGKILL. Largely drained by the age-based reaper (D-046); a heartbeat-column reaper is the deferred correct fix | P3 |
| **CI never acquires a runner** | Runs queue forever unacquired; `gh workflow run ci` returns 422 (the workflow has no `workflow_dispatch` trigger). **Not a repo problem — do not re-diagnose it as a test or config failure.** Local `make check` is the authority. Check run `status`, never mere presence | GitHub |

---

## Standing facts a fresh session should not re-derive

- **`make check` is the only gate.** pytest + ruff + mypy green is *not* green — the generalization checker
  only runs under `make check`. Run it in a detached worktree pinned to a commit
  (`git worktree add --detach /tmp/bw-gate <sha>`) so editing the main tree cannot corrupt a run in flight,
  capture the real exit code, and **never** pipe it through `head`/`tail` (SIGPIPE gives a false negative).
  End a backgrounded gate with `exit $ec`. For a docs-only change, `make generalization` alone (~1 s) suffices.
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
- **The résumé renderer is `tectonic`** compiling Mit's real LaTeX template (`tailor/render/latex.py` +
  `render/templates/resume_base.tex`), not Typst — D-058 reversed the Typst choice and D-060 completed the
  swap. `doctor` probes for it. A `typst` binary happens to be on this machine; nothing in boardwatch calls it.
- **The tailoring architecture is already correct** — typed skeleton, plain-text-only model contract,
  Python-owns-markup, independent entailment judge. Do not rebuild it (`PROGRAM.md` §5.1).
- **`track` has never been used** — `applications` and `application_events` are both 0 rows. That is why P6
  item 5 has no live population, and why regrouping's tracked-job refusal is *latent* rather than unreachable
  (D-104).
- **`jobs` and `postings` are both 24,073, exactly 1:1** on the live store, because regrouping has not been
  applied there yet.
- **`hidden_duplicate == 0` is ambiguous; `hidden_handled == 0` is not.** The first can mean "dedup never
  ran"; the second is never completeness-gated, because a stored disposition records a decision already
  taken (D-106).
- **`_verify_quad` has never fired** (D-097). It re-runs the key's own normalizers, so it guards a SHA-256
  collision and staleness but not normalizer lossiness. **Never cite "string-verified" as precision evidence.**
- **D-072, the model-tier benchmark, is DEFERRED INDEFINITELY** (D-102). Not an owed item, not a next action,
  not blocking anything.
- **`.agent/` and `.superpowers/` are gitignored** working material, not a source of truth for released
  behaviour. `CHANGELOG.md` is authoritative for what shipped.
- **Live urgency.** `STAGE1_ONLY=1` is active in job-apps' launchd plist; its 08:30 run stops after
  discovery. Nothing is generating Mit's résumés daily right now.

---

## Process lessons this program paid real time for

- **A truncated grep is not a negative result.** One false claim survived four separate "finished" retraction
  passes and lived in six places; the pass that missed it piped grep through `head -30`.
- **A retraction commit reintroduces the defect class it cures**, so it needs its own review. Dispatch a
  **separate** docs-only reviewer for documentation written about already-reviewed code — they keep finding
  blockers in it.
- **Derive a test's mutation from its stated CLAIM, not from the implementation.** Commit before
  mutation-testing (`git checkout` discards uncommitted fixes) and clear `__pycache__` first, because stale
  bytecode fakes a CAUGHT.
- **A component's self-report is not verification.** Count the deliverable through a different path than the
  one that produced it — and re-grouping the same table a second way is *not* a different path (D-028).
- **A failed command is not a negative result.** Confirm a check actually ran before reading its silence as
  evidence.
- **A deferral justified by a number deserves re-checking when the design changes.** D-098 priced wiring the
  identity backfill into the pipeline using the wrong subsystem's figures, and the price turned out not to
  apply to the design that shipped (D-105).
