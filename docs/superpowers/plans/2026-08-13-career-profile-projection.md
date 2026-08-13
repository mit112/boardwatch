# Career-Profile Projection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `projection` package that turns the canonical career-profile bundle into a
`Resume` document the existing tailor renders, choosing per-JD which optional entries appear against
a fixed pinned core.

**Architecture:** Two stages behind one new top-level package. Stage 1 is JD-blind: read the bundle
plus an owner-authored `projection.yaml`, validate a fidelity contract, and emit a typed
`ProjectionPool`. Stage 2 is JD-aware: score candidate entries against the posting's extracted
skills, admit them highest-first, and stop when the page budget is exceeded. `tailor` is unchanged
except for one extracted public function; the `profile_bundle`↔`tailor` import wall stays up because
`projection` sits outside both root sets.

**Tech Stack:** Python 3.11+, pydantic v2 (frozen models), SQLAlchemy Core, Typer, pytest,
`uv` for everything. No new dependency.

**Spec:** `docs/superpowers/specs/2026-08-13-career-profile-projection-design.md` (revision 3)
**Preflight:** `docs/superpowers/research/2026-08-13-projection-plan-preflight.md` — **read this
second. It falsifies four of the spec's claims and corrects twelve of its citations.** Where the
spec and the preflight disagree, the preflight wins; it was verified against the code at `f8991c6`.

---

## Global Constraints

Every task's requirements implicitly include this section.

### Commands and gates

- **Neither `python` nor `boardwatch` is on `PATH`.** Always `uv run …`.
- **`make check` is the only gate.** It is `generalization index-check lint type test` (`Makefile:2`).
  Run it in plain mode and capture the real exit code. **Never pipe it through `head`/`tail`** —
  SIGPIPE kills the run and you read a false negative. It takes ~4.5 minutes.
- **A narrow pytest run needs `--no-cov`.** `addopts` carries `--cov-fail-under=85`
  (`pyproject.toml:95`), so a single-file run exits 1 even when green.
- `mypy --strict` runs on **`src` and `tools` only** — `tests/` is not type-checked. `ruff` runs on
  everything, `line-length = 100`, `select = ["E","F","I","UP","B"]`.
- Coverage floor is **85% branch coverage** repo-wide (`branch = true`, `pyproject.toml:98-99`).
- **`-n auto` belongs at call sites only** (`Makefile:8`, `ci.yml:52`), never in `addopts` — the
  `perf` job measures wall clock and inheriting workers corrupts it.
- Two CI-only jobs exist: **`gitleaks` and `perf` — two, not three.** Run
  `gitleaks git --log-opts=origin/main..HEAD` before any push.

### The generalization checker will block naive choices

- **R5 bans these stems on any *data* file, including a directory segment:** `resume`, `résumé`,
  `cv`, `cover_letter`, `eeo`, `work_auth`, `transcript`. `.py` modules are exempt.
  - `src/boardwatch/projection/resume.py` — **fine**
  - `tests/projection/fixtures/resume.yaml` — **VIOLATION**
  - `tests/projection/fixtures/master_resume.yaml` — **fine** (stem is `master_resume`)
- **R7: every new file with a `.yaml/.yml/.json/.txt/.tex/.toml/.csv` suffix needs a reviewed
  `SHIPPED_DATA` entry** in `tools/generalization/allowlists.py` stating `kind`, `reason`,
  `provenance`, `pin`. `kind` is closed: `{taxonomy, company_enumeration, fixture, corpus, template}`.
  `provenance` is closed: `{first-party, synthetic, public, licensed}`. A pin is
  `"sha256:<digest>"` and **pin drift is a violation**.
- **R1 bans absolute home paths.** Use `tmp_path` in tests, `~/…` in docs.
- **Never add an allowlist entry to excuse a fixture.** Entries are keyed on *matched text*, so an
  exception is repo-wide; an unused entry is itself a violation, and a blank reason is a violation.
  Restructure the value instead.
- R9/R10/R11 are scoped to a literal 14-module list a new package is **not** on, so a `projection`
  module may legally hold non-empty string collections.

### The import wall — non-negotiable

- The package is **`src/boardwatch/projection/`, top level.** Not `src/boardwatch/tailor/projection/`,
  which would join `TAILOR_ROOTS` (`test_profile_bundle_tailor_isolation.py:41-44`) and turn
  `test_no_production_tailor_module_reaches_the_profile_bundle` red instantly.
- **`boardwatch.projection` may not be imported from any of the 58 modules in the tailor closure** —
  most sharply not from `reports/tailor.py`, `core/settings.py`, or `cli/context.py`. The walk is
  transitive, so one such import drags `profile_bundle` into the offender list.
- **`cli/app.py` is NOT in the closure**, so registering a new command module on the Typer app is safe.

### Test conventions

- **`tests/projection/`**, with its own `conftest.py`, **no `__init__.py`**, every file named
  `test_projection_*.py`. This mirrors `tests/profile_bundle/`, the newest package's convention.
- **Test module basenames must be globally unique** — `tests/` has no packages, so a duplicate
  basename aborts collection repo-wide.
- **Import fixtures as `from tests.projection.conftest import …`, never bare `from conftest import`.**
  A bare import binds whichever `conftest.py` loaded first.
- **There is no snapshot harness and no update mechanism.** `grep -rn "addoption"` is zero hits
  repo-wide. Do not write `--snapshot-update`. The repo's golden convention is byte-equality against
  a live generator (see `test_profile_bundle_schema_export.py:34-40`); regeneration means calling the
  generator and writing its output by hand.
- **Derive expected sets from the bundle at run time, never hardcode them.** A hardcoded catalog
  passed 98 tests while covering 5 of 13 documents once already. Any derived check also needs a
  non-vacuity assertion proving the derivation found something.

### Code conventions

- Frozen pydantic v2 models (`model_config = ConfigDict(frozen=True)`) or frozen dataclasses.
- **Typed violations at the raise site — never classify behaviour by string-matching a message.**
  Reason codes are a `StrEnum` closed catalog carried as a keyword-only payload on the exception,
  following `LLMLaneDeadError` (`llm/client.py:41-53`).
- Package root exception `ProjectionError(Exception)`, following `ProfileBundleError`
  (`profile_bundle/errors.py:452`).
- **Out-of-catalog is a failure, never a new bucket.**
- Commits are **plain imperative sentences**, sentence-capitalised, no trailing period, no
  conventional-commit prefix. **No AI attribution anywhere.**

### Scope

- v1 projects **`skill_groups`, `entries`, `extracurricular`** and nothing else. `header` and
  `education` are template-hardcoded and carried as an inert shell.
- **Do not pick a scorer.** Task 21 builds four candidates behind one interface; the winner is
  selected by measurement against the owner-labeled matrix (Task 20), not by this plan.
- Do not touch `Resume`, `latex.py`, `persona.py`, or the store schema.

---

## Preflight corrections carried into every task

The spec is the design input, but these eight statements in it are wrong. **Do not implement from
the spec's version of any of them.**

| # | The spec says | Implement instead |
|---|---|---|
| 1 | an out-of-catalog `Entry.kind` "falls through to Experience" | Both section filters are equality tests (`tailor/render/latex.py:155`, `:170`). An out-of-catalog `kind` is **silently omitted from the PDF entirely**. Task 6's test asserts absence from the rendered source. |
| 2 | `render/latex.py` | **`tailor/render/latex.py`.** `src/boardwatch/render/` does not exist. |
| 3 | `FactValue` "has nine typed shapes" (§4.1 line 264) | **Ten** (`profile_bundle/models/facts.py:52-61`). The spec's own next paragraph says ten. |
| 4 | `effective_skills(text, jd_skills, taxonomy, equivalences)` | **`effective_skills(text, jd_skills, table, taxonomy)`** — the repo calls it `table`, and `build_plan`'s order is `(resume, jd_skills, table, taxonomy)`. |
| 5 | a test asserts the shared callable "is the only implementation" | There are **four** non-equivalent implementations; folding `reports/tailor.py:255,271` in would change their audit output. Narrow it to *"`build_plan` and projection call the same callable"* (Task 2). |
| 6 | reuse `approvals.py`'s owner-gate for the projection stamp | `test_profile_bundle_cli_approval.py:427-447` asserts by `rglob` that **exactly two files** call `approval_stamp_bytes(`, and `ApprovedVia` is a closed one-member enum in the shipped JSON schema. Define a **separate** projection stamp type (Task 9). |
| 7 | artifact metadata "records only master kind and validator version" | That is the master artifact. The tailored artifact's meta carries ~17 keys from `_trace` (`reports/tailor.py:279-310`). Slice P5 adds lineage keys to a rich dict. |
| 8 | effectiveness is "derived separately", `effective.py:76-147` | `effective.py:60-95` **+ `validation/referential.py:708-721`**. And `eligible_fact_surfaces` returns `frozenset()` for a non-effective fact — so Task 8 must use `effective_fact_ids` for the effectiveness row and the predicate catalog for the surface row, or the effectiveness test passes vacuously. |

Additionally, three facts the spec omits entirely:

- **No `Resume` serializer exists anywhere in the repo.** Task 11 builds it.
- **`SkillGroup` has `label` + `items: list[str]`, not `skills`.** `projection.yaml` declares bundle
  *ids*; Task 5 maps id → `SkillRecord.canonical_name` → `items`.
- **The packaged example bundle is a draft** with `bundle_digest: ''` and no blobs, so
  `read_current_once` cannot reach it. Every test goes through `tests/profile_bundle/conftest.py`'s
  `synthetic_bundle` fixture or `materialise`.

---

## File Structure

### Created

| Path | Responsibility |
|---|---|
| `src/boardwatch/projection/__init__.py` | Public surface: `project_pool`, `select_entries`, `ProjectionPool`, `ProjectionError`. Nothing else is imported by callers. |
| `src/boardwatch/projection/errors.py` | `ProjectionError` root, `ProjectionIssue` StrEnum catalog, `ProjectionViolation` frozen record. |
| `src/boardwatch/projection/declaration.py` | The `projection.yaml` model + loader + `projection_digest`. Closed `kind` catalog. |
| `src/boardwatch/projection/grammar.py` | The two-namespace placeholder grammar and the ten-arm `FactValue` renderer. |
| `src/boardwatch/projection/contract.py` | The §7 fidelity contract: one predicate per row, all fatal. |
| `src/boardwatch/projection/shell.py` | The inert `header`/`education` shell, read from `shell_source`. |
| `src/boardwatch/projection/pool.py` | Stage 1: bundle + declaration → `ProjectionPool`. |
| `src/boardwatch/projection/serialize.py` | `Resume` → YAML bytes that `load_resume` reads back identically. |
| `src/boardwatch/projection/manifest.py` | The `projection-manifest.json` sidecar. |
| `src/boardwatch/projection/stamp.py` | The projection approval stamp — its own type, its own storage. |
| `src/boardwatch/projection/scoring.py` | The scorer protocol and the four candidate scorers. Names no winner. |
| `src/boardwatch/projection/select.py` | Stage 2: admission floor, ranking, budget fit, four-arm gate handling. |
| `src/boardwatch/projection/posting.py` | The posting-context seam: `(jd_skills, page_budget)` for a posting id. |
| `src/boardwatch/cli/projection_cmd.py` | `boardwatch resume project` + `boardwatch profile-bundle project`/`approve-projection`. |
| `tests/projection/conftest.py` | Fixtures: a materialised bundle, a minimal declaration, a fake terminal. |
| `tests/projection/test_projection_*.py` | One file per source module. |

### Modified

| Path | Change |
|---|---|
| `src/boardwatch/tailor/plan.py` | Task 1 only: extract public `effective_skills`; `build_plan` calls it. |
| `src/boardwatch/reports/tailor.py` | Task 17 only: extract the `jd_skills` query into a named function. |
| `src/boardwatch/cli/app.py` | Task 19: one import + one `add_typer`/`command` line. |
| `tools/generalization/allowlists.py` | Every task that adds a data file adds its `SHIPPED_DATA` entry. |
| `tests/generalization/test_inventory.py:55` | Task 4: bump `assert len(scope) == 74`. |

---

# Slice P0 — the shared scoring primitive

**Gate:** existing plan tests green; **both early returns preserved** (empty `jd_skills`, all-zero
coverage); a drift test proves `build_plan` routes through the new callable.

---

### Task 1: Extract a public `effective_skills` from `plan.py`

**Files:**
- Modify: `src/boardwatch/tailor/plan.py:65-104`
- Test: `tests/unit/test_tailor_plan_effective_skills.py`

**Interfaces:**
- Produces: `effective_skills(text: str, jd_skills: set[str], table: EquivalenceTable, taxonomy: Taxonomy) -> set[str]` — the one implementation both `build_plan` and `projection.scoring` score with.

Context you need: today the logic is a **closure**, `cover(b: Bullet) -> int` at `plan.py:76-78`. It
takes a `Bullet` because it keys into a `swaps_by_bullet` dict built at `:70-74`, and it returns a
**count**, never a set — so there is nothing set-returning to promote. `build_plan` reuses that same
dict at `:97` when emitting `EquivalenceSwap` ops, so the dict must stay.

**Accepted consequence:** after this change `_applicable_swaps` runs twice per bullet — once inside
`effective_skills` for scoring, once for the memo at `:70-74`. `equivalences.yaml` is 159 bytes, so
the cost is negligible; the alternative (passing precomputed swaps in) would break the single-callable
property this task exists to create.

- [ ] **Step 1: Write the failing test**

```python
"""`effective_skills` is the one coverage primitive `build_plan` and projection share."""

from __future__ import annotations

import pytest

from boardwatch.extract.taxonomy import Taxonomy, TaxonomyPattern
from boardwatch.tailor import plan as plan_mod
from boardwatch.tailor.equivalences import EquivalencePair, EquivalenceTable
from boardwatch.tailor.model import Bullet, Entry, Resume
from boardwatch.tailor.plan import build_plan, effective_skills


def _taxonomy(*names: str) -> Taxonomy:
    import re

    return Taxonomy(
        patterns=tuple(
            TaxonomyPattern(
                name=n,
                category="language",
                pattern=n,
                case_sensitive=False,
                regex=re.compile(n, re.IGNORECASE),
            )
            for n in names
        ),
        version="test-1",
        source="bundled",
    )


def _resume(*bullets: tuple[str, str]) -> Resume:
    return Resume(
        header=["Example Candidate", "candidate@example.com"],
        education=["Example University"],
        skill_groups=[],
        entries=[
            Entry(
                entry_id="entry.one",
                heading="One",
                bullets=[Bullet(bullet_id=bid, text=text) for bid, text in bullets],
            )
        ],
    )


def test_effective_skills_returns_what_the_text_demonstrates() -> None:
    taxonomy = _taxonomy("python", "swift")
    found = effective_skills("Built a python service", {"python"}, EquivalenceTable((), "v"), taxonomy)
    assert found == {"python"}


def test_effective_skills_includes_swap_images_the_jd_makes_reachable() -> None:
    """The property that distinguishes this from a bare `taxonomy.extract`: an equivalence
    whose target the JD asks for counts as covered."""
    taxonomy = _taxonomy("golang")
    table = EquivalenceTable((EquivalencePair(from_phrase="golang", to_phrase="go"),), "v")
    found = effective_skills("Wrote golang services", {"go"}, table, taxonomy)
    assert found == {"golang", "go"}


def test_effective_skills_omits_a_swap_image_the_jd_never_asked_for() -> None:
    """Non-vacuity: the swap union is JD-gated, not unconditional."""
    taxonomy = _taxonomy("golang")
    table = EquivalenceTable((EquivalencePair(from_phrase="golang", to_phrase="go"),), "v")
    found = effective_skills("Wrote golang services", {"rust"}, table, taxonomy)
    assert found == {"golang"}


def test_build_plan_routes_through_effective_skills(monkeypatch: pytest.MonkeyPatch) -> None:
    """The drift test, scoped honestly.

    It asserts `build_plan` and projection score with ONE callable — not that the callable is
    the repo's only coverage implementation. It is not: `reports/tailor.py:255` and `:271` omit
    the swap union and `tailor/coverage.py:55-61` scores a different corpus, so folding those in
    would change their emitted audit values. Replacing the callable and observing `build_plan`
    change is what proves the routing, and it cannot pass if the closure is reinstated.
    """
    taxonomy = _taxonomy("python")
    resume = _resume(("b1", "Built a python service"), ("b2", "Wrote documentation"))

    calls: list[str] = []

    def fake(text: str, jd_skills: set[str], table: EquivalenceTable, tax: Taxonomy) -> set[str]:
        calls.append(text)
        return set()

    monkeypatch.setattr(plan_mod, "effective_skills", fake)
    result = build_plan(resume, {"python"}, EquivalenceTable((), "v"), taxonomy)

    assert calls, "build_plan never called effective_skills"
    # Every bullet scored 0 through the stub, so the all-zero early return fires.
    assert result.ops == ()


def test_the_empty_jd_skills_early_return_is_preserved() -> None:
    """P0's gate, arm 1. `plan.py:68-69`."""
    resume = _resume(("b1", "Built a python service"))
    assert build_plan(resume, set(), EquivalenceTable((), "v"), _taxonomy("python")).ops == ()


def test_the_all_zero_coverage_early_return_is_preserved() -> None:
    """P0's gate, arm 2. `plan.py:81-82`. The JD is non-empty and nothing matches."""
    resume = _resume(("b1", "Wrote documentation"))
    assert build_plan(resume, {"python"}, EquivalenceTable((), "v"), _taxonomy("python")).ops == ()
```

