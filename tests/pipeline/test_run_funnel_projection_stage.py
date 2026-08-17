"""The `projection` stage as a REAL `boardwatch run --project` writes it (P5a task 9).

`tests/unit/test_run_funnel_projection.py` pins the pure builder. This module pins the thing that
builder exists for and that no unit test can see: a projected run that loses one lead to a per-lead
projection failure must report **`reconciles: true`**.

That is not cosmetic and it was not true before this stage existed. The `tailor` stage balances
`shortlisted = tailored + tailor_failed + withheld_not_live`, and a projection-dropped lead is in
none of those three buckets — so every `--project` run with a per-lead drop wrote `reconciles: no`
into its own artifact, which is Gate P0's headline claim. Nothing pinned it, so it could have been
"fixed" by arithmetic that happened to work.

The environment is the one `test_pipeline_projection_leads` already assembles — its `_SelectRunner`
makes the SECOND lead's candidate compile fail, which is a real `CANDIDATE_UNRENDERABLE` raised by
`select`, not a failure injected at the funnel's boundary. The counts are then read out of the
FROZEN JSON rather than off the summary, so what is asserted is what a reader of the artifact gets.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from boardwatch.projection.run import ProjectionAvailability, ProjectionLeadOutcome
from tests.pipeline.test_ledger_advances_the_queue import _ready
from tests.pipeline.test_pipeline_projection_leads import (
    _pipeline,
    _projected_env,
    _SelectRunner,
    _use,
)
from tests.pipeline.test_pipeline_projection_preflight import _config_dir, _install_projection


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


def _stages(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    stages = payload["stages"]
    assert isinstance(stages, list)
    return {str(stage["name"]): stage for stage in stages}


def _drops(stage: dict[str, object]) -> dict[str, int]:
    entries = stage["drops"]
    assert isinstance(entries, list)
    return {str(entry["reason"]): int(entry["count"]) for entry in entries}


def test_a_projected_run_that_lost_a_lead_reconciles(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two shortlisted leads, one projected, one lost to `CANDIDATE_UNRENDERABLE`.

    The assertion that trips without the stage is `payload["reconciles"] is True`: the tailor stage
    accounts for 1 lead + 0 tailor failures + 0 withheld against 2 shortlisted, so it reports
    `reconciled: false` and `RunFunnel.reconciles` follows it.
    """
    _ready(env, 2)
    _projected_env(env)
    _use(monkeypatch, _SelectRunner(fail_lead=2))

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.fatal is None, summary.errors
    assert summary.projection_outcomes == Counter(
        {
            ProjectionLeadOutcome.PROJECTED: 1,
            ProjectionLeadOutcome.CANDIDATE_UNRENDERABLE: 1,
        }
    )
    assert summary.funnel is not None
    payload = json.loads(summary.funnel.json_path.read_text(encoding="utf-8"))

    # The regression this task fixes, read off the frozen artifact.
    assert payload["reconciles"] is True
    assert payload["artifact_version"] == 5

    stages = _stages(payload)
    projection = stages["projection"]
    assert projection["entered"] == 2
    assert projection["advanced"] == 1
    assert _drops(projection) == {"withheld_not_live": 0, "candidate_unrenderable": 1}
    assert projection["reconciled"] is True
    # The drops are counted per lead at the raise site, so the balance is evidence.
    assert projection["derived"] is False

    # The tailor stage enters at what projection advanced, and the lost lead is NOT in its bucket.
    assert stages["tailor"]["entered"] == 1
    assert stages["tailor"]["advanced"] == 1
    assert _drops(stages["tailor"]) == {"tailor_failed": 0}
    assert stages["tailor"]["reconciled"] is True

    # The independent recount, over rows this run actually wrote.
    checks = {str(check["name"]): check for check in payload["cross_checks"]}
    assert checks["projected_leads"]["in_memory"] == 1
    assert checks["projected_leads"]["from_store"] == 1
    assert checks["projected_leads"]["agrees"] is True

    markdown = summary.funnel.markdown_path.read_text(encoding="utf-8")
    assert "### projection — 2 in, 1 out" in markdown
    assert "**candidate_unrenderable**: 1" in markdown


def test_a_refused_projected_run_still_carries_an_UNMEASURED_stage(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The third case of "absent, not zeroed", and the only one with no other end-to-end cover.

    `--project` with no approval filed: the preflight refuses and the pipeline `return`s BEFORE
    `rank_open_postings`, so `summary.shortlist` is None and `projection_outcomes` is EMPTY — yet the
    funnel is still emitted from the `finally`, and the run has a verdict to report. The stage must
    therefore be PRESENT and UNMEASURED: `entered`/`advanced` null, `instrumented: false`,
    `reconciled: null` so it is excluded from `unreconciled`.

    This is the case a helper that folds `projection_outcomes` before the real decision site cannot
    reach. `collect_run_funnel` is what decides here — and it must decide on the run's VERDICT, not
    on the counter being non-empty, or an empty counter drops this stage out of the artifact
    altogether and a refused run becomes indistinguishable from a run that never passed the flag.
    """
    _ready(env, 2)
    _install_projection(_config_dir(env))  # no approval filed at all

    summary = _pipeline(env, tmp_path / "apps")

    # The preconditions that make this the uncovered case, asserted rather than assumed.
    assert summary.projection_availability is ProjectionAvailability.MISSING_APPROVAL
    assert summary.projection_outcomes == Counter()
    assert summary.shortlist is None
    assert summary.fatal is not None
    assert summary.funnel is not None

    payload = json.loads(summary.funnel.json_path.read_text(encoding="utf-8"))
    stages = _stages(payload)
    assert "projection" in stages, sorted(stages)
    projection = stages["projection"]
    assert projection["entered"] is None
    assert projection["advanced"] is None
    assert projection["instrumented"] is False
    # An uncomputable identity is not a pass and not a failure: null, so the stage is in neither
    # `unreconciled` nor the list of balances that could have failed.
    assert projection["reconciled"] is None
    assert projection["drops"] == []
    assert "NOT INSTRUMENTED" in str(projection["note"])
    assert not any(stage["reconciled"] is False for stage in stages.values()), stages

    markdown = summary.funnel.markdown_path.read_text(encoding="utf-8")
    assert "| projection | not instrumented | not instrumented | — | — |" in markdown
    # The refusal's cause is on the FATAL line; the stage does not fabricate one of its own.
    assert ProjectionAvailability.MISSING_APPROVAL.value not in str(projection["note"])
    assert ProjectionAvailability.MISSING_APPROVAL.value in str(payload["fatal"])


def test_an_authored_run_has_no_projection_stage(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same environment, no `--project`: the stage is ABSENT rather than a row of zeros, and the
    tailor stage still enters at the shortlist. A stage reading 0 in / 0 out would claim projection
    ran and dropped nothing on every ordinary run."""
    _ready(env, 2)
    _projected_env(env)

    summary = _pipeline(env, tmp_path / "apps", project=False)

    assert summary.fatal is None, summary.errors
    assert summary.projection_availability is None
    assert summary.funnel is not None
    payload = json.loads(summary.funnel.json_path.read_text(encoding="utf-8"))

    assert "projection" not in _stages(payload)
    assert _stages(payload)["tailor"]["entered"] == 2
    assert "withheld_not_live" in _drops(_stages(payload)["tailor"])
    assert "projected_leads" not in {str(check["name"]) for check in payload["cross_checks"]}
    assert payload["reconciles"] is True
