import pytest

from boardwatch.core.secrets import LLM_API_KEY_ENV, resolve_secret


def test_returns_value_from_injected_env() -> None:
    assert resolve_secret("X", env={"X": "sekret"}) == "sekret"


def test_absent_var_returns_none() -> None:
    assert resolve_secret("X", env={}) is None


def test_blank_and_whitespace_values_are_unset() -> None:
    assert resolve_secret("X", env={"X": ""}) is None
    assert resolve_secret("X", env={"X": "   "}) is None


def test_value_is_stripped() -> None:
    assert resolve_secret("X", env={"X": "  sekret  "}) == "sekret"


def test_reads_os_environ_at_call_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(LLM_API_KEY_ENV, raising=False)
    assert resolve_secret(LLM_API_KEY_ENV) is None
    monkeypatch.setenv(LLM_API_KEY_ENV, "live-value")
    assert resolve_secret(LLM_API_KEY_ENV) == "live-value"
