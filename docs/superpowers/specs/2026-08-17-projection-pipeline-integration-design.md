# Projection inside `boardwatch run` — slice P5a design

**Date:** 2026-08-17 · **Revision 3** · **Status:** awaiting owner review, then build
**Implements:** part of slice **P5** of `2026-08-13-career-profile-projection-design.md` §10, and that
design's **§12 Q1** (ruled by Mit 2026-08-13: *"what is settled is that it happens; what is open is its
form"*).
**Owns:** §4.2's *pipeline-side* stale-lineage gap.
**Reviews:** two rounds by `gpt-5.6-sol`, both **REWORK**, both preserved verbatim in the repo
(`...-review-gpt56sol.md`, `...-review-gpt56sol-r2.md`). Round 1: 5 blocking + 3 major, 9 of 22
self-derived premises FALSE. Round 2 audited those dispositions (6 CLOSED, 2 RELOCATED, 2 NOT CLOSED) and
found 4 new blocking + 2 major + 1 minor on revision 2's own new material, 9 of 14 fresh premises FALSE.
Dispositions for both rounds in §9.

**Review loop closes here, deliberately.** The severity *kind* converged: round 1's blockers were "this
design defeats its own purpose"; round 2's were "these mechanisms are underspecified", each with a concrete
named fix now incorporated. The parent design burned three rounds and its own §13a records fix-rounds
*creating* defects, so a third round buys less than building does. Remaining risk after revision 3 is
implementation risk, which is what tests and `make check` exist for.

---

## 1. Why this slice, now

The bundle → résumé track is v1-complete: Stage 1 and Stage 2 both work, all eleven entities' bullets are
refined, Gate B is MET, and the pool renders one page with zero overfull. None of it reaches an unattended
run. Measured, not recalled:

- `rg --no-ignore 'projection|profile_bundle|project_pool' src/boardwatch/pipeline/` returns **zero hits**.
- `pipeline/runner.py:518` passes one `resume_path` to `run_tailor`; `run_cmd.py:55,74` defaults it to
  `{config_dir}/resume.yaml`; `run_tailor` reaches `load_resume` at `reports/tailor.py:375,410`.

So the résumé an unattended run produces is **not** the résumé eleven sessions of bullet work produced.

**Scope honesty, up front.** This is **P5a**, not all of P5. The parent P5 gate includes *"`resume.yaml`
stops being the daily default"*, and this slice deliberately leaves that clause unmet (§2 A1, §8). Parent
P5 must not be marked met when this ships. Parent **§12 Q2** — whether *manual* `tailor run` validates a
manifest — is **not** owned here either; revision 1 claimed it and was wrong. Parent §4.2 assigns
*pipeline-side* validation to P5, while Q2 separately asks about the manual path. Note that §4.2's own
stated reason — that P5 "requires no change to `tailor`" — is **obsolete**: §4.3 accepts a narrow
`run_tailor` change. The scope conclusion survives that; the rationale does not (§9).

## 2. Decisions, and their standing

Mit was unavailable when both were needed, so both are assumptions flagged for review. **A2 was inverted in
revision 2 and given its run-state semantics in revision 3** — the reviews confirmed the inversion was
right, so the assumption held, but it was incomplete twice over.

**A1 — Form: opt-in `boardwatch run --project`.** `resume.yaml` stays the unattended default. §8 of the
parent design requires it until projection is proven on real JDs, and hand-running one posting at a time is
not that proof. **Rejected:** projection as the default stage (flips before the proof condition), and an
auto-flip on a metric (invents a criterion nobody argued for). What evidence licenses the flip is named in
§8 as owner-gated, not decided here.

**A2 — Fail closed at a run-level preflight. No per-lead fallback.** With `--project`, if projection is
unavailable — no stamp, a stale stamp, an unreadable or absent declaration, an unreadable bundle — the
projection stage refuses **before any lead earns a disposition**, and the run ends without consuming leads.
Without `--project`, **behaviour** is unchanged: no projection stage is emitted, no lineage keys are
written, and lead outcomes and dispositions are exactly what they were. The funnel artifact's own
`artifact_version` field is the one thing that does move — see §4.5.

**Revision 1 said the opposite, and it was a blocking defect.** It proposed rendering each lead from static
`resume.yaml` on projection failure. That fallback *succeeds*, so every lead enters `summary.tailored`
(`runner.py:592`), and `built_ids` is derived from exactly that set (`runner.py:268`), earning each lead a
**permanent `built`** disposition. `tests/pipeline/test_ledger_advances_the_queue.py:109` pins that the next
run suppresses built leads. So the fallback permanently consumes precisely the leads this slice exists to
gather projection evidence from, and re-approving projection cannot bring them back. Revision 1 called the
morning artifact's remedy line a "drain"; naming a remedy is not a drain when the leads are already gone.

