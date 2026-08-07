"""The per-run morning artifact, end to end (P3 item 7).

Mirrors `tests/pipeline/test_run_funnel_artifact.py`: the pure builder is pinned at the unit
level (`tests/unit/test_morning.py`); what only an end-to-end run can show is that the artifact
is actually EMITTED beside the funnel, describes the run that just happened, and that its
verdict label is the SAME thing `eligibility/audit.py::load_audit` would render for that
posting right now — not a value invented by the runner's own threading.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from rich.console import Console

from boardwatch.core.settings import load_settings
from boardwatch.eligibility.audit import load_audit
from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.preflight import current_identity
from boardwatch.pipeline.runner import run_pipeline
from boardwatch.store.db import get_engine
from tests.pipeline.test_pipeline_run import INIT_INPUT, _cli, _seed_posting


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


def _ready(data_dir: Path) -> int:
    posting_id = _seed_posting(data_dir)
    assert _cli(data_dir, ["init"], INIT_INPUT).exit_code == 0
    assert _cli(data_dir, ["tailor", "init"]).exit_code == 0
    return posting_id


def _pipeline(data_dir: Path, out_root: Path, **kw):
    settings = load_settings(data_dir=data_dir)
    return run_pipeline(
        get_engine(data_dir),
        settings,
        console=Console(quiet=True),
        out_root=out_root,
        resume_path=settings.config_dir / "resume.yaml",
        skip_scan=True,
        **kw,
    )


def _payload(out_root: Path, kind: str) -> dict:
    found = list(out_root.glob(f"*/{kind}-*.json"))
    assert len(found) == 1, f"expected exactly one {kind} artifact, got {found}"
    return json.loads(found[0].read_text())


def test_a_run_emits_the_morning_artifact_beside_the_funnel(env: Path, tmp_path: Path) -> None:
    _ready(env)
    out_root = tmp_path / "apps"

    summary = _pipeline(env, out_root)

    assert summary.morning is not None, "the run produced no morning artifact"
    assert summary.morning.json_path.exists()
    assert summary.morning.markdown_path.exists()
    assert summary.morning.json_path.name == f"morning-{summary.run_id}.json"
    assert summary.morning.json_path.parent == summary.funnel.json_path.parent  # type: ignore[union-attr]


def test_the_morning_artifact_links_the_funnel_by_name(env: Path, tmp_path: Path) -> None:
    _ready(env)
    out_root = tmp_path / "apps"

    summary = _pipeline(env, out_root)
    payload = _payload(out_root, "morning")

    assert payload["run_id"] == summary.run_id
    assert payload["funnel"] == f"funnel-{summary.run_id}.md"


def test_one_row_per_tailored_lead_with_apply_url_and_pdf_path(
    env: Path, tmp_path: Path
) -> None:
    posting_id = _ready(env)
    out_root = tmp_path / "apps"

    summary = _pipeline(env, out_root)
    payload = _payload(out_root, "morning")

    assert len(payload["leads"]) == len(summary.tailored) == 1
    (row,) = payload["leads"]
    assert row["posting_id"] == posting_id
    # `_seed_posting` writes url="https://example.test/j" — the artifact must carry it through
    # a real `postings.url` join, not fabricate or drop it.
    assert row["apply_url"] == "https://example.test/j"
    assert row["pdf_path"], "a lead that compiled a PDF must carry its real path"
    assert Path(row["pdf_path"]).exists()


def test_the_verdict_label_equals_load_audit_s_presentation(env: Path, tmp_path: Path) -> None:
    """The honest AuditView.presentation label (D-036) — not the bare stored verdict, and not
    a value the runner invented independently of what `show`/`top` would render right now."""
    posting_id = _ready(env)
    out_root = tmp_path / "apps"

    settings = load_settings(data_dir=env)
    summary = _pipeline(env, out_root)
    payload = _payload(out_root, "morning")
    (row,) = payload["leads"]

    engine = get_engine(env)
    catalog = load_rules(settings.config_dir)
    with engine.connect() as conn:
        identity = current_identity(conn, settings)
        assert identity is not None
        profile_hash, rules_hash = identity
        audit = load_audit(
            conn, posting_id, catalog, profile_hash=profile_hash, rules_hash=rules_hash
        )
    assert audit is not None
    assert row["verdict_label"] == audit.presentation.value
    assert summary.run_id == payload["run_id"]


def test_a_run_with_no_tailored_leads_still_emits_an_empty_morning_artifact(
    env: Path, tmp_path: Path
) -> None:
    """A run producing zero leads is exactly when an operator most needs to see that the
    morning artifact ran at all — an absent file would read as "the pipeline never got here"
    rather than "nothing qualified"."""
    _seed_posting(env)  # a posting, but no `init` — no profile, so nothing is ranked/tailored
    out_root = tmp_path / "apps"

    summary = _pipeline(env, out_root)
    payload = _payload(out_root, "morning")

    assert summary.fatal is not None, "a missing profile is fatal; the fixture is wrong"
    assert payload["leads"] == []
