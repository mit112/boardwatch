"""`boardwatch web` — serve the local review app on loopback (design §7).

**This command does not build the context every other DB command builds.** `build_context` calls
`ensure_schema`, which runs alembic to head — so opening a browser tab would migrate the store, and
on a checkout carrying a migration the daily driver has never seen that is D-279 exactly. The
review app is a *viewer* of a store `boardwatch run` maintains: it reads through
`get_readonly_engine` and writes only the four mark functions, and neither needs a migration. So
this resolves settings and nothing else.

`--host` exists so a non-loopback address can be **refused by name** rather than silently ignored.
The refusal is the feature: the server carries the owner's answers panel, their résumé and
third-party job text, and the only thing standing between that and the network is the bind
address.
"""

from __future__ import annotations

import sys
import webbrowser
from pathlib import Path

import typer
from rich.console import Console

from boardwatch.cli.run_cmd import DEFAULT_OUT_ROOT
from boardwatch.core.settings import Settings, load_settings
from boardwatch.delivery.api import ApiContext, resolve_owner_name
from boardwatch.delivery.queue import DEFAULT_QUEUE_ROOT
from boardwatch.delivery.server import (
    BundleMissingError,
    NonLoopbackBindError,
    build_server,
    load_or_create_token,
    prime_queue,
)
from boardwatch.store.db import WalUnsafeFilesystemError, get_readonly_engine

console = Console()

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787


def web(
    ctx: typer.Context,
    host: str = typer.Option(
        DEFAULT_HOST, "--host", help="Bind address. Only loopback is permitted."
    ),
    port: int = typer.Option(DEFAULT_PORT, "--port", help="Port to bind. 0 picks a free one."),
    out_root: Path = typer.Option(  # noqa: B008
        DEFAULT_OUT_ROOT, "--out-root", help="Where runs wrote their PDFs and funnel artifacts."
    ),
    queue_root: Path = typer.Option(  # noqa: B008
        DEFAULT_QUEUE_ROOT, "--queue-root", help="The delivery queue's own root."
    ),
    open_browser: bool = typer.Option(
        True, "--open/--no-open", help="Open the session URL in your browser."
    ),
) -> None:
    """Review this run's leads in a local web page (loopback only)."""
    settings = load_settings(data_dir=ctx.obj)
    api_ctx = ApiContext(
        settings=settings,
        # Resolved here, once: `plan_lead_names` prices its byte budget against the root it is
        # given, and every containment check compares resolved paths.
        out_root=out_root.expanduser().resolve(),
        queue_root=queue_root.expanduser().resolve(),
        owner_name=_owner_name(settings),
        platform=sys.platform,
    )
    token = load_or_create_token(settings.config_dir)
    try:
        server = build_server(ctx=api_ctx, token=token, host=host, port=port)
    except NonLoopbackBindError as exc:
        console.print(str(exc), markup=False)
        raise typer.Exit(code=2) from exc
    except BundleMissingError as exc:
        console.print(str(exc), markup=False)
        raise typer.Exit(code=2) from exc
    except OSError as exc:
        console.print(f"could not bind {host}:{port}: {exc.strerror}", markup=False)
        raise typer.Exit(code=1) from exc

    prime_queue(api_ctx)
    console.print("boardwatch review — open this URL:", markup=False)
    # `markup=False` because the URL carries the token, and a token is arbitrary URL-safe text
    # Rich must never read as a style tag. `soft_wrap=True` because Rich hard-wraps a "word"
    # longer than the terminal, and a URL folded mid-token is a URL that cannot be copied — the
    # one thing this line exists to be. On its own line so a double-click selects all of it.
    console.print(server.url, markup=False, soft_wrap=True)
    console.print(
        f"The token lives in {settings.config_dir / 'web-token'} and is stable, so this URL can "
        "be bookmarked. Ctrl-C to stop.",
        markup=False,
    )
    if open_browser:
        webbrowser.open(server.url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        console.print("stopped", markup=False)
    finally:
        server.server_close()


def _owner_name(settings: Settings) -> str:
    """The owner's name for the résumé download filename, from their own files.

    A store that does not exist yet is not an error here: the name falls back to the answers file
    and the résumé, both of which are read without a connection.
    """
    try:
        engine = get_readonly_engine(settings.data_dir, busy_timeout_ms=settings.busy_timeout_ms)
    except (OSError, WalUnsafeFilesystemError):
        return resolve_owner_name(None, settings.config_dir)
    try:
        with engine.connect() as conn:
            return resolve_owner_name(conn, settings.config_dir)
    finally:
        engine.dispose()


__all__ = ["DEFAULT_HOST", "DEFAULT_PORT", "web"]
