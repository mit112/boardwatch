# Slice P5a branch — final whole-branch review (gpt-5.6-sol)

**Date:** 2026-08-17 · **Target:** `projection-pipeline-p5a`, 20 commits `9b7cf3a..4f30356`
**Verdict: DO NOT SHIP** — 4 Important seam findings + 1 Minor, plus deferred-item triage.

Reproduced verbatim below.

---

## Merge verdict: DO NOT SHIP

Four integration contracts remain broken. Shortest path to shippable:

1. Validate or consume the frozen taxonomy/persona/equivalence snapshot inside `run_tailor`.
2. Account for late run-scoped projection failures without producing a fourth, unbalanced funnel case.
3. Refuse `--project` combined with an explicit `--resume`.
4. Resolve the no-flag byte-identity contradiction around artifact version 5.
5. Add seam regressions, rerun `make check`, and correct D-225/STATE/METRICS claims.

I accepted the supplied exact-SHA gate, benchmark, store-isolation, and SQL lineage evidence; I did not rerun them.

## Seam findings

### Important — recorded transformation lineage can differ from the transformation actually applied

[src/boardwatch/reports/tailor.py:445](src/boardwatch/reports/tailor.py:445)

Scenario: the run freezes taxonomy/persona/equivalence versions A → projection writes a résumé and lineage naming A → configuration changes before tailoring → `_plan_tier_a` reloads taxonomy/personas/equivalences at lines 446, 449, and 484 → a missing taxonomy extraction is even coalesced to an empty set → tailoring runs under B → lines 801–802 write lineage claiming A.

`_master_from_lineage` validates only document hashes and posting version. It never compares the reloaded transformation versions. Two leads can therefore be transformed under different rules, with the second artifact falsely labeled as using snapshot A.

Suggested fix: pass the frozen objects into `run_tailor`, or compare the versions actually loaded there against `source_lineage` before persona application/planning and raise `ResumeLineageMismatch` on disagreement. Test taxonomy, persona, and equivalence changes between projection and tailoring.

### Important — a late run-scoped failure creates an unbalanced fourth funnel case

[src/boardwatch/pipeline/runner.py:704](src/boardwatch/pipeline/runner.py:704)

Scenario: preflight reports `AVAILABLE` for ten leads → lead 1 projects → lead 2’s pinned compile discovers a missing tool, bad template, pinned overflow, or pinned compile failure → `_projection_scope` returns run-scoped availability → the loop sets fatal and breaks → current and remaining leads receive no terminal accounting.

The funnel nevertheless declares `projection.entered = shortlist.shortlisted` at [run_funnel.py:791](src/boardwatch/reports/run_funnel.py:791), while `advanced` and drops contain only work completed before the break. The stage reports `DOES NOT RECONCILE`.

That creates a fourth case outside the promised three:

- flag absent;
- preflight refused;
- balanced projection run;
- **preflight passed, projection started, then aborted unbalanced**.

Suggested fix: move run-invariant template/toolchain/pinned checks into the pre-ranking preflight, and explicitly account for unattempted leads if a systemic condition can still arise mid-loop. Add a real emitted-funnel regression for each run-scoped issue reachable from `select()`.

### Important — `--project --resume custom.yaml` silently ignores the explicit résumé

[src/boardwatch/cli/run_cmd.py:87](src/boardwatch/cli/run_cmd.py:87)

Scenario: a user runs `boardwatch run --project --resume custom.yaml` → the CLI accepts both → `custom.yaml` is passed into the pipeline → every projected lead overwrites `lead_resume_path` with `resume.projected.yaml` → the explicit option has no effect.

The plan explicitly says this unresolved combination must refuse until the owner rules its meaning. Silent precedence is especially unsafe because both help entries describe active document-source choices.

Suggested fix: reject `project and resume_path is not None` at the CLI boundary with a typed usage error and test that no run row or disposition is written.

### Important — no-flag output is not byte-identical because every funnel is now version 5

[src/boardwatch/reports/run_funnel.py:78](src/boardwatch/reports/run_funnel.py:78)

Scenario: run identical inputs without `--project` before and after this branch → projection stage remains omitted, but `artifact_version` changes from 4 to 5. The JSON is therefore not byte-identical.

This exposes an unresolved contradiction in revision 3: it requires both a global 4→5 bump and byte-identical no-flag behavior.

Suggested fix: emit v4 for authored runs and v5 for projected runs, or obtain an explicit owner amendment narrowing “byte-identical.” Do not leave both claims recorded as met.

### Minor — `_publish` still describes the pre-Task-8 directory lifecycle

[src/boardwatch/projection/run.py:431](src/boardwatch/projection/run.py:431)

The comment says the pipeline creates the lead directory before `_publish`; the final runner deliberately does not. On an existing directory, the two files are also replaced individually, so the operation is not pair-atomic.

Suggested fix: correct the comment and state the actual existing-directory partial-update behavior. Consider preserving/restoring the old pair if the second replacement fails.

## Deferred-item triage

| Ledger item | Triage | Reason |
|---|---|---|
| `core/lineage.py` double negative | can-ship | Cosmetic wording only. |
| Test-local `lineage` shadows module import | can-ship | Test readability; no behavior change. |
| False line-length justification for test helper | can-ship | The helper is harmless; only the recorded rationale is wrong. |
| Taxonomy validation now precedes bundle/stamp refusal | can-ship | Both remain typed refusals; this changes diagnostic ordering only. |
| Second `PersonaError` race arm is near-dead | can-ship | A legitimate between-read race guard, although narrow coverage would help. |
| `_fatal_if_infrastructure` overstates two arms | can-ship | Its docstring now states the real attribution rules; rename separately. |
