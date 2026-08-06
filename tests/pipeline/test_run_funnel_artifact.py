"""The per-run funnel artifact, end to end (P0 item 1).

The unit tests pin the builder and the queries in isolation. What only an end-to-end run can
show is that the artifact is actually EMITTED, lands outside the git tree beside the day's
leads, and describes the run that just happened rather than a default-constructed one.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from rich.console import Console
from sqlalchemy import select

from boardwatch.core.settings import load_settings
from boardwatch.pipeline.runner import run_pipeline
from boardwatch.store import tables
from boardwatch.store.db import get_engine
from tests.pipeline.test_pipeline_run import INIT_INPUT, _cli, _seed_posting


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Defined here rather than imported: importing the fixture would shadow it at every test
    signature, which ruff flags as a redefinition (F811)."""
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


def _payload(out_root: Path) -> dict:
    found = list(out_root.glob("*/funnel-*.json"))
    assert len(found) == 1, f"expected exactly one funnel artifact, got {found}"
    return json.loads(found[0].read_text())


def test_a_run_emits_both_halves_beside_that_day_s_leads(env: Path, tmp_path: Path) -> None:
    """Both halves, in the dated output folder — outside the git tree.

    Generalization rule R7 requires a sha256-pinned SHIPPED_DATA entry for any tracked
    `.json`, which a per-run artifact can never satisfy, so the tracked tree is the one place
    this must not land.
    """
    _ready(env)
    out_root = tmp_path / "apps"

    summary = _pipeline(env, out_root)

    assert summary.funnel is not None, "the run produced no funnel artifact"
    assert summary.funnel.json_path.exists()
    assert summary.funnel.markdown_path.exists()
    assert summary.funnel.json_path.name == f"funnel-{summary.run_id}.json"
    # Beside the leads, under the dated folder, not at the root of the output tree.
    assert summary.funnel.json_path.parent.parent == out_root


def test_the_artifact_describes_the_run_that_just_happened(env: Path, tmp_path: Path) -> None:
    """Not a default-constructed shell: the run id, a finished timestamp, and a corpus whose
    head is every open posting, not the lead count."""
    _ready(env)
    _seed_posting(env, slug="acme3")  # a second open posting, so the counts are not all 1
    out_root = tmp_path / "apps"

    summary = _pipeline(env, out_root)
    payload = _payload(out_root)

    assert payload["run_id"] == summary.run_id
    assert payload["finished_at"] is not None, "written before the run row was closed"
    stages = {stage["name"]: stage for stage in payload["stages"]}
    # TWO open postings, so these cannot be confused with the lead count. They still cannot
    # separate `entered` from `evaluated` — the pipeline judges everything open, so the two
    # are equal on any healthy run. That distinction is pinned at the unit level, by
    # test_scan_throughput_is_not_presented_as_a_funnel_edge, which can construct a corpus
    # where they differ. What this asserts is that the artifact carries the run's real shape
    # rather than a default-constructed one.
    assert stages["corpus"]["entered"] == 2, "the corpus head is not every OPEN posting"
    assert stages["attribution"]["advanced"] == 2, "both postings were judged by THIS run"


def test_a_real_run_reconciles(env: Path, tmp_path: Path) -> None:
    """Gate P0's headline property, on an actual pipeline run rather than fed counts.

    The unit tests prove `reconciles` can be False; this proves it is True end to end, which
    is the thing the gate asks for three consecutive times. Without it, every reconciliation
    in the suite is over numbers a test handed the builder.
    """
    _ready(env)
    out_root = tmp_path / "apps"

    _pipeline(env, out_root)
    payload = _payload(out_root)

    unbalanced = [s["name"] for s in payload["stages"] if s["reconciled"] is False]
    disagreed = [c["name"] for c in payload["cross_checks"] if not c["agrees"]]
    assert unbalanced == [], f"stages did not balance: {unbalanced}"
    assert disagreed == [], f"the store disagreed with the pipeline: {disagreed}"
    assert payload["reconciles"] is True


