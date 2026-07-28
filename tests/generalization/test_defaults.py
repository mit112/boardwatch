"""R9: a preference collection must never ship non-empty."""

from __future__ import annotations

from pathlib import Path

from tools.generalization.defaults import SCOPED_MODULES, check_collection_defaults
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
