"""`boardwatch run --project` refuses BEFORE any lead earns a ledger disposition.

The defect this exists to prevent is not "the run does not fail" — it is a run that fails
*correctly* and still destroys the queue. An earlier design had projection fall back to the
authored résumé. A fallback SUCCEEDS, so every lead entered `summary.tailored`, `built_ids` is
derived from exactly that set (`runner._record_shortlist_dispositions`), and each lead earned a
PERMANENT `built` the ledger then suppresses on every later run. Re-approving projection could
never have recovered them: there is no drain for a `built` that names an artifact nobody wanted.

The other half is that "it refused" is not a run state. Only `summary.fatal` decides the persisted
status, and `cli/run_cmd.py` deliberately exits 0 for non-fatal stage errors — so an early `return`
that left `fatal` as `None` would write `status=ok` and exit 0 while producing nothing, which is
exactly the "reports success while producing nothing" P3's gate forbids.

Both halves are asserted in ONE test, on purpose: four of them pass while the fifth is broken.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime
from importlib import resources
from pathlib import Path

import pytest
from rich.console import Console
from sqlalchemy import Engine, func, select
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.core.settings import load_settings
from boardwatch.pipeline.runner import PipelineSummary, run_pipeline
from boardwatch.profile_bundle.paths import BUNDLE_DIR_NAME
from boardwatch.projection.declaration import load_declaration, projection_digest
from boardwatch.projection.run import ProjectionAvailability, ProjectionLeadOutcome
from boardwatch.projection.stamp import write_stamp
from boardwatch.store import tables
from boardwatch.store.db import get_engine
from boardwatch.store.queries import RUN_FAILED, RUN_OK

# The pipeline half — seeded postings on unwatched companies, plus `init`/`tailor init` — is
# reused rather than re-implemented: `tests/pipeline/test_ledger_advances_the_queue.py` already
# assembles exactly the environment the ledger claims are made against, which is the environment
# whose dispositions this test counts.
from tests.conftest import write_test_resume_template
from tests.pipeline.test_ledger_advances_the_queue import _ready
from tests.profile_bundle.conftest import promote_example_tree

cli = CliRunner()

#: A minimal, valid header/education shell — the file the packaged declaration's
#: `shell_source: master_resume.yaml` resolves to against `config_dir`. Plain fixture data,
#: identical in shape to `tests/projection/conftest.py`'s own.
_SHELL_BODY = (
    "header:\n"
    "  - Example Candidate\n"
    "  - candidate@example.com\n"
    "education:\n"
    "  - Example University\n"
)

#: A syntactically valid bundle digest that no promotion can ever produce. Stamping the real
#: declaration digest against THIS is what makes the approval stale for real — `project_pool`
#: compares `stamp.bundle_digest` to the revision actually being read (D-167) — rather than
#: monkeypatching the raise.
WRONG_BUNDLE_DIGEST = "sha256:" + "1" * 64

#: Deliberately far from any real "today", so a `date.today()` implementation cannot coincide with
#: the frozen `utcnow()` the clock test injects.
FROZEN_NOW = datetime(2027, 3, 4, 23, 30, tzinfo=UTC)


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


def _config_dir(data_dir: Path) -> Path:
    return load_settings(data_dir=data_dir).config_dir


def _install_projection(config_dir: Path) -> str:
    """Promote a bundle at the root the pipeline itself resolves and copy the packaged declaration
    beside it. Returns the promoted bundle digest.

    The bundle goes to `config_dir / BUNDLE_DIR_NAME` because that is what
    `resolve_bundle_root(settings.config_dir, None)` returns and the pipeline passes no override —
    so this exercises the pipeline's own path resolution rather than a path the test chose.

    The declaration is the packaged example, copied byte for byte rather than restated: its
    `shell_source` is RELATIVE, which is what makes the shell lookup a real resolution against
    `config_dir`.
    """
    bundle_digest = promote_example_tree(config_dir / BUNDLE_DIR_NAME).bundle_digest
    (config_dir / "master_resume.yaml").write_text(_SHELL_BODY, encoding="utf-8")
    # T2: `resolve_template` fails closed on a config dir missing `resume_template.tex`, and the
    # pipeline's projection stage renders through the real
    # `LatexRenderer(config_dir=settings.config_dir)` — so this environment needs one on disk, as
    # a properly set-up user's config dir would.
    write_test_resume_template(config_dir)
    traversable = resources.files("boardwatch.projection.examples").joinpath(
        "projection.example.yaml"
    )
    with resources.as_file(traversable) as packaged:
        declaration_text = packaged.read_text(encoding="utf-8")
    (config_dir / "projection.yaml").write_text(declaration_text, encoding="utf-8")
    return bundle_digest


def _approve(config_dir: Path, bundle_digest: str) -> None:
    """File a projection approval for the declaration on disk, bound to `bundle_digest`.

    `stamp_path` is a pure function of the DECLARATION digest, so calling this a second time with
    the real bundle digest overwrites the stale stamp rather than leaving two — which is what
    `approve-projection` does, and what makes the retry in the headline test a genuine
    re-approval instead of a fresh environment.
    """
    write_stamp(
        config_dir,
        digest=projection_digest(load_declaration(config_dir / "projection.yaml")),
        bundle_digest=bundle_digest,
        approved_at=datetime(2026, 8, 13, 12, tzinfo=UTC),
    )


def _pipeline(
    data_dir: Path, out_root: Path, *, project: bool, top_n: int = 2
) -> PipelineSummary:
    settings = load_settings(data_dir=data_dir)
    return run_pipeline(
        get_engine(data_dir),
        settings,
        console=Console(quiet=True),
        out_root=out_root,
        resume_path=settings.config_dir / "resume.yaml",
        skip_scan=True,
        top_n=top_n,
        project=project,
    )


def _disposition_count(engine: Engine) -> int:
    """Every row in the ledger, counted straight off the table rather than through
    `load_dispositions`/`live_dispositions`. Those two filter (by job, by liveness), and a filtered
    count of zero is not the claim being made: what must be true is that the table is EMPTY."""
    with engine.connect() as conn:
        return int(
            conn.execute(select(func.count()).select_from(tables.job_dispositions)).scalar_one()
        )


def _run_count(engine: Engine) -> int:
    """Every `runs` row. The pipeline mints one before it can refuse anything (`scan/coordinator`
    creates it inside the scan lock, and `ensure_run` does on `--no-scan`), so a CLI-boundary
    refusal is only genuinely "before any state is created" if this stays at zero."""
    with engine.connect() as conn:
        return int(conn.execute(select(func.count()).select_from(tables.runs)).scalar_one())


def _run_status(engine: Engine, run_id: int) -> str:
    with engine.connect() as conn:
        return str(
            conn.execute(
                select(tables.runs.c.status).where(tables.runs.c.id == run_id)
            ).scalar_one()
        )


# -- the headline claim ----------------------------------------------------------------


def test_a_stale_stamp_fails_the_run_and_consumes_no_leads(env: Path, tmp_path: Path) -> None:
    """FIVE assertions in one test on purpose.

    A run that refuses but exits 0 is P3's "reporting success while producing nothing". A run that
    refuses AFTER dispositions are written destroys the drain — and each of those two failures is
    invisible to the other's assertion, so neither may be split into its own test where a
    regression could turn one green while the other is red.
    """
    ids = _ready(env, 2)
    config_dir = _config_dir(env)
    real_digest = _install_projection(config_dir)
    # Approved — but against a revision that is not the one on disk.
    _approve(config_dir, WRONG_BUNDLE_DIGEST)
    engine = get_engine(env)
    out_root = tmp_path / "apps"

    summary = _pipeline(env, out_root, project=True)

    # The TYPED cause. Asserted on the enum member, never by matching `fatal`'s text, and it is
    # what tells `STALE_APPROVAL` (re-approve) apart from `MISSING_APPROVAL` (approve at all).
    assert summary.projection_availability is ProjectionAvailability.STALE_APPROVAL
    assert summary.fatal is not None
    # (2) the persisted failure. `fatal` is the only field `finish_run` reads, so a `return` that
    # forgot to set it would land here as `ok`.
    assert _run_status(engine, summary.run_id) == RUN_FAILED
    # (3) visible in the artifact, which Gate P0 requires to be answerable on its own.
    #
    # Asserted on the FATAL **line**, not on the substring "FATAL". A bare `"FATAL" in markdown`
    # cannot fail on this path and was measured not to: the shortlist stage's NOT-INSTRUMENTED
    # note — which is what a refused run always emits, because `summary.shortlist` is None —
    # spells the word in its own prose ("it is whatever the FATAL line and the Errors section
    # below say", `reports/run_funnel.py:629`). Passing `fatal=None` to the writer left that
    # substring assertion green. The line must also NAME the availability member, so the artifact
    # answers *which* refusal on its own rather than only *that* one happened.
    assert summary.funnel is not None
    markdown = summary.funnel.markdown_path.read_text(encoding="utf-8")
    fatal_lines = [line for line in markdown.splitlines() if line.startswith("- **FATAL:**")]
    assert len(fatal_lines) == 1, markdown
    assert ProjectionAvailability.STALE_APPROVAL.value in fatal_lines[0]
    # Nothing was rendered, so there is no lead a `built` could have named.
    assert summary.tailored == []

    # (1) exit code 1. This is `run_cmd.py`'s own mapping, and it is not implied by any assertion
    # above: that module deliberately exits 0 for non-fatal stage errors, so only invoking it
    # proves a refusal is not one of those. A second refused run, which must also consume nothing.
    result = cli.invoke(
        app,
        [
            "--data-dir", str(env),
            "run", "--no-scan", "--project", "--no-check-liveness",
            "--top", "2", "--out", str(out_root),
        ],
    )
    assert result.exit_code == 1, result.output

    # (4) no lead consumed — after BOTH refusals. `built`, `skipped` and `seen` all live in this
    # one table, and any of the three would suppress these jobs on the retry below.
    assert _disposition_count(engine) == 0

    # (5) retry visibility. The whole point of failing closed: re-approving is a real drain, so the
    # same postings are still reachable rather than permanently `built`.
    _approve(config_dir, real_digest)
    second = _pipeline(env, out_root, project=True)

    assert second.projection_availability is ProjectionAvailability.AVAILABLE
    assert second.fatal is None
    assert {lead.posting_id for lead in second.tailored} == set(ids)
    # Non-vacuity for the set above: the shortlist was not empty in the first place.
    assert ids


# -- the negative control -------------------------------------------------------------


def test_without_the_flag_nothing_changes(env: Path, tmp_path: Path) -> None:
    """The projection material is installed and left DELIBERATELY stale. Without `--project` the
    preflight never runs, so a refusal-worthy configuration must be entirely invisible — otherwise
    this change would have made every existing run depend on a bundle nobody asked it to read."""
    ids = _ready(env, 2)
    config_dir = _config_dir(env)
    _install_projection(config_dir)
    _approve(config_dir, WRONG_BUNDLE_DIGEST)

    summary = _pipeline(env, tmp_path / "apps", project=False)

    # `None`, not `AVAILABLE`: a run that never asked has no verdict, and claiming `AVAILABLE`
    # would assert a resolve that never happened.
    assert summary.projection_availability is None
    # Empty, not zeroed per member: a later task omits a funnel stage entirely on the difference
    # between "absent" and "0", so an outcome nothing reached must not be present at all.
    assert summary.projection_outcomes == Counter()
    assert ProjectionLeadOutcome.PROJECTED not in summary.projection_outcomes
    assert summary.fatal is None
    assert _run_status(get_engine(env), summary.run_id) == RUN_OK
    assert {lead.posting_id for lead in summary.tailored} == set(ids)


# -- the classification is not a constant ---------------------------------------------


def test_a_missing_approval_is_its_own_availability_member(env: Path, tmp_path: Path) -> None:
    """Non-vacuity for the headline test: the member tracks the CAUSE rather than being a constant
    the preflight always writes. No stamp at all is a different member pointing at a different
    remedy, and an operator sent to "re-approve" when they have never approved is sent nowhere."""
    _ready(env, 1)
    _install_projection(_config_dir(env))  # no approval filed at all

    summary = _pipeline(env, tmp_path / "apps", project=True)

    assert summary.projection_availability is ProjectionAvailability.MISSING_APPROVAL
    assert summary.fatal is not None
    assert _disposition_count(get_engine(env)) == 0


# -- `--project` and `--resume` cannot both be honoured --------------------------------


def test_project_with_an_explicit_resume_refuses_before_any_state_exists(
    env: Path, tmp_path: Path
) -> None:
    """Both options describe an active choice of document source, and the pipeline can only obey
    one: every projected lead overwrites `lead_resume_path` with the projection's own file, so
    `--resume custom.yaml` had NO EFFECT and said nothing about it. Silent precedence is the worst
    of the three possible answers, and what the combination should mean is P5b's question — so the
    CLI refuses until the owner rules it.

    Asserted at the boundary, not merely on the exit code: a refusal that first minted a `runs` row
    would burn a row per typo and leave `doctor` reporting an unfinished run, and one that got as
    far as a disposition would suppress the very leads it never worked. Exit 2, not 1: this is a
    usage error, not a run that failed — nothing about the store or the bundle is wrong.
    """
    _ready(env, 2)
    config_dir = _config_dir(env)
    _approve(config_dir, _install_projection(config_dir))
    custom = tmp_path / "custom.yaml"
    custom.write_text("header: []\n", encoding="utf-8")

    result = cli.invoke(
        app,
        [
            "--data-dir", str(env),
            "run", "--no-scan", "--project", "--no-check-liveness",
            "--resume", str(custom), "--top", "2", "--out", str(tmp_path / "apps"),
        ],
    )

    assert result.exit_code == 2, result.output
    assert "--resume" in result.output and "--project" in result.output
    engine = get_engine(env)
    assert _run_count(engine) == 0
    assert _disposition_count(engine) == 0
    # Non-vacuity: the same invocation WITHOUT `--resume` is accepted and does mint a run, so the
    # zeros above are the refusal's doing and not an environment that could never have run.
    accepted = cli.invoke(
        app,
        [
            "--data-dir", str(env),
            "run", "--no-scan", "--project", "--no-check-liveness",
            "--top", "2", "--out", str(tmp_path / "apps"),
        ],
    )
    assert accepted.exit_code == 0, accepted.output
    assert _run_count(engine) == 1


# -- one clock, one date ---------------------------------------------------------------


def test_as_of_is_one_reading_of_the_runs_own_clock(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`as_of` feeds effective-fact resolution, so it decides WHICH facts render — it is not
    cosmetic. It must be `utcnow().date()` from the same clock the `runs` row uses, read ONCE.

    `utcnow` is frozen to a date far from any real "today" so the test discriminates: a
    `date.today()` implementation (the LOCAL date, which nothing in this codebase reads for `as_of`
    any more) would record the real date here and fail, and a per-lead re-read would append more
    than one entry.
    """
    _ready(env, 2)
    config_dir = _config_dir(env)
    _approve(config_dir, _install_projection(config_dir))

    import boardwatch.pipeline.runner as runner_mod

    real = runner_mod.resolve_projection_run
    seen: list[date] = []

    def spy(*args: object, **kwargs: object) -> object:
        as_of = kwargs["as_of"]
        assert isinstance(as_of, date)
        seen.append(as_of)
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(runner_mod, "resolve_projection_run", spy)
    monkeypatch.setattr(runner_mod, "utcnow", lambda: FROZEN_NOW)

    summary = _pipeline(env, tmp_path / "apps", project=True)

    assert summary.fatal is None
    assert seen == [FROZEN_NOW.date()]
