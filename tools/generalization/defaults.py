"""Group 3: preference-default gates.

R9 is structural: a shipped default that already contains one user's titles,
locations or filters is the exact failure this phase exists to prevent, and a
non-empty collection literal in these modules is the shape that takes.
"""

from __future__ import annotations

import ast

from tools.generalization.discovery import Repo
from tools.generalization.model import Violation

SCOPED_MODULES: tuple[str, ...] = (
    "src/boardwatch/core/settings.py",
    "src/boardwatch/cli/profile_cmd.py",
    "src/boardwatch/cli/init_cmd.py",
    "src/boardwatch/rank/heuristic.py",
)
INIT_MODULE = "src/boardwatch/cli/init_cmd.py"
HEURISTIC_MODULE = "src/boardwatch/rank/heuristic.py"


def _is_non_empty_collection(node: ast.expr) -> bool:
    if isinstance(node, ast.Dict):
        return bool(node.keys)
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return bool(node.elts)
    return False


def _callee_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _offenders(value: ast.expr) -> list[tuple[ast.expr, str]]:
    if _is_non_empty_collection(value):
        return [(value, "non-empty collection default")]
    if isinstance(value, ast.Call) and _callee_name(value.func) == "Field":
        out: list[tuple[ast.expr, str]] = []
        for keyword in value.keywords:
            if keyword.arg == "default" and _is_non_empty_collection(keyword.value):
                out.append((keyword.value, "non-empty Field(default=...) collection"))
            if (
                keyword.arg == "default_factory"
                and isinstance(keyword.value, ast.Lambda)
                and _is_non_empty_collection(keyword.value.body)
            ):
                out.append(
                    (keyword.value, "default_factory lambda returning a non-empty collection")
                )
        return out
    return []


def check_collection_defaults(repo: Repo) -> list[Violation]:
    """R9: no non-empty collection as a module constant or a field default."""
    violations: list[Violation] = []
    for rel in SCOPED_MODULES:
        found = repo.by_path(rel)
        if found is None:
            violations.append(Violation("R9", rel, None, "scoped module is missing"))
            continue
        tree = ast.parse(found.text)
        statements: list[ast.stmt] = list(tree.body)
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                statements.extend(node.body)
        for stmt in statements:
            if not isinstance(stmt, (ast.Assign, ast.AnnAssign)):
                continue
            if stmt.value is None:
                continue
            for offender, why in _offenders(stmt.value):
                violations.append(
                    Violation(
                        "R9",
                        rel,
                        stmt.lineno,
                        f"{why}: {ast.unparse(offender)!r}. Preference collections ship "
                        "empty; a user's own values belong in their config or database",
                    )
                )
    return violations
