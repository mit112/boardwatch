"""The pipe contract for every command that takes `--json`, in one place.

One JSON object goes to standard output and nothing else does, so the output can be piped into
the next program. Everything a person needs to read but a pipe must not swallow — preflight
notices, refusals, "nothing tracked yet", the next-step hint — goes to standard error instead.
`boardwatch guide` states this contract; the commands that honour it route their readable lines
through `narrative` and their one object through `emit_json`.
"""

from __future__ import annotations

import json
import sys

from rich.console import Console

ERR = Console(stderr=True)


def emit_json(payload: object) -> None:
    """Write one JSON object and a newline to standard output. Dates and paths become strings."""
    sys.stdout.write(json.dumps(payload, default=str, ensure_ascii=False) + "\n")


def narrative(as_json: bool, console: Console) -> Console:
    """Where a command's readable lines go: standard error under `--json`, `console` otherwise."""
    return ERR if as_json else console
