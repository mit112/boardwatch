from __future__ import annotations

from pathlib import Path
from typing import Protocol

from boardwatch.tailor.model import Resume
from boardwatch.tailor.render.latex import unescape
from boardwatch.tailor.render.outcome import CompileOutcome, CompileRunner


class Renderer(Protocol):
    def emit(self, resume: Resume, *, reworded: frozenset[str] = frozenset()) -> str: ...

    def to_pdf(
        self, source: str, out_dir: Path, name: str, runner: CompileRunner
    ) -> CompileOutcome: ...


def parse_bullets(source: str) -> list[str]:
    out: list[str] = []
    marker = r"\resumeItem{"
    i = 0
    while (start := source.find(marker, i)) != -1:
        pos = start + len(marker)
        depth = 1
        while pos < len(source) and depth:
            c = source[pos]
            if c == "\\":  # escaped literal (\{ \} \% ...) — skip both chars, no depth change
                pos += 2
                continue
            depth += (c == "{") - (c == "}")
            pos += 1
        out.append(unescape(source[start + len(marker) : pos - 1]))
        i = pos
    return out
