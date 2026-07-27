"""Discovery must never skip and never trust an incomplete scan."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tools.generalization.discovery import (
    DiscoveryError,
    Repo,
    discover,
    find_repo_root,
)
from tools.generalization.model import Violation

REPO_ROOT = Path(__file__).resolve().parents[2]


def _fake_repo(root: Path) -> None:
    """Build the minimum tree that discovery is willing to trust."""
    (root / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    (root / "Makefile").write_text("check:\n", encoding="utf-8")
    settings = root / "src" / "boardwatch" / "core"
    settings.mkdir(parents=True)
    (settings / "settings.py").write_text("X = 1\n", encoding="utf-8")


def _init_git_repo(root: Path) -> None:
    """Build the minimum trusted tree and commit it to a fresh git repo at root."""
    _fake_repo(root)
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"], cwd=root, check=True, capture_output=True
    )
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"], cwd=root, check=True, capture_output=True
    )


def test_find_repo_root_locates_the_real_repo() -> None:
    assert find_repo_root(Path(__file__).resolve().parent) == REPO_ROOT


def test_find_repo_root_raises_when_there_is_no_root(tmp_path: Path) -> None:
    with pytest.raises(DiscoveryError, match="no repository root"):
        find_repo_root(tmp_path)


def test_discover_real_tree_finds_files_and_sentinels() -> None:
    repo = discover(REPO_ROOT)
    assert len(repo.files) > 50
    paths = {f.path for f in repo.files}
    assert "pyproject.toml" in paths
    assert "src/boardwatch/core/settings.py" in paths


def test_discover_works_outside_a_git_work_tree(tmp_path: Path) -> None:
    _fake_repo(tmp_path)
    repo = discover(tmp_path)
    assert {f.path for f in repo.files} == {
        "pyproject.toml",
        "Makefile",
        "src/boardwatch/core/settings.py",
    }


def test_discover_fails_closed_when_sentinels_are_missing(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    (tmp_path / "Makefile").write_text("check:\n", encoding="utf-8")
    with pytest.raises(DiscoveryError, match="sentinel"):
        discover(tmp_path)


def test_walk_skips_excluded_directories(tmp_path: Path) -> None:
    _fake_repo(tmp_path)
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "junk.pyc").write_text("noise", encoding="utf-8")
    repo = discover(tmp_path)
    assert all("__pycache__" not in f.path for f in repo.files)


def test_binary_files_are_flagged_and_carry_no_text(tmp_path: Path) -> None:
    _fake_repo(tmp_path)
    (tmp_path / "blob.bin").write_bytes(b"\x00\x01\x02")
    repo = discover(tmp_path)
    blob = repo.by_path("blob.bin")
    assert blob is not None
    assert blob.is_text is False
    assert blob.text == ""


def test_by_path_returns_none_for_an_unknown_path(tmp_path: Path) -> None:
    _fake_repo(tmp_path)
    assert discover(tmp_path).by_path("nope.txt") is None


def test_repo_file_suffix_is_lowercased(tmp_path: Path) -> None:
    _fake_repo(tmp_path)
    (tmp_path / "Notes.TXT").write_text("hi", encoding="utf-8")
    repo = discover(tmp_path)
    entry = repo.by_path("Notes.TXT")
    assert entry is not None
    assert entry.suffix == ".txt"


def test_violation_render_includes_the_line_when_known() -> None:
    assert Violation("R1", "a/b.py", 7, "bad").render() == "[R1] a/b.py:7: bad"
    assert Violation("R7", "a/b.py", None, "bad").render() == "[R7] a/b.py: bad"


def test_repo_is_a_frozen_value_type(tmp_path: Path) -> None:
    _fake_repo(tmp_path)
    repo = discover(tmp_path)
    assert isinstance(repo, Repo)
    with pytest.raises(AttributeError):
        repo.root = tmp_path  # type: ignore[misc]


def test_discover_prefers_git_mode_inside_a_work_tree(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    repo = discover(tmp_path)
    assert repo.mode == "git"


def test_discover_excludes_untracked_debris_in_a_git_work_tree(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / "scratch.txt").write_text("untracked", encoding="utf-8")
    repo = discover(tmp_path)
    assert repo.by_path("scratch.txt") is None


def test_discover_excludes_excluded_dirs_in_git_mode_too(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    junk_dir = tmp_path / "dist"
    junk_dir.mkdir()
    (junk_dir / "artifact.txt").write_text("junk", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "track dist"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    repo = discover(tmp_path)
    assert repo.by_path("dist/artifact.txt") is None


def test_discover_raises_when_a_tracked_file_is_missing_from_disk(
    tmp_path: Path,
) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / "Makefile").unlink()
    with pytest.raises(DiscoveryError, match="cannot read"):
        discover(tmp_path)


def test_discover_raises_when_minimum_files_is_not_met(tmp_path: Path) -> None:
    _fake_repo(tmp_path)
    with pytest.raises(DiscoveryError, match="minimum"):
        discover(tmp_path, minimum_files=10)
