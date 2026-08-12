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

**1. The code is complete, merged and green.** All nineteen slices, every review round's fixes, and the
three post-merge fixes (D-138, D-141, D-142) are on `main`. All four gates, re-run on the result:

| Gate | Result |
|---|---|
| `make check` | **exit 0** · 5,919 passed · 1 deselected · **95.65%** · 16m22s |
| `gitleaks` (`origin/main..HEAD`) | **exit 0** · 165 commits · no leaks |
| `perf` (CI-only) | **exit 0** · top-path 0.245–0.268 s |
| acceptance | **8 PASS / 0 FAIL**, re-run after the fixes |

Evidence: `.agent/GATE-A-CI-EQUIVALENCE.md`, which records the gated sha and the full test-count
accounting. Two `.md`-only commits followed that gate, owing `generalization` + `index-check`
(D-116) — both green.

**The track is now PUSHED.** `origin/main` was `88c5857` (T11) and the published 0.3.0 wheel
(`dc1ffec`) is T1–T10; on 2026-08-12 Mit authorised the push and `88c5857..8c3dd9f` went to
`origin/main` after a re-run `gitleaks` over the unpushed range (exit 0, captured unpiped, no leaks).
**The remote reported "Bypassed rule violations — 6 of 6 required status checks are expected":** it
went straight to `main` past branch protection, so CI ran *on* `main` rather than gating the push.
Check that run before treating the remote as verified.

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

**The last open question is ANSWERED (D-143).** Mit ruled on 2026-08-12 that `add-evidence` writes the
back-citation itself, default on. The premise the question had been framed on was false — `add_evidence`
was **already** a multi-document write (evidence *and* manifest), and the guide said otherwise while the
same guide's Editing section said the truth. **Gate A's standing turns on the gate, not on owner input.**

**The build was reviewed and came back REWORK, and the fixes are the useful part.** Three lenses ran on
the first commit: design conformance (**CONFORMS**, §12 quoted, §19 silent on whether `add-evidence` may
touch other records), docs accuracy (**REWORK** — a transcript whose evidence ID and fact disagreed, and
two further sites still describing the old two-document behaviour), and adversarial runtime (**REWORK**).
What the last one found is worth carrying:

- **A behaviour change verified only by the tests the commit itself edited ships red.** The full gate
  caught one CLI test asserting the old outcome; a narrow run over the authoring file could not.
- **"Any of the twelve fact-bearing documents" was not test-locked.** A hard-coded four-class list passed
  all 98 tests reaching `add_evidence` while covering 5 of 13 — D-142's shape inside the fix citing D-142.
  The catalog is now read off `FactBearingDocument.__subclasses__()` at run time.
- **The write order was wrong and its comment argued for it at length.** The manifest now goes second;
  written last it gave every citing document a failure position carrying `evidence_set_digest_mismatch`.
- **D-144**, the one that outlived the change that surfaced it: grounding checks read `evidence_ids` raw,
  so a *contextualizing* source satisfied a predicate's evidence contract. Mit ruled to fix the semantic
  layer rather than narrow the auto-link. The defect predates D-143.

**Two silent-success defects were found and fixed *after* the review loop closed** (D-138/D-142,
D-141), which is the useful thing to know about this subsystem's remaining risk: both were "no flags"
standing in for cleared, in code that six reviews and four gates had passed. One review of the first
fix returned REWORK because the fix reached eight of twelve commands while claiming all twelve. Treat
the closed review loop as evidence about the slices reviewed, not about the subsystem being defect-free.

**Gate B stays prohibited until Gate A is met.** Start any Gate A session with `git worktree prune`.

**Next action, in order:** (1) drop the `prefix_of(target) in ("fact", "metric")` filter in
`_documents_citing_back` — a mutation proved it **cannot change behaviour** (29 passed with it removed),
and by this program's rule a check that cannot fire is deleted; it is a one-line follow-up owing its own
gate; (2) start accumulating real daily runs; (3) P2 item 8 or P3 slice 5, both owner-gated, both
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

*(Two others are **resolved**: whether docs-only commits owe a full `make check`, by D-116; and whether
`add-evidence` should write the back-citation itself, **ruled by Mit on 2026-08-12 — yes, default on** —
built as D-143. The guide now documents the one-step flow, verified through the real CLI: a capture
supporting a fact is clean at exit 0 and reports the `confirm_fact` gate the back-citation incurs.)*

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
