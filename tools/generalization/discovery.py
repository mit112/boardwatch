"""File discovery for the generalization checks.

`git ls-files` is preferred because it enumerates exactly what gets published and
ignores untracked local debris, which would otherwise produce failures that exist on
one machine only. A filesystem walk is the fallback outside a git work tree.

Discovery NEVER skips. A scan that cannot run must fail, because a zero-file scan
reporting success is the dangerous failure mode: the gate would look green while
being entirely disabled.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

SENTINELS: tuple[str, ...] = (
    "pyproject.toml",
    "Makefile",
    "src/boardwatch/core/settings.py",
)

EXCLUDED_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "dist",
        "build",
        ".agent",
        ".superpowers",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".idea",
        ".vscode",
        "node_modules",
    }
)

_NULL_SNIFF_BYTES = 8192


class DiscoveryError(RuntimeError):
    """Discovery could not produce a file list worth trusting."""


@dataclass(frozen=True)
class RepoFile:
    """One discovered file. `text` is empty for binary files."""

    path: str
    abspath: Path
    is_text: bool
    text: str

    @property
    def suffix(self) -> str:
        return PurePosixPath(self.path).suffix.lower()


@dataclass(frozen=True)
class Repo:
    root: Path
    files: tuple[RepoFile, ...]

    def by_path(self, path: str) -> RepoFile | None:
        for entry in self.files:
            if entry.path == path:
                return entry
        return None


def find_repo_root(start: Path) -> Path:
    """Walk up from `start` to the directory holding both pyproject.toml and Makefile."""
    for candidate in [start, *start.parents]:
        if (candidate / "pyproject.toml").is_file() and (candidate / "Makefile").is_file():
            return candidate
    raise DiscoveryError(
        f"no repository root (pyproject.toml plus Makefile) at or above {start}"
    )


def _git_paths(root: Path) -> list[str] | None:
    """Tracked paths, or None when this is not a usable git work tree."""
    try:
        proc = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    paths = [p for p in proc.stdout.split("\0") if p]
    return paths or None


def _walk_paths(root: Path) -> list[str]:
    out: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in EXCLUDED_DIRS for part in rel.parts):
            continue
        out.append(rel.as_posix())
    return out


def _load(root: Path, rel: str) -> RepoFile | None:
    abspath = root / rel
    try:
        raw = abspath.read_bytes()
    except OSError:
        return None
    is_text = b"\x00" not in raw[:_NULL_SNIFF_BYTES]
    text = raw.decode("utf-8", errors="replace") if is_text else ""
    return RepoFile(path=rel, abspath=abspath, is_text=is_text, text=text)


def discover(root: Path) -> Repo:
    """Enumerate the published file set. Raises rather than returning a partial scan."""
    paths = _git_paths(root)
    if paths is None:
        paths = _walk_paths(root)
    loaded = (_load(root, rel) for rel in sorted(set(paths)))
    files = tuple(entry for entry in loaded if entry is not None)
    if not files:
        raise DiscoveryError(f"discovery found no files under {root}")
    found = {entry.path for entry in files}
    missing = [name for name in SENTINELS if name not in found]
    if missing:
        raise DiscoveryError(
            f"scan is untrustworthy, sentinel files missing: {missing}. "
            "Refusing to report a clean result."
        )
    return Repo(root=root, files=files)
