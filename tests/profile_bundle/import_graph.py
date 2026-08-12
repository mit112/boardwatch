"""First-party import edges read from the AST, not from a text grep.

A grep for one dotted spelling is not a boundary check. `from boardwatch.profile_bundle import
canonical` never contains the substring ``profile_bundle.canonical``, so a guard that greps for
that literal admits the exact bridge it exists to refuse, while reading as coverage. Parsing the
import statements catches the CLASS instead of one spelling: plain, dotted, aliased, from-import,
relative and function-local imports all resolve to the same dotted target here.

`reachable_from` walks those edges transitively, because a boundary that only checks direct
imports is satisfied by one module of indirection.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

#: The real source tree. Every helper takes `src_root` so the tests can drive the same code
#: over a synthetic tree and prove it fires.
SRC_ROOT: Final = Path(__file__).resolve().parents[2] / "src"

TOP_LEVEL_PACKAGE: Final = "boardwatch"


def module_name(path: Path, *, src_root: Path = SRC_ROOT) -> str:
    """The dotted name a source file is imported under."""
    parts = list(path.resolve().relative_to(src_root.resolve()).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def containing_package(path: Path, *, src_root: Path = SRC_ROOT) -> str:
    """The package a relative import inside this file is resolved against."""
    name = module_name(path, src_root=src_root)
    if path.name == "__init__.py":
        return name
    return name.rpartition(".")[0]


def _absolute(package: str, level: int, module: str | None) -> str:
    """Resolve a relative `from ... import` target against its containing package."""
    parts = package.split(".") if package else []
    keep = len(parts) - (level - 1)
    if keep <= 0:
        return ""
    prefix = ".".join(parts[:keep])
    return f"{prefix}.{module}" if module else prefix


def imported_modules(source: str, *, package: str = "") -> frozenset[str]:
    """Every first-party module name this source imports, in any spelling.

    A `from X import y` contributes both `X` and `X.y`, because the name bound may be either a
    submodule or an attribute and the guard must not have to know which.
    """
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            target = (
                _absolute(package, node.level, node.module) if node.level else (node.module or "")
            )
            if not target:
                continue
            found.add(target)
            found.update(f"{target}.{alias.name}" for alias in node.names if alias.name != "*")
    return frozenset(name for name in found if name.split(".")[0] == TOP_LEVEL_PACKAGE)


def imports_of(path: Path, *, src_root: Path = SRC_ROOT) -> frozenset[str]:
    """`imported_modules` for a file on disk, with its package resolved from its location."""
    return imported_modules(
        path.read_text(encoding="utf-8"),
        package=containing_package(path, src_root=src_root),
    )


def module_file(name: str, *, src_root: Path = SRC_ROOT) -> Path | None:
    """The file a dotted module name resolves to, or None if it names an attribute."""
    base = src_root.joinpath(*name.split("."))
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


@dataclass(frozen=True)
class Closure:
    """The transitive first-party import closure of a set of root files."""

    modules: frozenset[str]
    """Dotted names of the files actually walked, roots included."""

    targets: frozenset[str]
    """Every first-party name imported anywhere in the closure, submodule or attribute."""


def reachable_from(roots: Iterable[Path], *, src_root: Path = SRC_ROOT) -> Closure:
    """Walk first-party imports breadth-first from `roots` until nothing new resolves."""
    pending = list(roots)
    walked: dict[Path, str] = {}
    targets: set[str] = set()
    while pending:
        path = pending.pop()
        resolved = path.resolve()
        if resolved in walked:
            continue
        walked[resolved] = module_name(resolved, src_root=src_root)
        for target in imports_of(resolved, src_root=src_root):
            targets.add(target)
            found = module_file(target, src_root=src_root)
            if found is not None and found.resolve() not in walked:
                pending.append(found)
    return Closure(modules=frozenset(walked.values()), targets=frozenset(targets))
