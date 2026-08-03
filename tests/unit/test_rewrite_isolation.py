"""Architectural guard (D5, §3 isolation): the Tier B rewrite package must never import
Tier A's `boardwatch.tailor.safety` (the no-fabrication verifier). Tier B's own gate is
the deterministic overmatch filter + fail-closed judge in this same package — it must
stand on its own rather than piggyback on Tier A's guarantee, which would blur the line
this task exists to keep sharp.

Pure-AST: this test never imports the modules it inspects, only parses their source, so
it cannot be defeated by import-time side effects and cannot accidentally pull in the
forbidden module itself.
"""

from __future__ import annotations

import ast
from pathlib import Path

PKG = Path("src/boardwatch/tailor/rewrite")
FORBIDDEN = "boardwatch.tailor.safety"


def _imported_paths(py: Path) -> set[str]:
    """Every fully-qualified path a module's imports could resolve to, covering both
    `import boardwatch.tailor.safety` and `from boardwatch.tailor import safety` forms.

    A plain `node.module` collection (checking only ImportFrom.module) misses the
    latter: `from boardwatch.tailor import safety` has `module == "boardwatch.tailor"`
    and the forbidden name only shows up in the imported alias, not the module path.
    """
    tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
    paths: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                paths.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            paths.add(node.module)
            for alias in node.names:
                paths.add(f"{node.module}.{alias.name}")
    return paths


def test_no_rewrite_module_imports_tier_a_safety() -> None:
    files = sorted(PKG.glob("*.py"))
    # Guards against the check passing vacuously if the package were ever moved,
    # renamed, or emptied out from under this test.
    assert len(files) >= 4, f"expected the rewrite package populated, found: {files}"
    for py in files:
        imported = _imported_paths(py)
        assert FORBIDDEN not in imported, f"{py} imports {FORBIDDEN}"
