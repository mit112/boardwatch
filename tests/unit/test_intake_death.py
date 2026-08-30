"""F4 cross-run intake-death detector.

Each test that expects the detector to FIRE is paired with the wrong-version it must
reject, noted inline, so none of these pass vacuously.
"""

from pathlib import Path

import pytest
from sqlalchemy import Engine, insert

from boardwatch.core.clock import utcnow
from boardwatch.notify.intake_death import INTAKE_DEATH_WINDOW, check_intake_death
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path)
    ensure_schema(eng)
    return eng


def _seed_run(engine: Engine, new_count: int | None) -> int:
    """Insert one run with the given net-new count (``None`` = scan never recorded)."""
    with engine.begin() as conn:
        values: dict[str, object] = {"started_at": utcnow()}
        if new_count is not None:
            values["new_count"] = new_count
        return int(conn.execute(insert(tables.runs).values(**values)).inserted_primary_key[0])


def test_fires_when_the_window_of_scanning_runs_all_read_zero(engine: Engine) -> None:
    # Rejects a version that drops the zero-check and fires whenever there is enough history.
    ids = [_seed_run(engine, 0) for _ in range(3)]
    alert = check_intake_death(engine, window=3)
    assert alert is not None
    assert "0 net-new" in alert
    for run_id in ids:
        assert str(run_id) in alert


def test_stays_silent_when_the_newest_run_had_intake(engine: Engine) -> None:
    _seed_run(engine, 0)
    _seed_run(engine, 0)
    _seed_run(engine, 5)  # newest
    assert check_intake_death(engine, window=3) is None


def test_stays_silent_when_an_older_run_in_the_window_had_intake(engine: Engine) -> None:
    # Rejects `all(... != 0)` in place of `any(...)`: that mutant would fire here.
    _seed_run(engine, 5)  # oldest but still inside the window
    _seed_run(engine, 0)
    _seed_run(engine, 0)  # newest
    assert check_intake_death(engine, window=3) is None


def test_abstains_when_history_is_shorter_than_the_window(engine: Engine) -> None:
    # Rejects a version without the `len(rows) < window` guard, which would fire on a fresh store.
    _seed_run(engine, 0)
    _seed_run(engine, 0)
    assert check_intake_death(engine, window=3) is None


def test_skips_runs_whose_scan_never_recorded_a_count(engine: Engine) -> None:
    # A NULL-new_count run (a `top --no-record` phantom) carries no intake signal. The window
    # is the last three SCANNING runs, so the interleaved NULL is skipped and the three real
    # zeros still fire. Rejects a version that drops the `new_count IS NOT NULL` filter: it
    # would pull the NULL into the newest three and go silent (`None != 0` is truthy).
    _seed_run(engine, 0)
    _seed_run(engine, 0)
    _seed_run(engine, None)  # phantom, newer than the zeros
    _seed_run(engine, 0)  # newest
    alert = check_intake_death(engine, window=3)
    assert alert is not None
    assert "0 net-new" in alert


def test_default_window_is_three(engine: Engine) -> None:
    # Pins the shipped default behaviourally: exactly three zeros fire, exactly two abstain,
    # both called without the `window` argument. Rejects any change to INTAKE_DEATH_WINDOW.
    assert INTAKE_DEATH_WINDOW == 3
    _seed_run(engine, 0)
    _seed_run(engine, 0)
    assert check_intake_death(engine) is None
    _seed_run(engine, 0)
    assert check_intake_death(engine) is not None
