import json
import tomllib
from pathlib import Path

import pytest
from sqlalchemy import insert
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.core.politeness import Fetcher
from boardwatch.core.secrets import LLM_API_KEY_ENV
from boardwatch.core.settings import load_settings
from boardwatch.extract.taxonomy import load_taxonomy
from boardwatch.providers.greenhouse import parse_job
from boardwatch.scan.apply import apply_board
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import insert_run, save_profile
from boardwatch.store.tables import companies

runner = CliRunner()

_GH_FIXTURE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "greenhouse" / "normal.json"


@pytest.fixture()
def cfg(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path))
    return tmp_path


def _base(tmp_path):
    return ["--data-dir", str(tmp_path / "data")]


def _seed_db(tmp_path) -> None:
    """Seed a DB with one company, one run, one posting, and a profile."""
    data_dir = tmp_path / "data"
    engine = get_engine(data_dir)
    ensure_schema(engine)

    with engine.begin() as conn:
        result = conn.execute(
            insert(companies).values(
                name="Acme", provider="greenhouse", slug="acme", source="user", watched=True
            )
        )
        company_id = int(result.inserted_primary_key[0])

    run_id = insert_run(engine)

    # Parse the Greenhouse fixture into a BoardSnapshot
    payload = json.loads(_GH_FIXTURE.read_bytes())
    jobs = payload["jobs"][:1]
    postings = [parse_job(job) for job in jobs]
    from boardwatch.core.models import BoardSnapshot

    snapshot = BoardSnapshot(status="complete", postings=postings, url="https://boards.greenhouse.io/acme")

    apply_board(engine, snapshot, company_id, run_id)

    # Save a profile so top has something to rank against
    taxonomy = load_taxonomy(tmp_path)
    with engine.begin() as conn:
        save_profile(
            conn,
            text="Python, Go, PostgreSQL",
            target_titles=["Backend Engineer"],
            exclude_titles=[],
            locations=[],
            remote_only=False,
            skills=sorted(taxonomy.extract("Python, Go, PostgreSQL")),
            taxonomy_version=taxonomy.version,
            resume_max_pages=1,
        )


def test_show_lists_keys(cfg) -> None:
    result = runner.invoke(app, [*_base(cfg), "config", "show"])
    assert result.exit_code == 0
    assert "retry_attempts" in result.stdout and "weights.skill_coverage" in result.stdout


def test_set_valid_writes_file_and_prints_change(cfg) -> None:
    result = runner.invoke(app, [*_base(cfg), "config", "set", "retry_attempts", "5"])
    assert result.exit_code == 0 and "→ 5" in result.stdout
    assert tomllib.loads((cfg / "config.toml").read_text())["retry_attempts"] == 5


@pytest.mark.parametrize(
    ("key", "value"), [("retry_attempts", "11"), ("nope", "1"), ("weights.recency", "2.0")]
)
def test_set_invalid_exits_nonzero_and_file_untouched(cfg, key, value) -> None:
    result = runner.invoke(app, [*_base(cfg), "config", "set", key, value])
    assert result.exit_code == 1
    assert not (cfg / "config.toml").exists()  # nothing written on the failure path


def test_set_keeps_a_search_hub_whose_NAME_CONTAINS_A_COMMA_intact(cfg) -> None:
    """The regression guard for the defect `lane_search_hubs` shipped with.

    The key was cast with `lanes_enabled`'s comma splitter. `config set lane_search_hubs
    "Austin, TX"` therefore stored `("Austin", "TX")` -- the lane geo-searched two places the
    user never named, found little, and reported that it had searched theirs.
    `"Austin, TX,Boston, MA"` became four hubs. Every hub LinkedIn's `location=` accepts is a
    "City, ST" pair, so this was not an edge case; it was every value the key has.

    Asserted through the CLI and then through `load_settings`, because the store-and-reload is
    the round trip that has to hold: `tomli_w` writes the list and pydantic must coerce the same
    two strings back.
    """
    result = runner.invoke(
        app,
        [*_base(cfg), "config", "set", "lane_search_hubs", '["Austin, TX", "Boston, MA"]'],
    )

    assert result.exit_code == 0, result.output
    assert tomllib.loads((cfg / "config.toml").read_text())["lane_search_hubs"] == [
        "Austin, TX",
        "Boston, MA",
    ]
    assert load_settings(data_dir=cfg / "data").lane_search_hubs == ("Austin, TX", "Boston, MA")


