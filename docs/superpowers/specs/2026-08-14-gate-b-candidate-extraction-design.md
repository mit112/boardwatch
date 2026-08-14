# Gate B candidate extraction — design

**Status:** design, awaiting owner review. No code written.
**Date:** 2026-08-14.
**Supersedes nothing.** Narrows D-170 ruling 1; see §7.

Every claim below carries a `file:line`. Claims I did not verify are marked **UNVERIFIED**.

---

## 1. What exists, and the one thing that does not

`profile-bundle import` (D-170) enumerates a source into `imports/source-ledger.yaml` and nothing else.
Disposition is derived, never authored: a record with candidates is `imported`, a record the owner excluded
is `excluded`, everything left is `review_required` (`imports.py:430-452`).

So the ledger is reachable and **candidates are not**. `build_candidate_package` takes `proposals`
(`imports.py:221-270`) and **nothing in `src/` constructs a `ProposedCandidate`** — the only two
construction sites in the repository are in `tests/profile_bundle/test_profile_bundle_import_idempotency.py`
(:317, :388). No record can reach `imported`, so Gate B's "zero undispositioned records"
(`docs/profile-bundle-authoring.md:1151`) cannot be met at all.

A proposal is small:

```python
@dataclass(frozen=True)
class ProposedCandidate:          # imports.py:205-218
    source_record_id: str
    predicate: str
    value: FactValue
    original_display_value: str
    proposed_candidate_id: str | None = None   # "accepted and discarded"
```

Identity is derived by the importer, never proposed: `candidate.<64hex>` from
`source_record_id | predicate | canonicalized_typed_value` (`imports.py:1-21`). **That half of the design is
already built and tested.** This document is only about what fills those four fields.

## 2. Two prerequisites no document names

Both are absences, found by reading code rather than docs.

### 2.1 A fresh bundle has an empty vocabulary

`init_draft` writes `{predicates_version: 1, predicates: []}` (`drafts.py:361-363`). The only predicate
catalog in the repository is the 41-entry **example** at
`examples/comprehensive/policy/predicates.yaml` (1,240 lines). `build_candidate_package` raises
`CandidateImportError(f"unknown predicate {…!r}")` for anything out of catalog (`imports.py:239-241`).

**So on a real bundle, extraction can produce zero candidates until a catalog exists.** Hand-authoring 41
`PredicateSpec` rows — 15 fields each, with `_verification_bases_need_evidence_routes` cross-checking
`legal_verification_bases` against `minimum_evidence` (`policy.py:161-174`) — is a larger transcription
burden than the 81 ledger rows D-170 just removed.

### 2.2 The shipped catalog forbids a keyword-only skill

Measured over `examples/comprehensive/policy/predicates.yaml`:

| Measure | Value |
|---|---|
| Predicates with `may_ground_skill: true` | **1 of 41** — `technology.used` |
| Predicates admitting `usage_context: incidental` | **0 of 41** |

`technology.used` admits `professional, academic, personal_project, contribution, publication, volunteer`
— not `incidental`. Two consequences:

1. **A familiarity-level skill is not expressible.** Every `technology.used` claim must assert one of six
   substantive contexts, so the owner must overclaim or omit. The owner has stated that the skills section
   deliberately carries some unbacked entries for JD keyword coverage; as shipped, the catalog prohibits
   recording that honestly.
2. **`effective.py:220`'s grounding guard can never fire.** `grounding_facts` requires
   `may_ground_skill` and `usage_context != INCIDENTAL` (`effective.py:198-227`), but the only
   `may_ground_skill` predicate forbids `incidental` outright. A check that cannot fire reads as coverage
   while providing none.

## 3. A correction this design records

`models/skills.py:3-6` says a skill's authority is derived from entity-bound facts and that *"Naming a
skill in an old résumé, a generic skills list, a course catalog, or a job description supports nothing."*

**That is a statement about authority, not admissibility.** It means such naming cannot make a skill
`verified`. It does **not** mean the skill may not exist, or may not render. An earlier reading of it as a
prohibition led to a recommendation to exclude all 58 of the résumé's skill items, which would have been
wrong twice over:

- The machinery for an owner-asserted skill is already built and legal — `VerificationBasis.OWNER_ATTESTED`
  (`base.py:309`), `VerificationState.OWNER_CONFIRMED`, and `EFFECTIVE_STATES = {VERIFIED,
  OWNER_CONFIRMED}` (`base.py:331-333`), with `_owner_attestation_is_permitted` capping an owner-attested
  fact at `owner_confirmed` (`validation/semantic.py:294-324`). `technology.used`'s catalog row lists
  `classes: [owner_attestation]` as a standalone `minimum_evidence` alternative, so the owner's word alone
  is sufficient.
- Excluding them would emit a **visibly empty section**. `render/latex.py:126-136` writes
  `\section{Skills}` unconditionally; with no groups the body is `""` and the heading renders over an empty
  block.

## 4. Decisions taken by the owner

