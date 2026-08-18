# Slice P5a — controller decision log

**Date:** 2026-08-17 · **Branch:** `projection-pipeline-p5a`

The working ledger from the subagent-driven build: the preflight conflict scan, every task and fix round,
and **every ruling made on the owner's behalf while he was unavailable**, each with what it costs if wrong.

Preserved because these are decisions taken *for* Mit, not by him — D-225 records the architectural
outcome, this records the reasoning and the alternatives rejected along the way. Roughly 45 `Ruling:` lines.

---

# SDD ledger — plan: docs/superpowers/plans/2026-08-17-projection-pipeline-integration-p5a.md

Spec: `docs/superpowers/specs/2026-08-17-projection-pipeline-integration-design.md` (revision 3) — read, reachable, binding authority.
Branch: `projection-pipeline-p5a`, forked from `main` at `9b7cf3a`.
Concurrent session: `boardwatch-locking` worktree owns `profile_bundle/locking.py` + the four Windows xfail markers. It has already committed `0ab16e9` and `875ad8b` (D-224) on branch `windows-lock-portability`, unmerged.

## Preflight conflict scan

### Cross-task pairs (shared file or interface)

| Tasks | Produces → Consumes | Finding |
|---|---|---|
| 1 → 4 | `ProjectionIssue.DECLARATION_MISSING` → `ISSUE_SCOPE` row | Clean. Task 4's enum-totality test fails loudly if the row is missed. |
| 3 → 4 | `ProjectionIssue.UNKNOWN_SCORER` (new) → `ISSUE_SCOPE` row | Clean, same net. |
| 3 → 4 → 5 | all three modify `projection/run.py` | Clean if run in order; each appends distinct symbols. |
| 3 → 5 | both modify `cli/projection_cmd.py` | **CONFLICT** — Task 3 moves `load_taxonomy` above the `posting_context` call; Task 5 rewrites that whole region as a thin caller and could silently revert it. See R3. |
| 2 → 6 | `ResumeSourceLineage` → `run_tailor(source_lineage=…)` | Clean. |
| 5 → 6 | both modify `reports/tailor.py` | Clean — Task 5 adds `default_compile_runner`, Task 6 adds the parameter and `ResumeLineageMismatch`. Disjoint regions. |
| 5 → 8 | `ProjectionResult` → per-lead wiring | Clean. |
| 4 → 8 | `classify_lead_outcome` → outcome counting | Clean. |
| 6 → 8 | `ResumeLineageMismatch` → caught and counted as `LINEAGE_MISMATCH` | Clean; named explicitly in Task 8. |
| 7 → 8 | `projection_ctx` local + `summary.projection_outcomes` → tailor loop | **GAP** — Task 8's code reads `projection_ctx`, which Task 7 creates. Task 7 never says to leave it in scope. See R4. |
| 7 → 9 | `summary.projection_availability` → stage omission | Clean. |
| 8 → 9 | `summary.projection_outcomes` (Counter) → stage drops | Clean after the plan's own `dict`→`Counter` fix. |
| 7, 9, 10 | `runner.py` / `run_funnel.py` / program docs | Clean. |
| 10 ↔ concurrent session | `DECISIONS.md`, `STATE.md` | **CONFLICT** — the locking session already used **D-224**. See R5. |

### Per-task self-consistency

| Task | Own text agrees with itself? |
|---|---|
| 1 | Yes. `load_declaration` verified at `declaration.py:130`; missing-file branch is inside it at `:134`. |
| 2 | Yes. Field list matches `as_meta()`'s `dataclasses.fields` assertion. |
| 3 | **No** — the monkeypatch target cannot work as written. See R1. Also `scorer_id` has no source. See R2. |
| 4 | Yes, after the plan's self-review fixes (`TEMPLATE_INVALID` and `UNKNOWN_SCORER` were corrected before commit). |
| 5 | Yes. Hashes computed from the written buffer; temp-then-`os.replace` satisfies its own no-husk test. |
| 6 | Yes. Keyword-only default `None` keeps existing callers valid, which its fourth test asserts. |
| 7 | Yes, once R2 and R4 are applied. |
| 8 | Yes, after the plan's `compile_runner` fix. |
| 9 | Yes. `derived=False` is consistent with counting drops independently. |
| 10 | Yes. |

## Preflight rulings

Ruling: Task 3's taxonomy-load test patches `boardwatch.projection.run.load_taxonomy`, not `boardwatch.extract.taxonomy.load_taxonomy` — because `run.py` will use a by-name import exactly as its sibling `posting.py:31` does, so patching the source module leaves the already-bound name untouched and the test would pass while proving nothing. — Cost if wrong: the test is vacuous and a per-posting reload ships undetected.

Ruling: Task 3 also adds `DEFAULT_SCORER_ID = "mean_per_bullet"` to `projection/scoring.py`, and both `cli/projection_cmd.py:352` and the Task 7 pipeline preflight reference it instead of repeating the literal. The default is D-198's measured choice and currently exists only as a bare string in a Typer option, so the pipeline would otherwise become a second source of truth. — Cost if wrong: one extra exported constant.

Ruling: Task 5 must preserve Task 3's taxonomy injection in `cli/projection_cmd.py`. Its dispatch will carry this explicitly, and its acceptance includes `tests/projection/test_projection_run_context.py` still passing. — Cost if wrong: the CLI silently reverts to a per-posting taxonomy load while the pipeline stays correct, and only the run-context test would catch it.

Ruling: Task 7 must leave `projection_ctx` in scope for the tailor loop (assign it before the ranker call, default `None` when `--project` is absent), since Task 8's wiring reads it. — Cost if wrong: Task 8 fails immediately with a `NameError`; cheap to detect.

Ruling: this plan's `DECISIONS.md` entry is **D-225 or later, never D-224** — the concurrent locking session already committed D-224 on its own branch. Task 10 must re-read the index and take the next free number rather than trusting any number written here. I will not merge the locking branch myself: merging a shared branch is a side effect that belongs to Mit. — Cost if wrong: two entries collide on one number and `make reindex` or the index gate catches it.

Ruling: the plan's test paths `tests/core/` (Task 2) and `tests/reports/` (Tasks 6, 9) do not exist — verified with `ls`. The repo keeps unit tests for `core/` and `reports/` under `tests/unit/`, prefixed by module area (`test_reports_tailor_jd_skills.py`, `test_run_funnel.py`). Corrected paths: Task 2 → `tests/unit/test_core_lineage.py`; Task 6 → `tests/unit/test_reports_tailor_lineage.py`; Task 9 → `tests/unit/test_run_funnel_projection.py`, and its Step 4 suite run becomes `tests/unit/`. Following the existing convention beats inventing two directories. — Cost if wrong: tests sit in a slightly unidiomatic file name; no behavioural risk.

## Execution

Task 1: implemented (commit 2e7215a). Implementer flagged that `ProjectionError` exposes `.violation.issue`, not `.issue`; it used the repo's existing accessor. Plan corrected in 01357f0 (accessor + the three test paths from the preflight ruling).
Task 1: task review dispatched over 9b7cf3a..2e7215a.
Task 1: complete (commits 9b7cf3a..2e7215a, review clean — spec ✅, quality approved, zero findings; reviewer independently confirmed 33 enum members, one raise site changed, and that both new tests fail on revert)
Task 2: implementer dispatched from base 01357f0.

