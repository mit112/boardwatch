import json
import tomllib
from pathlib import Path

import pytest
from sqlalchemy import insert
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.core.politeness import Fetcher
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
