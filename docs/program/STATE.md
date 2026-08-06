# PROGRAM STATE — read this first

**Last updated:** 2026-08-06 (session 3, P0 in progress)
**Updated by:** boardwatch (Claude)
**Repo state at write time:** P0's instrumentation work is merged to `main`; the tree is clean.
**This header carries no commit count or sha on purpose** — the previous one named both, went stale inside
a single session when three later docs commits did not update it, and a cold session following the
session-start ritual hit the disagreement on its very first check. State what is durably true; verify the
rest against `git log`. (D-017.)
**Gate:** `make check` exits **0** (2633 passed, coverage 94.98%), measured on this branch tip.

> This is the single file a fresh session with zero memory reads to know where the program stands.
> If it disagrees with the repo, **the repo wins** — fix this file and note the correction in
> `DECISIONS.md`. Full plan: `PROGRAM.md`. Numbers: `METRICS.md`. Rationale: `DECISIONS.md`.

---

## Current phase

**P0 — Instrumentation. IN PROGRESS on `main`.** Nothing is blocked.

Two of P0's eight items are done and on `main`: item 7 (the `run_id` migration) and item 2 (**per-rule
abstain rate**). `main` is green and pushed for the first time since session 1 — the branch that fixed it
merged this session.

Remaining P0 items, in the order D-016 implies: the **pipeline-run row** (item 0, early P3 work taken on
deliberately), then threading `run_id` into the two write paths, then the funnel artifact, the per-source
table, the run manifest, the reconciliation sweep, the stub rate, and the fabrication counters.

---

## What shipped in session 3 (2026-08-06)

Everything below is on `main` and **pushed**. `make check` exited 0 at each commit (2650 passed, 94.91%).

- **Merged `p0-instrumentation` to `main` and pushed** (`88c98d4`), after a second independent review.
  `main` had been red since session 1 and is now green: `make check` exits 0, `generalization: OK`. CI on
  the merge: success.
- **`540bb34` — per-rule abstain rate** (`boardwatch eligibility abstain`), P0 item 2. Enumerates from
  `load_rules()` and LEFT JOINs observed counts, so the 7 rules that have never fired are visible instead of
  absent. Never-fired reports as `never fired`, **never as 0%**.
- **`fc6e8a5`** — closed four nits from a third review (of the abstain feature itself). See D-018.
- **`5f254a3`, `193468e`** — this file, `METRICS.md`, `CHANGELOG.md`, and D-017/D-018.

**Two independent reviews ran this session, and neither found a logic defect.** Both found documents and
tests. D-017: `STATE.md`'s own header named a HEAD and commit count that three later docs commits had
invalidated — the header no longer carries either. D-018: a test whose docstring cited a rendering fix
**did not pin it** (it widened the terminal to 160 columns, dodging the 80-column condition the fix
addressed; deleting the fix left the suite green), and `total_rows` — documented as the property B6
reconciles against — had no caller and no assertion.

> **The standing lesson, now twice-observed: review the documents and the tests, not just the code.**
> A test that cannot fail is documentation with a green tick next to it. Confirm a new test fails without
> its fix before trusting it.

### What the new metric immediately found

**7 of 44 rules have never fired; 17 more fire and never decide.** Full numbers in `METRICS.md`. The two
that matter most:

- **The entire `clearance` family** — 105 detections, **0 met and 0 unmet, ever**. Every clearance rule
  that fires is at 100% abstain.
- **`work_auth:no_sponsorship_offered`: 1052/1052 abstained.** A thousand postings said in their own text
  that they offer no sponsorship, and the engine concluded nothing on every one. This is **bar metric B7
  measured rather than asserted**, and it is why `ineligible` is 0 across the whole database.

---

## What shipped in session 2 (2026-08-06)

Five commits on `p0-instrumentation` — two of substance, three recording them, `make check` green at each:

- **`bc0973d`** — `main` was **red** and had been since session 1. `PROGRAM.md:4` and `STATE.md:27`
  carried an absolute `/Users/<name>` path, violating generalization rule R1, so `make check` exited 2
  before pytest ever ran. Session 1 wrote "`make check` is the only gate" and then committed twice without
  running it. Fixed to `~/...`. See D-014 — **docs are scanned; a docs-only commit is not exempt.**
- **`c56bc11`** — `run_attribution` migration: nullable `run_id` on `eligibility_evaluations` and
  `artifacts`, plus round-trip test and the head-revision pin. See D-015.

