"""One configuration snapshot per run: `resolve_projection_run`.

Freezing the résumé pool alone is not enough. `select` scores through the taxonomy and the
equivalence table, and persona application reads the registry, so a run that holds one pool and
reloads the rest can still build two leads under different rules — a stale *transformation*, which
no digest or hash over the pool can see.

The posting seam is seeded straight through the store, reusing
`tests/projection/test_projection_posting.py`'s own `_engine`/`_seed` helpers rather than a second
copy of them; the bundle side comes from `projection_env` (tests/projection/conftest.py). The two
have to be combined by hand here — `_settings` in that module points `config_dir` at its own
`cfg/`, and this suite needs the `config_dir` the bundle fixture approved a stamp in.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert

from boardwatch.cli import projection_cmd
from boardwatch.core.settings import Settings
from boardwatch.extract.taxonomy import Taxonomy
from boardwatch.projection import posting as posting_mod
from boardwatch.projection import run as run_mod
from boardwatch.projection.errors import ProjectionError, ProjectionIssue
from boardwatch.projection.posting import posting_context
from boardwatch.projection.run import ProjectionRunContext, resolve_projection_run
from boardwatch.projection.scoring import DEFAULT_SCORER_ID, SCORERS
from boardwatch.store.tables import extractions
from tests.projection.conftest import ProjectionEnv
from tests.projection.test_projection_posting import NOW, _engine, _seed

AS_OF = date(2026, 8, 17)

#: An engine_version no `load_taxonomy` can ever produce (versions are sha256 hex), so an
#: extraction row keyed to it is reachable ONLY through an injected taxonomy object.
INJECTED_VERSION = "injected"
#: Disjoint from `_seed`'s own default skills, so "the injected taxonomy was used" and "a freshly
#: loaded one was used" cannot produce the same `jd_skills`.
INJECTED_SKILLS = ("Kotlin",)


def _settings_over(env: ProjectionEnv, tmp_path: Path) -> Settings:
    """Settings whose `config_dir` is the fixture's approved config dir, with a database beside
    it. `resolve_projection_run` reads the stamp, the declaration and the shell out of
    `settings.config_dir`, so it must be the directory `projection_env` wrote them into."""
    return Settings(data_dir=tmp_path / "run-data", config_dir=env.config_dir)


def _resolve(env: ProjectionEnv, engine: Engine, settings: Settings, **over: object) -> object:
    kwargs: dict[str, object] = {
        "bundle_root": env.bundle_root,
        "declaration_path": env.declaration,
        "scorer_id": DEFAULT_SCORER_ID,
        "as_of": AS_OF,
    }
    kwargs.update(over)
    return resolve_projection_run(engine, settings, **kwargs)  # type: ignore[arg-type]


# -- load once ------------------------------------------------------------------------


def test_the_run_context_loads_the_taxonomy_exactly_once(
    projection_env: ProjectionEnv, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two postings, one taxonomy load.

    Counting the CALL is the assertion, not comparing two returned objects: two loads of an
    unchanged file are equal (and `re.compile`'s own cache even makes their patterns identical),
    so no comparison of results can detect the defect this guards.

    Both bound names are patched, and both are load-bearing:

    * `run_mod.load_taxonomy` — `run.py` does `from boardwatch.extract.taxonomy import
      load_taxonomy`, so patching `boardwatch.extract.taxonomy` itself would leave that
      already-bound name untouched and count nothing.
    * `posting_mod.load_taxonomy` with `raising=False` — after this change `posting.py` holds no
      such name at all, and that ABSENCE is the property under test. Setting it anyway means a
      regression that re-adds a per-call `load_taxonomy(...)` to `posting.py` resolves through the
      patched module `__dict__` at call time and is counted, failing this test, instead of passing
      unseen.
    """
    settings = _settings_over(projection_env, tmp_path)
    engine = _engine(settings)
    first_id = _seed(engine, settings, slug="acme")
    second_id = _seed(engine, settings, slug="globex")

    calls: list[Path] = []
    real = run_mod.load_taxonomy

    def counting(config_dir: Path) -> Taxonomy:
        calls.append(config_dir)
        return real(config_dir)

    monkeypatch.setattr(run_mod, "load_taxonomy", counting)
    monkeypatch.setattr(posting_mod, "load_taxonomy", counting, raising=False)

    ctx = _resolve(projection_env, engine, settings)
    assert isinstance(ctx, ProjectionRunContext)
    posting_context(engine, settings, first_id, taxonomy=ctx.taxonomy)
    posting_context(engine, settings, second_id, taxonomy=ctx.taxonomy)

    assert len(calls) == 1
    assert calls == [settings.config_dir]


