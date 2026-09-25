"""The REAL job-apps lane through the pipeline's lane stage, over both of its roots (T218).

`test_lane_stage.py` drives the stage with a stub; this drives it with `JobAppsLane` built by its
own `LANE_FACTORIES` row from the two settings, so the funnel's T191 cross-check compares the
lane's self-report against the store's recount of what two real roots landed.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from tests.pipeline.test_lane_stage import _lane_checks, _payload, _pipeline, _ready, env
from tests.unit.test_jobapps_lane import (
    _staging_with_one_dangling_group_link,
    _tree_with_one_unlistable_group,
    _two_roots_sharing_one_record,
    lock_dir,
)

__all__ = ["env", "lock_dir"]  # the fixtures, imported so pytest resolves them here


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


def test_a_dangling_group_link_reaches_the_funnels_lane_row_and_the_lane_does_not_fail(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T220, end to end: a staging root with one dangling group link beside a resolving and a
    plain group. The lane raises nothing -- no `jobapps` error line -- and the count reaches the
    funnel artifact's lane row through the tally's `counts`, read back off disk rather than off
    the in-memory report."""
    _ready(env)
    discovery = tmp_path / "jobapps" / "resumes"
    (discovery / "Greenhouse").mkdir(parents=True)  # intact and empty: the owner caught up
    staging = _staging_with_one_dangling_group_link(tmp_path / "jobapps")

    summary = _pipeline(
        env,
        tmp_path / "apps",
        lanes_enabled=("jobapps",),
        jobapps_discovery_dir=discovery,
        jobapps_queue_dir=staging,
    )

    assert summary.fatal is None
    assert not [error for error in summary.errors if "jobapps" in error], summary.errors
    [lane] = _payload(tmp_path / "apps")["lanes"]
    assert lane["name"] == "jobapps"
    assert lane["counts"]["dangling_group_link"] == 1
    assert lane["counts"]["not_attemptable"] == 0
    assert lane["counts"]["body_inline"] == 3
    # The published record count keeps its meaning: three records, not three plus a group.
    assert lane["attempted"] == 3
    assert lane["is_silent_outage"] is False


def test_an_unlistable_group_reaches_the_funnels_lane_row_and_the_lane_does_not_fail(
    env: Path, tmp_path: Path, lock_dir: Callable[[Path], None]
) -> None:
    """T238, end to end: one group that resolves but cannot be listed, beside a readable one.
    The lane raises nothing and the count reaches the funnel artifact's lane row, read back off
    disk."""
    _ready(env)
    discovery = tmp_path / "jobapps" / "resumes"
    (discovery / "Greenhouse").mkdir(parents=True)  # intact and empty: the owner caught up
    queue = _tree_with_one_unlistable_group(tmp_path / "jobapps", lock_dir)

    summary = _pipeline(
        env,
        tmp_path / "apps",
        lanes_enabled=("jobapps",),
        jobapps_discovery_dir=discovery,
        jobapps_queue_dir=queue,
    )

    assert summary.fatal is None
    assert not [error for error in summary.errors if "jobapps" in error], summary.errors
    [lane] = _payload(tmp_path / "apps")["lanes"]
    assert lane["counts"]["unreadable_group"] == 1
    assert lane["counts"]["dangling_group_link"] == 0
    assert lane["counts"]["body_inline"] == 1
    assert lane["attempted"] == 1
    assert lane["is_silent_outage"] is False
