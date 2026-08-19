# Seniority Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop off-target leads reaching the daily shortlist by adding a rank-time seniority gate with an auditable abstain path, plus a guarded bare-`coordinator` deny in the role gate.

**Architecture:** A new `rank/seniority_gate.py` mirrors `rank/role_gate.py` — ordered patterns, every non-pass verdict carrying the text that decided it. Seniority meanings live in a versioned YAML catalog split into a universal tier (level grammars, named company-free schemes) and a field tier (word→band, roman→band, keyed by career field). The company→scheme binding lives in **user config**, keyed on `(provider, slug)`, so shipped data contains zero company names. Only a confident word or bound-scheme hit drops; everything else passes **flagged and counted**.

**Tech Stack:** Python 3.11–3.13, SQLAlchemy Core, Alembic, pydantic v2, typer, pytest, PyYAML.

**Spec:** `docs/superpowers/specs/2026-08-19-seniority-gate-design.md` (revision 2)
**Self-review of that spec:** `docs/superpowers/specs/2026-08-19-seniority-gate-design-review.md`

## Global Constraints

- **`make check` is the only gate.** pytest + ruff + mypy passing individually is *not* green. Run it in plain mode; **never** pipe it through `head`/`tail` (SIGPIPE gives a false negative). It takes 4.5–35 min — batch edits before running.
- **`git add` new files before `make check`.** The generalization checker enumerates via `git ls-files`; an untracked file is invisible to R7 and the gate passes falsely.
- **No AI attribution** in commits, branches, or PRs. No `Co-Authored-By`, no "Generated with".
- **Typed violations at the raise site** — never classify behaviour by string-matching a message.
- **Closed, versioned catalogs.** Out-of-catalog ⇒ a raise, never a new bucket.
- **Fail direction:** `uncertain` ⇒ pass-through **flagged**. Only a confident hit drops. An unset target band ⇒ gate inert **and reported**.
- **Never use `boardwatch doctor` as a read-only check** — it writes. Query the live store with `sqlite3 "file:<db>?immutable=1"`.
- **Band vocabulary is closed:** `entry | mid | senior | staff_plus`. Target vocabulary is closed: `entry | mid | senior | any`.
- Narrow pytest runs need `--no-cov` (the suite sets `--cov-fail-under=85`) and `-n 0`.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/boardwatch/rank/leveling.yaml` | **Create.** Versioned catalog: level grammars, named company-free schemes, field-tier word/roman maps. No company names. |
| `src/boardwatch/rank/leveling.py` | **Create.** Loader + closed-vocabulary validation + `LevelingCatalog` / `LevelScheme` types + binding loader. |
| `src/boardwatch/rank/seniority_gate.py` | **Create.** `parse_seniority` / `seniority_verdict`. Pure functions, no I/O. |
| `src/boardwatch/rank/role_gate.py` | Modify. One appended soft-deny pattern. |
| `src/boardwatch/rank/heuristic.py` | Modify. `ProfileView` gains `target_seniority_band`. |
| `src/boardwatch/store/tables.py` + new migration | Modify/create. `profile.target_seniority_band`. |
| `src/boardwatch/store/queries.py` | Modify. `save_profile` — signature, `.values()`, `set_`. |
| `src/boardwatch/cli/profile_cmd.py` | Modify. `ProfileInput`, `persist_profile`, `edit` prompt, `show` line. |
| `src/boardwatch/reports/manifest.py` | Modify. `profile_row_hash` + `policy_version` gain the band and the leveling digest. |
| `src/boardwatch/pipeline/policy.py`, `pipeline/funnel_writer.py` | Modify. Both `profile_row_hash` call sites. |
| `src/boardwatch/cli/top_cmd.py` | Modify. Bucket, drain, counters, observability, select columns. |
| `src/boardwatch/reports/run_funnel.py`, `pipeline/runner.py`, `cli/run_cmd.py` | Modify. Funnel mirror sites. |
| `src/boardwatch/reports/notify.py`, `reports/stats.py`, `cli/show_cmd.py` | Modify. The other two filter chains + the audit surface. |
| `tools/generalization/allowlists.py`, `tools/generalization/defaults.py` | Modify. R7 entry + `SCOPED_MODULES`. |

---

## Task 1: Guarded bare-`coordinator` deny in the role gate

Independent of everything else. Ship it first — it closes half of D-245 on its own.

**Files:**
- Modify: `src/boardwatch/rank/role_gate.py` (the `_DENY_BUSINESS_SOFT` tuple)
- Test: `tests/unit/test_role_gate.py`

**Interfaces:**
- Consumes: nothing.
- Produces: no new symbols. `role_verdict(title) -> tuple[RoleVerdict, str]` is unchanged in shape.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_role_gate.py`:

```python
class TestCoordinatorDeny:
    """A bare `… Coordinator` with no engineering noun is not a software role (D-245).

    Measured 2026-08-19 over 26,997 live open postings: 135 postings / 125 distinct titles
    flip `uncertain` -> `not_swe`, and ZERO `swe`-classified titles contain `coordinator`,
    so the deny cannot bury a software job.
    """

    @pytest.mark.parametrize("title", [
        "Disaster Response Coordinator",          # the D-245 lead
        "Talent Coordinator",
        "Workplace Coordinator",
        "People Ops Coordinator",
        "Coordinator, Content Operations",
    ])
    def test_bare_coordinator_is_vetoed(self, title: str) -> None:
        verdict, reason = role_verdict(title)
        assert verdict == "not_swe"
        assert "coordinator" in reason.lower()

    @pytest.mark.parametrize("title", [
        # The _NOENG guard spares anything carrying an engineering noun anywhere.
        "Administrative Coordinator - College of Engineering - Information Networking Institute",
        "Student Program Coordinator, Engineering Student Success Center",
        # A real software title must never reach the soft denies at all.
        "Software Engineer, Release Coordinator Tooling",
    ])
    def test_engineering_titles_are_never_vetoed_by_the_coordinator_deny(self, title: str) -> None:
        assert role_verdict(title)[0] != "not_swe"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_role_gate.py::TestCoordinatorDeny -v --no-cov -n 0`
Expected: the five `test_bare_coordinator_is_vetoed` cases FAIL with `assert 'uncertain' == 'not_swe'`. The three guard cases already PASS — that is correct and proves they are not accidentally protected by the new pattern.

- [ ] **Step 3: Add the pattern**

In `src/boardwatch/rank/role_gate.py`, append as the **last** entry of the `_DENY_BUSINESS_SOFT` tuple (order inside the soft list does not affect the verdict, only the reported match; last keeps the diff surgical):

```python
    # Bare `coordinator`, anchor-guarded (D-245). "Disaster Response Coordinator" reached the
    # shortlist on run 61 because it verdicts `uncertain` and the ranker passes `uncertain`
    # through. Measured over 26,997 open postings: 135 flip to not_swe, all non-software, and
    # 0 `swe`-classified titles contain the word, so this cannot bury a software job. The
    # anchored guard additionally spares 4 administrative roles at engineering schools.
    _NOENG + r"\bcoordinator\b",
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_role_gate.py -v --no-cov -n 0`
Expected: PASS, including every pre-existing test in the file.

- [ ] **Step 5: Commit**

```bash
git add src/boardwatch/rank/role_gate.py tests/unit/test_role_gate.py
git commit -m "Veto bare Coordinator titles in the role gate

Measured over 26,997 live open postings: 135 postings flip from uncertain to
not_swe and none of them is a software role, while zero swe-classified titles
contain the word, so the deny cannot bury a real job."
```

---

## Task 2: The leveling catalog and its loader

