"""Board-discovery coverage reaches an unattended run's own artifacts (D-274).

The instrument shipped correct and MUTE: `boardwatch coverage` had to be typed by hand, so a
scheduled run persisted its four `board_scans` columns and reported nothing. The unit tests pin
what the renderers say; what only an end-to-end run can show is that the section is actually
EMITTED by `run_pipeline` into both artifacts, and that a coverage failure costs the SECTION and
never the artifact.

**Why several tests here drive the loader through a spy rather than through seeded rows.** Every
run in this file uses `skip_scan=True`, so the store holds **zero `board_scans` rows** and a real
load returns one all-`unscanned` board with every number `None`. Two independent loads of that
store are byte-identical, which makes an equality assertion between the two artifacts unable to
fail — it would pass just as well if each artifact loaded its own report. The store cannot be
seeded around this either: the coverage row must belong to the run's OWN `run_id`, which does not
exist until the run that writes the artifacts is already underway. So the single-load property is
pinned the only way it can be made falsifiable — a spy that returns DIFFERENT data on each call,
plus a call count. A second load then makes the two artifacts disagree and both assertions fail.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from rich.console import Console

from boardwatch.core.settings import load_settings
from boardwatch.pipeline.runner import run_pipeline
from boardwatch.reports.board_coverage import BoardCoverage
from boardwatch.store.coverage_queries import load_board_coverage as real_load
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


def _measured(ratio: float) -> list[BoardCoverage]:
    """One `measured` board whose ratio is whatever the caller asks for."""
    held = int(round(1000 * ratio))
    return [
        BoardCoverage(
            company_id=1,
            name="Acme",
            provider="greenhouse",
            bucket="measured",
            held=held,
            board_reported_total=1000,
            board_enumerated=1000,
            detail_deferred=0,
            shortfall=1000 - held,
            ratio=ratio,
        )
    ]


def test_both_artifacts_carry_a_board_coverage_section(env: Path, tmp_path: Path) -> None:
    """Neither surface may be the only one that reports it: the funnel is where a per-board
    table belongs, and the morning file is the one the operator opens."""
    _ready(env)
    out_root = tmp_path / "apps"

    _pipeline(env, out_root)

    assert _payload(out_root, "funnel")["board_coverage"] is not None
    assert _payload(out_root, "morning")["board_coverage"] is not None
    assert "## Board coverage" in _markdown(out_root, "funnel")
    assert "## Discovery reach" in _markdown(out_root, "morning")


def test_the_report_is_loaded_exactly_once_per_run(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE single-load guard, in its falsifiable form.

    `held` is a live count of open postings with NO run dimension, so two loads seconds apart can
    legitimately differ and one run's two artifacts must not disagree. Reverting `_emit_morning`
    to load its own report makes this count 2.
    """
    _ready(env)
    out_root = tmp_path / "apps"
    calls: list[int | None] = []

    def _spy(conn: object, *, run_id: int | None = None) -> list[BoardCoverage]:
        calls.append(run_id)
        return real_load(conn, run_id=run_id)  # type: ignore[arg-type]

    monkeypatch.setattr("boardwatch.pipeline.runner.load_board_coverage", _spy)

    _pipeline(env, out_root)

    assert len(calls) == 1, f"expected exactly one coverage load per run, got {len(calls)}"