**Revision 1's supporting argument was also false.** It cited `MAX_BULLETS_PER_ENTRY = 6` (`plan.py:107`) as
proof that static fallback trims and renders. `build_plan` returns an empty plan **before** reaching that
cap when `jd_skills` is empty (`plan.py:84`) or when no bullet covers anything (`plan.py:101`). On exactly
those weak JDs the full 6,134-char master renders, exceeds `resume_max_pages=1`, and the untailored rung is
the same document — so the fallback chain fails, and if it fails for every lead the run is fatal anyway
(`runner.py:624`). The fallback was weakest precisely where projection helps most.

**Consequence accepted:** on a day when the stamp is stale, `--project` produces nothing. That is the
correct cost — no leads are burned, so every one of them is still available the moment `approve-projection`
runs. **This is the drain**, and it is structural rather than advisory: leads are never consumed, so nothing
needs re-entering.

**"Refuses" is not a run state, and revision 2's failure to say so was a blocking defect.** Only
`summary.fatal` decides the persisted status — `status=RUN_FAILED if summary.fatal is not None else RUN_OK`
(`runner.py:721`) — and `run_cmd.py` deliberately exits 0 for non-fatal stage errors, because "making the
daily driver exit 1 every day would destroy the exit status as a signal". So an unavailability refusal that
merely returns early would write `status=ok` and exit 0 while producing nothing, which is exactly P3's *"0
runs reporting success while producing nothing"*. Worse, P3's existing guards cannot catch it: both
`_zero_output_guard` and `_cohort_guard` run **after** the disposition write and need the ranked cohort
(`runner.py:624,668`), so an early return never reaches them.

Therefore every non-`available` availability outcome **sets a typed `summary.fatal`**, appends to the run
errors, and returns through the existing `finally` so `finish_run` records `RUN_FAILED` and the CLI exits 1.
**This is a fifth fatal class and it is added to `docs/program/RUN_CONTRACT.md` in the same change** — a new
fatal condition that is not in the written contract is the contract rotting.

**Placement:** after scan-outcome handling, **before** ranking. That position is what makes "no lead earns a
disposition" true rather than hoped for: the ranker is already called with `record_surfaced=False`
(`runner.py:428`) and every shortlist disposition is deferred to `runner.py:606`. Note the honest limit —
*no lead disposition* is achievable, *nothing recorded at all* is not: the `runs` row is created before
scanning (`scan/coordinator.py:181`) and scan application writes versions and events. The claim is scoped to
lead dispositions, which is what the drain needs.

**Rejected alternatives:** fall back but record no disposition (touches disposition logic, which is Gate-P6
dedup territory, for a benefit fail-closed already provides); and a new typed retryable projection
disposition with a TTL/reopen drain (a new catalog value plus its drain mirrored across the funnel — real
machinery to solve a problem fail-closed dissolves).

## 3. What forces the design

**An unattended run can satisfy the approval gate, but can never repair it.** `ProjectionStamp.approved_via`
is a one-value `Literal` and is not a `write_stamp` parameter (`stamp.py:41,62,87,100-102`); the CLI refuses
without a controlling terminal (`projection_cmd.py:116`); and `project_pool` reads the stamp back and
compares `bundle_digest` unconditionally (D-167, `pool.py:121,165`). So a *current* stamp works unattended
exactly as it does by hand — what a 07:00 run cannot do is create or renew one. Revision 1's "the approval
gate cannot be satisfied unattended" was an overclaim.

> **The projection stage never writes a stamp, and no non-TTY approval path is added — not now, not behind
> a flag.**

Because every promotion invalidates the stamp, **a stale stamp is the expected steady state**, which is
what makes A2's fail-closed cost routine rather than exceptional, and why §4.4 treats it as a first-class
reported outcome rather than an error.

## 4. Architecture

### 4.1 Two APIs, not one extraction

Revision 1 said "resolve the pool once per run" *and* "extract the sequence beginning with `project_pool`,
then call it per lead" — mutually incompatible. Revision 2 splits them explicitly, in a new
`src/boardwatch/projection/run.py`:

```
resolve_projection_run(...) -> ProjectionRunContext     # called ONCE per run
project_for_posting(context, engine, settings, posting_id, *, compile_runner) -> ProjectionOutcome
```

