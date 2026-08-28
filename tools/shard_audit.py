"""Prove that the sharded CI run actually executed the whole suite.

Sharding is only safe if the shards form a genuine partition of the collection. The failure
that matters is not a shard erroring — CI shows that — but a shard silently owning fewer
tests than it should, or a shard artifact never arriving. Either leaves the run green while
covering less than it claims, which is the same class of defect as a gate that passes because
it verified nothing.

A unit test of the splitter cannot establish this. It would still pass if the hook were never
registered, if `--shard` were parsed and ignored, if the matrix passed a wrong denominator,
or if two jobs collected different tests. Those are all cross-process properties, so the
evidence has to be cross-process too: every shard writes a manifest naming the full eligible
collection it saw and the subset it took, and this reads all of them together.

The checks, per Python version:

    exactly N manifests          - no shard's evidence went missing
    shard indexes are 1..N       - no duplicate or out-of-range shard ran
    every shard_total == N       - no shard used a stale denominator
    all full_digests identical   - every job collected the same suite
    pairwise disjoint            - no test ran twice
    union == full collection     - no test was dropped

N comes from the caller, which reads it from the same workflow output that built the matrix.
Nothing here hardcodes a shard count: a literal would let the matrix change to 4 while the
audit kept validating a population of 8, which is the exact drift this file exists to catch.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

MANIFEST_RE = re.compile(r"manifest-py(?P<python>[0-9.]+)-shard(?P<shard>\d+)\.json$")


@dataclass(frozen=True)
class Manifest:
    python: str
    shard: int
    shard_total: int
    full_count: int
    full_digest: str
    selected: frozenset[str]


def load(path: Path) -> Manifest:
    match = MANIFEST_RE.search(path.name)
    if match is None:
        raise ValueError(f"{path.name}: not a shard manifest name")
    body = json.loads(path.read_text())
    return Manifest(
        python=match["python"],
        shard=int(match["shard"]),
        shard_total=int(body["shard_total"]),
        full_count=int(body["full_count"]),
        full_digest=str(body["full_digest"]),
        selected=frozenset(body["selected"]),
    )


def audit_one_python(python: str, found: Sequence[Manifest], expected: int) -> list[str]:
    """Return the reasons this Python version's shard set is not a partition."""
    problems: list[str] = []

    if len(found) != expected:
        problems.append(
            f"py{python}: expected {expected} manifests, found {len(found)} "
            f"(shards {sorted(m.shard for m in found)})"
        )

    indexes = sorted(m.shard for m in found)
    if indexes != list(range(1, expected + 1)):
        problems.append(f"py{python}: shard indexes are {indexes}, expected 1..{expected}")

    stale = {m.shard: m.shard_total for m in found if m.shard_total != expected}
    if stale:
        problems.append(f"py{python}: shards ran with a stale denominator: {stale}")

    digests = {m.full_digest for m in found}
    if len(digests) > 1:
        problems.append(
            f"py{python}: shards disagree about the collection — {len(digests)} distinct "
            f"digests, so at least one job collected a different suite"
        )

    for left, right in combinations(sorted(found, key=lambda m: m.shard), 2):
        overlap = left.selected & right.selected
        if overlap:
            sample = sorted(overlap)[:3]
            problems.append(
                f"py{python}: shards {left.shard} and {right.shard} both ran "
                f"{len(overlap)} test(s), e.g. {sample}"
            )

    union = frozenset[str]().union(*(m.selected for m in found)) if found else frozenset[str]()
    full_count = found[0].full_count if found else 0
    if len(union) != full_count:
        problems.append(
            f"py{python}: shards ran {len(union)} distinct tests but collected "
            f"{full_count} — {full_count - len(union)} never ran"
        )

    return problems


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="directory holding the shard manifests")
    parser.add_argument("--shards", type=int, required=True, help="expected shards per Python")
    parser.add_argument(
        "--python", action="append", required=True, dest="pythons", help="expected Python version"
    )
    args = parser.parse_args(argv)

    manifests = [load(p) for p in sorted(args.directory.rglob("manifest-py*-shard*.json"))]
    if not manifests:
        print(f"FAIL: no shard manifests under {args.directory}", file=sys.stderr)
        return 1

    by_python: dict[str, list[Manifest]] = {}
    for manifest in manifests:
        by_python.setdefault(manifest.python, []).append(manifest)

    problems: list[str] = []
    unexpected = sorted(set(by_python) - set(args.pythons))
    if unexpected:
        problems.append(f"manifests from unexpected Python versions: {unexpected}")

    for python in args.pythons:
        problems.extend(audit_one_python(python, by_python.get(python, []), args.shards))

    if problems:
        print("FAIL: the shards are not a partition of the suite", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    total = manifests[0].full_count
    print(
        f"OK: {len(args.pythons)} Python version(s) x {args.shards} shards partition "
        f"{total} tests exactly."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
