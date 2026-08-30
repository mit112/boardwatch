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
from boardwatch.pipeline import runner
from boardwatch.pipeline.runner import run_pipeline
from boardwatch.rank.location_gate import classify_location
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


def test_the_artifact_names_where_each_lead_is_and_how_the_us_gate_read_it(
    env: Path, tmp_path: Path
) -> None:
    """D-267, end to end. The hard US location gate is the one gate whose failure is a lead the
    user cannot legally take, and until v7 it left no trace in the artifact it emits: every
    "all leads US-located" claim came from a by-hand store read and could not be reproduced
    afterwards.

    The expected location is READ BACK OUT OF THE STORE rather than transcribed, so the
    assertion cannot go on passing against a stale literal if the seed changes — and the gate's
    verdict is compared against the production classifier, not against a hand-written answer.
    """
    posting_id = _ready(env)
    seeded = ["Austin, TX", "Remote"]
    with get_engine(env).begin() as conn:
        conn.execute(
            tables.postings.update()
            .where(tables.postings.c.id == posting_id)
            .values(locations_json=seeded)
        )
    out_root = tmp_path / "apps"

    _pipeline(env, out_root)
    payload = _payload(out_root)
    (found,) = payload["leads"]

    with get_engine(env).connect() as conn:
        stored = conn.execute(
            select(tables.postings.c.locations_json).where(tables.postings.c.id == posting_id)
        ).scalar_one()
    assert found["locations"] == list(stored)
    assert found["location_class"] == classify_location(list(stored))
    # And the run says whether the gate was armed at all, so the verdicts above are readable.
    assert payload["manifest"]["location_filter_mode"] == load_settings(
        data_dir=env
    ).location_filter_mode


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

    assert abstain["rule_count"] == 45
    assert len(abstain["rules"]) == 45
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


def test_a_funnel_that_fails_to_write_is_recorded_rather_than_only_printed(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A funnel-less run must stop being indistinguishable from a clean one in the store.

    The emit stays fail-open on purpose — a reporting failure must never discard a run that
    produced real leads and PDFs. But until D-287 the failure reached neither `summary.fatal`
    nor `summary.errors`, only the console, and `finish_run` had already committed. So a
    scheduled tick whose funnel never wrote still exited 0 and looked byte-identical to a
    clean one to anything reading the database, while **Gate P3 counts clean unattended runs
    and B1/B5 are read out of the funnel that does not exist** (STATE open question 1; Mit's
    ruling was to keep it non-fatal and record it).

    Fails on `main` three ways: `summary.errors` is empty, the run row's `errors_json` is
    empty, and nothing distinguishes this run from a clean one.
    """
    _ready(env)

    def _boom(*_args: object, **_kw: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(runner, "_emit_funnel", _boom)

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.funnel is None
    assert summary.fatal is None, "a reporting failure must never fail the run"
    assert any("funnel artifact not written" in e for e in summary.errors), summary.errors
    with get_engine(env).connect() as conn:
        row = conn.execute(
            select(tables.runs).where(tables.runs.c.id == summary.run_id)
        ).one()
    assert any(
        "funnel artifact not written" in e for e in (row.errors_json or [])
    ), row.errors_json


def _stage(payload: dict, name: str) -> dict:
    """The named funnel stage, out of the artifact this run actually wrote."""
    found = [stage for stage in payload["stages"] if stage["name"] == name]
    assert len(found) == 1, f"expected exactly one {name!r} stage, got {found}"
    return found[0]


def test_the_runs_row_carries_the_same_corpus_the_funnel_reported(
    env: Path, tmp_path: Path
) -> None:
    """D-371's write, checked against the artifact rather than against itself.

    The corpus-regression detector reads `runs.corpus_*` while every existing reader of these
    numbers reads the funnel, so the two must be the same measurement. They are, by
    construction — the writer stamps the very `CorpusCounts` object the artifact is rendered
    from — and this pins that construction. It rejects a version that re-counts the corpus in a
    second sweep (five more passes over the whole open corpus, and two numbers for one run with
    nothing to say which is authoritative), and a version wired into the no-profile branch or
    into no branch at all, which would leave the columns NULL on a run that measured a corpus.

    `corpus_candidates` is checked against the VERDICT stage, not the corpus stage: it is
    eligible + uncertain, and the artifact keeps those unfolded — `advanced` for eligible and
    the `abstained` drop for uncertain. Recomposing it here is what makes this a comparison
    between two representations rather than a restatement of one.
    """
    _ready(env)
    out_root = tmp_path / "apps"
    summary = _pipeline(env, out_root)
    payload = _payload(out_root)

    corpus = _stage(payload, "corpus")
    verdict = _stage(payload, "verdict")
    abstained = [d["count"] for d in verdict["drops"] if d["reason"] == "abstained"]
    assert len(abstained) == 1, verdict["drops"]

    with get_engine(env).connect() as conn:
        row = conn.execute(select(tables.runs).where(tables.runs.c.id == summary.run_id)).one()

    assert row.corpus_open == corpus["entered"]
    assert row.corpus_evaluated == corpus["advanced"]
    assert row.corpus_candidates == verdict["advanced"] + abstained[0]
    # Non-vacuous: a run that evaluated nothing would satisfy every equality above with three
    # zeros, and a NULL column would satisfy none of them but is what a dead branch writes.
    assert row.corpus_evaluated > 0, "the fixture judged nothing; the equalities are trivial"


def test_a_corpus_regression_alert_reaches_the_run_row_not_just_the_summary(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The alert has to be DURABLE, because the owner is not at the machine.

    An unattended run prints to a log nobody reads. `summary.errors` alone is invisible the
    moment the process exits, which is the asymmetry D-287 closed for the funnel and the
    morning digest; the same asymmetry would make this detector decorative. So the alert must
    land in `runs.errors_json` via `append_run_error` as well.

    And it must not fatal the run. The run itself succeeded — a corpus regression is a ticket,
    not a dead-man's-switch trip — so `summary.fatal` stays None and the run stays `ok`.
    Rejects a version that sets `fatal`, and one that only appends to the summary.
    """
    _ready(env)

    monkeypatch.setattr(
        runner, "check_corpus_regression", lambda *_a, **_k: "corpus: rate collapsed to 0.00%"
    )

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.fatal is None, "a soft alert was promoted into a run failure"
    assert any("rate collapsed" in e for e in summary.errors), summary.errors
    with get_engine(env).connect() as conn:
        row = conn.execute(select(tables.runs).where(tables.runs.c.id == summary.run_id)).one()
    assert any("rate collapsed" in e for e in (row.errors_json or [])), row.errors_json
    assert row.status == "ok", "the run outcome moved for a reporting-side alert"
