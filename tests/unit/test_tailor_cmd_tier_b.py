"""boardwatch tailor run --tier-b: CLI surface for the opt-in Tier B rewording lane.

Mirrors tests/unit/test_tailor_cmd.py's env-fixture style (CliRunner + `--data-dir` +
`BOARDWATCH_CONFIG_DIR`) and its `_seed_open_posting` shape for a minimal open posting
with a taxonomy extraction. No new global fixtures are introduced — this file defines
its own local `env` fixture rather than reaching into test_tailor_cmd.py's.
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
from boardwatch.store.tables import (
    artifacts,
    companies,
    extractions,
    jobs,
    posting_versions,
    postings,
)

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


# --- gate: resume_tailoring off (the default) ------------------------------------------


def test_tier_b_flag_errors_when_resume_tailoring_disabled(env: Env, tmp_path: Path) -> None:
    _run(env, ["tailor", "init"])
    posting_id = _seed_open_posting(env)
    out = tmp_path / "artifacts"
    result = _run(env, ["tailor", "run", str(posting_id), "--tier-b", "--out", str(out)])
    assert result.exit_code == 1
    assert "resume_tailoring" in result.stdout
    # Gate failed before run_tailor: nothing written.
    assert not out.exists()
    assert not (env.data_dir / "tailored").exists()
    assert _artifact_count(env) == 0


def test_llm_alias_errors_when_resume_tailoring_disabled(env: Env, tmp_path: Path) -> None:
    _run(env, ["tailor", "init"])
    posting_id = _seed_open_posting(env)
    out = tmp_path / "artifacts"
    result = _run(env, ["tailor", "run", str(posting_id), "--llm", "--out", str(out)])
    assert result.exit_code == 1
    assert "resume_tailoring" in result.stdout
    # Gate failed before run_tailor: nothing written.
    assert not out.exists()
    assert not (env.data_dir / "tailored").exists()
    assert _artifact_count(env) == 0


# --- regression: no flag behaves exactly as Tier A alone --------------------------------


def test_no_flag_runs_tier_a_only(env: Env, tmp_path: Path) -> None:
    _run(env, ["tailor", "init"])
    posting_id = _seed_open_posting(env)
    out = tmp_path / "artifacts"
    result = _run(env, ["tailor", "run", str(posting_id), "--out", str(out)])
    assert result.exit_code == 0, result.stdout
    assert "guarantee: PASS" in result.stdout.replace("\n", "")
    assert "Tier B" not in result.stdout


# --- gate: resume_tailoring on, but the LLM tier itself is off/uncredentialed -----------


def test_tier_b_flag_errors_when_llm_tier_not_configured(env: Env, tmp_path: Path) -> None:
    _write_config(env, "[llm]\nresume_tailoring = true\n")
    _run(env, ["tailor", "init"])
    posting_id = _seed_open_posting(env)
    out = tmp_path / "artifacts"
    result = _run(env, ["tailor", "run", str(posting_id), "--tier-b", "--out", str(out)])
    assert result.exit_code == 1
    assert "LLM tier" in result.stdout
    # Gate failed before run_tailor: nothing written.
    assert not out.exists()
    assert not (env.data_dir / "tailored").exists()
    assert _artifact_count(env) == 0


def test_tier_b_flag_errors_when_llm_enabled_but_misconfigured(
    env: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # resume_tailoring + llm.enabled = true, but missing llm.model / llm.base_url.
    # Set the API key so build_client reaches the misconfiguration ValueError.
    _write_config(env, "[llm]\nresume_tailoring = true\nenabled = true\n")
    monkeypatch.setenv("BOARDWATCH_LLM_API_KEY", "fake-key")
    _run(env, ["tailor", "init"])
    posting_id = _seed_open_posting(env)
    out = tmp_path / "artifacts"
    result = _run(env, ["tailor", "run", str(posting_id), "--tier-b", "--out", str(out)])
    assert result.exit_code == 1
    assert "llm.model" in result.stdout
    # Gate failed before run_tailor: nothing written.
    assert not out.exists()
    assert not (env.data_dir / "tailored").exists()
    assert _artifact_count(env) == 0
