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
from boardwatch.llm.client import LaneDeathReason, LLMLaneDeadError
from boardwatch.llm.run_client import RunScopedClient
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
    assert (out / f"tailored-{posting_id}-llm.tex").exists()
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


# --- lane death: both containment boundaries, and a reason the CLI can name --------------


# A provenance-passing reword of the scaffold's FIRST bullet ("Built a Python service
# handling 2M requests/day on Kubernetes"), reusing the scripted bodies above. Load-bearing:
# a reply that is NOT provenanced is vetoed at lane.py's provenance gate BEFORE the judge
# call, so `die_on=2` would spend call 2 on the SECOND bullet's propose and exercise the
# propose boundary twice while still passing every assertion below.
_PROVENANCED_REWORD = "Built the Python service handling 2M requests/day on Kubernetes"


class _DiesOnNthCall:
    """Succeeds for `n - 1` calls, then reports the credential is unusable."""

    def __init__(self, n: int, reply: str = _PROVENANCED_REWORD) -> None:
        self._n = n
        self._reply = reply
        self.calls = 0

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        self.calls += 1
        if self.calls >= self._n:
            raise LLMLaneDeadError("revoked", reason=LaneDeathReason.CREDENTIAL_INVALID)
        return self._reply


class _DiesAfterBodies:
    """Serves a scripted transcript, then reports the credential is unusable."""

    def __init__(self, bodies: list[str]) -> None:
        self.bodies = list(bodies)
        self.calls = 0

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        self.calls += 1
        if not self.bodies:
            raise LLMLaneDeadError("revoked", reason=LaneDeathReason.CREDENTIAL_INVALID)
        return self.bodies.pop(0)


class _AlwaysSucceeds:
    """Never fails. Used to warm the response cache and to drive the budget path."""

    def __init__(self, reply: str = _PROVENANCED_REWORD) -> None:
        self._reply = reply
        self.calls = 0

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        self.calls += 1
        return self._reply


@pytest.mark.parametrize("die_on", [1, 2], ids=["propose-boundary", "judge-boundary"])
def test_lane_death_records_lane_dead_and_keeps_tier_a(
    env: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, die_on: int
) -> None:
    _write_tier_b_config(env)
    inner = _DiesOnNthCall(die_on)
    client = RunScopedClient(inner)
    monkeypatch.setattr("boardwatch.cli.tailor_cmd.build_client", lambda settings: client)
    _run(env, ["tailor", "init"])
    posting_id = _seed_open_posting(env)
    out = tmp_path / "artifacts"

    result = _run(env, ["tailor", "run", str(posting_id), "--tier-b", "--out", str(out)])

    flat = result.stdout.replace("\n", "")
    # `lane_dead` reaches stdout through the EXISTING per-row printer (tag =
    # f"fallback:{drop_reason}"), so this assertion would still pass with the new CLI
    # block deleted. The load-bearing pair is the reason and the exit code below.
    assert "lane_dead" in flat
    assert "credential_invalid" in flat
    assert result.exit_code == 1  # death observed AND zero kept
    # Tier A is untouched: the lane is advisory rewording layered over an intact Tier-A
    # résumé, and a dead credential must never delete or downgrade a real result.
    assert "guarantee: PASS" in flat
    assert _artifact_count(env) > 0
    # The provider is touched exactly `die_on` times however many bullets remain: the
    # wrapper latches on the first death and short-circuits every later call.
    assert inner.calls == die_on
    assert client.dead_reason is LaneDeathReason.CREDENTIAL_INVALID
    # Both bullets fall back for lane death and for nothing else. For `die_on=2` this is
    # what proves the JUDGE boundary fired: call 1's candidate cleared every pre-judge
    # veto (no `fallback:provenance` row) and bullet 1 still fell back as `lane_dead`, so
    # the only place call 2 can have died is `lane.py`'s judge boundary.
    assert flat.count("fallback:lane_dead") == 2
    assert "fallback:provenance" not in flat
    # The exit-1 run still WROTE a resume_tailored_llm artifact, so the line naming it must
    # survive the failure. Raising above the printer suppressed the only pointer to a file
    # that exists on disk.
    assert "tier B pdf:" in flat


