"""Run attribution (D-016): every row written after this change carries a run_id.

The invariant these tests pin is narrow and load-bearing: `run_id IS NULL` must mean
*exactly* "this row predates run attribution" — the ~20,637 rows in the append-only
eligibility ledger that can never be backfilled. If a stage invoked standalone wrote NULL
instead of minting its own run, NULL would also mean "written outside a pipeline" and the
funnel's unattributed bucket would be unreadable.
"""

from pathlib import Path

import pytest
from rich.console import Console
from sqlalchemy import func, insert, select
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.core.clock import utcnow
from boardwatch.core.settings import load_settings
from boardwatch.eligibility.preflight import run_eligibility
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import ensure_run, finish_run, insert_run
from tests.conftest import write_test_resume_template

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


def _runs(data_dir: Path) -> list[tuple[int, object]]:
    with get_engine(data_dir).connect() as conn:
        return [
            (int(r.id), r.finished_at)
            for r in conn.execute(select(tables.runs.c.id, tables.runs.c.finished_at)).all()
        ]


def _eval_run_ids(data_dir: Path) -> list[int | None]:
    with get_engine(data_dir).connect() as conn:
        return [
            r.run_id
            for r in conn.execute(select(tables.eligibility_evaluations.c.run_id)).all()
        ]


# --- the invariant ------------------------------------------------------------------


def test_standalone_eligibility_attributes_every_evaluation_to_a_minted_run(env: Path) -> None:
    """`eligibility run` has no pipeline above it, so it must mint its own run, not write NULL."""
    _seed_posting(env)
    assert _cli(env, ["init"], INIT_INPUT).exit_code == 0

    assert _cli(env, ["eligibility", "run"]).exit_code == 0

    run_ids = _eval_run_ids(env)
    assert run_ids, "the preflight evaluated nothing, so this test proves nothing"
    assert None not in run_ids, "an evaluation was written with a NULL run_id"
    assert len(set(run_ids)) == 1
    minted = _runs(env)
    assert len(minted) == 1
    assert minted[0][0] == run_ids[0]
    assert minted[0][1] is not None, "a run that owns itself must be finished"


def test_eligibility_with_nothing_pending_mints_no_run(env: Path) -> None:
    """A no-op preflight must not litter `runs`, or every `top` invocation logs a run."""
    _seed_posting(env)
    assert _cli(env, ["init"], INIT_INPUT).exit_code == 0
    assert _cli(env, ["eligibility", "run"]).exit_code == 0
    before = len(_runs(env))

    # Second pass: the identity is unchanged, so _pending is empty and nothing is judged.
    assert _cli(env, ["eligibility", "run"]).exit_code == 0

    assert len(_runs(env)) == before


def test_a_supplied_run_id_is_used_rather_than_minting_another(env: Path) -> None:
    _seed_posting(env)
    assert _cli(env, ["init"], INIT_INPUT).exit_code == 0
    engine = get_engine(env)
    settings = load_settings(data_dir=env)
    owner = insert_run(engine)

    stats = run_eligibility(engine, settings, Console(quiet=True), run_id=owner)

    assert stats.evaluated > 0
    assert stats.run_id == owner
    assert set(_eval_run_ids(env)) == {owner}
    assert len(_runs(env)) == 1, "run_eligibility minted a second run despite being given one"
    # The caller owns the row, so this stage must NOT have stamped finished_at.
    assert _runs(env)[0][1] is None


def test_a_cache_hit_keeps_the_first_runs_attribution(env: Path) -> None:
    """Re-judging writes no row, so the evaluation stays filed under the run that made it.

    Cache-hit-vs-judged-this-run is a funnel stage counted from the insert rowcount, never
    inferred from run_id. Reattributing here would erase that distinction.
    """
    _seed_posting(env)
    assert _cli(env, ["init"], INIT_INPUT).exit_code == 0
    engine = get_engine(env)
    settings = load_settings(data_dir=env)
    first = insert_run(engine)
    run_eligibility(engine, settings, Console(quiet=True), run_id=first)
    second = insert_run(engine)

    stats = run_eligibility(engine, settings, Console(quiet=True), run_id=second)

    assert stats.evaluated == 0, "nothing should have been pending"
    assert set(_eval_run_ids(env)) == {first}


def test_standalone_tailor_mints_its_own_run_for_its_artifacts(env: Path) -> None:
    posting_id = _seed_posting(env)
    assert _cli(env, ["init"], INIT_INPUT).exit_code == 0
    assert _cli(env, ["tailor", "init"]).exit_code == 0
    # T2: `tailor init` does not scaffold `resume_template.tex`, and `resolve_template` no longer
    # falls back to the bundled default for a real config dir missing it — so a standalone
    # `tailor run` that reaches rendering needs one on disk, as a properly set-up user's config
    # dir would.
    write_test_resume_template(load_settings(data_dir=env).config_dir)
    out = env.parent / "out"
    out.mkdir()

    result = _cli(env, ["tailor", "run", str(posting_id), "--out", str(out)])
    assert result.exit_code == 0, result.output

    with get_engine(env).connect() as conn:
        rows = conn.execute(
            select(tables.artifacts.c.kind, tables.artifacts.c.run_id)
        ).all()
    assert rows, "no artifact was written, so this test proves nothing"
    assert all(r.run_id is not None for r in rows), (
        f"artifact written with NULL run_id: {[(r.kind, r.run_id) for r in rows]}"
    )


# --- runs-row ownership -------------------------------------------------------------


def test_finish_run_appends_errors_instead_of_replacing_them(tmp_path: Path) -> None:
    """The scan stage writes errors_json before the pipeline finishes; overwriting loses them."""
    engine = get_engine(tmp_path / "data")
    ensure_schema(engine)
    run_id = insert_run(engine)
    with engine.begin() as conn:
        conn.execute(
            tables.runs.update()
            .where(tables.runs.c.id == run_id)
            .values(errors_json=["scan: board x failed"])
        )

    finish_run(engine, run_id, errors=["tailor: posting 3 failed"])

    with engine.connect() as conn:
        errors = conn.execute(
            select(tables.runs.c.errors_json).where(tables.runs.c.id == run_id)
        ).scalar_one()
    assert errors == ["scan: board x failed", "tailor: posting 3 failed"]


def test_ensure_run_returns_the_given_id_and_mints_only_when_none(tmp_path: Path) -> None:
    engine = get_engine(tmp_path / "data")
    ensure_schema(engine)

    minted = ensure_run(engine, None)
    assert ensure_run(engine, minted) == minted

    with engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(tables.runs)).scalar_one() == 1