`ProjectionRunContext` is frozen and carries the fixed `as_of`, the approved pool, the scorer, the taxonomy
and the equivalence table. **`project_for_posting` never calls `project_pool`.**

**The extraction is wider than revision 1 claimed.** The reusable sequence does not start at
`projection_cmd.py:443`: persona preflight and scorer validation happen at `:393`, and dependency imports
and context construction at `:414`. Both belong to `resolve_projection_run`.

**Couplings the extraction must sever, not inherit:**

- `reports.tailor._default_runner` is imported privately (`projection_cmd.py:430`). `project_for_posting`
  takes an injected `compile_runner` instead, so `projection` does not reach into `reports` internals.
- The `compile_prefix` closure captures the renderer, a temp-dir lifetime, and `posting.page_budget`
  (`projection_cmd.py:460-466`). The temp dir's lifetime must be owned inside `project_for_posting`, not by
  a caller's `with` block.
- **Three exception families cross the boundary, not two.** `ProjectionError` and `ProfileBundleError`
  (`:445`), `TemplateArtifactError` (`:477`, deliberately separate), and `PersonaError` from persona
  loading (`persona_preflight.py:22`). §4.4's mapping must be total over all of them.

**One pool is not one configuration, and revision 2 conflated them.** Freezing the pool leaves the rest of
the transformation floating:

- `posting_context` **reloads the taxonomy and reruns extraction preflight on every call**
  (`posting.py:53`), so posting 2's JD skills can be extracted under a different taxonomy than posting 1's;
- `select` meanwhile scores against the taxonomy held in the run context — so **selection can score under
  taxonomy A while JD extraction ran under taxonomy B**, in the same run;
- `run_tailor` independently reloads taxonomy, personas and equivalences again (`tailor.py:383,419`).

The failure this permits is not a stale *document* — `resume_sha256` and `posting_version_id` catch that —
it is a stale *transformation*: both checks pass, the artifact's bundle lineage looks valid, and the run is
not reproducible because selection and tailoring applied different rules. Round 2 named this precisely as
lineage moving "from document identity to transformation identity".

**So the freeze covers every transformation dependency, not just the pool:** bundle revision, declaration,
`as_of`, scorer identity, taxonomy, equivalence table, and persona registry are resolved **once** into
`ProjectionRunContext`. `posting_context` **accepts the run's taxonomy** rather than loading one — a
signature change, and the reason `resolve_projection_run` owns extraction preflight. `run_tailor` either
consumes the same snapshot or compares its own resolved dependencies against the recorded versions and
refuses before parsing or rendering; which of those two is an implementation choice, but doing neither is
not.

**Hoisting the pool is safe under current code**, verified: `select` only reads the pool and `_subset_resume`
copies (`select.py:119,174`). It is still a stated invariant (§5) rather than an inherited accident, because
nothing today prevents a future `select` from mutating.

**`as_of` needs a declared clock.** It is not metadata — it feeds every entry build and effective-fact
resolution (`pool.py:201,309`), so it decides which facts are effective. It is fixed once at run start from
the same UTC clock the `runs` row uses (`utcnow()`, as `runner.py` already does), and recorded in the
manifest. One run, one `as_of`, one bundle revision.

### 4.2 Per-lead Stage 2

For each lead: `project_for_posting` selects against that posting's JD skills, writes
`resume.projected.yaml` and `projection-manifest.json` into the lead's existing destination directory, and
the pipeline calls `run_tailor(resume_path=<the projected document>)`. The projected document is *"exactly
the shape `tailor/load.py` reads"*, so `load_resume` is untouched.

**Compile cost, corrected and budgeted.** Revision 1 said ~8 compiles per lead. The real worst case is
**~10**: one pinned-prefix compile plus one per candidate attempt (`select.py:148,189`) plus `run_tailor`'s
own render — and `run_tailor` may add an untailored-fallback compile. At eight candidates and ten leads
that is ~100 serial tectonic invocations. `_grow` can stop early, so this is an upper bound, not a
forecast.

**A pre-merge benchmark is owed, not a post-hoc measurement.** Revision 1 deferred measuring until the
first real projected run, which is too late to define unattended operability: a serial 100-compile stage
can be operationally broken while every correctness test passes. Before merge, record wall time and the
compile-count distribution over ten representative postings at the live candidate count in `METRICS.md`,
and declare a maximum acceptable stage duration. Caching comes after measurement if at all — the pool is
JD-blind and the pinned prefix is identical across leads, which is where a cache would go.

