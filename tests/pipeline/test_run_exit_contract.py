"""T139 — the run's exit contract, executable (F10; `docs/program/RUN_CONTRACT.md`).

One row per outcome, each driven through the REAL entry point: `boardwatch run` invoked through
`CliRunner`, so every exit code below is `run_cmd`'s own mapping and none is restated here. The
`PipelineSummary` a row asserts on is the object `run_pipeline` actually handed back to the CLI,
captured by a pass-through spy on the name `run_cmd` calls: it forwards the call unchanged and
records what came back or what was raised.

**Characterization, not specification.** Every row pins what the code does TODAY, including where
F4/F5 say it is wrong. A deliberate correction moves its row in the same change, visibly.

**This module is the table, not a second copy of the tests behind it.** Each fatal cause already
has a test that pins its detail; a row reuses that test's seeding and names it, and adds only what
none of them asserts together: the exit code, `runs.status`, and exactly one new `runs` row. No
row reaches its fatal by assigning `summary.fatal` in a patch — that would test the patch. Where a
row injects a fault, it injects it UPSTREAM of the code that decides, and the decision is real.

`--no-check-liveness` on every invocation: without it the CLI builds a real network prober, and
liveness has no fatal arm to pin (a withheld lead is a non-fatal error).

A run's `summary.errors` is two lists end to end: the STAGE errors, and from `escalatable_from` on
the finalize block's soft alerts (B8's apply-lane volume alert fires on every run here, under 20
apply-lane leads). Rows assert the stage half, split at the code's own boundary: the slice the
run hands `escalate_alerts`, observed by a pass-through spy. Both alert URLs are unset, so that
call POSTs nothing and nothing is appended after the slice.
"""

from __future__ import annotations

import ast
import re
import shutil
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from filelock import FileLock
from sqlalchemy import Engine, select
from typer.testing import CliRunner, Result

import boardwatch.cli.run_cmd as run_cmd
import boardwatch.pipeline.runner as runner_mod
import boardwatch.scan.coordinator as coordinator
from boardwatch.cli.app import app
from boardwatch.core.settings import load_settings
from boardwatch.notify.alert_escalation import ALERT_URL_ENV
from boardwatch.notify.heartbeat import HEARTBEAT_URL_ENV
from boardwatch.pipeline.runner import PipelineSummary
from boardwatch.projection.run import ProjectionAvailability
from boardwatch.scan.coordinator import ScanLockHeldError, systemic_scan_outage_reason
from boardwatch.store import tables
from boardwatch.store.db import get_engine
from boardwatch.store.queries import RUN_FAILED, RUN_OK, insert_run
from tests.pipeline.test_ledger_advances_the_queue import _ready as _ready_unwatched
from tests.pipeline.test_pipeline_projection_leads import _projected_env, _SelectRunner, _use
from tests.pipeline.test_pipeline_projection_preflight import _config_dir, _install_projection
from tests.pipeline.test_pipeline_run import (
    _GH,
    SEEDED_BOARDS,
    _pipeline,
    _ready,
    _seed_posting,
)
from tests.pipeline.test_run_lease import _backdate_unfinished_runs, _count_schema_steps, _runs

cli = CliRunner()

RUNNER_SOURCE = Path(runner_mod.__file__)
RUN_CONTRACT = Path(__file__).resolve().parents[2] / "docs" / "program" / "RUN_CONTRACT.md"


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv(ALERT_URL_ENV, raising=False)
    monkeypatch.delenv(HEARTBEAT_URL_ENV, raising=False)
    return tmp_path / "data"


@dataclass
class _Returned:
    """What `run_pipeline` gave the CLI: exactly one of the two is set once it has run."""

    summary: PipelineSummary | None = None
    raised: BaseException | None = None


def _spy_run_pipeline(monkeypatch: pytest.MonkeyPatch) -> _Returned:
    seen = _Returned()
    real = run_cmd.run_pipeline

    def spy(*args: Any, **kwargs: Any) -> PipelineSummary:
        try:
            seen.summary = real(*args, **kwargs)
        except BaseException as exc:
            seen.raised = exc
            raise
        return seen.summary

    monkeypatch.setattr(run_cmd, "run_pipeline", spy)
    return seen


