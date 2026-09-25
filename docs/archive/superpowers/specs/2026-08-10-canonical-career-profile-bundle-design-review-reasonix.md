# Independent adversarial design review — `2026-08-10-canonical-career-profile-bundle-design.md`

Reviewed against the live tree (STATE.md, `src/boardwatch/{core/settings,eligibility/facts,tailor/{model,load,persona},reports/tailor,store/{artifacts,tables},cli/*}`). Every line reference was verified against the actual document; live code wins where prose conflicts.

## Verdict

`NEEDS-REVISION`

## Findings

### BLOCKING

**1. Manifest digest self-reference normalization is unspecified**

- **§7, lines 186–195** (steps 1–6), especially line 191.
- **Evidence:** Step 1 "Enumerate every source file in the logical revision tree"; step 3 "Exclude only `manifest.bundle_digest` from its own leaf calculation." The spec never states (a) whether `manifest.yaml` is itself one of the enumerated source files, (b) what value occupies `bundle_digest` while the manifest's own leaf is computed (sentinel? key stripped? empty string?), or (c) the relative-path base for the sorted path+digest pairs (revision-root-relative for source files, bundle-root-relative for shared blobs — two bases mixed in one sequence). If the manifest were *excluded* from enumeration, then `revision`, `change_id`, and `parent_bundle_digest` would sit outside the digest and §20.6's "computed … digest matches the manifest" would become vacuous — any manifest would match.
- **Why it matters:** The canonical digest is the root identity anchoring immutability detection, parent linkage, and artifact lineage. Two implementations choosing different self-reference conventions produce different digests for identical content, breaking the §20.6 reproducibility guarantee (lines 751–752) — which Gate A ("content-addressed with reproducible … digests", line 812) is measured on.
- **Correction:** Specify executable pseudocode: the manifest is enumerated like any other file; before normalization its `bundle_digest` value is replaced by the reserved sentinel `""`; step 5's blob pairs are bundle-root-relative, source-file pairs revision-root-relative, and both are sorted into one sequence. State the base explicitly.

**2. No initial predicate catalog**

- **§10.1, lines 315–316**; examples only at lines 277 (`technology_used`) and 487 (`start_date`); skill `category: language` (line 526) likewise unenumerated.
- **Evidence:** Every other closed catalog is enumerated: entities (§9, 8 types), statuses (§9), verification states and bases (§10.2, 6 + 7), surfaces (§10.3, 3), qualifiers (§11, 6), evidence classes and directions (§12, 6 + 3), claim statuses (§15, 4), ruling decisions (§13, 4), actors (§17, 3). The predicate catalog — the interface between the fact model and every semantic validation rule ("Predicate contracts in code declare which value types, entity types, evidence bases, and surface combinations are legal") — is the single catalog left to an unspecified "code" contract.
- **Why it matters:** Gate A ("parsed into strict typed models", "validated … semantically") cannot be assessed or implemented without the legal predicate set: a reviewer cannot check domain coverage (title, dates, responsibilities, team size, budget, venue, certification body, GPA, honors…), and the semantic rules in §20.4 (`Value types match predicate contracts`, `Verified skills have eligible supporting facts`) are unenforceable until the contracts exist. The code-based mechanism is fine for *enforcement*; the catalog is needed for *reviewability*.
- **Correction:** Add a §10.4 table enumerating the initial closed predicate set (≥15–20 entries spanning the entity types), each row declaring legal entity types, value types, minimum evidence basis, allowed surfaces, single/multi-valuedness, and whether the predicate can ground a skill. The same table must define the skill `category` vocabulary.

### MAJOR

**3. `evidence_set_digest` scope, dedupe, and path base ambiguous**

- **§7, lines 196–198**.
- **Evidence:** "computed independently from normalized `evidence/records.yaml` plus the relative paths and raw-byte digests of every referenced blob." The §6 layout (lines 122–123) has exactly one evidence file, which mostly resolves "referenced by what", but the spec never states that evidence records cannot appear in other files, and two sub-ambiguities remain: (a) set-vs-multiset semantics when two records reference the same blob (the path+digest pair appearing twice changes the hash of the sorted sequence), and (b) the relative-path base (see finding 1c).
- **Why it matters:** The digest's guarantee — "self-contained because every evidence record required by the active revision points to a blob inside this root" (lines 154–156) — is unverifiable if implementations enumerate blobs differently.
- **Correction:** State: "every blob referenced by any `capture.sha256` in any evidence record in any YAML file of the revision tree; each blob path+digest pair appears exactly once (deduped) in the sequence; paths are bundle-root-relative."

