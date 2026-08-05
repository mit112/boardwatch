from pathlib import Path

import pytest
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.core.secrets import LLM_API_KEY_ENV
from boardwatch.notify.webhook import WEBHOOK_URL_ENV

runner = CliRunner()


@pytest.fixture()
def cfg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path))
    return tmp_path


def _base(cfg: Path) -> list[str]:
    return ["--data-dir", str(cfg / "data")]


def test_settings_lists_features_and_always_on_block(cfg: Path) -> None:
    result = runner.invoke(app, [*_base(cfg), "settings"])
    assert result.exit_code == 0
    assert "Always on" in result.output and "Scanning boards" in result.output
    assert "LLM API tier" in result.output
    assert "Resume tailoring, agent" in result.output
    assert "boardwatch config" in result.output  # pointer to numeric tuning


def test_settings_shows_secret_status_never_value(
    cfg: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    canary = "CANARY-SETTINGS-SECRET"
    monkeypatch.setenv(LLM_API_KEY_ENV, canary)
    result = runner.invoke(app, [*_base(cfg), "settings"])
    assert result.exit_code == 0
    assert f"{LLM_API_KEY_ENV}: set" in result.output
    assert f"{WEBHOOK_URL_ENV}: unset" in result.output
    assert canary not in result.output


def test_settings_notes_unmet_prereq_for_enabled_feature(
    cfg: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(LLM_API_KEY_ENV, raising=False)
    (cfg / "config.toml").write_text("[llm]\nresume_tailoring = true\n", encoding="utf-8")
    result = runner.invoke(app, [*_base(cfg), "settings"])
    assert result.exit_code == 0
    assert "needs" in result.output and LLM_API_KEY_ENV in result.output


def test_settings_graceful_on_malformed_config(cfg: Path) -> None:
    (cfg / "config.toml").write_text("per_host_delay_seconds = 0.1\n", encoding="utf-8")  # < floor
    result = runner.invoke(app, [*_base(cfg), "settings"])
    assert result.exit_code == 1
    assert "per_host_delay_seconds" in result.output  # names the offending key
    assert "Traceback" not in result.output


def test_settings_creates_no_db(cfg: Path) -> None:
    runner.invoke(app, [*_base(cfg), "settings"])
    assert not (cfg / "data" / "boardwatch.db").exists()
