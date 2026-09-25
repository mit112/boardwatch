"""T133 — one whole-run lease: `run_pipeline` holds `scan.lock` from before its first write to its
last, so a contender is refused having written nothing.

Contention is driven deterministically: a hook patched into run A's post-scan eligibility stage
(`_regroup`, after ranking and before any shortlist disposition) runs contender B synchronously,
on the same thread. An "other process" is a SEPARATE `FileLock` object on the same path, which
contends on POSIX exactly as a second process does. No timing sleeps.
"""

from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from filelock import FileLock, Timeout
from rich.console import Console
from sqlalchemy import Engine, select, update

import boardwatch.pipeline.runner as runner_mod
import boardwatch.scan.coordinator as coordinator
from boardwatch.core.clock import utcnow
from boardwatch.core.settings import Settings, load_settings
from boardwatch.pipeline.runner import run_pipeline
from boardwatch.scan.coordinator import ScanLockHeldError, run_scan
from boardwatch.store import tables
from boardwatch.store.db import get_engine
from boardwatch.store.queries import insert_run
from tests.pipeline.test_pipeline_run import _GH, HEALTHY_BODY, SEEDED_BOARDS, _ready


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    # Patched by name where it is bound (see `_queue_lock`'s docstring): POSIX already asks
    # once, and this keeps the contender fail-fast on Windows too.
    monkeypatch.setattr(coordinator, "RECLAIM_WINDOW_SECONDS", 0.0)
    return tmp_path / "data"


def _runs(engine: Engine) -> list[tuple[Any, ...]]:
    with engine.connect() as conn:
        rows = conn.execute(
            select(
                tables.runs.c.id,
                tables.runs.c.status,
                tables.runs.c.finished_at,
                tables.runs.c.errors_json,
            ).order_by(tables.runs.c.id)
        ).all()
    return [tuple(row) for row in rows]


def _backdate_unfinished_runs(engine: Engine) -> None:
    """Make every unfinished row look older than `reap_stale_after_hours`, so a reap shows."""
    with engine.begin() as conn:
        conn.execute(
            update(tables.runs)
            .where(tables.runs.c.finished_at.is_(None))
            .values(started_at=utcnow() - timedelta(days=3))
        )


def _pipeline(engine: Engine, settings: Settings, out_root: Path, **kw: Any) -> Any:
    return run_pipeline(
        engine,
        settings,
        console=Console(quiet=True),
        out_root=out_root,
        resume_path=settings.config_dir / "resume.yaml",
        **kw,
    )


def _count_schema_steps(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Count every `ensure_schema` either pipeline path reaches, through the names they bind."""
    calls: list[int] = []
    for module in (runner_mod, coordinator):
        real = module.ensure_schema

        def spy(engine: Engine, _real: Callable[[Engine], None] = real) -> None:
            calls.append(1)
            _real(engine)

        monkeypatch.setattr(module, "ensure_schema", spy)
    return calls


def _contend_after_scan(
    env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contender: Callable[[Engine, Settings], object],
) -> None:
    """Run A with its scan on; in A's post-scan stage, run `contender` and assert it was refused
    and wrote nothing — no run row, no reap of A's (backdated, so reapable) row, no schema step.
    """
    _ready(env)
    settings = load_settings(data_dir=env)
    engine = get_engine(env)
    schema_steps = _count_schema_steps(monkeypatch)
    real_regroup = runner_mod._regroup
    observed: list[tuple[object, list[tuple[Any, ...]], list[tuple[Any, ...]], int]] = []
    fired: list[bool] = []

    def barrier(*args: Any, **kw: Any) -> Any:
        # Fires once, flagged BEFORE the contender runs: a contender that is not refused reaches
        # this same stage itself, and must pass straight through rather than recurse.
        if not fired:
            fired.append(True)
            _backdate_unfinished_runs(engine)  # A's own live row now looks stale
            before = _runs(engine)
            steps_before = len(schema_steps)
            outcome: object
            try:
                outcome = contender(engine, settings)
            except ScanLockHeldError as exc:
                outcome = exc
            observed.append((outcome, before, _runs(engine), len(schema_steps) - steps_before))
        return real_regroup(*args, **kw)

    monkeypatch.setattr(runner_mod, "_regroup", barrier)
    with respx.mock:
        for slug in SEEDED_BOARDS:
            respx.get(_GH.board_url(slug)).mock(
                return_value=httpx.Response(200, content=HEALTHY_BODY)
            )
        _pipeline(engine, settings, tmp_path / "a")

    assert observed, "run A never reached its post-scan stage, so this test proves nothing"
    outcome, before, after, steps = observed[0]
    assert isinstance(outcome, ScanLockHeldError), (
        f"the contender was not refused during run A's post-scan stage: {outcome!r}"
    )
    assert after == before, "the refused contender changed the runs table (row or reap)"
    assert steps == 0, "the refused contender ran a schema step"


@pytest.mark.usefixtures("no_real_sleep")
def test_a_second_pipeline_is_refused_while_the_first_is_past_its_scan(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _contend_after_scan(
        env, tmp_path, monkeypatch,
        lambda engine, settings: _pipeline(engine, settings, tmp_path / "b"),
    )


@pytest.mark.usefixtures("no_real_sleep")
def test_a_no_scan_pipeline_is_refused_while_the_first_is_past_its_scan(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _contend_after_scan(
        env, tmp_path, monkeypatch,
        lambda engine, settings: _pipeline(engine, settings, tmp_path / "b", skip_scan=True),
    )


@pytest.mark.usefixtures("no_real_sleep")
def test_a_standalone_scan_is_refused_while_a_pipeline_is_past_its_scan(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _contend_after_scan(env, tmp_path, monkeypatch, run_scan)


def test_a_contended_pipeline_reaps_nothing(env: Path, tmp_path: Path) -> None:
    """The reap sits behind the lease: a contender about to be refused must not have reaped."""
    _ready(env)
    settings = load_settings(data_dir=env)
    engine = get_engine(env)
    insert_run(engine)
    _backdate_unfinished_runs(engine)
    before = _runs(engine)
    holder = FileLock(str(settings.data_dir / "scan.lock"))
    holder.acquire()
    try:
        with pytest.raises(ScanLockHeldError):
            _pipeline(engine, settings, tmp_path / "apps")
    finally:
        holder.release()

    assert _runs(engine) == before, "a contended pipeline reaped a stale row before refusing"


@pytest.mark.parametrize("error", [RuntimeError("stage broke"), KeyboardInterrupt()])
def test_the_lease_is_released_when_the_pipeline_raises(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: BaseException
) -> None:
    _ready(env)
    settings = load_settings(data_dir=env)
    engine = get_engine(env)
    reached: list[bool] = []
    lock_path = settings.data_dir / "scan.lock"

    def boom(*_args: object, **_kw: object) -> None:
        # The lease must be HELD at the raising stage, or "released afterwards" is vacuous: a
        # `--no-scan` run held no lock at all before T133, and the probe below would pass on it.
        with pytest.raises(Timeout):
            FileLock(str(lock_path)).acquire(blocking=False)
        reached.append(True)
        raise error

    monkeypatch.setattr(runner_mod, "_regroup", boom)
    with pytest.raises(type(error)):
        _pipeline(engine, settings, tmp_path / "apps", skip_scan=True)
    assert reached, "the pipeline never reached the raising stage, so this test proves nothing"

    probe = FileLock(str(lock_path))
    probe.acquire(blocking=False)  # raises Timeout if the lease leaked
    probe.release()
    assert not lock_path.with_name("scan.lock.meta").exists(), "the lease sidecar leaked"