### 4.3 Content-bound lineage

Revision 1 proposed comparing the manifest's `bundle_digest`/`projection_digest` against what the stage
resolved. **That check is tautological** — the manifest is constructed from the same pool it would be
compared against, so it proves two assignments in one function agree. It detects nothing.

The lineage contract carries, and the pipeline validates:

| Field | Why it must be there |
|---|---|
| `manifest_schema`, checked against an exact supported set | an unrecognised version is a failure, never a shrug |
| `bundle_revision`, `bundle_digest`, `projection_digest` | which bundle and declaration produced this |
| `posting_id` **and `posting_version_id`** | `PostingContext` has it (`posting.py:38`) and `ProjectionManifest` omits it, while `run_tailor` independently re-reads the current version (`tailor.py:389`) — so selection can run against version A and tailoring against version B, undetected |
| `selected_entry_ids`, `jd_skills` | which selection this was |
| **`resume_sha256`** — the hash of the exact projected bytes | the only field that binds the manifest to the *document*; without it manifest B pairs with résumé A undetected, and a `shell_source` edit changes the projected résumé while no existing digest moves |
| **`as_of`** | promised by §4.1 and absent from revision 2's contract; it decides which facts are effective, so it is part of the transformation, not metadata |
| **`scorer_id`, `taxonomy_version`, `equivalence_version`, `persona_registry_version`** | transformation identity (§4.1). Without these the artifact records *which bundle* produced it but not *which rules*, and two runs that disagree are indistinguishable |

Validation happens against **the file actually handed to `run_tailor`**, and a posting-version change
between selection and tailoring refuses that lead.

**The hash must cover the bytes that were parsed, not a path read twice.** `load_resume` re-reads the path
(`tailor.py:410`), so hashing the file and then parsing it separately leaves a read/swap/read window in
which the validated bytes are not the rendered bytes. Note also that the existing master identity hashes the
**parsed model** — `master_hash = _sha(master.model_dump_json())` (`tailor.py:482`) — not raw input, so a raw
byte hash is a second, differently-shaped identity. The contract is therefore: **read once, hash and parse
the same buffer**, and carry the parsed-model hash alongside `resume_sha256` so the byte identity and the
model identity are both pinned. A check that can be defeated by a concurrent writer is not a check.

**Husks.** Projection writes both sidecars *before* `run_tailor` runs, so a per-lead projection or lineage
refusal leaves a non-empty lead directory. The runner's cleanup only removes an **empty** directory
(`_remove_if_empty` calls `rmdir()`, `runner.py:873`), and `tests/pipeline/test_pipeline_run.py:250` pins
that a failed lead leaves no directory behind. So a refusing lead must either write its sidecars to a
scratch location and move them into place only on success, or clean up its own partial output — otherwise
this slice breaks an existing regression.

`resume_sha256` is what lets §7 keep the `shell_source` digest gap out of scope honestly: the gap remains
an *approval* hole — a shell edit still needs no re-approval — but it is no longer a *detection* hole,
because the projected bytes are hashed and recorded whatever the shell said.

**`run_tailor` needs a contract change, and revision 1 denied it.** It constructs `meta` and inserts the
artifact internally (`tailor.py:721,746`) and its signature has no lineage parameter (`tailor.py:452`).
Lineage cannot be "copied in afterwards" without mutating a written row or creating a second artifact
writer. So `run_tailor` gains **one narrow optional typed source-lineage argument, whose type is defined
outside `projection`** to keep the import wall intact. It writes lineage into the `resume_tailored` row in
the **same transaction** as the artifact insert, and validates the supplied résumé hash. Not on
`resume_master`: that node is content-addressed and reused, and its metadata is written only on first
creation.

### 4.4 Two outcome catalogs, total over the typed arms

Revision 1 had one four-member catalog. It was neither complete nor implementable: a genuinely absent
declaration and an unreadable one share `DECLARATION_UNREADABLE` (`declaration.py:134,150`), so a
routine/fault split over them would require matching an exception *message* — which this repo forbids.

**Two catalogs, because the units differ** (revision 1 conflated a once-per-run refusal with a per-lead
outcome and the counts could never reconcile):

1. **Run-scoped availability**, decided once in the preflight: `available`, `missing_approval`,
   `stale_approval`, `declaration_missing`, `declaration_unreadable`, `bundle_unreadable`,
   `persona_invalid`, `scorer_invalid`, **`taxonomy_invalid`**, **`equivalences_invalid`**,
   **`template_invalid`**, **`toolchain_unavailable`**, **`pinned_budget_overflow`**, and
   **`declaration_invalid`** (the fidelity-contract arms). Anything other than `available` refuses the run
   before any disposition is written (A2) and sets `summary.fatal`.
