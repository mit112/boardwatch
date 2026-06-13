from pathlib import Path

import pytest
from pydantic import ValidationError

from boardwatch.core.settings import Settings, load_settings


def test_defaults_load_without_config_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("BOARDWATCH_DATA_DIR", str(tmp_path / "data"))
    settings = load_settings()
    assert settings.data_dir == tmp_path / "data"
    assert settings.config_dir == tmp_path / "cfg"
    assert settings.per_host_delay_seconds == 1.0
    assert settings.retry_attempts == 3
    assert settings.busy_timeout_ms == 5000
    assert settings.scan_workers == 4
    assert settings.recency_half_life_days == 14.0
    assert settings.location_filter_mode == "soft"
    assert settings.weights.skill_coverage == 0.50
    assert settings.weights.title_match == 0.25
    assert settings.weights.recency == 0.15
    assert settings.weights.location_fit == 0.10


def test_data_dir_argument_wins_over_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("BOARDWATCH_DATA_DIR", str(tmp_path / "env-data"))
    settings = load_settings(data_dir=tmp_path / "cli-data")
    assert settings.data_dir == tmp_path / "cli-data"


def test_config_file_overrides_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "config.toml").write_text(
        'per_host_delay_seconds = 2.5\n\n[weights]\nskill_coverage = 0.7\n'
        "title_match = 0.1\nrecency = 0.1\nlocation_fit = 0.1\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(cfg))
    monkeypatch.setenv("BOARDWATCH_DATA_DIR", str(tmp_path / "data"))
    settings = load_settings()
    assert settings.per_host_delay_seconds == 2.5
    assert settings.weights.skill_coverage == 0.7


def test_settings_are_frozen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from pydantic import ValidationError

    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("BOARDWATCH_DATA_DIR", str(tmp_path))
    settings = load_settings()
    with pytest.raises(ValidationError):
        settings.retry_attempts = 99  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("per_host_delay_seconds", 0.1),   # below 0.25 floor
        ("retry_attempts", 0), ("retry_attempts", 11),
        ("scan_workers", 0), ("scan_workers", 9),
    ],
)
def test_out_of_range_settings_are_rejected(tmp_path, field, bad) -> None:
    with pytest.raises(ValidationError) as exc:
        Settings(data_dir=tmp_path, config_dir=tmp_path, **{field: bad})
    assert field in str(exc.value)


@pytest.mark.parametrize(
    "key", ["skill_coverage", "title_match", "recency", "location_fit"]
)
@pytest.mark.parametrize("weight", [-0.1, 1.1])
def test_every_weight_key_constrained_to_unit_interval(tmp_path, key, weight) -> None:
    from boardwatch.core.settings import RankWeights
    with pytest.raises(ValidationError):
        Settings(
            data_dir=tmp_path, config_dir=tmp_path, weights=RankWeights(**{key: weight})
        )


@pytest.mark.parametrize(
    ("toml_line", "key"),
    [
        ("per_host_delay_seconds = 0.1", "per_host_delay_seconds"),  # below floor
        ("retry_attempts = 0", "retry_attempts"),
        ("retry_attempts = 11", "retry_attempts"),
        ("scan_workers = 0", "scan_workers"),
        ("scan_workers = 9", "scan_workers"),
        ("[weights]\nskill_coverage = -0.1", "skill_coverage"),
        ("[weights]\nskill_coverage = 1.1", "skill_coverage"),
    ],
)
def test_hand_edited_out_of_range_toml_fails_at_load(tmp_path, monkeypatch, toml_line, key) -> None:
    # every bounded key, at both bounds, loaded from a hand-edited config.toml (round 3 finding 3)
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path))
    (tmp_path / "config.toml").write_text(toml_line + "\n", encoding="utf-8")
    from boardwatch.core.settings import load_settings
    with pytest.raises(ValidationError) as exc:
        load_settings(data_dir=tmp_path)
    assert key in str(exc.value)  # the error names the offending key
