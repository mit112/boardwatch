"""Fetch-side modules are DB-free in both directions (D16/D22)."""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "boardwatch"

# Task 8 appends "scan/workers.py" to this list.
FETCH_ONLY_MODULES = ["core/politeness.py"]


def test_fetch_modules_never_import_store() -> None:
    for rel in FETCH_ONLY_MODULES:
        tree = ast.parse((SRC / rel).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                assert not name.startswith("boardwatch.store"), f"{rel} imports {name}"
