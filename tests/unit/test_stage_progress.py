"""D-658: checkpoint cadence and stage-local pace, independently hand calculated."""

import io

import pytest
from rich.console import Console

from boardwatch.pipeline.progress import ProgressUpdate, StageProgress


def _reporter(
    total: int, *, every: int = 25
) -> tuple[StageProgress, list[float], list[ProgressUpdate], io.StringIO]:
    now = [0.0]
    updates: list[ProgressUpdate] = []
    stream = io.StringIO()
    reporter = StageProgress(
        "example", total, console=Console(file=stream, width=200), every=every,
        clock=lambda: now[0], on_update=updates.append,
    )
    return reporter, now, updates, stream


def test_zero_total_has_no_eta() -> None:
    progress, _, updates, stream = _reporter(0)
    progress.finish()
    assert [u.done for u in updates] == [0, 0]
    assert all(u.remaining_seconds is None for u in updates)
    assert "0/0" in stream.getvalue()
    assert "ETA" not in stream.getvalue()


def test_no_eta_before_first_completed_unit() -> None:
    progress, now, updates, stream = _reporter(10)
    now[0] = 120
    progress.advance(0)
    assert updates[-1].elapsed_seconds == 120
    assert updates[-1].remaining_seconds is None
    assert "ETA" not in stream.getvalue()


def test_eta_uses_elapsed_pace() -> None:
    progress, now, updates, stream = _reporter(10, every=2)
    now[0] = 120
    progress.advance(2, item="Acme")
    assert updates[-1].remaining_seconds == 480
    assert "ETA 8.0 min" in stream.getvalue()
    assert "Acme" in stream.getvalue()


def test_unit_cadence_resets_after_each_line() -> None:
    progress, _, updates, _ = _reporter(10, every=3)
    progress.advance(2)
    assert len(updates) == 1
    progress.advance()
    assert [u.done for u in updates] == [0, 3]
    progress.advance(2)
    assert len(updates) == 2
    progress.advance()
    assert [u.done for u in updates] == [0, 3, 6]


def test_sixty_seconds_only_emits_at_a_checkpoint() -> None:
    progress, now, updates, _ = _reporter(100)
    now[0] = 59
    progress.advance()
    assert len(updates) == 1
    now[0] = 60
    assert len(updates) == 1
    progress.advance()
    assert [u.done for u in updates] == [0, 2]
    now[0] = 119
    progress.advance()
    assert len(updates) == 2
    now[0] = 120
    progress.advance()
    assert [u.done for u in updates] == [0, 2, 4]


def test_finish_forces_a_line_without_inventing_completed_work() -> None:
    progress, now, updates, _ = _reporter(10)
    now[0] = 30
    progress.advance(2)
    assert len(updates) == 1
    progress.finish()
    assert [u.done for u in updates] == [0, 2]
    assert updates[-1].finished is True
    assert updates[-1].remaining_seconds == 120


def test_no_console_is_silent_but_still_reports_snapshots(capsys: pytest.CaptureFixture[str]) -> None:
    updates: list[ProgressUpdate] = []
    progress = StageProgress("example", 2, every=1, on_update=updates.append)
    progress.advance()
    progress.finish()
    assert [u.done for u in updates] == [0, 1, 1]
    assert updates[-1].finished
    assert capsys.readouterr().out == ""
