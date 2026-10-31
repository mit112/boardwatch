"""D-656: tail costs reach the log and summary, but never rewrite the funnel."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console

from boardwatch.cli import run_cmd
from boardwatch.core.settings import load_settings
from boardwatch.pipeline import runner
from boardwatch.store.db import get_engine
from tests.pipeline.test_pipeline_run import _cli, _ready


@pytest.mark.parametrize("failure", [None, "queue_sync", "funnel", "morning"])
def test_tail_boundaries_charge_the_work_before_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str | None
) -> None:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    data_dir = tmp_path / "data"
    _ready(data_dir)
    settings = load_settings(data_dir=data_dir)
    elapsed = 0.0
    epoch = datetime(2026, 10, 30, 4)
    costs = {
        "form_sweep": 1.0,
        "funnel": 2.0,
        "queue_sync": 4.0,
        "soft_detectors": 8.0,
        "morning": 16.0,
        "heartbeat": 32.0,
        "escalation": 64.0,
    }
    calls: list[str] = []
    artifacts: dict[Path, bytes] = {}

    def charged(name, operation):
        def call(*args, **kwargs):
            nonlocal elapsed
            calls.append(name)
            elapsed += costs[name]
            if name == failure:
                raise RuntimeError(f"injected {name} failure")
            result = operation(*args, **kwargs)
            if name == "funnel":
                for path in (result.json_path, result.markdown_path):
                    artifacts[path] = path.read_bytes()
            return result

        return call

    monkeypatch.setattr(runner, "perf_counter", lambda: elapsed)
    monkeypatch.setattr(runner, "utcnow", lambda: epoch + timedelta(seconds=elapsed))
    for name, attribute in (
        ("form_sweep", "_sweep_form_questions"),
        ("funnel", "_emit_funnel"),
        ("queue_sync", "_sync_queue"),
        ("soft_detectors", "check_intake_death"),
        ("morning", "_emit_morning"),
    ):
        monkeypatch.setattr(runner, attribute, charged(name, getattr(runner, attribute)))
    monkeypatch.setattr(runner, "send_heartbeat", charged("heartbeat", lambda: None))
    monkeypatch.setattr(runner, "escalate_alerts", charged("escalation", lambda *_: None))
    output = StringIO()

    summary = runner.run_pipeline(
        get_engine(data_dir), settings, console=Console(file=output, width=200),
        out_root=tmp_path / "apps", resume_path=settings.config_dir / "resume.yaml",
        skip_scan=True, queue_root=tmp_path / "queue",
    )

    assert summary.fatal is None
    expected_costs = costs.copy()
    if failure in {"funnel", "morning"}:
        expected_costs["heartbeat"] = 0.0
    assert calls == [name for name in costs if name != "heartbeat" or expected_costs[name]]
    actual = {stage.name: stage.seconds for stage in summary.stage_durations[-7:]}
    assert actual == expected_costs, "tail durations must include each operation's own cost"
    cumulative = 0.0
    lines = output.getvalue().splitlines()
    timing_lines = [line.strip() for line in lines if line.strip().startswith("tail ")]
    expected_lines = []
    for name, seconds in expected_costs.items():
        cumulative += seconds
        end = epoch + timedelta(seconds=cumulative)
        expected_lines.append(f"tail {name} → {end.isoformat()} UTC · {seconds:.3f}s")
    assert timing_lines == expected_lines
    assert bool(artifacts) == (failure != "funnel")
    for path, original in artifacts.items():
        assert path.read_bytes() == original, "the funnel was republished after the tail"
        if path.suffix == ".json":
            payload = json.loads(original)
            assert payload["stage_durations"] == [
                {"name": stage.name, "seconds": round(stage.seconds, 3)}
                for stage in summary.stage_durations[:-7]
            ], "D-343: the funnel keeps the pre-tail snapshot"
    if failure:
        assert any(f"injected {failure} failure" in error for error in summary.errors)


@pytest.mark.parametrize("fatal", [None, "injected fatal"], ids=["clean", "fatal"])
def test_command_end_is_timestamped_after_the_summary_and_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fatal: str | None
) -> None:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    end = datetime(2026, 10, 30, 6, 7, 8)
    summary = runner.PipelineSummary(run_id=123, errors=["injected warning"], fatal=fatal)
    monkeypatch.setattr(run_cmd, "run_pipeline", lambda *a, **kw: summary)
    # Patching the shared clock also works before run_cmd imports utcnow.
    monkeypatch.setattr("boardwatch.core.clock.utcnow", lambda: end)
    if hasattr(run_cmd, "utcnow"):
        monkeypatch.setattr(run_cmd, "utcnow", lambda: end)

    result = _cli(tmp_path / "data", [
        "run", "--no-scan", "--no-check-liveness", "--out", str(tmp_path / "apps"),
        "--queue-root", str(tmp_path / "queue"),
    ])

    assert result.exit_code == (1 if fatal else 0), result.output
    assert "! injected warning" in result.output
    assert result.output.splitlines()[-1] == "run 123 command end → 2026-10-30T06:07:08 UTC"
