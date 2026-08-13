# Canonical Career-Profile Bundle

**Date:** 2026-08-10
**Status:** READY-FOR-IMPLEMENTATION
**Scope:** Private professional knowledge and evidence source only

## 1. Purpose

Boardwatch needs one private, structured, authoritative source for a user's complete professional
history. The source must be sufficient to understand, validate, and update the profile without
re-reading prior résumé repositories, portfolio notes, project repositories, or other upstream
material.

The canonical source is an organized local bundle, not a single oversized file and not an index
whose truth still depends on external sources. It stores the complete professional inventory,
atomic facts, evidence needed to evaluate those facts, conflicts and owner rulings, metrics,
skills, approved claim candidates, visibility rules, and professional application-only facts.

This design establishes the trustworthy input side of the system. It does not implement résumé
projection, JD-specific selection, tailoring, summary selection, rendering, PDF quality, or
representative-JD evaluation. Those require later designs after the knowledge source is complete
and validated.

## 2. Goals

1. Keep one final professional knowledge source in one private local location.
2. Represent the user's complete professional history, including material that is not currently
   résumé-eligible or public.
3. Make every accepted fact traceable to self-contained evidence in the bundle.
4. Preserve uncertainty, contradictions, stale material, and rejected claims instead of silently
   resolving or deleting them.
5. Make metrics, project status, visibility, and skill support structurally enforceable.
6. Support safe updates by a person or an LLM through readable YAML and deterministic tooling.
7. Produce stable bundle revisions and content digests for future artifact lineage.
8. Keep personal data, evidence, and diagnostics outside the generalized repository.

## 3. Non-goals

This phase does not:

- Select facts for a particular résumé or job description.
- Decide whether SDE, backend, iOS, or another role family produces the best résumé.
- Generate or rewrite résumé prose at runtime.
- Evaluate résumé craft, page fit, ATS parsing, taxonomy coverage, or tailoring quality.
- Change Boardwatch's current `Resume` model, renderer, page gate, or artifact schema.
- Import demographic, EEO, health, financial, or unrelated personal data.
- Copy entire source repositories or large binary archives into the bundle.
- Treat an LLM judgment as evidence or as a substitute for deterministic validation.

## 4. Architectural decision

### 4.1 Selected approach

Use a private canonical career-profile bundle that later compiles into Boardwatch's existing frozen
`Resume` projection model.

The current `resume.yaml` remains an output-oriented render skeleton. Expanding it into a complete
knowledge base would mix factual authority, evidence, conflict management, selection policy, and
one-page layout concerns in one model. A SQLite career ledger would support querying but would add
migrations and make the source harder to inspect, edit, back up, and review while the data model is
still evolving.

A private Git repository of YAML was also evaluated as the revision substrate. Git provides strong
content addressing, history, and ref updates, but it is not selected as a required product dependency:
the bundle must work without a Git executable or repository configuration; an ordinary checkout can
rewrite historical files; Git does not provide the bundle's typed validation, evidence-blob limits,
or owner-approval semantics; Git identifies raw bytes rather than the bundle's normalized semantic
YAML, so harmless formatting changes would alter identity; and storing private evidence blobs in Git
would make removal and backup policy harder. The design deliberately implements only the small
object-model subset needed for normalized identity and domain validation. A user may put the whole
encrypted bundle under private version control as an additional backup, but Boardwatch does not
treat Git state as authority.

The bundle is therefore the authority. Future résumé projections will be derived products.

### 4.2 Future integration boundary

The later data flow is:

```text
canonical bundle
    -> strict validation
    -> role-family projection
    -> existing frozen Resume model
    -> JD-specific selection and reordering
    -> existing safety and layout gates
    -> Python-owned LaTeX and PDF artifacts
```

Only the first two nodes—canonical bundle and strict validation—are in this design. The boundary is
recorded now so this phase does not accidentally encode renderer or tailoring decisions into the
knowledge schema.

## 5. Privacy and location

The bundle path is user-configurable. Boardwatch resolves it at the command boundary as
`settings.config_dir / "career-profile"`, with an explicit `--bundle PATH` override. It is not a new
`Settings` field: the path is machine-local and this phase does not change lead selection or
`policy_version`. The resulting macOS default is:

```text
~/Library/Application Support/boardwatch/career-profile/
```

The generalized Boardwatch repository may contain only:

- Typed schema and validation code.
- General CLI mechanisms.
- Synthetic fixtures and examples.
- General documentation that contains no personal values.

The repository must never contain a real user's profile, evidence, conflict decisions, claim text,
diagnostics containing personal values, or generated bundle revisions.

The bundle may be relocated for encrypted backup. Boardwatch stores or accepts only its configured
path and derives its identity from validated content, not from the absolute path.

## 6. Physical organization and revision model

The bundle root is one authority and contains all active and historical professional knowledge.
The logical content of a revision is:

```text
manifest.yaml
facts/
  identity.yaml
  education.yaml
  experience/
  projects/
  publications.yaml
  awards.yaml
  certifications.yaml
  affiliations.yaml
  courses.yaml
  presentations.yaml
  patents.yaml
claims/
  bullet-candidates.yaml
  summary-candidates.yaml
skills/
  inventory.yaml
metrics/
  records.yaml
evidence/
  records.yaml
conflicts/
  groups.yaml
  rulings.yaml
policy/
  predicates.yaml
  units.yaml
  relations.yaml
  sources.yaml
  skill-categories.yaml
  assertion-tags.yaml
  secret-scan.yaml
relations/
  records.yaml
imports/
  source-ledger.yaml
  candidates.yaml
  exclusions.yaml
application/
  gated-facts.yaml
history/
  changes.yaml
  approvals.yaml
```

To make multi-file promotion and history honest, the physical root adds revision machinery:

```text
career-profile/
  CURRENT
  career-profile.lock
  local-sources.yaml
  approvals/
  revisions/
    sha256-<64-hex-bundle-digest>/
      <logical revision tree>
      COMPLETE
  drafts/
  blobs/
    sha256/
      <full-digest>
```

`CURRENT` contains the revision number and full digest of one immutable validated revision, whose
directory is named only by that full digest. Human-readable revision numbers remain manifest and
ledger fields; they are not filesystem identity. Promotion uses Boardwatch's existing cross-platform
`filelock.FileLock` dependency for exclusive writers;
introducing a POSIX-only `flock` primitive would contradict the existing portability contract.
Readers do not need a shared lock: they read `CURRENT` exactly once, resolve that immutable revision,
require its `COMPLETE` marker, and verify its manifest identity. They never read `drafts/` or follow a
second `CURRENT` value during the same operation.

`FileLock`'s operating-system lock is released when its owning process exits; the lockfile path may
remain without representing a held lock. Boardwatch must never break or remove a lock based only on
PID age, timestamp, or file existence. An optional PID/host/start-time sidecar may improve contention
diagnostics but is never lock authority, matching the live scan-lock contract.

Promotion is process-crash consistent:

1. Acquire the exclusive bundle lock non-blocking. Contention returns the typed
   `bundle_lock_held` could-not-complete outcome.
2. Re-check that the draft parent is still `CURRENT`. A mismatch returns `stale_draft_parent`
   without changing or deleting the draft.
3. Derive the next revision as `CURRENT.revision + 1`; revision numbers are contiguous along the
   selected chain.
4. Validate the still-current direct parent's manifest envelope, source documents, schema, canonical
   document digests, and change, approval, and ruling ledgers; compare those ledgers with the draft as
   exact canonical prefixes; and validate the draft and its owner-approval stamp against the candidate
   digest. The one recovery exception is a parent whose source documents remain parseable but whose
   referenced evidence blob is missing or fails its raw-byte digest. Promotion reports that evidence
   quarantine, skips only the parent's blob-integrity and completeness checks, and may promote a fully
   valid replacement draft. Document corruption, manifest/directory disagreement, an unsupported parent
   schema, or a changed ledger prefix still blocks promotion.
5. Write the next revision to a same-filesystem temporary directory.
6. Re-read and validate the temporary revision from disk, then write its `COMPLETE` marker last.
7. Rename the complete directory to `revisions/sha256-<full-bundle-digest>`. If that target already
   exists after a torn earlier attempt, re-read it and require an identical logical tree, matching
   digest-named directory, matching `COMPLETE`, and matching manifest digest. On an exact match,
   discard only this attempt's temporary directory and continue at step 8 using the existing complete
   directory. Any missing marker or content mismatch returns typed `promotion_target_conflict` without
   changing `CURRENT` or either retained directory.
8. Write a temporary `CURRENT`, flush and close it, then replace `CURRENT` atomically.
9. Release the lock.

An interrupted step before the pointer replacement leaves `CURRENT` unchanged. `inventory` reports
incomplete temporary directories and complete-but-unselected digest directories; neither blocks a
later promotion because digest names do not reserve a revision-number slot. No command automatically
deletes them in this phase. `inventory` never adopts them; `promote` may reuse only the exact complete
digest target that it has independently recomputed from the current draft under step 7. Manifest revision, final change-ledger revision, and
change-ledger length must agree. This is a process-crash guarantee, not a claim that every filesystem
and storage device provides stronger power-loss durability than its documented rename and flush
semantics.

Evidence snapshots are content-addressed, write-once by contract, and tamper-detected; filesystem
permissions are defense in depth rather than an immutability guarantee. Blobs are shared across revisions. The bundle is
self-contained because every evidence record required by the active revision points to a blob
inside this root. Large external originals may remain outside the bundle, but they are not required
to evaluate an accepted fact.

`local-sources.yaml` maps logical source IDs to machine-local absolute roots. It is excluded from
revision and evidence digests, never exported, and contains no professional facts. Revisioned
`policy/sources.yaml` contains only portable source metadata and relative locators.

`facts/identity.yaml` owns the one person entity and its contact records;
`facts/education.yaml` owns education entities; and each of `facts/publications.yaml`,
`facts/awards.yaml`, `facts/certifications.yaml`, `facts/affiliations.yaml`, `facts/courses.yaml`,
`facts/presentations.yaml`, and `facts/patents.yaml` owns the named entity kind. Files under
`facts/experience/` and `facts/projects/` each own one employment or project entity and are named
`<entity-id>.yaml`; the basename must equal the contained entity ID. Entity-owned files also own their
subjects' atomic facts except that application-only facts live in `application/gated-facts.yaml`.
`metrics/records.yaml`, `conflicts/groups.yaml`, `conflicts/rulings.yaml`, and
`imports/candidates.yaml` respectively own every metric, conflict, ruling, and import-candidate record.
The other declared aggregate files own the record kinds named by their sections. The known-file grammar
is closed, so any other filename or extension is invalid. Future projection designs may add persona and selection policy files under `policy/`
without moving the career knowledge. Gate A does not define or accept those files yet; unknown-file
validation prevents an undeclared tailoring policy from becoming authority accidentally.

Direct YAML editing operates on a draft checkout. A validated draft becomes a new immutable
revision; an existing revision is never edited in place.

`COMPLETE` is the sole declared non-source file inside a final revision directory. It contains the
full bundle digest, is excluded from the logical-tree digest, and must agree with the digest-named directory,
manifest, and `CURRENT` when selected. Every other undeclared file remains invalid.

## 7. Manifest and canonical identity

Each revision has one `manifest.yaml` with:

```yaml
schema_version: 1
state: revision
profile_id: profile.example-candidate
revision: 2
parent_bundle_digest: "sha256:<previous-root-digest>"
bundle_digest: "sha256:<current-root-digest>"
evidence_set_digest: "sha256:<evidence-record-and-blob-digest>"
created_at: "2026-08-10T12:00:00Z"
created_by: owner
change_id: change.000002
approved_candidate_digest: "sha256:<draft-content-digest>"
approval_stamp_id: approval-stamp.000002
predicate_catalog_version: 1
unit_catalog_version: 1
relation_catalog_version: 1
skill_category_catalog_version: 1
assertion_tag_catalog_version: 1
secret_scan_ruleset_version: 1
```

`profile_id` is stable across all revisions. `revision` is a monotonically increasing integer.
`parent_bundle_digest` is required after revision 1 and makes the local history explicit even when
the bundle is not stored in Git. Revision directories use the full bundle digest after it exists;
directory names are never digest inputs and revision numbers never appear in directory names.

