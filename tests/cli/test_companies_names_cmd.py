"""`boardwatch companies names` — repair companies named after their slug (T74 part B).

`BOARDWATCH_CONFIG_DIR` is pinned in every test, never inherited: `conftest.py` autouses
`BOARDWATCH_DATA_DIR` but deliberately leaves the config dir alone, so without this these tests
would read the operator's real `config.toml`.

Every name here is synthetic (`acme.test`, "Acme Corp"). No real employer, host or slug appears.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import insert, select
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine

runner = CliRunner()


@pytest.fixture(autouse=True)
def _pinned_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)


def _data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


def _seed(tmp_path: Path, rows: list[dict[str, object]]) -> None:
    engine = get_engine(_data_dir(tmp_path))
    ensure_schema(engine)
    with engine.begin() as conn:
        for row in rows:
            conn.execute(insert(tables.companies).values(**row))
    engine.dispose()


def _names(tmp_path: Path) -> dict[str, str]:
    engine = get_engine(_data_dir(tmp_path))
    with engine.connect() as conn:
        stored = {
            f"{row.provider}:{row.slug}": row.name
            for row in conn.execute(
                select(tables.companies.c.provider, tables.companies.c.slug,
                       tables.companies.c.name)
            ).all()
        }
    engine.dispose()
    return stored


def _cli(tmp_path: Path, args: list[str]):
    return runner.invoke(app, ["--data-dir", str(_data_dir(tmp_path)), "companies", *args])


# ---------------------------------------------------------------- `add` names the employer

def test_add_names_a_non_registry_board_after_its_employer_not_its_host(tmp_path: Path) -> None:
    """RED before T74: the stored name was the slug, `careers.acme.test`."""
    result = _cli(tmp_path, ["add", "eightfold:careers.acme.test"])
    assert result.exit_code == 0, result.output
    assert _names(tmp_path) == {"eightfold:careers.acme.test": "acme"}


def test_add_keeps_the_slug_as_the_name_when_no_employer_is_derivable(tmp_path: Path) -> None:
    """A host whose every label is the vendor's or a career-site word names no employer, and a
    guessed one would merge two companies. The slug stands and the row is reportable."""
    assert _cli(tmp_path, ["add", "eightfold:careers.eightfold.ai"]).exit_code == 0
    assert _names(tmp_path) == {"eightfold:careers.eightfold.ai": "careers.eightfold.ai"}


def test_add_still_prefers_the_bundled_registrys_own_name(tmp_path: Path) -> None:
    """The registry knows this board, and a curated name beats a derived token."""
    assert _cli(tmp_path, ["add", "greenhouse:stripe"]).exit_code == 0
    assert _names(tmp_path) == {"greenhouse:stripe": "Stripe"}


# ---------------------------------------------------------------- the repair sweep

_LEGACY = [
    # named after its host by a pre-T74 `add`
    {"name": "careers.acme.test", "provider": "eightfold", "slug": "careers.acme.test",
     "source": "user", "watched": True},
    # named after its Workday triple by the same path
    {"name": "acme.wd1.myworkdayjobs.com/acme/Acme_External_Site", "provider": "workday",
     "slug": "acme.wd1.myworkdayjobs.com/acme/Acme_External_Site", "source": "user",
     "watched": True},
    # a curated registry name — must not be touched
    {"name": "Acme Corp", "provider": "greenhouse", "slug": "acmecorp",
     "source": "registry", "watched": True},
    # a lane-discovered name — must not be touched either
    {"name": "Acme Robotics", "provider": "lever", "slug": "acmerobotics",
     "source": "lane", "watched": False},
    # named after its slug, but the slug names no employer
    {"name": "careers.eightfold.ai", "provider": "eightfold", "slug": "careers.eightfold.ai",
     "source": "user", "watched": True},
]


def test_the_sweep_reports_without_writing_by_default(tmp_path: Path) -> None:
    _seed(tmp_path, _LEGACY)
    before = _names(tmp_path)
    result = _cli(tmp_path, ["names"])
    assert result.exit_code == 0, result.output
    assert "would rewrite" in result.output
    assert "not derivable" in result.output
    assert _names(tmp_path) == before


def test_the_sweep_rewrites_only_the_rows_named_after_their_slug(tmp_path: Path) -> None:
    """RED before T74: no `names` command existed, so these rows could only be repaired by
    hand-editing the live store."""
    _seed(tmp_path, _LEGACY)
    result = _cli(tmp_path, ["names", "--apply"])
    assert result.exit_code == 0, result.output
    assert _names(tmp_path) == {
        "eightfold:careers.acme.test": "acme",
        "workday:acme.wd1.myworkdayjobs.com/acme/Acme_External_Site": "acme",
        # untouched: a curated name and a lane-discovered one are already employer names
        "greenhouse:acmecorp": "Acme Corp",
        "lever:acmerobotics": "Acme Robotics",
        # untouched: nothing derivable, so nothing guessed
        "eightfold:careers.eightfold.ai": "careers.eightfold.ai",
    }


def test_the_sweep_names_the_backfill_the_operator_still_owes(tmp_path: Path) -> None:
    """`companies.name` feeds `IdentityInputs.company_name`, a component of `cross_host`, so
    every identity row written under the old name is stale the moment this commits. A repair
    that did not say so would leave dedup reading the OLD names and look like it had worked."""
    _seed(tmp_path, _LEGACY)
    result = _cli(tmp_path, ["names", "--apply"])
    assert "identities backfill" in result.output


def test_the_sweep_is_idempotent(tmp_path: Path) -> None:
    _seed(tmp_path, _LEGACY)
    _cli(tmp_path, ["names", "--apply"])
    after_first = _names(tmp_path)
    second = _cli(tmp_path, ["names", "--apply"])
    assert second.exit_code == 0
    assert "rewrote 0 row(s)" in second.output
    assert _names(tmp_path) == after_first


def test_the_sweep_says_so_when_there_is_nothing_to_repair(tmp_path: Path) -> None:
    _seed(tmp_path, [_LEGACY[2]])
    result = _cli(tmp_path, ["names"])
    assert result.exit_code == 0
    assert "nothing to repair" in result.output


def test_the_sweep_never_downcases_a_registry_name_that_matches_its_slug(tmp_path: Path) -> None:
    """A curated name differing from its slug ONLY in capitalisation is already the employer's.

    `companies_named_by_slug` matches `name == slug` case-INSENSITIVELY — deliberately, because
    that is the fact about how `companies add` wrote the row. But that also admits every registry
    row whose catalog name is the slug re-capitalised, and `derive_employer_name` cannot
    re-capitalise: it returns the lowercase slug token. Comparing exactly therefore planned a
    REWRITE for each of them.

    RED against an exact `derived != row.name`: this read `{'greenhouse:openai': 'openai'}` — and
    on the live fleet that comparison planned 129 rewrites where only 31 rows are actually named
    after a host, downcasing 100 curated names. `companies.name` reaches the delivered folder and
    the résumé filename, so it is a visible regression.
    """
    _seed(tmp_path, [
        # Capitalisation is the ONLY difference from the slug, exactly like a registry row.
        {"name": "OpenAi", "provider": "greenhouse", "slug": "openai",
         "source": "registry", "watched": True},
        # A genuine host-named row, so the sweep is proven still to do its job in the same run.
        {"name": "careers.acme.test", "provider": "eightfold", "slug": "careers.acme.test",
         "source": "user", "watched": True},
    ])
    result = _cli(tmp_path, ["names", "--apply"])
    assert result.exit_code == 0, result.output
    assert _names(tmp_path) == {
        "greenhouse:openai": "OpenAi",
        "eightfold:careers.acme.test": "acme",
    }, "a name that differs from its slug only in case is already the employer's"
    assert "rewrote 1 row(s)" in result.output.replace("\n", " ")


def test_the_sweep_still_matches_a_host_named_row_after_its_slug_was_sliced(tmp_path: Path) -> None:
    """A Workday facet slice (T71) is an IN-PLACE slug edit that appends `#group=descriptor`.
    Applied to a row an earlier `add` named after its slug, the name is now the slug WITHOUT
    its fragment, so an exact `name == slug` test no longer sees the row and it stays
    host-named — and `companies.name` reaches the delivered folder and the résumé filename.

    RED before the fix: the sweep reported "nothing to repair" and left the host as the name.
    """
    _seed(tmp_path, [
        {"name": "acme.wd1.myworkdayjobs.com/acme/Acme_External_Site", "provider": "workday",
         "slug": "acme.wd1.myworkdayjobs.com/acme/Acme_External_Site#jobFamilyGroup=Technology",
         "source": "user", "watched": True},
    ])
    result = _cli(tmp_path, ["names", "--apply"])
    assert result.exit_code == 0, result.output
    assert _names(tmp_path) == {
        "workday:acme.wd1.myworkdayjobs.com/acme/Acme_External_Site#jobFamilyGroup=Technology":
            "acme",
    }
