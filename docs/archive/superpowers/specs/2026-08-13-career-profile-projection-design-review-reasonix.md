# External design review — career-profile projection

Reviewer: Reasonix (adversarial design review, read-only)
Document reviewed: `docs/superpowers/specs/2026-08-13-career-profile-projection-design.md` (committed as `ce1efde`)
Environment: all probes via `uv run` / direct file reads; no tracked file modified. Narrow tests only; `make check` not run.

---

## §7.0 — Premise verification: the seven claims in the design's §2

Each claim was checked against the code on 2026-08-13, not inferred.

1. **"No operation `build_plan` can emit adds, removes, or reorders an *entry*" — PASS.**
   `src/boardwatch/tailor/plan.py:15-40` defines exactly five ops: `Select(bullet_id)`, `Reorder(entry_id, order: tuple[str,...])`, `Delete(bullet_id)`, `EquivalenceSwap(bullet_id)`, `Rewrite(bullet_id)`. `Reorder` names an entry but only to reorder bullets *inside* it (`plan.py:88` passes `tuple(b.bullet_id ...)`). `build_plan` itself emits only `Reorder`/`Delete`/`EquivalenceSwap` (`plan.py:87-103`). No op adds, removes, or reorders an entry. The design's parenthetical "The only op naming an entry is `Reorder(entry_id)`, which reorders bullets *inside* that entry" is exactly right.

2. **"Both bundled personas ship `entries: null`" — PASS.**
   `src/boardwatch/tailor/personas.yaml:31` (`general_swe`, `entries: null`) and `:37` (`ios`, `entries: null`). The documented semantics (`personas.yaml:19-21`) and the implementation (`persona.py:189-190`: `entries is None → entries = list(master.entries)`) both hold. Note the mechanism *can* pin entries (`persona.py:192-199`), which is what makes the design's open question 2 (§12) real.

3. **"Nothing manages a page or length budget; `MAX_BULLETS_PER_ENTRY = 6` is per-entry" — PASS, with the limits the design itself names.**
   `plan.py:48` and `plan.py:87-90`: the cap is applied per entry, emitting `Delete` for bullets beyond 6 — no global budget. The layout gate is terminal: `reports/resume_gate.py:148` (`BULLET_MAX_LENGTH = 220`), `:115-131` (`evaluate_compile` returns a pass/fail `GateResult` on `page_count > max_pages`), and its only remedy in `reports/tailor.py:578-604` is the untailored-master fallback. Nothing iterates content toward a budget.

4. **"`tech_tags` is inert — nothing reads it" — PASS.**
   `grep -rn "tech_tags" src/` finds only: the model definition (`tailor/model.py:16`), docstring examples (`tailor/load.py:113,116`), the bundle's own resume-import schema (`profile_bundle/enumerators.py:403`, a *different* package's type), and the comment `reports/tailor.py:430`: "the render drops bullet_id/entry_id/tech_tags". No production reader anywhere.

5. **"The renderer has no `SUMMARY` marker handler" — PASS.**
   `tailor/render/latex.py:54-55`: `SUMMARY` is in `_ALLOWED_MARKERS`, but `emit()` (`latex.py:224-241`) has handlers only for `%%TITLE_START%%`/`%%TITLE_END%%` (consumed) and `%%SECTIONS_START%%` (injection). No branch touches `SUMMARY_START`/`SUMMARY_END`; the template slot is empty (`tailor/render/templates/resume_base.tex:82-84`), so summary prose is whatever the template carries — static. Confirmed by `grep -rn "SUMMARY" src/boardwatch/`: the only renderer hits are the two catalog lines above.

6. **"`profile_bundle` and `tailor` do not import each other, in either direction" — PASS, held by a real test.**
   `grep -rn "boardwatch.tailor" src/boardwatch/profile_bundle/` and `grep -rn "profile_bundle" src/boardwatch/tailor/` both return zero production hits (the one hit is the `__init__.py` docstring). The test exists and is stronger than a grep: `tests/profile_bundle/test_profile_bundle_tailor_isolation.py` asserts the boundary three ways — the résumé path, a transitive import-graph closure over the live tree (`:107-132`), and a text-level guard for dynamic imports (`:135-144`) — with parameterized positive controls so the detector provably fires (`:164-188`). Ran it:
   `uv run pytest tests/profile_bundle/test_profile_bundle_tailor_isolation.py -q -p no:cacheprovider --no-cov` → `21 passed in 18.24s`.