YAML is parsed only by a pinned `CareerProfileLoader` built on PyYAML `>=6.0,<7.0` `SafeLoader`.
Gate A must narrow the live repository's current `pyyaml>=6.0` dependency and lock metadata to that
upper-bounded range before relying on this loader contract. The
loader rejects duplicate mapping keys, merge keys, anchors, aliases, and every explicitly written
YAML tag. It keeps SafeLoader's YAML 1.1 implicit resolvers and consults them as an ambiguity oracle
for plain scalars; values that the resolver would coerce outside the narrowed contract are rejected
rather than constructed. The positive allowlist recognizes null only as an empty scalar, `null`, or
`~`; booleans only as `true` or `false`; integers only in ordinary base-10 syntax without ambiguous
leading zeroes; and plain strings only when they begin with an ASCII letter or underscore. Dates,
year-months, decimal values, IDs, punctuation-leading strings, and string values that resemble
booleans, nulls, or numbers are quoted strings in the authoring contract. Non-finite numbers are
forbidden.

Canonical identity is computed only after typed Pydantic parsing. The implementation dumps each
validated model in JSON mode, normalizes all strings to Unicode NFC, encodes dates and datetimes as
ISO 8601 strings, keeps booleans as JSON booleans and integers as base-10 JSON integers, and
serializes with the equivalent of `json.dumps(value, sort_keys=True, separators=(",", ":"),
ensure_ascii=False, allow_nan=False)`. List order remains significant; mapping order and YAML
formatting do not.

The canonical bundle digest is computed in this order:

1. Parse and validate every declared source file, explicitly including `manifest.yaml`, using paths
   relative to the revision root. Do not compute the manifest leaf yet.
2. Read evidence records only from `evidence/records.yaml`. Compute the raw-byte SHA-256 for every
   blob capture, deduplicate identical blob digests, and sort the unique full digests. Inline captures
   contribute through the normalized evidence document and have no separate blob leaf.
3. Canonical-JSON serialize `[normalized_evidence_records, sorted_unique_blob_digests]`, hash it, and
   place the resulting `sha256:<hex>` value into `manifest.evidence_set_digest`.
4. Compute every non-manifest document leaf. Prefix revision leaves as
   `doc:<revision-root-relative-path>` and blob leaves as `blob:sha256:<full-digest>`. Blob filesystem
   paths are never identity inputs.
5. Replace `manifest.bundle_digest` with the reserved empty-string sentinel, canonicalize the now-
   final manifest, and compute its `doc:manifest.yaml` leaf.
6. Sort all `[canonical_key, leaf_digest]` pairs by canonical key, canonical-JSON serialize that list
   of two-element lists, SHA-256 hash the exact UTF-8 bytes, and store `sha256:<hex>` as
   `bundle_digest`.

Every document and blob leaf digest uses the same lowercase `sha256:<64-hex>` textual form; no bare
hex or delimiter-concatenated framing is permitted in the bundle identity algorithm.

`evidence_set_digest` excludes the manifest and therefore introduces no digest cycle. The bundle
ships a new, private-to-this-subsystem canonical serializer. It must not modify, consolidate, or
replace `eligibility/hashing.py`, `extract/taxonomy.py::_version_of`,
`eligibility/catalog.py::_version_of`, `tailor/persona.py::_version_of`, or their callers. Those live
hashes deliberately use different serialization and feed existing stored identities and
`policy_version`; changing them would alter ledger staleness semantics. Characterization tests pin
their current non-ASCII output before the bundle serializer is added.

The candidate-content digest used for approval applies the same canonical leaf algorithm to a
precisely defined candidate view of the proposed logical tree. That view omits
`history/approvals.yaml`; retains `history/changes.yaml` only through the direct parent's prefix; sets
manifest `state: draft` and `draft_of_revision` to the direct parent's revision (or `null` for revision
1); omits the promotion-derived `revision`, `created_at`, and `created_by` fields; and replaces
`approved_candidate_digest`, `approval_stamp_id`, `change_id`, and `bundle_digest` with empty-string
sentinels. It includes every proposed owner-gated state and every other draft document.

The digest remains recomputable after promotion. Starting from a promoted revision, validation omits
`history/approvals.yaml`, removes exactly the final change record named by the manifest's `change_id`,
derives `draft_of_revision` from the direct parent's stable manifest envelope, applies the same
manifest omissions and sentinels, and recomputes the candidate view. The result must equal both
`manifest.approved_candidate_digest` and the approval stamp's `candidate_content_digest`. This inverse
normalization is validation-only and never rewrites the revision.

A target-record content digest is the canonical digest of that normalized record before any external
approval metadata is attached; target records never embed their approval IDs. `profile-bundle approve`
creates one revision approval stamp bound to the candidate digest and containing any number of typed
sub-approval entries. Promotion appends that one stamp to `history/approvals.yaml`, writes its ID and
the approved candidate digest to the manifest, appends the promotion-derived change record, and
computes the final bundle digest.

Unknown files inside a revision are a validation error. Temporary files, drafts, complete-but-
unselected revisions, and unreferenced blobs are outside the active revision digest and are reported
by `inventory`. All completed revisions and captured blobs are retained in this phase; automatic
history pruning, blob garbage collection, and cleanup deletion are forbidden.

Schema evolution is append-only. Schema v1 is the bootstrap release and supports exactly `{1}`;
there is no invented v0 document shape or `0 -> 1` migration. On a v1 bundle,
`profile-bundle migrate` returns `already_current` and performs no write. Beginning when schema v2 is
designed, readers support the current schema version and the immediately preceding version, and the
design for every bump must include the exact previous-version fixture and forward migration.
Normal validation fully recomputes only the selected revision. Ancestor traversal
reads a stable manifest envelope and verifies that each child's `parent_bundle_digest` equals the
stored `bundle_digest` of the digest-named parent; it does not reparse ancestor domain models or
recompute ancestor document/blob bytes. A missing or unreadable ancestor yields the typed
`unverifiable_ancestor` completeness blocker but does not make the selected revision structurally
invalid. An optional deep history audit may recompute any intact revision whose schema is still
supported, but that is not a precondition for using the selected revision.

A schema bump requires a pinned schema-head test and `profile-bundle migrate`, which creates a new revision with a change record such as
`schema_migration: "1 -> 2"`; existing revisions are never rewritten.

Any record-shape change or addition to a code-defined closed enum—including entity kinds,
verification states, evidence classes, claim states, or ruling decisions—bumps `schema_version`.
Adding data to a revision-owned predicate, unit, relation, source, skill-category, or assertion-tag
catalog changes that catalog's version and the bundle digest but does not bump the schema unless the
catalog entry shape changes.
A validator encountering a bundle schema newer than it supports returns the typed
`unsupported_schema_version` could-not-complete outcome rather than misreporting an unknown enum.

## 8. Stable identifiers

Every profile, source, source record, import candidate, entity, contact, relation, fact, metric, evidence record,
conflict, ruling, skill, claim candidate, approval sub-entry, approval stamp, and change has an
explicit stable ID.

The prefix is part of the type, not a naming convention. IDs use lowercase namespaced tokens and
must match the closed record-kind grammar:

```text
^(profile|source|source-record|candidate|person|education|employment|project|publication|award|certification|affiliation|course|presentation|patent|contact|relation|fact|metric|evidence|conflict|ruling|skill|claim|approval|approval-stamp|change)\.[a-z0-9]+(?:[._-][a-z0-9]+)*$
```

Synthetic examples include:

```text
project.packet-pantry
fact.packet-pantry.status.001
metric.packet-pantry.throughput.001
evidence.packet-pantry.benchmark.001
conflict.packet-pantry.launch-date
claim.packet-pantry.backend.001
```

Every reference field is typed to its target record kind, so an evidence ID cannot satisfy a metric
reference merely because the string exists. An ID is never automatically regenerated from a
display-name change. A corrected fact receives a new fact ID and a `supersedes_fact_ids` edge; the
old record remains immutable. Its effective superseded state is derived from that edge instead of
mutating history. Renaming an entity creates a new revision of the entity record while preserving
its ID and prior revision history.

## 9. Domain entities

The schema uses typed professional entities rather than résumé sections. The initial closed entity
catalog is:

- `person`
- `education`
- `employment`
- `project`
- `publication`
- `award`
- `certification`
- `affiliation`
- `course`
- `presentation`
- `patent`

Each entity has:

- `entity_id`
- `entity_type`
- `display_name`
- zero or more aliases
- a controlled status appropriate to its entity type
- creation and review dates
- atomic fact records

Initial status catalogs are:

| Entity | Statuses |
|---|---|
| education | `in_progress`, `completed`, `withdrawn` |
| employment | `planned`, `offer_only`, `active`, `completed` |
| project | `concept`, `prototype`, `active_development`, `completed`, `shipped_private`, `shipped_open_source`, `live_public`, `sunset` |
| publication | `draft`, `submitted`, `accepted`, `published` |
| award | `nominated`, `awarded` |
| certification | `active`, `expired`, `revoked` |
| affiliation | `planned`, `active`, `past` |
| course | `planned`, `in_progress`, `completed`, `withdrawn` |
| presentation | `proposed`, `accepted`, `delivered`, `cancelled` |
| patent | `draft`, `filed`, `published`, `granted`, `abandoned` |

Status does not itself prove an accomplishment. For example, an active volunteer affiliation may
exist without any contribution facts. A future claim validator must not permit accomplishment
claims merely because the affiliation is real.

Contact channels are typed records attached to the single `person` entity, not unstructured strings:

```yaml
contact_id: contact.example.email
person_id: person.example-candidate
channel_type: email
value: candidate@example.com
allowed_surfaces:
  - resume
  - application
verification_state: owner_confirmed
```

The closed initial channel types are `email`, `phone`, `profile_url`, and `location`. Contact values
and their surfaces require a `confirm_contact` sub-approval in the revision's single approval stamp.

Cross-entity relationships are explicit records in `relations/records.yaml`; a single-valued fact
subject is never overloaded to express them. The initial closed relation catalog includes
`project_at_employment`, `course_at_education`, `presentation_for_project`,
`publication_about_project`, and `patent_for_project`. Each relation declares typed source and target
entity kinds in `policy/relations.yaml`.

## 10. Atomic facts

Facts are typed assertions about one subject. A fact record contains:

```yaml
fact_id: fact.packet-pantry.language.001
subject_id: project.packet-pantry
predicate: technology.used
value:
  type: skill_ref
  skill_id: skill.rust
verification_state: verified
verification_basis: repository_verified
usage_context: personal_project
evidence_ids:
  - evidence.packet-pantry.manifest.001
allowed_surfaces:
  - resume
  - public
conflict_group_id: null
reviewed_at: "2026-08-10"
expires_at: null
supersedes_fact_ids: []
import_lineage:
  source_id: source.legacy-project-notes
  source_locator: projects/packet-pantry.md#stack
  source_content_digest: "sha256:<64 lowercase hexadecimal characters>"
notes: null
```

### 10.1 Value types

The initial value union supports:

- string
- integer
- decimal encoded as a string
- boolean
- date
- year-month
- closed or open date range
- URL
- string list
- skill reference

Pydantic discriminated unions enforce the expected payload for each type. Predicate contracts are
closed, versioned data in `policy/predicates.yaml`, not an implicit collection of code branches. Each
predicate entry declares:

- predicate ID and catalog version;
- legal subject entity kinds;
- legal value types;
- cardinality and exclusivity rules;
- minimum evidence classes and verification bases;
- whether owner attestation is an allowed authority;
- legal surfaces and any surface-specific restrictions;
- whether the predicate may ground a skill and its legal usage contexts;
- expiry behavior and review requirements.

Code validates the catalog's own schema and applies it exhaustively. An unknown predicate is a hard
failure; extending the catalog requires a versioned policy edit inside a new bundle revision.

Every fact also declares one `usage_context`: `professional`, `academic`, `personal_project`,
`contribution`, `publication`, `volunteer`, or `incidental`. Context describes how the subject used or
encountered the asserted material; it does not change evidence strength. `incidental` can never
ground a verified skill.

### 10.2 Verification states

The closed fact-state catalog is:

- `verified`: evidence satisfies the predicate's evidence contract.
- `owner_confirmed`: owner attestation is the appropriate authority for this predicate.
- `unresolved`: a candidate value exists but no ruling selected it.
- `stale`: once-valid information needs re-verification.
- `rejected`: evidence or an owner ruling determined the assertion must not be used.
- `superseded`: a newer fact replaced this fact without erasing history.

`owner_confirmed` is not a weaker synonym for `verified`. Predicate contracts explicitly state
when owner attestation is sufficient. It may settle an intended title or preferred public wording;
it cannot prove repository implementation, publication, or measured performance. Draft YAML may
request an owner-confirmed transition but cannot establish one merely by containing the string
`owner_confirmed`.

