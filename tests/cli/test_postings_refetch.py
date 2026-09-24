"""`boardwatch postings refetch` — re-read a damaged posting from its own board.

WHAT THESE DEFEND. The job-apps lane overwrote some board postings' `body_text` and `raw_json`
with its own copy (D-500/D-502), and a known posting is never re-read by a subset-detail board
scan. The repair must go through the scan's writer, so each test here fails against a plausible
wrong repair: one that writes the columns by hand (no `revised` version, stale identities), one
that writes without `--apply`, one that writes a `gone` or `unsupported` posting, one that
reopens or re-dates a posting it merely read, and one that races a running `boardwatch run`.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from filelock import FileLock
from sqlalchemy import Engine, func, insert, select
from typer.testing import CliRunner

from boardwatch.cli import postings_cmd
from boardwatch.cli.app import app
from boardwatch.core.models import RawPosting
from boardwatch.core.normalize import content_hash, normalize_title
from boardwatch.core.politeness import Fetcher
from boardwatch.core.posting_identity import IdentityInputs, compute_identities
from boardwatch.core.settings import load_settings
from boardwatch.scan.coordinator import ScanLockHeldError, scan_lease
from boardwatch.store.db import db_revision, ensure_schema, get_engine, schema_revision
from boardwatch.store.identity_queries import write_identities
from boardwatch.store.tables import (
    board_scans,
    companies,
    jobs,
    posting_events,
    posting_identities,
    posting_version_sources,
    posting_versions,
    postings,
    runs,
)

NOW = datetime(2026, 9, 1, 12, 0, 0)
PID = "5219548007"
LANE_BODY = "GRC Engineer. Responsibilities copied by an aggregator, truncated."
LANE_RAW = {"jobapps": {"posting_id": "pst_7b06", "canonical": {"title": "GRC Engineer"}}}
BOARD_BODY = "GRC Engineer\n\nOwn the compliance program. Requires 3+ years of GRC work."
BOARD_RAW = {"id": int(PID), "title": "GRC Engineer", "content": "&lt;p&gt;Own the program"}
BOARD_URL = "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true"


def _board_posting(body: str = BOARD_BODY) -> RawPosting:
    return RawPosting(
        provider_posting_id=PID, title="GRC Engineer",
        url=f"https://job-boards.greenhouse.io/acme/jobs/{PID}",
        locations=["San Mateo, CA"], department="Security", body_text=body, raw_json=BOARD_RAW,
    )


class FakeBoard:
    """A provider WITH `fetch_posting`, answering from a script and recording its calls."""

    name = "greenhouse"
    board_hosts: tuple[str, ...] = ()

    def __init__(self, answer: RawPosting | None) -> None:
        self.answer = answer
        self.calls: list[tuple[str, str]] = []

    def board_url(self, slug: str) -> str:
        return BOARD_URL

    def fetch_board(self, fetcher: Fetcher, request: Any) -> Any:
        raise AssertionError("refetch must never scan the board")

    def healthcheck(self, fetcher: Fetcher, slug: str) -> Any:
        raise AssertionError("refetch must never healthcheck")

    def fetch_posting(
        self, fetcher: Fetcher, slug: str, provider_posting_id: str
    ) -> RawPosting | None:
        self.calls.append((slug, provider_posting_id))
        return self.answer


class NoRefetchBoard:
    """A provider WITHOUT `fetch_posting` — the shape of lever, workable, jibe..."""

    name = "greenhouse"
    board_hosts: tuple[str, ...] = ()

    def board_url(self, slug: str) -> str:
        return BOARD_URL

    def fetch_board(self, fetcher: Fetcher, request: Any) -> Any:
        raise AssertionError("unreachable")

    def healthcheck(self, fetcher: Fetcher, slug: str) -> Any:
        raise AssertionError("unreachable")


def _use(monkeypatch: pytest.MonkeyPatch, provider: object) -> None:
    monkeypatch.setattr(postings_cmd, "build_providers", lambda: {"greenhouse": provider})


def _invoke(data_dir: Path, *args: str):
    return CliRunner().invoke(
        app, ["--data-dir", str(data_dir), "postings", "refetch", *args]
    )


def _base_inputs(posting_id: int, company_id: int) -> dict[str, Any]:
    return dict(
        posting_id=posting_id, company_id=company_id, company_name="Acme",
        provider_posting_id=PID, first_seen_at=NOW,
    )


def _seed(data_dir: Path, *, status: str = "open") -> tuple[Engine, int, int]:
    """A board posting whose body, hash, raw_json AND identities are the lane's."""
    engine = get_engine(data_dir)
    ensure_schema(engine)
    with engine.begin() as conn:
        company_id = int(
            conn.execute(
                insert(companies).values(
                    name="Acme", provider="greenhouse", slug="acme", source="user", watched=True,
                )
            ).inserted_primary_key[0]
        )
        job_id = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
        posting_id = int(
            conn.execute(
                insert(postings).values(
                    company_id=company_id, job_id=job_id, provider_posting_id=PID,
                    title="GRC Engineer", normalized_title=normalize_title("GRC Engineer"),
                    url=f"https://job-boards.greenhouse.io/acme/jobs/{PID}",
                    locations_json=["San Mateo, CA United States"], remote_policy="unknown",
                    first_seen_at=NOW, last_seen_at=NOW, status=status,
                    closed_at=NOW if status == "closed" else None,
                    consecutive_missing=1, death_strikes=1,
                    content_hash=content_hash(LANE_BODY), body_text=LANE_BODY, raw_json=LANE_RAW,
                )
            ).inserted_primary_key[0]
        )
        conn.execute(
            insert(posting_versions).values(
                posting_id=posting_id, content_hash=content_hash(LANE_BODY), body_text=LANE_BODY,
                captured_at=NOW, capture_reason="revised",
            )
        )
        write_identities(
            conn, posting_id,
            compute_identities(
                IdentityInputs(
                    **_base_inputs(posting_id, company_id), title="GRC Engineer",
                    locations=["San Mateo, CA United States"],
                    content_hash=content_hash(LANE_BODY), body_text=LANE_BODY, url="",
                )
            ),
            now=NOW,
        )
    return engine, posting_id, company_id


