"""`boardwatch web` serves while the start-up queue prime is still running.

Run inline, the prime held the process for ~106 s on the live store with the socket already bound
and listening, so every request in that window was reset and the viewer read as down after each
restart. The page reads the database, not the folders, so nothing it serves waits on the prime.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from boardwatch.cli import web_cmd
from boardwatch.cli.app import app


class _FakeServer:
    url = "http://127.0.0.1:0/#token"

    def __init__(self, primed: threading.Event) -> None:
        self.primed = primed
        self.served_before_prime_ended: bool | None = None

    def serve_forever(self) -> None:
        self.served_before_prime_ended = not self.primed.is_set()

    def server_close(self) -> None:
        pass


def test_the_server_serves_before_the_prime_finishes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release, primed = threading.Event(), threading.Event()

    def slow_prime(_ctx: Any) -> None:
        release.wait(timeout=10)
        primed.set()

    server = _FakeServer(primed)
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(web_cmd, "prime_queue", slow_prime)
    monkeypatch.setattr(web_cmd, "build_server", lambda **_kw: server)
    try:
        result = CliRunner().invoke(
            app, ["--data-dir", str(tmp_path / "data"), "web", "--no-open"]
        )
    finally:
        release.set()
    assert result.exit_code == 0, result.output
    assert server.served_before_prime_ended is True
    assert primed.wait(timeout=10)  # the prime still runs to the end