The closed `verification_basis` catalog is `public_record_verified`,
`private_document_verified`, `repository_verified`, `measured`, `owner_attested`,
`secondary_only`, and `multiple_sources`. The validator checks that a fact's basis agrees with its
referenced evidence classes and the predicate's minimum evidence contract.

### 10.3 Surface policy

`allowed_surfaces` is a set drawn from:

- `resume`
- `public`
- `application`

Internal storage is implicit and is not an authored surface. An empty set means the fact is private
knowledge only. `application` does not imply `resume` or `public`. A fact cannot inherit permission
from its parent entity. For each declared skill surface, at least one eligible supporting fact must
independently allow that surface; equivalently, a skill's surfaces are a subset of the union of its
eligible supporting facts' surfaces. Recording an additional true fact cannot narrow an already
grounded skill. A claim's surfaces remain a subset of the intersection of all required facts and
metrics because every required record is conjunctive support for the complete wording. These graph
invariants prevent an application-only fact from widening into a public skill or claim.

Metric surfaces are owner-declared and require an `approve_metric_surfaces` sub-approval bound to the
metric's target-content digest; private supporting evidence may legitimately
verify a public metric, so evidence-record visibility is not intersected into the metric's surface.
Relations are internal knowledge records and have no `allowed_surfaces` field in this phase. Any
future projection of a relation requires a separate policy design rather than inheriting permission
implicitly.

Downstream eligibility is derived. A fact is unavailable when any of these hold:

- its verification state is unresolved, stale, rejected, or superseded;
- its conflict group is unresolved;
- its evidence is missing, invalid, contradicted without a ruling, or below the predicate's
  required standard;
- the requested surface is absent;
- the subject's status is incompatible with the assertion.

This design stores the information needed for that derivation. Actual résumé projection is a later
phase.

### 10.4 Initial predicate catalog and skill-category mechanism

`policy/predicates.yaml` begins with the following closed catalog. “Surfaces” are maxima; each fact
may declare any subset allowed by the row. `surface_policy` is the closed catalog `standard` or
`application_only`; the latter forbids `resume` and `public` even if a future catalog edit accidentally
widens the maximum. Cardinality and exclusivity are evaluated only over effective facts: a fact must
have state `verified` or `owner_confirmed`, must not be superseded by an active edge, and must not be
blocked by an unresolved conflict. Retained `unresolved`, `stale`, `rejected`, and `superseded` records
therefore do not make a correction exceed cardinality. Competing otherwise-effective values must be
inside one declared conflict group until a ruling selects an effective value.

Every serialized predicate entry repeats every column across both tables below. There are no parser
defaults, implicit evidence-strength substitutions, or implicit “all contexts” fallback. `none` is an
explicit exclusivity rule; `never; null` means no automatic expiry and no fixed review interval.
Omitting any field from the actual YAML is invalid. Each listed minimum evidence class is independently
sufficient unless the entry lists a combination; every legal verification basis must be backed by its
corresponding evidence class. `owner_attestation_authority` is the closed catalog `none`, `verified`, or
`owner_confirmed`; all initial predicates that admit owner attestation use `owner_confirmed`, never
`verified`.

| Predicate | Legal subjects | Value type | Cardinality | Exclusivity | Surfaces | Surface policy | Legal usage contexts | Expiry; review | Skill grounding |
|---|---|---|---|---|---|---|---|---|---|
| `person.professional_name` | person | string | one | none | resume, public, application | standard | professional | never; null | no |
| `person.professional_headline` | person | string | one | none | resume, public, application | standard | professional | never; null | no |
| `education.institution` | education | string | one | none | resume, public, application | standard | academic | never; null | no |
| `education.credential` | education | string | many | none | resume, public, application | standard | academic | never; null | no |
| `education.field` | education | string | many | none | resume, public, application | standard | academic | never; null | no |
| `education.start_date` | education | year-month | one | none | resume, public, application | standard | academic | never; null | no |
| `education.end_date` | education | year-month | one | none | resume, public, application | standard | academic | never; null | no |
| `education.result` | education, course | decimal-string or string | many | none | resume, application | standard | academic, professional | never; null | no |
| `employment.organization` | employment | string | one | none | resume, public, application | standard | professional | never; null | no |
| `employment.title` | employment | string | many | none | resume, public, application | standard | professional | never; null | no |
| `employment.date_range` | employment | date range | one | one effective range; start <= end | resume, public, application | standard | professional | never; null | no |
| `employment.responsibility` | employment | string | many | none | resume, public, application | standard | professional | never; null | no |
| `employment.accomplishment` | employment | string | many | none | resume, public, application | standard | professional | never; null | no |
| `employment.team_size` | employment | integer | one | none | resume, public, application | standard | professional | never; null | no |
| `project.summary` | project | string | one | none | resume, public, application | standard | professional, academic, personal_project, contribution, volunteer | never; null | no |
| `project.start_date` | project | year-month | one | none | resume, public, application | standard | professional, academic, personal_project, contribution, volunteer | never; null | no |
| `project.end_date` | project | year-month | one | none | resume, public, application | standard | professional, academic, personal_project, contribution, volunteer | never; null | no |
| `project.contribution` | project | string | many | none | resume, public, application | standard | professional, academic, personal_project, contribution, volunteer | never; null | no |
| `deployment.environment` | project, employment | string enum: development, staging, production | many | none | resume, public, application | standard | professional, personal_project, contribution, volunteer | never; null | no |
| `technology.used` | education, employment, project, course, publication | skill reference | many | none | resume, public, application | standard | professional, academic, personal_project, contribution, publication, volunteer | never; null | yes |
| `publication.title` | publication | string | one | none | resume, public, application | standard | publication, academic, professional, contribution | never; null | no |
| `publication.venue` | publication | string | one | none | resume, public, application | standard | publication, academic, professional, contribution | never; null | no |
| `publication.date` | publication | date | one | none | resume, public, application | standard | publication, academic, professional, contribution | never; null | no |
| `entity.location` | education, employment, project, presentation, affiliation | string | many | none | resume, public, application | standard | professional, academic, personal_project, contribution, publication, volunteer | never; null | no |
| `entity.url` | project, publication, patent, presentation, certification, affiliation | URL | many | none | resume, public, application | standard | professional, academic, personal_project, contribution, publication, volunteer | never; null | no |
| `recognition.name` | award, certification | string | one | none | resume, public, application | standard | professional, academic, contribution, volunteer | never; null | no |
| `recognition.issuer` | award, certification | string | one | none | resume, public, application | standard | professional, academic, contribution, volunteer | never; null | no |
| `award.date` | award | date | one | none | resume, public, application | standard | professional, academic, contribution, volunteer | never; null | no |
| `certification.issue_date` | certification | date | one | none | resume, public, application | standard | professional, academic | never; null | no |
| `certification.expiry` | certification | date | one | one effective value | resume, public, application | standard | professional, academic | block active use after value date; null | no |
| `affiliation.role` | affiliation | string | many | none | resume, public, application | standard | professional, academic, volunteer | never; null | no |
| `affiliation.date_range` | affiliation | date range | one | one effective range; start <= end | resume, public, application | standard | professional, academic, volunteer | never; null | no |
| `course.title` | course | string | one | none | resume, public, application | standard | academic, professional | never; null | no |
| `presentation.title` | presentation | string | one | none | resume, public, application | standard | professional, academic, publication, volunteer | never; null | no |
| `presentation.date` | presentation | date | one | none | resume, public, application | standard | professional, academic, publication, volunteer | never; null | no |
| `presentation.venue` | presentation | string | one | none | resume, public, application | standard | professional, academic, publication, volunteer | never; null | no |
| `patent.title` | patent | string | one | none | resume, public, application | standard | professional, academic, personal_project, contribution | never; null | no |
| `patent.filing_date` | patent | date | one | none | resume, public, application | standard | professional, academic, personal_project, contribution | never; null | no |
| `patent.grant_date` | patent | date | one | none | resume, public, application | standard | professional, academic, personal_project, contribution | never; null | no |
| `application.requires_sponsorship` | person | boolean | one | one effective value | application | application_only | professional | never; 90 days | no |
| `application.authorized_regions` | person | string list | one | one effective set | application | application_only | professional | never; 90 days | no |

| Predicate | Minimum evidence classes | Legal verification bases | Owner-attestation authority |
|---|---|---|---|
| `person.professional_name` | owner_attestation | owner_attested | owner_confirmed |
| `person.professional_headline` | owner_attestation | owner_attested | owner_confirmed |
| `education.institution` | private_document | private_document_verified | none |
| `education.credential` | private_document | private_document_verified | none |
| `education.field` | private_document | private_document_verified | none |
| `education.start_date` | private_document | private_document_verified | none |
| `education.end_date` | private_document | private_document_verified | none |
| `education.result` | private_document | private_document_verified | none |
| `employment.organization` | private_document | private_document_verified | none |
| `employment.title` | private_document or owner_attestation | private_document_verified or owner_attested | owner_confirmed |
| `employment.date_range` | private_document or owner_attestation | private_document_verified or owner_attested | owner_confirmed |
| `employment.responsibility` | owner_attestation | owner_attested | owner_confirmed |
| `employment.accomplishment` | owner_attestation | owner_attested | owner_confirmed |
| `employment.team_size` | private_document or owner_attestation | private_document_verified or owner_attested | owner_confirmed |
| `project.summary` | owner_attestation | owner_attested | owner_confirmed |
| `project.start_date` | repository_artifact or owner_attestation | repository_verified or owner_attested | owner_confirmed |
| `project.end_date` | repository_artifact or owner_attestation | repository_verified or owner_attested | owner_confirmed |
| `project.contribution` | repository_artifact | repository_verified | none |
| `deployment.environment` | repository_artifact or private_document | repository_verified or private_document_verified | none |
| `technology.used` | repository_artifact, private_document, or owner_attestation | repository_verified, private_document_verified, or owner_attested | owner_confirmed |
| `publication.title` | public_record or private_document | public_record_verified or private_document_verified | none |
| `publication.venue` | public_record or private_document | public_record_verified or private_document_verified | none |
| `publication.date` | public_record or private_document | public_record_verified or private_document_verified | none |
| `entity.location` | private_document or owner_attestation | private_document_verified or owner_attested | owner_confirmed |
| `entity.url` | public_record or repository_artifact | public_record_verified or repository_verified | none |
| `recognition.name` | public_record or private_document | public_record_verified or private_document_verified | none |
| `recognition.issuer` | public_record or private_document | public_record_verified or private_document_verified | none |
| `award.date` | public_record or private_document | public_record_verified or private_document_verified | none |
| `certification.issue_date` | public_record or private_document | public_record_verified or private_document_verified | none |
| `certification.expiry` | public_record or private_document | public_record_verified or private_document_verified | none |
| `affiliation.role` | private_document or owner_attestation | private_document_verified or owner_attested | owner_confirmed |
| `affiliation.date_range` | private_document or owner_attestation | private_document_verified or owner_attested | owner_confirmed |
| `course.title` | private_document | private_document_verified | none |
| `presentation.title` | public_record or private_document | public_record_verified or private_document_verified | none |
| `presentation.date` | public_record or private_document | public_record_verified or private_document_verified | none |
| `presentation.venue` | public_record or private_document | public_record_verified or private_document_verified | none |
| `patent.title` | public_record or private_document | public_record_verified or private_document_verified | none |
| `patent.filing_date` | public_record or private_document | public_record_verified or private_document_verified | none |
| `patent.grant_date` | public_record or private_document | public_record_verified or private_document_verified | none |
| `application.requires_sponsorship` | owner_attestation | owner_attested | owner_confirmed |
| `application.authorized_regions` | owner_attestation | owner_attested | owner_confirmed |

Skill categories are field-dependent taxonomy and therefore revision-owned versioned data in
`policy/skill-categories.yaml`, never a code-defined software vocabulary. The generalized mechanism
ships only the catalog schema; Gate A uses a synthetic catalog, and Gate B gathers the private
catalog appropriate to the user's declared career field. A catalog contains `catalog_version`,
`career_field`, and entries with `category_id`, `display_name`, optional `parent_category_id`, and
aliases. Category IDs are closed for that revision. Adding an entry increments
`skill_category_catalog_version` and changes the bundle digest without a schema bump; changing the
entry shape requires a schema bump.