Ruling: Task 2's brief was self-contradictory and my preflight scan wrongly marked it self-consistent — the docstring I specified contains the literal `profile_bundle`, while the test I specified asserts that substring is absent from the module source. The implementer resolved it by rewording the docstring, which passes but leaves a brittle test: it forbids ever naming the constraint in the one file that exists because of it, so the next person to write an explanatory comment breaks the build. Correct shape is an AST-based check that no `import`/`from` statement in the module names `profile_bundle` or `boardwatch.projection` — that tests the actual guarantee (no import edge) instead of a proxy, and permits prose. Sent to the Task 2 implementer as a fix before review. — Cost if wrong: a slightly longer test; the guarantee is also covered transitively by test_profile_bundle_tailor_isolation.py once Task 6 makes reports.tailor import this module.
Task 2: fix round 1/5 (1 addressed, 0 open — substring test replaced with an AST import check; implementer verified it fails when a forbidden import is added; commits 87d690b..65e5b8d)
Task 2: task review dispatched over 01357f0..65e5b8d. Task 3 implementer dispatched from base 65e5b8d.
Task 2: complete (commits 01357f0..65e5b8d, review clean — spec ✅, quality approved; reviewer independently re-ran the mutation and confirmed the AST test fails on a real forbidden import, and endorsed the ruling)
Task 2: minor (deferred): src/boardwatch/core/lineage.py:1 — docstring double negative "neither the tailor nor the bundle may not import" (my plan text, copied verbatim). One-word fix, cosmetic.
Task 2: minor (deferred): tests/unit/test_core_lineage.py:87 — local `lineage` shadows the module-level `lineage` import inside one test; not a bug, but reads like one.
Task 3: implemented (commit 293b143), DONE_WITH_CONCERNS — three concerns, all ruled below.

Ruling: my preflight Ruling 2 was not implementable as written, and the implementer measured why rather than assuming — `projection.scoring` reaches `boardwatch.store.tables` via `extract.taxonomy`, and `cli/projection_cmd.py` is bound by `test_the_command_module_imports_no_store_module`, so importing `DEFAULT_SCORER_ID` there breaks a real architectural boundary. ACCEPT its workaround: the constant lives in `scoring.py` as ruled, and the CLI's literal is locked to it by an assertion so divergence fails a test. I decline the offered five-line leaf-module follow-up: the goal was one source of truth, an assertion achieves that, and Task 7's consumer is the store-coupled pipeline which can import `scoring.DEFAULT_SCORER_ID` directly. — Cost if wrong: one duplicated literal, guarded by a test that fails if they diverge.

Ruling: the brief's `test_posting_context_uses_the_injected_taxonomy` was undeliverable as drafted — `jd_skills_for` keys its extraction row on `taxonomy.version`, so an empty-pattern taxonomy raises `NO_JD_EXTRACTION` instead of returning an empty set. ACCEPT the implementer's substitute (seed a row under a distinctive version and assert that skill surfaces), which is strictly stronger because it proves the injected object was used rather than merely that nothing came back. My test design was wrong. — Cost if wrong: none identified.

Ruling: `run_preflight` continues to load its own taxonomy per `posting_context` call, leaving a residual gap in the §4.1 freeze. ACCEPT and document rather than fix. The consequence is fail-safe in the direction the design wants: a mid-run `taxonomy.yaml` edit makes lead 2 raise `NO_JD_EXTRACTION`, which Task 4's catalog routes to the per-lead `extraction_unavailable` outcome — the lead is skipped and counted, never rendered under mixed rules. Silently rendering under a second taxonomy is the outcome round 2 flagged as blocking; refusing the lead is not. Task 4 must carry this explicitly so the mapping is deliberate. — Cost if wrong: a mid-run taxonomy edit costs that run's remaining leads instead of being surfaced as a configuration change; no wrong résumé is produced either way.

Task 3: task review dispatched over 65e5b8d..293b143.
Task 3: complete (commits 65e5b8d..293b143, review clean — spec ✅, quality approved, 4 minors). Reviewer independently confirmed all three of my rulings, and verified ruling 3 more strongly than either I or the implementer had: `extract/preflight.py:37` backfills at the NEW taxonomy version and `select` loads no taxonomy of its own, so the only two reachable outcomes are a consistent render or a skipped lead — no path renders under two taxonomies.
Task 3: minor (folded into Task 4, not deferred): tests/projection/test_projection_run_context.py:87 — the counting test patches only the two bound names, so a function-local or attribute-style reload is invisible to it. The reviewer DEMONSTRATED this with a second mutation arm (function-local import → 1 failed, 7 passed; the counting test passed while a per-posting reload was live). One extra monkeypatch closes it.
Task 3: minor (folded into Task 4): same file line 79 — docstring claims "one taxonomy load" for the run; `run_preflight` loads more that the test does not count.
Task 3: minor (deferred): report justified a test helper by a line-length limit that `pyproject.toml:82` disables for `tests/**`. Helper is harmless; the stated reason is false.
Task 3: minor (deferred): cli/projection_cmd.py:445 — moving the taxonomy load above the `try` changed error precedence (a broken taxonomy.yaml now beats a bundle/stamp refusal); no test pins the new ordering.

Ruling: the first two minors are folded into Task 4's dispatch rather than deferred to final review, because the blind spot they close guards the single property external review round 2 rated blocking (no mixed-configuration render). Task 4 already touches this area, so it costs no extra dispatch. The other two are genuine deferrals. — Cost if wrong: a one-line test hardening lands one task later than it could have.
Task 4: implemented (commit e881030) — 34/34 issues mapped in one written-out table, 5 foreign exception families in a second, totality proven three ways on src copies including "adding a new enum member fails the test", and the folded run-context third-patch fix verified to fail on an injected function-local reload while the pre-fix version passed silently.

Ruling: concern 1 is a real defect, not a judgement call to accept. `SHELL_SOURCE_UNREADABLE` describes a broken **`resume.yaml`** (the `shell_source`), while `DECLARATION_UNREADABLE` describes a broken **`projection.yaml`**. Those are different files with different remedies, and the entire purpose of the availability catalog is that each member names an operator problem the operator can act on — so conflating them sends someone to edit the wrong file. Sent back to add a distinct `SHELL_SOURCE_INVALID` availability member, with a test pinning it (the implementer noted no test pinned the old mapping). — Cost if wrong: one extra catalog member.

Ruling: concern 2 (no `is_run_scoped` predicate) is correct as YAGNI, but it exposes a real hazard for Task 8 that must not be rediscovered there. `PINNED_SET_EXCEEDS_BUDGET` and `COMPILE_INFRASTRUCTURE_FAILURE` are run-scoped yet physically surface inside the per-lead loop, and both classifiers assert on the other's scope — so a Task 8 that blindly calls `classify_lead_outcome` would crash the run with an `AssertionError` instead of setting a clean typed fatal. Task 8's dispatch will carry the requirement: route by scope FIRST, and promote a run-scoped cause to `summary.fatal` rather than counting it as a lead outcome. The loud assert is the right design; the routing is the caller's job. — Cost if wrong: a pinned-budget overflow aborts with an assertion traceback rather than a clean fatal; loud either way, so cheap to detect.

