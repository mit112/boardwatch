# Projection in the daily pipeline (slice P5a) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `boardwatch run --project` render each lead from the career-profile bundle's projected résumé instead of the static authored `resume.yaml`, with lineage recorded and no lead consumed when projection is unavailable.

**Architecture:** One configuration snapshot is resolved per run (`resolve_projection_run`) and reused for every lead (`project_for_posting`), so a run can never mix taxonomies or bundle revisions. A run-level preflight decides availability once; anything but `available` sets `summary.fatal` and exits 1 *before* any lead earns a ledger disposition, which is what makes re-approval a real drain. Each projected lead carries document *and* transformation lineage into its artifact row, and projection gets its own balanced funnel stage.

**Tech Stack:** Python 3.11+, SQLAlchemy Core, Pydantic v2, Typer, pytest, tectonic (LaTeX), `filelock`.

**Spec:** `docs/superpowers/specs/2026-08-17-projection-pipeline-integration-design.md` (revision 3). Its two external review rounds are in `...-review-gpt56sol.md` and `...-review-gpt56sol-r2.md`. **Read the spec — this plan argues from it and does not restate its reasoning.**

## Global Constraints

- **`make check` is the only gate.** Run it in plain mode, capture the real exit code, never pipe through `head`/`tail` (SIGPIPE gives a false negative). Expect 4½–35 minutes.
- **Narrow pytest runs need `--no-cov -n 0`** — `addopts` carries `--cov-fail-under=85`, so a subset run fails on coverage without it.
- **`resume.yaml` stays the unattended default.** Without `--project`, behaviour must be byte-identical to today. This is a hard invariant, not a preference.
- **No non-TTY approval path, ever.** The pipeline never writes a `ProjectionStamp`.
- **Typed violations at the raise site.** Never classify behaviour by string-matching an exception message.
- **Closed catalogs.** An out-of-catalog value is a failure, never a new bucket.
- **The import wall:** `boardwatch/tailor/**` plus `cli/tailor_cmd.py` must not transitively reach `boardwatch.profile_bundle` (`tests/profile_bundle/test_profile_bundle_tailor_isolation.py`). `reports.tailor` is inside that closure, so **any type `reports.tailor` imports must not reach `profile_bundle`** — this is why the lineage type lives in `boardwatch/core/`, which is verified neutral.
- **Surgical diffs.** Every changed line traces to this plan. Do not reformat adjacent code.
- **Program docs:** append to `docs/program/DECISIONS.md`, add its index row, then run `make reindex` (`make check` fails on a stale index). Do not rewrite `STATE.md`/`METRICS.md` wholesale — a concurrent session may be appending.
- **No AI attribution** in commits, branches, or PRs.
- Existing values you must not re-derive: `ARTIFACT_VERSION = 4` (`reports/run_funnel.py:69`), `MANIFEST_SCHEMA_VERSION = 1` (`projection/manifest.py`), 32 members in `ProjectionIssue` (`projection/errors.py`).

---

### Task 1: A typed `DECLARATION_MISSING` issue

Today an absent `projection.yaml` and an unreadable one both raise `DECLARATION_UNREADABLE` (`projection/declaration.py:134` and `:150`). The availability catalog must distinguish them, and doing it by message is forbidden.

**Files:**
- Modify: `src/boardwatch/projection/errors.py` (add the enum member)
- Modify: `src/boardwatch/projection/declaration.py:134` (the missing-file branch only)
- Test: `tests/projection/test_projection_declaration.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `ProjectionIssue.DECLARATION_MISSING`.

- [ ] **Step 1: Write the failing test**

```python
def test_an_absent_declaration_is_missing_not_unreadable(tmp_path: Path) -> None:
    """The two arms are different operator problems: 'you have not opted in' vs 'your file is
    broken'. Task 4's availability catalog routes them differently and may not read a message."""
    absent = tmp_path / "projection.yaml"
    with pytest.raises(ProjectionError) as exc:
        load_declaration(absent)
    assert exc.value.issue is ProjectionIssue.DECLARATION_MISSING


def test_an_unreadable_declaration_stays_unreadable(tmp_path: Path) -> None:
    bad = tmp_path / "projection.yaml"
    bad.write_bytes(b"\xff\xfe not utf-8")
    with pytest.raises(ProjectionError) as exc:
        load_declaration(bad)
    assert exc.value.issue is ProjectionIssue.DECLARATION_UNREADABLE
```

- [ ] **Step 2: Run the tests to verify the first fails**

Run: `uv run pytest tests/projection/test_projection_declaration.py -k "missing_not_unreadable or stays_unreadable" -v --no-cov -n 0`

Expected: the first FAILS with `AttributeError: DECLARATION_MISSING` (or `assert ... is`), the second PASSES. Confirm the *first* is what trips — a pre-existing failure elsewhere proves nothing.

- [ ] **Step 3: Add the enum member**

In `src/boardwatch/projection/errors.py`, beside `DECLARATION_UNREADABLE`:

```python
    #: `projection.yaml` is absent. Distinct from DECLARATION_UNREADABLE because "you have not
    #: opted into projection" and "your declaration is corrupt" are different operator problems,
    #: and the availability catalog may not tell them apart by inspecting a message.
    DECLARATION_MISSING = "declaration_missing"
```

- [ ] **Step 4: Narrow the missing-file branch**

In `src/boardwatch/projection/declaration.py`, the branch at `:134` that fires when the path does not exist changes its issue to `ProjectionIssue.DECLARATION_MISSING`. **Leave `:150` (the read/decode failure) as `DECLARATION_UNREADABLE`.** Verify with `grep -n DECLARATION_ src/boardwatch/projection/declaration.py` that exactly one site changed.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/projection/test_projection_declaration.py -v --no-cov -n 0`

Expected: PASS, including every pre-existing test in that file. If another test asserted `DECLARATION_UNREADABLE` for an absent file, it is now wrong and must be updated to the new member — that is a legitimate edit, not an accommodation.

- [ ] **Step 6: Commit**

