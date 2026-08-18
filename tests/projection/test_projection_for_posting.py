"""`project_for_posting` — the per-posting projection both `resume project` and the pipeline call.

The environment is the same combination `test_projection_run_context.py` assembles: the bundle half
from `projection_env` (tests/projection/conftest.py) and the posting half seeded straight through
the store with `test_projection_posting.py`'s own `_engine`/`_seed`. The two have to be joined by
hand, because `resolve_projection_run` reads the stamp, the declaration and the shell out of
`settings.config_dir` and that must be the directory the bundle fixture approved a stamp in.

The compile runner is a fake returning a one-page `OK` outcome. That is not a shortcut around a
real toolchain: `select`'s compiles exist only to measure page count, `posting_context` floors an
absent profile row's budget to 1 page, and a real `tectonic` would make every assertion below
depend on a binary the gate does not require.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import Engine

from boardwatch.core.settings import Settings
from boardwatch.projection import pool as pool_mod
from boardwatch.projection import run as run_mod
from boardwatch.projection.errors import ProjectionError, ProjectionIssue
from boardwatch.projection.run import (
    MANIFEST_FILENAME,
    RESUME_FILENAME,
    ProjectionLeadOutcome,
    ProjectionRunContext,
    project_for_posting,
    resolve_projection_run,
)
from boardwatch.projection.scoring import DEFAULT_SCORER_ID
from boardwatch.store.queries import current_posting_versions
from boardwatch.tailor.load import load_resume
from boardwatch.tailor.render.outcome import CompileOutcome, CompileReason
from tests.projection.conftest import ProjectionEnv
from tests.projection.test_projection_posting import _engine, _seed

AS_OF = date(2026, 8, 17)


def _fake_runner(tex: Path, pdf: Path) -> CompileOutcome:
    """One page, always `OK`. The PDF need not exist: nothing downstream of `evaluate_compile`
    opens it on this path — `select` reads only `GateResult.reason`/`page_count`."""
    return CompileOutcome(CompileReason.OK, pdf, 1, "")


def _settings_over(env: ProjectionEnv, tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path / "run-data", config_dir=env.config_dir)


def _resolve(env: ProjectionEnv, engine: Engine, settings: Settings) -> ProjectionRunContext:
    return resolve_projection_run(
        engine,
        settings,
        bundle_root=env.bundle_root,
        declaration_path=env.declaration,
        scorer_id=DEFAULT_SCORER_ID,
        as_of=AS_OF,
    )


def _project(
    env: ProjectionEnv, tmp_path: Path, *, status: str = "open"
) -> tuple[ProjectionRunContext, Engine, Settings, int]:
    """A resolved run context plus one seeded posting, ready for `project_for_posting`."""
    settings = _settings_over(env, tmp_path)
    engine = _engine(settings)
    posting_id = _seed(engine, settings, status=status)
    return _resolve(env, engine, settings), engine, settings, posting_id


# -- the manifest's transformation identity -------------------------------------------


def test_the_manifest_carries_transformation_identity(
    projection_env: ProjectionEnv, tmp_path: Path
) -> None:
    """Bundle lineage alone records WHICH BUNDLE produced a résumé but not WHICH RULES. Two runs
    that disagree because the taxonomy moved must be distinguishable."""
    ctx, engine, settings, posting_id = _project(projection_env, tmp_path)
    out = tmp_path / "lead"

    result = project_for_posting(
        ctx, engine, settings, posting_id, out_dir=out, compile_runner=_fake_runner
    )

    assert result.manifest_path is not None
    manifest = json.loads(result.manifest_path.read_bytes())
    assert manifest["taxonomy_version"] == ctx.taxonomy.version
    assert manifest["equivalence_version"] == ctx.table.version
    assert manifest["persona_registry_version"] == ctx.persona_registry_version
    assert manifest["scorer_id"] == ctx.scorer_id
    assert manifest["as_of"] == ctx.as_of.isoformat()
    assert manifest["manifest_schema"] == run_mod.MANIFEST_SCHEMA_VERSION

    # `posting_version_id` read from the store, not from the manifest under test: an independent
    # oracle, and the field whose absence let selection run against version A while `run_tailor`
    # re-read version B.
    with engine.connect() as conn:
        expected = current_posting_versions(conn, [posting_id])[posting_id].posting_version_id
    assert manifest["posting_version_id"] == expected
    # Non-vacuity: the oracle is a real row id, not a coincidental zero/None.
    assert expected


def test_the_lineage_and_the_manifest_agree_field_for_field(
    projection_env: ProjectionEnv, tmp_path: Path
) -> None:
    """Two records of the same run, written in one call. A divergence between them is exactly the
    defect a lineage check downstream cannot detect — it would validate against one and the ledger
    would carry the other."""
    ctx, engine, settings, posting_id = _project(projection_env, tmp_path)

    result = project_for_posting(
        ctx, engine, settings, posting_id, out_dir=tmp_path / "lead", compile_runner=_fake_runner
    )

    assert result.lineage is not None and result.manifest_path is not None
    lineage = result.lineage
    manifest = json.loads(result.manifest_path.read_bytes())
    shared = (
        "bundle_revision",
        "bundle_digest",
        "projection_digest",
        "posting_version_id",
        "as_of",
        "scorer_id",
        "taxonomy_version",
        "equivalence_version",
        "persona_registry_version",
        "resume_sha256",
        "resume_model_sha256",
        "manifest_schema",
    )
    assert {name: manifest[name] for name in shared} == {
        name: getattr(lineage, name) for name in shared
    }
    assert lineage.kind == "projection"


# -- the two hashes -------------------------------------------------------------------


def test_the_resume_hash_is_over_the_bytes_that_were_written(
    projection_env: ProjectionEnv, tmp_path: Path
) -> None:
    ctx, engine, settings, posting_id = _project(projection_env, tmp_path)

    result = project_for_posting(
        ctx, engine, settings, posting_id, out_dir=tmp_path / "lead", compile_runner=_fake_runner
    )

    assert result.lineage is not None and result.resume_path is not None
    written = result.resume_path.read_bytes()
    assert result.lineage.resume_sha256 == hashlib.sha256(written).hexdigest()
    # Non-vacuity: the file has content, so a hash of b"" could not pass by coincidence.
    assert written


def test_the_model_hash_is_what_a_reader_of_the_written_file_computes(
    projection_env: ProjectionEnv, tmp_path: Path
) -> None:
    """`resume_model_sha256` is taken from the in-memory model, never by re-reading the path — but
    it is only useful if a later reader who loads the file back computes the same value. This walks
    that reader's route (`load_resume` → `model_dump_json`), which is the identity
    `reports/tailor.py` already uses for a master."""
    ctx, engine, settings, posting_id = _project(projection_env, tmp_path)

    result = project_for_posting(
        ctx, engine, settings, posting_id, out_dir=tmp_path / "lead", compile_runner=_fake_runner
    )

    assert result.lineage is not None and result.resume_path is not None
    reloaded = load_resume(result.resume_path)
    expected = hashlib.sha256(reloaded.model_dump_json().encode("utf-8")).hexdigest()
    assert result.lineage.resume_model_sha256 == expected
    # The two hashes are genuinely different functions of the same document, not one value
    # written twice — `core/lineage.py`'s "neither subsumes the other".
    assert result.lineage.resume_model_sha256 != result.lineage.resume_sha256


# -- one pool per run -----------------------------------------------------------------


def test_project_for_posting_never_resolves_a_pool(
    projection_env: ProjectionEnv, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole point of the two-API split: this function must consume the run's pool, never
    resolve its own, or the one-revision-per-run invariant is decorative.

    BOTH bindings are patched, and each is load-bearing. `run.py` does `from
    boardwatch.projection.pool import project_pool`, so patching `boardwatch.projection.pool` alone
    leaves that already-bound name untouched and the test would pass without checking anything;
    patching only `run_mod` leaves a function-local `from ... import project_pool` inside
    `project_for_posting` invisible, since that resolves through the source module at call time.
    """
    ctx, engine, settings, posting_id = _project(projection_env, tmp_path)

    def explode(*_a: object, **_kw: object) -> object:
        raise AssertionError("project_for_posting must not call project_pool")

    monkeypatch.setattr(run_mod, "project_pool", explode)
    monkeypatch.setattr(pool_mod, "project_pool", explode)

    # Non-vacuity, through the one caller that IS supposed to resolve a pool: with these patches
    # installed the run-level resolve really does trip the explosion, so a `project_for_posting`
    # that reached `project_pool` by either route would trip it too.
    with pytest.raises(AssertionError, match="must not call project_pool"):
        _resolve(projection_env, engine, settings)

    result = project_for_posting(
        ctx, engine, settings, posting_id, out_dir=tmp_path / "lead", compile_runner=_fake_runner
    )
    assert result.outcome is ProjectionLeadOutcome.PROJECTED


