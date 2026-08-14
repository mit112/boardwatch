# Gate B candidate extraction — design

**Status:** revision 2. Externally reviewed once, verdict NOT READY; four of six findings applied here, two
are owner decisions in §9. No code written.
**Date:** 2026-08-14.
**Supersedes nothing.** Narrows D-170 ruling 1; see §7.

**What revision 1 got wrong, kept visible on purpose rather than quietly edited out:**

| # | Revision 1 claimed | Actually |
|---|---|---|
| 1 | skill candidates carry an evidenced-vs-`incidental` context | **False.** `CandidateRecord` has no `usage_context`, subject, verification state, evidence or surfaces (§6.4). That is a fact-layer property this design never reaches |
| 2 | `review_required` "is exactly that visibility" | **A quarantine with no drain**, violating the house rule that a drain is designed in the same change. Four distinct causes were indistinguishable (§6.3a) |
| 3 | Slice A's gate | Proved the catalog was *present*, never *audited* — its central claim. Replaced with invariants that fail on today's catalog (§5) |
| 4 | admitting `incidental` because it revives a dead guard | **Unsound ordering.** A dead check can mean an obsolete rule; the reason is semantic (§5) |

Finding 1 (extraction coverage can masquerade as owner disposition) is **not fixed here** — it needs a
definition the owner owns. §7a states what the design commits to regardless, and §9.2 the recommendation.

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
| D4 | **All 58 skill items become candidate assertions, not exclusions.** Nothing is written off. The evidenced-versus-familiarity distinction is **NOT** recorded at this layer — see §6.4; that was a false claim in revision 1. |
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

- **Admit `incidental` on `technology.used`'s `legal_usage_contexts`.** The justification is **semantic, not
  mechanical**: familiarity without substantive use is a legitimate state in any user's career, it must
  remain *effective* (storable, and eligible to reach a surface), and it must never be able to ground
  verification. That is exactly what `incidental` means, and no other context expresses it. Grounding stays
  clean because `grounding_facts` already excludes `incidental` — such a fact is storable and renderable and
  still cannot ground.

  **That `effective.py:220`'s guard becomes reachable is a consequence, not the reason.** Revision 1 argued
  it the other way round, which is unsound: a dead check can equally mean an obsolete rule, and
  reachability alone can never justify widening a contract shipped to every user. The test that follows
  from this must assert the semantic requirement (an `incidental` `technology.used` fact is accepted and
  does not ground), not merely that a branch is exercised.

*Alternative rejected:* a separate `technology.familiar` predicate with `may_ground_skill: false`.
Semantically tidier, but it leaves `effective.py:220` dead, doubles the technology vocabulary, and forces
every consumer to know both spellings.

The remaining 40 rows need reading before they ship — their `minimum_evidence` and `expiry` rules were
written to demonstrate the schema and would silently become policy for every user. **This audit is work,
not a formality**, and its findings are not predictable from here.

**Gate for Slice A.** Revision 1's gate — 41 rows exist, one predicate is accepted, a bad version exits 3 —
proved only that the catalog is *present*, while Slice A's central claim is that it was **audited**. It could
have shipped unaudited universal policy with the gate green. Replaced with:

*Mechanical, and derived from the defect actually found — each of these would have failed on the example
catalog as it stands:*

1. **No dead enum member.** Every `UsageContext`, `Surface` and `VerificationBasis` member is admitted by at
   least one predicate. `incidental` is admitted by **0 of 41** today, so this fails now.
2. **No unreachable guard.** For every predicate with `may_ground_skill: true`, `incidental` is in
   `legal_usage_contexts` — otherwise `effective.py:220`'s exclusion can never fire. Fails now.
3. **Semantic, not branch-based:** an `incidental` `technology.used` fact is accepted and does **not** ground
   a skill; a `professional` one does.
4. **No accidental rows.** Every predicate is either reachable from a v1 adapter mapping (§6.2) or listed in
   an explicit `unused_by_v1_adapters` declaration. 30 of the 41 are unused by this résumé and must be
   *declared* unused rather than merely present.
5. Version handling: a recorded version outside `SUPPORTED_CATALOG_VERSIONS` exits 3, per `secret_scan`.

*Non-mechanical, and honestly labelled:* "these rows were read" cannot be proven by a test. The gate is
therefore a **recorded per-row account** — for each of the 41, either "unchanged from the example, reviewed"
or a stated change with its reason — carried in the decision entry. Invariants 1-4 catch the *class* of
defect that the unaudited catalog actually contained; they do not substitute for reading the rows.

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
exception — a single bad proposal must not abort a batch.

### 6.3a The drain, which revision 1 omitted

Revision 1 called `review_required` "exactly that visibility" and stopped. That breaks the house rule that
**every quarantine needs a drain designed in the same change**, and it is wrong on the facts:
`SourceLedgerRecord` carries `disposition` and `candidate_ids` and **no reason field**
(`models/imports.py:99-125`), while `ExclusionRecord` *does* carry `reason` and `rationale`. So the ledger
records only that a record awaits review — span failure, absent mapping, unparsable value and deliberate
non-assertion are indistinguishable, and three of the four had no route out.

