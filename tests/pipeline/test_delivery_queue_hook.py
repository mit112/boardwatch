"""The run hook: every run refreshes the delivery queue, and the queue can never fail a run.

A real schema, a real applications root and a real queue root, all on `tmp_path`. Nothing here
opens the live store or touches `~/boardwatch-queue`: `runner.DEFAULT_QUEUE_ROOT` is redirected by
name in **every** test, which is the seam the hook reads at call time for exactly this reason.

The load-bearing test is `test_a_raising_sync_never_fails_the_run`. It is the one that fails if the
`try/except` around the hook is deleted, and it was confirmed to fail that way before being counted
as done — every other test here stays green against an unguarded hook.

Every patch runs inside `pytest.MonkeyPatch.context()` rather than through the `monkeypatch`
fixture. That is not style: the fixture is shared with `env` and `queue_root`, so a single
`monkeypatch.undo()` before the assertions also reverts `BOARDWATCH_CONFIG_DIR` and the queue-root
redirect — which made one assertion here read the *live* config dir and compare against the
operator's own résumé instead of the scaffolded one. A context reverts only its own patch.

Two traps are deliberate:

- **The drain test's control.** `_snapshot` records the folder's contents before the second run, so
  "it moved to `_applied/`" is asserted against real bytes rather than against an empty directory a
  no-op drain could also produce.
- **Failures are simulated inside the queue's own collaborator, never by stubbing the queue.**
  `plan_lead_names` is patched so `sync_queue`'s real per-lead isolation runs and produces a real
  `SyncReport` with `failures`; stubbing `sync_queue` itself would prove only that a hand-built
  dataclass does not raise.
"""

from __future__ import annotations

import io
import json
import os
from dataclasses import replace
from pathlib import Path

import pytest
from filelock import FileLock
from rich.console import Console
from sqlalchemy import Connection, insert, select

from boardwatch.core.clock import utcnow
from boardwatch.core.settings import load_settings
from boardwatch.delivery import DRAIN_DIRS
from boardwatch.delivery import queue as queue_module
from boardwatch.delivery.api import FALLBACK_OWNER_NAME, resolve_owner_name
from boardwatch.delivery.queue import (
    APPLIED_DIR,
    DETAILS_FILE,
    LOCK_FILE,
    SKIPPED_DIR,
    FolderFailure,
    ReconcileReport,
    SyncReport,
)
from boardwatch.pipeline import runner as runner_module
from boardwatch.pipeline.runner import PipelineSummary, run_pipeline
from boardwatch.store import tables
from boardwatch.store.applications import MarkOutcome, mark_job_applied
from boardwatch.store.db import ensure_schema, get_engine

