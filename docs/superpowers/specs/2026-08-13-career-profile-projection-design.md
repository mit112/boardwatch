# Career-Profile Projection and JD-Aware Entry Selection

**Status:** design, awaiting owner review · **Date:** 2026-08-13 · **Owner:** boardwatch (Claude)

Implements deferred gate 1 of `2026-08-10-canonical-career-profile-bundle-design.md` §23
("role-family projection and persona selection"), and a capability that document did not anticipate:
JD-aware selection of which experiences and projects appear at all.

Program context: D-155. The program reorients onto the bundle-to-résumé path; `resume.yaml` becomes an
import source rather than an artifact to hand-fix.

---

## 1. Purpose

Boardwatch holds a canonical career-profile bundle (Gate A, MET 2026-08-12) that no part of the résumé
path can read. This design specifies the bridge: how bundle content becomes a compiled, JD-adjusted
résumé, and what may not happen along the way.

The owner's stated intent, unmodified:

> "I created this whole thing so it feels like it's alive. Constantly adjusting, intelligently, to the
> job description... my education, work ex (Saayam For All, NIO) would be there in every résumé because
> they're fixed... the other stuff — Nakshatra, SAKEC Marathon, Hookrail, mobile apps, Knowledge Forge —
> this stuff can be swapped based on the JD."

Two requirements follow, and they are different:

1. **Faithfulness.** Everything on the page traces to bundle content the owner approved.
2. **Adjustment.** Which optional entries appear is decided per JD, against a fixed core that always
   appears.

---

## 2. What is true today, measured

Every claim in this section was verified against the code on 2026-08-13, not inferred.

- **No stage selects entries by JD.** Every operation `build_plan` can emit is bullet-scoped:
  `Select(bullet_id)`, `Delete(bullet_id)`, `EquivalenceSwap(bullet_id)`, `Rewrite(bullet_id)`. The only
  op naming an entry is `Reorder(entry_id)`, which reorders bullets *inside* that entry
  (`tailor/plan.py`). **There is no op that adds, removes, or reorders an entry.**
- **Persona can pin entries but does not.** `personas.yaml` documents that `entries: null` renders every
  master entry and a list renders exactly those; **both bundled personas ship `entries: null`**. Entry
  selection is therefore static and total.
- **Nothing manages a page or length budget.** `MAX_BULLETS_PER_ENTRY = 6` is a per-entry cap, not a
  global budget. The layout gate is a terminal pass/fail whose only remedy is the untailored fallback.
- **Consequence, observed.** `tailor run 19541` (a data-platform JD against an iOS/Swift résumé) scored
  11 of 13 bullets "no jd skills" and planned `kept 13 · dropped 0 · swaps 0`. Not a bad selection — no
  selection exists.
- **`tech_tags` is inert.** Nothing reads it; `reports/tailor.py:430` states the render drops it.
- **The summary is static.** The template carries `%%SUMMARY_START%%`/`%%SUMMARY_END%%` and `SUMMARY` is
  in the renderer's allowed-marker catalog, but `latex.py` has handlers only for `TITLE_START` and
  `SECTIONS_START`. No code substitutes a summary; the template's own prose passes through.
- **`profile_bundle` and `tailor` do not import each other**, in either direction, and a test holds it.

---

## 3. Architecture

```
career-profile/  ─┐
                  ├─▶ [1. projection]  ─▶  pool: pinned + candidates  (JD-BLIND)
projection.yaml  ─┘                              │   in-memory unless requested
                                                 │
JD ──▶ select_persona (exists, deterministic) ───┤   narrows and orders
                                                 ▼
                                    [2. entry selection]  (JD-AWARE, budget-bound)
                                                 ▼
                                    resume.projected.yaml   (a valid résumé document)
                                                 ▼
                              tailor (UNCHANGED): build_plan ─▶ apply ─▶ render ─▶ PDF
```

**Stage 1 is JD-blind. Stage 2 is where the system "adjusts".** Splitting them is what makes stage 1
testable without a JD and keeps the fidelity guarantee separable from the selection policy.

### Package boundaries

