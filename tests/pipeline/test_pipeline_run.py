"""`boardwatch run` — the pipeline run row (D-016, P0 item 0).

What is under test is ownership, not the stages themselves: one row spans scan, eligibility
and tailor, `finished_at` means "the pipeline is done" rather than "scan is done", and a run
that aborts is still closed out rather than left dangling for `doctor` to call still-running.
"""

import json
from pathlib import Path

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
from boardwatch.pipeline.runner import _slug, run_pipeline
from boardwatch.providers.registry import build_providers
from boardwatch.scan.coordinator import ScanLockHeldError
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine

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
    _pipeline(env, tmp_path / "apps")

    with get_engine(env).connect() as conn:
        row = conn.execute(
            select(tables.runs.c.status).order_by(tables.runs.c.id.desc()).limit(1)
        ).one()
    assert row.status == "ok", f"a clean run was closed as {row.status!r}"


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
        rows = conn.execute(select(tables.runs.c.finished_at)).scalars().all()
    assert rows, "no run row was created, so this test proves nothing"
    assert all(r is not None for r in rows), "an abort during scan left a run row dangling"


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