Ruling: concern 3 — `LINEAGE_MISMATCH` and `OUTPUT_IO_FAILURE` currently have no producer. Keep them for now; Task 6 wires the first (`ResumeLineageMismatch`) and Task 5/8 the second. But this is conditional: if either still has no producer after Task 8, DELETE it — a catalog member that cannot fire is a member to remove, not to keep for symmetry. Recorded here so the final review can check it. — Cost if wrong: two dead enum members ship; caught by the final review.
Cross-lane note: the `bulletless` lane has uncommitted edits to `projection/declaration.py` and `projection/serialize.py`, beyond the `pool.py`/`resume_gate.py` set I predicted for it. Legitimate — making a bullet-less entry *declarable* needs the schema — but `declaration.py` is also touched by this lane's Task 1 (the DECLARATION_MISSING raise site). Different regions of the file, so a textual merge should succeed; flagged to that lane so the overlap is not a surprise at merge time. No action needed here.
Cross-lane note: the `locking` lane now has Windows evidence that distinguishes repair from suppression — commit 1fbd967, "the race fired pre-fix on 3.13 and does not after". That is stronger than the green-with-markers run this session saw earlier, which only ever proved suppression.
Task 4: fix round 1/5 (1 addressed, 0 open — SHELL_SOURCE_INVALID added as a distinct availability member with the missing test; can-it-fail verified by re-pointing the row on a src copy, failing exactly that one test; commits e881030..5d9dde9). Implementer conceded the point: it had collapsed two separately authored files into one remedy.
Task 4: task review dispatched over 293b143..5d9dde9. Task 5 implementer dispatched from base 5d9dde9.
Cross-lane resolution: the bulletless lane reported that its new `Entry.bulletless` field changes `master_content_hash`. Verified in this lane's own files (`reports/tailor.py` is mine): `master_hash` at :485 is the dedupe key for `get_or_create_master_artifact` at :739, so the effect is up to 6 extra `resume_master` rows once (6 exist today) — and it is content-addressing working correctly, since the model genuinely changed. Also verified: `exclude_none=True` would NOT be a neutral fix (Entry already has six None-defaulted fields); no test pins the hash's absolute value; and NO reconciliation invariant counts `resume_master` (zero hits across run_funnel.py, pipeline/, store/queries.py), which was the only path that could have made this gate-breaking. Its disposition accepted, mechanism relayed. That lane adds no ProjectionIssue member, so this lane's totality test is unaffected, and it took D-226 leaving D-225 for Task 10.
Task 4: complete (commits 293b143..5d9dde9, review clean — spec ✅, quality approved). Reviewer ran SIX independent mutations on src copies (verifying the mutated module was the one imported) and proved both classifiers' closure rather than accepting the report: dropped cross-scope assert, foreign-exception default return, cross-catalog collision, an added lead-outcome member, `type(exc) is` instead of `isinstance`, and a hardcoded early return — six distinct failures. Also endorsed both of my rulings and the SHELL_SOURCE_INVALID call.

## Plan amendment: new Task 5b — make the catalog's guarantees real

Ruling: insert a new task between 5 and 6. The review surfaced one Important inherited defect and three minors that all share one theme — the closed catalog's guarantees are currently narrower than they claim. I verified the Important one myself at `projection/select.py:82-91` and `:164`.

The defect: `_fatal_if_infrastructure` raises `COMPILE_INFRASTRUCTURE_FAILURE` for BOTH `GateReason.BINARY_MISSING` (environment) and `GateReason.COMPILE_FAILED` (tectonic exited non-zero = owner content, e.g. an unescaped `%` in a bullet), and it is called inside the JD-dependent candidate loop. So one bad character in candidate entry X aborts the whole projected run as "toolchain unavailable" for exactly the postings where X is admitted, and sends the operator to reinstall tectonic. Its docstring conflates "never budget overflow" with "infrastructure fault" — those are not the same claim. This is a live risk, not theoretical: Mit's 23 bullets were rewritten across eleven entities this week and LaTeX specials are exactly what that churn introduces. My design's §4.4 listed `compile_infrastructure_failure` as run-scoped without anticipating that a content failure flows through the same arm. The catalog cannot fix this — telling the two apart by re-reading a message is forbidden — so the split belongs at the raise site as a new `ProjectionIssue`, mapped per-lead. — Cost if wrong: one extra issue member and a per-lead outcome; the alternative is a misdiagnosed abort on the most likely real failure.

Task 5b also folds in the three minors, same theme:
- Both classifiers' terminal path is a bare `assert`, so under `python -O` they vanish and `classify_availability` can return a `ProjectionLeadOutcome` typed as `ProjectionAvailability` — the exact silent-wrong-bucket its own docstring forbids. Convert to an explicit `raise` of a typed error. In-house style uses asserts elsewhere, but a closed-catalog guarantee that evaporates under a flag is a check that cannot fire.
- `ISSUE_SCOPE` is a plain dict typed `Mapping`; `MappingProxyType` makes the closed catalog actually closed.
- `tests/projection/test_projection_outcome_catalog.py:145-149` — a `.value !=` assertion that cannot fail independently (equal values alias to one StrEnum member, which the preceding `is not` already catches) and which `mypy --strict` would flag as comparison-overlap if tests were type-checked. Remove or make it meaningful.
Task 5: implemented (commit 02c45d7) — CLI suite `test_projection_cli_resume_project.py` confirmed UNEDITED (empty git diff --stat), mypy --strict clean over 275 files, 4 mutations each killing the intended test.

Ruling: concern 1 accepted — my husk test could not fail. A closed posting refuses inside `posting_context`, BEFORE any file is written, so the test I specified would have passed against a direct-write implementation. The implementer's substitute (make `manifest_bytes` return a `str` so the SECOND staged write raises with the résumé already on disk) is the only shape that kills a direct-write `_publish`. **This is the third time an implementer has caught a test I specified being unable to fail** (Task 2's substring test, Task 3's empty-taxonomy test, now this) — the pattern is that I write tests from the claim I want to make rather than from the mechanism that would violate it. Recorded as a lesson, not just a fix. — Cost if wrong: none; the substitute is strictly stronger.

Ruling: concern 2 accepted — routing `resume project` through `_boundary_outcome` was wrong in my brief; it emits a `profile-bundle project:` envelope and would break four assertions in the suite I declared protected. The protected suite was the binding constraint, so preserving the echo/exit shape is correct. — Cost if wrong: two commands keep slightly different error envelopes.

Ruling: concern 3 accepted — `--scorer` validation stays in the CLI because `run.py` binds `SCORERS` at import and delegating would fail the runtime-derivation test. Same shape as the earlier DEFAULT_SCORER_ID finding. — Cost if wrong: validation lives one layer out from where the brief imagined.

Ruling: concern 4 is a REGRESSION this task introduced and gets fixed here, not deferred. `resolve_projection_run` now loads the persona registry, so a malformed `personas.yaml` makes `resume project` raise an uncaught `PersonaError` — a traceback where this repo's whole convention is a typed refusal. `TaxonomyError`/`EquivalenceError` were already uncaught on that path, so the one-liner closes three arms at once. Fixing it where it was introduced also means the Task 5 review reviews correct code. — Cost if wrong: three exception types get a clean message instead of a traceback.

Ruling: concern 5 carried to Task 8 — `ProjectionResult`'s `| None` fields are unreachable today because every refusal raises. If Task 8 does not fill them, they get tightened to non-optional. A field that cannot be None in practice but is typed optional makes every caller write a dead check. — Cost if wrong: one type tightening lands a task later.

