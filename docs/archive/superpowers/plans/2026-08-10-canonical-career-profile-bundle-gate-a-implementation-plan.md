# Canonical Career-Profile Bundle Gate A Implementation Plan

> **For the implementing agent:** Execute this plan task-by-task in dependency order. No
> Superpowers workflow or plugin is required. Use each slice's checkbox steps, tests, and commit as
> its review boundary; stop on a design conflict instead of inventing a contract.

**Goal:** Build only Gate A's generalized, private-filesystem career-profile bundle mechanism: strict typed YAML, deterministic identity, layered validation, evidence and owner gates, imports, immutable revisions, drafts, crash-consistent promotion, deterministic CLI/JSON outcomes, and synthetic proof.

**Architecture:** Add an isolated `boardwatch.profile_bundle` package whose pure core parses a closed logical tree into strict Pydantic models, indexes and validates it, and computes canonical/candidate identities. A filesystem shell owns `CURRENT`, immutable digest-named revisions, drafts, external approval stamps, content-addressed evidence blobs, `FileLock` serialization, rebase, migration, and atomic promotion; a Typer sub-app translates typed outcomes to the design's 0/1/2/3 exit contract. Gate A remains disconnected from the SQLite store and from `boardwatch.tailor`.

**Tech Stack:** Python 3.11+, Pydantic 2, PyYAML `>=6.0,<7.0`, stdlib `hashlib`/`json`/`pathlib`/`unicodedata`/`os`/`tempfile`, existing `filelock`, Typer/Rich, pytest, Ruff, strict mypy, Hatch/uv packaging, and the existing generalization gate.

## Status and execution gate

**Plan status: READY FOR IMPLEMENTATION.** The live design now closes the schema-v1 bootstrap rule,
the exact unit/assertion/secret-scan v1 contracts, and all deterministic source-adapter and derived-ID
contracts. No known planning blocker remains. If implementation exposes a contradiction, stop and
record it against the design; do not silently widen Gate A.

## Global Constraints

- Gate A generalized bundle mechanism first. Gate B private canonical baseline begins only after Gate A is implemented and reviewed.
- Role-family projection, persona/claim selection, taxonomy integration, rendering, representative-JD evaluation, and tailoring evaluation remain separate designs after both gates.
- No personal profile values, résumé content, credentials, live-store artifacts, diagnostics with personal values, or private targeting policy may enter tracked files.
- The bundle default is resolved at the command boundary as `settings.config_dir / "career-profile"`; `--bundle PATH` overrides it. Do not add a `Settings` field or alter `policy_version`.
- Existing tailor commands continue to resolve `settings.config_dir / "resume.yaml"`. No profile-bundle module may be imported by `boardwatch.tailor`, `boardwatch.reports.tailor`, or `boardwatch.cli.tailor_cmd`.
- Gate A is filesystem-only. Do not modify `src/boardwatch/store/tables.py`, any Alembic migration, `tests/unit/test_store.py`, or the database schema head; bundle schema migrations are immutable filesystem revisions, not SQL migrations.
- Every model uses `ConfigDict(extra="forbid", frozen=True)`; every closed enum and ID prefix is enforced at parse time; unknown files and wrong owning files fail closed.
- Validation is time-pure. Structural validity never reads the clock. Completeness takes an explicit `as_of: date`, and CLI defaulting to the local date occurs only at the command boundary.
- Validation, inventory, inspect, and conflicts are read-only. No Gate A command deletes revisions, drafts, stamps, blobs, corrupt bytes, or complete-but-unselected revisions.
- All owner authority is candidate-digest-bound. Cooperative agents must stop before `approve`; there is no `--yes`, piped-stdin, environment, or agent bypass.
- Use `FileLock.acquire(blocking=False)`. Never infer lock ownership from lockfile existence, PID, age, or timestamp; never remove or break a persistent lockfile.
- Promotion must preserve the approved corrupt-parent recovery exception: only parent blob-integrity and completeness checks may be skipped, and only when the parent source tree and manifest envelope remain parseable and every ledger prefix remains exact.
- PyYAML must be narrowed to `>=6.0,<7.0` in both project metadata and `uv.lock` before the restricted loader contract is relied upon.
- Every tracked YAML/JSON example is synthetic, digest-pinned in `tools.generalization.allowlists.SHIPPED_DATA`, and present in the built wheel. Contact examples use `candidate@example.com` and `https://example.com/profile/example-candidate`, never LinkedIn or a `mailto` URI.
- Test module basenames must be globally unique because `tests/` has no package `__init__.py`.
- Run commands with `uv run ...`; neither `python` nor `boardwatch` is assumed on `PATH`.
- The final gate is an unpiped `make check` with its real exit code.

---

## Live repository integration map

| Existing seam | Gate A treatment |
|---|---|
| `src/boardwatch/cli/app.py` | Register exactly one new `profile-bundle` Typer sub-app. |
| `src/boardwatch/core/settings.py` | Read `settings.config_dir`; do not add or classify a setting. |
| `src/boardwatch/cli/tailor_cmd.py::_resume_path` | Characterize unchanged `settings.config_dir / "resume.yaml"`; no bridge/import. |
| `src/boardwatch/eligibility/hashing.py`, `extract/taxonomy.py::_version_of`, `eligibility/catalog.py::_version_of`, `tailor/persona.py::_version_of` | Pin existing non-ASCII behavior before adding the new NFC/`ensure_ascii=False` serializer; never consolidate these hashes. |
| `src/boardwatch/scan/coordinator.py` | Reuse only the `FileLock` dependency and non-blocking acquisition convention; bundle locking remains package-local. |
| `tools/generalization/allowlists.py`, `inventory.py`, `tests/generalization/test_inventory.py` | Admit and pin every new schema/example YAML or JSON file, with `synthetic` provenance for examples. |
| `tools/generalization/packaging.py`, `tests/generalization/test_packaging.py` | Prove JSON Schema and synthetic example resources enter the wheel. |
| `pyproject.toml`, `uv.lock` | Narrow PyYAML; rely on Hatch's package-data inclusion and verify the actual wheel. |
| `docs/configuration.md`, new authoring guide | Document bundle location, command contract, owner stop, recovery, and the unchanged tailor boundary. |

## Planned file architecture

| File | Single responsibility |
|---|---|
| `src/boardwatch/profile_bundle/errors.py` | Typed issue codes, validation tiers, operation outcome categories, and exceptions. |
| `src/boardwatch/profile_bundle/paths.py` | Default path resolution and safe draft/stamp/revision/blob path construction. |
| `src/boardwatch/profile_bundle/yaml_loader.py` | The only restricted PyYAML loader and UTF-8 document parser. |
| `src/boardwatch/profile_bundle/layout.py` | Closed logical-file grammar, owning-file rules, and source-tree discovery. |
| `src/boardwatch/profile_bundle/models/*.py` | Strict immutable typed records split by domain responsibility. |
| `src/boardwatch/profile_bundle/models/sidecars.py` | Private root `local-sources.yaml` mapping, excluded from revision identity and export. |
| `src/boardwatch/profile_bundle/schema.py` | Schema head/support constants and generated JSON Schema parity. |
| `src/boardwatch/profile_bundle/canonical.py` | NFC canonical JSON, document/blob leaves, evidence set, bundle digest, candidate digest, target digests. |
| `src/boardwatch/profile_bundle/index.py` | Global typed record index and graph lookup tables. |
| `src/boardwatch/profile_bundle/validation/*.py` | Structural, referential, evidence, semantic, completeness, and digest layers. |
| `src/boardwatch/profile_bundle/secret_scan.py` | Versioned built-in ruleset registry and byte/text scanning. |
| `src/boardwatch/profile_bundle/blobs.py` | Size/media/redaction checks and exclusive temporary capture-to-blob writes. |
| `src/boardwatch/profile_bundle/approvals.py` | Pure stamp construction, required sub-approval derivation, and binding validation. |
| `src/boardwatch/profile_bundle/imports.py` | Approved enumerator registry, locator/value normalization, derived IDs, occurrence merge, and denominator checks. |
| `src/boardwatch/profile_bundle/reports.py` | Deterministic diagnostic sorting and human/JSON render models. |
| `src/boardwatch/profile_bundle/storage.py` | One-read `CURRENT`, immutable revision reads, atomic writes/renames, and exact-target reuse checks. |
| `src/boardwatch/profile_bundle/drafts.py` | `init`, `checkout`, and draft validation orchestration. |
| `src/boardwatch/profile_bundle/rebase.py` | Record-level three-way rebase with exact deterministic backup behavior. |
| `src/boardwatch/profile_bundle/promotion.py` | Lock, parent recheck, derived revision data, prefix checks, recovery exception, from-disk verify, and pointer swap. |
| `src/boardwatch/profile_bundle/migrations.py` | Append-only supported bundle-schema transformations and migrate orchestration. |
| `src/boardwatch/cli/profile_bundle_cmd.py` | Typer commands, TTY owner interaction, and exit/JSON mapping only. |

---

### Task 1: Dependency floor, package boundary, paths, and typed outcomes

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `src/boardwatch/profile_bundle/__init__.py`
- Create: `src/boardwatch/profile_bundle/errors.py`
- Create: `src/boardwatch/profile_bundle/paths.py`
- Create: `tests/profile_bundle/test_profile_bundle_outcomes.py`
- Create: `tests/profile_bundle/test_profile_bundle_paths.py`

**Interfaces:**
- Consumes: `Settings.config_dir` only at callers; raw `Path` values inside this package.
- Produces:

```python
JsonScalar = str | int | bool | None
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
IssueTier = Literal["error", "blocker", "warning", "information"]
OutcomeCategory = Literal["clean", "findings", "usage_error", "could_not_complete"]

Sha256Digest = Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]
BareSha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]

class IssueCode(StrEnum):
    INVALID_YAML = "invalid_yaml"
    UNKNOWN_FILE = "unknown_file"
    BUNDLE_LOCK_HELD = "bundle_lock_held"
    STALE_DRAFT_PARENT = "stale_draft_parent"
    DRAFT_REBASE_CONFLICT = "draft_rebase_conflict"
    DRAFT_BACKUP_CONFLICT = "draft_backup_conflict"
    PROMOTION_TARGET_CONFLICT = "promotion_target_conflict"
    UNVERIFIABLE_ANCESTOR = "unverifiable_ancestor"
    UNSUPPORTED_SCHEMA_VERSION = "unsupported_schema_version"
    UNSUPPORTED_SECRET_SCAN_RULESET_VERSION = "unsupported_secret_scan_ruleset_version"

@dataclass(frozen=True)
class Diagnostic:
    tier: IssueTier
    code: str
    path: str | None
    record_id: str | None
    message: str
    details: Mapping[str, JsonValue]

@dataclass(frozen=True)
class OperationOutcome(Generic[T]):
    category: OutcomeCategory
    value: T | None
    diagnostics: tuple[Diagnostic, ...]
    exit_code: int

def outcome_for(code: IssueCode) -> OperationOutcome[None]: ...
def resolve_bundle_root(config_dir: Path, override: Path | None) -> Path: ...
def draft_root(bundle_root: Path, name: str) -> Path: ...
def approval_path(bundle_root: Path, candidate_digest: Sha256Digest) -> Path: ...
```

- [ ] **Step 1: Pin the exit and path contracts with failing tests**

