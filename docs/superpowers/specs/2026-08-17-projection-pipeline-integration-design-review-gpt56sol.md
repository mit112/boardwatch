# Slice P5 design — external review (gpt-5.6-sol, medium effort)

**Date:** 2026-08-17 · **Reviewer:** `gpt-5.6-sol` via `codex exec`, read-only sandbox
**Target:** `2026-08-17-projection-pipeline-integration-design.md`
**Verdict: REWORK** — 5 blocking, 3 major. 22 self-derived premises, 9 FALSE.

Reproduced verbatim below.

---

## 1. Premise table

I derived these premises independently from the implementation.

| # | Premise the design depends on | Result | Repository evidence |
|---|---|---|---|
| 1 | `boardwatch run` currently has no projection path. | **CONFIRMED** | The tailor loop always passes its single `resume_path` to `run_tailor`: [runner.py:518](src/boardwatch/pipeline/runner.py:518). `rg --no-ignore -n 'projection\|profile_bundle\|project_pool\|project_for_posting' src/boardwatch/pipeline tests/pipeline` returned zero hits. |
| 2 | The CLI default is `{config_dir}/resume.yaml`. | **CONFIRMED** | [run_cmd.py:55](src/boardwatch/cli/run_cmd.py:55), [run_cmd.py:74](src/boardwatch/cli/run_cmd.py:74). |
| 3 | `run_tailor` loads and validates the supplied résumé separately for each lead. | **CONFIRMED** | `_plan_tier_a` calls `load_resume(resume_path)`: [tailor.py:375](src/boardwatch/reports/tailor.py:375), [tailor.py:410](src/boardwatch/reports/tailor.py:410). |
| 4 | Projection approval can only be written as controlling-terminal approval. | **CONFIRMED** | `approved_via` is the one-value literal and is not a `write_stamp` parameter: [stamp.py:41](src/boardwatch/projection/stamp.py:41), [stamp.py:87](src/boardwatch/projection/stamp.py:87). The CLI refuses without a controlling terminal: [projection_cmd.py:116](src/boardwatch/cli/projection_cmd.py:116). |
| 5 | `project_pool` checks the stamp’s bundle digest unconditionally. | **CONFIRMED** | It always reads the stamp and compares it to the selected bundle: [pool.py:121](src/boardwatch/projection/pool.py:121), [pool.py:165](src/boardwatch/projection/pool.py:165). |
| 6 | An unattended run cannot renew a stale approval, but it can use an already-current approval. | **CONFIRMED** | The writer is TTY-only, while `project_pool` merely reads an existing stamp. Therefore §3’s stronger wording—“the approval gate cannot be satisfied unattended”—is misleading. The run cannot *repair* the gate; it can satisfy it from a pre-existing current stamp. |
| 7 | Pool construction is JD-blind and carries exact bundle/projection lineage. | **CONFIRMED** | `project_pool` takes no posting, reads one current selection, and returns revision/digests: [pool.py:121](src/boardwatch/projection/pool.py:121), [pool.py:155](src/boardwatch/projection/pool.py:155), [pool.py:221](src/boardwatch/projection/pool.py:221). |
| 8 | The current selection code does not mutate the shared pool per posting. | **CONFIRMED** | `_subset_resume` makes a copied résumé with a filtered list, and `select` only reads the pool: [select.py:119](src/boardwatch/projection/select.py:119), [select.py:174](src/boardwatch/projection/select.py:174). Hoisting the pool is safe under the current code. |
| 9 | A run-scoped `as_of` is semantically relevant, not just metadata. | **CONFIRMED** | It is passed into every entry build and effective-fact resolution: [pool.py:201](src/boardwatch/projection/pool.py:201), [pool.py:309](src/boardwatch/projection/pool.py:309). The design must specify the clock/timezone used for `run_started_date`. |
| 10 | `projection_cmd.py:443-530` is the complete reusable sequence. | **FALSE** | Persona preflight and scorer validation occur before line 443: [projection_cmd.py:393](src/boardwatch/cli/projection_cmd.py:393). Dependency imports and context construction also begin earlier: [projection_cmd.py:414](src/boardwatch/cli/projection_cmd.py:414). |
| 11 | The extracted function can raise only `ProjectionError` or `ProfileBundleError`. | **FALSE** | `TemplateArtifactError` is deliberately caught separately: [projection_cmd.py:477](src/boardwatch/cli/projection_cmd.py:477). Persona loading may raise `PersonaError` unchanged: [persona_preflight.py:21](src/boardwatch/projection/persona_preflight.py:21). |
| 12 | The proposed extraction has private and closure coupling. | **CONFIRMED** | It imports private `_default_runner`; `compile_prefix` captures renderer, scratch directory and posting page budget: [projection_cmd.py:430](src/boardwatch/cli/projection_cmd.py:430), [projection_cmd.py:460](src/boardwatch/cli/projection_cmd.py:460). |
| 13 | Eight candidates mean at most eight selection compiles per lead. | **FALSE** | `select` first compiles the pinned base, then `_grow` compiles once per attempted candidate: [select.py:4](src/boardwatch/projection/select.py:4), [select.py:148](src/boardwatch/projection/select.py:148), [select.py:189](src/boardwatch/projection/select.py:189). The maximum is nine selection compiles per lead. |
| 14 | `run_tailor` can remain unchanged while projection lineage is written into its artifact metadata. | **FALSE** | Its signature has no lineage/metadata argument: [tailor.py:452](src/boardwatch/reports/tailor.py:452). It constructs `meta` and inserts the artifact internally: [tailor.py:721](src/boardwatch/reports/tailor.py:721), [tailor.py:746](src/boardwatch/reports/tailor.py:746). |
| 15 | Production code currently parses or validates a projection manifest. | **FALSE** | `manifest.py` explicitly says nothing reads it: [manifest.py:1](src/boardwatch/projection/manifest.py:1). `rg --no-ignore -n 'ProjectionManifest\\.model_validate\|model_validate_json\|projection-manifest\\.json' src/boardwatch` found only the model/writer and CLI output path, no reader. |
| 16 | The manifest is cryptographically bound to the projected résumé bytes. | **FALSE** | It has bundle/projection digests and selection fields, but no projected-document content hash: [manifest.py:24](src/boardwatch/projection/manifest.py:24). |
| 17 | The manifest binds projection and tailoring to one posting version. | **FALSE** | `PostingContext` knows `posting_version_id`: [posting.py:38](src/boardwatch/projection/posting.py:38). `ProjectionManifest` omits it: [manifest.py:34](src/boardwatch/projection/manifest.py:34). `run_tailor` independently re-reads the current version: [tailor.py:389](src/boardwatch/reports/tailor.py:389). |
| 18 | Static fallback reliably trims to six bullets per entry. | **FALSE** | `build_plan` returns an empty plan before applying the cap when JD skills are empty or all coverage is zero: [plan.py:81](src/boardwatch/tailor/plan.py:81), [plan.py:100](src/boardwatch/tailor/plan.py:100). The six-bullet cap is only reached later: [plan.py:105](src/boardwatch/tailor/plan.py:105). |
| 19 | A successful static fallback is recorded as an ordinary built lead. | **CONFIRMED** | Any successful `run_tailor` result enters `summary.tailored`: [runner.py:590](src/boardwatch/pipeline/runner.py:590). Every tailored lead then earns permanent `built`: [runner.py:265](src/boardwatch/pipeline/runner.py:265). Existing tests explicitly require the next run to suppress built leads: [test_ledger_advances_the_queue.py:109](tests/pipeline/test_ledger_advances_the_queue.py:109). |
| 20 | Projection counters can be added “in `runner.py`, and nothing outside it changes shape.” | **FALSE** | `PipelineSummary`, `_emit_funnel`, `collect_run_funnel`, and the pure funnel model all need a new data path: [runner.py:94](src/boardwatch/pipeline/runner.py:94), [runner.py:741](src/boardwatch/pipeline/runner.py:741), [funnel_writer.py:82](src/boardwatch/pipeline/funnel_writer.py:82). |
| 21 | “No declaration” is structurally distinguishable from every other unreadable-declaration failure. | **FALSE** | Missing file, permission failure, deletion race and invalid UTF-8 all use `DECLARATION_UNREADABLE`: [declaration.py:130](src/boardwatch/projection/declaration.py:130), [declaration.py:144](src/boardwatch/projection/declaration.py:144). The proposed routine/fault severity split cannot classify these without forbidden message matching. |
| 22 | Existing CLI tests pin stale approval and custom-template refusal behavior. | **CONFIRMED** | Stale bundle approval: [test_projection_cli_resume_project.py:443](tests/projection/test_projection_cli_resume_project.py:443). `TemplateArtifactError` behavior: [test_projection_cli_resume_project.py:521](tests/projection/test_projection_cli_resume_project.py:521). |

