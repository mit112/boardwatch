"""`boardwatch run` — the pipeline run row (D-016, P0 item 0).

What is under test is ownership, not the stages themselves: one row spans scan, eligibility
and tailor, `finished_at` means "the pipeline is done" rather than "scan is done", and a run
that aborts is still closed out rather than left dangling for `doctor` to call still-running.
"""

import json
from datetime import timedelta
from pathlib import Path
from time import perf_counter, sleep

import httpx
import pytest
import respx
from filelock import FileLock
from rich.console import Console
from sqlalchemy import func, insert, select
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.core.clock import utcnow
from boardwatch.core.settings import load_settings
from boardwatch.pipeline.runner import _cohort_guard, _slug, _zero_output_guard, run_pipeline
from boardwatch.providers.registry import build_providers
from boardwatch.scan.coordinator import ScanLockHeldError
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.ledger_queries import record_disposition
from boardwatch.store.queries import RUN_FAILED
from tests.conftest import write_test_resume_template

# The seeded company is a real watched greenhouse board, so any test that runs the scan stage
# must mock it. Three of these tests previously reached boards-api.greenhouse.io for real,
# which made them slow and network-dependent — every other scan test in the repo mocks.
_GH = build_providers()["greenhouse"]
# `init` registers a watched "acme" board of its own, on top of the seeded "acme2". Both must
# be mocked or the test reaches the network and the failure counts include an accident.
SEEDED_BOARDS = ("acme", "acme2")
HEALTHY_BODY = b'{"jobs": []}'

runner = CliRunner()

INIT_INPUT = "3\nacme\nBackend engineer: Python, Go, PostgreSQL.\n\n\n\nn\nn\n"
BODY = "We are hiring a backend engineer to work on Python and PostgreSQL services."


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


def _run_count(engine: object) -> int:
    with engine.connect() as conn:  # type: ignore[attr-defined]
        return int(conn.execute(select(func.count()).select_from(tables.runs)).scalar_one())


def _cli(data_dir: Path, args: list[str], stdin: str | None = None):
    return runner.invoke(app, ["--data-dir", str(data_dir), *args], input=stdin)


def _seed_posting(data_dir: Path, *, slug: str = "acme2") -> int:
    engine = get_engine(data_dir)
    ensure_schema(engine)
    now = utcnow()
    with engine.begin() as conn:
        company_id = int(
            conn.execute(
                insert(tables.companies).values(
                    name="Acme", provider="greenhouse", slug=slug, source="user", watched=True
                )
            ).inserted_primary_key[0]
        )
        job_id = int(
            conn.execute(insert(tables.jobs).values(created_at=now)).inserted_primary_key[0]
        )
        posting_id = int(
            conn.execute(
                insert(tables.postings).values(
                    company_id=company_id, provider_posting_id=f"p-{slug}",
                    title="Backend Engineer", normalized_title="backend engineer",
                    url="https://example.test/j", locations_json=["Remote"],
                    remote_policy="remote", first_seen_at=now, last_seen_at=now,
                    status="open", consecutive_missing=0, content_hash=f"h-{slug}",
                    body_text=BODY, job_id=job_id,
                )
            ).inserted_primary_key[0]
        )
        conn.execute(
            insert(tables.posting_versions).values(
                posting_id=posting_id, content_hash=f"h-{slug}", body_text=BODY,
                captured_at=now, capture_reason="new",
            )
        )
    return posting_id


def _add_live_board(data_dir: Path) -> None:
    """A second watched board that answers 200, so "every board failed" is not the default."""
    with get_engine(data_dir).begin() as conn:
        conn.execute(
            insert(tables.companies).values(
                name="Live", provider="greenhouse", slug="live", source="user", watched=True
            )
        )


def _ready(data_dir: Path) -> int:
    posting_id = _seed_posting(data_dir)
    assert _cli(data_dir, ["init"], INIT_INPUT).exit_code == 0
    assert _cli(data_dir, ["tailor", "init"]).exit_code == 0
    # T2: `tailor init` does not scaffold `resume_template.tex`, and `resolve_template` no longer
    # falls back to the bundled default for a real config dir missing it — so a pipeline run that
    # reaches tailoring/rendering needs one on disk, as a properly set-up user's config dir would.
    write_test_resume_template(load_settings(data_dir=data_dir).config_dir)
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


def test_one_run_row_spans_eligibility_and_tailor(env: Path, tmp_path: Path) -> None:
    _ready(env)
    out_root = tmp_path / "apps"

    summary = _pipeline(env, out_root)

    engine = get_engine(env)
    with engine.connect() as conn:
        runs = conn.execute(select(tables.runs.c.id, tables.runs.c.finished_at)).all()
        eval_runs = {
            r.run_id for r in conn.execute(select(tables.eligibility_evaluations.c.run_id)).all()
        }
        art_runs = {r.run_id for r in conn.execute(select(tables.artifacts.c.run_id)).all()}

    assert len(runs) == 1, "the pipeline minted more than one run"
    assert runs[0].id == summary.run_id
    assert runs[0].finished_at is not None, "the pipeline did not finish its own run"
    assert eval_runs == {summary.run_id}
    assert art_runs == {summary.run_id}, "an artifact escaped the pipeline's run"


def test_the_summary_counts_evaluations_through_a_genuinely_different_path(
    env: Path, tmp_path: Path
) -> None:
    """Counted through a different path than the one that produced it (CLAUDE.md).

    An earlier version of this test re-ran `_count_evaluations`' own query and compared the
    result to itself — X == X, which cannot fail. The independent path is the evaluations'
    parent `eligibility_inputs` rows: one distinct posting_version per evaluation, reached by
    a join rather than by the run_id filter the summary used.
    """
    _ready(env)

    summary = _pipeline(env, tmp_path / "apps")

    with get_engine(env).connect() as conn:
        via_inputs = conn.execute(
            select(func.count(func.distinct(tables.eligibility_inputs.c.posting_version_id)))
            .select_from(
                tables.eligibility_inputs.join(
                    tables.eligibility_evaluations,
                    tables.eligibility_evaluations.c.input_id == tables.eligibility_inputs.c.id,
                )
            )
        ).scalar_one()
    assert summary.evaluated > 0
    assert summary.evaluated == via_inputs


def test_leads_land_in_a_dated_folder_per_posting(env: Path, tmp_path: Path) -> None:
    _ready(env)
    out_root = tmp_path / "apps"

    summary = _pipeline(env, out_root)

    assert summary.tailored, "nothing was tailored, so this test proves nothing"
    for lead in summary.tailored:
        assert lead.out_dir.is_dir()
        assert lead.out_dir.parent.parent == out_root
        assert lead.out_dir.parent.name.count("-") == 2  # YYYY-MM-DD


def test_a_contended_pipeline_writes_no_run_row_at_all(env: Path, tmp_path: Path) -> None:
    """`boardwatch run` inherits `scan`'s "a rejected scan writes nothing" contract.

    The scan stage creates the row, inside the lock. So contention cannot strand a row — which
    is stronger than closing one out, and is why the pipeline does not mint before the lock.
    """
    _ready(env)
    settings = load_settings(data_dir=env)
    engine = get_engine(env)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    before = _run_count(engine)
    holder = FileLock(str(settings.data_dir / "scan.lock"))
    holder.acquire()
    try:
        with pytest.raises(ScanLockHeldError):
            run_pipeline(
                engine,
                settings,
                console=Console(quiet=True),
                out_root=tmp_path / "apps",
                resume_path=settings.config_dir / "resume.yaml",
            )
    finally:
        holder.release()

    assert _run_count(engine) == before, "a contended pipeline stranded a run row"


