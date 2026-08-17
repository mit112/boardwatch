# Slice P5a design revision 2 — external review, round 2 (gpt-5.6-sol, medium effort)

**Date:** 2026-08-17 · **Reviewer:** `gpt-5.6-sol` via `codex exec`, read-only sandbox
**Target:** revision 2 of `2026-08-17-projection-pipeline-integration-design.md`
**Verdict: REWORK** — 4 blocking, 2 major, 1 minor. Round-1 audit: 6 CLOSED, 2 RELOCATED, 2 NOT CLOSED.
**14 fresh premises on the new material, 9 FALSE.**

Reproduced verbatim below.

---

## 1. Round-1 disposition audit

| # | Result | Independent ruling |
|---|---|---|
| 1 | **CLOSED** | Removing static fallback eliminates the permanent-`built` scenario. A preflight can precede every lead disposition because ranking disables its own `seen` writes ([runner.py:428](src/boardwatch/pipeline/runner.py:428)) and the pipeline writes dispositions only after the tailor loop ([runner.py:606](src/boardwatch/pipeline/runner.py:606)). Revision 2 still needs exact placement and fatal semantics, addressed below. |
| 2 | **RELOCATED** | Two APIs remove the repeated-`project_pool` contradiction, but the promised frozen context is not actually reusable with the current seam: `posting_context` reruns extraction preflight and reloads taxonomy for every posting ([posting.py:46](src/boardwatch/projection/posting.py:46)), while `select` separately consumes the taxonomy stored in the proposed run context ([select.py:174](src/boardwatch/projection/select.py:174)). One pool is fixed; one configuration snapshot is not. |
| 3 | **RELOCATED** | `resume_sha256` and `posting_version_id` close the specific manifest-A/résumé-B and posting-A/posting-B examples, but lineage still omits taxonomy, equivalence-table, scorer, persona, and—despite §4.1 promising it—`as_of`. `run_tailor` reloads those dependencies independently ([tailor.py:383](src/boardwatch/reports/tailor.py:383), [tailor.py:419](src/boardwatch/reports/tailor.py:419)). The stale-lineage defect moved from document identity to transformation identity. |
| 4 | **NOT CLOSED** | The design claims a total mapping but supplies neither a mapping table nor exhaustive typed implementation. There are **32** current `ProjectionIssue` members ([errors.py:15](src/boardwatch/projection/errors.py:15)), plus omitted `TaxonomyError` and `EquivalenceError` families ([taxonomy.py:30](src/boardwatch/extract/taxonomy.py:30), [equivalences.py:12](src/boardwatch/tailor/equivalences.py:12)). Several failures are also assigned to the wrong unit. |
| 5 | **CLOSED** | The false static-fallback argument has been removed. Empty or zero-coverage JDs no longer underpin A2. |
| 6 | **CLOSED** | Revision 2 now admits that `run_tailor` needs a contract change. An optional keyword argument preserves existing callers because the current function is keyword-oriented ([tailor.py:452](src/boardwatch/reports/tailor.py:452)). Its type must live in a genuinely neutral module—not merely “outside projection”—to preserve the transitive import wall ([test_profile_bundle_tailor_isolation.py:107](tests/profile_bundle/test_profile_bundle_tailor_isolation.py:107)). |
| 7 | **CLOSED** | The compile estimate is corrected to at least ten per lead, acknowledges the possible extra fallback compile, and now requires a pre-merge benchmark and budget. |
| 8 | **CLOSED** | Renaming this slice P5a and expressly leaving parent P5 unmet is honest. The resulting P5a gate remains insufficient, but it no longer falsely claims to complete P5. |
| P6 correction | **CLOSED** | “Cannot repair unattended” is the accurate statement. Existing stamps are consumable; creating one remains TTY-only. |
| P20 correction | **NOT CLOSED** | Naming `PipelineSummary`, `_emit_funnel`, and the writer is not a data-path design. The current funnel has a closed, balanced stage model and version convention ([run_funnel.py:61](src/boardwatch/reports/run_funnel.py:61), [run_funnel.py:706](src/boardwatch/reports/run_funnel.py:706)); revision 2 specifies neither where projection enters that model nor how its counts reconcile. |

