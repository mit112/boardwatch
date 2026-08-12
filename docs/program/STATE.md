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

**P6's build is COMPLETE — all six items — and its commits are PUSHED.** Detail in D-095, D-103…D-107,
D-110 (ledger), D-111 + D-113 (applied state, liveness). Schema head is **`p6_job_dispositions`**.

**Read D-110 before touching the ledger, D-111 and D-113 before touching liveness.** The one most likely
to be undone by accident: `Fetcher` sets `follow_redirects=True`, so a `302 → 404` chain arrives as a bare
404, and `FetchFailure.redirected` is the only thing distinguishing a posting that is gone from one whose
old link points at a dead path on a new host.

**P6 has nothing left to BUILD — its last two gate clauses need the system RUN**: duplicate leakage needs
7 days of runs (the window must start after D-110, which changed which callers advance the queue), and
"0 dead postings" needs a real run whose leads are actually probed.

**Next action, in order:** (1) finish Gate A — T16 is in flight, then T18 and T19; (2) start accumulating
real daily runs, gated on Mit's `resume.yaml` fix below; (3) P2 item 8 or P3 slice 5, both owner-gated and
both wanting their own context window.

### Gate A branch table — where every unmerged slice stands (2026-08-11)

**No sha here is `main`'s** — `git log --oneline -1` is the authority for
that (D-017). Every branch is local; `docs/superpowers/` holds
the design and plan and is untracked — copy it into any worktree you create.

| Branch | Head | Stands where |
|---|---|---|
| `t13-followup` | — | **MERGED** to main at `b87fa06`, gate exit 0 · 5,436 passed · 95.64%. Branch retained but done. |
| `t14-storage` | **merged** | **MERGED** to main at `aff1dc0`. Round-2 review found 1 BLOCKING + 4 SHOULD-FIX (REWORK); fixed in 5 commits, one per finding. Gate **exit 0 · 5,534 passed · 95.73% · 11m54s**. Detail in D-128. Its fix round is now **independently reviewed** (REWORK): the blocking fix genuinely closes the escape at every depth and keeps a symlinked bundle root allowed, but it regressed a symlink loop into an uncaught `RuntimeError` and admits a FIFO. |
| `t15-rebase` | **merged** | **MERGED** to main at `f74be0e`. Two concurrent lenses, both REWORK: 6 distinct BLOCKING + 6 SHOULD-FIX, none covered by its own 54 green tests. Fixed in 12 commits; two design departures ruled in D-129. Branch gate **exit 0 · 5,611 passed · 95.83%**. Detail in D-128. Its fix round is now **independently reviewed** (REWORK): five of the six blocking fixes hold under fresh adversarial probes, the sixth — the append-only ledger merge — is closed on one arm only (blocker table). |
| `t16-promotion` | 4 commits on `main` | **BUILT (all 9 plan steps) and gated — exit 0 · 5,729 passed · 95.84% · 16m12s. REVIEWED BY NOBODY, and NOT merged.** It owes **two lenses plus a concurrency pass** — highest-risk slice, and a green gate is not sign-off. 23-mutation sweep: 21 red, 1 red on re-run, 1 green (deleted per D-115). Found and fixed two pre-existing defects: no `profile_bundle` module was importable first in a fresh interpreter, and `build_approval_stamp` made **colliding approval IDs across revisions**, making any twice-approved record unpromotable and blocking §6 recapture recovery. Its build agent flagged its own deviation: plan step 6 wanted tests first, it wrote them alongside and satisfied the mutation requirement instead. **Branched from `main` BEFORE the append-only blocking fix — merge `main` forward before re-gating.** |
| `t17-schema` | **merged** | **MERGED** to main at `27879bb`. Light review: APPROVE, no BLOCKING and no SHOULD-FIX in its own diff. |
| T18, T19 | — | Not started. T18 is the `profile-bundle` CLI, the first non-inert surface. T19 is the authoring contract and the final Gate A gate. |

