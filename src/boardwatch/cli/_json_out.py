"""The pipe contract for every command that takes `--json`, in one place.

One JSON object goes to standard output and nothing else does, so the output can be piped into
the next program. Everything a person needs to read but a pipe must not swallow — preflight
notices, refusals, "nothing tracked yet", the next-step hint — goes to standard error instead.
`boardwatch guide` states this contract; the commands that honour it route their readable lines
through `narrative` and their one object through `emit_json`.
"""

from __future__ import annotations

import json
from datetime import datetime

import typer
from rich.console import Console

ERR = Console(stderr=True)


def emit_json(payload: object) -> None:
    """Write one JSON object and a newline to standard output.

    Through `typer.echo`, not `sys.stdout.write`, for the reason `export_cmd` gives: a REDIRECTED
    Windows stdout reports the ANSI codepage, so a non-ASCII character in a third-party job
    description raises `UnicodeEncodeError` and the pipe dies. Click force-corrects the stream.
    Dates become ISO 8601 (`str(datetime)` uses a space separator, which is not ISO); paths and
    everything else become `str`.
    """
    typer.echo(
        json.dumps(
            payload,
            default=lambda o: o.isoformat() if isinstance(o, datetime) else str(o),
            ensure_ascii=False,
        )
    )


def narrative(as_json: bool, console: Console) -> Console:
    """Where a command's readable lines go: standard error under `--json`, `console` otherwise."""
    return ERR if as_json else console
