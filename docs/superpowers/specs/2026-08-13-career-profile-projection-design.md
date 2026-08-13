# Career-Profile Projection and JD-Aware Entry Selection

**Status:** design, revision 2 — reworked after two independent external reviews returned REWORK
**Date:** 2026-08-13 · **Owner:** boardwatch (Claude)

Implements deferred gate 1 of `2026-08-10-canonical-career-profile-bundle-design.md` §23, and a
capability that document did not anticipate: JD-aware selection of which experiences and projects appear
at all.

Program context: D-155. Review context: D-156. Revision 1 (`ce1efde`) was reviewed by two external
reviewers running in-repo; both returned REWORK with executable probes. Every finding is dispositioned in
§13.

---

## 1. Purpose

Boardwatch holds a canonical career-profile bundle (Gate A, MET 2026-08-12) that no part of the résumé
path can read. This design is the bridge.

The owner's intent, unmodified:

> "I created this whole thing so it feels like it's alive. Constantly adjusting, intelligently, to the job
> description... my education, work ex (Saayam For All, NIO) would be there in every résumé because
> they're fixed... the other stuff — Nakshatra, SAKEC Marathon, Hookrail, mobile apps, Knowledge Forge —
> this stuff can be swapped based on the JD."

Two requirements, and they are different:

1. **Faithfulness.** Everything projected traces to bundle content the owner approved.
2. **Adjustment.** Which optional entries appear is decided per JD, against a fixed core that always
   appears.

---

## 2. What is true today, measured

Verified against the code on 2026-08-13. Items 8-11 were found by external review of revision 1 and are
the reason this revision exists.

1. **No operation `build_plan` emits adds, removes, or reorders an entry.** The op union is
   `Select`/`Reorder`/`Delete`/`EquivalenceSwap`/`Rewrite` (`tailor/plan.py:15-40`); `build_plan` itself
   emits only `Reorder`, `Delete`, `EquivalenceSwap` (`plan.py:87-103`). `Reorder` names an entry only to
   reorder bullets inside it.
2. **Both bundled personas ship `entries: null`** (`personas.yaml:31,37`), so every master entry always
   renders. The pinning mechanism exists (`persona.py:192-199`) and is unused.
3. **Nothing manages a page or length budget.** `MAX_BULLETS_PER_ENTRY = 6` is per-entry
   (`plan.py:48,87-90`); `evaluate_compile` is a terminal pass/fail (`reports/resume_gate.py:115-131`)
   whose only remedy is the untailored fallback.
4. **`tech_tags` is inert to selection and rendering, but NOT to identity.** The renderer drops it, and
   `reports/tailor.py:430` hashes `master.model_dump_json()` *deliberately* so two masters that merely
   look alike do not content-address to one artifact. Emitting it empty is therefore a lineage change,
   not a no-op.
5. **The renderer has no `SUMMARY` handler.** `SUMMARY` is in `_ALLOWED_MARKERS`
   (`render/latex.py:54-55`) but `emit()` handles only `TITLE` and `SECTIONS`. Summary prose is static.
6. **`profile_bundle` and `tailor` do not import each other**, held by a transitive import-graph test with
   positive controls (`tests/profile_bundle/test_profile_bundle_tailor_isolation.py`).
7. **`taxonomy.extract` is public and pure** (`extract/taxonomy.py:47-48`).
8. **The renderer never reads `Resume.header` or `Resume.education`.** `LatexRenderer.emit` builds
   sections from skills, entries, projects and extracurriculars only. The layout gate says so verbatim:
   *"Header/education are NOT asserted here: Increment 1's template hardcodes them (never
   model-rendered)."* (`reports/resume_gate.py:237-242`). **Projecting them cannot change the PDF.**
9. **Equivalence applicability is private.** `_applicable_swaps` (`plan.py:51-62`) is the behaviour that
   decides whether a swap target counts; `EquivalenceTable.as_pairs()` exposes data only. Entry scoring
   cannot "inherit `build_plan`'s behaviour" without either importing a private helper or restating it.