**Combined gate on `main` with T14+T15+T17: exit 0 · 5,620 passed · 95.83%.** Gate A is **16 of 19 slices merged**; T16, T18 and T19 remain. **Gate A is NOT met and Gate B stays prohibited.** **T1–T12 ARE pushed and shipped inside the 0.3.0 wheel**; what is unpushed is everything from T13 onward.

**The independent review of T14's and T15's FIX ROUNDS is DONE — verdict REWORK. Do not re-run it.**
Every new check in both rounds is pinned: **16 of 16 mutations RED**, each caught by exactly the test
written for it (T14 M1/M2/M3/M5, T15 M1–M11; the one green, T14-M4, is an equivalence, not a gap).
The three new T14 tests locate the blob store by hashing rather than by the constant the check reads,
so they cannot agree with themselves. What the round did **not** establish is above: one BLOCKING and
three residual SHOULD-FIX, all in the blocker table. Evidence, with negative controls on every probe:
`.agent/T14-T15-FIXROUND-REVIEW.md`.

**T16 is the only branch left to merge forward, and it already sits on `main`.** The traps that cost
this program real time are recorded in D-128; the three a merge must still act on:

1. **Sweep every `quoted_yaml(` call** in any branch being merged — `logical_path` is required, new test
   files never conflict, and the failure appears only at runtime. **A line-based grep gives false
   positives**; only the suite settles it.
2. **Look for the same thing under two names, and for a deletion that is really a rename.** Both have
   happened here: two byte-identical `OSError` helpers, and a test `main` deleted that a branch kept.
3. **Resolving conflict markers is not resolving the conflict** — files sit at `UU` until an explicit
   `git add`, which a passing test run will not tell you.

**Import fixtures as `from tests.<package>.conftest import ...`, never bare `from conftest import`.** A
bare import binds whichever `conftest.py` loaded first; under the full suite that is
`tests/unit/conftest.py`. This shipped in T15, survived two review lenses and a fix round, and is
invisible to any narrow run — it is the concrete reason `make check` is the only gate.

**Dispatch state.** `scratchpad/RESUME-AT-0910.md` is the queue the previous session left; the T14
review, both T15 lenses and the T17 review are now **consumed**. What remains from it is the T16 build
brief (`scratchpad/BRIEF-T16.md`) and its carried debt (`scratchpad/CARRIED-DEBT.md`), then T18 and T19.
Review records are `scratchpad/T14-REVIEW-ROUND2.md`, `T15-REVIEW-LENS-A.md`, `T15-REVIEW-LENS-B.md`
and `T17-REVIEW.md`; Lens A's runnable probes are archived at `scratchpad/T15-lensa-probes/` and are the
executable statement of six defects, so re-run them after any change to the rebase.

**This file remains well over its ~170-line target and is OWED a trim** (no count here on purpose —
D-017). The next trim should compress the P6 narrative, now fully recorded in D-110/D-111/D-113, not the
standing-facts list. **The Gate A branch table is deliberately exempt**: it is the only record of the
unmerged local branches, and it collapses to one line the moment they land.

**A green `make check` is NOT a green CI** (D-117). `gitleaks`, `perf` and `generalization` are separate CI
jobs `make check` never runs, and pushing turned `gitleaks` red for the first time in the project's history
with every local check green. This does not contradict "`make check` is the only gate" — that holds for *this
repo's own correctness*. Run `gitleaks git --log-opts=origin/main..HEAD` before pushing.

**0.3.0 is PUBLISHED (D-119)** — PyPI, GHCR (`amd64` + `arm64`) and GitHub Releases, verified through three
paths independent of the workflow's own report. `v0.3.0` is a **lightweight** tag on `dc1ffec`, like every
prior tag. It **ships Gate A inside it, deliberately**: the wheel carries the whole `profile_bundle`
package and the `## [0.3.0]` section does not enumerate it. **Mit was offered "hold until Gate A is
reviewed" twice and declined both times.** The basis holds because the package is **inert** — no CLI
command, no bundle-to-`Resume` bridge, a test asserts both directions, nothing in a shipped code path
reaches it. Publishing changed the release, **not** the review's standing.

