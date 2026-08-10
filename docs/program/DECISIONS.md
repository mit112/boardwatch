# Decision log

Append-only. One entry per architectural or program decision, so no decision is re-litigated after a
context reset. Newest last. If a decision is reversed, add a new entry that supersedes it — never edit or
delete the original.

Format: **context** (what forced a choice) · **choice** · **alternatives rejected** · **consequence**.

---

## Index — spans both files

**Do not read either file end to end.** Together they are ~80,000 tokens; `STATE.md` is the read-first
document, this is a reference. Find the entry you want below, then read just its range:

```
sed -n '<start>,<end>p' docs/program/<file>
```

Entries **D-001 … D-076** live in `DECISIONS-ARCHIVE.md`, which is closed. **D-077 onward** live in this
file, and new entries are appended here. Cross-references are by number (`D-028`), never by file, so they
resolve across the split.

Line numbers drift as entries are appended. Confirm one before trusting it:

```
grep -n '^## D-0NN' docs/program/DECISIONS.md docs/program/DECISIONS-ARCHIVE.md
```

| # | File | Line | Decision |
|---|---|---|---|
| D-001 | DECISIONS-ARCHIVE.md | 15 | Program machinery lives in `docs/program/`, version-controlled |
| D-002 | DECISIONS-ARCHIVE.md | 33 | Output-side phases precede input-side phases |
| D-003 | DECISIONS-ARCHIVE.md | 51 | The 14-day clock is acceptance-only, never a phase gate |
| D-004 | DECISIONS-ARCHIVE.md | 68 | Stub defense: take the metric now, defer the machinery |
| D-005 | DECISIONS-ARCHIVE.md | 87 | Do not rebuild the tailoring architecture |
| D-006 | DECISIONS-ARCHIVE.md | 109 | The PDF cliff is a silent-degrade defect, not a packaging problem |
| D-007 | DECISIONS-ARCHIVE.md | 127 | The work-auth fix is one declared field, not a phase |
| D-008 | DECISIONS-ARCHIVE.md | 146 | Retire the P12 pre-registered parity comparison |
| D-009 | DECISIONS-ARCHIVE.md | 167 | Applied-suppression belongs in P6, and is smaller than described |
| D-010 | DECISIONS-ARCHIVE.md | 185 | Published mechanism vs. personal instance, system wide |
| D-011 | DECISIONS-ARCHIVE.md | 211 | Two personas, and `needs_sponsorship` declared per user |
| D-012 | DECISIONS-ARCHIVE.md | 231 | Verify rather than assume, as a program rule |
| D-013 | DECISIONS-ARCHIVE.md | 253 | Independent review: verdict APPROVE WITH CHANGES, amendments adopted |
| D-014 | DECISIONS-ARCHIVE.md | 291 | `main` was red; program docs are subject to the generalization checker |
| D-015 | DECISIONS-ARCHIVE.md | 314 | Migration `run_attribution`: nullable, unnamed inline FK, evaluations + artifacts only |
| D-016 | DECISIONS-ARCHIVE.md | 350 | `run_id` means a pipeline run, and P0 introduces it |
| D-017 | DECISIONS-ARCHIVE.md | 386 | second independent review; STATE's own header was the defect |
| D-018 | DECISIONS-ARCHIVE.md | 428 | abstain-rate scope, and the `IN`-clause limit is a repo-wide debt, not this metric's |
| D-019 | DECISIONS-ARCHIVE.md | 462 | `run_id` is never NULL on a row written after attribution exists |
| D-020 | DECISIONS-ARCHIVE.md | 514 | the scan stage creates the run row; the pipeline finishes it |
| D-021 | DECISIONS-ARCHIVE.md | 587 | second review: the exit-code fix had over-corrected into bar metric B5 |
| D-022 | DECISIONS-ARCHIVE.md | 642 | the funnel's head is the open-posting corpus, not scan throughput |
| D-023 | DECISIONS-ARCHIVE.md | 661 | a stage reports `None` when unmeasured, and says when its balance is bookkeeping |
| D-024 | DECISIONS-ARCHIVE.md | 700 | the artifact is written from the `finally`, and never fails the run |
| D-025 | DECISIONS-ARCHIVE.md | 718 | mutation testing has two failure modes that both report a false PASS |
| D-026 | DECISIONS-ARCHIVE.md | 747 | `assisted` is as unmeasurable as `unique`, and both report `None` |
| D-027 | DECISIONS-ARCHIVE.md | 781 | the shortlist stage becomes evidence, by rooting it at what the ranker considered |
| D-028 | DECISIONS-ARCHIVE.md | 813 | only one per-source total was worth reconciling, and the first attempt could not fail |
| D-029 | DECISIONS-ARCHIVE.md | 870 | `runs.status` is a closed catalog whose DEFAULT carries the meaning |
| D-030 | DECISIONS-ARCHIVE.md | 918 | the run manifest ships two hashes, closing the profile-row gap rather than only noting it |
| D-031 | DECISIONS-ARCHIVE.md | 965 | `boardwatch verify` is a standalone DB↔artifact reconciliation sweep, supplementing Gate P0 rather than re-anchoring it |
| D-032 | DECISIONS-ARCHIVE.md | 1069 | P1a ships a hard PDF gate as impure-runner/pure-policy, splits P1b out, and closes D-006's silent degrade |
| D-033 | DECISIONS-ARCHIVE.md | 1175 | Tier-B reword provenance: a deterministic allowlist, fail-closed to Tier-A, counted separately from B4 |
| D-034 | DECISIONS-ARCHIVE.md | 1261 | `needs_sponsorship` is an orthogonal bit on the work-auth fact, and it only decides sponsorship rules |
| D-035 | DECISIONS-ARCHIVE.md | 1298 | `work_auth` ships `default_policy: blocker`; the other five families stay `preference` |
| D-036 | DECISIONS-ARCHIVE.md | 1364 | `eligible` with zero fired requirements renders distinctly from `eligible` with cleared ones |
| D-037 | DECISIONS-ARCHIVE.md | 1458 | the fatal-vs-non-fatal contract is written, and the outage predicate is one function |
| D-038 | DECISIONS-ARCHIVE.md | 1516 | the run-scoped morning artifact, and freshness from run_id + a terminal row + the funnel's own reconciliation |
| D-039 | DECISIONS-ARCHIVE.md | 1611 | run-integrity guards: cohort completeness by ID set, zero-output provably-right via run_id attribution, filesystem-truth reusing slice-4 |
| D-040 | DECISIONS-ARCHIVE.md | 1714 | LLM transient-error retry-with-backoff, ported from politeness into a shared adapter helper |
| D-041 | DECISIONS-ARCHIVE.md | 1793 | the SQLite/WAL concurrency stance is now documented (P3 item 8, doc half) |
| D-042 | DECISIONS-ARCHIVE.md | 1815 | the tailor-level idempotence short-circuit is DECLINED (YAGNI); the response cache already covers it |
| D-043 | DECISIONS-ARCHIVE.md | 1839 | the scan lock now notifies loudly with the blocking pid; the sidecar is message-only, never a lock authority |
| D-044 | DECISIONS-ARCHIVE.md | 1884 | P3 slice 5b: KEEP today's Tier-A downgrade on provider/quota error; decline the "never downgrade" inversion |
| D-045 | DECISIONS-ARCHIVE.md | 1913 | P3 slice 2: DECLINE custom stale-reclaim (unsound AND unnecessary); the loud-notify shipped, the reaper stays fresh-context |
| D-046 | DECISIONS-ARCHIVE.md | 1940 | P3 slice 2: age-based run REAPER (no schema); this CLOSES the last non-Mit / non-Docker P3 build item |
| D-047 | DECISIONS-ARCHIVE.md | 1979 | Proceed with P4 (craft rubric) ahead of Gate P3; Gate P3 is blocked only by Docker+ops, not by any P4 build dependency |
| D-048 | DECISIONS-ARCHIVE.md | 2005 | P4 item 1: deterministic overmatch (verbatim-lift + unusual-caps) guard SHIPPED; first P4 slice |
| D-049 | DECISIONS-ARCHIVE.md | 2037 | P4 item 2: consolidate the canonical-vocab seed; DECLINE the per-field selector (YAGNI) |
| D-050 | DECISIONS-ARCHIVE.md | 2068 | P4 item 3a: banned-register + buzzword-density + verb-diversity craft guards SHIPPED |
| D-051 | DECISIONS-ARCHIVE.md | 2103 | P4 item 3b: requirement-echo detector SHIPPED; item 3 COMPLETE |
| D-052 | DECISIONS-ARCHIVE.md | 2142 | P4 item 4: DEFER the de-senioritizer into item 7 (don't build inert dead code); do items 5–6 first |
| D-053 | DECISIONS-ARCHIVE.md | 2169 | P4 item 5a: per-lead layout gate SHIPPED (bullet length/count, escaping round-trip, template-artifact) |
| D-054 | DECISIONS-ARCHIVE.md | 2194 | Personas / field-specific knowledge are GATHERED per-user at onboarding, never authored by us (we ship tech expertise only) |
| D-055 | DECISIONS-ARCHIVE.md | 2226 | Opus 5 checkpoint reviews of the session's big pieces (reaper + P4 guard gauntlet); fix-forwards |
| D-056 | DECISIONS-ARCHIVE.md | 2259 | P4 item 5b: run-once fatal master-résumé validation at load; item 5 COMPLETE |
| D-057 | DECISIONS-ARCHIVE.md | 2285 | Résumé TAILORING is fundamentally wrong; a dedicated fix session precedes Gate 3 (and, recommended, the remaining P4 polish) |
| D-058 | DECISIONS-ARCHIVE.md | 2309 | Résumé render engine = tectonic compiling the user's actual LaTeX template (Typst decision reversed) |
| D-059 | DECISIONS-ARCHIVE.md | 2352 | Increment-1 plan cleared for execution after a SECOND fresh-context re-review (both REWORK, all folded in) |
| D-060 | DECISIONS-ARCHIVE.md | 2399 | Increment 1 (LaTeX render substrate) executed and shipped to `main`; the Typst→tectonic swap is complete |
| D-061 | DECISIONS-ARCHIVE.md | 2467 | P4 item 6 (keyword-coverage measurement) shipped to `main` |
| D-062 | DECISIONS-ARCHIVE.md | 2501 | Persona (P4 item 7) is a résumé-presentation lens, not an eligibility variant; the de-senioritizer is made live via JD-title stripping |
| D-063 | DECISIONS-ARCHIVE.md | 2543 | P4 item 7 (persona registry + live de-senioritizer) shipped to `main`; P4 build complete |
| D-066 | DECISIONS-ARCHIVE.md | 2589 | P5 answer-key is AI-oracle + human-audit-a-sample via a job-apps judge port (its own session) |
| D-065 | DECISIONS-ARCHIVE.md | 2623 | P5b B0 scaffolding: reference all-blocker policy + precision scorer + labeling worksheet |
| D-064 | DECISIONS-ARCHIVE.md | 2672 | P5a: three verdict-SAFE eligibility-integrity slices shipped to `main` |
| D-067 | DECISIONS-ARCHIVE.md | 2715 | P5 answer-key oracle judge: agent-lane port + deferred (but drained) human audit |
| D-068 | DECISIONS-ARCHIVE.md | 2760 | P5b answer-key oracle judge SHIPPED to `main` (agent lane, all 7 tasks) |
| D-069 | DECISIONS-ARCHIVE.md | 2803 | First Gate-P5 measurement: precision 94% (16/17), one FP = a disjunctive-experience over-fire |
| D-070 | DECISIONS-ARCHIVE.md | 2845 | Audit via historic data (Mit declined manual audit); B1–B4 unblocked at 28% coverage |
| D-071 | DECISIONS-ARCHIVE.md | 2900 | Two-stage eligibility gate agreed for a fresh session; model-agnostic, agent-lane cheap gate |
| D-072 | DECISIONS-ARCHIVE.md | 2927 | Model-tier benchmark for the eligibility judge + published guidance (research, next sessions) |
| D-073 | DECISIONS-ARCHIVE.md | 2957 | Disjunctive experience-years fix SHIPPED; Gate P5 MET (precision 100%) |
| D-074 | DECISIONS-ARCHIVE.md | 3009 | Final eligibility gate lane SHIPPED (persistent, agent-lane, fail-open); Gate P5 unchanged |
| D-075 | DECISIONS-ARCHIVE.md | 3084 | Gate P2 reconciled: three individually-correct verdicts (may coincide); ≥3-field mechanism via fixtures |
| D-076 | DECISIONS-ARCHIVE.md | 3153 | P2 item 4's final whole-branch review: what it caught, and four rulings it forced |
| D-077 | DECISIONS.md | 143 | P6 Slice 1: the design is settled and the plan is written; no code exists yet |
| D-078 | DECISIONS.md | 233 | P6 Slice 1: the plan's test fixtures are now real; eleven defects, all found by running code |
| D-079 | DECISIONS.md | 322 | P6 Slice 1 annotates only; `postings.job_id` is not mutated |
| D-080 | DECISIONS.md | 336 | `content_hash` alone may never suppress |
| D-081 | DECISIONS.md | 350 | `exact_quad` is the sole suppressing kind, and its yield is stated honestly |
| D-082 | DECISIONS.md | 368 | `cross_host` ships annotate-only, reversing an earlier draft |
| D-083 | DECISIONS.md | 389 | No location evidence ⇒ no location-bearing identity, never a `"[]"` sentinel |
| D-084 | DECISIONS.md | 404 | Three host classes, not two; matching is exact-or-dot-suffix |
| D-085 | DECISIONS.md | 418 | Allowlist URL normalization, not a denylist |
| D-086 | DECISIONS.md | 432 | Survivor election never consults score; `posting_id` is a load-bearing tiebreak |
| D-087 | DECISIONS.md | 447 | Instrumentation is completeness-gated, not existence-gated |
| D-088 | DECISIONS.md | 461 | `assisted` stays `None` in this slice |
| D-089 | DECISIONS.md | 476 | Identities are upserted on every observation; a kind that stops being produced is deleted |
| D-090 | DECISIONS.md | 493 | The ranker is completeness-gated for reproducibility, not safety |
| D-091 | DECISIONS.md | 511 | The recount recomputes in Python, and claims staleness only |
| D-092 | DECISIONS.md | 526 | Identities are backfilled by an explicit command, not by the migration |
| D-093 | DECISIONS.md | 540 | Slice 1 does NOT meet Gate P6, and makes only one of its four clauses measurable |
| D-094 | DECISIONS.md | 554 | P6 Slice 1 BUILT (unattended run): five more plan defects, three of them tests that could not fail |
| D-095 | DECISIONS.md | 682 | P6 Slice 1 reviewed by three independent reviewers; fourteen findings fixed, two rejected |
| D-096 | DECISIONS.md | 747 | The C++/C# fix folds punctuation into words; it does NOT add a raw-title comparison |
| D-097 | DECISIONS.md | 791 | `_verify_quad` rejected nothing on the live corpus; "string-verified" is not precision evidence |
| D-098 | DECISIONS.md | 820 | Suppression reports when it is OFF; wiring backfill into the pipeline is Slice 2 |
| D-099 | DECISIONS.md | 856 | Gate batching stays allowed; the per-task fast-check set must include the schema guards |
| D-100 | DECISIONS.md | 882 | P6 Slice 1 merged to `main`; Gate P6 clause 3 is MET, not merely measurable |
| D-101 | DECISIONS.md | 914 | Gate P6 clause 4 is MET: 20/20 sampled suppressions are genuine duplicates |
| D-102 | DECISIONS.md | 944 | D-072 (model-tier benchmark) is deferred indefinitely |
| D-103 | DECISIONS.md | 966 | P6 Slice 2: the ledger is a current-state row per job, `seen` suppresses on a TTL, and the policy stamp never auto-reopens |
| D-104 | DECISIONS.md | 1031 | Job regrouping: the survivor's job wins, and a tracked group is refused whole |
| D-105 | DECISIONS.md | 1074 | Identity writes move into the scan path, closing D-098 — and D-098's cost argument did not apply |
| D-106 | DECISIONS.md | 1105 | Two consequences the build forced: what earns a permanent `skipped`, and the zero-output guard |
| D-107 | DECISIONS.md | 1131 | P6 Slice 2 BUILT and verified on real data; `cross_host` dereference deferred by measured absence |
| D-108 | DECISIONS.md | 1180 | The decision log and the metrics log are archive-split; the reading protocol moves into the index |

---

## D-077 — P6 Slice 1: the design is settled and the plan is written; no code exists yet

**2026-08-09/10 · P6 Liveness + dedup, design + planning session. Stopped at Mit's request before
execution.** Repo unchanged except this file and `STATE.md`. The spec and the 9-task TDD plan live at
`.superpowers/sdd/2026-08-09-p6-liveness-dedup/` (gitignored — hence this entry, which is the durable
record of what was decided); `HANDOFF.md` there states where to resume.

**Scope.** P6 is split into three slices. **Slice 1** = PROGRAM items 1–3 (posting-identity table,
allowlist URL normalization, cross-host identity) plus the funnel's measured `unique` counter.
**Slice 2** = item 4's durable ledger with its drain, job regrouping, and cross-host dereference.
**Slice 3** = item 5 (applied-state suppression) and item 6 (liveness). Slice 1 **does not meet Gate
P6** and makes only one of its four clauses measurable; that is stated in the spec rather than
discovered later.

**The decisions, so they are never re-litigated.** Section references are to `design.md`.

- Slice 1 **annotates only**; `postings.job_id` is not mutated until Slice 2, because
  `applications.job_id` is the tracking key (§1.3).
- **`content_hash` alone may never suppress.** The live corpus contains 727 groups it would wrongly
  collapse (§2).
- **`exact_quad` is the sole suppressing kind**, and what it suppresses is stated honestly: 131 groups
  / 168 surplus rows / 0.72% of the live population, and the sampled groups are
  same-role-different-requisition pairs with byte-identical descriptions, not re-postings. The claim
  defended is "one application decision", not "the same requisition" (§2).
- **`cross_host` ships annotate-only** (`suppresses=False`), reversing an earlier draft that had
  assumed otherwise: an unanswered flag is not consent, `core/identity.py:3` already records that
  cross-ID heuristics may only annotate, PROGRAM item 1 says only exact identities may suppress, and a
  concrete false-suppression counterexample exists. Re-entry path: it becomes suppressible once an
  aggregator can be dereferenced to exact requisition evidence (§3.1).
- **A posting with no location evidence emits no location-bearing identity at all** —
  `normalized_locations` returns `None`, never `"[]"`. A `"[]"` sentinel is a silent collapse that
  neither string-verify nor the recount can detect, because both sides compare equal. Measured cost: 7
  rows of 23,455 (§2.1).
- Three host classes, not two. `unknown` is the default and never suppresses; host matching is
  exact-or-dot-suffix, **never substring** (§3).
- **Allowlist** URL normalization, not a denylist — direction chosen by which failure is detectable
  (§4.1), plus string-verify on hash hit (§4.2).
- **Survivor election never consults score.** `posting_id` is a load-bearing tiebreak because
  `first_seen_at` is second-resolution (§5.1). The drain (`--include-duplicates`) ships in the same
  change as the quarantine, per the standing invariant (§5.2).
- **Instrumentation is completeness-gated, not existence-gated:** `unique` is `None` unless *every*
  open posting has a current-version identity (§2.2). The ranker is completeness-gated too, but for a
  different reason — partial coverage cannot over-suppress, since an uncovered posting joins no group;
  it is that survivor election over a subset is backfill-order-dependent, and Gate P6 requires
  re-deriving 20 sampled suppressions from the data.
- **`assisted` stays `None` in this slice.** Nothing here can produce a non-zero value, and reporting
  the structurally-true `0` would assert a measurement that was never taken (§6.2) — the D-022/D-023
  rule.
- Identities are recomputed on **every observation** and upserted when any key component changed,
  because `scan/apply.py:153-170` refreshes title/locations *outside* the `content_hash` revision gate
  at `:124` (§2.3). A kind that stops being produced is **deleted**, not orphaned — an abandoned
  `exact_quad` row would keep suppressing for a posting that no longer earns one.
- The recount recomputes normalizers in Python rather than re-grouping the same table (§6.3), per
  D-028 — and its claim is narrowed to **staleness**, not normalizer correctness, since both paths
  share the normalizers.
- Identities are backfilled by an **explicit command, not by the migration** (§7).

**Three defects were found in the plan by running its code against the engine, not by reading it.**
Two are fixed in `plan.md`; the third is open and is the next action.

1. **FIXED — the one that would have disabled dedup silently.** `IdentityInputs.locations` was typed
   `str | None` and `normalized_locations` called `json.loads` on it. But `postings.locations_json` is
   a SQLAlchemy `JSON` column (`store/tables.py:67`), so a SELECT returns a *deserialized list*.
   `str(['Dublin','Madrid'])` is a Python repr, not JSON: the parse raises, the `except` swallows it,
   the function returns `None`, no `exact_quad` is ever emitted, and **dedup suppresses nothing,
   forever, with the entire suite green** — because the unit tests hand it a valid JSON string. Fixed
   by typing the field as what the column yields, moving the sole "is this really a list?" judgement to
   the loader boundary (`load_identity_inputs`), deleting the parse, and adding a round-trip test that
   goes red under the original shape. This is the CLAUDE.md fixture rule and D-028 applied to a *type*
   rather than a number.
2. **FIXED — a closed connection.** The dedup block reused `rank_open_postings`'s `conn`, whose `with`
   opens at `cli/top_cmd.py:113` and **closes at `:157`**; scoring and the visible/hidden loop both run
   with no connection open, so it would have raised `ResourceClosedError` on the first real run. It now
   opens its own, and passes `eligible_ids` so it does not pull 23,455 `body_text` rows to deduplicate
   a few thousand leads.
3. **OPEN — every pytest fixture Tasks 6/7/8 name is invented.** `tests/unit/conftest.py` defines
   exactly one fixture (`seeded_events`); the plan names twelve others. The plan fails at *collection*
   as written. Fix by authoring them on the repo's real idiom in `tests/unit/test_top_accounting.py`
   (`env` fixture + module-level `_seed`/`_settings` helpers), then re-running the plan's Self-Review.

**Both external plan reviews were abandoned without a verdict, and the reason is reusable.** deepseek
v4 flash spent its tail reading *alembic's own source* in the uv cache and its harness logged that it
was repeating work without new evidence; gpt-5.6-sol produced no verdict across two attempts (8.5k and
8.3k lines of repo trawling). The brief asked for six attack categories at once over eight files —
**that breadth is what sent both unbounded.** Give a plan reviewer one attack category per dispatch.
Note what did work: all three real defects came from the cheap thing — reading the engine and running
it — not from the reviewers.

---

## D-078 — P6 Slice 1: the plan's test fixtures are now real; eleven defects, all found by running code

**2026-08-10 · P6 Slice 1, planning session 2. Planning is COMPLETE; still no P6 code.** The plan
and spec stay at `.superpowers/sdd/2026-08-09-p6-liveness-dedup/` (gitignored), which is why this
entry exists. D-077 records the design; this records the plan being made executable.

**The open defect from D-077 is closed, and it was bigger than D-077 stated.** Every pytest fixture
Tasks 5–8 named was invented — **sixteen**, not the twelve counted before, and the defect reached
**Task 5**, not just 6/7/8. `tests/unit/conftest.py` defines exactly one fixture (`seeded_events`).

**What replaced them.** Two fixtures the plan authors as real code, not as an instruction to the
implementer to go find equivalents:

- `tests/conftest.py` (**new**, Task 5 Step 1) — `DedupSeed` + `dedup_env` + a `seed_dedup`
  factory (`count=N`, `identical=True/False`, `body=...`).
- `backfill_identities` (Task 6 Step 1), appended to the same file once `identity_queries` exists.

Three placement decisions, each forced by something measured rather than assumed:

- **Root `tests/conftest.py`, not `tests/unit/`.** Task 6's CLI test belongs in `tests/cli/`, which
  cannot see a unit-scoped conftest. Verified empirically that a root conftest resolves for both
  directories and coexists with the existing unit conftest.
- **`backfill_identities` imports inside the function body.** A root conftest is imported for every
  test in the repo, so a module-level `from boardwatch.store.identity_queries import …` would break
  collection repo-wide at the Task 5 commit and at every bisect point between Tasks 5 and 6.
- **A conftest factory, not a `tests/unit/_dedup_seed.py` module.** The repo already solved this:
  `seeded_events` is a factory fixture used by six modules. Reuse beats a new import mechanism whose
  `sys.path` behaviour depends on pytest's import mode.

**Eight further defects, found while authoring the fixtures.** None came from reading the plan.

1. `tests/integration/` **does not exist** (the tree is `cli/contract/fixtures/generalization/perf/
   pipeline/unit`). The CLI test moved to `tests/cli/`.
2. Task 5's own `seeded_posting_id` omitted three NOT NULL columns — `normalized_title`,
   `content_hash`, `body_text`. That is an `IntegrityError` at *runtime*, so D-077's "fails at
   collection" summary understated the blast radius.
3. **`tests/unit/test_schema_head.py` pins the Alembic head** and its docstring requires a new
   migration to state the new head rather than inherit it. Task 5 would have turned `make check` red
   with nothing in the plan explaining why. Now an explicit step. `p1_resume_max_pages` confirmed as
   the current head, so the migration's `down_revision` was right.
4. **Neither `python` nor `boardwatch` is on PATH** (`which python` → not found). Eleven
   `python -m pytest` lines, four `boardwatch` lines and one `python -m alembic` line would all have
   failed. All now `uv run`. The alembic line also carried a literal `<the repo's alembic.ini>`
   placeholder; replaced by `schema_revision()`, which the repo already has and which raises on a
   forked chain — so there is no `alembic` CLI step at all.
5. **The "two identical postings, one ineligible" fixture was unbuildable.** Eligibility reads the
   JD body, so making exactly one of a duplicate pair ineligible requires them to share a
   `content_hash` while their bodies differ — a state production cannot reach, since the hash is
   derived from the body. Reshaped to two identical postings that are *both* ineligible
   (`hidden_ineligible == 2, hidden_duplicate == 0`). The dedup-before-eligibility mutation still
   goes red — it would read 1 and 1 — and the fixture stops lying about a production invariant.
6. **A survivor-election test would have passed for the wrong reason.** With `first_seen_at`
   ascending in posting-id order, an election that ignores `first_seen_at` and sorts by `posting_id`
   elects the *same* row, so the mutation could never go red. The seed now inverts the two orderings
   deliberately (`posting_ids[-1]` is earliest-seen, `posting_ids[0]` has the lowest id). This is
   the D-020 lesson again: derive the mutation from the claim, then check the fixture can express it.
7. Task 8 named a nonexistent call site (`test_run_funnel.py`) for `count_by_source`'s arguments —
   they are in `test_run_funnel_queries.py::_by_source` — and no invented fixture created the `runs`
   row that function requires. The `_ARGS` placeholder is gone.
8. Tasks 7 and 8 named the same fixture two ways (`..._without_backfill` / `..._no_backfill`).

Also corrected: three `...` placeholders in the CLI module (the prior Self-Review said two, in the
wrong step) are now real code, `build_context(ctx.obj).engine` / `utcnow()`, copied from
`track_cmd.py:53`; the File Structure note claimed "Tasks 1–5 are pure … Task 3 adds the schema",
both halves wrong; and the live-smoke step now says to run the ~23k-posting backfill against a
**copy** of the store first, and to confirm the corpus-wide count — a top-20 showing zero
duplicates is equally consistent with dedup working and with dedup being inert.

**The Self-Review was re-run and had itself gone stale.** It still described
`normalized_locations` as `str | None -> str | None` — the shape D-077's JSON-column defect had
left behind — after the signature had been fixed to `list[str] | None -> str | None`. A plan's
self-review is a document like any other and rots the same way (D-017, and the "review the docs you
write" lesson).

**The method, stated because it keeps paying.** All eleven defects across both sessions came from
writing the fixture code and executing it against the real schema and the real ranker — not from
review. This session ran the seed helper against a live migrated DB (every NOT NULL column,
`locations_json` returning a real `list`, identical hashes with distinct `provider_posting_id`,
inverted `first_seen_at` ordering) and then ran `rank_open_postings` to confirm the three states
Task 7's tests assert: an identical pair is both-visible *today* (so `hidden_duplicate == 1` will be
a real change and not some pre-existing filter's work), the degree recipe yields
`hidden_ineligible == 2`, and the distinct pair is a genuine control. What is **not** verified is any
implementation — those modules do not exist; that is TDD's job, and the plan says so.

**Both external plan reviewers remain abandoned with no verdict** (D-077 has the detail). Not
re-dispatched, per that entry's own rule: one attack category per dispatch, or not at all.

---

## D-079 — P6 Slice 1 annotates only; `postings.job_id` is not mutated

**Context.** Dedup could either project its result onto `postings.job_id` (regrouping postings under
one canonical job) or record it beside the data and let readers apply it.

**Choice.** Slice 1 **annotates only.** Identities are stored in a new `posting_identities` table and
suppression is resolved at *read* time; `postings.job_id` is untouched. Design §1.3.

**Alternatives rejected.** Mutating `job_id` in this slice. `applications.job_id` is the tracking key,
so regrouping a posting silently rewrites which job a recorded application belongs to. Job regrouping
and the `applications.job_id` migration are Slice 2's, designed together with their drain.

---

## D-080 — `content_hash` alone may never suppress

**Context.** A shared `content_hash` is the cheapest possible duplicate signal and the obvious first
thing to key dedup on.

**Choice.** `content_hash_only` is computed and stored as an annotate-only kind. It may never suppress.

**Alternatives rejected.** Hash-keyed dedup. Measured on the live corpus: 809 hash-collision groups, of
which **727 span a different title or location** — the Datadog 5843/5846/5849 shape, where one
description text is reused across genuinely different requisitions. Suppressing on the bare hash
collapses different jobs, which is the unrecoverable direction.

---

## D-081 — `exact_quad` is the sole suppressing kind, and its yield is stated honestly

**Context.** Five identity kinds are computed. Which of them may remove a posting from the lead list?

**Choice.** **`exact_quad`** — `(company_id, normalized_title, normalized_locations, content_hash)` —
and nothing else. On the live corpus this suppresses **147 groups / 186 surplus rows / 0.79%** of
23,455 open postings (measured 2026-08-10; see D-094 for why this differs from the design's
pre-registered 131/168/0.72%).

**What is claimed, precisely.** The sampled groups are same-role-different-requisition pairs with
byte-identical descriptions, **not** re-postings. The claim defended is "these represent **one
application decision**", not "these are the same requisition". Design §2.

**Alternatives rejected.** Adding a second suppressing kind for reach. Precision over recall: a leaked
duplicate is counted and recoverable, a suppressed real lead is neither.

---

## D-082 — `cross_host` ships annotate-only, reversing an earlier draft

**Context.** An earlier draft assumed `cross_host` (same normalized company + title + locations across
an ATS and an aggregator) would suppress, on the strength of an unanswered design flag.

**Choice.** `cross_host` ships with `suppresses=False`. It is computed, stored, and its survivor
election is written and directly tested — but it is unreachable from `resolve_duplicates`.

**Alternatives rejected.** Shipping it as a suppressor. Four reasons, any one sufficient: an unanswered
flag is not consent; `core/identity.py:3` already records that cross-ID heuristics may only annotate;
PROGRAM P6 item 1 restricts suppression to *exact* identities and `cross_host` carries neither
`company_id` nor `content_hash`; and a concrete counterexample exists (Acme Greenhouse req ENG-241 vs
LinkedIn req ENG-319 — same company, title and location, different jobs, and string-verify cannot tell
them apart because it re-compares the same three weak fields).

**Re-entry path.** It becomes suppressible once an aggregator posting can be dereferenced to exact
requisition evidence. The election logic already ships and is proven, so enabling it is one boolean.
Design §3.1.

---

## D-083 — No location evidence ⇒ no location-bearing identity, never a `"[]"` sentinel

**Context.** `normalized_locations` needs a representation for a posting that carries no locations.

**Choice.** It returns **`None`**, and the caller emits no location-bearing identity at all — so
`exact_quad`, `cross_host` and `company_title_location` are simply absent for that posting.

**Alternatives rejected.** An `"[]"` sentinel. It makes every location-less posting compare **equal** to
every other one on that component, and the resulting false suppression is undetectable downstream:
string-verify re-compares the same two `"[]"` values and passes, and the §6.3 recount recomputes the
same `"[]"` and agrees. Both guards would agree on the wrong answer. Measured cost of the safe
direction: 7 rows of 23,455. Design §2.1.

---

## D-084 — Three host classes, not two; matching is exact-or-dot-suffix

**Context.** Survivor election across hosts needs to know which URL is authoritative.

**Choice.** Three classes — `ats`, `aggregator`, `unknown` — with `unknown` as the default. `unknown` is
never elected and never dropped. Host matching is `host == known or host.endswith("." + known)`.

**Alternatives rejected.** (a) A binary ATS/aggregator split: it classifies a company's own careers site
as "not ATS" and would drop the company's own page in favour of a job board. (b) Substring matching:
`greenhouse.io.evil.example` and `notgreenhouse.io` would both read as ATS and could win election.
Design §3.

---

## D-085 — Allowlist URL normalization, not a denylist

**Context.** `normalize_url` must strip tracking parameters while keeping identity-bearing ones
(`gh_jid` is load-bearing in real posting URLs).

**Choice.** An **allowlist** of identity params; everything else is dropped.

**Alternatives rejected.** A denylist of tracking params. The direction was chosen by *which failure is
detectable*: a denylist that has not yet learned a new tracking param silently **splits** one posting
into two, which nothing catches; an allowlist that has not learned a new identity param **merges** two
postings, which string-verify then catches. Merge-then-verify is the recoverable failure. Design §4.1.

---

## D-086 — Survivor election never consults score; `posting_id` is a load-bearing tiebreak

**Context.** When a group of duplicates is found, one row survives.

**Choice.** Election is `(host_class, earliest first_seen_at, lowest posting_id)`. Score is never a
tiebreaker.

**Alternatives rejected.** Electing the highest-scoring row. Scores move whenever the profile, taxonomy
or ranker changes, so the survivor's identity would change between runs — and Gate P6 requires
measuring duplicate leakage across a 7-day window, which a moving survivor makes meaningless.
`posting_id` is not decoration: `first_seen_at` is second-resolution and a single board's postings are
inserted in one pass, so ties are routine. Design §5.1.

---

## D-087 — Instrumentation is completeness-gated, not existence-gated

**Context.** The funnel's `unique` counter reads stored identities. When may it report a number?

**Choice.** Only when **every** open posting carries a row at the current
`IDENTITY_ALGORITHM_VERSION`. Otherwise `None`. An algorithm-version bump therefore degrades `unique`
to `None` until a re-backfill.

**Alternatives rejected.** `if identities:`. A single backfilled posting in a 23,455-posting corpus is
indistinguishable from a complete one under a truthiness check, and the number that falls out would be
printed in the same column as a real measurement. Design §2.2.

---

## D-088 — `assisted` stays `None` in this slice

**Context.** `SourceOutcome.assisted` credits a source that arrived second for a posting another source
won. With dedup now live, it is tempting to report it.

**Choice.** `assisted` reports **`None`**, even on a complete corpus with live suppressions.

**Alternatives rejected.** Reporting `0`. `exact_quad` is keyed on `company_id` and sources *are*
`company_id`, so no suppression this slice can produce crosses a source boundary — `assisted` is
structurally incapable of being non-zero. `0` would assert "we looked and no source arrived second";
the honest statement is "no mechanism exists that could have counted one". This is the D-022/D-023 rule,
which this program has already been bitten by twice. Design §6.2.

---

## D-089 — Identities are upserted on every observation; a kind that stops being produced is deleted

**Context.** `scan/apply.py` refreshes a posting's title and locations on *every* observation
(`_mutable_fields`, "regardless of content_hash") while gating a *revision* on `content_hash` alone. So
a retitle with an unchanged body moves an identity key without producing a revision.

**Choice.** `write_identities` makes a posting's current-version rows match the computed set **exactly**
— inserting, updating **and deleting**.

**Alternatives rejected.** Insert-if-absent. It leaves the superseded key stored forever, which makes
`identities verify` permanently red on a legitimate update — and a permanently-red check is a discarded
check. Deletion is part of the same contract: losing location evidence drops three kinds (D-083), and an
orphaned `exact_quad` row would keep suppressing on behalf of a posting that no longer earns one.
Design §2.3.

---

## D-090 — The ranker is completeness-gated for reproducibility, not safety

**Context.** The ranker skips suppression entirely unless identities are complete. It would be easy to
justify this as a safety measure; that justification would be wrong, and worth stating so it is not
repeated.

**Choice.** Gate the ranker on completeness, and record that the reason is **reproducibility**.

**Why not safety.** Partial coverage cannot over-suppress: a posting with no identity row joins no
group and is never suppressed. The worst a partial view does is elect a survivor from the covered
subset while the true survivor sits uncovered and stays visible anyway — which over-shows, the
acceptable direction. The real reason is that *which* rows get suppressed mid-backfill depends on
backfill order, and Gate P6 requires re-deriving 20 sampled suppressions from the data. A suppression
whose survivor election did not see all the candidates cannot be re-derived. The cost of the gate is one
command.

---

## D-091 — The recount recomputes in Python, and claims staleness only

**Context.** `identities verify` is the D-028 "count the deliverable through a different path" check.

**Choice.** Path A reads stored `posting_identities` rows; Path B **recomputes** them from `postings` in
Python. It lives in `identities verify`, not in `boardwatch verify` (which is run-artifact scoped), and
exits 1 on missing identities as well as stale ones.

**What it does NOT claim.** It is a staleness and consistency check, **not** proof that the normalizers
are correct — both paths call the same `normalize_title` / `normalized_locations`. Re-grouping the same
table a second way would have been the D-028 tautology this program has already shipped and deleted
once. Design §6.3.

---

## D-092 — Identities are backfilled by an explicit command, not by the migration

**Context.** The `p6_posting_identities` migration could populate the table as it creates it.

**Choice.** The migration creates the table and **does not backfill**. `boardwatch identities backfill`
is a separate, re-runnable command.

**Alternatives rejected.** Backfilling inside `upgrade()`. Recomputing identities for a 23k-row corpus
is not a side effect anyone wants from `alembic upgrade`, and it could not be re-run after an
`IDENTITY_ALGORITHM_VERSION` bump. Until the command is run the funnel honestly reports `not
instrumented` rather than a partial number. Design §7.

---

## D-093 — Slice 1 does NOT meet Gate P6, and makes only one of its four clauses measurable

**Context.** It would be easy to read "dedup shipped" as "Gate P6 met".

**Choice.** State plainly, in the spec and in `STATE.md`, that Slice 1 does not meet Gate P6.

**What it does.** It makes the funnel's `unique` counter a measured number instead of `not
instrumented` — one clause. The other three are operational measurements over a running system: 7-day
duplicate leakage, zero dead postings reaching the lead list, and a 20-sample suppression audit. The
build made them measurable; it did not meet them. Slice 2 is the durable ledger + drain + job
regrouping; Slice 3 is applied-state suppression + liveness. Design §0.

---

## D-094 — P6 Slice 1 BUILT (unattended run): five more plan defects, three of them tests that could not fail

**2026-08-10, unattended launchd run starting 03:10. All nine plan tasks executed on branch
`p6-slice1`. NOT merged, NOT reviewed.** `main` is untouched. Execution mode was inline
(`superpowers:executing-plans`), decided in advance: subagent-driven development is the better mode
when a human reviews between tasks, and there was no human.

**Constraints honoured, all three:** branch-only (no merge, no PR, no force-push); every live-data
step against a **copy** of the store (`/tmp/bw-smoke-copy`), with the live store never written to;
and no speculative fan-out, no D-072 benchmark, no re-dispatched plan review.

### The plan was executable, and the fixtures held

D-078's claim that the seeding was verified against the real schema held up: `seed_dedup` was
re-run before the table existed and produced exactly what it promised — `locations_json` reading
back as a Python `list`, one shared `content_hash` with distinct `provider_posting_id`, and
`first_seen_at` **inverted** against `posting_id` order. The three ranker preconditions Task 7
asserts also held. Every mutation check the plan specified was run in isolation with a cleared
`__pycache__` (D-025), and all of them were caught by the *named* test — except the four below.

### A fifth defect, found by `make check` — and the reason the gate is the gate

**The first full-branch gate run came back RED: `test_migrations_match_metadata` failed**, and it
was right to. `tables.py` declares `posting_identities`' UNIQUE constraint **unnamed**, letting
`metadata.naming_convention` render it as
`uq_posting_identities_posting_id_kind_algorithm_version`. The plan's migration text hard-codes
`name=op.f("uq_posting_identities_posting")`. The two disagree, so alembic's `compare_metadata`
saw permanent drift between the migrated database and the metadata — a defect that would have
poisoned every future autogenerate diff, not just this one test.

Fixed by writing both constraint names in their full convention-rendered form
(`uq_posting_identities_posting_id_kind_algorithm_version`,
`ck_posting_identities_identity_kind_enum`), which is what `p0_applications.py` and
`8df3b3809bba_schema_v1.py` already do. The CHECK name was wrong the same way and did *not* fail
the test — alembic does not reflect SQLite CHECK constraints — so it was corrected on the same
reasoning rather than left because nothing complained. Mutation-confirmed: restoring the old name
turns `test_migrations_match_metadata` red on its own.

**Why this one matters out of proportion to its size.** Every other defect this session was caught
by running code during TDD. This one was invisible to all of it: the migration applied cleanly, the
table worked, all five schema tests passed, the 23,455-posting backfill ran, and `identities
verify` exited 0. Only the full gate saw it. That is the whole argument for `make check` being the
only gate, and for never reporting a result before it has run.

### Four defects, found by running the plan's own code

1. **Task 3's separator test could not fail.** It shifted a word between `title` and `locations`
   to prove `_SEP` prevents `("ab","c")` and `("a","bc")` colliding. But `normalized_locations`
   emits `json.dumps`, so the locations component always arrives wrapped in `["..."]` and
   delimits itself; the two keys stayed distinct with `_SEP = ""`. **The only boundary where two
   *bare* components meet is company_id↔title.** Retargeted there (company 10 + title `"1data"`
   vs company 101 + title `"data"`, both concatenating to `"101data"`); it now goes red under the
   mutation.

2. **Task 4's `test_no_suppression_anywhere_ever_carries_the_cross_host_kind` could not fail.**
   Its two `_p(3)`/`_p(4)` rows shared the cross pair's normalized company, title and location, so
   all three unsuppressed rows landed in **one** `cross_host` group with two ATS members — which
   `elect_cross_host_survivor` correctly declines as ambiguous. The test therefore stayed green
   with `cross_host.suppresses` flipped to `True`, i.e. green against the one mutation it exists
   to catch. Fixed by giving the exact_quad pair a different company name and title, and by adding
   `assert result` — `all()` over an empty tuple is vacuously true, a second way the same test
   could have passed for nothing.

3. **Task 4's posting_id-tiebreak test could not isolate what it claimed.** Its docstring said
   that without the tiebreak "the survivor depends on dict ordering". It does not:
   `resolve_duplicates` groups over `sorted(by_id.items())`, so members always reach `_elect` in
   posting-id order and `min` returns the lowest id on a tie regardless. Dropping the `posting_id`
   term left the whole suite green. Fixed by adding
   `test_elect_breaks_a_first_seen_tie_by_lowest_posting_id`, which calls `_elect` directly with
   members deliberately out of order, and by correcting the misleading docstring rather than
   leaving it to mislead the next reader.

4. **Task 4's `_cross` helper passed `provider_posting_id` twice** — once positionally in its
   defaults and once through `**over`, which the ENG-241 test overrides — a `TypeError` at run
   time. Fixed by merging `over` into a dict so the override wins.

Also: one *mutation* in this session's own Task 6 checklist was mis-specified by the implementer
(removing the `posting_ids=[]` early return is compensated by `.in_([])`, so nothing changed).
Corrected to also make the filter truthiness-based, at which point the test went red as intended.
**A mutation that survives is not automatically a bad test — check the mutation expresses the
claim first.** And `Sequence` was deferred out of the Task 5 conftest import block to Task 6,
where it is first used, because ruff's F401 would otherwise have failed the Task 5 commit.

### What was measured, and the number that moved

On the copy: **23,455** open postings, **117,254** identity rows, `identities verify` **exit 0**,
`identities_complete` **True**, and **147 groups / 186 surplus rows / 0.79%** suppressed — all
`exact_quad`, no survivor itself suppressed.

**That is more than the pre-registered 131/168/0.72% baseline, and the cause was found before
committing** rather than explained away after. Re-running the grouping over the same corpus with
**raw** `locations_json` reproduces **136/174/0.74%**, matching the design's own *unguarded*
baseline (135/173/0.74%) to within one group. The delta is location **normalization** — sort,
case-fold, whitespace-collapse, exactly what design §2.1 specifies — which merges a further 11
groups / 12 rows; measured directly, **12 of the 186** suppressions have raw location lists that
differ. Title normalization contributes nothing: 0 of 186 have a stored `normalized_title`
disagreeing with `normalize_title(title)`.

~~**Precision was re-checked through a second path**, comparing company_id, normalized title,
normalized locations and normalized body outside `_verify_quad`: **0 of 186 failures**.~~
**RETRACTED 2026-08-10 — see D-097.** `_verify_quad` *is* those four comparisons with those
normalizers, so the check could not disagree. Sampled groups are same-role-different-requisition
pairs — identical titles, identical locations, distinct `provider_posting_id`; that observation
stands. ~~And the funnel's per-source `unique` reconciles independently: sum(open) − sum(unique) =
**186** across 118 sources, equal to the resolver's own count~~ — **RETRACTED 2026-08-10, same
entry**: `unique_by_company` is built from the same `identity_rows` and the same `resolve_duplicates`
output that produced the count, so that identity holds for every possible database state. `assisted`
was `None` on all 118, which is unaffected.

**Marked, not rewritten** — this log is append-only, so the original wording stays legible and the
withdrawal is annotated in place. Recorded here because the retraction commit itself missed this
entry: the grep that was supposed to find every restatement was piped through `head -30` and the
match on this line sat below the cut. **A truncated grep is not a negative result** — the same rule
that already applies to a failed command applies to a clipped one.

### Not finished

The `boardwatch top --top 20` half of Task 8's live smoke did not complete — it ran >40 minutes
against the 23,455-posting copy (it pays for `run_preflight` + `run_eligibility` over the whole
corpus) and was still running at close. **This is cosmetic:** the corpus-wide figure it exists to
sanity-check was obtained two other ways, and the plan itself notes that a top-20 usually shows 0
duplicates and so cannot distinguish working dedup from inert dedup. Recorded as skipped rather
than quietly dropped.

**Gate P6 remains NOT met** (D-093), and no clause of it was claimed.

---

## D-095 — P6 Slice 1 reviewed by three independent reviewers; fourteen findings fixed, two rejected

*2026-08-10, post-overnight-build fix session.*

**Context.** The branch was built unattended and gated green, but nothing had been reviewed. The P2
item 4 whole-branch review had caught a CRITICAL that every per-task review missed, so this
comparable checkpoint got the same treatment — widened to three reviewers to see whether the extra
lanes pay for themselves.

**Choice.** Three reviewers in parallel on the pinned range `main..3a35819`: fresh-context Opus 5
(whole-branch, read-only), DeepSeek v4 flash (full diff), GPT-5.6 sol at high reasoning (repo
access, read-only sandbox). Verdicts REWORK / REWORK / SHIP-WITH-FIXES. Every claim was verified
against the code before being acted on.

**Was the third lane worth it?** Yes, and not for the reason expected. **Corrected 2026-08-10 after a
docs review:** an earlier version of this entry said "seven findings" and "the reviewers overlapped on
exactly one finding". Both were wrong, and the second was load-bearing for this entry's own
conclusion. The full enumeration — **fourteen** findings fixed, each with an attribution (a second
docs review caught that the corrected entry still miscounted its own table, 12 against 14 rows; the
count is now stated as the row count and nothing else):

| Finding | Found by | Fixed in |
|---|---|---|
| `_verify_quad`'s `None == None` hole | **all three** | `dedup.py` |
| `load_identities` corpus-sized `IN` list (32,766 cap) | **DeepSeek + Opus** | `identity_queries.py` |
| `normalize_title` C++/C#/C collision | GPT-5.6 sol | `normalize.py`, D-096 |
| migration imports the live catalog into its CHECK | GPT-5.6 sol | `p6_posting_identities.py` |
| `ValueError` handler in `normalize_url` never exercised | GPT-5.6 sol | test |
| `host_class` precedence in `_elect` untested | GPT-5.6 sol | test |
| drain bounded by the rank `limit` | Opus | `top_cmd.py` |
| `company_id` untested in the only suppressing key | Opus | test |
| the two tautological verification claims | Opus | D-097, METRICS/STATE |
| `normalize_url` param-order test vacuous | Opus | test |
| three `all()`-over-empty assertions | Opus | test |
| bare `KeyError` for a resolver-less kind | Opus (minor, elevated) | `dedup.py` |
| `locations_json = [null]` as location evidence | DeepSeek | `identity_queries.py` |
| `split("_")` field-neutrality test vacuous | DeepSeek | test |

So the overlap is **two** findings, not one — and the second overlap (the `IN`-list cliff) is arguably
the most consequential of the whole set, since it made `identities verify` and the funnel sweep a
scheduled failure as the corpus grows past 32,766 open postings. It was previously unattributed here,
which is exactly the gap that let the miscount stand. Each reviewer still found things neither other
saw, so the conclusion holds — but on a corrected count.

**Two findings were rejected as factually wrong**, which is the cost of the extra lanes:

1. DeepSeek: *"`normalize_body` is ASCII-only (`[^a-z0-9 ]`), so `["Remote","远程"]` collides with
   `["Remote"," "]`."* It confused `normalize_body` with `normalize_company`. Measured:
   `normalized_locations(["Remote","远程"])` returns the JSON string `'["remote", "远程"]'` (escaped
   as `远程`, since `json.dumps` defaults to `ensure_ascii=True`), while
   `normalized_locations(["Remote","  "])` returns `'["", "remote"]'`. Two different keys, so no
   collision — the non-ASCII text is preserved, not stripped.
2. GPT-5.6 sol: *"survivor election prioritizes host class before `first_seen_at`, contrary to the
   stated earliest-seen rule."* D-086 explicitly ratifies `(host_class, earliest first_seen_at,
   lowest posting_id)` and the docstring matches. Its sub-claim was kept: no test covered the
   precedence, because every `exact_quad` test seeds one host.

**Alternatives rejected.** Trusting the reviewers' severities. DeepSeek rated the `_verify_quad`
hole a BLOCKER on precision grounds; it is not, because `_verify_quad` re-compares company, title,
locations **and body** against current data, so anything it clears still shares a byte-identical
normalized body. The real damage was narrower (a D-083 invariant violation), and mis-rating it
would have justified emergency work on the wrong thing.

---

## D-096 — The C++/C# fix folds punctuation into words; it does NOT add a raw-title comparison

*2026-08-10.*

**Context.** `normalize_title` folds `[\W_]` to spaces, so `C++ Developer`, `C# Developer` and
`C Developer` all normalize to `c developer`. Since `_verify_quad` re-runs the same normalizer, the
string-verify agrees with the key on the wrong answer — the exact failure shape D-083 names.

**Choice.** Fold `+` and `#` to words (` plus `, ` sharp `) inside `normalize_title`, before the
punctuation strip. Bump `IDENTITY_ALGORITHM_VERSION` to `p6.2` as any normalizer change requires.

**Alternatives rejected — and this one was rejected by measurement, after being recommended.** The
first proposal was to add a case-folded, whitespace-collapsed **raw title** comparison to
`_verify_quad`, so the verify would stop depending on the key's own normalizer. Measured against the
live corpus first: **8 of 147 suppression groups already differ in raw title, and all 8 differ only
in punctuation, spacing or case on the same role** (`Mobile Expert - Bilingual…` vs
`Mobile Expert, Bilingual…`; `Store-in-Store` vs `Store in Store`; `Javascript` vs `JavaScript`;
`IC design` vs `IC Design`; `Manager, Clinical Study Lead` vs `Manager Clinical Study Lead`). A raw
comparison would have leaked **6 of those 8 real duplicates** to defend a collision the corpus does
not contain. The shipped fix costs nothing: 123 open titles contain `+` and 16 contain `#`, and
**none of them sits in any suppression group**, so the measured figure stays 147/186. Both facts are
now pinned by tests — one asserting C++/C#/C produce different keys, one asserting the five real
punctuation-noise pairs still collapse.

**This RETIRES a previously pinned ACCEPTED caveat, deliberately.**
`tests/unit/test_normalize.py::TestNormalizeTitle::test_caveat_cpp_collapses_to_c` asserted
`normalize_title("C++ Developer") == "c developer"` with the comment *"Pinned ACCEPTED caveat: '+' is
stripped, so C++ titles collide with C titles."* So the collision was known and accepted — but it was
accepted when `normalize_title` fed no suppressing key and a title collision was cosmetic. P6 slice 1
made it a component of `exact_quad`, the only kind that can suppress, which changed the consequence
from "two titles look alike" to "a real, different posting is hidden". The caveat is therefore
re-ratified against its new stakes rather than inherited: the test is replaced by
`test_language_punctuation_no_longer_collapses`, which pins the new behaviour and records why.

**The two transferable lessons.** (1) A fix aimed at a theoretical failure must have its blast radius
measured on real data before it ships — this one would have traded live recall for hypothetical
precision, and only the corpus could say so. (2) **A pinned caveat is scoped to the consumers it was
pinned against.** When a normalizer acquires a new consumer with harsher consequences, every accepted
caveat on it needs re-checking; `grep` for existing tests of a function before changing it, because
the accepted-caveat tests are where the prior reasoning is recorded and they are easy to miss — this
one was found by `make check`, not by the focused test modules.

---

## D-097 — `_verify_quad` rejected nothing on the live corpus; "string-verified" is not precision evidence

*2026-08-10.*

**Context.** Re-deriving the suppression count in SQL (grouping stored `identity_key`s, calling no
Python normalizer and no resolver) returned **147 groups / 186 surplus rows** — identical to
`resolve_duplicates`.

**Choice.** Record the agreement as a finding rather than as reassurance. Equal counts mean
`_verify_quad` rejected **zero** members on the 2026-08-10 copy of the live store. Scoped to that
snapshot deliberately: "has never once fired" overreaches one corpus, and the function does reject in
`tests/unit/test_dedup_resolver.py` where a divergent body is forged.

It is not broken. It is redundant with the key on this data, because it re-runs the same normalizers
the key was built from. So it genuinely defends against a SHA-256 collision and against stale stored
identities, but **not** against the normalizers being lossy — which is precisely how the C++/C#
collision (D-096) got in. Nothing may cite "string-verified" as evidence of precision it cannot
supply. Precision evidence has to come from a comparison the key does not already make: the raw-field
audit in METRICS.md is the one that can disagree.

**Alternatives rejected.** Deleting `_verify_quad` as dead weight. It is the only guard that fires **in
the read path**, and staleness is a live condition (D-098); it costs one pass over a small group.
Corrected 2026-08-10 — an earlier draft said "the only guard against a stale stored identity", which
D-091 falsifies: `identities verify` detects staleness by recomputing (Path B) and exits 1 on it. The
distinction is the whole point, though — `verify` only catches it when somebody runs it, and nothing in
the automated path does.

---

## D-098 — Suppression reports when it is OFF; wiring backfill into the pipeline is Slice 2

**Context.** `write_identities` has exactly one caller in `src/` — the manual
`boardwatch identities backfill`. Nothing in the scan or pipeline path writes identities. So on any
run that discovers ≥1 new posting, `identities_complete()` is False, suppression is silently
disabled and `unique` reports `None` for every source; on a run that only mutates existing postings,
coverage stays complete and suppression runs on **stale** keys. The 147/186 figure was produced by a
manual backfill on a copy — a sequence that does not occur in the shipped automated path.

**Choice (ruled by Mit).** Ship the operator-visible notice now; defer wiring the backfill into the
pipeline to Slice 2. `top` prints, whenever coverage is incomplete, that suppression is OFF and
which command fixes it. `RankedResults` carries `identities_are_complete`, defaulting to **False** —
the noisy direction, so a caller that forgets to set it gets "disabled" rather than a silent claim
that the subsystem ran.

**Why the notice is not cosmetic.** `hidden_duplicate == 0` is ambiguous between "no duplicates
found" and "dedup never ran", and the second is the *common* case, not the corner. Without the notice
an uninstrumented run is indistinguishable from a clean one — the same "a rule that cannot fire is a
monitoring failure, not a conservatism feature" problem the keystone invariant exists for.

**Alternatives rejected.** Wiring the idempotent backfill into the pipeline now. It is the better end
state and makes the Gate P6 `unique` clause genuinely measurable, but it adds a **second corpus-wide
`body_text` load** beside the one `count_by_source` already does, and belongs with Slice 2's ledger
work where that load can be paid once rather than twice.

**Cost corrected 2026-08-10.** An earlier draft justified this deferral with "it adds the measured
471 MB peak RSS / 9.4 s to every run". Those figures belong to `count_by_source`'s survivor sweep,
which **already runs on every run**, so wiring in the backfill cannot add them. The backfill's own
measured cost is **41 s** cold (METRICS.md). Citing the
wrong subsystem's number — ~4× too small — in the sentence that rules the work out until Slice 2 is
precisely the kind of unchallengeable-looking figure this log exists to prevent. (A "10.3 s on a warm
copy" figure was also cited here and has been removed: it was measured in the fix session but never
recorded in METRICS.md, so it could not be checked from the file that owns per-run numbers.)

---

## D-099 — Gate batching stays allowed; the per-task fast-check set must include the schema guards

**Context.** The overnight run batched `make check` over Tasks 5–8 rather than gating each task, and
committed before the batched gate returned. That gate came back RED on
`test_migrations_match_metadata` — a constraint-naming drift the standing suite **already covered**.
The per-task fast checks (ruff, `mypy --strict`, the generalization checker, plus the focused test
modules) did not include `test_store.py`, so the defect survived four commits.

**Choice (ruled by Mit).** Do **not** ban batching. Batching a ~18-minute gate over several tasks is
the correct wall-clock trade and the pinned-worktree pattern that made it safe is worth keeping. The
ruling is narrower: the per-task fast-check set **must** include the schema/metadata guard tests —
`tests/unit/test_store.py` and `tests/unit/test_schema_head.py` — for any task that touches
`tables.py`, a migration, or the Alembic head. They run in seconds.

**Alternatives rejected.** A blanket "gate every task" rule. Five ~18-minute gates is most of an
unattended night, and the failure here was not that the gate ran late — it was that the cheap check
which would have caught it was not in the per-task set. Fixing the set is the surgical repair;
banning batching pays a large wall-clock cost for a defect that a two-second test catches.

**Also recorded, because it is the real cause of the commit order.** The run committed Tasks 5–8
before their gate returned. "Never commit on a red gate" is unenforceable when the gate result
arrives after the commit; the enforceable version is "do not commit a schema change without running
the schema guards", which is what this ruling installs.

---

## D-100 — P6 Slice 1 merged to `main`; Gate P6 clause 3 is MET, not merely measurable

*2026-08-10, on Mit's explicit authorization after the three-reviewer review.*

**Context.** Slice 1 was built unattended, reviewed by three independent reviewers, and every finding
fixed (D-095 … D-099). `make check` green at `f2f2430`. Mit authorized the merge.

**Choice.** Fast-forwarded `main` from `1c0747e` to `f26c87a` and pushed. **Fast-forward, not squash**,
so the 19 commits keep their individual history: each is one logical change, the TDD trail is legible,
and the review-fix commits stay distinguishable from the original build. Previous phases squashed via
PR; that collapses a nine-task TDD sequence into one commit and was not worth it here.

**Also recorded: Gate P6's third clause is MET.** The gate asks for "a deliberately-injected
hash-collision test proving the wrong job cannot be deduped".
`tests/unit/test_dedup_resolver.py::test_string_verify_blocks_suppression_when_bodies_diverge` forges
`identity_key` equality across two divergent bodies and asserts the group is refused; two adjacent
tests reproduce the real Datadog 5843/5846/5849 shape (one `content_hash`, three requisitions, 809
such groups live of which 727 span a different title or location). That clause is a **test**, not an
operational measurement, so it is satisfied outright rather than "made measurable".

**Alternatives rejected.** Continuing to report all four clauses as outstanding, per the earlier
"Slice 1 makes exactly one of four clauses measurable" line. That undersold a clause that is actually
met and would have left a future session re-building a test that exists. D-093's framing (Slice 1 does
not meet Gate P6 *as a whole*) is unchanged and still correct.

**Carried forward, not done.** The live store needs `boardwatch identities backfill` after this merge:
D-096 bumped `IDENTITY_ALGORITHM_VERSION` to `p6.2`, so the existing `p6.1` rows stop being read and
suppression stays off until the backfill runs. `top` now says so out loud (D-098), which is the only
reason this is a follow-up rather than a silent regression.

---

## D-101 — Gate P6 clause 4 is MET: 20/20 sampled suppressions are genuine duplicates

*2026-08-10, on the live store immediately after its first backfill.*

**Context.** Gate P6 requires "a suppression audit of 20 sampled suppressions confirming each was a
genuine duplicate or policy skip". Until the live store was backfilled there was nothing real to sample.

**Choice.** Sampled **deterministically** — every 7th group ordered by `identity_key`, first 20 — rather
than randomly, so the sample is reproducible and a future re-run audits the same groups. Read all 20 by
eye. **All 20 are same-company, same-title, same-location, distinct `provider_posting_id`.** Zero false
positives. Spread over 13 employers and both software and non-software roles, so it is not an artifact of
one board's requisition scheme.

**The one group that earns its own line.** Duolingo `6469`/`6470` ("Software Engineer II, Android")
differ **only** in location list order: `["Pittsburgh, PA", "New York, NY"]` against
`["New York, NY", "Pittsburgh, PA"]`. Only the sort in `normalized_locations` catches it. This is the
empirical justification for design §2.1's sort + case-fold, and it explains the shipped 186 exceeding the
raw-grouped 174: **the delta is real duplicates, not over-suppression.** The pre-registered baseline
looked "safer" only because it was blind to this class.

**Alternatives rejected.** A random sample. Reproducibility matters more than statistical purity for an
audit that a later session may need to re-run against a changed algorithm version — and with 147 groups
and a uniform failure mode, a systematic sample is no weaker here.

**Gate P6 now stands at two of four clauses met** (this one and the injected hash-collision test, D-100).
The remaining two — 7-day duplicate leakage ≤ 5%, and 0 dead postings reaching the lead list — need a
running system and liveness (Slice 3) respectively. Neither is a build gap in Slice 1.

---

## D-102 — D-072 (model-tier benchmark) is deferred indefinitely

*2026-08-10, ruled by Mit.*

**Context.** D-072 agreed a benchmark to compare model tiers on the 173-row eligibility answer key, which
would also have picked the final gate's default judge model. It has been carried as an owed next-action
since 2026-08-08 across several sessions.

**Choice.** **Deferred indefinitely.** It is no longer an owed item and must not be carried forward as
one, listed as a next action, or treated as blocking any phase.

**Consequences, stated so nobody re-derives them as blockers.** The final eligibility gate keeps whatever
default judge model it currently ships with, chosen without benchmark evidence; that is now an accepted
condition rather than a gap. Gate P5 is unaffected — it is MET on the deterministic engine (D-073) and the
agent-lane gate is additive (D-074).

**Alternatives rejected.** Keeping it as a low-priority backlog item. A perpetually-deferred "next
action" in a read-first document is worse than no entry: it costs every future session the same triage and
makes the real next action harder to find. Recorded as closed-by-decision instead.

---

## D-103 — P6 Slice 2: the ledger is a current-state row per job, `seen` suppresses on a TTL, and the policy stamp never auto-reopens

*2026-08-10. Design at `.superpowers/sdd/2026-08-10-p6-slice2-ledger/design.md` (gitignored — hence this
entry). Spec: PROGRAM §3.P6 item 4.*

**One row per job, upserted — not an append-only events table.** The spec asks for *monotonic upserts*, and
an append-only log cannot be upserted; "monotonic upsert" describes a current-state row. The append-only
trail exists where it is actually needed: `job_grouping_events` (D-104), the half that mutates a key
another table reads. Recorded so a later session does not re-derive a `job_disposition_events` table and
report it as missing.

**Rank is `seen` 0 < `skipped` 1 < `built` 2.** Against a **live** row an upsert may raise or hold, never
lower. Against a non-live row (expired or reopened) any disposition may be recorded, which is what makes an
expiry or a reopen mean anything. The one case that reads like a breach and is not: re-recording `seen` on a
live `seen` row refreshes `expires_at` — monotonicity is over the rank, not the timestamp.

**One liveness predicate, shared by the reader and the writer.** `core.ledger.is_live` is the only
definition, and `plan_upsert` calls it rather than trusting the caller to pre-filter. A reader that thinks a
row is expired while the writer thinks it is live both hides a job and refuses to re-decide it — a job that
can never be surfaced again. Lazy read-time expiry throughout: nothing sweeps, nothing deletes, and the
drain sets `reopened_at` instead of deleting, so a drained decision is still on record.

**`seen` suppresses for a TTL — ruled by Mit**, from three options put to him with the measured evidence.
Every job the ranker surfaces as a lead is recorded `seen` with `expires_at = now + seen_ttl_days` (7), so
the daily queue advances past what was already shown and re-enters after the TTL in case it was missed or
the JD moved. **The alternatives rejected:** a non-suppressing bookkeeping `seen` (safer and less
surprising, but it would have had no reader in this slice and the spec's TTL machinery would be exercised
only by tests), and `seen` written only on an aborted run (narrowest, but it would almost never fire, which
this program treats as a monitoring failure in itself).

**Measured consequence of that ruling, stated because it is real and reversible.** The ranker is the
`seen` writer — one writer, so `top` and the pipeline cannot drift on what "surfaced" means — which makes
`top` mutate suppression state. Two `top` invocations inside the TTL therefore show different rows. The full
gate quantified the blast radius: **four tests in four modules** broke, every one a caller that ranks twice
against the same corpus. Each was isolating a different mechanism and now opts out with
`--include-handled`; one could not, because it asserts full `RankedResults` equality and a drained row
carries `handled_as='seen'`, so it releases the ledger between calls via the drain's own reopen path. If
`top`'s behaviour turns out to be surprising in practice, the cheap reversal is to move the `seen` write
from `rank_open_postings` into the pipeline only; the disjointness guarantee does not depend on it, because
`built` alone carries that.

**The policy stamp is reused, and a mismatch is reported rather than acted on.** `policy_version` is a
digest of the run manifest's own five components (`code_fingerprint`, `config_hash`, `profile_row_hash`,
`profile_facts_hash`, `rules_hash`) — nothing new is hashed, because "what would make us re-decide this" and
"what makes two runs comparable" are the same question and P0 item 4 already answered it. **A stamp
mismatch never re-opens a disposition automatically.** Auto-expiry on mismatch would rebuild the entire
shortlist on any settings tweak — the 465-item-queue failure in a different costume — and an automatic
re-open cannot be reviewed before it happens. `ledger show --stale` lists them; `ledger reopen --stale`
releases them. Accepted cost, stated plainly: a `built` lead whose résumé has since been rewritten stays
suppressed until somebody runs the drain.

