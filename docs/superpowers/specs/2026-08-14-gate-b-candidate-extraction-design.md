# Gate B candidate extraction — design

**Status:** revision 4. Two external review rounds, both NOT READY. Round 2's findings are applied here,
including four defects that revision 2's *fixes* introduced. No code written. **One departure from D-172 is
proposed in §6.2 and needs the owner's veto or assent.**
**Date:** 2026-08-14.
**Narrows** D-170 ruling 1 (§7). **Amends** D-172 ruling 1 (§7a) and proposes amending ruling 2 (§6.2).

Every claim carries a `file:line`. Claims not verified are marked **UNVERIFIED**.

## 0. What earlier revisions got wrong, kept visible on purpose

A fix round is where this project has historically introduced its worst defects, so the record stays.

| Revision | Claimed | Actually |
|---|---|---|
| 1 | skill candidates carry an evidenced-vs-`incidental` context | **False.** `CandidateRecord` has no `usage_context`, subject, verification state, evidence or surfaces (§6.4) |
| 1 | `review_required` "is exactly that visibility" | A quarantine with no drain (§6.3a) |
| 1 | Slice A's gate | Proved the catalog *present*, never *audited* (§5) |
| 1 | `incidental` justified by reviving a dead guard | Unsound ordering; the reason is semantic (§5) |
| **2** | the report states "records the owner has accepted" | **False.** Approval is one revision-level digest decision, not a per-record count. Fixing a conflation introduced another (§7a) |
| **2** | re-extraction is safe, "the same IDs" | **False.** Identity includes predicate and value, so corrected material yields a *new* ID and the append-only merge keeps the old (§6.6) |
| **2** | grounding in "the record's own bytes" | **False.** `EnumeratedSourceRecord` keeps a parsed `atomic_value`; there is no byte substrate (§6.3) |
| **2** | Slice A invariant 4 (catalog reachability) | **Incoherent.** The catalog is package-wide, the mapping bundle-owned; nothing to check against (§5) |
| **2** | "a schema bump, affordable" | **Understated.** The loader and migrator are not version-dispatched (§6.7) |

---

## 1. What exists, and the one thing that does not

`profile-bundle import` (D-170) enumerates a source into `imports/source-ledger.yaml` and nothing else.
Disposition is derived: a record with candidates is `imported`, one the owner excluded is `excluded`,
everything left is `review_required` (`imports.py:430-452`).

So the ledger is reachable and **candidates are not**. `build_candidate_package` takes `proposals`
(`imports.py:221-270`) and **nothing in `src/` constructs a `ProposedCandidate`** — the only two construction
sites are in `tests/profile_bundle/test_profile_bundle_import_idempotency.py` (:317, :388). No record can
reach `imported`.

```python
@dataclass(frozen=True)
class ProposedCandidate:          # imports.py:205-218
    source_record_id: str
    predicate: str
    value: FactValue
    original_display_value: str
    proposed_candidate_id: str | None = None   # "accepted and discarded"
```

Identity is derived by the importer: `candidate.<64hex>` from
`source_record_id | predicate | canonicalized_typed_value` (`imports.py:1-21`). That half is built and
tested. This document is only about what fills those four fields, and what must exist around them.

## 2. Two prerequisites no document names

### 2.1 A fresh bundle has an empty vocabulary

`init_draft` writes `{predicates_version: 1, predicates: []}` (`drafts.py:361-363`). The only catalog in the
repository is the 41-entry **example** (`examples/comprehensive/policy/predicates.yaml`, 1,240 lines).
`build_candidate_package` raises on an out-of-catalog predicate (`imports.py:239-241`). Hand-authoring 41
`PredicateSpec` rows — 15 fields each, with `_verification_bases_need_evidence_routes` cross-checking
(`policy.py:161-174`) — is a larger burden than the 81 ledger rows D-170 removed.

### 2.2 The shipped catalog forbids a familiarity-level skill

| Measure | Value |
|---|---|
| Predicates with `may_ground_skill: true` | **1 of 41** — `technology.used` |
| Predicates admitting `usage_context: incidental` | **0 of 41** |

Two consequences: a familiarity-level claim is not expressible, so the owner must overclaim or omit; and
`effective.py:220`'s guard (`may_ground_skill` and `usage_context != INCIDENTAL`) **can never fire**.