**Files:**
- Create: `src/boardwatch/rank/leveling.yaml`
- Create: `src/boardwatch/rank/leveling.py`
- Test: `tests/unit/test_leveling_catalog.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `LEVELING_VERSION: int = 1`
  - `class LevelingError(ValueError)`
  - `SeniorityBand = Literal["entry", "mid", "senior", "staff_plus"]`
  - `@dataclass(frozen=True) LevelScheme: name: str; grammar: str; levels: Mapping[str, SeniorityBand]`
  - `@dataclass(frozen=True) FieldTier: words: Mapping[str, SeniorityBand]; roman: Mapping[str, SeniorityBand]`
  - `@dataclass(frozen=True) LevelingCatalog: version: int; ambiguous_grammars: frozenset[str]; schemes: Mapping[str, LevelScheme]; fields: Mapping[str, FieldTier]; digest: str`
  - `def load_leveling(config_dir: Path) -> LevelingCatalog`
  - `def load_bindings(config_dir: Path) -> dict[tuple[str, str], str]` — `(provider, slug) -> scheme name`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_leveling_catalog.py`:

```python
from pathlib import Path

import pytest

from boardwatch.rank.leveling import (
    LEVELING_VERSION,
    LevelingError,
    load_bindings,
    load_leveling,
)


def test_bundled_catalog_loads_and_pins_its_version(tmp_path: Path) -> None:
    catalog = load_leveling(tmp_path)
    assert catalog.version == LEVELING_VERSION
    assert catalog.digest  # content-addressed, for policy_version


def test_software_field_tier_carries_the_measured_words(tmp_path: Path) -> None:
    words = load_leveling(tmp_path).fields["software"].words
    assert words["senior"] == "senior"
    assert words["leader"] == "senior"        # required: `Lead` c `Leader` (spec 3.5)
    assert words["distinguished"] == "staff_plus"
    assert words["vice president"] == "staff_plus"
    # Measured false drop: `fellow` kills early-career fellowships (spec 3.4).
    assert "fellow" not in words
    # Dropped as ambiguous or field-inverting.
    for absent in ("architect", "specialist", "associate", "expert", "advanced", "master"):
        assert absent not in words


def test_bare_letter_grammars_are_declared_ambiguous(tmp_path: Path) -> None:
    catalog = load_leveling(tmp_path)
    assert "l_prefix" in catalog.ambiguous_grammars
    assert "e_prefix" in catalog.ambiguous_grammars
    assert "level_n" not in catalog.ambiguous_grammars


def test_no_company_name_appears_in_the_shipped_catalog(tmp_path: Path) -> None:
    """Shipped data must contain zero company names (spec 2.1); bindings are user config."""
    from importlib.resources import files

    text = (files("boardwatch.rank") / "leveling.yaml").read_text(encoding="utf-8").lower()
    for company in ("snap", "twilio", "google", "meta", "amazon", "microsoft", "cisco"):
        assert company not in text


def _write(tmp_path: Path, body: str) -> Path:
    (tmp_path / "leveling.yaml").write_text(body, encoding="utf-8")
    return tmp_path


def test_out_of_catalog_band_raises_rather_than_bucketing(tmp_path: Path) -> None:
    cfg = _write(tmp_path, """
leveling_version: 1
grammars: {level_n: {kind: self_describing}}
schemes: {s: {grammar: level_n, levels: {"5": archmage}}}
fields: {software: {words: {}, roman: {}}}
""")
    with pytest.raises(LevelingError, match="archmage"):
        load_leveling(cfg)


def test_unquoted_yaml_boolean_level_key_raises(tmp_path: Path) -> None:
    """YAML 1.1: an unquoted `no`/`on`/`y` loads as a bool and becomes a plausible token."""
    cfg = _write(tmp_path, """
leveling_version: 1
grammars: {level_n: {kind: self_describing}}
schemes: {s: {grammar: level_n, levels: {no: senior}}}
fields: {software: {words: {}, roman: {}}}
""")
    with pytest.raises(LevelingError, match="QUOTE"):
        load_leveling(cfg)


def test_version_mismatch_raises(tmp_path: Path) -> None:
    cfg = _write(tmp_path, """
leveling_version: 99
grammars: {}
schemes: {}
fields: {software: {words: {}, roman: {}}}
""")
    with pytest.raises(LevelingError, match="99"):
        load_leveling(cfg)


def test_scheme_naming_an_unknown_grammar_raises(tmp_path: Path) -> None:
    cfg = _write(tmp_path, """
leveling_version: 1
grammars: {level_n: {kind: self_describing}}
schemes: {s: {grammar: nonesuch, levels: {"5": senior}}}
fields: {software: {words: {}, roman: {}}}
""")
    with pytest.raises(LevelingError, match="nonesuch"):
        load_leveling(cfg)


def test_bindings_default_to_empty(tmp_path: Path) -> None:
    assert load_bindings(tmp_path) == {}


def test_bindings_are_keyed_on_provider_and_slug(tmp_path: Path) -> None:
    (tmp_path / "leveling-bindings.yaml").write_text(
        'bindings:\n'
        '  - provider: workday\n'
        '    slug: snapchat.wd1.myworkdayjobs.com/snapchat/snap\n'
        '    scheme: ic_1_to_7\n',
        encoding="utf-8",
    )
    got = load_bindings(tmp_path)
    assert got == {("workday", "snapchat.wd1.myworkdayjobs.com/snapchat/snap"): "ic_1_to_7"}
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_leveling_catalog.py -v --no-cov -n 0`
Expected: FAIL — `ModuleNotFoundError: No module named 'boardwatch.rank.leveling'`.

- [ ] **Step 3: Write the catalog**

Create `src/boardwatch/rank/leveling.yaml`:

```yaml
# Seniority leveling catalog (D-246). Universal tier = the mechanism; field tier = meanings.
#
# THIS FILE CONTAINS NO COMPANY NAMES, deliberately. A company's leveling scheme is not a
# fact boardwatch can ship — the board list is per-operator — so the company -> scheme
# binding lives in {config_dir}/leveling-bindings.yaml. An unbound level ABSTAINS.
leveling_version: 1

# Which token shapes are levels at all. Measured 2026-08-19 over 26,997 open postings.
grammars:
  # "Level 5" names itself. All 33 live hits are genuine levels.
  level_n: {kind: self_describing}
  # Bare letter+digit is usually NOT a level: of 45 live `L#` hits, most are OSI layer 2,
  # support tiers, or facility codes. These never resolve, whatever the binding says.
  l_prefix: {kind: ambiguous}
  e_prefix: {kind: ambiguous}
  ic_prefix: {kind: ambiguous}
  t_prefix: {kind: ambiguous}

# Named, company-free rung ladders. An operator binds a company to one of these by name.
schemes:
  ic_1_to_7:
    grammar: level_n
    levels: {"1": entry, "2": entry, "3": entry, "4": mid,
             "5": senior, "6": staff_plus, "7": staff_plus}
  ic_1_to_6:
    grammar: level_n
    levels: {"1": entry, "2": entry, "3": mid, "4": senior,
             "5": staff_plus, "6": staff_plus}

# Field tier: what the WORDS mean. An unresolvable career field abstains rather than
# defaulting to software, because these invert by field (a postdoc Fellow is entry-level).
fields:
  software:
    words:
      senior: senior
      "sr": senior
      lead: senior
      leader: senior          # required: `Lead` is a substring of `Leader`
      manager: senior
      staff: staff_plus
      principal: staff_plus
      distinguished: staff_plus
      director: staff_plus
      "vp": staff_plus
      "vice president": staff_plus
      "head of": staff_plus   # dormant: 0 hits measured 2026-08-19
      chief: staff_plus       # dormant: 0 hits measured 2026-08-19
    roman: {"II": mid, "III": senior, "IV": senior}
