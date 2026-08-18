"""`boardwatch run --project` renders each lead FROM the projection, per lead (P5a task 8).

Everything else in this feature existed already and did nothing: a per-run configuration snapshot,
a per-posting projector, two closed outcome catalogs, lineage validation inside `run_tailor`, and a
preflight that refuses the whole run. This module is where a lead's résumé actually comes from the
bundle — and where the four failure shapes that only exist per-lead are pinned:

* a per-lead refusal is COUNTED, non-fatal, and never falls back to the authored `resume.yaml`;
* a RUN-scoped cause that surfaces inside the loop is promoted to `fatal` instead of being handed to
  `classify_lead_outcome`, which raises on it by design;
* a `ResumeLineageMismatch` from `run_tailor` reaches `LINEAGE_MISMATCH` rather than the generic
  `tailor_failed` bucket the broad `except Exception` would have filed it under;
* an output write failure reaches `OUTPUT_IO_FAILURE` rather than aborting the run.

The compile runner is faked, and the fake is the instrument for three of those: `select`'s compiles
exist only to measure page count, and the two compile refusals differ ONLY in which compile fails —
the pinned-only base one (run-scoped, unattributable) or a later one that added a candidate
(per-lead, attributable). `_SelectRunner` discriminates by the scratch directory
`project_for_posting` creates per lead, which is a structural property of that function rather than
a guessed call index. `run_tailor`'s own render still uses the real toolchain.

The environment is assembled from the two modules that already own its halves rather than
re-implemented: `_ready` (seeded postings on unwatched companies plus `init`/`tailor init`) and the
preflight module's `_install_projection`/`_approve`, so the bundle lands at the root the pipeline
itself resolves.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path

import pytest
from rich.console import Console
from sqlalchemy import Engine, select

from boardwatch.core.settings import load_settings
from boardwatch.pipeline import runner as runner_mod
from boardwatch.pipeline.runner import PipelineSummary, _projection_scope, run_pipeline
from boardwatch.projection.errors import ProjectionError, ProjectionIssue, ProjectionViolation
from boardwatch.projection.run import (
    ISSUE_SCOPE,
    MANIFEST_FILENAME,
    RESUME_FILENAME,
    ProjectionAvailability,
    ProjectionLeadOutcome,
    ProjectionResult,
)
from boardwatch.store import tables
from boardwatch.store.db import get_engine
from boardwatch.store.queries import RUN_FAILED, RUN_OK
from boardwatch.tailor.render.latex import TemplateArtifactError
from boardwatch.tailor.render.outcome import CompileOutcome, CompileReason
from tests.pipeline.test_ledger_advances_the_queue import _ready
from tests.pipeline.test_pipeline_projection_preflight import (
    _approve,
    _config_dir,
    _install_projection,
)


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


class _SelectRunner:
    """A compile runner for `select`'s page-budget compiles, able to fail one chosen compile.

    Every call is grouped by `tex.parent`, which is the `TemporaryDirectory`
    `project_for_posting` opens once per lead — so "which lead is this?" is read off a real
    structural property instead of a hardcoded call index that a change in `select`'s growth loop
    would silently invalidate.

    Within a lead, the FIRST compile is the pinned-only base (`select`'s own
    `pinned_gate = compile_prefix(_subset_resume(pool, pinned))`, before any candidate exists) and
    every later one has added a candidate. That distinction is the entire difference between the
    run-scoped `PINNED_SET_COMPILE_FAILED` and the per-lead `CANDIDATE_COMPILE_FAILED`, so both
    arms of the pipeline's scope routing are reachable from this one fixture.
    """

    def __init__(self, *, fail_lead: int | None = None, fail_base: bool = False) -> None:
        self.fail_lead = fail_lead
        self.fail_base = fail_base
        self.scratches: list[Path] = []
        self.calls: list[Path] = []

    def __call__(self, tex: Path, pdf: Path) -> CompileOutcome:
        scratch = tex.parent
        if scratch not in self.scratches:
            self.scratches.append(scratch)
        lead = self.scratches.index(scratch) + 1
        is_base = scratch not in self.calls
        self.calls.append(scratch)
        if lead == self.fail_lead and (is_base if self.fail_base else not is_base):
            return CompileOutcome(CompileReason.COMPILE_FAILED, None, None, "synthetic failure")
        pdf.write_bytes(b"%PDF")
        return CompileOutcome(CompileReason.OK, pdf, 1, "ok")


def _projected_env(env: Path) -> str:
    """Two leads, a promoted bundle, the packaged declaration and a matching approval. Returns the
    promoted bundle digest — the value the ARTIFACT's lineage has to agree with, taken from the
    promotion rather than from anything projection wrote."""
    config_dir = _config_dir(env)
    digest = _install_projection(config_dir)
    _approve(config_dir, digest)
    return digest


def _pipeline(
    env: Path, out_root: Path, *, project: bool = True, top_n: int = 2
) -> PipelineSummary:
    settings = load_settings(data_dir=env)
    return run_pipeline(
        get_engine(env),
        settings,
        console=Console(quiet=True),
        out_root=out_root,
        resume_path=settings.config_dir / "resume.yaml",
        skip_scan=True,
        top_n=top_n,
        project=project,
    )


def _use(monkeypatch: pytest.MonkeyPatch, runner: _SelectRunner) -> None:
    """Install `runner` as the compile runner the pipeline hands to `project_for_posting`.

    Patched on `pipeline.runner`, which is where the name is bound, and read at CALL time inside
    the loop — so this replaces exactly the projection's compiles and leaves `run_tailor`'s own
    render on the real toolchain.
    """
    monkeypatch.setattr(runner_mod, "default_compile_runner", lambda: runner)


def _tailored_meta(engine: Engine, run_id: int) -> list[dict[str, object]]:
    with engine.connect() as conn:
        rows = conn.execute(
            select(tables.artifacts.c.uri, tables.artifacts.c.meta_json, tables.artifacts.c.kind)
            .where(tables.artifacts.c.run_id == run_id, tables.artifacts.c.kind == "resume_tailored")
        ).fetchall()
    return [dict(row.meta_json) for row in rows]


def _master_uris(engine: Engine, run_id: int) -> list[str]:
    """Every `resume_master` uri this run recorded. `run_tailor` passes `str(resume_path)` there, so
    this names the file the tailoring was actually built FROM — an independent route to "it rendered
    from the projection" that does not read the lineage metadata under test."""
    with engine.connect() as conn:
        return [
            str(uri)
            for uri in conn.execute(
                select(tables.artifacts.c.uri).where(
                    tables.artifacts.c.run_id == run_id,
                    tables.artifacts.c.kind == "resume_master",
                )
            ).scalars()
        ]