| # | Decision |
|---|---|
| D1 | **Deterministic first, agent lane only for free text.** The structured buckets map mechanically; prose does not. |
| D2 | **Strict span grounding.** `original_display_value` must occur in the record's own bytes. If it does not, no candidate is produced and the record stays `review_required` — the `INELIGIBLE`-needs-a-quoted-span rule, one layer up. |
| D3 | **One step.** The extractor writes `imports/candidates.yaml` directly; no separate owner-accept file. |
| D4 | **All 58 skill items become claims, not exclusions.** Nothing is written off; the evidenced/unevidenced difference is recorded instead. |
| D5 | **Ship a starter predicate catalog as package data, audited before shipping** — rather than making catalog authoring the owner's Gate B work. |

## 5. Slice A — the seeded predicate catalog

**Reuses an exact precedent rather than inventing one.** `policy/secret-scan.yaml` is already the declared
exception to "empty": `_empty_documents` seeds it from `secret_scan.builtin_ruleset(CURRENT_RULESET_VERSION)`
(`drafts.py:321-329`), because *"an empty ruleset would make the first revision claim a scan it never ran."*
The same argument holds for predicates: an empty vocabulary makes a bundle claim a denominator it can never
disposition.

Shape, mirroring `secret_scan.py:169-180`:

- `BUILTIN_PREDICATE_CATALOGS: Mapping[int, PredicateCatalog]`, `SUPPORTED_CATALOG_VERSIONS`,
  `CURRENT_CATALOG_VERSION`.
- `builtin_catalog(version) -> PredicateCatalog`, raising `UnsupportedPredicateCatalogError` for an
  unavailable recorded version so a caller turns it into **exit 3** rather than reporting a clean catalog it
  does not have.
- `_empty_documents` calls it **at call time, not bound at import** — the reason `drafts.py:326-329` gives
  for secret-scan, and the reason a by-name import snapshots a version set.

**Content: the example's 41 rows, moved and audited — not copied.** The audit is the point of D5, and it has
one mandatory finding already:

- **Admit `incidental` on `technology.used`'s `legal_usage_contexts`.** This makes a familiarity-level claim
  expressible, and simultaneously makes `effective.py:220`'s guard reachable, so the rule that an incidental
  fact cannot ground a skill starts doing real work. Grounding semantics stay clean because
  `grounding_facts` already excludes `incidental` — an incidental `technology.used` fact is storable,
  effective and renderable, and still cannot ground.

*Alternative rejected:* a separate `technology.familiar` predicate with `may_ground_skill: false`.
Semantically tidier, but it leaves `effective.py:220` dead, doubles the technology vocabulary, and forces
every consumer to know both spellings.

The remaining 40 rows need reading before they ship — their `minimum_evidence` and `expiry` rules were
written to demonstrate the schema and would silently become policy for every user. **This audit is work,
not a formality**, and its findings are not predictable from here.

**Gate for Slice A:** a fresh `profile-bundle init` produces a bundle whose `policy/predicates.yaml` holds
`CURRENT_CATALOG_VERSION` and 41 rows; `build_candidate_package` accepts a proposal naming
`employment.title`; a recorded version outside `SUPPORTED_CATALOG_VERSIONS` exits 3.

## 6. Slice B — deterministic extraction, grounded

### 6.1 What each bucket yields

The `boardwatch-resume-v1` adapter emits five shapes (`enumerators.py:437-547`). Against the live
`resume.yaml` (81 records: header 2, education 2, skill-groups 58, entry metadata 6, bullets 13):

| Locator | n | `atomic_value` | Predicate(s) | Route |
|---|---|---|---|---|
| `entries/<id>/bullets/<id>` | 13 | `{bullet_id, text, tech_tags}` | `employment.accomplishment` / `project.contribution` by entry `kind` | deterministic |
| `entries/<id>/metadata` | 6 | `{entry_id, heading, kind, title, dates, subtitle, location}` | `employment.organization`, `.title`, `.date_range`, `entity.location` | deterministic; `dates` needs parsing |
| `skill-groups/<label>/<n>` | 58 | `{label, item}` | `technology.used` | deterministic (§6.3) |
| `education/<n>` | 2 | `str` | `education.institution` + `.credential` + `.field` | **agent lane** (Slice C) |
| `header/<n>` | 2 | `str` | `person.professional_name`; the email has no predicate | 1 deterministic, 1 stays `review_required` |

One record may yield several candidates — the model supports it (`SourceLedgerRecord.candidate_ids` is a
tuple) and entry metadata is the case that needs it.

### 6.2 The mapping is data, not code

A locator-shape → predicate table hard-coded in Python is the mistake CLAUDE.md names explicitly: when a
second user appeared in job-apps, the thing that failed to port was the taxonomy. **No locator → predicate
mapping exists anywhere today** (verified: `predicate_id` appears in exactly two source files,
`models/policy.py` and `imports.py`; `enumerators.py` never references it).