A verified skill requires a category present in the active private catalog and a supporting
`technology.used` fact whose predicate contract allows skill grounding, whose context is not
`incidental`, and whose evidence and surfaces remain eligible. The repository must not ship a
software-only default catalog as universal product truth.

## 11. Metrics

Metrics are first-class typed facts. A number embedded only in claim prose is not an authoritative
metric.

```yaml
metric_id: metric.packet-pantry.throughput.001
subject_id: project.packet-pantry
metric_kind: throughput
value:
  number: "120"
  unit: requests_per_second
  qualifier: approximate
display_value: "~120 requests/s"
measurement_context: "Single-node local benchmark with one producer"
measurement_method: "Committed load profile run for five minutes"
evidence_ids:
  - evidence.packet-pantry.benchmark.001
verification_state: verified
allowed_surfaces:
  - resume
  - public
allowed_phrasings:
  - "sustained approximately 120 requests/s"
  - "sustained ~120 requests/s"
forbidden_phrasings:
  - "handled thousands of requests per second"
protected_tokens:
  - "120"
  - "requests/s"
caveats:
  - severity: context_required
    text: "Do not generalize this local result to production hardware."
reviewed_at: "2026-08-10"
```

The initial closed `metric_kind` catalog is `count`, `duration`, `rate`, `throughput`, `latency`,
`percentage`, `currency`, `size`, `rank`, and `score`. The qualifier catalog is `exact`,
`approximate`, `at_least`, `more_than`, `at_most`, and `range`.

Units are closed at validation time by versioned `policy/units.yaml`. The file has
`units_version: 1` and a `units` sequence whose rows have exactly:

```yaml
unit_id: items
display_name: "items"
symbol: items
aliases:
  - item
allowed_metric_kinds:
  - count
```

`unit_id` is a lowercase ID token, `display_name` and `symbol` are nonblank strings, `aliases` is a
list of unique nonblank strings, and `allowed_metric_kinds` is a nonempty unique subset of the closed
metric-kind catalog. Unit IDs and aliases are unique across the catalog after NFC normalization.
Validation performs exact ID/alias lookup only; the catalog defines no conversions, implicit aliases,
or dimensional inference.

Gate A ships no universal built-in unit vocabulary. The comprehensive synthetic fixture declares
exactly these fixture-local rows, which exercise every initial metric kind:

```yaml
units_version: 1
units:
  - unit_id: items
    display_name: "items"
    symbol: items
    aliases: [item]
    allowed_metric_kinds: [count]
  - unit_id: milliseconds
    display_name: "milliseconds"
    symbol: ms
    aliases: [millisecond]
    allowed_metric_kinds: [duration, latency]
  - unit_id: items_per_second
    display_name: "items per second"
    symbol: items/s
    aliases: [item_per_second]
    allowed_metric_kinds: [rate, throughput]
  - unit_id: percent
    display_name: "percent"
    symbol: "%"
    aliases: [percentage]
    allowed_metric_kinds: [percentage]
  - unit_id: usd
    display_name: "US dollars"
    symbol: USD
    aliases: [us_dollars]
    allowed_metric_kinds: [currency]
  - unit_id: bytes
    display_name: "bytes"
    symbol: B
    aliases: [byte]
    allowed_metric_kinds: [size]
  - unit_id: ordinal
    display_name: "ordinal position"
    symbol: ordinal
    aliases: [place]
    allowed_metric_kinds: [rank]
  - unit_id: points
    display_name: "points"
    symbol: pts
    aliases: [point]
    allowed_metric_kinds: [score]
```

Extending a revision's registry requires a policy edit and changes the bundle digest; changing this
row shape requires a schema bump. Every metric requires a subject, method, context, evidence, and at
least one allowed phrasing before it can be considered for a future résumé.

Metric caveats are typed objects. Severity is `informational`, `context_required`, or
`disqualifying`. A `context_required` caveat must travel with any later projection of the figure; a
`disqualifying` caveat makes the metric ineligible for projection until a new metric supersedes it.
This phase validates and preserves that policy but does not perform projection.

Changing a protected value, unit, subject, or qualifier creates a new metric record and supersedes
the old one. It is never an in-place prose edit.

## 12. Evidence

Promoted evidence records are append-only by contract, and their captured bytes are content-addressed,
self-contained, and tamper-detected. The evidence-class catalog is:

- `public_record`
- `private_document`
- `repository_artifact`
- `measured_result`
- `owner_attestation`
- `secondary_summary`

An evidence record contains:

```yaml
evidence_id: evidence.packet-pantry.benchmark.001
evidence_class: measured_result
title: "Packet Pantry local throughput baseline"
origin:
  kind: repository_file
  source_id: source.packet-pantry-repository
  path: docs/baseline.md
  repository_commit: "0123456789abcdef0123456789abcdef01234567"
locator:
  kind: section
  value: "Baseline A / Results"
capture:
  kind: blob
  sha256: "<64 lowercase hexadecimal characters>"
  media_type: text/markdown
captured_at: "2026-08-10T12:00:00Z"
reviewed_at: "2026-08-10"
sufficiency_review:
  state: owner_approved
redactions: []
supports_record_ids:
  - metric.packet-pantry.throughput.001
contradicts_record_ids: []
contextualizes_record_ids: []
```

`capture` is a closed discriminated union:

```yaml
# Small capture stored directly in evidence/records.yaml
capture:
  kind: inline
  text: "Synthetic evidence excerpt sufficient to review the linked record."
  media_type: text/plain

# Larger capture stored once under blobs/sha256/
capture:
  kind: blob
  sha256: "<64 lowercase hexadecimal characters>"
  media_type: text/markdown
```

Exactly one variant is legal. Inline text is UTF-8 content in the normalized evidence document and
has no blob leaf; a blob capture must resolve to the raw bytes named by `sha256`. Both forms are
hashed. The
captured material must be sufficient to evaluate the linked fact without resolving its origin. The
revisioned source registry stores only logical source IDs, source kinds, and portable metadata;
relative paths are resolved through the non-exported local source sidecar when an owner deliberately
reopens an original.

Evidence relationships are directional and closed: `supports`, `contradicts`, or `contextualizes`.
A contextual source cannot satisfy a verification requirement. Record-to-evidence and
evidence-to-record links must agree exactly.

### 12.1 Evidence standards

Evidence strength is predicate-specific:

- A transcript or institution record can verify an education result.
- A repository artifact can verify that a technology is implemented.
- A benchmark artifact can verify a measured result within its recorded context.
- An owner attestation can verify an intended title, preferred wording, or private historical fact
  when no external record is reasonably expected.
- A secondary summary is import evidence, not final verification, unless the predicate contract
  explicitly permits it.

There is no numeric confidence score. The system records the evidence class and whether it meets
the fact's explicit contract.

Evidence sufficiency is a human judgment made mechanically auditable. A non-empty capture alone is
not sufficient. The closed `sufficiency_review.state` catalog is `unreviewed` and `owner_approved`.
Each `owner_approved` sufficiency state must match one approval-stamp sub-entry bound
to the evidence record's target-content digest. Because the evidence record embeds no approval ID,
this binding is acyclic. Unreviewed evidence is structurally valid but a completeness blocker for
every dependent accepted record.

Evidence-class structural contracts contain only machine-checkable record fields:

| Evidence class | Required record fields |
|---|---|
| `public_record` | portable origin, locator, capture, capture date |
| `private_document` | logical source ID, locator, capture, capture date |
| `repository_artifact` | logical source ID, relative path, full repository commit, capture |
| `measured_result` | capture plus at least one supported metric ID |
| `owner_attestation` | `attested_at`, capture, and at least one supported `owner_confirmed` fact whose stamp carries `confirm_fact` |
| `secondary_summary` | source ID, locator, capture, and `authoritative: false` |

Evidence classes are a discriminated Pydantic union, so class-required fields are typed rather than
free-form metadata and fields illegal for that class are rejected.

Whether a measured capture actually contains enough context and method to evaluate its linked metric,
or a repository excerpt contains the relevant code/test material, belongs to the owner sufficiency
review criteria. The validator verifies the approval binding; it does not pretend to infer adequacy
from opaque text.

Blob creation uses exclusive temporary files, verifies the raw-byte digest before atomic rename,
and marks the final file read-only where the platform supports it. Those permissions are accidental-
write protection, not a bit-rot guarantee. A corrupted blob is logically quarantined by validation
without moving or deleting its bytes, and the
active revision remains unusable until the exact digest is restored from an independently verified
encrypted backup. If no valid backup exists, the evidence is lost: the owner must recapture it into a
new blob and promote a new evidence/fact revision rather than rewriting history. `checkout` may copy
the still-parseable YAML from a selected revision with a corrupt or missing blob into a recovery
draft; promotion validates the replacement draft fully and treats the broken predecessor only as a
stored-digest ancestor link. This makes the new selected revision usable while preserving the typed
`unverifiable_ancestor` history completeness blocker.

### 12.2 Redaction and prohibited capture

Snapshots must not copy credentials, API keys, private keys, authentication cookies, demographic
answers, health data, financial data, or unrelated personal material. A redacted excerpt records
the removed region and reason. Redaction may remove unrelated sensitive content but cannot remove
the portion needed to evaluate the fact.

`profile-bundle add-evidence` and every full validation run scan canonical inline captures and blob bytes
with the manifest's closed, versioned secret-detection ruleset and fail closed on a hit. The initial
capture media allowlist is UTF-8 `text/plain`, `text/markdown`, `application/json`, and `text/csv`;
other media require a later reviewed design. Every inline or blob capture is at most 1 MiB. The total
UTF-8 byte length of all inline captures plus the raw-byte sizes of unique referenced blobs in one
active revision is at most 50 MiB. These are hard validation limits, not recommendations.

`policy/secret-scan.yaml` records the exact closed rule IDs and version that the revision passed. Its
v1 shape is `ruleset_version: 1` plus a `rules` sequence whose rows contain exactly `rule_id`,
`pattern`, and `flags`. `flags` is a unique subset of `ignore_case` and `multiline`; patterns use
Python regular-expression syntax. Rules are applied to the decoded UTF-8 text of every allowed
inline or blob capture. V1 deliberately has no entropy heuristic: low-confidence token guessing
would make structural validation noisy and non-reproducible.

The built-in v1 rules are exactly the following YAML rows. Literal block chomping keeps each pattern
free of a trailing newline.

```yaml
ruleset_version: 1
rules:
  - rule_id: private-key-block
    pattern: |-
      -----BEGIN[ \t]+(?:OPENSSH[ \t]+|RSA[ \t]+|EC[ \t]+|DSA[ \t]+|PGP[ \t]+)?PRIVATE[ \t]+KEY(?:[ \t]+BLOCK)?-----
    flags: []
  - rule_id: authorization-header
    pattern: |-
      ^[ \t]*authorization[ \t]*:[ \t]*(?:bearer|basic)[ \t]+[A-Za-z0-9._~+/=-]{8,}[ \t]*$
    flags: [ignore_case, multiline]
  - rule_id: cookie-header
    pattern: |-
      ^[ \t]*(?:cookie|set-cookie)[ \t]*:[^\r\n]{8,}$
    flags: [ignore_case, multiline]
  - rule_id: credential-url
    pattern: |-
      \b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s@]{4,}@
    flags: [ignore_case]
  - rule_id: generic-secret-assignment
    pattern: |-
      \b(?:api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|password|private[_-]?key)\b[ \t]{0,8}(?::|=)[ \t]{0,8}["']?[A-Za-z0-9._~+/=-]{8,}
    flags: [ignore_case]
  - rule_id: aws-access-key-id
    pattern: |-
      \b(?:AKIA|ASIA)[A-Z0-9]{16}\b
    flags: []
  - rule_id: github-token
    pattern: |-
      \b(?:gh[pousr]_[A-Za-z0-9]{36,255}|github_pat_[A-Za-z0-9_]{82,255})\b
    flags: []
  - rule_id: slack-token
    pattern: |-
      \bxox[baprs]-[A-Za-z0-9-]{10,255}\b
    flags: []
```

The generalized implementation ships that exact v1 catalog. A revision recording ruleset version 1
must contain rows canonically equal to the built-in v1 rows, so it cannot remove, add, reorder,
rename, or weaken them. Adding or changing a rule requires a new supported ruleset version. Structural
validation of an existing revision always scans with the exact ruleset version recorded in that
revision's manifest, so the same content has the same structural verdict. The implementation retains
every ruleset version it claims to support; an unavailable recorded version returns typed
`unsupported_secret_scan_ruleset_version` rather than a secret-hit error. A newer, stronger installed
catalog scans an older revision additionally for completeness and reports hits only as blockers
requiring recapture, rescan, and promotion; it does not retroactively make the selected revision
structurally invalid or rewrite the old manifest's assertion.