**4. Revision number has three competing sources of truth, plus undefined interrupted-promotion numbering**

- **§6 lines 136–148** (directory prefixes `000001-`, `000002-`), **§7 line 173** (`revision: 2`), **§17 line 600** (ledger `revision: 2`).
- **Evidence:** §17 line 614 validates ledger↔manifest agreement; nothing validates the directory prefix against either. Also unspecified: after an interrupted promotion leaves a partial `revisions/00000N-…/` directory (the §21 line 766 guarantee only covers `CURRENT`), how does the next `promote` derive N — max-prefix+1 (gaps accumulate) or reuse (collision risk)?
- **Why it matters:** The design ties parent linkage and the ledger to `revision`, and calls it "monotonically increasing" (line 182), but no rule makes the three copies agree, so drift is undetectable.
- **Correction:** State that the directory prefix is the single source of truth; manifest `revision` and the ledger's final entry must equal it, enforced in §20.6 validation; specify next-N derivation as max existing numeric prefix + 1, with stray non-`CURRENT` directories reported by inventory.

**5. "Immutable" evidence is tamper detection without a recovery path**

- **§12 line 407** ("Evidence is immutable and self-contained"); **§20.3 lines 708–710**; **§21 line 767** ("Evidence or revision mutated after promotion → Digest failure; revision unusable").
- **Evidence:** Blobs are content-addressed (`blobs/sha256/<digest>`); mutation is *detected* but the only stated outcome is "revision unusable" — a single bit-flip in one blob makes the entire active revision unopenable, with no repair path in the design. §5 (line 101) mentions backup relocation but no restore procedure.
- **Why it matters:** The foundation of every verified fact becomes a single point of failure; "immutable" overpromises what is delivered (content-addressing + detection).
- **Correction:** Either downgrade the claim to "content-addressed with tamper detection" and add a §21 recovery row ("corrupted blob: restore from backup, or re-promote from draft"), or specify write-once enforcement (e.g., blobs created with read-only permissions, corruptions quarantined to `blobs/.trash/` rather than left in place) so detection never destroys the only copy.

**6. Skill supporting facts cannot distinguish implementation from incidental mention**

- **§14 lines 538–541**; **§20.4 line 727** ("Verified skills have eligible supporting facts").
- **Evidence:** §14 says supporting facts "may describe implementation, professional use, substantial coursework, publication work, or another explicit context; future projection policy can distinguish those contexts." But the fact schema (§10) carries no field for that distinction, and the predicate contracts (finding 2) are unspecified. A `technology_used` fact with basis `owner_attested` on a forked repo would satisfy today's rule as written — the §24 guarantee "Unsupported skills cannot be marked verified" (line 860) is hollow.
- **Why it matters:** The validator, not future projection policy, must enforce the skill-evidence gate; the information needed to do so must exist in the schema now.
- **Correction:** Either add a controlled `evidence_context` field to facts (`professional`, `academic`, `personal_project`, `contribution`, `incidental`) or require the predicate contracts (finding 2) to declare, per predicate, whether and in which contexts the fact can ground a skill, with §20.4 enforcing it.

**7. YAML normalization ignores parser dialect**

- **§7 steps 2–4, lines 188–193**; **§20.6 lines 747–752**.
- **Evidence:** The spec never names the parser. The repo pins `pyyaml>=6.0` (pyproject.toml line 45) and installs PyYAML 6.0.3 — YAML 1.1 semantics: `no`/`yes`/`on`/`off` parse as booleans, `2026-08-10` as a `datetime.date` (which then needs a defined JSON serialization), `0123` as octal-ish, `1.0` vs `1` as distinct types. The canonical-JSON step therefore depends on the dialect and on how non-string scalars are serialized; the design's own examples mix quoted and unquoted dates.
- **Why it matters:** The "same logical content → same digest" guarantee must hold across machines and environments (a bundle created on one host validated on another); two parsers/serializers yield different digests for identical YAML.
- **Correction:** Pin "PyYAML 6.x (`yaml.safe_load`) with YAML 1.1 semantics", define the canonical JSON encoding of `date`/`datetime`/int/float/bool scalars, and mandate quoting rules in the authoring contract (dates, strings that look like booleans/numbers). Add the edge-case test set (item 3 in Missing acceptance tests below).

