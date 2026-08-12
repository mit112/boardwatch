"""The tailor/bundle boundary, asserted over the import graph rather than by convention.

Gate A ships the canonical career-profile bundle as an authoring store and nothing more. The
bundle-to-`Resume` bridge is Gate B, and Gate B is prohibited until Gate A is reviewed. The
thing that would quietly void that deferral is not a design decision, it is one import: the
moment any production tailor module can see `boardwatch.profile_bundle`, the bridge exists
whether or not anyone meant to build it, and the existing tailoring path stops being the frozen
thing the deferral assumes.

So the boundary is checked three ways, none of which is a text grep for one spelling:

1. the résumé the tailor reads is still `{config_dir}/resume.yaml`, on a path that has nothing
   to do with the bundle root;
2. no production tailor module reaches `boardwatch.profile_bundle` transitively; and
3. authored-résumé loading works with no bundle directory on disk at all.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest

from boardwatch.cli.tailor_cmd import _resume_path
from boardwatch.core.settings import Settings
from boardwatch.profile_bundle.paths import resolve_bundle_root
from boardwatch.tailor.load import load_resume, scaffold_template
from tests.profile_bundle.import_graph import (
    SRC_ROOT,
    Closure,
    imported_modules,
    module_name,
    reachable_from,
)

BUNDLE_PACKAGE: Final = "boardwatch.profile_bundle"

#: Derived from the live tree, never enumerated: a tailor module added tomorrow is inside the
#: boundary the day it lands, with no table to remember to update.
TAILOR_ROOTS: Final = tuple(
    sorted(SRC_ROOT.glob("boardwatch/tailor/**/*.py"))
    + [SRC_ROOT / "boardwatch" / "cli" / "tailor_cmd.py"]
)


def _settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path / "data", config_dir=tmp_path / "cfg")


# --------------------------------------------------------------------------------------
# 1. The résumé path
# --------------------------------------------------------------------------------------


def test_the_tailor_default_resume_path_is_still_config_dir_resume_yaml(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    assert _resume_path(settings) == settings.config_dir / "resume.yaml"


def test_an_explicit_resume_override_still_wins(tmp_path: Path) -> None:
    """Non-vacuity for the test above: `_resume_path` is a real branch, not a constant."""
    settings = _settings(tmp_path)
    override = tmp_path / "elsewhere" / "other.yaml"
    assert _resume_path(settings, override) == override


def test_the_resume_and_the_bundle_live_at_disjoint_paths(tmp_path: Path) -> None:
    """The two stores share `config_dir` and nothing else. If the bundle root ever contained the
    résumé, deleting or checking out a revision would move the tailor's input underneath it."""
    settings = _settings(tmp_path)
    resume = _resume_path(settings)
    bundle_root = resolve_bundle_root(settings.config_dir, None)
    assert resume != bundle_root
    assert bundle_root not in resume.parents


# --------------------------------------------------------------------------------------
# 2. The import graph
# --------------------------------------------------------------------------------------


def test_the_tailor_root_set_is_read_from_the_tree_and_is_not_empty() -> None:
    """A boundary check over an empty file set passes on anything. These five names are outside
    facts about the tailoring subsystem, not a restatement of the glob that collected them."""
    names = {module_name(path) for path in TAILOR_ROOTS}
    assert len(TAILOR_ROOTS) >= 25
    for expected in (
        "boardwatch.cli.tailor_cmd",
        "boardwatch.tailor.load",
        "boardwatch.tailor.model",
        "boardwatch.tailor.render.latex",
        "boardwatch.tailor.rewrite.agent_lane",
    ):
        assert expected in names


def test_the_closure_leaves_the_tailor_package() -> None:
    """Non-vacuity for the boundary assertion: the walk is transitive, and on the real tree it
    demonstrably crosses into modules the tailor only reaches through another module."""
    closure = reachable_from(TAILOR_ROOTS)
    assert "boardwatch.reports.tailor" in closure.modules
    assert "boardwatch.store.queries" in closure.modules
    assert len(closure.modules) > len(TAILOR_ROOTS)


def test_no_production_tailor_module_reaches_the_profile_bundle() -> None:
    """The boundary itself. Gate B is where the bridge lives; until then there is no edge."""
    closure = reachable_from(TAILOR_ROOTS)
    offenders = sorted(
        target
        for target in closure.targets
        if target == BUNDLE_PACKAGE or target.startswith(f"{BUNDLE_PACKAGE}.")
    )
    assert offenders == []