def _spy_escalation(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, ...]]:
    """The alert slice (`summary.errors[escalatable_from:]`) of every escalation call."""
    slices: list[tuple[str, ...]] = []
    real = runner_mod.escalate_alerts

    def spy(run_id: int, alerts: tuple[str, ...], **kwargs: Any) -> str | None:
        slices.append(tuple(alerts))
        return real(run_id, alerts, **kwargs)

    monkeypatch.setattr(runner_mod, "escalate_alerts", spy)
    return slices


def _stage_errors(errors: list[str], slices: list[tuple[str, ...]]) -> list[str]:
    """`errors` up to the escalation mark, given the one slice this run escalated."""
    assert len(slices) == 1, f"escalation ran {len(slices)} times"
    alerts = slices[0]
    stage, tail = errors[: len(errors) - len(alerts)], errors[len(errors) - len(alerts) :]
    assert tail == list(alerts), "something was appended after the escalation slice"
    return stage


def _spy_guard(monkeypatch: pytest.MonkeyPatch, name: str) -> list[object]:
    """Every value the named guard RETURNED this run, so a declining case proves it was reached."""
    returned: list[object] = []
    real = getattr(runner_mod, name)

    def spy(*args: Any, **kwargs: Any) -> object:
        result = real(*args, **kwargs)
        returned.append(result)
        return result

    monkeypatch.setattr(runner_mod, name, spy)
    return returned


def _run(data_dir: Path, out_root: Path, *extra: str) -> Result:
    return cli.invoke(
        app,
        ["--data-dir", str(data_dir), "run", "--no-check-liveness", "--out", str(out_root), *extra],
    )


@dataclass
class Invocation:
    """What one row's arrangement hands the shared test body."""

    args: tuple[str, ...]
    #: Asserts the row's cause against the summary the run returned and its stage errors.
    expect: Callable[[PipelineSummary, list[str]], None]
    context: AbstractContextManager[object] = field(default_factory=nullcontext)


@dataclass(frozen=True)
class Row:
    name: str
    #: The row of RUN_CONTRACT.md's "thirteen places" table this exercises; 0 for none.
    contract: int
    arrange: Callable[[Path, Path, pytest.MonkeyPatch], Invocation]


# --- the non-fatal rows: (exit 0, runs.status ok, one new row) --------------------------------


def _clean(env: Path, out_root: Path, monkeypatch: pytest.MonkeyPatch) -> Invocation:
    """`test_pipeline_run.test_a_clean_run_is_recorded_as_ok`, through the CLI."""
    _ready(env)

    def expect(summary: PipelineSummary, stage_errors: list[str]) -> None:
        assert summary.tailored, "the fixture produced no lead, so `ok` here proves nothing"
        assert stage_errors == []

    return Invocation(("--no-scan",), expect)


def _per_item_error(env: Path, out_root: Path, monkeypatch: pytest.MonkeyPatch) -> Invocation:
    """One of two leads' tailor raises. `test_run_pdf_gate.
    test_a_lead_that_cannot_compile_either_way_is_dropped_not_fatal` pins the deterministic
    variant; this is the generic `except Exception` arm."""
    doomed = _ready(env)
    kept = _seed_posting(env, slug="acme3")
    real = runner_mod.run_tailor

    def flaky(engine: Engine, settings: object, posting_id: int, **kw: Any) -> Any:
        if posting_id == doomed:
            raise RuntimeError("no extraction for this posting")
        return real(engine, settings, posting_id, **kw)

    monkeypatch.setattr(runner_mod, "run_tailor", flaky)

    def expect(summary: PipelineSummary, stage_errors: list[str]) -> None:
        assert [lead.posting_id for lead in summary.tailored] == [kept]
        assert summary.tailor_failed_ids == [doomed]
        assert stage_errors == [f"tailor: posting {doomed}: no extraction for this posting"]

    return Invocation(("--no-scan",), expect)


