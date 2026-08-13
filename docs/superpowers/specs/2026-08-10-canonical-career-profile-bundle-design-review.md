# Adversarial design review — Canonical Career-Profile Bundle

**Reviewed file:** `docs/superpowers/specs/2026-08-10-canonical-career-profile-bundle-design.md` (866 lines)
**Date:** 2026-08-10
**Mode:** Independent, adversarial. Review only — no edits to the spec, no implementation, no plan.
**Authority used:** live code and tests over prose, per CLAUDE.md.

---

NEEDS-REVISION

## Findings

### BLOCKING

**B1. Skill records bypass surface isolation — an application-only fact can reach `public`**
§14 (L521–536), §16 (L586–588), §20.4 (L717–728)

`skill` records carry their own `allowed_surfaces` (L534–536) and reference `supporting_fact_ids` (L527–528). The only skill rule in the validator list is "Verified skills have eligible supporting facts" (L727). Claims get a subset rule — "every referenced fact or metric must be eligible for every allowed claim surface" (§15 L572–573) — skills get nothing equivalent. §16's guard (L586–588) is scoped to facts stored in `application/gated-facts.yaml`, not to derived records that point at them.

Concretely: `skill.some-clearance-tool` with `allowed_surfaces: [resume, public]` whose only supporting fact is an `allowed_surfaces: [application]` gated fact validates clean. Acceptance criterion L862 ("Application-only professional facts cannot appear on résumé or public surfaces") is therefore not enforceable as written, and locked decision 8 depends on it.

*Correction:* add a general derived-record surface rule to §20.4 — for every record with `allowed_surfaces` that also carries required/supporting references (skill, metric-with-entity-subject, claim), `allowed_surfaces ⊆ ⋂(allowed_surfaces of every referenced record)`. State it once as an invariant over the reference graph rather than per record type, and add the skill case to §22 test group 9.

**B2. "Predicate contracts" are the load-bearing layer and are never enumerated or located**
§10.1 (L315–316), §10.2 (L334–336), §12.1 (L451–462), §13 (L473–480)

The design defers to "predicate contracts" for: which value types are legal (L315–316), which evidence bases satisfy `verified` (L335–336), whether `owner_confirmed` is sufficient (L330–331), whether `secondary_summary` counts (L460–461), and — critically — which predicates are single-valued, which is what §13's first conflict trigger (L475) is defined in terms of. The predicate catalog itself appears nowhere. `technology_used`, `start_date`, `retry-design` appear only as example strings.

Without it, §13 conflict detection, §20.3 evidence validation, and §20.4 semantic validation are all unimplementable, and Gate A's "validated ... semantically" bullet (L808) has no referent.

Worse, L315–316 places the contracts "in code". CLAUDE.md's multi-tenancy section is explicit that field-dependent taxonomies must "ship the taxonomy as versioned **data**, not code", and names the eligibility taxonomy as the exact thing that failed to port when a second user appeared. A predicate catalog is field-dependent by construction (`technology_used` is a software predicate).

*Correction:* add a §10.4 defining the predicate contract record — `predicate_id`, tier (`universal` / `profile-dependent` / `field-dependent`), legal `entity_type`s for the subject, legal value types, cardinality (`single` / `multi`), minimum evidence contract as a set of `verification_basis` values, and legal surfaces — ship it as a versioned YAML catalog inside the revision tree (`policy/predicates.yaml`) with its version folded into `bundle_digest`, and enumerate the initial closed catalog. Out-of-catalog predicate ⇒ validation error, per CLAUDE.md's closed-catalog rule.

**B3. An LLM can manufacture owner authority; nothing mechanically distinguishes agent-authored from owner-authored records**
§10 (L280–281), §12 (L414, L457–458), §15 (L562), §17 (L616), §19 (L676–683), §3 (L48)

Every marker of owner authority is a plain authored string in YAML that the same agent writing the draft also writes: `verification_state: owner_confirmed` (L280), `evidence_class: owner_attestation` (L414), claim `status: approved` (L562), metric `owner_protected: true` (L394), and `authorized_by: owner` (L616). §19's authoring contract (L676–683) is a procedure an agent is asked to follow, not a mechanism.

