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


def _headings(text: str, pattern: re.Pattern[str]) -> tuple[dict[str, int], list[str]]:
    """{heading key: 1-based line}. A repeated key is ambiguous, so it is an error."""
    found: dict[str, int] = {}
    problems: list[str] = []
    for number, line in enumerate(text.split("\n"), start=1):
        match = pattern.match(line)
        if match is None:
            continue
        key = match.group("key")
        if key in found:
            problems.append(f"duplicate heading {key!r} at lines {found[key]} and {number}")
            continue
        found[key] = number
    return found, problems


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
    index_ends_at = 0
    for offset, line in enumerate(lines):
        match = spec.row.match(line)
        if match is None:
            continue
        index_ends_at = offset + 1
        name, key = match.group("file"), match.group("key")
        indexed.add((name, key))
        real = positions[name].get(key)
        if real is None:
            errors.append(f"{spec.live}: index row {key!r} has no heading in {name}")
            continue
        if int(match.group("num")) != real:
            start, end = match.span("num")
            drifts.append(Drift(file=name, key=key, old=int(match.group("num")), new=real))
            lines[offset] = line[:start] + str(real) + line[end:]

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
