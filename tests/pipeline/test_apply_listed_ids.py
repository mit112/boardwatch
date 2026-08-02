from __future__ import annotations

from pathlib import Path

from sqlalchemy import insert, select

from boardwatch.core.models import BoardSnapshot, RawPosting
from boardwatch.scan.apply import apply_board
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import insert_run


def _insert_company(engine) -> int:
    with engine.begin() as conn:
        result = conn.execute(
            insert(tables.companies).values(
                name="Acme", provider="smartrecruiters", slug="acme",
                source="user", watched=True,
            )
        )
        return int(result.inserted_primary_key[0])


def _posting(pid: str, body: str = "b") -> RawPosting:
    return RawPosting(
        provider_posting_id=pid, title=f"Job {pid}", url=f"https://x/{pid}",
        locations=[], body_text=body, raw_json={"id": pid},
    )


def _complete(url: str, postings_in: list[RawPosting], listed: frozenset[str]) -> BoardSnapshot:
    return BoardSnapshot(
        status="complete", postings=postings_in, url=url,
        observed_validators=None, error=None, listed_ids=listed,
    )


def _open_ids(engine, company_id: int) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            select(tables.postings.c.provider_posting_id).where(
                tables.postings.c.company_id == company_id, tables.postings.c.status == "open"
            )
        ).all()
    return {r.provider_posting_id for r in rows}


def test_known_postings_survive_when_details_are_skipped(tmp_path: Path) -> None:
    engine = get_engine(tmp_path)
    ensure_schema(engine)
    company_id = _insert_company(engine)
    url = "https://api.smartrecruiters.com/v1/companies/acme/postings?limit=100&offset=0"

    # Scan 1: full board of 3, all fetched.
    r1 = insert_run(engine)
    apply_board(engine, _complete(url, [_posting("A"), _posting("B"), _posting("C")],
                                  frozenset({"A", "B", "C"})), company_id, r1)
    assert _open_ids(engine, company_id) == {"A", "B", "C"}

    # Scan 2: all 3 are known/skipped -> postings EMPTY, but listed_ids still full.
    # This is the C1 corruption case: without listed_ids all three would close by scan 3.
    r2 = insert_run(engine)
    apply_board(engine, _complete(url, [], frozenset({"A", "B", "C"})), company_id, r2)
    assert _open_ids(engine, company_id) == {"A", "B", "C"}

    # Scan 3+4: C genuinely delisted (drops out of listed_ids). Closes after 2 misses.
    r3 = insert_run(engine)
    apply_board(engine, _complete(url, [], frozenset({"A", "B"})), company_id, r3)
    assert _open_ids(engine, company_id) == {"A", "B", "C"}  # 1 miss, still open
    r4 = insert_run(engine)
    apply_board(engine, _complete(url, [], frozenset({"A", "B"})), company_id, r4)
    assert _open_ids(engine, company_id) == {"A", "B"}       # C closed at 2 misses

    # Scan 5: C reappears. This mirrors the coordinator's OPEN-ONLY known_posting_ids
    # (Task 3): once C is closed its id is NOT in known, so SmartRecruiters re-fetches its
    # detail and C lands in snapshot.postings -> _apply_listed reopens it. That is why C is
    # a real posting here, not a masking shortcut.
    r5 = insert_run(engine)
    apply_board(engine, _complete(url, [_posting("C")], frozenset({"A", "B", "C"})), company_id, r5)
    assert _open_ids(engine, company_id) == {"A", "B", "C"}


def test_fallback_to_postings_when_listed_ids_empty(tmp_path: Path) -> None:
    """Existing single-request providers (listed_ids empty) must behave exactly as before:
    a posting absent from snapshot.postings takes a miss."""
    engine = get_engine(tmp_path)
    ensure_schema(engine)
    company_id = _insert_company(engine)
    url = "https://boards.example/x"
    r1 = insert_run(engine)
    apply_board(engine, _complete(url, [_posting("A"), _posting("B")], frozenset()), company_id, r1)
    r2 = insert_run(engine)
    apply_board(engine, _complete(url, [_posting("A")], frozenset()), company_id, r2)  # B absent
    r3 = insert_run(engine)
    apply_board(engine, _complete(url, [_posting("A")], frozenset()), company_id, r3)
    assert _open_ids(engine, company_id) == {"A"}  # B closed after 2 misses, listed_ids unused


def test_partial_snapshot_resets_listed_skipped_miss_counter(tmp_path: Path) -> None:
    """D23 on PARTIAL: a known/skipped posting that is still listed has its miss counter
    reset even when the snapshot is partial. Without this, one transient miss + a partial
    scan would close a still-listed posting a scan early."""
    engine = get_engine(tmp_path)
    ensure_schema(engine)
    company_id = _insert_company(engine)
    url = "https://api.smartrecruiters.com/v1/companies/acme/postings?limit=100&offset=0"
    apply_board(engine, _complete(url, [_posting("A"), _posting("B")], frozenset({"A", "B"})),
                company_id, insert_run(engine))
    # Scan 2 (complete): A omitted from listed -> 1 miss, still open.
    apply_board(engine, _complete(url, [], frozenset({"B"})), company_id, insert_run(engine))
    # Scan 3 (PARTIAL): A listed again but detail-skipped -> D23 reset must fire.
    partial = BoardSnapshot(status="partial", postings=[], url=url, observed_validators=None,
                            error="1 issue", listed_ids=frozenset({"A", "B"}))
    apply_board(engine, partial, company_id, insert_run(engine))
    # Scan 4 (complete): A omitted again. If scan 3 had NOT reset, A would hit 2 misses and close.
    apply_board(engine, _complete(url, [], frozenset({"B"})), company_id, insert_run(engine))
    assert _open_ids(engine, company_id) == {"A", "B"}  # A survived (reset made it 1 miss, not 2)