7. **"`taxonomy.extract` and the equivalence table can be applied at entry level" — PASS.**
   `extract/taxonomy.py:47-48`: `extract(self, text: str) -> set[str]` is a pure function over text. `tailor/equivalences.py:57-64`: `as_pairs()`/`images()` are pure. `plan.py:76-78` already applies exactly the design's per-entry formula (union of `extract(b.text)` plus JD-applicable swap targets) per bullet; lifting it to an entry is the same computation over the entry's bullet texts. Verified by running it (`uv run python`): negative control `extract("wrote documentation and led team meetings") == set()`, positive control `extract("wrote python services on postgres") == {'PostgreSQL','Python'}`.

**All seven premises hold.** The design's §2 is not the problem — the problems are in what the design then *builds* on it.

---

## Findings, most severe first

### Finding 1 — BLOCKING

- **Severity:** BLOCKING
- **Where:** §4.1 (the example `projection.yaml` header, lines 117-119), §5 "Composition rule" (lines 191-195), §7 fidelity table (lines 264-280). Pattern: §7.1-1/§7.1-2 (a stated mechanism that cannot express the design's own example).
- **Defect:** The design's own header template — `{person.email} | {person.phone} | {person.profile_url}` — cannot be resolved by the composition rule the design specifies, and contact resolution is absent from the fidelity contract entirely.
- **Why it matters:** The bundle models contact channels as `ContactRecord`s, not facts: `profile_bundle/models/entities.py:238` (`contact_id, person_id, channel_type, value, allowed_surfaces`), and the synthetic bundle the design is tested against carries exactly that shape (`examples/comprehensive/facts/identity.yaml`): `contact.example.email`, `contact.example.profile`, `contact.example.location`, `contact.example.phone` — channels, with no `person.email`-style predicate anywhere (the only `person.*` facts are `person.professional_name` and `person.professional_headline`). The design's rule is "Every `{predicate}` resolves against `(subject_id = entity_id, predicate)`" (§5, line 192) and "Templates substitute fact values only" (line 191). Under that rule, all three header placeholders are unresolvable → and unresolved placeholders are **fatal** (§5 line 192). So the design's flagship example, projected against the very synthetic bundle the design is built and tested against, always fails. Worse, the surface gate it leans on never fires for contacts: the synthetic bundle's phone contact is `allowed_surfaces: [application]` (`identity.yaml`), so *if* an implementer naively special-cases contacts to make the example work, the phone would leak an application-only surface onto the résumé — precisely the leak the bundle's `allowed_surfaces` machinery exists to prevent. Either the example is wrong or the mechanism is underspecified; there is no reading under which it works as written.
- **Evidence:**
  - `src/boardwatch/profile_bundle/models/entities.py:238` — `ContactRecord` fields.
  - `src/boardwatch/profile_bundle/examples/comprehensive/facts/identity.yaml` — `contacts:` list; `contact.example.phone` has `allowed_surfaces: [application]`.
  - Design lines 117-119 (`header:` with `{person.email}`/`{person.phone}`/`{person.profile_url}`) vs. lines 191-195 (facts-only resolution).
  - Design §7 table (lines 264-280): rows for predicates, surfaces, claim status, conflict groups, id existence, byte-equality, id derivation — **no row for contacts**.
- **Suggested direction:** Add a contacts row to the fidelity contract: contact placeholders resolve against `(person_id, channel_type)` with `allowed_surfaces` enforced exactly like facts, and the fatal table gains "every referenced contact carries `resume` in `allowed_surfaces`". Change the §4.1 example to the mechanism that actually exists (or mark the header example with the corrected placeholder grammar).

### Finding 2 — BLOCKING

- **Severity:** BLOCKING
- **Where:** §6 step 4 (lines 232-233) and §8. Pattern: §7.1-8 (silent success) — an unspecified arm that this project's gates cannot catch, on a failure that is documented to exist in the field.
- **Defect:** The budget loop specifies only the "page count exceeds the budget" arm of `evaluate_compile`. The gate has four outcomes, and the design says nothing about the other three.
- **Why it matters:** `evaluate_compile` returns `GateReason.BINARY_MISSING` / `COMPILE_FAILED` / `PAGE_LIMIT_EXCEEDED` / `OK` (`reports/resume_gate.py:115-131`). Only the last two carry a page count. On a machine without `pdfinfo` — a documented live state in this project ("`pdfinfo` is a hard dependency wearing a soft failure … returns `None` at `reports/tailor.py:170-171` and is laundered into `COMPILE_FAILED`", STATE.md carried-gaps table) — *every* compile during budget fit returns `COMPILE_FAILED`. A literal implementation of step 4 ("compile; if the page count exceeds the budget, drop … and recompile") that reads "not shippable" as "over budget" will then drop every candidate, one compile at a time, and finally report the **typed failure naming the pinned set as a content problem** — the true cause (missing `pdfinfo`) is never named. That is the exact silent-misdiagnosis class this codebase has already shipped twice (D-138, D-141), and no gate the project has today would catch it: the design's own §9 test list has no budget-loop test for infrastructure failure.
- **Evidence:**
  - `src/boardwatch/reports/resume_gate.py:117-131` — the four-armed `GateResult`.
  - `src/boardwatch/reports/tailor.py:167-171` — `_pdf_page_count` returns `None` when `pdfinfo` is absent, and `:197-200` launders `page_count is None` into `CompileOutcome(CompileReason.COMPILE_FAILED)`.
  - Design lines 232-233 (step 4 names only the page-count arm); §9 (no corresponding test).
  - Project's own fail-safe rule: "systemic outage ⇒ fatal".
- **Suggested direction:** One sentence in step 4: only `PAGE_LIMIT_EXCEEDED` drops a candidate; `BINARY_MISSING` and `COMPILE_FAILED` during budget fit are fatal, named (not reported as a content overflow). Add the matching test: budget fit with a stubbed `CompileRunner` returning `COMPILE_FAILED` must fail named, never drop a candidate.

### Finding 3 — BLOCKING

- **Severity:** BLOCKING
- **Where:** §3 CLI (lines 98-101), §10 delivery (lines 322-328), §11 (line 341). Pattern: §7.2-10 — a missing stage nobody specified.
- **Defect:** No slice wires deterministic projection into `boardwatch run`. The unattended daily flow keeps reading the static `{config_dir}/resume.yaml`, so the system the owner built "so it feels like it's alive — constantly adjusting to the JD" never adjusts in the flow he actually runs.
- **Why it matters:** `cli/run_cmd.py:80` resolves the pipeline's résumé to `resume_path or settings.config_dir / "resume.yaml"` and `pipeline/runner.py:526` passes that path into `run_tailor` per lead. §10's delivery table contains P1 (schema), P2 (stage 1), P3 (CLI), P4 (stage 2), P5 (model re-ranker) — and no pipeline slice. §11 excludes only "wiring *any model lane* into `pipeline/runner.py`", so the deterministic path is neither planned nor excluded; the design's own "two commands, deliberately" paragraph (lines 98-101) addresses only why `tailor` must not learn about the bundle — it does not answer how the per-posting projection ever gets invoked without the owner hand-running two commands per lead. The owner's stated intent (packet §5) is the yardstick, and against it, a mechanism the daily pipeline never calls delivers nothing daily. No gate can catch an unmet intent.
- **Evidence:**
  - `src/boardwatch/cli/run_cmd.py:55-56,80` — `--resume` default `{config_dir}/resume.yaml`; pipeline passes it verbatim.
  - `src/boardwatch/pipeline/runner.py:349,526` — `resume_path` flows to `run_tailor` unchanged.
  - Design §10 lines 322-328 (delivery slices) and §11 line 341 (only the model lane is out of scope).
- **Suggested direction:** Either add a delivery slice (e.g., `boardwatch run --project` that runs stage 1+2 per lead before `run_tailor`, opt-in, with a pinned failure mode), or record an explicit owner ruling that v1 is manual-only and the daily pipeline stays on `resume.yaml`. As written it is a hole, not a decision.

### Finding 4 — SHOULD-FIX

- **Severity:** SHOULD-FIX
- **Where:** §6 "Scoring" (lines 217-220). Pattern: §7.2-1 (scoring bias) — verified, not hypothetical.
- **Defect:** `score(entry) = |skills(entry) ∩ jd_skills|` is an unnormalized count of *distinct* matched skill names. It rewards entry breadth — more bullets and wordier bullets touching more distinct taxonomy names — independent of how deeply (or whether) the entry is about the JD.
- **Why it matters:** Run against the bundled taxonomy and a data-platform JD skill set `{'Airflow','ETL/ELT','Python','Snowflake'}`, with the design's own formula:
  - a focused, deeply relevant entry — `"Built Airflow DAGs, scheduled backfills, and tuned ETL jobs end to end"` (1 bullet) → `skills=['Airflow','ETL/ELT']`, **score = 2**;
  - an irrelevant breadth entry (4 bullets: *"Learned Python basics in a bootcamp." / "Attended a Snowflake vendor talk." / "Ran one Airflow job during an internship." / "Wrote an ETL script for a class."*) → `skills=['Airflow','ETL/ELT','Python','Snowflake']`, **score = 4**.
  The irrelevant entry wins 4 > 2, because four shallow mentions touch four distinct names while the deep entry can only ever touch two. The design claims entry scoring "inherits the behaviour" of bullet scoring — that is the subtle error: per-bullet `|∩|` in `build_plan` (`plan.py:76-78`) has no cross-bullet bias because it ranks bullets independently; lifting it to entry level *introduces* a size bias that does not exist at bullet level. For the owner's real pool (entries of 2-6 bullets each), this systematically prefers the entry that name-drops the most JD keywords — the opposite of "actively decide which projects would be good to showcase."
- **Evidence:**
  - Design lines 217-219 (the formula), 222-223 (the "inherits its behaviour" claim).
  - Probe command and output (negative control included — `extract("") == set()` and a plain-English sentence also produced `set()`; positive control `extract("wrote python services on postgres") == {'PostgreSQL','Python'}`):
    ```
    uv run python /tmp/projection_probe2.py
    deep-1-bullet:    skills=['Airflow', 'ETL/ELT'] score=2
    broad-4-bullets:  skills=['Airflow', 'ETL/ELT', 'Python', 'Snowflake'] score=4
    ```
- **Suggested direction:** Normalize: `|∩| / |skills(entry)|` (precision) or average per-bullet coverage, with the tie-break by declared order kept. Cost: selection outcomes change, so the §9 JD-matrix tests need owner-reviewed expected outcomes rather than "selects differently" before the change lands.

### Finding 5 — SHOULD-FIX

- **Severity:** SHOULD-FIX
- **Where:** §5 lines 201-204 and §9 line 315. Pattern: §7.1-2 — a guarantee that lands nowhere in the mechanism.
- **Defect:** The template-smuggling risk is "accepted and named" with a mitigation that is pure prose: "§9 requires the projected document be reviewed before first use." Nothing enforces that a review happened, ever, for any template revision.
- **Why it matters:** The design's own example demonstrates the hole is live, not theoretical: `{education.result}/10` (line 123) against the synthetic bundle's `fact.example-university.result.001`, `value: '3.85'` — a 4.0-scale GPA (`examples/comprehensive/facts/education.yaml`) — renders "3.85/10", an unearned scale assertion introduced by a template literal exactly the way `"Senior {employment.title}"` would be. Because projection output becomes Tier A's ground truth (design §8.1), a smuggled claim is unverifiable by every downstream gate — that is the design's own argument for fatal-everywhere, and it applies to this hole too. A "review before first use" that no mechanism records is §7.1-2 verbatim: the guarantee exists in prose and nowhere in code.
- **Evidence:**
  - Design lines 201-204 ("Known residual risk, accepted and named … §9 requires the projected document be reviewed before first use") and line 315 ("has no mechanical check").
  - `src/boardwatch/profile_bundle/examples/comprehensive/facts/education.yaml` — `predicate: education.result`, `type: decimal`, `value: '3.85'`.
  - The machinery to fix it already exists: `profile_bundle/approvals.py:1-141` derives owner-gated transitions and approval stamps bound to content digests.
- **Suggested direction:** Reuse the bundle's owner-gate pattern: before `project` first emits for a given `projection_digest`, require a recorded approval stamp bound to the digest of `projection.yaml`; editing the file invalidates the stamp. `--check` already diffs, which surfaces template-literal changes; the stamp turns "reviewed before first use" from prose into a gate. One-line alternative if that is too heavy: have `project` print every composed template line (resolved values inline) and require `--check` in the first-use flow — but the recorded stamp is the only option that cannot be skipped by accident.

### Finding 6 — SHOULD-FIX

- **Severity:** SHOULD-FIX
- **Where:** §7 last row (lines 274-280) and its justification (lines 279-280). Pattern: §7.2-5 (identifier stability) plus §7.1-2 (prose justification).
- **Defect:** "`entry_id` / `bullet_id` derive deterministically from `entity_id` / `claim_id`" is an unspecified function, and its stated motivation — "the plan, the artifact ledger and Tier A entailment all key on `entry_id`/`bullet_id`" — is imprecise about what actually breaks and what detects it.
- **Why it matters:** Two concrete gaps. (1) A pure function of `entity_id` cannot distinguish the same entity declared twice in `projection.yaml`; the collision surfaces as the frozen model's `ValueError("duplicate entry_id")` (`tailor/model.py:57-64`) — not as a named §7 fidelity violation, and not naming the `projection.yaml` line. (2) Across bundle revisions, a superseded claim is a new `claim_id` and therefore a new `bullet_id`; the design names "silently break attribution" as the danger but its only detectors are the human-run `--check` and provenance comments in the emitted file. Meanwhile the code the design cites keys differently than claimed: Tier A entailment and the plan are built within one run from one loaded document (`safety.py` compares master vs tailored; `plan.py` operates on the loaded resume), so they are internally consistent; and the artifacts table (`store/tables.py:366`) has no entry/bullet id column at all — the ledger hashes the authored model (`reports/tailor.py:430`). The real cross-run hazard is attribution in *reports and diffs*, which provenance makes detectable but nothing makes loud.
- **Evidence:**
  - Design lines 274-280 (the derivation rule and its justification).
  - `src/boardwatch/tailor/model.py:57-64` — duplicate-id `ValueError`, no projection context.
  - `src/boardwatch/store/tables.py:366-391` — `artifacts`/artifact-relations columns: no entry/bullet ids; `grep -rn "entry_id\|bullet_id" src/boardwatch/store/` returns nothing.
  - `src/boardwatch/reports/tailor.py:430` — "Hash the authored model, not its render."
- **Suggested direction:** Specify the derivation (e.g., `entry_id = f"entry.{entity_id}"`, `bullet_id = claim_id` verbatim — both are already bundle-unique) and add one §7 row: "no `entity_id` is declared more than once in `projection.yaml`" (named, with the offending line). Then make provenance active rather than informational: `--check` fails (or at least warns loudly) when the emitted document's `bundle_revision`/`projection_digest` differ from the current bundle/`projection.yaml` — closing the stale-document path between `project` and `tailor run`.

### Finding 7 — NOTE

- **Severity:** NOTE
- **Where:** §6 step 4 (lines 232-233). Pattern: §7.2-2 (the budget loop).
- **Defect:** The loop is sound but underspecified in two dimensions: add-all-then-drop vs add-one-at-a-time (the text says "add candidates highest-score-first; compile" — both readings are possible, and they differ by up to *n* tectonic compiles per posting), and greedy selection — since additions are score-ordered, "drop the lowest-scoring included" is the *last-added* one, so the result is always a prefix of the score ranking, never the best-fitting subset (a long mid-score entry crowds out two short lower-score ones).
- **Why it matters:** Convergence is fine: the template has no float environments (`grep -n "table\|figure\|float\|minipage\|multicol" src/boardwatch/tailor/render/templates/resume_base.tex` → nothing), content is itemize-only, so dropping content cannot increase page count and the loop terminates within the candidate-count bound. But cost is per-iteration real (each drop is a full tectonic compile), on top of the double compile the design already accepts (lines 100-101); and suboptimality is fine only if named — the design neither names it nor says the loop should stop dropping and re-try shorter candidates.
- **Evidence:** design lines 232-233; `resume_base.tex` content inspection above; `reports/resume_gate.py:115-131` (the oracle the loop iterates).
- **Suggested direction:** Pin the loop to one reading ("add one candidate, compile, repeat until overflow, then drop last-added and recompile, repeat until fit"), state the compile-count bound, and add one sentence acknowledging the result is the largest fitting score-prefix, not a knapsack optimum.

### Finding 8 — NOTE

- **Severity:** NOTE
- **Where:** §4.1 (line 131: "`kind` is declared, never derived"). Pattern: §7.1-6 (closed catalog).
- **Defect:** The frozen model's `kind` is an open string (`tailor/model.py:38`: `kind: str = "experience"`), and the renderer routes on `== "project"` vs *everything else as experience* (`render/latex.py:115,155`). The design declares `kind` explicitly but never names the closed set projection validation must enforce.
- **Why it matters:** A typo (`kind: experince`) passes the frozen model and silently renders the entry under Experience with the wrong subheading shape. The design's "declared, never derived" is right; the missing piece is that the declaration itself needs a closed catalog enforced in projection's schema validation (the frozen model will not do it), with out-of-catalog = typed failure, not a silent fallback — the project's own rule for catalogs.
- **Evidence:** `tailor/model.py:38`; `render/latex.py:110-123` (subheading routing); design line 131.
- **Suggested direction:** One bullet in P1's schema validation: `kind ∈ {"experience", "project"}`, unknown value fatal with the projection.yaml line named.

### Finding 9 — NOTE

- **Severity:** NOTE
- **Where:** §10 P5 gate (lines 328-330), §9 selection tests (lines 311-312). Pattern: §7.2-7 (the honest v1/v2 split) and §7.1-4 (a test that agrees with itself).
- **Defect:** P5's gate — "Beats the deterministic baseline on a measured set, or does not ship" — has no measurement procedure. §9's JD matrix asserts that two JDs *select differently*; nothing anywhere defines what a *good* selection is.
- **Why it matters:** Without a labeled ground truth (owner-ranked selections over the JD matrix, or an explicit rubric), "beats the baseline" is unfalsifiable — the exact failure mode the design's §6 says the program exists to prevent. The v1/v2 split itself is honest and the right sequencing; only the P5 measurement is undefined.
- **Evidence:** design lines 328-330 ("P5 is explicitly gated on measurement, not on being built" — but what measurement?); lines 311-312 (the matrix test's assertion is difference + pinned invariance, never quality).
- **Suggested direction:** Add to the design the P5 measurement: an owner-labeled JD matrix (e.g., the ten JDs used in §9's matrix, each with owner-ranked expected candidate order) recorded before P5 starts; "beats" = agreement/rank metric on that set. The owner labeling is a one-session task and makes P5's gate real.

---

## Answers to the ten specific questions (§7.2)

**1. Scoring bias.** Yes, systematic, and demonstrated (finding 4): an irrelevant four-bullet entry outscores a focused one-bullet entry 4 > 2 against the same JD skill set, because the score counts distinct matched names and breadth touches more names. Wordier bullets bias the same way (one kitchen-sink bullet touching Python, Docker, Kubernetes, Prometheus, PostgreSQL scored 1 on the data JD despite being about infrastructure migration). Fix: precision-normalize (`|∩| / |skills(entry)|`) or average per-bullet coverage. Cost: every selection outcome shifts, so the §9 JD matrix must gain owner-reviewed expected outcomes first — which it needs anyway for finding 9.

**2. The budget loop.** Sound, converging, and monotone — dropping content cannot increase pages because the template has no floats (verified: `resume_base.tex` contains no `table`/`figure`/`float`/`minipage` environment; content is itemize-only), so the candidate-count bound is a real termination guarantee. The pathologies are: (a) cost — every drop is a full tectonic compile, on top of the double compile the design already accepts; (b) greed — dropping the lowest scorer drops the *last added*, so the result is the largest score-prefix that fits, never the best-fitting subset (a long mid-score entry can crowd out two short lower-score ones); (c) the design doesn't pin down add-all-then-drop vs add-one-at-a-time (n vs 2n compiles); (d) the pinned-set-overflow arm is correctly a typed failure naming the pinned set — and it is the right failure, not a warning (finding 2 aside, which is about a different arm). See finding 7.

**3. Is the two-stage split real?** Yes. Stage 2's inputs are the pool (a full `Resume` with ids and texts — everything scoring needs), the JD skill set (the posting's extraction row: `reports/tailor.py:356` reads `row.json.skills`), the persona (registry only), and the budget (`profile.resume_max_pages`, `store/tables.py:203`, default 1). Nothing stage 2 needs lives only in the bundle: `allowed_surfaces`, claim status, and conflict-group checks are all stage-1 validation, done before scoring. The one seam to watch is the persona's `entries` list narrowing by `entry_id` — it already exists in tailor (`persona.py:192-199`) and operates on the projected model, so the split holds. Fine as written.

**4. Fatal in every arm.** Defensible, and the design's two reasons are the right ones: the projected document becomes Tier A's ground truth (`safety.py::output_is_entailed` compares tailored against master — a fabrication introduced by projection is invisible to it), and `resume.yaml` remains a working fallback. The "user gets nothing forever" mode only appears if the owner retires `resume.yaml` before projection is green — worth one sentence in the design making that migration order explicit (projection must prove itself on real JDs *before* `resume.yaml` stops being the pipeline default; finding 3 makes this concrete). No arm should become a warning; the pinned-overflow message should, however, name the actionable knob (`resume_max_pages=1` in the profile; trim pinned content) so the fatal is fixable, which is the drain this quarantine needs.

**5. Identifier stability.** The derivation function is unspecified, and its motivation is overstated (finding 6): Tier A entailment and the plan are within-run and self-consistent; the artifacts table has no entry/bullet id columns; the ledger hashes the authored model. The real hazard is cross-revision: a superseded claim is a new `claim_id` and therefore a new `bullet_id`, silently renumbering the projected document between runs — detectable today only by the human-run `--check` and the provenance comments. Fixes: specify the derivation (both id namespaces are already bundle-unique, so verbatim derivation works), add a duplicate-`entity_id` row to §7, and make provenance active: `--check` fails when the emitted document's digests don't match the current bundle and `projection.yaml`. Also state explicitly what a bundle revision change between `project` and `tailor run` should do (re-project or refuse; today it tailors the stale file silently).

**6. The template hole.** Named, accepted, and real — the design's own example demonstrates it: `{education.result}/10` against the synthetic bundle's `3.85` (a 4.0-scale GPA) renders "3.85/10", an unearned scale assertion smuggled by a template literal, the same shape as `"Senior {employment.title}"`. Accepting it is defensible *only* because §9 requires owner review before first use — but that requirement is prose with no mechanism, and it must be re-earned after every `projection.yaml` edit. The cheap check exists in this codebase already: bind an owner approval stamp to the `projection.yaml` digest (reusing `profile_bundle/approvals.py`'s owner-gate machinery) and refuse to emit until the current digest is stamped; `--check`'s diff then shows exactly what template literals changed since the last approval. See finding 5.

**7. Does this satisfy §5's intent?** Partially, honestly, and with two load-bearing gaps. The v1/v2 split is the right call and is not deferring the whole point — deterministic keyword selection does swap Hookrail/Nakshatra/etc. per JD, which is a real, testable form of "adjusts intelligently." What stands between the design and the owner's "alive" vision is not the model lane; it is (a) finding 4 — the scorer picks breadth over depth, so the swaps it makes are often the wrong swaps — and (b) finding 3 — the daily pipeline never invokes it, so the owner's actual workflow sees zero adjustment until he hand-runs two commands per posting. With those two fixed, v1 already delivers the owner's core intent, and v2's "actively think" becomes an upgrade on a measured baseline instead of the whole feature in disguise. P5's measurement must be defined first (finding 9).

**8. The `pinned` split.** Two states are sufficient for the owner's stated intent — the fixed core is always-present-and-unscored, everything else competes by score, which is exactly "fixed stuff always, swappable stuff swapped." A third state ("appear only if the family matches") is not in the owner's words and not needed for the nurse test. Two real caveats instead: pinned entries always precede candidates and cannot be interleaved (a position-slot notion would be the fix, but nothing in the owner's intent requires it — NOTE), and the persona `entries` list is a second, overlapping selection mechanism, which the design's own open question 2 already names — resolve it before P5, because two mechanisms selecting entries is precisely a §7.1-1 drift hazard.

**9. Multi-tenancy.** The nurse test passes on the schema: templates are data, `kind` is declared, all catalogs (personas, taxonomy, `projection.yaml` shape) are overridable per user, no code change needed — *provided* finding 1 is fixed, because contacts are how the bundle models email/phone/profile for every user, not just Mit. Two riders worth naming: the phone contact being `application`-only in the synthetic bundle is exactly the surface-enforcement the contract must keep (finding 1), and persona selection is SWE-family-only — a nurse's JD falls to the default `general_swe` persona and its "Software Engineer" headline title. That is pre-existing tailor behaviour the design inherits rather than introduces, but stage 2 should not bake the title deeper in; note it in the design so the nurse story is explicit.

**10. What is missing entirely?** The biggest missing stage is pipeline wiring (finding 3): the design specifies the capability end to end and never says how the daily `boardwatch run` uses it — the one integration that turns "a mechanism exists" into "the owner's résumés adjust daily." The design's three open questions are all legitimate, but they are the wrong three to stop at. The missing ones: (a) the contact namespace (finding 1); (b) the P5 measurement definition (finding 9); (c) stale-provenance handling between `project` and `tailor run` (finding 6); (d) the budget loop's infrastructure-failure arm (finding 2).

---

VERDICT: REWORK