Each redaction entry is `{start, end, reason}` over the UTF-8 bytes of the stored post-redaction
capture before hashing, using the closed reasons `credential`, `unrelated_personal`, `demographic`,
`health`, `financial`, `third_party_private`, and `personal_path`. The half-open range must be valid,
non-overlapping, and contain exactly the ASCII marker `[REDACTED:<reason>]`; multiple removed regions
therefore require multiple markers and entries. The validator can verify every recorded redaction
against retained bytes without storing the removed content. The stored capture and digest are
post-redaction. Absolute home paths and user-directory locators are rejected in
all revision YAML and in the decoded bytes of every allowed inline or blob capture. Evidence must
replace such paths with portable relative locators or a recorded `personal_path` redaction; there is
no silent private-bundle exception.

## 13. Conflicts and owner rulings

The validator detects and requires explicit conflict groups for:

- different values for the same subject and single-valued predicate;
- contradictory titles, dates, statuses, technologies, or metric subjects;
- impossible or overlapping timelines under a declared exclusivity rule;
- duplicate entities under different names;
- status-language mismatches;
- facts whose supporting and contradicting evidence have no ruling.

A conflict record contains all candidates:

```yaml
conflict_id: conflict.packet-pantry.launch-date
subject_id: project.packet-pantry
predicate: project.start_date
state: unresolved
candidate_fact_ids:
  - fact.packet-pantry.start-date.001
  - fact.packet-pantry.start-date.002
active_ruling_id: null
opened_at: "2026-08-10"
```

An owner ruling is append-only:

```yaml
ruling_id: ruling.packet-pantry.launch-date.001
conflict_id: conflict.packet-pantry.launch-date
decision: select_candidate
selected_fact_id: fact.packet-pantry.start-date.002
rejected_fact_ids:
  - fact.packet-pantry.start-date.001
rationale: "The later date is the start of implementation; the earlier date was ideation."
owner_evidence_id: evidence.packet-pantry.owner-ruling.001
decided_at: "2026-08-10"
```

Allowed decisions are `select_candidate`, `replace_all`, `keep_unresolved`, and `not_applicable`.
Resolving a conflict updates its active state but does not delete candidates or prior rulings. New
evidence may create a `reopened` state and a later ruling. Appending any ruling requires an
`authorize_conflict_ruling` sub-approval whose target is that ruling and whose target-content digest
matches the proposed ruling record. A revision-level stamp with no such entry cannot authorize the
ruling merely because the YAML names the owner.

Promotion compares the draft's ruling sequence with its parent using canonical records. Every parent
ruling must remain an identical prefix in the same order; a draft may only append new rulings. The
change ledger follows the same rule and must append exactly one change record whose revision equals
the proposed manifest revision. Removing, reordering, or editing any prior entry is a hard failure.

One promoted revision appends exactly one approval stamp. The stamp may contain any number of
sub-approvals:

```yaml
approval_stamp_id: approval-stamp.000002
candidate_content_digest: "sha256:<approved-draft-digest>"
approved_at: "2026-08-10T12:00:00Z"
approved_via: controlling_terminal
entries:
  - approval_id: approval.evidence.packet-pantry.benchmark.001
    action: approve_evidence_sufficiency
    target_record_id: evidence.packet-pantry.benchmark.001
    target_content_digest: "sha256:<normalized-record-digest>"
    resulting_state: owner_approved
  - approval_id: approval.claim.packet-pantry.backend.001
    action: approve_claim
    target_record_id: claim.packet-pantry.backend.001
    target_content_digest: "sha256:<normalized-record-digest>"
    resulting_state: approved
```

The closed sub-approval action catalog is `confirm_fact`, `confirm_contact`,
`approve_evidence_sufficiency`, `approve_claim`, `approve_metric_surfaces`,
`approve_source_scope`, `approve_source_record_exclusion`, and `authorize_conflict_ruling`. The stamp itself
authorizes the candidate revision, so `entries` may be empty when it contains no additional
owner-gated transitions. Sub-approval IDs are
globally unique and indexed for referential validation, but target records do not point back to them.
The stamp's candidate digest binds the complete draft; each entry makes the specific owner decision
auditable without requiring one top-level approval record per target. Registering a new source or
changing its portable locator, kind, approved scope, or enumerator requires `approve_source_scope`
targeting the `source.*` ID. Its target-content digest is computed over the canonical two-document
source-scope view formed by joining the `policy/sources.yaml` entry and the matching
`imports/source-ledger.yaml` source entry. Declaring or changing a metric's surfaces requires
`approve_metric_surfaces` for that metric. An `owner_excluded` disposition requires
`approve_source_record_exclusion` targeting the `source-record.*` ID; its target-content digest binds
the canonical pair of the source-ledger record and its exclusion entry. Ruling authorization follows
the trigger defined above. These triggers are mandatory even when the surrounding revision stamp is
otherwise valid.

Owner authority is not inferred from YAML strings such as `owner_confirmed`, `approved`, or
`authorized_by: owner`. An agent may propose any of those transitions in a draft, but
`profile-bundle approve --draft <name>` creates a separate approval stamp under `approvals/` tied to the
draft's exact candidate-content digest and the enumerated owner-gated transitions. Candidate-content
identity excludes external approval stamps. Promotion rejects a missing, stale, or scope-mismatched
stamp; any subsequent draft content edit invalidates it. The stamp is copied to
`history/approvals.yaml`, and the final bundle manifest records the approved candidate digest. The
final bundle digest includes that audit record without creating a cycle because the approval refers
to the separately defined candidate-content digest, not the final bundle digest.

`approve` refuses when stdin or stdout is not a controlling TTY and has no `--yes`, environment,
stdin-pipe, or agent-mode bypass. It displays the candidate digest and every proposed sub-approval and
requires an interactive confirmation. This is a deliberate operator-interaction seam, not access
control: any process with write permission to the bundle can construct an otherwise valid stamp file,
and an agent with an allocated TTY and the owner's permissions can answer the prompt. Cooperative
agents are contractually required to stop and request the owner's action. The durable control is
explicit digest binding, transcript, and stamp reviewability, not a security claim that Boardwatch can
distinguish a human from an equally privileged process.

The implementation exposes one pure library constructor, `build_approval_stamp`, which accepts a
validated candidate digest and typed decisions but performs no TTY interaction and no filesystem
write. The production `approve` command calls it only after the controlling-TTY confirmation. Tests
use it directly with synthetic data to exercise promotion deterministically; that test seam does not
strengthen the cooperative control described above.

Conflicts block only dependent facts and claims. They do not invalidate unrelated verified content
or the entire bundle.

## 14. Skills

Skills are canonical records, not a free-form résumé keyword list.

```yaml
skill_id: skill.rust
canonical_name: Rust
aliases:
  - rust-lang
category: language
supporting_fact_ids:
  - fact.packet-pantry.language.001
verification_state: verified
allowed_surfaces:
  - resume
  - public
```

A verified skill requires at least one eligible supporting fact. Referencing a skill only in an
old résumé, generic skills list, course catalog, or JD is insufficient. Supporting facts may
describe implementation, professional use, substantial coursework, publication work, or another
explicit context; future projection policy can distinguish those contexts.

`skill` is a distinct typed record class, not a domain entity: it names a reusable capability whose
authority is derived from one or more entity-bound supporting facts. Its surfaces must satisfy the
per-surface supporting-fact union rule in §10.3. Role-family tags are deliberately absent because they are
selection policy deferred to the tailoring design.

This phase stores canonical names and aliases but does not change Boardwatch's JD taxonomy. Mapping
the profile inventory to extraction taxonomy is part of a later tailoring design.

## 15. Approved claim candidates

The bundle may store owner-approved wording without making it runtime-generative.

```yaml
claim_id: claim.packet-pantry.backend.001
subject_id: project.packet-pantry
claim_type: accomplishment
text: "Built a Rust service with retry-safe ingestion and measured local throughput."
required_fact_ids:
  - fact.packet-pantry.language.001
  - fact.packet-pantry.retry-design.001
required_metric_ids:
  - metric.packet-pantry.throughput.001
metric_mentions:
  - metric_id: metric.packet-pantry.throughput.001
    rendering: qualitative_only
status: approved
allowed_surfaces:
  - resume
assertion_tags:
  - built
reviewed_at: "2026-08-10"
```

The initial closed `claim_type` catalog is `responsibility`, `accomplishment`, `project_summary`, and
`professional_summary`. `claims/bullet-candidates.yaml` owns the first three types;
`claims/summary-candidates.yaml` owns only `professional_summary`. A type in the wrong file is a hard
validation failure. Claim status is `draft`, `approved`, `rejected`, or `superseded`. An approved claim must reference
at least one fact, and every referenced fact or metric must be eligible for every allowed claim
surface. Every numeral, numeric range, percentage, duration, currency, and measured unit in claim
text must trace to one referenced metric's allowed rendering. A referenced metric omitted from the
text must be declared `qualitative_only`; that permission does not allow an unreferenced figure.
Forbidden metric phrasing is rejected. Canonical skills, public status terms, and any rendered
protected metric tokens receive deterministic cross-checks. Claim approval itself requires an
`approve_claim` sub-entry in the revision approval stamp tied to the candidate digest and claim
content digest.

`assertion_tags` is closed versioned data in `policy/assertion-tags.yaml`. The file has
`assertion_tags_version: 1` and an `assertion_tags` sequence. Each row contains exactly `tag_id`,
`high_risk`, `legal_subject_kinds`, and `authorization_any_of`. Each authorization branch contains
exactly:

```yaml
subject_statuses: []
required_fact_predicates: []
required_fact_value: null
require_same_subject_metric: false
```

Every branch must set at least one constraint. Within one branch all nonempty constraints are ANDed;
items inside either list are alternatives. `required_fact_value`, when non-null, is a canonical typed
fact value and requires exactly one `required_fact_predicates` item. An authorizing fact must be an
effective fact on the claim subject and must appear in the claim's referenced fact IDs. A
same-subject metric must be eligible and referenced by the claim. Every authorizing fact or metric
must itself be eligible for every claim surface. `authorization_any_of` is nonempty and succeeds when
at least one complete branch succeeds. The initial catalog rows encode exactly:

| Tag | High risk | Legal subject kinds | Authorization: at least one branch must match |
|---|---:|---|---|
| `shipped` | yes | `project` | subject status is `shipped_private`, `shipped_open_source`, `live_public`, or `sunset` |
| `live` | yes | `project` | subject status is `live_public` and a referenced effective `entity.url` fact exists |
| `production` | yes | `project` | a referenced effective fact has `deployment.environment == production` |
| `published` | yes | `publication` | subject status is `published` and a referenced effective `publication.date` fact exists |
| `granted` | yes | `patent` | subject status is `granted` and a referenced effective `patent.grant_date` fact exists |
| `awarded` | yes | `award` | subject status is `awarded` and a referenced effective `award.date` fact exists |
| `certified` | yes | `certification` | subject status is `active` and a referenced effective `certification.issue_date` fact exists |
| `designed` | no | `project`, `employment` | a referenced effective `project.contribution` or `employment.responsibility` fact exists |
| `built` | no | `project`, `employment` | a referenced effective `project.contribution` or `employment.accomplishment` fact exists |
| `implemented` | no | `project`, `employment` | a referenced effective `project.contribution` or `employment.accomplishment` fact exists |
| `led` | no | `employment`, `affiliation` | a referenced effective `employment.responsibility`, `employment.accomplishment`, or `affiliation.role` fact exists |
| `measured` | no | `person`, `education`, `employment`, `project`, `publication`, `award`, `certification`, `affiliation`, `course`, `presentation`, `patent` | at least one referenced eligible metric has the same subject as the claim |

Each initial tag has exactly one authorization branch. The table's listed statuses populate
`subject_statuses`; its listed predicates populate `required_fact_predicates`; all unmentioned
branch fields use the displayed empty/null/false values. The `production` branch alone sets
`required_fact_value: {type: string, value: production}`. The `measured` branch alone sets
`require_same_subject_metric: true`. The YAML rows encode those branches structurally; prose
authorization strings are forbidden. The
initial high-risk set is therefore exactly `shipped`, `live`, `production`, `published`, `granted`,
`awarded`, and `certified`. Aliases such as `ga_release` or `in_production` are rejected unless added
explicitly in a new catalog version. `production` has no implicit authorization from a project being
merely `completed`. Matching a branch makes a tag structurally eligible, but claim approval remains
mandatory and does not become an arbitrary natural-language entailment guarantee.