Partial rejection of finding 3: **legitimate as a scope ruling, but not as a technical defense**. Parent §4.2 explicitly assigns pipeline-side validation to P5 ([parent design:321](docs/superpowers/specs/2026-08-13-career-profile-projection-design.md:321)), while §12 Q2 separately asks whether manual `tailor run` should validate a manifest ([parent design:665](docs/superpowers/specs/2026-08-13-career-profile-projection-design.md:665)). Therefore this slice need not close the manual path. However, the quoted rationale that P5 “requires no change to tailor” is obsolete: revision 2 itself correctly accepts a `run_tailor` change.

## 2. New premises

| # | Premise | Result | Evidence |
|---|---|---|---|
| 1 | A projection preflight can run before any lead earns `seen`, `skipped`, or `built`. | **CONFIRMED** | The ranker is called with `record_surfaced=False` ([runner.py:428](src/boardwatch/pipeline/runner.py:428)); all shortlist dispositions are deferred to [runner.py:606](src/boardwatch/pipeline/runner.py:606). |
| 2 | Such a preflight can occur before the run or scan writes anything. | **FALSE** | The scan creates the run row before scanning ([coordinator.py:181](src/boardwatch/scan/coordinator.py:181)), and scan application writes versions/events ([apply.py:122](src/boardwatch/scan/apply.py:122)). “No lead disposition” is achievable; “nothing recorded” is not under the current lifecycle. |
| 3 | Saying the run “refuses” determines a non-zero exit. | **FALSE** | Only `summary.fatal` controls persisted failure ([runner.py:718](src/boardwatch/pipeline/runner.py:718)) and CLI exit 1 ([run_cmd.py:107](src/boardwatch/cli/run_cmd.py:107)). Revision 2 never says the availability refusal sets `fatal`. |
| 4 | P3’s existing zero-output/cohort guards can classify an early refusal. | **FALSE** | Both execute after the disposition write and require the ranked cohort ([runner.py:624](src/boardwatch/pipeline/runner.py:624), [runner.py:668](src/boardwatch/pipeline/runner.py:668)). An early preflight must set fatal directly. |
| 5 | `ProjectionRunContext.taxonomy` guarantees one taxonomy across postings. | **FALSE** | `posting_context` reloads taxonomy and invokes `run_preflight` on every call ([posting.py:53](src/boardwatch/projection/posting.py:53)). |
| 6 | Selection and tailoring naturally share one taxonomy, equivalence table, and persona snapshot. | **FALSE** | `run_tailor` independently reloads taxonomy, personas, and equivalences ([tailor.py:383](src/boardwatch/reports/tailor.py:383), [tailor.py:419](src/boardwatch/reports/tailor.py:419)). |
| 7 | `posting_version_id` is available and comparable at both boundaries. | **CONFIRMED** | `PostingContext` carries it ([posting.py:38](src/boardwatch/projection/posting.py:38)); `_plan_tier_a` resolves its own `CurrentVersion` ([tailor.py:389](src/boardwatch/reports/tailor.py:389)). |
| 8 | The proposed hash contract guarantees that the bytes validated are the bytes parsed. | **FALSE** | `load_resume` currently rereads a path ([tailor.py:410](src/boardwatch/reports/tailor.py:410)); existing master identity hashes parsed-model JSON, not raw input bytes ([tailor.py:482](src/boardwatch/reports/tailor.py:482)). A separately performed path hash leaves a read/swap/read race. |
| 9 | `DECLARATION_MISSING` can be raised without message matching. | **CONFIRMED** | The missing-file branch already exists distinctly at the raise site ([declaration.py:130](src/boardwatch/projection/declaration.py:130)); only its issue member needs changing. |
| 10 | The two catalogs cover every typed dependency loaded by the new run resolver. | **FALSE** | Taxonomy and equivalence loading have their own typed errors, neither named by §4.4 ([taxonomy.py:60](src/boardwatch/extract/taxonomy.py:60), [equivalences.py:61](src/boardwatch/tailor/equivalences.py:61)). |
| 11 | Every listed per-lead outcome is genuinely posting-scoped. | **FALSE** | The template and renderer are shared, and the current runner treats template/tool failures as systemic fatal conditions ([runner.py:530](src/boardwatch/pipeline/runner.py:530)). Page budget is also the same profile value for every posting ([posting.py:80](src/boardwatch/projection/posting.py:80)). |
| 12 | Adding projection counters to the three named objects is sufficient for funnel correctness. | **FALSE** | The current `tailor` stage balances `shortlisted = tailored + tailor_failed + withheld_not_live` ([run_funnel.py:787](src/boardwatch/reports/run_funnel.py:787)). Projection failures would create an unexplained gap unless a projection stage or new drop partition is designed. |
| 13 | An empty JD-skill extraction is the same outcome as missing extraction. | **FALSE** | `jd_skills_for` explicitly distinguishes missing (`None`) from a valid empty set ([tailor.py:346](src/boardwatch/reports/tailor.py:346)); `select` deliberately uses fallback when no candidate scores ([select.py:204](src/boardwatch/projection/select.py:204)). The catalog name `no_jd_skills` risks collapsing them. |
| 14 | Projection-on failures inherit the existing no-husk guarantee. | **FALSE** | Projection writes two sidecars before `run_tailor` ([projection_cmd.py:491](src/boardwatch/cli/projection_cmd.py:491)); runner cleanup removes only an empty directory ([runner.py:873](src/boardwatch/pipeline/runner.py:873)). The existing regression explicitly forbids failed-lead directories ([test_pipeline_run.py:250](tests/pipeline/test_pipeline_run.py:250)). |

