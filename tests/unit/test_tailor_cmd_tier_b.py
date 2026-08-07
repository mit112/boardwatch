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
from boardwatch.store.db import DB_FILENAME, ensure_schema, get_engine
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


def test_tier_b_gate_failure_creates_no_database(env: Env) -> None:
    """The gate must run before build_context, which creates/migrates boardwatch.db.

    Deliberately skips `_seed_open_posting` and `_artifact_count` above: both call
    `ensure_schema`/`get_engine` directly and would create the very database file this
    test proves does not exist. The gate fails on `resume_tailoring` alone, before any
    posting lookup, so a nonexistent posting id is fine here.
    """
    result = _run(env, ["tailor", "run", "1", "--tier-b"])
    assert result.exit_code == 1
    assert "resume_tailoring" in result.stdout
    assert not (env.data_dir / DB_FILENAME).exists()


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


# --- dry-run: the LLM cache is written even though no artifacts/résumé files are -----------


class _FakeClient:
    """Scripted client for CLI-level tests: build_client is monkeypatched to return
    this instead of a real provider adapter, so no network is required."""

    def __init__(self, bodies: list[str]) -> None:
        self.bodies = list(bodies)

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        return self.bodies.pop(0) if self.bodies else ""


def test_tier_b_dry_run_does_not_claim_nothing_written(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tier B's ResponseCache writes to {data_dir}/llm-cache during a dry run (the
    preview must reflect what a real run would produce), so the CLI must not print the
    Tier-A-only "nothing written" line when Tier B actually ran."""
    _write_config(env, "[llm]\nresume_tailoring = true\n")
    monkeypatch.setattr(
        "boardwatch.cli.tailor_cmd.build_client",
        lambda settings: _FakeClient(
            [
                "Built the Python service handling 2M requests/day on Kubernetes",
                "ENTAILED",
                "Cut p99 latency 40% by rewriting the hot path with Rust",
                "ENTAILED",
            ]
        ),
    )
    _run(env, ["tailor", "init"])
    posting_id = _seed_open_posting(env)
    result = _run(env, ["tailor", "run", str(posting_id), "--tier-b", "--dry-run"])
    assert result.exit_code == 0, result.stdout
    assert "nothing written" not in result.stdout.lower()
    cache_dir = env.data_dir / "llm-cache"
    assert cache_dir.exists()
    assert any(cache_dir.iterdir())  # provider replies really were cached


def test_run_dry_run_without_tier_b_message_unchanged(env: Env, tmp_path: Path) -> None:
    """Regression: the plain Tier A dry-run message must stay byte-identical."""
    _run(env, ["tailor", "init"])
    posting_id = _seed_open_posting(env)
    result = _run(env, ["tailor", "run", str(posting_id), "--dry-run"])
    assert result.exit_code == 0, result.stdout
    assert "dry run — source only, nothing written" in result.stdout


# --- report block: Tier B counts line, budget hint, and no-op tagging (real CLI run) ----
#
# These drive a real Tier B run through the CLI: the gate (resume_tailoring, llm.enabled,
# BOARDWATCH_LLM_API_KEY) runs unmodified, and only the seam past the gate — build_client —
# is monkeypatched to hand back a scripted client instead of a real provider adapter. The
# scaffolded résumé (see scaffold_template) has exactly two bullets: acme-1 "Built a Python
# service handling 2M requests/day on Kubernetes" and acme-2 "Cut p99 latency 40% by
# rewriting the hot path in Rust", processed entry-then-bullet in that order, so a scripted
# client's bodies list is consumed as [b1-propose, b1-judge, b2-propose, b2-judge].


def _write_tier_b_config(env: Env, *, max_calls_per_run: int | None = None) -> None:
    body = "[llm]\nresume_tailoring = true\nenabled = true\n"
    if max_calls_per_run is not None:
        body += f"max_calls_per_run = {max_calls_per_run}\n"
    _write_config(env, body)


def test_tier_b_report_shows_reworded_count_and_disclaimer(
    env: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_tier_b_config(env)
    monkeypatch.setenv("BOARDWATCH_LLM_API_KEY", "fake-key")
    monkeypatch.setattr(
        "boardwatch.cli.tailor_cmd.build_client",
        lambda settings: _FakeClient(
            [
                "Built the Python service handling 2M requests/day on Kubernetes",
                "ENTAILED",
                "Cut p99 latency 40% by rewriting the hot path with Rust",
                "ENTAILED",
            ]
        ),
    )
    _run(env, ["tailor", "init"])
    posting_id = _seed_open_posting(env)
    out = tmp_path / "artifacts"
    result = _run(env, ["tailor", "run", str(posting_id), "--tier-b", "--out", str(out)])
    assert result.exit_code == 0, result.stdout
    flat = result.stdout.replace("\n", "")
    assert "Tier B (LLM): reworded 2 · unchanged 0 · fell back 0" in flat
    assert (out / f"tailored-{posting_id}-llm.typ").exists()
    assert "NOT structurally proven" in flat


def test_tier_b_report_shows_budget_hint_when_exhausted(
    env: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Tier B spends 2 calls per bullet (propose + judge); a budget of 2 lets the first
    # bullet complete but leaves nothing for the second, which drops with drop_reason="budget".
    _write_tier_b_config(env, max_calls_per_run=2)
    monkeypatch.setenv("BOARDWATCH_LLM_API_KEY", "fake-key")
    monkeypatch.setattr(
        "boardwatch.cli.tailor_cmd.build_client",
        lambda settings: _FakeClient(
            ["Built the Python service handling 2M requests/day on Kubernetes", "ENTAILED"]
        ),
    )
    _run(env, ["tailor", "init"])
    posting_id = _seed_open_posting(env)
    out = tmp_path / "artifacts"
    result = _run(env, ["tailor", "run", str(posting_id), "--tier-b", "--out", str(out)])
    assert result.exit_code == 0, result.stdout
    flat = result.stdout.replace("\n", "")
    assert "Tier B (LLM): reworded 1 · unchanged 0 · fell back 1" in flat
    assert "max_calls_per_run" in flat


def test_tier_b_report_tags_unchanged_and_excludes_it_from_fell_back(
    env: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A client that echoes each bullet back verbatim: candidate == source short-circuits
    # before the judge, so only two calls (one propose per bullet) are ever made.
    _write_tier_b_config(env)
    monkeypatch.setenv("BOARDWATCH_LLM_API_KEY", "fake-key")
    monkeypatch.setattr(
        "boardwatch.cli.tailor_cmd.build_client",
        lambda settings: _FakeClient(
            [
                "Built a Python service handling 2M requests/day on Kubernetes",
                "Cut p99 latency 40% by rewriting the hot path in Rust",
            ]
        ),
    )
    _run(env, ["tailor", "init"])
    posting_id = _seed_open_posting(env)
    out = tmp_path / "artifacts"
    result = _run(env, ["tailor", "run", str(posting_id), "--tier-b", "--out", str(out)])
    assert result.exit_code == 0, result.stdout
    flat = result.stdout.replace("\n", "")
    assert "Tier B (LLM): reworded 0 · unchanged 2 · fell back 0" in flat
    assert "fallback:unchanged" not in flat