def test_lane_death_after_a_kept_rewrite_is_a_partial_success(
    env: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The OTHER conjunct of the exit rule. Death is observed and reported, but the first
    # bullet was already reworded and judged ENTAILED before the credential went, so the
    # invocation is a partial success and must exit 0 -- exit 1 is death AND zero kept.
    _write_tier_b_config(env)
    inner = _DiesAfterBodies([_PROVENANCED_REWORD, "ENTAILED"])
    client = RunScopedClient(inner)
    monkeypatch.setattr("boardwatch.cli.tailor_cmd.build_client", lambda settings: client)
    _run(env, ["tailor", "init"])
    posting_id = _seed_open_posting(env)
    out = tmp_path / "artifacts"

    result = _run(env, ["tailor", "run", str(posting_id), "--tier-b", "--out", str(out)])

    flat = result.stdout.replace("\n", "")
    assert result.exit_code == 0, result.stdout
    # Death is still named -- a partial success is not a silent one.
    assert "credential_invalid" in flat
    assert "Tier B (LLM): reworded 1 · unchanged 0 · fell back 1" in flat
    assert flat.count("fallback:lane_dead") == 1
    # bullet 1 propose + judge, then bullet 2's propose is the call that dies.
    assert inner.calls == 3
    assert client.dead_reason is LaneDeathReason.CREDENTIAL_INVALID


def test_healthy_run_keeping_zero_rewrites_still_exits_0(
    env: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # lane.py drops a rewrite down many more paths than it keeps one, so zero-kept is a
    # routine HEALTHY outcome -- a live credential legitimately keeps nothing whenever
    # every candidate is judged not-entailed, echoed back unchanged, or filtered. Exiting
    # non-zero on it would break normal use: exit 1 requires death observed AND zero kept.
    #
    # Driven through the BUDGET path rather than the judge: with the cap at 1 the first
    # propose spends the only call and every later call drops with drop_reason="budget",
    # kept=False. Deterministic, and it needs no knowledge of the judge's vocabulary.
    _write_tier_b_config(env, max_calls_per_run=1)
    healthy = RunScopedClient(_AlwaysSucceeds())
    monkeypatch.setattr("boardwatch.cli.tailor_cmd.build_client", lambda settings: healthy)
    _run(env, ["tailor", "init"])
    posting_id = _seed_open_posting(env)
    out = tmp_path / "artifacts"

    result = _run(env, ["tailor", "run", str(posting_id), "--tier-b", "--out", str(out)])

    flat = result.stdout.replace("\n", "")
    assert result.exit_code == 0, result.stdout
    assert "Tier B (LLM): reworded 0 · unchanged 0 · fell back 2" in flat
    assert "lane_dead" not in flat
    assert healthy.dead_reason is None


def test_warm_cache_work_still_lands_after_death(
    env: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The cache is consulted BEFORE the client (lane.py's `call`), so cached bullets keep
    # landing after the latch trips. That is the specified policy: a mixed invocation is a
    # partial success and exits 0, and a fully-warm one never probes the credential at all.
    #
    # Warm the cache by running once with a healthy client that reworded BOTH bullets, then
    # re-run against a dead one -- simpler and more faithful than hand-computing cache keys,
    # and it makes "work lands" falsifiable: the second run must still report `reworded 2`.
    # Both invocations share `env.data_dir` (via `_run`'s `--data-dir`), which is what makes
    # the cache warm on the second pass.
    _write_tier_b_config(env)
    healthy = RunScopedClient(
        _FakeClient(
            [
                _PROVENANCED_REWORD,
                "ENTAILED",
                "Cut p99 latency 40% by rewriting the hot path with Rust",
                "ENTAILED",
            ]
        )
    )
    monkeypatch.setattr("boardwatch.cli.tailor_cmd.build_client", lambda settings: healthy)
    _run(env, ["tailor", "init"])
    posting_id = _seed_open_posting(env)
    out = tmp_path / "artifacts"
    first = _run(env, ["tailor", "run", str(posting_id), "--tier-b", "--out", str(out)])
    assert first.exit_code == 0, first.stdout
    assert "Tier B (LLM): reworded 2 · unchanged 0 · fell back 0" in first.stdout.replace("\n", "")
    assert healthy.calls_attempted == 4

    dead = RunScopedClient(_DiesOnNthCall(1))
    monkeypatch.setattr("boardwatch.cli.tailor_cmd.build_client", lambda settings: dead)
    second = _run(env, ["tailor", "run", str(posting_id), "--tier-b", "--out", str(out)])

    flat = second.stdout.replace("\n", "")
    assert second.exit_code == 0, second.stdout
    # The rewrites still LAND -- served entirely from the cache, which is checked before the
    # client, so the dead credential was never probed and never latched.
    assert "Tier B (LLM): reworded 2 · unchanged 0 · fell back 0" in flat
    assert dead.calls_attempted == 0
    assert dead.dead_reason is None
    assert "lane_dead" not in flat
