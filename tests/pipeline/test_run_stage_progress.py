"""T286 owner checkpoints: attempted work, durable batches and the actual render slate."""

from __future__ import annotations

import io
from pathlib import Path
from types import ModuleType, SimpleNamespace

import httpx
import pytest
import respx
from rich.console import Console
from sqlalchemy import Engine, func, select

from boardwatch.cli import top_cmd
from boardwatch.cli.context import build_context
from boardwatch.core.settings import Settings, load_settings
from boardwatch.eligibility import preflight
from boardwatch.extract import preflight as extraction
from boardwatch.llm import gate_judge
from boardwatch.pipeline import death_probe, liveness, runner
from boardwatch.pipeline.progress import ProgressUpdate, StageProgress
from boardwatch.scan import coordinator
from boardwatch.store import tables
from boardwatch.store.queries import insert_run
from tests.pipeline.test_eligibility_flow import _install
from tests.pipeline.test_gate_stage import _arm_gate, _ready, _seed
from tests.pipeline.test_lane_split_before_tailor import _fake_ok, _seed_slate
from tests.pipeline.test_lane_stage import StubLane
from tests.pipeline.test_scan import _add_company
from tests.unit.test_death_probe import _company, _error, _posting, _store
from tests.unit.test_preflight import _seed_company, _seed_posting


def _observe(monkeypatch: pytest.MonkeyPatch, owner: ModuleType) -> list[ProgressUpdate]:
    updates: list[ProgressUpdate] = []

    def create(stage: str, total: int, **kwargs: object) -> StageProgress:
        return StageProgress(
            stage, total, console=Console(quiet=True), every=1, on_update=updates.append
        )

    monkeypatch.setattr(owner, "StageProgress", create, raising=False)
    return updates


@pytest.mark.parametrize("workers", [1, 2], ids=["serial", "parallel"])
def test_eligibility_progress_follows_parent_commit_across_batches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, workers: int
) -> None:
    data_dir = _install(tmp_path, monkeypatch)
    ctx = build_context(data_dir)
    observed: list[tuple[int, int]] = []

    def read_committed(update: ProgressUpdate) -> None:
        with ctx.engine.connect() as conn:
            persisted = conn.scalar(select(func.count()).select_from(tables.eligibility_evaluations))
        observed.append((update.done, int(persisted)))

    def create(stage: str, total: int, **kwargs: object) -> StageProgress:
        return StageProgress(
            stage, total, console=Console(quiet=True), every=1, on_update=read_committed
        )

    monkeypatch.setattr(preflight, "StageProgress", create, raising=False)
    monkeypatch.setattr(preflight, "BATCH_SIZE", 2)
    stats = preflight.run_eligibility(
        ctx.engine, ctx.settings, Console(quiet=True), workers=workers, parallel_threshold=1
    )
    assert stats.evaluated == 6
    assert observed == [(0, 0), (2, 2), (4, 4), (6, 6), (6, 6)]


def test_extraction_progress_follows_batch_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _store(tmp_path)
    company = _seed_company(engine)
    for n in range(3):
        _seed_posting(engine, company, str(n), f"Python posting {n}.")
    observed: list[tuple[int, int]] = []

    def read_committed(update: ProgressUpdate) -> None:
        with engine.connect() as conn:
            count = conn.scalar(select(func.count()).select_from(tables.extractions))
        observed.append((update.done, int(count)))

    def create(stage: str, total: int, **kwargs: object) -> StageProgress:
        return StageProgress(
            stage, total, console=Console(quiet=True), every=1, on_update=read_committed
        )

    monkeypatch.setattr(extraction, "StageProgress", create, raising=False)
    monkeypatch.setattr(extraction, "BATCH_SIZE", 2)
    extraction.run_preflight(
        engine, Settings(data_dir=tmp_path / "data", config_dir=tmp_path), Console(quiet=True)
    )
    assert observed == [(0, 0), (2, 2), (3, 3), (3, 3)]


@pytest.mark.parametrize("apply_fails", [False, True], ids=["fetch", "apply"])
def test_scan_failure_advances_attempted_progress(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, apply_fails: bool
) -> None:
    _add_company(engine, "acme")
    updates = _observe(monkeypatch, coordinator)
    if apply_fails:
        def fail_apply(*args: object, **kwargs: object) -> None:
            raise RuntimeError("synthetic write failure")
        monkeypatch.setattr(coordinator, "apply_board", fail_apply)
    with respx.mock:
        respx.get("https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true").mock(
            return_value=httpx.Response(500)
        )
        result = coordinator.run_scan(
            engine, Settings(data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1)
        )
    assert result.failed == 1
    assert [u.done for u in updates] == [0, 1, 1]