2. **Per-lead outcome**, only reachable when availability is `available`: `projected`,
   `posting_unavailable`, **`extraction_unavailable`**, `lineage_mismatch`, `output_io_failure`.

**Six things moved out of the per-lead catalog, because they are run-invariant.** The template, the renderer
and the tectonic toolchain are shared; the pinned set and its budget are identical for every posting; and
`page_budget` is the same profile value each time (`posting.py:80`). Revision 2 listed them per-lead, which
would retry a missing renderer once per lead and — because dispositions are recorded at `runner.py:606`
before the all-failed fatal check at `:624` — could grant `seen` to leads that failed for a run-wide reason.
The current runner already treats template and tool failures as systemic (`runner.py:530`); preflight is
where they belong.

**`no_jd_skills` is renamed `extraction_unavailable`, and the distinction is load-bearing.** `jd_skills_for`
returns `None` for *missing* extraction and a valid *empty set* separately (`tailor.py:346`), and `select`
deliberately routes an empty/zero-scoring set to the curated no-match fallback (`select.py:204`). Collapsing
the two would turn a legitimate fallback into a failure and silently drop leads projection handles fine.
Only `None` is an outcome; an empty set continues into selection.

**A new typed `DECLARATION_MISSING`** issue is required so absence is distinguishable from unreadability at
the raise site — verified cheap: the missing-file branch already exists distinctly at `declaration.py:130`
and only its issue member changes. No message matching anywhere.

**The mapping is written out, not asserted.** There are **32** `ProjectionIssue` members today (counted, not
recalled), and revision 2 named a "total mapping" without supplying one — which round 2 correctly ruled
unreviewable, since "unmapped ⇒ fatal" cannot be checked against a table that does not exist. The build
therefore ships an **explicit exhaustive mapping table**, in code, covering:

- all 32 `ProjectionIssue` members;
- `ProfileBundleError`, `PersonaError`, `TemplateArtifactError`;
- **`TaxonomyError`** (`extract/taxonomy.py`) and **`EquivalenceError`** (`tailor/equivalences.py`), which
  revision 2 named nowhere even though `resolve_projection_run` loads both;
- I/O arms.

A test enumerates `ProjectionIssue` **from the enum itself** and fails if any member is unmapped, so a new
issue added later cannot silently land in a default bucket. An unmapped outcome is fatal, never a catch-all.

Per-lead counts are **attempted leads**, stated explicitly so the funnel's balance is checkable.

### 4.5 The funnel gets a real stage, not counters bolted on

Revision 2 named `PipelineSummary` (`runner.py:94`), `_emit_funnel` (`runner.py:741`) and the writer
(`funnel_writer.py:82`) and called that a data path. Round 2 ruled it NOT CLOSED, correctly: the funnel is a
**closed, balanced stage model**, and the existing `tailor` stage balances

```
shortlisted = tailored + tailor_failed + withheld_not_live
```

(`run_funnel.py:787`). Two leads lost to projection would therefore either **break reconciliation** — the
P0 gate's own 100%-reconciliation clause — or get folded into `tailor_failed`, which destroys the new
catalog's meaning and hides projection loss behind an existing bucket. Either outcome is worse than no
counters.

**So projection becomes its own stage between `liveness` and `tailor`:**

```
served_after_liveness = projected + Σ(per-lead projection drops)
tailor stage now ENTERS at `projected`, not at `shortlisted`
```

Both balances are asserted, and the projection stage carries an **independent recount from the store** —
`resume_tailored` rows carrying projection lineage — rather than trusting the summary that produced it. That
is the repo's own rule that a component's self-report is not verification, and it is what makes this stage
able to genuinely fail rather than merely report.

**Artifact version.** `ARTIFACT_VERSION` convention is explicit that "every bump so far has signalled a new
top-level SECTION", with D-113 the precedent for *declining* a bump on a key added inside an existing block
(`run_funnel.py:58-64`). A `projection` stage is a new top-level section, so it **bumps the version**. That
is a deliberate, recorded decision, not an incidental one.