```python
def test_state_refusal_and_finding_exit_one_but_io_exit_three() -> None:
    assert outcome_for(IssueCode.STALE_DRAFT_PARENT).exit_code == 1
    assert outcome_for(IssueCode.BUNDLE_LOCK_HELD).exit_code == 3

def test_bundle_default_is_config_dir_child_and_override_wins(tmp_path: Path) -> None:
    assert resolve_bundle_root(tmp_path / "cfg", None) == tmp_path / "cfg" / "career-profile"
    assert resolve_bundle_root(tmp_path / "cfg", tmp_path / "private") == tmp_path / "private"

@pytest.mark.parametrize("name", ["../escape", "/absolute", "a/b", "", ".", ".."])
def test_draft_name_cannot_escape_bundle(name: str, tmp_path: Path) -> None:
    with pytest.raises(BundlePathError):
        draft_root(tmp_path, name)
```

- [ ] **Step 2: Run the new tests and verify the package is absent**

Run: `uv run pytest tests/profile_bundle/test_profile_bundle_outcomes.py tests/profile_bundle/test_profile_bundle_paths.py -q`

Expected: FAIL during collection because `boardwatch.profile_bundle` does not exist.

- [ ] **Step 3: Narrow PyYAML and implement the typed package boundary**

Change the dependency to `"pyyaml>=6.0,<7.0"`, run `uv lock`, define the complete design-specified issue codes (not only the excerpt above), map outcome categories to `0/1/2/3`, validate lowercase full `sha256:<64-hex>` values, and confine all constructed paths under the resolved bundle root.

- [ ] **Step 4: Run targeted tests and dependency verification**

Run: `uv run pytest tests/profile_bundle/test_profile_bundle_outcomes.py tests/profile_bundle/test_profile_bundle_paths.py -q`

Expected: PASS.

Run: `uv tree | rg '^pyyaml|pyyaml'`

Expected: the resolved PyYAML version is `>=6.0` and `<7.0`, and `uv.lock` carries `<7.0` in the project requirement.

- [ ] **Step 5: Commit the slice**

```bash
git add pyproject.toml uv.lock src/boardwatch/profile_bundle tests/profile_bundle/test_profile_bundle_outcomes.py tests/profile_bundle/test_profile_bundle_paths.py
git commit -m "build(profile-bundle): pin loader dependency and core outcomes"
```

### Task 2: Restricted YAML loader and closed file grammar

**Files:**
- Create: `src/boardwatch/profile_bundle/yaml_loader.py`
- Create: `src/boardwatch/profile_bundle/layout.py`
- Create: `tests/profile_bundle/test_profile_bundle_yaml_loader.py`
- Create: `tests/profile_bundle/test_profile_bundle_layout.py`

**Interfaces:**
- Consumes: `BundlePathError`, `Diagnostic`, and `Sha256Digest` from Task 1.
- Produces:

```python
class CareerProfileLoader(yaml.SafeLoader): ...

def load_yaml_bytes(raw: bytes, *, logical_path: PurePosixPath) -> object: ...
def discover_source_files(root: Path, *, final_revision: bool) -> tuple[SourceFile, ...]: ...
def owner_for_path(path: PurePosixPath) -> DocumentKind: ...
```

The closed grammar is the design's complete logical tree, plus entity-owned `facts/experience/<employment-id>.yaml` and `facts/projects/<project-id>.yaml`. Final revisions permit exactly one non-source file, `COMPLETE`; drafts permit no non-source file. `policy/persona.yaml`, `policy/selection.yaml`, editor swap files, dotfiles, symlinks, and all undeclared extensions are rejected.

- [ ] **Step 1: Write loader edge-case tests**

```python
@pytest.mark.parametrize("token", ["yes", "no", "on", "off", "2026-08-10", "01", ".nan", ".inf"])
def test_ambiguous_plain_scalar_is_rejected(token: str) -> None:
    with pytest.raises(RestrictedYamlError):
        load_yaml_bytes(f"value: {token}\n".encode(), logical_path=PurePosixPath("facts/identity.yaml"))

def test_quoted_boolean_like_string_stays_a_string() -> None:
    assert load_yaml_bytes(b'value: "no"\n', logical_path=PurePosixPath("facts/identity.yaml")) == {"value": "no"}

@pytest.mark.parametrize("body", [b"a: 1\na: 2\n", b"base: &x {a: 1}\ncopy: *x\n", b"x: {<<: {a: 1}}\n"])
def test_duplicate_anchor_alias_and_merge_are_rejected(body: bytes) -> None:
    with pytest.raises(RestrictedYamlError):
        load_yaml_bytes(body, logical_path=PurePosixPath("manifest.yaml"))
```

- [ ] **Step 2: Write file-grammar and ownership tests**

Cover every declared aggregate file, wrong claim type/file, experience/project basename-to-ID mismatch, symlinks, `COMPLETE`, and explicit rejection of `policy/persona.yaml` and `policy/selection.yaml`.

- [ ] **Step 3: Run tests and verify they fail**

Run: `uv run pytest tests/profile_bundle/test_profile_bundle_yaml_loader.py tests/profile_bundle/test_profile_bundle_layout.py -q`

Expected: FAIL because the loader and grammar are undefined.

- [ ] **Step 4: Implement the loader without calling `yaml.safe_load` elsewhere**

Remove timestamp, YAML 1.1 boolean, legacy integer, and non-finite float resolvers; add exact `true|false` and ordinary base-10 integer resolvers; reject every alias/anchor/merge event and duplicate constructed mapping key. Decode UTF-8 strictly before parsing. Keep paths POSIX-relative and reject symlinks before reading bytes.

- [ ] **Step 5: Run targeted tests**

Run: `uv run pytest tests/profile_bundle/test_profile_bundle_yaml_loader.py tests/profile_bundle/test_profile_bundle_layout.py -q`

Expected: PASS.

- [ ] **Step 6: Commit the slice**

```bash
git add src/boardwatch/profile_bundle/yaml_loader.py src/boardwatch/profile_bundle/layout.py tests/profile_bundle/test_profile_bundle_yaml_loader.py tests/profile_bundle/test_profile_bundle_layout.py
git commit -m "feat(profile-bundle): add restricted YAML and closed layout"
```

### Task 3: Stable IDs, typed values, entities, contacts, facts, relations, and skills

**Files:**
- Create: `src/boardwatch/profile_bundle/models/__init__.py`
- Create: `src/boardwatch/profile_bundle/models/base.py`
- Create: `src/boardwatch/profile_bundle/models/entities.py`
- Create: `src/boardwatch/profile_bundle/models/facts.py`
- Create: `src/boardwatch/profile_bundle/models/relations.py`
- Create: `src/boardwatch/profile_bundle/models/skills.py`
- Create: `tests/profile_bundle/test_profile_bundle_entity_models.py`
- Create: `tests/profile_bundle/test_profile_bundle_fact_models.py`

**Interfaces:**
- Consumes: parsed Python objects from Task 2.
- Produces strict `RootModel` ID types for every prefix, discriminated fact values, every entity/status type, `ContactRecord`, `FactRecord`, `RelationRecord`, and `SkillRecord`.

```python
class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

class FactValue(RootModel[StringValue | IntegerValue | DecimalValue | BooleanValue | DateValue | YearMonthValue | DateRangeValue | UrlValue | StringListValue | SkillRefValue]): ...

class FactRecord(StrictModel):
    fact_id: FactId
    subject_id: EntityId
    predicate: PredicateId
    value: FactValue
    verification_state: VerificationState
    verification_basis: VerificationBasis
    usage_context: UsageContext
    evidence_ids: tuple[EvidenceId, ...]
    allowed_surfaces: frozenset[Surface]
    conflict_group_id: ConflictId | None
    reviewed_at: date
    expires_at: date | None
    supersedes_fact_ids: tuple[FactId, ...]
    import_lineage: ImportLineage | None
    notes: str | None
```

- [ ] **Step 1: Write exhaustive ID and enum tests**

Generate one valid instance of every design ID prefix and closed entity/status/state/basis/surface/context/channel enum. For every typed reference field, replace its value with a different valid prefix and assert Pydantic rejects it before graph validation.

- [ ] **Step 2: Write discriminated value and entity placement tests**

Pin decimal-as-string, year-month format, closed/open date ranges, URL parsing, no extra fields, one person type, contact `allowed_surfaces`, and all eleven initial entity kinds/status catalogs.

- [ ] **Step 3: Run tests and verify they fail**

Run: `uv run pytest tests/profile_bundle/test_profile_bundle_entity_models.py tests/profile_bundle/test_profile_bundle_fact_models.py -q`

Expected: FAIL because the models are absent.

- [ ] **Step 4: Implement strict models and no validation policy yet**

Keep record-shape parsing in this slice. Cross-record cardinality, evidence strength, effective state, surfaces, and conflict semantics belong to Tasks 8–10. Enforce only intrinsic shape: prefixes, formats, discriminants, duplicate items within set-like fields, and entity-specific status types.

- [ ] **Step 5: Run targeted tests**

Run: `uv run pytest tests/profile_bundle/test_profile_bundle_entity_models.py tests/profile_bundle/test_profile_bundle_fact_models.py -q`

Expected: PASS.

- [ ] **Step 6: Commit the slice**

```bash
git add src/boardwatch/profile_bundle/models tests/profile_bundle/test_profile_bundle_entity_models.py tests/profile_bundle/test_profile_bundle_fact_models.py
git commit -m "feat(profile-bundle): model entities facts relations and skills"
```

### Task 4: Revision-owned catalogs, evidence, metrics, claims, and application facts

**Files:**
- Create: `src/boardwatch/profile_bundle/models/policy.py`
- Create: `src/boardwatch/profile_bundle/models/evidence.py`
- Create: `src/boardwatch/profile_bundle/models/metrics.py`
- Create: `src/boardwatch/profile_bundle/models/claims.py`
- Create: `tests/profile_bundle/test_profile_bundle_policy_models.py`
- Create: `tests/profile_bundle/test_profile_bundle_evidence_models.py`
- Create: `tests/profile_bundle/test_profile_bundle_metric_claim_models.py`

**Interfaces:**
- Consumes: Task 3 IDs, values, entity kinds, surfaces, facts, and strict base model.
- Produces typed document rows for all seven policy catalogs, the six evidence-class discriminants, inline/blob captures and redactions, metrics/caveats, claims/metric mentions, and application-only fact documents.

```python
class PredicateSpec(StrictModel):
    predicate_id: PredicateId
    catalog_version: PositiveInt
    legal_subject_kinds: frozenset[EntityKind]
    legal_value_types: frozenset[FactValueKind]
    cardinality: Cardinality
    exclusivity: ExclusivitySpec
    minimum_evidence: tuple[EvidenceAlternative, ...]
    legal_verification_bases: frozenset[VerificationBasis]
    owner_attestation_authority: OwnerAttestationAuthority
    legal_surfaces: frozenset[Surface]
    surface_policy: SurfacePolicy
    legal_usage_contexts: frozenset[UsageContext]
    expiry: ExpirySpec
    may_ground_skill: bool

class BlobCapture(StrictModel):
    kind: Literal["blob"]
    sha256: BareSha256
    media_type: CaptureMediaType

class MetricRecord(StrictModel): ...
class ClaimRecord(StrictModel): ...
```

- [ ] **Step 1: Write exhaustive catalog-shape tests**