```

- [ ] **Step 4: Write the loader**

Create `src/boardwatch/rank/leveling.py`:

```python
"""Seniority leveling catalog (D-246).

Structurally mirrors `eligibility/catalog.py` and `extract/taxonomy.py`: a bundled YAML with a
`{config_dir}` override that wins, closed vocabularies that raise rather than bucket, and a
content digest so a run's manifest can name the catalog it ran under.

The catalog is UNCACHED on purpose, for the same reason its two siblings are: an override may
appear between calls. Callers load it ONCE per rank and pass the result into the loop —
`role_verdict` is tuned to 0.30s over 19,262 postings, so a per-row load is a real regression.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Literal

import yaml

LEVELING_VERSION = 1

SeniorityBand = Literal["entry", "mid", "senior", "staff_plus"]

_BANDS: frozenset[str] = frozenset({"entry", "mid", "senior", "staff_plus"})
_GRAMMAR_KINDS: frozenset[str] = frozenset({"self_describing", "ambiguous"})
# YAML 1.1 turns these into bools when unquoted, which would silently become a token.
_YAML_BOOLISH = "unquoted no/yes/on/off/true/false are YAML booleans"


class LevelingError(ValueError):
    """A schema or vocabulary error, message naming the offending value."""


@dataclass(frozen=True)
class LevelScheme:
    name: str
    grammar: str
    levels: Mapping[str, SeniorityBand]


@dataclass(frozen=True)
class FieldTier:
    words: Mapping[str, SeniorityBand]
    roman: Mapping[str, SeniorityBand]


@dataclass(frozen=True)
class LevelingCatalog:
    version: int
    ambiguous_grammars: frozenset[str]
    self_describing_grammars: frozenset[str]
    schemes: Mapping[str, LevelScheme]
    fields: Mapping[str, FieldTier]
    digest: str


def _text(config_dir: Path) -> str:
    override = config_dir / "leveling.yaml"
    if override.is_file():
        return override.read_text(encoding="utf-8")
    return (files("boardwatch.rank") / "leveling.yaml").read_text(encoding="utf-8")


def _band(value: object, where: str) -> SeniorityBand:
    if not isinstance(value, str):
        raise LevelingError(f"{where}: band {value!r} is {type(value).__name__}, not a string. "
                            f"QUOTE it: {_YAML_BOOLISH}")
    if value not in _BANDS:
        raise LevelingError(f"{where}: unknown band {value!r}; known: {', '.join(sorted(_BANDS))}")
    return value  # type: ignore[return-value]


def _key(value: object, where: str) -> str:
    if not isinstance(value, str):
        raise LevelingError(f"{where}: key {value!r} is {type(value).__name__}, not a string. "
                            f"QUOTE it: {_YAML_BOOLISH}")
    return value


def load_leveling(config_dir: Path) -> LevelingCatalog:
    raw = yaml.safe_load(_text(config_dir)) or {}
    if not isinstance(raw, dict):
        raise LevelingError("leveling.yaml: top level must be a mapping")

    version = raw.get("leveling_version")
    if version != LEVELING_VERSION:
        raise LevelingError(
            f"leveling.yaml: leveling_version {version!r} disagrees with the builtin "
            f"{LEVELING_VERSION}"
        )

    ambiguous: set[str] = set()
    self_describing: set[str] = set()
    for name, body in (raw.get("grammars") or {}).items():
        gname = _key(name, "grammars")
        kind = (body or {}).get("kind")
        if kind not in _GRAMMAR_KINDS:
            raise LevelingError(f"grammar {gname!r}: unknown kind {kind!r}")
        (ambiguous if kind == "ambiguous" else self_describing).add(gname)

    schemes: dict[str, LevelScheme] = {}
    for name, body in (raw.get("schemes") or {}).items():
        sname = _key(name, "schemes")
        grammar = (body or {}).get("grammar")
        if grammar not in self_describing:
            raise LevelingError(
                f"scheme {sname!r}: grammar {grammar!r} is not a self-describing grammar; "
                f"known: {', '.join(sorted(self_describing))}"
            )
        levels = {
            _key(k, f"scheme {sname!r}"): _band(v, f"scheme {sname!r} level {k!r}")
            for k, v in ((body or {}).get("levels") or {}).items()
        }
        schemes[sname] = LevelScheme(name=sname, grammar=grammar, levels=levels)

    fields: dict[str, FieldTier] = {}
    for name, body in (raw.get("fields") or {}).items():
        fname = _key(name, "fields")
        words = {
            _key(k, f"field {fname!r} words").casefold(): _band(v, f"field {fname!r} word {k!r}")
            for k, v in ((body or {}).get("words") or {}).items()
        }
        roman = {
            _key(k, f"field {fname!r} roman").upper(): _band(v, f"field {fname!r} roman {k!r}")
            for k, v in ((body or {}).get("roman") or {}).items()
        }
        fields[fname] = FieldTier(words=words, roman=roman)

    # Hash the PARSED document, not the file: the consumer reads the parsed object, so a
    # digest over raw bytes would move on a comment edit and miss a semantic one via override.
    canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(
        f"{canonical}|leveling_version={LEVELING_VERSION}".encode()
    ).hexdigest()

    return LevelingCatalog(
        version=LEVELING_VERSION,
        ambiguous_grammars=frozenset(ambiguous),
        self_describing_grammars=frozenset(self_describing),
        schemes=schemes,
        fields=fields,
        digest=digest,
    )


def load_bindings(config_dir: Path) -> dict[tuple[str, str], str]:
    """Company -> scheme, keyed on (provider, slug) — the pair the store and registry agree on.

    User config, never shipped: which companies you watch is yours. Absent file => no bindings
    => every level token abstains and is reported, which is the honest default.
    """
    path = config_dir / "leveling-bindings.yaml"
    if not path.is_file():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: dict[tuple[str, str], str] = {}
    for row in raw.get("bindings") or []:
        provider, slug, scheme = row.get("provider"), row.get("slug"), row.get("scheme")
        for label, value in (("provider", provider), ("slug", slug), ("scheme", scheme)):
            if not isinstance(value, str) or not value:
                raise LevelingError(f"leveling-bindings.yaml: {label} must be a non-empty string")
        out[(provider, slug)] = scheme
    return out
```

- [ ] **Step 5: Run to verify they pass**

Run: `uv run pytest tests/unit/test_leveling_catalog.py -v --no-cov -n 0`
Expected: PASS (11 tests).

- [ ] **Step 6: Commit**

```bash
git add src/boardwatch/rank/leveling.yaml src/boardwatch/rank/leveling.py tests/unit/test_leveling_catalog.py
git commit -m "Add the seniority leveling catalog and its loader

The catalog ships zero company names: a company's rung ladder is not a fact
boardwatch can ship, because the board list is per-operator, so the company to
scheme binding is user config keyed on (provider, slug). Bare letter-digit
tokens are declared ambiguous and never resolve, since most live L2 hits are
OSI layer 2, support tiers or facility codes rather than job levels."
```

---

## Task 3: The seniority gate

**Files:**
- Create: `src/boardwatch/rank/seniority_gate.py`
- Test: `tests/unit/test_seniority_gate.py`

**Interfaces:**
- Consumes: `LevelScheme`, `FieldTier`, `SeniorityBand`, `LevelingCatalog` from Task 2.
- Produces:
  - `TargetBand = Literal["entry", "mid", "senior", "any"]`
  - `SeniorityVerdict = Literal["in_band", "above_band", "uncertain"]`
  - `BAND_ORDER: dict[str, int]`
  - `def parse_seniority(title: str, scheme: LevelScheme | None, tier: FieldTier, catalog: LevelingCatalog) -> tuple[SeniorityBand | None, str]`
  - `def seniority_verdict(title: str, scheme: LevelScheme | None, target_band: TargetBand, tier: FieldTier, catalog: LevelingCatalog) -> tuple[SeniorityVerdict, str]`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_seniority_gate.py`:

```python
from pathlib import Path

import pytest

from boardwatch.rank.leveling import load_leveling
from boardwatch.rank.seniority_gate import seniority_verdict


@pytest.fixture
def cat(tmp_path: Path):
    return load_leveling(tmp_path)


@pytest.fixture
def tier(cat):
    return cat.fields["software"]


def V(title, cat, tier, *, scheme=None, target="entry"):
    return seniority_verdict(title, scheme, target, tier, cat)


class TestWordBoundaries:
    @pytest.mark.parametrize("title", [
        "Software Engineer - Cloud SRE",
        "Software Development Engineer, SRE (US Federal)",
        "Software Engineer - Figma Weave (Tel Aviv, Israel)",
    ])
    def test_sr_does_not_match_inside_sre_isr_or_israel(self, title, cat, tier):
        assert V(title, cat, tier)[0] == "in_band"

    def test_leader_is_senior(self, cat, tier):
        verdict, reason = V("Software Engineering Technical Leader", cat, tier)
        assert verdict == "above_band"
        assert "leader" in reason.lower()

    def test_fellow_is_not_a_seniority_word(self, cat, tier):
        # Measured false drop: fellowships are early-career (spec 3.4).
        assert V("SWE Fellow - Human Frontier Collective", cat, tier)[0] == "in_band"

    def test_distinguished_and_vice_president_drop(self, cat, tier):
        assert V("Distinguished Engineer", cat, tier)[0] == "above_band"
        assert V("Full Stack Engineer, Vice President", cat, tier)[0] == "above_band"


class TestRoman:
    def test_engineer_i_is_entry_and_stays(self, cat, tier):
        # Run 61's Affirm lead must be retained.
        assert V("Software Engineer I, Backend (Collections)", cat, tier)[0] == "in_band"

    def test_ii_is_mid_and_drops_at_entry(self, cat, tier):
        assert V("Backend Engineer II", cat, tier)[0] == "above_band"

    def test_ii_stays_when_the_target_is_mid(self, cat, tier):
        assert V("Backend Engineer II", cat, tier, target="mid")[0] == "in_band"


class TestSchemes:
    def test_level_token_without_a_binding_abstains(self, cat, tier):
        verdict, reason = V("Software Engineer, Specs, Level 5", cat, tier)
        assert verdict == "uncertain"
        assert "no scheme" in reason.lower()
        assert "Level 5" in reason

    def test_level_token_with_a_binding_resolves(self, cat, tier):
        scheme = cat.schemes["ic_1_to_7"]
        assert V("Software Engineer, Specs, Level 5", cat, tier, scheme=scheme)[0] == "above_band"
        assert V("Software Engineer, Level 3", cat, tier, scheme=scheme)[0] == "in_band"

    def test_level_outside_the_scheme_range_abstains_with_its_own_reason(self, cat, tier):
        scheme = cat.schemes["ic_1_to_7"]
        verdict, reason = V("Software Architect, Level 9", cat, tier, scheme=scheme)
        assert verdict == "uncertain"
        assert "outside" in reason.lower()

    @pytest.mark.parametrize("title", [
        "Software Development Engineer - Routing Platforms & L2 - Routing",
        "L2 Support Engineer (Automation Focused)",
        "Machine Learning Engineer (T25)",
    ])
    def test_ambiguous_bare_letter_tokens_always_abstain(self, title, cat, tier):
        # Even WITH a scheme bound: L2 is OSI layer 2 here, not a rung.
        assert V(title, cat, tier, scheme=cat.schemes["ic_1_to_7"])[0] == "uncertain"


class TestFailDirection:
    def test_no_token_is_in_band(self, cat, tier):
        assert V("Software Engineer, Content Platform", cat, tier)[0] == "in_band"

    def test_target_any_is_always_in_band_and_says_so(self, cat, tier):
        verdict, reason = V("Distinguished Engineer", cat, tier, target="any")
        assert verdict == "in_band"
        assert "inert" in reason.lower()

    def test_every_non_pass_verdict_names_the_text_that_decided_it(self, cat, tier):
        for title in ("Senior Software Engineer", "Staff Software Engineer", "Backend Engineer II"):
            verdict, reason = V(title, cat, tier)
            assert verdict == "above_band"
            assert reason.strip()
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_seniority_gate.py -v --no-cov -n 0`
Expected: FAIL — `ModuleNotFoundError: No module named 'boardwatch.rank.seniority_gate'`.

- [ ] **Step 3: Write the module**

Create `src/boardwatch/rank/seniority_gate.py`:

```python
"""Title seniority gate: is this posting above the band the operator is targeting? (D-246.)

