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
from boardwatch.tailor.render.outcome import CompileOutcome, CompileReason
from boardwatch.tailor.safety import TierASafetyError

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
    # Printed with markup=False; under rich's markup parser the bracket would be swallowed.
    assert "[acme-sre] acme-1" in " ".join(result.stdout.replace("\n", "").split())


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


# --- --resume / --out / --format overrides -------------------------------------------


def test_validate_resume_override_is_honoured(env: Env, tmp_path: Path) -> None:
    # No {config_dir}/resume.yaml exists: only the override can make this validate.
    override = tmp_path / "elsewhere" / "cv.yaml"
    override.parent.mkdir(parents=True)
    override.write_text(scaffold_template(), encoding="utf-8")
    result = _run(env, ["tailor", "validate", "--resume", str(override)])
    assert result.exit_code == 0, result.stdout
    assert not (env.config_dir / "resume.yaml").exists()
    assert "bullets" in result.stdout.lower()
    assert "python" in result.stdout.lower()


def test_validate_bad_resume_override_exits_nonzero(env: Env, tmp_path: Path) -> None:
    # A *valid* default exists, so a non-zero exit proves the override — not the
    # default — is what got loaded.
    _run(env, ["tailor", "init"])
    missing = tmp_path / "elsewhere" / "cv.yaml"
    result = _run(env, ["tailor", "validate", "--resume", str(missing)])
    assert result.exit_code != 0
    assert "cv.yaml" in result.stdout.replace("\n", "")


def test_run_resume_override_is_honoured(env: Env, tmp_path: Path) -> None:
    override = tmp_path / "elsewhere" / "cv.yaml"
    override.parent.mkdir(parents=True)
    override.write_text(scaffold_template(), encoding="utf-8")
    posting_id = _seed_open_posting(env)  # no `tailor init`: no default resume.yaml
    result = _run(env, ["tailor", "run", str(posting_id), "--resume", str(override)])
    assert result.exit_code == 0, result.stdout
    assert not (env.config_dir / "resume.yaml").exists()
    assert "guarantee: PASS" in result.stdout.replace("\n", "")
    assert (env.data_dir / "tailored" / f"tailored-{posting_id}.typ").is_file()