10. **Contact channels are not facts.** Email, phone, profile URL and location are `ContactRecord`s
    (`profile_bundle/models/entities.py:238`), not `FactRecord`s, and the synthetic bundle's phone is
    `allowed_surfaces: [application]`.
11. **The daily pipeline never projects.** `cli/run_cmd.py:80` resolves the résumé to
    `resume_path or {config_dir}/resume.yaml` and `pipeline/runner.py:526` passes it verbatim to
    `run_tailor`.

**Consequence, observed.** `tailor run 19541` (a data-platform JD against an iOS/Swift résumé) scored 11
of 13 bullets "no jd skills" and planned `kept 13 · dropped 0 · swaps 0`. Not a bad selection — no
selection exists.

---

## 3. Scope of v1: only what the renderer consumes

Because of §2.8, v1 projects **`skill_groups`, `entries` and `extracurricular`** and nothing else.

`header`, `education` and the summary are **hardcoded in the user's LaTeX template and are out of scope**,
declared here rather than discovered later. This is the same reasoning already applied to the summary:
projecting a field the renderer never reads is a faithfulness guarantee that cannot land.

**Stated plainly: after v1, the bundle is not the source of truth for the owner's name, contact details,
or education.** Those remain hand-edited in the template. Taking renderer ownership of them is a separate
design (§12).

This scope decision removes three revision-1 defects outright: the inert header/education projection, the
contact-channel grammar (§2.10), and a template-smuggling example the design itself committed
(`{education.result}/10` against a 4.0-scale GPA renders "3.85/10").

---

## 4. Architecture

```
career-profile/  ─┐
                  ├─▶ [1. projection] ─▶ ProjectionPool (typed, in-process or serialized)
projection.yaml  ─┘                              │        pinned + candidates + digests
                                                 │
JD ──▶ jd_skills ────────────────────────────────┤
                                                 ▼
                                    [2. entry selection] (JD-aware, budget-bound)
                                                 ▼
                              resume.projected.yaml  +  projection-manifest.json
                                                 ▼
                              tailor (UNCHANGED): persona ─▶ build_plan ─▶ render ─▶ PDF
```

**Stage 1 is JD-blind. Stage 2 is where the system adjusts.** Splitting them keeps stage 1 testable
without a JD and separates the fidelity guarantee from the selection policy.

### Package boundaries

A new package `src/boardwatch/projection/`. It imports `profile_bundle` (to read) and `tailor` (to
construct and validate a `Resume`, and to compile for the budget check). **The existing wall stays up**:
`profile_bundle` still never imports `tailor`, and `tailor` still never imports `profile_bundle`.

**One narrow change to `tailor` is required and is not optional** (§2.9): extract a public
`effective_skills(text, jd_skills, taxonomy, equivalences) -> set[str]` from `plan.py`'s private
`_applicable_swaps` + coverage logic, and have `build_plan` call it. Projection calls the same function.
Revision 1 claimed entry scoring "inherits" bullet-scoring behaviour *and* that `plan.py` is unchanged;
those cannot both hold, and a restated rule is this project's most expensive recurring defect.

### Persona ownership — assigned to exactly one stage

**`tailor` owns persona shaping. Stage 2 does not apply the persona.**

Revision 1 had stage 2 apply `persona.entries` and then drop entries for budget; `tailor run` would then
re-apply the persona and `apply_persona` raises `PersonaError` on any declared id missing from its input
(`persona.py:194-198`). A budget-selected résumé could never render. This is latent today only because
both bundled personas ship `entries: null`, and multi-tenancy makes latent unacceptable.

Consequence: stage 2's budget compile measures a document without persona title and skill-group ordering,
which is a *different* document from what finally renders. Handled in §6.

### CLI

- `boardwatch profile-bundle project --out <path>` — **stage 1 only.** Serializes the pool for review.
  JD-blind.
- `boardwatch profile-bundle project --posting <id> --out <path>` — **stages 1 and 2.** Writes
  `resume.projected.yaml` and `projection-manifest.json` beside it.
- Both accept `--json` and `--check` (re-run and diff; **exits non-zero on drift** — see §4.2).

---

