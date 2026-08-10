"""Derive a program log's index line numbers from the headings themselves.

`DECISIONS.md` and `METRICS.md` each open with an index whose rows point at a heading in
either that file or its closed archive (D-108). Those numbers drift on *any* edit above a
heading, not only on an append — editing two preamble paragraphs once moved 32 decision
rows and 6 metrics rows at a stroke — so they are recomputed here rather than maintained
by hand.

`reindex` is pure and idempotent: it reads current heading positions, so it converges
however far the index has drifted, and reports no drift when the index is already right.

Two conditions it reports but will not repair, because repairing them means inventing
text a human owes: a heading with no index row, and an index row naming a heading that
does not exist.

**Fenced code blocks are not read.** These logs quote their own index rows and their own
`grep -n '^## '` output inside fences, so a fence-blind scan would rewrite an illustrative
row as if it were real and invent phantom duplicate headings. **The index is the first
unbroken run of index rows**, so a row-shaped line further down is prose, not an index
entry — anchoring to the last row-shaped line anywhere let one stray line switch off the
missing-row check for everything above it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class IndexSpec:
    """One live log, its closed archive, and how to recognise a heading and an index row.

    `heading` needs a `key` group. `row` needs `key`, `file` and `num` groups. Only the
    `num` span is rewritten, so a title carrying a pipe survives untouched.
    """

    live: str
    archive: str
    heading: re.Pattern[str]
    row: re.Pattern[str]


@dataclass(frozen=True)
class Drift:
    """An index row whose line number disagrees with its heading."""

    file: str
    key: str
    old: int
    new: int

    def render(self) -> str:
        return f"{self.file}:{self.key}: {self.old} -> {self.new}"


@dataclass(frozen=True)
class Result:
    """The corrected live text, what drifted, and what could not be repaired."""

    text: str
    drifts: tuple[Drift, ...]
    errors: tuple[str, ...]


SPECS: tuple[IndexSpec, ...] = (
    IndexSpec(
        live="DECISIONS.md",
        archive="DECISIONS-ARCHIVE.md",
        heading=re.compile(r"^## (?P<key>D-\d{3}) — "),
        row=re.compile(
            r"^\| (?P<key>D-\d{3}) \| (?P<file>DECISIONS(?:-ARCHIVE)?\.md) \| (?P<num>\d+) \|"
        ),
    ),
    IndexSpec(
        live="METRICS.md",
        archive="METRICS-ARCHIVE.md",
        heading=re.compile(r"^## (?P<key>.+)$"),
        row=re.compile(
            r"^\| (?P<file>METRICS(?:-ARCHIVE)?\.md) \| (?P<num>\d+) \| (?P<key>.+) \|$"
        ),
    ),
)


_FENCE = re.compile(r"^\s{0,3}(?:```|~~~)")


def _prose_lines(text: str) -> list[tuple[int, str]]:
    """(1-based line number, line) for every line outside a fenced code block."""
    outside: list[tuple[int, str]] = []
    fenced = False
    for number, line in enumerate(text.split("\n"), start=1):
        if _FENCE.match(line):
            fenced = not fenced
            continue
        if not fenced:
            outside.append((number, line))
    return outside


def _headings(text: str, pattern: re.Pattern[str]) -> tuple[dict[str, int], list[str]]:
    """{heading key: 1-based line}. A repeated key is ambiguous, so it resolves to nothing.

    Dropping the key rather than keeping the first occurrence means a row pointing at it
    reports "no heading" instead of being rewritten to a line nobody chose.
    """
    seen: dict[str, list[int]] = {}
    for number, line in _prose_lines(text):
        match = pattern.match(line)
        if match is not None:
            seen.setdefault(match.group("key"), []).append(number)
    found = {key: numbers[0] for key, numbers in seen.items() if len(numbers) == 1}
    problems = [
        f"duplicate heading {key!r} at lines {', '.join(str(n) for n in numbers)}"
        for key, numbers in seen.items()
        if len(numbers) > 1
    ]
    return found, problems


def _index_block(spec: IndexSpec, live_text: str) -> list[tuple[int, re.Match[str]]]:
    """The first unbroken run of index rows. Row-shaped lines after it are prose."""
    block: list[tuple[int, re.Match[str]]] = []
    for number, line in _prose_lines(live_text):
        match = spec.row.match(line)
        if match is None:
            continue
        if block and number != block[-1][0] + 1:
            break
        block.append((number, match))
    return block


def reindex(spec: IndexSpec, live_text: str, archive_text: str) -> Result:
    positions: dict[str, dict[str, int]] = {}
    errors: list[str] = []
    for name, text in ((spec.live, live_text), (spec.archive, archive_text)):
        found, problems = _headings(text, spec.heading)
        positions[name] = found
        errors.extend(f"{name}: {problem}" for problem in problems)

    lines = live_text.split("\n")
    drifts: list[Drift] = []
    indexed: set[tuple[str, str]] = set()
    block = _index_block(spec, live_text)
    index_ends_at = block[-1][0] if block else 0
    for number, match in block:
        name, key = match.group("file"), match.group("key")
        indexed.add((name, key))
        real = positions[name].get(key)
        if real is None:
            errors.append(f"{spec.live}: index row {key!r} has no heading in {name}")
            continue
        if int(match.group("num")) != real:
            start, end = match.span("num")
            drifts.append(Drift(file=name, key=key, old=int(match.group("num")), new=real))
            line = lines[number - 1]
            lines[number - 1] = line[:start] + str(real) + line[end:]

    # The index's own heading sits above the index; only content below it owes a row.
    for name in (spec.live, spec.archive):
        for key, number in positions[name].items():
            if name == spec.live and number <= index_ends_at:
                continue
            if (name, key) not in indexed:
                errors.append(
                    f"{spec.live}: {name} heading {key!r} at line {number} has no index row"
                )

    return Result(text="\n".join(lines), drifts=tuple(drifts), errors=tuple(errors))