## 3. New findings

### BLOCKING — A fail-closed refusal can still be recorded as a successful empty run

Failure scenario:

1. `--project` has a stale approval.
2. The new preflight returns a non-`available` outcome before ranking and writes no disposition.
3. The implementation does not set `summary.fatal`, because revision 2 specifies “refuses” but not the run-state transition.
4. `finish_run` writes `status=ok`, and the CLI exits 0.
5. The ledger-visibility test passes: no disposition exists, and the posting projects after reapproval.
6. P3 nevertheless observes a run reporting success while producing nothing.

The zero-output and cohort guards cannot repair this because an early return never reaches them.

Suggested fix: place preflight explicitly after scan outcome handling but before ranking; every unavailable outcome must set a typed fatal message, append the run error, return through `finally`, and produce `RUN_FAILED`/exit 1. Add this as a fifth run-contract fatal class and test exit code, `runs.status`, funnel fatal, no disposition, and retry visibility together.

### BLOCKING — the “frozen” run context permits mixed configuration and undetectably stale transformation lineage

Failure scenario:

1. `resolve_projection_run` loads taxonomy A, equivalences A, persona A, and creates the pool.
2. A tenant or concurrent process edits `taxonomy.yaml` before posting 2.
3. `posting_context` reloads taxonomy B and creates/reads JD skills under B.
4. `select` scores résumé bullets with taxonomy A from the run context.
5. `run_tailor` reloads taxonomy B and equivalences/personas afresh.
6. The résumé hash and posting-version check both pass, but selection and tailoring used different rules. The artifact’s bundle lineage looks valid while its transformation is not reproducible.

The proposed manifest also omits scorer identity, taxonomy version, equivalence version, persona version, and `as_of`; the current manifest model confirms none exists ([manifest.py:34](src/boardwatch/projection/manifest.py:34)).

Suggested fix: make `posting_context` accept the run’s taxonomy instead of loading one; freeze every transformation dependency once; add `as_of`, scorer identifier/version, taxonomy version, equivalence version, and persona-registry version to lineage; require `run_tailor` either to consume that snapshot or compare its dependencies before parsing/rendering.

### BLOCKING — disposition 4’s claimed “total catalog” is still neither total nor correctly partitioned

Concrete failures:

- A malformed taxonomy raises `TaxonomyError`, which is absent from both catalogs.
- A malformed equivalence table raises `EquivalenceError`, also absent.
- `PINNED_SET_EXCEEDS_BUDGET`, template invalidity, and compile infrastructure failure are assigned per-lead even though they are invariant across this run’s shared résumé, profile page budget, template, and toolchain.
- `no_jd_skills` can be implemented by mistakenly treating a valid empty extraction as failure, bypassing the curated no-match fallback.
- Thirty-two `ProjectionIssue` values are compressed into aggregate outcomes without an explicit exhaustive mapping, so “unmapped ⇒ fatal” cannot itself be reviewed.

A missing renderer discovered on lead 1 may consequently be retried for every lead and those failed leads may receive `seen` before the later all-failed fatal check, because disposition recording currently precedes that check ([runner.py:606](src/boardwatch/pipeline/runner.py:606), [runner.py:624](src/boardwatch/pipeline/runner.py:624)).

