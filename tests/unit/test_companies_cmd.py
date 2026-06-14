import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.store import tables
from boardwatch.store.db import get_engine

runner = CliRunner()


@pytest.fixture(autouse=True)
def _no_gha(monkeypatch, tmp_path):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))


def _base(tmp_path):
    return ["--data-dir", str(tmp_path / "data")]


def _watch_count(tmp_path, provider, slug):
    try:
        with get_engine(tmp_path / "data").connect() as conn:
            return conn.execute(
                select(tables.companies).where(
                    tables.companies.c.provider == provider, tables.companies.c.slug == slug
                )
            ).all()
    except OperationalError:
        return []  # no DB / no table = no watches


@pytest.mark.parametrize("sub", ["search", "add", "remove", "list", "import", "export"])
def test_all_six_subcommands_have_help(tmp_path, sub) -> None:
    result = runner.invoke(app, [*_base(tmp_path), "companies", sub, "--help"])
    assert result.exit_code == 0


def test_search_is_case_insensitive_and_offline(tmp_path) -> None:
    # search reads the bundled catalog (no DB, no network); case-insensitive substring
    result = runner.invoke(app, [*_base(tmp_path), "companies", "search", "ACME"])
    assert result.exit_code == 0  # renders a (possibly empty) table without touching the network


def test_add_then_list_renders_watched_then_remove(tmp_path) -> None:
    base = _base(tmp_path)
    assert runner.invoke(app, [*base, "companies", "add", "lever:globex"]).exit_code == 0
    listed = runner.invoke(app, [*base, "companies", "list"])
    assert listed.exit_code == 0 and "globex" in listed.stdout and "yes" in listed.stdout  # watched col
    assert runner.invoke(app, [*base, "companies", "remove", "lever:globex"]).exit_code == 0


def test_add_is_idempotent_no_duplicate(tmp_path) -> None:
    base = _base(tmp_path)
    runner.invoke(app, [*base, "companies", "add", "lever:globex"])
    runner.invoke(app, [*base, "companies", "add", "https://jobs.lever.co/globex/job-9"])  # 2nd variant
    assert len(_watch_count(tmp_path, "lever", "globex")) == 1  # UNIQUE(provider, slug) respected


def test_add_unknown_url_exits_nonzero_and_writes_nothing(tmp_path) -> None:
    base = _base(tmp_path)
    result = runner.invoke(app, [*base, "companies", "add", "https://workday.com/acme"])
    assert result.exit_code == 1
    assert _watch_count(tmp_path, "greenhouse", "acme") == []  # DB untouched


def test_export_import_round_trip_is_noop_beyond_watching(tmp_path) -> None:
    base = _base(tmp_path)
    runner.invoke(app, [*base, "companies", "add", "lever:globex"])
    dump = runner.invoke(app, [*base, "companies", "export"]).stdout
    (tmp_path / "out.yaml").write_text(dump, encoding="utf-8")
    result = runner.invoke(app, [*base, "companies", "import", str(tmp_path / "out.yaml")])
    assert result.exit_code == 0
    assert len(_watch_count(tmp_path, "lever", "globex")) == 1
