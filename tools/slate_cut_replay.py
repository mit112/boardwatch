"""T368: replay the slate cut from the `slate-cut-<run>.json` files the nightlies write.

Read-only. For each run it reports the survivors, the slate size, how many ELIGIBLE in-band
survivors sat beyond the cut, how many above-band (`no`) survivors took slate slots, and what a
seniority-first stable cut would have put in the slate instead, holding the slate size fixed at
the slots each run filled (a slot taken is not a delivery: a lead can still fail to render).

The cut's groups read the decision and the seniority reading together, because the two reads are
keyed differently and a seniority `yes` alone is not an opportunity: the judge can answer
`uncertain` with seniority `yes`, and after an effort switch a lead can carry `yes` from the old
effort with no current decision.

    1. in band:  decision `eligible` and seniority `yes`
    2. open:     decision `eligible` and seniority `unclear` or absent
    3. the rest: seniority `no`, or a decision that is absent, `uncertain` or `ineligible`

Ranker order (`position`) decides inside a group. Only files are replayed: a replay rebuilt from
gate rows alone would miss every survivor whose reading already stood, so it would be partial.
By default only runs that scanned (nightlies) are read; an intraday pass shares the day folder.

    python -m tools.slate_cut_replay [--all-runs] <day-dir-or-file> [...]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

PREFIX = "slate-cut-"


def _group(row: dict[str, object]) -> int:
    if row.get("decision") != "eligible":
        return 2
    fit = row.get("seniority_fit")
    return 0 if fit == "yes" else 2 if fit == "no" else 1


@dataclass(frozen=True)
class RunReplay:
    run_id: int
    survivors: int
    slate_size: int
    in_slate: int
    eligible_in_band_beyond: int
    above_band_in_slate: int
    above_band_in_slate_after: int
    swapped_in: tuple[int, ...]
    swapped_out: tuple[int, ...]


def replay(report: dict[str, object]) -> RunReplay:
    rows = [r for r in report["survivors"] if isinstance(r, dict)]  # type: ignore[attr-defined]
    slate = [r for r in rows if r["in_slate"]]
    k = len(slate)
    # Ranker order (`position`) decides inside a group.
    after = sorted(rows, key=lambda r: (_group(r), int(r["position"])))[:k]
    before_ids = {int(r["posting_id"]) for r in slate}
    after_ids = {int(r["posting_id"]) for r in after}
    return RunReplay(
        run_id=int(report["run_id"]),  # type: ignore[call-overload]
        survivors=len(rows),
        slate_size=int(report["slate_size"]),  # type: ignore[call-overload]
        in_slate=k,
        eligible_in_band_beyond=sum(1 for r in rows if not r["in_slate"] and _group(r) == 0),
        above_band_in_slate=sum(1 for r in slate if r.get("seniority_fit") == "no"),
        above_band_in_slate_after=sum(1 for r in after if r.get("seniority_fit") == "no"),
        swapped_in=tuple(sorted(after_ids - before_ids)),
        swapped_out=tuple(sorted(before_ids - after_ids)),
    )


def find_files(paths: Sequence[Path]) -> list[Path]:
    """Each path is a file, or a day folder (or an out root) holding `slate-cut-*.json`."""
    found: list[Path] = []
    for path in paths:
        if path.is_dir():
            found.extend(sorted({*path.glob(f"{PREFIX}*.json"), *path.glob(f"*/{PREFIX}*.json")}))
        elif path.is_file():
            found.append(path)
    return found


def table(replays: Sequence[RunReplay]) -> str:
    head = ("run", "survivors", "in slate", "eligible in-band beyond", "above-band in slate",
            "above-band after", "in", "out")
    lines = [head, *(
        (str(r.run_id), str(r.survivors), str(r.in_slate), str(r.eligible_in_band_beyond),
         str(r.above_band_in_slate), str(r.above_band_in_slate_after),
         str(len(r.swapped_in)), str(len(r.swapped_out)))
        for r in replays
    )]
    widths = [max(len(line[i]) for line in lines) for i in range(len(head))]
    return "\n".join(
        "  ".join(cell.rjust(width) for cell, width in zip(line, widths, strict=True))
        for line in lines
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument(
        "--all-runs", action="store_true",
        help="include runs that did not scan (intraday passes); default is nightlies only",
    )
    args = parser.parse_args(argv)
    reports = [json.loads(f.read_text(encoding="utf-8")) for f in find_files(args.paths)]
    if not args.all_runs:
        reports = [r for r in reports if r.get("scan_ran") is True]
    if not reports:
        print("no slate-cut files found", file=sys.stderr)
        return 1
    print(table(sorted((replay(r) for r in reports), key=lambda r: r.run_id)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