Pin every required serialized predicate column, catalog-version agreement, relation source/target
kinds, source metadata ownership, private synthetic skill categories, and the design's exact v1 row
shapes. Unit rows have exactly `unit_id`, `display_name`, `symbol`, `aliases`, and
`allowed_metric_kinds`; the comprehensive fixture contains only `items`, `milliseconds`,
`items_per_second`, `percent`, `usd`, `bytes`, `ordinal`, and `points`, covering all metric kinds with
no conversions or implicit aliases. Assertion-tag rows have exactly `tag_id`, `high_risk`,
`legal_subject_kinds`, and structured `authorization_any_of` branches. Pin all 12 design-defined
tags and their exact status, fact-predicate/value, or same-subject eligible-metric authorizations.
Omitted contract fields, prose authorization strings, illegal aliases, and unknown rows fail.

- [ ] **Step 2: Write evidence/metric/claim parse tests**

Cover inline versus blob exclusivity, every evidence-class required/illegal field, exact redaction shape, metric kinds/qualifiers/caveat severities, claim type-to-owning-file, status, required references, and application-only parse shape.

- [ ] **Step 3: Run tests and verify they fail**

Run: `uv run pytest tests/profile_bundle/test_profile_bundle_policy_models.py tests/profile_bundle/test_profile_bundle_evidence_models.py tests/profile_bundle/test_profile_bundle_metric_claim_models.py -q`

Expected: FAIL because the policy/evidence/metric/claim models are absent.

- [ ] **Step 4: Implement the strict shapes and frozen v1 rows**

Represent catalog semantics as revision data parsed into models. Code may define schema enums and
the exact built-in secret-rule registry from design §12.2, but it must compare the revision's rows and
version to the live design's v1 contract instead of supplying missing YAML defaults. Do not create a
universal built-in unit vocabulary or software-only skill categories.

- [ ] **Step 5: Run targeted tests**

Run: `uv run pytest tests/profile_bundle/test_profile_bundle_policy_models.py tests/profile_bundle/test_profile_bundle_evidence_models.py tests/profile_bundle/test_profile_bundle_metric_claim_models.py -q`

Expected: PASS.

- [ ] **Step 6: Commit the slice**

```bash
git add src/boardwatch/profile_bundle/models tests/profile_bundle/test_profile_bundle_policy_models.py tests/profile_bundle/test_profile_bundle_evidence_models.py tests/profile_bundle/test_profile_bundle_metric_claim_models.py
git commit -m "feat(profile-bundle): model policy evidence metrics and claims"
```

### Task 5: Manifests, history, conflicts, approvals, imports, document registry, and schema export

**Files:**
- Create: `src/boardwatch/profile_bundle/models/history.py`
- Create: `src/boardwatch/profile_bundle/models/imports.py`
- Create: `src/boardwatch/profile_bundle/models/manifests.py`
- Create: `src/boardwatch/profile_bundle/models/documents.py`
- Create: `src/boardwatch/profile_bundle/models/sidecars.py`
- Create: `src/boardwatch/profile_bundle/schema.py`
- Create: `src/boardwatch/profile_bundle/resources/__init__.py`
- Create: `src/boardwatch/profile_bundle/resources/career-profile.schema.json`
- Create: `tests/profile_bundle/test_profile_bundle_history_models.py`
- Create: `tests/profile_bundle/test_profile_bundle_import_models.py`
- Create: `tests/profile_bundle/test_profile_bundle_schema_export.py`
- Create: `tests/profile_bundle/test_profile_bundle_sidecars.py`
- Modify: `tools/generalization/allowlists.py`
- Modify: `tests/generalization/test_inventory.py`

**Interfaces:**
- Consumes: all Task 3–4 record models.
- Produces `DraftManifest`/`RevisionManifest`, conflict/ruling and ledger models, one-stamp/many-entry approval models, import ledger/candidate/exclusion models, typed per-file document wrappers, `BundleDocuments`, the private root sidecar model, and `bundle_json_schema()`.

```python
class DraftManifest(StrictModel):
    schema_version: PositiveInt
    state: Literal["draft"]
    profile_id: ProfileId
    draft_of_revision: NonNegativeInt | None
    parent_bundle_digest: Sha256Digest | None
    bundle_digest: Literal[""]
    evidence_set_digest: Sha256Digest
    approved_candidate_digest: Literal[""]
    approval_stamp_id: Literal[""]
    change_id: Literal[""]
    predicate_catalog_version: PositiveInt
    unit_catalog_version: PositiveInt
    relation_catalog_version: PositiveInt
    skill_category_catalog_version: PositiveInt
    assertion_tag_catalog_version: PositiveInt
    secret_scan_ruleset_version: PositiveInt

class RevisionManifest(StrictModel): ...

class BundleDocuments(StrictModel):
    manifest: DraftManifest | RevisionManifest
    by_path: Mapping[PurePosixPath, DocumentModel]

class LocalSourcesSidecar(RootModel[dict[SourceId, AbsolutePath]]): ...
```

External approval stamp files use `approvals/sha256-<64-hex-candidate-digest>.yaml`; the digest in the filename must equal `candidate_content_digest`. This deterministic location preserves stale stamps without draft-name aliasing.

- [ ] **Step 1: Write strict manifest/history/import tests**

Pin draft sentinels and forbidden promotion fields, revision-required fields, every ruling decision, every approval action/result combination, zero/one/many stamp entries, append-only ledger document shapes, exact source-ledger/disposition arithmetic fields, candidate occurrences, all exclusion reasons, and the root-only `local-sources.yaml` map. Sidecar roots must be absolute machine-local paths, source IDs must resolve to revision-owned portable source metadata when a revision is selected, and the sidecar must reject professional record fields.

- [ ] **Step 2: Write JSON Schema parity test before committing the schema**

```python
def test_committed_json_schema_matches_models() -> None:
    committed = json.loads(resources.files("boardwatch.profile_bundle.resources").joinpath("career-profile.schema.json").read_text())
    assert committed == bundle_json_schema()
```

Also load representative valid/invalid objects through both Pydantic and `jsonschema` only if `jsonschema` is already present; do not add it solely for parity. The authoritative parity check is exact generated-document equality plus model tests.

- [ ] **Step 3: Run tests and verify they fail**

Run: `uv run pytest tests/profile_bundle/test_profile_bundle_history_models.py tests/profile_bundle/test_profile_bundle_import_models.py tests/profile_bundle/test_profile_bundle_schema_export.py tests/profile_bundle/test_profile_bundle_sidecars.py -q`

Expected: FAIL because the models/schema exporter are absent.

- [ ] **Step 4: Implement models, generate the schema, and inventory it**

Run: `uv run python -c 'from pathlib import Path; from boardwatch.profile_bundle.schema import schema_json; Path("src/boardwatch/profile_bundle/resources/career-profile.schema.json").write_text(schema_json() + "\n", encoding="utf-8")'`

Add the JSON file to `SHIPPED_DATA` as `kind="template"`, `provenance="first-party"`, with its raw-byte SHA-256 pin. Update the inventory test's exact count and assert the schema path is in scope.

- [ ] **Step 5: Run targeted and inventory tests**

Run: `uv run pytest tests/profile_bundle/test_profile_bundle_history_models.py tests/profile_bundle/test_profile_bundle_import_models.py tests/profile_bundle/test_profile_bundle_schema_export.py tests/profile_bundle/test_profile_bundle_sidecars.py tests/generalization/test_inventory.py -q`

Expected: PASS.

- [ ] **Step 6: Commit the slice**

```bash
git add src/boardwatch/profile_bundle/models src/boardwatch/profile_bundle/schema.py src/boardwatch/profile_bundle/resources tools/generalization/allowlists.py tests/profile_bundle tests/generalization/test_inventory.py
git commit -m "feat(profile-bundle): complete document models and schema export"
```

### Task 6: Synthetic comprehensive logical bundle and package-data proof

**Files:**
- Create: `src/boardwatch/profile_bundle/examples/comprehensive/manifest.yaml`
- Create: `src/boardwatch/profile_bundle/examples/comprehensive/facts/identity.yaml`
- Create: `src/boardwatch/profile_bundle/examples/comprehensive/facts/education.yaml`
- Create: `src/boardwatch/profile_bundle/examples/comprehensive/facts/experience/employment.example-labs.yaml`
- Create: `src/boardwatch/profile_bundle/examples/comprehensive/facts/projects/project.packet-pantry.yaml`
- Create: `src/boardwatch/profile_bundle/examples/comprehensive/facts/publications.yaml`
- Create: `src/boardwatch/profile_bundle/examples/comprehensive/facts/awards.yaml`
- Create: `src/boardwatch/profile_bundle/examples/comprehensive/facts/certifications.yaml`
- Create: `src/boardwatch/profile_bundle/examples/comprehensive/facts/affiliations.yaml`
- Create: `src/boardwatch/profile_bundle/examples/comprehensive/facts/courses.yaml`
- Create: `src/boardwatch/profile_bundle/examples/comprehensive/facts/presentations.yaml`
- Create: `src/boardwatch/profile_bundle/examples/comprehensive/facts/patents.yaml`
- Create: `src/boardwatch/profile_bundle/examples/comprehensive/claims/bullet-candidates.yaml`
- Create: `src/boardwatch/profile_bundle/examples/comprehensive/claims/summary-candidates.yaml`
- Create: `src/boardwatch/profile_bundle/examples/comprehensive/skills/inventory.yaml`
- Create: `src/boardwatch/profile_bundle/examples/comprehensive/metrics/records.yaml`
- Create: `src/boardwatch/profile_bundle/examples/comprehensive/evidence/records.yaml`
- Create: `src/boardwatch/profile_bundle/examples/comprehensive/conflicts/groups.yaml`
- Create: `src/boardwatch/profile_bundle/examples/comprehensive/conflicts/rulings.yaml`
- Create: `src/boardwatch/profile_bundle/examples/comprehensive/policy/predicates.yaml`
- Create: `src/boardwatch/profile_bundle/examples/comprehensive/policy/units.yaml`
- Create: `src/boardwatch/profile_bundle/examples/comprehensive/policy/relations.yaml`
- Create: `src/boardwatch/profile_bundle/examples/comprehensive/policy/sources.yaml`
- Create: `src/boardwatch/profile_bundle/examples/comprehensive/policy/skill-categories.yaml`
- Create: `src/boardwatch/profile_bundle/examples/comprehensive/policy/assertion-tags.yaml`
- Create: `src/boardwatch/profile_bundle/examples/comprehensive/policy/secret-scan.yaml`
- Create: `src/boardwatch/profile_bundle/examples/comprehensive/relations/records.yaml`
- Create: `src/boardwatch/profile_bundle/examples/comprehensive/imports/source-ledger.yaml`
- Create: `src/boardwatch/profile_bundle/examples/comprehensive/imports/candidates.yaml`
- Create: `src/boardwatch/profile_bundle/examples/comprehensive/imports/exclusions.yaml`
- Create: `src/boardwatch/profile_bundle/examples/comprehensive/application/gated-facts.yaml`
- Create: `src/boardwatch/profile_bundle/examples/comprehensive/history/changes.yaml`
- Create: `src/boardwatch/profile_bundle/examples/comprehensive/history/approvals.yaml`
- Create: `tests/profile_bundle/conftest.py`
- Create: `tests/profile_bundle/test_profile_bundle_comprehensive_example.py`
- Modify: `tools/generalization/allowlists.py`
- Modify: `tests/generalization/test_inventory.py`
- Modify: `tests/generalization/test_packaging.py`

**Interfaces:**
- Consumes: `BundleDocuments`, strict loader/layout, JSON Schema, and the blocker-closure catalog rows.
- Produces a packaged, parentless comprehensive draft fixture and `synthetic_bundle(tmp_path) -> SyntheticBundle` test fixture that copies it, creates any raw blob bytes, computes current digests, and can be approved/promoted by later tests.

