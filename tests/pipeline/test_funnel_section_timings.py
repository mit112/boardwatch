"""T361, end to end. Each funnel section's collection and each queue_sync part is timed, printed
under its tail line, and (for the funnel) kept in the artifact, on a pass that scanned and on one
that did not.

Pinned through `run_pipeline` because the wiring is the risk: `collect_run_funnel` timing a
section the runner never prints, or the runner printing a section the artifact never carries,
would each pass a test of one half alone.
"""

from __future__ import annotations

import json
import re
from io import StringIO
from pathlib import Path

import httpx
import pytest
import respx
from rich.console import Console

from boardwatch.core.settings import load_settings
from boardwatch.pipeline import funnel_writer, runner
from boardwatch.pipeline.funnel_writer import SectionClock
from boardwatch.providers.registry import build_providers
from boardwatch.store.db import get_engine
from tests.pipeline.test_pipeline_run import SEEDED_BOARDS, _ready

_GH = build_providers()["greenhouse"]

# The sections `collect_run_funnel` times, in the order it reads them. `delivered_direct` is
# absent: it exists only when the direct-share attribution measured something.
_COLLECTED = [
    "identity",
    "corpus",
    "abstain",
    "dedup",
    "sources",
    "tailored_artifacts",
    "projected_lineage",
    "lane_captures",
    "apply_lane",
    "buried",
    "marked_applied",
    "unattributed_evaluations",
    "lead_provenance",
    "stub_postings",
    "record_corpus_counts",
    "manifest",
    "store_size",
    "build",
]
_SCAN_ONLY = ["watched_never_complete", "watched_stale_complete"]


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


def _run(env: Path, tmp_path: Path, *, skip_scan: bool) -> tuple[runner.PipelineSummary, str]:
    _ready(env)
    settings = load_settings(data_dir=env)
    output = StringIO()
    summary = runner.run_pipeline(
        get_engine(env), settings, console=Console(file=output, width=200),
        out_root=tmp_path / "apps", resume_path=settings.config_dir / "resume.yaml",
        skip_scan=skip_scan, queue_root=tmp_path / "queue",
    )
    return summary, output.getvalue()


def _names(payload: dict[str, object]) -> list[str]:
    rows = payload["section_timings"]
    assert isinstance(rows, list)
    return [row["name"] for row in rows if row["name"] != "delivered_direct"]


def _part_lines(log: str, tail: str) -> list[str]:
    """The part names printed under one tail stage, in print order. Four-space indent, so the
    stage lines themselves (two spaces) never match."""
    return re.findall(rf"^    tail {tail}\.(\S+) → \S+ UTC · \d+\.\d{{3}}s$", log, re.MULTILINE)


def test_a_pass_that_did_not_scan_times_every_section_in_the_artifact_and_the_log(
    env: Path, tmp_path: Path
) -> None:
    summary, log = _run(env, tmp_path, skip_scan=True)

    assert summary.funnel is not None
    payload = json.loads(summary.funnel.json_path.read_text(encoding="utf-8"))
    assert payload["scan"]["ran"] is False
    assert _names(payload) == ["board_coverage", *_COLLECTED]
    assert all(row["seconds"] >= 0 for row in payload["section_timings"])
    # The log carries the same sections, then the write the artifact cannot contain.
    printed = _part_lines(log, "funnel")
    assert [name for name in printed if name != "delivered_direct"] == [
        "board_coverage", *_COLLECTED, "write",
    ]
    assert "## Wall clock" in summary.funnel.markdown_path.read_text(encoding="utf-8")
    assert "Collection cost by funnel section" in summary.funnel.markdown_path.read_text(
        encoding="utf-8"
    )


@pytest.mark.usefixtures("no_real_sleep")
def test_a_pass_that_scanned_adds_the_two_standing_board_reads_and_still_reconciles(
    env: Path, tmp_path: Path
) -> None:
    _ready(env)
    settings = load_settings(data_dir=env)
    output = StringIO()
    with respx.mock:
        for slug in SEEDED_BOARDS:
            respx.get(_GH.board_url(slug)).mock(
                return_value=httpx.Response(200, content=b'{"jobs": []}')
            )
        summary = runner.run_pipeline(
            get_engine(env), settings, console=Console(file=output, width=200),
            out_root=tmp_path / "apps", resume_path=settings.config_dir / "resume.yaml",
            queue_root=tmp_path / "queue",
        )

    assert summary.funnel is not None
    payload = json.loads(summary.funnel.json_path.read_text(encoding="utf-8"))
    assert payload["scan"]["ran"] is True
    assert _names(payload) == ["board_coverage", *_SCAN_ONLY, *_COLLECTED]
    assert payload["reconciles"] is True, payload["cross_checks"]
    assert [name for name in _part_lines(output.getvalue(), "funnel") if name != "delivered_direct"] == [
        "board_coverage", *_SCAN_ONLY, *_COLLECTED, "write",
    ]


