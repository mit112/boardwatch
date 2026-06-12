from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from gh_fixtures import BOARD_URL, clone_with_id, gh_jobs, set_body, snapshot_for
from sqlalchemy import Engine, select
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.extract.taxonomy import load_taxonomy
from boardwatch.scan.apply import apply_board
from boardwatch.store import tables
from boardwatch.store.queries import save_profile

runner = CliRunner()


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(cfg))
    return tmp_path


def _seed_profile(engine: Engine, config_dir: Path, text: str = "Python, Go, PostgreSQL.") -> None:
    taxonomy = load_taxonomy(config_dir)
    with engine.begin() as conn:
        save_profile(
            conn, text=text, target_titles=["Backend Engineer"], exclude_titles=[],
            locations=["Remote"], remote_only=False,
            skills=sorted(taxonomy.extract(text)), taxonomy_version=taxonomy.version,
        )


def _seed_postings(engine: Engine, company_id: int, run_id: int) -> dict[str, int]:
    jobs = gh_jobs()[:2]
    strong = set_body(clone_with_id(jobs[0], 111), "<p>Python, Go, and PostgreSQL daily.</p>")
    strong["title"] = "Backend Engineer"
    strong["location"] = {"name": "Remote — US"}
    weak = set_body(clone_with_id(jobs[1], 222), "<p>Watering plants and pruning roses.</p>")
    weak["title"] = "Gardener"
    weak["location"] = {"name": "On-site greenhouse"}
    apply_board(engine, snapshot_for([strong, weak]), company_id, run_id)
    with engine.connect() as conn:
        rows = conn.execute(
            select(tables.postings.c.id, tables.postings.c.provider_posting_id)
        ).all()
    return {row.provider_posting_id: int(row.id) for row in rows}


def _invoke(data_dir: Path, args: list[str]) -> Any:
    return runner.invoke(app, ["--data-dir", str(data_dir), *args])


def test_top_ranks_strong_match_first(
    env: Path, engine: Engine, company_id: int, run_id: int, tmp_path: Path
) -> None:
    _seed_postings(engine, company_id, run_id)
    _seed_profile(engine, env / "cfg")
    result = _invoke(tmp_path, ["top"])
    assert result.exit_code == 0
    out = result.stdout
    assert "Backend Engineer" in out and "Gardener" in out
    assert out.index("Backend Engineer") < out.index("Gardener")
    assert "covers" in out  # the why column


def test_top_excludes_closed_postings(
    env: Path, engine: Engine, company_id: int, run_id: int, tmp_path: Path
) -> None:
    ids = _seed_postings(engine, company_id, run_id)
    _seed_profile(engine, env / "cfg")
    apply_board(engine, snapshot_for([]), company_id, run_id)  # miss 1 for both
    jobs = gh_jobs()[:1]
    strong = set_body(clone_with_id(jobs[0], 111), "<p>Python, Go, and PostgreSQL daily.</p>")
    strong["title"] = "Backend Engineer"
    apply_board(engine, snapshot_for([strong]), company_id, run_id)  # Gardener: miss 2 -> closed
    result = _invoke(tmp_path, ["top"])
    assert result.exit_code == 0
    assert "Gardener" not in result.stdout
    assert ids  # silence unused warning


def test_top_help_does_not_promise_new_flag(env: Path) -> None:
    result = runner.invoke(app, ["top", "--help"])
    assert result.exit_code == 0
    assert "--new" not in result.stdout  # P2 owns the event cursor


def test_show_open_posting_renders_breakdown(
    env: Path, engine: Engine, company_id: int, run_id: int, tmp_path: Path
) -> None:
    ids = _seed_postings(engine, company_id, run_id)
    _seed_profile(engine, env / "cfg")
    result = _invoke(tmp_path, ["show", str(ids["111"])])
    assert result.exit_code == 0
    out = result.stdout
    assert "skill_coverage" in out and "title_match" in out
    assert "recency" in out and "location_fit" in out
    assert "Python" in out  # body text rendered


def test_show_closed_posting_banner_no_score_no_extraction(
    env: Path, engine: Engine, company_id: int, run_id: int,
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    ids = _seed_postings(engine, company_id, run_id)
    _seed_profile(engine, env / "cfg")
    apply_board(engine, snapshot_for([]), company_id, run_id)
    apply_board(engine, snapshot_for([]), company_id, run_id)  # both closed

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("preflight must not run for closed postings")

    monkeypatch.setattr("boardwatch.cli.show_cmd.run_preflight", forbidden)
    result = _invoke(tmp_path, ["show", str(ids["222"])])
    assert result.exit_code == 0
    out = result.stdout
    assert "CLOSED" in out
    assert "closed — not ranked" in out
    assert "skill_coverage" not in out  # no score section
    assert "Watering plants" in out  # body/link/comp stay readable
    with engine.connect() as conn:
        extraction_count = len(conn.execute(select(tables.extractions)).all())
    assert extraction_count == 0  # no on-demand extraction for closed postings


def test_show_no_recognized_skills_message(
    env: Path, engine: Engine, company_id: int, run_id: int, tmp_path: Path
) -> None:
    ids = _seed_postings(engine, company_id, run_id)
    _seed_profile(engine, env / "cfg")
    result = _invoke(tmp_path, ["show", str(ids["222"])])  # gardening body: no taxonomy hits
    assert result.exit_code == 0
    assert "no recognized skills" in result.stdout  # Rich may wrap across lines


def test_show_unknown_id_fails_cleanly(env: Path, engine: Engine, tmp_path: Path) -> None:
    result = _invoke(tmp_path, ["show", "424242"])
    assert result.exit_code == 1
    assert "no posting with id 424242" in result.stdout


def test_scan_summary_includes_filter_match_count(
    env: Path, engine: Engine, company_id: int, run_id: int, tmp_path: Path
) -> None:
    _seed_profile(engine, env / "cfg")
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "greenhouse" / "normal.json"
    with respx.mock:
        respx.get(BOARD_URL).mock(
            return_value=httpx.Response(200, content=fixture.read_bytes())
        )
        result = _invoke(tmp_path, ["scan"])
    assert result.exit_code == 0
    assert "match your filters" in result.stdout


def test_help_smoke(env: Path) -> None:
    assert runner.invoke(app, ["top", "--help"]).exit_code == 0
    assert runner.invoke(app, ["show", "--help"]).exit_code == 0