**Enforced twice, per CLAUDE.md.** Typed at the write site (`UnknownDisposition`,
`UnknownDispositionReason`, `MalformedDisposition`) and again as three CHECK constraints, so a direct INSERT
cannot invent a bucket or store a permanent decision with no stamp. The permanence CHECK states **both
tiers explicitly**: the obvious biconditional `(disposition IN permanent) = (policy_version IS NOT NULL AND
expires_at IS NULL)` looks equivalent and is not — it constrains only the permanent side, so a `seen` row
carrying a policy stamp *and* no TTL satisfies it (0 = 0). The store tests caught that before it shipped.

**Three reasons, not one per ranker filter** (`lead_built`, `unshippable_artifact`, `surfaced`).
`hidden_hard_filter`, `hidden_non_swe`, `hidden_ineligible`, `hidden_below_cutoff` and `hidden_duplicate`
are recomputed deterministically every run and already counted in the funnel; persisting them would be
~20,000 writes a run with no reader.

---

## D-104 — Job regrouping: the survivor's job wins, and a tracked group is refused whole

**Context.** D-079 deferred the projection of dedup onto `postings.job_id` out of Slice 1, because
`applications.job_id` is the tracking key. This is that projection.

**Why it is worth doing at all**, since read-time suppression already collapses duplicates: that
suppression is completeness-gated, and D-098 established completeness is the *exceptional* state. Discover
one new posting and suppression switches off — at which point a duplicate of an already-built job carries no
disposition of its own and is built again. Regrouping makes the grouping durable in the data, so a
disposition covers the group whether or not the read-time gate is open. It is also the only thing that makes
D-081's "one application decision" claim true of the store rather than only of the read path.