A new package `src/boardwatch/projection/`. It imports `profile_bundle` (to read) and `tailor` (to
construct and validate a `Resume`, and to compile for the budget check). **Neither existing package
changes, and the existing wall stays up**: `profile_bundle` still never imports `tailor`, and `tailor`
still never imports `profile_bundle`. `tailor` continues to read a résumé document off disk exactly as
it does today.

### CLI

- `boardwatch profile-bundle project --out <path>` — **stage 1 only.** Emits the pool: every pinned and
  candidate entry. JD-blind, so this is the artifact to read when reviewing what the bundle projects to.
- `boardwatch profile-bundle project --posting <id> --out <path>` — **stages 1 and 2.** Selects against
  that posting's JD and emits a résumé that fits the budget.
- Both accept `--json` for the machine report and `--check`, which re-runs and diffs instead of writing.
- `boardwatch tailor run <id> --resume <path>` — existing loader, unchanged.

**The pool is in-memory unless asked for.** Stage 1 hands its result to stage 2 directly; it is written
only when the caller omits `--posting`.

**The flow is two commands, deliberately.** `project --posting <id>` then `tailor run <id> --resume …`.
Folding projection into `tailor run` would require `tailor` to know about the bundle, which is the wall
this design keeps up. The cost is that the JD is read twice (once for entry selection, once for bullet
planning) and the résumé compiles twice (once for the budget fit, once for the real render).

---

## 4. Artifacts

### 4.1 `{config_dir}/projection.yaml` — the editorial declaration

Lives **outside** the bundle. Design §4.2 records the integration boundary specifically so this phase
"does not accidentally encode renderer or tailoring decisions into the knowledge schema"; which entries
appear on a résumé, in what order, under what heading, is a rendering decision. The bundle stays pure
knowledge and remains publishable as such.

```yaml
projection_version: 1

header:
  - "{person.professional_name}"
  - "{person.email} | {person.phone} | {person.profile_url}"

education:
  - entity_id: education.northeastern
    format: "{education.institution}, {education.credential} in {education.field}, {education.result}/10"

skill_groups:
  - label: Languages
    skills: [skill.python, skill.swift]     # ids from skills/inventory.yaml

entries:
  - entity_id: affiliation.saayam-for-all
    kind: experience          # explicit; NOT derived from entity_type
    pinned: true              # always present, never scored, never dropped
    title:    "{affiliation.role} (Volunteer)"
    subtitle: "{affiliation.organization}"
    dates:    "{affiliation.start_date} – {affiliation.end_date}"
    location: "{affiliation.location}"
    claims: [claim.saayam.llm-service.001, claim.saayam.instrumentation.001]

  - entity_id: project.hookrail
    kind: project
    pinned: false             # candidate: competes for space against the JD
    title:  "{project.name}"
    dates:  "{project.start_date} – {project.end_date}"
    claims: [claim.hookrail.delivery.001, claim.hookrail.storage.001]

extracurricular: []
```

**`kind` is declared, never derived.** A volunteer role is an `affiliation` entity in the bundle and
belongs under Experience on the page — the owner's own convention, visible in the 2026-08-12 job-apps
build, where "Full Stack Developer (Volunteer) · Saayam For All" sits under `\section{Experience}`.
Entity type is a knowledge fact; section placement is editorial.

**`pinned` is the fixed/swappable split.** Pinned entries are always emitted, in declared order, and are
never scored. Everything else is a candidate.

### 4.2 The emitted document

A document in exactly the shape `tailor/load.py` already reads, plus provenance:

```yaml
# bundle_revision:    sha256:…      the revision projected from
# projection_digest:  sha256:…      digest of projection.yaml
# selected_for:       posting 19541 / persona ios      (or "pool" when JD-blind)
header: [...]
education: [...]
skill_groups: [...]
entries: [...]
```

Provenance makes staleness detectable rather than assumed. `--check` re-runs and diffs.

**Round-trip requirement:** the document must load back through the existing résumé loader into a
`Resume` equal to the one projection constructed. This is a contract test, not a hope (§9).

---

## 5. Stage 1 — projection (JD-blind)

Reads the bundle's active revision plus `projection.yaml`; emits the pool: pinned entries, candidate
entries, and the non-entry sections (header, education, skill groups, extracurricular).

Projection constructs a `tailor.model.Resume` in memory so that shape is guaranteed by construction, then
serializes. It does not see a JD, a posting, or a persona.