## 2. Findings

### 1. BLOCKING — fallback permanently consumes the leads it is supposed to preserve

**What breaks:** A stale stamp followed by static fallback records each lead as permanently `built`. Re-approving projection repairs only future unsurfaced jobs; it does not re-enter the leads already consumed by fallback. The §4.4 remedy is therefore not a drain.

**Failure scenario:**

1. Mit promotes revision 22; the projection stamp is stale.
2. The scheduled `boardwatch run --project` resolves the pool once and falls back for all eight leads.
3. Static `run_tailor` succeeds, so all eight enter `summary.tailored`.
4. `_record_shortlist_dispositions` records all eight jobs as `built`.
5. Mit runs `approve-projection`.
6. The next daily run hides those jobs as `hidden_handled`; none is projected.

That directly defeats the goal of accumulating real-JD projection evidence. The existing ledger regression test guarantees this suppression behavior.

**Evidence:** Design routine fallback and claimed drain: [integration design:43](docs/superpowers/specs/2026-08-17-projection-pipeline-integration-design.md:43), [integration design:126](docs/superpowers/specs/2026-08-17-projection-pipeline-integration-design.md:126). Built disposition path: [runner.py:265](src/boardwatch/pipeline/runner.py:265), [runner.py:590](src/boardwatch/pipeline/runner.py:590).