**The reason is recorded outside the bundle, not in the ledger.** Adding a field to `SourceLedgerRecord`
would bump the schema and give the ledger a second source of truth about disposition. Instead `extract`
emits a report — the `--json` shape every other command already has — naming every enumerated record it
produced nothing for, from a **closed** reason catalog. Out-of-catalog is a failure, never a new bucket.

| Reason | Meaning | Drain |
|---|---|---|
| `no_mapping_for_locator` | the locator shape has no predicate in the mapping | extend the mapping data (§6.2), re-extract |
| `span_not_grounded` | the display value is not in the record's bytes | **a defect signal, not owner work** — the extractor or mapping is wrong; fix and re-extract |
| `value_not_typeable` | e.g. a date string the parser cannot type | agent lane, or the owner corrects the source |
| `free_text_deferred` | prose needing judgement — the 2 education lines | Slice C |
| `no_predicate_exists` | nothing in the catalog can express it — the header email | **owner decision**: add a predicate, or exclude with a reason |

Two properties this buys. `span_not_grounded` is separated from owner work, so a mapping bug cannot hide in
a pile that looks like a to-do list. And re-extraction is safe by construction: identity is derived, so a
re-run over corrected material produces the same IDs and no duplicates (`imports.py:1-21`).

**The report is the drain's instrument, so it is part of Slice B, not a follow-up.** A record whose reason is
absent from the report is itself a finding — that is the check that keeps the bucket from silently growing.

### 6.4 The skill items, and the layer this design does NOT reach

All 58 become `technology.used` **candidate assertions**. Nothing is excluded.

**What a candidate cannot carry, and revision 1 wrongly claimed it did.** `CandidateRecord` holds
`candidate_id`, `source_record_id`, `predicate`, `canonicalized_typed_value`, `original_display_value`,
`occurrences` — and nothing else (`models/imports.py:191-211`). There is **no** subject, **no**
`usage_context`, **no** `verification_state`, **no** `verification_basis`, **no** `evidence_ids`, **no**
`allowed_surfaces`, and no acceptance flag. Those all live on `FactRecord` (`models/facts.py:160-182`).

So revision 1's claim that context "comes from the entry the skill is evidenced by, otherwise `incidental`"
was **false at this layer**, and so was "the difference is recorded." The evidenced-versus-familiarity
distinction is a **fact-layer** property. Extraction cannot express it, and this design does not reach it.

**What that means concretely, stated so no plan built on this can assume otherwise:**

- Slice B produces candidate assertions. It creates **no** `FactRecord`, **no** `SkillRecord`, **no**
  entity, and **no** evidence. Nothing it produces is renderable, and it should not be — the résumé reads
  `SkillRecord`s via `{config_dir}/projection.yaml` (§10).
- A `technology.used` candidate's value is `{type: skill_ref, skill_id: …}` naming a skill that **need not
  exist**, and **nothing validates that reference**. Verified: the import validators cover identity,
  naming, scope, locator shape, one-record-per-unit, exclusion agreement, imported-names-candidates,
  undispositioned records and never-enumerated sources (`validation/imports.py`) — **none** checks a
  candidate's `skill_id` against the skill inventory. Referential validation covers canonical facts only.
  This is a real gap and it is **out of scope here**; a later slice owns it.
- **The promotion slice this design does not write is where the semantics live.** It creates subjects,
  facts, skill records, contexts, verification state, evidence and surfaces, and it is the only place the
  familiarity distinction can be recorded. It must exist before any skill from this source reaches a
  résumé. Naming it is a prerequisite of planning, not of this document.

The mutual reference that slice will need: a `technology.used` **fact** carries `{type: skill_ref,
skill_id: …}` while the `SkillRecord` names that fact in `supporting_fact_ids` (`min_length=1`,
`skills.py:45`). The packaged example does exactly this (`skill.example-language` ↔
`fact.packet-pantry.language.001`), so mutual reference is normal and validated over the final state rather
than in creation order.

### 6.5 The command

`profile-bundle extract --draft NAME --source SOURCE_ID`, writing `imports/candidates.yaml` (D3) and then
re-deriving `imports/source-ledger.yaml` through the existing `build_source_ledger`, so the two documents
are never left disagreeing. That is **two document writes**, which D-137 already rules cannot be made
atomic — reuse `PARTIAL_EDIT_APPLIED` rather than inventing a second answer.

**Import wall:** `cli/profile_bundle_cmd.py` must transitively import no `boardwatch.store` module, checked
in a fresh interpreter via `sys.modules`. Four such walls exist across three test files and no document
enumerates them (D-161, D-162). **Grep `tests/` for what constrains this package's imports before wiring in
a new module** — a symbol check cannot find a prohibition.

**Gate for Slice B.** Revision 1 had none worth the name: derived disposition passes the moment every record
carries *any* syntactically valid candidate, so extraction coverage would have read as success.