Suggested fix: define actual run/per-lead enums and an exhaustive mapping table covering all 32 issues plus every foreign typed exception. Hoist shared template, pinned-budget, taxonomy, equivalence, and toolchain validation to run preflight. Rename `no_jd_skills` to `extraction_unavailable`; a valid empty set must continue into fallback selection.

### BLOCKING — the funnel design is incomplete and can either fail reconciliation or hide projection loss

Failure scenario:

1. Eight live leads enter the current tailor edge.
2. Two fail projection and six reach `run_tailor`.
3. The new counters report two projection failures, but the existing stage still says eight entered, six advanced, with only `tailor_failed` and liveness drops.
4. The funnel fails reconciliation—or the implementation silently folds projection failure into `tailor_failed`, destroying the new catalog’s meaning.
5. Every §6 projection test can still pass because none requires a balanced, independently recounted projection stage.

Adding a new top-level projection block also requires an artifact-version decision; current convention retains version 4 only for additive keys inside existing blocks, while prior bumps represent new top-level sections ([run_funnel.py:61](src/boardwatch/reports/run_funnel.py:61)).

Suggested fix: add an explicit `projection` stage between liveness and tailor:

`served_after_liveness = projected + every per-lead projection drop`

Then make the tailor stage enter at `projected`, not `shortlisted`. Add a store-backed cross-check using `resume_tailored` rows carrying projection lineage, test every balance, and bump the artifact version if projection is a new top-level section.

### MAJOR — the byte-hash check is vulnerable to a second-read race, and failed paths leave partial artifacts

Failure scenario:

1. `project_for_posting` hashes `resume.projected.yaml`.
2. The path is replaced or rewritten before `load_resume` rereads it.
3. The expected hash passes against the first read, but `run_tailor` parses different bytes.
4. Alternatively, `run_tailor` simply fails after projection writes its two sidecars.
5. `_remove_if_empty` cannot remove the non-empty lead directory, leaving a projected résumé and manifest that look like a deliverable although no artifact row/PDF exists.

The listed mismatch test changes the file before validation; it does not exercise a swap between validation and parse. The negative-control pipeline suite runs without `--project`, so its no-husk assertion does not cover this path.

Suggested fix: read the projected document exactly once into immutable bytes, hash those bytes, and parse that same buffer. Validate hash and posting version before any render or output. Define atomic sidecar writes and delete only projection-owned files on every failure; add projection-on no-husk and partial-write tests.

### MAJOR — P5a’s gate is measurable but not sufficient

The gate can pass with:

- one successful owner-layout run;
- a stale-stamp retry test that returns exit 0;
- a simple pre-validation hash mismatch;
- ten acceptable benchmark postings;

while mixed taxonomy/equivalence snapshots, broken funnel reconciliation, partial failed-lead directories, and non-owner configuration remain untested. The gate also explicitly defers whether another tenant can choose their own bundle/declaration ([integration design:274](docs/superpowers/specs/2026-08-17-projection-pipeline-integration-design.md:274)).

Suggested fix: require at least:

- failed status/non-zero exit for every run-unavailable outcome;
- projection-stage funnel reconciliation and an independent lineage recount;
- configuration-drift tests;
- no partial folders on every per-lead failure;
- a test using a second temporary `config_dir` with its own bundle and declaration.

### MINOR — `as_of` is promised but absent from the lineage contract

Section 4.1 says `as_of` is recorded in the manifest, but §4.3’s field table omits it, and the current manifest has no such field. Because `as_of` controls fact effectiveness in pool construction ([pool.py:201](src/boardwatch/projection/pool.py:201)), this is not cosmetic.

Suggested fix: add an ISO date `as_of` field to the bumped manifest schema and source it from the persisted run’s `started_at`, avoiding a midnight mismatch from a later independent `utcnow()` call.

The defect class still passing every listed §6 test is: **taxonomy or equivalence configuration changes after run resolution but before a posting is selected/tailored**. Bundle promotion is the only simulated mid-run mutation; all listed hash and posting-version assertions still pass.

## 4. Verdict

**REWORK**

The single most important change is to replace §4.4’s prose catalogs with an executable, exhaustive projection state machine that fixes the preflight’s exact position, fatal/non-fatal direction, frozen dependency snapshot, funnel edge, and disposition behavior. Until that exists, “Fixed” finding 4 is false and the run can report success, mix configuration versions, or lose funnel balance.

## 5. Scope statement

I did not:

- modify or create files;
- run `make check` or runtime tests, because there is no implementation diff and this was a read-only design review;
