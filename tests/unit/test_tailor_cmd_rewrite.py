"""boardwatch tailor rewrite request: CLI surface for the subscription Tier B agent
lane's step 1 (P7b task 4). Mirrors tests/unit/test_tailor_cmd_tier_b.py's env-fixture
style (CliRunner + `--data-dir` + `BOARDWATCH_CONFIG_DIR`) and its `_seed_open_posting`
shape for a minimal open posting with a taxonomy extraction.
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
from boardwatch.store.db import DB_FILENAME, ensure_schema, get_engine
from boardwatch.store.tables import (
    artifacts,
    companies,
    extractions,
    jobs,
    posting_versions,
    postings,
)
from boardwatch.tailor.rewrite.agent_io import RewriteRequest, load_json

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
    monkeypatch.delenv("BOARDWATCH_LLM_API_KEY", raising=False)
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


def _write_config(env: Env, body: str) -> None:
    (env.config_dir / "config.toml").write_text(body, encoding="utf-8")


def _artifact_count(env: Env) -> int:
    engine = get_engine(env.data_dir)
    ensure_schema(engine)
    with engine.connect() as conn:
        return conn.execute(artifacts.select()).all().__len__()


# --- gate: resume_tailoring_via_agent off (the default) --------------------------------


def test_rewrite_request_gate_off_exits_1(env: Env, tmp_path: Path) -> None:
    _run(env, ["tailor", "init"])
    posting_id = _seed_open_posting(env)
    out = tmp_path / "rewrite_request.json"
    result = _run(env, ["tailor", "rewrite", "request", str(posting_id), "--out", str(out)])
    assert result.exit_code == 1
    assert "resume_tailoring_via_agent" in result.stdout
    # Gate failed before plan_tier_a: nothing written.
    assert not out.exists()
    assert _artifact_count(env) == 0


def test_rewrite_request_gate_failure_creates_no_database(env: Env) -> None:
    """The gate must run before build_context, which creates/migrates boardwatch.db."""
    result = _run(env, ["tailor", "rewrite", "request", "1"])
    assert result.exit_code == 1
    assert "resume_tailoring_via_agent" in result.stdout
    assert not (env.data_dir / DB_FILENAME).exists()


# --- happy path: gate on, writes a round-trippable RewriteRequest ----------------------


def test_rewrite_request_writes_expected_file(env: Env, tmp_path: Path) -> None:
    _write_config(env, "[llm]\nresume_tailoring_via_agent = true\n")
    _run(env, ["tailor", "init"])
    posting_id = _seed_open_posting(env, skills=("python", "javascript"))
    out = tmp_path / "rewrite_request.json"
    result = _run(env, ["tailor", "rewrite", "request", str(posting_id), "--out", str(out)])
    assert result.exit_code == 0, result.stdout
    assert out.exists()

    req = load_json(RewriteRequest, out)
    assert req.jd_skills == ["javascript", "python"]
    # scaffold_template's two bullets both survive Tier A against these jd_skills.
    assert {b.bullet_id for b in req.bullets} == {"acme-1", "acme-2"}
    by_id = {b.bullet_id: b for b in req.bullets}
    assert by_id["acme-1"].entry_id == "acme-sre"
    assert by_id["acme-1"].a_text == "Built a Python service handling 2M requests/day on Kubernetes"


def test_rewrite_request_default_out_path(env: Env) -> None:
    _write_config(env, "[llm]\nresume_tailoring_via_agent = true\n")
    _run(env, ["tailor", "init"])
    posting_id = _seed_open_posting(env)
    result = _run(env, ["tailor", "rewrite", "request", str(posting_id)])
    assert result.exit_code == 0, result.stdout
    expected = env.data_dir / "tailored" / f"rewrite_request-{posting_id}.json"
    assert expected.exists()


def test_rewrite_request_no_current_version_exits_1(env: Env) -> None:
    _write_config(env, "[llm]\nresume_tailoring_via_agent = true\n")
    _run(env, ["tailor", "init"])
    result = _run(env, ["tailor", "rewrite", "request", "999"])
    assert result.exit_code == 1
    assert "no current version" in result.stdout
