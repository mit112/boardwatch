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
from pathlib import Path

import pytest
from filelock import FileLock
from rich.console import Console
from sqlalchemy import Connection, insert, select

from boardwatch.core.clock import utcnow
from boardwatch.core.settings import load_settings
from boardwatch.delivery import queue as queue_module
from boardwatch.delivery.api import FALLBACK_OWNER_NAME, resolve_owner_name
from boardwatch.delivery.queue import (
    APPLIED_DIR,
    DETAILS_FILE,
    INELIGIBLE_DIR,
    LOCK_FILE,
    SKIPPED_DIR,
    SyncReport,
)
from boardwatch.pipeline import runner as runner_module
from boardwatch.pipeline.runner import PipelineSummary, run_pipeline
from boardwatch.store import tables
from boardwatch.store.applications import MarkOutcome, mark_job_applied
from boardwatch.store.db import ensure_schema, get_engine

# `init` answers: 3 = skip the board wizard, then the profile prompts.
INIT_INPUT = "3\nacme\nBackend engineer: Python, Go, PostgreSQL.\n\n\n\nn\nn\n"
BODY = "We are hiring a backend engineer to work on Python and PostgreSQL services."


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


def _run(data_dir: Path, out_root: Path, *, top_n: int = 1) -> tuple[PipelineSummary, str]:
    """One pipeline run and everything it printed. Width is pinned wide so the queue line, which
    carries the counts this hook exists to surface AND the queue root, is not folded mid-line.
    The root here is a pytest-xdist tmp path (~130 chars deep) whose length grows with the run
    counter and worker id, so the pin must clear any tmp path, not merely a short production one."""
    buffer = io.StringIO()
    settings = load_settings(data_dir=data_dir)
    summary = run_pipeline(
        get_engine(data_dir),
        settings,
        console=Console(file=buffer, width=10_000),
        out_root=out_root,
        resume_path=settings.config_dir / "resume.yaml",
        skip_scan=True,
        top_n=top_n,
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
        and path.name not in (APPLIED_DIR, SKIPPED_DIR, INELIGIBLE_DIR)
    )


def _snapshot(folder: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(folder.iterdir()) if p.is_file()}


def _status(data_dir: Path, run_id: int) -> str:
    with get_engine(data_dir).connect() as conn:
        return str(
            conn.execute(select(tables.runs.c.status).where(tables.runs.c.id == run_id)).scalar_one()
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


def test_per_lead_queue_failures_do_not_propagate(
    env: Path, tmp_path: Path, queue_root: Path
) -> None:
    """`sync_queue` reports a lead it could not write inside its report. The hook counts that into
    its log line and returns; it never re-raises and never records a run error."""

    def unplannable(**_kwargs: object) -> object:
        raise RuntimeError("no name fits")

    _ready(env, 1)
    with pytest.MonkeyPatch.context() as patched:
        patched.setattr(queue_module, "plan_lead_names", unplannable)
        summary, output = _run(env, tmp_path / "apps")

    assert summary.fatal is None, summary.fatal
    assert len(summary.tailored) == 1, summary.errors
    assert _status(env, summary.run_id) == "ok"
    assert [note for note in summary.errors if "queue" in note] == []
    assert "1 failed" in _queue_line(output)
    assert _folders(queue_root) == [], "a lead that could not be planned was written anyway"


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