The validator does not pretend to prove arbitrary natural-language entailment. Owner approval plus
structured references establish that the wording is an allowed candidate. Runtime selection,
composition, rewording, and semantic judging are deferred.

## 16. Professional application-only facts

`application/gated-facts.yaml` stores professional facts that may be needed for eligibility or job
applications but must not leak into résumés or public artifacts. Examples in synthetic fixtures may
include work authorization, availability, or employment-type preference.

These records use the same fact and evidence model but must have `allowed_surfaces: [application]`
or no allowed surfaces. Validation rejects any application-only fact that also declares `resume` or
`public`.

Demographic, EEO, disability, veteran, health, compensation, financial, and unrelated personal
answers are outside this career bundle. If Boardwatch ever supports them, they require a separate
store and design.

## 17. History

Every promoted revision appends a change record:

```yaml
change_id: change.000002
revision: 2
parent_bundle_digest: "sha256:<previous-root-digest>"
actor: owner
authorized_by: owner
summary: "Add benchmark evidence and correct project start date"
changed_record_ids:
  - evidence.packet-pantry.benchmark.001
  - metric.packet-pantry.throughput.001
  - fact.packet-pantry.start-date.002
  - conflict.packet-pantry.launch-date
  - ruling.packet-pantry.launch-date.001
created_at: "2026-08-10T12:00:00Z"
```

The change and approval ledgers are append-only. Promotion requires the parent's canonical sequences
as identical prefixes plus exactly one new change and one matching approval stamp. The change-ledger length
must equal the proposed revision number. Its last entry must match the active manifest's revision,
`change_id`, and parent digest. The resulting bundle digest lives only in the manifest, avoiding a
self-reference inside the hashed change record. `actor` is one of `owner`, `agent`, or `importer`;
`authorized_by` is derived from the matching approval stamp rather than trusted from YAML. The
authoring CLI derives `changed_record_ids` from the validated draft diff rather than trusting a
manually authored list.

## 18. Import and initial migration

Gate B's denominator is the set of deterministic `source_record` units enumerated before any LLM
candidate extraction. An LLM may extract zero or more candidate assertions from one source record,
but it cannot create, omit, renumber, or assign IDs to the denominator. Candidate extraction receives
the immutable enumerated ledger package rather than raw authority to redefine source boundaries.

The initial closed source-kind and adapter pairing is:

| `source_kind` | `enumerator_id` | `enumerator_version` | Allowed scope |
|---|---|---:|---|
| `boardwatch_resume` | `boardwatch-resume-v1` | 1 | `complete_file` |
| `markdown_document` | `markdown-blocks-v1` | 1 | `complete_file` |
| `structured_objects` | `structured-objects-v1` | 1 | `complete_file` |
| `repository_markdown` | `markdown-blocks-v1` | 1 | `selected_sections` |

`approved_scope` is a discriminated object, never a scalar. It is either
`{kind: complete_file}` or `{kind: selected_sections, locators: [...]}`. Selected-section locators
are a nonempty unique list of normalized Markdown heading paths. Repository-source approval binds
the complete source policy record and the ledger's exact scope object; widening or changing that
scope therefore requires a new owner approval.

All normalized locators use NFC, preserve case, and trim surrounding whitespace. They are
POSIX-relative and reject empty segments, absolute paths, `.` segments, and `..` segments. Each
segment is percent-encoded from UTF-8 bytes with only ASCII alphanumerics plus `._-` left unescaped.
The source-record ID is the lowercase full SHA256 rendering
`source-record.<64hex>` of the canonical JSON UTF-8 bytes for
`["source-record", source_id, normalized_locator]`. The candidate ID is
`candidate.<64hex>` from canonical JSON UTF-8 bytes for
`["candidate", source_record_id, predicate, canonicalized_typed_value]`. Canonical JSON uses the
same Unicode normalization, key ordering, number representation, and insignificant-whitespace rules
as bundle canonicalization. Content digests are occurrence lineage, not identity, so changed bytes at
the same logical locator do not churn the denominator or every downstream candidate ID.

### 18.1 Source adapter contracts

`boardwatch-resume-v1` reads restricted YAML with exactly Boardwatch's current logical résumé shape:
top-level `header: [string]`, `education: [string]`, `skill_groups: [{label: string,
items: [string]}]`, `entries: [...]`, optional `extracurricular: [string]` defaulting to empty, and
optional `title: string | null` defaulting to null. An entry has exactly `entry_id: nonblank string`,
`heading: string`, `bullets: [...]`, optional `kind: string` defaulting to `experience`, and nullable
string `title`, `dates`, `subtitle`, and `location` fields defaulting to null. A bullet has exactly
`bullet_id: nonblank string`, `text: nonempty string`, and optional `tech_tags: [string]` defaulting
to empty. All authored strings are preserved as source data; the adapter does not run the tailor
loader's bullet-whitespace normalization.

The importer owns this duplicate source model; the frozen tailor package must not import
`profile_bundle`, and `profile_bundle` must not import or alter the tailor model or loader. It emits
records in this order:

1. each header line, locator `header/<1-based-index>`;
2. the non-null top-level title, locator `title`;
3. each education row, locator `education/<1-based-index>`;
4. each skill item in source group order, locator
   `skill-groups/<encoded-group-label>/<1-based-index>`;
5. each entry's complete metadata excluding bullets, locator `entries/<entry_id>/metadata`;
6. each complete bullet object, locator `entries/<entry_id>/bullets/<bullet_id>`;
7. each extracurricular row, locator `extracurricular/<1-based-index>`.

Entry and bullet IDs must be unique globally. Position-derived identity is allowed only for header,
education, skill items, and extracurricular because the source shape provides no stable row IDs
there. The adapter rejects blank header, title, education, skill-item, or extracurricular scalar
records, blank normalized skill-group labels, and duplicate normalized group labels, entry IDs, or
bullet IDs. Record content includes the complete normalized atomic value, including skill-group label,
entry optional fields, and bullet `tech_tags`, so no accepted field is outside occurrence lineage.

`markdown-blocks-v1` requires UTF-8. It retains raw bytes for `source_content_digest` but normalizes
CRLF and CR to LF for record content. It recognizes a heading only when a line matches
`^(#{1,6})[ \t]+(.+?)[ \t]*$`; the captured body is trimmed, NFC-normalized, and must be nonblank.
The leading hash count defines a case-preserving heading stack; skipped heading levels are allowed.
Duplicate normalized heading paths receive deterministic `~2`, `~3`, and subsequent suffixes. A
fence opener matches `^ {0,3}(?:\x60{3,}|~{3,})`; its closer uses the same character, has at least
the opening length, and may have only trailing whitespace. A list-item opener matches
`^ {0,3}(?:[-+*]|[0-9]+[.)])[ \t]+`. For each heading, the adapter emits the heading line itself
and then, in source order:

- each contiguous paragraph;
- each list item together with following nonblank lines indented farther than its leading
  indentation; and
- each fenced block from an opening backtick or tilde fence through its matching close.

Indentation columns count ASCII spaces as one and tabs to the next multiple of four. Blank lines end
paragraphs and list-item continuations and are not records. A heading, list-item
opener, or fence opener ends the preceding paragraph. An unterminated fence is a hard enumeration
error. Locators are
`<heading-path>/heading`, `<heading-path>/paragraph-<n>`,
`<heading-path>/list-item-<n>`, and `<heading-path>/fence-<n>`; content before the first heading uses
`_root`. A heading path percent-encodes each normalized heading body as one locator segment and joins
the active stack with `/`; the duplicate suffix is applied to the final encoded segment. For
`repository_markdown`, an exact selected heading includes its heading record and every descendant
block beneath it. Selected locators refer to these resolved paths, including any `~N` suffix.
Overlapping selected scopes deduplicate records while preserving source order; a selected heading
that does not exist is a hard error.

`structured-objects-v1` reads restricted JSON or YAML. For a root mapping, each top-level key must be
a nonblank string and maps to
one atomic value; rows sort by the NFC-normalized, encoded key and use locator
`objects/<encoded-key>`. For a root list, every element must be a mapping with a unique nonblank
string `id`; rows sort by encoded ID and use locator `objects/<encoded-id>`. Scalar roots,
position-derived list identity, and duplicate normalized keys or IDs are hard errors.

For every adapter, `source_content_digest` is SHA256 over the raw source bytes.
`record_content_digest` is SHA256 over the canonical JSON bytes of the adapter-normalized atomic
value only, excluding source and locator metadata. A résumé atomic value is the emitted scalar or
complete object described above. A Markdown atomic value is the exact emitted source substring after
line-ending normalization, including heading/list/fence markers. A structured mapping atomic value
is `{key: <NFC key>, value: <value>}`; a structured list atomic value is the complete element mapping.
Re-enumeration must reproduce byte-identical locators, order, IDs, and record digests.

`policy/sources.yaml` is authoritative for each source's `source_kind` and `portable_locator`.
`imports/source-ledger.yaml` references those entries by `source_id` and owns only enumeration,
approved-scope, source-digest, source-record, and disposition state. The two documents may not repeat
the same metadata fields.

`imports/source-ledger.yaml` has this closed shape:

```yaml
ledger_version: 1
sources:
  - source_id: source.synthetic-notes
    enumerator_id: markdown-blocks-v1
    enumerator_version: 1
    source_content_digest: "sha256:<64 lowercase hexadecimal characters>"
    approved_scope:
      kind: complete_file
    source_record_ids:
      - source-record.998d9c300586321739213be591f2be32bc52c04c46e1439c994b1f54c98793f1
records:
  - source_record_id: source-record.998d9c300586321739213be591f2be32bc52c04c46e1439c994b1f54c98793f1
    source_id: source.synthetic-notes
    normalized_locator: projects/example/summary/paragraph-1
    disposition: imported
    candidate_ids:
      - candidate.f4e2f2d54d1b5510cbd4253b70b4431a45ba88d48e879aa8ccf3b062acc875ee
```

Every enumerated record appears exactly once and has disposition `imported`, `excluded`, or
`review_required`. `record_count` is derived as `len(records)` rather than authored. Imported records
must name at least one deterministic candidate ID; excluded records must have a matching entry in
`imports/exclusions.yaml`; `review_required` is an undispositioned Gate B blocker.
For each source, `sources[].source_record_ids` must equal exactly, in the adapter's deterministic
canonical order, the IDs of all `records[]` entries carrying that `source_id`; neither side may contain
an extra, missing, reordered, or duplicate ID.

`imports/candidates.yaml` owns the typed candidate records and their append-only source occurrences:

```yaml
candidates_version: 1
candidates:
  - candidate_id: candidate.f4e2f2d54d1b5510cbd4253b70b4431a45ba88d48e879aa8ccf3b062acc875ee
    source_record_id: source-record.998d9c300586321739213be591f2be32bc52c04c46e1439c994b1f54c98793f1
    predicate: project.summary
    canonicalized_typed_value:
      type: string
      value: "Synthetic project summary"
    original_display_value: "Synthetic project summary"
    occurrences:
      - source_content_digest: "sha256:<64 lowercase hexadecimal characters>"
        record_content_digest: "sha256:<64 lowercase hexadecimal characters>"
```

The source digest identifies the enumerated source snapshot; the record digest identifies the
adapter-normalized atomic source-record bytes. The pair is unique within one candidate. Re-enumerating
changed source bytes at the same locator appends an occurrence rather than replacing prior lineage.

```yaml
exclusions_version: 1
exclusions:
  - source_record_id: source-record.eaf04cb408649b28ac6ad86736f7657f527009b58e5317699e3cab395966ca31
    reason: administrative_noise
    rationale: "Navigation text contains no professional assertion."
```

The closed exclusion reasons are `duplicate`, `administrative_noise`, `non_professional`,
`prohibited_sensitive`, `superseded_source`, `no_candidate_assertion`, and `owner_excluded`. Every
exclusion requires a rationale; `owner_excluded` additionally requires an
`approve_source_record_exclusion` sub-approval bound to the excluded source record's target-content
digest. The
Gate B denominator is `len(source-ledger.records)`, and its imported, excluded, and review-required
counts must sum exactly to that denominator with zero missing or duplicate record IDs.