Research findings are in `METRICS.md` under "Session 2". The load-bearing ones:

- **6 families, 44 rule patterns. 7 of the 44 have never fired once** in 20,637 evaluations. A
  `GROUP BY rule_id` emits no group for them at all, so per-rule abstain **must** enumerate from
  `load_rules()` and LEFT JOIN, or the rules it exists to expose stay invisible.
- **A 100% abstain rate already exists:** `experience_years:scoped_years_minimum`, 11,670/11,670 `unknown`.
  *(Session-3 correction: it is not one rule. Measuring it properly found **17**, including the whole
  `clearance` family. Session 2 found the one it happened to look at.)*
- Two of session 1's schema claims were imprecise: the dedup index is **partial**
  (`WHERE engine_kind = 'deterministic'`), and there is **no `abstain` verdict** — it is stored as
  `uncertain`.
- `disposition='unknown'` conflates **four** causes, separable only by free-text `rationale` with no CHECK
  constraint. Abstain *rate* is computable; the typed abstain *reason* the keystone invariant wants is not.
- `artifacts.uri` points at the **`.typ`, not the PDF**; PDF-built lives only in
  `meta_json.typst_pdf_built`.
- **Only 1 of 7 funnel stages** was run-attributable before the migration.

---

## What shipped in session 1

Analysis, planning and program machinery — **zero source changes**. Committed as `84cfab6`.

- Read all seven job-apps handover documents (2,609 lines) in `~/dev/Job apps/docs/boardwatch/`.
- Verified job-apps' claims about boardwatch against boardwatch's actual code. job-apps never read this
  repo and said so; four of its factual claims about boardwatch are wrong as a result. See `DECISIONS.md`
  D-002, D-004, D-005, D-006, D-007, D-009 and `PROGRAM.md` §5.
- Wrote `PROGRAM.md`, `STATE.md`, `DECISIONS.md`, `METRICS.md`, and the repo's first `CLAUDE.md`.

**Correction to boardwatch's own record:** the "37 applied folders" figure boardwatch used in
`.agent/plans/p12-parity-report.md` is wrong. job-apps' real figure is **388** `_applied/` folders (369
distinct, 380 with PDFs); 37 was one bucket of its current curated queue. boardwatch's "37 shipped vs 222
targets, and job-apps' applied count is also 37" argument is dead — both halves were coincidence on
job-apps' own numbers. That parity doc is retired by D-008; the file is gitignored working material and
has been left in place, unedited, as a record.

---

## Independent review — 2026-08-06

Reviewed by a fresh agent with no shared context, at Mit's instruction. **Verdict: APPROVE WITH CHANGES.**
Full record in D-013.

