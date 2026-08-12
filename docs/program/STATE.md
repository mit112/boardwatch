# PROGRAM STATE — read this first

> The one file a fresh session with zero memory reads to know where the program stands.
> **If it disagrees with the repo, the repo wins** — fix this file and note the correction in
> `DECISIONS.md`. Plan: `PROGRAM.md`. Numbers: `METRICS.md`. Rationale: `DECISIONS.md`. What shipped:
> `CHANGELOG.md`. **Facts you should not re-derive: `STANDING-FACTS.md`** (D-139) — read it by section,
> when you are about to touch the thing it describes.
>
> `DECISIONS.md` and `METRICS.md` each carry an **index spanning themselves and a closed archive**
> (`*-ARCHIVE.md`, D-108). Read the index, then the one range you need — never the whole file.

**This file states only what is true now**, and carries no commit sha or commit count on purpose — both go
stale inside a single session (D-017). `git log --oneline -1` and `git status --short --branch` are the
authority. **Rewrite it, never prepend to it.** Keep it near 170 lines; the long tail belongs in
`STANDING-FACTS.md`. Git has every previous version.

---

## Current standing

**Two tracks are live.** The **P0–P7 replacement program** is at P6, whose build is complete and whose
last two gate clauses need the system *run*. The **canonical career-profile bundle (Gate A)** is merged
into `main`, green on the whole CI surface, and reviewed — but **not met**, on one owner ruling.

### The P0–P7 program

**P6's build is COMPLETE — all six items — and its commits are PUSHED.** Detail in D-095, D-103…D-107,
D-110 (ledger), D-111 + D-113 (applied state, liveness). Schema head is **`p6_job_dispositions`**.
**Read D-110 before touching the ledger, D-111 and D-113 before touching liveness**, and the liveness
section of `STANDING-FACTS.md` before touching either.

**P6 has nothing left to BUILD — its last two gate clauses need the system RUN**: duplicate leakage needs
7 days of runs (the window must start after D-110, which changed which callers advance the queue), and
"0 dead postings" needs a real run whose leads are actually probed. Accumulating those runs is gated on
Mit's `resume.yaml` fix below.

### Gate A — merged, green, reviewed, and NOT met

**Three separate claims, kept separate on purpose. Do not collapse them into "Gate A is met".**

**1. The code is complete, merged and green.** All nineteen slices and every review round's fixes are on
`main`. All four gates, on the integration head that was gated:

| Gate | Result |
|---|---|
| `make check` | **exit 0** · 5,913 passed · 1 deselected · 95.59% · 16m35s · Python 3.13.12 |
| `gitleaks` (`origin/main..t18-cli`, and `..main`) | **exit 0** · no leaks |
| `perf` (CI-only) | **exit 0** |

Evidence: `.agent/GATE-A-CI-EQUIVALENCE.md`. First time the *whole* CI surface has been run locally
against this track. **Nothing on this track is pushed** — `origin/main` is `88c5857` (T11) and the
published 0.3.0 wheel (`dc1ffec`) is T1–T10, so everything from T12 onward is local. The merge into
`main` moved only `.md` files relative to the gated tree, which owes `generalization` + `index-check`
(D-116); a full gate is owed again for anything merged after it.

**2. The review loop is CLOSED (D-137).** Five rounds: two lenses on T18's build (REWORK, REWORK, each
finding a BLOCKING the other missed), one on its 10-commit fix round (REWORK), one on those fixes
(REWORK — 2 BLOCKING), and round five (**APPROVE**, 14 claims verified, 11 of 12 mutations red). D-126's
stopping rule is satisfied and **the exit criterion was written down before round five ran**. T19's guide
has its own docs-only review: **APPROVE**, 0 BLOCKING, 37 claims verified. Reports:
`.agent/GATE-A-CLOSING-REVIEW.md`, `-ROUND5-REVIEW.md`, `.agent/GUIDE-DOCS-REVIEW.md`,
`.agent/T18-REVIEW-LENS-A.md`, `-BOUNDARY.md`, `.agent/T18-FIXROUND-REVIEW.md`. **Do not re-run any of
them.**

**3. The acceptance clauses are demonstrated.** The design's Gate A section lists eleven; eight are driven
end to end through the real CLI against the packaged synthetic example by `.agent/gate-a/acceptance.sh`
(re-runnable, 8 PASS / 0 FAIL), and clauses 7 and 9 (crash matrix, import idempotency) are cited to the
suite that owns them, because a script driving the CLI once cannot establish them. Clause-by-clause map:
`.agent/GATE-A-ACCEPTANCE.md`.