Ruling: concern 6 accepted as an improvement — `_publish` yields mode 0700 on a fresh lead directory where the old path was umask-derived 0755. These directories hold résumé PDFs and personal data; more restrictive is the right direction and needs no action.
Task 5: fix round 1/5 (1 addressed, 0 open — three exception arms given typed refusals; commits 02c45d7..bab2dd3). Two things made my one-liner insufficient, both found by the implementer: the persona arm actually fires at the PRE-DATABASE `reject_entry_declaring_personas` preflight (which calls `load_personas` itself), so widening only the resolve site would have left the traceback in place — it widened both; and `load_equivalences()` reads the PACKAGED table with no config override, so the test redirects `equivalences.files` to make the exception come from the production parser rather than patching the loader, which would have made the "names the file" assertion self-fulfilling. All three can-it-fail checks confirmed on a src copy.
Task 5: minor (deferred): the second `PersonaError` except arm is near-dead (only a between-reads change reaches it) and untested there. Defensible as a narrow race guard; final review to triage against "a check that cannot fire is deleted".
Task 5: task review dispatched over 5d9dde9..bab2dd3. Task 5b implementer dispatched from base bab2dd3.
Task 5: complete (commits 5d9dde9..bab2dd3, review clean — spec ✅, quality approved, 3 minors + 1 informational). Reviewer verified all three hard constraints by independent mutation, and confirmed by BLOB SHA (not just an empty --stat) that the protected CLI suite is byte-identical at both commits and in the worktree. It also confirmed the brief's original husk test was a genuine no-op: against a mutant direct-write `_publish`, the replacement test failed and my original one passed.

Ruling: three of Task 5's minors go into a PENDING FIX BATCH rather than to the final review, because one is load-bearing for Task 8. They cannot be dispatched yet — Task 5b's implementer is editing `projection/run.py` right now and a concurrent edit to the same file risks a conflict, so this batch is dispatched once 5b lands. — Cost if wrong: the batch lands one task later than ideal.

Pending fix batch (dispatch after Task 5b):
  (a) `projection/run.py:358-364` — the existing-out_dir branch's inline justification is FALSE: it claims "there is no husk to create here anyway, because the directory the cleanup would have removed already exists", but `_remove_if_empty` (`pipeline/runner.py:873-876`) swallows `OSError`, so a pre-existing non-empty lead directory survives regardless of who created it. **Task 8 takes exactly this branch**, so a later task would build on a false premise. Fix the comment; the practical risk is ~nil since both payloads are staged first.
  (b) `tests/projection/test_projection_for_posting.py:100` asserts `manifest["manifest_schema"] == run_mod.MANIFEST_SCHEMA_VERSION` — derived from the constant under test, so reverting `manifest.py:26` to 1 leaves every suite green. This is the [[a-test-derived-from-a-constant-agrees-with-itself]] pattern exactly. Pin the literal 2 once, outside.
  (c) `projection/manifest.py:43` still types `posting_id: int | None` and documents "None for a JD-blind Stage 1 manifest", while `:59` adds a REQUIRED `posting_version_id: int` — so a Stage 1 manifest is now unrepresentable. Either restore representability or drop the claim; documenting a state the type forbids is worse than not supporting it.

Ruling: the reviewer's informational point is accepted and worth carrying — `test_the_resume_hash_is_over_the_bytes_that_were_written` would pass equally against a hash-by-re-read implementation, because single-threaded the file holds those same bytes. The read/swap/read window is structurally unobservable from a test. So the property is CODE-VERIFIED ONLY, and that test must not be cited as evidence for it. No test is owed; the honesty is the deliverable. — Cost if wrong: none, provided nobody later reads that test as proof.
Task 5b: implemented (commit 4d38815) — all four parts, 7 new tests each mutation-proved red without its fix.

Ruling: the implementer's `GateReason` judgement is ACCEPTED and is better reasoning than I gave it. It kept the six `validate_layout`-only reasons run-scoped on a REACHABILITY argument: production `compile_prefix` can only return `evaluate_compile`'s four, so a fifth means a compiler was miswired — run-invariant by construction — and classifying it per-lead would bill N leads to the owner's content for one wiring bug. That is the correct shape of argument for a scope decision, and it is now in the docstring rather than in a ledger only I read. — Cost if wrong: a genuinely per-posting layout reason would abort a run; but no production path can produce one.

Ruling: my Step 5 test could not fail — the FOURTH such instance in this plan. `classify_availability` already terminated in a real `raise`, so the `RuntimeError` case refused before any fix. The brief's PROSE named the real hole (the scope-crossing assert) while its CODE tested something already true; the implementer tested the prose and kept my case as one of four. Note the asymmetry: my reasoning has been right each time and my test snippets wrong — the defect is in translating a claim into an executable check, not in the analysis. — Cost if wrong: none; coverage is strictly greater than specified.

Ruling: Part 2 was an UNDERCOUNT in the brief, not just in the implementation. `classify_lead_outcome` carried the mirror defect AND an `AttributeError` leak, so three defects sat behind what I described as one. Accepted as fixed; recorded because it means the Task 4 review's "Minor" severity on the `-O` issue was itself too low — a stripped assert was leaking a wrong-typed enum member in BOTH directions plus raising the wrong exception type in a third case. — Cost if wrong: none; all four cases now refuse under `-O`, verified in a child interpreter.