Five load-bearing factual claims were attacked: **D-004, D-007, D-009 VERIFIED** · **D-005, D-006
OVERSTATED** (both in boardwatch's own favour — the D-012 failure mode, caught). All twelve required
changes adopted, none contested.

### Worklist from the review

| # | Item | Phase | Status |
|---|---|---|---|
| 1 | Lane-scope D-005; add Tier-B token-provenance validator | P1 (3c) | **corrected in place** |
| 2 | Replace LaTeX `hbox`/`vbox` clause with Typst-native overflow check | P1 (3) | **corrected in place** |
| 3 | `typst` in Dockerfile + loud missing-binary preflight | P1 (3b) | **corrected in place** |
| 4 | `run_id` migration on `eligibility_evaluations` + `artifacts`; cache hit as an asserted stage | P0 | **corrected in place** |
| 5 | B1–B7 → phase → gate traceability table; give B4 an owner; fabrication counters in the funnel (`RewriteRow.drop_reason` already carries the data) | P0 | **closed** |
| 6 | Severity/policy layer into P2 deliverables and §3b's split table; specify which policy P5's labeled set is scored under | P2 / P5 | **closed** |
| 7 | Resolve the P1/P2 ordering inconsistency | P1/P2 | **closed — Mit ratified P1 first 2026-08-06; cost now stated explicitly in §2 rather than denied** |
| 8 | Make P4's blind-craft gate executable — job-apps produces no résumés under `STAGE1_ONLY=1` | P4 | **closed — corpus is job-apps' 392 existing `_applied/` folders** |
| 9 | Restore dropped handover items: sponsorship phrases, cohort completeness, persona registry, fixture-drift discipline, two-OS WAL | P3/P4/P5 | **closed** — persona registry is now P4 item 7; fixture drift is in `CLAUDE.md` |
| 10 | Augment the existing `FileLock` at `scan/coordinator.py:73` rather than replacing it | P3 | **closed** |
| 11 | Tier-B quota + meta-hash idempotence (~300 model calls/day unattended at 2/bullet) | P3 | **closed — P3 item 10** |
| 12 | Commit `docs/program/` and `CLAUDE.md` | — | **closed — committed 2026-08-06; standing permission to commit granted** |

**All twelve closed. The plan is final and approved to execute.**

---

## Next action

**Introduce the pipeline-run row** — P0 item 0, per D-016. One command running scan → eligibility → tailor
that owns run identity across all three. This is early P3 work, taken on deliberately.

Everything below it in P0 depends on that row existing, which is why it goes first now that the
`run_id`-independent metric (per-rule abstain rate) is done.

**Starting points a fresh session should not re-derive.** `runs` rows are written in exactly one place —
`insert_run` at `scan/coordinator.py:104`, inside the scan's file lock. Eligibility is judged later as a
`top`/`stats` preflight side-effect (`eligibility/preflight.py:133`) with no `run_id` in scope, and tailoring
is later still and single-posting (`run_tailor` takes one `posting_id`). **There is no batch orchestrator in
`src/`** — the de facto one is `.agent/bin/bw-daily` (`bwd`), gitignored shell. The new command replaces
that, and `build_abstain_report` (`reports/abstain.py`) is already a clean seam for the artifact to consume:
it is a pure function of catalog + counts, so the funnel writer needs no new query.

1. Thread `run_id` into the two write paths — `write_evaluation` (`eligibility/engine.py:242`) and
   `record_artifact` (`store/artifacts.py:17`) take no such parameter today, so the new column stays NULL
   forever until they do. **The migration alone changes no behaviour.**
2. ~~Per-rule abstain rate~~ — **DONE, `540bb34`.** `boardwatch eligibility abstain`. **But note the gap:**
   `PROGRAM.md` §3.P0.2 says "every run" and Gate P0 requires it answerable *from the artifact alone*.
   This ships an on-demand CLI table only. The metric exists and is correct; emitting it into a per-run
   artifact is item 3's job. **Gate P0 is not met by this commit** — do not read item 2 as closing it.
3. Funnel artifact (`json` + `md`) with cache hits as their own asserted stage
   (`store/eligibility.py:130`'s `inserted.rowcount == 0` **is** the cache-hit signal, computed today and
   discarded — this is plumbing an existing boolean out, not new detection).
4. Fabrication counters. Needs new plumbing, not a query: aggregates die at `cli/tailor_cmd.py:196-204`
   and `:407-414` after `console.print`, and Tier A's fail-safe has no counter anywhere.

Write the artifact **outside the git tree** (as tailored résumés already are): R6 forbids any `.pdf` in the
tracked tree and R7 requires a sha256-pinned `SHIPPED_DATA` entry for tracked `.json`. `.md` is exempt from R7.

---

## Phase status

| Phase | Status | Gate met? |
|---|---|---|
| P0 Instrumentation | **in progress** — items 7 (`c56bc11`) and 2 (`540bb34`) done; nothing blocked | — |
| P1 Résumé artifact gate | not started | — |
| P2 Profile + keystone invariant | not started | — |
| P3 Unattended one command | not started | — |
| P4 Craft gate | not started | — |
| P5 Eligibility decides | not started | — |
| P6 Liveness + dedup | not started | — |
| 14-day acceptance run | not started | — |
| P7 Breadth | not started | — |

---

## Blocked items

| Item | Blocked on | Since |
|---|---|---|
| _(none)_ — the run-key question was ratified as D-016 on 2026-08-06 | | |

---

## Open questions

**None.** The run-key question was **ratified by Mit as option (b), pipeline run, on 2026-08-06** — see
**D-016**. Do not re-litigate it. Its analysis is kept below because the rejected options carry the reasons.

### 1. What is a "run"? — RESOLVED 2026-08-06 (D-016): a pipeline run

**The problem, measured.** `runs` rows are inserted in exactly one place: `insert_run` at
`scan/coordinator.py:104`, inside the scan's own file lock. `run_id` is then threaded as a plain parameter
(no contextvar, no ambient state) through `apply_board` → `append_event`/`record_version_source`. But:

- **Eligibility runs in a different process.** `run_eligibility` (`eligibility/preflight.py:133`) is called
  from `top`, `stats` and `eligibility` preflight — never from `scan`. No `run_id` is in scope there.
- **Tailoring runs in a third process, one posting at a time.** `run_tailor` takes a single `posting_id`;
  **no batch orchestrator exists in `src/`**. The de facto batch driver is `.agent/bin/bw-daily` (`bwd`),
  which is gitignored shell — it just calls `boardwatch tailor run <id> --out ...` in a loop.

So a seven-stage funnel does not correspond to the boundaries of any process that exists. The evidence is
structural, above — no code path puts a `run_id` in scope where evaluations are written. (`runs` holds 4
rows against 20,637 evaluations, but that ratio proves nothing on its own: 4 scan runs could legitimately
produce 20,637 evaluations. It is a symptom, not the measurement.)

**The fork.** (a) `run_id` = the scan run, with downstream writers recording the scan they are working off —
cheap, but an evaluation's "run" then means *the run that captured the version*, not when it was judged.
(b) Broaden `runs` into a **pipeline run**: a new command wrapping scan → eligibility → tailor that owns the
row and emits the artifact — this is what P3 builds anyway, so P0 would be laying P3's foundation early.
(c) Make the funnel a **window** report like `stats`, not run-keyed at all — but then B6 ("funnel reconciles
to a terminal state") has nothing to reconcile *per run*, and PROGRAM.md §3.P0.4's run manifest has no owner.

**Recommendation: (b)**, scoped so P0 does not wait for P3 — introduce the pipeline-run row and the artifact
writer now, have `scan` populate what it owns, and report downstream stages as an explicit `unattributed`
bucket until their writers thread `run_id`. Do **not** silently pick (a): it makes "cache hit" and
"judged during this run" the same number, which is the exact indistinguishability D-013 added the migration
to prevent.

**Status: RATIFIED — (b), by Mit, 2026-08-06.** Recorded as **D-016**. P0 now includes the pipeline-run row
and the funnel artifact writer; this is accepted as *early* P3 work rather than extra work, since P3's "one
command, unattended" needs the same row and the alternative was re-keying at P3.

### 2. `main` is red until this branch merges — deliberate, not forgotten

`bc0973d` (on this branch) is the fix. It was **not** cherry-picked onto `main` because pushing is not
covered by standing permission and the branch merge resolves it anyway. A cold session that runs
`make check` on `main` before merging will see generalization exit 2 — that is D-014, already diagnosed, not
a new problem. Do not re-diagnose it.

### Previously resolved

All four of session 1's questions were answered by Mit on 2026-08-06 — see `PROGRAM.md` §7 and
`DECISIONS.md` D-010/D-011.

Summary of the answers, because they carry program-wide weight:

1. **Reading the job-apps repo is authorized, standing.** It was revoked only for the self-assessment
   session so the plan would be honest. Accompanying standing instruction: **check and verify rather than
   assume** — a failed command is not a negative result, a recalled number is not a measured one.
2. **Two personas (SDE / iOS)** with different protected-fact sets, matching Mit's job-apps setup.
3. **`needs_sponsorship: true` for Mit**, declared knowingly and declared per user — never inferred.
4. **`~/boardwatch-applications/<date>/`** stays the daily output home.

Answers 2 and 3 both carry the same governing rule, now `PROGRAM.md` §3b and D-010: **publish the
generalized mechanism, keep Mit's instance local. This applies system wide.**

---

## Standing facts a fresh session should not re-derive

- **Live urgency.** `STAGE1_ONLY=1` is active in job-apps' launchd plist. Its 08:30 run stops after
  discovery. **Nothing is generating Mit's résumés daily right now.** P1 and P3 close a live gap.
- **The tailoring architecture is already correct.** Typed skeleton, plain-text-only model contract,
  Python-owns-markup, independent entailment judge — all present. Do not rebuild it. (`PROGRAM.md` §5.1.)
- **`typst` is installed** at `/opt/homebrew/bin/typst`. "No PDF" is a silent-degrade code path, not a
  missing binary.
- **`track` exists but has never been used** — `applications` and `application_events` are both 0 rows.
- **`jobs` and `postings` are both 19,448** — `job_id` is 1:1, grouping has never run, duplicate leakage
  is structurally unmeasurable until P6.
- **`make check` is the only real gate.** pytest + ruff + mypy green is not green; the generalization
  checker only runs under `make check`.
- **`.agent/` and `.superpowers/` are gitignored** working material. `CHANGELOG.md` is authoritative for
  what shipped.