**8. Import idempotency's "captured digest" is not storable in the fact schema**

- **§18 line 638** vs **§10 lines 292–295**.
- **Evidence:** "Re-import is idempotent by source locator, captured digest, and candidate record ID." The `import_lineage` mapping (lines 292–295) has only `source_system`, `source_locator`, `notes` — no digest field. Without a stored digest of the upstream source at import time, a changed value under an unchanged locator is indistinguishable from "already imported".
- **Why it matters:** The idempotency guarantee (a Gate A criterion, line 814) and the §21 row "Changed import source → New candidate" are unenforceable as specified.
- **Correction:** Add `source_content_digest: str | None` to `import_lineage`; the skip rule becomes same locator + same digest + same candidate ID; different digest → new candidate.

**9. Draft manifest digest state is undefined**

- **§19 lines 657–671** (`checkout`, `validate --draft`, `promote`); **§20.6 lines 746–752**.
- **Evidence:** §20.6 requires "The computed bundle and evidence digests match the manifest." A draft is a logical tree containing `manifest.yaml` — whose `bundle_digest` cannot equal the draft's own computed digest unless some placeholder convention exists. The spec never states what value a draft's manifest carries, nor whether `validate --draft` skips digest-match checks, nor whether `promote` rewrites the manifest (including `revision`, `created_at`, `change_id`) before hashing. An LLM author (the §19 contract) cannot know what to write.
- **Why it matters:** The core authoring loop (checkout → edit → validate → promote) is unexecutable as specified; validate on a draft and validate on a revision must have defined, different digest semantics.
- **Correction:** Specify: `checkout` writes the draft manifest with `bundle_digest: ""` (and a `draft_of_revision` marker); `validate --draft` skips only digest-match checks; `promote` recomputes revision/`change_id`/`created_at`, rewrites the manifest, then verifies the digest from disk exactly as §19 says.

**10. Change ledger "append-only" has no mechanical enforcement**

- **§17 lines 614–618**; **§20.6 lines 748–750**.
- **Evidence:** `history/changes.yaml` lives inside each revision tree (lines 130–131), so revision N's tree carries the full ledger through N. The only stated checks are "final entry matches the manifest revision, `change_id`, and parent digest" (line 614) and the parent digest exists in the preceding revision (line 750). Nothing requires revision N+1's ledger to be a strict prefix-extension of N's — a promotion that silently dropped an old ruling or change record would validate.
- **Why it matters:** "Append-only" is a headline guarantee of the review brief; without the prefix rule it is aspirational convention, and the ledger is the program's audit trail for owner rulings.
- **Correction:** Add a §20.2/§20.6 rule: "the active revision's ledger must contain the parent revision's ledger verbatim as a prefix" — mechanically checkable and cheap.

**11. `role_families` vocabulary is neither enumerated nor bound to the live closed catalog**

- **§14 lines 529–531** (`role_families: [backend, systems]`); **§15 line 561** (`role_families: [backend]`).
- **Evidence:** The live closed catalog is `ROLE_FAMILIES` in `src/boardwatch/extract/role_family.py` (lines 11–44): mobile, security, devops_sre, data_eng, ml_ai, fullstack, frontend, backend, plus fallback general_swe (`VALID_ROLE_FAMILIES`, persona.py line 34). "systems" is not in it. The design neither binds its `role_families` values to this catalog nor enumerates its own — while §14 line 543 explicitly says the phase "does not change Boardwatch's JD taxonomy."
- **Why it matters:** Skills and claims carry a role-family field validated against an undefined vocabulary; the synthetic example itself would fail validation against the live closed set, so Gate A fixtures cannot be written until the vocabulary is decided.
- **Correction:** State that bundle `role_families` draws from a new closed catalog (e.g., the live set plus explicit additions such as `systems`), enumerate it, and validate against it — or reuse `VALID_ROLE_FAMILIES` and change the example.