def _zero_output_declines(env: Path, out_root: Path, monkeypatch: pytest.MonkeyPatch) -> Invocation:
    """#10 reached and DECLINING: every eligible posting is a prior run's cache hit, so zero leads
    is provably right (`test_pipeline_run.
    test_steady_state_where_eligible_work_is_all_prior_run_cache_hits_is_not_fatal`)."""
    _ready(env)
    first = _pipeline(env, out_root)
    assert first.fatal is None and first.tailored, "run 1 produced no lead, so run 2 proves nothing"
    returned = _spy_guard(monkeypatch, "_zero_output_guard")

    def expect(summary: PipelineSummary, stage_errors: list[str]) -> None:
        assert summary.tailored == []
        assert returned == [None], f"the guard was not reached, or it fired: {returned}"
        assert stage_errors == []

    return Invocation(("--no-scan", "--top", "0"), expect)


def _cohort_declines(env: Path, out_root: Path, monkeypatch: pytest.MonkeyPatch) -> Invocation:
    """#11 reached and DECLINING: every shortlisted candidate became a lead."""
    _ready(env)
    returned = _spy_guard(monkeypatch, "_cohort_guard")

    def expect(summary: PipelineSummary, stage_errors: list[str]) -> None:
        assert summary.tailored
        assert returned == [None], f"the guard was not reached, or it fired: {returned}"
        assert stage_errors == []

    return Invocation(("--no-scan",), expect)


OK_ROWS = (
    Row("clean", 0, _clean),
    Row("per_item_error", 0, _per_item_error),
    Row("zero_output_guard_declines", 10, _zero_output_declines),
    Row("cohort_guard_declines", 11, _cohort_declines),
)