## 3. A correction that governs the skills question

`models/skills.py:3-6` — *"Naming a skill in an old résumé, a generic skills list, a course catalog, or a job
description supports nothing."* **That is about authority, not admissibility.** It means such naming cannot
make a skill `verified`; not that it may not exist or render. Read as a prohibition it produced a
recommendation to exclude all 58 skill items, wrong twice: `VerificationBasis.OWNER_ATTESTED` and
`VerificationState.OWNER_CONFIRMED` are legal and `EFFECTIVE_STATES` contains both (`base.py:309, 331-333`),
capped at `owner_confirmed` by `validation/semantic.py:294-324`; and excluding them would make
`render/latex.py:126-136` emit `\section{Skills}` over an empty block.

## 4. Decisions taken by the owner

| # | Decision |
|---|---|
| D1 | Deterministic first, agent lane only for free text |
| D2 | **Strict grounding** — the display value must occur in the record's parsed atomic field (§6.3, restated from "bytes") or no candidate is produced |
| D3 | **One step** — the extractor writes `imports/candidates.yaml` directly, no separate accept file |
| D4 | **All 58 skill items become candidate assertions, not exclusions.** The evidenced-vs-familiarity difference is **NOT** recorded at this layer (§6.4) |
| D5 | Ship a starter predicate catalog as package data, audited first |
| D6 | **Gate B is met at a promoted revision** (D-172 ruling 1, amended mechanically in §7a) |
| D7 | **The mapping lives inside the bundle** (D-172 ruling 2; its *carrier* is questioned in §6.2) |

## 5. Slice A — the seeded predicate catalog

**Precedent, reused rather than invented.** `policy/secret-scan.yaml` is already the declared exception to
"empty": `_empty_documents` seeds it from `secret_scan.builtin_ruleset(CURRENT_RULESET_VERSION)`
(`drafts.py:321-329`), because *"an empty ruleset would make the first revision claim a scan it never ran."*
An empty vocabulary makes a bundle claim a denominator it can never disposition.

Shape mirroring `secret_scan.py:169-180`: `BUILTIN_PREDICATE_CATALOGS`, `SUPPORTED_CATALOG_VERSIONS`,
`CURRENT_CATALOG_VERSION`, and `builtin_catalog(version)` raising `UnsupportedPredicateCatalogError` so a
caller turns an unavailable recorded version into **exit 3**. Read **at call time, not bound at import** —
the reason `drafts.py:326-329` gives for secret-scan.

**Critically, the content is written INTO the bundle, not referenced by id.** That is what makes a revision
reproducible: the rows are part of the digest-bound content, not a pointer into whatever the installed
program currently means by that name.

### 5.1 The `incidental` amendment

Admit `incidental` on `technology.used`'s `legal_usage_contexts`. **The justification is semantic:**
familiarity without substantive use is a legitimate state in any user's career, must remain *effective*, and
must never ground verification. That is what `incidental` means and no other context expresses it. Grounding
stays clean because `grounding_facts` already excludes it.

**That `effective.py:220` becomes reachable is a consequence, not the reason.** Revision 1 argued it the
other way, which is unsound — a dead check can equally mean an obsolete rule. The test asserts the semantic
requirement (an `incidental` `technology.used` fact is accepted and does not ground; a `professional` one
does), never that a branch was exercised.

### 5.2 Gate for Slice A

Revision 1's gate proved the catalog *present* while the claim was *audited*. Revision 2 added an invariant 4
that **cannot be evaluated** — the starter catalog is package-wide, mappings are bundle-owned, so there is no
universal "v1 mapping" to prove reachability against. Both replaced:

*Mechanical, each failing on the example catalog as it stands:*

1. **No dead enum member.** Every `UsageContext`, `Surface` and `VerificationBasis` member is admitted by at
   least one predicate. `incidental`: **0 of 41** today. Fails now.
2. **No unreachable guard.** Every `may_ground_skill: true` predicate admits `incidental`, or
   `effective.py:220` can never fire. Fails now.