def test_an_unexpected_stage_failure_still_closes_the_run_row(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dangling run is reported by `doctor` as in-progress forever, one more per retry."""
    _ready(env)
    settings = load_settings(data_dir=env)
    engine = get_engine(env)

    import boardwatch.pipeline.runner as runner_mod

    def boom(*_args: object, **_kw: object) -> None:
        raise RuntimeError("taxonomy.yaml is malformed")

    monkeypatch.setattr(runner_mod, "run_tailor", boom)
    with pytest.raises(RuntimeError):
        # The tailor loop catches Exception per lead, so make the failure escape the loop
        # instead: a raise from finish-time accounting is the same unguarded window.
        monkeypatch.setattr(runner_mod, "_count_evaluations", boom)
        run_pipeline(
            engine,
            settings,
            console=Console(quiet=True),
            out_root=tmp_path / "apps",
            resume_path=settings.config_dir / "resume.yaml",
            skip_scan=True,
        )

    with engine.connect() as conn:
        finished = conn.execute(select(tables.runs.c.finished_at)).scalars().all()
    assert finished, "no run row was created, so this test proves nothing"
    assert all(f is not None for f in finished), "an exception left a run row dangling"


def test_a_lead_that_fails_to_tailor_leaves_no_empty_folder_behind(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Listing the dated directory is the obvious independent count; a husk would inflate it."""
    _ready(env)
    out_root = tmp_path / "apps"

    import boardwatch.pipeline.runner as runner_mod

    def boom(*_args: object, **_kw: object) -> None:
        raise RuntimeError("no extraction for this posting")

    monkeypatch.setattr(runner_mod, "run_tailor", boom)
    summary = _pipeline(env, out_root)

    assert summary.tailor_failed > 0, "nothing failed, so this test proves nothing"
    assert summary.tailored == []
    # Directories only: a lead is a FOLDER, and the dated directory also holds the run's
    # funnel artifact, which is a file and is meant to be there even when every lead failed.
    day_dirs = [p for p in out_root.glob("*/*") if p.is_dir()] if out_root.exists() else []
    assert day_dirs == [], f"empty husks left behind: {day_dirs}"


def _scan_pipeline(env: Path, out_root: Path, *, status: int, extra_board: bool = False):
    """Run the pipeline with the scan stage ON. Every seeded board answers `status`.

    `extra_board` adds one healthy board, so "some boards failed" is distinguishable from
    "every board failed" — the two cases have opposite fatality.
    """
    settings = load_settings(data_dir=env)
    with respx.mock:
        for slug in SEEDED_BOARDS:
            respx.get(_GH.board_url(slug)).mock(return_value=httpx.Response(status))
        if extra_board:
            respx.get(_GH.board_url("live")).mock(
                return_value=httpx.Response(200, content=HEALTHY_BODY)
            )
        return run_pipeline(
            get_engine(env),
            settings,
            console=Console(quiet=True),
            out_root=out_root,
            resume_path=settings.config_dir / "resume.yaml",
        )


def test_a_dead_board_is_reported_but_does_not_fail_the_run(env: Path, tmp_path: Path) -> None:
    """A few dead boards are the norm across 85 watched; `scan` itself exits 0 for them.

    The board must actually FAIL — an unknown *provider* takes a different branch that
    deliberately never increments `failed`, so it would leave `scan_boards_failed` at 0 and
    pin nothing.
    """
    _ready(env)
    _add_live_board(env)

    summary = _scan_pipeline(env, tmp_path / "apps", status=500, extra_board=True)

    assert summary.scan_boards_failed == len(SEEDED_BOARDS), "no board actually failed"
    assert summary.scan_boards_complete == 1, "the healthy board did not complete"
    assert any("acme2" in e for e in summary.errors), summary.errors
    assert summary.fatal is None, "dead boards alongside a healthy one failed the whole run"


def test_every_board_failing_is_a_systemic_outage_and_IS_fatal(env: Path, tmp_path: Path) -> None:
    """CLAUDE.md: "systemic outage => fatal (prevents the silent empty day)". Bar metric B5.

    Not one board completing is DNS or the network, not a few rotten slugs — and reporting
    success for it is precisely the silent empty day.
    """
    _ready(env)

    summary = _scan_pipeline(env, tmp_path / "apps", status=500)

    assert summary.scan_boards_complete == 0
    assert summary.fatal is not None, "a total scan outage was reported as success"
    assert "systemic" in summary.fatal


def test_scan_errors_are_recorded_once_not_twice(env: Path, tmp_path: Path) -> None:
    """The scan stage persists its own errors; finish_run appends, so passing them again dupes."""
    _ready(env)
    _add_live_board(env)

    summary = _scan_pipeline(env, tmp_path / "apps", status=500, extra_board=True)

    with get_engine(env).connect() as conn:
        persisted = conn.execute(
            select(tables.runs.c.errors_json).where(tables.runs.c.id == summary.run_id)
        ).scalar_one()
    dead = [e for e in (persisted or []) if "acme2" in e]
    assert len(dead) == 1, f"scan errors recorded {len(dead)} times: {persisted}"


def test_every_lead_failing_to_tailor_is_fatal(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Zero leads from a NON-empty shortlist is a broken résumé path, not an honest empty day."""
    _ready(env)

    import boardwatch.pipeline.runner as runner_mod

    def boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("resume.yaml is missing")

    monkeypatch.setattr(runner_mod, "run_tailor", boom)
    summary = _pipeline(env, tmp_path / "apps")

    assert summary.shortlist.shortlisted > 0, "nothing was shortlisted, so this proves nothing"
    assert summary.tailored == []
    assert summary.fatal is not None, "a run that produced no lead at all reported success"


def test_a_late_fatal_leaves_no_seen_disposition_behind(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T6. `seen` suppresses a job for its TTL on the strength of having presented it. The
    disposition write sat ABOVE the four late fatals, so a run that ended in one still
    banked `seen` for every surfaced job — the exact case the tier is gated against, and
    the reason the ranker was told not to write `seen` itself (`record_surfaced=False`).
    A broken résumé path would suppress tomorrow's shortlist too.
    """
    _ready(env)

    import boardwatch.pipeline.runner as runner_mod

    def boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("tectonic is not installed")

    monkeypatch.setattr(runner_mod, "run_tailor", boom)
    summary = _pipeline(env, tmp_path / "apps")

    assert summary.shortlist.shortlisted > 0, "nothing was shortlisted, so this proves nothing"
    assert summary.fatal is not None
    assert "every lead failed to project or tailor" in summary.fatal
    with get_engine(env).connect() as conn:
        assert (
            conn.execute(select(tables.runs.c.status).where(tables.runs.c.id == summary.run_id))
            .scalar_one()
            == RUN_FAILED
        )
        seen = conn.execute(
            select(func.count())
            .select_from(tables.job_dispositions)
            .where(
                tables.job_dispositions.c.run_id == summary.run_id,
                tables.job_dispositions.c.disposition == "seen",
            )
        ).scalar_one()
    assert seen == 0, "a run that ended in a late fatal suppressed its own shortlist"


def test_cli_exits_one_when_the_run_is_fatally_broken(env: Path, tmp_path: Path) -> None:
    """The exit-1 side of the contract this change redefines; 0 and 2 are pinned elsewhere."""
    _seed_posting(env)  # no `init`, so no profile: fatal

    result = _cli(env, ["run", "--no-scan", "--out", str(tmp_path / "apps")])

    assert result.exit_code == 1, result.output
    assert "FAILED" in result.output


def test_a_crash_mid_pipeline_is_recorded_not_left_looking_clean(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Closing the row without recording why makes a crash indistinguishable from an empty run."""
    _ready(env)

    import boardwatch.pipeline.runner as runner_mod

    def boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("taxonomy.yaml is malformed")

    monkeypatch.setattr(runner_mod, "_count_evaluations", boom)
    with pytest.raises(RuntimeError):
        _pipeline(env, tmp_path / "apps")

    with get_engine(env).connect() as conn:
        errors = conn.execute(select(tables.runs.c.errors_json)).scalars().all()
    assert any(
        e and any("aborted" in item for item in e) for e in errors
    ), f"the crash left no trace in the ledger: {errors}"


def test_a_crash_mid_pipeline_is_recorded_in_the_ARTIFACT_not_only_the_ledger(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Gate P0 asks the artifact to be answerable ALONE, so the ledger is not enough.

    The abort was recorded only in `stage_errors`, which reaches the `runs` row. The funnel is
    built from the summary, so a crashed run's artifact reported RECONCILES with no FATAL line
    and an empty Errors section — the exact "indistinguishable from a clean empty run" defect,
    one layer up from where it was previously fixed.
    """
    _ready(env)
    out_root = tmp_path / "apps"

    import boardwatch.pipeline.runner as runner_mod

    def boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("taxonomy.yaml is malformed")

    monkeypatch.setattr(runner_mod, "_count_evaluations", boom)
    with pytest.raises(RuntimeError):
        _pipeline(env, out_root)

    payload = json.loads(
        next((out_root / utcnow().date().isoformat()).glob("funnel-*.json")).read_text()
    )
    assert payload["fatal"] is not None, "a crashed run's artifact claimed no fatal condition"
    assert "aborted" in payload["fatal"]
    assert any("aborted" in err for err in payload["errors"])


def test_a_crashed_run_is_recorded_as_failed_not_left_reading_running(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`status` must agree with the artifact's FATAL line (P0 item 4).

    The crash path sets `summary.fatal` before re-raising, so the `finally` has to close the
    row as `failed`. If it closed as `ok`, the ledger would contradict the artifact for the
    same run — and the whole point of an exit status is that a reader who never opens the
    artifact still learns the run did not deliver.
    """
    _ready(env)
    out_root = tmp_path / "apps"

    import boardwatch.pipeline.runner as runner_mod

    def boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("taxonomy.yaml is malformed")

    monkeypatch.setattr(runner_mod, "_count_evaluations", boom)
    with pytest.raises(RuntimeError):
        _pipeline(env, out_root)

    with get_engine(env).connect() as conn:
        row = conn.execute(
            select(tables.runs.c.status, tables.runs.c.finished_at)
            .order_by(tables.runs.c.id.desc())
            .limit(1)
        ).one()
    assert row.status == "failed", f"a crashed run was closed as {row.status!r}"
    assert row.finished_at is not None, "the crashed run row was left open"

    payload = json.loads(
        next((out_root / utcnow().date().isoformat()).glob("funnel-*.json")).read_text()
    )
    assert (payload["fatal"] is not None) == (row.status == "failed"), (
        "the ledger's status and the artifact's FATAL line disagree about the same run"
    )


def test_a_failing_finish_run_does_not_take_the_rest_of_the_finally_with_it(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T11. `finish_run` sits FIRST in the `finally` chain and was unguarded, so a raise there
    replaced the run's own outcome with a store error and skipped everything after it: the
    funnel artifact, the delivery queue, the morning digest, the soft detectors and the
    heartbeat. The run row would then sit `running` until the next run reaped it, with no
    artifact anywhere to say why.

    What this proves is the SECOND half of the ticket's two readings. `finish_run` is patched
    to raise unconditionally, so the row genuinely cannot be finished — the assertion is that
    the FUNNEL is still written and the run's ORIGINAL fatal reason survives on the summary,
    rather than being replaced by the store error.
    """
    _ready(env)

    import boardwatch.pipeline.runner as runner_mod

    def tailor_boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("tectonic is not installed")

    def finish_boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("database is locked")

    monkeypatch.setattr(runner_mod, "run_tailor", tailor_boom)
    monkeypatch.setattr(runner_mod, "finish_run", finish_boom)
    out_root = tmp_path / "apps"
    summary = _pipeline(env, out_root)

    assert summary.fatal is not None
    assert "every lead failed to project or tailor" in summary.fatal, (
        "the store error replaced the run's own reason"
    )
    assert "database is locked" not in summary.fatal
    assert any("finish_run" in e for e in summary.errors), (
        "a failure to close the run row was not recorded anywhere"
    )
    funnels = list(out_root.rglob(f"funnel-{summary.run_id}.md"))
    assert funnels, "the funnel artifact was skipped because finish_run raised above it"


def test_a_clean_run_is_recorded_as_ok(env: Path, tmp_path: Path) -> None:
    """The other side of the same column: `failed` means nothing if nothing is ever `ok`."""
    _ready(env)
    summary = _pipeline(env, tmp_path / "apps")
    # Without this the test still passes if the fixture ever drifts to a zero-lead shortlist,
    # because the all-leads-failed fatal is gated on `shortlisted > 0` — it would then be
    # asserting `ok` over a run that produced nothing.
    assert summary.tailored, "the fixture produced no leads, so `ok` here proves nothing"

    with get_engine(env).connect() as conn:
        row = conn.execute(
            select(tables.runs.c.status).order_by(tables.runs.c.id.desc()).limit(1)
        ).one()
    assert row.status == "ok", f"a clean run was closed as {row.status!r}"


def test_a_stale_prior_run_is_reaped_before_a_new_no_scan_run_starts(
    env: Path, tmp_path: Path
) -> None:
    """P3 slice 2 (D-046): the reaper drains a crashed prior run's phantom `running` row at
    pipeline start, before this run mints its own — and a healthy run still exits 0."""
    _ready(env)
    engine = get_engine(env)
    with engine.begin() as conn:
        stale_id = int(
            conn.execute(
                insert(tables.runs).values(
                    started_at=utcnow() - timedelta(hours=25), boards_attempted=0
                )
            ).inserted_primary_key[0]
        )

    result = _cli(env, ["run", "--no-scan", "--out", str(tmp_path / "apps")])

    assert result.exit_code == 0, result.output
    with engine.connect() as conn:
        rows = {
            r.id: (r.status, r.finished_at)
            for r in conn.execute(
                select(tables.runs.c.id, tables.runs.c.status, tables.runs.c.finished_at)
            ).all()
        }
    assert rows[stale_id] == ("failed", rows[stale_id][1])
    assert rows[stale_id][1] is not None, "the stale row's finished_at was not stamped"
    new_id = max(rows)
    assert new_id != stale_id, "the new run reused the stale run's id"
    assert rows[new_id][0] == "ok", f"the new run reconciled as {rows[new_id][0]!r}, not ok"
    assert rows[new_id][1] is not None


def test_a_run_row_nobody_closed_still_reads_running(env: Path) -> None:
    """What an un-updated row MEANS, pinned (P0 item 4).

    A SIGKILL never reaches the `finally`, so no code ever sets this row's status. The column
    default is the only thing that decides what such a row says. `running` with `finished_at`
    NULL is the killed-run signature; a default of `ok` would launder it into a clean run.
    """
    ensure_schema(get_engine(env))
    with get_engine(env).begin() as conn:
        run_id = conn.execute(
            insert(tables.runs).values(started_at=utcnow(), boards_attempted=0)
        ).inserted_primary_key[0]
        row = conn.execute(
            select(tables.runs.c.status, tables.runs.c.finished_at).where(
                tables.runs.c.id == run_id
            )
        ).one()
    assert row.status == "running", f"an unclosed run row read {row.status!r}"
    assert row.finished_at is None


def test_an_abort_during_the_scan_stage_still_closes_the_run_row(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The scan creates the row, so the pipeline's try/finally cannot cover this window."""
    _ready(env)
    import boardwatch.scan.coordinator as coord

    def boom(*_a: object, **_k: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(coord, "_scan_body", boom)
    settings = load_settings(data_dir=env)
    with pytest.raises(KeyboardInterrupt):
        run_pipeline(
            get_engine(env),
            settings,
            console=Console(quiet=True),
            out_root=tmp_path / "apps",
            resume_path=settings.config_dir / "resume.yaml",
        )

    with get_engine(env).connect() as conn:
        rows = conn.execute(
            select(tables.runs.c.finished_at, tables.runs.c.status)
        ).all()
    assert rows, "no run row was created, so this test proves nothing"
    assert all(r.finished_at is not None for r in rows), (
        "an abort during scan left a run row dangling"
    )
    # Closing the row is not enough. `doctor` only looks for a NULL finished_at, so a scan
    # abort recorded as `ok` is invisible everywhere — and under `boardwatch run` the scan is
    # called OUTSIDE the pipeline's try, so no funnel artifact is written to contradict it.
    assert all(r.status == "failed" for r in rows), (
        f"an aborted scan was recorded as {[r.status for r in rows]}, not failed"
    )


def test_no_profile_is_a_real_run_that_produced_nothing_not_a_crash(
    env: Path, tmp_path: Path
) -> None:
    _seed_posting(env)  # deliberately no `init`, so there is no profile

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.tailored == []
    # None, not a zeroed count: the ranker never executed, so its considered population is
    # unknown rather than zero. A zeroed instance made the funnel assert the opposite.
    assert summary.shortlist is None
    assert any("no profile" in e for e in summary.errors)
    with get_engine(env).connect() as conn:
        finished = conn.execute(select(tables.runs.c.finished_at)).scalar_one()
    assert finished is not None


def test_a_corrupt_policy_column_is_a_run_fatal_not_a_silent_fallback(
    env: Path, tmp_path: Path
) -> None:
    """T7. An unreadable `eligibility_policy_json` used to parse down to an empty Policy,
    which MATERIALISES the catalog defaults: only work_auth is a `blocker`, the other five
    families fall back to `preference`, and `preference` can never yield `ineligible`. So
    the run reported success while clearing postings the user's own policy rejects. The
    row is written directly here because every CLI writer validates before storing — the
    only way in is a hand edit or an older/newer schema, which is exactly the live case.
    """
    _ready(env)
    engine = get_engine(env)
    with engine.begin() as conn:
        conn.execute(
            tables.profile.update()
            .where(tables.profile.c.id == 1)
            .values(eligibility_policy_json={"experience_years": "blocker"})
        )

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.fatal is not None, "a run under an unusable policy reported success"
    assert "eligibility_policy_json" in summary.fatal
    assert summary.tailored == []
    with engine.connect() as conn:
        assert (
            conn.execute(select(tables.runs.c.status).where(tables.runs.c.id == summary.run_id))
            .scalar_one()
            == RUN_FAILED
        )
        # Nothing may be persisted under a policy nobody can read. The eligibility tables
        # carry BEFORE UPDATE/DELETE RAISE(ABORT) triggers, so a row written here could
        # only ever be superseded, never corrected.
        assert (
            conn.execute(
                select(func.count())
                .select_from(tables.eligibility_evaluations)
                .where(tables.eligibility_evaluations.c.run_id == summary.run_id)
            ).scalar_one()
            == 0
        )
        assert (
            conn.execute(
                select(func.count())
                .select_from(tables.job_dispositions)
                .where(tables.job_dispositions.c.run_id == summary.run_id)
            ).scalar_one()
            == 0
        )


def test_cli_reports_the_run_id_and_exits_zero_on_a_clean_run(env: Path, tmp_path: Path) -> None:
    _ready(env)

    result = _cli(env, ["run", "--no-scan", "--out", str(tmp_path / "apps")])

    assert result.exit_code == 0, result.output
    assert "run 1 ·" in result.output
    assert "evaluated" in result.output
    assert "boardwatch track add" in result.output


def test_cli_exits_two_when_the_scan_lock_is_held(env: Path, tmp_path: Path) -> None:
    """Exit 2 is the repo's reserved contention code (scan_cmd.py), distinct from failure."""
    _ready(env)
    settings = load_settings(data_dir=env)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    holder = FileLock(str(settings.data_dir / "scan.lock"))
    holder.acquire()
    try:
        result = _cli(env, ["run", "--out", str(tmp_path / "apps")])
    finally:
        holder.release()

    assert result.exit_code == 2, result.output


def test_scan_given_a_run_id_records_its_counts_without_claiming_the_run_finished(
    env: Path,
) -> None:
    """Stage one of three must not stamp finished_at, or the pipeline reads as done at scan."""
    from boardwatch.scan.coordinator import run_scan

    _seed_posting(env)  # one watched company, so boards_attempted must become non-zero
    settings = load_settings(data_dir=env)
    engine = get_engine(env)

    summary = run_scan(engine, settings, finish=False)

    with engine.connect() as conn:
        row = conn.execute(
            select(
                tables.runs.c.finished_at,
                tables.runs.c.boards_attempted,
                tables.runs.c.postings_seen,
            ).where(tables.runs.c.id == summary.run_id)
        ).one()
        assert conn.execute(select(func.count()).select_from(tables.runs)).scalar_one() == 1
    # postings_seen is NULL at birth and only finalize_run ever sets it, so asserting it is
    # non-NULL is what actually pins "the counts were written". boards_attempted is 0 from
    # birth, so on its own it pinned nothing — deleting finalize_run left the old test green.
    assert row.postings_seen is not None, "the scan stage did not write its counts"
    assert row.boards_attempted == 1
    assert row.finished_at is None, "the scan stage finished a run it does not own"


def test_bare_scan_mints_and_finishes_its_own_run(env: Path) -> None:
    """A bare `scan` is a degenerate pipeline run: one row shape, no `kind` column."""
    from boardwatch.scan.coordinator import run_scan

    ensure_schema(get_engine(env))
    engine = get_engine(env)

    run_scan(engine, load_settings(data_dir=env))

    with engine.connect() as conn:
        rows = conn.execute(select(tables.runs.c.finished_at)).all()
    assert len(rows) == 1
    assert rows[0].finished_at is not None


@pytest.mark.parametrize(
    ("company", "posting_id", "expected"),
    [
        ("Acme Corp", 7, "acme-corp-7"),
        ("Foo & Bar, Inc.", 12, "foo-bar-inc-12"),
        ("", 3, "company-3"),
        ("///", 4, "company-4"),
    ],
)
def test_slug_is_filesystem_safe_and_unique_per_posting(
    company: str, posting_id: int, expected: str
) -> None:
    assert _slug(company, posting_id) == expected


# --------------------------------------------------------------------------------------
# P3 slice 3 — run-integrity guards (PROGRAM.md §3.P3 items 5, 9, 6)
# --------------------------------------------------------------------------------------


def test_cohort_guard_balances_when_every_candidate_reached_a_terminal_state() -> None:
    assert _cohort_guard(frozenset({1, 2, 3}), frozenset({1, 2}), frozenset({3})) is None


def test_cohort_guard_is_fatal_and_names_the_vanished_candidate() -> None:
    message = _cohort_guard(frozenset({1, 2, 3}), frozenset({1, 2}), frozenset())

    assert message is not None
    assert "cohort incomplete" in message
    assert "3" in message


def test_cohort_guard_by_id_set_catches_a_compensating_bug_a_count_check_would_miss() -> None:
    """The design's named mutation: reconciling by COUNT instead of by ID SET.

    `visible={1,2,3}`; a mislabeled/double-counted lead lands `4` (not a shortlisted candidate
    at all) in `leads`, and candidate `3` is lost. `len(visible) == len(leads) + len(failed)`
    (3 == 3 + 0) balances — a count check would miss it. The id-set check still catches `3` as
    unaccounted, which is exactly why the guard reconciles by set (reviewer Minor, resolved).
    """
    visible = frozenset({1, 2, 3})
    leads = frozenset({1, 2, 4})
    failed: frozenset[int] = frozenset()
    assert len(visible) == len(leads) + len(failed), "the count identity should balance here"

    message = _cohort_guard(visible, leads, failed)

    assert message is not None, "the count-based identity balances, but a candidate is missing"
    assert "3" in message


def test_zero_output_guard_is_not_fatal_when_no_new_eligible_work_happened() -> None:
    assert _zero_output_guard(0) is None


def test_zero_output_guard_is_fatal_when_new_eligible_work_produced_no_lead() -> None:
    message = _zero_output_guard(5)

    assert message is not None
    assert "empty day not provably right" in message
    assert "5" in message


def _ready_no_posting(data_dir: Path) -> None:
    """A profile, but no posting at all — the genuinely empty-corpus case."""
    assert _cli(data_dir, ["init"], INIT_INPUT).exit_code == 0
    assert _cli(data_dir, ["tailor", "init"]).exit_code == 0


def test_a_genuinely_empty_corpus_is_not_a_false_alarm(env: Path, tmp_path: Path) -> None:
    """Honest empty day: no open postings at all, so no eligible work could exist. Exit 0."""
    _ready_no_posting(env)

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.shortlist is not None
    assert summary.shortlist.shortlisted == 0
    assert summary.tailored == []
    assert summary.fatal is None, summary.fatal


def test_zero_leads_with_fresh_eligible_work_this_run_is_fatal(
    env: Path, tmp_path: Path
) -> None:
    """Suspicious case: an eligible posting exists and was judged BY THIS RUN, yet the ranker
    shortlisted nothing (forced here with `--top 0`) — 0 leads is not provably right."""
    _ready(env)

    summary = _pipeline(env, tmp_path / "apps", top_n=0)

    assert summary.shortlist is not None
    assert summary.shortlist.shortlisted == 0
    assert summary.tailored == []
    assert summary.fatal is not None
    assert "empty day not provably right" in summary.fatal


def test_steady_state_where_eligible_work_is_all_prior_run_cache_hits_is_not_fatal(
    env: Path, tmp_path: Path
) -> None:
    """The review's flagged false alarm (Major 3, resolved): eligible postings exist, but every
    one was already judged by a PRIOR run under the same profile+rules identity — this run did
    no NEW eligible work. `judged_this_run` (run_id) attribution is what tells this apart from
    the suspicious case above, without a cross-run handled ledger.
    """
    _ready(env)
    out_root = tmp_path / "apps"
    first = _pipeline(env, out_root)
    assert first.fatal is None, first.fatal
    assert first.tailored, "the fixture produced no lead on run 1, so run 2 proves nothing"

    second = _pipeline(env, out_root, top_n=0)

    assert second.shortlist is not None
    assert second.shortlist.shortlisted == 0
    assert second.tailored == []
    assert second.fatal is None, second.fatal


def test_runner_fatal_on_silent_empty_day(env: Path, tmp_path: Path) -> None:
    """B5 — the regression this whole change closes. A prior-run posting that is now `built`
    makes the CORPUS-scoped `hidden_handled` non-zero, which is exactly what disarmed the OLD
    guard (D-282): its `hidden_handled == 0` clause never fired again once anything anywhere
    had ever been built. The run-scoped twin does not credit that posting — it was not judged
    THIS run — so a second, genuinely NEW eligible posting rejected by the cutoff (`--top 0`)
    still leaves an unexplained candidate, and the new guard fires where the old one could not.
    """
    _ready(env)
    out_root = tmp_path / "apps"
    first = _pipeline(env, out_root)
    assert first.fatal is None, first.fatal
    assert first.tailored, "the fixture produced no lead on run 1, so run 2 proves nothing"

    _seed_posting(env, slug="acme3")  # a second, NEW posting for run 2

    second = _pipeline(env, out_root, top_n=0)

    assert second.shortlist is not None
    assert second.shortlist.hidden_handled == 1, "the prior lead must still read as handled"
    assert second.tailored == []
    assert second.fatal is not None
    assert "empty day not provably right" in second.fatal


def test_runner_ok_on_ledger_drain_day(env: Path, tmp_path: Path) -> None:
    """A NEW eligible-this-run posting that already carries a live `built` disposition (the
    ledger drain, P6 slice 2) is an honest empty day: `handled_this_run` explains the whole
    candidate population this run judged, so the guard stays silent."""
    posting_id = _seed_posting(env)
    assert _cli(env, ["init"], INIT_INPUT).exit_code == 0
    assert _cli(env, ["tailor", "init"]).exit_code == 0

    engine = get_engine(env)
    with engine.begin() as conn:
        job_id = int(
            conn.execute(
                select(tables.postings.c.job_id).where(tables.postings.c.id == posting_id)
            ).scalar_one()
        )
        record_disposition(
            conn, job_id, disposition="built", reason="lead_built", policy_version="v1",
            now=utcnow(),
        )

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.shortlist is not None
    assert summary.shortlist.shortlisted == 0
    assert summary.tailored == []
    assert summary.fatal is None, summary.fatal


def test_a_lead_whose_folder_disappeared_after_tailoring_is_filesystem_truth_fatal(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P3 item 6 — the DB says a lead was produced, but its folder is gone from disk. Counting
    the deliverable through a different path than the one that produced it (CLAUDE.md)."""
    _ready(env)
    import shutil

    import boardwatch.pipeline.runner as runner_mod

    real_run_tailor = runner_mod.run_tailor

    def sabotage(*args: object, **kwargs: object):
        result = real_run_tailor(*args, **kwargs)
        shutil.rmtree(kwargs["out_dir"])  # type: ignore[arg-type]
        return result

    monkeypatch.setattr(runner_mod, "run_tailor", sabotage)
    summary = _pipeline(env, tmp_path / "apps")

    assert summary.tailored, "nothing was tailored, so this proves nothing"
    assert summary.fatal is not None
    assert "filesystem-truth" in summary.fatal


# --- every fatal path must leave its reason on the run row ------------------------------
#
# `status=failed` with `errors_json=[]` is a run that cannot say why it failed, and it is the
# shape an unattended failure actually took. The four late guards below the tailor loop set
# `summary.fatal` and fall through to `finish_run` without ever touching `stage_errors`, so the
# reason existed only in a console log nobody reads on a 04:00 run.
#
# Parametrized over the fatal paths rather than written four times, because the invariant is
# about the CHOKE POINT, not about any one guard: whatever put a reason in `summary.fatal` has
# to be findable on the row afterwards. A new guard added later is covered by adding one entry
# here, and — more to the point — is covered in PRODUCTION without touching this file at all.


def _fatal_scan_outage(env: Path, out_root: Path, monkeypatch: pytest.MonkeyPatch):
    """Run 132's shape through the PIPELINE caller. Already recorded before this change
    (the scan arm appends `scan: <reason>` itself), so it pins the behaviour rather than
    discriminating — the discriminating case is the standalone caller, in test_scan.py."""
    _ready(env)
    return _scan_pipeline(env, out_root, status=500)


def _fatal_every_lead_unrendered(env: Path, out_root: Path, monkeypatch: pytest.MonkeyPatch):
    """A non-empty shortlist that produced no lead at all — a broken résumé path."""
    _ready(env)
    import boardwatch.pipeline.runner as runner_mod

    def boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("resume.yaml is missing")

    monkeypatch.setattr(runner_mod, "run_tailor", boom)
    return _pipeline(env, out_root)


def _fatal_zero_output_guard(env: Path, out_root: Path, monkeypatch: pytest.MonkeyPatch):
    """B5's silent empty day: a genuinely new eligible posting that no lead explains."""
    _ready(env)
    first = _pipeline(env, out_root)
    assert first.fatal is None, first.fatal
    assert first.tailored, "run 1 produced no lead, so run 2 proves nothing"
    _seed_posting(env, slug="acme3")
    return _pipeline(env, out_root, top_n=0)


def _fatal_cohort_guard(env: Path, out_root: Path, monkeypatch: pytest.MonkeyPatch):
    """Stands in for the fatal path nobody has written yet as much as for `_cohort_guard`
    itself: the guard is replaced by one returning a reason the runner has never seen, so what
    is proved is that the choke point persists whatever a guard hands it, not that it knows
    this particular sentence."""
    _ready(env)
    import boardwatch.pipeline.runner as runner_mod

    monkeypatch.setattr(
        runner_mod, "_cohort_guard", lambda *_a: "cohort: candidate 4242 reached no terminal state"
    )
    return _pipeline(env, out_root)


def _fatal_filesystem_truth(env: Path, out_root: Path, monkeypatch: pytest.MonkeyPatch):
    """The store says a lead was produced; its folder is gone from disk."""
    _ready(env)
    import shutil

    import boardwatch.pipeline.runner as runner_mod

    real_run_tailor = runner_mod.run_tailor

    def sabotage(*args: object, **kwargs: object):
        result = real_run_tailor(*args, **kwargs)
        shutil.rmtree(kwargs["out_dir"])  # type: ignore[arg-type]
        return result

    monkeypatch.setattr(runner_mod, "run_tailor", sabotage)
    return _pipeline(env, out_root)


@pytest.mark.parametrize(
    "make_fatal",
    [
        _fatal_scan_outage,
        _fatal_every_lead_unrendered,
        _fatal_zero_output_guard,
        _fatal_cohort_guard,
        _fatal_filesystem_truth,
    ],
    ids=[
        "scan_outage",
        "every_lead_unrendered",
        "zero_output_guard",
        "cohort_guard",
        "filesystem_truth",
    ],
)
def test_every_fatal_path_persists_its_reason_on_the_run_row(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_fatal: object
) -> None:
    summary = make_fatal(env, tmp_path / "apps", monkeypatch)  # type: ignore[operator]

    assert summary.fatal is not None, "guard: this scenario did not go fatal, so it proves nothing"
    with get_engine(env).connect() as conn:
        row = conn.execute(
            select(tables.runs.c.status, tables.runs.c.errors_json).where(
                tables.runs.c.id == summary.run_id
            )
        ).one()
    persisted = list(row.errors_json or [])
    assert row.status == "failed", f"a fatal run was not recorded failed: {row.status}"
    carrying = [note for note in persisted if summary.fatal in note]
    assert carrying, (
        f"the run recorded failed but not WHY — errors_json cannot answer it: {persisted}"
    )
    # One event, one entry. A path that both records at its own site AND falls through to the
    # choke point would double every fatal, which makes any per-run error count downstream
    # uninterpretable — the same duplication the scan stage's own errors already avoid.
    assert len(carrying) == 1, f"one fatal was recorded {len(carrying)} times: {persisted}"


def test_a_fatal_reason_a_stage_already_recorded_is_not_recorded_twice(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The crash handler already appends its message and then sets `fatal` to that same
    message, so the choke point must recognise it as recorded. One event, one row entry —
    otherwise every per-run error count downstream becomes uninterpretable."""
    _ready(env)

    import boardwatch.pipeline.runner as runner_mod

    def boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("taxonomy.yaml is malformed")

    monkeypatch.setattr(runner_mod, "_count_evaluations", boom)
    with pytest.raises(RuntimeError):
        _pipeline(env, tmp_path / "apps")

    with get_engine(env).connect() as conn:
        persisted = list(conn.execute(select(tables.runs.c.errors_json)).scalar_one() or [])
    aborted = [note for note in persisted if "taxonomy.yaml is malformed" in note]
    assert len(aborted) == 1, f"the crash reason was recorded {len(aborted)} times: {persisted}"


def test_a_normal_run_that_produced_leads_stays_non_fatal(env: Path, tmp_path: Path) -> None:
    """Regression: the guards must not fire on a healthy run. Distinct from
    `test_a_clean_run_is_recorded_as_ok`, which checks `runs.status`; this checks the guards'
    own discriminator directly."""
    _ready(env)

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.tailored, "the fixture produced no lead, so this proves nothing"
    assert summary.fatal is None, summary.fatal


def test_a_successful_run_pings_the_heartbeat(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A clean run fires the dead-man's-switch exactly once. The whole design rests on a
    successful run being the ONLY thing that pings, so that a missed run produces silence."""
    _ready(env)

    import boardwatch.pipeline.runner as runner_mod

    pings: list[int] = []
    monkeypatch.setattr(runner_mod, "send_heartbeat", lambda: pings.append(1), raising=False)

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.fatal is None, "guard: this must be the success path"
    assert summary.tailored, "guard: the fixture produced no lead, so success proves nothing"
    assert pings == [1], "a clean run did not ping the heartbeat exactly once"


def test_a_fatal_run_does_not_ping_the_heartbeat(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The point of a dead-man's-switch: a failed run must NOT ping, so the monitor still
    goes silent and alerts. Every lead failing to tailor is fatal (see the sibling test)."""
    _ready(env)

    import boardwatch.pipeline.runner as runner_mod

    def boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("resume.yaml is missing")

    pings: list[int] = []
    monkeypatch.setattr(runner_mod, "run_tailor", boom)
    monkeypatch.setattr(runner_mod, "send_heartbeat", lambda: pings.append(1), raising=False)

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.fatal is not None, "guard: this must be the fatal path"
    assert pings == [], "a fatal run pinged the heartbeat — the monitor would never alert"


def test_a_funnel_write_failure_withholds_the_heartbeat(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run whose funnel never wrote is non-fatal (fail-open, D-287) but its authoritative
    record is missing (B1/B5/P3 are read out of it), so the green ping is withheld and the
    monitor alerts. A clean run that could not record itself must not read as clean to the
    dead-man's-switch."""
    _ready(env)

    import boardwatch.pipeline.runner as runner_mod

    def boom(*_a: object, **_k: object) -> object:
        raise RuntimeError("funnel boom")

    pings: list[int] = []
    monkeypatch.setattr(runner_mod, "_emit_funnel", boom)
    monkeypatch.setattr(runner_mod, "send_heartbeat", lambda: pings.append(1), raising=False)

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.fatal is None, "a funnel-write failure must not fail the run (fail-open)"
    assert summary.funnel is None, "guard: the funnel must have failed to write"
    assert pings == [], "the heartbeat pinged despite a missing funnel — the monitor would not alert"


def test_a_morning_write_failure_withholds_the_heartbeat(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The digest is where a soft alert is DELIVERED, so a run that could not write one warned
    nobody — and looked exactly like a run with nothing to warn about.

    The other three channels are all unread unattended: the console goes to a log file, nothing
    queries `runs.errors_json`, and the funnel buries an alert a thousand lines into a file that
    is searched rather than read. Withholding the ping is what makes that state reach the
    operator at all. It stays fail-open in every other respect: the run is still non-fatal and
    the leads still shipped.
    """
    _ready(env)

    import boardwatch.pipeline.runner as runner_mod

    def boom(*_a: object, **_k: object) -> object:
        raise RuntimeError("morning boom")

    pings: list[int] = []
    monkeypatch.setattr(runner_mod, "_emit_morning", boom)
    monkeypatch.setattr(runner_mod, "send_heartbeat", lambda: pings.append(1), raising=False)

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.fatal is None, "a digest-write failure must not fail the run (fail-open)"
    assert summary.funnel is not None, "guard: the FUNNEL wrote, so only the digest is missing"
    assert summary.morning is None, "guard: the digest must have failed to write"
    assert summary.tailored, "guard: the run still delivered its leads"
    assert pings == [], "the heartbeat pinged despite a missing digest — no alert would ever land"


# --- the heartbeat's OWN outcome ---------------------------------------------------------
#
# The monitor can only see pings that arrive, and cannot tell a REFUSED ping from a machine
# that was asleep. So a rotated token, a deleted healthchecks.io check, or an endpoint
# answering 500 left no local trace of any kind, and boardwatch's silence read as health while
# the whole unattended safety net was down.
#
# These three drive the REAL `send_heartbeat` over an httpx.MockTransport rather than stubbing
# its return value, so the runner's wiring and the module's own contract are proved together.
# No test here may ever reach a real monitor URL: a test ping registers as a successful run on
# the operator's live check and destroys exactly the signal this feature exists to protect.

_MONITOR_URL = "https://hc.example/ping-token"


def _wire_heartbeat(
    monkeypatch: pytest.MonkeyPatch, *, env_value: str | None, handler: object
) -> list[str]:
    """Point the runner's heartbeat at a mock transport; return the list of URLs it requested."""
    import boardwatch.pipeline.runner as runner_mod
    from boardwatch.notify import heartbeat as heartbeat_mod

    requested: list[str] = []

    def recording(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return handler(request)  # type: ignore[operator]

    def send() -> str | None:
        return heartbeat_mod.send_heartbeat(
            env={} if env_value is None else {heartbeat_mod.HEARTBEAT_URL_ENV: env_value},
            client=httpx.Client(
                transport=httpx.MockTransport(recording), follow_redirects=True
            ),
        )

    monkeypatch.setattr(runner_mod, "send_heartbeat", send)
    return requested


def test_a_refused_heartbeat_ping_is_recorded_and_does_not_fail_the_run(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ping's return value used to be discarded, so a 4xx/5xx produced no trace anywhere.
    It must now be durable on the run row — and the run must stay clean, because telemetry can
    never be the thing that fails a run (D-076)."""
    _ready(env)
    requested = _wire_heartbeat(
        monkeypatch, env_value=_MONITOR_URL, handler=lambda req: httpx.Response(404)
    )

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.tailored, "guard: the fixture produced no lead, so this proves nothing"
    assert requested == [_MONITOR_URL], "guard: exactly one ping must have been attempted"
    with get_engine(env).connect() as conn:
        row = conn.execute(
            select(tables.runs.c.status, tables.runs.c.errors_json).where(
                tables.runs.c.id == summary.run_id
            )
        ).one()
    persisted = list(row.errors_json or [])
    assert any("heartbeat" in note and "404" in note for note in persisted), (
        f"a refused heartbeat left no durable trace: {persisted}"
    )
    assert any("heartbeat" in note for note in summary.errors), summary.errors
    assert summary.fatal is None, "a telemetry failure failed the run — fail-open is broken"
    assert row.status == "ok", f"a telemetry failure changed the run's status: {row.status}"


def test_an_unset_heartbeat_url_records_nothing(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The heartbeat is off by default for every user but this one, and the OLD return value
    could not tell "unset" from "failed" — both were `False`. Alerting on falsiness would have
    put a heartbeat failure on every run of every install that never configured one."""
    _ready(env)
    requested = _wire_heartbeat(
        monkeypatch, env_value=None, handler=lambda req: httpx.Response(500)
    )

    summary = _pipeline(env, tmp_path / "apps")

    assert requested == [], "an unset URL must never touch the network"
    with get_engine(env).connect() as conn:
        persisted = list(
            conn.execute(
                select(tables.runs.c.errors_json).where(tables.runs.c.id == summary.run_id)
            ).scalar_one()
            or []
        )
    assert not any("heartbeat" in note for note in persisted), persisted
    assert not any("heartbeat" in note for note in summary.errors), summary.errors


def test_an_acknowledged_heartbeat_ping_records_nothing(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The quiet path stays quiet: a 2xx is the normal nightly outcome and must not add a
    line to every clean run's error list."""
    _ready(env)
    requested = _wire_heartbeat(
        monkeypatch, env_value=_MONITOR_URL, handler=lambda req: httpx.Response(200, text="ok")
    )

    summary = _pipeline(env, tmp_path / "apps")

    assert requested == [_MONITOR_URL], "guard: the ping was never sent, so this proves nothing"
    with get_engine(env).connect() as conn:
        persisted = list(
            conn.execute(
                select(tables.runs.c.errors_json).where(tables.runs.c.id == summary.run_id)
            ).scalar_one()
            or []
        )
    assert not any("heartbeat" in note for note in persisted), persisted
    assert not any("heartbeat" in note for note in summary.errors), summary.errors


def test_the_funnel_accounts_for_the_whole_run_STAGE_BY_STAGE(  # noqa: N802
    env: Path, tmp_path: Path
) -> None:
    """Run 128 spent 26.8 minutes between its last board apply and its first lane apply, and
    no artifact could say on which stage — the scan's per-provider fetch cost was the only
    timing the funnel carried, and every stage after it was timed nowhere. Reconstructing it
    afterwards meant joining four tables on their side-effect timestamps.

    Two properties, and neither is "the key exists". The marks must name every stage IN RUN
    ORDER, because a missing mark is not a missing row — its cost silently joins the stage
    after it. And they must not exceed the run: the clock closes each stage as it marks it, so
    a mark that failed to advance the cursor would report cumulative times that look like a
    plausible breakdown and sum to several times the run.
    """
    _ready(env)
    out_root = tmp_path / "apps"

    started = perf_counter()
    summary = _pipeline(env, out_root)
    elapsed = perf_counter() - started

    assert [stage.name for stage in summary.stage_durations] == [
        "scan",
        "projection",
        "lanes",
        "death_probe",
        "eligibility",
        "liveness",
        "gate",
        "tailor",
        "finalize",
    ]
    assert all(stage.seconds >= 0 for stage in summary.stage_durations)
    total = sum(stage.seconds for stage in summary.stage_durations)
    assert 0 < total <= elapsed, f"the stages claim {total:.3f}s of a {elapsed:.3f}s run"

    payload = json.loads(
        next((out_root / utcnow().date().isoformat()).glob("funnel-*.json")).read_text()
    )
    # NAMES AND SECONDS. Comparing names alone would let the serializer emit a different
    # number from the one the run measured — a table that reconciles against itself and
    # against nothing else. The writer rounds to 3dp, so the summary is rounded the same way
    # rather than compared with a tolerance nobody could justify.
    assert payload["stage_durations"] == [
        {"name": stage.name, "seconds": round(stage.seconds, 3)}
        for stage in summary.stage_durations
    ], "the artifact and the summary disagree about what the run cost"


# Long enough to dominate the rounding the funnel writer applies (3dp) and short enough not to
# slow the suite. Only ever compared one-sided.
_ABORT_TICK = 0.05


def test_a_crashed_run_still_reports_where_its_time_went(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A crashed run is exactly the one whose cost breakdown is worth having, and it is the
    case a per-stage context manager would lose: `_count_evaluations` raising skips the
    `tailor` mark entirely, so that stage's cost must be charged to the mark that follows it
    from the `finally` rather than vanishing. The artifact must still balance."""
    _ready(env)
    out_root = tmp_path / "apps"

    import boardwatch.pipeline.runner as runner_mod

    # Deliberately SLOW before it raises. A bare raise leaves the assertion below unable to
    # tell "the aborted work was charged to `finalize`" from "`finalize` happened to be a few
    # milliseconds" — the measurable sleep is what makes the claim falsifiable. One-sided:
    # `sleep` is a lower bound, so no machine load can make this flake.
    def boom(*_a: object, **_k: object) -> None:
        sleep(_ABORT_TICK)
        raise RuntimeError("taxonomy.yaml is malformed")

    monkeypatch.setattr(runner_mod, "_count_evaluations", boom)
    with pytest.raises(RuntimeError):
        _pipeline(env, out_root)

    payload = json.loads(
        next((out_root / utcnow().date().isoformat()).glob("funnel-*.json")).read_text()
    )
    by_name = {row["name"]: row["seconds"] for row in payload["stage_durations"]}
    names = list(by_name)
    assert names[-1] == "finalize", f"the aborting run reported {names}"
    assert "tailor" not in names, "a stage that never completed was reported as if it had"
    # The work the abort discarded is CHARGED to the mark that follows it, never dropped:
    # `finalize` is the only mark between `liveness` and the crash, so it must carry at least
    # the time the aborting call itself burned.
    assert by_name["finalize"] >= _ABORT_TICK * 0.8, (
        f"the aborted stage's {_ABORT_TICK}s went unaccounted for: {by_name}"
    )


def test_a_morning_write_failure_is_recorded_durably_not_only_printed(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The morning digest (P3 item 7) is emitted AFTER finish_run, like the funnel. A swallowed
    write used to reach only the console — invisible to anything reading the store, so an
    unattended run whose digest never wrote looked byte-identical to a clean one (D-287). It must
    now reach `summary.errors` and the `runs` row, without failing the run: a digest write is not
    the run's outcome (fail-open)."""
    import boardwatch.pipeline.runner as runner_mod

    _ready(env)

    def boom(*_a: object, **_k: object) -> object:
        raise RuntimeError("morning boom")

    monkeypatch.setattr(runner_mod, "_emit_morning", boom)
    summary = _pipeline(env, tmp_path / "apps")

    assert summary.fatal is None, "a digest-write failure must not fail the run"
    assert any("morning artifact not written" in e for e in summary.errors), summary.errors
    # Durable, read back through a DIFFERENT path than summary.errors — the runs row itself.
    with get_engine(env).connect() as conn:
        stored = conn.execute(
            select(tables.runs.c.errors_json).where(tables.runs.c.id == summary.run_id)
        ).scalar_one()
    assert any("morning artifact not written" in e for e in (stored or [])), stored


def test_the_run_surfaces_net_new_intake_as_a_real_number(env: Path, tmp_path: Path) -> None:
    """'0 new across the whole corpus' is intake death that is NOT a scan outage
    (is_systemic_scan_outage stays False on a complete-but-empty listing) and yields zero leads
    with no fatal. `summary.scan_new` must carry the real count discovered, not sit at its
    default: a scan that found a posting reads > 0."""
    _ready(env)
    _add_live_board(env)
    body = b'{"meta": {"total": 1}, "jobs": [{"id": 1, "title": "Engineer A"}]}'
    settings = load_settings(data_dir=env)
    with respx.mock:
        for slug in SEEDED_BOARDS:
            respx.get(_GH.board_url(slug)).mock(
                return_value=httpx.Response(200, content=HEALTHY_BODY)
            )
        respx.get(_GH.board_url("live")).mock(return_value=httpx.Response(200, content=body))
        summary = run_pipeline(
            get_engine(env),
            settings,
            console=Console(quiet=True),
            out_root=tmp_path / "apps",
            resume_path=settings.config_dir / "resume.yaml",
        )
    assert summary.scan_new >= 1, (
        f"a scan that discovered a posting reported scan_new={summary.scan_new}"
    )


def test_the_run_summary_line_carries_the_net_new_signal(env: Path, tmp_path: Path) -> None:
    """The net-new count rides the one line an unattended run is read from (stdout → the log),
    so a corpus that stops producing new postings is a visible number rather than buried in
    `evaluated: 0`."""
    _ready(env)
    result = _cli(env, ["run", "--no-scan", "--out", str(tmp_path / "apps")])
    assert result.exit_code == 0, result.output
    assert " new · " in result.output and " closed · " in result.output, result.output


# --- soft-alert ESCALATION: the absent-owner channel ---------------------------------------
#
# The heartbeat gate is satisfied by a merely non-fatal run, so a run that raised every soft
# alert in the finalize block still pings GREEN. While somebody is at the machine the morning
# digest carries those alerts; unattended it cannot, because it is a local file in no synced
# folder. Escalation is what makes a DEGRADED-but-successful run visible remotely, and its
# correctness is entirely a question of WHERE it is called from.


def test_the_escalation_report_carries_every_alert_including_the_heartbeat_s_own(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pins the call site, which is the whole of this feature's correctness.

    Escalation is the one thing in the finalize block that belongs BELOW `_emit_morning` — it
    raises no alert, it reports the alerts every handler above already raised, so it must run
    after the last of them. Two moves break it and neither changes any other test:

    - lifted into the soft-alert block (where the ordering invariant would "correctly" put a
      NEW alert), and the report goes out missing the heartbeat's own result;
    - lifted above the heartbeat gate, same thing.

    A refused ping is the single alert most worth escalating — it means the dead-man's switch
    itself is not reporting, so the monitor's silence can no longer be read as health. So this
    asserts the payload contains BOTH a soft alert raised early in the block and the heartbeat
    result raised at the very end of it.
    """
    _ready(env)

    import boardwatch.pipeline.runner as runner_mod

    monkeypatch.setattr(runner_mod, "check_intake_death", lambda *_a, **_k: "MARKER-intake")
    monkeypatch.setattr(runner_mod, "send_heartbeat", lambda: "MARKER-heartbeat")

    captured: list[tuple[str, ...]] = []

    def spy(run_id: int, alerts: tuple[str, ...], **_k: object) -> None:
        captured.append(tuple(alerts))
        return None

    monkeypatch.setattr(runner_mod, "escalate_alerts", spy)

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.fatal is None, "guard: escalation must never fail the run (fail-open)"
    assert captured, "escalation was never called — a degraded run reports nothing remotely"
    payload = captured[-1]
    assert "MARKER-intake" in payload, (
        "escalation ran ABOVE the soft-alert block: the report omits alerts raised after it"
    )
    assert "MARKER-heartbeat" in payload, (
        "escalation ran ABOVE the heartbeat: a refused ping — the one alert that invalidates "
        "the monitor's silence — never reaches the owner"
    )


def test_a_stage_error_is_NOT_escalated(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`summary.errors` is not "the run's alerts", and escalating all of it would destroy the
    channel.

    It accumulates every stage error the pipeline produced — one dead board slug, a lane that
    could not collect, a per-lead tailor degradation. Measured over runs 109-133, NINE runs
    carried a non-empty `summary.errors` and NOT ONE of the nine was a finalize-block alert:
    runs 124-128 each carried `plaid: HTTP 404` for a single dead slug out of 379 boards. Armed
    against a healthchecks.io `/fail` URL, that is five consecutive ordinary `status=ok` runs
    driving the monitor DOWN — and an owner who learns a DOWN check means nothing has lost the
    only property this channel has.

    So the payload is the finalize-block SLICE. This pins that: a stage error present before
    finalize must stay out, while an alert raised inside it goes in.
    """
    _ready(env)

    import boardwatch.pipeline.runner as runner_mod

    # A PRE-finalize stage error, injected the way the lane stage produces one
    # (`runner.py` extends `summary.errors` with whatever `_run_lanes` returns).
    monkeypatch.setattr(
        runner_mod, "_run_lanes", lambda *_a, **_k: ([], ["lane fake: collection failed"])
    )
    # ...and an alert raised INSIDE the finalize block.
    monkeypatch.setattr(runner_mod, "check_intake_death", lambda *_a, **_k: "MARKER-alert")
    monkeypatch.setattr(runner_mod, "send_heartbeat", lambda: None)

    captured: list[tuple[str, ...]] = []

    def spy(run_id: int, alerts: tuple[str, ...], **_k: object) -> None:
        captured.append(tuple(alerts))
        return None

    monkeypatch.setattr(runner_mod, "escalate_alerts", spy)

    summary = _pipeline(env, tmp_path / "apps")

    assert captured, "escalation was never called"
    payload = captured[-1]
    assert "MARKER-alert" in payload, "the finalize-block alert must be escalated"
    assert "lane fake: collection failed" not in payload, (
        "a pre-finalize STAGE error reached the escalation payload — armed, an ordinary run "
        "with one dead board slug would drive the monitor DOWN"
    )
    # Guard: the stage error is still recorded, just not escalated. The two lists differ on
    # purpose, so a mutant that simply drops the error everywhere does not pass this.
    assert any("lane fake" in e for e in summary.errors), (
        "guard: the stage error must still reach summary.errors and the digest"
    )


def test_the_runner_lets_escalation_read_the_REAL_environment(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stray `env=`/`client=` at the call site ships the feature permanently disarmed, and
    both are invisible: a working escalation and a dead one are equally silent, and the unit
    tests inject `env` themselves so they stay green either way."""
    _ready(env)

    import boardwatch.pipeline.runner as runner_mod

    monkeypatch.setattr(runner_mod, "send_heartbeat", lambda: None)
    seen_kwargs: list[dict[str, object]] = []

    def spy(run_id: int, alerts: tuple[str, ...], **kw: object) -> None:
        seen_kwargs.append(kw)
        return None

    monkeypatch.setattr(runner_mod, "escalate_alerts", spy)

    _pipeline(env, tmp_path / "apps")

    assert seen_kwargs, "escalation was never called"
    assert "env" not in seen_kwargs[-1], "the call site pins `env`, so the real one is never read"
    assert "client" not in seen_kwargs[-1], "the call site pins `client`"


def test_a_refused_escalation_is_recorded_DURABLY(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rotated token gives a 401 on every run. Printing that to a launchd log nobody opens,
    with no row in `runs.errors_json`, is the same invisibility the feature exists to end — and
    it is the failure most likely to actually happen."""
    _ready(env)

    import boardwatch.pipeline.runner as runner_mod

    monkeypatch.setattr(runner_mod, "send_heartbeat", lambda: None)
    monkeypatch.setattr(
        runner_mod, "escalate_alerts", lambda *_a, **_k: "alert escalation: refused (HTTP 401)"
    )

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.fatal is None, "a refused escalation must never fail the run"
    assert any("HTTP 401" in e for e in summary.errors), "not recorded on summary.errors"
    with get_engine(env).connect() as conn:
        stored = conn.execute(
            select(tables.runs.c.errors_json).where(tables.runs.c.id == summary.run_id)
        ).scalar_one()
    # `errors_json` is a JSON column, so this comes back as a LIST, not a string — a bare
    # `"HTTP 401" in stored` is a membership test against whole entries and never matches.
    assert stored is not None and any("HTTP 401" in e for e in stored), (
        "not durable in runs.errors_json"
    )


def test_an_escalation_that_RAISES_never_fails_the_run(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`httpx.InvalidURL` does not inherit from `HTTPError`, so a typo'd port in the env var can
    escape the module. Telemetry may never fail a run (D-076) — this pins the runner's guard,
    which no other test exercises: delete the `try/except` and every other test still passes."""
    _ready(env)

    import boardwatch.pipeline.runner as runner_mod

    monkeypatch.setattr(runner_mod, "send_heartbeat", lambda: None)

    def boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("escalation boom")

    monkeypatch.setattr(runner_mod, "escalate_alerts", boom)

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.fatal is None, "an escalation crash fell through and failed the run"
    assert summary.tailored, "guard: the run still delivered its leads"
    assert any("escalation boom" in e for e in summary.errors), "the crash left no record"


def test_a_clean_run_escalates_nothing(env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-vacuity companion to the test above: the assertions there must be reachable only on
    a run that actually raised alerts, or they would pass on any run at all."""
    _ready(env)

    import boardwatch.pipeline.runner as runner_mod

    monkeypatch.setattr(runner_mod, "send_heartbeat", lambda: None)

    captured: list[tuple[str, ...]] = []

    def spy(run_id: int, alerts: tuple[str, ...], **_k: object) -> None:
        captured.append(tuple(alerts))
        return None

    monkeypatch.setattr(runner_mod, "escalate_alerts", spy)

    _pipeline(env, tmp_path / "apps")

    assert captured, "guard: escalation is still CALLED on a clean run"
    assert captured[-1] == (), "a clean run handed the channel alerts it did not raise"


# --- a crashed DETECTOR must leave a durable record --------------------------------------
#
# The three artifact-write handlers in the finalize block (funnel, queue sync, morning) all
# record their failure through `append_run_error` as well as printing it. The four DETECTOR
# handlers did not: they appended to `summary.errors` and stopped there. `finish_run` has
# already committed by the time any of them runs, so `summary.errors` alone never reaches the
# run row (D-287) — meaning a detector that had silently stopped working left the digest and
# the escalation channel able to say so, and `runs.errors_json` unable to. Over an unattended
# fortnight that is the difference between "which day did the detector break?" being
# answerable on return and not.


@pytest.mark.parametrize(
    ("attr", "phrase"),
    [
        ("check_intake_death", "intake-death check not run"),
        ("check_delivery_drought", "delivery-drought check not run"),
        ("check_liveness_blind", "liveness-blindness check not run"),
        ("check_corpus_regression", "corpus-regression check not run"),
        ("check_apply_lane_drought", "apply-lane-drought check not run"),
    ],
)
def test_a_crashed_detector_is_recorded_DURABLY(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, attr: str, phrase: str
) -> None:
    """Each detector, one at a time: when the CHECK ITSELF raises, the note must reach
    `runs.errors_json`, not only `summary.errors`.

    Parametrised rather than folded into one run because a single test that crashes all four
    would pass while three of the four `append_run_error` calls were missing — the first note
    in the row would satisfy a naive assertion.
    """
    _ready(env)

    import boardwatch.pipeline.runner as runner_mod

    def boom(*_a: object, **_k: object) -> None:
        raise RuntimeError(f"{attr} boom")

    monkeypatch.setattr(runner_mod, attr, boom)
    monkeypatch.setattr(runner_mod, "send_heartbeat", lambda: None)

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.fatal is None, "a crashed detector must never fail the run (fail-open)"
    assert any(phrase in e for e in summary.errors), "not even on summary.errors"

    with get_engine(env).connect() as conn:
        stored = conn.execute(
            select(tables.runs.c.errors_json).where(tables.runs.c.id == summary.run_id)
        ).scalar_one()
    # `errors_json` is a JSON column, so this is a LIST — a bare `phrase in stored` is a
    # membership test against whole entries and never matches.
    assert stored is not None and any(phrase in e for e in stored), (
        f"{phrase!r} reached summary.errors but NOT runs.errors_json — on return there is no "
        f"way to answer which day the detector stopped working"
    )


# --- a NEW soft alert must sit ABOVE `_emit_morning` --------------------------------------
#
# The invariant is easy to satisfy and easy to lose: below `_emit_morning` an alert still
# fires, is still appended to `summary.errors`, and is still made durable by
# `append_run_error` — so every other assertion about it passes — and it is INVISIBLE in the
# digest, which is the one artifact an unattended owner reads. A mechanical rebase union lands
# a new block below the digest without a conflict.


def test_the_apply_lane_alert_reaches_the_MORNING_DIGEST(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pins the CALL SITE's position, not merely that the alert is raised.

    Fails against the same detector wired in below `_emit_morning`: `summary.errors` would
    still carry the marker (so an assertion on that list cannot tell the two apart) while the
    rendered digest would not. Asserting on the digest FILE is what discriminates.
    """
    _ready(env)

    import boardwatch.pipeline.runner as runner_mod

    monkeypatch.setattr(
        runner_mod, "check_apply_lane_drought", lambda *_a, **_k: "MARKER-apply-lane"
    )
    monkeypatch.setattr(runner_mod, "send_heartbeat", lambda: None)

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.morning is not None, "guard: the digest must have been written"
    assert any("MARKER-apply-lane" in e for e in summary.errors), (
        "guard: the alert must reach summary.errors at all"
    )
    rendered = summary.morning.markdown_path.read_text(encoding="utf-8")
    assert "MARKER-apply-lane" in rendered, (
        "the apply-lane alert is missing from the morning digest — the call sits BELOW "
        "`_emit_morning`, where it fires, is recorded, and is invisible to an absent owner"
    )
