"""Group 3: preference-default gates.

R9 is structural: a shipped default that already contains one user's titles,
locations or filters is the exact failure this phase exists to prevent, and a
non-empty collection literal in these modules is the shape that takes.
"""

from __future__ import annotations

import ast
from collections.abc import Callable, Iterator
from typing import Any, cast

from tools.generalization import snapshots as snap
from tools.generalization.discovery import Repo
from tools.generalization.model import Violation

SCOPED_MODULES: tuple[str, ...] = (
    "src/boardwatch/core/settings.py",
    "src/boardwatch/cli/profile_cmd.py",
    "src/boardwatch/cli/init_cmd.py",
    "src/boardwatch/rank/heuristic.py",
    "src/boardwatch/eligibility/facts.py",
    "src/boardwatch/eligibility/hashing.py",
    "src/boardwatch/eligibility/catalog.py",
    "src/boardwatch/eligibility/detect.py",
    "src/boardwatch/eligibility/resolve.py",
)
INIT_MODULE = "src/boardwatch/cli/init_cmd.py"
HEURISTIC_MODULE = "src/boardwatch/rank/heuristic.py"


# Dunder declarations are decidably not preferences. __all__ is the one that actually occurs,
# and flagging it would make an idiomatic export list a landmine in a rule with no allowlist.
EXEMPT_TARGETS: frozenset[str] = frozenset({"__all__"})


def _holds_a_string(node: ast.expr) -> bool:
    """Whether a collection literal carries string content at any depth.

    R9 is scoped to collections OF STRINGS, so a tuple of retry backoffs is not a candidate.
    The search recurses, because grouping preference values one level down
    (`[['Chief Widget Officer']]`, `[{'title': ...}]`) is an ordinary shape rather than an
    evasion, and R9 has no backstop rule.

    A dict counts on its KEYS as well as its values, because a title-to-weight map carries the
    preference in the keys. The cost is that a string-keyed numeric dict is also a candidate.
    That is deliberate: R9 guards the only leak class with no second rule behind it, so it fails
    closed and a reviewer resolves the rare false positive.

    Only literal collections are traversed. A constructor call (`frozenset({...})`), string
    concatenation, a name reference and an f-string all evade it. These are accepted bypasses,
    the same limitation R1 and R2 have.
    """
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str)
    if isinstance(node, ast.Dict):
        parts = [key for key in node.keys if key is not None] + list(node.values)
    elif isinstance(node, ast.List | ast.Tuple | ast.Set):
        parts = list(node.elts)
    else:
        return False
    return any(_holds_a_string(part) for part in parts)


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
    that is an accepted bypass, not an oversight, and narrowing it further would reject the
    legitimate `Field(default_factory=RankWeights)` nested-model pattern.
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
    """Whether EVERY target of this statement is exempt.

    `any` here was a bypass: `__all__ = DEFAULT_TITLES = [...]` is one statement with two
    targets, so exempting on a single match let a real preference constant ride along with the
    dunder.
    """
    targets = _target_names(stmt)
    return bool(targets) and all(
        isinstance(target, ast.Name) and target.id in EXEMPT_TARGETS for target in targets
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
                            f"{why}: {ast.unparse(offender)!r}. If this is a preference, ship "
                            "it empty: a user's own values belong in their config or database. "
                            "If it is not a preference, this rule has no allowlist by design, "
                            "so express it as a model, build it with a constructor call, or "
                            "move it out of the scoped modules",
                        )
                    )
    return violations


SNAPSHOT_PATH = "tools/generalization/snapshots.py"


def _diff(
    actual: dict[str, object], expected: dict[str, object], label: str
) -> list[Violation]:
    violations: list[Violation] = []
    for key in sorted(set(actual) - set(expected)):
        violations.append(
            Violation(
                "R10",
                SNAPSHOT_PATH,
                None,
                f"new {label} {key!r} = {actual[key]!r} is not in the snapshot. Check "
                "whether it encodes one user's preference, then pin it",
            )
        )
    for key in sorted(set(expected) - set(actual)):
        violations.append(
            Violation(
                "R10", SNAPSHOT_PATH, None, f"snapshotted {label} {key!r} no longer exists"
            )
        )
    for key in sorted(set(actual) & set(expected)):
        if actual[key] != expected[key]:
            violations.append(
                Violation(
                    "R10",
                    SNAPSHOT_PATH,
                    None,
                    f"{label} {key!r} changed from {expected[key]!r} to {actual[key]!r}. "
                    "Confirm this is a neutral default, then update the snapshot",
                )
            )
    return violations