**The bump is GLOBAL, and revision 3 contradicted itself about it — ruled by Mit, 2026-08-17.** The bump
and a literal reading of "byte-identical no-flag output" cannot both hold: a run without `--project` emits
a funnel whose `artifact_version` reads **5** where it read **4**, so the JSON is not byte-identical. The
ruling keeps the global bump and narrows the claim. One emitter with one schema version is right —
versioning per run type would force every consumer to handle both, for a field whose whole job is to tell a
consumer which shape it is reading. The over-claim was "byte-identical", which was always about
*behaviour*: **no projection stage, no lineage keys, unchanged lead outcomes and unchanged dispositions**.
It should never have extended to the artifact's own schema-version field. So: `artifact_version` advances
to 5 for **every** run, including authored ones, and the unchanged-behaviour guarantee covers stages,
lineage, outcomes and dispositions — not that field.

**When `--project` is absent, the projection stage is omitted entirely** — not emitted as zeros. A stage
reporting `0` would claim projection ran and dropped nothing; omission says it never ran, which is the same
distinction P0 item 1 already draws with `not instrumented` versus `0` (D-023).

## 5. Invariants

1. No non-TTY approval path, ever (§3).
2. **One configuration snapshot per run** — one bundle revision, one `as_of`, one taxonomy, one equivalence
   table, one persona registry, one scorer — asserted by **call count**, not by comparing two returned pools
   (§4.1).
3. `--project` unavailable ⇒ set `summary.fatal`, refuse before any lead earns a disposition, exit 1 (A2).
4. Without `--project`, **behaviour** is unchanged — no `projection` funnel stage is emitted, no lineage
   keys are written, and lead outcomes and dispositions are what they were. **Not** the funnel's
   `artifact_version`, which advances to 5 for every run including authored ones (§4.5).
5. One implementation of pool assembly and of selection, shared by CLI and pipeline (§4.1).
6. One artifact writer. Lineage goes in the artifact's own transaction (§4.3).
7. Hash the buffer that is parsed, never a path read twice (§4.3).
8. A refusing lead leaves no directory behind (§4.3).
9. Every funnel stage balances, and the projection stage is recounted from the store (§4.5).

## 6. Testing

Per parent §9: each test confirmed to fail without its fix and naming *which* assertion trips (D-148), and
expectations derived from the bundle at run time rather than hardcoded (D-142/D-149).

**The test revision 1 was missing, and the reason it needed review.** The defect class that passed every
test revision 1 listed: *a fallback renders static résumés, records them permanently `built`, and prevents
those leads re-entering after the stamp is repaired.* Every listed assertion still passed. So:

- **Ledger visibility across runs is the headline test.** With `--project` and a stale stamp: the run
  refuses, **no disposition row is written**, and a second run — after the stamp is made current — projects
  those same postings. This asserts the drain structurally. It asserts **five things together**, because
  round 2 showed four of them can pass while the fifth is broken: exit code 1, `runs.status = failed`, a
  FATAL line in the funnel, zero disposition rows, and retry visibility on the next run.
- **Mixed configuration is refused.** A taxonomy edited between lead 1 and lead 2 must not produce two leads
  scored under different rules — either the run context is genuinely reused or the run refuses. Round 2's
  scenario: `resume_sha256` and `posting_version_id` both pass while selection and tailoring disagree, so
  this test cannot be written against those two fields alone.
- **The hash covers what was parsed.** A file swapped between hashing and parsing is caught, or the design's
  read-once contract is violated.
- **A refusing lead leaves no husk** — asserted against the existing regression
  (`tests/pipeline/test_pipeline_run.py:250`) unedited.
- **Every funnel balance holds**, including the new `served_after_liveness = projected + drops` identity, and
  the projection stage's store recount disagreeing with the summary is a failure.
- **Without `--project` no projection stage is emitted** — absent, not zeroed.
- **Enum totality:** a test enumerates `ProjectionIssue` from the enum and fails on any unmapped member.
- **Posting-version drift:** a posting version changing between selection and tailoring refuses that lead.
  Revision 1's digest check passed this case.
- **Lineage is real, not a label:** a manifest whose `resume_sha256` disagrees with the file handed to
  `run_tailor` refuses; an artifact row for a projected lead names its bundle revision and posting version.
- **Every availability member and every per-lead member** gets a case; an unmapped exception is fatal.
- **`DECLARATION_MISSING` vs `DECLARATION_UNREADABLE`** are distinguished without inspecting any message.
- **One pool per run:** a promotion simulated between two leads does not change the second lead's pool, and
  `project_pool` is called exactly once.
- **The extraction is a no-op for the CLI.** `resume project`'s existing tests pass **unedited** — including
  the stale-approval case (`tests/projection/test_projection_cli_resume_project.py:443`) and the
  `TemplateArtifactError` case (`:521`) — and its exit codes and stdout are unchanged.