**Suggested fix:** Resolve A2 before implementation. The safest opt-in contract is:

- Without `--project`: current static behavior.
- With `--project`: missing/stale approval or declaration is a run-level projection preflight refusal before leads earn dispositions.
- A per-lead projection failure must not earn `built` or `seen`; either leave it undisposed for retry or introduce a typed, retryable projection disposition with an actual TTL/reopen drain.

Add the required end-to-end test: stale stamp → fallback/refusal → reapprove → the same posting re-enters and projects.

### 2. BLOCKING — “one pool per run” and the proposed extraction are mutually incompatible

Section 4.1 requires exactly one `project_pool` call before the lead loop. Section 4.2 says `project_for_posting` extracts the sequence beginning with `project_pool`, and then says the pipeline calls that function for every lead.

If implemented literally, the function re-resolves the bundle per lead, defeating the one-revision invariant. If it instead accepts the pre-resolved pool, it is not the extraction the design specifies.

The body is also not self-contained: persona preflight, scorer validation, configuration resolution and dependency imports occur before line 443.

**Suggested fix:** Define two explicit APIs:

- `resolve_projection_run(...) -> ProjectionRunContext`, called once, holding the fixed `as_of`, approved pool, scorer, taxonomy and equivalences.
- `project_for_posting(context, engine, settings, posting_id, compile_runner=...)`, which never calls `project_pool`.

The CLI wrapper calls both. The pipeline calls the first once and the second per lead. Test `project_pool` call count, not merely equality of two returned pools.

### 3. BLOCKING — the proposed manifest check is tautological and does not close stale lineage

The production path constructs a fresh manifest from the same pool it proposes comparing it against. Checking only `bundle_digest` and `projection_digest` proves that two assignments in the same function agree; it does not independently verify the résumé, posting version, selected entries or actual artifact.

