from pathlib import Path

import pytest

from boardwatch.core.features import (
    FEATURE_BY_KEY,
    FEATURES,
    SETTABLE_FEATURE_KEYS,
    feature_state,
    unmet_prerequisites,
)
from boardwatch.core.secrets import LLM_API_KEY_ENV
from boardwatch.core.settings import LLMTier, NotifyTier, Settings
from boardwatch.notify.webhook import WEBHOOK_URL_ENV


def _settings(tmp_path: Path, *, llm: LLMTier | None = None, notify: NotifyTier | None = None) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "cfg",
        llm=llm or LLMTier(),
        notify=notify or NotifyTier(),
    )


def test_settable_keys_are_the_six_feature_keys() -> None:
    assert SETTABLE_FEATURE_KEYS == {
        "llm.enabled",
        "llm.eligibility_extraction",
        "llm.resume_tailoring",
        "llm.resume_tailoring_via_agent",
        "notify.desktop_enabled",
        "notify.webhook_enabled",
    }
    assert set(FEATURE_BY_KEY) == SETTABLE_FEATURE_KEYS
    assert len(FEATURES) == 6


def test_feature_state_reads_typed_values(tmp_path: Path) -> None:
    s = _settings(tmp_path, notify=NotifyTier(desktop_enabled=True))
    assert feature_state(FEATURE_BY_KEY["notify.desktop_enabled"], s) is True
    assert feature_state(FEATURE_BY_KEY["notify.webhook_enabled"], s) is False


def test_agent_tier_b_has_no_prerequisites(tmp_path: Path) -> None:
    # B1: the agent lane does NOT require llm.enabled or an API key.
    agent = FEATURE_BY_KEY["llm.resume_tailoring_via_agent"]
    assert agent.requires == ()
    s = _settings(tmp_path, llm=LLMTier(enabled=False, resume_tailoring_via_agent=True))
    assert unmet_prerequisites(agent, s) == []


def test_api_lane_prereqs_reported_when_unmet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(LLM_API_KEY_ENV, raising=False)
    feat = FEATURE_BY_KEY["llm.resume_tailoring"]
    s = _settings(tmp_path, llm=LLMTier(enabled=False, model=None))
    unmet = unmet_prerequisites(feat, s)
    assert "llm.enabled on" in unmet
    assert f"{LLM_API_KEY_ENV} set" in unmet
    assert "llm.model in config.toml" in unmet


def test_api_lane_prereqs_all_met(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(LLM_API_KEY_ENV, "k")
    feat = FEATURE_BY_KEY["llm.eligibility_extraction"]
    s = _settings(tmp_path, llm=LLMTier(enabled=True, model="claude-x"))
    assert unmet_prerequisites(feat, s) == []


def test_webhook_prereq_tracks_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(WEBHOOK_URL_ENV, raising=False)
    feat = FEATURE_BY_KEY["notify.webhook_enabled"]
    assert unmet_prerequisites(feat, _settings(tmp_path)) == [f"{WEBHOOK_URL_ENV} set"]


def test_agent_lane_sends_discloses_anthropic() -> None:
    # B3: the agent-lane copy must disclose that bullets + posting go to Claude Code -> Anthropic.
    sends = FEATURE_BY_KEY["llm.resume_tailoring_via_agent"].sends
    assert "Anthropic" in sends
