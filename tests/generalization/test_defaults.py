"""R9: a preference collection must never ship non-empty."""

from __future__ import annotations

from pathlib import Path

from tools.generalization import snapshots as snap
from tools.generalization.defaults import (
    HEURISTIC_MODULE,
    INIT_MODULE,
    SCOPED_MODULES,
    check_collection_defaults,
    check_defaults_snapshot,
    check_init_prompts,
)
from tools.generalization.discovery import Repo, RepoFile, discover

REPO_ROOT = Path(__file__).resolve().parents[2]


def _module(source: str, path: str = SCOPED_MODULES[0]) -> Repo:
    others = tuple(
        RepoFile(path=other, abspath=Path(other), is_text=True, text="")
        for other in SCOPED_MODULES
        if other != path
    )
    target = RepoFile(path=path, abspath=Path(path), is_text=True, text=source)
    return Repo(root=Path("/tmp/fake"), files=(target, *others))


def test_real_tree_has_no_collection_defaults() -> None:
    assert check_collection_defaults(discover(REPO_ROOT)) == []


def test_module_level_preference_constant_is_rejected() -> None:
    found = check_collection_defaults(_module('DEFAULT_TITLES = ["Chief Widget Officer"]\n'))
    assert [v.rule for v in found] == ["R9"]
    assert found[0].line == 1


def test_class_field_default_is_rejected() -> None:
    source = "class P:\n    locations: list[str] = ['Atlantis', 'Elsewhere']\n"
    found = check_collection_defaults(_module(source))
    assert [v.rule for v in found] == ["R9"]


def test_pydantic_field_default_is_rejected() -> None:
    source = "class P:\n    titles: list[str] = Field(default=['Widget Wrangler'])\n"
    found = check_collection_defaults(_module(source))
    assert [v.rule for v in found] == ["R9"]


def test_lambda_default_factory_is_rejected() -> None:
    source = "class P:\n    titles: list[str] = Field(default_factory=lambda: ['Widget Wrangler'])\n"
    found = check_collection_defaults(_module(source))
    assert [v.rule for v in found] == ["R9"]


def test_empty_collections_are_allowed() -> None:
    source = (
        "EMPTY: list[str] = []\n"
        "class P:\n"
        "    a: list[str] = []\n"
        "    b: dict[str, str] = {}\n"
        "    c: list[str] = Field(default_factory=list)\n"
    )
    assert check_collection_defaults(_module(source)) == []


def test_scalars_and_nested_models_are_allowed() -> None:
    source = (
        "class P:\n"
        "    delay: float = 1.0\n"
        "    mode: str = 'soft'\n"
        "    weights: RankWeights = Field(default_factory=RankWeights)\n"
    )
    assert check_collection_defaults(_module(source)) == []


def test_function_locals_are_not_flagged() -> None:
    source = "def f():\n    folded = ['a', 'b']\n    return folded\n"
    assert check_collection_defaults(_module(source)) == []


def test_missing_scoped_module_is_reported() -> None:
    repo = Repo(root=Path("/tmp/fake"), files=())
    found = check_collection_defaults(repo)
    assert len(found) == len(SCOPED_MODULES)
    assert all(v.rule == "R9" for v in found)


def test_an_unparseable_scoped_module_is_reported() -> None:
    found = check_collection_defaults(_module("def broken(\n"))
    assert [v.rule for v in found] == ["R9"]
    assert "could not be parsed as Python" in found[0].detail


def test_a_named_default_factory_returning_a_collection_is_rejected() -> None:
    source = (
        "def _titles() -> list[str]:\n"
        "    return ['Chief Widget Officer']\n"
        "class P:\n"
        "    titles: list[str] = Field(default_factory=_titles)\n"
    )
    found = check_collection_defaults(_module(source))
    assert [v.rule for v in found] == ["R9"]
    assert "naming a function" in found[0].detail


def test_a_named_default_factory_returning_empty_is_allowed() -> None:
    source = (
        "def _titles() -> list[str]:\n"
        "    return []\n"
        "class P:\n"
        "    titles: list[str] = Field(default_factory=_titles)\n"
    )
    assert check_collection_defaults(_module(source)) == []


def test_an_unresolvable_default_factory_is_an_accepted_bypass() -> None:
    """A factory naming something imported cannot be resolved from this module's AST, so it
    passes. Rejecting it would reject the legitimate nested-model pattern. Spec section 8."""
    source = "class P:\n    weights: RankWeights = Field(default_factory=RankWeights)\n"
    assert check_collection_defaults(_module(source)) == []


def test_dunder_all_is_not_a_preference_collection() -> None:
    assert check_collection_defaults(_module('__all__ = ["a", "b"]\n')) == []


def test_a_nested_class_body_is_checked() -> None:
    source = (
        "class Outer:\n"
        "    class Config:\n"
        "        titles: list[str] = ['Chief Widget Officer']\n"
    )
    found = check_collection_defaults(_module(source))
    assert [v.rule for v in found] == ["R9"]


def test_a_constant_inside_a_module_level_block_is_checked() -> None:
    source = "if True:\n    DEFAULT_TITLES = ['Chief Widget Officer']\n"
    found = check_collection_defaults(_module(source))
    assert [v.rule for v in found] == ["R9"]