Initial migration is staged and reviewable:

1. Register every owner-approved source in `policy/sources.yaml` with a matching
   `approve_source_scope` sub-approval, enumerate it in `imports/source-ledger.yaml`, and record every
   source record as imported or in `imports/exclusions.yaml` with a closed reason.
2. Extract only from that ledger into a typed candidate package.
3. Capture enough evidence for each candidate fact to make the package self-contained.
4. Normalize aliases and detect candidate duplicate entities.
5. Produce deterministic reports for conflicts, unsupported facts, missing evidence, stale claims,
   invalid status language, and unbacked skills.
6. Resolve required conflicts with the owner one question at a time.
7. Promote accepted candidate records into a draft canonical revision.
8. Validate the complete draft and freeze revision 1.
9. Preserve portable original-source IDs as import lineage only.

The generalized importer accepts a candidate package; it does not contain personal filesystem
paths or fetch a user's repositories. Candidate extraction may be performed by an LLM, but import
validation and promotion are deterministic.

The importer, not the LLM, assigns identity. Source adapters normalize locators to NFC POSIX-relative
syntax, trim surrounding whitespace, reject `.`/`..` traversal, and apply an adapter-versioned heading
or object-key rule; case is preserved unless that adapter explicitly declares case-insensitive
identity. Candidate values are typed first, then strings are NFC-normalized, Unicode whitespace is
collapsed, and ends are trimmed. Casefolding occurs only when the predicate contract declares
case-insensitive identity. Set-like lists are sorted by canonical element identity; ordered lists
retain order. The original display value and locator are preserved separately.

The candidate ID is derived from
`source_record_id | predicate | canonicalized_typed_value`. Re-extracting unchanged or
whitespace-equivalent input with
different ordering, grouping, proposed IDs, or whitespace-equivalent values therefore creates zero
new candidates. Paraphrases are deliberately outside this equivalence class and require review as
new candidates. Each candidate occurrence stores both source and atomic-record content digests. The
same source record, digest pair, and derived candidate ID is an exact duplicate; a changed source or
record digest with the same canonical value appends one review occurrence to the existing candidate;
a changed canonical value creates a new candidate ID. Import never overwrites canonical facts,
evidence, or rulings.

After baseline promotion, upstream sources are historical provenance. Normal future updates are
made directly in the bundle with new evidence. Boardwatch must not require another multi-source
discovery cycle to understand the profile.

## 19. LLM-friendly authoring workflow

The storage format is readable YAML. Boardwatch also ships:

- JSON Schema generated from the typed models.
- A concise general authoring contract.
- Synthetic complete-bundle examples.
- Deterministic JSON diagnostics.
- A concise human-readable validation report.

The proposed command surface is:

```text
boardwatch profile-bundle init
boardwatch profile-bundle checkout
boardwatch profile-bundle rebase-draft --draft <name>
boardwatch profile-bundle validate [--draft <name>] [--completeness] [--as-of YYYY-MM-DD] [--json]
boardwatch profile-bundle inspect <record-id>
boardwatch profile-bundle inventory [--json]
boardwatch profile-bundle conflicts [--json]
boardwatch profile-bundle add-evidence ...
boardwatch profile-bundle resolve-conflict ...
boardwatch profile-bundle approve --draft <name>
boardwatch profile-bundle promote --draft <name> --summary <text>
boardwatch profile-bundle migrate
```

`init` creates an empty revision-1 draft when no `CURRENT` exists; that draft has
`draft_of_revision: null` and `parent_bundle_digest: null`. `checkout` creates a writable draft from
`CURRENT`. A draft uses a discriminated manifest with `state: draft`, `draft_of_revision`,
`parent_bundle_digest`, and empty-string `bundle_digest`, `approved_candidate_digest`,
`approval_stamp_id`, and `change_id` sentinels; it has no promotion-derived `revision`, `created_at`,
or `created_by`.
`validate --draft` checks the full content,
evidence digest, parent, and candidate-content digest but skips only final bundle-digest equality and
promotion-approval requirements. It reports pending owner gates as blockers, not structural errors.

`approve` performs the controlling-TTY owner interaction in §13 and stamps the current candidate
digest. `promote` acquires the bundle lock non-blocking, then rechecks the parent, derives the next revision number, change ID, timestamp,
approval audit entry, and `state: revision` manifest, then revalidates the entire result, verifies its
digest from disk, and atomically replaces `CURRENT`.

If the parent moved, `promote` returns exit 1 with `stale_draft_parent` and leaves the draft intact.
`rebase-draft` is the drain: under the non-blocking exclusive lock it computes the record-level diff
from the draft's old parent, applies it to a new draft based on `CURRENT` only when the touched record
IDs are disjoint from intervening changes, renames the old draft to
`drafts/<name>.pre-rebase-<old-parent-token>/`, where the token is
`sha256-<64-hex-old-parent-digest>` or `root` for a parentless revision-1 draft, and atomically installs the rebased draft
at the original `drafts/<name>/` path. If that deterministic backup path already exists, it must be
byte-identical to the old draft or rebase returns typed `draft_backup_conflict` with no write. Rebase
does not delete or modify approval stamps; the new candidate digest makes every old stamp stale by
digest mismatch. An overlap returns `draft_rebase_conflict` with the exact record IDs and performs no
write; the owner or agent resolves those records explicitly in a new draft. `record_ids` is empty
**exactly** when the conflicting unit has no addressable records — a field-level or whole-document
conflict — and in that case `path`, together with `details.field` where the conflict has one, is the
locator. An empty list is therefore a statement about the unit's shape, never a missing value, and a
consumer must not read it as "no records were affected".

During Gates A and B, the existing `boardwatch tailor` commands continue to read `resume.yaml`
unchanged. Gate B neither deletes nor replaces it. Compiling the bundle into the frozen `Resume`
model is the later bridge in §4.2 and requires a separate design.

An LLM update follows this contract:

1. Read the active manifest and authoring guide.
2. Inspect the affected entity, facts, evidence, and conflicts.
3. Checkout or reuse an explicit draft.
4. Make the smallest relevant change.
5. Add evidence and provenance in the same draft.
6. Run complete validation.
7. Present changed record IDs, eligibility changes, diagnostics, owner-gated transitions, and the
   candidate digest.
8. Stop and ask the owner to run `profile-bundle approve` for that exact digest; the agent must not
   invoke or answer the approval prompt on the owner's behalf.
9. Promote only with the matching approval stamp.

Direct edits to a draft are supported. Direct edits to an immutable revision are detected by digest
verification and make that revision invalid rather than silently changing its identity.

## 20. Validation

Validation is layered and fail-closed. Structural, referential, evidence, semantic, and digest
validity are pure functions of bundle content; wall-clock time cannot turn the same bytes from valid
to invalid. Time-sensitive review and expiry are evaluated only by completeness against an explicit
`--as-of` date, defaulting to the local current date and always reported in machine output.

### 20.1 Structural validation

- Valid UTF-8 and YAML.
- Strict Pydantic models with `extra="forbid"`.
- Closed enums and discriminated value unions.
- The restricted YAML loader rejects duplicate keys, aliases, merges, ambiguous leading-zero
  integers, and out-of-contract implicit scalars.
- Stable-ID syntax and global uniqueness.
- Record-kind prefixes agree with model kinds.
- Unknown source files rejected.

### 20.2 Referential validation

- Every subject, fact, metric, skill, evidence, conflict, ruling, claim, and change reference
  resolves to the required record kind.
- Bidirectional evidence relationships agree.
- Supersession graphs are acyclic.
- Conflict candidates share the declared subject and predicate.
- The active ruling belongs to its conflict.
- Every declared skill surface has at least one eligible supporting fact that permits it; claim
  surfaces are subsets of the intersection of all required fact-and-metric surfaces; metrics carry
  matching `approve_metric_surfaces` entries; and relations expose none.

### 20.3 Evidence validation

- Every blob exists and matches its digest.
- Every verified fact meets its predicate's evidence contract.
- Every capture passes the exact secret-scan ruleset version recorded by its revision, plus the media
  allowlist and byte budgets; stronger installed rules are completeness-only for existing revisions.
- Evidence-class minimum fields are present, and accepted dependents have a digest-bound sufficiency
  approval.
- Contradictory evidence requires a conflict or ruling.
- Redaction metadata is complete.

### 20.4 Semantic validation

- Every predicate exists in the active versioned catalog; value type, subject kind, cardinality,
  evidence basis, context, and surfaces match its contract.
- Entity statuses come from the correct catalog.
- Fact states and supersession edges agree.
- Surface combinations obey privacy rules.
- Application-only facts cannot leak to résumé or public surfaces.
- Metrics have exact subjects, values, units, qualifiers, methods, contexts, evidence, protected
  tokens, allowed phrasing, and typed caveats whose severity rules are satisfied.
- Every assertion tag exists in the active catalog. The complete high-risk set—`shipped`, `live`,
  `production`, `published`, `granted`, `awarded`, and `certified`—satisfies its exact status and
  predicate requirements.
- Verified skills use a category from the active revision-owned catalog and have an eligible `technology.used` supporting fact whose
  predicate permits skill grounding and whose usage context is not `incidental`.
- Approved claims reference eligible facts; every figure is metric-traceable; qualitative metric
  references are explicit; forbidden phrasing is absent; and rendered protected tokens are preserved.
- Owner-gated states and operations have their specifically triggered sub-approval action and
  target-content digest inside the single approval stamp. The stamp's candidate digest and
  `manifest.approved_candidate_digest` both equal the candidate view recomputed from the promoted
  revision by §7's inverse normalization.

### 20.5 Completeness validation

Completeness is reported separately from structural validity. A bundle may validly preserve
uncertainty while being incomplete for downstream use.

The report distinguishes:

- errors: the revision is invalid;
- blockers: the revision is valid, but a named subject or fact cannot be used downstream;
- warnings: optional history or review work is missing;
- information: counts, surfaces, status distribution, and evidence coverage.

Required profile fields are generalized schema requirements, not personal values: one person
entity, at least one contact channel for a requested surface, explicit education/employment/project
status, and a declared review state for every imported fact.

Expired evidence or review dates are completeness blockers at the chosen `--as-of` date, never
structural errors. Completeness output includes the selected date, source-ledger totals, exclusion
totals by reason, unexplained source records, unreviewed evidence, unresolved conflicts, stale facts,
metric-review coverage, and surface coverage.

### 20.6 Digest validation

- The computed bundle and evidence digests match the manifest.
- The selected digest-named directory, `COMPLETE`, manifest, and `CURRENT` full digests agree; manifest
  revision, last change revision, and change-ledger length agree exactly.
- The change ledger's final entry matches the manifest revision, `change_id`, and parent digest.
- During promotion, the direct parent's source documents and manifest envelope are validated and its
  change, approval, and ruling sequences are exact canonical prefixes; exactly one change and one
  approval stamp are appended. The only exception skips a broken parent's evidence-blob integrity and
  completeness checks for the explicit recapture path in §6. Validation of an already selected
  revision does not deep-parse ancestors to repeat that promotion-time check.
- Ancestor links are traversed through stored manifest digests without deep revalidation; missing or
  unreadable ancestors produce `unverifiable_ancestor` completeness blockers.
- A draft follows the draft-manifest sentinel contract; a promoted revision follows the final
  manifest contract, and the final digest is verified from disk.
- The promoted revision's inverse-normalized candidate view recomputes the exact candidate digest
  carried by both its manifest and its appended approval stamp.
- Recomputing the same logical content produces the same digest regardless of YAML formatting or
  mapping-key order.

## 21. Failure behavior

