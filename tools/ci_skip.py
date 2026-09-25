"""Decide whether a push to main may skip the Ubuntu shards a PR run already ran on its tree.

boardwatch ships by squash-merging a PR whose branch was rebuilt on main just before. When main did
not move in between, the squash commit's TREE is the PR head's tree, so the push run would re-test
byte-identical code — and, at 28 jobs against a 20-job ceiling, make the next PR queue behind it.

This is a SPEED-ONLY decision, so it fails SAFE: it prints `true` only when every fact below holds,
and `false` on anything else, including any API error, a missing field or an unexpected shape.

    the event is `push`
    a completed `pull_request` run of this workflow has a head commit with the push commit's tree
    no completed `pull_request` run on that tree concluded anything but success or cancelled
    the newest green one's head descends from the push commit's parent
    in that run, every shard of THIS push's matrix, `shard-audit`, `coverage` and `ci` succeeded

The descent check is what makes a tree match mean "tested". A PR run does not test its head; it
tests the merge of its head into the base branch as the base then was. That merge's tree is the
head's own tree only if the head already contained that base — which holds when the head descends
from the push's parent, because main only moves forward, so the base the PR run saw is an ancestor
of that parent. Without it, a head whose tree matches could have been tested merged with commits
main has since reverted.

Stdlib only: it runs on the bare runner before any environment is installed.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

Fetch = Callable[[str], Any]

# The jobs downstream of the shards that the push run would skip with them, plus the aggregate.
GATE_JOBS = ("shard-audit", "coverage", "ci")
# A run that concluded one of these on the same tree is not evidence against it; anything else is.
NOT_EVIDENCE = frozenset({"success", "cancelled"})
PER_PAGE = 100


@dataclass(frozen=True)
class Decision:
    skip: bool
    reason: str


def shard_job_names(pythons: Sequence[str], shards: int) -> frozenset[str]:
    """The names ci.yml's `test-ubuntu` matrix gives its jobs (pinned against ci.yml by a test)."""
    return frozenset(
        f"test ({p}, shard {i}/{shards})" for p in pythons for i in range(1, shards + 1)
    )


def _is_shard_job(name: str) -> bool:
    return name.startswith("test (") and ", shard " in name


def _check_jobs(body: Any, required: frozenset[str]) -> str | None:
    """None when every required job succeeded exactly once; otherwise what is wrong."""
    jobs = body["jobs"]
    if body["total_count"] != len(jobs):
        return f"the job list is incomplete ({len(jobs)} of {body['total_count']})"
    names = [job["name"] for job in jobs]
    foreign = sorted(n for n in set(names) if _is_shard_job(n) and n not in required)
    if foreign:
        return f"shard jobs outside this push's matrix: {foreign}"
    for name in sorted(required):
        found = [job for job in jobs if job["name"] == name]
        if len(found) != 1:
            return f"{len(found)} jobs named {name!r}, expected exactly 1"
        [job] = found
        if job["status"] != "completed" or job["conclusion"] != "success":
            return f"{name!r} is {job['status']}/{job['conclusion']}, not completed/success"
    return None


def _decide(
    *,
    event: str,
    repo: str,
    sha: str,
    workflow: str,
    pythons: Sequence[str],
    shards: int,
    fetch: Fetch,
) -> Decision:
    if event != "push":
        return Decision(False, f"event is {event!r}; only a push may skip")

    commit = fetch(f"repos/{repo}/git/commits/{sha}")
    tree = commit["tree"]["sha"]
    parents = commit["parents"]
    if len(parents) < 1:
        return Decision(False, f"{sha} has no parent to compare a PR head against")
    parent = parents[0]["sha"]

    listing = fetch(
        f"repos/{repo}/actions/workflows/{workflow}/runs"
        f"?event=pull_request&status=completed&per_page={PER_PAGE}"
    )
    matches = [
        run
        for run in listing["workflow_runs"]
        if run["event"] == "pull_request"
        and run["status"] == "completed"
        and run["head_commit"]["tree_id"] == tree
    ]
    if not matches:
        return Decision(False, f"no completed pull_request run tested tree {tree}")

    doubtful = sorted(
        (run["id"], run["conclusion"]) for run in matches if run["conclusion"] not in NOT_EVIDENCE
    )
    if doubtful:
        return Decision(False, f"pull_request runs on tree {tree} concluded {doubtful}")

    green = [run for run in matches if run["conclusion"] == "success"]
    if not green:
        return Decision(False, f"no pull_request run on tree {tree} succeeded")
    run = max(green, key=lambda r: (r["created_at"], r["id"]))
    run_id, head = run["id"], run["head_sha"]

    status = fetch(f"repos/{repo}/compare/{parent}...{head}")["status"]
    if status not in ("ahead", "identical"):
        return Decision(
            False, f"run {run_id}'s head {head} is {status} of the push's parent {parent}"
        )

    required = shard_job_names(pythons, shards) | frozenset(GATE_JOBS)
    problem = _check_jobs(
        fetch(f"repos/{repo}/actions/runs/{run_id}/jobs?filter=latest&per_page={PER_PAGE}"),
        required,
    )
    if problem is not None:
        return Decision(False, f"run {run_id}: {problem}")

    return Decision(True, f"run {run_id} (head {head}) passed every Ubuntu shard on tree {tree}")


def decide(
    *,
    event: str,
    repo: str,
    sha: str,
    workflow: str,
    pythons: Sequence[str],
    shards: int,
    fetch: Fetch,
) -> Decision:
    """The decision, with every failure — API, shape, anything — turned into "run the tests"."""
    try:
        return _decide(
            event=event,
            repo=repo,
            sha=sha,
            workflow=workflow,
            pythons=pythons,
            shards=shards,
            fetch=fetch,
        )
    except Exception as exc:  # noqa: BLE001 — fail-safe by design: any doubt runs the tests
        return Decision(False, f"could not decide ({type(exc).__name__}: {exc})")


def gh_fetch(path: str) -> Any:
    """One read-only GET through `gh api`, which authenticates from GH_TOKEN."""
    done = subprocess.run(
        ["gh", "api", "-H", "Accept: application/vnd.github+json", path],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if done.returncode != 0:
        raise RuntimeError(f"gh api {path} exited {done.returncode}: {done.stderr.strip()}")
    return json.loads(done.stdout)


def main(argv: Sequence[str] | None = None, fetch: Fetch = gh_fetch) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", required=True)
    parser.add_argument("--repo", required=True, help="owner/name")
    parser.add_argument("--sha", required=True, help="the pushed commit")
    parser.add_argument("--workflow", required=True, help="this workflow's file name")
    parser.add_argument("--pythons", required=True, help="space-separated, as `plan` emits them")
    parser.add_argument("--shards", type=int, required=True)
    args = parser.parse_args(argv)

    decision = decide(
        event=args.event,
        repo=args.repo,
        sha=args.sha,
        workflow=args.workflow,
        pythons=args.pythons.split(),
        shards=args.shards,
        fetch=fetch,
    )
    print(f"skip_ubuntu_tests={str(decision.skip).lower()}: {decision.reason}", file=sys.stderr)
    print("true" if decision.skip else "false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