def test_unknown_death_probe_advances_after_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _store(tmp_path)
    company = _company(engine, slug="unknown", watched=False)
    posting_id = _posting(engine, company)
    updates = _observe(monkeypatch, death_probe)
    result = death_probe.sweep_unwatched_deaths(
        engine, prober=_error, listing_prober=None, run_id=insert_run(engine),
        budget=10, company_budget=10, ttl_hours=24,
    )
    assert result.unknown == 1
    with engine.connect() as conn:
        assert conn.scalar(select(tables.postings.c.last_death_probe_at).where(
            tables.postings.c.id == posting_id
        )) is not None
    assert [u.done for u in updates] == [0, 1, 1]


def test_shortlist_unknown_probe_counts_as_attempted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _store(tmp_path)
    posting_id = _posting(engine, _company(engine, slug="unknown", watched=True))
    updates = _observe(monkeypatch, liveness)
    result = liveness.check_leads(engine, [posting_id], prober=_error)
    assert result[posting_id].verdict == "unknown"
    assert [u.done for u in updates] == [0, 1, 1]


def test_failed_gate_batch_counts_all_request_items(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    data_dir = tmp_path / "data"
    _ready(data_dir)
    ids = [_seed(data_dir, slug=f"gate{i}") for i in range(3)]
    _arm_gate(data_dir, batch_size=2)
    monkeypatch.setattr(gate_judge, "_judge_batch", lambda *a, **kw: (None, "offline", []))
    updates = _observe(monkeypatch, gate_judge)
    _, result = gate_judge.run_gate_stage(
        build_context(data_dir).engine, load_settings(data_dir=data_dir),
        [SimpleNamespace(posting_id=i) for i in ids], run_id=None,
    )
    assert result.failed_open_batches == 2
    assert [u.done for u in updates] == [0, 2, 3, 3]
    assert all(u.total == 3 for u in updates)


def test_lane_failure_counts_as_attempted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _store(tmp_path)
    monkeypatch.setitem(
        runner.LANE_FACTORIES, "stub", lambda ctx: StubLane([], raises=RuntimeError("offline"))
    )
    updates = _observe(monkeypatch, runner)
    _, errors = runner._fetch_lanes(
        engine, Settings(data_dir=tmp_path / "data", config_dir=tmp_path, lanes_enabled=["stub"]),
        insert_run(engine),
    )
    assert len(errors) == 1
    assert [u.done for u in updates] == [0, 1, 1]


def test_tailor_announces_actual_render_total_on_mixed_slate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    data_dir = tmp_path / "data"
    _ready(data_dir)
    _seed_slate(data_dir)
    monkeypatch.setattr("boardwatch.reports.tailor._default_runner", _fake_ok)
    settings = load_settings(data_dir=data_dir)
    stream = io.StringIO()
    updates = _observe(monkeypatch, runner)
    result = runner.run_pipeline(
        build_context(data_dir).engine, settings, console=Console(file=stream, width=200),
        out_root=tmp_path / "apps", resume_path=settings.config_dir / "resume.yaml", skip_scan=True,
    )
    assert result.fatal is None
    assert sum(lead.pdf_built for lead in result.tailored) == 3
    assert "tailor: 5 leads · 3 renderable · 2 review-only" in stream.getvalue()
    tailor = [u for u in updates if u.stage == "tailor"]
    assert [u.done for u in tailor] == [0, 1, 2, 3, 3]
    assert all(u.total == 3 for u in tailor)


def test_ranking_announces_corpus_size_and_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    data_dir = tmp_path / "data"
    _ready(data_dir)
    _seed_slate(data_dir)
    ctx = build_context(data_dir)
    updates = _observe(monkeypatch, top_cmd)
    ranked = top_cmd.rank_open_postings(ctx.engine, ctx.settings, output_console=Console(quiet=True))
    assert ranked.considered == 5
    assert [u.done for u in updates] == [0, 5, 5]
    assert all(u.total == 5 for u in updates)
