"""The push run may skip the Ubuntu shards ONLY when a green PR run already tested the same tree.

The decision is speed-only and must fail SAFE: every doubt runs the tests. So most of these tests
build a case that is one fact away from "skip" and assert that it runs — and each asserts the
REASON too, because a fake API that answers a misrouted request with an error would otherwise make
every "run" test pass for the wrong reason.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from tools import ci_skip
from tools.ci_skip import Decision, decide, shard_job_names

REPO = "owner/repo"
WORKFLOW = "ci.yml"
PUSH_SHA = "a" * 40
PARENT = "b" * 40
TREE = "c" * 40
OTHER_TREE = "d" * 40
PR_HEAD = "e" * 40
OLDER_PR_HEAD = "f" * 40
PYTHONS = ("3.11", "3.12", "3.13")
SHARDS = 4

COMMIT_PATH = f"repos/{REPO}/git/commits/{PUSH_SHA}"
RUNS_PATH = f"repos/{REPO}/actions/workflows/{WORKFLOW}/runs?event=pull_request&status=completed&per_page=100"


def compare_path(head: str) -> str:
    return f"repos/{REPO}/compare/{PARENT}...{head}"


def pulls_path(head: str) -> str:
    return f"repos/{REPO}/commits/{head}/pulls?per_page=100"


def _pull(
    number: int, base: str = "main", base_repo: str = REPO, head_repo: str | None = REPO
) -> Any:
    return {
        "number": number,
        "base": {"ref": base, "repo": {"full_name": base_repo}},
        "head": {
            "ref": f"branch-{number}",
            "repo": None if head_repo is None else {"full_name": head_repo},
        },
    }


def events_path(number: int) -> str:
    return f"repos/{REPO}/issues/{number}/events?per_page=100"


def _events(*kinds: str) -> list[dict[str, Any]]:
    return [{"id": i, "event": kind} for i, kind in enumerate(("closed", "merged", *kinds))]


def jobs_path(run_id: int) -> str:
    return f"repos/{REPO}/actions/runs/{run_id}/jobs?filter=latest&per_page=100"


def _run(run_id: int, head: str, tree: str, conclusion: str = "success") -> dict[str, Any]:
    return {
        "id": run_id,
        "event": "pull_request",
        "status": "completed",
        "conclusion": conclusion,
        "head_sha": head,
        "head_commit": {"id": head, "tree_id": tree},
        "created_at": f"2026-09-25T0{run_id % 10}:00:00Z",
    }


def _green_jobs() -> dict[str, Any]:
    # The shape a real PR run returns: every gate, plus the jobs a PR skips by design.
    names = [
        "plan",
        "lint",
        "type (3.11)",
        "gitleaks",
        *sorted(shard_job_names(PYTHONS, SHARDS)),
        "shard-audit",
        "coverage",
        "ci",
    ]
    jobs = [{"name": n, "status": "completed", "conclusion": "success"} for n in names]
    jobs.append(
        {
            "name": "test (${{ matrix.python }}, ${{ matrix.os }})",
            "status": "completed",
            "conclusion": "skipped",
        }
    )
    jobs.append({"name": "nightly-watch", "status": "completed", "conclusion": "skipped"})
    return {"total_count": len(jobs), "jobs": jobs}


def _api() -> dict[str, Any]:
    """A push whose tree one green, up-to-date PR run already tested: the one case that skips."""
    return {
        COMMIT_PATH: {"sha": PUSH_SHA, "tree": {"sha": TREE}, "parents": [{"sha": PARENT}]},
        RUNS_PATH: {"total_count": 1, "workflow_runs": [_run(7, PR_HEAD, TREE)]},
        compare_path(PR_HEAD): {"status": "ahead"},
        pulls_path(PR_HEAD): [_pull(480)],
        events_path(480): _events(),
        jobs_path(7): _green_jobs(),
    }


class FakeAPI:
    def __init__(self, responses: dict[str, Any], fail: frozenset[str] = frozenset()) -> None:
        self.responses = responses
        self.fail = fail
        self.calls: list[str] = []

    def __call__(self, path: str) -> Any:
        self.calls.append(path)
        if path in self.fail:
            raise RuntimeError(f"HTTP 502 for {path}")
        if path not in self.responses:
            raise AssertionError(f"unexpected API path {path}")
        return copy.deepcopy(self.responses[path])


def _decide(api: FakeAPI, event: str = "push") -> Decision:
    return decide(
        event=event,
        repo=REPO,
        sha=PUSH_SHA,
        workflow=WORKFLOW,
        branch="main",
        pythons=PYTHONS,
        shards=SHARDS,
        fetch=api,
    )


def _set_job(api: dict[str, Any], name: str, conclusion: str) -> None:
    [job] = [j for j in api[jobs_path(7)]["jobs"] if j["name"] == name]
    job["conclusion"] = conclusion


# --------------------------------------------------------------------------------------
# The one case that skips
# --------------------------------------------------------------------------------------


def test_a_green_up_to_date_pr_run_on_the_same_tree_skips() -> None:
    decision = _decide(FakeAPI(_api()))
    assert decision.skip is True, decision.reason
    assert "run 7 " in decision.reason


# --------------------------------------------------------------------------------------
# One fact away from skip: each must run
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("event", ["pull_request", "schedule", "workflow_dispatch"])
def test_a_non_push_event_always_runs_without_calling_the_api(event: str) -> None:
    api = FakeAPI(_api())
    decision = _decide(api, event=event)
    assert decision.skip is False
    assert "only a push may skip" in decision.reason
    assert api.calls == []


@pytest.mark.parametrize("conclusion", ["failure", "skipped", "cancelled", "timed_out"])
@pytest.mark.parametrize("name", ["test (3.12, shard 3/4)", "shard-audit", "coverage", "ci"])
def test_one_required_job_that_did_not_succeed_runs(name: str, conclusion: str) -> None:
    api = _api()
    _set_job(api, name, conclusion)
    decision = _decide(FakeAPI(api))
    assert decision.skip is False
    assert f"{name!r} is " in decision.reason


def test_a_required_job_still_in_progress_runs() -> None:
    api = _api()
    [job] = [j for j in api[jobs_path(7)]["jobs"] if j["name"] == "test (3.11, shard 1/4)"]
    job["status"] = "in_progress"
    decision = _decide(FakeAPI(api))
    assert decision.skip is False
    assert "'test (3.11, shard 1/4)' is in_progress" in decision.reason


def test_a_missing_shard_job_runs() -> None:
    api = _api()
    jobs = api[jobs_path(7)]
    jobs["jobs"] = [j for j in jobs["jobs"] if j["name"] != "test (3.13, shard 4/4)"]
    jobs["total_count"] = len(jobs["jobs"])
    decision = _decide(FakeAPI(api))
    assert decision.skip is False
    assert "0 jobs named 'test (3.13, shard 4/4)'" in decision.reason


def test_a_shard_job_outside_this_runs_matrix_runs() -> None:
    """The PR run sharded differently from this push's plan: its shards are not this push's shards."""
    api = _api()
    jobs = api[jobs_path(7)]
    jobs["jobs"].append(
        {"name": "test (3.11, shard 5/5)", "status": "completed", "conclusion": "success"}
    )
    jobs["total_count"] = len(jobs["jobs"])
    decision = _decide(FakeAPI(api))
    assert decision.skip is False
    assert "test (3.11, shard 5/5)" in decision.reason


def test_a_duplicated_required_job_name_runs() -> None:
    api = _api()
    jobs = api[jobs_path(7)]
    jobs["jobs"].append({"name": "ci", "status": "completed", "conclusion": "success"})
    jobs["total_count"] = len(jobs["jobs"])
    decision = _decide(FakeAPI(api))
    assert decision.skip is False
    assert "2 jobs named 'ci'" in decision.reason


def test_a_truncated_job_list_runs() -> None:
    api = _api()
    api[jobs_path(7)]["total_count"] = 101
    decision = _decide(FakeAPI(api))
    assert decision.skip is False
    assert "the job list is incomplete (21 of 101)" in decision.reason


def test_no_pr_run_on_this_tree_runs() -> None:
    api = _api()
    api[RUNS_PATH]["workflow_runs"] = [_run(7, PR_HEAD, OTHER_TREE)]
    decision = _decide(FakeAPI(api))
    assert decision.skip is False
    assert "no completed pull_request run" in decision.reason


def test_no_pr_runs_at_all_runs() -> None:
    api = _api()
    api[RUNS_PATH] = {"total_count": 0, "workflow_runs": []}
    decision = _decide(FakeAPI(api))
    assert decision.skip is False
    assert "no completed pull_request run" in decision.reason


def test_only_an_older_green_run_on_a_different_tree_runs() -> None:
    """The newest PR run tested this tree and failed; the only green one tested something else."""
    api = _api()
    api[RUNS_PATH]["workflow_runs"] = [
        _run(8, PR_HEAD, TREE, conclusion="failure"),
        _run(7, OLDER_PR_HEAD, OTHER_TREE),
    ]
    decision = _decide(FakeAPI(api))
    assert decision.skip is False
    assert "concluded [(" in decision.reason and "'failure')]" in decision.reason


def test_a_failed_pr_run_on_the_same_tree_runs_even_beside_a_green_one() -> None:
    """Conflicting evidence about the identical tree is doubt, and doubt runs the tests."""
    api = _api()
    api[RUNS_PATH]["workflow_runs"] = [
        _run(7, PR_HEAD, TREE),
        _run(6, OLDER_PR_HEAD, TREE, "failure"),
    ]
    decision = _decide(FakeAPI(api))
    assert decision.skip is False
    assert "concluded [(" in decision.reason and "'failure')]" in decision.reason


def test_a_cancelled_pr_run_on_the_same_tree_does_not_block_a_green_one() -> None:
    api = _api()
    api[RUNS_PATH]["workflow_runs"] = [
        _run(7, PR_HEAD, TREE),
        _run(6, OLDER_PR_HEAD, TREE, "cancelled"),
    ]
    decision = _decide(FakeAPI(api))
    assert decision.skip is True, decision.reason


def test_the_newest_green_run_on_the_tree_is_the_one_checked() -> None:
    api = _api()
    api[RUNS_PATH]["workflow_runs"] = [_run(6, OLDER_PR_HEAD, TREE), _run(7, PR_HEAD, TREE)]
    api[compare_path(OLDER_PR_HEAD)] = {"status": "ahead"}
    api[pulls_path(OLDER_PR_HEAD)] = [_pull(479)]
    api[events_path(479)] = _events()
    api[jobs_path(6)] = {"total_count": 0, "jobs": []}
    decision = _decide(FakeAPI(api))
    assert decision.skip is True, decision.reason
    assert "run 7 " in decision.reason


@pytest.mark.parametrize("status", ["behind", "diverged"])
def test_a_pr_head_that_does_not_descend_from_the_pushs_parent_runs(status: str) -> None:
    """A PR run tests the MERGE of its head into the base as it then was, not the head itself.

    Only when the head already contains the push's parent (and so the base the PR run merged with)
    was the tree it tested the head's own tree.
    """
    api = _api()
    api[compare_path(PR_HEAD)] = {"status": status}
    decision = _decide(FakeAPI(api))
    assert decision.skip is False
    assert f"is {status} of the push's parent" in decision.reason


@pytest.mark.parametrize(
    ("pulls", "problem"),
    [
        # Its run tested the merge into THAT branch, not the pushed tree.
        ([_pull(480, base="release")], "480 targets owner/repo:release"),
        ([_pull(480), _pull(481, base="exec-t229")], "481 targets owner/repo:exec-t229"),
        ([_pull(480, base_repo="other/repo")], "480 targets other/repo:main"),
        ([_pull(480, head_repo="fork/repo")], "480 comes from fork/repo"),
        ([_pull(480, head_repo=None)], "could not decide"),
        ([], "no pull request is associated with"),
        ([_pull(n) for n in range(100)], "100 pull requests"),
        ({"message": "Not Found"}, "could not decide"),
    ],
)
def test_a_pr_run_not_established_as_a_same_repo_pr_into_this_branch_runs(
    pulls: Any, problem: str
) -> None:
    api = _api()
    api[pulls_path(PR_HEAD)] = pulls
    decision = _decide(FakeAPI(api))
    assert decision.skip is False
    assert problem in decision.reason


@pytest.mark.parametrize(
    "kind", ["base_ref_changed", "automatic_base_change_succeeded", "automatic_base_change_failed"]
)
def test_a_pr_whose_base_ever_changed_runs(kind: str) -> None:
    """Its CURRENT base is main, but its run may have tested the merge into the old base.

    A retarget is an `edited` event, which does not start a `pull_request` run.
    """
    api = _api()
    api[events_path(480)] = _events("labeled", kind, "reopened")
    decision = _decide(FakeAPI(api))
    assert decision.skip is False
    assert f"#480's base changed ({kind})" in decision.reason


def test_a_retarget_on_the_second_of_two_prs_runs() -> None:
    api = _api()
    api[pulls_path(PR_HEAD)] = [_pull(480), _pull(481)]
    api[events_path(481)] = _events("base_ref_changed")
    decision = _decide(FakeAPI(api))
    assert decision.skip is False
    assert "#481's base changed (base_ref_changed)" in decision.reason


def test_a_possibly_truncated_event_list_runs() -> None:
    api = _api()
    api[events_path(480)] = [{"id": i, "event": "labeled"} for i in range(100)]
    decision = _decide(FakeAPI(api))
    assert decision.skip is False
    assert "#480 has 100 events; the list may be truncated" in decision.reason


def test_an_event_list_of_the_wrong_shape_runs() -> None:
    api = _api()
    # An empty object, not an empty list: iterating it would find no base change.
    api[events_path(480)] = {}
    decision = _decide(FakeAPI(api))
    assert decision.skip is False
    assert "could not decide" in decision.reason


def test_a_push_commit_without_a_parent_runs() -> None:
    api = _api()
    api[COMMIT_PATH]["parents"] = []
    decision = _decide(FakeAPI(api))
    assert decision.skip is False
    assert "has no parent" in decision.reason


def test_a_run_whose_event_is_not_pull_request_is_not_evidence() -> None:
    api = _api()
    api[RUNS_PATH]["workflow_runs"][0]["event"] = "push"
    decision = _decide(FakeAPI(api))
    assert decision.skip is False
    assert "no completed pull_request run" in decision.reason


@pytest.mark.parametrize(
    "path",
    [
        COMMIT_PATH,
        RUNS_PATH,
        compare_path(PR_HEAD),
        pulls_path(PR_HEAD),
        events_path(480),
        jobs_path(7),
    ],
)
def test_an_api_failure_at_any_call_runs(path: str) -> None:
    decision = _decide(FakeAPI(_api(), fail=frozenset({path})))
    assert decision.skip is False
    assert "HTTP 502" in decision.reason


def test_an_unexpected_response_shape_runs() -> None:
    api = _api()
    del api[RUNS_PATH]["workflow_runs"][0]["head_commit"]
    decision = _decide(FakeAPI(api))
    assert decision.skip is False
    assert "KeyError: 'head_commit'" in decision.reason


# --------------------------------------------------------------------------------------
# The command line the workflow runs
# --------------------------------------------------------------------------------------


def _argv(event: str = "push") -> list[str]:
    return [
        "--event", event, "--repo", REPO, "--sha", PUSH_SHA, "--workflow", WORKFLOW, "--branch", "main",
        "--pythons", " ".join(PYTHONS), "--shards", str(SHARDS),
    ]  # fmt: skip


def test_main_prints_true_only_for_the_skip_case(capsys: pytest.CaptureFixture[str]) -> None:
    assert ci_skip.main(_argv(), fetch=FakeAPI(_api())) == 0
    assert capsys.readouterr().out == "true\n"


def test_main_prints_false_when_the_api_fails(capsys: pytest.CaptureFixture[str]) -> None:
    assert ci_skip.main(_argv(), fetch=FakeAPI(_api(), fail=frozenset({RUNS_PATH}))) == 0
    captured = capsys.readouterr()
    assert captured.out == "false\n"
    assert "HTTP 502" in captured.err


def test_main_prints_false_when_gh_itself_cannot_run(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The real fetcher, with no `gh` on PATH: the failure must read as "run", never as a crash."""
    monkeypatch.setenv("PATH", str(tmp_path))
    assert ci_skip.main(_argv()) == 0
    assert capsys.readouterr().out == "false\n"


# --------------------------------------------------------------------------------------
# The job names the decision looks for are the names ci.yml gives its jobs
# --------------------------------------------------------------------------------------

CI_YML = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"


def test_the_expected_shard_names_are_what_ci_yml_renders() -> None:
    """If ci.yml renames a job, no PR run would ever match and the skip would silently die.

    Rendered from the workflow's own `name:` template, so a rename fails here instead.
    """
    jobs = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))["jobs"]
    template = jobs["test-ubuntu"]["name"]
    rendered = frozenset(
        template.replace("${{ matrix.python }}", p)
        .replace("${{ matrix.shard }}", str(i))
        .replace("${{ needs.plan.outputs.shards }}", str(SHARDS))
        for p in PYTHONS
        for i in range(1, SHARDS + 1)
    )
    assert rendered == shard_job_names(PYTHONS, SHARDS)
    assert "${{" not in "".join(rendered)
    for job_id in ci_skip.GATE_JOBS:
        assert jobs[job_id]["name"] == job_id