```bash
git add src/boardwatch/projection/errors.py src/boardwatch/projection/declaration.py tests/projection/test_projection_declaration.py
git commit -m "Distinguish an absent projection declaration from an unreadable one"
```

---

### Task 2: `ResumeSourceLineage` in a neutral module

The lineage type must exist before anything produces or consumes it, and its *home* is the constraint: `reports.tailor` will import it, and `reports.tailor` sits inside the tailor import-wall closure, so a type living in `projection/` (which imports `profile_bundle`) would break the wall.

**Files:**
- Create: `src/boardwatch/core/lineage.py`
- Test: `tests/core/test_lineage.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `ResumeSourceLineage` — a frozen dataclass with fields `kind: Literal["projection"]`, `bundle_revision: str`, `bundle_digest: str`, `projection_digest: str`, `posting_version_id: int`, `as_of: str`, `scorer_id: str`, `taxonomy_version: str`, `equivalence_version: str`, `persona_registry_version: str`, `resume_sha256: str`, `resume_model_sha256: str`, `manifest_schema: int`; and `ResumeSourceLineage.as_meta() -> dict[str, str | int]`.

- [ ] **Step 1: Write the failing test**

```python
def test_lineage_round_trips_through_its_meta_form() -> None:
    lineage = ResumeSourceLineage(
        kind="projection",
        bundle_revision="21",
        bundle_digest="sha256:" + "a" * 64,
        projection_digest="sha256:" + "b" * 64,
        posting_version_id=4321,
        as_of="2026-08-17",
        scorer_id="mean_per_bullet",
        taxonomy_version="c" * 64,
        equivalence_version="d" * 64,
        persona_registry_version="e" * 64,
        resume_sha256="f" * 64,
        resume_model_sha256="0" * 64,
        manifest_schema=1,
    )
    meta = lineage.as_meta()
    assert meta["projection_bundle_revision"] == "21"
    assert meta["projection_posting_version_id"] == 4321
    # Every field reaches the artifact row: a lineage field that is silently dropped is the
    # exact "more inspectable, not detected" failure this slice exists to close.
    assert len(meta) == len(dataclasses.fields(lineage))


def test_the_lineage_module_does_not_reach_the_profile_bundle() -> None:
    """`reports.tailor` imports this type and sits inside the tailor import-wall closure, so a
    lineage module that reached `profile_bundle` would break
    `test_no_production_tailor_module_reaches_the_profile_bundle`."""
    source = (Path("src/boardwatch/core/lineage.py")).read_text(encoding="utf-8")
    assert "profile_bundle" not in source
    assert "boardwatch.projection" not in source
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/core/test_lineage.py -v --no-cov -n 0`

Expected: FAIL with `ModuleNotFoundError: boardwatch.core.lineage`.

- [ ] **Step 3: Write the module**

```python
"""One projected résumé's lineage, in a module neither the tailor nor the bundle may not import.

Deliberately in `boardwatch.core`: `reports.tailor` consumes this type, and `reports.tailor` is
inside the closure `tests/profile_bundle/test_profile_bundle_tailor_isolation.py` walks. A type
defined in `boardwatch.projection` would drag `boardwatch.profile_bundle` into that closure and
break the wall. `core` imports neither, and a test above pins that it stays that way.

Two hashes, not one. `resume_sha256` is over the raw projected bytes; `resume_model_sha256` is over
the parsed model, matching the identity `reports/tailor.py` already uses for a master
(`_sha(master.model_dump_json())`). Byte identity catches a swapped file; model identity catches two
different documents that serialise to the same bytes under a different loader version. Neither
subsumes the other.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ResumeSourceLineage:
    """Where a tailored résumé's master came from, when the master was projected rather than
    authored. Every field is part of either document identity or transformation identity; see the
    design's §4.3 for why transformation identity is not optional."""

    kind: Literal["projection"]
    bundle_revision: str
    bundle_digest: str
    projection_digest: str
    posting_version_id: int
    as_of: str
    scorer_id: str
    taxonomy_version: str
    equivalence_version: str
    persona_registry_version: str
    resume_sha256: str
    resume_model_sha256: str
    manifest_schema: int

    def as_meta(self) -> dict[str, str | int]:
        """Flat, prefixed keys for an artifact's `meta_json`. Prefixed because the row already
        carries unprefixed tailoring keys and a bare `as_of` there would be ambiguous."""
        return {
            f"projection_{field.name}": getattr(self, field.name)
            for field in dataclasses.fields(self)
        }
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/core/test_lineage.py -v --no-cov -n 0`

Expected: PASS both.

- [ ] **Step 5: Commit**

```bash
git add src/boardwatch/core/lineage.py tests/core/test_lineage.py
git commit -m "Add the projected-resume lineage type in a neutral module"
```

---

### Task 3: One configuration snapshot per run

This is the fix for round 2's sharpest finding: freezing the pool alone leaves the taxonomy, equivalences and persona registry floating, so selection and tailoring can apply different rules while every digest check passes.

**Files:**
- Create: `src/boardwatch/projection/run.py`
- Modify: `src/boardwatch/projection/posting.py:46` (accept an injected taxonomy)
- Modify: `src/boardwatch/cli/projection_cmd.py:444` (pass the taxonomy it already loads)
- Test: `tests/projection/test_projection_run_context.py`

**Interfaces:**
- Consumes: `project_pool(bundle_root, declaration_path, *, config_dir, as_of) -> ProjectionPool`; `posting_context`; `load_taxonomy(config_dir) -> Taxonomy` (has `.version`); `load_equivalences() -> EquivalenceTable` (has `.version`); `load_personas(config_dir) -> PersonaRegistry` (has `.version`); `SCORERS: Mapping[str, EntryScorer]`.
- Produces:
  - `ProjectionRunContext` — frozen dataclass: `pool: ProjectionPool`, `scorer: EntryScorer`, `scorer_id: str`, `taxonomy: Taxonomy`, `table: EquivalenceTable`, `persona_registry_version: str`, `as_of: date`.
  - `resolve_projection_run(engine, settings, *, bundle_root: Path, declaration_path: Path, scorer_id: str, as_of: date) -> ProjectionRunContext`
  - `posting_context(engine, settings, posting_id, *, taxonomy: Taxonomy) -> PostingContext` (changed signature)

- [ ] **Step 1: Write the failing tests**

```python
def test_the_run_context_loads_the_taxonomy_exactly_once(monkeypatch, tmp_path) -> None:
    """Two postings, one taxonomy load. Counting the CALL is the assertion, not comparing two
    returned objects: two loads of an unchanged file are equal, so equality cannot detect the
    defect this guards."""
    calls: list[Path] = []
    real = taxonomy_mod.load_taxonomy

    def counting(config_dir: Path):
        calls.append(config_dir)
        return real(config_dir)

    monkeypatch.setattr(taxonomy_mod, "load_taxonomy", counting)
    ctx = resolve_projection_run(engine, settings, bundle_root=root,
                                 declaration_path=decl, scorer_id="mean_per_bullet",
                                 as_of=date(2026, 8, 17))
    posting_context(engine, settings, first_id, taxonomy=ctx.taxonomy)
    posting_context(engine, settings, second_id, taxonomy=ctx.taxonomy)
    assert len(calls) == 1


