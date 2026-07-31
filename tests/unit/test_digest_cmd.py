"""digest renders the window and advances the cursor; --peek renders and does not."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.reports.digest import summarize_events
from boardwatch.store.app_state import get_digest_cursor, set_digest_cursor
from boardwatch.store.db import get_engine
from boardwatch.store.events import append_event
from boardwatch.store.queries import insert_run

runner = CliRunner()


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


def _run(data_dir: Path, args: list[str]):
    return runner.invoke(app, ["--data-dir", str(data_dir), *args])


def _cursor(data_dir: Path) -> int:
    with get_engine(data_dir).connect() as conn:
        return get_digest_cursor(conn)


def test_empty_digest_says_so_and_leaves_the_cursor_at_zero(env: Path) -> None:
    result = _run(env, ["digest"])
    assert result.exit_code == 0
    assert "nothing new since your last digest" in result.stdout
    assert _cursor(env) == 0


def test_digest_advances_the_cursor(env: Path, seeded_events) -> None:
    seed = seeded_events(env)
    assert _run(env, ["digest"]).exit_code == 0
    assert _cursor(env) == seed.max_event_id


def test_peek_renders_but_does_not_advance(env: Path, seeded_events) -> None:
    seeded_events(env)
    result = _run(env, ["digest", "--peek"])
    assert result.exit_code == 0
    assert "alpha" in result.stdout
    assert _cursor(env) == 0


def test_a_second_digest_is_empty(env: Path, seeded_events) -> None:
    seeded_events(env)
    assert _run(env, ["digest"]).exit_code == 0
    second = _run(env, ["digest"])
    assert "nothing new since your last digest" in second.stdout


def test_closed_postings_render_as_a_count_only(env: Path, seeded_events) -> None:
    seeded_events(env)
    result = _run(env, ["digest", "--peek"])
    assert "2 closed" in result.stdout
    assert "epsilon" not in result.stdout


def test_reopened_section_renders(env: Path, seeded_events) -> None:
    """A8: the reopened section must exist, not just be tolerated."""
    seeded_events(env)
    result = _run(env, ["digest", "--peek"])
    assert result.exit_code == 0
    assert "gamma" in result.stdout
    assert "Reopened" in result.stdout


def test_revised_section_renders(env: Path, seeded_events) -> None:
    """A8: the revised section must exist, not just be tolerated."""
    seeded_events(env)
    result = _run(env, ["digest", "--peek"])
    assert result.exit_code == 0
    assert "delta" in result.stdout
    assert "Updated" in result.stdout


def test_two_interleaved_digests_cursor_only_moves_forward(
    env: Path, seeded_events
) -> None:
    """A1: overlapping digests from two connections cannot rewind the cursor."""
    seed = seeded_events(env)
    engine = get_engine(env)
    with engine.connect() as first, engine.connect() as second:
        # Both reads happen before either write: the overlap shape A1 protects.
        first_summary = summarize_events(first, get_digest_cursor(first))
        second_summary = summarize_events(second, get_digest_cursor(second))
        assert first_summary.max_event_id == seed.max_event_id
        assert second_summary.max_event_id == seed.max_event_id
        with engine.begin() as write_a:
            set_digest_cursor(write_a, first_summary.max_event_id)
        with engine.begin() as write_b:
            set_digest_cursor(write_b, second_summary.max_event_id)
    assert _cursor(env) == seed.max_event_id


def test_event_after_query_is_picked_up_by_next_window(env: Path, seeded_events) -> None:
    """A1: an event committed after the read is reported by the next window, not skipped."""
    seed = seeded_events(env)
    engine = get_engine(env)
    with engine.connect() as conn:
        summary = summarize_events(conn, get_digest_cursor(conn))
        assert summary.max_event_id == seed.event_ids["zeta"]
        # A new event commits before the cursor write lands.
        run_id = insert_run(engine)
        with engine.begin() as late:
            append_event(late, seed.posting_ids["alpha"], "revised", run_id)
        # The cursor advances only as far as what was actually read.
        with engine.begin() as cursor_write:
            set_digest_cursor(cursor_write, summary.max_event_id)
    assert _cursor(env) == seed.event_ids["zeta"]
    # The late event id is above the cursor, so the next digest reports it.
    result = _run(env, ["digest", "--peek"])
    assert result.exit_code == 0
    assert "alpha" in result.stdout
    assert "Updated" in result.stdout