def test_a_pass_that_did_not_scan_reconciles_with_every_cross_check_agreeing(
    env: Path, tmp_path: Path
) -> None:
    summary, _log = _run(env, tmp_path, skip_scan=True)

    assert summary.funnel is not None
    payload = json.loads(summary.funnel.json_path.read_text(encoding="utf-8"))
    assert payload["reconciles"] is True, payload["cross_checks"]
    assert all(check["agrees"] for check in payload["cross_checks"])


def test_the_queue_sync_prints_its_parts_under_its_tail_line(env: Path, tmp_path: Path) -> None:
    _summary, log = _run(env, tmp_path, skip_scan=True)

    assert _part_lines(log, "queue_sync") == ["owner_name", "reconcile", "rows", "sync"]
    # Parts print BEFORE the stage's own boundary line, which closes the stage.
    assert log.index("tail queue_sync.sync") < log.index("  tail queue_sync →")


def test_a_section_that_raises_is_still_recorded_before_the_error_propagates() -> None:
    """A read that fails 5 minutes in must still say where the 5 minutes went."""
    seen: list[str] = []
    clock = SectionClock(lambda row: seen.append(row.name))

    with pytest.raises(RuntimeError), clock.time("dedup"):
        raise RuntimeError("boom")

    assert [row.name for row in clock.rows] == ["dedup"] == seen


def test_a_section_records_the_elapsed_time_the_clock_measured(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A controlled clock: every `perf_counter` read advances 1.5 s, so each section that opens
    and closes once measures exactly 1.5 s, in the artifact and in the log line. A timer that
    records 0.0, or a different span, cannot pass."""
    ticks = iter(float(n) * 1.5 for n in range(100_000))
    monkeypatch.setattr(funnel_writer, "perf_counter", lambda: next(ticks))

    summary, log = _run(env, tmp_path, skip_scan=True)

    assert summary.funnel is not None
    rows = json.loads(summary.funnel.json_path.read_text(encoding="utf-8"))["section_timings"]
    collected = {row["name"]: row["seconds"] for row in rows if row["name"] != "board_coverage"}
    # `build` spans the builder's own clock reads (the store-size read sits inside it), so it is
    # the one section whose span is not a single tick pair.
    assert {k: v for k, v in collected.items() if k != "build"} == {
        name: 1.5 for name in collected if name != "build"
    }
    assert collected["dedup"] == collected["store_size"] == 1.5
    assert re.search(r"^    tail funnel\.dedup → \S+ UTC · 1\.500s$", log, re.MULTILINE)


class _FlakyLog(Console):
    """A log that refuses every timing line, as a closed or full log file would."""

    def print(self, *objects: object, **kwargs: object) -> None:  # type: ignore[override]
        if objects and str(objects[0]).startswith("    tail "):
            raise OSError("log is gone")
        super().print(*objects, **kwargs)  # type: ignore[arg-type]


def test_a_log_that_refuses_timing_lines_costs_neither_the_funnel_nor_the_queue(
    env: Path, tmp_path: Path
) -> None:
    _ready(env)
    settings = load_settings(data_dir=env)
    summary = runner.run_pipeline(
        get_engine(env), settings, console=_FlakyLog(file=StringIO(), width=200),
        out_root=tmp_path / "apps", resume_path=settings.config_dir / "resume.yaml",
        skip_scan=True, queue_root=tmp_path / "queue",
    )

    assert summary.funnel is not None, summary.errors
    assert summary.funnel.json_path.is_file() and summary.funnel.markdown_path.is_file()
    assert [
        e for e in summary.errors if "funnel artifact" in e or "delivery queue" in e
    ] == []
    assert summary.tailored, "guard: the run must deliver a lead for the queue to hold"
    assert list((tmp_path / "queue").glob("*/details.json")) or any(
        (tmp_path / "queue").iterdir()
    ), "the queue was not synced"