The loop closes completely: an agent can author an `owner_attestation` evidence record containing inline text it wrote, cite it from a fact as `owner_confirmed`, and cite that fact from an `approved` claim. Every §20 check passes. §3's non-goal L48 ("Treat an LLM judgment as evidence") is violated by a design that provides no way to stop it, and locked decision 4's "approved claim candidates" become agent-approved candidates.

*Correction:* make authority a CLI-stamped property, not an authored one. (a) `actor` is set by the CLI from its invocation mode and is rejected if present in an authored file. (b) Define a closed set of *owner-gated transitions* — `verification_state: owner_confirmed`, `evidence_class: owner_attestation`, `claim.status: approved`, `owner_protected: true`, `ruling.decision`, `authorized_by` — that a draft may only *propose* (e.g. `status: draft` + `proposed_transition:`), and that only an interactive `boardwatch career approve <record-id>` promotes, stamping `approved_by: owner` plus the draft digest at approval time. (c) Promotion fails closed if any owner-gated field changed relative to the parent revision without a matching approval stamp. Add a §22 test group: an agent-authored draft that self-declares every owner-gated field is rejected at promote.

**B4. "Append-only" change ledger has no executable check**
§17 (L614–618), §20.6 (L746–752)

`history/changes.yaml` lives inside the logical revision tree (L130–131), and each revision is a full copy of that tree. Nothing carries the ledger forward except the promoting writer. The only stated check is that "the change ledger's final entry must match the active manifest's revision, `change_id`, and parent digest" (L748–749) — the *last* entry. A promotion that rewrites, reorders, or drops every prior entry and appends a correct final one validates clean.

"Append-only" (L614) is asserted, not enforced. Same for §13's "An owner ruling is append-only" (L496) — rulings also live in a per-revision file copy with no carry-forward check.

*Correction:* add to §20.6: the draft's `history/changes.yaml` must equal the parent revision's ledger with exactly one entry appended, byte-for-byte after canonicalization, and its length must equal `manifest.revision`. Add the identical prefix-preservation check for `conflicts/rulings.yaml` (prior rulings may not be modified or removed; only appended to) and for superseded facts. Add §22 tests: "parent ledger prefix mutated ⇒ promotion rejected" and "prior ruling edited ⇒ promotion rejected."

**B5. The metric protected-token rule contradicts the design's own example, and the real fabrication hole is unchecked**
§11 (L384–391), §15 (L554–574), §20.4 (L728)

§20.4 L728 says approved claims must "preserve protected tokens." The metric at L389–391 declares `protected_tokens: ["120", "requests/s"]`. The claim at L554 — `"Built a Rust service with retry-safe ingestion and measured local throughput."` — references that metric via `required_metric_ids` (L558–559) and contains neither token. Under the stated rule the design's own worked example fails validation.

More importantly, the rule as stated is the wrong direction. Requiring a claim to *contain* protected tokens forces numbers into prose; what actually needs blocking is the inverse — a numeral or unit in claim text that does **not** trace to a referenced metric. That is the fabrication case, and nothing in §15 or §20.4 catches it. A claim reading `"sustained thousands of requests per second"` with `required_metric_ids: []` passes every listed check.

*Correction:* replace "preserve protected tokens" with three directional rules: (i) every numeric token and unit token in `claim.text` must appear in the `allowed_phrasings` of some metric in `required_metric_ids` — otherwise error; (ii) no `forbidden_phrasings` string of any referenced metric may appear in `claim.text`; (iii) if a claim references a metric, its text must match at least one of that metric's `allowed_phrasings` **or** declare `metric_referenced_without_figure: true`. Then fix the L554 example to be consistent with whichever rule you keep. Add §22 test: "claim containing an unreferenced numeral is rejected."

---

### MAJOR

**M1. Atomic promotion and crash recovery are asserted without a mechanism**
§6 (L150–152), §19 (L669–671), §21 (L766)

L151 says promotion "atomically replaces the small `CURRENT` pointer"; L766 guarantees "Interrupted promotion ⇒ `CURRENT` remains on the prior valid revision." Neither is traceable to anything. Unspecified: the replacement primitive (`os.replace` on a temp file vs. write-in-place), fsync ordering (the revision directory and every blob must be durable *before* the `CURRENT` flip, or a crash yields a `CURRENT` pointing at a torn tree), the lock file's path and primitive (§6 L152 "read lock", §19 L669 "exclusive bundle lock" — neither defined), stale-lock recovery, and how a torn revision directory left by a crashed promotion is distinguished from a valid one on the *next* promote (which will compute the same revision number and may find the directory already present). This repo has already paid for exactly this class of gap — STATE.md L116 carries "cross-OS two-writer WAL test" as an open P3 item.