@pytest.mark.parametrize("row", OK_ROWS, ids=[row.name for row in OK_ROWS])
def test_a_non_fatal_outcome_exits_0_with_one_ok_row(
    row: Row, env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_root = tmp_path / "apps"
    invocation = row.arrange(env, out_root, monkeypatch)
    engine = get_engine(env)
    before = len(_runs(engine))
    returned = _spy_run_pipeline(monkeypatch)
    escalated = _spy_escalation(monkeypatch)

    with invocation.context:
        result = _run(env, out_root, *invocation.args)

    assert returned.raised is None, returned.raised
    summary = returned.summary
    assert summary is not None
    assert result.exit_code == 0, result.output
    runs = _runs(engine)
    assert len(runs) == before + 1, f"expected exactly one new run row: {runs}"
    run_id, status, finished_at, errors = runs[-1]
    assert run_id == summary.run_id
    assert (status, finished_at is not None) == (RUN_OK, True)
    assert summary.fatal is None, summary.fatal
    # A non-fatal error is recorded, never promoted: on these paths the row carries exactly
    # what the summary does, stage errors and alerts alike.
    assert list(errors or []) == summary.errors
    invocation.expect(summary, _stage_errors(summary.errors, escalated))


# --- the fatal rows: (exit 1, runs.status failed, one new row) --------------------------------


@contextmanager
def _every_board_answers(status: int) -> Iterator[None]:
    with respx.mock:
        for slug in SEEDED_BOARDS:
            respx.get(_GH.board_url(slug)).mock(return_value=httpx.Response(status))
        yield


def _scan_outage(env: Path, out_root: Path, monkeypatch: pytest.MonkeyPatch) -> Invocation:
    """#1. `test_pipeline_run.test_every_board_failing_is_a_systemic_outage_and_IS_fatal`, with
    the scan stage ON — the only row that runs it."""
    _ready(env)

    def expect(summary: PipelineSummary, stage_errors: list[str]) -> None:
        assert summary.fatal == systemic_scan_outage_reason(len(SEEDED_BOARDS))

    return Invocation((), expect, _every_board_answers(500))


def _projection_preflight(env: Path, out_root: Path, monkeypatch: pytest.MonkeyPatch) -> Invocation:
    """#2. `test_pipeline_projection_preflight.test_a_missing_approval_is_its_own_availability_member`."""
    _ready(env)
    _install_projection(_config_dir(env))  # no approval filed at all

    def expect(summary: PipelineSummary, stage_errors: list[str]) -> None:
        member = ProjectionAvailability.MISSING_APPROVAL
        assert summary.projection_availability is member
        assert summary.fatal is not None
        assert summary.fatal.startswith(f"projection unavailable: {member.value} (")

    return Invocation(("--no-scan", "--project"), expect)


def _no_profile(env: Path, out_root: Path, monkeypatch: pytest.MonkeyPatch) -> Invocation:
    """#3. `test_pipeline_run.test_cli_exits_one_when_the_run_is_fatally_broken`."""
    _seed_posting(env)  # no `init`, so no profile

    def expect(summary: PipelineSummary, stage_errors: list[str]) -> None:
        assert summary.fatal == "no profile configured; nothing ranked or tailored"

    return Invocation(("--no-scan",), expect)


def _profile_row_unusable(env: Path, out_root: Path, monkeypatch: pytest.MonkeyPatch) -> Invocation:
    """#4. `test_pipeline_run.test_a_corrupt_policy_column_is_a_run_fatal_not_a_silent_fallback`."""
    _ready(env)
    with get_engine(env).begin() as conn:
        conn.execute(
            tables.profile.update()
            .where(tables.profile.c.id == 1)
            .values(eligibility_policy_json={"experience_years": "blocker"})
        )

    def expect(summary: PipelineSummary, stage_errors: list[str]) -> None:
        assert summary.fatal is not None
        assert summary.fatal.startswith("profile row unusable: ")
        assert "eligibility_policy_json" in summary.fatal

    return Invocation(("--no-scan",), expect)


def _projection_in_loop(env: Path, out_root: Path, monkeypatch: pytest.MonkeyPatch) -> Invocation:
    """#5. `test_pipeline_projection_leads.test_a_run_scoped_cause_inside_the_loop_is_a_typed_fatal`:
    the pinned-only base compile fails, which is run-scoped although it surfaces per lead."""
    _ready_unwatched(env, 2)
    _projected_env(env)
    _use(monkeypatch, _SelectRunner(fail_lead=1, fail_base=True))

    def expect(summary: PipelineSummary, stage_errors: list[str]) -> None:
        member = ProjectionAvailability.PINNED_SET_UNRENDERABLE
        assert summary.projection_availability is member
        assert summary.fatal is not None
        assert summary.fatal.startswith(f"projection unavailable: {member.value} (posting ")

    return Invocation(("--no-scan", "--project", "--top", "2"), expect)


def _render_tool_missing(env: Path, out_root: Path, monkeypatch: pytest.MonkeyPatch) -> Invocation:
    """#6. `test_run_pdf_gate.test_binary_missing_is_a_run_level_fatal_not_a_per_lead_drop`."""
    _ready(env)
    monkeypatch.setattr("boardwatch.reports.tailor.shutil.which", lambda name: None)

    def expect(summary: PipelineSummary, stage_errors: list[str]) -> None:
        assert summary.fatal is not None
        assert summary.fatal.startswith("render tool unavailable: ")

    return Invocation(("--no-scan",), expect)


def _master_resume_invalid(env: Path, out_root: Path, monkeypatch: pytest.MonkeyPatch) -> Invocation:
    """#7. `test_run_pdf_gate.test_broken_master_resume_is_a_run_level_fatal_not_a_per_lead_drop`:
    a master résumé with no contact block."""
    _ready(env)
    (load_settings(data_dir=env).config_dir / "resume.yaml").write_text(
        'header:\n  - "Ada Lovelace"\neducation: []\nskill_groups: []\nentries:\n'
        '  - entry_id: "e1"\n    heading: "Senior Engineer"\n    bullets:\n'
        '      - bullet_id: "b1"\n        text: "Did a thing"\n',
        encoding="utf-8",
    )

    def expect(summary: PipelineSummary, stage_errors: list[str]) -> None:
        assert summary.fatal is not None
        assert summary.fatal.startswith("master résumé invalid: ")

    return Invocation(("--no-scan",), expect)


def _persona_registry_invalid(
    env: Path, out_root: Path, monkeypatch: pytest.MonkeyPatch
) -> Invocation:
    """#8. `test_persona_integration.test_broken_registry_aborts_the_run_loudly_not_a_silent_per_lead_drop`:
    a `{config_dir}/personas.yaml` declaring two defaults."""
    _ready(env)
    (load_settings(data_dir=env).config_dir / "personas.yaml").write_text(
        "personas:\n"
        "  - id: a\n"
        '    title: "A"\n'
        "    default: true\n"
        "    role_families: [general_swe]\n"
        "    skill_group_order: []\n"
        "    entries: null\n"
        "  - id: b\n"
        '    title: "B"\n'
        "    default: true\n"
        "    role_families: [backend]\n"
        "    skill_group_order: []\n"
        "    entries: null\n",
        encoding="utf-8",
    )

    def expect(summary: PipelineSummary, stage_errors: list[str]) -> None:
        assert summary.fatal is not None
        assert summary.fatal.startswith("persona registry invalid: ")

    return Invocation(("--no-scan",), expect)


def _every_lead_unrendered(env: Path, out_root: Path, monkeypatch: pytest.MonkeyPatch) -> Invocation:
    """#9. `test_pipeline_run.test_every_lead_failing_to_tailor_is_fatal`."""
    _ready(env)

    def boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("resume.yaml is missing")

    monkeypatch.setattr(runner_mod, "run_tailor", boom)

    def expect(summary: PipelineSummary, stage_errors: list[str]) -> None:
        assert summary.fatal == "every lead failed to project or tailor (1/1)"

    return Invocation(("--no-scan",), expect)


def _zero_output_fires(env: Path, out_root: Path, monkeypatch: pytest.MonkeyPatch) -> Invocation:
    """#10 FIRING. `test_pipeline_run.test_runner_fatal_on_silent_empty_day`: a new eligible posting
    judged this run, cut by `--top 0`, with the prior run's lead `built`."""
    _ready(env)
    first = _pipeline(env, out_root)
    assert first.fatal is None and first.tailored, "run 1 produced no lead, so run 2 proves nothing"
    _seed_posting(env, slug="acme3")

    def expect(summary: PipelineSummary, stage_errors: list[str]) -> None:
        assert summary.fatal == (
            "empty day not provably right: 1 of 1 candidate postings judged this run were "
            "neither delivered nor honestly suppressed"
        )

    return Invocation(("--no-scan", "--top", "0"), expect)


def _cohort_fires(env: Path, out_root: Path, monkeypatch: pytest.MonkeyPatch) -> Invocation:
    """#11 FIRING, through the REAL guard. `test_pipeline_run`'s `_fatal_cohort_guard` replaces
    the guard with a lambda, which pins the choke point but not the guard. Here the guard is
    untouched and the gate stage is made to LOSE one of two candidates — handing back a slate
    that is short by one while naming no exclusion, the compensating-bug class the guard exists
    for. Two candidates, so the survivor is delivered and neither #9 nor #10 can pre-empt it."""
    _ready(env)
    _seed_posting(env, slug="acme3")
    real = runner_mod.run_gate_stage
    lost: list[int] = []

    def lossy(engine: Engine, settings: object, leads: list[Any], **kw: Any) -> Any:
        kept, result = real(engine, settings, leads, **kw)
        lost.append(kept[-1].posting_id)
        return kept[:-1], result

    monkeypatch.setattr(runner_mod, "run_gate_stage", lossy)

    def expect(summary: PipelineSummary, stage_errors: list[str]) -> None:
        assert len(lost) == 1
        assert summary.fatal == f"cohort incomplete: 1 shortlisted candidates unaccounted: {lost[0]}"

    return Invocation(("--no-scan",), expect)


def _filesystem_truth(env: Path, out_root: Path, monkeypatch: pytest.MonkeyPatch) -> Invocation:
    """#12. `test_pipeline_run.test_a_lead_whose_folder_disappeared_after_tailoring_is_filesystem_truth_fatal`."""
    _ready(env)
    real = runner_mod.run_tailor

    def sabotage(*args: Any, **kwargs: Any) -> Any:
        result = real(*args, **kwargs)
        shutil.rmtree(kwargs["out_dir"])
        return result

    monkeypatch.setattr(runner_mod, "run_tailor", sabotage)

    def expect(summary: PipelineSummary, stage_errors: list[str]) -> None:
        assert summary.fatal == (
            "filesystem-truth: 0 lead folder(s) on disk vs 1 tailored artifact row(s) in the "
            f"store for run {summary.run_id}"
        )

    return Invocation(("--no-scan",), expect)


FATAL_ROWS = (
    Row("scan_outage", 1, _scan_outage),
    Row("projection_preflight", 2, _projection_preflight),
    Row("no_profile", 3, _no_profile),
    Row("profile_row_unusable", 4, _profile_row_unusable),
    Row("projection_in_loop", 5, _projection_in_loop),
    Row("render_tool_unavailable", 6, _render_tool_missing),
    Row("master_resume_invalid", 7, _master_resume_invalid),
    Row("persona_registry_invalid", 8, _persona_registry_invalid),
    Row("every_lead_unrendered", 9, _every_lead_unrendered),
    Row("zero_output_guard_fires", 10, _zero_output_fires),
    Row("cohort_guard_fires", 11, _cohort_fires),
    Row("filesystem_truth", 12, _filesystem_truth),
)


@pytest.mark.parametrize("row", FATAL_ROWS, ids=[row.name for row in FATAL_ROWS])
def test_each_fatal_cause_exits_1_with_one_failed_row(
    row: Row, env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_root = tmp_path / "apps"
    invocation = row.arrange(env, out_root, monkeypatch)
    engine = get_engine(env)
    before = len(_runs(engine))
    returned = _spy_run_pipeline(monkeypatch)
    escalated = _spy_escalation(monkeypatch)

    with invocation.context:
        result = _run(env, out_root, *invocation.args)

    assert returned.raised is None, returned.raised
    summary = returned.summary
    assert summary is not None
    assert result.exit_code == 1, result.output
    runs = _runs(engine)
    assert len(runs) == before + 1, f"expected exactly one new run row: {runs}"
    run_id, status, finished_at, errors = runs[-1]
    assert run_id == summary.run_id
    assert (status, finished_at is not None) == (RUN_FAILED, True)
    assert summary.fatal is not None
    invocation.expect(summary, _stage_errors(summary.errors, escalated))
    # The row says WHY, once: the finally's choke point records any reason no stage recorded.
    carrying = [note for note in errors or [] if note.endswith(summary.fatal)]
    assert len(carrying) == 1, errors


# --- #13, the crash path: a raise after the row exists ---------------------------------------


@pytest.mark.parametrize(
    ("error", "exit_code"),
    [(RuntimeError("taxonomy.yaml is malformed"), 1), (KeyboardInterrupt(), 130)],
    ids=["exception", "keyboard_interrupt"],
)
def test_a_raise_after_the_row_exists_fails_the_row_and_propagates(
    error: BaseException,
    exit_code: int,
    env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`except BaseException`, not `except Exception`: a Ctrl-C closes the row as `failed` with
    its reason exactly as an exception does. Raised from `_count_evaluations`, the last call in
    the try — the seam `test_pipeline_run`'s crash tests use. The exit code is what the CLI
    framework makes of the propagating raise: `run_cmd` maps neither."""
    _ready(env)

    def boom(*_a: object, **_k: object) -> None:
        raise error

    monkeypatch.setattr(runner_mod, "_count_evaluations", boom)
    engine = get_engine(env)
    before = len(_runs(engine))
    returned = _spy_run_pipeline(monkeypatch)
    escalated = _spy_escalation(monkeypatch)

    result = _run(env, tmp_path / "apps", "--no-scan")

    assert returned.raised is error, "the raise did not propagate out of run_pipeline unchanged"
    assert result.exit_code == exit_code, result.output
    runs = _runs(engine)
    assert len(runs) == before + 1, f"expected exactly one new run row: {runs}"
    _, status, finished_at, errors = runs[-1]
    assert (status, finished_at is not None) == (RUN_FAILED, True)
    # The reason, once, ahead of the finalize block's alerts — which still ran: the `finally`
    # completes the whole chain while the raise is propagating.
    assert _stage_errors(list(errors or []), escalated) == [f"pipeline: aborted: {error!r}"]


# --- contention: (exit 2, no new row, no other write) ----------------------------------------


def _every_row(engine: Engine) -> dict[str, list[tuple[Any, ...]]]:
    with engine.connect() as conn:
        return {
            table.name: [tuple(row) for row in conn.execute(select(table))]
            for table in tables.metadata.sorted_tables
        }


def test_a_held_lease_exits_2_and_writes_nothing(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T133's `test_a_contended_pipeline_reaps_nothing`, through the CLI and widened from the
    `runs` table to every table: a backdated unfinished row a reap WOULD close is planted, and
    the refused run must leave it — and everything else — exactly as it was."""
    monkeypatch.setattr(coordinator, "RECLAIM_WINDOW_SECONDS", 0.0)  # T133: fail fast everywhere
    _ready(env)
    engine = get_engine(env)
    insert_run(engine)
    _backdate_unfinished_runs(engine)
    before = _every_row(engine)
    schema_steps = _count_schema_steps(monkeypatch)
    returned = _spy_run_pipeline(monkeypatch)
    out_root = tmp_path / "apps"
    holder = FileLock(str(load_settings(data_dir=env).data_dir / "scan.lock"))
    holder.acquire()
    try:
        result = _run(env, out_root)  # the scan ON: the unattended driver's own invocation
    finally:
        holder.release()

    assert result.exit_code == 2, result.output
    assert isinstance(returned.raised, ScanLockHeldError), returned.raised
    assert _every_row(engine) == before, "the refused run wrote to the store (row, reap or other)"
    assert schema_steps == [], "the refused run ran a schema step"
    assert not out_root.exists(), "the refused run created its output root"


# --- the drift check: the contract table is re-derived from the code, every run ---------------


def _fatal_assignments(source: str) -> int:
    """Every store to `summary.fatal`, counted in the AST: an `=`, an annotated or augmented
    assignment, or an unpacking target — and never a comparison, which the doc's own grep
    (`summary\\.fatal\\s*=`) would also match."""
    return sum(
        1
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Attribute)
        and isinstance(node.ctx, ast.Store)
        and node.attr == "fatal"
        and isinstance(node.value, ast.Name)
        and node.value.id == "summary"
    )


#: Matched on its shape rather than its number word, so the heading renamed for a fourteenth row
#: is still found.
_TABLE_HEADING = re.compile(r"^## The \w+ places `summary\.fatal` is set$")


def _contract_rows(text: str) -> int:
    lines = text.splitlines()
    starts = [index for index, line in enumerate(lines) if _TABLE_HEADING.match(line)]
    assert len(starts) == 1, "RUN_CONTRACT.md's fatal-assignment table heading was not found once"
    table: list[str] = []
    for line in lines[starts[0] + 1 :]:
        if line.startswith("|"):
            table.append(line)
        elif table or line.startswith("## "):
            break
    assert len(table) > 2, "the heading has no table under it"
    return len(table) - 2  # the header row and the separator


def test_the_run_contract_table_has_one_row_per_fatal_assignment() -> None:
    in_code = _fatal_assignments(RUNNER_SOURCE.read_text(encoding="utf-8"))
    in_doc = _contract_rows(RUN_CONTRACT.read_text(encoding="utf-8"))

    assert in_code == in_doc, (
        f"runner.py assigns summary.fatal in {in_code} places and RUN_CONTRACT.md's table has "
        f"{in_doc} rows — one of them drifted"
    )
    # And this module is the executable form of that table: one row per contract row, with
    # #13 (the crash path) pinned by the parametrized crash test above.
    pinned = {row.contract for row in FATAL_ROWS} | {13}
    assert pinned == set(range(1, in_code + 1)), sorted(pinned)