**A PARALLEL TRACK exists: the canonical career-profile bundle, Gate A — 16 of 19 slices merged
(T1–T15 and T17; D-115, D-118, D-120, D-125, D-127, D-128, D-129).** T16 is in build; T18 and T19 are
not started. **The branch table above is the authority for per-slice standing.** Not a P0–P7 phase; it has moved no program gate. Its design and plan live
**untracked** under `docs/superpowers/` — read them there, and **copy that directory into any worktree you
create**, where they otherwise vanish. `src/boardwatch/profile_bundle/` holds the typed outcomes, the
restricted YAML loader, the closed 33-document grammar, every record model, the JSON Schema export, a
packaged synthetic example, an isolated canonical serializer, the global record index, structural +
referential + evidence + **semantic** validation, the **effectiveness derivation**, the blob store,
versioned secret scanning, owner-gate derivation and append-only history, and the four deterministic
source adapters with candidate identity and import validation. **Gate A is NOT met and the bundle is
wired to nothing** — no CLI command, and deliberately no bundle-to-`Resume` bridge (a test asserts both
directions). Its commits being on `origin/main` is **not** sign-off. **Gate B stays prohibited until
Gate A is implemented AND independently reviewed.**

**T1–T12 are implemented and independently reviewed. T12's review loop is CLOSED (D-126) — it was
reviewed FIVE times, every finding is fixed, and no sixth round is owed.** Rounds one, two and three each returned REWORK
(D-121, D-122, D-124) and each is fixed (D-125). Rounds four and five ran **concurrently against the
same commit with different lenses** — one hunting runtime forgeries, one checking conformance against
the design's own words — and both returned REWORK. **Both independently found the same gap** the
author and a 20-mutation suite had missed: the byte-free adapter grammar reached record locators and
stopped, so an approved scope could name a shape no heading stack resolves to, validate clean, and
then fail every re-enumeration. All of it is fixed, with **28 of 28 distinct mutations caught** and
the gate green at **exit 0, 5,260 tests, 95.41%**. **D-126 states the exit criterion so this loop is
not reopened by reflex: a slice's review ends when a round finds no BLOCKING defect that is either a
silent identity/data-integrity fault or a legitimate input the system refuses.** Round four found
neither. That rule is per-slice and evidence-based. The conformance lens alone found a `SourceSpec` docstring claiming a
guarantee that landed nowhere — a sentence **D-122 had already recorded as false**.

**Read D-125 before touching locators, and D-120 before touching identity derivation.** The four
things most likely to be undone by accident:

- **`_root`, `.` and `..` are ESCAPED by the encoder, never refused** (`%5Froot`, `%2E`, `%2E.`).
  Refusing makes a legitimate document unenumerable, which is rounds one and three's shared defect
  class. `normalize_locator` keeps a `.`/`..` guard for raw *paths*, where the same spelling means
  traversal — D-120's reason for deleting that guard has inverted.
- **The reservation is global on purpose.** A structured key or résumé identifier named `_root` is
  escaped too and moves in §18.1's encoded-key sort. A per-adapter reservation would mean two
  encoders and the drift the round removed.
- **`is_normalized_locator` is deliberately WEAKER than `emits_locator`.** It admits the `~N` suffix
  and a reserved segment anywhere, because it also serves owner-authored scope locators. Tightening
  it strands every legitimate selected scope.
- **The résumé adapter's stage order and `~N` locator preservation are load-bearing for stored IDs**,
  and four checks were deleted in T12 for being unable to fire.