def _param_defaults(source: str) -> dict[str, object]:
    """Every parameter default in the module, keyed by scope-qualified name.

    This collects every positional-or-keyword and keyword-only default in the module, not a
    filtered set of ones that look like preferences: a heuristic for "looks like a preference"
    is exactly how this check would go silently blind to a new one. It is the snapshot
    comparison in check_defaults_snapshot that fails loudly on an addition; this function's
    job is only to see everything so that comparison has something complete to work with.

    Keys are qualified because a bare function name collides: a decoy method with the same
    name in the same module could otherwise shadow a changed real default and the snapshot
    would compare equal. Functions nested inside functions are not collected, because a local
    helper's default is not a shipped API default.
    """
    out: dict[str, object] = {}

    def collect(function: ast.FunctionDef | ast.AsyncFunctionDef, prefix: str) -> None:
        args = function.args
        positional = args.posonlyargs + args.args
        offset = len(positional) - len(args.defaults)
        for arg, default in zip(positional[offset:], args.defaults, strict=True):
            out[f"{prefix}.{arg.arg}"] = ast.unparse(default)
        for arg, kwdefault in zip(args.kwonlyargs, args.kw_defaults, strict=True):
            if kwdefault is not None:
                out[f"{prefix}.{arg.arg}"] = ast.unparse(kwdefault)

    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            collect(node, node.name)
        elif isinstance(node, ast.ClassDef):
            for member in node.body:
                if isinstance(member, ast.FunctionDef | ast.AsyncFunctionDef):
                    collect(member, f"{node.name}.{member.name}")
    return out


def check_defaults_snapshot(repo: Repo) -> list[Violation]:
    """R10: every settings default and preference-bearing parameter default is pinned."""
    from boardwatch.core.settings import LLMTier, RankWeights, Settings

    violations: list[Violation] = []
    if set(snap.SETTINGS_FIELD_CLASS) != set(snap.EXPECTED_SETTINGS_DEFAULTS):
        violations.append(
            Violation(
                "R10",
                SNAPSHOT_PATH,
                None,
                "SETTINGS_FIELD_CLASS and EXPECTED_SETTINGS_DEFAULTS cover different keys; "
                "every pinned default needs a reviewer-guidance class",
            )
        )

    actual: dict[str, object] = {}
    for model in (Settings, RankWeights, LLMTier):
        for name, field in model.model_fields.items():
            key = f"{model.__name__}.{name}"
            factory = field.default_factory
            if field.is_required():
                actual[key] = "REQUIRED"
            elif factory is not None:
                made = cast(Callable[[], Any], factory)()
                actual[key] = made.model_dump() if hasattr(made, "model_dump") else made
            else:
                actual[key] = field.default
    violations.extend(_diff(actual, snap.EXPECTED_SETTINGS_DEFAULTS, "settings default"))

    found = repo.by_path(HEURISTIC_MODULE)
    if found is None:
        violations.append(Violation("R10", HEURISTIC_MODULE, None, "module is missing"))
        return violations
    expected_params: dict[str, object] = dict(snap.EXPECTED_PARAM_DEFAULTS)
    try:
        violations.extend(_diff(_param_defaults(found.text), expected_params, "parameter default"))
    except SyntaxError as exc:
        violations.append(
            Violation(
                "R10",
                HEURISTIC_MODULE,
                exc.lineno,
                f"could not be parsed as Python ({exc.msg}), so the parameter default check "
                "is disabled",
            )
        )
    return violations


def _prompt_defaults(source: str) -> list[tuple[str, str, str | None]]:
    """Extract typer.prompt and typer.confirm calls with their defaults.

    Matches any object calling prompt or confirm, not just the literal typer. prefix,
    because the snapshot is an exact match. A broader matcher can only ADD rows, and an
    added row fails loudly. Requiring the literal prefix would let an alias like
    'import typer as _t' or 'from typer import prompt' silently remove a row, which is
    the failure mode this system exists to prevent. That is not fully closed: 'from typer
    import prompt as p' followed by a bare 'p(...)' call still removes a row silently,
    because the call site keeps only the renamed bare name, with neither an attribute nor
    a literal 'prompt'/'confirm' spelling left for this matcher to see.
    """
    rows: list[tuple[int, tuple[str, str, str | None]]] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute):
            called = func.attr
        elif isinstance(func, ast.Name):
            called = func.id
        else:
            continue
        if called not in ("prompt", "confirm"):
            continue
        prompt = ast.unparse(node.args[0]) if node.args else "<no-argument>"
        default: str | None = ast.unparse(node.args[1]) if len(node.args) > 1 else None
        for keyword in node.keywords:
            if keyword.arg == "default":
                default = ast.unparse(keyword.value)
        rows.append((node.lineno, (called, prompt, default)))
    return [row for _, row in sorted(rows, key=lambda item: item[0])]


def check_init_prompts(repo: Repo) -> list[Violation]:
    """R11: the first-run wizard never defaults to one user's titles or locations."""
    found = repo.by_path(INIT_MODULE)
    if found is None:
        return [Violation("R11", INIT_MODULE, None, "module is missing")]
    try:
        actual = tuple(_prompt_defaults(found.text))
    except SyntaxError as exc:
        return [
            Violation(
                "R11",
                INIT_MODULE,
                exc.lineno,
                f"could not be parsed as Python ({exc.msg}), so the init prompt check "
                "is disabled",
            )
        ]
    if actual == snap.EXPECTED_INIT_PROMPTS:
        return []
    return [
        Violation(
            "R11",
            INIT_MODULE,
            None,
            "init prompt defaults changed. Confirm no prompt now defaults to one user's "
            "titles, locations or filters, then update EXPECTED_INIT_PROMPTS.\n"
            f"    expected: {snap.EXPECTED_INIT_PROMPTS!r}\n"
            f"    actual:   {actual!r}",
        )
    ]
