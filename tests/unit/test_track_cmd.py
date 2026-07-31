"""track is the funnel surface. It records what the user did; it never applies for them."""

from pathlib import Path

import pytest
from sqlalchemy import select
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.store.db import get_engine
from boardwatch.store.funnel_queries import job_id_for_posting, list_funnel
from boardwatch.store.queries import current_posting_versions
from boardwatch.store.tables import applications

runner = CliRunner()


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


def _run(data_dir: Path, args: list[str]):
    return runner.invoke(app, ["--data-dir", str(data_dir), *args])


def _funnel(data_dir: Path, status: str | None = None):
    with get_engine(data_dir).connect() as conn:
        return list_funnel(conn, status=status)


def _first_posting_id(data_dir: Path, seeded_events) -> int:
    """The `alpha` posting id, looked up rather than assumed."""
    return seeded_events(data_dir).posting_ids["alpha"]


def test_add_starts_tracking_at_interested(env: Path, seeded_events) -> None:
    posting_id = _first_posting_id(env, seeded_events)
    result = _run(env, ["track", "add", str(posting_id)])
    assert result.exit_code == 0
    rows = _funnel(env)
    assert len(rows) == 1
    assert rows[0].status == "interested"
    assert rows[0].title == "alpha"


def test_add_accepts_an_explicit_status(env: Path, seeded_events) -> None:
    posting_id = _first_posting_id(env, seeded_events)
    assert _run(env, ["track", "add", str(posting_id), "--status", "applied"]).exit_code == 0
    rows = _funnel(env)
    assert rows[0].status == "applied"
    assert rows[0].submitted_at is not None


def test_add_rejects_an_unknown_posting(env: Path, seeded_events) -> None:
    seeded_events(env)
    result = _run(env, ["track", "add", "9999"])
    assert result.exit_code != 0
    assert "no posting 9999" in result.stdout


def test_add_rejects_an_invalid_status(env: Path, seeded_events) -> None:
    posting_id = _first_posting_id(env, seeded_events)
    result = _run(env, ["track", "add", str(posting_id), "--status", "hired"])
    assert result.exit_code != 0
    assert "hired" in result.stderr


def test_add_links_the_postings_current_version(env: Path, seeded_events) -> None:
    """A4: track add resolves the posting's current posting_version_id into the application."""
    seed = seeded_events(env)
    posting_id = seed.posting_ids["alpha"]
    assert _run(env, ["track", "add", str(posting_id)]).exit_code == 0
    with get_engine(env).connect() as conn:
        job_id = job_id_for_posting(conn, posting_id)
        assert job_id is not None
        version_id = current_posting_versions(conn, [posting_id])[posting_id].posting_version_id
        linked = int(
            conn.execute(
                select(applications.c.posting_version_id).where(applications.c.job_id == job_id)
            ).scalar_one()
        )
    assert linked == version_id


def test_re_add_reports_the_existing_application_without_writing(
    env: Path, seeded_events
) -> None:
    """A7: a plain re-add must not fork the funnel; it reports the existing application."""
    posting_id = _first_posting_id(env, seeded_events)
    assert _run(env, ["track", "add", str(posting_id)]).exit_code == 0
    app_id = _funnel(env)[0].application_id
    again = _run(env, ["track", "add", str(posting_id)])
    assert again.exit_code == 0
    assert str(app_id) in again.stdout
    rows = _funnel(env)
    assert len(rows) == 1
    assert rows[0].application_id == app_id
    assert rows[0].attempt_no == 1


def test_new_attempt_increments_attempt_no(env: Path, seeded_events) -> None:
    """A7: --new-attempt is the explicit way to start a fresh attempt on a tracked job."""
    posting_id = _first_posting_id(env, seeded_events)
    assert _run(env, ["track", "add", str(posting_id)]).exit_code == 0
    assert _run(env, ["track", "add", str(posting_id), "--new-attempt"]).exit_code == 0
    rows = _funnel(env)
    assert sorted(r.attempt_no for r in rows) == [1, 2]
    assert len({r.application_id for r in rows}) == 2


def test_status_moves_the_application_and_ledgers_it(env: Path, seeded_events) -> None:
    posting_id = _first_posting_id(env, seeded_events)
    assert _run(env, ["track", "add", str(posting_id)]).exit_code == 0
    app_id = _funnel(env)[0].application_id
    assert _run(env, ["track", "status", str(app_id), "applied"]).exit_code == 0
    assert _funnel(env)[0].status == "applied"
    log = _run(env, ["track", "log", str(app_id)])
    assert "interested" in log.stdout
    assert "applied" in log.stdout


def test_status_rejects_an_unknown_application(env: Path) -> None:
    result = _run(env, ["track", "status", "77", "applied"])
    assert result.exit_code != 0
    assert "no application 77" in result.stdout


def test_status_records_a_note(env: Path, seeded_events) -> None:
    posting_id = _first_posting_id(env, seeded_events)
    assert _run(env, ["track", "add", str(posting_id)]).exit_code == 0
    app_id = _funnel(env)[0].application_id
    assert _run(
        env, ["track", "status", str(app_id), "interviewing", "--note", "phone screen booked"]
    ).exit_code == 0
    log = _run(env, ["track", "log", str(app_id)])
    # The note is rendered in full; the boxed table wraps it across lines at 80 columns.
    assert "phone screen" in log.stdout
    assert "booked" in log.stdout


def test_list_filters_by_status(env: Path, seeded_events) -> None:
    seed = seeded_events(env)
    alpha, beta = seed.posting_ids["alpha"], seed.posting_ids["beta"]
    assert _run(env, ["track", "add", str(alpha)]).exit_code == 0
    assert _run(env, ["track", "add", str(beta), "--status", "applied"]).exit_code == 0
    applied = _run(env, ["track", "list", "--status", "applied"])
    assert "beta" in applied.stdout
    assert "alpha" not in applied.stdout


def test_list_is_empty_before_anything_is_tracked(env: Path) -> None:
    result = _run(env, ["track", "list"])
    assert result.exit_code == 0
    assert "nothing tracked yet" in result.stdout


def test_a_closed_posting_can_still_be_tracked(env: Path, seeded_events) -> None:
    """epsilon is seeded closed. Tracking is about your funnel, not the board's state."""
    seed = seeded_events(env)
    result = _run(env, ["track", "add", str(seed.posting_ids["epsilon"])])
    assert result.exit_code == 0
    assert _funnel(env)[0].title == "epsilon"
