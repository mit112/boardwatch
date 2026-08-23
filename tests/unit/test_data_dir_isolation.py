"""The suite must not be able to reach the real data dir. Pins `tests/conftest.py`'s
`_never_reach_the_real_data_dir` autouse fixture.

Written because the suite migrated Mit's production database on 2026-08-23. One test —
`test_config_cmd.py::test_the_new_scalar_keys_round_trip_through_set_and_show` — invoked the CLI
without `--data-dir` while only `BOARDWATCH_CONFIG_DIR` was set, so `load_settings()` fell
through to `default_data_dir()`, resolved the live ~1.4 GB store, and `ensure_schema` ran
`alembic upgrade head` against it. The daily driver then executes `main`'s tree, finds no such
revision and exits 1 — D-279's incident, reproduced by any branch that adds a migration.

Fixing that one test would have closed that one leak. These pin the GUARDRAIL instead, because
the next leak will be in a test nobody has written yet.
"""

from pathlib import Path

from platformdirs import user_data_dir

from boardwatch.core.settings import default_data_dir, load_settings


def test_the_default_data_dir_is_never_the_real_one_under_test() -> None:
    """Delete the autouse fixture and this fails: `default_data_dir()` returns the live store.

    Asserted against `platformdirs.user_data_dir` rather than a hard-coded
    `~/Library/Application Support/boardwatch`, so it holds on Linux and Windows CI too — the
    real path differs per platform but the function that produces it does not.
    """
    real = Path(user_data_dir("boardwatch"))
    assert default_data_dir() != real, (
        "BOARDWATCH_DATA_DIR is not pinned to a scratch dir, so any test reaching "
        "load_settings() without --data-dir would run alembic against the production store"
    )


def test_load_settings_without_a_data_dir_resolves_somewhere_disposable() -> None:
    """The specific call the leaking test made: `load_settings(data_dir=None)`.

    `default_data_dir()` above is the unit; this is the path that actually reached the store,
    and it is worth pinning separately because `load_settings` can override the environment
    from a `config.toml` `data_dir` key — the one route the fixture does NOT close.
    """
    resolved = load_settings().data_dir
    assert resolved != Path(user_data_dir("boardwatch")), (
        "load_settings() resolved the real data dir; if BOARDWATCH_DATA_DIR is pinned, the "
        "likely cause is a data_dir key in a real config.toml, which outranks the variable"
    )