def _artifact_count_for(engine: Engine, posting_id: int) -> int:
    """Every artifact row bound to any version of `posting_id`. 0 is what proves no fallback: a run
    that quietly tailored the authored `resume.yaml` instead would have left a row here."""
    with engine.connect() as conn:
        version_ids = list(
            conn.execute(
                select(tables.posting_versions.c.id).where(
                    tables.posting_versions.c.posting_id == posting_id
                )
            ).scalars()
        )
        if not version_ids:
            return 0
        return len(
            conn.execute(
                select(tables.artifacts.c.id).where(
                    tables.artifacts.c.posting_version_id.in_(version_ids)
                )
            ).fetchall()
        )


def _dispositions(engine: Engine, posting_id: int) -> set[str]:
    """The dispositions on `posting_id`'s canonical job. A `built` or `skipped` here would be
    permanent, which is what makes a projection failure recoverable or not."""
    with engine.connect() as conn:
        job_id = conn.execute(
            select(tables.postings.c.job_id).where(tables.postings.c.id == posting_id)
        ).scalar_one()
        return {
            str(row)
            for row in conn.execute(
                select(tables.job_dispositions.c.disposition).where(
                    tables.job_dispositions.c.job_id == job_id
                )
            ).scalars()
        }


def _lead_dirs(day_dir: Path) -> list[Path]:
    return sorted(p for p in day_dir.iterdir() if p.is_dir())


def _run_status(engine: Engine, run_id: int) -> str:
    with engine.connect() as conn:
        return str(
            conn.execute(
                select(tables.runs.c.status).where(tables.runs.c.id == run_id)
            ).scalar_one()
        )


# -- the headline claim ------------------------------------------------------------------