def test_posting_context_uses_the_injected_taxonomy(engine, settings, posting_id) -> None:
    """A taxonomy that extracts nothing must yield no jd_skills, proving the injected object is
    the one used rather than a freshly loaded one."""
    empty = Taxonomy(patterns=(), version="injected", source="test")
    ctx = posting_context(engine, settings, posting_id, taxonomy=empty)
    assert ctx.jd_skills == frozenset()


def test_the_run_context_records_every_transformation_version(...) -> None:
    ctx = resolve_projection_run(...)
    assert ctx.taxonomy.version and ctx.table.version and ctx.persona_registry_version
    assert ctx.scorer_id == "mean_per_bullet"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/projection/test_projection_run_context.py -v --no-cov -n 0`

Expected: FAIL with `ModuleNotFoundError: boardwatch.projection.run`.

- [ ] **Step 3: Change `posting_context` to accept a taxonomy**

In `src/boardwatch/projection/posting.py`, make the taxonomy a required keyword and delete the internal `load_taxonomy` call. Keep `run_preflight(engine, settings)` where it is — it is extraction preflight, not configuration.

```python
def posting_context(
    engine: Engine, settings: Settings, posting_id: int, *, taxonomy: Taxonomy
) -> PostingContext:
    """... (keep the existing docstring, and add:)

    The taxonomy is injected rather than loaded here so that one run scores every posting under
    one taxonomy. Loading it per call let JD extraction for posting 2 run under a taxonomy that
    selection was not using — a stale *transformation*, invisible to every digest check.
    """
    run_preflight(engine, settings)
```

Update the sole production caller, `src/boardwatch/cli/projection_cmd.py:444`, to pass the taxonomy it already loads at `:453`. **Move that `load_taxonomy` call above the `posting_context` call** so one object serves both.

- [ ] **Step 4: Write `resolve_projection_run`**

```python
@dataclass(frozen=True)
class ProjectionRunContext:
    """Every input that decides what a projected résumé says, resolved once per run.

    The pool alone is not enough. `select` scores through the taxonomy and equivalence table, and
    `apply_persona` reads the registry, so a run holding one pool and reloading the rest can still
    produce two leads built under different rules.
    """

    pool: ProjectionPool
    scorer: EntryScorer
    scorer_id: str
    taxonomy: Taxonomy
    table: EquivalenceTable
    persona_registry_version: str
    as_of: date


def resolve_projection_run(
    engine: Engine,
    settings: Settings,
    *,
    bundle_root: Path,
    declaration_path: Path,
    scorer_id: str,
    as_of: date,
) -> ProjectionRunContext:
    """Resolve one run's projection configuration, or raise.

    Raises `ProjectionError` / `ProfileBundleError` / `PersonaError` / `TaxonomyError` /
    `EquivalenceError`; Task 4 maps every one of those to an availability member. Nothing is
    caught here — a preflight that classifies its own failures cannot be reused by a caller that
    wants to classify them differently.
    """
    scorer = SCORERS.get(scorer_id)
    if scorer is None:
        raise_violation(
            ProjectionIssue.UNKNOWN_SCORER,
            f"no scorer {scorer_id!r}; known: {sorted(SCORERS)}",
            where="run",
        )
    reject_entry_declaring_personas(settings.config_dir)
    taxonomy = load_taxonomy(settings.config_dir)
    table = load_equivalences()
    personas = load_personas(settings.config_dir)
    pool = project_pool(
        bundle_root, declaration_path, config_dir=settings.config_dir, as_of=as_of
    )
    return ProjectionRunContext(
        pool=pool,
        scorer=scorer,
        scorer_id=scorer_id,
        taxonomy=taxonomy,
        table=table,
        persona_registry_version=personas.version,
        as_of=as_of,
    )
```

**`ProjectionIssue.UNKNOWN_SCORER` does not exist yet — verified.** Add it in this task exactly as Task 1 added `DECLARATION_MISSING` (member + docstring comment), and add its `ISSUE_SCOPE` row in Task 4 mapping to `ProjectionAvailability.SCORER_INVALID`. Task 4's enum-totality test is what will fail if you forget.

**Also verified for this task:** `Taxonomy.version`, `EquivalenceTable.version` and `PersonaRegistry.version` all already exist as sha256 strings (`extract/taxonomy.py:46`, `tailor/equivalences.py:25`, `tailor/persona.py:57`), so no new versioning mechanism is needed — only wiring.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/projection/ -v --no-cov -n 0`

Expected: PASS. `tests/projection/test_projection_posting.py`'s eight `posting_context` call sites now need the keyword — updating them is required by the signature change, but **do not weaken any assertion** while you are in there.

- [ ] **Step 6: Commit**

```bash
git add src/boardwatch/projection/run.py src/boardwatch/projection/posting.py src/boardwatch/cli/projection_cmd.py tests/projection/
git commit -m "Resolve one projection configuration snapshot per run"
```

---