**T13 is MERGED to `main`** (gate `5aa8d1c`: exit 0, 5,416 passed, 95.61%): `reports.py`, `validation/digest.py`, the
promoted-revision fixture, `validation/completeness.py` and `validation/run.py`. Its review found one BLOCKING — the §20.6 clause binding an owner's approval to promoted content was
skipped for **every revision from 2 onward**, so a re-sealed tree carrying documents nobody approved
validated clean. Fixed and verified three ways (pre-fix / post-fix / fix mutated out). **Mit ruled that `METRIC_REVIEW_MISSING` is DELETED and metrics
get no review interval** (`review_interval_days` is a `PredicateSpec` column, a metric has no
predicate, and `reviewed_at` is required, so the check could not fire — D-115). A metric's freshness
is its `reviewed_at` date alone. The build also fixed two pre-existing defects: `validate_history`
derived owner gates against `parent=None`, reporting ~35 spurious `missing_owner_approval` errors on
**every revision ≥ 2**, and `parse_error_diagnostics` had no arm for `UnsupportedSchemaVersionError`.

**The live store has NOT had Slice 2 applied.** Migrated and backfilled for Slice 1 only (head
`p6_posting_identities`, 117,254 identity rows, `identities verify` exit 0, 147 groups / 186 surplus /
0.79%); Slice 2 was verified on an **isolated copy**. Re-verified read-only three times on 2026-08-10:
**no `job_dispositions` table**, `postings` 24,073 and `count(distinct job_id)` **24,073 — exactly 1:1**,
the cheap proof, since a regrouped store would read 23,887. `identities regroup` would move 186 postings
onto 147 canonical jobs and needs the `p6_job_dispositions` migration first; **Mit declined it on
2026-08-10** — not blocked, just not now. The 769 MB backup sits beside it.

**Not demonstrated on real data:** the ledger end to end, and the liveness probe against real leads. A
`boardwatch top 5` against the 23,455-posting copy ran past 20 minutes and was stopped — it pays for
`run_preflight` + `run_eligibility` over the whole corpus. Both are mutation-checked by tests; neither has
run at corpus scale.

**The closed-phrase catalog was NOT shipped, deliberately — not an omission to correct** (D-111). Providers
assemble `body_text` only from JSON-payload description fields, so page chrome cannot reach that column:
**11 of 23,455** matched, **all false positives**; a high-precision catalog matches **0**. Also note `bwd`
lives in gitignored `.agent/bin/bw-daily`, so its `top --no-record` fix is local to this machine.

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
| **BLOCKING on `main`: the append-only ledger merge is bypassed** | `rebase.py:374-378`. `_merge_plan` short-cuts to the draft's document wholesale when the selected revision left a document byte-identical, so `_merge_append_only` never runs — and for `conflicts/rulings.yaml` that is the **normal** case, because an ordinary promotion appends a change and a stamp but no ruling. **A draft that deletes an inherited ruling installs at exit 0 with no diagnostic**, and the revision's sequence is not a prefix of the result. T15's fix for this defect class therefore holds only when the revision also touched the ledger. Reproduced with a negative control on `history/approvals.yaml`, where the revision does append and the refusal fires correctly. Full evidence: `.agent/T14-T15-FIXROUND-REVIEW.md` finding 7. | Gate A |
| **A symlink LOOP escapes as an uncaught `RuntimeError`** | `storage.py:150`. The T14 fix round replaced a check that refused a loop cleanly with `symlink_refused` by an equality on `resolve()`, which raises instead. Measured before/after on the same path. Wrap the `resolve()`; do not weaken the predicate. Same file, finding 1. | Gate A |
| **D-129 clause 1 is violated by T15's own merge-validation refusal** | `record_ids: []` is emitted on a document holding 12 addressable records, where D-129 ruled empty means the unit has **no** addressable records. `_merge_conflict`'s docstring states the opposite of the ruling, and D-129 is the later of the two. Settle it before T18 renders these. Same file, finding 8. | Gate A |
| **A draft name `inventory` prints is not a name any command accepts** | `e7fc9a1` moved Lens B's 13-character trap to 96 rather than closing it: `inspection` classifies drafts with the 179-char segment grammar, while `draft_root` and `rebase_draft` still use the 96-char one — and `rebase.py:139` calls it outside every `except`, so a backup of a long draft raises an uncaught `BundlePathError`. That backup is the only copy of the pre-rebase draft. One cap for anything under `drafts/`. Same file, finding 11. | Gate A |
| **Confinement costs one `realpath` per stored blob, on every command** | 503 ms at 1,000 blobs, 8.7 s at 20,000, on `inventory`/`checkout`/`validate`/`rebase` and next on T16's `promote`. For the store's *entries* `is_symlink()` is behaviourally identical (every ancestor is checked one loop earlier) and ~6× cheaper; keep the equality only where an aliasing ancestor is possible. `perf` is a CI job `make check` never runs. Same file, finding 15. | Gate A |
| **A FIFO in the blob store blocks `open()` forever** | The confinement predicate admits it — a FIFO resolves to its own place — and `inventory` then hangs unkillably-by-`SIGTERM` in `open()`. Pre-existing (measured on both sides of the fix), but the new docstring is the first to claim this class is excluded, and the refusal is one `stat` away inside a loop that already iterates the entries. Same file, finding 4. | Gate A |
| **Three `resume.yaml` bullets exceed the 220-char layout gate** | Forces an untailored-master degrade on every posting, which is what blocks accumulating real runs. The file also lacks Knowledge Forge, has stale `skill_groups`, and an empty extracurricular block. **Mit pins `resume_max_pages=1` — do not advise setting it to 2.** | Mit (content) |
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
  **Check the driver for byte-identical duplicates before quoting a count** (D-122 reported 13 when 12 were
  distinct; the driver now aborts).
