"""T371 end to end: a real offline replay, through the CLI in a subprocess, writes only inside its arm."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

from boardwatch.store.db import get_engine
from tests.pipeline.test_pipeline_run import _ready
from tests.unit.test_replay import _fingerprint
from tools import replay
from tools.replay import Source

BOARDWATCH = Path(sys.executable).with_name("boardwatch")

# The harness is POSIX-only (`main` refuses on Windows: `os.kill(pid, 0)` terminates there).
pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the replay harness is POSIX-only")


def test_a_real_offline_replay_writes_only_inside_its_arm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end through the real CLI in a subprocess, which sees none of this suite's
    `BOARDWATCH_*` pins: the harness strips them, so isolation here is the harness's alone."""
    data, config, queue = tmp_path / "live-data", tmp_path / "live-config", tmp_path / "live-queue"
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(config))
    _ready(data)
    # The operator layout this harness is for: `config.toml` names the live store.
    toml = config / "config.toml"
    toml.write_text(f'data_dir = "{data}"\n' + (toml.read_text() if toml.exists() else ""))
    queue.mkdir()
    # Quiet, the way a store between runs is: the seeding engine's writes checkpointed.
    get_engine(data).dispose()
    with sqlite3.connect(data / "boardwatch.db") as db:
        db.execute("pragma wal_checkpoint(TRUNCATE)")
    # Anything that still reaches the network fails fast instead of fetching.
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        monkeypatch.setenv(var, "http://127.0.0.1:9")
    monkeypatch.delenv("NO_PROXY", raising=False)
    source = Source(data, config, queue)
    before = _fingerprint(*source.dirs())

    (arm,) = replay.clone(source, tmp_path / "scratch", ["base"])
    code = replay.run_arm(arm, ["--top", "10"], boardwatch=BOARDWATCH)

    log = (arm / "run.log").read_text()
    assert code == 0, log
    result = json.loads((arm / "result.json").read_text())
    assert result["isolation"].startswith("ok"), result
    funnel = json.loads(replay.funnel_path(arm).read_text())
    assert funnel["leads"], f"the replay delivered nothing, so isolation proves nothing:\n{log}"
    arm_runs = sqlite3.connect(arm / "data" / "boardwatch.db").execute(
        "select count(*) from runs"
    ).fetchone()[0]
    live_runs = replay.read_only(data / "boardwatch.db").execute(
        "select count(*) from runs"
    ).fetchone()[0]
    assert arm_runs == live_runs + 1
    assert _fingerprint(*source.dirs()) == before, "the replay wrote to the source"
