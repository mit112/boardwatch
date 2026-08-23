"""The three lane settings (plan D8), and the one thing that matters most about them: OFF.

Gate P3 needs 7 consecutive clean SCHEDULED ticks and stands at 0 of 7. An unproven network
lane armed in the daily driver risks the streak and buys the gate nothing — the lane can be
exercised by a manual run, which does not touch the counter. So a default that silently became
`("hiringcafe",)` would be a program-level regression, not a config nit, and it gets its own
test rather than relying on the generalization snapshot alone (which pins the value but is a
tooling check a reader of this package never sees).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.core.settings import Settings, load_settings

runner = CliRunner()


@pytest.fixture()
def cfg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("BOARDWATCH_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "cfg").mkdir(parents=True)
    return tmp_path / "cfg"


def test_every_lane_ships_off(cfg: Path) -> None:
    """Gate P3, not caution. An empty tuple, never a name."""
    settings = load_settings(data_dir=None)
    assert settings.lanes_enabled == ()


def test_the_two_budgets_default_to_the_documented_values(cfg: Path) -> None:
    """10 matches `lanes.admission.DEFAULT_NEW_COMPANIES_PER_RUN`; 60 is the body-GET ceiling."""
    from boardwatch.lanes.admission import DEFAULT_NEW_COMPANIES_PER_RUN

    settings = load_settings(data_dir=None)
    assert settings.lane_new_companies_per_run == DEFAULT_NEW_COMPANIES_PER_RUN == 10
    assert settings.lane_posting_budget == 60


def test_a_lane_list_loads_from_config_toml_as_a_tuple(cfg: Path) -> None:
    """TOML has no tuple, so the array has to coerce — otherwise arming a lane by hand-editing
    config.toml would fail validation and the only route in would be the CLI."""
    (cfg / "config.toml").write_text(
        'lanes_enabled = ["alpha", "beta"]\nlane_posting_budget = 5\n', encoding="utf-8"
    )
    settings = load_settings(data_dir=None)
    assert settings.lanes_enabled == ("alpha", "beta")
    assert settings.lane_posting_budget == 5


def test_a_negative_budget_is_refused_at_load(cfg: Path) -> None:
    """0 is meaningful (disarm the spend); a negative one is a typo, and `CompanyBudget` would
    otherwise raise it deep inside a run rather than at the edit that caused it."""
    (cfg / "config.toml").write_text("lane_new_companies_per_run = -1\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_settings(data_dir=None)


def test_the_lane_keys_round_trip_through_config_set_and_show(cfg: Path) -> None:
    """Reachability from the CLI is asserted exhaustively elsewhere; this is the other half —
    a key that shows but cannot be written is still a gap. `lanes_enabled` is the only
    non-scalar in that table, so its caster is the one that can silently not work."""
    assert runner.invoke(app, ["config", "set", "lanes_enabled", "alpha, beta"]).exit_code == 0
    assert runner.invoke(app, ["config", "set", "lane_posting_budget", "12"]).exit_code == 0

    out = runner.invoke(app, ["config", "show"]).stdout
    assert "lanes_enabled = ('alpha', 'beta')" in out
    assert "lane_posting_budget = 12" in out
    assert load_settings(data_dir=None).lanes_enabled == ("alpha", "beta")


def test_setting_the_lane_list_to_blank_disarms_every_lane(cfg: Path) -> None:
    """The way back off has to exist, and an empty string must not register a lane named ""
    that would then be reported as unregistered on every run."""
    assert runner.invoke(app, ["config", "set", "lanes_enabled", "alpha"]).exit_code == 0
    assert runner.invoke(app, ["config", "set", "lanes_enabled", ""]).exit_code == 0
    assert load_settings(data_dir=None).lanes_enabled == ()


def test_the_lane_knobs_do_not_move_the_config_hash(cfg: Path) -> None:
    """They are ACQUISITION, classified with `detail_fetch_budget` rather than with the ranking
    knobs. The consequence is the reason: `policy_version` derives from `config_hash`, so a
    decision-relevant classification would mark every permanent `built`/`skipped` disposition
    stale the moment a lane is armed — a corpus-wide drain triggered by a knob that judged
    nothing. The funnel's `lanes` section is what discloses the change instead."""
    from boardwatch.reports.manifest import config_hash

    base = Settings(data_dir=cfg / "d", config_dir=cfg)
    armed = base.model_copy(
        update={
            "lanes_enabled": ("alpha",),
            "lane_new_companies_per_run": 3,
            "lane_posting_budget": 1,
        }
    )
    assert config_hash(armed) == config_hash(base)