*Correction:* specify: promotion writes to `revisions/.tmp-<uuid>/`, fsyncs every file and the directory, `os.replace`s it to `revisions/NNNNNN-<prefix>/`, fsyncs the parent, writes a `COMPLETE` marker containing `bundle_digest`, fsyncs, then writes `CURRENT.tmp` + fsync + `os.replace` + parent fsync. A revision directory without a matching `COMPLETE` marker is torn: never selectable, reported by `inventory`, removable only by an explicit command. Lock = a single `flock`-style exclusive lock on `<root>/.lock` held for the whole promote; readers take it shared; no lock timeout stealing. State the POSIX-only assumption explicitly.

**M2. Validation is time-dependent while revisions are immutable — a frozen valid revision becomes invalid at midnight**
§10 (L290 `expires_at`), §10.2 (L325 `stale`), §22 (L790–791)

`expires_at` is authored per fact but §20 and §21 never say what evaluates it. If expiry is a validation error, revision 1 can validate clean on promotion day and hard-fail later with identical bytes and an identical digest — while §22 test 12 (L790) asserts digest stability and nothing asserts *validation* stability. If expiry is instead ignored, the field is decoration.

*Correction:* state that structural, referential, evidential, and digest validation are pure functions of bundle content and must be time-independent — `make check` should assert this by validating a fixture at two mocked clocks. Move expiry entirely into §20.5 completeness, evaluated against an explicit `--as-of` date defaulting to today, and reported as a *blocker*, never an error. Add §22 test: "a fixture with a past `expires_at` still validates; it reports one blocker."

**M3. Canonical-digest determinism is underspecified in four ways, one of which is a self-reference**
§7 (L186–198), §6 (L139–142)

- **Self-reference:** revision directories are named `000001-<digest-prefix>` (L139–140). Step 1 enumerates "every source file in the logical revision tree" and step 6 hashes "relative-path and leaf-digest pairs" (L194) — relative to *what*? If relative to the bundle root, the path contains the digest prefix and the digest is defined in terms of itself.
- **Blob paths:** step 5 includes "each referenced evidence blob's relative path and raw-byte SHA-256" (L193), but blobs live at `blobs/sha256/<full-digest>` (L146–147), i.e. *outside* the revision tree, and the path is literally the digest — so the pair is redundant and the base is again unstated.
- **YAML scalar typing:** step 2 says "parse YAML and serialize as sorted-key compact JSON" (L189–190). Unstated: which loader/schema (YAML 1.1 turns `NO` into `False` and `12:30` into 750), how dates/datetimes serialize (`yaml.safe_load` yields `datetime.date`, which `json.dumps` refuses), NaN/Infinity handling, `ensure_ascii`, and Unicode normalization form.
- **Ordering:** `evidence_set_digest` must be computed and written into the manifest *before* `bundle_digest`, since it is a manifest field and only `bundle_digest` is excluded (L191). Implied, never stated.

*Correction:* pin all four. Declare relative paths as revision-root-relative for revision files and `blobs/`-relative for blobs (drop the redundant per-blob path). Mandate a restricted loader (YAML 1.2 core schema, or `SafeLoader` with implicit timestamp/bool resolvers removed so all scalars stay strings), `json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)` over NFC-normalized text, and state the two-phase manifest write order. Reuse the existing in-tree implementation rather than writing a third copy: `src/boardwatch/extract/taxonomy.py:95-103` `_version_of` is the canonical-JSON reference, duplicated verbatim at `src/boardwatch/tailor/persona.py:150-155`. CLAUDE.md's reuse-first default applies — extract it to a shared helper.

**M4. `origin.uri` mandates absolute personal filesystem paths inside the bundle, contradicting §18 and §5**
§12 (L422–425), §18 (L634–635), §5 (L101–102)

The evidence example carries `uri: "/external/original/path/docs/baseline.md"` — an absolute path. In a real bundle that is `/Users/<name>/...`. Meanwhile §18 L634–635 promises the importer "does not contain personal filesystem paths," and §5 L101–102 says identity derives "from validated content, not from the absolute path." Those cannot all hold. §12.2's prohibited-capture list (L466–468) covers credentials and demographics but not filesystem paths or usernames.