# -- no husks -------------------------------------------------------------------------


def test_a_refusing_lead_leaves_no_directory(
    projection_env: ProjectionEnv, tmp_path: Path
) -> None:
    """Sidecars are written before `run_tailor`, and the runner's cleanup only removes an EMPTY
    directory (`_remove_if_empty` calls `rmdir()`), while
    `tests/pipeline/test_pipeline_run.py::test_a_lead_that_fails_to_tailor_leaves_no_empty_folder_behind`
    pins that a failed lead leaves nothing behind."""
    ctx, engine, settings, posting_id = _project(projection_env, tmp_path, status="closed")
    out = tmp_path / "lead"

    with pytest.raises(ProjectionError) as exc:
        project_for_posting(
            ctx, engine, settings, posting_id, out_dir=out, compile_runner=_fake_runner
        )

    assert exc.value.violation.issue is ProjectionIssue.POSTING_NOT_OPEN
    assert not out.exists()


def test_a_failure_between_the_two_writes_leaves_no_directory(
    projection_env: ProjectionEnv, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The husk the refusal test above cannot reach: it refuses in `posting_context`, before any
    output work, so it would pass even against an implementation that wrote straight into
    `out_dir`.

    This one raises with the résumé already on disk. `manifest_bytes` is made to return a `str`,
    so the SECOND `write_bytes` raises `TypeError` after the first succeeded — exactly the shape
    the pre-extraction CLI had (mkdir, write résumé, build the manifest, write it), where the
    strict-zip crash of D-199 left `out_dir` holding one file and `rmdir()` could not remove it.
    """
    ctx, engine, settings, posting_id = _project(projection_env, tmp_path)
    parent = tmp_path / "leads"
    parent.mkdir()
    out = parent / "349"

    monkeypatch.setattr(run_mod, "manifest_bytes", lambda _manifest: "not bytes")

    with pytest.raises(TypeError):
        project_for_posting(
            ctx, engine, settings, posting_id, out_dir=out, compile_runner=_fake_runner
        )

    assert not out.exists()
    # The staging directory was cleaned up too, so the leftover is not merely renamed out of the
    # way — nothing at all survives beside where `out_dir` would have been.
    assert list(parent.iterdir()) == []


# -- the result names what it wrote ---------------------------------------------------


def test_the_result_points_at_the_two_files_it_wrote(
    projection_env: ProjectionEnv, tmp_path: Path
) -> None:
    ctx, engine, settings, posting_id = _project(projection_env, tmp_path)
    out = tmp_path / "nested" / "lead"

    result = project_for_posting(
        ctx, engine, settings, posting_id, out_dir=out, compile_runner=_fake_runner
    )

    assert result.resume_path == out / RESUME_FILENAME
    assert result.manifest_path == out / MANIFEST_FILENAME
    assert result.resume_path.is_file()
    assert result.manifest_path.is_file()
    # Nothing else was left in the output directory — no staging leftovers renamed into place.
    assert sorted(p.name for p in out.iterdir()) == sorted([RESUME_FILENAME, MANIFEST_FILENAME])
    assert result.selection is not None
    assert result.selection.pinned_entry_ids == ctx.pool.pinned_entry_ids