def test_tuple_unpacking_of_empty_collections_is_allowed() -> None:
    assert check_collection_defaults(_module("A, B = [], []\n")) == []


def test_non_string_collections_are_allowed() -> None:
    """Spec section 6 scopes R9 to collections OF STRINGS. A tuple of backoff seconds is not
    a preference list, and flagging it would fire the rule on legitimate content."""
    source = "BACKOFFS = (1, 2, 4)\n"
    assert check_collection_defaults(_module(source)) == []


def test_a_dict_with_string_keys_is_flagged() -> None:
    """A dict with string keys is a collection OF STRINGS and therefore a preference candidate."""
    source = "SCALES = {'a': 1.0}\n"
    found = check_collection_defaults(_module(source))
    assert [v.rule for v in found] == ["R9"]


def test_a_nested_collection_of_strings_is_rejected() -> None:
    for source in (
        "DEFAULT_TITLES = [['Chief Widget Officer']]\n",
        "GROUPS = (('Chief Widget Officer',),)\n",
        "DEFAULT = [{'title': 'Chief Widget Officer'}]\n",
        "BY_ID = {1: ['Widget Wrangler']}\n",
    ):
        found = check_collection_defaults(_module(source))
        assert [v.rule for v in found] == ["R9"], source


def test_a_nested_collection_without_strings_is_allowed() -> None:
    assert check_collection_defaults(_module("BACKOFFS = [[1, 2], [4, 8]]\n")) == []


def test_real_tree_defaults_match_the_snapshot() -> None:
    assert check_defaults_snapshot(discover(REPO_ROOT)) == []


def test_real_tree_init_prompts_match_the_snapshot() -> None:
    assert check_init_prompts(discover(REPO_ROOT)) == []


def test_every_snapshotted_default_carries_a_class_label() -> None:
    assert set(snap.SETTINGS_FIELD_CLASS) == set(snap.EXPECTED_SETTINGS_DEFAULTS)
    assert set(snap.SETTINGS_FIELD_CLASS.values()) <= {
        "preference",
        "operational",
        "path",
        "capability",
    }


def test_a_changed_default_is_rejected() -> None:
    original = snap.EXPECTED_SETTINGS_DEFAULTS["Settings.recency_half_life_days"]
    snap.EXPECTED_SETTINGS_DEFAULTS["Settings.recency_half_life_days"] = 3.0
    try:
        found = [v for v in check_defaults_snapshot(discover(REPO_ROOT)) if "changed" in v.detail]
        assert [v.rule for v in found] == ["R10"]
    finally:
        snap.EXPECTED_SETTINGS_DEFAULTS["Settings.recency_half_life_days"] = original


def test_a_removed_snapshot_key_is_reported_as_new() -> None:
    original = snap.EXPECTED_SETTINGS_DEFAULTS.pop("Settings.scan_workers")
    try:
        found = [v for v in check_defaults_snapshot(discover(REPO_ROOT)) if "not in the snapshot" in v.detail]
        assert [v.rule for v in found] == ["R10"]
    finally:
        snap.EXPECTED_SETTINGS_DEFAULTS["Settings.scan_workers"] = original


def test_the_heuristic_parameter_default_is_pinned() -> None:
    assert snap.EXPECTED_PARAM_DEFAULTS == {"score_posting.half_life_days": "14.0"}


def test_a_changed_init_prompt_default_is_rejected(tmp_path: Path) -> None:
    source = 'import typer\nx = typer.prompt("Locations", default="Atlantis")\n'
    files = tuple(f for f in discover(REPO_ROOT).files if f.path != INIT_MODULE) + (
        RepoFile(path=INIT_MODULE, abspath=tmp_path / "init.py", is_text=True, text=source),
    )
    found = check_init_prompts(Repo(root=REPO_ROOT, files=files))
    assert [v.rule for v in found] == ["R11"]
    assert "Atlantis" in found[0].detail


def test_an_unparseable_heuristic_module_is_reported() -> None:
    others = tuple(
        RepoFile(path=other, abspath=Path(other), is_text=True, text="")
        for other in SCOPED_MODULES
        if other != HEURISTIC_MODULE
    )
    target = RepoFile(
        path=HEURISTIC_MODULE,
        abspath=Path(HEURISTIC_MODULE),
        is_text=True,
        text="def broken(\n",
    )
    files = tuple(f for f in discover(REPO_ROOT).files if f.path not in SCOPED_MODULES) + (
        target,
        *others,
    )
    found = [
        v for v in check_defaults_snapshot(Repo(root=REPO_ROOT, files=files))
        if "could not be parsed" in v.detail
    ]
    assert [v.rule for v in found] == ["R10"]


def test_an_unparseable_init_module_is_reported() -> None:
    others = tuple(
        RepoFile(path=other, abspath=Path(other), is_text=True, text="")
        for other in SCOPED_MODULES
        if other != INIT_MODULE
    )
    target = RepoFile(
        path=INIT_MODULE,
        abspath=Path(INIT_MODULE),
        is_text=True,
        text="def broken(\n",
    )
    files = tuple(f for f in discover(REPO_ROOT).files if f.path not in SCOPED_MODULES) + (
        target,
        *others,
    )
    found = [
        v for v in check_init_prompts(Repo(root=REPO_ROOT, files=files))
        if "could not be parsed" in v.detail
    ]
    assert [v.rule for v in found] == ["R11"]