def test_set_refuses_a_bare_comma_separated_hub_list_rather_than_splitting_it(cfg) -> None:
    """The failure has to be LOUD. A user who types the old comma form must be told, not quietly
    given two wrong hubs -- silently mis-parsing is exactly the defect above."""
    result = runner.invoke(
        app, [*_base(cfg), "config", "set", "lane_search_hubs", "Austin, TX"]
    )

    assert result.exit_code == 1
    assert not (cfg / "config.toml").exists()


def test_set_a_blank_hub_list_disables_the_nets_rather_than_naming_an_empty_hub(cfg) -> None:
    result = runner.invoke(app, [*_base(cfg), "config", "set", "lane_search_hubs", "[]"])

    assert result.exit_code == 0, result.output
    assert load_settings(data_dir=cfg / "data").lane_search_hubs == ()


def test_set_preserves_unknown_user_keys(cfg) -> None:
    (cfg / "config.toml").write_text('mystery = "keep me"\n', encoding="utf-8")
    runner.invoke(app, [*_base(cfg), "config", "set", "scan_workers", "6"])
    data = tomllib.loads((cfg / "config.toml").read_text())
    assert data["scan_workers"] == 6 and data["mystery"] == "keep me"


# ---- D17/§3.4 effect tests for all four knob families ----
def test_delay_and_retry_and_workers_take_effect_next_scan(cfg) -> None:
    runner.invoke(app, [*_base(cfg), "config", "set", "per_host_delay_seconds", "2.5"])
    runner.invoke(app, [*_base(cfg), "config", "set", "retry_attempts", "7"])
    runner.invoke(app, [*_base(cfg), "config", "set", "scan_workers", "6"])
    settings = load_settings(data_dir=cfg / "data")
    fetcher = Fetcher(settings)
    assert fetcher.effective_delay == 2.5
    assert fetcher.retry_attempts == 7  # deviation-10 property
    assert settings.scan_workers == 6  # coordinator pool size source


def test_weight_change_alters_next_top(cfg) -> None:
    """A weights.* change reaches ranking with no other action (D17 live-read)."""
    _seed_db(cfg)
    base = _base(cfg)

    before = runner.invoke(app, [*base, "top"]).stdout
    runner.invoke(app, [*base, "config", "set", "weights.skill_coverage", "0.9"])
    after = runner.invoke(app, [*base, "top"]).stdout
    assert before != after  # the live-read weight changed the ranking output


def test_show_lists_llm_state_not_reserved(cfg, monkeypatch) -> None:
    canary = "CANARY-SHOW-SECRET"
    monkeypatch.setenv(LLM_API_KEY_ENV, canary)
    result = runner.invoke(app, [*_base(cfg), "config", "show"])
    assert result.exit_code == 0
    assert "reserved" not in result.output.lower()
    assert "llm.enabled" in result.output
    assert "llm.resume_tailoring" in result.output
    assert "llm.resume_tailoring_via_agent" in result.output
    assert "llm.api_key" in result.output and "set" in result.output
    assert canary not in result.output  # value never printed


def test_set_llm_enabled_now_succeeds(cfg) -> None:
    result = runner.invoke(app, [*_base(cfg), "config", "set", "llm.enabled", "true"])
    assert result.exit_code == 0 and "→ True" in result.stdout
    assert load_settings(data_dir=cfg / "data").llm.enabled is True


