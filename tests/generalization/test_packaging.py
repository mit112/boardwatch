"""R12 wheel completeness."""

from __future__ import annotations

from pathlib import Path

from tools.generalization.discovery import (
    PRODUCTION_MINIMUM_FILES,
    Repo,
    discover,
    find_repo_root,
)
from tools.generalization.packaging import (
    check_wheel_completeness,
    missing_from_wheel,
    shipped_data_files,
)


def _repo() -> Repo:
    return discover(find_repo_root(Path.cwd().resolve()), minimum_files=PRODUCTION_MINIMUM_FILES)


def test_shipped_data_files_finds_the_known_data_files() -> None:
    """Non-vacuity: if this returned an empty set the rule would pass on anything."""
    found = shipped_data_files(_repo())
    assert "boardwatch/eligibility/rules.yaml" in found
    assert "boardwatch/extract/taxonomy.yaml" in found
    assert "boardwatch/registry/companies.yaml" in found
    assert "boardwatch/py.typed" in found
    assert len(found) >= 6


def test_shipped_data_files_excludes_python_and_caches() -> None:
    found = shipped_data_files(_repo())
    assert not [p for p in found if p.endswith(".py")]
    assert not [p for p in found if "__pycache__" in p]


def test_missing_from_wheel_flags_an_absent_file() -> None:
    """Positive control: the diff must actually report a gap."""
    found = missing_from_wheel(
        {"boardwatch/eligibility/rules.yaml", "boardwatch/py.typed"},
        {"boardwatch/py.typed"},
    )
    assert len(found) == 1
    assert found[0].rule == "R12"
    assert found[0].path == "src/boardwatch/eligibility/rules.yaml"


def test_missing_from_wheel_is_quiet_when_everything_ships() -> None:
    assert missing_from_wheel({"boardwatch/py.typed"}, {"boardwatch/py.typed", "extra"}) == []


def test_the_real_wheel_ships_every_data_file() -> None:
    """The end-to-end rule against the real tree. Builds a wheel; takes a second or two."""
    assert check_wheel_completeness(_repo()) == []