_WATCHED = (
    postings, posting_versions, posting_version_sources, posting_identities, posting_events,
    board_scans,
)


def _everything(engine: Engine) -> dict[str, list[tuple[Any, ...]]]:
    with engine.connect() as conn:
        return {t.name: [tuple(r) for r in conn.execute(select(t)).all()] for t in _WATCHED}


def _identity_keys(engine: Engine, posting_id: int) -> dict[str, str]:
    with engine.connect() as conn:
        return dict(
            conn.execute(  # type: ignore[arg-type]
                select(posting_identities.c.kind, posting_identities.c.identity_key)
                .where(posting_identities.c.posting_id == posting_id)
            ).all()
        )


def test_apply_revises_through_the_scan_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, posting_id, company_id = _seed(tmp_path)
    board = FakeBoard(_board_posting())
    _use(monkeypatch, board)

    result = _invoke(tmp_path, "--ids", str(posting_id), "--apply")
    assert result.exit_code == 0, result.output
    assert f"{posting_id}\trevised" in result.output
    assert board.calls == [("acme", PID)]

    with engine.connect() as conn:
        row = conn.execute(select(postings).where(postings.c.id == posting_id)).one()
        versions = conn.execute(
            select(posting_versions).where(posting_versions.c.posting_id == posting_id)
            .order_by(posting_versions.c.id)
        ).all()
        sources = conn.execute(select(posting_version_sources)).all()
        scans = conn.execute(select(func.count()).select_from(board_scans)).scalar_one()
        events = conn.execute(select(func.count()).select_from(posting_events)).scalar_one()

    # The version chain: the lane's row is kept, the board's is appended and current.
    assert [v.capture_reason for v in versions] == ["revised", "revised"]
    assert versions[0].body_text == LANE_BODY, "history keeps what was actually quoted"
    assert versions[1].body_text == BOARD_BODY
    assert versions[1].run_id is None, "a refetch has no run"
    assert row.content_hash == content_hash(BOARD_BODY) == versions[1].content_hash
    assert row.body_text == BOARD_BODY
    # D25: raw_json and the provider fields are the board's now.
    assert row.raw_json == BOARD_RAW
    assert row.locations_json == ["San Mateo, CA"]
    assert row.department == "Security"
    # Provenance of the new version, with no run; and no scan row / events invented for one.
    assert [(s.posting_version_id, s.run_id, s.source_url) for s in sources] == [
        (versions[1].id, None, BOARD_URL)
    ]
    assert scans == 0, "a board_scans row would count a one-posting 'scan' in coverage"
    assert events == 0

    # Identity rows recomputed from what the row now holds, not the lane's copy.
    want = {
        i.kind: i.identity_key
        for i in compute_identities(
            IdentityInputs(
                **_base_inputs(posting_id, company_id), title="GRC Engineer",
                locations=["San Mateo, CA"], content_hash=content_hash(BOARD_BODY),
                body_text=BOARD_BODY, url="",
            )
        )
    }
    assert _identity_keys(engine, posting_id) == want