Mirrors `role_gate` in shape and in discipline — ordered rules, and EVERY non-pass verdict
carries the text that decided it, because a gate you cannot audit is how a real job disappears.

ORDER IS LOAD-BEARING. Field-tier words run before level tokens so that "Staff Software
Engineer, Level 6" reports the word (universal, certain) rather than the level (which needs a
binding and might abstain). Ambiguous grammars are checked BEFORE self-describing ones so a
bound scheme can never rescue an `L2` that is really OSI layer 2.

The fail direction is fixed by the keystone invariant: only a confident word, roman numeral, or
bound-scheme hit may DROP. A level token with no binding, a level outside its scheme's range,
and every ambiguous bare-letter token all return `uncertain`, which the caller passes through
FLAGGED and COUNTS. Absence of any token is `in_band` — silence is never evidence of seniority.

R9 note: listed in `tools/generalization/defaults.py::SCOPED_MODULES` for the same reason
`role_gate` is — it holds TITLE data, and moving title data to an unscoped module to escape the
rule is the evasion R9 exists to catch. The word and band data live in `leveling.yaml`; the
patterns here are built with `tuple(...)` constructor calls, the documented escape hatch.
"""

from __future__ import annotations

import re
from typing import Literal

from boardwatch.rank.leveling import FieldTier, LevelingCatalog, LevelScheme, SeniorityBand

TargetBand = Literal["entry", "mid", "senior", "any"]
SeniorityVerdict = Literal["in_band", "above_band", "uncertain"]

BAND_ORDER: dict[str, int] = {"entry": 0, "mid": 1, "senior": 2, "staff_plus": 3}

# "Level 5" — the one grammar measured to be unambiguous (33/33 live hits are real levels).
_LEVEL_N = re.compile(r"\blevel\s+(\d{1,2})\b", re.IGNORECASE)

# Bare letter+digit. Measured NOT to be levels: OSI layer 2, support tiers, facility codes.
# Matched only so the gate can ABSTAIN loudly instead of silently ignoring them.
_AMBIGUOUS: tuple[re.Pattern[str], ...] = tuple([
    re.compile(r"\b(L\s?-?\d{1,2})\b"),
    re.compile(r"\b(E\s?-?\d{1,2})\b"),
    re.compile(r"\b(IC\s?-?\d{1,2})\b"),
    re.compile(r"\b(T\s?-?\d{1,3})\b"),
])

# Bare roman numerals. `I` is deliberately absent: it is entry, so it can never raise the band,
# and matching it would collide with initials and Roman-numeral product names.
_ROMAN = re.compile(r"\b(I{2,3}|IV)\b")


def parse_seniority(
    title: str,
    scheme: LevelScheme | None,
    tier: FieldTier,
    catalog: LevelingCatalog,
) -> tuple[SeniorityBand | None, str]:
    """Return the title's band and the text that decided it, or (None, reason) to abstain."""
    # 1. Field-tier words, longest first so "vice president" beats "vp".
    for word in sorted(tier.words, key=len, reverse=True):
        if re.search(rf"\b{re.escape(word)}\b", title, re.IGNORECASE):
            return tier.words[word], f'seniority word "{word}"'

    # 2. Ambiguous tokens abstain BEFORE any scheme can resolve them.
    for pattern in _AMBIGUOUS:
        found = pattern.search(title)
        if found is not None:
            return None, (
                f'"{found.group(1)}" looks like a level but that token shape is ambiguous '
                "(it is usually a network layer, support tier or site code), so it never resolves"
            )

    # 3. Self-describing level token.
    level = _LEVEL_N.search(title)
    if level is not None:
        if scheme is None:
            return None, (
                f'"{level.group(0)}" is a level but this company has no scheme bound; '
                "bind one in {config_dir}/leveling-bindings.yaml"
            )
        rung = level.group(1)
        if rung not in scheme.levels:
            return None, (
                f'"{level.group(0)}" is outside scheme {scheme.name!r}, which covers '
                f"{', '.join(sorted(scheme.levels))}"
            )
        return scheme.levels[rung], f'{scheme.name} "{level.group(0)}"'

    # 4. Bare roman numerals, from the field tier.
    roman = _ROMAN.search(title)
    if roman is not None:
        band = tier.roman.get(roman.group(1).upper())
        if band is not None:
            return band, f'roman numeral "{roman.group(1)}"'

    # 5. Nothing found. Absence of signal is never seniority.
    return "entry", "no seniority signal in title"


