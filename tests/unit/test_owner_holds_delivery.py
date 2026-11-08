"""An owner hold leaves every actionable list and drains/re-enters without losing files."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert

from boardwatch.core.settings import load_settings
from boardwatch.delivery.api import ApiContext, queue_payload, rejected_payload
from boardwatch.delivery.queue import refresh_queue, sync_queue
from boardwatch.store.app_state import set_state
from boardwatch.store.queue_state import mark_job_manual, mark_job_skipped
from boardwatch.store.tables import app_state
from tests.unit.test_delivery_queue import (
    NOW,
    OWNER,
    _deliver,
)
from tests.unit.test_delivery_queue import (
    _scratch_config as _scratch_config,
)
from tests.unit.test_delivery_queue import (
    apps as apps,
)
from tests.unit.test_delivery_queue import (
    engine as engine,
)
from tests.unit.test_delivery_queue import (
    root as root,
)


@pytest.mark.parametrize("manual", [False, True])
def test_hold_drains_actionable_lists_preserves_files_and_release_restores_lane(
    engine: Engine, apps: Path, root: Path, manual: bool,
) -> None:
    with engine.begin() as conn:
        pid, job = _deliver(conn, apps, "held")
        control, _ = _deliver(conn, apps, "control", title="Frontend Engineer")
        sync_queue(conn, root=root, owner_name=OWNER)
        if manual:
            mark_job_manual(conn, job_id=job, at=NOW)
    refresh_queue(engine, root=root, owner_name=OWNER)
    details = next(p for p in root.rglob("details.json") if json.loads(p.read_text())["posting_id"] == pid)
    (details.parent / "owner-note.txt").write_text("Keep my notes")
    value = {"version": 1, "reason": "Await owner", "held_at": NOW.isoformat(), "released_at": None}
    with engine.begin() as conn:
        conn.execute(insert(app_state).values(key=f"queue.held.{job}", value=json.dumps(value)))
    drained, synced = refresh_queue(engine, root=root, owner_name=OWNER)
    assert not drained.failures and not synced.failures
    assert drained.moved == 1
    ctx = ApiContext(settings=load_settings(), out_root=apps.resolve(), queue_root=root.resolve(),
                     owner_name=OWNER, platform="darwin")
    with engine.connect() as conn:
        page = queue_payload(conn, ctx)
        assert all(pid not in {r["posting_id"] for r in page[k]} for k in ("rows", "review", "manual"))
        assert control in {r["posting_id"] for r in page["rows"]}
        assert page["counts"]["held"] == 1
        assert [(r["posting_id"], r["reason"]) for r in page["held"]] == [(pid, "Await owner")]
        assert pid not in {r["posting_id"] for r in rejected_payload(conn, ctx)["rows"]}
    held = root / "_held" / details.parent.name
    assert (held / "owner-note.txt").read_text() == "Keep my notes"
    assert len(list(root.rglob("owner-note.txt"))) == 1
    with engine.begin() as conn:
        value["released_at"] = NOW.isoformat()
        set_state(conn, f"queue.held.{job}", json.dumps(value))
    refresh_queue(engine, root=root, owner_name=OWNER)
    with engine.connect() as conn:
        page = queue_payload(conn, ctx)
        assert pid in {r["posting_id"] for r in page["manual" if manual else "rows"]}
    restored = next(root.rglob("owner-note.txt"))
    assert restored.read_text() == "Keep my notes"
    assert "_held" not in restored.parts


def test_releasing_hold_does_not_release_independent_skip(engine: Engine, apps: Path, root: Path) -> None:
    from boardwatch.store.owner_holds import hold_job, release_job_hold

    with engine.begin() as conn:
        pid, job = _deliver(conn, apps, "skipped-hold")
        sync_queue(conn, root=root, owner_name=OWNER)
        mark_job_skipped(conn, job_id=job, at=NOW)
        hold_job(conn, job_id=job, reason="Pending", at=NOW)
        release_job_hold(conn, job_id=job, at=NOW)
    refresh_queue(engine, root=root, owner_name=OWNER)
    assert len(list((root / "_skipped").rglob("details.json"))) == 1


def test_hold_preserves_existing_duplicate_holder(engine: Engine, apps: Path) -> None:
    from boardwatch.store.delivery_queries import requisition_holder_urls, standing_slate_keys
    from boardwatch.store.owner_holds import hold_job

    with engine.begin() as conn:
        pid, job = _deliver(conn, apps, "held-holder",
                            url="https://boards.greenhouse.io/acme/jobs/42")
        hold_job(conn, job_id=job, reason="Pending owner decision", at=NOW)
    with engine.connect() as conn:
        assert pid in requisition_holder_urls(conn)[0]
        assert any(pid in ids for ids in standing_slate_keys(conn).values())