def test_a_projected_lead_renders_from_the_projection(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every lead's résumé comes from the bundle, and the artifact row proves it independently.

    Three routes, none of which is the summary reporting on itself: the two sidecars exist beside
    the lead, the `resume_master` uri names the projected file rather than `resume.yaml`, and the
    tailored row's lineage hash equals a sha256 recomputed here over the bytes on disk.
    """
    ids = _ready(env, 2)
    bundle_digest = _projected_env(env)
    _use(monkeypatch, _SelectRunner())
    out_root = tmp_path / "apps"

    summary = _pipeline(env, out_root)

    assert summary.fatal is None, summary.errors
    assert summary.projection_outcomes == Counter({ProjectionLeadOutcome.PROJECTED: 2})
    assert summary.projection_outcomes[ProjectionLeadOutcome.PROJECTED] == len(summary.tailored)
    assert {lead.posting_id for lead in summary.tailored} == set(ids)

    for lead in summary.tailored:
        assert (lead.out_dir / RESUME_FILENAME).is_file()
        assert (lead.out_dir / MANIFEST_FILENAME).is_file()

    engine = get_engine(env)
    # The master each lead was tailored FROM is the projected document, not the authored résumé.
    masters = _master_uris(engine, summary.run_id)
    assert masters and all(uri.endswith(RESUME_FILENAME) for uri in masters), masters
    assert not any(uri.endswith("resume.yaml") for uri in masters)

    metas = _tailored_meta(engine, summary.run_id)
    assert len(metas) == 2
    on_disk = {
        hashlib.sha256((lead.out_dir / RESUME_FILENAME).read_bytes()).hexdigest()
        for lead in summary.tailored
    }
    for meta in metas:
        assert meta["projection_kind"] == "projection"
        # From the promotion, not from the manifest the projection also wrote.
        assert meta["projection_bundle_digest"] == bundle_digest
        assert meta["projection_resume_sha256"] in on_disk
    # Discriminating, not merely present: the recorded hash is NOT the authored résumé's. Both
    # postings here share a body, so the two projected documents are legitimately identical (one
    # hash for two leads) — what must not happen is that hash being `resume.yaml`'s.
    authored = _config_dir(env) / "resume.yaml"
    assert authored.is_file()
    assert hashlib.sha256(authored.read_bytes()).hexdigest() not in on_disk


def test_one_pool_serves_every_lead(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One snapshot per RUN. A promotion between lead 1 and lead 2 must not be able to change lead
    2's pool, so counting resolutions is the assertion: `resolve_projection_run` is what reads the
    bundle, the taxonomy, the equivalence table and the persona registry, and a second call would
    mean two leads could be built under two configurations that no digest over either résumé could
    tell apart.
    """
    _ready(env, 2)
    _projected_env(env)
    _use(monkeypatch, _SelectRunner())

    real = runner_mod.resolve_projection_run
    calls: list[object] = []

    def counting(*args: object, **kwargs: object) -> object:
        calls.append(kwargs.get("as_of"))
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(runner_mod, "resolve_projection_run", counting)

    summary = _pipeline(env, tmp_path / "apps")

    assert len(calls) == 1
    # Non-vacuity: one resolve served TWO projected leads, so the count is not 1 because the loop
    # never ran.
    assert summary.projection_outcomes[ProjectionLeadOutcome.PROJECTED] == 2


# -- a per-lead refusal skips one lead, and nothing else ----------------------------------


def test_a_failed_projection_lead_is_counted_and_leaves_no_directory(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole point of a per-lead outcome: the OTHER lead still ships.

    The failure is real, not injected at the boundary — the second lead's candidate compile fails,
    which is what `select` raises `CANDIDATE_COMPILE_FAILED` for. Four things must hold at once, and
    each is invisible to the others' assertion: the outcome is counted, the run is NOT fatal, the
    failed lead produced no artifact of any kind (no silent fallback to the authored résumé), and it
    earned no permanent disposition, so tomorrow's run can still reach it.
    """
    ids = _ready(env, 2)
    _projected_env(env)
    _use(monkeypatch, _SelectRunner(fail_lead=2))
    out_root = tmp_path / "apps"

    summary = _pipeline(env, out_root)

    assert summary.projection_outcomes == Counter(
        {
            ProjectionLeadOutcome.PROJECTED: 1,
            ProjectionLeadOutcome.CANDIDATE_UNRENDERABLE: 1,
        }
    )
    assert summary.fatal is None, summary.errors
    engine = get_engine(env)
    assert _run_status(engine, summary.run_id) == RUN_OK
    assert len(summary.tailored) == 1
    # NOT a tailor failure: the tailor stage never ran for this lead, and folding it in there would
    # both make that count a lie and hide the drop under a reason naming the wrong stage.
    assert summary.tailor_failed == 0
    assert summary.tailor_failed_ids == []
    failed = sorted(set(ids) - {lead.posting_id for lead in summary.tailored})
    assert summary.projection_failed_ids == failed
    # One error, non-fatal, naming the typed outcome rather than describing it in prose only.
    assert [msg for msg in summary.errors if "projection: posting" in msg]
    assert ProjectionLeadOutcome.CANDIDATE_UNRENDERABLE.value in "".join(summary.errors)

    # No husk: `_publish` stages both sidecars elsewhere and renames them in only once both exist,
    # so the refused lead has no directory at all — which `rmdir` could not have undone. Counted by
    # listing the dated folder, which is the independent path (D-028) and the one a husk inflates.
    assert _lead_dirs(summary.tailored[0].out_dir.parent) == [summary.tailored[0].out_dir]

    # No fallback: the refused lead has no artifact row of any kind. A run that quietly tailored
    # `resume.yaml` for it would have produced one and looked entirely successful.
    assert _artifact_count_for(engine, failed[0]) == 0
    # And nothing permanent was written for it, so re-approving or fixing the bundle is a real
    # drain rather than a lead deleted for good. EQUALITY, not `<= {"seen"}`: the subset form is
    # satisfied by the empty set, so it could not fail on a run that wrote no disposition at all —
    # and `seen` is exactly what a completed stage owes a shortlisted job it did not build.
    assert _dispositions(engine, failed[0]) == {"seen"}
    assert "built" in _dispositions(engine, summary.tailored[0].posting_id)


# -- a run-scoped cause inside the loop is a typed fatal, not a lead outcome --------------


def test_a_run_scoped_cause_inside_the_loop_is_a_typed_fatal(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`PINNED_SET_COMPILE_FAILED` is raised by `select` while building ONE lead and is still
    run-scoped: the pinned set comes from the frozen declaration, so it fails identically for every
    posting. `classify_lead_outcome` RAISES when handed it, so a loop that classified before routing
    by scope would abort the run with an `AssertionError` instead of recording this.

    The run must therefore end fatal, with the typed availability member, and stop rather than
    re-shelling out for every remaining lead — while still giving every lead it abandoned a terminal
    accounting, because the funnel's projection stage declares it entered at the ranker's shortlist
    and a lead counted nowhere makes that stage unreconcilable.
    """
    ids = _ready(env, 2)
    _projected_env(env)
    runner = _SelectRunner(fail_lead=1, fail_base=True)
    _use(monkeypatch, runner)

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.projection_availability is ProjectionAvailability.PINNED_SET_UNRENDERABLE
    assert summary.fatal is not None
    assert ProjectionAvailability.PINNED_SET_UNRENDERABLE.value in summary.fatal
    # No lead is given a CAUSE — the run-wide fault is `projection_availability` and `fatal`, said
    # once. What every abandoned lead does get is `NOT_ATTEMPTED`, which names no cause and exists
    # so `entered == advanced + drops` can still close: the lead this surfaced on, and the one
    # behind it that never got a turn. Before it, both were counted nowhere and the stage read
    # `2 in, 0 out, 0 dropped`.
    assert summary.projection_outcomes == Counter({ProjectionLeadOutcome.NOT_ATTEMPTED: 2})
    assert sorted(summary.projection_failed_ids) == sorted(ids)
    assert summary.tailored == []
    engine = get_engine(env)
    assert _run_status(engine, summary.run_id) == RUN_FAILED
    # The stage stopped at the first lead: one compile attempted, one scratch directory opened.
    assert len(runner.scratches) == 1
    # No lead earned any disposition — `seen` included, since the stage never presented anything.
    with engine.connect() as conn:
        assert conn.execute(select(tables.job_dispositions.c.job_id)).fetchall() == []


#: Every RUN-scoped member of the closed table, DERIVED from it rather than transcribed. Three of
#: them surface from inside the per-lead loop today, because `select()` raises them while building
#: one lead (`PINNED_SET_COMPILE_FAILED`, `PINNED_SET_EXCEEDS_BUDGET`,
#: `COMPILE_INFRASTRUCTURE_FAILURE`) — but a hardcoded list of those three cannot see a fourth
#: arriving, and the loop's routing has to hold for whichever ones reach it. Parametrising over the
#: whole run-scoped half of the table is a superset of what the loop can raise, so nothing drifts
#: past. Sorted for a deterministic parametrisation order.
RUN_SCOPED_ISSUES = sorted(
    issue for issue, scope in ISSUE_SCOPE.items() if isinstance(scope, ProjectionAvailability)
)


def test_the_run_scoped_derivation_is_not_vacuous() -> None:
    """An empty parametrisation collects no tests and reports green, so the derivation above needs a
    floor that does not come from itself: the three `select()` raises from inside the loop must all
    be in it. A LOWER bound, deliberately — the derived set is what the next test covers."""
    assert {
        ProjectionIssue.PINNED_SET_COMPILE_FAILED,
        ProjectionIssue.PINNED_SET_EXCEEDS_BUDGET,
        ProjectionIssue.COMPILE_INFRASTRUCTURE_FAILURE,
    } <= set(RUN_SCOPED_ISSUES)


@pytest.mark.parametrize("issue", RUN_SCOPED_ISSUES)
def test_every_run_scoped_cause_that_surfaces_per_lead_routes_by_scope(
    issue: ProjectionIssue,
) -> None:
    """Each must reach the availability catalog through `_projection_scope`; handed straight to
    `classify_lead_outcome`, each raises."""
    exc = ProjectionError(ProjectionViolation(issue=issue, message="m", where="w"))
    assert isinstance(_projection_scope(exc), ProjectionAvailability)


def test_a_per_lead_cause_and_a_foreign_one_route_to_their_own_catalogs() -> None:
    """Non-vacuity for the parametrised test above: `_projection_scope` is not a constant that
    calls everything run-scoped. A per-lead issue resolves to its lead member, and a foreign
    exception — which `classify_lead_outcome` refuses by construction — resolves run-scoped."""
    per_lead = ProjectionError(
        ProjectionViolation(issue=ProjectionIssue.NO_JD_EXTRACTION, message="m", where="w")
    )
    assert _projection_scope(per_lead) is ProjectionLeadOutcome.EXTRACTION_UNAVAILABLE
    assert _projection_scope(TemplateArtifactError("bad")) is ProjectionAvailability.TEMPLATE_INVALID


# -- the lineage arm is reached, not swallowed -------------------------------------------


def test_a_lineage_mismatch_reaches_its_own_outcome_not_the_generic_bucket(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`run_tailor` raises `ResumeLineageMismatch` when the file it was handed is not the document
    its lineage describes. Without an explicit arm the broad `except Exception` files that as an
    ordinary `tailor_failed` and `ProjectionLeadOutcome.LINEAGE_MISMATCH` can never be produced —
    a typed refusal degraded into a generic bucket, green all the way down.

    The swap is what is injected; the refusal is not. `project_for_posting` runs for real and then
    one byte is appended to the résumé it published, which is exactly the read/swap/read window
    `_master_from_lineage` exists to close.
    """
    ids = _ready(env, 2)
    _projected_env(env)
    _use(monkeypatch, _SelectRunner())

    real = runner_mod.project_for_posting
    tampered: list[int] = []

    def tampering(*args: object, **kwargs: object) -> ProjectionResult:
        result: ProjectionResult = real(*args, **kwargs)  # type: ignore[arg-type]
        if not tampered:
            tampered.append(1)
            with result.resume_path.open("ab") as handle:
                handle.write(b"\n# swapped after publication\n")
        return result

    monkeypatch.setattr(runner_mod, "project_for_posting", tampering)

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.projection_outcomes == Counter(
        {
            ProjectionLeadOutcome.PROJECTED: 1,
            ProjectionLeadOutcome.LINEAGE_MISMATCH: 1,
        }
    )
    # The claim this test exists for: it did NOT land in the generic per-lead bucket.
    assert summary.tailor_failed == 0
    assert summary.tailor_failed_ids == []
    # `served == projected + drops` — the identity a reader has to be able to close. The tampered
    # lead was counted PROJECTED when its sidecars landed and is retracted here, because
    # `run_tailor` refused it before parsing or rendering anything.
    assert len(ids) == sum(summary.projection_outcomes.values())
    assert summary.fatal is None, summary.errors
    assert len(summary.tailored) == 1
    failed = sorted(set(ids) - {lead.posting_id for lead in summary.tailored})
    assert summary.projection_failed_ids == failed
    assert _artifact_count_for(get_engine(env), failed[0]) == 0


# -- a write failure is a lead outcome, not an aborted run -------------------------------


def test_a_publication_failure_is_a_counted_lead_outcome(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`OUTPUT_IO_FAILURE` has a producer: `project_for_posting` translates the `OSError` from
    publishing the two sidecars into its own catalog. Left as a bare `OSError`, the loop would have
    routed it to `classify_availability`, which refuses an unmapped type — so a full disk aborted
    the run with an `AssertionError` instead of skipping the lead it happened to.

    The `OSError` is driven from INSIDE the real `_publish` rather than replacing it: the wrapper
    only plants a regular FILE where the first lead's output directory would go, and then calls the
    real function, whose `os.replace` into a path that is not a directory raises `ENOTDIR`. Replacing
    `_publish` wholesale left its atomic staging unexercised on this path, so the no-husk guarantee
    rested entirely on the `CANDIDATE_UNRENDERABLE` test; here the staging directory is really
    created, both payloads are really written into it, and the `finally` that removes it really runs
    — which the two extra assertions below read off the filesystem.
    """
    ids = _ready(env, 2)
    _projected_env(env)
    _use(monkeypatch, _SelectRunner())

    from boardwatch.projection import run as projection_run

    real_publish = projection_run._publish
    blocked: list[Path] = []

    def colliding(out_dir: Path, files: object) -> None:
        if not blocked:
            # A file, not a directory: `_publish` finds `out_dir.exists()` true and publishes each
            # payload individually with `os.replace(staging / name, out_dir / name)`, which cannot
            # descend into a regular file.
            out_dir.parent.mkdir(parents=True, exist_ok=True)
            out_dir.write_bytes(b"not a directory")
            blocked.append(out_dir)
        real_publish(out_dir, files)  # type: ignore[arg-type]

    monkeypatch.setattr(projection_run, "_publish", colliding)

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.projection_outcomes == Counter(
        {
            ProjectionLeadOutcome.OUTPUT_IO_FAILURE: 1,
            ProjectionLeadOutcome.PROJECTED: 1,
        }
    )
    assert summary.fatal is None, summary.errors
    assert len(summary.tailored) == 1
    failed = sorted(set(ids) - {lead.posting_id for lead in summary.tailored})
    assert summary.projection_failed_ids == failed
    assert _artifact_count_for(get_engine(env), failed[0]) == 0

    # Real staging, verified on disk: nothing was published into the blocked destination (its bytes
    # are untouched), and the sibling staging directory the failed `_publish` opened was removed by
    # its own `finally` rather than left beside the day's leads.
    assert blocked[0].read_bytes() == b"not a directory"
    day_dir = blocked[0].parent
    assert [p.name for p in day_dir.glob(".projection-*")] == []


# -- the negative control ---------------------------------------------------------------


def test_without_the_flag_no_projection_runs(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The projection material is installed and approved, and a compile runner that would fail
    every candidate is installed too. Without `--project` none of it is reached: the counter stays
    EMPTY (absent, not zeroed), every lead still ships, and the master is the authored résumé."""
    ids = _ready(env, 2)
    _projected_env(env)
    _use(monkeypatch, _SelectRunner(fail_lead=1, fail_base=True))

    summary = _pipeline(env, tmp_path / "apps", project=False)

    assert summary.projection_availability is None
    assert summary.projection_outcomes == Counter()
    assert summary.projection_failed_ids == []
    assert summary.fatal is None, summary.errors
    assert {lead.posting_id for lead in summary.tailored} == set(ids)
    masters = _master_uris(get_engine(env), summary.run_id)
    assert masters and all(uri.endswith("resume.yaml") for uri in masters), masters
