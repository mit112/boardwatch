"""The REAL job-apps lane through the pipeline's lane stage, over both of its roots (T218).

`test_lane_stage.py` drives the stage with a stub; this drives it with `JobAppsLane` built by its
own `LANE_FACTORIES` row from the two settings, so the funnel's T191 cross-check compares the
lane's self-report against the store's recount of what two real roots landed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.pipeline.test_lane_stage import _lane_checks, _payload, _pipeline, _ready, env
from tests.unit.test_jobapps_lane import _two_roots_sharing_one_record

__all__ = ["env"]  # the fixture, imported so pytest resolves it here


def test_two_roots_persist_the_distinct_set_and_the_funnel_recount_agrees(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Four records over two roots, one in both by `posting_id`: three new employers land, the
    lane reports three, and the store's independent recount finds three. A walk that reads the
    discovery root twice instead of the queue reports and lands two."""
    _ready(env)
    discovery, promoted = _two_roots_sharing_one_record(tmp_path / "jobapps")

    summary = _pipeline(
        env,
        tmp_path / "apps",
        lanes_enabled=("jobapps",),
        jobapps_discovery_dir=discovery,
        jobapps_queue_dir=promoted,
    )

    assert summary.fatal is None
    [report] = summary.lanes
    assert sorted(report.persisted_new) == [
        ("greenhouse", "alpha"), ("greenhouse", "beta"), ("greenhouse", "sharedco"),
    ]
    assert _lane_checks(_payload(tmp_path / "apps")) == {
        "lane:jobapps:persisted_new": (3, 3, True),
        "lanes:board_scans": (3, 3, True),
    }