- **A test derived from a constant agrees with itself.** Deriving a test from the emitter closes drift
  between two pieces of code and says nothing about a shared wrong premise: mutating `_MAX_HEADING_LEVEL`
  survived because every assertion about the cap read the same constant it was checking (D-125). Pin the
  outside fact — what Markdown does — not the constant.
- **A detector must be confirmed to FIRE** — mutate the thing it watches and watch it go red (D-116). Its
  mirror image: **a check that cannot fire is deleted, not shipped** (D-115) — write a test saying *where* the
  guarantee actually lands. A fix elsewhere can make a live check dead: escaping `.`/`..` in the encoder
  killed a guard that had been firing until then (D-125).
- **Two reviewers with different LENSES beat two sequential rounds.** A forgery-hunting reviewer and a
  design-conformance reviewer run against the same commit both found the same missed gap independently,
  and only the conformance one found a docstring asserting a guarantee that landed nowhere (D-125).
  Reviewers that RUN the code find what reviewers that read it cannot (D-111).
- **`git add -A` and `git add -u` both sweep another writer's work.** `-u` feels safer because it cannot take
  untracked files, which is exactly why it is easy to forget it takes *every* tracked modification in the
  tree. Stage explicit paths, always.
- **When two sessions share a clone, a position in `git log` proves neither authorship nor order.** Commits
  land above *and* below yours. Push an explicit sha (`git push origin <sha>:main`) so a concurrent commit
  cannot ride along un-gated.
- **Concurrent subagents and a gate contend for the same CPU.** Load average 21 stretched a 65-second suite
  to eight minutes and SIGTERMed a gate in an earlier session. Pin the gate to a sha in its own worktree,
  and do not start a second heavy suite beside it.
- **Measure the spec's premise before building it.** D-098 priced a deferral with the wrong subsystem's
  figures (D-105); D-111 found PROGRAM item 6's authoritative signal was 0-for-11 on the real corpus and
  structurally unable to reach the column it reads. A spec written against another codebase's data is a
  hypothesis, not a requirement.