### Composition rule

Bundle facts are atomic and typed (`education.institution`, `education.credential`, …), while
`Resume.education` and `Resume.header` are display strings. Composition is unavoidable. The rule:

- **Templates substitute fact values only.** Every `{predicate}` resolves against
  `(subject_id = entity_id, predicate)`. An unresolved placeholder is fatal.
- **Every literal in the output is either a fact value from the bundle or a connective the owner wrote
  in the template.** Boardwatch never invents a word.
- **Bullet text is copied verbatim from `claim.text`.** Never templated, never edited, never reflowed.

The fabrication surface is therefore exactly the template, which the owner authored — and the format is
data, not code, which satisfies the multi-tenancy test in `PROGRAM.md` §3b ("could a US-citizen senior
nurse use this without editing code?").

**Known residual risk, accepted and named:** a template can smuggle an unearned claim
(`"Senior {employment.title}"`). Validation cannot distinguish an authored connective from an authored
claim. It is the owner's file and the owner's assertion; §9 requires the projected document be reviewed
before first use.

---

## 6. Stage 2 — entry selection (JD-aware, budget-bound)

The stage that makes the system adjust. Inputs: the pool, the JD's extracted skill set, the selected
persona, and the page budget (`resume_max_pages`, which the owner pins to 1).

### Scoring

Mirrors the bullet-level scoring `build_plan` already performs, lifted to the entry:

```
skills(entry) = ⋃ taxonomy.extract(bullet.text)  ∪  {equivalence-swap targets applicable to the JD}
score(entry)  = |skills(entry) ∩ jd_skills|
```

Reusing `taxonomy.extract` and the equivalence table is deliberate: it is the mechanism already trusted
for bullets, so entry selection inherits its behaviour rather than introducing a second notion of
"relevant".

### Algorithm

1. Emit all `pinned` entries, in declared order. They are never scored and never dropped.
2. Apply the persona's `entries` list if it declares one (narrowing the candidate pool).
3. Rank remaining candidates by `score` descending; ties broken by declared order in `projection.yaml`,
   which keeps the result deterministic and owner-controlled.
4. **Fit to budget.** Add candidates highest-score-first; compile; if the page count exceeds the budget,
   drop the lowest-scoring included candidate and recompile. Bound the loop by the candidate count.
5. If the pinned set alone exceeds the budget, that is a content problem the owner must resolve — report
   it as a typed failure naming the pinned set, never silently drop a pinned entry.

The budget oracle is the **existing page-count gate** (`evaluate_compile` against `resume_max_pages`), not
a heuristic estimate. Iterating against the real gate is the only way to be right about a LaTeX page, and
the degraded-path precedent (retry with the untailored master on overflow) already establishes
compile-retry as idiomatic here.

**Stage 2 fits the *master*, which is necessary but not sufficient.** Tailoring runs afterwards and mostly
shrinks the document (bullets dropped, equivalent phrases swapped), but a Tier-B reword may legitimately
run up to 1.5× the source bullet's length, so a master that fits can still overflow after rewording. The
existing terminal page gate and its untailored fallback remain the last word; stage 2 removes the common
cause of overflow, it does not replace the gate.

### Deterministic first; the model lane is next, not never

v1 is deterministic: no credential, runs on every unattended run, fully testable.

v2 adds an opt-in model re-ranker behind the same interface, failing open to the deterministic result
when the lane is dead or absent. Sequencing rationale: without a deterministic baseline, "the model picks
good projects" is unfalsifiable, which is the failure mode this program exists to prevent. It also
matches `PROGRAM.md` §3.P5 item 7 — deterministic default stays the default, any model lane is opt-in.

Wiring a model lane into `pipeline/runner.py` remains an open owner decision (D-146) and is **not**
assumed by this design.

---

## 7. Fidelity contract

Enforced at projection time, before any document is written:

| Rule | Violation |
|---|---|
| Every `{predicate}` resolves to a fact on the named entity | fatal |
| Every referenced fact carries `resume` in `allowed_surfaces` | fatal |
| Every referenced claim is `status: approved` **and** résumé-surfaced | fatal |
| No referenced fact sits in an unresolved conflict group | fatal |
| Every `entity_id` / `claim_id` / `skill_id` exists in the bundle | fatal |
| Bullet text equals `claim.text` byte-for-byte | fatal |
| `entry_id` / `bullet_id` derive deterministically from `entity_id` / `claim_id` | fatal |

The `allowed_surfaces` rule is where the bundle's application-only gate actually bites: a fact the owner
marked application-only cannot reach a page, structurally.

Identifier stability matters beyond tidiness — the plan, the artifact ledger and Tier A entailment all key
on `entry_id`/`bullet_id`, so a projection that renumbers between runs would silently break attribution.

---

## 8. Failure behaviour: fatal, uniformly

`CLAUDE.md` requires the fail-safe direction be chosen per gate. For projection it is fatal in every arm:
**refuse to emit rather than emit a partial résumé.**

Two reasons, both specific to this stage:

1. **The projected document becomes Tier A's ground truth.** `safety.py::output_is_entailed` compares the
   tailored bullet against the master. A fabrication introduced *by projection* is not caught — it becomes
   the truth. No downstream gate can see it. This is the silent-success class that has already produced
   D-138 and D-141 in this codebase.
2. **Refusing costs nothing.** `resume.yaml` still works and job-apps is delivering the owner's daily
   minimum (D-155). A failed projection blocks no other path, so there is no fail-open argument.

---

## 9. Testing strategy

- **Golden projection over the synthetic example bundle** that ships as package data. No personal data, so
  it runs in CI and the generalization checker stays clean.
- **Round-trip contract test:** `load_resume(serialize(project(bundle))) == project(bundle)`. This makes
  "the emitted file really is a valid résumé" falsifiable rather than asserted.
- **One test per fatal arm in §7**, each confirmed to fail without its fix — and the confirmation must name
  *which* assertion trips, since a pre-existing assertion firing first proves nothing (D-148).
- **Expected fact/claim sets derived from the bundle at run time**, never a hardcoded list. A hardcoded
  catalog passed 98 tests while covering 5 of 13 classes once already (D-142, D-149); this design has the
  same shape and must not repeat it.
- **Selection tests over a JD matrix:** a data-platform JD and a mobile JD against one pool must select
  different candidates while emitting an identical pinned set.
- **Budget tests:** a pool that overflows must converge; a pinned set that alone overflows must report the
  typed failure rather than drop a pinned entry.
- **Owner review before first use.** The projected document is read by the owner before it renders
  anything real — the residual template risk in §5 has no mechanical check.

---

## 10. Delivery

| Slice | Content | Gate |
|---|---|---|
| P1 | `projection.yaml` schema, loader, strict validation | Every §7 rule has a failing-then-passing test |
| P2 | Stage 1 projection over the synthetic bundle; serializer | Golden output + round-trip contract test green |
| P3 | `boardwatch profile-bundle project` CLI, `--json`, `--check` | Exit-code tiers match the bundle CLI's existing convention |
| P4 | Stage 2 deterministic entry selection + budget fit | JD matrix selects differently; pinned set invariant |
| P5 | Model re-ranker, opt-in, fail-open | Beats the deterministic baseline on a measured set, or does not ship |

P5 is explicitly gated on measurement, not on being built.

---

## 11. Out of scope for v1

- **Summary wiring.** Requires a field on the frozen `Resume` and a `SUMMARY` handler in `latex.py`.
  Deferred so v1 changes nothing downstream and stays discardable.
- **`tech_tags`.** Emitted empty; nothing reads it.
- Any change to `Resume`, `latex.py`, `persona.py`, or `plan.py`.
- Gate B population of the real bundle — this design is built and tested against the synthetic bundle.
- Wiring any model lane into `pipeline/runner.py`.

---

## 12. Open questions

1. **Does `projection.yaml` belong to the published mechanism or the personal instance?** The schema is
   published; the owner's file is personal (`PROGRAM.md` §3b). Whether a seed example ships as package
   data is unresolved.
2. **Does the persona's `entries` list survive?** Stage 2 subsumes most of what a persona entry-pin would
   do. Keeping both risks two overlapping selection mechanisms; removing it changes shipped P4 behaviour.
   Deferred until stage 2 is measured.
3. **What is the budget when `resume_max_pages > 1`?** The owner pins 1; the algorithm generalises, but
   the multi-page ordering convention is unspecified.