This also makes the "relocated for encrypted backup" story (L101) lossy — every `origin.uri` dangles after a move, and any fixture that mirrors the real shape trips generalization rule R1 (`HOME_PATH_RE`, `tools/generalization/shape.py:29`).

*Correction:* make `origin` an opaque, scheme-qualified locator resolved through a small `policy/sources.yaml` registry of source IDs: `origin: {source_id: src.project-notes, path: docs/baseline.md, repository_commit: <sha>}`. Keep the absolute path, if wanted at all, in a single non-digested, non-exported local sidecar. Add a validator rule mirroring R1 that rejects any absolute home path anywhere in the bundle.

**M5. "Self-contained evidence" collapses to "non-empty" at the only place it is enforced**
§12 (L443), §20.3 (L713), §24 (L855)

§12 L443 states the substantive requirement: "The captured material must be sufficient to evaluate the linked fact without opening `origin.uri`." §20.3 L713 reduces it to "inline content is non-empty or a blob is present." A one-byte blob satisfies the machine check while the acceptance criterion at L855 and locked decision 3 rest on the human one. This is the design's largest gap between a guarantee word and an enforceable mechanism.

*Correction:* accept that sufficiency is undecidable and make the *attestation* mechanical. Add to the evidence record: `sufficiency_reviewed_by` (owner-gated per B3), `sufficiency_reviewed_at`, and a per-`evidence_class` minimum contract (`measured_result` requires a `measurement_context` echo and a non-trivial capture; `repository_artifact` requires `repository_commit` plus a code/manifest excerpt). Make an unreviewed evidence record a §20.5 *blocker* for every fact it supports. Then make Gate B's corresponding bullet a sampled audit with a number (see M8).

**M6. Redaction and prohibited-capture are aspirational; nothing scans the bundle, and no size budget enforces locked decision 3**
§12.2 (L464–469), §3 (L47)

"Snapshots must not copy credentials, API keys, private keys, authentication cookies…" (L466–467) has no mechanism. The repo's secret scanning is gitleaks in pre-commit and CI (`.pre-commit-config.yaml`, `.github/workflows/ci.yml`) — both scan the *repository*, and the bundle lives outside it by locked decision 7, so nothing ever looks at a captured blob. Separately, `redactions: []` (L435) has no field schema — no offsets, no reason vocabulary, and no way to verify a redaction removed anything, since the blob is hashed post-redaction. And §3 L47 / locked decision 3 forbid copying "entire source repositories or large binary archives" with no size or media-type limit anywhere.

*Correction:* run a secret-detection ruleset over every capture at `add-evidence` time **and** at `validate`, fail-closed on a hit, and record `secret_scan_ruleset_version` in the manifest so a ruleset upgrade re-checks. Define the `redactions` entry schema (`{start, end, reason}` over the canonical capture, closed reason catalog). Add a per-blob max size, a media-type allowlist, and a total-bundle byte budget, all as hard validation failures in §21.

**M7. `person` has no contact-channel schema, yet §20.5 mandates checking one**
§20.5 (L742–745), §9 (L245–253)

L743–744 requires "at least one contact channel for a requested surface." The entity model (L245–253) gives every entity only `entity_id`, `entity_type`, `display_name`, aliases, status, dates, and facts. There is no contact-channel type, no surface scoping for one, and nothing in §10's value union (L300–312) that models "email" or "profile URL" as distinct from `string`/`URL`. The check cannot be written.

*Correction:* define the contact channel explicitly — either as a closed predicate family on the `person` entity (`contact.email`, `contact.phone`, `contact.profile_url`, `contact.location`) with per-channel `allowed_surfaces`, or as a typed sub-record. Note this is exactly the surface most exposed to generalization R2/R4 (see m5).

**M8. Gate B is not independently executable or objectively measurable**
§23 (L819–832)

Every Gate B clause is an unfalsifiable universal over an undefined denominator: "every known conflict is represented" (L826) — *known* by whom; "every accepted fact has sufficient self-contained evidence" (L827) — the very thing M5 shows is not checkable; "the complete professional inventory is understandable without reopening upstream sources" (L831). None has a number, a sample size, a procedure, or a reviewer. This program's other gates do: Gate P5 is "16/16 INELIGIBLE precision," Gate P6 clause 4 is "20 sampled suppressions, sampled deterministically so it can be re-run" (STATE.md L89). CLAUDE.md: "A gate is met when its metric says so, not when the work feels done."

