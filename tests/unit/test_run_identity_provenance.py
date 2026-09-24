"""T137 — identity drift and execution provenance, the pure half and the git read.

The end-to-end half (`tests/pipeline/test_run_identity_drift.py`) shows the pipeline wires them;
this pins what each renders and how the code provenance behaves against real git checkouts.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from boardwatch.pipeline import funnel_writer
from boardwatch.pipeline.funnel_writer import code_provenance
from boardwatch.reports.run_funnel import (
    CodeProvenance,
    ExecutionProvenance,
    RunIdentity,
    funnel_to_dict,
    funnel_to_markdown,
    identity_drift,
)
from tests.unit.test_run_funnel import funnel

_START = RunIdentity(
    code_fingerprint="engine-1+abc",
    config_hash="c0ffee",
    profile_facts_hash="pf00",
    profile_row_hash="pr00",
    rules_hash="ru1e5",
    routing_hash="r0ute",
)

_PROVENANCE = ExecutionProvenance(
    code=CodeProvenance(commit="0123abcd" * 5, dirty=True),
    gate_engine_version="final_gate:p1:q2",
    gate_model="sonnet",
    gate_effort=None,
    lanes=("linkedin", "indeed"),
    watched_companies=12,
    boards_attempted=11,
    skip_scan=False,
    project=True,
    liveness_prober=True,
    top_n=10,
)


def _manifest_section(markdown: str) -> str:
    return markdown.split("## Manifest", 1)[1].split("\n## ", 1)[0]


# --- the drift field -------------------------------------------------------------------------


def test_drift_names_each_moved_field_in_field_order_and_nothing_else() -> None:
    assert identity_drift(_START, _START) == ()
    assert identity_drift(_START, replace(_START, rules_hash="ru1e6")) == ("rules_hash",)
    moved = replace(_START, routing_hash="other", config_hash="other")
    assert identity_drift(_START, moved) == ("config_hash", "routing_hash")
    # A profile appearing or vanishing mid-run is a move too, not a skipped comparison.
    assert identity_drift(_START, replace(_START, profile_facts_hash=None)) == (
        "profile_facts_hash",
    )


def test_the_three_drift_states_publish_three_different_things() -> None:
    """`null` NOT MEASURED, `[]` measured and stable, a list of names when it moved — and only the
    moved state says DRIFTED. A stable run's manifest section gains nothing at all."""
    unmeasured = funnel()
    stable = replace(unmeasured, identity_drift=())
    drifted = replace(unmeasured, identity_drift=("profile_row_hash", "rules_hash"))

    assert funnel_to_dict(unmeasured)["identity_drift"] is None
    assert funnel_to_dict(stable)["identity_drift"] == []
    assert funnel_to_dict(drifted)["identity_drift"] == ["profile_row_hash", "rules_hash"]

    assert "NOT MEASURED" in _manifest_section(funnel_to_markdown(unmeasured))
    assert "drift" not in _manifest_section(funnel_to_markdown(stable)).lower()
    moved = _manifest_section(funnel_to_markdown(drifted))
    assert "DRIFTED" in moved and "`profile_row_hash`, `rules_hash`" in moved


def test_drift_is_published_beside_the_manifest_not_inside_it() -> None:
    """The manifest publishes exactly what it did before T137, plus T204's `target_countries`."""
    payload = funnel_to_dict(replace(funnel(), identity_drift=("rules_hash",)))

    assert set(payload["manifest"]) == {  # type: ignore[arg-type]
        "code_fingerprint", "config_hash", "profile_facts_hash", "profile_row_hash",
        "rules_hash", "status", "location_filter_mode", "routing_hash",
    "target_countries",
    }


# --- the provenance block -----------------------------------------------------------------