- [ ] **Step 1: Author the fixture as a parentless draft using only synthetic values**

Use `profile.example-candidate`, `person.example-candidate`, fictional Example Labs/University records, `candidate@example.com`, and `https://example.com/profile/example-candidate`. Include at least one of every entity and record kind, both capture kinds, every catalog, an unresolved conflict, a ruled conflict, a stale record, a supersession edge, application-only facts, all claim types in their correct files, all metric caveat severities, and zero personal paths.

- [ ] **Step 2: Write complete-placement and unknown-placement tests**

Parse every file into its declared wrapper; assert every model class appears; clone one record into every wrong owner file and assert failure; add every undeclared path from test group 28 and assert `unknown_file`.

- [ ] **Step 3: Inventory and pin every YAML resource**

Add each exact YAML path above to `SHIPPED_DATA` as `kind="fixture"`, `provenance="synthetic"`, `source="generated for Gate A model and validation tests"`, and its raw-byte SHA-256 pin. Update exact inventory count and add a test that all paths beneath `boardwatch/profile_bundle/examples/` are pinned and synthetic.

- [ ] **Step 4: Run example/generalization/packaging tests**

Run: `uv run pytest tests/profile_bundle/test_profile_bundle_comprehensive_example.py tests/generalization/test_inventory.py tests/generalization/test_packaging.py -q`

Expected: PASS, and the wheel test sees both `boardwatch/profile_bundle/resources/career-profile.schema.json` and the comprehensive example tree.

- [ ] **Step 5: Commit the slice**

```bash
git add src/boardwatch/profile_bundle/examples tools/generalization/allowlists.py tests/profile_bundle tests/generalization/test_inventory.py tests/generalization/test_packaging.py
git commit -m "test(profile-bundle): add comprehensive synthetic bundle"
```

### Task 7: Private canonical serializer, evidence set, bundle identity, and hash isolation

**Files:**
- Create: `src/boardwatch/profile_bundle/canonical.py`
- Create: `tests/profile_bundle/test_profile_bundle_canonical_identity.py`
- Create: `tests/profile_bundle/test_profile_bundle_hash_isolation.py`

**Interfaces:**
- Consumes: validated models/documents and raw referenced blob bytes.
- Produces:

```python
def canonical_json_bytes(value: object) -> bytes: ...
def record_digest(record: StrictModel) -> Sha256Digest: ...
def evidence_set_digest(documents: BundleDocuments, blobs: BlobReader) -> Sha256Digest: ...
def bundle_digest(documents: BundleDocuments, blobs: BlobReader) -> Sha256Digest: ...
def candidate_content_digest(documents: BundleDocuments, parent: StableManifestEnvelope | None) -> Sha256Digest: ...
def candidate_digest_from_revision(documents: BundleDocuments, parent: StableManifestEnvelope | None) -> Sha256Digest: ...
def source_scope_target_digest(source: SourceSpec, ledger: SourceLedgerSource) -> Sha256Digest: ...
def source_exclusion_target_digest(record: SourceLedgerRecord, exclusion: ExclusionRecord) -> Sha256Digest: ...
```

- [ ] **Step 1: Characterize all existing serializer hashes with one non-ASCII payload**

Pin exact current outputs from eligibility hashing, taxonomy, eligibility catalog, and persona. Assert no existing module imports `boardwatch.profile_bundle.canonical`.

- [ ] **Step 2: Write canonical identity tests**

Cover NFC versus decomposed Unicode, mapping-order/YAML-format neutrality, significant list order, date/datetime ISO output, `ensure_ascii=False`, no NaN, lowercase textual digest form, manifest empty-sentinel behavior, full canonical key framing, blob dedupe, evidence-document sensitivity, changed stored sentinel neutrality, path relocation neutrality, and proof that changing only root `local-sources.yaml` cannot change evidence, candidate, or bundle identity.

- [ ] **Step 3: Write candidate forward/inverse tests**

Build a draft, compute its candidate digest, append one stamp/change during synthetic promotion, inverse-normalize the revision, and assert equality among draft candidate digest, manifest field, stamp field, and recomputed revision candidate view. Editing any owner-gated record must change it.

- [ ] **Step 4: Run tests and verify they fail**

Run: `uv run pytest tests/profile_bundle/test_profile_bundle_canonical_identity.py tests/profile_bundle/test_profile_bundle_hash_isolation.py -q`

Expected: FAIL because canonical functions are absent.

- [ ] **Step 5: Implement the exact six-step bundle algorithm and candidate views**

Use model dumps in JSON mode, recursively NFC-normalize all strings, preserve JSON booleans/integers, reject floats/non-string mapping keys, key document leaves as `doc:<revision-relative-path>`, key blob leaves as `blob:sha256:<full-digest>`, and canonicalize the sorted list of `[canonical_key, leaf_digest]` pairs. Never use delimiter concatenation.

- [ ] **Step 6: Run targeted tests**

Run: `uv run pytest tests/profile_bundle/test_profile_bundle_canonical_identity.py tests/profile_bundle/test_profile_bundle_hash_isolation.py -q`

Expected: PASS.

- [ ] **Step 7: Commit the slice**

```bash
git add src/boardwatch/profile_bundle/canonical.py tests/profile_bundle/test_profile_bundle_canonical_identity.py tests/profile_bundle/test_profile_bundle_hash_isolation.py
git commit -m "feat(profile-bundle): add isolated canonical identity"
```

### Task 8: Document loading, global index, structural and referential validation

**Files:**
- Create: `src/boardwatch/profile_bundle/index.py`
- Create: `src/boardwatch/profile_bundle/validation/__init__.py`
- Create: `src/boardwatch/profile_bundle/validation/context.py`
- Create: `src/boardwatch/profile_bundle/validation/structural.py`
- Create: `src/boardwatch/profile_bundle/validation/referential.py`
- Create: `tests/profile_bundle/test_profile_bundle_structural_validation.py`
- Create: `tests/profile_bundle/test_profile_bundle_referential_validation.py`

**Interfaces:**
- Consumes: Tasks 2–7.
- Produces:

```python
@dataclass(frozen=True)
class BundleIndex:
    records: Mapping[RecordId, Record]
    by_kind: Mapping[RecordKind, tuple[Record, ...]]
    evidence_links: Mapping[RecordId, tuple[EvidenceId, ...]]
    approval_entries: Mapping[ApprovalId, ApprovalEntry]

@dataclass(frozen=True)
class ValidationContext:
    root: Path
    documents: BundleDocuments
    index: BundleIndex
    parent: ParentSnapshot | None
    blob_reader: BlobReader

def load_documents(root: Path, *, mode: Literal["draft", "revision"]) -> BundleDocuments: ...
def validate_structural(ctx: ValidationContext) -> tuple[Diagnostic, ...]: ...
def validate_referential(ctx: ValidationContext) -> tuple[Diagnostic, ...]: ...
```

- [ ] **Step 1: Write structural tests over the comprehensive fixture**

Pin UTF-8/YAML/model/layout errors, global ID uniqueness, record-prefix agreement, aggregate owner placement, experience/project basename equality, manifest/catalog version agreement, and unsupported-newer-schema as a typed could-not-complete outcome rather than an unknown enum.

- [ ] **Step 2: Write referential graph tests**

Cover every reference kind, bidirectional evidence links, acyclic fact supersession, conflict candidate subject/predicate agreement, active-ruling membership, relation catalog typing, approval sub-entry uniqueness, source-ledger exact per-source order, and localized unresolved-conflict reachability.

- [ ] **Step 3: Run tests and verify they fail**

Run: `uv run pytest tests/profile_bundle/test_profile_bundle_structural_validation.py tests/profile_bundle/test_profile_bundle_referential_validation.py -q`

Expected: FAIL because indexing and validation layers are absent.

- [ ] **Step 4: Implement deterministic load/index/validation**

Diagnostics sort by `(tier rank, code, path or "", record_id or "", message)` and never embed full contact/evidence values in messages or JSON details. Accumulate independent findings after parse succeeds; stop only when a layer cannot safely construct its input.

- [ ] **Step 5: Run targeted tests**

Run: `uv run pytest tests/profile_bundle/test_profile_bundle_structural_validation.py tests/profile_bundle/test_profile_bundle_referential_validation.py -q`

Expected: PASS.

- [ ] **Step 6: Commit the slice**

```bash
git add src/boardwatch/profile_bundle/index.py src/boardwatch/profile_bundle/validation tests/profile_bundle/test_profile_bundle_structural_validation.py tests/profile_bundle/test_profile_bundle_referential_validation.py
git commit -m "feat(profile-bundle): validate structure and references"
```

### Task 9: Evidence blobs, redactions, byte budgets, and versioned secret scanning

**Files:**
- Create: `src/boardwatch/profile_bundle/secret_scan.py`
- Create: `src/boardwatch/profile_bundle/blobs.py`
- Create: `src/boardwatch/profile_bundle/validation/evidence.py`
- Create: `tests/profile_bundle/test_profile_bundle_secret_scan.py`
- Create: `tests/profile_bundle/test_profile_bundle_blob_store.py`
- Create: `tests/profile_bundle/test_profile_bundle_evidence_validation.py`

**Interfaces:**
- Consumes: evidence/policy models, bundle index, approval lookup interface, raw bytes.
- Produces:

```python
MAX_CAPTURE_BYTES = 1_048_576
MAX_REVISION_EVIDENCE_BYTES = 52_428_800

def scan_capture(raw: bytes, *, media_type: CaptureMediaType, ruleset_version: int) -> tuple[SecretHit, ...]: ...
def write_blob(bundle_root: Path, raw: bytes, *, expected_digest: BareSha256, media_type: CaptureMediaType) -> BlobWriteResult: ...
def validate_evidence_structural(ctx: ValidationContext) -> tuple[Diagnostic, ...]: ...
def evidence_completeness(ctx: ValidationContext, *, installed_ruleset_version: int) -> tuple[Diagnostic, ...]: ...
```

- [ ] **Step 1: Write exact-ruleset and stronger-ruleset tests**

Assert recorded v1 hits are structural errors, unavailable recorded versions return
`unsupported_secret_scan_ruleset_version`/exit 3, and hits found only by a stronger installed version
are completeness blockers. Pin the design's exact eight v1 rows—`private-key-block`,
`authorization-header`, `cookie-header`, `credential-url`, `generic-secret-assignment`,
`aws-access-key-id`, `github-token`, and `slack-token`—with one positive and one near-miss negative
fixture each. Assert exact canonical catalog equality, closed flags (`ignore_case`, `multiline`),
UTF-8 decoded scanning, and absence of an entropy heuristic.

- [ ] **Step 2: Write blob/redaction/budget tests**

Cover exclusive temp creation, pre/post-write digest verification, atomic rename, exact-match existing blob reuse, read-only best effort, per-capture 1 MiB, unique aggregate 50 MiB, allowed media, invalid UTF-8 text, exact ASCII redaction marker at half-open UTF-8 byte ranges, non-overlap, secret scanning, and absolute home paths in YAML and decoded captures.

- [ ] **Step 3: Write evidence graph/authority tests**

Cover all evidence-class structural contracts, record-to-evidence direction equality, contextual evidence not satisfying support, owner-approved sufficiency target digest, owner attestation requiring `confirm_fact`, missing/tampered blobs, duplicate blob set semantics, and logical quarantine without moving bytes.

- [ ] **Step 4: Run tests and verify they fail**

Run: `uv run pytest tests/profile_bundle/test_profile_bundle_secret_scan.py tests/profile_bundle/test_profile_bundle_blob_store.py tests/profile_bundle/test_profile_bundle_evidence_validation.py -q`

