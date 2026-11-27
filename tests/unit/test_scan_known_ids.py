"""T350 item 1: which boards are handed their open ids, and exactly which ids.

A provider that skips the detail read for an id the store holds open declares `reads_known_ids`,
and only those boards are handed the set. Each gets exactly its own board's OPEN ids: a closed id
listed again (a reopen) is not known and must be detail-fetched, and one `provider_posting_id`
on two boards belongs to each board's own set.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from sqlalchemy import insert

from boardwatch.core.clock import utcnow
from boardwatch.core.models import BoardRequest, BoardSnapshot
from boardwatch.core.settings import load_settings
from boardwatch.providers.registry import build_providers
from boardwatch.scan import coordinator
from boardwatch.scan.coordinator import run_scan
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.posting_blobs import insert_posting


def test_a_provider_declares_reads_known_ids_exactly_when_it_reads_them() -> None:
    """The closed set lives with the providers. A provider that reads the set without declaring
    it would be handed an empty one and detail-fetch every posting it already holds, silently."""
    for name, provider in build_providers().items():
        reads = "known_posting_ids" in inspect.getsource(inspect.getmodule(provider))  # type: ignore[arg-type]
        assert bool(getattr(provider, "reads_known_ids", False)) == reads, name


class _Recorder:
    """A provider that records the request it was handed and lists nothing."""

    board_hosts: tuple[str, ...] = ()

    def __init__(self, name: str, *, reads: bool) -> None:
        self.name = name
        if reads:
            self.reads_known_ids = True
        self.seen: dict[str, frozenset[str]] = {}

    def board_url(self, slug: str) -> str:
        return f"https://{slug}.{self.name}.test/jobs"

    def fetch_board(self, fetcher: object, request: BoardRequest) -> BoardSnapshot:
        self.seen[request.slug] = request.known_posting_ids
        return BoardSnapshot(status="failed", postings=[], url=request.url,
                             observed_validators=None, error="recorded")

    def healthcheck(self, fetcher: object, slug: str) -> object:
        raise NotImplementedError


def _board(conn, provider: str, slug: str, postings: dict[str, str]) -> None:  # type: ignore[no-untyped-def]
    now = utcnow()
    company_id = conn.execute(insert(tables.companies).values(
        name=slug, provider=provider, slug=slug, source="user", watched=True
    )).inserted_primary_key[0]
    for posting_id, status in postings.items():
        job_id = conn.execute(insert(tables.jobs).values(created_at=now)).inserted_primary_key[0]
        insert_posting(conn,
            company_id=company_id, provider_posting_id=posting_id, title="Engineer",
            normalized_title="engineer", url="https://example.test/j", locations_json=[],
            remote_policy="unknown", first_seen_at=now, last_seen_at=now, status=status,
            consecutive_missing=0, content_hash=f"h-{slug}-{posting_id}", body_text="",
            job_id=job_id, closed_at=now if status == "closed" else None,
        )


@pytest.mark.usefixtures("no_real_sleep")
def test_each_reading_board_gets_its_own_open_ids_and_no_other_board_gets_any(
    tmp_path: Path,
) -> None:
    data = tmp_path / "data"
    engine = get_engine(data)
    ensure_schema(engine)
    with engine.begin() as conn:
        _board(conn, "reader", "a", {"1": "open", "shared": "open", "reopened": "closed"})
        _board(conn, "reader", "b", {"shared": "open", "2": "open"})
        _board(conn, "reader", "empty", {})
        _board(conn, "plain", "c", {"3": "open"})
    reader, plain = _Recorder("reader", reads=True), _Recorder("plain", reads=False)
    settings = load_settings(data_dir=data).model_copy(update={"scan_workers": 2})

    run_scan(engine, settings, providers={"reader": reader, "plain": plain})  # type: ignore[dict-item]

    assert reader.seen == {
        "a": frozenset({"1", "shared"}),  # not "reopened": it is closed, so it is not known
        "b": frozenset({"shared", "2"}),
        "empty": frozenset(),
    }
    assert plain.seen == {"c": frozenset()}


@pytest.mark.usefixtures("no_real_sleep")
def test_a_boards_ids_are_read_when_it_is_dispatched_not_for_the_fleet_up_front(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The memory claim: only boards in flight hold their sets. One worker, so each read must
    sit right before its own board's fetch, and a board that does not read ids is never read."""
    data = tmp_path / "data"
    engine = get_engine(data)
    ensure_schema(engine)
    with engine.begin() as conn:
        _board(conn, "reader", "a", {"1": "open"})
        _board(conn, "reader", "b", {"2": "open"})
        _board(conn, "plain", "c", {"3": "open"})
    events: list[str] = []
    real = coordinator._known_posting_ids

    def recording(engine_: object, company_id: int) -> frozenset[str]:
        events.append(f"read {company_id}")
        return real(engine_, company_id)  # type: ignore[arg-type]

    monkeypatch.setattr(coordinator, "_known_posting_ids", recording)

    class _Ordered(_Recorder):
        def fetch_board(self, fetcher: object, request: BoardRequest) -> BoardSnapshot:
            events.append(f"fetch {request.slug}")
            return super().fetch_board(fetcher, request)

    providers = {"reader": _Ordered("reader", reads=True), "plain": _Ordered("plain", reads=False)}
    settings = load_settings(data_dir=data).model_copy(update={"scan_workers": 1})
    run_scan(engine, settings, providers=providers)  # type: ignore[arg-type]

    reads = [i for i, e in enumerate(events) if e.startswith("read ")]
    assert len(reads) == 2  # boards a and b; never c
    for i in reads:
        assert events[i + 1].startswith("fetch "), events  # each read is its own board's dispatch
    assert events.count("fetch c") == 1