## 4.1 `{config_dir}/projection.yaml` — the editorial declaration

Lives **outside** the bundle: "which entries appear, in what order" is a rendering decision, and the
bundle design warns against encoding renderer decisions into the knowledge schema.

```yaml
projection_version: 1

skill_groups:
  - label: Languages
    skills: [skill.python, skill.swift]     # ids from skills/inventory.yaml

entries:
  - entity_id: affiliation.saayam-for-all
    kind: experience             # closed catalog {experience, project}; unknown = fatal
    pinned: true                 # always present, never scored, never dropped
    heading:  "{affiliation.organization}"          # REQUIRED by Entry; was missing in revision 1
    title:    "{affiliation.role} (Volunteer)"
    subtitle: "{affiliation.organization}"
    dates:    "{affiliation.date_range}"            # ONE fact of type date_range, not start/end
    location: "{affiliation.location}"
    claims: [claim.saayam.llm-service.001, claim.saayam.instrumentation.001]

  - entity_id: project.hookrail
    kind: project
    pinned: false                # candidate: competes for space against the JD
    heading: "{@display_name}"   # entity display field, distinct namespace from predicates
    dates:   "{project.start_date} – {project.end_date}"
    claims: [claim.hookrail.delivery.001, claim.hookrail.storage.001]

no_match_fallback: [project.hookrail]   # used when no candidate scores > 0 (§6)
extracurricular: []
```

**`kind` is declared, never derived**, and is a closed catalog. A volunteer role is an `affiliation` in the
bundle and belongs under Experience on the page — entity type is knowledge, section placement is
editorial. The frozen model types `kind` as an open `str` and the renderer routes on `== "project"` with
everything else falling through to Experience, so a typo would render silently; projection's schema
validation owns the catalog.

**`pinned` is the fixed/swappable split.** Pinned entries are always emitted, in declared order, never
scored.

### The placeholder grammar (closed)

Revision 1 said only "every `{predicate}` resolves against `(subject_id = entity_id, predicate)`", which
could not express its own examples. The grammar has exactly two namespaces:

| Form | Resolves to | Notes |
|---|---|---|
| `{<predicate>}` | the fact on this entry's entity with that predicate | must be résumé-surfaced |
| `{@<field>}` | an entity display field: `@display_name`, `@status` | not a fact; no surface gate |

No other form is admitted. A placeholder that is neither is fatal, naming the `projection.yaml` line.

### Rendering typed fact values

`FactValue` has nine typed shapes. Each admitted kind gets exactly one rendering, defined here so that
formatting is not invented at implementation time:

| Kind | Rendering |
|---|---|
| `string` | verbatim |
| `decimal` | verbatim as stored (no rounding, no unit appended) |
| `integer` | verbatim |
| `year_month` | `YYYY-MM` verbatim |
| `date_range` | the stored range's own display form, verbatim |
| `boolean`, `list`, `skill_ref`, and any other kind | **not admitted in a template — fatal** |

Rendering is verbatim in every admitted case. Projection never reformats a stored value, because
reformatting is authoring.

## 4.2 Emitted artifacts

Revision 1 put provenance in YAML comments. `load_resume` calls `yaml.safe_load`, which discards them, so
provenance never reached the artifact ledger and staleness was undetectable unless someone chose to run
`--check`.

Two files are written together:

- **`resume.projected.yaml`** — exactly the shape `tailor/load.py` reads. No extra keys, so the existing
  loader is untouched.
- **`projection-manifest.json`** — a sidecar carrying `bundle_revision`, `projection_digest`,
  `posting_id`, `jd_skills`, pinned ids, selected ids, scores, and the `claim_id → bullet_id` map.

`--check` re-projects and **exits non-zero** when the emitted document's digests differ from the current
bundle or `projection.yaml`. Provenance is active, not informational.

**Known residual, named:** `tailor run` does not read the manifest, so running it directly on a stale
projected file still tailors the stale document. Closing that requires `tailor` to learn about the
manifest, which crosses the wall. Carried as an open question (§12), not silently accepted.

---

## 5. Stage 1 — projection (JD-blind)