**What remains before "Gate A met" can be written down:** the owner's call on **open question 3 below**
(`evidence_link_asymmetry` after `add-evidence` on a fact or metric). That is the whole list.

**Gate B stays prohibited until Gate A is met.** Start any Gate A session with `git worktree prune`.

**Next action, in order:** (1) get Mit's ruling on `evidence_link_asymmetry` and write down whether Gate A
is met; (2) start accumulating real daily runs; (3) P2 item 8 or P3 slice 5, both owner-gated, both
wanting their own context window.

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
| *Gate A (parallel track)* | *complete, merged to `main`, gate green* | ***NOT MET*** — *one owner ruling; has moved no program gate* |

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

**3. Should `add-evidence` write the back-citation itself?** *(The last thing standing between Gate A and
"met".)* `evidence_link_asymmetry` stands after a successful capture: §12 requires a fact to cite the
evidence that supports it, and `add_evidence` only appends to the evidence document, so the owner must then
edit the fact. Same class as the BLOCKING T18's fix round closed — a correct operation leaving a standing
error.

**Scope, measured, and narrower than this entry first claimed:** bidirectional citation is required only
for **`fact` and `metric`** records, because only they carry `evidence_ids`. Evidence naming a `skill` or
a `claim` is a legitimate one-way link under §12 and reports nothing. Driven through the CLI: fact → exit
1, metric → exit 1, **skill → clean exit 0, claim → clean exit 0**. So the question is whether facts and
metrics should be auto-linked, not whether every capture is affected.

**The authoring guide is not blocked on this** — `docs/profile-bundle-authoring.md` documents the two-step
flow as it actually behaves and says the question is open. Neither T18 reviewer raised the issue (lens A
hand-fixed it in a probe and moved on).

*(A fourth — whether docs-only commits owe a full `make check` — was **resolved** by D-116.)*

---

## Live blockers and carried gaps

| Item | Detail | Owner |
|---|---|---|
| **Three `resume.yaml` bullets exceed the 220-char layout gate** | Forces an untailored-master degrade on every posting, which is what blocks accumulating real runs. The file also lacks Knowledge Forge, has stale `skill_groups`, and an empty extracurricular block. **Mit pins `resume_max_pages=1` — do not advise setting it to 2.** Mit deprioritized this 2026-08-11; do not gate other work behind it. | Mit (content) |
| **The 03:10 launchd job re-fires a task that shipped 209 commits ago** | `com.mitsheth.boardwatch-p6.plist` is a *daily* `StartCalendarInterval` job carrying the *one-shot* "execute P6 Slice 1" prompt, asserting `main` at `fb0386a`. It has now misfired **twice** — 2026-08-11 and 2026-08-12 (D-123, D-135). Benign and self-detecting in five read-only commands, **not** self-correcting, and it spends a real usage window each night. Fix: `launchctl bootout gui/$UID/com.mitsheth.boardwatch-p6`, or repoint `~/.claude/scheduled/p6-slice1-run.sh` at a fresh prompt. | Mit (automation) |
| **No local pre-push check for the TWO CI-only jobs** | **`gitleaks` and `perf` — two, not three.** `generalization` IS inside `make check` (`Makefile:2`, the identical command CI runs). `gitleaks` is installed on this machine (8.30.1) but not wired into project tooling; all four gates are green on the Gate A tree — `.agent/GATE-A-CI-EQUIVALENCE.md` (D-117) | mitigated, not wired |
| **P2 item 8 — the onboarding gatherer** | The thing that would make the field tier fire for anyone. D-054 forbids us authoring non-tech field content, so it must be gathered per user. Needs its own brainstorm | owner-gated |
| **P3 Slice 5 — LLM economics** | Substantial and design-heavy; use a fresh context window | P3 |
| **P3 item 8 — cross-OS two-writer WAL test** | A same-OS test proves nothing; needs a Docker-Linux-container + macOS-host harness. The documented-stance half shipped (D-041) | P3 |
| **A `SIGKILL`ed run leaves a dangling `runs` row** | `try/finally` covers exceptions and Ctrl-C, not SIGKILL. Largely drained by the age-based reaper (D-046); a heartbeat-column reaper is the deferred correct fix | P3 |
