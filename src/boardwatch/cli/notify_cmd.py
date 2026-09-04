"""boardwatch notify (P5): push NEW matching postings to enabled channels.

Sibling of `digest`, but it does network I/O, so it must NEVER hold the SQLite write lock
across delivery. Three phases: (1) READ matches on a short plain connection; (2) DELIVER with
NO transaction open (a slow webhook can't block a concurrent scan/digest); (3) ADVANCE the
cursor under a tiny own IMMEDIATE transaction. The cursor advances to max_event_id when at least one
channel delivered OR when there were new events but no matches (mark them seen so they are not
re-scanned forever). It does NOT advance when matches exist but went undelivered (no channels /
all failed), so the next run retries. No --peek (a deliver-but-don't-advance mode re-delivers
on every run — a footgun); --dry-run renders without sending or advancing. Exactly-once is not
achievable (a crash after a POST but before the advance re-notifies next run) — same honest
caveat `digest`/`app_state` document."""

from __future__ import annotations

import typer
from rich.console import Console
from sqlalchemy import Engine

from boardwatch.cli.context import build_context
from boardwatch.core.settings import Settings
from boardwatch.notify.channel import Channel
from boardwatch.notify.desktop import DesktopChannel
from boardwatch.notify.dispatch import dispatch
from boardwatch.notify.webhook import WebhookChannel, build_payload
from boardwatch.rank.heuristic import profile_view_from_row
from boardwatch.reports.notify import NotifyResult, select_new_matches
from boardwatch.store.app_state import get_notify_cursor, set_notify_cursor
from boardwatch.store.db import write_connection
from boardwatch.store.queries import get_profile

console = Console()


def _render(result: NotifyResult) -> None:
    console.print(f"{len(result.items)} new match(es):")
    for i in result.items:
        line = f"  #{i.posting_id} {i.title} — {i.company} ({i.score:.2f})"
        console.print(line + (f" {i.url}" if i.url else ""))


def _build_channels(settings: Settings, result: NotifyResult) -> list[Channel]:
    channels: list[Channel] = []
    if settings.notify.webhook_enabled:
        payload = build_payload(result.items, result.since_event_id, result.max_event_id)
        channels.append(WebhookChannel(payload=payload))
    if settings.notify.desktop_enabled:
        channels.append(DesktopChannel())
    return channels


def _advance(engine: Engine, event_id: int) -> None:
    """Advance the notify cursor under a tiny own transaction (no I/O held under the lock)."""
    with write_connection(engine) as conn:
        try:
            set_notify_cursor(conn, event_id)  # monotonic guard re-reads current
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def notify(
    ctx: typer.Context,
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be sent; deliver nothing; do not advance."
    ),
) -> None:
    """Notify enabled channels of new postings that match your profile since last notify."""
    app_ctx = build_context(ctx.obj)

    # Phase 1: READ (short, plain connection — no long-held lock).
    with app_ctx.engine.connect() as conn:
        profile_row = get_profile(conn)
        if profile_row is None:
            console.print("no profile yet — run `boardwatch init` first")
            raise typer.Exit(code=1)
        profile = profile_view_from_row(profile_row)
        since = get_notify_cursor(conn)
        result = select_new_matches(conn, since, profile, app_ctx.settings)

    # Phase 2: DECIDE / DELIVER (no transaction open).
    if result.is_empty:
        # Advance past non-matching new events so they are not re-scanned every run.
        if result.max_event_id > since and not dry_run:
            _advance(app_ctx.engine, result.max_event_id)
        console.print("no new matches since last notify")
        return
    if dry_run:
        _render(result)
        console.print("dry run — nothing sent, cursor unchanged")
        return
    channels = _build_channels(app_ctx.settings, result)
    if not channels:
        console.print(
            "no channels enabled — run `boardwatch config set notify.webhook_enabled true` "
            "(and set BOARDWATCH_NOTIFY_WEBHOOK_URL) or notify.desktop_enabled true"
        )
        return  # matches undelivered → do NOT advance
    outcome = dispatch(result.items, channels)  # network POST / osascript here, no lock held
    for r in outcome.results:
        console.print(f"  {r.channel}: {'ok' if r.ok else 'failed'} — {r.detail}")

    # Phase 3: ADVANCE (short own tx) only if something actually reached a channel.
    if outcome.any_delivered:
        _advance(app_ctx.engine, result.max_event_id)
