"""State tests a–c, e–h, l, m (§6.3-3, P0 ownership) parametrized over three providers."""

from datetime import datetime
from typing import Any

import httpx
import pytest
import respx
from provider_cases import ProviderCase
from sqlalchemy import Engine, insert, select

from boardwatch.core.models import BoardRequest, ResponseValidators
from boardwatch.core.politeness import Fetcher
from boardwatch.core.settings import Settings
from boardwatch.scan.apply import CLOSE_AFTER_MISSES, apply_board
from boardwatch.store import tables
from boardwatch.store.queries import get_validators

V1 = ("W/\"v1\"", "Mon, 01 Jun 2026 00:00:00 GMT")
V2 = ("W/\"v2\"", "Tue, 02 Jun 2026 00:00:00 GMT")
V3 = ("W/\"v3\"", "Wed, 03 Jun 2026 00:00:00 GMT")


def _validators(v):
    return ResponseValidators(etag=v[0], last_modified=v[1])


def _dump(engine: Engine, table: Any) -> list[tuple]:
    with engine.connect() as conn:
        return [tuple(r) for r in conn.execute(select(table).order_by(table.c[0]))]


def _event_kinds(engine: Engine) -> list[str]:
    with engine.connect() as conn:
        return list(conn.execute(
            select(tables.posting_events.c.kind).order_by(tables.posting_events.c.id)
        ).scalars())


def _scan_statuses(engine: Engine) -> list[str]:
    with engine.connect() as conn:
        return list(conn.execute(
            select(tables.board_scans.c.status).order_by(tables.board_scans.c.id)
        ).scalars())


def _posting_by_pid(engine: Engine, pid: str) -> Any:
    with engine.connect() as conn:
        return conn.execute(
            select(tables.postings).where(tables.postings.c.provider_posting_id == pid)
        ).one()


def _cache_etag(engine: Engine, url: str) -> str | None:
    with engine.connect() as conn:
        return conn.execute(
            select(tables.http_cache.c.etag).where(tables.http_cache.c.url == url)
        ).scalar_one_or_none()


def _seed_extraction(engine: Engine, posting_id: int, content_hash: str, skills: list[str]) -> None:
    with engine.begin() as conn:
        conn.execute(insert(tables.extractions).values(
            posting_id=posting_id, content_hash=content_hash, kind="taxonomy",
            engine_version="vtest", json={"skills": skills}, created_at=datetime(2026, 1, 1),
        ))


def test_close_after_misses_is_two() -> None:
    assert CLOSE_AFTER_MISSES == 2


def test_a_failed_scan_closes_nothing(
    engine: Engine, company_id: int, run_id: int, case: ProviderCase
) -> None:
    jobs = case.jobs()[:2]
    apply_board(engine, case.snapshot_for(jobs, validators=_validators(V1)), company_id, run_id)
    apply_board(engine, case.snapshot_for(jobs[:1]), company_id, run_id)  # second job: miss 1
    before_postings = _dump(engine, tables.postings)
    before_cache = _dump(engine, tables.http_cache)
    before_events = _event_kinds(engine)

    result = apply_board(engine, case.failed_snapshot(), company_id, run_id)

    assert result.status == "failed"
    assert _dump(engine, tables.postings) == before_postings  # counters untouched
    assert _dump(engine, tables.http_cache) == before_cache  # no validator write
    assert _event_kinds(engine) == before_events
    assert _scan_statuses(engine)[-1] == "failed"
    with engine.connect() as conn:
        row = conn.execute(
            select(tables.board_scans).order_by(tables.board_scans.c.id.desc())
        ).first()
    assert row is not None and row.error == "HTTP 503 after retries"


def test_b_partial_upserts_resets_and_never_closes(
    engine: Engine, company_id: int, run_id: int, case: ProviderCase
) -> None:
    jobs = case.jobs()[:2]
    apply_board(engine, case.snapshot_for(jobs, validators=_validators(V1)), company_id, run_id)
    apply_board(engine, case.snapshot_for([], status="complete"), company_id, run_id)  # both miss 1
    assert _posting_by_pid(engine, str(jobs[0]["id"])).consecutive_missing == 1
    before_cache = _dump(engine, tables.http_cache)

    listed = case.clone_with_id(jobs[0], jobs[0]["id"])
    listed[case.title_key] = "Renamed Title via Partial"
    partial = case.snapshot_for([listed], status="partial", validators=_validators(V2), error="1 of 2 failed")
    result = apply_board(engine, partial, company_id, run_id)

    assert result.status == "partial"
    refreshed = _posting_by_pid(engine, str(jobs[0]["id"]))
    assert refreshed.consecutive_missing == 0  # D23: positive observation resets
    assert refreshed.title == "Renamed Title via Partial"  # D25: metadata refreshed
    unlisted = _posting_by_pid(engine, str(jobs[1]["id"]))
    assert unlisted.consecutive_missing == 1  # partial never increments
    assert unlisted.status == "open"  # and never closes
    assert _dump(engine, tables.http_cache) == before_cache  # partial never persists validators