- **Negative control:** without `--project`, unchanged behaviour — no projection stage, no lineage keys,
  the same lead outcomes and dispositions — asserted against the existing pipeline suite unedited. The
  funnel's `artifact_version` is excluded from the claim (§4.5).

Gate: `make check` in plain mode, exit code captured, never piped.

## 7. Out of scope, deliberately

- **Flipping the unattended default** — P5b (§8).
- **Manual `tailor run` manifest validation** (parent §12 Q2) — parent §4.2 scoped it away from `tailor` on
  purpose. Still open, and no longer claimed here.
- **The `shell_source` approval gap.** `projection.yaml` declares `shell_source: resume.yaml`, whose content
  no digest covers (`shell.py:18-24`), so editing it changes the projected document with no re-approval.
  §4.3's `resume_sha256` closes the *detection* half; the *approval* half belongs to parent §12 Q5's
  renderer-ownership work.
- **Parent §12 Q3**, persona `entries` vs Stage 2 — guarded by the existing typed preflight, not resolved;
  parent §10 puts it before P6.
- **P1 item 5's dead last rung.** The untailored fallback is the full 6,134-char master against
  `resume_max_pages=1`, so it cannot ship for this profile. Pre-existing and orthogonal — and no longer
  load-bearing for any argument here, since A2 no longer relies on the fallback chain.
- The model re-ranker (parent slice P6), and any LLM lane in `pipeline/runner.py` (parent §11).

## 8. Gate

**P5a — this slice:**

| Clause | How it is met |
|---|---|
| Projection runs inside `boardwatch run --project` | projected leads on a real run over live postings |
| Stale lineage is **detected**, not merely inspectable | document identity (`resume_sha256`, parsed-model hash, `posting_version_id`) **and** transformation identity (`as_of`, scorer, taxonomy, equivalence, persona versions) validated against the file handed to `run_tailor` |
| Projection unavailability consumes no leads **and cannot report success** | the five-part cross-run test (§6): exit 1, `status=failed`, funnel FATAL, zero dispositions, retry visible |
| The funnel still reconciles | new stage balances asserted, plus an independent store recount |
| Every typed failure is classified | enum-totality test over all 32 `ProjectionIssue` members plus the foreign exception families |
| Compile cost is known before merge | wall time + compile distribution over ten postings in `METRICS.md`, with a declared maximum stage duration |

**P5b — not this slice, owner-gated:** `resume.yaml` stops being the daily default. Its criteria are
undecided and must be named by Mit, not inferred here: how many clean projected runs, over how many
distinct postings, with what defect budget. Also open for P5b, and deliberately not answered now:

- what `--project` combined with an explicit `--resume custom.yaml` means (today they would conflict);
- whether `--bundle`, `--declaration` and `--scorer` overrides are exposed on `run` as they are on
  `resume project`;
- **multi-tenancy:** whether a non-owner can point `--project` at their own bundle and declaration without
  adopting this repo owner's filesystem layout.

Parent P5 is **not** met by P5a alone.

## 9. Review dispositions

### Round 2 (revision 2 → 3)

Round 2 audited the above dispositions — **6 CLOSED, 2 RELOCATED, 2 NOT CLOSED** — and reviewed revision 2's
new material with 14 fresh premises, **9 FALSE**. Verdict **REWORK**.