Task 5b: owed a `DECISIONS.md` entry (the split + the GateReason ruling). The implementer deliberately did NOT append it, because three sessions share this repo and the reindex gate is mine to run — correct call. Rolled into Task 10.
Task 5b: carried to Task 8 — the implementer notes nothing yet ACTS on the new per-lead row, so the misdiagnosis is fixed but run survival is not. Task 8 owns routing by scope and skipping the lead.
Task 5b: task review dispatched over bab2dd3..4d38815. Held fix batch (Task 5's three minors) dispatched now that run.py is free.
Fix batch: complete (commit 9cc33ac) — all three of Task 5's minors. Fix 3 investigated to Case 1 (no Stage 1 manifest writer exists), so `posting_id` became required and the false docstring claim was removed. Fix 2's literal pin verified to fail when the constant is reverted.

Task 5b: review returned spec ✅ / quality NEEDS WORK — two Important findings, both correct, both entering fix round 1.

Ruling: my Task 5b Part 1 premise was WRONG and the reviewer caught it by citing a sibling catalog I never consulted. I asserted `COMPILE_FAILED` means owner content. `reports/resume_gate.py:87-90` reasons the opposite in an existing closed catalog — "a non-zero `tectonic` exit is environmental (cold support-file cache with no network, disk full, OOM, killed subprocess), so burying the lead permanently would delete a real opportunity on the strength of a bad afternoon" — and `_default_runner` folds three distinct causes into one `CompileReason`, so NOTHING typed anywhere distinguishes content from environment. Verified at the source myself. Consequence of my version: a disk-full run bills every lead to the owner's content and yields a silent empty day, which CLAUDE.md's fail-safe table forbids (systemic outage ⇒ fatal).

The resolution I am ruling, which closes BOTH Important findings with one change: discriminate by **differential observation**, not by type.
  - The **pinned-base** compile (`select.py:231`, before any candidate exists) is unattributable — it could be the environment or the pinned content, and the pinned set is fixed by the frozen declaration. So it stays **run-scoped and fatal**, by exactly the argument `PINNED_SET_EXCEEDS_BUDGET` already uses. This also fixes finding 1, where the pinned arm was raising a *candidate* issue with a message naming a candidate that does not exist.
  - A **candidate-loop** failure where the pinned base just compiled OK **is** attributable: the same document minus X compiled seconds earlier, so X is implicated. That stays **per-lead**, which preserves the original fix — one bad `%` in a candidate bullet skips only the leads admitting it.
  - The degradation is safe if the environment truly died mid-run: later candidates also fail, all get skipped, and the lead still receives a pinned-only résumé; if the pinned compile itself fails, the run goes fatal. No silent empty day in either direction.
  This is consistent with `resume_gate.py` rather than contradicting it: it never claims `COMPILE_FAILED` is content, only that a *candidate-attributable* failure is attributable enough to skip that candidate.
— Cost if wrong: an environmental blip that strikes exactly between the pinned compile and one candidate compile skips one candidate for one lead. Bounded, and the lead still ships.

Task 5b: the `DECISIONS.md` entry (Task 10) MUST cite `resume_gate.py`'s environmental reasoning and explain why differential attribution does not contradict it. An entry that ignores the sibling catalog would re-litigate this in three months.
Task 5b: fix round 1/5 (3 addressed — 2 Important + 1 Minor; 0 open; commits 4d38815..8587f86). Pinned-base arm proved twice; mutation M4 (restoring the reviewed behaviour) reproduced Finding 1 verbatim, emitting "adding candidate entry `None` made the compile fail".

Ruling: the implementer took the "clearer run-scoped member" option and its reasoning is right, so ACCEPT the new `PINNED_SET_COMPILE_FAILED` → `PINNED_SET_UNRENDERABLE`. Reusing `COMPILE_INFRASTRUCTURE_FAILURE` would resolve to `TOOLCHAIN_UNAVAILABLE`, whose remedy is "install something" — so an unescaped `%` in a PINNED bullet would still have sent the operator to reinstall a working tectonic, which is the same misdiagnosis this task exists to kill, merely relocated. The new member points at the compile log instead. `BINARY_MISSING` keeps the old member at both call sites, correctly, since it is the one arm typed at its source. — Cost if wrong: one more catalog member in a catalog that now has a totality test.

Ruling: my point 4 was factually wrong about the code and the implementer's correction is better. I claimed a dead environment would still "ship a pinned-only résumé". It would not: a per-lead outcome skips the WHOLE lead — `_grow` raises and no résumé is written. What actually happens is stronger for the safety argument: every lead begins with its own pinned compile, so a persisting outage is caught at the NEXT lead's pinned base, unattributably, and goes fatal. **A real outage therefore costs at most ONE misattributed lead before the run stops.** That is a tighter bound than the one I asserted, and it is what got documented. — Cost if wrong: none; the bound is better than the one I claimed.

Ruling: accept the rename `CANDIDATE_CONTENT_UNRENDERABLE` → `CANDIDATE_UNRENDERABLE`. The old name embedded the very cause claim I had just retracted, and nothing consumes it yet.
Task 5b: minor (deferred): `_fatal_if_infrastructure`'s NAME now overstates two of its three arms — `_fatal_unless_overflow` would be truthful (2 call sites + 1 test import). Deferring to the final review to stay consistent with how every other minor in this plan was handled; minors do not enter the fix loop. Noted that it is the same class of defect as the docstring that caused Finding 2, so the final review should weigh it on those grounds rather than as cosmetics.
Task 5b: scoped re-review dispatched over 4d38815..8587f86.
Task 5b: complete (commits bab2dd3..8587f86, all findings addressed at the cap of round 1). Scoped re-review verified all three ADDRESSED and independently confirmed BOTH of the implementer's corrections to me: that `project_for_posting` catches nothing so a `_grow` raise writes no résumé (killing my "ships a pinned-only résumé" claim), and that `select()` runs a fresh pinned compile first thing on every call, so a persisting outage surfaces at the next lead's pinned base — bounding misattribution to one lead. It also confirmed the totality test passes because a row was added, not because it was relaxed, and that both new docstrings cite `resume_gate.py:87-90` verbatim and accurately.
Task 6: implementer dispatched from base 8587f86. Line numbers in the Task 6 brief have DRIFTED (Task 5 edited reports/tailor.py): run_tailor 452→463, master_hash 482→496, the artifact insert 746→759. Dispatch cites symbols instead and tells the implementer to derive lines.
Task 6: complete (commits 8587f86..5a1c3f9, review clean — spec ✅, quality approved, 3 minors). The reviewer did NOT take the implementer's message-diff probe on faith: it ran two cases the probe missed (a CRLF résumé, exercising `read_text`'s universal-newline translation vs `read_bytes().decode()`, and an invalid byte at offset 20003, exercising chunked vs whole-buffer decode), printing `IMPL:` to prove the two runs loaded different files. Both identical old vs new — so the claim now rests on stronger evidence than the report gave. It also confirmed the `_plan_tier_a` placement deviation is correct AND better: `cv` is resolved there and `run_tailor` only sees it afterwards via `r.cv`, so checking in `run_tailor` would have required a second version query plus a second file read — precisely the read/swap/read window.

Ruling: Task 6's minor 2 is NOT a deferral — it is a forward hazard that would silently defeat the whole catalog, so it becomes a Task 8 obligation. `pipeline/runner.py:579` catches `except Exception` for per-lead failures; once the pipeline passes `source_lineage`, a `ResumeLineageMismatch` with no explicit arm lands in the generic `tailor_failed` bucket and never reaches `ProjectionLeadOutcome.LINEAGE_MISMATCH`. A typed raise silently degraded by a broad catch is exactly the failure mode the closed catalog exists to prevent, and it would have shipped looking green. Task 8 must add the explicit arm BEFORE the catch-all, and must not rely on the catch-all. — Cost if wrong: the lineage-mismatch outcome can never be observed, and the funnel would misattribute it to tailoring.

Fix batch 2 (queued, dispatch after Task 8 — both touch reports/tailor.py tests, and Tasks 7/8 are live in runner.py):
  (a) Task 6 minor 1 — the read-once contract has NO regression test. A future edit to `resume_sha256 = hashlib.sha256(path.read_bytes())` followed by `load_resume(path)` reintroduces the swap window and all 7 tests still pass. A call-counting wrapper over `read_resume_bytes` pins it. Note this is the same property an earlier reviewer called structurally unobservable from behaviour — but a CALL COUNT is observable, which is the insight worth keeping.
  (b) Task 6 minor 3 — no test covers `dry_run=True` with lineage. Validation does fire (it lives in `_plan_tier_a`), but the "no artifact ⇒ no lineage" behaviour is unasserted.
Task 7: implemented (commits 43fc491, 6279bfb). Whole suite 6497 passed, exit 0. All five headline assertions proven to fail independently, including a mutation showing assertion 4 is not subsumed by assertion 5.

Ruling: my assertion 3 was VACUOUS and the implementer's mutation C caught it — the sixth wrong test snippet I have written in this plan, and the most instructive. I specified `"FATAL" in funnel_markdown`. A refused run has `shortlist is None`, so the shortlist stage renders its NOT-INSTRUMENTED prose, and that prose contains the word "FATAL" (`reports/run_funnel.py:629` — I verified it at the source). So the assertion passed with `fatal=None`. The irony is the lesson: I built a five-assertion test SPECIFICALLY because a reviewer had shown four can pass while the fifth is broken, and one of my own five was itself unfalsifiable. Substring assertions against generated prose are the recurring shape of this mistake. Now asserts exactly one `- **FATAL:**` line naming the availability member's `.value`. — Cost if wrong: none; the replacement is strictly stronger.

Ruling: the `as_of` divergence the implementer raised is real and gets fixed, in batch 2. `cli/projection_cmd.py` uses `date.today()` while the pipeline now uses `utcnow().date()`. For an owner at UTC-4/5 these differ for several hours each evening, so `resume project` could preview a résumé built from different effective facts than `run --project` produces — a preview that does not match the run is worse than either convention alone. Unify on `utcnow().date()`, since `as_of` is recorded in lineage beside a `runs` row that is already UTC. — Cost if wrong: a human previewing near midnight sees the UTC date rather than their local one, which is the lesser surprise.