# `init` answers: 3 = skip the board wizard, then the profile prompts.
INIT_INPUT = "3\nacme\nBackend engineer: Python, Go, PostgreSQL.\n\n\n\nn\nn\n"
#: The stated requirement is load-bearing, not decoration. The pipeline evaluates this body for
#: real, and since A3 an evaluation that produces NO requirement row holds the lead in `_review` —
#: so a body the catalog reads nothing out of would put every lead in a drain and no assertion
#: about the queue root below could pass. `degree` is a `preference` family by default, so the row
#: makes the lead APPLY-lane rather than merely present.
BODY = (
    "We are hiring a backend engineer to work on Python and PostgreSQL services. "
    "Bachelor's degree in Computer Science required."
)


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Both boardwatch directories on `tmp_path`. `queue_detail` resolves the eligibility identity
    through a bare `load_settings()`, so the config dir has to be redirected too."""
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


def _seed_posting(data_dir: Path, n: int) -> int:
    """One open posting on its own company and its own job — the live 1:1 shape."""
    engine = get_engine(data_dir)
    ensure_schema(engine)
    now = utcnow()
    with engine.begin() as conn:
        company_id = int(
            conn.execute(
                insert(tables.companies).values(
                    name=f"Acme{n}",
                    provider="greenhouse",
                    slug=f"acme{n}",
                    source="user",
                    watched=False,
                )
            ).inserted_primary_key[0]
        )
        job_id = int(
            conn.execute(insert(tables.jobs).values(created_at=now)).inserted_primary_key[0]
        )
        posting_id = int(
            conn.execute(
                insert(tables.postings).values(
                    company_id=company_id,
                    provider_posting_id=f"p-{n}",
                    job_id=job_id,
                    title="Backend Engineer",
                    normalized_title="backend engineer",
                    url=f"https://example.test/j/{n}",
                    locations_json=["Remote"],
                    remote_policy="remote",
                    first_seen_at=now,
                    last_seen_at=now,
                    status="open",
                    consecutive_missing=0,
                    content_hash=f"h-{n}",
                    body_text=BODY,
                )
            ).inserted_primary_key[0]
        )
        conn.execute(
            insert(tables.posting_versions).values(
                posting_id=posting_id,
                content_hash=f"h-{n}",
                body_text=BODY,
                captured_at=now,
                capture_reason="new",
            )
        )
    return posting_id


def _ready(data_dir: Path, count: int) -> list[int]:
    from typer.testing import CliRunner

    from boardwatch.cli.app import app

    cli = CliRunner()
    ids = [_seed_posting(data_dir, n) for n in range(count)]
    assert cli.invoke(app, ["--data-dir", str(data_dir), "init"], input=INIT_INPUT).exit_code == 0
    assert cli.invoke(app, ["--data-dir", str(data_dir), "tailor", "init"]).exit_code == 0
    return ids


def _run(
    data_dir: Path,
    out_root: Path,
    *,
    top_n: int = 1,
    queue_root: Path | None = None,
) -> tuple[PipelineSummary, str]:
    """One pipeline run and everything it printed. Width is pinned wide so the queue line, which
    carries the counts this hook exists to surface AND the queue root, is not folded mid-line.
    The root here is a pytest-xdist tmp path (~130 chars deep) whose length grows with the run
    counter and worker id, so the pin must clear any tmp path, not merely a short production one.

    `queue_root` is passed through only when given, so every caller that does not care about it
    (every test in this file except the T5 override tests below) still calls `run_pipeline` with
    exactly the signature it had before T5 — the override tests are the only ones that should fail
    against a `run_pipeline` that does not yet accept the parameter.
    """
    buffer = io.StringIO()
    settings = load_settings(data_dir=data_dir)
    kwargs: dict[str, object] = {}
    if queue_root is not None:
        kwargs["queue_root"] = queue_root
    summary = run_pipeline(
        get_engine(data_dir),
        settings,
        console=Console(file=buffer, width=10_000),
        out_root=out_root,
        resume_path=settings.config_dir / "resume.yaml",
        skip_scan=True,
        top_n=top_n,
        **kwargs,
    )
    return summary, buffer.getvalue()


def _folders(where: Path) -> list[str]:
    """The lead folders directly under `where`. The two drains are structural and are excluded, so
    an empty result means "no lead lives here" rather than "the root was never created"."""
    if not where.is_dir():
        return []
    return sorted(
        path.name
        for path in where.iterdir()
        if path.is_dir()
        and not path.name.startswith(".")
        and path.name not in DRAIN_DIRS
    )


def _snapshot(folder: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(folder.iterdir()) if p.is_file()}


def _status(data_dir: Path, run_id: int) -> str:
    with get_engine(data_dir).connect() as conn:
        return str(
            conn.execute(select(tables.runs.c.status).where(tables.runs.c.id == run_id)).scalar_one()
        )


def _errors_json(data_dir: Path, run_id: int) -> list[str]:
    """The run row's own error list. Read through the store rather than off `summary.errors`,
    because the queue hook runs AFTER `finish_run` — a note that only reaches the summary is
    invisible to everything that reads the database, which is the whole point of asserting it
    here as well as there (D-287)."""
    with get_engine(data_dir).connect() as conn:
        return list(
            conn.execute(
                select(tables.runs.c.errors_json).where(tables.runs.c.id == run_id)
            ).scalar_one()
            or []
        )


def _job_id(data_dir: Path, posting_id: int) -> int:
    with get_engine(data_dir).connect() as conn:
        return int(
            conn.execute(
                select(tables.postings.c.job_id).where(tables.postings.c.id == posting_id)
            ).scalar_one()
        )


def _queue_line(output: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip().startswith("queue →")]
    assert len(lines) == 1, f"expected exactly one queue log line, got {lines!r}"
    return lines[0]


@pytest.fixture()
def queue_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the hook's root. Patched on `pipeline.runner`, not on `delivery.queue`: the hook
    reads its own module's binding, so patching the definition site would not reach it and every
    test in this file would write into the owner's real home."""
    root = tmp_path / "queue"
    monkeypatch.setattr(runner_module, "DEFAULT_QUEUE_ROOT", root)
    return root


