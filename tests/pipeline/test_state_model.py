"""State tests a–c, e–h, l, m (§6.3-3, P0 ownership) on Greenhouse fixtures."""

import json
from typing import Any

import httpx
import pytest
import respx
from gh_fixtures import (
    BOARD_URL,
    clone_with_id,
    failed_snapshot,
    gh_jobs,
    set_body,
    snapshot_for,
    unchanged_snapshot,
)
from sqlalchemy import Engine, insert, select

from boardwatch.core.models import BoardRequest, ResponseValidators
from boardwatch.core.politeness import Fetcher
from boardwatch.core.settings import Settings
from boardwatch.providers.greenhouse import GreenhouseProvider
from boardwatch.scan.apply import CLOSE_AFTER_MISSES, apply_board
from boardwatch.store import tables
from boardwatch.store.queries import get_validators

V1 = ResponseValidators(etag='W/"v1"', last_modified="Mon, 01 Jun 2026 00:00:00 GMT")
V2 = ResponseValidators(etag='W/"v2"', last_modified="Tue, 02 Jun 2026 00:00:00 GMT")
V3 = ResponseValidators(etag='W/"v3"', last_modified="Wed, 03 Jun 2026 00:00:00 GMT")


def dump(engine: Engine, table: Any) -> list[tuple[Any, ...]]:
    with engine.connect() as conn:
        return [tuple(row) for row in conn.execute(select(table).order_by(table.c[0]))]


def event_kinds(engine: Engine) -> list[str]:
    with engine.connect() as conn:
        return list(
            conn.execute(
                select(tables.posting_events.c.kind).order_by(tables.posting_events.c.id)
            ).scalars()
        )


def posting(engine: Engine, pid: str) -> Any:
    with engine.connect() as conn:
        return conn.execute(
            select(tables.postings).where(tables.postings.c.provider_posting_id == pid)
        ).one()


def scan_statuses(engine: Engine) -> list[str]:
    with engine.connect() as conn:
        return list(
            conn.execute(
                select(tables.board_scans.c.status).order_by(tables.board_scans.c.id)
            ).scalars()
        )


def cache_etag(engine: Engine) -> str | None:
    with engine.connect() as conn:
        return conn.execute(
            select(tables.http_cache.c.etag).where(tables.http_cache.c.url == BOARD_URL)
        ).scalar_one_or_none()


def test_close_after_misses_is_two() -> None:
    assert CLOSE_AFTER_MISSES == 2


def test_a_failed_scan_closes_nothing(engine: Engine, company_id: int, run_id: int) -> None:
    jobs = gh_jobs()[:2]
    apply_board(engine, snapshot_for(jobs, validators=V1), company_id, run_id)
    apply_board(engine, snapshot_for(jobs[:1]), company_id, run_id)  # second job: miss 1
    before_postings = dump(engine, tables.postings)
    before_cache = dump(engine, tables.http_cache)
    before_events = event_kinds(engine)

    result = apply_board(engine, failed_snapshot(), company_id, run_id)

    assert result.status == "failed"
    assert dump(engine, tables.postings) == before_postings  # counters untouched
    assert dump(engine, tables.http_cache) == before_cache  # no validator write
    assert event_kinds(engine) == before_events
    assert scan_statuses(engine)[-1] == "failed"
    with engine.connect() as conn:
        row = conn.execute(
            select(tables.board_scans).order_by(tables.board_scans.c.id.desc())
        ).first()
    assert row is not None and row.error == "HTTP 503 after retries"


def test_b_partial_upserts_resets_and_never_closes(
    engine: Engine, company_id: int, run_id: int
) -> None:
    jobs = gh_jobs()[:2]
    apply_board(engine, snapshot_for(jobs, validators=V1), company_id, run_id)
    apply_board(engine, snapshot_for([], status="complete"), company_id, run_id)  # both miss 1
    assert posting(engine, str(jobs[0]["id"])).consecutive_missing == 1
    before_cache = dump(engine, tables.http_cache)

    listed = clone_with_id(jobs[0], jobs[0]["id"])
    listed["title"] = "Renamed Title via Partial"
    partial = snapshot_for([listed], status="partial", validators=V2, error="1 of 2 failed")
    result = apply_board(engine, partial, company_id, run_id)

    assert result.status == "partial"
    refreshed = posting(engine, str(jobs[0]["id"]))
    assert refreshed.consecutive_missing == 0  # D23: positive observation resets
    assert refreshed.title == "Renamed Title via Partial"  # D25: metadata refreshed
    unlisted = posting(engine, str(jobs[1]["id"]))
    assert unlisted.consecutive_missing == 1  # partial never increments
    assert unlisted.status == "open"  # and never closes
    assert dump(engine, tables.http_cache) == before_cache  # partial never persists validators