Reads the bundle's active revision plus `projection.yaml`; emits a typed `ProjectionPool`:

```python
@dataclass(frozen=True)
class ProjectionPool:
    resume: Resume                      # all entries, pinned and candidate
    pinned_entry_ids: tuple[str, ...]   # declared order
    candidate_entry_ids: tuple[str, ...]
    no_match_fallback_ids: tuple[str, ...]
    bundle_revision: str
    projection_digest: str
```

**A serialized `Resume` is not a sufficient handoff.** `Entry` has no `pinned` field, so stage 2 could not
distinguish the fixed core from swappable projects and would have to reread `projection.yaml` or guess.
The pool is the contract between stages; the plain `Resume` document is stage 2's *output*, not stage 1's
handoff.

### Composition rule

- **Templates substitute fact values only**, through the §4.1 grammar. Unresolved ⇒ fatal.
- **Every literal in the output is either a bundle value or a connective the owner wrote.** Boardwatch
  never invents a word.
- **Bullet text is copied verbatim from `claim.text`.** Never templated, edited, or reflowed.
- **`tech_tags` is emitted empty**, and this is recorded as a deliberate lineage decision (§2.4), not
  claimed to be a no-op.

### The template hole, and its gate

A template literal can smuggle an unearned claim (`"Senior {employment.title}"`). Revision 1 accepted this
with "owner review before first use" — prose with no mechanism, re-earned never.

**v1 binds it.** Reusing the bundle's own owner-gate pattern (`profile_bundle/approvals.py`): `project`
refuses to emit until an approval stamp bound to the current `projection_digest` exists. Editing
`projection.yaml` changes the digest and reopens the gate. `--check`'s diff shows exactly which template
literals changed.

This does not prove a literal is honest — nothing can — but it guarantees no literal reaches a résumé
without the owner having seen that exact text.

---

## 6. Stage 2 — entry selection (JD-aware, budget-bound)

Inputs: the pool, the JD's extracted skill set, and the page budget (`resume_max_pages`, pinned to 1).
**Not** the persona (§4).

### Scoring