- [ ] **Step 2: Run it to confirm it fails, and confirm WHICH assertion trips**

```
uv run pytest tests/unit/test_tailor_plan_effective_skills.py -v --no-cov -n 0
```

Expected: `ImportError: cannot import name 'effective_skills' from 'boardwatch.tailor.plan'` at
collection. That is a collection error, not an assertion — so after Step 3, re-run and confirm the
two early-return tests pass for the right reason rather than because a prior assertion masked them.

- [ ] **Step 3: Add the function and route `build_plan` through it**

In `src/boardwatch/tailor/plan.py`, insert after `_applicable_swaps` (ends `:62`):

```python
def effective_skills(
    text: str, jd_skills: set[str], table: EquivalenceTable, taxonomy: Taxonomy
) -> set[str]:
    """The skills `text` demonstrates, including equivalence images this JD makes reachable.

    The single primitive `build_plan` and `boardwatch.projection` both score with. Extracted from
    `build_plan`'s `cover` closure, which took a `Bullet` because it read a precomputed swap map;
    this takes the text, so a caller holding an entry rather than a bullet can score it too.

    Parameter order mirrors `build_plan`'s — `table` then `taxonomy` — so the two cannot be
    transposed at a call site.
    """
    swaps = _applicable_swaps(text, jd_skills, table)
    return taxonomy.extract(text) | {to for _, to in swaps}
```

Then replace `build_plan`'s closure at `:76-78`. **Read the module attribute at call time**, not the
bare name, so the drift test's `monkeypatch.setattr` is observable:

```python
    def cover(b: Bullet) -> int:
        import boardwatch.tailor.plan as _self

        return len(_self.effective_skills(b.text, jd_skills, table, taxonomy) & jd_skills)
```

Leave `swaps_by_bullet` (`:70-74`) exactly as it is — `:97` still needs it for op emission.

- [ ] **Step 4: Run the new tests, then the whole tailor suite for regressions**

```
uv run pytest tests/unit/test_tailor_plan_effective_skills.py -v --no-cov -n 0
uv run pytest tests/unit -k "tailor or plan" --no-cov -n 0
```

Expected: all pass. The second command is the regression check — `build_plan`'s output must be
byte-identical for every existing fixture.

- [ ] **Step 5: Confirm the test fails without its fix**

Revert only the `cover` body to the original one-liner, keeping `effective_skills` defined. Re-run:

```
uv run pytest tests/unit/test_tailor_plan_effective_skills.py::test_build_plan_routes_through_effective_skills -v --no-cov -n 0
```

Expected: **FAIL on `assert calls`** — specifically that assertion, not the `result.ops` one. If it
fails on `result.ops` instead, the test is proving the wrong thing. Restore the fix.

- [ ] **Step 6: Run the full gate**

```
make check
```

Expected: exit 0. Capture the real exit code; do not pipe through `head`/`tail`.

- [ ] **Step 7: Commit**

```bash
git add src/boardwatch/tailor/plan.py tests/unit/test_tailor_plan_effective_skills.py
git commit -m "Extract a public effective_skills so projection and build_plan score alike"
```

---

# Slice P1 — the declaration, its contract, and the owner gate

**Gate:** every §7 rule has a failing-then-passing test; decline and non-TTY each tested.

---

### Task 2: The error catalog

**Files:**
- Create: `src/boardwatch/projection/__init__.py`, `src/boardwatch/projection/errors.py`
- Test: `tests/projection/test_projection_errors.py`
- Create: `tests/projection/conftest.py` (empty for now; Task 5 fills it)

**Interfaces:**
- Produces: `ProjectionError`, `ProjectionIssue` (StrEnum), `ProjectionViolation` (frozen dataclass), `raise_violation(...)`.

- [ ] **Step 1: Write the failing test**

```python
"""The projection package's closed reason catalog."""

from __future__ import annotations

import pytest

from boardwatch.projection.errors import (
    ProjectionError,
    ProjectionIssue,
    ProjectionViolation,
    raise_violation,
)


def test_every_issue_is_a_string_valued_member() -> None:
    """Derived from the enum itself, so a member added without a value fails here."""
    assert len(list(ProjectionIssue)) >= 12
    for issue in ProjectionIssue:
        assert isinstance(issue.value, str) and issue.value


def test_a_violation_carries_its_typed_issue_not_a_message_to_grep() -> None:
    with pytest.raises(ProjectionError) as exc:
        raise_violation(
            ProjectionIssue.UNRESOLVED_PLACEHOLDER, "nope", where="projection.yaml:12"
        )
    assert exc.value.violation.issue is ProjectionIssue.UNRESOLVED_PLACEHOLDER
    assert exc.value.violation.where == "projection.yaml:12"


def test_the_violation_record_is_frozen() -> None:
    v = ProjectionViolation(issue=ProjectionIssue.UNRESOLVED_PLACEHOLDER, message="m", where="w")
    with pytest.raises(Exception):
        v.message = "other"  # type: ignore[misc]
```

- [ ] **Step 2: Run it to verify it fails**

```
uv run pytest tests/projection/test_projection_errors.py -v --no-cov -n 0
```

Expected: `ModuleNotFoundError: No module named 'boardwatch.projection'`.

- [ ] **Step 3: Write the implementation**

`src/boardwatch/projection/errors.py`:

```python
"""Typed projection failures. Every arm of the fidelity contract has a member here.

A reason is a `StrEnum` member carried as a keyword-only payload on the exception, following
`LLMLaneDeadError` (`llm/client.py:41-53`) — never a message a caller string-matches. The catalog
is CLOSED: a condition it does not name is a defect in this file, not a new bucket.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import NoReturn


class ProjectionIssue(StrEnum):
    """Everything projection can refuse for. Closed."""

    # -- declaration ------------------------------------------------------------------
    UNKNOWN_ENTRY_KIND = "unknown_entry_kind"
    DUPLICATE_ENTITY_ID = "duplicate_entity_id"
    UNRESOLVED_PLACEHOLDER = "unresolved_placeholder"
    MALFORMED_PLACEHOLDER = "malformed_placeholder"
    MISSING_OPEN_RANGE_LABEL = "missing_open_range_label"
    # -- fallback ---------------------------------------------------------------------
    FALLBACK_ID_NOT_A_CANDIDATE = "fallback_id_not_a_candidate"
    FALLBACK_ID_DUPLICATED = "fallback_id_duplicated"
    FALLBACK_OVERLAPS_PINNED = "fallback_overlaps_pinned"
    # -- bundle references ------------------------------------------------------------
    UNKNOWN_BUNDLE_ID = "unknown_bundle_id"
    FACT_NOT_RESUME_SURFACED = "fact_not_resume_surfaced"
    FACT_NOT_EFFECTIVE = "fact_not_effective"
    FACT_EXPIRED = "fact_expired"
    FACT_VALUE_KIND_NOT_ADMITTED = "fact_value_kind_not_admitted"
    CLAIM_NOT_APPROVED = "claim_not_approved"
    CLAIM_NOT_RESUME_SURFACED = "claim_not_resume_surfaced"
    CLAIM_SUBJECT_MISMATCH = "claim_subject_mismatch"
    SKILL_NOT_RESUME_SURFACED = "skill_not_resume_surfaced"
    BULLET_TEXT_ALTERED = "bullet_text_altered"
    # -- shell ------------------------------------------------------------------------
    SHELL_SOURCE_UNREADABLE = "shell_source_unreadable"
    # -- persona ----------------------------------------------------------------------
    PERSONA_DECLARES_ENTRIES = "persona_declares_entries"
    # -- owner gate -------------------------------------------------------------------
    MISSING_PROJECTION_APPROVAL = "missing_projection_approval"
    # -- selection --------------------------------------------------------------------
    PINNED_SET_EXCEEDS_BUDGET = "pinned_set_exceeds_budget"
    COMPILE_INFRASTRUCTURE_FAILURE = "compile_infrastructure_failure"
    NO_JD_EXTRACTION = "no_jd_extraction"


@dataclass(frozen=True)
class ProjectionViolation:
    """One refusal. `where` locates it — a declaration line, a record id, or an option name."""

    issue: ProjectionIssue
    message: str
    where: str


class ProjectionError(Exception):
    """Base for every typed projection failure. Carries the violation, never just prose."""

    def __init__(self, violation: ProjectionViolation) -> None:
        super().__init__(f"{violation.issue}: {violation.message} ({violation.where})")
        self.violation = violation


def raise_violation(issue: ProjectionIssue, message: str, *, where: str) -> NoReturn:
    """The one construction site, so a caller cannot invent an untyped refusal."""
    raise ProjectionError(ProjectionViolation(issue=issue, message=message, where=where))
```

`src/boardwatch/projection/__init__.py`:

```python
"""Bundle-to-résumé projection: the Gate B bridge, as a package outside both walls.

`boardwatch.projection` imports BOTH `boardwatch.profile_bundle` (to read) and `boardwatch.tailor`
(to construct and validate a `Resume`). That is legal precisely because this package is in neither
root set of `tests/profile_bundle/test_profile_bundle_tailor_isolation.py`, whose two assertions
walk OUTWARD from `boardwatch/tailor/**` and `boardwatch/profile_bundle/**`.

Two consequences, both load-bearing:

- This package must stay at `boardwatch/projection/`. Moving it under `boardwatch/tailor/` would
  make it a tailor root and the wall would fail on its first import.
- **No module in the tailor closure may import this package** — 58 modules, including
  `reports/tailor.py`, `core/settings.py` and `cli/context.py`. `cli/app.py` is outside the closure,
  which is why the CLI may register these commands.
"""

from boardwatch.projection.errors import ProjectionError, ProjectionIssue, ProjectionViolation

__all__ = ["ProjectionError", "ProjectionIssue", "ProjectionViolation"]
```

- [ ] **Step 4: Run the tests to verify they pass**

```
uv run pytest tests/projection/test_projection_errors.py -v --no-cov -n 0
```

Expected: 3 passed.

- [ ] **Step 5: Prove the wall still holds, with the new package on disk**

```
uv run pytest tests/profile_bundle/test_profile_bundle_tailor_isolation.py -v --no-cov -n 0
```

Expected: 13 passed. This is the whole reason the package sits at top level; run it now, before any
import edges exist, so a later failure is unambiguously caused by the edge that introduced it.

- [ ] **Step 6: Commit**

```bash
git add src/boardwatch/projection tests/projection
git commit -m "Add the projection package root and its closed refusal catalog"
```

---

### Task 3: The `projection.yaml` model and its closed catalogs

**Files:**
- Create: `src/boardwatch/projection/declaration.py`
- Test: `tests/projection/test_projection_declaration.py`

**Interfaces:**
- Consumes: `ProjectionIssue`, `raise_violation` (Task 2).
- Produces:
  - `EntryDeclaration` — frozen model: `entity_id: str`, `kind: EntryKind`, `pinned: bool`, `heading: str`, `title: str | None`, `subtitle: str | None`, `dates: str | None`, `location: str | None`, `claims: tuple[str, ...]`
  - `SkillGroupDeclaration` — `label: str`, `skills: tuple[str, ...]`
  - `ProjectionDeclaration` — `projection_version: int`, `skill_groups`, `entries`, `no_match_fallback`, `extracurricular`, `shell_source: Path`, `open_range_label: str`
  - `EntryKind` — `StrEnum{EXPERIENCE, PROJECT}`
  - `load_declaration(path: Path) -> ProjectionDeclaration`
  - `projection_digest(declaration: ProjectionDeclaration) -> str`

Two facts to build on. `Entry.kind` is an **open `str` with a default** (`tailor/model.py:38`) and
nothing in `src/` validates it, so this catalog is the only thing standing between a typo and an
entry that silently vanishes from the PDF. And `canonical.digest_of` **refuses floats and non-string
mapping keys** (`canonical.py:136-154`), so the digest input must carry neither.

- [ ] **Step 1: Write the failing test**

```python
"""`projection.yaml`: closed catalogs, and a digest that moves when content moves."""

from __future__ import annotations

from pathlib import Path

import pytest

from boardwatch.projection.declaration import (
    EntryKind,
    load_declaration,
    projection_digest,
)
from boardwatch.projection.errors import ProjectionError, ProjectionIssue

MINIMAL = """\
projection_version: 1
shell_source: {shell}
open_range_label: Present
skill_groups:
  - label: Languages
    skills: [skill.example-language]
entries:
  - entity_id: project.packet-pantry
    kind: project
    pinned: true
    heading: '{{@display_name}}'
    claims: [claim.packet-pantry.backend.001]
no_match_fallback: []
extracurricular: []
"""


def _write(tmp_path: Path, body: str) -> Path:
    shell = tmp_path / "master_resume.yaml"
    shell.write_text("header: []\neducation: []\n", encoding="utf-8")
    path = tmp_path / "projection.yaml"
    path.write_text(body.format(shell=shell.as_posix()), encoding="utf-8")
    return path


def test_a_minimal_declaration_loads(tmp_path: Path) -> None:
    decl = load_declaration(_write(tmp_path, MINIMAL))
    assert decl.projection_version == 1
    assert decl.entries[0].kind is EntryKind.PROJECT
    assert decl.entries[0].pinned is True
    assert decl.open_range_label == "Present"


def test_an_out_of_catalog_kind_is_fatal_and_names_the_entity(tmp_path: Path) -> None:
    """The catalog exists because `Entry.kind` is an open `str` and an out-of-catalog value
    makes the renderer drop the entry from the PDF silently (`tailor/render/latex.py:155,170`)."""
    body = MINIMAL.replace("kind: project", "kind: publication")
    with pytest.raises(ProjectionError) as exc:
        load_declaration(_write(tmp_path, body))
    assert exc.value.violation.issue is ProjectionIssue.UNKNOWN_ENTRY_KIND
    assert "project.packet-pantry" in exc.value.violation.where


def test_a_duplicated_entity_id_is_fatal(tmp_path: Path) -> None:
    """Without this, `entry_id = "entry." + entity_id` is not total and the failure surfaces
    much later as the frozen model's bare `duplicate entry_id` with no projection context."""
    body = MINIMAL + """\
  - entity_id: project.packet-pantry
    kind: project
    pinned: false
    heading: 'Again'
    claims: []
"""
    # The second entry must attach to the `entries:` list, so rebuild rather than concatenate.
    body = MINIMAL.replace(
        "no_match_fallback: []",
        "  - entity_id: project.packet-pantry\n"
        "    kind: project\n"
        "    pinned: false\n"
        "    heading: 'Again'\n"
        "    claims: []\n"
        "no_match_fallback: []",
    )
    with pytest.raises(ProjectionError) as exc:
        load_declaration(_write(tmp_path, body))
    assert exc.value.violation.issue is ProjectionIssue.DUPLICATE_ENTITY_ID


def test_a_missing_open_range_label_is_fatal(tmp_path: Path) -> None:
    """No default: `end: null` has to render as the owner's own word, and inventing one would
    put authored English in code."""
    body = MINIMAL.replace("open_range_label: Present\n", "")
    with pytest.raises(ProjectionError) as exc:
        load_declaration(_write(tmp_path, body))
    assert exc.value.violation.issue is ProjectionIssue.MISSING_OPEN_RANGE_LABEL


def test_the_digest_changes_when_a_template_literal_changes(tmp_path: Path) -> None:
    """This is what reopens the owner gate. Editing a literal must not keep the old approval."""
    first = projection_digest(load_declaration(_write(tmp_path, MINIMAL)))
    changed = MINIMAL.replace("{{@display_name}}", "Senior {{@display_name}}")
    second = projection_digest(load_declaration(_write(tmp_path, changed)))
    assert first != second
    assert first.startswith("sha256:")


def test_the_digest_is_stable_across_formatting(tmp_path: Path) -> None:
    """Non-vacuity for the test above: the digest tracks content, not bytes."""
    first = projection_digest(load_declaration(_write(tmp_path, MINIMAL)))
    reflowed = MINIMAL.replace("skills: [skill.example-language]", "skills:\n      - skill.example-language")
    second = projection_digest(load_declaration(_write(tmp_path, reflowed)))
    assert first == second
```

- [ ] **Step 2: Run it to verify it fails**

```
uv run pytest tests/projection/test_projection_declaration.py -v --no-cov -n 0
```

Expected: `ModuleNotFoundError: No module named 'boardwatch.projection.declaration'`.

- [ ] **Step 3: Write the implementation**

`src/boardwatch/projection/declaration.py`:

```python
"""`{config_dir}/projection.yaml` — the owner's editorial declaration.

It lives OUTSIDE the bundle on purpose: "which entries appear, in what order" is a rendering
decision, and the bundle design warns against encoding renderer decisions into the knowledge
schema.

`kind` is declared, never derived. A volunteer role is an `affiliation` in the bundle and belongs
under Experience on the page — entity type is knowledge, section placement is editorial.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from boardwatch.profile_bundle.canonical import digest_of
from boardwatch.projection.errors import ProjectionIssue, raise_violation


class EntryKind(StrEnum):
    """The closed catalog `Entry.kind` should have had.

    `tailor/model.py:38` types `kind` as an open `str` with a default, and BOTH renderer section
    filters are equality tests (`tailor/render/latex.py:155`, `:170`) — so a third value matches
    neither section and the entry is silently omitted from the PDF entirely. Nothing else in
    `src/` validates it. This enum is the only guard.
    """

    EXPERIENCE = "experience"
    PROJECT = "project"


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SkillGroupDeclaration(_Strict):
    """`skills` are bundle skill IDs, not display strings.

    `tailor.model.SkillGroup` has `label` + `items: list[str]`, and `items` holds rendered text.
    The id-to-text mapping is `pool.py`'s, through `SkillRecord.canonical_name`.
    """

    label: str = Field(min_length=1)
    skills: tuple[str, ...] = Field(min_length=1)


class EntryDeclaration(_Strict):
    entity_id: str = Field(min_length=1)
    kind: EntryKind
    pinned: bool
    heading: str = Field(min_length=1)
    title: str | None = None
    subtitle: str | None = None
    dates: str | None = None
    location: str | None = None
    claims: tuple[str, ...] = ()


class ProjectionDeclaration(_Strict):
    projection_version: int
    shell_source: Path
    open_range_label: str = Field(min_length=1)
    skill_groups: tuple[SkillGroupDeclaration, ...] = ()
    entries: tuple[EntryDeclaration, ...] = ()
    no_match_fallback: tuple[str, ...] = ()
    extracurricular: tuple[str, ...] = ()

    @property
    def pinned_ids(self) -> tuple[str, ...]:
        return tuple(e.entity_id for e in self.entries if e.pinned)

    @property
    def candidate_ids(self) -> tuple[str, ...]:
        return tuple(e.entity_id for e in self.entries if not e.pinned)


def load_declaration(path: Path) -> ProjectionDeclaration:
    """Parse and validate. Every refusal is typed and names the offending declaration."""
    if not path.is_file():
        raise_violation(
            ProjectionIssue.SHELL_SOURCE_UNREADABLE,
            "no projection declaration at this path",
            where=path.name,
        )
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise_violation(
            ProjectionIssue.MALFORMED_PLACEHOLDER, f"invalid YAML: {exc}", where=path.name
        )
    if not isinstance(raw, dict):
        raise_violation(
            ProjectionIssue.MALFORMED_PLACEHOLDER,
            "the declaration must be a mapping",
            where=path.name,
        )

    # Checked before model validation so the owner gets the specific refusal rather than
    # pydantic's "field required" for a field whose absence is a deliberate design rule.
    if not raw.get("open_range_label"):
        raise_violation(
            ProjectionIssue.MISSING_OPEN_RANGE_LABEL,
            "open_range_label has no default: the word for 'still going' is the owner's, "
            "not ours, and a date range with `end: null` cannot render without it",
            where=path.name,
        )

    _reject_unknown_kinds(raw, path)

    try:
        declaration = ProjectionDeclaration.model_validate(raw)
    except ValidationError as exc:
        raise_violation(
            ProjectionIssue.MALFORMED_PLACEHOLDER, str(exc), where=path.name
        )

    _reject_duplicate_entities(declaration, path)
    _reject_bad_fallback(declaration, path)
    return declaration


def _reject_unknown_kinds(raw: dict[str, Any], path: Path) -> None:
    """Pre-model, so the refusal can name the entity rather than a list index."""
    legal = {k.value for k in EntryKind}
    for declared in raw.get("entries") or []:
        if not isinstance(declared, dict):
            continue
        kind = declared.get("kind")
        if kind not in legal:
            raise_violation(
                ProjectionIssue.UNKNOWN_ENTRY_KIND,
                f"kind {kind!r} is not in the closed catalog {sorted(legal)}; the renderer "
                "filters sections by equality, so an out-of-catalog kind would drop this "
                "entry from the PDF with no error",
                where=f"{path.name}: {declared.get('entity_id')}",
            )


def _reject_duplicate_entities(declaration: ProjectionDeclaration, path: Path) -> None:
    """`entry_id = "entry." + entity_id` is only total if entity ids are unique here."""
    seen: set[str] = set()
    for entry in declaration.entries:
        if entry.entity_id in seen:
            raise_violation(
                ProjectionIssue.DUPLICATE_ENTITY_ID,
                f"{entry.entity_id} is declared more than once",
                where=f"{path.name}: {entry.entity_id}",
            )
        seen.add(entry.entity_id)


def _reject_bad_fallback(declaration: ProjectionDeclaration, path: Path) -> None:
    """Without these three, a pinned id in the fallback duplicates an entry and fails late as
    the frozen model's bare `duplicate entry_id`, and an undeclared id is a KeyError."""
    candidates = set(declaration.candidate_ids)
    pinned = set(declaration.pinned_ids)
    seen: set[str] = set()
    for fid in declaration.no_match_fallback:
        if fid in seen:
            raise_violation(
                ProjectionIssue.FALLBACK_ID_DUPLICATED, f"{fid} appears twice", where=path.name
            )
        seen.add(fid)
        if fid in pinned:
            raise_violation(
                ProjectionIssue.FALLBACK_OVERLAPS_PINNED,
                f"{fid} is pinned, so it always renders; listing it as a fallback would "
                "emit it twice",
                where=path.name,
            )
        if fid not in candidates:
            raise_violation(
                ProjectionIssue.FALLBACK_ID_NOT_A_CANDIDATE,
                f"{fid} is not a declared candidate entry",
                where=path.name,
            )


def projection_digest(declaration: ProjectionDeclaration) -> str:
    """`sha256:<hex>` over the declaration's canonical content.

    Reuses the bundle's own canonicaliser: NFC-normalised, key-sorted, float-refusing. Content,
    not bytes — reflowing the YAML must not reopen the owner's approval, but changing a template
    literal must. `mode="json"` is what keeps `Path` and `StrEnum` representable, and what keeps
    tuples out of `digest_of`, which refuses them.
    """
    return digest_of(declaration.model_dump(mode="json"))
```

- [ ] **Step 4: Run the tests to verify they pass**

```
uv run pytest tests/projection/test_projection_declaration.py -v --no-cov -n 0
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/boardwatch/projection/declaration.py tests/projection/test_projection_declaration.py
git commit -m "Add the projection declaration model with closed kind and fallback catalogs"
```

---

### Task 4: Register the example declaration as shipped data

**Files:**
- Create: `src/boardwatch/projection/examples/projection.example.yaml`
- Modify: `tools/generalization/allowlists.py`
- Modify: `tests/generalization/test_inventory.py:55`
- Test: `tests/projection/test_projection_example_data.py`

This task exists because **R7 fails the build on any new data file without a reviewed
`SHIPPED_DATA` entry**, and two hardcoded counters break on the first one added. Doing it as its own
task keeps that failure from being misread as a defect in Task 5.

Note the filename: **`projection.example.yaml`, never `resume.yaml` or anything containing `resume`
or `cv`** — R5 bans those stems on data files, including as a directory segment.

- [ ] **Step 1: Write the failing test**

```python
"""The shipped example declaration is real, loadable, and inventoried."""

from __future__ import annotations

from importlib import resources

from boardwatch.projection.declaration import load_declaration
from tools.generalization import allowlists as al

EXAMPLE = "src/boardwatch/projection/examples/projection.example.yaml"


def test_the_example_is_registered_as_synthetic_shipped_data() -> None:
    entry = al.SHIPPED_DATA.get(EXAMPLE)
    assert entry is not None, f"{EXAMPLE} needs a reviewed SHIPPED_DATA entry (R7)"
    assert entry.kind == "fixture"
    assert entry.provenance == "synthetic"
    assert entry.pin.startswith("sha256:")


def test_the_example_parses_through_the_production_loader() -> None:
    """Delegates rather than re-parsing: a fixture validated by its own path would let the
    fixture agree with itself while disagreeing with what the CLI reads."""
    traversable = resources.files("boardwatch.projection.examples").joinpath(
        "projection.example.yaml"
    )
    with resources.as_file(traversable) as path:
        declaration = load_declaration(path)
    assert declaration.entries
    assert declaration.pinned_ids
    assert declaration.candidate_ids, "the example must exercise BOTH pinned and candidate arms"
```

- [ ] **Step 2: Run it to verify it fails**

```
uv run pytest tests/projection/test_projection_example_data.py -v --no-cov -n 0
```

Expected: FAIL on `assert entry is not None`.

- [ ] **Step 3: Write the example, against the real synthetic bundle's ids**

`src/boardwatch/projection/examples/projection.example.yaml`. Every id below is real in
`profile_bundle/examples/comprehensive/` — verified, not invented:

```yaml
# The example editorial declaration, over the synthetic bundle that ships as package data.
# Synthetic throughout: no owner content, so it runs in CI and the generalization checker stays
# clean. `shell_source` is deliberately relative — the loader resolves it against the config dir.
projection_version: 1
shell_source: master_resume.yaml
open_range_label: Present

skill_groups:
  - label: Languages
    skills:
      - skill.example-language

entries:
  - entity_id: employment.example-labs
    kind: experience
    pinned: true
    heading: '{@display_name}'
    title: '{employment.title}'
    dates: '{employment.date_range}'
    claims:
      - claim.example-labs.ownership.001

  - entity_id: project.packet-pantry
    kind: project
    pinned: false
    heading: '{@display_name}'
    title: '{@display_name}'
    claims:
      - claim.packet-pantry.backend.001

no_match_fallback:
  - project.packet-pantry

extracurricular: []
```

- [ ] **Step 4: Compute the pin and add the inventory entry**

```
uv run python -c "import hashlib,pathlib; p=pathlib.Path('src/boardwatch/projection/examples/projection.example.yaml'); print('sha256:'+hashlib.sha256(p.read_bytes()).hexdigest())"
```

Add to `SHIPPED_DATA` in `tools/generalization/allowlists.py`, using the digest printed above:

```python
    "src/boardwatch/projection/examples/projection.example.yaml": DataEntry(
        kind="fixture",
        reason=(
            "The example editorial declaration for bundle-to-résumé projection, over the "
            "synthetic career-profile bundle. Synthetic throughout, so the golden projection "
            "test runs in CI with no owner content."
        ),
        provenance="synthetic",
        pin="sha256:<paste the digest printed above>",
    ),
```

Create `src/boardwatch/projection/examples/__init__.py` (empty) so `importlib.resources` can
address the directory as a package.

- [ ] **Step 5: Bump the repo-wide data-file counter**

`tests/generalization/test_inventory.py:55` asserts the exact count. Read the current value, run the
checker to learn the new one, and update it:

```
uv run pytest tests/generalization/test_inventory.py -v --no-cov -n 0
```

Expected first: FAIL with `assert 75 == 74`. Change `74` to `75`. Re-run: pass.

- [ ] **Step 6: Verify both gates**

```
uv run python -m tools.generalization; echo "exit=$?"
uv run pytest tests/projection/test_projection_example_data.py tests/generalization -v --no-cov -n 0
```

Expected: generalization exit 0; all tests pass. **If R12 complains the example is not in the
wheel**, confirm `pyproject.toml`'s package-data configuration includes `*.yaml` under
`boardwatch.projection.examples`; every non-`.py` file under `src/boardwatch/` must reach the wheel.

- [ ] **Step 7: Commit**

```bash
git add src/boardwatch/projection/examples tools/generalization/allowlists.py \
        tests/generalization/test_inventory.py tests/projection/test_projection_example_data.py
git commit -m "Ship the example projection declaration and inventory it"
```

---

### Task 5: The placeholder grammar and the ten-arm fact-value renderer

**Files:**
- Create: `src/boardwatch/projection/grammar.py`
- Test: `tests/projection/test_projection_grammar.py`

**Interfaces:**
- Consumes: `ProjectionIssue`, `raise_violation`; `ProjectionDeclaration`.
- Produces:
  - `resolve_template(template: str, *, entity, facts_by_predicate: Mapping[str, FactRecord], open_range_label: str, where: str) -> str`
  - `render_value(value: FactValue, *, open_range_label: str, where: str) -> str`
  - `render_skill(skill: SkillRecord) -> str`
  - `ADMITTED_KINDS: frozenset[FactValueKind]`

Facts to build on, all verified:

- `FactValueKind` has **ten** members (`profile_bundle/models/facts.py:52-61`).
- **There is no uniform `.value` accessor.** Seven arms expose `.value`; `string_list` exposes
  `.values`; `skill_ref` exposes `.skill_id`; `date_range` exposes `.start`/`.end`. `getattr(v, "value")`
  raises on three of ten.
- `DateRangeValue` has exactly `type`/`start`/`end` — **no display member**, `start: date` required,
  `end: date | None`, and ordering is **not** enforced by the model.
- `display_name` is on `_EntityBase` so it is universal; **`status` is absent on `PersonEntity`**
  (`models/entities.py:143-145`) and is ten different enums elsewhere.

- [ ] **Step 1: Write the failing test**

```python
"""The closed placeholder grammar and the ten-arm value renderer."""

from __future__ import annotations

from datetime import date

import pytest

from boardwatch.profile_bundle.models.facts import (
    BooleanValue,
    DateRangeValue,
    DateValue,
    DecimalValue,
    FactValueKind,
    IntegerValue,
    SkillRefValue,
    StringListValue,
    StringValue,
    UrlValue,
    YearMonthValue,
)
from boardwatch.projection.errors import ProjectionError, ProjectionIssue
from boardwatch.projection.grammar import ADMITTED_KINDS, render_value


def test_the_renderer_covers_every_kind_the_enum_declares() -> None:
    """Derived from `FactValueKind`, never restated. An eleventh member added to the bundle
    must fail here rather than fall through to an unrendered placeholder — this repo's own
    rule: a derived check must read the emitter's constants."""
    declared = set(FactValueKind)
    assert len(declared) == 10, "the bundle's value union changed; revisit the render table"
    handled = ADMITTED_KINDS | {
        FactValueKind.BOOLEAN,
        FactValueKind.STRING_LIST,
        FactValueKind.SKILL_REF,
    }
    assert handled == declared


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (StringValue(type="string", value="Example Labs"), "Example Labs"),
        (UrlValue(type="url", value="https://example.com/x"), "https://example.com/x"),
        (DecimalValue(type="decimal", value="8.5"), "8.5"),
        (IntegerValue(type="integer", value=12), "12"),
        (YearMonthValue(type="year_month", value="2026-02"), "2026-02"),
        (DateValue(type="date", value=date(2026, 2, 1)), "2026-02-01"),
        (
            DateRangeValue(type="date_range", start=date(2025, 2, 1), end=date(2026, 1, 31)),
            "2025-02-01 – 2026-01-31",
        ),
    ],
)
def test_each_admitted_kind_has_exactly_one_rendering(value: object, expected: str) -> None:
    assert render_value(value, open_range_label="Present", where="w") == expected  # type: ignore[arg-type]


def test_an_open_range_renders_the_owners_own_word() -> None:
    """`DateRangeValue` has no display member, so this convention is projection-owned. The word
    is the owner's; the ISO formatting is ours."""
    value = DateRangeValue(type="date_range", start=date(2025, 2, 1), end=None)
    assert render_value(value, open_range_label="Present", where="w") == "2025-02-01 – Present"
    assert render_value(value, open_range_label="Current", where="w") == "2025-02-01 – Current"


@pytest.mark.parametrize(
    "value",
    [
        BooleanValue(type="boolean", value=True),
        StringListValue(type="string_list", values=("a", "b")),
        SkillRefValue(type="skill_ref", skill_id="skill.example-language"),
    ],
)
def test_an_unadmitted_kind_is_fatal(value: object) -> None:
    """A list or a boolean on a résumé line is authoring, not projection."""
    with pytest.raises(ProjectionError) as exc:
        render_value(value, open_range_label="Present", where="projection.yaml: entry.x")  # type: ignore[arg-type]
    assert exc.value.violation.issue is ProjectionIssue.FACT_VALUE_KIND_NOT_ADMITTED
```

Add a second test module `tests/projection/test_projection_grammar_templates.py` for the two
namespaces (separate file so the basename stays unique and the value table stays readable):

```python
"""`{predicate}` and `{@field}` — the only two admitted forms."""

from __future__ import annotations

import pytest

from boardwatch.projection.errors import ProjectionError, ProjectionIssue
from boardwatch.projection.grammar import resolve_template


class _Entity:
    entity_type = "project"
    display_name = "Packet Pantry"
    status = "live_public"


class _Person:
    """`PersonEntity` genuinely has no `status` field (`models/entities.py:143-145`), so the stub
    genuinely omits it rather than setting it to None — `getattr` must miss, not find a null."""

    entity_type = "person"
    display_name = "Example Candidate"


def test_an_entity_display_field_resolves() -> None:
    assert (
        resolve_template("{@display_name}", entity=_Entity(), facts_by_predicate={},
                         open_range_label="Present", where="w")
        == "Packet Pantry"
    )


def test_a_literal_the_owner_wrote_is_preserved_around_a_placeholder() -> None:
    """Boardwatch never invents a word; it also never drops one the owner wrote."""
    out = resolve_template(
        "{@display_name} (Volunteer)", entity=_Entity(), facts_by_predicate={},
        open_range_label="Present", where="w",
    )
    assert out == "Packet Pantry (Volunteer)"


def test_an_unknown_namespace_form_is_fatal() -> None:
    with pytest.raises(ProjectionError) as exc:
        resolve_template("{%weird}", entity=_Entity(), facts_by_predicate={},
                         open_range_label="Present", where="projection.yaml:12")
    assert exc.value.violation.issue is ProjectionIssue.MALFORMED_PLACEHOLDER


def test_an_unresolvable_predicate_is_fatal_not_blank() -> None:
    with pytest.raises(ProjectionError) as exc:
        resolve_template("{employment.title}", entity=_Entity(), facts_by_predicate={},
                         open_range_label="Present", where="projection.yaml:12")
    assert exc.value.violation.issue is ProjectionIssue.UNRESOLVED_PLACEHOLDER


def test_status_resolves_on_an_entity_that_has_one() -> None:
    """The positive control for the test below. Without it, a `resolve_template` that refused
    `{@status}` unconditionally would pass — a check that cannot fire reads as coverage."""
    out = resolve_template("{@status}", entity=_Entity(), facts_by_predicate={},
                           open_range_label="Present", where="w")
    assert out == "live_public"


def test_status_on_a_person_entity_is_a_named_refusal_not_an_attribute_error() -> None:
    """`PersonEntity` has no `status` field, deliberately (`models/entities.py:143-145`), so the
    grammar table's `@status` is not universally resolvable and must say so."""
    with pytest.raises(ProjectionError) as exc:
        resolve_template("{@status}", entity=_Person(), facts_by_predicate={},
                         open_range_label="Present", where="projection.yaml:12")
    assert exc.value.violation.issue is ProjectionIssue.UNRESOLVED_PLACEHOLDER
```

- [ ] **Step 2: Run both to verify they fail**

```
uv run pytest tests/projection/test_projection_grammar.py tests/projection/test_projection_grammar_templates.py -v --no-cov -n 0
```

Expected: `ModuleNotFoundError: No module named 'boardwatch.projection.grammar'`.

- [ ] **Step 3: Write the implementation**

`src/boardwatch/projection/grammar.py`:

```python
"""The closed placeholder grammar, and the one rendering each admitted fact value gets.

Rendering is projection-owned and specified HERE rather than deferred, because the alternative is
that whoever implements it invents `2025-02-01 – Present` versus `Feb 2025 – Present` and a golden
test blesses whichever convention they happened to pick.

There is no uniform accessor on `FactValue`: seven of ten arms expose `.value`, `string_list`
exposes `.values`, `skill_ref` exposes `.skill_id`, and `date_range` exposes `.start`/`.end`. So
this dispatches on type, and a test derives the arm set from `FactValueKind` so an eleventh member
cannot slip through as an unrendered placeholder.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from boardwatch.profile_bundle.models.facts import (
    DateRangeValue,
    DateValue,
    DecimalValue,
    FactRecord,
    FactValue,
    FactValueKind,
    IntegerValue,
    StringValue,
    UrlValue,
    YearMonthValue,
)
from boardwatch.profile_bundle.models.skills import SkillRecord
from boardwatch.projection.errors import ProjectionIssue, raise_violation

#: The en-dash separator for a date range. One convention, one place.
RANGE_SEPARATOR = " – "

#: Kinds a template may carry. `boolean`, `string_list` and `skill_ref` are excluded: a list or a
#: boolean on a résumé line is authoring, not projection.
ADMITTED_KINDS: frozenset[FactValueKind] = frozenset(
    {
        FactValueKind.STRING,
        FactValueKind.INTEGER,
        FactValueKind.DECIMAL,
        FactValueKind.DATE,
        FactValueKind.YEAR_MONTH,
        FactValueKind.DATE_RANGE,
        FactValueKind.URL,
    }
)

#: `{predicate}` or `{@field}`. Nothing else is admitted.
_PLACEHOLDER_RE = re.compile(r"\{([^{}]*)\}")
_PREDICATE_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
_FIELD_RE = re.compile(r"^@([a-z][a-z0-9_]*)$")

#: Entity display fields the `{@…}` namespace admits. `status` is NOT universal — `PersonEntity`
#: has none — so resolution checks the instance, not this set alone.
_DISPLAY_FIELDS: frozenset[str] = frozenset({"display_name", "status"})


def render_value(value: FactValue, *, open_range_label: str, where: str) -> str:
    """One rendering per admitted kind. An unadmitted kind is fatal, never a best effort."""
    if isinstance(value, StringValue | UrlValue):
        return value.value
    if isinstance(value, DecimalValue):
        # The model stores a DecimalString, so this is already exact — no rounding, no unit.
        return value.value
    if isinstance(value, IntegerValue):
        # NOT verbatim: the loader normalises, so a legal `+12` input arrives here as 12.
        return str(value.value)
    if isinstance(value, YearMonthValue):
        return value.value
    if isinstance(value, DateValue):
        return value.value.isoformat()
    if isinstance(value, DateRangeValue):
        end = value.end.isoformat() if value.end is not None else open_range_label
        return f"{value.start.isoformat()}{RANGE_SEPARATOR}{end}"
    raise_violation(
        ProjectionIssue.FACT_VALUE_KIND_NOT_ADMITTED,
        f"a {value.type!r} value cannot be rendered on a résumé line; admitted kinds are "
        f"{sorted(k.value for k in ADMITTED_KINDS)}",
        where=where,
    )


def render_skill(skill: SkillRecord) -> str:
    """A skill id becomes its canonical name.

    The spec's `projection.yaml` declares `skills:` as bundle IDs while `tailor.model.SkillGroup`
    carries `items: list[str]` of rendered text; this is the mapping between them, and it was
    unspecified.
    """
    return skill.canonical_name


def resolve_template(
    template: str,
    *,
    entity: Any,
    facts_by_predicate: Mapping[str, FactRecord],
    open_range_label: str,
    where: str,
) -> str:
    """Substitute fact values and entity display fields. Everything else is the owner's own text.

    Unresolved is FATAL. A blank substitution would put a half-built line on a résumé, and the
    projected document becomes Tier A's ground truth — a gap introduced here is not caught
    downstream, it becomes the truth.
    """

    def one(match: re.Match[str]) -> str:
        token = match.group(1)
        field = _FIELD_RE.match(token)
        if field is not None:
            name = field.group(1)
            if name not in _DISPLAY_FIELDS:
                raise_violation(
                    ProjectionIssue.MALFORMED_PLACEHOLDER,
                    f"{{@{name}}} is not an entity display field; admitted: "
                    f"{sorted(_DISPLAY_FIELDS)}",
                    where=where,
                )
            resolved = getattr(entity, name, None)
            if resolved is None:
                raise_violation(
                    ProjectionIssue.UNRESOLVED_PLACEHOLDER,
                    f"{{@{name}}} does not resolve on a "
                    f"{getattr(entity, 'entity_type', 'unknown')!r} entity; `status` in "
                    "particular is absent on `person` by design",
                    where=where,
                )
            return str(getattr(resolved, "value", resolved))
        if _PREDICATE_RE.match(token) is None:
            raise_violation(
                ProjectionIssue.MALFORMED_PLACEHOLDER,
                f"{{{token}}} is neither a predicate nor an @display field",
                where=where,
            )
        fact = facts_by_predicate.get(token)
        if fact is None:
            raise_violation(
                ProjectionIssue.UNRESOLVED_PLACEHOLDER,
                f"no résumé-surfaced, effective fact with predicate {token!r} on this entity",
                where=where,
            )
        return render_value(fact.value, open_range_label=open_range_label, where=where)

    return _PLACEHOLDER_RE.sub(one, template)
```

- [ ] **Step 4: Run both test modules to verify they pass**

```
uv run pytest tests/projection/test_projection_grammar.py tests/projection/test_projection_grammar_templates.py -v --no-cov -n 0
```

Expected: all pass, including the ten-member derivation.

- [ ] **Step 5: Confirm the derivation test is not vacuous**

Temporarily remove `FactValueKind.URL` from `ADMITTED_KINDS`. Re-run:

```
uv run pytest tests/projection/test_projection_grammar.py::test_the_renderer_covers_every_kind_the_enum_declares -v --no-cov -n 0
```

Expected: **FAIL on `assert handled == declared`** — that assertion specifically, not the
`len(declared) == 10` one above it. Restore.

- [ ] **Step 6: Commit**

```bash
git add src/boardwatch/projection/grammar.py tests/projection/test_projection_grammar.py \
        tests/projection/test_projection_grammar_templates.py
git commit -m "Specify the projection placeholder grammar and one rendering per admitted value kind"
```

---

### Task 6: The fidelity contract — the simple-lookup rows

**Files:**
- Create: `src/boardwatch/projection/contract.py`
- Test: `tests/projection/test_projection_contract.py`
- Create/extend: `tests/projection/conftest.py`

**Interfaces:**
- Produces: `check_references(declaration, ctx) -> None` — raises on the first violation. Covers the
  §7 rows that are lookups: every id exists; claim `status: approved`; claim résumé-surfaced;
  **claim `subject_id` equals the entry's `entity_id`**; skill résumé-surfaced; fact résumé-surfaced.

The effectiveness and expiry rows are **Task 8**, deliberately separate — see the preflight's finding
that implementing the surface row through `eligible_fact_surfaces` makes the effectiveness row's test
pass vacuously.

The conftest this task creates:

```python
"""Projection fixtures. The bundle comes from the profile_bundle fixtures, never re-parsed here.

Imported as `from tests.projection.conftest import ...` — never `from conftest import`, which binds
whichever conftest loaded first.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from boardwatch.profile_bundle.validation.context import context_from_documents
from tests.profile_bundle.conftest import materialise, parse_documents


@pytest.fixture
def bundle_ctx(tmp_path: Path):  # type: ignore[no-untyped-def]
    """A ValidationContext over the packaged synthetic bundle.

    The packaged example is a DRAFT with `bundle_digest: ''` and no blobs, so
    `read_current_once` cannot reach it — `materialise` is what turns it into a usable tree.
    """
    root = tmp_path / "career-profile"
    root.mkdir()
    (root / "drafts").mkdir()
    bundle = materialise(root)
    documents = parse_documents(bundle.draft)
    return context_from_documents(documents, root=bundle.draft, mode="draft", bundle_root=root)
```

- [ ] **Step 1: Write the failing test** — one case per row, each naming its issue

```python
"""§7's lookup rows. Every arm fatal, every arm with its own failing case."""

from __future__ import annotations

import pytest

from boardwatch.projection.contract import check_references
from boardwatch.projection.errors import ProjectionError, ProjectionIssue
from tests.projection.conftest import bundle_ctx  # noqa: F401  (fixture re-export)


def _declaration(**overrides):  # type: ignore[no-untyped-def]
    """Built in code against real synthetic ids, so a bundle change breaks this loudly."""
    from boardwatch.projection.declaration import (
        EntryDeclaration,
        EntryKind,
        ProjectionDeclaration,
    )

    base = dict(
        projection_version=1,
        shell_source="master_resume.yaml",
        open_range_label="Present",
        entries=(
            EntryDeclaration(
                entity_id="project.packet-pantry",
                kind=EntryKind.PROJECT,
                pinned=True,
                heading="{@display_name}",
                claims=("claim.packet-pantry.backend.001",),
            ),
        ),
    )
    base.update(overrides)
    return ProjectionDeclaration.model_validate(base)


def test_the_real_synthetic_declaration_passes(bundle_ctx) -> None:  # noqa: F811
    """The positive control. Without it every refusal below could be a false positive."""
    check_references(_declaration(), bundle_ctx)


def test_an_unknown_entity_id_is_fatal(bundle_ctx) -> None:  # noqa: F811
    from boardwatch.projection.declaration import EntryDeclaration, EntryKind

    decl = _declaration(
        entries=(
            EntryDeclaration(
                entity_id="project.does-not-exist",
                kind=EntryKind.PROJECT,
                pinned=True,
                heading="x",
                claims=(),
            ),
        )
    )
    with pytest.raises(ProjectionError) as exc:
        check_references(decl, bundle_ctx)
    assert exc.value.violation.issue is ProjectionIssue.UNKNOWN_BUNDLE_ID


def test_a_draft_claim_is_fatal(bundle_ctx) -> None:  # noqa: F811
    """`claim.packet-pantry.draft.001` really is `status: draft` with `allowed_surfaces: []`."""
    from boardwatch.projection.declaration import EntryDeclaration, EntryKind

    decl = _declaration(
        entries=(
            EntryDeclaration(
                entity_id="project.packet-pantry",
                kind=EntryKind.PROJECT,
                pinned=True,
                heading="x",
                claims=("claim.packet-pantry.draft.001",),
            ),
        )
    )
    with pytest.raises(ProjectionError) as exc:
        check_references(decl, bundle_ctx)
    assert exc.value.violation.issue in {
        ProjectionIssue.CLAIM_NOT_APPROVED,
        ProjectionIssue.CLAIM_NOT_RESUME_SURFACED,
    }


def test_a_claim_belonging_to_another_entity_is_fatal(bundle_ctx) -> None:  # noqa: F811
    """The row that closes revision 1's worst hole: an approved, résumé-surfaced claim about a
    DIFFERENT entity passed every other rule and would have printed one project's
    accomplishment under another employer."""
    from boardwatch.projection.declaration import EntryDeclaration, EntryKind

    decl = _declaration(
        entries=(
            EntryDeclaration(
                entity_id="employment.example-labs",
                kind=EntryKind.EXPERIENCE,
                pinned=True,
                heading="x",
                claims=("claim.packet-pantry.backend.001",),  # subject is the PROJECT
            ),
        )
    )
    with pytest.raises(ProjectionError) as exc:
        check_references(decl, bundle_ctx)
    assert exc.value.violation.issue is ProjectionIssue.CLAIM_SUBJECT_MISMATCH


def test_an_unknown_skill_id_is_fatal(bundle_ctx) -> None:  # noqa: F811
    from boardwatch.projection.declaration import SkillGroupDeclaration

    decl = _declaration(
        skill_groups=(SkillGroupDeclaration(label="Languages", skills=("skill.nope",)),)
    )
    with pytest.raises(ProjectionError) as exc:
        check_references(decl, bundle_ctx)
    assert exc.value.violation.issue is ProjectionIssue.UNKNOWN_BUNDLE_ID
```

- [ ] **Step 2: Run to verify it fails**

```
uv run pytest tests/projection/test_projection_contract.py -v --no-cov -n 0
```

Expected: `ModuleNotFoundError: No module named 'boardwatch.projection.contract'`.

- [ ] **Step 3: Write the implementation**

`src/boardwatch/projection/contract.py`:

```python
"""§7's fidelity contract. Every row is fatal; nothing degrades.

Refusing costs nothing — the authored `resume.yaml` still works and the daily driver is unaffected
— while emitting a partial document costs everything, because the projected document becomes Tier
A's ground truth. `output_is_entailed` compares the tailored résumé against the master, so a
fabrication introduced by PROJECTION is not caught downstream: it becomes the truth.
"""

from __future__ import annotations

from boardwatch.profile_bundle.models.base import Surface
from boardwatch.profile_bundle.models.claims import ClaimStatus
from boardwatch.profile_bundle.validation.context import ValidationContext
from boardwatch.projection.declaration import ProjectionDeclaration
from boardwatch.projection.errors import ProjectionIssue, raise_violation


def check_references(declaration: ProjectionDeclaration, ctx: ValidationContext) -> None:
    """Every id resolves, every claim is the owner's and this entity's, every skill may surface."""
    claims = {c.claim_id: c for c in ctx.index.claims}
    skills = {s.skill_id: s for s in ctx.index.skills}

    for group in declaration.skill_groups:
        for skill_id in group.skills:
            skill = skills.get(skill_id)
            if skill is None:
                raise_violation(
                    ProjectionIssue.UNKNOWN_BUNDLE_ID,
                    f"no skill {skill_id!r} in the bundle",
                    where=f"skill_groups: {group.label}",
                )
            if Surface.RESUME not in skill.allowed_surfaces:
                raise_violation(
                    ProjectionIssue.SKILL_NOT_RESUME_SURFACED,
                    f"{skill_id!r} is valid but not résumé-surfaced",
                    where=f"skill_groups: {group.label}",
                )

    for entry in declaration.entries:
        where = f"entries: {entry.entity_id}"
        if entry.entity_id not in ctx.index.entities:
            raise_violation(
                ProjectionIssue.UNKNOWN_BUNDLE_ID,
                f"no entity {entry.entity_id!r} in the bundle",
                where=where,
            )
        for claim_id in entry.claims:
            claim = claims.get(claim_id)
            if claim is None:
                raise_violation(
                    ProjectionIssue.UNKNOWN_BUNDLE_ID,
                    f"no claim {claim_id!r} in the bundle",
                    where=where,
                )
            if claim.status is not ClaimStatus.APPROVED:
                raise_violation(
                    ProjectionIssue.CLAIM_NOT_APPROVED,
                    f"{claim_id!r} is {claim.status.value!r}, not approved",
                    where=where,
                )
            if Surface.RESUME not in claim.allowed_surfaces:
                raise_violation(
                    ProjectionIssue.CLAIM_NOT_RESUME_SURFACED,
                    f"{claim_id!r} is approved but not résumé-surfaced",
                    where=where,
                )
            if claim.subject_id != entry.entity_id:
                raise_violation(
                    ProjectionIssue.CLAIM_SUBJECT_MISMATCH,
                    f"{claim_id!r} is about {claim.subject_id!r}, so printing it here would "
                    f"attribute one entity's accomplishment to {entry.entity_id!r}",
                    where=where,
                )
```

- [ ] **Step 4: Run the tests**

```
uv run pytest tests/projection/test_projection_contract.py -v --no-cov -n 0
```

Expected: 5 passed, positive control included.

- [ ] **Step 5: Add the outside-fact test that justifies the `kind` catalog**

New file `tests/projection/test_projection_kind_is_load_bearing.py`. This is the corrected version
of the spec's §4.1 claim: an out-of-catalog `kind` does **not** fall through to Experience.

```python
"""Why `EntryKind` is a closed catalog: the renderer drops what it cannot section.

The design said an out-of-catalog `kind` "falls through to Experience", so a typo "would render
silently". It does not. BOTH section filters are equality tests, so the entry matches neither and
vanishes from the PDF with no error at all. This test pins the real behaviour as an OUTSIDE fact,
so if the renderer ever gains a fall-through the catalog's rationale is revisited deliberately.
"""

from __future__ import annotations

from boardwatch.tailor.model import Bullet, Entry, Resume
from boardwatch.tailor.render.latex import LatexRenderer


def _resume(kind: str) -> Resume:
    return Resume(
        header=["Example Candidate", "candidate@example.com"],
        education=["Example University"],
        skill_groups=[],
        entries=[
            Entry(
                entry_id="entry.one",
                heading="Findable Heading",
                kind=kind,
                title="Findable Title",
                bullets=[Bullet(bullet_id="b1", text="A findable bullet sentence")],
            )
        ],
    )


def test_an_out_of_catalog_kind_disappears_from_the_rendered_source() -> None:
    source = LatexRenderer(config_dir=None).emit(_resume("publication"))
    assert "Findable Title" not in source
    assert "A findable bullet sentence" not in source


def test_both_catalog_values_do_reach_the_source() -> None:
    """Non-vacuity: the assertion above is about the KIND, not about the renderer being empty."""
    for kind in ("experience", "project"):
        source = LatexRenderer(config_dir=None).emit(_resume(kind))
        assert "A findable bullet sentence" in source, kind
```

- [ ] **Step 6: Run it, then commit**

```
uv run pytest tests/projection/test_projection_kind_is_load_bearing.py -v --no-cov -n 0
```

```bash
git add src/boardwatch/projection/contract.py tests/projection/conftest.py \
        tests/projection/test_projection_contract.py \
        tests/projection/test_projection_kind_is_load_bearing.py
git commit -m "Enforce the projection reference contract and pin why entry kind is closed"
```

---

### Task 7: The inert header/education shell

**Files:**
- Create: `src/boardwatch/projection/shell.py`
- Test: `tests/projection/test_projection_shell.py`

**Interfaces:**
- Produces: `load_shell(path: Path) -> tuple[tuple[str, ...], tuple[str, ...]]` returning
  `(header, education)`.

`Resume.header` and `Resume.education` are plain **`list[str]`** (`tailor/model.py:47-48`) — no
structured type exists — and both are required with no default. `validate_master` rejects three
things, not one: a blank first line (`CONTACT_BLOCK_MISSING_NAME`, `load.py:51-55`), no email
anywhere in the header (`CONTACT_BLOCK_INVALID_EMAIL`, `:56-60`), and any template artifact
(`TEMPLATE_ARTIFACT`, `:61-67`). The spec's §7 row names only the email; all three must be tested.

- [ ] **Step 1: Write the failing test**

```python
"""The inert shell: model-only, never rendered, but required to exist and to be valid."""

from __future__ import annotations

from pathlib import Path

import pytest

from boardwatch.projection.errors import ProjectionError, ProjectionIssue
from boardwatch.projection.shell import load_shell

GOOD = "header:\n  - Example Candidate\n  - candidate@example.com\neducation:\n  - Example University\n"


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "master_resume.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_a_valid_shell_loads_verbatim(tmp_path: Path) -> None:
    header, education = load_shell(_write(tmp_path, GOOD))
    assert header == ("Example Candidate", "candidate@example.com")
    assert education == ("Example University",)


def test_a_missing_shell_source_is_fatal(tmp_path: Path) -> None:
    with pytest.raises(ProjectionError) as exc:
        load_shell(tmp_path / "absent.yaml")
    assert exc.value.violation.issue is ProjectionIssue.SHELL_SOURCE_UNREADABLE


def test_a_header_with_no_email_is_fatal(tmp_path: Path) -> None:
    body = "header:\n  - Example Candidate\neducation:\n  - Example University\n"
    with pytest.raises(ProjectionError) as exc:
        load_shell(_write(tmp_path, body))
    assert exc.value.violation.issue is ProjectionIssue.SHELL_SOURCE_UNREADABLE


def test_a_header_with_a_blank_first_line_is_fatal(tmp_path: Path) -> None:
    """`validate_master` rejects this separately from the email; the spec named only the email."""
    body = "header:\n  - '   '\n  - candidate@example.com\neducation:\n  - X\n"
    with pytest.raises(ProjectionError):
        load_shell(_write(tmp_path, body))


def test_a_template_artifact_in_the_shell_is_fatal(tmp_path: Path) -> None:
    """The third arm of `validate_master`, also unnamed by the spec."""
    body = "header:\n  - TODO\n  - candidate@example.com\neducation:\n  - X\n"
    with pytest.raises(ProjectionError):
        load_shell(_write(tmp_path, body))
```

- [ ] **Step 2: Run to verify it fails**

```
uv run pytest tests/projection/test_projection_shell.py -v --no-cov -n 0
```

- [ ] **Step 3: Write the implementation**

`src/boardwatch/projection/shell.py`:

```python
"""The inert `header`/`education` shell.

`LatexRenderer.emit` never reads either field — the template hardcodes the contact block
(`resume_base.tex:72-80`) and Education (`:87-93`), and the layout gate says so in its own
docstring. So projecting them cannot change the PDF. But both are REQUIRED on the frozen model with
no default, and `load_resume` additionally rejects a header with no valid email, a blank name line,
or a template artifact — so a document without them is not constructible or loadable at all.
Revision 2 of the design narrowed the scope without sourcing them and made no projected document
constructible.

The shell is therefore copied verbatim from the owner's existing authored résumé:

- model-only — it satisfies the frozen model and the loader, and the renderer still ignores it;
- NOT authoritative for the PDF, which keeps using the template's hardcoded values;
- part of `ProjectionPool` identity, so a shell change is visible rather than silent.

This is the one place v1 reads the file it is replacing, and it is transitional: when renderer
ownership of header/education lands, the shell goes.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from boardwatch.projection.errors import ProjectionIssue, raise_violation
from boardwatch.tailor.load import ResumeLoadError, load_resume


def load_shell(path: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """`(header, education)` from an authored résumé, validated by the production loader.

    Delegates to `load_resume` rather than re-parsing, so the shell is held to exactly the
    contract the tailor enforces. A shell that passed a private check here and failed
    `load_resume` later would be a document projection called valid and the tailor refused.
    """
    if not path.is_file():
        raise_violation(
            ProjectionIssue.SHELL_SOURCE_UNREADABLE,
            "shell_source names no readable file; the projected document cannot be built "
            "without a header and education, which are required on the frozen model",
            where=str(path.name),
        )
    try:
        resume = load_resume(path)
    except ResumeLoadError as exc:
        raise_violation(
            ProjectionIssue.SHELL_SOURCE_UNREADABLE,
            f"shell_source is not a loadable authored résumé: {exc}",
            where=str(path.name),
        )
    return tuple(resume.header), tuple(resume.education)
```

**Note for the implementer:** `load_resume` needs the file to be a *complete* résumé (it validates
entries too). If the owner's `resume.yaml` is the shell source that holds. If a future shell file
carries only `header`/`education`, this function must instead build a minimal `Resume` around them
and call `validate_master` directly — decide when you get there, and write the test first.

- [ ] **Step 4: Run the tests, then commit**

```
uv run pytest tests/projection/test_projection_shell.py -v --no-cov -n 0
```

```bash
git add src/boardwatch/projection/shell.py tests/projection/test_projection_shell.py
git commit -m "Source the inert header and education shell through the production loader"
```

---

### Task 8: The effectiveness and expiry rows

**Files:**
- Create: `src/boardwatch/projection/effectiveness.py`
- Test: `tests/projection/test_projection_effectiveness.py`

**Interfaces:**
- Produces: `resume_facts_for(entity_id, ctx, *, as_of: date) -> dict[str, FactRecord]` — the
  predicate → fact map `grammar.resolve_template` consumes, containing only facts that are
  résumé-surfaced **and** effective **and** unexpired at `as_of`.

**This is the subtlest task in the plan.** Three findings shape it:

1. `effective.py` has **no `as_of` parameter on any function**, deliberately (`effective.py:29-32`):
   §20 requires validation to be a pure function of bundle content, so expiry is evaluated by
   completeness against an explicit date, never there.
2. `eligible_fact_surfaces` returns `frozenset()` for a non-effective fact — so if the surface row
   is implemented through it, **the effectiveness row's test passes vacuously.** Use
   `effective_fact_ids` for effectiveness and the predicate catalog for surfaces, separately.
3. The date that governs expiry is chosen by `completeness._declared_expiry` (`:296-318`), which is
   **private**, and reads *two* declarations — `expires_at` and, for a `DateValue` fact, the value
   itself, earlier wins. Do **not** re-derive it from a restated "date" rule; promote it.

- [ ] **Step 1: Write the failing test, with the two fixtures the spec conflated**

```python
"""Effectiveness and expiry are different gates, and the synthetic bundle proves it.

The design's §9 asked for a before/after expiry control using the stale fact. That cannot work:
`fact.packet-pantry.legacy-language.001` fails on `verification_state: stale`, so no choice of
`as_of` changes its verdict. The fact that CAN demonstrate a date-driven transition is
`fact.example-credential.expiry.001` — verified, `expires_at: '2026-07-01'`, and still effective.
Two fixtures, two code paths.
"""

from __future__ import annotations

from datetime import date

from boardwatch.profile_bundle.effective import effective_fact_ids
from boardwatch.projection.effectiveness import resume_facts_for
from tests.projection.conftest import bundle_ctx  # noqa: F401

STALE = "fact.packet-pantry.legacy-language.001"
EXPIRING = "fact.example-credential.expiry.001"


def test_the_stale_fact_is_resume_surfaced_and_conflict_free(bundle_ctx) -> None:  # noqa: F811
    """The premise. If the bundle stops carrying such a fact, every test below is vacuous."""
    fact = next(f for f in bundle_ctx.index.facts if f.fact_id == STALE)
    assert "resume" in [s.value for s in fact.allowed_surfaces]
    assert fact.conflict_group_id is None
    assert fact.fact_id not in effective_fact_ids(bundle_ctx)


def test_a_stale_fact_is_refused_at_any_date(bundle_ctx) -> None:  # noqa: F811
    """Effectiveness, not expiry: no `as_of` rescues it."""
    for when in (date(2020, 1, 1), date(2026, 8, 13), date(2030, 1, 1)):
        facts = resume_facts_for("project.packet-pantry", bundle_ctx, as_of=when)
        assert STALE not in {f.fact_id for f in facts.values()}, when


def test_the_expiring_fact_is_effective_so_only_the_date_decides(bundle_ctx) -> None:  # noqa: F811
    """The before/after control the design wanted, on the fact that can actually provide it."""
    fact = next(f for f in bundle_ctx.index.facts if f.fact_id == EXPIRING)
    assert fact.fact_id in effective_fact_ids(bundle_ctx)
    assert fact.expires_at is not None

    subject = fact.subject_id
    before = resume_facts_for(subject, bundle_ctx, as_of=date(2026, 6, 1))
    after = resume_facts_for(subject, bundle_ctx, as_of=date(2026, 8, 1))

    assert EXPIRING in {f.fact_id for f in before.values()}, "same bytes must pass before expiry"
    assert EXPIRING not in {f.fact_id for f in after.values()}, "and fail after"
```

- [ ] **Step 2: Run to verify it fails**

```
uv run pytest tests/projection/test_projection_effectiveness.py -v --no-cov -n 0
```

Expected: `ModuleNotFoundError`. If instead the *premise* test fails, stop — the synthetic bundle
has changed and the whole fixture choice needs revisiting before writing code.

- [ ] **Step 3: Promote `_declared_expiry` to public**

In `src/boardwatch/profile_bundle/validation/completeness.py`, rename `_declared_expiry` to
`declared_expiry`, keep a module-private alias so existing call sites are untouched, and add it to
`__all__`:

```python
def declared_expiry(fact: FactRecord) -> tuple[date, ExpiryDeclaration] | None:
    """The date after which this fact's value stops being active, and which declaration states it.

    Public because projection needs the same answer: reading only `expires_at` left a credential
    that lapsed years ago effective forever, and a résumé built from the bundle would have
    asserted it. Re-deriving the pairing in another package would be a second implementation of
    one rule.
    """
    ...  # body unchanged


#: Retained so this module's existing call sites read unchanged.
_declared_expiry = declared_expiry
```

- [ ] **Step 4: Write the projection-side implementation**

`src/boardwatch/projection/effectiveness.py`:

```python
"""Which of an entity's facts a résumé may cite, at an explicit date.

Three gates, deliberately separate, because two of them are NOT the same check:

- **effective** — `effective_fact_ids` (verification state, supersession, unresolved conflicts).
- **surfaced** — `resume` in `allowed_surfaces`, intersected with the predicate's legal surfaces
  and its `APPLICATION_ONLY` policy.
- **unexpired** — `declared_expiry` against an explicit `as_of`, which `effective.py` deliberately
  excludes because that package reads no clock.

Keeping them separate matters: `eligible_fact_surfaces` returns an EMPTY surface set for a
non-effective fact, so implementing the surface gate through it would make the effectiveness gate
untestable — it would pass without ever being reached.

`effective_fact_ids` is hoisted once. It is O(facts + conflict candidates) per call, so asking it
per fact would make this quadratic for no benefit.
"""

from __future__ import annotations

from datetime import date

from boardwatch.profile_bundle.effective import effective_fact_ids, is_application_only
from boardwatch.profile_bundle.models.base import Surface
from boardwatch.profile_bundle.models.facts import FactRecord
from boardwatch.profile_bundle.validation.completeness import declared_expiry
from boardwatch.profile_bundle.validation.context import ValidationContext


def resume_facts_for(
    entity_id: str, ctx: ValidationContext, *, as_of: date
) -> dict[str, FactRecord]:
    """Predicate → fact, for the facts about `entity_id` a résumé may cite at `as_of`.

    Keyed by predicate because that is what the `{predicate}` grammar looks up. A predicate with
    two usable facts keeps the first in index order; a genuine ambiguity there is a bundle
    cardinality problem, which the bundle's own validation owns, not projection's.
    """
    effective = effective_fact_ids(ctx)
    out: dict[str, FactRecord] = {}
    for fact in ctx.index.facts:
        if fact.subject_id != entity_id:
            continue
        if fact.fact_id not in effective:
            continue
        if Surface.RESUME not in fact.allowed_surfaces:
            continue
        if is_application_only(fact, ctx):
            continue
        expiry = declared_expiry(fact)
        if expiry is not None and expiry[0] < as_of:
            continue
        out.setdefault(fact.predicate, fact)
    return out
```

- [ ] **Step 5: Run the tests**

```
uv run pytest tests/projection/test_projection_effectiveness.py -v --no-cov -n 0
uv run pytest tests/profile_bundle -k completeness --no-cov -n 0
```

Expected: projection tests pass; the completeness suite is unaffected by the rename.

- [ ] **Step 6: Confirm the expiry arm fails without its fix**

Delete the two `expiry` lines from `resume_facts_for`. Re-run:

```
uv run pytest tests/projection/test_projection_effectiveness.py -v --no-cov -n 0
```

Expected: **FAIL on `assert EXPIRING not in ...`, "and fail after"** — that assertion specifically.
The `before` assertion must still pass, which is what proves the test discriminates a date rather
than a fact. Restore.

- [ ] **Step 7: Commit**

```bash
git add src/boardwatch/projection/effectiveness.py \
        src/boardwatch/profile_bundle/validation/completeness.py \
        tests/projection/test_projection_effectiveness.py
git commit -m "Gate projected facts on effectiveness, surface and expiry as three separate checks"
```

---

### Task 9: The projection approval stamp — its own type, not the bundle's

**Files:**
- Create: `src/boardwatch/projection/stamp.py`
- Test: `tests/projection/test_projection_stamp.py`

**Interfaces:**
- Produces: `ProjectionStamp` (frozen model: `projection_stamp_id`, `projection_digest`,
  `approved_at`, `approved_via`), `stamp_path(config_dir, digest) -> Path`,
  `write_stamp(config_dir, *, digest, approved_at) -> Path`,
  `stamp_exists(config_dir, digest) -> bool`.

**Why not reuse `ApprovalStamp`** — the spec said to, and it cannot be done:

- `test_profile_bundle_cli_approval.py:427-447` asserts by `rglob` over `src/` that **exactly two
  files** call `approval_stamp_bytes(`. A third breaks it, and the assertion cannot be scoped away.
- `ApprovedVia` is a **closed single-member enum** (`models/history.py:180-184`) baked into the
  shipped JSON schema (`resources/career-profile.schema.json:187,207`).
- `ApprovalStamp.candidate_content_digest` means *bundle candidate*. A projection digest is a
  different fact with the same shape, and conflating them would let a bundle approval satisfy a
  projection gate.

Keep the *properties* — digest-bound, collision-free id, controlling-terminal only — and copy the
`approvals.py:202-230` dot-free-scope argument, which is the reason its ids cannot be re-bracketed
ambiguously.

- [ ] **Step 1: Write the failing test**

```python
"""The projection stamp is bound to a digest, and editing the declaration reopens the gate."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from boardwatch.projection.stamp import stamp_exists, write_stamp

D1 = "sha256:" + "a" * 64
D2 = "sha256:" + "b" * 64
NOW = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)


def test_no_stamp_exists_before_one_is_written(tmp_path: Path) -> None:
    assert stamp_exists(tmp_path, D1) is False


def test_a_written_stamp_is_found_for_its_own_digest_only(tmp_path: Path) -> None:
    """Keyed by digest, so the lookup itself is the binding: an edited declaration has a
    different digest and simply has no stamp."""
    write_stamp(tmp_path, digest=D1, approved_at=NOW)
    assert stamp_exists(tmp_path, D1) is True
    assert stamp_exists(tmp_path, D2) is False


def test_the_stamp_round_trips_through_the_restricted_loader(tmp_path: Path) -> None:
    """Written with `yaml_writer.document_bytes`, so it is readable by the same grammar the
    bundle uses — and so a float or tuple in the payload fails loudly rather than silently."""
    path = write_stamp(tmp_path, digest=D1, approved_at=NOW)
    assert path.is_file()
    assert D1.removeprefix("sha256:")[:12] in path.name


def test_two_writes_of_one_digest_do_not_produce_two_files(tmp_path: Path) -> None:
    write_stamp(tmp_path, digest=D1, approved_at=NOW)
    write_stamp(tmp_path, digest=D1, approved_at=NOW)
    assert len(list(path for path in (tmp_path / "projection-approvals").iterdir())) == 1
```

- [ ] **Step 2: Run to verify it fails, then implement**

```
uv run pytest tests/projection/test_projection_stamp.py -v --no-cov -n 0
```

`src/boardwatch/projection/stamp.py`:

```python
"""The owner's approval of one `projection.yaml`, bound to its digest.

Deliberately NOT `profile_bundle.ApprovalStamp`, for three reasons:
`test_profile_bundle_cli_approval.py:427-447` asserts by rglob that exactly two files may call
`approval_stamp_bytes(`; `ApprovedVia` is a closed one-member enum in the shipped JSON schema; and
`candidate_content_digest` means *bundle candidate*, so reusing it would let a bundle approval
satisfy a projection gate. The PROPERTIES are copied — digest-bound, collision-free id,
controlling terminal only — the type is not.

The gate does not prove a template literal is honest; nothing can. It guarantees no literal reaches
a résumé without the owner having seen that exact text.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import PurePosixPath
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from boardwatch.profile_bundle.yaml_writer import document_bytes

APPROVALS_DIR = "projection-approvals"


class ProjectionStamp(BaseModel):
    """One approval. `approved_via` is a literal here rather than a shared enum, because the
    bundle's `ApprovedVia` is closed and schema-bound."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    projection_stamp_id: str
    projection_digest: str
    approved_at: datetime
    approved_via: str = "controlling_terminal"


def _token(digest: str) -> str:
    return "sha256-" + digest.removeprefix("sha256:")


def stamp_path(config_dir: Path, digest: str) -> Path:
    """`{config_dir}/projection-approvals/sha256-<digest>.yaml`.

    Keyed by digest, not by a name: a stamp outlives the declaration that produced it, and two
    declarations with the same content must not alias to two stamp files.
    """
    return config_dir / APPROVALS_DIR / f"{_token(digest)}.yaml"


def stamp_exists(config_dir: Path, digest: str) -> bool:
    return stamp_path(config_dir, digest).is_file()


def write_stamp(config_dir: Path, *, digest: str, approved_at: datetime) -> Path:
    """Write the stamp for exactly this digest. Idempotent — one digest, one file.

    The id carries the digest token as its scope, and the token is dot-free by construction, so
    the id's components can never be re-bracketed ambiguously (the argument at
    `profile_bundle/approvals.py:202-213`).
    """
    stamp = ProjectionStamp(
        projection_stamp_id=f"projection-approval.{_token(digest)}",
        projection_digest=digest,
        approved_at=approved_at,
    )
    path = stamp_path(config_dir, digest)
    path.parent.mkdir(parents=True, exist_ok=True)
    logical = PurePosixPath(f"{APPROVALS_DIR}/{path.name}")
    path.write_bytes(document_bytes(stamp.model_dump(mode="json"), logical_path=logical))
    return path
```

- [ ] **Step 3: Run the tests and the assertion this task exists to protect**

```
uv run pytest tests/projection/test_projection_stamp.py -v --no-cov -n 0
uv run pytest tests/profile_bundle/test_profile_bundle_cli_approval.py -v --no-cov -n 0
```

Expected: both pass. The second is the one that would have gone red had this reused
`approval_stamp_bytes`.

- [ ] **Step 4: Commit**

```bash
git add src/boardwatch/projection/stamp.py tests/projection/test_projection_stamp.py
git commit -m "Add a projection approval stamp bound to the declaration digest"
```

---

### Task 10: `boardwatch profile-bundle approve-projection`

**Files:**
- Create: `src/boardwatch/cli/projection_cmd.py` (the `profile-bundle` half only; Task 19 adds the
  `resume` group)
- Modify: `src/boardwatch/cli/profile_bundle_cmd.py` — register the new command on the existing app
- Test: `tests/projection/test_projection_cli_approval.py`

Mirror `approve` exactly (`cli/profile_bundle_cmd.py:927-1079`): the `ApprovalTerminal` protocol,
`_StandardTerminal.is_controlling()` checking **both** `sys.stdin` and `sys.stdout` and catching
`(AttributeError, ValueError)`, the prompt on **stderr** via `err=True`, and exact comparison against
`CONFIRMATION_WORD` with no strip and no casefold. **No `--yes`, no environment variable, no piped
answer** — the refusal is structural, not coded.

The command prints **the composed lines with their resolved values**, not the template source, so the
owner approves what will actually be printed.

- [ ] **Step 1: Write the failing test** — copy the three TTY-faking mechanisms from
`tests/profile_bundle/test_profile_bundle_cli_approval.py` (factory replacement at `:96-103`,
gate-only replacement at `:567-577`, stream replacement at `:502-526`), plus the env-variable
absence test at `:156-174` **with its spellings written out**, because the property is an absence and
a test that asked the code which variables it reads could only confirm the answer it was given.

```python
"""`approve-projection`: a controlling terminal, or nothing is approved."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest
from typer.testing import CliRunner

from boardwatch.cli import projection_cmd
from boardwatch.cli.app import app
from boardwatch.projection.stamp import APPROVALS_DIR


@dataclass
class FakeTerminal:
    """The only thing a test replaces. It answers; it decides nothing."""

    controlling: bool = True
    answer: str = "approve"
    shown: list[str] = field(default_factory=list)

    def is_controlling(self) -> bool:
        return self.controlling

    def show(self, text: str) -> None:
        self.shown.append(text)

    def ask(self, prompt: str) -> str:
        return self.answer


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    config_dir = tmp_path / "cfg"
    config_dir.mkdir(parents=True)
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(config_dir))
    return config_dir


def _run(env: Path, terminal: FakeTerminal, monkeypatch: pytest.MonkeyPatch, decl: Path):
    monkeypatch.setattr(projection_cmd, "approval_terminal", lambda: terminal)
    return CliRunner().invoke(
        app, ["profile-bundle", "approve-projection", "--declaration", str(decl)]
    )


def test_a_non_controlling_terminal_writes_nothing(env, monkeypatch, example_declaration):
    result = _run(env, FakeTerminal(controlling=False), monkeypatch, example_declaration)
    assert result.exit_code == 1
    assert not (env / APPROVALS_DIR).exists()


def test_declining_writes_nothing(env, monkeypatch, example_declaration):
    result = _run(env, FakeTerminal(answer="no"), monkeypatch, example_declaration)
    assert result.exit_code == 1
    assert not (env / APPROVALS_DIR).exists()


@pytest.mark.parametrize("answer", ["y", "yes", "APPROVE", " approve", "approve ", ""])
def test_only_the_exact_word_approves(env, monkeypatch, example_declaration, answer):
    result = _run(env, FakeTerminal(answer=answer), monkeypatch, example_declaration)
    assert result.exit_code == 1
    assert not (env / APPROVALS_DIR).exists()


def test_approving_writes_exactly_one_stamp(env, monkeypatch, example_declaration):
    result = _run(env, FakeTerminal(), monkeypatch, example_declaration)
    assert result.exit_code == 0
    assert len(list((env / APPROVALS_DIR).iterdir())) == 1


def test_the_owner_is_shown_resolved_values_not_template_source(
    env, monkeypatch, example_declaration
):
    """The gate's whole point: approving `{@display_name}` tells the owner nothing."""
    terminal = FakeTerminal()
    _run(env, terminal, monkeypatch, example_declaration)
    shown = "\n".join(terminal.shown)
    assert "{@display_name}" not in shown
    assert "Packet Pantry" in shown


@pytest.mark.parametrize(
    "variable",
    ["CI", "BOARDWATCH_YES", "BOARDWATCH_ASSUME_YES", "BOARDWATCH_NON_INTERACTIVE",
     "DEBIAN_FRONTEND"],
)
def test_no_environment_variable_bypasses_the_prompt(env, monkeypatch, example_declaration, variable):
    """The spellings are written out rather than derived, because the property is an absence."""
    monkeypatch.setenv(variable, "1")
    result = CliRunner().invoke(
        app, ["profile-bundle", "approve-projection", "--declaration", str(example_declaration)]
    )
    assert result.exit_code != 0
    assert not (env / APPROVALS_DIR).exists()


@pytest.mark.parametrize("state", ["detached", "closed", "tty"])
def test_the_real_adapter_answers_no_for_anything_not_plainly_a_terminal(monkeypatch, state):
    """The production adapter across the states a LaunchAgent actually reaches. The `tty` case is
    the control: without it, an adapter that always answered False would pass."""

    class Closed:
        def isatty(self) -> bool:
            raise ValueError("I/O operation on closed file")

    class Terminal:
        def isatty(self) -> bool:
            return True

    replacement = {"detached": None, "closed": Closed(), "tty": Terminal()}[state]
    monkeypatch.setattr(projection_cmd.sys, "stdin", replacement)
    monkeypatch.setattr(projection_cmd.sys, "stdout", Terminal())
    assert projection_cmd.approval_terminal().is_controlling() is (state == "tty")
```

Add an `example_declaration` fixture to `tests/projection/conftest.py` that copies the packaged
example beside a valid `master_resume.yaml` in `tmp_path` and returns its path.

- [ ] **Step 2: Run to verify it fails; Step 3: implement, copying `profile_bundle_cmd.py:927-1079`'s
  four units** (protocol, `_StandardTerminal`, the command, the prompt builder), substituting
  `projection_digest` for the candidate digest and `write_stamp` for `file_approval_stamp`. Compose
  the prompt by running stage 1's template resolution so the printed lines are resolved values.

- [ ] **Step 4: Run the tests, then `make check`, then commit**

```
uv run pytest tests/projection/test_projection_cli_approval.py -v --no-cov -n 0
make check
```

```bash
git add src/boardwatch/cli/projection_cmd.py src/boardwatch/cli/profile_bundle_cmd.py \
        tests/projection/test_projection_cli_approval.py tests/projection/conftest.py
git commit -m "Add approve-projection, the owner gate for a projection declaration"
```

---

# Slice P2 — stage 1, the pool, and the emitted artifacts

**Gate:** golden output + round-trip test green.

---

### Task 11: A `Resume` serializer

**Files:**
- Create: `src/boardwatch/projection/serialize.py`
- Test: `tests/projection/test_projection_serialize.py`

**Interfaces:**
- Produces: `resume_document_bytes(resume: Resume) -> bytes`.

**Nothing in the repo writes a `Resume` to YAML.** Verified three ways: `model_dump_json()` appears
at exactly two sites (`reports/tailor.py:433`, `:503`), both for SHA-256 hashing; `scaffold_template()`
writes a static string constant; there is no `save`/`dump`/`to_yaml` for `Resume` anywhere. So this is
new code, and `yaml.safe_dump` is not an option — its implicit scalars fall outside the restricted
loader's narrowed grammar.

`document_bytes` **refuses floats, tuples and non-string keys**, and read-back-verifies its own
output. `model_dump(mode="json")` handles the tuple case.

- [ ] **Step 1: Write the failing test — the round-trip contract is the whole spec**

```python
"""`load_resume(serialize(resume)) == resume`. That is the contract."""

from __future__ import annotations

from pathlib import Path

from boardwatch.projection.serialize import resume_document_bytes
from boardwatch.tailor.load import load_resume
from boardwatch.tailor.model import Bullet, Entry, Resume, SkillGroup


def _resume() -> Resume:
    return Resume(
        header=["Example Candidate", "candidate@example.com", "+1 555 0100"],
        education=["Example University — B.S. Computer Science"],
        skill_groups=[SkillGroup(label="Languages", items=["Example Language", "Swift"])],
        entries=[
            Entry(
                entry_id="entry.employment.example-labs",
                heading="Example Labs",
                kind="experience",
                title="Software Engineer",
                dates="2025-02-01 – Present",
                subtitle="Example Labs",
                location="Remote",
                bullets=[
                    Bullet(bullet_id="claim.a.001", text="Built a retry-safe ingestion path"),
                    Bullet(bullet_id="claim.a.002", text="Measured sustained local throughput"),
                ],
            ),
            Entry(
                entry_id="entry.project.packet-pantry",
                heading="Packet Pantry",
                kind="project",
                title="Packet Pantry",
                bullets=[Bullet(bullet_id="claim.b.001", text="Shipped a public service")],
            ),
        ],
        extracurricular=["Example Society — organiser"],
    )


def test_a_projected_resume_round_trips_through_the_production_loader(tmp_path: Path) -> None:
    original = _resume()
    path = tmp_path / "projected.yaml"
    path.write_bytes(resume_document_bytes(original))
    assert load_resume(path) == original


def test_the_bytes_are_stable_for_one_document() -> None:
    """Deterministic output, so the golden test and the digest both mean something."""
    assert resume_document_bytes(_resume()) == resume_document_bytes(_resume())


def test_a_unicode_bullet_survives_the_round_trip(tmp_path: Path) -> None:
    """The repo has been bitten by mojibake in appended text; the serializer must not add to it."""
    original = _resume().model_copy(
        update={
            "extracurricular": ["Café résumé — naïve coöperation"],
        }
    )
    path = tmp_path / "projected.yaml"
    path.write_bytes(resume_document_bytes(original))
    assert load_resume(path).extracurricular == ["Café résumé — naïve coöperation"]
```

- [ ] **Step 2: Run to verify it fails; Step 3: implement**

`src/boardwatch/projection/serialize.py`:

```python
"""`Resume` → YAML bytes that `tailor.load.load_resume` reads back as the same document.

There was no such function. `Resume` is load-only today: the only two serialization sites hash the
model for content addressing, and the scaffold writes a static string. So this is the one place the
projected document's bytes are decided.

Routed through `profile_bundle.yaml_writer.document_bytes` rather than `yaml.safe_dump`, for the
reason that module documents: a stock dump's implicit scalars fall outside the restricted loader's
narrowed grammar, so `safe_dump` can emit documents Boardwatch itself refuses to read. It also
read-back-verifies, refuses floats and tuples, and quotes every string — which is what makes a
bullet beginning "NO" or containing "12:30" survive.

The emitted mapping carries EXACTLY the keys `load_resume` reads. No provenance comment: the loader
calls `yaml.safe_load`, which discards comments, so a comment could never reach the artifact ledger.
Provenance is the manifest sidecar's job.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from boardwatch.profile_bundle.yaml_writer import document_bytes
from boardwatch.tailor.model import Resume

#: Named for the diagnostic `document_bytes` produces on failure, not for a real filesystem path.
_LOGICAL = PurePosixPath("projected-resume.yaml")


def resume_document_bytes(resume: Resume) -> bytes:
    """The projected document's bytes. `mode="json"` is load-bearing twice over: it turns tuples
    into lists (`document_bytes` refuses tuples) and drops nothing the loader needs."""
    payload = resume.model_dump(mode="json")
    return document_bytes(payload, logical_path=_LOGICAL)
```

- [ ] **Step 4: Run the tests**

```
uv run pytest tests/projection/test_projection_serialize.py -v --no-cov -n 0
```

Expected: 3 passed. **If the round-trip fails on `title: None`**, check whether `document_bytes`
round-trips a null — if not, drop `None`-valued optional keys from the payload before emitting and
add a test pinning that a `None` title survives as absent rather than as the string "None".

- [ ] **Step 5: Commit**

```bash
git add src/boardwatch/projection/serialize.py tests/projection/test_projection_serialize.py
git commit -m "Serialize a projected resume through the restricted YAML writer"
```

---

### Task 12: Stage 1 — the `ProjectionPool`

**Files:**
- Create: `src/boardwatch/projection/pool.py`
- Test: `tests/projection/test_projection_pool.py`

**Interfaces:**
- Consumes: everything from Tasks 3, 5, 6, 7, 8.
- Produces:
  - `ProjectionPool` — frozen dataclass: `resume: Resume`, `pinned_entry_ids: tuple[str, ...]`,
    `candidate_entry_ids: tuple[str, ...]`, `no_match_fallback_ids: tuple[str, ...]`,
    `bundle_revision: str`, `bundle_digest: str`, `projection_digest: str`
  - `project_pool(bundle_root: Path, declaration_path: Path, *, config_dir: Path, as_of: date) -> ProjectionPool`

**A serialized `Resume` is not a sufficient handoff.** `Entry` has no `pinned` field, so stage 2
could not tell the fixed core from the swappable projects and would have to reread `projection.yaml`
or guess. The pool is the contract between stages; the plain `Resume` is stage 2's *output*.

Identifier derivation, made total by Task 3's duplicate rule: `entry_id = "entry." + entity_id`,
`bullet_id = claim_id` verbatim.

Key steps: read the bundle (`read_current_once` → `selected_documents` → `context_from_documents`);
check the approval stamp for the current `projection_digest`; run `check_references`; for each entry
resolve its templates against `resume_facts_for(...)`; build `Bullet`s with `text=claim.text`
**byte-for-byte**; map skill ids through `render_skill`; attach the shell; emit `tech_tags` empty and
`Resume.title=None` (tailor owns persona).

- [ ] **Step 1: Write the failing test**

```python
"""Stage 1 is JD-blind and total: it either emits a faithful pool or refuses."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from boardwatch.projection.errors import ProjectionError, ProjectionIssue
from boardwatch.projection.pool import project_pool

AS_OF = date(2026, 8, 13)


def test_the_pool_separates_pinned_from_candidates(projection_env) -> None:
    pool = project_pool(
        projection_env.bundle_root, projection_env.declaration,
        config_dir=projection_env.config_dir, as_of=AS_OF,
    )
    assert pool.pinned_entry_ids == ("entry.employment.example-labs",)
    assert pool.candidate_entry_ids == ("entry.project.packet-pantry",)
    assert set(pool.pinned_entry_ids) & set(pool.candidate_entry_ids) == set()


def test_every_bullet_is_its_claim_text_byte_for_byte(projection_env, bundle_ctx) -> None:
    """Bullet text is copied, never templated, edited or reflowed. Derived from the bundle at
    run time so a claim edit cannot silently diverge."""
    pool = project_pool(
        projection_env.bundle_root, projection_env.declaration,
        config_dir=projection_env.config_dir, as_of=AS_OF,
    )
    by_id = {c.claim_id: c.text for c in bundle_ctx.index.claims}
    seen = 0
    for entry in pool.resume.entries:
        for bullet in entry.bullets:
            assert bullet.text == by_id[bullet.bullet_id]
            seen += 1
    assert seen >= 2, "the derivation found nothing; the fixture stopped exercising bullets"


def test_tech_tags_are_emitted_empty(projection_env) -> None:
    """A deliberate lineage decision, not a no-op: `reports/tailor.py:433` hashes the model, so
    an empty `tech_tags` changes the master hash."""
    pool = project_pool(
        projection_env.bundle_root, projection_env.declaration,
        config_dir=projection_env.config_dir, as_of=AS_OF,
    )
    assert all(b.tech_tags == [] for e in pool.resume.entries for b in e.bullets)


def test_the_persona_title_is_left_unset(projection_env) -> None:
    """`tailor` owns persona shaping. Stage 1 setting `title` would fight it."""
    pool = project_pool(
        projection_env.bundle_root, projection_env.declaration,
        config_dir=projection_env.config_dir, as_of=AS_OF,
    )
    assert pool.resume.title is None


def test_the_projected_document_loads_through_the_production_loader(projection_env, tmp_path) -> None:
    from boardwatch.projection.serialize import resume_document_bytes
    from boardwatch.tailor.load import load_resume

    pool = project_pool(
        projection_env.bundle_root, projection_env.declaration,
        config_dir=projection_env.config_dir, as_of=AS_OF,
    )
    path = tmp_path / "projected.yaml"
    path.write_bytes(resume_document_bytes(pool.resume))
    assert load_resume(path) == pool.resume


def test_a_missing_approval_stamp_refuses_to_emit(projection_env_unapproved) -> None:
    """The template hole's mechanical gate: no literal reaches a résumé unapproved."""
    with pytest.raises(ProjectionError) as exc:
        project_pool(
            projection_env_unapproved.bundle_root, projection_env_unapproved.declaration,
            config_dir=projection_env_unapproved.config_dir, as_of=AS_OF,
        )
    assert exc.value.violation.issue is ProjectionIssue.MISSING_PROJECTION_APPROVAL


def test_editing_a_template_literal_reopens_the_gate(projection_env) -> None:
    """Approved, then edited: the digest moves and the old stamp no longer matches."""
    text = projection_env.declaration.read_text(encoding="utf-8")
    projection_env.declaration.write_text(
        text.replace("{@display_name}", "Senior {@display_name}"), encoding="utf-8"
    )
    with pytest.raises(ProjectionError) as exc:
        project_pool(
            projection_env.bundle_root, projection_env.declaration,
            config_dir=projection_env.config_dir, as_of=AS_OF,
        )
    assert exc.value.violation.issue is ProjectionIssue.MISSING_PROJECTION_APPROVAL
```

Add `projection_env` and `projection_env_unapproved` fixtures to `tests/projection/conftest.py`,
returning a frozen dataclass of `(bundle_root, config_dir, declaration)`. The approved variant calls
`write_stamp(config_dir, digest=projection_digest(load_declaration(path)), approved_at=…)`.

- [ ] **Step 2: Run to verify it fails; Step 3: implement `pool.py`; Step 4: run to verify it passes**

```
uv run pytest tests/projection/test_projection_pool.py -v --no-cov -n 0
```

- [ ] **Step 5: Confirm the byte-for-byte test discriminates**

Add `+ " "` to the bullet text in `pool.py`. Re-run — expected FAIL on
`assert bullet.text == by_id[bullet.bullet_id]`. Note that `Bullet._single_line` normalises
whitespace runs, so a *trailing* space may be normalised away; if the mutation does not trip, use a
mid-text edit instead and record which mutation actually discriminates. Restore.

- [ ] **Step 6: Commit**

```bash
git add src/boardwatch/projection/pool.py tests/projection/test_projection_pool.py \
        tests/projection/conftest.py
git commit -m "Build the JD-blind projection pool from the bundle and the declaration"
```

---

### Task 13: The manifest sidecar

**Files:**
- Create: `src/boardwatch/projection/manifest.py`
- Test: `tests/projection/test_projection_manifest.py`

**Interfaces:**
- Produces: `ProjectionManifest` (frozen model) and `manifest_bytes(manifest) -> bytes`.

Fields: `manifest_schema: int`, `bundle_revision`, `bundle_digest`, `projection_digest`,
`posting_id: int | None`, `jd_skills: tuple[str, ...]`, `pinned_entry_ids`, `selected_entry_ids`,
`scores: tuple[tuple[str, str], ...]` (id → **decimal string**), `claim_to_bullet: tuple[tuple[str, str], ...]`.

**Scores are decimal strings, not floats.** `canonical._normalize` raises on any float
(`canonical.py:136-154`) and `document_bytes` refuses them too. Mirror `DecimalValue`'s
`DecimalString`.

Revision 1 put provenance in YAML comments; `load_resume` calls `yaml.safe_load`, which discards
them, so provenance never reached the ledger. **State plainly in the module docstring that v1 does
not close stale lineage** — `tailor run` never reads this file, so the sidecar makes staleness
*inspectable*, not *detected*. Slice P5 owns the real fix.

- [ ] **Steps:** failing test (JSON is deterministic, `sort_keys=True`, and a float score is
  rejected) → implement → pass → commit as
  `"Emit a projection manifest sidecar carrying bundle and selection lineage"`.

---

### Task 14: The golden projection

**Files:**
- Create: `tests/projection/test_projection_golden.py`
- Create: `src/boardwatch/projection/examples/projection.golden.txt` + its `SHIPPED_DATA` entry
- Modify: `tests/generalization/test_inventory.py:55` (bump again)

**There is no snapshot harness and no `--snapshot-update`.** `grep -rn "addoption"` is zero hits
repo-wide. Follow `test_profile_bundle_schema_export.py:34-40`: commit the artifact, compare it
byte-for-byte against the **live generator**, and regenerate by calling the generator and writing its
output by hand.

Name it `projection.golden.txt`, **not** anything containing `resume` or `cv` — R5 bans those stems on
data files, including as a directory segment.

- [ ] **Steps:** write the comparison test → run it, capture the generator's output, commit that as
  the golden → compute and register the pin → bump the counter → verify
  `uv run python -m tools.generalization` exits 0 → commit as
  `"Pin the golden projection over the synthetic bundle"`.

The test must also assert the shell's contribution to identity, so a silent shell change fails:

```python
def test_the_shell_is_part_of_the_projected_document(projection_env) -> None:
    """The shell is model-only and never rendered, but it IS part of identity — so a change to
    it must be visible rather than silent."""
    pool = project_pool(...)
    assert pool.resume.header, "the inert shell must be present, not empty"
    assert any("@" in line for line in pool.resume.header)
```

---

# Slice P3 — the CLIs and the posting-context seam

**Gate:** exit tiers match the bundle CLI's convention; the `profile-bundle` family still opens no
database.

---

### Task 15: The persona preflight

**Files:**
- Create: `src/boardwatch/projection/persona_preflight.py`
- Test: `tests/projection/test_projection_persona_preflight.py`

**Interfaces:**
- Produces: `reject_entry_declaring_personas(config_dir: Path) -> None`.

`apply_persona` raises `PersonaError` on any declared id missing from its input
(`tailor/persona.py:189-199` — **not** `192-199`; the spec's line numbers are off by 1–3). If a
persona declares `entries: [e1, e2]` and stage 2 omits `e2`, `tailor run`'s downstream
`apply_persona` raises and the résumé can never render. Moving persona application did not remove
that collision; it only moved where it happens. **v1 forbids the combination**, reported before any
selection runs.

Both bundled personas ship `entries: null` (`personas.yaml:31,37` — verified), so nothing shipped is
affected. **The fixture must therefore be authored** — the bundled personas cannot reproduce this,
which is exactly why no selection test would otherwise catch it.

- [ ] **Steps:** write the failing test with an authored `personas.yaml` override carrying
  `entries: [entry.x]` → assert `ProjectionIssue.PERSONA_DECLARES_ENTRIES` **before** any selection
  → add a positive control that the bundled registry passes → implement → commit as
  `"Refuse a persona that declares entries, before any selection runs"`.

---

### Task 16: Extract the JD-skills query into a named function

**Files:**
- Modify: `src/boardwatch/reports/tailor.py:341-356`
- Test: `tests/unit/test_reports_tailor_jd_skills.py`

**Interfaces:**
- Produces: `jd_skills_for(conn: Connection, posting_id: int, *, taxonomy: Taxonomy) -> set[str] | None` — `None` when **no extraction row exists**, distinct from an empty set.

The JD skill set has **no producing function**. It is an inline SQLAlchemy `SELECT` on `extractions`,
duplicated in **five** places (`reports/tailor.py:342`, `cli/top_cmd.py:204`, `:471`,
`cli/show_cmd.py:121`, `reports/notify.py:94`), keyed on `taxonomy.version`, and **a cache miss
silently yields `set()`**. Without extracting it, the posting seam becomes a sixth copy — and a
duplicated query can score a different JD version than tailoring does.

**Return `None` on a cache miss, not `set()`.** Today a miss and a genuinely skill-free JD are
indistinguishable, and for projection they must not be: a miss must be a named fatal
(`NO_JD_EXTRACTION`), not a silent slide into `no_match_fallback` that produces a plausible-looking
résumé for the wrong reason.

`_plan_tier_a` keeps its existing behaviour by coalescing: `jd_skills = found if found is not None
else set()`. **That coalesce is the compatibility guarantee** — assert it with a test so the tailor
path is provably unchanged.

- [ ] **Steps:** failing test (a seeded extraction row returns its skills; no row returns `None`; a
  row at a *different* `engine_version` returns `None`) → extract the function, leaving
  `_plan_tier_a` behaviourally identical → run the tailor suite for regressions → run the wall test,
  since this touches a tailor-closure module → commit as
  `"Name the JD-skills query so one route serves tailoring and projection"`.

---

### Task 17: The posting-context seam

**Files:**
- Create: `src/boardwatch/projection/posting.py`
- Test: `tests/projection/test_projection_posting.py`

**Interfaces:**
- Produces: `PostingContext` (frozen: `posting_id`, `posting_version_id`, `jd_skills: frozenset[str]`, `page_budget: int`) and `posting_context(engine, settings, posting_id) -> PostingContext`.

The **single** route to those inputs. It composes, in order:

1. `run_preflight(engine, settings)` — without it a posting whose taxonomy version moved has no
   extraction row.
2. `load_taxonomy(settings.config_dir)` — for `taxonomy.version`, the `engine_version` filter.
3. `current_posting_versions(conn, [posting_id])` plus the `status != "open"` guard from
   `reports/tailor.py:333-336`.
4. `jd_skills_for(...)` from Task 16 — **`None` raises `NO_JD_EXTRACTION`.**
5. `get_profile(conn)` and **`max(1, row.resume_max_pages) if row is not None else 1`**.

**The page budget is global, not per-posting** — one column on the singleton `profile` table
(`store/tables.py:203`, `CheckConstraint("id = 1")`). The `max(1, …)` floor lives at the call site
(`reports/tailor.py:555`), not in `get_profile`; a reader that skips it reintroduces the 0-page bug
that comment describes.

`plan_tier_a` (`reports/tailor.py:385`) looks like this seam and is not usable: it requires a
`resume_path`, loads personas, and builds/applies/enforces a whole tailor plan — all of which
projection replaces.

- [ ] **Steps:** failing test (budget floor at a stored 0; a stored 2 is honoured — mirror
  `tests/unit/test_run_tailor_gate.py:262`; a closed posting refuses; a missing extraction raises
  `NO_JD_EXTRACTION` rather than returning empty) → implement → commit as
  `"Add the single posting-context seam for JD skills and the page budget"`.

---

### Task 18: `boardwatch profile-bundle project` — stage 1 only

**Files:** modify `src/boardwatch/cli/projection_cmd.py`; test `tests/projection/test_projection_cli_project.py`.

Stage 1 only: serializes the pool for review, JD-blind, and **opens no database**. It joins the
`profile-bundle` family, so it must keep that family's three rules
(`cli/profile_bundle_cmd.py:1-36`): no database — `load_settings`, never `build_context`; no absolute
path in any diagnostic; exit tiers read, never restated.

Accepts `--json` and `--check`. `--check` re-projects and **exits non-zero** when the emitted
document's digests differ from the current bundle or declaration — provenance is active, not
informational.

**Adding diagnostics to that family means editing the closed `IssueCode` catalog**
(`profile_bundle/errors.py:49-221`) plus `STATE_REFUSAL_CODES` / `COULD_NOT_COMPLETE_CODES`, and
`tier_of` is asserted total by a test. Budget for that. Alternatively keep projection's own
`ProjectionIssue` and map it to one bundle `IssueCode` at the boundary — **decide and write the
reason down**; do not do both.

Also: `cli/profile_bundle_cmd.py:1` says "the twelve commands". Adding two makes fourteen. Update it.

- [ ] **Steps:** failing test (`--json` carries all 7 envelope keys — mirror
  `test_profile_bundle_cli_exit_codes.py:44-71`; `--check` exits non-zero after the declaration is
  edited; **no `boardwatch.db` is created anywhere under the data dir**) → implement → commit as
  `"Add profile-bundle project for JD-blind stage 1 review"`.

---

### Task 19: `boardwatch resume project` — stages 1 and 2

**Files:** modify `src/boardwatch/cli/projection_cmd.py`, `src/boardwatch/cli/app.py`; test
`tests/projection/test_projection_cli_resume_project.py`.

A **new top-level group**, `resume`, which does not exist today (`grep -n "resume" cli/app.py` is
empty). Copy `tailor_cmd.py:41-56`'s group pattern; module is `cli/projection_cmd.py` exporting
`resume_app`; register with one import plus `app.add_typer(resume_app, name="resume")`.

**It lives outside the `profile-bundle` family deliberately**, because JD skills and the page budget
are database-owned and that family never opens the database. This command uses `build_context`.

**`cli/app.py` is NOT in the tailor closure**, so registering here is safe — but re-run the wall test
to prove it.

The flow is **two commands, deliberately**: `resume project --posting <id>` then
`tailor run <id> --resume …`. Folding projection into `tailor run` would require `tailor` to know
about the bundle, which is the wall this design keeps up. Two accepted costs: the JD is read twice
and the résumé compiles twice.

- [ ] **Steps:** failing test (writes both `resume.projected.yaml` and `projection-manifest.json`
  beside each other; the emitted document loads through `load_resume`; the wall test still passes)
  → implement → `make check` → commit as
  `"Add resume project, the posting-aware projection command"`.

---

# Slice PM — the owner-labeled selection matrix

**This is Mit's task, not an implementer's. It is one session, it blocks Task 21's *selection* (not
its code), and it is what ends the scorer loop.**

**Gate:** labels exist and are committed.

Two design rounds produced two scorers and an executable probe falsified both — round 1's
`|skills ∩ jd_skills|` lost to `4 > 2` (a shallow four-bullet entry beat a focused one-bullet entry
against a data JD), and round 2's mean-per-bullet coverage lost to `2.0 > 1.5` (a one-bullet entry
matching two JD skills beat a six-bullet entry matching nine). **A third hand-picked formula would be
falsified by a third probe**, because "which formula picks the projects a human would pick" is an
empirical question that two rounds kept trying to answer analytically.

### Task 20: Record the matrix

**Files:** create `docs/program/projection-selection-matrix.md`.

A prose document, not a data file — **deliberately**, so it needs no `SHIPPED_DATA` entry and cannot
drift into a fixture that agrees with the scorer.

**It must be recorded before any scorer is tuned against it.** A matrix labeled after seeing a
scorer's output is a test that agrees with itself.

Format, one block per posting, ten postings spanning the owner's role families:

```markdown
## Posting <id> — <company>, "<title>"  ·  role family: <family>

JD skills extracted (`boardwatch show <id>`): <list>

Expected candidate entries, best first. Rank ties are allowed; write them on one line.

1. <entity_id>
2. <entity_id>
3. <entity_id>
—— below here should NOT appear ——
- <entity_id>
```

The line marking where relevance stops is what sets the **admission threshold**, not just the scorer
ranking. Both come from this one measurement; picking either number in a design document would be
the same mistake as picking a formula there.

- [ ] **Step 1:** pick ten real open postings spanning the role families (`boardwatch top`).
- [ ] **Step 2:** for each, record the extracted JD skills verbatim.
- [ ] **Step 3:** rank the candidate entries by hand, and draw the cut line.
- [ ] **Step 4:** commit — `"Record the owner-labeled projection selection matrix"`. **Do not run
      any scorer before this commit lands.**

---

# Slice P4 — stage 2, with the scorer chosen by measurement

**Gate:** the winning scorer's rank agreement recorded in `METRICS.md`; roomy-budget negative control
green.

**This plan names no winning scorer.** Task 21 builds four candidates behind one interface; Task 22
measures them against the matrix; the winner is a *measurement output*.

### Task 21: The scorer protocol and four candidates

**Files:** create `src/boardwatch/projection/scoring.py`; test `tests/projection/test_projection_scoring.py`.

**Interfaces:**
- Produces: `EntryScorer` protocol (`__call__(entry: Entry, jd_skills, table, taxonomy) -> Decimal`),
  and `SCORERS: Mapping[str, EntryScorer]` with exactly these four keys:
  - `mean_per_bullet` — mean over bullets of `|effective_skills(...) ∩ jd_skills|`
  - `total_distinct` — `|union of effective_skills over bullets ∩ jd_skills|`
  - `mean_top_k` — mean over the **top-`MAX_BULLETS_PER_ENTRY`** bullets only, which removes the
    truncation disagreement by construction
  - `coverage_then_density` — lexicographic `(total_distinct, mean_per_bullet)`

All four call `effective_skills` from Task 1. **`Decimal`, not `float`** — a score reaches the
manifest, and `canonical._normalize` raises on floats.

- [ ] **Step 1: Write the failing test pinning BOTH demonstrated biases**

```python
"""Both probes that falsified a design round, as executable fixtures.

The design cited these numbers but no fixture, script or log for them exists in the repo — they
lived in external reviewers' contexts. So they are AUTHORED here rather than named, which is this
repo's own rule: a plan fixture must be run against the real schema, not referenced.

Neither test asserts a winner. Each records which scorers survive which bias, so Task 22's
measurement is interpreted against known trade-offs rather than surprised by them.
"""

from __future__ import annotations

import re

import pytest

from boardwatch.extract.taxonomy import Taxonomy, TaxonomyPattern
from boardwatch.projection.scoring import SCORERS
from boardwatch.tailor.equivalences import EquivalenceTable
from boardwatch.tailor.model import Bullet, Entry

JD = {"airflow", "snowflake", "dbt", "spark", "kafka", "python", "sql", "terraform", "aws"}


def _taxonomy() -> Taxonomy:
    return Taxonomy(
        patterns=tuple(
            TaxonomyPattern(name=n, category="tool", pattern=n, case_sensitive=False,
                            regex=re.compile(n, re.IGNORECASE))
            for n in JD
        ),
        version="probe-1",
        source="bundled",
    )


def _entry(entry_id: str, *texts: str) -> Entry:
    return Entry(
        entry_id=entry_id,
        heading=entry_id,
        bullets=[Bullet(bullet_id=f"{entry_id}.{i}", text=t) for i, t in enumerate(texts)],
    )


FOCUSED_ONE = _entry("entry.focused", "Built an airflow and snowflake ingestion pipeline")
SHALLOW_FOUR = _entry(
    "entry.shallow",
    "Attended a snowflake vendor talk",
    "Ran one airflow job during an internship",
    "Read about dbt",
    "Saw a spark demo",
)
COMPREHENSIVE_SIX = _entry(
    "entry.comprehensive",
    "Built airflow DAGs and snowflake models",
    "Wrote dbt transformations and spark jobs",
    "Ran kafka ingestion in python",
    "Tuned sql warehouses",
    "Provisioned terraform on aws",
    "Wrote documentation",
)


@pytest.mark.parametrize("name", sorted(SCORERS))
def test_round_one_bias_the_shallow_entry_must_not_beat_the_focused_one(name: str) -> None:
    """Round 1's probe: `4 > 2`. An unnormalized count lifts a size bias to entry level that
    does not exist at bullet level, because `build_plan` ranks bullets independently."""
    scorer = SCORERS[name]
    table, taxonomy = EquivalenceTable((), "v"), _taxonomy()
    focused = scorer(FOCUSED_ONE, JD, table, taxonomy)
    shallow = scorer(SHALLOW_FOUR, JD, table, taxonomy)
    if name == "total_distinct":
        pytest.xfail("total_distinct is the scorer this probe falsified; recorded, not hidden")
    assert focused >= shallow, f"{name}: focused={focused} shallow={shallow}"


@pytest.mark.parametrize("name", sorted(SCORERS))
def test_round_two_bias_the_comprehensive_entry_must_not_lose_to_the_narrow_one(name: str) -> None:
    """Round 2's probe: `2.0 > 1.5`. A one-bullet entry matching two JD skills beat a six-bullet
    entry matching nine — density over coverage."""
    scorer = SCORERS[name]
    table, taxonomy = EquivalenceTable((), "v"), _taxonomy()
    comprehensive = scorer(COMPREHENSIVE_SIX, JD, table, taxonomy)
    focused = scorer(FOCUSED_ONE, JD, table, taxonomy)
    if name == "mean_per_bullet":
        pytest.xfail("mean_per_bullet is the scorer this probe falsified; recorded, not hidden")
    assert comprehensive >= focused, f"{name}: comp={comprehensive} focused={focused}"


#: Six bullets that each match a JD skill, then six that match nothing. `MAX_BULLETS_PER_ENTRY`
#: is 6, so `build_plan` keeps exactly the first six — the scorer must agree with that cap.
MATCHING_SIX = [
    "Built airflow DAGs",
    "Wrote dbt models",
    "Ran spark jobs",
    "Tuned sql warehouses",
    "Used kafka streams",
    "Provisioned aws infrastructure",
]
FILLER_SIX = [f"Wrote internal documentation, part {i}" for i in range(6)]


def test_no_scorer_penalises_a_bullet_the_cap_would_keep() -> None:
    """The truncation-agreement requirement. A twelve-bullet entry whose six matching bullets are
    exactly the survivors of `MAX_BULLETS_PER_ENTRY` must not be scored down for the six it loses.
    """
    twelve = _entry("entry.twelve", *(MATCHING_SIX + FILLER_SIX))
    six = _entry("entry.six", *MATCHING_SIX)
    table, taxonomy = EquivalenceTable((), "v"), _taxonomy()

    # The premise: the filler really does match nothing, or the two entries are trivially equal
    # and this test would pass without the cap-awareness it exists to check.
    from boardwatch.tailor.plan import effective_skills

    assert all(not (effective_skills(t, JD, table, taxonomy) & JD) for t in FILLER_SIX)

    scorer = SCORERS["mean_top_k"]
    assert scorer(twelve, JD, table, taxonomy) == scorer(six, JD, table, taxonomy)
```

- [ ] **Steps 2-5:** run to verify failure → implement the four scorers → run and record **which
  scorer xfails which probe, as a table in the commit message** → commit as
  `"Add four candidate entry scorers behind one interface, naming no winner"`.

### Task 22: The rank-agreement harness

**Files:** create `src/boardwatch/projection/agreement.py`; test `tests/projection/test_projection_agreement.py`.

- [ ] **Interfaces:** `rank_agreement(expected: Sequence[str], actual: Sequence[str]) -> Decimal`
  (Kendall tau-b, handling the ties the matrix format allows) and
  `score_all(matrix, pool, ...) -> Mapping[str, Decimal]`.
- [ ] Tests: perfect agreement is 1; exact reversal is -1; a tie in `expected` does not penalise
  either order in `actual`. **Then run it against Task 20's matrix and record every scorer's
  agreement in `METRICS.md`.** A scorer no better than the others is a finding, not a failure.
- [ ] The winner ships as v1's deterministic default. **The admission threshold comes from the same
  measurement** — the matrix's cut line — not from a number chosen here. Until it exists, `> 0` is
  the placeholder and is documented as one.

### Task 23: Selection — admission floor, fallback, budget fit

**Files:** create `src/boardwatch/projection/select.py`; test `tests/projection/test_projection_select.py`.

Algorithm, pinned to one reading: emit all pinned entries in declared order, never scored, never
dropped; rank candidates above the threshold descending, ties by total distinct matched skills then
by declared order; **add one candidate, compile, repeat until the budget is exceeded, then drop the
last-added candidate and stop** — at most `n+1` compiles, not `2n`; if the pinned set alone exceeds
the budget, fail with `PINNED_SET_EXCEEDS_BUDGET` naming the pinned set **and the actionable knob**.

**The compile gate has four arms and only `PAGE_LIMIT_EXCEEDED` drops a candidate.**
`BINARY_MISSING` and `COMPILE_FAILED` are **fatal infrastructure failures**, never overflow. This is
not hypothetical: `_pdf_page_count` has **three** `None` returns (`reports/tailor.py:171`, `:174`,
`:176`) and `:193-197` launders every one into `COMPILE_FAILED`, so a missing `pdfinfo` would
otherwise drop every candidate one compile at a time and then blame the owner's pinned content.

The result is the **largest fitting score-prefix, not a knapsack optimum** — a long mid-score entry
can crowd out two short lower-score ones. Named and accepted.

- [ ] Required tests, each its own case: a data JD and a mobile JD over one pool select **different**
  candidates; the pinned set is **byte-identical** across both; **with a roomy budget an unrelated
  zero-score candidate stays out** (the test that would have caught revision 1's missing floor); a
  JD matching nothing yields **exactly** `no_match_fallback`; a stubbed compile returning
  `COMPILE_FAILED` **fails named and drops nothing**; a pinned-only overflow reports the typed
  failure with its knob.
- [ ] Commit as `"Select entries against the JD within the page budget, four gate arms honoured"`.

---

# Deferred slices — declared, not written

These are **deliberately not decomposed into tasks**, because doing so now would be speculative.

| Slice | Content | Why deferred | Gate when written |
|---|---|---|---|
| **P5** | Pipeline integration: projection inside `boardwatch run`, manifest validation, artifact lineage | **Committed by Mit, built after v1.** Its *form* is open (an opt-in `boardwatch run --project`, or a pipeline stage). §8 requires `resume.yaml` stay the pipeline default until projection is proven on real JDs, and hand-running is how it gets proven | a stale manifest is **detected**, not merely inspectable. **Re-verify the import wall** — `pipeline/runner.py` importing projection is the one way an edge reappears. Scope it as "add lineage keys to `_trace`'s already-rich meta dict", not "there is no metadata" |
| **P6** | Opt-in model re-ranker, fail-open to the deterministic result | v2 by design. Without a deterministic baseline, "the model picks good projects" is unfalsifiable | beats the winning deterministic scorer on the **same** matrix |

Carried open questions (spec §12), unchanged by this plan: whether `tailor run` should validate the
manifest (it would close the stale-document path but crosses the wall); whether the persona's
`entries` list survives stage 2 (Task 15 forbids the combination rather than reconciling it);
cross-revision claim succession (`ClaimRecord` has no supersession edge, unlike `FactRecord`);
renderer ownership of header/education/summary; and persona role families being a closed
software-only catalog (`extract/role_family.py:11` — **not** `persona.py:27-34`, which is the
derivation), which bounds the multi-tenancy claim until that catalog moves to data.

---

## Self-Review

**1. Spec coverage.** Every section maps to a task: §3 scope → Tasks 7, 12; §4 architecture and CLI
→ Tasks 18, 19; §4.1 declaration and grammar → Tasks 3, 5; §4.2 artifacts → Tasks 11, 13; §5 stage 1
and the owner gate → Tasks 9, 10, 12; §6 stage 2 → Tasks 21-23; §7 fidelity contract → Tasks 3, 6, 7,
8, 15; §8 fatal-uniformly → Task 2's catalog plus every task's refusal tests; §9 testing → distributed;
§10 delivery → the slice headings; §11 out-of-scope → Global Constraints; §12 → carried above.

**Deliberate gaps, each with a reason:** §6's summary prose (the renderer has no `SUMMARY` handler);
§2.4's `tech_tags` lineage (recorded in Task 12's test, not "fixed"); §4.2's stale-lineage detection
(v1 does not close it — Task 13 says so in the module docstring and P5 owns it).

**2. Placeholder scan.** Three steps are intentionally compressed rather than placeheld — Tasks 13,
14, 15, 16, 17, 22 and 23 give interfaces, required test cases and the commit message but not full
literal bodies. That is a real reduction in density from Tasks 1-12 and the executor should expect to
write more of those themselves. Everywhere a decision could be invented — the value-render table, the
grammar, the serializer, the effectiveness gate, the four scorers — the code is literal.

**3. Type consistency.** `effective_skills(text, jd_skills, table, taxonomy)` is used with that name
and order in Tasks 1 and 21. `ProjectionIssue` members referenced in later tasks all exist in Task 2's
enum. `project_pool(bundle_root, declaration_path, *, config_dir, as_of)` is consistent across Tasks
12, 14, 18, 19. `Decimal` is the score type in Tasks 13, 21, 22, 23. `EntryKind` is `StrEnum` in Tasks
3, 6.

**One inconsistency to fix at execution time:** Task 6's conftest re-export
(`from tests.projection.conftest import bundle_ctx  # noqa: F401`) is not how pytest fixtures compose
— a fixture defined in `tests/projection/conftest.py` is available to every module in that directory
with no import at all. Delete those import lines when writing the files; they are harmless but
misleading, and `ruff` may flag them.