*Correction:* give Gate B a denominator and a procedure. (a) An exclusion ledger listing every source record not imported with a reason; gate = zero unexplained records, count reported. (b) `career validate --completeness --json` exits 0 with zero errors and every reported blocker carrying an explicit owner disposition; counts recorded in METRICS.md. (c) A deterministically-sampled audit of N evidence records (N stated) scored for sufficiency by a reviewer who did not author the import — the P6 D-101 pattern. (d) Every metric record reviewed 1:1, count reported, since the population is small.

**M9. Import idempotency is incompatible with LLM candidate extraction**
§18 (L636–639)

L638–639: "Re-import is idempotent by source locator, captured digest, and candidate record ID." L636 permits an LLM to perform candidate extraction. An LLM re-run over an unchanged source produces different splits, different groupings, and different candidate IDs, so re-import will manufacture spurious "new" candidates for identical input. Idempotency keyed on an ID the nondeterministic step invents is not idempotency.

*Correction:* the LLM proposes; the importer keys. Derive `candidate_id` deterministically as `sha256(source_id | locator | predicate | canonicalized_value)`, so re-extraction of the same content collapses to the same candidate regardless of phrasing or ordering. Add §22 test: "the same source re-extracted with a perturbed candidate ordering and renamed candidate IDs produces zero new candidates."

**M10. §4.1 never evaluates Git as the revision substrate, which is where most of the unproven complexity lives**
§4.1 (L52–63), §7 (L183–184)