def test_no_production_tailor_file_names_the_bundle_package_in_text_either() -> None:
    """The AST check cannot see `importlib.import_module("boardwatch.profile_bundle")`, so the
    root files are additionally held free of the name in any form. Scoped to the roots, because
    over the whole closure this would fire on prose."""
    offenders = [
        path.relative_to(SRC_ROOT).as_posix()
        for path in TAILOR_ROOTS
        if "profile_bundle" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


# --------------------------------------------------------------------------------------
# 2b. Positive controls: the detector must fire on every spelling, and the walk must recurse
# --------------------------------------------------------------------------------------


BUNDLE_IMPORT_SPELLINGS: Final = (
    "import boardwatch.profile_bundle",
    "import boardwatch.profile_bundle.canonical as c",
    "from boardwatch.profile_bundle import canonical",
    "from boardwatch.profile_bundle.canonical import digest_of",
    "from boardwatch import profile_bundle",
    "from ..profile_bundle import canonical",
    "from ..profile_bundle.canonical import digest_of",
    "def build() -> None:\n    from boardwatch.profile_bundle import canonical\n",
)


@pytest.mark.parametrize("source", BUNDLE_IMPORT_SPELLINGS)
def test_every_spelling_of_the_forbidden_import_is_detected(source: str) -> None:
    found = imported_modules(source, package="boardwatch.tailor")
    assert any(name.startswith(BUNDLE_PACKAGE) for name in found), source


def test_at_least_one_spelling_defeats_a_text_grep_for_the_dotted_module() -> None:
    """The outside fact this whole module exists for. `tests/profile_bundle/
    test_profile_bundle_hash_isolation.py` used to grep for the literal
    `profile_bundle.canonical`; these spellings reach the same module without containing it, so
    a grep-shaped guard reads as coverage while admitting the bridge."""
    invisible = [s for s in BUNDLE_IMPORT_SPELLINGS if "profile_bundle.canonical" not in s]
    assert invisible
    for source in invisible:
        found = imported_modules(source, package="boardwatch.tailor")
        assert any(name.startswith(BUNDLE_PACKAGE) for name in found), source


def test_an_unrelated_import_is_not_reported() -> None:
    """The detector has to be able to say no, or the assertions above are unfalsifiable."""
    found = imported_modules(
        "from boardwatch.tailor.load import load_resume\nimport json\n",
        package="boardwatch.cli",
    )
    assert found == frozenset({"boardwatch.tailor.load", "boardwatch.tailor.load.load_resume"})


def _write(root: Path, dotted: str, source: str) -> Path:
    path = root.joinpath(*dotted.split("."))
    path = path.with_suffix(".py")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def test_the_walk_finds_a_bridge_two_modules_deep(tmp_path: Path) -> None:
    """A guard that only inspected the root files would pass this tree. The bridge is real —
    the tailor module imports a helper, and the helper imports the bundle."""
    _write(tmp_path, "boardwatch.__init__", "")
    _write(tmp_path, "boardwatch.tailor.__init__", "")
    root = _write(tmp_path, "boardwatch.tailor.plan", "from boardwatch import helper\n")
    _write(tmp_path, "boardwatch.helper", "from boardwatch.profile_bundle import canonical\n")
    _write(tmp_path, "boardwatch.profile_bundle.__init__", "")
    _write(tmp_path, "boardwatch.profile_bundle.canonical", "")

    closure: Closure = reachable_from([root], src_root=tmp_path)

    assert "boardwatch.helper" in closure.modules
    assert BUNDLE_PACKAGE in closure.targets


def test_the_walk_reports_nothing_when_the_bridge_is_absent(tmp_path: Path) -> None:
    _write(tmp_path, "boardwatch.__init__", "")
    _write(tmp_path, "boardwatch.tailor.__init__", "")
    root = _write(tmp_path, "boardwatch.tailor.plan", "from boardwatch import helper\n")
    _write(tmp_path, "boardwatch.helper", "import json\n")

    closure = reachable_from([root], src_root=tmp_path)

    assert "boardwatch.helper" in closure.modules
    assert not [t for t in closure.targets if t.startswith(BUNDLE_PACKAGE)]


# --------------------------------------------------------------------------------------
# 3. Tailoring runs with no bundle on disk
# --------------------------------------------------------------------------------------


def test_the_authored_resume_loads_with_no_bundle_directory_present(tmp_path: Path) -> None:
    """The scaffold the tailor ships is loadable on a machine that has never run
    `boardwatch profile-bundle init`, which is what "the bundle is not in this path" means
    operationally rather than structurally."""
    settings = _settings(tmp_path)
    resume_path = _resume_path(settings)
    resume_path.parent.mkdir(parents=True, exist_ok=True)
    resume_path.write_text(scaffold_template(), encoding="utf-8")
    assert not resolve_bundle_root(settings.config_dir, None).exists()

    resume = load_resume(resume_path)

    assert resume.entries
    assert not resolve_bundle_root(settings.config_dir, None).exists()
