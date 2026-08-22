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
from collections.abc import Callable
from pathlib import Path

import pytest

from boardwatch.pipeline import runner as runner_mod
from boardwatch.projection.run import ProjectionAvailability, ProjectionLeadOutcome
from boardwatch.reports.resume_gate import RenderToolMissingError
from boardwatch.store.db import get_engine
from boardwatch.tailor.render.latex import resolve_template
from boardwatch.tailor.render.outcome import CompileOutcome, CompileReason
from tests.pipeline.test_ledger_advances_the_queue import _ready
from tests.pipeline.test_pipeline_projection_leads import (
    _pipeline,
    _projected_env,
    _SelectRunner,
    _use,
)
from tests.pipeline.test_pipeline_projection_preflight import (
    _config_dir,
    _disposition_count,
    _install_projection,
)


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
    assert payload["artifact_version"] == 6

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


# -- the late run-scoped abort still reconciles -------------------------------------------
#
# Preflight says AVAILABLE, lead 1 projects, and lead 2 then hits a RUN-scoped cause from inside
# `select()`. The loop sets `fatal` and breaks — and before this fix the current lead and every
# lead behind it got no terminal accounting at all, while the stage still declared
# `entered = shortlist.shortlisted`. That is a FOURTH case outside the three §4.5 promises are
# exhaustive (flag absent / preflight refused / balanced run), and it wrote `reconciles: false`.
#
# One case per run-scoped issue reachable from `select()`, parametrised over the real cause rather
# than over a mocked classification: three arrive through the compile gate (`_fatal_if_infrastructure`
# and the pinned-budget check) and the fourth is `TemplateArtifactError`, raised by the real
# `LatexRenderer.emit` inside `compile_prefix`.


class _BaseCompileRunner:
    """Fails the pinned-only BASE compile of one chosen lead with a supplied gate outcome.

    Same discriminator as `_SelectRunner`: calls are grouped by `tex.parent`, the
    `TemporaryDirectory` `project_for_posting` opens once per lead, and within a lead the FIRST
    compile is `select`'s `pinned_gate`. Reading the lead off that structural property rather than
    off a call index is what keeps this fixture honest when `select`'s growth loop changes.

    `outcome` is a factory over the destination pdf path, not a value: the `PAGE_LIMIT_EXCEEDED`
    case has to hand back an `OK` outcome carrying a real page count, and `CompileOutcome`'s own
    invariant requires the pdf to exist for that reason.
    """

    def __init__(self, *, fail_lead: int, outcome: Callable[[Path], CompileOutcome]) -> None:
        self.fail_lead = fail_lead
        self.outcome = outcome
        self.scratches: list[Path] = []
        self.seen: set[Path] = set()

    def __call__(self, tex: Path, pdf: Path) -> CompileOutcome:
        scratch = tex.parent
        if scratch not in self.scratches:
            self.scratches.append(scratch)
        lead = self.scratches.index(scratch) + 1
        is_base = scratch not in self.seen
        self.seen.add(scratch)
        if lead == self.fail_lead and is_base:
            return self.outcome(pdf)
        pdf.write_bytes(b"%PDF")
        return CompileOutcome(CompileReason.OK, pdf, 1, "ok")


def _compile_failed(pdf: Path) -> CompileOutcome:
    """A compile that RAN and produced nothing readable. On the pinned-only base nothing smaller
    has compiled, so it is unattributable ⇒ `PINNED_SET_COMPILE_FAILED`."""
    return CompileOutcome(CompileReason.COMPILE_FAILED, None, None, "synthetic failure")


def _binary_missing(pdf: Path) -> CompileOutcome:
    """`tectonic`/`pdfinfo` absent — typed separately by `evaluate_compile`, so it really is the
    machine ⇒ `COMPILE_INFRASTRUCTURE_FAILURE`."""
    return CompileOutcome(CompileReason.BINARY_MISSING, None, None, "", tool="tectonic")


def _over_budget(pdf: Path) -> CompileOutcome:
    """A clean compile whose page count exceeds the profile's `resume_max_pages` (1 here), which
    `evaluate_compile` turns into `PAGE_LIMIT_EXCEEDED` ⇒ `PINNED_SET_EXCEEDS_BUDGET`."""
    pdf.write_bytes(b"%PDF")
    return CompileOutcome(CompileReason.OK, pdf, 2, "ok")