1. **Per-locator-class semantics, not just validity.** For each of the five buckets, the candidate carries
   the *expected* predicate and the expected value type — a bullet under an `experience` entry yields
   `employment.accomplishment`, under a project yields `project.contribution`. A test that only asserts "a
   candidate exists" passes on a mapping that assigns every record the same wrong predicate.
2. **Grounding is falsifiable in both directions.** A record whose display value is present grounds; one
   mutated by a single character does **not**, and appears in the report as `span_not_grounded`. The
   uncollapsed-whitespace case gets its own test: a bullet with a double space must ground.
3. **Coverage is reported separately from disposition.** The gate asserts `imported + excluded +
   review_required == 81` *and* that the report accounts for every non-imported record. Extraction
   completeness and owner-accepted disposition are **never** read off the same number (§7a).
4. **Idempotence:** a second `extract` over unchanged material writes no byte and adds no candidate.

## 7. What this narrows, and what it does not touch

D-170 ruling 1 says candidates stay owner-authored. Its stated reason was *"It cannot: no extractor
exists."* That reason expires here, so D3 narrows the ruling rather than relitigating it — **and owes its own
decision entry.** What survives unchanged: identity is derived not proposed; disposition is derived from
candidates and exclusions, never carried over; scope is reused, never widened; the splice is in place.

Out of scope: promotion, facts, entities, evidence, conflicts. Extraction produces candidates only.

## 7a. Extraction coverage is not owner disposition

`build_source_ledger` derives `imported` from the mere presence of a candidate (`imports.py:430-452`), and
`SourceLedgerRecord` requires an `imported` record to name one (`models/imports.py:108-125`). Under D3 the
extractor writes candidates directly, so **a deterministic extractor that emits something for every mapped
locator drives `review_required` to zero by itself.** If Gate B is read off that number, it measures
extractor coverage and calls it owner disposition.

This design does **not** resolve that by itself, because the resolution is a definition the owner owns
(question 2). What it does commit to:

- **The two quantities are never reported as one number.** The `extract` report states records-with-candidates
  separately from records the owner has accepted, and Slice B's gate asserts both (§6.5).
- **The recommended resolution needs no new document and no reversal of D3.** An owner-acceptance boundary
  already exists: `approve` runs on a controlling terminal and binds to the draft's exact content digest, and
  `promote` is refused without a matching stamp. Machine-written candidates therefore already require an
  owner approval *before they can become a revision*. Binding Gate B to a promoted revision uses that
  boundary instead of inventing an acceptance file — which is what D3 declined.
- What this cannot do is make approval mean the owner *read* all 81 candidates. No mechanism in the bundle
  does that for any document; approval means "I approve this exact content."

## 8. Slice C — the agent lane (declared, not decomposed)

Only the 2 education lines need it, so it is deliberately last and the bundle is useful without it — those
records simply stay `review_required`. The shape to follow is the existing subscription-tier handshake:
request JSON → agent fills → verify and ingest, with the rule from `tailor/rewrite/agent_lane.py:61` that
`a_text` is re-derived authoritatively and the agent's copy is **never** trusted. Under D2 that rule is
already structural: an agent proposal whose span is not in the record's bytes produces nothing.

## 9. Open questions

**Two are owner decisions and block planning. They are not deferrable to implementation.**

1. **Where the locator→predicate mapping lives** (§6.2) — `SourceSpec` field versus package-data resource.
   This is the multi-tenancy boundary, not a detail: it decides version binding, override behaviour, and
   whether a historical revision can reproduce the mapping it was built under. **Recommendation:
   `SourceSpec`**, because package data is not versioned with the bundle and a past revision could then not
   be reproduced from the bundle alone. Cost: a schema bump.
2. **What Gate B is, precisely, and what it is bound to** (§7a). Today it is *"a real person's canonical
   baseline, and the bundle-to-`Resume` bridge"* (`docs/profile-bundle-authoring.md:18-22`) — no number, no
   procedure. **Recommendation: bind it to a promoted revision**, so the existing `approve` step is the
   owner-acceptance boundary.

*Not blocking:* whether `header/2` (an email) argues for a contact predicate or is correctly left
undispositioned as `no_predicate_exists` (§6.3a).

## 10. What must not be re-derived

- The renderer never reads `Resume.header` or `Resume.education` (D-156), so those buckets cannot change a
  PDF regardless of how they are dispositioned.
- Projection filters skills on `allowed_surfaces` alone — **not** `verification_state`, **not**
  `usage_context` (`projection/contract.py:28-42`). So even once the promotion slice records the evidence
  distinction, **nothing downstream reads it**; and a skill in an unavailable state still renders. A separate
  pre-existing gap, not this design's to close. (Revision 1 said "the evidence distinction this design
  records" — this design records no such thing; see §6.4.)
- The résumé's skills section is assembled from `{config_dir}/projection.yaml`, the owner's editorial file
  naming bundle skill ids (`projection/pool.py:145-151`), so the owner retains explicit curation.
