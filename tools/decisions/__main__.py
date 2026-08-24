"""Entry point: `python -m tools.decisions --find <words>` / `--show D-113`.

Finding one decision should not cost reading the index. `DECISIONS.md`'s index block alone is
~114 KB (~28.6k tokens) and `METRICS.md` is 590 KB, so the documented "read the index, then the
one range" protocol charges the whole index for every lookup. This reads the index, prints only
the matching rows, and can emit the entry itself.

The index rows are the same ones `make index-check` keeps true (D-109), so a lookup here is only
as correct as the last `make reindex` — a stale index reports a stale range, not a wrong entry.

Exit codes: 0 a match was printed, 1 nothing matched, 2 the log could not be read.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tools.program_index.index import SPECS, IndexSpec, _index_block

DOCS = Path(__file__).resolve().parents[2] / "docs" / "program"

# key, file, line, title
Row = tuple[str, str, int, str]

_TITLE_CAP = 160

# `--log decisions` is the common case; SPECS carries METRICS too, and supporting it is a
# dict lookup rather than a second tool.
LOGS: dict[str, IndexSpec] = {"decisions": SPECS[0], "metrics": SPECS[1]}


class LogError(Exception):
    """The log could not be read."""


def _read(docs: Path, name: str) -> str:
    # `encoding="utf-8"` for the same reason program_index pins it: the headings carry em-dashes,
    # and a locale decoder turns every one of them into mojibake rather than an error.
    try:
        return (docs / name).read_text(encoding="utf-8")
    except OSError as exc:
        raise LogError(f"cannot read {name}: {exc}") from exc


def _rows(spec: IndexSpec, live_text: str) -> list[Row]:
    """(key, file, heading-line, title) for every row in the authoritative index block.

    Reuse `program_index._index_block` rather than matching every row-shaped line. These logs
    quote example index rows inside code fences and carry row-shaped lines below the index, and
    the block is the *first unbroken run of rows outside a fence* — exactly the rows `make reindex`
    keeps true (D-108/D-109). A bare per-line scan would surface a fenced example as a real entry,
    so `--find` would report a phantom and `--show` would extract against a heading that never
    existed. There are none in the logs today, which is precisely why this must not rely on it.
    """
    found: list[Row] = []
    for _number, match in _index_block(spec, live_text):
        title = match.string[match.end() :].strip().strip("|").strip()
        found.append((match["key"], match["file"], int(match["num"]), title))
    return found


def _find(rows: list[Row], words: list[str]) -> list[Row]:
    """Rows whose key or title contains every word, case-insensitively."""
    needles = [w.lower() for w in words]
    return [r for r in rows if all(n in f"{r[0]} {r[3]}".lower() for n in needles)]


def _extract(spec: IndexSpec, docs: Path, file: str, start: int) -> tuple[int, str]:
    """The entry at `start`, up to the line before the next heading. Returns (end, text)."""
    lines = _read(docs, file).splitlines()
    if not 1 <= start <= len(lines):
        raise LogError(f"{file}:{start} is past the end of the file — run `make reindex`")
    end = len(lines)
    for offset, line in enumerate(lines[start:], start=start + 1):
        if spec.heading.match(line):
            end = offset - 1
            break
    return end, "\n".join(lines[start - 1 : end]).rstrip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="decisions", description=__doc__)
    parser.add_argument("--log", choices=sorted(LOGS), default="decisions")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--find", nargs="+", metavar="WORD", help="rows matching every word")
    group.add_argument("--show", metavar="KEY", help="print the entry itself, e.g. D-113")
    # Some index titles run to several thousand characters, so an unbounded --find costs what
    # this tool exists to avoid. Truncate by default; --full opts back in.
    parser.add_argument("--full", action="store_true", help="do not truncate matched titles")
    args = parser.parse_args(argv)

    spec = LOGS[args.log]
    try:
        rows = _rows(spec, _read(DOCS, spec.live))
    except LogError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not rows:
        print(f"error: no index rows in {spec.live} — is the index block intact?", file=sys.stderr)
        return 2

    if args.find is not None:
        hits = _find(rows, args.find)
        if not hits:
            print(f"no match in {spec.live} for: {' '.join(args.find)}", file=sys.stderr)
            return 1
        for key, file, line, title in hits:
            shown = title if args.full or len(title) <= _TITLE_CAP else title[:_TITLE_CAP] + " …"
            print(f"{key}  {file}:{line}  {shown}")
        # The range is what makes the hit actionable; without it the caller re-greps.
        if len(hits) == 1:
            key, file, line, _ = hits[0]
            try:
                end, _text = _extract(spec, DOCS, file, line)
            except LogError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            print(f"\nsed -n '{line},{end}p' docs/program/{file}")
        return 0

    wanted = args.show.strip()
    for key, file, line, _title in rows:
        if key.lower() == wanted.lower():
            try:
                end, text = _extract(spec, DOCS, file, line)
            except LogError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            print(f"# {file}:{line}-{end}\n")
            print(text)
            return 0
    print(f"error: {wanted} is not in the {spec.live} index", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