Revision 1 used `|skills(entry) ∩ jd_skills|`, an unnormalized count of distinct matched names. A reviewer
demonstrated the bias with a probe: a shallow four-bullet entry ("Attended a Snowflake vendor talk", "Ran
one Airflow job during an internship", …) scored **4** against a data JD while a focused, deeply relevant
one-bullet entry scored **2**. Lifting a per-bullet metric to entry level introduces a size bias that does
not exist at bullet level, because `build_plan` ranks bullets independently.

v1 scores **mean per-bullet JD coverage**:

```
score(entry) = mean over its bullets of  |effective_skills(bullet.text, jd_skills, …) ∩ jd_skills|
```

On the probe above: deep entry `2/1 = 2.0`, shallow entry `4/4 = 1.0`. It also survives the opposite
failure — naive precision (`|∩| / |skills(entry)|`) would let a one-token entry score 1.0 and dominate;
under mean coverage that entry scores 1.0 and loses to the deep entry's 2.0.

Ties break by total distinct matched skills, then by declared order in `projection.yaml`.

**This is a v1 heuristic, and its quality is measured (§10 P5), not asserted.** Keyword matching cannot
observe depth; it can only avoid rewarding pure breadth.

### Admission floor

**A candidate scoring 0 is never admitted, even when there is room.** Revision 1 added candidates
highest-score-first until the page overflowed, so whenever everything fit, a mobile JD and a data JD
produced *identical* résumés — v1 would not have decided anything.

If no candidate scores above 0, the declared `no_match_fallback` list is used. That is this quarantine's
drain: a JD matching nothing yields a deliberate, owner-declared résumé rather than a pinned-only stub.

### Algorithm

1. Emit all pinned entries in declared order. Never scored, never dropped.
2. Rank candidates with `score > 0` descending; ties as above. If none, use `no_match_fallback`.
3. **Add one candidate, compile, repeat until the budget is exceeded; then drop the last-added candidate
   and stop.** Pinned by this reading: at most `n+1` compiles, not `2n`.
4. If the pinned set alone exceeds the budget, fail with a typed error naming the pinned set **and the
   actionable knob** (`resume_max_pages`, or trim pinned content). Never drop a pinned entry.

**The result is the largest fitting score-prefix, not a knapsack optimum** — a long mid-score entry can
crowd out two short lower-score ones. Named, accepted; optimising it is not worth a combinatorial search
over compiles.

Termination is guaranteed: the template has no float environments (verified — no `table`, `figure`,
`float`, `minipage` or `multicol` in `resume_base.tex`), content is itemize-only, so removing content
cannot increase page count.

### The compile gate has four arms, not one

`evaluate_compile` returns `BINARY_MISSING` / `COMPILE_FAILED` / `PAGE_LIMIT_EXCEEDED` / `OK`, and only
the last two carry a page count.

**Only `PAGE_LIMIT_EXCEEDED` drops a candidate.** `BINARY_MISSING` and `COMPILE_FAILED` during budget fit
are **fatal and named as infrastructure failures**, never treated as overflow.

This arm is not hypothetical. `pdfinfo` is a known live gap in this project — missing, it returns `None`
(`reports/tailor.py:167-171`) laundered into `COMPILE_FAILED`. A literal reading of revision 1 would have
dropped every candidate one compile at a time and then blamed the owner's pinned content, never naming the
true cause. That is exactly the silent-misdiagnosis class this codebase has shipped twice.

### The budget measures a different document than renders

Stage 2 compiles without persona shaping; `tailor run` applies the persona afterwards, which changes the
headline title and skill-group order. Skill-group *reordering* does not change content volume, and the
title occupies a fixed line, so the discrepancy is bounded — but it is real, and the terminal page gate
plus untailored fallback remain the last word. Stage 2 removes the common cause of overflow; it does not
replace the gate.

Also unchanged: a Tier-B reword may run to 1.5x its source bullet's length, so a fitting master can still
overflow after rewording.

### Deterministic first; the model lane is next, not never

v1 is deterministic: no credential, runs unattended, fully testable. v2 adds an opt-in model re-ranker
behind the same interface, failing open to the deterministic result. Without a deterministic baseline,
"the model picks good projects" is unfalsifiable.

---

## 7. Fidelity contract

Enforced before any document is written:

| Rule | Violation |
|---|---|
| Every placeholder matches the §4.1 grammar and resolves | fatal |
| Every referenced fact carries `resume` in `allowed_surfaces` | fatal |
| Every fact value is an admitted kind (§4.1) | fatal |
| Every referenced claim is `status: approved` **and** résumé-surfaced | fatal |
| **Every claim's `subject_id` equals the entry's `entity_id`** | fatal |
| **Every referenced skill carries `resume` in `allowed_surfaces`** | fatal |
| No referenced fact sits in an unresolved conflict group | fatal |
| Every `entity_id` / `claim_id` / `skill_id` exists in the bundle | fatal |
| **No `entity_id` is declared more than once in `projection.yaml`** | fatal, naming the line |
| `kind` is in the closed catalog `{experience, project}` | fatal, naming the line |
| Bullet text equals `claim.text` byte-for-byte | fatal |
| An approval stamp exists for the current `projection_digest` | fatal |

The two bolded additions close a hole revision 1 had: an approved, résumé-surfaced claim belonging to
*another* entity passed every rule and would have printed one project's accomplishment under another
employer; and a skill valid but `application`-only could be named in `skill_groups`.

### Identifier derivation

`entry_id = "entry." + entity_id`, `bullet_id = claim_id` verbatim. Both namespaces are already
bundle-unique. The duplicate-`entity_id` rule above is what makes the derivation total.

**Deterministic is not stable across revisions.** A superseded claim gets a new `claim_id` and therefore a
new `bullet_id`. Within a run this is harmless — Tier A entailment and the plan are built from one loaded
document, and the `artifacts` table carries no entry/bullet id columns. Across runs it silently renumbers.
The manifest's `claim_id → bullet_id` map is what makes that inspectable; cross-revision successor
tracking is deferred (§12).

---

## 8. Failure behaviour: fatal, uniformly

**Refuse to emit rather than emit a partial résumé.** Two reasons specific to this stage:

1. **The projected document becomes Tier A's ground truth.** `output_is_entailed` compares the tailored
   résumé against the master; a fabrication introduced *by projection* is not caught — it becomes the
   truth. This is the silent-success class behind D-138 and D-141.
2. **Refusing costs nothing.** `resume.yaml` still works and job-apps delivers the owner's daily minimum
   (D-155). A failed projection blocks no other path.

Two riders. Stage 1 without `--posting` never compiles, so no compile arm can fail it. And **the migration
order is explicit: `resume.yaml` must remain the pipeline default until projection is proven on real
JDs** — otherwise "fatal in every arm" becomes "the user gets nothing."

---

## 9. Testing strategy

- **Golden projection over the synthetic example bundle** (package data). No personal data, so it runs in
  CI and the generalization checker stays clean.
- **Round-trip contract test:** `load_resume(serialize(pool.resume)) == pool.resume`.
- **One test per fatal arm in §7**, each confirmed to fail without its fix — and the confirmation must name
  *which* assertion trips, since a pre-existing assertion firing first proves nothing (D-148).
- **Expected fact/claim sets derived from the bundle at run time**, never hardcoded. A hardcoded catalog
  passed 98 tests while covering 5 of 13 classes once already (D-142, D-149).
- **Selection tests, with the negative control revision 1 lacked:**
  - a data JD and a mobile JD over one pool select different candidates;
  - the pinned set is byte-identical across both;
  - **with a roomy budget, an unrelated zero-score candidate stays out** — this is the test that would
    have caught revision 1's missing admission floor;
  - a JD matching nothing yields exactly `no_match_fallback`.
- **Scoring test pinning the demonstrated bias:** the shallow-four-bullet entry must lose to the focused
  one-bullet entry.
- **Budget tests:** a pool that overflows converges; a pinned-only overflow reports the typed failure with
  its knob; **a stubbed compile returning `COMPILE_FAILED` fails named and drops nothing.**
- **A drift test that both scorers agree:** `build_plan` and projection must call the same
  `effective_skills`; a test asserts the shared callable is the only implementation.

---

## 10. Delivery

| Slice | Content | Gate |
|---|---|---|
| P0 | Extract public `effective_skills` from `plan.py`; `build_plan` calls it | Existing plan tests green, unchanged behaviour |
| P1 | `projection.yaml` schema, loader, strict validation, approval stamp | Every §7 rule has a failing-then-passing test |
| P2 | Stage 1 → `ProjectionPool`; serializer; manifest | Golden output + round-trip test green |
| P3 | `project` CLI, `--json`, `--check` with non-zero drift exit | Exit tiers match the bundle CLI's convention |
| P4 | Stage 2: scoring, admission floor, budget fit, four-arm gate handling | Selection matrix incl. roomy-budget negative control |
| P5 | Pipeline integration — **committed by Mit, built after v1** (§12 Q1) | Projection runs inside `boardwatch run`; `resume.yaml` stops being the daily default only once §8's migration order is satisfied |
| P6 | Model re-ranker, opt-in, fail-open | Beats the deterministic baseline on the labeled matrix |

**P6's measurement is defined before P6 starts**, or its gate is unfalsifiable: an owner-labeled JD matrix
— the §9 matrix JDs, each with the owner's own ranked expected candidate order — recorded first. "Beats"
means a rank-agreement metric on that set. Labeling is a one-session owner task.

---

## 11. Out of scope for v1

- **`header`, `education`, and the summary** — all template-hardcoded and never model-rendered (§3).
- **`tech_tags`** — emitted empty, with its lineage effect recorded rather than denied.
- Any change to `Resume`, `latex.py`, `persona.py`, or the store schema.
- Gate B population of the real bundle — this design is built and tested against the synthetic bundle.
- Wiring any model lane into `pipeline/runner.py`.

**No longer out of scope:** `plan.py` changes narrowly in P0 to expose `effective_skills`. Revision 1's
"no `plan.py` change" could not coexist with its "inherits `build_plan`'s behaviour."

---

## 12. Open questions

1. ~~**Does the daily `boardwatch run` invoke projection?**~~ **RULED by Mit, 2026-08-13: it will be
   built, after v1.** Not manual-only forever, and not part of v1. Today the pipeline reads static
   `resume.yaml` (`run_cmd.py:80`), so until that slice lands the projection is exercised by hand, one
   posting at a time — which is the right order anyway: §8 requires `resume.yaml` stay the pipeline
   default until projection is proven on real JDs, and hand-running is how it gets proven. Carried as
   slice P5 in §10 with its shape still open (an opt-in `boardwatch run --project`, or projection as a
   pipeline stage). **What is settled is that it happens; what is open is its form.**
2. **Should `tailor run` validate the projection manifest?** It would close the stale-document path, and
   it crosses the wall this design otherwise keeps up.
3. **Does the persona's `entries` list survive stage 2?** Two mechanisms selecting entries is a drift
   hazard. Resolve before P6.
4. **Cross-revision claim succession.** `ClaimRecord` has no supersession edge, unlike `FactRecord`. Adding
   one is a bundle-schema change.
5. **Renderer ownership of header/education/summary** — the separate design §3 defers.
6. **Persona role families are a closed software-only catalog** (`persona.py:27-34`), so a non-software
   user falls to the default persona and its "Software Engineer" headline. Pre-existing, inherited, and it
   bounds the multi-tenancy claim until that catalog moves to data.

---

## 13. Review disposition (revision 1 → 2)

Two external reviewers, independently, in-repo, both REWORK. All seven of revision 1's §2 premises were
confirmed by both; the defects were in what the design built on them.

| Finding | Source | Disposition |
|---|---|---|
| Renderer never reads `header`/`education` | GPT | **Fixed by scope** — §3 |
| Pool type cannot carry `pinned` | GPT | **Fixed** — typed `ProjectionPool`, §5 |
| Persona applied twice; `PersonaError` on trimmed subset | GPT | **Fixed** — tailor owns persona, §4 |
| Declaration not executable against the real schema | GPT | **Fixed** — grammar + typed-value table, §4.1 |
| Missing `claim.subject_id` and skill-surface checks | GPT | **Fixed** — §7 |
| No relevance floor; identical résumés on a roomy budget | GPT | **Fixed** — admission floor, §6 |
| Provenance in YAML comments is discarded | GPT | **Fixed** — manifest sidecar, §4.2 |
| No shared scoring primitive | GPT | **Fixed** — `effective_skills`, P0 |
| Template smuggling has no mechanical gate | GPT + DeepSeek | **Fixed** — digest-bound approval, §5 |
| Identifier stability overstated | GPT + DeepSeek | **Fixed** — derivation specified, §7 |
| Contacts are not facts | GPT + DeepSeek | **Dissolved by scope** — §3 |
| Scoring bias (probe: 4 > 2) | DeepSeek | **Fixed** — mean per-bullet coverage, §6 |
| Budget loop ignores three of four gate arms | DeepSeek | **Fixed** — §6 |
| Pipeline never wired | DeepSeek | **Accepted and scheduled** — Mit ruled 2026-08-13 that it gets built after v1; slice P5, form still open |
| `kind` is not a closed catalog | DeepSeek | **Fixed** — §4.1, §7 |
| P6 gate has no measurement | DeepSeek | **Fixed** — labeled matrix defined, §10 |
| Budget loop reading ambiguous; greedy | DeepSeek | **Fixed** — one reading pinned, greediness named, §6 |
| `tech_tags` inert claim imprecise | GPT | **Fixed** — §2.4 |

**Where the reviewers disagreed, and who was right.** Three splits, all resolved against the code:
`tech_tags` (GPT right — it changes the master hash), premise 7 (GPT right — `_applicable_swaps` is
private, so revision 1 contradicted itself), and "is the split real?" (GPT right — `Entry` has no `pinned`
field). Running two reviewers with the same brief produced three findings one of them would have missed.