### Task 4: Two outcome catalogs and an exhaustive mapping

Revision 2 asserted a total mapping without supplying one, which round 2 correctly ruled unreviewable. The mapping is the deliverable here, and a test derived from the enum is what keeps it total.

**Files:**
- Modify: `src/boardwatch/projection/run.py`
- Test: `tests/projection/test_projection_outcome_catalog.py`

**Interfaces:**
- Consumes: `ProjectionIssue` (32 members), `ProfileBundleError`, `PersonaError`, `TemplateArtifactError`, `TaxonomyError`, `EquivalenceError`.
- Produces: `ProjectionAvailability` (StrEnum), `ProjectionLeadOutcome` (StrEnum), `classify_availability(exc: Exception) -> ProjectionAvailability`, `classify_lead_outcome(exc: Exception) -> ProjectionLeadOutcome`, `ISSUE_SCOPE: Mapping[ProjectionIssue, ProjectionAvailability | ProjectionLeadOutcome]`.

- [ ] **Step 1: Write the failing tests**

```python
def test_every_projection_issue_is_mapped() -> None:
    """Derived from the enum, never a hardcoded list: a member added next year must fail here
    rather than land in a default bucket. A hardcoded catalog already passed 98 tests while
    covering 5 of 13 classes once in this repo (D-142/D-149)."""
    unmapped = [issue for issue in ProjectionIssue if issue not in ISSUE_SCOPE]
    assert unmapped == []


def test_run_invariant_causes_are_run_scoped_not_per_lead() -> None:
    """The template, the toolchain and the pinned budget are identical for every posting in a run.
    Classifying them per-lead would retry a missing renderer once per lead and could grant `seen`
    to leads that failed for a run-wide reason, because dispositions are written at
    runner.py:606 before the all-failed check at :624."""
    assert isinstance(
        ISSUE_SCOPE[ProjectionIssue.PINNED_SET_EXCEEDS_BUDGET], ProjectionAvailability
    )
    # Template failure is NOT a ProjectionIssue — it arrives as TemplateArtifactError from
    # tailor.render.latex, which is why it is classified by exception type, not by issue.
    assert classify_availability(TemplateArtifactError("bad")) is ProjectionAvailability.TEMPLATE_INVALID


def test_the_stamp_arms_use_their_real_issue_members() -> None:
    """Verified member names, not guessed ones: the catalog has MISSING_PROJECTION_APPROVAL and
    STALE_PROJECTION_APPROVAL."""
    assert ISSUE_SCOPE[ProjectionIssue.MISSING_PROJECTION_APPROVAL] is ProjectionAvailability.MISSING_APPROVAL
    assert ISSUE_SCOPE[ProjectionIssue.STALE_PROJECTION_APPROVAL] is ProjectionAvailability.STALE_APPROVAL
    assert ISSUE_SCOPE[ProjectionIssue.BUNDLE_UNREADABLE] is ProjectionAvailability.BUNDLE_UNREADABLE


def test_a_missing_extraction_and_an_empty_skill_set_are_different() -> None:
    """`jd_skills_for` returns None for missing extraction and a valid empty set separately
    (reports/tailor.py:346), and `select` routes an empty set to the curated no-match fallback
    (select.py:204). Collapsing them would turn a working fallback into a dropped lead."""
    assert ISSUE_SCOPE[ProjectionIssue.NO_JD_EXTRACTION] is ProjectionLeadOutcome.EXTRACTION_UNAVAILABLE
    assert not hasattr(ProjectionLeadOutcome, "NO_JD_SKILLS")


def test_foreign_exception_families_classify() -> None:
    assert classify_availability(TaxonomyError("bad")) is ProjectionAvailability.TAXONOMY_INVALID
    assert classify_availability(EquivalenceError("bad")) is ProjectionAvailability.EQUIVALENCES_INVALID
    assert classify_availability(PersonaError("bad")) is ProjectionAvailability.PERSONA_INVALID


def test_an_unmapped_exception_is_fatal_not_a_bucket() -> None:
    with pytest.raises(AssertionError):
        classify_availability(RuntimeError("something nobody mapped"))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/projection/test_projection_outcome_catalog.py -v --no-cov -n 0`

Expected: FAIL with `ImportError` on `ProjectionAvailability`.

- [ ] **Step 3: Write the catalogs and the mapping**

```python
class ProjectionAvailability(StrEnum):
    """Decided ONCE per run. Anything but AVAILABLE refuses the run before any lead earns a
    disposition, and sets `summary.fatal` (Task 6)."""

    AVAILABLE = "available"
    MISSING_APPROVAL = "missing_approval"
    STALE_APPROVAL = "stale_approval"
    DECLARATION_MISSING = "declaration_missing"
    DECLARATION_UNREADABLE = "declaration_unreadable"
    DECLARATION_INVALID = "declaration_invalid"
    BUNDLE_UNREADABLE = "bundle_unreadable"
    PERSONA_INVALID = "persona_invalid"
    SCORER_INVALID = "scorer_invalid"
    TAXONOMY_INVALID = "taxonomy_invalid"
    EQUIVALENCES_INVALID = "equivalences_invalid"
    TEMPLATE_INVALID = "template_invalid"
    TOOLCHAIN_UNAVAILABLE = "toolchain_unavailable"
    PINNED_BUDGET_OVERFLOW = "pinned_budget_overflow"


class ProjectionLeadOutcome(StrEnum):
    """Per attempted lead, reachable only when availability is AVAILABLE."""

    PROJECTED = "projected"
    POSTING_UNAVAILABLE = "posting_unavailable"
    EXTRACTION_UNAVAILABLE = "extraction_unavailable"
    LINEAGE_MISMATCH = "lineage_mismatch"
    OUTPUT_IO_FAILURE = "output_io_failure"
```