def seniority_verdict(
    title: str,
    scheme: LevelScheme | None,
    target_band: TargetBand,
    tier: FieldTier,
    catalog: LevelingCatalog,
) -> tuple[SeniorityVerdict, str]:
    """Classify a title against the operator's target band.

    `any` makes the gate inert, and says so rather than passing silently — an inert gate nobody
    knows about is the same monitoring failure as an unreported abstain.
    """
    if target_band == "any":
        return "in_band", "gate inert: target_seniority_band is `any`"
    band, reason = parse_seniority(title, scheme, tier, catalog)
    if band is None:
        return "uncertain", reason
    if BAND_ORDER[band] > BAND_ORDER[target_band]:
        return "above_band", f"{band} above target {target_band} ({reason})"
    return "in_band", reason
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/unit/test_seniority_gate.py -v --no-cov -n 0`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/boardwatch/rank/seniority_gate.py tests/unit/test_seniority_gate.py
git commit -m "Add the rank-time seniority gate

Only a confident word, roman numeral or bound-scheme hit may drop. A level with
no binding, a level outside its scheme range, and every ambiguous bare-letter
token abstain instead, so the caller can pass them through flagged and counted."
```

---

## Task 4: The `target_seniority_band` profile field

**Files:**
- Modify: `src/boardwatch/store/tables.py` (the `profile` table)
- Create: `src/boardwatch/store/migrations/versions/p_seniority_band.py`
- Modify: `src/boardwatch/store/queries.py` (`save_profile`)
- Modify: `src/boardwatch/cli/profile_cmd.py` (`ProfileInput`, `persist_profile`, `edit`, `show`)
- Modify: `src/boardwatch/rank/heuristic.py` (`ProfileView`, `profile_view_from_row`)
- Test: `tests/unit/test_profile_seniority_band.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `ProfileView.target_seniority_band: str` (always a non-empty string, never `None`); `save_profile(..., target_seniority_band: str = "any")`; `persist_profile(..., target_seniority_band: str = "any")`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_profile_seniority_band.py`:

```python
import inspect

from sqlalchemy import select

from boardwatch.rank.heuristic import profile_view_from_row
from boardwatch.reports.manifest import profile_row_hash
from boardwatch.store.queries import get_profile, save_profile
from boardwatch.store.tables import profile


def _save(conn, **over):
    kwargs = dict(
        text="t", target_titles=[], exclude_titles=[], locations=[], remote_only=False,
        skills=[], taxonomy_version="v1", resume_max_pages=1,
    )
    kwargs.update(over)
    save_profile(conn, **kwargs)


def test_band_defaults_to_any_and_is_never_null(engine) -> None:
    with engine.begin() as conn:
        _save(conn)
        row = conn.execute(select(profile)).one()
    assert row.target_seniority_band == "any"


def test_band_round_trips_through_edit(engine) -> None:
    """The set_ map defect: omitting the column makes `profile edit` silently never update it."""
    with engine.begin() as conn:
        _save(conn, target_seniority_band="entry")
        assert get_profile(conn).target_seniority_band == "entry"
        _save(conn, target_seniority_band="senior")
        assert get_profile(conn).target_seniority_band == "senior"


def test_profile_view_exposes_the_band(engine) -> None:
    with engine.begin() as conn:
        _save(conn, target_seniority_band="entry")
        view = profile_view_from_row(get_profile(conn))
    assert view.target_seniority_band == "entry"


def test_profile_view_falls_back_to_any_for_a_row_without_the_column() -> None:
    class Bare:
        pass
    assert profile_view_from_row(Bare()).target_seniority_band == "any"


def test_profile_row_hash_tracks_the_band() -> None:
    base = dict(skills=[], target_titles=[], exclude_titles=[], locations=[], remote_only=False)
    assert profile_row_hash(**base, target_seniority_band="any") != profile_row_hash(
        **base, target_seniority_band="entry"
    )


def test_profile_row_hash_parameter_set_is_pinned() -> None:
    assert set(inspect.signature(profile_row_hash).parameters) == {
        "skills", "target_titles", "exclude_titles", "locations", "remote_only",
        "target_seniority_band",
    }
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_profile_seniority_band.py -v --no-cov -n 0`
Expected: FAIL — `TypeError: save_profile() got an unexpected keyword argument 'target_seniority_band'`.

- [ ] **Step 3: Add the column and the migration**

In `src/boardwatch/store/tables.py`, in the `profile` table, after `resume_max_pages`:

```python
    # D-246. NOT NULL with a server default: `None` and "any" would otherwise be two hash
    # inputs for one behaviour, and `hashing.canonical` keeps an explicit null distinct from
    # a missing key. Closed vocabulary enforced in Python at the write site (ProfileInput),
    # not by a CHECK — retrofitting one to SQLite costs a full table rebuild.
    Column("target_seniority_band", Text, nullable=False, server_default="any"),
```

Create `src/boardwatch/store/migrations/versions/p_seniority_band.py`:

```python
"""D-246: the operator's target seniority band on the profile singleton.

One additive column with a server default of `any`, which makes the seniority gate INERT for
every existing install — the gate reports itself inert rather than changing any behaviour until
the operator narrows the band. ALTER TABLE ADD COLUMN with no table rebuild; downgrade uses
native DROP COLUMN (SQLite >= 3.35), the path p1_resume_max_pages takes.

Unlike resume_max_pages this DOES enter the ranker's profile_row_hash: it drives a funnel drop
bucket, so a run manifest that omitted it would claim two runs identical when the setting
driving the drop changed.
"""

from alembic import op

revision = "p_seniority_band"
down_revision = "runs_status_backfill_repair"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE profile ADD COLUMN target_seniority_band TEXT NOT NULL DEFAULT 'any'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE profile DROP COLUMN target_seniority_band")
```

- [ ] **Step 4: Thread the field through the writer and the view**