def test_a_refetch_is_not_a_sighting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A closed posting stays closed and its liveness columns stay the scan's: a detail read
    is not a listing, and closing/reopening belongs to the scan and the death probe."""
    engine, posting_id, _ = _seed(tmp_path, status="closed")
    _use(monkeypatch, FakeBoard(_board_posting()))

    result = _invoke(tmp_path, "--ids", str(posting_id), "--apply")
    assert result.exit_code == 0, result.output
    with engine.connect() as conn:
        row = conn.execute(select(postings).where(postings.c.id == posting_id)).one()
    assert row.body_text == BOARD_BODY
    assert (row.status, row.closed_at, row.last_seen_at) == ("closed", NOW, NOW)
    assert (row.consecutive_missing, row.death_strikes) == (1, 1)


def test_same_body_refreshes_raw_json_without_a_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, posting_id, _ = _seed(tmp_path)
    _use(monkeypatch, FakeBoard(_board_posting(body=LANE_BODY)))

    result = _invoke(tmp_path, "--ids", str(posting_id), "--apply")
    assert result.exit_code == 0, result.output
    assert f"{posting_id}\trefreshed" in result.output
    with engine.connect() as conn:
        row = conn.execute(select(postings).where(postings.c.id == posting_id)).one()
        n_versions = conn.execute(
            select(func.count()).select_from(posting_versions)
        ).scalar_one()
    assert row.raw_json == BOARD_RAW
    assert n_versions == 1, "an unchanged body is not a revision"


def test_without_apply_it_reports_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, posting_id, _ = _seed(tmp_path)
    board = FakeBoard(_board_posting())
    _use(monkeypatch, board)
    before = _everything(engine)

    result = _invoke(tmp_path, "--ids", str(posting_id))
    assert result.exit_code == 0, result.output
    assert f"{posting_id}\trevised" in result.output
    assert "would apply" in result.output
    assert board.calls == [("acme", PID)], "the report is built from a real fetch"
    assert _everything(engine) == before


def test_a_posting_the_board_no_longer_lists_is_gone_and_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, posting_id, _ = _seed(tmp_path)
    _use(monkeypatch, FakeBoard(None))
    before = _everything(engine)

    result = _invoke(tmp_path, "--ids", str(posting_id), "--apply")
    assert result.exit_code == 0, result.output
    assert f"{posting_id}\tgone" in result.output
    assert _everything(engine) == before, "gone is a report line; the death probe closes"


def test_a_provider_without_fetch_posting_is_unsupported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, posting_id, _ = _seed(tmp_path)
    _use(monkeypatch, NoRefetchBoard())
    before = _everything(engine)

    result = _invoke(tmp_path, "--ids", str(posting_id), "--apply")
    assert result.exit_code == 0, result.output
    assert f"{posting_id}\tunsupported" in result.output
    assert _everything(engine) == before


def _hold_scan_lock(data_dir: Path) -> FileLock:
    """What a launchd `boardwatch run` holds for its whole run (T133)."""
    holder = FileLock(str(data_dir / "scan.lock"))
    holder.acquire()
    return holder


def test_a_held_scan_lease_is_refused_before_any_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The exclusion is the scan lease, not the `runs` row: a run that holds `scan.lock` with no
    `running` row yet (it takes the lease before its runs insert) still refuses the repair."""
    engine, posting_id, _ = _seed(tmp_path)
    board = FakeBoard(_board_posting())
    _use(monkeypatch, board)
    before = _everything(engine)

    holder = _hold_scan_lock(tmp_path)
    try:
        result = _invoke(tmp_path, "--ids", str(posting_id), "--apply")
    finally:
        holder.release()
    assert result.exit_code == 2, result.output
    assert "refetch refused" in result.output
    assert board.calls == [], "refused, not waited on and not half-run"
    assert _everything(engine) == before


def test_a_stale_running_row_alone_is_advisory_and_the_refetch_proceeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A killed run leaves its row `running` until a reap (run 473, 24h on 2026-09-23). With
    nobody holding the lease that row is not a run in progress, so it must not refuse."""
    engine, posting_id, _ = _seed(tmp_path)
    with engine.begin() as conn:
        run_id = conn.execute(
            insert(runs).values(started_at=NOW, boards_attempted=0, status="running")
        ).inserted_primary_key[0]
    board = FakeBoard(_board_posting())
    _use(monkeypatch, board)

    result = _invoke(tmp_path, "--ids", str(posting_id), "--apply")
    assert result.exit_code == 0, result.output
    assert f"run {run_id} is marked running in the runs table" in result.output
    assert f"{posting_id}\trevised" in result.output
    assert board.calls == [("acme", PID)]


def test_apply_holds_the_scan_lease_for_the_whole_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run starting mid-loop must be the one refused: from inside the fetch, a concurrent
    `scan_lease` caller finds the lease held."""
    _, posting_id, _ = _seed(tmp_path)
    settings = load_settings(data_dir=tmp_path)
    seen: list[str] = []

    class ProbingBoard(FakeBoard):
        def fetch_posting(
            self, fetcher: Fetcher, slug: str, provider_posting_id: str
        ) -> RawPosting | None:
            try:
                with scan_lease(settings):
                    seen.append("acquired")
            except ScanLockHeldError:
                seen.append("held")
            return super().fetch_posting(fetcher, slug, provider_posting_id)

    _use(monkeypatch, ProbingBoard(_board_posting()))
    result = _invoke(tmp_path, "--ids", str(posting_id), "--apply")
    assert result.exit_code == 0, result.output
    assert seen == ["held"]
    with scan_lease(settings):  # released when the command ends
        pass


