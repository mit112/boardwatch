"""`docs/configuration.md` names every key `boardwatch config show` prints.

The reference is a hand-kept mirror of `Settings`, and it drifted: by 0.6.0 it named 30 of the 57
keys `config show` printed, and said `[gate]` had five keys when it had ten. The key list here is
read from the command itself rather than from a second copy, so a setting added without its
documentation fails this test instead of reaching users undocumented.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from boardwatch.cli.app import app

DOC = Path(__file__).resolve().parents[2] / "docs" / "configuration.md"

#: `config show` prints these two as set/unset. They are environment variables, never
#: `config.toml` keys, so the reference documents them by the variable's name.
SECRET_KEYS = {
    "llm.api_key": "BOARDWATCH_LLM_API_KEY",
    "notify.webhook_url": "BOARDWATCH_NOTIFY_WEBHOOK_URL",
}


def test_every_key_config_show_prints_is_documented(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    result = CliRunner().invoke(
        app, ["--data-dir", str(tmp_path / "data"), "config", "show", "--json"]
    )
    assert result.exit_code == 0, result.output
    keys = set(json.loads(result.stdout))
    assert "per_host_delay_seconds" in keys and "gate.enabled" in keys, sorted(keys)

    doc = DOC.read_text(encoding="utf-8")
    missing = sorted(key for key in keys if f"`{SECRET_KEYS.get(key, key)}`" not in doc)
    assert missing == [], f"docs/configuration.md does not document: {missing}"
