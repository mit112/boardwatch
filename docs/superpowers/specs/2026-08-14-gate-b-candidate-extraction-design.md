# Gate B candidate extraction — design

**Status:** revision 7. Five external review rounds, all NOT READY. **The review loop is PAUSED and no round 6
will run (D-178): this revision is now the design we BUILD FROM, and the rule interface is settled by code
under `make check`, not by more prose review. Where this document and the code disagree, the code wins.** Round 5 found
that the flat rule tuple could not *express* three extraction operations — a predicate chosen by the
kind→subject model (the bullet case), one component of a parsed range (project dates), and a coalesce across
fields (project name) — and that patching prose around an under-powered interface is exactly the loop that
five rounds have not broken. Revision 7 is therefore **not a patch pass**: it designs the rule interface as a
complete data schema over a **closed set of extraction operations** (§6.2a), makes `entry_kind_model` a real
in-bundle object both the metadata and the bullet predicates resolve through, and **proves completeness** by
expressing every §6.1 bucket in that schema with nothing left to invent in Python. Revision 7 does **not**
declare itself clean (§9). No code written. **Date:** 2026-08-14.
**Narrows** D-170 ruling 1 (§7). **Amends** D-172 ruling 1 (§7a) and ruling 2's carrier (§6.2, assented
2026-08-14, D-174). Respects, and does not relitigate, D-170 / D-172 / D-173 / D-174 / D-175 / D-176. No open
owner decisions — every fix below is a data-schema change inside already-decided boundaries, requiring no new
owner ruling.

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
| **4** | §7a predicate 6 — the report "accounts for every non-`imported` record" | **Contradicts §6.3a.** Non-imported includes `excluded`, which §6.3a forbids from the report; the predicate must scope to `review_required` (§7a) |
| **4** | §6.2a keyed conditionals on an `atomic_value` `kind`, allowed one output per locator, and built the typed value "from the named field" | **Unexpressible.** The bullet record has no `kind`; entry metadata owes four candidates but one-output + "ties are an error" forbids it; a single education scalar cannot yield three predicates (§6.2a) |
| **4** | §6.2a called the locator grammar "already defined by `emits_locator`", "a literal head, `*` for one segment" | **Loose + too weak.** `emits_locator` is a per-head shape validator, not a wildcard grammar, and `header/*` cannot select `header/1` while leaving `header/2` unresolved (§6.2a) |
| **5** | `entries/*/metadata` maps unconditionally to `employment.organization`/`.title`/`.date_range`/`entity.location` | **Fails for `kind: project`.** Those predicates are `legal_subject_kinds: [employment]` only (`predicates.yaml:215,241,270`); a project entry's facts land on a `project` subject and `semantic.py:149-165` raises `PREDICATE_SUBJECT_KIND_ILLEGAL`, so promotion refuses and Gate B predicate 2 can never hold. Rev 5 split *bullets* by kind but left *metadata* unsplit — the same concept modelled once and forgotten once (§6.2a) |
| **5** | `Entry.kind` is `"experience" \| "project"` and every entry routes to one of them | **False + non-total.** `Entry.kind` is an open `str = "experience"` (`tailor/model.py:38`); an entry whose kind is neither has no route, so it would fall to a silent `review_required` with no reason, or be misfiled as `no_mapping_for_locator` though a rule *did* match (§6.3a) |
| **5** | §6.7 residual is "exactly two things" (transform + widen `SUPPORTED_SCHEMA_VERSIONS`) | **Omits a third.** `CURRENT_SCHEMA_VERSION` must also become 2 (`schema.py:80`): `_initial_manifest` stamps it into every fresh `init` manifest (`drafts.py:404,415`), and D-174 has `init` seed the new mapping document, so a fresh bundle must be born v2 — not v1 lacking the seeded doc (§6.7) |
| **5** | §6.2a: "§8 has its own proposal contract (request JSON → agent fills → grounding-check → ingest)" | **Overstated.** §8 is declared, not decomposed; it cites the rewrite handshake (`agent_lane.py:61`, `agent_io.py`) only as *precedent*, with no education request/response model or ingest command. Also implied Gate B was reachable in Slice B, though the 2 education records stay `free_text_deferred` until Slice C (§6.2a, §7a) |
| **6** | project identity: `title`→nothing, `heading`→`project.summary` | **Backwards.** `render/latex.py:115-119` displays `title` as the project's name and uses `heading` only when `title is None` (`model.py:35-38`; fixture `heading="ignored", title="Knowledge Forge"`, `test_tailor_render_latex.py:58-59`). Rev 6 dropped the real name and relabelled the *fallback* as a description. Fixed: coalesce `title` else `heading` → a new `project.name` predicate (§6.2a; a Slice-A audit row, §9) |
| **6** | the bullet's kind→predicate lookup is a *rule element* | **Not representable.** The tuple `{locator_pattern, predicate, value_from, value_type, display_from, condition}` had no way to say "the predicate is the model's contribution slot for the parent entry's kind" — the model lived in prose, so the same routing was modelled in a table for metadata and re-invented as prose for bullets. Rev 7 makes `entry_kind_model` a real object and adds `predicate_from` so **both** resolve through it (§6.2a) |
| **6** | project `dates` → two `year_month` via two rules differing only in `predicate` | **Undecomposable.** No element told the constructor to take the range's *start* for one predicate and its *end* for the other; two rules sharing `value_from: dates` and `value_type: year_month` cannot deterministically yield two different values (rev 6's own §9 flagged this unresolved). Rev 7 adds `value_selector: range_start\|range_end` (§6.2a) |
| **6** | "Gate B cannot be MET until Slice C ships" | **Incomplete *and* overstated.** `header/2` (the email) is `no_predicate_exists` with no exclusion, so `imports.py:422-427` derives `review_required` and `validation/imports.py:507` blocks Gate B — a **third** unresolved record Slice C never touches; and explicit owner exclusions of the 2 education records clear predicate 4 *without* Slice C at all (§7a) |
| **6** | §6.7's v2 residual is "exactly three things" (transform + widen `SUPPORTED` + `CURRENT_SCHEMA_VERSION=2`) | **Understated the doc-add plumbing.** Adding two documents also needs two `DocumentKind` members + `FIXED_DOCUMENTS` paths (`layout.py:38,76`), two `DOCUMENT_MODELS` registrations (`schema.py:92`, which asserts totality over `DocumentKind`), and two `_empty_documents` seeds (`drafts.py:321`) — else the new documents are not legal members of their own schema and the required-file check rejects them (§6.7) |

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
| D7 | **The mapping lives inside the bundle** (D-172 ruling 2), **carried by `policy/extraction-mappings.yaml`** keyed by adapter and seeded at `init` (D-174, amending that ruling's carrier — §6.2) |

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
   artifacts.** Because §6.2 now seeds a **builtin mapping** (including the `entry_kind_model`, §6.2a)
   alongside the builtin catalog, both are package-wide and the check is well-defined: every predicate the
   builtin `boardwatch-resume-v1` mapping (rules **and** every `entry_kind_model` slot) names exists in the
   builtin catalog, and every catalog predicate is either named by some builtin mapping or listed in an
   explicit `not_reachable_from_builtin_mappings` roster. Most predicates are unused by this résumé and must
   be *declared* so rather than merely present — and the §6.2a audit shifts two rows: the new `project.name`
   becomes *named* by the mapping, and `project.summary` (no longer `heading`'s target) moves *into* the
   roster.
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
| `entries/<id>/metadata` | 6 | `{entry_id, heading, kind, title, dates, subtitle, location}` | **by entry `kind`** via `entry_kind_model` (§6.2a): `experience` → `employment.organization`(heading), `.title`(title), `.date_range`(dates), `entity.location`(location); `project` → `project.name`(title else heading, coalesced), `project.start_date`+`.end_date`(dates), `entity.location`(location); any other kind → `unsupported_entry_kind` | deterministic; `dates` parsed |
| `skill-groups/<label>/<n>` | 58 | `{label, item}` | `technology.used` | deterministic |
| `education/<n>` | 2 | `str` | `education.institution` + `.credential` + `.field` | agent lane (§8) |
| `header/<n>` | 2 | `str` | `person.professional_name`; the email has none | 1 deterministic, 1 unresolved |

One record may yield several candidates; `SourceLedgerRecord.candidate_ids` is a tuple and entry metadata is
the case needing it.

### 6.2 The mapping — inside the bundle, in its own document

**D-172 ruling 2 decided the mapping lives inside the bundle. That stands.** It named the carrier as a
`SourceSpec` field; **D-174 amends that carrier to `policy/extraction-mappings.yaml`** (owner assent,
2026-08-14). The location never changed.

Why the field was the wrong shape. `SourceSpec` is keyed per *source* — `source_id`, `source_kind`,
`portable_locator`
(`policy.py:356+`, three fields). A mapping is inherently per *adapter*: every source of kind
`boardwatch_resume` shares one locator grammar. Putting it on `SourceSpec` duplicates one mapping across
every source of a kind, which is exactly the trap `SourceLedgerSource`'s docstring names — *"`source_kind`
and `portable_locator` live in `policy/sources.yaml` and are deliberately not repeated here — two homes for
one field is two chances to disagree."* It also has no seeding point: `init` declares no sources, so a
per-source field cannot be seeded, and a fresh bundle would have no mapping — reproducing §2.1's defect one
layer over.

**Decided: `policy/extraction-mappings.yaml`, keyed by adapter id, seeded non-empty at `init` from a builtin
— exactly the `policy/secret-scan.yaml` pattern.** Content in the bundle, so reproducibility is preserved;
seeded, so extraction works out of the box; keyed by adapter, so one mapping has one home; and package-level
builtins make §5.2's invariant 4 evaluable.

### 6.2a The data contract, not just the location

The review's standing objection is that naming a location leaves the consequential semantics to be invented
in the plan, where they would leak into Python. The contract, therefore:

**Which records this deterministic contract covers.** Per §6.1: bullets, entry metadata, skill items, and
`header/1` (the professional name). Education (the 2 free-text lines) is **agent-lane (§8), explicitly OUT of
this deterministic contract** — a single education scalar (`enumerators.py:510-511`) carries institution,
credential and field together, and splitting one line into three predicates is judgement, not a field
selection. That agent lane's **proposal contract is DEFERRED to Slice C — §8 is declared, not
decomposed** (it cites the rewrite handshake, `agent_lane.py:61` / `agent_io.py`, only as
*precedent*, and defines no education request/response model, multiplicity, typed value, or ingest command;
do not decompose Slice C now — education is last and the bundle is useful without it). The deterministic
mapping never attempts education, and an education record carries `free_text_deferred` in the extraction
report until Slice C. `header/2` (the email) matches no rule and ends `no_predicate_exists`.

**The closed set of extraction operations — the anti-loop claim.** Five rounds looped because each patched
prose around an interface that could not *express* the next operation. Revision 7 breaks that by enumerating
the operations extraction actually needs as a **closed set**, giving each a schema element, and proving in
§6.2a-proof that every §6.1 bucket is a composition of only these — so nothing falls to Python and no round-6
finding can be "the interface cannot say X" unless X is a genuinely new operation, which is then a *data
schema* change gated here, never a code special-case.

| # | Operation | Schema element | Fails as |
|---|---|---|---|
| **O1** | **match** records by locator | `locator_pattern` (segment-wise literal / `*`) | `no_mapping_for_locator` if none |
| **O2a** | **literal predicate** | `predicate: <catalog id>` | build error if out-of-catalog |
| **O2b** | **modeled predicate** (depends on entry kind) | `predicate_from: entry_kind_model` (+ `kind_source`, `emits_group`) | `unsupported_entry_kind` if the kind is unmodeled |
| **O3a** | **value = a named field** | `value_from: <field>` (or `.` for a scalar) | no candidate if the field is null/absent |
| **O3b** | **value = one component of a parsed range** | `value_from: <field>` + `value_selector: range_start \| range_end` | `value_not_typeable` if the component will not construct |
| **O3c** | **value = first non-null of a priority list** (coalesce) | `value_from: [<field>, …]` | no candidate if every field is null |
| **O4** | **type** the value | `value_type: <FactValueKind>` | `value_not_typeable` if construction fails |
| **O5** | **ground** the display span | `display_from: <field>` (the *chosen* source field) | `span_not_grounded` if the span is absent |
| **O6** | **cross-record lookup** of the parent kind | `condition: parent_entry.kind` (feeds O2b) | resolvable by construction (emission order) |

The claim is **completeness, not minimality plus room to grow**: §6.2a-proof expresses every bucket using
only O1–O6, and every one of O3a/O3b/O3c is exercised by some cell below, so none is dead weight and none is
missing. This table, not any prose, is the interface.

**The `entry_kind_model` object — the root of BOTH the metadata split and the bullet split, now a real
object.** Revision 5 split *bullets* by kind (prose) but mapped *metadata* unconditionally to `employment.*`;
that fails for `kind: project`, because those predicates are `legal_subject_kinds: [employment]` only
(`predicates.yaml:216,242,271`) and `semantic.py:149-165` raises `PREDICATE_SUBJECT_KIND_ILLEGAL` when a
project entry's facts land on a `project` subject. Revision 6 rooted the *idea* in one table but left the
predicate that a rule resolves to still living in prose for the bullet case — so the recurrence was not
actually closed. Revision 7 makes the table a **first-class in-bundle object**, `entry_kind_model`, inside
`policy/extraction-mappings.yaml` (§6.2), that **both** the metadata rule and the bullet rule reference via
`predicate_from` (O2b). One object, two referents; that is what makes "modelled once, forgotten once"
structurally impossible rather than merely promised.

*Shape.* Keyed by entry kind; each kind names its subject kind and a set of **slots**, each slot a fully
specified emission (its value source, selector, type, predicate, and grounding field):

```yaml
entry_kind_model:                      # inside policy/extraction-mappings.yaml, under adapter boardwatch-resume-v1
  experience:
    subject_kind: employment
    slots:
      organization: {group: metadata, value_from: heading,   value_type: string,     predicate: employment.organization, display_from: heading}
      title:        {group: metadata, value_from: title,     value_type: string,     predicate: employment.title,        display_from: title}
      dates:        {group: metadata, value_from: dates,      value_type: date_range, predicate: employment.date_range,   display_from: dates}
      location:     {group: metadata, value_from: location,   value_type: string,     predicate: entity.location,         display_from: location}
      contribution: {group: contribution, value_from: text,   value_type: string,     predicate: employment.accomplishment, display_from: text}
  project:
    subject_kind: project
    slots:
      name:         {group: metadata, value_from: [title, heading], value_type: string, predicate: project.name,      display_from: chosen}   # O3c coalesce
      dates_start:  {group: metadata, value_from: dates, value_selector: range_start, value_type: year_month, predicate: project.start_date, display_from: dates}  # O3b
      dates_end:    {group: metadata, value_from: dates, value_selector: range_end,   value_type: year_month, predicate: project.end_date,   display_from: dates}  # O3b
      location:     {group: metadata, value_from: location, value_type: string, predicate: entity.location,   display_from: location}
      contribution: {group: contribution, value_from: text, value_type: string, predicate: project.contribution, display_from: text}
  # a kind absent from this map has NO subject kind -> unsupported_entry_kind for its metadata AND bullets
```

*Entry kind → subject kind is total over `str`.* `Entry.kind` is an open `str` defaulting to `"experience"`
(`tailor/model.py:38`), **not** a closed enum, and constraining it is out of bounds (it would change the Gate
A adapter/résumé model). Any kind **absent from `entry_kind_model`** resolves to no subject kind, and every
candidate that entry would have produced — metadata *and* bullets — reports `unsupported_entry_kind` (§6.3a):
a typed failure with a drain, never a silent `review_required`, never `no_mapping_for_locator` (a rule *did*
match the locator). The map being a data object rather than a Python `if` is what makes the escape hatch
declarative.

*The slot table read out per (subject-kind, source field),* every predicate verified against the seeded
catalog to have a `legal_subject_kinds` admitting that cell's subject kind:

| source field | `experience` (subject `employment`) | `project` (subject `project`) |
|---|---|---|
| `heading` | `employment.organization` — string (`:216-218`) | *(name fallback only)* — feeds `project.name` when `title` is null (O3c coalesce), else no candidate |
| `title` | `employment.title` — string (`:242-245`) | `project.name` — string, card. one — **new predicate** (Slice-A audit, §9); coalesced `title` else `heading` |
| `dates` | `employment.date_range` — one `date_range` (`:271-273`) | `project.start_date` (`range_start`) **+** `project.end_date` (`range_end`) — **two** `year_month` (`:408`, `:441`) |
| `location` | `entity.location` — string (`:677`) | `entity.location` — string (`:677`) |
| `subtitle` | **no candidate** — no predicate, no slot | **no candidate** — no predicate, no slot |
| bullet (contribution) | `employment.accomplishment` — string (`:323`) | `project.contribution` — string (`:474`) |

Three asymmetries fall out of the catalog and are decided here, not assumed:

- **project name = coalesce(`title`, `heading`) → `project.name`.** The renderer proves `title` is the
  project's real name and `heading` its fallback: `render/latex.py:115-119` displays `escape(e.title)` as the
  project heading and only falls back to `escape(e.heading)` when `title is None` (`:113-114`;
  `model.py:35-38`; fixture `heading="ignored", title="Knowledge Forge"`, `test_tailor_render_latex.py:58-59`).
  Revision 6 had this **backwards** — it dropped `title` and relabelled `heading` as `project.summary`, a
  *description* predicate. The catalog has no project name/title/organization predicate today, so this needs a
  **new `project.name`** (string, card. one; mirror `project.summary`'s subject/surface shape). That is a
  Slice-A **catalog-audit row** (§9, task 1) — the audit sanctions the catalog change; this document only
  specifies the mapping. `project.summary` is then **unused by the builtin mapping** and moves to §5.2's
  `not_reachable_from_builtin_mappings` roster. The `display_from: chosen` marker means the grounding field is
  whichever coalesce field supplied the value: if `title` was used the span must occur in `title`, if the
  `heading` fallback was used it must occur in `heading` (O5).
- **`subtitle` → no candidate, either kind.** No predicate expresses a subtitle, so it has no slot. A
  present-but-unmapped field emits nothing — the same outcome as a null field. The metadata record still
  reaches `imported` on its other slots, so this is per-*field*, not a per-*record* `review_required`.
- **`dates` on a project → two candidates via a component selector.** There is no `project.date_range`;
  `project.start_date`/`.end_date` are each `year_month`, card. one. Revision 6 had two rules that both said
  `value_from: dates`, `value_type: year_month` and differed only in `predicate` — which **cannot**
  deterministically yield two different values from one string. O3b closes this: each slot carries
  `value_selector: range_start` / `range_end`, so after the `dates` grammar parses the range the constructor
  selects a component per slot. This is multi-output emission (two predicates), not ambiguity. A component
  that will not construct `year_month` reports `value_not_typeable` (§6.3a). `entity.location` is the one
  predicate legal for **both** subject kinds (`legal_subject_kinds: [education, employment, project,
  presentation, affiliation]`, `:679-684`), so `location` maps identically either way — but still through the
  model, keyed by subject.

*Catalog-checked, once, before extraction.* Every slot's predicate must exist in the seeded catalog and its
`legal_subject_kinds` must admit that slot's subject kind, or the model is a **build/validation error** — not
a promotion-time `PREDICATE_SUBJECT_KIND_ILLEGAL` discovered per entry. This is what makes the revision-5
misrouting a caught *class* rather than a per-entry surprise; it sits beside §5.2's package-level reachability
invariant.

**The rule schema, over O1–O6.** A rule is one of two shapes, both drawing only on the operation set above:

- **`locator_pattern`** (O1) is a small, segment-wise pattern the mapping interpreter defines, matched against
  `normalized_locator`. Each segment is either a **literal** (matches that segment exactly) or `*` (matches
  any one segment). **Literal non-head segments are legal and required:** `entries/*/metadata` needs the
  literal `metadata`, and `header/1` needs a literal index so it selects the professional name while leaving
  `header/2` (the email) unmatched — a `header/*` pattern would wrongly claim the email. This is **not**
  `emits_locator`: that function is a hardcoded per-head *shape* validator (`_is_index` / `is_emitted_segment`,
  `enumerators.py:463-490`), not a wildcard-pattern grammar. The relationship is one-way — every
  `locator_pattern` must only match shapes `emits_locator` admits (validated once against the adapter), so a
  pattern cannot name a locator the adapter never emits. No regex; a regex over locators is a second grammar
  that would drift from the emitter.
- **Predicate source — exactly one of** `predicate` (O2a) or `predicate_from` (O2b):
  - a **literal rule** carries `predicate: <catalog id>` and its own `value_from` / `value_type` /
    `display_from` (O3a + O4 + O5). This is the whole of the `header/1` and skill rules.
  - a **model-routed rule** carries `predicate_from: entry_kind_model`, a `kind_source`, and an `emits_group`.
    It carries **no** `predicate` / `value_from` / `value_type` / `display_from` of its own — those come from
    each slot the model defines for the resolved kind, filtered to `emits_group`. Metadata and bullets are one
    such rule apiece, and *both* resolve through the one object, so the routing lives in exactly one place.
- **`kind_source`** (present only with `predicate_from`) is `self` or `condition`:
  - `self` reads the kind off the record's own `atomic_value.kind` — the metadata rule, whose record carries
    `kind` (the enumerator dumps the entry excluding bullets, `enumerators.py:529-533`).
  - `condition: parent_entry.kind` (O6) supplies a kind the record does **not** carry, by a **defined
    cross-record lookup**. The bullet record's `atomic_value` is `{bullet_id, text, tech_tags}` with **no
    `kind`** (`tailor/model.py:12-16`), while its contribution predicate depends on the **parent entry's**
    kind. The parent is reached deterministically — a bullet locator `entries/<id>/bullets/<id>` yields its
    parent's metadata locator `entries/<id>/metadata` by dropping the `bullets/<id>` tail, and that metadata
    record's `atomic_value` **does** carry `kind`. Metadata is emitted before any bullet
    (`enumerators.py:492-497,529-539`), so the parent is always resolvable. **Chosen over widening the
    bullet's `atomic_value` to carry `kind`:** that would change the Gate A adapter contract and the digest
    basis — exactly what §6.3 rejects — and D-170 keeps derivation, not widening, as the grain. The lookup
    reads records already emitted and changes no adapter. Because the model is total, an unmodeled parent kind
    yields `unsupported_entry_kind` for the bullet too — the *same* routing its metadata got, so a bullet can
    never resolve to a predicate its parent's metadata could not.
- **`emits_group`** (present only with `predicate_from`) is `metadata` or `contribution`, and selects the
  slots of the resolved kind whose `group` matches. The metadata rule (`emits_group: metadata`) emits every
  metadata-group slot the kind defines; the bullet rule (`emits_group: contribution`) emits the single
  contribution slot.
- **Value source (O3a/O3b/O3c), `value_type` (O4), `display_from` (O5).** On a literal rule these sit on the
  rule; on a model-routed rule they sit on each slot. `value_from` names a field of `atomic_value` (`item`,
  `text`, `heading`, `dates`, `title`, `location`, …), or `.` for a scalar record, or a **priority list**
  `[a, b, …]` (O3c, first non-null wins). `value_selector: range_start | range_end` (O3b) selects a component
  after the `dates` grammar parses a range. A named field **absent or null** (entry
  `title`/`dates`/`subtitle`/`location` are `str | None`, `tailor/model.py:39-42`), or an all-null coalesce
  list, yields **no candidate** — never an error. `value_type` is a `FactValueKind`; a kind whose construction
  can fail (`date_range`, `year_month`, `date`) reports `value_not_typeable` rather than raising (§6.3a).
  `display_from` names the field the span must occur in (O5, §6.3): the literal field for O3a, the **chosen**
  coalesce field for O3c, and the **raw range field** (`dates`) for O3b — because the parsed component
  (e.g. `2023-09`) need not appear verbatim in `Sep 2023 – Dec 2023`, both `dates` slots ground against the
  raw `dates` string and carry it as `original_display_value`, while their differing `year_month` typed values
  keep their `candidate_id`s distinct (identity is `source_record_id | predicate | typed_value`, §1).
- **Multi-output emission, not ambiguity.** One `entries/*/metadata` locator emits the candidates the model
  gives for the entry's subject kind — up to four for `experience`
  (`employment.organization`/`.title`/`.date_range`/`entity.location`) and up to four for `project`
  (`project.name`/`project.start_date`/`.end_date`/`entity.location`, `subtitle` contributing none) — all from
  slots of the one model, sharing the pattern but naming different fields and predicates. Null fields drop out,
  so an entry with no `location` simply emits fewer.
- **Ambiguity, redefined, is evaluated per `(locator, predicate)` group:** two rules (or two slots) that
  produce the **same predicate** for the same locator are a *validation error* — an ambiguous mapping the
  author must resolve — **except** that a `locator_pattern` **strictly more literal-specific** (a longer
  literal prefix) wins over a less specific one for that predicate. Two rules of **equal** specificity
  producing the same predicate for the same locator is the genuine, reachable tie that fails validation.
  Declaration order is **not** a tiebreaker: making it one (revision 4's rule) rendered "ties are a validation
  error" a dead branch, because a total order can never tie.

**§6.2a-proof — completeness.** Every §6.1 bucket, expressed in O1–O6, nothing left to Python:

| Bucket | Rule(s) | Operations used |
|---|---|---|
| `header/1` (professional name) | literal: `locator_pattern: header/1`, `predicate: person.professional_name`, `value_from: .`, `value_type: string`, `display_from: .` | O1, O2a, O3a, O4, O5 |
| `header/2` (email) | **no rule matches** — `no_predicate_exists` (§6.3a, §7a): the catalog has no contact predicate | none — a reported gap, not a Python branch |
| skill items (58) | literal: `locator_pattern: skill-groups/*/*`, `predicate: technology.used`, `value_from: item`, `value_type: string`, `display_from: item` | O1, O2a, O3a, O4, O5 |
| education (2) | **no deterministic rule** — agent lane, Slice C (§8); reported `free_text_deferred` | none deterministic — a bounded deferral |
| entry metadata (6) | **one** model-routed rule: `locator_pattern: entries/*/metadata`, `predicate_from: entry_kind_model`, `kind_source: self`, `emits_group: metadata` → each kind's metadata slots | O1, O2b, O3a/O3b/O3c, O4, O5 |
| bullets (13) | **one** model-routed rule: `locator_pattern: entries/*/bullets/*`, `predicate_from: entry_kind_model`, `kind_source: condition (parent_entry.kind)`, `emits_group: contribution` | O1, O2b, O3a, O4, O5, O6 |

Two literal rules, two model-routed rules, two reported non-rules (`header/2`, education). O3a appears in
every string cell, O3b in the two `project.dates` slots, O3c in `project.name`; each operation is reached, and
no bucket needs an operation absent from the set. That is the anti-loop check: a round-6 "the interface cannot
express X" is only admissible if X is a *seventh* operation, at which point it is a new row in the O-table and
a slot/rule field — a data change gated in this document, never a Python special-case.

**Deliberately NOT specified here, and why:** the `dates` range grammar (which now feeds both the `date_range`
construction for `experience` and the `range_start`/`range_end` split for `project`), and skill-id derivation
from a skill item. Both are string-level parsing whose shape changes no interface in this document — O3b names
*that* a component is selected; the grammar decides *how* the string is cut. Writing them into a design is how
a spec acquires false precision. They are §9 plan tasks. The distinction: the design fixes the *model, the
operation set, and the interpreter's rules*; the plan fixes the *string-level parsing*.

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
| `unsupported_entry_kind` | a rule matched, but the entry's `kind` resolves to no subject kind in the §6.2a model (neither `experience` nor `project`) — so its metadata and bullets have no legal predicate | **owner decision**: extend the Gate A résumé adapter and the §6.2a kind→predicate map to cover the new kind (with catalog-legal predicates), or correct/exclude the entry with a reason. Distinct from `no_mapping_for_locator` (a rule *did* match the locator) and never a silent `review_required` — an open `Entry.kind` (`tailor/model.py:38`) makes this the total contract's escape hatch, not an enum constraint |
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

Revision 2 called the bump "affordable"; revision 4 overstated the residual as needing a restricted raw-v1
loader or version-aware dispatch. Neither is true for **this** bump, because v2 only **adds** two documents
and changes **no** v1 model:

- `load_documents` parses only the files that are **present** and does **not** reject a declared-but-absent
  document (`validation/context.py:95`, docstring lines 102-104). The missing-file check lives one layer up,
  in `_missing_declared_documents` (`validation/structural.py:88`), which `migrate_bundle` never runs.
- So a v1 tree parses cleanly under v2 models: the two new documents are simply absent, not malformed, and
  `require_supported_schema` (`schema.py:142`) lets it through once v1 is in the supported set.

The **version trio** below is correct but was **not the whole residual** — the two new documents must first
become legal members of the schema, or the machinery has no path→kind→parser→required-file for them. The
residual is the trio **plus** the doc-add plumbing (§6.7-plumbing).

The version trio:

1. **`migrate_bundle` is a stub.** It returns `already_current` and writes nothing (`migrations.py:83`); at
   v2 it needs a real `1 -> 2` transform that **seeds the two new documents** — `policy/extraction-mappings.yaml`
   (§6.2) and `imports/extraction-report.yaml` (§6.3a) — from their builtins and **bumps the manifest**,
   writing the result as a **v2 draft that never rewrites a v1 revision** (history is append-only; a rewrite
   would break every descendant's `parent_bundle_digest`, `migrations.py:31-39`).
2. **The supported set must widen to `{1, 2}`.** `SUPPORTED_SCHEMA_VERSIONS` is `frozenset({1})`
   (`schema.py:84`); growing the set is already pinned by the tripwire
   `test_a_previous_schema_fixture_and_a_forward_migration_are_owed_at_v2`, which fails the moment the set
   grows and forces the bump to ship the previous-version fixture and the forward transform
   (`migrations.py:20-28`).
3. **`CURRENT_SCHEMA_VERSION` must become 2.** It is `1` today (`schema.py:80`), and revision 5 omitted this,
   calling the residual "two things". It is load-bearing: `_initial_manifest` (`drafts.py:404`) stamps
   `CURRENT_SCHEMA_VERSION` into the manifest of every fresh `init` (`drafts.py:415`), and D-174 has `init`
   seed the new mapping document (`policy/extraction-mappings.yaml`). If the constant stayed `1`, a freshly
   `init`-ed bundle would be born **v1** while carrying a v2-only document — a tree that neither the migrator
   (which only sees existing v1 trees) nor `require_supported_schema` reconciles. A fresh bundle must be born
   **v2** so its seeded mapping is a legal member of its own schema.

**§6.7-plumbing — the companion grammar/model/init obligations revision 5 understated.** Adding two required
documents is not just a transform and a version bump; each of `policy/extraction-mappings.yaml` (§6.2) and
`imports/extraction-report.yaml` (§6.3a) owes, per the code:

1. **A `DocumentKind` member each** (`layout.py:38`) — the enum parsing dispatches on, one kind per declared
   file.
2. **A `FIXED_DOCUMENTS` path→kind entry each** (`layout.py:76`). This is what makes them **required, not
   optional**: `missing_fixed_documents` (`layout.py:165`) and `_missing_declared_documents`
   (`validation/structural.py:88`) report any `FIXED_DOCUMENTS` path absent from the tree. That the *parse*
   layer is lenient (above) and the *validation* layer requires the file is not a contradiction — it is
   exactly why both `init` and the `1 -> 2` transform must **seed** the documents: a promoted revision runs
   full validation, which demands them present.
3. **A `DOCUMENT_MODELS` parser registration each** (`schema.py:92`) — the one place a file's kind becomes a
   pydantic model. A test asserts **totality over `DocumentKind`** (comment `schema.py:91`), so a new kind
   with no registered model fails that test until both are added together.
4. **An `_empty_documents` seed each** (`drafts.py:321`), the `init` path (as distinct from the migrate path
   in trio-item 1). Following the `policy/secret-scan.yaml` precedent (`drafts.py:330`): the **extraction
   report is seeded EMPTY** (a fresh bundle has no sources, so no reasons), while the **extraction mapping is
   seeded NON-EMPTY from its builtin** (`builtin_catalog`/`builtin mapping`, §6.2) — an empty mapping would
   reproduce §2.1's "claim a denominator it can never disposition" defect one layer over. Read at call time,
   not bound at import, exactly as secret-scan is.

Miss any of these four and the document is not a legal member of its own schema: no kind means no parser, no
`FIXED_DOCUMENTS` entry means the required-file check never guards it (or, once the transform writes it, an
undeclared path), no `DOCUMENT_MODELS` row breaks the totality test, no seed means a fresh `init` bundle is
born without the document the version bump just made mandatory.

The plan must also name the **exact v1 fixture** the transform runs against, and seed **both** new documents
so a migrated v2 draft is not born incomplete. **No raw-v1 loader and no version-dispatched parsing are
required** — that mandate is withdrawn.

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
6. the **extraction report carries exactly one reason for every `review_required` record, and none for any
   other** (§6.3a). Scoped to `review_required` deliberately: §6.3a forbids a report entry for an `imported`
   or `excluded` record, so "every non-`imported`" would demand entries §6.3a rejects.

**What predicate 4 (zero `review_required`) actually requires — stated accurately.** After Slice B, **three**
records are unresolved, not two, and disposition is derived (`imports.py:422-427`): a record with no
candidates and no exclusion is `review_required`, and `validation/imports.py:507` makes each one a Gate-B
blocker.

- **2 education records** carry `free_text_deferred` (§6.3a) — prose the deterministic mapping never
  attempts. **The candidate-producing path** to zero for these needs **Slice C's agent lane (§8)** to promote
  them out of `free_text_deferred`.
- **`header/2` (the email)** carries `no_predicate_exists` — the catalog has no contact predicate, so no rule
  matches, so it has no candidate and no exclusion and is therefore `review_required`. **Slice C never touches
  it**: it is not free text needing judgement, it is a missing predicate. Revision 6's "Gate B cannot be MET
  until Slice C ships" was **incomplete** for exactly this — `header/2` is a third unresolved record on which
  Slice C has no bearing.

So predicate 4 needs, independently: education promoted (Slice C on the candidate path), **and** `header/2`
resolved (an owner adds a contact predicate to the catalog, or excludes `header/2` with a reason — a Slice-A
audit / disposition question, §9, not Slice C).

**And Slice C is not strictly necessary at all.** Revision 6 was also **overstated**: explicit owner
exclusions can satisfy zero-`review_required` **without** Slice C. An owner who excludes the 2 education
records with a reason moves them from `review_required` to `excluded` (`build_source_ledger`), and §6.3a then
forbids any extraction-report entry for them, so they clear predicate 4 *and* predicate 6. Do the same for
`header/2` and predicate 4 holds on the exclusion path alone. That is a disposition choice, not the
deterministic candidate path — but it is a real second route to Gate B, and the flat "cannot be MET until
Slice C ships" denied it.

The honest statement: **the deterministic candidate-producing path to Gate B needs Slice C (for education);
Gate B additionally needs `header/2` resolved (outside Slice C); and explicit owner exclusions of the
education and `header/2` records satisfy zero-`review_required` with no Slice C at all.** Revision 5's implied
"Gate B reachable in Slice B" is still false — Slice B alone leaves three `review_required` records.

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
pre-planned sequence. It has **at least three** rows to change, all known now: §5.2 invariants 1 and 2 fail on
the example catalog today (the `incidental` gap), **and** §6.2a adds a **new `project.name` predicate** (string,
card. one; mirror `project.summary`'s subject/surface shape) while retiring `heading`→`project.summary`, which
moves `project.summary` into §5.2's `not_reachable_from_builtin_mappings` roster. The audit sanctions these
catalog rows; this document only specifies the mapping over them.

**No owner decisions outstanding.** §6.2's carrier was settled by D-174; `project.name` is a Slice-A audit row,
not an owner ruling; `value_selector` and `predicate_from` are data-schema additions inside D-172/D-174's
already-decided in-bundle declarative mapping — none needs a new decision. The only genuinely-open owner
question is `header/2` (below), and it is not on Slice B's path.

**Review round 6 is scoped, not a fresh sweep — and revision 7 does not declare itself clean.** Rounds 3–5
each found that the *previous* revision's fix introduced a new defect of the same class, and revision 6's
consolidation still left the routing predicate for bullets in prose, project identity mapped backwards, and
the range-split unrepresentable. Revision 7 answers the *class* — it stops patching an under-powered interface
and instead fixes the interface: a closed operation set (O1–O6), `entry_kind_model` as a real object both
splits resolve through, and a completeness proof (§6.2a-proof). But a revision whose whole thesis is "this
time the interface is complete" has *not* earned a first-clean claim; the completeness argument is precisely
what round 6 must try to break. Round 6's charge is narrow:
1. **Is the operation set actually closed?** Find a §6.1 bucket, or a plausible near-neighbour, that needs an
   operation outside O1–O6 — the falsification the anti-loop check invites. If one exists, it is a **seventh
   O-row and a schema field**, not a Python branch.
2. **Do both splits truly resolve through the one `entry_kind_model` object** (§6.2a-proof), with no predicate
   still chosen in prose for either metadata or bullets?
3. **Is O3b's grounding sound** — both `project.dates` slots grounding against the raw `dates` field while
   carrying distinct `year_month` typed values, with distinct `candidate_id`s?
4. **Is O3c's grounding sound** — `project.name` grounding against whichever coalesce field (`title` or
   `heading`) actually supplied the value (`display_from: chosen`)?
5. **Is §6.7-plumbing's four-item doc-add list complete**, and consistent with the "parse-lenient,
   validation-strict" reconciliation?
6. **Is §7a's three-record Gate-B accounting right** — 2 education + `header/2`, with the exclusion path a
   real second route?

A re-sweep of settled ground (D-170/172/173/174/175/176, the grounding model, the drain, the
ambiguity/literal-segment grammar, the schema-v2 version trio) would re-derive rather than converge and is out
of scope.

**Plan tasks, deliberately not designed here (§6.2a):** the `dates` range grammar — which feeds *both* the
`date_range` construction for `experience` and the `range_start`/`range_end` component split for `project` (now
selectable via O3b) — and skill-id derivation from a skill item.

**Resolved since revision 6, recorded so it is not reopened:** rev 6's §9 flagged the project-`dates`
"one source field → two typed values" gap as unresolved. Revision 7 closes it with the O3b `value_selector`
element (§6.2a); the design now *can* select the range's start for one predicate and its end for the other.
Only the string-level range grammar remains, and that is a plan task, not an interface gap.

**Owner question, and now a Gate-B blocker (§7a):** `header/2` (an email) is `no_predicate_exists`, so it is
`review_required` and blocks predicate 4. It is not on Slice B's *candidate* path, but Gate B does not close
until the owner either adds a contact predicate (a Slice-A audit row) or excludes `header/2` with a reason.
Rev 6 filed this as "not blocking"; §7a corrects that — it blocks Gate B, just not via Slice C.

## 10. What must not be re-derived

- The renderer never reads `Resume.header` or `Resume.education` (D-156), so those buckets cannot change a
  PDF regardless of disposition.
- Projection filters skills on `allowed_surfaces` alone — **not** `verification_state`, **not**
  `usage_context` (`projection/contract.py:28-42`). So even once §6.8 records the distinction, **nothing
  downstream reads it**, and a skill in an unavailable state still renders. Pre-existing, not this design's
  to close.
- The résumé's skills section is assembled from `{config_dir}/projection.yaml`, the owner's editorial file
  naming bundle skill ids (`projection/pool.py:145-151`), so the owner retains explicit curation.