In `src/boardwatch/store/queries.py::save_profile`, add to **all three** places — the signature (defaulted, so the 25 existing call sites keep compiling), `.values()`, and the `set_` map:

```python
    target_seniority_band: str = "any",
```
```python
        target_seniority_band=target_seniority_band,
```
```python
            "target_seniority_band": stmt.excluded.target_seniority_band,
```

In `src/boardwatch/rank/heuristic.py`:

```python
@dataclass(frozen=True)
class ProfileView:
    skills: frozenset[str]
    target_titles: tuple[str, ...]
    exclude_titles: tuple[str, ...]
    locations: tuple[str, ...]
    remote_only: bool
    # D-246. `notify` consumes ProfileView too, which is what makes wiring the second filter
    # chain cheap. Falls back to "any" (inert) so a row predating the migration is safe.
    target_seniority_band: str = "any"
```
```python
        target_seniority_band=str(getattr(row, "target_seniority_band", None) or "any"),
```

In `src/boardwatch/cli/profile_cmd.py`, add the closed vocabulary and thread it:

```python
SeniorityBandChoice = Literal["entry", "mid", "senior", "any"]
```
```python
    target_seniority_band: SeniorityBandChoice = "any"
```

and in `persist_profile`'s signature, its `ProfileInput(...)` construction, and its `save_profile(...)` call — **explicitly**, because a defaulted parameter that the caller forgets to pass silently resets the band on every `edit`.

- [ ] **Step 5: Add the `profile_row_hash` parameter**

In `src/boardwatch/reports/manifest.py::profile_row_hash`, add the keyword-only parameter and payload key:

```python
    target_seniority_band: str = "any",
```
```python
        "target_seniority_band": target_seniority_band,
```

Update both call sites — `src/boardwatch/pipeline/policy.py` and `src/boardwatch/pipeline/funnel_writer.py` — to pass `target_seniority_band=profile_row.target_seniority_band`.

- [ ] **Step 6: Run to verify they pass**

Run: `uv run pytest tests/unit/test_profile_seniority_band.py tests/unit/test_profile_resume_max_pages.py -v --no-cov -n 0`
Expected: PASS. `test_profile_resume_max_pages.py:61`'s pinned parameter-set assertion will FAIL first — update it to include `target_seniority_band`, which is the intended, reviewed change.

- [ ] **Step 7: Add the CLI prompt and the show line**

In `profile_cmd.py::edit`, beside the `resume_max_pages` prompt:

```python
    target_seniority_band = typer.prompt(
        "Target seniority band (entry/mid/senior/any)",
        default=getattr(row, "target_seniority_band", None) or "any",
    )
```

and in `show`, beside the exclude-titles line:

```python
    console.print(f"Target seniority band: {row.target_seniority_band}")
```

**Do NOT add a prompt to `init_cmd.py`** — following the `resume_max_pages` precedent. (R11 would permit it behind a reviewed `EXPECTED_INIT_PROMPTS` update; keeping it out is a judgement call, not a rule.)

- [ ] **Step 8: Commit**

```bash
git add src/boardwatch/store src/boardwatch/cli/profile_cmd.py src/boardwatch/rank/heuristic.py src/boardwatch/reports/manifest.py src/boardwatch/pipeline/policy.py src/boardwatch/pipeline/funnel_writer.py tests/unit/test_profile_seniority_band.py tests/unit/test_profile_resume_max_pages.py
git commit -m "Add the target_seniority_band profile field

NOT NULL with a server default of any, so the gate is inert for every existing
install and None is unreachable. It enters the ranker's profile_row_hash because
it drives a funnel drop bucket, which re-keys policy_version once."
```

---

## Task 5: Ranker wiring, the drop bucket, and the abstain counter

**Files:**
- Modify: `src/boardwatch/cli/top_cmd.py`
- Test: `tests/unit/test_top_seniority_gate.py`

**Interfaces:**
- Consumes: `seniority_verdict` (Task 3), `load_leveling` / `load_bindings` (Task 2), `ProfileView.target_seniority_band` (Task 4).
- Produces: `RankedResults.hidden_over_seniority: int`, `RankedResults.uncertain_band: int`, `RankedPosting.band: str`, `RankedPosting.band_reason: str`, `rank_open_postings(..., include_over_seniority: bool = False)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_top_seniority_gate.py`:

```python
from boardwatch.cli.top_cmd import rank_open_postings


def test_above_band_postings_land_in_their_own_bucket(engine, settings, seeded_senior_posting):
    r = rank_open_postings(engine, settings, limit=50)
    assert r.hidden_over_seniority == 1
    assert all(p.title != "Staff Software Engineer" for p in r.visible)


def test_the_drain_reveals_them(engine, settings, seeded_senior_posting):
    r = rank_open_postings(engine, settings, limit=50, include_over_seniority=True)
    assert any(p.title == "Staff Software Engineer" for p in r.visible)


def test_the_drain_does_not_consume_the_queue(engine, settings, seeded_senior_posting):
    """A drain that records `seen` is a re-entry path that closes behind you."""
    r = rank_open_postings(engine, settings, limit=50, include_over_seniority=True)
    drained = [p for p in r.visible if p.title == "Staff Software Engineer"]
    assert drained
    assert all(p.posting_id not in r.surfaced_job_ids for p in drained)


def test_uncertain_is_counted_but_never_dropped(engine, settings, seeded_unbound_level_posting):
    r = rank_open_postings(engine, settings, limit=50)
    assert r.uncertain_band == 1
    assert any(p.title == "Software Engineer, Specs, Level 5" for p in r.visible)


def test_the_accounting_identity_holds_with_the_new_bucket(engine, settings, seeded_mixed):
    r = rank_open_postings(engine, settings, limit=5)
    accounted = (
        len(r.visible) + r.skipped_not_new + r.hidden_hard_filter + r.hidden_non_swe
        + r.hidden_over_seniority + r.hidden_ineligible + r.hidden_below_cutoff
        + r.hidden_duplicate + r.hidden_handled + r.hidden_applied
    )
    assert r.considered == accounted


def test_uncertain_band_is_not_part_of_the_identity(engine, settings, seeded_unbound_level_posting):
    """It is a REPORTED counter, not a drop — folding it in would break reconciliation."""
    r = rank_open_postings(engine, settings, limit=50)
    assert r.uncertain_band == 1
    assert r.considered == (
        len(r.visible) + r.skipped_not_new + r.hidden_hard_filter + r.hidden_non_swe
        + r.hidden_over_seniority + r.hidden_ineligible + r.hidden_below_cutoff
        + r.hidden_duplicate + r.hidden_handled + r.hidden_applied
    )
```

Add fixtures to `tests/conftest.py` seeding: a `Staff Software Engineer` posting, a Snap-like `Software Engineer, Specs, Level 5` posting with **no** binding, and a `seeded_mixed` set combining both with two ordinary titles. Set the profile's `target_seniority_band="entry"` in each.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_top_seniority_gate.py -v --no-cov -n 0`
Expected: FAIL — `AttributeError: 'RankedResults' object has no attribute 'hidden_over_seniority'`.

- [ ] **Step 3: Make the changes in `top_cmd.py`**

Nineteen edits, all in this file:

1. `RankedPosting`: add `band: str = "in_band"` and `band_reason: str = ""` beside `role`/`role_reason`.
2. `RankedResults` docstring: add `+ hidden_over_seniority` to the reconciliation identity prose, and state that `uncertain_band` is **reported, not a drop**.
3. `RankedResults` docstring: rewrite the "SIX hand-maintained mirror sites" paragraph — the count is **at least 27**, stated as a floor, and it is enumerated in `docs/superpowers/plans/2026-08-19-seniority-gate.md`.
4. `RankedResults`: add `hidden_over_seniority: int = 0` and `uncertain_band: int = 0` with explanatory comments matching the file's convention.
5. The `select(...)`: add `companies.c.provider` and `companies.c.slug`.
6. Before the loop: `catalog = load_leveling(settings.config_dir)`, `bindings = load_bindings(settings.config_dir)`, `tier = catalog.fields.get(profile_career_field)`, and `schemes = {k: catalog.schemes[v] for k, v in bindings.items() if v in catalog.schemes}`. Loaded **once**, never per row.
7. Counter init: `hidden_over_seniority = 0`, `uncertain_band = 0`.
8. The gate itself, immediately after the role gate:

```python
        band, band_reason = seniority_verdict(
            row.title, schemes.get((row.provider, row.slug)),
            profile.target_seniority_band, tier, catalog,
        )
        if band == "uncertain":
            # Counted, never dropped: the abstain rate is the keystone number, and an
            # unreported abstain is the monitoring failure this gate exists to prevent.
            uncertain_band += 1
        if band == "above_band" and not include_over_seniority:
            hidden_over_seniority += 1
            continue
```
9. `RankedPosting(...)`: pass `band=band, band_reason=band_reason`.
10. `rank_open_postings` signature: `include_over_seniority: bool = False`.
11. The `return RankedResults(...)`: pass both new counters.
12. `_record_surfaced`: exclude drained rows (`band == "above_band"` and `role == "not_swe"`) from `surfaced_job_ids`.
13. `_print_hidden_notices` signature: `include_over_seniority: bool`.
14. The drain notice, mirroring the non-SWE one.
15. A notice when `uncertain_band` is non-zero, naming the count and `leveling-bindings.yaml`.
16. A notice when `profile.target_seniority_band == "any"` **and** `uncertain_band + hidden_over_seniority > 0`, naming `profile edit`.
17. The empty-result early-return guard at `:690`: add `and not results.hidden_over_seniority`.
18. The typer `--include-over-seniority` option.
19. All four call sites threading the flag (`:633, 654, 701, 725`).

Also `_why_cell`: annotate **only** the drained row, preserving *"every drain annotates; a normally-visible row is unannotated"*.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/unit/test_top_seniority_gate.py tests/unit/test_top_accounting.py tests/unit/test_top_duplicates.py -v --no-cov -n 0`
Expected: PASS. `_accounted()` in `test_top_accounting.py` and the two hand-summed identities in `test_top_duplicates.py` must gain `+ r.hidden_over_seniority` and will fail until they do.

- [ ] **Step 5: Commit**

```bash
git add src/boardwatch/cli/top_cmd.py tests/unit/test_top_seniority_gate.py tests/unit/test_top_accounting.py tests/unit/test_top_duplicates.py tests/conftest.py
git commit -m "Gate the shortlist on seniority and report the abstain rate

above_band drops into its own bucket with an --include-over-seniority drain;
uncertain is counted and passed through, because an unreported abstain is the
monitoring failure the gate exists to prevent. The drain no longer records seen,
so inspecting the quarantine cannot suppress those jobs from later runs."
```

---

## Task 6: The funnel and pipeline mirror sites

**Files:**
- Modify: `src/boardwatch/reports/run_funnel.py`, `src/boardwatch/pipeline/runner.py`, `src/boardwatch/cli/run_cmd.py`
- Test: `tests/unit/test_run_funnel.py`, `tests/pipeline/test_liveness_withholds_dead_leads.py`

**Interfaces:**
- Consumes: `RankedResults.hidden_over_seniority` / `.uncertain_band` (Task 5).
- Produces: `ShortlistCounts.hidden_over_seniority: int = 0`, `ShortlistCounts.uncertain_band: int = 0`.

- [ ] **Step 1: Write the failing tests**

```python
def test_the_shortlist_stage_reconciles_with_the_new_bucket() -> None:
    f = funnel(considered=10, shortlisted=6, hidden_over_seniority=4)
    stage = next(s for s in f.stages if s.name == "shortlist")
    assert stage.reconciled is True


def test_the_markdown_names_the_over_seniority_drop_with_its_count() -> None:
    f = funnel(considered=10, shortlisted=6, hidden_over_seniority=4)
    assert "- **hidden_over_seniority**: 4" in funnel_to_markdown(f)


def test_uncertain_band_is_reported_but_is_not_a_drop() -> None:
    """Folding an abstain into a drop would break the identity AND hide the abstain."""
    f = funnel(considered=10, shortlisted=10, uncertain_band=3)
    stage = next(s for s in f.stages if s.name == "shortlist")
    assert stage.reconciled is True
    assert all(d.reason != "uncertain_band" for d in stage.drops)
    assert "uncertain_band" in funnel_to_markdown(f)


def test_the_operator_summary_line_names_the_over_seniority_bucket() -> None:
    line = _shortlist_line(ShortlistCounts(
        considered=10, shortlisted=6, hidden_over_seniority=4,
    ))
    assert "4 over seniority" in line
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_run_funnel.py -k "over_seniority or uncertain_band" -v --no-cov -n 0`
Expected: FAIL — `TypeError: ShortlistCounts.__init__() got an unexpected keyword argument`.

- [ ] **Step 3: Make the changes**

In `run_funnel.py`, add to `ShortlistCounts`:

```python
    # D-246: title seniority above the operator's target band. Drained by
    # `top --include-over-seniority`.
    hidden_over_seniority: int = 0
    # D-246: the gate could not decide — an unbound level token or an ambiguous one. REPORTED,
    # never dropped, and deliberately NOT part of the reconciliation identity: it counts
    # postings that PASSED. The keystone invariant requires abstain rates every run.
    uncertain_band: int = 0
```

Add to the shortlist stage's `drops=(...)` tuple:

```python
                Drop(reason="hidden_over_seniority", count=shortlist.hidden_over_seniority,
                     note="title seniority above target band; "
                          "drain with `top --include-over-seniority`"),
```

Render `uncertain_band` in the shortlist stage's **report** block, not its drops.

In `pipeline/runner.py`, map both new counters into `ShortlistCounts`. **Do not touch
`_zero_output_guard`** — `over_seniority` is a rejection, not a suppression; registering it would
weaken the guard.

In `cli/run_cmd.py::_shortlist_line`, add `f"{counts.hidden_over_seniority} over seniority, "`.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/unit/test_run_funnel.py tests/pipeline/test_liveness_withholds_dead_leads.py tests/pipeline/test_applied_state_suppression.py -v --no-cov -n 0`
Expected: PASS. The `funnel()` helper needs the kwarg, the `ShortlistCounts(...)` pass-through, **and** the default `considered=` balance — missing the last makes every unrelated funnel test fail as unbalanced.

- [ ] **Step 5: Commit**

```bash
git add src/boardwatch/reports/run_funnel.py src/boardwatch/pipeline/runner.py src/boardwatch/cli/run_cmd.py tests/unit/test_run_funnel.py tests/pipeline
git commit -m "Report the over-seniority drop and the band abstain rate in the funnel

The drop joins the shortlist stage's reconciliation identity; the abstain count
is reported outside it, because it counts postings that passed."
```

---

## Task 7: The other two filter chains and the audit surface

Without this the notification path keeps pushing the exact lead the gate was built to stop.

**Files:**
- Modify: `src/boardwatch/reports/notify.py`, `src/boardwatch/reports/stats.py`, `src/boardwatch/cli/show_cmd.py`
- Test: `tests/unit/test_reports_notify.py`, `tests/unit/test_top_show.py`