def test_a_run_that_delivers_leads_fills_the_queue(
    env: Path, tmp_path: Path, queue_root: Path
) -> None:
    posting_ids = _ready(env, 1)
    summary, output = _run(env, tmp_path / "apps")

    assert len(summary.tailored) == 1, summary.errors
    folders = _folders(queue_root)
    assert len(folders) == 1, f"{folders!r} under {queue_root}"
    details = json.loads((queue_root / folders[0] / DETAILS_FILE).read_text(encoding="utf-8"))
    assert details["posting_id"] == posting_ids[0]
    assert details["job_id"] == _job_id(env, posting_ids[0])
    # The counts reach the operator, not just the disk.
    assert "1 new" in _queue_line(output)


def test_a_run_that_delivers_nothing_still_drains_an_applied_lead(
    env: Path, tmp_path: Path, queue_root: Path
) -> None:
    """The reason the hook is unconditional. Applying happens on the web page between runs, so the
    folder for an applied lead has to retire on a day that delivered nothing at all."""
    posting_ids = _ready(env, 1)
    out_root = tmp_path / "apps"
    _run(env, out_root)
    folder = _folders(queue_root)[0]
    contents = _snapshot(queue_root / folder)
    assert contents, "an empty folder would make the move below unfalsifiable"

    with get_engine(env).begin() as conn:
        marked = mark_job_applied(conn, posting_id=posting_ids[0], source="web")
    assert marked.outcome is MarkOutcome.CREATED, marked

    second, output = _run(env, out_root)

    assert second.tailored == [], "the corpus was exhausted; this must be an empty day"
    assert second.fatal is None, second.fatal
    assert _folders(queue_root) == []
    assert _folders(queue_root / APPLIED_DIR) == [folder]
    # Moved, not re-created: the same bytes.
    assert _snapshot(queue_root / APPLIED_DIR / folder) == contents
    assert "1 moved" in _queue_line(output)


