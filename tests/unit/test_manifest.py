"""P0 item 4: the two new manifest hashes (`config_hash`, `profile_row_hash`).

These pin the two claims the manifest makes and could get wrong: that the config hash tracks
exactly the decision-relevant settings and nothing else, and that it FAILS closed on an
unclassified field rather than silently covering the wrong set.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from boardwatch.core.settings import LLMTier, Settings
from boardwatch.reports import manifest
from boardwatch.reports.manifest import (
    UnclassifiedSettingError,
    config_hash,
    profile_row_hash,
)


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    base: dict[str, object] = {"data_dir": tmp_path / "data", "config_dir": tmp_path / "cfg"}
    base.update(overrides)
    return Settings(**base)


def test_config_hash_is_stable_for_the_same_settings(tmp_path: Path) -> None:
    assert config_hash(_settings(tmp_path)) == config_hash(_settings(tmp_path))


def test_a_decision_relevant_change_changes_the_hash(tmp_path: Path) -> None:
    base = config_hash(_settings(tmp_path))
    assert config_hash(_settings(tmp_path, location_filter_mode="hard")) != base
    assert config_hash(_settings(tmp_path, recency_half_life_days=30.0)) != base
    assert config_hash(_settings(tmp_path, llm=LLMTier(enabled=True, provider="anthropic"))) != base


def test_a_machine_local_or_throughput_change_does_not_change_the_hash(tmp_path: Path) -> None:
    """scan_workers, notify and max_calls_per_run are OUT — they must not move the hash, or a
    reproducibility check would fire on a change that cannot alter which postings become leads."""
    base = config_hash(_settings(tmp_path))
    assert config_hash(_settings(tmp_path, scan_workers=8)) == base
    assert config_hash(_settings(tmp_path, detail_fetch_budget=999)) == base
    assert config_hash(_settings(tmp_path, reap_stale_after_hours=1)) == base
    assert config_hash(_settings(tmp_path, llm=LLMTier(max_calls_per_run=7))) == base


def test_a_data_dir_change_does_not_change_the_hash(tmp_path: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    other = tmp_path_factory.mktemp("elsewhere")
    assert config_hash(_settings(tmp_path)) == config_hash(
        Settings(data_dir=other, config_dir=other)
    )


def test_config_hash_fails_closed_on_an_unclassified_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulate a newly-added Settings field by dropping one from the classification: the hash
    must refuse rather than quietly cover a different set of fields."""
    monkeypatch.setattr(
        manifest, "_CONFIG_RELEVANT", manifest._CONFIG_RELEVANT - {"location_filter_mode"}
    )
    with pytest.raises(UnclassifiedSettingError):
        config_hash(_settings(tmp_path))


def test_profile_row_hash_distinguishes_missing_from_empty() -> None:
    """A null column and an empty list are different inputs; folding them would let a profile
    that dropped every exclude-title hash the same as one that never had any."""
    missing = profile_row_hash(
        skills=["python"], target_titles=None, exclude_titles=None,
        locations=None, remote_only=False,
    )
    empty = profile_row_hash(
        skills=["python"], target_titles=[], exclude_titles=[],
        locations=[], remote_only=False,
    )
    assert missing != empty


def test_profile_row_hash_tracks_exclude_titles() -> None:
    base = profile_row_hash(
        skills=["python"], target_titles=["swe"], exclude_titles=["manager"],
        locations=["remote"], remote_only=True,
    )
    changed = profile_row_hash(
        skills=["python"], target_titles=["swe"], exclude_titles=["manager", "sales"],
        locations=["remote"], remote_only=True,
    )
    assert base != changed
