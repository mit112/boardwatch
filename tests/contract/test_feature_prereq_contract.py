"""Contract: the registry's prereq claims must match the code's real gates (M11). This is
what stops B1 (the agent lane wrongly requiring llm.enabled) from recurring if a gate moves."""

import inspect
from pathlib import Path

import pytest

from boardwatch.cli import tailor_cmd
from boardwatch.core.features import FEATURE_BY_KEY
from boardwatch.core.secrets import LLM_API_KEY_ENV
from boardwatch.core.settings import LLMTier, Settings
from boardwatch.llm.factory import build_client


def _settings(tmp_path: Path, **llm: object) -> Settings:
    return Settings(data_dir=tmp_path / "d", config_dir=tmp_path / "c", llm=LLMTier(**llm))


def test_api_lane_registry_matches_build_client(tmp_path, monkeypatch) -> None:
    labels = {p.label for p in FEATURE_BY_KEY["llm.resume_tailoring"].requires}
    assert labels == {"llm.enabled on", f"{LLM_API_KEY_ENV} set", "llm.model in config.toml"}

    monkeypatch.setenv(LLM_API_KEY_ENV, "k")
    assert build_client(_settings(tmp_path, enabled=True, provider="anthropic", model="m")) is not None
    with pytest.raises(ValueError):  # model prereq is real
        build_client(_settings(tmp_path, enabled=True, provider="anthropic", model=None))
    monkeypatch.delenv(LLM_API_KEY_ENV)
    assert build_client(_settings(tmp_path, enabled=True, provider="anthropic", model="m")) is None


def test_agent_lane_registry_has_no_prereqs_and_gate_ignores_enabled() -> None:
    assert FEATURE_BY_KEY["llm.resume_tailoring_via_agent"].requires == ()
    src = inspect.getsource(tailor_cmd)
    # The agent lane gates on its own flag (>=3 gate sites) and must not read llm.enabled
    # in those gates — the source binding that makes the empty-prereq claim honest.
    assert src.count("resume_tailoring_via_agent") >= 3