Fix batch 2, updated (dispatch after Task 8):
  (c) unify `as_of` on `utcnow().date()` across `cli/projection_cmd.py` and the pipeline; expect test updates in the projection CLI suite.
  (d) optional, low value: `RUN_CONTRACT.md` rows 1-4 cite stale line numbers (Task 7's new row 5 is accurate). The repo's own convention is to omit line numbers from prose; consider dropping rather than refreshing them.

Task 7: task review dispatched over 5a1c3f9..6279bfb. Task 8 implementer dispatched from base 6279bfb, carrying five obligations accumulated from earlier reviews.
Task 7: complete (commits 5a1c3f9..6279bfb, review clean — spec ✅, quality approved, 4 minors + 1 note). Reviewer proved the refusal path writes no disposition STRUCTURALLY rather than by test: the only writer of `job_dispositions` is `record_disposition` (`store/ledger_queries.py:107,115`), reachable solely from `_record_shortlist_dispositions` at `runner.py:706`, and `resolve_projection_run` is read-only. It also confirmed the replacement assertion 3 is genuinely falsifiable — the sole emitter of `- **FATAL:**` is guarded by `if funnel.fatal:` — and that `stale_approval` appears in neither the raise prose nor the issue name, so the assertion tests the interpolation rather than agreeing with the message.

Ruling: Task 7 minor 3 becomes a Task 8 REVIEW obligation, not a fix. The reviewer noted assertion 5 (retry visibility) passes today only because `--project` on the AVAILABLE path still renders the AUTHORED résumé — per-lead wiring is Task 8 — so it cannot yet distinguish "the drain works" from "projection is a no-op", and Task 8's non-fatal per-lead `continue` will make full-set equality STRICTER than the code guarantees. Task 8's review must re-check that assertion against the new behaviour, and a legitimate relaxation there is not a regression. — Cost if wrong: a test that either over-constrains Task 8 or under-proves the drain; caught either way by naming it now.

Ruling: Task 7 minor 4 is an INTEGRATION GATE, recorded so it cannot be lost. `cli/run_cmd.py:61-66`'s help text promises "Render each lead from the … projection", which is FALSE at this commit on the AVAILABLE path. Task 8 closes it. **This branch must not merge without Task 8** — a flag whose help text describes behaviour it does not have is worse than an absent flag. — Cost if wrong: a user passes `--project`, sees success, and gets the authored résumé.

Ruling: the reviewer's closing NOTE is carried to Task 9 as a hard obligation. `Counter.__missing__` returns 0, so "absent, not zero" holds ONLY for readers using `in` / `.items()`. If Task 9 indexes `projection_outcomes[X]` it silently reads 0 and the absent-vs-zero distinction — the whole basis for omitting the funnel stage rather than emitting zeros — evaporates with no test failing. **Task 9 must ITERATE, never index.** — Cost if wrong: the funnel claims projection ran and dropped nothing on runs where it never ran at all, which is precisely the D-023 "not instrumented vs 0" distinction this program already settled once.

Fix batch 2, updated:
  (e) `RUN_CONTRACT.md:39` cites the ranker call at `:527`; it is at `:520` (`:527` is a comment inside the argument list). Six of seven citations in that row check out; this one does not. Consider dropping line numbers entirely, per the repo's own convention.
  (f) `tests/pipeline/test_pipeline_projection_preflight.py:588` — assertion 4's non-vacuity exists only in the report's mutation log. Add `assert _disposition_count(engine) > 0` after the successful run so `== 0` cannot go vacuous if the ledger ever moves tables.
Task 8: complete (commits 6279bfb..aba48c9, review clean — spec ✅, quality approved, 1 Important deferred to Task 9 + 5 minors). The reviewer INDEPENDENTLY REPRODUCED the cohort-guard finding on a src copy with a live canary: deleting `- frozenset(summary.projection_failed_ids)` fails all three per-lead tests with "cohort incomplete: 1 shortlisted candidates unaccounted", so the fourth terminal state is required rather than decorative. It then enumerated ALL SEVEN loop exits and verified each iteration takes exactly one, that `dead_lead_ids` cannot overlap (dead leads are filtered out of `leads` before the loop), and that the `PROJECTED` retraction cannot double-count because increment and retraction happen inside one iteration.

Also: Task 7's assertion 5 was STRENGTHENED, not relaxed — the file is unedited, and that run now projects both leads through real `select` compiles, so it proves both the drain and that projection is not a no-op. It buys a new dependency on `tectonic` being present, which the suite already has.

Ruling: the Important finding goes to Task 9 IN FLIGHT rather than into a queue, because Task 9 is building exactly that code right now and the reviewer specifically warned it "could close it without proving it". As of Task 8, `reports/run_funnel.py:788-805`'s tailor stage drops are `tailor_failed + withheld_not_live`, so a projection-dropped lead is in NO bucket and any `--project` run with a per-lead drop reports **`reconciles: no`** — Gate P0's headline claim. Task 9 must both fix the balance AND pin it with an assertion on that exact path, proved to fail beforehand. Sent. — Cost if wrong: the branch would ship a funnel that fails the P0 reconciliation clause on the feature's own primary path.

Ruling: the `_retract_projected` hazard (`runner.py:808`) also went to Task 9 in flight, since it targets Task 9's absent-vs-zero rule. A retraction with no `PROJECTED` key would leave `PROJECTED: -1` — a non-empty counter on a non-projected run — and it is unreachable today only by a behavioural accident (one raise site gated on `source_lineage is not None`), not by structure. I gave Task 9 two acceptable resolutions and let it choose, requiring only that the omit decision must NOT depend on the counter being empty as its sole evidence. — Cost if wrong: the funnel could omit or emit a stage on the wrong signal.

Fix batch 2, updated with Task 8's minors:
  (g) `tests/pipeline/test_pipeline_projection_leads.py:393-397` — the three run-scoped causes are hardcoded literals while the report claims they are "enumerated from the catalog". Derive them from `ISSUE_SCOPE` so a fourth cause reaching the loop cannot drift past.
  (h) `runner.py:726` — message double-prints the outcome, because `str(ProjectionError)` already leads with the issue value.
  (i) `runner.py:877` — the all-failed fatal reads "every lead failed to tailor" while its numerator now includes leads that failed to PROJECT.
  (j) the `OUTPUT_IO_FAILURE` test replaces `_publish` wholesale, so that path never exercises `_publish`'s own atomic staging; the no-husk guarantee rests solely on the `CANDIDATE_UNRENDERABLE` test. And `:350`'s `_dispositions(...) <= {"seen"}` is satisfied by the empty set — assert equality once `seen` is known written.
Task 9: implemented (commit 5605b2c). 22 new unit + 2 new pipeline tests; tests/unit 1880 passed, tests/pipeline 1830 passed.

Ruling: my brief was wrong a NINTH time, and again in the silent way. I specified the projection stage's `entered = shortlisted - dead`. The implementer read the loop first and found that the `withheld_not_live` drop had to MOVE into the projection stage, because subtracting the dead leads instead leaves those leads counted in NO stage — "with nothing failing". It kept one `Drop` object with two possible placements, never both. This is the same class as the cohort-guard gap Task 8 found: my balance arithmetic looked right and silently dropped a bucket. — Cost if wrong: none now; the accounting is complete and pinned.

Ruling: ACCEPT both documented departures. (a) The projection stage enters at `shortlisted` rather than `shortlisted - dead`, which is what keeps the withheld bucket inside a stage. (b) The store recount compares against the LEADS rather than against `advanced`, because `advanced` legitimately exceeds the artifact rows by `tailor_failed` — `LeadArtifactError` raises above `record_artifact`. Comparing `advanced` to artifact rows, as I implied, would have pinned a FALSE invariant that fails on any tailor failure. — Cost if wrong: none identified; both were verified against the code rather than argued.

Ruling: ACCEPT the verdict-only resolution of the `_retract_projected` hazard, and its reasoning is better than either option I offered. It chose to drive the omit decision off `projection_availability` plus a hazard comment, rather than raising on a contradictory counter, because **a raise there would sit inside the swallowed reporting `finally` and therefore be a check that cannot fire**. Pinned by `test_a_stray_counter_entry_cannot_conjure_the_stage`. — Cost if wrong: a stray counter entry is inert rather than loud, which is the correct trade given it cannot surface anyway.

Task 9: the Important funnel finding is CLOSED AND PINNED, fails-first proved on a HEAD src copy — `payload["reconciles"] is True` is `False` before the change and `True` after. That was the reviewer's specific worry (that it could be closed without being proven) and it is now discharged.
Task 9: obligation 1 verified the way it needed to be — indexing the catalog instead of iterating would emit four zero drops with EVERY balance still holding, and exactly one test fails. So the absent-vs-zero rule is pinned by a test rather than by discipline.
Task 9: task review dispatched over aba48c9..5605b2c. Fix batch 2 dispatched (items a-j).
Task 9: review returned spec ✅ / quality APPROVED with one Important coverage gap. The reviewer independently reproduced the load-bearing claim by rebuilding HEAD~1's four source files into a scratch copy (verifying `__file__`, `ARTIFACT_VERSION == 4` and `grep -c projection == 0` first) and running the new pipeline test against it: `1 failed`, tripping exactly `assert payload["reconciles"] is True`. Against a real run and the frozen JSON, not the in-memory summary. It also verified the partitioning against the RUNNER rather than the report, confirmed both departures were right (`LeadArtifactError` has one raise site at `tailor.py:752`, above `record_artifact` at `:820`, so my `rows == advanced` would have been a false invariant tripping on every projected run with a tailor failure), and confirmed the store recount is genuinely independent — SQL over `json_extract(meta_json,'$.projection_kind')`, which fails where the existing `tailored` row count cannot.

Ruling: the Important finding enters a fix round for Task 9 — the test does not test its own docstring. `test_a_stray_counter_entry_cannot_conjure_the_stage` never reaches the decision site (`funnel_writer.py:235-237`), because its helper computes `projection = build_projection_counters(...) if projection_ran else None` and short-circuits first. `collect_run_funnel` is exercised from only one test file, and no pipeline test covers a projected run with an empty counter. Concrete drift scenario the reviewer named: change that line to `if projection_ran and projection_outcomes` and a real `--project` PREFLIGHT REFUSAL silently loses its NOT INSTRUMENTED stage with the whole suite green. So the very hazard I sent Task 9 mid-flight is pinned by a test that cannot see it. Needs one end-to-end refusal test asserting the stage is present-and-unmeasured in the emitted JSON. Cannot dispatch yet — fix batch 2 is live in tests/ — so it goes immediately after. — Cost if wrong: the omit/emit decision is unpinned at its only real decision site.

Task 9: minor (deferred) — the report claimed the zero-drop mutation makes "the only thing that fails" one test; the reviewer measured SEVEN. Harmless here, but it is precisely the unverified-enumeration shape this repo has been bitten by before ("an enumeration is a claim, not a census").
Task 9: minor (deferred) — `store/run_funnel_queries.py:579` hardcodes the field name in `$.projection_kind`, so the docstring's claim about not copying the emitter's constant is half true: it drops the value literal and keeps the field name. A rename of `ResumeSourceLineage.kind` breaks it, but LOUDLY (disagreement ⇒ `reconciles: false`), so the fail direction is safe.
Task 9: minor (deferred) — `projection_ran: bool = False` fails in the omission direction: a forgetful caller silently claims projection never ran. The implementer flagged it and one caller already relies on the default. Wrong fail direction for a reporting flag, but bounded.
Note for Task 10: the gate runs `ruff check .`, NOT `ruff check src tools` — several implementers linted only the narrower path. Task 10 must run the real gate.
Fix batch 2: complete (commit fb768c2, 7 files, +225/-51). 4052 passed across tests/unit + tests/pipeline + tests/projection, exit 0.

Ruling: my Fix A instrument was WRONG and this is the tenth brief defect — and the most pointed, because I specified a test to catch a specific mutation and my test would not have caught that mutation. I proposed counting calls to `read_resume_bytes`. The implementer measured that a `read_resume_bytes`-only count STAYS AT 1 through mutation 1 (`path.read_bytes()` + `load_resume(path)` — the exact example I wrote in the same brief), because that mutation bypasses the helper entirely. It instead counts both the `read_resume_bytes` bindings AND `Path.read_bytes` on the projected file, which does catch it: `1/1` unmutated, `1/2` mutated, failing on the file-read count. `reports/tailor.py` is byte-identical to HEAD, so the instrument added no production change. — Cost if wrong: none; the delivered instrument is strictly stronger than the specified one.

Ruling: my Fix D correction was ALSO stale. I said the ranker call is at `:520`, not `:527`; it is at `:588`. The implementer deleted every citation in the file rather than refreshing any, extended the change to the whole document since the preamble now promises no line numbers, and found that TWO of the existing citations named the wrong FILE — not merely the wrong line. Accepted: this is the repo's own convention (omit line numbers from prose, cite by file and symbol) and my instinct to hand-correct one number was the wrong move. — Cost if wrong: none.

Ruling: accept H1's substitution. I offered `chmod` as the way to drive an `OSError` from inside real `_publish`; the implementer used a planted file yielding `ENOTDIR` on `os.replace` instead, because **`chmod` is a no-op on Windows** and the test would have been vacuous there. It added two filesystem assertions proving staging ran and cleaned up. Better cross-platform reasoning than mine, and it matters given this repo's Windows story. — Cost if wrong: none.

Residuals recorded, not fixed (for the final review / DECISIONS):
  - the run-scoped sibling message still doubles for `bundle_unreadable`;
  - `cli/profile_bundle_cmd.py` still uses `date.today()` for three AUTHORING `as_of` values. Fix C unified the projection/render path only. Authoring is interactive TTY work where a local date is defensible, so I am NOT expanding scope — but it is a real consistency gap and belongs in the decision record;
  - five test comments now quote the old fatal text inexactly.
Task 9: fix round 1 dispatched for the Important coverage gap.
Task 9: fix round 1/5 (1 addressed, 0 open; commits 5605b2c..923e589) then COMPLETE (commits aba48c9..923e589, all findings addressed). The scoped re-review verified the can-it-fail claim BY INDEPENDENT REASONING rather than from the report, and went further: it proved the other two tests in that file are drift-BLIND (one has a non-empty counter so both branches agree; the other has `projection_ran=False` so the `and` short-circuits either way), which establishes the new test is load-bearing rather than redundant. It also confirmed the test reads `summary.funnel.json_path.read_text(...)` — the emitted JSON, not an in-memory summary — and that a stage that were simply ABSENT would fail `assert "projection" in stages`, so the refusal case cannot be satisfied by the omission case.

ALL 11 BUILD TASKS COMPLETE (1, 2, 3, 4, 5, 5b, 6, 7, 8, 9) plus two fix batches. Only Task 10 (gate + benchmark + decision record) remains.

Gate: `make check` started in the background against sha 923e589, log at .superpowers/sdd/2026-08-17-projection-pipeline-integration-p5a/make-check.log, bound four ways (sha before, branch, porcelain before, timestamps) with sha/porcelain re-recorded after so the log cannot later be read against a different tree. CPU verified free first — no pytest/make/tectonic running in any lane — because a contended gate here produces plausible false failures.
Task 10: complete (commit 4f30356, docs only). Final `make check` **exit 0** on 4f30356 == HEAD, 6566 passed / 4 xfailed, mypy clean over 275 files, index current, bound with matching sha_before/sha_after and unchanged porcelain.

Ruling: my ~100-compiles-per-run estimate was wrong by roughly 4x — measured 27 (17 select + 10 render), max 3 per lead. `_grow` compiles only candidates that clear `ADMISSION_FLOOR`, and just 1 of 8 scored above zero on this corpus. ACCEPT the implementer's handling: it set the declared ceiling against the STRUCTURAL worst case (10 compiles/lead ⇒ 32s/10 leads) rather than against today's observation, because the observation is a property of the current pool and not of the code, and pitched the ceiling at 6s/lead — exactly where a doubled candidate pool lands. Today sits 8x under. That is the right way to set a budget from a measurement. — Cost if wrong: the ceiling is generous; crossing it still signals that compile count or per-compile cost moved materially.

Ruling: the isolation finding is worth recording as a lesson, not just a result. `--data-dir` alone would NOT have isolated the benchmark — the BUNDLE resolves off `config_dir`, which is the same directory in this layout, so a naive isolation attempt would have read (and could have written) the live bundle. Both env vars had to be overridden. Proof delivered is stronger than I asked for: `job_dispositions` 0→0, `artifacts` 52→52, `runs` 22→22, `artifact_derivations` 46→46, AND the live DB's sha256 byte-identical with no `-wal`/`-shm` created.

Ruling: ACCEPT the naming correction, which caught a collision I created. "P5a" collides with this program's OWN `P5 Eligibility decides`, which STATE records as already MET — so a bare "P5a shipped" in STATE would have contradicted the phase table. The implementer wrote "the projection spec's P5" explicitly instead. My label was ambiguous across two numbering systems. — Cost if wrong: none; the explicit phrasing is unambiguous.

CROSS-LANE CONFLICT, verified myself across all four branches by enumerating `## D-` headings: **D-227 is claimed by BOTH `windows-lock-portability` (which also holds D-224) and `fixture-drift-detection`.** Neither branch can see the other's entry, so `make reindex` and the index gate pass independently on each and the collision only surfaces at merge. Messaged the fixtures lane recommending it renumber to D-228 — not because its claim is weaker, but because the locking lane is finished, closer to merge, and already anchored at D-224. Also reminded it that references in this repo are by number deliberately, so a renumber must sweep cross-references. Not mine to fix; not merging anything myself.

Final whole-branch review dispatched over 9b7cf3a..4f30356 (20 commits) on the most capable model, pointed at the ledger's 45 `Ruling:` lines and 13 deferred items for triage.

## Final whole-branch review — DO NOT SHIP (4 Important + 1 Minor)

The first Claude attempt died on a session limit mid-read; re-run through `gpt-5.6-sol` (separate budget),
saved verbatim to `docs/superpowers/specs/2026-08-17-projection-pipeline-integration-final-review.md`.
It triaged all six deferred ledger items as **can-ship** — none blocks merge. The blockers are seams.

Ruling: finding 1 is a genuine SPEC-VS-IMPLEMENTATION gap and it is mine. Design revision 3 §4.1 says
`run_tailor` must "either consume the same snapshot or compare its own resolved dependencies against the
recorded versions and refuse". My Task 6 brief listed the transformation versions as lineage FIELDS but
specified validation over only the byte hash, the model hash and `posting_version_id`. So `_plan_tier_a`
reloads taxonomy/personas/equivalences and nothing compares them — meaning a configuration change between
projection and tailoring produces an artifact whose recorded lineage names snapshot A while the transform
actually applied B. That is exactly the "stale transformation identity" defect external review round 2
rated blocking, reappearing one layer down because I under-specified the check. MUST FIX. — Cost if wrong:
lineage is decorative on the one path it exists to make trustworthy.

Ruling: finding 2 MUST FIX. A run-scoped cause discovered mid-loop (lead 2's pinned compile) sets fatal and
breaks, leaving the current and remaining leads with no terminal accounting while `projection.entered` is
still `shortlist.shortlisted` — so the stage reports DOES NOT RECONCILE. It is a FOURTH funnel case outside
the three I promised are exhaustive. — Cost if wrong: Gate P0's reconciliation clause fails on a real
operational path.

Ruling: finding 3 MUST FIX, and it is cheap. `--project --resume custom.yaml` silently ignores the explicit
résumé. My own plan said this combination "must refuse until the owner rules its meaning"; it does not.
Silent precedence between two options that both describe an active document source is the worst outcome.

Ruling on finding 4 — MY SPEC CONTRADICTED ITSELF and I am resolving it rather than passing it up. Revision 3
requires BOTH a global `ARTIFACT_VERSION` 4→5 bump AND byte-identical no-flag behaviour. Those cannot both
hold: a no-flag run now emits version 5. **Keep the global bump; narrow the claim.** A single emitter with a
single schema version is right — versioning per run type would force every consumer to handle both, which is
worse than the thing it fixes. The over-claim is "byte-identical", which I wrote about BEHAVIOUR (no
projection stage, no lineage, unchanged lead outcomes and dispositions) and should never have extended to the
artifact's own schema-version field. Correct the wording in the design, in D-225 and in STATE — do not leave
both claims recorded as met. — Cost if wrong: a consumer keying on `artifact_version == 4` sees 5 on an
authored run; acceptable, and the alternative is mixed versions.

Ruling: finding 5 (Minor) is folded into the same wave — `_publish`'s comment still describes the pre-Task-8
directory lifecycle, and on an existing directory the two replaces are not pair-atomic. Comment fix plus an
honest statement of the partial-update behaviour; no behaviour change.

One fix wave, then one scoped re-review, per the process. No second wave.

## Merge mechanics — verified, for the handoff

D-227 collision RESOLVED by the fixtures lane: it renumbered to D-228, swept every by-number reference
(heading, index row, 4 in METRICS.md, 1 in STATE.md, its PR body and its memory files), confirmed zero
`D-227` remains, re-ran `make reindex` and `program_index --check` (exit 0), and pushed. Final allocation:
D-224 + D-227 locking · **D-225 mine** · D-226 bulletless · D-228 fixtures.

Verified myself, not taken from the peer's report:
- `origin/main` now equals local `main`, tip `9b7cf3a` — which is exactly this branch's merge-base. My branch
  is **20 ahead, 0 behind**, so it fast-forwards cleanly with no rebase owed.
- `origin/main` does contain this lane's design docs.
- **`main` IS protected: 6 required status checks, `strict: false`, and `enforce_admins: false`** — that last
  flag is why an admin-authenticated push could bypass them. The run for `9b7cf3a` came back **success**, so
  the checks passed retroactively.

**A peer session pushed to protected `main`, bypassing those 6 required checks.** It self-reported this to
Mit as its error. I am recording it independently because it is his repo and his protected branch, and
because the peer warned "if your lane pushes main, expect the same bypass prompt". **This lane will not push
`main` and will not merge anything** — that decision is Mit's, and a peer's action is not approval for mine.

**Textual merge conflicts are expected across ALL FOUR lanes in `DECISIONS.md` and `METRICS.md`** — every
lane appended an entry plus an index row. The decision NUMBERS no longer collide, but the text will. The
index gate keys on LINE NUMBERS, and every merge shifts them, so **whoever merges second onward must rebase
and re-run `make reindex`**. Resolving an index conflict by hand and leaving it stale would pass locally and
fail the gate. This is the single most likely way the four-lane merge goes wrong.