def test_provenance_publishes_every_block_and_names_an_unrecorded_one() -> None:
    recorded = replace(funnel(), provenance=_PROVENANCE)

    assert funnel_to_dict(recorded)["provenance"] == {
        "code": {"commit": "0123abcd" * 5, "dirty": True},
        "gate": {"engine_version": "final_gate:p1:q2", "model": "sonnet", "effort": None},
        "lanes": ["linkedin", "indeed"],
        "fleet": {"watched_companies": 12, "boards_attempted": 11},
        "flags": {"skip_scan": False, "project": True, "liveness_prober": True, "top_n": 10},
    }
    body = funnel_to_markdown(recorded)
    assert "## Execution provenance" in body
    assert f"| code | {'0123abcd' * 5} (dirty tree) |" in body
    assert "| lanes | linkedin, indeed |" in body

    assert funnel_to_dict(funnel())["provenance"] is None
    assert "not recorded" in funnel_to_markdown(funnel()).split("## Execution provenance", 1)[1]


def test_a_missing_commit_is_published_as_null_not_as_a_guess() -> None:
    payload = funnel_to_dict(replace(funnel(), provenance=replace(_PROVENANCE, code=None)))

    assert payload["provenance"]["code"] is None  # type: ignore[index]


# --- code provenance against real git ----------------------------------------------------


@pytest.fixture()
def clean_git(monkeypatch: pytest.MonkeyPatch) -> None:
    """No global or system git config — no signing, no hooks — so a scratch repo behaves the same
    on every machine and CI runner."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=root, capture_output=True, text=True, check=True,
    ).stdout


def _checkout(root: Path, package: str = "pkg") -> Path:
    """A repository with a tracked package directory, committed clean."""
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    (root / package).mkdir(parents=True)
    (root / package / "__init__.py").write_text("x = 1\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    return root / package


def test_a_checkout_reports_its_commit_and_whether_the_tree_is_dirty(
    tmp_path: Path, clean_git: None
) -> None:
    package = _checkout(tmp_path / "repo")
    head = _git(tmp_path / "repo", "log", "-1", "--format=%H").strip()

    assert code_provenance(package) == CodeProvenance(commit=head, dirty=False)
    (tmp_path / "repo" / "untracked.py").write_text("", encoding="utf-8")
    assert code_provenance(package) == CodeProvenance(commit=head, dirty=True)


def test_a_directory_in_no_checkout_is_none(tmp_path: Path, clean_git: None) -> None:
    (tmp_path / "__init__.py").write_text("", encoding="utf-8")

    assert code_provenance(tmp_path) is None


def test_a_package_installed_inside_an_ignored_directory_is_not_that_checkout_s_code(
    tmp_path: Path, clean_git: None
) -> None:
    """A wheel in a virtualenv that lives inside a checkout: git answers `rev-parse HEAD` there
    with the ENCLOSING checkout's commit, which names code that did not run."""
    repo = tmp_path / "repo"
    _checkout(repo)
    (repo / ".gitignore").write_text(".venv/\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "ignore the venv")
    installed = repo / ".venv" / "lib" / "site-packages" / "pkg"
    installed.mkdir(parents=True)
    (installed / "__init__.py").write_text("x = 1\n", encoding="utf-8")
    assert _git(installed, "rev-parse", "HEAD").strip(), "guard: git DOES answer from in here"

    assert code_provenance(installed) is None


def test_the_dirty_check_never_rewrites_the_checkout_s_index(
    tmp_path: Path, clean_git: None
) -> None:
    """This runs unattended against the owner's own checkout. A plain `git status` refreshes a
    stat-dirty index and REWRITES it under `index.lock`, which a concurrent commit there would
    meet and a killed run could leave behind."""
    package = _checkout(tmp_path / "repo")
    index = tmp_path / "repo" / ".git" / "index"
    stat = (package / "__init__.py").stat()
    # Same content, new mtime: exactly what a refresh would write back.
    os.utime(package / "__init__.py", (stat.st_atime + 60, stat.st_mtime + 60))
    before = index.read_bytes()

    assert code_provenance(package) is not None

    assert index.read_bytes() == before


def test_git_missing_from_path_is_none(
    tmp_path: Path, clean_git: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _checkout(tmp_path / "repo")
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))

    assert code_provenance(package) is None


def test_a_git_that_hangs_is_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def hang(*_a: Any, **kwargs: Any) -> Any:
        raise subprocess.TimeoutExpired(cmd=["git"], timeout=kwargs["timeout"])

    monkeypatch.setattr(funnel_writer.subprocess, "run", hang)

    assert code_provenance(tmp_path) is None
