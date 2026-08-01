"""R12 wheel completeness: every shipped data file must reach the built wheel.

A data file that is in the tree but absent from the wheel breaks only INSTALLED users.
The dev checkout and the test suite both read it straight from src/, so every local gate
stays green while the published package is missing its eligibility rules or taxonomy.
"""

from __future__ import annotations

import subprocess
import tempfile
import zipfile
from pathlib import Path

from tools.generalization.discovery import Repo
from tools.generalization.model import Violation

IGNORED_NAMES = frozenset({".DS_Store"})


def shipped_data_files(repo: Repo) -> set[str]:
    """Non-Python files under the package, as the wheel would name them.

    Walks the tree directly rather than using `repo.files`: the wheel ships whatever is on
    disk under the package root, so that is what must be compared.
    """
    package = repo.root / "src" / "boardwatch"
    found: set[str] = set()
    for path in package.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix == ".py" or "__pycache__" in path.parts:
            continue
        if path.name in IGNORED_NAMES:
            continue
        found.add(path.relative_to(package.parent).as_posix())
    return found


def missing_from_wheel(expected: set[str], shipped: set[str]) -> list[Violation]:
    """The tree-minus-wheel difference, rendered as violations."""
    return [
        Violation(
            "R12",
            f"src/{name}",
            None,
            "present in the tree but MISSING from the built wheel. Installed users would "
            "not get this file, while every local gate stays green",
        )
        for name in sorted(expected - shipped)
    ]


def _build_wheel_namelist(root: Path) -> set[str]:
    """Build a wheel into a temp dir and return its member names.

    Raises on any failure: a rule that could not inspect the artifact has not passed, it
    has broken, and __main__ turns that into exit 2.
    """
    with tempfile.TemporaryDirectory() as tmp:
        result = subprocess.run(
            ["uv", "build", "--wheel", "--out-dir", tmp],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"uv build failed, so wheel contents are unknown:\n{result.stderr}")
        wheels = sorted(Path(tmp).glob("*.whl"))
        if len(wheels) != 1:
            raise RuntimeError(f"expected exactly one wheel, found {len(wheels)}")
        with zipfile.ZipFile(wheels[0]) as archive:
            return set(archive.namelist())


def check_wheel_completeness(repo: Repo) -> list[Violation]:
    """R12: every non-Python file under src/boardwatch must reach the built wheel."""
    return missing_from_wheel(shipped_data_files(repo), _build_wheel_namelist(repo.root))