3. **Semantic, not branch-based:** §5.1's behavioural assertion.
4. *(replaces the incoherent one)* **Package-level reachability, checked between two package-level
   artifacts.** Because §6.2 now seeds a **builtin mapping** alongside the builtin catalog, both are
   package-wide and the check is well-defined: every predicate the builtin `boardwatch-resume-v1` mapping
   names exists in the builtin catalog, and every catalog predicate is either named by some builtin mapping
   or listed in an explicit `not_reachable_from_builtin_mappings` roster. 30 of 41 are unused by this résumé
   and must be *declared* so rather than merely present.
5. Version handling: a recorded version outside `SUPPORTED_CATALOG_VERSIONS` exits 3.

*Non-mechanical, labelled honestly:* "these rows were read" cannot be proven by a test. The gate is a
**recorded per-row account** — for each of the 41, "unchanged from the example, reviewed" or a stated change
with its reason. Invariants 1–4 catch the *class* of defect the unaudited catalog contained; they do not
substitute for reading.

## 6. Slice B — deterministic extraction, grounded

### 6.1 What each bucket yields

Against the live `resume.yaml` (81 records), via `boardwatch-resume-v1` (`enumerators.py:437-547`):

| Locator | n | `atomic_value` | Predicate(s) | Route |
|---|---|---|---|---|
| `entries/<id>/bullets/<id>` | 13 | `{bullet_id, text, tech_tags}` | `employment.accomplishment` / `project.contribution` by entry `kind` | deterministic |
| `entries/<id>/metadata` | 6 | `{entry_id, heading, kind, title, dates, subtitle, location}` | `employment.organization`, `.title`, `.date_range`, `entity.location` | deterministic; `dates` parsed |
| `skill-groups/<label>/<n>` | 58 | `{label, item}` | `technology.used` | deterministic |
| `education/<n>` | 2 | `str` | `education.institution` + `.credential` + `.field` | agent lane (§8) |
| `header/<n>` | 2 | `str` | `person.professional_name`; the email has none | 1 deterministic, 1 unresolved |

One record may yield several candidates; `SourceLedgerRecord.candidate_ids` is a tuple and entry metadata is
the case needing it.

### 6.2 The mapping — carrier, and a proposed departure from D-172

**D-172 ruling 2 decided the mapping lives inside the bundle. That stands and is right.** It also named the
carrier as a `SourceSpec` field. **I believe the field is the wrong shape, and propose a separate document
instead. This needs the owner's assent or veto; the location is unchanged either way.**

Why the field is wrong. `SourceSpec` is keyed per *source* — `source_id`, `source_kind`, `portable_locator`
(`policy.py:356+`, three fields). A mapping is inherently per *adapter*: every source of kind
`boardwatch_resume` shares one locator grammar. Putting it on `SourceSpec` duplicates one mapping across
every source of a kind, which is exactly the trap `SourceLedgerSource`'s docstring names — *"`source_kind`
and `portable_locator` live in `policy/sources.yaml` and are deliberately not repeated here — two homes for
one field is two chances to disagree."* It also has no seeding point: `init` declares no sources, so a
per-source field cannot be seeded, and a fresh bundle would have no mapping — reproducing §2.1's defect one
layer over.

**Proposed: `policy/extraction-mappings.yaml`, keyed by adapter id, seeded non-empty at `init` from a builtin
— exactly the `policy/secret-scan.yaml` pattern.** Content in the bundle, so reproducibility is preserved;
seeded, so extraction works out of the box; keyed by adapter, so one mapping has one home; and package-level
builtins make §5.2's invariant 4 evaluable.

### 6.2a The data contract, not just the location

The review's standing objection is that naming a location leaves the consequential semantics to be invented
in the plan, where they would leak into Python. The contract, therefore:

- **A rule** is `{locator_pattern, predicate, value_from, value_type, display_from}`.
- **`locator_pattern`** matches against `normalized_locator` using the adapter's own segment grammar — the
  vocabulary `emits_locator` already defines (`enumerators.py:463-487`): a literal head, `*` for one
  segment. No regex; a regex over locators is a second grammar that will drift from the emitter.
- **`value_from` / `display_from`** name a field of `atomic_value` (`item`, `text`, `heading`, `dates`, …) or
  `.` for a scalar record. Naming the field is what makes §6.3's grounding checkable.
- **`value_type`** is a `FactValueKind`; construction from the named field is by kind, and a kind whose
  construction can fail (`date_range`, `year_month`, `date`) reports `value_not_typeable` rather than
  raising (§6.3a).