Concrete undetected cases:

- Resume bytes for posting A are paired with manifest B. Both share the same bundle and projection digests, so the proposed check passes.
- The posting receives a new version between `posting_context` and `run_tailor`. Selection used version A; tailoring and the artifact row use version B. The manifest has no `posting_version_id`.
- `shell_source` changes. The projected résumé changes without either checked digest moving.
- Manual `tailor run --resume stale/resume.projected.yaml` remains unchanged and still ignores the adjacent manifest, despite the design claiming to own parent §12 Q2.

Copying unchecked labels into `meta_json` makes lineage more inspectable; it does not make staleness detected.

**Suggested fix:** Add a content-bound lineage contract containing at least:

- manifest schema with exact supported-version check;
- bundle revision/digests;
- posting ID and posting-version ID;
- selected IDs and JD-skill identity;
- SHA-256 of the exact projected résumé bytes.

Validate that contract against the actual file passed to `run_tailor` and refuse if the posting version changed. If this slice claims to close Q2, define the manual `tailor run` behavior too—such as an explicit `--projection-manifest`, or mandatory adjacent-manifest validation for projected inputs.

The `shell_source` digest gap cannot safely remain out of scope while the gate claims active stale-document detection.

### 4. BLOCKING — the closed outcome catalog is neither complete nor implementable from typed exceptions

The design names four outcomes:

- `projected`
- `skipped_no_declaration`
- `skipped_stale_stamp`
- `skipped_fidelity_fault`

But live projection can also produce:

- `MISSING_PROJECTION_APPROVAL`, distinct from stale approval;
- unreadable bundle or malformed stamp as `ProfileBundleError`;
- persona registry `PersonaError`;
- posting closed/missing;
- missing JD extraction;
- pinned budget overflow;
- compile infrastructure failure;
- `TemplateArtifactError`;
- output-directory I/O failures.

Worse, a genuinely absent declaration and an unreadable existing declaration share `DECLARATION_UNREADABLE`. The required routine/fault split cannot legally distinguish them by typed data.

Section 4.1 also counts a run-scoped pool refusal once, while §4.4 reads like a per-lead outcome catalog. Those units will not reconcile.

**Suggested fix:** Specify a total typed mapping before implementation:

- Separate run-scoped projection availability from per-lead projection outcomes.
- Add a distinct typed `DECLARATION_MISSING` if absence is routine.
- Include missing approval explicitly.
- Map every current `ProjectionIssue`, `ProfileBundleError`, `PersonaError`, template, compile and I/O arm.
- Make an unmapped outcome fatal rather than a catch-all “fidelity” bucket.
- Define whether funnel counts are runs, attempted leads, or completed artifacts.

### 5. BLOCKING — A2’s “fallback is real” justification is false for exactly the weak-JD path projection improves

The design cites `MAX_BULLETS_PER_ENTRY = 6` as proof that static `resume.yaml` will trim and render. But `build_plan` never reaches that cap when the JD has no extracted skills or every bullet scores zero; it returns an empty plan.

That yields this scenario:

1. The curated projection fallback could fit a no-match JD.
2. Projection is unavailable because the stamp is stale.
3. Static fallback sees zero coverage, does not trim, and renders the full authored master.
4. The tailored render exceeds one page.
5. The “untailored” fallback is the same full master and also fails.
6. If this affects every lead, the pipeline becomes fatal under [runner.py:624](src/boardwatch/pipeline/runner.py:624).

The design’s own out-of-scope section admits the last safety rung is unreachable, so it cannot simultaneously use that fallback chain to justify A2.

A compile-infrastructure projection failure is similar: falling back invokes the same renderer/toolchain and can immediately become the existing run-level fatal.

**Suggested fix:** Do not adopt “never fatal” until the owner rules it. If fail-soft remains desired, demonstrate every fallback arm with real gate behavior—including empty JD skills, all-zero coverage, missing tectonic and full-master overflow. Otherwise, make explicit `--project` fail closed before dispositions while leaving the no-flag path unchanged.

