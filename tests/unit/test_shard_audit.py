"""The shard split must be a partition, and the audit must notice when it is not.

These tests are deliberately written against BROKEN shard sets rather than only a healthy
one. A green audit over a correct partition proves very little — the audit would also be
green if it checked nothing. What earns the gate its keep is that each specific corruption
below is rejected, and each test names the corruption it defends against.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tools.shard import ShardSpecError, collection_digest, owns, parse_shard
from tools.shard_audit import audit_one_python, load, main

NODE_IDS = [f"tests/unit/test_mod{i % 17}.py::test_case_{i}" for i in range(400)]


# --------------------------------------------------------------------------------------
# The splitter itself
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("total", [2, 3, 4, 8, 13])
def test_every_test_lands_in_exactly_one_shard(total: int) -> None:
    owners = [[n for n in NODE_IDS if owns(n, i, total)] for i in range(1, total + 1)]
    flat = [n for shard in owners for n in shard]
    assert sorted(flat) == sorted(NODE_IDS), "the shards are not a partition"
    assert len(flat) == len(set(flat)), "a test was assigned to more than one shard"


def test_assignment_does_not_depend_on_collection_order() -> None:
    """Hashing is content-based, so a reordered collection yields the same shards.

    This is what lets eight independent jobs agree without coordinating.
    """
    forward = {n for n in NODE_IDS if owns(n, 2, 5)}
    backward = {n for n in reversed(NODE_IDS) if owns(n, 2, 5)}
    assert forward == backward


def test_assignment_survives_a_different_process_hash_seed() -> None:
    """The property the whole design rests on, and the one a single-process test cannot see.

    xdist workers are separate processes. Python randomises `hash()` per process unless
    PYTHONHASHSEED is fixed, so a splitter built on `hash()` would have workers disagree
    about which tests they own — and eight CI jobs disagree the same way, silently running
    an overlapping or incomplete suite.

    Every in-process partition test still passes against that bug, because within ONE process
    `hash()` is perfectly consistent. Only crossing a process boundary with a different seed
    exposes it.
    """
    import subprocess
    import sys

    root = str(Path(__file__).resolve().parents[2])
    program = (
        "import json,sys;"
        f"sys.path.insert(0, {root!r});"
        "from tools.shard import owns;"
        "print(json.dumps([n for n in json.loads(sys.argv[1]) if owns(n, 2, 5)]))"
    )
    seeds = ["0", "1", "12345"]
    results = [
        json.loads(
            subprocess.run(
                [sys.executable, "-c", program, json.dumps(NODE_IDS)],
                capture_output=True,
                text=True,
                check=True,
                env={"PYTHONHASHSEED": seed, "PATH": os.environ.get("PATH", "")},
            ).stdout
        )
        for seed in seeds
    ]
    in_process = [n for n in NODE_IDS if owns(n, 2, 5)]
    for seed, result in zip(seeds, results, strict=True):
        assert result == in_process, f"shard membership changed under PYTHONHASHSEED={seed}"


def test_a_single_shard_keeps_everything() -> None:
    assert all(owns(n, 1, 1) for n in NODE_IDS)


@pytest.mark.parametrize("spec", ["0/4", "5/4", "-1/4", "1/0", "abc", "1", "1/2/3", ""])
def test_a_shard_spec_that_would_drop_tests_is_refused(spec: str) -> None:
    """Every rejected spec here would otherwise silently run a partial suite."""
    with pytest.raises(ShardSpecError):
        parse_shard(spec)


@pytest.mark.parametrize("spec,expected", [("1/1", (1, 1)), ("3/8", (3, 8)), ("8/8", (8, 8))])
def test_a_valid_shard_spec_parses(spec: str, expected: tuple[int, int]) -> None:
    assert parse_shard(spec) == expected


# --------------------------------------------------------------------------------------
# The cross-job audit
# --------------------------------------------------------------------------------------


def _manifests(total: int, node_ids: list[str] | None = None) -> list[dict[str, object]]:
    ids = NODE_IDS if node_ids is None else node_ids
    digest = collection_digest(ids)
    return [
        {
            "shard_total": total,
            "full_count": len(ids),
            "full_digest": digest,
            "selected": sorted(n for n in ids if owns(n, i, total)),
        }
        for i in range(1, total + 1)
    ]


def _write(tmp_path: Path, bodies: list[dict[str, object]], python: str = "3.12") -> Path:
    for i, body in enumerate(bodies, start=1):
        (tmp_path / f"manifest-py{python}-shard{i}.json").write_text(json.dumps(body))
    return tmp_path


def _audit(tmp_path: Path, bodies: list[dict[str, object]], shards: int) -> list[str]:
    _write(tmp_path, bodies)
    found = [load(p) for p in sorted(tmp_path.glob("manifest-py*-shard*.json"))]
    return audit_one_python("3.12", found, shards)


def test_a_clean_partition_passes(tmp_path: Path) -> None:
    assert _audit(tmp_path, _manifests(4), shards=4) == []


def test_a_missing_shard_artifact_is_caught(tmp_path: Path) -> None:
    """The upload silently failing is the likeliest real-world corruption."""
    bodies = _manifests(4)[:3]
    problems = _audit(tmp_path, bodies, shards=4)
    assert any("expected 4 manifests, found 3" in p for p in problems)
    assert any("never ran" in p for p in problems)


def test_a_test_running_in_two_shards_is_caught(tmp_path: Path) -> None:
    bodies = _manifests(4)
    stolen = sorted(bodies[0]["selected"])[0]  # type: ignore[call-overload]
    bodies[1]["selected"] = sorted([*bodies[1]["selected"], stolen])  # type: ignore[misc]
    problems = _audit(tmp_path, bodies, shards=4)
    assert any("both ran" in p for p in problems)


def test_a_dropped_test_is_caught(tmp_path: Path) -> None:
    """A shard that quietly runs fewer tests than it owns."""
    bodies = _manifests(4)
    bodies[2]["selected"] = sorted(bodies[2]["selected"])[1:]  # type: ignore[index,misc]
    problems = _audit(tmp_path, bodies, shards=4)
    assert any("never ran" in p for p in problems)


def test_shards_that_collected_different_suites_are_caught(tmp_path: Path) -> None:
    """Cross-job collection drift — the thing no single-process test can see."""
    bodies = _manifests(4)
    bodies[3]["full_digest"] = "0" * 64
    problems = _audit(tmp_path, bodies, shards=4)
    assert any("disagree about the collection" in p for p in problems)


def test_a_stale_denominator_is_caught(tmp_path: Path) -> None:
    """A job still running --shard i/8 after the matrix moved to 4."""
    bodies = _manifests(4)
    bodies[1]["shard_total"] = 8
    problems = _audit(tmp_path, bodies, shards=4)
    assert any("stale denominator" in p for p in problems)


def test_the_expected_shard_count_is_not_hardcoded(tmp_path: Path) -> None:
    """Changing the matrix must change what the audit demands, or it validates nothing."""
    assert _audit(tmp_path, _manifests(2), shards=2) == []
    assert _audit(tmp_path, _manifests(2), shards=4) != []


def test_main_fails_loudly_when_no_manifests_arrived(tmp_path: Path) -> None:
    assert main([str(tmp_path), "--shards", "4", "--python", "3.12"]) == 1


def test_main_accepts_a_healthy_multi_version_run(tmp_path: Path) -> None:
    for python in ("3.11", "3.12", "3.13"):
        _write(tmp_path, _manifests(4), python=python)
    assert main([str(tmp_path), "--shards", "4", "--python", "3.11",
                 "--python", "3.12", "--python", "3.13"]) == 0


def test_main_rejects_a_run_missing_an_entire_python_version(tmp_path: Path) -> None:
    for python in ("3.11", "3.12"):
        _write(tmp_path, _manifests(4), python=python)
    assert main([str(tmp_path), "--shards", "4", "--python", "3.11",
                 "--python", "3.12", "--python", "3.13"]) == 1