Then `ISSUE_SCOPE`, one row per `ProjectionIssue` member, written out in full. Derive the member list with `python -c "from boardwatch.projection.errors import ProjectionIssue; [print(i.name) for i in ProjectionIssue]"` and map each: the fidelity-contract and declaration-shape issues to `DECLARATION_INVALID`; `PINNED_SET_EXCEEDS_BUDGET` to `PINNED_BUDGET_OVERFLOW`; `POSTING_NOT_OPEN`/`POSTING_NO_CURRENT_VERSION` to `POSTING_UNAVAILABLE`; `NO_JD_EXTRACTION` to `EXTRACTION_UNAVAILABLE`; the stamp arms to `MISSING_APPROVAL`/`STALE_APPROVAL`. `classify_*` assert on a miss rather than returning a default.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/projection/test_projection_outcome_catalog.py -v --no-cov -n 0`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/boardwatch/projection/run.py tests/projection/test_projection_outcome_catalog.py
git commit -m "Map every projection failure to a run-scoped or per-lead outcome"
```

---

### Task 5: `project_for_posting`, extracted from the CLI

**Files:**
- Modify: `src/boardwatch/projection/run.py`
- Modify: `src/boardwatch/cli/projection_cmd.py:393-539` (becomes a thin caller)
- Modify: `src/boardwatch/projection/manifest.py` (new lineage fields)
- Test: `tests/projection/test_projection_for_posting.py`; existing `tests/projection/test_projection_cli_resume_project.py` must pass **unedited**

**Interfaces:**
- Consumes: `ProjectionRunContext`, `select(...) -> SelectionResult`, `resume_document_bytes`, `ProjectionManifest`, `manifest_bytes`.
- Produces: `ProjectionResult` (frozen: `outcome: ProjectionLeadOutcome`, `resume_path: Path | None`, `manifest_path: Path | None`, `lineage: ResumeSourceLineage | None`, `selection: SelectionResult | None`); `project_for_posting(ctx, engine, settings, posting_id, *, out_dir: Path, compile_runner: CompileRunner) -> ProjectionResult`.
- `ProjectionManifest` gains: `as_of: str`, `scorer_id: str`, `taxonomy_version: str`, `equivalence_version: str`, `persona_registry_version: str`, `posting_version_id: int`, `resume_sha256: str`, `resume_model_sha256: str`; `MANIFEST_SCHEMA_VERSION` 1 → 2.

- [ ] **Step 1: Write the failing tests**

```python
def test_the_manifest_carries_transformation_identity(...) -> None:
    """Bundle lineage alone records WHICH BUNDLE produced a résumé but not WHICH RULES. Two runs
    that disagree because the taxonomy moved must be distinguishable."""
    result = project_for_posting(ctx, engine, settings, posting_id, out_dir=out, compile_runner=fake)
    manifest = json.loads(result.manifest_path.read_bytes())
    assert manifest["taxonomy_version"] == ctx.taxonomy.version
    assert manifest["equivalence_version"] == ctx.table.version
    assert manifest["persona_registry_version"] == ctx.persona_registry_version
    assert manifest["scorer_id"] == ctx.scorer_id
    assert manifest["as_of"] == ctx.as_of.isoformat()
    assert manifest["posting_version_id"] == expected_version_id


def test_the_resume_hash_is_over_the_bytes_that_were_written(...) -> None:
    result = project_for_posting(...)
    assert result.lineage.resume_sha256 == hashlib.sha256(result.resume_path.read_bytes()).hexdigest()


def test_project_for_posting_never_resolves_a_pool(monkeypatch, ...) -> None:
    """The whole point of the two-API split: this function must consume the run's pool, never
    resolve its own, or the one-revision-per-run invariant is decorative."""
    def explode(*a, **k):
        raise AssertionError("project_for_posting must not call project_pool")
    monkeypatch.setattr(pool_mod, "project_pool", explode)
    project_for_posting(ctx, engine, settings, posting_id, out_dir=out, compile_runner=fake)


def test_a_refusing_lead_leaves_no_directory(...) -> None:
    """Sidecars are written before run_tailor, and the runner's cleanup only removes an EMPTY
    directory (`_remove_if_empty` calls rmdir(), runner.py:873), while
    tests/pipeline/test_pipeline_run.py:250 pins that a failed lead leaves nothing behind."""
    out = tmp_path / "lead"
    with pytest.raises(ProjectionError):
        project_for_posting(ctx, engine, settings, closed_posting_id, out_dir=out, compile_runner=fake)
    assert not out.exists()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/projection/test_projection_for_posting.py -v --no-cov -n 0`

Expected: FAIL with `ImportError` on `project_for_posting`.

- [ ] **Step 3: Extend the manifest**

Add the eight fields to `ProjectionManifest` and set `MANIFEST_SCHEMA_VERSION = 2`. Update its docstring: the sidecar is now *read* by the pipeline, so the line saying nothing reads it is obsolete and must go.

- [ ] **Step 4: Write `project_for_posting`**

Move the body of `projection_cmd.py:443-530` into it, with four changes:

1. No `project_pool` call — take `ctx.pool`.
2. No `typer.echo` / `typer.Exit` — raise the typed exceptions.
3. `compile_runner` is injected, not `reports.tailor._default_runner` imported privately. **Give that runner a public name in the same step:** add `def default_compile_runner() -> CompileRunner: return _default_runner` to `reports/tailor.py` and export it, so both `resume project` and the pipeline (Task 8) obtain it without reaching into a private symbol. Do not rename `_default_runner` itself — it has existing callers inside that module.
4. **Write to a temp directory inside the function and `os.replace` into `out_dir` only after both files and the lineage exist.** This is what makes the no-husk test pass; a partial write followed by a raise is the husk.

Compute both hashes from the one `bytes` object you wrote — never re-read the path.

- [ ] **Step 5: Rewire the CLI as a thin caller**

`resume project` calls `resolve_projection_run` then `project_for_posting`, keeps its `typer.echo` lines and exit codes, and maps exceptions through the existing `_boundary_outcome`. **Its tests must pass unedited**, including the stale-approval case (`test_projection_cli_resume_project.py:443`) and the `TemplateArtifactError` case (`:521`).

- [ ] **Step 6: Run both suites**

Run: `uv run pytest tests/projection/ -v --no-cov -n 0`