def test_c_unchanged_writes_exactly_one_scan_row_and_nothing_else(
    engine: Engine, company_id: int, run_id: int
) -> None:
    apply_board(engine, snapshot_for(gh_jobs()[:2], validators=V1), company_id, run_id)
    tracked = {
        name: table for name, table in tables.metadata.tables.items() if name != "board_scans"
    }
    before = {name: dump(engine, table) for name, table in tracked.items()}
    scans_before = len(scan_statuses(engine))

    result = apply_board(engine, unchanged_snapshot(), company_id, run_id)

    assert result.status == "unchanged"
    after = {name: dump(engine, table) for name, table in tracked.items()}
    assert after == before  # D15 verbatim: EVERY other table untouched — the sole write
    statuses = scan_statuses(engine)
    assert len(statuses) == scans_before + 1
    assert statuses[-1] == "unchanged"
    with engine.connect() as conn:
        row = conn.execute(
            select(tables.board_scans).order_by(tables.board_scans.c.id.desc())
        ).first()
    assert row is not None
    assert row.postings_listed == 0
    assert row.error is None


def test_e_two_complete_misses_close_reappearance_reopens(
    engine: Engine, company_id: int, run_id: int
) -> None:
    jobs = gh_jobs()[:2]
    pid = str(jobs[1]["id"])
    apply_board(engine, snapshot_for(jobs), company_id, run_id)
    apply_board(engine, snapshot_for(jobs[:1]), company_id, run_id)
    assert posting(engine, pid).status == "open"
    apply_board(engine, snapshot_for(jobs[:1]), company_id, run_id)
    closed = posting(engine, pid)
    assert closed.status == "closed"
    assert closed.closed_at is not None
    assert event_kinds(engine).count("closed") == 1

    apply_board(engine, snapshot_for(jobs), company_id, run_id)  # reappears
    reopened = posting(engine, pid)
    assert reopened.status == "open"
    assert reopened.closed_at is None
    assert reopened.consecutive_missing == 0
    assert event_kinds(engine).count("reopened") == 1


def test_f_identical_bodies_two_provider_ids_stay_two_postings(
    engine: Engine, company_id: int, run_id: int
) -> None:
    base = set_body(gh_jobs()[0], "<p>Same body for two simultaneous openings.</p>")
    twin = clone_with_id(base, 987654321)
    apply_board(engine, snapshot_for([base, twin]), company_id, run_id)
    with engine.connect() as conn:
        rows = conn.execute(select(tables.postings)).all()
    assert len(rows) == 2  # D10: identity never merges on content
    assert rows[0].content_hash == rows[1].content_hash
    assert event_kinds(engine) == ["new", "new"]


def test_g_revision_makes_old_extraction_unreachable(
    engine: Engine, company_id: int, run_id: int
) -> None:
    from datetime import datetime

    job = set_body(gh_jobs()[0], "<p>Original body.</p>")
    apply_board(engine, snapshot_for([job]), company_id, run_id)
    row = posting(engine, str(job["id"]))
    old_hash = row.content_hash
    with engine.begin() as conn:
        conn.execute(
            insert(tables.extractions).values(
                posting_id=row.id, content_hash=old_hash, kind="taxonomy",
                engine_version="vtest", json={"skills": ["Python"]},
                created_at=datetime(2026, 1, 1),
            )
        )

    revised_job = set_body(gh_jobs()[0], "<p>Materially different body.</p>")
    apply_board(engine, snapshot_for([revised_job]), company_id, run_id)

    current = posting(engine, str(job["id"]))
    assert current.content_hash != old_hash
    assert "revised" in event_kinds(engine)
    with engine.connect() as conn:
        reachable = conn.execute(
            select(tables.extractions).where(
                tables.extractions.c.posting_id == row.id,
                tables.extractions.c.content_hash == current.content_hash,
            )
        ).all()
        all_rows = conn.execute(select(tables.extractions)).all()
    assert reachable == []  # unreachable via the current hash
    assert len(all_rows) == 1  # but the old row is retained


