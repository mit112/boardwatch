"""boardwatch tailor init/validate/run: CLI coverage over reports.tailor + tailor.load.

Mirrors tests/unit/test_notify_cmd.py's env-fixture style (CliRunner + `--data-dir` +
`BOARDWATCH_CONFIG_DIR`) and tests/unit/test_reports_tailor.py's `_seed` shape for a
minimal open posting with a taxonomy extraction. No new global fixtures are introduced.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import insert
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.core.settings import Settings
from boardwatch.extract.taxonomy import load_taxonomy
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.tables import companies, extractions, jobs, posting_versions, postings
from boardwatch.tailor.load import scaffold_template

runner = CliRunner()
NOW = datetime(2026, 8, 2, 12, 0, 0)


@dataclass(frozen=True)
class Env:
    data_dir: Path
    config_dir: Path


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    cfg = tmp_path / "cfg"
    cfg.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(cfg))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return Env(data_dir=tmp_path / "data", config_dir=cfg)


def _run(env: Env, args: list[str]):
    return runner.invoke(app, ["--data-dir", str(env.data_dir), *args])


def _seed_open_posting(env: Env, *, skills: tuple[str, ...] = ("Python", "JavaScript")) -> int:
    """Insert one company+job+posting+version+taxonomy extraction; return posting_id."""
    settings = Settings(data_dir=env.data_dir, config_dir=env.config_dir)
    engine = get_engine(env.data_dir)
    ensure_schema(engine)
    with engine.begin() as conn:
        company_id = int(
            conn.execute(
                insert(companies).values(
                    name="acme", provider="greenhouse", slug="acme", source="user", watched=True,
                )
            ).inserted_primary_key[0]
        )
        job_id = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
        posting_id = int(
            conn.execute(
                insert(postings).values(
                    company_id=company_id, job_id=job_id, provider_posting_id="pp-acme",
                    title="Backend Engineer", normalized_title="backend engineer",
                    url="https://example.test/acme", locations_json=["Remote"],
                    remote_policy="remote", posted_at=NOW, first_seen_at=NOW, last_seen_at=NOW,
                    status="open", consecutive_missing=0, content_hash="h1",
                    body_text="Python JavaScript backend services",
                )
            ).inserted_primary_key[0]
        )
        conn.execute(
            insert(posting_versions).values(
                posting_id=posting_id, content_hash="h1",
                body_text="Python JavaScript backend services",
                captured_at=NOW, capture_reason="new",
            )
        )
        conn.execute(
            insert(extractions).values(
                posting_id=posting_id, content_hash="h1", kind="taxonomy",
                engine_version=load_taxonomy(settings.config_dir).version,
                json={"skills": list(skills)}, created_at=NOW,
            )
        )
    return posting_id


def test_init_scaffolds(env: Env) -> None:
    result = _run(env, ["tailor", "init"])
    assert result.exit_code == 0, result.stdout
    path = env.config_dir / "resume.yaml"
    assert path.is_file()
    assert path.read_text(encoding="utf-8") == scaffold_template()
    # Rich hard-wraps long paths mid-word in a narrow test console; drop newlines to compare.
    assert str(path) in result.stdout.replace("\n", "")


def test_init_refuses_clobber_without_force(env: Env) -> None:
    first = _run(env, ["tailor", "init"])
    assert first.exit_code == 0, first.stdout
    (env.config_dir / "resume.yaml").write_text("mutated", encoding="utf-8")
    second = _run(env, ["tailor", "init"])
    assert second.exit_code != 0
    assert "force" in second.stdout.lower()
    # Refused: the mutated file must survive untouched.
    assert (env.config_dir / "resume.yaml").read_text(encoding="utf-8") == "mutated"


def test_init_force_overwrites(env: Env) -> None:
    _run(env, ["tailor", "init"])
    path = env.config_dir / "resume.yaml"
    path.write_text("mutated", encoding="utf-8")
    result = _run(env, ["tailor", "init", "--force"])
    assert result.exit_code == 0, result.stdout
    assert path.read_text(encoding="utf-8") == scaffold_template()


def test_validate_reports_skills(env: Env) -> None:
    _run(env, ["tailor", "init"])
    result = _run(env, ["tailor", "validate"])
    assert result.exit_code == 0, result.stdout
    assert "bullets" in result.stdout.lower()
    assert "python" in result.stdout.lower()  # taxonomy.extract on the scaffold's own bullets


def test_validate_bad_resume_exits_nonzero(env: Env) -> None:
    # Valid YAML, invalid Resume (missing every required field) -> ResumeLoadError.
    (env.config_dir / "resume.yaml").write_text("not_a_resume_field: true\n", encoding="utf-8")
    result = _run(env, ["tailor", "validate"])
    assert result.exit_code != 0


def test_validate_missing_resume_exits_nonzero(env: Env) -> None:
    result = _run(env, ["tailor", "validate"])
    assert result.exit_code != 0
    assert "tailor init" in result.stdout.replace("\n", "")


def test_run_dry_run(env: Env) -> None:
    _run(env, ["tailor", "init"])
    posting_id = _seed_open_posting(env)
    result = _run(env, ["tailor", "run", str(posting_id), "--dry-run"])
    assert result.exit_code == 0, result.stdout
    assert "dry run" in result.stdout.lower()
    assert "kept" in result.stdout.lower()


def test_run_no_current_version_exits_1(env: Env) -> None:
    _run(env, ["tailor", "init"])
    result = _run(env, ["tailor", "run", "999"])
    assert result.exit_code == 1
    assert "999" in result.stdout


def test_run_missing_resume_exits_1(env: Env) -> None:
    posting_id = _seed_open_posting(env)  # no `tailor init` run first
    result = _run(env, ["tailor", "run", str(posting_id), "--dry-run"])
    assert result.exit_code == 1
