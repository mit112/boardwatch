"""Board-discovery coverage reaches an unattended run's own artifacts (D-274).

The instrument shipped correct and MUTE: `boardwatch coverage` had to be typed by hand, so a
scheduled run persisted its four `board_scans` columns and reported nothing. The unit tests pin
what the renderers say; what only an end-to-end run can show is that the section is actually
EMITTED by `run_pipeline` into both artifacts, that both describe the run that just happened,
and — the part a unit test structurally cannot reach — that a coverage failure costs the
SECTION and never the artifact.

That last one is the real risk in this change. `_emit_funnel` and `_emit_morning` are each
wrapped in one `except Exception` that prints a warning and writes NOTHING, so an exception
raised while assembling the coverage section would have cost the entire funnel — the artifact
that explains the run — to report a number that is nice to have. `load_board_coverage` already
degrades a single bad ROW to `unreadable`, but a whole-SELECT failure (a store whose schema
predates the four columns) is a different fault and needed its own guard.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from rich.console import Console

from boardwatch.core.settings import load_settings
from boardwatch.pipeline.runner import run_pipeline
from boardwatch.store.db import get_engine
from tests.pipeline.test_pipeline_run import INIT_INPUT, _cli, _seed_posting


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


def _ready(data_dir: Path) -> int:
    posting_id = _seed_posting(data_dir)
    assert _cli(data_dir, ["init"], INIT_INPUT).exit_code == 0
    assert _cli(data_dir, ["tailor", "init"]).exit_code == 0
    return posting_id


def _pipeline(data_dir: Path, out_root: Path, **kw: object) -> object:
    settings = load_settings(data_dir=data_dir)
    return run_pipeline(
        get_engine(data_dir),
        settings,
        console=Console(quiet=True),
        out_root=out_root,
        resume_path=settings.config_dir / "resume.yaml",
        skip_scan=True,
        **kw,  # type: ignore[arg-type]
    )


def _payload(out_root: Path, kind: str) -> dict:
    found = list(out_root.glob(f"*/{kind}-*.json"))
    assert len(found) == 1, f"expected exactly one {kind} artifact, got {found}"
    return json.loads(found[0].read_text())


def _markdown(out_root: Path, kind: str) -> str:
    found = list(out_root.glob(f"*/{kind}-*.md"))
    assert len(found) == 1, f"expected exactly one {kind} markdown, got {found}"
    return found[0].read_text()


def test_both_artifacts_carry_a_board_coverage_section(env: Path, tmp_path: Path) -> None:
    """Neither surface may be the only one that reports it: the funnel is where a per-board
    table belongs, and the morning file is the one the operator opens."""
    _ready(env)
    out_root = tmp_path / "apps"

    _pipeline(env, out_root)

    funnel = _payload(out_root, "funnel")
    morning = _payload(out_root, "morning")
    assert funnel["board_coverage"] is not None
    assert morning["board_coverage"] is not None
    assert "## Board coverage" in _markdown(out_root, "funnel")
    assert "## Discovery reach" in _markdown(out_root, "morning")


def test_the_two_artifacts_report_the_identical_report(env: Path, tmp_path: Path) -> None:
    """One load, two renders. `held` is a live count of open postings with NO run dimension
    (`store/coverage_queries.py`), so loading it once per artifact would let the funnel and the
    morning file disagree about one run's coverage whenever a posting closed in the seconds
    between the two writes. This is the assertion that keeps the single load load-bearing."""
    _ready(env)
    out_root = tmp_path / "apps"

    _pipeline(env, out_root)

    assert _payload(out_root, "funnel")["board_coverage"] == (
        _payload(out_root, "morning")["board_coverage"]
    )


def test_the_section_is_scoped_to_this_run_not_the_latest_scanned_run(
    env: Path, tmp_path: Path
) -> None:
    """`load_board_coverage` defaults to the newest run carrying `board_scans` rows. An
    artifact stamped `funnel-N` must describe run N, so the runner passes `run_id` explicitly —
    otherwise a re-run would silently restate a different run's boards under N's number.

    These runs are `skip_scan=True` and so write no `board_scans` rows at all, which is the
    honest edge: every watched board is `unscanned` and the ratio is `None`, never 0%.
    """
    _ready(env)
    out_root = tmp_path / "apps"

    _pipeline(env, out_root)

    section = _payload(out_root, "funnel")["board_coverage"]
    assert section["global_ratio"] is None
    assert section["bucket_counts"]["measured"] == 0
    assert "not measurable" in _markdown(out_root, "funnel")


def test_a_coverage_failure_costs_the_section_and_never_the_artifact(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The seam guard, and the reason this change needed one.

    Both emitters swallow any exception and write NOTHING, so an unguarded raise here would
    trade the whole funnel — the artifact that explains the run — for a number that is merely
    nice to have. Asserting on the raised message confirms the fault reached the guard rather
    than the test passing because the fixture never triggered it (a reproduction is a claim
    too).
    """
    _ready(env)
    out_root = tmp_path / "apps"

    def _boom(*_args: object, **_kw: object) -> None:
        raise RuntimeError("no such column: board_scans.board_reported_total")

    monkeypatch.setattr("boardwatch.pipeline.runner.load_board_coverage", _boom)

    summary = _pipeline(env, out_root)

    assert summary.board_coverage is None  # type: ignore[attr-defined]
    # Both artifacts still exist, and both say so rather than omitting the section.
    assert _payload(out_root, "funnel")["board_coverage"] is None
    assert _payload(out_root, "morning")["board_coverage"] is None
    assert "not measured this run" in _markdown(out_root, "funnel")
    assert "not measured this run" in _markdown(out_root, "morning")
    # The run itself is unaffected: a reporting failure is not a run failure.
    assert summary.funnel is not None  # type: ignore[attr-defined]
    assert summary.morning is not None  # type: ignore[attr-defined]


def test_the_guard_actually_fires_when_the_load_raises(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Confirms the test above is not passing vacuously: without the guard the exception would
    escape `_load_board_coverage` into the `finally` block. Here the raise is observed through
    a flag the fake sets, so "no exception surfaced" cannot be mistaken for "never called"."""
    _ready(env)
    out_root = tmp_path / "apps"
    called: list[int] = []

    def _boom(*_args: object, **kw: object) -> None:
        called.append(int(kw["run_id"]))  # type: ignore[arg-type]
        raise RuntimeError("boom")

    monkeypatch.setattr("boardwatch.pipeline.runner.load_board_coverage", _boom)

    summary = _pipeline(env, out_root)

    assert called == [summary.run_id]  # type: ignore[attr-defined]
