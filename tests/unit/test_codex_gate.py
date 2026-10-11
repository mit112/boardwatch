"""Codex must judge the same isolated payload and preserve the gate's fail-open boundary."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from boardwatch.core.settings import GateTier, Settings
from boardwatch.llm import gate_judge

VERDICT = {"label": "1", "decision": "eligible", "reason": None, "evidence": "",
           "confidence": "high", "seniority_fit": "yes"}
BATCH: list[dict[str, object]] = [
    {"label": "1", "facts": {}, "jd_text": "New graduate software engineer.", "hint": "hidden"}
]


def _events(*extra: dict[str, object]) -> str:
    return "\n".join(json.dumps(e) for e in [
        {"type": "thread.started", "thread_id": "test"},
        {"type": "turn.started"},
        *extra,
        {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps([VERDICT])}},
        {"type": "turn.completed", "usage": {}},
    ])


def _settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path / "data", config_dir=tmp_path / "config",
                    gate=GateTier(enabled=True, model="codex:gpt-6.1-sol", effort="high"))


def test_codex_dispatch_is_isolated_and_reuses_the_verdict_parser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert argv[:2] == ["codex", "exec"]
        assert argv[argv.index("--model") + 1] == "gpt-6.1-sol"
        assert {"--ignore-user-config", "--ignore-rules", "--ephemeral",
                "--skip-git-repo-check", "--json"} <= set(argv)
        assert argv[argv.index("--sandbox") + 1] == "read-only"
        assert 'model_reasoning_effort="high"' in argv
        assert 'forced_login_method="chatgpt"' in argv
        assert "features.shell_tool=false" in argv
        assert "features.plugins=false" in argv
        assert "features.apps=false" in argv
        assert "features.hooks=false" in argv
        assert "project_doc_max_bytes=0" in argv
        assert "skills.include_instructions=false" in argv
        cwd = Path(str(kwargs["cwd"]))
        assert cwd != Path.cwd()
        assert not (cwd / "AGENTS.md").exists()
        prompt = str(kwargs["input"])
        assert "New graduate software engineer." in prompt
        assert "hidden" not in prompt
        assert kwargs["timeout"] == 300
        assert kwargs["check"] is True
        return subprocess.CompletedProcess(argv, 0, _events(), "")

    monkeypatch.setattr(subprocess, "run", run)
    verdicts, note, seniority = gate_judge._judge_batch(BATCH, "policy", _settings(tmp_path))
    assert verdicts is not None and [v.label for v in verdicts] == ["1"]
    assert note is None
    assert verdicts[0].seniority_fit == "yes"
    assert seniority == ("answered",)


@pytest.mark.parametrize("stdout", [
    "not JSON", _events({"type": "item.started", "item": {"type": "command_execution"}}),
    _events({"type": "turn.failed", "error": {"message": "failed"}}),
    _events({"type": "item.completed", "item": {"type": "error", "message": "failed"}}),
    _events().replace('"turn.completed"', '"turn.unfinished"'),
])
def test_codex_malformed_incomplete_or_tool_using_calls_fail_open(
    stdout: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        a[0], 0, stdout, ""))
    verdicts, note, seniority = gate_judge._judge_batch(BATCH, "policy", _settings(tmp_path))
    assert verdicts is None
    assert note is not None and "response" in note
    assert seniority == ()


@pytest.mark.parametrize("exc", [FileNotFoundError(),
    subprocess.TimeoutExpired("codex", 300),
    subprocess.CalledProcessError(1, "codex", stderr="access denied"),
    PermissionError(13, "denied"),
])
def test_codex_process_failures_name_codex_and_fail_open(
    exc: Exception, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise exc
    monkeypatch.setattr(subprocess, "run", run)
    verdicts, note, seniority = gate_judge._judge_batch(BATCH, "policy", _settings(tmp_path))
    assert verdicts is None
    assert note is not None and "codex" in note and "claude" not in note
    assert seniority == ()
