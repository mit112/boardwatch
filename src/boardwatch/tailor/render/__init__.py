from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from boardwatch.tailor.model import Resume

TypstRunner = Callable[[Path, Path], bool]

_BULLET = re.compile(r'#resume-bullet\("((?:[^"\\]|\\.)*)"\)')


class Renderer(Protocol):
    def emit(self, resume: Resume, *, reworded: frozenset[str] = frozenset()) -> str: ...

    def to_pdf(
        self, source: str, out_dir: Path, name: str, runner: TypstRunner
    ) -> Path | None: ...


def _unescape(s: str) -> str:
    return s.replace('\\"', '"').replace("\\\\", "\\")


def parse_bullets(source: str) -> list[str]:
    return [_unescape(m.group(1)) for m in _BULLET.finditer(source)]