**Choice.** The canonical job is the job of the survivor `resolve_duplicates` already elected under D-086
`(host_class, first_seen_at, posting_id)`. **No second election**, so a regrouping can never disagree with a
suppression about which row is authoritative.

**The refusal guard, and why it refuses the whole group.** A group is left ungrouped when any
**non-survivor** member's job carries an `applications` or `artifacts` row.
`store/run_funnel_queries.py:472` joins `applications.job_id == postings.job_id` and
`reports/export.py:73` selects `applications.job_id` as its tracked set, so a merged loser job keeps its
application row and loses every posting pointing at it — **a real applied count silently becoming wrong**,
this program's worst failure shape. `UNIQUE(job_id, attempt_no)` also means a future "move the application
too" collides the moment two members each have an attempt 1. Refusing the *whole* group rather than the
offending member is deliberate: a partially-merged group is a third state nothing downstream understands and
it makes the outcome iteration-order-dependent. A tracked **survivor** job refuses nothing, since nothing
moves off it — that is the common good case (you applied via the row dedup already elected).

Measured 2026-08-10: `applications` = 0 rows, and all 44 `artifacts` rows have `job_id IS NULL`
(`record_artifact`'s two callers in `src/` never pass it). The guard is therefore **latent, not
unreachable** — the distinction the "dead for bundled ≠ unreachable" lesson turns on — and it ships with
tests.

**Write order.** `job_grouping_events` INSERT first, `postings.job_id` UPDATE second, one transaction: the
projection can be rebuilt from the trail, never the reverse. The UPDATE is guarded on `from_job_id`, so a
plan built against a stale read moves nothing rather than overwriting an anchor somebody else set. Loser
`jobs` rows are not deleted — `job_grouping_events.from_job_id` is a real FK to them.

**Completeness-gated for a stronger reason than the ranker's** (D-090): survivor election over a partial
corpus is backfill-order-dependent, and unlike the read path this writes that order-dependence to disk
permanently.

---

## D-105 — Identity writes move into the scan path, closing D-098 — and D-098's cost argument did not apply

**Context.** D-098: `write_identities` had exactly one caller in `src/`, the manual `identities backfill`.
Any run that discovered one new posting left it uncovered, `identities_complete()` went False, and
duplicate suppression silently switched off corpus-wide. Mit ruled the wiring was Slice 2's job.

**Choice.** Identities are computed and upserted **per posting, inside the board's existing transaction**,
in `scan/apply.py::_apply_listed`.

**D-098 priced this work at "a second corpus-wide `body_text` load beside the one `count_by_source`
already does". That price belongs to the design D-098 had in mind** — a sweep bolted onto the pipeline —
and not to this one. `_apply_listed` already holds every field `IdentityInputs` needs, so the cost is
O(postings this board listed) and no body is loaded that was not already in memory. Recording this because
D-098 has already had to correct one wrong cost figure in the same paragraph; a deferral justified by a
number deserves re-checking when the design changes.

**Not wrapped in a try/except.** A failure fails the board's transaction, so a posting and its identity
commit or vanish together — the D16 property the module is built on. A posting stored without its identity
is exactly the state that disables suppression.

**The stale-key half needs no extra work.** `_apply_listed` calls the writer on every positive
observation, which is the same trigger that refreshes title and locations, and `write_identities`' contract
is already upsert-and-delete (D-089). A retitle with an unchanged body moves the key with no revision, and
the test asserts exactly that: the stored `exact_quad` changes while `posting_versions` gains no `revised`
row.

`identities backfill` remains, for the pre-existing corpus and after an `IDENTITY_ALGORITHM_VERSION` bump.
What changed is that it is no longer the only writer.

---

## D-106 — Two consequences the build forced: what earns a permanent `skipped`, and the zero-output guard

**Only a deterministic refusal earns `skipped`.** `LeadArtifactError` — the résumé gate refusing a
shippable artifact — is deterministic: the same résumé against the same JD under the same settings refuses
identically, so re-attempting it every run costs a render and produces the same answer. The generic
`except Exception` branch in the tailor loop deliberately does **not** write a disposition: an unclassified
failure may be transient (a provider blip, an interrupted render), and a permanent disposition on a
transient fault silently deletes a real lead. This is the precision-over-recall direction the phase has
applied throughout: a leaked duplicate is counted and recoverable, a suppressed real lead is neither.

**The zero-output guard had to learn about the ledger, and this is a widening the ledger forces rather
than a weakening.** `_zero_output_guard` held that 0 leads is provably right iff
`eligible_judged_this_run == 0`. Under the ledger a run can judge genuinely new eligible postings and still
produce 0 leads because every candidate carries a live disposition — an honest empty day with a reason it
can name. Without a `hidden_handled` clause the daily driver's exit status would be **1 every day** once the
queue is caught up, which is precisely the signal destruction `PipelineSummary`'s own docstring exists to
prevent. New condition: fire iff `eligible_judged_this_run > 0 **and** hidden_handled == 0`. A run with no
handled candidates still cannot explain itself and still fires; **both directions are tested**, because
weakening a guard without a test that it still fires is how a guard becomes decoration.

**`hidden_handled` is not gated on identity completeness**, unlike `hidden_duplicate`. A stored disposition
records a decision this program already made, so it governs whether or not dedup happens to be running that
minute. Consequently `hidden_handled == 0` means zero, with none of `hidden_duplicate`'s ambiguity.

---

## D-107 — P6 Slice 2 BUILT and verified on real data; `cross_host` dereference deferred by measured absence

*2026-08-10.*

**What shipped.** `job_dispositions` + the `p6_job_dispositions` migration (now the Alembic head);
`core/ledger.py` (closed catalogs, `is_live`, `plan_upsert`); `store/ledger_queries.py` (monotonic upsert,
lazy-expiring reads, stale detection, reopen); `core/regroup.py` + `store/regroup.py` (pure planner, refusal
guard, trail-then-projection writer); identity writes in `scan/apply.py`; `seen_ttl_days`;
`pipeline/policy.py`'s `run_policy_version`; the ranker's `hidden_handled` bucket, `--include-handled` drain
and `seen` write; the pipeline's `built`/`skipped` writes and regrouping call; `boardwatch ledger
show|reopen`; `boardwatch identities regroup [--dry-run]`; and `hidden_handled` in the funnel's shortlist
stage and reconciliation identity.

**The headline claim is falsifiable and was falsified before the fix.** Measured on the live store: postings
2011, 2012, 10947, 15498 and 15499 each carry a `resume_tailored` artifact from **four separate runs**
(5, 6, 7, 9); 6 of the 18 postings ever tailored were tailored more than once, because nothing suppressed an
already-built lead. `test_a_second_run_builds_a_DISJOINT_set_of_leads` asserts the opposite end to end.
**Mutation-checked:** disabling the ranker's ledger check turns 4 of that module's 6 tests red, including
this one. Caveat kept: runs 5–7 and 9 were the Gate-P0 repeat-run evidence over one store on one day, so the
*mechanism* is measured and the daily frequency is inferred.

**Verified on an isolated COPY of the live store; the live store was never written to.**
`identities regroup` planned **186 merges across 147 groups, 0 refusals**, matching D-081/D-101's
147 groups / 186 surplus rows exactly. After applying: SQL grouping over `postings.job_id` — the
projection, whereas the planner worked from `posting_identities` + `resolve_duplicates` — reports **147 jobs
anchoring 2+ open postings, 186 surplus open postings, 186 events, 186 distinct postings moved, 0
self-merges**, and `count(distinct job_id)` fell 24,073 → 23,887, exactly 186. A second pass moved **0**
(idempotence). What that agreement does and does not show: the group *count* matching an independently
measured figure, and the exact −186 with zero self-merges, is real evidence that no merge collapsed two
groups or moved a posting twice; it is **not** evidence that the right postings were grouped, which rests on
D-101's by-eye audit.

**`cross_host` dereference is deferred by measured absence, not by judgement.** D-077 filed it under Slice
2 and D-082 left it as "the Slice 2 design question". Measured 2026-08-10 over 23,455 open postings:
**15,217 `ats`, 8,238 `unknown`, 0 `aggregator`.** There is no aggregator posting in the corpus to
dereference, so the work has no population and no test that could fail for the right reason. D-082's
re-entry path is unchanged and still correct; its trigger is an aggregator lane, which is P7, and breadth is
last.

**Gate P6 is still NOT met, and this slice was not designed to meet it.** It moves the 7-day-leakage clause
from *unmeasurable in practice* to *measurable*, because D-105 stops a single newly-discovered posting from
silently disabling suppression — without which `unique` was `None` on essentially every real run. Clauses 3
and 4 remain MET (D-100, D-101). Zero-dead-postings still needs liveness, which is Slice 3 (items 5 and 6).

**Not done, deliberately.** Slice 3's applied-state suppression and liveness. Note that item 5 has no live
population either: `applications` = 0 rows.

---

## D-108 — the decision log and the metrics log are archive-split; the reading protocol moves into the index

**2026-08-10 · a documentation-structure session, no code touched.** Mit: *"decisions.md is getting too
long I think… ingesting a long file like that every session or turn is going to fill up context and take up
more tokens than what might be needed for that task."* Measured before acting: `DECISIONS.md` 4,369 lines /
333,846 bytes (~80k tokens, 107 entries), `METRICS.md` 1,547 lines / 96,063 bytes (~24k tokens, 29 sections,
no index at all). Both grow by append and neither is ever read end to end on purpose, so the cost is paid by
every session that opens one to answer a single question. The previous session had already cut `STATE.md`
from 1,387 lines to 169 and prepended a 107-row index to `DECISIONS.md`; the index made the file navigable
but did not make it smaller.

**Choice.** Split each log into a live file and a closed archive, at the boundary where the program's
current work begins.

- `DECISIONS.md` keeps **D-077 … D-107** (P6 onward) — 1,175 lines. **D-001 … D-076** move to
  `DECISIONS-ARCHIVE.md` — 3,221 lines.
- `METRICS.md` keeps the **live** tables and the P6-era session records — 465 lines. The baseline, the
  superseded per-rule abstain table, and every session record from P0 through Gate P2 move to
  `METRICS-ARCHIVE.md` — 1,148 lines.

**`METRICS.md` is split by kind, not by position.** A positional cut at the P6 boundary would have archived
the run log and the acceptance-run table, which sit near the top of the file but are still appended to — the
acceptance run has not even started yet. Order is preserved *within* each file; only the interleaving
between them is broken, which any split does.

**The reading protocol now lives in the index, and the index spans both files** — one row per entry or
section, carrying a file column and a line number. Cross-references stay **by number** (`D-028`), never by
file, so every existing reference keeps resolving across the split without being touched.

**Both moves are byte-for-byte.** Entry and section bodies were copied, never reworded or summarised: a
summary has already discarded the details worth transferring, and `DECISIONS.md` is append-only, so an
archive-split is the only structural change permitted to it. This entry is the record that it happened.

**Proved, not asserted.** For each file, the halves were concatenated back into the original order and
diffed: `DECISIONS` 322,260 bytes, SHA-1 `472dec65…` both sides; `METRICS` 96,063 bytes, SHA-1 `adcca125…`
both sides. Entry counts reconcile — 76 + 31 = 107, and 23 + 6 = 29 sections. Every generated line number was
then read back with `sed` and checked against the heading it claimed to point at: 107/107 and 29/29 correct,
zero mismatches. The check matters because the index this replaces was itself generated once with the
positions of the pre-index file, leaving all 107 rows off by 118 — a generated number nobody checked is
exactly the kind of unchallengeable-looking figure this repo has been bitten by.

**Alternatives rejected.** *Summarise the old entries instead of moving them* — forbidden by the append-only
rule and self-defeating, since the detail is the reason the log exists. *One file per decision* — 107 files,
and a grep across them is worse than a grep within one. *Move the index into its own file* — adds a hop to
every lookup for ~2k tokens saved. *Leave `METRICS.md` alone* — same growth shape, no index, and it is where
gates are checked.

**Consequence.** A session that opens the live decision log pays ~21k tokens instead of ~80k, and the live
metrics log ~7k instead of ~24k. The archives are opened only when an old decision is actually needed. Both
archives are **closed**: new entries and new measurements go in the live files. `CLAUDE.md`'s program-document
table names all four files and points at the index, so a cold session learns the archives exist before it
learns it wanted them.

**Not done, deliberately.** `CHANGELOG.md` is 863 lines for one reason — its `[Unreleased]` section has never
been cut to a release. That is the same growth shape, but cutting a release is the owner's call, not a
documentation-hygiene decision, so it is recommended to Mit rather than taken here.