Expected: PASS, with `test_projection_cli_resume_project.py` **unmodified**. If you needed to edit it, the extraction changed CLI behaviour — fix the extraction, not the test.

- [ ] **Step 7: Commit**

```bash
git add src/boardwatch/projection/ src/boardwatch/cli/projection_cmd.py tests/projection/
git commit -m "Extract per-posting projection so the pipeline and CLI share one implementation"
```

---

### Task 6: `run_tailor` accepts lineage and writes it in the artifact's transaction

**Files:**
- Modify: `src/boardwatch/reports/tailor.py:452` (signature), `:721` and `:746` (meta and insert)
- Test: `tests/reports/test_tailor_lineage.py`

**Interfaces:**
- Consumes: `ResumeSourceLineage` from `boardwatch.core.lineage`.
- Produces: `run_tailor(..., source_lineage: ResumeSourceLineage | None = None)`, and a new
  `ResumeLineageMismatch(RuntimeError)` defined in `reports/tailor.py` beside the existing
  `NoCurrentVersionError` (`:122`) — a typed exception at the raise site, never a message check.
  The pipeline maps it to `ProjectionLeadOutcome.LINEAGE_MISMATCH`.

- [ ] **Step 1: Write the failing tests**

```python
def test_lineage_lands_on_the_tailored_row(...) -> None:
    """Not on resume_master: that node is content-addressed and reused, and its metadata is
    written only on first creation, so lineage there would be attributed to whichever run
    happened to create the master first."""
    run_tailor(engine, settings, posting_id, resume_path=projected, out_dir=out,
               source_lineage=lineage)
    meta = tailored_row_meta(engine, posting_id)
    assert meta["projection_bundle_revision"] == "21"


def test_a_hash_mismatch_refuses_before_rendering(...) -> None:
    """The check must be able to fail. A lineage whose hash does not match the file handed over
    is exactly the manifest-B-with-resume-A case."""
    wrong = dataclasses.replace(lineage, resume_sha256="0" * 64)
    with pytest.raises(ResumeLineageMismatch):
        run_tailor(engine, settings, posting_id, resume_path=projected, out_dir=out,
                   source_lineage=wrong)


def test_a_posting_version_change_refuses(...) -> None:
    """Selection ran against version A; if tailoring resolves version B the lead is refused."""
    stale = dataclasses.replace(lineage, posting_version_id=lineage.posting_version_id - 1)
    with pytest.raises(ResumeLineageMismatch):
        run_tailor(..., source_lineage=stale)


def test_existing_callers_are_unaffected(...) -> None:
    """Every current caller passes no lineage and must behave exactly as before."""
    before = run_tailor(engine, settings, posting_id, resume_path=authored, out_dir=out)
    assert before.pdf_path is not None
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/reports/test_tailor_lineage.py -v --no-cov -n 0`

Expected: FAIL — `run_tailor() got an unexpected keyword argument 'source_lineage'`.

- [ ] **Step 3: Implement**

Add the keyword-only parameter with default `None` (the signature is already keyword-oriented, so no caller changes). When it is not `None`, **before** `load_resume`: read the file once into `bytes`, compare `sha256` to `lineage.resume_sha256`, compare the resolved `CurrentVersion.posting_version_id` (already fetched at `:389`) to `lineage.posting_version_id`, and raise a new typed `ResumeLineageMismatch` on either. Parse the résumé from **that same buffer**, and check `resume_model_sha256` against the parsed model. Merge `lineage.as_meta()` into the `meta` dict built at `:721` so it is inserted in the same transaction as the artifact at `:746`.

- [ ] **Step 4: Run the tests, then the import wall**

Run: `uv run pytest tests/reports/test_tailor_lineage.py tests/profile_bundle/test_profile_bundle_tailor_isolation.py -v --no-cov -n 0`

Expected: PASS both. The wall test is the one that catches a lineage import from the wrong module.

- [ ] **Step 5: Commit**

```bash
git add src/boardwatch/reports/tailor.py tests/reports/test_tailor_lineage.py
git commit -m "Validate and record projected-resume lineage on the tailored artifact"
```

---

### Task 7: The `--project` preflight, its fatal class, and the run contract

**Files:**
- Modify: `src/boardwatch/pipeline/runner.py` (preflight before ranking; `PipelineSummary` fields)
- Modify: `src/boardwatch/cli/run_cmd.py:47` (the flag)
- Modify: `docs/program/RUN_CONTRACT.md` (fifth fatal class)
- Test: `tests/pipeline/test_pipeline_projection_preflight.py`

**Interfaces:**
- Consumes: `resolve_projection_run`, `classify_availability`, `ProjectionAvailability`.
- Produces: `run_pipeline(..., project: bool = False)`; `PipelineSummary.projection_availability: ProjectionAvailability | None` (None when the flag is absent) and `.projection_outcomes: Counter[ProjectionLeadOutcome]` (empty by default, so an outcome that never occurred is absent rather than zero).

- [ ] **Step 1: Write the failing test — all five assertions together**

```python
def test_a_stale_stamp_fails_the_run_and_consumes_no_leads(...) -> None:
    """FIVE assertions in one test on purpose: round 2 showed four of them can pass while the
    fifth is broken. A run that refuses but exits 0 is P3's 'reporting success while producing
    nothing'; a run that refuses after dispositions are written destroys the drain."""
    summary = run_pipeline(engine, settings, project=True, ...)   # stamp deliberately stale
    assert summary.projection_availability is ProjectionAvailability.STALE_APPROVAL
    assert summary.fatal is not None                       # 1. fatal set
    assert run_row_status(engine, summary.run_id) == RUN_FAILED   # 2. persisted failure
    assert "FATAL" in funnel_markdown(...)                 # 3. visible in the artifact
    assert disposition_count(engine) == 0                  # 4. no lead consumed
    # 5. retry visibility, after the stamp is made current
    approve_current(...)
    second = run_pipeline(engine, settings, project=True, ...)
    assert {lead.posting_id for lead in second.tailored} == original_shortlist_ids


def test_without_the_flag_nothing_changes(...) -> None:
    summary = run_pipeline(engine, settings, project=False, ...)
    assert summary.projection_availability is None
    assert summary.fatal is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/pipeline/test_pipeline_projection_preflight.py -v --no-cov -n 0`

