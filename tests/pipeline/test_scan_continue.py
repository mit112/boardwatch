"""T353: `run --continue-scan` continues a killed pipeline scan from the boards it committed.

The scan runs in a SUBPROCESS that is SIGKILLed (a) inside board 3's apply transaction, right
before it commits, and (b) right after that commit. Then it is continued in this process. The
control is one uninterrupted scan on a clone of the same starting store, and the null control is
today's retry (a fresh run, no flag) on a clone of the same killed store: it charges the sentinel
a second miss and closes it, which is what makes the main assertions discriminate.

Six boards on three hosts (two each on Greenhouse, Lever and Ashby), one worker, so the order is
fixed: the two Greenhouse boards apply first. `gh-a` drops the sentinel posting tonight; it
completes before either kill, so its absence is counted before the kill and must not be counted
again.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
from collections import Counter
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from rich.console import Console
from sqlalchemy import func, insert, inspect, select, update

from boardwatch.core.clock import utcnow
from boardwatch.core.settings import Settings, load_settings
from boardwatch.pipeline.runner import run_pipeline
from boardwatch.providers.registry import build_providers
from boardwatch.scan import apply as apply_module
from boardwatch.scan import coordinator
from boardwatch.scan import resume as resume_module
from boardwatch.scan.coordinator import run_scan
from boardwatch.scan.resume import ScanResumeRefusedError
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="SIGKILL is POSIX-only")

REPO = Path(__file__).resolve().parents[2]
_PROVIDERS = build_providers()
BOARDS = (
    ("gh-a", "greenhouse"), ("gh-b", "greenhouse"),
    ("lv-a", "lever"), ("lv-b", "lever"),
    ("ab-a", "ashby"), ("ab-b", "ashby"),
)
SENTINEL = "sentinel"
#: A line the killed attempt's listing gate wrote to its audit file. None of these three providers
#: gates, so it is planted after the kill.
AUDIT_LINE = '{"provider": "smartrecruiters", "slug": "killed-attempt"}'


def _job(provider: str, posting_id: str) -> dict[str, Any]:
    title = f"Backend Engineer {posting_id}"
    if provider == "lever":
        return {"id": posting_id, "text": title, "hostedUrl": f"https://example.test/{posting_id}",
                "descriptionPlain": "Python services."}
    return {"id": posting_id, "title": title, "absolute_url": f"https://example.test/{posting_id}",
            "jobUrl": f"https://example.test/{posting_id}", "content": "Python services.",
            "descriptionHtml": "<p>Python services.</p>"}


def _body(provider: str, ids: list[str]) -> bytes:
    jobs = [_job(provider, i) for i in ids]
    return json.dumps(jobs if provider == "lever" else {"jobs": jobs}).encode()


def _listing(slug: str, *, night: bool) -> list[str]:
    """Two postings per board. Tonight `gh-a` drops the sentinel and gains one, and `ab-b` gains
    one: a new posting on each side of the kill."""
    ids = [f"{slug}-1", f"{slug}-2"]
    if slug == "gh-a" and not night:
        ids.append(SENTINEL)
    if slug in ("gh-a", "ab-b") and night:
        ids.append(f"{slug}-3")
    return ids


#: Tonight this board answers 500, before either kill, so a settled `failed` board is carried.
FAILING = "gh-b"


def _settings(data_dir: Path) -> Settings:
    # The gate armed, so its key is a real digest and a profile edit can change it.
    return load_settings(data_dir=data_dir).model_copy(
        update={"scan_workers": 1, "listing_gate": True}
    )


@contextmanager
def _routes(night: bool, log: Path | None = None) -> Iterator[dict[str, respx.Route]]:
    """One route per board; `log` gets one line per request, flushed, so a SIGKILL keeps it."""
    def recorder(slug: str, content: bytes) -> Callable[[httpx.Request], httpx.Response]:
        def respond(request: httpx.Request) -> httpx.Response:
            if log is not None:
                with log.open("a") as handle:
                    handle.write(slug + "\n")
            if night and slug == FAILING:
                return httpx.Response(500)
            return httpx.Response(200, content=content)
        return respond

    with respx.mock(assert_all_called=False) as mock:
        yield {
            slug: mock.get(_PROVIDERS[provider].board_url(slug)).mock(
                side_effect=recorder(slug, _body(provider, _listing(slug, night=night)))
            )
            for slug, provider in BOARDS
        }


def _seed(data_dir: Path) -> None:
    """Six watched boards and a profile, then one finished scan that lists the sentinel."""
    engine = get_engine(data_dir)
    ensure_schema(engine)
    with engine.begin() as conn:
        for slug, provider in BOARDS:
            conn.execute(insert(tables.companies).values(
                name=slug, provider=provider, slug=slug, source="user", watched=True
            ))
        conn.execute(insert(tables.profile).values(
            text="Backend engineer.", exclude_titles_json=["staff"], updated_at=utcnow()
        ))
    with _routes(night=False):
        assert run_scan(engine, _settings(data_dir)).complete == len(BOARDS)
    engine.dispose()


def _clone(src: Path, dst: Path) -> Path:
    """A copy-on-write clone on APFS, so control and subject start from the same bytes."""
    if sys.platform == "darwin":
        subprocess.run(["cp", "-c", "-R", str(src), str(dst)], check=True)
    else:
        shutil.copytree(src, dst)
    return dst


def _child(data_dir: str, kill_point: str, log: str) -> None:
    """The subprocess: tonight's pipeline scan, SIGKILLed around board 3's commit."""
    import time

    time.sleep = lambda seconds: None  # pacing is not this test's subject
    applied = 0
    if kill_point == "before":
        real_row = apply_module._scan_row

        def row_then_die(*args: Any, **kwargs: Any) -> None:
            nonlocal applied
            real_row(*args, **kwargs)
            applied += 1
            if applied == 3:  # the board's last write, inside its uncommitted transaction
                os.kill(os.getpid(), signal.SIGKILL)

        apply_module._scan_row = row_then_die  # type: ignore[assignment]
    else:
        real_apply = coordinator.apply_board

        def apply_then_die(*args: Any, **kwargs: Any) -> Any:
            nonlocal applied
            result = real_apply(*args, **kwargs)
            applied += 1
            if applied == 3:  # committed
                os.kill(os.getpid(), signal.SIGKILL)
            return result

        coordinator.apply_board = apply_then_die  # type: ignore[assignment]
    path = Path(data_dir)
    with _routes(night=True, log=Path(log)):
        run_scan(get_engine(path), _settings(path), finish=False)
    raise SystemExit("the scan finished: the kill hook never fired")


def _kill(data_dir: Path, kill_point: str, log: Path) -> Counter[str]:
    proc = subprocess.run(
        [sys.executable, "-c",
         "from tests.pipeline.test_scan_continue import _child; "
         f"_child({str(data_dir)!r}, {kill_point!r}, {str(log)!r})"],
        cwd=REPO, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == -signal.SIGKILL, proc.stderr
    return Counter(log.read_text().split()) if log.exists() else Counter()


def _scan(data_dir: Path, *, continue_scan: bool = False) -> Counter[str]:
    engine = get_engine(data_dir)
    with _routes(night=True) as routes:
        run_scan(engine, _settings(data_dir), finish=False, continue_scan=continue_scan)
    engine.dispose()
    return Counter({slug: route.call_count for slug, route in routes.items()})


def _state(data_dir: Path) -> dict[str, Any]:
    """What the acceptance compares: posting ids and their fate, and the event multiset."""
    engine = get_engine(data_dir)
    with engine.connect() as conn:
        posting_rows = conn.execute(
            select(tables.postings.c.provider_posting_id, tables.postings.c.status,
                   tables.postings.c.consecutive_missing)
        ).all()
        events = conn.execute(
            select(tables.posting_events.c.kind, tables.postings.c.provider_posting_id,
                   tables.posting_events.c.run_id)
            .join(tables.postings, tables.postings.c.id == tables.posting_events.c.posting_id)
        ).all()
        runs = conn.execute(select(tables.runs.c.id)).scalars().all()
        scans = conn.execute(
            select(tables.board_scans.c.run_id, tables.board_scans.c.company_id)
        ).all()
    engine.dispose()
    return {
        "postings": {r.provider_posting_id: (r.status, r.consecutive_missing)
                     for r in posting_rows},
        "events": Counter(tuple(e) for e in events),
        "runs": sorted(runs),
        "scans": Counter(tuple(s) for s in scans),
    }


def _settled(data_dir: Path, run_id: int) -> set[str]:
    engine = get_engine(data_dir)
    with engine.connect() as conn:
        slugs = set(conn.execute(
            select(tables.companies.c.slug)
            .join(tables.board_scans, tables.board_scans.c.company_id == tables.companies.c.id)
            .where(tables.board_scans.c.run_id == run_id)
        ).scalars())
    engine.dispose()
    return slugs


@pytest.mark.usefixtures("no_real_sleep")
@pytest.mark.parametrize(("kill_point", "settled"), [
    ("before", {"gh-a", "gh-b"}),
    ("after", {"gh-a", "gh-b", "lv-a"}),
])
def test_a_continued_scan_matches_an_uninterrupted_one(
    tmp_path: Path, kill_point: str, settled: set[str]
) -> None:
    start = tmp_path / "start"
    _seed(start)
    control = _scan(_clone(start, tmp_path / "control"))
    expected = _state(tmp_path / "control")
    night_run = max(expected["runs"])

    killed = _clone(start, tmp_path / "killed")
    child = _kill(killed, kill_point, tmp_path / "child.log")
    assert _settled(killed, night_run) == settled
    (killed / "listing_gated.jsonl").write_text(AUDIT_LINE + "\n")
    null = _clone(killed, tmp_path / "null")

    resumed = _scan(killed, continue_scan=True)
    got = _state(killed)

    for slug, _ in BOARDS:
        if slug in settled:
            assert resumed[slug] == 0, slug  # a settled board is never asked again
            assert child[slug] == control[slug], slug
        else:
            assert resumed[slug] == control[slug], slug
    assert got["postings"] == expected["postings"]
    assert got["events"] == expected["events"]
    assert got["runs"] == expected["runs"]  # one logical scan, under the original id
    assert got["scans"] == expected["scans"]  # one board_scans row per (run, board)
    assert got["postings"][SENTINEL] == ("open", 1)
    # The gate's trace is appended to, so the killed attempt's lines stay readable.
    assert AUDIT_LINE in (killed / "listing_gated.jsonl").read_text().splitlines()

    # Null control: today's retry over the same kill charges the second miss and closes it.
    _scan(null)
    assert _state(null)["postings"][SENTINEL] == ("closed", 2)
    assert AUDIT_LINE not in (null / "listing_gated.jsonl").read_text()


@pytest.mark.usefixtures("no_real_sleep")
def test_the_continued_run_reports_the_whole_scan_and_keeps_the_kill_on_record(
    tmp_path: Path,
) -> None:
    data = tmp_path / "data"
    _seed(data)
    _kill(data, "after", tmp_path / "child.log")
    engine = get_engine(data)
    with _routes(night=True):
        summary = run_scan(engine, _settings(data), finish=False, continue_scan=True)
    with engine.connect() as conn:
        row = conn.execute(select(tables.runs).where(tables.runs.c.id == summary.run_id)).one()
        finalized = conn.execute(
            select(tables.scan_manifests.c.scan_finalized_at)
            .where(tables.scan_manifests.c.run_id == summary.run_id)
        ).scalar_one()
    assert (row.boards_attempted, row.boards_complete, row.boards_failed) == (len(BOARDS), 5, 1)
    # gh-a's new posting (before the kill) and ab-b's (after it); nothing closes.
    assert (row.new_count, row.closed_count) == (2, 0)
    assert any(note.startswith(f"{FAILING}: ") for note in row.errors_json)
    assert row.status == "running"  # the pipeline owns the terminal status
    assert row.finished_at is None
    assert any(note.startswith("scan: resumed at ") for note in row.errors_json)
    assert finalized is not None
    with pytest.raises(ScanResumeRefusedError, match="finished"):
        run_scan(engine, _settings(data), finish=False, continue_scan=True)


def _dump(data_dir: Path) -> dict[str, list[tuple[Any, ...]]]:
    engine = get_engine(data_dir)
    with engine.connect() as conn:
        dump = {
            name: sorted(map(tuple, conn.execute(select(table)).all()), key=repr)
            for name, table in sorted(tables.metadata.tables.items())
        }
    engine.dispose()
    return dump


@pytest.mark.usefixtures("no_real_sleep")
@pytest.mark.parametrize(("edit", "field"), [
    ("profile", "listing_gate_key"),
    ("watch", "boards"),
    ("slug", "boards"),  # edited in place: the id stays, the listing it reads does not
])
def test_a_changed_manifest_field_refuses_and_writes_nothing(
    tmp_path: Path, edit: str, field: str
) -> None:
    data = tmp_path / "data"
    _seed(data)
    _kill(data, "after", tmp_path / "child.log")
    engine = get_engine(data)
    with engine.begin() as conn:
        if edit == "profile":
            conn.execute(update(tables.profile).values(exclude_titles_json=["staff", "intern"]))
        elif edit == "watch":
            conn.execute(update(tables.companies).where(tables.companies.c.slug == "ab-b")
                         .values(watched=False))
        else:
            conn.execute(update(tables.companies).where(tables.companies.c.slug == "ab-b")
                         .values(slug="ab-b-narrower"))
    before = _dump(data)
    with _routes(night=True) as routes, pytest.raises(ScanResumeRefusedError) as refusal:
        run_scan(engine, _settings(data), finish=False, continue_scan=True)
    assert refusal.value.field == field
    assert field in str(refusal.value)
    assert not any(route.called for route in routes.values())
    assert _dump(data) == before


@pytest.mark.usefixtures("no_real_sleep")
def test_a_setting_in_the_manifest_refuses_by_its_name(tmp_path: Path) -> None:
    data = tmp_path / "data"
    _seed(data)
    _kill(data, "after", tmp_path / "child.log")
    changed = _settings(data).model_copy(update={"detail_fetch_budget": 7})
    with _routes(night=True), pytest.raises(ScanResumeRefusedError) as refusal:
        run_scan(get_engine(data), changed, finish=False, continue_scan=True)
    assert refusal.value.field == "detail_fetch_budget"


def _refusal(data: Path) -> str:
    with _routes(night=True), pytest.raises(ScanResumeRefusedError) as refusal:
        run_scan(get_engine(data), _settings(data), finish=False, continue_scan=True)
    assert refusal.value.field is None
    return str(refusal.value)


@pytest.mark.usefixtures("no_real_sleep")
def test_only_the_newest_scan_unfinished_recent_and_from_a_pipeline_is_continued(
    tmp_path: Path,
) -> None:
    empty = tmp_path / "empty"
    ensure_schema(get_engine(empty))
    assert "no scan has a manifest" in _refusal(empty)

    seeded = tmp_path / "seeded"
    _seed(seeded)  # its only scan is a finished standalone one
    assert "finished" in _refusal(seeded)

    killed = tmp_path / "killed"
    _seed(killed)
    _kill(killed, "after", tmp_path / "child.log")

    stale = _clone(killed, tmp_path / "stale")
    with get_engine(stale).begin() as conn:
        newest = conn.execute(select(func.max(tables.runs.c.id))).scalar_one()
        conn.execute(update(tables.runs).where(tables.runs.c.id == newest)
                     .values(started_at=utcnow() - timedelta(hours=13)))
    assert "more than 12 h ago" in _refusal(stale)

    # A fresh scan after the kill has read every board: the killed run behind it stays closed.
    overtaken = _clone(killed, tmp_path / "overtaken")
    _scan(overtaken)
    assert "finished" in _refusal(overtaken)

    # A standalone scan writes no pipeline board scan, so it is never continued.
    standalone = tmp_path / "standalone"
    _seed(standalone)
    with get_engine(standalone).begin() as conn:
        conn.execute(update(tables.scan_manifests).values(scan_finalized_at=None))
    assert "no pipeline board scan" in _refusal(standalone)


@pytest.mark.usefixtures("no_real_sleep")
def test_a_scan_code_change_refuses_by_its_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = tmp_path / "data"
    _seed(data)
    _kill(data, "after", tmp_path / "child.log")
    monkeypatch.setattr(resume_module, "scan_code_digest", lambda: "a different scan")
    with _routes(night=True), pytest.raises(ScanResumeRefusedError) as refusal:
        run_scan(get_engine(data), _settings(data), finish=False, continue_scan=True)
    assert refusal.value.field == "scan_code"


def test_the_scan_code_digest_covers_the_scan_the_providers_and_the_pacing() -> None:
    names = {path.relative_to(REPO / "src" / "boardwatch").as_posix()
             for path in resume_module._scan_sources()}
    expected = {f"scan/{p.name}" for p in (REPO / "src/boardwatch/scan").glob("*.py")}
    for package in ("providers", "rank"):
        expected |= {f"{package}/{p.name}" for p in (REPO / f"src/boardwatch/{package}").glob("*.py")}
    assert names == expected | {"core/politeness.py"}
    assert {"scan/coordinator.py", "scan/apply.py", "providers/workday.py",
            "rank/listing_gate.py", "rank/heuristic.py"} <= names


def test_a_store_the_migrations_have_not_reached_refuses_unmigrated(tmp_path: Path) -> None:
    """`ensure_schema` would migrate it; a refused resume writes nothing, a migration included."""
    from alembic import command
    from alembic.config import Config

    from boardwatch.store.db import DB_FILENAME

    data = tmp_path / "data"
    data.mkdir()
    cfg = Config()
    cfg.set_main_option("script_location", str(REPO / "src/boardwatch/store/migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{data / DB_FILENAME}")
    command.upgrade(cfg, "p_head_shadow")
    with pytest.raises(ScanResumeRefusedError, match="schema p_head_shadow"):
        run_scan(get_engine(data), _settings(data), finish=False, continue_scan=True)
    engine = get_engine(data)
    with engine.connect() as conn:
        assert "scan_manifests" not in inspect(conn).get_table_names()
    engine.dispose()

    missing = tmp_path / "missing"
    with pytest.raises(ScanResumeRefusedError, match="no store"):
        run_scan(get_engine(missing), _settings(missing), finish=False, continue_scan=True)


@pytest.mark.usefixtures("no_real_sleep")
def test_the_pipeline_continues_an_aborted_scan_under_its_run_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ctrl-C on the second board: the abort handler closes the run `failed`. `run
    --continue-scan` reopens it, reads only the unsettled board and finishes it as one run."""
    from tests.pipeline.test_pipeline_run import SEEDED_BOARDS, _ready  # not in `_child`

    data = tmp_path / "data"
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    _ready(data)
    settings = load_settings(data_dir=data).model_copy(update={"scan_workers": 1})
    engine = get_engine(data)

    real_apply = coordinator.apply_board
    calls = 0

    def interrupt_second(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt
        return real_apply(*args, **kwargs)

    gh = _PROVIDERS["greenhouse"]
    body = _body("greenhouse", ["acme-job"])

    def pipeline(**kw: Any) -> Any:
        return run_pipeline(engine, settings, console=Console(quiet=True),
                            out_root=tmp_path / "apps",
                            resume_path=settings.config_dir / "resume.yaml", **kw)

    monkeypatch.setattr(coordinator, "apply_board", interrupt_second)
    with respx.mock, pytest.raises(KeyboardInterrupt):
        for slug in SEEDED_BOARDS:
            respx.get(gh.board_url(slug)).mock(return_value=httpx.Response(200, content=body))
        pipeline()
    monkeypatch.setattr(coordinator, "apply_board", real_apply)
    with engine.connect() as conn:
        aborted = conn.execute(select(tables.runs).order_by(tables.runs.c.id.desc())).first()
    assert aborted is not None and aborted.status == "failed"
    (settled,) = _settled(data, aborted.id)
    (unsettled,) = set(SEEDED_BOARDS) - {settled}

    with respx.mock:
        routes = {slug: respx.get(gh.board_url(slug)).mock(
            return_value=httpx.Response(200, content=body)) for slug in SEEDED_BOARDS}
        summary = pipeline(continue_scan=True)

    assert summary.run_id == aborted.id
    assert routes[settled].call_count == 0
    assert routes[unsettled].call_count == 1
    with engine.connect() as conn:
        row = conn.execute(select(tables.runs).where(tables.runs.c.id == aborted.id)).one()
        count = conn.execute(select(func.count()).select_from(tables.runs)
                             .where(tables.runs.c.id > aborted.id)).scalar_one()
    assert count == 0  # no second run row for the night
    assert row.status == "ok" and row.finished_at is not None
    assert row.boards_attempted == 2
    assert "scan: aborted: KeyboardInterrupt()" in row.errors_json
    assert any(note.startswith("scan: resumed at ") for note in row.errors_json)


def test_the_cli_refuses_with_exit_2_and_rejects_no_scan(tmp_path: Path) -> None:
    from tests.pipeline.test_pipeline_run import _cli

    data = tmp_path / "data"
    engine = get_engine(data)
    ensure_schema(engine)
    # A row the stale-run reap would close: a refused resume writes nothing, so it stays open.
    with engine.begin() as conn:
        conn.execute(insert(tables.runs).values(
            started_at=utcnow() - timedelta(hours=30), boards_attempted=0
        ))
    before = _dump(data)
    queue = ["--queue-root", str(tmp_path / "queue")]
    refused = _cli(data, ["run", "--continue-scan", *queue])
    assert refused.exit_code == 2, refused.output
    assert "--continue-scan refused: no scan has a manifest" in refused.output
    assert _dump(data) == before
    clash = _cli(data, ["run", "--continue-scan", "--no-scan", *queue])
    assert clash.exit_code == 2
    assert "--no-scan" in clash.output