def test_run_out_dir_override_is_honoured(
    env: Env, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # A stub stands in for `typst` (never shelled out to) so this test's outcome does not
    # depend on whether the machine running it happens to have typst installed — since a
    # missing binary is now a fatal TypstUnavailableError (not a silent PDF skip), the
    # command's own exit code would otherwise vary with the host, not with --out.
    _run(env, ["tailor", "init"])
    posting_id = _seed_open_posting(env)
    out = tmp_path / "artifacts"

    def _fake_typst(typ: Path, pdf: Path) -> CompileOutcome:
        pdf.write_bytes(b"%PDF")
        return CompileOutcome(CompileReason.OK, pdf, 1, "ok")

    monkeypatch.setattr("boardwatch.reports.tailor._default_runner", _fake_typst)
    result = _run(env, ["tailor", "run", str(posting_id), "--out", str(out)])
    assert result.exit_code == 0, result.stdout
    assert (out / f"tailored-{posting_id}.typ").is_file()
    assert (out / f"tailored-{posting_id}.pdf").is_file()
    assert (out / "typst-compile.log").is_file()
    assert not (env.data_dir / "tailored").exists()  # default location untouched


def test_run_out_dir_receives_pdf_when_typst_available(
    env: Env, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Same as above but with a stub standing in for the `typst` binary (never shelled out
    to), so the PDF half of --out is asserted regardless of what is on the test runner."""
    _run(env, ["tailor", "init"])
    posting_id = _seed_open_posting(env)
    out = tmp_path / "artifacts"

    def _fake_typst(typ: Path, pdf: Path) -> CompileOutcome:
        pdf.write_bytes(b"%PDF")
        return CompileOutcome(CompileReason.OK, pdf, 1, "ok")

    monkeypatch.setattr("boardwatch.reports.tailor._default_runner", _fake_typst)
    result = _run(env, ["tailor", "run", str(posting_id), "--out", str(out)])
    assert result.exit_code == 0, result.stdout
    assert (out / f"tailored-{posting_id}.pdf").is_file()
    assert str(out / f"tailored-{posting_id}.pdf") in result.stdout.replace("\n", "")
    assert not (env.data_dir / "tailored").exists()


def test_run_unsupported_format_exits_1(env: Env, tmp_path: Path) -> None:
    _run(env, ["tailor", "init"])
    posting_id = _seed_open_posting(env)
    out = tmp_path / "artifacts"
    result = _run(env, ["tailor", "run", str(posting_id), "--format", "latex", "--out", str(out)])
    assert result.exit_code == 1
    assert "latex" in result.stdout.replace("\n", "")
    assert not out.exists()
    assert not (env.data_dir / "tailored").exists()


# --- per-bullet report ----------------------------------------------------------------


# Seven bullets in one entry (one over MAX_BULLETS_PER_ENTRY) with a mix of JD coverage,
# so a single run exercises every op the report can print: b3 holds "JS" (swapped to the
# JD's "JavaScript"), b1/b2/b3 change position among the survivors (reordered), b4-b6 are
# untouched (kept), and the lowest-ranked b7 falls off the end (dropped).
MULTI_OP_RESUME = """\
header:
  - "Ada Lovelace"
education:
  - "BSc Mathematics — Example University — 2018"
skill_groups:
  - label: "Languages"
    items: ["Python", "JavaScript"]
entries:
  - entry_id: "acme-sre"
    heading: "Senior Engineer — Acme — 2021–2024 — Remote"
    bullets:
      - bullet_id: "b1"
        text: "Wrote onboarding docs and runbooks for the on-call rotation"
      - bullet_id: "b2"
        text: "Built a Python service for billing reconciliation"
      - bullet_id: "b3"
        text: "Shipped a JS dashboard for the operations team"
      - bullet_id: "b4"
        text: "Mentored two interns through their first shipped change"
      - bullet_id: "b5"
        text: "Ran the quarterly incident review with stakeholders"
      - bullet_id: "b6"
        text: "Negotiated the vendor contract renewal with procurement"
      - bullet_id: "b7"
        text: "Organised the internal engineering reading group"
"""


def test_run_prints_per_bullet_report(env: Env, tmp_path: Path) -> None:
    resume = tmp_path / "multi.yaml"
    resume.write_text(MULTI_OP_RESUME, encoding="utf-8")
    posting_id = _seed_open_posting(env)
    result = _run(
        env,
        ["tailor", "run", str(posting_id), "--resume", str(resume), "--out", str(tmp_path / "o")],
    )
    assert result.exit_code == 0, result.stdout
    # Rich hard-wraps long lines in the narrow test console; drop newlines before matching.
    # Column padding is collapsed too so these assertions describe content, not layout.
    # The `[entry_id]` survives only because the CLI prints these rows with markup=False;
    # under Rich's markup parser the bracket reads as an unknown style tag and vanishes.
    flat = " ".join(result.stdout.replace("\n", "").split())
    assert "kept 6 · dropped 1 · swaps 1" in flat
    assert "reordered [acme-sre] b2: Python" in flat
    assert "swapped [acme-sre] b3: JavaScript" in flat
    assert "reordered [acme-sre] b1: no jd skills" in flat
    assert "kept [acme-sre] b4: no jd skills" in flat
    assert "dropped [acme-sre] b7: no jd skills" in flat
    assert "JS -> JavaScript" in flat


def test_run_tier_a_safety_error_exits_1(
    env: Env, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _run(env, ["tailor", "init"])
    posting_id = _seed_open_posting(env)
    out = tmp_path / "artifacts"

    def _boom(*args: object, **kwargs: object) -> None:
        raise TierASafetyError("Tier A safety check failed; refusing to render")

    monkeypatch.setattr("boardwatch.cli.tailor_cmd.run_tailor", _boom)
    result = _run(env, ["tailor", "run", str(posting_id), "--out", str(out)])
    assert result.exit_code == 1
    assert "refusing to render" in result.stdout.replace("\n", "")
    assert not out.exists()