- **Precedence is longest-literal-prefix first, then declaration order**, and ties are a *validation error*
  rather than a silent pick — an ambiguous mapping is a defect, not a policy.
- **Conditional-by-entry-kind** is expressed as a rule whose `locator_pattern` is qualified by an
  `atomic_value` field equality (`kind == "experience"`), not as code. This is the one place the contract
  admits a predicate on content, and it exists because §6.1's bullets genuinely need it.

**Deliberately NOT specified here, and why:** the date grammar for `dates`, and skill-id derivation from a
skill item. Both are implementable detail whose shape does not change any interface in this document, and
writing them into a design is how a spec acquires false precision. They are named in §9 as plan tasks. The
distinction I am drawing: the design fixes the *model and the interpreter's rules*; the plan fixes the
*string-level parsing*.

### 6.3 Grounding, restated — a parsed field, not bytes

**Revision 2 said "the record's own bytes". There are none.** `EnumeratedSourceRecord` carries
`source_record_id`, `source_id`, `normalized_locator`, `atomic_value` and `record_content_digest`
(`enumerators.py:309-321`) — a *parsed, adapter-normalised* value and a digest over it, with no raw substrate
and no byte range. Extending enumeration to retain one is **rejected**: it would change the Gate A adapter
contract and the digest basis to serve a check that the parsed field already supports.

**So the guarantee is: `original_display_value` must occur in the parsed atomic field the rule names
(`display_from`).** Never `str(atomic_value)` — matching the whole dict would let a proposal match a key name
or a sibling field.

| Bucket | Field |
|---|---|
| header / education | the scalar itself |
| skill-groups | `item` — never `label`, never the dict |
| entry metadata | the field the rule names |
| bullets | `text` |

