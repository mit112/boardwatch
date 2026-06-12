"""Settings: config/data locations (§2.4) and documented defaults (D17, §3.4).

Precedence: CLI --data-dir > BOARDWATCH_DATA_DIR > platformdirs default.
Config file: {config_dir}/config.toml; weights and politeness knobs are read
at call time per D17 — there is no caching layer to invalidate.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any, Literal

from platformdirs import user_config_dir, user_data_dir
from pydantic import BaseModel, ConfigDict, Field

APP_NAME = "boardwatch"


class RankWeights(BaseModel):
    model_config = ConfigDict(frozen=True)

    skill_coverage: float = 0.50
    title_match: float = 0.25
    recency: float = 0.15
    location_fit: float = 0.10


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    data_dir: Path
    config_dir: Path
    per_host_delay_seconds: float = 1.0  # floor 0.25 enforced by the Fetcher (§3.4)
    retry_attempts: int = 3
    busy_timeout_ms: int = 5000
    scan_workers: int = 4
    recency_half_life_days: float = 14.0
    location_filter_mode: Literal["soft", "hard"] = "soft"
    weights: RankWeights = Field(default_factory=RankWeights)


def default_config_dir() -> Path:
    env = os.environ.get("BOARDWATCH_CONFIG_DIR")
    return Path(env) if env else Path(user_config_dir(APP_NAME))


def default_data_dir() -> Path:
    env = os.environ.get("BOARDWATCH_DATA_DIR")
    return Path(env) if env else Path(user_data_dir(APP_NAME))


def load_settings(data_dir: Path | None = None) -> Settings:
    config_dir = default_config_dir()
    raw: dict[str, Any] = {}
    config_file = config_dir / "config.toml"
    if config_file.is_file():
        raw = tomllib.loads(config_file.read_text(encoding="utf-8"))
    raw.pop("config_dir", None)
    file_data_dir = raw.pop("data_dir", None)
    resolved = data_dir or (Path(str(file_data_dir)) if file_data_dir else default_data_dir())
    return Settings(data_dir=resolved, config_dir=config_dir, **raw)
