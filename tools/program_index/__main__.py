"""Entry point: `python -m tools.program_index [--check]`.

Exit codes: 0 the indexes are true, 1 they are not, 2 the check could not run.
Without `--check` the drift is repaired in place; with it, nothing is written.
An index that could not be read has not passed: it has broken.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tools.program_index.index import SPECS, IndexSpec, Result, reindex

DOCS = Path(__file__).resolve().parents[2] / "docs" / "program"


def _run(spec: IndexSpec, docs: Path) -> Result:
    live, archive = docs / spec.live, docs / spec.archive
    return reindex(spec, live.read_text(), archive.read_text())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="program_index", description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="report drift and exit 1 instead of rewriting the index",
    )
    parser.add_argument("--docs", type=Path, default=DOCS, help="directory holding the logs")
    args = parser.parse_args(argv)

    drifted = False
    unrepairable = False
    for spec in SPECS:
        try:
            result = _run(spec, args.docs)
        except OSError as exc:
            print(f"program-index: FAILED, {exc}", file=sys.stderr)
            return 2

        if result.errors:
            unrepairable = True
            print(f"{spec.live}: {len(result.errors)} problem(s) a human must fix", file=sys.stderr)
            for error in result.errors:
                print(f"  {error}", file=sys.stderr)

        if not result.drifts:
            # Never call an index current on a run that just reported a problem in it.
            if not result.errors:
                print(f"{spec.live}: index is current")
            continue
        drifted = True
        stream = sys.stderr if args.check else sys.stdout
        print(
            f"{spec.live}: {len(result.drifts)} row(s) "
            f"{'stale' if args.check else 'corrected'}",
            file=stream,
        )
        for drift in result.drifts:
            print(f"  {drift.render()}", file=stream)
        if not args.check:
            (args.docs / spec.live).write_text(result.text)

    if args.check and drifted:
        print("Run `make reindex` to correct it.", file=sys.stderr)
    # Repairing drift is the fixer doing its job; only the unrepairable half fails it.
    return 1 if unrepairable or (args.check and drifted) else 0


if __name__ == "__main__":
    raise SystemExit(main())