Expected: FAIL because scanner/blob/evidence validators are absent.

- [ ] **Step 5: Implement fail-closed capture handling**

Scan canonical inline UTF-8 and decoded UTF-8 blob text at add time and every full validation.
`validate_evidence_structural` uses exactly the manifest-recorded ruleset; for v1 its catalog must be
canonically equal to the built-in v1 rows. `evidence_completeness` additionally uses a stronger
installed ruleset and is called only for requested completeness. Never log capture bytes or matched
secret text; diagnostics carry rule ID, evidence ID, and byte range only. Deduplicate aggregate size
by full raw-byte digest.

- [ ] **Step 6: Run targeted tests**

Run: `uv run pytest tests/profile_bundle/test_profile_bundle_secret_scan.py tests/profile_bundle/test_profile_bundle_blob_store.py tests/profile_bundle/test_profile_bundle_evidence_validation.py -q`

Expected: PASS.

- [ ] **Step 7: Commit the slice**

```bash
git add src/boardwatch/profile_bundle/secret_scan.py src/boardwatch/profile_bundle/blobs.py src/boardwatch/profile_bundle/validation/evidence.py tests/profile_bundle/test_profile_bundle_secret_scan.py tests/profile_bundle/test_profile_bundle_blob_store.py tests/profile_bundle/test_profile_bundle_evidence_validation.py
git commit -m "feat(profile-bundle): validate evidence and content-addressed blobs"
```

### Task 10: Predicate, state, surface, metric, skill, assertion-tag, and claim semantics

**Files:**
- Create: `src/boardwatch/profile_bundle/effective.py`
- Create: `src/boardwatch/profile_bundle/validation/semantic.py`
- Create: `tests/profile_bundle/test_profile_bundle_predicate_semantics.py`
- Create: `tests/profile_bundle/test_profile_bundle_surface_semantics.py`
- Create: `tests/profile_bundle/test_profile_bundle_metric_semantics.py`
- Create: `tests/profile_bundle/test_profile_bundle_claim_semantics.py`

**Interfaces:**
- Consumes: validated structure/references/evidence, active catalogs, approval lookup.
- Produces:

```python
def effective_fact(fact: FactRecord, ctx: ValidationContext) -> bool: ...
def eligible_fact_surfaces(fact: FactRecord, ctx: ValidationContext) -> frozenset[Surface]: ...
def validate_semantic(ctx: ValidationContext) -> tuple[Diagnostic, ...]: ...
```

- [ ] **Step 1: Generate one parameterized contract case per initial predicate**

For every serialized predicate row, test accepted subject/value/basis/evidence/context/surface and one rejection for each illegal dimension. Add cardinality/exclusivity, effective-only counting, supersession correction, conflict blocking, expiry remaining outside structural semantics, and `technology.used` having no inherited interval.

- [ ] **Step 2: Write surface and application-only tests**

Pin skill union support per requested surface, claim intersection across every required fact/metric, monotonic skill support when another true fact is added, application-only non-widening, metric `approve_metric_surfaces`, contact approval, and relations exposing no surfaces.

- [ ] **Step 3: Write metric, assertion-tag, and claim tests**

Cover exact metric subject/value/unit/qualifier/method/context/evidence/phrasing/protected tokens/caveats; all exact assertion-tag authorization rows; rejection of `ga_release` and `in_production`; high-risk `production` requiring evidence-backed deployment status; claim fact eligibility; every numeral/range/percentage/duration/currency/unit trace; `qualitative_only`; forbidden phrasing; and protected-token preservation.

- [ ] **Step 4: Run tests and verify they fail**

Run: `uv run pytest tests/profile_bundle/test_profile_bundle_predicate_semantics.py tests/profile_bundle/test_profile_bundle_surface_semantics.py tests/profile_bundle/test_profile_bundle_metric_semantics.py tests/profile_bundle/test_profile_bundle_claim_semantics.py -q`

Expected: FAIL because semantic validation is absent.

- [ ] **Step 5: Implement semantic validation as catalog interpretation**

Do not branch on personal values or career field. Interpret the active revision's catalogs exhaustively, fail on unknown catalog versions, derive effective state from facts/conflicts/supersession, and keep natural-language entailment outside Gate A.

- [ ] **Step 6: Run targeted tests**

Run: `uv run pytest tests/profile_bundle/test_profile_bundle_predicate_semantics.py tests/profile_bundle/test_profile_bundle_surface_semantics.py tests/profile_bundle/test_profile_bundle_metric_semantics.py tests/profile_bundle/test_profile_bundle_claim_semantics.py -q`

Expected: PASS.

- [ ] **Step 7: Commit the slice**

```bash
git add src/boardwatch/profile_bundle/effective.py src/boardwatch/profile_bundle/validation/semantic.py tests/profile_bundle/test_profile_bundle_predicate_semantics.py tests/profile_bundle/test_profile_bundle_surface_semantics.py tests/profile_bundle/test_profile_bundle_metric_semantics.py tests/profile_bundle/test_profile_bundle_claim_semantics.py
git commit -m "feat(profile-bundle): enforce catalog and surface semantics"
```

### Task 11: Owner-gate derivation, pure approval stamps, conflicts, and ledger prefixes

**Files:**
- Create: `src/boardwatch/profile_bundle/approvals.py`
- Create: `src/boardwatch/profile_bundle/validation/history.py`
- Create: `tests/profile_bundle/test_profile_bundle_approval_gates.py`
- Create: `tests/profile_bundle/test_profile_bundle_conflict_history.py`

**Interfaces:**
- Consumes: candidate/target digest functions, current draft/revision, parent snapshot, index.
- Produces:

```python
@dataclass(frozen=True)
class ApprovalDecision:
    action: ApprovalAction
    target_record_id: RecordId
    target_content_digest: Sha256Digest
    resulting_state: str

def required_approval_decisions(candidate: BundleDocuments, parent: BundleDocuments | None) -> tuple[ApprovalDecision, ...]: ...
def build_approval_stamp(*, stamp_id: ApprovalStampId, candidate_digest: Sha256Digest, approved_at: datetime, decisions: Sequence[ApprovalDecision]) -> ApprovalStamp: ...
def validate_history(ctx: ValidationContext) -> tuple[Diagnostic, ...]: ...
```

- [ ] **Step 1: Write every owner-trigger test**

Cover `confirm_fact`, `confirm_contact`, evidence sufficiency, claim approval, metric surfaces, joined source scope, joined source exclusion, and conflict ruling. For each trigger test correct binding, missing action, wrong target kind, wrong target digest, wrong resulting state, duplicate approval ID, forged YAML state, and a post-approval content edit.

- [ ] **Step 2: Write conflict and prefix tests**

Cover conflict creation/resolution/reopening/local blocking, every ruling decision, mandatory ruling authorization, identical parent ruling/change/approval prefixes, exactly one appended change/stamp, change-ledger length equals revision, and removal/reorder/edit failures.

- [ ] **Step 3: Run tests and verify they fail**

Run: `uv run pytest tests/profile_bundle/test_profile_bundle_approval_gates.py tests/profile_bundle/test_profile_bundle_conflict_history.py -q`

Expected: FAIL because approval/history services are absent.

- [ ] **Step 4: Implement pure stamp construction and mechanical owner gates**

`build_approval_stamp` performs no TTY checks and no filesystem writes. Derive `authorized_by` from the matching stamp; never trust an authored `authorized_by` string. A revision stamp may contain zero entries only when the diff triggers no sub-approval.

- [ ] **Step 5: Run targeted tests**

Run: `uv run pytest tests/profile_bundle/test_profile_bundle_approval_gates.py tests/profile_bundle/test_profile_bundle_conflict_history.py -q`

Expected: PASS.

- [ ] **Step 6: Commit the slice**

```bash
git add src/boardwatch/profile_bundle/approvals.py src/boardwatch/profile_bundle/validation/history.py tests/profile_bundle/test_profile_bundle_approval_gates.py tests/profile_bundle/test_profile_bundle_conflict_history.py
git commit -m "feat(profile-bundle): enforce owner gates and append-only history"
```

### Task 12: Deterministic enumeration, candidate identity, and idempotent import

**Files:**
- Create: `src/boardwatch/profile_bundle/enumerators.py`
- Create: `src/boardwatch/profile_bundle/imports.py`
- Create: `src/boardwatch/profile_bundle/validation/imports.py`
- Create: `tests/profile_bundle/test_profile_bundle_source_enumeration.py`
- Create: `tests/profile_bundle/test_profile_bundle_import_idempotency.py`

**Interfaces:**
- Consumes: approved source/enumerator catalogs, typed values/predicate contracts, import documents.
- Produces:

```python
class SourceEnumerator(Protocol):
    id: str
    version: int
    def enumerate(self, source: bytes, *, scope: ApprovedScope) -> tuple[EnumeratedSourceRecord, ...]: ...

def normalize_locator(raw: str, *, adapter: SourceEnumerator) -> str: ...
def derive_source_record_id(source_id: SourceId, normalized_locator: str) -> SourceRecordId: ...
def canonicalize_candidate_value(value: FactValue, predicate: PredicateSpec) -> FactValue: ...
def derive_candidate_id(source_record_id: SourceRecordId, predicate: PredicateId, value: FactValue) -> CandidateId: ...
def merge_candidate_package(existing: CandidatePackage, incoming: CandidatePackage) -> ImportMergeResult: ...
def validate_imports(ctx: ValidationContext) -> tuple[Diagnostic, ...]: ...
```

- [ ] **Step 1: Write one deterministic positive/negative suite per approved adapter**

Pin the closed source-kind/adapter pairs: `boardwatch_resume`/`boardwatch-resume-v1`,
`markdown_document`/`markdown-blocks-v1`, `structured_objects`/`structured-objects-v1`, and
`repository_markdown`/`markdown-blocks-v1`, all version 1. For each, pin the design's accepted input,
atomic-unit boundaries, raw source digest, normalized-record digest, NFC percent-encoded POSIX
locators, empty/absolute/`.`/`..` rejection, case preservation, canonical ordering, stable record IDs
across changed bytes at the same locator, and changed content digests without denominator churn.

For `boardwatch-resume-v1`, cover the exact duplicate source model and ordered header lines, optional
top-level title, education rows, grouped skill items, complete entry metadata, ID-addressed complete
bullet objects, and extracurricular rows plus blank/duplicate-ID failures. For
`markdown-blocks-v1`, cover the exact design regex/indent grammar, LF normalization, ATX heading
stacks, duplicate-path `~N` suffixes, heading/paragraph/list-item/fence records, `_root`,
unterminated-fence refusal, and exact repository selected-section closure/deduping.
For `structured-objects-v1`, cover sorted mapping keys, ID-sorted mapping list elements, and refusal
of scalar roots, positional list identity, and duplicate normalized keys/IDs.

- [ ] **Step 2: Write normalization and derived-ID tests**

Cover Unicode whitespace collapse, end trimming, predicate-authorized case folding only, set-like
sorting, ordered-list preservation, original display retention, proposed-ID/order/grouping
independence, whitespace equivalence, paraphrase non-equivalence, and exact occurrence pair
uniqueness. Pin full lowercase SHA256 IDs over canonical JSON arrays exactly:
`["source-record", source_id, normalized_locator]` and
`["candidate", source_record_id, predicate, canonicalized_typed_value]`.

- [ ] **Step 3: Write ledger arithmetic and exclusion tests**