def test_a_run_with_no_profile_still_reconciles(
    env: Path, tmp_path: Path
) -> None:
    """A run with no profile judged nothing, and the funnel must say so and still balance.

    The whole corpus lands in `no_current_evaluation` — which is the truth, not a
    degradation — rather than the stage reporting counts it has no identity to compute.
    """
    _seed_posting(env)  # a posting, but deliberately no `init`, so no profile exists
    out_root = tmp_path / "apps"

    summary = _pipeline(env, out_root)
    payload = _payload(out_root)

    assert summary.fatal is not None, "a missing profile is fatal; the fixture is wrong"
    stages = {stage["name"]: stage for stage in payload["stages"]}
    assert stages["corpus"]["entered"] == 1
    assert stages["corpus"]["advanced"] == 0, "nothing can be judged without a profile"
    assert stages["corpus"]["drops"][0]["count"] == 1
    # The ranker never ran, so `shortlist` must be UNMEASURED — not 0 in / 0 out. This run
    # still reconciles, but only because an uninstrumented stage is excluded from the gate
    # rather than silently passing it. Before the fix this stage reported zeros with
    # derived=False, which put it in the artifact's list of stages that could have failed and
    # asserted the ranker had run and accounted for everything.
    assert stages["shortlist"]["entered"] is None
    assert stages["shortlist"]["instrumented"] is False
    assert stages["shortlist"]["reconciled"] is None
    assert payload["reconciles"] is True


def test_the_artifact_names_the_board_each_lead_came_from(env: Path, tmp_path: Path) -> None:
    """Gate P0: *which source produced each lead*, from the artifact alone.

    The seeded posting belongs to a watched greenhouse board, and the artifact must say so
    without the reader consulting the database or the code.
    """
    posting_id = _ready(env)
    out_root = tmp_path / "apps"

    _pipeline(env, out_root)
    leads = _payload(out_root)["leads"]

    assert [lead["posting_id"] for lead in leads] == [posting_id]
    assert leads[0]["provider"] == "greenhouse"
    assert leads[0]["board_slug"] == "acme2"
    assert leads[0]["company_source"] == "user"


def test_the_artifact_reports_every_catalog_rule_not_just_the_ones_that_fired(
    env: Path, tmp_path: Path
) -> None:
    """Gate P0 requires per-rule abstain for EVERY rule in the catalog, every run.

    On a one-posting run almost no rule fires, so a report built by grouping the observed
    rows would be nearly empty — which is precisely the condition this must not degrade to.
    """
    _ready(env)
    out_root = tmp_path / "apps"

    _pipeline(env, out_root)
    abstain = _payload(out_root)["abstain"]

    assert abstain["rule_count"] == 44
    assert len(abstain["rules"]) == 44
    assert abstain["never_fired"] > 0, "a single posting fired every rule in the catalog?"
    # Never-fired rules carry no rate at all, rather than the 0% that would rank them healthy.
    assert any(rule["abstain_rate"] is None for rule in abstain["rules"])


def test_a_crashed_run_still_leaves_a_funnel(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A crashed run is exactly when its funnel is worth having.

    The artifact is written from the same `finally` that closes the run row, so a pipeline
    that raised partway still explains how far it got. If it were written on the success path
    only, every failed run would be undiagnosable from the artifact.
    """
    _ready(env)
    out_root = tmp_path / "apps"

    import boardwatch.pipeline.runner as runner_mod

    def boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("taxonomy.yaml is malformed")

    monkeypatch.setattr(runner_mod, "_count_evaluations", boom)
    with pytest.raises(RuntimeError):
        _pipeline(env, out_root)

    payload = _payload(out_root)
    assert payload["finished_at"] is not None
    with get_engine(env).connect() as conn:
        run_id = conn.execute(select(tables.runs.c.id)).scalars().one()
    assert payload["run_id"] == run_id


def test_a_failure_to_write_the_funnel_does_not_fail_the_run(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reporting is not the deliverable.

    The write happens in a `finally` that may be running while an exception propagates, so
    raising there would replace the real cause of a failure with a reporting error — and on a
    healthy run it would discard leads that were already produced.
    """
    _ready(env)
    out_root = tmp_path / "apps"

    import boardwatch.pipeline.runner as runner_mod

    def boom(*_a: object, **_k: object) -> None:
        raise OSError("read-only file system")

    monkeypatch.setattr(runner_mod, "collect_run_funnel", boom)
    summary = _pipeline(env, out_root)

    assert summary.funnel is None
    assert summary.fatal is None, "a reporting failure was promoted into a run failure"
    assert len(summary.tailored) == 1, "the run's real output was discarded"