#: (run-scoped availability member, the outcome its cause produces on the pinned base compile).
_LATE_RUN_SCOPED_CASES = (
    (ProjectionAvailability.PINNED_SET_UNRENDERABLE, _compile_failed),
    (ProjectionAvailability.TOOLCHAIN_UNAVAILABLE, _binary_missing),
    (ProjectionAvailability.PINNED_BUDGET_OVERFLOW, _over_budget),
)


@pytest.mark.parametrize(("availability", "outcome"), _LATE_RUN_SCOPED_CASES)
def test_a_late_run_scoped_projection_failure_still_reconciles(
    availability: ProjectionAvailability,
    outcome: Callable[[Path], CompileOutcome],
    env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Three shortlisted leads: lead 1 projects and tailors, lead 2's pinned-only compile discovers
    a run-invariant fault, lead 3 never gets a turn.

    The assertion that trips without `NOT_ATTEMPTED` is `projection["reconciled"] is True`: the
    stage entered at 3, advanced 1 and dropped nothing, so it reported `reconciled: false` and
    `payload["reconciles"]` followed it. The drop count is asserted as 2 — the lead the fault
    surfaced on AND the lead behind it — because counting only the untouched remainder would look
    balanced on a two-lead run and be wrong on every longer one.
    """
    ids = _ready(env, 3)
    _projected_env(env)
    _use(monkeypatch, _BaseCompileRunner(fail_lead=2, outcome=outcome))

    summary = _pipeline(env, tmp_path / "apps", top_n=3)

    # The typed cause, on the RUN, and said exactly once.
    assert summary.projection_availability is availability
    assert summary.fatal is not None and availability.value in summary.fatal
    assert summary.projection_outcomes == Counter(
        {ProjectionLeadOutcome.PROJECTED: 1, ProjectionLeadOutcome.NOT_ATTEMPTED: 2}
    )
    assert len(ids) == 3

    assert summary.funnel is not None
    payload = json.loads(summary.funnel.json_path.read_text(encoding="utf-8"))
    projection = _stages(payload)["projection"]
    assert projection["entered"] == 3
    assert projection["advanced"] == 1
    assert _drops(projection) == {"withheld_not_live": 0, "not_attempted": 2}
    # The regression, read off the frozen artifact rather than off the summary.
    assert projection["reconciled"] is True
    assert projection["derived"] is False

    # The FATAL line names the cause once; the stage's own bucket names none.
    markdown = summary.funnel.markdown_path.read_text(encoding="utf-8")
    fatal_lines = [line for line in markdown.splitlines() if line.startswith("- **FATAL:**")]
    assert len(fatal_lines) == 1, markdown
    assert availability.value in fatal_lines[0]
    assert "**not_attempted**: 2" in markdown

    # And nothing permanent was written for the abandoned leads, so they are still reachable
    # tomorrow: `_record_shortlist_dispositions` runs with `stage_completed=False` on a fatal.
    assert _disposition_count(get_engine(env)) == 1  # lead 1's own `built`, and nothing else


def test_a_late_template_failure_still_reconciles(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fourth run-scoped cause reachable from `select()`, and the only one that is not a
    `ProjectionIssue`: `compile_prefix` calls the real `LatexRenderer.emit`, which raises
    `TemplateArtifactError` when the resolved template still carries a leftover authoring
    placeholder. It reaches the loop as a FOREIGN exception and routes through
    `FOREIGN_AVAILABILITY` rather than through `ISSUE_SCOPE`, so it exercises the other half of
    `_projection_scope`.

    The break is real, not injected at the classification boundary: a `{config_dir}` template
    override carrying a `TODO` token is written once lead 1 has been tailored, and
    `resolve_template` is re-read on every `emit`, so lead 2's first projection render genuinely
    fails. It is hung on `run_tailor` rather than on `project_for_posting` deliberately — breaking
    it the moment lead 1 was PROJECTED would have tripped lead 1's own tailoring render first, and
    the run would have aborted through the tailor stage instead of through projection.
    """
    _ready(env, 3)
    _projected_env(env)
    _use(monkeypatch, _SelectRunner())

    real = runner_mod.run_tailor
    broken: list[int] = []

    def breaking_the_template(*args: object, **kwargs: object) -> object:
        result = real(*args, **kwargs)  # type: ignore[arg-type]
        if not broken:
            broken.append(1)
            (_config_dir(env) / "resume_template.tex").write_text(
                resolve_template(None) + "\nTODO\n", encoding="utf-8"
            )
        return result

    monkeypatch.setattr(runner_mod, "run_tailor", breaking_the_template)

    summary = _pipeline(env, tmp_path / "apps", top_n=3)

    assert broken  # non-vacuity: the override really was written
    assert summary.projection_availability is ProjectionAvailability.TEMPLATE_INVALID
    assert summary.projection_outcomes == Counter(
        {ProjectionLeadOutcome.PROJECTED: 1, ProjectionLeadOutcome.NOT_ATTEMPTED: 2}
    )

    assert summary.funnel is not None
    payload = json.loads(summary.funnel.json_path.read_text(encoding="utf-8"))
    projection = _stages(payload)["projection"]
    assert projection["entered"] == 3
    assert projection["advanced"] == 1
    assert _drops(projection) == {"withheld_not_live": 0, "not_attempted": 2}
    assert projection["reconciled"] is True


def test_a_projected_run_aborting_in_the_TAILOR_loop_still_reconciles(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same fourth case, reached through the OTHER family of run-scoped `break`s.

    The tailor loop aborts on a missing render tool, a broken template, an invalid master or an
    invalid persona registry — and on a projected run those leave the projection stage exactly as
    unbalanced as a projection-side abort does, because the leads behind the break never reached
    projection either. The lead the break happened ON is different: it was already counted
    `PROJECTED`, and the TAILOR stage is where it drops (that stage's own behaviour on a fatal
    abort is unchanged from the authored path and is not this stage's balance to close).
    """
    _ready(env, 3)
    _projected_env(env)
    _use(monkeypatch, _SelectRunner())

    real = runner_mod.run_tailor
    calls: list[int] = []

    def failing(*args: object, **kwargs: object) -> object:
        calls.append(1)
        if len(calls) == 2:
            raise RenderToolMissingError("tectonic gone")
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(runner_mod, "run_tailor", failing)

    summary = _pipeline(env, tmp_path / "apps", top_n=3)

    assert summary.fatal is not None and "render tool unavailable" in summary.fatal
    # TWO projected: lead 2 projected fine and then failed to tailor. ONE not attempted: lead 3.
    assert summary.projection_outcomes == Counter(
        {ProjectionLeadOutcome.PROJECTED: 2, ProjectionLeadOutcome.NOT_ATTEMPTED: 1}
    )

    assert summary.funnel is not None
    payload = json.loads(summary.funnel.json_path.read_text(encoding="utf-8"))
    projection = _stages(payload)["projection"]
    assert projection["entered"] == 3
    assert projection["advanced"] == 2
    assert _drops(projection) == {"withheld_not_live": 0, "not_attempted": 1}
    assert projection["reconciled"] is True


def test_an_authored_run_aborting_late_grows_no_projection_stage(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The negative control for the accounting above. The tailor loop's run-scoped `break`s predate
    `--project` and fire on an authored run too; they must not materialise a projection stage there.

    `run_tailor` is made to raise `RenderToolMissingError` on the second lead — the same `break` the
    projected run shares — and the counter must stay EMPTY, the stage ABSENT.
    """
    _ready(env, 3)
    _projected_env(env)

    real = runner_mod.run_tailor
    calls: list[int] = []

    def failing(*args: object, **kwargs: object) -> object:
        calls.append(1)
        if len(calls) == 2:
            raise RenderToolMissingError("tectonic gone")
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(runner_mod, "run_tailor", failing)

    summary = _pipeline(env, tmp_path / "apps", project=False, top_n=3)

    assert summary.fatal is not None and "render tool unavailable" in summary.fatal
    assert summary.projection_outcomes == Counter()
    assert summary.funnel is not None
    payload = json.loads(summary.funnel.json_path.read_text(encoding="utf-8"))
    assert "projection" not in _stages(payload)


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
