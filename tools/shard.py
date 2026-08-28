"""Deterministic test sharding, so CI can spend jobs instead of wall clock.

The suite is ~8,200 tests and a GitHub standard runner has 4 vCPU, which put a PR at 30-42
minutes with `pytest -n auto` alone. The durations profile has no hot spot to fix — the
slowest single test is 1.5% of total CPU and the top 25 together are 9% — so the only lever
left is to run the tests on more machines at once.

Assignment is by SHA-256 of the node id, deliberately not by measured duration: a durations
file is a content pin that drifts as tests are added and needs its own staleness gate. On a
suite this flat, hashing balances well enough without one.

`hashlib`, not the builtin `hash()`: `hash()` is PYTHONHASHSEED-randomized per process, so
xdist workers would disagree about which tests they own and the run would die on a collection
mismatch.

The pytest wiring lives in the root `conftest.py`; this module is the part worth testing and
type-checking on its own.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path


class ShardSpecError(ValueError):
    """A `--shard` value that would silently run a partial suite."""


def parse_shard(spec: str) -> tuple[int, int]:
    """Parse `INDEX/TOTAL`, rejecting anything that would silently drop tests."""
    try:
        raw_index, raw_total = spec.split("/", 1)
        index, total = int(raw_index), int(raw_total)
    except ValueError:
        raise ShardSpecError(f"--shard must look like INDEX/TOTAL, got {spec!r}") from None
    if total < 1:
        raise ShardSpecError(f"--shard TOTAL must be >= 1, got {total}")
    if not 1 <= index <= total:
        raise ShardSpecError(f"--shard INDEX must be in 1..{total}, got {index}")
    return index, total


def owns(node_id: str, index: int, total: int) -> bool:
    """True when `node_id` belongs to 1-based shard `index` of `total`."""
    return int(hashlib.sha256(node_id.encode()).hexdigest(), 16) % total == index - 1


def collection_digest(node_ids: list[str]) -> str:
    """A stable fingerprint of a collection, order-independent.

    Comparing this across jobs is what detects two shards having collected different suites,
    which no single-process check can see.
    """
    return hashlib.sha256("\n".join(sorted(node_ids)).encode()).hexdigest()


def write_manifest(path: Path, full: list[str], selected: list[str], total: int) -> None:
    """Write this shard's evidence atomically.

    A half-written file that still parses would be read by the audit as authoritative. The
    rename makes the file appear complete or not at all; a crashed writer then shows up as a
    MISSING manifest, which the audit's exact-count check already fails on.
    """
    payload = {
        "shard_total": total,
        "full_count": len(full),
        "full_digest": collection_digest(full),
        "selected": sorted(selected),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".shard-manifest.")
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(payload, handle)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