def test_c_unchanged_writes_exactly_one_scan_row_and_nothing_else(
    engine: Engine, company_id: int, run_id: int, case: ProviderCase
) -> None:
    apply_board(engine, case.snapshot_for(case.jobs()[:2], validators=_validators(V1)), company_id, run_id)
    tracked = {
        name: table for name, table in tables.metadata.tables.items() if name != "board_scans"
    }
    before = {name: _dump(engine, table) for name, table in tracked.items()}
    scans_before = len(_scan_statuses(engine))

    result = apply_board(engine, case.unchanged_snapshot(), company_id, run_id)

    assert result.status == "unchanged"
    after = {name: _dump(engine, table) for name, table in tracked.items()}
    assert after == before  # D15 verbatim: EVERY other table untouched — the sole write
    statuses = _scan_statuses(engine)
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
    engine: Engine, company_id: int, run_id: int, case: ProviderCase
) -> None:
    jobs = case.jobs()[:2]
    pid = str(jobs[1]["id"])
    apply_board(engine, case.snapshot_for(jobs), company_id, run_id)
    apply_board(engine, case.snapshot_for(jobs[:1]), company_id, run_id)
    assert _posting_by_pid(engine, pid).status == "open"
    apply_board(engine, case.snapshot_for(jobs[:1]), company_id, run_id)
    closed = _posting_by_pid(engine, pid)
    assert closed.status == "closed"
    assert closed.closed_at is not None
    assert _event_kinds(engine).count("closed") == 1

    apply_board(engine, case.snapshot_for(jobs), company_id, run_id)  # reappears
    reopened = _posting_by_pid(engine, pid)
    assert reopened.status == "open"
    assert reopened.closed_at is None
    assert reopened.consecutive_missing == 0
    assert _event_kinds(engine).count("reopened") == 1


def test_f_identical_bodies_two_provider_ids_stay_two_postings(
    engine: Engine, company_id: int, run_id: int, case: ProviderCase
) -> None:
    base = case.set_body(case.jobs()[0], "Same body for two simultaneous openings.")
    twin = case.clone_with_id(base, 987654321)
    apply_board(engine, case.snapshot_for([base, twin]), company_id, run_id)
    with engine.connect() as conn:
        rows = conn.execute(select(tables.postings)).all()
    assert len(rows) == 2  # D10: identity never merges on content
    assert rows[0].content_hash == rows[1].content_hash
    assert _event_kinds(engine) == ["new", "new"]


