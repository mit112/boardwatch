"""`boardwatch run` — the pipeline run row (D-016, P0 item 0).

What is under test is ownership, not the stages themselves: one row spans scan, eligibility
and tailor, `finished_at` means "the pipeline is done" rather than "scan is done", and a run
that aborts is still closed out rather than left dangling for `doctor` to call still-running.
"""

from pathlib import Path

import pytest
from filelock import FileLock
from rich.console import Console
from sqlalchemy import func, insert, select
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.core.clock import utcnow
from boardwatch.core.settings import load_settings
from boardwatch.pipeline.runner import _slug, run_pipeline
from boardwatch.scan.coordinator import ScanLockHeldError
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine

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
    day_dirs = list(out_root.glob("*/*")) if out_root.exists() else []
    assert day_dirs == [], f"empty husks left behind: {day_dirs}"


def test_scan_board_failures_are_reported_but_do_not_fail_the_run(
    env: Path, tmp_path: Path
) -> None:
    """A few dead boards are the norm across 85 watched; `scan` itself exits 0 for them."""
    _ready(env)
    engine = get_engine(env)
    with engine.begin() as conn:
        conn.execute(
            insert(tables.companies).values(
                name="Ghost", provider="not-a-provider", slug="ghost",
                source="user", watched=True,
            )
        )

    summary = run_pipeline(
        engine,
        load_settings(data_dir=env),
        console=Console(quiet=True),
        out_root=tmp_path / "apps",
        resume_path=load_settings(data_dir=env).config_dir / "resume.yaml",
    )

    assert any("ghost" in e for e in summary.errors), summary.errors
    assert summary.fatal is None, "an unreachable board was treated as a run failure"


def test_scan_errors_are_recorded_once_not_twice(env: Path, tmp_path: Path) -> None:
    """The scan stage persists its own errors; finish_run appends, so passing them again dupes."""
    _ready(env)
    engine = get_engine(env)
    with engine.begin() as conn:
        conn.execute(
            insert(tables.companies).values(
                name="Ghost", provider="not-a-provider", slug="ghost",
                source="user", watched=True,
            )
        )

    summary = run_pipeline(
        engine,
        load_settings(data_dir=env),
        console=Console(quiet=True),
        out_root=tmp_path / "apps",
        resume_path=load_settings(data_dir=env).config_dir / "resume.yaml",
    )

    with engine.connect() as conn:
        persisted = conn.execute(
            select(tables.runs.c.errors_json).where(tables.runs.c.id == summary.run_id)
        ).scalar_one()
    ghost = [e for e in (persisted or []) if "ghost" in e]
    assert len(ghost) == 1, f"scan errors recorded {len(ghost)} times: {persisted}"


def test_no_profile_is_a_real_run_that_produced_nothing_not_a_crash(
    env: Path, tmp_path: Path
) -> None:
    _seed_posting(env)  # deliberately no `init`, so there is no profile

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.tailored == []
    assert summary.shortlisted == 0
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
