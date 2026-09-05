"""T39: the empty-complete guard (T15) reaches the funnel artifact and the run log.

`ApplyResult.empty_complete_guarded` (T15) was unobservable on a pipeline run: it reached only
`boardwatch scan`'s own console line (`cli/scan_cmd.py`), never `PipelineSummary`, the funnel's
`scan` block, or `boardwatch run`'s own log — an operator reading a nightly run's artifacts could
not tell a degraded provider or a renamed board slug apart from an ordinary day.

Pinned END TO END, on the `test_scan_board_split.py` precedent one file over: a test that hands
`ScanContext` its own `empty_complete_guarded` tuple would go green against a pipeline that never
threads `ScanSummary.empty_complete_guarded` through `PipelineSummary` at all.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx
from rich.console import Console

from boardwatch.core.settings import load_settings
from boardwatch.pipeline.runner import run_pipeline
from boardwatch.providers.registry import build_providers
from boardwatch.store.db import get_engine
from tests.pipeline.test_pipeline_run import SEEDED_BOARDS, _cli, _ready

_GH = build_providers()["greenhouse"]

# `_ready` leaves "acme2" watched with one OPEN posting already stored (seeded directly, not
# through a scan) and "acme" watched with none. An empty `{"jobs": []}` answer is therefore the
# T15 shape for "acme2" ONLY — a `complete` snapshot listing nothing for a board that still holds
# an open posting — and ordinary for "acme", which never held one to lose. Asserting the guarded
# list equals `["acme2"]` exactly (never `["acme", "acme2"]`) is the null control: "acme" is the
# same run, the same empty body, and must NOT trip the guard.
_EMPTY_BODY = b'{"jobs": []}'


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


def test_the_scan_block_names_the_board_the_guard_fired_on(env: Path, tmp_path: Path) -> None:
    _ready(env)
    settings = load_settings(data_dir=env)
    with respx.mock:
        for slug in SEEDED_BOARDS:
            respx.get(_GH.board_url(slug)).mock(
                return_value=httpx.Response(200, content=_EMPTY_BODY)
            )
        # No `liveness_prober`: mirrors `test_scan_board_split.py` — the shortlisted acme2
        # posting's stored URL is never mocked, and this test is about the guard, not liveness.
        summary = run_pipeline(
            get_engine(env),
            settings,
            console=Console(quiet=True),
            out_root=tmp_path / "apps",
            resume_path=settings.config_dir / "resume.yaml",
        )

    assert summary.scan_empty_complete_guarded == ["acme2"], (
        "guard: acme2's seeded open posting did not trip the guard, so this test proves nothing: "
        f"{summary.scan_empty_complete_guarded}"
    )
    assert summary.funnel is not None
    # Read off the WRITTEN artifact, not `summary` again — CLAUDE.md's rule that a component's
    # self-report is not verification, the same reason `test_scan_board_split.py` reads
    # `funnel.json_path` rather than asserting on `ScanContext` directly.
    scan = json.loads(summary.funnel.json_path.read_text(encoding="utf-8"))["scan"]
    assert scan["empty_complete_guarded"] == ["acme2"]
    # The guard changes what `apply_board` DOES, never what status it reports: the guarded board
    # is still `complete`, so both boards land there.
    assert scan["boards_complete"] == 2


def test_the_run_log_names_the_board_the_guard_fired_on(env: Path, tmp_path: Path) -> None:
    _ready(env)
    with respx.mock:
        for slug in SEEDED_BOARDS:
            respx.get(_GH.board_url(slug)).mock(
                return_value=httpx.Response(200, content=_EMPTY_BODY)
            )
        # `--no-check-liveness`: the shortlisted acme2 posting's stored URL
        # (`https://example.test/j`) is not mocked, and this test is about the guard's
        # visibility on the run log, not the liveness stage.
        result = _cli(env, ["run", "--no-check-liveness", "--out", str(tmp_path / "apps")])

    assert result.exit_code == 0, result.output
    assert "1 empty-complete guarded (acme2)" in result.output, result.output