def test_g_revision_makes_old_extraction_unreachable(
    engine: Engine, company_id: int, run_id: int, case: ProviderCase
) -> None:
    jobs = case.jobs()[:1]
    pid = str(jobs[0]["id"])
    case.set_body(jobs[0], "Original body.")
    apply_board(engine, case.snapshot_for(jobs), company_id, run_id)
    row = _posting_by_pid(engine, pid)
    old_hash = row.content_hash
    _seed_extraction(engine, row.id, old_hash, ["Python"])

    revised = case.jobs()[:1]
    case.set_body(revised[0], "Materially different body.")
    apply_board(engine, case.snapshot_for(revised), company_id, run_id)

    current = _posting_by_pid(engine, pid)
    assert current.content_hash != old_hash
    assert "revised" in _event_kinds(engine)
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
    case: ProviderCase,
) -> None:
    jobs = case.jobs()[:2]
    apply_board(engine, case.snapshot_for(jobs[:1], validators=_validators(V1)), company_id, run_id)
    assert _cache_etag(engine, case.board_url()) == V1[0]
    before_postings = _dump(engine, tables.postings)
    before_events = _event_kinds(engine)
    scans_before = len(_scan_statuses(engine))

    def boom(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("injected crash mid-apply")

    # _scan_row runs AFTER _persist_validators inside the same transaction, so
    # when this crash hits, the V2 validator upsert and the inventory writes
    # HAVE executed — the rollback must revert all of them together.
    monkeypatch.setattr("boardwatch.scan.apply._scan_row", boom)
    revised = case.set_body(case.jobs()[0], "New body that must vanish on rollback.")
    with pytest.raises(RuntimeError, match="injected crash"):
        apply_board(
            engine, case.snapshot_for([revised, jobs[1]], validators=_validators(V2)), company_id, run_id
        )
    monkeypatch.undo()

    assert _dump(engine, tables.postings) == before_postings  # no partial inventory
    assert _event_kinds(engine) == before_events  # no events
    assert len(_scan_statuses(engine)) == scans_before  # no scan row
    assert _cache_etag(engine, case.board_url()) == V1[0]  # the EXECUTED V2 upsert was rolled back

    # Issue #7 follow-up: the next request carries the SURVIVING old validators,
    # so the changed upstream answers 200 with the full body — the 304 trap is
    # structurally impossible (D22).
    with engine.connect() as conn:
        survivors = get_validators(conn, case.board_url())
    assert survivors == _validators(V1)
    request = BoardRequest(
        provider=case.name, slug="acme", url=case.board_url(), validators=survivors
    )
    with respx.mock:
        route = respx.get(case.board_url()).mock(
            return_value=httpx.Response(
                200, content=case.wrap([revised, jobs[1]])
            )
        )
        snapshot = case.provider.fetch_board(
            Fetcher(Settings(data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1)),
            request,
        )
    assert route.calls[0].request.headers["If-None-Match"] == V1[0]
    assert snapshot.status == "complete"
    assert len(snapshot.postings) == 2


def test_l_nonconsecutive_misses_never_close(
    engine: Engine, company_id: int, run_id: int, case: ProviderCase
) -> None:
    jobs = case.jobs()[:2]
    pid = str(jobs[0]["id"])
    apply_board(engine, case.snapshot_for(jobs), company_id, run_id)      # present
    apply_board(engine, case.snapshot_for(jobs[1:]), company_id, run_id)  # miss 1
    assert _posting_by_pid(engine, pid).consecutive_missing == 1
    apply_board(engine, case.snapshot_for(jobs), company_id, run_id)       # present -> reset 0
    assert _posting_by_pid(engine, pid).consecutive_missing == 0
    apply_board(engine, case.snapshot_for(jobs[1:]), company_id, run_id)   # miss 1 again
    row = _posting_by_pid(engine, pid)
    assert row.status == "open"  # D23: only CONSECUTIVE misses close
    assert row.consecutive_missing == 1
    assert "closed" not in _event_kinds(engine)
    apply_board(engine, case.snapshot_for(jobs[1:]), company_id, run_id)  # consecutive miss 2
    assert _posting_by_pid(engine, pid).status == "closed"


def test_m_metadata_only_change_refreshes_without_revised(
    engine: Engine, company_id: int, run_id: int, monkeypatch: pytest.MonkeyPatch,
    case: ProviderCase,
) -> None:
    jobs = case.jobs()[:1]
    pid = str(jobs[0]["id"])
    case.set_body(jobs[0], "Stable body text.")
    case.set_metadata(jobs[0], variant=1)
    apply_board(engine, case.snapshot_for(jobs, validators=_validators(V1)), company_id, run_id)
    row = _posting_by_pid(engine, pid)
    meta_before = case.metadata_value(row.raw_json)
    _seed_extraction(engine, row.id, row.content_hash, [])
    events_before = _event_kinds(engine)

    changed = case.jobs()[:1]
    case.set_body(changed[0], "Stable body text.")   # SAME body
    case.set_title(changed[0], " (Updated Level)")   # metadata: title …
    case.set_metadata(changed[0], variant=2)         # … and a DISTINCT provider metadata value
    apply_board(engine, case.snapshot_for(changed, validators=_validators(V2)), company_id, run_id)

    refreshed = _posting_by_pid(engine, pid)
    assert refreshed.title.endswith("(Updated Level)")               # mutable fields refreshed
    assert case.metadata_value(refreshed.raw_json) != meta_before    # provider metadata refreshed
    assert refreshed.content_hash == row.content_hash               # same body => same hash
    assert _event_kinds(engine) == events_before                    # NO revised event
    with engine.connect() as conn:
        current_extraction = conn.execute(
            select(tables.extractions).where(
                tables.extractions.c.posting_id == row.id,
                tables.extractions.c.content_hash == refreshed.content_hash,
            )
        ).all()
    assert len(current_extraction) == 1  # extraction stays current
    assert _cache_etag(engine, case.board_url()) == V2[0]  # validator committed atomically

    # Failure injection: the metadata refresh and the validator persistence
    # are ATOMIC — a crash after the V3 upsert rolls BOTH back together.
    def boom(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("injected crash after validator upsert")

    monkeypatch.setattr("boardwatch.scan.apply._scan_row", boom)
    crashing = case.jobs()[:1]
    case.set_body(crashing[0], "Stable body text.")  # same body again
    case.set_title(crashing[0], " (Third Title)")
    with pytest.raises(RuntimeError, match="injected crash"):
        apply_board(engine, case.snapshot_for(crashing, validators=_validators(V3)), company_id, run_id)
    monkeypatch.undo()
    after_crash = _posting_by_pid(engine, pid)
    assert after_crash.title.endswith("(Updated Level)")  # refresh rolled back ...
    assert _cache_etag(engine, case.board_url()) == V2[0]  # ... together with the V3 validator (atomic)