| Condition | Result |
|---|---|
| Invalid YAML, unknown fields/enums, duplicate IDs, or broken references | Hard validation failure |
| Missing or mismatched evidence blob | Hard validation failure |
| Corrupted content-addressed blob | Logical quarantine without moving or deletion; restore the exact digest from verified backup, or recapture and promote a new revision |
| Secret hit, prohibited media, oversize capture, or absolute personal path | Hard validation failure |
| `verified` fact below its evidence standard | Hard validation failure |
| Conflicting single-valued facts outside a conflict group | Hard validation failure |
| Parent ledger/ruling prefix changed | Hard validation failure |
| Missing or stale owner-approval stamp | Promotion refusal |
| Unresolved, stale, rejected, or superseded fact | Retained and locally blocked |
| Evidence or review expired at `--as-of` | Completeness blocker; structural validity unchanged |
| Missing optional history | Completeness warning |
| Missing required professional-profile field | Incomplete-profile blocker |
| Changed import source | New occurrence for each stable record/value; a new candidate only when the canonical typed value changes; no canonical mutation |
| Interrupted promotion | `CURRENT` remains on the prior valid revision |
| Existing digest target differs or lacks a valid `COMPLETE` marker | Exit 3 with `promotion_target_conflict`; `CURRENT` unchanged |
| Bundle lock already held | Exit 3 with `bundle_lock_held`; no wait or mutation |
| Draft parent no longer current | Exit 1 with `stale_draft_parent`; draft retained for `rebase-draft` |
| Rebase touches an interveningly changed record | Exit 1 with `draft_rebase_conflict`; no write |
| Deterministic rebase-backup path exists with different content | Exit 1 with `draft_backup_conflict`; no write |
| Missing or unreadable ancestor | `unverifiable_ancestor` completeness blocker; selected revision remains structurally valid |
| Evidence or revision mutated after promotion | Digest failure; revision unusable |
| Bundle schema newer than the validator | Exit 3 with `unsupported_schema_version` |
| Recorded secret-scan ruleset unavailable | Exit 3 with `unsupported_secret_scan_ruleset_version` |

Validation performs no writes. Inventory and inspection perform no writes. No Gate A/B command
deletes revisions, blobs, evidence, conflicts, rulings, drafts, or unselected digest directories.

The single exception is a staging directory the running command created **itself**, under
`DRAFT_TEMP_PREFIX`, within the same operation, and has proved byte-identical to the material it
retains. That is the command's own scratch rather than the owner's work, and the prohibition exists to
protect the owner's work. Keeping it would be strictly worse in two ways: it strands a full-size tree
with no drain, which this project treats as a leak, and `DRAFT_TEMP_PREFIX` is exactly what `inventory`
reads as "an interrupted draft installation", so the residue would assert an interruption that never
happened. A command may never delete a draft it did not create, and never one it has not proved
redundant.

All `profile-bundle` validation-style commands use exit `0` for a completed check with no requested-
tier violations, `1` when the check completed and found errors, blockers, or a typed state refusal,
`2` only for command-line usage errors produced before command execution, and `3` when the check
could not complete because of I/O, lock contention, internal failure, or unsupported schema. JSON
output after successful argument parsing carries the same outcome category explicitly.
This is intentionally scoped to the new `profile-bundle` command family. Existing `scan` and `run`
commands currently use exit 2 for lock contention, and an eligibility worksheet command uses exit 2
for a missing directory; those historical behaviors are not treated as a Boardwatch-wide exit-code
contract and are unchanged by Gate A.

## 22. Testing strategy

All tracked tests and fixtures use synthetic identities, organizations, projects, evidence, and
metrics.

Required test groups are:

1. Typed model and JSON Schema parity, plus one comprehensive bundle containing every entity and
   record kind in its declared owning file and rejection of every unknown placement.
2. Restricted-loader cases for quoted boolean-like strings, timestamps, ambiguous leading zeroes,
   duplicate keys, merge keys, anchors/aliases, explicitly written standard and custom tags,
   integers versus decimal strings, and non-finite values.
3. Exhaustive round-trips for every closed enum and revision-owned catalog, including unknown-value,
   missing-contract-field, wrong catalog-version, and out-of-career-field category rejection.
4. Global ID uniqueness, referential integrity, wrong-kind references, nested approval-sub-entry
   indexing, and relation-catalog typing.
5. Both inline and blob captures: presence, discriminant exclusivity, declared-digest mismatch, byte
   tampering, exact post-redaction marker/range validation, secret and absolute-path scanning,
   recorded-ruleset structural stability, stronger-ruleset completeness blocking, unavailable-ruleset
   refusal, per-capture and aggregate byte limits, class contracts, and relationship direction.
6. One revision approval stamp containing zero, one, and many sub-approvals; evidence, metric-surface,
   source-scope, source-exclusion, claim, contact, fact, and ruling target-content binding; forged
   states, every missing triggered action, post-approval edits, non-TTY command refusal, and direct
   synthetic use of the pure `build_approval_stamp` constructor.
7. Corrupted-blob quarantine, restoration from an independently verified exact-digest backup, and
   recovery-draft promotion after recapture while only the broken parent's blob check is waived.
8. Conflict creation, resolution, reopening, mandatory ruling authorization, parent-prefix-preserved
   rulings, change and approval-stamp ledgers, revision-length equality, and localized blocking.
9. Fact-state transitions and acyclic supersession without mutating parent records.
10. Predicate subject/value/evidence-class/basis/owner-attestation-authority/context/surface-policy/
    cardinality/exclusivity/expiry/review enforcement for every initial predicate, including correction
    by supersession without a cardinality failure and `technology.used` having no inherited interval.
11. Metric subject, unit, qualifier, protected token, typed caveat severity, and
    allowed/forbidden-phrasing enforcement.
12. Assertion-tag catalog closure and exact high-risk status/predicate requirements, including
    rejection of `ga_release` and `in_production` aliases.
13. Per-surface skill support using the union of independently eligible supporting facts, claim
    intersection semantics, application-only non-widening, owner-approved metric surfaces, and
    relations exposing no surfaces.
14. Revision-owned skill-category closure and eligible non-incidental `technology.used` coverage.
15. Claim-to-fact validation, unreferenced-numeral rejection, qualitative metric omission, forbidden
    phrasing, and protected-token preservation.
16. Canonical bundle-digest stability across harmless YAML formatting and Unicode representation;
    changing only a stored sentinel value leaves recomputed identity unchanged.
17. A characterization pin for the existing eligibility/taxonomy/catalog/persona serializers using a
    fixed non-ASCII payload, proving bundle work does not shift `policy_version` inputs.
18. Evidence-digest set semantics: two records referencing one blob include that blob leaf exactly
    once while the changed evidence-record document still changes the overall digest.
19. Three intact revisions that can be deep-audited in a fixture, plus production validation that
    recomputes only the selected revision and traverses ancestor stored-digest links; missing old
    blobs or unsupported old schemas yield `unverifiable_ancestor` without invalidating the selected
    revision.
20. Draft manifest sentinel validation followed by promotion-time derivation, full-digest directory
    naming, from-disk final verification, and inverse recomputation of the approved candidate digest
    from the promoted revision.
21. Non-blocking promotion contention, `stale_draft_parent`, successful disjoint `rebase-draft`, exact
    deterministic backup naming, conflicting rebase or backup collision with no write, draft
    preservation, stamp retention, and approval invalidation by digest mismatch.
22. Deterministic source enumeration; exact agreement between per-source ID lists and ledger records;
    `policy/sources.yaml` metadata authority; denominator arithmetic; every exclusion reason;
    zero-candidate disposition; stable locator-derived source-record IDs; source/record occurrence
    lineage; locator/value normalization; paraphrase non-equivalence; and candidate import idempotence
    across content-digest, whitespace, LLM-ordering, and proposed-ID changes.
23. Bootstrap schema behavior: schema head 1, supported set `{1}`, typed newer-schema refusal, and
    `migrate` returning `already_current` with no write. Once schema v2 is designed, this test must add
    the exact v1 previous-schema fixture and append-only `1 -> 2` migration required by Section 7.
24. Time-pure validation: a fixture with a past expiry remains structurally valid and produces one
    completeness blocker at the chosen `--as-of` date.
25. Torn promotion at every boundary, exact-match reuse of an existing complete digest target,
    mismatch refusal, atomic `CURRENT` replacement, two concurrent promoters yielding exactly one
    winner, complete-but-unselected digest inventory, and lock-free readers seeing either one complete
    old revision or one complete new revision—never a mixed tree.
26. Process-death lock release proving that a persistent lockfile path is not treated as a held lock.
27. CLI exit-code characterization for clean, findings/refusal, usage error, and could-not-complete
    outcomes in both human and JSON modes.
28. Explicit Gate A refusal of undeclared `policy/persona.yaml`, `policy/selection.yaml`, and every
    other tailoring-policy file.
29. Existing-tailor characterization: `_resume_path` remains `settings.config_dir / "resume.yaml"`,
    the frozen `Resume` path imports no profile-bundle module, and Gate A/B add no alternate bridge.
30. Generalization inventory proving no personal data enters tracked files, fixtures, docs, or
    commits; contact URL fixtures use a deliberately non-LinkedIn reserved URL because R4 has no
    reserved-domain exemption.

The repository's authoritative `make check` remains the final implementation gate. Targeted tests
may be used during development, but completion requires its real exit code.

Synthetic contact fixtures use reserved `example.com` email values and a deliberately non-LinkedIn
URL such as `https://example.com/profile/example-candidate`; the generalization R4 profile matcher has
no reserved-domain exemption for LinkedIn or `mailto` URI shapes. Every tracked YAML or JSON fixture must be declared and digest-pinned in
the generalization `SHIPPED_DATA` inventory; shipped package data must also pass wheel-content checks.

## 23. Delivery decomposition and gates

This input-side program is deliberately separated from tailoring.

### Gate A — Generalized bundle mechanism

Gate A is met when a synthetic comprehensive bundle can be:

- parsed into strict typed models;
- validated structurally, referentially, evidentially, semantically, and for completeness;
- inspected through deterministic CLI and JSON output;
- checked out, edited as a draft, and promoted atomically;
- owner-approved through a candidate-digest-bound stamp rather than trusted YAML state;
- content-addressed with reproducible bundle and evidence digests;
- process-crash tested across promotion boundaries with one-writer semantics;
- conflict-resolved without deleting history;
- imported idempotently from a typed candidate package;
- verified by `make check` with the generalization scan clean.

No personal data is needed to meet Gate A.

### Gate B — Private canonical baseline

Gate B begins only after Gate A is implemented and reviewed. It operates entirely in the private
bundle and has an explicit measurement packet. It is met only when:

- the approved-source ledger reports its total source-record denominator, imported count, excluded
  count by closed reason, and **zero unexplained records**;
- `profile-bundle validate --completeness --as-of <recorded-date> --json` completes with zero structural
  errors and zero undispositioned blockers;
- every conflict detected by the deterministic conflict report is represented or carries an explicit
  owner disposition, with zero silent resolutions;
- every accepted fact references self-contained evidence with a digest-bound sufficiency approval;
- a reviewer who did not author the import audits a deterministic sample of
  `min(20, evidence_population)` records for source-independent sufficiency, with the sample seed,
  denominator, and result recorded;
- every metric is reviewed 1:1 for subject, context, method, caveats, allowed wording, and evidence,
  with numerator and denominator reported and equal;
- every entity has an honest status and allowed surfaces, every skill is evidence-backed or excluded,
  and every stale claim is rejected, superseded, or explicitly unresolved;
- a reviewer can answer the Gate B inventory checklist using the bundle alone, with every checklist
  item linked to bundle record IDs rather than an upstream source;
- revision 1 is frozen and the measurement packet records its bundle and evidence digests.

An explicit owner disposition may retain a blocker for later work, but Gate B cannot call the bundle
downstream-ready while such a blocker remains. The packet reports retained blockers separately and
Gate B is unmet until their downstream scope is either resolved or deliberately excluded.

Gate B may expose schema defects. Corrections to the generalized mechanism require synthetic
regression tests before the private baseline is promoted.

### Later gates — explicitly deferred

After Gate B, separate designs may cover:

1. Role-family projection and persona selection.
2. Summary and approved-claim selection.
3. Taxonomy integration and evidence-backed skill coverage.
4. Rendering and artifact provenance integration.
5. Representative-JD evaluation and tailoring-quality acceptance.

None of those later gates may weaken the canonical bundle's truth, evidence, visibility, conflict,
metric, or status rules.

## 24. Acceptance criteria for this design

The implementation created from this design is acceptable only when:

- There is one private, organized, revisioned career-profile bundle.
- The active revision and all required evidence are self-contained under one root.
- Every accepted fact is atomic, typed, traceable, and surface-scoped.
- Every metric has an exact subject and evidence-backed context.
- Unresolved conflicts block only dependent material.
- Prototype, active-development, shipped, live, and published states cannot be conflated.
- Unsupported skills cannot be marked verified.
- Approved wording references canonical facts and preserves protected tokens.
- Application-only professional facts cannot appear on résumé or public surfaces.
- Future updates can be made once through readable YAML and deterministic validation.
- An LLM can understand the authoring contract without rediscovering upstream repositories.
- Personal values remain absent from the generalized repository.
- Tailoring remains outside the implementation scope.