def test_report_only_takes_no_lease(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Without `--apply` nothing is written, so a running pipeline does not refuse the report."""
    _, posting_id, _ = _seed(tmp_path)
    _use(monkeypatch, FakeBoard(_board_posting()))
    holder = _hold_scan_lock(tmp_path)
    try:
        result = _invoke(tmp_path, "--ids", str(posting_id))
    finally:
        holder.release()
    assert result.exit_code == 0, result.output
    assert f"{posting_id}\trevised" in result.output


def test_refused_is_classified_by_type(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The refusal maps `ScanLockHeldError` itself, whatever its message says."""
    _, posting_id, _ = _seed(tmp_path)
    board = FakeBoard(_board_posting())
    _use(monkeypatch, board)

    @contextmanager
    def held(_settings: object) -> Iterator[None]:
        raise ScanLockHeldError("")
        yield

    monkeypatch.setattr(postings_cmd, "scan_lease", held)
    result = _invoke(tmp_path, "--ids", str(posting_id), "--apply")
    assert result.exit_code == 2, result.output
    assert board.calls == []


def test_ids_file_and_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, posting_id, _ = _seed(tmp_path)
    board = FakeBoard(None)
    _use(monkeypatch, board)
    ids_file = tmp_path / "ids.txt"
    ids_file.write_text(f"{posting_id}\n999999\n")

    result = _invoke(tmp_path, "--ids-file", str(ids_file), "--limit", "1")
    assert result.exit_code == 0, result.output
    assert "999999" not in result.output
    assert board.calls == [("acme", PID)]

    missing = _invoke(tmp_path, "--ids", "999999")
    assert "999999\tfailed\tno such posting" in missing.output


def test_without_apply_the_store_is_not_migrated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Report-only never runs the schema migration: `build_context(ensure=True)` would migrate a
    behind-schema store before the command reported anything (Codex on T210)."""
    from boardwatch.cli import context as cli_context

    engine, posting_id, _ = _seed(tmp_path)
    _use(monkeypatch, FakeBoard(_board_posting()))

    def refuse(_engine: object) -> None:
        raise AssertionError("ensure_schema ran on a report-only refetch")

    monkeypatch.setattr(cli_context, "ensure_schema", refuse)
    before = _everything(engine)
    result = _invoke(tmp_path, "--ids", str(posting_id))
    assert result.exit_code == 0, result.output
    assert "revised" in result.output
    assert _everything(engine) == before


def _one_migration_behind(engine: Engine) -> str:
    """Downgrade a migrated store one real step: behind-schema with no hardcoded revision, so a
    new head moves this fixture with it."""
    from alembic import command

    from boardwatch.store.db import _alembic_config

    command.downgrade(_alembic_config(engine), "-1")
    with engine.connect() as conn:
        behind = db_revision(conn)
    assert behind is not None and behind != schema_revision()
    return behind


def test_a_refused_apply_does_not_migrate_the_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The lease is taken BEFORE the schema ensure, as `scan` and `run` order it: a contended
    `--apply` is refused against the store exactly as it found it, not after an alembic upgrade
    that the running pipeline never agreed to (Codex on T222)."""
    engine, posting_id, _ = _seed(tmp_path)
    behind = _one_migration_behind(engine)
    board = FakeBoard(_board_posting())
    _use(monkeypatch, board)

    holder = _hold_scan_lock(tmp_path)
    try:
        result = _invoke(tmp_path, "--ids", str(posting_id), "--apply")
    finally:
        holder.release()
    assert result.exit_code == 2, result.output
    assert board.calls == []
    with engine.connect() as conn:
        assert db_revision(conn) == behind, "a refused refetch migrated the store"


def test_an_uncontended_apply_migrates_then_proceeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CONTROL: with nobody holding the lease, `--apply` is a write and takes the migration."""
    engine, posting_id, _ = _seed(tmp_path)
    _one_migration_behind(engine)
    _use(monkeypatch, FakeBoard(_board_posting()))

    result = _invoke(tmp_path, "--ids", str(posting_id), "--apply")
    assert result.exit_code == 0, result.output
    assert f"{posting_id}\trevised" in result.output
    with engine.connect() as conn:
        assert db_revision(conn) == schema_revision()