def test_set_llm_resume_tailoring_via_agent_succeeds(cfg) -> None:
    result = runner.invoke(
        app, [*_base(cfg), "config", "set", "llm.resume_tailoring_via_agent", "true"]
    )
    assert result.exit_code == 0
    assert load_settings(data_dir=cfg / "data").llm.resume_tailoring_via_agent is True


def test_set_llm_provider_refused_as_not_a_toggle(cfg) -> None:
    result = runner.invoke(app, [*_base(cfg), "config", "set", "llm.provider", "anthropic"])
    assert result.exit_code == 1
    assert "not a toggle" in result.output.lower()
    assert not (cfg / "config.toml").exists()


def test_set_llm_bad_bool_writes_nothing(cfg) -> None:
    result = runner.invoke(app, [*_base(cfg), "config", "set", "llm.enabled", "maybe"])
    assert result.exit_code == 1
    assert not (cfg / "config.toml").exists()


def test_set_llm_max_calls_per_run_valid_and_floor(cfg) -> None:
    ok = runner.invoke(app, [*_base(cfg), "config", "set", "llm.max_calls_per_run", "10"])
    assert ok.exit_code == 0
    assert load_settings(data_dir=cfg / "data").llm.max_calls_per_run == 10
    bad = runner.invoke(app, [*_base(cfg), "config", "set", "llm.max_calls_per_run", "0"])
    assert bad.exit_code == 1  # ge=1 floor


def test_set_llm_api_key_still_refused_as_secret(cfg) -> None:
    result = runner.invoke(app, [*_base(cfg), "config", "set", "llm.api_key", "whatever"])
    assert result.exit_code == 1
    assert "whatever" not in result.output
    assert not (cfg / "config.toml").exists()


def test_set_secret_key_rejected_pointing_to_env(cfg) -> None:
    result = runner.invoke(app, [*_base(cfg), "config", "set", "llm.api_key", "whatever"])
    assert result.exit_code == 1
    assert LLM_API_KEY_ENV in result.output    # points to the env var
    assert "whatever" not in result.output     # the value is never echoed
    assert not (cfg / "config.toml").exists()


def test_set_refuses_when_config_contains_secret_and_never_leaks_value(cfg) -> None:
    canary = "CANARY-SECRET-DO-NOT-LEAK"
    (cfg / "config.toml").write_text(f'[llm]\napi_key = "{canary}"\n', encoding="utf-8")
    result = runner.invoke(app, [*_base(cfg), "config", "set", "retry_attempts", "5"])
    assert result.exit_code == 1
    assert "llm.api_key" in result.output      # the offending path is named
    assert canary not in result.output         # value-free error
    assert result.exception is None or canary not in repr(result.exception)


def test_config_set_notify_webhook_enabled_roundtrips(cfg) -> None:
    result = runner.invoke(app, [*_base(cfg), "config", "set", "notify.webhook_enabled", "true"])
    assert result.exit_code == 0
    assert load_settings(data_dir=cfg / "data").notify.webhook_enabled is True


def test_config_set_notify_bad_bool_rejected(cfg) -> None:
    result = runner.invoke(app, [*_base(cfg), "config", "set", "notify.desktop_enabled", "maybe"])
    assert result.exit_code == 1
    assert not (cfg / "config.toml").exists()  # nothing written on the failure path


def test_config_set_notify_webhook_url_rejected_and_never_written(cfg) -> None:
    """notify.webhook_url has no config home by design (P0-3): it's unrecognized, so `set`
    must reject it AND must never let the URL land in config.toml."""
    result = runner.invoke(
        app, [*_base(cfg), "config", "set", "notify.webhook_url", "https://hook.example/x"]
    )
    assert result.exit_code != 0
    assert not (cfg / "config.toml").exists()  # nothing written on the failure path