**Interfaces:**
- Consumes: `seniority_verdict` (Task 3), `ProfileView.target_seniority_band` (Task 4).
- Produces: `select_new_matches(..., include_over_seniority: bool = False)`.

- [ ] **Step 1: Write the failing tests**

```python
def test_notify_does_not_push_an_above_band_posting(engine, settings, seeded_senior_posting):
    assert select_new_matches(engine, settings) == []


def test_notify_drain_reveals_it(engine, settings, seeded_senior_posting):
    assert select_new_matches(engine, settings, include_over_seniority=True)


def test_notify_still_pushes_an_uncertain_band_posting(engine, settings, seeded_unbound_level_posting):
    """Fail-open: an abstain is never a suppression."""
    assert select_new_matches(engine, settings)


def test_show_prints_the_band_line(engine, settings, seeded_senior_posting, capsys):
    show_posting(engine, settings, seeded_senior_posting)
    out = capsys.readouterr().out
    assert "Band:" in out
    assert "hidden from top unless --include-over-seniority" in out
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_reports_notify.py tests/unit/test_top_show.py -v --no-cov -n 0`
Expected: FAIL — notify returns the senior posting; `show` prints no `Band:` line.

- [ ] **Step 3: Make the changes**

`notify.py::select_new_matches`: add `provider`/`slug` to the select, load the catalog and bindings
once before the loop, add `include_over_seniority: bool = False`, and add the same
`above_band` → `continue` beside the existing `role_verdict` check at `:117-128`.

`stats.py`: apply the same gate at `:119` so `stats` reports the funnel's population.

`show_cmd.py`, beside the `Role:` line at `:150-155`:

```python
    band, band_reason = seniority_verdict(
        row.title, schemes.get((row.provider, row.slug)),
        profile.target_seniority_band, tier, catalog,
    )
    band_note = " — hidden from top unless --include-over-seniority" if band == "above_band" else ""
    console.print(f"Band: {band_reason}{band_note}", markup=False)
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/unit/test_reports_notify.py tests/unit/test_top_show.py tests/unit/test_stats_cmd.py -v --no-cov -n 0`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/boardwatch/reports/notify.py src/boardwatch/reports/stats.py src/boardwatch/cli/show_cmd.py tests/unit
git commit -m "Apply the seniority gate in notify, stats and show

All three call the role gate independently, so wiring only the ranker would have
left the notification path pushing the same senior lead the gate blocks."
```

---

## Task 8: Generalization registration and the full gate

**Files:**
- Modify: `tools/generalization/allowlists.py`, `tools/generalization/defaults.py`
- Modify: `CHANGELOG.md`, `README.md`, `docs/program/DECISIONS.md`, `docs/program/STATE.md`

**Interfaces:**
- Consumes: everything above.
- Produces: a green `make check`.

- [ ] **Step 1: Register the catalog and the scoped module**

In `tools/generalization/allowlists.py`:

```python
    "src/boardwatch/rank/leveling.yaml": DataEntry(
        kind="taxonomy",
        reason="Seniority level grammars, company-free rung ladders, and per-field word "
        "meanings. Describes how postings word seniority, not one user's targets — it "
        "contains no company names at all, because a company's ladder is not a fact "
        "boardwatch can ship. The company binding is user config in "
        "{config_dir}/leveling-bindings.yaml (D-246)",
        pin="sha256:<fill from `shasum -a 256 src/boardwatch/rank/leveling.yaml`>",
    ),
```

In `tools/generalization/defaults.py::SCOPED_MODULES`, after `role_gate.py`:

```python
    # Scoped for the same reason role_gate is: it holds TITLE data. The word and band data
    # live in leveling.yaml; the patterns here use tuple(...) constructor calls.
    "src/boardwatch/rank/seniority_gate.py",
```

- [ ] **Step 2: Stage everything, then run the only gate**

```bash
git add -- src/boardwatch/rank/leveling.yaml src/boardwatch/rank/leveling.py src/boardwatch/rank/seniority_gate.py
make check
```

Expected: exit 0. **Do not pipe through `head`/`tail`** — SIGPIPE gives a false negative. If R7 fails with a pin mismatch, re-run `shasum -a 256` and update the pin. Budget 4.5–35 min.

- [ ] **Step 3: Update the docs**

- `CHANGELOG.md`: follow the existing bucket convention — *"`boardwatch top` gains a `hidden_over_seniority` bucket and an `--include-over-seniority` drain; the funnel's shortlist stage reports the new bucket and its reconciliation identity includes it."* Add the one-time `policy_version` re-key (11 ledger rows) and the `--include-non-swe` drain-no-longer-records-`seen` fix.
- `README.md:224`: document the new drain beside `--include-non-swe`.
- `docs/program/DECISIONS.md`: append **D-246** — context, choice, alternatives rejected. Record explicitly that the owner's chosen "company map in the registry" was **not buildable** (37-entry seed catalog, `extra="forbid"`, Snap/Twilio/Google absent) and that schemes-plus-user-binding replaced it. Add its index row, then run `make reindex`.
- `docs/program/STATE.md`: rewrite the D-245 open question 4 entry as resolved.

- [ ] **Step 4: Re-run the gate after the doc edits**

Run: `make check`
Expected: exit 0. `make reindex` must have been run or the index check fails (D-109).

- [ ] **Step 5: Commit and open the PR**

```bash
git add tools/generalization CHANGELOG.md README.md docs/program
git commit -m "Register the leveling catalog and record D-246"
git push -u origin <branch>
gh pr create --title "Add the rank-time seniority gate" --body "<summary + measurements>"
```

---

## Self-Review

**1. Spec coverage.** §1 → Tasks 1, 5. §2.1 (no company names) → Task 2 (with a test asserting no company string appears in the shipped file). §3.2 → Task 1. §3.3 (ambiguous grammars never resolve) → Tasks 2, 3. §3.4 (measured word list, `fellow` dropped) → Tasks 2, 3. §3.6 (roman) → Tasks 2, 3. §4.1 → Task 3. §4.2 → Task 2. §4.3 → Task 4. §4.4 (three chains) → Tasks 5, 7. §4.5 (observability) → Tasks 5, 6, 7. §4.6 (drain doesn't consume) → Task 5. §5 (mirror sites) → Tasks 5, 6, 7. §6 → Task 8 docs. §7 → tests throughout.

**Gap found and closed:** the spec's §4.3 "new-user awareness" notice had no task; it is now step 3 item 16 of Task 5. **Gap found and closed:** the spec requires `uncertain_role` reported by the same mechanism as `uncertain_band` — that is *not* in this plan. It is deliberately deferred: it belongs with §8 Q2 (closing the role gate's `uncertain` lane), which the spec names as separate, larger work. Task 8's D-246 entry must say so, or it will read as an oversight.

**2. Placeholder scan.** One intentional placeholder remains: the `pin="sha256:<fill…>"` in Task 8, which cannot be computed until the file's final bytes exist; the step names the exact command. No others.

**3. Type consistency.** `SeniorityBand` is defined once in `leveling.py` and imported by `seniority_gate.py` — not redefined. `TargetBand` lives in `seniority_gate.py`; `SeniorityBandChoice` in `profile_cmd.py` is the pydantic-facing twin and is deliberately a separate name. `seniority_verdict(title, scheme, target_band, tier, catalog)` has the same argument order at all four call sites (Tasks 5 and 7). `load_bindings` returns `dict[tuple[str, str], str]` (scheme *names*); callers resolve names to `LevelScheme` objects once before the loop, and Task 5 step 3 item 6 does exactly that.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-19-seniority-gate.md`. Two execution options:

**1. Subagent-Driven (recommended)** — a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