def test_a_raising_sync_never_fails_the_run(env: Path, tmp_path: Path, queue_root: Path) -> None:
    """**The guard, and the only test here that fails without it.**

    The run's deliverables are the résumé and the funnel; the queue is a copy of what the store
    already holds. So a queue that cannot be written costs the queue and nothing else: the run
    still returns, still reports `status=ok`, and its funnel is still on disk.
    """
    _ready(env, 1)

    def boom(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("queue root is on fire")

    with pytest.MonkeyPatch.context() as patched:
        patched.setattr(runner_module, "sync_queue", boom)
        summary, output = _run(env, tmp_path / "apps")

    assert summary.fatal is None, summary.fatal
    assert len(summary.tailored) == 1, summary.errors
    assert _status(env, summary.run_id) == "ok"
    assert summary.funnel is not None
    assert summary.funnel.markdown_path.is_file()
    # Reported, never silent: the note reaches the summary `run_cmd` prints and the console.
    assert [note for note in summary.errors if "delivery queue not synced" in note]
    assert "queue root is on fire" in output
    # Durable, not only printed: the sync runs after `finish_run`, so without an explicit
    # `append_run_error` the note never reaches `runs.errors_json` and an unattended queue
    # failure is invisible to anything reading the store (D-287). This fails against that gap.
    assert [note for note in _errors_json(env, summary.run_id) if "delivery queue not synced" in note]


def test_contention_is_not_a_failure(env: Path, tmp_path: Path, queue_root: Path) -> None:
    """A scheduled run colliding with a serving web app changed nothing and is not an error.

    The lock is really held rather than the report stubbed, and the reclaim window is pinned to
    zero so this measures the refusal instead of the platform's Windows allowance.
    """
    _ready(env, 1)
    queue_root.mkdir(parents=True, exist_ok=True)
    with pytest.MonkeyPatch.context() as patched:
        patched.setattr(queue_module, "RECLAIM_WINDOW_SECONDS", 0.0)
        holder = FileLock(str(queue_root / LOCK_FILE))
        holder.acquire(blocking=False)
        try:
            summary, output = _run(env, tmp_path / "apps")
        finally:
            holder.release()

    assert summary.fatal is None, summary.fatal
    assert _status(env, summary.run_id) == "ok"
    assert [note for note in summary.errors if "queue" in note] == []
    assert "contended" in _queue_line(output)
    assert "0 failed" in _queue_line(output)
    assert _folders(queue_root) == [], "a contended sync wrote anyway"


def test_per_lead_queue_failures_are_recorded_and_never_propagate(
    env: Path, tmp_path: Path, queue_root: Path
) -> None:
    """`sync_queue` reports a lead it could not write inside its report rather than raising. The
    hook counts that into its log line, escalates it to the run's error list and to the run row,
    and returns — it still never re-raises and still never fails the run.

    Recorded is the NEW half of the contract and it inverts what this test used to assert. The
    count was console-only, which is defensible while somebody is watching the run and is not
    defensible unattended: `run_cmd` prints the queue line to a log file nobody opens, so a queue
    that silently stopped copying leads was byte-identical in the store to one that copied every
    one of them, and the owner would keep trusting a queue that had quietly gone empty.

    The failure is simulated inside the queue's own collaborator, never by stubbing the queue, so
    `sync_queue`'s real per-lead isolation runs and produces a real `SyncReport` with `failures`.

    Non-fatal is asserted alongside, in three places at once — `summary.fatal`, the run's status,
    and the lead still being tailored — because the escalation must not have turned a queue copy
    failure into a run outcome. The queue holds COPIES; the dated tree is the real output.
    """

    def unplannable(**_kwargs: object) -> object:
        raise RuntimeError("no name fits")

    _ready(env, 1)
    with pytest.MonkeyPatch.context() as patched:
        patched.setattr(queue_module, "plan_lead_names", unplannable)
        summary, output = _run(env, tmp_path / "apps")

    assert summary.fatal is None, summary.fatal
    assert len(summary.tailored) == 1, summary.errors
    assert _status(env, summary.run_id) == "ok"
    assert "1 failed" in _queue_line(output)
    assert _folders(queue_root) == [], "a lead that could not be planned was written anyway"
    # Both halves, and the store one is the load-bearing one: a note on the summary alone is gone
    # the moment the process exits.
    assert [note for note in summary.errors if "delivery queue" in note], summary.errors
    recorded = [note for note in _errors_json(env, summary.run_id) if "delivery queue" in note]
    assert recorded, _errors_json(env, summary.run_id)
    assert "1" in recorded[0], f"the note does not carry the failed count: {recorded[0]!r}"


def test_the_owner_name_comes_from_the_profile(
    env: Path, tmp_path: Path, queue_root: Path
) -> None:
    """The copied résumé is named from the owner's own data (design §4.1), so the hook must hand
    `sync_queue` the name the résumé filename already resolves from — not a constant, and not the
    `owner` fallback that means "no name was found". The fallback is asserted to be a DIFFERENT
    string first, because otherwise the equality below would hold for a hook that resolved nothing.
    """
    _ready(env, 1)
    seen: list[str] = []
    real = queue_module.sync_queue

    def spy(conn: Connection, *, root: Path, owner_name: str) -> SyncReport:
        seen.append(owner_name)
        return real(conn, root=root, owner_name=owner_name)

    with pytest.MonkeyPatch.context() as patched:
        patched.setattr(runner_module, "sync_queue", spy)
        _run(env, tmp_path / "apps")

    expected = resolve_owner_name(None, load_settings(data_dir=env).config_dir)
    assert expected != FALLBACK_OWNER_NAME, "no name resolved; the assert below would be vacuous"
    assert seen == [expected]


def test_the_hook_never_reads_the_real_queue_root(
    env: Path, tmp_path: Path, queue_root: Path
) -> None:
    """The seam this file rests on, asserted rather than assumed: the hook resolves the root from
    `pipeline.runner`'s own binding at call time. If it ever captured `DEFAULT_QUEUE_ROOT` in a
    default argument or read `delivery.queue` directly, every test above would silently write into
    the owner's home and this one would fail."""
    _ready(env, 1)
    _run(env, tmp_path / "apps")

    # `_ensure_root` builds the root and both drains on every call, so their presence under
    # `tmp_path` is the hook's footprint. The lockfile is not asserted: `filelock` unlinks it on
    # release, so its absence would say nothing.
    assert (queue_root / APPLIED_DIR).is_dir(), "the hook did not use the redirected root"
    assert (queue_root / SKIPPED_DIR).is_dir()
    assert queue_root.is_relative_to(tmp_path)


def test_a_drain_failure_is_escalated_too(env: Path, tmp_path: Path, queue_root: Path) -> None:
    """The hook reports `synced.failed + drained.failed`, and only the sync half of that sum has a
    natural provocation in this file — the `plan_lead_names` trap above. Without this test a
    version that returned `synced.failed` alone ships green, and a queue whose `_applied` drain had
    stopped moving folders stays exactly as silent as the per-lead case used to be.

    The real `reconcile_queue` still runs and still does its real work; only one synthetic failure
    is appended to the report on the way out. That is deliberately not the same thing as the
    hand-built report this module's docstring warns against: what is asserted here is the hook's
    arithmetic over a report, not the queue's own per-folder isolation.
    """
    _ready(env, 1)
    real = runner_module.reconcile_queue

    def with_a_drain_failure(conn: Connection, *, root: Path) -> ReconcileReport:
        report = real(conn, root=root)
        return replace(
            report, failures=(*report.failures, FolderFailure("acme0-backend", "drain broke"))
        )

    with pytest.MonkeyPatch.context() as patched:
        patched.setattr(runner_module, "reconcile_queue", with_a_drain_failure)
        summary, output = _run(env, tmp_path / "apps")

    assert summary.fatal is None, summary.fatal
    assert _status(env, summary.run_id) == "ok"
    assert "1 failed" in _queue_line(output)
    assert [note for note in summary.errors if "delivery queue" in note], summary.errors
    assert [note for note in _errors_json(env, summary.run_id) if "delivery queue" in note]


# --- T5: queue root override on `run` -----------------------------------------------------
#
# The three tests below are T5's acceptance tests (docs/program/TICKETS-2026-09-04.md). They are
# appended here rather than in a new file because this module already owns the seam
# (`runner_module.DEFAULT_QUEUE_ROOT`) and the seeding helpers (`_ready`, `_folders`) T5 needs, and
# duplicating a working `init` + `tailor init` + one-posting seed elsewhere would be the actual
# hazard the ticket is about, not a saving.


def test_run_pipeline_queue_root_param_overrides_the_module_default(
    env: Path, tmp_path: Path, queue_root: Path
) -> None:
    """`run_pipeline(queue_root=...)` must win over `DEFAULT_QUEUE_ROOT` — the parameter
    `--queue-root` threads through. The `queue_root` fixture leaves `runner_module.
    DEFAULT_QUEUE_ROOT` pointed at a scratch decoy (never the owner's real home): if the explicit
    parameter were ignored, the decoy — not `explicit_root` below — would receive the lead folder.
    """
    _ready(env, 1)
    explicit_root = tmp_path / "explicit-queue"
    summary, output = _run(env, tmp_path / "apps", queue_root=explicit_root)

    assert len(summary.tailored) == 1, summary.errors
    assert len(_folders(explicit_root)) == 1, f"{_folders(explicit_root)!r} under {explicit_root}"
    assert _folders(queue_root) == [], "the decoy default must never be touched"
    assert str(explicit_root) in _queue_line(output)


def test_run_cli_queue_root_option_overrides_the_default(
    env: Path, tmp_path: Path, queue_root: Path
) -> None:
    """`boardwatch run --queue-root PATH` must reach the same hook `run_pipeline(queue_root=...)`
    does. Same decoy-default reasoning as the test above, but driven through the actual CLI
    command (`run_cmd.run`) rather than by calling `run_pipeline` directly, so the option's
    plumbing through `run_cmd` and into the pipeline is what is under test here."""
    from typer.testing import CliRunner

    from boardwatch.cli.app import app

    _ready(env, 1)
    explicit_root = tmp_path / "cli-queue"
    result = CliRunner().invoke(
        app,
        [
            "--data-dir",
            str(env),
            "run",
            "--no-scan",
            "--out",
            str(tmp_path / "apps"),
            "--queue-root",
            str(explicit_root),
        ],
    )

    assert result.exit_code == 0, result.output
    assert len(_folders(explicit_root)) == 1, f"{_folders(explicit_root)!r} under {explicit_root}"
    assert _folders(queue_root) == [], "the decoy default must never be touched"


def test_run_refuses_when_data_dir_env_drives_the_store_and_no_queue_root_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The case that actually bites (T5): `BOARDWATCH_DATA_DIR` silently points a run at a
    scratch store while the queue hook still defaults to the owner's real `~/boardwatch-queue`.
    `run` must refuse rather than reconcile the real queue against the scratch store's authority.

    No extra environment setup for the precondition itself: `tests/conftest.py`'s autouse
    `_never_reach_the_real_data_dir` fixture already sets `BOARDWATCH_DATA_DIR` to a scratch path
    for every test in the suite, which is exactly the precondition this guards — the only thing
    this test controls beyond `COLUMNS` (below) is NOT passing `--data-dir`, which is what makes
    the env var the thing actually choosing the store (CLI `--data-dir` outranks it per
    `core/settings.py`'s documented precedence, which is also why this guard must not fire for
    every other CLI-driven test in this file: they all pass `--data-dir` explicitly).

    `COLUMNS` is widened because Click/Rich wraps a `BadParameter` message's box to the terminal
    width, and a pytest tmp path is long enough that the wrap can split the asserted path across
    two lines — a test artifact of the error's presentation, not of the refusal itself.
    """
    from typer.testing import CliRunner

    from boardwatch.cli.app import app

    monkeypatch.setenv("COLUMNS", "10000")
    data_dir_env = os.environ["BOARDWATCH_DATA_DIR"]
    result = CliRunner().invoke(app, ["run", "--no-scan"])

    assert result.exit_code != 0, result.output
    assert data_dir_env in result.output
    # The refusal must fire before any store I/O — never mind the queue — so no `runs` row (and
    # not even a schema) exists at the path the env var named.
    assert not (Path(data_dir_env) / "boardwatch.db").exists()
