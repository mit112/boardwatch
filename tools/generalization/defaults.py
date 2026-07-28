"""Group 3: preference-default gates.

R9 is structural: a shipped default that already contains one user's titles,
locations or filters is the exact failure this phase exists to prevent, and a
non-empty collection literal in these modules is the shape that takes.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator

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


# Dunder declarations are decidably not preferences. __all__ is the one that actually occurs,
# and flagging it would make an idiomatic export list a landmine in a rule with no allowlist.
EXEMPT_TARGETS: frozenset[str] = frozenset({"__all__"})


def _holds_a_string(node: ast.expr) -> bool:
    """Whether a collection literal carries string content.

    Spec section 6 defines R9 over collections OF STRINGS. A tuple of retry backoffs or a
    dict of floats is not a preference list, and telling its author that their personal
    values belong in a config file would be the rule firing on legitimate content.
    """
    if isinstance(node, ast.Dict):
        parts = [key for key in node.keys if key is not None] + list(node.values)
    elif isinstance(node, ast.List | ast.Tuple | ast.Set):
        parts = list(node.elts)
    else:
        return False
    return any(
        isinstance(part, ast.Constant) and isinstance(part.value, str) for part in parts
    )


def _is_non_empty_collection(node: ast.expr) -> bool:
    if isinstance(node, ast.Dict):
        return bool(node.keys) and _holds_a_string(node)
    if isinstance(node, ast.List | ast.Tuple | ast.Set):
        return bool(node.elts) and _holds_a_string(node)
    return False


def _callee_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _returns_a_collection(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Whether any return statement in `function` yields a non-empty string collection."""
    return any(
        isinstance(node, ast.Return)
        and node.value is not None
        and _is_non_empty_collection(node.value)
        for node in ast.walk(function)
    )


def _local_factories(tree: ast.Module) -> set[str]:
    """Module-level function names whose body returns a non-empty string collection.

    A `default_factory` naming one of these is the same leak as an inline lambda. A factory
    naming something imported cannot be resolved from this module's AST and therefore passes:
    that is a recorded bypass (spec section 8), not an oversight, and narrowing it further
    would reject the legitimate `Field(default_factory=RankWeights)` nested-model pattern.
    """
    return {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and _returns_a_collection(node)
    }


def _offenders(value: ast.expr, local_factories: set[str]) -> list[tuple[ast.expr, str]]:
    if _is_non_empty_collection(value):
        return [(value, "non-empty collection default")]
    if isinstance(value, ast.Call) and _callee_name(value.func) == "Field":
        out: list[tuple[ast.expr, str]] = []
        for keyword in value.keywords:
            if keyword.arg == "default" and _is_non_empty_collection(keyword.value):
                out.append((keyword.value, "non-empty Field(default=...) collection"))
            if keyword.arg != "default_factory":
                continue
            factory = keyword.value
            if isinstance(factory, ast.Lambda) and _is_non_empty_collection(factory.body):
                out.append(
                    (factory, "default_factory lambda returning a non-empty collection")
                )
            if isinstance(factory, ast.Name) and factory.id in local_factories:
                out.append(
                    (
                        factory,
                        "default_factory naming a function that returns a non-empty collection",
                    )
                )
        return out
    return []


def _declarations(node: ast.AST) -> Iterator[ast.Assign | ast.AnnAssign]:
    """Assignments at declaration positions.

    Module level, class bodies including nested ones, and inside any block statement (an
    `if TYPE_CHECKING:` guard, a `try:`) at those levels. Function and lambda bodies are NOT
    descended into: a local variable is not a shipped default.
    """
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
            continue
        if isinstance(child, ast.Assign | ast.AnnAssign):
            yield child
        yield from _declarations(child)


def _target_names(stmt: ast.Assign | ast.AnnAssign) -> list[ast.expr]:
    return list(stmt.targets) if isinstance(stmt, ast.Assign) else [stmt.target]


def _assigned_values(stmt: ast.Assign | ast.AnnAssign) -> list[ast.expr]:
    """The values a statement assigns.

    Tuple unpacking assigns each element separately, so `A, B = [], []` assigns two empty
    lists rather than one two-element tuple.
    """
    if stmt.value is None:
        return []
    unpacking = any(
        isinstance(target, ast.Tuple | ast.List) for target in _target_names(stmt)
    )
    if unpacking and isinstance(stmt.value, ast.Tuple | ast.List):
        return list(stmt.value.elts)
    return [stmt.value]


def _is_exempt(stmt: ast.Assign | ast.AnnAssign) -> bool:
    return any(
        isinstance(target, ast.Name) and target.id in EXEMPT_TARGETS
        for target in _target_names(stmt)
    )


def check_collection_defaults(repo: Repo) -> list[Violation]:
    """R9: no non-empty collection as a module constant or a field default."""
    violations: list[Violation] = []
    for rel in SCOPED_MODULES:
        found = repo.by_path(rel)
        if found is None:
            violations.append(Violation("R9", rel, None, "scoped module is missing"))
            continue
        try:
            tree = ast.parse(found.text)
        except SyntaxError as exc:
            violations.append(
                Violation(
                    "R9",
                    rel,
                    exc.lineno,
                    f"could not be parsed as Python ({exc.msg}), so this module was not "
                    "checked. An unparseable module means the check is disabled, not that "
                    "it passed",
                )
            )
            continue
        local_factories = _local_factories(tree)
        for stmt in _declarations(tree):
            if _is_exempt(stmt):
                continue
            for value in _assigned_values(stmt):
                for offender, why in _offenders(value, local_factories):
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
