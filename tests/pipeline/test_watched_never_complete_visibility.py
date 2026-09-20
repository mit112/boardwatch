"""T117: the watched boards no liveness owner can retire reach the funnel artifact.

Two owners retire a dead posting. Absence-based closure (`scan/apply.py::apply_board`) only
reaches `_process_missing` under a `complete` snapshot; the death sweep's
`unreachable_by_the_scanner` predicate is `status == 'open' AND watched IS FALSE`, so a watched
company is excluded from it by construction. A watched board whose scans are never `complete`
therefore has NEITHER — and every provider demotes a whole board to `partial` on a single
per-posting parse error, so this is fleet-wide. Measured on the live store 2026-09-20: 8 watched
companies had never had a `complete` scan and 16,510 open postings sat under them, 6.3% of the
open corpus, with nothing in any artifact counting the population.

`boards_partial` was already published per run — that is the EVENT. What was missing is the
STANDING population, which is why the 16,510 went unnoticed.

Pinned END TO END, on the `test_scan_board_split.py` / `test_empty_complete_guard_visibility.py`
precedent: a test that hands `ScanContext` its own tuple would go green against a pipeline that
never reads the store for it.

Report-only. Nothing here closes, probes or sweeps anything differently — see
`tests/unit/test_death_probe.py::test_a_watched_companys_posting_is_never_probed` and
`::test_a_watched_companys_listing_is_never_asked`, the controls that stay green.
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
from tests.pipeline.test_pipeline_run import SEEDED_BOARDS, _ready
from tests.pipeline.test_scan_board_split import _BAD_JOB, _GOOD_JOB, _PARTIAL, _body, _watch

_GH = build_providers()["greenhouse"]


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


def _scan_block(env: Path, tmp_path: Path, **kw: object) -> dict[str, object]:
    settings = load_settings(data_dir=env)
    summary = run_pipeline(
        get_engine(env),
        settings,
        console=Console(quiet=True),
        out_root=tmp_path / "apps",
        resume_path=settings.config_dir / "resume.yaml",
        **kw,  # type: ignore[arg-type]
    )
    assert summary.funnel is not None
    # Read off the WRITTEN artifact rather than `summary`: a component's self-report is not
    # verification, the same path `test_empty_complete_guard_visibility.py` takes.
    payload = json.loads(summary.funnel.json_path.read_text(encoding="utf-8"))
    return {
        "scan": payload["scan"],
        "markdown": summary.funnel.markdown_path.read_text(encoding="utf-8"),
    }


def test_the_scan_block_names_the_watched_board_that_has_never_scanned_complete(
    env: Path, tmp_path: Path
) -> None:
    """One partial board and two complete ones in a single run.

    The two `complete` boards are the discriminating control: they are watched, they are in the
    same run, and they must NOT appear — without them the counter could be "every watched
    board" and still look right.
    """
    _ready(env)
    _watch(env, _PARTIAL)

    with respx.mock:
        for slug in SEEDED_BOARDS:
            respx.get(_GH.board_url(slug)).mock(
                return_value=httpx.Response(200, content=_body(_GOOD_JOB))
            )
        respx.get(_GH.board_url(_PARTIAL)).mock(
            return_value=httpx.Response(200, content=_body(_GOOD_JOB, _BAD_JOB))
        )
        out = _scan_block(env, tmp_path)

    scan = out["scan"]
    assert isinstance(scan, dict)
    assert scan["boards_complete"] == 2, "control: the two seeded boards must scan complete"
    assert scan["boards_partial"] == 1
    assert scan["watched_never_complete"] == [
        {"provider": "greenhouse", "board_slug": _PARTIAL, "open_postings": 1}
    ]
    markdown = out["markdown"]
    assert isinstance(markdown, str)
    assert f"`greenhouse:{_PARTIAL}` (1)" in markdown


def test_a_run_that_did_not_scan_reports_not_measured_rather_than_an_empty_list(
    env: Path, tmp_path: Path
) -> None:
    """`--no-scan` over a store that HAS one: `null`, never `[]`.

    `_ready` leaves `acme2` watched, holding one open posting, with no `board_scans` row at all
    — so the population is genuinely non-empty here and an empty list would be a false
    all-clear rather than a missing measurement. Same direction as `scan.fetch_cost` (D-330).
    """
    _ready(env)

    out = _scan_block(env, tmp_path, skip_scan=True)

    scan = out["scan"]
    assert isinstance(scan, dict)
    assert scan["watched_never_complete"] is None
    markdown = out["markdown"]
    assert isinstance(markdown, str)
    assert "skipped (`--no-scan`)" in markdown