def test_h_crash_mid_apply_rolls_back_everything_incl_validators(
    engine: Engine,
    company_id: int,
    run_id: int,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    jobs = gh_jobs()[:2]
    apply_board(engine, snapshot_for(jobs[:1], validators=V1), company_id, run_id)
    assert cache_etag(engine) == V1.etag
    before_postings = dump(engine, tables.postings)
    before_events = event_kinds(engine)
    scans_before = len(scan_statuses(engine))

    def boom(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("injected crash mid-apply")

    # _scan_row runs AFTER _persist_validators inside the same transaction, so
    # when this crash hits, the V2 validator upsert and the inventory writes
    # HAVE executed — the rollback must revert all of them together.
    monkeypatch.setattr("boardwatch.scan.apply._scan_row", boom)
    revised = set_body(gh_jobs()[0], "<p>New body that must vanish on rollback.</p>")
    with pytest.raises(RuntimeError, match="injected crash"):
        apply_board(
            engine, snapshot_for([revised, jobs[1]], validators=V2), company_id, run_id
        )
    monkeypatch.undo()

    assert dump(engine, tables.postings) == before_postings  # no partial inventory
    assert event_kinds(engine) == before_events  # no events
    assert len(scan_statuses(engine)) == scans_before  # no scan row
    assert cache_etag(engine) == V1.etag  # the EXECUTED V2 upsert was rolled back

    # Issue #7 follow-up: the next request carries the SURVIVING old validators,
    # so the changed upstream answers 200 with the full body — the 304 trap is
    # structurally impossible (D22).
    with engine.connect() as conn:
        survivors = get_validators(conn, BOARD_URL)
    assert survivors == V1
    request = BoardRequest(
        provider="greenhouse", slug="acme", url=BOARD_URL, validators=survivors
    )
    with respx.mock:
        route = respx.get(BOARD_URL).mock(
            return_value=httpx.Response(
                200, content=json.dumps({"jobs": [revised, jobs[1]]}).encode()
            )
        )
        snapshot = GreenhouseProvider().fetch_board(
            Fetcher(Settings(data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1)),
            request,
        )
    assert route.calls[0].request.headers["If-None-Match"] == V1.etag
    assert snapshot.status == "complete"
    assert len(snapshot.postings) == 2


def test_l_nonconsecutive_misses_never_close(
    engine: Engine, company_id: int, run_id: int
) -> None:
    jobs = gh_jobs()[:2]
    pid = str(jobs[0]["id"])
    apply_board(engine, snapshot_for(jobs), company_id, run_id)      # present
    apply_board(engine, snapshot_for(jobs[1:]), company_id, run_id)   # miss 1
    assert posting(engine, pid).consecutive_missing == 1
    apply_board(engine, snapshot_for(jobs), company_id, run_id)       # present -> reset 0
    assert posting(engine, pid).consecutive_missing == 0
    apply_board(engine, snapshot_for(jobs[1:]), company_id, run_id)   # miss 1 again
    row = posting(engine, pid)
    assert row.status == "open"  # D23: only CONSECUTIVE misses close
    assert row.consecutive_missing == 1
    assert "closed" not in event_kinds(engine)
    apply_board(engine, snapshot_for(jobs[1:]), company_id, run_id)   # consecutive miss 2
    assert posting(engine, pid).status == "closed"


def test_m_metadata_only_change_refreshes_without_revised(
    engine: Engine, company_id: int, run_id: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import datetime

    job = set_body(gh_jobs()[0], "<p>Stable body text.</p>")
    job["pay_input_ranges"] = [{"min_cents": 100, "max_cents": 200}]
    apply_board(engine, snapshot_for([job], validators=V1), company_id, run_id)
    row = posting(engine, str(job["id"]))
    with engine.begin() as conn:
        conn.execute(
            insert(tables.extractions).values(
                posting_id=row.id, content_hash=row.content_hash, kind="taxonomy",
                engine_version="vtest", json={"skills": []},
                created_at=datetime(2026, 1, 1),
            )
        )
    events_before = event_kinds(engine)

    changed = set_body(gh_jobs()[0], "<p>Stable body text.</p>")  # same body
    changed["title"] = job["title"] + " (Updated Level)"
    changed["pay_input_ranges"] = [{"min_cents": 150, "max_cents": 250}]
    apply_board(engine, snapshot_for([changed], validators=V2), company_id, run_id)

    refreshed = posting(engine, str(job["id"]))
    assert refreshed.title.endswith("(Updated Level)")  # mutable fields refreshed
    assert refreshed.raw_json["pay_input_ranges"] == [{"min_cents": 150, "max_cents": 250}]
    assert refreshed.content_hash == row.content_hash  # same body => same hash
    assert event_kinds(engine) == events_before  # NO revised event
    with engine.connect() as conn:
        current_extraction = conn.execute(
            select(tables.extractions).where(
                tables.extractions.c.posting_id == row.id,
                tables.extractions.c.content_hash == refreshed.content_hash,
            )
        ).all()
    assert len(current_extraction) == 1  # extraction stays current
    assert cache_etag(engine) == V2.etag  # validator committed atomically (D22/D25)

    # Failure injection: the metadata refresh and the validator persistence
    # are ATOMIC — a crash after the V3 upsert rolls BOTH back together.
    def boom(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("injected crash after validator upsert")

    monkeypatch.setattr("boardwatch.scan.apply._scan_row", boom)
    crashing = set_body(gh_jobs()[0], "<p>Stable body text.</p>")  # same body again
    crashing["title"] = job["title"] + " (Third Title)"
    with pytest.raises(RuntimeError, match="injected crash"):
        apply_board(engine, snapshot_for([crashing], validators=V3), company_id, run_id)
    monkeypatch.undo()
    after_crash = posting(engine, str(job["id"]))
    assert after_crash.title.endswith("(Updated Level)")  # refresh rolled back ...
    assert cache_etag(engine) == V2.etag  # ... together with the V3 validator (atomic)