def test_set_refuses_when_config_contains_webhook_url_secret_and_preserves_it(cfg) -> None:
    """A pre-existing notify.webhook_url is a secret (P0-3): a later VALID `config set`
    must refuse rather than silently reserializing (and thus persisting) it."""
    canary = "https://hook.example/secret-token"
    (cfg / "config.toml").write_text(f'[notify]\nwebhook_url = "{canary}"\n', encoding="utf-8")
    result = runner.invoke(app, [*_base(cfg), "config", "set", "notify.desktop_enabled", "true"])
    assert result.exit_code != 0
    assert "notify.webhook_url" in result.output   # the offending path is named
    assert canary not in result.output             # value-free error
    data = tomllib.loads((cfg / "config.toml").read_text())
    assert "desktop_enabled" not in data.get("notify", {})   # valid set was NOT applied
    assert data["notify"]["webhook_url"] == canary            # secret preserved untouched


def test_set_refuses_secret_in_array_of_tables_and_never_leaks(cfg) -> None:
    canary = "CANARY-AOT-SECRET"
    (cfg / "config.toml").write_text(f'[[watches]]\napi_key = "{canary}"\n', encoding="utf-8")
    result = runner.invoke(app, [*_base(cfg), "config", "set", "retry_attempts", "5"])
    assert result.exit_code == 1
    assert "watches[0].api_key" in result.output   # nested path is named
    assert canary not in result.output             # value never leaks
    assert result.exception is None or canary not in repr(result.exception)


def test_every_scalar_setting_is_reachable_from_the_cli() -> None:
    """`_SCALAR_KEYS` is a hand-maintained mirror of `Settings`, and it drifted silently.

    Five settings — `seen_ttl_days` among them, which P6 shipped as the knob governing how long
    a surfaced lead stays suppressed — were absent, so `config show` did not print them and
    `config set` rejected them as unknown keys, while the README promised the command "prints
    every key" and the settings surface promised every feature was reversible without
    hand-editing `config.toml`. Nothing caught it because a missing entry is not an error
    anywhere; this test is the detector.
    """
    from boardwatch.cli.config_cmd import _SCALAR_KEYS
    from boardwatch.core.settings import Settings

    # data_dir/config_dir are CLI/env-level paths, and the four nested models have their own
    # surfaces (weights.*, llm.*, notify.*, gate.*).
    nested = {"weights", "llm", "notify", "gate"}
    paths = {"data_dir", "config_dir"}
    # A per-lane MAPPING, not a scalar `_SCALAR_KEYS` can cast: `config set`'s casters each
    # parse one string into one value, and a lane name isn't known ahead of time to give one a
    # key of its own. Deliberately config.toml-only — hand-edit the `[lane_new_companies_per_run_overrides]`
    # table; `config show` omits it for the same reason.
    non_scalar = {"lane_new_companies_per_run_overrides"}
    scalar = set(Settings.model_fields) - nested - paths - non_scalar

    assert scalar == set(_SCALAR_KEYS), (
        f"missing from config show/set: {sorted(scalar - set(_SCALAR_KEYS))}; "
        f"stale entries: {sorted(set(_SCALAR_KEYS) - scalar)}"
    )


def test_the_new_scalar_keys_round_trip_through_set_and_show(cfg) -> None:
    """Reachability is not enough — a key that shows but cannot be written is still a gap."""
    assert runner.invoke(app, ["config", "set", "seen_ttl_days", "14"]).exit_code == 0
    assert runner.invoke(app, ["config", "set", "location_filter_mode", "hard"]).exit_code == 0

    out = runner.invoke(app, ["config", "show"]).stdout
    assert "seen_ttl_days = 14" in out
    assert "location_filter_mode = hard" in out
    assert load_settings(data_dir=None).seen_ttl_days == 14


def test_an_invalid_value_for_a_new_key_is_refused(cfg) -> None:
    """Validation rides on constructing a `Settings`, so the enum and the ge=1 bound both fire
    even though the casters here only parse."""
    assert runner.invoke(app, ["config", "set", "location_filter_mode", "sideways"]).exit_code == 1
    assert runner.invoke(app, ["config", "set", "seen_ttl_days", "0"]).exit_code == 1
