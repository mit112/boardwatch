from pathlib import Path

import pytest
from sqlalchemy import select
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.store import tables
from boardwatch.store.db import get_engine

runner = CliRunner()

INIT_INPUT = (
    "acme, globex\n"  # slugs
    "Backend engineer: Python, Go, PostgreSQL, Kubernetes.\n"  # profile text
    "Backend Engineer, Software Engineer\n"  # target titles
    "Staff, Principal\n"  # exclude titles
    "New York, Remote\n"  # locations
    "n\n"  # remote only?
)


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    return tmp_path / "data"


def _invoke(data_dir: Path, args: list[str], input_text: str | None = None) -> object:
    return runner.invoke(app, ["--data-dir", str(data_dir), *args], input=input_text)


def test_init_creates_watches_and_profile(env: Path) -> None:
    result = _invoke(env, ["init"], INIT_INPUT)
    assert result.exit_code == 0
    engine = get_engine(env)
    with engine.connect() as conn:
        companies = conn.execute(select(tables.companies).order_by(tables.companies.c.slug)).all()
        profile = conn.execute(select(tables.profile)).one()
    assert [(c.slug, c.provider, c.source, c.watched) for c in companies] == [
        ("acme", "greenhouse", "user", True),
        ("globex", "greenhouse", "user", True),
    ]
    assert {"Python", "Go", "PostgreSQL", "Kubernetes"} <= set(profile.skills_json)
    assert profile.taxonomy_version
    assert profile.target_titles_json == ["Backend Engineer", "Software Engineer"]
    assert profile.exclude_titles_json == ["Staff", "Principal"]
    assert profile.locations_json == ["New York", "Remote"]
    assert profile.remote_only is False


def test_init_is_idempotent(env: Path) -> None:
    assert _invoke(env, ["init"], INIT_INPUT).exit_code == 0
    rerun_input = INIT_INPUT.replace("Kubernetes", "Terraform")
    assert _invoke(env, ["init"], rerun_input).exit_code == 0
    engine = get_engine(env)
    with engine.connect() as conn:
        companies = conn.execute(select(tables.companies)).all()
        profiles = conn.execute(select(tables.profile)).all()
    assert len(companies) == 2  # updated, never duplicated
    assert len(profiles) == 1
    assert "Terraform" in profiles[0].skills_json  # re-derived on save


def test_zero_skill_warning(env: Path) -> None:
    no_skill_input = INIT_INPUT.replace(
        "Backend engineer: Python, Go, PostgreSQL, Kubernetes.",
        "I enjoy hiking and reading.",
    )
    result = _invoke(env, ["init"], no_skill_input)
    assert result.exit_code == 0
    assert "ranking will use" in result.output
    assert "title/recency/location only" in result.output


def test_profile_show(env: Path) -> None:
    _invoke(env, ["init"], INIT_INPUT)
    result = _invoke(env, ["profile", "show"])
    assert result.exit_code == 0
    assert "Python" in result.output
    assert "Taxonomy version" in result.output


def test_profile_show_without_profile_fails_cleanly(env: Path) -> None:
    result = _invoke(env, ["profile", "show"])
    assert result.exit_code == 1
    assert "boardwatch init" in result.output


def test_profile_edit_rederives_skills(env: Path) -> None:
    _invoke(env, ["init"], INIT_INPUT)
    edit_input = (
        "Now focused on Rust and Kafka stream processing.\n"  # new text
        "\n"  # keep target titles
        "\n"  # keep exclude titles
        "\n"  # keep locations
        "n\n"  # remote only
    )
    result = _invoke(env, ["profile", "edit"], edit_input)
    assert result.exit_code == 0
    engine = get_engine(env)
    with engine.connect() as conn:
        profile = conn.execute(select(tables.profile)).one()
    assert "Rust" in profile.skills_json and "Kafka" in profile.skills_json
    assert "Python" not in profile.skills_json


def test_profile_input_validated_at_the_boundary() -> None:
    from pydantic import ValidationError

    from boardwatch.cli.profile_cmd import ProfileInput

    with pytest.raises(ValidationError):  # empty/whitespace-only text never persists
        ProfileInput(
            text="", target_titles=[], exclude_titles=[], locations=[], remote_only=False
        )


def test_help_smoke(env: Path) -> None:
    assert runner.invoke(app, ["init", "--help"]).exit_code == 0
    assert runner.invoke(app, ["profile", "--help"]).exit_code == 0