def test_posting_context_uses_the_injected_taxonomy(
    projection_env: ProjectionEnv, tmp_path: Path
) -> None:
    """A taxonomy whose `version` only one seeded extraction row carries proves the injected
    object is the one used, rather than a freshly loaded one.

    Keying on `version` rather than on `patterns` is deliberate: `jd_skills_for` looks the
    extraction row up BY `taxonomy.version`, so a `posting_context` that reloaded the taxonomy
    would read the row `_seed` wrote for the real version and come back with its skills instead.
    """
    settings = _settings_over(projection_env, tmp_path)
    engine = _engine(settings)
    posting_id = _seed(engine, settings, skills=("Python", "JavaScript"))
    with engine.begin() as conn:
        conn.execute(
            insert(extractions).values(
                posting_id=posting_id,
                content_hash="h1",
                kind="taxonomy",
                engine_version=INJECTED_VERSION,
                json={"skills": list(INJECTED_SKILLS)},
                created_at=NOW,
            )
        )

    empty = Taxonomy(patterns=(), version=INJECTED_VERSION, source="test")
    ctx = posting_context(engine, settings, posting_id, taxonomy=empty)

    assert ctx.jd_skills == frozenset(INJECTED_SKILLS)
    # Non-vacuity: the skills a reloaded taxonomy WOULD have produced are absent.
    assert ctx.jd_skills.isdisjoint({"Python", "JavaScript"})


# -- transformation versions ----------------------------------------------------------


def test_the_run_context_records_every_transformation_version(
    projection_env: ProjectionEnv, tmp_path: Path
) -> None:
    settings = _settings_over(projection_env, tmp_path)
    engine = _engine(settings)
    ctx = _resolve(projection_env, engine, settings)
    assert isinstance(ctx, ProjectionRunContext)

    assert ctx.taxonomy.version and ctx.table.version and ctx.persona_registry_version
    assert ctx.scorer_id == DEFAULT_SCORER_ID
    assert ctx.scorer is SCORERS[DEFAULT_SCORER_ID]
    assert ctx.as_of == AS_OF
    # The pool really was projected, not left as a placeholder.
    assert ctx.pool.projection_digest and ctx.pool.bundle_digest


def test_a_non_default_scorer_id_is_honoured(
    projection_env: ProjectionEnv, tmp_path: Path
) -> None:
    """Non-vacuity for the test above: `scorer`/`scorer_id` track the argument rather than being
    pinned to the default."""
    settings = _settings_over(projection_env, tmp_path)
    engine = _engine(settings)
    other = next(name for name in sorted(SCORERS) if name != DEFAULT_SCORER_ID)
    ctx = _resolve(projection_env, engine, settings, scorer_id=other)
    assert isinstance(ctx, ProjectionRunContext)
    assert ctx.scorer_id == other
    assert ctx.scorer is SCORERS[other]


# -- refusals -------------------------------------------------------------------------


def test_an_unknown_scorer_is_a_typed_refusal_before_anything_is_read(
    projection_env_unpromoted_bundle: ProjectionEnv, tmp_path: Path
) -> None:
    """The scorer check is the cheapest refusal, so it must come first: this environment's bundle
    has never been promoted, so a resolve that read the bundle before validating `--scorer` would
    surface `BUNDLE_UNREADABLE` and the operator would never learn the scorer name was wrong."""
    env = projection_env_unpromoted_bundle
    settings = _settings_over(env, tmp_path)
    engine = _engine(settings)
    with pytest.raises(ProjectionError) as exc:
        _resolve(env, engine, settings, scorer_id="not-a-real-scorer")
    assert exc.value.violation.issue is ProjectionIssue.UNKNOWN_SCORER
    assert "not-a-real-scorer" in exc.value.violation.message
    # Derived from the live mapping, not a hand-copied list.
    for name in SCORERS:
        assert name in exc.value.violation.message


def test_a_bundle_failure_propagates_uncaught(
    projection_env_unapproved: ProjectionEnv, tmp_path: Path
) -> None:
    """`resolve_projection_run` classifies nothing of its own: a preflight that folded its
    failures into one bucket could not be reused by a caller that wants to map them differently.
    The owner-gate refusal must arrive as the typed issue `project_pool` raised."""
    env = projection_env_unapproved
    settings = _settings_over(env, tmp_path)
    engine = _engine(settings)
    with pytest.raises(ProjectionError) as exc:
        _resolve(env, engine, settings)
    assert exc.value.violation.issue is ProjectionIssue.MISSING_PROJECTION_APPROVAL


# -- the one default ------------------------------------------------------------------


def test_the_default_scorer_id_is_a_registered_scorer() -> None:
    """A default naming an unregistered scorer would make every unattended run refuse."""
    assert DEFAULT_SCORER_ID in SCORERS


def test_the_cli_scorer_default_is_the_module_level_default() -> None:
    """`cli/projection_cmd.py` cannot IMPORT `DEFAULT_SCORER_ID` at module level: its
    `SCORER_OPTION` is evaluated at import time, `projection.scoring` reaches
    `boardwatch.store.tables` through `extract.taxonomy`, and `profile_bundle_cmd` imports
    `projection_cmd` — so that import would break
    `tests/profile_bundle/test_profile_bundle_cli.py::test_the_command_module_imports_no_store_module`.
    This assertion is the link instead: the option's default is READ here and compared, so the two
    cannot drift even though the CLI still spells the value.
    """
    assert projection_cmd.SCORER_OPTION.default == DEFAULT_SCORER_ID