The architectural decision compares the bundle against one large file and against SQLite. It never compares it against *a private Git repository of YAML*, which supplies for free every mechanism the design then hand-rolls and asserts: immutable content-addressed revisions, explicit parent digests, atomic ref update, tamper detection, history, and locking. L183–184 acknowledges Git exists ("even when the bundle is not stored in Git") without arguing against it. CLAUDE.md's engineering default is "platform/native feature → … → new code (last resort)", and the design's five weakest guarantees (M1, B4, garbage accumulation, revision duplication, M3's path/self-reference issue) are all substrate concerns Git already solves.

*Correction:* add the comparison to §4.1 explicitly and state the deciding reason — plausibly "the owner must be able to relocate and encrypt the bundle without a `.git` directory," or "a stray `git checkout` in the bundle would violate immutability." If Git wins, `revisions/`, `CURRENT`, `drafts/`, `blobs/`, the lock, atomic promotion, crash recovery, and GC all collapse to `git commit` + `git tag` + `git fsck`. Either outcome is defensible; not evaluating it is not.

**M11. No bundle-schema migration policy, and immutable revisions make it structurally hard**
§7 (L171), §20.6 (L746–752)

`schema_version: 1` exists with no evolution story. Because revisions are immutable, revision 1 stays schema 1 forever while the code moves to schema 2 — but §20.6 L750 requires "the parent digest exists in the preceding local revision," which means old revisions must remain *readable*. There is no stated policy for reading an older schema, no compatibility window, and no equivalent of this repo's Alembic discipline (`tests/unit/test_schema_head.py` pins the head; D-099 requires an explicit bump).

*Correction:* state the policy. Recommended: readers must parse any `schema_version` within a declared support window; parent-chain validation verifies only the *digest*, never re-parses the parent's models; a schema bump requires a `career migrate` producing a new revision whose change record declares `schema_migration: 1 -> 2`; and a pinned-head test mirrors `test_schema_head.py`. Add a §22 fixture bundle at the previous schema version that must still resolve its digest.

**M12. Cross-references are untyped, so a wrong-kind reference "resolves"**
§8 (L209–213), §20.1 (L696), §20.2 (L701–702)

IDs are globally unique in one namespace (L696) and the grammar (L211–213) treats the `project.` / `fact.` / `metric.` prefixes as pure convention — nothing binds a prefix to a record kind. §20.2's referential check is "every … reference resolves" (L701–702), not "resolves to the right kind." `evidence_ids: [metric.packet-pantry.throughput.001]` resolves.

*Correction:* bind the prefix to the record type in the grammar (`^(person|education|employment|project|publication|award|certification|affiliation|fact|metric|evidence|conflict|ruling|skill|claim|change)\.…`), and type every reference field to its target kind in the Pydantic models so mis-kinded references fail at parse, not at a graph walk. Add a §22 case per reference field.

**M13. `role_families` is a third, unclosed vocabulary**
§14 (L533), §15 (L560)

Skills and claims both carry `role_families`, with `backend` / `systems` as examples. The live tree already closes this vocabulary: `src/boardwatch/tailor/persona.py:34` — `VALID_ROLE_FAMILIES = frozenset(name for name, _ in ROLE_FAMILIES) | {"general_swe"}` — derived from `boardwatch/extract/role_family.py:11` with the comment "so the two can never drift", and `persona.py:107-110` rejects any persona declaring a family outside it. A bundle introducing a free-form third list is precisely the drift that guard exists to prevent. It is also field-dependent content in a multi-tenant system (CLAUDE.md), so hardcoding SWE families is doubly wrong.

*Correction:* either close bundle `role_families` against a versioned catalog shipped in the revision (`policy/role-families.yaml`, field-tiered) whose relationship to `ROLE_FAMILIES` is stated, or drop the field from this phase entirely — it is selection policy, and §4.2 L79–81 says this phase must not encode tailoring decisions into the knowledge schema.

**M14. A `Settings` field for the bundle path will break `config_hash` and shift `policy_version`**
§5 (L85–89), §19

The design says the path is "user-configurable" without saying how. If implemented as a `Settings` field, `reports/manifest.py:90-108` `_assert_exhaustive()` raises `UnclassifiedSettingError` until the field is added to `_CONFIG_RELEVANT` or `_CONFIG_IRRELEVANT`; classifying it relevant changes `config_hash`, hence `policy_version` (`manifest.py:157-190`), hence every subsequent run's artifact lineage.

*Correction:* follow the established precedent instead — personas, taxonomy, and `resume.yaml` are all derived as `{config_dir}/<name>` at the call site with a CLI override and no `Settings` field (`cli/tailor_cmd.py:55-56`, `tailor/persona.py:71-78`). Specify `settings.config_dir / "career-profile"` plus `--bundle`. If a `Settings` field is used anyway, state that it is classified `_CONFIG_IRRELEVANT` and why (nothing in the pipeline reads the bundle this phase).

---

### MINOR

**m1. `character_count` is layout policy leaking into the knowledge schema**
§15 (L567). `character_count: 77` is (a) derivable from `text`, so it can disagree with it, and (b) meaningful only against the résumé layout gate — `BULLET_MAX_LENGTH = 220` in `reports/resume_gate.py:99`. §4.2 L79–81 explicitly forbids encoding renderer decisions here. Drop the field; compute it downstream.

**m2. `career snapshot` is listed and never defined; there is no `career init`**
§19 (L657–667). `snapshot` (L666) appears in the command surface with no description in §19, §20, §21, or §23. Separately, `checkout` derives a draft from `CURRENT` (L669), so nothing creates revision 1 for a user who is not importing. Define both or remove `snapshot`.

**m3. Unbounded growth with no collection path**
§7 (L200–202), §21 (L769–770). Every revision is a full copy of the YAML tree (blobs are shared, documents are not), no command deletes revisions (L770), and unreferenced blobs are only reported (L201–202). After superseding evidence, blobs pile up permanently. State a retention policy and add an explicit, owner-confirmed `career gc --keep-last N --keep-referenced-blobs` that refuses to break the parent-digest chain.

**m4. `experience/` and `projects/` have no file-naming rule, but unknown files are an error**
§6 (L113–115), §7 (L200), §20.1 (L697). "Unknown source files rejected" needs a definition of *known* for two directories whose contents are unconstrained. Specify `experience/<entity-id>.yaml` (basename must equal the contained `entity_id`) and reject anything else.

**m5. A synthetic bundle demonstrating a contact channel will fail the generalization gate**
§22 (L794–795), §20.5 (L743–744). Generalization R4 (`tools/generalization/shape.py:63-65`) matches `linkedin\.com/in/<handle>` with `PROFILE_URL_EXCEPTIONS = {}` (`allowlists.py:26`), and the allowlist discipline punishes both a blank reason and a never-matched entry. So a synthetic fixture exercising the M7 contact-channel check cannot use a LinkedIn URL without adding the repo's first allowlist entry. Emails are fine (`@example.com` is exempt, R2). Also: every tracked `.yaml`/`.json` fixture the design ships needs a `SHIPPED_DATA` entry with a `sha256:` pin (R7, `tools/generalization/inventory.py:91-213`), re-pinned on every fixture edit, and anything shipped under `src/boardwatch/` must reach the wheel (R12). Say so in §22 so it is not discovered during implementation.

**m6. No exit-code contract for the CLI**
§19, §21. `boardwatch career validate` needs a stated 3-way contract in the style the generalization tool already uses (`tools/generalization/__main__.py:1-4`: 0 clean, 1 violations, 2 could-not-complete). Without it, "0 or non-zero" conflates "invalid bundle" with "checker crashed" — which this repo's own gate design explicitly rejects.

**m7. "closed extensible registry" is self-contradictory**
§11 (L399). Units are "a closed extensible registry." State the mechanism: closed at validation time, extended only by a versioned edit to a registry file inside the revision, with the registry version folded into `bundle_digest`.

**m8. `skill` is ID-bearing but is not in the entity catalog**
§8 (L206–207) lists skills among things with stable IDs; §9's closed entity catalog (L234–241) omits them, and skills live in their own file with aliases and status — i.e. they *are* entities. Either add `skill` to the catalog or state explicitly why it is a separate record class.

**m9. Missing relations and entity types**
§9 (L234–241). No way to express "this project was done at this employer" (no relational predicate, and `subject_id` is single-valued), no `course` entity despite §14 L540 admitting "substantial coursework" as supporting evidence, and no `talk`/`presentation` or `patent`. Add a `related_entity_ids` edge with a closed relation catalog, and either add `course` or state that coursework attaches to the `education` entity.

---

## Missing acceptance tests

1. **Surface subset over the reference graph** (B1) — a skill/metric/claim declaring a surface not held by every referenced record is rejected; specifically an application-only fact supporting a `public` skill.
2. **Owner-gated transition forgery** (B3) — an agent-authored draft that sets `owner_confirmed`, `owner_attestation`, `claim.status: approved`, `owner_protected`, and `authorized_by: owner` is rejected at promote.
3. **Ledger and ruling prefix preservation** (B4) — a draft whose `changes.yaml` prefix or whose prior rulings differ from the parent revision is rejected; ledger length equals `manifest.revision`.
4. **Unreferenced numeral in claim text** (B5) — a claim containing a figure not traceable to a `required_metric_ids` entry is rejected; a claim containing a `forbidden_phrasing` is rejected.
5. **Torn-promotion recovery** (M1) — kill between revision write and `CURRENT` flip: `CURRENT` unchanged, the incomplete directory is not selectable and is reported by `inventory`; and a subsequent successful promote over the debris.
6. **Concurrent promote** (M1) — two promoters, one lock: exactly one revision is created, the loser fails cleanly, no partial tree survives.
7. **Time-independence of validation** (M2) — the same fixture validates identically at two mocked clocks; a past `expires_at` yields a blocker, never an error.
8. **Digest hostile-input determinism** (M3) — YAML 1.1 traps (`NO`, `12:30`, `1.0`), a date scalar, non-NFC Unicode, and CRLF line endings all round-trip to a stable digest; a semantic value change does not.
9. **Digest independence from placement** (M3) — a bundle copied to a different absolute path and a revision directory renamed to a different `<digest-prefix>` yield the same `bundle_digest`.
10. **Absolute-home-path rejection** (M4) — an evidence record carrying an absolute home-directory path (either the macOS or the Linux form) in any field is rejected.
11. **Secret capture rejection** (M6) — a blob containing an API-key-shaped token is rejected at `add-evidence` and at `validate`; an oversize blob and a disallowed media type are rejected.
12. **LLM-extraction idempotency** (M9) — the same source re-extracted with perturbed ordering and renamed candidate IDs produces zero new candidates; changed source content produces exactly one.
13. **Cross-schema parent chain** (M11) — a fixture bundle at schema version N-1 still resolves its digest and satisfies the parent-chain check under schema N.
14. **Mis-kinded reference** (M12) — a `metric.*` ID placed in `evidence_ids` fails at parse.
15. **Post-promotion formatting-only mutation** — reformat a promoted revision's YAML without changing content: assert the *stated* behavior. Under the current §7 the digest is unchanged and §21 L767's "revision unusable" is false; the test forces the spec to say which it means.

## Scope assessment

**Stops before tailoring: mostly, with three leaks.** §1–§13, §16–§21 are cleanly input-side. The leaks are `character_count` (m1, a layout constant from `resume_gate.py`), `role_families` on skills and claims (M13, selection policy), and `allowed_phrasings` / `forbidden_phrasings` — the last is defensible as owner-approved provenance under locked decision 4, but it is prose policy and §11 should say why it belongs here rather than in the projection design. §4.2's explicit boundary diagram (L65–81) and §6's note that Gate A refuses undeclared `policy/` files (L159–161) are genuinely good defenses.

**Generalized mechanism vs private content: correctly separated in intent, under-specified in mechanism.** §5's split (L91–99) is right and matches locked decision 8. But the design leans on the generalization checker without knowing what it does: the checker is shape-based only and, per `CONTRIBUTING.md:32-34`, "cannot catch personal values written into Python source or prose; code review is the control there." So §22 test 16's phrasing — "proving no personal data enters tracked files" — overstates what `make check` can prove. Two real interactions go unmentioned: the R7 pin burden on every shipped fixture, and R4's empty allowlist versus a contact-channel fixture (m5). And M2/M13 push field-specific content (predicates, role families) into code, which is the exact multi-tenancy failure CLAUDE.md names.

**Gate A / Gate B decomposition: the split is right; the halves are not symmetric.** Gate A (L806–816) is well-formed — every bullet maps to a §22 test group and it terminates in `make check` with a real exit code. Gate B (L821–832) is a checklist of unfalsifiable universals with no denominator, no sample, and no reviewer (M8). Gate B also correctly requires synthetic regression tests for schema defects it exposes (L834–835), which is the right instinct. Fix M8 and the decomposition is sound.

## Strongest counterargument

**The revision substrate is a hand-rolled, weaker Git, and roughly half this design is spent rebuilding it.**

Strip §6, §7's digest, §17's ledger, §19's checkout/promote, §20.6, and §21's crash rows, and what remains — typed entities, atomic facts, evidence contracts, conflicts and rulings, metric protection, surface isolation, skill backing, claim references — is the genuinely novel and valuable part, and it is *substrate-independent*. The substrate half, by contrast, re-implements immutable content-addressed revisions, parent-digest chains, atomic ref updates, tamper detection, locking, and history, and it is exactly where this review found its weakest guarantees: B4's unenforced append-only, M1's mechanism-free atomicity, M3's self-referential path, m3's absent GC, and the per-revision duplication of the whole document tree.

A private Git repository under the same application-support directory supplies every one of those, tested by millions of users, with `git fsck` for tamper detection and `git log` for history. The design acknowledges Git exists only to dismiss it in a subordinate clause (L183–184) and never argues the case. CLAUDE.md's own ordering — platform feature before new code — points the other way, as does its warning that a component's self-report is not verification: a hand-rolled promote that reports success is precisely the class of claim this program has repeatedly had to retract.

The counter-counterargument is real and should be *written down* rather than assumed: a `.git` directory inside an encrypted-backup target is a liability, a stray `git checkout`/`git gc` violates immutability from outside the tool, and Git's own atomicity guarantees on macOS are not stronger than a correctly-implemented `os.replace`. If those hold, the current design wins — but §4.1 has to say so.

## Recommendation

**Revise before implementation planning.**

Five blocking findings are correctness or trust defects, not clarifications: B1 defeats the privacy invariant the design exists to guarantee, B2 leaves the entire semantic layer undefined and unimplementable, B3 lets the LLM authoring workflow manufacture the owner authority that makes the bundle trustworthy at all, B4 makes "append-only" decorative, and B5's rule contradicts the spec's own worked example while missing the fabrication case that actually matters. None can be resolved during implementation without re-deciding the design.

The architecture is sound and the decomposition is right. The revision needed is concentrated: define the predicate catalog as versioned data (B2), make owner authority CLI-stamped (B3), state the surface-subset invariant over the whole reference graph (B1), add the prefix-preservation checks (B4), invert the metric-token rule (B5), pin the digest and promotion mechanisms (M1, M3), and give Gate B a denominator (M8). That is a focused second draft, not a redesign.
