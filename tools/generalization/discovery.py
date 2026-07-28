"""File discovery for the generalization checks.

`git ls-files` is preferred because it enumerates exactly what gets published. Its output is
NOT filtered: everything tracked is published, so filtering would skip the tree. A filesystem
walk is the fallback outside a git work tree, and EXCLUDED_DIRS applies only there, where
untracked local debris (a virtualenv, a build directory, tool caches) really is noise.

Discovery NEVER skips. A scan that cannot run must fail, because a zero-file scan reporting
success is the dangerous failure mode: the gate would look green while being entirely disabled.
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
        ".reasonix-runs",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".idea",
        ".vscode",
        "node_modules",
    }
)

_NULL_SNIFF_BYTES = 8192

# The real tree holds 165+ tracked files. This is a truncation floor for the CLI to
# pass to `discover`, not a value used by anything in this module.
PRODUCTION_MINIMUM_FILES = 40


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
    mode: str = "walk"

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


def _is_excluded(rel: str) -> bool:
    """Whether a discovered relative path falls under a directory we never scan."""
    return any(part in EXCLUDED_DIRS for part in PurePosixPath(rel).parts)


def _git_paths(root: Path) -> list[str] | None:
    """Tracked paths, or None when this is not a usable git work tree."""
    try:
        proc = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=root,
            capture_output=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    # No exclude filter here, deliberately. Everything git tracks is published content, so
    # filtering it would skip the tree rather than skip debris: a tracked .vscode/settings.json
    # holding a home path, or a tracked build/resume.yaml, would vanish from every rule while
    # the gate reported OK. EXCLUDED_DIRS applies only to the filesystem-walk fallback, where
    # untracked local debris is real.
    decoded = proc.stdout.decode("utf-8", errors="surrogateescape")
    paths = [p for p in decoded.split("\0") if p]
    return paths or None


def _walk_paths(root: Path) -> list[str]:
    out: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if _is_excluded(rel):
            continue
        out.append(rel)
    return out


def _load(root: Path, rel: str) -> RepoFile:
    """Load one discovered file. Raises OSError; callers must not swallow it."""
    abspath = root / rel
    raw = abspath.read_bytes()
    is_text = b"\x00" not in raw[:_NULL_SNIFF_BYTES]
    text = raw.decode("utf-8", errors="replace") if is_text else ""
    return RepoFile(path=rel, abspath=abspath, is_text=is_text, text=text)


def discover(root: Path, *, minimum_files: int = 1) -> Repo:
    """Enumerate the published file set. Raises rather than returning a partial scan."""
    paths = _git_paths(root)
    mode = "git" if paths is not None else "walk"
    if paths is None:
        paths = _walk_paths(root)
    files: list[RepoFile] = []
    unreadable: list[str] = []
    for rel in sorted(set(paths)):
        try:
            files.append(_load(root, rel))
        except OSError:
            unreadable.append(rel)
    if unreadable:
        raise DiscoveryError(
            f"cannot read {len(unreadable)} discovered file(s), refusing to report a "
            f"clean scan: {unreadable}"
        )
    if not files:
        raise DiscoveryError(f"discovery found no files under {root}")
    if len(files) < minimum_files:
        raise DiscoveryError(
            f"discovery found {len(files)} file(s) under {root}, fewer than the "
            f"required minimum of {minimum_files}. Refusing to report a clean scan."
        )
    found = {entry.path for entry in files}
    missing = [name for name in SENTINELS if name not in found]
    if missing:
        raise DiscoveryError(
            f"scan is untrustworthy, sentinel files missing: {missing}. "
            "Refusing to report a clean result."
        )
    return Repo(root=root, files=tuple(files), mode=mode)
