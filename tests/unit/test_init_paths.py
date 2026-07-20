import pytest
from sqlalchemy import func, select
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.registry.validate import CompanyEntry
from boardwatch.store import tables
from boardwatch.store.db import get_engine

runner = CliRunner()
CATALOG = [
    CompanyEntry(name="Acme", provider="greenhouse", slug="acme", tags=["starter"]),
    CompanyEntry(name="Globex", provider="lever", slug="globex", tags=["starter"]),
    CompanyEntry(name="Initech", provider="ashby", slug="initech", tags=[]),
]


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch, tmp_path):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    # both init_cmd and companies_cmd read the catalog through these names
    monkeypatch.setattr("boardwatch.cli.init_cmd.load_catalog", lambda *a, **k: CATALOG)
    monkeypatch.setattr("boardwatch.cli.init_cmd.starter_entries",
                        lambda entries: [e for e in entries if "starter" in e.tags])


def _base(tmp_path):
    return ["--data-dir", str(tmp_path / "data")]


def _watches(tmp_path):
    with get_engine(tmp_path / "data").connect() as conn:
        return {
            (r.provider, r.slug, r.source)
            for r in conn.execute(
                select(tables.companies.c.provider, tables.companies.c.slug,
                       tables.companies.c.source).where(tables.companies.c.watched.is_(True))
            ).all()
        }


# profile answers reused by every path (text, targets, excludes, locations, remote?)
_PROFILE = "Backend engineer: Python, Go.\nBackend Engineer\n\n\nn\n"


def test_starter_path_watches_all_starter_as_registry(tmp_path) -> None:
    base = _base(tmp_path)
    result = runner.invoke(app, [*base, "init"], input="1\n" + _PROFILE)
    assert result.exit_code == 0
    assert _watches(tmp_path) == {("greenhouse", "acme", "registry"), ("lever", "globex", "registry")}


def test_paste_path_accepts_mixed_slugs_and_urls_bare_is_greenhouse(tmp_path) -> None:
    base = _base(tmp_path)
    paste = "acme, lever:globex, https://jobs.ashbyhq.com/initech"  # bare token → greenhouse
    result = runner.invoke(app, [*base, "init"], input="3\n" + paste + "\n" + _PROFILE)
    assert result.exit_code == 0
    assert ("greenhouse", "acme", "registry") in _watches(tmp_path)  # acme is in CATALOG
    assert ("lever", "globex", "registry") in _watches(tmp_path)
    assert ("ashby", "initech", "registry") in _watches(tmp_path)


def test_rerun_with_starter_already_watched_changes_nothing(tmp_path) -> None:
    base = _base(tmp_path)
    runner.invoke(app, [*base, "init"], input="1\n" + _PROFILE)
    before = _watches(tmp_path)
    with get_engine(tmp_path / "data").connect() as conn:
        n_before = conn.execute(select(func.count()).select_from(tables.companies)).scalar_one()
    runner.invoke(app, [*base, "init"], input="1\n" + _PROFILE)  # re-run, same path
    with get_engine(tmp_path / "data").connect() as conn:
        n_after = conn.execute(select(func.count()).select_from(tables.companies)).scalar_one()
    assert _watches(tmp_path) == before and n_after == n_before  # no duplicates, no churn


def test_search_path_watches_confirmed_entry(tmp_path) -> None:
    # path 2: search "globex" → confirm y → that entry is watched (source=registry)
    base = _base(tmp_path)
    result = runner.invoke(app, [*base, "init"], input="2\nglobex\ny\n" + _PROFILE)
    assert result.exit_code == 0
    assert ("lever", "globex", "registry") in _watches(tmp_path)


def test_zero_skill_warning_fires_for_skilless_profile(tmp_path) -> None:
    # the P0 #11 zero-skill warning is unchanged (regression, not rewritten): a profile with
    # no recognized skills emits the EXACT shipped ZERO_SKILL_WARNING text
    from boardwatch.cli.profile_cmd import ZERO_SKILL_WARNING

    base = _base(tmp_path)
    skilless = "1\nqqzz nonsense lorem ipsum\nBackend Engineer\n\n\nn\n"
    result = runner.invoke(app, [*base, "init"], input=skilless)
    assert result.exit_code == 0
    # Rich wraps at 80 cols and may split the warning across lines — collapse whitespace on
    # BOTH sides, then assert the EXACT shipped ZERO_SKILL_WARNING appears (not a fragment)
    normalized = " ".join(result.stdout.split())
    assert " ".join(ZERO_SKILL_WARNING.split()) in normalized
    assert "Recognized" not in normalized  # and NOT the positive branch