**Load-bearing asymmetry:** the adapter does **not** whitespace-collapse bullet text (`enumerators.py:16-21`,
unlike `tailor/model.py`'s `Bullet`), while `canonicalize_candidate_value` *does*, via `_collapsed`
(`imports.py:141-147`). The check runs against the **raw** display value; the canonical value is derived
separately. Comparing a collapsed span to uncollapsed text false-negatives on every wrapped bullet.

### 6.3a The drain, and its durable carrier

Revision 1 left `review_required` a quarantine with no drain. Revision 2 added a reason catalog but put it in
a **regenerated command report**, which the review correctly rejected: that is visibility, not durable state.
It lives outside the digest-bound revision and cannot later prove why *that promoted draft* left a record
unresolved.

**`imports/extraction-report.yaml`, inside the bundle, keyed by `source_record_id`, bound into the candidate
digest.** Validated: **exactly one** closed reason for every `review_required` record, and **none** for an
`imported` or `excluded` one.

This is not a second source of truth about disposition. Disposition remains derived solely from candidates
and exclusions (`imports.py:430-452`); the report explains only the *resulting* unresolved state, and the
validator ties it to that state rather than letting it assert one.

| Reason | Meaning | Drain |
|---|---|---|
| `no_mapping_for_locator` | no rule matches the locator | extend the mapping (§6.2), re-extract |
| `span_not_grounded` | display value absent from the named field | **a defect signal, not owner work** — the rule or extractor is wrong; fix, re-extract |
| `value_not_typeable` | the named field will not construct the declared kind | agent lane, or the owner corrects the source |
| `free_text_deferred` | prose needing judgement — the 2 education lines | Slice C |
| `no_predicate_exists` | nothing in the catalog can express it — the header email | **owner decision**: add a predicate, or exclude with a reason |

Out-of-catalog is a failure, never a new bucket. `span_not_grounded` being separated from owner work is the
point: a mapping bug must not hide in a pile that looks like a to-do list.

### 6.4 The skill items, and the layer this design does NOT reach

All 58 become `technology.used` **candidate assertions**. Nothing is excluded.

`CandidateRecord` holds `candidate_id`, `source_record_id`, `predicate`, `canonicalized_typed_value`,
`original_display_value`, `occurrences` — and nothing else (`models/imports.py:191-211`). **No** subject,
`usage_context`, `verification_state`, `verification_basis`, `evidence_ids`, `allowed_surfaces`, or
acceptance flag. Those live on `FactRecord` (`models/facts.py:160-182`).

So revision 1's "context comes from the entry the skill is evidenced by, otherwise `incidental`" was **false
at this layer**, as was "the difference is recorded". Concretely:

- Slice B creates **no** `FactRecord`, `SkillRecord`, entity or evidence. **Nothing it produces is
  renderable**, and should not be — the résumé reads `SkillRecord`s via `projection.yaml` (§10).
- A `technology.used` candidate names a `skill_id` that **need not exist**, and **nothing validates that
  reference.** The import validators cover identity, naming, scope, locator shape, one-record-per-unit,
  exclusion agreement, imported-names-candidates, undispositioned records and never-enumerated sources
  (`validation/imports.py`); none checks a candidate's `skill_id` against the inventory. Referential
  validation covers canonical facts only. Owned by §6.8.

### 6.5 The command

`profile-bundle extract --draft NAME --source SOURCE_ID`. It writes `imports/candidates.yaml` (D3),
`imports/extraction-report.yaml` (§6.3a), and re-derives `imports/source-ledger.yaml` via the existing
`build_source_ledger` so the three never disagree.

**Three document writes.** D-137 already rules these cannot be made atomic — POSIX cannot rename three paths
as one operation — so reuse `PARTIAL_EDIT_APPLIED`, which is deliberately outside `COULD_NOT_COMPLETE_CODES`
because exit 3 would invite a retry guaranteed to refuse. Do not invent a second answer.

**Import wall:** `cli/profile_bundle_cmd.py` must transitively import no `boardwatch.store` module, checked
in a fresh interpreter via `sys.modules`. Four walls exist across three test files and no document
enumerates them (D-161, D-162). **Grep `tests/` before wiring in a new module** — a symbol check cannot find
a prohibition.

### 6.6 Stale candidates — extraction is authoritative per source

Revision 2 claimed re-extraction is "safe by construction, the same IDs". **False.** Identity includes
predicate and canonicalized value, so corrected material produces a **different** `candidate_id`, and
`merge_candidate_packages` is append-only (`imports.py:359+`) — the superseded candidate would survive, and
a record could name both.

**Rule: `extract` rebuilds the candidate set for the source it extracts, authoritatively**, replacing that
source's candidates rather than merging into them, and preserving `occurrences` for IDs that survive the
rebuild. Candidates of *other* sources are untouched.

Three reasons this is the right shape rather than a convenience: D-170 ruling 4 already treats a source's
ledger block as replaced **in place**, so per-source authority is the established grain; occurrence lineage
exists to record *the same assertion seen again*, not to retain a withdrawn one; and
`merge_candidate_packages` has **no production caller** (verified: `src/` contains only its definition), so
this defines the extraction path without changing any live behaviour. The merge helper stays for the import
path it was written for.

### 6.7 Schema v2 — what it costs, stated properly

Revision 2 called the bump "affordable". It is *feasible*, and the mechanics were understated:
`migrate_bundle` loads the selected revision **through current document models** before transforming
anything (`migrations.py:83`), and document parsing is not schema-version-dispatched
(`validation/context.py:130`). A new required document or field therefore makes v1 content fail parsing
*before* the 1→2 transform can run.

v2 adds **two documents** and changes no existing model: `policy/extraction-mappings.yaml` (§6.2) and
`imports/extraction-report.yaml` (§6.3a). What the plan must specify:

- a **restricted raw-v1 loader** for migration, or version-aware dispatch in document reading — the design
  requires one of the two and does not choose;
- the exact v1 fixture the transform runs against;
- that migration **creates a v2 draft without rewriting v1 revisions** (history is append-only, §14);
- both new documents seeded, so a migrated v2 draft is not born incomplete.

Affordable in *schedule* terms because no private bundle exists yet, and because Gate A is not declared met
so the grammar may still change (`docs/profile-bundle-authoring.md:24-26`). Not affordable in *effort* terms
as a one-line bump.

### 6.8 The promotion slice, named

The review is right that revision 3 declared this a planning prerequisite and then left it unnamed. It is
not designed here, but it is now bounded:

- **Inputs:** a draft holding candidates, exclusions, the ledger and the extraction report.
- **Outputs:** `FactRecord`s with subject, `usage_context`, `verification_state`/`basis`, `evidence_ids`,
  `allowed_surfaces`; the entities they attach to; `SkillRecord`s with `supporting_fact_ids`.
- **Ownership boundary:** it is the **only** place the evidenced-vs-familiarity distinction can be recorded,
  and the only place a candidate's `skill_id` becomes a real reference. It owns the missing referential check
  from §6.4.
- **Stop condition:** a promoted revision whose facts and skills satisfy semantic validation, and from which
  `projection.yaml` can name a skill that renders.
- **Not in Gate B's critical path for the *denominator*** — a record reaches `imported` on candidates alone —
  **but on the critical path for anything reaching a résumé.**

## 7. What this narrows, and what it does not touch

D-170 ruling 1 said candidates stay owner-authored; its stated reason was *"It cannot: no extractor exists."*
That reason expires. Surviving unchanged: identity derived not proposed, disposition derived not carried,
scope reused not widened, splice in place. Exclusions remain owner-authored.

Out of scope: promotion, facts, entities, evidence, conflicts (§6.8 bounds them).

## 7a. Gate B, mechanically — amending D-172 ruling 1

D-172 bound Gate B to a promoted revision. The review confirmed that boundary is mechanically real —
approval is digest-bound and promotion refuses content without the matching stamp (`promotion.py:555`,
`profile_bundle_cmd.py:997`), and promotion runs full validation and refuses blockers
(`promotion.py:862`), so **a promoted revision cannot contain `review_required` records.**

But it left no falsifiable predicate, and revision 2 invented a quantity that does not exist. **Gate B is
met, for a source, when all of:**

1. there is a **selected promoted revision**;
2. its **full validation is clean** — zero blockers, zero errors;
3. its ledger's **declared denominator for that source is 81**, the number the adapter reaches over the live
   `resume.yaml`;
4. its **`review_required` count is zero**;
5. the **approval and candidate digest binding validates**;
6. the **extraction report accounts for every non-`imported` record** (§6.3a).

**Revision-level approval is reported as a BOOLEAN.** There is no per-record accepted count and the report
must not imply one — approval is one digest decision over the whole revision. Revision 2's "records the owner
has accepted" is withdrawn.

Residual limit, unresolved by design: approval means "I approve this exact content", never "I read all 81".
No bundle mechanism proves reading, for any document. Raising that bar means sampling — audit N, require all
N correct — a separate and heavier decision.

## 8. Slice C — the agent lane (declared, not decomposed)

Only the 2 education lines need it, so it is last and the bundle is useful without it. Follow the existing
subscription-tier handshake: request JSON → agent fills → verify and ingest, with
`tailor/rewrite/agent_lane.py:61`'s rule that the authoritative text is re-derived and the agent's copy is
**never** trusted. Under D2 that is structural: a proposal whose span is absent from the named field produces
nothing and reports `span_not_grounded`.

## 9. Open questions and plan constraints

**Hard constraint on the plan, accepted from the review:** the predicate audit is task 1, and the plan
**stops after it** for a replan checkpoint. An audit that can change policy cannot sit at task 1 of a fully
pre-planned sequence; invariants 1 and 2 of §5.2 already fail today, so at least two rows change.

**Owner decision outstanding:** §6.2's carrier — `policy/extraction-mappings.yaml` versus the `SourceSpec`
field D-172 named. Location is settled; only the carrier is in question.

**Plan tasks, deliberately not designed here (§6.2a):** the `dates` grammar, and skill-id derivation from a
skill item.

**Still open, not blocking:** whether `header/2` (an email) argues for a contact predicate or is correctly
`no_predicate_exists`.

## 10. What must not be re-derived

- The renderer never reads `Resume.header` or `Resume.education` (D-156), so those buckets cannot change a
  PDF regardless of disposition.
- Projection filters skills on `allowed_surfaces` alone — **not** `verification_state`, **not**
  `usage_context` (`projection/contract.py:28-42`). So even once §6.8 records the distinction, **nothing
  downstream reads it**, and a skill in an unavailable state still renders. Pre-existing, not this design's
  to close.
- The résumé's skills section is assembled from `{config_dir}/projection.yaml`, the owner's editorial file
  naming bundle skill ids (`projection/pool.py:145-151`), so the owner retains explicit curation.
