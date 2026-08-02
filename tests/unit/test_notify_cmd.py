"""notify command: three-phase read / deliver / advance cursor semantics.

Delivery is hermetic — the real WebhookChannel is exercised end to end, but
httpx.Client is monkeypatched to a MockTransport so no socket is ever opened.
This keeps _build_channels, resolve_secret, build_payload and deliver on the real
path; only the wire is faked (see task-7 report for the injection rationale)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy import insert
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.store.app_state import get_notify_cursor
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.events import append_event
from boardwatch.store.queries import insert_run, save_profile
from boardwatch.store.tables import companies, jobs, posting_versions, postings

runner = CliRunner()
NOW = datetime(2026, 7, 30, 12, 0, 0)
WEBHOOK_URL = "https://hooks.example.test/T000/B000/xxxx"


@dataclass(frozen=True)
class Env:
    data_dir: Path
    config_dir: Path


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    cfg = tmp_path / "cfg"
    cfg.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(cfg))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("BOARDWATCH_NOTIFY_WEBHOOK_URL", raising=False)
    return Env(data_dir=tmp_path / "data", config_dir=cfg)


def _run(env: Env, args: list[str]):
    return runner.invoke(app, ["--data-dir", str(env.data_dir), *args])


def _cursor(env: Env) -> int:
    with get_engine(env.data_dir).connect() as conn:
        return get_notify_cursor(conn)


def _enable(env: Env, *, webhook: bool = False, desktop: bool = False) -> None:
    lines = ["[notify]"]
    if webhook:
        lines.append("webhook_enabled = true")
    if desktop:
        lines.append("desktop_enabled = true")
    (env.config_dir / "config.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _seed_profile(
    env: Env, *, exclude_titles: tuple[str, ...] = ()
) -> None:
    engine = get_engine(env.data_dir)
    ensure_schema(engine)
    with engine.begin() as conn:
        save_profile(
            conn, text="Backend engineer.", target_titles=[],
            exclude_titles=list(exclude_titles), locations=[], remote_only=False,
            skills=[], taxonomy_version="t",
        )


def _seed_posting(env: Env, *, title: str, slug: str, kind: str = "new") -> int:
    """Insert one company+job+posting+version+event; return the event id."""
    engine = get_engine(env.data_dir)
    run_id = insert_run(engine)
    with engine.begin() as conn:
        company_id = int(
            conn.execute(
                insert(companies).values(
                    name=slug, provider="greenhouse", slug=slug, source="user", watched=True,
                )
            ).inserted_primary_key[0]
        )
        job_id = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
        posting_id = int(
            conn.execute(
                insert(postings).values(
                    company_id=company_id, job_id=job_id, provider_posting_id=f"pp-{slug}",
                    title=title, normalized_title=title.lower(),
                    url=f"https://example.test/{slug}",
                    locations_json=["Remote"], remote_policy="remote",
                    posted_at=NOW, first_seen_at=NOW, last_seen_at=NOW,
                    status="open", consecutive_missing=0, content_hash=f"h-{slug}",
                    body_text="We are hiring.",
                )
            ).inserted_primary_key[0]
        )
        conn.execute(
            insert(posting_versions).values(
                posting_id=posting_id, content_hash=f"h-{slug}", body_text="We are hiring.",
                captured_at=NOW, capture_reason="new",
            )
        )
        return append_event(conn, posting_id, kind, run_id)


class _Recorder:
    def __init__(self) -> None:
        self.count = 0


def _patch_webhook(monkeypatch: pytest.MonkeyPatch, status: int) -> _Recorder:
    """Fake the wire under WebhookChannel.deliver: real code path, MockTransport socket."""
    recorder = _Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        recorder.count += 1
        return httpx.Response(status, json={})

    transport = httpx.MockTransport(handler)
    orig_client = httpx.Client

    def make_client(*args: object, **kwargs: object) -> httpx.Client:
        return orig_client(transport=transport)

    monkeypatch.setattr("boardwatch.notify.webhook.httpx.Client", make_client)
    return recorder


def test_notify_advances_cursor_on_delivery(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_profile(env)
    event_id = _seed_posting(env, title="Backend Engineer", slug="a")
    _enable(env, webhook=True)
    monkeypatch.setenv("BOARDWATCH_NOTIFY_WEBHOOK_URL", WEBHOOK_URL)
    recorder = _patch_webhook(monkeypatch, 200)
    result = _run(env, ["notify"])
    assert result.exit_code == 0, result.stdout
    assert "webhook" in result.stdout
    assert recorder.count == 1
    assert _cursor(env) == event_id


def test_notify_does_not_advance_on_total_failure(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_profile(env)
    _seed_posting(env, title="Backend Engineer", slug="a")
    _enable(env, webhook=True)
    monkeypatch.setenv("BOARDWATCH_NOTIFY_WEBHOOK_URL", WEBHOOK_URL)
    _patch_webhook(monkeypatch, 500)
    result = _run(env, ["notify"])
    assert result.exit_code == 0
    assert _cursor(env) == 0  # nothing delivered -> retried next run


def test_notify_dry_run_never_advances_and_no_post(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_profile(env)
    _seed_posting(env, title="Backend Engineer", slug="a")
    _enable(env, webhook=True)
    monkeypatch.setenv("BOARDWATCH_NOTIFY_WEBHOOK_URL", WEBHOOK_URL)
    recorder = _patch_webhook(monkeypatch, 200)
    result = _run(env, ["notify", "--dry-run"])
    assert result.exit_code == 0
    assert "dry run" in result.stdout
    assert recorder.count == 0
    assert _cursor(env) == 0


def test_notify_nonmatching_events_advance_cursor(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_profile(env, exclude_titles=("Sales",))
    event_id = _seed_posting(env, title="Sales Lead", slug="sales")
    _enable(env, webhook=True)
    monkeypatch.setenv("BOARDWATCH_NOTIFY_WEBHOOK_URL", WEBHOOK_URL)
    recorder = _patch_webhook(monkeypatch, 200)
    result = _run(env, ["notify"])
    assert result.exit_code == 0
    assert "no new matches" in result.stdout
    assert recorder.count == 0  # nothing matched -> nothing sent
    assert _cursor(env) == event_id  # but marked seen, not re-scanned


def test_notify_no_channels_enabled_hint(env: Env) -> None:
    _seed_profile(env)
    _seed_posting(env, title="Backend Engineer", slug="a")
    result = _run(env, ["notify"])  # both flags default false
    assert result.exit_code == 0
    assert "config set notify" in result.stdout
    assert _cursor(env) == 0  # matches undelivered -> NOT advanced


def test_notify_no_profile_exits_1(env: Env) -> None:
    engine = get_engine(env.data_dir)
    ensure_schema(engine)  # schema exists, but no profile row
    result = _run(env, ["notify"])
    assert result.exit_code == 1
    assert "init" in result.stdout


def test_notify_no_events_at_all(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_profile(env)
    _enable(env, webhook=True)
    monkeypatch.setenv("BOARDWATCH_NOTIFY_WEBHOOK_URL", WEBHOOK_URL)
    recorder = _patch_webhook(monkeypatch, 200)
    result = _run(env, ["notify"])
    assert result.exit_code == 0
    assert "no new matches" in result.stdout
    assert recorder.count == 0
    assert _cursor(env) == 0