Expected: FAIL — `run_pipeline() got an unexpected keyword argument 'project'`.

- [ ] **Step 3: Implement the preflight**

Place it **after scan-outcome handling and before the ranker call at `runner.py:428`**. On anything but `AVAILABLE`, set `summary.projection_availability`, set `summary.fatal` to a typed message naming the member and its remedy, append to `stage_errors`, and return through the existing `finally` so `finish_run` records `RUN_FAILED` (`runner.py:721`) and the CLI exits 1. Do **not** rely on `_zero_output_guard`/`_cohort_guard` — they run after the disposition write and need the ranked cohort.

**`as_of` comes from the run's own clock, fixed once.** Derive it as `utcnow().date()` using `boardwatch.core.clock.utcnow` — the same clock the `runs` row already uses — and pass it into `resolve_projection_run`. It is not cosmetic: `as_of` feeds effective-fact resolution (`pool.py:201,309`), so it decides which facts render. One run, one date, even if the run crosses midnight UTC.

Wrap the call as:

```python
        try:
            projection_ctx = resolve_projection_run(
                engine, settings,
                bundle_root=resolve_bundle_root(settings.config_dir, None),
                declaration_path=settings.config_dir / "projection.yaml",
                scorer_id=scorer_id,
                as_of=utcnow().date(),
            )
            summary.projection_availability = ProjectionAvailability.AVAILABLE
        except Exception as exc:  # classified, never swallowed
            summary.projection_availability = classify_availability(exc)
            summary.fatal = (
                f"projection unavailable: {summary.projection_availability.value} ({exc})"
            )
            stage_errors.append(summary.fatal)
            return summary
```

The bare `except Exception` is deliberate and safe **only because `classify_availability` asserts on an unmapped type** (Task 4): an unrecognised failure becomes a loud test failure rather than a silent availability member.

- [ ] **Step 4: Add the flag**

In `run_cmd.py`, beside `--resume`:

```python
    project: bool = typer.Option(
        False,
        "--project",
        help="Render each lead from the career-profile bundle's projection instead of the "
        "authored résumé. Requires a current projection approval.",
    ),
```

- [ ] **Step 5: Document the fatal class**

Add a fifth row to `docs/program/RUN_CONTRACT.md`'s fatal table: *projection requested and unavailable* — fatal, exit 1, no lead disposition written, remedy `approve-projection`. Match the existing rows' wording style.

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/pipeline/ -v --no-cov -n 0`

Expected: PASS, with the existing pipeline suite unedited.

- [ ] **Step 7: Commit**

```bash
git add src/boardwatch/pipeline/runner.py src/boardwatch/cli/run_cmd.py docs/program/RUN_CONTRACT.md tests/pipeline/test_pipeline_projection_preflight.py
git commit -m "Refuse a projected run before any lead earns a disposition"
```

---

### Task 8: Per-lead wiring in the tailor loop

**Files:**
- Modify: `src/boardwatch/pipeline/runner.py:518-530` (the `run_tailor` call)
- Test: `tests/pipeline/test_pipeline_projection_leads.py`

**Interfaces:**
- Consumes: `project_for_posting`, `run_tailor(..., source_lineage=...)`.
- Produces: populated `summary.projection_outcomes`.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_projected_lead_renders_from_the_projection(...) -> None:
    summary = run_pipeline(engine, settings, project=True, ...)
    assert summary.projection_outcomes[ProjectionLeadOutcome.PROJECTED] == len(summary.tailored)
    meta = tailored_row_meta(engine, summary.tailored[0].posting_id)
    assert meta["projection_bundle_revision"] == expected_revision


def test_one_pool_serves_every_lead(monkeypatch, ...) -> None:
    """A promotion between lead 1 and lead 2 must not change lead 2's pool: the run holds one
    snapshot, so counting resolutions is the assertion."""
    calls = []
    monkeypatch.setattr(run_mod, "resolve_projection_run", counting(calls))
    run_pipeline(engine, settings, project=True, ...)
    assert len(calls) == 1


def test_a_failed_projection_lead_leaves_no_directory(...) -> None:
    summary = run_pipeline(engine, settings, project=True, ...)  # one posting goes closed
    assert not (day_dir / slug_of_the_failed_lead).exists()
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/pipeline/test_pipeline_projection_leads.py -v --no-cov -n 0`

Expected: FAIL — `summary.projection_outcomes` empty or missing.

- [ ] **Step 3: Implement**

Inside the loop, when `project` is on:

```python
            if project:
                try:
                    projected = project_for_posting(
                        projection_ctx, engine, settings, posting.posting_id,
                        out_dir=_ensure_dir(dest), compile_runner=default_compile_runner(),
                    )
                except Exception as exc:
                    outcome = classify_lead_outcome(exc)
                    summary.projection_outcomes[outcome] += 1
                    message = f"projection: posting {posting.posting_id}: {outcome.value}: {exc}"
                    stage_errors.append(message)
                    summary.errors.append(message)
                    continue
                summary.projection_outcomes[ProjectionLeadOutcome.PROJECTED] += 1
                lead_resume_path = projected.resume_path
                lead_lineage = projected.lineage
            else:
                lead_resume_path = resume_path
                lead_lineage = None
```

then pass `resume_path=lead_resume_path, source_lineage=lead_lineage` to the existing `run_tailor` call. A per-lead projection failure counts its outcome, records a **non-fatal** error, and `continue`s — it does **not** fall back to `resume.yaml` and does **not** abort the run. Also catch `ResumeLineageMismatch` from `run_tailor` itself and count it as `LINEAGE_MISMATCH` the same way.

`summary.projection_outcomes` is a `Counter[ProjectionLeadOutcome]` initialised empty, so an outcome that never occurs is absent rather than zero — which is what lets Task 9 omit the stage entirely when projection did not run.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/pipeline/ -v --no-cov -n 0`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/boardwatch/pipeline/runner.py tests/pipeline/test_pipeline_projection_leads.py
git commit -m "Render projected leads inside the daily pipeline"
```

