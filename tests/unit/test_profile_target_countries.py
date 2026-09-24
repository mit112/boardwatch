"""DESIGN-T183 B1: the profile row's `target_countries` (ISO-3166 alpha-3, closed vocabulary).

Read by nothing yet. What is pinned here is the storage contract the B3 gates will rely on:
an existing profile row survives the migration and reads as undeclared (`()`), `profile edit`
writes the value and re-reads it, an out-of-vocabulary code is a typed failure, and the value
enters the ranker's profile fingerprint.
"""

import json
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.cli.profile_cmd import (
    ProfileInput,
    UnknownCountryCode,
    parse_target_countries,
)
from boardwatch.rank.heuristic import profile_view_from_row
from boardwatch.reports.manifest import profile_row_hash
from boardwatch.store.db import get_engine
from boardwatch.store.queries import get_profile

BASE = "p_form_questions"  # the head this migration follows
HEAD = "p_target_countries"  # the migration under test
MIGRATIONS = Path("src/boardwatch/store/migrations")

runner = CliRunner()


def _cfg(db_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_migration_keeps_a_seeded_row_and_reads_it_as_undeclared(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    cfg = _cfg(url)
    engine = create_engine(url)
    command.upgrade(cfg, BASE)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO profile (id, text, locations_json, remote_only, target_seniority_band, "
            "updated_at) VALUES (1, 'seeded', '[\"Boston, MA\"]', 0, 'entry', "
            "'2026-01-01 00:00:00')"
        ))
    command.upgrade(cfg, HEAD)
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM profile")).mappings().one()
    assert row["text"] == "seeded"
    assert row["target_seniority_band"] == "entry"
    assert row["target_countries_json"] == "[]"
    command.downgrade(cfg, BASE)
    with engine.connect() as conn:
        cols = {r[1] for r in conn.execute(text("PRAGMA table_info(profile)"))}
        assert conn.execute(text("SELECT text FROM profile")).scalar_one() == "seeded"
    assert "target_countries_json" not in cols


def test_absent_target_countries_reads_as_empty() -> None:
    class Bare:
        pass

    assert profile_view_from_row(Bare()).target_countries == ()


def test_codes_are_normalized_deduplicated_and_sorted() -> None:
    assert parse_target_countries(" can, usa,USA ") == ("CAN", "USA")
    assert parse_target_countries("") == ()


def test_an_unknown_code_is_a_typed_failure() -> None:
    with pytest.raises(UnknownCountryCode) as exc:
        parse_target_countries("USA, XYZ")
    assert exc.value.code == "XYZ"
    # Alpha-2 is not the vocabulary: "US" is a typo for the ISO-3 form, not a synonym.
    with pytest.raises(UnknownCountryCode):
        parse_target_countries("US")
    with pytest.raises(ValidationError):
        ProfileInput(
            text="t", target_titles=[], exclude_titles=[], locations=[], remote_only=False,
            target_countries=("ZZZ",),
        )


def test_profile_row_hash_tracks_target_countries() -> None:
    base = dict(skills=[], target_titles=[], exclude_titles=[], locations=[], remote_only=False)
    assert profile_row_hash(**base, target_countries=()) != profile_row_hash(
        **base, target_countries=("USA",)
    )


_INIT = "3\nacme\nBackend engineer: Python.\n\n\n\nn\nn\nsoftware\n"  # T184: the field prompt is last


def _edit(countries: str) -> str:
    return (
        "\n\n\n\n"  # keep text, target titles, exclude titles, locations
        "n\n"  # remote only
        "\n"  # keep resume max pages
        "\n"  # keep target seniority band
        f"{countries}\n"  # target countries
        "n\n"  # update eligibility checks? no
    )


def _invoke(env: Path, args: list[str], input_text: str) -> object:
    return runner.invoke(app, ["--data-dir", str(env), *args], input=input_text)


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    return tmp_path / "data"


def test_profile_edit_writes_and_rereads_target_countries(env: Path) -> None:
    assert _invoke(env, ["init"], _INIT).exit_code == 0
    with get_engine(env).connect() as conn:
        assert profile_view_from_row(get_profile(conn)).target_countries == ()
    result = _invoke(env, ["profile", "edit"], _edit("usa"))
    assert result.exit_code == 0, result.output
    with get_engine(env).connect() as conn:
        assert profile_view_from_row(get_profile(conn)).target_countries == ("USA",)
    # A blank answer keeps the stored value; `profile show --json` reports it.
    assert _invoke(env, ["profile", "edit"], _edit("")).exit_code == 0
    shown = _invoke(env, ["profile", "show", "--json"], "")
    assert json.loads(shown.output)["target_countries"] == ["USA"]


def test_profile_edit_reprompts_on_an_unknown_code(env: Path) -> None:
    assert _invoke(env, ["init"], _INIT).exit_code == 0
    result = _invoke(env, ["profile", "edit"], _edit("Canada\nCAN"))
    assert result.exit_code == 0, result.output
    assert "'CANADA' is not an ISO-3166 alpha-3 country code" in result.output
    with get_engine(env).connect() as conn:
        assert profile_view_from_row(get_profile(conn)).target_countries == ("CAN",)


def test_init_on_an_existing_install_keeps_target_countries(env: Path) -> None:
    """Re-running `init` re-persists the profile from its own prompts, which do not ask for the
    target countries. Under B3 an undeclared target makes both location gates inert, so a
    silent reset to `[]` would lift every non-US drop and hold on the next read; the stored
    value survives instead."""
    assert _invoke(env, ["init"], _INIT).exit_code == 0
    assert _invoke(env, ["profile", "edit"], _edit("usa")).exit_code == 0
    assert _invoke(env, ["init"], _INIT).exit_code == 0
    with get_engine(env).connect() as conn:
        assert profile_view_from_row(get_profile(conn)).target_countries == ("USA",)
