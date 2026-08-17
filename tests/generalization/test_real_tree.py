"""The gate, end to end, against the actual repository."""

from __future__ import annotations

import inspect
import subprocess
import sys
from pathlib import Path

from pytest import CaptureFixture, MonkeyPatch

from tools.generalization import __main__ as entry
from tools.generalization import defaults, fixtures, inventory, packaging, shape
from tools.generalization.__main__ import ALL_RULES, main, run
from tools.generalization.discovery import Repo
from tools.generalization.model import Rule, Violation

REPO_ROOT = Path(__file__).resolve().parents[2]

EXPECTED_RULES = (
    "check_shapes",
    "check_artifact_files",
    "check_inventory",
    "check_registry_invariants",
    "check_collection_defaults",
    "check_defaults_snapshot",
    "check_init_prompts",
    "check_wheel_completeness",
    "check_fixture_coverage",
    "check_fixture_pins",
    "check_fixture_review_due",
)


def test_every_rule_function_is_registered() -> None:
    """Eleven named functions cover the fifteen rules R1 through R15, in spec order."""
    assert tuple(rule.__name__ for rule in ALL_RULES) == EXPECTED_RULES


def test_no_rule_function_is_left_unregistered() -> None:
    """A check_ function that exists but is not in ALL_RULES never runs at all."""
    defined = {
        name
        for module in (shape, inventory, defaults, packaging, fixtures)
        for name, value in vars(module).items()
        if name.startswith("check_")
        and inspect.isfunction(value)
        and value.__module__ == module.__name__
    }
    assert defined == set(EXPECTED_RULES)


def test_run_calls_every_registered_rule(monkeypatch: MonkeyPatch) -> None:
    """A run loop that skips rules would otherwise report every tree clean."""
    called: list[str] = []

    def spy(name: str) -> Rule:
        def rule(repo: Repo) -> list[Violation]:
            called.append(name)
            return []

        return rule

    monkeypatch.setattr(entry, "ALL_RULES", tuple(spy(f"r{index}") for index in range(3)))
    assert run(REPO_ROOT) == []
    assert called == ["r0", "r1", "r2"]


def test_the_real_tree_is_clean() -> None:
    violations = run(REPO_ROOT)
    assert violations == [], "\n".join(v.render() for v in violations)


def test_main_returns_zero_on_the_real_tree(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.chdir(REPO_ROOT)
    assert main() == 0


def test_main_returns_one_when_a_rule_reports(monkeypatch: MonkeyPatch) -> None:
    def dirty(repo: Repo) -> list[Violation]:
        return [Violation("R1", "docs/example.md", 3, "synthetic")]

    monkeypatch.setattr(entry, "ALL_RULES", (dirty,))
    monkeypatch.chdir(REPO_ROOT)
    assert main() == 1


def test_main_returns_two_when_a_rule_raises(monkeypatch: MonkeyPatch) -> None:
    def broken(repo: Repo) -> list[Violation]:
        raise RuntimeError("rule blew up")

    monkeypatch.setattr(entry, "ALL_RULES", (broken,))
    monkeypatch.chdir(REPO_ROOT)
    assert main() == 2


def test_main_returns_two_when_discovery_fails(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main() == 2


def test_the_report_sorts_r2_before_r10(monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]) -> None:
    """Plain string order puts 'R10' before 'R2', which is unreadable in an 11-rule report."""

    def noisy(repo: Repo) -> list[Violation]:
        return [
            Violation("R10", "a.py", 5, "synthetic"),
            Violation("R2", "b.py", None, "synthetic"),
        ]

    monkeypatch.setattr(entry, "ALL_RULES", (noisy,))
    monkeypatch.chdir(REPO_ROOT)
    assert main() == 1
    reported = capsys.readouterr().err
    assert reported.index("[R2]") < reported.index("[R10]")


def test_module_entry_point_exits_zero() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "tools.generalization"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "generalization: OK" in proc.stdout