### 6. MAJOR — the artifact-lineage write requires a `run_tailor` contract change

The runner cannot “copy” lineage into the artifact metadata after rendering without either:

- mutating an already-written artifact row;
- duplicating the artifact insertion path; or
- changing `run_tailor` to accept lineage.

The first conflicts with immutable provenance expectations; the second creates a second artifact writer; the third contradicts “`run_tailor` needs no change.”

**Suggested fix:** Give `run_tailor` a narrow typed optional source-lineage argument defined outside `projection` so the import wall remains intact. It must validate the supplied résumé hash and write lineage into the `resume_tailored` row inside the same transaction as the artifact. Do not place it only on `resume_master`: that node is content-addressed and reused, and its metadata is written only on first creation.

### 7. MAJOR — compile cost is understated, serial and accepted before measurement

With eight candidates, the worst case is:

- 1 pinned-prefix compile;
- 8 candidate attempts;
- 1 normal `run_tailor` compile.

That is at least 10 compiles per lead, or roughly 100 for ten leads—not 80. `run_tailor` may add an untailored fallback compile, and Tier B may add another. `_grow` may stop early, so the actual count can be lower, but the stated upper estimate is wrong.

“Measure after the first real projected run” is too late to define unattended-operability acceptance. A serial 100-process run can be operationally broken while every correctness test passes.

**Suggested fix:** Record a pre-merge benchmark using the live candidate count and ten representative postings, including wall time and compile-count distribution. Define a timeout or maximum acceptable stage duration. Cache only after measurement, but do not defer measurement itself.

### 8. MAJOR — A1 is a reasonable migration shape, but this is not a complete P5 gate

Keeping static output as the default while collecting evidence is defensible. Calling this completed slice P5 is not: the parent P5 gate explicitly includes “`resume.yaml` stops being the daily default,” and this design explicitly leaves that clause unmet.

The design also does not settle:

- what evidence permits the default flip;
- what `--project` combined with explicit `--resume custom.yaml` means;
- whether the existing `--bundle`, `--declaration`, and `--scorer` overrides remain available;
- whether a non-owner user can select their own bundle/declaration without adopting Mit’s filesystem convention.

**Suggested fix:** Split delivery status explicitly:

- P5a: opt-in pipeline integration and measured real-JD evidence.
- P5b: owner-ruling/default migration, with named measurable criteria.

Do not mark parent P5 met after P5a.

## 3. Testing and gate assessment

The defect class that passes every listed §6 test is:

> **A projection fallback successfully renders static résumés, records them as permanently built, and prevents those same leads from re-entering after the projection stamp is repaired.**

All listed assertions can pass: fallback occurred, the right counter incremented, exit status remained zero, one revision was used, and static behavior was unchanged. None tests the next run’s ledger visibility.

A second missed class is a posting-version change between `posting_context` and `run_tailor`; the proposed digest checks still pass because the manifest does not carry `posting_version_id`.

The §8 gate can therefore be met while the feature remains broken:

- one live run can successfully project;
- an artificial digest mismatch can be refused;
- artifact metadata can carry four lineage labels;
- the default can remain static;
- stale approval can still consume and permanently suppress real leads;
- manual stale projected résumés remain renderable.

`make check` cannot cure an underspecified contract; it can only verify the implementation and tests supplied.

## 4. Verdict

**REWORK**

The single most important change is to resolve A2 so a projection failure cannot earn a permanent `built` disposition and remove the lead from the projection retry population. Until that has a real drain, opt-in fallback defeats the feature’s evidence-gathering purpose.

## 5. Scope statement

I did not:

- edit or create any files;
- run `make check` or runtime tests, because this was a read-only design review with no implementation diff;
- benchmark real Tectonic execution;
- inspect Mit’s private live bundle, projection configuration or production store;
- assess the P6 model reranker;
- review parent-design sections unrelated to the requested integration and adjacent contracts;
- perform a general security/privacy audit beyond lineage, path and multi-tenancy implications.