Assert the `approved_scope` discriminant is `{kind: complete_file}` for the first three source kinds
and `{kind: selected_sections, locators: [...]}` for repository Markdown; scope widening changes the
owner-approval target. Assert per-source lists exactly match ledger records in adapter order; every
record appears once; imported records have candidates; excluded records have one rationale and
matching exclusion; every reason works; `owner_excluded` is approval-gated; `review_required` is a
blocker; and imported/excluded/review counts sum to the denominator.

- [ ] **Step 4: Run tests and verify they fail**

Run: `uv run pytest tests/profile_bundle/test_profile_bundle_source_enumeration.py tests/profile_bundle/test_profile_bundle_import_idempotency.py -q`

Expected: FAIL because enumerators/import merge are absent.

- [ ] **Step 5: Implement only deterministic adapters and import validation**

The importer assigns IDs and ignores any LLM-proposed IDs. It gives candidate extraction an immutable
ledger package and never lets an LLM enumerate records. It never fetches repositories, follows
personal paths, mutates accepted facts/evidence/rulings, or performs Gate B extraction. It accepts
source bytes or a typed candidate package supplied explicitly by a caller. Its Boardwatch résumé
source model is package-local and does not alter or import through the frozen tailor path.

- [ ] **Step 6: Run targeted tests**

Run: `uv run pytest tests/profile_bundle/test_profile_bundle_source_enumeration.py tests/profile_bundle/test_profile_bundle_import_idempotency.py -q`

Expected: PASS.

- [ ] **Step 7: Commit the slice**

```bash
git add src/boardwatch/profile_bundle/enumerators.py src/boardwatch/profile_bundle/imports.py src/boardwatch/profile_bundle/validation/imports.py tests/profile_bundle/test_profile_bundle_source_enumeration.py tests/profile_bundle/test_profile_bundle_import_idempotency.py
git commit -m "feat(profile-bundle): add deterministic source imports"
```

### Task 13: Completeness, digest validation, ancestor traversal, and deterministic reports

**Files:**
- Create: `src/boardwatch/profile_bundle/validation/completeness.py`
- Create: `src/boardwatch/profile_bundle/validation/digest.py`
- Create: `src/boardwatch/profile_bundle/validation/run.py`
- Create: `src/boardwatch/profile_bundle/reports.py`
- Create: `tests/profile_bundle/test_profile_bundle_completeness.py`
- Create: `tests/profile_bundle/test_profile_bundle_digest_validation.py`
- Create: `tests/profile_bundle/test_profile_bundle_reports.py`

**Interfaces:**
- Consumes: every prior validation layer and an explicit `date`.
- Produces:

```python
@dataclass(frozen=True)
class ValidationReport:
    schema_version: int | None
    bundle_digest: Sha256Digest | None
    candidate_digest: Sha256Digest | None
    as_of: date | None
    diagnostics: tuple[Diagnostic, ...]
    counts: ValidationCounts

def validate_bundle(root: Path, *, mode: ValidationMode, completeness: bool, as_of: date | None, deep_history: bool = False) -> OperationOutcome[ValidationReport]: ...
def report_json(report: ValidationReport) -> str: ...
def report_text(report: ValidationReport) -> str: ...
```

- [ ] **Step 1: Write time-purity and completeness tests**

Validate identical bytes under two mocked clocks and assert identical structural output. Pass two explicit `as_of` dates around an expiry and assert only completeness changes. Cover one person, requested-surface contact, entity statuses, imported fact review state, unreviewed evidence, unresolved conflicts, stale facts, metric/surface coverage, source totals, exclusions by reason, and unexplained records.

- [ ] **Step 2: Write digest/ancestor tests**

Cover selected directory/manifest/`COMPLETE`/`CURRENT` agreement; revision/change/ledger-length agreement; final entry fields; draft sentinel; inverse candidate digest; three intact revisions; normal selected-only recomputation; stored-envelope ancestor traversal; missing/unreadable/unsupported ancestors as `unverifiable_ancestor` blockers; optional deep audit for supported intact ancestors; and mutated selected bytes as errors.

- [ ] **Step 3: Write deterministic human/JSON report tests**

Pin schema, `outcome`, `exit_code`, `as_of`, counts, sorted diagnostic objects, and privacy-safe messages. JSON uses sorted keys and compact separators plus one trailing newline. Human output may use Rich but must derive from the same report model.

- [ ] **Step 4: Run tests and verify they fail**

Run: `uv run pytest tests/profile_bundle/test_profile_bundle_completeness.py tests/profile_bundle/test_profile_bundle_digest_validation.py tests/profile_bundle/test_profile_bundle_reports.py -q`

Expected: FAIL because orchestration/reporting are absent.

- [ ] **Step 5: Implement layered orchestration**

Run structural → referential → recorded-ruleset evidence → semantic → history/import → digest. Run general completeness plus stronger-installed-ruleset evidence completeness only when structural inputs are usable and only with non-null `as_of`. A valid bundle with blockers remains structurally valid; requested completeness exits 1 when blockers exist.

- [ ] **Step 6: Run targeted tests**

Run: `uv run pytest tests/profile_bundle/test_profile_bundle_completeness.py tests/profile_bundle/test_profile_bundle_digest_validation.py tests/profile_bundle/test_profile_bundle_reports.py -q`

Expected: PASS.

- [ ] **Step 7: Commit the slice**

```bash
git add src/boardwatch/profile_bundle/validation src/boardwatch/profile_bundle/reports.py tests/profile_bundle/test_profile_bundle_completeness.py tests/profile_bundle/test_profile_bundle_digest_validation.py tests/profile_bundle/test_profile_bundle_reports.py
git commit -m "feat(profile-bundle): add completeness digest and report layers"
```

### Task 14: One-read storage, init, checkout, inspect, conflicts, and inventory

**Files:**
- Create: `src/boardwatch/profile_bundle/storage.py`
- Create: `src/boardwatch/profile_bundle/drafts.py`
- Create: `src/boardwatch/profile_bundle/inspection.py`
- Create: `tests/profile_bundle/test_profile_bundle_storage.py`
- Create: `tests/profile_bundle/test_profile_bundle_drafts.py`
- Create: `tests/profile_bundle/test_profile_bundle_inspection.py`

**Interfaces:**
- Consumes: paths, layout, models, validation/report APIs.
- Produces:

```python
class CurrentPointer(StrictModel):
    revision: PositiveInt
    bundle_digest: Sha256Digest

def read_current_once(bundle_root: Path) -> SelectedRevision: ...
def init_draft(bundle_root: Path, *, name: str) -> DraftHandle: ...
def checkout_current(bundle_root: Path, *, name: str) -> DraftHandle: ...
def inspect_record(bundle_root: Path, record_id: RecordId) -> InspectReport: ...
def conflicts_report(bundle_root: Path) -> ConflictsReport: ...
def inventory(bundle_root: Path) -> InventoryReport: ...
```

`CURRENT` is canonical JSON containing exactly `revision` and `bundle_digest`, written with one trailing newline. `COMPLETE` is exactly the full digest plus one newline. Readers read and parse `CURRENT` once, resolve the digest-named immutable directory, require `COMPLETE`, and never reread the pointer during the operation.

- [ ] **Step 1: Write init/checkout tests**

Pin empty revision-1 draft fields (`draft_of_revision: null`, parent null, promotion sentinels), refusal when `CURRENT` already exists for `init`, named draft collision, checkout copy from valid selected revision, corrupt/missing-blob recovery checkout, no reads from other drafts, and no writes to revisions.

- [ ] **Step 2: Write inventory/inspect/conflicts tests**

Report selected revision, drafts, external approval stamps, unreferenced blobs, incomplete temp directories, complete-but-unselected digest directories, corrupt selected state, optional `local-sources.yaml` parse/reference findings, and records/conflicts by stable ID. Assert no command adopts or deletes anything.

- [ ] **Step 3: Write one-read concurrency characterization**

Monkeypatch the pointer reader to return different values on a second call and assert each public read operation calls it exactly once. A selected operation must return one coherent immutable root.

- [ ] **Step 4: Run tests and verify they fail**

Run: `uv run pytest tests/profile_bundle/test_profile_bundle_storage.py tests/profile_bundle/test_profile_bundle_drafts.py tests/profile_bundle/test_profile_bundle_inspection.py -q`

Expected: FAIL because storage/draft/inspection services are absent.

- [ ] **Step 5: Implement read-only selection and draft copying**

Use no shared reader lock. The bundle-root grammar permits exactly `CURRENT`, `career-profile.lock`, `local-sources.yaml`, `approvals/`, `revisions/`, `drafts/`, and `blobs/`; lockfile persistence is normal. Reject symlinks and undeclared root/revision files. `init` writes an empty private `local-sources.yaml`; checkout never copies it into a draft. `checkout` copies source YAML even when a referenced blob is corrupt/missing, but reports the quarantine and preserves the parent digest.

- [ ] **Step 6: Run targeted tests**

Run: `uv run pytest tests/profile_bundle/test_profile_bundle_storage.py tests/profile_bundle/test_profile_bundle_drafts.py tests/profile_bundle/test_profile_bundle_inspection.py -q`

Expected: PASS.

- [ ] **Step 7: Commit the slice**

```bash
git add src/boardwatch/profile_bundle/storage.py src/boardwatch/profile_bundle/drafts.py src/boardwatch/profile_bundle/inspection.py tests/profile_bundle/test_profile_bundle_storage.py tests/profile_bundle/test_profile_bundle_drafts.py tests/profile_bundle/test_profile_bundle_inspection.py
git commit -m "feat(profile-bundle): add immutable reads and draft checkout"
```

### Task 15: Record-level draft rebase and deterministic backup drain

**Files:**
- Create: `src/boardwatch/profile_bundle/diff.py`
- Create: `src/boardwatch/profile_bundle/rebase.py`
- Create: `tests/profile_bundle/test_profile_bundle_rebase.py`

**Interfaces:**
- Consumes: current/old-parent/draft document trees, canonical record identity, `FileLock`.
- Produces:

```python
@dataclass(frozen=True)
class RecordDiff:
    added: frozenset[RecordId]
    removed: frozenset[RecordId]
    changed: frozenset[RecordId]

def diff_records(base: BundleDocuments, changed: BundleDocuments) -> RecordDiff: ...
def rebase_draft(bundle_root: Path, *, name: str) -> OperationOutcome[DraftHandle]: ...
```

- [ ] **Step 1: Write disjoint/overlap tests**

Pin disjoint successful three-way application onto `CURRENT`, exact conflicting record IDs for overlap, parentless `root` token, full old-parent digest token, stale approval retention, and candidate-digest invalidation.

- [ ] **Step 2: Write backup atomicity tests**

The backup is `drafts/<name>.pre-rebase-sha256-<64-hex>/` or `.pre-rebase-root/`. Exact byte-identical existing backup is reusable; any difference returns `draft_backup_conflict`/exit 1 with no writes. Inject failures before backup rename, after backup rename, and before rebased install; assert the original or exact backup remains recoverable and no mixed draft is installed.

- [ ] **Step 3: Write lock behavior tests**

Assert non-blocking contention returns `bundle_lock_held`/exit 3, no wait, and no mutation. Kill a subprocess holding the lock; the next rebase succeeds even though `career-profile.lock` still exists.

- [ ] **Step 4: Run tests and verify they fail**

Run: `uv run pytest tests/profile_bundle/test_profile_bundle_rebase.py -q`

Expected: FAIL because diff/rebase are absent.

- [ ] **Step 5: Implement rebase with same-filesystem temporaries**