---

### Task 9: The funnel's projection stage

**Files:**
- Modify: `src/boardwatch/reports/run_funnel.py` (new stage; `ARTIFACT_VERSION` 4 → 5)
- Modify: `src/boardwatch/pipeline/funnel_writer.py` (carry the counts)
- Test: `tests/reports/test_run_funnel_projection.py`

**Interfaces:**
- Consumes: `summary.projection_outcomes`, `summary.projection_availability`.
- Produces: a `Stage(name="projection", ...)` between `liveness` and `tailor`; the `tailor` stage now enters at `projected`.

- [ ] **Step 1: Write the failing tests**

```python
def test_the_projection_stage_balances(...) -> None:
    """served_after_liveness = projected + every per-lead projection drop. Without its own stage
    projection drops either break the tailor stage's existing identity
    (shortlisted = tailored + tailor_failed + withheld_not_live, run_funnel.py:787) or hide
    inside tailor_failed."""
    funnel = collect_run_funnel(engine, settings, run_id=run_id)
    stage = stage_named(funnel, "projection")
    assert stage.entered == stage.advanced + sum(d.count for d in stage.drops)


def test_the_tailor_stage_now_enters_at_projected(...) -> None:
    funnel = collect_run_funnel(...)
    assert stage_named(funnel, "tailor").entered == stage_named(funnel, "projection").advanced


def test_the_projection_stage_is_recounted_from_the_store(...) -> None:
    """A component's self-report is not verification. The stage's `advanced` must be checkable
    against resume_tailored rows carrying projection lineage, not just against the summary that
    produced it."""
    assert projected_rows_in_store(engine, run_id) == stage_named(funnel, "projection").advanced


def test_the_stage_is_absent_without_the_flag(...) -> None:
    """Absent, not zeroed. A stage reporting 0 claims projection ran and dropped nothing; D-023
    already set this precedent with `not instrumented` versus 0."""
    funnel = collect_run_funnel(...)   # run without --project
    assert stage_named(funnel, "projection") is None


def test_the_artifact_version_is_bumped() -> None:
    """Convention: every bump so far signalled a new top-level SECTION (run_funnel.py:58-64),
    and D-113 is the precedent for declining one on a merely additive key."""
    assert ARTIFACT_VERSION == 5
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/reports/test_run_funnel_projection.py -v --no-cov -n 0`

Expected: FAIL — no stage named `projection`, and `ARTIFACT_VERSION == 4`.

- [ ] **Step 3: Implement**

Build the stage from `summary.projection_outcomes`, one `Drop(reason=<outcome value>, count=…)` per non-`PROJECTED` member, `entered` = leads served after liveness, `advanced` = the `PROJECTED` count, `derived=False` (the drops are counted independently, not a remainder). Re-point the `tailor` stage's `entered` at the projection stage's `advanced` when projection ran. Bump `ARTIFACT_VERSION` to 5 and extend the comment block at `:58-64` to say a `projection` section is why.

- [ ] **Step 4: Run the whole funnel suite**

Run: `uv run pytest tests/reports/ -v --no-cov -n 0`

Expected: PASS. Any existing test asserting `artifact_version == 4` must be updated — that is the bump, not an accommodation.

- [ ] **Step 5: Commit**

```bash
git add src/boardwatch/reports/run_funnel.py src/boardwatch/pipeline/funnel_writer.py tests/reports/
git commit -m "Give projection its own balanced funnel stage"
```

---

### Task 10: The gate, the benchmark, and the decision record

The compile budget must be known **before** merge, not measured afterwards: a serial ~100-compile stage can be operationally broken while every correctness test passes.

**Files:**
- Modify: `docs/program/METRICS.md` (benchmark row)
- Modify: `docs/program/DECISIONS.md` (+ index row, then `make reindex`)
- Modify: `docs/program/STATE.md` (surgical edit only)

- [ ] **Step 1: Run the full gate**

Run: `make check` (plain mode, capture the exit code, never piped)

Expected: exit 0. If it fails, **re-run it alone before diagnosing** — a contended gate produces plausible-looking false failures on a tree that is actually green.

- [ ] **Step 2: Benchmark the projection stage**

Run `boardwatch run --project` over ten representative postings against a **copy** of the store. Record in `METRICS.md`: wall time for the projection stage, compile count distribution per lead (expected up to ~10: one pinned prefix, up to eight candidates, one render), and total. **Declare a maximum acceptable stage duration** in the same row.

- [ ] **Step 3: Verify lineage through a second path**

Query the store directly for `resume_tailored` rows from that run and confirm each names its bundle revision and posting version. Counting the deliverable through a different path than the one that produced it is the repo's own rule; the funnel's self-report does not discharge it.

- [ ] **Step 4: Record the decision**

Append a `DECISIONS.md` entry: context (projection reached no unattended run), the choice (opt-in `--project`, fail-closed preflight, one snapshot per run, content+transformation lineage, its own funnel stage), and the alternatives rejected (per-lead fallback — it consumed leads permanently via `built`; a default flip — deferred to P5b). Add its index row, then run `make reindex`.

- [ ] **Step 5: Update STATE surgically**

Record P5a as shipped and **parent P5 as still unmet** (the default flip is P5b). Do not rewrite the file.

- [ ] **Step 6: Commit**

```bash
git add docs/program/METRICS.md docs/program/DECISIONS.md docs/program/STATE.md
git commit -m "Record slice P5a's gate evidence and the projection integration decision"
```

---

## Open, and owner-gated — do not decide these while implementing

- **P5b's flip criteria:** how many clean projected runs, over how many distinct postings, at what defect budget, before `resume.yaml` stops being the unattended default.
- **`--project` combined with an explicit `--resume custom.yaml`** — today they would conflict. Until ruled, refuse the combination with a typed error rather than silently preferring one.
- **Exposing `--bundle` / `--declaration` / `--scorer` on `run`** as `resume project` has them, and whether a non-owner can point `--project` at their own bundle without adopting this repo owner's filesystem layout.