| Finding | Disposition in revision 3 |
|---|---|
| **BLOCKING** — a fail-closed refusal can still be recorded as a successful empty run: revision 2 said "refuses" but never named the run-state transition, so `status=ok` and exit 0 while producing nothing | **Fixed** — every unavailability outcome sets a typed `summary.fatal`, exits 1, and is added to `RUN_CONTRACT.md` as a fifth fatal class; placement pinned after scan handling and before ranking; the five-part test (§2, §6) |
| **BLOCKING** — the "frozen" context permits mixed configuration and undetectably stale *transformation* lineage | **Fixed** — the freeze covers taxonomy, equivalences, persona, scorer and `as_of`; `posting_context` accepts the run's taxonomy; `run_tailor` consumes or compares (§4.1), and all of it enters lineage (§4.3) |
| **BLOCKING** — the "total catalog" was neither total nor correctly partitioned | **Fixed** — an explicit exhaustive mapping table in code with an enum-totality test; `TaxonomyError`/`EquivalenceError` added; six run-invariant causes hoisted to preflight; `no_jd_skills` → `extraction_unavailable` with the `None`-vs-empty distinction preserved (§4.4) |
| **BLOCKING** — the funnel design would either fail reconciliation or hide projection loss | **Fixed** — a real `projection` stage between liveness and tailor, both balances asserted, an independent store recount, an artifact-version bump, and omission rather than zeros when the flag is absent (§4.5) |
| **MAJOR** — the byte-hash check has a second-read race, and failed paths leave partial artifacts | **Fixed** — read once, hash and parse one buffer, carry the parsed-model hash too; refusing leads leave no directory, asserted against the existing regression (§4.3) |
| **MAJOR** — P5a's gate is measurable but not sufficient | **Fixed** — gate widened to six clauses (§8) |
| **MINOR** — `as_of` promised in §4.1 but absent from the lineage contract | **Fixed** — in the §4.3 table |
| Audit: disposition 4 **NOT CLOSED** (mapping asserted, not supplied) | **Fixed** — see the catalog row above; the table is now a build deliverable, not a claim |
| Audit: P20 **NOT CLOSED** (naming three objects is not a data-path design) | **Fixed** — §4.5 designs the stage, its balances and its version consequence |
| Audit: disposition 6 — the lineage type must live in a *genuinely neutral* module, not merely "outside `projection`", to preserve the **transitive** import wall (`tests/profile_bundle/test_profile_bundle_tailor_isolation.py:107`) | **Accepted** — stated as a constraint on the type's home |

**Round 2's correction of my own pushback, accepted.** It ruled the partial rejection below "legitimate as a
scope ruling, but not as a technical defense": parent §4.2 does assign pipeline-side validation to P5 while
§12 Q2 separately asks about manual `tailor run`, so this slice need not close the manual path — **but** the
quoted rationale that P5 "requires no change to `tailor`" is now **obsolete**, because revision 2 itself
accepts a `run_tailor` change. The scope conclusion stands; the supporting quote does not, and is withdrawn.

### Round 1 (revision 1 → 2)

`gpt-5.6-sol`, medium effort, read-only, deriving its own 22 premises: **REWORK**, 9 premises FALSE.

| # | Finding | Disposition |
|---|---|---|
| 1 | **BLOCKING** — fallback permanently consumes leads via `built`; the claimed drain is not a drain | **Fixed** — A2 inverted to fail-closed preflight (§2); cross-run ledger test added (§6) |
| 2 | **BLOCKING** — "one pool per run" and the proposed extraction are mutually incompatible; body not self-contained | **Fixed** — two APIs, extraction widened to `:393`/`:414`, call-count assertion (§4.1, and §5 item 2) |
| 3 | **BLOCKING** — the manifest check is tautological; no content or posting-version binding | **Fixed** — `resume_sha256` + `posting_version_id` + schema check, validated against the handed file (§4.3) |
| 4 | **BLOCKING** — outcome catalog incomplete and unimplementable from typed exceptions | **Fixed** — two catalogs by unit, total mapping, new typed `DECLARATION_MISSING`, unmapped ⇒ fatal (§4.4) |
| 5 | **BLOCKING** — A2's "fallback is real" is false on empty/zero-coverage JDs | **Fixed** — argument withdrawn and the mechanism documented (§2); A2 no longer depends on it |
| 6 | **MAJOR** — artifact lineage requires a `run_tailor` contract change | **Accepted** — one narrow typed optional argument, type defined outside `projection`, same transaction, `resume_tailored` only (§4.3) |
| 7 | **MAJOR** — compile cost understated and accepted before measurement | **Fixed** — ~10/lead and ~100/run; pre-merge benchmark with a declared budget (§4.2) |
| 8 | **MAJOR** — this is not a complete P5 gate; several contracts unsettled | **Accepted** — retitled P5a, P5b split with its open contracts named (§1, §8) |
| — | Premise 6: "the gate cannot be satisfied unattended" overclaims | **Fixed** — it cannot be *repaired* unattended (§3) |
| — | Premise 20: "nothing outside `runner.py` changes shape" | **Fixed** — funnel/summary data path named (§4.4) |


**Partially rejected, with reasoning.** Finding 3 also faults the design for leaving manual `tailor run`
unable to validate an adjacent manifest. Parent §4.2 scoped that away from `tailor` deliberately —
*"requires no change to `tailor` and does not cross the wall, which is why forcing it into v1 through
`tailor` would have been the wrong shape."* The genuine error was revision 1 claiming to own parent §12 Q2,
which is literally a question about `tailor run`. The claim is withdrawn (§1) and Q2 stays open (§7); the
pipeline-side lineage is what this slice owns and §4.3 now closes it properly.