Acquire the lock before rereading `CURRENT`; compare touched record IDs, not file paths; validate the rebased draft before install; never modify/delete approval stamps; never auto-resolve a record conflict.

- [ ] **Step 6: Run targeted tests**

Run: `uv run pytest tests/profile_bundle/test_profile_bundle_rebase.py -q`

Expected: PASS.

- [ ] **Step 7: Commit the slice**

```bash
git add src/boardwatch/profile_bundle/diff.py src/boardwatch/profile_bundle/rebase.py tests/profile_bundle/test_profile_bundle_rebase.py
git commit -m "feat(profile-bundle): add conflict-safe draft rebase"
```

### Task 16: Crash-consistent promotion, exact-target reuse, and corrupt-parent recovery

**Files:**
- Create: `src/boardwatch/profile_bundle/promotion.py`
- Create: `tests/profile_bundle/test_profile_bundle_promotion.py`
- Create: `tests/profile_bundle/test_profile_bundle_promotion_crashes.py`
- Create: `tests/profile_bundle/test_profile_bundle_promotion_concurrency.py`
- Create: `tests/profile_bundle/test_profile_bundle_recovery.py`

**Interfaces:**
- Consumes: all validation, approval, storage, diff, canonical, and lock APIs.
- Produces:

```python
@dataclass(frozen=True)
class PromotionRequest:
    draft_name: str
    summary: str
    actor: Literal["owner", "agent", "importer"]
    created_at: datetime

def promote(bundle_root: Path, request: PromotionRequest) -> OperationOutcome[SelectedRevision]: ...
```

- [ ] **Step 1: Write normal promotion derivation tests**

Pin non-blocking lock before mutation, parent recheck, contiguous revision, stable profile ID, derived change ID/timestamp/actor/changed IDs, exactly one approval/change append, exact prefix checks, evidence/bundle/candidate digests, full digest directory name, `COMPLETE` last, from-disk validation, and atomic `CURRENT` replace.

- [ ] **Step 2: Write target reuse/conflict tests**

An existing exact complete target with identical logical tree/directory/marker/manifest is reused. A missing marker, directory/digest mismatch, manifest mismatch, or byte/content mismatch returns `promotion_target_conflict`/exit 3, retains both directories, and leaves `CURRENT` unchanged.

- [ ] **Step 3: Write crash matrix tests at every mutation boundary**

Inject process termination or raised failure after lock, parent check, temp creation, each document write, temp reread, `COMPLETE`, final rename, temporary `CURRENT` write/flush/close, and immediately before/after `os.replace`. Before pointer replacement the old selection remains; after replacement readers see the complete new selection. Inventory reports leftovers.

- [ ] **Step 4: Write concurrent promoter/reader and process-death lock tests**

Two subprocess promoters from the same parent yield exactly one winner; the loser receives lock or stale-parent refusal with intact draft. Repeated lock-free readers observe either the complete old or complete new tree. Kill the lock holder and prove the persistent lockfile is not treated as held.

- [ ] **Step 5: Write recovery exception tests**

For a parent with missing or corrupt referenced blob but parseable source/manifest and exact ledgers, checkout, recapture to a new digest, approve, and promote a fully valid replacement. Parent YAML corruption, unsupported parent schema, manifest/directory disagreement, or any changed ledger prefix still blocks. The new selected revision validates structurally and reports `unverifiable_ancestor` completeness for the broken parent.

- [ ] **Step 6: Run tests and verify they fail**

Run: `uv run pytest tests/profile_bundle/test_profile_bundle_promotion.py tests/profile_bundle/test_profile_bundle_promotion_crashes.py tests/profile_bundle/test_profile_bundle_promotion_concurrency.py tests/profile_bundle/test_profile_bundle_recovery.py -q`

Expected: FAIL because promotion is absent.

- [ ] **Step 7: Implement the nine-step promotion protocol literally**

Write same-filesystem temp directories; flush each file, close it, reread the full temp tree, write and flush `COMPLETE` last, then rename. Write/flush/close a temporary `CURRENT` and use `os.replace`. Do not claim directory fsync or power-loss guarantees beyond the approved process-crash contract.

- [ ] **Step 8: Run targeted tests**

Run: `uv run pytest tests/profile_bundle/test_profile_bundle_promotion.py tests/profile_bundle/test_profile_bundle_promotion_crashes.py tests/profile_bundle/test_profile_bundle_promotion_concurrency.py tests/profile_bundle/test_profile_bundle_recovery.py -q`

Expected: PASS.

- [ ] **Step 9: Commit the slice**

```bash
git add src/boardwatch/profile_bundle/promotion.py tests/profile_bundle/test_profile_bundle_promotion.py tests/profile_bundle/test_profile_bundle_promotion_crashes.py tests/profile_bundle/test_profile_bundle_promotion_concurrency.py tests/profile_bundle/test_profile_bundle_recovery.py
git commit -m "feat(profile-bundle): promote revisions crash consistently"
```

### Task 17: Bundle schema-v1 bootstrap and migration no-op

**Files:**
- Create: `src/boardwatch/profile_bundle/migrations.py`
- Create: `tests/profile_bundle/test_profile_bundle_schema_head.py`
- Create: `tests/profile_bundle/test_profile_bundle_schema_migration.py`

**Interfaces:**
- Consumes: the schema-v1 bootstrap contract and draft/approval/promotion pipeline.
- Produces:

```python
CURRENT_SCHEMA_VERSION = 1
SUPPORTED_SCHEMA_VERSIONS: frozenset[int]

class SchemaMigration(Protocol):
    from_version: int
    to_version: int
    def transform(self, documents: Mapping[PurePosixPath, object]) -> Mapping[PurePosixPath, object]: ...

def migrate_bundle(bundle_root: Path, *, draft_name: str = "schema-migration") -> OperationOutcome[DraftHandle]: ...
```

- [ ] **Step 1: Write pinned-head and newer-schema refusal tests**

Assert head `1`, exact supported set `{1}`, typed `unsupported_schema_version`/exit 3 for newer
bundles, no generic enum error, and no v0 registry entry or fixture.

- [ ] **Step 2: Write approved compatibility/migration tests**

On a v1 bundle, assert `migrate_bundle` returns `already_current`, creates no draft, revision, or
change, does not alter `CURRENT` or any byte under the bundle root, and remains idempotent. Add an
explicit assertion documenting that the previous-schema fixture and `1 -> 2` migration become
mandatory only when schema v2 is designed; do not create placeholder v0 data.

- [ ] **Step 3: Run tests and verify they fail**

Run: `uv run pytest tests/profile_bundle/test_profile_bundle_schema_head.py tests/profile_bundle/test_profile_bundle_schema_migration.py -q`

Expected: FAIL because migration support is absent.

- [ ] **Step 4: Implement the schema-v1 bootstrap policy**

Register no migration at schema v1. Return `already_current` without acquiring a promotion lock or
writing when the selected revision is v1. Preserve the extension point so a future `1 -> 2`
migration can write a draft and use the same owner approval/promotion path without rewriting an
existing revision. Adding/changing a code-defined enum requires a schema bump; catalog row additions
change their catalog version and bundle digest only.

- [ ] **Step 5: Run targeted tests**

Run: `uv run pytest tests/profile_bundle/test_profile_bundle_schema_head.py tests/profile_bundle/test_profile_bundle_schema_migration.py -q`

Expected: PASS.

- [ ] **Step 6: Commit the slice**

```bash
git add src/boardwatch/profile_bundle/migrations.py tests/profile_bundle/test_profile_bundle_schema_head.py tests/profile_bundle/test_profile_bundle_schema_migration.py
git commit -m "feat(profile-bundle): pin schema v1 bootstrap behavior"
```

### Task 18: Complete `profile-bundle` CLI, TTY approval, JSON outcomes, evidence and conflict authoring

**Files:**
- Create: `src/boardwatch/cli/profile_bundle_cmd.py`
- Modify: `src/boardwatch/cli/app.py`
- Create: `tests/profile_bundle/test_profile_bundle_cli.py`
- Create: `tests/profile_bundle/test_profile_bundle_cli_approval.py`
- Create: `tests/profile_bundle/test_profile_bundle_cli_exit_codes.py`

**Interfaces:**
- Consumes: public library APIs from Tasks 1–17 and `load_settings(data_dir=ctx.obj)`/`settings.config_dir`.
- Produces exactly these commands:

```text
boardwatch profile-bundle init [--bundle PATH] [--draft NAME]
boardwatch profile-bundle checkout [--bundle PATH] [--draft NAME]
boardwatch profile-bundle rebase-draft --draft NAME [--bundle PATH]
boardwatch profile-bundle validate [--bundle PATH] [--draft NAME] [--completeness] [--as-of YYYY-MM-DD] [--deep-history] [--json]
boardwatch profile-bundle inspect RECORD_ID [--bundle PATH] [--json]
boardwatch profile-bundle inventory [--bundle PATH] [--json]
boardwatch profile-bundle conflicts [--bundle PATH] [--json]
boardwatch profile-bundle add-evidence --draft NAME --evidence-file PATH --capture PATH [--bundle PATH]
boardwatch profile-bundle resolve-conflict --draft NAME --ruling-file PATH [--bundle PATH]
boardwatch profile-bundle approve --draft NAME [--bundle PATH]
boardwatch profile-bundle promote --draft NAME --summary TEXT [--actor owner|agent|importer] [--bundle PATH]
boardwatch profile-bundle migrate [--bundle PATH] [--draft NAME]
```

`add-evidence` reads one strict `EvidenceRecord` YAML file plus capture bytes, scans/captures the blob or normalizes inline content according to the record's discriminant, updates only the named draft's `evidence/records.yaml`, and revalidates. `resolve-conflict` reads one strict `RulingRecord`, appends it to the named draft, updates only the matching conflict's active state, and reports the required `authorize_conflict_ruling` owner gate. Neither command approves or promotes.

- [ ] **Step 1: Write command registration/default-path/no-database tests**

Assert help lists every command; default/override paths work; every command except explicitly requested mutation leaves `boardwatch.db` absent in a pristine `--data-dir`; and CLI imports no store module.

- [ ] **Step 2: Write approval TTY tests**

Refuse when stdin or stdout is not a controlling TTY; no `--yes` exists; environment and piped confirmation cannot bypass. On a controlling TTY, show candidate digest plus sorted owner-gated decisions, require exact interactive confirmation, call pure `build_approval_stamp`, and atomically write `approvals/sha256-<candidate>.yaml`. Tests patch only the TTY/confirmation adapter and use synthetic typed decisions; production has no alternative approval entry point.

- [ ] **Step 3: Write exit/JSON matrix tests**

Characterize clean `0`, findings/state refusal `1`, Typer usage `2` before execution, and I/O/lock/internal/unsupported `3`, in human and JSON modes. JSON always includes `outcome`, `exit_code`, `diagnostics`, command-specific `result`, and explicit `as_of` for completeness.

- [ ] **Step 4: Write authoring command tests**

Cover inline/blob evidence, secret hit/no partial draft write, idempotent blob reuse, ruling append, conflict state update, required owner-gate report, stale approval after edit, stale parent, rebase drains, exact promotion result, and migrate behavior from Task 17.

- [ ] **Step 5: Run tests and verify they fail**

Run: `uv run pytest tests/profile_bundle/test_profile_bundle_cli.py tests/profile_bundle/test_profile_bundle_cli_approval.py tests/profile_bundle/test_profile_bundle_cli_exit_codes.py -q`

Expected: FAIL because the sub-app is absent.

