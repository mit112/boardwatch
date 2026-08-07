"""boardwatch tailor rewrite request: CLI surface for the subscription Tier B agent
lane's step 1 (P7b task 4). Mirrors tests/unit/test_tailor_cmd_tier_b.py's env-fixture
style (CliRunner + `--data-dir` + `BOARDWATCH_CONFIG_DIR`) and its `_seed_open_posting`
shape for a minimal open posting with a taxonomy extraction.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import insert
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.core.settings import Settings
from boardwatch.extract.taxonomy import load_taxonomy
from boardwatch.store.artifacts import get_derivations
from boardwatch.store.db import DB_FILENAME, ensure_schema, get_engine
from boardwatch.store.tables import (
    artifacts,
    companies,
    extractions,
    jobs,
    posting_versions,
    postings,
)
from boardwatch.tailor.render.outcome import CompileOutcome, CompileReason
from boardwatch.tailor.rewrite.agent_io import (
    Candidate,
    CandidatesFile,
    JudgeRequest,
    RewriteRequest,
    Verdict,
    VerdictsFile,
    dump_json,
    load_json,
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
                    name="acme",
                    provider="greenhouse",
                    slug="acme",
                    source="user",
                    watched=True,
                )
            ).inserted_primary_key[0]
        )
        job_id = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
        posting_id = int(
            conn.execute(
                insert(postings).values(
                    company_id=company_id,
                    job_id=job_id,
                    provider_posting_id="pp-acme",
                    title="Backend Engineer",
                    normalized_title="backend engineer",
                    url="https://example.test/acme",
                    locations_json=["Remote"],
                    remote_policy="remote",
                    posted_at=NOW,
                    first_seen_at=NOW,
                    last_seen_at=NOW,
                    status="open",
                    consecutive_missing=0,
                    content_hash="h1",
                    body_text="Python JavaScript backend services",
                )
            ).inserted_primary_key[0]
        )
        conn.execute(
            insert(posting_versions).values(
                posting_id=posting_id,
                content_hash="h1",
                body_text="Python JavaScript backend services",
                captured_at=NOW,
                capture_reason="new",
            )
        )
        conn.execute(
            insert(extractions).values(
                posting_id=posting_id,
                content_hash="h1",
                kind="taxonomy",
                engine_version=load_taxonomy(settings.config_dir).version,
                json={"skills": list(skills)},
                created_at=NOW,
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


# --- rewrite screen (P7b task 5, agent lane step 2) -------------------------------------


def test_rewrite_screen_gate_off_exits_1(env: Env, tmp_path: Path) -> None:
    _run(env, ["tailor", "init"])
    posting_id = _seed_open_posting(env)
    candidates_path = tmp_path / "candidates.json"
    dump_json(CandidatesFile(request_id="r1", candidates=[]), candidates_path)
    out = tmp_path / "judge_request.json"
    result = _run(
        env,
        [
            "tailor",
            "rewrite",
            "screen",
            str(posting_id),
            "--candidates",
            str(candidates_path),
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 1
    assert "resume_tailoring_via_agent" in result.stdout
    assert not out.exists()


def test_rewrite_screen_writes_jd_free_judge_request(env: Env, tmp_path: Path) -> None:
    _write_config(env, "[llm]\nresume_tailoring_via_agent = true\n")
    _run(env, ["tailor", "init"])
    posting_id = _seed_open_posting(env, skills=("python", "javascript"))

    # Produce the real tailored resume context via `request`, then hand-author
    # candidates.json referencing those bullet ids.
    request_out = tmp_path / "rewrite_request.json"
    req_result = _run(
        env, ["tailor", "rewrite", "request", str(posting_id), "--out", str(request_out)]
    )
    assert req_result.exit_code == 0, req_result.stdout
    rewrite_request = load_json(RewriteRequest, request_out)
    assert {b.bullet_id for b in rewrite_request.bullets} == {"acme-1", "acme-2"}

    candidates_path = tmp_path / "candidates.json"
    dump_json(
        CandidatesFile(
            request_id="req-1",
            candidates=[
                # passes the filter -> should survive to the judge
                Candidate(
                    bullet_id="acme-1",
                    candidate="Shipped a Python service handling 2M requests/day on Kubernetes",
                ),
                # byte-equal to a_text -> dropped "unchanged"
                Candidate(
                    bullet_id="acme-2",
                    candidate="Cut p99 latency 40% by rewriting the hot path in Rust",
                ),
            ],
        ),
        candidates_path,
    )

    out = tmp_path / "judge_request.json"
    result = _run(
        env,
        [
            "tailor",
            "rewrite",
            "screen",
            str(posting_id),
            "--candidates",
            str(candidates_path),
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert out.exists()

    judge_req = load_json(JudgeRequest, out)
    assert judge_req.request_id == "req-1"
    assert len(judge_req.items) == 1
    item = judge_req.items[0]
    assert item.bullet_id == "acme-1"
    assert item.a_text == "Built a Python service handling 2M requests/day on Kubernetes"
    assert item.candidate == "Shipped a Python service handling 2M requests/day on Kubernetes"

    # CRITICAL: judge_request.json must be structurally JD-free -- no jd/jd_skills key
    # anywhere in the raw JSON, not just absent from the parsed model.
    raw = json.loads(out.read_text(encoding="utf-8"))
    assert "jd" not in raw
    assert "jd_skills" not in raw
    for raw_item in raw["items"]:
        assert "jd" not in raw_item
        assert "jd_skills" not in raw_item

    assert "dropped [acme-2]: unchanged" in result.stdout


# --- rewrite apply (P7b task 6, agent lane step 3) --------------------------------------


def test_rewrite_apply_gate_off_exits_1(env: Env, tmp_path: Path) -> None:
    _run(env, ["tailor", "init"])
    posting_id = _seed_open_posting(env)
    candidates_path = tmp_path / "candidates.json"
    dump_json(CandidatesFile(request_id="r1", candidates=[]), candidates_path)
    verdicts_path = tmp_path / "verdicts.json"
    dump_json(VerdictsFile(request_id="r1", verdicts=[]), verdicts_path)
    result = _run(
        env,
        [
            "tailor",
            "rewrite",
            "apply",
            str(posting_id),
            "--candidates",
            str(candidates_path),
            "--verdicts",
            str(verdicts_path),
        ],
    )
    assert result.exit_code == 1
    assert "resume_tailoring_via_agent" in result.stdout
    assert _artifact_count(env) == 0


def test_rewrite_apply_emits_llm_artifact_with_lineage(env: Env, tmp_path: Path) -> None:
    """End-to-end: request -> hand-authored candidates.json + verdicts.json -> apply.

    Asserts exit 0, a `resume_tailored_llm` artifact row exists with a `rewritten_from`
    derivation to the Tier A artifact, meta provider/model carry the agent-lane
    provenance override, and the rendered llm source marks the kept bullet.
    """
    _write_config(env, "[llm]\nresume_tailoring_via_agent = true\n")
    _run(env, ["tailor", "init"])
    posting_id = _seed_open_posting(env, skills=("python", "javascript"))

    request_out = tmp_path / "rewrite_request.json"
    req_result = _run(
        env, ["tailor", "rewrite", "request", str(posting_id), "--out", str(request_out)]
    )
    assert req_result.exit_code == 0, req_result.stdout

    candidates_path = tmp_path / "candidates.json"
    dump_json(
        CandidatesFile(
            request_id="req-1",
            candidates=[
                # passes the overmatch filter -> proceeds to the (agent) judge
                Candidate(
                    bullet_id="acme-1",
                    candidate="Shipped a Python service handling 2M requests/day on Kubernetes",
                ),
            ],
        ),
        candidates_path,
    )
    verdicts_path = tmp_path / "verdicts.json"
    dump_json(
        VerdictsFile(
            request_id="req-1",
            verdicts=[Verdict(bullet_id="acme-1", raw_reply="ENTAILED")],
        ),
        verdicts_path,
    )

    out_dir = tmp_path / "out"
    result = _run(
        env,
        [
            "tailor",
            "rewrite",
            "apply",
            str(posting_id),
            "--candidates",
            str(candidates_path),
            "--verdicts",
            str(verdicts_path),
            "--out",
            str(out_dir),
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "reworded 1" in result.stdout
    assert "[acme-sre] acme-1" in result.stdout

    engine = get_engine(env.data_dir)
    ensure_schema(engine)
    with engine.connect() as conn:
        rows = conn.execute(artifacts.select()).fetchall()
        tier_a_row = next(r for r in rows if r.kind == "resume_tailored")
        llm_row = next(r for r in rows if r.kind == "resume_tailored_llm")
        edges = get_derivations(conn, llm_row.id)

    assert llm_row.meta_json["provider"] == "claude-code-agent"
    assert llm_row.meta_json["model"] == "subscription"
    # The agent lane enforces its own budget (2x the résumé's bullet count -- scaffold's
    # two bullets, acme-1 + acme-2, so 4), NOT the API lane's llm.max_calls_per_run
    # (default 50). If run_tailor's meta ever fell back to the settings default here,
    # this would catch it (4 != 50).
    assert llm_row.meta_json["budget"] == 4
    assert any(
        e.relation == "rewritten_from" and e.parent_artifact_id == tier_a_row.id for e in edges
    )

    llm_typ = out_dir / f"tailored-{posting_id}-llm.typ"
    assert llm_typ.exists()
    assert "reworded (Tier B)" in llm_typ.read_text(encoding="utf-8")


def _apply_fixture(env: Env, tmp_path: Path) -> tuple[int, Path, Path]:
    """A posting plus a matching candidates.json/verdicts.json pair, ready for `rewrite
    apply` — the shared setup for the PDF-gate tests below and the happy path above."""
    _write_config(env, "[llm]\nresume_tailoring_via_agent = true\n")
    _run(env, ["tailor", "init"])
    posting_id = _seed_open_posting(env, skills=("python", "javascript"))

    request_out = tmp_path / "rewrite_request.json"
    req_result = _run(
        env, ["tailor", "rewrite", "request", str(posting_id), "--out", str(request_out)]
    )
    assert req_result.exit_code == 0, req_result.stdout

    candidates_path = tmp_path / "candidates.json"
    dump_json(
        CandidatesFile(
            request_id="req-1",
            candidates=[
                Candidate(
                    bullet_id="acme-1",
                    candidate="Shipped a Python service handling 2M requests/day on Kubernetes",
                ),
            ],
        ),
        candidates_path,
    )
    verdicts_path = tmp_path / "verdicts.json"
    dump_json(
        VerdictsFile(
            request_id="req-1",
            verdicts=[Verdict(bullet_id="acme-1", raw_reply="ENTAILED")],
        ),
        verdicts_path,
    )
    return posting_id, candidates_path, verdicts_path


def test_rewrite_apply_compile_failure_exits_nonzero_not_a_traceback(
    env: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both the tailored and untailored-master renders fail: `run_tailor` raises
    `LeadArtifactError`. Before this change `rewrite apply` had no try/except around
    `run_tailor` at all, so this would surface as an unhandled traceback rather than a
    clean, user-facing failure."""
    posting_id, candidates_path, verdicts_path = _apply_fixture(env, tmp_path)

    def _fake_typst(typ: Path, pdf: Path) -> CompileOutcome:
        return CompileOutcome(CompileReason.COMPILE_FAILED, None, None, "boom")

    monkeypatch.setattr("boardwatch.reports.tailor._default_runner", _fake_typst)
    result = _run(
        env,
        [
            "tailor", "rewrite", "apply", str(posting_id),
            "--candidates", str(candidates_path), "--verdicts", str(verdicts_path),
        ],
    )
    assert result.exit_code == 1, result.stdout
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert "no shippable résumé PDF" in result.stdout


