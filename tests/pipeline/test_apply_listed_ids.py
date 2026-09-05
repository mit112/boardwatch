from __future__ import annotations

from pathlib import Path

from sqlalchemy import insert, select

from boardwatch.core.models import BoardSnapshot, RawPosting, ResponseValidators
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


def test_duplicate_provider_posting_id_in_one_snapshot_is_collapsed(tmp_path: Path) -> None:
    """A board may list one posting id more than once in a single snapshot (Workable repeats a
    shortcode across location facets). apply snapshots `existing` once, so without a guard both
    rows take the INSERT branch and the second violates UNIQUE(company_id, provider_posting_id) —
    the IntegrityError that aborted a whole scan when workable:alexander-dennis was first watched.
    apply must collapse the duplicates to one posting, the same guard the lanes apply."""
    engine = get_engine(tmp_path)
    ensure_schema(engine)
    company_id = _insert_company(engine)
    url = "https://apply.workable.com/alexander-dennis/"
    r1 = insert_run(engine)
    apply_board(
        engine,
        _complete(url, [_posting("B94B9BDDEE", body="one"), _posting("B94B9BDDEE", body="two")],
                  frozenset({"B94B9BDDEE"})),
        company_id, r1,
    )
    assert _open_ids(engine, company_id) == {"B94B9BDDEE"}  # one posting, no crash


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


def _validators(engine, url: str):
    with engine.connect() as conn:
        return conn.execute(
            select(tables.http_cache.c.etag).where(tables.http_cache.c.url == url)
        ).all()


def test_two_empty_complete_snapshots_do_not_close_a_whole_board(tmp_path: Path) -> None:
    """T15. `CLOSE_AFTER_MISSES` is 2, so two consecutive `200 {"jobs": []}` answers closed an
    entire board's inventory. The two commonest causes of that answer are not closure at all: a
    provider serving an empty list while degraded, and a tenant renaming its board so the old
    slug still resolves and returns nothing. Either way boardwatch deleted a live board from
    its own corpus on the strength of two empty responses.

    ZERO ONLY, never a ratio: a ratio guard on a legitimately shrinking board is a quarantine
    with no drain, because the board never rises back above the ratio. This guard drains itself
    — see the control below, where one listed posting restores normal miss counting at once.
    """
    engine = get_engine(tmp_path)
    ensure_schema(engine)
    company_id = _insert_company(engine)
    url = "https://api.smartrecruiters.com/v1/companies/acme/postings?limit=100&offset=0"
    apply_board(
        engine,
        _complete(url, [_posting("A"), _posting("B"), _posting("C")], frozenset({"A", "B", "C"})),
        company_id,
        insert_run(engine),
    )
    assert _open_ids(engine, company_id) == {"A", "B", "C"}

    empty = BoardSnapshot(
        status="complete", postings=[], url=url,
        observed_validators=ResponseValidators(etag="W/\"empty\"", last_modified=None),
        error=None, listed_ids=frozenset(),
    )
    first = apply_board(engine, empty, company_id, insert_run(engine))
    second = apply_board(engine, empty, company_id, insert_run(engine))

    assert _open_ids(engine, company_id) == {"A", "B", "C"}, "an empty answer closed the board"
    assert (first.closed, second.closed) == (0, 0)
    assert first.empty_complete_guarded and second.empty_complete_guarded
    # No miss counted at all — not merely "not closed yet". A counter left walking upward would
    # close the board on the first non-guarded scan that happened to miss one posting.
    with engine.connect() as conn:
        misses = conn.execute(
            select(tables.postings.c.consecutive_missing).where(
                tables.postings.c.company_id == company_id
            )
        ).scalars().all()
    assert set(misses) == {0}, misses
    # The validator is NOT cached. Caching the ETag of an empty answer makes the next scan a
    # 304, which is `unchanged`, which skips this board's inventory — the board would be frozen
    # at empty for as long as the provider served the same validator.
    assert _validators(engine, url) == []


def test_a_complete_snapshot_that_lists_some_postings_still_counts_a_miss(tmp_path: Path) -> None:
    """The control, and the drain. The guard is about ZERO, so a board that lists 2 of its 3
    postings is ordinary evidence and the third counts a miss exactly as before."""
    engine = get_engine(tmp_path)
    ensure_schema(engine)
    company_id = _insert_company(engine)
    url = "https://api.smartrecruiters.com/v1/companies/acme/postings?limit=100&offset=0"
    apply_board(
        engine,
        _complete(url, [_posting("A"), _posting("B"), _posting("C")], frozenset({"A", "B", "C"})),
        company_id,
        insert_run(engine),
    )

    partial_inventory = _complete(url, [_posting("A"), _posting("B")], frozenset({"A", "B"}))
    result = apply_board(engine, partial_inventory, company_id, insert_run(engine))

    assert result.empty_complete_guarded is False
    with engine.connect() as conn:
        misses = dict(
            conn.execute(
                select(
                    tables.postings.c.provider_posting_id, tables.postings.c.consecutive_missing
                ).where(tables.postings.c.company_id == company_id)
            ).all()
        )
    assert misses["C"] == 1, misses
    assert misses["A"] == 0 and misses["B"] == 0