- [ ] **Step 6: Implement thin CLI translation**

Load settings with `ensure=False` behavior by calling `load_settings` directly; do not construct a SQLAlchemy engine. Catch only typed library errors at the boundary; unexpected exceptions become privacy-safe `could_not_complete` JSON/human outcomes without traceback content unless the existing global CLI debug policy explicitly requests it.

- [ ] **Step 7: Run targeted tests**

Run: `uv run pytest tests/profile_bundle/test_profile_bundle_cli.py tests/profile_bundle/test_profile_bundle_cli_approval.py tests/profile_bundle/test_profile_bundle_cli_exit_codes.py -q`

Expected: PASS.

- [ ] **Step 8: Commit the slice**

```bash
git add src/boardwatch/cli/profile_bundle_cmd.py src/boardwatch/cli/app.py tests/profile_bundle/test_profile_bundle_cli.py tests/profile_bundle/test_profile_bundle_cli_approval.py tests/profile_bundle/test_profile_bundle_cli_exit_codes.py
git commit -m "feat(cli): expose profile bundle lifecycle"
```

### Task 19: Authoring contract, tailor isolation, generalization/wheel audit, and final gate

**Files:**
- Create: `docs/profile-bundle-authoring.md`
- Modify: `docs/configuration.md`
- Modify: `README.md`
- Modify: `tools/generalization/allowlists.py`
- Modify: `tests/generalization/test_inventory.py`
- Modify: `tests/generalization/test_packaging.py`
- Create: `tests/profile_bundle/test_profile_bundle_tailor_isolation.py`
- Modify only after implementation/review evidence exists: `CHANGELOG.md`
- Modify only after implementation/review evidence exists: `docs/program/STATE.md`
- Modify only after implementation/review evidence exists: `docs/program/METRICS.md`
- Modify only for a durable architectural decision or owner ruling: `docs/program/DECISIONS.md`

**Interfaces:**
- Consumes: complete Gate A behavior and real test output.
- Produces a concise authoring contract, installation/resource proof, unchanged tailor proof, generalization inventory, and final program evidence.

- [ ] **Step 1: Write the tailor-boundary and package-content tests**

```python
def test_tailor_default_path_remains_resume_yaml(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data", config_dir=tmp_path / "cfg")
    assert _resume_path(settings) == settings.config_dir / "resume.yaml"

def test_tailor_import_graph_has_no_profile_bundle_bridge() -> None:
    forbidden = "boardwatch.profile_bundle"
    for path in TAILOR_PRODUCTION_FILES:
        assert forbidden not in path.read_text(encoding="utf-8")
```

Also assert the frozen `Resume` model and current tailoring tests operate without a bundle directory.

- [ ] **Step 2: Write the authoring and recovery guide**

Document closed tree/files, strict scalar quoting, stable IDs, root-only `local-sources.yaml` and its exclusion from revisions/digests/exports, direct-draft editing, evidence/media/size/redaction rules, validation tiers, `--as-of`, candidate versus bundle digest, owner approval stop, stale stamp behavior, conflict/import rules, checkout/rebase/promotion, corrupt-blob restore/recapture, inventory-only orphan handling, schema migration, JSON/exit contracts, default/override paths, and the explicit Gate A/Gate B/later-gates boundary. Examples remain synthetic.

- [ ] **Step 3: Finish generalization inventory and non-vacuity assertions**

Verify every new YAML/JSON path has a nonblank reason, synthetic/first-party provenance, and a correct SHA-256 pin; no broad exemption or new unpinned path is added. Update inventory count only to the observed exact total. Add package test assertions for JSON Schema and at least `manifest.yaml`, `policy/predicates.yaml`, and `application/gated-facts.yaml` from the example.

- [ ] **Step 4: Run focused boundary and packaging checks**

Run: `uv run pytest tests/profile_bundle/test_profile_bundle_tailor_isolation.py tests/unit/test_tailor_cmd.py tests/unit/test_tailor_load.py tests/generalization/test_real_tree.py tests/generalization/test_inventory.py tests/generalization/test_packaging.py -q`

Expected: PASS.

Run: `uv run python -m tools.generalization`

Expected: `generalization: OK`, exit 0.

- [ ] **Step 5: Run every profile-bundle test as one subsystem gate**

Run: `uv run pytest tests/profile_bundle -q`

Expected: PASS with no deselected Gate A test and no duplicate module basename collection error.

- [ ] **Step 6: Run the authoritative repository gate unpiped**

Run: `make check`

Expected: exit 0 from generalization, program-index check, Ruff, strict mypy, and pytest. Capture the complete command's real exit code; do not pipe through `head` or `tail`.

- [ ] **Step 7: Record only verified evidence**

After the implementation and required review are complete, update `CHANGELOG.md`, rewrite current standing in `STATE.md`, add measured counts/digests/test output to `METRICS.md`, append any owner rulings/architecture changes to `DECISIONS.md`, add index rows, run `make reindex`, then rerun `make check` because program-doc line indexes changed.

- [ ] **Step 8: Commit the documentation/evidence slice**

```bash
git add docs/profile-bundle-authoring.md docs/configuration.md README.md tools/generalization/allowlists.py tests/generalization tests/profile_bundle/test_profile_bundle_tailor_isolation.py CHANGELOG.md docs/program/STATE.md docs/program/METRICS.md docs/program/DECISIONS.md
git commit -m "docs(profile-bundle): document Gate A and record verification"
```

Omit any program file that did not require a truthful change; never add a no-op evidence edit.

---

## Dependency-ordered slice sequence

1. Dependency/path/outcome boundary.
2. Restricted YAML and closed file grammar.
3. Entity/fact/relation/skill models.
4. Policy/evidence/metric/claim models with the closed v1 catalogs.
5. Manifest/history/import/document models and JSON Schema.
6. Comprehensive synthetic packaged example and generalization admission.
7. Canonical, evidence, bundle, candidate, and target digests plus hash isolation.
8. Aggregate loading, indexing, structural and referential validation.
9. Blob capture, secret-scan versioning, evidence validation, and recovery primitives.
10. Predicate/state/surface/metric/skill/assertion/claim semantic validation.
11. Owner-gate derivation, pure stamps, conflicts, and append-only ledgers.
12. Deterministic enumeration and idempotent imports using the three closed v1 adapters.
13. Completeness, digest/ancestor validation, and deterministic reports.
14. Immutable selected reads, init/checkout, inspection, conflicts, and inventory.
15. Disjoint record-level rebase and deterministic backup drain.
16. Crash-consistent promotion, target reuse/conflict, concurrency, and corrupt-parent recovery.
17. Schema-v1 head/support and no-write `already_current` migration behavior.
18. Full Typer/JSON/TTY command surface.
19. Authoring docs, tailor isolation, generalization/wheel proof, subsystem tests, and unpiped `make check`.

## Design coverage review

| Approved design requirement | Planned proof |
|---|---|
| Private location and no `Settings`/policy-version change | Tasks 1, 18, 19 |
| Root-only local source map excluded from revision identity/export | Tasks 5, 7, 14, 19 |
| Closed physical/logical organization and unknown-file refusal | Tasks 2, 6, 8 |
| Canonical/evidence/candidate/target digests and inverse normalization | Task 7; digest checks in Task 13 |
| Typed IDs, entities, contacts, facts, relations, values, states, surfaces | Tasks 3, 8, 10 |
| Predicate/unit/relation/source/skill/assertion/secret catalogs | Tasks 4, 6, 9, 10; exact v1 rows are pinned from the live design |
| Metrics, evidence, redaction, media/byte budgets, secret scanning | Tasks 4, 9, 10 |
| Conflicts, rulings, one stamp, all owner-gated transitions | Task 11; production TTY in Task 18 |
| Skills and approved claim candidates without runtime generation | Tasks 3, 4, 10 |
| Application-only facts and non-widening | Tasks 4, 10 |
| History, exact prefixes, revision-length equality, derived changed IDs | Tasks 11, 16 |
| Deterministic denominator, candidates, occurrences, exclusions, import idempotency | Task 12; exact adapters, locators, scopes, and full SHA256 IDs are pinned |
| Draft authoring, init, checkout, validate, inspect, inventory, conflicts | Tasks 13, 14, 18 |
| Non-blocking lock, stale parent, rebase, exact backup, stamp invalidation | Task 15 |
| Promotion temp tree, `COMPLETE`, exact target reuse, atomic `CURRENT` | Task 16 |
| Torn promotion, concurrent writers/readers, lock process death | Task 16 |
| Corrupt-parent recapture exception and `unverifiable_ancestor` | Tasks 9, 13, 14, 16 |
| Schema-v1 bootstrap and future N−1 activation | Task 17; supports exactly `{1}`, performs no-write `already_current`, and forbids fabricated v0 |
| Human/JSON output and 0/1/2/3 outcomes | Tasks 1, 13, 18 |
| JSON Schema, authoring contract, synthetic complete example | Tasks 5, 6, 19 |
| Generalization inventory and wheel contents | Tasks 5, 6, 19 |
| Existing tailor remains on `resume.yaml`; no bundle bridge | Task 19 |
| Gate B/private content and all projection/tailoring evaluation excluded | Global constraints and Task 19 documentation |
| Final authoritative verification | Task 19 unpiped `make check` |

## Plan-only consistency review performed 2026-08-10

- **Spec coverage:** Every Gate A criterion and every required test group in design §22 maps to at least one task above. Gate B and later projection gates map to no implementation task.
- **Live repo fit:** The plan uses the existing Typer registration pattern, call-boundary config path, Pydantic 2, `filelock`, uv/Hatch package data, generalization inventory, and unpiped `make check`. It adds no store table or Alembic migration.
- **Type consistency:** Public types are introduced before consumers: outcomes/paths → parsed models → documents/schema → canonical identities → index/validation → approvals/imports/reports → storage/rebase/promotion/migration → CLI.
- **Recovery consistency:** Promotion validates current parent source/manifest/ledger prefixes; only the design's broken-parent blob/completeness checks may be waived. No lockfile-breaking, adoption, cleanup, or deletion path was introduced.
- **Owner-gate consistency:** Library stamp construction is pure; only the production CLI owns TTY interaction; agents stop before owner approval; edits/rebase invalidate stamps by candidate-digest mismatch.
- **Boundary consistency:** No bundle-to-`Resume` conversion, persona/role-family selection, JD taxonomy mapping, rendering, representative-JD evaluation, or tailoring-quality work appears in any task.
- **Blocker closure:** The live design now fixes the schema-v1 bootstrap exception, exact v1 unit,
  assertion-tag, and secret-scan contracts, and exact source adapter/scope/locator/ID contracts. The
  corresponding tasks contain no execution preconditions.
- **Placeholder scan:** The plan contains no hidden implementation placeholders or unresolved design
  choices. Ellipses in interface sketches denote typed model bodies whose exact fields are fully
  specified by the design and the associated exhaustive shape tests, not deferred requirements.

## Verification strategy

Each slice follows red/green targeted tests and ends with an independently reviewable commit. Cross-cutting tests deliberately separate parse/structure, references, evidence, semantics, completeness, digest/history, filesystem crash consistency, CLI translation, and repository privacy/packaging. Task 19 then runs the entire `tests/profile_bundle` suite, targeted tailor-isolation regressions, the real generalization tool, wheel checks, and finally unpiped `make check` with the real exit code.

## Stop boundary

This planning session authorizes no implementation. Start Gate A in a separate execution session and
follow the 19 slices in order. Gate B remains prohibited until Gate A is both implemented and reviewed.