### MINOR

**12. Evidence-class catalog versioning policy undefined** — **§12 lines 407–415**; `schema_version` at line 172. Adding a *new* class never invalidates *old* bundles (they only contain old values); the real risk is a new bundle read by an old validator, which is what `schema_version` exists for. **Correction:** define what bumps `schema_version` (any enum/catalog addition does) and require validators to report "bundle schema_version newer than validator" as a typed error rather than a generic unknown-enum failure.

**13. Metric `caveats` have no structure** — **§11 lines 392–393**: `caveats: list[str]` free text. Downstream (human or LLM) cannot mechanically distinguish "annotate" from "suppress this metric". **Correction:** optional `severity` per caveat (`informational` | `context_required` | `disqualifying`), or a one-line statement that this is a deliberate projection-phase deferral.

**14. Bundle lock mechanism and stale-lock recovery unspecified** — **§19 lines 669–671** ("promote acquires the exclusive bundle lock"); **§21 line 766**. A dead process holding the lock blocks all future promotions; §21's interrupted-promotion guarantee doesn't cover it. **Correction:** advisory lockfile carrying PID + timestamp, with a rule that a lock held by a non-running PID (or older than N minutes) may be broken.

**15. No coexistence statement for `boardwatch career` vs `boardwatch tailor`** — **§19 lines 655–668**; live `src/boardwatch/cli/tailor_cmd.py` (462 lines, `tailor init/validate/run/rewrite` on `{config_dir}/resume.yaml`). §3 line 45's non-goal implies tailor keeps working, but the spec never says so. **Correction:** one sentence: during Gate A/B, `tailor` continues to read `resume.yaml`; the bundle→`Resume` bridge is the later design (§4.2); Gate B does not require deleting or replacing `resume.yaml`.

**16. Orphaned blobs accumulate with no retention policy** — **§6 lines 200–202**; **§21 lines 769–770**. Inventory reports, never deletes; every evidence replacement adds an orphan forever. **Correction:** either a documented manual drain (`career gc --older-than N --dry-run`, still never automatic) or an explicit "known deferred item" line.

**17. `owner_protected` is undefined** — **§11 line 394**, the only occurrence in the document. A boolean with no stated semantics (never shown? shown only on owner review?) cannot be validated or honored. **Correction:** define it in §11 (e.g., "metric may not be projected without an explicit owner re-confirmation") and add it to §20.4's metric checks.

**18. Gate B's "clean … completeness report" is undefined** — **§23 line 832** vs **§20.5 lines 732–744**. §20.5 says a bundle "may validly preserve uncertainty while being incomplete for downstream use" and splits errors/blockers/warnings; Gate B requires "a clean validation and completeness report" while also requiring unresolved conflicts to remain represented (line 825). "Clean" cannot mean zero blockers. **Correction:** define "clean" as "zero errors; blockers limited to explicitly-accepted unresolved conflicts; warnings reported", and say so in §23.

**19. Claim `character_count` is stored but unvalidated** — **§15 line 567**; §20.4's claim checks (lines 728–729) don't include it. A field that can drift from `text` without detection is exactly the "aspirational rather than executable" class the review brief targets. **Correction:** either validate `character_count == len(text)` (with the counting rule stated) or drop the field until the layout gate needs it.

## Missing acceptance tests

The §22 groups are strong; the following guarantees have no test group:

