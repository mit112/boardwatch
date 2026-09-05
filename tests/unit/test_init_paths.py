from pathlib import Path

import pytest
from sqlalchemy import func, select
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.registry.validate import CompanyEntry
from boardwatch.store import tables
from boardwatch.store.db import get_engine
from boardwatch.tailor.render.latex import TemplateArtifactError, resolve_template

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
_PROFILE = "Backend engineer: Python, Go.\nBackend Engineer\n\n\nn\nn\n"  # trailing n: skip eligibility


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
    skilless = "1\nqqzz nonsense lorem ipsum\nBackend Engineer\n\n\nn\nn\n"
    result = runner.invoke(app, [*base, "init"], input=skilless)
    assert result.exit_code == 0
    # Rich wraps at 80 cols and may split the warning across lines — collapse whitespace on
    # BOTH sides, then assert the EXACT shipped ZERO_SKILL_WARNING appears (not a fragment)
    normalized = " ".join(result.stdout.split())
    assert " ".join(ZERO_SKILL_WARNING.split()) in normalized
    assert "Recognized" not in normalized  # and NOT the positive branch


# --- T31: `init` seeds the résumé template ------------------------------------------------
#
# T2 made a run refuse when `{config_dir}/resume_template.tex` is absent, which left a fresh
# install with nothing to edit. `init` now writes the bundled template there when the file is
# absent. The refusal is NOT relaxed: the bundled header/education are placeholder identity and
# `_PLACEHOLDER_PHRASES` still refuses them, so the guarantee is unchanged and only the
# actionability moves — an editable file instead of an absent one.


def _template_path(tmp_path) -> Path:
    return tmp_path / "cfg" / "resume_template.tex"


def test_init_writes_the_bundled_template_when_absent(tmp_path) -> None:
    assert not _template_path(tmp_path).exists()
    result = runner.invoke(app, [*_base(tmp_path), "init"], input="1\n" + _PROFILE)
    assert result.exit_code == 0
    assert _template_path(tmp_path).read_text(encoding="utf-8") == resolve_template(None)


def test_init_never_overwrites_an_existing_template(tmp_path) -> None:
    # An edited template is the whole point of the file; `init` re-run must not clobber it.
    edited = resolve_template(None).replace("Your Name", "Ada Lovelace")
    _template_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    _template_path(tmp_path).write_text(edited, encoding="utf-8")
    result = runner.invoke(app, [*_base(tmp_path), "init"], input="1\n" + _PROFILE)
    assert result.exit_code == 0
    assert _template_path(tmp_path).read_text(encoding="utf-8") == edited


def test_the_seeded_template_is_still_refused_until_it_is_edited(tmp_path) -> None:
    # The fail-closed guarantee T2 shipped, restated against the seeded file: writing it does
    # NOT make a run render placeholder identity. The refusal moves from "no such file" to
    # "still carries the bundled placeholder", and both are TemplateArtifactError, which is
    # what `run.py`'s FOREIGN_AVAILABILITY matches by isinstance.
    result = runner.invoke(app, [*_base(tmp_path), "init"], input="1\n" + _PROFILE)
    assert result.exit_code == 0
    with pytest.raises(TemplateArtifactError) as excinfo:
        resolve_template(tmp_path / "cfg")
    assert "Your Name" in str(excinfo.value)
