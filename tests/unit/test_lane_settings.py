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


def test_linkedin_hub_nets_ship_inert_with_user_independent_defaults(cfg: Path) -> None:
    settings = load_settings(data_dir=None)

    assert settings.lane_search_hubs == ()
    assert settings.lane_hub_combos_per_run == 12
    assert settings.lane_hub_distance_miles == 25

    (cfg / "config.toml").write_text(
        'lane_search_hubs = ["Austin, TX", "Boston, MA"]\n', encoding="utf-8"
    )
    loaded = load_settings(data_dir=None)
    assert loaded.lane_search_hubs == ("Austin, TX", "Boston, MA")


def test_the_two_budgets_default_to_the_documented_values(cfg: Path) -> None:
    """10 matches `lanes.admission.DEFAULT_NEW_COMPANIES_PER_RUN`; 60 is the body-GET ceiling."""
    from boardwatch.lanes.admission import DEFAULT_NEW_COMPANIES_PER_RUN

    settings = load_settings(data_dir=None)
    assert settings.lane_new_companies_per_run == DEFAULT_NEW_COMPANIES_PER_RUN == 10
    assert settings.lane_posting_budget == 60


def test_only_the_two_BOUNDED_lanes_ship_uncapped_and_linkedin_does_not(cfg: Path) -> None:
    """The override mapping separates BOUNDED sources from STREAMS, and that is the whole rule.

    `jobapps`' source tree caps out around 38-45 companies in total. `hiringcafe` searches
    `dateFetchedPastNDays: 7`, a rolling pool that RECIRCULATES the same companies every run —
    measured over runs 116-127, per-run refusals fell monotonically 240 -> 193 while the cap
    admitted 10 a run and consecutive-run overlap ran 0.90-0.96 Jaccard. A cap on either only
    slows a fixed backlog down.

    **`linkedin` must stay absent**, and this test pins that as much as it pins the two entries.
    Its window is `f_TPR=r86400`, a fresh 24-hour slice: over runs 129-139 the cumulative union
    of companies went 187 -> 1,294 with no saturation and exactly one company refused in all ten
    runs. An exact-equality assertion is deliberate — a lane added to this mapping without the
    bounded-source evidence should fail here rather than quietly uncap a stream.
    """
    settings = load_settings(data_dir=None)
    assert settings.lane_new_companies_per_run_overrides == {
        "jobapps": "unlimited",
        "hiringcafe": "unlimited",
    }
    assert "linkedin" not in settings.lane_new_companies_per_run_overrides


def test_the_shipped_overrides_RESOLVE_to_uncapped_for_the_pool_lanes_only(cfg: Path) -> None:
    """The mapping above is data; this is the behaviour it buys, and nothing covered it.

    `_lane_company_cap` is the ONE site that resolves a lane's cap, and `"unlimited"` has to
    become `CompanyBudget`'s `None` sentinel rather than 0 — 0 means "admit nothing and still
    report every refusal", so a translation bug here would silently turn an uncapped lane into a
    lane that admits none of its finds and looks like it is working.

    Asserted per lane rather than on the dict, so this fails if the resolution changes even
    though the shipped mapping does not — and it pins that an unnamed lane still lands on the
    shared default.
    """
    from boardwatch.pipeline.runner import _lane_company_cap

    settings = load_settings(data_dir=None)
    assert _lane_company_cap(settings, "hiringcafe") is None, "hiringcafe must be uncapped"
    assert _lane_company_cap(settings, "jobapps") is None, "jobapps must be uncapped"
    assert _lane_company_cap(settings, "linkedin") == settings.lane_new_companies_per_run
    assert _lane_company_cap(settings, "linkedin") == 10, "the shared default is the point"
    assert _lane_company_cap(settings, "a-lane-nobody-named") == 10


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
            "lane_new_companies_per_run_overrides": {"alpha": 1},
            "lane_posting_budget": 1,
            "lane_search_hubs": ("Austin, TX",),
            "lane_hub_combos_per_run": 1,
            "lane_hub_distance_miles": 50,
        }
    )
    assert config_hash(armed) == config_hash(base)


# ---------------------------------------------------------------------------------------
# The jobapps lane's source path (D-386). Arming is a config.toml edit, so the round-trip
# through `load_settings` is the mechanism itself, not a detail about it.
# ---------------------------------------------------------------------------------------


def test_the_jobapps_source_ships_unset(cfg: Path) -> None:
    """Inert TWICE over: an empty lane list AND no source path. Either alone stops the lane."""
    assert load_settings(data_dir=None).jobapps_discovery_dir is None


def test_the_jobapps_source_round_trips_from_config_toml_as_a_path(cfg: Path) -> None:
    """The arming mechanism, asserted end to end.

    `Settings` IGNORES an unknown config key silently, so a typo here would arm nothing while
    looking armed. Reading the value back through `load_settings` is the only check that
    distinguishes the two, and a TOML string has to coerce to `Path` for a hand edit to work at
    all -- the CLI is not the only route in.
    """
    (cfg / "config.toml").write_text(
        'jobapps_discovery_dir = "/srv/jobapps/APPLY_QUEUE"\n', encoding="utf-8"
    )
    loaded = load_settings(data_dir=None).jobapps_discovery_dir
    assert loaded == Path("/srv/jobapps/APPLY_QUEUE")
    assert isinstance(loaded, Path)


def test_arming_the_jobapps_lane_needs_both_the_name_and_the_path(cfg: Path) -> None:
    """Naming the lane without a path leaves it unable to read, which it REPORTS rather than
    treating as an empty source."""
    (cfg / "config.toml").write_text('lanes_enabled = ["jobapps"]\n', encoding="utf-8")
    settings = load_settings(data_dir=None)
    assert settings.lanes_enabled == ("jobapps",)
    assert settings.jobapps_discovery_dir is None

    from boardwatch.lanes.jobapps import JobAppsLane, JobAppsSourceError

    with pytest.raises(JobAppsSourceError):
        JobAppsLane(source_dir=settings.jobapps_discovery_dir).collect(
            None,  # type: ignore[arg-type]
            lambda provider, slug: True,
        )


def test_the_jobapps_source_round_trips_through_config_set(cfg: Path) -> None:
    """A key that shows but cannot be written is still a gap. The caster is `str`, because the
    value is written straight into TOML and a `Path` is not TOML-serializable."""
    result = runner.invoke(app, ["config", "set", "jobapps_discovery_dir", "/srv/q"])
    assert result.exit_code == 0, result.stdout
    assert "jobapps_discovery_dir = /srv/q" in runner.invoke(app, ["config", "show"]).stdout
    assert load_settings(data_dir=None).jobapps_discovery_dir == Path("/srv/q")


def test_the_jobapps_source_does_not_move_the_config_hash(cfg: Path) -> None:
    """WHERE a lane reads from is not how a posting is judged.

    `policy_version` derives from `config_hash`, so classifying this IN would mark every
    permanent `built`/`skipped` disposition stale the moment the source directory moved -- a
    corpus-wide drain triggered by a path change that judged nothing.
    """
    from boardwatch.reports.manifest import config_hash

    base = Settings(data_dir=cfg / "d", config_dir=cfg)
    moved = base.model_copy(update={"jobapps_discovery_dir": Path("/srv/elsewhere")})
    assert config_hash(moved) == config_hash(base)