1. **Parent-digest chain integrity across ≥3 revisions** (§7/§20.6): create three revisions, assert each `parent_bundle_digest` equals the actual predecessor digest; break the chain and assert failure. Group 12 covers stability, not chaining.
2. **Read-lock vs promotion concurrency** (Group 15 covers "concurrent readers" but not the interaction): readers under the read lock observe either the complete old or complete new revision, never a partial replace, while promotion proceeds.
3. **Digest determinism over YAML edge cases**: `no`/`yes`/`on`/`off` as quoted strings, unquoted `2026-08-10` (date object), `0123`, `1.0` vs `1`, duplicate mapping keys, anchors/aliases — both "formatting-neutral" and "semantic change" directions. Group 12 doesn't enumerate the quirks.
4. **Blob present but `capture.sha256` mismatched** — a data-entry error, distinct from Group 4's tampering test (which mutates the blob).
5. **Exhaustive closed-catalog round-trips**: for *every* enumerated catalog (entities, statuses, states, bases, surfaces, qualifiers, evidence classes/directions, claim statuses, ruling decisions, actors), an out-of-catalog value is rejected. Groups 1–2 imply this; make it explicit.
6. **Revision-number consistency** (finding 4): directory prefix, manifest `revision`, and ledger final entry must agree; each pairwise violation is detected.
7. **Ledger prefix-extension** (finding 10): N+1's ledger containing N's ledger minus one entry must fail validation.
8. **Draft digest semantics** (finding 9): a draft with placeholder `bundle_digest` validates under `validate --draft`; promote rewrites and verifies the real digest from disk.
9. **Self-reference sentinel** (finding 1): changing only the stored `bundle_digest` value (keeping everything else identical) leaves the recomputed digest unchanged — proves the exclusion rule.
10. **Blob-reference dedupe** (finding 3): two records referencing one blob produce the same `evidence_set_digest` as one record referencing it.
11. **role_family closed-catalog binding** (finding 11): skills/claims reject out-of-catalog families; the synthetic fixtures validate against the chosen catalog.

## Scope assessment

- **Cleanly stops before tailoring:** Yes. §3 non-goals, §4.2's boundary, and §15's "stores candidates, defers selection/composition/judging" draw the line correctly; claim `allowed_surfaces` and `character_count` are storage-only and harmless. Nothing in the design composes prose at runtime.
- **Generalized mechanism vs private content:** Yes. §5 defaults the bundle outside the repo (consistent with the platformdirs precedent in `core/settings.py`), the repo gets only schema/CLI/synthetic fixtures, and Gate A (line 817) and §22 item 16 route privacy enforcement through the existing `tools/generalization` checker. One check on Gate B's side: the "import or explicitly excluded with a reason" criterion (line 824) is auditable, not mechanical — acceptable for an owner gate.
- **Gate A / Gate B decomposition:** Appropriate. Gate A's eight criteria are all mechanical and independently executable on synthetic data; Gate B is private, owner-driven, and starts only after A is reviewed. The only measurability defect is finding 18 ("clean completeness report" undefined). Gate B's qualitative clauses ("every known conflict is represented") are audit-lists, not measurements — correct for an owner gate, and the design says so.

## Strongest counterargument

**Git already implements most of the revision machinery this design rebuilds.** The model — immutable content-addressed snapshots, parent pointers, append-only history, tree-of-blobs storage, atomic pointer promotion, corruption detection — is a bare Git repository. Using a bare repo as the bundle store would give `CURRENT` (ref/`HEAD`), revision layout (`git checkout`), content addressing (`git hash-object`), chain integrity (commit DAG), the change ledger (`git log`), and atomic promotion (`git commit`) for free, leaving only the domain layer (typed schemas, predicate contracts, conflicts/rulings, metric protection, the CLI) to build — which is the bulk of the actual work anyway. The counterargument fails where the design's *core differentiators* live: Git hashes raw bytes, so two logically identical YAML files with different formatting produce different identities, which directly contradicts the design's "formatting never matters" digest guarantee; blob dedup across revisions is user-visible content addressing here but an internal packfile detail in Git; and Git brings no conflict/merge semantics for the domain-level conflicts this design manages (it would actively fight the "preserve contradictions" goal with merge machinery). The design should nonetheless acknowledge it is reimplementing a subset of Git's object model and justify the bespoke cost — the justification exists (normalized digests + domain conflicts), but it is not stated.

## Recommendation

**Revise before implementation planning.** The two blocking findings (digest self-reference, missing predicate catalog) prevent a correct implementation, and findings 4, 8, 9, and 10 are one-line additions that close genuine executable gaps. Nothing found requires re-architecting: the bundle model, the revision scheme, the Gate A/B split, and the privacy boundary are sound. After the revision, the strongest remaining risk to watch at implementation time is digest determinism (findings 1, 3, 7) — it is the guarantee every other guarantee hangs off, and it is the one most likely to pass its own tests while failing cross-environment reproducibility.