The mapping ships as versioned data keyed by adapter id, so a user whose career is not software supplies
their own without new code. **UNVERIFIED:** whether it belongs in `policy/sources.yaml`'s `SourceSpec` (no
new document, but a schema bump) or as a package-data resource beside the starter catalog. Resolve before
implementation — a new bundle document would break the closed 33-document grammar.

### 6.3 Grounding, per bucket

`atomic_value` is not uniformly a string, so the span check must target the specific field and **never**
`str(atomic_value)` — matching the whole dict would let a proposal match against a key name or the label.

| Bucket | Field the span must occur in |
|---|---|
| header / education | the value itself |
| skill-groups | `["item"]` — not `["label"]`, not the dict |
| entry metadata | the one field the predicate reads |
| bullets | `["text"]` |

**Load-bearing asymmetry:** the adapter does **not** whitespace-collapse bullet text — it preserves authored
bytes, unlike `tailor/model.py`'s `Bullet` (`enumerators.py:16-21`), while `canonicalize_candidate_value`
*does* collapse via `_collapsed` (`imports.py:141-147`). So the span check runs against the **raw** display
value and the canonical value is derived separately. Comparing a collapsed span to uncollapsed bytes
false-negatives on every wrapped bullet.

**Failure direction (D2):** ungrounded ⇒ produce no candidate and leave the record `review_required`. Not an
exception — a single bad proposal must not abort a batch, and the house rule is never to silently drop
without leaving the item visible. `review_required` is exactly that visibility.

### 6.4 The skill items

All 58 become `technology.used` claims. The context comes from the entry the skill is evidenced by, where
one exists; otherwise `incidental` (§5). A skill the bullets do evidence can later reach `owner_confirmed`
or `verified`; one that nothing evidences stays a recorded, renderable familiarity claim. **Nothing is
excluded and nothing is lost.**

Note the mutual reference this implies: a `technology.used` fact carries `{type: skill_ref, skill_id: …}`
while the `SkillRecord` names that fact in `supporting_fact_ids` (`min_length=1`, `skills.py:45`). The
packaged example does exactly this (`skill.example-language` ↔ `fact.packet-pantry.language.001`), so
mutual reference is normal and validated over the final state rather than in creation order.

### 6.5 The command

`profile-bundle extract --draft NAME --source SOURCE_ID`, writing `imports/candidates.yaml` (D3) and then
re-deriving `imports/source-ledger.yaml` through the existing `build_source_ledger`, so the two documents
are never left disagreeing. That is **two document writes**, which D-137 already rules cannot be made
atomic — reuse `PARTIAL_EDIT_APPLIED` rather than inventing a second answer.

**Import wall:** `cli/profile_bundle_cmd.py` must transitively import no `boardwatch.store` module, checked
in a fresh interpreter via `sys.modules`. Four such walls exist across three test files and no document
enumerates them (D-161, D-162). **Grep `tests/` for what constrains this package's imports before wiring in
a new module** — a symbol check cannot find a prohibition.

## 7. What this narrows, and what it does not touch

D-170 ruling 1 says candidates stay owner-authored. Its stated reason was *"It cannot: no extractor
exists."* That reason expires here, so D3 narrows the ruling rather than relitigating it — **and owes its own
decision entry.** What survives unchanged: identity is derived not proposed; disposition is derived from
candidates and exclusions, never carried over; scope is reused, never widened; the splice is in place.

Out of scope: promotion, facts, entities, evidence, conflicts. Extraction produces candidates only.

## 8. Slice C — the agent lane (declared, not decomposed)

Only the 2 education lines need it, so it is deliberately last and the bundle is useful without it — those
records simply stay `review_required`. The shape to follow is the existing subscription-tier handshake:
request JSON → agent fills → verify and ingest, with the rule from `tailor/rewrite/agent_lane.py:61` that
`a_text` is re-derived authoritatively and the agent's copy is **never** trusted. Under D2 that rule is
already structural: an agent proposal whose span is not in the record's bytes produces nothing.

## 9. Open questions

1. §6.2 — `SourceSpec` field or package-data resource for the mapping.
2. Whether the audit of the other 40 predicate rows produces findings that change Slice A's gate.
3. Whether `header/2` (an email) argues for a contact predicate, or is correctly left undispositioned.

## 10. What must not be re-derived

- The renderer never reads `Resume.header` or `Resume.education` (D-156), so those buckets cannot change a
  PDF regardless of how they are dispositioned.
- Projection filters skills on `allowed_surfaces` alone — **not** `verification_state`, **not**
  `usage_context` (`projection/contract.py:28-42`). So the evidence distinction this design records is not
  yet read by anything downstream. A skill in an unavailable state still renders; that is a separate
  pre-existing gap, not this design's to close.
- The résumé's skills section is assembled from `{config_dir}/projection.yaml`, the owner's editorial file
  naming bundle skill ids (`projection/pool.py:145-151`), so the owner retains explicit curation.
