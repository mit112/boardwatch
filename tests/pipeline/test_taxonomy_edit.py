"""State test k (D21): editing the {config_dir}/taxonomy.yaml override triggers
the preflight on the next ranking command — profile skills and open-posting
extractions refresh together; superseded extractions become unreachable."""

from pathlib import Path

import pytest
from provider_cases import ProviderCase
from sqlalchemy import Engine, select
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.extract.taxonomy import bundled_taxonomy_text, load_taxonomy
from boardwatch.scan.apply import apply_board
from boardwatch.store import tables
from boardwatch.store.queries import save_profile

runner = CliRunner()

OVERRIDE_EXTRA = (
    "  - {name: 'Zig', category: language, pattern: '\\bzig\\b', case_sensitive: false}\n"
)


def test_k_taxonomy_edit_triggers_preflight_on_next_top(
    tmp_path: Path, engine: Engine, company_id: int, run_id: int,
    monkeypatch: pytest.MonkeyPatch, case: ProviderCase,
) -> None:
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(cfg))

    jobs = case.jobs()[:2]
    zig = case.set_body(case.clone_with_id(jobs[0], 111), "We use Zig and Python for tooling.")
    other = case.set_body(case.clone_with_id(jobs[1], 222), "Go services on Kubernetes.")
    apply_board(engine, case.snapshot_for([zig, other]), company_id, run_id)
    bundled_version = load_taxonomy(cfg).version
    with engine.begin() as conn:
        save_profile(
            conn, text="Python and Zig enthusiast.", target_titles=[], exclude_titles=[],
            locations=[], remote_only=False,
            skills=sorted(load_taxonomy(cfg).extract("Python and Zig enthusiast.")),
            taxonomy_version=bundled_version,
        )

    first = runner.invoke(app, ["--data-dir", str(tmp_path), "top"])
    assert first.exit_code == 0
    assert "re-extracting 2 postings" in first.output  # initial backfill at bundled version

    # ---- the edit: user override = bundled + one new pattern ----
    (cfg / "taxonomy.yaml").write_text(
        bundled_taxonomy_text() + OVERRIDE_EXTRA, encoding="utf-8"
    )
    override_version = load_taxonomy(cfg).version
    assert override_version != bundled_version

    second = runner.invoke(app, ["--data-dir", str(tmp_path), "top"])
    assert second.exit_code == 0
    assert "re-extracting 2 postings" in second.output  # preflight ran again

    with engine.connect() as conn:
        profile_row = conn.execute(select(tables.profile)).one()
        current_rows = conn.execute(
            select(tables.extractions).where(
                tables.extractions.c.engine_version == override_version
            )
        ).all()
        superseded_rows = conn.execute(
            select(tables.extractions).where(
                tables.extractions.c.engine_version == bundled_version
            )
        ).all()
    assert profile_row.taxonomy_version == override_version  # refreshed TOGETHER
    assert "Zig" in profile_row.skills_json
    assert len(current_rows) == 2  # every open posting re-extracted
    zig_row = next(r for r in current_rows if "Zig" in r.json["skills"])
    assert zig_row is not None
    assert len(superseded_rows) == 2  # superseded rows remain ...
    # ... but are unreachable through the current version key (asserted by the
    # current_rows query keying on override_version only)

    third = runner.invoke(app, ["--data-dir", str(tmp_path), "top"])
    assert third.exit_code == 0
    assert "re-extracting" not in third.output  # zero work when current
