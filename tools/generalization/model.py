"""Shared value types for the generalization rules."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from tools.generalization.discovery import Repo


@dataclass(frozen=True)
class Violation:
    """One rule failure, addressed to the person who has to fix it."""

    rule: str
    path: str
    line: int | None
    detail: str

    def render(self) -> str:
        where = f"{self.path}:{self.line}" if self.line is not None else self.path
        return f"[{self.rule}] {where}: {self.detail}"


Rule = Callable[[Repo], list[Violation]]