def test_a_second_load_would_make_the_two_artifacts_disagree(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same invariant from the other side, and the reason a plain equality assertion is not
    enough: with zero `board_scans` rows a real report is all-`unscanned` and identical on every
    load, so equality alone passes even if each artifact loads separately.

    Here each call returns a DIFFERENT ratio. One load ⇒ both artifacts show 50.0%. Two loads ⇒
    the morning file shows 90.0% and both assertions below fail.
    """
    _ready(env)
    out_root = tmp_path / "apps"
    ratios = iter((0.5, 0.9))

    def _spy(_conn: object, *, run_id: int | None = None) -> list[BoardCoverage]:
        return _measured(next(ratios))

    monkeypatch.setattr("boardwatch.pipeline.runner.load_board_coverage", _spy)

    _pipeline(env, out_root)

    funnel = _payload(out_root, "funnel")["board_coverage"]
    morning = _payload(out_root, "morning")["board_coverage"]
    assert funnel["global_ratio"] == 0.5
    assert funnel == morning


def test_a_measured_board_renders_its_ratio_into_both_artifacts(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every other end-to-end run here exercises only the all-`unscanned` path, where no ratio is
    published at all. This one drives a real `measured` board through both renderers, so the
    number actually reaches the page the operator reads."""
    _ready(env)
    out_root = tmp_path / "apps"
    monkeypatch.setattr(
        "boardwatch.pipeline.runner.load_board_coverage",
        lambda _conn, **_kw: _measured(0.5),
    )

    _pipeline(env, out_root)

    assert _payload(out_root, "funnel")["board_coverage"]["global_ratio"] == 0.5
    assert "50.0%" in _markdown(out_root, "funnel")
    assert "50.0%" in _markdown(out_root, "morning")
    assert "greenhouse:Acme" in _markdown(out_root, "funnel")


def test_the_load_is_scoped_to_this_run_not_the_latest_scanned_run(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`load_board_coverage` defaults to the newest run holding any `board_scans` rows. An
    artifact stamped `funnel-N` must describe run N, so the runner passes `run_id` explicitly.

    Asserted on the observed argument rather than on the output, because with zero `board_scans`
    rows the default and the explicit value produce the same all-`unscanned` report — dropping
    `run_id=run_id` would not change a single number. Here it records `None` and fails.
    """
    _ready(env)
    out_root = tmp_path / "apps"
    seen: list[int | None] = []

    def _spy(conn: object, *, run_id: int | None = None) -> list[BoardCoverage]:
        seen.append(run_id)
        return real_load(conn, run_id=run_id)  # type: ignore[arg-type]

    monkeypatch.setattr("boardwatch.pipeline.runner.load_board_coverage", _spy)

    summary = _pipeline(env, out_root)

    assert seen == [summary.run_id]  # type: ignore[attr-defined]


def test_a_run_with_no_scan_rows_reports_not_measurable_never_zero(
    env: Path, tmp_path: Path
) -> None:
    """The honest edge, and the real shape of a `--no-scan` run: no board wrote a scan row, so
    every watched board is `unscanned`, nothing is measurable, and the ratio is `None`. It must
    never render as 0%, which would claim the boards were read and found empty."""
    _ready(env)
    out_root = tmp_path / "apps"

    _pipeline(env, out_root)

    section = _payload(out_root, "funnel")["board_coverage"]
    assert section["global_ratio"] is None
    assert section["bucket_counts"]["measured"] == 0
    assert "not measurable" in _markdown(out_root, "funnel")
    assert "0.0%" not in _markdown(out_root, "funnel")


def test_a_coverage_failure_costs_the_section_and_never_the_artifact(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The seam guard, and the reason this change needed one.

    Both emitters swallow any exception and write NOTHING, so an unguarded raise here would trade
    the whole funnel — the artifact that explains the run — for a number that is merely nice to
    have. Removing `_load_board_coverage`'s `try` makes this raise out of `run_pipeline`.
    """
    _ready(env)
    out_root = tmp_path / "apps"
    called: list[int] = []

    def _boom(*_args: object, **kw: object) -> None:
        called.append(int(kw["run_id"]))  # type: ignore[arg-type]
        raise RuntimeError("no such column: board_scans.board_reported_total")

    monkeypatch.setattr("boardwatch.pipeline.runner.load_board_coverage", _boom)

    summary = _pipeline(env, out_root)

    # The fault reached the guard — a reproduction is a claim too, so this is observed, not
    # inferred from the absence of an exception.
    assert called == [summary.run_id]  # type: ignore[attr-defined]
    assert summary.board_coverage is None  # type: ignore[attr-defined]
    # Both artifacts still exist, and both say so rather than omitting the section.
    assert _payload(out_root, "funnel")["board_coverage"] is None
    assert _payload(out_root, "morning")["board_coverage"] is None
    assert "not measured this run" in _markdown(out_root, "funnel")
    assert "not measured this run" in _markdown(out_root, "morning")
    # The run itself is unaffected: a reporting failure is not a run failure.
    assert summary.funnel is not None  # type: ignore[attr-defined]
    assert summary.morning is not None  # type: ignore[attr-defined]
