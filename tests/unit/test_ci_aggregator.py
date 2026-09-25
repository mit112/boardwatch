"""The `ci` job's truth table, run against the script ci.yml actually contains.

`ci` is the one required check, so what it accepts is what can merge and what main reports as
green. A push may now skip the Ubuntu shards (tools/ci_skip.py), and the only safe reading of
that skip is the narrow one: green ONLY on a push whose plan said skip, and a failure for every
other skip, on every other event. The script is extracted from ci.yml rather than copied, so an
edit to the workflow is what these cases test.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

CI_YML = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"
NEEDS = (
    "plan",
    "test-ubuntu",
    "test-other-os",
    "lint",
    "type",
    "shard-audit",
    "coverage",
    "gitleaks",
    "perf",
    "generalization",
    "web-bundle",
)
UBUNTU = {"test-ubuntu": "skipped", "shard-audit": "skipped", "coverage": "skipped"}


def _jobs() -> Any:
    return yaml.safe_load(CI_YML.read_text(encoding="utf-8"))["jobs"]


def _aggregate_step() -> Any:
    [step] = _jobs()["ci"]["steps"]
    return step


def _script() -> str:
    run: str = _aggregate_step()["run"]
    start = run.index("<<'PY'\n") + len("<<'PY'\n")
    return run[start : run.index("\nPY", start)]


def _aggregate(event: str, skip: str, **overrides: str) -> subprocess.CompletedProcess[str]:
    results = {name: "success" for name in NEEDS} | overrides
    needs = {name: {"result": result, "outputs": {}} for name, result in results.items()}
    env = {
        **os.environ,
        "RESULTS": json.dumps(needs),
        "EVENT": event,
        "SKIP_UBUNTU_TESTS": skip,
    }
    return subprocess.run(
        [sys.executable, "-c", _script()], env=env, capture_output=True, text=True, check=False
    )


def test_the_aggregate_needs_exactly_the_jobs_this_table_covers() -> None:
    assert tuple(_jobs()["ci"]["needs"]) == NEEDS


def test_the_skip_reaches_the_aggregate_from_the_plan_job() -> None:
    assert (
        _aggregate_step()["env"]["SKIP_UBUNTU_TESTS"]
        == "${{ needs.plan.outputs.skip_ubuntu_tests }}"
    )


def test_macos_does_not_read_the_skip() -> None:
    """`test-other-os` stays on every push: the platform boardwatch actually runs on."""
    assert "skip_ubuntu_tests" not in yaml.safe_dump(_jobs()["test-other-os"])


@pytest.mark.parametrize(
    ("event", "skip", "overrides"),
    [
        ("pull_request", "false", {"test-other-os": "skipped"}),
        ("push", "false", {}),
        ("push", "true", UBUNTU),
        ("schedule", "false", {}),
        ("workflow_dispatch", "false", {}),
    ],
)
def test_passes(event: str, skip: str, overrides: dict[str, str]) -> None:
    done = _aggregate(event, skip, **overrides)
    assert done.returncode == 0, done.stdout + done.stderr


@pytest.mark.parametrize(
    ("event", "skip", "overrides", "problem"),
    [
        # The pre-existing guarantees.
        ("pull_request", "false", {}, "test-other-os: expected 'skipped'"),
        ("push", "false", {"test-other-os": "skipped"}, "test-other-os: expected 'success'"),
        ("push", "false", {"lint": "failure"}, "lint: expected 'success'"),
        ("push", "false", {"coverage": "cancelled"}, "coverage: expected 'success'"),
        # A skip the plan did not order is a failure, whatever the event.
        ("push", "false", UBUNTU, "test-ubuntu: expected 'success'"),
        ("push", "", UBUNTU, "test-ubuntu: expected 'success'"),
        ("push", "True", UBUNTU, "test-ubuntu: expected 'success'"),
        ("push", "false", {"coverage": "skipped"}, "coverage: expected 'success'"),
        (
            "pull_request",
            "true",
            {**UBUNTU, "test-other-os": "skipped"},
            "test-ubuntu: expected 'success'",
        ),
        ("schedule", "true", UBUNTU, "test-ubuntu: expected 'success'"),
        ("workflow_dispatch", "true", UBUNTU, "test-ubuntu: expected 'success'"),
        # The ordered skip covers exactly the three Ubuntu jobs, and only as skips.
        ("push", "true", {**UBUNTU, "test-other-os": "skipped"}, "test-other-os: expected"),
        ("push", "true", {**UBUNTU, "lint": "failure"}, "lint: expected 'success'"),
        ("push", "true", {**UBUNTU, "plan": "failure"}, "plan: expected 'success'"),
        ("push", "true", {**UBUNTU, "test-ubuntu": "cancelled"}, "test-ubuntu: expected 'skipped'"),
        ("push", "true", {**UBUNTU, "test-ubuntu": "failure"}, "test-ubuntu: expected 'skipped'"),
        ("push", "true", {**UBUNTU, "coverage": "failure"}, "coverage: expected 'skipped'"),
        ("push", "true", {}, "test-ubuntu: expected 'skipped'"),
    ],
)
def test_fails(event: str, skip: str, overrides: dict[str, str], problem: str) -> None:
    done = _aggregate(event, skip, **overrides)
    assert done.returncode == 1, done.stdout + done.stderr
    assert problem in done.stdout
