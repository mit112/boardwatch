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


def test_the_summary_counts_evaluations_through_the_database_not_its_own_tally(
    env: Path, tmp_path: Path
) -> None:
    """Counted through a different path than the one that produced it (CLAUDE.md)."""
    _ready(env)

    summary = _pipeline(env, tmp_path / "apps")

    with get_engine(env).connect() as conn:
        actual = conn.execute(
            select(func.count())
            .select_from(tables.eligibility_evaluations)
            .where(tables.eligibility_evaluations.c.run_id == summary.run_id)
        ).scalar_one()
    assert summary.evaluated == actual
    assert summary.evaluated > 0


def test_leads_land_in_a_dated_folder_per_posting(env: Path, tmp_path: Path) -> None:
    _ready(env)
    out_root = tmp_path / "apps"

    summary = _pipeline(env, out_root)

    assert summary.tailored, "nothing was tailored, so this test proves nothing"
    for lead in summary.tailored:
        assert lead.out_dir.is_dir()
        assert lead.out_dir.parent.parent == out_root
        assert lead.out_dir.parent.name.count("-") == 2  # YYYY-MM-DD


def test_a_contended_scan_closes_its_run_row_rather_than_leaving_it_dangling(
    env: Path, tmp_path: Path
) -> None:
    """`doctor` reports finished_at IS NULL as a still-running run; an aborted run is not that."""
    _ready(env)
    settings = load_settings(data_dir=env)
    engine = get_engine(env)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
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

    with engine.connect() as conn:
        runs = conn.execute(
            select(tables.runs.c.finished_at, tables.runs.c.errors_json)
        ).all()
    assert len(runs) == 1
    assert runs[0].finished_at is not None, "the aborted run was left looking still-running"
    assert runs[0].errors_json == ["scan: lock held by another process"]


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
    from boardwatch.store.queries import insert_run

    ensure_schema(get_engine(env))
    settings = load_settings(data_dir=env)
    engine = get_engine(env)
    owner = insert_run(engine)  # no watched companies: the scan is a no-op but still finalizes

    run_scan(engine, settings, run_id=owner)

    with engine.connect() as conn:
        row = conn.execute(
            select(tables.runs.c.finished_at, tables.runs.c.boards_attempted).where(
                tables.runs.c.id == owner
            )
        ).one()
        assert conn.execute(select(func.count()).select_from(tables.runs)).scalar_one() == 1
    assert row.boards_attempted == 0, "the scan stage did not write its counts"
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