def test_rewrite_apply_binary_missing_exits_nonzero_with_install_hint(
    env: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    posting_id, candidates_path, verdicts_path = _apply_fixture(env, tmp_path)

    monkeypatch.setattr("boardwatch.reports.tailor.shutil.which", lambda name: None)
    result = _run(
        env,
        [
            "tailor", "rewrite", "apply", str(posting_id),
            "--candidates", str(candidates_path), "--verdicts", str(verdicts_path),
        ],
    )
    assert result.exit_code == 1, result.stdout
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert "typst" in result.stdout.lower()
    assert "install" in result.stdout.lower()


def test_rewrite_apply_rejects_mismatched_request_ids(env: Env, tmp_path: Path) -> None:
    """candidates.json and verdicts.json from two different runs must be rejected --
    bullet_ids alone can't tell them apart since they're stable across postings (same
    authored resume.yaml), so a mismatched ENTAILED verdict from the wrong run could
    keep a bullet its own run's judge would have dropped."""
    _write_config(env, "[llm]\nresume_tailoring_via_agent = true\n")
    _run(env, ["tailor", "init"])
    posting_id = _seed_open_posting(env, skills=("python", "javascript"))

    request_out = tmp_path / "rewrite_request.json"
    req_result = _run(
        env, ["tailor", "rewrite", "request", str(posting_id), "--out", str(request_out)]
    )
    assert req_result.exit_code == 0, req_result.stdout

    candidates_path = tmp_path / "candidates.json"
    dump_json(
        CandidatesFile(
            request_id="req-1",
            candidates=[
                Candidate(
                    bullet_id="acme-1",
                    candidate="Shipped a Python service handling 2M requests/day on Kubernetes",
                ),
            ],
        ),
        candidates_path,
    )
    verdicts_path = tmp_path / "verdicts.json"
    dump_json(
        VerdictsFile(
            request_id="req-2-DIFFERENT-RUN",
            verdicts=[Verdict(bullet_id="acme-1", raw_reply="ENTAILED")],
        ),
        verdicts_path,
    )

    out_dir = tmp_path / "out"
    result = _run(
        env,
        [
            "tailor",
            "rewrite",
            "apply",
            str(posting_id),
            "--candidates",
            str(candidates_path),
            "--verdicts",
            str(verdicts_path),
            "--out",
            str(out_dir),
        ],
    )
    assert result.exit_code == 1
    assert "req-1" in result.stdout
    assert "req-2-DIFFERENT-RUN" in result.stdout
    assert _artifact_count(env) == 0
