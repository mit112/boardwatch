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
