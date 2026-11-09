"""F4 cross-run intake-death detector.

Each test that expects the detector to FIRE is paired with the wrong-version it must
reject, noted inline, so none of these pass vacuously.
"""

from pathlib import Path

import pytest
from sqlalchemy import Engine, insert, update

from boardwatch.core.clock import utcnow
from boardwatch.notify.intake_death import INTAKE_DEATH_WINDOW, check_intake_death
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import RUN_KIND_PREFIX, set_state


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path)
    ensure_schema(eng)
    return eng


def _seed_run(
    engine: Engine, new_count: int | None, *, kind: str | None = "delivery",
    incremental: bool = False,
) -> int:
    """Insert one run with the given net-new count (``None`` = scan never recorded).

    `kind` is the D-680 purpose marker; ``None`` writes none (an untagged, pre-D-680 row).
    """
    with engine.begin() as conn:
        values: dict[str, object] = {"started_at": utcnow(), "incremental": incremental}
        if new_count is not None:
            values["new_count"] = new_count
        run_id = int(conn.execute(insert(tables.runs).values(**values)).inserted_primary_key[0])
        if kind is not None:
            set_state(conn, f"{RUN_KIND_PREFIX}{run_id}", kind)
        return run_id


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


# ---- run purpose (D-680): which rows may form the window, and which count as intake

NON_DELIVERY = ["scan", "maintenance", None, "unsupported"]


@pytest.mark.parametrize("kind", NON_DELIVERY)
def test_non_delivery_zeros_cannot_manufacture_an_alert(engine: Engine, kind: str | None) -> None:
    # A bare `boardwatch scan` (kind scan, non-incremental, counted) or an untagged pre-D-680
    # row reads zero because an earlier scan took the postings; three of them are not a stall.
    # Rejects a window that does not read the run purpose.
    for _ in range(3):
        _seed_run(engine, 0, kind=kind)
    assert check_intake_death(engine, window=3) is None


@pytest.mark.parametrize("kind", NON_DELIVERY)
def test_non_delivery_zero_cannot_displace_a_delivery_from_the_window(
    engine: Engine, kind: str | None
) -> None:
    # Three zero deliveries are a real stall. A newer manual scan that also read zero must
    # neither hide it nor be named in it. Rejects a window that includes the newer row.
    ids = [_seed_run(engine, 0) for _ in range(3)]
    _seed_run(engine, 0, kind=kind)
    alert = check_intake_death(engine, window=3)
    assert alert is not None
    assert "(runs " + ", ".join(str(i) for i in reversed(ids)) + ")" in alert


@pytest.mark.parametrize("kind", NON_DELIVERY)
def test_a_non_delivery_zero_is_not_one_of_the_window_runs(
    engine: Engine, kind: str | None
) -> None:
    # Two deliveries plus a bare-scan zero are NOT three delivery runs: abstain.
    _seed_run(engine, 0)
    _seed_run(engine, 0, kind=kind)
    _seed_run(engine, 0)
    assert check_intake_death(engine, window=3) is None


def test_historical_corpus_measurement_still_proves_a_delivery(engine: Engine) -> None:
    # Pre-D-680 pipeline runs carry no marker; a corpus measurement is their delivery proof
    # (78 live rows). Rejects reading only the explicit marker.
    for _ in range(3):
        rid = _seed_run(engine, 0, kind=None)
        with engine.begin() as conn:
            conn.execute(update(tables.runs).where(tables.runs.c.id == rid).values(corpus_open=0))
    assert check_intake_death(engine, window=3) is not None


@pytest.mark.parametrize("kind", ["scan", None])
def test_a_positive_incremental_scan_since_the_window_is_intake(
    engine: Engine, kind: str | None
) -> None:
    # D-670: the daytime `scan --provider ...` finds the postings first. Both the tagged scan
    # (run 1013) and the untagged ones (10 live rows) must escape. Rejects an escape restricted
    # to a purpose, which would silence the detector on today's untagged history.
    for _ in range(3):
        _seed_run(engine, 0)
    _seed_run(engine, 40, kind=kind, incremental=True)
    assert check_intake_death(engine, window=3) is None


@pytest.mark.parametrize("kind", ["scan", None])
def test_a_positive_bare_scan_since_the_window_is_intake(engine: Engine, kind: str | None) -> None:
    # A non-incremental non-delivery scan is outside the window, so the escape has to see it:
    # it found postings. Rejects keeping the escape restricted to incremental rows.
    _seed_run(engine, 0)
    _seed_run(engine, 0)
    _seed_run(engine, 0)
    _seed_run(engine, 40, kind=kind)
    assert check_intake_death(engine, window=3) is None


def test_a_positive_scan_before_the_window_is_not_intake(engine: Engine) -> None:
    # The escape is "since the window's oldest row": older intake does not excuse a stall.
    _seed_run(engine, 40, kind="scan", incremental=True)
    for _ in range(3):
        _seed_run(engine, 0)
    assert check_intake_death(engine, window=3) is not None
